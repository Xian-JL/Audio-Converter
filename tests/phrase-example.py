"""Package a validated real regenerated interlude, preserving the original intro."""
import copy
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server.project import normalize_project,restore_texture
from server.phrase_development import note_signature,diagnostics

root=Path(__file__).resolve().parents[1];target=root/'exports/EMO-呜-乐句发展示例.acproject.json'
if target.exists():raise SystemExit('Example already exists; preserve it before creating another.')
payload=json.loads((root/'exports/情感器乐-呜-对照示例.acproject.json').read_text(encoding='utf-8'))
_,_,workspace=normalize_project(payload);version=workspace['versions'][workspace['activeVersion']];score,harmony=version['score'],version['harmony']
key=next(iter(payload['textureSets']));base=payload['textureSets'][key]['items'][0]
generated=json.loads((root/'tests/output/emo-development-probe.json').read_text(encoding='utf-8'));restore_texture(generated,score,harmony)
assert generated['model']['development']=='phrase-development-v1'
ranges=[r for r in harmony['instrumentalSections'] if r['kind']=='interlude'];assert len(ranges)==1;region=ranges[0]
outside=lambda e:e['end']<=region['start'] or e['start']>=region['end']
pairs=[(copy.deepcopy(e),copy.deepcopy(n)) for e,n in zip(base['events'],base['writtenChords']) if e['role']=='block' or outside(e)]
staff_voices={1:[],2:[]}
for e,_ in pairs:
    if e['voice']>=3 and e['voice'] not in staff_voices[e['staff']]:staff_voices[e['staff']].append(e['voice'])
used={e['voice'] for e,_ in pairs};voice_map={};usage={1:0,2:0}
for e,n in zip(generated['events'],generated['writtenChords']):
    if e['role']!='instrumental':continue
    assert region['start']<=e['start']<e['end']<=region['end']+1e-7
    e,n=copy.deepcopy(e),copy.deepcopy(n);old_voice=e['voice'];staff=e['staff']
    if old_voice not in voice_map:
        i=usage[staff];usage[staff]+=1
        if i<len(staff_voices[staff]):voice_map[old_voice]=staff_voices[staff][i]
        else:
            voice_map[old_voice]=max(used)+1;used.add(voice_map[old_voice])
    identity=f"fill-development-{len(pairs)+1}"
    for item in (e,n):item['voice']=voice_map[old_voice];item['id']=identity
    pairs.append((e,n))
pairs.sort(key=lambda pair:(pair[0]['start'],pair[0]['voice'],pair[0]['id']))
take=copy.deepcopy(generated);take['events']=[e for e,_ in pairs];take['writtenChords']=[n for _,n in pairs]
take['settings']['sections']=copy.deepcopy(base['settings']['sections'])
take['model']={**take['model'],'baseFingerprint':base['fingerprint'],'regeneratedSections':[{k:region[k] for k in ('firstMeasure','lastMeasure')}]}
take['references']=[r for r in base['references'] if r.get('kind')!='interlude']+generated['references']
identity={'version':take['settings']['mode'],'harmony':harmony['fingerprint'],'settings':take['settings'],'events':take['events'],'model':take['model']}
take['fingerprint']=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
take=restore_texture(take,score,harmony)
original_outside=[e for e in base['events'] if e['role']=='block' or outside(e)]
assert [e for e in take['events'] if e['role']=='block' or outside(e)]==original_outside
assert len({(e['start'],p) for e in take['events'] if e['role']=='instrumental' for p in e['pitches']})==sum(len(e['pitches']) for e in take['events'] if e['role']=='instrumental')
payload['appVersion']='0.7.1';payload['textureSets'][key]['items'].append({k:v for k,v in take.items() if k!='xml'});payload['textureSets'][key]['active']=2
_,_,restored=normalize_project(payload);assert restored['versions'][workspace['activeVersion']]['score']['events']==score['events']
target.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
def metrics(item):
    signatures=[]
    for bar in harmony['bars'][region['firstMeasure']-1:region['lastMeasure']]:
        notes=[{'start':e['start'],'end':e['end'],'midi':p} for e in item['events'] if e['role']=='instrumental' and bar['playStart']<=e['start']<bar['playEnd'] for p in e['pitches']]
        signatures.append(note_signature(notes,bar['playStart'],bar['playEnd']))
    return diagnostics(signatures)
report={'old':metrics(base),'new':metrics(take),'outsideUnchanged':True,'unchangedGF':True,'oldCandidatesRetained':2,'newCandidate':2,'phrases':generated['references'][0]['phrases']}
(root/'tests/output/phrase-development-checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False),flush=True)
