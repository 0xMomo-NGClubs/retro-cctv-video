"""Small local helpers; no generation or network side effects."""
import hashlib,json,math,subprocess
from pathlib import Path

def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.part');temp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(path)

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def local(base,value):
    p=Path(value).expanduser();return p.resolve() if p.is_absolute() else (Path(base)/p).resolve()

def number(value,name,minimum=0):
    result=float(value)
    if not math.isfinite(result) or result<minimum:raise ValueError(f'{name} must be finite and >= {minimum}')
    return result

def probe(path):
    return json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(path)]))

def video_info(path):
    data=probe(path);v=next((s for s in data['streams'] if s['codec_type']=='video'),None)
    if not v:raise ValueError(f'No video stream: {path}')
    raw=v.get('duration',data.get('format',{}).get('duration'))
    if raw is None:raise ValueError(f'No measurable duration: {path}')
    return data,v,float(raw)

def audio_hash(path):
    return subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-map','0:a:0','-c','copy','-f','hash','-hash','sha256','-']).decode().strip()

def run(command):
    subprocess.run([str(x) for x in command],check=True)
