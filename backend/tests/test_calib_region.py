"""A térfél-kalibráció cél-pontjainak tesztjei (forgatással együtt)."""
from scripts.process_video import _calib_court_points


def test_full_court_default():
    pts = _calib_court_points()
    assert pts == [(0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0)]


def test_left_half():
    pts = _calib_court_points("left")
    assert pts == [(0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)]


def test_right_half():
    pts = _calib_court_points("right")
    assert pts == [(20.0, 0.0), (40.0, 0.0), (40.0, 20.0), (20.0, 20.0)]


def test_rotate_full():
    # 180°: a képen bejelölt 1. sarok a pálya átellenes sarkának felel meg.
    pts = _calib_court_points("full", rotate=True)
    assert pts == [(40.0, 20.0), (0.0, 20.0), (0.0, 0.0), (40.0, 0.0)]


def test_rotate_half_stays_in_half():
    # Forgatva is a KIVÁLASZTOTT térfélen belül maradnak a cél-pontok.
    pts = _calib_court_points("right", rotate=True)
    xs = [p[0] for p in pts]
    assert min(xs) == 20.0 and max(xs) == 40.0


def test_unknown_region_falls_back_to_full():
    assert _calib_court_points("nonsense") == _calib_court_points("full")
