"""
Az előzetes ellenőrzés a motor felületén: POST /preflight, és a
kevés helynél való ELUTASÍTÁS a feldolgozás indításakor.

Miért itt is: a modul-tesztek a számolást őrzik, ez pedig azt, hogy a
válasz TÉNYLEG eljut a klienshez — és hogy a feldolgozás nem indul el
olyan gépen, ahol félúton elfogyna a hely (az elveszett fél óra a
felhasználó ideje).

Futtatás:
    python -m pytest tests/test_preflight_api.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

cv2 = pytest.importorskip("cv2", reason="OpenCV nincs telepítve")
np = pytest.importorskip("numpy", reason="numpy nincs telepítve")
TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient


def _tiny_video(path, frames=25, w=96, h=64):
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"),
                         25.0, (w, h))
    rng = np.random.default_rng(3)
    for _ in range(frames):
        vw.write(rng.integers(90, 200, size=(h, w, 3), dtype=np.uint8))
    vw.release()


def _client():
    from handball.api.app import create_app
    os.environ["HANDBALL_DATA_DIR"] = tempfile.mkdtemp(prefix="hb_pref_")
    return TestClient(create_app())


def test_preflight_megmondja_a_video_hosszat(tmp_path):
    """A 25 kockás, 25 fps-es videó egy másodperc — ezt kell látni."""
    video = tmp_path / "meccs.mp4"
    _tiny_video(video, frames=25)
    r = _client().post("/preflight", json={"path": str(video)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path_ok"] is True
    assert body["video_seconds"] == pytest.approx(1.0, abs=0.2)
    assert body["space_error"] is None or "szabad hely" in body["space_error"]


def test_preflight_nem_letezo_utra_is_valaszol(tmp_path):
    """A hiányzó fájl nem hiba, hanem információ: path_ok=false."""
    r = _client().post("/preflight", json={"path": str(tmp_path / "nincs.mp4")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path_ok"] is False
    assert body["estimate_s"] is None


def test_preflight_kevés_meresnel_nem_becsul(tmp_path):
    """Friss gépen nincs mérés — inkább semmi, mint téves szám."""
    video = tmp_path / "meccs.mp4"
    _tiny_video(video)
    body = _client().post("/preflight", json={"path": str(video)}).json()
    assert body["estimate_s"] is None
    assert body["estimate_label"] is None


def test_keves_helynel_el_sem_indul_a_feldolgozas(tmp_path, monkeypatch):
    """Elutasítás INDULÁS előtt, magyar indoklással — nem a 90%-nál."""
    import handball.preflight as pf

    video = tmp_path / "meccs.mp4"
    _tiny_video(video)
    client = _client()
    monkeypatch.setattr(pf, "free_gb", lambda _root: 0.2)
    r = client.post("/matches/process", json={"path": str(video)})
    assert r.status_code == 400
    assert "szabad hely" in r.json()["detail"]


def test_a_munka_rekordja_viszi_a_video_hosszat(tmp_path):
    """Enélkül a motor sosem tanulná meg, milyen gyors ez a gép."""
    video = tmp_path / "meccs.mp4"
    _tiny_video(video)
    client = _client()
    r = client.post("/matches/process", json={"path": str(video), "max": 5})
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    j = client.get(f"/jobs/{job_id}").json()
    assert j.get("video_seconds") == pytest.approx(1.0, abs=0.2)


def test_preflight_a_meccsablakra_szamol(tmp_path):
    """A becslés a FELDOLGOZANDÓ szakaszra szóljon, ne a teljes videóra.

    Ha a felhasználó megadja a meccs időablakát, csak annak a részét
    dolgozzuk fel — a teljes hosszal számolt becslés ugyanúgy téves
    lenne, mint a rossz profillal számolt.
    """
    video = tmp_path / "meccs.mp4"
    _tiny_video(video, frames=250)          # 10 másodperc @ 25 fps
    client = _client()

    teljes = client.post("/preflight", json={"path": str(video)}).json()
    assert teljes["video_seconds"] == pytest.approx(10.0, abs=0.3)
    assert teljes["processed_seconds"] == pytest.approx(10.0, abs=0.3)

    ablakos = client.post("/preflight", json={
        "path": str(video), "start_s": 2.0, "end_s": 6.0}).json()
    # A videó hossza változatlan, a feldolgozandó szakasz viszont 4 mp.
    assert ablakos["video_seconds"] == pytest.approx(10.0, abs=0.3)
    assert ablakos["processed_seconds"] == pytest.approx(4.0, abs=0.3)


def test_preflight_ertelmetlen_ablakot_nem_fogad_el(tmp_path):
    """A fordított (vagy videón kívüli) ablak ne csonkítsa a becslést."""
    video = tmp_path / "meccs.mp4"
    _tiny_video(video, frames=250)
    client = _client()

    # A vége korábban van, mint a kezdet → marad a teljes hossz.
    r = client.post("/preflight", json={
        "path": str(video), "start_s": 8.0, "end_s": 3.0}).json()
    assert r["processed_seconds"] == pytest.approx(10.0, abs=0.3)

    # A videón túlnyúló vég a videó végére vágódik.
    r2 = client.post("/preflight", json={
        "path": str(video), "start_s": 2.0, "end_s": 999.0}).json()
    assert r2["processed_seconds"] == pytest.approx(8.0, abs=0.3)
