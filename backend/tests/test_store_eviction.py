"""A meccs-tár memória-plafonja: csak a legutóbb használt meccsek maradnak
teljesen a memóriában, a többinek a fejléce (hideg), visszatöltés a
lemezről igény szerint."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.api.app import _MatchStore
from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                      PlayerPosition, PositionSource, Team)


def _meccs(mid: str, n: int = 5) -> Match:
    frames = [Frame(t=t, players=[PlayerPosition(
        track_id=1, team=Team.HOME, x=10.0, y=10.0,
        source=PositionSource.MEASURED, confidence=1.0)],
        ball=Ball(x=10.0, y=10.0, confidence=1.0)) for t in range(n)]
    return Match(MatchMeta(match_id=mid, home_team="H", away_team="A",
                           fps=25.0), frames)


def _tar(hot: int, lemez: dict):
    store = _MatchStore(hot_limit=hot)
    hivasok = []

    def loader(mid):
        hivasok.append(mid)
        return lemez.get(mid)

    store.loader = loader
    store.exists = lambda mid: mid in lemez
    return store, hivasok


def test_a_plafon_folott_a_legregebben_hasznalt_meccs_hideg_lesz():
    """Öt meccs, kettes plafon: a szótár a két legutóbbit tartja, a
    könyvtár mégis öt meccs; a hideg meccs hozzáféréskor visszatöltődik,
    és a legrégebbi meleg helyet cserél vele."""
    lemez = {f"m{i}": _meccs(f"m{i}", n=i + 1) for i in range(5)}
    store, hivasok = _tar(2, lemez)
    for i in range(5):
        store[f"m{i}"] = lemez[f"m{i}"]
    assert dict.__len__(store) == 2 and len(store) == 5
    assert store.evictions == 3
    assert sorted(dict.keys(store)) == ["m3", "m4"]
    for i in range(5):
        assert f"m{i}" in store
    # Fejlécek betöltés nélkül: kockaszám a hidegeknél is jó.
    fejlecek = {meta.match_id: n for meta, n in store.summaries()}
    assert fejlecek == {f"m{i}": i + 1 for i in range(5)}
    assert hivasok == []
    # Hideg meccs: visszatöltődik, a legrégebbi meleg (m3) hideg lesz.
    m0 = store["m0"]
    assert m0 is lemez["m0"] and hivasok == ["m0"]
    assert sorted(dict.keys(store)) == ["m0", "m4"]
    assert store.get("nincs") is None and "nincs" not in store


def test_a_konyvtar_szintu_olvasas_mindent_ad_es_utana_visszaall_a_plafon():
    lemez = {f"m{i}": _meccs(f"m{i}") for i in range(4)}
    store, hivasok = _tar(1, lemez)
    for mid, m in lemez.items():
        store[mid] = m
    assert dict.__len__(store) == 1
    ertekek = store.values()
    assert sorted(m.meta.match_id for m in ertekek) == sorted(lemez)
    assert sorted(k for k, _ in store.items()) == sorted(lemez)
    assert sorted(store.keys()) == sorted(lemez) == sorted(store)
    # A felsorolás végén a plafon újra érvényes.
    assert dict.__len__(store) == 1


def test_ami_nincs_a_lemezen_azt_sosem_dobjuk_ki():
    lemez = {"disk": _meccs("disk")}
    store, hivasok = _tar(1, lemez)
    store["mem"] = _meccs("mem")       # csak memóriában (pl. sikertelen írás)
    store["disk"] = lemez["disk"]
    store["mem2"] = _meccs("mem2")
    # A "disk" kidobható, a memória-meccsek nem: a plafon fölött maradnak.
    assert "disk" not in dict.keys(store)
    assert sorted(dict.keys(store)) == ["mem", "mem2"]
    assert len(store) == 3 and store["disk"] is lemez["disk"]


def test_torles_es_pop_a_hideg_meccsre_is():
    lemez = {f"m{i}": _meccs(f"m{i}") for i in range(3)}
    store, hivasok = _tar(1, lemez)
    for mid, m in lemez.items():
        store[mid] = m
    assert "m0" not in dict.keys(store)   # hideg
    del store["m0"]
    assert "m0" not in store and len(store) == 2
    assert store.pop("m1").meta.match_id == "m1"
    assert len(store) == 1
    with pytest.raises(KeyError):
        del store["m0"]
    assert store.pop("m0", None) is None


def test_eltunt_fajl_a_hideg_fejlecet_is_viszi():
    lemez = {f"m{i}": _meccs(f"m{i}") for i in range(2)}
    store, hivasok = _tar(1, lemez)
    for mid, m in lemez.items():
        store[mid] = m
    del lemez["m0"]                       # a fájl közben eltűnt
    assert store.get("m0") is None
    assert len(store) == 1 and "m0" not in store


def test_plafon_nelkul_a_regi_viselkedes():
    lemez = {f"m{i}": _meccs(f"m{i}") for i in range(4)}
    store, _ = _tar(0, lemez)
    for mid, m in lemez.items():
        store[mid] = m
    assert dict.__len__(store) == 4 and store.evictions == 0


TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient


def test_a_motor_konyvtara_plafonnal_is_teljes(monkeypatch):
    """Végpont-szinten: 4 mentett meccs, kettes plafon — a lista mind a
    négyet mutatja (a hidegeket visszatöltés nélkül), a meccs lekérése a
    hideget is visszaadja, a szezon-összesítés mindet látja."""
    tmp = tempfile.mkdtemp(prefix="hb_evict_")
    d = Path(tmp) / "data" / "matches"
    d.mkdir(parents=True)
    for i in range(4):
        (d / f"e{i}.json").write_text(json.dumps(_meccs(f"e{i}", n=10 + i).to_dict()),
                                      encoding="utf-8")
    monkeypatch.setenv("HANDBALL_DATA_DIR", tmp)
    monkeypatch.setenv("HANDBALL_STORE_SYNC", "1")
    monkeypatch.setenv("HANDBALL_STORE_HOT", "2")
    from handball.api.app import create_app
    client = TestClient(create_app())
    lista = client.get("/matches").json()["matches"]
    assert sorted(m["match_id"] for m in lista) == ["e0", "e1", "e2", "e3"]
    assert {m["match_id"]: m["num_frames"] for m in lista}["e3"] == 13
    for i in range(4):
        r = client.get(f"/matches/e{i}")
        assert r.status_code == 200, i
        assert len(r.json()["frames"]) == 10 + i
    assert client.get("/health").status_code == 200


def test_a_szezon_vegpontok_nem_toltik_vissza_a_hideg_meccseket(monkeypatch):
    """A kezdőlap könyvtár-végpontjai a lemezes eredmény-tárból dolgoznak:
    a MÁSODIK hívás egyetlen hideg meccset sem tölt vissza (különben egy
    húsz meccses könyvtárnál a kezdőlap percekig nyílna), és a lista sem."""
    tmp = tempfile.mkdtemp(prefix="hb_lazy_")
    d = Path(tmp) / "data" / "matches"
    d.mkdir(parents=True)
    for i in range(3):
        (d / f"l{i}.json").write_text(json.dumps(_meccs(f"l{i}", n=8).to_dict()),
                                      encoding="utf-8")
    monkeypatch.setenv("HANDBALL_DATA_DIR", tmp)
    monkeypatch.setenv("HANDBALL_STORE_SYNC", "1")
    monkeypatch.setenv("HANDBALL_STORE_HOT", "1")
    from handball.api.app import create_app
    app = create_app()
    client = TestClient(app)
    store = app.state.store
    assert dict.__len__(store) == 1 and len(store) == 3
    eredeti = store.loader
    hivasok = []

    def szamlalo(mid):
        hivasok.append(mid)
        return eredeti(mid)

    store.loader = szamlalo
    for ut in ("/library/summary", "/library/leaders", "/library/training-focus"):
        assert client.get(ut).status_code == 200, ut
    elso = len(hivasok)
    assert elso >= 2, "az első számolás a hideg meccseket betölti"
    for ut in ("/library/summary", "/library/leaders", "/library/training-focus",
               "/matches"):
        assert client.get(ut).status_code == 200, ut
    assert len(hivasok) == elso, "a második körben nincs visszatöltés"
    assert dict.__len__(store) == 1


def test_a_visszatoltes_alatt_a_tar_tobbi_olvasasa_nem_var():
    """A lemezről visszatöltés másodpercekig tart: közben a /health-nek
    (len, status), a listának (summaries) és a meleg meccseknek azonnal
    válaszolnia kell — a betöltés nem tarthatja a tár zárát."""
    import threading
    import time

    lemez = {f"m{i}": _meccs(f"m{i}") for i in range(3)}
    store, _ = _tar(1, lemez)
    for mid, m in lemez.items():
        store[mid] = m
    hideg = "m0"
    assert hideg not in dict.keys(store)
    elindult = threading.Event()

    def lassu_loader(mid):
        elindult.set()
        time.sleep(0.8)
        return lemez.get(mid)

    store.loader = lassu_loader
    eredmeny = []
    th = threading.Thread(target=lambda: eredmeny.append(store[hideg]))
    th.start()
    assert elindult.wait(2.0)
    t0 = time.time()
    assert len(store) == 3
    assert len(store.summaries()) == 3
    assert store.status()["loading"] is False
    assert store["m2"] is lemez["m2"]          # meleg meccs: azonnal
    assert time.time() - t0 < 0.3, "a visszatöltés blokkolta a tárat"
    th.join(3.0)
    assert eredmeny and eredmeny[0] is lemez[hideg]
