"""Fetch verified font assets into a project cache, never the skill directory."""
import argparse,io,json,urllib.request,zipfile
from pathlib import Path
from common import digest,atomic_json

FONTS={
 'VCR_OSD_MONO_1.001.ttf':{'sha256':'01918d86cb163a715dcb97165b997256734dfcc9f550beeb7c142fa4a064cf1c','url':'https://dl.dafont.com/dl/?f=vcr_osd_mono','source':'https://www.dafont.com/vcr-osd-mono.font?sort=date','zip':True},
 'unifont-16.0.04.hex.gz':{'sha256':'f9c8c7802453f47be02677176aeac2342ee96d354fad7a26cedcce48e68e1d9f','url':'https://unifoundry.com/pub/unifont/unifont-16.0.04/font-builds/unifont-16.0.04.hex.gz','source':'https://unifoundry.com/unifont.html','zip':False}
}

def fetch(folder,force=False):
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    for name,meta in FONTS.items():
        target=folder/name
        if target.exists() and digest(target)==meta['sha256']:continue
        if target.exists() and not force:raise ValueError(f'Unexpected font hash: {target}; use a clean cache or --force to fetch the pinned file')
        req=urllib.request.Request(meta['url'],headers={'User-Agent':'Mozilla/5.0 (font asset fetch)'})
        with urllib.request.urlopen(req,timeout=45) as response:data=response.read(10*1024*1024+1)
        if len(data)>10*1024*1024:raise ValueError('Unexpectedly large font download')
        if meta['zip']:
            archive=zipfile.ZipFile(io.BytesIO(data));found=[n for n in archive.namelist() if Path(n).name==name]
            if len(found)!=1:raise ValueError('Unexpected font archive contents')
            data=archive.read(found[0])
        temp=target.with_name(target.name+'.part');temp.write_bytes(data)
        if digest(temp)!=meta['sha256']:
            temp.unlink();raise ValueError(f'Font source changed for {name}; inspect upstream and update the verified manifest')
        temp.replace(target)
    atomic_json(folder/'font-sources.json',FONTS)
    return folder

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True);p.add_argument('--force',action='store_true');a=p.parse_args()
    print(fetch(a.out,a.force))
