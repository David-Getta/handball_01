"""Hol törhető fel a védekezésük — a felderítés rangsorolt kivonata."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import Team  # noqa: E402
from handball.pipeline.scouting import (DBP_MAX_ITEMS, ScoutingReport,  # noqa: E402
                                        defence_breakpoints, report_to_dict)


def test_ures_jelentesbol_nincs_itelet():
    assert defence_breakpoints(ScoutingReport(team="away", team_name="X")) == []


def test_a_tetelek_a_bizonyitek_ereje_szerint_rangsorolva():
    rep = ScoutingReport(team="away", team_name="Ellenfél", matches=1, attacks=20,
                         defense_main="6-0")
    # Fal-rés: 4,5 m átlag, 70%-ban a bal szélen → a legerősebb tétel.
    rep.dgap_frames = 200
    rep.dgap_sum_m = 900.0
    rep.dgap_zones = {"bal szél": 140, "közép": 40, "jobb szél": 20}
    # Szabad lövők: 50% → 2,5 pont.
    rep.def_shots_against = 20
    rep.def_free_shots = 10
    rep.def_zones = {"bal szél": {"shots": 8, "goals": 4, "free": 3},
                     "közép": {"shots": 6, "goals": 1, "free": 1}}
    # Átjárható jobb oldal: 10/12 = 83% → 3,3 pont.
    rep.csb_left = 2
    rep.csb_right = 10
    # Gyenge visszazárás: 3/6 = 50% → 2,5 pont.
    rep.transition_turnovers = 6
    rep.transition_goals_against = 3
    tetelek = defence_breakpoints(rep)
    assert tetelek and len(tetelek) <= DBP_MAX_ITEMS
    pontok = [t["pont"] for t in tetelek]
    assert pontok == sorted(pontok, reverse=True)
    assert "bal szél" in tetelek[0]["hol"] and "4,5" in tetelek[0]["miert"].replace(".", ",")
    holok = " | ".join(t["hol"] for t in tetelek)
    assert "jobb oldalán" in holok and "9 m-en" in holok
    assert "labdaszerzés után" in holok
    for t in tetelek:
        assert t["hol"] and t["mivel"] and t["miert"] and t["pont"] >= 1.0
    # Az alak-ellenszer a leggyengébb: a végén, vagy kiszorul.
    assert tetelek[-1]["pont"] <= 1.0 or "6-0" not in " ".join(
        t["miert"] for t in tetelek)


def test_keves_mintanal_nem_szol():
    rep = ScoutingReport(team="away", team_name="Kevés", matches=1)
    rep.def_shots_against = 3   # < 4
    rep.def_free_shots = 3
    rep.csb_left = 7            # szárny-összeg < 8
    rep.transition_turnovers = 3
    rep.transition_goals_against = 3
    rep.gk_on_target = 3
    assert defence_breakpoints(rep) == []


def test_a_valodi_felderitesbol_is_a_jelentesbe_kerul():
    """A report_to_dict a VALÓDI felderítésen is viszi a kulcsot (lista),
    és a lövős szimuláción legalább egy tétel megszólal."""
    from handball.pipeline.scouting import scout_team
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=240, fps=25.0, seed=5,
                              shots_per_min=8)
    d = report_to_dict(scout_team(m, Team.AWAY))
    assert isinstance(d["defence_breakpoints"], list)
    assert d["defence_breakpoints"], d["weaknesses"]
    assert all({"hol", "mivel", "miert", "pont"} <= set(t)
               for t in d["defence_breakpoints"])
