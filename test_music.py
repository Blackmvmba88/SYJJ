import unittest
from music import progression, parse, midi, QUALITIES

class MusicTests(unittest.TestCase):
    def test_example(self):
        result = progression('Eb9 Abmaj7 Am7b5 D7#9 Gm9 Bbm7')
        self.assertEqual(len(result['voices']), 6)
        for chord, notes in zip(result['chords'], result['voices']):
            self.assertEqual(sorted(n%12 for n in notes), sorted(chord['pcs']))
            self.assertEqual(notes, sorted(set(notes)))
            self.assertTrue(all(48 <= n <= 84 for n in notes))

    def test_qualities_and_enharmonics(self):
        for quality in QUALITIES:
            result = progression('C'+quality+' F#'+quality+' Bb'+quality)
            self.assertEqual(len(result['voices']), 3)
        self.assertEqual(parse('Cb')['root_pc'], 11)
        self.assertEqual(parse('B#')['root_pc'], 0)
        self.assertEqual(parse('E♭9')['pcs'], parse('Eb9')['pcs'])

    def test_invalid(self):
        for value in ['', 'H7', 'Cunknown', 'C '*25]:
            with self.assertRaises(ValueError):
                progression(value)

    def test_midi(self):
        output = midi('Cmaj7 Dm7 G7')
        self.assertTrue(output.startswith(b'MThd'))
        self.assertTrue(output.endswith(b'\x00\xff\x2f\x00'))
        self.assertEqual(int.from_bytes(output[18:22], 'big'), len(output)-22)
        with self.assertRaises(ValueError):
            midi('C',0)

if __name__ == '__main__':
    unittest.main()
