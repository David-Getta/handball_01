"""
Tesztek a gól-sorozat (momentum) felismerésre (momentum.py).

A pálya 40x20 m; a HAZAI a +x (x=40) kapu felé támad.

Futtatás:
    python -m pytest tests/test_momentum.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.momentum import scoring_runs


def _meta(fps=25.0):
    return MatchMeta(match_id="mo", home_team="H", away_team="A", fps=fps)


def _goal(t0, toward_home_goal=False):
    """Egy gól-esemény kockái: a labda gyorsan a kapuvonalig (kapufák között).
    toward_home_goal=False → a +x (x=40) kapu → HAZAI gól."""
    frames = []
    for i in range(8):
        if toward_home_goal:
            x = max(6.4 - i, 0.0)          # a -x (x=0) kapu felé → VENDÉG gól
        else:
            x = min(33.6 + i, 40.0)        # a +x (x=40) kapu felé → HAZAI gól
        frames.append(Frame(t=t0 + i, players=[], ball=Ball(x=x, y=10.0,
                                                            confidence=1.0)))
    return frames


def _match_from_goals(sequence):
    """sequence: 'H'/'A' betűk időrendben; egyenletesen elosztott gólok."""
    frames = []
    t = 0
    gap = 20  # kockányi szünet a gólok között (a debounce miatt kell)
    for ch in sequence:
        frames += _goal(t, toward_home_goal=(ch == "A"))
        t += 8
        frames.append(Frame(t=t, players=[], ball=Ball(x=20.0, y=10.0,
                                                       confidence=1.0)))
        t += gap
    return Match(_meta(), frames)


def test_detects_unanswered_run():
    """HHHH majd A: a hazai 4-gólos sorozata jelenik meg."""
    m = _match_from_goals("HHHHA")
    runs = scoring_runs(m)
    assert len(runs) == 1
    r = runs[0]
    assert r["team"] == "home" and r["length"] == 4
    assert r["score_before"] == [0, 0]
    assert r["score_after"] == [4, 0]


def test_short_runs_ignored():
    """Váltakozó gólok (max 2 egymás után) → nincs sorozat (küszöb 3)."""
    m = _match_from_goals("HHAAHA")
    assert scoring_runs(m) == []


def test_two_runs_with_scores():
    """HHH ... AAAA: két sorozat, helyes állással a másodiknál."""
    m = _match_from_goals("HHHAAAA")
    runs = scoring_runs(m)
    assert len(runs) == 2
    assert runs[0]["team"] == "home" and runs[0]["length"] == 3
    assert runs[1]["team"] == "away" and runs[1]["length"] == 4
    # A vendég-sorozat a 3-0-s hazai állásból indult, 3-4-re fordítva.
    assert runs[1]["score_before"] == [3, 0]
    assert runs[1]["score_after"] == [3, 4]


def test_min_len_parameter():
    """A küszöb állítható: min_len=2-nél a 2-es sorozat is bekerül."""
    m = _match_from_goals("HHA")
    assert scoring_runs(m, min_len=2)[0]["length"] == 2


def test_no_goals_no_runs():
    m = Match(_meta(), [Frame(t=t, players=[], ball=None) for t in range(20)])
    assert scoring_runs(m) == []
