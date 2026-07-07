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

## macOS

```bash
# 1) Motor becsomagolása
bash packaging/build_backend.sh

# 2) Flutter desktop build
cd client && flutter build macos --release && cd ..

# 3) A motrot az .app csomag Resources/engine mappájába másoljuk,
#    majd .dmg-t készítünk (pl. create-dmg).
APP="client/build/macos/Build/Products/Release/Sport Machine.app"
mkdir -p "$APP/Contents/Resources/engine"
cp -R dist/handball_backend/* "$APP/Contents/Resources/engine/"
# create-dmg "$APP"   # vagy Disk Utility → új képfájl
```

> Aláírás/notarizálás nélkül a macOS "ismeretlen fejlesztő" figyelmeztetést ad;
> éles terjesztéshez Apple Developer aláírás kell. (A backend_launcher a
> `Resources/engine`-ben is keresi a motort.)

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
