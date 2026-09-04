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


def _textured_big(seed=3, w=640, h=360):
    """Nagyobb, részletgazdag kép a horgony-teszthez (ORB-nak elég pont)."""
    import cv2
    import numpy as np
    rng = np.random.default_rng(seed)
    img = (rng.random((h, w)) * 255).astype(np.uint8)
    img = cv2.GaussianBlur(img, (3, 3), 0)
    # Néhány éles alakzat is (a valódi képen: vonalak, lelátó, falak).
    for _ in range(40):
        x, y = int(rng.integers(10, w - 40)), int(rng.integers(10, h - 40))
        cv2.rectangle(img, (x, y), (x + 20, y + 20), int(rng.integers(0, 255)), -1)
    return img


def test_horgony_visszahozza_a_kalibralt_allast():
    """A kamera elfordul, majd VISSZAÁLL a kalibrált állásba: a horgonyzott
    becslés a végén ~egység (a puszta lánc a lépések hibáját halmozná).
    Ez a Kiel-féle eset: a kamera jobbra-balra svenkel, és nem biztos,
    hogy pontosan ugyanott áll meg — a horgony a kalibrált képhez méri."""
    img = _textured_big()
    tr = PanTracker(anchor=True)
    tr.update(img)
    for dx in (8, 16, 24, 32, 40, 32, 24, 16, 8, 0, 0):
        G = tr.update(_shift(img, dx))
    assert abs(G[0][2]) < 1.5 and abs(G[1][2]) < 1.5, f"G={G}"
    assert tr.stats["anchored"] >= 1
    assert tr.stats["frames"] == 12
    assert "horgonyzott" in tr.summary()


def test_horgony_kozben_is_helyes_az_eltolas():
    """A horgonyzott becslés az elfordult állásban is a valódi eltolást
    adja (nem csak a visszaállásnál)."""
    img = _textured_big()
    tr = PanTracker(anchor=True)
    tr.update(img)
    G = None
    for dx in (10, 20, 30, 40, 50):
        G = tr.update(_shift(img, dx))
    # 5 lépés után (ANCHOR_EVERY = 5) horgonyzott: az eltolás ~ -50.
    assert abs(G[0][2] + 50.0) < 2.0, f"tx={G[0][2]}"
    assert tr.stats["anchored"] >= 1


def test_a_mozgo_dobozok_kimaszkolva_is_megy_a_becsles():
    """A kizárt (mozgó ember) dobozokkal is helyes az eltolás — és a
    maszk nem töri el a becslést, ha a kép nagy részét fedi."""
    img = _textured_big()
    tr = PanTracker(anchor=False)
    tr.update(img, exclude=[(100, 100, 200, 250)])
    G = tr.update(_shift(img, 12), exclude=[(100, 100, 200, 250),
                                            (400, 50, 460, 200)])
    assert abs(G[0][2] + 12.0) < 1.5, f"tx={G[0][2]}"
    assert tr.stats["chain"] == 1
