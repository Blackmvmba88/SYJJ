"""Bounded analysis-by-synthesis search over an editable score."""
from dataclasses import replace
from functools import lru_cache
import math

import librosa
import numpy as np

from .instrument import render_profile
from .score import Note, Voice
from .spectrotemporal import RATE

def _features(audio, fft):
    return np.sqrt(np.abs(librosa.stft(audio,n_fft=fft,hop_length=128)))

def _residual_proposals(reference,mix,events,low,high,limit):
    fft,hop = 4096,256
    def spectrum(audio):
        return np.abs(librosa.stft(audio,n_fft=fft,hop_length=hop))
    source = spectrum(reference)
    residual = np.maximum(source-spectrum(mix),0)
    minimum = .13*np.percentile(source.max(axis=0),95)
    proposals = []
    for pitch in range(low,high+1):
        hz = 440*2**((pitch-69)/12)
        center = round(hz*fft/RATE)
        energy = residual[max(1,center-1):center+2].max(axis=0)
        octave = round(2*hz*fft/RATE)
        harmonic = residual[octave-1:octave+2].max(axis=0)
        active = (energy>minimum) & (harmonic>.08*energy)
        edges = np.flatnonzero(np.diff(np.r_[False,active,False]))
        for i,j in edges.reshape(-1,2):
            start,end = i*hop/RATE,min(j*hop/RATE,len(reference)/RATE)
            if j-i<9 or end<=start or any(n.pitch==pitch and n.start<end+.07 and n.end>start-.07 for n in events):
                continue
            proposals.append((float(np.median(energy[i:j])),Note(pitch,start,end,80)))
    return [n for _,n in sorted(proposals,key=lambda item:item[0],reverse=True)[:limit]]

def refine_score(reference,profile,voices,pedal=None,modes=("pitch","timing","missing"),
                 passes=2,max_edits=24):
    """Score each proposal against the polyphonic mixture, keeping a fixed profile."""
    if len(reference)<1024 or not np.all(np.isfinite(reference)):
        raise ValueError("Audio de referencia demasiado corto o inválido")
    if not 1<=passes<=4 or not 1<=max_edits<=100:
        raise ValueError("Presupuesto de búsqueda fuera de rango")
    if not set(modes)<= {"pitch","timing","missing"}:
        raise ValueError("Modo de refinamiento desconocido")
    by_id = {v.id:v for v in voices}
    if len(by_id)!=len(voices):
        raise ValueError("Las voces deben tener identificadores únicos")
    existing = set(by_id)
    generated = "inverse"
    while generated in existing:
        generated += "_"
    by_id[generated] = Voice(generated,"inner",[])
    pedal = dict(pedal or {})
    timelines = {tuple(tuple(interval) for interval in pedal.get(v.id,())) for v in voices}
    if len(timelines)==1:
        pedal[generated] = next(iter(timelines))
    length = len(reference)

    @lru_cache(maxsize=64)
    def sample(voice_id,note):
        voice = by_id[voice_id]
        offset = round(note.start*RATE)
        shift = offset/RATE
        local = replace(note,start=0.,end=note.end-note.start)
        points = [(t-shift,value) for t,value in voice.expression if t>shift]
        if voice.expression:
            times, values = zip(*voice.expression)
            points.insert(0,(0.,int(round(np.interp(shift,times,values)))))
        controls = {voice.id:[(a-shift,b-shift if b is not None else None)
                             for a,b in pedal.get(voice.id,())]}
        audio = render_profile(profile,[replace(voice,notes=[local],expression=points)],controls)
        return offset,audio[:max(0,length-offset)]

    events = [(v.id,n) for v in voices for n in v.notes]
    mix = np.zeros(length,dtype=np.float32)
    for voice_id,note in events:
        offset,signal = sample(voice_id,note)
        mix[offset:offset+len(signal)] += signal

    def attempt(voice_id,old,options,threshold):
        if not options:
            return old,None
        old_sample = sample(voice_id,old) if old is not None else None
        samples = [(option,*sample(voice_id,option)) for option in options]
        spans = [(offset,len(data)) for _,offset,data in samples]
        if old_sample is not None:
            spans.append((old_sample[0],len(old_sample[1])))
        lo = max(0,min(i for i,_ in spans)-1536)
        hi = min(length,max(i+n for i,n in spans)+1536)
        if hi-lo<1024:
            return old,None
        target = [_features(reference[lo:hi],fft) for fft in (512,2048)]
        def cost(audio):
            return sum(float(np.mean(abs(_features(audio,fft)-truth)))
                       for fft,truth in zip((512,2048),target))
        original = cost(mix[lo:hi])
        context = mix[lo:hi].copy()
        if old_sample is not None:
            offset,data = old_sample
            context[offset-lo:offset-lo+len(data)] -= data
        best,best_cost,best_audio = old,original,None
        for option,offset,data in samples:
            candidate = context.copy()
            candidate[offset-lo:offset-lo+len(data)] += data
            score = cost(candidate)
            if score<best_cost:
                best,best_cost,best_audio = option,score,candidate
        gain = (original-best_cost)/max(original,1e-8)
        if best_audio is None or gain<threshold:
            return old,None
        mix[lo:hi] = best_audio
        return best,{"voice":voice_id,"before":old.__dict__ if old else None,
                     "after":best.__dict__,"local_relative_gain":gain}

    edits = []
    for _ in range(passes):
        for i,(voice_id,note) in enumerate(events):
            if len(edits)>=max_edits:
                break
            def available(candidate):
                return not any(j!=i and key==voice_id and n.pitch==candidate.pitch
                               and n.start<candidate.end and n.end>candidate.start
                               for j,(key,n) in enumerate(events))
            if "pitch" in modes:
                options = [replace(note,pitch=p) for p in range(note.pitch-2,note.pitch+3)
                           if p!=note.pitch and min(profile.notes)<=p<=max(profile.notes)]
                note,edit = attempt(voice_id,note,[o for o in options if available(o)],.035)
                if edit:
                    edits.append({"operation":"pitch",**edit})
            if "timing" in modes and len(edits)<max_edits:
                shifts = (-.08,-.04,.04,.08)
                options = [replace(note,start=note.start+d) for d in shifts
                           if 0<=note.start+d<=note.end-.10]
                options += [replace(note,end=note.end+d) for d in shifts
                            if note.start+.10<=note.end+d<=length/RATE]
                note,edit = attempt(voice_id,note,[o for o in options if available(o)],.028)
                if edit:
                    edits.append({"operation":"timing",**edit})
            events[i] = voice_id,note

        if "missing" in modes and len(edits)<max_edits:
            candidates = _residual_proposals(reference,mix,[n for _,n in events],
                                            max(36,min(profile.notes)),min(88,max(profile.notes)),12)
            for candidate in candidates:
                if len(edits)>=max_edits:
                    break
                if any(n.pitch==candidate.pitch and n.start<candidate.end+.07
                       and n.end>candidate.start-.07 for _,n in events):
                    continue
                options = [replace(candidate,velocity=v) for v in (48,72,96)]
                note,edit = attempt(generated,None,options,.09)
                if edit:
                    events.append((generated,note))
                    edits.append({"operation":"missing",**edit})

    output = []
    for voice_id,voice in by_id.items():
        notes = sorted((n for key,n in events if key==voice_id),key=lambda n:n.start)
        if notes or voice_id!=generated:
            output.append(replace(voice,notes=notes))
    return output,edits
