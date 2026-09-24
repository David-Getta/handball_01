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
    assert n["db"] == 1
    TestClient(app).get("/matches/rc1/coach-summary")
    assert n["db"] == 1, "a megnyitás a kész előszámolást kapja"
    forras = inspect.getsource(app_mod.create_app)
    assert "_maybe_merge_group(job)\n                    _warm_results(" in forras
