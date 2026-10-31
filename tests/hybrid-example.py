"""Create a new private local example using the saved GF, never rerun recognition."""
import copy
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server.project import normalize_project
from server.adaptive_harmony import generate,POLICY
from server.hybrid import generate as compose

root=Path(__file__).resolve().parents[1]
target=root/'exports/柱式与器乐-呜-示例.acproject.json'
if target.exists():raise SystemExit('Example already exists; keep it or choose a new filename before generating another.')
source=json.loads((root/'exports/AMT-呜-完整示例.acproject.json').read_text(encoding='utf-8'))
_,_,workspace=normalize_project(source);index=workspace['activeVersion'];score=workspace['versions'][index]['score'];before=copy.deepcopy(score['events'])
harmony=generate(score)
print(json.dumps({'blocks':len(harmony['events']),'sections':harmony['instrumentalSections']},ensure_ascii=False),flush=True)
started=time.monotonic();last=0
def progress(value):
    global last
    if time.monotonic()-last>5 or value.get('stage') in ('loading','retrying'):
        print(json.dumps(value),flush=True);last=time.monotonic()
take=compose(score,harmony,20261028,progress)
payload=copy.deepcopy(source);payload['appVersion']='0.6.0'
payload['versions'][index]['harmony']={'fingerprint':harmony['fingerprint'],'harmonyPolicy':POLICY,'locks':harmony['locks'],'segmentLocks':harmony['segmentLocks'],'phraseStarts':harmony['phraseStarts'],'chordOffsetMs':0}
payload['textureSets']={f"{index}:{harmony['fingerprint']}":{'items':[{k:v for k,v in take.items() if k!='xml'}],'active':0}}
_,_,restored=normalize_project(payload)
assert restored['versions'][index]['score']['events']==before
assert next(iter(restored['textureSets'].values()))['items'][0]['events']==take['events']
target.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
report={'seconds':round(time.monotonic()-started,3),'melodyNotes':len(before),'blockEvents':sum(e['role']=='block' for e in take['events']),'instrumentalEvents':sum(e['role']=='instrumental' for e in take['events']),'rightInstrumentalEvents':sum(e['role']=='instrumental' and e['staff']==1 for e in take['events']),'sections':take['settings']['sections'],'unchangedGF':True,'project':str(target)}
(root/'tests/output/hybrid-real-checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False),flush=True)
