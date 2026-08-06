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
