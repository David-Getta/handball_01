"""
Tesztek az edzői jegyzetek API-jára (/matches/{id}/notes).

Futtatás:
    python -m pytest tests/test_notes_api.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Izolált adat-mappa, hogy a teszt ne írjon a fejlesztői data/ alá.
_tmp = tempfile.mkdtemp(prefix="handball_notes_test_")
os.environ["HANDBALL_DATA_DIR"] = _tmp

import json  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

# A CI minimál-környezetében nincs FastAPI — ott ez a modul kihagyja magát
# (az API-t a teljes fejlesztői/csomagolt környezetben teszteljük).
TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient

from handball.api.app import create_app  # noqa: E402
from handball.sim.match_simulator import simulate_ground_truth  # noqa: E402


def _client_with_match():
    """Lemezre írt meccsel indított app — a tár indításkor onnan tölt."""
    # Híváskor állítjuk az adatmappát (más API-tesztmodulok is állítják
    # import-időben) — így a modulok bármilyen sorrendben futhatnak.
    os.environ["HANDBALL_DATA_DIR"] = _tmp
    m = simulate_ground_truth(duration_s=5, fps=25.0, seed=1)
    matches_dir = Path(_tmp) / "data" / "matches"
    matches_dir.mkdir(parents=True, exist_ok=True)
    (matches_dir / f"{m.meta.match_id}.json").write_text(
        json.dumps(m.to_dict()), encoding="utf-8")
    # A korábbi tesztek jegyzeteit töröljük — minden teszt tiszta lappal indul.
    for old in matches_dir.glob("*.notes.json"):
        old.unlink()
    client = TestClient(create_app())
    return client, m.meta.match_id


def test_notes_crud_roundtrip():
    client, mid = _client_with_match()
    # Kezdetben üres.
    assert client.get(f"/matches/{mid}/notes").json() == {"notes": []}
    # Két jegyzet, szándékosan fordított időrendben.
    n2 = client.post(f"/matches/{mid}/notes",
                     json={"frame": 80, "text": "Második"}).json()
    n1 = client.post(f"/matches/{mid}/notes",
                     json={"frame": 10, "text": "Első"}).json()
    notes = client.get(f"/matches/{mid}/notes").json()["notes"]
    assert [n["text"] for n in notes] == ["Első", "Második"]  # idő szerint
    assert notes[0]["id"] == n1["id"] and notes[1]["id"] == n2["id"]
    # Törlés.
    assert client.delete(f"/matches/{mid}/notes/{n1['id']}").status_code == 200
    notes = client.get(f"/matches/{mid}/notes").json()["notes"]
    assert [n["text"] for n in notes] == ["Második"]
    # Nem létező jegyzet törlése: 404.
    assert client.delete(f"/matches/{mid}/notes/nincs").status_code == 404


def test_notes_validation():
    client, mid = _client_with_match()
    # Üres szöveg: 400.
    assert client.post(f"/matches/{mid}/notes",
                       json={"frame": 5, "text": "   "}).status_code == 400
    # Negatív frame nullára vágva.
    n = client.post(f"/matches/{mid}/notes",
                    json={"frame": -3, "text": "x"}).json()
    assert n["frame"] == 0
    # Nem létező meccs: 404.
    assert client.get("/matches/nincs-ilyen/notes").status_code == 404


def test_notes_persist_to_disk():
    client, mid = _client_with_match()
    client.post(f"/matches/{mid}/notes", json={"frame": 3, "text": "megmarad"})
    # Új app-példány (mint egy szerver-újraindítás): a jegyzet lemezről jön.
    client2 = TestClient(create_app())
    notes = client2.get(f"/matches/{mid}/notes").json()["notes"]
    assert [n["text"] for n in notes] == ["megmarad"]


if __name__ == "__main__":
    test_notes_crud_roundtrip()
    test_notes_validation()
    test_notes_persist_to_disk()
    print("Minden jegyzet-API teszt OK.")
