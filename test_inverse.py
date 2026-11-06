import unittest

from glide_arrangement.score import Note, Voice
from test_arrangement import HAS_AUDIO

@unittest.skipUnless(HAS_AUDIO,"Instala requirements-arrangement.txt")
class InverseTests(unittest.TestCase):
    def test_refines_wrong_pitch_inside_mix_without_editing_a(self):
        import numpy as np
        from glide_arrangement.instrument import GRID, Profile, render_profile
        from glide_arrangement.inverse import refine_score
        from glide_arrangement.spectrotemporal import RATE

        fundamental = np.full(len(GRID),.18)
        envelope = np.array([fundamental/(i+1)**2 for i in range(8)]).tolist()
        profile = Profile("piano",{55:envelope,72:envelope})
        truth = Voice("v","inner",[Note(60,.20,.61),Note(67,.24,.69)])
        audio = render_profile(profile,[truth],length=RATE)
        baseline = Voice("v","inner",[Note(61,.20,.61),Note(67,.24,.69)])
        output, edits = refine_score(audio,profile,[baseline],modes=("pitch",),passes=1)
        self.assertEqual(output[0].notes,truth.notes)
        self.assertEqual(baseline.notes[0].pitch,61)
        self.assertEqual([e["operation"] for e in edits],["pitch"])

    def test_velocity_modes_change_shape_only_when_allowed(self):
        import numpy as np
        from glide_arrangement.instrument import GRID
        from glide_arrangement.velocity import fit_velocity

        examples = []
        for pitch in (55,65):
            for velocity in (25,75,127):
                matrix = np.ones((8,len(GRID)))*(.05+velocity/1000)
                matrix[1] *= velocity/75*(1+GRID)
                examples.append((pitch,velocity,matrix))
        model = fit_velocity(examples)
        ratios = lambda method,vel: model.predict(60,vel,method)[1,10]/model.predict(60,vel,method)[0,10]
        self.assertAlmostEqual(ratios("amplitude",50),ratios("amplitude",100))
        self.assertGreater(ratios("partials",100),ratios("partials",50))
        self.assertGreater(ratios("joint",100),ratios("joint",50))
