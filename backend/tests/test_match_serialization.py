"""A meccs szerializálása — gyors, darabolt, és bájtra azonos a régivel.

A motor egy teljes meccset (60 perc, ~420 ezer játékos-pozíció) adott ki
`asdict` + FastAPI-kódolóval: 9 + 9 másodperc, és ez alatt az életjelre
sem felelt időben. A kliens ilyenkor halottnak hitte, és újraindította —
ebből jött a "nem indul el a motor, nem nyílik a könyvtár". Ezek a
tesztek azt őrzik, hogy a gyors út UGYANAZT adja, mint a régi.
"""
import dataclasses
import json
import tempfile
from dataclasses import asdict
from pathlib import Path

import pytest

from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                      PlayerPosition, PositionSource, Team,
                                      _enums_to_str, frame_to_dict)


def _meccs(n=50):
    frames = []
    for t in range(n):
        ps = [PlayerPosition(track_id=i, team=Team.HOME if i < 3 else Team.AWAY,
                             x=1.5 * i + t * 0.01, y=10.0 - i * 0.7,
                             source=(PositionSource.MEASURED if t % 3
                                     else list(PositionSource)[-1]),
                             confidence=0.5 + 0.01 * i,
                             jersey_number=(7 if i == 1 else None),
                             role=("kapus" if i == 0 else None))
              for i in range(6)]
        frames.append(Frame(t=t * 3, players=ps if t != 4 else [],
                            ball=(None if t % 7 == 0
                                  else Ball(x=20.0, y=10.0, confidence=0.4))))
    m = Match(MatchMeta(match_id="ser1", home_team="Hazai ÁÉ", away_team="Vendég",
                        fps=8.33, calib_pairs=[[[[1, 0, 0], [0, 1, 0], [0, 0, 1]],
                                                "left"]],
                        event_overrides=[{"op": "add", "t": 3, "type": "goal",
                                          "team": "home"}]), frames)
    return m


def test_a_gyors_szerializalas_azonos_az_asdict_alakkal():
    m = _meccs()
    regi = json.dumps(_enums_to_str(asdict(m)), ensure_ascii=False)
    assert m.to_json() == regi
    assert json.dumps(m.to_dict()) == json.dumps(_enums_to_str(asdict(m)))


def test_a_kocka_szotar_minden_mezot_kiir():
    """ŐR: a kézi kocka-kiíró a dataclass-ok MINDEN mezőjét viszi — egy új
    PlayerPosition-/Ball-/Frame-mező nem veszhet el csendben."""
    fr = Frame(t=1, players=[PlayerPosition(track_id=1, team=Team.HOME, x=1.0,
                                            y=2.0)],
               ball=Ball(x=1.0, y=2.0))
    d = frame_to_dict(fr)
    assert list(d) == [f.name for f in dataclasses.fields(Frame)]
    assert list(d["players"][0]) == [f.name for f in
                                     dataclasses.fields(PlayerPosition)]
    assert list(d["ball"]) == [f.name for f in dataclasses.fields(Ball)]


def test_a_darabolt_json_a_tomor_json():
    m = _meccs(n=130)
    tomor = json.dumps(m.to_dict(), ensure_ascii=False, separators=(",", ":"))
    for meret in (1, 7, 400):
        assert "".join(m.iter_json_chunks(frames_per_chunk=meret)) == tomor
    ures = Match(MatchMeta(match_id="u", home_team="a", away_team="b", fps=25.0))
    assert json.loads("".join(ures.iter_json_chunks()))["frames"] == []
    assert Match.from_json("".join(m.iter_json_chunks())).to_json() == m.to_json()


TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient


def test_a_meccs_vegpont_darabolva_ugyanazt_adja(monkeypatch):
    import inspect

    tmp = tempfile.mkdtemp(prefix="hb_ser_")
    d = Path(tmp) / "data" / "matches"
    d.mkdir(parents=True)
    m = _meccs(n=120)
    # A kézi javítások betöltéskor a KÜLÖN fájlból jönnek (itt nincs) —
    # a meccs-fájlba írtat a motor szándékosan felülírja.
    m.meta.event_overrides = []
    (d / "ser1.json").write_text(m.to_json(), encoding="utf-8")
    monkeypatch.setenv("HANDBALL_DATA_DIR", tmp)
    monkeypatch.setenv("HANDBALL_STORE_SYNC", "1")
    from handball.api.app import create_app
    app = create_app()
    client = TestClient(app)
    r = client.get("/matches/ser1")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert r.json() == json.loads(m.to_json())
    assert client.get("/matches/nincs").status_code == 404
    # Az életjel ASZINKRON: nem áll sorba a nehéz kérések mögött.
    health = next(rt for rt in app.routes if getattr(rt, "path", "") == "/health")
    assert inspect.iscoroutinefunction(health.endpoint)


def test_a_meccs_mentese_tomor_es_atomikus(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="hb_put_")
    monkeypatch.setenv("HANDBALL_DATA_DIR", tmp)
    monkeypatch.setenv("HANDBALL_STORE_SYNC", "1")
    from handball.api.app import create_app
    app = create_app()
    m = _meccs(n=20)
    app.state.put_match(m)
    d = Path(tmp) / "data" / "matches"
    szoveg = (d / "ser1.json").read_text(encoding="utf-8")
    assert "\n" not in szoveg, "tömör JSON (behúzás nélkül)"
    assert not list(d.glob("*.tmp")), "az atomikus írás nem hagy szemetet"
    assert Match.from_json(szoveg).to_json() == m.to_json()
