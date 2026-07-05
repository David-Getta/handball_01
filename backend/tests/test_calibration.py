"""
Tesztek a kalibráció (homográfia) matematikájára.

Mind tiszta Python, szintetikus pontokkal — nincs videó, nincs külső csomag.
Az alapötlet: veszünk egy ISMERT homográfiát, generálunk vele pont-párokat, majd
ellenőrizzük, hogy a kódunk visszaadja-e ugyanazt a leképezést.

Futtatás:
    python tests/test_calibration.py
"""

from __future__ import annotations

# A backend/ mappát a kereső-útvonalra tesszük, hogy a teszt bárhonnan fusson.
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.pipeline._homography import (
    solve_linear, homography_from_points, apply_homography,
)
from handball.pipeline.calibration import Calibrator, standard_court_landmarks


def test_solve_linear_simple():
    """A lineáris megoldó helyesen old meg egy ismert 2x2 rendszert.

    2x + y = 5 ; x + 3y = 10  ->  x = 1, y = 3
    """
    x = solve_linear([[2.0, 1.0], [1.0, 3.0]], [5.0, 10.0])
    assert abs(x[0] - 1.0) < 1e-9
    assert abs(x[1] - 3.0) < 1e-9


def _ground_truth_h():
    """Egy tetszőleges, de valódi perspektívát tartalmazó ismert homográfia."""
    return [
        [1.2, 0.1, 30.0],
        [0.05, 1.1, 20.0],
        [0.001, 0.002, 1.0],
    ]


def test_homography_recovers_known_mapping():
    """Ismert H-ból generált párokból visszanyerjük ugyanazt a leképezést.

    Nem a mátrix-elemeket hasonlítjuk (skálázás miatt csúszhatnak), hanem azt,
    hogy egy FÜGGETLEN tesztpontot ugyanoda képez-e a visszanyert H.
    """
    h_gt = _ground_truth_h()
    src = [(100.0, 50.0), (900.0, 60.0), (920.0, 700.0), (120.0, 680.0), (500.0, 360.0)]
    dst = [apply_homography(h_gt, px, py) for (px, py) in src]

    h_est = homography_from_points(src, dst)

    for (px, py) in [(300.0, 200.0), (640.0, 480.0), (800.0, 100.0)]:
        gx, gy = apply_homography(h_gt, px, py)
        ex, ey = apply_homography(h_est, px, py)
        assert abs(gx - ex) < 1e-4, f"x eltérés: {gx} vs {ex}"
        assert abs(gy - ey) < 1e-4, f"y eltérés: {gy} vs {ey}"


def test_calibrate_reference_maps_corners():
    """A Calibrator a kép-sarkokat a megadott pálya-sarkokra képezi.

    4 kép-pixel sarkot a 40x20 m-es pálya 4 sarkára kalibrálunk, majd ellenőrizzük,
    hogy a kép közepe nagyjából a pálya közepére (20,10) képződik.
    """
    image_corners = [(0.0, 0.0), (1920.0, 0.0), (1920.0, 1080.0), (0.0, 1080.0)]
    court_corners = [(0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0)]

    calib = Calibrator().calibrate_reference(image_corners, court_corners)
    assert calib.homography is not None

    # Sarok-ellenőrzés: a (0,0) pixel a (0,0) méterre megy.
    x0, y0 = calib.image_to_court(0.0, 0.0)
    assert abs(x0) < 1e-6 and abs(y0) < 1e-6

    # A kép közepe (960,540) a pálya közepére (20,10) — itt affin, így pontos.
    xc, yc = calib.image_to_court(960.0, 540.0)
    assert abs(xc - 20.0) < 1e-6
    assert abs(yc - 10.0) < 1e-6


def test_singular_points_raise():
    """Egy vonalba eső (elfajult) pontoknál a homográfia hibát jelez."""
    src = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)]   # mind egy vízszintesen
    dst = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0)]
    try:
        homography_from_points(src, dst)
        assert False, "elfajult pontoknál hibát várunk"
    except ValueError:
        pass


def test_standard_landmarks_sane():
    """A szabálykönyvi pálya-pontok a 40x20 m-es tartományban, helyes helyeken vannak."""
    lm = standard_court_landmarks()
    assert lm["jobb_felso_sarok"] == (40.0, 20.0)
    assert lm["bal_7m_pont"] == (7.0, 10.0)
    # a kapufák a középvonal körül 1.5 m-re (3 m-es kapu)
    assert lm["bal_kapufa_also"] == (0.0, 8.5)
    assert lm["bal_kapufa_felso"] == (0.0, 11.5)
    for (x, y) in lm.values():
        assert 0.0 <= x <= 40.0 and 0.0 <= y <= 20.0


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    print(f"\n{'OK' if failures == 0 else failures} hibás teszt")
    raise SystemExit(1 if failures else 0)
