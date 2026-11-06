import unittest

from glide_arrangement.score import Note, Voice
from test_arrangement import HAS_AUDIO

@unittest.skipUnless(HAS_AUDIO,"Instala requirements-arrangement.txt")
class SpectrotemporalTests(unittest.TestCase):
    def test_tracks_a_partial_that_changes_inside_held_note(self):
        import numpy as np
        from glide_arrangement.spectrotemporal import RATE, synthesize, track_partials

        t = np.arange(RATE*2)/RATE
        phase = 2*np.pi*440*t
        reference = .2*np.sin(phase)+np.where(t<1,.025,.17)*np.sin(2*phase)
        note = Note(69,.1,1.8)
        voice = Voice("one","lead",[note],release=.1)
        tracks = track_partials(reference,[voice],"guitar")
        fundamental, second = tracks[:2]
        self.assertGreater(np.median(second.amplitude[-25:-10]),
                           4*np.median(second.amplitude[10:25]))
        self.assertAlmostEqual(np.median(fundamental.amplitude),.2,delta=.035)
        reconstructed = synthesize(tracks,len(t))
        self.assertEqual(voice.notes,[note])
        self.assertEqual(np.count_nonzero(reconstructed[:round(.1*RATE)]),0)
        self.assertEqual(np.count_nonzero(reconstructed[round(1.9*RATE):]),0)

    def test_shared_bin_is_not_counted_twice_and_pedal_extends_support(self):
        import numpy as np
        from glide_arrangement.spectrotemporal import RATE, track_partials

        t = np.arange(RATE*2)/RATE
        reference = .2*np.sin(2*np.pi*440*t)
        notes = [Note(69,.1,.9)]
        voices = [Voice(name,"inner",notes.copy()) for name in ("a","b")]
        single = track_partials(reference,voices[:1],"piano")[0]
        shared = [p for p in track_partials(reference,voices,"piano",pedal=[(.5,1.5)])
                  if p.harmonic==1]
        self.assertEqual(len(shared),2)
        self.assertAlmostEqual(shared[0].end,1.66)
        self.assertAlmostEqual(sum(p.amplitude[20]**2 for p in shared),single.amplitude[20]**2,delta=.001)
        self.assertEqual(voices[0].notes,notes)
