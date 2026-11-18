"""Each hand has its own subdivision of the beat: three against two and the like."""

from __future__ import annotations

from melograph.model import LEFT, RIGHT
from melograph.pipeline import Options, analyse

from .music import play


def run(performance, beats, downbeats, **options):
    return analyse(performance, beats, downbeats, Options(title="Test", **options))


def staff(result, bar: int, hand: int):
    """The written notes (no rests) of one hand in one bar."""
    return [atom for voice in result.layout.bars[bar].staves[hand] for atom in voice if atom.notes]


EIGHTHS = "c5:1/2 d5:1/2 e5:1/2 f5:1/2 g5:1/2 f5:1/2 e5:1/2 d5:1/2 "
BASS = "c3:1/2 g3:1/2 e3:1/2 g3:1/2 c3:1/2 g3:1/2 e3:1/2 g3:1/2 "


def test_triplets_over_plain_eighths_are_three_against_two():
    triplets = "c5:1/3 e5:1/3 g5:1/3 c6:1/3 g5:1/3 e5:1/3 " * 2
    perf, beats, downs = play(EIGHTHS * 3 + triplets * 2 + EIGHTHS * 3, BASS * 8, jitter=0.008)
    result = run(perf, beats, downs)
    assert {str(m) for m in result.layout.meters} == {"4/4"}
    for bar in (3, 4):
        upper, lower = staff(result, bar, RIGHT), staff(result, bar, LEFT)
        assert len(upper) == 12 and all(a.tuplet and a.kind == "eighth" for a in upper)
        assert len(lower) == 8 and all(a.kind == "eighth" and not a.tuplet for a in lower)
    for bar in (0, 1, 2, 5, 6, 7):
        assert not any(a.tuplet for hand in (RIGHT, LEFT) for a in staff(result, bar, hand))


def test_quarter_note_triplet_over_eighths():
    """The second and third note fall between the eighths of the left hand; they are still one triplet."""
    tune = EIGHTHS * 2 + "g5:2/3 a5:2/3 b5:2/3 c6:2 " + EIGHTHS + "g5:2/3 a5:2/3 b5:2/3 c6:2 " + EIGHTHS
    perf, beats, downs = play(tune, BASS * 6, jitter=0.008)
    result = run(perf, beats, downs)
    for bar in (2, 4):
        upper = staff(result, bar, RIGHT)
        assert [(a.kind, bool(a.tuplet)) for a in upper[:3]] == [("quarter", True)] * 3
        assert {a.tuplet_unit for a in upper[:3]} == {"quarter"}
        lower = staff(result, bar, LEFT)
        assert len(lower) == 8 and all(a.kind == "eighth" and not a.tuplet for a in lower)


def test_three_three_two_stays_in_sixteenths():
    """♪. ♪. ♪ over eighths is no triplet, however close it comes to one."""
    tune = EIGHTHS * 2 + "g5:3/4 a5:3/4 b5:1/2 c6:2 " * 4 + EIGHTHS
    perf, beats, downs = play(tune, BASS * 7, jitter=0.008)
    result = run(perf, beats, downs)
    assert not any(a.tuplet for bar in range(7) for hand in (RIGHT, LEFT) for a in staff(result, bar, hand))
    first = staff(result, 2, RIGHT)[0]
    assert first.kind == "eighth" and first.dots == 1
