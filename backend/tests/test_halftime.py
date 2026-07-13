"""
Tesztek a félidő-érzékelésre és térfélcsere-normalizálásra (halftime.py).

Futtatás:
    python -m pytest tests/test_halftime.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.halftime import (
    auto_normalize, detect_halftime, detect_side_swap, normalize_sides,
)

FPS = 25.0


def _meta():
    return MatchMeta(match_id="ht", home_team="H", away_team="A", fps=FPS)


def _pl(track_id, team, x, y):
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0)


def _play_frames(t0, seconds, home_x, away_x):
    """Aktív játék: 6-6 mért játékos a megadott térfél-középpontok körül."""
    frames = []
    for i in range(int(seconds * FPS)):
        players = [_pl(100 + k, Team.HOME, home_x + k * 0.5, 4.0 + k * 2)
                   for k in range(6)]
        players += [_pl(200 + k, Team.AWAY, away_x + k * 0.5, 4.0 + k * 2)
                    for k in range(6)]
        frames.append(Frame(t=t0 + i, players=players,
                            ball=Ball(x=(home_x + away_x) / 2, y=10.0,
                                      confidence=1.0)))
    return frames


def _break_frames(t0, seconds):
    """Szünet: üres pálya (nincs mért játékos, nincs labda)."""
    return [Frame(t=t0 + i, players=[], ball=None)
            for i in range(int(seconds * FPS))]


def _full_match(swap=True, break_s=90):
    """1. félidő (hazai balra) + szünet + 2. félidő (cserélt vagy azonos)."""
    frames = _play_frames(0, 120, home_x=12.0, away_x=26.0)
    t = len(frames)
    frames += _break_frames(t, break_s)
    t = len(frames)
    if swap:
        frames += _play_frames(t, 120, home_x=26.0, away_x=12.0)
    else:
        frames += _play_frames(t, 120, home_x=12.0, away_x=26.0)
    return Match(_meta(), frames)


def test_halftime_detected_in_middle():
    m = _full_match()
    ht = detect_halftime(m)
    assert ht is not None
    # A szünet a 120–210 mp tartományban van.
    assert 120 * FPS <= ht <= 210 * FPS


def test_no_halftime_without_break():
    m = Match(_meta(), _play_frames(0, 240, home_x=12.0, away_x=26.0))
    assert detect_halftime(m) is None


def test_side_swap_detected_and_normalized():
    m = _full_match(swap=True)
    ht = detect_halftime(m)
    assert detect_side_swap(m, ht) is True
    mirrored = normalize_sides(m, ht)
    assert mirrored > 0
    # Normalizálás után a hazai súlypont a 2. félidőben is a bal térfélen.
    from handball.pipeline.halftime import _centroid_x
    b = _centroid_x(m, Team.HOME, ht, m.frames[-1].t + 1)
    assert b is not None and b < 20.0


def test_no_swap_when_sides_kept():
    m = _full_match(swap=False)
    ht = detect_halftime(m)
    assert ht is not None
    assert detect_side_swap(m, ht) is False


def test_auto_normalize_end_to_end():
    m = _full_match(swap=True)
    info = auto_normalize(m)
    assert info is not None and info["swapped"] is True
    assert info["mirrored_frames"] > 0
    # Szünet nélküli meccsen nem csinál semmit.
    m2 = Match(_meta(), _play_frames(0, 240, home_x=12.0, away_x=26.0))
    assert auto_normalize(m2) is None
