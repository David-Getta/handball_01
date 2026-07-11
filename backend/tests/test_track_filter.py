"""
Tesztek a játékos-pálya simításra (track_filter.py).

Futtatás:
    python tests/test_track_filter.py
"""

from __future__ import annotations

import math
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.track_filter import smooth_player_tracks
from handball.pipeline.stats import compute_player_stats


def _meta(fps=25.0):
    return MatchMeta(match_id="t", home_team="A", away_team="B", fps=fps,
                     frame_width=1920, frame_height=1080)


def _pl(tid, x, y, source=PositionSource.MEASURED):
    return PlayerPosition(track_id=tid, team=Team.HOME, x=x, y=y,
                          source=source, confidence=1.0)


def _match_track(points, tid=1, source=PositionSource.MEASURED, skip=None):
    """Match egyetlen játékossal a megadott pozíció-soron (skip: kihagyott kockák)."""
    skip = skip or set()
    frames = []
    for i, (x, y) in enumerate(points):
        players = [] if i in skip else [_pl(tid, x, y, source)]
        frames.append(Frame(t=i, players=players, ball=None))
    return Match(_meta(), frames)


def test_jitter_reduced_distance():
    """A cikk-cakk remegés simítás után rövidebb megtett távot ad (valósabbat)."""
    # y remeg ±0.3 m-t egy egyenes vonal körül — a valódi mozgás ~egyenes.
    pts = [(10.0 + 0.2 * i, 10.0 + (0.3 if i % 2 else -0.3)) for i in range(20)]
    m = _match_track(pts)
    before = compute_player_stats(m)[1].distance_m
    changed = smooth_player_tracks(m)
    after = compute_player_stats(m)[1].distance_m
    assert changed > 0
    assert after < before * 0.7, f"before={before:.2f} after={after:.2f}"


def test_straight_line_nearly_unchanged():
    """Az egyenes vonalú (zajmentes) mozgást a simítás gyakorlatilag nem bántja."""
    pts = [(10.0 + 0.5 * i, 10.0) for i in range(12)]
    m = _match_track(pts)
    smooth_player_tracks(m)
    for i, f in enumerate(m.frames):
        assert abs(f.players[0].y - 10.0) < 1e-9
        # x-ben a széleken sem tér el érdemben (középen pontos)
        assert abs(f.players[0].x - (10.0 + 0.5 * i)) < 0.2


def test_estimated_positions_untouched():
    """A becsült (ESTIMATED) pozíciókhoz a simítás nem nyúl."""
    pts = [(10.0, 10.0 + (0.3 if i % 2 else -0.3)) for i in range(10)]
    m = _match_track(pts, source=PositionSource.ESTIMATED)
    changed = smooth_player_tracks(m)
    assert changed == 0
    assert m.frames[1].players[0].y == 10.3


def test_gap_splits_segments():
    """A nagy kihagyás szakaszhatár: a két látási periódus nem átlagolódik össze.

    A játékos a 0-4. kockán a pálya elején, hosszú kihagyás után a 20-24. kockán
    a másik végén — a szakaszok végei nem húznak egymás felé.
    """
    pts = {i: (5.0, 10.0) for i in range(5)}
    pts.update({i: (35.0, 10.0) for i in range(20, 25)})
    frames = []
    for i in range(25):
        players = [_pl(1, *pts[i])] if i in pts else []
        frames.append(Frame(t=i, players=players, ball=None))
    m = Match(_meta(), frames)
    smooth_player_tracks(m, max_gap=10)
    assert abs(m.frames[4].players[0].x - 5.0) < 1e-9   # az első szakasz vége a helyén
    assert abs(m.frames[20].players[0].x - 35.0) < 1e-9  # a második eleje a helyén


def test_invalid_window_rejected():
    """Páros vagy túl kicsi ablak: hiba (ne csendben csináljon mást)."""
    m = _match_track([(10.0, 10.0)] * 5)
    for bad in (2, 4, 1):
        try:
            smooth_player_tracks(m, window=bad)
            assert False, "hibát vártunk"
        except ValueError:
            pass


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
