"""
[C] Követés + ReID + mezszám-OCR — STABIL azonosító minden játékosnak.

Feladata: a frame-enkénti detektálásokat (lásd [B]) összefűzni úgy, hogy ugyanaz
a valós játékos végig UGYANAZT a `track_id`-t kapja, még akkor is, ha közben
kicsúszott a képből (pásztázó kamera!) és később visszatért.

Három eszköz együtt:
1. Követő (ByteTrack/BoT-SORT): frame-ről frame-re követi a mozgó dobozokat.
2. ReID (megjelenés-embedding): ha valaki eltűnt és visszatért, megjelenés alapján
   visszakapja a régi id-ját.
3. Mezszám-OCR: ahol a hátszám olvasható (szabály szerint min. 20 cm, lásd
   docs/RULES.md 5. szakasz), az a LEGERŐSEBB azonosító jel — ezzel pontosítjuk
   és javítjuk a ReID-et.

Ez a váz placeholder. A `Track` az egy frame-re vonatkozó követett objektumot írja le.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .detection import Detection


@dataclass
class Track:
    """Egy követett objektum egy frame-en — a Detection kiegészítve stabil id-val.

    - track_id:       a végig megőrzött azonosító.
    - detection:      a hozzá tartozó nyers detektálás (kép-koordináta).
    - jersey_number:  a mezszám-OCR eredménye, ha sikerült kiolvasni (None, ha nem).
    - dominant_color: a játékos domináns mezszíne (RGB) a bbox-ból kinyerve, a
                      meccs-profil szerinti csapat-/kapus-/bíró-besoroláshoz
                      (lásd teams.py, appearance.py). None, amíg nincs kinyerve.
    """
    track_id: int
    detection: Detection
    jersey_number: Optional[int] = None
    dominant_color: Optional[tuple[int, int, int]] = None


class Tracker:
    """Frame-szekvenciát követ, stabil id-kat ad.

    A valódi implementáció állapotot tart a frame-ek között (aktív követések,
    megjelenés-embeddingek, mezszám-szavazatok). Ez a váz csak a felületet rögzíti.
    """

    def __init__(self):
        # TODO: a követő (ByteTrack), a ReID-modell és az OCR állapotának inicializálása.
        self._next_id = 1

    def update(self, detections: list[Detection], frame=None) -> list[Track]:
        """Egy frame detektálásaiból követett Track-eket állít elő.

        Bemenet: az adott frame Detection-jei (csak a JÁTÉKOSOK; a labdát külön
        kezeljük), és opcionálisan maga a `frame` kép (az OCR/ReID-hez).
        Kimenet: Track-ek stabil id-val.

        TODO:
        - a követő frissítése a detektálásokkal (id-társítás),
        - ReID a visszatérő játékosokra,
        - mezszám-OCR a doboz-kivágatokon, és id-javítás a szám alapján.
        Most placeholder: nincs követés.
        """
        # TODO: valódi követés. Most üres.
        return []
