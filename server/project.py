"""Portable data-only projects. Rebuild notation; never accept embedded HTML/XML."""
import math
import re
from .editing import notes_checked, score_for_request
from .basic_harmony import generate_basic_harmony
from .chord_score import engrave_block_chords

PROJECT_LIMIT=32*1024*1024
INSTRUMENTS={'piano','guitar-nylon','cello','flute','harp','organ','violin','clarinet','bassoon','trumpet','trombone','xylophone'}

def number(value,low,high):
    if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:raise ValueError('Invalid project number.')
    return value

def index(value,length,allow_none=False):
    if type(value)!=int or not (-1 if allow_none else 0)<=value<length:raise ValueError('Invalid project selection.')
    return value

def restore_texture(item,score,harmony):
    if not isinstance(item,dict) or item.get('sourceFingerprint')!=score['scoreFingerprint'] or item.get('harmonyFingerprint')!=harmony['fingerprint']:raise ValueError('The saved accompaniment does not match this score.')
    if not isinstance(item.get('fingerprint'),str) or not re.fullmatch('[a-f0-9]{64}',item['fingerprint']):raise ValueError('Invalid accompaniment identity.')
    events=item.get('events');written=item.get('writtenChords')
    if not isinstance(events,list) or not isinstance(written,list) or len(events)!=len(written) or len(events)>20000:raise ValueError('Invalid saved accompaniment.')
    settings=item.get('settings',{})
    if settings.get('style') not in ('lyrical','flowing','syncopated') or type(settings.get('density'))!=int or settings['density'] not in (0,1,2) or type(settings.get('variant'))!=int or settings['variant'] not in (0,1,2) or settings.get('voicing','compact') not in ('compact','layered'):raise ValueError('Invalid arrangement settings.')
    choices={c['id']:c for c in harmony['choices']};ids=set();last={};last_tick={};clean_events=[];clean_written=[]
    for e,n in zip(events,written):
        if not isinstance(e,dict) or not isinstance(n,dict):raise ValueError('Invalid saved accompaniment.')
        identity=e.get('id');voice=e.get('voice',2);pitches=e.get('pitches')
        if not isinstance(identity,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',identity) or identity in ids or type(voice)!=int or voice not in (2,3,4):raise ValueError('Invalid accompaniment note.')
        start=number(e.get('start'),0,score['duration']);end=number(e.get('end'),start,score['duration'])
        a=number(n.get('startTick'),0,score['measures'][-1]['endTick']);b=number(n.get('endTick'),a,score['measures'][-1]['endTick'])
        if start>=end or a>=b or a!=int(a) or b!=int(b) or start<last.get(voice,0)-1e-6 or a<last_tick.get(voice,0):raise ValueError('Invalid or overlapping accompaniment notes.')
        if not isinstance(pitches,list) or not 1<=len(pitches)<=3 or any(type(p)!=int or not 0<=p<=127 for p in pitches) or n.get('pitches')!=pitches or n.get('id')!=identity or n.get('voice',2)!=voice:raise ValueError('Invalid accompaniment pitches.')
        if n.get('chordId') not in choices or any(p%12 not in choices[n['chordId']]['pitchClasses'] for p in pitches):raise ValueError('Accompaniment pitches conflict with the saved chord.')
        velocity=number(e.get('velocity',.55),0,1)
        clean_events.append({'id':identity,'start':start,'end':end,'staff':2,'voice':voice,'pitches':pitches,'velocity':velocity})
        clean_written.append({'id':identity,'startTick':a,'endTick':b,'staff':2,'voice':voice,'pitches':pitches,'velocity':velocity,'chordId':n['chordId'],'showChord':bool(n.get('showChord',True))})
        ids.add(identity);last[voice]=end;last_tick[voice]=b
    xml,fragments=engrave_block_chords(score,clean_written,harmony['choices'],'Piano arrangement')
    # Provenance is inert bounded JSON; it cannot choose a local model or file path.
    return {**{k:item.get(k) for k in ('sourceFingerprint','harmonyFingerprint','fingerprint','model','references','generationSeconds')},'settings':settings,'events':clean_events,'writtenChords':clean_written,'xml':xml,'chordFragments':fragments}

def normalize_project(payload):
    if not isinstance(payload,dict) or payload.get('kind')!='audio-converter-project' or payload.get('schemaVersion')!=1:raise ValueError('Unsupported project format.')
    source=payload.get('source')
    if not isinstance(source,dict):raise ValueError('Project source is missing.')
    duration=number(source.get('duration'),.001,7200)
    sha=source.get('sourceSha256')
    if not isinstance(sha,str) or not re.fullmatch('[a-f0-9]{64}',sha):raise ValueError('Invalid source identity.')
    name=source.get('name')
    if not isinstance(name,str) or not 1<=len(name)<=255 or any(ord(c)<32 for c in name) or '/' in name or '\\' in name:raise ValueError('Invalid source name.')
    original={'duration':duration,'notes':notes_checked(source.get('notes'),duration),'engine':'game','engineSignature':source.get('engineSignature'),'sourceSha256':sha}
    params={k:source.get(k) for k in ('bpm','meter','key')}
    root=score_for_request(original,params);root['sourceName']=name
    if source.get('scoreFingerprint')!=root['scoreFingerprint']:raise ValueError('The original score identity does not match. This project may be damaged or from an incompatible version.')
    saved=payload.get('versions')
    if not isinstance(saved,list) or not 1<=len(saved)<=32:raise ValueError('Invalid score versions (maximum 32).')
    versions=[]
    for i,v in enumerate(saved):
        if not isinstance(v,dict):raise ValueError('Invalid score version.')
        score=score_for_request(original,{**params,'editedNotes':v.get('editedNotes'),'anchorNoteId':v.get('anchorNoteId')});score['sourceName']=name
        if i==0 and score['scoreFingerprint']!=root['scoreFingerprint']:raise ValueError('The first version must preserve the original GF score.')
        h=v.get('harmony');harmony=None
        if h is not None:
            if not isinstance(h,dict):raise ValueError('Invalid harmony plan.')
            harmony=generate_basic_harmony(score,h.get('locks'),h.get('phraseStarts'),h.get('chordOffsetMs',0))
            if h.get('fingerprint')!=harmony['fingerprint']:raise ValueError('The saved harmony identity does not match.')
        versions.append({'score':score,'harmony':harmony,'kind':'original' if i==0 else ('edit' if v.get('kind')=='edit' else 'rebar')})
    textures={};sets=payload.get('textureSets',{})
    if not isinstance(sets,dict) or len(sets)>32:raise ValueError('Too many accompaniment sets.')
    valid={f"{i}:{v['harmony']['fingerprint']}":v for i,v in enumerate(versions) if v['harmony']}
    for key,value in sets.items():
        if key not in valid or not isinstance(value,dict):raise ValueError('Invalid accompaniment version.')
        items=value.get('items');v=valid[key]
        if not isinstance(items,list) or len(items)>12:raise ValueError('Too many saved arrangements (maximum 12 per version).')
        textures[key]={'items':[restore_texture(item,v['score'],v['harmony']) for item in items],'active':index(value.get('active'),len(items),True)}
    selected=index(payload.get('activeVersion'),len(versions))
    instruments=payload.get('instruments',['piano','piano']);voices=payload.get('voices',[True,True])
    if not isinstance(instruments,list) or len(instruments)!=2 or any(not isinstance(i,str) or i not in INSTRUMENTS for i in instruments):raise ValueError('Invalid instruments.')
    if not isinstance(voices,list) or len(voices)!=2 or any(type(v)!=bool for v in voices):raise ValueError('Invalid voice selection.')
    loop=payload.get('loop',{'enabled':False,'startMeasure':1,'endMeasure':1});bars=len(versions[selected]['score']['measures'])
    if not isinstance(loop,dict) or type(loop.get('enabled'))!=bool:raise ValueError('Invalid loop.')
    a=number(loop.get('startMeasure'),1,bars);b=number(loop.get('endMeasure'),a,bars)
    if a!=int(a) or b!=int(b):raise ValueError('Invalid loop measures.')
    levels=payload.get('levels',[60,40])
    if not isinstance(levels,list) or len(levels)!=2:raise ValueError('Invalid voice levels.')
    levels=[number(n,0,100) for n in levels]
    workspace={'versions':versions,'activeVersion':selected,'textureSets':textures,'instruments':instruments,'voices':voices,'levels':levels,'position':number(payload.get('position',0),0,duration),'loop':loop}
    return original,root,workspace
