"""The notation settings as the window shows them, and their translation into pipeline options."""

from __future__ import annotations

import re
from fractions import Fraction
from pathlib import Path

DEFAULTS = {
    "title": "",
    "composer": "",
    "time": "auto",  # "auto" or "3/4" …
    "pickup": "auto",  # "auto" or a number of beats
    "tempo": "auto",  # "auto", "half" or "double"
    "key": "auto",  # "auto" or "Cm", "Eb", "F#m" …
    "grid": 16,
    "triplets": "auto",
    "swing": "auto",
    "voices": 2,
    "split": "auto",  # "auto" or a MIDI pitch
    "pedal": "lines",
    "slurs": True,
    "dynamics": True,
    "hairpins": True,
    "accents": True,
    "staccato": True,
    "graces": True,
    "ornaments": True,
    "ottava": True,
    "clefs": True,
    "tempoChanges": True,
    "fermatas": True,
    "chords": False,
}

TIME_SIGNATURES = ["2/4", "3/4", "4/4", "5/4", "6/4", "2/2", "3/8", "6/8", "9/8", "12/8", "5/8", "7/8"]
KEYS = [
    "C", "G", "D", "A", "E", "B", "F#", "Db", "Ab", "Eb", "Bb", "F",
    "Am", "Em", "Bm", "F#m", "C#m", "G#m", "Ebm", "Bbm", "Fm", "Cm", "Gm", "Dm",
]


def title_from(path: Path) -> str:
    title = re.sub(r"\s*[\[(][A-Za-z0-9_-]{6,}[\])]\s*$", "", path.stem)  # trailing video ids
    return re.sub(r"[_]+", " ", title).strip() or path.stem


def merged(values: dict | None) -> dict:
    result = dict(DEFAULTS)
    for key, value in (values or {}).items():
        if key in DEFAULTS:
            result[key] = value
    return result


def to_options(values: dict, source: Path | None):
    from ..pipeline import Options

    v = merged(values)
    time = None
    if v["time"] != "auto":
        numerator, denominator = (int(x) for x in str(v["time"]).split("/"))
        time = (numerator, denominator)
    return Options(
        time_signature=time,
        key=None if v["key"] == "auto" else str(v["key"]),
        finest=int(v["grid"]),
        triplets=str(v["triplets"]),
        tempo_scale={"half": Fraction(1, 2), "double": Fraction(2)}.get(v["tempo"]),
        pickup=None if v["pickup"] == "auto" else float(v["pickup"]),
        split_pitch=None if v["split"] == "auto" else int(v["split"]),
        max_voices=int(v["voices"]),
        staccato=bool(v["staccato"]),
        dynamics=bool(v["dynamics"]),
        graces=bool(v["graces"]),
        title=v["title"] or (title_from(source) if source else ""),
        composer=v["composer"],
        pedal=str(v["pedal"]),
        slurs=bool(v["slurs"]),
        hairpins=bool(v["hairpins"]),
        accents=bool(v["accents"]),
        fermatas=bool(v["fermatas"]),
        ottava=bool(v["ottava"]),
        clef_changes=bool(v["clefs"]),
        tempo_changes=bool(v["tempoChanges"]),
        trills=bool(v["ornaments"]),
        arpeggios=bool(v["ornaments"]),
        swing=str(v["swing"]),
        chords=bool(v["chords"]),
    )
