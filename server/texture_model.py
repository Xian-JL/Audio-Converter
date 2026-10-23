"""Pinned AccoMontage chord/texture VAE on CPU, with compact phrase retrieval.

The neural decoder is upstream code. Retrieval and left-hand reduction are local
adaptations; this is not the unmodified two-handed AccoMontage pipeline.
"""
from functools import lru_cache
from pathlib import Path
import hashlib
import importlib
import importlib.util
import json
import sys
import types
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
DIRECTORY=ROOT/'models/accomontage'

def available():
    return all((DIRECTORY/name).is_file() for name in ('manifest.json','model_master_final.pt','donors-v1.npz')) and importlib.util.find_spec('torch') is not None and importlib.util.find_spec('pretty_midi') is not None

@lru_cache(maxsize=1)
def runtime():
    if not available():raise ValueError('Accompaniment resources are missing. Run SetupTexture.cmd first.')
    import torch
    manifest=json.loads((DIRECTORY/'manifest.json').read_text(encoding='utf-8'))
    for name,info in manifest['files'].items():
        path=DIRECTORY/name
        if hashlib.sha256(path.read_bytes()).hexdigest()!=info['sha256']:raise ValueError('Accompaniment resources are damaged. Run SetupTexture.cmd again.')
    root=ROOT/'vendor/AccoMontage/AccoMontage';prefix='_local_acco'
    # Avoid upstream MIDI/chord-recognition/training entry points and CUDA-only setup.
    for name,folder in [(prefix,root),(prefix+'.models',root/'models'),(prefix+'.models.amc_dl',root/'models/amc_dl'),(prefix+'.models.amc_dl.torch_plus',root/'models/amc_dl/torch_plus')]:
        package=types.ModuleType(name);package.__path__=[str(folder)];sys.modules[name]=package
    module=importlib.import_module(prefix+'.models.amc_dl.torch_plus.module')
    sys.modules[prefix+'.models.amc_dl.torch_plus'].PytorchModel=module.PytorchModel
    cls=importlib.import_module(prefix+'.models.Poly_Dis').DisentangleVAE
    torch.set_num_threads(4)
    model=cls.init_model(torch.device('cpu'))
    model.load_state_dict(torch.load(DIRECTORY/'model_master_final.pt',map_location='cpu',weights_only=True));model.eval()
    for component in model.modules():
        if hasattr(component,'device'):component.device=torch.device('cpu')
    bank=np.load(DIRECTORY/'donors-v1.npz',allow_pickle=False)
    return model,{k:bank[k] for k in bank.files},manifest

def choose_donors(score,harmony,style,density,variant,bank):
    from .meter_grid import score_grid
    grid=score_grid(score);bars=harmony['bars'];starts=harmony['phraseStarts']
    pieces=[]
    for index,first in enumerate(starts):
        end=starts[index+1]-1 if index+1<len(starts) else len(bars)
        group=[b for b in bars[first-1:end] if not b.get('pickup')]
        for offset in range(0,len(group),4):
            window=group[offset:offset+4]
            if not window:continue
            left=window[0].get('startTick',(window[0]['number']-1)*grid.bar_ticks)
            length=len(window)*16;onsets=np.zeros(64,np.float32)
            local=[n for n in score['notes'] if left<=n['startTick']<left+len(window)*grid.bar_ticks]
            for note in local:
                frame=int((note['startTick']-left)/(score['divisions']/4))
                if 0<=frame<64:onsets[frame]+=1
            query=onsets.reshape(16,4).sum(axis=1)
            donor=bank['melody'];similarity=(donor@query)/(np.linalg.norm(donor,axis=1)*np.linalg.norm(query)+1e-7)
            target=(1.1,1.65,2.2)[density]
            if len(local)/max(len(window),1)>8:target*=.65
            target_sync={'lyrical':.45,'flowing':.6,'syncopated':.78}[style]
            stats=bank['stats'];cost=1-similarity+.38*np.abs(stats[:,0]-target)+.3*np.abs(stats[:,2]-target_sync)+.12*np.maximum(0,stats[:,1]-2.4)
            cost[(stats[:,0]<.4)|(stats[:,1]>3.5)]=100
            candidates=np.argsort(cost,kind='stable')[:8]
            pieces.append({'bars':window,'left':left,'length':length,'candidates':candidates,'costs':cost,'onsets':len(local)})
    if not pieces:return []
    values=[float(pieces[0]['costs'][i])+.07*abs(j-variant) for j,i in enumerate(pieces[0]['candidates'])];history=[]
    for p,previous in zip(pieces[1:],pieces):
        updated=[];back=[]
        for rank,target in enumerate(p['candidates']):
            options=[value+.25*abs(float(bank['stats'][target,0]-bank['stats'][source,0]))+.15*abs(float(bank['stats'][target,1]-bank['stats'][source,1])) for value,source in zip(values,previous['candidates'])]
            best=min(range(len(options)),key=lambda n:(options[n],n));back.append(best);updated.append(options[best]+float(p['costs'][target])+.07*abs(rank-variant))
        values=updated;history.append(back)
    best=min(range(len(values)),key=lambda n:(values[n],n));path=[best]
    for back in reversed(history):best=back[best];path.append(best)
    for p,index in zip(pieces,reversed(path)):p['donor']=int(p['candidates'][index])
    return pieces

def infer(score,harmony,style,density,variant):
    import torch
    model,bank,manifest=runtime();pieces=choose_donors(score,harmony,style,density,variant,bank)
    rolls=[];chords=[];windows=[]
    for piece in pieces:
        donor=bank['rolls'][piece['donor']].astype(np.float32)
        first=next((b for b in piece['bars'] if b['root'] is not None),None)
        starts=np.flatnonzero(donor.sum(axis=1));bass=int(np.flatnonzero(donor[starts[0]])[0])%12 if len(starts) else 0
        shift=((first['root']-bass+6)%12-6) if first else 0
        donor=np.roll(donor,shift,axis=1)
        if shift>0:donor[:,:shift]=0
        elif shift<0:donor[:,shift:]=0
        target=np.zeros((16,36),np.float32)
        for i,bar in enumerate(piece['bars']):
            if bar['root'] is None:continue
            choice=next(c for c in harmony['choices'] if c['id']==bar['chordId'])
            target[i*4:(i+1)*4,bar['root']]=1
            target[i*4:(i+1)*4,12+np.array(choice['pitchClasses'])]=1
            target[i*4:(i+1)*4,24+bar['pitches'][0]%12]=1
        for offset in range(0,piece['length'],32):
            rolls.append(donor[offset:offset+32]);chords.append(target[offset//4:offset//4+8]);windows.append((piece,offset))
    output=[]
    for start in range(0,len(rolls),4):
        pr=torch.from_numpy(np.stack(rolls[start:start+4]));ch=torch.from_numpy(np.stack(chords[start:start+4]))
        with torch.inference_mode():result=model.inference(pr,ch,sample=False)
        output.extend(result)
    proposals=[];references=[];step=score['divisions']//4
    for result,(piece,offset) in zip(output,windows):
        for frame,notes in enumerate(result):
            if offset+frame>=piece['length']:break
            pitches=[];durations=[]
            for item in notes:
                pitch=int(item[0])
                if pitch==129:break
                if not 0<=pitch<=127:continue
                pitches.append(pitch);durations.append(int(''.join(map(str,map(int,item[1:]))),2)+1)
            if pitches:proposals.append({'tick':piece['left']+(offset+frame)*step,'pitches':pitches,'length':min(durations)*step})
    for p in pieces:
        song,phrase=map(int,bank['references'][p['donor']]);references.append({'firstMeasure':p['bars'][0]['number'],'bars':len(p['bars']),'donor':p['donor'],'sourceSongIndex':song,'sourcePhraseIndex':phrase})
    return proposals,references,manifest
