"""Basic chord planning: AccoMontage2 corpus/fit tables + constrained Viterbi.

Adapted, not the upstream end-to-end pipeline. See vendor/AccoMontage2/LICENSE.
The runtime reads JSON only and does not import training or texture dependencies.
"""
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import math
from .arrangement import TONICS, Chord, INTERVALS, transition_cost
from .score import KEYS, spell_pitch
from .harmony_timing import align_harmony
from .chord_score import engrave_block_chords

VERSION='basic-harmony-v2'
RESOURCE=Path(__file__).with_name('data')/'basic-harmony.json'


def harmony_for_settings(score,settings,default='adaptive-block-v1'):
    policy=settings.get('harmonyPolicy',default)
    if policy=='legacy':return generate_basic_harmony(score,settings.get('locks'),settings.get('phraseStarts'),settings.get('chordOffsetMs',0))
    if policy=='adaptive-block-v1':
        from .adaptive_harmony import generate
        return generate(score,settings.get('locks'),settings.get('phraseStarts'),settings.get('chordOffsetMs',0),settings.get('segmentLocks'))
    raise ValueError('Unsupported harmony policy.')

@lru_cache(maxsize=1)
def resources():
    return json.loads(RESOURCE.read_text(encoding='utf-8'))

def root_name(pc,fifths):
    step,alter,_=spell_pitch(pc+60,fifths)
    return step+('b'*(-alter) if alter<0 else '#' * alter)

def palette(key):
    tonic,mode=key.split();tonic=TONICS[tonic];fifths=KEYS[key]
    offsets=(0,2,4,5,7,9,11) if mode=='major' else (0,2,3,5,7,8,10)
    qualities=('major','minor','minor','major','major','minor','dim') if mode=='major' else ('minor','dim','major','minor','minor','major','major')
    romans=('I','ii','iii','IV','V','vi','vii°') if mode=='major' else ('i','ii°','III','iv','v','VI','VII')
    result=[]
    for degree,(offset,quality,roman) in enumerate(zip(offsets,qualities,romans),1):
        result.append({'id':f'{degree}:{quality}','degree':degree,'root':(tonic+offset)%12,'quality':quality,'roman':roman})
    if mode=='minor':result.append({'id':'5:major','degree':5,'root':(tonic+7)%12,'quality':'major','roman':'V'})
    result.append({'id':'5:7','degree':5,'root':(tonic+7)%12,'quality':'7','roman':'V7'})
    for c in result:
        c['pitchClasses']=[(c['root']+v)%12 for v in INTERVALS[c['quality']]]
        c['name']=root_name(c['root'],fifths)+{'major':'','minor':'m','dim':'dim','7':'7'}[c['quality']]
        c['tones']=[root_name(pc,fifths) for pc in c['pitchClasses']]
    return result+[{'id':'none','degree':0,'root':None,'quality':'none','roman':'—','pitchClasses':[],'name':'N.C.','tones':[]}]

def corpus_prior(mode):
    transitions=defaultdict(Counter);positions=defaultdict(Counter)
    for template in resources()['templates']:
        if template['mode']!=mode:continue
        degrees=[Counter(bar).most_common(1)[0][0] for bar in template['bars']]
        for index,degree in enumerate(degrees):
            positions[index%4][degree]+=1
            if index:transitions[degrees[index-1]][degree]+=1
    return transitions,positions

def phrase_starts(score,provided):
    count=len(score['measures'])
    if provided is not None:
        if not isinstance(provided,list) or not provided or provided[0]!=1 or any(type(n)!=int or n<1 or n>count for n in provided) or provided!=sorted(set(provided)):
            raise ValueError('Invalid phrase boundaries.')
        return provided
    starts=[1];quarter=60/score['bpm']
    first=1
    if score['measures'][0].get('pickup') and count>1:starts.append(2);first=2
    for index,bar in enumerate(score['measures'][first:],first):
        before=[n['end'] for n in score['notes'] if n['end']<=bar['start']]
        after=[n['start'] for n in score['notes'] if n['start']>=bar['start']]
        gap=bool(before and after and min(after)-max(before)>=quarter)
        if index+1-starts[-1]>=4 or (gap and index+1-starts[-1]>=2):starts.append(index+1)
    return starts

def melody_cost(chord,bar,notes,bpm,key):
    local=[(max(bar['start'],n['start']),min(bar['end'],n['end']),n) for n in notes if n['start']<bar['end'] and n['end']>bar['start']]
    if not local:return (0.,0.) if chord['id']=='none' else (2.,0.)
    if chord['id']=='none':return 4.,1.
    tonic,mode=key.split();tonic=TONICS[tonic];table=resources()['fitTables'][mode][chord['degree']-1]
    total=weight=conflict=0.;quarter=60/bpm
    for left,right,n in local:
        pc=n['midi']%12
        metrical_start=bar.get('metricalStart',bar['start'])
        beat=(n['start']-metrical_start)/quarter
        if 'calibratedBeat' in n:beat=n['calibratedBeat']-bar['startTick']/bar['quarterDivisions']
        strength=2. if abs(beat)<.12 else 1.35 if abs(beat-round(beat))<.12 else .8
        mass=(right-left)/quarter*strength
        if 'calibratedBeat' in n:mass=(min(n['endTick'],bar['endTick'])-max(n['startTick'],bar['startTick']))/bar['quarterDivisions']*strength
        in_chord=pc in chord['pitchClasses']
        passing=False
        i=n['index']-1
        if not in_chord and 0<i<len(notes)-1 and n['end']-n['start']<quarter*.55 and strength<1:
            before,after=notes[i-1],notes[i+1]
            passing=abs(before['midi']-n['midi'])<=2 and abs(after['midi']-n['midi'])<=2 and before['midi']%12 in chord['pitchClasses'] and after['midi']%12 in chord['pitchClasses']
        miss=0 if in_chord else .18 if passing else 1.
        # Table affinity is a corpus model preference, never a correctness probability.
        cost=miss*1.5+(1-table[(pc-tonic)%12])*.45
        if chord['quality']=='7':cost+=.05
        if not in_chord and any((pc-p)%12 in (1,11) for p in chord['pitchClasses']):cost+=.15
        total+=mass*cost;weight+=mass;conflict+=mass*miss
    return total/max(weight,1e-8),conflict/max(weight,1e-8)

def connection(before,after,transitions):
    if not before['degree'] or not after['degree']:return 0.
    counts=transitions[before['degree']]
    prior=-math.log((counts[after['degree']]+1)/(sum(counts.values())+7))*.12
    def as_chord(c):
        function='D' if c['degree'] in (5,7) else 'P' if c['degree'] in (2,4) else 'T'
        return Chord(c['root'],c['quality'],c['roman'],function)
    return prior+transition_cost(as_chord(before),as_chord(after))*.5

def voicing(chord,previous):
    if not chord['pitchClasses']:return []
    candidates=[]
    for base in range(48,60):
        if base%12 not in chord['pitchClasses']:continue
        pitches=sorted(base+(pc-base)%12 for pc in chord['pitchClasses'])
        if max(pitches)>67:continue
        motion=sum(abs(a-b) for a,b in zip(pitches,previous)) if previous else abs(base-48)*.4
        penalty=motion+(0 if base%12==chord['root'] else 1.5)+abs(sum(pitches)/len(pitches)-56)*.15
        candidates.append((penalty,pitches))
    return min(candidates,key=lambda v:(v[0],v[1]))[1]

def generate_basic_harmony(score,locks=None,phrases=None,chord_offset_ms=0):
    if not score.get('notes'):raise ValueError('No melody notes are available for harmony.')
    if len(score['measures'])>4096:raise ValueError('This score is too long for basic harmony.')
    choices=palette(score['key']);by_id={c['id']:c for c in choices}
    locks={} if locks is None else locks
    if not isinstance(locks,dict) or any(not isinstance(k,str) or not k.isdigit() or str(int(k))!=k or not 1<=int(k)<=len(score['measures']) or not isinstance(v,str) or v not in by_id for k,v in locks.items()):
        raise ValueError('Invalid locked chord.')
    starts=phrase_starts(score,phrases);mode=score['key'].split()[1]
    transitions,positions=corpus_prior(mode)
    analysis_notes=[{**n,'start':n['notatedStart'],'end':n['notatedEnd']} for n in score['notes']]
    if score.get('downbeats'):
        analysis_notes=[{**n,'calibratedBeat':n['startTick']/score['divisions']} for n in analysis_notes]
    emissions=[];conflicts=[];phrase_index=0
    for i,bar in enumerate(score['measures']):
        if phrase_index+1<len(starts) and i+1>=starts[phrase_index+1]:phrase_index+=1
        relative=i+1-starts[phrase_index];prior=positions[relative%4]
        ending=[n for n in analysis_notes if n['start']<bar['end'] and n['end']>bar['start']]
        closure=(i+2 in starts or i==len(score['measures'])-1) and ending and ending[-1]['end']-ending[-1]['start']>=60/score['bpm']*.75
        target=None
        if closure:
            final_pc=ending[-1]['midi']%12
            if final_pc in choices[0]['pitchClasses']:target=1
            elif final_pc in by_id['5:7']['pitchClasses']:target=5
        costs=[];bad=[]
        for c in choices:
            cost,conflict=melody_cost(c,{**bar,'quarterDivisions':score['divisions']},analysis_notes,score['bpm'],score['key'])
            if c['degree']:cost+=.07*-math.log((prior[c['degree']]+1)/(sum(prior.values())+7))
            if target and c['degree'] not in (0,target):cost+=.16
            if str(i+1) in locks and locks[str(i+1)]!=c['id']:cost=math.inf
            # An entirely silent bar remains silent unless explicitly assigned a chord.
            if not bar['hasVocal'] and str(i+1) not in locks and c['id']!='none':cost=math.inf
            if bar['hasVocal'] and c['id']=='none' and str(i+1) not in locks:cost=math.inf
            costs.append(cost);bad.append(conflict)
        emissions.append(costs);conflicts.append(bad)
    values=emissions[0][:];history=[]
    for row in emissions[1:]:
        updated=[];back=[]
        for j,c in enumerate(choices):
            costs=[value+connection(p,c,transitions) for value,p in zip(values,choices)]
            winner=min(range(len(choices)),key=lambda n:(costs[n],n))
            back.append(winner);updated.append(costs[winner]+row[j])
        history.append(back);values=updated
    winner=min(range(len(choices)),key=lambda n:(values[n],n));path=[winner]
    for back in reversed(history):winner=back[winner];path.append(winner)
    path.reverse();bars=[];previous=[]
    for i,(bar,index) in enumerate(zip(score['measures'],path)):
        c=choices[index];pitches=voicing(c,previous)
        if pitches:previous=pitches
        ranking=[]
        for j,option in enumerate(choices):
            cost,bad=melody_cost(option,{**bar,'quarterDivisions':score['divisions']},analysis_notes,score['bpm'],score['key'])
            if i:cost+=connection(choices[path[i-1]],option,transitions)
            if i+1<len(path):cost+=connection(option,choices[path[i+1]],transitions)
            ranking.append((cost,j,bad))
        ranking.sort();alternatives=[choices[j]['id'] for _,j,_ in ranking[:3]]
        bars.append({**bar,'chordId':c['id'],'name':c['name'],'roman':c['roman'],'tones':c['tones'],'root':c['root'],'quality':c['quality'],
                     'pitches':pitches,'locked':str(bar['number']) in locks,'phraseStart':bar['number'] in starts,
                     'needsReview':conflicts[i][index]>.35,'alternatives':alternatives})
    events,written,alignment=align_harmony(score,bars,chord_offset_ms)
    xml,fragments=engrave_block_chords(score,written,choices)
    signature={'version':VERSION,'resourceSha256':hashlib.sha256(RESOURCE.read_bytes()).hexdigest(),'upstreamCommit':resources()['source']['commit']}
    identity={'melody':score['scoreFingerprint'],'model':signature,'alignment':alignment,'locks':locks,'phrases':starts,'bars':[(b['chordId'],b['pitches']) for b in bars]}
    return {'sourceFingerprint':score['scoreFingerprint'],'fingerprint':hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest(),
            'model':signature,'bars':bars,'events':events,'choices':choices,'phraseStarts':starts,'locks':locks,
            'alignment':alignment,'writtenChords':written,'chordFragments':fragments,'xml':xml}
