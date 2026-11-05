"""Run with the optional audio dependencies installed."""
import importlib.util
import tempfile
from pathlib import Path
import unittest

from glide_arrangement.score import Note, Voice, load_score

HAS_AUDIO = all(importlib.util.find_spec(name) for name in ("numpy", "scipy", "soundfile", "librosa"))

class ScoreTests(unittest.TestCase):
    def test_inversion_and_doubled_pitch_survive_loading(self):
        data = {"voices": [
            {"id": "bass", "role": "bass", "notes": [{"pitch": 40, "start": 0, "end": 2}]},
            {"id": "first", "role": "inner", "notes": [{"pitch": 60, "start": 0, "end": 2}]},
            {"id": "second", "role": "lead", "notes": [{"pitch": 60, "start": .1, "end": 2}]},
        ]}
        voices = load_score(data)
        self.assertEqual([v.notes[0].pitch for v in voices], [40, 60, 60])
        self.assertEqual(voices[2].notes[0].start, .1)

@unittest.skipUnless(HAS_AUDIO, "Instala requirements-arrangement.txt")
class AudioTests(unittest.TestCase):
    def test_recovers_held_bass_and_moving_inner_note(self):
        import numpy as np
        import soundfile as sf
        from glide_arrangement.transcribe import assign_voices, estimate_notes
        rate = 22050
        t = np.arange(rate*2)/rate
        mix = np.zeros_like(t)
        for pitch, start, end, level in [(43,.15,1.85,.27),(60,.15,.9,.21),
                                          (62,.9,1.85,.21),(67,.15,1.85,.22)]:
            phase = 2*np.pi*440*2**((pitch-69)/12)*(t-start)
            envelope = np.clip(np.minimum(t-start,end-t)/.025,0,1)
            mix += level*envelope*(np.sin(phase)+.3*np.sin(2*phase))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"known.wav"
            sf.write(path,mix,rate)
            notes = estimate_notes(path)
        for pitch, start, end in [(43,.15,1.85),(60,.15,.9),(62,.9,1.85),(67,.15,1.85)]:
            found = [n for n in notes if n.pitch == pitch]
            self.assertTrue(any(abs(n.start-start)<.13 and abs(n.end-end)<.13 for n in found), notes)
        voices = assign_voices(notes)
        self.assertTrue(any([60,62] == [n.pitch for n in v.notes] for v in voices), voices)

    def test_expression_and_overlap_export(self):
        import numpy as np
        import soundfile as sf
        from glide_arrangement.render import render_midi, render_wav
        voice = Voice("v1", "inner", [Note(60,0,1,92), Note(62,.93,2,86)],
                      instrument="strings", expression=[(0,20),(1,120),(2,5)])
        midi = render_midi([voice],126)
        self.assertEqual(midi[:4],b"MThd")
        self.assertIn(bytes([0xC0,48]),midi)
        self.assertIn(bytes([0xB0,11,120]),midi)
        self.assertIn(bytes([0x90,60,92]),midi)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"render.wav"
            render_wav([voice],path)
            samples, rate = sf.read(path)
        self.assertGreater(len(samples)/rate,2)
        self.assertGreater(np.std(samples[rate//2:rate]), np.std(samples[:rate//4])*1.5)

    def test_ab_reports_alignment_pitch_and_duration(self):
        from glide_arrangement.compare import compare
        result = compare([Note(60,0,1),Note(67,1,2)],
                         [Note(61,.1,1.3),Note(67,1,2),Note(72,3,4)])
        self.assertEqual(result["exact_pitch_matches"],1)
        self.assertEqual(result["candidate_unmatched"],1)
        self.assertEqual(result["pitch_mae_semitones"],.5)
        self.assertAlmostEqual(result["onset_mae_seconds"],.05)
        self.assertAlmostEqual(result["duration_mae_seconds"],.1)
        self.assertEqual(result["candidate_octaves"],{4:2,5:1})
