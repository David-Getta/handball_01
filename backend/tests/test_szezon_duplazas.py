"""
Tesztek arra, hogy az összefűzött meccs DARABJAI nem duplázzák a
szezont.

Összefűzés után a darabok és az egész is a könyvtárban van (a darab
szándékosan megmarad: törölhető, külön is megnézhető). A szezon-szintű
összesítés viszont így ugyanazt a meccset KÉTSZER számolta: a #7 gólja
egyszer a darabban, egyszer az egészben — a góllövő-lista, a
szezon-mérleg és a jegyzet-lista is duplázott.

Futtatás:
    python -m pytest tests/test_szezon_duplazas.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient

from handball.models.tracking import (  # noqa: E402
    Ball, Frame, Match, MatchMeta, PlayerPosition, Team,
)


def _resz(match_id, video, n=60):
    meta = MatchMeta(match_id=match_id, home_team="Mi", away_team="Ok",
                     fps=10.0, video_path=video, date="2026-08-01")
    frames = [
        Frame(t=i, players=[
            PlayerPosition(track_id=1, team=Team.HOME,
                           x=10.0 + 0.2 * (i % 20), y=10.0,
                           jersey_number=7),
        ], ball=Ball(x=20.0, y=10.0))
        for i in range(n)
    ]
    return Match(meta, frames)


def _client(reszek):
    tmp = tempfile.mkdtemp(prefix="hb_dupla_")
    os.environ["HANDBALL_DATA_DIR"] = tmp
    d = Path(tmp) / "data" / "matches"
    d.mkdir(parents=True, exist_ok=True)
    for m in reszek:
        (d / f"{m.meta.match_id}.json").write_text(
            json.dumps(m.to_dict()), encoding="utf-8")
    from handball.api.app import create_app
    return TestClient(create_app())


def test_a_darabok_nem_duplazzak_a_jatekos_gorbet():
    """A #7 görbéjén az összefűzés után EGY pont van (az egész meccs),
    nem három (két darab + az egész)."""
    c = _client([_resz("d1", "/v/a.mp4"), _resz("d2", "/v/b.mp4")])
    c.post("/matches/merge", json={"ids": ["d1", "d2"],
                                   "match_id": "egesz"})
    pontok = c.get("/players/trend",
                   params={"team": "Mi", "jersey": 7}).json()["points"]
    assert [p["match_id"] for p in pontok] == ["egesz"], pontok


def test_a_konyvtar_lista_tovabbra_is_mindent_mutat():
    """A kezelő nézet NEM szűr: a darab törölhető, újrafeldolgozható —
    ahhoz látni kell. A szűrés csak a SZÁMOLÁSé."""
    c = _client([_resz("d1", "/v/a.mp4"), _resz("d2", "/v/b.mp4")])
    c.post("/matches/merge", json={"ids": ["d1", "d2"],
                                   "match_id": "egesz"})
    nevek = {m["match_id"] for m in c.get("/matches").json()["matches"]}
    assert nevek == {"d1", "d2", "egesz"}


def test_a_jegyzet_lista_nem_duplaz():
    """Az összefűzött meccs a darabok jegyzeteinek MÁSOLATÁT viszi —
    ha a lista a darabokat is mutatná, minden jegyzet kétszer
    szerepelne, és a törlés is zavaros lenne (melyiket törli?)."""
    c = _client([_resz("d1", "/v/a.mp4"), _resz("d2", "/v/b.mp4")])
    c.post("/matches/d1/notes", json={"frame": 3, "text": "fontos"})
    c.post("/matches/merge", json={"ids": ["d1", "d2"],
                                   "match_id": "egesz"})
    jegyzetek = c.get("/library/notes").json()["notes"]
    assert len(jegyzetek) == 1, jegyzetek
    assert jegyzetek[0]["match_id"] == "egesz"


def test_osszefuzes_nelkul_semmi_nem_valtozik():
    """ŐR: aki nem fűz össze, annak a szezonja változatlan — a szűrő
    csak a darabokat veszi ki, nem az önálló meccseket."""
    c = _client([_resz("m1", "/v/a.mp4"), _resz("m2", "/v/b.mp4")])
    pontok = c.get("/players/trend",
                   params={"team": "Mi", "jersey": 7}).json()["points"]
    assert {p["match_id"] for p in pontok} == {"m1", "m2"}
