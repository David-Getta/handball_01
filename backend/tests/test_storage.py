"""
Tesztek az adattár-helyekre (storage.py) — hova írhat a program.

Futtatás:
    python tests/test_storage.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contextlib import contextmanager

from handball.storage import data_root


@contextmanager
def _adatmappa_valtozo(ertek=None):
    """A HANDBALL_DATA_DIR a blokk idejére a megadott értékre áll (None:
    nincs beállítva), utána VISSZAÁLL a korábbira.

    A csomag több tucat API-tesztje beállítja ezt a változót, és nem
    mindegyik veszi vissza. E tesztek eddig arra építettek, hogy az első
    (az env-felülbírálás tesztje) épp előttük törli — párhuzamos
    futtatásnál (xdist) viszont a fájl tesztjei külön munkásra, más
    tesztek közé kerülhetnek, és a beállítva maradt változó miatt a
    fejlesztői / csomagolt mappa tesztje véletlenszerűen bukott."""
    regi = os.environ.get("HANDBALL_DATA_DIR")
    if ertek is None:
        os.environ.pop("HANDBALL_DATA_DIR", None)
    else:
        os.environ["HANDBALL_DATA_DIR"] = ertek
    try:
        yield
    finally:
        if regi is None:
            os.environ.pop("HANDBALL_DATA_DIR", None)
        else:
            os.environ["HANDBALL_DATA_DIR"] = regi


def test_env_override_wins():
    """A HANDBALL_DATA_DIR mindent felülbírál."""
    with _adatmappa_valtozo("/tmp/hb-test-data"):
        assert data_root() == Path("/tmp/hb-test-data")


def test_dev_mode_is_backend_dir():
    """Fejlesztői módban a repó backend/ mappája (mint eddig)."""
    with _adatmappa_valtozo(None):
        root = data_root()
    assert root.name == "backend"
    assert (root / "handball").is_dir()


def test_a_tesztek_nem_fuggnek_a_kornyezet_maradekatol():
    """ŐR: a mappa-tesztek akkor is ugyanazt adják, ha egy korábbi teszt
    beállítva hagyta a HANDBALL_DATA_DIR-t — és maguk nem hagynak nyomot
    (a változó a blokk után a korábbi értékén áll)."""
    with _adatmappa_valtozo("/tmp/egy-korabbi-teszt-maradeka"):
        test_dev_mode_is_backend_dir()
        test_frozen_paths_per_platform()
        test_env_override_wins()
        assert os.environ["HANDBALL_DATA_DIR"] == \
            "/tmp/egy-korabbi-teszt-maradeka"
    with _adatmappa_valtozo(None):
        test_env_override_wins()
        assert "HANDBALL_DATA_DIR" not in os.environ


def test_frozen_paths_per_platform():
    """Csomagolt futásnál platform szerinti felhasználói adatmappa."""
    with _adatmappa_valtozo(None):
        _frozen_paths_per_platform()


def _frozen_paths_per_platform():
    orig_platform = sys.platform
    try:
        sys.frozen = True  # a PyInstaller így jelzi magát
        sys.platform = "darwin"
        assert str(data_root()).endswith("Library/Application Support/SportMachine")
        sys.platform = "linux"
        os.environ.pop("XDG_DATA_HOME", None)
        assert str(data_root()).endswith(".local/share/sportmachine")
        os.environ["XDG_DATA_HOME"] = "/tmp/xdg"
        assert data_root() == Path("/tmp/xdg/sportmachine")
        sys.platform = "win32"
        os.environ["LOCALAPPDATA"] = r"C:\Users\x\AppData\Local"
        assert str(data_root()).endswith("SportMachine")
    finally:
        del sys.frozen
        sys.platform = orig_platform
        os.environ.pop("XDG_DATA_HOME", None)
        os.environ.pop("LOCALAPPDATA", None)


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    print(f"\n{'OK' if failures == 0 else failures} hibás teszt")
    raise SystemExit(1 if failures else 0)
