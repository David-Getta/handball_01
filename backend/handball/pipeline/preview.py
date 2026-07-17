"""Detektálás-próba kalibráció-ellenőrzése — a végpontból kiemelt, tisztán
tesztelhető geometria.

A próbaképre rávetítjük a kalibrált pálya-modellt (keret, felezővonal,
kapuk, 6 m-es ívek), és megszámoljuk, hány talált játékos talp-pontja
esik a játéktérre méterben. Ha az arany vonalak nem illeszkednek a
valódi pályavonalakra, a kalibráció rossz — és ez MÉG az órákig tartó
feldolgozás előtt kiderül.
"""

from __future__ import annotations

import math

from ._homography import (
    apply_homography, homography_from_points, invert_3x3,
)
from .roi import CourtRegion

_GOLD_BGR = (107, 179, 216)
_RED_BGR = (107, 107, 255)


def draw_calibration_overlay(frame, persons, corners, region="full",
                             rotate=False) -> int:
    """A pálya-modell berajzolása + a pályán lévő játékosok megszámolása.

    - frame:   BGR kép (numpy tömb) — HELYBEN rajzolunk rá.
    - persons: [(x1, y1, x2, y2, ...), ...] — a talált játékos-dobozok.
    - corners: a kalibráció 4 kép-sarka [[x, y], ...].
    - region/rotate: mire illesztettük (mint a feldolgozásban).

    Visszatérés: hány játékos talp-pontja esik a játéktérre (méterben).
    Hibás bemenetre ValueError-t enged tovább — a hívó dönt a sorsáról.
    """
    import cv2

    from scripts.process_video import _calib_court_points

    pts_m = _calib_court_points(region, bool(rotate))
    hm = homography_from_points(
        pts_m, [tuple(map(float, p)) for p in corners])  # méter → kép

    def to_img(mx, my):
        x, y = apply_homography(hm, mx, my)
        return (int(round(x)), int(round(y)))

    xs = [p[0] for p in pts_m]
    x0, x1 = min(xs), max(xs)
    rect = [(x0, 0.0), (x1, 0.0), (x1, 20.0), (x0, 20.0)]
    for i in range(4):
        cv2.line(frame, to_img(*rect[i]), to_img(*rect[(i + 1) % 4]),
                 _GOLD_BGR, 2)
    if x0 <= 20.0 <= x1:  # felezővonal
        cv2.line(frame, to_img(20.0, 0.0), to_img(20.0, 20.0), _GOLD_BGR, 2)
    for gx in (0.0, 40.0):  # kapuk + 6 m-es ívek a látott feleken
        if not (x0 <= gx <= x1):
            continue
        cv2.line(frame, to_img(gx, 8.5), to_img(gx, 11.5), _RED_BGR, 4)
        d = 1.0 if gx == 0.0 else -1.0
        arc = [to_img(gx + d * 6.0 * math.cos(a), 10.0 + 6.0 * math.sin(a))
               for a in [(-math.pi / 2 + math.pi * k / 24)
                         for k in range(25)]]
        for a_, b_ in zip(arc, arc[1:]):
            cv2.line(frame, a_, b_, _GOLD_BGR, 2)

    # Hány játékos esik a játéktérre? (talp-pont: a doboz alsó közepe)
    inv = invert_3x3(hm)
    court = CourtRegion(margin_m=2.0)
    on_court = 0
    for box in persons:
        px1, _py1, px2, py2 = box[0], box[1], box[2], box[3]
        mx, my = apply_homography(inv, (px1 + px2) / 2.0, float(py2))
        if court.contains(mx, my):
            on_court += 1
    return on_court
