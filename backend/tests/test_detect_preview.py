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


def test_unreadable_frame_gives_404(tmp_path):
    # Létező, de nem videó fájl → a kocka nem olvasható.
    bogus = tmp_path / "nem_video.mp4"
    bogus.write_bytes(b"ez nem videofajl")
    client = _client()
    r = client.get("/detect-preview", params={"path": str(bogus)})
    assert r.status_code == 404
