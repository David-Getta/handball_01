"""
Tesztek a réteg-katalógus szkriptjére (scripts/layer_catalog.py).

A csomag eddig csak a GENERÁLT fájlt őrizte (test_layer_registry); a
generátor függvényei (a regisztráció kiolvasása, a réteg megkeresése, a
katalógus építése, a main író és ellenőrző módja) egyszer sem futottak.
A kis próbák a tmp mappában dolgoznak — a valódi katalógust a teszt nem
írja át.

Futtatás:
    python -m pytest tests/test_layer_catalog.py -q
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import layer_catalog as lc  # noqa: E402

_PROBA_APP = '''
    _layer("xg", lambda: match_xg(match))
    _layer("positions",
           lambda: roles.estimate_positions(match))
    _layer("wall_gaps", lambda: wall_gaps(match, config))
    _layer("osszetett", lambda: {"a": helper(match)})
    _layer(  "docstring_nelkul", lambda: docstring_nelkul(match))
'''

_PROBA_XG = '''
def match_xg(match, config=None):
    """A meccs minden lövésének helyzetminősége   + csapat-összegzés.

    Hosszabb leírás, ami már nem kerül a katalógusba.
    """
    return {}
'''

_PROBA_DEFENSE = '''
def wall_gaps(match, config=None) -> dict:
    """Fal-rés: mekkora réseket hagy a rendezett védőfal."""
    return {}
'''

_PROBA_ROLES = '''
def estimate_positions(match):
    """Poszt-becslés a támadó-fázis átlag-pozícióiból.
    """
    return {}
'''

_PROBA_Z = '''
def docstring_nelkul(match):
    return {}
'''


def _proba_kodbazis(tmp_path, monkeypatch):
    """Próba app + pipeline a tmp mappában, a szkript arra mutat."""
    pipeline = tmp_path / "pipeline"
    pipeline.mkdir()
    (pipeline / "xg.py").write_text(_PROBA_XG, encoding="utf-8")
    (pipeline / "defense.py").write_text(_PROBA_DEFENSE, encoding="utf-8")
    (pipeline / "roles.py").write_text(_PROBA_ROLES, encoding="utf-8")
    (pipeline / "zzz.py").write_text(_PROBA_Z, encoding="utf-8")
    app = tmp_path / "app.py"
    app.write_text(_PROBA_APP, encoding="utf-8")
    ki = tmp_path / "docs" / "RETEG_KATALOGUS.md"
    ki.parent.mkdir()
    monkeypatch.setattr(lc, "_APP", app)
    monkeypatch.setattr(lc, "_PIPELINE", pipeline)
    monkeypatch.setattr(lc, "_OUT", ki)
    return ki


def test_registered_layers_a_hivott_fuggvenyt_adja(tmp_path, monkeypatch):
    """A regisztrációból a réteg neve és a lambda által HÍVOTT függvény
    jön (álnévnél a hívott a mérvadó, modul-előtag nélkül, több sorba
    tört regisztrációnál is); amit a minta nem ismer fel (összetett
    lambda), az a saját nevén szerepel."""
    _proba_kodbazis(tmp_path, monkeypatch)
    assert lc._registered_layers() == {
        "xg": "match_xg", "positions": "estimate_positions",
        "wall_gaps": "wall_gaps", "osszetett": "osszetett",
        "docstring_nelkul": "docstring_nelkul"}


def test_registered_layers_regisztracio_nelkul_ures(tmp_path, monkeypatch):
    """Regisztráció nélküli forrásból üres szótár jön (nem kivétel)."""
    _proba_kodbazis(tmp_path, monkeypatch)
    lc._APP.write_text("def create_app():\n    return None\n",
                       encoding="utf-8")
    assert lc._registered_layers() == {}


def test_find_layer_modul_es_a_docstring_elso_sora(tmp_path, monkeypatch):
    """A réteg-függvény modulja és a docstringjének ELSŐ sora (egysoros
    és többsoros docstringnél is, típus-annotált fejlécnél is)."""
    _proba_kodbazis(tmp_path, monkeypatch)
    assert lc._find_layer("match_xg") == (
        "xg", "A meccs minden lövésének helyzetminősége   + "
              "csapat-összegzés.")
    assert lc._find_layer("wall_gaps") == (
        "defense", "Fal-rés: mekkora réseket hagy a rendezett védőfal.")
    assert lc._find_layer("estimate_positions") == (
        "roles", "Poszt-becslés a támadó-fázis átlag-pozícióiból.")


def test_find_layer_docstring_vagy_fuggveny_nelkul(tmp_path, monkeypatch):
    """Docstring nélküli függvénynél a leírás "—" (nem kitalált szöveg);
    ha nincs ilyen önálló pipeline-függvény (összetett / beágyazott
    réteg), a modul az api/app.py."""
    _proba_kodbazis(tmp_path, monkeypatch)
    assert lc._find_layer("docstring_nelkul") == ("zzz", "—")
    assert lc._find_layer("osszetett") == (
        "api/app.py", "— (összetett/beágyazott réteg)")
    # A név ELEJE nem elég: a "match" nem a "match_xg".
    assert lc._find_layer("match")[0] == "api/app.py"


def test_build_catalog_modulonkent_csoportosit_es_szamol(tmp_path,
                                                         monkeypatch):
    """A katalógus fejléce az összes réteg számát mondja; a rétegek
    modulonként (névsorban, darabszámmal), azon belül névsorban állnak,
    a leírás szóközei egyre szűkítve; a fájl egy sortöréssel zárul."""
    _proba_kodbazis(tmp_path, monkeypatch)
    szoveg = lc.build_catalog()
    assert szoveg.startswith(
        "# Réteg-katalógus — a meccs-csomag regisztrált elemző rétegei\n")
    assert "Összesen **5 réteg**, modulonként csoportosítva" in szoveg
    fejlecek = [s for s in szoveg.splitlines() if s.startswith("## ")]
    assert fejlecek == ["## api/app.py (1)", "## defense (1)",
                        "## roles (1)", "## xg (1)", "## zzz (1)"]
    assert ("| `xg` | A meccs minden lövésének helyzetminősége + "
            "csapat-összegzés. |") in szoveg
    assert "| `positions` | Poszt-becslés a támadó-fázis " \
           "átlag-pozícióiból. |" in szoveg
    assert "| `osszetett` | — (összetett/beágyazott réteg) |" in szoveg
    assert "| `docstring_nelkul` | — |" in szoveg
    assert szoveg.count("| `") == 5
    assert szoveg.endswith("|\n") and not szoveg.endswith("\n\n")
    assert lc.build_catalog() == szoveg          # determinisztikus


def test_build_catalog_egy_modul_tobb_retege_nevsorban(tmp_path,
                                                       monkeypatch):
    """Egy modul több rétege egy szakaszba kerül, a RÉTEG neve szerint
    rendezve (nem a regisztráció sorrendjében)."""
    _proba_kodbazis(tmp_path, monkeypatch)
    lc._APP.write_text(
        '_layer("zeta", lambda: match_xg(match))\n'
        '_layer("alfa", lambda: match_xg(match))\n', encoding="utf-8")
    szoveg = lc.build_catalog()
    assert "## xg (2)" in szoveg
    assert szoveg.index("| `alfa` |") < szoveg.index("| `zeta` |")
    assert "Összesen **2 réteg**" in szoveg


def test_build_catalog_reteg_nelkul_csak_fejlec(tmp_path, monkeypatch):
    """Regisztrált réteg nélkül a katalógus csak a fejléc: 0 réteg,
    modul-szakasz nélkül."""
    _proba_kodbazis(tmp_path, monkeypatch)
    lc._APP.write_text("", encoding="utf-8")
    szoveg = lc.build_catalog()
    assert "Összesen **0 réteg**" in szoveg
    assert "## " not in szoveg and "| `" not in szoveg


def test_main_megirja_a_katalogust_es_a_check_zold(tmp_path, monkeypatch,
                                                   capsys):
    """Író módban a main megírja a fájlt és kimondja a réteg-számot;
    utána az ellenőrző mód (--check) zöld, és nem ír."""
    ki = _proba_kodbazis(tmp_path, monkeypatch)
    assert lc.main([]) == 0
    assert ki.read_text(encoding="utf-8") == lc.build_catalog()
    assert f"Katalógus kiírva: {ki} (5 réteg)" in capsys.readouterr().out

    elotte = ki.stat().st_mtime_ns
    assert lc.main(["--check"]) == 0
    assert "A katalógus friss." in capsys.readouterr().out
    assert ki.stat().st_mtime_ns == elotte


def test_main_check_elavult_vagy_hianyzo_katalogusnal_1_es_kod(
        tmp_path, monkeypatch, capsys):
    """Az ellenőrző mód hiányzó vagy elavult katalógusnál 1-gyel tér
    vissza, a teendővel — és NEM javít (az őr dolga jelezni)."""
    ki = _proba_kodbazis(tmp_path, monkeypatch)
    assert lc.main(["--check"]) == 1
    assert "a katalógus elavult — futtasd: python -m scripts.layer_catalog" \
        in capsys.readouterr().err
    assert not ki.exists()

    lc.main([])
    capsys.readouterr()
    # Új réteg kerül a regisztrációba → a beírt katalógus elavul.
    lc._APP.write_text(_PROBA_APP + '    _layer("uj", lambda: match_xg(m))\n',
                       encoding="utf-8")
    regi = ki.read_text(encoding="utf-8")
    assert lc.main(["--check"]) == 1
    assert "elavult" in capsys.readouterr().err
    assert ki.read_text(encoding="utf-8") == regi


def test_a_valodi_regisztraciobol_es_katalogusbol():
    """A VALÓDI kódbázison: az 500+ réteg kiolvasható, az álnevek a
    hívott függvényre mutatnak, a réteg-függvény megtalálható a
    moduljában, és a beírt katalógus pontosan a generátor kimenete."""
    retegek = lc._registered_layers()
    assert len(retegek) >= 500
    assert retegek["xg"] == "match_xg"
    assert retegek["coach_summary"] == "coach_summary"
    modul, leiras = lc._find_layer("match_xg")
    assert modul == "xg" and leiras and leiras != "—"
    assert lc._OUT.read_text(encoding="utf-8") == lc.build_catalog()
