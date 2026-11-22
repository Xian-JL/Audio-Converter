"""Instrument performance events and reversible, polyphonic staff notation."""
import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET
from .score import tag, spell_pitch, timestamp, KEYS, validate_settings
from .meter_grid import make_grid, calibrated_grid
from .melody_score import DURATIONS, generate_melody_score


def checked_notes(notes, duration):
    if not isinstance(notes, list) or len(notes) > 20000:
        raise ValueError('Invalid performance notes (maximum 20000).')
    clean = []; ids = set()
    for n in notes:
        if not isinstance(n, dict): raise ValueError('Invalid performance note.')
        identity = n.get('id')
        if not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', identity) or identity in ids:
            raise ValueError('Invalid performance note identity.')
        values = [n.get(k) for k in ('start', 'end', 'midi')]
        if any(type(v) not in (int, float) or not math.isfinite(v) for v in values): raise ValueError('Invalid performance values.')
        start, end, midi = values
        if not 0 <= start < end <= duration + 1e-6 or not 0 <= midi <= 127 or midi != int(midi): raise ValueError('Performance note is outside the audio or pitch range.')
        item = {'id':identity, 'start':float(start), 'end':float(end), 'midi':int(midi), 'midiFloat':float(midi)}
        for key in ('velocity', 'confidence'):
            value = n.get(key)
            if value is not None:
                if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 1: raise ValueError('Invalid note strength.')
                item[key] = float(value)
        if n.get('staff') is not None:
            if type(n['staff']) != int or n['staff'] not in (1, 2): raise ValueError('Invalid staff.')
            item['staff'] = n['staff']
        bends = n.get('pitchBends', [])
        if not isinstance(bends, list) or len(bends) > 2000: raise ValueError('Invalid pitch trajectory.')
        if bends:
            previous = start - 1
            item['pitchBends'] = []
            for point in bends:
                if not isinstance(point, list) or len(point) != 2 or any(type(v) not in (int, float) or not math.isfinite(v) for v in point): raise ValueError('Invalid pitch trajectory.')
                at, cents = point
                if not start <= at <= end or at < previous or abs(cents) > 2400: raise ValueError('Invalid pitch trajectory bounds.')
                item['pitchBends'].append([float(at), float(cents)]); previous = at
        clean.append(item); ids.add(identity)
    return sorted(clean, key=lambda n:(n['start'], n['midi'], n['end'], n['id']))


def checked_controllers(controllers,duration):
    if not isinstance(controllers,list) or len(controllers)>20000:raise ValueError('Invalid pedal controllers.')
    clean=[]
    for c in controllers:
        if not isinstance(c,dict) or type(c.get('controller'))!=int or c['controller'] not in (64,66,67) or type(c.get('value'))!=int or not 0<=c['value']<=127:raise ValueError('Invalid pedal controller.')
        a,b=c.get('start'),c.get('end')
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in (a,b)) or not 0<=a<b<=duration:raise ValueError('Invalid pedal duration.')
        clean.append({'controller':c['controller'],'start':float(a),'end':float(b),'value':c['value']})
    return clean


def melody_candidate(notes):
    """A reviewable upper-line candidate. Never changes the original performance."""
    import bisect
    result=[];previous=None;at=-1.;starts=[n['start'] for n in notes];i=0
    while i<len(notes):
        if notes[i]['start']<at-1e-6:i+=1;continue
        right=bisect.bisect_left(starts,notes[i]['start']+.035);group=notes[i:right]
        best=max(group,key=lambda n:n['midi']-(.45*abs(n['midi']-previous) if previous is not None else 0)+2*n.get('confidence',.5))
        end=min(best['end'],starts[right]) if right<len(notes) else best['end']
        if end>best['start']:
            item={**best,'end':end,'staff':1}
            if item.get('pitchBends'):item['pitchBends']=[p for p in item['pitchBends'] if p[0]<=end]
            result.append(item);previous=best['midi'];at=end
        i=right
    return result



def generate(source, body):
    if body.get('downbeats')==[]:body={**body,'downbeats':None}
    bpm, meter, key = validate_settings(body.get('bpm'), body.get('meter'), body.get('key'))
    duration = source['duration']; raw = checked_notes(source['notes'], duration)
    controllers=checked_controllers(source.get('controllers',[]),duration)
    mode = body.get('scoreMode', 'performance')
    if mode not in ('performance', 'melody'): raise ValueError('Unknown instrument score mode.')
    notes = checked_notes(body['editedNotes'], duration) if body.get('editedNotes') is not None else raw
    if mode == 'melody' and body.get('editedNotes') is None: notes = melody_candidate(notes)
    if mode == 'melody':
        if any(a['end'] > b['start'] + 1e-6 for a,b in zip(notes, notes[1:])): raise ValueError('The melody branch must contain one non-overlapping line.')
        result = generate_melody_score({**source, 'notes':notes}, bpm, meter, key, body.get('anchorNoteId'), body.get('downbeats'))
        doc = ET.fromstring(result['xml'])
        for clef in doc.findall('.//clef/clef-octave-change'): doc.find('.//clef').remove(clef)
        doc.find('./work/work-title').text = 'Instrument melody'
        result['xml'] = '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(doc, encoding='unicode')
        by_id={n['id']:n for n in notes}
        for fragment in result['fragments']:fragment.update(staff=1,voice=1)
        for note in result['notes']:note.update(staff=1,voice=1)
        for event in result['events']:event['velocity']=by_id[event['id']].get('velocity',.75)
        result.update(melodyConfirmed=body.get('melodyConfirmed') is True,sourceKind=source['sourceKind'], scoreMode=mode, sourceNotes=raw, editedNotes=notes, engine=source['engine'], engineSignature=source.get('engineSignature'))
        return result
    divisions = 64
    points = body.get('downbeats')
    if points is None and body.get('anchorNoteId'):
        match = next((n for n in notes if n['id'] == body['anchorNoteId']), None)
        if match is None: raise ValueError('Select a note onset for the downbeat.')
        base = make_grid(bpm, meter, divisions)
        points = [{'noteId':match['id'], 'measure':max(1, int(base.tick(match['start']) // base.bar_ticks) + 1)}]
    anchors = []
    if points is not None:
        if not isinstance(points, list) or not 1 <= len(points) <= 5: raise ValueError('Choose 1–5 downbeat references.')
        for p in points:
            if not isinstance(p, dict) or type(p.get('measure')) != int or not 1 <= p['measure'] <= 4096: raise ValueError('Invalid downbeat measure.')
            n = next((n for n in notes if n['id'] == p.get('noteId')), None)
            if n is None: raise ValueError('Downbeat note is missing.')
            anchors.append({'noteId':n['id'], 'measure':p['measure'], 'time':n['start']})
        if any(a['time'] >= b['time'] or a['measure'] >= b['measure'] for a,b in zip(anchors, anchors[1:])): raise ValueError('Downbeat times and measures must increase.')
    grid = calibrated_grid(bpm,meter,divisions,anchors) if anchors else make_grid(bpm,meter,divisions)
    total = max(1, math.ceil(grid.tick(duration)))
    # Cluster into staves by register and continuity; preserve explicit user assignments.
    last_pitch = {1:72, 2:48}; written = []; previous_starts = {}
    for i,n in enumerate(notes):
        staff = n.get('staff')
        if staff is None:
            costs = {s:abs(n['midi']-last_pitch[s])*.3 + (max(0,60-n['midi']) if s==1 else max(0,n['midi']-60)) for s in (1,2)}
            staff = min(costs,key=costs.get)
        last_pitch[staff] = n['midi']
        start = max(0, min(total-1, round(grid.tick(n['start']))))
        previous = previous_starts.get((staff,n['midi']))
        if previous is not None and n['start'] > previous[0] and start <= previous[1]: start = previous[1]+1
        end = max(start+1, round(grid.tick(n['end'])))
        previous_starts[(staff,n['midi'])] = (n['start'],start)
        written.append({**n,'index':i+1,'staff':staff,'startTick':start,'endTick':end,'notatedStart':grid.time(start),'notatedEnd':grid.time(end)})
    total = max([total]+[n['endTick'] for n in written])
    groups = {}
    for n in written:
        # Equal-pitch events can share an onset and duration (e.g. two hands).
        # Give them separate voices so SVG mapping never overwrites an identity.
        bucket=0
        while any(x['midi']==n['midi'] for x in groups.get((n['staff'],n['startTick'],n['endTick'],bucket),[])):bucket+=1
        groups.setdefault((n['staff'],n['startTick'],n['endTick'],bucket),[]).append(n)
    voices = {}; ends = {}; next_voice = 1
    for (staff,start,end,_),group in sorted(groups.items()):
        free = next((v for v in voices if voices[v]['staff']==staff and ends[v]<=start), None)
        if free is None:
            if next_voice>64: raise ValueError('Too many overlapping voices. Shorten note tails or select a shorter recording.')
            free=next_voice;next_voice+=1;voices[free]={'staff':staff,'groups':[]}
        voices[free]['groups'].append((start,end,group));ends[free]=end
        for n in group:n['voice']=free
    for staff in (1,2):
        if not any(v['staff']==staff for v in voices.values()):voices[next_voice]={'staff':staff,'groups':[]};next_voice+=1
    root=ET.Element('score-partwise',version='4.0');tag(tag(root,'work'),'work-title', 'Piano performance' if source['sourceKind']=='piano' else 'Guzheng performance')
    tag(tag(tag(root,'part-list'),'score-part',id='P1'),'part-name','Piano' if source['sourceKind']=='piano' else 'Guzheng')
    part=tag(root,'part',id='P1');measures=[];fragments=[]
    durations=[(x*2,t,d) for x,t,d in DURATIONS]+[(1,'256th',False)]
    def emit(measure,start,end,voice,staff,group=None):
        at=start
        while at<end:
            length,kind,dotted=next(x for x in durations if x[0]<=end-at)
            for j,info in enumerate(group or [None]):
                node=tag(measure,'note',**({'id':info['id']+'-t'+str(at)} if info else {}))
                if j:tag(node,'chord')
                if info:
                    p=tag(node,'pitch');step,alter,octave=spell_pitch(info['midi'],KEYS[key]);tag(p,'step',step)
                    if alter:tag(p,'alter',alter)
                    tag(p,'octave',octave)
                else:tag(node,'rest')
                tag(node,'duration',length)
                stop=bool(info and at>info['startTick']);begin=bool(info and at+length<info['endTick'])
                if stop:tag(node,'tie',type='stop')
                if begin:tag(node,'tie',type='start')
                tag(node,'voice',voice);tag(node,'type',kind)
                if dotted:tag(node,'dot')
                tag(node,'staff',staff)
                if stop or begin:
                    notation=tag(node,'notations')
                    if stop:tag(notation,'tied',type='stop')
                    if begin:tag(notation,'tied',type='start')
                if info:fragments.append({'noteId':info['id'],'startTick':at,'endTick':at+length,'midi':info['midi'],'staff':staff,'voice':voice})
            at+=length
    if math.ceil(total/grid.bar_ticks)>4096:raise ValueError('The score exceeds 4096 measures. Use a shorter recording or adjust the tempo and downbeats.')
    for i,(left,right,pickup) in enumerate(grid.measures(total)):
        display=i if grid.pickup_ticks else i+1;measure=tag(part,'measure',number=display,**({'implicit':'yes'} if pickup else {}))
        if i==0:
            attributes=tag(measure,'attributes');tag(attributes,'divisions',divisions);signature=tag(attributes,'key');tag(signature,'fifths',KEYS[key]);tag(signature,'mode',key.split()[1])
            time=tag(attributes,'time');tag(time,'beats',meter.split('/')[0]);tag(time,'beat-type',meter.split('/')[1]);tag(attributes,'staves',2)
            for staff,sign,line in ((1,'G',2),(2,'F',4)):
                clef=tag(attributes,'clef',number=staff);tag(clef,'sign',sign);tag(clef,'line',line)
            direction=tag(measure,'direction');metronome=tag(tag(direction,'direction-type'),'metronome');tag(metronome,'beat-unit','quarter');tag(metronome,'per-minute',bpm);tag(direction,'sound',tempo=bpm)
        direction=tag(measure,'direction',placement='above');tag(tag(direction,'direction-type'),'words',f'{display} · {timestamp(grid.time(left))}')
        for j,(voice,v) in enumerate(voices.items()):
            if j:tag(tag(measure,'backup'),'duration',right-left)
            cursor=left
            for start,end,group in v['groups']:
                if start>=right or end<=left:continue
                a,b=max(left,start),min(right,end)
                if a>cursor:emit(measure,cursor,a,voice,v['staff'])
                emit(measure,a,b,voice,v['staff'],group);cursor=b
            if cursor<right:emit(measure,cursor,right,voice,v['staff'])
        measures.append({'number':i+1,'displayNumber':display,'pickup':pickup,'startTick':left,'endTick':right,'start':min(duration,max(0,grid.time(left))),'end':min(duration,max(0,grid.time(right))),'label':timestamp(grid.time(left)),'hasVocal':any(n['startTick']<right and n['endTick']>left for n in written)})
    identity={'sourceKind':source['sourceKind'],'baselineNotes':checked_notes(source['baselineNotes'],duration) if source.get('baselineNotes') is not None else None,'controllers':controllers,'source':source.get('sourceSha256'),'engine':source.get('engineSignature'),'notes':notes,'bpm':bpm,'meter':meter,'key':key,'downbeats':anchors,'notationVersion':'performance-v1'}
    fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True,allow_nan=False).encode()).hexdigest()
    base_fingerprint=hashlib.sha256(json.dumps({**identity,'downbeats':[]},sort_keys=True,allow_nan=False).encode()).hexdigest()
    events=[{'id':n['id'],'start':n['start'],'end':n['end'],'pitches':[n['midi']],'staff':n['staff'],'voice':n['voice'],'velocity':n.get('velocity',.75)} for n in written]
    result={'melodyConfirmed':False,'sourceKind':source['sourceKind'],'scoreMode':mode,'sourceNotes':raw,'engine':source['engine'],'engineSignature':source.get('engineSignature'),'sourceSha256':source.get('sourceSha256'),'scoreFingerprint':fingerprint,'baseFingerprint':base_fingerprint,'duration':duration,'notes':written,'events':events,'xml':'<?xml version="1.0" encoding="utf-8"?>\n'+ET.tostring(root,encoding='unicode'),'fragments':fragments,'measures':measures,'bpm':bpm,'meter':meter,'key':key,'divisions':divisions,'noteCount':len(notes),'chordCount':0,'downbeat':None,'downbeats':[],'grid':{'phaseSeconds':grid.phase,'pickupTicks':grid.pickup_ticks,'anchors':list(grid.anchors)}}
    result['sourceControllers']=controllers
    if source.get('baselineNotes') is not None:result['sourceBaselineNotes']=checked_notes(source['baselineNotes'],duration)
    if body.get('editedNotes') is not None:result['editedNotes']=notes
    if anchors:
        result['downbeats']=[{**p,'measureNumber':next(m['number'] for m in measures if m['startTick']==round(grid.tick(p['time'])))} for p in anchors]
        result['downbeat']={**result['downbeats'][0],'phaseSeconds':grid.phase}
    return result
