"""Melody-led block harmony with variable harmonic rhythm; no generative model."""
import hashlib
import json
import math
from .arrangement import INTERVALS, TONICS
from .basic_harmony import (palette as legacy_palette, resources, RESOURCE, root_name,
                            corpus_prior, phrase_starts, melody_cost, connection, voicing)
from .score import KEYS
from .harmony_timing import align_harmony
from .chord_score import engrave_block_chords

POLICY='adaptive-block-v1'


def palette(key):
    result=legacy_palette(key)[:-1];mode=key.split()[1];fifths=KEYS[key]
    qualities=('maj7','min7','min7','maj7','7','min7','half-dim7') if mode=='major' else ('min7','half-dim7','maj7','min7','min7','maj7','7')
    suffix={'maj7':'maj7','min7':'m7','7':'7','half-dim7':'m7b5','dim7':'dim7'}
    additions=[]
    for base,quality in zip(result[:7],qualities):
        additions.append({**base,'id':f"{base['degree']}:{quality}",'quality':quality,'roman':base['roman'].replace('°','ø')+'7'})
    tonic=TONICS[key.split()[0]]
    additions.append({'id':'7h:dim7','degree':7,'root':(tonic+11)%12,'quality':'dim7','roman':'vii°7'})
    for chord in additions:
        if any(c['id']==chord['id'] for c in result):continue
        chord['pitchClasses']=[(chord['root']+n)%12 for n in INTERVALS[chord['quality']]]
        chord['name']=root_name(chord['root'],fifths)+suffix[chord['quality']]
        chord['tones']=[root_name(pc,fifths) for pc in chord['pitchClasses']]
        result.append(chord)
    return result+[legacy_palette(key)[-1]]


def generate(score,locks=None,phrases=None,chord_offset_ms=0,segment_locks=None):
    if not score.get('notes'):raise ValueError('No melody notes are available for harmony.')
    if len(score['measures'])>4096:raise ValueError('This score is too long for harmony.')
    choices=palette(score['key']);by_id={c['id']:c for c in choices};bars=score['measures'];divisions=score['divisions']
    locks={} if locks is None else locks;segment_locks={} if segment_locks is None else segment_locks
    if not isinstance(locks,dict) or any(not isinstance(k,str) or not k.isdigit() or str(int(k))!=k or not 1<=int(k)<=len(bars) or not isinstance(v,str) or v not in by_id for k,v in locks.items()):raise ValueError('Invalid locked chord.')
    if not isinstance(segment_locks,dict) or len(segment_locks)>16384:raise ValueError('Invalid locked chord segment.')
    numerator,denominator=map(int,score['meter'].split('/'))
    beat=divisions*4//denominator*(3 if denominator==8 and numerator%3==0 else 1)
    boundaries=set();fixed={};protected=set()
    for bar in bars:
        left,right=bar['startTick'],bar['endTick']
        boundaries.update((bar['number'],t) for t in range(left,right,beat));boundaries.add((bar['number'],right))
    for key,chord in segment_locks.items():
        try:
            number,left,right=map(int,key.split(':'))
            valid=key==f'{number}:{left}:{right}' and 1<=number<=len(bars) and (number,left) in boundaries and (number,right) in boundaries and left<right and isinstance(chord,str) and chord in by_id
        except (ValueError,AttributeError):valid=False
        if not valid:raise ValueError('Invalid locked chord segment.')
        protected.update(((number,left),(number,right)))
        for tick in range(left,right,beat):
            if (number,tick) in fixed and fixed[number,tick]!=chord:raise ValueError('Conflicting locked chord segments.')
            if str(number) in locks and locks[str(number)]!=chord:raise ValueError('Conflicting locked chord segments.')
            fixed[number,tick]=chord
    starts=phrase_starts(score,phrases);transitions,_=corpus_prior(score['key'].split()[1])
    notes=[{**n,'start':n['notatedStart'],'end':n['notatedEnd'],'calibratedBeat':n['startTick']/divisions} for n in score['notes']]
    units=[];emissions=[];conflicts=[]
    from .meter_grid import score_grid
    grid=score_grid(score)
    for bar in bars:
        for left in range(bar['startTick'],bar['endTick'],beat):
            right=min(bar['endTick'],left+beat)
            unit={**bar,'startTick':left,'endTick':right,'start':bar['start'] if left==bar['startTick'] else round(grid.time(left),6),'end':bar['end'] if right==bar['endTick'] else round(grid.time(right),6),'quarterDivisions':divisions}
            row=[];bad=[];locked=fixed.get((bar['number'],left),locks.get(str(bar['number'])))
            for c in choices:
                cost,conflict=melody_cost(c,unit,notes,score['bpm'],score['key'])
                # More tones need an audible melodic reason; seventh chords are not a free win.
                if len(c['pitchClasses'])==4:cost+=.10 if c['quality']!='dim7' else .17
                if c['quality']=='dim':cost+=.035
                if locked is not None and c['id']!=locked:cost=math.inf
                if locked is None and bool(bar['hasVocal'])==(c['id']=='none'):cost=math.inf
                row.append(cost*(right-left)/divisions);bad.append(conflict)
            units.append(unit);emissions.append(row);conflicts.append(bad)
    links=[[connection(a,b,transitions) for b in choices] for a in choices]
    values=emissions[0][:];history=[]
    for i,row in enumerate(emissions[1:],1):
        unit=units[i];internal=unit['number']==units[i-1]['number'];forced=(unit['number'],unit['startTick']) in protected
        has_onset=any(unit['startTick']<=n['startTick']<unit['endTick'] for n in notes)
        updated=[];back=[]
        for j,c in enumerate(choices):
            costs=[]
            for k,previous in enumerate(choices):
                changed=previous['id']!=c['id']
                extra=(.48 if internal else .16) if changed else 0.
                if internal and changed and not has_onset and not forced and str(unit['number']) not in locks:extra=math.inf
                costs.append(values[k]+links[k][j]+extra)
            winner=min(range(len(choices)),key=lambda k:(costs[k],k));back.append(winner);updated.append(costs[winner]+row[j])
        history.append(back);values=updated
    winner=min(range(len(choices)),key=lambda k:(values[k],k))
    if not math.isfinite(values[winner]):raise ValueError('Locked chords cannot be represented on this grid.')
    path=[winner]
    for back in reversed(history):winner=back[winner];path.append(winner)
    path.reverse();segments=[];previous=[]
    for i,(unit,index) in enumerate(zip(units,path)):
        c=choices[index];number=unit['number'];left=unit['startTick'];locked=(number,left) in fixed or str(number) in locks
        if segments and segments[-1]['number']==number and segments[-1]['chordId']==c['id'] and (number,left) not in protected and segments[-1]['locked']==locked:
            segments[-1].update(endTick=unit['endTick'],end=unit['end']);continue
        pitches=voicing(c,previous)
        if pitches:previous=pitches
        alternatives=sorted(range(len(choices)),key=lambda j:(emissions[i][j],j))[:4]
        segments.append({**unit,'chordId':c['id'],'name':c['name'],'roman':c['roman'],'tones':c['tones'],'root':c['root'],'quality':c['quality'],'pitches':pitches,
                         'locked':locked,'phraseStart':number in starts and left==bars[number-1]['startTick'],'needsReview':conflicts[i][index]>.35,'alternatives':[choices[j]['id'] for j in alternatives]})
    for segment in segments:
        segment['lockKey']=f"{segment['number']}:{segment['startTick']}:{segment['endTick']}"
        segment['eventId']=f"block-{segment['number']}-{segment['startTick']}"
        segment['beat']=1+(segment['startTick']-bars[segment['number']-1]['startTick'])/(divisions*4/denominator)
    summary=[]
    for bar in bars:
        first=next(s for s in segments if s['number']==bar['number'])
        summary.append({**first,**bar,'phraseStart':bar['number'] in starts,'locked':str(bar['number']) in locks})
    # Summary bars keep the shared measure playback clock; events use the finer segments.
    align_harmony(score,summary,chord_offset_ms)
    events,written,alignment=align_harmony(score,segments,chord_offset_ms)
    xml,fragments=engrave_block_chords(score,written,choices)
    signature={'version':POLICY,'resourceSha256':hashlib.sha256(RESOURCE.read_bytes()).hexdigest(),'upstreamCommit':resources()['source']['commit']}
    identity={'melody':score['scoreFingerprint'],'model':signature,'alignment':alignment,'locks':locks,'segmentLocks':segment_locks,'phrases':starts,'segments':[(s['startTick'],s['endTick'],s['chordId'],s['pitches']) for s in segments]}
    result={'policy':POLICY,'sourceFingerprint':score['scoreFingerprint'],'fingerprint':hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest(),'model':signature,'bars':summary,'segments':segments,'events':events,'choices':choices,'phraseStarts':starts,'locks':locks,'segmentLocks':segment_locks,'alignment':alignment,'writtenChords':written,'chordFragments':fragments,'xml':xml}
    from .instrumental import sections,profile
    result['instrumentalSections']=sections(score,result);result['instrumentalProfile']=profile(score)
    return result
