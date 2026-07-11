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

## Kód
- [`backend/`](backend/) — szerveroldali Python csomag: a központi `Tracking`
  adatmodell (JSON, a kliens-szerződés), a `[A]–[H]` pipeline-váz, a meccs-
  szimulátor és a FastAPI. Lásd [`backend/README.md`](backend/README.md).
- [`client/`](client/) — Flutter kliens (desktop-first): a felülnézeti taktikai
  nézet, ami a backend Tracking JSON-ját rajzolja ki (backend nélkül beágyazott
  demóval is fut). Lásd [`client/README.md`](client/README.md).

## Hol tartunk
**0. fázis (alapok)** kész — repó-struktúra és tervek.
**1. fázis (MVP)** folyamatban — a backend **váza** kész (Tracking modell + JSON +
pipeline-csontváz + tesztek); a valódi modellek (YOLO, követés) behelyettesítése
következik. A kliens **Flutter** lesz (Win/Mac/iPad/Android).

## Elv
Alulról építkezünk. A megbízható 2D követés a rendszer gerince; minden további
elemzés (taktika, döntések, szimuláció, VR, élő javaslat) erre épül.
