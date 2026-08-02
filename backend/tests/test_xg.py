"""
Tesztek a helyzetminőség (xG) számításra (xg.py).

A pálya 40x20 m; a HAZAI a +x (x=40) kapu felé támad.

Futtatás:
    python -m pytest tests/test_xg.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.xg import match_xg, xg_of_position


def _meta(fps=25.0):
    return MatchMeta(match_id="xg", home_team="H", away_team="A", fps=fps)


def _pl(track_id, team, x, y):
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0)


def test_close_central_beats_far_and_wing():
    """A hatosról, szemből leadott lövés többet ér, mint a távoli vagy a
    szélső szögből jövő — és minden érték a [0,05, 0,9] sávban marad."""
    close_central = xg_of_position(34.0, 10.0, 40.0)   # ~6 m, szemből
    far_central = xg_of_position(28.0, 10.0, 40.0)     # ~12 m, szemből
    wing = xg_of_position(34.0, 2.0, 40.0)             # éles szélső szög
    assert close_central > far_central
    assert close_central > wing
    for v in (close_central, far_central, wing):
        assert 0.05 <= v <= 0.9


def test_symmetry_between_goals():
    """Ugyanaz a helyzet a két kapunál tükrözve ugyanannyit ér."""
    assert xg_of_position(34.0, 7.0, 40.0) == xg_of_position(6.0, 7.0, 0.0)


def _shot_frames(t0, shooter_x, shooter_y, goal=True):
    """Egy hazai lövés kockái: a lövő a megadott helyen, a labda a +x kapura."""
    frames = []
    for i in range(8):
        bx = min(34.0 + i, 40.0)
        by = shooter_y + (10.0 - shooter_y) * min(1.0, i / 6.0) if goal else 5.0
        frames.append(Frame(
            t=t0 + i,
            players=[_pl(1, Team.HOME, shooter_x, shooter_y)],
            ball=Ball(x=bx, y=by if goal else 5.0, confidence=1.0)))
    return frames


def test_match_xg_totals_and_shooter_position():
    """A csapat-összeg a lövések xG-inek összege, a hely a LÖVŐ pozíciója."""
    frames = _shot_frames(0, 33.0, 10.0, goal=True)
    frames.append(Frame(t=8, players=[], ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    frames += _shot_frames(40, 28.0, 3.0, goal=False)
    m = Match(_meta(), frames)
    r = match_xg(m)
    assert len(r["shots"]) == 2
    th = r["teams"]["home"]
    assert th["shots"] == 2 and th["goals"] == 1
    assert abs(th["xg"] - sum(s["xg"] for s in r["shots"])) < 0.02
    # A közeli-középső helyzet értékesebb, mint a távoli-szélső.
    assert r["shots"][0]["xg"] > r["shots"][1]["xg"]
    # A hely a lövő pozíciója (nem a labdáé a kapu előtt).
    assert r["shots"][0]["x"] == 33.0
    # diff = gól − xG.
    assert abs(th["diff"] - (1 - th["xg"])) < 0.02


def test_empty_match_gives_zero():
    m = Match(_meta(), [Frame(t=t, players=[], ball=None) for t in range(10)])
    r = match_xg(m)
    assert r["shots"] == []
    assert r["teams"]["home"]["xg"] == 0.0


def test_shooter_breakdown():
    """Lövőnkénti bontás: két lövés ugyanattól a játékostól összegződik,
    a diff a gól − xG; az azonosítatlan lövő nem szerepel a listában."""
    frames = _shot_frames(0, 33.0, 10.0, goal=True)     # 1-es: gól közelről
    frames.append(Frame(t=8, players=[], ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    frames += _shot_frames(40, 28.0, 3.0, goal=False)   # 1-es: kihagyva
    m = Match(_meta(), frames)
    r = match_xg(m)
    assert len(r["shooters"]) == 1
    rec = r["shooters"][0]
    assert rec["player_id"] == 1 and rec["team"] == "home"
    assert rec["shots"] == 2 and rec["goals"] == 1
    assert abs(rec["xg"] - r["teams"]["home"]["xg"]) < 0.02
    assert abs(rec["diff"] - (1 - rec["xg"])) < 0.02


def test_shooterless_shot_not_in_breakdown():
    """Lövő nélküli (labda-alapú) lövés: a csapat-összegben igen, a
    lövő-listában nem."""
    frames = [Frame(t=i, players=[], ball=Ball(x=34.0 + i, y=10.0, confidence=1.0))
              for i in range(7)]
    r = match_xg(Match(_meta(), frames))
    assert r["teams"]["home"]["shots"] == 1
    assert r["shooters"] == []


def test_avg_xg_per_shot_reported():
    """A csapat-összegzés tartalmazza az átlagos xG/lövést, és az a
    lövések számából jön ki."""
    frames = _shot_frames(0, 33.0, 10.0, goal=True)
    frames.append(Frame(t=8, players=[], ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    frames += _shot_frames(40, 28.0, 3.0, goal=False)
    r = match_xg(Match(_meta(), frames))["teams"]["home"]
    assert r["shots"] == 2
    assert abs(r["avg_xg_per_shot"] - r["xg"] / 2) < 0.02


def test_missed_big_chances_filters_by_xg_and_outcome():
    """A közeli-középső kihagyott helyzet ziccer; a gól és a távoli
    kihagyás nem kerül a listába."""
    from handball.pipeline.xg import missed_big_chances

    # Nagy xG-s kihagyás: a labda a lövőtől (37, 10) indul — így a lövő
    # azonosítható —, majd a kapufák mellé hajlik el.
    frames = []
    for i in range(7):
        frames.append(Frame(
            t=i,
            players=[_pl(1, Team.HOME, 37.0, 10.0)],
            ball=Ball(x=min(37.4 + 0.6 * i, 40.0), y=10.0 - i * 1.0,
                      confidence=1.0)))
    frames.append(Frame(t=8, players=[], ball=Ball(x=20.0, y=10.0,
                                                   confidence=1.0)))
    frames += _shot_frames(40, 37.0, 10.0, goal=True)    # nagy xG, de GÓL
    frames.append(Frame(t=48, players=[], ball=Ball(x=20.0, y=10.0,
                                                    confidence=1.0)))
    frames += _shot_frames(80, 27.0, 3.0, goal=False)    # kis xG, kihagyva
    m = Match(_meta(), frames)

    chances = missed_big_chances(m)
    assert len(chances) == 1
    assert chances[0]["t"] < 10          # az első (kihagyott) helyzet
    assert chances[0]["xg"] >= 0.5
    assert chances[0]["team"] == "home"


def test_big_saves_requires_save_outcome():
    """A kapus által fogott ziccer bekerül; a mellé menő nagy helyzet nem
    (az kihagyott ziccer, nem védés)."""
    from handball.pipeline.xg import big_saves

    # Fogott ziccer: közeli-középső lövés, a kapusnál megáll a labda.
    frames = []
    gk = _pl(30, Team.AWAY, 39.0, 10.0)
    gk.role = "kapus"
    for i in range(8):
        frames.append(Frame(
            t=i,
            players=[_pl(1, Team.HOME, 37.0, 10.0), gk],
            ball=Ball(x=min(37.4 + 0.6 * i, 38.8), y=10.0,
                      confidence=1.0)))
    m = Match(_meta(), frames)
    saves = big_saves(m)
    assert len(saves) == 1
    assert saves[0]["xg"] >= 0.5
    assert saves[0]["team"] == "home"     # a LÖVŐ csapata
    # Ugyanez kapus nélkül (mellé): nem bravúr-védés.
    frames2 = []
    for i in range(7):
        frames2.append(Frame(
            t=i,
            players=[_pl(1, Team.HOME, 37.0, 10.0)],
            ball=Ball(x=min(37.4 + 0.6 * i, 40.0), y=10.0 - i * 1.0,
                      confidence=1.0)))
    assert big_saves(Match(_meta(), frames2)) == []


def test_xg_saved_credits_defending_side():
    """A fogott ziccer helyzet-értéke a VÉDŐ oldal hárított xG-jébe
    számít; gólnál semmi nem íródik jóvá."""
    from handball.pipeline.xg import xg_saved

    # Fogott ziccer: közeli-középső lövés, a kapusnál megáll a labda.
    frames = []
    gk = _pl(30, Team.AWAY, 39.0, 10.0)
    gk.role = "kapus"
    for i in range(8):
        frames.append(Frame(
            t=i,
            players=[_pl(1, Team.HOME, 37.0, 10.0), gk],
            ball=Ball(x=min(37.4 + 0.6 * i, 38.8), y=10.0,
                      confidence=1.0)))
    xs = xg_saved(Match(_meta(), frames))
    assert xs["away"] >= 0.5     # a nagy helyzet értéke a védőé
    assert xs["home"] == 0.0

    # Gólnál nincs hárított xG.
    frames2 = _shot_frames(0, 37.0, 10.0, goal=True)
    xs2 = xg_saved(Match(_meta(), frames2))
    assert xs2["home"] == 0.0 and xs2["away"] == 0.0


def test_xg_prevented_balances_faced_and_conceded():
    """A megmentett gól = kapura tartó xG − kapott gól; a mellé menő
    lövés nem számít bele."""
    from handball.pipeline.xg import xg_prevented

    # Egy gól a vendég kapuba (a hazai lövő nagy helyzetből).
    frames = _shot_frames(0, 37.0, 10.0, goal=True)
    rec = xg_prevented(Match(_meta(), frames))["away"]
    assert rec["conceded"] == 1
    assert rec["faced_xg"] >= 0.5
    # prevented = faced − 1: nagy helyzetnél kis negatív szám.
    assert abs(rec["prevented"] - (rec["faced_xg"] - 1)) < 1e-6
    # A hazai oldalon nem történt semmi.
    assert xg_prevented(Match(_meta(), frames))["home"]["faced_xg"] == 0.0


def test_miss_punishment_counts_quick_goals_after_miss():
    """3 hazai ziccer-kihagyásból az elsőt fél percen belüli vendég-gól
    bünteti → 33%; kevés kihagyásnál nincs ítélet."""
    from handball.pipeline.xg import miss_punishment

    def _miss(t0):
        fr = []
        for i in range(7):
            fr.append(Frame(
                t=t0 + i,
                players=[_pl(1, Team.HOME, 37.0, 10.0)],
                ball=Ball(x=min(37.4 + 0.6 * i, 40.0), y=10.0 - i * 1.0,
                          confidence=1.0)))
        fr.append(Frame(t=t0 + 8, players=[],
                        ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        return fr

    frames = _miss(0)
    for i in range(8):  # vendég-gól a -x kapuba, ~8 mp-re a kihagyástól
        frames.append(Frame(t=200 + i, players=[],
                            ball=Ball(x=max(6.4 - i, 0.0), y=10.0,
                                      confidence=1.0)))
    frames.append(Frame(t=210, players=[],
                        ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    frames += _miss(3000)
    frames += _miss(6000)
    mp = miss_punishment(Match(_meta(), frames))
    h = mp["home"]
    assert h["misses"] == 3 and h["punished"] == 1
    assert abs(h["rate_pct"] - 33.3) < 0.1
    assert mp["away"]["misses"] == 0 and mp["away"]["rate_pct"] is None


def test_big_save_momentum_counts_quick_goals_after_save():
    """3 vendég-bravúrból az elsőt fél percen belüli vendég-gól követi
    → 33%; kevés bravúrnál nincs ítélet."""
    from handball.pipeline.xg import big_save_momentum

    def _saved(t0):
        fr = []
        gk = _pl(30, Team.AWAY, 39.0, 10.0)
        gk.role = "kapus"
        for i in range(8):
            fr.append(Frame(
                t=t0 + i,
                players=[_pl(1, Team.HOME, 37.0, 10.0), gk],
                ball=Ball(x=min(37.4 + 0.6 * i, 38.8), y=10.0,
                          confidence=1.0)))
        fr.append(Frame(t=t0 + 9, players=[],
                        ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        return fr

    frames = _saved(0)
    for i in range(8):  # vendég-gól a -x kapuba, ~8 mp-re a bravúrtól
        frames.append(Frame(t=200 + i, players=[],
                            ball=Ball(x=max(6.4 - i, 0.0), y=10.0,
                                      confidence=1.0)))
    frames.append(Frame(t=210, players=[],
                        ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    frames += _saved(3000)
    frames += _saved(6000)
    bsm = big_save_momentum(Match(_meta(), frames))
    a = bsm["away"]
    assert a["saves"] == 3 and a["sparked"] == 1
    assert abs(a["rate_pct"] - 33.3) < 0.1
    assert bsm["home"]["saves"] == 0 and bsm["home"]["rate_pct"] is None


def test_finish_fade_drop_needs_halftime():
    """Az 1. félidőben 6 kísérletből 3 gól, a 2.-ban 6-ból 0 → 50 pp
    esés; félidő-jel nélkül nincs ítélet."""
    from handball.pipeline.xg import finish_fade

    def _active(t0, seconds):
        players = [_pl(100 + k, Team.HOME if k < 4 else Team.AWAY,
                       8.0 + 3.0 * k, 4.0 + (k % 4)) for k in range(8)]
        return [Frame(t=t0 + i, players=players,
                      ball=Ball(x=20.0, y=10.0, confidence=1.0))
                for i in range(int(seconds * 25))]

    def _try(t0, goal):
        fr = []
        for i in range(8):
            x = min((33.6 if goal else 37.4) + (1.0 if goal else 0.8) * i,
                    40.0)
            y = 10.0 if goal else 10.0 - i * 1.0
            fr.append(Frame(t=t0 + i,
                            players=[_pl(1, Team.HOME, 33.0, 10.0)],
                            ball=Ball(x=x, y=y, confidence=1.0)))
        fr.append(Frame(t=t0 + 9, players=[],
                        ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        return fr

    def _half(t0, tries):
        frames = _active(t0, 30)
        t = frames[-1].t + 1
        for goal in tries:
            frames += _try(t, goal)
            t += 10
            frames += _active(t, 30)
            t = frames[-1].t + 1
        return frames

    frames = _half(0, [True, False, True, False, True, False])
    t = frames[-1].t + 1
    frames += [Frame(t=t + i, players=[], ball=None)
               for i in range(int(120 * 25))]
    frames += _half(frames[-1].t + 1, [False] * 6)
    ff = finish_fade(Match(_meta(), frames))
    h = ff["home"]
    assert h["fh_shots"] == 6 and h["fh_goals"] == 3
    assert h["sh_shots"] == 6 and h["sh_goals"] == 0
    assert h["drop_pp"] == 50.0

    # Félidő-jel nélkül nincs ítélet.
    no_ht = finish_fade(Match(_meta(), _half(0, [True, False])))
    assert no_ht["home"]["drop_pp"] is None


def test_shot_accuracy_counts_on_target_share():
    """8 hazai kísérletből 5 kaput ér (3 gól + 2 fogott) → 62,5%; kevés
    kísérletnél nincs ítélet."""
    from handball.pipeline.xg import shot_accuracy

    def _attempt(t0, kind):
        fr = []
        gk = _pl(30, Team.AWAY, 39.0, 10.0)
        gk.role = "kapus"
        for i in range(8):
            if kind == "goal":
                ball = Ball(x=min(33.6 + i, 40.0), y=10.0, confidence=1.0)
                players = [_pl(1, Team.HOME, 33.0, 10.0)]
            elif kind == "save":
                ball = Ball(x=min(37.4 + 0.6 * i, 38.8), y=10.0,
                            confidence=1.0)
                players = [_pl(1, Team.HOME, 37.0, 10.0), gk]
            else:  # mellé
                ball = Ball(x=min(37.4 + 0.8 * i, 40.0), y=10.0 - i * 1.0,
                            confidence=1.0)
                players = [_pl(1, Team.HOME, 37.0, 10.0)]
            fr.append(Frame(t=t0 + i, players=players, ball=ball))
        fr.append(Frame(t=t0 + 9, players=[],
                        ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        return fr

    frames = []
    t = 0
    for kind in ("goal", "goal", "goal", "save", "save",
                 "miss", "miss", "miss"):
        frames += _attempt(t, kind)
        t += 40
    sa = shot_accuracy(Match(_meta(), frames))
    h = sa["home"]
    assert h["attempts"] == 8 and h["on_target"] == 5
    assert abs(h["pct"] - 62.5) < 0.1

    # Kevés kísérlet: nincs ítélet.
    few = shot_accuracy(Match(_meta(), _attempt(0, "goal")))
    assert few["home"]["attempts"] == 1
    assert few["home"]["pct"] is None


def test_shot_concentration_flags_one_man_offense():
    """9 lövés a fő lövőtől + 3 a társtól → 75% részarány, egy emberre
    épülő terhelés; kevés lövésnél nincs ítélet."""
    from handball.pipeline.xg import shot_concentration

    def _shot_by(t0, pid):
        frames = []
        for i in range(8):
            frames.append(Frame(
                t=t0 + i,
                players=[_pl(pid, Team.HOME, 33.0, 10.0)],
                ball=Ball(x=min(34.0 + i, 40.0), y=10.0, confidence=1.0)))
        frames.append(Frame(t=t0 + 9, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        return frames

    frames = []
    t = 0
    for pid in (1, 1, 1, 2, 1, 1, 1, 2, 1, 1, 2, 1):
        frames += _shot_by(t, pid)
        t += 40
    sc = shot_concentration(Match(_meta(), frames))
    h = sc["home"]
    assert h["shots"] == 12 and h["top_shots"] == 9
    assert h["top_player_id"] == 1
    assert h["share"] is not None and abs(h["share"] - 0.75) < 0.01
    assert h["concentrated"] is True

    # Kevés lövés: nincs ítélet.
    few = shot_concentration(Match(_meta(), _shot_by(0, 1)))
    assert few["home"]["shots"] == 1
    assert few["home"]["share"] is None
    assert few["home"]["concentrated"] is None


def test_shot_release_separates_catch_and_shoot_from_holders():
    """A hazai lövők 0,2 mp után elengedik a labdát (kapásból), a
    vendégek 2 mp-ig fogják (labdafogó); kevés lövésnél nincs ítélet."""
    from handball.pipeline.xg import shot_release

    frames = []
    t = 0

    def _shot_cycle(home_side, hold_frames):
        # A lövő a zónán KÍVÜL (12+ m) kapja és fogja a labdát — a
        # bejátszás hátrafelé ível (sosem lövés-irány), a lövés-zónába
        # maga a lövés repülése lép be.
        nonlocal t, frames
        if home_side:
            shooter = _pl(1, Team.HOME, 26.0, 10.0)
            rest, hold_xy = (30.0, 3.0), (26.0, 10.0)
        else:
            shooter = _pl(11, Team.AWAY, 14.0, 10.0)
            rest, hold_xy = (10.0, 17.0), (14.0, 10.0)
        players = [shooter]
        for i in range(6):  # érkező (hátrafelé tartó) bejátszás
            fx = rest[0] + (hold_xy[0] - rest[0]) * i / 5.0
            fy = rest[1] + (hold_xy[1] - rest[1]) * i / 5.0
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=fx, y=fy, confidence=1.0)))
            t += 1
        for _ in range(hold_frames):
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=hold_xy[0], y=hold_xy[1],
                                          confidence=1.0)))
            t += 1
        for i in range(18):  # lövés: 0,8 m/kocka repülés a kapuig
            bx = (min(26.8 + 0.8 * i, 40.0) if home_side
                  else max(13.2 - 0.8 * i, 0.0))
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=bx, y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(60):  # szünet: a labda hátul pihen, senkinél
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=rest[0], y=rest[1],
                                          confidence=1.0)))
            t += 1

    for _ in range(8):
        _shot_cycle(True, 5)    # hazai: 0,2 mp fogás
    for _ in range(8):
        _shot_cycle(False, 50)  # vendég: 2 mp fogás

    sr = shot_release(Match(_meta(), frames))
    h, a = sr["home"], sr["away"]
    assert h["shots"] >= 8 and h["style"] == "kapásból"
    assert a["shots"] >= 8 and a["style"] == "labdafogó"
    assert a["avg_hold_s"] > h["avg_hold_s"]

    # Kevés lövés: nincs ítélet.
    few = shot_release(Match(_meta(), frames[:150]))
    assert few["home"]["style"] is None


# ---- Pontatlan lövők (kinek a lövései mennek mellé) -------------------------

def _wasteful_match(cases, fps=25.0):
    """Lövés-sorozat: a `cases` elemei (lövő id, mellé?) párok — a
    mellé lövés a kapufák mellett (y=5) hagyja el a pályát."""
    frames = []
    t = 0
    for (pid, off) in cases:
        for i in range(3):
            frames.append(Frame(
                t=t + i, players=[_pl(pid, Team.HOME, 33.0, 10.0)],
                ball=Ball(x=33.0, y=10.0, confidence=1.0)))
        t += 3
        for i in range(9):
            frames.append(Frame(
                t=t, players=[_pl(pid, Team.HOME, 33.0, 10.0)],
                ball=Ball(x=min(34.0 + i, 40.4),
                          y=5.0 if off else 10.0, confidence=1.0)))
            t += 1
        for i in range(25):    # szünet a lövés-debounce-hoz
            frames.append(Frame(t=t + i, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
        t += 25
    return Match(_meta(fps), frames)


def test_wasteful_shooters_finds_the_off_target_shooter():
    """A 8-as hat lövéséből négy elkerüli a kaput → rá lehet engedni a
    lövést."""
    from handball.pipeline.xg import wasteful_shooters

    cases = [(8, True)] * 4 + [(8, False)] * 2 + [(3, False)] * 5
    rec = wasteful_shooters(_wasteful_match(cases))["home"]
    assert rec["top"] is not None
    assert rec["top"]["player_id"] == 8
    assert rec["top"]["shots"] == 6 and rec["top"]["off_target"] == 4


def test_wasteful_shooters_needs_enough_shots():
    """Kevés (5-nél kevesebb) lövésnél nincs kiemelt lövő."""
    from handball.pipeline.xg import wasteful_shooters

    rec = wasteful_shooters(_wasteful_match(
        [(8, True), (8, True), (3, False)]))["home"]
    assert rec["top"] is None


# ---- Kapott helyzetek minősége (milyen lövéseket enged a fal) --------------

def _ccq_match(positions, fps=25.0):
    """Hazai lövés-sorozat a megadott (x, y) helyekről — a VENDÉG fal
    engedte őket; a labda a LÖVŐ helyéről indul, hogy a lövő
    azonosítható legyen."""
    frames = []
    t = 0
    for (x, y) in positions:
        for i in range(8):
            bx = x + (40.0 - x) * min(1.0, i / 5.0)
            by = y + (10.0 - y) * min(1.0, i / 5.0)
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, x, y)],
                                ball=Ball(x=bx, y=by, confidence=1.0)))
            t += 1
        for _ in range(30):     # szünet: a labda középen áll
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_conceded_chance_quality_flags_the_open_wall():
    """Nyolc közeli, szemből leadott lövés → a vendég fal nagy
    helyzeteket enged."""
    from handball.pipeline.xg import conceded_chance_quality

    rec = conceded_chance_quality(_ccq_match([(35.0, 10.0)] * 8))["away"]
    assert rec["shots"] == 8 and rec["avg_xga"] > 0.35
    assert rec["verdict"] == "nagy helyzeteket engednek"


def test_conceded_chance_quality_flags_the_tight_wall():
    """Nyolc távoli, éles szögű lövés → csak nehéz helyzeteket
    engednek."""
    from handball.pipeline.xg import conceded_chance_quality

    rec = conceded_chance_quality(_ccq_match([(27.0, 3.0)] * 8))["away"]
    assert rec["verdict"] == "csak nehéz helyzeteket engednek"


def test_conceded_chance_quality_needs_enough_shots():
    """Kevés (8-nál kevesebb) kapott lövésnél nincs ítélet."""
    from handball.pipeline.xg import conceded_chance_quality

    rec = conceded_chance_quality(_ccq_match([(35.0, 10.0)] * 4))["away"]
    assert rec["shots"] == 4 and rec["avg_xga"] is None
    assert rec["verdict"] is None


# ---- Fal-fáradás (melyik félidőben nyílik ki a fal) ------------------------

def _wf_active(t0, seconds, fps=25.0):
    """Aktív játék lövés nélkül: 10 mért játékos a labdától távol."""
    frames = []
    for i in range(int(seconds * fps)):
        players = [_pl(100 + k, Team.HOME, 8.0 + k, 15.0 + 0.5 * k)
                   for k in range(5)]
        players += [_pl(200 + k, Team.AWAY, 30.0 + k, 16.0 + 0.5 * k)
                    for k in range(5)]
        frames.append(Frame(t=t0 + int(i), players=players,
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    return frames


def _wf_shot(t0, x, y, fps=25.0):
    """Hazai lövés (x, y)-ból a +x kapura, aktív háttérrel."""
    frames = []
    for i in range(8):
        bx = x + (40.0 - x) * min(1.0, i / 5.0)
        by = y + (10.0 - y) * min(1.0, i / 5.0)
        players = [_pl(1, Team.HOME, x, y)]
        players += [_pl(100 + k, Team.HOME, 8.0 + k, 15.0 + 0.5 * k)
                    for k in range(5)]
        players += [_pl(200 + k, Team.AWAY, 30.0 + k, 16.0 + 0.5 * k)
                    for k in range(5)]
        frames.append(Frame(t=t0 + i, players=players,
                            ball=Ball(x=bx, y=by, confidence=1.0)))
    return frames


def _wf_match(fh_pos, sh_pos, fps=25.0):
    """1. félidő lövései fh_pos-ból, szünet, 2. félidő lövései
    sh_pos-ból — a VENDÉG fal engedte őket."""
    frames = []
    t = 0

    def _half(positions):
        nonlocal t
        for (x, y) in positions:
            frames.extend(_wf_shot(t, x, y, fps))
            t = frames[-1].t + 1
            frames.extend(_wf_active(t, 2.0, fps))
            t = frames[-1].t + 1

    _half(fh_pos)
    frames.extend(_wf_active(t, 100.0, fps))     # kitöltés a szünetig
    t = frames[-1].t + 1
    for i in range(int(90 * fps)):               # szünet: üres pálya
        frames.append(Frame(t=t, players=[], ball=None))
        t += 1
    _half(sh_pos)
    frames.extend(_wf_active(t, 100.0, fps))
    return Match(_meta(fps), frames)


def test_wall_fade_flags_the_opening_wall():
    """Az 1. félidőben csak távoli-éles, a 2.-ban közeli-szemből jövő
    lövések → a vendég fal a második félidőre nyílik ki."""
    from handball.pipeline.xg import wall_fade

    rec = wall_fade(_wf_match([(27.0, 3.0)] * 6, [(35.0, 10.0)] * 6))["away"]
    assert rec["fh_shots"] == 6 and rec["sh_shots"] == 6
    assert rec["sh_avg_xga"] > rec["fh_avg_xga"]
    assert rec["verdict"] == "a második félidőre kinyílik a faluk"


def test_wall_fade_flags_the_settling_wall():
    """Fordított sorrendben a fal a szünet után áll össze."""
    from handball.pipeline.xg import wall_fade

    rec = wall_fade(_wf_match([(35.0, 10.0)] * 6, [(27.0, 3.0)] * 6))["away"]
    assert rec["verdict"] == "a második félidőre áll össze a faluk"


def test_wall_fade_needs_enough_shots_per_half():
    """Félidőnként 5-nél kevesebb kapott lövésnél nincs ítélet."""
    from handball.pipeline.xg import wall_fade

    rec = wall_fade(_wf_match([(35.0, 10.0)] * 3, [(27.0, 3.0)] * 3))["away"]
    assert rec["fh_shots"] == 3 and rec["fh_avg_xga"] is None
    assert rec["verdict"] is None


# ---- Lövés-választás állás szerint (hátrányban elkapkodják-e) --------------

def _sqs_shot(t0, x, y):
    """Hazai kapufa-mellé lövés (x, y)-ból: a labda a lövőtől indul a
    +x kapu MELLÉ, így az állás nem változik."""
    frames = []
    for i in range(8):
        bx = x + (40.0 - x) * min(1.0, i / 5.0)
        by = y + (4.0 - y) * min(1.0, i / 5.0)
        frames.append(Frame(t=t0 + i, players=[_pl(1, Team.HOME, x, y)],
                            ball=Ball(x=bx, y=by, confidence=1.0)))
    return frames


def _sqs_match(other_pos, trail_pos, fps=25.0):
    """Egál-lövések other_pos-ból, egy kapott gól, majd hátrány-lövések
    trail_pos-ból."""
    frames = []
    t = 0

    def _pause():
        nonlocal t
        for _ in range(30):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    for (x, y) in other_pos:
        frames.extend(_sqs_shot(t, x, y))
        t = frames[-1].t + 1
        _pause()
    for i in range(8):        # vendég gól a 0-s kapuba: hazai hátrány
        frames.append(Frame(t=t, players=[
            _pl(21, Team.AWAY, 7.0, 10.0)],
            ball=Ball(x=max(6.0 - i, 0.0), y=10.0, confidence=1.0)))
        t += 1
    _pause()
    for (x, y) in trail_pos:
        frames.extend(_sqs_shot(t, x, y))
        t = frames[-1].t + 1
        _pause()
    return Match(_meta(fps), frames)


def test_shot_quality_by_score_flags_the_rushing_team():
    """Egálban közeli, hátrányban távoli-éles lövések → hátrányban
    elkapkodják."""
    from handball.pipeline.xg import shot_quality_by_score

    rec = shot_quality_by_score(_sqs_match(
        [(35.0, 10.0)] * 6, [(27.0, 3.0)] * 6))["home"]
    assert rec["other_shots"] == 6 and rec["trail_shots"] == 6
    assert rec["other_avg_xg"] > rec["trail_avg_xg"]
    assert rec["verdict"] == "hátrányban elkapkodják a lövéseket"


def test_shot_quality_by_score_flags_the_patient_team():
    """Fordítva (hátrányban jobb helyzetek) → hátrányban is
    türelmesek."""
    from handball.pipeline.xg import shot_quality_by_score

    rec = shot_quality_by_score(_sqs_match(
        [(27.0, 3.0)] * 6, [(35.0, 10.0)] * 6))["home"]
    assert rec["verdict"] == "hátrányban is türelmesek"


def test_shot_quality_by_score_needs_shots_in_both_states():
    """Állapotonként 5-nél kevesebb lövésnél nincs ítélet."""
    from handball.pipeline.xg import shot_quality_by_score

    rec = shot_quality_by_score(_sqs_match(
        [(35.0, 10.0)] * 6, [(27.0, 3.0)] * 3))["home"]
    assert rec["trail_shots"] == 3 and rec["verdict"] is None


# ---- Ziccer-befejezők (ki értékesíti a nagy helyzeteket) --------------------

def _bcf_match(cases, fps=25.0):
    """Hazai ziccerek a hatosról: a `cases` elemei (lövő, gól-e)
    párok."""
    frames = []
    t = 0
    for (pid, scored) in cases:
        for i in range(8):
            bx = 35.0 + 5.0 * min(1.0, i / 4.0)
            by = 10.0 if scored else 10.0 - 6.0 * min(1.0, i / 4.0)
            frames.append(Frame(t=t, players=[_pl(pid, Team.HOME,
                                                  35.0, 10.0)],
                                ball=Ball(x=bx, y=by, confidence=1.0)))
            t += 1
        for _ in range(30):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_big_chance_finishers_finds_safe_and_shaky():
    """A 7-es 4/4 ziccert belő, a 9-es 1/4-et → biztos és bizonytalan
    befejező."""
    from handball.pipeline.xg import big_chance_finishers

    rec = big_chance_finishers(_bcf_match(
        [(7, True)] * 4 + [(9, True)] + [(9, False)] * 3))["home"]
    assert rec["safe"] is not None and rec["safe"]["player_id"] == 7
    assert rec["shaky"] is not None and rec["shaky"]["player_id"] == 9


def test_big_chance_finishers_needs_enough_chances():
    """Kevés (3-nál kevesebb) ziccernél nincs kiemelt befejező."""
    from handball.pipeline.xg import big_chance_finishers

    rec = big_chance_finishers(_bcf_match(
        [(7, True), (7, True), (9, False)]))["home"]
    assert rec["safe"] is None and rec["shaky"] is None


# ---- Előny-védekezés (leül-e a fal, amikor vezetnek) ------------------------

def _dbs_match(soft=True, n=5, fps=25.0):
    """Vendég-lövések a hazai fal ellen: döntetlennél messziről (vagy
    közelről), majd egy hazai gól utáni vezetésnél közelről (vagy
    messziről) — a hazai fal előny-viselkedése így mérhető."""
    frames = []
    t = 0

    def _pause(sec=1.6):
        nonlocal t
        for _ in range(int(sec * fps)):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    def _away_shot(sx):
        nonlocal t
        for _ in range(10):     # a vendég lövő birtokol
            frames.append(Frame(t=t, players=[_pl(21, Team.AWAY, sx, 10.0)],
                                ball=Ball(x=sx, y=10.0, confidence=1.0)))
            t += 1
        steps = max(3, int(round(sx - 0.8)))
        for i in range(1, steps + 1):   # lövés a -x kapura (nem gól)
            frames.append(Frame(t=t, players=[_pl(21, Team.AWAY, sx, 10.0)],
                                ball=Ball(x=sx - (sx - 0.8) * i / steps,
                                          y=10.0, confidence=1.0)))
            t += 1
        _pause()

    def _home_goal():
        nonlocal t
        for _ in range(10):
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 34.0, 10.0)],
                                ball=Ball(x=34.0, y=10.0, confidence=1.0)))
            t += 1
        for i in range(8):
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 34.0, 10.0)],
                                ball=Ball(x=min(34.0 + i, 40.5), y=10.0,
                                          confidence=1.0)))
            t += 1
        _pause()

    far, close = 12.0, 6.0
    for _ in range(n):                  # döntetlennél
        _away_shot(far if soft else close)
    _home_goal()                        # a hazaiak vezetnek
    for _ in range(n):                  # vezetés közben
        _away_shot(close if soft else far)
    return Match(_meta(fps), frames)


def test_defense_by_score_flags_the_relaxing_wall():
    """Vezetve közelről kapják a lövéseket → előnyben leül a faluk."""
    from handball.pipeline.xg import defense_by_score

    rec = defense_by_score(_dbs_match(True))["home"]
    assert rec["leading"]["shots"] >= 5 and rec["rest"]["shots"] >= 5
    assert rec["verdict"] == "előnyben leül a faluk"


def test_defense_by_score_flags_the_tight_wall():
    """Vezetve messzebbről kapják a lövéseket → előnyben is feszes."""
    from handball.pipeline.xg import defense_by_score

    rec = defense_by_score(_dbs_match(False))["home"]
    assert rec["verdict"] == "előnyben is feszes a faluk"


def test_defense_by_score_needs_enough_shots():
    """Kevés (5-nél kevesebb) kapott lövésnél nincs ítélet."""
    from handball.pipeline.xg import defense_by_score

    rec = defense_by_score(_dbs_match(True, n=3))["home"]
    assert rec["verdict"] is None


def test_goal_patterns_flags_repeated_fingerprint():
    """3 bal-közeli hazai gól + 1 jobb-távoli → a minta kimondva."""
    from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                          PlayerPosition, Team)
    from handball.pipeline.xg import goal_patterns

    meta = MatchMeta(match_id="gpt", home_team="H", away_team="A",
                     fps=25.0)

    def goal(frames, t, sx, sy):
        for _ in range(30):
            frames.append(Frame(t=t, players=[
                PlayerPosition(track_id=1, team=Team.HOME, x=sx, y=sy)],
                ball=Ball(x=sx, y=sy, confidence=1.0)))
            t += 1
        x, y = sx, sy
        n = max(1, int((40.5 - sx) / 0.5))
        for k in range(1, n + 1):
            frames.append(Frame(t=t, players=[
                PlayerPosition(track_id=1, team=Team.HOME, x=sx, y=sy)],
                ball=Ball(x=sx + (40.5 - sx) * k / n,
                          y=sy + (10.0 - sy) * k / n, confidence=1.0)))
            t += 1
        for _ in range(40):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        return t

    frames = []
    t = 0
    for _ in range(3):
        t = goal(frames, t, 34.0, 4.0)   # bal-közeli (6 m, alsó sáv)
    t = goal(frames, t, 30.0, 16.0)      # jobb-távoli (10 m, felső sáv)

    gpt = goal_patterns(Match(meta, frames))
    h = gpt["home"]
    assert h["goals"] == 4
    assert h["patterns"].get("bal-közeli") == 3
    assert h["top"] == "bal-közeli"
    assert h["verdict"] == "a góljaik mintázata: bal-közeli (3/4)"
    assert gpt["away"]["verdict"] is None


def test_goal_patterns_spread_goals_no_verdict():
    """Szórt minták (1-1 gól sávonként) → nincs kimondható minta."""
    from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                          PlayerPosition, Team)
    from handball.pipeline.xg import goal_patterns

    meta = MatchMeta(match_id="gpt2", home_team="H", away_team="A",
                     fps=25.0)
    frames = []
    t = 0

    def goal(frames, t, sx, sy):
        for _ in range(30):
            frames.append(Frame(t=t, players=[
                PlayerPosition(track_id=1, team=Team.HOME, x=sx, y=sy)],
                ball=Ball(x=sx, y=sy, confidence=1.0)))
            t += 1
        n = max(1, int((40.5 - sx) / 0.5))
        for k in range(1, n + 1):
            frames.append(Frame(t=t, players=[
                PlayerPosition(track_id=1, team=Team.HOME, x=sx, y=sy)],
                ball=Ball(x=sx + (40.5 - sx) * k / n,
                          y=sy + (10.0 - sy) * k / n, confidence=1.0)))
            t += 1
        for _ in range(40):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        return t

    t = goal(frames, t, 34.0, 4.0)    # bal-közeli
    t = goal(frames, t, 30.0, 16.0)   # jobb-távoli
    t = goal(frames, t, 34.0, 10.0)   # közép-közeli
    gpt = goal_patterns(Match(meta, frames))
    assert gpt["home"]["verdict"] is None
