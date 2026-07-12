"""
Tesztek a mezszám-OCR prototípusra (jersey_ocr.py) — szintetikus mezekkel.

Futtatás:
    python -m pytest tests/test_jersey_ocr.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

from handball.pipeline.jersey_ocr import JerseyVoter, read_jersey_number


def _jersey_crop(number: int, light_on_dark: bool = True, size=(120, 120)):
    """Szintetikus mez-kivágás: egyszínű "mez" + nagy szám a közepén."""
    bg = 40 if light_on_dark else 215
    fg = 235 if light_on_dark else 30
    img = np.full((size[1], size[0], 3), bg, np.uint8)
    text = str(number)
    scale = 2.2 if len(text) == 1 else 1.8
    tw = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 4)[0]
    org = ((size[0] - tw[0]) // 2, (size[1] + tw[1]) // 2)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale,
                (fg, fg, fg), 4)
    return img


def test_reads_single_and_double_digits():
    for number in (7, 23, 5, 41):
        r = read_jersey_number(_jersey_crop(number))
        assert r is not None, f"nem olvasta le: {number}"
        assert r[0] == number, f"várt {number}, lett {r[0]} (conf {r[1]:.2f})"


def test_reads_dark_number_on_light_jersey():
    r = read_jersey_number(_jersey_crop(18, light_on_dark=False))
    assert r is not None and r[0] == 18


def test_rejects_blank_and_tiny_crops():
    blank = np.full((120, 120, 3), 60, np.uint8)
    assert read_jersey_number(blank) is None
    tiny = np.full((10, 10, 3), 60, np.uint8)
    assert read_jersey_number(tiny) is None
    assert read_jersey_number(None) is None


def test_voter_needs_votes_and_margin():
    v = JerseyVoter(min_votes=3.0, min_margin=2.0)
    v.add(1, 23)
    v.add(1, 23)
    assert v.decide(1) is None  # kevés szavazat
    v.add(1, 23)
    assert v.decide(1) == 23
    # Zajos, megosztott track: nincs elég előny → nincs döntés.
    v.add(2, 7)
    v.add(2, 7)
    v.add(2, 7)
    v.add(2, 1)
    v.add(2, 1)
    assert v.decide(2) is None
    # További 7-esek: az előny meglesz.
    v.add(2, 7)
    v.add(2, 7)
    v.add(2, 7)
    assert v.decide(2) == 7


def test_voter_decisions_format_matches_jerseys_store():
    v = JerseyVoter(min_votes=1.0, min_margin=1.0)
    v.add(4, 11)
    v.add(9, 32)
    v.add(5, 150)  # érvénytelen szám — eldobjuk
    d = v.decisions()
    assert d == {4: 11, 9: 32}


def test_end_to_end_ocr_plus_voter():
    """A felismerő + szavazó együtt: több zajos kivágásból stabil döntés."""
    v = JerseyVoter(min_votes=2.0, min_margin=1.5)
    rng = np.random.default_rng(3)
    for _ in range(6):
        crop = _jersey_crop(9)
        noise = rng.integers(0, 18, crop.shape, dtype=np.uint8)
        r = read_jersey_number(cv2.add(crop, noise))
        if r is not None:
            v.add(1, r[0], r[1])
    assert v.decide(1) == 9


if __name__ == "__main__":
    test_reads_single_and_double_digits()
    test_reads_dark_number_on_light_jersey()
    test_rejects_blank_and_tiny_crops()
    test_voter_needs_votes_and_margin()
    test_voter_decisions_format_matches_jerseys_store()
    test_end_to_end_ocr_plus_voter()
    print("Minden mezszám-OCR teszt OK.")
