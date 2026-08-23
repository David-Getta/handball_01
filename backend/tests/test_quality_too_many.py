"""
Minőség-jelentés: a TÖBBLET ugyanolyan hiba, mint a hiány.

Miért ez a teszt: egy éles meccsen a rendszer 27,4 játékost mért
kockánként (a pályán 14 lehet) — a nézőteret és a kispadot is
játékosnak mérte —, a jelentés mégis 70/100-at mutatott. A képlet a
lefedettséget 1.0-ra vágta, tehát a hibás feldolgozást TÖKÉLETESNEK
látta a játékos-részen. Ilyenkor a birtoklás, a fal-forma és minden
távolság-alapú réteg mást mér, mint amit mond — a felhasználónak ezt
tudnia kell, mielőtt bármelyik számban megbízik.

Futtatás:
    python -m pytest tests/test_quality_too_many.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (  # noqa: E402
    Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team)
from handball.pipeline.quality import (  # noqa: E402
    EXPECTED_PLAYERS, TOO_MANY_PLAYERS, TOO_MANY_SCORE_CAP,
    compute_quality_report)


def _match(players_per_frame: int, frames: int = 200, fps: float = 25.0):
    """Felvétel, ahol minden kockán ennyi MÉRT játékos van a pályán."""
    fs = []
    for t in range(frames):
        pl = []
        for i in range(players_per_frame):
            pl.append(PlayerPosition(
                track_id=i,
                team=Team.HOME if i % 2 == 0 else Team.AWAY,
                x=5.0 + (i % 10) * 3.0, y=3.0 + (i % 5) * 3.0,
                source=PositionSource.MEASURED, confidence=1.0))
        fs.append(Frame(t=t, players=pl,
                        ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    meta = MatchMeta(match_id="q", home_team="H", away_team="A", fps=fps)
    return Match(meta, fs)


def test_tul_sok_jatekos_figyelmeztetest_kap():
    """27 játékos/kocka: ezt ki KELL mondani, méghozzá a teendővel."""
    rep = compute_quality_report(_match(27))
    assert rep["avg_measured_players"] == 27.0
    szoveg = " ".join(rep["warnings"])
    assert "TÚL sok játékos" in szoveg
    assert "kalibráció" in szoveg  # a leggyakoribb ok és a teendő


def test_tul_sok_jatekos_nem_kap_teljes_pontot():
    """A többlet RONTSA a pontszámot — korábban tökéletesnek számított."""
    jo = compute_quality_report(_match(EXPECTED_PLAYERS))["score"]
    rossz = compute_quality_report(_match(27))["score"]
    assert jo > rossz, "a 27 játékos/kocka nem lehet ugyanolyan jó, mint a 14"
    # A plafon akkor is tart, ha a labda-lefedettség tökéletes: ha a
    # nézőtér is a pályán van, az egész feldolgozás megkérdőjelezhető.
    assert rossz <= TOO_MANY_SCORE_CAP, (
        f"a hibás feldolgozás pontszáma túl magas: {rossz}")


def test_pontos_letszam_a_legjobb():
    """A 14 (a valós létszám) legyen a csúcs — se alatta, se fölötte."""
    pont = {n: compute_quality_report(_match(n))["score"]
            for n in (8, EXPECTED_PLAYERS, 20)}
    assert pont[EXPECTED_PLAYERS] > pont[8]
    assert pont[EXPECTED_PLAYERS] > pont[20]


def test_a_kuszob_a_valos_letszam_folott_van():
    """A kispad/bíró még beleférjen — ne riasszunk 15 játékosnál."""
    assert TOO_MANY_PLAYERS > EXPECTED_PLAYERS
    rep = compute_quality_report(_match(EXPECTED_PLAYERS + 1))
    assert not any("TÚL sok játékos" in w for w in rep["warnings"])


def test_reszleges_lefedettseg_jelzest_kap():
    """"Csak az első félidőt elemezte ki" — ezt ki kell mondani."""
    m = _match(EXPECTED_PLAYERS, frames=250, fps=25.0)   # 10 mp feldolgozva
    m.meta.stride = 1
    m.meta.video_seconds = 60.0                          # a videó 60 mp
    rep = compute_quality_report(m)
    assert rep["processed_pct"] is not None
    assert 15.0 <= rep["processed_pct"] <= 18.0
    assert any("csak a" in w and "%-át dolgoztuk fel" in w
               for w in rep["warnings"])


def test_teljes_lefedettsegnel_nincs_jelzes():
    """A teljes videót feldolgozva ne riogassunk."""
    m = _match(EXPECTED_PLAYERS, frames=250, fps=25.0)   # 10 mp
    m.meta.stride = 1
    m.meta.video_seconds = 10.0
    rep = compute_quality_report(m)
    assert not any("%-át dolgoztuk fel" in w for w in rep["warnings"])


def test_regi_meccs_video_hossz_nelkul_nem_szall_el():
    """A régi mentésekben nincs video_seconds — ott nincs jelzés sem."""
    m = _match(EXPECTED_PLAYERS, frames=100)
    m.meta.video_seconds = None
    rep = compute_quality_report(m)
    assert rep["processed_pct"] is None
