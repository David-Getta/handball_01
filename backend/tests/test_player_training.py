"""
Tesztek az EGYÉNI edzés-fókuszra (training.player_training_focus).

A csapat-szintű fókusz megmondja, mit gyakoroljon a csapat — a játékos
viszont a saját nevét keresi, és az edző is emberre bontva osztja ki a
hét feladatait.

Futtatás:
    python -m pytest tests/test_player_training.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (  # noqa: E402
    Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.training import (  # noqa: E402
    PLAYER_MAX_ITEMS, player_training_focus,
)


def _meta(fps=25.0):
    return MatchMeta(match_id="ptf", home_team="A", away_team="B", fps=fps)


def _match(frames=None):
    return Match(_meta(), frames or [])


def _ures(_m, _c=None):
    return {"home": {"top": None, "players": []},
            "away": {"top": None, "players": []}}


def _csend(monkeypatch):
    """Minden forrás-réteg hallgat — a tesztek egyesével szólaltatják meg."""
    monkeypatch.setattr(
        "handball.pipeline.decisions.pressure_sensitive_players", _ures)
    monkeypatch.setattr(
        "handball.pipeline.decisions.tired_turnover_players", _ures)
    monkeypatch.setattr("handball.pipeline.xg.match_xg",
                        lambda m, c=None: {"shooters": []})
    monkeypatch.setattr("handball.pipeline.stats.player_fatigue",
                        lambda m, c=None: [])
    monkeypatch.setattr("handball.pipeline.attack_types.risky_passers",
                        _ures)
    monkeypatch.setattr(
        "handball.pipeline.momentum.clutch_turnover_players", _ures)


# ---- A négy forrás egyenként megszólal -------------------------------


def test_nyomas_alatti_kiadas(monkeypatch):
    _csend(monkeypatch)
    monkeypatch.setattr(
        "handball.pipeline.decisions.pressure_sensitive_players",
        lambda m, c=None: {
            "home": {"players": [],
                     "top": {"player_id": 7, "jersey": 9,
                             "press_events": 10, "press_to": 6}},
            "away": {"players": [], "top": None}})
    rec = player_training_focus(_match())["home"]["players"]
    assert len(rec) == 1
    assert rec[0]["player_id"] == 7 and rec[0]["jersey"] == 9
    assert rec[0]["items"][0]["area"] == "labdabiztonság"
    assert "60%" in rec[0]["items"][0]["why"], rec[0]["items"][0]["why"]


def test_faradt_labdakezeles(monkeypatch):
    _csend(monkeypatch)
    monkeypatch.setattr(
        "handball.pipeline.decisions.tired_turnover_players",
        lambda m, c=None: {
            "home": {"fh": {}, "sh": {},
                     "top": {"player_id": 3, "jersey": 4,
                             "fh": 1, "sh": 5}},
            "away": {"fh": {}, "sh": {}, "top": None}})
    rec = player_training_focus(_match())["home"]["players"]
    assert rec and rec[0]["items"][0]["title"] == "Fáradt labdakezelés"
    assert "1 → 5" in rec[0]["items"][0]["why"]


def test_befejezes_a_helyzeteihez_kepest(monkeypatch):
    _csend(monkeypatch)
    monkeypatch.setattr(
        "handball.pipeline.xg.match_xg",
        lambda m, c=None: {"shooters": [
            # Elmarad a helyzeteitől → jár neki tétel.
            {"player_id": 11, "team": "away", "shots": 8, "goals": 1,
             "xg": 3.2},
            # Kevés lövés → a szórás dönt, nem szólunk.
            {"player_id": 12, "team": "away", "shots": 2, "goals": 0,
             "xg": 1.5},
            # A helyzetei FÖLÖTT teljesít → nem edzés-fókusz.
            {"player_id": 13, "team": "away", "shots": 9, "goals": 6,
             "xg": 3.0},
        ]})
    rec = player_training_focus(_match())["away"]["players"]
    assert [r["player_id"] for r in rec] == [11], rec
    assert rec[0]["items"][0]["area"] == "befejezés"
    assert "−2.2" in rec[0]["items"][0]["why"], rec[0]["items"][0]["why"]


def test_kondicio(monkeypatch):
    _csend(monkeypatch)
    monkeypatch.setattr(
        "handball.pipeline.stats.player_fatigue",
        lambda m, c=None: [
            {"track_id": 5, "team": "home", "drop_pct": 40.0},
            {"track_id": 6, "team": "home", "drop_pct": 5.0},
        ])
    rec = player_training_focus(_match())["home"]["players"]
    assert [r["player_id"] for r in rec] == [5]
    assert rec[0]["items"][0]["area"] == "kondíció"


def test_emberenkent_legfeljebb_ket_tetel(monkeypatch):
    """A fókusz attól fókusz, hogy kevés: négy jel esetén is legfeljebb
    PLAYER_MAX_ITEMS tétel jut egy emberre."""
    _csend(monkeypatch)
    monkeypatch.setattr(
        "handball.pipeline.decisions.pressure_sensitive_players",
        lambda m, c=None: {
            "home": {"players": [],
                     "top": {"player_id": 7, "jersey": 9,
                             "press_events": 10, "press_to": 6}},
            "away": {"players": [], "top": None}})
    monkeypatch.setattr(
        "handball.pipeline.decisions.tired_turnover_players",
        lambda m, c=None: {
            "home": {"fh": {}, "sh": {},
                     "top": {"player_id": 7, "jersey": 9, "fh": 1, "sh": 5}},
            "away": {"fh": {}, "sh": {}, "top": None}})
    monkeypatch.setattr(
        "handball.pipeline.xg.match_xg",
        lambda m, c=None: {"shooters": [
            {"player_id": 7, "team": "home", "shots": 8, "goals": 1,
             "xg": 3.2}]})
    monkeypatch.setattr(
        "handball.pipeline.stats.player_fatigue",
        lambda m, c=None: [{"track_id": 7, "team": "home",
                            "drop_pct": 40.0}])
    rec = player_training_focus(_match())["home"]["players"]
    assert len(rec) == 1
    assert len(rec[0]["items"]) == PLAYER_MAX_ITEMS


def test_ures_lista_ervenyes_eredmeny():
    """Ha egyetlen mért területen sincs kilógó gyengeség, a lista üres —
    ez EREDMÉNY, nem hiányzó adat."""
    rec = player_training_focus(_match())
    assert rec["home"]["players"] == [] and rec["away"]["players"] == []


def test_hosszu_labda_dontese(monkeypatch):
    _csend(monkeypatch)
    monkeypatch.setattr(
        "handball.pipeline.attack_types.risky_passers",
        lambda m, c=None: {
            "home": {"players": [],
                     "top": {"player_id": 2, "jersey": 5,
                             "tries": 12, "turnovers": 5}},
            "away": {"players": [], "top": None}})
    rec = player_training_focus(_match())["home"]["players"]
    assert rec and rec[0]["items"][0]["title"] == "Hosszú labda döntése"
    assert "42%" in rec[0]["items"][0]["why"], rec[0]["items"][0]["why"]


def test_dontes_a_hajraban(monkeypatch):
    _csend(monkeypatch)
    monkeypatch.setattr(
        "handball.pipeline.momentum.clutch_turnover_players",
        lambda m, c=None: {
            "home": {"players": [], "top": None},
            "away": {"players": [],
                     "top": {"player_id": 21, "jersey": 8,
                             "turnovers": 3}}})
    rec = player_training_focus(_match())["away"]["players"]
    assert rec and rec[0]["items"][0]["area"] == "hajrá"
    assert rec[0]["jersey"] == 8


# ---- A forrás-rétegek ALAKJA: a néma kód elleni őr --------------------


def _terheles_match(fps=25.0, perc=4):
    """Két játékos, végig mérve — a fáradás-réteg ebből tud számolni."""
    import math

    n = int(perc * 60 * fps)
    frames = []
    for t in range(n):
        # Az 1-es sokat mozog az első félidőben, alig a másodikban.
        # Sima (szinuszos) mozgás: a fűrészfog egy kocka alatti hatalmas
        # ugrást jelentene, amit a sebesség-szűrő kidobna.
        gyors = t < n // 2
        x = 15.0 + (5.0 if gyors else 0.4) * math.sin(t / 20.0)
        frames.append(Frame(t=t, players=[
            PlayerPosition(track_id=1, team=Team.HOME, x=x, y=10.0,
                           source=PositionSource.MEASURED, confidence=1.0,
                           jersey_number=9),
            PlayerPosition(track_id=2, team=Team.AWAY, x=30.0, y=10.0,
                           source=PositionSource.MEASURED, confidence=1.0),
        ], ball=None))
    return Match(_meta(fps), frames)


def test_a_forras_retegek_mezonevei_leteznek():
    """ŐR: a réteg a VALÓDI mezőneveket olvassa.

    Minden szabály `try/except`-ben ül (egy forrás hibája ne vigye el a
    többit) — csakhogy ez az elgépelt mezőnevet is elnyeli: a szabály
    némán semmit sem csinálna, a teszt pedig zöld maradna. Ezért itt a
    valódi rétegeket futtatjuk, és a mezőneveket ellenőrizzük.
    """
    from handball.pipeline.stats import player_fatigue
    from handball.pipeline.xg import match_xg

    m = _terheles_match()
    sorok = player_fatigue(m)
    assert sorok, "a fáradás-réteg nem adott sort — a próba nem mérne semmit"
    for r in sorok:
        assert "track_id" in r and "team" in r and "drop_pct" in r
        # A csapat-mező sztring vagy Enum is lehet — a réteg mindkettőt
        # kezeli, de valamelyiknek "home"/"away" értéket kell adnia.
        assert getattr(r["team"], "value", r["team"]) in ("home", "away")

    # A lövő-bontás mezőnevei (üres lövés-listán is a szerződés a
    # lényeg: a kulcsok neve, nem a darabszám).
    xg = match_xg(m)
    assert "shooters" in xg
    for r in xg["shooters"]:
        for k in ("player_id", "team", "shots", "goals", "xg"):
            assert k in r, k

    # A "top"-ot adó rétegek szerződése: a réteg a top szótár MEZŐIT
    # olvassa, tehát a kulcsok neve itt is számít.
    from handball.pipeline.attack_types import risky_passers
    from handball.pipeline.decisions import (pressure_sensitive_players,
                                             tired_turnover_players)
    from handball.pipeline.momentum import clutch_turnover_players

    for fn, kulcsok in (
            (pressure_sensitive_players,
             ("player_id", "press_events", "press_to")),
            (tired_turnover_players, ("player_id", "fh", "sh")),
            (risky_passers, ("player_id", "tries", "turnovers")),
            (clutch_turnover_players, ("player_id", "turnovers")),
    ):
        ki = fn(m)
        for side in ("home", "away"):
            assert side in ki, (fn.__name__, side)
            assert "top" in ki[side], fn.__name__
            top = ki[side]["top"]
            if top is None:
                continue
            for k in kulcsok:
                assert k in top, (fn.__name__, k)


def test_a_kondicio_szabaly_valodi_retegbol_is_megszolal():
    """A kondíció-szabály a VALÓDI fáradás-rétegből is ad tételt.

    Ez a próba nem monkeypatch-el: ha a mezőnév vagy a csapat-alak
    elromlik, itt derül ki — a monkeypatch-es tesztek nem vennék észre.
    """
    m = _terheles_match()
    rec = player_training_focus(m)
    tetelek = [i for side in ("home", "away")
               for p in rec[side]["players"] for i in p["items"]]
    assert any(i["area"] == "kondíció" for i in tetelek), tetelek


def test_a_szezon_lapon_ott_van_a_mit_gyakorolj():
    """A játékos szezon-lapján ott a "Mit gyakorolj" szakasz.

    Ez az a rész, amiért a játékos elteszi a lapot: nem az, hogy hány
    kilométert futott, hanem hogy MIN kell dolgoznia. Ami több meccsen
    visszatér, az nem napi forma.
    """
    from handball.pipeline.report_html import player_season_html

    html = player_season_html(
        "A", 9, [{"date": "2026-01-01", "opponent": "B", "minutes": 30,
                  "shots": 5, "goals": 1, "distance_m": 3000,
                  "sprint_count": 12}],
        "Kovács",
        [{"title": "Második félidei tempó", "area": "kondíció",
          "why": "az átlagtempója 40%-kal esik a 2. félidőre",
          "drill": "intervallum-futás", "count": 3}])
    assert "Mit gyakorolj" in html
    assert "Második félidei tempó" in html
    assert "3 meccsen" in html, "nem látszik, hányszor tért vissza"
    # A név a címben van (a lapot a játékos kapja a kezébe).
    assert "Kovács" in html


def test_a_szezon_lap_fokusz_nelkul_is_teljes():
    """Fókusz nélkül a szakasz elmarad — üres lista nem hiba."""
    from handball.pipeline.report_html import player_season_html

    html = player_season_html("A", 9, [], None, [])
    assert "<!DOCTYPE html>" in html
    assert "Mit gyakorolj" not in html


def test_player_focus_vegpont():
    """A "Mit gyakorolj" a KÉPERNYŐN is elérhető, nem csak nyomtatva.

    A játékos a görbéjét nézi meg — a teendőnek ott kell lennie
    mellette, nem egy külön letöltött HTML-ben.
    """
    import json
    import os
    import tempfile
    from pathlib import Path

    import pytest

    TestClient = pytest.importorskip(
        "fastapi.testclient", reason="fastapi nincs telepítve").TestClient

    tmp = tempfile.mkdtemp(prefix="handball_focus_ep_")
    os.environ["HANDBALL_DATA_DIR"] = tmp
    d = Path(tmp) / "data" / "matches"
    d.mkdir(parents=True, exist_ok=True)
    m = _terheles_match()
    m.meta.match_id = "f1"
    (d / "f1.json").write_text(json.dumps(m.to_dict()), encoding="utf-8")

    from handball.api.app import create_app
    client = TestClient(create_app())
    r = client.get("/players/focus", params={"team": "A", "jersey": 9})
    assert r.status_code == 200
    data = r.json()
    assert data["team"] == "A" and data["jersey"] == 9
    # A fixture-játékos a 2. félidőre lelassul → kondíció-tétel jár.
    cimek = [f["title"] for f in data["focus"]]
    assert "Második félidei tempó" in cimek, data["focus"]
    # A count nélkül nem lehet eldönteni, hogy visszatérő-e.
    assert all(f["count"] >= 1 for f in data["focus"])

    # Ismeretlen játékosra üres lista, nem hiba.
    ures = client.get("/players/focus",
                      params={"team": "A", "jersey": 77}).json()
    assert ures["focus"] == []


def test_edzesterv_nyomtathato_lap():
    """Az edzésterv lapja a csapat ÉS az egyéni feladatokat is viszi.

    Ezt a lapot az edző leviszi az edzésre, kiteszi az öltözőben —
    ott nincs képernyő, tehát ami lemarad róla, az nem létezik.
    """
    from handball.pipeline.report_html import training_plan_html

    html = training_plan_html(
        "Sport SE", 5,
        [{"title": "Fedezés-fegyelem", "area": "védekezés", "count": 3,
          "why": "a kapott lövések 45%-ánál nem volt védő",
          "drill": "kilépés-gyakorlat"}],
        [{"jersey": 9, "name": "Kovács",
          "items": [{"title": "Kiadás nyomás alatt",
                     "area": "labdabiztonság",
                     "why": "10 nyomott döntésből 6 eladás",
                     "drill": "kettőzés elleni kiadás", "count": 2}]}])
    assert "Edzésterv" in html and "Sport SE" in html
    assert "Fedezés-fegyelem" in html and "3 meccsen" in html
    assert "#9 Kovács" in html and "Kiadás nyomás alatt" in html
    assert "5 elemzett meccs" in html


def test_edzesterv_ures_eredmenyt_is_kimond():
    """Üres lista nem hiányzó adat: ha nincs visszatérő gyengeség, azt
    ki kell mondani — különben az edző hibának nézi az üres lapot."""
    from handball.pipeline.report_html import training_plan_html

    html = training_plan_html("Sport SE", 4, [], [])
    assert "Nincs olyan gyengeség" in html
    assert "Egyéni feladatok" not in html


# ---- Felderítés-oldal: KIRE mit csináljunk --------------------------


def test_a_felderites_atviszi_az_egyeni_gyengeseget():
    """Az általános kulcsok a CSAPATRÓL szólnak.

    A meccsterv viszont attól lesz konkrét, hogy KIRE mit kell
    csinálni: "a 7-esük nyomás alatt elveszti a labdát" egy
    kettőzés-utasítás, nem megfigyelés. A jelentés-mező darabszám
    alapú, hogy meccsek közt pontosan összegződjön.
    """
    from handball.pipeline.scouting import (ScoutingReport, _coach_keys,
                                            combine_reports)

    rep = ScoutingReport(team="home", team_name="A",
                         ptf_press={"7": 2}, ptf_clutch={"9": 1})
    _s, _w, kulcsok = _coach_keys(rep)
    assert any("#7" in k and "kettőz" in k for k in kulcsok), kulcsok
    assert any("#9" in k and "HAJRÁ" in k for k in kulcsok), kulcsok

    # Meccsek közt ÖSSZEADÓDIK — mezszámonként.
    a = ScoutingReport(team="home", team_name="A", ptf_press={"7": 2})
    b = ScoutingReport(team="home", team_name="A",
                       ptf_press={"7": 1, "3": 1})
    egy = combine_reports([a, b])
    assert egy.ptf_press == {"7": 3, "3": 1}


def test_a_meccsterv_ranevez_a_nyomas_erzekeny_emberre():
    """456. szabály: a kettőzésnek CÉLPONTJA van, nem iránya."""
    from handball.pipeline.scouting import ScoutingReport, matchup_plan

    opp = ScoutingReport(team="away", team_name="B", ptf_press={"7": 2})
    own = ScoutingReport(team="home", team_name="A", trans_steals=6)
    terv = matchup_plan(own, opp)
    assert any("#7" in p and "kettőz" in p for p in terv), terv

    # Ha MI nem szerzünk labdát, a tanács nem a mi fegyverünk —
    # ilyenkor a szabály hallgat.
    gyenge = ScoutingReport(team="home", team_name="A", trans_steals=1)
    assert not any("#7" in p for p in matchup_plan(gyenge, opp))


def test_a_szezon_fokusz_meccsenkent_egyszer_szamol(monkeypatch):
    """A szezon-szintű összegzés ne futtassa újra a réteget mezszámonként.

    Az edzésterv-lap MINDEN mezszámra kéri a szezon-fókuszt; a réteg
    pedig minden forrás-mérését újraszámolná. Egy húsz meccses
    könyvtárnál ez percekben mérhető — ezért meccsenként
    gyorsítótárazunk.
    """
    import json
    import os
    import tempfile
    from pathlib import Path

    import pytest

    TestClient = pytest.importorskip(
        "fastapi.testclient", reason="fastapi nincs telepítve").TestClient

    tmp = tempfile.mkdtemp(prefix="handball_ptf_cache_")
    os.environ["HANDBALL_DATA_DIR"] = tmp
    d = Path(tmp) / "data" / "matches"
    d.mkdir(parents=True, exist_ok=True)
    for i in range(2):
        m = _terheles_match()
        m.meta.match_id = f"c{i}"
        (d / f"c{i}.json").write_text(json.dumps(m.to_dict()),
                                      encoding="utf-8")

    hivasok = {"n": 0}
    valodi = player_training_focus

    def szamlalo(match, config=None):
        hivasok["n"] += 1
        return valodi(match, config)

    monkeypatch.setattr("handball.pipeline.training.player_training_focus",
                        szamlalo)

    from handball.api.app import create_app
    client = TestClient(create_app())
    # Két külön mezszámra kérünk fókuszt (a másodikra nincs adat).
    client.get("/players/focus", params={"team": "A", "jersey": 9})
    elso = hivasok["n"]
    client.get("/players/focus", params={"team": "A", "jersey": 4})
    assert elso <= 2, f"két meccsnél kettőnél többször futott: {elso}"
    assert hivasok["n"] == elso, (
        "a második kérés újraszámolta a rétegeket")


def test_a_csapat_egyeni_terve_vegpont():
    """A csapat egyéni terve: minden ismert mezszámra a szezon-fókusz.

    Elöl, akinek több gyakorlandója van — az edző ott kezdi a hetet.
    """
    import json
    import os
    import tempfile
    from pathlib import Path

    import pytest

    TestClient = pytest.importorskip(
        "fastapi.testclient", reason="fastapi nincs telepítve").TestClient

    tmp = tempfile.mkdtemp(prefix="handball_team_plan_")
    os.environ["HANDBALL_DATA_DIR"] = tmp
    d = Path(tmp) / "data" / "matches"
    d.mkdir(parents=True, exist_ok=True)
    for i in range(2):
        m = _terheles_match()
        m.meta.match_id = f"tp{i}"
        (d / f"tp{i}.json").write_text(json.dumps(m.to_dict()),
                                       encoding="utf-8")

    from handball.api.app import create_app
    client = TestClient(create_app())
    client.post("/library/players",
                json={"team": "A", "jersey": 9, "name": "Kovács"})
    r = client.get("/library/training-focus/players",
                   params={"team": "A"})
    assert r.status_code == 200
    sorok = r.json()["players"]
    assert sorok, "a fixture-játékosnak van gyakorlandója"
    assert sorok[0]["jersey"] == 9
    assert sorok[0]["name"] == "Kovács"
    assert sorok[0]["items"]
    # A tételek szám szerint is elárulják, hány meccsen tértek vissza.
    assert sorok[0]["items"][0]["count"] >= 1

    # Ismeretlen csapatra üres lista, nem hiba.
    ures = client.get("/library/training-focus/players",
                      params={"team": "Nincs Ilyen SE"}).json()
    assert ures["players"] == []
