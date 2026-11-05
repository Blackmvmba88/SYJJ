"""Dry WAV rendering and MIDI with separate programs and expression curves."""
import struct

import numpy as np
import soundfile as sf

from music import variable_length

INSTRUMENTS = {
    "soft": (89, (1, .22, .09, .04), .10),
    "keys": (4, (1, .38, .20, .09), .58),
    "strings": (48, (1, .48, .31, .19, .10), .08),
    "bass": (33, (1, .24, .09), .22),
}

def expression_at(voice, times):
    points = voice.expression
    if not points:
        return np.full_like(times, 100, dtype=float)
    return np.interp(times, [p[0] for p in points], [p[1] for p in points])

def render_wav(voices, path, sample_rate=44100, note_tails=None):
    tails = note_tails or {}
    duration = max((n.end + tails.get((v.id,i),v.release)
                    for v in voices for i,n in enumerate(v.notes)), default=0)
    mix = np.zeros(max(1, int(np.ceil(duration * sample_rate))))
    for voice in voices:
        _, partials, decay = INSTRUMENTS[voice.instrument]
        previous_end = 0
        for index, note in sorted(enumerate(voice.notes), key=lambda item:item[1].start):
            release = tails.get((voice.id,index),voice.release)
            start = round(note.start * sample_rate)
            end = min(len(mix), round((note.end + release) * sample_rate))
            t = np.arange(end-start)/sample_rate
            held = note.end-note.start
            attack = voice.attack * (1.8 if note.start < previous_end else 1)
            envelope = np.minimum(t/max(attack, 1/sample_rate), 1)
            envelope *= 1-decay*(1-np.exp(-t/.55))
            envelope *= np.clip(1-(t-held)/max(release, 1/sample_rate), 0, 1)
            hz = 440*2**((note.pitch-69)/12)
            wave = sum(gain*np.sin(2*np.pi*hz*k*t)
                       for k, gain in enumerate(partials, 1) if hz*k < sample_rate/2)
            mix[start:end] += .18 * note.velocity/127 * expression_at(voice, note.start+t)/127 * envelope * wave
            previous_end = max(previous_end, note.end)
    peak = np.max(np.abs(mix))
    if peak > .96:
        mix *= .96/peak
    sf.write(path, mix, sample_rate, subtype="PCM_16")

def _track(events):
    data = bytearray()
    last = 0
    for tick, _, message in sorted(events):
        data.extend(variable_length(tick-last) + message)
        last = tick
    data.extend(b"\x00\xff\x2f\x00")
    return b"MTrk" + struct.pack(">I", len(data)) + data

def render_midi(voices, bpm=120):
    if not 4 <= bpm <= 600:
        raise ValueError("Tempo fuera de rango")
    channels = [ch for ch in range(16) if ch != 9]
    if len(voices) > len(channels):
        raise ValueError("MIDI admite hasta 15 voces independientes por puerto")
    tracks = [_track([(0, 0, b"\xff\x51\x03" + round(60_000_000/bpm).to_bytes(3,"big"))])]
    def tick(seconds):
        return round(seconds*bpm*480/60)
    for voice, channel in zip(voices, channels):
        program = INSTRUMENTS[voice.instrument][0]
        events = [(0, 0, bytes([0xC0+channel, program]))]
        end_time = max((n.end for n in voice.notes), default=0)
        times = sorted({0., *[t for t, _ in voice.expression],
                        *([i/20 for i in range(int(end_time*20)+1)] if voice.expression else [])})
        for time, value in zip(times, expression_at(voice, np.asarray(times))):
            events.append((tick(time), 1, bytes([0xB0+channel, 11, round(value)])))
        previous_end = {}
        for note in sorted(voice.notes, key=lambda n: n.start):
            start = tick(note.start)
            end = max(start+1, tick(note.end))
            if previous_end.get(note.pitch, -1) > start:
                raise ValueError(f"Notas del mismo tono superpuestas en {voice.id}; separa las voces")
            previous_end[note.pitch] = end
            events.extend([(start, 3, bytes([0x90+channel, note.pitch, note.velocity])),
                           (end, 2, bytes([0x80+channel, note.pitch, 0]))])
        tracks.append(_track(events))
    return b"MThd"+struct.pack(">IHHH",6,1,len(tracks),480)+b"".join(tracks)
