"""
Tesztek az elemző rétegre (analytics.py): hőtérkép + csapat-összegzés.

Tiszta adatfeldolgozás, videó nélkül. Kézzel összerakott Match-ekkel ellenőrizzük
a cella-besorolást, az összegeket és a súlypont/kiterjedés számítást.

Futtatás:
    python tests/test_analytics.py
"""

from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, Team, PositionSource,
)
from handball.pipeline.analytics import (
    compute_player_heatmap, compute_team_heatmap, compute_team_summary,
)


def _meta():
    return MatchMeta(match_id="t", home_team="A", away_team="B", fps=25.0)


def test_player_heatmap_single_cell():
    """Egy helyben álló játékos minden pontja UGYANABBA a cellába kerül."""
    # (10, 5) m a 40x20 pályán, 20x10 rácsnál: ix=int(10/40*20)=5, iy=int(5/20*10)=2
    frames = [
        Frame(t=i, players=[PlayerPosition(
            track_id=1, team=Team.HOME, x=10.0, y=5.0,
            source=PositionSource.MEASURED, confidence=1.0)])
        for i in range(7)
    ]
    hm = compute_player_heatmap(Match(_meta(), frames), track_id=1)
    assert hm.total == 7.0
    assert hm.grid[2][5] == 7.0
    # minden más cella üres
    assert sum(sum(row) for row in hm.grid) == 7.0


def test_heatmap_excludes_estimated_by_default():
    """Alapból a BECSÜLT pozíciókat nem számoljuk a hőtérképbe."""
    frames = [
        Frame(t=0, players=[PlayerPosition(track_id=1, team=Team.HOME, x=10.0, y=5.0,
                                           source=PositionSource.MEASURED, confidence=1.0)]),
        Frame(t=1, players=[PlayerPosition(track_id=1, team=Team.HOME, x=30.0, y=15.0,
                                           source=PositionSource.ESTIMATED, confidence=0.5)]),
    ]
    match = Match(_meta(), frames)
    assert compute_player_heatmap(match, 1).total == 1.0                     # csak a mért
    assert compute_player_heatmap(match, 1, include_estimated=True).total == 2.0


def test_team_heatmap_sums_all_players():
    """A csapat-hőtérkép a csapat minden mért játékosát összegzi."""
    frame = Frame(t=0, players=[
        PlayerPosition(track_id=1, team=Team.HOME, x=5.0, y=5.0, source=PositionSource.MEASURED, confidence=1.0),
        PlayerPosition(track_id=2, team=Team.HOME, x=35.0, y=15.0, source=PositionSource.MEASURED, confidence=1.0),
        PlayerPosition(track_id=11, team=Team.AWAY, x=20.0, y=10.0, source=PositionSource.MEASURED, confidence=1.0),
    ])
    match = Match(_meta(), [frame])
    assert compute_team_heatmap(match, Team.HOME).total == 2.0
    assert compute_team_heatmap(match, Team.AWAY).total == 1.0


def test_team_summary_centroid_and_spread():
    """A súlypont a két játékos átlaga; a kiterjedés a szórásuk."""
    # Két hazai: (10,8) és (20,12) -> centroid (15,10).
    frame = Frame(t=0, players=[
        PlayerPosition(track_id=1, team=Team.HOME, x=10.0, y=8.0, source=PositionSource.MEASURED, confidence=1.0),
        PlayerPosition(track_id=2, team=Team.HOME, x=20.0, y=12.0, source=PositionSource.MEASURED, confidence=1.0),
    ])
    s = compute_team_summary(Match(_meta(), [frame]), Team.HOME)
    assert abs(s.avg_centroid_x - 15.0) < 1e-9
    assert abs(s.avg_centroid_y - 10.0) < 1e-9
    # pstdev két pontra: |érték - átlag| = 5 (x) és 2 (y)
    assert abs(s.avg_spread_x - 5.0) < 1e-9
    assert abs(s.avg_spread_y - 2.0) < 1e-9
    assert s.frames_counted == 1


def test_team_summary_empty_when_too_few():
    """Ha egy frame-en <2 mért játékos van, nem számolunk súlypontot."""
    frame = Frame(t=0, players=[
        PlayerPosition(track_id=1, team=Team.HOME, x=10.0, y=8.0, source=PositionSource.MEASURED, confidence=1.0),
    ])
    s = compute_team_summary(Match(_meta(), [frame]), Team.HOME)
    assert s.frames_counted == 0


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
