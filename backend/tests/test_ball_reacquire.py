"""
Tesztek a labda-visszaszerzés logikájára (ball_reacquire.py).

Futtatás:
    python -m pytest tests/test_ball_reacquire.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.pipeline.ball_reacquire import BallReacquirer


def test_predicts_linear_motion():
    r = BallReacquirer()
    r.note(0, (100.0, 200.0))
    r.note(3, (130.0, 215.0))  # 10 px/kocka x, 5 px/kocka y
    p = r.predict(5)
    assert p is not None
    assert abs(p[0] - 150.0) < 1e-6 and abs(p[1] - 225.0) < 1e-6


def test_single_observation_predicts_last_position():
    r = BallReacquirer()
    r.note(10, (300.0, 100.0))
    assert r.predict(12) == (300.0, 100.0)


def test_no_prediction_without_history_or_after_long_gap():
    r = BallReacquirer(max_gap=20)
    assert r.predict(5) is None  # nincs előzmény
    r.note(0, (100.0, 100.0))
    assert r.predict(21) is None  # túl régi — nem találgatunk
    assert r.predict(0) is None   # nem a jövő


def test_roi_clamped_to_image():
    r = BallReacquirer(roi_px=320)
    r.note(0, (10.0, 10.0))  # a kép sarkában
    roi = r.roi_for(2, 1920, 1080)
    assert roi is not None
    x1, y1, x2, y2 = roi
    assert x1 == 0 and y1 == 0 and x2 - x1 == 320 and y2 - y1 == 320
    # Jobb-alsó sarok: a kivágás a képen belül marad.
    r2 = BallReacquirer(roi_px=320)
    r2.note(0, (1915.0, 1075.0))
    x1, y1, x2, y2 = r2.roi_for(2, 1920, 1080)
    assert x2 <= 1920 and y2 <= 1080 and x2 - x1 == 320 and y2 - y1 == 320


def test_map_back_translates_roi_coordinates():
    roi = (100, 200, 420, 520)
    assert BallReacquirer.map_back(roi, 50.0, 60.0) == (150.0, 260.0)


def test_note_none_keeps_history():
    """A "nem találtuk" kockák nem törlik az előzményt — a kiesés alatt
    végig az utolsó észlelésekből extrapolálunk."""
    r = BallReacquirer()
    r.note(0, (100.0, 100.0))
    r.note(1, (110.0, 100.0))
    for t in range(2, 8):
        r.note(t, None)
    p = r.predict(8)
    assert p is not None and abs(p[0] - 180.0) < 1e-6


if __name__ == "__main__":
    test_predicts_linear_motion()
    test_single_observation_predicts_last_position()
    test_no_prediction_without_history_or_after_long_gap()
    test_roi_clamped_to_image()
    test_map_back_translates_roi_coordinates()
    test_note_none_keeps_history()
    print("Minden labda-visszaszerzés teszt OK.")
