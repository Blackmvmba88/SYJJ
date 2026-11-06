"""Experimental additive resynthesis with soft spectral ownership."""
from dataclasses import dataclass

import librosa
import numpy as np
import soundfile as sf
from scipy.ndimage import gaussian_filter1d
from scipy.signal import get_window

RATE = 22050
HOP = 256
FFT = 4096
WINDOW = 2048

@dataclass(frozen=True)
class Partial:
    voice: str
    note_index: int
    harmonic: int
    frequency: float
    start: float
    end: float
    first_frame: int
    amplitude: np.ndarray

def _pedal_return(end, pedal):
    for down, up in pedal:
        if down <= end and (up is None or end < up):
            return min(end+3,up if up is not None else end+3)
    return end

def track_partials(audio, voices, instrument, tails=None, pedal=()):
    """Allocate mixture power across active note/partial candidates once per bin."""
    if instrument not in {"piano","guitar"}:
        raise ValueError("El perfil debe ser piano o guitarra")
    tails = tails or {}
    spectrum = np.abs(librosa.stft(audio,n_fft=FFT,win_length=WINDOW,hop_length=HOP))**2
    ownership = np.zeros_like(spectrum)
    frames = spectrum.shape[1]
    candidates = []
    for voice in voices:
        for index,note in enumerate(voice.notes):
            tail = tails.get((voice.id,index),voice.release)
            damper = _pedal_return(note.end,pedal) if instrument=="piano" else note.end
            end = min(len(audio)/RATE,max(note.end+tail,damper+.16 if damper>note.end else note.end))
            first = max(0,int(np.ceil(note.start*RATE/HOP)))
            last = min(frames,int(end*RATE/HOP)+1)
            if last<=first:
                continue
            time = np.arange(first,last)*HOP/RATE
            # Held strings win ambiguous bins over old pedal tails. The
            # observation still determines each partial's absolute amplitude.
            prior = np.exp(-2*np.maximum(time-note.end,0)-8*np.maximum(time-damper,0))
            fundamental = 440*2**((note.pitch-69)/12)
            for harmonic in range(1,9):
                stiffness = 2e-5 if instrument=="piano" else 0
                frequency = fundamental*harmonic*np.sqrt(1+stiffness*(harmonic**2-1))
                if frequency >= RATE/2-30:
                    break
                center = frequency*FFT/RATE
                bins = np.arange(max(1,round(center)-3),min(FFT//2,round(center)+4))
                shape = np.exp(-.5*((bins-center)/1.25)**2)
                weights = (shape[:,None]*prior[None,:]/harmonic**.85).astype(np.float32)
                ownership[bins,first:last] += weights
                candidates.append((voice.id,index,harmonic,frequency,note.start,end,first,last,bins,weights))
    scale = FFT*np.sum(get_window("hann",WINDOW)**2)/4
    tracks = []
    for voice,index,harmonic,frequency,start,end,first,last,bins,weights in candidates:
        mixture = spectrum[bins,first:last]
        total = ownership[bins,first:last]
        # Reject bins far from all candidate frequencies rather than giving
        # their whole power to the only note with a very weak claim.
        fraction = weights / np.maximum(total,.09)
        power = np.sum(mixture*fraction,axis=0)
        amplitude = gaussian_filter1d(np.sqrt(power/scale),.85,mode="nearest")
        tracks.append(Partial(voice,index,harmonic,frequency,start,end,first,amplitude))
    return tracks

def synthesize(tracks, length):
    output = np.zeros(length,dtype=np.float32)
    for partial in tracks:
        start = round(partial.start*RATE)
        end = min(length,round(partial.end*RATE))
        if end<=start:
            continue
        samples = np.arange(start,end)
        frames = (partial.first_frame+np.arange(len(partial.amplitude)))*HOP
        amplitude = np.interp(samples,frames,partial.amplitude)
        # Oscillators have independent phase and short boundary fades. No
        # waveform samples or reference phases enter the synthesized signal.
        amplitude *= np.clip((samples-start)/(.009*RATE),0,1)
        amplitude *= np.clip((end-samples)/(.018*RATE),0,1)
        phase = 2*np.pi*partial.frequency*(samples-start)/RATE+.17*partial.harmonic
        output[start:end] += (amplitude*np.sin(phase)).astype(np.float32)
    return output

def render_conditioned(path,voices,output,instrument,tails=None,pedal=()):
    reference,_ = librosa.load(path,sr=RATE,mono=True)
    tracks = track_partials(reference,voices,instrument,tails,pedal)
    sf.write(output,synthesize(tracks,len(reference)),RATE,subtype="FLOAT")
    return tracks
