import tempfile
import unittest
from pathlib import Path

from glide_arrangement.score import Note, Voice
from test_arrangement import HAS_AUDIO

@unittest.skipUnless(HAS_AUDIO, "Instala requirements-arrangement.txt")
class ArticulationTests(unittest.TestCase):
    def test_audio_distinguishes_retrigger_from_sustain(self):
        import numpy as np
        import soundfile as sf
        from glide_arrangement.articulation import extract_evidence, refine
        from glide_arrangement.articulation_metrics import repeated_attack_accuracy

        rate = 22050
        t = np.arange(3*rate)/rate
        carrier = np.sin(2*np.pi*261.6256*t) + .3*np.sin(4*np.pi*261.6256*t)
        for repeated in (False, True):
            with self.subTest(repeated=repeated), tempfile.TemporaryDirectory() as directory:
                env = np.clip((t-.2)/.025,0,1) * np.clip((2.7-t)/.2,0,1)
                if repeated:
                    env *= 1-.78*np.exp(-.5*((t-1.31)/.055)**2)
                path = Path(directory)/"fixture.wav"
                sf.write(path,.5*env*carrier,rate)
                original = Voice("keys","inner",[Note(60,.2,2.68)])
                output, events = refine([original],extract_evidence(path,{60}))
                expected = [{"type":"retrigger","voice":"keys","pitch":60,"time":1.39}] if repeated else []
                accuracy = repeated_attack_accuracy(expected,events)
                self.assertEqual(accuracy["matched"],len(expected),events)
                self.assertEqual(accuracy["predicted"],len(expected),events)
                self.assertEqual(len(output[0].notes),1+repeated)
                self.assertTrue(any(e["type"]=="release" and 2.43 < e["time"] < 2.65 for e in events),events)
                self.assertEqual(original.notes,[Note(60,.2,2.68)])

    def test_rejoins_false_break_and_keeps_legato(self):
        import numpy as np
        from glide_arrangement.articulation import Evidence, refine
        t = np.linspace(0,3,601)
        stationary = Evidence(t,np.ones_like(t),np.zeros_like(t))
        voice = Voice("inner","inner",[Note(60,.2,.9),Note(60,.95,1.54),Note(62,1.51,2.7)])
        output, events = refine([voice],{60:stationary,62:stationary})
        self.assertEqual(output[0].notes,[Note(60,.2,1.54),Note(62,1.51,2.7)])
        self.assertEqual([event["type"] for event in events],["sustain","legato"])
