import unittest

from glide_arrangement.score import Note, Voice
from test_arrangement import HAS_AUDIO

@unittest.skipUnless(HAS_AUDIO, "Instala requirements-arrangement.txt")
class SelectiveTests(unittest.TestCase):
    def test_variants_isolate_edits_and_leave_uncertainty_in_a(self):
        import numpy as np
        from glide_arrangement.articulation import Evidence
        from glide_arrangement.selective import refine_selective

        time = np.arange(0,4,.005)
        level = np.ones_like(time)
        flat = Evidence(time,level,np.zeros_like(time),np.tile(level,(6,1)))
        pulse = np.exp(-.5*((time-2.50)/.012)**2)
        energy = 1-.95*np.exp(-.5*((time-2.44)/.045)**2)
        repeat = Evidence(time,energy,pulse,np.tile(energy,(6,1)))
        unknown = Evidence(time,level,np.zeros_like(time))
        original = Voice("v","inner",[Note(60,.1,.8),Note(60,.85,1.3),Note(62,2,3.1),
                                      Note(64,3.15,3.4),Note(64,3.44,3.8)])
        for variant, actions, count in (("B1",["sustain"],4),("B2",["retrigger"],6),
                                        ("B3",["sustain","retrigger"],5)):
            with self.subTest(variant=variant):
                out, audit = refine_selective([original],{60:flat,62:repeat,64:unknown},variant)
                self.assertEqual([e["type"] for e in audit],actions)
                self.assertEqual(len(out[0].notes),count)
                self.assertEqual(out[0].notes[-2:],original.notes[-2:])
        self.assertEqual(len(original.notes),5)
