"""
Adattár-helyek — HOVA írhat a program (telepítve is).

A TELEPÍTETT alkalmazás a saját mappájába (Applications / Program Files) NEM
írhat — a meccseknek, a figura-könyvtárnak, a feltöltéseknek és a naplónak
felhasználói adatmappába kell kerülniük. Fejlesztéskor viszont maradjon minden
a repó backend/ mappájában (ahogy eddig), hogy egyszerű legyen a munka.

Sorrend:
1. HANDBALL_DATA_DIR környezeti változó (kifejezett felülbírálás),
2. csomagolt (PyInstaller "frozen") futásnál a platform szabvány-helye:
   - Windows: %LOCALAPPDATA%\\SportMachine
   - macOS:   ~/Library/Application Support/SportMachine
   - Linux:   $XDG_DATA_HOME/sportmachine (vagy ~/.local/share/sportmachine)
3. fejlesztői mód: a repó backend/ mappája (mint eddig).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def data_root() -> Path:
    """A program írható adat-gyökere (lásd a modul-docstringet)."""
    env = os.environ.get("HANDBALL_DATA_DIR")
    if env:
        return Path(env)
    if getattr(sys, "frozen", False):  # PyInstaller-csomagolt futás
        if sys.platform == "win32":
            base = Path(os.environ.get("LOCALAPPDATA",
                                       str(Path.home() / "AppData" / "Local")))
            return base / "SportMachine"
        if sys.platform == "darwin":
            return Path.home() / "Library" / "Application Support" / "SportMachine"
        xdg = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg) if xdg else Path.home() / ".local" / "share"
        return base / "sportmachine"
    # Fejlesztői mód: a backend/ mappa (ez a fájl handball/ alatt van).
    return Path(__file__).resolve().parents[1]
