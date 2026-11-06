"""Held-out velocity layers from a single NSynth instrument."""
import argparse
import json
from pathlib import Path
from statistics import mean

import librosa
import numpy as np

from glide_arrangement.instrument import Profile, REFERENCE_VELOCITY, fit_profile, render_profile
from glide_arrangement.score import Note, Voice
from glide_arrangement.spectrotemporal import RATE
from glide_arrangement.velocity import METHODS,fit_velocity
from .spectrotemporal_ab import metrics

TRAIN = {25,75,127}
TEST = {50,100}

def run(directory):
    sources = {}
    for path in directory.glob("*.wav"):
        try:
            pitch,vel = map(int,path.stem.split("-"))
        except ValueError:
            continue
        if 48<=pitch<=72 and vel in TRAIN|TEST:
            sources[pitch,vel] = path
    training = sorted((pitch,vel) for pitch,vel in sources if vel in TRAIN)
    testing = sorted((pitch,vel) for pitch,vel in sources if vel in TEST)
    if len(training)<8 or len(testing)<4 or {v for _,v in training}!=TRAIN:
        raise ValueError("Faltan ejemplos de entrenamiento o velocidades reservadas")
    examples = []
    for pitch,vel in training:
        samples,_ = librosa.load(sources[pitch,vel],sr=RATE,duration=.9)
        profile = fit_profile(samples,[Note(pitch,0,len(samples)/RATE,vel)],"piano")
        amplitude = np.asarray(profile.notes[pitch])*vel/REFERENCE_VELOCITY
        examples.append((pitch,vel,amplitude))
    model = fit_velocity(examples)
    entries = []
    for pitch,vel in testing:
        original,_ = librosa.load(sources[pitch,vel],sr=RATE,duration=.8)
        voice = Voice("solo","inner",[Note(pitch,0,len(original)/RATE,vel)])
        entry = {"pitch":pitch,"velocity":vel,"models":{}}
        for method in METHODS:
            matrix = model.predict(pitch,vel,method)*REFERENCE_VELOCITY/vel
            predicted = render_profile(Profile("piano",{pitch:matrix.tolist()}),[voice],length=len(original))
            entry["models"][method] = metrics(original,predicted,{"attack":[(0,.1)]})
        entries.append(entry)
    return {"train_velocities":sorted(TRAIN),"test_velocities":sorted(TEST),"training_examples":training,"test_examples":testing,
            "means":{method:{part:{metric:mean(e["models"][method][part][metric] for e in entries)
                                   for metric in ("raw_rms_mae","normalized_rms_mae","spectral_distance")}
                             for part in ("full","attack")} for method in METHODS},
            "details":entries}

if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path)
    print(json.dumps(run(parser.parse_args().directory),indent=2))
