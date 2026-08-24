"""
Kézi meccs-ablak: a felhasználó MEGMONDHATJA, hol kezdődik a meccs.

Miért kell: a feltöltött felvételben rendszerint benne van a
bemelegítés és a csapatbemutatás. Az automatikus meccs-ablak ezt
megpróbálja levágni, de rossz kalibrációnál becsapható (ha a lelátó is
a pályára vetül, a bemelegítés is "játéknak" látszik) — és akkor a
bemelegítő kapura lövésekből lövés, az álldogálásból eladott labda
lesz. A kézi ablak ezt felülírja: ez a végső menekülőút.

Amit itt őrzünk: a MÁSODPERC → KOCKA átváltás (a felhasználó
másodpercben gondolkodik, a feldolgozó kockákban), a ritkítás
figyelembevétele a végénél, és hogy a megadott ablak a MENTETT
paraméterekbe is bekerül (különben a Folytatás elveszítené).

Futtatás:
    python -m pytest tests/test_manual_window.py
"""

from __future__ import annotations

import json
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


def _video(path, frames=250, w=96, h=64, fps=25.0):
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"),
                         fps, (w, h))
    rng = np.random.default_rng(7)
    for _ in range(frames):
        vw.write(rng.integers(90, 200, size=(h, w, 3), dtype=np.uint8))
    vw.release()


def _client(tmp_root):
    from handball.api.app import create_app
    os.environ["HANDBALL_DATA_DIR"] = tmp_root
    return TestClient(create_app())


def _params(tmp_root, match_id):
    p = Path(tmp_root) / "data" / "matches" / f"{match_id}.params.json"
    return json.loads(p.read_text(encoding="utf-8"))


def test_kezdet_masodpercbol_kockat_szamol(tmp_path):
    """4 mp @ 25 fps = a 100. nyers kocka."""
    video = tmp_path / "m.mp4"
    _video(video)
    root = tempfile.mkdtemp(prefix="hb_win_")
    client = _client(root)
    r = client.post("/matches/process",
                    json={"path": str(video), "start_s": 4.0, "max": 3})
    assert r.status_code == 200, r.text
    par = _params(root, r.json()["match_id"])
    assert par["start"] == 100


def test_veg_a_ritkitast_is_figyelembe_veszi(tmp_path):
    """0-8 mp, stride=3 → (8*25 - 0)/3 ≈ 67 feldolgozandó kocka."""
    video = tmp_path / "m.mp4"
    _video(video)
    root = tempfile.mkdtemp(prefix="hb_win2_")
    client = _client(root)
    r = client.post("/matches/process",
                    json={"path": str(video), "end_s": 8.0, "stride": 3,
                          "max": 3})
    assert r.status_code == 200, r.text
    par = _params(root, r.json()["match_id"])
    assert par["max"] == 67


def test_ablak_nelkul_nem_nyul_a_parameterekhez(tmp_path):
    """Aki nem ad meg ablakot, a régi viselkedést kapja."""
    video = tmp_path / "m.mp4"
    _video(video)
    root = tempfile.mkdtemp(prefix="hb_win3_")
    client = _client(root)
    r = client.post("/matches/process",
                    json={"path": str(video), "start": 5, "max": 3})
    assert r.status_code == 200, r.text
    par = _params(root, r.json()["match_id"])
    assert par["start"] == 5
    assert par["max"] == 3


def test_kezi_ablaknal_nincs_automatikus_vagas(tmp_path):
    """A kézi ablak ígérete: "felülír minden felismerést".

    Eddig ez nem volt igaz — a megadott szakasz beolvasása UTÁN az
    automatikus meccs-ablak még lecsíphetett az elejéből-végéből. Aki
    perc:másodpercre megmondta, hol a meccs, nem erre számít.

    Kézi ablaknál a felismerés le sem fut, tehát a mentés meccs-ablak
    mezői ismeretlenek (None) maradnak: a jelentés így sem
    figyelmeztetést, sem megnyugtatást nem ad olyasmiről, amit meg sem
    vizsgáltunk.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.process_video import process

    video = tmp_path / "meccs.mp4"
    _video(video, frames=120)
    m = process(str(video), None, stride=2, max_frames=20,
                match_id="kezi", manual_window=True)
    assert m.meta.game_window_found is None
    assert m.meta.game_trim_head_s is None


def test_kezi_ablak_nelkul_lefut_a_felismeres(tmp_path):
    """Ablak nélkül viszont MEGVIZSGÁLJUK, és a mentés meg is mondja az
    eredményt — enélkül a jelentés nem tudná, kimaradt-e a bemelegítés."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.process_video import process

    video = tmp_path / "meccs.mp4"
    _video(video, frames=120)
    m = process(str(video), None, stride=2, max_frames=20, match_id="auto")
    assert m.meta.game_window_found is not None
    assert m.meta.game_trim_head_s is not None
