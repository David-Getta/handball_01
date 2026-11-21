"""
Tesztek a finomhangoló szkriptre (scripts/finetune.py).

A tanítás az ultralytics-szel futna (percek, GPU) — itt egy kamu YOLO-val
a szkript SAJÁT dolgát nézzük: az élesbe állítást (a régi súly mentésével)
és a main útjait (hiányzó adathalmaz, be nem fejezett tanítás, kész
modell, --install). A súlyok a teszt tmp adat-mappájába kerülnek.

Futtatás:
    python -m pytest tests/test_finetune.py -q
"""

from __future__ import annotations

import os
import sys
import types
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import finetune as ft  # noqa: E402


def test_install_weights_a_felhasznaloi_suly_mappaba_masol(tmp_path,
                                                            monkeypatch):
    """A kész modell a felhasználói adat-mappa weights/yolov8n.pt fájljába
    kerül (a mappa létrejön) — a feldolgozó ezt részesíti előnyben."""
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path / "adat"))
    best = tmp_path / "best.pt"
    best.write_bytes(b"UJ-MODELL")

    cel = ft.install_weights(best)
    assert cel == tmp_path / "adat" / "weights" / "yolov8n.pt"
    assert cel.read_bytes() == b"UJ-MODELL"
    assert not cel.with_suffix(".pt.bak").exists()   # nem volt mit menteni
    assert best.exists()                             # másol, nem mozgat


def test_install_weights_a_korabbi_sulyt_bak_ba_menti(tmp_path, monkeypatch):
    """Ha már van élesített súly, az .bak mentést kap, mielőtt az új
    felülírja — a visszaállítás egy másolás. Újabb élesítésnél a mentés
    az ELŐZŐ élesített modell."""
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    wdir = tmp_path / "weights"
    wdir.mkdir()
    (wdir / "yolov8n.pt").write_bytes(b"ALAPMODELL")
    elso = tmp_path / "best1.pt"
    elso.write_bytes(b"ELSO-HANGOLT")
    masodik = tmp_path / "best2.pt"
    masodik.write_bytes(b"MASODIK-HANGOLT")

    cel = ft.install_weights(elso)
    assert cel.read_bytes() == b"ELSO-HANGOLT"
    assert (wdir / "yolov8n.pt.bak").read_bytes() == b"ALAPMODELL"
    ft.install_weights(masodik)
    assert cel.read_bytes() == b"MASODIK-HANGOLT"
    assert (wdir / "yolov8n.pt.bak").read_bytes() == b"ELSO-HANGOLT"


class _KamuYolo:
    """Az ultralytics.YOLO helyett: feljegyzi, mivel tanítanák, és (ha
    kell) letesz egy best.pt-t a mentési mappába."""

    hivasok: list = []
    keszit_best = True
    mentesi_mappa: Path | None = None

    def __init__(self, suly):
        self.suly = suly

    def train(self, **kw):
        _KamuYolo.hivasok.append({"suly": self.suly, **kw})
        if _KamuYolo.keszit_best:
            w = _KamuYolo.mentesi_mappa / "weights"
            w.mkdir(parents=True, exist_ok=True)
            (w / "best.pt").write_bytes(b"HANGOLT")
        return types.SimpleNamespace(save_dir=str(_KamuYolo.mentesi_mappa))


def _kornyezet(monkeypatch, tmp_path, argv, keszit_best=True):
    _KamuYolo.hivasok = []
    _KamuYolo.keszit_best = keszit_best
    _KamuYolo.mentesi_mappa = tmp_path / "runs" / "handball"
    monkeypatch.setitem(sys.modules, "ultralytics",
                        types.SimpleNamespace(YOLO=_KamuYolo))
    monkeypatch.setattr(ft, "_pick_device", lambda: "cpu")
    monkeypatch.setattr(ft, "_resolve_weights", lambda w: f"feloldva:{w}")
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path / "adat"))
    monkeypatch.setattr(sys, "argv", ["finetune", *argv])


def test_main_hianyzo_adathalmazra_1_es_nem_tanit(tmp_path, monkeypatch,
                                                  capsys):
    """Nem létező dataset.yaml-re a main beszélő hibával 1-et ad — a
    tanítás el sem indul (a modell be sem töltődik)."""
    _kornyezet(monkeypatch, tmp_path,
               ["--data", str(tmp_path / "nincs" / "dataset.yaml")])
    assert ft.main() == 1
    assert "HIBA: nincs ilyen adathalmaz" in capsys.readouterr().out
    assert _KamuYolo.hivasok == []


def test_main_tanit_es_megmondja_hol_a_kesz_modell(tmp_path, monkeypatch,
                                                   capsys):
    """Meglévő adathalmazzal a tanítás a megadott paraméterekkel indul
    (a feloldott kiinduló súllyal, a választott eszközön); --install
    nélkül a kész modellt csak megnevezi, és megmondja, hogyan lehet
    élesíteni — a felhasználói súly-mappához nem nyúl."""
    adat = tmp_path / "dataset.yaml"
    adat.write_text("path: .\n", encoding="utf-8")
    _kornyezet(monkeypatch, tmp_path,
               ["--data", str(adat), "--epochs", "3", "--imgsz", "640",
                "--batch", "8", "--model", "sajat.pt"])
    assert ft.main() == 0
    assert _KamuYolo.hivasok == [{
        "suly": "feloldva:sajat.pt", "data": str(adat), "epochs": 3,
        "imgsz": 640, "batch": 8, "device": "cpu", "project": "runs",
        "name": "handball", "exist_ok": True}]
    ki = capsys.readouterr().out
    assert f"tanítás indul · eszköz: cpu · adat: {adat}" in ki
    assert "kész modell: " in ki and "best.pt" in ki
    assert "Élesbe állítás: python -m scripts.finetune --data ... --install" \
        in ki
    assert "ÉLESBE ÁLLÍTVA" not in ki
    assert not (tmp_path / "adat" / "weights").exists()


def test_main_install_elesbe_allitja_a_kesz_modellt(tmp_path, monkeypatch,
                                                    capsys):
    """Az --install a kész modellt a felhasználói súly-mappába teszi, és
    kimondja a visszaállítás módját; az alapértékek (60 epoch, 960 px,
    automatikus batch, yolov8n.pt) mennek a tanításba."""
    adat = tmp_path / "dataset.yaml"
    adat.write_text("path: .\n", encoding="utf-8")
    _kornyezet(monkeypatch, tmp_path, ["--data", str(adat), "--install"])
    assert ft.main() == 0
    h = _KamuYolo.hivasok[0]
    assert (h["suly"], h["epochs"], h["imgsz"], h["batch"]) == (
        "feloldva:yolov8n.pt", 60, 960, -1)
    cel = tmp_path / "adat" / "weights" / "yolov8n.pt"
    assert cel.read_bytes() == b"HANGOLT"
    ki = capsys.readouterr().out
    assert f"ÉLESBE ÁLLÍTVA: {cel}" in ki
    assert "visszaállítás" in ki


def test_main_be_nem_fejezett_tanitasnal_1_es_nem_elesit(tmp_path,
                                                         monkeypatch, capsys):
    """Ha a tanítás után nincs best.pt (megszakadt / elszállt), a main
    1-et ad beszélő hibával, és --install mellett SEM élesít semmit."""
    adat = tmp_path / "dataset.yaml"
    adat.write_text("path: .\n", encoding="utf-8")
    _kornyezet(monkeypatch, tmp_path, ["--data", str(adat), "--install"],
               keszit_best=False)
    assert ft.main() == 1
    ki = capsys.readouterr().out
    assert "HIBA: nem található a kész modell (best.pt)" in ki
    assert "ÉLESBE ÁLLÍTVA" not in ki
    assert not (tmp_path / "adat" / "weights").exists()
