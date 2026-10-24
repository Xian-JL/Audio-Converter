"""Validated, reversible edits over frozen GF notes. Never reruns recognition."""
import math
import json
import re
import uuid
from .melody_score import generate_melody_score

def notes_checked(notes,duration):
    if not isinstance(notes,list) or len(notes)>20000:raise ValueError('Invalid melody notes.')
    result=[];ids=set();last=0.
    for index,n in enumerate(notes):
        if not isinstance(n,dict):raise ValueError('Invalid melody notes.')
        identity=n.get('id',f'gf-{index+1:06d}')
        if not isinstance(identity,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',identity) or identity in ids:raise ValueError('Invalid note identities.')
        values=[n.get(k) for k in ('start','end','midi')]
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in values):raise ValueError('Note values must be finite numbers.')
        start,end,midi=values
        if not 0<=start<end<=duration+1e-6 or start<last-1e-6 or midi!=int(midi) or not 0<=midi<=127:raise ValueError('Notes must stay within the audio, use MIDI pitches 0–127, and must not overlap.')
        pitch=n.get('midiFloat',float(midi))
        if type(pitch) not in (int,float) or not math.isfinite(pitch):raise ValueError('Invalid note pitch.')
        result.append({'id':identity,'start':start,'end':end,'midi':int(midi),'midiFloat':pitch});last=end;ids.add(identity)
    return result

def restore_note_identity(notes,encoded,duration):
    if encoded is None:return notes
    if not isinstance(encoded,str) or len(encoded)>4*1024*1024:raise ValueError('Invalid note identity data.')
    try:raw=json.loads(encoded)
    except (ValueError,TypeError):raise ValueError('Invalid note identity data.') from None
    if notes_checked(raw,duration)!=notes_checked(notes,duration):raise ValueError('Note identity data does not match the melody.')
    return raw

def score_for_request(source,body,anchor=True):
    edited=body.get('editedNotes')
    result=source if edited is None else {**source,'notes':restore_note_identity(notes_checked(edited,source['duration']),body.get('identityNotesJson'),source['duration'])}
    score=generate_melody_score(result,body.get('bpm'),body.get('meter'),body.get('key'),body.get('anchorNoteId') if anchor else None)
    if edited is not None:score['editedNotes']=result['notes']
    return score

def edit_score(source,body):
    current=score_for_request(source,body)
    if body.get('sourceFingerprint')!=current['scoreFingerprint']:raise ValueError('The melody has changed. Reload the score.')
    notes=notes_checked(body.get('editedNotes') if body.get('editedNotes') is not None else source['notes'],source['duration'])
    operation=body.get('operation')
    if not isinstance(operation,dict):raise ValueError('Invalid note edit.')
    kind=operation.get('kind');identity=operation.get('id');index=next((i for i,n in enumerate(notes) if n['id']==identity),None)
    anchor=body.get('anchorNoteId');selected=identity
    if kind=='insert':
        selected='edit-'+uuid.uuid4().hex
        notes.append({'id':selected,'start':operation.get('start'),'end':operation.get('end'),'midi':operation.get('midi'),'midiFloat':operation.get('midi')})
    elif index is None:raise ValueError('Please select a melody note.')
    elif kind=='update':
        for key in ('start','end','midi'):
            if key in operation:notes[index][key]=operation[key]
        if 'midi' in operation:notes[index]['midiFloat']=operation['midi']
    elif kind=='delete':
        if identity==anchor:raise ValueError('Choose another downbeat before deleting its reference note.')
        notes.pop(index);selected=notes[min(index,len(notes)-1)]['id'] if notes else None
    elif kind=='split':
        at=operation.get('time');note=notes[index]
        if type(at) not in (int,float) or not math.isfinite(at) or not note['start']<at<note['end']:raise ValueError('Split time must be inside the selected note.')
        selected='edit-'+uuid.uuid4().hex;right={**note,'id':selected,'start':at};note['end']=at;notes.insert(index+1,right)
    elif kind=='merge':
        if index+1>=len(notes) or notes[index]['midi']!=notes[index+1]['midi']:raise ValueError('Only consecutive notes with the same pitch can be merged.')
        if notes[index+1]['id']==anchor:raise ValueError('Choose another downbeat before merging its reference note.')
        notes[index]['end']=notes[index+1]['end'];notes.pop(index+1)
    else:raise ValueError('Unknown note edit.')
    if any(type(n.get('start')) not in (int,float) for n in notes):raise ValueError('Invalid note start.')
    notes.sort(key=lambda n:n['start']);notes=notes_checked(notes,source['duration'])
    score=score_for_request(source,{**body,'editedNotes':notes,'identityNotesJson':None})
    score['revisionKind']='edit'
    return {'score':score,'harmony':None,'kind':'edit','selectedNoteId':selected}
