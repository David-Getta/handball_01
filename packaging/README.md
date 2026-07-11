# Csomagolás — telepíthető kiadás készítése

Ez a mappa azt írja le, hogyan lesz a fejlesztői projektből **egyetlen, laikusnak
is telepíthető program**. A végfelhasználó élménye: *letölt egy fájlt → dupla
kattintás → használ*. Nincs Python, nincs parancssor, nincs uvicorn.

> A tényleges buildet **az adott operációs rendszeren** kell futtatni (Windows-os
> telepítő csak Windowson készül, macOS-es csak macOS-en). Ezt a lépést a
> fejlesztő/kiadás-készítő végzi el egyszer; a végfelhasználónak már csak a kész
> telepítőt adjuk.

## Áttekintés

A kiadás két részből áll, egybe csomagolva:

1. **Motor (backend)** — a Python/ML elemző, PyInstallerrel **egyetlen, telepítés
   nélkül futó programmá** csomagolva, benne a YOLO súlyfájllal. (`packaging/backend.spec`)
2. **App (Flutter desktop)** — a felület. Induláskor **magától elindítja a motort**
   a háttérben (`client/lib/services/backend_launcher.dart`), és megvárja, míg kész.

A telepítő a motrot az app melletti `engine/` mappába teszi — pontosan oda, ahol
az app keresi. Így a felhasználónak semmit sem kell beállítania.

## Windows

```powershell
# 1) Motor becsomagolása (Python + PyInstaller kell a builder gépén)
.\packaging\build_backend.ps1

# 2) Flutter desktop build
cd client
flutter build windows --release
cd ..

# 3) Telepítő (Inno Setup kell: https://jrsoftware.org/isdl.php)
iscc packaging\installer_windows.iss
```

Eredmény: **`dist\installer\SportMachine-Setup.exe`** — ezt adjuk a felhasználónak.

## macOS — AUTOMATIZÁLVA

A macOS-app a GitHub Actions-ben automatikusan épül (`release.yml` →
`macos-app` job): motor (PyInstaller) → füstteszt → Flutter macOS build →
sandbox kikapcsolása → a motor beágyazása a `Resources/engine`-be → ad-hoc
aláírás → **`SportMachine-macOS.zip`** artifactként, `v*` címkénél a Releases
oldalra.

Kézi build ugyanezekkel a lépésekkel a fenti workflow-ból követhető.

> Ad-hoc aláírással a macOS első indításkor "ismeretlen fejlesztő"
> figyelmeztetést ad (jobb klikk → Megnyitás). Bolti terjesztéshez Apple
> Developer aláírás + notarizálás kell — későbbi lépés.

## Linux

```bash
bash packaging/build_backend.sh
cd client && flutter build linux --release && cd ..
# a dist/handball_backend/ tartalmát az app melletti engine/ mappába tesszük,
# majd AppImage/.deb csomagba (pl. appimagetool).
```

## Ellenőrző lista kiadás előtt

- [ ] `packaging/weights/yolov8n.pt` létezik (a build-szkript letölti; offline-hoz kell).
- [ ] A motor önmagában elindul: `handball_backend` → `http://127.0.0.1:8000/health` → `{"status":"ok"}`.
- [ ] Az app tiszta gépen (Python nélkül) elindul, a kezdőképernyő "A motor elindult" után belép.
- [ ] Egy rövid videó feldolgozása végigmegy, a meccs megjelenik a könyvtárban.

## Méret

A motor (PyTorch + OpenCV + ultralytics) miatt a kiadás nagy (~1–2 GB). Ez egy
asztali elemző-programnál elfogadható. Kisebb méret később: CPU-only/kvantált
modell, vagy a nehéz futtatás szerveren (távoli mód).
