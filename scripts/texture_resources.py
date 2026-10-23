"""Provision official AccoMontage assets and a compact numeric donor library."""
from pathlib import Path
import gc
import hashlib
import json
import urllib.request
import zipfile
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
DIRECTORY=ROOT/'models/accomontage'
URL='https://drive.usercontent.google.com/download?id=1EPj-O4dR3EWiv1kjoBo0EzM_yNoK6tNt&export=download&confirm=t'
ARCHIVE_SHA='5ed631f7e08c35172ee976d3260521c672b4981d0f7151adc436c1396e522fab'
EXPECTED={'model_master_final.pt':'eae8cd37fb0c2d830a14401d6831d50c598550f5f62b61e680d6dd4b35c1b8b7','donors-v1.npz':'7b1bce54b88dfe9a97bb8e0726f9f0aa3459432caeca3b0b4f50e5799749f73f'}

def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()

def rhythm(melody):
    values=np.zeros(64,np.float32);length=min(64,len(melody))
    values[:length]=(melody[:length,:128].sum(axis=-1)>0)
    return values.reshape(16,4).sum(axis=1)

def main():
    DIRECTORY.mkdir(exist_ok=True);archive=DIRECTORY/'checkpoints.zip'
    manifest_path=DIRECTORY/'manifest.json'
    if manifest_path.is_file():
        try:existing=json.loads(manifest_path.read_text(encoding='utf-8'))
        except (ValueError,OSError):existing={}
        if all((DIRECTORY/name).is_file() and digest(DIRECTORY/name)==sha and existing.get('files',{}).get(name,{}).get('sha256')==sha for name,sha in EXPECTED.items()):
            print('Existing accompaniment resources verified; no download required.');return
    if not archive.exists():
        partial=archive.with_suffix('.zip.part')
        with urllib.request.urlopen(URL,timeout=60) as response,partial.open('wb') as target:
            while block:=response.read(1024*1024):target.write(block)
        if digest(partial)!=ARCHIVE_SHA:raise RuntimeError('AccoMontage archive checksum mismatch.')
        partial.replace(archive)
    if digest(archive)!=ARCHIVE_SHA:raise RuntimeError('AccoMontage archive checksum mismatch.')
    with zipfile.ZipFile(archive) as z:
        if z.testzip():raise RuntimeError('Damaged AccoMontage archive.')
        for name in ('model_master_final.pt','phrase_data.npz'):
            path=DIRECTORY/name
            original=z.read('checkpoints/'+name)
            if not path.exists() or digest(path)!=hashlib.sha256(original).hexdigest():path.write_bytes(original)
    bank=DIRECTORY/'donors-v1.npz'
    if bank.exists() and digest(bank)!=EXPECTED[bank.name]:bank.unlink()
    if not bank.exists():
        source=np.load(DIRECTORY/'phrase_data.npz',allow_pickle=True)
        melody=source['melody'];metadata=[];features=[]
        for song,phrases in enumerate(melody):
            eligible=[i for i,m in enumerate(phrases) if len(m)>=32 and m[:64,:128].sum()>=6]
            selected=sorted({eligible[0],eligible[len(eligible)//2],eligible[-1]}) if eligible else []
            for phrase in selected:
                metadata.append((song,phrase));features.append(rhythm(phrases[phrase]))
        del melody;gc.collect()
        accompaniment=source['acc'];rolls=[];stats=[]
        for song,phrase in metadata:
            raw=accompaniment[song][phrase];roll=np.zeros((64,128),np.uint8);length=min(64,len(raw));roll[:length]=np.clip(raw[:length],0,31).astype(np.uint8)
            activity=(roll>0).sum(axis=1);positions=np.flatnonzero(activity)
            density=len(positions)/16;poly=float(activity[positions].mean()) if len(positions) else 0
            sync=float((positions%4!=0).mean()) if len(positions) else 0
            rolls.append(roll);stats.append((density,poly,sync))
        del accompaniment;source.close();gc.collect()
        np.savez_compressed(bank,rolls=np.stack(rolls),melody=np.stack(features),stats=np.array(stats,np.float32),references=np.array(metadata,np.int32))
    files={name:{'bytes':(DIRECTORY/name).stat().st_size,'sha256':digest(DIRECTORY/name)} for name in EXPECTED}
    if any(info['sha256']!=EXPECTED[name] for name,info in files.items()):raise RuntimeError('Prepared resource checksum mismatch.')
    manifest={'version':1,'repository':'https://github.com/zhaojw1998/AccoMontage','commit':'9630afe08eb2e90b0b94fcf97154d9385fda5e4c','archive':{'url':URL,'sha256':ARCHIVE_SHA},'files':files}
    (DIRECTORY/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('Texture resources ready:',files,flush=True)

if __name__=='__main__':main()
