"""Command line: `melograph recording.mp3` → `recording.musicxml`."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import warnings
from fractions import Fraction
from pathlib import Path
from urllib.parse import unquote

from . import __version__, ui
from .audio import AUDIO_SUFFIXES, MIDI_SUFFIXES, SAMPLE_RATE, AudioError
from .i18n import language, set_language, t


class Problem(Exception):
    """Something the user can fix; shown without a traceback."""


# ── arguments ───────────────────────────────────────────────────────────────


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="melograph", description=t("usage"), add_help=False)
    parser.add_argument("input", nargs="*", type=Path, metavar=t("meta_file"), help=t("arg_input"))
    parser.add_argument("-h", "--help", action="help", help=t("arg_help"))
    parser.add_argument("--version", action="version", version=f"Melograph {__version__}", help=t("arg_version"))
    parser.add_argument("--lang", choices=["de", "en"], help=t("arg_lang"))

    notation = parser.add_argument_group(t("group_notation"))
    notation.add_argument("--title", metavar="TEXT", help=t("arg_title"))
    notation.add_argument("--time", metavar="N/N", help=t("arg_time"))
    notation.add_argument("--pickup", type=float, metavar="N", help=t("arg_pickup"))
    notation.add_argument("--key", metavar="KEY", help=t("arg_key"))
    notation.add_argument("--grid", type=int, choices=[8, 16, 32], default=16, help=t("arg_grid"))
    notation.add_argument("--triplets", choices=["auto", "on", "off"], default="auto", help=t("arg_triplets"))
    tempo = notation.add_mutually_exclusive_group()
    tempo.add_argument("--double-time", action="store_true", help=t("arg_double"))
    tempo.add_argument("--half-time", action="store_true", help=t("arg_half"))
    notation.add_argument("--split", metavar="C4", help=t("arg_split"))
    notation.add_argument("--voices", type=int, choices=[1, 2], default=2, help=t("arg_voices"))
    notation.add_argument("--swing", choices=["auto", "on", "off"], default="auto", help=t("arg_swing"))
    notation.add_argument("--pedal", choices=["auto", "lines", "signs", "text", "off"], default="auto", help=t("arg_pedal"))
    notation.add_argument("--chords", action="store_true", help=t("arg_chords"))
    notation.add_argument("--composer", metavar="TEXT", help=t("arg_composer"))
    notation.add_argument("--no-graces", action="store_true", help=t("arg_no_graces"))
    notation.add_argument("--no-staccato", action="store_true", help=t("arg_no_staccato"))
    notation.add_argument("--no-dynamics", action="store_true", help=t("arg_no_dynamics"))
    notation.add_argument("--no-hairpins", action="store_true", help=t("arg_no_hairpins"))
    notation.add_argument("--no-slurs", action="store_true", help=t("arg_no_slurs"))
    notation.add_argument("--no-accents", action="store_true", help=t("arg_no_accents"))
    notation.add_argument("--no-ottava", action="store_true", help=t("arg_no_ottava"))
    notation.add_argument("--no-clef-changes", action="store_true", help=t("arg_no_clef_changes"))
    notation.add_argument("--no-tempo-changes", action="store_true", help=t("arg_no_tempo_changes"))
    notation.add_argument("--no-ornaments", action="store_true", help=t("arg_no_ornaments"))

    output = parser.add_argument_group(t("group_output"))
    output.add_argument("-o", "--output", metavar="PATH", help=t("arg_output"))  # str: a trailing / means folder
    output.add_argument("--pdf", action="store_true", help=t("arg_pdf"))
    output.add_argument("--no-midi", action="store_true", help=t("arg_no_midi"))
    output.add_argument("--overwrite", action="store_true", help=t("arg_overwrite"))
    opening = output.add_mutually_exclusive_group()
    opening.add_argument("--open", action="store_true", help=t("arg_open"))
    opening.add_argument("--no-open", action="store_true", help=t("arg_no_open"))
    output.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto", help=t("arg_device"))
    output.add_argument("--fresh", action="store_true", help=t("arg_fresh"))
    return parser


def _time_signature(text: str | None) -> tuple[int, int] | None:
    if not text:
        return None
    match = re.fullmatch(r"\s*(\d{1,2})\s*/\s*(2|4|8|16)\s*", text)
    if not match or int(match.group(1)) < 1:
        raise Problem(t("err_time", value=text))
    return int(match.group(1)), int(match.group(2))


def _pitch(text: str | None) -> int | None:
    if not text:
        return None
    if text.isdigit() and 21 <= int(text) <= 108:
        return int(text)
    match = re.fullmatch(r"\s*([A-Ha-h])(#|b|is|es|s)?(-?\d)\s*", text)
    if not match:
        raise Problem(t("err_split", value=text))
    letter = match.group(1).upper()
    base = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11, "H": 11}[letter]
    alter = {"#": 1, "is": 1, "b": -1, "es": -1, "s": -1, None: 0}[match.group(2)]
    return 12 * (int(match.group(3)) + 1) + base + alter


# ── choosing files ──────────────────────────────────────────────────────────


def _user_dir(name: str, fallback: str) -> Path:
    try:
        found = subprocess.run(["xdg-user-dir", name], capture_output=True, text=True, timeout=3).stdout.strip()
        if found:
            return Path(found)
    except (OSError, subprocess.SubprocessError):
        pass
    return Path.home() / fallback


def _recent_recordings(limit: int = 8) -> list[Path]:
    folders = [Path.cwd(), _user_dir("DESKTOP", "Desktop"), _user_dir("DOWNLOAD", "Downloads"), _user_dir("MUSIC", "Music")]
    found: dict[Path, float] = {}
    for folder in folders:
        try:
            for entry in folder.iterdir():
                if entry.suffix.lower() in AUDIO_SUFFIXES | MIDI_SUFFIXES and entry.is_file():
                    found[entry.resolve()] = entry.stat().st_mtime
        except OSError:
            continue
    return sorted(found, key=found.get, reverse=True)[:limit]


def _dropped_path(text: str) -> Path:
    """A path as typed, pasted or dragged into the terminal."""
    text = text.strip()
    if text.startswith("file://"):
        text = unquote(text[7:])
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        text = text[1:-1]
    else:
        text = text.replace("\\ ", " ")
    return Path(text).expanduser()


def _ask_for_file() -> Path:
    from rich.text import Text

    recent = _recent_recordings()
    ui.console.print(Text("  " + t("pick_title"), style="bold"))
    if recent:
        ui.console.print()
        for number, path in enumerate(recent, start=1):
            line = Text(f"  {number:>2}  ", style=ui.ACCENT)
            line.append(path.name, style="default")
            line.append(f"   {ui.short(path.parent)}", style=ui.DIM)
            ui.console.print(line, no_wrap=True, overflow="ellipsis")
    ui.console.print()
    while True:
        prompt = Text("  " + t("pick_prompt" if recent else "pick_prompt_plain"), style=ui.DIM).append(" › ", style=ui.ACCENT)
        answer = ui.console.input(prompt).strip()
        if not answer:
            continue
        if answer.isdigit() and 1 <= int(answer) <= len(recent):
            return recent[int(answer) - 1]
        path = _dropped_path(answer)
        if path.is_file():
            return path
        ui.error(t("pick_invalid", path=answer))


def _targets(source: Path, given: str | None, overwrite: bool, interactive: bool, suffixes: list[str]) -> Path:
    """Where the results go (path without suffix). Never replaces a file unasked."""
    output = Path(given).expanduser() if given else None
    if output is None:
        base = source.with_suffix("")
    elif output.is_dir() or given.endswith(os.sep):
        output.mkdir(parents=True, exist_ok=True)
        base = output / source.stem
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        base = output.with_suffix("") if output.suffix.lower() in (".musicxml", ".xml", ".mxl") else output
    def taken(candidate: Path) -> list[Path]:
        files = [candidate.with_name(candidate.name + suffix) for suffix in suffixes]
        return [f for f in files if f.exists() and f.resolve() != source.resolve()]

    existing = taken(base)
    if overwrite or not existing:
        return base
    if interactive:
        from rich.text import Text

        names = ", ".join(f.name for f in existing)
        prompt = Text("  " + t("overwrite_ask", name=names), style="default").append(f" {t('yes_no')} ", style=ui.DIM)
        answer = ui.console.input(prompt).strip().lower()
        ui.console.print()
        if answer == "" or answer.startswith(t("yes_keys")) or answer.startswith("y"):
            return base
    number = 2
    while taken(base.with_name(f"{base.name} ({number})")):
        number += 1
    return base.with_name(f"{base.name} ({number})")


def _title_from(path: Path) -> str:
    title = re.sub(r"\s*[\[(][A-Za-z0-9_-]{6,}[\])]\s*$", "", path.stem)  # trailing video ids
    title = re.sub(r"[_]+", " ", title).strip()
    return title or path.stem


# ── MuseScore ───────────────────────────────────────────────────────────────


def _musescore() -> str | None:
    for name in ("mscore", "musescore", "mscore4", "MuseScore4", "musescore4", "mscore4portable", "MuseScore-Studio"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _open(path: Path) -> bool:
    program = _musescore() or shutil.which("xdg-open")
    if not program:
        return False
    subprocess.Popen(
        [program, str(path)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return True


def _pdf(score: Path, pdf: Path, title: str) -> bool:
    """MuseScore engraves the PDF when it is installed; otherwise Verovio does, as in the window."""
    program = _musescore()
    if program:
        environment = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        try:
            result = subprocess.run([program, "-o", str(pdf), str(score)], capture_output=True, env=environment, timeout=300)
            if result.returncode == 0 and pdf.exists():
                return True
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        from PySide6.QtGui import QGuiApplication

        from .render import engrave, register_fonts, write_pdf

        app = QGuiApplication.instance() or QGuiApplication(["melograph", "-platform", "offscreen"])
        register_fonts()
        write_pdf(engrave(score.read_text(encoding="utf-8"), lambda quarters: quarters).pages, pdf, title)
        del app
    except Exception:
        return False
    return pdf.exists()


# ── the conversion ──────────────────────────────────────────────────────────


def _convert(source: Path, args, interactive: bool) -> Path:
    from .pipeline import Options, analyse

    if not source.is_file():
        raise Problem(t("err_missing", path=source))
    options = Options(
        time_signature=_time_signature(args.time),
        key=args.key,
        finest=args.grid,
        triplets=args.triplets,
        tempo_scale=Fraction(2) if args.double_time else Fraction(1, 2) if args.half_time else None,
        pickup=args.pickup,
        split_pitch=_pitch(args.split),
        max_voices=args.voices,
        staccato=not args.no_staccato,
        dynamics=not args.no_dynamics,
        graces=not args.no_graces,
        composer=args.composer or "",
        pedal=args.pedal,
        slurs=not args.no_slurs,
        hairpins=not args.no_hairpins,
        accents=not args.no_accents,
        ottava=not args.no_ottava,
        clef_changes=not args.no_clef_changes,
        tempo_changes=not args.no_tempo_changes,
        trills=not args.no_ornaments,
        arpeggios=not args.no_ornaments,
        swing=args.swing,
        chords=args.chords,
        title=args.title or _title_from(source),
    )
    if options.key:
        from .spelling import parse_key

        try:
            parse_key(options.key)
        except ValueError:
            raise Problem(t("err_key", value=options.key)) from None

    is_midi = source.suffix.lower() in MIDI_SUFFIXES
    suffixes = [".musicxml"] + ([] if is_midi or args.no_midi else [".mid"]) + ([".pdf"] if args.pdf else [])
    from rich.text import Text

    ui.console.print(Text(f"  {t('file')}  ", style=ui.DIM).append(source.name, style="bold"), no_wrap=True, overflow="ellipsis")
    ui.console.print()
    base = _targets(source, args.output, args.overwrite, interactive, suffixes)

    tracked = None
    remembered = None
    if is_midi:
        from .transcribe import read_midi

        with ui.Step(t("step_midi"), t("done_midi")) as step:
            performance = read_midi(source)
            if not performance.notes:
                raise Problem(t("err_no_notes"))
            step.done(t("notes_pedals", notes=len(performance.notes), pedals=len(performance.pedals)))
    else:
        from . import cache
        from .audio import load_audio

        key = cache.fingerprint(source)
        remembered = None if args.fresh else cache.load(key)
        if remembered is not None:
            performance, tracked = remembered
            with ui.Step(t("step_cache"), t("done_cache")) as step:
                step.done(t("notes_pedals", notes=len(performance.notes), pedals=len(performance.pedals)))
            if tracked is None:
                # Remembered by an older version, which kept a list of beats only: the pulse is heard again.
                with ui.Step(t("step_beats"), t("done_beats")) as step:
                    from .beats import track_audio
                    from .transcribe import pick_device

                    try:
                        tracked = track_audio(load_audio(source), SAMPLE_RATE, pick_device(args.device))
                        cache.save_tracked(key, tracked)
                    except Exception:
                        tracked = None
                    step.done(t("from_notes") if tracked is None else "Beat This!")

    if not is_midi and remembered is None:
        with ui.Step(t("step_load"), t("done_load")) as step:
            try:
                audio = load_audio(source)
            except AudioError as problem:
                raise Problem(t("err_ffmpeg") if str(problem) == "ffmpeg" else t("err_decode")) from None
            step.done(f"{ui.clock(len(audio) / SAMPLE_RATE)} min")

        with ui.Step(t("step_transcribe"), t("done_transcribe")) as step:
            from .transcribe import pick_device, transcribe

            device = pick_device(args.device)
            if args.device == "auto" and device == "cpu" and _has_gpu():
                step.note(t("gpu_busy"))
            try:
                performance = transcribe(audio, device, step.progress)
            except RuntimeError as problem:
                if "out of memory" not in str(problem).lower() or device == "cpu":
                    raise
                device = "cpu"
                step.note(t("gpu_busy"))
                performance = transcribe(audio, device, step.progress)
            if not performance.notes:
                raise Problem(t("err_no_notes"))
            where = "GPU" if device == "cuda" else "CPU"
            step.done(f"{t('notes_pedals', notes=len(performance.notes), pedals=len(performance.pedals))} · {where}")

        with ui.Step(t("step_beats"), t("done_beats")) as step:
            from .beats import beat_model_ready, track_audio

            if not beat_model_ready():
                step.note(t("first_run"))
            try:
                tracked = track_audio(audio, SAMPLE_RATE, device)
            except Exception:
                tracked = None
            cache.save(key, source, performance, tracked, cache.waveform_peaks(audio))
            del audio
            step.done(t("from_notes") if tracked is None else "Beat This!")

    midi_path = None
    if not is_midi and not args.no_midi:
        from .transcribe import write_midi

        midi_path = base.with_name(base.name + ".mid")
        write_midi(performance, midi_path)

    with ui.Step(t("step_score"), t("done_score")) as step:
        result = analyse(performance, None, None, options, tracked)
        unit, bpm = result.tempo
        step.done(f"{result.meter} · {unit} = {bpm} · {result.key.label(language())}")

    score_path = base.with_name(base.name + ".musicxml")
    with ui.Step(t("step_write"), t("done_write")) as step:
        from .export import write_musicxml

        write_musicxml(result.score, score_path)
        step.done(t("bars", bars=result.bars))

    files = {"score_file": score_path}
    if midi_path:
        files["midi_file"] = midi_path
    if args.pdf:
        with ui.Step(t("step_pdf"), t("done_pdf")) as step:
            pdf_path = base.with_name(base.name + ".pdf")
            if _pdf(score_path, pdf_path, options.title or ""):
                files["pdf_file"] = pdf_path
                step.done()
            else:
                step.__exit__(None, None, None)
                ui.error(t("err_pdf"))

    ui.summary(result, files, language())
    if result.grid.source == "audio" and result.grid.downbeat_confidence < 0.6 and not options.time_signature:
        ui.console.print()
        ui.note(t("low_confidence"))
    return score_path


def _has_gpu() -> bool:
    try:
        import torch

        return torch.cuda.is_available()
    except Exception:
        return False


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    # Without files – or with --gui – Melograph opens its window (when there is a screen).
    has_screen = bool(os.environ.get("WAYLAND_DISPLAY") or os.environ.get("DISPLAY"))
    if "--gui" in argv or (not argv and has_screen):
        from .gui.app import run

        return run([a for a in argv if not a.startswith("-")])
    # The language has to be known before the help texts are built.
    chosen = None
    for index, argument in enumerate(argv):
        if argument == "--lang" and index + 1 < len(argv):
            chosen = argv[index + 1]
        elif argument.startswith("--lang="):
            chosen = argument.split("=", 1)[1]
    set_language(chosen)
    args = _parser().parse_args(argv)

    warnings.filterwarnings("ignore")
    os.environ.setdefault("PYTHONWARNINGS", "ignore")
    interactive = sys.stdin.isatty() and sys.stdout.isatty()

    try:
        ui.banner()
        sources = list(args.input)
        if not sources:
            if not interactive:
                _parser().print_usage()
                return 2
            sources = [_ask_for_file()]
            ui.console.print()
        last = None
        for index, source in enumerate(sources):
            if index:
                ui.console.print()
            last = _convert(source.expanduser(), args, interactive)

        ui.console.print()
        if last is not None and len(sources) == 1 and not args.no_open:
            wanted = args.open
            if not wanted and interactive:
                from rich.text import Text

                prompt = Text("  " + t("open_ask"), style="bold").append(f" {t('yes_no')} ", style=ui.DIM)
                answer = ui.console.input(prompt).strip().lower()
                wanted = answer == "" or answer.startswith(t("yes_keys")) or answer.startswith("y")
            if wanted:
                ui.note(t("opened") if _open(last) else t("no_musescore"))
        ui.note(t("hint"))
        ui.console.print()
        return 0
    except Problem as problem:
        ui.error(str(problem))
        ui.console.print()
        return 1
    except (KeyboardInterrupt, EOFError):
        ui.console.print()
        ui.note(t("cancelled"))
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
