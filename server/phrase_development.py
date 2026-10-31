"""Phrase-level sampling guidance. These functions never edit generated notes."""
from collections import Counter
from statistics import median

VERSION='phrase-development-v1'


def roles(count):
    if count<=0:return []
    if count==1:return ['resolution']
    return ['statement' if i==0 else 'resolution' if i==count-1 else 'development' for i in range(count)]


def boundary_harmonies(harmony,region):
    sounding=[s for s in harmony.get('segments',harmony['bars']) if s['pitches']]
    previous=max((s for s in sounding if s.get('playEnd',s['end'])<=region['start']+1e-6),key=lambda s:s.get('playEnd',s['end']),default=None)
    following=min((s for s in sounding if s.get('playStart',s['start'])>=region['end']-1e-6),key=lambda s:s.get('playStart',s['start']),default=None)
    return previous or following,following or previous


def pitch_penalty(pitch,history,role='statement',center=None,arrival_pcs=()):
    """Discourage repeated upper-melody cycles, with soft rather than pitch-folding rules."""
    history=list(history);penalty=0.
    if history:
        penalty+=.018*max(0,abs(pitch-history[-1])-7)**2
        repeated=0
        for value in reversed(history):
            if value!=pitch:break
            repeated+=1
        penalty+=.7*max(0,repeated-1)
    for length,weight in ((4,4.5),(6,6.0)):
        if len(history)>=length:
            candidate=tuple(history[-(length-1):]+[pitch])
            repeats=sum(tuple(history[i:i+length])==candidate for i in range(len(history)-length+1))
            penalty+=weight*min(3,repeats)
    if center is not None:
        target=center+(3 if role=='development' else 0)
        penalty+=.012*max(0,abs(pitch-target)-5)**2
    if role=='resolution' and arrival_pcs and pitch%12 not in arrival_pcs:penalty+=.35
    return penalty


def lead_signature(notes):
    return tuple((beat,duration,pitch) for beat,duration,pitch in notes)


def note_signature(notes,left,right,floor=55):
    """Skyline onsets, excluding bass patterns under sustained upper voices."""
    groups={}
    for n in notes:
        if n['midi']>=floor:groups.setdefault(n['start'],[]).append(n)
    result=[]
    for start,local in sorted(groups.items()):
        highest=max(local,key=lambda n:n['midi'])
        if any(n['start']<start<n['end']-1e-6 and n['midi']>highest['midi'] for n in notes):continue
        result.append((round((start-left)/(right-left)*16),round((highest['end']-start)/(right-left)*16),highest['midi']))
    return tuple(result)


def repeated_bar(signature,previous):
    # Motifs may recur; consecutive complete copies of a developed melody are rejected.
    return len(signature)>=3 and bool(previous) and signature==previous[-1]


def diagnostics(signatures):
    pitches=[n[2] for bar in signatures for n in bar]
    grams=[tuple(pitches[i:i+4]) for i in range(max(0,len(pitches)-3))]
    counts=Counter(grams)
    return {'bars':len(signatures),'uniqueBarMelodies':len(set(signatures)),
            'consecutiveExactCopies':sum(a==b and len(a)>=3 for a,b in zip(signatures,signatures[1:])),
            'repeatedFourNoteWindows':sum(max(0,count-1) for count in counts.values()),
            'fourNoteWindows':len(grams),'uniqueMelodyPitches':len(set(pitches))}
