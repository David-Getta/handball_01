"""
[E] Pálya-koordináta — a kép-béli helyek átszámítása méteres pálya-koordinátára.

Feladata: minden követett játékos talaj-pontját (és a labdát) a [A] kalibrációval
a pálya valós (méteres) rendszerébe vetíteni. Innentől a játékosok helye már nem
pixelben, hanem méterben értendő — ez kell a sebesség/táv/hőtérkép számításához
és a felülnézeti megjelenítéshez.

Ez a lépés vékony: csak a homográfiát alkalmazza, nincs külön "modell".
"""

from __future__ import annotations

from ..models.tracking import PlayerPosition, PositionSource, Team, Ball
from .calibration import CourtCalibration
from .tracking_step import Track
from .detection import Detection


def player_to_court(track: Track, team: Team, calib: CourtCalibration) -> PlayerPosition:
    """Egy követett játékosból PlayerPosition-t készít méteres pálya-koordinátán.

    - a talaj-pontot a homográfiával méterre váltjuk,
    - a forrás MEASURED (mert ezt ténylegesen láttuk a képen),
    - a megbízhatóságot a detektálás confidence-éből visszük tovább,
    - a mezszámot (ha van) átadjuk az azonosításhoz.
    """
    fx, fy = track.detection.foot_point()          # talaj-pont képben (pixel)
    x, y = calib.image_to_court(fx, fy)            # -> pálya-koordináta (méter)
    return PlayerPosition(
        track_id=track.track_id,
        team=team,
        x=x,
        y=y,
        source=PositionSource.MEASURED,
        confidence=track.detection.confidence,
        jersey_number=track.jersey_number,
    )


def ball_to_court(detection: Detection, calib: CourtCalibration) -> Ball:
    """A labda-detektálásból méteres pálya-koordinátájú Ball-t készít."""
    fx, fy = detection.foot_point()                # a labdánál a doboz aljának közepe
    x, y = calib.image_to_court(fx, fy)
    return Ball(x=x, y=y, confidence=detection.confidence)
