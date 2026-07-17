"""Tesztek a labdabirtoklás-arányra (possession_share)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.stats import possession_share


def _meta(fps=25.0):
    return MatchMeta(match_id="p", home_team="H", away_team="A", fps=fps)


def _pl(tid, team, x, y):
    return PlayerPosition(track_id=tid, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0)


def test_possession_share_split():
    """60 kocka hazai-birtoklás, 20 vendég → ~75/25 a meghatározott
    kockákra; 20 senki-földje kocka a contested_pct-ben."""
    frames = []
    t = 0
    for _ in range(60):  # a hazai 1-es a labdánál
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 20.0, 10.0)],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    for _ in range(20):  # a vendég 11-es a labdánál
        frames.append(Frame(t=t, players=[_pl(11, Team.AWAY, 20.0, 10.0)],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    for _ in range(20):  # nincs labda (szabad játék)
        frames.append(Frame(t=t, players=[], ball=None))
        t += 1
    ps = possession_share(Match(_meta(), frames))
    assert ps["home"]["pct"] == 75.0
    assert ps["away"]["pct"] == 25.0
    assert ps["contested_pct"] == 20.0


def test_possession_share_empty():
    m = Match(_meta(), [Frame(t=i, players=[], ball=None) for i in range(10)])
    ps = possession_share(m)
    assert ps["home"]["pct"] == 0.0 and ps["away"]["pct"] == 0.0
    assert ps["contested_pct"] == 100.0
