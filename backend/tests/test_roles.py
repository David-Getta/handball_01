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


# ---- Egyirányú játékosok (védő- és támadó-specialisták) ---------------------

def _phase_match(block_frames=1600, specialists=True):
    """Váltakozó birtoklás: hazai, majd vendég labda. Ha specialists
    igaz, a hazai 3-as csak védekezéskor, a 4-es csak támadáskor van
    fent; az 1-es mindig."""
    frames = []
    t = 0
    for phase in ("atk", "def"):
        holder = (_pl(1, Team.HOME, 20.0, 10.0) if phase == "atk"
                  else _pl(21, Team.AWAY, 20.0, 10.0))
        for _ in range(block_frames):
            players = [holder, _pl(1, Team.HOME, 20.0, 10.0)] \
                if phase == "def" else [holder]
            if specialists:
                if phase == "def":
                    players.append(_pl(3, Team.HOME, 10.0, 10.0))
                else:
                    players.append(_pl(4, Team.HOME, 30.0, 10.0))
            else:
                players.append(_pl(3, Team.HOME, 10.0, 10.0))
                players.append(_pl(4, Team.HOME, 30.0, 10.0))
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    return Match(MatchMeta(match_id="ph", home_team="H", away_team="A",
                           fps=25.0), frames)


def test_phase_specialists_finds_the_swapped_units():
    """A 3-as csak védekezik, a 4-es csak támad → váltott sorokkal
    játszanak."""
    from handball.pipeline.roles import phase_specialists

    rec = phase_specialists(_phase_match())["home"]
    def_ids = [r["player_id"] for r in rec["def_specialists"]]
    atk_ids = [r["player_id"] for r in rec["atk_specialists"]]
    assert 3 in def_ids and 4 in atk_ids
    assert rec["verdict"] == "váltott sorokkal játszanak"


def test_phase_specialists_two_way_players_no_verdict():
    """Ha mindenki mindkét fázisban fent van, nincs váltott sor."""
    from handball.pipeline.roles import phase_specialists

    rec = phase_specialists(_phase_match(specialists=False))["home"]
    assert rec["def_specialists"] == [] and rec["atk_specialists"] == []
    assert rec["verdict"] is None


def test_phase_specialists_needs_enough_frames():
    """Kevés (1500-nál kevesebb) fázis-kockánál nincs ítélet."""
    from handball.pipeline.roles import phase_specialists

    rec = phase_specialists(_phase_match(block_frames=400))["home"]
    assert rec["verdict"] is None


# ---- Poszt-hibák (melyik poszt veszíti el a labdát) -------------------------

def _role_turnover_match(losers, warmup=150):
    """Poszt-mintát adó birtoklás, majd a `losers` szerint egy-egy
    labdaeladás: a vesztes birtokol, aztán a labdát a mellette álló
    vendég szerzi meg."""
    frames = []
    t = 0
    for _ in range(warmup):
        players, ball = _lineup()
        frames.append(Frame(t=t, players=players, ball=ball))
        t += 1
    taker = _pl(21, Team.AWAY, 20.0, 16.0)   # a szerző vendég helye
    for tid in losers:
        sx, sy = _SPOTS[tid]
        for i in range(1, 61):     # a labda lassan a veszteshez ér
            f_ = i / 60.0
            frames.append(Frame(
                t=t, players=_lineup()[0] + [taker],
                ball=Ball(x=28.5 + (sx - 28.5) * f_,
                          y=10.0 + (sy - 10.0) * f_, confidence=1.0)))
            t += 1
        for _ in range(5):         # a vesztes birtokol
            frames.append(Frame(t=t, players=_lineup()[0] + [taker],
                                ball=Ball(x=sx, y=sy, confidence=1.0)))
            t += 1
        for _ in range(10):        # a labda a vendégnél terem (szerzés)
            frames.append(Frame(t=t, players=_lineup()[0] + [taker],
                                ball=Ball(x=20.0, y=16.0, confidence=1.0)))
            t += 1
        for _ in range(25):        # vissza a középre, új kör
            players, ball = _lineup()
            frames.append(Frame(t=t, players=[taker] + players,
                                ball=ball))
            t += 1
    return Match(MatchMeta(match_id="rt", home_team="H", away_team="A",
                           fps=25.0), frames)


def test_turnovers_by_role_finds_the_leaky_post():
    """Hat eladásból négy a szélsőé → a szélső-bejátszás vadászható."""
    from handball.pipeline.roles import turnovers_by_role

    rec = turnovers_by_role(_role_turnover_match([2, 2, 2, 2, 1, 1]))["home"]
    assert rec["turnovers"] == 6
    assert rec["roles"]["szélső"] == 4
    assert rec["top"] is not None
    assert rec["top"]["poszt"] == "szélső" and rec["top"]["turnovers"] == 4


def test_turnovers_by_role_balanced_has_no_top():
    """Holtversenyben álló posztoknál nincs kiemelt hibázó."""
    from handball.pipeline.roles import turnovers_by_role

    rec = turnovers_by_role(_role_turnover_match([1, 1, 1, 2, 2, 2]))["home"]
    assert rec["turnovers"] == 6 and rec["top"] is None


def test_turnovers_by_role_needs_enough_turnovers():
    """Kevés (6-nál kevesebb) poszthoz kötött eladásnál nincs ítélet."""
    from handball.pipeline.roles import turnovers_by_role

    rec = turnovers_by_role(_role_turnover_match([2, 2, 2]))["home"]
    assert rec["turnovers"] == 3 and rec["top"] is None
