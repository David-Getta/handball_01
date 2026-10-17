"""Az elakadt képkockát átugró adagoló (StallSkippingFeed) tesztjei.

Terepen látott hiba: a videó-olvasás natív szinten beragad egy fix
képkockánál, és a feldolgozás örökre megáll rajta. Az adagolónak ilyenkor
NEM feladnia kell, hanem a rossz kockát átugrania és a következőtől
folytatnia — feladás csak sok egymást követő elakadás után jár.

Futtatás:
    python -m pytest tests/test_stall_skip.py
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.process_video import StallSkippingFeed  # noqa: E402


def _blokkolo(*elemek):
    """Termelő, amely a megadott elemek után beragad (mint a hibás kocka)."""
    def _gen():
        yield from elemek
        time.sleep(600.0)   # "natív" beragadás — a szál árván marad
    return _gen()


def test_elakadt_kocka_atugrasa_es_folytatas():
    """Két jó kocka után beragadó olvasó: a rossz kockát átugorja, és a
    folytató-olvasóval a KÖVETKEZŐ pozíciótól megy tovább."""
    hivasok = []

    def _folytato(start):
        hivasok.append(start)
        return iter([f"r{start}"])

    feed = StallSkippingFeed(_blokkolo(1, 2), resume_factory=_folytato,
                             stride=2, first_timeout_s=0.5,
                             skip_timeout_s=0.3, max_skips=5)
    kapott = list(feed.frames())
    assert kapott == [1, 2, "r6"], kapott
    # A jó kockák a 0. és 2. pozíción voltak; a 4. ragadt be → a
    # folytatás a 6.-tól indul.
    assert hivasok == [6], hivasok
    assert feed.skips == 1
    assert feed.stalled is False


def test_folytato_nelkul_felad():
    """Folytató-olvasó nélkül a régi viselkedés él: részleges mentés."""
    feed = StallSkippingFeed(_blokkolo(), resume_factory=None,
                             stride=1, first_timeout_s=0.3,
                             skip_timeout_s=0.3)
    assert list(feed.frames()) == []
    assert feed.stalled is True


def test_tul_sok_elakadas_utan_felad():
    """Ha az átugrások száma eléri a plafont, az adagoló felad, és a
    stalled jelzővel az addig kész rész mentődik."""
    feed = StallSkippingFeed(
        _blokkolo("a"), resume_factory=lambda start: _blokkolo(),
        stride=3, first_timeout_s=0.5, skip_timeout_s=0.25,
        max_skips=2)
    assert list(feed.frames()) == ["a"]
    assert feed.skips == 2
    assert feed.stalled is True


def test_ismetelt_elakadasnal_nagyobbat_ugrik():
    """Ha a folytató-olvasó SEM ad kockát, a hibás szakasz hosszabb egy
    kockánál — ilyenkor egyre nagyobbat kell ugrani, különben a
    feldolgozás percekig ugyanabban a rossz szakaszban toporog."""
    hivasok = []

    def _folytato(start):
        hivasok.append(start)
        # A második és harmadik kísérlet is beragad (üres, blokkoló).
        return _blokkolo()

    feed = StallSkippingFeed(_blokkolo(1), resume_factory=_folytato,
                             stride=2, first_timeout_s=0.4,
                             skip_timeout_s=0.2, max_skips=3)
    assert list(feed.frames()) == [1]
    # 0. kocka jó → a 2. ragadt be. Az ugrás-táv: 2, majd 8, majd 32.
    assert hivasok == [4, 12, 44], hivasok
    assert feed.skips == 3 and feed.stalled is True


def test_atugras_szol_a_felhasznalonak():
    """Az átugrás visszajelzést ad (a felület enélkül állni látszik)."""
    uzenetek = []
    feed = StallSkippingFeed(_blokkolo(1), resume_factory=lambda s: iter(["x"]),
                             stride=1, first_timeout_s=0.4,
                             skip_timeout_s=0.2, max_skips=2,
                             on_skip=uzenetek.append)
    assert list(feed.frames()) == [1, "x"]
    assert len(uzenetek) == 1, uzenetek
    assert "átugorva" in uzenetek[0] and "folytatás" in uzenetek[0]


def test_sikeres_kocka_utan_visszaall_az_ugras_tav():
    """Ha az átugrás után JÖTT kocka, a következő elakadásnál megint a
    legkisebb ugrással próbálkozunk — nem hagyunk ki feleslegesen."""
    hivasok = []

    def _folytato(start):
        hivasok.append(start)
        # Az első folytatás ad egy kockát, majd újra beragad.
        return _blokkolo("x") if len(hivasok) == 1 else _blokkolo()

    feed = StallSkippingFeed(_blokkolo(1), resume_factory=_folytato,
                             stride=1, first_timeout_s=0.4,
                             skip_timeout_s=0.2, max_skips=2)
    assert list(feed.frames()) == [1, "x"]
    # 0. jó → 1. ragad (ugrás 1) → a 2. pozíciótól jön "x" → a 3.
    # ragad be, és ott ismét a legkisebb ugrás jön (1), nem a növelt.
    assert hivasok == [2, 4], hivasok


# --- Időkorlátos dúsító (TimeboxedEnricher) --------------------------
#
# A StallSkippingFeed a termelő oldalt védi; a fogyasztó cikluson
# belüli dúsítók (mezszám-OCR, labda-újrakeresés) beragadása ellen a
# TimeboxedEnricher véd: a hívás időkorláttal fut, beragadásnál
# kihagyjuk, sok beragadás után a dúsítót kikapcsoljuk — a fő
# detektálás sosem állhat meg miatta.

from scripts.process_video import TimeboxedEnricher  # noqa: E402


def test_gyors_dusito_eredmenye_atmegy():
    """A rendben visszatérő hívás eredménye változatlanul jön vissza."""
    guard = TimeboxedEnricher("teszt", timeout_s=1.0)
    assert guard.call(lambda: 42) == 42
    assert not guard.disabled


def test_beragadt_dusito_kihagyva_majd_kikapcsolva():
    """A beragadó hívást kihagyjuk (None), és max_timeouts beragadás
    után a dúsító kikapcsol — a további hívások futás nélkül None-t
    adnak."""
    guard = TimeboxedEnricher("teszt", timeout_s=0.05, max_timeouts=2)
    assert guard.call(lambda: time.sleep(5.0)) is None
    assert not guard.disabled
    assert guard.call(lambda: time.sleep(5.0)) is None
    assert guard.disabled
    futott = []
    assert guard.call(lambda: futott.append(1)) is None
    assert futott == []


def test_dusito_hibaja_nem_szamit_beragadasnak():
    """A kivétellel elhasaló hívás None-t ad, de nem kapcsolja ki a
    dúsítót — a hiba nem beragadás."""
    def _hibas():
        raise RuntimeError("OCR-hiba")

    guard = TimeboxedEnricher("teszt", timeout_s=1.0, max_timeouts=1)
    assert guard.call(_hibas) is None
    assert not guard.disabled
    assert guard.call(lambda: "jo") == "jo"


def test_beragadas_szol_a_felhasznalonak():
    """A beragadásról a felület is értesül (on_note)."""
    uzenetek = []
    guard = TimeboxedEnricher("mezszám-OCR", timeout_s=0.05,
                              on_note=uzenetek.append)
    guard.call(lambda: time.sleep(5.0))
    assert uzenetek and "mezszám-OCR" in uzenetek[0]
    assert "kihagyva" in uzenetek[0]
