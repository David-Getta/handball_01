"""
Tesztek a követés vázára (tracking_step.py): Track + Tracker.

A valódi követő (ByteTrack + ReID + mezszám-OCR) a feldolgozóban él; ez
a modul a FELÜLETET rögzíti, amire a pipeline-összefogó épít: a Track
alakját és azt, hogy a Tracker.update listát ad vissza. A "kevés minta"
itt az üres detektálás-lista és a hiányzó kép: ilyenkor nincs követett
játékos (üres lista) — nem kivétel, nem None.

Futtatás:
    python -m pytest tests/test_tracking_step.py -q
"""

from __future__ import annotations

from handball.pipeline.detection import Detection, DetectionClass
from handball.pipeline.tracking_step import Track, Tracker


def _doboz(x=100.0, y=200.0):
    return Detection(DetectionClass.PLAYER, x, y - 120.0, x + 40.0, y, 0.9)


def test_track_alapertekek_es_mezok():
    """A Track a detektálást stabil azonosítóval egészíti ki; a mezszám
    és a domináns szín None, amíg nincs kiolvasva / kinyerve."""
    d = _doboz()
    tr = Track(track_id=7, detection=d)
    assert tr.track_id == 7 and tr.detection is d
    assert tr.jersey_number is None and tr.dominant_color is None

    teljes = Track(track_id=7, detection=d, jersey_number=9,
                   dominant_color=(240, 240, 240))
    assert teljes.jersey_number == 9
    assert teljes.dominant_color == (240, 240, 240)
    # Adatosztály: mezőnként egyenlő; más azonosító → más követés.
    assert teljes == Track(7, d, 9, (240, 240, 240))
    assert teljes != Track(8, d, 9, (240, 240, 240))
    # A talaj-pont a detektálásból jön (ezt vetíti a pipeline a pályára).
    assert tr.detection.foot_point() == (120.0, 200.0)


def test_tracker_update_listat_ad_detektalasokra():
    """A váz-követő bármilyen detektálás-listára LISTÁT ad vissza (a
    pipeline végigiterál rajta) — képpel és kép nélkül is, kivétel
    nélkül. A valódi követés beépítéséig a lista üres."""
    koveto = Tracker()
    dets = [_doboz(100.0), _doboz(300.0), _doboz(500.0)]
    ki = koveto.update(dets, frame=object())
    assert isinstance(ki, list)
    assert all(isinstance(t, Track) for t in ki)
    assert koveto.update(dets) == ki          # a kép elhagyható
    # A bemenetet nem módosítja.
    assert len(dets) == 3


def test_tracker_update_ures_detektalasra_ures_lista():
    """Nincs detektálás → nincs követett játékos: üres lista (nem None),
    és minden hívás SAJÁT listát ad (a hívó bővítheti)."""
    koveto = Tracker()
    elso = koveto.update([])
    assert elso == []
    elso.append("idegen elem")
    assert koveto.update([]) == []


def test_tracker_az_azonosito_kiosztas_egytol_indul():
    """Az új követő azonosító-számlálója 1-ről indul, és a két követő
    állapota független (meccsenként külön példány)."""
    a, b = Tracker(), Tracker()
    assert a._next_id == 1 and b._next_id == 1
    a._next_id = 5
    assert b._next_id == 1
