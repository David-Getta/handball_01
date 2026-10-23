"""A meccs-tár HÁTTÉR-betöltése — a motor induláskor azonnal válaszol.

A motor eddig az ÖSSZES mentett meccset beolvasta, mielőtt a portot
megnyitotta volna: egy teljes meccs ~75 MB JSON, több másodperc — húsz
meccsnél percekig zárva volt a motor, a kliens "nem érem el a
háttérmotort"-ot mondott, és a könyvtár nem nyílt meg. Ezek a tesztek a
_MatchStore szerződését őrzik: a /health és a /matches a betöltés alatt
is válaszol, a kért meccs soron kívül töltődik, a többi olvasás megvárja
a végét, és a végén minden meccs bent van.
"""
import json
import os
import tempfile
import threading
import time
from pathlib import Path

import pytest

from handball.models import (Ball, Frame, Match, MatchMeta, PlayerPosition,
                             PositionSource, Team)


def _kis_meccs(mid: str, n: int = 40) -> Match:
    frames = [Frame(t=t, players=[PlayerPosition(
        track_id=1, team=Team.HOME, x=10.0 + t * 0.1, y=10.0,
        source=PositionSource.MEASURED, confidence=1.0)],
        ball=Ball(x=10.0, y=10.0, confidence=1.0)) for t in range(n)]
    return Match(MatchMeta(match_id=mid, home_team="H", away_team="A",
                           fps=25.0), frames)


def _konyvtar(ids) -> str:
    tmp = tempfile.mkdtemp(prefix="hb_store_")
    d = Path(tmp) / "data" / "matches"
    d.mkdir(parents=True)
    for mid in ids:
        (d / f"{mid}.json").write_text(json.dumps(_kis_meccs(mid).to_dict()),
                                       encoding="utf-8")
    return tmp


# ---- a tár egysége ----------------------------------------------------------


def test_a_tar_betoltes_alatt_a_kert_meccset_soron_kivul_adja():
    """Betöltés alatt: a /health-nek és a /matches-nek szánt olvasás nem
    vár; a kért (még be nem töltött) meccs a loader-ből jön; a teljes
    olvasás (values) megvárja a végét."""
    from handball.api.app import _MatchStore

    store = _MatchStore()
    lemez = {"a": _kis_meccs("a"), "b": _kis_meccs("b")}
    store.loader = lambda mid: lemez.get(mid)
    store.begin_loading(2)
    assert store.loading and store.status() == {"loading": True, "loaded": 0,
                                                "total": 2}
    assert store.snapshot() == []                 # nem vár
    assert store["a"].meta.match_id == "a"        # soron kívül a lemezről
    assert "b" in store and store.get("b") is lemez["b"]
    # A háttér-betöltő a soron kívül behozottat nem írja felül.
    masik_a = _kis_meccs("a", n=5)
    store.put_raw("a", masik_a, overwrite=False)
    assert store["a"] is lemez["a"]
    # values() megvárja a betöltés végét — külön szál zárja le.
    eredmeny = {}

    def _olvas():
        eredmeny["n"] = len(store.values())

    th = threading.Thread(target=_olvas)
    th.start()
    time.sleep(0.2)
    assert th.is_alive(), "a values()-nek várnia kell a betöltés végére"
    store.finish_loading()
    th.join(timeout=5)
    assert eredmeny["n"] == 2 and not store.loading


def test_a_tar_betoltes_utan_kozonseges_szotar():
    """Betöltés után (és betöltés nélkül) a tár sima szótárként viselkedik:
    írás, olvasás, törlés, iterálás."""
    from handball.api.app import _MatchStore

    store = _MatchStore()
    assert not store.loading and store.status()["loading"] is False
    store["x"] = _kis_meccs("x")
    assert "x" in store and len(store) == 1 and list(store) == ["x"]
    assert store.get("y") is None
    del store["x"]
    assert "x" not in store and store.snapshot() == []


# ---- az API ------------------------------------------------------------------


TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient


def test_a_motor_a_konyvtar_betoltese_alatt_is_valaszol(monkeypatch):
    """A /health és a /matches a háttér-betöltés alatt is válaszol, a
    betöltés állásával; a kért meccs soron kívül megnyílik; a végén a
    lista teljes."""
    from handball.api import app as app_mod

    monkeypatch.setenv("HANDBALL_DATA_DIR", _konyvtar(["m1", "m2", "m3"]))
    monkeypatch.delenv("HANDBALL_STORE_SYNC", raising=False)
    # A beolvasást LELASSÍTJUK, hogy a betöltés alatti állapot mérhető
    # legyen (a valóságban a fájl mérete lassítja).
    eredeti = app_mod.Match.from_json
    kapu = threading.Event()

    def _lassu(text):
        kapu.wait(timeout=5)
        return eredeti(text)

    monkeypatch.setattr(app_mod.Match, "from_json", staticmethod(_lassu))
    client = TestClient(app_mod.create_app())
    h = client.get("/health").json()
    assert h["status"] == "ok"
    assert h["library"]["loading"] is True and h["library"]["total"] == 3
    lista = client.get("/matches").json()
    assert lista["library"]["loading"] is True
    assert len(lista["matches"]) < 3, "a betöltés alatt a lista részleges"
    # A kért meccs soron kívül — a kapu nyitása után a lassú beolvasás
    # is végigmegy, de a kérés nem a teljes könyvtárra vár.
    kapu.set()
    r = client.get("/matches/m2")
    assert r.status_code == 200 and r.json()["meta"]["match_id"] == "m2"
    hatarido = time.time() + 10
    while time.time() < hatarido:
        lista = client.get("/matches").json()
        if not lista["library"]["loading"]:
            break
        time.sleep(0.05)
    assert not lista["library"]["loading"]
    assert sorted(m["match_id"] for m in lista["matches"]) == ["m1", "m2",
                                                               "m3"]


def test_a_szinkron_betoltes_kapcsoloval_kerheto(monkeypatch):
    """HANDBALL_STORE_SYNC=1: a régi, blokkoló betöltés — a tesztek és a
    determinisztikus indulás kedvéért. Induláskor már minden bent van."""
    from handball.api.app import create_app

    monkeypatch.setenv("HANDBALL_DATA_DIR", _konyvtar(["s1", "s2"]))
    monkeypatch.setenv("HANDBALL_STORE_SYNC", "1")
    client = TestClient(create_app())
    h = client.get("/health").json()
    assert h["library"] == {"loading": False, "loaded": 2, "total": 2}
    lista = client.get("/matches").json()
    assert sorted(m["match_id"] for m in lista["matches"]) == ["s1", "s2"]


def test_a_legfrissebb_meccs_toltodik_be_eloszor(monkeypatch):
    """A háttér-betöltés a legutóbb módosított fájllal kezd: amit az edző
    most nyitna, az legyen kész először."""
    from handball.api.app import create_app

    tmp = _konyvtar(["regi", "uj"])
    d = Path(tmp) / "data" / "matches"
    most = time.time()
    os.utime(d / "regi.json", (most - 1000, most - 1000))
    os.utime(d / "uj.json", (most, most))
    monkeypatch.setenv("HANDBALL_DATA_DIR", tmp)
    monkeypatch.setenv("HANDBALL_STORE_SYNC", "1")
    app = create_app()
    client = TestClient(app)
    ids = [m["match_id"] for m in client.get("/matches").json()["matches"]]
    assert set(ids) == {"regi", "uj"}
