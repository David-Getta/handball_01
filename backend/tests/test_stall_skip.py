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
