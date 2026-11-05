"""Generate the independent, annotated synthetic recording for vNext.2."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path

import numpy as np
import soundfile as sf

from glide_arrangement.score import Note, Voice

def generate(directory):
    directory.mkdir(parents=True,exist_ok=True)
    rate = 22050
    bass = Voice("bass","bass",[Note(45,.2,3.1),Note(43,3.1,6.1)],instrument="bass")
    inner = Voice("inner","inner",[Note(60,.32,2.9),Note(62,2.9,5.9)])
    lead = Voice("lead","lead",[Note(69,.42,1.28),Note(69,1.43,2.2),
                              Note(69,2.35,3.2),Note(72,3.35,5.75)],instrument="keys")
    voices = [bass,inner,lead]
    t = np.arange(round(6.4*rate))/rate
    audio = np.zeros_like(t)
    for voice, partials, decay in zip(voices,[(1,.18,.08),(1,.26,.14,.06),(1,.45,.21,.11)], [.21,.14,.8]):
        for note in voice.notes:
            local = t-note.start
            envelope = np.clip(local/.014,0,1)*np.clip((note.end+.05-t)/.08,0,1)
            envelope *= np.exp(-decay*np.maximum(local,0))
            hz = 440*2**((note.pitch-69)/12)
            tone = sum(gain*np.sin(2*np.pi*hz*k*local+.13*k) for k,gain in enumerate(partials,1))
            audio += .21*envelope*tone
    annotations = [{"voice":"lead","pitch":69,"time":t,"type":"retrigger"} for t in (1.43,2.35)]
    sf.write(directory/"holdout.wav",audio,rate)
    (directory/"holdout-labels.json").write_text(json.dumps(
        {"voices":[asdict(v) for v in voices],"articulation":annotations},indent=2)+"\n")

if __name__=="__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path)
    generate(parser.parse_args().directory)
