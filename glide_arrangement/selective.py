"""Conservative sustain and retrigger edits relative to a fixed baseline."""
from dataclasses import replace

import numpy as np

from .articulation import attack_times
from .score import Note

VARIANTS = ("B1", "B2", "B3")

def _window(curve, start, end):
    return (curve.time >= start) & (curve.time <= end)

def _sustain(curve, previous, current):
    gap = current.start-previous.end
    if not -.012 <= gap <= .075 or curve.partials is None:
        return False
    left = _window(curve, previous.end-.115, previous.end-.028)
    right = _window(curve, current.start+.028, current.start+.115)
    bridge = _window(curve, previous.end-.025, current.start+.025)
    if not all(mask.any() for mask in (left, right, bridge)):
        return False
    a, b = (np.median(curve.partials[:, mask], axis=1) for mask in (left,right))
    norm = np.linalg.norm(a)*np.linalg.norm(b)
    level = max(np.median(curve.energy[left]), np.median(curve.energy[right]))
    if norm <= 1e-8 or level <= 1e-8:
        return False
    return bool(
        np.dot(a,b)/norm >= .975
        and np.percentile(curve.energy[bridge], 10) >= .65*level
        and np.max(curve.flux[bridge]) <= .028*level
        and not attack_times(curve, previous.end-.055, current.start+.055)
    )

def _retriggers(curve, note):
    if curve.partials is None:
        return []
    result = []
    for time in attack_times(curve, note.start+.18, note.end-.15):
        before = _window(curve,time-.10,time-.025)
        after = _window(curve,time+.018,time+.075)
        # Demand a corresponding dip and rise at the fundamental itself.
        low = np.min(curve.partials[0,before])
        high = np.max(curve.partials[0,after])
        if high > 1e-8 and low <= .40*high:
            result.append(time)
    return result

def refine_selective(voices, evidence, variant):
    if variant not in VARIANTS:
        raise ValueError("Variante desconocida")
    output, decisions = [], []
    for voice in voices:
        merged = []
        for note in sorted(voice.notes, key=lambda note: note.start):
            if (variant in {"B1","B3"} and merged and merged[-1].pitch == note.pitch
                    and _sustain(evidence[note.pitch], merged[-1], note)):
                previous = merged[-1]
                merged[-1] = replace(previous, end=max(previous.end,note.end))
                decisions.append({"type":"sustain", "voice":voice.id, "pitch":note.pitch,
                                  "time":note.start, "previous_end":previous.end})
            else:
                merged.append(note)

        notes = []
        for note in merged:
            starts = [note.start]
            if variant in {"B2","B3"}:
                for time in _retriggers(evidence[note.pitch], note):
                    if time-starts[-1] >= .18:
                        starts.append(time)
                        decisions.append({"type":"retrigger", "voice":voice.id,
                                          "pitch":note.pitch, "time":time})
            notes.extend(Note(note.pitch,start,end,note.velocity)
                         for start,end in zip(starts,starts[1:]+[note.end]))
        output.append(replace(voice,notes=notes))
    return output, decisions
