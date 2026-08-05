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


def test_goalkeeper_marking_really_changes_a_layer():
    """A mérés létjogosultsága: a kapus-jelölés tényleg számot módosít.

    A `double_punishment` a kettőzött kockákat számolja; kapus-jelölés
    nélkül a kapus is beszámít második védőként. Ez a teszt rögzíti,
    hogy a jelenség VALÓS — nem a mérőeszköz hibája.
    """
    from handball.pipeline.defense import double_punishment
    from handball.pipeline.goalkeeper import detect_goalkeepers
    from handball.sim.match_simulator import simulate_ground_truth

    plain = double_punishment(simulate_ground_truth(duration_s=60.0, seed=7))
    marked_match = simulate_ground_truth(duration_s=60.0, seed=7)
    detect_goalkeepers(marked_match)
    marked = double_punishment(marked_match)
    assert plain != marked, (plain, marked)
