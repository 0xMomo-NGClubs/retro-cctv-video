"""Fixed-cell CCTV OSD; low-resolution text only is softened."""
import argparse,datetime,gzip,json,math,warnings
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageFilter,ImageChops
from common import local,number,atomic_json

class Renderer:
    def __init__(self,cfg,base,output_size):
        self.cfg=cfg;self.output=tuple(map(int,output_size))
        default_w=round(480*self.output[0]/self.output[1])
        self.native=tuple(map(int,cfg.get('native_size',[default_w,480])))
        if min(self.native)<32 or max(self.native)>4096:raise ValueError('OSD native_size must be 32..4096')
        if abs(self.native[0]/self.native[1]-self.output[0]/self.output[1])>.03:raise ValueError('OSD native_size must match the output aspect ratio')
        fonts=local(base,cfg['font_dir'])
        self.font=ImageFont.truetype(str(fonts/'VCR_OSD_MONO_1.001.ttf'),28)
        self.hex={}
        with gzip.open(fonts/'unifont-16.0.04.hex.gz','rt') as f:
            for line in f:
                k,v=line.strip().split(':');self.hex[int(k,16)]=v
        fields=cfg.get('start_time','09:00:00').split(':')
        if len(fields)!=3:raise ValueError('start_time must be HH:MM:SS')
        h,m,s=map(int,fields)
        if not(0<=h<24 and 0<=m<60 and 0<=s<60):raise ValueError('Invalid start_time')
        self.start=h*3600+m*60+s
        if cfg.get('date') and cfg.get('date_label'):raise ValueError('Choose date or date_label, not both')
        self.date=datetime.date.fromisoformat(cfg['date']) if cfg.get('date') else None
        self.blur=number(cfg.get('blur',.45),'blur');self.echo=number(cfg.get('echo',.07),'echo')
        if self.echo>1 or self.blur>5:raise ValueError('Use echo 0..1 and blur 0..5')
        self.camera=str(cfg.get('camera','CAM1'));self.place=str(cfg.get('place',''))
        self.cache={}

    def text_at(self,sec):
        value=self.start+int(sec);day,clock=divmod(value,86400);h,rest=divmod(clock,3600);m,s=divmod(rest,60)
        if self.date:
            d=self.date+datetime.timedelta(days=day);prefix=f'{d.year:04d}年{d.month:02d}月{d.day:02d}日'
        else:prefix=str(self.cfg.get('date_label',''))
        return f'{prefix}{h:02d}:{m:02d}:{s:02d}'

    def glyph(self,ch):
        if ch in self.cache:return self.cache[ch]
        if ord(ch)<128:
            image=Image.new('L',(16,24));ImageDraw.Draw(image).text((0,-2),ch,font=self.font,fill=255)
            result=(image.point(lambda v:255 if v>=128 else 0),16)
        else:
            if ord(ch) not in self.hex:raise ValueError(f'No explicit glyph for {ch!r}; choose supported text or adapt the font')
            raw=self.hex[ord(ch)];w=len(raw)//4;image=Image.new('L',(w,16));step=w//4
            for y in range(16):
                bits=int(raw[y*step:(y+1)*step],16)
                for x in range(w):
                    if bits & (1<<(w-1-x)):image.putpixel((x,y),255)
            result=(image.resize((24,24),Image.Resampling.NEAREST),24)
        self.cache[ch]=result;return result

    def line(self,text,spacing=0):
        if '\n' in text or '\r' in text:raise ValueError('OSD fields must be single-line text')
        items=[self.glyph(c) for c in text]
        width=sum(w for _,w in items)+max(0,len(items)-1)*spacing
        canvas=Image.new('L',(max(1,width),24));x=0
        for g,w in items:canvas.paste(g,(x,0));x+=w+spacing
        return canvas

    def position(self,key,default):
        v=self.cfg.get(key,default)
        if len(v)!=2 or not all(math.isfinite(float(x)) and 0<=float(x)<1 for x in v):raise ValueError(f'Invalid {key}')
        return tuple(round(float(x)*dim) for x,dim in zip(v,self.native))

    def paste(self,mask,text,pos,spacing=0):
        if not text:return 0
        g=self.line(text,spacing);x,y=pos
        available_w=self.native[0]-x-8;available_h=self.native[1]-y-4
        scale=min(1,available_w/g.width,available_h/g.height)
        if scale<=0:raise ValueError('OSD anchor outside image')
        if scale<1:g=g.resize((max(1,round(g.width*scale)),max(1,round(g.height*scale))),Image.Resampling.NEAREST)
        region=(x,y,x+g.width,y+g.height);mask.paste(ImageChops.lighter(mask.crop(region),g),(x,y));return g.width

    def render(self,sec):
        mask=Image.new('L',self.native)
        self.paste(mask,self.text_at(sec),self.position('clock_anchor',[.07026,.03542]))
        camera_pos=self.position('camera_anchor',[.03279,.88333]);cw=self.paste(mask,self.camera,camera_pos)
        px,py=self.position('place_anchor',[.14520,.87917]);px=max(px,camera_pos[0]+cw+32)
        if self.place:self.paste(mask,self.place,(px,py),2)
        edge=mask.filter(ImageFilter.MaxFilter(3))
        black=Image.new('RGBA',self.native,(0,0,0,0));black.putalpha(edge.point(lambda a:round(a*.87)))
        face=Image.new('RGBA',self.native,(230,230,230,0));face.putalpha(mask.point(lambda a:round(a*.98)))
        layer=Image.alpha_composite(black,face).filter(ImageFilter.GaussianBlur(self.blur))
        if self.echo:
            ghost=Image.new('RGBA',self.native);ghost.alpha_composite(layer,(1,0));ghost.putalpha(ghost.getchannel('A').point(lambda a:round(a*self.echo)));layer=Image.alpha_composite(ghost,layer)
        return layer.resize(self.output,Image.Resampling.BILINEAR)

    def write(self,duration,out):
        out=Path(out);out.mkdir(parents=True,exist_ok=True)
        if self.cfg.get('date_label') and self.start+duration>=86400:warnings.warn('date_label crosses midnight: check the date label manually')
        # An extra OSD frame and non-shortest overlay both protect fractional tails.
        count=math.ceil(duration)+1
        for sec in range(count):self.render(sec).save(out/f'osd-{sec:06d}.png')
        metadata={'native_size':self.native,'output_size':self.output,'duration':duration,'osd_frames':count,'digit_bounds':{c:self.font.getbbox(c) for c in '0123456789'},'digit_advance':{c:self.font.getlength(c) for c in '0123456789'},'first_clock':self.text_at(0),'last_clock':self.text_at(int(duration))}
        atomic_json(out/'settings.json',metadata);return metadata

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--project',required=True);p.add_argument('--duration',required=True,type=float);p.add_argument('--out',required=True);a=p.parse_args()
    path=Path(a.project).resolve();cfg=json.loads(path.read_text());o=cfg.get('output',{})
    print(json.dumps(Renderer(cfg['osd'],path.parent,(o.get('width',1280),o.get('height',720))).write(number(a.duration,'duration',.001),a.out),ensure_ascii=False))
