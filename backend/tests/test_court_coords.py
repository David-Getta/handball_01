"""
Tesztek a pálya-koordináta lépésre (court_coords.py).

A lépés vékony: a követett játékos talaj-pontját (és a labdát) a
kalibráció homográfiájával a méteres pályára vetíti. Itt azt nézzük,
hogy a JÓ pont megy át a JÓ leképezésen, és hogy minden kísérő adat
(azonosító, csapat, mezszám, megbízhatóság, forrás) megérkezik. A
"kevés minta" eset a hiányzó kalibráció: ilyenkor a koordináta
változatlanul (pixelben) megy tovább — a pipeline így is végigfut.

Futtatás:
    python -m pytest tests/test_court_coords.py -q
"""

from __future__ import annotations

from handball.models.tracking import Ball, PlayerPosition, PositionSource, Team
from handball.pipeline.calibration import Calibrator, CourtCalibration
from handball.pipeline.court_coords import ball_to_court, player_to_court
from handball.pipeline.detection import Detection, DetectionClass
from handball.pipeline.tracking_step import Track

# 1 m = 50 px, eltolás nélkül: (600, 400) px → (12, 8) m.
SKALA = [[0.02, 0.0, 0.0], [0.0, 0.02, 0.0], [0.0, 0.0, 1.0]]


def _track(x1, y1, x2, y2, conf=0.9, track_id=7, mez=None):
    det = Detection(DetectionClass.PLAYER, x1, y1, x2, y2, conf)
    return Track(track_id=track_id, detection=det, jersey_number=mez)


def test_player_to_court_a_talajpontot_vetiti_meterre():
    """A doboz ALSÓ élének közepe megy át a homográfián — nem a doboz
    közepe, nem a sarka —, és minden kísérő adat megérkezik."""
    tr = _track(580.0, 280.0, 620.0, 400.0, conf=0.7, track_id=7, mez=9)
    pos = player_to_court(tr, Team.AWAY, CourtCalibration(homography=SKALA))
    assert isinstance(pos, PlayerPosition)
    assert abs(pos.x - 12.0) < 1e-9 and abs(pos.y - 8.0) < 1e-9
    assert pos.track_id == 7 and pos.team == Team.AWAY
    assert pos.jersey_number == 9
    assert pos.confidence == 0.7
    assert pos.source == PositionSource.MEASURED      # ezt láttuk a képen


def test_player_to_court_a_csapat_a_hivoe_a_mezszam_elhagyhato():
    """A csapatot a hívó (a csapatba soroló) adja — ugyanaz a doboz
    hazaiként és vendégként is ugyanoda vetül; kiolvasatlan mezszámnál
    None megy tovább."""
    tr = _track(980.0, 380.0, 1020.0, 500.0)
    calib = CourtCalibration(homography=SKALA)
    hazai = player_to_court(tr, Team.HOME, calib)
    vendeg = player_to_court(tr, Team.AWAY, calib)
    assert hazai.team == Team.HOME and vendeg.team == Team.AWAY
    assert (hazai.x, hazai.y) == (vendeg.x, vendeg.y)
    assert abs(hazai.x - 20.0) < 1e-9 and abs(hazai.y - 10.0) < 1e-9
    assert hazai.jersey_number is None


def test_player_to_court_perspektiv_kalibracioval_a_sarokra_all():
    """Valódi (perspektív) referencia-kalibrációval: aki a kép egy
    kijelölt pálya-sarkán áll, az a pálya megfelelő sarkára kerül."""
    kep = [(100.0, 700.0), (1800.0, 720.0), (1500.0, 250.0), (400.0, 240.0)]
    palya = [(0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0)]
    calib = Calibrator().calibrate_reference(kep, palya)
    for (px, py), (mx, my) in zip(kep, palya):
        tr = _track(px - 20.0, py - 120.0, px + 20.0, py)
        pos = player_to_court(tr, Team.HOME, calib)
        assert abs(pos.x - mx) < 1e-6 and abs(pos.y - my) < 1e-6


def test_player_to_court_kalibracio_nelkul_valtozatlan_koordinata():
    """Amíg nincs kalibráció (homography None), a talaj-pont változatlanul
    megy tovább — nem kivétel, nem (0, 0)."""
    tr = _track(580.0, 280.0, 620.0, 400.0)
    pos = player_to_court(tr, Team.HOME, CourtCalibration())
    assert (pos.x, pos.y) == (600.0, 400.0)
    assert pos.source == PositionSource.MEASURED


def test_ball_to_court_a_labda_meterben_a_megbizhatosaggal():
    """A labdánál is a doboz aljának közepe vetül, és a detektor
    megbízhatósága megy tovább."""
    det = Detection(DetectionClass.BALL, 995.0, 490.0, 1005.0, 500.0, 0.55)
    labda = ball_to_court(det, CourtCalibration(homography=SKALA))
    assert isinstance(labda, Ball)
    assert abs(labda.x - 20.0) < 1e-9 and abs(labda.y - 10.0) < 1e-9
    assert labda.confidence == 0.55


def test_ball_to_court_kalibracio_nelkul_valtozatlan_koordinata():
    """Kalibráció nélkül a labda is pixelben marad (a pipeline fut)."""
    det = Detection(DetectionClass.BALL, 300.0, 200.0, 310.0, 210.0, 0.6)
    labda = ball_to_court(det, CourtCalibration())
    assert (labda.x, labda.y, labda.confidence) == (305.0, 210.0, 0.6)


def test_jatekos_es_labda_ugyanazon_a_lekepezesen_megy_at():
    """Ugyanarra a kép-pontra a játékos és a labda UGYANODA kerül a
    pályán — különben a birtoklás (ki van a labdánál) elcsúszna."""
    calib = Calibrator().calibrate_reference(
        [(100.0, 700.0), (1800.0, 720.0), (1500.0, 250.0), (400.0, 240.0)],
        [(0.0, 0.0), (40.0, 0.0), (40.0, 20.0), (0.0, 20.0)])
    tr = _track(880.0, 380.0, 920.0, 500.0)
    det = Detection(DetectionClass.BALL, 895.0, 490.0, 905.0, 500.0)
    pos, labda = player_to_court(tr, Team.HOME, calib), ball_to_court(det, calib)
    assert abs(pos.x - labda.x) < 1e-9 and abs(pos.y - labda.y) < 1e-9
    assert 0.0 < pos.x < 40.0 and 0.0 < pos.y < 20.0
