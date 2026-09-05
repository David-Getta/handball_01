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


def _stage(msg: str) -> None:
    """Indulási mérföldkő a naplóba.

    Miért kell: a nehéz importok (torch, OpenCV) MÁSODPERCEKIG —
    becsomagolt kiadásban, víruskereső-átvizsgálással PERCEKIG — tartanak,
    és eddig az ELSŐ naplósor is csak utánuk jött. Ha a motor közben halt
    el (hiányzó rendszerkönyvtár, OpenMP-ütközés), a felhasználó ÜRES
    naplót látott, és nem lehetett megmondani, meddig jutott el. Ezek a
    sorok pontosan ezt mondják meg.
    """
    try:
        print(f"[indulás] {msg}", flush=True)
    except Exception:
        # Ablak nélküli futásnál a stdout hiányozhat (vagy a cső eltörhet).
        # A naplózás hibája SOSEM állíthatja meg az indulást.
        pass


def _crash_report(exc: BaseException) -> None:
    """A halálos kivétel kiírása a felhasználói adatmappába is.

    A kliens a csővön keresztül olvassa a kimenetünket, de ha a kliens
    előbb áll le (vagy a cső eltörik), a hiba oka nyomtalanul elvész. Ez
    a fájl az utolsó mentsvár — a diagnosztika is beolvassa.
    """
    import traceback
    # A LÉNYEG külön sorban, a nyomkövetés elé: a felhasználó ezt az egy
    # sort tudja továbbadni, ha a hosszú traceback elriasztja.
    fej = f"{type(exc).__name__}: {exc}"
    # A képernyőre írás maga is elhasalhat (nincs stdout — pont az az
    # eset, amikor a stream-átirányítás bukott el). A FÁJLBA írás ettől
    # függetlenül próbálkozzon: az a fontosabb.
    try:
        print(fej, flush=True)
        traceback.print_exc()
    except Exception:
        pass
    try:
        from handball.storage import data_root
        root = data_root()
        root.mkdir(parents=True, exist_ok=True)
        import datetime
        with open(root / "engine-crash.log", "a", encoding="utf-8") as f:
            f.write(f"\n=== {datetime.datetime.now().isoformat()} ===\n")
            f.write(fej + "\n")
            traceback.print_exc(file=f)
    except Exception:
        pass  # a hibajelentés hibája nem takarhatja el az eredeti hibát


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
    try:
        # A stream-átirányítás MAGA is elhasalhat: ha az adatmappa nem
        # írható (vállalati gép, OneDrive-ra terelt AppData), a nyitás
        # kivételt dob. Eddig ez a try-n KÍVÜL volt, tehát a motor nyom
        # nélkül halt meg — a hibajelentő maga sem futott le.
        _ensure_streams()
        # Az ELSŐ sor még a nehéz importok előtt megy ki: ebből tudjuk,
        # hogy a program egyáltalán elindult (a becsomagolt indító
        # lefutott).
        _stage(f"az indító elindult (python {sys.version.split()[0]})")

        _stage("webszerver betöltése…")
        import uvicorn

        _stage("elemző motor betöltése — az első futásnál ez a leglassabb "
               "lépés (a víruskereső átvizsgálja a programot)…")
        from handball.api.app import create_app

        _stage("a motor betöltve")

        host = os.environ.get("HANDBALL_HOST", "127.0.0.1")
        want = int(os.environ.get("HANDBALL_PORT", "8000"))
        port = pick_free_port(host, want)
        if port != want:
            print(f"FIGYELEM: a {want}-es port foglalt — tartalék port: {port}",
                  flush=True)

        # A frozen (PyInstaller) kiadásban NEM adhatunk import-sztringet a
        # uvicornnak (nincs reload/worker), ezért közvetlenül a kész
        # app-objektumot indítjuk.
        app = create_app()
        print(f"Sport Machine backend indul: http://{host}:{port}", flush=True)
        uvicorn.run(app, host=host, port=port, log_level="info")
        return 0
    except BaseException as exc:  # noqa: BLE001 — a MIÉRT-et meg kell őrizni
        # Ide a becsomagolt kiadás legcsúnyább hibái esnek: hiányzó
        # rendszerkönyvtár, OpenMP-ütközés, jogosultsági hiba az
        # adatmappán. Enélkül a folyamat némán meghalt, és a felhasználó
        # csak "Connection refused"-öt látott.
        _stage("VÉGZETES HIBA az indulás közben — a részletek alább")
        _crash_report(exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
