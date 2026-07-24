"""Az elakadás-őrszem tesztje: a GET /jobs/{id} figyelmeztet, ha a futó
munka szívverése (utolsó tényleges előrelépés) régen volt.

Futtatás:
    python -m pytest tests/test_job_stall.py
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient


def test_job_status_warns_on_stall():
    from handball.api.app import create_app

    app = create_app()
    client = TestClient(app)

    # Kézzel beültetett "futó" munka régi szívveréssel (3 perce állt meg).
    jobs = None
    for route in app.routes:
        if getattr(route, "path", "") == "/jobs/{job_id}":
            jobs = route.endpoint.__globals__.get("_jobs")
            break
    # A create_app záróján keresztül érjük el a _jobs dictet.
    closure = {}
    for route in app.routes:
        if getattr(route, "path", "") == "/jobs/{job_id}":
            fn = route.endpoint
            closure = {v: c.cell_contents
                       for v, c in zip(fn.__code__.co_freevars,
                                       fn.__closure__ or [])}
            break
    jobs = closure.get("_jobs")
    assert jobs is not None, "a /jobs végpont _jobs záróváltozója nem található"

    jobs["stalltest"] = {
        "job_id": "stalltest", "match_id": "m", "status": "running",
        "stage": "B", "progress": 0.22,
        "message": "feldolgozás… 22% · 19,7 kocka/mp",
        "error": None, "created": time.time(),
        "video": "v.mp4", "heartbeat": time.time() - 180.0,
    }
    r = client.get("/jobs/stalltest")
    assert r.status_code == 200
    msg = r.json()["message"]
    assert "FIGYELEM" in msg and "nincs előrelépés" in msg
    assert "Megszakítás menti" in msg

    # Friss szívverésnél nincs figyelmeztetés.
    jobs["stalltest"]["heartbeat"] = time.time()
    jobs["stalltest"]["message"] = "feldolgozás… 23%"
    msg2 = client.get("/jobs/stalltest").json()["message"]
    assert "FIGYELEM" not in msg2
