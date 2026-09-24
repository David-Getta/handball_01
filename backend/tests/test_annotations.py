"""Kézi elemzés — az edző saját esemény-naplója és taktikai táblái.

Két szint: a normalizálás (tiszta függvény: ami menthető, azt megmenti,
ami a korlátokon túl van, azt levágja) és az API (mentés félkészen,
visszaolvasás, újraindítás után is megmarad, CSV-export, és a
kísérőfájl nem keveredik a meccsek közé).
"""
import json
import os
import tempfile
from pathlib import Path

import pytest

from handball.annotations import (ANN_COURT_LENGTH_M, ANN_COURT_WIDTH_M,
                                  ANN_MAX_EVENTS, ANN_MAX_LABEL,
                                  ANN_MAX_TEXT, annotations_csv,
                                  empty_annotations, normalize_annotations,
                                  summarize_annotations)
from handball.models import (Ball, Frame, Match, MatchMeta, PlayerPosition,
                             PositionSource, Team)


def _dok():
    """Egy félkész kézi elemzés: két esemény (fordított időrendben
    beküldve), egy tábla két bábuval és egy passz-nyíllal."""
    return {
        "status": "in_progress",
        "events": [
            {"id": "e2", "t_s": 95.0, "team": "away", "type": "lövés",
             "jersey": "14", "outcome": "védés", "note": "bal szélről"},
            {"id": "e1", "t_s": 12.34, "team": "home", "type": "passz",
             "jersey": "7", "to_jersey": "11", "scene_id": "s1"},
        ],
        "scenes": [{
            "id": "s1", "name": "Kereszt balra", "t_s": 12.0,
            "tokens": [
                {"id": "h7", "team": "home", "label": "7", "x": 24, "y": 6},
                {"id": "h11", "team": "home", "label": "11", "x": 28,
                 "y": 3},
                {"id": "b", "team": "ball", "label": "", "x": 24, "y": 6},
            ],
            "arrows": [{"kind": "pass", "from": "h7", "to": "h11"},
                       {"kind": "run", "from": "h11", "x": 34, "y": 8}],
        }],
    }


# ---- normalizálás -----------------------------------------------------------


def test_a_normalizalas_idorendbe_tesz_es_megtartja_a_munkat():
    doc = normalize_annotations(_dok(), "m1")
    assert doc["match_id"] == "m1" and doc["version"] == 1
    assert doc["status"] == "in_progress" and doc["updated_at"]
    assert [e["id"] for e in doc["events"]] == ["e1", "e2"]
    assert doc["events"][0]["t_s"] == 12.3
    assert doc["events"][0]["to_jersey"] == "11"
    assert doc["events"][0]["scene_id"] == "s1"
    s = doc["scenes"][0]
    assert [t["id"] for t in s["tokens"]] == ["h7", "h11", "b"]
    assert s["arrows"][0] == {"kind": "pass", "from": "h7", "to": "h11"}
    assert s["arrows"][1]["to"] == "" and s["arrows"][1]["x"] == 34.0


def test_a_normalizalas_a_hibas_mezoket_javitja_nem_dobja_el_a_munkat():
    """A pályán kívüli bábu a pályára szorul, a hosszú szöveg levágódik,
    a nem létező táblára mutató hivatkozás üres lesz, a nem létező
    bábura mutató nyíl elesik, az ismeretlen csapat üres."""
    d = _dok()
    d["events"][0]["note"] = "x" * (ANN_MAX_TEXT + 50)
    d["events"][0]["team"] = "mindketto"
    d["events"][1]["scene_id"] = "nincs-ilyen"
    d["events"].append({"t_s": "nem szám", "type": ""})
    d["scenes"][0]["tokens"][0].update(x=-5, y=99, label="12345678")
    d["scenes"][0]["arrows"].append({"kind": "pass", "from": "h7",
                                     "to": "senki"})
    d["scenes"][0]["arrows"].append({"kind": "repül", "from": "h7",
                                     "to": "h11"})
    d["status"] = "valami"
    doc = normalize_annotations(d, "m1")
    lovés = next(e for e in doc["events"] if e["id"] == "e2")
    assert len(lovés["note"]) == ANN_MAX_TEXT and lovés["team"] == ""
    passz = next(e for e in doc["events"] if e["id"] == "e1")
    assert passz["scene_id"] == ""
    ures = next(e for e in doc["events"] if e["type"] == "egyéb")
    assert ures["t_s"] == 0.0
    tk = doc["scenes"][0]["tokens"][0]
    assert tk["x"] == 0.0 and tk["y"] == ANN_COURT_WIDTH_M
    assert len(tk["label"]) == ANN_MAX_LABEL
    assert len(doc["scenes"][0]["arrows"]) == 2, "a hibás nyilak elesnek"
    assert doc["status"] == "in_progress"


def test_a_normalizalas_korlatoz_es_a_hibas_alakot_elutasitja():
    with pytest.raises(ValueError):
        normalize_annotations(["nem", "szótár"], "m1")
    sok = {"events": [{"t_s": i} for i in range(ANN_MAX_EVENTS + 20)]}
    assert len(normalize_annotations(sok, "m1")["events"]) == ANN_MAX_EVENTS
    # Azonos azonosítójú események: mind megmarad, egyedi azonosítóval.
    dup = {"events": [{"id": "a", "t_s": 1}, {"id": "a", "t_s": 2}]}
    ids = [e["id"] for e in normalize_annotations(dup, "m1")["events"]]
    assert len(ids) == 2 and len(set(ids)) == 2
    assert empty_annotations("m1")["updated_at"] is None
    assert summarize_annotations(normalize_annotations(_dok(), "m1")) \
        ["events"] == 2


def test_a_csv_az_osszevetes_formatuma():
    doc = normalize_annotations(_dok(), "m1")
    csv = annotations_csv(doc, home="Hazai FC", away="Vendég SE")
    sorok = csv.strip().split("\r\n")
    assert sorok[0] == ("ido;ido_mp;csapat;esemeny;mez;kinek;kimenetel;"
                        "megjegyzes;tabla")
    assert sorok[1].startswith("00:12;12,3;Hazai FC;passz;7;11;;;")
    assert sorok[1].endswith("Kereszt balra")
    assert sorok[2].startswith("01:35;95,0;Vendég SE;lövés;14;;védés;")
    assert ANN_COURT_LENGTH_M == 40.0


# ---- API ----------------------------------------------------------------------


TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient


def _kis_meccs(mid: str) -> Match:
    frames = [Frame(t=t, players=[PlayerPosition(
        track_id=1, team=Team.HOME, x=10.0, y=10.0,
        source=PositionSource.MEASURED, confidence=1.0)],
        ball=Ball(x=10.0, y=10.0, confidence=1.0)) for t in range(20)]
    return Match(MatchMeta(match_id=mid, home_team="Hazai FC",
                           away_team="Vendég SE", fps=25.0), frames)


@pytest.fixture()
def kliens(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="hb_ann_")
    d = Path(tmp) / "data" / "matches"
    d.mkdir(parents=True)
    (d / "k1.json").write_text(json.dumps(_kis_meccs("k1").to_dict()),
                               encoding="utf-8")
    monkeypatch.setenv("HANDBALL_DATA_DIR", tmp)
    monkeypatch.setenv("HANDBALL_STORE_SYNC", "1")
    from handball.api.app import create_app
    return TestClient(create_app()), d


def test_az_ures_kezi_elemzes_es_a_felkesz_mentes(kliens):
    client, _d = kliens
    r = client.get("/matches/k1/annotations")
    assert r.status_code == 200
    assert r.json()["events"] == [] and r.json()["updated_at"] is None
    r = client.put("/matches/k1/annotations", json=_dok())
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "in_progress"
    vissza = client.get("/matches/k1/annotations").json()
    assert [e["id"] for e in vissza["events"]] == ["e1", "e2"]
    assert vissza["scenes"][0]["arrows"][0]["to"] == "h11"
    # Kész-re állítva is menthető, és felülírja az előzőt.
    kesz = dict(vissza, status="done")
    assert client.put("/matches/k1/annotations",
                      json=kesz).json()["status"] == "done"


def test_a_kezi_elemzes_tuleli_az_ujrainditast_es_nem_meccs(kliens):
    """A program újraindítása után is megvan, és a kísérőfájl NEM
    kerül a meccsek közé (a könyvtár-lista nem nő tőle)."""
    client, d = kliens
    client.put("/matches/k1/annotations", json=_dok())
    assert (d / "k1.annotations.json").exists()
    assert not list(d.glob("*.tmp")), "az atomikus írás nem hagy szemetet"
    from handball.api.app import create_app
    ujra = TestClient(create_app())
    assert len(ujra.get("/matches/k1/annotations").json()["events"]) == 2
    ids = [m["match_id"] for m in ujra.get("/matches").json()["matches"]]
    assert ids == ["k1"]


def test_a_kezi_elemzes_hibas_kerest_elutasit(kliens):
    client, _d = kliens
    assert client.get("/matches/nincs/annotations").status_code == 404
    assert client.put("/matches/nincs/annotations",
                      json=_dok()).status_code == 404
    assert client.put("/matches/k1/annotations",
                      json=["lista"]).status_code in (400, 422)


def test_a_kezi_elemzes_csv_exportja(kliens):
    client, _d = kliens
    client.put("/matches/k1/annotations", json=_dok())
    r = client.get("/matches/k1/annotations.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    szoveg = r.content.decode("utf-8")
    assert szoveg.startswith("﻿ido;ido_mp;csapat;")
    assert "Hazai FC;passz;7;11" in szoveg
    assert "attachment" in r.headers.get("content-disposition", "")


# ---- Összevetés a géppel -------------------------------------------------------


def _gol_meccs(start_frame: int = 0) -> Match:
    """Egy felismerhető hazai gól a +x kapura a meccs elején (a
    test_validation mintája), utána üresjárat."""
    def _pl(x):
        return PlayerPosition(track_id=1, team=Team.HOME, x=x, y=10.0,
                              source=PositionSource.MEASURED, confidence=1.0)
    frames = [Frame(t=i, players=[_pl(33.0)],
                    ball=Ball(x=33.0, y=10.0, confidence=1.0))
              for i in range(3)]
    for i in range(9):
        frames.append(Frame(t=3 + i, players=[_pl(33.0)],
                            ball=Ball(x=min(33.0 + 1.6 * (i + 1), 40.0),
                                      y=10.0, confidence=1.0)))
    for i in range(30):
        frames.append(Frame(t=12 + i, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    return Match(MatchMeta(match_id="g", home_team="H", away_team="A",
                           fps=25.0, start_frame=start_frame), frames)


def test_a_kezi_naplo_lovesei_ground_truth_kent():
    from handball.annotations import annotations_to_truth
    doc = {"events": [
        {"t_s": 5, "type": "lövés", "team": "home", "outcome": "gól"},
        {"t_s": 9, "type": "hetes", "team": "away", "outcome": "védés"},
        {"t_s": 12, "type": "lövés", "team": "home", "outcome": ""},
        {"t_s": 14, "type": "passz", "team": "home"},
        {"type": "lövés", "team": "home"},  # idő nélkül: kimarad
    ]}
    assert annotations_to_truth(doc) == [
        {"t_s": 5.0, "type": "gól", "team": "home"},
        {"t_s": 9.0, "type": "lövés", "team": "away"},
        {"t_s": 12.0, "type": "lövés", "team": "home"},
    ]


def test_az_osszevetes_videoidoben_par_es_keves_mintanal_nincs_itelet():
    """A kézi idő a VIDEÓ ideje: a feldolgozás 10 mp-nél indult (250.
    kocka), a gól a videóban ~10,4 mp-nél van — ezzel párosul, a
    kimaradt tétel ideje is videó-idő. Két kézi lövésből nincs ítélet."""
    from handball.annotations import compare_with_detection
    m = _gol_meccs(start_frame=250)
    doc = {"status": "done", "events": [
        {"t_s": 10.4, "type": "lövés", "team": "home", "outcome": "gól"},
        {"t_s": 40.0, "type": "lövés", "team": "home", "outcome": "gól"},
    ]}
    res = compare_with_detection(m, doc)
    g = res["by_type"]["goal"]
    assert g["tp"] == 1 and g["fn"] == 1 and g["fp"] == 0
    assert g["missed"][0]["t_s"] == 40.0
    assert res["offset_s"] == 10.0 and res["window_s"] is None
    assert res["manual_shots"] == 2 and res["enough"] is False
    assert res["verdict"]["pass"] is None


def test_a_felkesz_elemzes_csak_a_lefedett_idoszakot_veti_ossze():
    """Félkész elemzés: a még nem annotált rész felismerése (a gól az
    elején) nem számít TÉVES-nek, ha a napló később kezdődik."""
    from handball.annotations import compare_with_detection
    m = _gol_meccs()
    doc = {"status": "in_progress", "events": [
        {"t_s": 60.0 + i, "type": "lövés", "team": "home",
         "outcome": "védés"} for i in range(3)]}
    res = compare_with_detection(m, doc)
    assert res["overall"]["fp"] == 0
    assert res["window_s"][0] > 50.0
    assert res["enough"] is True
    # Késznek jelölve már az egész meccs számít: a gól téves-nek látszik.
    doc["status"] = "done"
    assert compare_with_detection(m, doc)["by_type"]["goal"]["fp"] == 1


def test_az_osszevetes_vegpontja(kliens):
    client, _d = kliens
    assert client.get("/matches/nincs/annotations/compare").status_code == 404
    client.put("/matches/k1/annotations", json=_dok())
    r = client.get("/matches/k1/annotations/compare")
    assert r.status_code == 200
    res = r.json()
    for kulcs in ("by_type", "overall", "verdict", "manual_shots",
                  "window_s", "enough"):
        assert kulcs in res, kulcs


def test_a_javitas_terv_tipus_csere_felvetel_torles():
    """Kimaradt gól + mellette téves lövés = típus-csere; a többi
    kimaradt felvétel, a többi téves törlés — tracking-kockában."""
    from handball.annotations import plan_overrides
    res = {"offset_s": 10.0, "tol_s": 3.0, "by_type": {
        "goal": {"missed": [{"t_s": 20.0, "type": "goal", "team": "home"}],
                 "spurious": [{"t_s": 70.0, "type": "goal",
                               "team": "away"}]},
        "shot": {"missed": [{"t_s": 40.0, "type": "shot", "team": "away"}],
                 "spurious": [{"t_s": 21.0, "type": "shot",
                               "team": "home"}]},
    }}
    ops = plan_overrides(res, fps=10.0)
    assert ops == [
        {"op": "set_type", "t": 110, "type": "goal"},
        {"op": "add", "t": 300, "type": "shot", "team": "away"},
        {"op": "remove", "t": 600, "type": "goal"},
    ]


@pytest.fixture()
def gol_kliens(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="hb_ann_gol_")
    d = Path(tmp) / "data" / "matches"
    d.mkdir(parents=True)
    m = _gol_meccs()
    m.meta.match_id = "g1"
    (d / "g1.json").write_text(json.dumps(m.to_dict()), encoding="utf-8")
    monkeypatch.setenv("HANDBALL_DATA_DIR", tmp)
    monkeypatch.setenv("HANDBALL_STORE_SYNC", "1")
    from handball.api.app import create_app
    return TestClient(create_app())


def test_a_naplo_javitaskent_atvezetheto_a_motorba(gol_kliens):
    """A gép gólt lát, a napló szerint védett lövés volt: a terv
    típus-csere, az átvezetés után a gép is lövést lát (az összevetés
    egyezik), és a próba-futás nem ír."""
    client = gol_kliens
    doc = {"status": "done", "events": [
        {"id": f"e{i}", "t_s": t, "type": "lövés", "team": "home",
         "outcome": o}
        for i, (t, o) in enumerate([(0.2, "védés")])]}
    assert client.put("/matches/g1/annotations", json=doc).status_code == 200
    elotte = client.get("/matches/g1/annotations/compare").json()
    assert elotte["by_type"]["goal"]["fp"] == 1
    assert elotte["by_type"]["shot"]["fn"] == 1
    terv = client.post("/matches/g1/annotations/apply?dry_run=true").json()
    assert terv["applied"] is False
    assert terv["counts"] == {"set_type": 1, "add": 0, "remove": 0}
    assert client.get("/matches/g1/event-overrides").json()["overrides"] == []
    kesz = client.post("/matches/g1/annotations/apply").json()
    assert kesz["applied"] is True
    utana = client.get("/matches/g1/annotations/compare").json()
    assert utana["overall"]["tp"] == 1 and utana["overall"]["fp"] == 0
    assert utana["overrides"] == 1
    # Másodszor nincs mit átvezetni (nem duplázódik).
    assert client.post("/matches/g1/annotations/apply").json()["ops"] == []
