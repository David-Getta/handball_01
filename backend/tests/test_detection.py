"""
Tesztek a detektálás vázára (detection.py): Detection + Detector.

A valódi YOLO-hívás a feldolgozóban él; ez a modul a FELÜLETET rögzíti,
amire a pipeline-összefogó épít: a Detection alakját, a talaj-pontot
(amit a homográfia a pályára vetít) és azt, hogy a Detector.detect
listát ad vissza. A "kevés minta" itt a modell nélküli váz és a nulla
méretű doboz: üres lista / a doboz saját pontja — nem kivétel.

Futtatás:
    python -m pytest tests/test_detection.py -q
"""

from __future__ import annotations

from handball.pipeline.detection import Detection, DetectionClass, Detector


def test_foot_point_a_doboz_aljanak_kozepe():
    """A talaj-érintési pont a befoglaló téglalap ALSÓ élének közepe —
    ott áll a játékos, ezt vetítjük a pályára (nem a doboz közepét)."""
    d = Detection(DetectionClass.PLAYER, 100.0, 50.0, 140.0, 170.0)
    assert d.foot_point() == (120.0, 170.0)
    # Nem a doboz közepe: az a csípő magasságában lenne.
    assert d.foot_point() != (120.0, 110.0)
    # Tört pixelekkel is pontos, és a megbízhatóságtól független.
    t = Detection(DetectionClass.PLAYER, 10.5, 20.25, 11.5, 80.75, 0.3)
    assert t.foot_point() == (11.0, 80.75)


def test_foot_point_a_labdanal_is_a_doboz_alja():
    """A labdánál ugyanaz a szabály (a doboz aljának közepe) — a
    pálya-koordináta lépés ezt használja mindkét osztályra."""
    labda = Detection(DetectionClass.BALL, 300.0, 200.0, 310.0, 210.0, 0.6)
    assert labda.foot_point() == (305.0, 210.0)


def test_foot_point_elfajult_doboznal_sem_hibazik():
    """Nulla szélességű / magasságú doboz (a kép szélén levágott alak):
    a pont maga a doboz — nincs osztás, nincs kivétel; negatív
    koordinátával (képen kívülre lógó doboz) is számol."""
    pont = Detection(DetectionClass.PLAYER, 50.0, 60.0, 50.0, 60.0)
    assert pont.foot_point() == (50.0, 60.0)
    kilog = Detection(DetectionClass.PLAYER, -20.0, 400.0, 20.0, 480.0)
    assert kilog.foot_point() == (0.0, 480.0)


def test_detection_alapertekek_es_osztalyok():
    """A megbízhatóság alapból 1,0; a két osztály szöveg-értékű (a JSON
    és a naplók így olvashatók), és az adatosztály mezőnként egyenlő."""
    d = Detection(DetectionClass.PLAYER, 1.0, 2.0, 3.0, 4.0)
    assert d.confidence == 1.0
    assert d == Detection(DetectionClass.PLAYER, 1.0, 2.0, 3.0, 4.0, 1.0)
    assert d != Detection(DetectionClass.BALL, 1.0, 2.0, 3.0, 4.0)
    assert DetectionClass.PLAYER.value == "player"
    assert DetectionClass.BALL.value == "ball"
    assert DetectionClass("ball") is DetectionClass.BALL


def test_detector_lustan_tolt_es_listat_ad():
    """A detektor a modellt nem a létrehozáskor, hanem az első
    használatkor tölti (az import így nem kér GPU-t); a detect LISTÁT ad
    vissza, amin a pipeline végigiterál — a váz üreset."""
    det = Detector()
    assert det.model_path is None and det._model is None
    toltesek = []
    eredeti = det._load_model
    det._load_model = lambda: (toltesek.append(1), eredeti())[1]

    ki = det.detect(frame=object())
    assert isinstance(ki, list)
    assert all(isinstance(d, Detection) for d in ki)
    assert len(toltesek) == 1                 # az első hívás tölt


def test_detector_modell_nelkul_ures_lista_nem_kivetel():
    """Modell (súlyfájl) nélkül, kép nélkül is fut: üres lista — nem
    None, nem kivétel —, és minden hívás saját listát ad."""
    det = Detector(model_path="nincs_ilyen_suly.pt")
    assert det.model_path == "nincs_ilyen_suly.pt"
    elso = det.detect(None)
    assert elso == []
    elso.append("idegen elem")
    assert det.detect(None) == []
