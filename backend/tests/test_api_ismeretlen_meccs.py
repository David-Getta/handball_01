"""
ŐR: az API ismeretlen meccsre és üres könyvtáron sem ad 500-at.

Két általános szerződés, amelyet az alkalmazás MINDEN útvonalán végig-
nézünk (az útvonalakat a FastAPI-tól kérdezzük le, tehát az új végpont
magától bekerül az őrbe):

1. ISMERETLEN MECCS: minden meccs-szintű útvonal (`/matches/{match_id}/…`,
   minden módszerrel) nem létező azonosítóra beszélő 404-et ad — nem
   500-at, és az író végpont nem hoz létre adatot egy nem létező
   meccshez. A kliens a 404-ből tudja megmondani, hogy "ezt a meccset
   törölték / még nincs feldolgozva"; az 500 "a motor hibás" lenne.
2. ÜRES KÖNYVTÁR: frissen telepített gépen (egyetlen meccs nélkül)
   egyik lekérdező (GET) útvonal sem ad szerver-hibát — akkor sem, ha az
   azonosítója nem létezik.

A végpontok "nincs ilyen meccs" ága jellemzően egy-két sor, amelyet
külön teszt ritkán jár be; a lefedettség-mérésben ezek az apró, soha le
nem futó ágak adták az API hézagainak nagy részét.

Futtatás:
    python -m pytest tests/test_api_ismeretlen_meccs.py -q
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

pytest.importorskip("fastapi")

from fastapi.routing import APIRoute  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

ISMERETLEN = "nincs-ilyen-meccs"

# Kivételek az 1. szerződés alól — mindegyik INDOKKAL. A közös nézés
# állapota nem a meccs-tárban él: a követő a vezető ELŐTT is kérdezhet
# ("nincs vezető" a válasz), a leállítás pedig ismételhető.
KIVETELEK = {
    ("GET", "/matches/{match_id}/shared3d"),
    ("DELETE", "/matches/{match_id}/shared3d"),
}


@pytest.fixture
def kliens(tmp_path, monkeypatch):
    """Friss motor üres adatmappával; a szerver-oldali kivétel 500-as
    válasz lesz (nem a tesztbe dobódik), hogy az útvonalat megnevezhessük."""
    from handball.api.app import create_app

    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("HANDBALL_HOST", raising=False)
    app = create_app()
    return app, TestClient(app, raise_server_exceptions=False)


def _kitoltott(route):
    """Az útvonal kitöltve: a meccs-azonosító helyén a nem létező
    azonosító, a többi path-paraméter helyén "1" (szám-típusúnak is
    érvényes, hogy a kérés a keresésig eljusson), és a KÖTELEZŐ
    lekérdezés-paraméterek egy semleges értékkel."""
    ut = route.path
    for p in route.dependant.path_params:
        ertek = ISMERETLEN if p.name == "match_id" else "1"
        ut = ut.replace("{" + p.name + "}", ertek)
        ut = ut.replace("{" + p.name + ":path}", ertek)
    parameterek = {p.name: "1" for p in route.dependant.query_params
                   if p.field_info.is_required()}
    return ut, parameterek


def _utvonalak(app):
    return [r for r in app.routes if isinstance(r, APIRoute)]


def test_ismeretlen_meccsre_minden_meccs_szintu_vegpont_404(kliens):
    """Nem létező meccs-azonosítóra minden meccs-szintű útvonal 404-et ad
    beszélő üzenettel. Az író végpontnál a kérés-ellenőrzés (422)
    megelőzheti a keresést — de sikeres (2xx) válasz és szerver-hiba
    (5xx) sosem jöhet."""
    app, c = kliens
    hibak, vizsgalt = [], 0
    for r in _utvonalak(app):
        if "{match_id}" not in r.path:
            continue
        for modszer in sorted(r.methods - {"HEAD", "OPTIONS"}):
            if (modszer, r.path) in KIVETELEK:
                continue
            ut, parameterek = _kitoltott(r)
            valasz = c.request(modszer, ut, params=parameterek,
                               **({} if modszer in ("GET", "DELETE")
                                  else {"json": {}}))
            vizsgalt += 1
            elfogadott = (404,) if modszer == "GET" else (404, 422)
            if valasz.status_code not in elfogadott:
                hibak.append(f"{modszer} {r.path} → {valasz.status_code}")
                continue
            if valasz.status_code == 404:
                uzenet = valasz.json().get("detail")
                if not (isinstance(uzenet, str) and uzenet.strip()):
                    hibak.append(f"{modszer} {r.path} → 404 üzenet nélkül")
    assert not hibak, ("ismeretlen meccsre nem 404:\n  "
                       + "\n  ".join(hibak))
    assert vizsgalt >= 100, vizsgalt     # az őr tényleg az API-t járja be


def test_a_kivetelek_tenyleg_leteznek_es_ugy_viselkednek(kliens):
    """A kivétel-lista nem rejthet el hibát: minden kivétel létező
    útvonal, és ismeretlen meccsre a leírt, ártalmatlan választ adja (a
    közös nézés: "nincs vezető"; a leállítás: rendben)."""
    app, c = kliens
    letezo = {(m, r.path) for r in _utvonalak(app) for m in r.methods}
    assert KIVETELEK <= letezo
    allapot = c.get(f"/matches/{ISMERETLEN}/shared3d")
    assert allapot.status_code == 200
    assert allapot.json()["active"] is False
    assert c.delete(f"/matches/{ISMERETLEN}/shared3d").json() == {"ok": True}
    # A vezető állapotát viszont nem létező meccsre nem lehet beírni.
    assert c.put(f"/matches/{ISMERETLEN}/shared3d",
                 json={"t": 1.0}).status_code == 404
    # ...és a kérdezés sem hozott létre állapotot.
    assert c.get(f"/matches/{ISMERETLEN}/shared3d").json()["active"] is False


def test_ures_konyvtaron_egyik_lekerdezo_vegpont_sem_ad_szerver_hibat(
        kliens):
    """Frissen telepített gépen (nincs meccs, nincs fiók, nincs jegyzet)
    minden GET útvonal 5xx nélkül válaszol — nem létező azonosítóval és
    semleges kötelező paraméterekkel is."""
    app, c = kliens
    hibak, vizsgalt, kodok = [], 0, set()
    for r in _utvonalak(app):
        if "GET" not in r.methods:
            continue
        ut, parameterek = _kitoltott(r)
        valasz = c.get(ut, params=parameterek, follow_redirects=False)
        vizsgalt += 1
        kodok.add(valasz.status_code)
        if valasz.status_code >= 500:
            hibak.append(f"GET {r.path} → {valasz.status_code}: "
                         f"{valasz.text[:120]}")
    assert not hibak, ("szerver-hiba üres könyvtáron:\n  "
                       + "\n  ".join(hibak))
    assert vizsgalt >= 120, vizsgalt
    # Az üres könyvtár nem "minden 404": a lista-végpontok üres listával
    # válaszolnak (200).
    assert 200 in kodok and 404 in kodok


def test_a_kitoltes_a_path_es_a_kotelezo_parametereket_kezeli(kliens):
    """Ön-teszt: az útvonal-kitöltő minden path-paramétert behelyettesít
    (nem marad kapcsos zárójel), és csak a KÖTELEZŐ lekérdezés-
    paramétereket tölti ki."""
    app, _ = kliens
    tobb_parameteres = 0
    for r in _utvonalak(app):
        ut, parameterek = _kitoltott(r)
        assert "{" not in ut and "}" not in ut, r.path
        kotelezo = {p.name for p in r.dependant.query_params
                    if p.field_info.is_required()}
        assert set(parameterek) == kotelezo, r.path
        if len(r.dependant.path_params) >= 2:
            tobb_parameteres += 1
    assert tobb_parameteres >= 5          # van, ahol két azonosító is kell
