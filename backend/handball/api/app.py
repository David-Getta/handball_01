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

from ..models.tracking import Match, MatchMeta
from ..pipeline.pipeline import summarize


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

    # Segéd a feltöltéshez/teszteléshez (később a pipeline tölti fel az eredményt).
    def _put_match(match: Match) -> None:
        _store[match.meta.match_id] = match

    app.state.put_match = _put_match  # elérhetővé tesszük indítás után
    return app
