"""
Tesztek a szintetikus meccs-generáló szkriptre (scripts/simulate_match.py).

A szkript eddig egyszer sem futott a csomagban. Itt rövid (1–2 mp-es)
meccsekkel: az opció-olvasás, az összefoglaló, a fájlba írt Tracking JSON
(pásztázó kamera, illetve földi igazság) és az üres meccs.

Futtatás:
    python -m pytest tests/test_simulate_match.py -q
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import Match, PositionSource  # noqa: E402
from scripts import simulate_match as sm  # noqa: E402


def test_arg_kiolvassa_az_opciot_kulonben_az_alapertek():
    """Az `--név ÉRTÉK` alakú opciót a megadott típusra váltva adja; ha
    az opció nincs a parancssorban, az alapérték marad."""
    argv = ["simulate_match", "ki.json", "--seconds", "2.5", "--seed", "4"]
    assert sm._arg(argv, "--seconds", 8.0, float) == 2.5
    assert sm._arg(argv, "--seed", 0, int) == 4
    assert sm._arg(argv, "--fps", 25.0, float) == 25.0
    assert sm._arg(["simulate_match"], "--fov", 18.0, float) == 18.0


def test_main_fajl_nelkul_csak_osszefoglalot_ir(capsys):
    """Kimeneti fájl nélkül nem önti a JSON-t a kimenetre: a meccs mérete,
    a mért / becsült megoszlás és néhány játékos statisztikája jön."""
    assert sm.main(["simulate_match", "--seconds", "2", "--seed", "3"]) == 0
    ki = capsys.readouterr().out
    assert "Szimulált meccs: 50 frame, fps=25.0, seed=3" in ki
    assert "Pásztázó kamera:" in ki and "mért=" in ki and "becsült=" in ki
    assert "--- Néhány játékos statisztika (pásztázó kamera) ---" in ki
    assert ki.count("táv=") == 5                 # az első öt játékos
    assert "{" not in ki                         # nincs JSON a kimeneten


def test_main_a_paszatzo_kameras_trackinget_irja_fajlba(tmp_path, capsys):
    """Fájlnévvel a pásztázó-kamerás Tracking JSON a fájlba kerül: a
    Match visszaolvasható belőle, és van benne BECSÜLT pozíció is (a
    kamera nem lát mindenkit)."""
    ki_fajl = tmp_path / "meccs.json"
    assert sm.main(["simulate_match", str(ki_fajl), "--seconds", "2",
                    "--seed", "3", "--fov", "12"]) == 0
    assert f"Tracking JSON kiírva: {ki_fajl} (pásztázó kamera)" in \
        capsys.readouterr().out
    m = Match.from_dict(json.loads(ki_fajl.read_text(encoding="utf-8")))
    assert len(m.frames) == 50 and m.meta.fps == 25.0
    forrasok = {p.source for f in m.frames for p in f.players}
    assert forrasok == {PositionSource.MEASURED, PositionSource.ESTIMATED}


def test_main_ground_truth_a_teljes_foldi_igazsagot_irja(tmp_path, capsys):
    """A --ground-truth a teljes rálátású meccset írja ki: minden pozíció
    MÉRT; az opciók a fájlnév ELŐTT is állhatnak, és a képráta állítható."""
    ki_fajl = tmp_path / "igazsag.json"
    assert sm.main(["simulate_match", "--seconds", "2", "--fps", "10",
                    str(ki_fajl), "--ground-truth"]) == 0
    assert "(földi igazság)" in capsys.readouterr().out
    m = Match.from_dict(json.loads(ki_fajl.read_text(encoding="utf-8")))
    assert len(m.frames) == 20 and m.meta.fps == 10.0
    assert {p.source for f in m.frames for p in f.players} == {
        PositionSource.MEASURED}


def test_main_ugyanazzal_a_maggal_ugyanaz_a_meccs(tmp_path, capsys):
    """A mag (seed) megismételhetővé teszi a meccset; más maggal más
    meccs készül."""
    a, b, c = (tmp_path / n for n in ("a.json", "b.json", "c.json"))
    for fajl, mag in ((a, "5"), (b, "5"), (c, "6")):
        assert sm.main(["simulate_match", str(fajl), "--seconds", "1",
                        "--seed", mag]) == 0
    capsys.readouterr()
    assert a.read_text(encoding="utf-8") == b.read_text(encoding="utf-8")
    assert a.read_text(encoding="utf-8") != c.read_text(encoding="utf-8")


def test_main_nulla_hosszu_meccsen_sem_oszt_nullaval(capsys):
    """Nulla másodperces (üres) meccsen nincs kocka és nincs pozíció: az
    összefoglaló 0%-okat ír — osztás nullával és kivétel nélkül."""
    assert sm.main(["simulate_match", "--seconds", "0"]) == 0
    ki = capsys.readouterr().out
    assert "Szimulált meccs: 0 frame" in ki
    assert "0 játékos-pozíció összesen — mért=0 (0%), becsült=0 (0%)" in ki
    assert "táv=" not in ki
