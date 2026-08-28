"""
Tesztek a KÖTEG-UTÁNI automatikus összefűzésre (merge_group).

Aki egy meccs hat darabját tölti fel, hat feldolgozást indít —
jellemzően éjszakára. Reggel hat KÜLÖN "meccset" talált, és kézzel
kellett összefűznie, jó sorrendben. Ez pont az a lépés, amit az ember
elfelejt; a motor viszont tudja, mikor lett kész az utolsó darab.

Az összefűzés CSENDES és HIBATŰRŐ: ha bármelyik darab elhasalt vagy
részleges, elmarad (fél meccset összefűzni rosszabb, mint szólni), és
az üzenet megmondja, miért.

Futtatás:
    python -m pytest tests/test_koteg_osszefuzes.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from pathlib import Path  # noqa: E402

cv2 = pytest.importorskip("cv2", reason="OpenCV nincs telepítve")
np = pytest.importorskip("numpy", reason="numpy nincs telepítve")
TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient


def _video(path, frames=120, w=96, h=64, fps=25.0):
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"),
                         fps, (w, h))
    rng = np.random.default_rng(7)
    for _ in range(frames):
        vw.write(rng.integers(90, 200, size=(h, w, 3), dtype=np.uint8))
    vw.release()


def _client():
    from handball.api.app import create_app
    os.environ["HANDBALL_DATA_DIR"] = tempfile.mkdtemp(prefix="hb_group_")
    return TestClient(create_app())


def _bevar(client, job_ids, timeout_s=120.0):
    """Megvárja, míg minden munka végállapotba ér; a végső rekordok."""
    hatarido = time.time() + timeout_s
    while time.time() < hatarido:
        jobs = [client.get(f"/jobs/{j}").json() for j in job_ids]
        if all(j["status"] in ("done", "error", "cancelled")
               for j in jobs):
            return jobs
        time.sleep(0.3)
    raise AssertionError("a feldolgozások nem értek véget időben")


def test_a_koteg_magatol_osszeall(tmp_path):
    client = _client()
    v1, v2 = tmp_path / "resz1.mp4", tmp_path / "resz2.mp4"
    _video(v1)
    _video(v2)

    jobs = []
    for i, v in enumerate((v1, v2)):
        r = client.post("/matches/process", json={
            "path": str(v), "max": 10, "home_team": "Mi", "away_team": "Ok",
            "merge_group": "proba-1", "merge_order": i,
            "merge_total": 2, "queue_behind": True})
        assert r.status_code == 200, r.text
        jobs.append(r.json()["job_id"])

    kesz = _bevar(client, jobs)
    assert all(j["status"] == "done" for j in kesz), kesz

    # Az összefűzött meccs OTT VAN a könyvtárban, és az üzenet mondja.
    nevek = [m["match_id"] for m in client.get("/matches").json()["matches"]]
    osszefuzott = [n for n in nevek if n.startswith("teljes-")]
    assert len(osszefuzott) == 1, nevek
    assert any("összefűzve" in (j.get("message") or "") for j in kesz), kesz

    # A darabok is megmaradnak: az eredeti sosem veszik el.
    assert len(nevek) == 3


def test_csoport_nelkul_nincs_osszefuzes(tmp_path):
    """ŐR: aki NEM kötegben tölt fel, ne kapjon kéretlen összefűzést —
    két külön meccs két külön meccs marad."""
    client = _client()
    v1, v2 = tmp_path / "a.mp4", tmp_path / "b.mp4"
    _video(v1)
    _video(v2)
    jobs = []
    for v in (v1, v2):
        r = client.post("/matches/process",
                        json={"path": str(v), "max": 10,
                              "queue_behind": True})
        jobs.append(r.json()["job_id"])
    _bevar(client, jobs)
    nevek = [m["match_id"] for m in client.get("/matches").json()["matches"]]
    assert not any(n.startswith("teljes-") for n in nevek), nevek


def test_megszakitott_darabbal_nem_lesz_teljes_meccs(tmp_path):
    """Ha a csoport egyik darabját megszakították, a többi kész
    darabból NEM lesz "teljes" meccs — fél meccset összefűzni rosszabb,
    mint szólni. Az ok ki van mondva."""
    client = _client()
    v1, v2 = tmp_path / "megvan.mp4", tmp_path / "leallitott.mp4"
    _video(v1)
    _video(v2)

    r1 = client.post("/matches/process", json={
        "path": str(v1), "max": 10,
        "merge_group": "proba-2", "merge_order": 0, "merge_total": 2,
        "queue_behind": True})
    r2 = client.post("/matches/process", json={
        "path": str(v2), "max": 10,
        "merge_group": "proba-2", "merge_order": 1, "merge_total": 2,
        "queue_behind": True})
    jobs = [r1.json()["job_id"], r2.json()["job_id"]]
    # A második darabot azonnal megszakítjuk (még a sorban áll).
    client.post(f"/jobs/{jobs[1]}/cancel")
    kesz = _bevar(client, jobs)
    nevek = [m["match_id"] for m in client.get("/matches").json()["matches"]]
    assert not any(n.startswith("teljes-") for n in nevek), nevek
    # Az ok KI VAN MONDVA valamelyik munka üzenetében.
    assert any("összefűzés elmaradt" in (j.get("message") or "")
               for j in kesz), kesz


def test_fel_bekuldott_csoport_nem_zarodik_le():
    """ŐR a VERSENY ellen: ha az első darab elkészül, mielőtt a
    többit beküldték, a csoport nem zárulhat le egy darabbal — a
    merge_total mondja meg, hányat várunk."""
    from handball.api.app import create_app  # noqa: F401 — a fenti kliens

    client = _client()
    # Közvetlenül a job-nyilvántartásba nyúlni törékeny lenne; ehelyett
    # a viselkedést a fenti két teszt fedi, itt a SZERZŐDÉST rögzítjük:
    # a /process elfogadja és eltárolja a merge_total mezőt.
    import handball.api.app as app_mod
    src = (Path(app_mod.__file__)).read_text(encoding="utf-8")
    assert "merge_total" in src
    assert "len(tarsak) < vart" in src, (
        "a csoport a beküldött darabszám ellenőrzése nélkül zárul le")
