"""A nehéz meccs-végpontok eredmény-gyorsítótára.

Egy 60 perces meccs megnyitása a támadások (80 mp), a védekezés (50 mp),
az edzői összefoglaló (45 mp) és az edzés-fókusz (30 mp) számolása miatt
közel négy perc volt — MINDEN alkalommal, újraindítás után is. A tár az
első számolás után azonnal ad; ezek a tesztek azt őrzik, hogy (1) tényleg
nem számol újra, (2) az újraindítást is túléli, (3) viszont MINDEN
változásra (kézi javítás, motor-verzió) újraszámol, és (4) a törölt meccs
tára is eltűnik, a könyvtár-mentésbe pedig nem kerül bele.
"""
import io
import json
import tempfile
import zipfile
from pathlib import Path

import pytest

from handball.models import (Ball, Frame, Match, MatchMeta, PlayerPosition,
                             PositionSource, Team)

TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient


def _meccs(mid="rc1"):
    frames = [Frame(t=t, players=[
        PlayerPosition(track_id=1, team=Team.HOME, x=20.0 + t * 0.05, y=10.0,
                       source=PositionSource.MEASURED, confidence=1.0),
        PlayerPosition(track_id=2, team=Team.AWAY, x=30.0, y=8.0,
                       source=PositionSource.MEASURED, confidence=1.0)],
        ball=Ball(x=20.0 + t * 0.05, y=10.0, confidence=1.0)) for t in range(60)]
    return Match(MatchMeta(match_id=mid, home_team="H", away_team="V",
                           fps=25.0), frames)


@pytest.fixture()
def konyvtar(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="hb_rc_")
    d = Path(tmp) / "data" / "matches"
    d.mkdir(parents=True)
    (d / "rc1.json").write_text(_meccs().to_json(), encoding="utf-8")
    monkeypatch.setenv("HANDBALL_DATA_DIR", tmp)
    monkeypatch.setenv("HANDBALL_STORE_SYNC", "1")
    return Path(tmp)


def _szamlalo(monkeypatch):
    """A coach_summary hívásainak száma (a végpont hívásonként importál)."""
    from handball.pipeline import coach_summary as cs
    eredeti = cs.coach_summary
    n = {"db": 0}

    def _szamolo(match):
        n["db"] += 1
        return eredeti(match)

    monkeypatch.setattr(cs, "coach_summary", _szamolo)
    return n


def test_masodszorra_a_tarbol_jon_es_az_ujrainditast_is_tuleli(konyvtar,
                                                               monkeypatch):
    from handball.api.app import create_app
    n = _szamlalo(monkeypatch)
    client = TestClient(create_app())
    elso = client.get("/matches/rc1/coach-summary").json()
    assert client.get("/matches/rc1/coach-summary").json() == elso
    assert n["db"] == 1, "a második megnyitás nem számol újra"
    assert (konyvtar / "data" / "cache" / "rc1" / "coach-summary.json").exists()
    # Újraindítás: új app-példány, a lemezi tárból jön.
    ujra = TestClient(create_app())
    assert ujra.get("/matches/rc1/coach-summary").json() == elso
    assert n["db"] == 1, "újraindítás után is a lemezi tárból"
    # A többi nehéz végpont is a tárból jön, és ugyanazt adja.
    for ut in ("attacks", "defense", "training", "team-stats"):
        a = client.get(f"/matches/rc1/{ut}")
        assert a.status_code == 200, ut
        assert ujra.get(f"/matches/rc1/{ut}").json() == a.json(), ut
    assert client.get("/matches/nincs/coach-summary").status_code == 404


def test_valtozasra_ujraszamol(konyvtar, monkeypatch):
    import handball
    from handball.api.app import create_app
    n = _szamlalo(monkeypatch)
    client = TestClient(create_app())
    client.get("/matches/rc1/coach-summary")
    assert n["db"] == 1
    # Kézi esemény-javítás → a kísérő-fájl változik → újraszámol.
    r = client.post("/matches/rc1/event-overrides",
                    json={"overrides": [{"op": "add", "t": 10, "type": "goal",
                                         "team": "home"}]})
    assert r.status_code == 200
    client.get("/matches/rc1/coach-summary")
    assert n["db"] == 2
    # Motor-frissítés (új verzió) → újraszámol.
    monkeypatch.setattr(handball, "__version__", "9.9.9-teszt")
    client.get("/matches/rc1/coach-summary")
    assert n["db"] == 3


def test_torleskor_eltunik_es_a_mentesbe_nem_kerul(konyvtar):
    from handball.api.app import create_app
    client = TestClient(create_app())
    client.get("/matches/rc1/coach-summary")
    tar = konyvtar / "data" / "cache" / "rc1"
    assert tar.exists()
    z = zipfile.ZipFile(io.BytesIO(client.get("/library/export").content))
    assert not [n for n in z.namelist() if n.startswith("cache/")]
    assert "matches/rc1.json" in z.namelist()
    assert client.delete("/matches/rc1").status_code == 200
    assert not tar.exists()


def test_a_feldolgozas_vegen_elore_kiszamolja(konyvtar, monkeypatch):
    """A kész feldolgozás után a háttérben előszámol — az edző első
    megnyitása is azonnali. A job-útvonal ténylegesen hívja."""
    import inspect
    import time

    from handball.api import app as app_mod
    from handball.api.app import create_app
    monkeypatch.setenv("HANDBALL_WARM_RESULTS", "1")
    n = _szamlalo(monkeypatch)
    app = create_app()
    app.state.warm_results("rc1")
    tar = konyvtar / "data" / "cache" / "rc1"
    hatarido = time.time() + 60
    while time.time() < hatarido and not (tar / "attacks.json").exists():
        time.sleep(0.1)
    assert (tar / "attacks.json").exists(), "a háttér-előszámolás lefutott"
    for ut in ("team-stats", "training", "coach-summary", "defense"):
        assert (tar / f"{ut}.json").exists(), ut
    hatarido = time.time() + 30
    while time.time() < hatarido and not (tar / "player-tallies.json").exists():
        time.sleep(0.1)
    assert (tar / "library-summary.json").exists()
    assert (tar / "player-tallies.json").exists()
    assert n["db"] == 1
    TestClient(app).get("/matches/rc1/coach-summary")
    assert n["db"] == 1, "a megnyitás a kész előszámolást kapja"
    forras = inspect.getsource(app_mod.create_app)
    assert "_maybe_merge_group(job)\n                    _warm_results(" in forras


def test_a_kezdolap_szezon_szamolasai_is_a_tarbol_jonnek(konyvtar, monkeypatch):
    """A kezdőlap minden indításkor az EGÉSZ könyvtárra kéri a szezon-
    összképet, a szezon-fókuszt és a toplistát. Meccsenként ezek
    másodpercekig (a fókusz fél percig) számoltak, újraindítás után
    mindig elölről — húsz meccsnél ez percek. Újraindítás után a
    meccsenkénti rész a lemezes tárból jön."""
    from handball.api.app import create_app
    from handball.pipeline import training as tr_mod
    from handball.pipeline import xg as xg_mod
    n = {"tf": 0, "xg": 0}
    tf0, xg0 = tr_mod.training_focus, xg_mod.match_xg

    def _tf(match, config=None):
        n["tf"] += 1
        return tf0(match, config)

    def _xg(match, config=None):
        n["xg"] += 1
        return xg0(match, config)

    monkeypatch.setattr(tr_mod, "training_focus", _tf)
    monkeypatch.setattr(xg_mod, "match_xg", _xg)
    client = TestClient(create_app())
    utak = ("/library/summary", "/library/training-focus", "/library/leaders")
    elso = {u: client.get(u).json() for u in utak}
    tf1, xg1 = n["tf"], n["xg"]
    assert tf1 >= 1 and xg1 >= 1
    ujra = TestClient(create_app())
    for u in utak:
        assert ujra.get(u).json() == elso[u], u
    assert n["tf"] == tf1, "a szezon-fókusz a tárból jött"
    assert n["xg"] == xg1, "a toplista meccsenkénti része a tárból jött"
    tar = konyvtar / "data" / "cache" / "rc1"
    for nev in ("library-summary", "training", "player-tallies"):
        assert (tar / f"{nev}.json").exists(), nev


def test_a_felderites_ujrainditas_utan_a_tarbol_jon_es_zipbol_nem_jon_tar(
        konyvtar, monkeypatch):
    """A felderítő jelentés (csapatonként ~50 mp egy teljes meccsen) a
    lemezen is megmarad, PONTOSAN visszaolvasva; a könyvtár-visszaállítás
    viszont kívülről kapott zipből sosem ír a gyorsítótárba."""
    from handball.api.app import create_app
    from handball.pipeline import scouting as sc_mod
    import handball.api.app as app_mod
    n = {"db": 0}
    eredeti = app_mod.scout_team

    def _szamolo(match, team, config=None):
        n["db"] += 1
        return eredeti(match, team, config)

    monkeypatch.setattr(app_mod, "scout_team", _szamolo)
    client = TestClient(create_app())
    elso = client.get("/matches/rc1/scouting?team=away").json()
    assert n["db"] == 1
    assert (konyvtar / "data" / "cache" / "rc1" / "scout-away.json").exists()
    ujra = TestClient(create_app())
    assert ujra.get("/matches/rc1/scouting?team=away").json() == elso
    assert n["db"] == 1, "újraindítás után a lemezi tárból"
    # Kívülről kapott zip: a cache/ ág nem csomagolódik ki.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("cache/rc1/scout-home.json", '{"fp": "x", "report": {}}')
        z.writestr("notes_extra.txt", "ok")
    r = ujra.post("/library/import", content=buf.getvalue())
    assert r.status_code == 200, r.text
    assert not (konyvtar / "data" / "cache" / "rc1" / "scout-home.json").exists()
    assert (konyvtar / "data" / "notes_extra.txt").exists()
    assert sc_mod.ScoutingReport  # a modul él


def test_a_tipusmegorzo_json_pontosan_visszaolvas():
    """A felderítő jelentésben egész kulcsú szótár is van (mezszám →
    poszt): a sima JSON ebből szöveg-kulcsot csinálna, és a visszaolvasott
    jelentés már nem ugyanaz. A címkés alak mindent pontosan visszaad."""
    from handball.api.app import typed_json_decode, typed_json_encode
    minta = {"positions": {1: "szélső", 7: "beálló"},
             "par": (3, "x"), "halmaz": {1, 2},
             "__t__": "ütköző kulcs", "lista": [(1, 2), {"a": None}],
             "szam": 1.5, "igaz": True}
    szoveg = json.dumps(typed_json_encode(minta))
    assert typed_json_decode(json.loads(szoveg)) == minta
    with pytest.raises(TypeError):
        typed_json_encode(object())
