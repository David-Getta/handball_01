"""
Tesztek a TV-közvetítés elő-feldolgozására (broadcast.py): vágás-
felismerés, szakaszolás, totál/közeli osztályozás, használható-szűrő.

A tiszta magfüggvények (hist_distance, detect_cuts, segment_stream,
classify_segments, usable_segments) videó nélkül tesztelhetők; az
orchesztrátort (analyze_broadcast) pici szintetikus videóval.

Futtatás:
    python -m pytest tests/test_broadcast.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from handball.pipeline.broadcast import (
    classify_segments, detect_cuts, hist_distance, segment_stream,
    usable_segments,
)


def test_hist_distance_bounds():
    a = [1.0, 0.0, 0.0]
    b = [0.0, 0.0, 1.0]
    assert hist_distance(a, a) == 0.0
    assert hist_distance(a, b) == 1.0  # teljesen diszjunkt eloszlás
    # Fél átfedés: fél-L1 = 0,5.
    assert abs(hist_distance([0.5, 0.5, 0.0], [0.0, 0.5, 0.5]) - 0.5) < 1e-9


def test_detect_cuts_finds_jumps_and_respects_gap():
    # 3 "jelenet" hisztogramja, éles váltásokkal a 4. és 8. kockánál.
    scenes = ([[1.0, 0, 0]] * 4 + [[0, 1.0, 0]] * 4 + [[0, 0, 1.0]] * 4)
    cuts = detect_cuts(scenes, threshold=0.5, min_gap=2)
    assert cuts == [4, 8]
    # Nagyobb min_gap: a közeli második vágás elnyomódik.
    close = ([[1.0, 0, 0]] * 2 + [[0, 1.0, 0]] + [[0, 0, 1.0]] * 5)
    assert detect_cuts(close, threshold=0.5, min_gap=4) == [2]


def test_segment_stream_covers_all_frames():
    segs = segment_stream([4, 8], 12)
    assert segs == [(0, 3), (4, 7), (8, 11)]
    # Vágás nélkül egyetlen szakasz.
    assert segment_stream([], 5) == [(0, 4)]
    assert segment_stream([3], 0) == []


def test_classify_and_usable_segments():
    # Két szakasz: az első totál (magas szórtság), a második közeli.
    segs = [(0, 9), (10, 19)]
    spreads = [0.6] * 10 + [0.2] * 10
    cls = classify_segments(segs, spreads, wide_min=0.42)
    assert cls[0]["kind"] == "totál" and cls[1]["kind"] == "közeli"
    # 25 fps mellett a 10 kockás totál (0,4 mp) túl rövid a küszöbhöz (3 mp).
    assert usable_segments(cls, fps=25.0, min_wide_s=3.0) == []
    # Alacsonyabb küszöbnél a totál-szakasz átmegy.
    keep = usable_segments(cls, fps=25.0, min_wide_s=0.3)
    assert len(keep) == 1 and keep[0]["start"] == 0


def test_analyze_broadcast_on_synthetic_video(tmp_path):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")

    # "Közvetítés": 3 egyszínű jelenet (kék, zöld, piros) egymás után —
    # a jelenethatárokon éles hisztogram-ugrás = vágás.
    path = tmp_path / "broadcast.mp4"
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"),
                         25.0, (160, 90))
    colors = [(200, 40, 40), (40, 200, 40), (40, 40, 200)]
    for c in colors:
        for _ in range(30):  # ~1,2 mp jelenetenként
            img = np.full((90, 160, 3), c, np.uint8)
            img[::7, :] = 255  # kis textúra, hogy a spread ne legyen 0
            vw.write(img)
    vw.release()

    res = __import__("handball.pipeline.broadcast", fromlist=["analyze_broadcast"]).analyze_broadcast(
        str(path), stride=1)
    assert res["n_frames"] == 90
    # A két jelenethatár vágásként megjelenik (a ritkítatlan sorozaton).
    assert len(res["cuts"]) == 2
    assert all(28 <= c <= 32 or 58 <= c <= 62 for c in res["cuts"])
    # Három szakasz keletkezik.
    assert len(res["segments"]) == 3


# ---- Szín-hisztogram (color_histogram) ----------------------------------------

def test_color_histogram_normalt_es_a_szint_a_helyere_teszi():
    """A hisztogram bins³ hosszú, 1-re normált; egyszínű képnél a teljes
    tömeg EGY vödörben ül, és a képmérettől független."""
    pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    from handball.pipeline.broadcast import color_histogram

    kek = np.full((90, 160, 3), (200, 40, 40), np.uint8)          # BGR
    h = color_histogram(kek)
    assert h.shape == (8 ** 3,)
    assert abs(h.sum() - 1.0) < 1e-12
    assert h.max() == 1.0 and (h > 0).sum() == 1
    # Más felbontás, ugyanaz a szín → ugyanaz a hisztogram.
    nagy = np.full((360, 640, 3), (200, 40, 40), np.uint8)
    assert hist_distance(h, color_histogram(nagy)) == 0.0
    # Finomabb / durvább felosztás: a hossz bins³.
    assert color_histogram(kek, bins=4).shape == (64,)
    assert abs(color_histogram(kek, bins=4).sum() - 1.0) < 1e-12


def test_color_histogram_vagasnal_ugrik_jeleneten_belul_nem():
    """A vágás-detektálás alapja: két különböző színvilágú kocka
    hisztogramja diszjunkt (távolság 1), ugyanazon jelenet enyhén zajos
    kockáié közel azonos; félig-félig kép a kettő között van."""
    pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    from handball.pipeline.broadcast import CUT_THRESHOLD, color_histogram

    kek = np.full((90, 160, 3), (200, 40, 40), np.uint8)
    zold = np.full((90, 160, 3), (40, 200, 40), np.uint8)
    assert hist_distance(color_histogram(kek), color_histogram(zold)) == 1.0
    # Enyhe zaj a vödrön belül (±3 intenzitás): nincs vágás.
    rng = np.random.default_rng(7)
    zajos = (kek.astype(np.int16)
             + rng.integers(-3, 4, kek.shape)).clip(0, 255).astype(np.uint8)
    assert hist_distance(color_histogram(kek),
                         color_histogram(zajos)) < CUT_THRESHOLD
    # Félig kék, félig zöld kép: a tömeg két vödörben fele-fele.
    fele = kek.copy()
    fele[:, 80:] = (40, 200, 40)
    hf = color_histogram(fele)
    assert sorted(hf[hf > 0].tolist()) == [0.5, 0.5]
    assert abs(hist_distance(hf, color_histogram(kek)) - 0.5) < 1e-12
    hists = [color_histogram(k) for k in [kek] * 8 + [zold] * 8]
    assert detect_cuts(hists) == [8]


def test_color_histogram_ures_hisztogramra_nem_oszt_nullaval(monkeypatch):
    """Ha a nyers hisztogram üres (nulla összegű — pl. nulla pixeles
    kivágás), nincs mit normálni: csupa nulla vektor, nem NaN és nem
    kivétel. (A nyers számlálást itt helyettesítjük, hogy a teszt ne az
    OpenCV üres-kép viselkedésén múljon.)"""
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    from handball.pipeline.broadcast import color_histogram

    monkeypatch.setattr(cv2, "calcHist",
                        lambda *a, **k: np.zeros((8, 8, 8), np.float32))
    h = color_histogram(np.zeros((4, 4, 3), np.uint8))
    assert h.shape == (512,)
    assert not np.isnan(h).any() and h.sum() == 0.0


# ---- A tartalom térbeli szórtsága (content_spread) ----------------------------

def test_content_spread_total_nagy_kozeli_kicsi():
    """Totálkép: az élek (pályavonalak, sok kis alak) a kép egészén
    szétterülnek → a szórtság a totál-küszöb fölött; közeli: az élek egy
    kis területre sűrűsödnek → jóval alatta."""
    pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    from handball.pipeline.broadcast import WIDE_SPREAD_MIN, content_spread

    total = np.zeros((180, 320, 3), np.uint8)
    total[::12, :] = 255                      # vonalak az egész képen
    total[:, ::16] = 255
    kozeli = np.zeros((180, 320, 3), np.uint8)
    kozeli[80:100, 150:170] = 255             # egyetlen kis folt középen
    s_total, s_kozeli = content_spread(total), content_spread(kozeli)
    assert 0.0 <= s_kozeli < s_total <= 1.0
    assert s_total >= WIDE_SPREAD_MIN
    assert s_kozeli < WIDE_SPREAD_MIN / 2
    # A folt helye nem számít (a súlypont körüli szórást mérjük).
    sarok = np.zeros((180, 320, 3), np.uint8)
    sarok[10:30, 10:30] = 255
    assert abs(content_spread(sarok) - s_kozeli) < 1e-6


def test_content_spread_el_nelkuli_kepen_nulla():
    """Egyszínű (él nélküli) képen nincs mit mérni: 0,0 — nem NaN, nem
    osztás nullával; a szórtság felső korlátja 1,0."""
    pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    from handball.pipeline.broadcast import content_spread

    assert content_spread(np.full((90, 160, 3), 120, np.uint8)) == 0.0
    assert content_spread(np.zeros((90, 160, 3), np.uint8)) == 0.0
    # Két átellenes sarokba tett él-energia: a lehető legnagyobb szórás,
    # a korlát (1,0) mégsem lépődik át.
    ket_sarok = np.zeros((90, 160, 3), np.uint8)
    ket_sarok[0:3, 0:3] = 255
    ket_sarok[87:90, 157:160] = 255
    assert content_spread(ket_sarok) == 1.0
