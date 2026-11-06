"""Learn an additive instrument from isolated notes and play it from MIDI."""
from collections import defaultdict
from dataclasses import dataclass
import math

import librosa
import numpy as np
import soundfile as sf

from .pedal import read_performance
from .score import Note, Voice
from .spectrotemporal import HOP, RATE, Partial, _pedal_return, synthesize, track_partials

GRID = np.arange(0,.801,.02)
REFERENCE_VELOCITY = 80

@dataclass(frozen=True)
class Profile:
    instrument: str
    notes: dict

    def __post_init__(self):
        if self.instrument not in {"piano","guitar"} or not self.notes:
            raise ValueError("Perfil de instrumento vacío o desconocido")

    def to_json(self):
        return {"instrument":self.instrument,"notes":self.notes,"step_seconds":.02}

    @classmethod
    def from_json(cls,data):
        if data["step_seconds"]!=.02:
            raise ValueError("Resolución de perfil desconocida")
        notes = {}
        for pitch, values in data["notes"].items():
            key = int(pitch)
            array = np.asarray(values,dtype=float)
            if not (0<=key<=127 and array.shape==(8,len(GRID)) and np.all(np.isfinite(array))
                    and np.all(array>=0)):
                raise ValueError("Envolventes del perfil inválidas")
            notes[key] = array.tolist()
        return cls(data["instrument"],notes)

def fit_profile(audio, notes, instrument):
    """Fit smoothed amplitude knots with fixed harmonic centers on isolated notes."""
    if not notes:
        raise ValueError("Se necesitan notas aisladas")
    ordered = sorted(notes,key=lambda n:n.start)
    if any(a.end>b.start for a,b in zip(ordered,ordered[1:])):
        raise ValueError("Las notas de calibración deben estar aisladas")
    groups = defaultdict(list)
    for note in ordered:
        if note.end>len(audio)/RATE:
            raise ValueError("Nota de calibración fuera de la grabación")
        begin = round(note.start*RATE)
        segment = audio[begin:round(note.end*RATE)]
        local = Note(note.pitch,0,len(segment)/RATE,note.velocity)
        voice = Voice("fit","inner",[local],release=0)
        tracks = track_partials(segment,[voice],instrument)
        matrix = np.zeros((8,len(GRID)))
        for partial in tracks:
            time = np.arange(len(partial.amplitude))*HOP/RATE
            valid = time < local.end-.045
            if valid.any():
                matrix[partial.harmonic-1] = np.interp(GRID,time[valid],partial.amplitude[valid])
        matrix *= REFERENCE_VELOCITY/note.velocity
        groups[note.pitch].append(matrix)
    return Profile(instrument,{pitch:np.median(values,axis=0).tolist() for pitch,values in groups.items()})

def _interpolated_profile(profile,pitch):
    keys = sorted(profile.notes)
    i = int(np.searchsorted(keys,pitch))
    lower,upper = keys[max(0,i-1)],keys[min(i,len(keys)-1)]
    mix = 0 if lower==upper else np.clip((pitch-lower)/(upper-lower),0,1)
    return np.asarray(profile.notes[lower])*(1-mix)+np.asarray(profile.notes[upper])*mix

def render_profile(profile,voices,pedal=None,length=None):
    pedal = pedal or {}
    tracks = []
    for voice in voices:
        for index,note in enumerate(voice.notes):
            damper = _pedal_return(note.end,pedal.get(voice.id,())) if profile.instrument=="piano" else note.end
            end = damper+(.20 if profile.instrument=="piano" else .14)
            first = int(np.ceil(note.start*RATE/HOP))
            last = int(end*RATE/HOP)+1
            time = np.arange(first,last)*HOP/RATE
            age = np.maximum(0,time-note.start)
            closed = np.maximum(0,time-damper)
            for harmonic, knots in enumerate(_interpolated_profile(profile,note.pitch),1):
                stiffness = 2e-5 if profile.instrument=="piano" else 0
                hz = 440*2**((note.pitch-69)/12)*harmonic*math.sqrt(1+stiffness*(harmonic**2-1))
                if hz>=RATE/2-30:
                    break
                amplitude = np.interp(age,GRID,knots)
                # Extrapolation beyond the learned knot range is deliberately
                # bounded by simple instrument-specific decay, not copied audio.
                amplitude *= np.exp(-np.maximum(age-GRID[-1],0)*(1+.12*harmonic))
                amplitude *= np.exp(-closed*(18+harmonic))
                amplitude *= note.velocity/REFERENCE_VELOCITY
                if voice.expression:
                    amplitude *= np.interp(time,[p[0] for p in voice.expression],
                                           [p[1] for p in voice.expression])/127
                tracks.append(Partial(voice.id,index,harmonic,hz,note.start,end,first,amplitude))
    if length is None:
        length = max(1,math.ceil(max((p.end for p in tracks),default=0)*RATE))
    return synthesize(tracks,length)

def read_midi(path):
    import mido

    events = list(mido.MidiFile(path))
    notes, intervals = read_performance(events)
    channels = defaultdict(list)
    for note in notes:
        if note.channel!=9 and note.off[0]>note.onset[0]:
            velocity = events[note.onset[1]].velocity
            channels[note.channel].append(Note(note.pitch,note.onset[0],note.off[0],velocity))
    voices = [Voice(f"ch{channel}","inner",values) for channel,values in channels.items()]
    pedal = defaultdict(list)
    for interval in intervals:
        pedal[f"ch{interval.channel}"].append((interval.down[0],interval.up[0] if interval.up else None))
    return voices,pedal

def fit_file(path,notes,instrument):
    audio,_ = librosa.load(path,sr=RATE,mono=True)
    return fit_profile(audio,notes,instrument)

def write_profile_audio(profile,voices,pedal,path):
    sf.write(path,render_profile(profile,voices,pedal),RATE,subtype="FLOAT")
