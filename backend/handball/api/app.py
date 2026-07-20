"""
HTTP API — a Flutter-kliens ezen keresztül kapja a Tracking-et és a statisztikát.

A backend és a (Flutter) kliens KÜLÖN válik: a nehéz feldolgozás itt, szerveren
fut, a kliens csak a kész JSON-t kéri le és jeleníti meg (lásd docs/ARCHITECTURE.md
"Kliens–szerver szétválasztás").

Ez a modul a FastAPI-t LUSTÁN használja: az importja egy függvényben van, hogy a
csomag a FastAPI telepítése nélkül is importálható és tesztelhető legyen. A
szervert a `create_app()`-ből indítjuk (lásd scripts/serve.py vagy uvicorn).

Végpontok (MVP):
- GET  /health                     → életjel.
- POST /matches/process            → videó-feldolgozás indítása (háttérszál) → job_id.
- GET  /jobs/{job_id}              → a feldolgozás állapota (stage/progress/message).
- GET  /matches                     → a tárolt meccsek listája (könyvtár nézet).
- GET  /matches/{match_id}          → a Match (Tracking) JSON-ja.
- PATCH /matches/{match_id}         → metaadat-frissítés (csapatnevek átírása).
- DELETE /matches/{match_id}        → meccs törlése (memória + lemez).
- GET  /matches/{match_id}/quality  → a feldolgozás minőség-önellenőrzése.
- GET  /matches/{match_id}/stats    → játékosonkénti statisztika.
- GET  /matches/{match_id}/coaching → élő edzői javaslatok (idővonal vagy egy frame).
- GET  /matches/{match_id}/scouting → ellenfél-felderítő jelentés egy csapatról.
- GET  /matches/{match_id}/scouting/export → nyomtatható HTML-jelentés.
- POST /scouting                     → több meccsből egyesített felderítés.
- POST /scouting/trend               → fejlődés-követés (két időszak összevetése).
- GET/POST/DELETE /playbook          → figura-könyvtár (mentett figurák).
- POST /matches/demo                 → demó meccs videó nélkül (első kipróbálás).

Az adattárolás itt egyelőre memóriában/placeholder; később Postgres + objektumtár.
"""

from __future__ import annotations

from ..models.tracking import Match, MatchMeta, Team
from ..storage import data_root
from ..pipeline.pipeline import summarize
from ..pipeline.analytics import compute_team_heatmap, compute_team_summary
from ..pipeline.tactics import team_style_profile, TacticsConfig
from ..pipeline.coaching import suggest_for_frame, coaching_timeline
from ..pipeline.scouting import (
    scout_team, combine_reports, report_to_dict, trend_report,
)
from ..pipeline.report_html import scouting_report_html
from ..pipeline.setplays import discover_setplays
from ..pipeline.decisions import analyze_player_decisions
from ..pipeline.event_detection import detect_events, event_counts
from ..pipeline.play_simulation import DefenseModel, SetPlay, simulate_setplay, evaluate_setplay


def create_app():
    """Létrehozza és visszaadja a FastAPI alkalmazást.

    A FastAPI importja szándékosan ITT van (nem a modul tetején), hogy a csomag
    többi része függőség nélkül is működjön. A szerver indításához:
        uvicorn "handball.api.app:create_app" --factory
    """
    import json
    from pathlib import Path

    from fastapi import FastAPI, HTTPException, Request

    app = FastAPI(title="Handball Analysis API", version="0.1.0")

    # Meccs-tár: memóriában (match_id -> Match), lemezre TÜKRÖZVE, hogy a szerver
    # újraindítása ne veszítse el a feldolgozott meccseket (data/matches/{id}.json).
    # Ez az MVP-perzisztencia; később adatbázis + objektumtár.
    _store: dict[str, Match] = {}
    # Írható adat-gyökér: telepítve felhasználói mappa, fejlesztésben a backend/
    # (lásd handball/storage.py) — a telepített app a saját mappájába nem írhat.
    _data_dir = data_root() / "data" / "matches"
    _data_dir.mkdir(parents=True, exist_ok=True)

    def _match_path(match_id: str) -> Path:
        # Fájlnév-fertőtlenítés (path traversal ellen): csak biztonságos karakterek.
        import re
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", match_id) or "match"
        return _data_dir / f"{safe}.json"

    def _params_path(match_id: str) -> Path:
        import re
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", match_id) or "match"
        return _data_dir / f"{safe}.params.json"

    def _load_store_from_disk() -> int:
        """A lemezen lévő meccsek betöltése a memóriába (indulás + könyvtár-
        visszaállítás után). A jegyzet/mezszám/roster kísérőfájlokat a nevük
        különbözteti meg (*.notes.json stb.) — azok nem meccsek."""
        loaded = 0
        for f in sorted(_data_dir.glob("*.json")):
            if any(f.name.endswith(s) for s in
                   (".notes.json", ".jerseys.json", ".roster.json",
                    ".params.json")):
                continue
            try:
                m = Match.from_json(f.read_text(encoding="utf-8"))
                _store[m.meta.match_id] = m
                loaded += 1
            except Exception:
                pass  # sérült fájlt átugrunk, ne akadályozza az indulást
        return loaded

    # Indításkor betöltjük a korábban lementett meccseket a memóriába.
    _load_store_from_disk()

    @app.get("/health")
    def health():
        """Életjel — a kliens ezzel ellenőrzi, hogy a backend elérhető."""
        return {"status": "ok"}

    @app.get("/health/full")
    def health_full():
        """Teljes rendszer-ellenőrzés — a pilot-telepítések gyors
        diagnosztikája egyetlen hívásban.

        Minden ellenőrzés {"name", "ok", "detail"} — a kliens listaként
        mutatja. A súlyfájl-ellenőrzés NEM tölt le semmit, csak a helyi
        jelölteket nézi (első futásnál a letöltés a feldolgozáskor
        történik)."""
        import os
        import shutil

        checks: list[dict] = []

        def add(name, ok, detail):
            checks.append({"name": name, "ok": bool(ok),
                           "detail": str(detail)})

        # 1) Python-környezet: a kulcs-csomagok betölthetők-e.
        for mod, label in (("cv2", "OpenCV (videó-kezelés)"),
                           ("numpy", "NumPy (számítás)"),
                           ("ultralytics", "Ultralytics YOLO (detektor)")):
            try:
                m = __import__(mod)
                add(label, True, getattr(m, "__version__", "elérhető"))
            except Exception as e:
                add(label, False, f"nem tölthető be: {e}")

        # 2) Inferencia-eszköz (CUDA / Apple GPU / CPU).
        try:
            import sys as _sys
            from pathlib import Path as _P
            backend_dir = str(_P(__file__).resolve().parents[2])
            if backend_dir not in _sys.path:
                _sys.path.insert(0, backend_dir)
            from scripts.process_video import _pick_device, _weights_ok
            add("Inferencia-eszköz", True, _pick_device())
            # 3) Modell-súly: van-e ÉP helyi példány (letöltés nélkül).
            candidates = []
            env_dir = os.environ.get("HANDBALL_WEIGHTS_DIR")
            if env_dir:
                candidates.append(_P(env_dir) / "yolov8n.pt")
            candidates.append(data_root() / "weights" / "yolov8n.pt")
            found = next((c for c in candidates
                          if c.exists() and _weights_ok(str(c))), None)
            add("Modell-súlyfájl (yolov8n)", found is not None,
                str(found) if found else
                "nincs helyi példány — az első feldolgozáskor letöltődik")
        except Exception as e:
            add("Inferencia-eszköz", False, str(e))

        # 4) Adatmappa írható-e (könyvtár, jegyzetek, napló ide kerül).
        try:
            probe = data_root() / "data" / ".health_probe"
            probe.parent.mkdir(parents=True, exist_ok=True)
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            add("Adatmappa írható", True, str(data_root()))
        except Exception as e:
            add("Adatmappa írható", False, f"{data_root()} — {e}")

        # 5) Szabad tárhely az adatmappán (a klip/csomag-exporthoz kell).
        try:
            free_gb = shutil.disk_usage(str(data_root())).free / 1e9
            add("Szabad tárhely", free_gb >= 2.0, f"{free_gb:.1f} GB")
        except Exception as e:
            add("Szabad tárhely", False, str(e))

        # 6) Videó-írás (mp4v kodek) — a klipvágás ezen múlik.
        try:
            import tempfile

            import cv2
            import numpy as np
            with tempfile.TemporaryDirectory() as td:
                out = str(Path(td) / "probe.mp4")
                vw = cv2.VideoWriter(out,
                                     cv2.VideoWriter_fourcc(*"mp4v"),
                                     25.0, (64, 48))
                vw.write(np.zeros((48, 64, 3), np.uint8))
                vw.release()
                ok_write = Path(out).exists() and Path(out).stat().st_size > 0
            add("Videó-írás (mp4v)", ok_write,
                "működik" if ok_write else "a klipvágás nem fog menni")
        except Exception as e:
            add("Videó-írás (mp4v)", False, str(e))

        # 7) Könyvtár-állapot.
        add("Meccskönyvtár", True, f"{len(_store)} meccs betöltve")

        return {"ok": all(c["ok"] for c in checks), "checks": checks}

    async def upload_video(request, filename: str = "match.mp4"):
        """Meccsvideó feltöltése (nyers bájt-folyam a törzsben, `filename` query).

        Szándékosan NEM multipart (nem kell a python-multipart függőség): a törzset
        DARABONKÉNT (stream) írjuk lemezre, így egy több GB-os videó sem tölti be
        egészében a memóriába. A mentett fájl backend-oldali útját adjuk vissza,
        amit aztán a /matches/process és a /reference-frame használ.
        """
        import re
        from pathlib import Path
        uploads = data_root() / "uploads"
        uploads.mkdir(parents=True, exist_ok=True)
        # A fájlnevet fertőtlenítjük (path traversal ellen): csak biztonságos karakterek.
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", filename).lstrip(".") or "match.mp4"
        dest = uploads / safe
        size = 0
        with open(dest, "wb") as f:
            async for chunk in request.stream():
                f.write(chunk)
                size += len(chunk)
        return {"path": str(dest), "filename": safe, "size": size}

    # A `request` paraméter típusát KÉZZEL állítjuk be (a modul `from __future__
    # import annotations` miatt a sztring-annotáció nem oldódna fel), majd
    # regisztráljuk az útvonalat — így a FastAPI a nyers Request-et injektálja.
    upload_video.__annotations__["request"] = Request
    app.post("/upload")(upload_video)

    @app.get("/reference-frame")
    def reference_frame(path: str, t: int = 100):
        """Egy képkockát ad vissza (PNG) a megadott videóból — a kalibráló
        képernyő ezt tölti be, hogy a felhasználó a valódi képre húzza a sarkokat."""
        import cv2
        from fastapi import Response
        cap = cv2.VideoCapture(path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, t)
        ok, frame = cap.read()
        cap.release()
        if not ok:
            raise HTTPException(status_code=404, detail="frame not read")
        ok, buf = cv2.imencode(".png", frame)
        return Response(content=buf.tobytes(), media_type="image/png")

    @app.get("/broadcast/segments")
    def broadcast_segments(path: str, stride: int = 5, max: int = 0):
        """TV-KÖZVETÍTÉS elő-elemzése: vágások + totál/közeli szakaszok.

        A közvetítés (a saját pásztázó kamerával szemben) vágott: totál →
        közeli → visszajátszás. Ez a végpont a felvételt szakaszokra bontja
        és megjelöli a HASZNÁLHATÓ (elég hosszú totálkép) szakaszokat — csak
        ezekből érdemes követést/kalibrációt futtatni, és így a visszajátszás
        nem számolja duplán a gólt. A tévés-út első lépcsője.

        404: a videó nem olvasható."""
        import os
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="video not found")
        from ..pipeline.broadcast import analyze_broadcast
        try:
            return analyze_broadcast(path, stride=int(stride),
                                     max_frames=int(max))
        except Exception as e:
            raise HTTPException(status_code=500,
                                detail=f"a közvetítés-elemzés nem sikerült: {e}")

    @app.get("/broadcast/lines")
    def broadcast_lines(path: str, frame: int = 0):
        """Pályavonal-jelöltek egy közvetítés-képkockából.

        A vonal-alapú auto-kalibráció első fele: a megadott képkockán
        felismert hosszú, egyenes vonalak (végpontokkal) és a nem-
        párhuzamos párjaik képen belüli metszéspontjai (sarok-jelöltek).
        A kliens ezt rárajzolhatja a képre — így ellenőrizhető, mit lát
        a rendszer, mielőtt a pálya-modell megfeleltetés elkészül.

        404: a videó nem olvasható / nincs ilyen képkocka."""
        import os
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="video not found")
        try:
            import cv2
            cap = cv2.VideoCapture(path)
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(frame))
            ok, img = cap.read()
            cap.release()
            if not ok or img is None:
                raise HTTPException(status_code=404,
                                    detail="frame not readable")
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            from ..pipeline.broadcast_lines import (
                detect_court_lines, line_intersections,
                suggest_calibration_quad)
            lines = detect_court_lines(gray)
            h, w = gray.shape[:2]
            corners = line_intersections(lines, w, h)
            return {"frame": int(frame), "width": w, "height": h,
                    "lines": lines, "corners": corners,
                    "suggested_quad": suggest_calibration_quad(corners,
                                                               w, h)}
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500,
                                detail=f"a vonal-felismerés nem sikerült: {e}")

    @app.get("/detect-preview")
    def detect_preview(path: str, t: int = 100, imgsz: int = 1280,
                       calib: str | None = None, region: str = "full",
                       rotate: bool = False):
        """Egy-képkockás detektálási PRÓBA a hosszú feldolgozás előtt.

        Lefuttatja a YOLO-t a kért kockán, berajzolja a talált játékosokat
        (a két mezszín-klaszter szerint színezve), a bírót és a labdát —
        az edző az indítás ELŐTT látja, jól látja-e a rendszer a pályát.

        KALIBRÁCIÓVAL (calib: 4 sarok JSON-ban + region/rotate) a képre
        rávetítjük a kalibrált pálya-modellt (arany vonalak: keret, felező,
        kapuk, 6 m-es ívek) — ha nem illeszkednek a valódi vonalakra, a
        kalibráció rossz. Emellett megszámoljuk, hány talált játékos esik
        a játéktérre méterben ("on_court") — az indítás előtti utolsó
        ellenőrzés.

        Visszatérés: {"persons", "balls", "referees", "on_court" (kalibrá-
        cióval, különben None), "image_b64" (JPEG)}.
        404: a videó/kocka nem olvasható; 503: a detektor nem elérhető.
        """
        import base64
        import os

        import cv2
        import numpy as np

        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="video not found")
        cap = cv2.VideoCapture(path)
        cap.set(cv2.CAP_PROP_POS_FRAMES, t)
        ok, frame = cap.read()
        cap.release()
        if not ok:
            raise HTTPException(status_code=404, detail="frame not read")

        # A nehéz feldolgozó segédei (súly-feloldás, osztályok, mezszín).
        import sys
        from pathlib import Path
        backend_dir = str(Path(__file__).resolve().parents[2])
        if backend_dir not in sys.path:
            sys.path.insert(0, backend_dir)
        try:
            from ultralytics import YOLO
            from scripts.process_video import (
                _class_ids, _is_referee, _pick_device, _resolve_weights,
                _torso_color,
            )
            model = YOLO(_resolve_weights("yolov8n.pt"))
        except Exception as e:
            raise HTTPException(
                status_code=503,
                detail=f"a detektor nem érhető el: {e}")

        person_ids, ball_ids = _class_ids(getattr(model, "names", None))
        res = model.predict(frame, imgsz=imgsz, conf=0.2, verbose=False,
                            device=_pick_device())[0]

        persons = []   # (x1, y1, x2, y2, mezszín)
        referees = 0
        balls = []
        for b in res.boxes:
            cls = int(b.cls[0])
            x1, y1, x2, y2 = (int(v) for v in b.xyxy[0])
            if cls in person_ids:
                if _is_referee(frame, x1, y1, x2, y2):
                    referees += 1
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
                    cv2.putText(frame, "biro", (x1, max(0, y1 - 6)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
                else:
                    persons.append((x1, y1, x2, y2,
                                    _torso_color(frame, x1, y1, x2, y2)))
            elif cls in ball_ids:
                balls.append((x1, y1, x2, y2))

        # Két mezszín-klaszter (mint a feldolgozásban) — a doboz színe
        # mutatja, melyik csapathoz sorolná a rendszer a játékost.
        team_of_idx = [0] * len(persons)
        if len(persons) >= 4:
            data = np.array([c for (_, _, _, _, c) in persons], np.float32)
            crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 0.5)
            _, labels, _ = cv2.kmeans(data, 2, None, crit, 5,
                                      cv2.KMEANS_PP_CENTERS)
            team_of_idx = [int(l) for l in labels.ravel()]
        draw_colors = [(196, 217, 47), (107, 107, 255)]  # BGR: accent / away
        for (x1, y1, x2, y2, _c), ti in zip(persons, team_of_idx):
            cv2.rectangle(frame, (x1, y1), (x2, y2), draw_colors[ti], 2)
        for (x1, y1, x2, y2) in balls:
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            cv2.circle(frame, (cx, cy), max(8, x2 - x1), (107, 179, 216), 3)
            cv2.putText(frame, "labda", (x1, max(0, y1 - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (107, 179, 216), 2)

        # Kalibráció-ellenőrzés: a pálya-modell rávetítése + méter-számolás
        # (a geometria a pipeline.preview modulban — ott tesztelt).
        on_court = None
        if calib:
            try:
                from ..pipeline.preview import draw_calibration_overlay
                on_court = draw_calibration_overlay(
                    frame, persons, json.loads(calib), region=region,
                    rotate=bool(rotate))
            except Exception:
                on_court = None  # rossz calib-paraméter: a próba enélkül él

        ok, buf = cv2.imencode(".jpg", frame,
                               [int(cv2.IMWRITE_JPEG_QUALITY), 82])
        return {
            "persons": len(persons),
            "referees": referees,
            "balls": len(balls),
            "on_court": on_court,
            "image_b64": base64.b64encode(buf.tobytes()).decode("ascii"),
        }

    # Feldolgozási munkák (job) állapota — a kliens ezt kérdezi le a haladáshoz.
    # Memóriabeli, mint a _store; a szerver újraindításáig él.
    _jobs: dict[str, dict] = {}

    @app.post("/matches/process")
    def start_processing(body: dict):
        """Elindítja egy videó feldolgozását HÁTTÉRSZÁLON, és job_id-t ad vissza.

        A törzs (JSON) mezői: path (kötelező, backend-oldali videó út), opcionálisan
        weights, stride, max (0 = a TELJES videó — ez az alapérték), imgsz, conf,
        start, calib ([[x,y],...] 4 sarok), match_id.
        A haladást a GET /jobs/{job_id} adja vissza (stage, progress, message);
        megszakítás: POST /jobs/{job_id}/cancel.
        """
        import time
        import uuid

        path = body.get("path")
        if not path:
            raise HTTPException(status_code=400, detail="path required")
        if not Path(path).exists():
            raise HTTPException(status_code=400,
                                detail=f"a videó nem található: {path}")

        # Kalibráció-épség: elfajzott (apró/önmetsző) négyszöggel a teljes
        # feldolgozás rossz koordinátákat adna — inkább itt utasítjuk el.
        def _calib_error(corners) -> str | None:
            try:
                pts = [(float(p_[0]), float(p_[1])) for p_ in corners]
            except Exception:
                return "a kalibráció formátuma hibás (4 [x,y] pont kell)"
            if len(pts) != 4:
                return "a kalibrációhoz pontosan 4 sarok kell"
            # Előbb a keresztezés (az önmetsző négyszög saru-területe
            # félrevezetően kicsi lenne), utána a terület-nagyságrend.
            pos = neg = False
            for i in range(4):
                a, b, c = pts[i], pts[(i + 1) % 4], pts[(i + 2) % 4]
                cr = ((b[0] - a[0]) * (c[1] - b[1])
                      - (b[1] - a[1]) * (c[0] - b[0]))
                pos |= cr > 0
                neg |= cr < 0
            if pos and neg:
                return ("a kalibrációs sarkok sorrendje hibás (a vonalak "
                        "keresztezik egymást) — a helyes sorrend: bal-fent, "
                        "jobb-fent, jobb-lent, bal-lent")
            area2 = sum(pts[i][0] * pts[(i + 1) % 4][1]
                        - pts[(i + 1) % 4][0] * pts[i][1] for i in range(4))
            if abs(area2) < 1000.0:  # px² nagyságrend: ~22x22 px alatti terület
                return ("a bejelölt kalibrációs terület elfajzott/túl kicsi "
                        "— jelöld újra a 4 sarkot")
            return None

        for c in ([body.get("calib")] if body.get("calib") else []) +                 [cc.get("corners") for cc in (body.get("calibs") or [])
                 if isinstance(cc, dict)]:
            err = _calib_error(c)
            if err:
                raise HTTPException(status_code=400, detail=err)

        job_id = uuid.uuid4().hex[:12]
        match_id = body.get("match_id") or f"video-{job_id}"
        # A feldolgozási beállítások lemezre mentése: részleges eredménynél
        # (megszakítás/összeomlás) ebből tud a Folytatás ugyanígy elindulni.
        try:
            _params_path(match_id).write_text(
                json.dumps(body, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        job = {"job_id": job_id, "match_id": match_id, "status": "queued",
               "stage": "A", "progress": 0.0, "message": "sorban áll",
               "error": None, "created": time.time(),
               "video": Path(path).name}
        _jobs[job_id] = job
        _job_params[job_id] = body
        _job_queue.put(job_id)
        _ensure_worker()
        return {"job_id": job_id, "match_id": match_id}

    # A feldolgozási SOR: a munkák egyesével futnak (egy nehéz ML-feldolgozás
    # használja ki jól a gépet; kettő párhuzamosan csak lassítaná egymást).
    # A felhasználó több videót is sorba állíthat (pl. két félidő), és a
    # kezdőképernyő mutatja a sor állapotát (GET /jobs).
    import queue as _queue_mod
    import threading as _threading
    _job_queue: "_queue_mod.Queue[str]" = _queue_mod.Queue()
    _job_params: dict[str, dict] = {}
    _worker_flag = {"started": False}

    def _ensure_worker():
        if _worker_flag["started"]:
            return
        _worker_flag["started"] = True
        _threading.Thread(target=_job_worker, daemon=True).start()

    def _job_worker():
        while True:
            job_id = _job_queue.get()
            job = _jobs.get(job_id)
            if job is None or job["status"] != "queued":
                continue  # időközben megszakították
            job["status"] = "running"
            job["message"] = "indítás"
            _run_job(job, _job_params.pop(job_id, {}))

    def _run_job(job, body):
        match_id = job["match_id"]
        path = body.get("path")
        if True:  # (behúzás-megőrző blokk a korábbi törzsnek)
            # A nehéz feldolgozó a scripts.process_video-ban van; a backend/ mappát
            # biztosítjuk a sys.path-en, hogy a szerver bárhonnan indítva megtalálja.
            import sys
            from pathlib import Path
            backend_dir = str(Path(__file__).resolve().parents[2])
            if backend_dir not in sys.path:
                sys.path.insert(0, backend_dir)
            from scripts.process_video import process

            # Megszakítás: SZELÍD leállítás. A detektáló ciklus a stop_check
            # jelzésére megáll, de az addig feldolgozott kockákra az utómunka
            # lefut, és a részleges eredmény ELMENTŐDIK — órákig tartó
            # feldolgozásnál a Megszakítás nem dobja el az elvégzett munkát.
            def cb(stage, prog, msg):
                job["stage"] = stage
                job["progress"] = round(float(prog), 3)
                # Leállítás-kérés közben jelezzük, hogy a befejezés fut.
                if job.get("cancel"):
                    msg = f"leállítás — az eddigi rész mentése… ({msg})"
                job["message"] = msg

            try:
                match = process(
                    path, None,
                    weights=body.get("weights"),
                    stride=int(body.get("stride", 3)),
                    max_frames=int(body.get("max", 0)),  # 0 = teljes videó
                    imgsz=int(body.get("imgsz", 1280)),
                    conf=float(body.get("conf", 0.20)),
                    calib_corners=body.get("calib"),
                    # Térfél-kalibráció + forgatás (ha az induló képen csak
                    # az egyik térfél látszik): "full" | "left" | "right".
                    calib_region=body.get("calib_region", "full"),
                    calib_rotate=bool(body.get("calib_rotate", False)),
                    # TÖBB kalibráció (pl. külön bal és jobb térfél, akár
                    # külön képkockán): [{corners, region, rotate, frame}].
                    calibs=body.get("calibs"),
                    start=int(body.get("start", 0)),
                    progress_cb=cb, match_id=match_id,
                    estimate=bool(body.get("estimate", True)),
                    ball_smooth=bool(body.get("ball_smooth", True)),
                    track_smooth=bool(body.get("track_smooth", True)),
                    home_team=body.get("home_team") or "Csapat A",
                    away_team=body.get("away_team") or "Csapat B",
                    # KÍSÉRLETI: mezszám-OCR a feldolgozás alatt.
                    jersey_ocr=bool(body.get("jersey_ocr", False)),
                    # Szelíd megszakítás: a Megszakítás gombra a detektálás
                    # megáll, az eddigi rész feldolgozva elmentődik.
                    stop_check=lambda: bool(job.get("cancel")),
                    # Időszakos checkpoint: hosszú feldolgozásnál pár percenként
                    # elmentjük a részeredményt, így áramszünet/összeomlás után
                    # sem vész el minden — a könyvtárban ott a legutóbbi állapot.
                    checkpoint_save=lambda m: app.state.put_match(m),
                )
                cancelled = bool(job.pop("cancel", False))
                if cancelled and not match.frames:
                    # Annyira korán állították le, hogy nincs mit menteni.
                    job["status"] = "cancelled"
                    job["message"] = "megszakítva (nem készült feldolgozott kocka)"
                else:
                    app.state.put_match(match)
                    job["status"] = "done"
                    job["progress"] = 1.0
                    job["message"] = (
                        f"megszakítva — az addig feldolgozott rész elmentve "
                        f"({len(match.frames)} kocka)" if cancelled
                        else f"kész ({len(match.frames)} frame)")
            except Exception as e:  # a hibát a kliensnek is megmutatjuk
                msg = str(e)
                # A nyers zlib-hiba ("Error -3 ... incorrect header check")
                # önmagában semmitmondó — lefordítjuk cselekvésre: sérült
                # tömörített fájl (modell-súly vagy programfájl) a tünet.
                if "incorrect header check" in msg or "decompressing" in msg:
                    msg += (" — Egy tömörített fájl sérült (modell-súlyfájl "
                            "vagy program-összetevő). Próbáld újra a "
                            "feldolgozást (a modellt újratöltjük); ha "
                            "marad, telepítsd újra a programot a legfrissebb "
                            "telepítővel.")
                job["status"] = "error"
                job["error"] = msg
                job["message"] = f"hiba: {msg}"
            _log_job(job)

    # Feldolgozás-napló: a LEZÁRT job-ok (kész/hiba/megszakítva) egy sora
    # a lemezre kerül — újraindítás után is visszanézhető, mi történt.
    _jobs_log_path = data_root() / "data" / "jobs_log.jsonl"

    def _log_job(job):
        try:
            import time as _t
            rec = {k: job.get(k) for k in
                   ("job_id", "match_id", "status", "message", "error",
                    "created", "video", "stage")}
            rec["finished"] = _t.time()
            _jobs_log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(_jobs_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass  # a naplózás hibája nem érinti a feldolgozást

    @app.get("/jobs/history")
    def job_history(limit: int = 20):
        """A lezárt feldolgozások naplója (legutóbbi elöl) — újraindítás
        után is megvan; hibakereséshez és "mi futott le" áttekintéshez."""
        rows = []
        try:
            with open(_jobs_log_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
        except FileNotFoundError:
            pass
        rows.reverse()
        return {"jobs": rows[:max(1, min(int(limit), 100))]}

    @app.get("/jobs")
    def list_jobs():
        """A feldolgozási munkák listája (legújabb elöl) — a kezdőképernyő
        "folyamatban" kártyája ebből épül. A belső mezőket nem adjuk ki."""
        jobs = sorted(_jobs.values(), key=lambda j: j.get("created", 0), reverse=True)
        return {"jobs": [
            {k: v for k, v in j.items() if k != "cancel"} for j in jobs[:20]
        ]}

    @app.get("/jobs/{job_id}")
    def job_status(job_id: str):
        """Egy feldolgozási munka állapota (stage/progress/message/status/error)."""
        job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        return job

    @app.post("/jobs/{job_id}/cancel")
    def cancel_job(job_id: str):
        """Egy futó feldolgozás megszakítása. A leállítás SZELÍD: a
        detektálás a következő képkockánál megáll, és az addig feldolgozott
        rész teljes utómunkával elmentődik (a job "done"-nal zárul)."""
        job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        if job["status"] == "queued":
            # Sorban álló munka: azonnal megszakítható (el sem indult).
            job["status"] = "cancelled"
            job["message"] = "megszakítva (a sorból)"
        elif job["status"] == "running":
            job["cancel"] = True
            job["message"] = "leállítás — az eddigi rész mentése…"
        return job

    @app.get("/matches")
    def list_matches():
        """A tárolt meccsek listája (a kliens áttekintő/könyvtár nézetéhez).

        Csak összefoglaló adatok (nem a teljes Tracking): azonosító, csapatnevek,
        képkocka-szám, fps és becsült hossz. Idő szerint (fps-alapú hossz) rendezve.
        """
        out = []
        for m in _store.values():
            fps = m.meta.fps if m.meta.fps > 0 else 25.0
            out.append({
                "match_id": m.meta.match_id,
                "home_team": m.meta.home_team,
                "away_team": m.meta.away_team,
                "num_frames": len(m.frames),
                "fps": m.meta.fps,
                "duration_s": len(m.frames) / fps,
                # Részleges feldolgozás (megszakítva/összeomlás után mentve).
                "partial": bool(m.meta.partial),
            })
        out.sort(key=lambda d: d["match_id"])
        return {"matches": out}

    @app.get("/matches/{match_id}")
    def get_match(match_id: str):
        """Visszaadja a kért meccs Tracking JSON-ját (ezt rajzolja ki a kliens)."""
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        return match.to_dict()

    @app.patch("/matches/{match_id}")
    def update_match(match_id: str, body: dict):
        """A meccs metaadatainak frissítése (csapatnevek, dátum).

        Törzs: {"home_team": "...", "away_team": "...", "date": "ÉÉÉÉ-HH-NN"}
        — bármelyik elhagyható; üres date törli a dátumot. A módosítás a
        lemezre is kiíródik, így újraindítás után is megmarad."""
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        home = body.get("home_team")
        away = body.get("away_team")
        date = body.get("date")
        if home is None and away is None and date is None:
            raise HTTPException(status_code=400,
                                detail="home_team, away_team or date required")
        if home is not None:
            match.meta.home_team = str(home).strip() or match.meta.home_team
        if away is not None:
            match.meta.away_team = str(away).strip() or match.meta.away_team
        if date is not None:
            d = str(date).strip()
            if d:
                import datetime
                try:
                    datetime.date.fromisoformat(d)
                except ValueError:
                    raise HTTPException(status_code=400,
                                        detail="date must be YYYY-MM-DD")
                match.meta.date = d
            else:
                match.meta.date = None  # üres = a dátum törlése
        _put_match(match)  # memóriába + lemezre (perzisztencia)
        return {"match_id": match_id,
                "home_team": match.meta.home_team,
                "away_team": match.meta.away_team,
                "date": match.meta.date}

    @app.post("/matches/{match_id}/swap-teams")
    def swap_teams(match_id: str):
        """Felcseréli a két csapatot (minden játékos team-mezőjét) — ha a
        csapatszín-klaszterezés fordítva találta el, melyik szín a hazai.
        A csapatnevek maradnak; a statisztika/felderítés a friss adatból számol."""
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        match.swap_teams()
        _put_match(match)  # memóriába + lemezre (perzisztencia)
        return {"match_id": match_id, "swapped": True}

    @app.post("/matches/merge")
    def merge_halves(body: dict):
        """Több feldolgozott felvétel (pl. 1. és 2. félidő) összefűzése EGY meccsé.

        Törzs: {"ids": [elso, masodik, ...]  — időrendben!,
                "match_id": opcionális név, "home_team"/"away_team": opcionális}.
        Az eredmény új meccsként kerül a könyvtárba; az eredeti részek megmaradnak.
        """
        import uuid

        from ..pipeline.merge import merge_matches

        ids = body.get("ids") or []
        if not isinstance(ids, list) or len(ids) < 2:
            raise HTTPException(status_code=400, detail="legalabb ket meccs-azonosito kell")
        parts = []
        for mid in ids:
            m = _store.get(str(mid))
            if m is None:
                raise HTTPException(status_code=404, detail=f"match not found: {mid}")
            parts.append(m)
        new_id = str(body.get("match_id") or "").strip() or (
            "teljes-" + "+".join(str(i) for i in ids))
        if new_id in _store:
            new_id = f"{new_id}-{uuid.uuid4().hex[:6]}"
        merged = merge_matches(
            parts, new_id,
            home_team=body.get("home_team"), away_team=body.get("away_team"))
        _put_match(merged)  # memóriába + lemezre (perzisztencia)
        return {"match_id": new_id, "num_frames": len(merged.frames),
                "parts": [p.meta.match_id for p in parts]}

    def _calibration_path(video_path: str) -> Path:
        """A videóhoz tartozó kalibráció-fájl (kulcs: a videó fájlneve)."""
        import re
        base = re.sub(r"[^A-Za-z0-9._-]", "_", Path(video_path).name) or "video"
        d = data_root() / "data" / "calibrations"
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{base}.json"

    @app.get("/calibration")
    def get_calibration(path: str):
        """A videóhoz ELMENTETT kalibrációk — újrafeldolgozásnál (vagy az app
        újraindítása után) nem kell újra bejelölni a sarkokat.
        Válasz: {"calibs": [{corners, region, rotate, frame}, ...]} (lehet üres)."""
        f = _calibration_path(path)
        if f.exists():
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                if isinstance(d.get("calibs"), list):
                    return {"calibs": d["calibs"]}
            except Exception:
                pass
        return {"calibs": []}

    @app.post("/calibration")
    def save_calibration(body: dict):
        """Kalibrációk mentése a videóhoz. Törzs: {"path": ..., "calibs": [...]}."""
        path = body.get("path")
        if not path:
            raise HTTPException(status_code=400, detail="path required")
        calibs = body.get("calibs") or []
        _calibration_path(path).write_text(
            json.dumps({"calibs": calibs}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        return {"saved": len(calibs)}

    def _roster_path(match_id: str) -> Path:
        import re
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", match_id) or "match"
        return _data_dir / f"{safe}.roster.json"

    @app.get("/matches/{match_id}/roster")
    def get_roster(match_id: str):
        """A meccshez felvitt kiállítások/kapus-állapot (a szerkesztő ezt tölti be)."""
        if match_id not in _store:
            raise HTTPException(status_code=404, detail="match not found")
        p = _roster_path(match_id)
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"suspensions": [], "gk_absent_home": False, "gk_absent_away": False}

    @app.post("/matches/{match_id}/roster")
    def set_roster(match_id: str, body: dict):
        """Kiállítások felvitele → a képen kívüli becslés ÚJRASZÁMÍTÁSA.

        Törzs: {"suspensions": [{"team": "home"|"away", "start_s": mp,
        "duration_s": mp}, ...], "gk_absent_home"?, "gk_absent_away"?}.
        Az időket másodpercben kapjuk (edző-barát), és a meccs fps-ével váltjuk
        képkockára. A mért pozíciók változatlanok; csak a becsültek számolódnak
        újra az új létszám-idővonal szerint. A roster lemezre is mentődik.
        """
        from ..models.events import RosterTimeline, Suspension
        from ..pipeline.estimation import reapply_estimates

        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        fps = match.meta.fps if match.meta.fps > 0 else 25.0

        suspensions = []
        for s in body.get("suspensions", []):
            try:
                team = Team(s["team"])
                start_s = float(s["start_s"])
                duration_s = float(s["duration_s"])
            except (KeyError, TypeError, ValueError):
                raise HTTPException(status_code=400, detail="invalid suspension entry")
            if start_s < 0 or duration_s <= 0:
                raise HTTPException(status_code=400, detail="invalid suspension times")
            suspensions.append(Suspension(
                team=team,
                start_t=round(start_s * fps),
                duration_t=round(duration_s * fps),
            ))

        roster = RosterTimeline(
            suspensions=suspensions,
            gk_absent_home=bool(body.get("gk_absent_home", False)),
            gk_absent_away=bool(body.get("gk_absent_away", False)),
        )
        added = reapply_estimates(match, roster)
        _put_match(match)  # a frissített frame-ek lemezre is
        try:
            _roster_path(match_id).write_text(
                json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
        return {"match_id": match_id, "suspensions": len(suspensions),
                "estimated_added": added}

    @app.delete("/matches/{match_id}")
    def delete_match(match_id: str):
        """Törli a meccset a memóriából és a lemezről (könyvtár-karbantartás)."""
        if match_id not in _store:
            raise HTTPException(status_code=404, detail="match not found")
        del _store[match_id]
        try:
            _match_path(match_id).unlink(missing_ok=True)
            _roster_path(match_id).unlink(missing_ok=True)
            _params_path(match_id).unlink(missing_ok=True)
        except Exception:
            pass
        return {"deleted": match_id}

    @app.post("/matches/{match_id}/reprocess")
    def reprocess_match(match_id: str):
        """ÚJRA-feldolgozás a job indításakor elmentett beállításokkal.

        Hibára futott (vagy gyanús eredményű) feldolgozásnál egy hívással
        újraindítható ugyanaz a munka — a params-sidecar őrzi az eredeti
        beállításokat (kalibráció, stride, modell), a kész eredmény a
        régi meccs HELYÉRE kerül. Ha nincs mentett beállítás vagy a videó
        már nem érhető el, érthető hibát adunk."""
        pp = _params_path(match_id)
        if not pp.exists():
            raise HTTPException(
                status_code=404,
                detail="ehhez a meccshez nincsenek mentett feldolgozási "
                       "beállítások — indítsd a feldolgozást a varázslóból")
        try:
            body = json.loads(pp.read_text(encoding="utf-8"))
        except Exception:
            raise HTTPException(status_code=500,
                                detail="a mentett beállítások nem olvashatók")
        path = body.get("path")
        if not path or not Path(path).exists():
            raise HTTPException(
                status_code=400,
                detail=f"az eredeti videó nem található: {path}")
        body["match_id"] = match_id  # ugyanarra a helyre dolgozunk
        return start_processing(body)

    @app.post("/matches/{match_id}/resume")
    def resume_processing(match_id: str):
        """RÉSZLEGES meccs feldolgozásának folytatása onnan, ahol megszakadt.

        A megszakított/összeomlás után mentett meccs (meta.partial) mellé a
        job indításakor elmentett beállításokkal (params-sidecar) új
        feldolgozás indul a meta.next_start_frame képkockától. KÜLÖN
        meccsként ("<id>-folyt"), mert a track-azonosítók és a csapatszín-
        klaszterezés nem folytonos a megszakításon át — a két részt a
        meglévő POST /matches/merge tudja utólag összefűzni."""
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        if not match.meta.partial:
            raise HTTPException(status_code=400,
                                detail="a meccs nem részleges — nincs mit folytatni")
        video = match.meta.video_path
        if not video or not Path(video).exists():
            raise HTTPException(status_code=400,
                                detail=f"az eredeti videó nem található: {video}")
        body: dict = {}
        pp = _params_path(match_id)
        if pp.exists():
            try:
                body = json.loads(pp.read_text(encoding="utf-8"))
            except Exception:
                body = {}
        body["path"] = video
        body["start"] = int(match.meta.next_start_frame)
        body["stride"] = int(body.get("stride", match.meta.stride))
        body["home_team"] = match.meta.home_team
        body["away_team"] = match.meta.away_team
        # Új, ütközésmentes azonosító: <eredeti>-folyt, -folyt2, ...
        base = f"{match_id}-folyt"
        mid, n = base, 2
        while mid in _store:
            mid, n = f"{base}{n}", n + 1
        body["match_id"] = mid
        return start_processing(body)

    def _notes_path(match_id: str) -> Path:
        import re
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", match_id) or "match"
        return _data_dir / f"{safe}.notes.json"

    def _load_notes(match_id: str) -> list:
        p = _notes_path(match_id)
        if p.exists():
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(d.get("notes"), list):
                    return d["notes"]
            except Exception:
                pass
        return []

    @app.get("/matches/{match_id}/notes")
    def get_notes(match_id: str):
        """Az edzői jegyzetek a meccshez (időbélyeggel) — idő szerint rendezve."""
        if match_id not in _store:
            raise HTTPException(status_code=404, detail="match not found")
        notes = _load_notes(match_id)
        notes.sort(key=lambda n: n.get("frame", 0))
        return {"notes": notes}

    @app.post("/matches/{match_id}/notes")
    def add_note(match_id: str, body: dict):
        """Új edzői jegyzet. Törzs: {"frame": képkocka-index, "text": "..."}.
        A jegyzet lemezre mentődik, és a HTML-jelentésbe is bekerül."""
        import uuid
        if match_id not in _store:
            raise HTTPException(status_code=404, detail="match not found")
        text = str(body.get("text") or "").strip()
        if not text:
            raise HTTPException(status_code=400, detail="text required")
        note = {
            "id": uuid.uuid4().hex[:10],
            "frame": max(0, int(body.get("frame") or 0)),
            "text": text[:500],  # ésszerű hossz-korlát
        }
        notes = _load_notes(match_id)
        notes.append(note)
        _notes_path(match_id).write_text(
            json.dumps({"notes": notes}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        return note

    @app.delete("/matches/{match_id}/notes/{note_id}")
    def delete_note(match_id: str, note_id: str):
        """Egy jegyzet törlése azonosító alapján."""
        if match_id not in _store:
            raise HTTPException(status_code=404, detail="match not found")
        notes = _load_notes(match_id)
        kept = [n for n in notes if n.get("id") != note_id]
        if len(kept) == len(notes):
            raise HTTPException(status_code=404, detail="note not found")
        _notes_path(match_id).write_text(
            json.dumps({"notes": kept}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        return {"deleted": note_id}

    @app.get("/matches/{match_id}/quality")
    def get_quality(match_id: str):
        """A feldolgozás minőség-jelentése: mennyire megbízható az elemzés
        (lefedettség, becsült-arány, labda-hézagok, figyelmeztetések teendővel)."""
        from ..pipeline.quality import (analysis_confidence,
                                        compute_quality_report)
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        res = compute_quality_report(match)
        try:
            res["confidence"] = analysis_confidence(match)
        except Exception:
            pass
        return res

    @app.get("/matches/{match_id}/stats")
    def get_stats(match_id: str):
        """Visszaadja a meccs játékosonkénti statisztikáit (táv, sebesség)."""
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        stats = summarize(match)
        # A dataclass-okat egyszerű szótárrá alakítjuk a JSON-válaszhoz.
        return {str(tid): vars(s) for tid, s in stats.items()}

    def _stats_csv(match) -> str:
        """A játékos-statisztika CSV tartalma (Excel-barát: pontosvessző,
        UTF-8 BOM, tizedesvessző) — a /stats/export és a meccs-csomag közös
        építője. Azonos mezszám = egy játékos (aggregate_by_jersey)."""
        stats = summarize(match)
        # Csapat + mezszám a frame-ekből (első előfordulás alapján).
        team_of: dict = {}
        jersey_of: dict = {}
        for fr in match.frames:
            for p in fr.players:
                team_of.setdefault(p.track_id, p.team.value)
                if p.jersey_number is not None:
                    jersey_of.setdefault(p.track_id, p.jersey_number)

        def num(x):
            return f"{x:.1f}".replace(".", ",")  # tizedesvessző (magyar Excel)

        # Azonos mezszám = egy játékos: a megszakadt követés trackjei a
        # mezszám-hozzárendelés után itt EGY sorrá olvadnak össze.
        from ..pipeline.stats import aggregate_by_jersey
        fps = match.meta.fps if match.meta.fps > 0 else 25.0
        rows = aggregate_by_jersey(stats, team_of, jersey_of, fps=fps)

        # Játék-statisztika oszlopok (gól/lövés/xG/blokk/poszt) — ha a
        # rétegek számolhatók; hibánál üresen maradnak, a CSV nem törik.
        shooter_of: dict = {}
        try:
            from ..pipeline.xg import match_xg
            for rec_sh in match_xg(match).get("shooters", []):
                shooter_of[rec_sh["player_id"]] = rec_sh
        except Exception:
            pass
        blocks_of: dict = {}
        try:
            from ..pipeline.defense import detect_blocks
            blk_csv = detect_blocks(match)
            for side_ in ("home", "away"):
                for e_ in blk_csv[side_].get("events", []):
                    pid_ = e_.get("player_id")
                    if pid_ is not None:
                        blocks_of[pid_] = blocks_of.get(pid_, 0) + 1
        except Exception:
            pass
        poszt_of: dict = {}
        try:
            from ..pipeline.roles import estimate_positions
            est_csv = estimate_positions(match)
            for side_ in ("home", "away"):
                for tid_, r_ in est_csv.get(side_, {}).items():
                    poszt_of[tid_] = r_["poszt"]
        except Exception:
            pass

        lines = ["Játékos;Csapat;Track-ek;Táv (m);Átl. sebesség (m/s);"
                 "Max sebesség (km/h);Sprintek;Sprint táv (m);"
                 "Séta (mp);Kocogás (mp);Futás (mp);Sprint (mp);"
                 "Mért kocka;Becsült kocka;Gól;Lövés;xG;Blokk;Poszt"]
        for g in rows:
            team = (match.meta.home_team if g["team"] == "home"
                    else match.meta.away_team)
            zones = g["zone_seconds"]
            lines.append(";".join([
                g["label"], team,
                "+".join(str(t) for t in g["track_ids"]),
                num(g["distance_m"]), num(g["avg_speed_ms"]),
                num(g["top_speed_ms"] * 3.6), str(g["sprint_count"]),
                num(g["sprint_distance_m"]),
                num(zones.get("seta", 0.0)), num(zones.get("kocogas", 0.0)),
                num(zones.get("futas", 0.0)), num(zones.get("sprint", 0.0)),
                str(g["measured_frames"]), str(g["estimated_frames"]),
                str(sum(shooter_of.get(t, {}).get("goals", 0)
                        for t in g["track_ids"])),
                str(sum(shooter_of.get(t, {}).get("shots", 0)
                        for t in g["track_ids"])),
                num(sum(shooter_of.get(t, {}).get("xg", 0.0)
                        for t in g["track_ids"])),
                str(sum(blocks_of.get(t, 0) for t in g["track_ids"])),
                next((poszt_of[t] for t in g["track_ids"]
                      if t in poszt_of), ""),
            ]))
        return "\ufeff" + "\r\n".join(lines) + "\r\n"  # BOM: Excel

    @app.get("/matches/{match_id}/stats/export")
    def export_stats_csv(match_id: str):
        """Játékos-statisztika CSV-ben, Excel-barát formában — az edző
        táblázatban dolgozhat tovább az adatokkal."""
        from fastapi import Response
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        csv = _stats_csv(match)
        return Response(
            content=csv, media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition":
                     f'attachment; filename="statisztika_{match_id}.csv"'})

    @app.post("/matches/{match_id}/clips/export")
    def start_clip_export(match_id: str, body: dict):
        """Videóklip-export indítása HÁTTÉRSZÁLON: a kiválasztott típusú
        események jelenetei külön MP4-be, majd egy zip-be. A haladás a
        GET /jobs/{job_id} végponton követhető; a kész zip a
        GET /matches/{id}/clips/download címen tölthető le.

        Törzs: {"types": ["goal", "shot", "turnover"]} — üres/hiányzó
        lista esetén csak a gólok."""
        import time
        import uuid
        from ..pipeline.clips import export_event_clips

        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        types = set(body.get("types") or ["goal"])

        job_id = uuid.uuid4().hex[:12]
        job = {"job_id": job_id, "match_id": match_id, "status": "running",
               "stage": "K", "progress": 0.0, "message": "klipvágás indítása",
               "error": None, "created": time.time(),
               "video": Path(match.meta.video_path or "").name}
        _jobs[job_id] = job

        out_dir = _clips_dir(match_id)

        def _work():
            try:
                events = detect_events(match)
                ev = [{"t": e.t, "type": e.type.value, "team": e.team.value}
                      for e in events]
                # Az új elemző rétegek jelenetei is kérhetők klipnek:
                # hétméteres, időkérés (a leálláshoz vezető jelenet) és
                # cserehullám — hibatűrően, rétegenként.
                if "seven_meter" in types:
                    try:
                        from ..pipeline.rules import seven_meter_outcomes
                        ev += [{"t": sm["t"], "type": "seven_meter",
                                "team": sm["team"]}
                               for sm in seven_meter_outcomes(match)]
                    except Exception:
                        pass
                if "timeout" in types:
                    try:
                        from ..pipeline.stoppages import detect_stoppages
                        ev += [{"t": st["start_frame"], "type": "timeout",
                                "team": st["likely_team"] or "home"}
                               for st in detect_stoppages(match)
                               if st["kind"] == "időkérés"]
                    except Exception:
                        pass
                if "substitution" in types:
                    try:
                        from ..pipeline.substitutions import (
                            detect_substitutions)
                        ev += [{"t": sw["t"], "type": "substitution",
                                "team": sw["team"]}
                               for sw in detect_substitutions(match)]
                    except Exception:
                        pass
                if "missed_chance" in types:
                    # Kihagyott ziccer: nagy értékű (xG >= 0,5) helyzet,
                    # ami nem lett gól — a leginkább visszanézendő jelenetek.
                    try:
                        from ..pipeline.xg import missed_big_chances
                        ev += [{"t": mc["t"], "type": "missed_chance",
                                "team": mc["team"]}
                               for mc in missed_big_chances(match)]
                    except Exception:
                        pass
                if "big_save" in types:
                    # Bravúr-védés: ziccert fogott a kapus — a védő
                    # csapathoz írjuk (az ő kapusának jelenete).
                    try:
                        from ..pipeline.xg import big_saves
                        ev += [{"t": bs["t"], "type": "big_save",
                                "team": ("away" if bs["team"] == "home"
                                         else "home")}
                               for bs in big_saves(match)]
                    except Exception:
                        pass
                if "block" in types:
                    # Blokkolt lövések: a fal munkája — a blokkoló
                    # csapathoz írva.
                    try:
                        from ..pipeline.defense import detect_blocks
                        blk = detect_blocks(match)
                        for side in ("home", "away"):
                            ev += [{"t": e_["t"], "type": "block",
                                    "team": side}
                                   for e_ in blk[side].get("events", [])]
                    except Exception:
                        pass
                if "free_shot" in types:
                    # Fedezés-hibák: a szabadon hagyott lövők jelenetei
                    # — a VÉDEKEZŐ oldal tanuló-anyaga.
                    try:
                        from ..pipeline.defense import defense_analysis
                        _da = defense_analysis(match)
                        for side in ("home", "away"):
                            ev += [{"t": sh_["t"], "type": "free_shot",
                                    "team": side,
                                    "label": sh_.get("zone") or ""}
                                   for sh_ in _da[side].get("shots", [])
                                   if sh_.get("free") is True]
                    except Exception:
                        pass
                if "best_figure" in types:
                    # A legjobb (leggólerősebb) figura támadásai
                    # csapatonként — "tanuld meg felismerni" csomag.
                    try:
                        from ..pipeline.setplays import setplay_efficiency
                        eff_bf = setplay_efficiency(match)
                        for side in ("home", "away"):
                            rows_bf = eff_bf.get(side) or []
                            best_bf = max(rows_bf,
                                          key=lambda r: r["goals"],
                                          default=None)
                            if best_bf is None or best_bf["goals"] < 1:
                                continue
                            ev += [{"t": t_bf, "type": "best_figure",
                                    "team": side,
                                    "label": (f"{best_bf['figure'] + 1}. "
                                              "figura")}
                                   for t_bf in best_bf.get("starts", [])]
                    except Exception:
                        pass
                if "key_moment" in types:
                    # A meccs gerince videóban: a key_moments réteg
                    # pillanataiból egy-egy klip, a címkével a
                    # fájlnévben.
                    try:
                        from ..pipeline.momentum import key_moments
                        ev += [{"t": km["t"], "type": "key_moment",
                                "team": "home", "label": km["label"]}
                               for km in key_moments(match)]
                    except Exception:
                        pass
                if "turning_point" in types:
                    # A meccs fordulópontja: a győzelmi esély legnagyobb
                    # billenésének pillanata (ha volt legalább 2 gól).
                    try:
                        from ..pipeline.momentum import win_probability
                        tp = win_probability(match).get("turning_point")
                        if tp is not None:
                            fps_tp = (match.meta.fps
                                      if match.meta.fps > 0 else 25.0)
                            ev.append({
                                "t": round(tp["t_s"] * fps_tp),
                                "type": "turning_point",
                                "team": ("home" if tp["to_p"] > tp["from_p"]
                                         else "away"),
                            })
                    except Exception:
                        pass
                if "empty_net" in types:
                    # 7 a 6 szakaszok: a lehozott kapusos játék jelenetei
                    # — a saját végrehajtás és az ellenfél szokásainak
                    # visszanézéséhez.
                    try:
                        from ..pipeline.goalkeeper import detect_empty_net
                        ev += [{"t": w["start_frame"], "type": "empty_net",
                                "team": w["team"]}
                               for w in detect_empty_net(match)]
                    except Exception:
                        pass
                if "top_shooter" in types:
                    # A fő lövő lövései: csapatonként a legtöbbet lövő
                    # azonosított játékos minden lövése — felderítési
                    # videó-csomag ("készülj a fő lövőre").
                    try:
                        from ..pipeline.xg import match_xg
                        shots = [s_ for s_ in
                                 match_xg(match).get("shots", [])
                                 if s_.get("player_id") is not None]
                        for side in ("home", "away"):
                            per: dict = {}
                            for s_ in shots:
                                if s_["team"] == side:
                                    per[s_["player_id"]] = (
                                        per.get(s_["player_id"], 0) + 1)
                            if not per:
                                continue
                            top = max(per.items(),
                                      key=lambda kv: kv[1])[0]
                            ev += [{"t": s_["t"], "type": "top_shooter",
                                    "team": side}
                                   for s_ in shots
                                   if s_["team"] == side
                                   and s_["player_id"] == top]
                    except Exception:
                        pass
                if "note" in types:
                    # Az edző saját jegyzetei — a megjelölt pillanat
                    # jelenete, a jegyzet szövegével a fájlnévben.
                    try:
                        ev += [{"t": int(n.get("frame", 0)), "type": "note",
                                "team": "home",
                                "label": str(n.get("text", ""))[:40]}
                               for n in _load_notes(match_id)]
                    except Exception:
                        pass

                def cb(done, total, msg):
                    job["progress"] = round(done / max(1, total), 3)
                    job["message"] = msg

                res = export_event_clips(match, ev, types, out_dir,
                                         progress_cb=cb)
                job["status"] = "done"
                job["progress"] = 1.0
                job["message"] = (f"kész: {res.count} klip"
                                  + (f" ({res.skipped} jelenet kimaradt "
                                     "— ismétlés vagy limit)"
                                     if res.skipped else ""))
            except Exception as e:
                job["status"] = "error"
                job["error"] = str(e)
                job["message"] = f"hiba: {e}"
            _log_job(job)

        _threading.Thread(target=_work, daemon=True).start()
        return {"job_id": job_id}

    def _clips_dir(match_id: str) -> Path:
        import re
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", match_id) or "match"
        return data_root() / "clips" / safe

    @app.get("/matches/{match_id}/clips/download")
    def download_clips(match_id: str):
        """A legutóbb exportált klip-csomag (zip) letöltése."""
        from fastapi.responses import FileResponse
        if match_id not in _store:
            raise HTTPException(status_code=404, detail="match not found")
        zip_path = _clips_dir(match_id) / "klipek.zip"
        if not zip_path.exists():
            raise HTTPException(status_code=404,
                                detail="nincs kész klip-csomag ehhez a meccshez")
        return FileResponse(str(zip_path), media_type="application/zip",
                            filename=f"klipek_{match_id}.zip")

    def _jerseys_path(match_id: str) -> Path:
        import re
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", match_id) or "match"
        return _data_dir / f"{safe}.jerseys.json"

    def _apply_jerseys(match, mapping: dict) -> None:
        """A track_id → mezszám hozzárendelés ráírása a meccs kockáira."""
        for fr in match.frames:
            for p in fr.players:
                key = str(p.track_id)
                if key in mapping:
                    p.jersey_number = mapping[key]

    @app.get("/matches/{match_id}/jerseys")
    def get_jerseys(match_id: str):
        """A kézzel hozzárendelt mezszámok (track_id → szám)."""
        if match_id not in _store:
            raise HTTPException(status_code=404, detail="match not found")
        p = _jerseys_path(match_id)
        if p.exists():
            try:
                return {"jerseys": json.loads(p.read_text(encoding="utf-8"))}
            except Exception:
                pass
        return {"jerseys": {}}

    @app.post("/matches/{match_id}/jerseys")
    def set_jersey(match_id: str, body: dict):
        """Mezszám hozzárendelése egy játékoshoz (track-hez) — a szám a
        meccs MINDEN kockájára ráíródik, így a statisztika, a passzháló,
        a jelentés és a CSV is név szerint (mezszámmal) beszél.

        Törzs: {"track_id": 7, "jersey": 23} — jersey=null törli a számot.
        A hozzárendelés lemezre mentődik, és a meccs betöltésekor újra
        érvényesül; a későbbi mezszám-OCR is ezt a tárat tölti majd."""
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        try:
            track_id = int(body["track_id"])
        except (KeyError, TypeError, ValueError):
            raise HTTPException(status_code=400, detail="track_id required")
        jersey = body.get("jersey")
        if jersey is not None:
            try:
                jersey = int(jersey)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="invalid jersey")
            if not (0 <= jersey <= 99):
                raise HTTPException(status_code=400,
                                    detail="jersey must be 0..99")
        p = _jerseys_path(match_id)
        mapping: dict = {}
        if p.exists():
            try:
                mapping = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                mapping = {}
        if jersey is None:
            mapping.pop(str(track_id), None)
        else:
            mapping[str(track_id)] = jersey
        p.write_text(json.dumps(mapping, ensure_ascii=False, indent=2),
                     encoding="utf-8")
        # Azonnal érvényesítjük a memóriabeli meccsen, és lemezre tükrözzük.
        _apply_jerseys(match, {str(track_id): jersey})
        _put_match(match)
        return {"jerseys": mapping}

    @app.get("/library/export")
    def export_library():
        """A TELJES meccskönyvtár egyetlen zip-ben: meccsek + jegyzetek +
        mezszámok + kiállítások + kalibrációk. Gépváltáshoz / biztonsági
        mentéshez — a videófájlokat NEM tartalmazza (azok nagyok és a
        felhasználó saját mappáiban vannak)."""
        import zipfile
        from fastapi.responses import FileResponse
        root = data_root() / "data"
        if not root.exists():
            raise HTTPException(status_code=404, detail="nincs még adat")
        zip_path = data_root() / "konyvtar_mentes.zip"
        n = 0
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            for f in sorted(root.rglob("*")):
                if f.is_file():
                    z.write(f, f.relative_to(root).as_posix())
                    n += 1
        if n == 0:
            raise HTTPException(status_code=404, detail="nincs még adat")
        return FileResponse(str(zip_path), media_type="application/zip",
                            filename="sportmachine_konyvtar.zip")

    async def import_library(request):
        """Meccskönyvtár visszaállítása a /library/export zip-jéből (nyers
        bájt-folyam a törzsben). A meglévő fájlokat felülírja, majd újra
        betölti a tárat. Path-traversal ellen csak a data/ alá csomagolunk ki.
        """
        import io
        import zipfile
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
        try:
            z = zipfile.ZipFile(io.BytesIO(bytes(body)))
        except Exception:
            raise HTTPException(status_code=400,
                                detail="a feltöltött fájl nem érvényes zip")
        root = (data_root() / "data").resolve()
        root.mkdir(parents=True, exist_ok=True)
        restored = 0
        for info in z.infolist():
            if info.is_dir():
                continue
            dest = (root / info.filename).resolve()
            if not str(dest).startswith(str(root)):
                continue  # kitörési kísérlet (../ vagy abszolút út) — kihagyjuk
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(z.read(info))
            restored += 1
        loaded = _load_store_from_disk()
        return {"restored_files": restored, "matches": loaded}

    import_library.__annotations__["request"] = Request
    app.post("/library/import")(import_library)

    @app.get("/players/trend")
    def get_player_trend(team: str, jersey: int):
        """Egy játékos fejlődése MECCSRŐL MECCSRE, mezszám alapján.

        A megadott csapatnévhez és mezszámhoz tartozó játékos terhelés-
        mutatói minden tárolt meccsből, időrendben. Ha egy meccsen több
        track viseli ugyanazt a számot (megszakadt követés), összegzünk —
        pont ezért éri meg mezszámot rendelni a játékosokhoz.
        """
        points = []
        for match in _store.values():
            side = None
            if match.meta.home_team == team:
                side = Team.HOME
            elif match.meta.away_team == team:
                side = Team.AWAY
            if side is None:
                continue
            tracks = set()
            for fr in match.frames:
                for p in fr.players:
                    if p.team == side and p.jersey_number == jersey:
                        tracks.add(p.track_id)
            if not tracks:
                continue
            stats = summarize(match)
            fps = match.meta.fps if match.meta.fps > 0 else 25.0
            distance = sum(stats[t].distance_m for t in tracks if t in stats)
            top = max((stats[t].top_speed_ms for t in tracks if t in stats),
                      default=0.0)
            sprints = sum(stats[t].sprint_count for t in tracks if t in stats)
            frames = sum(stats[t].measured_frames for t in tracks if t in stats)
            # Lövés-hatékonyság: a lövés-események lövője (player_id) a
            # játékos valamelyik trackje — így a gól/lövés trend is látszik.
            shots = goals = 0
            try:
                from ..pipeline.event_detection import EventType, detect_shots
                for e in detect_shots(match):
                    if e.player_id not in tracks or e.team != side:
                        continue
                    shots += 1
                    if e.type == EventType.GOAL:
                        goals += 1
            except Exception:
                pass
            # Helyzetminőség: a játékos lövéseinek várható gól-értéke ezen a
            # meccsen — a gól/xG trendből a FORMA látszik (a gólarány önmagában
            # a helyzetek minőségét is méri, nem csak a befejezést).
            xg = None
            try:
                from ..pipeline.xg import match_xg
                v = sum(r["xg"] for r in match_xg(match)["shooters"]
                        if r["player_id"] in tracks)
                xg = round(v, 2) if v > 0 else None
            except Exception:
                pass
            # Kapus-mérleg (ha a mezszám kapusé): védés + GSAx ezen a
            # meccsen, a kapusonkénti idővonal-rétegből.
            gk_on = gk_saves = gk_prevented = None
            try:
                from ..pipeline.goalkeeper import goalkeeper_timeline
                pk_tr = (goalkeeper_timeline(match)
                         .get(side.value, {}) or {}).get("per_keeper", {})
                recs_tr = [pk_tr[t] for t in tracks if t in pk_tr]
                if recs_tr:
                    gk_on = sum(r["on_target"] for r in recs_tr)
                    gk_saves = sum(r["saves"] for r in recs_tr)
                    gk_prevented = round(
                        sum(r.get("prevented", 0.0) for r in recs_tr), 2)
            except Exception:
                pass
            points.append({
                "match_id": match.meta.match_id,
                "date": match.meta.date,
                "opponent": (match.meta.away_team if side == Team.HOME
                             else match.meta.home_team),
                "gk_on_target": gk_on,
                "gk_saves": gk_saves,
                "gk_prevented": gk_prevented,
                "distance_m": round(distance, 1),
                "top_speed_ms": round(top, 2),
                "sprint_count": sprints,
                "minutes": round(frames / fps / 60.0, 1),
                "shots": shots,
                "goals": goals,
                "shot_pct": round(100.0 * goals / shots, 1) if shots else None,
                "xg": xg,
                "xg_diff": round(goals - xg, 2) if xg is not None else None,
            })
        points.sort(key=lambda p: (p["date"] or "", p["match_id"]))
        return {"team": team, "jersey": jersey, "points": points}

    @app.get("/season/report")
    def get_season_report(team: str):
        """Szezon-riport egy kattintásra: a csapat meccsei időrendben
        két időszakra bontva (fejlődés-tábla) + visszatérő edzés-
        fókuszok — nyomtatható HTML-ben. 404, ha 2-nél kevesebb meccs
        van a csapattól."""
        from fastapi.responses import HTMLResponse
        entries = []
        for m in _store.values():
            side = ("home" if m.meta.home_team == team
                    else "away" if m.meta.away_team == team else None)
            if side is None:
                continue
            entries.append((m.meta.date or "", m.meta.match_id, side))
        entries.sort()
        if len(entries) < 2:
            raise HTTPException(status_code=404,
                                detail="too few matches for team")
        cut = max(1, len(entries) // 2)
        older_items = [{"match_id": e[1], "team": e[2]}
                       for e in entries[:cut]]
        newer_items = [{"match_id": e[1], "team": e[2]}
                       for e in entries[cut:]]
        tr = trend_report(_combined_report({"items": older_items}),
                          _combined_report({"items": newer_items}))
        focuses = []
        try:
            focuses = (library_training_focus().get("teams", {})
                       .get(team, []))[:6]
        except Exception:
            pass
        from ..pipeline.report_html import season_report_html
        return HTMLResponse(content=season_report_html(
            team, tr, focuses, len(entries)))

    @app.get("/players/season-report")
    def get_player_season_report(team: str, jersey: int):
        """Szezon játékos-lap nyomtatható HTML-ben: a játékos meccsről
        meccsre (a /players/trend pontjaiból). 404, ha a mezszámhoz
        egyetlen meccsen sincs adat."""
        from fastapi.responses import HTMLResponse
        data = get_player_trend(team, jersey)
        if not data["points"]:
            raise HTTPException(status_code=404,
                                detail="no data for player")
        from ..pipeline.report_html import player_season_html
        return HTMLResponse(content=player_season_html(
            team, jersey, data["points"]))

    # Szezon-összkép gyorsítótár: meccsenkénti kivonat, a frame-szám a
    # kulcs érvényessége — újrafeldolgozásnál magától frissül.
    _summary_cache: dict = {}

    def _match_summary(m) -> dict:
        # Érvényesség: frame-szám + csapatnevek + dátum — átnevezés vagy
        # újrafeldolgozás után a kivonat újraszámolódik.
        key = (len(m.frames), m.meta.home_team, m.meta.away_team, m.meta.date)
        cached = _summary_cache.get(m.meta.match_id)
        if cached is not None and cached[0] == key:
            return cached[1]
        from ..pipeline.event_detection import EventType, detect_shots
        fps = m.meta.fps if m.meta.fps > 0 else 25.0
        goals_home = goals_away = shots = saves = 0
        try:
            for e in detect_shots(m):
                if e.type == EventType.GOAL:
                    if e.team == Team.HOME:
                        goals_home += 1
                    else:
                        goals_away += 1
                elif e.type == EventType.SHOT:
                    shots += 1
                    if (e.detail or {}).get("outcome") == "save":
                        saves += 1
        except Exception:
            pass  # sérült/üres meccsnél a többi mutató még érték
        distance_m = 0.0
        sprints = 0
        try:
            for s in summarize(m).values():
                distance_m += s.distance_m
                sprints += s.sprint_count
        except Exception:
            pass
        seven_meters = suspensions = 0
        try:
            from ..pipeline.rules import detect_powerplay, detect_seven_meters
            seven_meters = len(detect_seven_meters(m))
            suspensions = len(detect_powerplay(m))
        except Exception:
            pass
        # Szezon-trendhez: helyzetminőség (xG) és a védekezés szabad lövés-
        # aránya csapatonként — a dashboard trend-sávjai ezekből épülnek.
        xg_home = xg_away = None
        free_home = free_away = None
        try:
            from ..pipeline.xg import match_xg
            tx = match_xg(m)["teams"]
            if tx["home"]["shots"] + tx["away"]["shots"] > 0:
                xg_home, xg_away = tx["home"]["xg"], tx["away"]["xg"]
        except Exception:
            pass
        try:
            from ..pipeline.defense import defense_analysis
            d = defense_analysis(m)
            free_home = d["home"]["free_pct"]
            free_away = d["away"]["free_pct"]
        except Exception:
            pass
        poss_home = poss_away = None
        try:
            from ..pipeline.stats import possession_share
            ps = possession_share(m)
            if ps["home"]["pct"] or ps["away"]["pct"]:
                poss_home, poss_away = ps["home"]["pct"], ps["away"]["pct"]
        except Exception:
            pass
        cond_home = cond_away = None
        try:
            from ..pipeline.stats import intensity_trend
            it = intensity_trend(m)
            if it["home"]["first_ms"]:
                cond_home = it["home"]["drop_pct"]
            if it["away"]["first_ms"]:
                cond_away = it["away"]["drop_pct"]
        except Exception:
            pass
        blocks_home = blocks_away = None
        fastest_kmh = None
        try:
            from ..pipeline.defense import detect_blocks
            bl = detect_blocks(m)
            blocks_home = bl["home"]["blocks"]
            blocks_away = bl["away"]["blocks"]
        except Exception:
            pass
        try:
            from ..pipeline.event_detection import shot_speeds
            fastest = shot_speeds(m).get("fastest")
            if fastest:
                fastest_kmh = fastest["speed_kmh"]
        except Exception:
            pass
        xg_saved_home = xg_saved_away = None
        try:
            from ..pipeline.xg import xg_saved
            xs = xg_saved(m)
            if xs["home"] or xs["away"]:
                xg_saved_home = xs["home"]
                xg_saved_away = xs["away"]
        except Exception:
            pass
        # Egymondatos főcím a könyvtár-listához: eredmény + jelleg +
        # a meccs embere (ha kirajzolódik).
        headline = None
        try:
            total_g = goals_home + goals_away
            if total_g:
                margin = abs(goals_home - goals_away)
                if goals_home == goals_away:
                    core = f"döntetlen ({goals_home}–{goals_away})"
                else:
                    wname = (m.meta.home_team if goals_home > goals_away
                             else m.meta.away_team)
                    jelleg = ("szoros" if margin <= 2
                              else "sima" if margin >= 6 else "")
                    core = (f"{wname}-siker "
                            f"({goals_home}–{goals_away})")
                    if jelleg:
                        core = f"{jelleg} {core}"
                headline = core[0].upper() + core[1:]
                from ..pipeline.xg import match_xg
                best_sc = None
                for rec_sc in match_xg(m).get("shooters", []):
                    if best_sc is None or rec_sc["goals"] > best_sc["goals"]:
                        best_sc = rec_sc
                if best_sc is not None and best_sc["goals"] >= 4:
                    headline += (f" — a meccs embere a(z) "
                                 f"{best_sc['player_id']}. játékos "
                                 f"({best_sc['goals']} gól)")
        except Exception:
            pass
        susp_home = susp_away = None
        try:
            from ..pipeline.rules import detect_powerplay
            pps_lib = detect_powerplay(m)
            if pps_lib:
                susp_home = sum(1 for w in pps_lib
                                if w["team_down"] == "home")
                susp_away = sum(1 for w in pps_lib
                                if w["team_down"] == "away")
        except Exception:
            pass
        out = {
            "match_id": m.meta.match_id,
            "home_team": m.meta.home_team,
            "away_team": m.meta.away_team,
            "date": m.meta.date,
            "duration_s": round(len(m.frames) / fps, 1),
            "goals_home": goals_home,
            "goals_away": goals_away,
            "shots": shots,
            "saves": saves,
            "distance_m": round(distance_m, 1),
            "sprints": sprints,
            "seven_meters": seven_meters,
            "suspensions": suspensions,
            "xg_home": xg_home,
            "xg_away": xg_away,
            "free_pct_home": free_home,
            "free_pct_away": free_away,
            "possession_home": poss_home,
            "possession_away": poss_away,
            "cond_drop_home": cond_home,
            "cond_drop_away": cond_away,
            "blocks_home": blocks_home,
            "blocks_away": blocks_away,
            "fastest_kmh": fastest_kmh,
            "xg_saved_home": xg_saved_home,
            "headline": headline,
            "suspensions_home": susp_home,
            "suspensions_away": susp_away,
            "xg_saved_away": xg_saved_away,
        }
        _summary_cache[m.meta.match_id] = (key, out)
        return out

    @app.get("/library/summary")
    def library_summary():
        """Szezon-összkép a kezdőlapnak: a teljes könyvtár összesített
        mutatói + meccsenkénti kivonat (gólok, lövések, táv, sprintek).

        A meccsenkénti számítás gyorsítótárazott (frame-szám az érvényesség),
        így a kezdőlap újranyitása nagy könyvtárnál is azonnali.
        """
        per = [_match_summary(m) for m in _store.values()]
        per.sort(key=lambda d: (d.get("date") or "", d["match_id"]))
        teams = sorted({t for d in per
                        for t in (d["home_team"], d["away_team"]) if t})
        return {
            "matches": len(per),
            "total_duration_s": round(sum(d["duration_s"] for d in per), 1),
            "teams": teams,
            "goals": sum(d["goals_home"] + d["goals_away"] for d in per),
            "shots": sum(d["shots"] for d in per),
            "saves": sum(d.get("saves", 0) for d in per),
            "sprints": sum(d["sprints"] for d in per),
            "distance_km": round(sum(d["distance_m"] for d in per) / 1000.0, 2),
            "per_match": per,
        }

    # Edzés-fókusz kivonat-gyorsítótár (match_id → (kulcs, eredmény)) — a
    # könyvtár-szintű összesítés ne számolja újra a változatlan meccseket.
    _training_cache: dict = {}

    @app.get("/library/training-focus")
    def library_training_focus():
        """VISSZATÉRŐ edzés-fókuszok csapatonként, a teljes könyvtárból.

        Minden tárolt meccsre lefut az edzés-fókusz elemzés, és a csapat-
        nevek mentén összesítjük: ami legalább KÉT meccsen előjött, az nem
        egyszeri kisiklás, hanem visszatérő gyengeség — az edzéstervezés
        első számú jelöltje. Visszatérés:
        {"teams": {csapatnév: [{"title","area","count","why","drill"}]},
         "matches": {csapatnév: meccsek száma}}."""
        from ..pipeline.training import training_focus
        agg: dict = {}
        counts: dict = {}
        for m in _store.values():
            key = (len(m.frames), m.meta.home_team, m.meta.away_team)
            cached = _training_cache.get(m.meta.match_id)
            if cached is not None and cached[0] == key:
                tf = cached[1]
            else:
                try:
                    tf = training_focus(m)
                except Exception:
                    tf = {"home": [], "away": []}
                _training_cache[m.meta.match_id] = (key, tf)
            for side, name in (("home", m.meta.home_team),
                               ("away", m.meta.away_team)):
                if not name:
                    continue
                counts[name] = counts.get(name, 0) + 1
                for it in tf.get(side) or []:
                    rec = agg.setdefault(name, {}).setdefault(it["title"], {
                        "title": it["title"], "area": it["area"],
                        "count": 0, "why": it["why"], "drill": it["drill"]})
                    rec["count"] += 1
                    rec["why"] = it["why"]  # a legutóbbi meccs indoka
        teams = {}
        for name, items in agg.items():
            recurring = sorted((r for r in items.values() if r["count"] >= 2),
                               key=lambda r: -r["count"])
            if recurring:
                teams[name] = recurring
        return {"teams": teams, "matches": counts}

    @app.get("/matches/{match_id}/positions")
    def get_positions(match_id: str):
        """Poszt-becslés: ki a beálló / szélső / átlövő / irányító a
        támadó-fázis átlag-pozícióiból."""
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        from ..pipeline.roles import estimate_positions
        return {"positions": estimate_positions(match)}

    @app.get("/matches/{match_id}/players/{track_id}/report")
    def get_player_report(match_id: str, track_id: int):
        """Játékos-lap: egy játékos meccs-riportja kiosztható HTML-ben
        (játék-mérleg + fizikai mutatók). 404, ha a track ismeretlen."""
        from fastapi.responses import HTMLResponse
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        from ..pipeline.report_html import player_report_html
        try:
            html = player_report_html(match, track_id)
        except ValueError:
            raise HTTPException(status_code=404,
                                detail="player not found")
        return HTMLResponse(content=html)

    @app.get("/matches/{match_id}/key-moments")
    def get_key_moments(match_id: str):
        """A meccs gerince: kulcs-pillanatok időrendben (fordulópont,
        sorozatok, kiállítások, hetesek, kapuscserék) — az app
        kattintható listájához és külső felhasználáshoz."""
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        from ..pipeline.momentum import key_moments
        return {"moments": key_moments(match)}

    @app.get("/matches/{match_id}/key-players")
    def get_key_players(match_id: str):
        """Kulcsemberek: kinél dől el a meccs (fő lövő, fal kulcsa,
        hetes-dobó, kontra-befejező, indítás-célpont)."""
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        from ..pipeline.scouting import match_key_players
        return {"key_players": match_key_players(match)}

    @app.get("/matches/{match_id}/goalkeepers")
    def get_goalkeeper_stats(match_id: str):
        """Kapus-teljesítmény: kapott kapura tartó lövések, védések,
        kapott gólok (zóna-bontással) és védés-hatékonyság csapatonként.
        Üres szótár, ha a meccsen nincs kapus-jelölés."""
        from ..pipeline.goalkeeper import goalkeeper_stats
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        res = {"goalkeepers": goalkeeper_stats(match)}
        try:
            from ..pipeline.goalkeeper import goalkeeper_timeline, outlet_speed
            res["timeline"] = goalkeeper_timeline(match)
            res["outlets"] = outlet_speed(match)
            from ..pipeline.xg import xg_saved
            res["xg_saved"] = xg_saved(match)
        except Exception:
            pass
        return res

    @app.get("/matches/{match_id}/rules")
    def get_rules(match_id: str):
        """Szabály-értő réteg: emberhátrány-szakaszok (kiállítás lenyomata),
        hétméteresek és passzív-játék kockázatú támadások."""
        from ..pipeline.rules import rules_report
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        return rules_report(match)

    @app.get("/matches/{match_id}/attacks")
    def get_attacks(match_id: str):
        """Támadás-szakaszok típus-címkével (lerohanás / gyors indítás /
        felállt / 7 a 6) + csapatonkénti támadás-mix százalékban."""
        from ..pipeline.attack_types import (attack_duration_efficiency,
                                             attack_efficiency, attack_mix,
                                             classify_attacks)
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        return {"attacks": classify_attacks(match),
                "mix": attack_mix(match),
                "efficiency": attack_efficiency(match),
                "duration_efficiency": attack_duration_efficiency(match)}

    @app.get("/matches/{match_id}/empty-net")
    def get_empty_net(match_id: str):
        """7 a 6 elleni (üres kapus) szakaszok: mikor és mennyi ideig
        játszott egy csapat lehozott kapussal. Üres lista, ha nincs
        kapus-jelölés vagy nem volt ilyen szakasz."""
        from ..pipeline.goalkeeper import detect_empty_net
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        return {"windows": detect_empty_net(match)}

    @app.get("/matches/{match_id}/momentum")
    def get_momentum(match_id: str):
        """Gól-sorozatok (momentum): válasz nélküli szériák a felismert
        gólokból, a pillanatnyi állással. Üres lista, ha nincs érdemi
        sorozat vagy nincs felismert gól. Minden sorozathoz "context"
        címkelista: a sorozat LEHETSÉGES OKAI (emberelőny, 7 a 6,
        az ellenfél védekezés-váltása / tempó-esése)."""
        from ..pipeline.momentum import (annotate_runs, clutch_performance,
                                         goal_droughts, goal_responses,
                                         halftime_score, score_progression,
                                         scoring_timeline, win_probability)
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        return {"runs": annotate_runs(match),
                "progression": score_progression(match),
                "timeline": scoring_timeline(match),
                "clutch": clutch_performance(match),
                "droughts": goal_droughts(match),
                "halftime": halftime_score(match),
                "responses": goal_responses(match),
                "win_prob": win_probability(match)}

    @app.get("/matches/{match_id}/xg")
    def get_xg(match_id: str):
        """Helyzetminőség (xG): lövésenkénti érték + csapat-összegzés
        (várható gól vs tényleges — befejezés-hatékonyság)."""
        from ..pipeline.xg import match_xg
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        return match_xg(match)

    @app.get("/matches/{match_id}/defense")
    def get_defense(match_id: str):
        """Védekezés-elemzés: kapott lövések — szabadon hagyott lövők,
        zóna-lyukak, kapott xG (csapatonként, a védekező szemszögéből)."""
        from ..pipeline.defense import (defense_analysis,
                                        transition_defense)
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        res = defense_analysis(match)
        res["transition"] = transition_defense(match)
        try:
            from ..pipeline.defense import defensive_pressure
            res["pressure"] = defensive_pressure(match)
        except Exception:
            pass
        try:
            from ..pipeline.defense import turnover_zones
            res["turnover_zones"] = turnover_zones(match)
        except Exception:
            pass
        try:
            from ..pipeline.defense import detect_blocks
            res["blocks"] = detect_blocks(match)
        except Exception:
            pass
        try:
            from ..pipeline.defense import transition_recovery
            res["recovery"] = transition_recovery(match)
        except Exception:
            pass
        try:
            from ..pipeline.defense import pressure_finishing
            res["pressure_finishing"] = pressure_finishing(match)
        except Exception:
            pass
        return res

    @app.get("/matches/{match_id}/playmaker")
    def get_playmaker(match_id: str):
        """Irányító-függés: a fő szervező azonosítása, és a vele/nélküle
        futott támadások eredményességének összevetése csapatonként."""
        from ..pipeline.playmaker import playmaker_dependency
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        return playmaker_dependency(match)

    @app.get("/matches/{match_id}/substitutions")
    def get_substitutions(match_id: str):
        """Cserehullámok (a cserezónán át ki-be lépő track-ekből) + a
        cserék utáni 90 mp mérlege (dobott/kapott gól) csapatonként."""
        from ..pipeline.substitutions import substitution_impact
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        return substitution_impact(match)

    @app.get("/matches/{match_id}/stoppages")
    def get_stoppages(match_id: str):
        """Játékmegszakítások (időkérés-szerű tartós leállások) a mozgás-
        jelekből, a valószínű kérő csapattal és az időkérés HATÁSÁVAL
        (előtte/utána kapott gólok, ítélet)."""
        from ..pipeline.stoppages import timeout_effects
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        return {"stoppages": timeout_effects(match)}

    @app.get("/matches/{match_id}/training")
    def get_training(match_id: str):
        """Edzés-fókusz javaslatok a meccs gyengeségeiből, csapatonként
        rangsorolva (terület, fókusz, indoklás, gyakorlat-típus)."""
        from ..pipeline.training import training_focus
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        return training_focus(match)

    @app.get("/matches/{match_id}/coach-summary")
    def get_coach_summary(match_id: str):
        """Automatikus edzői összefoglaló magyarul: mi történt a meccsen,
        mi volt feltűnő, mire érdemes ránézni. Sablon-alapú (minden mondat
        mögött kiszámolt szám áll), determinisztikus."""
        from ..pipeline.coach_summary import coach_summary
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        return coach_summary(match)

    @app.get("/matches/{match_id}/intensity")
    def get_intensity(match_id: str, window_s: float = 300.0):
        """Intenzitás-idővonal: csapatonkénti átlagos mozgás-sebesség
        idő-ablakonként (fáradás-elemzés)."""
        from ..pipeline.stats import compute_intensity_timeline
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        return {"windows": compute_intensity_timeline(match, window_s=window_s)}

    @app.post("/matches/{match_id}/package/export")
    def start_package_export(match_id: str, body: dict):
        """MECCS-CSOMAG készítése háttérszálon: nyomtatható jelentés (HTML) +
        játékos-statisztika (CSV) + gól/lövés-klipek egyetlen zip-ben — az
        edző egy fájlt küld a klubnak/csapatnak. A haladás a /jobs/{id}-n
        követhető; a kész zip a GET /matches/{id}/package/download címen.

        Törzs: {"clip_types": ["goal", ...]} — üres lista = nincs klip;
        hiányzó kulcs = csak a gólok. Ha az eredeti videó nem érhető el, a
        csomag klipek nélkül készül el (a jelentés + CSV akkor is érték)."""
        import time
        import uuid
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        clip_types = body.get("clip_types")
        types = set(clip_types) if clip_types is not None else {"goal"}

        job_id = uuid.uuid4().hex[:12]
        job = {"job_id": job_id, "match_id": match_id, "status": "running",
               "stage": "P", "progress": 0.0, "message": "csomag készítése",
               "error": None, "created": time.time(),
               "video": Path(match.meta.video_path or "").name}
        _jobs[job_id] = job

        out_dir = _clips_dir(match_id)  # a klipek munkamappája újrahasznosítva

        def _work():
            import zipfile
            from ..pipeline.clips import export_event_clips
            from ..pipeline.quality import compute_quality_report
            from ..pipeline.report_html import match_report_html
            try:
                out_dir.mkdir(parents=True, exist_ok=True)
                events = detect_events(match)
                # 1) Jelentés (HTML) — minden mellék-adattal, ami van.
                job["message"] = "jelentés készítése"
                try:
                    quality = compute_quality_report(match)
                except Exception:
                    quality = None
                try:
                    heatmaps = {t.value: compute_team_heatmap(match, t)
                                for t in (Team.HOME, Team.AWAY)}
                except Exception:
                    heatmaps = None
                try:
                    player_stats = summarize(match)
                except Exception:
                    player_stats = None
                html = match_report_html(
                    match, team_style_profile(match), events, quality,
                    heatmaps=heatmaps, player_stats=player_stats,
                    notes=_load_notes(match_id))
                # 2) CSV.
                job["progress"] = 0.2
                job["message"] = "statisztika (CSV)"
                csv = _stats_csv(match)
                # 2/b) Minden elemzés-réteg egyetlen, géppel olvasható
                # JSON-ban (archívumhoz / a klub saját eszközeihez), és az
                # edzői összefoglaló sima szövegként — rétegenként hibatűrően.
                job["message"] = "elemzések (JSON)"
                analyses: dict = {}

                def _layer(name, fn):
                    try:
                        analyses[name] = fn()
                    except Exception:
                        pass

                from ..pipeline.coach_summary import coach_summary
                from ..pipeline.defense import defense_analysis
                from ..pipeline.momentum import annotate_runs
                from ..pipeline.playmaker import playmaker_dependency
                from ..pipeline.rules import rules_report
                from ..pipeline.stoppages import timeout_effects
                from ..pipeline.substitutions import substitution_impact
                from ..pipeline.training import training_focus
                from ..pipeline.xg import match_xg
                _layer("coach_summary", lambda: coach_summary(match))
                _layer("xg", lambda: match_xg(match))
                _layer("defense", lambda: defense_analysis(match))
                from ..pipeline.defense import turnover_zones
                _layer("turnover_zones", lambda: turnover_zones(match))
                from ..pipeline.defense import detect_blocks
                _layer("blocks", lambda: detect_blocks(match))
                from ..pipeline.tactics import slow_attacks
                _layer("slow_attacks", lambda: slow_attacks(match))
                from ..pipeline.defense import pressure_finishing
                _layer("pressure_finishing",
                       lambda: pressure_finishing(match))
                from ..pipeline.tactics import attack_sides
                _layer("attack_sides", lambda: attack_sides(match))
                from ..pipeline.tactics import efficiency_vs_formation
                _layer("vs_formation",
                       lambda: efficiency_vs_formation(match))
                _layer("rules", lambda: rules_report(match))
                _layer("momentum", lambda: annotate_runs(match))
                from ..pipeline.momentum import score_progression
                _layer("progression", lambda: score_progression(match))
                from ..pipeline.momentum import clutch_performance
                _layer("clutch", lambda: clutch_performance(match))
                from ..pipeline.momentum import goal_droughts
                _layer("droughts", lambda: goal_droughts(match))
                from ..pipeline.momentum import halftime_score
                _layer("halftime", lambda: halftime_score(match))
                from ..pipeline.momentum import goal_responses
                _layer("responses", lambda: goal_responses(match))
                from ..pipeline.momentum import win_probability
                _layer("win_prob", lambda: win_probability(match))
                from ..pipeline.goalkeeper import goalkeeper_timeline
                _layer("gk_timeline", lambda: goalkeeper_timeline(match))
                from ..pipeline.quality import analysis_confidence
                _layer("confidence", lambda: analysis_confidence(match))
                from ..pipeline.attack_types import attack_efficiency
                _layer("attack_efficiency", lambda: attack_efficiency(match))
                from ..pipeline.attack_types import attack_duration_efficiency
                _layer("attack_duration_efficiency",
                       lambda: attack_duration_efficiency(match))
                from ..pipeline.event_detection import assist_network
                _layer("assist_network", lambda: assist_network(match))
                from ..pipeline.event_detection import pass_network
                _layer("pass_network", lambda: pass_network(match))
                from ..pipeline.event_detection import shot_speeds
                _layer("shot_speeds", lambda: shot_speeds(match))
                from ..pipeline.stats import possession_share
                _layer("possession", lambda: possession_share(match))
                from ..pipeline.stats import intensity_trend
                _layer("intensity_trend", lambda: intensity_trend(match))
                from ..pipeline.stats import player_fatigue
                _layer("player_fatigue", lambda: player_fatigue(match))
                _layer("playmaker", lambda: playmaker_dependency(match))
                _layer("substitutions", lambda: substitution_impact(match))
                _layer("stoppages", lambda: timeout_effects(match))
                _layer("training", lambda: training_focus(match))
                # Újabb rétegek: kapus-indítás, 7 a 6 mérleg/időzítés,
                # kontra-befejezők, kulcsemberek, tempó, késő cserék.
                from ..pipeline.attack_types import (fast_break_finishers,
                                                     match_pace)
                from ..pipeline.goalkeeper import (empty_net_context,
                                                   empty_net_goals,
                                                   outlet_speed)
                from ..pipeline.scouting import match_key_players
                from ..pipeline.substitutions import late_sub_flags
                from ..pipeline.xg import big_saves, missed_big_chances
                _layer("outlets", lambda: outlet_speed(match))
                _layer("empty_net_goals", lambda: empty_net_goals(match))
                _layer("empty_net_context",
                       lambda: empty_net_context(match))
                _layer("fast_break_finishers",
                       lambda: fast_break_finishers(match))
                _layer("key_players", lambda: match_key_players(match))
                _layer("pace", lambda: match_pace(match))
                _layer("late_subs", lambda: late_sub_flags(match))
                _layer("big_saves", lambda: big_saves(match))
                _layer("missed_big_chances",
                       lambda: missed_big_chances(match))
                from ..pipeline.attack_types import attack_origins
                from ..pipeline.xg import xg_prevented, xg_saved
                _layer("xg_saved", lambda: xg_saved(match))
                _layer("xg_prevented", lambda: xg_prevented(match))
                _layer("attack_origins", lambda: attack_origins(match))
                from ..pipeline.defense import transition_recovery
                _layer("recovery", lambda: transition_recovery(match))
                from ..pipeline.roles import estimate_positions
                _layer("positions", lambda: estimate_positions(match))
                from ..pipeline.rules import seven_meter_earners
                _layer("seven_earners",
                       lambda: seven_meter_earners(match))
                from ..pipeline.rules import suspension_earners
                _layer("susp_earners",
                       lambda: suspension_earners(match))
                from ..pipeline.halftime import second_half_start
                _layer("second_half_start",
                       lambda: second_half_start(match))
                from ..pipeline.attack_types import pace_by_score
                _layer("pace_by_score",
                       lambda: pace_by_score(match))
                from ..pipeline.momentum import key_moments
                _layer("key_moments", lambda: key_moments(match))
                from ..pipeline.setplays import setplay_efficiency
                _layer("setplay_efficiency",
                       lambda: setplay_efficiency(match))
                analyses_json = json.dumps(analyses, ensure_ascii=False,
                                           indent=2)
                summary_txt = ""
                cs = analyses.get("coach_summary") or {}
                lines = [f"{match.meta.home_team} vs {match.meta.away_team}"
                         + (f" · {match.meta.date}" if match.meta.date else ""),
                         ""]
                for sec in cs.get("sections", []):
                    lines += [sec.get("title", ""), sec.get("body", ""), ""]
                if cs.get("highlights"):
                    lines += ["Mire nézz rá:"]
                    lines += [f"- {h}" for h in cs["highlights"]]
                summary_txt = "\n".join(lines)
                # 3) Klipek (ha kérték és van videó) — a hiba nem végzetes.
                clips_zip = None
                if types:
                    def cb(done, total, msg):
                        job["progress"] = 0.25 + 0.65 * (done / max(1, total))
                        job["message"] = msg
                    try:
                        ev = [{"t": e.t, "type": e.type.value,
                               "team": e.team.value} for e in events]
                        res = export_event_clips(match, ev, types, out_dir,
                                                 progress_cb=cb)
                        clips_zip = Path(res.zip_path)
                    except Exception as e:
                        job["message"] = f"klipek kihagyva: {e}"
                # 4) Minden egy zip-be.
                job["progress"] = 0.95
                job["message"] = "csomagolás"
                pkg = out_dir / "meccs_csomag.zip"
                with zipfile.ZipFile(pkg, "w", zipfile.ZIP_STORED) as z:
                    z.writestr("jelentes.html", html)
                    z.writestr("statisztika.csv", csv.encode("utf-8"))
                    z.writestr("elemzesek.json",
                               analyses_json.encode("utf-8"))
                    # Az edzői jegyzetek sima szövegként (időbélyeggel).
                    notes = _load_notes(match_id)
                    if notes:
                        fps_n = match.meta.fps if match.meta.fps > 0 else 25.0
                        nl = []
                        for n in sorted(notes,
                                        key=lambda x: x.get("frame", 0)):
                            sec = (n.get("frame", 0) or 0) / fps_n
                            nl.append(f"[{int(sec // 60)}:{int(sec % 60):02d}]"
                                      f" {n.get('text', '')}")
                        z.writestr("jegyzetek.txt",
                                   "\n".join(nl).encode("utf-8"))
                    if summary_txt:
                        z.writestr("osszefoglalo.txt",
                                   summary_txt.encode("utf-8"))
                    # Kulcs-pillanatok: időbélyeges lista a videó gyors
                    # visszanézéséhez — a közös key_moments rétegből.
                    try:
                        from ..pipeline.momentum import key_moments
                        kms = key_moments(match)
                        if kms:
                            klines = [
                                f"[{int(km['t_s'] // 60)}:"
                                f"{int(km['t_s'] % 60):02d}] "
                                f"{km['label']}"
                                for km in kms]
                            z.writestr("kulcs_pillanatok.txt",
                                       "\n".join(klines)
                                       .encode("utf-8"))
                    except Exception:
                        pass
                    # Játékos-lapok: minden játékos egyéni meccs-
                    # riportja a jatekos_lapok/ mappában — kiosztásra.
                    try:
                        import re

                        from ..pipeline.report_html import (
                            player_report_html)
                        from ..pipeline.stats import (
                            aggregate_by_jersey, compute_player_stats)
                        _pl_stats = compute_player_stats(match)
                        _team_of: dict = {}
                        _jersey_of: dict = {}
                        for _fr in match.frames:
                            for _p in _fr.players:
                                _team_of.setdefault(
                                    _p.track_id,
                                    getattr(_p.team, "value", _p.team))
                                if _p.jersey_number is not None:
                                    _jersey_of.setdefault(
                                        _p.track_id, _p.jersey_number)
                        _fps_pl = (match.meta.fps
                                   if match.meta.fps > 0 else 25.0)
                        for _g in aggregate_by_jersey(
                                _pl_stats, _team_of, _jersey_of,
                                fps=_fps_pl):
                            if not _g["track_ids"]:
                                continue
                            _safe = re.sub(
                                r"[^\wáéíóöőúüűÁÉÍÓÖŐÚÜŰ-]+", "_",
                                f"{_g['team']}_{_g['label']}")
                            try:
                                z.writestr(
                                    f"jatekos_lapok/{_safe}.html",
                                    player_report_html(
                                        match, _g["track_ids"][0])
                                    .encode("utf-8"))
                            except Exception:
                                continue
                    except Exception:
                        pass
                    # Meccsterv a visszavágóra: a két csapat e meccsen
                    # mért profiljának keresztezése, mindkét irányban.
                    try:
                        from ..pipeline.scouting import (matchup_plan,
                                                         scout_team)
                        rep_h = scout_team(match, Team.HOME,
                                           TacticsConfig())
                        rep_a = scout_team(match, Team.AWAY,
                                           TacticsConfig())
                        mt_lines = []
                        plan_h = matchup_plan(rep_h, rep_a)
                        if plan_h:
                            head_h = (f"{match.meta.home_team} terve a "
                                      f"{match.meta.away_team} ellen")
                            mt_lines += [head_h, "=" * len(head_h)]
                            mt_lines += [f"- {p_}" for p_ in plan_h]
                            mt_lines.append("")
                        plan_a = matchup_plan(rep_a, rep_h)
                        if plan_a:
                            head_a = (f"{match.meta.away_team} terve a "
                                      f"{match.meta.home_team} ellen")
                            mt_lines += [head_a, "=" * len(head_a)]
                            mt_lines += [f"- {p_}" for p_ in plan_a]
                            mt_lines.append("")
                        if mt_lines:
                            z.writestr("meccsterv.txt",
                                       "\n".join(mt_lines)
                                       .encode("utf-8"))
                    except Exception:
                        pass
                    # Edzésterv sima szövegként: fókuszok indoklással
                    # és gyakorlatokkal, csapatonként.
                    tf_pkg = analyses.get("training") or {}
                    tl_lines = []
                    for side, name in (("home", match.meta.home_team),
                                       ("away", match.meta.away_team)):
                        items = tf_pkg.get(side) or []
                        if not items:
                            continue
                        tl_lines += [name, "=" * len(name)]
                        for it in items:
                            tl_lines.append(
                                f"- {it.get('title', '')} "
                                f"({it.get('area', '')})")
                            tl_lines.append(
                                f"  miért: {it.get('why', '')}")
                            tl_lines.append(
                                f"  gyakorlat: {it.get('drill', '')}")
                        tl_lines.append("")
                    if tl_lines:
                        z.writestr("edzesterv.txt",
                                   "\n".join(tl_lines).encode("utf-8"))
                    if clips_zip is not None and clips_zip.exists():
                        z.write(clips_zip, "klipek.zip")
                job["status"] = "done"
                job["progress"] = 1.0
                job["message"] = ("kész (jelentés + CSV"
                                  + (" + klipek)" if clips_zip else ")"))
            except Exception as e:
                job["status"] = "error"
                job["error"] = str(e)
                job["message"] = f"hiba: {e}"
            _log_job(job)

        _threading.Thread(target=_work, daemon=True).start()
        return {"job_id": job_id}

    @app.get("/matches/{match_id}/package/download")
    def download_package(match_id: str):
        """A legutóbb elkészített meccs-csomag (zip) letöltése."""
        from fastapi.responses import FileResponse
        if match_id not in _store:
            raise HTTPException(status_code=404, detail="match not found")
        pkg = _clips_dir(match_id) / "meccs_csomag.zip"
        if not pkg.exists():
            raise HTTPException(status_code=404,
                                detail="nincs kész csomag ehhez a meccshez")
        return FileResponse(str(pkg), media_type="application/zip",
                            filename=f"meccs_csomag_{match_id}.zip")

    @app.get("/matches/{match_id}/heatmap")
    def get_heatmap(match_id: str, team: str = "home",
                    bins_x: int = 20, bins_y: int = 10):
        """A megadott csapat hőtérképe (rács-cellánkénti látogatottság)."""
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        try:
            t = Team(team)
        except ValueError:
            raise HTTPException(status_code=400, detail="team must be 'home' or 'away'")
        hm = compute_team_heatmap(match, t, bins_x=bins_x, bins_y=bins_y)
        return {"bins_x": hm.bins_x, "bins_y": hm.bins_y, "total": hm.total, "grid": hm.grid}

    @app.get("/matches/{match_id}/team-stats")
    def get_team_stats(match_id: str):
        """Mindkét csapat összegzése (súlypont, kiterjedés)."""
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        out = {team.value: vars(compute_team_summary(match, team))
               for team in (Team.HOME, Team.AWAY)}
        try:
            from ..pipeline.stats import possession_share
            out["possession"] = possession_share(match)
        except Exception:
            pass
        try:
            from ..pipeline.stats import intensity_trend
            out["intensity_trend"] = intensity_trend(match)
        except Exception:
            pass
        try:
            from ..pipeline.stats import player_fatigue
            out["player_fatigue"] = player_fatigue(match)
        except Exception:
            pass
        return out

    @app.get("/matches/{match_id}/tactics")
    def get_tactics(match_id: str):
        """Taktikai összkép (csapat-stílusprofil): fázis-megoszlás, csapatonkénti
        leggyakoribb védekezési forma, és tempó-metrikák."""
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        res = team_style_profile(match)
        try:
            from ..pipeline.tactics import slow_attacks
            res["slow_attacks"] = slow_attacks(match)
        except Exception:
            pass
        try:
            from ..pipeline.tactics import attack_sides
            res["attack_sides"] = attack_sides(match)
        except Exception:
            pass
        try:
            from ..pipeline.tactics import efficiency_vs_formation
            res["vs_formation"] = efficiency_vs_formation(match)
        except Exception:
            pass
        return res

    @app.get("/matches/{match_id}/report/export")
    def export_match_report(match_id: str):
        """A meccs egyoldalas edzői jelentése NYOMTATHATÓ HTML-ként.

        Tartalma: mutatók, esemény-összesítő (gól/lövés/labdaeladás),
        játékfázisok, védekezési formák, gól-idővonal, minőség-önellenőrzés.
        Böngészőben megnyitva Ctrl+P/⌘P → PDF."""
        from fastapi import Response
        from ..pipeline.report_html import match_report_html
        from ..pipeline.quality import compute_quality_report
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        tactics = team_style_profile(match)
        events = detect_events(match)
        try:
            quality = compute_quality_report(match)
        except Exception:
            quality = None  # a jelentés minőség-szakasz nélkül is teljes
        try:
            heatmaps = {t.value: compute_team_heatmap(match, t)
                        for t in (Team.HOME, Team.AWAY)}
        except Exception:
            heatmaps = None  # hőtérkép nélkül is teljes a jelentés
        try:
            player_stats = summarize(match)  # terhelés-tábla a jelentésbe
        except Exception:
            player_stats = None
        html = match_report_html(match, tactics, events, quality,
                                 heatmaps=heatmaps, player_stats=player_stats,
                                 notes=_load_notes(match_id))
        return Response(content=html, media_type="text/html; charset=utf-8")

    @app.get("/matches/{match_id}/scouting")
    def get_scouting(match_id: str, team: str = "away"):
        """Ellenfél-felderítő jelentés a megadott csapatról EGY meccsből.

        `team`: melyik csapatot derítjük fel ('home'/'away'). A jelentés edzői
        nyelven adja a védekezést, tempót, befejezést, kulcsjátékosokat és a
        "hogyan játssz ellenük" kulcsokat."""
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        try:
            t = Team(team)
        except ValueError:
            raise HTTPException(status_code=400, detail="team must be 'home' or 'away'")
        return report_to_dict(scout_team(match, t, TacticsConfig()))

    @app.get("/matches/{match_id}/scouting/export")
    def export_scouting(match_id: str, team: str = "away"):
        """A felderítő jelentés NYOMTATHATÓ, önálló HTML-je (böngészőből PDF).

        Az edző ezt menti/nyomtatja a stábnak. Minden stílus beágyazva, offline
        is megnyitható."""
        from fastapi import Response
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        try:
            t = Team(team)
        except ValueError:
            raise HTTPException(status_code=400, detail="team must be 'home' or 'away'")
        # Figura-egyezés a mentett könyvtárral — ha van figura, a jelentésbe kerül.
        from ..pipeline.setplays import match_attacks_to_playbook
        plays = []
        for f in sorted(_playbook_dir.glob("*.json")):
            try:
                plays.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                continue
        pm = match_attacks_to_playbook(match, plays, TacticsConfig(), team=t) if plays else None
        rep_sc = scout_team(match, t, TacticsConfig())
        # Meccsterv-illesztés a másik oldallal (mint a képernyő
        # MECCSTERV kártyája) — hibatűrően, enélkül is teljes.
        matchup = None
        try:
            from ..pipeline.scouting import matchup_plan
            own_t = Team.HOME if t == Team.AWAY else Team.AWAY
            matchup = matchup_plan(
                scout_team(match, own_t, TacticsConfig()), rep_sc) or None
        except Exception:
            matchup = None
        html = scouting_report_html(rep_sc, playbook_match=pm,
                                    matchup=matchup)
        return Response(content=html, media_type="text/html; charset=utf-8")

    def _combined_report(body: dict):
        """Közös segéd: a törzs items-eiből egyesített ScoutingReport-ot épít."""
        items = body.get("items")
        if not items or not isinstance(items, list):
            raise HTTPException(status_code=400, detail="items required")
        reports = []
        for it in items:
            m = _store.get(it.get("match_id"))
            if m is None:
                raise HTTPException(status_code=404, detail=f"match not found: {it.get('match_id')}")
            try:
                t = Team(it.get("team", "away"))
            except ValueError:
                raise HTTPException(status_code=400, detail="team must be 'home' or 'away'")
            reports.append(scout_team(m, t, TacticsConfig()))
        return combine_reports(reports)

    @app.post("/scouting")
    def combined_scouting(body: dict):
        """TÖBB meccsből egyesített felderítő jelentés egy csapatról.

        Törzs: {"items": [{"match_id": "...", "team": "home"|"away"}, ...]}.
        Több meccs adja a valós, zajmentes profilt (a számokat átlagolja/összegzi).
        """
        return report_to_dict(_combined_report(body))

    @app.post("/scouting/trend")
    def scouting_trend(body: dict):
        """Fejlődés-követés: két időszak összevetése egy csapatról.

        Törzs: {"older": {"items": [...]}, "newer": {"items": [...]}} — az items
        formátuma azonos a /scouting-éval. Visszaadja mutatónként a régi/új
        értéket, a változást és a javult/romlott minősítést + magyar összegzést."""
        older_body = body.get("older")
        newer_body = body.get("newer")
        if not older_body or not newer_body:
            raise HTTPException(status_code=400, detail="older and newer required")
        older = _combined_report(older_body)
        newer = _combined_report(newer_body)
        return trend_report(older, newer)

    @app.post("/scouting/trend/export")
    def scouting_trend_export(body: dict):
        """A fejlődés-riport nyomtatható HTML-ben — a /scouting/trend
        törzsével azonos bemenettel."""
        from fastapi.responses import HTMLResponse
        older_body = body.get("older")
        newer_body = body.get("newer")
        if not older_body or not newer_body:
            raise HTTPException(status_code=400,
                                detail="older and newer required")
        older = _combined_report(older_body)
        newer = _combined_report(newer_body)
        from ..pipeline.report_html import trend_report_html
        return HTMLResponse(content=trend_report_html(
            trend_report(older, newer)))

    @app.post("/scouting/matchup")
    def scouting_matchup(body: dict):
        """Meccsterv-illesztés: a SAJÁT és az ELLENFÉL profiljának
        keresztezése páros-specifikus tanácsokká.

        Törzs: {"own": {"items": [...]}, "opp": {"items": [...]}} — az
        items formátuma azonos a /scouting-éval."""
        own_body = body.get("own")
        opp_body = body.get("opp")
        if not own_body or not opp_body:
            raise HTTPException(status_code=400,
                                detail="own and opp required")
        from ..pipeline.scouting import matchup_plan
        own = _combined_report(own_body)
        opp = _combined_report(opp_body)
        return {"plan": matchup_plan(own, opp),
                "own_team": own.team_name, "opp_team": opp.team_name}

    @app.post("/scouting/export")
    def combined_scouting_export(body: dict):
        """Az egyesített felderítés NYOMTATHATÓ HTML-je (mint az
        egy-meccses export). Opcionális "own" kulccsal a meccsterv-
        illesztés is bekerül a jelentésbe."""
        from fastapi import Response
        rep = _combined_report(body)
        matchup = None
        own_body = body.get("own")
        if own_body:
            try:
                from ..pipeline.scouting import matchup_plan
                matchup = matchup_plan(_combined_report(own_body), rep)
            except Exception:
                matchup = None
        html = scouting_report_html(rep, matchup=matchup)
        return Response(content=html, media_type="text/html; charset=utf-8")

    @app.get("/matches/{match_id}/coaching")
    def get_coaching(match_id: str, t: int = -1):
        """Élő edzői javaslatok. `t` nélkül a teljes meccs frame-enkénti idővonala
        (a kliens ebbe indexel lejátszáskor); `t`-vel egyetlen frame javaslatai."""
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        cfg = TacticsConfig()
        if t < 0:
            return {"per_frame": coaching_timeline(match, cfg)}
        if t >= len(match.frames):
            raise HTTPException(status_code=400, detail="t out of range")
        fps = match.meta.fps if match.meta.fps > 0 else 25.0
        prev = match.frames[t - 1] if t > 0 else None
        sugg = suggest_for_frame(match.frames[t], cfg, prev_frame=prev, fps=fps)
        return {"t": t, "suggestions": [vars(s) for s in sugg]}

    @app.get("/matches/{match_id}/setplays")
    def get_setplays(match_id: str, threshold: float = 0.15):
        """Figura-felismerés: hány visszatérő figurát játszottak és milyen
        gyakorisággal (a támadások mozgás-mintázatainak klaszterezéséből)."""
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        r = discover_setplays(match, threshold=threshold)
        from ..pipeline.setplays import setplay_efficiency
        return {
            "attacks": r.attacks,
            "num_figures": r.num_figures,
            "figure_sizes": r.figure_sizes,
            "labels": r.labels,
            "efficiency": setplay_efficiency(match, threshold=threshold),
        }

    @app.get("/matches/{match_id}/events")
    def get_events(match_id: str):
        """Felismert események (passz, lövés, gól, labdaeladás) + összegzés."""
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        events = detect_events(match)
        from ..pipeline.event_detection import (assist_network, pass_network,
                                                shot_speeds)
        return {
            "counts": event_counts(match),
            "assist_network": assist_network(match),
            "pass_network": pass_network(match),
            "shot_speeds": shot_speeds(match),
            "events": [
                {"t": e.t, "type": e.type.value, "team": e.team.value,
                 "player_id": e.player_id, "detail": e.detail}
                for e in events
            ],
        }

    @app.get("/matches/{match_id}/players/{player_id}/decisions")
    def get_player_decisions(match_id: str, player_id: int):
        """Egy játékos passz-döntései: kihez passzol és mennyire optimálisan."""
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        r = analyze_player_decisions(match, player_id)
        return {
            "player_id": r.player_id,
            "passes": r.passes,
            "pass_distribution": r.pass_distribution,
            "optimal_rate": r.optimal_rate,
            "avg_value_gap": r.avg_value_gap,
        }

    @app.post("/matches/{match_id}/simulate-setplay")
    def simulate(match_id: str, body: dict, defending: str = "away"):
        """Az edző figuráját lejátssza a meccsből TANULT védelem ellen.

        A meccsből megtanuljuk a `defending` csapat védekezési stílusát, majd a
        kérés törzsében kapott figurát (attackers + ball_carrier) lejátsszuk ellene.
        Visszaadja a szimulált Tracking-et, a kiértékelést és a tanult modellt.
        """
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        try:
            team = Team(defending)
        except ValueError:
            raise HTTPException(status_code=400, detail="defending must be 'home' or 'away'")

        model = DefenseModel.learn(match, team)
        try:
            attackers = [[(float(p[0]), float(p[1])) for p in path] for path in body["attackers"]]
            setplay = SetPlay(attackers=attackers, ball_carrier=list(body["ball_carrier"]))
        except (KeyError, TypeError, IndexError, ValueError):
            raise HTTPException(status_code=400, detail="invalid setplay body")

        sim = simulate_setplay(setplay, model)
        return {
            "defense_model": vars(model),
            "evaluation": evaluate_setplay(sim),
            "tracking": sim.to_dict(),
        }

    @app.post("/matches/demo")
    def create_demo_match(body: dict | None = None):
        """DEMÓ meccs létrehozása videó nélkül — az első kipróbáláshoz.

        A beépített szimulátorral készít egy valósághű, pásztázó-kamerás meccset
        (mért + becsült pozíciók, labda), és beteszi a könyvtárba — így a
        felhasználó a teljes appot (elemzés, felderítés, export) azonnal
        kipróbálhatja, mielőtt videót töltene fel."""
        import uuid
        from ..sim import (append_demo_episodes, simulate_ground_truth,
                           simulate_with_panning_camera)

        body = body or {}
        seconds = float(body.get("seconds", 30.0))
        seconds = max(5.0, min(120.0, seconds))  # ésszerű keretek közt
        seed = int(body.get("seed", 0))

        ground = simulate_ground_truth(duration_s=seconds, fps=25.0, seed=seed)
        match = simulate_with_panning_camera(ground)
        # Forgatókönyv-epizódok a végére: gól-sorozat, hetes, csere,
        # időkérés — így a demóban az ÖSSZES elemző réteg mutat valamit.
        append_demo_episodes(match)
        match.meta.match_id = f"demo-{uuid.uuid4().hex[:8]}"
        match.meta.home_team = "Demó Hazai"
        match.meta.away_team = "Demó Vendég"
        _put_match(match)
        return {"match_id": match.meta.match_id,
                "num_frames": len(match.frames)}

    # ---- Figura-könyvtár (playbook) ----------------------------------------
    # Az edző megrajzolt figurái név szerint mentve, lemezen (data/playbook/).
    # Formátum: {"id", "name", "attackers": [ [[x0,y0],[x1,y1]], ... ]} — játékosonként
    # a kulcs-pozíciók (kezdő+vég, méterben). Egyszerű fájl-tár, adatbázis később.
    _playbook_dir = data_root() / "data" / "playbook"
    _playbook_dir.mkdir(parents=True, exist_ok=True)

    def _play_path(play_id: str) -> Path:
        import re
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", play_id) or "play"
        return _playbook_dir / f"{safe}.json"

    @app.get("/playbook")
    def list_plays():
        """A mentett figurák listája (id + név + játékos-szám)."""
        out = []
        for f in sorted(_playbook_dir.glob("*.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                out.append({"id": d.get("id"), "name": d.get("name", "névtelen"),
                            "players": len(d.get("attackers", []))})
            except Exception:
                continue  # sérült fájlt kihagyunk
        return {"plays": out}

    @app.get("/playbook/{play_id}")
    def get_play(play_id: str):
        """Egy mentett figura teljes tartalma (a tervező ezt tölti vissza)."""
        p = _play_path(play_id)
        if not p.exists():
            raise HTTPException(status_code=404, detail="play not found")
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            raise HTTPException(status_code=500, detail="corrupt play file")

    @app.post("/playbook")
    def save_play(body: dict):
        """Figura mentése. Törzs: {"name": ..., "attackers": [[[x,y],[x,y]],...]}.

        Validáció: 1..7 játékos, játékosonként legalább 2 kulcs-pozíció, minden
        koordináta szám. Visszaadja a generált azonosítót."""
        import uuid
        name = str(body.get("name") or "").strip()
        attackers = body.get("attackers")
        if not name:
            raise HTTPException(status_code=400, detail="name required")
        if not isinstance(attackers, list) or not (1 <= len(attackers) <= 7):
            raise HTTPException(status_code=400, detail="attackers must be 1..7 players")
        try:
            attackers = [[[float(p[0]), float(p[1])] for p in path] for path in attackers]
        except (TypeError, IndexError, ValueError):
            raise HTTPException(status_code=400, detail="invalid coordinates")
        if any(len(path) < 2 for path in attackers):
            raise HTTPException(status_code=400, detail="each player needs >=2 keyframes")

        play_id = uuid.uuid4().hex[:10]
        data = {"id": play_id, "name": name, "attackers": attackers}
        _play_path(play_id).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"id": play_id, "name": name}

    @app.delete("/playbook/{play_id}")
    def delete_play(play_id: str):
        """Figura törlése a könyvtárból."""
        p = _play_path(play_id)
        if not p.exists():
            raise HTTPException(status_code=404, detail="play not found")
        p.unlink()
        return {"deleted": play_id}

    @app.get("/matches/{match_id}/playbook-match")
    def playbook_match(match_id: str, team: str = "", threshold: float = 0.2):
        """A meccs támadásainak hozzárendelése a MENTETT figurákhoz.

        "Melyik ismert figurát játsszák és hányszor" — a felderítés kiegészítése.
        `team` (opcionális): csak az adott csapat támadásai; `threshold`: az
        egyezés szigorúsága (kisebb = szigorúbb)."""
        from ..pipeline.setplays import match_attacks_to_playbook
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        t = None
        if team:
            try:
                t = Team(team)
            except ValueError:
                raise HTTPException(status_code=400, detail="team must be 'home' or 'away'")
        plays = []
        for f in sorted(_playbook_dir.glob("*.json")):
            try:
                plays.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                continue
        return match_attacks_to_playbook(match, plays, TacticsConfig(),
                                         team=t, threshold=threshold)

    @app.post("/matches/fuse")
    def fuse_views(payload: dict):
        """Több nézet (külön feldolgozott meccs) egyesítése egy meccsé.

        Kérés: {"match_ids": [id1, id2, ...], "match_id": "opcionális-új-id",
        "auto_sync": true}. A nézeteknek KÖZÖS méter-térre kalibráltnak
        kell lenniük (ugyanaz a pálya). auto_sync esetén az első nézethez
        képest a többi órajel-eltolását a labda-pályából becsüljük és
        kiigazítjuk. Az eredmény új meccsként kerül a könyvtárba, és a
        teljes elemző-lánc fut rajta.

        404: ismeretlen meccs-azonosító; 400: kevesebb mint két nézet."""
        from ..pipeline.fusion import (apply_offset, estimate_clock_offset,
                                       fuse_matches)
        ids = payload.get("match_ids") or []
        if len(ids) < 2:
            raise HTTPException(status_code=400,
                                detail="legalább két nézet kell")
        views = []
        for mid in ids:
            m = _store.get(mid)
            if m is None:
                raise HTTPException(status_code=404,
                                    detail=f"match not found: {mid}")
            views.append(m)
        offsets = [0]
        if payload.get("auto_sync", True):
            synced = [views[0]]
            for v in views[1:]:
                off = estimate_clock_offset(views[0], v)
                offsets.append(off if off is not None else 0)
                synced.append(apply_offset(v, off) if off else v)
            views = synced
        else:
            offsets = [0] * len(views)
        fused = fuse_matches(views)
        new_id = payload.get("match_id") or ("fuzio-" + "-".join(ids)[:40])
        fused.meta.match_id = new_id
        _store[new_id] = fused
        try:
            _match_path(new_id).write_text(fused.to_json(indent=2),
                                           encoding="utf-8")
        except Exception:
            pass
        from ..pipeline.fusion import fusion_gain
        return {"match_id": new_id, "n_views": len(ids),
                "offsets": offsets, "frames": len(fused.frames),
                "gain": fusion_gain(views, fused)}

    # Segéd a feltöltéshez/teszteléshez: memóriába tesz ÉS lemezre tükröz.
    def _put_match(match: Match) -> None:
        _store[match.meta.match_id] = match
        try:
            _match_path(match.meta.match_id).write_text(
                match.to_json(indent=2), encoding="utf-8")
        except Exception:
            pass  # a memóriabeli tár akkor is működik, ha a lemezre írás elakad

    app.state.put_match = _put_match  # elérhetővé tesszük indítás után
    return app
