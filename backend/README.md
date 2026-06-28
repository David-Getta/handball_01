# Backend — videó → Tracking → statisztika

A kézilabda-elemző **szerveroldali** csomagja. A nehéz feldolgozás (detektálás,
követés, becslés) itt fut; a Flutter-kliens csak a kész JSON-t kéri le.

> Tervek és döntések: a repó gyökerében a `docs/` mappa
> (`ARCHITECTURE.md`, `MVP_PLAN.md`, `RULES.md`).

## Felépítés

```
backend/
├── handball/
│   ├── models/
│   │   ├── tracking.py   # ⭐ KÖZPONTI: Match/Frame/PlayerPosition + JSON (a kliens-szerződés)
│   │   └── events.py     # dinamikus létszám: kiállítások, kapus nélküli játék
│   ├── pipeline/         # [A]–[H] lépések (most kommentált csontvázak)
│   │   ├── calibration.py   # [A] homográfia (pásztázó kamera)
│   │   ├── detection.py     # [B] YOLO detektálás
│   │   ├── tracking_step.py # [C] követés + ReID + mezszám-OCR
│   │   ├── teams.py         # [D] csapatba sorolás mezszín alapján
│   │   ├── court_coords.py  # [E] kép -> pálya (méter)
│   │   ├── estimation.py    # [F] képen kívüli játékosok becslése
│   │   ├── stats.py         # [H] táv/sebesség (valódi számítás)
│   │   └── pipeline.py      # a lépéseket összefogó vezérlés
│   └── api/app.py        # FastAPI: a kliens innen kéri a Tracking JSON-t
├── scripts/run_pipeline.py  # futtatható demó: szintetikus Tracking JSON
└── tests/test_tracking_model.py  # a modell JSON round-trip + statisztika tesztjei
```

## Hol tart most

A **váz** kész: a központi `Tracking` adatmodell teljes és JSON-ra szerializálható,
a pipeline-lépések felülete és a köztük lévő adatfolyam rögzített. A nehéz modellek
(YOLO, ByteTrack, OpenCV) helyén kommentált `TODO`-k állnak — ezek lépésről lépésre
behelyettesíthetők a szerkezet változtatása nélkül.

## Futtatás (függőség nélkül is megy)

```bash
cd backend

# Demó: szintetikus Tracking JSON + statisztika a kimenetre
python -m scripts.run_pipeline

# Tesztek (pytest nélkül is futnak; a backend/ legyen a kereső-útvonalon)
PYTHONPATH=. python tests/test_tracking_model.py
# vagy ha van pytest:  PYTHONPATH=. python -m pytest
```

## API-szerver indítása (FastAPI kell hozzá)

```bash
pip install -e .          # fastapi + uvicorn
uvicorn "handball.api.app:create_app" --factory --reload
# GET /health, GET /matches/{id}, GET /matches/{id}/stats
```

A valódi videó-feldolgozáshoz az ML-extra: `pip install -e ".[ml]"`
(ultralytics, opencv, numpy).
