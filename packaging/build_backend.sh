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
  # Az ultralytics az AKTUÁLIS mappába tölti le a kért súlyfájlt — oda lépünk.
  (cd "$HERE/weights" && python3 -c "from ultralytics import YOLO; YOLO('yolov8n.pt')")
fi
[ -f "$HERE/weights/yolov8n.pt" ] || { echo "HIBA: a súlyfájl letöltése nem sikerült"; exit 1; }

echo "==> PyInstaller…"
pyinstaller packaging/backend.spec --noconfirm --distpath dist --workpath build/pyi

echo "==> Kész: dist/handball_backend/handball_backend"
echo "    Teszt:  ./dist/handball_backend/handball_backend  (majd böngészőben http://127.0.0.1:8000/health)"
