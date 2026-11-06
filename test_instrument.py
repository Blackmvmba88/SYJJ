import unittest

from glide_arrangement.score import Note, Voice
from test_arrangement import HAS_AUDIO

@unittest.skipUnless(HAS_AUDIO,"Instala requirements-arrangement.txt")
class InstrumentTests(unittest.TestCase):
    def test_learned_partial_and_pedal_render_without_reference(self):
        import numpy as np
        from glide_arrangement.instrument import Profile, fit_profile, render_profile
        from glide_arrangement.spectrotemporal import RATE

        t = np.arange(RATE)/RATE
        phase = 2*np.pi*440*t
        isolated = .2*np.sin(phase)+.09*np.exp(-3*t)*np.sin(2*phase)
        profile = Profile.from_json(fit_profile(isolated,[Note(69,0,.96,80)],"piano").to_json())
        self.assertGreater(profile.notes[69][1][5],2*profile.notes[69][1][38])
        notes = [Note(69,.02,.25,80),Note(60,.1,.29,60)]
        voice = Voice("ch0","inner",notes)
        dry = render_profile(profile,[voice])
        pedaled = render_profile(profile,[voice],{"ch0":[(0,.70)]})
        self.assertEqual(voice.notes,notes)
        self.assertLess(len(dry),int(.51*RATE))
        self.assertGreater(np.linalg.norm(pedaled[int(.52*RATE):int(.65*RATE)]),1)

    def test_midi_import_preserves_velocity_and_channel_pedal(self):
        import importlib.util
        if importlib.util.find_spec("mido") is None:
            self.skipTest("Instala requirements-arrangement.txt")
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from glide_arrangement.instrument import read_midi
        from glide_arrangement.render import render_midi

        original = Voice("source","inner",[Note(60,.25,.5,96),Note(67,.35,.65,61)])
        with TemporaryDirectory() as directory:
            midi = Path(directory)/"test.mid"
            midi.write_bytes(render_midi([original],120,[(.1,.9)]))
            voices,pedal = read_midi(midi)
        self.assertEqual([(n.pitch,n.velocity) for n in voices[0].notes],[(60,96),(67,61)])
        self.assertAlmostEqual(voices[0].notes[0].start,.25)
        self.assertAlmostEqual(voices[0].notes[0].end,.5)
        self.assertAlmostEqual(pedal["ch0"][0][0],.1)
        self.assertAlmostEqual(pedal["ch0"][0][1],.9)
