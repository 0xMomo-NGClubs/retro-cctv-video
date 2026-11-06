"""Explicit H3 T8 image-reference mapping; paid submissions never auto-retry."""
import argparse,copy,contextlib,hashlib,json,os,re
from pathlib import Path
from common import atomic_json,digest,local,video_info,number
from rh_client import Client,APIError,SubmissionUnknown,scrub

SECTIONS=('subject_definitions','summary','retention_analysis','detailed_description','overall_soundscape','non_diegetic_music')

def slot(graph,binding):
    node=str(binding.get('node'));field=binding.get('field')
    if node not in graph or not field or field not in graph[node].get('inputs',{}):raise ValueError(f'Invalid binding: node {node}, field {field}')
    if binding.get('class_type') and binding['class_type']!=graph[node]['class_type']:raise ValueError(f'Class mismatch on node {node}')
    return graph[node]['inputs'],field

def prune(graph,outputs):
    seen=set()
    def walk(n):
        n=str(n)
        if n in seen:return
        if n not in graph:raise ValueError(f'Unknown linked node {n}')
        seen.add(n)
        for val in graph[n].get('inputs',{}).values():
            if isinstance(val,list) and len(val)==2 and isinstance(val[1],int) and str(val[0]) in graph:walk(str(val[0]))
    for output in outputs:walk(output)
    return {n:v for n,v in graph.items() if n in seen}

def compile_project(project,shot_id,remote_images=None):
    path=Path(project).resolve();base=path.parent;cfg=json.loads(path.read_text())
    shots=[s for s in cfg.get('shots',[]) if s['id']==shot_id]
    if len(shots)!=1:raise ValueError('Shot ID must match exactly one configured shot')
    shot=shots[0];graph=json.loads(local(base,cfg['workflow_file']).read_text())
    if not isinstance(graph,dict) or not all(isinstance(n,dict) and 'class_type' in n for n in graph.values()):raise ValueError('Provide an API-format graph, not UI workflow JSON')
    prompt=local(base,shot['prompt_file']).read_text(encoding='utf-8')
    positions=[prompt.find(k) for k in SECTIONS]
    if any(p<0 for p in positions) or positions!=sorted(positions):raise ValueError('Prompt needs the six H3 sections in order')
    if re.search(r'\b(TODO|REPLACE_ME)\b|\{\{[^}]+\}\}',prompt):raise ValueError('Prompt contains unresolved placeholders')
    images=[local(base,p) for p in shot.get('images',[])];ib=cfg.get('image_bindings',[])
    if not images or len(ib)!=len(images):raise ValueError('Map exactly one image loader per image')
    for n in re.findall(r'<Picture\s+(\d+)>',prompt):
        if not 1<=int(n)<=len(images):raise ValueError(f'Picture {n} has no uploaded image')
    img_hashes=[digest(p) for p in images]
    if remote_images is not None and len(remote_images)!=len(images):raise ValueError('Uploaded image count mismatch')
    mapped=set()
    for name,value in [('prompt',prompt),('duration',number(shot['duration_seconds'],'duration_seconds',.001)),('seed',int(shot['seed']))]:
        binding=cfg['bindings'][name];inputs,field=slot(graph,binding);inputs[field]=value;mapped.add(str(binding['node']))
    for i,binding in enumerate(ib):
        inputs,field=slot(graph,binding)
        if graph[str(binding['node'])]['class_type']!='LoadImage' or field!='image':raise ValueError('This adapter supports LoadImage.image references only')
        inputs[field]=remote_images[i] if remote_images else 'LOCAL_SHA256:'+img_hashes[i];mapped.add(str(binding['node']))
    cond=cfg.get('conditioning_nodes',[])
    if not cond:raise ValueError('List every participating H3 conditioning node')
    for n in cond:
        n=str(n)
        if n not in graph or graph[n]['class_type']!='MiniMaxH3AudioConditioningT8':raise ValueError(f'Unsupported conditioning node {n}')
        inputs=graph[n]['inputs']
        for k in list(inputs):
            if k.startswith(('ref_images.','ref_videos.')):del inputs[k]
        for i,binding in enumerate(ib):inputs[f'ref_images.ref_image_{i}']=[str(binding['node']),0]
        mapped.add(n)
    protected=set(mapped)
    for override in cfg.get('overrides',[]):
        inputs,field=slot(graph,override)
        if str(override['node']) in protected:raise ValueError('Overrides cannot replace prompt, reference, duration, seed or conditioning bindings')
        inputs[field]=override['value'];mapped.add(str(override['node']))
    outputs=[str(n) for n in cfg.get('output_nodes',[])]
    result=str(cfg.get('result_node'))
    if not outputs or result not in outputs:raise ValueError('Select output_nodes and one result_node')
    graph=prune(graph,outputs)
    if not mapped<=set(graph):raise ValueError('Some mapped nodes do not participate in selected outputs')
    for n,node in graph.items():
        kind=node['class_type'].lower()
        if node['class_type']=='MiniMaxH3AudioConditioningT8' and n not in {str(c) for c in cond}:raise ValueError('An unlisted H3 conditioning node retains template references')
        if ('load' in kind and any(k in kind for k in ('image','video','audio'))) and n not in {str(b['node']) for b in ib}:raise ValueError(f'Unbound media loader {n}: {node["class_type"]}')
    base_url=cfg.get('base_url') or os.environ.get('RUNNINGHUB_BASE_URL') or 'https://www.runninghub.ai'
    canonical=copy.deepcopy(graph)
    for i,binding in enumerate(ib):canonical[str(binding['node'])]['inputs'][binding['field']]='LOCAL_SHA256:'+img_hashes[i]
    payload={'base_url':base_url.rstrip('/'),'workflow_id':str(cfg.get('workflow_id') or ''),'instance_type':cfg.get('instance_type','default'),'result_node':result,'graph':canonical,'images':img_hashes,'shot':shot_id}
    if not re.fullmatch(r'\d+',payload['workflow_id']):raise ValueError('Set a numeric workflow_id')
    fingerprint=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return cfg,shot,graph,images,fingerprint

@contextlib.contextmanager
def locked(path):
    # This helper targets the macOS/Linux Codex runtime. Other hosts can use a native exclusive lock.
    import fcntl
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.with_name(path.name+'.lock').open('a') as f:
        try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise ValueError('This state is already in use') from None
        try:yield
        finally:fcntl.flock(f,fcntl.LOCK_UN)

def state_context(project,shot_id,state_path,client=None):
    cfg,shot,graph,images,fp=compile_project(project,shot_id)
    client=client or Client(cfg.get('base_url'))
    account=hashlib.sha256(client.key.encode()).hexdigest()
    expected={'fingerprint':fp,'account_digest':account,'base_url':client.base}
    path=Path(state_path)
    state=json.loads(path.read_text()) if path.exists() else {**expected,'status':'PREPARED','shot':shot_id}
    if any(state.get(k)!=v for k,v in expected.items()):raise ValueError('Inputs, account or region changed; use a new state file')
    return cfg,shot,graph,images,client,state

def submit(project,shot_id,state_path,client=None):
    with locked(state_path):
        cfg,shot,graph,images,c,state=state_context(project,shot_id,state_path,client)
        if state.get('task_id'):return state
        if state['status']!='PREPARED':raise ValueError(f'Will not resubmit state {state["status"]}; reconcile history or fix inputs in a new state')
        # Upload is not a generation submission. Unknown uploads may be repeated; create never is.
        names=[c.upload(p) for p in images]
        _,_,remote,_,current_fp=compile_project(project,shot_id,names)
        if current_fp!=state['fingerprint']:raise ValueError('Inputs changed during upload; no task submitted')
        state['status']='SUBMITTING';atomic_json(state_path,state)
        try:
            state['task_id']=c.create(cfg['workflow_id'],remote,cfg.get('instance_type','default'));state['status']='SUBMITTED'
        except SubmissionUnknown as e:
            state.update(status='SUBMISSION_UNKNOWN',error=str(scrub(str(e),c.key)));atomic_json(state_path,state);raise
        except APIError as e:
            state.update(status='SUBMISSION_REJECTED',error=str(scrub(str(e),c.key)));atomic_json(state_path,state);raise
        except Exception:
            state['status']='SUBMISSION_UNKNOWN';atomic_json(state_path,state);raise
        atomic_json(state_path,state);return state

def poll(project,shot_id,state_path,download,client=None):
    with locked(state_path):
        cfg,shot,graph,images,c,state=state_context(project,shot_id,state_path,client)
        if not state.get('task_id'):raise ValueError('No known task; reconcile history before polling')
        target=Path(download).resolve()
        if state.get('download_sha256') and target.is_file() and digest(target)==state['download_sha256']:return state
        try:
            status=c.status(state['task_id']);state['status']=status
            if status=='SUCCESS':
                outputs=c.outputs(state['task_id']);state['receipt']=scrub(outputs,c.key)
                items=[x for x in outputs if str(x.get('nodeId'))==str(cfg['result_node']) and x.get('fileUrl')]
                if len(items)!=1:raise ValueError('Expected exactly one file from result_node; inspect the saved receipt')
                pending=target.with_name(target.stem+'.download'+target.suffix)
                c.download(items[0]['fileUrl'],pending);_,v,dur=video_info(pending);pending.replace(target)
                state.update(download=str(target),download_sha256=digest(target),actual_duration=dur)
            elif status in ('FAILED','FAILURE','CANCELED','CANCELLED'):
                try:state['failure_receipt']=scrub(c.post('/task/openapi/outputs',{'taskId':state['task_id']}),c.key)
                except APIError as e:state['failure_detail']=str(scrub(str(e),c.key))
            state.pop('poll_error',None)
        except Exception as e:
            state['poll_error']=str(scrub(str(e),c.key));atomic_json(state_path,state);raise
        atomic_json(state_path,state);return state

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    f=sub.add_parser('fetch');f.add_argument('--workflow-id',required=True);f.add_argument('--out',required=True);f.add_argument('--base-url')
    i=sub.add_parser('inspect');i.add_argument('--workflow',required=True)
    for name in ('compile','submit','poll','attach'):
        s=sub.add_parser(name);s.add_argument('--project',required=True);s.add_argument('--shot',required=True)
        if name=='compile':s.add_argument('--out',required=True)
        else:s.add_argument('--state',required=True)
        if name=='poll':s.add_argument('--download',required=True)
        if name=='attach':s.add_argument('--task-id',required=True)
    a=p.parse_args()
    if a.command=='fetch':
        atomic_json(a.out,Client(a.base_url).workflow(a.workflow_id));result={'workflow_saved':str(Path(a.out).resolve())}
    elif a.command=='inspect':
        graph=json.loads(Path(a.workflow).read_text());result={n:{'class_type':v.get('class_type'),'inputs':list(v.get('inputs',{}))} for n,v in graph.items()}
    elif a.command=='compile':
        cfg,shot,graph,images,fp=compile_project(a.project,a.shot);atomic_json(a.out,{'fingerprint':fp,'graph':graph,'local_image_hashes':[digest(p) for p in images]});result={'nodes':len(graph),'fingerprint':fp,'paid_task_submitted':False}
    elif a.command=='submit':result=submit(a.project,a.shot,a.state)
    elif a.command=='poll':result=poll(a.project,a.shot,a.state,a.download)
    else:
        if not re.fullmatch(r'\d+',a.task_id):raise ValueError('Task ID must be numeric')
        with locked(a.state):
            *_,c,state=state_context(a.project,a.shot,a.state)
            if state.get('task_id') not in (None,a.task_id):raise ValueError('A different task is already attached')
            if state['status'] not in ('SUBMISSION_UNKNOWN','SUBMITTING','PREPARED','SUBMITTED'):raise ValueError('Cannot attach a task to this state')
            state.update(task_id=a.task_id,status='SUBMITTED',attachment='confirmed by operator');atomic_json(a.state,state);result=state
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
