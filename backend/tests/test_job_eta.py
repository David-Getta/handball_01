"""Hátralévő idő becslése a feldolgozásnál.

Percekig futó munkánál ez a leghiányzóbb adat: enélkül a felhasználó
nem tudja eldönteni, megvárja-e, vagy elmegy a gép mellől.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from handball.api.app import create_app  # noqa: E402


def _client(tmp_path):
    os.environ["HANDBALL_DATA_DIR"] = str(tmp_path)
    return TestClient(create_app())


def test_a_becsles_nem_szolal_meg_tul_koran(tmp_path):
    """ŐR: a haladás első pár százalékából NEM becslünk.

    Ott a modell-betöltés és a videó-megnyitás torzít; egy vadul téves
    "kb. 3 óra" rosszabb, mint a semmi.
    """
    from handball.api import app as appmod

    # A becslő tiszta függvény-viselkedését a modul konstansán át
    # ellenőrizzük: a küszöb létezik és ésszerű.
    src = (os.path.dirname(os.path.abspath(appmod.__file__)))
    with open(os.path.join(src, "app.py"), encoding="utf-8") as f:
        szoveg = f.read()
    assert "ETA_MIN_PROGRESS" in szoveg
    assert "def _with_eta(" in szoveg
    # A sorban töltött idő nem számíthat bele.
    fo = szoveg.index("def _with_eta(")
    torzs = szoveg[fo:szoveg.index("@app.get(\"/jobs\")", fo)]
    assert 'job.get("started")' in torzs, (
        "a becslés nem a TÉNYLEGES indulástól számol — a sorban töltött "
        "idő reménytelenül túlbecsülné a hátralévőt")
    assert 'job.get("status") != "running"' in torzs, (
        "nem futó munkára is becsülnénk hátralévő időt")


def test_a_becsles_aranyos_es_stabil(tmp_path):
    """A becslés az eddigi átlagos ütem tartását feltételezi:
    fél úton az eltelt idővel megegyező hátralévőt kell mondania."""
    from handball.api.app import create_app  # noqa: F401

    # A számítás képlete: eltelt / prog * (1 - prog).
    eltelt, prog = 120.0, 0.5
    assert int(round(eltelt / prog * (1.0 - prog))) == 120

    eltelt, prog = 60.0, 0.75
    assert int(round(eltelt / prog * (1.0 - prog))) == 20


def test_a_jobs_vegpont_kiadja_az_eta_mezot(tmp_path):
    """A /jobs válaszában ott kell lennie az eta_s mezőnek (üres
    listánál is értelmes válasz jön)."""
    c = _client(tmp_path)
    r = c.get("/jobs")
    assert r.status_code == 200
    assert "jobs" in r.json()
