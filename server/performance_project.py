"""Schema 3 instrument projects reopen without running a model or trusting XML."""
import re
from .performance_score import checked_notes, checked_controllers, generate


def restore(payload):
    from .project import number,index,ensembles_checked,INSTRUMENTS,restore_texture
    from .basic_harmony import harmony_for_settings
    source=payload.get('source')
    if not isinstance(source,dict) or source.get('sourceKind') not in ('piano','guzheng'):raise ValueError('Invalid instrument project source.')
    duration=number(source.get('duration'),.001,7200);name=source.get('name');sha=source.get('sourceSha256')
    if not isinstance(name,str) or not 1<=len(name)<=255 or any(ord(c)<32 for c in name) or '/' in name or '\\' in name:raise ValueError('Invalid source name.')
    if not isinstance(sha,str) or not re.fullmatch('[a-f0-9]{64}',sha):raise ValueError('Invalid source hash.')
    original={'duration':duration,'sourceSha256':sha,'sourceKind':source['sourceKind'],'engine':source.get('engine'),'engineSignature':source.get('engineSignature'),'notes':checked_notes(source.get('notes'),duration)}
    if original['engine'] not in ('transkun','basic-pitch'):raise ValueError('Unknown instrument engine.')
    if source.get('baselineNotes') is not None:original['baselineNotes']=checked_notes(source['baselineNotes'],duration)
    original['controllers']=checked_controllers(source.get('controllers',[]),duration)
    params={k:source.get(k) for k in ('bpm','meter','key')};root=generate(original,params);root['sourceName']=name
    if root['scoreFingerprint']!=source.get('scoreFingerprint'):raise ValueError('Instrument source identity does not match.')
    saved=payload.get('versions')
    if not isinstance(saved,list) or not 1<=len(saved)<=32:raise ValueError('Invalid score versions.')
    versions=[]
    for i,v in enumerate(saved):
        if not isinstance(v,dict):raise ValueError('Invalid score version.')
        score=generate(original,{**params,**{k:v.get(k) for k in ('editedNotes','downbeats','anchorNoteId')},'scoreMode':v.get('scoreMode','performance')});score['sourceName']=name;score['melodyConfirmed']=v.get('melodyConfirmed') is True
        if i==0 and score['scoreFingerprint']!=root['scoreFingerprint']:raise ValueError('The original performance must be retained.')
        harmony=None
        if v.get('harmony') is not None:
            if score['scoreMode']!='melody' or not score['melodyConfirmed']:raise ValueError('Accompaniment requires a melody branch.')
            harmony=harmony_for_settings(score,v['harmony'])
            if harmony['fingerprint']!=v['harmony'].get('fingerprint'):raise ValueError('Harmony identity does not match.')
        versions.append({'score':score,'harmony':harmony,'kind':'original' if i==0 else ('edit' if v.get('kind')=='edit' else 'rebar')})
    active=index(payload.get('activeVersion'),len(versions));ensembles=ensembles_checked(payload.get('ensembles'),['piano','piano'])
    layout=payload.get('scoreLayout','compact')
    if layout not in ('compact','standard'):raise ValueError('Invalid layout.')
    voices=payload.get('voices',[True,True]);levels=payload.get('levels',[60,40])
    if not isinstance(voices,list) or len(voices)!=2 or any(type(x)!=bool for x in voices):raise ValueError('Invalid staff enable flags.')
    if not isinstance(levels,list) or len(levels)!=2:raise ValueError('Invalid staff levels.')
    levels=[number(x,0,100) for x in levels];loop=payload.get('loop',{'enabled':False,'startMeasure':1,'endMeasure':1})
    bars=len(versions[active]['score']['measures'])
    if not isinstance(loop,dict) or type(loop.get('enabled'))!=bool:raise ValueError('Invalid loop.')
    a=number(loop.get('startMeasure'),1,bars);b=number(loop.get('endMeasure'),a,bars)
    if a!=int(a) or b!=int(b):raise ValueError('Invalid loop range.')
    sets=payload.get('textureSets',{})
    if not isinstance(sets,dict) or len(sets)>32:raise ValueError('Invalid accompaniment sets.')
    valid={f"{i}:{v['harmony']['fingerprint']}":v for i,v in enumerate(versions) if v['harmony']};textures={}
    for k,value in sets.items():
        if k not in valid or not isinstance(value,dict) or not isinstance(value.get('items'),list) or len(value['items'])>12:raise ValueError('Invalid instrument accompaniment.')
        v=valid[k];items=[restore_texture(x,v['score'],v['harmony']) for x in value['items']];textures[k]={'items':items,'active':index(value.get('active'),len(items),True)}
    return original,root,{'versions':versions,'activeVersion':active,'textureSets':textures,'instruments':[e[0]['instrument'] for e in ensembles],'ensembles':ensembles,'scoreLayout':layout,'voices':voices,'levels':levels,'position':number(payload.get('position',0),0,duration),'loop':loop}
