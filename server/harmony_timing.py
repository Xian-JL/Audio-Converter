"""One monotone mapping from written beats to GF performance time."""
from bisect import bisect_right
import math
from .meter_grid import score_grid

def interpolate(points,value):
    if value<=points[0][0]:return points[0][1]
    if value>=points[-1][0]:return points[-1][1]
    i=bisect_right([p[0] for p in points],value)-1
    x,y=points[i];xx,yy=points[i+1]
    return y+(value-x)/(xx-x)*(yy-y)

def align_harmony(score,bars,offset_ms=0):
    if isinstance(offset_ms,bool):raise ValueError('Chord timing must be between -2000 and 2000 ms.')
    try:offset_ms=float(offset_ms)
    except (TypeError,ValueError):raise ValueError('Chord timing must be between -2000 and 2000 ms.') from None
    if not math.isfinite(offset_ms) or not -2000<=offset_ms<=2000:raise ValueError('Chord timing must be between -2000 and 2000 ms.')
    duration=score['duration'];knots={0.:0.,duration:duration}
    for n in score['notes']:
        if n['notatedStart']<duration:knots[n['notatedStart']]=n['start']
    anchors=sorted(knots.items())
    if any(a[1]>=b[1] for a,b in zip(anchors,anchors[1:])):raise ValueError('Unable to align the melody timeline.')
    inverse=sorted((y,x) for x,y in anchors)
    grid=score_grid(score);events=[];written=[]
    for bar in bars:
        bar['playStart']=round(interpolate(anchors,bar['start']),6)
        bar['playEnd']=round(interpolate(anchors,bar['end']),6)
        if not bar['pitches']:continue
        start=max(0.,min(duration,bar['playStart']+offset_ms/1000))
        end=max(0.,min(duration,bar['playEnd']+offset_ms/1000))
        if end-start<1e-6:continue
        first=max(written[-1]['startTick']+1 if written else 0,round(grid.tick(interpolate(inverse,start))))
        last=max(first+1,round(grid.tick(interpolate(inverse,end))))
        event={'id':f"chord-{bar['number']}",'start':round(start,6),'end':round(end,6),'pitches':bar['pitches'],'staff':2,'velocity':.65}
        events.append(event)
        written.append({**event,'startTick':first,'endTick':last,'chordId':bar['chordId']})
    for before,after in zip(written,written[1:]):before['endTick']=min(before['endTick'],after['startTick'])
    return events,written,{'version':'gf-grid-warp-v1','offsetMs':offset_ms,'anchors':anchors,'maxWarpMs':round(max(abs(x-y) for x,y in anchors)*1000,3)}
