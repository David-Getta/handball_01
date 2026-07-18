"""
Tesztek a nézet-fúzióra (fusion.py) — szintetikus két-kamerás nézetekkel.

Futtatás:
    python -m pytest tests/test_fusion.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.fusion import fuse_matches


def _meta():
    return MatchMeta(match_id="fu", home_team="H", away_team="A", fps=25.0)


def _pl(tid, team, x, y):
    return PlayerPosition(track_id=tid, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0)


def test_fusion_averages_noisy_views():
    """Ugyanaz a játékos két nézetben ±0,2 m zajjal → a fúzió a kettő
    átlagát adja (pontosabb, mint bármelyik nézet)."""
    a = Match(_meta(), [Frame(t=0, players=[_pl(1, Team.HOME, 19.8, 10.2)])])
    b = Match(_meta(), [Frame(t=0, players=[_pl(7, Team.HOME, 20.2, 9.8)])])
    fused = fuse_matches([a, b])
    assert len(fused.frames[0].players) == 1
    p = fused.frames[0].players[0]
    assert abs(p.x - 20.0) < 0.01 and abs(p.y - 10.0) < 0.01


def test_fusion_fills_occlusion_from_other_view():
    """A 2. kockán az egyik nézetből eltűnik a játékos (takarás) — a
    másik nézet kitölti, és a fúziós track-azonosító folytonos marad."""
    a = Match(_meta(), [
        Frame(t=0, players=[_pl(1, Team.HOME, 20.0, 10.0)]),
        Frame(t=1, players=[]),                       # takarás az A nézetben
        Frame(t=2, players=[_pl(1, Team.HOME, 20.6, 10.0)]),
    ])
    b = Match(_meta(), [
        Frame(t=0, players=[_pl(9, Team.HOME, 20.0, 10.0)]),
        Frame(t=1, players=[_pl(9, Team.HOME, 20.3, 10.0)]),
        Frame(t=2, players=[_pl(9, Team.HOME, 20.6, 10.0)]),
    ])
    fused = fuse_matches([a, b])
    tids = [fused.frames[i].players[0].track_id for i in range(3)]
    assert len(set(tids)) == 1          # végig ugyanaz a fúziós track
    assert fused.frames[1].players     # a takart kockán is van pozíció


def test_fusion_keeps_separate_players_apart():
    """Két különböző (2 m-nél távolabbi) játékos nem olvad össze; az
    azonos helyen álló ELLENFÉL sem."""
    a = Match(_meta(), [Frame(t=0, players=[
        _pl(1, Team.HOME, 10.0, 10.0),
        _pl(2, Team.HOME, 14.0, 10.0),
        _pl(11, Team.AWAY, 10.2, 10.0),
    ])])
    fused = fuse_matches([a])
    assert len(fused.frames[0].players) == 3


def test_fusion_picks_highest_confidence_ball():
    a = Match(_meta(), [Frame(t=0, players=[],
                              ball=Ball(x=10.0, y=5.0, confidence=0.4))])
    b = Match(_meta(), [Frame(t=0, players=[],
                              ball=Ball(x=10.1, y=5.0, confidence=0.9))])
    fused = fuse_matches([a, b])
    assert abs(fused.frames[0].ball.x - 10.1) < 1e-6
