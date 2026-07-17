"""
Tesztek az irányító-függés elemzésre (playmaker.py).

A pálya 40x20 m; a HAZAI a +x (x=40) kapu felé támad. Az 1-es a hazai
irányító: a vele futott támadások lövésig jutnak, a nélküle futottak nem.

Futtatás:
    python -m pytest tests/test_playmaker.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.playmaker import playmaker_dependency


def _meta(fps=25.0):
    return MatchMeta(match_id="p", home_team="H", away_team="A", fps=fps)


def _pl(track_id, team, x, y):
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0)


def _attack(t, holder_id, shoot):
    """Egy hazai támadás: 30 kocka birtoklás a támadó térfélen a megadott
    játékosnál; shoot esetén a végén lövés a +x kapura. Utána 10 kocka
    vendég-birtoklás a másik térfélen (ez zárja le a szakaszt)."""
    frames = []
    for i in range(30):
        frames.append(Frame(
            t=t, players=[_pl(holder_id, Team.HOME, 28.0, 10.0)],
            ball=Ball(x=28.0, y=10.0, confidence=1.0)))
        t += 1
    if shoot:
        for i in range(7):
            frames.append(Frame(
                t=t, players=[_pl(holder_id, Team.HOME, 33.0, 10.0)],
                ball=Ball(x=34.0 + i, y=10.0, confidence=1.0)))
            t += 1
    for _ in range(10):
        frames.append(Frame(
            t=t, players=[_pl(30, Team.AWAY, 12.0, 10.0)],
            ball=Ball(x=12.0, y=10.0, confidence=1.0)))
        t += 1
    return frames, t


def _match(with_pm=4, without_pm=4):
    """with_pm támadás az 1-essel (mind lövésig jut) + without_pm a 2-essel
    (egyik sem jut lövésig). Az 1-es így a legtöbbet birtokló játékos is."""
    frames = []
    t = 0
    for _ in range(with_pm):
        fs, t = _attack(t, holder_id=1, shoot=True)
        frames += fs
    for _ in range(without_pm):
        fs, t = _attack(t, holder_id=2, shoot=False)
        frames += fs
    return Match(_meta(), frames)


def test_high_dependency_detected():
    d = playmaker_dependency(_match())["home"]
    assert d["playmaker"] == 1
    assert d["with"]["attacks"] >= 3 and d["without"]["attacks"] >= 3
    # Vele minden támadás lövésig jutott, nélküle egy sem.
    assert d["with"]["shots"] == d["with"]["attacks"]
    assert d["without"]["shots"] == 0
    assert d["shot_rate_drop"] == 1.0
    assert d["dependency"] == "magas"


def test_no_dependency_when_both_groups_score():
    """Ha nélküle is ugyanúgy lövésig jutnak, nincs függés-jelzés."""
    frames = []
    t = 0
    for _ in range(4):
        fs, t = _attack(t, holder_id=1, shoot=True)
        frames += fs
    for _ in range(4):
        fs, t = _attack(t, holder_id=2, shoot=True)
        frames += fs
    d = playmaker_dependency(Match(_meta(), frames))["home"]
    assert d["shot_rate_drop"] == 0.0
    assert d["dependency"] is None


def test_too_few_attacks_gives_none():
    """Kevés minta (nélküle < 3 támadás): nincs ítélet."""
    d = playmaker_dependency(_match(with_pm=4, without_pm=1))["home"]
    assert d["shot_rate_drop"] is None
    assert d["dependency"] is None


def test_empty_match():
    m = Match(_meta(), [Frame(t=i, players=[], ball=None) for i in range(10)])
    d = playmaker_dependency(m)
    assert d["home"]["playmaker"] is None
    assert d["away"]["playmaker"] is None
