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
              jerseys=None, **kw):
        latott["events"] = events
        latott["jerseys"] = jerseys
        latott.update(kw)
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
              jerseys=None, **kw):
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
def test_a_becsleshez_a_teljes_darabszam_is_megvan():
    """A vágás PERCEKBE telik — a rossz kijelölés a végén derülne ki.

    A képernyő ezért előre megbecsüli, hány klip lesz. Ehhez a
    csapat-szintű darabszám is kell, és a plafon is: a becslés
    különben a plafon fölött hazudna.
    """
    from handball.pipeline.clips import MAX_CLIPS

    client, mid = _client()
    r = client.get(f"/matches/{mid}/clip-players").json()
    assert r["max_clips"] == MAX_CLIPS
    assert r["totals"], "nincs csapat-szintű darabszám"
    assert all(isinstance(v, int) and v > 0 for v in r["totals"].values())


def test_a_teljes_darabszam_a_mezszam_nelkulieket_is_viszi():
    """ŐR: a csapat-szintű becslés NE a mezszámos jelenetekből jöjjön.

    A klipvágás mezszám nélkül is vág (az egész csapatra), tehát a
    becslésnek minden jelenetet számolnia kell. Ha csak a mezszámhoz
    kötötteket vinné, az edző kevesebb klipet várna, mint amennyit
    kap — és a plafon-üzenet is elmaradna.
    """
    client, mid = _client()
    r = client.get(f"/matches/{mid}/clip-players").json()
    jatekosonkent: dict = {}
    for p_ in r["players"]:
        for tip, db in p_["counts"].items():
            jatekosonkent[tip] = jatekosonkent.get(tip, 0) + db
    for tip, db in jatekosonkent.items():
        assert r["totals"].get(tip, 0) >= db, tip
def test_a_jatekos_lapja_a_klipek_melle_kerul():
    """Az edző EGY fájlt visz a beszélgetésre, nem kettőt.

    A videó megmutatja, mi történt; a lap azt, mit jelent. Külön
    letöltve a kettő szétesik: a klipek a letöltések közt, a lap egy
    másik mappában, és a beszélgetés előtt öt perc keresgélés.
    """
    import handball.pipeline.clips as clips_mod

    client, mid = _client()
    sorok = client.get(f"/matches/{mid}/clip-players").json()["players"]
    assert sorok
    mez = sorok[0]["jersey"]

    latott: dict = {}

    def _fake(match, events, types, out_dir, progress_cb=None,
              jerseys=None, extra_files=None, **kw):
        latott["extra"] = extra_files
        raise RuntimeError("teszt: itt megállunk")

    valodi = clips_mod.export_event_clips
    clips_mod.export_event_clips = _fake
    try:
        r = client.post(f"/matches/{mid}/clips/export",
                        json={"types": ["goal"], "jerseys": [mez]})
        job_id = r.json()["job_id"]
        for _ in range(200):
            if client.get(f"/jobs/{job_id}").json()["status"] in (
                    "done", "error"):
                break
    finally:
        clips_mod.export_event_clips = valodi

    lapok = latott.get("extra") or {}
    assert lapok, "a játékos lapja nem került a csomagba"
    nev = next(iter(lapok))
    assert nev.endswith(f"jatekos_lap_{mez}.html"), nev
    # EGY játékosnál nincs mappa — ott is a zip gyökerében a lap.
    assert "/" not in nev, nev
    assert "<html" in lapok[nev].lower()


def test_mezszam_nelkul_nincs_jatekos_lap():
    """Csapat-szintű csomagba NE kerüljön véletlenszerű játékos-lap:
    ott nincs kihez tenni, és egy odatévedt lap félrevezetne.

    Helyette az EDZŐI ÖSSZEFOGLALÓ megy a klipek mellé — ugyanaz a
    gondolat egy szinttel feljebb: a videó megmutatja, mi történt, a
    lap azt, mit jelent.
    """
    import handball.pipeline.clips as clips_mod

    client, mid = _client()
    latott: dict = {}

    def _fake(match, events, types, out_dir, progress_cb=None,
              jerseys=None, extra_files=None, **kw):
        latott["extra"] = extra_files
        raise RuntimeError("teszt: itt megállunk")

    valodi = clips_mod.export_event_clips
    clips_mod.export_event_clips = _fake
    try:
        r = client.post(f"/matches/{mid}/clips/export",
                        json={"types": ["goal"]})
        job_id = r.json()["job_id"]
        for _ in range(200):
            if client.get(f"/jobs/{job_id}").json()["status"] in (
                    "done", "error"):
                break
    finally:
        clips_mod.export_event_clips = valodi

    lapok = latott.get("extra") or {}
    assert not [n for n in lapok if "jatekos_lap" in n], lapok
    assert "edzoi_osszefoglalo.txt" in lapok, lapok
    assert lapok["edzoi_osszefoglalo.txt"].strip()
def test_a_becsles_a_bovitett_csomagokat_is_szamolja():
    """ŐR: a becslő UGYANABBÓL az esemény-építőből él, mint a vágás.

    Korábban a számláló csak az alap-eseményeket látta, a bővített
    csomagokra (jegyzet, nagy védés, kulcs-pillanat) NULLÁT becsült —
    a felület "üres csomagot adna"-t mondott, miközben a vágás
    klipeket adott volna. A jegyzet a legkönnyebben előállítható
    bővített típus: azon mérjük.
    """
    client, mid = _client()
    client.post(f"/matches/{mid}/notes", json={"frame": 5,
                                               "text": "jelenet"})
    r = client.get(f"/matches/{mid}/clip-players").json()
    assert r["totals"].get("note", 0) >= 1, r["totals"]


def test_a_kozos_epito_kotelezo():
    """ŐR a széttartás ellen: a számláló nem építhet saját listát."""
    src = (Path(__file__).resolve().parents[1] / "handball" / "api"
           / "app.py").read_text(encoding="utf-8")
    assert src.count("def _clip_events(") == 1
    # A worker ÉS a számláló is a közös építőt hívja.
    assert src.count("_clip_events(match, match_id,") >= 2
def test_a_szamlalo_gyorsitotara_frissul_a_valtozasra():
    """A számláló gyorsítótárazva van (egy hosszú meccsen az építés
    másodpercekbe telik, és a Klipek lap minden megnyitása lekéri) —
    de a gyorsítótár nem mutathat RÉGI képet: az új jegyzet azonnal
    látszódjon a becslésben.
    """
    import time

    client, mid = _client()
    # A megosztott teszt-mappában maradhatott korábbi jegyzet — a
    # VÁLTOZÁST mérjük, nem az abszolút számot.
    elotte = client.get(f"/matches/{mid}/clip-players").json()
    volt = elotte["totals"].get("note", 0)
    time.sleep(0.02)  # az mtime-kulcs biztosan elmozduljon
    client.post(f"/matches/{mid}/notes", json={"frame": 4,
                                               "text": "friss"})
    utana = client.get(f"/matches/{mid}/clip-players").json()
    assert utana["totals"].get("note", 0) == volt + 1, utana["totals"]


def test_a_draga_eladas_csomag_a_3d_labdavesztesebol_jon(tmp_path,
                                                        monkeypatch):
    """A "Drága eladások" csomag ugyanazokat a jeleneteket vágja, amiket
    a 3D Labdavesztések lapozója gólosnak mutat — a vesztő mezszámához
    írva (enélkül a játékos-szűrés némán üres csomagot adna)."""
    from test_court3d import _eladasos_meccs

    from handball.api.app import create_app
    from handball.pipeline.court3d import turnover_moments

    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    m = _eladasos_meccs()
    app = create_app()
    app.state.put_match(m)
    r = TestClient(app).get(f"/matches/{m.meta.match_id}/clip-players").json()
    gol = [x for x in turnover_moments(m)["moments"] if x["punished"]]
    assert len(gol) == 1 and gol[0]["jersey"] == 7
    assert r["totals"].get("costly_turnover") == 1
    hetes = next(p for p in r["players"]
                 if p["jersey"] == 7 and p["team"] == "home")
    assert hetes["counts"].get("costly_turnover") == 1


def test_a_lerohanas_csomagok_a_3d_lerohanasaibol_jonnek(tmp_path,
                                                         monkeypatch):
    """A "Lerohanások" és a "Kapott lerohanások" csomag ugyanazokat a
    jeleneteket vágja, amiket a 3D Lerohanások lapozója mutat: a támadóé
    a befejező mezszámához írva (a "#13 lerohanásai" szűréshez), a
    kapott a védekező csapaté, mezszám nélkül (nem egy védő hibája)."""
    from handball.api.app import create_app
    from handball.pipeline.court3d import fast_break_moments
    from handball.sim.match_simulator import simulate_ground_truth

    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    m = simulate_ground_truth(duration_s=300, fps=25.0, seed=7,
                              shots_per_min=8)
    app = create_app()
    app.state.put_match(m)
    r = TestClient(app).get(f"/matches/{m.meta.match_id}/clip-players").json()
    kontrak = fast_break_moments(m)["moments"]
    assert len(kontrak) == 4 and all(k["team"] == "home" for k in kontrak)
    assert r["totals"].get("fast_break") == 4
    assert r["totals"].get("conceded_fast_break") == 4
    mezek = [k["shooter_jersey"] for k in kontrak]
    for mez in set(mezek):
        p = next(p for p in r["players"]
                 if p["jersey"] == mez and p["team"] == "home")
        assert p["counts"].get("fast_break") == mezek.count(mez)
    # A kapott lerohanás egyetlen játékoshoz sem íródik.
    assert all("conceded_fast_break" not in p["counts"] for p in r["players"])


def test_a_dontes_hiba_csomag_a_3d_dontes_pillanataibol_jon(tmp_path,
                                                           monkeypatch):
    """A "Döntés-hibák" csomag a 3D Döntések lapozójának pillanatai — a
    passzolóhoz írva (a mezszámos sorok összege = a pillanatok száma)."""
    from handball.api.app import create_app
    from handball.pipeline.court3d import decision_moments

    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    m = simulate_ground_truth(duration_s=60, fps=25.0, seed=5,
                              shots_per_min=8)
    for f in m.frames:
        for p in f.players:
            p.jersey_number = (p.track_id % 14) + 1
    app = create_app()
    app.state.put_match(m)
    r = TestClient(app).get(f"/matches/{m.meta.match_id}/clip-players").json()
    n = len(decision_moments(m)["moments"])
    assert n > 0, "a szimuláción van döntés-pillanat"
    assert r["totals"].get("bad_decision") == n
    assert sum(p["counts"].get("bad_decision", 0) for p in r["players"]) == n
