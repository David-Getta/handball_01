"""
A backend indítója EGY paranccsal / EGY futtatható fájlként.

Ezt használja a becsomagolt (telepítés nélküli) kiadás: a Flutter-app ezt a
programot indítja a háttérben, a felhasználónak nem kell semmit beírnia.
Fejlesztéskor is futtatható közvetlenül:

    python -m scripts.serve            # http://127.0.0.1:8000

Környezeti változók (opcionális):
    HANDBALL_HOST (alap: 127.0.0.1), HANDBALL_PORT (alap: 8000)
"""

from __future__ import annotations

import os
import sys


def _ensure_streams() -> None:
    """Ablak nélküli (windowed) csomagolt futásnál nincs stdout/stderr — ilyenkor
    a kimenetet az exe melletti engine.log fájlba irányítjuk, hogy a print/log
    ne dőljön el, és hiba esetén legyen mit megnézni."""
    if sys.stdout is None or sys.stderr is None:
        log_path = os.path.join(os.path.dirname(sys.executable), "engine.log")
        f = open(log_path, "a", buffering=1, encoding="utf-8", errors="replace")
        if sys.stdout is None:
            sys.stdout = f
        if sys.stderr is None:
            sys.stderr = f


def main() -> int:
    _ensure_streams()
    import uvicorn
    from handball.api.app import create_app

    host = os.environ.get("HANDBALL_HOST", "127.0.0.1")
    port = int(os.environ.get("HANDBALL_PORT", "8000"))

    # A frozen (PyInstaller) kiadásban NEM adhatunk import-sztringet a uvicornnak
    # (nincs reload/worker), ezért közvetlenül a kész app-objektumot indítjuk.
    app = create_app()
    print(f"Sport Machine backend indul: http://{host}:{port}", flush=True)
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
