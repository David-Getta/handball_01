"""
Tesztek a meccs-csomag exportra (/matches/{id}/package/export|download).

Futtatás:
    python -m pytest tests/test_package_api.py
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import time
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_tmp = tempfile.mkdtemp(prefix="handball_package_test_")
os.environ["HANDBALL_DATA_DIR"] = _tmp

import pytest  # noqa: E402

TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient

from handball.api.app import create_app  # noqa: E402
from handball.sim.match_simulator import simulate_ground_truth  # noqa: E402


def _client_with_match():
    os.environ["HANDBALL_DATA_DIR"] = _tmp
    m = simulate_ground_truth(duration_s=5, fps=25.0, seed=1)
    matches_dir = Path(_tmp) / "data" / "matches"
    matches_dir.mkdir(parents=True, exist_ok=True)
    (matches_dir / f"{m.meta.match_id}.json").write_text(
        json.dumps(m.to_dict()), encoding="utf-8")
    return TestClient(create_app()), m.meta.match_id


def _wait_job(client, job_id, timeout_s=30):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        job = client.get(f"/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            return job
        time.sleep(0.1)
    raise AssertionError("a job nem fejeződött be időben")


def test_package_without_video_contains_report_and_csv():
    """Videó nélkül (szimulált meccs) a csomag jelentés + CSV — a klipek
    hiánya nem végzetes."""
    client, mid = _client_with_match()
    # Egy jegyzet is kerül a meccshez — a csomagnak ezt is vinnie kell.
    client.post(f"/matches/{mid}/notes",
                json={"frame": 10, "text": "fontos pillanat"})
    r = client.post(f"/matches/{mid}/package/export", json={})
    job = _wait_job(client, r.json()["job_id"])
    assert job["status"] == "done", job
    pkg = client.get(f"/matches/{mid}/package/download")
    assert pkg.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(pkg.content))
    names = z.namelist()
    assert "jelentes.html" in names and "statisztika.csv" in names
    # Az összes elemzés-réteg géppel olvasható JSON-ban is benne van.
    assert "elemzesek.json" in names
    import json as _json
    analyses = _json.loads(z.read("elemzesek.json").decode("utf-8"))
    for key in ("coach_summary", "xg", "defense", "rules", "training",
                "progression", "attack_efficiency", "assist_network",
                "possession", "outlets", "empty_net_goals",
                "empty_net_context", "fast_break_finishers",
                "key_players", "pace", "late_subs", "big_saves",
                "missed_big_chances", "xg_saved", "xg_prevented",
                "attack_origins", "recovery", "positions",
                "seven_earners", "susp_earners"):
        assert key in analyses, key
    # Az edzésterv pontosan akkor van a csomagban, ha van fókusz.
    tf_pkg = analyses.get("training") or {}
    has_focus = any((tf_pkg.get(s_) or []) for s_ in ("home", "away"))
    assert ("edzesterv.txt" in names) == has_focus
    if has_focus:
        etxt = z.read("edzesterv.txt").decode("utf-8")
        assert "gyakorlat:" in etxt
    # Az edzői összefoglaló sima szövegként is (osszefoglalo.txt).
    assert "osszefoglalo.txt" in names
    txt = z.read("osszefoglalo.txt").decode("utf-8")
    assert "vs" in txt
    # A jegyzetek időbélyeggel, sima szövegként (jegyzetek.txt).
    assert "jegyzetek.txt" in names
    jtxt = z.read("jegyzetek.txt").decode("utf-8")
    assert "fontos pillanat" in jtxt and "[" in jtxt
    assert "klipek.zip" not in names  # nincs videó → nincs klip
    html = z.read("jelentes.html").decode("utf-8")
    assert "Meccsjelentés" in html
    csv = z.read("statisztika.csv").decode("utf-8")
    assert "Játékos;Csapat" in csv


def test_package_download_404_before_export():
    client, mid = _client_with_match()
    # Friss adatmappa kell, ahol még nem készült csomag ehhez a meccshez.
    import shutil
    clips_dir = Path(_tmp) / "clips"
    if clips_dir.exists():
        shutil.rmtree(clips_dir)
    assert client.get(f"/matches/{mid}/package/download").status_code == 404
    assert client.get("/matches/nincs/package/download").status_code == 404


if __name__ == "__main__":
    test_package_without_video_contains_report_and_csv()
    test_package_download_404_before_export()
    print("Minden csomag-export teszt OK.")


def test_scouting_matchup_endpoint():
    """A meccsterv-végpont a két kombinált profilból tervet ad vissza."""
    client, mid = _client_with_match()
    body = {"own": {"items": [{"match_id": mid, "team": "home"}]},
            "opp": {"items": [{"match_id": mid, "team": "away"}]}}
    r = client.post("/scouting/matchup", json=body)
    assert r.status_code == 200
    data = r.json()
    assert "plan" in data and isinstance(data["plan"], list)
    # Hiányzó oldal → 400.
    r2 = client.post("/scouting/matchup",
                     json={"own": {"items": []}})
    assert r2.status_code == 400
