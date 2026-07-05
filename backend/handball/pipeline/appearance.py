"""
Megjelenés-profil — MECCSENKÉNTI színek (NEM bedrótozva).

Fontos követelmény: a csapatok, kapusok, bírók és a pálya színe meccsről meccsre
változik. Ezért a rendszer SEHOL nem feltételez fix színeket — minden meccshez egy
`AppearanceProfile` tartozik, amit vagy automatikusan TANULUNK a meccs elejéből,
vagy a felhasználó állít be (rákattint egy-egy mintajátékosra). A FOOTAGE_NOTES.md-
beli fehér/fekete/zöld/sárga csak PÉLDA egy konkrét meccsre.

Ez a modul a színhozzárendelés MAGJA: adott egy mintaszín (egy detektált személy
domináns mezszíne), és a meccs-profil referenciaszínei közül a LEGKÖZELEBBIT
választjuk (euklideszi távolság a színtérben). Ez szín-agnosztikus: bármilyen
meccs-színkészlettel ugyanúgy működik, és tisztán tesztelhető (nem kell videó).

A mintaszín tényleges KINYERÉSE a kép-pixelekből (a bbox domináns színe) a valódi
modellnél jön, mert ahhoz képadat kell — de a hozzárendelés logikája itt már valódi.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

RGB = tuple[int, int, int]


class AppearanceLabel(str, Enum):
    """Mivé sorolunk egy mintaszínt a meccs-profil alapján."""
    HOME = "home"              # hazai csapat mezőnyjátékos
    AWAY = "away"              # vendég csapat mezőnyjátékos
    GOALKEEPER = "goalkeeper"  # kapus (eltérő szín)
    REFEREE = "referee"        # bíró (nem játékos → kiszűrendő)


@dataclass
class AppearanceProfile:
    """Egy MECCS színkészlete (referenciaszínek). Tanult vagy kézzel beállított.

    Minden mező opcionális RGB (0..255). Ami nincs megadva, azt nem vesszük
    figyelembe a hozzárendelésnél. Több kapus-/bíró-szín is megadható (pl. a két
    csapat kapusa eltérő, vagy több bíró).

    - match_threshold: ennél nagyobb színtávolságnál "nem ismerjük fel" (None-t
      adunk vissza), hogy a háttér/zaj ne kerüljön rossz címkére.
    """
    home: Optional[RGB] = None
    away: Optional[RGB] = None
    goalkeeper: list[RGB] = field(default_factory=list)
    referee: list[RGB] = field(default_factory=list)
    match_threshold: float = 140.0  # max. megengedett színtávolság (0..441 skálán)

    def labeled_colors(self) -> list[tuple[AppearanceLabel, RGB]]:
        """A profil összes (címke, szín) párja, a hozzárendeléshez."""
        pairs: list[tuple[AppearanceLabel, RGB]] = []
        if self.home is not None:
            pairs.append((AppearanceLabel.HOME, self.home))
        if self.away is not None:
            pairs.append((AppearanceLabel.AWAY, self.away))
        for c in self.goalkeeper:
            pairs.append((AppearanceLabel.GOALKEEPER, c))
        for c in self.referee:
            pairs.append((AppearanceLabel.REFEREE, c))
        return pairs


def color_distance(a: RGB, b: RGB) -> float:
    """Két szín euklideszi távolsága az RGB térben (0 = azonos, ~441 = fekete-fehér)."""
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2)


def nearest_label(rgb: RGB, profile: AppearanceProfile) -> Optional[AppearanceLabel]:
    """A mintaszínhez (rgb) a meccs-profil LEGKÖZELEBBI referenciacímkéjét adja.

    Ha a legközelebbi referencia is távolabb van a küszöbnél, None-t ad (ismeretlen
    → nem soroljuk be, pl. háttér vagy hibás detektálás). Üres profilnál None.
    """
    best_label: Optional[AppearanceLabel] = None
    best_dist = float("inf")
    for label, ref in profile.labeled_colors():
        d = color_distance(rgb, ref)
        if d < best_dist:
            best_dist = d
            best_label = label
    if best_label is None or best_dist > profile.match_threshold:
        return None
    return best_label
