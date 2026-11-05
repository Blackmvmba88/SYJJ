"""Event-level A/B metrics. A is the reference and B the candidate."""
from collections import Counter
from statistics import mean

import numpy as np
from scipy.optimize import linear_sum_assignment

def compare(reference, candidate, onset_window=.20):
    a, b = list(reference), list(candidate)
    pairs = []
    if a and b:
        onset = np.abs(np.asarray([n.start for n in a])[:, None] - [n.start for n in b])
        pitch = np.abs(np.asarray([n.pitch for n in a])[:, None] - [n.pitch for n in b])
        cost = np.where(onset <= onset_window, onset + np.minimum(pitch, 24)*.02, 1000.)
        rows, cols = linear_sum_assignment(cost)
        pairs = [(a[i], b[j]) for i, j in zip(rows, cols) if onset[i,j] <= onset_window]
    def average(values):
        return mean(values) if pairs else None
    def register(notes):
        return dict(sorted(Counter(n.pitch//12-1 for n in notes).items()))
    exact = sum(x.pitch == y.pitch for x, y in pairs)
    return {
        "reference_notes": len(a), "candidate_notes": len(b), "aligned_notes": len(pairs),
        "reference_unmatched": len(a)-len(pairs), "candidate_unmatched": len(b)-len(pairs),
        "exact_pitch_matches": exact,
        "exact_pitch_fraction_aligned": exact/len(pairs) if pairs else None,
        "exact_pitch_precision": exact/len(b) if b else None,
        "exact_pitch_recall": exact/len(a) if a else None,
        "end_mae_seconds": average(abs(x.end-y.end) for x,y in pairs),
        "pitch_mae_semitones": average(abs(x.pitch-y.pitch) for x,y in pairs),
        "onset_mae_seconds": average(abs(x.start-y.start) for x,y in pairs),
        "duration_mae_seconds": average(abs((x.end-x.start)-(y.end-y.start)) for x,y in pairs),
        "reference_octaves": register(a), "candidate_octaves": register(b),
    }
