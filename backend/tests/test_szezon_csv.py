"""
Tesztek a szezon-CSV-re (GET /library/roster.csv).

A meccs-szintű játékos-CSV megvan; a SZEZON-szintű eddig hiányzott —
pedig a hét végi kimutatás tipikus edzői feladat ("küldd el Excelben,
ki hány gólnál jár"), és a képernyőről kézzel kellett kimásolni.

Futtatás:
    python -m pytest tests/test_szezon_csv.py
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

from handball.models.tracking import (  # noqa: E402
    Ball, Frame, Match, MatchMeta, PlayerPosition, Team,
)


def _meccs(match_id):
    meta = MatchMeta(match_id=match_id, home_team="Mi", away_team="Ok",
                     fps=10.0, date="2026-08-01")
    frames = [
        Frame(t=i, players=[
            PlayerPosition(track_id=1, team=Team.HOME, x=10.0, y=10.0,
                           jersey_number=7),
            PlayerPosition(track_id=2, team=Team.HOME, x=12.0, y=8.0,
                           jersey_number=9),
        ], ball=Ball(x=20.0, y=10.0))
        for i in range(40)
    ]
    return Match(meta, frames)


def _client():
    tmp = tempfile.mkdtemp(prefix="hb_szcsv_")
    os.environ["HANDBALL_DATA_DIR"] = tmp
    d = Path(tmp) / "data" / "matches"
    d.mkdir(parents=True, exist_ok=True)
    for m in (_meccs("cs1"), _meccs("cs2")):
        (d / f"{m.meta.match_id}.json").write_text(
            json.dumps(m.to_dict()), encoding="utf-8")
    from handball.api.app import create_app
    return TestClient(create_app())


def test_a_szezon_csv_letoltheto_es_excel_barat():
    c = _client()
    # Név is: a kimutatásban a név a lényeg, nem a szám.
    c.post("/library/players", json={"team": "Mi", "jersey": 7,
                                     "name": "Kovács"})
    r = c.get("/library/roster.csv", params={"team": "Mi"})
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert 'filename="szezon_Mi.csv"' in r.headers["content-disposition"]

    szoveg = r.content.decode("utf-8")
    # BOM: a magyar Excel enélkül szétesett ékezeteket mutat.
    assert szoveg.startswith("﻿")
    sorok = szoveg.lstrip("﻿").strip().split("\r\n")
    assert sorok[0].startswith("mezszam;nev;meccsek;")
    # A #7 sora: név + 2 meccs.
    hetes = [s_ for s_ in sorok[1:] if s_.startswith("7;")]
    assert hetes and hetes[0].startswith("7;Kovács;2;"), sorok


def test_a_csv_ugyanazt_mondja_mint_a_keret_lap():
    """ŐR: a CSV a keret-lap számolásából él — ha külön számolna, a
    képernyő és a kimutatás széttartana, és a vezetőség mást látna,
    mint az edző."""
    c = _client()
    keret = c.get("/library/roster", params={"team": "Mi"}).json()
    csv_sorok = (c.get("/library/roster.csv", params={"team": "Mi"})
                 .content.decode("utf-8").lstrip("﻿").strip()
                 .split("\r\n"))
    assert len(csv_sorok) - 1 == len(keret["players"])
    for r_, sor in zip(keret["players"], csv_sorok[1:]):
        mezok = sor.split(";")
        assert int(mezok[0]) == r_["jersey"]
        assert int(mezok[2]) == r_["matches"]
        assert int(mezok[3]) == r_["goals"]


def test_ismeretlen_csapatra_ures_tabla():
    """Ismeretlen csapatra fejléces, de üres CSV — nem hiba: a
    kimutatás "még nincs adat" állapota is kimutatás."""
    c = _client()
    r = c.get("/library/roster.csv", params={"team": "Nincs Ilyen"})
    assert r.status_code == 200
    sorok = r.content.decode("utf-8").lstrip("﻿").strip().split("\r\n")
    assert len(sorok) == 1 and sorok[0].startswith("mezszam;")
