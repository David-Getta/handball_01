"""Őr: a try/except-be zárt felületek ne nyeljenek el kivételt.

A recept szerint minden felület (összefoglaló-mondat, felderítés-mező,
meccsterv- és edzés-szabály) try/except-ben ül, hogy egy réteg hibája
ne vigye el a többit. Az ára: a HIBÁT is elnyeli. Így maradt
észrevétlen, hogy a felderítés `_scout_team_cached` függvénye a
`match_xg`-t a saját (későbbi) helyi importja ELŐTT használta — a
Python ezért az egész függvényben lokális névnek vette, a sor
UnboundLocalError-t dobott, és a szélső- meg a poszt-gólok MINDEN
felderítésben üresek maradtak (rájuk épülő edzői kulcs és öt
meccsterv-szabály sosem szólalt meg). A tesztek zöldek voltak: a
monkeypatch-es tesztek a saját alakjukat adják be, a valódi úton senki
nem nézte, dob-e valami.

Ez az őr a valódi úton nézi: nyomkövetővel (sys.settrace, csak a
hívás- és kivétel-események) lefuttatja a négy nagy felületet egy
szimulált meccsen, és minden kivételt összegyűjt, ami a `handball`
csomag kódjában SZÜLETETT — akkor is, ha valahol elnyelték. Egy sem
lehet (a generátor-zárás és a fájl-hiány — a gyorsítótár szándékos
hiány-ága — nem hiba).

Futtatás:
    python -m pytest tests/test_nema_kivetelek.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import handball  # noqa: E402

# Ezek nem hibák: a generátor lezárása és a bejárás vége vezérlés, a
# fájl-hiány a gyorsítótár/jegyzet "még nincs ilyen" ága.
NEM_HIBA = {"GeneratorExit", "StopIteration", "FileNotFoundError"}


def _elnyelt_kivetelek(feladatok) -> dict:
    """A feladatok futása közben a handball-kódban született kivételek:
    {(típus, fájl, sor, függvény): (darab, üzenet)}."""
    hb = os.path.dirname(os.path.abspath(handball.__file__))
    talalat: dict = {}
    # Az objektumot ÉLETBEN tartjuk: az id() a felszabadított kivételé
    # után újrahasznosul, és a következőt "már látottnak" vennénk.
    latott: dict = {}

    def lokalis(frame, event, arg):
        if event == "exception":
            exc = arg[1]
            if id(exc) not in latott:
                latott[id(exc)] = exc
                if type(exc).__name__ not in NEM_HIBA:
                    kulcs = (type(exc).__name__,
                             os.path.relpath(frame.f_code.co_filename, hb),
                             frame.f_lineno, frame.f_code.co_name)
                    n, uz = talalat.get(kulcs, (0, str(exc)[:160]))
                    talalat[kulcs] = (n + 1, uz)
        return lokalis

    def globalis(frame, event, arg):
        if frame.f_code.co_filename.startswith(hb):
            frame.f_trace_lines = False  # csak hívás/kivétel: gyors
            return lokalis
        return None

    regi = sys.gettrace()
    for fn in feladatok:
        sys.settrace(globalis)
        try:
            fn()
        finally:
            sys.settrace(regi)
    return talalat


def test_a_negy_nagy_felulet_nem_nyel_el_kivetelt():
    """Összefoglaló, felderítés (mindkét csapat), meccsterv és
    edzés-fókusz egy félidős, lövésekkel teli szimulált meccsen: egyetlen
    kivétel se szülessen a handball-kódban (elnyelve sem)."""
    from handball.models.tracking import Team
    from handball.pipeline.coach_summary import coach_summary
    from handball.pipeline.primitive_cache import primitive_cache
    from handball.pipeline.scouting import (matchup_plan, report_to_dict,
                                            scout_team)
    from handball.pipeline.training import training_focus
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=60, fps=25.0, seed=5,
                              shots_per_min=8, halftime_break_s=30)

    def felderites():
        with primitive_cache(m):
            h, a = scout_team(m, Team.HOME), scout_team(m, Team.AWAY)
            report_to_dict(h)
            matchup_plan(h, a)

    def osszefoglalo():
        with primitive_cache(m):
            coach_summary(m)

    def edzes():
        with primitive_cache(m):
            training_focus(m)

    talalat = _elnyelt_kivetelek([felderites, osszefoglalo, edzes])
    assert not talalat, "elnyelt kivételek a handball-kódban:\n" + "\n".join(
        f"  {n}× {tip} {fajl}:{sor} ({fv}) — {uz}"
        for (tip, fajl, sor, fv), (n, uz) in sorted(talalat.items()))


def test_az_or_eszreveszi_az_elnyelt_kivetelt(monkeypatch):
    """Az őr maga is működik: egy rétegbe ültetett hiba (amit a felület
    try/except-je elnyel, a hívás tehát nem bukik el) megjelenik a
    találatok közt — a hívó sorával."""
    from handball.pipeline.coach_summary import coach_summary
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=30, fps=25.0, seed=5,
                              shots_per_min=8)

    def hibas(*a, **k):
        raise ZeroDivisionError("ültetett hiba")

    monkeypatch.setattr("handball.pipeline.defense.wall_gaps", hibas)
    talalat = _elnyelt_kivetelek([lambda: coach_summary(m)])
    assert any(tip == "ZeroDivisionError" and "coach_summary" in fajl
               for (tip, fajl, _s, _f) in talalat), talalat


def test_a_felderites_kitolti_a_szelso_es_poszt_golokat():
    """A javított hiba közvetlen ellenőrzése: a valódi rétegekből a
    felderítés a szélső- és a poszt-gólokat is kitölti (a szimuláció
    hazai csapata lő; a "szélső" poszt gólja a szélső-gól mező párja)."""
    from handball.models.tracking import Team
    from handball.pipeline.scouting import scout_team
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=120, fps=25.0, seed=5,
                              shots_per_min=8)
    r = scout_team(m, Team.HOME)
    assert r.wing_total_goals > 0
    assert r.post_goals, "a poszt-gólok üresek"
    assert 0 < sum(r.post_goals.values()) <= r.wing_total_goals
    assert r.post_goals.get("szélső", 0) == r.wing_goals


def test_a_beirt_elnyelt_kivetel_jelentes_ures():
    """A kiadás előtti jelentés (scripts.swallowed_exceptions →
    docs/ELNYELT_KIVETELEK.md) ÜRES listát mond: ha a futtatás talált
    valamit, és a jelentés úgy került be, ez a teszt megállítja."""
    from pathlib import Path

    doc = (Path(__file__).resolve().parents[2] / "docs"
           / "ELNYELT_KIVETELEK.md")
    assert doc.exists(), "nincs elnyelt-kivétel jelentés — futtasd a szkriptet"
    szoveg = doc.read_text(encoding="utf-8")
    assert "Az elnyelt-kivétel lista üres" in szoveg
    assert "JAVÍTANDÓ" not in szoveg and "Elbukott felületek" not in szoveg


def test_a_jelentes_megnevezi_a_helyet_es_a_feluletet():
    """A jelentés-építő a találatot hellyel (fájl:sor, függvény) és a
    felülettel írja ki — ebből indul a javítás."""
    from scripts.swallowed_exceptions import build_report

    res = {"feluletek": 3, "elbukott": [("GET /x", "KeyError: 'a'")],
           "talalat": {("UnboundLocalError", "pipeline/scouting.py", 10711,
                        "_scout_team_cached"): {
                            "n": 4, "uzenet": "match_xg",
                            "feluletek": ["felderítés+meccsterv"]}}}
    s = build_report(res, 120)
    assert "JAVÍTANDÓ" in s
    assert "`pipeline/scouting.py:10711` (_scout_team_cached), 4×" in s
    assert "felderítés+meccsterv" in s and "GET /x: KeyError" in s
    assert "lista üres" not in s
