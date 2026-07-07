#!/usr/bin/env bash
# A Sport Machine "motor" (backend) becsomagolása macOS/Linux alatt.
# EGY telepítés nélkül futtatható programot állít elő (dist/handball_backend/).
#
# Futtatás a repo gyökeréből:  bash packaging/build_backend.sh
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
cd "$REPO"

echo "==> Függőségek telepítése (backend + ML + pyinstaller)…"
python3 -m pip install --upgrade pip
python3 -m pip install -e "backend[ml]" uvicorn pyinstaller

echo "==> YOLO súlyfájl előkészítése (packaging/weights/yolov8n.pt)…"
mkdir -p "$HERE/weights"
if [ ! -f "$HERE/weights/yolov8n.pt" ]; then
  # Az ultralytics letölti az első példányosításkor; onnan másoljuk a csomagba.
  python3 - <<'PY'
from ultralytics import YOLO
import shutil, os
YOLO("yolov8n.pt")  # letöltés a gyorsítótárba
for root, _, files in os.walk(os.path.expanduser("~")):
    if "yolov8n.pt" in files:
        shutil.copy(os.path.join(root, "yolov8n.pt"), os.path.join(os.path.dirname(__file__) if False else "packaging/weights", "yolov8n.pt"))
        print("Súlyfájl bemásolva a csomagba.")
        break
PY
fi

echo "==> PyInstaller…"
pyinstaller packaging/backend.spec --noconfirm --distpath dist --workpath build/pyi

echo "==> Kész: dist/handball_backend/handball_backend"
echo "    Teszt:  ./dist/handball_backend/handball_backend  (majd böngészőben http://127.0.0.1:8000/health)"
