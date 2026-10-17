"""
Tesztek a KALIBRÁCIÓ ÁTVÉTELÉRE (GET /calibration/saved).

Aki telefonnal vagy fényképezőgéppel vesz fel, darabokban kapja a
meccset: hat klip UGYANARRÓL a rögzített kameráról. A kalibráció a
videó FÁJLNEVÉHEZ van kötve, tehát eddig mind a hatot külön kellett
bejelölni — huszonnégy sarok-kattintás ugyanarra a pályára, holott a
kamera meg sem mozdult.

Az átvétel CSAK akkor helyes, ha a kamera tényleg nem mozdult; ezt a
program nem tudja eldönteni, tehát a FELÜLET mondja ki. A végpont
feladata annyi, hogy megmutassa, mi van, és ne kínálja fel a saját
kalibrációját átvételre.

Futtatás:
    python -m pytest tests/test_kalibracio_atvetel.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient

_SAROK = [[10, 20], [900, 25], [950, 700], [5, 690]]


def _client():
    os.environ["HANDBALL_DATA_DIR"] = tempfile.mkdtemp(prefix="hb_calib_")
    from handball.api.app import create_app
    return TestClient(create_app())


def _ment(c, path, n=1):
    calibs = [{"corners": _SAROK, "region": "full", "rotate": False,
               "frame": 0} for _ in range(n)]
    r = c.post("/calibration", json={"path": path, "calibs": calibs})
    assert r.status_code == 200


def test_ures_listaval_indul():
    c = _client()
    assert c.get("/calibration/saved").json()["items"] == []


def test_a_mentett_kalibraciok_atvehetok():
    c = _client()
    _ment(c, "/videok/elso_resz.mp4")
    _ment(c, "/videok/masodik_resz.mp4", n=2)
    tetelek = c.get("/calibration/saved").json()["items"]
    assert len(tetelek) == 2
    nevek = {t["video"] for t in tetelek}
    assert "elso_resz.mp4" in nevek and "masodik_resz.mp4" in nevek
    # A SAROKPONTOK is jönnek: az átvételhez nem kell külön kérés.
    for t in tetelek:
        assert t["calibs"][0]["corners"] == _SAROK
        assert t["count"] == len(t["calibs"])


def test_a_sajat_kalibraciot_nem_kinaljuk_atvetelre():
    """Aki a második klipnél áll, ne kapja fel önmagát a listán — az
    értelmetlen választás, és elrejti a valódit."""
    c = _client()
    _ment(c, "/videok/elso_resz.mp4")
    _ment(c, "/videok/masodik_resz.mp4")
    tetelek = c.get("/calibration/saved",
                    params={"exclude_path": "/videok/masodik_resz.mp4"}
                    ).json()["items"]
    assert [t["video"] for t in tetelek] == ["elso_resz.mp4"]


def test_a_kizaras_a_fajlnevet_ugyanugy_tisztitja():
    """ŐR: a kizárás a MENTÉSSEL azonos szabállyal tisztít.

    A mentés a nem-biztonságos jeleket aláhúzásra cseréli. Ha a
    kizárás nyers fájlnévvel hasonlítana, egy ékezetes vagy szóközös
    néven a saját kalibráció mégis megjelenne a listán — némán, és
    pont ott, ahol a legzavaróbb.
    """
    c = _client()
    _ment(c, "/videok/Bajnoki meccs (1).mp4")
    tetelek = c.get("/calibration/saved",
                    params={"exclude_path": "/videok/Bajnoki meccs (1).mp4"}
                    ).json()["items"]
    assert tetelek == [], tetelek


def test_ures_kalibracio_nem_kerul_a_listara():
    """Üres listát átvenni semmit sem ér — ne is kínáljuk fel."""
    c = _client()
    c.post("/calibration", json={"path": "/videok/ures.mp4", "calibs": []})
    assert c.get("/calibration/saved").json()["items"] == []


def test_a_legfrissebb_van_elol():
    """A legutóbb kalibrált videó a legvalószínűbb forrás: azzal
    dolgozott a felhasználó egy perce."""
    import time

    c = _client()
    _ment(c, "/videok/regi.mp4")
    time.sleep(0.02)
    _ment(c, "/videok/uj.mp4")
    tetelek = c.get("/calibration/saved").json()["items"]
    assert tetelek[0]["video"] == "uj.mp4"
