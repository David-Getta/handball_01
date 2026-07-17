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


def test_degenerate_calibration_rejected(tmp_path):
    """Önmetsző vagy elfajzott kalibrációval a feldolgozás el sem indul —
    érthető magyar hibaüzenettel (a többórás futás előtt szólunk)."""
    import tempfile

    video = tmp_path / "cal.mp4"
    _tiny_video(video, frames=5)
    client = _partial_setup(tempfile.mkdtemp(prefix="hb_cal_"), video,
                            partial=False)

    ok_corners = [[100, 100], [900, 120], [880, 600], [90, 580]]
    crossed = [[100, 100], [880, 600], [900, 120], [90, 580]]  # önmetsző
    tiny = [[10, 10], [12, 10], [12, 12], [10, 12]]            # elfajzott

    r = client.post("/matches/process",
                    json={"path": str(video), "calib": crossed})
    assert r.status_code == 400 and "sorrend" in r.json()["detail"]

    r = client.post("/matches/process",
                    json={"path": str(video), "calib": tiny})
    assert r.status_code == 400 and "elfajzott" in r.json()["detail"]

    r = client.post("/matches/process",
                    json={"path": str(video),
                          "calibs": [{"corners": crossed, "region": "left"}]})
    assert r.status_code == 400

    # Ép kalibrációval a job elindul (a feldolgozás maga háttérben fut).
    r = client.post("/matches/process",
                    json={"path": str(video), "calib": ok_corners})
    assert r.status_code == 200 and "job_id" in r.json()


def test_job_history_logged_and_survives_restart(tmp_path):
    """A lezárt job a naplóba kerül, és a /jobs/history új szerver-
    példányból (újraindítás után) is visszaadja."""
    import tempfile

    video = tmp_path / "h.mp4"
    _tiny_video(video, frames=8)
    tmp = tempfile.mkdtemp(prefix="hb_hist_")
    client = _partial_setup(tmp, video, partial=False)

    r = client.post("/matches/process",
                    json={"path": str(video), "match_id": "napló1"})
    _wait_done(client, r.json()["job_id"])

    h = client.get("/jobs/history").json()["jobs"]
    assert len(h) >= 1
    assert h[0]["match_id"] == "napló1"
    assert h[0]["status"] == "done"
    assert h[0]["finished"] > 0

    # "Újraindítás": friss app-példány ugyanarra az adatmappára.
    import os as _os

    from handball.api.app import create_app
    _os.environ["HANDBALL_DATA_DIR"] = tmp
    from fastapi.testclient import TestClient as _TC
    client2 = _TC(create_app())
    h2 = client2.get("/jobs/history").json()["jobs"]
    assert any(j["match_id"] == "napló1" for j in h2)


def test_reprocess_with_saved_params(tmp_path):
    """Az újra-feldolgozás a mentett beállításokkal fut, és az eredmény a
    régi meccs HELYÉRE kerül; mentett beállítások híján 404."""
    import tempfile

    video = tmp_path / "re.mp4"
    _tiny_video(video, frames=10)
    client = _partial_setup(tempfile.mkdtemp(prefix="hb_re_"), video,
                            partial=False)

    # Első feldolgozás — ez menti a params-sidecart is.
    r = client.post("/matches/process",
                    json={"path": str(video), "match_id": "ujra1",
                          "stride": 1})
    _wait_done(client, r.json()["job_id"])
    first = client.get("/matches/ujra1").json()
    assert len(first["frames"]) == 10

    # Újra-feldolgozás: ugyanaz a beállítás, ugyanarra az azonosítóra.
    r2 = client.post("/matches/ujra1/reprocess")
    assert r2.status_code == 200
    body = r2.json()
    assert body["match_id"] == "ujra1"
    _wait_done(client, body["job_id"])
    again = client.get("/matches/ujra1").json()
    assert len(again["frames"]) == 10  # a régi helyére dolgozott

    # Mentett beállítások nélkül érthető hiba.
    r3 = client.post("/matches/nincs-ilyen/reprocess")
    assert r3.status_code == 404
    assert "mentett" in r3.json()["detail"]
