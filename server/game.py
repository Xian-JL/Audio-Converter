"""Local GAME 1.0.3 CPU driver. No training dependencies or runtime downloads.

Model interfaces: openvpi/GAME (MIT); see GAME-LICENSE.txt.
"""
from pathlib import Path
import hashlib
import json
import time
import numpy as np
import onnxruntime as ort

ROOT=Path(__file__).resolve().parents[1]
VERSION='game-1.0.3-gf-v1'
FILES=('encoder','segmenter','estimator','dur2bd','bd2dur')

def model_directory():
    for directory in (ROOT/'models/game-small',):
        if (directory/'config.json').is_file() and all((directory/f'{name}.onnx').is_file() for name in FILES): return directory
    raise RuntimeError('GAME model is missing. Run setup-game.ps1 first.')

def signature():
    directory=model_directory()
    return {'version':VERSION,'files':{name:hashlib.sha256((directory/name).read_bytes()).hexdigest() for name in ('config.json',*[f'{part}.onnx' for part in FILES])}}

def run(session,**inputs):
    return dict(zip([out.name for out in session.get_outputs()],session.run(None,inputs)))

class GameTranscriber:
    def __init__(self):
        directory=model_directory();self.signature=signature()
        self.config=json.loads((directory/'config.json').read_text())
        ort.set_seed(20261018)
        options=ort.SessionOptions();options.intra_op_num_threads=4;options.inter_op_num_threads=1
        self.sessions={name:ort.InferenceSession(str(directory/f'{name}.onnx'),sess_options=options,providers=['CPUExecutionProvider']) for name in FILES}

    def transcribe(self,wave,rate,progress=lambda value:None):
        config=self.config;sessions=self.sessions
        wave=np.asarray(wave,dtype=np.float32)
        if wave.ndim==2:wave=wave.mean(axis=1)
        if wave.ndim!=1 or not len(wave) or not np.isfinite(wave).all():raise ValueError('Invalid audio waveform.')
        if rate!=config['samplerate']:raise ValueError('GAME requires decoded 44100 Hz audio.')
        duration=len(wave)/rate
        regions=[];chunks=[];started=time.perf_counter();seam_joins=[]
        for core_start in np.arange(0,duration,12.):
            core_start=float(core_start);core_end=min(duration,core_start+12)
            context_start=max(0,core_start-2);context_end=min(duration,core_end+2)
            clip=wave[round(context_start*rate):round(context_end*rate)][None,:]
            dur=np.array([clip.shape[1]/rate],dtype=np.float32)
            encoded=run(sessions['encoder'],waveform=clip,duration=dur)
            known=run(sessions['dur2bd'],durations=dur[:,None],maskT=encoded['maskT'])['boundaries'];assert not known.any()
            boundaries=known.copy();counts=[]
            for step in range(8):
                boundaries=run(sessions['segmenter'],x_seg=encoded['x_seg'],language=np.array([config['languages']['zh']],dtype=np.int64),
                               known_boundaries=known,prev_boundaries=boundaries,t=np.array([step/8],dtype=np.float32),maskT=encoded['maskT'],
                               threshold=np.array(.2,dtype=np.float32),radius=np.array(2,dtype=np.int64))['boundaries']
                counts.append(int(boundaries.sum()))
            segmented=run(sessions['bd2dur'],boundaries=boundaries,maskT=encoded['maskT'])
            estimated=run(sessions['estimator'],x_est=encoded['x_est'],boundaries=boundaries,maskT=encoded['maskT'],maskN=segmented['maskN'],threshold=np.array(.2,dtype=np.float32))
            cursor=0.;chunk_index=len(chunks)
            for length,valid,present,pitch in zip(segmented['durations'][0],segmented['maskN'][0],estimated['presence'][0],estimated['scores'][0]):
                if not valid:continue
                assert length>0 and np.isfinite(pitch)
                raw_start=context_start+cursor;raw_end=raw_start+float(length);cursor+=float(length)
                left=max(raw_start,core_start);right=min(raw_end,core_end)
                if right-left<1e-6:continue
                current={'start':round(left,6),'end':round(right,6),'present':bool(present),'midiFloat':float(pitch),'midi':int(round(float(pitch))),
                         'originalRegionStart':round(raw_start,6),'originalRegionEnd':round(raw_end,6),'chunkIndex':chunk_index}
                if regions and abs(left-core_start)<1e-5 and core_start>0:
                    previous=regions[-1]
                    continuous=(abs(previous['end']-core_start)<1e-5 and previous['present']==current['present']
                                and previous['originalRegionEnd']>core_start+.02 and current['originalRegionStart']<core_start-.02)
                    same_pitch=(not present or (previous['midi']==current['midi'] and abs(previous['midiFloat']-current['midiFloat'])<=.5))
                    if continuous and same_pitch:
                        seam_joins.append({'seam':core_start,'leftChunk':previous['chunkIndex'],'rightChunk':chunk_index,'midi':current['midi'] if present else None})
                        previous['end']=current['end'];previous['originalRegionEnd']=current['originalRegionEnd'];continue
                regions.append(current)
            assert abs(cursor-round(float(dur[0])/.01)*.01)<.011
            chunks.append({'core':[core_start,core_end],'context':[context_start,context_end],'boundaryCounts':counts})
            progress(core_end/duration)
        notes=[{'id':f'gf-{index+1:06d}','start':region['start'],'end':region['end'],'midi':region['midi'],'midiFloat':region['midiFloat']} for index,region in enumerate(r for r in regions if r['present'])]
        assert all(0<=n['start']<n['end']<=duration and 0<=n['midi']<=127 for n in notes)
        assert all(a['end']<=b['start']+1e-6 for a,b in zip(notes,notes[1:]))
        return {'notes':notes,'regions':regions,'duration':duration,'engine':'game','engineSignature':self.signature,
                'chunks':chunks,'seamJoins':seam_joins,'transcriptionSeconds':round(time.perf_counter()-started,3)}
