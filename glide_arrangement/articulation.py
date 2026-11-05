"""Refine events using pitch-local energy and spectral transients."""
from dataclasses import dataclass, replace

import librosa
import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import find_peaks

from .score import Note, Voice

@dataclass(frozen=True)
class Evidence:
    time: np.ndarray
    energy: np.ndarray
    flux: np.ndarray
    partials: np.ndarray | None = None

def extract_evidence(path, pitches):
    audio, rate = librosa.load(path, sr=22050, mono=True)
    hop, fft = 128, 4096
    magnitude = np.abs(librosa.stft(audio, n_fft=fft, win_length=2048, hop_length=hop))
    frequencies = librosa.fft_frequencies(sr=rate, n_fft=fft)
    time = librosa.frames_to_time(np.arange(magnitude.shape[1]), sr=rate, hop_length=hop)
    evidence = {}
    for pitch in pitches:
        fundamental = float(librosa.midi_to_hz(pitch))
        energy = np.zeros_like(time)
        flux = np.zeros_like(time)
        partials = np.zeros((6, len(time)))
        for partial in range(1, 7):
            center = fundamental*partial
            indices = np.abs(frequencies-center) <= max(12, center*.012)
            if not indices.any():
                continue
            band = magnitude[indices]
            weight = 1/partial**.65
            partials[partial-1] = np.linalg.norm(band, axis=0)
            energy += weight*partials[partial-1]
            positive = np.maximum(np.diff(band, axis=1, prepend=band[:, :1]), 0)
            flux += weight*np.linalg.norm(positive, axis=0)
        evidence[pitch] = Evidence(time, gaussian_filter1d(energy, 1.3), gaussian_filter1d(flux, 1.1), partials)
    return evidence

def attack_times(evidence, start, end):
    t, energy, flux = evidence.time, evidence.energy, evidence.flux
    region = (t >= start) & (t <= end)
    if not region.any():
        return []
    level = np.percentile(energy[region], 80)
    if level <= 1e-8:
        return []
    step = t[1]-t[0] if len(t) > 1 else 1
    peaks = find_peaks(flux, distance=max(1, round(.115/step)))[0]
    attacks = []
    for i in peaks[region[peaks]]:
        before = energy[(t >= t[i]-.105) & (t <= t[i]-.025)]
        after = energy[(t >= t[i]+.018) & (t <= t[i]+.075)]
        if not before.size or not after.size:
            continue
        low, high = np.min(before), np.max(after)
        if high >= .65*level and low <= .32*high and flux[i] >= .045*level:
            attacks.append(float(t[i]))
    return attacks

def release_start(evidence, start, end):
    """Find a stable downward change before the detected audible end."""
    t, energy = evidence.time, evidence.energy
    candidates = np.flatnonzero((t >= max(start+.13, end-.45)) & (t <= end-.055))
    for i in candidates:
        before = energy[(t >= t[i]-.105) & (t < t[i]-.018)]
        after = energy[(t >= t[i]+.06) & (t <= t[i]+.12)]
        tail = energy[(t >= t[i]+.12) & (t <= end+.035)]
        if not before.size or not after.size or not tail.size:
            continue
        level = np.median(before)
        if (level > 1e-8 and np.min(before) >= .82*level
                and .56*level <= energy[i] <= .85*level
                and np.median(after) < .60*level and np.max(tail) < .72*level):
            return float(t[i])
    return None

def refine(voices, evidence):
    """Return a separate score and an audit trail, preserving voice IDs and pitches."""
    output, decisions = [], []
    for voice in voices:
        notes = []
        audit = []
        for note in sorted(voice.notes, key=lambda n: n.start):
            curve = evidence[note.pitch]
            previous = notes[-1] if notes else None
            if previous and previous.pitch == note.pitch and -.015 <= note.start-previous.end <= .11:
                near = attack_times(curve, note.start-.045, note.start+.055)
                between = curve.energy[(curve.time >= min(previous.end, note.start)-.014)
                                        & (curve.time <= note.start+.014)]
                nearby = curve.energy[(curve.time >= previous.end-.18) & (curve.time <= note.start+.18)]
                if not near and between.size and nearby.size and np.max(nearby) > 0 and np.min(between) > .26*np.max(nearby):
                    notes[-1] = replace(previous, end=max(previous.end, note.end))
                    audit.append({"type":"sustain", "pitch":note.pitch, "time":note.start})
                    continue
                if near:
                    audit.append({"type":"retrigger", "pitch":note.pitch, "time":note.start})
            notes.append(note)

        split = []
        for note in notes:
            boundaries = attack_times(evidence[note.pitch], note.start+.18, note.end-.15)
            starts = [note.start]
            for boundary in boundaries:
                if boundary-starts[-1] >= .18:
                    starts.append(boundary)
                    audit.append({"type":"retrigger", "pitch":note.pitch, "time":boundary})
            split.extend(Note(note.pitch, start, end, note.velocity)
                         for start, end in zip(starts, starts[1:]+[note.end]))

        for i, note in enumerate(split):
            following = split[i+1] if i+1 < len(split) else None
            legato = False
            if following and following.pitch != note.pitch and -.095 <= following.start-note.end <= .025:
                curve = evidence[note.pitch]
                before = curve.energy[(curve.time >= note.end-.12) & (curve.time <= note.end-.035)]
                handoff = curve.energy[(curve.time >= following.start-.024) & (curve.time <= following.start+.012)]
                legato = bool(before.size and handoff.size and np.max(before) > 0
                              and np.median(handoff) >= .26*np.max(before))
            if legato:
                audit.append({"type":"legato", "pitch":note.pitch, "to_pitch":following.pitch, "time":following.start})
            elif not following or following.pitch != note.pitch or following.start-note.end > .08:
                release = release_start(evidence[note.pitch], note.start, note.end)
                if release is not None:
                    audit.append({"type":"release", "pitch":note.pitch, "time":release, "audible_end":note.end})
                    split[i] = replace(note, end=release)
        output.append(replace(voice, notes=split))
        decisions.extend({"voice":voice.id, **entry} for entry in audit)
    return output, decisions
