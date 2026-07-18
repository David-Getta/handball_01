"""
Tesztek a lidar-előkészítésre (lidar.py) — szintetikus pontfelhővel.

Futtatás:
    python -m pytest tests/test_lidar.py
"""

from __future__ import annotations

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.lidar import cluster_points, refine_with_lidar


def _cloud(cx, cy, n=20, spread=0.15, seed=1):
    rng = random.Random(seed)
    return [(cx + rng.uniform(-spread, spread),
             cy + rng.uniform(-spread, spread)) for _ in range(n)]


def test_cluster_points_finds_two_players_and_drops_noise():
    pts = (_cloud(10.0, 5.0, seed=1) + _cloud(20.0, 12.0, seed=2)
           + [(30.0, 18.0), (31.5, 2.0)])  # 2 magányos zaj-pont
    clusters = cluster_points(pts)
    assert len(clusters) == 2
    xs = sorted(c["x"] for c in clusters)
    assert abs(xs[0] - 10.0) < 0.1 and abs(xs[1] - 20.0) < 0.1


def test_refine_with_lidar_snaps_camera_position():
    """A kamera 0,6 m-t téved — a lidar-jelölt pontos helyre igazítja;
    a lefedetlen játékos változatlan marad."""
    meta = MatchMeta(match_id="li", home_team="H", away_team="A", fps=25.0)
    m = Match(meta, [Frame(t=0, players=[
        PlayerPosition(track_id=1, team=Team.HOME, x=10.6, y=5.0,
                       source=PositionSource.MEASURED, confidence=1.0),
        PlayerPosition(track_id=2, team=Team.AWAY, x=30.0, y=15.0,
                       source=PositionSource.MEASURED, confidence=1.0),
    ])])
    cands = {0: [{"x": 10.0, "y": 5.0, "n": 25}]}
    refined = refine_with_lidar(m, cands)
    p1 = next(p for p in refined.frames[0].players if p.track_id == 1)
    p2 = next(p for p in refined.frames[0].players if p.track_id == 2)
    assert abs(p1.x - 10.0) < 1e-6      # a lidarra igazítva
    assert p1.team == Team.HOME          # az azonosság a kameráé marad
    assert abs(p2.x - 30.0) < 1e-6      # lefedetlen → változatlan


def test_refine_one_candidate_serves_one_player():
    """Egy lidar-jelölt csak egy (a legközelebbi) játékost igazít."""
    meta = MatchMeta(match_id="li2", home_team="H", away_team="A", fps=25.0)
    m = Match(meta, [Frame(t=0, players=[
        PlayerPosition(track_id=1, team=Team.HOME, x=10.2, y=5.0,
                       source=PositionSource.MEASURED, confidence=1.0),
        PlayerPosition(track_id=2, team=Team.HOME, x=10.8, y=5.0,
                       source=PositionSource.MEASURED, confidence=1.0),
    ])])
    cands = {0: [{"x": 10.0, "y": 5.0, "n": 25}]}
    refined = refine_with_lidar(m, cands)
    snapped = [p for p in refined.frames[0].players if abs(p.x - 10.0) < 1e-6]
    assert len(snapped) == 1 and snapped[0].track_id == 1
