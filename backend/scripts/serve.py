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

# Natív OpenMP-ütközés elleni védelem — MÉG a nehéz importok (torch, OpenCV,
# numpy) ELŐTT kell beállítani, különben késő. A becsomagolt (PyInstaller)
# macOS-kiadásban a PyTorch libiomp5-je és az OpenCV/numpy libomp-ja
# ütközhet; az OpenMP ilyenkor abort()-ol az első nehéz numerikus hívásnál
# (kalibráció/detektálás), és a motor-folyamat CSENDBEN meghal — a kliens
# csak "Connection refused"-öt lát. A KMP_DUPLICATE_LIB_OK engedi a
# párhuzamos futásidőt (nem csökkenti a szálszámot, így a sebességet sem).
# Az MPS-fallback pedig a nem támogatott Apple-GPU műveleteket CPU-ra tereli
# ahelyett, hogy elszállna. Csak akkor állítjuk be, ha a felhasználó nem
# adott meg mást (setdefault).
for _k, _v in (("KMP_DUPLICATE_LIB_OK", "TRUE"),
               ("PYTORCH_ENABLE_MPS_FALLBACK", "1")):
    os.environ.setdefault(_k, _v)


def _ensure_streams() -> None:
    """Ablak nélküli (windowed) csomagolt futásnál nincs stdout/stderr — ilyenkor
    a kimenetet az exe melletti engine.log fájlba irányítjuk, hogy a print/log
    ne dőljön el, és hiba esetén legyen mit megnézni."""
    if sys.stdout is None or sys.stderr is None:
        # A napló a FELHASZNÁLÓI adatmappába megy — a telepített app a saját
        # mappájába (Applications / Program Files) nem írhat.
        from handball.storage import data_root
        root = data_root()
        root.mkdir(parents=True, exist_ok=True)
        log_path = str(root / "engine.log")
        f = open(log_path, "a", buffering=1, encoding="utf-8", errors="replace")
        if sys.stdout is None:
            sys.stdout = f
        if sys.stderr is None:
            sys.stderr = f


def pick_free_port(host: str, start_port: int, tries: int = 11) -> int:
    """Az első SZABAD port a start_porttól felfelé (max `tries` próbálkozás).

    Ha a 8000-est már használja valami (másik program, beragadt régi motor),
    a motor nem hal el, hanem a következő szabad portra köt — a kliens
    indítója ugyanezt a tartományt fésüli át a /health-tel."""
    import socket
    for port in range(start_port, start_port + tries):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind((host, port))
            return port
        except OSError:
            continue
        finally:
            s.close()
    return start_port  # nincs szabad — az eredeti, érthető bind-hibát adja


def main() -> int:
    _ensure_streams()
    import uvicorn
    from handball.api.app import create_app

    host = os.environ.get("HANDBALL_HOST", "127.0.0.1")
    want = int(os.environ.get("HANDBALL_PORT", "8000"))
    port = pick_free_port(host, want)
    if port != want:
        print(f"FIGYELEM: a {want}-es port foglalt — tartalék port: {port}",
              flush=True)

    # A frozen (PyInstaller) kiadásban NEM adhatunk import-sztringet a uvicornnak
    # (nincs reload/worker), ezért közvetlenül a kész app-objektumot indítjuk.
    app = create_app()
    print(f"Sport Machine backend indul: http://{host}:{port}", flush=True)
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
