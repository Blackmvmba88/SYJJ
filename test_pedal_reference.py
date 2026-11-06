import unittest
from types import SimpleNamespace

from experiments.pedal_reference import read_performance

def message(kind,time,**kwargs):
    return SimpleNamespace(type=kind,time=time,channel=0,**kwargs)

def pedal(time,value):
    return message("control_change",time,control=64,value=value)

def key(time,velocity):
    return message("note_on",time,note=60,velocity=velocity)

class PedalTests(unittest.TestCase):
    def test_pedal_pressed_mid_note_and_reattack_holds_damper_open(self):
        notes, intervals = read_performance([
            key(.1,85),pedal(.2,90),key(.3,0),key(.1,70),pedal(.2,0),key(.15,0),
        ])
        n = notes[0]
        self.assertFalse(n.pedal_at_on)
        self.assertTrue(n.pedal_at_off)
        self.assertAlmostEqual(n.pedal_during_key_seconds,.3)
        self.assertAlmostEqual(n.off[0],.6)
        self.assertAlmostEqual(n.damper_end,1.05)
        self.assertTrue(n.reattack_before_damper)
        self.assertAlmostEqual(intervals[0].up[0],.9)

    def test_order_at_same_tick_and_unclosed_pedal(self):
        notes,_ = read_performance([key(.1,80),key(.3,0),pedal(0,127),key(.1,80),key(.3,0)])
        self.assertFalse(notes[0].pedal_at_off)
        self.assertEqual(notes[0].off[0],notes[0].damper_end)
        self.assertTrue(notes[1].pedal_at_off)
        self.assertIsNone(notes[1].damper_end)

    def test_reattack_at_same_tick_depends_on_damper_order(self):
        earlier,_ = read_performance([pedal(0,127),key(.1,80),key(.2,0),
                                      key(.2,85),pedal(0,0),key(.3,0)])
        later,_ = read_performance([pedal(0,127),key(.1,80),key(.2,0),
                                    pedal(.2,0),key(0,85),key(.3,0)])
        self.assertAlmostEqual(earlier[0].damper_end,.8)
        self.assertTrue(earlier[0].reattack_before_damper)
        self.assertAlmostEqual(later[0].damper_end,.5)
        self.assertFalse(later[0].reattack_before_damper)

    def test_overlapping_same_pitch_has_ambiguous_note_off_pairing(self):
        notes,_ = read_performance([key(.1,80),key(.2,90),key(.2,0),key(.1,0)])
        self.assertTrue(all(note.overlapping_key_events for note in notes))
