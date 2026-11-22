"""All editable instrument notes retain stable identity, including chord members."""
import uuid
from .performance_score import generate, checked_notes


def edit(source, body):
    score=generate(source,body)
    if score['scoreFingerprint']!=body.get('sourceFingerprint'):raise ValueError('The score changed. Reload it before editing.')
    notes=checked_notes(body.get('editedNotes') if body.get('editedNotes') is not None else (score.get('editedNotes') or source['notes']),source['duration'])
    op=body.get('operation')
    if not isinstance(op,dict):raise ValueError('Invalid note edit.')
    kind=op.get('kind');identity=op.get('id');at=next((i for i,n in enumerate(notes) if n['id']==identity),None)
    anchors={p['noteId'] for p in score.get('downbeats',[])};selected=identity
    if kind=='insert':
        selected='edit-'+uuid.uuid4().hex;notes.append({'id':selected,**{k:op[k] for k in ('start','end','midi','staff') if k in op}})
    elif at is None:raise ValueError('Select a note.')
    elif kind=='update':
        before=dict(notes[at]);notes[at].update({k:op[k] for k in ('start','end','midi','staff') if k in op})
        # A timing edit invalidates the saved trajectory rather than inventing bend timestamps.
        if any(k in op and op[k]!=before.get(k) for k in ('start','end','midi')):notes[at].pop('pitchBends',None)
    elif kind=='delete':
        if identity in anchors:raise ValueError('Choose another downbeat before deleting this note.')
        notes.pop(at);selected=notes[min(at,len(notes)-1)]['id'] if notes else None
    elif kind=='split':
        note=notes[at];time=op.get('time')
        if type(time) not in (int,float) or not note['start']<time<note['end']:raise ValueError('Split time must be inside the note.')
        selected='edit-'+uuid.uuid4().hex
        right={**note,'id':selected,'start':time};note['end']=time
        if note.get('pitchBends'):
            trajectory=note['pitchBends'];note['pitchBends']=[p for p in trajectory if p[0]<=time];right['pitchBends']=[p for p in trajectory if p[0]>=time]
        notes.append(right)
    elif kind=='merge':
        note=notes[at];nxt=next((n for n in notes[at+1:] if n['midi']==note['midi'] and n.get('staff')==note.get('staff') and n['start']>=note['end']),None)
        if nxt is None:raise ValueError('No later non-overlapping equal-pitch note in this staff.')
        if nxt['id'] in anchors:raise ValueError('Choose another downbeat before merging.')
        note['end']=nxt['end'];note.pop('pitchBends',None);notes.remove(nxt)
    else:raise ValueError('Unknown note edit.')
    notes=checked_notes(notes,source['duration']);rebuilt=generate(source,{**body,'editedNotes':notes});rebuilt['revisionKind']='edit'
    return {'score':rebuilt,'harmony':None,'kind':'edit','selectedNoteId':selected}
