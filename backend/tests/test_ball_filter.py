"""
Tesztek a labda-utómunkára (ball_filter.py): kiugró-szűrés + hézagpótlás.

Futtatás:
    python tests/test_ball_filter.py
"""

from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import Match, MatchMeta, Frame, Ball
from handball.pipeline.ball_filter import (
    remove_ball_outliers, interpolate_ball_gaps, smooth_ball,
    INTERPOLATED_CONFIDENCE,
)


def _meta(fps=25.0):
    return MatchMeta(match_id="b", home_team="A", away_team="B", fps=fps,
                     frame_width=1920, frame_height=1080)


def _match(balls):
    """Match a megadott labda-listával (None = nincs labda azon a kockán)."""
    frames = [Frame(t=i, players=[],
                    ball=None if b is None else Ball(x=b[0], y=b[1], confidence=1.0))
              for i, b in enumerate(balls)]
    return Match(_meta(), frames)


def test_outlier_removed():
    """A mindkét szomszédjától lehetetlenül messze lévő észlelés kiesik.

    A labda 20 m-nél halad kockánként ~0.2 m-t; a 2. kockán hirtelen a pálya
    túloldalán (38,2) — 25 fps-nél ez ~450 m/s volna → téves észlelés.
    """
    m = _match([(20.0, 10.0), (20.2, 10.0), (38.0, 2.0), (20.6, 10.0), (20.8, 10.0)])
    removed = remove_ball_outliers(m)
    assert removed == 1
    assert m.frames[2].ball is None
    # a valódi pontok megmaradtak
    assert m.frames[1].ball is not None and m.frames[3].ball is not None


def test_fast_but_consistent_motion_kept():
    """A gyors, de KONZISZTENS mozgás (valódi lövés) nem esik ki.

    ~1 m/frame = 25 m/s — gyors, de plauzibilis, és a pont a pályán halad tovább.
    """
    m = _match([(20.0, 10.0), (21.0, 10.0), (22.0, 10.0), (23.0, 10.0)])
    assert remove_ball_outliers(m) == 0


def test_short_gap_interpolated():
    """A rövid hézag lineárisan pótolódik, csökkentett confidence-szel."""
    m = _match([(20.0, 10.0), None, None, (23.0, 10.0)])
    filled = interpolate_ball_gaps(m)
    assert filled == 2
    b1, b2 = m.frames[1].ball, m.frames[2].ball
    assert abs(b1.x - 21.0) < 1e-9 and abs(b2.x - 22.0) < 1e-9
    assert b1.confidence == INTERPOLATED_CONFIDENCE


def test_long_gap_not_filled():
    """A max_gap-nél hosszabb hézagot nem találjuk ki."""
    balls = [(20.0, 10.0)] + [None] * 20 + [(30.0, 10.0)]
    m = _match(balls)
    filled = interpolate_ball_gaps(m, max_gap_frames=12)
    assert filled == 0
    assert all(m.frames[i].ball is None for i in range(1, 21))


def test_smooth_ball_order_matters():
    """A teljes utómunka: előbb a kiugró esik ki, és a pótlás már enélkül készül.

    A kiugró (38,2) eldobása után a helyén hézag marad, amit a két valódi
    szomszéd között pótolunk — az interpolált pont a pályaív közelében van,
    nem a kiugró felé húz.
    """
    m = _match([(20.0, 10.0), (20.2, 10.0), (38.0, 2.0), (20.6, 10.0), (20.8, 10.0)])
    stats = smooth_ball(m)
    assert stats["removed"] == 1 and stats["filled"] == 1
    b = m.frames[2].ball
    assert b is not None
    assert abs(b.x - 20.4) < 1e-9 and abs(b.y - 10.0) < 1e-9
    assert b.confidence == INTERPOLATED_CONFIDENCE


def test_no_ball_at_all_is_safe():
    """Labda nélküli meccsen nem történik semmi (nem hibázik)."""
    m = _match([None, None, None])
    assert smooth_ball(m) == {"removed": 0, "filled": 0}


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    print(f"\n{'OK' if failures == 0 else failures} hibás teszt")
    raise SystemExit(1 if failures else 0)
