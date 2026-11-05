"""Evaluate note-off against time-aligned performance MIDI."""
import argparse
from collections import defaultdict, deque
import json
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

from glide_arrangement.articulation import extract_evidence
from glide_arrangement.duration import PROFILES, refine_duration
from glide_arrangement.transcribe import assign_voices, estimate_notes

def midi_labels(path, until):
    import mido
    notes = []
    time = 0.
    pending = defaultdict(deque)
    pedal = defaultdict(bool)
    for message in mido.MidiFile(path):
        time += message.time
        if time >= until:
            break
        if message.type == "control_change" and message.control == 64:
            pedal[message.channel] = message.value >= 64
        elif message.type == "note_on" and message.velocity > 0:
            pending[message.channel,message.note].append(time)
        elif message.type in {"note_on","note_off"} and pending[message.channel,message.note]:
            start = pending[message.channel,message.note].popleft()
            if start > .12 and time < until-.30:
                notes.append((message.note,start,time,pedal[message.channel]))
    return notes

def evaluate(reference, a, b, instrument):
    pitch, starts, ends, pedals = map(np.asarray,zip(*reference)) if reference else ([],[],[],[])
    gap = np.abs(np.asarray(starts)[:,None]-[n.start for n in a])
    exact = np.asarray(pitch)[:,None]==[n.pitch for n in a]
    cost = np.where(exact & (gap<=.10),gap,1000.)
    rows, cols = linear_sum_assignment(cost)
    errors = defaultdict(list)
    matches = 0
    for row,col in zip(rows,cols):
        if cost[row,col]>=1000:
            continue
        matches += 1
        note = a[col]
        register = "grave" if note.pitch<53 else "medio" if note.pitch<72 else "agudo"
        retrigger = any(p==pitch[row] and 0<=s-ends[row]<=.15 for p,s,_,_ in reference)
        articulation = "retrigger" if retrigger else "sin_retrigger_cercano"
        values = (abs(note.end-ends[row]),abs(b[col].end-ends[row]),note.end!=b[col].end)
        for group in ("total",f"registro/{register}",f"instrumento/{instrument}",
                      f"articulacion/{articulation}",f"pedal/{'abajo' if pedals[row] else 'arriba'}"):
            errors[group].append(values)
    groups = {}
    for group, values in sorted(errors.items()):
        original, refined, changed = zip(*values)
        groups[group] = {"matched":len(values),"edited":sum(changed),
                         "A_end_mae_seconds":float(np.mean(original)),
                         "duration_end_mae_seconds":float(np.mean(refined))}
    return {"reference_events":len(reference),"estimated_events":len(a),"matches":matches,
            "exact_pitch_onset_precision":matches/len(a) if a else None,
            "exact_pitch_onset_recall":matches/len(reference) if reference else None,
            "groups":groups}

def run(audio, midi, until, instrument):
    notes = estimate_notes(audio)
    voices = assign_voices(notes)
    evidence = extract_evidence(audio,{note.pitch for note in notes})
    refined, decisions = refine_duration(voices,evidence,instrument)
    a = [note for voice in voices for note in voice.notes]
    b = [note for voice in refined for note in voice.notes]
    result = evaluate(midi_labels(midi,until),a,b,instrument)
    result["edits"] = len(decisions)
    return result

if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio",type=Path)
    parser.add_argument("midi",type=Path)
    parser.add_argument("--seconds",type=float,required=True)
    parser.add_argument("--instrument",choices=PROFILES,default="piano")
    args = parser.parse_args()
    print(json.dumps(run(args.audio,args.midi,args.seconds,args.instrument),indent=2))
