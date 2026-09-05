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


def _vonalas_kep(h0, g, w=480, h=240):
    """Sötét kép, amire a pálya vonalait FEHÉRREL rárajzoljuk a (h0, g)
    vetítéssel — ez a "valódi" pálya a videón."""
    import numpy as np
    from handball.pipeline.calib_overlay import draw_overlay
    img = np.full((h, w, 3), 30, np.uint8)
    draw_overlay(img, overlay_pixels(h0, g, w, h), color=(255, 255, 255),
                 thickness=2)
    return img[:, :, 0]


def test_a_vonal_illeszkedes_a_jo_helyen_magas_a_melle_csuszottnal_alacsony():
    from handball.pipeline.calib_overlay import line_fit_score

    h0 = _skala(10.0)  # a 40x20 m-es pálya 400x200 px
    kep = _vonalas_kep(h0, None)
    jo = line_fit_score(kep, overlay_pixels(h0, None, 480, 240))
    assert jo["samples"] >= 20 and jo["fit"] is not None
    assert jo["fit"] > 0.6, jo
    # Ugyanaz a kép, de a rajz 25 px-szel odébb: a vonal a padlón fut.
    g = [[1.0, 0.0, -25.0], [0.0, 1.0, -12.0], [0.0, 0.0, 1.0]]
    rossz = line_fit_score(kep, overlay_pixels(h0, g, 480, 240))
    assert rossz["fit"] is not None and rossz["fit"] < jo["fit"] - 0.3, (jo, rossz)


def test_a_vonal_illeszkedes_kevés_mintanal_none():
    import numpy as np
    from handball.pipeline.calib_overlay import line_fit_score

    kep = np.zeros((50, 50), np.uint8)
    # A vonalak a képen messze kívül (1 px = 1 m → 40x20 px, de eltolva).
    g = [[1.0, 0.0, -500.0], [0.0, 1.0, -500.0], [0.0, 0.0, 1.0]]
    o = line_fit_score(kep, overlay_pixels(_skala(1.0), g, 50, 50))
    assert o["fit"] is None and o["samples"] < 20


def test_a_calib_fit_vegpont_kapuorei(tmp_path):
    import json

    from handball.models.tracking import Frame, Match, MatchMeta

    os.environ["HANDBALL_DATA_DIR"] = str(tmp_path)
    d = tmp_path / "data" / "matches"
    d.mkdir(parents=True)
    regi = Match(MatchMeta(match_id="regi", home_team="A", away_team="B",
                           fps=8.0), [Frame(t=0, players=[])])
    geo = Match(MatchMeta(match_id="geo", home_team="A", away_team="B",
                          fps=8.0, court_homography=_skala(10.0),
                          video_path=str(tmp_path / "nincs.mp4")),
                [Frame(t=0, players=[])])
    for m in (regi, geo):
        (d / f"{m.meta.match_id}.json").write_text(
            json.dumps(m.to_dict()), encoding="utf-8")
    from handball.api.app import create_app
    c = TestClient(create_app())
    assert c.get("/matches/nincs/calib-fit").status_code == 404
    r = c.get("/matches/regi/calib-fit")
    assert r.status_code == 400 and "kalibráció-geometria" in r.json()["detail"]
    r = c.get("/matches/geo/calib-fit?n=4")
    assert r.status_code == 400 and "videó" in r.json()["detail"]


def test_az_illeszkedes_osszegzese_es_a_minoseg_jelzes():
    """A feldolgozás alatt mért pontokból a meta-összegzés, és a
    minőség-jelentés a LEGGYENGÉBB kockából szól (az átlag elrejtené a
    meccs közepén elcsúszó követést) — teendővel."""
    from handball.models.tracking import Frame, Match, MatchMeta
    from handball.pipeline.calib_overlay import fit_summary
    from handball.pipeline.quality import (CALIB_FIT_WARN,
                                           compute_quality_report)

    assert fit_summary([]) is None
    assert fit_summary([(0, None)]) is None
    o = fit_summary([(0, 0.8), (16, None), (32, 0.2), (48, 0.7)])
    assert o["min_fit"] == 0.2 and o["worst_t"] == 32
    assert abs(o["mean_fit"] - 0.567) < 0.001
    assert CALIB_FIT_WARN > 0.2

    def _meccs(cf):
        meta = MatchMeta(match_id="cf", home_team="A", away_team="B",
                         fps=10.0, calib_fit=cf)
        return Match(meta, [Frame(t=i, players=[]) for i in range(100)])

    q = compute_quality_report(_meccs(o))
    talalat = [w for w in q["warnings"]
               if "pályavonal nem ül a kép valódi vonalain" in w]
    assert talalat and "0:03" in talalat[0], q["warnings"]
    assert q["next_action"] and "Kalibráció ellenőrzését" in q["next_action"]
    # Jó illeszkedésnél és régi mentésen (None) csend.
    jo = fit_summary([(0, 0.8), (32, 0.6)])
    for cf in (jo, None):
        q2 = compute_quality_report(_meccs(cf))
        assert not [w for w in q2["warnings"] if "pályavonal" in w]


def test_az_onkorrekcio_megtalalja_az_eltolast():
    """A kép vonalai 14 px-szel jobbra, 6-tal lejjebb vannak ahhoz képest,
    ahova a (rossz) kamera-mátrix rajzolna: a finomítás megtalálja az
    eltolást, az igazított G-vel a rajz már ül (fit magas)."""
    from handball.pipeline.calib_overlay import (edge_map, refine_shift,
                                                 shifted_g)

    h0 = _skala(10.0)
    # A VALÓDI vonalak a képen: G_igaz szerint (a kamera 14 px-t
    # balra, 6-ot felfelé svenkelt → a tartalom jobbra-le ment).
    g_igaz = [[1.0, 0.0, -14.0], [0.0, 1.0, -6.0], [0.0, 0.0, 1.0]]
    kep = _vonalas_kep(h0, g_igaz)
    sav, alap = edge_map(kep)
    # A becsült G elmaradt (egység): a rajz 14 px-szel balra ül.
    r = refine_shift(sav, alap, h0, None, 480, 240)
    assert r["fit0"] is not None and r["fit"] > r["fit0"] + 0.3, r
    assert abs(r["dx"] - 14.0) <= 2.0 and abs(r["dy"] - 6.0) <= 2.0, r
    # Az igazított G-vel a rajz a valódira ül.
    g_uj = shifted_g(None, r["dx"], r["dy"])
    assert abs(g_uj[0][2] + 14.0) <= 2.0 and abs(g_uj[1][2] + 6.0) <= 2.0
    px = overlay_pixels(h0, g_uj, 480, 240)
    from handball.pipeline.calib_overlay import fit_on_edge_map
    assert fit_on_edge_map(sav, alap, px)["fit"] >= r["fit"] - 0.05


def test_az_onkorrekcio_jo_helyen_nem_mozdit():
    from handball.pipeline.calib_overlay import edge_map, refine_shift

    h0 = _skala(10.0)
    kep = _vonalas_kep(h0, None)
    sav, alap = edge_map(kep)
    r = refine_shift(sav, alap, h0, None, 480, 240)
    assert abs(r["dx"]) <= 2.0 and abs(r["dy"]) <= 2.0, r
