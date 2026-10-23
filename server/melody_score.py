"""Single right-hand staff, preserving GF logical notes and review identities.

Notation uses a 32nd grid with 128th fallback to retain close attacks. Original
GF timing is retained separately for listening; neither representation drops notes.
"""
import hashlib
import json
import math
import xml.etree.ElementTree as ET
from .score import validate_settings, tag, spell_pitch, timestamp, KEYS
from .meter_grid import make_grid

DIVISIONS=32
DURATIONS=[(128,'whole',False),(96,'half',True),(64,'half',False),(48,'quarter',True),(32,'quarter',False),
           (24,'eighth',True),(16,'eighth',False),(12,'16th',True),(8,'16th',False),(6,'32nd',True),(4,'32nd',False),
           (3,'64th',True),(2,'64th',False),(1,'128th',False)]


def generate_melody_score(result,bpm,meter,key,anchor_note_id=None):
    bpm,meter,key=validate_settings(bpm,meter,key)
    duration=float(result['duration'])
    if not math.isfinite(duration) or duration<=0:raise ValueError('Audio duration must be positive.')
    raw=result.get('notes',[])
    last_end=0.
    for n in raw:
        if not all(math.isfinite(float(n[k])) for k in ('start','end','midi')) or not 0<=n['start']<n['end']<=duration+1e-5 or n['start']<last_end-1e-5 or not 0<=n['midi']<=127:
            raise ValueError('Invalid GF note sequence.')
        last_end=n['end']
    anchor_index=None
    if anchor_note_id is not None:
        ids={f'gf-{i+1:06d}':i for i in range(len(raw))}
        if not isinstance(anchor_note_id,str) or anchor_note_id not in ids:raise ValueError('Please select a melody note onset as the downbeat.')
        anchor_index=ids[anchor_note_id]
    anchor_time=raw[anchor_index]['start'] if anchor_index is not None else None
    divisions=DIVISIONS
    while True:
        grid=make_grid(bpm,meter,divisions,anchor_time)
        total_ticks=max(len(raw),1,math.ceil(grid.tick(duration)-1e-8))
        anchor_tick=round(grid.tick(anchor_time)) if anchor_time is not None else None
        enough=len(raw)<=math.ceil(grid.tick(duration)-1e-8)
        if anchor_index is not None:enough=enough and anchor_index<=anchor_tick and len(raw)-anchor_index<=total_ticks-anchor_tick
        if enough:break
        if divisions==64:raise ValueError('Too many notes for this notation resolution.')
        divisions=64
    duration_types=DURATIONS if divisions==DIVISIONS else [(n*2,kind,dotted) for n,kind,dotted in DURATIONS]+[(1,'256th',False)]
    starts=[]
    for i,n in enumerate(raw):
        preferred=grid.snap(n['start'])
        ceiling=total_ticks-(len(raw)-i)
        if anchor_index is not None and i<anchor_index:ceiling=min(ceiling,anchor_tick-(anchor_index-i))
        start=anchor_tick if i==anchor_index else min(ceiling,max(starts[-1]+1 if starts else 0,preferred))
        starts.append(start)
    notes=[];events=[];notated=[]
    for i,n in enumerate(raw):
        start=starts[i];end=min(starts[i+1] if i+1<len(raw) else total_ticks,max(start+1,grid.snap(n['end'])))
        note_id=f'gf-{i+1:06d}'
        info={'id':note_id,'index':i+1,'midi':int(round(n['midi'])),'midiFloat':n.get('midiFloat',float(n['midi'])),
              'start':n['start'],'end':n['end'],'startTick':start,'endTick':end,
              'notatedStart':round(grid.time(start),6),'notatedEnd':round(min(duration,grid.time(end)),6)}
        notes.append(info)
        events.append({'id':note_id,'start':n['start'],'end':n['end'],'pitches':[info['midi']],'staff':1})
        notated.append({'id':note_id,'start':info['notatedStart'],'end':info['notatedEnd'],'pitches':[info['midi']],'staff':1})
    if any(e['end']<=e['start'] for e in notated):raise ValueError('Unable to represent these note boundaries at the provided BPM.')
    root=ET.Element('score-partwise',version='4.0');tag(tag(root,'work'),'work-title','GF vocal melody · right hand')
    part_list=tag(root,'part-list');tag(tag(part_list,'score-part',id='P1'),'part-name','Melody')
    part=tag(root,'part',id='P1');measures=[];fragments=[];fifths=KEYS[key]
    def emit(measure,left,right,info=None,visible=True):
        at=left
        while at<right:
            length,kind,dotted=next(item for item in duration_types if item[0]<=right-at)
            attrs={} if info or visible else {'print-object':'no','print-spacing':'yes'}
            if info:attrs['id']=f"{info['id']}-t{at}"
            node=tag(measure,'note',**attrs)
            if info:
                pitch=tag(node,'pitch');step,alter,octave=spell_pitch(info['midi'],fifths);tag(pitch,'step',step)
                if alter:tag(pitch,'alter',alter)
                tag(pitch,'octave',octave)
            else:tag(node,'rest')
            tag(node,'duration',length)
            stop=bool(info and at>info['startTick']);start=bool(info and at+length<info['endTick'])
            if stop:tag(node,'tie',type='stop')
            if start:tag(node,'tie',type='start')
            tag(node,'voice',1);tag(node,'type',kind)
            if dotted:tag(node,'dot')
            tag(node,'staff',1)
            if stop or start:
                nt=tag(node,'notations')
                if stop:tag(nt,'tied',type='stop')
                if start:tag(nt,'tied',type='start')
            if info:fragments.append({'noteId':info['id'],'startTick':at,'endTick':at+length,'midi':info['midi']})
            at+=length
    for i,(left,right,pickup) in enumerate(grid.measures(total_ticks)):
        present=[n for n in notes if n['startTick']<right and n['endTick']>left]
        display_number=i if grid.pickup_ticks else i+1
        measure=tag(part,'measure',number=display_number,**({'implicit':'yes'} if pickup else {}))
        if i==0:
            attributes=tag(measure,'attributes');tag(attributes,'divisions',divisions)
            signature=tag(attributes,'key');tag(signature,'fifths',fifths);tag(signature,'mode',key.split()[1])
            time=tag(attributes,'time');tag(time,'beats',meter.split('/')[0]);tag(time,'beat-type',meter.split('/')[1])
            tag(attributes,'staves',1);clef=tag(attributes,'clef');tag(clef,'sign','G');tag(clef,'line',2)
            tag(clef,'clef-octave-change',-1)
            direction=tag(measure,'direction',placement='above');metronome=tag(tag(direction,'direction-type'),'metronome');tag(metronome,'beat-unit','quarter');tag(metronome,'per-minute',bpm);tag(direction,'sound',tempo=bpm)
        direction=tag(measure,'direction',placement='above');tag(tag(direction,'direction-type'),'words',f'{display_number} · {timestamp(grid.time(left))}')
        cursor=left
        for n in present:
            a=max(left,n['startTick']);b=min(right,n['endTick'])
            if a>cursor:emit(measure,cursor,a,visible=bool(present))
            emit(measure,a,b,n);cursor=b
        if cursor<right:emit(measure,cursor,right,visible=bool(present))
        measures.append({'number':i+1,'displayNumber':display_number,'pickup':pickup,'metricalStart':round(grid.phase-grid.bar_ticks*grid.seconds_per_tick if pickup else grid.time(left),6),'startTick':left,'endTick':right,'start':round(grid.time(left),6),'end':round(min(duration,grid.time(right)),6),'label':timestamp(grid.time(left)),'hasVocal':bool(present)})
    xml='<?xml version="1.0" encoding="utf-8"?>\n'+ET.tostring(root,encoding='unicode')
    # Clef presentation does not change logical notes, timings or existing review IDs.
    identity={'source':result.get('sourceSha256'),'engine':result.get('engineSignature'), 'notes':raw,'bpm':bpm,'meter':meter,'key':key,'notationVersion':'right-adaptive-v1'}
    base_fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True,allow_nan=False).encode()).hexdigest()
    if anchor_note_id is not None:identity={**identity,'notationVersion':'right-downbeat-v1','anchorNoteId':anchor_note_id,'phase':grid.phase}
    fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True,allow_nan=False).encode()).hexdigest()
    return {'xml':xml,'bpm':bpm,'meter':meter,'key':key,'duration':duration,'noteCount':len(notes),'chordCount':0,'melodyOnly':True,
            'engine':'game','engineSignature':result.get('engineSignature'),'sourceSha256':result.get('sourceSha256'),'scoreFingerprint':fingerprint,
            'notes':notes,'events':events,'notatedEvents':notated,'fragments':fragments,'divisions':divisions,'measures':measures,
            'baseFingerprint':base_fingerprint,'grid':{'phaseSeconds':grid.phase,'pickupTicks':grid.pickup_ticks},
            'downbeat':None if anchor_note_id is None else {'noteId':anchor_note_id,'time':anchor_time,'phaseSeconds':grid.phase,'measureNumber':next(m['number'] for m in measures if m['startTick']==anchor_tick)},
            'maxNotationShiftMs':round(max([abs(n['notatedStart']-n['start'])*1000 for n in notes]+[0]),2)}
