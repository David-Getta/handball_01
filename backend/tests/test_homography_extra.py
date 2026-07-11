"""A mátrix-inverz és -szorzás tesztjei (kettős térfél-kalibrációhoz)."""
from handball.pipeline._homography import (
    apply_homography, compose, homography_from_points, invert_3x3,
)


def test_invert_roundtrip_is_identity():
    # Egy valódi (perspektív) homográfia inverze visszaadja az eredeti pontot.
    src = [(100.0, 200.0), (900.0, 180.0), (950.0, 700.0), (60.0, 720.0)]
    dst = [(0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0)]
    H = homography_from_points(src, dst)
    Hinv = invert_3x3(H)
    x, y = apply_homography(H, 500.0, 400.0)
    px, py = apply_homography(Hinv, x, y)
    assert abs(px - 500.0) < 1e-6 and abs(py - 400.0) < 1e-6


def test_compose_applies_right_then_left():
    # compose(B, A): előbb A, majd B — eltolás-mátrixokkal ellenőrizve.
    A = [[1.0, 0.0, 5.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]   # x+5
    B = [[2.0, 0.0, 0.0], [0.0, 2.0, 0.0], [0.0, 0.0, 1.0]]   # *2
    x, y = apply_homography(compose(B, A), 1.0, 1.0)
    assert (x, y) == (12.0, 2.0)  # (1+5)*2, 1*2


def test_two_half_calibrations_refine_each_side():
    """Kettős kalibráció elve: a bal féllel számolt pont a bal H-val, a jobb
    féllel számolt a jobb H-val pontos — itt a két H szintetikus képen készül,
    és ellenőrizzük, hogy a saját térfelén mindkettő visszaadja az igazságot."""
    # Szintetikus "kamera": a pálya (40x20) egyszerű affin vetítése 1000x500-ra.
    def cam(mx, my):
        return (mx * 25.0, my * 25.0)

    left_img = [cam(*p) for p in [(0, 0), (20, 0), (20, 20), (0, 20)]]
    right_img = [cam(*p) for p in [(20, 0), (40, 0), (40, 20), (20, 20)]]
    H_left = homography_from_points(left_img, [(0, 0), (20, 0), (20, 20), (0, 20)])
    H_right = homography_from_points(right_img, [(20, 0), (40, 0), (40, 20), (20, 20)])

    # Bal-oldali pont (10 m): a bal H pontos.
    x, y = apply_homography(H_left, *cam(10, 5))
    assert abs(x - 10) < 1e-6 and abs(y - 5) < 1e-6
    # Jobb-oldali pont (30 m): a jobb H pontos.
    x, y = apply_homography(H_right, *cam(30, 15))
    assert abs(x - 30) < 1e-6 and abs(y - 15) < 1e-6
