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


# ---- Gólpassz-posztok (melyik poszt készíti elő a gólokat) ------------------

def test_assists_by_role_finds_the_backcourt_feeder():
    """A szélső-gólok utolsó átadója az átlövő (4-es, a labda útjába
    esik) → hat gólpasszból négy az átlövőé, ő a kiemelt előkészítő."""
    from handball.pipeline.roles import assists_by_role

    rec = assists_by_role(_role_goal_match([2, 2, 2, 2, 1, 1]))["home"]
    assert rec["assists"] == 6
    assert rec["top"] is not None
    assert rec["top"]["poszt"] == "átlövő"
    assert rec["top"]["assists"] == 4


def test_assists_by_role_needs_enough_assists():
    """Kevés (5-nél kevesebb) poszthoz kötött gólpassznál nincs
    kiemelt poszt."""
    from handball.pipeline.roles import assists_by_role

    rec = assists_by_role(_role_goal_match([2, 2, 1]))["home"]
    assert rec["top"] is None


# ---- Poszt szerinti befejezés-hatékonyság ------------------------------------

def _role_shot_match(attempts, warmup=150):
    """Poszt-mintát adó birtoklás, majd `attempts` = [(lövő, gól?)].

    Gólnál a labda a kapufák közé (y=10) érkezik; kihagyásnál olyan
    pályán, amely a gólvonal környékén VÉGIG a kapufákon kívül halad
    (a szélsőnél a saját sávjában marad, a középről indulóknál y=14
    felé) — így a lövés lövés marad, nem lesz gól.
    """
    frames = []
    t = 0
    for _ in range(warmup):
        players, ball = _lineup()
        frames.append(Frame(t=t, players=players, ball=ball))
        t += 1
    for tid, scored in attempts:
        sx, sy = _SPOTS[tid]
        cur_x, cur_y = (frames[-1].ball.x, frames[-1].ball.y)
        for i in range(1, 61):  # lassan a lövőhöz (nem lövés-sebesség)
            f_ = i / 60.0
            frames.append(Frame(
                t=t, players=_lineup()[0],
                ball=Ball(x=cur_x + (sx - cur_x) * f_,
                          y=cur_y + (sy - cur_y) * f_, confidence=1.0)))
            t += 1
        for _ in range(3):  # a lövő birtokolja a labdát
            players, ball = _lineup(tid)
            frames.append(Frame(t=t, players=players, ball=ball))
            t += 1
        target_y = 10.0 if scored else (sy if sy < 8.0 else 14.0)
        steps = max(3, int(round(40.5 - sx)))
        for i in range(1, steps + 1):
            f_ = i / steps
            frames.append(Frame(
                t=t, players=_lineup()[0],
                ball=Ball(x=sx + (40.5 - sx) * f_,
                          y=sy + (target_y - sy) * f_, confidence=1.0)))
            t += 1
        for _ in range(25):  # szünet a kísérletek közt
            players, ball = _lineup()
            frames.append(Frame(t=t, players=players, ball=ball))
            t += 1
    return Match(MatchMeta(match_id="rs", home_team="H", away_team="A",
                           fps=25.0), frames)


def test_shot_efficiency_by_role_separates_the_two_posts():
    """A szélsőjük sokat lő, keveset szerez — arra rá lehet engedni."""
    from handball.pipeline.roles import SER_MIN_SHOTS, shot_efficiency_by_role

    attempts = ([(2, False)] * 5 + [(2, True)]      # szélső: 1/6
                + [(1, True)] * 5 + [(1, False)])   # beálló: 5/6
    rec = shot_efficiency_by_role(_role_shot_match(attempts))["home"]
    assert rec["shots"] >= 2 * SER_MIN_SHOTS, rec
    assert rec["roles"]["szélső"]["pct"] < rec["roles"]["beálló"]["pct"], rec
    assert rec["worst"] is not None and rec["worst"]["poszt"] == "szélső"
    assert rec["best"] is not None and rec["best"]["poszt"] == "beálló"
    assert rec["worst"]["gap_pp"] < 0 < rec["best"]["gap_pp"]


def test_shot_efficiency_by_role_silent_with_few_shots():
    """Két lövésből nem mondunk ítéletet egyik posztról sem."""
    from handball.pipeline.roles import shot_efficiency_by_role

    rec = shot_efficiency_by_role(
        _role_shot_match([(2, True), (1, False)]))["home"]
    assert rec["best"] is None and rec["worst"] is None, rec


# ---- Gólpassz-tengelyek poszt szerint ----------------------------------------

# Két hazai poszt: irányító (12 m, közép) és beálló (6 m, közép).
_ARP = {3: (28.0, 10.0), 1: (34.0, 10.0)}


def _arp_players(ball_xy=None):
    players = [_pl(tid, Team.HOME, x, y) for tid, (x, y) in _ARP.items()]
    players.append(_pl(20, Team.AWAY, 37.0, 16.0))  # távoli vendég
    return players


def _arp_match(passes, warmup=150):
    """`passes` = [(passzoló, lövő)] — mindegyikből gólpasszos gól lesz."""
    frames = []
    t = 0

    def _add(bx, by):
        nonlocal t
        frames.append(Frame(t=t, players=_arp_players(),
                            ball=Ball(x=bx, y=by, confidence=1.0)))
        t += 1

    for _ in range(warmup):
        _add(28.0, 10.0)
    for passer, scorer in passes:
        px, py = _ARP[passer]
        sx, sy = _ARP[scorer]
        cur = (frames[-1].ball.x, frames[-1].ball.y)
        for i in range(1, 61):  # lassan a passzolóhoz (nem lövés)
            f_ = i / 60.0
            _add(cur[0] + (px - cur[0]) * f_, cur[1] + (py - cur[1]) * f_)
        for _ in range(3):      # a passzoló birtokol
            _add(px, py)
        for i in range(1, 26):  # a passz: lassan a lövőhöz
            f_ = i / 25.0
            _add(px + (sx - px) * f_, py + (sy - py) * f_)
        for _ in range(3):      # a lövő birtokol
            _add(sx, sy)
        steps = max(3, int(round(40.5 - sx)))
        for i in range(1, steps + 1):   # a lövés a kapuba
            f_ = i / steps
            _add(sx + (40.5 - sx) * f_, sy + (10.0 - sy) * f_)
        for _ in range(25):
            _add(40.5, 10.0)
    return Match(MatchMeta(match_id="ap", home_team="H", away_team="A",
                           fps=25.0), frames)


def test_assist_role_pairs_finds_the_axis():
    """Négy gól ugyanazon a tengelyen → az irányító–beálló vonal a téma."""
    from handball.pipeline.roles import assist_role_pairs

    rec = assist_role_pairs(_arp_match([(3, 1)] * 4))["home"]
    assert rec["pairs_total"] == 4, rec
    assert rec["pairs"].get("irányító→beálló") == 4, rec
    assert rec["top"] is not None
    assert rec["top"]["from"] == "irányító" and rec["top"]["to"] == "beálló"
    assert rec["top"]["share_pct"] == 100.0


def test_assist_role_pairs_silent_with_few_goals():
    """Két gólpasszos gólból nincs tengely-ítélet."""
    from handball.pipeline.roles import assist_role_pairs

    rec = assist_role_pairs(_arp_match([(3, 1)] * 2))["home"]
    assert rec["pairs_total"] <= 2, rec
    assert rec["top"] is None, rec
