"""
[D] Csapatba sorolás — melyik játékos melyik csapatban van (+ kapus felismerés).

Feladata: a követett játékosokat két csapatra osztani a MEZSZÍN alapján, és
felismerni a kapus(oka)t.

Miért működik a szín (lásd docs/RULES.md 4. szakasz):
- A két csapat mezőnyjátékosainak színe egymástól jól megkülönböztethető.
- A kapus mezszíne KÜLÖNBÖZIK a saját mezőnyjátékosoktól ÉS az ellenfél kapusától
  → a kapus külön (harmadik/negyedik) színklaszterként jelenik meg.
- Ha a kapus-szín ELTŰNIK a pályáról, az a "7. mezőnyjátékos / kapus nélküli
  játék" jele (lásd events.RosterTimeline.has_goalkeeper).

Módszer (valódi): a játékos-dobozok színhisztogramján k-means klaszterezés, majd
a klaszterek hozzárendelése a csapatokhoz/kapushoz. Ez a váz placeholder.
"""

from __future__ import annotations

from ..models.tracking import Team
from .tracking_step import Track


class TeamClassifier:
    """A követett játékosokat csapatokba sorolja a mezszín alapján.

    A valódi implementáció eleinte "betanul" a meccs első másodperceiből (milyen
    színek a két csapat és a kapusok), majd ez alapján sorol minden frame-en.
    """

    def __init__(self):
        # TODO: a megtanult csapat-/kapus-színek (klaszter-középpontok) tárolása.
        self._fitted = False

    def fit(self, sample_tracks: list[Track], frames=None) -> None:
        """Megtanulja a csapat- és kapus-színeket néhány minta-frame alapján.

        TODO: színhisztogramok gyűjtése a dobozokról + k-means a klaszterekhez,
        majd a klaszterek címkézése (hazai mezőny / vendég mezőny / kapus).
        """
        # TODO: valódi tanítás.
        self._fitted = True

    def classify(self, track: Track) -> Team:
        """Egy követett játékoshoz csapatot rendel a mezszíne alapján.

        TODO: a track doboz-színét a legközelebbi megtanult klaszterhez sorolni,
        és visszaadni a hozzá tartozó csapatot.
        Most placeholder: alapértelmezetten HOME (hogy a pipeline fusson).
        """
        return Team.HOME

    def is_goalkeeper(self, track: Track) -> bool:
        """Igaz, ha a játékos mezszíne a kapus-klaszterbe esik.

        TODO: a kapus-színklaszterhez való tartozás vizsgálata.
        """
        return False

    def is_referee(self, track: Track) -> bool:
        """Igaz, ha a detektált személy BÍRÓ (nem játékos), és ki kell szűrni.

        A valódi felvételen a bírók sárga mezben, a pályán mozognak (lásd
        docs/FOOTAGE_NOTES.md) — őket NEM szabad játékosnak venni. Mivel a sárga
        szín jól elkülönül a két csapattól (fehér/fekete) és a kapustól (zöld),
        szín alapján kiszűrhetők.

        TODO: a bíró-színklaszterhez (sárga) tartozás vizsgálata.
        Most placeholder: False (a váz nem szűr, amíg nincs valódi szín-logika).
        """
        return False
