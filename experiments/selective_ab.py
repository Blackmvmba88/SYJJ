"""Render A/B1/B2/B3 and score against audio and optional labeled notes."""
import argparse
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path

from glide_arrangement.articulation import extract_evidence
from glide_arrangement.articulation_metrics import envelope_similarity, repeated_attack_accuracy, voice_continuity
from glide_arrangement.compare import compare
from glide_arrangement.render import render_wav
from glide_arrangement.score import load_score
from glide_arrangement.selective import VARIANTS, refine_selective
from glide_arrangement.transcribe import assign_voices, estimate_notes

def flatten(voices):
    return [note for voice in voices for note in voice.notes]

def labeled_attacks(voices, truth):
    # This fixture has unambiguous pitch-to-voice ownership.
    owners = {}
    for voice in truth:
        for note in voice.notes:
            owners.setdefault(note.pitch,set()).add(voice.id)
    by_pitch = {}
    for voice in voices:
        for note in voice.notes:
            ids = owners.get(note.pitch,set())
            owner = next(iter(ids)) if len(ids)==1 else voice.id
            by_pitch.setdefault((owner,note.pitch),[]).append(note.start)
    return [{"type":"retrigger","voice":owner,"pitch":pitch,"time":time}
            for (owner,pitch),starts in by_pitch.items() for time in sorted(starts)[1:]]

def acceptance(a, b):
    """Declare non-regression limits before looking at results."""
    da, db = (x["events_vs_audio_estimate"] for x in (a,b))
    ra, rb = (x["envelope"]["rms_correlation"] for x in (a,b))
    tests = {"rms_improves": ra is not None and rb is not None and rb > ra}
    for metric in ("exact_pitch_precision","exact_pitch_recall"):
        tests[metric] = da[metric] is not None and db[metric] is not None and db[metric] >= da[metric]-.01
    for metric in ("onset_mae_seconds","end_mae_seconds"):
        tests[metric] = da[metric] is not None and db[metric] is not None and db[metric] <= da[metric]+.010
    return {"checks":tests,"passed":all(tests.values())}

def run(reference, directory, baseline=None, labels=None):
    directory.mkdir(parents=True,exist_ok=True)
    reference_notes = estimate_notes(reference)
    a = load_score(json.loads(baseline.read_text())) if baseline else assign_voices(reference_notes)
    truth = load_score(labels) if labels else None
    evidence = extract_evidence(reference,{n.pitch for n in flatten(a)})
    report = {}
    for variant in ("A",*VARIANTS):
        voices, decisions = (a,[]) if variant=="A" else refine_selective(a,evidence,variant)
        wav = directory/f"{variant}.wav"
        score = directory/f"{variant}.json"
        if score.resolve() in {path.resolve() for path in (baseline, reference) if path} or wav.resolve()==reference.resolve():
            raise ValueError("Usa una carpeta de salida separada de los archivos de referencia")
        score.write_text(json.dumps({"voices":[asdict(v) for v in voices],"articulation":decisions},indent=2)+"\n")
        render_wav(voices,wav)
        rendered_notes = estimate_notes(wav)
        item = {
            "score_notes":len(flatten(voices)),
            "decisions":dict(Counter(e["type"] for e in decisions)),
            "events_vs_audio_estimate":compare(reference_notes,rendered_notes),
            "envelope":envelope_similarity(reference,wav),
            "voice_continuity":voice_continuity(voices),
        }
        if truth is not None:
            item["score_vs_labels"] = compare(flatten(truth),flatten(voices))
            item["render_vs_labels"] = compare(flatten(truth),rendered_notes)
            item["retrigger_vs_labels"] = repeated_attack_accuracy(
                labels["articulation"],labeled_attacks(voices,truth))
        report[variant] = item
    report["B3_acceptance"] = acceptance(report["A"],report["B3"])
    (directory/"report.json").write_text(json.dumps(report,indent=2)+"\n")

if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference",type=Path)
    parser.add_argument("directory",type=Path)
    parser.add_argument("--baseline",type=Path)
    parser.add_argument("--labels",type=Path)
    args = parser.parse_args()
    run(args.reference,args.directory,args.baseline,json.loads(args.labels.read_text()) if args.labels else None)
