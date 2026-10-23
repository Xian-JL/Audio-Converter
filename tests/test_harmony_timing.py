import copy
import unittest
import xml.etree.ElementTree as ET
from server.basic_harmony import generate_basic_harmony
from server.melody_score import generate_melody_score
from server.harmony_timing import interpolate

class HarmonyTimingTests(unittest.TestCase):
    def score(self):
        return generate_melody_score({'duration':8,'notes':[{'start':.03,'end':1.7,'midi':60},{'start':1.97,'end':3.7,'midi':64},{'start':4.03,'end':5.6,'midi':67},{'start':5.97,'end':7.8,'midi':65}]},120,'4/4','C major')

    def test_chords_follow_raw_gf_anchors_and_fixed_offset_is_exact(self):
        score=self.score();before=copy.deepcopy(score);locks={str(n):'1:major' for n in range(1,5)}
        normal=generate_basic_harmony(score,locks);earlier=generate_basic_harmony(score,locks,chord_offset_ms=-250)
        self.assertEqual(score,before)
        self.assertAlmostEqual(normal['events'][1]['start'],1.97)
        self.assertAlmostEqual(normal['events'][2]['start'],4.03)
        for n,e in zip(normal['events'][1:],earlier['events'][1:]):self.assertAlmostEqual(n['start']-e['start'],.25)
        self.assertEqual(earlier['events'][0]['start'],0)
        self.assertEqual([b['chordId'] for b in normal['bars']],[b['chordId'] for b in earlier['bars']])
        self.assertNotEqual(normal['fingerprint'],earlier['fingerprint'])
        self.assertEqual(earlier['alignment']['offsetMs'],-250)

    def test_aligned_event_and_written_onset_share_mapping(self):
        score=self.score();result=generate_basic_harmony(score,chord_offset_ms=-300)
        tick=60/score['bpm']/score['divisions'];anchors=result['alignment']['anchors']
        for event in result['writtenChords']:
            if event['start']>=anchors[0][1]:
                self.assertLessEqual(abs(interpolate(anchors,event['startTick']*tick)-event['start']),tick*1.5)
            else:self.assertEqual(event['startTick'],0)
        root=ET.fromstring(result['xml'])
        self.assertTrue(root.findall('.//note[staff="2"]/chord'))
        self.assertTrue(root.findall('.//note[staff="2"]/tie'))

    def test_clipping_extremes_and_meter_changes_keep_both_staves_complete(self):
        for meter in ('3/4','4/4','6/8','7/8'):
            score=generate_melody_score({'duration':8,'notes':[{'start':0,'end':7.8,'midi':60}]},120,meter,'C major')
            num,den=map(int,meter.split('/'));ticks=num*score['divisions']*4//den
            for offset in (-1999,-1,0,1,1999):
                h=generate_basic_harmony(score,chord_offset_ms=offset)
                for event in h['events']:self.assertTrue(0<=event['start']<event['end']<=8)
                for a,b in zip(h['writtenChords'],h['writtenChords'][1:]):self.assertLessEqual(a['endTick'],b['startTick'])
                for measure in ET.fromstring(h['xml']).findall('.//measure'):
                    for staff in ('1','2'):
                        self.assertEqual(sum(int(n.findtext('duration')) for n in measure.findall(f'note[staff="{staff}"]') if n.find('chord') is None),ticks)
        for offset in (True,None,[],float('nan'),2001,-2001):
            with self.assertRaises(ValueError):generate_basic_harmony(self.score(),chord_offset_ms=offset)

if __name__=='__main__':unittest.main()
