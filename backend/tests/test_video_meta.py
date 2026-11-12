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


# ---- Az mvhd-kereső közvetlenül (_mvhd_creation) és a fájl-olvasás szélei -------

def test_mvhd_creation_mindket_verziobol_olvas():
    """A 0-s verziójú doboz 32 bites, az 1-es 64 bites creation_time-ot
    hordoz — mindkettőből UTC időpont jön, a környező bájtoktól
    függetlenül."""
    from handball.pipeline.video_meta import _mvhd_creation

    dt = datetime.datetime(2024, 11, 20, 18, 9, tzinfo=datetime.timezone.utc)
    assert _mvhd_creation(_mvhd_bytes(dt)) == dt
    assert _mvhd_creation(_mvhd_bytes(dt, version=1)) == dt
    assert _mvhd_creation(b"ftypisom" + b"\x00" * 100 + _mvhd_bytes(dt)
                          + b"trak" * 10) == dt


def test_mvhd_creation_none_ha_nincs_ertelmes_datum():
    """Nincs mvhd, üres adat, kitöltetlen (1904-es) vagy életszerűtlen
    (1995 előtti / 2100 utáni) dátum, illetve a doboz közepén véget érő
    (csonka) adat → None, kivétel nélkül."""
    from handball.pipeline.video_meta import _mvhd_creation

    assert _mvhd_creation(b"") is None
    assert _mvhd_creation(b"\x00" * 256 + b"moov" + b"\x00" * 64) is None
    assert _mvhd_creation(_mvhd_bytes(_QT_EPOCH)) is None
    regi = datetime.datetime(1980, 1, 1, tzinfo=datetime.timezone.utc)
    assert _mvhd_creation(_mvhd_bytes(regi)) is None
    tavoli = datetime.datetime(2150, 1, 1, tzinfo=datetime.timezone.utc)
    assert _mvhd_creation(_mvhd_bytes(tavoli, version=1)) is None
    jo = _mvhd_bytes(datetime.datetime(2024, 11, 20,
                                       tzinfo=datetime.timezone.utc))
    for vagas in (len(jo) - 1, len(jo) - 3, 9, 8):   # csonka doboz
        assert _mvhd_creation(jo[:vagas]) is None, vagas
    # A határ-évek még jók.
    for ev in (1995, 2100):
        hatar = datetime.datetime(ev, 6, 1, tzinfo=datetime.timezone.utc)
        assert _mvhd_creation(_mvhd_bytes(hatar, version=1)) == hatar


def test_mvhd_creation_a_veletlen_egyezes_utan_tovabb_keres():
    """Az "mvhd" bájtsor véletlenül is előfordulhat (vagy az első doboz
    kitöltetlen): az első ÉRTELMES dátumú találat számít, nem az első."""
    from handball.pipeline.video_meta import _mvhd_creation

    jo = datetime.datetime(2025, 3, 2, tzinfo=datetime.timezone.utc)
    kesobbi = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
    adat = (b"mvhd\xff\xff" + b"\x00" * 10            # szemét egyezés
            + _mvhd_bytes(_QT_EPOCH)                  # kitöltetlen doboz
            + _mvhd_bytes(jo) + _mvhd_bytes(kesobbi))
    assert _mvhd_creation(adat) == jo


def test_a_fajl_vegen_allo_mvhd_t_is_megtalalja(tmp_path, monkeypatch):
    """Nem faststart fájlnál a moov a fájl VÉGÉN van: ha az eleji
    darabban nincs dátum, a végi darabból olvasunk (itt az olvasott
    darabot kicsire vesszük, hogy a próba-fájl kicsi maradhasson)."""
    from handball.pipeline import video_meta

    monkeypatch.setattr(video_meta, "_SCAN_BYTES", 1024)
    dt = datetime.datetime(2024, 11, 20, tzinfo=datetime.timezone.utc)
    p = tmp_path / "vegen.mp4"
    p.write_bytes(b"\x00" * 5000 + _mvhd_bytes(dt) + b"\x00" * 100)
    assert video_recording_date(str(p)) == "2024-11-20"
    # A fájl KÖZEPÉN (sem az eleji, sem a végi darabban) álló dobozt nem
    # látjuk: a tartalék a fájl módosítási ideje.
    kozepen = tmp_path / "kozepen.mp4"
    kozepen.write_bytes(b"\x00" * 3000 + _mvhd_bytes(dt) + b"\x00" * 3000)
    ts = datetime.datetime(2023, 5, 6, 12, 0).timestamp()
    os.utime(kozepen, (ts, ts))
    assert video_recording_date(str(kozepen)) == "2023-05-06"


def test_eletszerutlen_fajlidonel_nincs_datum(tmp_path):
    """Ha a fájlban nincs dátum ÉS a módosítási ideje is életszerűtlen
    (pl. 1980 — hibás óra, kicsomagolt archívum), inkább nincs dátum
    (None), mint egy biztosan rossz; üres fájlból is a fájlidő a tartalék."""
    p = tmp_path / "regi.mp4"
    p.write_bytes(b"\x00" * 64)
    ts = datetime.datetime(1980, 1, 2, 12, 0).timestamp()
    os.utime(p, (ts, ts))
    assert video_recording_date(str(p)) is None
    ures = tmp_path / "ures.mp4"
    ures.write_bytes(b"")
    ts = datetime.datetime(2024, 2, 3, 12, 0).timestamp()
    os.utime(ures, (ts, ts))
    assert video_recording_date(str(ures)) == "2024-02-03"
    # Mappa (nem fájl) útjára sem száll el.
    assert video_recording_date(str(tmp_path)) is None
