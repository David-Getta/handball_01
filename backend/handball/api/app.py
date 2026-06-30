"""
HTTP API — a Flutter-kliens ezen keresztül kapja a Tracking-et és a statisztikát.

A backend és a (Flutter) kliens KÜLÖN válik: a nehéz feldolgozás itt, szerveren
fut, a kliens csak a kész JSON-t kéri le és jeleníti meg (lásd docs/ARCHITECTURE.md
"Kliens–szerver szétválasztás").

Ez a modul a FastAPI-t LUSTÁN használja: az importja egy függvényben van, hogy a
csomag a FastAPI telepítése nélkül is importálható és tesztelhető legyen. A
szervert a `create_app()`-ből indítjuk (lásd scripts/serve.py vagy uvicorn).

Végpontok (MVP):
- GET /health                      → életjel.
- GET /matches/{match_id}          → a Match (Tracking) JSON-ja.
- GET /matches/{match_id}/stats    → játékosonkénti statisztika.

Az adattárolás itt egyelőre memóriában/placeholder; később Postgres + objektumtár.
"""

from __future__ import annotations

from ..models.tracking import Match, MatchMeta, Team
from ..pipeline.pipeline import summarize
from ..pipeline.analytics import compute_team_heatmap, compute_team_summary
from ..pipeline.tactics import team_style_profile
from ..pipeline.setplays import discover_setplays
from ..pipeline.decisions import analyze_player_decisions


def create_app():
    """Létrehozza és visszaadja a FastAPI alkalmazást.

    A FastAPI importja szándékosan ITT van (nem a modul tetején), hogy a csomag
    többi része függőség nélkül is működjön. A szerver indításához:
        uvicorn "handball.api.app:create_app" --factory
    """
    from fastapi import FastAPI, HTTPException

    app = FastAPI(title="Handball Analysis API", version="0.1.0")

    # Ideiglenes, memóriabeli tár (match_id -> Match). Később adatbázis.
    _store: dict[str, Match] = {}

    @app.get("/health")
    def health():
        """Életjel — a kliens ezzel ellenőrzi, hogy a backend elérhető."""
        return {"status": "ok"}

    @app.get("/matches/{match_id}")
    def get_match(match_id: str):
        """Visszaadja a kért meccs Tracking JSON-ját (ezt rajzolja ki a kliens)."""
        match = _store.get(match_id)
        if match is None:
            raise HTTPException(status_code=404, detail="match not found")
        return match.to_dict()

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

    # Segéd a feltöltéshez/teszteléshez (később a pipeline tölti fel az eredményt).
    def _put_match(match: Match) -> None:
        _store[match.meta.match_id] = match

    app.state.put_match = _put_match  # elérhetővé tesszük indítás után
    return app
