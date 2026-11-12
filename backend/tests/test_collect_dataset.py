"""
Tesztek a tanítóadat-gyűjtő szkriptre (scripts/collect_dataset.py).

A szkript a YOLO-detektor előcímkéivel gyűjt — itt kamu YOLO-val a
SAJÁT dolgát nézzük: a modell kimenetének nevekre képzését a két külön
megbízhatósági küszöbbel (_make_detect_fn), és a main útját kis
próba-videókon. (A gyűjtés motorja a tests/test_dataset.py-ban él.)

Futtatás:
    python -m pytest tests/test_collect_dataset.py -q
"""

from __future__ import annotations

import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from scripts import collect_dataset as cd  # noqa: E402


class _Doboz:
    """Egy ultralytics-alakú doboz: cls / conf / xyxy tömb-szerűen."""

    def __init__(self, cls, conf, xyxy):
        self.cls = [cls]
        self.conf = [conf]
        self.xyxy = [types.SimpleNamespace(tolist=lambda: list(xyxy))]


class _KamuYolo:
    hivasok: list = []
    nevek = {0: "person", 32: "sports ball", 56: "chair"}
    eredmeny: list = []

    def __init__(self, suly):
        self.suly = suly
        self.names = _KamuYolo.nevek

    def predict(self, img, **kw):
        _KamuYolo.hivasok.append({"suly": self.suly, **kw})
        return _KamuYolo.eredmeny


@pytest.fixture
def kamu_yolo(monkeypatch):
    _KamuYolo.hivasok = []
    _KamuYolo.nevek = {0: "person", 32: "sports ball", 56: "chair"}
    _KamuYolo.eredmeny = []
    monkeypatch.setitem(sys.modules, "ultralytics",
                        types.SimpleNamespace(YOLO=_KamuYolo))
    monkeypatch.setattr(cd, "_pick_device", lambda: "cpu")
    monkeypatch.setattr(cd, "_resolve_weights", lambda w: f"feloldva:{w}")
    return _KamuYolo


def test_make_detect_fn_nevekre_kepez_a_ket_kuszobbel(kamu_yolo):
    """A modell dobozai (név, megbízhatóság, x1, y1, x2, y2) alakban
    jönnek; a játékosra és a labdára KÜLÖN küszöb él (a kis labda
    alacsony megbízhatósággal is kell), a többi osztály kimarad."""
    kamu_yolo.eredmeny = [types.SimpleNamespace(boxes=[
        _Doboz(0, 0.80, (10.0, 20.0, 50.0, 120.0)),      # játékos: jó
        _Doboz(0, 0.20, (60.0, 20.0, 90.0, 120.0)),      # játékos: gyenge
        _Doboz(32, 0.06, (200.0, 100.0, 212.0, 112.0)),  # labda: elég
        _Doboz(32, 0.01, (300.0, 100.0, 312.0, 112.0)),  # labda: zaj
        _Doboz(56, 0.99, (0.0, 0.0, 30.0, 30.0)),        # szék: nem kell
    ])]
    detect = cd._make_detect_fn("yolov8n.pt", imgsz=1920, person_conf=0.35,
                                ball_conf=0.05)
    assert detect(np.zeros((90, 160, 3), np.uint8)) == [
        ("person", 0.80, 10.0, 20.0, 50.0, 120.0),
        ("ball", 0.06, 200.0, 100.0, 212.0, 112.0)]
    # A modell a feloldott súllyal töltődött, és a KISEBB küszöbbel, csak
    # a két osztályra, a választott eszközön fut.
    assert kamu_yolo.hivasok == [{
        "suly": "feloldva:yolov8n.pt", "imgsz": 1920, "conf": 0.05,
        "classes": [0, 32], "device": "cpu", "verbose": False}]


def test_make_detect_fn_a_sajat_modell_osztalyaival_is(kamu_yolo):
    """A kézilabdára finomhangolt modellben a labda az 1-es osztály: a
    neveket nézzük, így külön beállítás nélkül működik."""
    kamu_yolo.nevek = {0: "person", 1: "ball"}
    kamu_yolo.eredmeny = [types.SimpleNamespace(boxes=[
        _Doboz(1, 0.50, (200.0, 100.0, 212.0, 112.0)),
        _Doboz(0, 0.90, (10.0, 20.0, 50.0, 120.0))])]
    detect = cd._make_detect_fn("best.pt", 960, 0.35, 0.05)
    assert [d[0] for d in detect(None)] == ["ball", "person"]
    assert kamu_yolo.hivasok[0]["classes"] == [0, 1]


def test_make_detect_fn_ures_eredmenyre_ures_lista(kamu_yolo):
    """Ha a modell nem lát semmit (nincs eredmény, vagy a doboz-lista
    None), üres lista jön — nem kivétel."""
    detect = cd._make_detect_fn("yolov8n.pt", 1920, 0.35, 0.05)
    assert detect(None) == []
    kamu_yolo.eredmeny = [types.SimpleNamespace(boxes=None),
                          types.SimpleNamespace(boxes=[])]
    assert detect(None) == []


def _video(path, n=60, vilagos=120):
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 25.0,
                         (320, 240))
    for _ in range(n):
        vw.write(np.full((240, 320, 3), vilagos, np.uint8))
    vw.release()
    return str(path)


def _kamu_detektor(monkeypatch, labda=True):
    """A main detektora helyett: egy játékos (+ labda) minden képen."""
    kert: dict = {}

    def gyarto(weights, imgsz, person_conf, ball_conf):
        kert.update(weights=weights, imgsz=imgsz, person_conf=person_conf,
                    ball_conf=ball_conf)

        def detect(img):
            ki = [("person", 0.9, 50.0, 60.0, 90.0, 160.0)]
            if labda:
                ki.append(("ball", 0.4, 200.0, 100.0, 214.0, 114.0))
            return ki
        return detect

    monkeypatch.setattr(cd, "_make_detect_fn", gyarto)
    return kert


def test_main_tobb_videobol_egy_adathalmazba_gyujt(tmp_path, monkeypatch,
                                                    capsys):
    """Több videó ugyanabba a mappába gyűlik (az adathalmaz együtt nő): a
    main videónként összegez, a végén megmondja a képek számát és a
    következő lépést; a kimenet szabványos YOLO-szerkezet."""
    kert = _kamu_detektor(monkeypatch)
    a = _video(tmp_path / "a.mp4")
    b = _video(tmp_path / "b.mp4")
    ki_mappa = tmp_path / "ds"
    monkeypatch.setattr(sys, "argv", ["collect_dataset", a, b, "--out",
                                      str(ki_mappa), "--samples", "10"])
    assert cd.main() == 0
    assert kert == {"weights": "yolov8n.pt", "imgsz": 1920,
                    "person_conf": 0.35, "ball_conf": 0.05}

    ki = capsys.readouterr().out
    assert f"gyűjtés: {a}" in ki and f"gyűjtés: {b}" in ki
    assert ki.count("labda a képek 100%-án") == 2
    assert f"Kész: 20 kép a(z) {ki_mappa} mappában." in ki
    assert f"python -m scripts.finetune --data {ki_mappa}/dataset.yaml" in ki
    kepek = [p for split in ("train", "val")
             for p in (ki_mappa / "images" / split).iterdir()]
    cimkek = [p for split in ("train", "val")
              for p in (ki_mappa / "labels" / split).iterdir()]
    assert len(kepek) == 20 and len(cimkek) == 20
    assert (ki_mappa / "dataset.yaml").exists()


def test_main_a_parameterek_atmennek_a_detektorba(tmp_path, monkeypatch,
                                                  capsys):
    """A súly, a felbontás és a két küszöb a parancssorból a detektorba
    megy; labda nélküli detektorral a labda-arány 0% (nem osztás
    nullával)."""
    kert = _kamu_detektor(monkeypatch, labda=False)
    video = _video(tmp_path / "meccs.mp4")
    monkeypatch.setattr(sys, "argv", [
        "collect_dataset", video, "--out", str(tmp_path / "ds"),
        "--samples", "5", "--weights", "best.pt", "--imgsz", "960",
        "--person-conf", "0.5", "--ball-conf", "0.1"])
    assert cd.main() == 0
    assert kert == {"weights": "best.pt", "imgsz": 960, "person_conf": 0.5,
                    "ball_conf": 0.1}
    ki = capsys.readouterr().out
    assert "0 labda-doboz" in ki and "labda a képek 0%-án" in ki
    # A gyűjtő megjegyzése a felhasználóhoz is eljut.
    assert "  FIGYELEM: Kevés képen látszik a labda" in ki


def test_main_hasznalhatatlan_videobol_nulla_kep_de_nem_kivetel(
        tmp_path, monkeypatch, capsys):
    """Csupa sötét videóból (nincs mit címkézni) nem készül kép: a main
    ezt "0 kép"-pel mondja ki — nem száll el, és nem oszt nullával."""
    _kamu_detektor(monkeypatch)
    sotet = _video(tmp_path / "sotet.mp4", vilagos=3)
    monkeypatch.setattr(sys, "argv", ["collect_dataset", sotet, "--out",
                                      str(tmp_path / "ds"), "--samples",
                                      "10"])
    assert cd.main() == 0
    ki = capsys.readouterr().out
    assert "  0 kép (0 train / 0 val)" in ki
    assert "labda a képek 0%-án" in ki
    assert "Kész: 0 kép" in ki
    assert "FIGYELEM" not in ki              # nincs kép → nincs mit pótolni
