"""
Tesztek: Apple-GPU-n (MPS) a tanítás / gyűjtés és a feldolgozás kizárja
egymást.

Az MPS nem szál-biztos (v0.1.177): egyszerre csak egy szál használhatja a
GPU-t. A finomhangolás és a tanítóadat-gyűjtés háttérszálon dolgozik; ha
mellettük feldolgozás indul (vagy fordítva), a Metal leállítaná a motort,
és mindkét munka elveszne.

Futtatás:
    python -m pytest tests/test_mps_kizaras.py
"""

from __future__ import annotations

import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

cv2 = pytest.importorskip("cv2", reason="OpenCV nincs telepítve")
np = pytest.importorskip("numpy", reason="numpy nincs telepítve")
pytest.importorskip("fastapi", reason="fastapi nincs telepítve")


def _app(tmp_path, monkeypatch):
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("HANDBALL_STORE_SYNC", "1")
    from fastapi.testclient import TestClient

    from handball.api.app import create_app
    return TestClient(create_app())


def _video(path, frames=30):
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 25.0,
                         (96, 64))
    for _ in range(frames):
        vw.write(np.full((64, 96, 3), 120, dtype=np.uint8))
    vw.release()


def test_mps_en_a_feldolgozas_megvarja_a_tanitast_es_a_gyujtest(
        tmp_path, monkeypatch):
    """Futó tanítás / gyűjtés mellett MPS-en a feldolgozás 409 (a motor
    mondatával); CPU-n (vagy tanítás nélkül) indul."""
    import scripts.process_video as pv

    c = _app(tmp_path, monkeypatch)
    v = tmp_path / "m.mp4"
    _video(v)
    monkeypatch.setattr(pv, "_pick_device", lambda: "mps")
    c.app.state.train_state["running"] = True
    r = c.post("/matches/process", json={"path": str(v), "max": 5})
    assert r.status_code == 409
    assert "finomhangolás" in r.json()["detail"]
    assert "várd meg a tanítás végét" in r.json()["detail"]
    c.app.state.train_state["running"] = False
    c.app.state.dataset_state["running"] = True
    r = c.post("/matches/process", json={"path": str(v), "max": 5})
    assert r.status_code == 409
    assert "tanítóadat-gyűjtés" in r.json()["detail"]
    # CPU-n a tanítás nem foglalja a GPU-t — a feldolgozás indulhat.
    monkeypatch.setattr(pv, "_pick_device", lambda: "cpu")
    monkeypatch.setattr(pv, "process", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("itt nem futunk tovább")))
    r = c.post("/matches/process", json={"path": str(v), "max": 5})
    assert r.status_code == 200 and r.json()["job_id"]
    c.app.state.dataset_state["running"] = False


def test_mps_en_a_tanitas_es_a_gyujtes_megvarja_a_feldolgozast(
        tmp_path, monkeypatch):
    """Futó feldolgozás mellett MPS-en a tanítás és a gyűjtés 409 (a motor
    mondatával); a feldolgozás után az útjuk szabad (a 409 a GPU-kizárásé
    volt, nem általános)."""
    import scripts.process_video as pv

    c = _app(tmp_path, monkeypatch)
    v = tmp_path / "m.mp4"
    _video(v)
    kapu = threading.Event()

    def kapus_process(*_a, **_k):
        kapu.wait(30.0)
        raise RuntimeError("a teszt elengedte")

    monkeypatch.setattr(pv, "process", kapus_process)
    monkeypatch.setattr(pv, "_pick_device", lambda: "mps")
    (tmp_path / "dataset").mkdir()
    (tmp_path / "dataset" / "dataset.yaml").write_text("path: x\n",
                                                        encoding="utf-8")
    jid = c.post("/matches/process", json={"path": str(v)}).json()["job_id"]
    hatarido = time.time() + 10
    while c.get(f"/jobs/{jid}").json()["status"] != "running":
        assert time.time() < hatarido
        time.sleep(0.05)
    try:
        for ut, torzs in (("/dataset/train", {"epochs": 5}),
                          ("/dataset/collect", {"match_ids": []})):
            r = c.post(ut, json=torzs)
            assert r.status_code == 409, ut
            assert "feldolgozás fut" in r.json()["detail"]
            assert "grafikus gyorsító" in r.json()["detail"]
        assert c.app.state.train_state["running"] is False
        assert c.app.state.dataset_state["running"] is False
    finally:
        kapu.set()
    hatarido = time.time() + 10
    while c.get(f"/jobs/{jid}").json()["status"] == "running":
        assert time.time() < hatarido
        time.sleep(0.05)
    # Feldolgozás nélkül: a gyűjtés a saját 400-áig jut (nincs videó), a
    # tanítás elindul.
    assert c.post("/dataset/collect", json={"match_ids": []}).status_code == 400
    r = c.post("/dataset/train", json={"epochs": 5})
    assert r.status_code == 200
    hatarido = time.time() + 10
    while c.app.state.train_state["running"]:
        assert time.time() < hatarido
        time.sleep(0.05)
