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


def _block_match(fps, gap_s, blocks=2):
    """Blokkolt lövések `gap_s` másodpercenként: a labda 12 m/s-mal repül
    a bal kapu felé (x: 15,76 → 10, 0,48 mp), a védőnél visszafordul, és
    6 m/s-mal jön vissza; közte a labda a mezőnyben áll. A fordulópont
    (0,48 mp) mindkét képrátán (0,04 és 0,12 mp-es minták) MINTÁRA
    esik: a blokk ~0,1 mp-es esemény, a felismerés a szomszédos
    mintákon nézi a fordulást."""
    frames = []
    t = 0
    seconds = 0.0
    events = []
    for b in range(blocks):
        events.append(b * gap_s)
    total = (blocks - 1) * gap_s + 1.5
    while seconds <= total:
        x = 20.0
        for t0 in events:
            u = seconds - t0
            if 0.0 <= u < 0.48 - 1e-9:
                x = 15.76 - 12.0 * u         # berepülés a védőig (x = 10)
            elif 0.48 - 1e-9 <= u < 1.0:
                x = 10.0 + 6.0 * (u - 0.48)  # visszapattanás
        frames.append(Frame(t=t, players=[
            _pl(1, Team.HOME, 2.0, 10.0, role="kapus"),
            _pl(5, Team.HOME, 10.0, 10.3),        # a blokkoló védő
            _pl(9, Team.AWAY, 14.0, 10.0)],
            ball=Ball(x=x, y=10.0, confidence=1.0)))
        t += 1
        seconds = t / fps
    return _match(frames, fps)


def test_a_blokk_szunet_masodpercben():
    """Két blokk 0,9 mp-cel egymás után: ritkítva (7-8 kocka) is kettő —
    a régi 12 kockás szünet a másodikat elnyelte volna."""
    from handball.pipeline.defense import BLOCK_COOLDOWN_S, detect_blocks

    assert 0 < BLOCK_COOLDOWN_S < 0.9
    for fps in (25.0, 25.0 / 3):
        res = detect_blocks(_block_match(fps, 1.44))
        assert res["home"]["blocks"] == 2, (fps, res)
    # Sűrűn a lassuló labda apró irányváltásai sem szaporítják a blokkot.
    assert detect_blocks(_block_match(25.0, 1.44, blocks=3))["home"]["blocks"] == 3


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



def test_a_tamadas_szakasz_minimuma_masodpercben():
    """0,3 mp-es támadás-szakaszok: sűrűn (7-8 kocka) és ritkítva (2-3
    kocka) is ugyanannyi szakasz — a régi "5 kocka" ritkítva mindet
    eldobta, sűrűn viszont a 0,2 mp-es villanásokat is elfogadta."""
    from handball.pipeline.setplays import (SEGMENT_MIN_S, segment_attacks,
                                            segment_min_length)

    assert 0 < SEGMENT_MIN_S <= 0.3
    counts = {}
    for fps in (25.0, 25.0 / 3):
        frames = []
        t = 0
        n = max(1, int(round(0.3 * fps)))
        for k in range(12):
            home = k % 2 == 0
            for _ in range(n):
                if home:
                    players = [_pl(1, Team.HOME, 2.0, 10.0, role="kapus"),
                               _pl(2, Team.HOME, 30.0, 8.0),
                               _pl(3, Team.HOME, 28.0, 12.0),
                               _pl(20, Team.AWAY, 38.0, 10.0, role="kapus"),
                               _pl(21, Team.AWAY, 33.0, 10.0)]
                    ball = Ball(x=30.0, y=8.0, confidence=1.0)
                else:
                    players = [_pl(1, Team.HOME, 2.0, 10.0, role="kapus"),
                               _pl(2, Team.HOME, 7.0, 10.0),
                               _pl(20, Team.AWAY, 38.0, 10.0, role="kapus"),
                               _pl(21, Team.AWAY, 10.0, 8.0),
                               _pl(22, Team.AWAY, 12.0, 12.0)]
                    ball = Ball(x=10.0, y=8.0, confidence=1.0)
                frames.append(Frame(t=t, players=players, ball=ball))
                t += 1
        m = _match(frames, fps)
        assert segment_min_length(m) == max(1, int(round(SEGMENT_MIN_S * fps)))
        counts[fps] = len(segment_attacks(m))
    assert counts[25.0] == counts[25.0 / 3] == 12, counts


def test_a_labdavezetes_tav_ablakos_nem_remeges_osszeg():
    """Egy labdás játékos 6 m-t fut 2 mp alatt kockánként ±0,3 m
    remegéssel: sűrűn a kockánkénti összeg ~6 + 50·0,3 m lett volna;
    az ablakos mérés ~6 m mindkét ritkításnál, a holds-szám azonos."""
    from handball.pipeline.decisions import CARRY_WINDOW_S, ball_carry_players

    assert 0.3 <= CARRY_WINDOW_S <= 1.0
    res = {}
    for fps in (25.0, 25.0 / 3):
        frames = []
        t = 0
        for _hold in range(6):
            n = int(round(2.0 * fps))
            for i in range(n + 1):
                x = 20.0 + 6.0 * i / n + (0.3 if i % 2 else -0.3)
                frames.append(Frame(t=t, players=[
                    _pl(7, Team.HOME, x, 10.0),
                    _pl(1, Team.HOME, 2.0, 10.0, role="kapus")],
                    ball=Ball(x=x + 0.2, y=10.0, confidence=1.0)))
                t += 1
            for _ in range(max(2, int(round(0.5 * fps)))):
                frames.append(Frame(t=t, players=[], ball=None))
                t += 1
        res[fps] = ball_carry_players(_match(frames, fps))["home"]
    for fps, r in res.items():
        assert r["holds"] == 6, (fps, r)
        assert 5.0 <= r["avg_m"] <= 7.5, (fps, r)
    assert abs(res[25.0]["avg_m"] - res[25.0 / 3]["avg_m"]) <= 1.0, res


def test_a_fal_csuszas_kesese_a_tenyleges_minta_eltolas_ideje():
    """A vendég fal 0,72 mp késéssel követi a labdát: sűrűn (18 kocka)
    és ritkítva (6 kocka) is ~0,72 mp és "lassan csúsznak"; a rács a
    minták ideje (ritkítva 0,12 mp-es lépések), nem névleges 0,1 mp. A
    védekezett-idő minimum másodpercben: 8 mp sűrűn 200, ritkítva 67
    kocka."""
    import math

    from handball.pipeline.defense import SHIFT_MIN_S, defensive_shift_lag

    assert SHIFT_MIN_S == 8.0
    for fps in (25.0, 25.0 / 3):
        lag = int(round(0.72 * fps))
        period = int(round(2.0 * fps))
        frames = []
        for i in range(8 * period + lag):
            ball_y = 10.0 + 6.0 * math.sin(2 * math.pi * i / period)
            wall_y = 10.0 + 6.0 * math.sin(2 * math.pi * (i - lag) / period)
            gk = _pl(29, Team.AWAY, 39.5, 10.0, role="kapus")
            frames.append(Frame(t=i, players=[
                _pl(1, Team.HOME, 32.0, ball_y),
                _pl(21, Team.AWAY, 36.0, wall_y - 2.0),
                _pl(22, Team.AWAY, 36.0, wall_y),
                _pl(23, Team.AWAY, 36.0, wall_y + 2.0), gk],
                ball=Ball(x=32.0, y=ball_y, confidence=1.0)))
        rec = defensive_shift_lag(_match(frames, fps))["away"]
        assert rec["frames"] >= int(round(SHIFT_MIN_S * fps)), fps
        assert abs(rec["lag_s"] - lag / fps) < 1e-6, (fps, rec)
        assert rec["verdict"] == "lassan csúsznak", (fps, rec)
