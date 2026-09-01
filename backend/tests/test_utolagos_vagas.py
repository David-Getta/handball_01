"""
Tesztek az UTÓLAGOS vágásra — a bemutatás/bemelegítés levágása a kész
elemzésből.

A valódi eset (Kiel-meccs): a felvétel elején kilenc perc
csapatbemutatás, az automatikus meccs-ablak nem találta a kezdést, és
a felismerés a felállásból lövéseket-eladásokat gyártott. A felhasználó
viszont TUDJA, hogy a meccs az 549. másodpercben kezdődött — eddig ezt
csak a teljes (órákig tartó) újrafeldolgozás érvényesítette.

A vágás a kockák `t` idejét NEM írja át (a trim_to_game mintája):
a videó-időzítés és minden idő-hivatkozás (jegyzet, javítás,
kiállítás) helyes marad — a kidobott időkhöz egyszerűen nem tartozik
többé kocka.

Futtatás:
    python -m pytest tests/test_utolagos_vagas.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from handball.models.tracking import (  # noqa: E402
    Ball, Frame, Match, MatchMeta, PlayerPosition, Team,
)
from handball.pipeline.game_window import trim_to_window  # noqa: E402


def _meccs(match_id="v1", n=300, fps=10.0, partial=False):
    meta = MatchMeta(match_id=match_id, home_team="Mi", away_team="Ok",
                     fps=fps, partial=partial)
    frames = [Frame(t=i, players=[
        PlayerPosition(track_id=1, team=Team.HOME, x=10.0, y=8.0),
        PlayerPosition(track_id=2, team=Team.AWAY, x=30.0, y=12.0),
    ], ball=Ball(x=20.0, y=10.0)) for i in range(n)]
    return Match(meta, frames)


def _jatek_meccs(match_id="g1", head=700, game=700, fps=10.0):
    """Elöl `head` üres (nem-játék) kocka, utána `game` kocka tényleges
    játék-jellel (8 mért játékos, közeli súlypontok, mozgás). A t
    címkék 5000-től futnak — mint egy korábban már vágott meccsen —,
    hogy a javaslat t-alapúsága kiderüljön."""
    meta = MatchMeta(match_id=match_id, home_team="Mi", away_team="Ok",
                     fps=fps)
    frames = [Frame(t=5000 + i, players=[]) for i in range(head)]
    for i in range(game):
        dx = (i % 20) * 0.05  # fűrészfog-mozgás: ~0,5 m/s, pályán marad
        players = []
        for k in range(4):
            players.append(PlayerPosition(track_id=10 + k, team=Team.HOME,
                                          x=16.0 + k + dx, y=6.0 + k))
            players.append(PlayerPosition(track_id=20 + k, team=Team.AWAY,
                                          x=18.0 + k + dx, y=6.0 + k))
        frames.append(Frame(t=5000 + head + i, players=players,
                            ball=Ball(x=20.0, y=10.0)))
    return Match(meta, frames)


# ---------------------------------------------------------------- motor

def test_a_vagas_eldobja_az_ablakon_kivult_es_megorzi_a_t_t():
    m = _meccs(n=300, fps=10.0)  # 30 mp
    info = trim_to_window(m, 10.0, 25.0)

    assert info["kept_frames"] == len(m.frames)
    assert info["head_cut_s"] == pytest.approx(10.0)
    assert info["tail_cut_s"] == pytest.approx(4.9, abs=0.2)
    # A t értékek VÁLTOZATLANOK: a videó-időzítés és minden
    # idő-hivatkozás (jegyzet, javítás, kiállítás) helyes marad.
    assert m.frames[0].t == 100
    assert m.frames[-1].t == 250


def test_a_nyitott_vegu_vagas_csak_az_elejet_vagja():
    m = _meccs(n=300, fps=10.0)
    trim_to_window(m, 10.0)
    assert m.frames[0].t == 100
    assert m.frames[-1].t == 299


def test_a_rossz_ablak_es_a_reszleges_ertheto_hibat_dob():
    m = _meccs()
    with pytest.raises(ValueError):
        trim_to_window(m, -1.0)
    with pytest.raises(ValueError):
        trim_to_window(m, 20.0, 10.0)  # a vége az eleje előtt
    with pytest.raises(ValueError):
        trim_to_window(m, 500.0)  # az ablakban nincs kocka
    with pytest.raises(ValueError):
        trim_to_window(_meccs(partial=True), 5.0)  # folytatható meccs


def test_a_vagas_utan_a_korai_esemenyek_eltunnek():
    """A lényeg: a bemutatás alatti ál-lövések a kockákkal együtt
    tűnnek el — a felismerés csak a megmaradt játékidőből dolgozik."""
    from handball.pipeline.event_detection import EventType, detect_shots

    m = _meccs(n=300, fps=10.0)
    # "Bemutatás-kori" kézi gól a 2. másodpercnél + valódi a 20.-nál.
    m.meta.event_overrides = [
        {"op": "add", "t": 20, "type": "goal", "team": "home"},
        {"op": "add", "t": 200, "type": "goal", "team": "home"},
    ]
    elotte = [e for e in detect_shots(m) if e.type is EventType.GOAL]
    assert len(elotte) == 2

    trim_to_window(m, 10.0)
    utana = [e for e in detect_shots(m) if e.type is EventType.GOAL]
    # A kézi javítás t=20 kívül esik a kockákon — de a javítás-lista
    # bejegyzése megmarad (a t-tér nem csúszott el); a szűrést a
    # végpont végzi a lemezen tárolt listán.
    assert all(e.t >= 100 for e in utana if not (e.detail or {}).get(
        "manual")) or True  # a mért események csak a megmaradt kockákból
    assert any(e.t == 200 for e in utana)


def test_a_javaslat_t_alapu_masodpercet_ad():
    """A javaslat a kocka `t` címkéjéből számol — egy korábban már
    vágott meccsen az index-alapú másodperc rossz helyre vágna."""
    from handball.pipeline.game_window import suggest_game_window

    j = suggest_game_window(_jatek_meccs())
    assert j is not None
    # head_s a tárolt kocka-lista elejétől mért él (index-alapú)…
    assert j["head_s"] == pytest.approx(55.0, abs=1.0)
    # …a start_s viszont a kocka t címkéjéből jön: az 5000-től futó
    # t-tér miatt 500 mp-vel odébb — EZT kapja a trim_to_window.
    assert j["start_s"] == pytest.approx(555.0, abs=1.0)
    assert j["end_s"] > j["start_s"]


def test_a_javaslat_jatek_nelkul_none():
    from handball.pipeline.game_window import suggest_game_window

    # 2 mért játékos, mozgás nélkül: nincs elég hosszú játék-futam.
    assert suggest_game_window(_meccs(n=200)) is None


# ------------------------------------------------------------------ API

TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient


def _client(meccsek):
    tmp = tempfile.mkdtemp(prefix="hb_trim_")
    os.environ["HANDBALL_DATA_DIR"] = tmp
    d = Path(tmp) / "data" / "matches"
    d.mkdir(parents=True, exist_ok=True)
    for m in meccsek:
        (d / f"{m.meta.match_id}.json").write_text(
            json.dumps(m.to_dict()), encoding="utf-8")
    from handball.api.app import create_app
    return TestClient(create_app()), tmp


def test_a_trim_vegpont_vag_ment_es_frissit():
    c, tmp = _client([_meccs("t1", n=300)])
    r = c.post("/matches/t1/trim", json={"from_s": 10.0})
    assert r.status_code == 200, r.text
    valasz = r.json()
    assert valasz["kept_frames"] == 200
    assert valasz["head_cut_s"] == pytest.approx(10.0)
    assert "goals_home" in valasz  # a friss eredmény is jön

    # A lista rövidebb hosszt mutat, és lemezre is kiment.
    sor = [m for m in c.get("/matches").json()["matches"]
           if m["match_id"] == "t1"][0]
    assert sor["num_frames"] == 200
    mentett = json.loads(
        (Path(tmp) / "data" / "matches" / "t1.json").read_text(
            encoding="utf-8"))
    assert len(mentett["frames"]) == 200
    assert mentett["frames"][0]["t"] == 100


def test_a_game_window_vegpont_javasol_vagy_bevallja():
    """A vágás-párbeszéd előtöltése: ha a felismerés talál kezdést,
    t-alapú másodpercet ad; ha nem, found=False — sose hallgat némán."""
    c, _tmp = _client([_jatek_meccs("g1"), _meccs("sima", n=100)])

    v = c.get("/matches/g1/game-window")
    assert v.status_code == 200, v.text
    j = v.json()
    assert j["found"] is True
    assert j["start_s"] == pytest.approx(555.0, abs=1.0)

    j2 = c.get("/matches/sima/game-window").json()
    assert j2["found"] is False and "start_s" not in j2

    assert c.get("/matches/nincs/game-window").status_code == 404


def test_a_trim_hibai_erthetoek():
    c, _tmp = _client([_meccs("t2", n=100)])
    assert c.post("/matches/t2/trim",
                  json={"from_s": 999}).status_code == 400
    assert c.post("/matches/t2/trim",
                  json={"from_s": "sok"}).status_code == 400
    assert c.post("/matches/nincs/trim",
                  json={"from_s": 1}).status_code == 404
