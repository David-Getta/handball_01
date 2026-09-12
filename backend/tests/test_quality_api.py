"""
A minőség-jelentés végpontja: MEGMONDJA-E, HOGY JAVULT-E.

Miért itt: a felhasználó a gyenge feldolgozás után újrakalibrál és
újrafuttat — és pont azt a választ keresi, hogy jó irányba ment-e. A
puszta "72/100" ezt nem mondja meg; a korábbi próbálkozásokhoz
viszonyítva viszont igen.

Futtatás:
    python -m pytest tests/test_quality_api.py
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
    Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team)


def _meccs(match_id, date, jatekos_db, labdas):
    """Meccs adott létszámmal és labda-lefedettséggel — a pontszám ezekből jön."""
    meta = MatchMeta(match_id=match_id, home_team="A", away_team="B",
                     fps=25.0, date=date, calibrated=True)
    frames = []
    for t in range(40):
        players = [
            PlayerPosition(track_id=i,
                           team=Team.HOME if i % 2 == 0 else Team.AWAY,
                           x=20.0, y=10.0, source=PositionSource.MEASURED,
                           confidence=1.0)
            for i in range(jatekos_db)]
        frames.append(Frame(t=t, players=players,
                            ball=(Ball(x=20.0, y=10.0, confidence=1.0)
                                  if t < labdas else None)))
    return Match(meta, frames)


def _client(*meccsek):
    from handball.api.app import create_app
    root = tempfile.mkdtemp(prefix="hb_q_")
    os.environ["HANDBALL_DATA_DIR"] = root
    d = Path(root) / "data" / "matches"
    d.mkdir(parents=True, exist_ok=True)
    for m in meccsek:
        (d / f"{m.meta.match_id}.json").write_text(
            json.dumps(m.to_dict()), encoding="utf-8")
    return TestClient(create_app())


def test_a_jelentes_megmondja_hogy_javult_e():
    """A GYENGE régi és a JÓ új feldolgozás mellett a jelentés kiadja a
    korábbi pontszámot és a különbséget.

    Ez a visszacsatolás hiányzott: aki újrakalibrál, a "72/100"-ból nem
    tudja meg, hogy jó irányba ment-e — a "korábban 41/100" viszont
    megmondja.
    """
    regi = _meccs("regi", "2026-08-01", jatekos_db=4, labdas=5)   # gyenge
    uj = _meccs("uj", "2026-08-20", jatekos_db=14, labdas=40)     # jó
    c = _client(regi, uj)

    r = c.get("/matches/uj/quality")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["previous"], "a korábbi feldolgozás pontszáma hiányzik"
    elozo = body["previous"][0]
    assert elozo["match_id"] == "regi"
    assert elozo["score"] < body["score"]
    assert body["score_delta"] == body["score"] - elozo["score"]
    assert body["score_delta"] > 0


def test_az_elso_feldolgozasnal_nincs_mihez_viszonyitani():
    """Egyetlen meccsnél üres a lista — nem találunk ki összehasonlítást."""
    c = _client(_meccs("egyetlen", "2026-08-20", jatekos_db=14, labdas=40))
    body = c.get("/matches/egyetlen/quality").json()
    assert body["previous"] == []
    # A kulcs OTT VAN, az értéke None — a projekt szabálya szerint az
    # "nincs ítélet" nem hallgatólagos hiány, hanem kimondott None.
    assert "score_delta" in body and body["score_delta"] is None


def test_a_legfrissebb_all_elol_es_legfeljebb_harmat_mutatunk():
    """A kérdés nem az, mi volt fél éve, hanem hogy a LEGUTÓBBIHOZ
    képest javult-e — ezért dátum szerint, legfeljebb hármat."""
    meccsek = [_meccs(f"m{i}", f"2026-08-{i:02d}", jatekos_db=14, labdas=40)
               for i in range(1, 7)]
    c = _client(*meccsek)
    body = c.get("/matches/m1/quality").json()
    assert len(body["previous"]) == 3
    datumok = [p["date"] for p in body["previous"]]
    assert datumok == sorted(datumok, reverse=True), datumok
    assert "m1" not in [p["match_id"] for p in body["previous"]]
