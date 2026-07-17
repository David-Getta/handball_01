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
