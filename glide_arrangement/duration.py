"""Estimate a change in decay rate near a note end, or keep the baseline."""
from dataclasses import dataclass, replace

import numpy as np

@dataclass(frozen=True)
class TailProfile:
    min_tail: float
    max_tail: float
    min_decay: float  # dB/s after excitation stops
    min_change: float # dB/s relative to the preceding envelope

PROFILES = {
    "piano": TailProfile(.055,.55,24,17),
    "guitar": TailProfile(.055,.48,19,13),
    "keys": TailProfile(.055,.50,22,16),
    "bass": TailProfile(.065,.40,20,15),
    "strings": TailProfile(.085,.65,15,12),
    "soft": TailProfile(.070,.55,17,13),
}

def estimate_end(curve, note, profile, limit=np.inf):
    """Fit a continuous, two-slope log envelope with harmonic corroboration."""
    if curve.partials is None or note.end-note.start < .22:
        return None
    # A note can only use evidence near its endpoint. Keep full takes cheap
    # without changing the search window or its decision thresholds.
    first = np.searchsorted(curve.time,note.end-.51)
    last = np.searchsorted(curve.time,note.end+.28,side="right")
    t, energy = curve.time[first:last], curve.energy[first:last]
    partials = curve.partials[:,first:last]
    step = t[1]-t[0] if len(t)>1 else 0
    if step <= 0:
        return None
    stop = min(limit, curve.time[-1], note.end+.28)
    search = np.flatnonzero((t >= max(note.start+.13,note.end-.40)) &
                            (t <= min(note.end+.12, stop-.105)))
    candidates = []
    for index in search[::max(1,round(.017/step))]:
        when = t[index]
        mask = (t >= when-.10) & (t <= min(when+.15,stop))
        before = mask & (t < when)
        after = mask & (t >= when)
        level = np.median(energy[before]) if before.any() else 0
        if level < 1e-7 or np.sum(after) < 7:
            continue
        x = t[mask]-when
        y = 20*np.log10(np.maximum(energy[mask]/level,.04))
        design = np.column_stack((np.ones_like(x),x,np.maximum(x,0)))
        coef = np.linalg.lstsq(design,y,rcond=None)[0]
        pre, change = coef[1:]
        post = pre+change
        residual = np.mean((design@coef-y)**2)
        linear = design[:,:2]
        baseline = np.mean((linear@np.linalg.lstsq(linear,y,rcond=None)[0]-y)**2)
        if (post > -profile.min_decay or change > -profile.min_change
                or baseline < .35 or residual > .48*baseline):
            continue
        early = (t >= when-.065) & (t <= when-.02)
        late = (t >= when+.07) & (t <= min(when+.115,stop))
        if not early.any() or not late.any():
            continue
        a = np.median(partials[:,early],axis=1)
        b = np.median(partials[:,late],axis=1)
        norm = np.linalg.norm(a)*np.linalg.norm(b)
        strong = a >= .16*np.max(a)
        if (norm <= 1e-8 or np.dot(a,b)/norm < .91 or not strong.any()
                or np.median(b[strong]/a[strong]) >= .78):
            continue
        # The acoustic endpoint uses an operational floor 24 dB below the knee.
        model_end = when + 24/abs(post)
        horizon = min(when+profile.max_tail,stop)
        decay_end = min(model_end,horizon)
        tail_region = np.flatnonzero((t >= when+profile.min_tail) & (t <= min(decay_end,stop)))
        if not tail_region.size:
            continue
        floor = level * 10**(-24/20)
        crossings = tail_region[energy[tail_region] <= floor]
        acoustic = float(t[crossings[0]]) if crossings.size else min(decay_end,stop)
        tail = acoustic-when
        if tail < profile.min_tail:
            continue
        score = residual/baseline + .55*abs(when-note.end)
        provenance = "observed" if crossings.size else "bounded" if horizon < model_end else "extrapolated"
        candidates.append((score,float(when),float(acoustic),float(post),provenance))
    if not candidates:
        return None
    _, end, acoustic, slope, provenance = min(candidates)
    return {"excitation_end":end,"acoustic_end":acoustic,"tail_seconds":acoustic-end,
            "tail_decay_db_s":slope,"acoustic_end_observed":provenance=="observed",
            "acoustic_end_provenance":provenance}

def refine_duration(voices, evidence, instrument=None):
    output, decisions = [], []
    for voice in voices:
        profile_name = instrument or voice.instrument
        profile = PROFILES[profile_name]
        notes = list(voice.notes)
        for index, note in enumerate(voice.notes):
            following = min((n.start for n in voice.notes if n.pitch==note.pitch and n.start>note.start),
                            default=np.inf)
            result = estimate_end(evidence[note.pitch],note,profile,following)
            if result is None or abs(result["excitation_end"]-note.end)<.018:
                continue
            notes[index] = replace(note,end=result["excitation_end"])
            decisions.append({"voice":voice.id,"index":index,"pitch":note.pitch,
                              "start":note.start,"baseline_end":note.end,
                              "instrument":profile_name,**result})
        output.append(replace(voice,notes=notes))
    return output, decisions
