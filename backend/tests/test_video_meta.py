"""
Tesztek a felvétel-dátum kinyerésére (video_meta.py) + a PATCH date mezőre.

Futtatás:
    python -m pytest tests/test_video_meta.py
"""

from __future__ import annotations

import datetime
import os
import struct
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.pipeline.video_meta import video_recording_date  # noqa: E402

_QT_EPOCH = datetime.datetime(1904, 1, 1, tzinfo=datetime.timezone.utc)


def _mvhd_bytes(dt: datetime.datetime, version: int = 0) -> bytes:
    """Egy minimális mvhd doboz a megadott creation_time-mal."""
    secs = int((dt - _QT_EPOCH).total_seconds())
    if version == 1:
        body = bytes([1, 0, 0, 0]) + struct.pack(">Q", secs)
    else:
        body = bytes([0, 0, 0, 0]) + struct.pack(">I", secs)
    box = b"mvhd" + body
    return struct.pack(">I", len(box) + 4) + box


def test_reads_mvhd_creation_date(tmp_path):
    dt = datetime.datetime(2024, 11, 20, 18, 9, tzinfo=datetime.timezone.utc)
    p = tmp_path / "match.mp4"
    p.write_bytes(b"\x00" * 64 + _mvhd_bytes(dt) + b"\x00" * 64)
    assert video_recording_date(str(p)) == "2024-11-20"


def test_reads_mvhd_version1(tmp_path):
    dt = datetime.datetime(2025, 3, 2, tzinfo=datetime.timezone.utc)
    p = tmp_path / "v1.mp4"
    p.write_bytes(_mvhd_bytes(dt, version=1))
    assert video_recording_date(str(p)) == "2025-03-02"


def test_zero_creation_falls_back_to_mtime(tmp_path):
    # creation_time=0 (1904) = "nincs kitöltve" → a fájl mtime-ja a tartalék.
    p = tmp_path / "empty_meta.mp4"
    p.write_bytes(_mvhd_bytes(_QT_EPOCH))
    want = datetime.date(2023, 5, 6)
    ts = datetime.datetime(2023, 5, 6, 12, 0).timestamp()
    os.utime(p, (ts, ts))
    assert video_recording_date(str(p)) == want.isoformat()


def test_missing_file_gives_none():
    assert video_recording_date("/nincs/ilyen.mp4") is None


def test_patch_date_validated_and_persisted():
    import json
    import pytest
    TestClient = pytest.importorskip(
        "fastapi.testclient", reason="fastapi nincs telepítve").TestClient
    tmp = tempfile.mkdtemp(prefix="handball_date_test_")
    os.environ["HANDBALL_DATA_DIR"] = tmp
    from pathlib import Path
    from handball.api.app import create_app
    from handball.sim.match_simulator import simulate_ground_truth
    m = simulate_ground_truth(duration_s=3, fps=25.0, seed=1)
    d = Path(tmp) / "data" / "matches"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{m.meta.match_id}.json").write_text(json.dumps(m.to_dict()),
                                               encoding="utf-8")
    client = TestClient(create_app())
    mid = m.meta.match_id
    # Érvényes dátum beállítása.
    r = client.patch(f"/matches/{mid}", json={"date": "2026-01-15"})
    assert r.status_code == 200 and r.json()["date"] == "2026-01-15"
    # Rossz formátum: 400.
    assert client.patch(f"/matches/{mid}",
                        json={"date": "15/01/2026"}).status_code == 400
    # Üres dátum: törlés.
    r = client.patch(f"/matches/{mid}", json={"date": ""})
    assert r.status_code == 200 and r.json()["date"] is None
