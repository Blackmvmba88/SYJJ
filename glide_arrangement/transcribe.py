"""Estimate MIDI events from a mix and link them into editable voices."""
from itertools import groupby

import librosa
import numpy as np
from scipy.optimize import linear_sum_assignment

from .score import Note, Voice

def _role(pitch):
    return "bass" if pitch < 53 else "lead" if pitch >= 67 else "inner"

def assign_voices(notes):
    """Match onsets jointly, favoring proximity and continuous held voices."""
    tracks = []
    for _, group in groupby(sorted(notes, key=lambda n: n.start), lambda n: round(n.start / .045)):
        incoming = list(group)
        eligible = [i for i, track in enumerate(tracks)
                    if incoming[0].start - track[-1].end >= -.085]
        costs = np.full((len(incoming), len(eligible) + len(incoming)), 19.)
        for row, note in enumerate(incoming):
            for col, index in enumerate(eligible):
                last = tracks[index][-1]
                gap = note.start-last.end
                if gap < 0 and note.pitch == last.pitch:
                    continue
                register_penalty = 7 if (_role(note.pitch) == "bass") != (_role(last.pitch) == "bass") else 0
                costs[row, col] = abs(note.pitch-last.pitch) + min(5, 5*abs(gap)) + register_penalty
        rows, cols = linear_sum_assignment(costs)
        for row, col in zip(rows, cols):
            if col < len(eligible):
                tracks[eligible[col]].append(incoming[row])
            else:
                tracks.append([incoming[row]])
    if not tracks:
        return []
    voices = []
    for i, track in enumerate(tracks):
        time_by_role = {role: 0. for role in ("bass", "inner", "lead")}
        for note in track:
            time_by_role[_role(note.pitch)] += note.end-note.start
        role = max(time_by_role, key=time_by_role.get)
        instrument = {"bass":"bass", "inner":"soft", "lead":"keys"}[role]
        voices.append(Voice(f"v{i+1}", role, track, instrument=instrument))
    return voices

def estimate_notes(path, max_polyphony=8):
    """Fundamental peak tracking with harmonic suppression. Returns hypotheses, including octaves."""
    if not 1 <= max_polyphony <= 16:
        raise ValueError("La polifonía debe estar entre 1 y 16")
    sample_rate = 22050
    audio, _ = librosa.load(path, sr=sample_rate, mono=True)
    if not audio.size or np.max(np.abs(audio)) < 1e-6:
        return []
    hop, fft = 256, 8192
    spectrum = np.abs(librosa.stft(audio, n_fft=fft, hop_length=hop))
    pitches = np.arange(36, 89)
    # Locate actual peaks rather than assigning a strong bin to nearby notes.
    peaks = (spectrum[1:-1] >= spectrum[:-2]) & (spectrum[1:-1] >= spectrum[2:])
    peaks &= spectrum[1:-1] >= .035 * spectrum.max(axis=0)
    peak_bin, peak_frame = np.nonzero(peaks)
    peak_bin += 1
    left, center, right = (spectrum[peak_bin+delta, peak_frame] for delta in (-1,0,1))
    offset = .5*(left-right)/np.minimum(left-2*center+right,-1e-8)
    peak_pitch = librosa.hz_to_midi((peak_bin+offset)*sample_rate/fft)
    nearest = np.rint(peak_pitch).astype(int)
    valid = (nearest >= pitches[0]) & (nearest <= pitches[-1]) & (abs(nearest-peak_pitch) <= .39)
    salience = np.zeros((len(pitches), spectrum.shape[1]), dtype=np.float32)
    np.maximum.at(salience, (nearest[valid]-pitches[0], peak_frame[valid]), center[valid])
    # A weak integer partial can be explained by a lower active fundamental.
    # Retain strong peaks at those pitches so an independent upper voice survives.
    activation = salience.copy()
    for partial in range(2, 9):
        shift = round(12*np.log2(partial))
        activation[shift:] -= salience[:-shift] * (.62 / partial**.65)
    np.maximum(activation, 0, out=activation)
    weakest_kept = np.partition(activation, -max_polyphony, axis=0)[-max_polyphony]
    activation[activation < weakest_kept] = 0
    notes = []
    frame_max = activation.max(axis=0)
    scale = max(float(np.percentile(frame_max, 90)), 1e-6)
    for pitch, energy in zip(pitches, activation):
        active = (energy >= .085 * scale) & (energy >= .12 * frame_max)
        # Bridge up to two missing frames inside a sustained note.
        for gap in (1, 2):
            for pos in np.flatnonzero(active[:-gap-1] & active[gap+1:]):
                active[pos+1:pos+gap+1] = True
        edges = np.flatnonzero(np.diff(np.r_[False, active, False]))
        for start, end in edges.reshape(-1, 2):
            if end-start < 11:
                continue
            t0, t1 = start*hop/sample_rate, min(end*hop/sample_rate, len(audio)/sample_rate)
            if t1 <= t0:
                continue
            strength = np.percentile(energy[start:end], 75) / scale
            velocity = int(np.clip(37 + 55 * np.sqrt(strength), 1, 127))
            notes.append(Note(int(pitch), float(t0), float(t1), velocity))
    return sorted(notes, key=lambda note: (note.start, note.pitch))
