"""
Kliens-őrzés: a detektálás-próba a TÚL SOK embert is kimondja.

Miért: az éles meccsen a kalibráció a lelátót is a játéktérre
vetítette, és emiatt 27 "játékos" került a pályára. A próbakockán ez
egy pillanat alatt látszott volna — de a felület csak a KEVÉS
észlelést ismerte hibaként ("persons >= 8"), a sokat nem. Így az
egyórás feldolgozás után derült ki, hogy semmi sem használható.

Futtatás:
    python -m pytest tests/test_client_calib_check.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _upload_src() -> str:
    return (Path(__file__).resolve().parent.parent.parent / "client" / "lib"
            / "ui" / "upload_screen.dart").read_text(encoding="utf-8")


def test_probakocka_jelzi_a_tul_sok_embert():
    """A pályára eső 14+ ember a kalibráció hibája — mondjuk ki ott."""
    src = _upload_src()
    assert "tulSok" in src, "a próbakocka nem nézi a felső határt"
    assert "onCourt != null && onCourt > 18" in src, (
        "a küszöbnek a motoréval kell egyeznie (TOO_MANY_PLAYERS = 18)")
    assert "fél-pálya kalibrációt" in src, (
        "a figyelmeztetés mondja meg a teendőt is")


def test_a_verdikt_nem_lehet_jo_tul_sok_embernel():
    """A régi 'persons >= 8' önmagában a hibás esetet is átengedte."""
    src = _upload_src()
    assert "final ok = !tulSok && persons >= 8;" in src


def test_kezi_meccsablak_mezoi_leteznek():
    """A bemelegítés levágásának végső menekülőútja a kézi ablak."""
    src = _upload_src()
    assert "_matchWindowFields" in src
    assert "Meccs kezdete" in src
    assert "startS:" in src and "endS:" in src, (
        "a megadott ablak nem jut el a motorhoz")


def _calib_src() -> str:
    return (Path(__file__).resolve().parent.parent.parent / "client" / "lib"
            / "ui" / "calibration_screen.dart").read_text(encoding="utf-8")


def test_sarok_javaslat_elerheto_a_kalibralo_kepernyon():
    """A motor ad négyszög-javaslatot — legyen mivel betölteni.

    A javaslat (`suggested_quad`) régóta megvolt a `/broadcast/lines`
    válaszában, de a kliens csak SZÖVEGBEN említette ("van javaslat"),
    használni nem lehetett. Nulláról jelölni a 4 sarkot sokkal
    nehezebb, a rosszul jelölt sarok pedig az egész elemzést elviszi.
    """
    src = _calib_src()
    assert "_suggestCorners" in src
    assert "suggested_quad" in src, "a javaslat nem jut el a sarkokhoz"
    assert "Sarkok javaslata" in src, "nincs gomb, amivel betölthető"


def test_a_javaslat_ellenorzesre_szolit():
    """A javaslat segítség, nem garancia — ezt ki kell mondani."""
    src = _calib_src()
    assert "ELLENŐRIZD" in src


def test_kalibracio_nelkul_rakerdez_az_inditas():
    """Fél-egy órás munka nem indulhat el némán kalibráció nélkül."""
    src = _upload_src()
    assert "_askNoCalibration" in src
    assert "Nincs pálya-kalibráció" in src
    # Nem tiltás: a felhasználó dönthet úgy, hogy így is elindítja.
    assert "Indítás kalibráció nélkül" in src


def _match_src() -> str:
    return (Path(__file__).resolve().parent.parent.parent / "client" / "lib"
            / "ui" / "match_screen.dart").read_text(encoding="utf-8")


def test_a_jelentesbol_inditható_az_ujrafeldolgozas():
    """A jelentés megmondja a bajt — legyen ott a javítás gombja is.

    Az újrafeldolgozás gombja eddig CSAK a hibára futott munkákon
    látszott a kezdőlapon. A felhasználó esete viszont az volt, hogy a
    feldolgozás LEFUTOTT, csak használhatatlan lett — ott nem volt
    honnan újraindítani a javított kalibrációval.
    """
    src = _match_src()
    assert "_reprocessThisMatch" in src
    assert "Újrafeldolgozás a friss kalibrációval" in src


def test_elso_teendo_kiemelve_a_jelentesben():
    """Négy-hat figyelmeztetésnél az EGY teendő ne vesszen el."""
    src = _match_src()
    assert "next_action" in src
    assert "ELSŐ TEENDŐ" in src
