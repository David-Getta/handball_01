"""
Tesztek a KERET-VISZONYÍTÁSRA a játékos-görbén (/players/trend).

A nyers "4,2 kilométer" a játékosnak semmit nem mond: sokat futott vagy
keveset? A keret-átlaghoz és a helyezéshez mérve viszont döntés lesz
belőle. Két csapda van benne, és mindkettőre van itt teszt:

  - trackenként összegezni HAZUDIK: a megszakadt követés két embernek
    látszik, és lenyomja a keret-átlagot (ezért mezszám szerint megyünk),
  - nyers métert hasonlítani HAZUDIK: a végig játszó irányító és a
    tizenöt percet kapó szélső nem összemérhető (ezért percre vetítünk).

Futtatás:
    python -m pytest tests/test_squad_compare.py
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

from handball.sim.match_simulator import simulate_ground_truth  # noqa: E402

_tmp = tempfile.mkdtemp(prefix="handball_squad_test_")


def _client(duration_s=150.0, fps=12.0):
    """Elég HOSSZÚ meccs, hogy a keret-viszonyítás küszöbe teljesüljön.

    A rövid szimuláción mindenki a küszöb alatt marad — és az is helyes
    viselkedés (lásd a kevés-minta tesztet).
    """
    os.environ["HANDBALL_DATA_DIR"] = _tmp
    m = simulate_ground_truth(duration_s=duration_s, fps=fps, seed=5)
    mezek = set()
    for f in m.frames:
        for p in f.players:
            p.jersey_number = (p.track_id % 14) + 1
            if p.team.value == "home":
                mezek.add(p.jersey_number)
    d = Path(_tmp) / "data" / "matches"
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("*"):
        old.unlink()
    (d / f"{m.meta.match_id}.json").write_text(
        json.dumps(m.to_dict()), encoding="utf-8")
    from handball.api.app import create_app
    return TestClient(create_app()), m.meta.home_team, sorted(mezek)


def _pont(client, team, jersey):
    r = client.get("/players/trend", params={"team": team, "jersey": jersey})
    assert r.status_code == 200
    pts = r.json()["points"]
    assert pts, "nincs pont a görbén"
    return pts[0]


def test_a_jatekos_latja_hol_tart_a_kereten_belul():
    client, team, mezek = _client()
    p = _pont(client, team, mezek[0])
    assert p["distance_per_min"] is not None
    assert p["team_distance_per_min"] is not None
    assert p["squad_size"] >= 5
    assert 1 <= p["distance_rank"] <= p["squad_size"]


def test_a_helyezes_egyezik_a_sajat_es_a_keret_ertekevel():
    """ŐR: a helyezés és az átlag NE két külön számolásból jöjjön.

    Ha az egyik trackenként, a másik mezszám szerint összegezne, a
    játékos azt látná, hogy ő az átlag fölött van — de csak a
    hetedik. Ez pont az a fajta ellentmondás, amitől az egész lapot
    nem hiszi el.
    """
    client, team, mezek = _client()
    sorok = []
    for mez in mezek:
        r = client.get("/players/trend",
                       params={"team": team, "jersey": mez}).json()
        if not r["points"]:
            continue
        p = r["points"][0]
        if p["distance_per_min"] is not None and p["distance_rank"]:
            sorok.append((mez, p))
    assert len(sorok) >= 5

    # Minden sor UGYANAZT a keret-átlagot és létszámot látja.
    atlagok = {p["team_distance_per_min"] for _m, p in sorok}
    letszamok = {p["squad_size"] for _m, p in sorok}
    assert len(atlagok) == 1, atlagok
    assert len(letszamok) == 1, letszamok

    # A helyezések a saját méter/perc szerinti sorrendet adják.
    szamitott = sorted(sorok, key=lambda e: -e[1]["distance_per_min"])
    for helyezes, (_mez, p) in enumerate(szamitott, start=1):
        assert p["distance_rank"] == helyezes, (helyezes, p)


def test_keves_jatszott_ember_eseten_nincs_viszonyitas():
    """Kevés mintánál None ítélet — sose hallgatólagos nulla.

    Rövid felvételen mindenki a játékidő-küszöb alatt marad; ilyenkor a
    keret-átlag félrevezetne (két emberből nincs "keret"), ezért a
    mezők üresek maradnak, és a felület el sem kezdi mutatni.
    """
    client, team, mezek = _client(duration_s=20.0, fps=25.0)
    p = _pont(client, team, mezek[0])
    assert p["team_distance_per_min"] is None
    assert p["distance_rank"] is None
    assert p["squad_size"] is None
    # A SAJÁT méter/perc ettől még kiszámolható — az nem viszonyítás.
    assert p["distance_per_min"] is not None


def test_a_kuszobok_modul_szintuek_es_dokumentaltak():
    """ŐR: a játékidő-küszöb IDŐTARTAM, tehát másodpercben.

    Kockában megadva a minőségi profiltól függően háromszoros valós
    időt jelentene (a termék minden 3. kockát dolgozza fel).
    """
    src = (Path(__file__).resolve().parents[1] / "handball" / "api"
           / "app.py").read_text(encoding="utf-8")
    assert "SQUAD_MIN_PLAY_S" in src
    assert "SQUAD_MIN_PLAYERS" in src
    assert "f_ / fps >= SQUAD_MIN_PLAY_S" in src, (
        "a játékidő-küszöböt nem az fps-ből számoljuk")
