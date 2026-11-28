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

import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

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


# ---- Kétoldalú meccs: a fordulásos ágak is lefutnak -------------------------

def _ketoldalu_meccs(sorrend: str):
    """Gólonként felépített kis meccs: "H" = hazai gól a +x kapuba, "A" =
    vendég gól a x=0 kapuba; minden gól után középkezdés. (A szimulált
    meccsen csak a hazai lő — ott a vezetés sosem fordul.)"""
    from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                          PlayerPosition, PositionSource,
                                          Team)

    def jatekos(tid, csapat, x):
        return PlayerPosition(track_id=tid, team=csapat, x=x, y=10.0,
                              source=PositionSource.MEASURED, confidence=1.0)

    frames, t = [], 0
    for ki in sorrend:
        for i in range(7):
            if ki == "H":
                frames.append(Frame(
                    t=t, players=[jatekos(1, Team.HOME, 33.0)],
                    ball=Ball(x=34.0 + i, y=10.0, confidence=1.0)))
            else:
                frames.append(Frame(
                    t=t, players=[jatekos(11, Team.AWAY, 7.0)],
                    ball=Ball(x=6.0 - i, y=10.0, confidence=1.0)))
            t += 1
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 20
    return Match(MatchMeta(match_id=f"ketoldalu-{sorrend}", home_team="Hazai",
                           away_team="Vendég", fps=25.0), frames)


def test_a_negy_nagy_felulet_ketoldalu_meccsen_sem_nyel_el_kivetelt():
    """A szimulált meccsen csak a hazai lő gólt, ezért a kétoldalú ágak
    (fordulás, egalizálás, elengedett vezetés) ott sosem futnak le. Így
    maradt észrevétlen, hogy az összefoglaló "Sorozatok" szakasza
    fordulásos, de sorozat nélküli meccsen kivételt dobott (üres listán
    max()), és az egész szakasz némán kimaradt.

    Két kis meccs a valódi úton: (1) a vezetés kétszer fordul, egyik
    csapat sem lő három gólt válasz nélkül; (2) két sorozat, egy
    fordulás, elengedett háromgólos előny. Egyetlen kivétel se szülessen
    a handball-kódban (elnyelve sem)."""
    from handball.models.tracking import Team
    from handball.pipeline.coach_summary import coach_summary
    from handball.pipeline.momentum import annotate_runs, score_progression
    from handball.pipeline.primitive_cache import primitive_cache
    from handball.pipeline.scouting import (matchup_plan, report_to_dict,
                                            scout_team)
    from handball.pipeline.training import training_focus

    szoros, fordulos = _ketoldalu_meccs("HAAHH"), _ketoldalu_meccs("HHHAAAA")
    # A fixture-ök tényleg azt az ágat járatják, amiért készültek.
    assert annotate_runs(szoros) == []
    assert score_progression(szoros)["lead_changes"] == 2
    assert len(annotate_runs(fordulos)) == 2
    assert score_progression(fordulos)["lead_changes"] == 1

    for m in (szoros, fordulos):
        def felderites():
            with primitive_cache(m):
                h, a = scout_team(m, Team.HOME), scout_team(m, Team.AWAY)
                report_to_dict(h)
                matchup_plan(h, a)
                matchup_plan(a, h)

        def osszefoglalo():
            with primitive_cache(m):
                cimek = [s["title"] for s in coach_summary(m)["sections"]]
            assert "Sorozatok" in cimek, (m.meta.match_id, cimek)

        def edzes():
            with primitive_cache(m):
                training_focus(m)

        talalat = _elnyelt_kivetelek([felderites, osszefoglalo, edzes])
        assert not talalat, (
            f"elnyelt kivételek ({m.meta.match_id}):\n" + "\n".join(
                f"  {n}× {tip} {fajl}:{sor} ({fv}) — {uz}"
                for (tip, fajl, sor, fv), (n, uz) in sorted(talalat.items())))


# ---- Statikus pár: a helyi import a HASZNÁLAT ELŐTT álljon ------------------
#
# A fenti őr a kivételt csak azon az ágon fogja meg, amelyik a próba-
# meccsen le is fut. A modul elején leírt hibafajta (a függvényben KÉSŐBB
# álló helyi import miatt a név az egész függvényben lokális, a korábbi
# használat UnboundLocalError) viszont a forrásból is látszik — futtatás
# nélkül, minden függvényben.

class _SajatHatokor(ast.NodeVisitor):
    """Egy függvény SAJÁT hatókörének helyi importjai, egyéb kötései és
    név-olvasásai. A beágyazott függvény / lambda törzsébe nem megy bele
    (az híváskor oldódik fel); a listaképző a helyén fut, de a saját
    célváltozói nem a függvény nevei."""

    def __init__(self):
        self.importok: dict = {}     # név -> az első helyi import sora
        self.kotesek: dict = {}      # név -> az első egyéb kötés sora
        self.olvasasok: dict = {}    # név -> [sor, …]
        self.kulso: set = set()      # global / nonlocal nevek

    def _elso(self, tar, nev, sor):
        tar[nev] = min(sor, tar.get(nev, sor))

    def visit_FunctionDef(self, node):
        self._elso(self.kotesek, node.name, node.lineno)
        for kif in (node.decorator_list + node.args.defaults
                    + [d for d in node.args.kw_defaults if d is not None]):
            self.visit(kif)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        self._elso(self.kotesek, node.name, node.lineno)

    def visit_Lambda(self, node):
        for kif in node.args.defaults:
            self.visit(kif)

    def visit_Global(self, node):
        self.kulso.update(node.names)

    visit_Nonlocal = visit_Global

    def visit_Import(self, node):
        for a in node.names:
            self._elso(self.importok, (a.asname or a.name).split(".")[0],
                       node.lineno)

    def visit_ImportFrom(self, node):
        for a in node.names:
            self._elso(self.importok, a.asname or a.name, node.lineno)

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load):
            self.olvasasok.setdefault(node.id, []).append(node.lineno)
        else:
            self._elso(self.kotesek, node.id, node.lineno)

    def visit_ExceptHandler(self, node):
        if node.name:
            self._elso(self.kotesek, node.name, node.lineno)
        self.generic_visit(node)

    def _kepzo(self, node):
        sajat = set()
        for belso in ast.walk(node):
            if isinstance(belso, (ast.ListComp, ast.SetComp, ast.DictComp,
                                  ast.GeneratorExp)):
                for g in belso.generators:
                    sajat.update(n.id for n in ast.walk(g.target)
                                 if isinstance(n, ast.Name))
            elif isinstance(belso, ast.Lambda):
                sajat.update(a.arg for a in belso.args.args
                             + belso.args.kwonlyargs)
        for n in ast.walk(node):
            if (isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
                    and n.id not in sajat):
                self.olvasasok.setdefault(n.id, []).append(n.lineno)

    visit_ListComp = visit_SetComp = visit_DictComp = _kepzo
    visit_GeneratorExp = _kepzo


def _korai_import_hasznalat(forras: str) -> list:
    """[(függvény, név, a használat sora, a helyi import sora), …]: a
    függvény egy nevet a SAJÁT, későbbi sorban álló helyi importja előtt
    olvas (és addig más kötése sincs) — futáskor UnboundLocalError."""
    ki = []
    for fn in ast.walk(ast.parse(forras)):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        h = _SajatHatokor()
        for utasitas in fn.body:
            h.visit(utasitas)
        parameterek = {a.arg for a in (fn.args.posonlyargs + fn.args.args
                                       + fn.args.kwonlyargs)}
        parameterek |= {a.arg for a in (fn.args.vararg, fn.args.kwarg) if a}
        for nev, import_sor in h.importok.items():
            if nev in parameterek or nev in h.kulso:
                continue
            elso_kotes = min(import_sor, h.kotesek.get(nev, import_sor))
            korai = [s for s in h.olvasasok.get(nev, []) if s < elso_kotes]
            if korai:
                ki.append((fn.name, nev, min(korai), import_sor))
    return sorted(ki, key=lambda r: (r[2], r[1]))


def test_a_helyi_import_a_hasznalat_elott_all():
    """A `handball` és a `scripts` egyetlen függvénye sem használ nevet a
    saját, KÉSŐBB álló helyi importja előtt. (A függvényben BÁRHOL
    importált név az EGÉSZ függvényben lokális: a korai sor akkor is
    UnboundLocalError-t dob, ha a modul tetején ugyanez a név be van
    importálva — a try/except pedig elnyeli.)"""
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1]
    talalat, fajlok = [], 0
    for gyoker in ("handball", "scripts"):
        for ut in sorted((backend / gyoker).rglob("*.py")):
            fajlok += 1
            for fv, nev, hasznalat, imp in _korai_import_hasznalat(
                    ut.read_text(encoding="utf-8")):
                talalat.append(f"{ut.relative_to(backend)}:{hasznalat} "
                               f"({fv}): a(z) `{nev}` használata megelőzi a "
                               f"helyi importját ({imp}. sor)")
    assert not talalat, ("a helyi import a használat ELŐTT álljon:\n  "
                         + "\n  ".join(talalat))
    assert fajlok >= 80, fajlok           # tényleg a kódbázist járja be


def test_a_statikus_or_megfogja_a_kesoi_helyi_importot():
    """Ön-teszt: a leírt hibát megtalálja (akkor is, ha a név a modul
    tetején is be van importálva), a jó sorrendet, a listaképzőt, a
    lambdát és a beágyazott függvényt nem jelzi — és a Python tényleg
    UnboundLocalError-t dob az ilyen kódra."""
    forras = (
        "from .xg import match_xg\n"                              # 1
        "\n"
        "def felderites(match):\n"                                # 3
        "    try:\n"
        "        r = match_xg(match)\n"                           # 5: korai
        "    except Exception:\n"
        "        r = None\n"
        "    from .xg import match_xg\n"                          # 8: késői
        "    return r\n"
        "\n"
        "def rendben(match, shot_speeds):\n"                      # 11
        "    from .xg import match_xg\n"
        "    sorok = [s['shots'] for s in match_xg(match)['shooters']]\n"
        "    kulcs = lambda s: s['goals']\n"
        "    def belso():\n"
        "        return kesobb(match)\n"                          # híváskor
        "    from .stats import kesobb\n"
        "    from .event_detection import shot_speeds\n"          # paraméter
        "    return sorok, kulcs, belso, shot_speeds(match)\n")
    assert _korai_import_hasznalat(forras) == [("felderites", "match_xg",
                                                5, 8)]

    def hibas():
        try:
            return os.getcwd()        # az `os` itt a függvény LOKÁLIS neve
        finally:
            pass
        import os                     # noqa: F811 — ez teszi lokálissá

    with pytest.raises(UnboundLocalError):
        hibas()
    assert _korai_import_hasznalat(
        "def hibas():\n    x = os.getcwd()\n    import os\n    return x\n"
    ) == [("hibas", "os", 2, 3)]


# ---- Elfajult meccsek: "kevés minta → None", kivétel nélkül ------------------

def _elfajult_meccsek() -> dict:
    """Meccsek, amelyeken alig van mit mérni — a felületeknek ezeken
    hallgatniuk kell (None / üres), nem kivétellel elesniük."""
    from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                          PlayerPosition, PositionSource,
                                          Team)

    def jatekos(tid, csapat, x, y):
        return PlayerPosition(track_id=tid, team=csapat, x=x, y=y,
                              source=PositionSource.MEASURED, confidence=1.0)

    def meccs(nev, kockak, fps=25.0):
        return Match(MatchMeta(match_id=nev, home_team="Hazai",
                               away_team="Vendég", fps=fps), kockak)

    hazai = [jatekos(i, Team.HOME, 25.0 + i, 3.0 * i) for i in range(1, 7)]
    vendeg = [jatekos(10 + i, Team.AWAY, 33.0, 3.0 * i) for i in range(1, 7)]
    mind = hazai + vendeg

    def allo_labda():
        return Ball(x=26.0, y=3.0, confidence=1.0)

    return {
        "ures": meccs("ures", []),
        "egy_kocka": meccs("egy", [Frame(t=0, players=mind,
                                         ball=allo_labda())]),
        "labda_nelkul": meccs("labdatlan", [
            Frame(t=t, players=mind, ball=None) for t in range(500)]),
        "jatekos_nelkul": meccs("jatekostalan", [
            Frame(t=t, players=[],
                  ball=Ball(x=20.0 + (t % 30) * 0.5, y=10.0, confidence=1.0))
            for t in range(500)]),
        "csak_a_hazai": meccs("csakhazai", [
            Frame(t=t, players=hazai, ball=allo_labda())
            for t in range(500)]),
        "csak_a_vendeg": meccs("csakvendeg", [
            Frame(t=t, players=vendeg,
                  ball=Ball(x=33.0, y=3.0, confidence=1.0))
            for t in range(500)]),
        "nulla_fps": meccs("nullafps", [
            Frame(t=t, players=mind, ball=allo_labda())
            for t in range(200)], fps=0.0),
        "hezagos_ido": meccs("hezagos", [
            Frame(t=t * 500, players=mind, ball=allo_labda())
            for t in range(100)]),
        "csupa_ures_kocka": meccs("szunet", [
            Frame(t=t, players=[], ball=None) for t in range(300)]),
    }


ELFAJULT_ESETEK = ("ures", "egy_kocka", "labda_nelkul", "jatekos_nelkul",
                   "csak_a_hazai", "csak_a_vendeg", "nulla_fps",
                   "hezagos_ido", "csupa_ures_kocka")


def test_az_elfajult_esetek_listaja_teljes():
    assert tuple(_elfajult_meccsek()) == ELFAJULT_ESETEK


@pytest.mark.parametrize("eset", ELFAJULT_ESETEK)
def test_a_feluletek_elfajult_meccsen_sem_szulnek_kivetelt(eset):
    """"Kevés minta → None" az ÖSSZES rétegre egyszerre, a valódi úton: a
    négy nagy felület (felderítés mindkét csapatra + meccsterv mindkét
    irányban + összevonás, összefoglaló, csapat- és egyéni edzés-fókusz)
    üres, egykockás, labda / játékos / egyik csapat nélküli, nulla
    képrátájú, hézagos idejű és csupa szünet-kockás meccsen is lefut —
    úgy, hogy a handball-kódban EGYETLEN kivétel sem születik (elnyelve
    sem). Aki nulla mintával oszt vagy üres listából választ, azt ez
    megfogja — akkor is, ha a try/except eltakarná."""
    from handball.models.tracking import Team
    from handball.pipeline.coach_summary import coach_summary
    from handball.pipeline.primitive_cache import primitive_cache
    from handball.pipeline.scouting import (combine_reports, matchup_plan,
                                            report_to_dict, scout_team)
    from handball.pipeline.training import (player_training_focus,
                                            training_focus)

    m = _elfajult_meccsek()[eset]
    eredmeny: dict = {}

    def felderites():
        with primitive_cache(m):
            h, a = scout_team(m, Team.HOME), scout_team(m, Team.AWAY)
            report_to_dict(h)
            matchup_plan(h, a)
            matchup_plan(a, h)
            combine_reports([h, h])

    def osszefoglalo():
        with primitive_cache(m):
            eredmeny["osszefoglalo"] = coach_summary(m)

    def edzes():
        with primitive_cache(m):
            eredmeny["fokusz"] = training_focus(m)
            player_training_focus(m)

    talalat = _elnyelt_kivetelek([felderites, osszefoglalo, edzes])
    assert not talalat, (
        f"kivétel született az elfajult meccsen ({eset}):\n" + "\n".join(
            f"  {n}× {tip} {fajl}:{sor} ({fv}) — {uz}"
            for (tip, fajl, sor, fv), (n, uz) in sorted(talalat.items())))
    # A válasz alakja ép: a hívó (API, kliens) ezekre a kulcsokra épít.
    assert set(eredmeny["fokusz"]) == {"home", "away"}
    assert isinstance(eredmeny["osszefoglalo"]["sections"], list)
    if eset in ("ures", "csupa_ures_kocka"):
        assert eredmeny["osszefoglalo"]["sections"] == []
        assert eredmeny["fokusz"] == {"home": [], "away": []}
