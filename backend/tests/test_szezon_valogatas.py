"""
Tesztek a SZEZON-VÁLOGATÁSRA (/players/season-clips/*).

A meccsenkénti klipcsomag megvan — a játékos viszont a SZEZONJÁT
akarja látni: "az összes gólom egy helyen". Eddig meccsenként kellett
vágatni, és a zipeket kézzel összeszedni.

Futtatás:
    python -m pytest tests/test_szezon_valogatas.py
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

import pytest  # noqa: E402

cv2 = pytest.importorskip("cv2", reason="OpenCV nincs telepítve")
np = pytest.importorskip("numpy", reason="numpy nincs telepítve")
TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient

from handball.models.tracking import (  # noqa: E402
    Ball, Frame, Match, MatchMeta, PlayerPosition, Team,
)


def _video(path, frames=300):
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"),
                         25.0, (96, 64))
    rng = np.random.default_rng(3)
    for _ in range(frames):
        vw.write(rng.integers(90, 200, size=(64, 96, 3), dtype=np.uint8))
    vw.release()


def _meccs(match_id, video, datum):
    """Meccs egy MELLÉ menő lövéssel a 7-estől (goal-lá javítva)."""
    meta = MatchMeta(match_id=match_id, home_team="Mi", away_team="Ok",
                     fps=25.0, video_path=str(video) if video else None,
                     date=datum)
    # A 7-es a labda MELLETT áll, hogy a lövés-felismerés őt találja
    # lövőnek — messziről a lövő ismeretlen (player_id=None) lenne, és
    # a mezszám-szűrő kidobná a jelenetet.
    frames = [Frame(t=i, players=[
        PlayerPosition(track_id=1, team=Team.HOME, x=34.0 + i, y=5.0,
                       jersey_number=7),
    ], ball=Ball(x=34.0 + i, y=5.0, confidence=1.0)) for i in range(6)]
    m = Match(meta, frames)
    # A lövést kézi javítással góllá tesszük: a válogatás a gólokat kéri.
    m.meta.event_overrides = [{"op": "set_type", "t": 4, "type": "goal"}]
    return m


def _client(meccsek):
    tmp = tempfile.mkdtemp(prefix="hb_szval_")
    os.environ["HANDBALL_DATA_DIR"] = tmp
    d = Path(tmp) / "data" / "matches"
    d.mkdir(parents=True, exist_ok=True)
    for m in meccsek:
        (d / f"{m.meta.match_id}.json").write_text(
            json.dumps(m.to_dict()), encoding="utf-8")
        # A kézi javítás a KÍSÉRŐFÁJLBAN él — a betöltő azt tekinti a
        # forrásnak, a meccs-JSON meta-mezőjét felülírja vele.
        if m.meta.event_overrides:
            (d / f"{m.meta.match_id}.events.json").write_text(
                json.dumps({"overrides": m.meta.event_overrides}),
                encoding="utf-8")
    from handball.api.app import create_app
    return TestClient(create_app())


def _bevar(client, job_id, timeout_s=90.0):
    hatarido = time.time() + timeout_s
    while time.time() < hatarido:
        job = client.get(f"/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            return job
        time.sleep(0.2)
    raise AssertionError("a szezon-válogatás nem készült el időben")


def test_a_szezon_valogatas_meccsenkent_mappaz(tmp_path):
    v1, v2 = tmp_path / "m1.mp4", tmp_path / "m2.mp4"
    _video(v1)
    _video(v2)
    client = _client([_meccs("sv1", v1, "2026-03-01"),
                      _meccs("sv2", v2, "2026-03-08")])

    r = client.post("/players/season-clips/export",
                    json={"team": "Mi", "jersey": 7, "types": ["goal"]})
    assert r.status_code == 200, r.text
    job = _bevar(client, r.json()["job_id"])
    assert job["status"] == "done", job
    assert "2 meccsből" in job["message"]

    letoltes = client.get("/players/season-clips/download",
                          params={"team": "Mi", "jersey": 7})
    assert letoltes.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(letoltes.content))
    nevek = z.namelist()
    # Meccsenkénti mappa, dátum + ellenfél a nevében.
    mappak = sorted({n.split("/")[0] for n in nevek})
    assert len(mappak) == 2, nevek
    assert all("Ok" in m_ for m_ in mappak), mappak
    assert all(n.endswith(".mp4") for n in nevek), nevek


def test_video_nelkuli_meccs_kimarad_es_ki_van_mondva(tmp_path):
    v1 = tmp_path / "m1.mp4"
    _video(v1)
    client = _client([_meccs("sq1", v1, "2026-03-01"),
                      _meccs("sq2", None, "2026-03-08")])
    r = client.post("/players/season-clips/export",
                    json={"team": "Mi", "jersey": 7})
    job = _bevar(client, r.json()["job_id"])
    assert job["status"] == "done", job
    assert "1 meccs videó nélkül kimaradt" in job["message"], job


def test_ismeretlen_mezszamra_ertheto_hiba(tmp_path):
    v1 = tmp_path / "m1.mp4"
    _video(v1)
    client = _client([_meccs("sx1", v1, "2026-03-01")])
    r = client.post("/players/season-clips/export",
                    json={"team": "Mi", "jersey": 99})
    job = _bevar(client, r.json()["job_id"])
    assert job["status"] == "error"
    assert "#99" in (job["error"] or "")


def test_letoltes_export_elott_404():
    client = _client([])
    r = client.get("/players/season-clips/download",
                   params={"team": "Senki", "jersey": 1})
    assert r.status_code == 404
