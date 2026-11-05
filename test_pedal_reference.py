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
