# A Sport Machine "motor" (backend) becsomagolása Windows alatt.
# EGY telepítés nélkül futtatható programot állít elő (dist\handball_backend\).
#
# Futtatás a repo gyökeréből (PowerShell):  .\packaging\build_backend.ps1
$ErrorActionPreference = "Stop"

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Repo = Split-Path -Parent $Here
Set-Location $Repo

Write-Host "==> Fuggosegek telepitese (backend + ML + pyinstaller)..."
python -m pip install --upgrade pip
python -m pip install -e "backend[ml]" uvicorn pyinstaller

Write-Host "==> YOLO sulyfajl elokeszitese (packaging\weights\yolov8n.pt)..."
New-Item -ItemType Directory -Force -Path "$Here\weights" | Out-Null
if (-not (Test-Path "$Here\weights\yolov8n.pt")) {
  # Az ultralytics az AKTUALIS mappaba tolti le a kert sulyfajlt - oda lepunk.
  Push-Location "$Here\weights"
  python -c "from ultralytics import YOLO; YOLO('yolov8n.pt')"
  Pop-Location
}
if (-not (Test-Path "$Here\weights\yolov8n.pt")) { throw "A sulyfajl letoltese nem sikerult" }

Write-Host "==> PyInstaller..."
pyinstaller packaging\backend.spec --noconfirm --distpath dist --workpath build\pyi

Write-Host "==> Kesz: dist\handball_backend\handball_backend.exe"
Write-Host "    Teszt: .\dist\handball_backend\handball_backend.exe  (majd http://127.0.0.1:8000/health)"
