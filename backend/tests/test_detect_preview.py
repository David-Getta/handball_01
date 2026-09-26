"""
Tesztek a detektálás-próba végpontra (/detect-preview) — hibaágak.

A valódi YOLO-futtatást nem teszteljük (súly-letöltést igényelne);
a paraméter-ellenőrzés és a hiányzó fájl kezelése a cél.

Futtatás:
    python -m pytest tests/test_detect_preview.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient

from handball.api.app import create_app  # noqa: E402


def _client():
    os.environ["HANDBALL_DATA_DIR"] = tempfile.mkdtemp(
        prefix="handball_preview_test_")
    return TestClient(create_app())


def test_missing_video_gives_404():
    client = _client()
    r = client.get("/detect-preview", params={"path": "/nincs/ilyen.mp4"})
    assert r.status_code == 404


def test_unreadable_frame_gives_400_with_reason(tmp_path):
    """LÉTEZŐ, de megnyithatatlan videónál 400 jár — MAGYARÁZATTAL.

    Korábban 404 volt, ami két okból rossz: a fájl megvan (tehát nem
    "nincs meg"), és a kliens a 404-et "a kért elem nincs meg (lehet,
    hogy időközben törölték)" mondatra fordítja — ami sérült videónál
    vagy ékezetes útvonalnál félrevezető. A 400 mellé a szerver kiadja
    a valódi okot és a teendőt is.
    """
    bogus = tmp_path / "nem_video.mp4"
    bogus.write_bytes(b"ez nem videofajl")
    client = _client()
    r = client.get("/detect-preview", params={"path": str(bogus)})
    assert r.status_code == 400, r.text
    detail = r.json()["detail"]
    assert "nem sikerült megnyitni" in detail
    assert "kodek" in detail  # ékezet nélküli úton a kodek a gyanúsított
