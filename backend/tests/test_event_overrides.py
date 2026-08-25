"""
Tesztek a KÉZI esemény-javításra (event_overrides).

A felismerés téved: gólt lövésnek lát, lövést nem vesz észre. Az edző
egy rossz eredményű jelentésnek EGYETLEN számát sem hiszi el, akkor sem,
ha a többi jó — ezért a javításnak MINDEN rétegen át kell ütnie, nem
csak az esemény-listán.

Futtatás:
    python -m pytest tests/test_event_overrides.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from handball.models.tracking import (  # noqa: E402
    Ball, Frame, Match, MatchMeta, Team,
)
from handball.pipeline.event_detection import (  # noqa: E402
    EventType, detect_events, detect_shots,
)

_tmp = tempfile.mkdtemp(prefix="handball_overrides_test_")


def _meta():
    return MatchMeta(match_id="ov", home_team="A", away_team="B", fps=25.0)


def _shot_match():
    """Egy MELLÉ menő lövés a +x kapura (hazai) — a javítás alanya."""
    frames = [Frame(t=i, players=[], ball=Ball(x=34.0 + i, y=5.0,
                                               confidence=1.0))
              for i in range(6)]
    return Match(_meta(), frames)


# ---- A motor: a javítás a lövés-felismerésben ül ---------------------


def test_set_type_lovesbol_golt_csinal():
    """A leggyakoribb eset: a gól LÖVÉSKÉNT jött ki."""
    m = _shot_match()
    alap = detect_shots(m)
    assert [e.type for e in alap] == [EventType.SHOT]

    m.meta.event_overrides = [{"op": "set_type", "t": alap[0].t,
                               "type": "goal"}]
    javitott = detect_shots(m)
    assert [e.type for e in javitott] == [EventType.GOAL]
    # A KIMENETEL is együtt mozog a típussal: sok réteg a
    # detail["outcome"] mezőből dolgozik, és egy "gól" típusú, de
    # "miss" kimenetelű esemény néma ellentmondás lenne.
    assert javitott[0].detail["outcome"] == "goal"
    # A kézi eredet jelölve van.
    assert javitott[0].detail["manual"] is True


def test_remove_torol_es_add_felvesz():
    m = _shot_match()
    t0 = detect_shots(m)[0].t

    m.meta.event_overrides = [{"op": "remove", "t": t0, "type": "shot"}]
    assert detect_shots(m) == []

    m.meta.event_overrides = [{"op": "add", "t": 4, "type": "goal",
                               "team": "away"}]
    ki = detect_shots(m)
    kezi = [e for e in ki if (e.detail or {}).get("manual")]
    assert len(kezi) == 1
    assert kezi[0].type == EventType.GOAL
    assert kezi[0].team == Team.AWAY
    assert kezi[0].detail["outcome"] == "goal"


def test_a_javitas_atut_a_teljes_esemenylistan():
    """A javítás a lövés-felismerésben ül, ezért MINDEN rétegen átüt.

    Ha csak az esemény-végponton javítanánk, az eredmény jó lenne, de az
    xG, a lövő-listák és a felderítés a régi (hibás) képet mutatná — az
    edző pedig pont az ilyen ellentmondástól veszti el a bizalmát.
    """
    m = _shot_match()
    m.meta.event_overrides = [{"op": "set_type", "t": detect_shots(m)[0].t,
                               "type": "goal"}]
    golok = [e for e in detect_events(m) if e.type == EventType.GOAL]
    assert len(golok) == 1


def test_a_tavoli_javitas_nem_ut_mas_esemenyt():
    """Egy RÉGI javítás (pl. újrafeldolgozás után elcsúszott idő) ne
    írja át egy MÁSIK esemény típusát: ha az ablakon belül nincs semmi,
    a javítás csendben elmarad."""
    m = _shot_match()
    m.meta.event_overrides = [{"op": "set_type", "t": 9999, "type": "goal"}]
    assert [e.type for e in detect_shots(m)] == [EventType.SHOT]


def test_a_hibas_javitas_nem_viszi_el_a_tobbit():
    """Egy rossz alakú bejegyzés ne akadályozza meg a többi javítást."""
    m = _shot_match()
    m.meta.event_overrides = [
        {"op": "set_type", "t": "nem szám", "type": "goal"},
        {"op": "add", "t": 4, "type": "goal", "team": "home"},
    ]
    kezi = [e for e in detect_shots(m) if (e.detail or {}).get("manual")]
    assert len(kezi) == 1


def test_az_ido_ablak_masodpercben_van():
    """ŐR: az egyeztetés-ablak IDŐTARTAM, tehát másodpercben.

    A termék minden 3. kockát dolgozza fel, tehát a `meta.fps` a forrás
    harmada — egy kockában megadott ablak a minőségi profiltól függően
    háromszoros valós időt jelentene.
    """
    from handball.pipeline import event_detection as ed

    assert hasattr(ed, "OVERRIDE_MATCH_S")
    src = Path(ed.__file__).read_text(encoding="utf-8")
    assert "OVERRIDE_MATCH_S * fps" in src, (
        "az ablakot nem az fps-ből számoljuk")


# ---- A tárolás: a javítás a meccshez tartozik, nem a képernyőhöz -----


TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient


def _client():
    os.environ["HANDBALL_DATA_DIR"] = _tmp
    d = Path(_tmp) / "data" / "matches"
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("*"):
        old.unlink()
    m = _shot_match()
    m.meta.match_id = "ov1"
    (d / "ov1.json").write_text(json.dumps(m.to_dict()), encoding="utf-8")
    from handball.api.app import create_app
    return TestClient(create_app()), "ov1"


def _tipusok(client, mid):
    return [e["type"] for e in client.get(f"/matches/{mid}/events").json()
            ["events"] if e["type"] in ("goal", "shot")]


def test_a_javitas_tullel_egy_ujraindulast():
    """A javítás a MECCS tulajdonsága, nem egy képernyőé: a program
    újraindítása (és a könyvtár újratöltése) után is élnie kell."""
    client, mid = _client()
    assert _tipusok(client, mid) == ["shot"]

    r = client.post(f"/matches/{mid}/event-overrides",
                    json={"overrides": [{"op": "set_type", "t": 2,
                                         "type": "goal"}]})
    assert r.status_code == 200
    assert _tipusok(client, mid) == ["goal"]

    # Új app-példány = a program újraindítása.
    from handball.api.app import create_app
    ujra = TestClient(create_app())
    assert _tipusok(ujra, mid) == ["goal"]
    assert ujra.get(f"/matches/{mid}/event-overrides").json()["overrides"]


def test_a_vegpont_kiszuri_a_szemetet():
    """Ismeretlen művelet és típus nem kerül a tárolt listába — egy
    elgépelt kulcs némán semmit sem csinálna, de ott ülne a fájlban."""
    client, mid = _client()
    r = client.post(f"/matches/{mid}/event-overrides", json={"overrides": [
        {"op": "hack", "t": 1},
        {"op": "set_type", "t": 2, "type": "kapufa"},
        {"op": "add", "t": 3, "type": "goal", "team": "home"},
        "nem is szótár",
    ]})
    assert r.json()["overrides"] == [
        {"op": "add", "t": 3, "type": "goal", "team": "home"}]


def test_a_javitas_fajlja_nem_meccs():
    """A javítás-fájl a meccsek mappájában él; a betöltő nem
    próbálhatja meccsként olvasni (különben minden induláskor egy
    sérült meccset látna)."""
    client, mid = _client()
    client.post(f"/matches/{mid}/event-overrides",
                json={"overrides": [{"op": "set_type", "t": 2,
                                     "type": "goal"}]})
    assert (Path(_tmp) / "data" / "matches" / "ov1.events.json").exists()
    from handball.api.app import create_app
    ujra = TestClient(create_app())
    assert len(ujra.get("/matches").json()["matches"]) == 1


def test_ismeretlen_meccs_javitasa_404():
    client, _mid = _client()
    r = client.post("/matches/nincs-ilyen/event-overrides",
                    json={"overrides": []})
    assert r.status_code == 404
