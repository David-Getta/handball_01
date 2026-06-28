"""
[B] Detektálás — játékosok és a labda megtalálása egy képkockán.

Feladata: egy videó-frame-en megtalálni minden játékost és a labdát, és
visszaadni a kép-béli helyüket (befoglaló téglalap, "bounding box").

Eszköz (későbbi valódi implementáció): előtanított YOLO (Ultralytics), eleinte
általános "person"/"sports ball" osztályokkal, később kézilabda-adattal finomhangolva.

Ebben a vázban a tényleges modell-hívás placeholder. A `Detection` adatszerkezet
és a felelősség viszont rögzített.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class DetectionClass(str, Enum):
    """Mit detektáltunk."""
    PLAYER = "player"   # egy játékos (csapat-hovatartozás még NEM ismert, az a [D] lépés)
    BALL = "ball"       # a labda


@dataclass
class Detection:
    """Egy detektált objektum egy frame-en, KÉP-koordinátában (pixel).

    - cls:        játékos vagy labda.
    - x1,y1,x2,y2: a befoglaló téglalap bal-felső és jobb-alsó sarka (pixel).
    - confidence: a detektor megbízhatósága 0..1.

    A játékos talaj-pontját (amivel a pályára vetítünk) a téglalap aljának
    közepéből számoljuk: ( (x1+x2)/2 , y2 ). Lásd `foot_point`.
    """
    cls: DetectionClass
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float = 1.0

    def foot_point(self) -> tuple[float, float]:
        """A talaj-érintési pont kép-koordinátája (a téglalap aljának közepe).

        Ezt vetítjük a homográfiával a pályára — ez közelíti, hol áll a játékos.
        """
        return ((self.x1 + self.x2) / 2.0, self.y2)


class Detector:
    """A frame-enkénti detektor.

    A valódi implementáció lustán (a `_load_model`-ben) tölti be a YOLO modellt,
    hogy a modul importja ne igényeljen GPU-t / nehéz csomagot.
    """

    def __init__(self, model_path: str | None = None):
        # A modell elérési útja; None esetén az alapértelmezett előtanított súlyok.
        self.model_path = model_path
        self._model = None  # lustán töltjük be

    def _load_model(self):
        """A YOLO modell lusta betöltése (csak az első tényleges használatkor).

        TODO: `from ultralytics import YOLO; self._model = YOLO(self.model_path)`.
        """
        # TODO: valódi modellbetöltés.
        self._model = None

    def detect(self, frame) -> list[Detection]:
        """Egy frame-en visszaadja a detektált játékosokat és a labdát.

        Bemenet: `frame` — egy kép (a valódi implementációban numpy tömb / OpenCV kép).
        Kimenet: Detection-ök listája (kép-koordinátában).

        TODO: a YOLO-ráfuttatás és a kimenet Detection-ökre alakítása.
        Most placeholder: üres lista, hogy a pipeline végigfusson.
        """
        if self._model is None:
            self._load_model()
        # TODO: valódi inferencia. Most nincs detektálás.
        return []
