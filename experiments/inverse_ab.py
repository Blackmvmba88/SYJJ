"""Score inverse synthesis against MIDI labels, including a controlled mixture."""
import argparse
from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import librosa
import numpy as np
import soundfile as sf
from scipy.optimize import linear_sum_assignment

from glide_arrangement.instrument import Profile, read_midi
from glide_arrangement.inverse import refine_score
from glide_arrangement.score import Note, Voice
from glide_arrangement.spectrotemporal import RATE
from glide_arrangement.transcribe import assign_voices, estimate_notes

def score(reference,voices):
    predicted = [n for v in voices for n in v.notes]
    pairs = []
    if reference and predicted:
        time = np.abs(np.asarray([n.start for n in reference])[:,None]-[n.start for n in predicted])
        pitch = np.asarray([n.pitch for n in reference])[:,None]==[n.pitch for n in predicted]
        cost = np.where(pitch & (time<=.05),time,1000.)
        rows,cols = linear_sum_assignment(cost)
        pairs = [(reference[i],predicted[j]) for i,j in zip(rows,cols) if cost[i,j]<1000]
    complete = [(a,b) for a,b in pairs if abs(a.end-b.end)<=max(.05,.20*(a.end-a.start))]
    mean = lambda values: float(np.mean(values)) if values else None
    return {"reference":len(reference),"predicted":len(predicted),"matched_pitch_onset":len(pairs),
            "precision":len(pairs)/len(predicted) if predicted else None,
            "recall":len(pairs)/len(reference) if reference else None,
            "f1":2*len(pairs)/(len(reference)+len(predicted)) if reference or predicted else None,
            "f1_with_offset":2*len(complete)/(len(reference)+len(predicted)) if reference or predicted else None,
            "onset_mae_seconds":mean([abs(a.start-b.start) for a,b in pairs]),
            "offset_mae_seconds":mean([abs(a.end-b.end) for a,b in pairs])}

def evaluate(audio,profile,reference,initial,pedal=(),max_edits=24):
    result = {"A":score(reference,initial)}
    for name,modes in (("pitch",("pitch",)),("timing",("timing",)),
                       ("missing",("missing",)),("joint",("pitch","timing","missing"))):
        refined,edits = refine_score(audio,profile,initial,{v.id:pedal for v in initial},
                                     modes,passes=1,max_edits=max_edits)
        result[name] = {**score(reference,refined),"edits":dict(Counter(e["operation"] for e in edits)),
                        "mean_local_objective_gain":float(np.mean([e["local_relative_gain"] for e in edits]))
                        if edits else None}
    return result

def controlled(audio,midi,profile):
    signal,_ = librosa.load(audio,sr=RATE)
    voices,_ = read_midi(midi)
    samples = {}
    for note in sorted((n for v in voices for n in v.notes),key=lambda n:n.start):
        samples.setdefault(note.pitch,note)
    truth = [Note(48,.20,.75,100),Note(52,.28,.83,100),Note(56,.44,1.03,100),
             Note(60,1.13,1.68,100),Note(64,1.22,1.79,100),Note(68,1.31,1.88,100)]
    mixture = np.zeros(int(2.2*RATE),dtype=np.float32)
    for note in truth:
        original = samples[note.pitch]
        start = round(note.start*RATE)
        length = round((note.end-note.start)*RATE)
        offset = round(original.start*RATE)
        mixture[start:start+length] += signal[offset:offset+length]
    initial = [replace(n,pitch=51) if n.pitch==52 else
               replace(n,start=n.start+.08) if n.pitch==60 else n for n in truth if n.pitch!=56]
    return evaluate(mixture,profile,truth,[Voice("candidate","inner",initial)],max_edits=12)

def external(audio,midi,profile,seconds):
    signal,_ = librosa.load(audio,sr=RATE,duration=seconds)
    voices,pedal = read_midi(midi)
    truth = [n for v in voices for n in v.notes if .12<n.start and n.end<seconds-.25]
    with TemporaryDirectory() as directory:
        clipped = Path(directory)/"clip.wav"
        sf.write(clipped,signal,RATE,subtype="FLOAT")
        estimated = estimate_notes(clipped)
    initial = assign_voices(n for n in estimated if .12<n.start and n.end<seconds-.25)
    return evaluate(signal,profile,truth,initial,pedal.get("ch0",()),max_edits=16)

if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("audio","midi","profile"):
        parser.add_argument(name,type=Path)
    parser.add_argument("--external",type=float,metavar="SECONDS")
    args = parser.parse_args()
    profile = Profile.from_json(json.loads(args.profile.read_text()))
    report = (external(args.audio,args.midi,profile,args.external) if args.external
              else controlled(args.audio,args.midi,profile))
    print(json.dumps(report,indent=2))
