"""
Kliens-őrzés: a KÉSZ feldolgozás bejelentése bárhonnan.

Egy meccs feldolgozása percekig fut. A felhasználó közben más
képernyőn dolgozik az appban — és eddig CSAK úgy tudta meg, hogy kész,
ha visszament megnézni: a menü-jelvény eltűnése néma. A burokba tett
bejelentő sáv ezt zárja le.

Amit itt őrzünk (Flutter nélkül, forrásból olvasva):
  - a figyelő MELYIK munka lett kész kérdésre válaszol (nem csak azt,
    hogy "nincs több aktív"),
  - a MEGSZAKÍTOTT munkát nem jelenti be (azt a felhasználó kérte),
  - az első kör néma (a tegnapi kész elemzést ma reggel bejelenteni
    értelmetlen),
  - a bejelentő sáv a BUROKBAN van, tehát minden képernyőn ott van,
  - és van rajta elrejtés meg egy továbblépő gomb.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _lib() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "client" / "lib"


def test_figyelo_megmondja_melyik_munka_lett_kesz():
    """A bejelentéshez a munka REKORDJA kell, nem egy számláló."""
    src = (_lib() / "services" / "jobs_monitor.dart").read_text(
        encoding="utf-8")
    assert "lastFinished" in src, "nincs 'melyik lett kész' jelzés"
    assert "ValueNotifier<Map<String, dynamic>?>" in src, (
        "a bejelentéshez a munka rekordja kell (meccs-azonosító, hiba)")
    assert "dismissFinished" in src, "a bejelentést el kell tudni rejteni"


def test_figyelo_nem_jelenti_be_a_megszakitast():
    """A megszakítást a felhasználó kérte — az nem hír."""
    src = (_lib() / "services" / "jobs_monitor.dart").read_text(
        encoding="utf-8")
    assert '!= "cancelled"' in src, (
        "a megszakított munka bejelentése zavaró: azt a felhasználó "
        "maga állította le")


def test_figyelo_elso_kore_nema():
    """Indításkor minden munka 'új' — a régi kész elemzés nem hír."""
    src = (_lib() / "services" / "jobs_monitor.dart").read_text(
        encoding="utf-8")
    assert "elsoKor" in src, (
        "az első kör néma kell legyen, különben induláskor a tegnapi "
        "kész feldolgozást jelentené be")


def test_bejelento_sav_a_burokban_van():
    """A sáv csak akkor ér valamit, ha MINDEN képernyőn ott van."""
    src = (_lib() / "ui" / "shell" / "app_shell.dart").read_text(
        encoding="utf-8")
    assert "class _FinishedBanner" in src, "nincs bejelentő sáv a burokban"
    assert "const _FinishedBanner()," in src, (
        "a sáv nincs beépítve a burok szerkezetébe — akkor sosem látszik")
    # A leggyakoribb következő lépés (a kész meccs megnyitása) és a
    # kikapcsolás egy kattintás legyen.
    assert "Megnyitás" in src and "Elrejtés" in src
