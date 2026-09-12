"""
Tesztek a szezon-összkép végpontra (/library/summary).

Futtatás:
    python -m pytest tests/test_library_summary.py
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Izolált adat-mappa, hogy a teszt ne írjon a fejlesztői data/ alá.
_tmp = tempfile.mkdtemp(prefix="handball_summary_test_")
os.environ["HANDBALL_DATA_DIR"] = _tmp

import json  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

# A CI minimál-környezetében nincs FastAPI — ott ez a modul kihagyja magát.
TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient

from handball.api.app import create_app  # noqa: E402
from handball.sim.match_simulator import simulate_ground_truth  # noqa: E402


def _client_with_matches(n: int = 2, duration_s: float = 3):
    # Más API-tesztmodulok is állítják a HANDBALL_DATA_DIR-t import-időben —
    # itt HÍVÁSKOR állítjuk vissza a sajátunkra (sorrend-független futás).
    os.environ["HANDBALL_DATA_DIR"] = _tmp
    matches_dir = Path(_tmp) / "data" / "matches"
    matches_dir.mkdir(parents=True, exist_ok=True)
    for old in matches_dir.glob("*.json"):
        old.unlink()
    ids = []
    for i in range(n):
        m = simulate_ground_truth(duration_s=duration_s, fps=25.0,
                                  seed=i + 1)
        m.meta.match_id = f"summary-{i}"
        (matches_dir / f"{m.meta.match_id}.json").write_text(
            json.dumps(m.to_dict()), encoding="utf-8")
        ids.append(m.meta.match_id)
    return TestClient(create_app()), ids


def test_summary_counts_and_per_match():
    client, ids = _client_with_matches(2)
    r = client.get("/library/summary")
    assert r.status_code == 200
    s = r.json()
    assert s["matches"] == 2
    assert s["total_duration_s"] > 0
    # A szimulátor mindig ad csapatneveket → a névsor nem üres.
    assert len(s["teams"]) >= 1
    # A meccsenkénti kivonatban minden meccs pontosan egyszer szerepel.
    per_ids = [d["match_id"] for d in s["per_match"]]
    assert sorted(per_ids) == sorted(ids)
    for d in s["per_match"]:
        assert d["duration_s"] > 0
        assert d["distance_m"] >= 0
        assert d["goals_home"] >= 0 and d["goals_away"] >= 0
        # A beálló-terhelés mező jelen van (None, ha nem mérhető).
        assert "pivot_share_home" in d and "pivot_share_away" in d
        assert "pass_avg_home" in d and "pass_avg_away" in d
    # Az összesített mutatók a meccsenkéntiek összegei.
    assert s["sprints"] == sum(d["sprints"] for d in s["per_match"])
    assert s["saves"] == sum(d["saves"] for d in s["per_match"])
    for d in s["per_match"]:
        assert d["saves"] <= d["shots"]  # védés csak kapura tartó lövésből
    assert s["goals"] == sum(
        d["goals_home"] + d["goals_away"] for d in s["per_match"])


def test_summary_cache_refreshes_on_rename():
    client, ids = _client_with_matches(1)
    first = client.get("/library/summary").json()
    # Átnevezés után az új név jelenik meg (a gyorsítótár nem ragad be).
    client.patch(f"/matches/{ids[0]}", json={"home_team": "Új Név KC"})
    second = client.get("/library/summary").json()
    assert second["per_match"][0]["home_team"] == "Új Név KC"
    assert first["per_match"][0]["home_team"] != "Új Név KC"


def test_summary_empty_library():
    os.environ["HANDBALL_DATA_DIR"] = tempfile.mkdtemp(
        prefix="handball_summary_empty_")
    client = TestClient(create_app())
    s = client.get("/library/summary").json()
    assert s["matches"] == 0
    assert s["per_match"] == []
    assert s["goals"] == 0 and s["distance_km"] == 0.0


def test_summary_includes_trend_fields():
    """A meccsenkénti kivonatban ott vannak a szezon-trend mezők (xG és
    szabad lövés-arány) — None is érvényes, ha nem számolható."""
    client, ids = _client_with_matches(1)
    d = client.get("/library/summary").json()["per_match"][0]
    for k in ("xg_home", "xg_away", "free_pct_home", "free_pct_away"):
        assert k in d
    if d["xg_home"] is not None:
        assert d["xg_home"] >= 0 and d["xg_away"] >= 0


def test_library_leaders_endpoint():
    """A szezon-toplisták végpont mezszám alapján összegez a teljes
    könyvtárból; minden kategória lista, value szerint csökkenő."""
    client, ids = _client_with_matches(2)
    r = client.get("/library/leaders")
    assert r.status_code == 200
    data = r.json()
    for key in ("goals", "blocks", "steals", "saves", "assists"):
        assert key in data and isinstance(data[key], list)
        vals = [e["value"] for e in data[key]]
        assert vals == sorted(vals, reverse=True)
        for e in data[key]:
            assert e["team"] and isinstance(e["jersey"], int)
            assert e["value"] >= 1
        assert len(data[key]) <= 5


def test_library_roster_endpoint():
    """Keret-lap: a csapat ÖSSZES ismert mezszáma egy táblában.

    A toplisták az öt legjobbat adják — a keret-lap MINDENKIT, aki a
    könyvtárban mezszámmal szerepel: ez a játékos szemszöge (hol tart a
    SAJÁT sorom), és az edzőé, amikor a teljes keretet nézi végig.
    """
    client, ids = _client_with_matches(2)
    teams = client.get("/library/summary").json()["teams"]
    assert teams, "a szimulátor csapatnév nélkül adott vissza meccset"
    r = client.get("/library/roster", params={"team": teams[0]})
    assert r.status_code == 200
    data = r.json()
    assert data["team"] == teams[0]
    assert data["note"], "a lap nem mondja ki a mezszám-feltételt"
    mezek = [p["jersey"] for p in data["players"]]
    assert mezek == sorted(mezek), "a keret nem mezszám szerint rendezett"
    for p in data["players"]:
        for k in ("matches", "goals", "assists", "blocks", "steals",
                  "saves"):
            assert k in p and p[k] >= 0
        # A meccs-darabszám nélkül egy alacsony gólszám félrevezet
        # (kevés játék vagy gyenge forma? — két külön teendő).
        assert p["matches"] >= 1


def test_a_keret_es_a_toplista_ugyanabbol_a_szamolasbol_el():
    """A két végpont NEM tarthat széjjel.

    A toplista és a keret-lap ugyanazt a szezon-összeget mutatja, csak
    más metszetben; ha külön számolnák, előbb-utóbb más számot írnának
    ugyanarról a játékosról. Ezért egy közös tallyzó adja mindkettőt —
    ez a teszt azt méri, hogy tényleg egyezik.
    """
    # Hosszabb szimuláció: a pár másodperces meccsen egyetlen
    # toplista-sor sem születik, és a teszt NÉMÁN átmenne.
    client, ids = _client_with_matches(2, duration_s=45)
    leaders = client.get("/library/leaders").json()
    assert any(leaders[k] for k in leaders), (
        "egyetlen toplista-sor sincs — a teszt nem mérne semmit")
    for kategoria in ("goals", "assists", "blocks", "steals", "saves"):
        for sor in leaders[kategoria]:
            keret = client.get("/library/roster",
                               params={"team": sor["team"]}).json()
            egyezo = [p for p in keret["players"]
                      if p["jersey"] == sor["jersey"]]
            assert egyezo, (
                f"a toplista {sor['team']} #{sor['jersey']} játékosa "
                "hiányzik a keret-lapról")
            assert egyezo[0][kategoria] == sor["value"], (
                f"{kategoria}: toplista {sor['value']} vs keret "
                f"{egyezo[0][kategoria]}")


def test_ismeretlen_csapat_keret_lapja_ures_de_nem_hiba():
    """Nem létező csapatnévre üres keret jár, nem 500 — a kliens
    csapatnév-listája és a könyvtár elcsúszhat (átnevezés, törlés)."""
    client, ids = _client_with_matches(1)
    r = client.get("/library/roster", params={"team": "Nincs Ilyen SE"})
    assert r.status_code == 200
    assert r.json()["players"] == []


def test_jatekos_nevek_mezszamhoz_es_a_lapokon():
    """Mezszám → NÉV, csapat-szinten — és minden lapon ott is van.

    Az egész termék "#7"-et mondott. Az edző nem számokban gondolkodik,
    a játékos pedig a saját nevét keresi. A név a CSAPATHOZ és a
    mezszámhoz tartozik, nem egy meccshez: a mezszám a szezonban
    stabil, a track-azonosító nem — egy helyen felvitt név minden
    korábbi és későbbi meccsen is látszik.
    """
    client, ids = _client_with_matches(1)
    teams = client.get("/library/summary").json()["teams"]
    csapat = teams[0]
    keret = client.get("/library/roster", params={"team": csapat}).json()
    assert keret["players"], "a szimulált meccsen egyetlen mezszám sincs"
    mez = keret["players"][0]["jersey"]
    # Kezdetben névtelen — de a mező LÉTEZIK (nem hiányzó kulcs).
    assert keret["players"][0]["name"] is None

    r = client.post("/library/players",
                    json={"team": csapat, "jersey": mez, "name": "Kovács"})
    assert r.status_code == 200 and r.json()["name"] == "Kovács"

    # A keret-lapon látszik…
    keret2 = client.get("/library/roster", params={"team": csapat}).json()
    sor = [p for p in keret2["players"] if p["jersey"] == mez][0]
    assert sor["name"] == "Kovács"
    # …és a játékos-görbén is (ebből lesz a szezon-lap címe).
    trend = client.get("/players/trend",
                       params={"team": csapat, "jersey": mez}).json()
    assert trend["name"] == "Kovács"

    # Üres név TÖRLI a hozzárendelést (a szám marad, névtelen lesz).
    client.post("/library/players",
                json={"team": csapat, "jersey": mez, "name": "   "})
    keret3 = client.get("/library/roster", params={"team": csapat}).json()
    sor3 = [p for p in keret3["players"] if p["jersey"] == mez][0]
    assert sor3["name"] is None


def test_a_nev_kenyelem_nem_adat():
    """Hiányzó vagy sérült név-fájl nem viheti el a keretet.

    A név KÉNYELEM: nélküle a program a mezszámokkal ugyanúgy működik.
    Ha a tárolt fájl sérült, a lapoknak akkor is meg kell jelenniük —
    egy elrontott név-fájl miatt nem veszhet el a szezon-statisztika.
    """
    client, ids = _client_with_matches(1)
    teams = client.get("/library/summary").json()["teams"]
    (Path(_tmp) / "data" / "players.json").write_text(
        "{ ez nem json", encoding="utf-8")
    r = client.get("/library/roster", params={"team": teams[0]})
    assert r.status_code == 200
    assert r.json()["players"], "a sérült név-fájl elvitte a keretet"
    assert all(p["name"] is None for p in r.json()["players"])
