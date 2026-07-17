"""
Tesztek a részleges feldolgozás folytatására (POST /matches/{id}/resume).

Egy megszakított/összeomlás után mentett meccs (meta.partial) a job
indításakor elmentett beállításokkal (params-sidecar) folytatható onnan,
ahol megszakadt — az eredmény KÜLÖN meccsként jelenik meg ("<id>-folyt").

Futtatás:
    python -m pytest tests/test_resume_api.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

cv2 = pytest.importorskip("cv2", reason="OpenCV nincs telepítve")
np = pytest.importorskip("numpy", reason="numpy nincs telepítve")
TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient

from handball.models.tracking import Match, MatchMeta  # noqa: E402


def _tiny_video(path, frames=20, w=96, h=64):
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"),
                         25.0, (w, h))
    rng = np.random.default_rng(1)
    for _ in range(frames):
        vw.write(rng.integers(90, 200, size=(h, w, 3), dtype=np.uint8))
    vw.release()


def _partial_setup(tmp: str, video: Path, partial=True):
    """Részleges meccs + params-sidecar a lemezen, ahogy egy megszakadt
    feldolgozás után kinéz — friss szerver ebből indul."""
    from handball.api.app import create_app
    os.environ["HANDBALL_DATA_DIR"] = tmp
    mdir = Path(tmp) / "data" / "matches"
    mdir.mkdir(parents=True, exist_ok=True)
    m = Match(MatchMeta(match_id="felido1", home_team="H", away_team="A",
                        fps=25.0, video_path=str(video), stride=1,
                        partial=partial, next_start_frame=10))
    (mdir / "felido1.json").write_text(m.to_json(), encoding="utf-8")
    (mdir / "felido1.params.json").write_text(
        json.dumps({"path": str(video), "stride": 1, "max": 0}),
        encoding="utf-8")
    return TestClient(create_app())


def _wait_done(client, job_id, timeout_s=60.0):
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        j = client.get(f"/jobs/{job_id}").json()
        if j["status"] in ("done", "error", "cancelled"):
            return j
        time.sleep(0.2)
    raise AssertionError("a job nem fejeződött be időben")


def test_resume_processes_remaining_frames(tmp_path):
    video = tmp_path / "felido.mp4"
    _tiny_video(video, frames=20)
    client = _partial_setup(tempfile.mkdtemp(prefix="hb_resume_"), video)

    r = client.post("/matches/felido1/resume")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["match_id"] == "felido1-folyt"
    j = _wait_done(client, body["job_id"])
    assert j["status"] == "done", j

    got = client.get("/matches/felido1-folyt").json()
    # A folytatás a 10. kockától dolgozott: 10 kocka, a meta őrzi a kezdést.
    assert len(got["frames"]) == 10
    assert got["meta"]["start_frame"] == 10
    assert got["meta"]["partial"] is False
    # A lista mindkét meccset mutatja, a részlegest jelölve.
    rows = {m["match_id"]: m for m in client.get("/matches").json()["matches"]}
    assert rows["felido1"]["partial"] is True
    assert rows["felido1-folyt"]["partial"] is False


def test_resume_rejects_complete_match(tmp_path):
    video = tmp_path / "kesz.mp4"
    _tiny_video(video, frames=10)
    client = _partial_setup(tempfile.mkdtemp(prefix="hb_resume2_"), video,
                            partial=False)
    r = client.post("/matches/felido1/resume")
    assert r.status_code == 400
    assert "nincs mit folytatni" in r.json()["detail"]


def test_resume_missing_video_fails_cleanly(tmp_path):
    video = tmp_path / "eltunt.mp4"
    _tiny_video(video, frames=10)
    client = _partial_setup(tempfile.mkdtemp(prefix="hb_resume3_"), video)
    video.unlink()  # a videót időközben letörölték/átnevezték
    r = client.post("/matches/felido1/resume")
    assert r.status_code == 400
    assert "nem található" in r.json()["detail"]
