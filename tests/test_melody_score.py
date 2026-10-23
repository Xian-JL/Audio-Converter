import json
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from server.melody_score import generate_melody_score

ROOT=Path(__file__).resolve().parents[1]

class MelodyScoreTests(unittest.TestCase):
    def test_real_gf_outputs_preserve_every_note_and_fill_one_staff_measures(self):
        for case,bpm in [('unsaid',100),('the-ember',68)]:
            data=json.loads((ROOT/f'tests/fixtures/{case}-gf.json').read_text(encoding='utf-8'))
            result={'duration':data['duration'],'notes':[{'start':e['start'],'end':e['end'],'midi':e['pitches'][0]} for e in data['events']], 'sourceSha256':data['vocalFileSha256'],'engineSignature':{'test':'fixed'}}
            score=generate_melody_score(result,bpm,'4/4','C major')
            self.assertEqual(score['noteCount'],len(data['events']))
            self.assertEqual([(e['start'],e['end'],e['pitches']) for e in score['events']],[(e['start'],e['end'],e['pitches']) for e in data['events']])
            self.assertEqual({e['staff'] for e in score['events']},{1})
            root=ET.fromstring(score['xml']);self.assertEqual(root.findtext('.//staves'),'1');self.assertIsNone(root.find('.//backup'))
            self.assertEqual(root.findtext('.//clef/clef-octave-change'),'-1')
            natural={'C':0,'D':2,'E':4,'F':5,'G':7,'A':9,'B':11}
            for xml_note,fragment in zip(root.findall('.//note[pitch]'),score['fragments']):
                pitch=xml_note.find('pitch')
                sounding=(int(pitch.findtext('octave'))+1)*12+natural[pitch.findtext('step')]+int(pitch.findtext('alter','0'))
                self.assertEqual(sounding,fragment['midi'])
            ids={n['id'] for n in score['notes']};self.assertEqual(ids,{f['noteId'] for f in score['fragments']})
            for measure in root.findall('.//measure'):
                self.assertEqual(sum(int(n.findtext('duration')) for n in measure.findall('note')),128)
            self.assertTrue(all(a['endTick']<=b['startTick'] for a,b in zip(score['notes'],score['notes'][1:])))
            self.assertEqual(len(ids),len(score['notes']))
            self.assertNotEqual(score['scoreFingerprint'],generate_melody_score(result,bpm+1,'4/4','C major')['scoreFingerprint'])

    def test_repeated_short_notes_and_cross_bar_ties_share_logical_ids(self):
        data={'duration':4.5,'notes':[{'start':.2,'end':.23,'midi':64},{'start':.24,'end':.27,'midi':64},{'start':1.8,'end':3.4,'midi':62}]}
        score=generate_melody_score(data,120,'4/4','C major')
        self.assertEqual(score['noteCount'],3)
        self.assertEqual(len({n['id'] for n in score['notes']}),3)
        ties=[f for f in score['fragments'] if f['noteId']=='gf-000003']
        self.assertGreater(len(ties),1)
        self.assertTrue(all(e['end']>e['start'] for e in score['notatedEvents']))
        for meter,bar in [('3/4',96),('6/8',96),('5/4',160)]:
            xml=ET.fromstring(generate_melody_score(data,120,meter,'D minor')['xml'])
            self.assertTrue(all(sum(int(n.findtext('duration')) for n in m.findall('note'))==bar for m in xml.findall('.//measure')))

    def test_empty_score_and_invalid_notes(self):
        score=generate_melody_score({'duration':3,'notes':[]},68,'4/4','C major')
        self.assertEqual(score['noteCount'],0)
        self.assertTrue(all(n.get('print-object')=='no' for n in ET.fromstring(score['xml']).findall('.//note')))
        with self.assertRaises(ValueError):generate_melody_score({'duration':1,'notes':[{'start':0,'end':2,'midi':60}]},68,'4/4','C major')

    def test_dense_rearticulation_in_slow_meter_uses_finer_lattice(self):
        score=generate_melody_score({'duration':.4,'notes':[{'start':i*.05,'end':i*.05+.04,'midi':60} for i in range(8)]},30,'4/4','C major')
        self.assertEqual(score['divisions'],64)
        self.assertEqual(score['noteCount'],8)
        self.assertTrue(all(n['endTick']>n['startTick'] for n in score['notes']))

if __name__=='__main__':unittest.main()
