"""
Tesztek a pályavonal-felismerésre (broadcast_lines.py) — szintetikus
képekkel, valódi közvetítés nélkül.

Futtatás:
    python -m pytest tests/test_broadcast_lines.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from handball.pipeline.broadcast_lines import (
    detect_court_lines, edge_mask, hough_lines,
)


def _canvas(h=120, w=200, floor=100):
    return np.full((h, w), floor, dtype=np.uint8)


def _draw_hline(img, y, val=220, thickness=2):
    img[y:y + thickness, :] = val


def _draw_vline(img, x, val=220, thickness=2):
    img[:, x:x + thickness] = val


def test_edge_mask_marks_thin_bright_line():
    img = _canvas()
    _draw_hline(img, 60)
    mask = edge_mask(img)
    # A vonal pixelei jelölve, a padló nem.
    assert mask[60, 100]
    assert not mask[30, 100]


def test_hough_finds_horizontal_and_vertical():
    img = _canvas()
    _draw_hline(img, 60)     # vízszintes vonal: normálisa 90 fok
    _draw_vline(img, 150)    # függőleges vonal: normálisa 0 fok
    lines = hough_lines(edge_mask(img))
    assert len(lines) >= 2
    angles = sorted(abs(t) for (t, _, _) in lines[:2])
    assert angles[0] < 6.0                # függőleges (normálisa ~0 fok)
    assert abs(angles[1] - 90.0) < 6.0    # vízszintes (normálisa ~90 fok)


def test_detect_court_lines_returns_endpoints():
    img = _canvas()
    _draw_hline(img, 40)
    out = detect_court_lines(img)
    assert out, "legalább egy vonal kell"
    top = out[0]
    (x1, y1), (x2, y2) = top["p1"], top["p2"]
    # A vízszintes vonal végpontjai a kép két szélén, y ~ 40-41.
    assert abs(y1 - 40.5) < 3 and abs(y2 - 40.5) < 3
    assert abs(x1 - x2) > 150


def test_empty_image_gives_no_lines():
    assert detect_court_lines(_canvas()) == []


def test_line_intersections_finds_corner():
    """Vízszintes + függőleges vonal metszése a (150, 40) sarok-jelölt;
    két párhuzamos vonal nem ad metszést."""
    from handball.pipeline.broadcast_lines import line_intersections
    img = _canvas()
    _draw_hline(img, 40)
    _draw_vline(img, 150)
    lines = detect_court_lines(img)
    pts = line_intersections(lines, width=200, height=120)
    assert pts, "kell metszéspont"
    p = pts[0]
    assert abs(p["x"] - 150.5) < 4 and abs(p["y"] - 40.5) < 4
    # Két párhuzamos vízszintes vonal: nincs (képen belüli) metszés.
    img2 = _canvas()
    _draw_hline(img2, 30)
    _draw_hline(img2, 80)
    lines2 = detect_court_lines(img2)
    assert line_intersections(lines2, width=200, height=120) == []
