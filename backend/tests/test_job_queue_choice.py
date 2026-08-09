"""Új elemzés indítása FUTÓ feldolgozás mellett: a felhasználó választ.

A kliens megkérdezi, hogy megvárja-e az előző videó elemzését, vagy
azonnal kezdje az újat. A backend a `queue_behind` mezőből tudja a
döntést: várakozásnál a futó munkához NEM nyúlunk, egyébként
félretesszük (az addigi rész elmentődik, később folytatható).

Futtatás:
    python -m pytest tests/test_job_queue_choice.py
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

cv2 = pytest.importorskip("cv2", reason="OpenCV nincs telepítve")
np = pytest.importorskip("numpy", reason="numpy nincs telepítve")
TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient


def test_varakozasnal_a_futo_munkat_nem_tesszuk_felre():
    """queue_behind=True: a futó feldolgozás érintetlen marad."""
    from handball.api.app import preemptable_jobs

    jobs = [{"job_id": "regi", "status": "running"},
            {"job_id": "uj", "status": "queued"}]
    assert preemptable_jobs(jobs, "uj", True) == []


def test_azonnali_inditasnal_a_futot_felretesszuk():
    """Alapeset: az új elemzés azonnal indul, a futó félrekerül —
    de csak a FUTÓ, a sorban állókhoz és önmagához nem nyúlunk."""
    from handball.api.app import preemptable_jobs

    jobs = [{"job_id": "regi", "status": "running"},
            {"job_id": "varakozo", "status": "queued"},
            {"job_id": "uj", "status": "queued"}]
    out = preemptable_jobs(jobs, "uj", False)
    assert [j["job_id"] for j in out] == ["regi"]


def _tiny_video(path, frames=5, w=96, h=64):
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"),
                         25.0, (w, h))
    rng = np.random.default_rng(3)
    for _ in range(frames):
        vw.write(rng.integers(90, 200, size=(h, w, 3), dtype=np.uint8))
    vw.release()


def _jobs_of(app):
    """A create_app zárójában élő _jobs dict (teszt-célú elérés)."""
    for route in app.routes:
        if getattr(route, "path", "") == "/jobs/{job_id}":
            fn = route.endpoint
            closure = {v: c.cell_contents
                       for v, c in zip(fn.__code__.co_freevars,
                                       fn.__closure__ or [])}
            return closure.get("_jobs")
    return None


def _start(client, video, **extra):
    body = {"path": str(video), "max": 1}
    body.update(extra)
    r = client.post("/matches/process", json=body)
    assert r.status_code == 200, r.text
    return r.json()["job_id"]


def test_varakozo_elemzes_nem_szakitja_meg_a_futot(tmp_path):
    """A "megvárom az előzőt" választás: a futó munka nem kap
    félretevés-jelet, az új pedig jelzi a várakozást az üzenetében."""
    import tempfile

    from handball.api.app import create_app

    os.environ["HANDBALL_DATA_DIR"] = tempfile.mkdtemp(prefix="hb_qb_")
    video = tmp_path / "q.mp4"
    _tiny_video(video)
    app = create_app()
    client = TestClient(app)
    jobs = _jobs_of(app)
    assert jobs is not None

    jobs["fut"] = {"job_id": "fut", "match_id": "m", "status": "running",
                   "stage": "B", "progress": 0.4, "message": "feldolgozás…",
                   "error": None, "created": time.time(), "video": "elso.mp4"}

    job_id = _start(client, video, queue_behind=True)
    assert jobs["fut"].get("cancel") is None
    assert jobs["fut"].get("preempted") is None
    # (Az üzenetet a munkás azonnal átírhatja "indítás"-ra, ezért itt a
    # döntést hordozó jelzőt ellenőrizzük.)
    assert jobs[job_id]["queue_behind"] is True


def test_azonnali_elemzes_felreteszi_a_futot(tmp_path):
    """A "kezdje most" választás: a futó munka szelíd félretevést kap
    (az addigi része mentésre kerül), az új pedig azonnal indulhat."""
    import tempfile

    from handball.api.app import create_app

    os.environ["HANDBALL_DATA_DIR"] = tempfile.mkdtemp(prefix="hb_qb2_")
    video = tmp_path / "q2.mp4"
    _tiny_video(video)
    app = create_app()
    client = TestClient(app)
    jobs = _jobs_of(app)
    assert jobs is not None

    jobs["fut"] = {"job_id": "fut", "match_id": "m", "status": "running",
                   "stage": "B", "progress": 0.4, "message": "feldolgozás…",
                   "error": None, "created": time.time(), "video": "elso.mp4"}

    job_id = _start(client, video)
    assert jobs["fut"]["cancel"] is True
    assert jobs["fut"]["preempted"] is True
    assert jobs[job_id]["queue_behind"] is False
