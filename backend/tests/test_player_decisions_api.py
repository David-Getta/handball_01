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


def test_a_jatekos_trend_meccsenkent_mutatja_a_dontes_minoseget():
    """A játékos-trend (mezszám szerint) meccsenként hozza a besorolt
    döntéseit és közülük a legjobb-opciósakat, szorítva külön is — a
    "jobban dönt-e" kérdés meccsről meccsre."""
    client, mid = _client()
    r = client.post(f"/matches/{mid}/jerseys",
                    json={"track_id": 1, "jersey": 7})
    assert r.status_code == 200, r.text
    tr = client.get("/players/trend",
                    params={"team": "A", "jersey": 7}).json()
    assert len(tr["points"]) == 1, tr
    p = tr["points"][0]
    assert p["dec_n"] == 10 and p["dec_best"] == 0, p
    assert p["dec_press"] == 10 and p["dec_press_best"] == 0, p
    # Döntés nélküli szám: a mezők None-ok (nem 0), a felület "—"-t ír.
    client.post(f"/matches/{mid}/jerseys",
                json={"track_id": 3, "jersey": 11})
    p3 = client.get("/players/trend",
                    params={"team": "A", "jersey": 11}).json()["points"][0]
    assert p3["dec_n"] is None and p3["dec_press"] is None, p3


def test_a_szezon_lap_is_viszi_a_dontes_minoseget():
    """A nyomtatott szezon-lap sem mondhat kevesebbet a képernyőnél: a
    döntés-összesítő és a meccsenkénti oszlop rajta van; döntés nélküli
    szezonban az oszlop el sem jelenik."""
    from handball.pipeline.report_html import player_season_html

    pontok = [{"match_id": "m1", "date": "2026-01-01", "opponent": "X",
               "goals": 1, "shots": 2, "minutes": 40.0,
               "distance_m": 4000.0, "top_speed_ms": 7.0,
               "sprint_count": 5, "dec_n": 12, "dec_best": 3,
               "dec_press": 8, "dec_press_best": 1},
              {"match_id": "m2", "date": "2026-01-08", "opponent": "Y",
               "goals": 0, "shots": 0, "minutes": 30.0,
               "distance_m": 3000.0, "top_speed_ms": 6.5,
               "sprint_count": 3, "dec_n": None, "dec_best": None}]
    html = player_season_html("A", 7, pontok, "Kovács", None)
    assert "Döntés: legjobb opció" in html
    assert "3/12 (25%) · szorítva 1/8" in html
    assert '<th class="num">Döntés</th>' in html
    assert '<td class="num">3/12</td>' in html
    nincs = [dict(p, dec_n=None, dec_best=None) for p in pontok]
    assert "Döntés" not in player_season_html("A", 7, nincs, "Kovács", None)


def test_az_elo_dontes_figyelo_vegpontja():
    """Az élő képernyő a /decision-alerts listát teszi időzített jelzésnek:
    kocka ("t") és szöveg kell; nem létező meccsre 404."""
    client, mid = _client()
    al = client.get(f"/matches/{mid}/decision-alerts").json()["alerts"]
    assert len(al) == 1 and al[0]["t"] > 0, al
    assert "kilépnek rájuk" in al[0]["text"], al
    assert client.get("/matches/nincs/decision-alerts").status_code == 404


def test_a_jatekos_lap_viszi_a_donteseit():
    """A kiosztható játékos-lap "Döntéseid" szakasza: helyzetenként a
    döntések, a választások és a legjobb opció aránya, szorítva külön,
    és a rossz szokásra egy tegező mondat. Döntés nélküli játékosnál a
    szakasz el sem jelenik."""
    from handball.pipeline.report_html import player_report_html

    m = _match()
    html = player_report_html(m, 1)
    assert "<h2>Döntéseid</h2>" in html
    assert "<b>Ha kilépnek rád</b>: 10 döntés — 10× visszajátszás; " \
        "a legjobb: 0/10" in html, html
    assert "0/10</div><div class=\"ml\">szorítva" in html
    assert "Ha kilépnek rád rendre a visszajátszás a választásod, pedig " \
        "a passz a 6 m-re érne többet" in html
    assert "Döntéseid" not in player_report_html(m, 3)
