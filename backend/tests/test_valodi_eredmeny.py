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


# ------------------------------------------------- tanítóadat-gyűjtés

def test_a_tanitoadat_gyujtes_hibai_erthetoek():
    """A gyűjtő-végpont kapuőrei: ismeretlen meccs → 404; videó nélküli
    meccs → 400 azzal, hogy összefűzöttnél a darabokat kell kijelölni;
    üres lista → 400. (A tényleges gyűjtés detektort igényel — azt a
    CLI-teszt és a valódi futás fedi.)"""
    c, _tmp = _client([_meccs("g1")])  # nincs video_path
    r = c.post("/dataset/collect", json={"match_ids": ["g1"]})
    assert r.status_code == 400
    assert "DARABOKAT" in r.json()["detail"]
    assert c.post("/dataset/collect",
                  json={"match_ids": ["nincs"]}).status_code == 404
    assert c.post("/dataset/collect",
                  json={"match_ids": []}).status_code == 400
    # Az állapot-végpont üresen is válaszol (a kliens 3 mp-enként kérdezi).
    st = c.get("/dataset/status").json()
    assert st["running"] is False


# --------------------------------------------------------- címkéző

def test_a_cimkezo_vegpontok_kore():
    """A beépített címkéző teljes köre: lista → címke-olvasás → mentés
    → visszaolvasás. A fájl szabványos YOLO-sor marad (külső eszközzel
    is kompatibilis), és az útvonal-védelem a könyvtár-ugrást fogja."""
    c, tmp = _client([])
    # A dataset szándékosan a data/ fán KÍVÜL él: a könyvtár-mentés
    # (export zip) a data/-t csomagolja, és a képhalmaz százmegás.
    gyoker = Path(tmp) / "dataset"
    (gyoker / "images" / "train").mkdir(parents=True)
    (gyoker / "labels" / "train").mkdir(parents=True)
    # 1x1-es érvényes JPEG helyett elég egy kamu-tartalmú .jpg: a lista
    # és a címke-végpontok nem dekódolják a képet.
    (gyoker / "images" / "train" / "a.jpg").write_bytes(b"jpg")
    (gyoker / "labels" / "train" / "a.txt").write_text(
        "0 0.5 0.5 0.1 0.2\n", encoding="utf-8")

    kepek = c.get("/dataset/images").json()["images"]
    assert kepek == [{"split": "train", "name": "a.jpg", "boxes": 1}]

    r = c.get("/dataset/labels/train/a.jpg").json()
    assert r["boxes"] == [[0, 0.5, 0.5, 0.1, 0.2]]

    r = c.post("/dataset/labels/train/a.jpg",
               json={"boxes": [[1, 0.3, 0.4, 0.05, 0.05],
                               [0, 0.6, 0.6, 0.2, 0.3]]})
    assert r.status_code == 200 and r.json()["saved"] == 2
    ujra = c.get("/dataset/labels/train/a.jpg").json()["boxes"]
    assert ujra[0][0] == 1 and len(ujra) == 2
    # A fájl YOLO-sor maradt.
    szoveg = (gyoker / "labels" / "train" / "a.txt").read_text(
        encoding="utf-8")
    assert szoveg.startswith("1 0.3")

    # Kapuőrök: rossz osztály / érték / fájlnév / hiányzó kép.
    assert c.post("/dataset/labels/train/a.jpg",
                  json={"boxes": [[2, .5, .5, .1, .1]]}).status_code == 400
    assert c.post("/dataset/labels/train/a.jpg",
                  json={"boxes": [[0, 1.5, .5, .1, .1]]}).status_code == 400
    assert c.get("/dataset/labels/train/../a.jpg").status_code in (400, 404)
    assert c.get("/dataset/labels/train/nincs.jpg").status_code == 404
    assert c.get("/dataset/image/train/nincs.jpg").status_code == 404


def test_a_tanitas_kapuorei():
    """Tanítás gombra: adathalmaz nélkül 400 azzal, hogy előbb gyűjtés
    és címkézés kell; az állapot-végpont üresen is válaszol."""
    c, _tmp = _client([])
    r = c.post("/dataset/train", json={"epochs": 60})
    assert r.status_code == 400
    assert "Tanítóadat gyűjtése" in r.json()["detail"]
    st = c.get("/dataset/train-status").json()
    assert st["running"] is False


def test_a_tanitas_merszamai_emberi_alakban():
    """A tanítás végén a mérőszám mondja meg, MEGÉRTE-e — a kinyerés
    az ultralytics eredmény-objektum alakját tükrözi, és ha az más,
    mérőszám nélkül sem törik (üres dict)."""
    from handball.api.app import train_metrics

    class _Tomb:
        def __init__(self, ertekek):
            self._e = ertekek

        def tolist(self):
            return self._e

    class _Box:
        ap_class_index = _Tomb([0, 1])
        ap50 = _Tomb([0.82, 0.61])

    class _Eredmeny:
        results_dict = {"metrics/mAP50(B)": 0.715,
                        "metrics/precision(B)": 0.8,
                        "metrics/recall(B)": 0.66}
        box = _Box()
        names = {0: "person", 1: "ball"}

    m = train_metrics(_Eredmeny())
    assert m["map50"] == 71.5
    assert m["map50_ball"] == 61.0
    assert m["map50_person"] == 82.0
    assert m["precision"] == 80.0 and m["recall"] == 66.0

    # Ismeretlen alak: nem törik, üres marad.
    assert train_metrics(object()) == {}


def test_a_tanitas_vedohaloja_csak_a_jobb_modellt_allitja_elesbe():
    """A tanítás nem cserélhet vakon: a labda AP50 dönt; ha nincs mihez
    mérni (első tanítás), élesbe áll; ha rosszabb lett, a mostani marad
    — és az indok magyarul megmondja, miért."""
    from handball.api.app import should_install

    # Első tanítás: nincs korábbi mérés → élesbe áll.
    d = should_install({"map50": 60.0, "map50_ball": 50.0}, {})
    assert d["install"] is True and "első tanítás" in d["reason"]
    # Javult a labda → csere.
    d = should_install({"map50_ball": 61.0}, {"map50_ball": 55.0})
    assert d["install"] is True and "61%" in d["reason"]
    # Rosszabb lett a labda → a mostani marad, indokkal.
    d = should_install({"map50_ball": 48.0, "map50": 70.0},
                       {"map50_ball": 55.0, "map50": 60.0})
    assert d["install"] is False and "rosszabb" in d["reason"]
    # Ha nincs labda-sor, az összesített mAP50 dönt.
    d = should_install({"map50": 70.0}, {"map50": 65.0})
    assert d["install"] is True and "mAP50" in d["reason"]
    # Mérőszám nélküli új modell: nem blokkolunk vakon.
    assert should_install({}, {"map50": 65.0})["install"] is True


def test_a_shutdown_vegpont_cserelheto_kilepessel():
    """A fél-frissülés őre: a /shutdown a régi motort állítja le. A
    kilépés-függvény cserélhető (app.state.exit_fn) — a teszt így nem
    hal bele; azt nézzük, hogy a végpont válaszol ÉS tényleg meghívja."""
    import time

    c, _tmp = _client([])
    hivasok = []
    c.app.state.exit_fn = lambda code: hivasok.append(code)
    r = c.post("/shutdown")
    assert r.status_code == 200 and r.json()["stopping"] is True
    for _ in range(30):  # a kilépés késleltetett szálon fut
        if hivasok:
            break
        time.sleep(0.1)
    assert hivasok == [0]


def test_a_diagnosztika_viszi_a_horgonyzas_aranyt():
    """A svenkelő kameránál a fejlesztő első kérdése: hány kockán
    sikerült a kalibrált képhez mérni. Régi mentésen None — de a kulcs
    akkor is ott van, hogy a hiány látsszon."""
    m = _meccs("pan1")
    m.meta.pan_anchor_pct = 42.5
    c, _tmp = _client([m, _meccs("pan0")])
    assert c.get("/matches/pan1/diagnostics").json()["pan_anchor_pct"] == 42.5
    regi = c.get("/matches/pan0/diagnostics").json()
    assert "pan_anchor_pct" in regi and regi["pan_anchor_pct"] is None


def test_a_view3d_esemenyeket_es_ugrast_is_visz():
    """A böngészős 3D/VR nézet paritása az appbeli 3D-vel: az események
    (gól/lövés/eladás) beágyazva, ⏮/⏭ gombok és jelenet-felirat."""
    from handball.pipeline.view3d_html import _compact_data, view3d_html

    m = _meccs("v3e", golok_home=2, golok_away=1)
    adat = _compact_data(m)
    assert len(adat["events"]) == 3
    assert {e[1] for e in adat["events"]} == {"g"}
    assert sorted(e[2] for e in adat["events"]) == [0, 1, 1]
    assert adat["events"] == sorted(adat["events"], key=lambda e: e[0])
    oldal = view3d_html(m)
    for jel in ('id="elozo"', 'id="kov"', 'id="felirat"',
                "esemenyUgras", "BracketRight"):
        assert jel in oldal, jel


def test_a_diagnosztika_viszi_a_kalibracio_illeszkedest():
    m = _meccs("cf1")
    m.meta.calib_fit = {"mean_fit": 0.7, "min_fit": 0.2, "worst_t": 40,
                        "points": [[0, 0.7], [40, 0.2]]}
    c, _tmp = _client([m, _meccs("cf0")])
    d = c.get("/matches/cf1/diagnostics").json()
    assert d["calib_fit"]["min_fit"] == 0.2 and d["calib_fit"]["worst_t"] == 40
    regi = c.get("/matches/cf0/diagnostics").json()
    assert "calib_fit" in regi and regi["calib_fit"] is None


def test_a_konyvtar_sor_viszi_a_kalibracio_illeszkedes_minimumat():
    m = _meccs("cm1")
    m.meta.calib_fit = {"mean_fit": 0.6, "min_fit": 0.2, "worst_t": 10,
                        "points": [[0, 0.6], [10, 0.2]]}
    c, _tmp = _client([m, _meccs("cm0")])
    sorok = {s["match_id"]: s for s in c.get("/matches").json()["matches"]}
    assert sorok["cm1"]["calib_min_fit"] == 0.2
    assert sorok["cm0"]["calib_min_fit"] is None
