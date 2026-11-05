"""Evaluate frozen vNext.3 endpoints against key and damper MIDI references."""
import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
import json
from pathlib import Path
from statistics import mean

import numpy as np
from scipy.optimize import linear_sum_assignment

from glide_arrangement.articulation import extract_evidence
from glide_arrangement.duration import refine_duration
from glide_arrangement.transcribe import assign_voices, estimate_notes
from .pedal_reference import read_performance

def summarize(errors):
    return {key:{"matched":len(pairs),
                 "A_mae_seconds":mean(a for a,_ in pairs),
                 "v3_mae_seconds":mean(b for _,b in pairs)}
            for key,pairs in sorted(errors.items())}

def paired_errors(labels, a, b, horizon):
    if not labels or not a:
        return {}
    distance = np.abs(np.array([n.onset[0] for n in labels])[:,None]-[n.start for n in a])
    same_pitch = np.array([n.pitch for n in labels])[:,None]==[n.pitch for n in a]
    cost = np.where(same_pitch & (distance<=.10),distance,1000.)
    errors = defaultdict(list)
    rows, columns = linear_sum_assignment(cost)
    for row,col in zip(rows,columns):
        if cost[row,col]>=1000:
            continue
        n = labels[row]
        status = "down" if n.pedal_at_off else "up"
        history = "down" if n.pedal_at_on else "up"
        key_errors = (abs(a[col].end-n.off[0]),abs(b[col].end-n.off[0]))
        for name in ("key/all",f"key/off_pedal_{status}",f"key/pedal_{history}_to_{status}"):
            errors[name].append(key_errors)
        if n.damper_end is not None and n.damper_end<horizon and not n.reattack_before_damper:
            damper_errors = (abs(a[col].end-n.damper_end),abs(b[col].end-n.damper_end))
            for name in ("damper/all",f"damper/off_pedal_{status}"):
                errors[name].append(damper_errors)
    return summarize(errors)

def run_take(audio, midi, horizon):
    import mido

    labels, intervals = read_performance(mido.MidiFile(midi))
    labels = [n for n in labels if .12<n.onset[0] and n.off[0]<horizon-.30]
    a = assign_voices(estimate_notes(audio))
    evidence = extract_evidence(audio,{n.pitch for v in a for n in v.notes})
    b, decisions = refine_duration(a,evidence,"piano")
    flatten = lambda voices: [n for v in voices for n in v.notes]
    return {
        "midi_notes":len(labels),
        "midi_pedal_down_at_key_off":sum(n.pedal_at_off for n in labels),
        "midi_pedal_used_while_held":sum(n.pedal_during_key_seconds>0 for n in labels),
        "midi_open_or_beyond_clip_damper":sum(n.damper_end is None or n.damper_end>=horizon for n in labels),
        "midi_reattacks_before_damper":sum(n.reattack_before_damper for n in labels),
        "cc64_intervals":[asdict(interval) for interval in intervals if interval.down[0]<horizon],
        "groups":paired_errors(labels,flatten(a),flatten(b),horizon),
        "acoustic_end_provenance":dict(Counter(d["acoustic_end_provenance"] for d in decisions)),
    }

def bootstrap_performance(takes, seed=424, draws=10000):
    rng = np.random.default_rng(seed)
    output = {}
    group_names = sorted({name for take in takes for name in take["groups"]})
    for name in group_names:
        groups = [take["groups"][name] for take in takes if name in take["groups"]]
        delta = np.array([g["v3_mae_seconds"]-g["A_mae_seconds"] for g in groups])
        if len(groups)>1:
            draws_delta = rng.choice(delta,size=(draws,len(delta)),replace=True).mean(axis=1)
            interval = np.percentile(draws_delta,[2.5,97.5]).tolist()
        else:
            interval = None
        output[name] = {"performances":len(groups),"notes":sum(g["matched"] for g in groups),
                        "A_performance_mean_mae_seconds":mean(g["A_mae_seconds"] for g in groups),
                        "v3_performance_mean_mae_seconds":mean(g["v3_mae_seconds"] for g in groups),
                        "delta_seconds":float(delta.mean()),"bootstrap_95_seconds":interval}
    return output

if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path)
    parser.add_argument("takes",nargs="+")
    parser.add_argument("--seconds",type=float,default=45)
    args = parser.parse_args()
    takes = {stem:run_take(args.directory/f"{stem}.wav",args.directory/f"{stem}.mid",args.seconds)
             for stem in args.takes}
    print(json.dumps({"seconds":args.seconds,"takes":takes,
                      "aggregate":bootstrap_performance(list(takes.values()))},indent=2))
