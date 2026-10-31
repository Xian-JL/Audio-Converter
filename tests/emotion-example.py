"""Real CPU comparison, preserving the confirmed GF and the original local examples."""
import copy
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server.project import normalize_project
from server.hybrid import generate

root=Path(__file__).resolve().parents[1];target=root/'exports/情感器乐-呜-对照示例.acproject.json'
if target.exists():raise SystemExit('Example already exists; preserve it and choose a new output before another generation.')
payload=json.loads((root/'exports/柱式与器乐-呜-示例.acproject.json').read_text(encoding='utf-8'))
_,_,workspace=normalize_project(payload);index=workspace['activeVersion'];version=workspace['versions'][index];score,harmony=version['score'],version['harmony']
before=copy.deepcopy(score['events']);takes=[];report=[]
for engine in ['emo','midi-emotion']:
    start=time.monotonic();last=0
    def progress(value):
        global last
        if time.monotonic()-last>5 or value.get('stage')=='loading':print(engine,json.dumps(value),flush=True);last=time.monotonic()
    settings={'engine':engine,'feeling':'sad','contour':'rising'}
    take=generate(score,harmony,20261030,progress,emotion=settings)
    assert score['events']==before
    takes.append({k:v for k,v in take.items() if k!='xml'})
    fills=[e for e in take['events'] if e['role']=='instrumental']
    report.append({'engine':engine,'seconds':round(time.monotonic()-start,3),'events':len(fills),'tones':sum(len(e['pitches']) for e in fills),'velocityRange':[min(e['velocity'] for e in fills),max(e['velocity'] for e in fills)],'emotion':settings,'unchangedGF':True})
    (root/f'tests/output/emotion-{engine}-events.json').write_text(json.dumps(take,ensure_ascii=False),encoding='utf-8')
    print('Completed',json.dumps(report[-1]),flush=True)
payload['appVersion']='0.7.0';payload['textureSets']={f"{index}:{harmony['fingerprint']}":{'items':takes,'active':0}}
_,_,restored=normalize_project(payload)
assert restored['versions'][index]['score']['events']==before
assert [t['events'] for t in next(iter(restored['textureSets'].values()))['items']]==[t['events'] for t in takes]
target.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
(root/'tests/output/emotion-real-checks.json').write_text(json.dumps({'results':report,'melodyNotes':430,'sections':harmony['instrumentalSections'],'projectRoundtrip':True},ensure_ascii=False,indent=2),encoding='utf-8')
print('Saved comparison project:',str(target),flush=True)
