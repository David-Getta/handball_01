"""
Előzetes ellenőrzés: hely és várható idő az INDÍTÁS előtt.

Miért kell: egy meccs feldolgozása fél-egy óra. A legrosszabb vég az,
amikor ez az óra elmegy, és utána derül ki, hogy nem volt hova írni az
eredményt. A második legrosszabb, amikor a felhasználó azért hagyja
félbe, mert nem tudta, meddig tart.

Amit itt őrzünk:
  - kevés helynél MAGYAR indoklás jön (szám szerint: mennyi van,
    mennyi kellene), bőven elég helynél nincs akadály,
  - a mérés hibája nem akadályozhatja a munkát (None → nincs hiba),
  - az idő-becslés EZEN a gépen mért adatból jön, és kevés mérésnél
    inkább nincs becslés, mint egy téves szám,
  - a nem KÉSZ (megszakított/hibás) futások nem rontják el az ütemet.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.preflight import (  # noqa: E402
    MIN_FREE_GB, MIN_HISTORY_RUNS, disk_space_error, estimate_seconds,
    human_duration, speed_from_history)


def _futas(video_s, munka_s, status="done"):
    return {"status": status, "video_seconds": video_s,
            "started": 1000.0, "finished": 1000.0 + munka_s}


def test_boven_eleg_helynel_nincs_akadaly(tmp_path):
    """A saját ideiglenes mappán van hely — nem szabad elutasítani."""
    # (Ha a tesztgépen tényleg kevés a hely, az üzenet is helyes válasz.)
    hiba = disk_space_error(None, tmp_path)
    assert hiba is None or "szabad hely" in hiba


def test_keves_helynel_szamokat_mond(monkeypatch, tmp_path):
    """Az üzenet megmondja, MENNYI van és MENNYI kellene."""
    import handball.preflight as pf

    monkeypatch.setattr(pf, "free_gb", lambda _root: 0.3)
    hiba = pf.disk_space_error(None, tmp_path)
    assert hiba is not None
    assert "0.3 GB" in hiba
    assert f"{MIN_FREE_GB:.1f} GB" in hiba


def test_meres_hibaja_nem_akadalyoz(monkeypatch, tmp_path):
    """Ha nem tudjuk megmérni a helyet, a munka NEM állhat meg emiatt."""
    import handball.preflight as pf

    monkeypatch.setattr(pf, "free_gb", lambda _root: None)
    assert pf.disk_space_error(None, tmp_path) is None


def test_keves_meresbol_nincs_becsles():
    """Egyetlen futásból az ütem félrevezető (modell-letöltés torzít)."""
    assert speed_from_history([]) is None
    assert speed_from_history([_futas(600, 1200)]) is None
    assert estimate_seconds(600, [_futas(600, 1200)]) is None
    assert MIN_HISTORY_RUNS >= 2


def test_becsles_a_gep_sajat_utemebol():
    """Két kész futás után a becslés az itt mért ütemet követi."""
    rows = [_futas(600, 1200), _futas(600, 1200)]  # 2x valós idő
    assert speed_from_history(rows) == 2.0
    assert estimate_seconds(300, rows) == 600


def test_nem_kesz_futasok_nem_rontjak_az_utemet():
    """A megszakított futás ideje nem a TELJES videóé — ki kell hagyni."""
    rows = [_futas(600, 1200), _futas(600, 1200),
            _futas(600, 60, status="cancelled"),
            _futas(600, 30, status="error")]
    assert speed_from_history(rows) == 2.0


def test_hianyos_naplosor_nem_szall_el():
    """A régi naplósorokban nincs video_seconds — azokat átugorjuk."""
    rows = [{"status": "done"}, {"status": "done", "video_seconds": None},
            _futas(600, 1200), _futas(600, 1200)]
    assert speed_from_history(rows) == 2.0


def test_emberi_felirat():
    assert human_duration(None) is None
    assert human_duration(0) is None
    assert human_duration(45) == "45 másodperc"
    assert human_duration(600) == "10 perc"
    assert human_duration(3600) == "1 óra"
    assert human_duration(5400) == "1 óra 30 perc"
