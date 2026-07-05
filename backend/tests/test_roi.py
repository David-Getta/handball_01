"""
Tesztek a ROI / szűrés modulra (roi.py).

Azt ellenőrizzük, hogy a programot nem zavarja meg, ami a játéktéren kívül van
(lelátó, kispad) vagy a képbe belóg (kosárpalánk):
- CourtRegion: a pályán (+ tűréssáv) belüli pont elfogadva, a messzi kívüli eldobva,
- point_in_polygon: pont-a-sokszögben teszt helyes konvex és konkáv alakzatra,
- ExclusionZones: a kizárt kép-régióba eső pont kiszűrve.

Futtatás:
    python tests/test_roi.py
"""

from __future__ import annotations

# A backend/ mappát a kereső-útvonalra tesszük, hogy a teszt bárhonnan fusson.
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.pipeline.roi import CourtRegion, ExclusionZones, point_in_polygon


def test_court_region_inside_and_outside():
    """A pálya közepe belül van; a lelátó (jóval a vonalon túl) kívül."""
    region = CourtRegion(margin_m=2.0)
    assert region.contains(20.0, 10.0)        # pálya közepe
    assert region.contains(0.0, 0.0)          # sarok
    assert not region.contains(20.0, 30.0)    # messze a hosszú vonalon túl (lelátó)
    assert not region.contains(50.0, 10.0)    # az alapvonalon jóval túl


def test_court_region_margin():
    """A tűréssávon belül (vonalon kicsit kívül) még elfogadjuk, azon túl nem."""
    region = CourtRegion(margin_m=2.0)
    assert region.contains(-1.5, 10.0)        # 1.5 m-re a vonalon kívül → még OK
    assert not region.contains(-3.0, 10.0)    # 3 m-re kívül → eldobjuk


def test_point_in_polygon_square():
    """Négyzet: a belső pont igaz, a külső hamis."""
    square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    assert point_in_polygon(5.0, 5.0, square)
    assert not point_in_polygon(15.0, 5.0, square)
    assert not point_in_polygon(-1.0, 5.0, square)


def test_point_in_polygon_concave():
    """Konkáv (L-alakú) sokszög: a kivágott sarokban lévő pont KÍVÜL legyen.

    Az L: az alsó sáv (y 0..2, x 0..4) + a jobb oszlop (x 2..4, y 2..4).
    A kivágott (bal-felső) rész x 0..2, y 2..4 → ott a pont kívül van.
    """
    l_shape = [(0, 0), (4, 0), (4, 4), (2, 4), (2, 2), (0, 2)]
    assert point_in_polygon(1.0, 1.0, l_shape)        # alsó sáv → belül
    assert point_in_polygon(3.0, 3.0, l_shape)        # jobb oszlop → belül
    assert not point_in_polygon(1.0, 3.0, l_shape)    # kivágott bal-felső sarok → kívül


def test_exclusion_zone_filters_hoop():
    """A kosárpalánk kép-régiójába eső detektálás kiszűrve, a többi nem.

    Tegyük fel, a palánk a kép tetején, az (800..1100, 0..200) pixel-téglalapban van.
    """
    hoop = [(800.0, 0.0), (1100.0, 0.0), (1100.0, 200.0), (800.0, 200.0)]
    zones = ExclusionZones(polygons=[hoop])

    assert zones.contains(950.0, 100.0)       # a palánk területén → kiszűrjük
    assert not zones.contains(950.0, 500.0)   # lejjebb, a pályán → megtartjuk
    assert not zones.contains(100.0, 100.0)   # máshol → megtartjuk


def test_empty_exclusions_keep_everything():
    """Ha nincs kizárt zóna, semmit nem szűrünk ki."""
    zones = ExclusionZones()
    assert not zones.contains(950.0, 100.0)


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
