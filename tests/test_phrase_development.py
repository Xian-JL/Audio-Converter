import importlib.util
import unittest
from server.phrase_development import roles,boundary_harmonies,pitch_penalty,repeated_bar,note_signature
from server.emotional_score import lead_bar,lead_notes,performance_bar


class PhraseDevelopmentTests(unittest.TestCase):
    def test_directional_entry_and_exit_and_phrase_roles(self):
        h={'bars':[{'start':0,'end':4,'pitches':[48,52,55]},{'start':12,'end':16,'pitches':[52,55,59]}]}
        entry,exit=boundary_harmonies(h,{'start':4,'end':12})
        self.assertEqual(entry['pitches'],[48,52,55]);self.assertEqual(exit['pitches'],[52,55,59])
        self.assertEqual(roles(3),['statement','development','resolution']);self.assertEqual(roles(2),['statement','resolution'])
        h['bars'][0].update(end=7,playEnd=4);h['bars'][1].update(start=10,playStart=12)
        entry,exit=boundary_harmonies(h,{'start':4,'end':12});self.assertEqual(entry['pitches'],[48,52,55]);self.assertEqual(exit['pitches'],[52,55,59])

    def test_cycles_receive_soft_penalty_but_single_motif_is_allowed(self):
        history=[64,62,64,62,64]
        self.assertGreater(pitch_penalty(62,history),pitch_penalty(65,history))
        self.assertEqual(pitch_penalty(62,[64]),0)
        self.assertFalse(repeated_bar(((0,4,64),(4,4,62)),[((0,4,64),(4,4,62))]))
        signature=((0,4,64),(4,4,62),(8,4,65))
        self.assertTrue(repeated_bar(signature,[signature]));self.assertFalse(repeated_bar(signature,[((0,4,64),(4,4,62),(8,8,65))]))

    def test_bass_ostinato_under_sustained_melody_is_not_a_melody_loop(self):
        notes=[{'start':0,'end':4,'midi':72}]+[{'start':i/2,'end':i/2+.4,'midi':48} for i in range(8)]
        self.assertEqual(note_signature(notes,0,4),((0,16,72),))
        notes += [{'start':1,'end':2,'midi':60},{'start':2,'end':3,'midi':59}]
        self.assertEqual(note_signature(notes,0,4),((0,16,72),))

    @unittest.skipUnless(importlib.util.find_spec('torch'),'Optional local inference dependency')
    def test_lead_decoder_cannot_stack_repeated_notes_at_one_position(self):
        import torch
        from server.emotion_runtime import ROOT
        import json
        vocab=json.loads((ROOT/'server/data/emo-stage1-vocabulary.json').read_text(encoding='utf-8'));e2i={v:i for i,v in enumerate(vocab)}
        def logits(tokens):
            result=torch.full((len(vocab)+1,),-40.)
            for word,score in [('Note_Octave_4',40),('Note_Degree_I',40),('Note_Duration_480',40),('Beat_4',30),('Beat_8',15),('Beat_12',0),('Bar_None',-10)]:result[e2i[word]]=score
            return result
        bar=lead_bar(logits,[e2i['Emotion_Negative'],e2i['Key_C']],vocab,'C major',torch.Generator().manual_seed(3))
        self.assertEqual(bar[:2],['Bar_None','Beat_0'])
        notes=lead_notes(bar,'C major');self.assertEqual(len(notes),4)
        self.assertEqual([p for p,_,_ in notes],[0,4,8,12])
        for a,b in zip(notes,notes[1:]):self.assertLessEqual(a[0]+a[1],b[0])

    @unittest.skipUnless(importlib.util.find_spec('torch'),'Optional local inference dependency')
    def test_performance_decoder_never_duplicates_a_pitch_at_the_same_onset(self):
        import torch,json
        from server.emotion_runtime import ROOT
        vocab=json.loads((ROOT/'server/data/emo-stage2-vocabulary.json').read_text(encoding='utf-8'));e2i={v:i for i,v in enumerate(vocab)}
        def logits(tokens,segments):
            result=torch.full((len(vocab)+1,),-40.)
            for word,score in [('Note_Octave_4',40),('Note_Degree_I',40),('Note_Duration_480',40),('Note_Velocity_64',40),('Track_LeadSheet',35)]:result[e2i[word]]=score
            return result
        notes,_,_=performance_bar(logits,[e2i['Emotion_Q2'],e2i['Key_C']],[0,0],vocab,'C major',torch.Generator().manual_seed(4),0,[{'playStart':0.,'playEnd':4.}],{'bpm':60,'contour':'rising'},[],'development',[(0,4,60)],())
        self.assertGreater(len(notes),1)
        self.assertEqual(len(notes),len({(n['start'],n['midi']) for n in notes}))
        self.assertLessEqual(max(n['midi'] for n in notes),72)


if __name__=='__main__':unittest.main()
