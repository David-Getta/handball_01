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

from handball.storage import data_root


def test_env_override_wins():
    """A HANDBALL_DATA_DIR mindent felülbírál."""
    os.environ["HANDBALL_DATA_DIR"] = "/tmp/hb-test-data"
    try:
        assert data_root() == Path("/tmp/hb-test-data")
    finally:
        del os.environ["HANDBALL_DATA_DIR"]


def test_dev_mode_is_backend_dir():
    """Fejlesztői módban a repó backend/ mappája (mint eddig)."""
    root = data_root()
    assert root.name == "backend"
    assert (root / "handball").is_dir()


def test_frozen_paths_per_platform():
    """Csomagolt futásnál platform szerinti felhasználói adatmappa."""
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
