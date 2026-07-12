"""
Tesztek a meccskönyvtár mentésére/visszaállítására (/library/export|import).

Futtatás:
    python -m pytest tests/test_library_api.py
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_tmp = tempfile.mkdtemp(prefix="handball_library_test_")
os.environ["HANDBALL_DATA_DIR"] = _tmp

import pytest  # noqa: E402

TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient

from handball.api.app import create_app  # noqa: E402
from handball.sim.match_simulator import simulate_ground_truth  # noqa: E402


def _fresh_client(tmp: str):
    os.environ["HANDBALL_DATA_DIR"] = tmp
    m = simulate_ground_truth(duration_s=3, fps=25.0, seed=1)
    matches_dir = Path(tmp) / "data" / "matches"
    matches_dir.mkdir(parents=True, exist_ok=True)
    (matches_dir / f"{m.meta.match_id}.json").write_text(
        json.dumps(m.to_dict()), encoding="utf-8")
    return TestClient(create_app()), m.meta.match_id


def test_export_then_import_on_new_machine_roundtrip():
    client, mid = _fresh_client(_tmp)
    # Kísérőfájl is (jegyzet) — a mentésnek ezt is vinnie kell.
    client.post(f"/matches/{mid}/notes", json={"frame": 3, "text": "fontos"})
    zip_bytes = client.get("/library/export").content
    names = zipfile.ZipFile(io.BytesIO(zip_bytes)).namelist()
    assert any(n.endswith(f"{mid}.json") for n in names)
    assert any(n.endswith(f"{mid}.notes.json") for n in names)

    # "Új gép": üres adatmappa, üres tár → visszaállítás.
    tmp2 = tempfile.mkdtemp(prefix="handball_library_test2_")
    os.environ["HANDBALL_DATA_DIR"] = tmp2
    client2 = TestClient(create_app())
    assert client2.get("/matches").json()["matches"] == []
    r = client2.post("/library/import", content=zip_bytes).json()
    assert r["matches"] >= 1 and r["restored_files"] >= 2
    ids = [m["match_id"] for m in client2.get("/matches").json()["matches"]]
    assert mid in ids
    notes = client2.get(f"/matches/{mid}/notes").json()["notes"]
    assert [n["text"] for n in notes] == ["fontos"]


def test_import_rejects_invalid_zip():
    client, _ = _fresh_client(tempfile.mkdtemp(prefix="handball_lib3_"))
    r = client.post("/library/import", content=b"ez nem zip")
    assert r.status_code == 400


def test_import_skips_path_traversal_entries():
    tmp = tempfile.mkdtemp(prefix="handball_lib4_")
    client, _ = _fresh_client(tmp)
    evil = io.BytesIO()
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("../../evil.txt", "kitores")
        z.writestr("matches/jo.txt", "rendben")
    r = client.post("/library/import", content=evil.getvalue()).json()
    assert r["restored_files"] == 1  # csak a data/ alá eső fájl
    assert not (Path(tmp) / "evil.txt").exists()
    assert not (Path(tmp).parent / "evil.txt").exists()
    assert (Path(tmp) / "data" / "matches" / "jo.txt").exists()


if __name__ == "__main__":
    test_export_then_import_on_new_machine_roundtrip()
    test_import_rejects_invalid_zip()
    test_import_skips_path_traversal_entries()
    print("Minden könyvtár-mentés teszt OK.")
