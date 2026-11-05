"""Compare guitar endpoints with string-derived GuitarSet note annotations."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

from glide_arrangement.articulation import extract_evidence
from glide_arrangement.duration import refine_duration
from glide_arrangement.transcribe import assign_voices, estimate_notes
from .pedal_ab import bootstrap_performance, summarize

def evaluate(audio, data):
    reference = sorted((n["onset_s"],n["offset_s"],round(n["midi"]),n["string"])
                       for n in data["notes"] if n["offset_s"]>n["onset_s"])
    voices = assign_voices(estimate_notes(audio))
    a = [n for v in voices for n in v.notes]
    evidence = extract_evidence(audio,{n.pitch for n in a})
    refined, decisions = refine_duration(voices,evidence,"guitar")
    b = [n for v in refined for n in v.notes]
    starts = np.asarray([n[0] for n in reference])
    pitch = np.asarray([n[2] for n in reference])
    distance = np.abs(starts[:,None]-[n.start for n in a])
    cost = np.where((distance<=.10) & (pitch[:,None]==[n.pitch for n in a]),distance,1000.)
    rows, cols = linear_sum_assignment(cost)
    errors = defaultdict(list)
    for row,col in zip(rows,cols):
        if cost[row,col]>=1000:
            continue
        start,end,pitch,string = reference[row]
        values = (abs(a[col].end-end),abs(b[col].end-end))
        errors["annotation/all"].append(values)
        errors[f"annotation/string_{string}"].append(values)
        if any(s!=string and min(e,end)-max(t,start)>.03 for t,e,_,s in reference):
            errors["annotation/overlapping_strings"].append(values)
        following = next(((t,p) for t,_,p,s in reference[row+1:] if s==string),None)
        if following and -.035<=following[0]-end<=.12:
            label = "repeated_pitch" if following[1]==pitch else "near_pitch_transition"
            errors[f"annotation/{label}"].append(values)
    return {"track":data["track_id"],"player":data["player"],
            "reference_notes":len(reference),"estimated_notes":len(a),"groups":summarize(errors),
            "acoustic_end_provenance":dict(Counter(d["acoustic_end_provenance"] for d in decisions))}

if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path)
    parser.add_argument("rows",nargs="+")
    args = parser.parse_args()
    takes = {}
    for row in args.rows:
        data = json.loads((args.directory/f"{row}.json").read_text())["rows"][0]["row"]
        takes[row] = evaluate(args.directory/f"{row}.wav",data)
    print(json.dumps({"takes":takes,"aggregate":bootstrap_performance(list(takes.values()))},indent=2))
