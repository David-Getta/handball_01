"""Hogyan állítsd meg a támadásukat — a felderítés rangsorolt kivonata."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import Team  # noqa: E402
from handball.pipeline.scouting import (ATS_MAX_ITEMS, ScoutingReport,  # noqa: E402
                                        attack_stoppers, report_to_dict)


def _rep(**kw):
    return ScoutingReport(team="away", team_name="Ellenfél", matches=1, **kw)


def test_ures_jelentesbol_nincs_itelet():
    assert attack_stoppers(_rep()) == []


def test_a_tetelek_a_bizonyitek_ereje_szerint_rangsorolva():
    rep = _rep(fast_break_pct=24.0)                  # 4,0 pont
    rep.shot_zones = {"átlövés közép": {"shots": 12, "goals": 5},
                      "beálló": {"shots": 5, "goals": 4},
                      "balszél": {"shots": 3, "goals": 1}}  # fő zóna 60% → 3,0
    rep.fb_finishers = [{"player_id": 8, "goals": 3}]
    rep.pivot_total_attacks = 20
    rep.pivot_attacks = 10                           # 50% → 2,5
    rep.pivot_goals = 4
    rep.wfs_left_shots, rep.wfs_left_goals = 6, 5    # 83%
    rep.wfs_right_shots, rep.wfs_right_goals = 6, 2  # 33% → 50 pp → 4,2
    rep.assist_pairs = [{"from": 5, "to": 9, "goals": 4}]
    rep.shooter_overperf = [{"player_id": 9, "diff": 2.4}]
    tetelek = attack_stoppers(rep)
    assert tetelek and len(tetelek) <= ATS_MAX_ITEMS
    pontok = [t["pont"] for t in tetelek]
    assert pontok == sorted(pontok, reverse=True)
    holok = " | ".join(t["hol"] for t in tetelek)
    assert "bal szélsőjük" in holok and "beállójuk" in holok
    assert "átlövés közép" in holok and "beálló" in holok
    assert "5. → 9. passzsáv" in holok and "9. játékosuk" in holok
    assert any("8. játékost" in t["mivel"] for t in tetelek)
    for t in tetelek:
        assert t["hol"] and t["mivel"] and t["miert"] and t["pont"] >= 1.0


def test_keves_mintanal_nem_szol():
    rep = _rep(fast_break_pct=11.0)
    rep.shot_zones = {"beálló": {"shots": 2, "goals": 2}}
    rep.pivot_total_attacks = 5
    rep.pivot_attacks = 5
    rep.wfs_left_shots, rep.wfs_left_goals = 2, 2
    rep.wfs_right_shots, rep.wfs_right_goals = 6, 0
    rep.assist_pairs = [{"from": 1, "to": 2, "goals": 2}]
    rep.shooter_overperf = [{"player_id": 3, "diff": 0.9}]
    rep.fb_finishers = [{"player_id": 4, "goals": 1}]
    assert attack_stoppers(rep) == []


def test_a_valodi_felderitesbol_is_a_jelentesbe_kerul():
    from handball.pipeline.scouting import scout_team
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=240, fps=25.0, seed=5,
                              shots_per_min=8)
    d = report_to_dict(scout_team(m, Team.HOME))
    assert isinstance(d["attack_stoppers"], list)
    assert d["attack_stoppers"], "a lövős hazai támadás megállítható"
    assert all({"hol", "mivel", "miert", "pont"} <= set(t)
               for t in d["attack_stoppers"])


def test_a_nyomtathato_jelentes_viszi():
    from handball.pipeline.report_html import scouting_report_html

    assert "Hogyan állítsd meg a támadásukat" not in scouting_report_html(_rep())
    rep = _rep(fast_break_pct=20.0)
    html = scouting_report_html(rep)
    assert "Hogyan állítsd meg a támadásukat" in html
    assert "visszafutásnál" in html


def test_egyetlen_nagy_szam_nem_nyomja_el_a_tobbit():
    """A darabszámmal növő pontok (hatékony zóna, gól-tengely, túlteljesítő
    lövő) 5,0-nál korlátosak: nagy mintán sem szorítják ki a többi
    bizonyítékot a lista elejéről."""
    rep = _rep(fast_break_pct=30.0)                 # 5,0 pont
    rep.shot_zones = {"beálló": {"shots": 40, "goals": 40},
                      "balszél": {"shots": 40, "goals": 10},
                      "jobbszél": {"shots": 40, "goals": 10}}
    rep.assist_pairs = [{"from": 1, "to": 2, "goals": 30}]
    rep.shooter_overperf = [{"player_id": 7, "diff": 12.0}]
    tetelek = attack_stoppers(rep)
    assert all(t["pont"] <= 5.0 for t in tetelek), tetelek
    assert any("visszafutásnál" in t["hol"] for t in tetelek[:4])
