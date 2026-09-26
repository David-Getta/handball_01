"""Kocka-ritkítás-független mozgás-mérés: a sebesség-ablak, a birtoklási
minimum és a blokk-szünet MÁSODPERCBEN, a térnyerés és a támadó-mozgás
remegés-mentes (nettó / ablakos) mérése.

A termék minden 3. kockát dolgozza fel (fps/3): ami kockában van
megadva, az ott háromszoros időt jelent; ami kockánkénti összeg, azt a
detektálási remegés sűrű felvételen felfújja. Ugyanaz a helyzet sűrűn
és ritkítva ugyanazt az ítéletet kell adja.
"""

from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                      PlayerPosition, PositionSource, Team)
from handball.pipeline.tactics import (ATTACK_MOTION_MIN_S, SPEED_WINDOW_S,
                                       attack_motion, displacement_at,
                                       speed_window_frames)


def _pl(tid, team, x, y, role=None, src=PositionSource.MEASURED):
    return PlayerPosition(track_id=tid, team=team, x=x, y=y, source=src,
                          confidence=1.0, role=role)


def _match(frames, fps):
    return Match(MatchMeta(match_id="k", home_team="H", away_team="A",
                           fps=fps), frames)


def test_a_sebesseg_ablak_masodpercben_ugyanaz_surun_es_ritkitva():
    """25 fps-en ±2 kocka, 8,33 fps-en ±1 kocka — mindkettő ~0,16–0,24 mp,
    nem "±2 kocka" (ami ritkítva 0,48 mp lenne)."""
    assert speed_window_frames(25.0) == 2
    assert speed_window_frames(25.0 / 3) == 1
    assert speed_window_frames(0.0) == 2          # hibás fps: 25-ös alap
    # Egy 4 m/s-mal futó játékos mindkét ritkításnál ~4 m/s.
    for fps in (25.0, 25.0 / 3):
        frames = [Frame(t=i, players=[_pl(1, Team.HOME, 10.0 + 4.0 * i / fps, 5.0)],
                        ball=None) for i in range(20)]
        p0, p1, dt = displacement_at(frames, 10, fps, lambda p: p.track_id == 1)
        assert abs(math.hypot(p1.x - p0.x, p1.y - p0.y) / dt - 4.0) < 1e-6
        assert abs(dt - 2 * speed_window_frames(fps) / fps) < 1e-9
    # Kilógó ablak / hiányzó játékos: None, nem kivétel.
    frames = [Frame(t=i, players=[_pl(1, Team.HOME, 1.0, 1.0)], ball=None)
              for i in range(3)]
    assert displacement_at(frames, 0, 25.0, lambda p: p.track_id == 1) is None
    assert displacement_at(frames, 1, 25.0, lambda p: p.track_id == 9) is None


def _possession_match(fps, seconds_per_stretch, stretches=10, keeper_first=True):
    """Váltakozó birtoklási szakaszok (hazai a kapussal / vendég), mind
    `seconds_per_stretch` hosszú — a labda a birtokosnál."""
    frames = []
    t = 0
    n = max(1, int(round(seconds_per_stretch * fps)))
    for k in range(stretches):
        home = k % 2 == 0
        for _ in range(n):
            if home:
                players = [_pl(1, Team.HOME, 3.0, 10.0, role="kapus"),
                           _pl(2, Team.HOME, 12.0, 5.0),
                           _pl(3, Team.AWAY, 30.0, 10.0)]
                ball = Ball(x=3.0, y=10.0, confidence=1.0)
            else:
                players = [_pl(1, Team.HOME, 3.0, 10.0, role="kapus"),
                           _pl(2, Team.HOME, 12.0, 5.0),
                           _pl(3, Team.AWAY, 30.0, 10.0)]
                ball = Ball(x=30.0, y=10.0, confidence=1.0)
            frames.append(Frame(t=t, players=players, ball=ball))
            t += 1
    return _match(frames, fps)


def test_a_kapus_bevonas_birtoklasi_minimuma_masodpercben():
    """0,4 mp-es szakaszok: sűrűn (10 kocka) és ritkítva (3 kocka) is
    számítanak — a régi "5 kocka" ritkítva mindet eldobta volna."""
    from handball.pipeline.goalkeeper import KIV_MIN_POSS_S, keeper_involvement

    assert 0 < KIV_MIN_POSS_S <= 0.4
    surun = keeper_involvement(_possession_match(25.0, 0.4, stretches=20))
    ritkitva = keeper_involvement(_possession_match(25.0 / 3, 0.4, stretches=20))
    assert surun["home"]["attacks"] == ritkitva["home"]["attacks"] == 10
    assert surun["home"]["with_keeper"] == ritkitva["home"]["with_keeper"] == 10
    assert surun["home"]["verdict"] == ritkitva["home"]["verdict"] == \
        "sokat játszanak vissza"


def _block_match(fps, gap_s):
    """Két blokk `gap_s` másodperccel egymás után: a labda lövés-tempóban
    repül a bal kapu felé, egy védőnél visszafordul."""
    frames = []
    t = 0

    def _shot_block(t0):
        out = []
        # 3 kocka: közelít (gyors), fordulópont (védő mellett), távolodik
        speed = 12.0 / fps  # 12 m/s
        xs = [10.0 + speed, 10.0, 10.0 + speed]
        for k, x in enumerate(xs):
            out.append(Frame(t=t0 + k, players=[
                _pl(1, Team.HOME, 2.0, 10.0, role="kapus"),
                _pl(5, Team.HOME, 10.0, 10.3),        # a blokkoló védő
                _pl(9, Team.AWAY, 14.0, 10.0)],
                ball=Ball(x=x, y=10.0, confidence=1.0)))
        return out

    frames += _shot_block(t)
    t += 3
    idle = max(0, int(round(gap_s * fps)) - 3)
    for _ in range(idle):
        frames.append(Frame(t=t, players=[
            _pl(1, Team.HOME, 2.0, 10.0, role="kapus"),
            _pl(5, Team.HOME, 10.0, 10.3), _pl(9, Team.AWAY, 14.0, 10.0)],
            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    frames += _shot_block(t)
    return _match(frames, fps)


def test_a_blokk_szunet_masodpercben():
    """Két blokk 0,9 mp-cel egymás után: ritkítva (7-8 kocka) is kettő —
    a régi 12 kockás szünet a másodikat elnyelte volna."""
    from handball.pipeline.defense import BLOCK_COOLDOWN_S, detect_blocks

    assert 0 < BLOCK_COOLDOWN_S < 0.9
    for fps in (25.0, 25.0 / 3):
        res = detect_blocks(_block_match(fps, 0.9))
        assert res["home"]["blocks"] == 2, fps


def test_a_ternyeres_a_futam_netto_elmozdulasa_nem_remeges_osszeg(monkeypatch):
    """Egy birtokos 5 m-t visz előre 2 mp alatt, kockánként ±0,3 m
    remegéssel: sűrűn a pozitív lépések összege ~5 + 25·0,3 m lett volna;
    a nettó mérés ~5 m mindkét ritkításnál."""
    from handball.pipeline import roles
    from handball.pipeline.decisions import ball_carrier_roles

    # A poszt-becslés a decisions-ben helyi import (from .roles import …),
    # ezért a forrás-modulon cseréljük.
    monkeypatch.setattr(
        roles, "estimate_positions",
        lambda match, config=None: {"home": {7: {"poszt": "irányító"}},
                                    "away": {}})
    meters = {}
    for fps in (25.0, 25.0 / 3):
        frames = []
        n = int(round(2.0 * fps))
        for i in range(n + 1):
            x = 20.0 + 5.0 * i / n + (0.3 if i % 2 else -0.3)
            frames.append(Frame(t=i, players=[
                _pl(7, Team.HOME, x, 10.0), _pl(1, Team.HOME, 2.0, 10.0, role="kapus"),
                _pl(9, Team.AWAY, 35.0, 10.0)],
                ball=Ball(x=x + 0.2, y=10.0, confidence=1.0)))
        meters[fps] = ball_carrier_roles(_match(frames, fps))["home"]["meters"]
    assert 4.0 <= meters[25.0] <= 6.5, meters
    assert abs(meters[25.0] - meters[25.0 / 3]) <= 1.0, meters


def test_az_allo_tamadas_remegessel_sem_mozgasos():
    """Álló támadók 0,2 m-es kockánkénti remegéssel: a kockánkénti
    összeg 25 fps-en 5 m/s-ot ("mozgásos") adott volna; az ablakos mérés
    ~0 m/s: "álló" — és ritkítva ugyanez."""
    from handball.pipeline.tactics import classify_phase  # noqa: F401 (szerződés)

    for fps in (25.0, 25.0 / 3):
        n = int(round((ATTACK_MOTION_MIN_S / 6 + 20) * fps))
        frames = []
        for i in range(n):
            jit = 0.2 if i % 2 else -0.2
            players = [_pl(1, Team.HOME, 2.0, 10.0, role="kapus")]
            # hat hazai támadó a vendég térfélen, álló pozícióban (remegve)
            for k in range(6):
                players.append(_pl(10 + k, Team.HOME, 28.0 + jit, 3.0 + 2.5 * k))
            players.append(_pl(20, Team.AWAY, 38.0, 10.0, role="kapus"))
            for k in range(6):
                players.append(_pl(30 + k, Team.AWAY, 33.0, 3.0 + 2.5 * k))
            frames.append(Frame(t=i, players=players,
                                ball=Ball(x=28.0 + jit, y=8.0, confidence=1.0)))
        res = attack_motion(_match(frames, fps))["home"]
        assert res["time_s"] >= ATTACK_MOTION_MIN_S, (fps, res)
        assert res["avg_mps"] is not None and res["avg_mps"] < 0.5, (fps, res)
        assert res["style"] == "álló", (fps, res)
