"""Fit on odd isolated pitches and evaluate untouched even pitches."""
import argparse
import json
from pathlib import Path
from statistics import mean
from tempfile import TemporaryDirectory

import librosa

from glide_arrangement.instrument import fit_profile, read_midi, render_profile
from glide_arrangement.render import render_wav
from glide_arrangement.score import Note, Voice
from glide_arrangement.spectrotemporal import RATE
from .spectrotemporal_ab import metrics

def run(audio,midi,profile_path):
    signal,_ = librosa.load(audio,sr=RATE)
    voices,_ = read_midi(midi)
    notes = [n for voice in voices for n in voice.notes if 45<=n.pitch<=72 and n.end<=len(signal)/RATE]
    pitches = [n.pitch for n in notes]
    if len(pitches)!=28 or len(set(pitches))!=28:
        raise ValueError("Se esperaba una nota aislada por altura MIDI de 45 a 72")
    train = [n for n in notes if n.pitch%2]
    test = [n for n in notes if not n.pitch%2]
    profile = fit_profile(signal,train,"piano")
    profile_path.write_text(json.dumps(profile.to_json(),indent=2)+"\n")
    details = {}
    with TemporaryDirectory() as temp:
        a = Path(temp)/"A.wav"
        for note in test:
            sample = signal[round(note.start*RATE):round(note.end*RATE)]
            voice = Voice("solo","inner",[Note(note.pitch,0,note.end-note.start,note.velocity)],
                          instrument="keys",release=0)
            render_wav([voice],a,sample_rate=RATE)
            baseline,_ = librosa.load(a,sr=RATE)
            learned = render_profile(profile,[voice],length=len(sample))
            windows = {"attack":[(0,.10)]}
            details[note.pitch] = {"fixed":metrics(sample,baseline,windows),
                                   "learned":metrics(sample,learned,windows)}
    return {"train_pitches":[n.pitch for n in train],"test_pitches":[n.pitch for n in test],
            "means":{variant:{part:{metric:mean(v[variant][part][metric] for v in details.values())
                                    for metric in ("spectral_distance","normalized_rms_mae","raw_rms_mae")}
                              for part in ("full","attack")} for variant in ("fixed","learned")},
            "details":details}

if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("audio","midi","profile"):
        parser.add_argument(name,type=Path)
    args = parser.parse_args()
    if args.profile.resolve() in {args.audio.resolve(),args.midi.resolve()}:
        parser.error("Usa un archivo nuevo para el perfil")
    print(json.dumps(run(args.audio,args.midi,args.profile),indent=2))
