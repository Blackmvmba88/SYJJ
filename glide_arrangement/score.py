"""Editable arrangement with stable voice IDs and independent note events."""
from dataclasses import dataclass, field
import math

@dataclass(frozen=True)
class Note:
    pitch: int
    start: float
    end: float
    velocity: int = 75

    def __post_init__(self):
        if not (type(self.pitch) is int and 0 <= self.pitch <= 127
                and type(self.velocity) is int and 1 <= self.velocity <= 127
                and 0 <= self.start < self.end and math.isfinite(self.end)):
            raise ValueError("Nota inválida")

@dataclass
class Voice:
    id: str
    role: str
    notes: list[Note]
    instrument: str = "soft"
    # Points in seconds and MIDI CC11 units. Linear interpolation.
    expression: list[tuple[float, int]] = field(default_factory=list)
    attack: float = .025
    release: float = .14

    def __post_init__(self):
        if self.role not in {"bass", "inner", "lead"} or self.instrument not in {"soft", "keys", "strings", "bass"}:
            raise ValueError("Rol o instrumento desconocido")
        if not all(math.isfinite(x) and x >= 0 for x in (self.attack, self.release)):
            raise ValueError("Articulación inválida")
        previous = -1
        for time, value in self.expression:
            if not (math.isfinite(time) and time >= 0 and time > previous and type(value) is int and 0 <= value <= 127):
                raise ValueError("Curva de expresión inválida")
            previous = time

def load_score(data):
    voices = []
    for item in data["voices"]:
        fields = dict(item)
        fields["notes"] = [Note(**note) for note in fields["notes"]]
        voices.append(Voice(**fields))
    if len({voice.id for voice in voices}) != len(voices):
        raise ValueError("Los identificadores de voz deben ser únicos")
    return voices
