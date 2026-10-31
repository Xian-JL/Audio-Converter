"""Validated complete-bar gaps and musical context for instrumental composition."""
from statistics import median
from .meter_grid import score_grid

MINIMUM_BARS=2


def sections(score,harmony):
    grid=score_grid(score);runs=[];current=[]
    for bar in harmony['bars']:
        left,right=bar['playStart'],bar['playEnd']
        complete=not bar.get('pickup') and bar['endTick']-bar['startTick']==grid.bar_ticks and grid.time(bar['endTick'])<=score['duration']+1e-7
        silent=complete and not any(n['start']<right and n['end']>left or n['startTick']<bar['endTick'] and n['endTick']>bar['startTick'] for n in score['notes'])
        if silent:current.append(bar)
        else:
            if len(current)>=MINIMUM_BARS:runs.append(current)
            current=[]
    if len(current)>=MINIMUM_BARS:runs.append(current)
    first=min(n['start'] for n in score['notes']);last=max(n['end'] for n in score['notes'])
    return [{'id':f"gap-{run[0]['number']}-{run[-1]['number']}",'firstMeasure':run[0]['number'],'lastMeasure':run[-1]['number'],'start':run[0]['playStart'],'end':run[-1]['playEnd'],
             'kind':'intro' if run[-1]['playEnd']<=first else 'outro' if run[0]['playStart']>=last else 'interlude'} for run in runs]


def selected_sections(score,harmony,provided=None):
    available=sections(score,harmony)
    if provided is None:return available
    if not isinstance(provided,list) or not provided or len(provided)>128:raise ValueError('Select at least one instrumental section.')
    chosen=[]
    for item in provided:
        if not isinstance(item,dict) or set(item)!={'firstMeasure','lastMeasure'} or any(type(item[k])!=int for k in item):raise ValueError('Invalid instrumental section.')
        a,b=item['firstMeasure'],item['lastMeasure']
        owner=next((s for s in available if s['firstMeasure']<=a<=b<=s['lastMeasure']),None)
        if owner is None or b-a+1<MINIMUM_BARS:raise ValueError('Instrumental sections need at least two complete melody-free measures.')
        if any(a<=s['lastMeasure'] and b>=s['firstMeasure'] for s in chosen):raise ValueError('Instrumental sections overlap.')
        chosen.append({**owner,'firstMeasure':a,'lastMeasure':b,'start':harmony['bars'][a-1]['playStart'],'end':harmony['bars'][b-1]['playEnd']})
    return sorted(chosen,key=lambda s:s['firstMeasure'])


def profile(score):
    notes=score['notes'];lengths=[n['end']-n['start'] for n in notes]
    return {'key':score['key'],'bpm':score['bpm'],'medianPitch':median(n['midi'] for n in notes),'medianNoteSeconds':round(median(lengths),4),
            'reference':'whole-song melody, neighboring phrases, key and tempo'}


def reference_motif(score,left,right):
    """Select actual song notes, never write/transpose them into the final score."""
    notes=score['notes'];before=[n for n in notes if n['end']<=left];after=[n for n in notes if n['start']>=right]
    target=median(n['midi'] for n in notes)
    nearby=before[-16:] if before else after[:16]
    if not nearby:nearby=notes[:16]
    # A contiguous phrase carries rhythmic and interval context; avoid isolated outliers.
    windows=[nearby[i:i+8] for i in range(max(1,len(nearby)-7))]
    return min(windows,key=lambda window:abs(median(n['midi'] for n in window)-target))
