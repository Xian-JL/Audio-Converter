"""Prepare pinned CC BY instrument samples locally; never reads user audio."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import re
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT/'public/instruments'
REVISION='622c2f1c32c8cfce4158ddc3eb26e518ddef37e5'
BASE=f'https://raw.githubusercontent.com/nbrosowsky/tonejs-instruments/{REVISION}'
IDS=('guitar-nylon','violin','cello','flute','clarinet','bassoon','trumpet','trombone','harp','organ','xylophone')

def fetch(url):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'LocalAudio/0.2'}),timeout=60) as response:return response.read()
        except Exception:
            if attempt==3:raise
            time.sleep(attempt+1)

def midi(name):
    match=re.fullmatch(r'([A-G])(#?)(\d)',name)
    return (int(match[3])+1)*12+{'C':0,'D':2,'E':4,'F':5,'G':7,'A':9,'B':11}[match[1]]+bool(match[2])

def main():
    DEST.mkdir(parents=True,exist_ok=True);manifest_path=DEST/'manifest.json'
    old={}
    if manifest_path.is_file():
        try:old=json.loads(manifest_path.read_text(encoding='utf-8'))
        except (ValueError,OSError):pass
        entries=[(DEST/i/n,info) for i,bank in old.get('instruments',{}).items() for n,info in bank.get('files',{}).items()]
        if old.get('revision')==REVISION and set(old.get('instruments',{}))==set(IDS) and all(p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==v['sha256'] for p,v in entries):
            print('Existing instrument samples verified; no download required.');return
    source=fetch(BASE+'/Tonejs-Instruments.js').decode();plans={};jobs=[]
    for instrument in IDS:
        block=re.search(r"'"+re.escape(instrument)+r"':\s*\{(.*?)\n\s*\}",source,re.S)
        if not block:raise RuntimeError('Missing upstream instrument: '+instrument)
        notes=dict(re.findall(r"'([A-G]#?\d)':\s*'([^']+)\.\[mp3\|ogg\]'",block[1]))
        chosen=sorted({min(notes,key=lambda n:abs(midi(n)-target)) for target in (36,42,48,54,60,66,72,78,84)},key=midi)
        plans[instrument]={'samples':{note:notes[note]+'.mp3' for note in chosen},'files':{}}
        for note in chosen:jobs.append((instrument,notes[note]+'.mp3'))
    def prepare(job):
        instrument,name=job;path=DEST/instrument/name;path.parent.mkdir(exist_ok=True)
        expected=old.get('instruments',{}).get(instrument,{}).get('files',{}).get(name,{}).get('sha256')
        if not path.exists() or path.stat().st_size<500 or not expected or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            data=fetch(f'{BASE}/samples/{instrument}/{name}')
            if len(data)<500 or data[:15].lower().startswith(b'<!doctype'):raise RuntimeError('Invalid sample: '+str(path))
            path.with_suffix('.part').write_bytes(data);path.with_suffix('.part').replace(path)
        data=path.read_bytes();return instrument,name,{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for instrument,name,info in pool.map(prepare,jobs):plans[instrument]['files'][name]=info
    for name in ('LICENSE.md','sample-source-info.txt'):(DEST/name).write_bytes(fetch(BASE+'/'+name))
    manifest={'repository':'https://github.com/nbrosowsky/tonejs-instruments','revision':REVISION,'license':'CC BY 3.0 (samples); MIT (loader, not used)','instruments':plans}
    manifest_path.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('Prepared',len(plans),'instruments,',len(jobs),'samples,',sum(p.stat().st_size for p in DEST.rglob('*.mp3')),'bytes')

if __name__=='__main__':main()
