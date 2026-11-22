"""Local CPU transcription adapters. Official models and note decoders are pinned."""
from pathlib import Path
import hashlib
import importlib
import importlib.util
import json
import sys
import types

ROOT=Path(__file__).resolve().parents[1]
DIRECTORY=ROOT/'models/instrument-transcription'


def available(kind):
    engine={'piano':'transkun','guzheng':'basic-pitch'}.get(kind)
    if engine is None:return False
    try:
        manifest=json.loads((ROOT/'models/instrument-models-manifest.json').read_text(encoding='utf-8'))
        files=manifest[engine]['files']
        modules=('torch','torchaudio','moduleconf','ncls','mir_eval') if engine=='transkun' else ('onnxruntime','mir_eval','resampy')
        return all(importlib.util.find_spec(m) is not None for m in modules) and all((ROOT/name).is_file() and (ROOT/name).stat().st_size==entry['bytes'] for name,entry in files.items())
    except (OSError,ValueError,KeyError):return False


def verify(engine):
    manifest=json.loads((ROOT/'models/instrument-models-manifest.json').read_text(encoding='utf-8'))[engine]
    for name,entry in manifest['files'].items():
        path=ROOT/name
        with path.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
        if sha!=entry['sha256']:raise ValueError('Instrument resource checksum mismatch: '+name)
    return {'version':engine+'-cpu-v1','files':{name:entry['sha256'] for name,entry in manifest['files'].items()}}


def basic_pitch(path,progress=lambda _:None,capture=None):
    import numpy as np
    import librosa
    import onnxruntime as ort
    # Load only the official constants and note decoder, without its TensorFlow installer/runtime.
    package=types.ModuleType('basic_pitch');package.__path__=[str(ROOT/'vendor/basic-pitch/basic_pitch')]
    sys.modules.setdefault('basic_pitch',package)
    decoder=importlib.import_module('basic_pitch.note_creation')
    from basic_pitch.constants import AUDIO_N_SAMPLES,FFT_HOP,ANNOTATIONS_FPS
    signature=verify('basic-pitch')
    session_options=ort.SessionOptions();session_options.intra_op_num_threads=4
    model=ort.InferenceSession(str(DIRECTORY/'basic-pitch.onnx'),sess_options=session_options,providers=['CPUExecutionProvider'])
    wave,sr=librosa.load(str(path),sr=22050,mono=True);duration=len(wave)/sr
    overlap=30*FFT_HOP;hop=AUDIO_N_SAMPLES-overlap
    padded=np.concatenate([np.zeros(overlap//2,np.float32),wave]);outputs={k:[] for k in ('note','onset','contour')}
    starts=range(0,len(padded),hop)
    for i,start in enumerate(starts):
        window=np.pad(padded[start:start+AUDIO_N_SAMPLES],(0,max(0,AUDIO_N_SAMPLES-len(padded[start:start+AUDIO_N_SAMPLES]))))
        values=model.run(['StatefulPartitionedCall:1','StatefulPartitionedCall:2','StatefulPartitionedCall:0'],{'serving_default_input_2:0':window.astype(np.float32)[None,:,None]})
        for k,v in zip(outputs,values):outputs[k].append(v[:,15:-15,:])
        progress((i+1)/len(starts)*.9)
    # Exact official overlap removal and frame count, including its frame-to-time correction.
    frame_count=int(len(wave)/hop*(2*ANNOTATIONS_FPS-30))
    output={k:np.concatenate(v,axis=0).reshape(-1,v[0].shape[-1])[:frame_count] for k,v in outputs.items()}
    if capture is not None:capture(output,decoder)
    def decode(min_len,prefix,onset=.5,melodia=True):
        _,events=decoder.model_output_to_notes(output,onset_thresh=onset,frame_thresh=.3,min_note_len=min_len,multiple_pitch_bends=True,melodia_trick=melodia)
        result=[]
        for i,(start,end,pitch,strength,bends) in enumerate(events):
            start=max(0,float(start));end=min(duration,float(end))
            if start>=end:continue
            n={'id':prefix+f'{i+1:06d}','start':start,'end':end,'midi':int(pitch),'midiFloat':float(pitch),'velocity':float(np.clip(strength,0,1))}
            if bends is not None and len(bends)>1:
                stride=max(1,int(np.ceil(len(bends)/256)))
                n['pitchBends']=[[float(start+(end-start)*j/(len(bends)-1)),float(bends[j])*100/3] for j in range(0,len(bends),stride)]
            result.append(n)
        return result
    baseline=decode(11,'bpbase-');notes=decode(3,'bp-',.6,False)
    progress(1.)
    return {'duration':duration,'notes':notes,'engine':'basic-pitch','engineSignature':signature,'baselineNotes':baseline,'decoder':'guzheng-onset-v1','previewFeatures':'fixed-pitch; model salience controls preview strength; bends retained in project'}


def piano(path,progress=lambda _:None):
    import torch
    import soundfile as sf
    import soxr
    signature=verify('transkun');torch.set_num_threads(4)
    vendor=str(ROOT/'vendor/transkun')
    if vendor not in sys.path:sys.path.insert(0,vendor)
    import moduleconf
    configuration=moduleconf.parseFromFile(str(DIRECTORY/'transkun-2.0.conf'))['Model']
    model=configuration.module.TransKun(conf=configuration.config).to('cpu')
    checkpoint=torch.load(DIRECTORY/'transkun-2.0.pt',map_location='cpu',weights_only=True)
    model.load_state_dict(checkpoint.get('best_state_dict',checkpoint.get('state_dict')),strict=True);model.eval()
    wave,rate=sf.read(path,dtype='float32',always_2d=True);duration=len(wave)/rate
    if rate!=model.fs:wave=soxr.resample(wave,rate,model.fs)
    progress(.05)
    with torch.inference_mode():decoded=model.transcribe(torch.from_numpy(wave),discardSecondHalf=False)
    notes=[];controllers=[]
    for i,n in enumerate(decoded):
        if n.pitch in (-64,-66,-67):
            start=max(0.,float(n.start));end=min(duration,float(n.end))
            if start<end:controllers.append({'controller':-int(n.pitch),'start':start,'end':end,'value':max(0,min(127,int(n.velocity)))})
        if not 0<=n.pitch<=127:continue # Pedal controller pseudo-notes are not pitched events.
        start=max(0,float(n.start));end=min(duration,float(n.end))
        if start<end:notes.append({'id':f'tk-{i+1:06d}','start':start,'end':end,'midi':int(n.pitch),'midiFloat':float(n.pitch),'velocity':max(0.,min(1.,float(n.velocity)/127))})
    progress(1.)
    return {'duration':duration,'notes':notes,'engine':'transkun','engineSignature':signature,'controllers':controllers,'decoder':'official-transkun-2.0.1','previewFeatures':'key notes; sustain controllers not yet rendered'}


def transcribe(path,kind,progress=lambda _:None):
    if not available(kind):raise ValueError('Instrument model is not ready. Run SetupInstrument.cmd.')
    from .performance_score import checked_notes
    result=piano(path,progress) if kind=='piano' else basic_pitch(path,progress)
    result['notes']=checked_notes(result['notes'],result['duration'])
    return result
