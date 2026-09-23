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
