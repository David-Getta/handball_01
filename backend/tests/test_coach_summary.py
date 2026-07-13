"""
Tesztek az automatikus edzői összefoglalóra (coach_summary).

Futtatás:
    python -m pytest tests/test_coach_summary.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import Match, MatchMeta  # noqa: E402
from handball.pipeline.coach_summary import (  # noqa: E402
    coach_summary,
    coach_summary_text,
)
from handball.sim.match_simulator import simulate_ground_truth  # noqa: E402


def test_summary_has_sections_on_simulated_match():
    m = simulate_ground_truth(duration_s=20, fps=25.0, seed=3)
    data = coach_summary(m)
    assert isinstance(data["sections"], list)
    assert isinstance(data["highlights"], list)
    # A szimulált meccsen van mozgás → legalább a játékkép/tempó és a
    # kiugró játékosok szekciónak össze kell állnia.
    titles = {s["title"] for s in data["sections"]}
    assert "Kiugró játékosok" in titles
    for s in data["sections"]:
        assert s["title"] and s["body"]  # üres mondat ne kerüljön a jelentésbe


def test_player_labels_use_jersey_numbers():
    m = simulate_ground_truth(duration_s=20, fps=25.0, seed=3)
    # A szimulátor mezszámokat oszt → a mondatokban "#szám" formát várunk.
    data = coach_summary(m)
    players = [s for s in data["sections"] if s["title"] == "Kiugró játékosok"]
    assert players and "#" in players[0]["body"]


def test_summary_text_is_plain_lines():
    m = simulate_ground_truth(duration_s=20, fps=25.0, seed=5)
    text = coach_summary_text(m)
    assert text.strip()
    for line in text.splitlines():
        assert ":" in line  # "Cím: mondatok" alak


def test_api_endpoint_returns_summary(tmp_path):
    # A CI minimál-környezetében nincs FastAPI — ott ez a teszt kimarad.
    TestClient = __import__("pytest").importorskip(
        "fastapi.testclient", reason="fastapi nincs telepítve").TestClient
    import json
    os.environ["HANDBALL_DATA_DIR"] = str(tmp_path)
    from handball.api.app import create_app
    m = simulate_ground_truth(duration_s=10, fps=25.0, seed=2)
    matches_dir = tmp_path / "data" / "matches"
    matches_dir.mkdir(parents=True, exist_ok=True)
    (matches_dir / f"{m.meta.match_id}.json").write_text(
        json.dumps(m.to_dict()), encoding="utf-8")
    client = TestClient(create_app())
    r = client.get(f"/matches/{m.meta.match_id}/coach-summary")
    assert r.status_code == 200
    data = r.json()
    assert data["sections"]
    assert client.get("/matches/nincs-ilyen/coach-summary").status_code == 404


def test_empty_match_degrades_gracefully():
    m = Match(meta=MatchMeta(match_id="empty", home_team="A", away_team="B",
                             fps=25.0), frames=[])
    data = coach_summary(m)
    assert data["sections"] == []
    assert coach_summary_text(m) == ""
