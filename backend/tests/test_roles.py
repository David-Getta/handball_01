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


# ---- Poszt-váltás a szünetre -------------------------------------------------

def _rss_match(first_scorers, second_scorers, break_s=90.0):
    """Első félidő góljai, ~90 mp üres szünet, majd a második félidő.

    A szünetben nincs mért játékos — így ismeri fel a félidő-kereső.
    """
    first = _role_goal_match(first_scorers)
    second = _role_goal_match(second_scorers)
    frames = list(first.frames)
    t = frames[-1].t + 1
    for _ in range(int(break_s * 25)):
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    for f in second.frames:
        frames.append(Frame(t=t, players=f.players, ball=f.ball))
        t += 1
    return Match(MatchMeta(match_id="rss", home_team="H", away_team="A",
                           fps=25.0), frames)


def test_role_share_shift_names_the_rising_post():
    """Szünet előtt a szélső, utána a beálló viszi a gólokat."""
    from handball.pipeline.halftime import detect_halftime
    from handball.pipeline.roles import role_share_shift

    match = _rss_match([2, 2, 2, 2, 1], [1, 1, 1, 1, 2])
    assert detect_halftime(match) is not None, "kell felismert félidő"
    rec = role_share_shift(match)["home"]
    assert rec["first_total"] >= 4 and rec["second_total"] >= 4, rec
    assert rec["shift"] is not None, rec
    assert rec["shift"]["poszt"] in ("beálló", "szélső"), rec
    assert rec["verdict"] and "szünet után" in rec["verdict"], rec
    if rec["shift"]["poszt"] == "beálló":
        assert rec["shift"]["gap_pp"] > 0, rec
    else:
        assert rec["shift"]["gap_pp"] < 0, rec


def test_role_share_shift_silent_without_halftime():
    """Felismert félidő nélkül nincs ítélet — nem találgatunk."""
    from handball.pipeline.roles import role_share_shift

    rec = role_share_shift(_role_goal_match([2, 2, 1, 1, 1]))["home"]
    assert rec["shift"] is None and rec["verdict"] is None, rec
    assert rec["first_total"] == 0 and rec["second_total"] == 0, rec


# ---- Eladás-ár poszt szerint -------------------------------------------------

# Hazai posztok az eladás-teszthez: irányító (12 m) és beálló (6 m).
_RTC = {3: (28.0, 10.0), 1: (34.0, 10.0)}


def _rtc_players():
    players = [_pl(tid, Team.HOME, x, y) for tid, (x, y) in _RTC.items()]
    players.append(_pl(20, Team.AWAY, 15.0, 10.0))
    return players


def _rtc_match(losses, warmup=150):
    """`losses` = [(eladó, büntetve?)] — eladás, majd (ha büntetve) az
    ellenfél gólja 30 mp-en belül."""
    frames = []
    t = 0

    def _add(bx, by):
        nonlocal t
        frames.append(Frame(t=t, players=_rtc_players(),
                            ball=Ball(x=bx, y=by, confidence=1.0)))
        t += 1

    for _ in range(warmup):
        _add(28.0, 10.0)
    for loser, punished in losses:
        lx, ly = _RTC[loser]
        cur = (frames[-1].ball.x, frames[-1].ball.y)
        for i in range(1, 61):  # vissza a hazai birtokoshoz
            f_ = i / 60.0
            _add(cur[0] + (lx - cur[0]) * f_, cur[1] + (ly - cur[1]) * f_)
        for _ in range(5):      # a hazai játékos birtokol
            _add(lx, ly)
        for i in range(1, 31):  # a labda a vendéghez kerül: ELADÁS
            f_ = i / 30.0
            _add(lx + (15.0 - lx) * f_, 10.0)
        for _ in range(20):     # vendég-birtoklás (a lövés-elnyomás miatt)
            _add(15.0, 10.0)
        if punished:
            for i in range(1, 16):  # lövés a hazai kapuba: vendég-gól
                _add(15.0 - 15.5 * (i / 15.0), 10.0)
            for _ in range(25):
                _add(-0.5, 10.0)
        else:
            for _ in range(40):     # marad kint, nincs gól
                _add(15.0, 10.0)
    return Match(MatchMeta(match_id="rt", home_team="H", away_team="A",
                           fps=25.0), frames)


def test_role_turnover_cost_names_the_punished_post():
    """Az irányítójuk eladásai rendre gólba kerülnek → őt kell letámadni."""
    from handball.pipeline.roles import RTC_MIN_TO, role_turnover_cost

    rec = role_turnover_cost(_rtc_match([(3, True)] * 4))["home"]
    assert rec["turnovers"] >= RTC_MIN_TO, rec
    assert rec["worst"] is not None, rec
    assert rec["worst"]["poszt"] == "irányító", rec
    assert rec["worst"]["rate_pct"] >= 35.0, rec
    assert rec["roles"]["irányító"]["punished"] >= RTC_MIN_TO, rec


def test_role_turnover_cost_silent_with_few_turnovers():
    """Két eladásból nincs ítélet egyik posztról sem."""
    from handball.pipeline.roles import role_turnover_cost

    rec = role_turnover_cost(_rtc_match([(3, True)] * 2))["home"]
    assert rec["worst"] is None, rec


# ---- Poszt-állás (hátrányban melyik poszt fejez be) --------------------------

def _rbs_match(home_scorers_trailing, home_scorers_rest, away_goals=5,
               warmup=150):
    """Előbb a vendég szerez `away_goals` gólt (a hazai hátrányba kerül),
    utána a hazai gólok — előbb hátrányban, majd a többi állásban."""
    frames = []
    t = 0

    def _add(bx, by, players):
        nonlocal t
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=bx, y=by, confidence=1.0)))
        t += 1

    def _lineup_away():
        players = [_pl(tid, Team.HOME, x, y) for tid, (x, y) in _SPOTS.items()]
        players.append(_pl(20, Team.AWAY, 10.0, 10.0))
        return players

    def _travel(tx, ty, steps=60):
        cur = (frames[-1].ball.x, frames[-1].ball.y) if frames else (28.5, 10.0)
        for i in range(1, steps + 1):
            f_ = i / steps
            _add(cur[0] + (tx - cur[0]) * f_, cur[1] + (ty - cur[1]) * f_,
                 _lineup_away())

    for _ in range(warmup):
        _add(28.5, 10.0, _lineup_away())
    for _ in range(away_goals):
        _travel(10.0, 10.0)
        for _ in range(20):
            _add(10.0, 10.0, _lineup_away())
        for i in range(1, 11):          # vendég-gól a hazai kapuba
            _add(10.0 - 10.5 * (i / 10.0), 10.0, _lineup_away())
        for _ in range(25):
            _add(-0.5, 10.0, _lineup_away())
    for tid in list(home_scorers_trailing) + list(home_scorers_rest):
        sx, sy = _SPOTS[tid]
        # Előbb ki a kapu-közeli zónából (a lövés-debounce így nyílik
        # újra), csak utána a lövő helyére.
        _travel(25.0, 10.0, steps=40)
        _travel(sx, sy, steps=40)
        for _ in range(5):
            _add(sx, sy, _lineup_away())
        steps = max(3, int(round(40.5 - sx)))
        for i in range(1, steps + 1):   # hazai gól
            f_ = i / steps
            _add(sx + (40.5 - sx) * f_, sy + (10.0 - sy) * f_,
                 _lineup_away())
        for _ in range(25):
            _add(40.5, 10.0, _lineup_away())
    return Match(MatchMeta(match_id="rb", home_team="H", away_team="A",
                           fps=25.0), frames)


def test_role_share_by_score_names_the_trailing_finisher():
    """Hátrányban a szélső viszi a befejezést, egyenlítés után a beálló."""
    from handball.pipeline.roles import role_share_by_score

    rec = role_share_by_score(_rbs_match([2] * 5, [1] * 4))["home"]
    assert rec["trailing_total"] >= 4 and rec["rest_total"] >= 4, rec
    assert rec["shift"] is not None, rec
    assert rec["verdict"] and "hátrányban" in rec["verdict"], rec
    if rec["shift"]["poszt"] == "szélső":
        assert rec["shift"]["gap_pp"] > 0, rec
    else:
        assert rec["shift"]["gap_pp"] < 0, rec


def test_role_share_by_score_silent_without_both_buckets():
    """Ha nincs hátrányban szerzett góljuk, nincs ítélet."""
    from handball.pipeline.roles import role_share_by_score

    rec = role_share_by_score(_role_goal_match([2, 2, 1, 1, 1]))["home"]
    assert rec["trailing_total"] == 0, rec
    assert rec["shift"] is None and rec["verdict"] is None, rec


# ---- Poszt-birtoklás ---------------------------------------------------------

def _rps_match(holder_id, frames_n=400):
    """A megadott hazai játékos tartja a labdát szervezett támadásban."""
    frames = []
    for t in range(frames_n):
        players, ball = _lineup(holder_id)
        frames.append(Frame(t=t, players=players, ball=ball))
    return Match(MatchMeta(match_id="rp", home_team="H", away_team="A",
                           fps=25.0), frames)


def test_role_possession_share_names_the_dominant_post():
    """Ha a labda végig az irányítónál van, őt kell letámadni."""
    from handball.pipeline.roles import role_possession_share

    rec = role_possession_share(_rps_match(3))["home"]
    assert rec["frames"] >= 250, rec
    assert rec["top"] is not None and rec["top"]["poszt"] == "irányító", rec
    assert rec["top"]["pct"] >= 55.0, rec
    assert rec["verdict"] and "irányító" in rec["verdict"], rec


def test_role_possession_share_silent_with_few_frames():
    """Rövid mintán nincs ítélet — nem találgatunk."""
    from handball.pipeline.roles import role_possession_share

    rec = role_possession_share(_rps_match(3, frames_n=200))["home"]
    assert rec["top"] is None and rec["verdict"] is None, rec


# ---- Poszt-passzháló ---------------------------------------------------------

def _rpm_match(passes, warmup=150):
    """`passes` = [(passzoló, fogadó)] — mindegyikből egy passz-esemény.

    A labda lassan vándorol a két poszt között; a birtokos-váltás adja
    a passzt. Lövés nincs: a labda a kaputól végig 6 méternél messzebb
    marad.
    """
    frames = []
    t = 0

    def _add(bx, by):
        nonlocal t
        frames.append(Frame(t=t, players=_arp_players(),
                            ball=Ball(x=bx, y=by, confidence=1.0)))
        t += 1

    for _ in range(warmup):
        _add(28.0, 10.0)
    for passer, receiver in passes:
        for tid in (passer, receiver):
            tx, ty = _ARP[tid]
            cur = (frames[-1].ball.x, frames[-1].ball.y)
            for i in range(1, 26):
                f_ = i / 25.0
                _add(cur[0] + (tx - cur[0]) * f_,
                     cur[1] + (ty - cur[1]) * f_)
            for _ in range(4):
                _add(tx, ty)
    return Match(MatchMeta(match_id="pm", home_team="H", away_team="A",
                           fps=25.0), frames)


def test_role_pass_map_finds_the_busiest_lane():
    """Ha a labda mindig ugyanazon a vonalon jár, az elfogás oda kell."""
    from handball.pipeline.roles import role_pass_map

    rec = role_pass_map(_rpm_match([(3, 1)] * 15))["home"]
    assert rec["passes_total"] >= 20, rec
    assert rec["top"] is not None, rec
    assert {rec["top"]["from"], rec["top"]["to"]} == {"irányító", "beálló"}
    assert rec["verdict"] and "vonalon megy" in rec["verdict"], rec


def test_role_pass_map_silent_with_few_passes():
    """Néhány passzból nincs ítélet — nem találgatunk."""
    from handball.pipeline.roles import role_pass_map

    rec = role_pass_map(_rpm_match([(3, 1)] * 3))["home"]
    assert rec["passes_total"] < 20, rec
    assert rec["top"] is None and rec["verdict"] is None, rec


# ---- Poszt-átvételi zóna -----------------------------------------------------

def test_role_receive_zones_separates_near_and_far_receivers():
    """A beálló 6 m-en, az irányító 12 m-en veszi át a labdát."""
    from handball.pipeline.roles import (RRZ_MIN_RECEPTIONS,
                                         role_receive_zones)

    # _ARP: irányító (28,10) = 12 m, beálló (34,10) = 6 m a kaputól.
    rec = role_receive_zones(_rpm_match([(3, 1)] * 12))["home"]
    assert rec["receptions"] >= 2 * RRZ_MIN_RECEPTIONS, rec
    assert rec["roles"]["beálló"]["avg_m"] < \
        rec["roles"]["irányító"]["avg_m"], rec
    assert rec["closest"] is not None and rec["closest"]["poszt"] == "beálló"
    assert rec["farthest"] is not None
    assert rec["farthest"]["poszt"] == "irányító", rec
    assert rec["closest"]["gap_m"] < 0 < rec["farthest"]["gap_m"]
    assert rec["verdict"] and "beálló" in rec["verdict"], rec


def test_role_receive_zones_silent_with_few_receptions():
    """Néhány átvételből nincs ítélet."""
    from handball.pipeline.roles import role_receive_zones

    rec = role_receive_zones(_rpm_match([(3, 1)] * 2))["home"]
    assert rec["closest"] is None and rec["farthest"] is None, rec
    assert rec["verdict"] is None, rec


# ---- Poszt-labdatartás -------------------------------------------------------

def _rht_match(cycles=10, long_frames=50, short_frames=10, warmup=150):
    """Az irányító hosszan, a beálló röviden tartja a labdát."""
    frames = []
    t = 0

    def _add(bx, by):
        nonlocal t
        frames.append(Frame(t=t, players=_arp_players(),
                            ball=Ball(x=bx, y=by, confidence=1.0)))
        t += 1

    for _ in range(warmup):
        _add(28.0, 10.0)
    for _ in range(cycles):
        for _ in range(long_frames):     # irányító: hosszú tartás
            _add(28.0, 10.0)
        for i in range(1, 6):            # gyors átadás (érintésnyi zaj)
            _add(28.0 + 6.0 * (i / 5.0), 10.0)
        for _ in range(short_frames):    # beálló: rövid tartás
            _add(34.0, 10.0)
        for i in range(1, 6):
            _add(34.0 - 6.0 * (i / 5.0), 10.0)
    return Match(MatchMeta(match_id="ht", home_team="H", away_team="A",
                           fps=25.0), frames)


def test_role_hold_time_names_the_slowest_post():
    """Az irányítójuknál áll meg a labda — ő a kettőzés célpontja."""
    from handball.pipeline.roles import RHT_MIN_HOLDS, role_hold_time

    rec = role_hold_time(_rht_match())["home"]
    assert rec["holds"] >= 2 * RHT_MIN_HOLDS, rec
    assert rec["roles"]["irányító"]["avg_s"] > \
        rec["roles"]["beálló"]["avg_s"], rec
    assert rec["slowest"] is not None, rec
    assert rec["slowest"]["poszt"] == "irányító", rec
    assert rec["slowest"]["gap_s"] >= 0.7, rec
    assert rec["verdict"] and "irányító" in rec["verdict"], rec


def test_role_hold_time_silent_with_few_holds():
    """Kevés labdás szakaszból nincs ítélet."""
    from handball.pipeline.roles import role_hold_time

    rec = role_hold_time(_rht_match(cycles=3))["home"]
    assert rec["slowest"] is None and rec["verdict"] is None, rec


# ---- Poszt-eladási zóna ------------------------------------------------------

# A hazai (+x kapura támadó) felállás. A pálya-harmadok a HOSSZ (x)
# mentén oszlanak, ezért x-ben mérünk: a beálló a támadó harmadban áll
# (6 m a kaputól), a szélső azon kívül (14 m).
_RTZ = {1: (34.0, 10.0), 2: (26.0, 3.0)}


def _rtz_players():
    players = [_pl(tid, Team.HOME, x, y) for tid, (x, y) in _RTZ.items()]
    players.append(_pl(20, Team.AWAY, 10.0, 10.0))
    return players


def _rtz_match(losers, warmup=200):
    """`losers` = a labdát elvesztő hazai játékosok sorrendben."""
    frames = []
    t = 0

    def _add(bx, by):
        nonlocal t
        frames.append(Frame(t=t, players=_rtz_players(),
                            ball=Ball(x=bx, y=by, confidence=1.0)))
        t += 1

    for _ in range(warmup):      # poszt-minta: a beálló birtokol
        _add(34.0, 10.0)
    for tid in losers:
        lx, ly = _RTZ[tid]
        cur = (frames[-1].ball.x, frames[-1].ball.y)
        for i in range(1, 21):   # a labda a vesztes játékoshoz
            f_ = i / 20.0
            _add(cur[0] + (lx - cur[0]) * f_, cur[1] + (ly - cur[1]) * f_)
        for _ in range(10):      # birtokolja
            _add(lx, ly)
        for i in range(1, 21):   # a vendéghez kerül: ELADÁS
            f_ = i / 20.0
            _add(lx + (10.0 - lx) * f_, ly + (10.0 - ly) * f_)
        for _ in range(25):
            _add(10.0, 10.0)
    return Match(MatchMeta(match_id="tz", home_team="H", away_team="A",
                           fps=25.0), frames)


def test_role_turnover_zones_finds_the_risky_post():
    """A beálló a támadó harmadban ad el — az ő eladása hív kontrát."""
    from handball.pipeline.roles import RTZ_MIN_TO, role_turnover_zones

    rec = role_turnover_zones(_rtz_match([1] * 6 + [2] * 6))["home"]
    assert rec["turnovers"] >= 2 * RTZ_MIN_TO, rec
    assert rec["roles"]["beálló"]["front_pct"] > \
        rec["roles"]["szélső"]["front_pct"], rec
    assert rec["riskiest"] is not None, rec
    assert rec["riskiest"]["poszt"] == "beálló", rec
    assert rec["riskiest"]["gap_pp"] >= 20.0, rec
    assert rec["verdict"] and "beálló" in rec["verdict"], rec


def test_role_turnover_zones_silent_with_few_turnovers():
    """Két eladásból nincs ítélet."""
    from handball.pipeline.roles import role_turnover_zones

    rec = role_turnover_zones(_rtz_match([1, 2]))["home"]
    assert rec["riskiest"] is None and rec["verdict"] is None, rec


# ---- Poszt-lövéstávolság (melyik posztjuk milyen messziről lő) --------------

# A beálló a 6 m-en, az irányító 12 m-en áll; a szélső a sávban.
_RSD = {1: (34.0, 10.0), 2: (28.0, 10.0)}


def _rsd_players():
    players = [_pl(tid, Team.HOME, x, y) for tid, (x, y) in _RSD.items()]
    players.append(_pl(20, Team.AWAY, 10.0, 10.0))
    return players


def _rsd_match(shooters, warmup=200):
    """`shooters` = a lövést leadó hazai játékosok sorrendben.

    Minden lövésnél a labda előbb a lövő KEZÉBEN van (ez az elengedés
    pillanata), majd lövés-tempóban a +x kapuba repül.
    """
    frames = []
    t = 0

    def _add(bx, by):
        nonlocal t
        frames.append(Frame(t=t, players=_rsd_players(),
                            ball=Ball(x=bx, y=by, confidence=1.0)))
        t += 1

    for _ in range(warmup):      # poszt-minta: a beálló birtokol
        _add(34.0, 10.0)
    for tid in shooters:
        sx, sy = _RSD[tid]
        for _ in range(6):       # a lövő kezében a labda
            _add(sx + 0.2, sy)
        x = sx + 0.2
        while x < 40.5:          # lövés: ~25 m/s a kapuba
            x += 1.0
            _add(min(x, 40.5), 10.0)
        for _ in range(30):      # a labda visszakerül középre
            _add(20.0, 10.0)
    return Match(MatchMeta(match_id="sd", home_team="H", away_team="A",
                           fps=25.0), frames)


def test_role_shot_distance_separates_the_posts():
    """A beálló 6 m-ről, az irányító 12 m-ről fejez be — a posztok
    közti különbség adja a "meddig lépj ki" döntést."""
    from handball.pipeline.roles import RSD_MIN_SHOTS, role_shot_distance

    rec = role_shot_distance(_rsd_match([1] * 5 + [2] * 5))["home"]
    assert rec["shots"] >= 2 * RSD_MIN_SHOTS, rec
    posts = rec["roles"]
    assert len(posts) == 2, rec
    # A két poszt átlagtávolsága érdemben eltér.
    avgs = sorted(r["avg_m"] for r in posts.values())
    assert avgs[1] - avgs[0] >= 4.0, rec
    assert rec["closest"] is not None and rec["farthest"] is not None, rec
    assert rec["closest"]["avg_m"] < rec["farthest"]["avg_m"], rec
    # A közeli befejezőt kell kizárni — ez az elsődleges ítélet.
    assert rec["verdict"] and "ki kell zárni" in rec["verdict"], rec


def test_role_shot_distance_silent_with_few_shots():
    """Két lövésből nincs ítélet (sose hallgatólagos átlag)."""
    from handball.pipeline.roles import role_shot_distance

    rec = role_shot_distance(_rsd_match([1, 2]))["home"]
    assert rec["closest"] is None and rec["farthest"] is None, rec
    assert rec["verdict"] is None, rec


# ---- Poszt-lövésidőzítés (melyik posztjuk mikor fejez be) -------------------

def _rst_match(plan, warmup=200):
    """`plan` = (lövő-azonosító, a támadás hányadik másodpercében lő) párok.

    Minden támadás a saját térfélről indul (hogy a szakasz kezdete
    egyértelmű legyen), majd a megadott idő után jön az elengedés és a
    lövés a +x kapuba.
    """
    frames = []
    t = 0

    def _add(bx, by, players):
        nonlocal t
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=bx, y=by, confidence=1.0)))
        t += 1

    def _cast():
        return [_pl(tid, Team.HOME, x, y) for tid, (x, y) in _RSD.items()] + \
            [_pl(20, Team.AWAY, 5.0, 10.0)]

    for _ in range(warmup):      # poszt-minta: a beálló birtokol
        _add(34.0, 10.0, _cast())
    for (tid, delay_s) in plan:
        sx, sy = _RSD[tid]
        # A támadás indulása: a labda a lövőnél áll `delay_s` ideig.
        for _ in range(max(1, int(delay_s * 25.0))):
            _add(sx + 0.2, sy, _cast())
        x = sx + 0.2
        while x < 40.5:          # lövés a kapuba
            x += 1.0
            _add(min(x, 40.5), 10.0, _cast())
        for _ in range(40):      # visszaáll: a labda a saját térfélen
            _add(5.0, 10.0, _cast())
    return Match(MatchMeta(match_id="st", home_team="H", away_team="A",
                           fps=25.0), frames)


def test_role_shot_timing_separates_early_and_late_posts():
    """A beálló másfél másodperc után fejez be, az irányító tizenöt
    után — a fal nem tud egyszerre mindkettőre készülni."""
    from handball.pipeline.roles import RST_MIN_SHOTS, role_shot_timing

    rec = role_shot_timing(
        _rst_match([(1, 1.5)] * 5 + [(2, 15.0)] * 5))["home"]
    assert rec["shots"] >= 2 * RST_MIN_SHOTS, rec
    avgs = sorted(r["avg_s"] for r in rec["roles"].values())
    assert avgs[1] - avgs[0] >= 8.0, rec
    assert rec["earliest"] is not None and rec["latest"] is not None, rec
    assert rec["earliest"]["avg_s"] < rec["latest"]["avg_s"], rec
    # A korai befejezőre a visszarendeződésnél kell ember — ez az
    # elsődleges ítélet.
    assert rec["verdict"] and "visszarendeződés" in rec["verdict"], rec


def test_role_shot_timing_silent_with_few_shots():
    """Két lövésből nincs ítélet."""
    from handball.pipeline.roles import role_shot_timing

    rec = role_shot_timing(_rst_match([(1, 1.5), (2, 15.0)]))["home"]
    assert rec["earliest"] is None and rec["latest"] is None, rec
    assert rec["verdict"] is None, rec


# ---- Poszt-lövéserő (melyik posztjuk lő keményen) ---------------------------

def _rsp_match(plan, warmup=200):
    """`plan` = (lövő-azonosító, a labda méter/kocka tempója) párok.

    25 fps mellett 1 m/kocka = 90 km/h, tehát a tempó közvetlenül
    állítja a mért lövéserőt.
    """
    frames = []
    t = 0

    def _cast():
        return [_pl(tid, Team.HOME, x, y) for tid, (x, y) in _RSD.items()] + \
            [_pl(20, Team.AWAY, 5.0, 10.0)]

    def _add(bx, by):
        nonlocal t
        frames.append(Frame(t=t, players=_cast(),
                            ball=Ball(x=bx, y=by, confidence=1.0)))
        t += 1

    for _ in range(warmup):      # poszt-minta: a beálló birtokol
        _add(34.0, 10.0)
    for (tid, step) in plan:
        sx, sy = _RSD[tid]
        for _ in range(6):       # a lövő kezében a labda
            _add(sx + 0.2, sy)
        x = sx + 0.2
        while x < 40.5:
            x += step
            _add(min(x, 40.5), 10.0)
        for _ in range(40):
            _add(5.0, 10.0)
    return Match(MatchMeta(match_id="sp", home_team="H", away_team="A",
                           fps=25.0), frames)


def test_role_shot_power_finds_the_hard_hitting_post():
    """Az irányítójuk ~135 km/h-val lő, a beálló ~63-mal — a kapust
    poszt szerint kell felkészíteni."""
    from handball.pipeline.roles import RSP_MIN_SHOTS, role_shot_power

    rec = role_shot_power(
        _rsp_match([(2, 1.5)] * 5 + [(1, 0.7)] * 5))["home"]
    assert rec["shots"] >= 2 * RSP_MIN_SHOTS, rec
    assert rec["hardest"] is not None, rec
    assert rec["hardest"]["gap_kmh"] >= 12.0, rec
    # A keményen lövő poszt átlaga a másiké fölött van.
    avgs = sorted(r["avg_kmh"] for r in rec["roles"].values())
    assert avgs[1] - avgs[0] >= 30.0, rec
    assert rec["verdict"] and "kapus" in rec["verdict"], rec


def test_role_shot_power_silent_with_few_shots():
    """Két lövésből nincs ítélet."""
    from handball.pipeline.roles import role_shot_power

    rec = role_shot_power(_rsp_match([(2, 1.5), (1, 0.7)]))["home"]
    assert rec["hardest"] is None and rec["verdict"] is None, rec
