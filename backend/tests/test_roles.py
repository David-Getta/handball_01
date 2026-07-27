"""
Tesztek a poszt-becslésre (roles.py).

Futtatás:
    python -m pytest tests/test_roles.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (  # noqa: E402
    Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.roles import estimate_positions  # noqa: E402


def _pl(tid, team, x, y):
    return PlayerPosition(track_id=tid, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0)


def test_estimates_pivot_wing_and_backcourt():
    """A támadó-fázis átlaghelye kiadja a posztokat: beálló középen
    közel, szélső a sávban, irányító középen távol."""
    frames = []
    for t in range(150):  # 6 mp hazai birtoklás (+x kapura támadva)
        frames.append(Frame(t=t, players=[
            _pl(1, Team.HOME, 34.0, 10.0),   # beálló: 6 m, közép
            _pl(2, Team.HOME, 36.0, 2.0),    # szélső: a bal sávban
            _pl(3, Team.HOME, 28.0, 10.0),   # irányító: 12 m, közép
            _pl(4, Team.HOME, 31.5, 7.0),    # átlövő: 8,5 m, belső sáv
        ], ball=Ball(x=28.5, y=10.0, confidence=1.0)))
    m = Match(MatchMeta(match_id="rl", home_team="H", away_team="A",
                        fps=25.0), frames)
    pos = estimate_positions(m)["home"]
    assert pos[1]["poszt"] == "beálló"
    assert pos[2]["poszt"] == "szélső"
    assert pos[3]["poszt"] == "irányító"
    assert pos[4]["poszt"] == "átlövő"


def test_too_few_samples_skipped():
    """Kevés támadó-fázisú kockánál nincs becslés."""
    frames = [Frame(t=t, players=[_pl(1, Team.HOME, 34.0, 10.0)],
                    ball=Ball(x=34.2, y=10.0, confidence=1.0))
              for t in range(30)]
    m = Match(MatchMeta(match_id="rl2", home_team="H", away_team="A",
                        fps=25.0), frames)
    assert estimate_positions(m)["home"] == {}


# ---- Poszt szerinti gólmegoszlás ---------------------------------------------

# A poszt-becsléshez használt hazai felállás (a +x kapura támadva).
_SPOTS = {1: (34.0, 10.0),    # beálló: 6 m, közép
          2: (36.0, 2.0),     # szélső: a bal sávban
          3: (28.0, 10.0),    # irányító: 12 m, közép
          4: (31.5, 7.0)}     # átlövő: 8,5 m, belső sáv


def _lineup(holder_id=None):
    """A négy hazai játékos; ha van holder, a labda nála van."""
    players = [_pl(tid, Team.HOME, x, y) for tid, (x, y) in _SPOTS.items()]
    if holder_id is None:
        return players, Ball(x=28.5, y=10.0, confidence=1.0)
    hx, hy = _SPOTS[holder_id]
    return players, Ball(x=hx, y=hy, confidence=1.0)


def _role_goal_match(scorers, warmup=150):
    """Poszt-mintát adó birtoklás, majd a `scorers` listája szerint
    egy-egy gól (a lövő birtokol, aztán a labda a +x kapuba száguld)."""
    frames = []
    t = 0
    for _ in range(warmup):
        players, ball = _lineup()
        frames.append(Frame(t=t, players=players, ball=ball))
        t += 1
    for tid in scorers:
        # A labda lassan (lövés-küszöb alatt) a lövőhöz vándorol, hogy a
        # helyváltás ne látsszon lövésnek.
        sx, sy = _SPOTS[tid]
        for i in range(1, 61):
            f_ = i / 60.0
            frames.append(Frame(
                t=t, players=_lineup()[0],
                ball=Ball(x=28.5 + (sx - 28.5) * f_,
                          y=10.0 + (sy - 10.0) * f_, confidence=1.0)))
            t += 1
        for _ in range(3):           # a lövő birtokolja a labdát
            players, ball = _lineup(tid)
            frames.append(Frame(t=t, players=players, ball=ball))
            t += 1
        # A lövés a lövő helyéről indul a kapuba (kb. 1 m/kocka), így a
        # labdához legközelebbi ember a lövés kezdetén ő maga.
        sx, sy = _SPOTS[tid]
        steps = max(3, int(round(40.5 - sx)))
        for i in range(1, steps + 1):
            f_ = i / steps
            players, _ = _lineup()
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=sx + (40.5 - sx) * f_,
                                          y=sy + (10.0 - sy) * f_,
                                          confidence=1.0)))
            t += 1
        for _ in range(25):          # szünet a gólok közt
            players, ball = _lineup()
            frames.append(Frame(t=t, players=players, ball=ball))
            t += 1
    return Match(MatchMeta(match_id="rg", home_team="H", away_team="A",
                           fps=25.0), frames)


def test_goals_by_role_finds_the_wing_heavy_attack():
    """Hat gólból négy a szélsőé → a szélső-védekezés az első feladat."""
    from handball.pipeline.roles import goals_by_role

    rec = goals_by_role(_role_goal_match([2, 2, 2, 2, 1, 1]))["home"]
    assert rec["goals"] == 6
    assert rec["roles"]["szélső"] == 4
    assert rec["top"] is not None
    assert rec["top"]["poszt"] == "szélső" and rec["top"]["goals"] == 4


def test_goals_by_role_balanced_attack_has_no_top():
    """Ha két poszt holtversenyben áll, nincs kiemelt poszt."""
    from handball.pipeline.roles import goals_by_role

    rec = goals_by_role(_role_goal_match([1, 1, 1, 2, 2, 2]))["home"]
    assert rec["goals"] == 6
    assert rec["top"] is None


def test_goals_by_role_needs_enough_goals():
    """Kevés (5-nél kevesebb) poszthoz kötött gólnál nincs ítélet."""
    from handball.pipeline.roles import goals_by_role

    rec = goals_by_role(_role_goal_match([2, 2, 2]))["home"]
    assert rec["goals"] == 3 and rec["top"] is None
