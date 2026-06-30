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
│   ├── api/app.py        # FastAPI: a kliens innen kéri a Tracking JSON-t
│   └── sim/              # meccs-szimulátor: valósághű Tracking VIDEÓ NÉLKÜL
│       └── match_simulator.py
├── scripts/
│   ├── run_pipeline.py   # futtatható demó: kicsi szintetikus Tracking JSON
│   └── simulate_match.py # teljes szintetikus meccs (földi igazság + pásztázó kamera)
└── tests/                # 26 teszt (modell, kalibráció, becslés, ROI, szimuláció)
```

## Videó nélküli fejlesztés (meccs-szimulátor)

Mivel meccsvideót nem mindig lehet feltölteni/feldolgozni, a `handball.sim`
valósághű szintetikus Tracking-et generál: két 7 fős csapat, 6-0 védekezés, mozgó
labda, passzok. A pásztázó-kamerás változat a látómezőből kieső játékosokat a
VALÓDI becslővel ([F]) becsli — pont úgy, ahogy egy igazi felvételen tenné.

```bash
# Összefoglaló (mért vs. becsült arány, statisztika)
python -m scripts.simulate_match
# Pásztázó-kamerás Tracking JSON fájlba (ezt eszi a Flutter-kliens)
python -m scripts.simulate_match match.json --fov 16
# A teljes "földi igazság" (mind a 14 játékos, kamera-korlát nélkül)
python -m scripts.simulate_match truth.json --ground-truth
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

# Tesztek (pytest nélkül is futnak, bárhonnan indítva)
python tests/test_tracking_model.py
# vagy ha van pytest:  python -m pytest
```

## API-szerver indítása (FastAPI kell hozzá)

```bash
pip install -e .          # fastapi + uvicorn
uvicorn "handball.api.app:create_app" --factory --reload
# GET /health
# GET /matches/{id}                 -> Tracking JSON (a kliens ezt rajzolja)
# GET /matches/{id}/stats           -> játékosonkénti táv/sebesség
# GET /matches/{id}/heatmap?team=home  -> csapat-hőtérkép (rács)
# GET /matches/{id}/team-stats      -> súlypont + kiterjedés csapatonként
# GET /matches/{id}/tactics         -> stílusprofil (fázis, forma, tempó)
# GET /matches/{id}/setplays        -> visszatérő figurák száma + gyakorisága
```

A valódi videó-feldolgozáshoz az ML-extra: `pip install -e ".[ml]"`
(ultralytics, opencv, numpy).
