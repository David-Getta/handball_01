"""
Tesztek a mezszám-hozzárendelés API-jára (/matches/{id}/jerseys).

Futtatás:
    python -m pytest tests/test_jerseys_api.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Izolált adat-mappa, hogy a teszt ne írjon a fejlesztői data/ alá.
_tmp = tempfile.mkdtemp(prefix="handball_jerseys_test_")
os.environ["HANDBALL_DATA_DIR"] = _tmp

import json  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

# A CI minimál-környezetében nincs FastAPI — ott ez a modul kihagyja magát.
TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient

from handball.api.app import create_app  # noqa: E402
from handball.sim.match_simulator import simulate_ground_truth  # noqa: E402


def _client_with_match():
    # A többi API-tesztmodul is állítja ezt a környezeti változót import-
    # időben — itt HÍVÁSKOR állítjuk vissza a sajátunkra, hogy a modulok
    # bármilyen sorrendben futhassanak.
    os.environ["HANDBALL_DATA_DIR"] = _tmp
    m = simulate_ground_truth(duration_s=3, fps=25.0, seed=1)
    matches_dir = Path(_tmp) / "data" / "matches"
    matches_dir.mkdir(parents=True, exist_ok=True)
    (matches_dir / f"{m.meta.match_id}.json").write_text(
        json.dumps(m.to_dict()), encoding="utf-8")
    for old in matches_dir.glob("*.jerseys.json"):
        old.unlink()
    client = TestClient(create_app())
    return client, m.meta.match_id


def test_set_jersey_applies_to_all_frames_and_persists():
    client, mid = _client_with_match()
    r = client.post(f"/matches/{mid}/jerseys",
                    json={"track_id": 1, "jersey": 23})
    assert r.status_code == 200 and r.json()["jerseys"] == {"1": 23}
    # A meccs minden kockáján a 1-es track a 23-as számot viseli.
    match = client.get(f"/matches/{mid}").json()
    for fr in match["frames"]:
        for p in fr["players"]:
            if p["track_id"] == 1:
                assert p["jersey_number"] == 23
    # Új app-példány (szerver-újraindítás): a szám lemezről is visszajön.
    client2 = TestClient(create_app())
    match2 = client2.get(f"/matches/{mid}").json()
    assert any(p["jersey_number"] == 23
               for fr in match2["frames"] for p in fr["players"]
               if p["track_id"] == 1)
    assert client2.get(f"/matches/{mid}/jerseys").json()["jerseys"] == {"1": 23}


def test_clear_jersey_with_null():
    client, mid = _client_with_match()
    client.post(f"/matches/{mid}/jerseys", json={"track_id": 2, "jersey": 7})
    r = client.post(f"/matches/{mid}/jerseys",
                    json={"track_id": 2, "jersey": None})
    assert r.json()["jerseys"] == {}
    match = client.get(f"/matches/{mid}").json()
    assert all(p["jersey_number"] is None
               for fr in match["frames"] for p in fr["players"]
               if p["track_id"] == 2)


def test_validation():
    client, mid = _client_with_match()
    assert client.post(f"/matches/{mid}/jerseys",
                       json={"jersey": 5}).status_code == 400  # nincs track_id
    assert client.post(f"/matches/{mid}/jerseys",
                       json={"track_id": 1, "jersey": 150}).status_code == 400
    assert client.post(f"/matches/{mid}/jerseys",
                       json={"track_id": 1, "jersey": "x"}).status_code == 400
    assert client.post("/matches/nincs/jerseys",
                       json={"track_id": 1, "jersey": 5}).status_code == 404


if __name__ == "__main__":
    test_set_jersey_applies_to_all_frames_and_persists()
    test_clear_jersey_with_null()
    test_validation()
    print("Minden mezszám-API teszt OK.")


def test_player_trend_by_jersey():
    """A mezszámhoz rendelt játékos meccsről meccsre visszakérdezhető,
    és a megszakadt követés (két track ugyanazzal a számmal) összegződik."""
    client, mid = _client_with_match()
    match = client.get(f"/matches/{mid}").json()
    team_name = match["meta"]["home_team"]
    # Két hazai track kapja ugyanazt a számot (mintha a követés megszakadt
    # volna) — a trendben egy játékosként, összegezve jelennek meg.
    home_tracks = sorted({p["track_id"] for fr in match["frames"]
                          for p in fr["players"] if p["team"] == "home"})[:2]
    for t in home_tracks:
        client.post(f"/matches/{mid}/jerseys",
                    json={"track_id": t, "jersey": 9})
    r = client.get("/players/trend",
                   params={"team": team_name, "jersey": 9}).json()
    assert len(r["points"]) == 1
    p = r["points"][0]
    assert p["match_id"] == mid and p["distance_m"] > 0
    assert p["opponent"] == match["meta"]["away_team"]
    # A lövés-hatékonyság mezők mindig jelen vannak (0/None is érvényes).
    assert "shots" in p and "goals" in p and "shot_pct" in p
    assert p["goals"] <= p["shots"]
    # Nem létező szám: üres lista (nem hiba).
    r2 = client.get("/players/trend",
                    params={"team": team_name, "jersey": 88}).json()
    assert r2["points"] == []
