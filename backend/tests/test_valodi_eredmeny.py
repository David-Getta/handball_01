"""
Tesztek a VALÓDI (jegyzőkönyvi) eredményre — a pontosság-tükör.

Az edző fejből tudja a végeredményt; ha megadja, az a legerősebb
mérce, ami csak létezik: nem heurisztika, hanem tény. A minőség-
jelentés ehhez méri a felismerést, és két kimondható hibát ismer:
a két csapat FORDÍTVA van kiosztva (a felcserélt valódi eredmény
sokkal közelebb áll), vagy a felismerés egyszerűen messze van.

Futtatás:
    python -m pytest tests/test_valodi_eredmeny.py
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
from handball.pipeline.quality import (  # noqa: E402
    REAL_SCORE_DIFF_WARN, compute_quality_report, next_action,
)


def _meccs(match_id="m1", n=50, golok_home=0, golok_away=0,
           real=None):
    """Kis meccs, ahol a 'felismert' gólokat kézi javítás adja be —
    a detect_shots a meta.event_overrides listát tiszteletben tartja,
    tehát a pontosság-tükör a VALÓDI úton kapja a felismert gólszámot."""
    meta = MatchMeta(match_id=match_id, home_team="Mi", away_team="Ok",
                     fps=10.0)
    if real is not None:
        meta.real_goals_home, meta.real_goals_away = real
    ov = []
    t = 1
    for _ in range(golok_home):
        ov.append({"op": "add", "t": t, "type": "goal", "team": "home"})
        t += 3
    for _ in range(golok_away):
        ov.append({"op": "add", "t": t, "type": "goal", "team": "away"})
        t += 3
    meta.event_overrides = ov
    frames = [Frame(t=i, players=[
        PlayerPosition(track_id=1, team=Team.HOME, x=10.0, y=8.0),
        PlayerPosition(track_id=2, team=Team.AWAY, x=30.0, y=12.0),
    ], ball=Ball(x=20.0, y=10.0)) for i in range(n)]
    return Match(meta, frames)


# --------------------------------------------------------------- modell

def test_a_valodi_eredmeny_tuleli_a_mentest():
    m = _meccs(real=(25, 24))
    ujra = Match.from_json(m.to_json())
    assert ujra.meta.real_goals_home == 25
    assert ujra.meta.real_goals_away == 24


def test_a_regi_mentes_valodi_eredmeny_nelkul_is_betolt():
    """Előre-hátra kompatibilitás: a mező előtti JSON-okban nincs
    real_goals_* — None-ként kell betöltődniük, ítélet nélkül."""
    m = _meccs()
    d = json.loads(m.to_json())
    d["meta"].pop("real_goals_home")
    d["meta"].pop("real_goals_away")
    ujra = Match.from_dict(d)
    assert ujra.meta.real_goals_home is None
    assert ujra.meta.real_goals_away is None


# ------------------------------------------------------------- minőség

def test_a_nagy_elteres_figyelmeztetest_kap_teendovel():
    m = _meccs(golok_home=2, golok_away=1, real=(12, 11))
    q = compute_quality_report(m)
    talalat = [w for w in q["warnings"]
               if "messze van a megadott valóditól" in w]
    assert talalat, q["warnings"]
    teendo = next_action(talalat)
    assert teendo and "Események" in teendo, teendo


def test_a_forditott_kiosztast_nevvel_mondja_ki():
    """A felismert 8:1 a valódi 1:8 TÜKÖRKÉPE — ez nem 'pontatlanság',
    hanem csapatcsere, és a teendő is más: a ⇄ gomb, nem az
    esemény-lista."""
    m = _meccs(golok_home=8, golok_away=1, real=(1, 8))
    q = compute_quality_report(m)
    talalat = [w for w in q["warnings"]
               if "fordítva osztotta ki" in w]
    assert talalat, q["warnings"]
    teendo = next_action(talalat)
    assert teendo and "csapatcsere" in teendo, teendo


def test_a_kis_elteres_nem_riaszt():
    """Két-három gólnyi eltérés normális felismerési szórás — attól még
    nem hibás a feldolgozás, és a 'hibátlan = üres figyelmeztetés-lista'
    szabály többet ér, mint egy okoskodó megjegyzés."""
    m = _meccs(golok_home=8, golok_away=6,
               real=(8 + REAL_SCORE_DIFF_WARN - 3, 6 + 1))
    q = compute_quality_report(m)
    assert not [w for w in q["warnings"] if "valódi" in w], q["warnings"]


def test_valodi_eredmeny_nelkul_nincs_uj_jelzes():
    m = _meccs(golok_home=2, golok_away=1)
    q = compute_quality_report(m)
    assert not [w for w in q["warnings"]
                if "valódi" in w or "fordítva osztotta" in w]


# ------------------------------------------------------------------ API

TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient


def _client(meccsek):
    tmp = tempfile.mkdtemp(prefix="hb_real_")
    os.environ["HANDBALL_DATA_DIR"] = tmp
    d = Path(tmp) / "data" / "matches"
    d.mkdir(parents=True, exist_ok=True)
    for m in meccsek:
        (d / f"{m.meta.match_id}.json").write_text(
            json.dumps(m.to_dict()), encoding="utf-8")
    from handball.api.app import create_app
    return TestClient(create_app()), tmp


def test_a_patch_menti_es_a_lista_mutatja():
    c, tmp = _client([_meccs("p1")])
    r = c.patch("/matches/p1", json={"real_goals_home": 25,
                                     "real_goals_away": 24})
    assert r.status_code == 200
    assert r.json()["real_goals_home"] == 25

    sor = [m for m in c.get("/matches").json()["matches"]
           if m["match_id"] == "p1"][0]
    assert sor["real_goals_home"] == 25
    assert sor["real_goals_away"] == 24

    # Lemezre is kiment: újraindítás után is megvan.
    mentett = json.loads(
        (Path(tmp) / "data" / "matches" / "p1.json").read_text(
            encoding="utf-8"))
    assert mentett["meta"]["real_goals_home"] == 25

    # null = törlés (a kulcs jelenléte számít).
    r = c.patch("/matches/p1", json={"real_goals_home": None,
                                     "real_goals_away": None})
    assert r.status_code == 200
    sor = [m for m in c.get("/matches").json()["matches"]
           if m["match_id"] == "p1"][0]
    assert sor["real_goals_home"] is None


def test_a_rossz_ertek_ertheto_hibat_kap():
    c, _tmp = _client([_meccs("p2")])
    assert c.patch("/matches/p2",
                   json={"real_goals_home": 100,
                         "real_goals_away": 1}).status_code == 400
    assert c.patch("/matches/p2",
                   json={"real_goals_home": "sok",
                         "real_goals_away": 1}).status_code == 400


def test_a_valodi_eredmeny_a_minoseg_vegponton_is_atut():
    """A teljes kör: PATCH-elt valódi eredmény → a /quality végpont
    figyelmeztet a nagy eltérésre. A gyorsítótár-ürítésen múlik — ha a
    PATCH nem dobná el a minőség-kivonatot, a régi (néma) jelentés
    jönne vissza."""
    c, _tmp = _client([_meccs("p3", golok_home=2, golok_away=1)])
    eleje = c.get("/matches/p3/quality").json()
    assert not [w for w in eleje["warnings"] if "valóditól" in w]
    c.patch("/matches/p3", json={"real_goals_home": 12,
                                 "real_goals_away": 11})
    utana = c.get("/matches/p3/quality").json()
    assert [w for w in utana["warnings"]
            if "messze van a megadott valóditól" in w], utana["warnings"]


def test_a_diagnosztika_egyben_hozza_a_kepet():
    """A fejlesztő-visszajelzés végpontja: minőség + eseményszám +
    beállítások + eredmények EGY JSON-ban — a képernyőkép helyett.
    Videót nem tartalmaz, és fél lábon (hibás rétegnél) is célba ér."""
    m = _meccs("d1", golok_home=3, golok_away=2, real=(20, 19))
    c, tmp = _client([m])
    # A betöltő a javításokat a MELLÉKFÁJLBÓL olvassa (a meta-belit
    # felülírja) — a fixture ezért a sidecart is kiírja.
    (Path(tmp) / "data" / "matches" / "d1.events.json").write_text(
        json.dumps({"overrides": m.meta.event_overrides}),
        encoding="utf-8")
    c.post("/matches/d1/event-overrides",
           json={"overrides": m.meta.event_overrides})
    r = c.get("/matches/d1/diagnostics")
    assert r.status_code == 200
    d = r.json()
    assert d["num_frames"] == 50
    assert d["real_goals_home"] == 20
    assert "quality" in d and "warnings" in d["quality"]
    assert "next_action" in d["quality"]
    assert d["event_counts"].get("goal") == 5
    assert d["goals_home"] == 3 and d["goals_away"] == 2
    # Videó-utat nem szivárogtat (personal adat lehetne).
    assert "video_path" not in json.dumps(d)

    assert c.get("/matches/nincs/diagnostics").status_code == 404


# ---------------------------------------------------- böngészős 3D / VR

def test_a_bongeszos_3d_oldal_osszeall():
    """A /view3d WebXR-képes HTML-t ad: three.js + VR-gomb + beágyazott,
    RITKÍTOTT követés-adat (legfeljebb ~6 kép/mp — a méret miatt)."""
    from handball.pipeline.view3d_html import (VIEW3D_MAX_FPS,
                                               _compact_data, view3d_html)

    m = _meccs("v3d", n=100)  # 10 fps → ritkítva ~5-6 fps-re
    oldal = view3d_html(m)
    assert "three.module.js" in oldal, "nincs three.js-betöltés"
    assert "VRButton" in oldal, "nincs VR-gomb (WebXR)"
    assert "Mi vs Ok" in oldal, "nincs cím a csapatnevekből"
    assert "WASD" in oldal, "nincs kezelés-súgó"

    adat = _compact_data(m)
    assert len(adat["frames"]) <= 100 * VIEW3D_MAX_FPS / 10.0 + 1, (
        "a beágyazott adat nincs ritkítva")

    # Jelenet-ugrás: a ?t= paramétert az oldal érti (URLSearchParams),
    # az appból az aktuális pillanat így folytatódik a böngészőben.
    assert "URLSearchParams" in oldal, "nincs ?t= jelenet-ugrás"

    c, _tmp = _client([m])
    r = c.get("/matches/v3d/view3d")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert c.get("/matches/nincs/view3d").status_code == 404
