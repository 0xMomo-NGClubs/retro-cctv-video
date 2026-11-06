"""Render fixed-view grayscale footage with softened pixel OSD."""
import argparse,json,math,subprocess
from fractions import Fraction
from pathlib import Path
from common import atomic_json,digest,local,number,probe,run,video_info,audio_hash
from osd import Renderer

FF=['ffmpeg','-hide_banner','-loglevel','error','-y']

def verify(path,audio_source=None,expected_frames=None,expected_fps=None):
    data,v,duration=video_info(path)
    frames=int(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-count_frames','-show_entries','stream=nb_read_frames','-of','csv=p=0',str(path)]).decode().strip())
    fps=float(Fraction(v['avg_frame_rate']))
    if expected_frames is not None and frames!=expected_frames:raise ValueError(f'Frame count {frames} != {expected_frames}')
    if expected_fps is not None and abs(fps-expected_fps)>1e-5:raise ValueError(f'FPS {fps} != {expected_fps}')
    run(FF+['-xerror','-i',path,'-map','0:v:0','-map','0:a?','-f','null','-'])
    result={'file':str(Path(path).resolve()),'frames':frames,'fps':fps,'duration':duration,'size':[v['width'],v['height']],'sha256':digest(path),'full_decode':'passed'}
    if audio_source:
        result['audio_bitstream_identical']=audio_hash(path)==audio_hash(audio_source)
        if not result['audio_bitstream_identical']:raise ValueError('Copied audio hash differs from premix')
    return result

def render(project,out,work):
    project=Path(project).resolve();base=project.parent;cfg=json.loads(project.read_text());o=cfg.get('output',{})
    w=int(o.get('width',1280));h=int(o.get('height',720));fps=number(o.get('fps',24),'fps',1)
    if not(16<=w<=7680 and 16<=h<=7680 and w%2==0 and h%2==0):raise ValueError('Use even output dimensions from 16 to 7680')
    fit=o.get('fit','contain')
    if fit not in ('contain','cover'):raise ValueError('fit must be contain or cover')
    crf=int(o.get('crf',18))
    if not 0<=crf<=51:raise ValueError('CRF must be 0..51')
    out=Path(out).resolve();work=Path(work).resolve();work.mkdir(parents=True,exist_ok=True);out.parent.mkdir(parents=True,exist_ok=True)
    audio=cfg.get('audio',{});mode=audio.get('mode','segments')
    if mode not in ('copy','segments'):raise ValueError('audio.mode must be copy or segments')
    segments=cfg.get('segments',[])
    if not segments:raise ValueError('segments is empty')
    prepared=[];total=0
    for i,s in enumerate(segments):
        if any(k in s for k in ('zoom','crop','scale','camera_move')):raise ValueError('Per-segment framing changes are not supported for fixed CCTV')
        src=local(base,s['file']);data,v,dur=video_info(src)
        if out==src:raise ValueError('Output must not overwrite source')
        start=number(s.get('start_seconds',0),'start_seconds')
        if start>=dur:raise ValueError(f'Segment starts after video ends: {src.name}')
        if 'frames' in s and 'duration_seconds' in s:raise ValueError('Choose frames or duration_seconds')
        requested=number(s.get('duration_seconds',dur-start),'duration_seconds',.001)
        rawframes=s.get('frames',round(requested*fps));n=int(rawframes)
        if n!=float(rawframes) or n<1:raise ValueError('frames must be a positive integer')
        if n/fps>dur-start+1/fps+.002:raise ValueError(f'Segment is longer than source: {src.name}')
        target=work/f'segment-{i:03d}.mkv';temp=work/f'segment-{i:03d}.part.mkv'
        scale=f'scale={w}:{h}:force_original_aspect_ratio={"decrease" if fit=="contain" else "increase"}'
        frame=f'pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black' if fit=='contain' else f'crop={w}:{h}'
        vf=f'fps={fps},trim=end_frame={n},setpts=PTS-STARTPTS,{scale},{frame},setsar=1,hue=s=0,format=yuv420p'
        command=FF+['-ss',start,'-i',src]
        has_audio=any(st['codec_type']=='audio' for st in data['streams'])
        if mode=='segments' and not has_audio:command+=['-f','lavfi','-i','anullsrc=r=48000:cl=stereo']
        command+=['-map','0:v:0','-vf',vf,'-c:v','ffv1','-level','3','-threads','2']
        if mode=='segments':
            duration=n/fps;fade=min(number(audio.get('fade_seconds',.03),'fade_seconds'),duration/2)
            af=f'aresample=48000,aformat=sample_fmts=s16:channel_layouts=stereo,apad,atrim=duration={duration},asetpts=PTS-STARTPTS'
            if fade:af+=f',afade=t=in:d={fade},afade=t=out:st={duration-fade}:d={fade}'
            command+=['-map','0:a:0' if has_audio else '1:a:0','-af',af,'-c:a','pcm_s16le']
        else:command+=['-an']
        command += ['-t',n/fps,temp];run(command);temp.replace(target)
        prepared.append({'file':str(target),'source':str(src),'source_sha256':digest(src),'start_seconds':start,'frames':n});total+=n
    duration=total/fps
    # Generated intermediary names avoid concat quoting of arbitrary user filenames.
    listing=work/'concat.txt';listing.write_text(''.join(f"file 'segment-{i:03d}.mkv'\n" for i in range(len(prepared))))
    joined=work/'joined.mkv';run(FF+['-f','concat','-safe','1','-i',listing,'-c','copy',joined])
    Renderer(cfg.get('osd',{}),base,(w,h)).write(duration,work/'osd')
    premix=None;command=FF+['-i',joined,'-framerate','1','-i',work/'osd'/'osd-%06d.png']
    if mode=='copy':
        premix=local(base,audio['file'])
        if out==premix:raise ValueError('Output must not overwrite premix')
        ad=probe(premix);astream=next((s for s in ad['streams'] if s['codec_type']=='audio'),None)
        if not astream:raise ValueError('Premix has no audio')
        if astream.get('codec_name') not in ('aac','mp3','alac'):raise ValueError('Premix codec is not in the supported MP4 copy set; prepare an MP4-compatible premix')
        alength=float(astream.get('duration',ad.get('format',{}).get('duration',0)))
        if abs(alength-duration)>max(.1,2/fps):raise ValueError('Premix must match the complete video duration; prepare a synchronized full-length mix')
        command+=['-i',premix]
    command+=['-filter_complex','[0:v][1:v]overlay=eof_action=repeat:shortest=0:format=auto,format=yuv420p[v]','-map','[v]']
    if mode=='copy':command+=['-map','2:a:0','-c:a','copy']
    else:
        gain=float(audio.get('gain_db',-1.5));limit=number(audio.get('peak_limit',.794328),'peak_limit',.0625)
        if not math.isfinite(gain) or limit>1:raise ValueError('Invalid gain or peak_limit')
        command+=['-map','0:a:0','-af',f'volume={gain}dB,alimiter=limit={limit}:level=false:latency=true','-c:a','aac','-b:a','192k']
    temp=out.with_name(out.stem+'.part.mp4')
    command+=['-c:v','libx264','-preset','medium','-crf',crf,'-r',fps,'-frames:v',total,'-t',duration,'-movflags','+faststart',temp]
    run(command)
    report=verify(temp,premix,total,fps);temp.replace(out);report['file']=str(out)
    report.update({'project':str(project),'project_sha256':digest(project),'segments':prepared,'expected_frames':total,'audio_mode':mode,'fit':fit})
    atomic_json(work/'validation.json',report);return report

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    i=sub.add_parser('inspect');i.add_argument('video')
    v=sub.add_parser('verify');v.add_argument('video');v.add_argument('--audio-source');v.add_argument('--expected-frames',type=int);v.add_argument('--expected-fps',type=float)
    r=sub.add_parser('render');r.add_argument('--project',required=True);r.add_argument('--out',required=True);r.add_argument('--work',required=True)
    a=p.parse_args()
    if a.command=='inspect':result=probe(a.video)
    elif a.command=='verify':result=verify(a.video,a.audio_source,a.expected_frames,a.expected_fps)
    else:result=render(a.project,a.out,a.work)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
