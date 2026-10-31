"""Block chords under the original melody; free piano only in approved empty sections."""
import copy
import hashlib
import json
import time
from .instrumental import selected_sections,profile
from .accompaniment import perform_model_notes
from .chord_score import engrave_block_chords

MODE='hybrid-v1'
EMOTION_MODE='hybrid-v2'


def compose_result(score,harmony,decoded,regions,seed,model,references,elapsed,emotion=None):
    # The existing quantization only creates notation; decoded seconds/pitches are retained.
    generated,notation,_,_=perform_model_notes(score,harmony,decoded,preserve_velocity=emotion is not None)
    events=[];written=[]
    for e,n in zip(harmony['events'],harmony['writtenChords']):
        # Preserve every planned block, including explicit user locks and anticipation
        # from the timing offset. A section boundary must never delete a vocal chord.
        events.append({**e,'voice':2,'role':'block'});written.append({**n,'voice':2,'role':'block'})
    endings={};tick_endings={};voice_staff={}
    for e,n in zip(generated,notation):
        owner=next((s for s in regions if s['start']<=e['start']<e['end']<=s['end']+1e-7),None)
        if owner is None or any(g['start']<e['end'] and g['end']>e['start'] for g in score['notes']):raise ValueError('Instrumental generation crossed the original melody.')
        # Equal-duration tones can span either hand. Voice IDs are unique within the part.
        for staff,pitches in ((1,[p for p in e['pitches'] if p>=60]),(2,[p for p in e['pitches'] if p<60])):
            if not pitches:continue
            voice=next(v for v in range(3,514) if voice_staff.get(v,staff)==staff and endings.get(v,0)<=e['start'] and tick_endings.get(v,0)<=n['startTick'])
            voice_staff[voice]=staff
            endings[voice]=e['end'];tick_endings[voice]=n['endTick'];identity=f"fill-{len(events)+1}"
            first=max(harmony['bars'][owner['firstMeasure']-1]['startTick'],n['startTick'])
            last=min(harmony['bars'][owner['lastMeasure']-1]['endTick'],n['endTick'])
            if last<=first:raise ValueError('Instrumental notation cannot fit this section.')
            events.append({**e,'id':identity,'pitches':pitches,'staff':staff,'voice':voice,'role':'instrumental'})
            written.append({**n,'id':identity,'pitches':pitches,'staff':staff,'voice':voice,'startTick':first,'endTick':last,'showChord':False,'role':'instrumental'})
    ordered=sorted(zip(events,written),key=lambda pair:(pair[0]['start'],pair[0]['voice'],pair[0]['id']))
    events=[e for e,_ in ordered];written=[n for _,n in ordered]
    xml,fragments=engrave_block_chords(score,written,harmony['choices'],'Melody, block chords and instrumental sections')
    settings={'mode':EMOTION_MODE if emotion is not None else MODE,'seed':seed,'sections':[{k:s[k] for k in ('firstMeasure','lastMeasure')} for s in regions]}
    if emotion is not None:
        from .emotional_score import checked
        settings['emotion']=checked(emotion)
    identity={'version':settings['mode'],'harmony':harmony['fingerprint'],'settings':settings,'events':events,'model':model}
    information=profile(score)
    if emotion is not None:
        information={**information,'emotion':settings['emotion'],'reference':'Neighboring GF phrase and explicit affect; EMO also conditions on the fixed key and boundary harmony.'}
    return {'sourceFingerprint':score['scoreFingerprint'],'harmonyFingerprint':harmony['fingerprint'],'fingerprint':hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest(),
            'settings':settings,'events':events,'writtenChords':written,'xml':xml,'chordFragments':fragments,'model':model,'references':references,'profile':information,'generationSeconds':round(elapsed,3)}


def generate(score,harmony,seed=0,on_progress=None,provided=None,emotion=None):
    if harmony.get('policy')!='adaptive-block-v1':raise ValueError('Generate melody-led block chords before composing instrumental sections.')
    if score['meter']!='4/4':raise ValueError('Instrumental generation currently supports 4/4. Block chords support the other meters.')
    if type(seed)!=int or not 0<=seed<=0xffffffff:raise ValueError('Invalid instrumental seed.')
    regions=selected_sections(score,harmony,provided)
    if not regions:raise ValueError('No instrumental section has two complete melody-free measures.')
    started=time.perf_counter()
    if emotion is None:
        from .amt_model import infer_instrumental
        decoded,references,model=infer_instrumental(score,harmony,regions,seed,on_progress)
    else:
        from .emotional_score import infer
        decoded,references,model=infer(score,harmony,regions,seed,emotion,on_progress)
    if not decoded:raise ValueError('No playable instrumental notes were generated. Retry this section.')
    if on_progress:on_progress({'stage':'engraving','progress':.98})
    return compose_result(score,harmony,decoded,regions,seed,model,references,time.perf_counter()-started,emotion)


def restore(item,score,harmony):
    """Validate data and reconstruct both staves; reopening never invokes a model."""
    settings=item.get('settings',{})
    required={'mode','seed','sections','emotion'} if settings.get('mode')==EMOTION_MODE else {'mode','seed','sections'}
    if set(settings)!=required or settings.get('mode') not in (MODE,EMOTION_MODE) or type(settings.get('seed'))!=int or not 0<=settings['seed']<=0xffffffff:raise ValueError('Invalid instrumental settings.')
    if settings['mode']==EMOTION_MODE:
        from .emotional_score import checked
        if not isinstance(settings['emotion'],dict):raise ValueError('Saved instrumental emotion settings are missing.')
        checked(settings['emotion'])
    regions=selected_sections(score,harmony,settings['sections']);events=item.get('events');written=item.get('writtenChords')
    if not isinstance(events,list) or not isinstance(written,list) or len(events)!=len(written) or len(events)>20000:raise ValueError('Invalid instrumental events.')
    # Keep exact stored values; validate the same timing and lane rules as legacy events.
    from .project import number
    ids=set();ends={};ticks={};voice_staff={};clean=[];engraving=[];blocks={e['id']:(e,n) for e,n in zip(harmony['events'],harmony['writtenChords'])}
    import re
    for e,n in zip(events,written):
        if not isinstance(e,dict) or not isinstance(n,dict):raise ValueError('Invalid instrumental note.')
        identity=e.get('id');staff=e.get('staff');voice=e.get('voice');pitches=e.get('pitches');role=e.get('role')
        if not isinstance(identity,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',identity) or identity in ids or type(staff)!=int or staff not in (1,2) or type(voice)!=int or not 2<=voice<=513:raise ValueError('Invalid instrumental lane.')
        start=number(e.get('start'),0,score['duration']);end=number(e.get('end'),start,score['duration']);velocity=number(e.get('velocity'),0,1)
        a=number(n.get('startTick'),0,score['measures'][-1]['endTick']);b=number(n.get('endTick'),a,score['measures'][-1]['endTick'])
        if start>=end or a>=b or a!=int(a) or b!=int(b) or start<ends.get(voice,0)-1e-7 or a<ticks.get(voice,0):raise ValueError('Overlapping instrumental lane.')
        if voice_staff.get(voice,staff)!=staff:raise ValueError('An instrumental lane cannot change staves.')
        voice_staff[voice]=staff
        if not isinstance(pitches,list) or not 1<=len(pitches)<=128 or any(type(p)!=int or not 0<=p<=127 for p in pitches):raise ValueError('Invalid instrumental pitches.')
        if any(n.get(k)!=e.get(k) for k in ('id','pitches','staff','voice','role')):raise ValueError('Instrumental notation does not match its events.')
        if role=='block':
            expected=blocks.pop(identity,None)
            if expected is None or any(e.get(k)!=expected[0].get(k) for k in ('start','end','pitches','staff','velocity')) or voice!=2 or any(n.get(k)!=expected[1].get(k) for k in ('startTick','endTick','chordId')):raise ValueError('Saved block chords have changed.')
        elif role=='instrumental':
            owner=next((s for s in regions if s['start']<=start<end<=s['end']+1e-7),None)
            if voice<3 or owner is None or n.get('showChord') is not False or n.get('chordId') not in {c['id'] for c in harmony['choices']}:raise ValueError('Instrumental note is outside its section.')
            if any(g['start']<end and g['end']>start for g in score['notes']) or not harmony['bars'][owner['firstMeasure']-1]['startTick']<=a<b<=harmony['bars'][owner['lastMeasure']-1]['endTick']:raise ValueError('Instrumental note overlaps the original melody.')
        else:raise ValueError('Invalid instrumental role.')
        ids.add(identity);ends[voice]=end;ticks[voice]=b;clean.append(copy.deepcopy(e));engraving.append(copy.deepcopy(n))
    if blocks:raise ValueError('Saved arrangement is missing block chords.')
    if not any(e['role']=='instrumental' for e in clean):raise ValueError('Saved arrangement has no instrumental melody.')
    xml,fragments=engrave_block_chords(score,engraving,harmony['choices'],'Melody, block chords and instrumental sections')
    return {**{k:item.get(k) for k in ('sourceFingerprint','harmonyFingerprint','fingerprint','model','references','generationSeconds','profile')},'settings':copy.deepcopy(settings),'events':clean,'writtenChords':engraving,'xml':xml,'chordFragments':fragments}
