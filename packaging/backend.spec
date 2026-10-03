# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller-spec a Sport Machine "motorhoz" (backend) — EGYETLEN, telepítés nélkül
futtatható programot állít elő, amelybe be van csomagolva a Python, az összes
függőség (FastAPI/uvicorn, OpenCV, PyTorch, ultralytics) ÉS a YOLO súlyfájl.

Így a végfelhasználónak NEM kell Pythont telepítenie: az app ezt a programot
indítja a háttérben (lásd client/lib/services/backend_launcher.dart).

Építés (a builder gépén, az adott OS-en):
    pip install -e "backend[ml]" pyinstaller uvicorn
    # a súlyfájl legyen itt: packaging/weights/yolov8n.pt
    pyinstaller packaging/backend.spec --noconfirm

Eredmény: dist/handball_backend/handball_backend(.exe) (onedir — gyorsabb indulás).
"""

import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

# A repo gyökere a spec helyéből (packaging/) — a backend és a súlyok megtalálásához.
REPO = os.path.dirname(os.path.abspath(SPECPATH))
BACKEND = os.path.join(REPO, "backend")
ENTRY = os.path.join(BACKEND, "scripts", "serve.py")

datas, binaries, hiddenimports = [], [], []

# A nagy csomagok ADAT- és kódfájljainak teljes begyűjtése (különben hiányoznak
# a modell-definíciók, tracker-yaml-ok, natív libek).
for pkg in ["ultralytics", "torch", "torchvision", "cv2", "uvicorn",
            "fastapi", "starlette", "pydantic", "numpy"]:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as e:  # noqa: BLE001
        print(f"[backend.spec] figyelmeztetés: {pkg} nem gyűjthető: {e}")

# uvicorn dinamikus importjai (protokollok/loopok) — biztos, ami biztos.
hiddenimports += collect_submodules("uvicorn")
# A projekt SOK modult futásidőben, FÜGGVÉNYEN BELÜL importál (a rétegek
# szándékosan így izoláltak: `from .xg import ...` a függvény testében). A
# PyInstaller statikus elemzése ezekre nem mindig fut rá, és a hiányzó modul
# némán jelentkezik: a réteg try/except-je elnyeli, a fiók-végpont pedig
# hibát ad. Ezért a két saját csomag MINDEN almodulját kifejezetten
# begyűjtjük — ez pár száz kB, cserébe nem maradhat ki semmi.
hiddenimports += ["handball", "scripts"]
# A begyűjtéshez a backend/ mappának a keresési úton kell lennie (a spec
# saját Python-folyamatban fut). Ha valamiért mégsem importálható, a build
# nem áll meg — csak figyelmeztet, és marad a régi, szűkebb lista.
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)
for own in ("handball", "scripts"):
    try:
        subs = collect_submodules(own)
        hiddenimports += subs
        print(f"[backend.spec] {own}: {len(subs)} almodul becsomagolva")
    except Exception as e:  # noqa: BLE001
        print(f"[backend.spec] FIGYELEM: {own} almoduljai nem gyűjthetők: {e}")

# A tanított számjegy-háló (mezszám-OCR) a handball csomag adata — a
# PyInstaller a .py-kon kívül mást nem visz magától, ezért kifejezetten.
_digit_net = os.path.join(BACKEND, "handball", "pipeline", "digit_net.npz")
if os.path.exists(_digit_net):
    datas += [(_digit_net, "handball/pipeline")]
else:
    print("[backend.spec] FIGYELEM: digit_net.npz hiányzik — a mezszám-OCR "
          "sablon-illesztéssel (gyengébben) megy.")

# A YOLO súlyfájl becsomagolása (a build-szkript teszi ide).
_weights = os.path.join(SPECPATH, "weights", "yolov8n.pt")
if os.path.exists(_weights):
    datas += [(_weights, "weights")]
else:
    print("[backend.spec] FIGYELEM: packaging/weights/yolov8n.pt hiányzik — "
          "a motor futásidőben próbálja letölteni (offline nem fog menni).")

a = Analysis(
    [ENTRY],
    pathex=[BACKEND],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="handball_backend",
    # Ablak NÉLKÜL fut (nincs felvillanó fekete konzol a felhasználónál);
    # a napló az exe melletti engine.log-ba megy (lásd scripts/serve.py).
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="handball_backend",
)
