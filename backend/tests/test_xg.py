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
