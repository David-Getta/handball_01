"""
Tesztek a játékos döntés-végpontjára (a Döntések panel játékos-modellje).

A panel a GET /matches/{id}/players/{pid}/decisions válaszából rajzolja a
helyzetenkénti profilt ("situations") és a szorított döntéseket
("pressure"). A motor-rétegek külön tesztelve vannak — itt a VÉGPONT
alakja a tét: a kliens ezeket a kulcsokat olvassa, és egy elírt kulcs
némán üres panelt adna.

Futtatás:
    python -m pytest tests/test_player_decisions_api.py
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
    Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)

_tmp = tempfile.mkdtemp(prefix="handball_playerdec_test_")


def _pl(track_id, team, x, y):
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0)


def _match(match_id="pdapi"):
    """A hazai 1-esre a vendég 11-es rálép; a 2-es szabad 6 m-es társ, a
    4-es hátul — az 1-es tízszer hátra passzol (lásd test_decisions
    _sit_match)."""
    base = {1: (30.0, 13.3), 2: (34.2, 12.5), 3: (37.0, 18.5),
            4: (26.5, 10.0)}
    frames = []
    t = 0

    def cast():
        return ([_pl(i, Team.HOME, *xy) for i, xy in base.items()]
                + [_pl(11, Team.AWAY, 31.0, 14.0),
                   _pl(12, Team.AWAY, 33.0, 8.0)])

    def hold(xy, k=3):
        nonlocal t
        for _ in range(k):
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=xy[0], y=xy[1], confidence=1.0)))
            t += 1

    for _ in range(10):
        hold((33.0, 8.0))
        hold(base[1])
        hold(base[4])
    return Match(MatchMeta(match_id=match_id, home_team="A",
                           away_team="B", fps=25), frames)


def _client():
    os.environ["HANDBALL_DATA_DIR"] = _tmp
    m = _match()
    d = Path(_tmp) / "data" / "matches"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{m.meta.match_id}.json").write_text(
        json.dumps(m.to_dict()), encoding="utf-8")
    from handball.api.app import create_app
    return TestClient(create_app()), m.meta.match_id


def test_a_dontes_vegpont_helyzetenkent_es_szoritva_is_valaszol():
    """A kiválasztott játékos helyzet-profilja és szorított döntései a
    kliens által olvasott kulcsokkal jönnek."""
    client, mid = _client()
    r = client.get(f"/matches/{mid}/players/1/decisions")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["passes"] == 10, d
    kilep = d["situations"]["kilépnek rá"]
    assert kilep["decisions"] == 10, d
    assert kilep["actions"] == {"visszajátszás": 10}, d
    assert kilep["match"] == 0, d
    assert d["pressure"] == {"press": 10, "press_best": 0,
                             "team_free_pct": None}, d


def test_dontes_nelkuli_jatekos_ures_profilt_kap():
    """Akinek nincs döntése, üres helyzet-profilt és None szorítást kap
    (nem hibát): a panel ebből írja ki, hogy nincs besorolható döntés."""
    client, mid = _client()
    d = client.get(f"/matches/{mid}/players/3/decisions").json()
    assert d["situations"] == {} and d["pressure"] is None, d
