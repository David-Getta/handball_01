"""
[A] Pálya-kalibráció (homográfia) — pásztázó kamerához.

Feladata: a kép-pixelekből a pálya VALÓS (méteres) koordinátáira átszámolni.

Miért speciális a pásztázó kamera (lásd docs/MVP_PLAN.md):
- A kamera HELYBEN marad és csak forog → a képkockák egymáshoz tiszta
  homográfiával köthetők (nincs parallaxis).
- Ezért EGYSZER kalibrálunk kézzel egy referencia-nézetet (rákattintunk a
  pályavonalak ismert pontjaira), majd minden további frame homográfiáját
  AUTOMATIKUSAN a referenciához illesztjük (jellemzőpont-illesztés / vonalfelismerés).

A kép->pálya átváltás matematikája (homográfia) MÁR VALÓDI — tiszta Pythonban,
lásd `_homography.py`. A videós rész (jellemzőpont-illesztés a pásztázás
követéséhez) marad még TODO, de a koordináta-rendszer alapja működik és tesztelt.
"""

from __future__ import annotations

from dataclasses import dataclass

from ._homography import homography_from_points, apply_homography

# A szabálykönyvi pályaméret (docs/RULES.md 1. szakasz) — a kalibráció cél-rendszere.
COURT_LENGTH_M = 40.0   # hosszú tengely (x)
COURT_WIDTH_M = 20.0    # rövid tengely (y)

# Koordináta-rendszer: az origó a pálya egyik sarka; x a 40 m-es hossz mentén,
# y a 20 m-es szélesség mentén. A kapuk x=0 és x=40 vonalán, y=10 körül középen.
GOAL_WIDTH_M = 3.0      # kapu szélessége (docs/RULES.md) → a kapufák y=8.5 és y=11.5


def standard_court_landmarks() -> dict[str, tuple[float, float]]:
    """A pálya jól azonosítható pontjai MÉTERBEN (a kalibráció cél-pontjai).

    A felhasználó a kalibrációkor a kép-pixelen rákattint ezek közül néhányra
    (legalább 4, nem egy vonalban), és a `Calibrator.calibrate_reference` ezekből
    a párokból számolja a homográfiát. A pontok a szabálykönyvi geometriából
    adódnak (docs/RULES.md 1. szakasz).
    """
    cy = COURT_WIDTH_M / 2.0          # a pálya középvonala y-ban (10 m)
    half_goal = GOAL_WIDTH_M / 2.0    # fél kapuszélesség (1.5 m)
    return {
        # Sarkok
        "bal_also_sarok": (0.0, 0.0),
        "bal_felso_sarok": (0.0, COURT_WIDTH_M),
        "jobb_also_sarok": (COURT_LENGTH_M, 0.0),
        "jobb_felso_sarok": (COURT_LENGTH_M, COURT_WIDTH_M),
        # Középvonal végpontjai
        "kozepvonal_also": (COURT_LENGTH_M / 2.0, 0.0),
        "kozepvonal_felso": (COURT_LENGTH_M / 2.0, COURT_WIDTH_M),
        # Bal kapu kapufái
        "bal_kapufa_also": (0.0, cy - half_goal),
        "bal_kapufa_felso": (0.0, cy + half_goal),
        # Bal oldali 6 m-es vonal egyenes szakaszának végei (x=6)
        "bal_6m_also": (6.0, cy - half_goal),
        "bal_6m_felso": (6.0, cy + half_goal),
        # Bal oldali 7 m-es pont
        "bal_7m_pont": (7.0, cy),
        # Bal oldali 9 m-es vonal egyenes szakaszának végei (x=9)
        "bal_9m_also": (9.0, cy - half_goal),
        "bal_9m_felso": (9.0, cy + half_goal),
    }


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

        Ha még nincs kalibráció (homography is None), változatlanul visszaadja a
        bemenetet (a pipeline így is végigfut). Ha van, VALÓDI perspektív
        transzformációt alkalmaz (homográfia + perspektív osztás, lásd _homography).
        """
        if self.homography is None:
            return px, py  # még nincs kalibráció — a koordináták egyelőre pixelben
        return apply_homography(self.homography, px, py)


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
        (pl. a 6 m-es vonal és az alapvonal metszéspontja). Legalább 4 pár kell.
        Kimenet: a referencia-nézethez tartozó CourtCalibration a kész homográfiával.

        A homográfiát a `_homography.homography_from_points` becsli (tiszta Python,
        legkisebb-négyzetes módszer 4+ pontra). Később ezt OpenCV is helyettesítheti,
        de a felület és a kimenet ugyanez marad.
        """
        h = homography_from_points(reference_points, court_points)
        return CourtCalibration(homography=h)

    def homography_for_frame(self, frame, reference_calib: CourtCalibration) -> CourtCalibration:
        """Egy konkrét frame kalibrációja.

        A pásztázás miatt a frame nézete eltér a referenciától; itt a frame-et a
        referenciához illesztjük (jellemzőpont-illesztéssel), és a két homográfiát
        összefűzve kapjuk a frame->pálya leképezést.

        TODO: ORB/SIFT jellemzők + illesztés a referencia-képpel; homográfiák szorzata.
        """
        return reference_calib  # placeholder: a referenciát használjuk
