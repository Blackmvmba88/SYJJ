import unittest

from glide_arrangement.score import Note, Voice
from test_arrangement import HAS_AUDIO

@unittest.skipUnless(HAS_AUDIO,"Instala requirements-arrangement.txt")
class DurationTests(unittest.TestCase):
    def test_keeps_onset_and_pitch_and_separates_tail(self):
        import numpy as np
        from glide_arrangement.articulation import Evidence
        from glide_arrangement.duration import refine_duration

        t = np.arange(0,2,.005)
        energy = np.exp(-.20*t-10*np.maximum(t-1,0))
        curve = Evidence(t,energy,np.zeros_like(t),np.array([energy,.35*energy]))
        note = Note(60,.12,1.28,89)
        original = Voice("v","inner",[note],instrument="keys")
        output, decisions = refine_duration([original],{60:curve},"piano")
        refined = output[0].notes[0]
        self.assertAlmostEqual(refined.end,1,delta=.035)
        self.assertEqual((refined.pitch,refined.start,refined.velocity),(60,.12,89))
        self.assertEqual(original.notes,[note])
        self.assertGreater(decisions[0]["tail_seconds"],.1)
        self.assertGreater(decisions[0]["acoustic_end"],refined.end)

    def test_ambiguous_decay_preserves_a(self):
        import numpy as np
        from glide_arrangement.articulation import Evidence
        from glide_arrangement.duration import refine_duration

        t = np.arange(0,2,.005)
        energy = np.exp(-5*t)
        curve = Evidence(t,energy,np.zeros_like(t),np.array([energy,.3*energy]))
        voice = Voice("v","inner",[Note(60,.1,1.3)])
        output, decisions = refine_duration([voice],{60:curve})
        self.assertEqual(output,[voice])
        self.assertEqual(decisions,[])
