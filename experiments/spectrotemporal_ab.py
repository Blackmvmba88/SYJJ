"""Compare three renders with frozen MIDI events on complete recordings."""
import argparse
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
from glide_arrangement.spectrotemporal import RATE, render_conditioned
from glide_arrangement.transcribe import assign_voices, estimate_notes

METRIC_HOP = 256

def regions(voices, pedal, known):
    result = {"attack":[],"release":[]}
    if known:
        result.update({"release_pedal_up":[],"release_pedal_down":[]})
    for voice in voices:
        for note in voice.notes:
            result["attack"].append((note.start,note.start+.10))
            window = (note.end,note.end+.25)
            result["release"].append(window)
            if known:
                down = any(start<=note.end and (end is None or note.end<end) for start,end in pedal)
                result["release_pedal_down" if down else "release_pedal_up"].append(window)
    return result

def masks(length,windows):
    result = {"full":np.ones(length,dtype=bool)}
    for name, spans in windows.items():
        mask = np.zeros(length,dtype=bool)
        for start,end in spans:
            first,last = np.ceil(np.array([start,end])*RATE/METRIC_HOP).astype(int)
            mask[first:last] = True
        if mask.any():
            result[name] = mask
    return result

def metrics(reference,candidate,windows):
    length = max(len(reference),len(candidate))
    a,b = (np.pad(x,(0,length-len(x))) for x in (reference,candidate))
    def rms(y):
        return librosa.feature.rms(y=y,frame_length=1024,hop_length=METRIC_HOP)[0]
    raw_a,raw_b = rms(a),rms(b)
    a = a/max(float(np.percentile(raw_a,95)),1e-8)
    b = b/max(float(np.percentile(raw_b,95)),1e-8)
    ra,rb = rms(a),rms(b)
    selections = masks(len(ra),windows)
    report = {name:{"frames":int(mask.sum()),
                    "normalized_rms_mae":float(np.mean(abs(ra[mask]-rb[mask]))),
                    "raw_rms_mae":float(np.mean(abs(raw_a[mask]-raw_b[mask]))),
                    "spectral_distance":0.}
              for name,mask in selections.items()}
    # Mean absolute log magnitude difference, above a fixed normalized floor.
    for fft in (512,2048,8192):
        def log_spectrum(signal):
            mag = np.abs(librosa.stft(signal,n_fft=fft,hop_length=METRIC_HOP))
            return np.log1p(mag*(200/fft))
        diff = np.mean(abs(log_spectrum(a)-log_spectrum(b)),axis=0)
        for name,mask in selections.items():
            report[name]["spectral_distance"] += float(np.mean(diff[mask]))/3
    return report

def evaluate(audio,instrument,midi=None):
    pedal = []
    if midi:
        import mido
        _, intervals = read_performance(mido.MidiFile(midi))
        pedal = [(i.down[0],i.up[0] if i.up else None) for i in intervals if i.channel==0]
    base = assign_voices(estimate_notes(audio))
    evidence = extract_evidence(audio,{n.pitch for v in base for n in v.notes})
    voices,duration = refine_duration(base,evidence,instrument)
    resonance = condition(voices,evidence,instrument,pedal if midi else None,duration)
    del evidence
    a_data = {"duration":duration}
    b_data = {**a_data,"resonance":resonance}
    reference,_ = librosa.load(audio,sr=RATE)
    windows = regions(voices,pedal,midi is not None)
    report = {}
    with TemporaryDirectory() as temp:
        for variant in ("A","B","C"):
            output = Path(temp)/f"{variant}.wav"
            if variant=="C":
                render_conditioned(audio,voices,output,instrument,rendering_tails(a_data),pedal)
            else:
                data = a_data if variant=="A" else b_data
                render_wav(voices,output,sample_rate=RATE,note_tails=rendering_tails(data),
                           note_dampers=rendering_dampers(data))
            candidate,_ = librosa.load(output,sr=RATE)
            report[variant] = metrics(reference,candidate,windows)
            output.unlink()
    return {"instrument":instrument,"seconds":len(reference)/RATE,
            "frozen_notes":sum(len(v.notes) for v in voices),"metrics":report}

if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path)
    parser.add_argument("takes",nargs="+")
    parser.add_argument("--instrument",choices=("piano","guitar"),required=True)
    args = parser.parse_args()
    result = {}
    for name in args.takes:
        piano = args.instrument=="piano"
        suffix = "mp3" if piano else "wav"
        result[name] = evaluate(args.directory/f"{name}.{suffix}",args.instrument,
                                args.directory/f"{name}.mid" if piano else None)
    print(json.dumps(result,indent=2))
