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


def test_library_notes_osszes_meccsbol():
    """A könyvtár-szintű jegyzet-lista meccs-környezettel.

    A jegyzetelés eddig egyirányú volt: a meccs közben meg lehetett
    jelölni egy pillanatot, de utána csak ANNAK a meccsnek a
    lejátszójában lehetett megtalálni. Az edző fejében viszont a
    jegyzetek egyetlen listát alkotnak ("amit vissza akarok nézni") —
    a hét közbeni munka ebből indul.
    """
    client, mid = _client_with_match()
    client.post(f"/matches/{mid}/notes",
                json={"frame": 60, "text": "második hullám"})
    client.post(f"/matches/{mid}/notes",
                json={"frame": 20, "text": "beállós elzárás"})

    r = client.get("/library/notes")
    assert r.status_code == 200
    notes = r.json()["notes"]
    assert len(notes) == 2
    # Meccsen belül képkocka-sorrendben — a lista időrendben olvasható.
    assert [n["frame"] for n in notes] == [20, 60]
    for n in notes:
        assert n["match_id"] == mid
        assert n["home_team"] and n["away_team"]
        assert n["text"]
        # A t_s a jegyzet JÁTÉKIDEJE: enélkül a lista csak
        # képkocka-indexet tudna mutatni, ami az edzőnek semmit sem
        # mond.
        assert n["t_s"] >= 0
    gyors = {n["frame"]: n["t_s"] for n in notes}
    assert gyors[60] > gyors[20]


def test_library_notes_ures_ha_nincs_jegyzet():
    """Jegyzet nélkül üres lista jár, nem hiba — a képernyő ebből
    tudja kiírni, hogy még nincs mit visszanézni."""
    client, mid = _client_with_match()
    assert client.get("/library/notes").json() == {"notes": []}


def test_a_legujabb_meccs_jegyzetei_elol():
    """A hét közbeni munka a LEGUTÓBBI meccsből indul.

    Húsz meccs jegyzetei közt a felvételi sorrend semmit nem mond;
    meccsen belül viszont marad az időrend, mert a jegyzetek a meccs
    menetét követik.
    """
    import json
    from pathlib import Path

    os.environ["HANDBALL_DATA_DIR"] = _tmp
    matches_dir = Path(_tmp) / "data" / "matches"
    matches_dir.mkdir(parents=True, exist_ok=True)
    for old in matches_dir.glob("*"):
        old.unlink()
    for mid, datum in (("regi", "2026-01-05"), ("uj", "2026-03-20")):
        m = simulate_ground_truth(duration_s=3, fps=25.0, seed=1)
        m.meta.match_id = mid
        m.meta.date = datum
        (matches_dir / f"{mid}.json").write_text(
            json.dumps(m.to_dict()), encoding="utf-8")
    client = TestClient(create_app())
    client.post("/matches/regi/notes", json={"frame": 5, "text": "régi"})
    client.post("/matches/uj/notes", json={"frame": 30, "text": "új-2"})
    client.post("/matches/uj/notes", json={"frame": 10, "text": "új-1"})

    notes = client.get("/library/notes").json()["notes"]
    assert [n["text"] for n in notes] == ["új-1", "új-2", "régi"]
