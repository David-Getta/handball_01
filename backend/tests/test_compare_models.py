"""
Tesztek a modell-összemérő szkriptre (scripts/compare_models.py) — a
szkript eddig egyszer sem futott a csomagban. Kamu detektorokkal, kis
próba-videón: az egymodelles és a kétmodelles eredménylap (Markdown +
JSON) és a labda-lefedettség változásának kiírása. (A mérés motorja a
tests/test_model_eval.py-ban él.)

Futtatás:
    python -m pytest tests/test_compare_models.py -q
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from scripts import compare_models as cm  # noqa: E402


def _video(path, n=100):
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 25.0,
                         (320, 240))
    for _ in range(n):
        vw.write(np.full((240, 320, 3), 120, np.uint8))
    vw.release()
    return str(path)


def _kamu_detektorok(monkeypatch, labda_minden):
    """A súlyfájl neve szerinti kamu detektor: öt játékos, és a megadott
    gyakorisággal labda (`labda_minden[súly]` = minden hányadik képen;
    0 = soha)."""
    kert: list = []

    def gyarto(weights, imgsz, person_conf, ball_conf):
        kert.append({"weights": weights, "imgsz": imgsz,
                     "person_conf": person_conf, "ball_conf": ball_conf})
        hivas = {"n": 0}
        gyakorisag = labda_minden[weights]

        def detect(img):
            hivas["n"] += 1
            ki = [("person", 0.8, 10.0 * i, 10.0, 10.0 * i + 8, 40.0)
                  for i in range(5)]
            if gyakorisag and hivas["n"] % gyakorisag == 0:
                ki.append(("ball", 0.3, 100.0, 100.0, 110.0, 110.0))
            return ki
        return detect

    monkeypatch.setattr(cm, "_make_detect_fn", gyarto)
    return kert


def test_main_egy_modellel_a_kiindulasi_szint(tmp_path, monkeypatch, capsys):
    """--weights-b nélkül egymodelles eredménylap készül (a kiindulási
    szint): Markdown + JSON, csak az "a" modellel, változás-sor nélkül."""
    kert = _kamu_detektorok(monkeypatch, {"yolov8n.pt": 2})
    video = _video(tmp_path / "meccs.mp4")
    ki_fajl = tmp_path / "lap.md"
    monkeypatch.setattr(sys, "argv", ["compare_models", video, "--samples",
                                      "20", "--out", str(ki_fajl)])
    assert cm.main() == 0
    assert kert == [{"weights": "yolov8n.pt", "imgsz": 1920,
                     "person_conf": 0.35, "ball_conf": 0.05}]

    adat = json.loads(ki_fajl.with_suffix(".json").read_text(
        encoding="utf-8"))
    assert set(adat) == {"video", "a"} and adat["video"] == video
    assert adat["a"]["weights"] == "yolov8n.pt"
    assert adat["a"]["frames"] == 20
    assert abs(adat["a"]["ball_coverage_pct"] - 50.0) < 0.1
    assert adat["a"]["avg_persons"] == 5.0
    md = ki_fajl.read_text(encoding="utf-8")
    assert "yolov8n.pt" in md and "Labda-lefedettség" in md
    ki = capsys.readouterr().out
    assert "mérés: yolov8n.pt …" in ki
    assert "20 kocka · labda-lefedettség: 50.0%" in ki
    assert f"eredménylap: {ki_fajl} (+ lap.json)" in ki
    assert "változása" not in ki


def test_main_ket_modellel_megmondja_mennyit_ert_a_tanitas(tmp_path,
                                                           monkeypatch,
                                                           capsys):
    """Két modellel egymás mellett: a JSON mindkettőt hozza (a lapon a
    fájlnévvel, mappa nélkül), és a kimenet kimondja a labda-lefedettség
    változását százalékpontban, előjellel."""
    hangolt = str(tmp_path / "runs" / "handball" / "weights" / "best.pt")
    kert = _kamu_detektorok(monkeypatch, {"yolov8n.pt": 4, hangolt: 1})
    video = _video(tmp_path / "meccs.mp4")
    ki_fajl = tmp_path / "osszehasonlitas.md"
    monkeypatch.setattr(sys, "argv", [
        "compare_models", video, "--weights-b", hangolt, "--samples", "20",
        "--imgsz", "960", "--out", str(ki_fajl)])
    assert cm.main() == 0
    assert [k["weights"] for k in kert] == ["yolov8n.pt", hangolt]
    assert all(k["imgsz"] == 960 for k in kert)

    adat = json.loads(ki_fajl.with_suffix(".json").read_text(
        encoding="utf-8"))
    assert set(adat) == {"video", "a", "b"}
    assert adat["b"]["weights"] == hangolt
    assert abs(adat["a"]["ball_coverage_pct"] - 25.0) < 0.1
    assert abs(adat["b"]["ball_coverage_pct"] - 100.0) < 0.1
    md = ki_fajl.read_text(encoding="utf-8")
    assert "best.pt" in md and "yolov8n.pt" in md
    assert str(tmp_path) not in md.replace(video, "")   # csak a fájlnév
    assert "labda-lefedettség változása: +75.0 százalékpont" in \
        capsys.readouterr().out


def test_main_a_romlast_is_kimondja(tmp_path, monkeypatch, capsys):
    """Ha a "finomhangolt" modell ROSSZABB (kevesebb képen találja a
    labdát), a változás negatív előjellel jön — a tanítás nem ért."""
    _kamu_detektorok(monkeypatch, {"yolov8n.pt": 1, "rossz.pt": 0})
    video = _video(tmp_path / "meccs.mp4")
    monkeypatch.setattr(sys, "argv", [
        "compare_models", video, "--weights-b", "rossz.pt", "--samples",
        "10", "--out", str(tmp_path / "lap.md")])
    assert cm.main() == 0
    ki = capsys.readouterr().out
    assert "labda-lefedettség változása: -100.0 százalékpont" in ki
    adat = json.loads((tmp_path / "lap.json").read_text(encoding="utf-8"))
    assert adat["b"]["ball_coverage_pct"] == 0.0


def test_main_mintavetelezes_nelkul_nulla_kocka_nem_kivetel(tmp_path,
                                                            monkeypatch,
                                                            capsys):
    """Ha a videóból nem jut mérhető kocka (a kezdő index a videó végén
    túl van), a lap 0 kockával és 0%-kal készül el — kivétel és osztás
    nullával nélkül."""
    _kamu_detektorok(monkeypatch, {"yolov8n.pt": 1})
    video = _video(tmp_path / "rovid.mp4", n=30)
    monkeypatch.setattr(sys, "argv", [
        "compare_models", video, "--start", "5000", "--samples", "10",
        "--out", str(tmp_path / "lap.md")])
    assert cm.main() == 0
    adat = json.loads((tmp_path / "lap.json").read_text(encoding="utf-8"))
    assert adat["a"]["frames"] == 0
    assert adat["a"]["ball_coverage_pct"] == 0.0
    assert "0 kocka · labda-lefedettség: 0.0%" in capsys.readouterr().out
