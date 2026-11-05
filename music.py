"""Motor armónico independiente de la interfaz; sólo biblioteca estándar."""
import re
import struct
from itertools import permutations

PC = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}
QUALITIES = {
    '': [0,4,7], 'm': [0,3,7], 'dim': [0,3,6], 'aug': [0,4,8],
    'sus2': [0,2,7], 'sus4': [0,5,7], '6': [0,4,7,9], 'm6': [0,3,7,9],
    '7': [0,4,7,10], 'maj7': [0,4,7,11], 'm7': [0,3,7,10],
    'm7b5': [0,3,6,10], 'dim7': [0,3,6,9], '9': [0,4,7,10,14],
    'maj9': [0,4,7,11,14], 'm9': [0,3,7,10,14],
    'add9': [0,4,7,14], '11': [0,4,7,10,14,17],
    '13': [0,4,7,10,14,21], '7#9': [0,4,7,10,15], '7b9': [0,4,7,10,13],
}

def parse(symbol):
    normalized = symbol.replace('♭', 'b').replace('♯', '#')
    match = re.fullmatch(r'([A-Ga-g])([#b]?)(.*)', normalized)
    if not match:
        raise ValueError(f'Acorde inválido: {symbol}')
    letter, accidental, quality = match.groups()
    quality = quality.replace('(', '').replace(')', '')
    if quality not in QUALITIES:
        raise ValueError(f'Acorde no admitido: {symbol}')
    root = (PC[letter.upper()] + {'': 0, '#': 1, 'b': -1}[accidental]) % 12
    return dict(label=letter.upper() + accidental.replace('b','♭').replace('#','♯') + quality.replace('b','♭').replace('#','♯'),
                root=letter.upper()+accidental, quality=quality, intervals=QUALITIES[quality],
                pcs=[(root+i)%12 for i in QUALITIES[quality]], root_pc=root)

def voicing(chord, previous=None):
    pcs = chord['pcs']
    if previous is None:
        return sorted(54 + (pc-54)%12 for pc in pcs)
    # Evaluate complete ascending assignments, avoiding greedy voice crossings.
    best = None
    for order in permutations(pcs):
        candidates = [[]]
        for pc in order:
            candidates = [prefix+[note] for prefix in candidates
                          for note in range(48+pc, 85, 12)
                          if not prefix or note > prefix[-1]]
        for notes in candidates:
            cost = sum(abs(n-previous[min(i,len(previous)-1)]) for i,n in enumerate(notes))
            cost += .05*sum(abs(n-66) for n in notes)
            if best is None or cost < best[0]:
                best = cost, notes
    return best[1]

def progression(text):
    parts = re.split(r'[\s,;]+', text.strip())
    if not text.strip() or not 1 <= len(parts) <= 24:
        raise ValueError('Introduce entre 1 y 24 acordes.')
    chords = [parse(part) for part in parts]
    voices = []
    for chord in chords:
        voices.append(voicing(chord, voices[-1] if voices else None))
    return {'chords': chords, 'voices': voices}

def variable_length(value):
    output = [value & 127]
    while value >> 7:
        value >>= 7
        output.insert(0, (value & 127) | 128)
    return bytes(output)

def midi(text, bpm=86):
    if not 45 <= bpm <= 180:
        raise ValueError('Tempo fuera de rango (45–180).')
    data = progression(text)
    track = bytearray(b'\x00\xff\x51\x03' + int(60000000/bpm).to_bytes(3,'big'))
    for notes in data['voices']:
        for note in notes:
            track.extend(bytes([0, 0x90, note, 80]))
        for i, note in enumerate(notes):
            track.extend(variable_length(960 if i == 0 else 0) + bytes([0x80,note,0]))
    track.extend(b'\x00\xff\x2f\x00')
    return b'MThd'+struct.pack('>IHHH',6,0,1,480)+b'MTrk'+struct.pack('>I',len(track))+track
