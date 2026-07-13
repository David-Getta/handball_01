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

    def _load_store_from_disk() -> int:
        """A lemezen lévő meccsek betöltése a memóriába (indulás + könyvtár-
        visszaállítás után). A jegyzet/mezszám/roster kísérőfájlokat a nevük
        különbözteti meg (*.notes.json stb.) — azok nem meccsek."""
        loaded = 0
        for f in sorted(_data_dir.glob("*.json")):
            if any(f.name.endswith(s) for s in
                   (".notes.json", ".jerseys.json", ".roster.json")):
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

        job_id = uuid.uuid4().hex[:12]
        match_id = body.get("match_id") or f"video-{job_id}"
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

            # Megszakítás: a haladás-visszahívás minden hívásnál megnézi a
            # job "cancel" jelzőjét — ha be van állítva, kivétellel kilépünk
            # a feldolgozásból (a detektáló ciklus kockánként hívja, így a
            # leállás másodperceken belül megtörténik).
            class _Cancelled(Exception):
                pass

            def cb(stage, prog, msg):
                if job.get("cancel"):
                    raise _Cancelled()
                job["stage"] = stage
                job["progress"] = round(float(prog), 3)
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
                )
                app.state.put_match(match)
                job["status"] = "done"
                job["progress"] = 1.0
                job["message"] = f"kész ({len(match.frames)} frame)"
            except _Cancelled:
                job["status"] = "cancelled"
                job["message"] = "megszakítva"
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
        """Egy futó feldolgozás megszakítása. A leállítás nem azonnali: a
        feldolgozó a következő képkockánál veszi észre a jelzőt (másodpercek)."""
        job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
        if job["status"] == "queued":
            # Sorban álló munka: azonnal megszakítható (el sem indult).
            job["status"] = "cancelled"
            job["message"] = "megszakítva (a sorból)"
        elif job["status"] == "running":
            job["cancel"] = True
            job["message"] = "megszakítás folyamatban…"
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
        """A meccs metaadatainak frissítése (jelenleg: csapatnevek átírása).

        Törzs: {"home_team": "...", "away_team": "..."} — bármelyik elhagyható.
        A módosítás a lemezre is kiíródik, így újraindítás után is megmarad."""
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        home = body.get("home_team")
        away = body.get("away_team")
        if home is None and away is None:
            raise HTTPException(status_code=400, detail="home_team or away_team required")
        if home is not None:
            match.meta.home_team = str(home).strip() or match.meta.home_team
        if away is not None:
            match.meta.away_team = str(away).strip() or match.meta.away_team
        _put_match(match)  # memóriába + lemezre (perzisztencia)
        return {"match_id": match_id,
                "home_team": match.meta.home_team, "away_team": match.meta.away_team}

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
        except Exception:
            pass
        return {"deleted": match_id}

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
        from ..pipeline.quality import compute_quality_report
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        return compute_quality_report(match)

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

        lines = ["Játékos;Csapat;Track-ek;Táv (m);Átl. sebesség (m/s);"
                 "Max sebesség (km/h);Sprintek;Sprint táv (m);"
                 "Séta (mp);Kocogás (mp);Futás (mp);Sprint (mp);"
                 "Mért kocka;Becsült kocka"]
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

                def cb(done, total, msg):
                    job["progress"] = round(done / max(1, total), 3)
                    job["message"] = msg

                res = export_event_clips(match, ev, types, out_dir,
                                         progress_cb=cb)
                job["status"] = "done"
                job["progress"] = 1.0
                job["message"] = f"kész: {res.count} klip"
            except Exception as e:
                job["status"] = "error"
                job["error"] = str(e)
                job["message"] = f"hiba: {e}"

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
            points.append({
                "match_id": match.meta.match_id,
                "date": match.meta.date,
                "opponent": (match.meta.away_team if side == Team.HOME
                             else match.meta.home_team),
                "distance_m": round(distance, 1),
                "top_speed_ms": round(top, 2),
                "sprint_count": sprints,
                "minutes": round(frames / fps / 60.0, 1),
            })
        points.sort(key=lambda p: (p["date"] or "", p["match_id"]))
        return {"team": team, "jersey": jersey, "points": points}

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
        goals_home = goals_away = shots = 0
        try:
            for e in detect_shots(m):
                if e.type == EventType.GOAL:
                    if e.team == Team.HOME:
                        goals_home += 1
                    else:
                        goals_away += 1
                elif e.type == EventType.SHOT:
                    shots += 1
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
        out = {
            "match_id": m.meta.match_id,
            "home_team": m.meta.home_team,
            "away_team": m.meta.away_team,
            "date": m.meta.date,
            "duration_s": round(len(m.frames) / fps, 1),
            "goals_home": goals_home,
            "goals_away": goals_away,
            "shots": shots,
            "distance_m": round(distance_m, 1),
            "sprints": sprints,
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
            "sprints": sum(d["sprints"] for d in per),
            "distance_km": round(sum(d["distance_m"] for d in per) / 1000.0, 2),
            "per_match": per,
        }

    @app.get("/matches/{match_id}/goalkeepers")
    def get_goalkeeper_stats(match_id: str):
        """Kapus-teljesítmény: kapott kapura tartó lövések, védések,
        kapott gólok (zóna-bontással) és védés-hatékonyság csapatonként.
        Üres szótár, ha a meccsen nincs kapus-jelölés."""
        from ..pipeline.goalkeeper import goalkeeper_stats
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        return {"goalkeepers": goalkeeper_stats(match)}

    @app.get("/matches/{match_id}/attacks")
    def get_attacks(match_id: str):
        """Támadás-szakaszok típus-címkével (lerohanás / gyors indítás /
        felállt / 7 a 6) + csapatonkénti támadás-mix százalékban."""
        from ..pipeline.attack_types import attack_mix, classify_attacks
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        return {"attacks": classify_attacks(match),
                "mix": attack_mix(match)}

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
        return {team.value: vars(compute_team_summary(match, team))
                for team in (Team.HOME, Team.AWAY)}

    @app.get("/matches/{match_id}/tactics")
    def get_tactics(match_id: str):
        """Taktikai összkép (csapat-stílusprofil): fázis-megoszlás, csapatonkénti
        leggyakoribb védekezési forma, és tempó-metrikák."""
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        return team_style_profile(match)

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
        html = scouting_report_html(scout_team(match, t, TacticsConfig()),
                                    playbook_match=pm)
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

    @app.post("/scouting/export")
    def combined_scouting_export(body: dict):
        """Az egyesített felderítés NYOMTATHATÓ HTML-je (mint az egy-meccses export)."""
        from fastapi import Response
        html = scouting_report_html(_combined_report(body))
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
        return {
            "attacks": r.attacks,
            "num_figures": r.num_figures,
            "figure_sizes": r.figure_sizes,
            "labels": r.labels,
        }

    @app.get("/matches/{match_id}/events")
    def get_events(match_id: str):
        """Felismert események (passz, lövés, gól, labdaeladás) + összegzés."""
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        events = detect_events(match)
        return {
            "counts": event_counts(match),
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
        from ..sim import simulate_ground_truth, simulate_with_panning_camera

        body = body or {}
        seconds = float(body.get("seconds", 30.0))
        seconds = max(5.0, min(120.0, seconds))  # ésszerű keretek közt
        seed = int(body.get("seed", 0))

        ground = simulate_ground_truth(duration_s=seconds, fps=25.0, seed=seed)
        match = simulate_with_panning_camera(ground)
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
