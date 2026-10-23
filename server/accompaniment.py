"""Left-hand arrangement over a frozen harmony plan and the existing GF grid."""
from collections import OrderedDict
import copy
import hashlib
import json
import threading
import time
from .chord_score import engrave_block_chords
from .harmony_timing import interpolate
from .meter_grid import score_grid

LOCK=threading.Lock()
CACHE=OrderedDict()
STYLES={'lyrical','flowing','syncopated'}

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

def render_texture(score,harmony,written):
    grid=score_grid(score);anchors=harmony['alignment']['anchors'];inverse=sorted((y,x) for x,y in anchors);offset=harmony['alignment']['offsetMs']/1000
    events=[];notation=[]
    for n in written:
        start=max(0,min(score['duration'],interpolate(anchors,grid.time(n['startTick']))+offset))
        end=max(0,min(score['duration'],interpolate(anchors,grid.time(n['endTick']))+offset))
        if end-start<1e-6:continue
        first=max(notation[-1]['startTick']+1 if notation else 0,round(grid.tick(interpolate(inverse,start))))
        last=max(first+1,round(grid.tick(interpolate(inverse,end))))
        e={'id':n['id'],'start':round(start,6),'end':round(end,6),'pitches':n['pitches'],'staff':2,'velocity':n['velocity']}
        events.append(e);notation.append({**n,'startTick':first,'endTick':last})
    for a,b in zip(notation,notation[1:]):a['endTick']=min(a['endTick'],b['startTick'])
    xml,fragments=engrave_block_chords(score,notation,harmony['choices'],'Piano arrangement')
    return events,notation,xml,fragments

def generate_accompaniment(score,harmony,style='lyrical',density=1,variant=0):
    if score['meter']!='4/4':raise ValueError('Expressive accompaniment currently supports 4/4. The block-chord version remains available.')
    if style not in STYLES or type(density)!=int or density not in (0,1,2) or type(variant)!=int or variant not in (0,1,2):raise ValueError('Invalid accompaniment settings.')
    settings={'style':style,'density':density,'variant':variant};key=harmony['fingerprint']+json.dumps(settings,sort_keys=True)
    with LOCK:
        if key in CACHE:return copy.deepcopy(CACHE[key])
        from .texture_model import infer
        start=time.perf_counter();proposals,references,manifest=infer(score,harmony,style,density,variant)
        written=reduce_left_hand(score,harmony,proposals,density);events,notation,xml,fragments=render_texture(score,harmony,written)
        identity={'version':'neural-left-v1','harmony':harmony['fingerprint'],'settings':settings,'model':manifest['files'],'events':events}
        result={'sourceFingerprint':score['scoreFingerprint'],'harmonyFingerprint':harmony['fingerprint'],'fingerprint':hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest(),
                'settings':settings,'events':events,'writtenChords':notation,'xml':xml,'chordFragments':fragments,'references':references,'model':{'version':'neural-left-v1','commit':manifest['commit'],'files':manifest['files']},'generationSeconds':round(time.perf_counter()-start,3)}
        CACHE[key]=result
        while len(CACHE)>6:CACHE.popitem(last=False)
        return copy.deepcopy(result)
