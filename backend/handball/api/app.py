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
- DELETE /matches/{match_id}        → meccs törlése (memória + lemez).
- GET  /matches/{match_id}/stats    → játékosonkénti statisztika.
- GET  /matches/{match_id}/coaching → élő edzői javaslatok (idővonal vagy egy frame).
- GET  /matches/{match_id}/scouting → ellenfél-felderítő jelentés egy csapatról.
- POST /scouting                     → több meccsből egyesített felderítés.

Az adattárolás itt egyelőre memóriában/placeholder; később Postgres + objektumtár.
"""

from __future__ import annotations

from ..models.tracking import Match, MatchMeta, Team
from ..pipeline.pipeline import summarize
from ..pipeline.analytics import compute_team_heatmap, compute_team_summary
from ..pipeline.tactics import team_style_profile, TacticsConfig
from ..pipeline.coaching import suggest_for_frame, coaching_timeline
from ..pipeline.scouting import scout_team, combine_reports, report_to_dict
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
    _data_dir = Path(__file__).resolve().parents[2] / "data" / "matches"
    _data_dir.mkdir(parents=True, exist_ok=True)

    def _match_path(match_id: str) -> Path:
        # Fájlnév-fertőtlenítés (path traversal ellen): csak biztonságos karakterek.
        import re
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", match_id) or "match"
        return _data_dir / f"{safe}.json"

    # Indításkor betöltjük a korábban lementett meccseket a memóriába.
    for _f in sorted(_data_dir.glob("*.json")):
        try:
            _m = Match.from_json(_f.read_text(encoding="utf-8"))
            _store[_m.meta.match_id] = _m
        except Exception:
            pass  # sérült fájlt átugrunk, ne akadályozza az indulást

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
        uploads = Path(__file__).resolve().parents[2] / "uploads"
        uploads.mkdir(exist_ok=True)
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
        weights, stride, max, imgsz, conf, start, calib ([[x,y],...] 4 sarok), match_id.
        A haladást a GET /jobs/{job_id} adja vissza (stage, progress, message).
        """
        import threading
        import uuid

        path = body.get("path")
        if not path:
            raise HTTPException(status_code=400, detail="path required")

        job_id = uuid.uuid4().hex[:12]
        match_id = body.get("match_id") or f"video-{job_id}"
        job = {"job_id": job_id, "match_id": match_id, "status": "running",
               "stage": "A", "progress": 0.0, "message": "indítás", "error": None}
        _jobs[job_id] = job

        def run():
            # A nehéz feldolgozó a scripts.process_video-ban van; a backend/ mappát
            # biztosítjuk a sys.path-en, hogy a szerver bárhonnan indítva megtalálja.
            import sys
            from pathlib import Path
            backend_dir = str(Path(__file__).resolve().parents[2])
            if backend_dir not in sys.path:
                sys.path.insert(0, backend_dir)
            from scripts.process_video import process

            def cb(stage, prog, msg):
                job["stage"] = stage
                job["progress"] = round(float(prog), 3)
                job["message"] = msg

            try:
                match = process(
                    path, None,
                    weights=body.get("weights"),
                    stride=int(body.get("stride", 3)),
                    max_frames=int(body.get("max", 400)),
                    imgsz=int(body.get("imgsz", 1280)),
                    conf=float(body.get("conf", 0.20)),
                    calib_corners=body.get("calib"),
                    start=int(body.get("start", 0)),
                    progress_cb=cb, match_id=match_id,
                    estimate=bool(body.get("estimate", True)),
                )
                app.state.put_match(match)
                job["status"] = "done"
                job["progress"] = 1.0
                job["message"] = f"kész ({len(match.frames)} frame)"
            except Exception as e:  # a hibát a kliensnek is megmutatjuk
                job["status"] = "error"
                job["error"] = str(e)
                job["message"] = f"hiba: {e}"

        threading.Thread(target=run, daemon=True).start()
        return {"job_id": job_id, "match_id": match_id}

    @app.get("/jobs/{job_id}")
    def job_status(job_id: str):
        """Egy feldolgozási munka állapota (stage/progress/message/status/error)."""
        job = _jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="job not found")
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

    @app.delete("/matches/{match_id}")
    def delete_match(match_id: str):
        """Törli a meccset a memóriából és a lemezről (könyvtár-karbantartás)."""
        if match_id not in _store:
            raise HTTPException(status_code=404, detail="match not found")
        del _store[match_id]
        try:
            _match_path(match_id).unlink(missing_ok=True)
        except Exception:
            pass
        return {"deleted": match_id}

    @app.get("/matches/{match_id}/stats")
    def get_stats(match_id: str):
        """Visszaadja a meccs játékosonkénti statisztikáit (táv, sebesség)."""
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        stats = summarize(match)
        # A dataclass-okat egyszerű szótárrá alakítjuk a JSON-válaszhoz.
        return {str(tid): vars(s) for tid, s in stats.items()}

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

    @app.post("/scouting")
    def combined_scouting(body: dict):
        """TÖBB meccsből egyesített felderítő jelentés egy csapatról.

        Törzs: {"items": [{"match_id": "...", "team": "home"|"away"}, ...]}.
        Több meccs adja a valós, zajmentes profilt (a számokat átlagolja/összegzi).
        """
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
        return report_to_dict(combine_reports(reports))

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
