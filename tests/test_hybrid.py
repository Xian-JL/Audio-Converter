import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
from server.melody_score import generate_melody_score
from server.adaptive_harmony import generate,palette,POLICY
from server.instrumental import sections,selected_sections
from server.hybrid import compose_result,generate as compose
from server.project import normalize_project,restore_texture
from server import app as service

PARAMS={'bpm':120,'meter':'4/4','key':'C major'}


def material(duration=20):
    raw={'engine':'game','sourceSha256':'a'*64,'engineSignature':{'test':'fixed'},'duration':duration,
         'notes':[{'id':'gf-1','start':4.,'end':7.,'midi':60,'midiFloat':60.}, {'id':'gf-2','start':12.,'end':13.9,'midi':67,'midiFloat':67.}]}
    score=generate_melody_score(raw,**PARAMS);return raw,score,generate(score)


class HybridTests(unittest.TestCase):
    def test_variable_harmonic_rhythm_and_extended_palette_are_deterministic(self):
        notes=[{'start':i/6,'end':i/6+.15,'midi':p} for i,p in enumerate([60,64,67,60,64,67,71,62,65,71,62,65])]
        score=generate_melody_score({'duration':4,'notes':notes},**PARAMS);before=copy.deepcopy(score);h=generate(score)
        self.assertEqual(h,generate(score));self.assertEqual(score,before)
        first=[s for s in h['segments'] if s['number']==1]
        self.assertGreater(len(first),1);self.assertNotEqual(first[0]['chordId'],first[-1]['chordId'])
        self.assertEqual(first[0]['startTick'],0);self.assertEqual(first[-1]['endTick'],128)
        qualities={c['quality'] for c in palette('C major')};self.assertTrue({'maj7','min7','7','dim','dim7','half-dim7'}<=qualities)
        for n in h['events']:
            self.assertTrue(3<=len(n['pitches'])<=4)
        root=ET.fromstring(h['xml']);old=ET.fromstring(score['xml'])
        self.assertEqual([ET.tostring(n) for n in old.findall('.//note')],[ET.tostring(n) for n in root.findall('.//note[staff="1"]')])

    def test_sevenths_segment_locks_and_exact_timing(self):
        _,s,_=material();h=generate(s,segment_locks={'3:256:320':'1:maj7','3:320:384':'7h:dim7'})
        local=[u for u in h['segments'] if u['number']==3]
        self.assertEqual([u['chordId'] for u in local],['1:maj7','7h:dim7']);self.assertTrue(all(u['locked'] for u in local))
        self.assertEqual(h['segmentLocks'],{'3:256:320':'1:maj7','3:320:384':'7h:dim7'})
        self.assertIn('major-seventh',h['xml']);self.assertIn('diminished-seventh',h['xml'])
        for bad in ({'3:1:320':'1:maj7'},{'3:256:320':'wrong'},{'3:256:384':'1:maj7','3:320:384':'5:7'}):
            with self.assertRaises(ValueError):generate(s,segment_locks=bad)
        shifted=generate(s,chord_offset_ms=-250)
        normal=generate(s)
        for a,b in zip(normal['events'],shifted['events']):self.assertAlmostEqual(a['start']-b['start'],.25)

    def test_two_complete_empty_bars_required_and_sustains_are_not_gaps(self):
        _,score,h=material();gaps=sections(score,h)
        self.assertEqual([(g['kind'],g['firstMeasure'],g['lastMeasure']) for g in gaps],[('intro',1,2),('interlude',5,6),('outro',8,10)])
        self.assertNotIn(4,[n for s in gaps for n in range(s['firstMeasure'],s['lastMeasure']+1)])
        _,short,hs=material(19)
        self.assertEqual(sections(short,hs)[-1]['lastMeasure'],9) # incomplete final bar excluded
        for request in ([],[{'firstMeasure':1,'lastMeasure':1}],[{'firstMeasure':True,'lastMeasure':2}],[{'firstMeasure':1,'lastMeasure':3}],[{'firstMeasure':1,'lastMeasure':2}]*2):
            with self.assertRaises(ValueError):selected_sections(score,h,request)

    def test_new_result_has_only_blocks_under_vocals_and_free_music_in_both_staves(self):
        _,s,h=material();before=copy.deepcopy((s,h));regions=selected_sections(s,h,[{'firstMeasure':1,'lastMeasure':2}])
        notes=[{'start':.03,'end':1.21,'midi':72},{'start':.03,'end':1.21,'midi':43},{'start':1.5,'end':3.9,'midi':65}]
        with patch('server.amt_model.infer_instrumental',return_value=(notes,[],{'version':'test'})) as infer:
            result=compose(s,h,3,provided=[{'firstMeasure':1,'lastMeasure':2}]);infer.assert_called_once()
        self.assertEqual(before,(s,h));self.assertEqual(result['settings']['mode'],'hybrid-v1')
        fill=[e for e in result['events'] if e['role']=='instrumental']
        self.assertEqual({e['staff'] for e in fill},{1,2})
        for voice in {e['voice'] for e in fill}:self.assertEqual(len({e['staff'] for e in fill if e['voice']==voice}),1)
        self.assertEqual(sorted((e['start'],e['end'],p) for e in fill for p in e['pitches']),sorted((n['start'],n['end'],n['midi']) for n in notes))
        self.assertEqual({e['id'] for e in result['events'] if e['role']=='block'},{e['id'] for e in h['events']})
        self.assertEqual(restore_texture(result,s,h)['events'],result['events'])
        root=ET.fromstring(result['xml'])
        for index,measure in enumerate(root.findall('./part/measure')):
            for voice in {n.findtext('voice') for n in measure.findall('note')}:
                self.assertEqual(sum(int(n.findtext('duration')) for n in measure.findall('note') if n.findtext('voice')==voice and n.find('chord') is None),s['measures'][index]['endTick']-s['measures'][index]['startTick'])
        for damage in ('outside','staff','block','missing'):
            bad=copy.deepcopy(result)
            if damage=='outside':bad['events'][0]['end']=6
            elif damage=='staff':bad['events'][0]['staff']=3
            elif damage=='block':next(e for e in bad['events'] if e['role']=='block')['pitches']=[0]
            else:
                i=next(i for i,e in enumerate(bad['events']) if e['role']=='block');bad['events'].pop(i);bad['writtenChords'].pop(i)
            with self.assertRaises(ValueError):restore_texture(bad,s,h)
        with self.assertRaises(ValueError):compose_result(s,h,[{'start':3.9,'end':5.,'midi':72}],regions,1,{},[],0)

    def test_project_roundtrip_without_model_and_legacy_project_still_opens(self):
        raw,s,h=material();region=selected_sections(s,h,[{'firstMeasure':1,'lastMeasure':2}])
        take=compose_result(s,h,[{'start':.1,'end':3.8,'midi':72}],region,1,{},[],0)
        payload={'kind':'audio-converter-project','schemaVersion':1,'source':{**raw,**PARAMS,'name':'synthetic.flac','scoreFingerprint':s['scoreFingerprint'],'identityNotesJson':s['identityNotesJson']},
                 'versions':[{'harmony':{'fingerprint':h['fingerprint'],'harmonyPolicy':POLICY,'segmentLocks':{},'locks':{},'phraseStarts':h['phraseStarts'],'chordOffsetMs':0}}],
                 'activeVersion':0,'textureSets':{f"0:{h['fingerprint']}":{'items':[take],'active':0}}}
        with patch('server.amt_model.infer_instrumental',side_effect=AssertionError('must not regenerate')):
            _,root,workspace=normalize_project(payload)
        self.assertEqual(root['events'],s['events']);self.assertEqual(next(iter(workspace['textureSets'].values()))['items'][0]['events'],take['events'])
        legacy=Path('exports/AMT-呜-完整示例.acproject.json')
        if legacy.exists():
            original=json.loads(legacy.read_text(encoding='utf-8'));_,_,w=normalize_project(original)
            self.assertEqual(next(iter(w['textureSets'].values()))['items'][0]['events'],next(iter(original['textureSets'].values()))['items'][0]['events'])

    def test_api_rejects_vocal_fill_ranges_before_launching_model(self):
        raw,s,h=material();identifier='b'*32
        with tempfile.TemporaryDirectory() as temporary,patch.object(service,'RUNTIME',Path(temporary)),patch.dict(service.jobs,{},clear=True):
            directory=service.owned_dir(identifier);directory.mkdir();(directory/'analysis.json').write_text(json.dumps(raw),encoding='utf-8');service.jobs[identifier]={'analysisReady':True}
            client=service.app.test_client();body={**PARAMS,'sourceFingerprint':s['scoreFingerprint'],'identityNotesJson':s['identityNotesJson'],'harmonyPolicy':POLICY}
            response=client.post(f'/api/jobs/{identifier}/harmony',json=body);self.assertEqual(response.status_code,200,response.json)
            body['harmonyFingerprint']=response.json['fingerprint']
            with patch('server.app.run_texture',return_value={'accepted':True}) as worker:
                bad=client.post(f'/api/jobs/{identifier}/texture',json={**body,'sections':[{'firstMeasure':2,'lastMeasure':4}]})
                self.assertEqual(bad.status_code,400);worker.assert_not_called()
                ok=client.post(f'/api/jobs/{identifier}/texture',json={**body,'sections':[{'firstMeasure':1,'lastMeasure':2}]})
                self.assertEqual(ok.status_code,200,ok.json);worker.assert_called_once()


if __name__=='__main__':unittest.main()
