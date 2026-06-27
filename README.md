# handball_01 — Kézilabda elemző AI

Videó- (és később LiDAR-) alapú elemző platform kézilabdára: csapatstílus
tanulása, egyéni játékos-döntéselemzés, figura-szimuláció ellenfél ellen, 3D/VR
bejárható meccsek és élő meccskövetés javaslatokkal.

## Dokumentáció
- [`docs/VISION.md`](docs/VISION.md) — mit építünk és miért (a teljes vízió).
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — a pipeline rétegei és a stack.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — fázisokra bontott útiterv.
- [`docs/MVP_PLAN.md`](docs/MVP_PLAN.md) — az 1. fázis (MVP) részletes terve.
- [`docs/RULES.md`](docs/RULES.md) — a követéshez releváns szabály-kivonat.

## Hol tartunk
**0. fázis (alapok)** kész — repó-struktúra és tervek.
**Következő: 1. fázis (MVP)** — 2D követés videóból + felülnézeti taktikai nézet.

## Elv
Alulról építkezünk. A megbízható 2D követés a rendszer gerince; minden további
elemzés (taktika, döntések, szimuláció, VR, élő javaslat) erre épül.
