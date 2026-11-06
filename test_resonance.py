import unittest

from glide_arrangement.score import Note, Voice
from test_arrangement import HAS_AUDIO

@unittest.skipUnless(HAS_AUDIO,"Instala requirements-arrangement.txt")
class ResonanceTests(unittest.TestCase):
    def test_pedal_moves_observation_window_without_editing_key_event(self):
        import numpy as np
        from glide_arrangement.articulation import Evidence
        from glide_arrangement.resonance import condition, rendering_tails

        t = np.arange(0,2,.005)
        energy = np.exp(-40*np.maximum(t-1.2,0))
        curve = Evidence(t,energy,np.zeros_like(t),np.array([energy,.4*energy]))
        note = Note(60,.1,.8)
        voice = Voice("v","inner",[note])
        records = condition([voice],{60:curve},"piano",[(.6,1.2)])
        r = records[0]
        self.assertEqual(r["damper_end"],1.2)
        self.assertEqual(r["excitation_end"],.8)
        self.assertAlmostEqual(r["acoustic_end_observed"],1.27,delta=.01)
        self.assertEqual(voice.notes,[note])
        self.assertGreater(rendering_tails({"resonance":records})["v",0],.4)

    def test_shared_pitch_requires_isolated_string_or_preserves_previous_tail(self):
        import numpy as np
        from glide_arrangement.articulation import Evidence
        from glide_arrangement.resonance import condition, rendering_tails

        t = np.arange(0,2,.005)
        energy = np.exp(-40*np.maximum(t-.8,0))
        curve = Evidence(t,energy,np.zeros_like(t),np.array([energy,.4*energy]))
        voices = [Voice("v","inner",[Note(60,.1,.8)]),Voice("other","inner",[Note(60,.2,1.3)])]
        prior = [{"voice":"v","index":0,"tail_seconds":.18,"tail_decay_db_s":-30}]
        result = condition(voices,{60:curve},"guitar",duration=prior)
        self.assertEqual(result[0]["provenance"],"predicted")
        self.assertEqual(rendering_tails({"duration":prior,"resonance":result})["v",0],.18)
        isolated = condition(voices,{60:curve},"guitar",strings={"v":"2","other":"3"},
                             string_evidence={"2":{60:curve}})
        self.assertEqual(isolated[0]["provenance"],"observed")

    def test_wav_changes_decay_shape_and_midi_keeps_note_off(self):
        import tempfile
        from pathlib import Path
        import numpy as np
        import soundfile as sf
        from glide_arrangement.render import render_midi, render_wav

        voice = Voice("v","inner",[Note(60,0,.25)])
        tails = {("v",0):.5}
        with tempfile.TemporaryDirectory() as temp:
            plain, pedal = (Path(temp)/name for name in ("plain.wav","pedal.wav"))
            render_wav([voice],plain,sample_rate=8000,note_tails=tails)
            render_wav([voice],pedal,sample_rate=8000,note_tails=tails,note_dampers={("v",0):.65})
            a,rate = sf.read(plain)
            b,_ = sf.read(pedal)
        region = slice(int(.53*rate),int(.61*rate))
        self.assertGreater(np.linalg.norm(b[region]),np.linalg.norm(a[region])*1.3)
        no_pedal = render_midi([voice],120)
        with_pedal = render_midi([voice],120,pedal_intervals=[(0,.65)])
        self.assertIn(b"\x81\x70\x80\x3c\x00",no_pedal)
        self.assertIn(b"\x81\x70\x80\x3c\x00",with_pedal)
        self.assertIn(b"\xb0\x40\x7f",with_pedal)
