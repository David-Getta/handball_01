"""
Tesztek a pásztázás-követésre (pan_tracking.py) — szintetikus, eltolt képekkel.

Zajos textúrájú képet tolunk el ismert mértékben (ez a "kamera pásztázása"), és
ellenőrizzük, hogy a PanTracker visszaméri az elmozdulást, illetve hogy a
halmozott mátrix a pontokat az ALAP képkocka koordinátáiba viszi vissza.

Futtatás:
    python tests/test_pan_tracking.py
"""

from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.pipeline.pan_tracking import PanTracker, apply_h


def _textured(seed=0, w=320, h=240):
    """Zajos, elmosott kép — bőven van rajta követhető sarokpont."""
    import cv2
    import numpy as np
    rng = np.random.default_rng(seed)
    img = (rng.random((h, w)) * 255).astype(np.uint8)
    return cv2.GaussianBlur(img, (5, 5), 0)


def _shift(img, dx):
    """A kép vízszintes eltolása dx pixellel (a kamera pásztázását szimulálja)."""
    import numpy as np
    return np.roll(img, dx, axis=1)


def test_first_frame_identity():
    """Az első képkockánál nincs mozgás: G az egységmátrix."""
    tr = PanTracker()
    G = tr.update(_textured())
    assert abs(G[0][2]) < 1e-9 and abs(G[1][2]) < 1e-9
    assert abs(G[0][0] - 1.0) < 1e-9


def test_same_frame_near_identity():
    """Ugyanaz a kép kétszer: a becsült mozgás ~nulla."""
    tr = PanTracker()
    img = _textured()
    tr.update(img)
    G = tr.update(img)
    assert abs(G[0][2]) < 0.5 and abs(G[1][2]) < 0.5


def test_known_shift_recovered():
    """Ismert eltolás: a tartalom +10 px-t mozdul (kamera balra pásztáz) →
    az aktuális→alap leképezés x-eltolása ~ -10."""
    tr = PanTracker()
    img = _textured()
    tr.update(img)
    G = tr.update(_shift(img, 10))
    assert abs(G[0][2] + 10.0) < 1.0, f"tx={G[0][2]}"
    # a pont-visszavetítés is stimmel: (50+10, 60) → (~50, ~60)
    x, y = apply_h(G, 60.0, 60.0)
    assert abs(x - 50.0) < 1.5 and abs(y - 60.0) < 1.5


def test_cumulative_shifts_compose():
    """Két egymás utáni +6 px eltolás halmozódik: össz ~ -12."""
    tr = PanTracker()
    img = _textured()
    tr.update(img)
    tr.update(_shift(img, 6))
    G = tr.update(_shift(img, 12))
    assert abs(G[0][2] + 12.0) < 1.5, f"tx={G[0][2]}"


def test_featureless_frame_keeps_state():
    """Jellemzőpont nélküli (egyszínű) kép: az előző állapot marad, nincs hiba."""
    import numpy as np
    tr = PanTracker()
    img = _textured()
    tr.update(img)
    G1 = tr.update(_shift(img, 8))
    flat = np.zeros_like(img)
    G2 = tr.update(flat)  # nem tud becsülni → tartja az állapotot
    assert abs(G2[0][2] - G1[0][2]) < 1e-6


def test_apply_h_identity():
    """apply_h az egységmátrixszal a pontot változatlanul adja vissza."""
    eye = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    assert apply_h(eye, 12.5, -3.0) == (12.5, -3.0)


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
