"""Build key and binary damper references from performance MIDI events."""
from bisect import bisect_right
from collections import defaultdict, deque
from dataclasses import dataclass

@dataclass(frozen=True)
class PedalInterval:
    channel: int
    down: tuple[float,int]
    up: tuple[float,int] | None

@dataclass(frozen=True)
class KeyNote:
    channel: int
    pitch: int
    onset: tuple[float,int]
    off: tuple[float,int]
    pedal_at_on: bool
    pedal_at_off: bool
    pedal_during_key_seconds: float
    damper_end: float | None
    reattack_before_damper: bool

def read_performance(messages, threshold=64):
    """Input is a MIDI iterator with delta times in seconds."""
    pending = defaultdict(deque)
    down = {}
    intervals = defaultdict(list)
    key_events = defaultdict(list)
    time = 0.
    for order, message in enumerate(messages):
        time += message.time
        event = time,order
        if message.type=="control_change" and message.control==64:
            channel = message.channel
            if message.value>=threshold:
                down.setdefault(channel,event)
            elif channel in down:
                intervals[channel].append(PedalInterval(channel,down.pop(channel),event))
        elif message.type in {"note_on","note_off"}:
            key = message.channel,message.note
            if message.type=="note_on" and message.velocity:
                pending[key].append(event)
            elif pending[key]:
                key_events[key].append((pending[key].popleft(),event))
    for channel,start in down.items():
        intervals[channel].append(PedalInterval(channel,start,None))

    notes = []
    infinity = (float("inf"),0)
    for (channel,pitch), events in key_events.items():
        pedal = intervals[channel]
        starts = [p.down for p in pedal]
        for onset,off in events:
            first = max(0,bisect_right(starts,onset)-1)
            relevant = pedal[first:bisect_right(starts,off)]
            overlap = sum(max(0.,min(off[0],(p.up or infinity)[0])-max(onset[0],p.down[0]))
                          for p in relevant)
            at_on = any(p.down<=onset<(p.up or infinity) for p in relevant)
            at_off = any(p.down<=off<(p.up or infinity) for p in relevant)
            # A later strike cannot rescue a note already damped. If the key
            # is held when the pedal rises, the damper remains open.
            end = off
            reattack = False
            while end!=infinity:
                index = bisect_right(starts,end)-1
                pedal_end = pedal[index].up or infinity if index>=0 and pedal[index].down<=end else end
                held = [(s,e) for s,e in events if s<=end<e and s!=onset]
                next_end = max([end,pedal_end,*[e for _,e in held]])
                reattack |= any(onset<s<next_end for s,_ in events)
                if next_end==end:
                    break
                end = next_end
            notes.append(KeyNote(channel,pitch,onset,off,at_on,at_off,overlap,
                                 None if end==infinity else end[0],reattack))
    return sorted(notes,key=lambda n:n.onset), [p for row in intervals.values() for p in row]
