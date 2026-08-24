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


def test_kalibracio_nelkul_figyelmeztetunk():
    """Kalibráció nélkül a nézőtér is "a pályára" kerül — mondjuk ki."""
    m = _match(EXPECTED_PLAYERS, frames=100)
    m.meta.calibrated = False
    rep = compute_quality_report(m)
    assert rep["calibrated"] is False
    assert any("kalibráció NÉLKÜL" in w for w in rep["warnings"])


def test_regi_meccsnel_nem_allitunk_semmit_a_kalibraciorol():
    """A mező előtti mentésekben nincs adat — abból nem vádolunk."""
    m = _match(EXPECTED_PLAYERS, frames=100)
    m.meta.calibrated = None
    rep = compute_quality_report(m)
    assert rep["calibrated"] is None
    assert not any("kalibráció NÉLKÜL" in w for w in rep["warnings"])


def test_elso_teendo_a_kalibraciot_teszi_elore():
    """Négy-hat figyelmeztetésnél a sorrend számít.

    A rossz kalibrációt kijavítva a jelzések fele magától eltűnik; a
    mezszám-hozzárendelés viszont a rossz alapokon semmit nem ér. Az
    "első teendő" ezért NEM a lista első eleme, hanem a rangsor szerinti
    legfontosabb.
    """
    from handball.pipeline.quality import next_action

    # A töredezettség előbb kerül a listába, a kalibráció mégis nyer.
    w = ["A követés töredezett (2891 track ...)",
         "Kevés labda-észlelés (26%) ...",
         "TÚL sok játékos látszik (átlag 27.4/kocka ...)"]
    teendo = next_action(w)
    assert teendo is not None and "Kalibrálj újra" in teendo


def test_elso_teendo_figyelmeztetes_nelkul_nincs():
    """Tiszta feldolgozásnál nincs mit tenni."""
    from handball.pipeline.quality import next_action

    assert next_action([]) is None


def test_elso_teendo_a_jelentesben_is_ott_van():
    """A kliens ebből emeli ki — a jelentésnek vinnie kell."""
    rep = compute_quality_report(_match(27))
    assert rep["next_action"] is not None
    assert "Kalibrálj újra" in rep["next_action"]


def test_minden_figyelmeztetesnek_van_teendoje():
    """ŐR: új figyelmeztetéshez tartozzon teendő is.

    Egy figyelmeztetés, amihez nem tudunk teendőt mondani, csak
    rossz érzést kelt. Ez a teszt a modul saját üzeneteit veti össze a
    rangsorral — a listából kimaradó jelzés itt bukik el.
    """
    import re
    from pathlib import Path

    from handball.pipeline.quality import NEXT_ACTION_ORDER

    src = (Path(__file__).resolve().parent.parent / "handball" / "pipeline"
           / "quality.py").read_text(encoding="utf-8")
    # A rangsorban keresett részleteknek tényleg szerepelniük kell a
    # modul üzeneteiben (elgépelés esetén a teendő sosem sülne el).
    for reszlet, _teendo in NEXT_ACTION_ORDER:
        assert src.count(reszlet) >= 2, (
            f"a rangsor részlete nem szerepel figyelmeztetésben: {reszlet}")
    assert len(NEXT_ACTION_ORDER) >= 8
    assert len({r for r, _ in NEXT_ACTION_ORDER}) == len(NEXT_ACTION_ORDER)
    del re


def test_megbizhatosag_kulon_szol_a_labda_alapu_retegekrol():
    """26% labda-lefedettségnél a birtoklás-számokra nem lehet építeni.

    Az éles meccsen a felhasználó ugyanolyan magabiztosan olvasta a
    birtoklás- és passz-számokat, mint a pozíció-alapúakat — pedig a
    labdát a kockák negyedén láttuk. Ezt rétegre bontva kell kimondani.
    """
    from handball.pipeline.quality import (BALL_CONFIDENCE_PCT,
                                           analysis_confidence)

    m = _match(EXPECTED_PLAYERS, frames=200)     # minden kockán van labda
    m.meta.calibrated = True
    sorok = {r["layer"]: r for r in analysis_confidence(m)}
    assert sorok["ball"]["available"] is True

    # Most vegyük el a labdát a kockák nagy részéről.
    for i, f in enumerate(m.frames):
        if i % 4 != 0:
            f.ball = None
    sorok = {r["layer"]: r for r in analysis_confidence(m)}
    assert sorok["ball"]["available"] is False
    assert "birtoklás" in sorok["ball"]["reason"]
    assert BALL_CONFIDENCE_PCT > 30.0


def test_megbizhatosag_kulon_szol_a_palya_alapu_retegekrol():
    """Lehetetlen létszámnál a távolság-alapú rétegek nem hihetők."""
    from handball.pipeline.quality import analysis_confidence

    jo = _match(EXPECTED_PLAYERS, frames=200)
    jo.meta.calibrated = True
    assert {r["layer"]: r for r in analysis_confidence(jo)}[
        "court"]["available"] is True

    rossz = _match(27, frames=200)
    rossz.meta.calibrated = True
    sor = {r["layer"]: r for r in analysis_confidence(rossz)}["court"]
    assert sor["available"] is False
    assert "lehetetlen létszám" in sor["reason"]

    # Kalibráció nélkül szintén — más indokkal.
    nincs = _match(EXPECTED_PLAYERS, frames=200)
    nincs.meta.calibrated = False
    sor2 = {r["layer"]: r for r in analysis_confidence(nincs)}["court"]
    assert sor2["available"] is False
    assert "kalibráció" in sor2["reason"]
