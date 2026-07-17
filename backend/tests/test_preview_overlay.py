"""
Tesztek a detektálás-próba kalibráció-ellenőrzésére (pipeline/preview.py).

Futtatás:
    python -m pytest tests/test_preview_overlay.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

cv2 = pytest.importorskip("cv2", reason="OpenCV nincs telepítve")
np = pytest.importorskip("numpy", reason="numpy nincs telepítve")

from handball.pipeline.preview import draw_calibration_overlay


def _frame(w=800, h=400):
    return np.zeros((h, w, 3), np.uint8)


# Egyszerű kalibráció: a pálya (40x20 m) a kép [100..700]x[50..350]
# téglalapjára képződik — 15 px/m vízszintesen, 15 px/m függőlegesen.
_CORNERS = [[100, 50], [700, 50], [700, 350], [100, 350]]


def _px(mx, my):
    return (100 + mx * 15.0, 50 + my * 15.0)


def test_overlay_draws_and_counts_on_court():
    frame = _frame()
    # Egy játékos a pálya közepén (talp-pont ~ (20 m, 10 m)), egy a lelátón.
    fx, fy = _px(20.0, 10.0)
    inside = (int(fx) - 10, int(fy) - 40, int(fx) + 10, int(fy))
    outside = (750, 10, 790, 40)  # messze a pályán kívül
    n = draw_calibration_overlay(frame, [inside, outside], _CORNERS)
    assert n == 1
    # A modell-vonalak tényleg a képre kerültek (nem maradt fekete).
    assert int(frame.sum()) > 0


def test_overlay_margin_tolerance():
    """A vonalon kicsit kívül álló játékos (2 m-es tűrés) még pályán van."""
    frame = _frame()
    fx, fy = _px(-1.0, 10.0)  # 1 m-rel az alapvonalon kívül
    box = (int(fx) - 8, int(fy) - 30, int(fx) + 8, int(fy))
    assert draw_calibration_overlay(frame, [box], _CORNERS) == 1
    fx, fy = _px(-5.0, 10.0)  # 5 m-re kívül: lelátó/kispad
    box = (int(fx) - 8, int(fy) - 30, int(fx) + 8, int(fy))
    assert draw_calibration_overlay(frame, [box], _CORNERS) == 1 - 1


def test_overlay_bad_corners_raise():
    """Hibás sarok-lista: a kivétel a hívóé (a végpont None-ra ejti)."""
    with pytest.raises(Exception):
        draw_calibration_overlay(_frame(), [], [[0, 0], [1, 1]])
