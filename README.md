# handball_01 — Kézilabda elemző AI

## Letöltés (Windows / Mac) — mint egy Steam-játék

1. Nyisd meg a repo **Releases** oldalát (GitHub → jobb oldalt "Releases").
2. Töltsd le a legfrissebbet: Windowsra a **`SportMachine-Setup.exe`**-t, Macre a **`SportMachine-macOS.zip`**-et.
3. Dupla kattintás → Tovább → Telepítés → indul. Ennyi.

Nem kell hozzá Python, Flutter vagy bármilyen fejlesztői eszköz — a telepítő a
teljes programot (felület + elemző motor + AI-modell) egyben tartalmazza.
Laikus útmutató: [`TELEPITES.md`](TELEPITES.md).

> A telepítőt a GitHub Actions automatikusan gyártja
> ([.github/workflows/release.yml](.github/workflows/release.yml)):
> kézzel az Actions fülről indítható, kiadás pedig egy `v*` címke
> (`git tag v0.1.0 && git push origin v0.1.0`) pusholásával készül.

Videó- (és később LiDAR-) alapú elemző platform kézilabdára: csapatstílus
tanulása, egyéni játékos-döntéselemzés, figura-szimuláció ellenfél ellen, 3D/VR
bejárható meccsek és élő meccskövetés javaslatokkal.

## Dokumentáció
- [`docs/VISION.md`](docs/VISION.md) — mit építünk és miért (a teljes vízió).
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — a pipeline rétegei és a stack.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — fázisokra bontott útiterv.
- [`docs/MVP_PLAN.md`](docs/MVP_PLAN.md) — az 1. fázis (MVP) részletes terve.
- [`docs/RULES.md`](docs/RULES.md) — a követéshez releváns szabály-kivonat.
- [`docs/FOOTAGE_NOTES.md`](docs/FOOTAGE_NOTES.md) — a valódi felvétel megfigyelései
  és azok hatása a tervre (pásztázó kamera, sárga 6 m, több-vonal, kosárpalánk,
  sárga bírók, GoPro-torzítás).
- [`docs/BROADCAST_AND_SENSORS.md`](docs/BROADCAST_AND_SENSORS.md) — a jövőbeli
  bemenetek útiterve: telepített több-kamerás + lidar arénarendszer és
  TV-közvetítés-elemzés (ellenfél-felderítéshez).

## Kód
- [`backend/`](backend/) — szerveroldali Python csomag: a központi `Tracking`
  adatmodell (JSON, a kliens-szerződés), a `[A]–[H]` pipeline-váz, a meccs-
  szimulátor és a FastAPI. Lásd [`backend/README.md`](backend/README.md).
- [`client/`](client/) — Flutter kliens (desktop-first): a felülnézeti taktikai
  nézet, ami a backend Tracking JSON-ját rajzolja ki (backend nélkül beágyazott
  demóval is fut). Lásd [`client/README.md`](client/README.md).

## Hol tartunk
A rendszer **működő, telepíthető alkalmazás** (v0.1.17 kiadva; a v0.1.18
tartalma a CHANGELOG-ban):

- **Feldolgozás**: YOLO + ByteTrack követés, kézi 4-sarkos kalibráció
  méter-térbe, pásztázás-kompenzáció, csapat-szétválasztás, kapus- és
  mezszám-felismerés; megszakítás-biztos (checkpoint, folytatás).
- **AI-elemzés**: 50+ magyarázható réteg — események (gól/lövés/passz/
  labdaeladás), xG és ziccerek, védekezés-kép (blokkok, őrzési párok,
  labdaszerzők, betörés-folyosók), momentum (sorozatok, fordulópont,
  vezetés-váltások, hajrá, gólcsend), kondíció, fáradás és
  rotáció-mélység, passz- és gólpassz-hálózat, passz-láncok,
  beálló-terhelés, poszt-becslés, hetesek iránnyal, kapusonkénti GSAx
  és kapus-kimozdulás, fegyelem (kiülők/kiharcolók), szünet utáni
  kezdés, előny-kezelés, cserék, időkérések. Minden réteg magyar
  edzői nyelven indokol.
- **Felderítés és tervezés**: több-meccses ellenfél-profil pontos
  összegzéssel, edzői kulcsok, meccsterv-illesztés (19 páros szabály),
  fejlődés-követés trenddel, edzés-fókusz (32 szabály, szezon-szintű
  visszatérő gyengeségekkel), élő jelzések a padnak (félidei
  emberfogás/beálló/rotáció-kép, hajrá-protokoll).
- **Kimenetek**: edzői összefoglaló a meccs történetével, nyolc
  nyomtatható riport (meccs, felderítő, játékos-lap, szezon
  játékos-lap, fejlődés, szezon — hazai/idegen és ellenfél-mérleggel,
  egymás ellen — visszavágó-meccstervvel, toplisták), tematikus
  klip-csomagok (kulcs-pillanatoktól a beállós gólokig), Excel-kész
  CSV, teljes meccs-csomag zip, szezon-toplisták a kezdőlapon.
- **Új bemenetek (előkészítve)**: TV-közvetítés előfeldolgozás
  (vágás/totálkép-szűrő, pályavonal-felismerés), több-nézetes fúzió
  (`POST /matches/fuse`) és lidar-finomítás — részletek a
  [`docs/BROADCAST_AND_SENSORS.md`](docs/BROADCAST_AND_SENSORS.md)-ben.
- **Minőség**: 670+ automata teszt; réteg-megbízhatósági önjelentés
  (mihez van elég minta az adott meccsen).

## Elv
Alulról építkezünk. A megbízható 2D követés a rendszer gerince; minden további
elemzés (taktika, döntések, szimuláció, VR, élő javaslat) erre épül.
