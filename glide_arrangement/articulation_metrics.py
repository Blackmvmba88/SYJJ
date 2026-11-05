"""Independent articulation metrics for aligned audio or annotated events."""
from collections import Counter

import librosa
import numpy as np

def envelope_similarity(reference, candidate):
    """Compare level-normalized RMS envelopes without shifting either file."""
    def envelope(path):
        signal, _ = librosa.load(path, sr=22050, mono=True)
        rms = librosa.feature.rms(y=signal, frame_length=1024, hop_length=220)[0]
        scale = np.percentile(rms, 95)
        return rms/scale if scale > 0 else rms
    a, b = envelope(reference), envelope(candidate)
    length = max(len(a), len(b))
    a, b = (np.pad(x, (0, length-len(x))) for x in (a,b))
    correlation = float(np.corrcoef(a,b)[0,1]) if np.std(a)>0 and np.std(b)>0 else None
    return {"rms_correlation": correlation, "normalized_rms_mae": float(np.mean(abs(a-b)))}

def voice_continuity(voices):
    """Report gaps and overlaps between consecutive notes per voice."""
    result = {}
    for voice in voices:
        notes = sorted(voice.notes, key=lambda n:n.start)
        gaps = [b.start-a.end for a,b in zip(notes,notes[1:])]
        result[voice.id] = {
            "transitions": len(gaps),
            "within_25ms_or_overlapping": sum(gap <= .025 for gap in gaps),
            "mean_gap_seconds": float(np.mean(np.maximum(gaps, 0))) if gaps else None,
        }
    return result

def repeated_attack_accuracy(expected, predicted, tolerance=.075):
    """Score hand-labeled retriggers by voice, pitch and time."""
    keys = lambda entry: (entry["voice"], entry["pitch"])
    remaining = sorted((e for e in predicted if e["type"]=="retrigger"), key=lambda e:e["time"])
    labels = sorted((e for e in expected if e["type"]=="retrigger"), key=lambda e:e["time"])
    matched = 0
    total = len(remaining)
    for label in labels:
        for i, event in enumerate(remaining):
            if keys(event)==keys(label) and abs(event["time"]-label["time"])<=tolerance:
                remaining.pop(i)
                matched += 1
                break
    return {"matched":matched, "expected":len(labels), "predicted":total,
            "precision":matched/total if total else None,
            "recall":matched/len(labels) if labels else None}

def evaluate(reference, a, b, a_audio, b_audio):
    from .compare import compare
    from .score import load_score
    from .transcribe import estimate_notes

    reference_notes = estimate_notes(reference)
    report = {}
    for key, data, audio in (("A",a,a_audio),("B",b,b_audio)):
        voices = load_score(data)
        events = compare(reference_notes, estimate_notes(audio))
        report[key] = {
            "score_notes": sum(len(v.notes) for v in voices),
            "detected_events": events,
            "envelope": envelope_similarity(reference,audio),
            "voice_continuity": voice_continuity(voices),
            "articulation_decisions": dict(Counter(e["type"] for e in data.get("articulation",[]))),
        }
    return report
