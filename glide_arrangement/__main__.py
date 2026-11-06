"""Offline CLI for arrangement reconstruction, rendering and A/B evaluation."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path

from .score import load_score

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    analyze = commands.add_parser("analyze")
    analyze.add_argument("audio", type=Path)
    analyze.add_argument("output", type=Path)
    analyze.add_argument("--polyphony", type=int, default=8)
    articulate = commands.add_parser("articulate")
    articulate.add_argument("audio", type=Path)
    articulate.add_argument("baseline", type=Path)
    articulate.add_argument("output", type=Path)
    articulate.add_argument("--variant", choices=("B1", "B2", "B3"))
    duration = commands.add_parser("duration")
    for name in ("audio","baseline","output"):
        duration.add_argument(name,type=Path)
    duration.add_argument("--instrument", choices=("piano","guitar","keys","bass","strings","soft"))
    resonance = commands.add_parser("resonance")
    for name in ("audio","baseline","output"):
        resonance.add_argument(name,type=Path)
    resonance.add_argument("--instrument",choices=("piano","guitar"),required=True)
    resonance.add_argument("--pedal-midi",type=Path)
    resonance.add_argument("--pedal-channel",type=int,choices=range(16),default=0)
    resonance.add_argument("--strings",type=Path)
    render = commands.add_parser("render")
    render.add_argument("score", type=Path)
    render.add_argument("output", type=Path)
    render.add_argument("--bpm", type=float, default=120)
    compare = commands.add_parser("compare")
    compare.add_argument("reference", type=Path)
    compare.add_argument("candidate", type=Path)

    experiment = commands.add_parser("articulation-ab")
    for name in ("reference", "a_score", "a_audio", "b_score", "b_audio"):
        experiment.add_argument(name, type=Path)

    args = parser.parse_args()
    def read(path):
        return load_score(json.loads(path.read_text()))
    def notes(path):
        if path.suffix.lower() == ".json":
            return [n for voice in read(path) for n in voice.notes]
        from .transcribe import estimate_notes
        return estimate_notes(path)
    try:
        if args.command == "analyze":
            from .transcribe import assign_voices, estimate_notes
            voices = assign_voices(estimate_notes(args.audio, args.polyphony))
            args.output.write_text(json.dumps({"voices": [asdict(v) for v in voices]}, indent=2)+"\n")
        elif args.command == "articulate":
            from .articulation import extract_evidence, refine
            if args.output.resolve() in {args.baseline.resolve(), args.audio.resolve()}:
                raise ValueError("Usa un archivo de salida distinto para conservar la referencia A")
            voices = read(args.baseline)
            evidence = extract_evidence(args.audio, {n.pitch for v in voices for n in v.notes})
            if args.variant:
                from .selective import refine_selective
                refined, decisions = refine_selective(voices, evidence, args.variant)
            else:
                refined, decisions = refine(voices, evidence)
            payload = {"voices": [asdict(v) for v in refined], "articulation": decisions}
            args.output.write_text(json.dumps(payload, indent=2)+"\n")
        elif args.command == "duration":
            from .articulation import extract_evidence
            from .duration import refine_duration
            if args.output.resolve() in {args.baseline.resolve(),args.audio.resolve()}:
                raise ValueError("Usa una salida distinta para conservar A")
            voices = read(args.baseline)
            evidence = extract_evidence(args.audio,{n.pitch for v in voices for n in v.notes})
            refined, decisions = refine_duration(voices,evidence,args.instrument)
            args.output.write_text(json.dumps(
                {"voices":[asdict(v) for v in refined],"duration":decisions},indent=2)+"\n")
        elif args.command == "resonance":
            from .articulation import extract_evidence
            from .resonance import condition
            if args.output.resolve() in {args.baseline.resolve(),args.audio.resolve()} or args.output.exists():
                raise ValueError("Usa un archivo de salida nuevo para conservar las referencias")
            data = json.loads(args.baseline.read_text())
            voices = load_score(data)
            pedal = None
            if args.pedal_midi:
                if args.instrument!="piano":
                    raise ValueError("CC64 solo se aplica al perfil de piano")
                import mido
                from .pedal import read_performance
                _, intervals = read_performance(mido.MidiFile(args.pedal_midi))
                pedal = [(i.down[0],i.up[0] if i.up else None)
                         for i in intervals if i.channel==args.pedal_channel]
                data["pedal_intervals"] = pedal
            strings, isolated = {}, {}
            if args.strings:
                if args.instrument!="guitar":
                    raise ValueError("Las pistas por cuerda solo se aplican a guitarra")
                layout = json.loads(args.strings.read_text())
                strings = layout["voices"]
                for string, wav in layout.get("audio",{}).items():
                    pitches = {n.pitch for v in voices if strings.get(v.id)==string for n in v.notes}
                    if pitches:
                        isolated[string] = extract_evidence(args.strings.parent/wav,pitches)
            evidence = extract_evidence(args.audio,{n.pitch for v in voices for n in v.notes})
            data["resonance"] = condition(voices,evidence,args.instrument,pedal,
                                         data.get("duration",[]),strings,isolated)
            args.output.write_text(json.dumps(data,indent=2)+"\n")
        elif args.command == "render":
            from .render import render_midi, render_wav
            data = json.loads(args.score.read_text())
            voices = load_score(data)
            if args.output.suffix.lower() == ".wav":
                from .resonance import rendering_dampers, rendering_tails
                tails = rendering_tails(data)
                render_wav(voices, args.output, note_tails=tails, note_dampers=rendering_dampers(data))
            elif args.output.suffix.lower() in {".mid", ".midi"}:
                args.output.write_bytes(render_midi(voices, args.bpm, pedal_intervals=data.get("pedal_intervals",())))
            else:
                raise ValueError("Usa una salida WAV o MIDI")
        elif args.command == "articulation-ab":
            from .articulation_metrics import evaluate
            a = json.loads(args.a_score.read_text())
            b = json.loads(args.b_score.read_text())
            print(json.dumps(evaluate(args.reference, a, b, args.a_audio, args.b_audio), indent=2))
        else:
            from .compare import compare as compare_events
            print(json.dumps(compare_events(notes(args.reference), notes(args.candidate)), indent=2))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"{error}\n")

if __name__ == "__main__":
    main()
