"""What Melograph looks like in the terminal."""

from __future__ import annotations

import time
from pathlib import Path

from rich.cells import cell_len
from rich.console import Console, Group
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from . import __version__
from .i18n import t
from .model import LEFT, RIGHT

ACCENT = "#e5484d"
COOL = "#6ea8d8"
DIM = "grey50"

console = Console(highlight=False)


def banner() -> None:
    title = Text()
    title.append("♪ ", style=ACCENT)
    title.append("Melograph", style=f"bold {ACCENT}")
    title.append(f"  {__version__}", style=DIM)
    title.append(f"   {t('tagline')}", style="default")
    console.print()
    console.print(Padding(title, (0, 2)))
    console.print()


def short(path: Path) -> str:
    """A path as the user would write it."""
    try:
        return "~/" + str(path.resolve().relative_to(Path.home()))
    except ValueError:
        return str(path)


def clock(seconds: float) -> str:
    return f"{int(seconds // 60)}:{int(seconds % 60):02d}"


class Step:
    """One line of work: a spinner while it runs, a tick and the outcome afterwards."""

    width = 36

    def __init__(self, running: str, done: str, quiet: bool = False):
        self.running, self.finished, self.quiet = running, done, quiet
        self.status = None
        self.started = 0.0

    def __enter__(self) -> "Step":
        self.started = time.monotonic()
        if not self.quiet:
            self.status = console.status(Text(f"{self.running} …"), spinner="dots", spinner_style=ACCENT)
            self.status.start()
        return self

    def progress(self, done: int, total: int) -> None:
        if self.status is not None and total > 1:
            self.status.update(Text(f"{self.running} …  {round(100 * done / total)} %"))

    def note(self, text: str) -> None:
        if self.status is not None:
            self.status.update(Text(f"{self.running} …  ").append(text, style=DIM))

    def done(self, detail: str = "") -> None:
        if self.status is not None:
            self.status.stop()
            self.status = None
        if self.quiet:
            return
        elapsed = time.monotonic() - self.started
        line = Text("  ")
        line.append("✓ ", style=ACCENT)
        line.append(self.finished)
        line.append(" " * max(2, self.width - cell_len(self.finished)))
        line.append(detail, style=DIM)
        if elapsed >= 1.0:
            line.append(f"  {elapsed:.0f} s", style="grey35")
        console.print(line, no_wrap=True, overflow="ellipsis")

    def __exit__(self, kind, value, traceback) -> None:
        if self.status is not None:
            self.status.stop()
            self.status = None


def error(message: str) -> None:
    console.print(Text("  ✗ ", style=f"bold {ACCENT}").append(message, style="default"))


def note(message: str) -> None:
    console.print(Text("  " + message, style=DIM))


def summary(result, files: dict[str, Path], language: str) -> None:
    table = Table.grid(padding=(0, 3))
    table.add_column(style=DIM)
    table.add_column()

    fifths = result.key.fifths
    signature = t("no_accidentals") if fifths == 0 else f"{abs(fifths)} {'♯' if fifths > 0 else '♭'}"
    unit, bpm = result.tempo
    table.add_row(t("key"), Text(result.key.label(language), style="bold").append(f"  ({signature})", style=DIM))
    table.add_row(t("time"), Text(str(result.meter), style="bold"))
    table.add_row(t("tempo"), Text(f"{unit} = {bpm}", style="bold"))
    table.add_row(t("length"), f"{t('bars', bars=result.bars)} · {clock(result.performance.duration)}")
    table.add_row(t("hands_label"), t("hands", right=result.right_hand, left=result.left_hand))
    table.add_row("", "")
    for label, path in files.items():
        table.add_row(t(label), Text(short(path), style=ACCENT if label == "score_file" else "default"))

    console.print()
    console.print(Padding(Panel(
        Group(table, Text(""), piano_roll(result, console.width - 12)),
        title=Text(t("result"), style=f"bold {ACCENT}"), title_align="left",
        border_style="grey35", padding=(1, 2), expand=False,
    ), (0, 2)))


def piano_roll(result, width: int) -> Group:
    """A small picture of the first bars: who plays what, and when."""
    notes = [n for n in result.notes if n.dur is not None]
    layout, meter = result.layout, result.meter
    width = max(30, min(width, 96))
    per_bar = meter.beats_per_bar
    bars = max(2, min(len(layout.bars), width // 14))
    start = layout.origin
    first_bar = layout.bars[0].length / meter.beat_ql
    end = start + first_bar + per_bar * (bars - 1)
    shown = [n for n in notes if n.pos < end]
    if not shown:
        return Group()

    rows = 9
    low, high = min(n.pitch for n in shown), max(n.pitch for n in shown)
    grid: list[list[int | None]] = [[None] * width for _ in range(rows)]
    scale = width / float(end - start)
    for n in sorted(shown, key=lambda n: n.hand == RIGHT):
        row = round((high - n.pitch) / max(1, high - low) * (rows - 1))
        a = int(float(n.pos - start) * scale)
        b = max(a + 1, int(float(min(n.pos + n.dur, end) - start) * scale))
        if b - a >= 3:
            b -= 1  # a small gap, so that repeated notes stay apart
        for column in range(a, min(b, width)):
            grid[row][column] = n.hand

    bar_columns = set()
    position = start + first_bar
    while position < end:
        bar_columns.add(int(float(position - start) * scale))
        position += per_bar

    lines = []
    for row in grid:
        line = Text()
        for column, hand in enumerate(row):
            if hand == RIGHT:
                line.append("━", style=ACCENT)
            elif hand == LEFT:
                line.append("━", style=COOL)
            elif column in bar_columns:
                line.append("│", style="grey23")
            else:
                line.append(" ")
        lines.append(line)
    legend = Text()
    legend.append("━ ", style=ACCENT).append(t("right"), style=DIM)
    legend.append("   ")
    legend.append("━ ", style=COOL).append(t("left"), style=DIM)
    legend.append(f"   {t('preview')}", style="grey35")
    return Group(*lines, Text(""), legend)
