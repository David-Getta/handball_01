"""
[A] Pálya-kalibráció (homográfia) — pásztázó kamerához.

Feladata: a kép-pixelekből a pálya VALÓS (méteres) koordinátáira átszámolni.

Miért speciális a pásztázó kamera (lásd docs/MVP_PLAN.md):
- A kamera HELYBEN marad és csak forog → a képkockák egymáshoz tiszta
  homográfiával köthetők (nincs parallaxis).
- Ezért EGYSZER kalibrálunk kézzel egy referencia-nézetet (rákattintunk a
  pályavonalak ismert pontjaira), majd minden további frame homográfiáját
  AUTOMATIKUSAN a referenciához illesztjük (jellemzőpont-illesztés / vonalfelismerés).

Ebben a vázban a tényleges OpenCV-logika még placeholder (TODO). A felelősség és a
ki-/bemenet viszont már rögzített, hogy a pipeline többi része építhessen rá.
"""

from __future__ import annotations

from dataclasses import dataclass

# A szabálykönyvi pályaméret (docs/RULES.md 1. szakasz) — a kalibráció cél-rendszere.
COURT_LENGTH_M = 40.0   # hosszú tengely (x)
COURT_WIDTH_M = 20.0    # rövid tengely (y)


@dataclass
class CourtCalibration:
    """Egy frame-hez tartozó kép->pálya transzformáció.

    `homography`: 3x3-as mátrix (listák listájaként tárolva, hogy függőség nélkül
    is szerializálható legyen), amely egy kép-pontot (pixel) a pálya méteres
    koordinátájára képez. Az MVP-ben None lehet, amíg nincs valódi kalibráció.
    """
    homography: list[list[float]] | None = None

    def image_to_court(self, px: float, py: float) -> tuple[float, float]:
        """Egy kép-pontot (px, py pixel) pálya-koordinátára (x, y méter) képez.

        TODO: a valódi perspektív transzformáció (homográfia * pont, majd
        normalizálás a harmadik koordinátával). Most placeholder: változatlanul
        visszaadja a bemenetet, hogy a pipeline végigfusson.
        """
        if self.homography is None:
            return px, py  # placeholder: még nincs kalibráció
        # TODO: valódi homográfia-alkalmazás (numpy/OpenCV-vel).
        return px, py


class Calibrator:
    """A kalibráció elvégzője.

    MVP-folyamat:
    1. `calibrate_reference(...)` — kézi referencia-kalibráció (a vonalmetszésekre
       kattintott pontokból homográfia a méteres pályára).
    2. `homography_for_frame(...)` — egy adott frame homográfiája a referenciához
       illesztve (a pásztázás követése).
    """

    def calibrate_reference(self, reference_points: list[tuple[float, float]],
                            court_points: list[tuple[float, float]]) -> CourtCalibration:
        """Kézi referencia-kalibráció.

        Bemenet: összetartozó pont-párok — `reference_points` a kép-pixelben
        kijelölt pontok, `court_points` ugyanazok valós méteres helye a pályán
        (pl. a 6 m-es vonal és az alapvonal metszéspontja).
        Kimenet: a referencia-nézethez tartozó CourtCalibration.

        TODO: cv2.findHomography(...) a pont-párokból.
        """
        # TODO: valódi homográfia-becslés. Most üres kalibrációt adunk vissza.
        return CourtCalibration(homography=None)

    def homography_for_frame(self, frame, reference_calib: CourtCalibration) -> CourtCalibration:
        """Egy konkrét frame kalibrációja.

        A pásztázás miatt a frame nézete eltér a referenciától; itt a frame-et a
        referenciához illesztjük (jellemzőpont-illesztéssel), és a két homográfiát
        összefűzve kapjuk a frame->pálya leképezést.

        TODO: ORB/SIFT jellemzők + illesztés a referencia-képpel; homográfiák szorzata.
        """
        return reference_calib  # placeholder: a referenciát használjuk
