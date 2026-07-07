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
hiddenimports += ["handball", "scripts"]

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
    console=True,          # háttérben fut; a kimenetét az app naplózza
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="handball_backend",
)
