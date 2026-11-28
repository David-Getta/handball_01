"""A sorrend-érzékenység mérő szkript (scripts.order_sensitivity) tesztjei.

A TELJES felmérés (299 réteg) percekig fut, ezért itt nem futtatjuk —
a szkript szerkezetét és a jelentés-generálást ellenőrizzük, plusz azt,
hogy a kapus-jelölés tényleg megváltoztat egy konkrét réteget (ez a
mérés létjogosultsága).
"""
from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.order_sensitivity import _layer_functions, build_report


def test_layer_functions_resolve_to_pipeline_modules():
    """A felmérés a katalógus regisztrációjából dolgozik, és talál rétegeket."""
    rows = _layer_functions()
    assert len(rows) > 200, len(rows)
    names = {n for n, _, _ in rows}
    assert "kickout_targets" in names
    assert "double_punishment" in names
    for _, mod, fn in rows:
        assert mod != "api/app.py"  # csak önálló pipeline-függvények
        assert fn and mod


def test_report_lists_the_sensitive_layers():
    """A jelentés kiírja a sorrend-függő rétegeket és a mérés paramétereit."""
    res = {"checked": 3, "sensitive": ["double_punishment"], "failed": []}
    text = build_report(res, 240.0, 7)
    assert "`double_punishment`" in text
    assert "3 réteg" in text and "1 sorrend-függő" in text
    assert "240 mp" in text and "mag: 7" in text
    assert "Nem mérhető" not in text  # üres lista → nincs szekció


def test_report_states_whether_shots_were_measured():
    """A jelentés kimondja, kapott-e a mérés lövéseket.

    Ez a legkönnyebben félreolvasható pont: lövés nélkül egy "nem
    sorrend-függő" sor bizonyítéknak látszana, holott üres bemenetből
    jön. A két eset szövege ezért különbözik.
    """
    res = {"checked": 5, "sensitive": [], "failed": []}
    with_shots = build_report(res, 120.0, 1, 6.0)
    assert "A mérés köre" in with_shots
    assert "valódi bemenetet kaptak" in with_shots

    # A szimuláció csak hazai támadást modellez — ezt is ki kell mondani,
    # különben a lista teljes körű mérésnek látszik.
    assert "VENDÉG TÁMADÓ oldaláról" in with_shots

    without = build_report(res, 120.0, 1, 0.0)
    assert "NEM MOND SEMMIT" in without
    assert "valódi bemenetet kaptak" not in without


def test_simulation_can_produce_shots():
    """A szimuláció bekapcsolva LŐ, és a lövéseknek van lövőjük.

    A mérés létjogosultsága ezen áll: enélkül a lövés-alapú rétegek
    üres bemenettel futnának.
    """
    from handball.pipeline.event_detection import EventType, detect_shots
    from handball.sim.match_simulator import simulate_ground_truth

    plain = simulate_ground_truth(duration_s=120.0, seed=7)
    assert not [e for e in detect_shots(plain)
                if e.type in (EventType.SHOT, EventType.GOAL)], \
        "alapból NEM termel lövést (a meglévő mérések erre épülnek)"

    m = simulate_ground_truth(duration_s=120.0, seed=7, shots_per_min=6.0)
    shots = [e for e in detect_shots(m)
             if e.type in (EventType.SHOT, EventType.GOAL)]
    assert len(shots) >= 8, len(shots)
    assert all(e.player_id is not None for e in shots), \
        "minden lövéshez tartozik lövő (van elengedés-fázis)"
    assert len({e.player_id for e in shots}) >= 4, \
        "a lövők körbejárnak — a játékos-bontásnak legyen mit bontania"


def test_report_says_when_nothing_is_sensitive():
    """Ha egy réteg sem sorrend-függő, azt is kimondjuk — nem hallgatunk."""
    text = build_report({"checked": 5, "sensitive": [], "failed": ["x"]},
                        120.0, 1)
    assert "egyetlen réteg sem bizonyult" in text
    assert "Nem mérhető (1)" in text


def test_detection_picks_the_real_goalkeepers():
    """A felismerés a VALÓDI kapusokat választja, nem a fal emberét.

    Ez a mérés eredeti létjogosultsága volt megfordítva: korábban a
    kapus-jelölés tényleg módosított számokat — de nem azért, mert a
    jelölés hasznos információt adott hozzá, hanem mert a felismerés
    holtversenyben a 6-0 fal középső VÉDŐJÉT (13) jelölte kapusnak a
    valódi kapus (17) helyett. A védő így kikerült minden védekező
    számításból, és a rá épülő rétegek mást adtak.

    A holtversenyt azóta a kaputól mért távolság dönti el. A
    szimulált meccsen a kapusok szerepe eleve jelölt, tehát a
    felismerésnek pontosan őket kell visszaadnia — és a jelölés
    ilyenkor semmit nem változtat.
    """
    from handball.pipeline.defense import double_punishment
    from handball.pipeline.goalkeeper import detect_goalkeepers
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=60.0, seed=7, shots_per_min=6.0)
    chosen = detect_goalkeepers(m)
    assert set(chosen) == {7, 17}, (
        f"a valódi kapusokat kell megtalálni (7, 17), nem: {chosen}")

    plain = double_punishment(
        simulate_ground_truth(duration_s=60.0, seed=7, shots_per_min=6.0))
    marked_match = simulate_ground_truth(duration_s=60.0, seed=7,
                                         shots_per_min=6.0)
    detect_goalkeepers(marked_match)
    assert plain == double_punishment(marked_match), (
        "a helyes jelölés után a sorrend már nem módosít számot")


def test_scope_makes_the_listed_layers_order_independent():
    """A TERMÉK útvonalán a sorrend már nem számít.

    A jelentés listája közvetlen (hatókör nélküli) hívásokból készül. A
    termék viszont `primitive_cache` hatókörben futtat, aminek a
    nyitása elvégzi a kapus-jelölést — ugyanaz a réteg tehát ugyanazt
    adja akkor is, ha előtte már futott kapus-réteg, és akkor is, ha
    nem. Ezt a garanciát itt rögzítjük, a listáról vett mintán.
    """
    import json

    from handball.pipeline.defense import double_punishment
    from handball.pipeline.goalkeeper import detect_goalkeepers
    from handball.pipeline.primitive_cache import primitive_cache
    from handball.sim.match_simulator import simulate_ground_truth

    def _run(mark_first: bool):
        m = simulate_ground_truth(duration_s=60.0, seed=7,
                                  shots_per_min=6.0)
        with primitive_cache(m):
            if mark_first:
                detect_goalkeepers(m)
            return json.dumps(double_punishment(m), sort_keys=True,
                              default=str)

    assert _run(False) == _run(True), (
        "a hatókörön belül a kapus-jelölés sorrendje nem "
        "befolyásolhatja az eredményt")


# ---- A mérés és a main (eddig egyszer sem futottak a csomagban) ----------------

def test_fresh_match_megismetelheto_es_lo():
    """A mérés próba-meccse ugyanazzal a maggal bitre ugyanaz (a két ág
    így összevethető), minden hívás FRISS példány, és a szimuláció lő is
    (enélkül a lövés-alapú rétegekről a mérés nem mondana semmit)."""
    from handball.pipeline.event_detection import detect_shots
    from scripts.order_sensitivity import (DEFAULT_SHOTS_PER_MIN, _dump,
                                           _fresh_match)

    a, b = _fresh_match(20.0, 7), _fresh_match(20.0, 7)
    assert a is not b and a.frames is not b.frames
    assert _dump(a.to_dict()) == _dump(b.to_dict())
    assert _dump(_fresh_match(20.0, 8).to_dict()) != _dump(a.to_dict())
    assert DEFAULT_SHOTS_PER_MIN > 0 and detect_shots(a)
    assert detect_shots(_fresh_match(20.0, 7, shots_per_min=0.0)) == []


def test_dump_kulcs_sorrendtol_fuggetlen_es_mindent_kiir():
    """Az összevetés alakja: kulcs szerint rendezett JSON (a szótár
    felépítési sorrendje nem számít), ékezettel, és a nem-JSON értékek
    (pl. Team, halmaz) szövegként — az eltérés tehát TARTALMI eltérés."""
    from handball.models.tracking import Team
    from scripts.order_sensitivity import _dump

    assert _dump({"b": 1, "a": {"y": 2, "x": 1}}) == \
        _dump({"a": {"x": 1, "y": 2}, "b": 1})
    assert _dump({"verdict": "zárt fal"}) == '{"verdict": "zárt fal"}'
    assert _dump({"a": 1}) != _dump({"a": 2})
    assert _dump({"team": Team.HOME, "x": None}) == \
        '{"team": "home", "x": null}'
    # Ami nem JSON-érték (pl. halmaz), az szövegként megy — nem kivétel.
    assert _dump({"jatekosok": {7}}) == '{"jatekosok": "{7}"}'
    assert _dump([]) == "[]" and _dump(None) == "null"


def _kis_meres(monkeypatch, retegek):
    from scripts import order_sensitivity as os_mod

    monkeypatch.setattr(os_mod, "_layer_functions", lambda: retegek)
    return os_mod.measure(seconds=20.0, seed=7)


def test_measure_megtalalja_a_szerep_fuggo_reteget(monkeypatch):
    """Kicsiben, próba-rétegekkel, SZEREP NÉLKÜLI meccsen (mint a valódi
    felvétel a jelölés előtt): az a réteg, amely a kapus-jelölésből
    (role == "kapus") dolgozik, mást ad jelölés előtt és után → a
    sorrend-függők közé kerül; a szereptől független réteg nem."""
    from handball.pipeline import xg
    from scripts import order_sensitivity as os_mod

    eredeti = os_mod._fresh_match

    def szerep_nelkul(seconds, seed, shots_per_min):
        m = eredeti(seconds, seed, shots_per_min)
        for f in m.frames:
            for p in f.players:
                p.role = None
        return m

    monkeypatch.setattr(os_mod, "_fresh_match", szerep_nelkul)

    def szerep_fuggo(match):
        kapusok = {p.track_id for f in match.frames for p in f.players
                   if p.role == "kapus"}
        return {"home": {"mezonyjatekos_kocka": sum(
            1 for f in match.frames for p in f.players
            if p.track_id not in kapusok)}}

    def fuggetlen(match):
        return {"home": {"kockak": len(match.frames)}}

    monkeypatch.setattr(xg, "_proba_szerep", szerep_fuggo, raising=False)
    monkeypatch.setattr(xg, "_proba_fuggetlen", fuggetlen, raising=False)
    res = _kis_meres(monkeypatch, [("szerep-függő", "xg", "_proba_szerep"),
                                   ("független", "xg", "_proba_fuggetlen")])
    assert res == {"checked": 2, "sensitive": ["szerep-függő"],
                   "failed": []}


def test_measure_a_szimulalt_meccsen_a_jeloles_nem_valtoztat(monkeypatch):
    """A szimulált meccsen a kapusok szerepe eleve jelölt, a felismerés
    pontosan őket adja vissza: ugyanaz a szerep-függő próba-réteg itt
    NEM sorrend-függő — ezért üres ma a jelentés listája."""
    from handball.pipeline import xg

    def szerep_fuggo(match):
        return {"home": {"kapus_kocka": sum(
            1 for f in match.frames for p in f.players
            if p.role == "kapus")}}

    monkeypatch.setattr(xg, "_proba_szerep", szerep_fuggo, raising=False)
    res = _kis_meres(monkeypatch, [("szerep-függő", "xg", "_proba_szerep")])
    assert res == {"checked": 1, "sensitive": [], "failed": []}


def test_measure_a_nem_merheto_reteget_kulon_listazza(monkeypatch):
    """A hibára futó, a nem egy-meccs-paraméteres (TypeError), a hiányzó
    függvényű és a hiányzó modulú réteg a "failed" listára kerül —
    ítélet nélkül, a többi mérését nem akasztja meg."""
    from handball.pipeline import xg

    def bukik(match):
        raise ValueError("nem megy")

    monkeypatch.setattr(xg, "_proba_bukik", bukik, raising=False)
    monkeypatch.setattr(xg, "_proba_ket_parameter",
                        lambda match, team: {}, raising=False)
    monkeypatch.setattr(xg, "_proba_jo",
                        lambda match: {"home": {"verdict": None}},
                        raising=False)
    res = _kis_meres(monkeypatch, [
        ("bukó", "xg", "_proba_bukik"),
        ("két paraméter", "xg", "_proba_ket_parameter"),
        ("hiányzó", "xg", "_nincs_ilyen_fuggveny"),
        ("rossz modul", "nincs_ilyen_modul", "f"),
        ("jó", "xg", "_proba_jo")])
    assert res["checked"] == 1 and res["sensitive"] == []
    assert res["failed"] == ["bukó", "két paraméter", "hiányzó",
                             "rossz modul"]


def test_measure_reteg_nelkul_ures_eredmeny(monkeypatch):
    """Réteg nélkül nincs mit mérni: nulla összevetett, üres listák."""
    assert _kis_meres(monkeypatch, []) == {"checked": 0, "sensitive": [],
                                           "failed": []}


def test_main_megirja_a_jelentest_es_osszegez(monkeypatch, tmp_path, capsys):
    """A main a paraméterekkel mér, a jelentést a (tmp mappába irányított)
    fájlba írja, és a kimenetre összegez — a doksit a teszt nem írja át."""
    from scripts import order_sensitivity as os_mod

    kert: dict = {}

    def kamu_meres(seconds, seed, shots_per_min):
        kert.update(seconds=seconds, seed=seed, shots_per_min=shots_per_min)
        return {"checked": 7, "sensitive": ["double_punishment"],
                "failed": ["xy", "zz"]}

    ki_fajl = tmp_path / "SORREND_FUGGES.md"
    monkeypatch.setattr(os_mod, "measure", kamu_meres)
    monkeypatch.setattr(os_mod, "_OUT", ki_fajl)
    assert os_mod.main(["--seconds", "30", "--seed", "4",
                        "--shots-per-min", "0"]) == 0
    assert kert == {"seconds": 30.0, "seed": 4, "shots_per_min": 0.0}
    szoveg = ki_fajl.read_text(encoding="utf-8")
    assert szoveg == os_mod.build_report(kamu_meres(30.0, 4, 0.0), 30.0, 4,
                                         0.0)
    assert "| `double_punishment` |" in szoveg
    assert "## Nem mérhető (2)" in szoveg
    assert "NEM termelt lövést" in szoveg
    ki = capsys.readouterr().out
    assert f"Sorrend-függés kiírva: {ki_fajl}" in ki
    assert "összevetve: 7 réteg" in ki and "sorrend-függő: 1" in ki
    assert "nem mérhető: 2" in ki

    # Paraméter nélkül az alapértékekkel (240 mp, 7-es mag, 6 lövés/perc).
    assert os_mod.main([]) == 0
    assert kert == {"seconds": os_mod.DEFAULT_SECONDS,
                    "seed": os_mod.DEFAULT_SEED,
                    "shots_per_min": os_mod.DEFAULT_SHOTS_PER_MIN}
    capsys.readouterr()
