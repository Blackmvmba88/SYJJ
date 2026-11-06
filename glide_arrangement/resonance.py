"""Experimental post-release observation, with conservative rendering fallback."""
from collections import defaultdict

import numpy as np

from .duration import PROFILES

def _stable_crossing(curve, note, damper, limit, max_tail):
    t = curve.time
    end = min(limit,damper+max_tail,t[-1])
    if end-damper<.095 or curve.partials is None:
        return None
    before = (t >= max(note.start+.035,note.end-.12)) & (t < note.end-.018)
    if not before.any():
        return None
    level = np.median(curve.energy[before])
    fundamental = np.median(curve.partials[0,before])
    if level <= 1e-7 or fundamental <= 1e-7:
        return None
    window = slice(np.searchsorted(t,damper),np.searchsorted(t,end,side="right"))
    indices = range(window.start,window.stop)
    threshold = 10**(-24/20)
    prior = False
    for i in indices:
        above = curve.energy[i] > level*threshold and curve.partials[0,i] > fundamental*threshold
        if not above and prior:
            j = np.searchsorted(t,t[i]+.070)
            if (j < window.stop
                    and np.max(curve.energy[i:j+1]) <= level*threshold
                    and np.max(curve.partials[0,i:j+1]) <= fundamental*threshold):
                return float(t[i])
        prior |= above
    return None

def _can_share_partial(pitch, other):
    return any(pitch-other==interval for interval in (0,12,19,24,28,31))

def condition(voices,evidence,instrument,pedal_intervals=None,duration=(),strings=None,string_evidence=None):
    """Keep score unchanged. Return independent tail observations or hypotheses."""
    strings = strings or {}
    pedal = sorted(pedal_intervals or (),key=lambda interval:interval[0])
    string_evidence = string_evidence or {}
    previous = {(d["voice"],d["index"]):d for d in duration}
    by_pitch = defaultdict(list)
    for voice in voices:
        for index,note in enumerate(voice.notes):
            by_pitch[note.pitch].append((voice.id,index,note))
    records = []
    voice_strings = strings
    for voice in voices:
        for index,note in enumerate(voice.notes):
            string = voice_strings.get(voice.id)
            isolated = string in string_evidence
            limit = min((other.start for v,i,other in by_pitch[note.pitch]
                         if (v,i)!=(voice.id,index) and other.start>=note.end
                         and (not isolated or voice_strings.get(v)==string)),default=np.inf)
            damper = note.end
            state = "unknown" if instrument=="piano" and pedal_intervals is None else "up"
            if instrument=="guitar":
                state = "not_applicable"
            if instrument=="piano":
                for down,up in pedal:
                    if down <= note.end and (up is None or note.end < up):
                        state,damper = "down",up
                        break
            base = previous.get((voice.id,index),{})
            profile = PROFILES[instrument]
            horizon = profile.max_tail
            # Mono pitch evidence cannot isolate a second note at the same
            # frequency, or a strong lower partial within the search window.
            overlap = any(other.start < min(limit,(damper or note.end)+horizon)
                          and other.end > note.end and other.start < note.end+.12
                          for pitch,events in by_pitch.items() if _can_share_partial(note.pitch,pitch)
                          for v,i,other in events if (v,i)!=(voice.id,index)
                          and (not isolated or voice_strings.get(v)==string))
            observed = None if damper is None or overlap or limit <= damper else _stable_crossing(
                (string_evidence[string] if isolated else evidence)[note.pitch],note,damper,limit,horizon)
            predicted = None
            if damper is not None and base.get("tail_decay_db_s",0)<0:
                predicted = min(damper+min(horizon,24/abs(base["tail_decay_db_s"])),limit)
            provenance = "observed" if observed is not None else "predicted" if predicted is not None else "indeterminate"
            records.append({"voice":voice.id,"index":index,"pitch":note.pitch,
                            "excitation_end":note.end,"damper_end":damper if instrument=="piano" and state!="unknown" else None,
                            "pedal_state":state,"string":string,"isolated_string":isolated,"shared_partial_risk":overlap,
                            "acoustic_end_observed":observed,"acoustic_end_predicted":predicted,
                            "provenance":provenance,"render_tail_seconds":observed-note.end if observed is not None else None})
    return records


def rendering_tails(data):
    """Apply observations only, retaining the previous rendering for uncertainty."""
    tails = {(d["voice"],d["index"]):d["tail_seconds"] for d in data.get("duration",[])}
    tails.update({(d["voice"],d["index"]):d["render_tail_seconds"]
                  for d in data.get("resonance",[]) if d["provenance"]=="observed"})
    return tails


def rendering_dampers(data):
    return {(d["voice"],d["index"]):d["damper_end"] for d in data.get("resonance",[])
            if d["provenance"]=="observed" and d["damper_end"] is not None}
