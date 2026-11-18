"""User-facing texts in German and English."""

from __future__ import annotations

import os

TEXTS: dict[str, dict[str, str]] = {
    "tagline": {"de": "Klavieraufnahme → Noten", "en": "piano recording → sheet music"},
    "usage": {
        "de": "Wandelt eine Klavieraufnahme in Noten (MusicXML für MuseScore) um.",
        "en": "Turns a piano recording into sheet music (MusicXML for MuseScore).",
    },
    "arg_input": {
        "de": "Aufnahme (mp3, wav, flac, m4a, Video …) oder MIDI-Datei; ohne Angabe fragt Melograph nach",
        "en": "recording (mp3, wav, flac, m4a, video …) or MIDI file; asks if omitted",
    },
    "meta_file": {"de": "DATEI", "en": "FILE"},
    "arg_help": {"de": "diese Hilfe anzeigen", "en": "show this help"},
    "arg_version": {"de": "Version anzeigen", "en": "show the version"},
    "arg_output": {"de": "Zieldatei oder -ordner (Standard: neben der Aufnahme)", "en": "output file or folder (default: next to the recording)"},
    "arg_title": {"de": "Titel über den Noten (Standard: Dateiname)", "en": "title above the music (default: file name)"},
    "arg_time": {"de": "Taktart vorgeben, z. B. 3/4 oder 6/8 (Standard: automatisch)", "en": "force the time signature, e.g. 3/4 or 6/8 (default: automatic)"},
    "arg_pickup": {
        "de": "Auftakt in Schlägen vorgeben; 0 = das Stück beginnt auf der Eins (Standard: automatisch)",
        "en": "pickup in beats; 0 = the piece starts on the downbeat (default: automatic)",
    },
    "arg_key": {"de": "Tonart vorgeben, z. B. c-Moll, Es-Dur, F#m (Standard: automatisch)", "en": "force the key, e.g. Cm, Eb, 'F# minor' (default: automatic)"},
    "arg_grid": {"de": "kleinster Notenwert: 8, 16 oder 32 (Standard: 16)", "en": "shortest note value: 8, 16 or 32 (default: 16)"},
    "arg_triplets": {"de": "Triolen: auto, on oder off (Standard: auto)", "en": "triplets: auto, on or off (default: auto)"},
    "arg_double": {"de": "doppelt so viele Schläge zählen (wenn das Tempo zu langsam erkannt wurde)", "en": "count twice as many beats (if the tempo came out too slow)"},
    "arg_half": {"de": "halb so viele Schläge zählen (wenn das Tempo zu schnell erkannt wurde)", "en": "count half as many beats (if the tempo came out too fast)"},
    "arg_split": {"de": "Hände fest an einem Ton teilen, z. B. C4 (Standard: automatisch)", "en": "split the hands at a fixed pitch, e.g. C4 (default: automatic)"},
    "arg_voices": {"de": "höchstens so viele Stimmen pro Hand: 1 oder 2 (Standard: 2)", "en": "at most this many voices per hand: 1 or 2 (default: 2)"},
    "arg_swing": {"de": "Swing-Achtel gerade notieren: auto, on oder off (Standard: auto)", "en": "write swung eighths straight: auto, on or off (default: auto)"},
    "arg_pedal": {"de": "Pedal: lines (Linien), signs (Ped. *), text (con pedale) oder off", "en": "pedal: lines, signs (Ped. *), text (con pedale) or off"},
    "arg_chords": {"de": "Akkordsymbole über die Noten schreiben", "en": "write chord symbols above the music"},
    "arg_composer": {"de": "Komponist über den Noten", "en": "composer above the music"},
    "arg_no_hairpins": {"de": "keine Crescendo-/Decrescendo-Gabeln", "en": "no crescendo/diminuendo hairpins"},
    "arg_no_slurs": {"de": "keine Bögen über Legato-Stellen", "en": "no slurs over legato passages"},
    "arg_no_accents": {"de": "keine Akzente", "en": "no accents"},
    "arg_no_ottava": {"de": "keine 8va-/8vb-Klammern", "en": "no 8va/8vb lines"},
    "arg_no_clef_changes": {"de": "keine Schlüsselwechsel innerhalb des Stücks", "en": "no clef changes within the piece"},
    "arg_no_tempo_changes": {"de": "keine Tempowechsel, kein rit. oder a tempo", "en": "no tempo changes, no rit. or a tempo"},
    "arg_no_ornaments": {"de": "Triller und Arpeggien ausschreiben statt als Zeichen", "en": "write trills and rolled chords out instead of as signs"},
    "arg_fresh": {"de": "Aufnahme neu heraushören statt den Zwischenspeicher zu nutzen", "en": "listen to the recording again instead of using the cache"},
    "step_cache": {"de": "Zwischenspeicher lesen", "en": "Reading the cache"},
    "done_cache": {"de": "Schon einmal herausgehört", "en": "Heard before"},
    "arg_no_graces": {"de": "Vorschlagsnoten nicht als solche schreiben", "en": "do not write grace notes as such"},
    "arg_no_staccato": {"de": "keine Staccato-Punkte setzen", "en": "do not write staccato dots"},
    "arg_no_dynamics": {"de": "keine Dynamikzeichen setzen", "en": "do not write dynamics"},
    "arg_device": {"de": "Rechenwerk: auto, cpu oder cuda (Standard: auto)", "en": "device: auto, cpu or cuda (default: auto)"},
    "arg_no_midi": {"de": "die MIDI-Datei der Einspielung nicht behalten", "en": "do not keep the performance MIDI file"},
    "arg_pdf": {"de": "zusätzlich ein PDF erzeugen (über MuseScore)", "en": "also write a PDF (through MuseScore)"},
    "arg_open": {"de": "Ergebnis danach in MuseScore öffnen", "en": "open the result in MuseScore afterwards"},
    "arg_no_open": {"de": "nicht fragen, ob MuseScore geöffnet werden soll", "en": "do not offer to open MuseScore"},
    "arg_overwrite": {"de": "vorhandene Dateien überschreiben", "en": "overwrite existing files"},
    "arg_lang": {"de": "Sprache: de oder en", "en": "language: de or en"},
    "group_notation": {"de": "Notenbild", "en": "notation"},
    "group_output": {"de": "Ausgabe", "en": "output"},

    "pick_title": {"de": "Welche Aufnahme soll in Noten umgewandelt werden?", "en": "Which recording should become sheet music?"},
    "pick_found": {"de": "Zuletzt geänderte Aufnahmen", "en": "Recently changed recordings"},
    "pick_prompt": {"de": "Nummer eingeben oder Datei hierher ziehen", "en": "Enter a number or drop a file here"},
    "pick_prompt_plain": {"de": "Datei hierher ziehen oder Pfad eingeben", "en": "Drop a file here or enter its path"},
    "pick_invalid": {"de": "Das habe ich nicht gefunden: {path}", "en": "I could not find that: {path}"},

    "file": {"de": "Aufnahme", "en": "Recording"},
    "step_load": {"de": "Aufnahme lesen", "en": "Reading the recording"},
    "done_load": {"de": "Aufnahme gelesen", "en": "Recording read"},
    "step_transcribe": {"de": "Tasten heraushören", "en": "Listening for the keys"},
    "done_transcribe": {"de": "Tasten herausgehört", "en": "Keys heard"},
    "step_midi": {"de": "MIDI lesen", "en": "Reading the MIDI file"},
    "done_midi": {"de": "MIDI gelesen", "en": "MIDI read"},
    "step_beats": {"de": "Puls und Takte suchen", "en": "Finding pulse and bars"},
    "done_beats": {"de": "Puls und Takte gefunden", "en": "Pulse and bars found"},
    "step_score": {"de": "Rhythmus, Hände und Stimmen setzen", "en": "Setting rhythm, hands and voices"},
    "done_score": {"de": "Rhythmus, Hände und Stimmen gesetzt", "en": "Rhythm, hands and voices set"},
    "step_write": {"de": "Noten schreiben", "en": "Writing the music"},
    "done_write": {"de": "Noten geschrieben", "en": "Music written"},
    "step_pdf": {"de": "PDF erzeugen", "en": "Making the PDF"},
    "done_pdf": {"de": "PDF erzeugt", "en": "PDF made"},
    "notes_pedals": {"de": "{notes} Töne · {pedals} Pedalwechsel", "en": "{notes} notes · {pedals} pedal changes"},
    "notes_only": {"de": "{notes} Töne", "en": "{notes} notes"},
    "hands": {"de": "rechts {right} · links {left}", "en": "right {right} · left {left}"},
    "bars": {"de": "{bars} Takte", "en": "{bars} bars"},
    "from_notes": {"de": "aus den Anschlägen", "en": "from the note onsets"},
    "gpu_busy": {"de": "Grafikkarte belegt, rechne auf dem Prozessor", "en": "GPU busy, using the CPU"},
    "first_run": {"de": "lade das Beat-Modell (einmalig, 78 MB)", "en": "downloading the beat model (once, 78 MB)"},

    "result": {"de": "Ergebnis", "en": "Result"},
    "key": {"de": "Tonart", "en": "Key"},
    "time": {"de": "Taktart", "en": "Time"},
    "tempo": {"de": "Tempo", "en": "Tempo"},
    "length": {"de": "Umfang", "en": "Length"},
    "hands_label": {"de": "Hände", "en": "Hands"},
    "score_file": {"de": "Noten", "en": "Score"},
    "midi_file": {"de": "MIDI", "en": "MIDI"},
    "pdf_file": {"de": "PDF", "en": "PDF"},
    "no_accidentals": {"de": "ohne Vorzeichen", "en": "no accidentals"},
    "preview": {"de": "Die ersten Takte", "en": "The first bars"},
    "right": {"de": "rechte Hand", "en": "right hand"},
    "left": {"de": "linke Hand", "en": "left hand"},
    "overwrite_ask": {"de": "{name} gibt es schon. Überschreiben?", "en": "{name} already exists. Overwrite?"},
    "open_ask": {"de": "In MuseScore öffnen?", "en": "Open in MuseScore?"},
    "opened": {"de": "MuseScore wird geöffnet.", "en": "Opening MuseScore."},
    "no_musescore": {"de": "MuseScore wurde nicht gefunden – öffne die Datei bitte von Hand.", "en": "MuseScore was not found – please open the file yourself."},
    "hint": {
        "de": "Stimmt etwas nicht? Taktart, Tonart oder Tempo lassen sich vorgeben: melograph --help",
        "en": "Something off? Time signature, key or tempo can be forced: melograph --help",
    },
    "low_confidence": {
        "de": "Die Taktschwerpunkte waren nicht eindeutig. Wirken die Taktstriche verschoben, hilft --pickup.",
        "en": "The downbeats were not clear-cut. If the bar lines look shifted, try --pickup.",
    },

    "err_missing": {"de": "Datei nicht gefunden: {path}", "en": "File not found: {path}"},
    "err_ffmpeg": {"de": "ffmpeg fehlt. Bitte installieren (z. B. sudo pacman -S ffmpeg).", "en": "ffmpeg is missing. Please install it."},
    "err_decode": {"de": "Die Datei ließ sich nicht als Audio lesen.", "en": "The file could not be read as audio."},
    "err_no_notes": {"de": "In der Aufnahme wurden keine Klaviertöne erkannt.", "en": "No piano notes were found in the recording."},
    "err_time": {"de": "Taktart nicht verstanden: {value} (Beispiel: 3/4)", "en": "Time signature not understood: {value} (example: 3/4)"},
    "err_key": {"de": "Tonart nicht verstanden: {value} (Beispiele: c-Moll, Es-Dur, F#m)", "en": "Key not understood: {value} (examples: Cm, Eb, 'F# minor')"},
    "err_split": {"de": "Ton nicht verstanden: {value} (Beispiel: C4)", "en": "Pitch not understood: {value} (example: C4)"},
    "err_pdf": {"de": "Das PDF ließ sich nicht erstellen.", "en": "The PDF could not be made."},
    "cancelled": {"de": "Abgebrochen.", "en": "Cancelled."},
    "yes_keys": {"de": "j", "en": "y"},
    "yes_no": {"de": "[J/n]", "en": "[Y/n]"},
}

_language = "en"


def detect_language() -> str:
    for name in ("MELOGRAPH_LANG", "LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(name)
        if value:
            return "de" if value.lower().startswith("de") else "en"
    return "en"


def set_language(language: str | None) -> str:
    global _language
    _language = language if language in ("de", "en") else detect_language()
    return _language


def language() -> str:
    return _language


def t(key: str, **values) -> str:
    text = TEXTS[key][_language]
    return text.format(**values) if values else text
