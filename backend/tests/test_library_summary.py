"""
Tesztek a szezon-összkép végpontra (/library/summary).

Futtatás:
    python -m pytest tests/test_library_summary.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Izolált adat-mappa, hogy a teszt ne írjon a fejlesztői data/ alá.
_tmp = tempfile.mkdtemp(prefix="handball_summary_test_")
os.environ["HANDBALL_DATA_DIR"] = _tmp

import json  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

# A CI minimál-környezetében nincs FastAPI — ott ez a modul kihagyja magát.
TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient

from handball.api.app import create_app  # noqa: E402
from handball.sim.match_simulator import simulate_ground_truth  # noqa: E402


def _client_with_matches(n: int = 2):
    # Más API-tesztmodulok is állítják a HANDBALL_DATA_DIR-t import-időben —
    # itt HÍVÁSKOR állítjuk vissza a sajátunkra (sorrend-független futás).
    os.environ["HANDBALL_DATA_DIR"] = _tmp
    matches_dir = Path(_tmp) / "data" / "matches"
    matches_dir.mkdir(parents=True, exist_ok=True)
    for old in matches_dir.glob("*.json"):
        old.unlink()
    ids = []
    for i in range(n):
        m = simulate_ground_truth(duration_s=3, fps=25.0, seed=i + 1)
        m.meta.match_id = f"summary-{i}"
        (matches_dir / f"{m.meta.match_id}.json").write_text(
            json.dumps(m.to_dict()), encoding="utf-8")
        ids.append(m.meta.match_id)
    return TestClient(create_app()), ids


def test_summary_counts_and_per_match():
    client, ids = _client_with_matches(2)
    r = client.get("/library/summary")
    assert r.status_code == 200
    s = r.json()
    assert s["matches"] == 2
    assert s["total_duration_s"] > 0
    # A szimulátor mindig ad csapatneveket → a névsor nem üres.
    assert len(s["teams"]) >= 1
    # A meccsenkénti kivonatban minden meccs pontosan egyszer szerepel.
    per_ids = [d["match_id"] for d in s["per_match"]]
    assert sorted(per_ids) == sorted(ids)
    for d in s["per_match"]:
        assert d["duration_s"] > 0
        assert d["distance_m"] >= 0
        assert d["goals_home"] >= 0 and d["goals_away"] >= 0
    # Az összesített mutatók a meccsenkéntiek összegei.
    assert s["sprints"] == sum(d["sprints"] for d in s["per_match"])
    assert s["saves"] == sum(d["saves"] for d in s["per_match"])
    for d in s["per_match"]:
        assert d["saves"] <= d["shots"]  # védés csak kapura tartó lövésből
    assert s["goals"] == sum(
        d["goals_home"] + d["goals_away"] for d in s["per_match"])


def test_summary_cache_refreshes_on_rename():
    client, ids = _client_with_matches(1)
    first = client.get("/library/summary").json()
    # Átnevezés után az új név jelenik meg (a gyorsítótár nem ragad be).
    client.patch(f"/matches/{ids[0]}", json={"home_team": "Új Név KC"})
    second = client.get("/library/summary").json()
    assert second["per_match"][0]["home_team"] == "Új Név KC"
    assert first["per_match"][0]["home_team"] != "Új Név KC"


def test_summary_empty_library():
    os.environ["HANDBALL_DATA_DIR"] = tempfile.mkdtemp(
        prefix="handball_summary_empty_")
    client = TestClient(create_app())
    s = client.get("/library/summary").json()
    assert s["matches"] == 0
    assert s["per_match"] == []
    assert s["goals"] == 0 and s["distance_km"] == 0.0


def test_summary_includes_trend_fields():
    """A meccsenkénti kivonatban ott vannak a szezon-trend mezők (xG és
    szabad lövés-arány) — None is érvényes, ha nem számolható."""
    client, ids = _client_with_matches(1)
    d = client.get("/library/summary").json()["per_match"][0]
    for k in ("xg_home", "xg_away", "free_pct_home", "free_pct_away"):
        assert k in d
    if d["xg_home"] is not None:
        assert d["xg_home"] >= 0 and d["xg_away"] >= 0
