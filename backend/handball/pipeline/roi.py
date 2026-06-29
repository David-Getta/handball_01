"""
ROI / szűrés — mi tartozik a JÁTÉKTÉRHEZ, és mit hagyunk figyelmen kívül.

A kamera képébe sok minden belóghat, ami NEM a játék része: a pálya fölé belógó
kosárpalánk (multifunkciós csarnok), lelátó, kispad, nézők, reklámtábla, lógó
kamera. A programnak ezeket úgy kell kezelnie, mintha ott sem lennének.

Két, egymást kiegészítő szűrő:

1. CourtRegion — PÁLYA-RÉGIÓ (méterben):
   amelyik detektálás a pálya (40 x 20 m + tűréssáv) területén KÍVÜLRE vetül, azt
   eldobjuk. Ez fogja ki a lelátót, kispadot, vonalon túli embereket/tárgyakat.
   A tűréssáv azért kell, mert a játékosok néha kicsit a vonalon kívül vannak
   (partvonal, cserezóna), őket NEM akarjuk eldobni.

2. ExclusionZones — KIZÁRÁSI ZÓNÁK (kép-pixelben):
   fix kép-régiók, ahol ismert, hogy belóg valami (pl. a kosárpalánk a pálya
   FÖLÉ). Az ezekbe eső detektálásokat eldobjuk. Ez kezeli azt is, ami a pálya
   fölé lóg (annak talaj-vetülete a pályán belülre eshet, így a pálya-régió
   önmagában nem fogná meg) — ezért kép-térben szűrünk.

Mindkét szűrő tiszta geometria (nincs külső csomag), így videó nélkül tesztelhető.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .calibration import COURT_LENGTH_M, COURT_WIDTH_M


@dataclass
class CourtRegion:
    """A játéktér MÉTERBEN, egy tűréssávval kibővítve.

    - length_m, width_m: a pálya mérete (alapból 40 x 20 m).
    - margin_m:          a vonalon kívüli sáv, ami még játéktér-közelinek számít
                         (a játékos lehet kicsit a vonalon kívül). Ami ezen is
                         kívülre esik (lelátó, kispad), azt eldobjuk.
    """
    length_m: float = COURT_LENGTH_M
    width_m: float = COURT_WIDTH_M
    margin_m: float = 2.0

    def contains(self, x: float, y: float) -> bool:
        """Igaz, ha az (x, y) pálya-pont a játéktéren (+ tűréssáv) belül van."""
        return (
            -self.margin_m <= x <= self.length_m + self.margin_m
            and -self.margin_m <= y <= self.width_m + self.margin_m
        )


def point_in_polygon(px: float, py: float, polygon: list[tuple[float, float]]) -> bool:
    """Pont-a-sokszögben teszt (ray casting / páratlan-átmetszés szabály).

    A (px, py) pontból indított vízszintes félegyenes hányszor metszi a sokszög
    éleit: páratlan = belül, páros = kívül. Tetszőleges (akár konkáv) sokszögre jó.
    A `polygon` a csúcsok listája (legalább 3), körbejárási irány mindegy.
    """
    n = len(polygon)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        # Metszi-e a vízszintes félegyenes az i-j élt, és a metszéspont a ponttól jobbra van-e.
        intersects = ((yi > py) != (yj > py)) and (
            px < (xj - xi) * (py - yi) / (yj - yi) + xi
        )
        if intersects:
            inside = not inside
        j = i
    return inside


@dataclass
class ExclusionZones:
    """Fix KÉP-régiók (pixelben), amelyekbe eső detektálásokat figyelmen kívül hagyjuk.

    - polygons: sokszögek listája; mindegyik egy kép-béli régió (pixel-csúcsok),
      pl. ahol a kosárpalánk belóg, vagy egy lógó kamera/reklám van.

    A felhasználó ezeket egyszer jelöli meg a referencia-képen (a kalibrációhoz
    hasonlóan), és minden frame-en alkalmazzuk.
    """
    polygons: list[list[tuple[float, float]]] = field(default_factory=list)

    def contains(self, px: float, py: float) -> bool:
        """Igaz, ha az (px, py) kép-pont BÁRMELYIK kizárási zónába esik."""
        return any(point_in_polygon(px, py, poly) for poly in self.polygons)
