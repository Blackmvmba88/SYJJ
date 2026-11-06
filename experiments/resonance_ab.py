"""Compare duration-only and observed-tail WAV renders on complete takes."""
import argparse
from collections import Counter
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import librosa
import numpy as np

from glide_arrangement.articulation import extract_evidence
from glide_arrangement.duration import refine_duration
from glide_arrangement.pedal import read_performance
from glide_arrangement.render import render_wav
from glide_arrangement.resonance import condition, rendering_dampers, rendering_tails
from glide_arrangement.transcribe import assign_voices, estimate_notes

def envelope(path):
    signal,rate = librosa.load(path,sr=22050)
    rms = librosa.feature.rms(y=signal,frame_length=1024,hop_length=220)[0]
    scale = np.percentile(rms,95)
    return rms/scale if scale>0 else rms

def evaluate(audio,instrument,midi=None):
    labels, pedal = [], None
    if midi:
        import mido
        labels, intervals = read_performance(mido.MidiFile(midi))
        pedal = [(i.down[0],i.up[0] if i.up else None) for i in intervals if i.channel==0]
    voices = assign_voices(estimate_notes(audio))
    evidence = extract_evidence(audio,{n.pitch for v in voices for n in v.notes})
    score,duration = refine_duration(voices,evidence,instrument)
    records = condition(score,evidence,instrument,pedal,duration)
    del evidence
    with TemporaryDirectory() as temp:
        a,b = (Path(temp)/name for name in ("A.wav","B.wav"))
        render_wav(score,a,note_tails=rendering_tails({"duration":duration}))
        data = {"duration":duration,"resonance":records}
        render_wav(score,b,note_tails=rendering_tails(data),note_dampers=rendering_dampers(data))
        ref = envelope(audio)
        rendered = [envelope(path) for path in (a,b)]
    length = max(len(ref),*[len(x) for x in rendered])
    ref, a_env, b_env = [np.pad(x,(0,length-len(x))) for x in [ref,*rendered]]
    time = np.arange(length)*220/22050
    masks = {"full":np.ones(length,dtype=bool)}
    for state in (False,True):
        selected = [n for n in labels if n.channel==0 and n.pedal_at_off==state
                    and not n.reattack_before_damper and not n.overlapping_key_events]
        mask = np.zeros(length,dtype=bool)
        for n in selected:
            start,stop = np.searchsorted(time,[n.off[0],n.off[0]+.25])
            mask[start:stop] = True
        if mask.any():
            masks["post_key_off_pedal_"+("down" if state else "up")] = mask
    return {"instrument":instrument,"duration_seconds":librosa.get_duration(path=audio),
            "events":len(records),"provenance":dict(Counter(r["provenance"] for r in records)),
            "observed_by_pedal":dict(Counter(r["pedal_state"] for r in records if r["provenance"]=="observed")),
            "envelope":{name:{"A_rms_mae":float(np.mean(abs(ref[mask]-a_env[mask]))),
                              "B_rms_mae":float(np.mean(abs(ref[mask]-b_env[mask]))),
                              "frames":int(mask.sum())} for name,mask in masks.items()}}

if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path)
    parser.add_argument("takes",nargs="+")
    parser.add_argument("--instrument",choices=("piano","guitar"),required=True)
    args = parser.parse_args()
    results = {}
    for name in args.takes:
        piano = args.instrument=="piano"
        audio = args.directory/f"{name}.{'mp3' if piano else 'wav'}"
        results[name] = evaluate(audio,args.instrument,args.directory/f"{name}.mid" if piano else None)
    print(json.dumps(results,indent=2))
