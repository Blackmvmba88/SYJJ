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
    render = commands.add_parser("render")
    render.add_argument("score", type=Path)
    render.add_argument("output", type=Path)
    render.add_argument("--bpm", type=float, default=120)
    compare = commands.add_parser("compare")
    compare.add_argument("reference", type=Path)
    compare.add_argument("candidate", type=Path)

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
        elif args.command == "render":
            from .render import render_midi, render_wav
            voices = read(args.score)
            if args.output.suffix.lower() == ".wav":
                render_wav(voices, args.output)
            elif args.output.suffix.lower() in {".mid", ".midi"}:
                args.output.write_bytes(render_midi(voices, args.bpm))
            else:
                raise ValueError("Usa una salida WAV o MIDI")
        else:
            from .compare import compare as compare_events
            print(json.dumps(compare_events(notes(args.reference), notes(args.candidate)), indent=2))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, f"{error}\n")

if __name__ == "__main__":
    main()
