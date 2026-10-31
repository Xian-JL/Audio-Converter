"""Unreduced model accompaniment over a frozen harmony plan and GF grid.

Historical reducers remain for regression checks; new generation bypasses both.
"""
from collections import OrderedDict
import copy
import hashlib
import json
from itertools import permutations
from statistics import median
import threading
import time
from .chord_score import engrave_block_chords
from .harmony_timing import interpolate
from .meter_grid import score_grid

LOCK=threading.Lock()
CACHE=OrderedDict()

def reduce_left_hand(score,harmony,proposals,density):
    grid=score_grid(score);step=score['divisions']//4;events=[];previous=55
    choices={c['id']:c for c in harmony['choices']}
    for bar in harmony['bars']:
        if not bar['pitches']:continue
        left=bar.get('startTick',(bar['number']-1)*grid.bar_ticks);right=bar.get('endTick',left+grid.bar_ticks)
        right=min(right,round(grid.tick(score['duration'])))
        if right<=left:continue
        local=[p for p in proposals if left<=p['tick']<right]
        if bar.get('pickup'):local=[{'tick':left,'pitches':bar['pitches'],'length':right-left}]
        if not local or local[0]['tick']>left:local=[{'tick':left,'pitches':[bar['root']+48],'length':min(score['divisions'],right-left)}]+local
        local=sorted({p['tick']:p for p in local}.values(),key=lambda p:p['tick'])
        melody=[n for n in score['notes'] if left<=n['startTick']<right]
        limit=(4,8,12)[density]
        if len(melody)>=8:limit=min(limit,4)
        # Keep a whole-phrase-derived rhythm; thinning protects a busy singer.
        if len(local)>limit:
            selected=sorted(set([0]+[round(i*(len(local)-1)/(limit-1)) for i in range(1,limit)]));local=[local[i] for i in selected]
        pcs=choices[bar['chordId']]['pitchClasses']
        for i,p in enumerate(local):
            tick=p['tick'];next_tick=local[i+1]['tick'] if i+1<len(local) else right
            end=min(next_tick,tick+max(step,p['length']),right)
            if end<=tick:continue
            folded=[]
            for source in p['pitches']:
                options=[m for m in range(48,65) if m%12 in pcs]
                if source%12 in pcs:options=[m for m in options if m%12==source%12]
                folded_source=source+12*round((55-source)/12)
                target=min(options,key=lambda m:min((m-source)%12,(source-m)%12)*2+abs(m-folded_source)+.25*abs(m-previous)+max(0,abs(m-previous)-9)*1.5)
                if target not in folded:folded.append(target)
            folded.sort()
            if tick==left:
                root=min((m for m in range(48,65) if m%12==bar['root']),key=lambda m:abs(m-previous)+.3*abs(m-52))
                folded=sorted(set([root]+folded))
            while len(folded)>3 or (folded and folded[-1]-folded[0]>12):
                if len(folded)>1:
                    removable=[j for j,m in enumerate(folded) if tick!=left or m%12!=bar['root']]
                    if not removable:removable=list(range(1,len(folded)))
                    victim=max(removable,key=lambda j:(abs(folded[j]-(bar['root']+48 if tick==left else previous)),j));folded.pop(victim)
                else:break
            if not folded:continue
            # A genuine rest near a phrase ending gives the accompaniment a breath.
            phrase_end=bar['number']+1 in harmony['phraseStarts'] or bar['number']==len(harmony['bars'])
            vocal_end=max((n['endTick'] for n in melody),default=right)
            if phrase_end and right-vocal_end>=score['divisions']//2:
                end=min(end,right-score['divisions']//2)
                if end<=tick:continue
            velocity=.61 if tick==left else .48 if (tick-left)%score['divisions'] else .55
            events.append({'id':f"texture-{bar['number']}-{i}",'startTick':tick,'endTick':end,'pitches':folded,'staff':2,'chordId':bar['chordId'],'velocity':velocity,'showChord':i==0})
            previous=folded[-1]
    return events

def layer_left_hand(score,harmony,proposals,density):
    """Retain decoder durations in three independent monophonic left-hand lanes.

    The compact reducer supplies the same tested rhythm and chord folding. Bass
    and inner tones then keep their own decoded ends until their lane reattacks.
    """
    compact=reduce_left_hand(score,harmony,proposals,density)
    proposals_by_tick={p['tick']:p for p in proposals};events=[];previous={2:48,3:55,4:60}
    for attack in compact:
        bar=next(b for b in harmony['bars'] if b['number']==int(attack['id'].split('-')[1]))
        right=min(bar['endTick'],round(score_grid(score).tick(score['duration'])))
        source=proposals_by_tick.get(attack['startTick'],{})
        tones=source.get('tones',[{'midi':p,'length':source.get('length',attack['endTick']-attack['startTick'])} for p in source.get('pitches',[])])
        pitches=attack['pitches'][:]
        if attack['startTick']==bar['startTick']:
            root=next(m for m in range(48,60) if m%12==bar['root'])
            pitches=sorted(set([root]+[p for p in pitches if p%12!=bar['root']]))[:3]
        melody=[n for n in score['notes'] if bar['startTick']<=n['startTick']<bar['endTick']]
        ceiling=min(64,max(55,round(median(n['midi'] for n in melody))-3)) if melody else 60
        pitches=sorted(set(p-12 if p>ceiling and p-12>=48 else p for p in pitches))
        while len(pitches)>1 and pitches[-1]-pitches[0]>12:pitches.pop()
        lanes=min(permutations((2,3,4),len(pitches)),key=lambda lanes:sum(abs(p-previous[lane]) for p,lane in zip(pitches,lanes)))
        for voice,pitch in zip(lanes,pitches):
            candidates=[t for t in tones if t['midi']%12==pitch%12]
            length=max((t['length'] for t in candidates),default=attack['endTick']-attack['startTick'])
            end=min(right,attack['startTick']+max(1,length))
            # Keep the established phrase-ending breath rather than filling it.
            if attack['endTick']<right and right-attack['endTick']==score['divisions']//2:
                end=min(end,attack['endTick'])
            phrase_start=max((p for p in harmony['phraseStarts'] if p<=bar['number']),default=1)
            phrase_end=next((p-1 for p in harmony['phraseStarts'] if p>bar['number']),len(harmony['bars']))
            gain=.92 if bar['number']==phrase_start else .85 if bar['number']==phrase_end else 1.
            if len(melody)>=8:gain*=.88
            events.append({**attack,'id':attack['id']+f'-v{voice}','pitches':[pitch],'endTick':end,'voice':voice,'velocity':round(attack['velocity']*gain,4),'showChord':attack['showChord'] and pitch==pitches[0]})
            previous[voice]=pitch
    for voice in (2,3,4):
        local=[n for n in events if n['voice']==voice]
        for a,b in zip(local,local[1:]):a['endTick']=min(a['endTick'],b['startTick'])
    # A held inner tone must not widen the active hand beyond an octave.
    active=[]
    for note in events:
        active=[held for held in active if held['endTick']>note['startTick']]
        for held in active:
            if held['startTick']<note['startTick']<held['endTick'] and abs(held['pitches'][0]-note['pitches'][0])>12:held['endTick']=note['startTick']
        active.append(note)
    return sorted((n for n in events if n['endTick']>n['startTick']),key=lambda n:(n['startTick'],n['voice']))

def model_notes(score,harmony,proposals):
    """Represent every decoded tone without changing its pitch or duration.

    Independent non-overlapping XML voices are bookkeeping only. Equal-onset,
    equal-duration tones share a chord; overlapping tones use another voice.
    Only the end of the source recording bounds the generated material.
    """
    grid=score_grid(score);end_tick=min(score['measures'][-1]['endTick'],round(grid.tick(score['duration'])))
    events=[];ends={};shown=set()
    for proposal in sorted(proposals,key=lambda p:p['tick']):
        tick=proposal['tick']
        if tick<0 or tick>=end_tick:continue
        bar=next((b for b in harmony['bars'] if b['startTick']<=tick<b['endTick']),None)
        if bar is None:continue
        tones=proposal.get('tones',[{'midi':p,'length':proposal['length']} for p in proposal['pitches']])
        groups={}
        for tone in tones:
            end=min(end_tick,tick+tone['length'])
            if end>tick:groups.setdefault(end,[]).append(tone['midi'])
        for end,pitches in groups.items():
            voice=next((v for v in range(2,len(ends)+3) if ends.get(v,0)<=tick),len(ends)+2)
            ends[voice]=end
            show=bar['number'] not in shown and bar['root'] is not None
            if show:shown.add(bar['number'])
            events.append({'id':f'model-{len(events)+1}','startTick':tick,'endTick':end,'pitches':pitches,'staff':2,'voice':voice,'chordId':bar['chordId'],'velocity':.65,'showChord':show})
    return events


def render_texture(score,harmony,written,preserve=False):
    grid=score_grid(score);anchors=harmony['alignment']['anchors'];inverse=sorted((y,x) for x,y in anchors);offset=harmony['alignment']['offsetMs']/1000
    events=[];notation=[];previous={}
    for n in written:
        start=max(0,min(score['duration'],interpolate(anchors,grid.time(n['startTick']))+offset))
        end=max(0,min(score['duration'],interpolate(anchors,grid.time(n['endTick']))+offset))
        if end-start<1e-6:continue
        voice=n.get('voice',2)
        first=n['startTick'] if preserve and not offset else max(previous.get(voice,-1)+1,round(grid.tick(interpolate(inverse,start))))
        previous[voice]=first
        last=n['endTick'] if preserve and not offset else max(first+1,round(grid.tick(interpolate(inverse,end))))
        e={'id':n['id'],'start':round(start,6),'end':round(end,6),'pitches':n['pitches'],'staff':2,'velocity':n['velocity'],**({'voice':voice} if 'voice' in n else {})}
        events.append(e);notation.append({**n,'startTick':first,'endTick':last})
    if not preserve:
        for voice in {n.get('voice',2) for n in notation}:
            local=[n for n in notation if n.get('voice',2)==voice]
            for a,b in zip(local,local[1:]):a['endTick']=min(a['endTick'],b['startTick'])
    xml,fragments=engrave_block_chords(score,notation,harmony['choices'],'Piano arrangement')
    return events,notation,xml,fragments

def perform_model_notes(score,harmony,decoded,offset_ms=0,preserve_velocity=False):
    """Assign notation voices without changing decoded performance boundaries."""
    grid=score_grid(score);inverse=sorted((y,x) for x,y in harmony['alignment']['anchors'])
    groups={};events=[];written=[];ends={};tick_ends={};shown=set()
    for n in decoded:
        start=round(max(0,min(score['duration'],n['start']+offset_ms/1000)),6)
        end=round(max(0,min(score['duration'],n['end']+offset_ms/1000)),6)
        if end<=start:continue
        velocity=n.get('velocity',.65) if preserve_velocity else .65
        if type(velocity) not in (int,float) or not 0<=velocity<=1:raise ValueError('Invalid generated note velocity.')
        groups.setdefault((start,end,velocity),[]).append(n['midi'])
    for (start,end,velocity),pitches in sorted(groups.items()):
        a=max(0,round(grid.tick(interpolate(inverse,start))));b=max(a+1,round(grid.tick(interpolate(inverse,end))))
        b=min(score['measures'][-1]['endTick'],b)
        if b<=a:continue
        voice=next(v for v in range(2,len(ends)+3) if ends.get(v,0)<=start+1e-7 and tick_ends.get(v,0)<=a)
        ends[voice]=end;tick_ends[voice]=b
        bar=next((bar for bar in harmony['bars'] if bar['startTick']<=a<bar['endTick']),harmony['bars'][-1])
        show=bar['root'] is not None and bar['number'] not in shown
        if show:shown.add(bar['number'])
        identity=f'amt-{len(events)+1}'
        events.append({'id':identity,'start':start,'end':end,'pitches':pitches,'staff':2,'voice':voice,'velocity':velocity})
        written.append({'id':identity,'startTick':a,'endTick':b,'pitches':pitches,'staff':2,'voice':voice,'velocity':velocity,'chordId':bar['chordId'],'showChord':show})
    xml,fragments=engrave_block_chords(score,written,harmony['choices'],'Piano arrangement')
    return events,written,xml,fragments


def generate_accompaniment(score,harmony,seed=0,on_progress=None,selection=None,base_arrangement=None):
    if score['meter']!='4/4':raise ValueError('Expressive accompaniment currently supports 4/4. The block-chord version remains available.')
    if type(seed)!=int or not 0<=seed<=0xffffffff:raise ValueError('Invalid accompaniment seed.')
    settings={'mode':'amt','seed':seed};base_notes=None
    if selection is not None:
        if not isinstance(selection,dict) or set(selection)!={'firstMeasure','lastMeasure'} or any(type(selection[k])!=int for k in selection) or not 1<=selection['firstMeasure']<=selection['lastMeasure']<=len(score['measures']):raise ValueError('Invalid accompaniment measure range.')
        from .project import restore_texture
        base=restore_texture(base_arrangement,score,harmony)
        offset=harmony['alignment']['offsetMs']/1000
        base_notes=[{'start':e['start']-offset,'end':e['end']-offset,'midi':p} for e in base['events'] for p in e['pitches']]
        settings.update(range=selection,baseFingerprint=base['fingerprint'])
    key='amt-medium-v1:'+harmony['fingerprint']+':'+json.dumps(settings,sort_keys=True)
    with LOCK:
        if key in CACHE:return copy.deepcopy(CACHE[key])
        from .amt_model import infer
        start=time.perf_counter();decoded,references,manifest=infer(score,harmony,seed,on_progress,selection,base_notes)
        if on_progress:on_progress({'stage':'engraving','progress':.98})
        events,notation,xml,fragments=perform_model_notes(score,harmony,decoded,harmony['alignment']['offsetMs'])
        if not events:raise ValueError('AMT did not generate playable accompaniment. Please regenerate.')
        identity={'version':'amt-medium-v1','harmony':harmony['fingerprint'],'settings':settings,'model':manifest['files'],'events':events}
        result={'sourceFingerprint':score['scoreFingerprint'],'harmonyFingerprint':harmony['fingerprint'],'fingerprint':hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest(),
                'settings':settings,'events':events,'writtenChords':notation,'xml':xml,'chordFragments':fragments,'references':references,'model':{'version':'amt-medium-v1','commit':manifest['commit'],'revision':manifest.get('revision'),'files':manifest['files']},'generationSeconds':round(time.perf_counter()-start,3)}
        CACHE[key]=result
        while len(CACHE)>6:CACHE.popitem(last=False)
        return copy.deepcopy(result)
