"""
ŐR: a felületek a forrás-rétegek LÉTEZŐ mezőit olvassák.

A recept szerint minden felület (összefoglaló-mondat, edzés-szabály,
felderítés-mező) `try/except`-ben ül, hogy egy réteg hibája ne vigye el
a többit. Ennek ára van: az elgépelt vagy elavult MEZŐNEVET is elnyeli —
a szabály ilyenkor némán sosem szólal meg, a tesztek pedig zöldek
maradnak. A szabályok jó része ráadásul egyetlen tesztben sem szólal
meg (a lefedettség-mérés szerint a közel ötszáz edzés-szabályból
mintegy kétszáz), tehát a mezőneveiket semmi sem ellenőrizte. A
`tests/test_nema_kivetelek.py` az elnyelt KIVÉTELT fogja meg — de csak
azon az ágon, amelyik le is fut.

Ez az őr nem várja meg, hogy a szabály megszólaljon. A forráskódból
(AST) kigyűjti, mely réteg-kimenet mely mezőit olvassa a felület
szögletes zárójellel — a csapat-rekordon (`x[side]["kulcs"]`),
beágyazott szótáron és lista-sorokon (`for sor in x["sorok"]:
sor["kulcs"]`) át —, aztán a VALÓDI réteget lefuttatja egy szimulált
meccsen, és megnézi, hogy a mező tényleg létezik-e a kimenetben.

Amit NEM néz (szándékosan):
  - a `.get()`-tel olvasott mezőt (az kimondva tűri a hiányt),
  - azt az ágat, ahol a szimulált meccsen nincs min ellenőrizni (None
    érték, üres lista, hibára futó réteg),
  - az `"available": False` (csonka) réteg-kimenetet — ott a felület
    maga is `.get("available")`-lel véd.
Ezek "nem ellenőrizhető" olvasások; a teszt alsó korlátot tart az
ELLENŐRZÖTT olvasások számára, hogy az őr ne üresedhessen ki csendben.

Futtatás:
    python -m pytest tests/test_mezonevek.py -q
"""

from __future__ import annotations

import ast
import dataclasses
import functools
import importlib
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

OLDAL, ELEM = "<oldal>", "<elem>"


# ---- Az elemző: mit olvas a felület a rétegek kimenetéből? ------------------

def _oldal_konstans(e) -> bool:
    return isinstance(e, ast.Constant) and e.value in ("home", "away")


class _Olvasasok(ast.NodeVisitor):
    """Forrás-sorrendben bejár egy függvényt, és összegyűjti, mely
    RÉTEG-kimenet (a `fn(match, …)` hívás eredménye) mely mezőit olvassa
    szögletes zárójellel. A változó-kötéseket sorrendben követi: az
    újra felhasznált név (`rec`) mindig az utolsó értékadását jelenti."""

    def __init__(self, importok: dict):
        self.importok = dict(importok)   # helyi név -> (modul, függvény)
        self.kot: dict = {}              # változó -> (réteg, út)
        self.oldal_nevek: set = set()    # "home"/"away"-on futó ciklusváltozók
        self.olvasas: list = []          # ((réteg, út), sor)

    # -- segédek
    def _reteg(self, v):
        if (isinstance(v, ast.Call) and isinstance(v.func, ast.Name)
                and v.func.id in self.importok and v.args
                and isinstance(v.args[0], ast.Name)
                and v.args[0].id == "match"):
            return self.importok[v.func.id]
        return None

    def _oldal_index(self, sl) -> bool:
        if isinstance(sl, ast.Name) and sl.id in self.oldal_nevek:
            return True
        if _oldal_konstans(sl):
            return True
        return (isinstance(sl, ast.Attribute) and sl.attr == "value"
                and isinstance(sl.value, ast.Name) and sl.value.id == "team")

    def _ut(self, e):
        """A kifejezés (réteg, út) alakja, vagy None, ha nem réteg-adat."""
        if isinstance(e, ast.Name):
            return self.kot.get(e.id)
        r = self._reteg(e)
        if r is not None:
            return (r, ())
        if isinstance(e, ast.Subscript):
            alap = self._ut(e.value)
            if alap is None:
                return None
            if self._oldal_index(e.slice):
                return (alap[0], alap[1] + (OLDAL,))
            if isinstance(e.slice, ast.Constant) \
                    and isinstance(e.slice.value, str):
                return (alap[0], alap[1] + (e.slice.value,))
        return None

    def _kot(self, cel, ut) -> None:
        if isinstance(cel, ast.Name):
            if ut is not None:
                self.kot[cel.id] = ut
            else:
                self.kot.pop(cel.id, None)
            self.oldal_nevek.discard(cel.id)
        elif isinstance(cel, (ast.Tuple, ast.List)):
            for c in cel.elts:
                self._kot(c, None)
        else:
            self.visit(cel)

    def _ciklus(self, cel, it) -> None:
        """A ciklusváltozó kötése: oldal-név, lista-elem vagy ismeretlen."""
        elemek = it.elts if isinstance(it, (ast.Tuple, ast.List)) else None
        if elemek and all(_oldal_konstans(x) for x in elemek):
            self._kot(cel, None)
            if isinstance(cel, ast.Name):
                self.oldal_nevek.add(cel.id)
            return
        if elemek and all(isinstance(x, ast.Tuple) and x.elts
                          and _oldal_konstans(x.elts[0]) for x in elemek):
            self._kot(cel, None)
            if isinstance(cel, ast.Tuple) and cel.elts \
                    and isinstance(cel.elts[0], ast.Name):
                self.oldal_nevek.add(cel.elts[0].id)
            return
        ut = self._ut(it)
        self._kot(cel, None if ut is None else (ut[0], ut[1] + (ELEM,)))

    # -- bejárás
    def visit_ImportFrom(self, node):
        if node.level == 1 and node.module:
            for a in node.names:
                self.importok[a.asname or a.name] = (node.module, a.name)

    def visit_Assign(self, node):
        self.visit(node.value)
        ut = self._ut(node.value)
        for cel in node.targets:
            self._kot(cel, ut)

    def visit_For(self, node):
        self.visit(node.iter)
        self._ciklus(node.target, node.iter)
        for s in node.body + node.orelse:
            self.visit(s)

    def _comp(self, node, elemek):
        for g in node.generators:
            self.visit(g.iter)
            self._ciklus(g.target, g.iter)
            for felt in g.ifs:
                self.visit(felt)
        for e in elemek:
            self.visit(e)

    def visit_ListComp(self, node):
        self._comp(node, [node.elt])

    visit_SetComp = visit_GeneratorExp = visit_ListComp

    def visit_DictComp(self, node):
        self._comp(node, [node.key, node.value])

    def _fuggveny(self, node, torzs):
        # A belső függvény paraméterei eltakarják a külső kötéseket.
        regi = dict(self.kot)
        for a in node.args.args + node.args.kwonlyargs:
            self.kot.pop(a.arg, None)
        for s in torzs:
            self.visit(s)
        self.kot = regi

    def visit_FunctionDef(self, node):
        self._fuggveny(node, node.body)

    def visit_Lambda(self, node):
        self._fuggveny(node, [node.body])

    def visit_Subscript(self, node):
        ut = self._ut(node)
        if ut is not None and ut[1] and ut[1][-1] not in (OLDAL, ELEM):
            self.olvasas.append((ut, node.lineno))
        self.generic_visit(node)


def _letezik(ertek, ut):
    """True: az út létezik a valódi kimenetben; False: egy kulcs HIÁNYZIK
    egy szótárból; None: nem ellenőrizhető (None érték, üres lista, nem
    szótár, vagy `"available": False` csonka kimenet)."""
    if not ut:
        return True
    lepes, maradek = ut[0], ut[1:]
    if lepes == OLDAL:
        if not (isinstance(ertek, dict)
                and ("home" in ertek or "away" in ertek)):
            return None
        agak = [_letezik(ertek[s], maradek) for s in ("home", "away")
                if s in ertek]
    elif lepes == ELEM:
        if not isinstance(ertek, (list, tuple)) or not ertek:
            return None
        agak = [_letezik(e, maradek) for e in ertek[:8]]
    else:
        if not isinstance(ertek, dict):
            return None
        if lepes not in ertek:
            return None if ertek.get("available") is False else False
        return _letezik(ertek[lepes], maradek)
    if True in agak:
        return True
    return False if False in agak else None


def _felulet_olvasasai(forras: str, fuggvenyek=None) -> dict:
    """{(réteg, út): [(függvény, sor), …]} a forrás megadott (vagy összes)
    felső szintű függvényéből."""
    fa = ast.parse(forras)
    alap: dict = {}
    for node in fa.body:
        if isinstance(node, ast.ImportFrom) and node.level == 1 \
                and node.module:
            for a in node.names:
                alap[a.asname or a.name] = (node.module, a.name)
    ki: dict = {}
    for fn in fa.body:
        if not isinstance(fn, ast.FunctionDef):
            continue
        if fuggvenyek is not None and fn.name not in fuggvenyek:
            continue
        v = _Olvasasok(alap)
        for s in fn.body:
            v.visit(s)
        for kulcs, sor in v.olvasas:
            ki.setdefault(kulcs, []).append((fn.name, sor))
    return ki


def _ellenoriz(olvasasok: dict, meccs, tar: dict):
    """(ellenőrzött, nem ellenőrizhető, hiányzó-lista) a VALÓDI rétegekkel.
    A `tar` a réteg-kimenetek tára (egy réteg egyszer fut)."""
    jo = nem = 0
    hianyzik = []
    for (reteg, ut), hol in sorted(olvasasok.items(),
                                   key=lambda kv: kv[1][0][1]):
        if reteg not in tar:
            try:
                fv = getattr(importlib.import_module(
                    f"handball.pipeline.{reteg[0]}"), reteg[1])
                tar[reteg] = fv(meccs)
            except Exception as e:  # a réteg hibája nem ennek az őrnek a dolga
                tar[reteg] = e
        ertek = tar[reteg]
        allapot = None if isinstance(ertek, Exception) \
            else _letezik(ertek, ut)
        if allapot is True:
            jo += 1
        elif allapot is False:
            fn, sor = hol[0]
            hianyzik.append(
                f"{fn} ({sor}. sor): a {reteg[0]}.{reteg[1]} kimenetében "
                "nincs ilyen mező: "
                + " → ".join(str(k) for k in ut))
        else:
            nem += 1
    return jo, nem, hianyzik


# ---- A valódi meccs és a réteg-kimenetek (egyszer számolva) -----------------

@functools.lru_cache(maxsize=1)
def _meccs():
    """Szimulált meccs lövésekkel és félidővel — a rétegek nagy része
    ezen már érdemi (nem üres) kimenetet ad."""
    from handball.sim.match_simulator import simulate_ground_truth

    return simulate_ground_truth(duration_s=120, fps=25.0, seed=1,
                                 shots_per_min=8, halftime_break_s=10)


_RETEG_TAR: dict = {}


def _modul_ellenorzes(modulnev: str):
    from handball.pipeline.primitive_cache import primitive_cache

    modul = importlib.import_module(f"handball.pipeline.{modulnev}")
    olvasasok = _felulet_olvasasai(
        Path(modul.__file__).read_text(encoding="utf-8"))
    meccs = _meccs()
    with primitive_cache(meccs):
        return _ellenoriz(olvasasok, meccs, _RETEG_TAR)


# A négy nagy felület és az ELLENŐRZÖTT olvasások alsó korlátja (a
# mostani szám kb. háromnegyede: új réteggel csak nő; ha ez alá esik,
# az elemző vagy a szimulált meccs romlott el — nem a felület javult).
_FELULETEK = [
    ("training", 850),        # edzés-fókusz: a sorszámozott szabályok
    ("coach_summary", 1000),  # edzői összefoglaló: a szakasz-mondatok
    ("scouting", 850),        # felderítés: a jelentés-mezők kitöltése
    ("report_html", 70),      # a nyomtatható meccs-jelentés
]


@pytest.mark.parametrize("modulnev, minimum", _FELULETEK)
def test_a_felulet_a_retegek_letezo_mezoit_olvassa(modulnev, minimum):
    """A felület minden szögletes zárójeles mező-olvasása létező mezőre
    mutat a VALÓDI réteg kimenetében — azokon az ágakon is, amelyek
    egyetlen tesztben sem szólalnak meg. Hiányzó mező = elgépelt vagy
    elavult név, amit a try/except némán elnyelne."""
    jo, nem, hianyzik = _modul_ellenorzes(modulnev)
    assert not hianyzik, (
        f"{modulnev}: {len(hianyzik)} mező-olvasás nem létező mezőre "
        "mutat:\n  " + "\n  ".join(hianyzik[:25]))
    assert jo >= minimum, (
        f"{modulnev}: csak {jo} olvasást sikerült ellenőrizni ({nem} nem "
        f"ellenőrizhető) — az őr kiüresedett (elvárt: legalább {minimum})")
    # A nagy többség ellenőrizhető: a szimulált meccs elég gazdag.
    assert jo >= 3 * nem, (modulnev, jo, nem)


def _jelentes_parameter(arg) -> bool:
    """A paraméter egy felderítő jelentés-e (az annotációja szerint)."""
    if arg.annotation is None:
        return False
    tipus = ast.unparse(arg.annotation)
    return ("ScoutingReport" in tipus and "list" not in tipus.lower()
            and "dict" not in tipus.lower())


def test_a_felderito_jelentes_mezoi_leteznek():
    """Aki felderítő jelentést olvas (az edzői kulcsok, a meccsterv, az
    összegzés, a kivonatok, a nyomtatható lap), az a jelentés LÉTEZŐ
    mezőit olvassa: a `rep.` / `own.` / `opp.` (vagy a ScoutingReport
    típusú paraméter) után álló név a ScoutingReport mezője vagy tagja.
    Az elgépelt mezőnév AttributeError lenne — a try/except elnyelné, és
    a szabály némán sosem szólalna meg."""
    import handball
    from handball.pipeline import scouting

    ismert = ({f.name for f in dataclasses.fields(scouting.ScoutingReport)}
              | set(dir(scouting.ScoutingReport)))
    osszes, rossz, modulok = 0, [], set()
    for ut in sorted(Path(handball.__file__).parent.rglob("*.py")):
        fa = ast.parse(ut.read_text(encoding="utf-8"))
        for fn in [n for n in ast.walk(fa)
                   if isinstance(n, ast.FunctionDef)]:
            jelentesek = {a.arg for a in fn.args.args
                          if _jelentes_parameter(a)}
            if ut.name == "scouting.py":
                jelentesek |= ({a.arg for a in fn.args.args}
                               & {"rep", "own", "opp"})
            for node in ast.walk(fn) if jelentesek else ():
                if (isinstance(node, ast.Attribute)
                        and isinstance(node.value, ast.Name)
                        and node.value.id in jelentesek):
                    osszes += 1
                    modulok.add(ut.name)
                    if node.attr not in ismert:
                        rossz.append(f"{ut.name}: {fn.name} "
                                     f"({node.lineno}. sor): "
                                     f"{node.value.id}.{node.attr}")
    assert not rossz, ("nem létező jelentés-mező:\n  "
                       + "\n  ".join(rossz[:25]))
    assert osszes >= 4000, osszes        # az őr tényleg a felületet nézi
    assert {"scouting.py", "report_html.py"} <= modulok


def test_az_or_megfogja_a_nem_letezo_jelentes_mezot():
    """Ön-teszt: a jelentés-mezők halmaza tényleg szűr — egy valódi mező
    benne van, egy elgépelt nincs (különben az őr mindig zöld lenne)."""
    from handball.pipeline import scouting

    ismert = ({f.name for f in dataclasses.fields(scouting.ScoutingReport)}
              | set(dir(scouting.ScoutingReport)))
    assert {"team_name", "keys_to_game", "lsp_lovo_minta",
            "sit_decisions"} <= ismert
    assert "team_nev" not in ismert and "kulcsok" not in ismert
    fa = ast.parse("def f(rep: 'ScoutingReport', masik: list): pass")
    parameterek = fa.body[0].args.args
    assert _jelentes_parameter(parameterek[0])
    assert not _jelentes_parameter(parameterek[1])
    lista = ast.parse("def f(reports: list[ScoutingReport]): pass")
    assert not _jelentes_parameter(lista.body[0].args.args[0])


# ---- Az elemző ön-tesztje: megfogja-e, amit meg kell? -----------------------

def _proba(forras: str):
    """Egy próba-felület (forrás-szöveg) ellenőrzése a valódi rétegekkel."""
    from handball.pipeline.primitive_cache import primitive_cache

    meccs = _meccs()
    with primitive_cache(meccs):
        return _ellenoriz(_felulet_olvasasai(forras), meccs, _RETEG_TAR)


def test_az_or_megfogja_az_elavult_mezonevet_a_csapat_rekordban():
    """Elgépelt kulcs a csapat-rekordban és a beágyazott szótárban: az
    őr megnevezi a függvényt, a sort, a réteget és a mezőt — a jó
    olvasások mellett is."""
    jo, nem, hianyzik = _proba('''
def proba_szabaly(match, config=None):
    try:
        from .stats import possession_share
        ps = possession_share(match)
        for side in ("home", "away"):
            rec = ps[side]
            if rec["pct"] > 60.0:                 # létező mező
                szoveg = f"{rec['szazalek']:.0f}%"  # ELGÉPELT mező
    except Exception:
        pass
''')
    assert jo == 1 and nem == 0
    assert hianyzik == [
        "proba_szabaly (9. sor): a stats.possession_share kimenetében "
        "nincs ilyen mező: <oldal> → szazalek"]


def test_az_or_megfogja_az_elavult_mezonevet_a_lista_sorokban():
    """A CLAUDE.md-ben leírt eset: a `match_xg` lövő-sorai nem
    tartalmaznak `jersey` mezőt — a lista-sorokon át olvasott elavult
    nevet is megfogja (ciklusban és listaképzőben is)."""
    from handball.pipeline.xg import match_xg

    assert match_xg(_meccs())["shooters"]         # a próba-meccsen van lövő
    jo, nem, hianyzik = _proba('''
def proba_mondat(match):
    from .xg import match_xg
    r_all = match_xg(match)
    for sor in r_all["shooters"]:
        if sor["shots"] >= 3:                     # létező mező
            nev = sor["jersey"]                   # NINCS ilyen mező
    golok = [s["goals"] for s in r_all["shooters"] if s["mezszam"]]
''')
    assert jo == 3                                # shooters, shots, goals
    assert len(hianyzik) == 2
    assert "<elem> → jersey" in hianyzik[0] and "(7. sor)" in hianyzik[0]
    assert "<elem> → mezszam" in hianyzik[1]


def test_az_or_nem_riaszt_ahol_nincs_min_ellenorizni():
    """Nem ellenőrizhető (és nem hiba): a `.get()`-tel olvasott mező, a
    hibára futó réteg, a nem réteg-adat, és az `"available": False`
    csonka kimenet mögötti kulcs."""
    from handball.pipeline.attack_types import match_pace

    assert match_pace(_meccs()).get("available") is False   # rövid a meccs
    jo, nem, hianyzik = _proba('''
def proba_felulet(match, sajat):
    from .attack_types import match_pace
    from .play_simulation import defense_test
    pc = match_pace(match)
    if pc.get("available"):
        szoveg = pc["label"]                 # csonka kimenet: nem riaszt
    dt = defense_test(match)                 # így hívva hibázik
    x = dt["home"]["verdict"]
    y = sajat["akarmi"]["mas"]               # nem réteg-adat
    z = pc.get("nincs_ilyen")                # .get(): tűri a hiányt
''')
    assert hianyzik == []
    assert jo == 0 and nem == 2               # a label és a verdict


def test_az_or_a_valtozo_utolso_ertekadasat_koveti():
    """Az újra felhasznált változónév (`rec`) mindig az UTOLSÓ
    értékadását jelenti: a második réteg mezőjét a második rétegen
    ellenőrzi — a belső függvény paramétere pedig eltakarja a külsőt."""
    jo, nem, hianyzik = _proba('''
def proba_ket_reteg(match):
    from .stats import possession_share
    from .xg import match_xg
    rec = possession_share(match)["home"]
    a = rec["pct"]                            # az első rétegé: létezik
    rec = match_xg(match)["teams"]["home"]
    b = rec["xg"]                             # a másodiké: létezik
    c = rec["pct"]                            # a másodikban NINCS

    def belso(rec):
        return rec["barmi"]                   # paraméter: nem réteg-adat
''')
    assert jo == 3                            # pct, teams → xg (2 út)
    assert len(hianyzik) == 1
    assert "xg.match_xg" in hianyzik[0] and "→ pct" in hianyzik[0]


def test_letezik_az_ut_a_valodi_kimenetben():
    """Az út-ellenőrzés három válasza: létezik (True), egy kulcs
    hiányzik (False), nem ellenőrizhető (None) — oldalanként és
    lista-elemenként elég, ha EGY helyen megvan."""
    ki = {"home": {"n": 3, "top": {"id": 7}, "rows": [{"a": 1}, {"b": 2}]},
          "away": {"n": 0, "top": None, "rows": []}}
    assert _letezik(ki, (OLDAL, "n")) is True
    assert _letezik(ki, (OLDAL, "top", "id")) is True       # a hazain megvan
    assert _letezik(ki, (OLDAL, "nincs")) is False
    assert _letezik(ki, (OLDAL, "top", "nincs")) is False
    assert _letezik(ki, (OLDAL, "rows", ELEM, "b")) is True  # a 2. sorban
    assert _letezik(ki, (OLDAL, "rows", ELEM, "c")) is False
    assert _letezik({"home": {"top": None}}, (OLDAL, "top", "id")) is None
    assert _letezik({"home": {"rows": []}}, (OLDAL, "rows", ELEM, "a")) \
        is None
    assert _letezik([1, 2], (OLDAL, "n")) is None           # nem oldal-szótár
    assert _letezik({"available": False}, ("label",)) is None
    assert _letezik({"available": True}, ("label",)) is False
    assert _letezik(ki, ()) is True
