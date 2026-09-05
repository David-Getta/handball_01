"""
Tesztek a kalibráció-ellenőrző rárajzolásra (calib_overlay.py).

A pálya vonalait a kalibráció homográfiájával és a kamera-mozgás
mátrixával vetítjük vissza a videó kockájára — a felhasználó a szemével
ellenőrzi, tartja-e a kalibráció a svenkelés alatt. Videó nélkül
tesztelhető: a geometria tiszta függvény.

Futtatás:
    python -m pytest tests/test_calib_overlay.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from handball.pipeline.calib_overlay import (  # noqa: E402
    PAN_KEYFRAME_S, court_polylines, keyframe_at, overlay_pixels,
    sample_pan_keyframes,
)

EGYSEG = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def _skala(s):
    """Pixel → méter: x_m = px / s (pl. 10 px = 1 m)."""
    return [[1.0 / s, 0.0, 0.0], [0.0, 1.0 / s, 0.0], [0.0, 0.0, 1.0]]


def test_a_palya_vonalai_teljesek():
    vonalak = court_polylines()
    # Téglalap, felező, 2 kapuelőtér, 2 kapu.
    assert len(vonalak) == 6
    assert vonalak[0][0] == (0.0, 0.0) and vonalak[0][2] == (40.0, 20.0)
    assert vonalak[1] == [(20.0, 0.0), (20.0, 20.0)]


def test_egysegnyi_kalibracional_a_pixel_a_meter_tizszerese():
    """H0: 10 px = 1 m → a pálya sarka (40, 20) m a (400, 200) pixelre."""
    px = overlay_pixels(_skala(10.0), None)
    sarok = px[0][2]
    assert abs(sarok[0] - 400.0) < 1e-6 and abs(sarok[1] - 200.0) < 1e-6


def test_a_kamera_eltolasa_a_vonalakat_is_eltolja():
    """G: aktuális → alap = +30 px eltolás (a kamera balra svenkelt, a
    tartalom jobbra ment) → a vonal a KOCKÁN 30 px-szel jobbra rajzolódik
    (G⁻¹)."""
    g = [[1.0, 0.0, -30.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    alap = overlay_pixels(_skala(10.0), None)[0][2]
    tolt = overlay_pixels(_skala(10.0), g)[0][2]
    assert abs(tolt[0] - (alap[0] + 30.0)) < 1e-6
    assert abs(tolt[1] - alap[1]) < 1e-6


def test_a_kepen_messze_kivul_eso_pont_kimarad():
    """Kép-méret mellett a képen messze kívüli pont elvágja a vonalat —
    nem húz vonalat a kép túloldalára."""
    px = overlay_pixels(_skala(10.0), None, width=100, height=100)
    # A 400x200 px-es pálya a 100x100-as képen: a (400, 200) sarok
    # 2*width-en túl van → nincs olyan pont, ami 200-nál nagyobb x-en ül.
    for vonal in px:
        for x, y in vonal:
            assert x <= 200.0 and y <= 200.0


def test_kulcskockak_ritkitasa_es_visszakeresese():
    fps = 8.0  # ritkított képráta
    lepes = int(round(PAN_KEYFRAME_S * fps))  # 16 kocka
    lista = [[[1.0, 0.0, float(i)], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
             for i in range(50)]
    lista[lepes] = None  # egy hiányzó mátrix: átugorjuk
    kf = sample_pan_keyframes(lista, fps)
    assert [k[0] for k in kf] == [0, 2 * lepes, 3 * lepes]
    # A t-hez az utolsó ≤ t kulcs tartozik; t=0 előtt / üres: egység.
    assert keyframe_at(kf, 3 * lepes + 5)[0][2] == float(3 * lepes)
    assert keyframe_at(kf, 2 * lepes - 1)[0][2] == 0.0
    assert keyframe_at([], 10) == EGYSEG
    assert keyframe_at(None, 10) == EGYSEG
    assert sample_pan_keyframes([], fps) == []


def test_a_meta_orzi_a_geometriat():
    from handball.models.tracking import Match, MatchMeta

    meta = MatchMeta(match_id="c", home_team="A", away_team="B", fps=8.0,
                     court_homography=_skala(10.0),
                     pan_keyframes=[[0, EGYSEG]])
    ujra = Match.from_json(Match(meta, []).to_json())
    assert ujra.meta.court_homography == _skala(10.0)
    assert ujra.meta.pan_keyframes == [[0, EGYSEG]]
    # Régi mentés: a mezők nélkül None.
    regi = Match.from_dict({"meta": {"match_id": "r", "home_team": "A",
                                     "away_team": "B", "fps": 8.0},
                            "frames": []})
    assert regi.meta.court_homography is None
    assert regi.meta.pan_keyframes is None


TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient


def test_a_vegpont_kapuorei(tmp_path):
    import json

    from handball.models.tracking import Match, MatchMeta

    os.environ["HANDBALL_DATA_DIR"] = str(tmp_path)
    d = tmp_path / "data" / "matches"
    d.mkdir(parents=True)
    regi = Match(MatchMeta(match_id="regi", home_team="A", away_team="B",
                           fps=8.0), [])
    geo = Match(MatchMeta(match_id="geo", home_team="A", away_team="B",
                          fps=8.0, court_homography=_skala(10.0),
                          video_path=str(tmp_path / "nincs.mp4")), [])
    for m in (regi, geo):
        (d / f"{m.meta.match_id}.json").write_text(
            json.dumps(m.to_dict()), encoding="utf-8")
    from handball.api.app import create_app
    c = TestClient(create_app())
    assert c.get("/matches/nincs/calib-overlay").status_code == 404
    r = c.get("/matches/regi/calib-overlay")
    assert r.status_code == 400 and "kalibráció-geometria" in r.json()["detail"]
    r = c.get("/matches/geo/calib-overlay?t=5")
    assert r.status_code == 400 and "videó" in r.json()["detail"]


def test_a_feldolgozas_elteszi_a_geometriat(tmp_path):
    """A VALÓDI feldolgozó-út (HOG, modell nélkül) kalibrációval: a meta
    megkapja a homográfiát és a kulcs-kocka listát — enélkül a
    finalize-ban egy elgépelt név minden kalibrált feldolgozást vinne."""
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    from scripts.process_video import process

    video = tmp_path / "mini.mp4"
    vw = cv2.VideoWriter(str(video), cv2.VideoWriter_fourcc(*"mp4v"),
                         25.0, (96, 64))
    rng = np.random.default_rng(1)
    for _ in range(20):
        vw.write(rng.integers(90, 200, size=(64, 96, 3), dtype=np.uint8))
    vw.release()
    # A 4 sarok a kép sarkai (bal-fent, jobb-fent, jobb-lent, bal-lent).
    m = process(str(video), None, weights=None, stride=1, max_frames=20,
                calib_corners=[(0, 0), (96, 0), (96, 64), (0, 64)])
    h0 = m.meta.court_homography
    assert h0 is not None and len(h0) == 3 and len(h0[0]) == 3
    # HOG-útvonalon nincs pásztázás-mátrix: a lista üres, de nem None.
    assert m.meta.pan_keyframes == []
    # A rárajzolás ebből már megy (pixelek a 96x64-es képen).
    px = overlay_pixels(h0, None, 96, 64)
    assert px and all(len(v) >= 2 for v in px)


def test_a_kamera_ut_osszegzese():
    from handball.pipeline.calib_overlay import camera_path_summary

    assert camera_path_summary(None) is None
    assert camera_path_summary([]) is None
    kf = [[0, EGYSEG],
          [16, [[1.0, 0.0, 30.0], [0.0, 1.0, 40.0], [0.0, 0.0, 1.0]]],
          [32, [[1.0, 0.0, 6.0], [0.0, 1.0, 8.0], [0.0, 0.0, 1.0]]]]
    o = camera_path_summary(kf)
    assert o["keyframes"] == 3
    assert o["max_shift_px"] == 50.0 and o["final_shift_px"] == 10.0
