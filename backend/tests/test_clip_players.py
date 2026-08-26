"""
Tesztek a klip-válogatás MEZSZÁM-szűrésére (a játékos saját videója).

A klipcsomag eddig csak csapat-szintű volt: a #7 a tizennyolc emberes
gólvideóból kereste ki magát. Az edzés előtti öt percben ez nem
történik meg — a szűrés ezért a termék, nem a kényelem.

A végpont-oldalt külön kell tesztelni: a motor jól szűr, de a
klip-munkás korábban `{"t","type","team"}` alakú szótárakat épített,
player_id NÉLKÜL — a szűrés így NÉMÁN mindenkit kidobott volna, és a
motor tesztjei ettől még zöldek maradnak (azok a saját alakjukat
adják be).

Futtatás:
    python -m pytest tests/test_clip_players.py
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

_tmp = tempfile.mkdtemp(prefix="handball_clipplayers_test_")


def _client():
    os.environ["HANDBALL_DATA_DIR"] = _tmp
    m = simulate_ground_truth(duration_s=20, fps=25.0, seed=3)
    # Mezszámok: enélkül a szűrés semmit nem találna — és pont ez az
    # eset, amiről a felületnek is szólnia kell.
    for f in m.frames:
        for p in f.players:
            p.jersey_number = (p.track_id % 14) + 1
    d = Path(_tmp) / "data" / "matches"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{m.meta.match_id}.json").write_text(
        json.dumps(m.to_dict()), encoding="utf-8")
    from handball.api.app import create_app
    return TestClient(create_app()), m.meta.match_id


def test_a_vegpont_megmondja_kihez_van_jelenet():
    """A felület nem találgathat: csak MŰKÖDŐ mezszámot kínálhat fel.

    Egy kiosztatlan (vagy esemény nélküli) szám némán üres zip-et adna
    — a felajánlott, de működésképtelen kapcsoló rosszabb a hiányánál.
    """
    client, mid = _client()
    r = client.get(f"/matches/{mid}/clip-players")
    assert r.status_code == 200
    sorok = r.json()["players"]
    assert sorok, "egyetlen játékoshoz sem köthető jelenet"
    for s in sorok:
        assert isinstance(s["jersey"], int)
        assert s["team"] in ("home", "away")
        assert s["team_name"]
        assert s["total"] >= 1
        assert sum(s["counts"].values()) == s["total"]
    # Csökkenő darabszám: a legtöbb jelenettel bíró ember elöl.
    assert [s["total"] for s in sorok] == sorted(
        (s["total"] for s in sorok), reverse=True)


def test_ismeretlen_meccs_404():
    client, _mid = _client()
    assert client.get("/matches/nincs-ilyen/clip-players").status_code == 404


def test_a_klip_munkas_atadja_a_mezszamot_a_motornak():
    """ŐR a NÉMA MEZŐNÉV ellen.

    Ez a teszt a VALÓDI klip-munkást futtatja (nem kitalált
    esemény-szótárakat), és megnézi, hogy a mezszám-szűrés tényleg
    kevesebb jelenetet enged át, mint a szűretlen kérés. Ha a munkás
    elfelejti a player_id-t az esemény-szótárban, a szűrés némán
    NULLÁRA szűkít — a motor tesztjei ettől még zöldek.
    """
    client, mid = _client()
    sorok = client.get(f"/matches/{mid}/clip-players").json()["players"]
    assert sorok
    mez = sorok[0]["jersey"]

    # A vágás videót igényel; a motort ezért elkapjuk, és CSAK azt
    # nézzük meg, milyen eseménylistát és mezszámot kapott.
    latott: dict = {}

    def _fake(match, events, types, out_dir, progress_cb=None,
              jerseys=None):
        latott["events"] = events
        latott["jerseys"] = jerseys
        raise RuntimeError("teszt: itt megállunk")

    import handball.pipeline.clips as clips_mod
    valodi = clips_mod.export_event_clips
    clips_mod.export_event_clips = _fake
    try:
        r = client.post(f"/matches/{mid}/clips/export",
                        json={"types": ["goal", "shot"], "jerseys": [mez]})
        assert r.status_code == 200
        job_id = r.json()["job_id"]
        for _ in range(200):
            job = client.get(f"/jobs/{job_id}").json()
            if job["status"] in ("done", "error"):
                break
    finally:
        clips_mod.export_event_clips = valodi

    assert latott.get("jerseys") == {mez}
    ev = latott.get("events") or []
    assert ev, "a munkás egyetlen eseményt sem adott át"
    # A LÉNYEG: az esemény tudja, kihez tartozik.
    assert all("player_id" in e for e in ev), (
        "a klip-munkás player_id nélkül adja át az eseményeket — a "
        "mezszám-szűrés így némán üres csomagot adna")
    assert any(e["player_id"] is not None for e in ev)


def test_az_elgepelt_mezszam_nem_szukiti_a_csomagot():
    """Szemét a `jerseys` listában ne váljon némán szűréssé.

    A "hetes" szöveg vagy a null nem mezszám; ha bekerülne a halmazba,
    a csomag üresen jönne ki, és az edző nem tudná, miért.
    """
    import handball.pipeline.clips as clips_mod

    client, mid = _client()
    latott: dict = {}

    def _fake(match, events, types, out_dir, progress_cb=None,
              jerseys=None):
        latott["jerseys"] = jerseys
        raise RuntimeError("teszt: itt megállunk")

    valodi = clips_mod.export_event_clips
    clips_mod.export_event_clips = _fake
    try:
        r = client.post(f"/matches/{mid}/clips/export",
                        json={"types": ["goal"],
                              "jerseys": ["hetes", None, 9, "11"]})
        job_id = r.json()["job_id"]
        for _ in range(200):
            if client.get(f"/jobs/{job_id}").json()["status"] in (
                    "done", "error"):
                break
    finally:
        clips_mod.export_event_clips = valodi

    assert latott.get("jerseys") == {9, 11}
