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


def test_a_finomitas_gyors_nagy_kepen():
    """A finomítás ~130 jelöltet próbál; 1920x1080-on is bőven egy
    másodperc alatt kell maradnia (a feldolgozás alatt fut, 2 mp-enként)."""
    import time
    from handball.pipeline.calib_overlay import edge_map, refine_shift

    h0 = [[1.0 / 40.0, 0.0, 0.0], [0.0, 1.0 / 40.0, 0.0], [0.0, 0.0, 1.0]]
    kep = _vonalas_kep(h0, [[1.0, 0.0, -10.0], [0.0, 1.0, 4.0],
                            [0.0, 0.0, 1.0]], w=1920, h=1080)
    sav, alap = edge_map(kep)
    t0 = time.perf_counter()
    r = refine_shift(sav, alap, h0, None, 1920, 1080)
    assert time.perf_counter() - t0 < 1.5
    assert abs(r["dx"] - 10.0) <= 3.0 and abs(r["dy"] + 4.0) <= 3.0, r


def test_a_meres_es_onkorrekcio_egyben_a_kovetovel():
    """A feldolgozó lépése a VALÓDI követővel (YOLO nélkül): a kép
    vonalai 16 px-szel odébb, a követő G-je elmaradt → a mérés alacsony,
    a korrekció megtalálja, a követő átveszi; horgonyzott kockán nem
    nyúl hozzá; jó helyen nincs korrekció."""
    from handball.pipeline.calib_overlay import measure_and_correct
    from handball.pipeline.pan_tracking import PanTracker

    h0 = _skala(10.0)
    g_igaz = [[1.0, 0.0, -16.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    kep = _vonalas_kep(h0, g_igaz)
    tr = PanTracker(anchor=False)
    panH = tr.update(kep)  # első kocka: egység (elmaradt a valóditól)

    ki = measure_and_correct(kep, h0, panH, last_mode="chain")
    assert ki["corrected"] is True and abs(ki["dx"] - 16.0) <= 3.0, ki
    assert ki["fit"] > 0.6
    tr.correct(ki["g"])
    assert tr.stats["corrected"] == 1
    assert abs(tr.translation[0] + 16.0) <= 3.0

    # Horgonyzott kockán: mérés igen, korrekció nem.
    ki2 = measure_and_correct(kep, h0, panH, last_mode="anchor")
    assert ki2["corrected"] is False and ki2["fit"] is not None

    # Jó helyen (a követő már igazított): nincs mit korrigálni.
    ki3 = measure_and_correct(kep, h0, ki["g"], last_mode="chain")
    assert ki3["corrected"] is False and ki3["fit"] > 0.6


def test_a_nyomtatott_jelentes_mutatja_az_illeszkedest():
    """A nyomtatott jelentés olvasója (más edző, vezetőség) ebből látja,
    mennyire ültek a pályavonalak a videón. Régi mentésen (mérés nélkül)
    a sor egyszerűen kimarad — nem "0%"-ot állítunk."""
    from handball.pipeline.quality import compute_quality_report
    from handball.pipeline.report_html import match_report_html
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=90, fps=10.0, seed=7)
    m.meta.calibrated = True
    nelkul = match_report_html(m, {}, [], compute_quality_report(m))
    assert "Kalibráció-illeszkedés" not in nelkul

    m.meta.calib_fit = {"mean_fit": 0.72, "min_fit": 0.41, "worst_t": 30,
                        "points": [[0, 0.72], [30, 0.41]]}
    html = match_report_html(m, {}, [], compute_quality_report(m))
    assert "Kalibráció-illeszkedés" in html
    assert "72%" in html and "leggyengébb 41%" in html


def test_a_fel_palyas_kalibracio_csak_a_sajat_terfelet_rajzolja():
    """FÉL-PÁLYÁS kalibrációnál a másik térfélen a homográfia erősen
    extrapolál — ott a rajz eleve nem ülhet a valódin. Ha mégis
    bevennénk, a mért illeszkedés fele akkora lenne, és a jelentés
    hibát kiáltana egy hibátlan kalibrációra."""
    from handball.pipeline.calib_overlay import court_polylines

    tel = court_polylines()
    bal = court_polylines("left")
    jobb = court_polylines("right")
    # Teljes: téglalap + felező + 2 kapuelőtér + 2 kapu = 6 vonal.
    assert len(tel) == 6 and len(bal) == 4 and len(jobb) == 4
    # A bal térfél rajza nem megy a felezőn túlra (x <= 20 m).
    assert max(x for v in bal for x, _ in v) <= 20.0 + 1e-9
    assert min(x for v in jobb for x, _ in v) >= 20.0 - 1e-9
    # A pixelekre is átüt (a régió a hívási láncban végigmegy).
    px_tel = overlay_pixels(_skala(10.0), None, 480, 240)
    px_bal = overlay_pixels(_skala(10.0), None, 480, 240, "left")
    assert len(px_bal) < len(px_tel)


def test_a_meta_orzi_a_kalibralt_terfelet():
    from handball.models.tracking import Match, MatchMeta

    meta = MatchMeta(match_id="r", home_team="A", away_team="B", fps=8.0,
                     calib_region="left")
    ujra = Match.from_json(Match(meta, []).to_json())
    assert ujra.meta.calib_region == "left"
    regi = Match.from_dict({"meta": {"match_id": "r2", "home_team": "A",
                                     "away_team": "B", "fps": 8.0},
                            "frames": []})
    assert regi.meta.calib_region is None


def test_mindket_vegpont_a_kalibralt_terfelet_hasznalja():
    """ŐR: a rárajzoló (calib-overlay) ÉS a mérő (calib-fit) végpont is
    a tárolt régióval dolgozik — ha csak az egyik, a kép és a szám
    ellentmondana egymásnak."""
    from pathlib import Path as _Path
    forras = (_Path(__file__).resolve().parent.parent / "handball" / "api"
              / "app.py").read_text(encoding="utf-8")
    # A közös segéd adja a párokat (két térfél-kalibrációnál mindkettőt,
    # régi mentésen az egyetlen homográfiát) — MINDKÉT végpont ezt hívja.
    assert "def calib_pairs_of(match)" in forras
    assert forras.count("calib_pairs_of(match)") >= 2
    assert 'getattr(match.meta, "calib_region", None) or "full"' in forras


def test_ket_kalibraciobol_a_jobban_illeszkedo_szamit():
    """Két kalibrációnál (bal + jobb térfél) a svenkelő kamera hol az
    egyik, hol a másik felet nézi: a mérés MINDKETTŐT megpróbálja, és a
    jobban illeszkedőt veszi — a képen kívüli fél magától kiesik."""
    from handball.pipeline.calib_overlay import measure_and_correct

    h0 = _skala(10.0)                     # a valódi vonalak ezzel állnak
    rossz = _skala(6.0)                   # ez mellémenne
    kep = _vonalas_kep(h0, None, w=480, h=240)

    # Csak a rosszal: gyenge illeszkedés.
    csak_rossz = measure_and_correct(kep, rossz, None, "anchor")
    # A kettő közül a jó számít (a párokat listaként adjuk át).
    parban = measure_and_correct(kep, [(rossz, "full"), (h0, "full")],
                                 None, "anchor")
    assert parban["fit"] is not None
    assert parban["fit"] > (csak_rossz["fit"] or 0.0) + 0.2, (
        csak_rossz, parban)
    # Egy homográfia átadása továbbra is működik (visszafelé kompatibilis).
    egy = measure_and_correct(kep, h0, None, "anchor")
    assert abs((egy["fit"] or 0) - parban["fit"]) < 1e-9


def test_a_calib_parok_visszafele_kompatibilisek():
    """A közös segéd: új mentésen a párok, RÉGI mentésen az egyetlen
    homográfia + régió, geometria nélkül üres lista."""
    from handball.api.app import calib_pairs_of
    from handball.models.tracking import Match, MatchMeta

    def _m(**kw):
        return Match(MatchMeta(match_id="x", home_team="A", away_team="B",
                               fps=8.0, **kw), [])

    assert calib_pairs_of(_m()) == []
    egy = calib_pairs_of(_m(court_homography=_skala(10.0),
                            calib_region="left"))
    assert egy == [(_skala(10.0), "left")]
    ketto = calib_pairs_of(_m(
        court_homography=_skala(10.0), calib_region="left",
        calib_pairs=[[_skala(10.0), "left"], [_skala(8.0), "right"]]))
    assert len(ketto) == 2 and ketto[1][1] == "right"
