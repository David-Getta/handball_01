"""
Tesztek az ellenfél-felderítésre (scouting.py) — kézzel összerakott meccsekkel.

A pálya 40x20 m; a HAZAI a +x (x=40) kapu felé támad, saját kapuja x=0.

Futtatás:
    python tests/test_scouting.py
"""

from __future__ import annotations

import os
import sys

import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, Ball, Team, PositionSource,
)
from handball.pipeline.scouting import (
    scout_team, combine_reports, ScoutingReport, _shot_zone, trend_report,
    scouting_narrative, report_to_dict,
)


def _pl(track_id, team, x, y):
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0)


def _meta(fps=25.0):
    return MatchMeta(match_id="s", home_team="Veszprém", away_team="Szeged", fps=fps,
                     frame_width=1920, frame_height=1080)


def _attack_60(n=30):
    """HAZAI szervezett támadás a +x térfélen, AWAY 6-0 fallal a x=40 kapunál."""
    frames = []
    for t in range(n):
        players = [_pl(1, Team.HOME, 28.0, 10.0), _pl(2, Team.HOME, 30.0, 5.0),
                   _pl(3, Team.HOME, 30.0, 15.0)]
        for j, y in enumerate([2, 6, 8, 12, 14, 18]):
            players.append(_pl(20 + j, Team.AWAY, 35.0, float(y)))
        frames.append(Frame(t=t, players=players, ball=Ball(x=28.0, y=10.0, confidence=1.0)))
    return Match(_meta(), frames)


def test_defense_distribution_detects_60():
    """A védekező (AWAY) csapat felderítve: leggyakoribb forma 6-0."""
    rep = scout_team(_attack_60(), Team.AWAY)
    assert rep.defense_main == "6-0"
    assert rep.defense_distribution.get("6-0", 0) > 0


def test_attack_share_for_attacking_team():
    """A támadó (HOME) csapatnál magas a szervezett-támadás arány."""
    rep = scout_team(_attack_60(), Team.HOME)
    assert rep.attack_share_pct > 50.0


def test_keys_to_game_mention_60():
    """A 6-0 fal ellen konkrét edzői kulcsot ad."""
    rep = scout_team(_attack_60(), Team.AWAY)
    assert any("6-0" in k for k in rep.keys_to_game)


def test_shot_and_goal_counting():
    """Lövés/gól számolás és hatékonyság a felderített csapatra."""
    # HAZAI gyorsan a x=40 kapu felé lő (gól), majd a labda a kapuvonalra ér.
    frames = []
    xs = [30, 33, 36, 39, 40.0]  # gyorsan a kapu felé
    for t, x in enumerate(xs):
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, x - 1, 10.0)],
                            ball=Ball(x=float(x), y=10.0, confidence=1.0)))
    m = Match(_meta(), frames)
    rep = scout_team(m, Team.HOME)
    assert rep.shots >= 1
    assert 0.0 <= rep.shot_efficiency_pct <= 100.0


def test_key_players_ranked_by_possession():
    """A legtöbbet birtokló játékos kerül előre a kulcsjátékosok közé."""
    rep = scout_team(_attack_60(), Team.HOME)
    assert len(rep.key_players) >= 1
    # az 1-es (a labdás) birtoklás-ideje a legnagyobb
    assert rep.key_players[0]["track_id"] == 1
    assert rep.key_players[0]["possession_frames"] > 0


def test_combine_reports_aggregates():
    """Több meccs egyesítése: matches nő, forma marad, számok összeadódnak."""
    r1 = scout_team(_attack_60(), Team.AWAY)
    r2 = scout_team(_attack_60(), Team.AWAY)
    comb = combine_reports([r1, r2])
    assert comb.matches == 2
    assert comb.defense_main == "6-0"
    assert comb.num_figures == r1.num_figures + r2.num_figures


def test_shot_zone_labels():
    """A zóna-címkék helyesek, a bal/jobb a támadás irányához igazodik."""
    assert _shot_zone(34.0, 2.0, 40.0) == "balszél"
    assert _shot_zone(34.0, 18.0, 40.0) == "jobbszél"
    assert _shot_zone(34.0, 10.0, 40.0) == "beálló (6 m)"
    assert _shot_zone(30.0, 10.0, 40.0) == "átlövés közép"
    assert _shot_zone(30.0, 3.0, 40.0) == "átlövés bal"
    # a -x kapura támadva a bal/jobb tükröződik
    assert _shot_zone(6.0, 2.0, 0.0) == "jobbszél"
    assert _shot_zone(10.0, 17.0, 0.0) == "átlövés bal"


def test_shot_zones_in_report():
    """A jelentésben megjelennek a lövési zónák (a szintetikus gól zónájával)."""
    frames = []
    xs = [30, 33, 36, 39, 40.0]  # gyors lövés a +x kapura, középről
    for t, x in enumerate(xs):
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, x - 1, 10.0)],
                            ball=Ball(x=float(x), y=10.0, confidence=1.0)))
    rep = scout_team(Match(_meta(), frames), Team.HOME)
    assert rep.shot_zones, "legalább egy zóna kell"
    zone = next(iter(rep.shot_zones))
    assert zone in ("átlövés közép", "beálló (6 m)")
    assert rep.shot_zones[zone]["shots"] >= 1


def test_combine_merges_shot_zones():
    """Az összevonás zónánként összegzi a lövéseket/gólokat."""
    frames = []
    xs = [30, 33, 36, 39, 40.0]
    for t, x in enumerate(xs):
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, x - 1, 10.0)],
                            ball=Ball(x=float(x), y=10.0, confidence=1.0)))
    r1 = scout_team(Match(_meta(), frames), Team.HOME)
    comb = combine_reports([r1, r1])
    zone = next(iter(r1.shot_zones))
    assert comb.shot_zones[zone]["shots"] == 2 * r1.shot_zones[zone]["shots"]


def test_combine_single_returns_same():
    """Egyetlen jelentés egyesítése önmagát adja."""
    r1 = scout_team(_attack_60(), Team.AWAY)
    assert combine_reports([r1]) is r1


def _rep_for_trend(**kw):
    base = dict(team="home", team_name="Mi", matches=2,
                attack_share_pct=50.0, fast_break_pct=10.0,
                avg_attack_duration_s=8.0, shot_efficiency_pct=40.0,
                shots=20, goals=8, turnovers=8)
    base.update(kw)
    return ScoutingReport(**base)


def test_trend_per_match_normalization():
    """A darabszámok meccsenkénti átlagra normálódnak (2 meccs / 20 lövés = 10)."""
    r = trend_report(_rep_for_trend(matches=2, shots=20),
                     _rep_for_trend(matches=4, shots=48))
    shots = next(m for m in r["metrics"] if m["metric"] == "shots")
    assert shots["older"] == 10.0 and shots["newer"] == 12.0
    assert shots["better"] is True


def test_trend_better_and_worse_flags():
    """A gólarány-növekedés javulás; a labdaeladás-növekedés romlás."""
    r = trend_report(_rep_for_trend(shot_efficiency_pct=40.0, turnovers=8),
                     _rep_for_trend(shot_efficiency_pct=55.0, turnovers=12))
    eff = next(m for m in r["metrics"] if m["metric"] == "shot_efficiency_pct")
    to = next(m for m in r["metrics"] if m["metric"] == "turnovers")
    assert eff["better"] is True
    assert to["better"] is False
    assert any(s.startswith("Javult") for s in r["summary"])
    assert any(s.startswith("Romlott") for s in r["summary"])


def test_trend_neutral_metric_not_judged():
    """A semleges irányú mutatót (támadáshossz) nem minősítjük."""
    r = trend_report(_rep_for_trend(avg_attack_duration_s=6.0),
                     _rep_for_trend(avg_attack_duration_s=12.0))
    dur = next(m for m in r["metrics"] if m["metric"] == "avg_attack_duration_s")
    assert dur["better"] is None
    assert not any("támadáshossz" in s.lower() for s in r["summary"])


def test_trend_includes_new_layers_and_skips_unmeasured():
    """A birtoklás/nyomás mutató benne van a trendben, ha mindkét
    időszakban mért; 0 (nincs mérés) esetén kimarad."""
    r = trend_report(
        _rep_for_trend(possession_pct=48.0, defensive_pressure_m=2.0),
        _rep_for_trend(possession_pct=55.0, defensive_pressure_m=1.5))
    names = [m["metric"] for m in r["metrics"]]
    assert "possession_pct" in names and "defensive_pressure_m" in names
    poss = next(m for m in r["metrics"] if m["metric"] == "possession_pct")
    press = next(m for m in r["metrics"] if m["metric"] == "defensive_pressure_m")
    assert poss["better"] is True     # több birtoklás = jobb
    assert press["better"] is True    # kisebb távolság = szorosabb = jobb
    # Nincs mérés (0) → kimarad, nem hamis romlás.
    r2 = trend_report(_rep_for_trend(possession_pct=0.0),
                      _rep_for_trend(possession_pct=55.0))
    assert "possession_pct" not in [m["metric"] for m in r2["metrics"]]


def test_trend_includes_blocks_per_match():
    """A blokk darabszám meccsenként normálódik, és több = jobb."""
    r = trend_report(_rep_for_trend(matches=2, blocks=4),
                     _rep_for_trend(matches=4, blocks=16))
    bl = next(m for m in r["metrics"] if m["metric"] == "blocks")
    assert bl["older"] == 2.0 and bl["newer"] == 4.0
    assert bl["better"] is True


def test_trend_no_change_summary():
    """Változatlan időszakok: "nincs jelentős változás" összegzés."""
    r = trend_report(_rep_for_trend(), _rep_for_trend())
    assert r["summary"] == ["Nincs jelentős változás a két időszak között."]


def test_narrative_sections_from_real_report():
    """A narratíva a jelentés számaiból áll össze, üres mondat nélkül."""
    rep = scout_team(_attack_60(), Team.HOME)
    sections = scouting_narrative(rep)
    assert sections
    for s in sections:
        assert s["title"] and s["body"]
    # Az API-válaszba is bekerül.
    d = report_to_dict(rep)
    assert d["narrative"] == sections


def test_narrative_defense_switching_mentioned():
    """Ha a második védőforma is gyakori (>=25%), a szöveg felhívja rá a figyelmet."""
    rep = ScoutingReport(
        team="away", team_name="Ellenfél KC",
        defense_main="6-0",
        defense_distribution={"6-0": 55.0, "5-1": 40.0},
    )
    bodies = " ".join(s["body"] for s in scouting_narrative(rep))
    assert "5-1" in bodies and "készülj" in bodies


def test_narrative_style_traits_mentioned():
    """A stílus-jegyek (pörgetett járatás, hosszú passzok, hátul ragadó
    birtoklás) bekerülnek az "Így támadnak" szövegbe."""
    rep = ScoutingReport(
        team="away", team_name="Ellenfél KC",
        avg_attack_duration_s=10.0,
        pt_passes=100, pt_poss_s=240.0,     # 25 passz/perc → pörgetik
        plen_n=20, plen_sum_m=180.0, plen_long=8,   # 40% hosszú
        tilt_frames=200, tilt_opp=80,       # 40% elöl → hátul ragad
    )
    bodies = " ".join(s["body"] for s in scouting_narrative(rep))
    assert "pörgetik" in bodies
    assert "hosszú" in bodies and "elfogható" in bodies
    assert "kihozási gondok" in bodies


def test_narrative_defense_traits_mentioned():
    """A védekezés-szakasz az új fal-jegyeket is hozza: tömör fal,
    ziccert engedő védekezés, elöl-szerzés (letámadás)."""
    rep = ScoutingReport(
        team="away", team_name="Ellenfél KC",
        defense_distribution={"6-0": 80.0},
        defw_frames=150, defw_sum_m=1500.0,      # 10 m → tömör
        def_shots_against=10, xga_sum=4.0,        # 0,40 xG/lövés → ziccer
        steal_n=6, steal_high=3,                  # 50% elöl → letámadás
    )
    bodies = " ".join(s["body"] for s in scouting_narrative(rep))
    assert "tömör" in bodies and "szélek nyitva" in bodies
    assert "Ziccereket engednek" in bodies
    assert "letámadásból" in bodies


def test_narrative_empty_report_degrades():
    """Üres jelentésnél is ad legalább egy ("kevés adat") szekciót."""
    rep = ScoutingReport(team="away", team_name="X")
    sections = scouting_narrative(rep)
    assert sections and sections[0]["title"] == "Kevés adat"


def test_coach_keys_flag_weak_goalkeeper_and_zone():
    """Gyenge kapus (alacsony védés%) → gyengeség; halmozott kapott-gól
    zóna → "támadd onnan" kulcs."""
    rep = ScoutingReport(
        team="away", team_name="Ellenfél KC",
        gk_on_target=6, gk_saves=1,
        gk_conceded_zones={"átlövés bal": 3, "beálló (6 m)": 2},
    )
    from handball.pipeline.scouting import _coach_keys
    strengths, weaknesses, keys = _coach_keys(rep)
    assert any("Bizonytalan kapus" in w for w in weaknesses)
    assert any("átlövés bal" in k and "támadd" in k for k in keys)


def test_combine_reports_merges_goalkeeper_stats():
    a = ScoutingReport(team="away", team_name="X", gk_on_target=4,
                       gk_saves=2, gk_conceded_zones={"átlövés bal": 2},
                       gk_on_target_zones={"átlövés bal": 3})
    b = ScoutingReport(team="away", team_name="X", gk_on_target=6,
                       gk_saves=1, gk_conceded_zones={"átlövés bal": 1,
                                                      "jobbszél": 2},
                       gk_on_target_zones={"átlövés bal": 2, "jobbszél": 4})
    merged = combine_reports([a, b])
    assert merged.gk_on_target == 10 and merged.gk_saves == 3
    assert merged.gk_conceded_zones == {"átlövés bal": 3, "jobbszél": 2}
    assert merged.gk_on_target_zones == {"átlövés bal": 5, "jobbszél": 4}


def test_coach_keys_flag_allowed_shot_quality():
    """Magas engedett xG/lövés → 'ziccereket engednek' gyengeség + kulcs;
    alacsony → 'kiszorító védekezés' erősség. A merge pontosan összegez."""
    from handball.pipeline.scouting import _coach_keys
    loose = ScoutingReport(team="away", team_name="Ellenfél KC",
                           def_shots_against=10, xga_sum=4.2)  # 0,42 xG/lövés
    _, weaknesses, keys = _coach_keys(loose)
    assert any("Ziccereket engednek" in w for w in weaknesses)
    assert any("nagy helyzetig" in k for k in keys)
    tight = ScoutingReport(team="away", team_name="Ellenfél KC",
                           def_shots_against=10, xga_sum=1.8)  # 0,18 xG/lövés
    strengths, _, k2 = _coach_keys(tight)
    assert any("Kiszorító védekezés" in s for s in strengths)
    assert any("kiszorít" in k for k in k2)
    merged = combine_reports([loose, tight])
    assert merged.def_shots_against == 20 and merged.xga_sum == 6.0


def test_coach_keys_flag_front_turnovers():
    """Sok támadó-harmadbeli labdaeladás → gyengeség + 'indíts hosszút'
    kulcs; kevés eladásnál nincs jelzés."""
    from handball.pipeline.scouting import _coach_keys
    rep = ScoutingReport(team="away", team_name="Ellenfél KC",
                         turnover_total=8, turnover_front=5)
    _, weaknesses, keys = _coach_keys(rep)
    assert any("támadó harmadban" in w for w in weaknesses)
    assert any("elöl" in k for k in keys)
    quiet = ScoutingReport(team="away", team_name="X",
                           turnover_total=3, turnover_front=3)
    _, w2, k2 = _coach_keys(quiet)
    assert not any("támadó harmadban" in w for w in w2)


def test_combine_reports_sums_turnover_zones():
    a = ScoutingReport(team="away", team_name="X",
                       turnover_total=6, turnover_front=2)
    b = ScoutingReport(team="away", team_name="X",
                       turnover_total=4, turnover_front=3)
    merged = combine_reports([a, b])
    assert merged.turnover_total == 10 and merged.turnover_front == 5


def test_coach_keys_flag_pass_axis():
    """Bejáratott passz-páros (7→9, 6 passz, 15+ összpassz) → 'vágd el' kulcs."""
    from handball.pipeline.scouting import _coach_keys
    rep = ScoutingReport(team="away", team_name="Ellenfél KC",
                         pass_total=18,
                         pass_pairs=[{"from": 7, "to": 9, "passes": 6}])
    _, _, keys = _coach_keys(rep)
    assert any("tengelye" in k and "7." in k and "9." in k for k in keys)
    quiet = ScoutingReport(team="away", team_name="X", pass_total=8,
                           pass_pairs=[{"from": 7, "to": 9, "passes": 3}])
    _, _, k2 = _coach_keys(quiet)
    assert not any("tengelye" in k for k in k2)


def test_coach_keys_flag_clutch_weakness_and_strength():
    """Hajrá-mérleg −3 → gyengeség + 'tartsd szorosan' kulcs; +3 → erősség."""
    from handball.pipeline.scouting import _coach_keys
    weak = ScoutingReport(team="away", team_name="Ellenfél KC",
                          clutch_matches=2, clutch_goals_for=2,
                          clutch_goals_against=5)
    _, weaknesses, keys = _coach_keys(weak)
    assert any("hajrában elfogynak" in w for w in weaknesses)
    assert any("végjátékban" in k for k in keys)
    strong = ScoutingReport(team="away", team_name="X",
                            clutch_matches=2, clutch_goals_for=6,
                            clutch_goals_against=3)
    strengths, _, _ = _coach_keys(strong)
    assert any("hajrában erősek" in s_ for s_ in strengths)


def test_coach_keys_flag_barren_long_attacks():
    """Rövid 60% vs hosszú 20% → 'kivárható őket' kulcs; kiegyenlítettnél
    nincs."""
    from handball.pipeline.scouting import _coach_keys
    rep = ScoutingReport(team="away", team_name="Ellenfél KC",
                         duration_eff={
                             "rövid (<15 mp)": {"attacks": 5, "goals": 3},
                             "hosszú (35 mp+)": {"attacks": 5, "goals": 1},
                         })
    _, _, keys = _coach_keys(rep)
    assert any("terméketlenek" in k for k in keys)
    even = ScoutingReport(team="away", team_name="X",
                          duration_eff={
                              "rövid (<15 mp)": {"attacks": 5, "goals": 2},
                              "hosszú (35 mp+)": {"attacks": 5, "goals": 2},
                          })
    _, _, k2 = _coach_keys(even)
    assert not any("terméketlenek" in k for k in k2)


def test_combine_reports_merges_duration_eff():
    a = ScoutingReport(team="away", team_name="X",
                       duration_eff={"rövid (<15 mp)": {"attacks": 3,
                                                        "goals": 2}})
    b = ScoutingReport(team="away", team_name="X",
                       duration_eff={"rövid (<15 mp)": {"attacks": 2,
                                                        "goals": 1},
                                     "hosszú (35 mp+)": {"attacks": 4,
                                                         "goals": 1}})
    m = combine_reports([a, b])
    assert m.duration_eff["rövid (<15 mp)"] == {"attacks": 5, "goals": 3}
    assert m.duration_eff["hosszú (35 mp+)"] == {"attacks": 4, "goals": 1}


def test_coach_keys_flag_formation_weakness():
    """A 6-0 ellen 20%, az 5-1 ellen 60% → 'ellenük 6-0-ban állj fel'."""
    from handball.pipeline.scouting import _coach_keys
    rep = ScoutingReport(team="away", team_name="Ellenfél KC",
                         vs_formation={"6-0": {"shots": 5, "goals": 1},
                                       "5-1": {"shots": 5, "goals": 3}})
    _, _, keys = _coach_keys(rep)
    assert any("6-0 fal ellen elakadnak" in k for k in keys)
    even = ScoutingReport(team="away", team_name="X",
                          vs_formation={"6-0": {"shots": 5, "goals": 2},
                                        "5-1": {"shots": 5, "goals": 2}})
    _, _, k2 = _coach_keys(even)
    assert not any("fal ellen elakadnak" in k for k in k2)


def test_combine_reports_merges_vs_formation():
    a = ScoutingReport(team="away", team_name="X",
                       vs_formation={"6-0": {"shots": 3, "goals": 1}})
    b = ScoutingReport(team="away", team_name="X",
                       vs_formation={"6-0": {"shots": 2, "goals": 2},
                                     "5-1": {"shots": 4, "goals": 3}})
    m = combine_reports([a, b])
    assert m.vs_formation["6-0"] == {"shots": 5, "goals": 3}
    assert m.vs_formation["5-1"] == {"shots": 4, "goals": 3}


def test_coach_keys_flag_response_time():
    """Gyors válasz (átlag 45 mp) → erősség; lassú (180 mp) → gyengeség."""
    from handball.pipeline.scouting import _coach_keys
    fast = ScoutingReport(team="away", team_name="Ellenfél KC",
                          response_n=5, response_sum_s=225.0)
    strengths, _, _ = _coach_keys(fast)
    assert any("gyorsan rendezik a sorokat" in s_ for s_ in strengths)
    slow = ScoutingReport(team="away", team_name="X",
                          response_n=4, response_sum_s=720.0)
    _, weaknesses, _ = _coach_keys(slow)
    assert any("megtorpannak" in w for w in weaknesses)


def test_combine_reports_sums_responses():
    a = ScoutingReport(team="away", team_name="X",
                       response_n=3, response_sum_s=200.0)
    b = ScoutingReport(team="away", team_name="X",
                       response_n=2, response_sum_s=150.0)
    m = combine_reports([a, b])
    assert m.response_n == 5
    assert abs(m.response_sum_s - 350.0) < 0.01


def test_coach_keys_flag_attack_side_bias():
    """A támadókockák 60%-a a bal sávban → 'told oda a falat' kulcs;
    kiegyenlített oldalaknál nincs."""
    from handball.pipeline.scouting import _coach_keys
    biased = ScoutingReport(team="away", team_name="Ellenfél KC",
                            side_frames={"bal": 300, "közép": 150,
                                         "jobb": 50})
    _, _, keys = _coach_keys(biased)
    assert any("súlypontja a bal oldal" in k for k in keys)
    balanced = ScoutingReport(team="away", team_name="X",
                              side_frames={"bal": 170, "közép": 170,
                                           "jobb": 160})
    _, _, k2 = _coach_keys(balanced)
    assert not any("súlypontja" in k for k in k2)


def test_combine_reports_sums_side_frames():
    a = ScoutingReport(team="away", team_name="X",
                       side_frames={"bal": 100, "közép": 50, "jobb": 30})
    b = ScoutingReport(team="away", team_name="X",
                       side_frames={"bal": 60, "közép": 90, "jobb": 20})
    m = combine_reports([a, b])
    assert m.side_frames == {"bal": 160, "közép": 140, "jobb": 50}


def test_coach_keys_flag_pressure_finishing():
    """Szabadon 80%, fedezve 20% → 'elég a fegyelmezett fal' kulcs;
    fedezve is 50% → 'hidegvérű lövők' erősség."""
    from handball.pipeline.scouting import _coach_keys
    soft = ScoutingReport(team="away", team_name="Ellenfél KC",
                          fin_free_shots=5, fin_free_goals=4,
                          fin_cov_shots=5, fin_cov_goals=1)
    _, _, keys = _coach_keys(soft)
    assert any("Fedezett helyzetben alig" in k for k in keys)
    cold = ScoutingReport(team="away", team_name="X",
                          fin_free_shots=5, fin_free_goals=3,
                          fin_cov_shots=6, fin_cov_goals=3)
    strengths, _, _ = _coach_keys(cold)
    assert any("hidegvérű" in s_ for s_ in strengths)


def test_combine_reports_sums_pressure_finishing():
    a = ScoutingReport(team="away", team_name="X", fin_free_shots=3,
                       fin_free_goals=2, fin_cov_shots=4, fin_cov_goals=1)
    b = ScoutingReport(team="away", team_name="X", fin_free_shots=2,
                       fin_free_goals=2, fin_cov_shots=3, fin_cov_goals=2)
    m = combine_reports([a, b])
    assert (m.fin_free_shots, m.fin_free_goals) == (5, 4)
    assert (m.fin_cov_shots, m.fin_cov_goals) == (7, 3)


def test_coach_keys_flag_powerful_shooters():
    """85+ km/h átlag (5+ mért lövésből) → 'nagy erejű lövők' erősség."""
    from handball.pipeline.scouting import _coach_keys
    rep = ScoutingReport(team="away", team_name="Ellenfél KC",
                         shot_speed_n=6, shot_speed_sum_kmh=540.0,
                         shot_speed_max_kmh=104.0)
    strengths, _, _ = _coach_keys(rep)
    assert any("Nagy erejű lövőik" in s_ for s_ in strengths)
    weakarm = ScoutingReport(team="away", team_name="X",
                             shot_speed_n=6, shot_speed_sum_kmh=420.0,
                             shot_speed_max_kmh=80.0)
    s2, _, _ = _coach_keys(weakarm)
    assert not any("Nagy erejű" in s_ for s_ in s2)


def test_combine_reports_merges_shot_speed():
    a = ScoutingReport(team="away", team_name="X", shot_speed_n=4,
                       shot_speed_sum_kmh=360.0, shot_speed_max_kmh=98.0)
    b = ScoutingReport(team="away", team_name="X", shot_speed_n=2,
                       shot_speed_sum_kmh=170.0, shot_speed_max_kmh=91.0)
    m = combine_reports([a, b])
    assert m.shot_speed_n == 6
    assert abs(m.shot_speed_sum_kmh - 530.0) < 0.01
    assert m.shot_speed_max_kmh == 98.0


def test_coach_keys_flag_half_pattern():
    """1. félidő −2, 2. félidő +3 → 'a 2. félidőben feljavulnak' kulcs;
    fordítva 'elfogynak'. Kevés gólnál nincs jelzés."""
    from handball.pipeline.scouting import _coach_keys
    improving = ScoutingReport(team="away", team_name="Ellenfél KC",
                               fh_goals_for=4, fh_goals_against=6,
                               sh_goals_for=8, sh_goals_against=5)
    _, _, keys = _coach_keys(improving)
    assert any("feljavulnak" in k for k in keys)
    fading = ScoutingReport(team="away", team_name="X",
                            fh_goals_for=8, fh_goals_against=5,
                            sh_goals_for=4, sh_goals_against=6)
    _, _, k2 = _coach_keys(fading)
    assert any("elfogynak" in k for k in k2)
    quiet = ScoutingReport(team="away", team_name="Y",
                           fh_goals_for=2, fh_goals_against=1,
                           sh_goals_for=1, sh_goals_against=2)
    _, _, k3 = _coach_keys(quiet)
    assert not any("félidő-mérleg" in k for k in k3)


def test_combine_reports_sums_half_goals():
    a = ScoutingReport(team="away", team_name="X", fh_goals_for=3,
                       fh_goals_against=2, sh_goals_for=4, sh_goals_against=5)
    b = ScoutingReport(team="away", team_name="X", fh_goals_for=2,
                       fh_goals_against=4, sh_goals_for=6, sh_goals_against=1)
    m = combine_reports([a, b])
    assert (m.fh_goals_for, m.fh_goals_against) == (5, 6)
    assert (m.sh_goals_for, m.sh_goals_against) == (10, 6)


def test_coach_keys_flag_slow_attacks():
    """A támadások 40%-a elhúzódó (10-ből 4) → 'maradj fegyelmezett' kulcs."""
    from handball.pipeline.scouting import _coach_keys
    rep = ScoutingReport(team="away", team_name="Ellenfél KC",
                         slow_attacks_total=10, slow_attacks_slow=4)
    _, _, keys = _coach_keys(rep)
    assert any("35 mp" in k for k in keys)
    quiet = ScoutingReport(team="away", team_name="X",
                           slow_attacks_total=10, slow_attacks_slow=1)
    _, _, k2 = _coach_keys(quiet)
    assert not any("35 mp" in k for k in k2)


def test_combine_reports_sums_slow_attacks():
    a = ScoutingReport(team="away", team_name="X",
                       slow_attacks_total=6, slow_attacks_slow=2)
    b = ScoutingReport(team="away", team_name="X",
                       slow_attacks_total=4, slow_attacks_slow=3)
    merged = combine_reports([a, b])
    assert merged.slow_attacks_total == 10
    assert merged.slow_attacks_slow == 5


def test_coach_keys_flag_active_block_wall():
    """3+ blokk → erősség + 'kerüld a falat' kulcs; kevés blokknál nincs."""
    from handball.pipeline.scouting import _coach_keys
    rep = ScoutingReport(team="away", team_name="Ellenfél KC", blocks=4)
    strengths, _, keys = _coach_keys(rep)
    assert any("blokkoltak" in s_ for s_ in strengths)
    assert any("blokkolnak" in k for k in keys)
    quiet = ScoutingReport(team="away", team_name="X", blocks=1)
    s2, _, k2 = _coach_keys(quiet)
    assert not any("blokkol" in x for x in s2 + k2)


def test_coach_keys_flag_long_drought():
    """10 perces leghosszabb gólcsend → 'ilyenkor kell ellépni' kulcs;
    rövid csendnél nincs."""
    from handball.pipeline.scouting import _coach_keys
    rep = ScoutingReport(team="away", team_name="Ellenfél KC",
                         drought_longest_s=600.0)
    _, _, keys = _coach_keys(rep)
    assert any("gólcsend" in k for k in keys)
    quiet = ScoutingReport(team="away", team_name="X",
                           drought_longest_s=200.0)
    _, _, k2 = _coach_keys(quiet)
    assert not any("gólcsend" in k for k in k2)


def test_combine_reports_takes_max_drought():
    a = ScoutingReport(team="away", team_name="X", drought_longest_s=300.0)
    b = ScoutingReport(team="away", team_name="X", drought_longest_s=540.0)
    assert combine_reports([a, b]).drought_longest_s == 540.0


def test_narrative_mentions_half_pattern():
    """Jelentős félidő-mérleg váltás → 'Félidő-minta' narratíva-szekció."""
    rep = ScoutingReport(team="away", team_name="Ellenfél KC",
                         fh_goals_for=4, fh_goals_against=6,
                         sh_goals_for=8, sh_goals_against=5)
    sections = scouting_narrative(rep)
    hp = next(s_ for s_ in sections if s_["title"] == "Félidő-minta")
    assert "feljavulnak" in hp["body"]
    # Kevés gólnál nincs ilyen szekció.
    quiet = ScoutingReport(team="away", team_name="X",
                           fh_goals_for=2, fh_goals_against=1,
                           sh_goals_for=1, sh_goals_against=2)
    assert not any(s_["title"] == "Félidő-minta"
                   for s_ in scouting_narrative(quiet))


def test_narrative_mentions_barren_long_attacks():
    """Terméketlen hosszú támadások → az 'Így támadnak' megemlíti."""
    rep = ScoutingReport(team="away", team_name="Ellenfél KC",
                         avg_attack_duration_s=8.0, fast_break_pct=5.0,
                         duration_eff={
                             "rövid (<15 mp)": {"attacks": 5, "goals": 3},
                             "hosszú (35 mp+)": {"attacks": 5, "goals": 1},
                         })
    sections = scouting_narrative(rep)
    attack = next(s_ for s_ in sections if s_["title"] == "Így támadnak")
    assert "terméketlenek" in attack["body"]


def test_narrative_mentions_weak_formation():
    """Nagy formánkénti különbség → az 'Így támadnak' megemlíti."""
    rep = ScoutingReport(team="away", team_name="Ellenfél KC",
                         avg_attack_duration_s=8.0, fast_break_pct=5.0,
                         vs_formation={"6-0": {"shots": 5, "goals": 1},
                                       "5-1": {"shots": 5, "goals": 3}})
    sections = scouting_narrative(rep)
    attack = next(s_ for s_ in sections if s_["title"] == "Így támadnak")
    assert "6-0 fal ellen" in attack["body"]


def test_narrative_mentions_attack_side():
    """Bal-súlypontú támadásépítés → az 'Így támadnak' megemlíti."""
    rep = ScoutingReport(team="away", team_name="Ellenfél KC",
                         avg_attack_duration_s=8.0, fast_break_pct=5.0,
                         side_frames={"bal": 300, "közép": 150, "jobb": 50})
    sections = scouting_narrative(rep)
    attack = next(s_ for s_ in sections if s_["title"] == "Így támadnak")
    assert "súlypontja a bal" in attack["body"]


def test_narrative_mentions_clutch():
    """Negatív hajrá-mérleg → Végjáték szekció a gyengeség-üzenettel."""
    rep = ScoutingReport(team="away", team_name="Ellenfél KC",
                         clutch_matches=2, clutch_goals_for=2,
                         clutch_goals_against=6)
    sections = scouting_narrative(rep)
    endg = next(s_ for s_ in sections if s_["title"] == "Végjáték")
    assert "-4" in endg["body"] or "−4" in endg["body"]
    assert "alulmaradnak" in endg["body"]


def test_combine_reports_sums_clutch():
    a = ScoutingReport(team="away", team_name="X", clutch_matches=1,
                       clutch_goals_for=3, clutch_goals_against=1)
    b = ScoutingReport(team="away", team_name="X", clutch_matches=1,
                       clutch_goals_for=2, clutch_goals_against=4)
    merged = combine_reports([a, b])
    assert merged.clutch_matches == 2
    assert merged.clutch_goals_for == 5
    assert merged.clutch_goals_against == 5


def test_narrative_mentions_pass_axis():
    """Bejáratott passz-tengely → az 'Így támadnak' szekció megemlíti."""
    rep = ScoutingReport(team="away", team_name="Ellenfél KC",
                         avg_attack_duration_s=8.0, fast_break_pct=5.0,
                         pass_total=20,
                         pass_pairs=[{"from": 7, "to": 9, "passes": 8}])
    sections = scouting_narrative(rep)
    attack = next(s_ for s_ in sections if s_["title"] == "Így támadnak")
    assert "tengely" in attack["body"]
    assert "7." in attack["body"] and "9." in attack["body"]


def test_combine_reports_merges_pass_pairs():
    a = ScoutingReport(team="away", team_name="X", pass_total=10,
                       pass_pairs=[{"from": 7, "to": 9, "passes": 4},
                                   {"from": 3, "to": 5, "passes": 2}])
    b = ScoutingReport(team="away", team_name="X", pass_total=12,
                       pass_pairs=[{"from": 7, "to": 9, "passes": 5}])
    merged = combine_reports([a, b])
    assert merged.pass_total == 22
    assert merged.pass_pairs[0] == {"from": 7, "to": 9, "passes": 9}
    assert {"from": 3, "to": 5, "passes": 2} in merged.pass_pairs


def test_coach_keys_flag_goalkeeper_weak_zone():
    """A zónánkénti védés-hatékonyságból a leggyengébb sarok külön kulcs:
    a 'jobbszél' 4 lövésből 3-at kapott (25% védés) → 'ide lőjetek'."""
    rep = ScoutingReport(
        team="away", team_name="Ellenfél KC",
        gk_on_target=8, gk_saves=4,
        gk_on_target_zones={"átlövés bal": 4, "jobbszél": 4},
        gk_conceded_zones={"átlövés bal": 1, "jobbszél": 3},
    )
    from handball.pipeline.scouting import _coach_keys
    _, _, keys = _coach_keys(rep)
    assert any("leggyengébb sarka" in k and "jobbszél" in k for k in keys)


def test_narrative_multi_match_prefix_and_gk_section():
    """Több meccsnél a befejezés-mondat jelzi a meccs-számot; a kapus-
    szekció a védés-hatékonyságot mondja el."""
    rep = ScoutingReport(
        team="away", team_name="Ellenfél KC", matches=3,
        shots=24, goals=12, shot_efficiency_pct=50.0,
        gk_on_target=10, gk_saves=5,
    )
    sections = scouting_narrative(rep)
    bodies = {s["title"]: s["body"] for s in sections}
    assert "3 meccs alatt" in bodies["Befejezésük"]
    assert "Kapusuk" in bodies and "50%" in bodies["Kapusuk"]


def test_scouting_report_html_shows_new_metrics():
    """A HTML-jelentés metrika-sora kiírja az új mutatókat, ha van adat."""
    from handball.pipeline.report_html import scouting_report_html
    rep = ScoutingReport(
        team="away", team_name="Ellenfél KC",
        gk_on_target=10, gk_saves=4, pp_shots=5, pp_goals=3,
        empty_net_s=45.0,
    )
    html = scouting_report_html(rep)
    assert "Kapusuk védés%" in html and "40%" in html
    assert "Emberelőny-gólarány" in html and "60%" in html
    assert "7 a 6 összesen" in html


def test_scouting_report_html_hides_absent_metrics():
    """Adat nélkül az új metrikák nem jelennek meg (nincs üres 0%)."""
    from handball.pipeline.report_html import scouting_report_html
    html = scouting_report_html(ScoutingReport(team="away", team_name="X"))
    assert "Kapusuk védés%" not in html
    assert "Emberelőny-gólarány" not in html
    assert "7 a 6 összesen" not in html


def _switching_match():
    """AWAY véd a x=40 kapunál: 6-0 → (hazai gól) → 5-1 → 6-0 → 5-1.

    A hazai gól után az AWAY hátrányban van, és kétszer is 5-1-re vált —
    ebből születik a "hátrányban 5-1-re váltanak" felderítési kulcs.
    """
    frames = []
    t = 0

    def defense(seconds, formation):
        nonlocal t
        for _ in range(int(seconds * 25)):
            players = [_pl(1, Team.HOME, 28.0, 10.0),
                       _pl(2, Team.HOME, 30.0, 6.0)]
            if formation == "6-0":
                xs = [35.0] * 6      # mind a hátsó sávban (depth 5)
            else:  # 5-1
                xs = [35.0] * 5 + [31.0]  # egy előretolt (depth 9 → mid)
            for j, x in enumerate(xs):
                players.append(_pl(20 + j, Team.AWAY, x, 3.0 + j * 2.5))
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=28.0, y=10.0, confidence=1.0)))
            t += 1

    def home_goal():
        nonlocal t
        for i in range(8):
            x = min(33.6 + i, 40.0)
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, x - 1, 10.0)],
                                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1

    defense(30, "6-0")
    home_goal()
    defense(15, "6-0")  # a gól után még 6-0 — a váltás már hátrányban jön
    defense(30, "5-1")
    defense(30, "6-0")
    defense(30, "5-1")
    return Match(_meta(), frames)


def test_formation_switch_profile_detects_switches_with_margin():
    from handball.pipeline.scouting import formation_switch_profile
    m = _switching_match()
    switches = formation_switch_profile(m, Team.AWAY)
    assert len(switches) >= 3
    to_51 = [s for s in switches if s["to"] == "5-1"]
    assert len(to_51) >= 2
    # A hazai gól után minden váltás hátrányban történt.
    assert all(s["margin"] < 0 for s in to_51)


def test_trailing_switch_key_in_report():
    m = _switching_match()
    rep = scout_team(m, Team.AWAY)
    assert any("hátrányban" in k.lower() and "5-1" in k
               for k in rep.keys_to_game), rep.keys_to_game


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    print(f"\n{'OK' if failures == 0 else failures} hibás teszt")
    raise SystemExit(1 if failures else 0)


def _shots_match(n_shots=4):
    """n_shots hazai lövés a +x kapura (mind gól), az 1-es játékostól."""
    frames = []
    t = 0
    for _ in range(n_shots):
        for i in range(7):
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 33.0, 10.0)],
                                ball=Ball(x=34.0 + i, y=10.0, confidence=1.0)))
            t += 1
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 20
    return Match(_meta(), frames)


def test_scout_team_includes_xg():
    """A felderítő jelentésben ott a várható gól és a befejezés-eltérés."""
    rep = scout_team(_shots_match(), Team.HOME)
    assert rep.shots >= 4 and rep.goals >= 4
    assert rep.xg > 0
    assert abs(rep.xg_diff - (rep.goals - rep.xg)) < 0.05
    # Minden gól bement → a helyzeteik felett teljesítenek (pozitív diff).
    assert rep.xg_diff > 0


def test_combine_reports_sums_xg():
    """Több meccs: az xG összegződik, a diff az összképből számolódik újra."""
    r1 = scout_team(_shots_match(), Team.HOME)
    r2 = scout_team(_shots_match(), Team.HOME)
    comb = combine_reports([r1, r2])
    assert abs(comb.xg - (r1.xg + r2.xg)) < 0.05
    assert abs(comb.xg_diff - (comb.goals - comb.xg)) < 0.05


def _shots_against_match(n_shots=4, free=True):
    """n_shots HAZAI lövés a +x kapura → az AWAY védekezése kapja őket.
    free=False esetén egy vendég-védő áll a lövő mellett (0,7 m)."""
    frames = []
    t = 0
    for _ in range(n_shots):
        for i in range(7):
            players = [_pl(1, Team.HOME, 33.0, 10.0)]
            if not free:
                players.append(_pl(20, Team.AWAY, 32.5, 10.5))
            else:
                players.append(_pl(20, Team.AWAY, 33.0, 16.0))  # 6 m-re
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=34.0 + i, y=10.0, confidence=1.0)))
            t += 1
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 20
    return Match(_meta(), frames)


def test_scout_team_defense_profile():
    """A felderített csapat védekezés-képe: kapott lövések, szabad lövők,
    zónák — és a gyengeség/kulcs a szabadon hagyott lövőkről."""
    rep = scout_team(_shots_against_match(free=True), Team.AWAY)
    assert rep.def_shots_against >= 4
    assert rep.def_free_shots == rep.def_shots_against  # mind szabad volt
    assert rep.def_zones  # zóna-bontás is van
    assert any("SZABADON" in w for w in rep.weaknesses)
    assert any("tiszta lövésig" in k for k in rep.keys_to_game)
    # Fedezett lövéseknél nincs ilyen gyengeség.
    rep2 = scout_team(_shots_against_match(free=False), Team.AWAY)
    assert rep2.def_free_shots == 0
    assert not any("SZABADON" in w for w in rep2.weaknesses)


def test_combine_reports_sums_defense():
    """Összevonásnál a védekezési számok összeadódnak, a zónák egyesülnek."""
    r1 = scout_team(_shots_against_match(free=True), Team.AWAY)
    r2 = scout_team(_shots_against_match(free=True), Team.AWAY)
    comb = combine_reports([r1, r2])
    assert comb.def_shots_against == r1.def_shots_against + r2.def_shots_against
    assert comb.def_free_shots == r1.def_free_shots + r2.def_free_shots
    total = sum(v["shots"] for v in comb.def_zones.values())
    assert total == comb.def_shots_against


def _sub_pattern_match():
    """Vendég gól (t=100) → hazai cserehullám hátrányban (t≈200-210) →
    hazai gól a csere után (t=300)."""
    frames = []
    for t in range(600):
        players = [_pl(1, Team.HOME, 25.0, 10.0),
                   _pl(2, Team.AWAY, 15.0, 10.0)]
        if t <= 200:  # az 5-ös a cserezóna felé tart, ott tűnik el
            frac = t / 200.0
            players.append(_pl(5, Team.HOME, 28.0 + (20.0 - 28.0) * frac,
                               8.0 + (1.0 - 8.0) * frac))
        if t >= 210:  # a 6-os a cserezónában jelenik meg
            frac = min(1.0, (t - 210) / 100.0)
            players.append(_pl(6, Team.HOME, 20.0 + (30.0 - 20.0) * frac,
                               1.0 + (12.0 - 1.0) * frac))
        ball = Ball(x=20.0, y=10.0, confidence=1.0)
        if 100 <= t < 107:  # vendég gól a -x kapura
            ball = Ball(x=max(0.0, 6.4 - (t - 100)), y=10.0, confidence=1.0)
        if 300 <= t < 307:  # hazai gól a +x kapura
            ball = Ball(x=min(40.0, 34.0 + (t - 300)), y=10.0, confidence=1.0)
        frames.append(Frame(t=t, players=players, ball=ball))
    return Match(_meta(), frames)


def test_scout_team_substitution_patterns():
    """A felderítés méri a cserehullámokat: darab, hátrányban-e, utó-mérleg."""
    rep = scout_team(_sub_pattern_match(), Team.HOME)
    assert rep.sub_rotations == 1
    assert rep.sub_trailing == 1        # a hullám 0-1-nél jött
    assert rep.sub_after_for == 1       # a csere után jött hazai gól
    assert rep.sub_after_against == 0
    # Összevonásnál a számok összeadódnak.
    comb = combine_reports([rep, scout_team(_sub_pattern_match(), Team.HOME)])
    assert comb.sub_rotations == 2 and comb.sub_trailing == 2
    assert comb.sub_after_for == 2


def _fast_break_goal_match():
    """Hazai lerohanás lövésig+gólig, majd egy lövés nélküli felállt támadás."""
    frames = []
    # Lerohanás: a labdás játékos 22→33 gyorsan, majd gól a +x kapura.
    for i in range(100):  # 4 mp
        x = 22.0 + (33.0 - 22.0) * i / 99.0
        frames.append(Frame(t=i, players=[
            _pl(1, Team.HOME, x, 10.0),
            _pl(9, Team.HOME, 1.5, 10.0),
            _pl(21, Team.AWAY, 37.0, 8.0),
            _pl(22, Team.AWAY, 37.0, 12.0)],
            ball=Ball(x=x, y=10.0, confidence=1.0)))
    t = len(frames)
    for i in range(7):
        frames.append(Frame(t=t + i, players=[_pl(1, Team.HOME, 33.0, 10.0)],
                            ball=Ball(x=34.0 + i, y=10.0, confidence=1.0)))
    return Match(_meta(), frames)


def test_scout_team_attack_efficiency():
    """A felderítés a támadás-hatékonyságot is méri, és a nagyon eredményes
    típus edzői kulcsot kap."""
    rep = scout_team(_fast_break_goal_match(), Team.HOME)
    assert rep.attack_efficiency  # van hatékonyság-adat
    fb = rep.attack_efficiency.get("lerohanás")
    assert fb and fb["goals"] >= 1 and fb["goal_pct"] >= 50.0
    # Összevonásnál a darabszámok összeadódnak.
    comb = combine_reports([rep, scout_team(_fast_break_goal_match(), Team.HOME)])
    cfb = comb.attack_efficiency.get("lerohanás")
    assert cfb["attacks"] == fb["attacks"] * 2


def test_big_chance_metrics_keys_and_combine():
    """Ziccer-mérleg: bravúr-kapus erősség, kihagyós befejezés gyengeség,
    a narratíva kapus-szekciója bővül, a számok meccsek közt összegződnek."""
    from handball.pipeline.scouting import _coach_keys, scouting_narrative
    rep = ScoutingReport(team="away", team_name="X",
                         gk_on_target=5, gk_saves=3,
                         gk_big_saves=3, big_total=6, big_missed=4)
    strengths, weaknesses, keys = _coach_keys(rep)
    assert any("bravúr" in x for x in strengths)
    assert any("Ziccereket hagynak ki" in x for x in weaknesses)
    sec = next(x for x in scouting_narrative(rep) if x["title"] == "Kapusuk")
    assert "Ziccert is fog" in sec["body"]
    comb = combine_reports([rep, rep])
    assert comb.gk_big_saves == 6
    assert comb.big_total == 12
    assert comb.big_missed == 8


def test_gk_outlet_key_and_combine():
    """Gyors kapus-indítás → felderítési kulcs a visszarendeződésről;
    a darabszámok meccsek közt összegződnek."""
    from handball.pipeline.scouting import _coach_keys
    rep = ScoutingReport(team="away", team_name="X",
                         gk_outlets=4, gk_outlet_fast=3,
                         gk_outlet_sum_s=16.0)
    _, _, keys = _coach_keys(rep)
    assert any("gyorsan indít" in k for k in keys)
    # Lassú indításnál nincs kulcs.
    slow = ScoutingReport(team="away", team_name="X",
                          gk_outlets=4, gk_outlet_fast=1,
                          gk_outlet_sum_s=50.0)
    _, _, keys2 = _coach_keys(slow)
    assert not any("gyorsan indít" in k for k in keys2)
    comb = combine_reports([rep, rep])
    assert comb.gk_outlets == 8
    assert comb.gk_outlet_fast == 6
    assert abs(comb.gk_outlet_sum_s - 32.0) < 1e-6


def test_empty_net_conceded_weakness_and_combine():
    """2+ üres kapura kapott gól → gyengeség a felderítésben; a szám
    meccsek közt összegződik."""
    from handball.pipeline.scouting import _coach_keys
    rep = ScoutingReport(team="away", team_name="X", empty_net_conceded=2)
    _, weaknesses, _ = _coach_keys(rep)
    assert any("üres kapura" in w for w in weaknesses)
    none = ScoutingReport(team="away", team_name="X", empty_net_conceded=1)
    _, w2, _ = _coach_keys(none)
    assert not any("üres kapura" in w for w in w2)
    comb = combine_reports([rep, rep])
    assert comb.empty_net_conceded == 4


def test_shooter_zone_habit_key_and_merge():
    """Ha a fő lövő lövéseinek 60%+-a egy zónából jön (4+ lövés),
    kulcs születik; a (játékos, zóna) párok meccsek közt összegződnek."""
    from handball.pipeline.scouting import _coach_keys, _merge_shooter_zones
    rep = ScoutingReport(
        team="away", team_name="X",
        shooter_zones=[{"player_id": 7, "zone": "átlövés bal", "shots": 5},
                       {"player_id": 7, "zone": "beálló (6 m)", "shots": 1}])
    _, _, keys = _coach_keys(rep)
    assert any("7. játékos" in k and "átlövés bal" in k for k in keys)
    # Kiegyenlített eloszlásnál nincs kulcs.
    flat = ScoutingReport(
        team="away", team_name="X",
        shooter_zones=[{"player_id": 7, "zone": "átlövés bal", "shots": 2},
                       {"player_id": 7, "zone": "beálló (6 m)", "shots": 2}])
    _, _, k2 = _coach_keys(flat)
    assert not any("innen jön" in k for k in k2)
    merged = _merge_shooter_zones([rep, rep])
    assert merged[0] == {"player_id": 7, "zone": "átlövés bal", "shots": 10}


def test_shooter_habit_narrative_section():
    """A koncentrált fő lövő a narratívában is megjelenik ("Fő lövőjük"),
    kiegyenlített eloszlásnál nem."""
    from handball.pipeline.scouting import scouting_narrative
    rep = ScoutingReport(
        team="away", team_name="X",
        shooter_zones=[{"player_id": 7, "zone": "átlövés bal", "shots": 5},
                       {"player_id": 7, "zone": "beálló (6 m)", "shots": 1}])
    secs = scouting_narrative(rep)
    sec = next((x for x in secs if x["title"] == "Fő lövőjük"), None)
    assert sec is not None
    assert "átlövés bal" in sec["body"]
    assert "83%" in sec["body"]
    flat = ScoutingReport(
        team="away", team_name="X",
        shooter_zones=[{"player_id": 7, "zone": "átlövés bal", "shots": 2},
                       {"player_id": 7, "zone": "beálló (6 m)", "shots": 2}])
    assert not any(x["title"] == "Fő lövőjük"
                   for x in scouting_narrative(flat))


def test_top_shooter_fade_key_and_merge():
    """Ha a fő lövő a 2. félidőben érdemben (15%+) lelassul, hajrá-kulcs
    születik; kis esésnél nem. A fáradás-adat meccsek közt összegződik."""
    from handball.pipeline.scouting import _coach_keys, _merge_shooter_fades
    rep = ScoutingReport(
        team="away", team_name="X",
        shooter_zones=[{"player_id": 7, "zone": "átlövés bal", "shots": 5}],
        shooter_fades=[{"player_id": 7, "drop_sum_pct": 22.0, "n": 1}])
    _, _, keys = _coach_keys(rep)
    assert any("elfárad" in k and "7. játékos" in k for k in keys)
    mild = ScoutingReport(
        team="away", team_name="X",
        shooter_zones=[{"player_id": 7, "zone": "átlövés bal", "shots": 5}],
        shooter_fades=[{"player_id": 7, "drop_sum_pct": 6.0, "n": 1}])
    _, _, k2 = _coach_keys(mild)
    assert not any("elfárad" in k for k in k2)
    merged = _merge_shooter_fades([rep, mild])
    assert merged == [{"player_id": 7, "drop_sum_pct": 28.0, "n": 2}]


def test_assist_pair_axis_key_and_merge():
    """3+ gólos (gólpasszoló -> lövő) páros → "tengely"-kulcs; kevesebb
    gólnál nincs. A párok meccsek közt összegződnek."""
    from handball.pipeline.scouting import _coach_keys, _merge_assist_pairs
    rep = ScoutingReport(
        team="away", team_name="X",
        assist_pairs=[{"from": 4, "to": 7, "goals": 3},
                      {"from": 2, "to": 7, "goals": 1}])
    _, _, keys = _coach_keys(rep)
    assert any("4. → 7." in k and "tengelye" in k for k in keys)
    few = ScoutingReport(
        team="away", team_name="X",
        assist_pairs=[{"from": 4, "to": 7, "goals": 2}])
    _, _, k2 = _coach_keys(few)
    assert not any("tengelye" in k for k in k2)
    merged = _merge_assist_pairs([few, few])
    assert merged == [{"from": 4, "to": 7, "goals": 4}]


def test_trend_includes_keeper_metrics_when_measured():
    """A bravúr-védés és a gyors indítás trendje megjelenik, ha mindkét
    időszakban volt mérés — nulla oldalnál (nincs mérés) kimarad."""
    older = ScoutingReport(team="away", team_name="X", matches=2,
                           gk_big_saves=2, gk_outlet_fast=2)
    newer = ScoutingReport(team="away", team_name="X", matches=2,
                           gk_big_saves=6, gk_outlet_fast=4)
    tr = trend_report(older, newer)
    m = {x["metric"]: x for x in tr["metrics"]}
    assert m["gk_big_saves"]["better"] is True
    assert m["gk_big_saves"]["older"] == 1.0   # meccsenkénti átlag
    assert m["gk_big_saves"]["newer"] == 3.0
    assert m["gk_outlet_fast"]["better"] is True
    # Nulla (nem mért) oldal → a mutató kimarad, nem "romlás".
    none_old = ScoutingReport(team="away", team_name="X", matches=2)
    tr2 = trend_report(none_old, newer)
    assert "gk_big_saves" not in {x["metric"] for x in tr2["metrics"]}


def test_top_blocker_key_and_merge():
    """3+ blokkos védő → "a faluk kulcsa" kulcs; kevesebbnél nincs.
    A blokkolónkénti számok meccsek közt összegződnek."""
    from handball.pipeline.scouting import _coach_keys, _merge_blockers
    rep = ScoutingReport(team="away", team_name="X", blocks=4,
                         blockers=[{"player_id": 5, "blocks": 3},
                                   {"player_id": 3, "blocks": 1}])
    _, _, keys = _coach_keys(rep)
    assert any("faluk kulcsa" in k and "5. játékos" in k for k in keys)
    few = ScoutingReport(team="away", team_name="X", blocks=2,
                         blockers=[{"player_id": 5, "blocks": 2}])
    _, _, k2 = _coach_keys(few)
    assert not any("faluk kulcsa" in k for k in k2)
    merged = _merge_blockers([rep, few])
    assert merged[0] == {"player_id": 5, "blocks": 5}


def test_outlet_target_key_and_merge():
    """Ha az indítások fele+ ugyanahhoz a játékoshoz megy, célpont-kulcs
    születik; szórt célpontoknál nem."""
    from handball.pipeline.scouting import (_coach_keys,
                                            _merge_outlet_targets)
    rep = ScoutingReport(team="away", team_name="X", gk_outlets=4,
                         gk_outlet_fast=1, gk_outlet_sum_s=40.0,
                         gk_outlet_targets=[{"player_id": 12, "n": 3},
                                            {"player_id": 8, "n": 1}])
    _, _, keys = _coach_keys(rep)
    assert any("célpontja" in k and "12." in k for k in keys)
    spread = ScoutingReport(team="away", team_name="X", gk_outlets=4,
                            gk_outlet_fast=1, gk_outlet_sum_s=40.0,
                            gk_outlet_targets=[{"player_id": 12, "n": 1},
                                               {"player_id": 8, "n": 1}])
    _, _, k2 = _coach_keys(spread)
    assert not any("célpontja" in k for k in k2)
    merged = _merge_outlet_targets([rep, spread])
    assert merged[0] == {"player_id": 12, "n": 4}


def test_fb_finisher_key_and_merge():
    """2+ kontra-gólos befejező → kulcs a visszafutásról; egy gólnál
    nincs. A gólszámok meccsek közt összegződnek."""
    from handball.pipeline.scouting import _coach_keys, _merge_fb_finishers
    rep = ScoutingReport(team="away", team_name="X",
                         fb_finishers=[{"player_id": 9, "goals": 2},
                                       {"player_id": 4, "goals": 1}])
    _, _, keys = _coach_keys(rep)
    assert any("lerohanásaikat" in k and "9. játékos" in k for k in keys)
    one = ScoutingReport(team="away", team_name="X",
                         fb_finishers=[{"player_id": 9, "goals": 1}])
    _, _, k2 = _coach_keys(one)
    assert not any("lerohanásaikat" in k for k in k2)
    merged = _merge_fb_finishers([rep, one])
    assert merged[0] == {"player_id": 9, "goals": 3}


def test_seven_taker_key_and_merge():
    """2+ hetes ugyanattól a dobótól → kulcs a kapusnak; gyenge mérlegnél
    külön biztatás. A kísérlet/gól számok meccsek közt összegződnek."""
    from handball.pipeline.scouting import _coach_keys, _merge_seven_takers
    rep = ScoutingReport(
        team="away", team_name="X",
        seven_takers=[{"player_id": 11, "attempts": 3, "goals": 1}])
    _, _, keys = _coach_keys(rep)
    key = next((k for k in keys if "heteseiket" in k), None)
    assert key is not None and "11. játékos" in key
    assert "bátran vállalhat" in key          # 1/3 = gyenge mérleg
    strong = ScoutingReport(
        team="away", team_name="X",
        seven_takers=[{"player_id": 11, "attempts": 3, "goals": 3}])
    _, _, k2 = _coach_keys(strong)
    key2 = next((k for k in k2 if "heteseiket" in k), None)
    assert key2 is not None and "bátran vállalhat" not in key2
    one = ScoutingReport(
        team="away", team_name="X",
        seven_takers=[{"player_id": 11, "attempts": 1, "goals": 1}])
    _, _, k3 = _coach_keys(one)
    assert not any("heteseiket" in k for k in k3)
    merged = _merge_seven_takers([rep, strong])
    assert merged[0] == {"player_id": 11, "attempts": 6, "goals": 4,
                         "dirs": {}}


def test_seven_taker_direction_key():
    """Ha a dobó hetesei 70%+ egy sávba mennek (3+ mért irány), a
    kulcs konkrét utasítást ad a kapusnak; szórt iránynál nem."""
    from handball.pipeline.scouting import _coach_keys
    pred = ScoutingReport(
        team="away", team_name="X",
        seven_takers=[{"player_id": 7, "attempts": 4, "goals": 3,
                       "dirs": {"bal": 3, "közép": 1}}])
    _, _, keys = _coach_keys(pred)
    key = next((k for k in keys if "heteseiket" in k), None)
    assert key is not None and "induljon balra" in key
    spread = ScoutingReport(
        team="away", team_name="X",
        seven_takers=[{"player_id": 7, "attempts": 4, "goals": 3,
                       "dirs": {"bal": 2, "jobb": 2}}])
    _, _, k2 = _coach_keys(spread)
    key2 = next((k for k in k2 if "heteseiket" in k), None)
    assert key2 is not None and "induljon" not in key2


def test_suspension_earner_key_and_merge():
    """2+ kiharcolt 2 perc → kulcs a fegyelmezett védekezésre; a
    darabszámok meccsek közt összegződnek."""
    from handball.pipeline.scouting import _coach_keys, _merge_susp_earners
    rep = ScoutingReport(
        team="away", team_name="X",
        susp_earners=[{"player_id": 9, "earned": 2}])
    _, _, keys = _coach_keys(rep)
    key = next((k for k in keys if "kiállításokat" in k), None)
    assert key is not None and "9. játékos" in key.replace("9. \n", "9. ")
    one = ScoutingReport(
        team="away", team_name="X",
        susp_earners=[{"player_id": 9, "earned": 1}])
    _, _, k2 = _coach_keys(one)
    assert not any("kiállításokat" in k for k in k2)
    merged = _merge_susp_earners([rep, one])
    assert merged == [{"player_id": 9, "earned": 3}]


def test_match_key_players_top_shooter():
    """A match_key_players a 3+ lövéses fő lövőt adja vissza a megfelelő
    oldalon, mérleggel."""
    from handball.models.tracking import Ball, Frame, Match, MatchMeta
    from handball.pipeline.scouting import match_key_players

    def pl(tid, x, y):
        from handball.models.tracking import (PlayerPosition,
                                              PositionSource)
        return PlayerPosition(track_id=tid, team=Team.HOME, x=x, y=y,
                              source=PositionSource.MEASURED,
                              confidence=1.0)

    frames = []
    t = 0
    for _ in range(4):
        for i in range(7):
            frames.append(Frame(t=t, players=[pl(1, 33.0, 10.0)],
                                ball=Ball(x=34.0 + i, y=10.0,
                                          confidence=1.0)))
            t += 1
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 20
    m = Match(MatchMeta(match_id="mkp", home_team="H", away_team="A",
                        fps=25.0), frames)
    kp = match_key_players(m)
    roles = {it["role"]: it for it in kp["home"]}
    assert "Fő lövő" in roles
    assert roles["Fő lövő"]["player_id"] == 1
    assert "lövés" in roles["Fő lövő"]["detail"]
    assert kp["away"] == []


def test_en_timing_key_and_combine():
    """Ha a 7 a 6 szakaszok 70%+-a hátrányban indul (2+ szakasz),
    időzítés-kulcs születik; vegyes mintánál nem."""
    from handball.pipeline.scouting import _coach_keys
    rep = ScoutingReport(team="away", team_name="X",
                         en_windows=3, en_trailing=3)
    _, _, keys = _coach_keys(rep)
    assert any("hátrányban húzzák elő" in k for k in keys)
    mixed = ScoutingReport(team="away", team_name="X",
                           en_windows=4, en_trailing=2)
    _, _, k2 = _coach_keys(mixed)
    assert not any("hátrányban húzzák elő" in k for k in k2)
    comb = combine_reports([rep, mixed])
    assert comb.en_windows == 7
    assert comb.en_trailing == 5


def test_pace_profile_keys_and_combine():
    """Tempós csapat → rotáció-kulcs; lassú csapat → tempóváltás-kulcs;
    kevés mért percnél nincs kulcs. A számok összegződnek."""
    from handball.pipeline.scouting import _coach_keys
    fast = ScoutingReport(team="away", team_name="X",
                          pace_attacks=60, pace_minutes=50.0)
    _, _, k1 = _coach_keys(fast)
    assert any("Tempósan játszanak" in k for k in k1)
    slow = ScoutingReport(team="away", team_name="X",
                          pace_attacks=20, pace_minutes=50.0)
    _, _, k2 = _coach_keys(slow)
    assert any("Lassú meccseket játszanak" in k for k in k2)
    short = ScoutingReport(team="away", team_name="X",
                           pace_attacks=30, pace_minutes=10.0)
    _, _, k3 = _coach_keys(short)
    assert not any("támadás/perc" in k for k in k3)
    comb = combine_reports([fast, slow])
    assert comb.pace_attacks == 80
    assert abs(comb.pace_minutes - 100.0) < 1e-6


def test_match_key_players_goal_axis():
    """A 2+ gólos (gólpasszoló -> lövő) páros Gól-tengely szerepként
    jelenik meg a kulcsember-listában."""
    from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                          PlayerPosition, PositionSource)
    from handball.pipeline.scouting import match_key_players

    def pl(tid, x, y):
        return PlayerPosition(track_id=tid, team=Team.HOME, x=x, y=y,
                              source=PositionSource.MEASURED,
                              confidence=1.0)

    frames = []
    t = 0
    for _ in range(2):
        # passz 1→2, majd a 2-es gólja a +x kapura
        frames.append(Frame(t=t, players=[pl(1, 25.0, 10.0),
                                          pl(2, 30.0, 10.0)],
                            ball=Ball(x=25.0, y=10.0, confidence=1.0)))
        t += 1
        frames.append(Frame(t=t, players=[pl(1, 25.0, 10.0),
                                          pl(2, 30.0, 10.0)],
                            ball=Ball(x=30.0, y=10.0, confidence=1.0)))
        t += 1
        for _ in range(3):   # a labda a lövő kezében (elengedés előtt)
            frames.append(Frame(t=t, players=[pl(2, 33.0, 10.0)],
                                ball=Ball(x=33.2, y=10.0, confidence=1.0)))
            t += 1
        for i in range(7):
            frames.append(Frame(t=t, players=[pl(2, 33.0, 10.0)],
                                ball=Ball(x=34.0 + i, y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(20):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    m = Match(MatchMeta(match_id="ax", home_team="H", away_team="A",
                        fps=25.0), frames)
    kp = match_key_players(m)
    axis = next((it for it in kp["home"] if it["role"] == "Gól-tengely"),
                None)
    assert axis is not None
    assert axis["player_id"] == 2
    assert "1. játékostól" in axis["detail"]
    assert "2 gól" in axis["detail"]


def test_match_key_players_cannon_role():
    """A 85 km/h fölötti lövés "Ágyú" szerepet ad a lövőnek."""
    from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                          PlayerPosition, PositionSource)
    from handball.pipeline.scouting import match_key_players

    def pl(tid, x, y):
        return PlayerPosition(track_id=tid, team=Team.HOME, x=x, y=y,
                              source=PositionSource.MEASURED,
                              confidence=1.0)

    # 1 m/kocka a kapu felé 25 fps-en = 25 m/s = 90 km/h.
    frames = []
    for i in range(7):
        frames.append(Frame(t=i, players=[pl(1, 33.0, 10.0)],
                            ball=Ball(x=34.0 + i, y=10.0,
                                      confidence=1.0)))
    m = Match(MatchMeta(match_id="cn", home_team="H", away_team="A",
                        fps=25.0), frames)
    kp = match_key_players(m)
    cannon = next((it for it in kp["home"] if it["role"] == "Ágyú"), None)
    assert cannon is not None
    assert cannon["player_id"] == 1
    assert "km/h" in cannon["detail"]


def test_match_key_players_big_save_keeper_role():
    """2 fogott ziccer → Bravúr-kapus szerep a védő csapat kapusával."""
    from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                          PlayerPosition, PositionSource)
    from handball.pipeline.scouting import match_key_players

    def pl(tid, team, x, y, role=None):
        p = PlayerPosition(track_id=tid, team=team, x=x, y=y,
                           source=PositionSource.MEASURED, confidence=1.0)
        if role:
            p.role = role
        return p

    frames = []
    t = 0
    for _ in range(2):  # két fogott ziccer: a labda a kapusnál megáll
        for i in range(8):
            frames.append(Frame(
                t=t,
                players=[pl(1, Team.HOME, 37.0, 10.0),
                         pl(30, Team.AWAY, 39.0, 10.0, role="kapus")],
                ball=Ball(x=min(37.4 + 0.6 * i, 38.8), y=10.0,
                          confidence=1.0)))
            t += 1
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 20
    m = Match(MatchMeta(match_id="bk", home_team="H", away_team="A",
                        fps=25.0), frames)
    kp = match_key_players(m)
    role = next((it for it in kp["away"]
                 if it["role"] == "Bravúr-kapus"), None)
    assert role is not None
    assert role["player_id"] == 30
    assert "2 fogott ziccer" in role["detail"]


def test_gk_xg_saved_strength_and_combine():
    """Meccsenként 1,0+ hárított xG erősségként jelenik meg; az összeg
    meccsek közt pontosan adódik."""
    from handball.pipeline.scouting import _coach_keys
    rep = ScoutingReport(team="away", team_name="X", matches=2,
                         gk_xg_saved=2.6)
    strengths, _, _ = _coach_keys(rep)
    assert any("nehéz lövéseket is fogja" in x for x in strengths)
    low = ScoutingReport(team="away", team_name="X", matches=2,
                         gk_xg_saved=1.0)
    s2, _, _ = _coach_keys(low)
    assert not any("nehéz lövéseket" in x for x in s2)
    comb = combine_reports([rep, low])
    assert abs(comb.gk_xg_saved - 3.6) < 1e-6


def test_gk_xg_saved_in_narrative():
    """Az 1,0+/meccs hárított xG a Kapusuk narratívában is megjelenik."""
    from handball.pipeline.scouting import scouting_narrative
    rep = ScoutingReport(team="away", team_name="X", matches=2,
                         gk_on_target=8, gk_saves=5, gk_xg_saved=2.6)
    sec = next(x for x in scouting_narrative(rep)
               if x["title"] == "Kapusuk")
    assert "hárított" in sec["body"]
    assert "1.3" in sec["body"] or "1,3" in sec["body"]


def test_gk_xg_prevented_weakness_and_combine():
    """Meccsenként −1,0 alatti megmentett gól gyengeség; jobb mérlegnél
    nincs. Az összeg pontosan adódik."""
    from handball.pipeline.scouting import _coach_keys
    rep = ScoutingReport(team="away", team_name="X", matches=2,
                         gk_xg_prevented=-2.4)
    _, weaknesses, _ = _coach_keys(rep)
    assert any("helyzetekhez képest sokat kap" in w for w in weaknesses)
    ok_rep = ScoutingReport(team="away", team_name="X", matches=2,
                            gk_xg_prevented=-0.8)
    _, w2, _ = _coach_keys(ok_rep)
    assert not any("helyzetekhez képest" in w for w in w2)
    comb = combine_reports([rep, ok_rep])
    assert abs(comb.gk_xg_prevented - (-3.2)) < 1e-6


def test_trend_includes_gk_xg_metrics():
    """A hárított xG és a GSAx trendje meccsenkénti átlagra normálva
    jelenik meg, mért adatnál."""
    older = ScoutingReport(team="away", team_name="X", matches=2,
                           gk_xg_saved=1.0, gk_xg_prevented=-2.0)
    newer = ScoutingReport(team="away", team_name="X", matches=2,
                           gk_xg_saved=3.0, gk_xg_prevented=2.0)
    tr = trend_report(older, newer)
    m = {x["metric"]: x for x in tr["metrics"]}
    assert m["gk_xg_saved"]["older"] == 0.5
    assert m["gk_xg_saved"]["newer"] == 1.5
    assert m["gk_xg_saved"]["better"] is True
    assert m["gk_xg_prevented"]["better"] is True


def test_shooter_overperf_key_and_merge():
    """+1,0 fölötti összesített befejezés-többlet kulcsot ad; kisebbnél
    nem. A többlet játékosonként összegződik."""
    from handball.pipeline.scouting import (_coach_keys,
                                            _merge_shooter_overperf)
    rep = ScoutingReport(team="away", team_name="X",
                         shooter_overperf=[{"player_id": 7, "diff": 1.2}])
    _, _, keys = _coach_keys(rep)
    assert any("FELETT" in k and "7. játékos" in k for k in keys)
    small = ScoutingReport(team="away", team_name="X",
                           shooter_overperf=[{"player_id": 7,
                                              "diff": 0.6}])
    _, _, k2 = _coach_keys(small)
    assert not any("FELETT" in k for k in k2)
    merged = _merge_shooter_overperf([rep, small])
    assert merged[0] == {"player_id": 7, "diff": 1.8}


def test_match_key_players_cold_finisher_role():
    """A +1,0 fölötti befejezés-többletű lövő "Hidegvérű befejező"
    szerepet kap."""
    from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                          PlayerPosition, PositionSource)
    from handball.pipeline.scouting import match_key_players

    def pl(tid, x, y):
        return PlayerPosition(track_id=tid, team=Team.HOME, x=x, y=y,
                              source=PositionSource.MEASURED,
                              confidence=1.0)

    # 4 távoli (kis xG-jű) gól ugyanattól a lövőtől: diff = 4 − ~kis xG.
    frames = []
    t = 0
    for _ in range(4):
        for i in range(10):
            frames.append(Frame(t=t, players=[pl(1, 28.0, 4.0)],
                                ball=Ball(x=min(28.5 + 1.3 * i, 40.0),
                                          y=4.0 + min(0.65 * i, 6.0),
                                          confidence=1.0)))
            t += 1
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 20
    m = Match(MatchMeta(match_id="cf", home_team="H", away_team="A",
                        fps=25.0), frames)
    kp = match_key_players(m)
    role = next((it for it in kp["home"]
                 if it["role"] == "Hidegvérű befejező"), None)
    assert role is not None
    assert role["player_id"] == 1
    assert "xG-hez képest" in role["detail"]


def test_shot_selection_keys():
    """Kis átlag-xG → "engedd a távolit"; nagy átlag-xG → "válogatósak";
    kevés lövésnél nincs kulcs."""
    from handball.pipeline.scouting import _coach_keys
    spray = ScoutingReport(team="away", team_name="X", shots=20, xg=1.6)
    _, _, k1 = _coach_keys(spray)
    assert any("kis esélyű lövést" in k for k in k1)
    picky = ScoutingReport(team="away", team_name="X", shots=12, xg=2.4)
    _, _, k2 = _coach_keys(picky)
    assert any("Válogatósak" in k for k in k2)
    few = ScoutingReport(team="away", team_name="X", shots=6, xg=0.4)
    _, _, k3 = _coach_keys(few)
    assert not any("xG/lövés" in k for k in k3)


def test_shot_selection_in_narrative():
    """A lövés-választás a Befejezésük narratívában is megjelenik."""
    from handball.pipeline.scouting import scouting_narrative
    rep = ScoutingReport(team="away", team_name="X", shots=20, goals=4,
                         xg=1.6)
    sec = next((x for x in scouting_narrative(rep)
                if x["title"] == "Befejezésük"), None)
    assert sec is not None
    assert "kis esélyű lövést" in sec["body"]


def test_attack_origin_key_and_merge():
    """Ha a gólok fele+ labdaszerzésből jön (5+ gólnál), kulcs születik;
    az eredet-számok pontosan összegződnek."""
    from handball.pipeline.scouting import (_coach_keys,
                                            _merge_attack_origins)
    rep = ScoutingReport(
        team="away", team_name="X",
        attack_origins={"labdaszerzés": {"attacks": 10, "goals": 4},
                        "kidobás": {"attacks": 6, "goals": 2}})
    _, _, keys = _coach_keys(rep)
    assert any("labdaszerzésből indul" in k for k in keys)
    few = ScoutingReport(
        team="away", team_name="X",
        attack_origins={"labdaszerzés": {"attacks": 4, "goals": 1},
                        "középkezdés": {"attacks": 8, "goals": 4}})
    _, _, k2 = _coach_keys(few)
    assert not any("labdaszerzésből indul" in k for k in k2)
    merged = _merge_attack_origins([rep, few])
    assert merged["labdaszerzés"] == {"attacks": 14, "goals": 5}


def test_attack_origin_in_narrative():
    """Az 50%+ arányú fő gól-forrás az Így támadnak narratívába kerül."""
    from handball.pipeline.scouting import scouting_narrative
    rep = ScoutingReport(
        team="away", team_name="X", avg_attack_duration_s=10.0,
        attack_origins={"labdaszerzés": {"attacks": 10, "goals": 4},
                        "kidobás": {"attacks": 6, "goals": 1}})
    secs = scouting_narrative(rep)
    body = " ".join(x["body"] for x in secs)
    assert "fő forrása: labdaszerzés" in body


def test_recovery_keys_and_combine():
    """Lassú visszarendeződés → "azonnal indíts" kulcs; gyors →
    "türelmes felállt támadás"; a számok összegződnek."""
    from handball.pipeline.scouting import _coach_keys
    slow = ScoutingReport(team="away", team_name="X",
                          rec_transitions=6, rec_sum_s=36.0, rec_slow=4)
    _, _, k1 = _coach_keys(slow)
    assert any("Lassan rendeződnek vissza" in k for k in k1)
    fast = ScoutingReport(team="away", team_name="X",
                          rec_transitions=6, rec_sum_s=12.0, rec_slow=0)
    _, _, k2 = _coach_keys(fast)
    assert any("Villámgyorsan visszaérnek" in k for k in k2)
    comb = combine_reports([slow, fast])
    assert comb.rec_transitions == 12
    assert abs(comb.rec_sum_s - 48.0) < 1e-6
    assert comb.rec_slow == 4


def test_key_players_detail_includes_position():
    """Elég mintánál a kulcsember-mérleg poszt-címkét is kap."""
    from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                          PlayerPosition, PositionSource)
    from handball.pipeline.scouting import match_key_players

    def pl(tid, x, y):
        return PlayerPosition(track_id=tid, team=Team.HOME, x=x, y=y,
                              source=PositionSource.MEASURED,
                              confidence=1.0)

    frames = []
    t = 0
    # Hosszú birtoklás-fázis: az 1-es középen, ~7 m-re áll (beálló).
    for _ in range(150):
        frames.append(Frame(t=t, players=[pl(1, 33.0, 10.0)],
                            ball=Ball(x=33.2, y=10.0, confidence=1.0)))
        t += 1
    # Négy lövése gólt ér → Fő lövő.
    for _ in range(4):
        for i in range(7):
            frames.append(Frame(t=t, players=[pl(1, 33.0, 10.0)],
                                ball=Ball(x=34.0 + i, y=10.0,
                                          confidence=1.0)))
            t += 1
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 20
    m = Match(MatchMeta(match_id="kpp", home_team="H", away_team="A",
                        fps=25.0), frames)
    kp = match_key_players(m)
    fo = next(it for it in kp["home"] if it["role"] == "Fő lövő")
    assert "· beálló" in fo["detail"]


def test_key_players_get_estimated_positions():
    """A kulcsjátékos-lista "mezőnyjátékos" címkéje helyett becsült
    poszt kerül, ha van elég minta."""
    from handball.models.tracking import (Ball, Frame,
                                          PlayerPosition, PositionSource)
    from handball.pipeline.scouting import _key_players
    from handball.pipeline.tactics import TacticsConfig

    def pl(tid, x, y):
        return PlayerPosition(track_id=tid, team=Team.HOME, x=x, y=y,
                              source=PositionSource.MEASURED,
                              confidence=1.0)

    frames = []
    for t in range(150):
        frames.append(Frame(t=t, players=[
            pl(1, 34.0, 10.0),   # beálló-hely
            pl(2, 36.0, 2.0),    # szélső-hely
            pl(3, 28.0, 10.0),   # nála a labda → irányító marad
        ], ball=Ball(x=28.3, y=10.0, confidence=1.0)))
    from handball.models.tracking import Match, MatchMeta
    m = Match(MatchMeta(match_id="kpe", home_team="H", away_team="A",
                        fps=25.0), frames)
    rows = _key_players(m, Team.HOME, TacticsConfig())
    roles = {r.track_id: r.role for r in rows}
    assert roles[3] == "irányító"       # birtoklásból, mint eddig
    assert roles[1] == "beálló"
    assert roles[2] == "szélső"


def test_positions_narrative_and_merge():
    """A becsült posztok "Felállásuk" szekcióként jelennek meg; a
    combine az első érdemi becslést tartja meg."""
    from handball.pipeline.scouting import scouting_narrative
    rep = ScoutingReport(team="away", team_name="X",
                         positions={1: "beálló", 2: "szélső",
                                    3: "irányító"})
    sec = next((x for x in scouting_narrative(rep)
                if x["title"] == "Felállásuk"), None)
    assert sec is not None
    assert "beálló: 1." in sec["body"]
    assert "szélső: 2." in sec["body"]
    newer = ScoutingReport(team="away", team_name="X",
                           positions={1: "átlövő"})
    comb = combine_reports([rep, newer])
    assert comb.positions[1] == "beálló"   # az első becslés marad
    assert comb.positions[2] == "szélső"


def test_pivot_key_from_positions():
    """Egyértelmű beállónál célzott kulcs születik; két beállónál nem."""
    from handball.pipeline.scouting import _coach_keys
    rep = ScoutingReport(team="away", team_name="X",
                         positions={1: "beálló", 2: "szélső"})
    _, _, keys = _coach_keys(rep)
    assert any("beállójuk a(z) 1. játékos" in k for k in keys)
    two = ScoutingReport(team="away", team_name="X",
                         positions={1: "beálló", 5: "beálló"})
    _, _, k2 = _coach_keys(two)
    assert not any("beállójuk" in k for k in k2)


def test_wing_dependency_keys_and_combine():
    """40%+ szélső-gólnál sáv-zárás kulcs; 10% alatt (ismert szélsőkkel)
    szűkítés-kulcs; a számok összegződnek."""
    from handball.pipeline.scouting import _coach_keys
    heavy = ScoutingReport(team="away", team_name="X",
                           wing_goals=4, wing_total_goals=8,
                           positions={2: "szélső"})
    _, _, k1 = _coach_keys(heavy)
    assert any("szélsőik szerzik" in k for k in k1)
    light = ScoutingReport(team="away", team_name="X",
                           wing_goals=0, wing_total_goals=8,
                           positions={2: "szélső"})
    _, _, k2 = _coach_keys(light)
    assert any("alig vannak játékban" in k for k in k2)
    comb = combine_reports([heavy, light])
    assert comb.wing_goals == 4
    assert comb.wing_total_goals == 16


def test_post_goal_distribution_narrative_and_combine():
    """A posztonkénti gól-eloszlás megjelenik a Befejezésük szekcióban,
    és meccsek közt pontosan összegződik."""
    from handball.pipeline.scouting import scouting_narrative
    rep = ScoutingReport(team="away", team_name="X", shots=12, goals=8,
                         post_goals={"szélső": 4, "átlövő": 4})
    sec = next(x for x in scouting_narrative(rep)
               if x["title"] == "Befejezésük")
    assert "Gól-eloszlás posztok szerint" in sec["body"]
    assert "szélső 50%" in sec["body"]
    other = ScoutingReport(team="away", team_name="X",
                           post_goals={"szélső": 1, "beálló": 2})
    comb = combine_reports([rep, other])
    assert comb.post_goals == {"szélső": 5, "átlövő": 4, "beálló": 2}


def test_seven_earner_key_and_merge():
    """2+ kiharcolt hetes ugyanattól a játékostól → fegyelem-kulcs;
    a darabszámok összegződnek."""
    from handball.pipeline.scouting import (_coach_keys,
                                            _merge_seven_earners)
    rep = ScoutingReport(team="away", team_name="X",
                         seven_earners=[{"player_id": 9, "earned": 2}])
    _, _, keys = _coach_keys(rep)
    assert any("harcolja ki" in k and "9. játékos" in k for k in keys)
    one = ScoutingReport(team="away", team_name="X",
                         seven_earners=[{"player_id": 9, "earned": 1}])
    _, _, k2 = _coach_keys(one)
    assert not any("harcolja ki" in k for k in k2)
    merged = _merge_seven_earners([rep, one])
    assert merged[0] == {"player_id": 9, "earned": 3}


def test_match_key_players_seven_earner_role():
    """2 kiharcolt hetes → Hetes-kiharcoló szerep a kulcsemberek közt."""
    from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                          PlayerPosition, PositionSource)
    from handball.pipeline.scouting import match_key_players

    def pl(tid, x, y):
        return PlayerPosition(track_id=tid, team=Team.HOME, x=x, y=y,
                              source=PositionSource.MEASURED,
                              confidence=1.0)

    frames = []
    t = 0
    for _ in range(2):  # két kiharcolt hetes, mindig a 9-es tör be
        for _ in range(50):
            frames.append(Frame(
                t=t, players=[pl(9, 37.5, 10.0), pl(1, 28.0, 10.0)],
                ball=Ball(x=36.0, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(50):
            frames.append(Frame(
                t=t, players=[pl(9, 34.0, 10.0), pl(1, 30.0, 10.0)],
                ball=Ball(x=33.0, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(200):  # 8 mp szünet: a 10 mp-es hetes-debounce
            frames.append(Frame(t=t, players=[pl(1, 25.0, 10.0)],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    m = Match(MatchMeta(match_id="se", home_team="H", away_team="A",
                        fps=25.0), frames)
    kp = match_key_players(m)
    role = next((it for it in kp["home"]
                 if it["role"] == "Hetes-kiharcoló"), None)
    assert role is not None
    assert role["player_id"] == 9


def test_matchup_plan_theme_order():
    """A meccsterv téma szerint rendeződik (kapus → védekezés →
    támadás → fegyelem → hajrá → egyéb), a témán belül a szabályok
    eredeti sorrendjében."""
    from handball.pipeline.scouting import _mpl_order

    nyers = [
        "A hajrában rájuk kell vinni a tempót.",          # hajrá
        "A falukat a bal oldalon kell megjáratni.",       # védekezés
        "A kapusuk lassan ér haza a 7 a 6 után.",         # kapus
        "Semleges mondat mindenféle kulcsszó nélkül.",    # egyéb
        "A kétperceiket egy ember gyűjti.",               # fegyelem
        "A kontrát az ő oldalukra kell vezetni.",         # támadás
        "A falukat a jobb oldalon is meg lehet járatni.",  # védekezés
    ]
    rendezett = _mpl_order(nyers)
    assert rendezett[0].startswith("A kapusuk")
    assert rendezett[1].startswith("A falukat a bal")
    assert rendezett[2].startswith("A falukat a jobb")   # stabil sorrend
    assert rendezett[3].startswith("A kontrát")
    assert rendezett[4].startswith("A kétperceiket")
    assert rendezett[5].startswith("A hajrában")
    assert rendezett[-1].startswith("Semleges")
    assert sorted(rendezett) == sorted(nyers)            # nincs veszteség


def test_matchup_plan_crosses_both_profiles():
    """A meccsterv-illesztés csak akkor ad mondatot, ha MINDKÉT oldal
    feltétele teljesül."""
    from handball.pipeline.scouting import matchup_plan
    own = ScoutingReport(team="home", team_name="Mi", matches=2,
                         fast_break_pct=15.0, shots=20,
                         turnover_front=6,
                         rec_transitions=5, rec_sum_s=30.0)
    opp = ScoutingReport(team="away", team_name="Ok", matches=2,
                         rec_transitions=6, rec_sum_s=36.0,
                         gk_xg_prevented=-2.4,
                         gk_outlets=4, gk_outlet_fast=3,
                         attack_origins={"labdaszerzés":
                                         {"attacks": 10, "goals": 5}})
    plan = matchup_plan(own, opp)
    joined = " ".join(plan)
    assert "kontra ebben a párosításban" in joined
    assert "kapura lövést" in joined
    assert "labdabiztonság ezen a meccsen" in joined
    assert "azonnali visszafutás" in joined
    # Ha a saját oldal nem kontrázik, a kontra-mondat elmarad.
    slow_own = ScoutingReport(team="home", team_name="Mi",
                              fast_break_pct=2.0)
    plan2 = matchup_plan(slow_own, opp)
    assert not any("kontra ebben a párosításban" in p_ for p_ in plan2)


def test_matchup_plan_extended_rules():
    """A 6-8. meccsterv-szabályok is páros-feltételesek."""
    from handball.pipeline.scouting import matchup_plan
    own = ScoutingReport(team="home", team_name="Mi", matches=2,
                         gk_xg_saved=2.4, gk_big_saves=3,
                         sub_rotations=3, sub_after_for=4,
                         sub_after_against=2)
    opp = ScoutingReport(team="away", team_name="Ok", matches=2,
                         seven_takers=[{"player_id": 11, "attempts": 4,
                                        "goals": 1}],
                         pace_attacks=60, pace_minutes=50.0,
                         big_total=6, big_missed=4)
    plan = matchup_plan(own, opp)
    joined = " ".join(plan)
    assert "ez a párbaj nektek áll" in joined
    assert "friss lábak nálatok" in joined
    assert "nagy helyzeteik sem biztos gólok" in joined
    # Gyenge saját kapusnál a hetes-párbaj mondat elmarad.
    weak_own = ScoutingReport(team="home", team_name="Mi", matches=2,
                              gk_xg_saved=0.2)
    plan2 = matchup_plan(weak_own, opp)
    assert not any("párbaj nektek áll" in p_ for p_ in plan2)


def test_matchup_plan_discipline_rule():
    """9. szabály: az ő fegyelmezetlen védőjük × a mi kiharcolónk —
    mindkét oldal küszöbe kell hozzá."""
    from handball.pipeline.scouting import matchup_plan
    own = ScoutingReport(team="home", team_name="Mi",
                         susp_earners=[{"player_id": 7, "earned": 2}])
    opp = ScoutingReport(team="away", team_name="Ok",
                         susp_players=[{"player_id": 105,
                                        "suspensions": 2}])
    plan = matchup_plan(own, opp)
    joined = " ".join(plan)
    assert "105. játékosuk fegyelmezetlen" in joined
    assert "7. játékos harcolja ki" in joined
    # Kiharcoló nélkül a mondat elmarad.
    plan2 = matchup_plan(ScoutingReport(team="home", team_name="Mi"),
                         opp)
    assert not any("fegyelmezetlen" in p_ for p_ in plan2)


def test_trend_includes_suspensions_metric():
    """A fejlődés-követés hozza a kiállítás/meccs mutatót — a kevesebb
    a jobb, és a 0 valós értékként számít (nem "nincs mérés")."""
    from handball.pipeline.scouting import trend_report
    older = ScoutingReport(team="home", team_name="Mi", matches=2,
                           suspensions=4)
    newer = ScoutingReport(team="home", team_name="Mi", matches=2,
                           suspensions=0)
    tr = trend_report(older, newer)
    rec = next((m_ for m_ in tr["metrics"]
                if m_["metric"] == "suspensions"), None)
    assert rec is not None
    assert rec["older"] == 2.0 and rec["newer"] == 0.0
    assert rec["better"] is True


def test_restart_keys_both_directions():
    """A szünet utáni kezdés kulcsa mindkét irányban, +-3 gólkülönbség
    fölött szólal meg."""
    from handball.pipeline.scouting import _coach_keys
    weak = ScoutingReport(team="away", team_name="X",
                          restart_matches=2, restart_for=1,
                          restart_against=4)
    _, _, keys = _coach_keys(weak)
    assert any("öltözőből rosszul jönnek ki" in k for k in keys)
    strong = ScoutingReport(team="away", team_name="X",
                            restart_matches=2, restart_for=5,
                            restart_against=1)
    _, _, k2 = _coach_keys(strong)
    assert any("ők ütnek először" in k for k in k2)
    quiet = ScoutingReport(team="away", team_name="X",
                           restart_matches=2, restart_for=2,
                           restart_against=3)
    _, _, k3 = _coach_keys(quiet)
    assert not any("öltözőből" in k or "ütnek először" in k
                   for k in k3)


def test_lead_management_keys():
    """Előny-kezelés kulcsok: időhúzás vezetve (+ kapkodás hátrányban),
    kis különbségnél hallgatás."""
    from handball.pipeline.scouting import _coach_keys
    slowlead = ScoutingReport(team="away", team_name="X",
                              lead_attacks=5, lead_sum_s=150.0,
                              trail_attacks=5, trail_sum_s=50.0)
    _, _, keys = _coach_keys(slowlead)
    assert any("Előnyben húzzák az időt" in k for k in keys)
    assert any("Hátrányban kapkodnak" in k for k in keys)
    even = ScoutingReport(team="away", team_name="X",
                          lead_attacks=5, lead_sum_s=100.0,
                          trail_attacks=5, trail_sum_s=90.0)
    _, _, k2 = _coach_keys(even)
    assert not any("Előnyben húzzák" in k for k in k2)


def test_matchup_plan_slowdown_rule():
    """10. szabály: az ő időhúzásuk × a mi erős első félidőnk."""
    from handball.pipeline.scouting import matchup_plan
    own = ScoutingReport(team="home", team_name="Mi",
                         fh_goals_for=12, fh_goals_against=8)
    opp = ScoutingReport(team="away", team_name="Ok",
                         lead_attacks=5, lead_sum_s=150.0,
                         trail_attacks=5, trail_sum_s=50.0)
    plan = matchup_plan(own, opp)
    assert any("altatják a meccset" in p_ for p_ in plan)
    # Gyenge saját kezdésnél a mondat elmarad.
    weak = ScoutingReport(team="home", team_name="Mi",
                          fh_goals_for=8, fh_goals_against=8)
    plan2 = matchup_plan(weak, opp)
    assert not any("altatják" in p_ for p_ in plan2)


def test_discipline_narrative_section():
    """A Fegyelmük szakasz 2+ kiállításnál jelenik meg, a kiülőkkel és
    a kiharcolóval; fegyelmezett csapatnál nincs ilyen szakasz."""
    from handball.pipeline.scouting import scouting_narrative
    rep = ScoutingReport(
        team="away", team_name="X", matches=2, suspensions=4,
        susp_players=[{"player_id": 105, "suspensions": 2},
                      {"player_id": 103, "suspensions": 1}],
        susp_earners=[{"player_id": 9, "earned": 2}])
    secs = scouting_narrative(rep)
    sec = next((s_ for s_ in secs if s_["title"] == "Fegyelmük"), None)
    assert sec is not None
    assert "4 kiállítás" in sec["body"]
    assert "105. (2×)" in sec["body"]
    assert "9. játékosuk harcolja ki" in sec["body"]
    clean = ScoutingReport(team="away", team_name="X", matches=2,
                           suspensions=1)
    assert not any(s_["title"] == "Fegyelmük"
                   for s_ in scouting_narrative(clean))


def test_best_figure_key_and_combine():
    """A működő figura kulcsot ad (3+ támadás, 2+ gól); a kombinált
    profilban a legerősebb meccs-figura marad."""
    from handball.pipeline.scouting import _coach_keys, combine_reports
    strong = ScoutingReport(team="away", team_name="X", matches=1,
                            best_fig_attacks=4, best_fig_goals=3)
    _, _, keys = _coach_keys(strong)
    assert any("figurájuk, ami működik" in k for k in keys)
    weak = ScoutingReport(team="away", team_name="X", matches=1,
                          best_fig_attacks=2, best_fig_goals=1)
    _, _, k2 = _coach_keys(weak)
    assert not any("figurájuk, ami működik" in k for k in k2)
    merged = combine_reports([weak, strong])
    assert merged.best_fig_goals == 3
    assert merged.best_fig_attacks == 4


def test_matchup_plan_figure_rule():
    """11. szabály: az ő működő figurájuk × a mi fedezés-hibáink —
    páros-feltételes."""
    from handball.pipeline.scouting import matchup_plan
    own = ScoutingReport(team="home", team_name="Mi",
                         def_shots_against=10, def_free_shots=5)
    opp = ScoutingReport(team="away", team_name="Ok",
                         best_fig_attacks=4, best_fig_goals=3)
    plan = matchup_plan(own, opp)
    assert any("figura-felismerés nálatok életbiztosítás" in p_
               for p_ in plan)
    tight = ScoutingReport(team="home", team_name="Mi",
                           def_shots_against=10, def_free_shots=1)
    plan2 = matchup_plan(tight, opp)
    assert not any("életbiztosítás" in p_ for p_ in plan2)


def test_attack_width_keys_both_directions():
    """Széles támadásnál kilépés-fegyelem, szűknél szűkítés-kulcs;
    köztes értéknél hallgatás."""
    from handball.pipeline.scouting import _coach_keys
    wide = ScoutingReport(team="away", team_name="X",
                          width_frames=200, width_sum_m=3000.0)
    _, _, keys = _coach_keys(wide)
    assert any("Szélesen támadnak" in k for k in keys)
    narrow = ScoutingReport(team="away", team_name="X",
                            width_frames=200, width_sum_m=1600.0)
    _, _, k2 = _coach_keys(narrow)
    assert any("Szűken támadnak" in k for k in k2)
    mid = ScoutingReport(team="away", team_name="X",
                         width_frames=200, width_sum_m=2300.0)
    _, _, k3 = _coach_keys(mid)
    assert not any("támadnak (" in k for k in k3)


def test_matchup_plan_width_rule():
    """12. szabály: az ő széles játékuk × a mi szél-góljaink —
    páros-feltételes."""
    from handball.pipeline.scouting import matchup_plan
    own = ScoutingReport(team="home", team_name="Mi",
                         gk_conceded_zones={"balszél": 3, "jobbszél": 1,
                                            "átlövés közép": 4})
    opp = ScoutingReport(team="away", team_name="Ok",
                         width_frames=200, width_sum_m=3000.0)
    plan = matchup_plan(own, opp)
    assert any("szélső-védő kilépés-fegyelme" in p_ for p_ in plan)
    center = ScoutingReport(team="home", team_name="Mi",
                            gk_conceded_zones={"átlövés közép": 8})
    plan2 = matchup_plan(center, opp)
    assert not any("kilépés-fegyelme ezen a meccsen" in p_
                   for p_ in plan2)


def test_matchup_plan_far_keeper_rule():
    """20. szabály: az ő kapusuk gyenge a távolira × a mi távoli
    lövés-erőnk — páros-feltételes."""
    from handball.pipeline.scouting import matchup_plan
    own = ScoutingReport(team="home", team_name="Mi",
                         sr_close_shots=2, sr_mid_shots=1, sr_far_shots=6)
    opp = ScoutingReport(team="away", team_name="Ok",
                         gk_far_faced=6, gk_far_saves=2)  # 33% távoli védés
    plan = matchup_plan(own, opp)
    assert any("távoli lövésekre gyenge" in p_ for p_ in plan)
    # Ha alig lövünk kintről, a szabály nem szólal meg.
    few = ScoutingReport(team="home", team_name="Mi",
                         sr_close_shots=8, sr_far_shots=1)
    assert not any("távoli lövésekre gyenge" in p_
                   for p_ in matchup_plan(few, opp))
    # Ha a kapusuk jól véd a távolira, szintén nem.
    good_gk = ScoutingReport(team="away", team_name="Ok",
                             gk_far_faced=6, gk_far_saves=5)
    assert not any("távoli lövésekre gyenge" in p_
                   for p_ in matchup_plan(own, good_gk))


def test_markers_merge_and_matchup_loose_rule():
    """Az emberfogó-számok (kockák + táv-összeg) meccsek közt pontosan
    összegződnek; a 13. meccsterv-szabály a laza emberfogóra csak a
    küszöbök felett süt el."""
    from handball.pipeline.scouting import combine_reports, matchup_plan
    r1 = ScoutingReport(team="away", team_name="Ok", matches=1,
                        markers=[{"player_id": 4, "frames": 40,
                                  "dist_sum": 110.0}])
    r2 = ScoutingReport(team="away", team_name="Ok", matches=1,
                        markers=[{"player_id": 4, "frames": 30,
                                  "dist_sum": 90.0},
                                 {"player_id": 2, "frames": 60,
                                  "dist_sum": 60.0}])
    comb = combine_reports([r1, r2])
    by_pid = {m["player_id"]: m for m in comb.markers}
    assert by_pid[4]["frames"] == 70
    assert abs(by_pid[4]["dist_sum"] - 200.0) < 0.01
    assert by_pid[2]["frames"] == 60
    # A 4-es átlaga 200/70 ≈ 2,86 m — laza; a 13. szabály róla szól.
    own = ScoutingReport(team="home", team_name="Mi")
    plan = matchup_plan(own, comb)
    assert any("4-es védőjük lazán őrzi" in p_ for p_ in plan)
    # Szoros emberfogóval (2-es, 1 m átlag) nem szól a szabály.
    tight = ScoutingReport(team="away", team_name="Ok", markers=[
        {"player_id": 2, "frames": 60, "dist_sum": 60.0}])
    assert not any("lazán őrzi" in p_ for p_ in matchup_plan(own, tight))


def test_coach_keys_flag_loose_marker():
    """Az edzői kulcsok a laza emberfogót gyengeségként és "hova
    játssz" kulcsként is hozzák; szoros emberfogónál hallgatnak."""
    from handball.pipeline.scouting import _coach_keys
    rep = ScoutingReport(team="away", team_name="Ok", matches=1,
                         markers=[{"player_id": 9, "frames": 80,
                                   "dist_sum": 240.0}])
    _, weaknesses, keys = _coach_keys(rep)
    assert any("9-es védőjük lazán őrzi" in w for w in weaknesses)
    assert any("egy-egy elleni játékot" in k for k in keys)
    tight = ScoutingReport(team="away", team_name="Ok", matches=1,
                           markers=[{"player_id": 9, "frames": 80,
                                     "dist_sum": 80.0}])
    _, w2, k2 = _coach_keys(tight)
    assert not any("lazán őrzi" in w for w in w2)


def test_coach_keys_and_matchup_tight_marker():
    """A tapadó emberfogó (<=1,5 m átlag, 50+ kocka) erősség + "csak
    elzárással" kulcs; a 14. meccsterv-szabály a fő lövővel párosítva
    süt el."""
    from handball.pipeline.scouting import _coach_keys, matchup_plan
    opp = ScoutingReport(team="away", team_name="Ok", matches=1,
                         markers=[{"player_id": 3, "frames": 80,
                                   "dist_sum": 96.0}])
    strengths, _, keys = _coach_keys(opp)
    assert any("3-es védőjük tapadó emberfogó" in s_ for s_ in strengths)
    assert any("csak" in k and "elzárással" in k for k in keys)
    own = ScoutingReport(team="home", team_name="Mi",
                         shooter_overperf=[{"player_id": 7,
                                            "diff": 1.5}])
    plan = matchup_plan(own, opp)
    assert any("tapadó emberfogó" in p_ and "7. játékos" in p_
               for p_ in plan)
    # Fő lövő nélkül a 14. szabály hallgat.
    plan2 = matchup_plan(ScoutingReport(team="home", team_name="Mi"),
                         opp)
    assert not any("tapadó emberfogó" in p_ for p_ in plan2)


def test_pivot_fields_merge_and_matchup_rule():
    """A beálló-terhelés darabszámai meccsek közt összegződnek; a 15.
    szabály (beálló-terhelés × kiállítás-hajlam) mindkét küszöbhöz
    kötött; az edzői kulcs a terhelés-arányról szól."""
    from handball.pipeline.scouting import (_coach_keys, combine_reports,
                                            matchup_plan)
    r1 = ScoutingReport(team="away", team_name="Ok", matches=1,
                        pivot_total_attacks=5, pivot_attacks=3,
                        pivot_goals=2, pivot_other_goals=0)
    r2 = ScoutingReport(team="away", team_name="Ok", matches=1,
                        pivot_total_attacks=5, pivot_attacks=2,
                        pivot_goals=1, pivot_other_goals=1)
    comb = combine_reports([r1, r2])
    assert comb.pivot_total_attacks == 10
    assert comb.pivot_attacks == 5
    assert comb.pivot_goals == 3
    assert comb.pivot_other_goals == 1
    _, _, keys = _coach_keys(comb)
    assert any("a beállón át megy" in k for k in keys)
    own = ScoutingReport(team="home", team_name="Mi", suspensions=2)
    plan = matchup_plan(own, comb)
    assert any("testtel és helyezkedéssel" in p_ for p_ in plan)
    # Fegyelmezett csapatnál (0 kiállítás) a 15. szabály hallgat.
    plan2 = matchup_plan(ScoutingReport(team="home", team_name="Mi"),
                         comb)
    assert not any("testtel és helyezkedéssel" in p_ for p_ in plan2)


def test_trend_includes_pivot_metric():
    """A fejlődés-követés hozza a beállós támadás / meccs mutatót,
    meccsenkénti átlagra normálva."""
    from handball.pipeline.scouting import trend_report
    older = ScoutingReport(team="home", team_name="Mi", matches=2,
                           pivot_attacks=4)
    newer = ScoutingReport(team="home", team_name="Mi", matches=2,
                           pivot_attacks=8)
    tr = trend_report(older, newer)
    row = next(r_ for r_ in tr["metrics"]
               if r_["label"] == "Beállós támadás / meccs")
    assert row["older"] == 2.0 and row["newer"] == 4.0


def test_break_lanes_merge_keys_and_rule16():
    """A betörés-sávok meccsek közt összegződnek; a kulcs 40%+
    koncentrációnál, a 16. szabály laza fallal párosítva szól."""
    from handball.pipeline.scouting import (_coach_keys, combine_reports,
                                            matchup_plan)
    r1 = ScoutingReport(team="away", team_name="Ok", matches=1,
                        break_entries=4,
                        break_lanes={"közép": {"entries": 3, "goals": 1},
                                     "bal szél": {"entries": 1,
                                                  "goals": 0}})
    r2 = ScoutingReport(team="away", team_name="Ok", matches=1,
                        break_entries=4,
                        break_lanes={"közép": {"entries": 3,
                                               "goals": 2}})
    comb = combine_reports([r1, r2])
    assert comb.break_entries == 8
    assert comb.break_lanes["közép"] == {"entries": 6, "goals": 3}
    _, _, keys = _coach_keys(comb)
    assert any("közép sávban jön" in k for k in keys)
    own = ScoutingReport(team="home", team_name="Mi",
                         defensive_pressure_m=2.4)
    plan = matchup_plan(own, comb)
    assert any("lépj ki korábban" in p_ for p_ in plan)
    # Szoros fallal a 16. szabály hallgat.
    tight = ScoutingReport(team="home", team_name="Mi",
                           defensive_pressure_m=1.2)
    assert not any("lépj ki korábban" in p_
                   for p_ in matchup_plan(tight, comb))


def test_pass_chain_merge_keys_and_rule17():
    """A passz-vödrök meccsek közt összegződnek; a gyors első hullám
    kulcsa és a 17. szabály (villámtámadás × gyenge visszazárás) a
    küszöbökhöz kötött."""
    from handball.pipeline.scouting import (_coach_keys, combine_reports,
                                            matchup_plan)
    r1 = ScoutingReport(team="away", team_name="Ok", matches=1,
                        pass_attacks=5, pass_total=8,
                        pass_buckets={"0–2 passz": {"attacks": 3,
                                                    "goals": 2}})
    r2 = ScoutingReport(team="away", team_name="Ok", matches=1,
                        pass_attacks=5, pass_total=10,
                        pass_buckets={"0–2 passz": {"attacks": 2,
                                                    "goals": 1},
                                      "6+ passz": {"attacks": 3,
                                                   "goals": 0}})
    comb = combine_reports([r1, r2])
    assert comb.pass_attacks == 10 and comb.pass_total == 18
    assert comb.pass_buckets["0–2 passz"] == {"attacks": 5, "goals": 3}
    _, _, keys = _coach_keys(comb)
    assert any("gyors első hullámból élnek" in k for k in keys)
    own = ScoutingReport(team="home", team_name="Mi",
                         transition_goals_against=2)
    plan = matchup_plan(own, comb)
    assert any("villámtámadásból" in p_ for p_ in plan)
    # Jó visszazárásnál a 17. szabály hallgat.
    ok_def = ScoutingReport(team="home", team_name="Mi")
    assert not any("villámtámadásból" in p_
                   for p_ in matchup_plan(ok_def, comb))


def test_rotation_merge_keys_and_rule18():
    """A rotáció-összegek meccsek közt összegződnek (átlag = összeg /
    meccsek); a szűk pad gyengeség + kulcs; a 18. szabály csak
    széles saját paddal szól."""
    from handball.pipeline.scouting import (_coach_keys, combine_reports,
                                            matchup_plan)
    r1 = ScoutingReport(team="away", team_name="Ok", matches=1,
                        rotation_used_sum=7, rotation_regulars_sum=6,
                        rotation_matches=1)
    r2 = ScoutingReport(team="away", team_name="Ok", matches=1,
                        rotation_used_sum=9, rotation_regulars_sum=6,
                        rotation_matches=1)
    comb = combine_reports([r1, r2])
    assert comb.rotation_used_sum == 16 and comb.rotation_matches == 2
    strengths, weaknesses, keys = _coach_keys(comb)
    assert any("Szűk rotációval" in w for w in weaknesses)
    assert any("vidd tempóban" in k for k in keys)
    own_wide = ScoutingReport(team="home", team_name="Mi",
                              rotation_used_sum=11,
                              rotation_regulars_sum=7,
                              rotation_matches=1)
    plan = matchup_plan(own_wide, comb)
    assert any("nyílik" in p_ and "olló" in p_ for p_ in plan)
    # Szűk saját paddal a 18. szabály hallgat.
    own_narrow = ScoutingReport(team="home", team_name="Mi",
                                rotation_used_sum=7,
                                rotation_regulars_sum=6,
                                rotation_matches=1)
    assert not any("olló" in p_ for p_ in matchup_plan(own_narrow, comb))


def test_ball_winners_merge_and_key():
    """A labdaszerző-számok meccsek közt összegződnek; 3+ szerzésnél
    erősség + "óvatos passz" kulcs születik."""
    from handball.pipeline.scouting import _coach_keys, combine_reports
    r1 = ScoutingReport(team="away", team_name="Ok", matches=1,
                        ball_winners=[{"player_id": 3, "steals": 2}])
    r2 = ScoutingReport(team="away", team_name="Ok", matches=1,
                        ball_winners=[{"player_id": 3, "steals": 2},
                                      {"player_id": 8, "steals": 1}])
    comb = combine_reports([r1, r2])
    by_pid = {w["player_id"]: w["steals"] for w in comb.ball_winners}
    assert by_pid == {3: 4, 8: 1}
    strengths, _, keys = _coach_keys(comb)
    assert any("3-es a labdaszerzőjük" in s_ for s_ in strengths)
    assert any("rövid, biztos passz" in k for k in keys)
    # Kevés szerzésnél nincs kulcs.
    few = ScoutingReport(team="away", team_name="Ok",
                         ball_winners=[{"player_id": 3, "steals": 2}])
    _, _, k2 = _coach_keys(few)
    assert not any("labdaszerző" in k for k in k2)


def test_gk_depth_merge_keys_and_rule19():
    """A kapus-mélység súlyozott átlaga meccsek közt pontosan
    összegződik; a kint álló kapus kulcsot ad, a 19. szabály csak
    kontra-erős saját csapattal szól."""
    from handball.pipeline.scouting import (_coach_keys, combine_reports,
                                            matchup_plan)
    r1 = ScoutingReport(team="away", team_name="Ok", matches=1,
                        gk_depth_sum_m=200.0, gk_depth_frames=100)
    r2 = ScoutingReport(team="away", team_name="Ok", matches=1,
                        gk_depth_sum_m=160.0, gk_depth_frames=100)
    comb = combine_reports([r1, r2])
    assert comb.gk_depth_frames == 200
    assert abs(comb.gk_depth_sum_m - 360.0) < 0.01  # átlag 1,8 m
    _, _, keys = _coach_keys(comb)
    assert any("átemelés és a lob" in k for k in keys)
    own = ScoutingReport(team="home", team_name="Mi",
                         fast_break_pct=15.0)
    plan = matchup_plan(own, comb)
    assert any("átemelést vállalni KELL" in p_ for p_ in plan)
    # Kontra nélkül a 19. szabály hallgat.
    slow = ScoutingReport(team="home", team_name="Mi",
                          fast_break_pct=4.0)
    assert not any("átemelést vállalni" in p_
                   for p_ in matchup_plan(slow, comb))


def test_transition_offense_merge_and_key():
    """Az átmenet-támadás darabszámai meccsek közt összegződnek; 4+
    szerzés / 2+ gyors gól / 30%+ konverziónál kulcs születik."""
    from handball.pipeline.scouting import _coach_keys, combine_reports
    r1 = ScoutingReport(team="away", team_name="Ok", matches=1,
                        trans_steals=3, trans_quick_goals=1)
    r2 = ScoutingReport(team="away", team_name="Ok", matches=1,
                        trans_steals=2, trans_quick_goals=2)
    comb = combine_reports([r1, r2])
    assert comb.trans_steals == 5 and comb.trans_quick_goals == 3
    _, _, keys = _coach_keys(comb)
    assert any("gyorsan gólra váltják" in k for k in keys)
    # Gyenge konverziónál nincs kulcs.
    weak = ScoutingReport(team="away", team_name="Ok",
                          trans_steals=10, trans_quick_goals=2)
    _, _, k2 = _coach_keys(weak)
    assert not any("gyorsan gólra váltják" in k for k in k2)


def _trend_rep(matches, shots_by_role, dist_sum, kmh_shots=None,
               kmh_sum=None):
    """Minimális jelentés a származtatott trend-mutatók teszteléséhez."""
    from handball.pipeline.scouting import ScoutingReport
    return ScoutingReport(
        team="home", team_name="Mi", matches=matches,
        attack_share_pct=60.0, fast_break_pct=10.0, avg_ball_speed_ms=4.0,
        avg_attack_duration_s=8.0, defense_main="6-0",
        defense_distribution={"6-0": 100.0},
        attack_centroid_x=30.0, attack_centroid_y=10.0, num_figures=0,
        attacks=10, shots=10, goals=5, turnovers=2,
        shot_efficiency_pct=50.0, key_players=[], strengths=[],
        weaknesses=[], keys_to_game=[],
        rsd_shots_by_role=shots_by_role, rsd_dist_sum_by_role=dist_sum,
        rsp_shots_by_role=kmh_shots or {}, rsp_kmh_sum_by_role=kmh_sum or {})


def test_trend_kozelebbi_befejezes_javulas():
    """A befejezés-távolság csökkenése JAVULÁS — közelebbről lőni jobb."""
    from handball.pipeline.scouting import trend_report

    older = _trend_rep(3, {"irányító": 10}, {"irányító": 120.0})   # 12,0 m
    newer = _trend_rep(3, {"irányító": 10}, {"irányító": 90.0})    # 9,0 m
    tr = trend_report(older, newer)
    rec = next(m for m in tr["metrics"] if m["metric"] == "shot_distance_m")
    assert rec["older"] == 12.0 and rec["newer"] == 9.0
    assert rec["better"] is True, rec
    assert any("befejezés-távolság" in s_ for s_ in tr["summary"]), tr


def test_trend_kimarad_ha_keves_a_loves():
    """Kevés mért lövésnél a mutató KIMARAD — nem látszik nulla-esésnek."""
    from handball.pipeline.scouting import trend_report

    older = _trend_rep(1, {"irányító": 3}, {"irányító": 36.0})
    newer = _trend_rep(1, {"irányító": 10}, {"irányító": 90.0})
    tr = trend_report(older, newer)
    assert not [m for m in tr["metrics"]
                if m["metric"] == "shot_distance_m"], tr["metrics"]


def test_trend_loveserobol_is_lesz_mutato():
    """A lövéserő növekedése javulás."""
    from handball.pipeline.scouting import trend_report

    older = _trend_rep(3, {}, {}, {"átlövő": 10}, {"átlövő": 900.0})
    newer = _trend_rep(3, {}, {}, {"átlövő": 10}, {"átlövő": 1100.0})
    tr = trend_report(older, newer)
    rec = next(m for m in tr["metrics"] if m["metric"] == "shot_power_kmh")
    assert rec["older"] == 90.0 and rec["newer"] == 110.0
    assert rec["better"] is True, rec


def test_combine_merges_every_by_role_field():
    """ŐR: minden *_by_role mező összegződik a combine_reports-ban.

    A réteg-recept 4. lépésének gyakori hibája, hogy az új
    posztonkénti mező kimarad az összevonásból — ilyenkor a több
    meccses felderítés csendben elveszíti a mintát. Ez a teszt
    minden posztonkénti számláló-mezőt kitölt, és megköveteli, hogy
    két meccs összevonása után pontosan duplázódjon.
    """
    import dataclasses

    role_fields = [f.name for f in dataclasses.fields(ScoutingReport)
                   if f.name.endswith("_by_role")]
    assert len(role_fields) >= 50, role_fields  # az olvasás elromlott

    r1 = ScoutingReport(team="home", team_name="Teszt")
    r2 = ScoutingReport(team="home", team_name="Teszt")
    for name in role_fields:
        setattr(r1, name, {"beálló": 1})
        setattr(r2, name, {"beálló": 1})
    comb = combine_reports([r1, r2])
    rossz = [name for name in role_fields
             if getattr(comb, name).get("beálló") != 2]
    assert not rossz, f"nem összegzett posztonkénti mezők: {rossz}"


def test_minden_posztonkenti_mezo_eljut_edzoi_feluletre():
    """ŐR: minden *_by_role mező jusson el edzői felületre — vagy az
    edzői kulcsok (_coach_keys), vagy a meccsterv (matchup_plan)
    olvassa. Egy csak eltárolt, de sehol nem olvasott posztonkénti
    mező holt adat: a réteg-recept 4. lépése fél-kész maradt."""
    import dataclasses
    import inspect

    from handball.pipeline import scouting

    fields = [f.name for f in dataclasses.fields(scouting.ScoutingReport)
              if f.name.endswith("_by_role")]
    assert len(fields) >= 60, fields   # az olvasás elromlott
    src = (inspect.getsource(scouting._coach_keys)
           + inspect.getsource(scouting.matchup_plan))
    arva = [f for f in fields if f not in src]
    assert not arva, f"edzői felület nélküli posztonkénti mezők: {arva}"


def _sty_rep(**kw):
    """Stílus-teszt felderítés: csak a stílus-tengelyek mezői."""
    from handball.models.tracking import Team
    from handball.pipeline.scouting import ScoutingReport

    rep = ScoutingReport(team=Team.HOME, team_name="X")
    alap = dict(shots=20, sr_close_shots=5, sr_mid_shots=5,
                sr_far_shots=10, pace_minutes=30.0, pace_attacks=60,
                fast_break_pct=20.0, scy_screened_shots=6,
                scy_clean_shots=6, pivot_total_attacks=20,
                pivot_attacks=10, agr_susp=3, svy_attempts=3,
                matches=1)
    alap.update(kw)
    for k, v in alap.items():
        setattr(rep, k, v)
    return rep


def test_style_distance_mirror_and_axes():
    """Azonos profilú csapatoknál tükör-meccs, és minden közös
    tengely bekerül a listába."""
    from handball.pipeline.scouting import (STY_MIRROR_PCT,
                                            style_distance)

    rec = style_distance(_sty_rep(), _sty_rep())
    assert rec["score_pct"] == 100.0, rec
    assert rec["score_pct"] >= STY_MIRROR_PCT
    assert len(rec["axes"]) >= 4, rec
    assert rec["verdict"] and "tükör-meccs" in rec["verdict"], rec


def test_style_distance_names_the_biggest_gap():
    """Eltérő profilnál a legnagyobb szakadékot nevezi meg."""
    from handball.pipeline.scouting import style_distance

    lassu = _sty_rep(sr_close_shots=15, sr_mid_shots=4, sr_far_shots=1,
                     pace_attacks=20, fast_break_pct=3.0,
                     scy_screened_shots=1, scy_clean_shots=11,
                     pivot_attacks=19, agr_susp=0, svy_attempts=0)
    rec = style_distance(_sty_rep(), lassu)
    assert rec["score_pct"] is not None and rec["score_pct"] < 100.0
    assert rec["farthest"] in {a["axis"] for a in rec["axes"]}
    assert rec["axes"][-1]["axis"] == rec["farthest"]
    assert rec["verdict"], rec


def test_style_distance_silent_with_few_axes():
    """Kevés közös tengelynél nincs ítélet (nem találgatunk)."""
    from handball.models.tracking import Team
    from handball.pipeline.scouting import (ScoutingReport,
                                            style_distance)

    ures = ScoutingReport(team=Team.HOME, team_name="Y")
    rec = style_distance(ures, ures)
    assert rec["score_pct"] is None and rec["verdict"] is None, rec


def test_matchup_plan_starts_with_match_character():
    """A meccs jellege (tükör-/ellentétes stílus) a lap élére kerül."""
    from handball.pipeline.scouting import matchup_plan

    plan = matchup_plan(_sty_rep(), _sty_rep())
    assert plan, plan
    assert plan[0].startswith("Tükör-meccs"), plan[0]


def test_a_meccsterv_kimondja_ha_gyenge_az_alapanyag():
    """A meccsterv az, ami alapján az edző dönt.

    Ha a mögötte lévő feldolgozás gyenge volt, a terv nem a másik
    csapatról szól, hanem a mérés zajáról — és ezt nem szabad
    elhallgatni, mert a jelentés minden mondata magabiztosan fogalmaz.
    """
    from handball.pipeline.scouting import ScoutingReport, scouting_caveat

    rep = ScoutingReport(team="home", team_name="A")
    rep.q_matches = 1
    rep.q_score_sum = 31.0
    rep.q_weak_matches = 1
    cav = scouting_caveat(rep)
    assert cav is not None
    assert "31/100" in cav
    assert "zaj" in cav


def test_tobb_meccsnel_a_gyengek_szamat_is_kimondja():
    """5 meccsből 1 gyenge más helyzet, mint 5-ből 5 — a számot is
    meg kell mondani, hogy az edző mérlegelhessen."""
    from handball.pipeline.scouting import ScoutingReport, scouting_caveat

    rep = ScoutingReport(team="home", team_name="A", matches=5)
    rep.q_matches = 5
    rep.q_score_sum = 5 * 40.0
    rep.q_weak_matches = 2
    cav = scouting_caveat(rep)
    assert cav is not None
    assert "5 meccsből" in cav and "2 feldolgozása" in cav


def test_jo_feldolgozasnal_es_regi_jelentesnel_nincs_figyelmeztetes():
    """Jó feldolgozásnál nincs miről szólni; adat nélküli (régi)
    jelentésről pedig nem állítunk semmit."""
    from handball.pipeline.scouting import ScoutingReport, scouting_caveat

    jo = ScoutingReport(team="home", team_name="A")
    jo.q_matches = 3
    jo.q_score_sum = 3 * 85.0
    jo.q_weak_matches = 0
    assert scouting_caveat(jo) is None

    regi = ScoutingReport(team="home", team_name="A")
    assert scouting_caveat(regi) is None


def test_a_figyelmeztetes_a_kliensnek_kuldott_szotarban_is_ott_van():
    """A kliens ebből rajzolja a dobozt — enélkül a mondat a motorban
    ragadna."""
    from handball.pipeline.scouting import ScoutingReport, report_to_dict

    rep = ScoutingReport(team="home", team_name="A")
    rep.q_matches = 1
    rep.q_score_sum = 20.0
    rep.q_weak_matches = 1
    d = report_to_dict(rep)
    assert d["caveat"] and "FIGYELEM" in d["caveat"]
    assert report_to_dict(ScoutingReport(team="home",
                                         team_name="A"))["caveat"] is None


def _hajra_opp():
    """Ellenfél-jelentés, amiben MINDEN hajrá-jel megszólal."""
    from handball.pipeline.scouting import ScoutingReport

    opp = ScoutingReport(team="away", team_name="Ellen")
    opp.lhf_fh_sum_m, opp.lhf_fh_n = 850.0, 100     # fal 8,5 → 6,5 m
    opp.lhf_sh_sum_m, opp.lhf_sh_n = 650.0, 100
    opp.rtf_fh_sum_s, opp.rtf_fh_n = 16.0, 4        # hazaérés 4 → 10 mp
    opp.rtf_sh_sum_s, opp.rtf_sh_n = 40.0, 4
    opp.wif_fh_wing, opp.wif_fh_n = 6, 8            # szél 75% → 12%
    opp.wif_sh_wing, opp.wif_sh_n = 1, 8
    opp.puf_fh_pivot, opp.puf_fh_n = 6, 8           # beálló 75% → 12%
    opp.puf_sh_pivot, opp.puf_sh_n = 1, 8
    opp.fpr_signals, opp.fpr_matches = 4, 1         # 4 jel egy meccsen
    return opp


def test_a_hajra_retegek_edzoi_kulcsai_tenyleg_megszolalnak():
    """A réteg + a felület megléte nem elég: a kulcsnak MEG IS kell
    szólalnia a megfelelő adatra.

    Egy elgépelt mezőnév vagy egy rossz irányú összehasonlítás néma
    kulcsot ad — semmi nem hasal el, a felhasználó pedig sosem tudja
    meg, hogy az elemzés létezik. (Az edzés-fókusz oldalán pontosan
    ez történt öt szabállyal.)
    """
    from handball.pipeline.scouting import _coach_keys

    _s, _w, keys = _coach_keys(_hajra_opp())
    vart = ("faluk a 2. félidőre visszahúzódik",
            "visszaállásuk a 2. félidőre lassul",
            "támadásuk a 2. félidőre beszűkül",
            "beállójuk a 2. félidőre elfogy",
            "fáradás-jel szólal meg náluk")
    nema = [v for v in vart if not any(v in k for k in keys)]
    assert not nema, f"néma edzői kulcsok: {nema}"


def test_a_hajra_retegek_meccsterv_szabalyai_tenyleg_megszolalnak():
    """A párosított szabályok ugyanígy: a saját oldal erősségével
    együtt meg kell szólalniuk."""
    from handball.pipeline.scouting import ScoutingReport, matchup_plan

    opp = _hajra_opp()
    own = ScoutingReport(team="home", team_name="Mi")
    own.sr_far_shots, own.sr_far_goals = 12, 5        # 450: távoli lövés
    own.fbc_breaks = 5                                # 451: kontra
    own.defense_main = "6-0"                          # 452: tömör fal
    own.clutch_matches = 2                            # 453: hajrá-erő
    own.clutch_goals_for, own.clutch_goals_against = 9, 4
    plan = matchup_plan(own, opp) or []
    vart = ("faluk a 2. félidőre visszahúzódik",
            "visszaállásuk a 2. félidőre lassul",
            "támadásuk a 2. félidőre beszűkül",
            "fáradás-jel szólal meg náluk")
    nema = [v for v in vart if not any(v in p for p in plan)]
    assert not nema, f"néma meccsterv-szabályok: {nema}"

    # A beálló-szabály KILÉPŐS falat kíván (a tömör 6-0 a szélső-szabályé):
    # a kettő szándékosan más falformára szól.
    own.defense_main = "3-2-1"
    plan2 = matchup_plan(own, opp) or []
    assert any("beállójuk a 2. félidőre elfogy" in p for p in plan2)


def test_a_felderites_probaja():
    """scouting_backtest: a csapat korábbi meccseinek egyesített kulcsai
    visszaköszönnek-e a meccs saját jelentésében — a liga általános
    kulcsaihoz mérve; a kulcsok számok nélkül egyeznek; kevés meccsnél
    None; a csapat-szűrő."""
    from handball.pipeline.scouting import (SC_ITELET_PP, SC_MIN_KORABBI,
                                            SC_PROBA_MIN, ScoutingReport,
                                            _kulcs_alak, coach_key_set,
                                            combine_reports,
                                            scouting_backtest)

    assert _kulcs_alak("Gyors indítás (14%) — 2,5 s") == \
        "Gyors indítás (#%) — # s"
    # "A": mély 6-0, gyors indítás, erős befejezés; "B": 5-1, lassú, gyenge
    # befejezés, sok eladott labda — a két profil kulcsai nem fedik egymást.
    a = ScoutingReport(team="home", team_name="A", defense_main="6-0",
                       defense_distribution={"6-0": 80.0, "5-1": 20.0},
                       fast_break_pct=20.0, shots=10, goals=6, xg=4.0,
                       xg_diff=2.0, turnovers=2)
    b = ScoutingReport(team="away", team_name="B", defense_main="5-1",
                       defense_distribution={"5-1": 90.0, "6-0": 10.0},
                       fast_break_pct=2.0, shots=10, goals=2, xg=4.0,
                       xg_diff=-2.0, turnovers=12)
    ka, kb = coach_key_set(a), coach_key_set(b)
    assert "Mély #-# faluk ellen: # m-es lövés és beúszó, csald ki a védőt." \
        in ka and "#-#-ük ellen: az előretolt védő kicselezése, gyors " \
        "lefordulás." in kb
    kozos = len(ka & kb)        # a két profil közös kulcsai (kevés)
    assert kozos < min(len(ka), len(kb)) / 2
    ms = [{"match_id": f"m{i}", "home": "A", "away": "B",
           "reports": {"home": a, "away": b}} for i in range(8)]
    p = scouting_backtest(ms)
    # Az első SC_MIN_KORABBI meccs a tanuláshoz: 6 meccs × 2 csapat; a
    # stabil profil kulcsai mind visszaköszönnek, a "ligáé" (a másik
    # csapat) csak a közös kulcsokban.
    assert (p["meccsek"], p["itelet"]) == (12, "atviheto")
    # Az egyesített jelentés kulcsai nem pont az egy meccsé (az összegzett
    # számok más küszöböket érnek el) — a többségük így is visszaköszön,
    # a ligáé csak a közös kulcsokban.
    assert 80.0 <= p["talalat_pct"] <= 100.0
    assert p["talalat_pct"] - p["liga_pct"] >= p["kulonbseg_pp"] - 0.1 >= \
        SC_ITELET_PP
    e0 = p["sorok"][0]
    assert e0["match_id"] == f"m{SC_MIN_KORABBI}" and e0["team"] == "A"
    ketto = coach_key_set(combine_reports([a, a]))
    assert (e0["kulcsok"], e0["talalt"]) == (len(ketto), len(ketto & ka))
    assert e0["liga_talalt"] == len(coach_key_set(combine_reports([b, b])) & ka)
    assert p["verdict"].startswith(
        f"a felderítés kulcsai 12 meccsen átlag {p['talalat_pct']:.0f}%-ban "
        "visszaköszöntek a következő meccsen (a liga általános kulcsai: ")
    assert p["verdict"].endswith("a felderítésre lehet építeni: a szokásaik "
                                 "meccsről meccsre megmaradnak")
    assert scouting_backtest(ms, "B")["meccsek"] == 6
    assert scouting_backtest(ms[:SC_MIN_KORABBI + SC_PROBA_MIN // 2]) is None
    # Ha a csapat meccsről meccsre más profilt mutat (az "A" felváltva a
    # két profil), a kulcsai nem stabilabbak a ligánál: "nem".
    v = [{"match_id": f"v{i}", "home": "A", "away": "B",
          "reports": {"home": a if i % 2 else ScoutingReport(
              **{**b.__dict__, "team": "home", "team_name": "A"}),
                      "away": b}} for i in range(8)]
    q = scouting_backtest(v, "A")
    assert q is not None and q["itelet"] == "nem"
    assert q["verdict"].endswith(
        "a meccstervet a friss meccsekre és a közös mintákra súlyozd")


def test_a_felderites_hatokoron_belul_csapatonkent_egyszer_epul():
    """A felderítő jelentés memoizált a primitive_cache hatókörben: az
    edzői összefoglaló (taktikai kulcsok), az angol kártyák és a csomag
    felderítés-rétege ugyanazt kéri — a sebesség-profil szerint ez volt
    a csomag idejének ötöde. Minden hívó SAJÁT másolatot kap, a
    módosítás nem szivárog vissza; az alapértelmezett beállítás és a
    None ugyanazt a bejegyzést olvassa; hatókör nélkül a nyers
    felépítés fut."""
    from dataclasses import asdict

    from handball.pipeline.primitive_cache import primitive_cache
    from handball.pipeline.scouting import _scout_team_cached, scout_team
    from handball.pipeline.tactics import TacticsConfig

    assert hasattr(_scout_team_cached, "uncached")
    m = _shots_match()
    nyers = asdict(_scout_team_cached.uncached(m, Team.HOME))
    with primitive_cache(m):
        elso = scout_team(m, Team.HOME)
        masodik = scout_team(m, Team.HOME)
        alap = scout_team(m, Team.HOME, TacticsConfig())
        assert asdict(elso) == asdict(masodik) == asdict(alap) == nyers
        assert elso is not masodik and masodik is not alap   # védő-másolat
        elso.matches = 99
        assert scout_team(m, Team.HOME).matches == 1
        # A másik csapat külön bejegyzés — nem keveredik.
        assert scout_team(m, Team.AWAY).team != elso.team


def test_rep_earn_count_osszeadja_a_kiharcolt_kiallitasokat():
    """A riport kiharcolt kiállításainak összege a susp_earners listából;
    üres (vagy None) lista → 0, hiányzó "earned" mező → 0."""
    from handball.pipeline.scouting import rep_earn_count

    rep = ScoutingReport(team="home", team_name="Mi",
                         susp_earners=[{"player_id": 7, "earned": 2},
                                       {"player_id": 9, "earned": 1},
                                       {"player_id": 4}])
    assert rep_earn_count(rep) == 3
    assert rep_earn_count(ScoutingReport(team="home", team_name="Mi")) == 0
    ures = ScoutingReport(team="home", team_name="Mi")
    ures.susp_earners = None
    assert rep_earn_count(ures) == 0


def test_rep_earn_count_a_kettos_hatrany_szabalyt_kapuzza():
    """A 248) páros szabály: az ő végzetes kettős hátrányuk × a ti
    kiharcolt kiállításaitok — 2 kiharcolásnál szól, 1-nél hallgat."""
    from handball.pipeline.scouting import matchup_plan

    opp = ScoutingReport(team="away", team_name="Ok", dsh_conceded=3)
    sok = ScoutingReport(team="home", team_name="Mi",
                         susp_earners=[{"player_id": 7, "earned": 1},
                                       {"player_id": 9, "earned": 1}])
    keves = ScoutingReport(team="home", team_name="Mi",
                           susp_earners=[{"player_id": 7, "earned": 1}])
    jel = "A kettős emberhátrány végzetes nekik"
    assert any(jel in p_ for p_ in matchup_plan(sok, opp))
    assert not any(jel in p_ for p_ in matchup_plan(keves, opp))


# ---- 241) Szünet utáni oldal-váltás × a ti falat váltó védekezésetek ---------

def _oldalvalto_ellenfel(fh_frames=120, sh_frames=120):
    """Az ellenfél az első félidőben balra (50%), a másodikban jobbra
    (58%) súlypontoz — kocka-darabszámokkal, ahogy a riport tárolja."""
    return ScoutingReport(
        team="away", team_name="Ok",
        sds_fh_frames=fh_frames, sds_sh_frames=sh_frames,
        sds_fh_counts={"bal": 60, "közép": 30, "jobb": 30},
        sds_sh_counts={"bal": 20, "közép": 30, "jobb": 70})


def _falvalto_sajat(fh=("6-0", 5, 6), sh=("5-1", 6, 8)):
    """A saját csapat félidőnként stabil, kimondható formát játszik:
    (forma, ennyi támadás ellen, az összesből)."""
    return ScoutingReport(
        team="home", team_name="Mi",
        dfs_fh_labels={fh[0]: fh[1]}, dfs_fh_attacks=fh[2],
        dfs_sh_labels={sh[0]: sh[1]}, dfs_sh_attacks=sh[2])


def test_meccsterv_241_oldalvaltas_ellen_a_tukrozest_keri():
    """Ha ők a szünet után oldalt váltanak (bal → jobb), és a ti falatok
    mindkét félidőben stabil formát játszik (≥60%, ≥5 támadás), a terv a
    szünetbeli tükrözést kéri — a két oldal nevével."""
    from handball.pipeline.scouting import matchup_plan

    plan = matchup_plan(_falvalto_sajat(), _oldalvalto_ellenfel())
    sor = [p_ for p_ in plan if "A szünet után oldalt váltanak" in p_]
    assert len(sor) == 1
    assert "(bal → jobb)" in sor[0]
    assert "készítsétek elő a tükrözést" in sor[0]


def test_meccsterv_241_keves_mintanal_vagy_valtas_nelkul_hallgat():
    """Hallgat, ha (a) az ellenfélnek félidőnként 100 kockánál kevesebb a
    mintája, (b) nem váltanak oldalt, (c) nincs uralkodó oldaluk (40%
    alatt), (d) a saját falról kevés a minta (5 támadás alatt) vagy
    (e) nem stabil (60% alatt), vagy (f) nincs is forma-adat."""
    from handball.pipeline.scouting import matchup_plan

    jel = "A szünet után oldalt váltanak"

    def szol(own, opp):
        return any(jel in p_ for p_ in matchup_plan(own, opp))

    assert szol(_falvalto_sajat(), _oldalvalto_ellenfel())
    # (a) kevés ellenfél-kocka az egyik félidőben
    assert not szol(_falvalto_sajat(), _oldalvalto_ellenfel(fh_frames=99))
    assert not szol(_falvalto_sajat(), _oldalvalto_ellenfel(sh_frames=99))
    # (b) mindkét félidőben ugyanaz az oldal
    ugyanaz = _oldalvalto_ellenfel()
    ugyanaz.sds_sh_counts = {"bal": 70, "közép": 30, "jobb": 20}
    assert not szol(_falvalto_sajat(), ugyanaz)
    # (c) nincs uralkodó oldal (a legnagyobb is csak 39%)
    szort = _oldalvalto_ellenfel()
    szort.sds_fh_counts = {"bal": 47, "közép": 37, "jobb": 36}
    assert not szol(_falvalto_sajat(), szort)
    # (d) a saját falról kevés a minta az első félidőben
    assert not szol(_falvalto_sajat(fh=("6-0", 4, 4)),
                    _oldalvalto_ellenfel())
    # (e) a saját fal nem stabil a második félidőben (50%)
    assert not szol(_falvalto_sajat(sh=("5-1", 4, 8)),
                    _oldalvalto_ellenfel())
    # (f) nincs forma-adat / üres riportok
    assert not szol(ScoutingReport(team="home", team_name="Mi"),
                    _oldalvalto_ellenfel())
    assert not szol(_falvalto_sajat(),
                    ScoutingReport(team="away", team_name="Ok"))


# ---- A meccsek közti összefésülők (_merge_*) táblázatosan -------------------
#
# A felderítés darabszám-alapú sorai meccsek közt PONTOSAN összeadódnak
# (arány sosem tárolódik). Minden összefésülőre ugyanazt nézzük: két
# meccs sorai kulcsonként összeadódnak, a mezszám megmarad, az üres
# bemenet üres eredményt ad — és a VALÓDI felderítés sorain is lefutnak
# (a mezőnevek tényleg azok, amiket az összefésülő olvas).

# (függvény, riport-mező, kulcs-mezők, összegzett mezők, rendező mező)
_JATEKOS_SOROK = [
    ("_merge_seven_earners", "seven_earners", ("player_id",), ("earned",), "earned"),
    ("_merge_cbc_players", "cbc_players", ("player_id",), ("trailing", "rest"), "trailing"),
    ("_merge_fdd_players", "fdd_players", ("player_id",), ("fh", "sh"), "fh"),
    ("_merge_fdr_players", "fdr_players", ("player_id",), ("fh", "sh"), "fh"),
    ("_merge_susp_earners", "susp_earners", ("player_id",), ("earned",), "earned"),
    ("_merge_susp_players", "susp_players", ("player_id",), ("suspensions",), "suspensions"),
    ("_merge_markers", "markers", ("player_id",), ("frames", "dist_sum"), "frames"),
    ("_merge_ball_winners", "ball_winners", ("player_id",), ("steals",), "steals"),
    ("_merge_turnover_players", "turnover_players", ("player_id",), ("losses",), "losses"),
    ("_merge_plus_minus", "player_plus_minus", ("player_id",), ("frames", "for", "against"), None),
    ("_merge_clutch_losers", "clutch_losers", ("player_id",), ("turnovers",), "turnovers"),
    ("_merge_pp_shooters", "pp_shooters", ("player_id",), ("shots", "goals"), "shots"),
    ("_merge_breakthrough_players", "breakthrough_players", ("player_id",), ("entries", "goals"), "entries"),
    ("_merge_covered_shooters", "covered_shooters", ("player_id",), ("shots", "covered"), "covered"),
    ("_merge_pdq_players", "pdq_players", ("player_id",), ("press", "press_best"), "press"),
    ("_merge_pressure_players", "pressure_players", ("player_id",), ("press_events", "press_to"), "press_to"),
    ("_merge_high_stealers", "high_stealers", ("player_id",), ("steals", "high"), "high"),
    ("_merge_wasteful_shooters", "wasteful_shooters", ("player_id",), ("shots", "off_target"), "off_target"),
    ("_merge_clutch_players", "clutch_players", ("player_id",), ("frames",), "frames"),
    ("_merge_rebounders", "rebounders", ("player_id",), ("rebounds",), "rebounds"),
    ("_merge_pivot_feeders", "pivot_feeders", ("player_id",), ("feeds",), "feeds"),
    ("_merge_seven_conceders", "seven_conceders", ("player_id",), ("conceded",), "conceded"),
    ("_merge_starters", "starters", ("player_id",), ("starts",), "starts"),
    ("_merge_hold_players", "hold_players", ("player_id",), ("holds", "frames"), None),
    ("_merge_carry_players", "carry_players", ("player_id",), ("holds", "meters"), None),
    ("_merge_targeted_defenders", "targeted_defenders", ("player_id",), ("shots", "goals"), "shots"),
    ("_merge_costly_turnovers", "costly_turnover_players", ("player_id",), ("turnovers", "punished"), "punished"),
    ("_merge_clutch_scorers", "clutch_scorers", ("player_id",), ("goals",), "goals"),
    ("_merge_scorer_goals", "scorer_goals", ("player_id",), ("goals",), "goals"),
    ("_merge_fb_finishers", "fb_finishers", ("player_id",), ("goals",), "goals"),
    ("_merge_risky_passers", "risky_passers", ("player_id",), ("tries", "turnovers"), "turnovers"),
    ("_merge_screen_setters", "screen_setters", ("player_id",), ("screens",), "screens"),
    ("_merge_outlet_targets", "gk_outlet_targets", ("player_id",), ("n",), "n"),
    ("_merge_blockers", "blockers", ("player_id",), ("blocks",), "blocks"),
    ("_merge_shooter_overperf", "shooter_overperf", ("player_id",), ("diff",), "diff"),
    ("_merge_bcf_players", "bcf_players", ("player_id",), ("chances", "goals"), "chances"),
    ("_merge_drb_players", "drb_players", ("player_id",), ("breaks",), "breaks"),
    ("_merge_cbh_players", "cbh_players", ("player_id",), ("frames",), "frames"),
    ("_merge_pivot_guards", "pvg_guards", ("player_id",), ("frames",), "frames"),
    ("_merge_phase_players", "phs_players", ("player_id",), ("frames", "def_frames"), "frames"),
    ("_merge_sprint_threats", "spt_players", ("player_id",), ("sprints", "sprint_m"), "sprints"),
    ("_merge_adv_players", "adv_players", ("player_id",), ("frames", "depth_sum_m"), "frames"),
    ("_merge_restart_targets", "rst_players", ("player_id",), ("takes",), "takes"),
    ("_merge_shooter_fades", "shooter_fades", ("player_id",), ("drop_sum_pct", "n"), None),
    ("_merge_shooter_placement", "shooter_placement", ("player_id",), ("goals", "bal", "közép", "jobb"), "goals"),
    ("_merge_screen_pairs", "scp_pairs", ("setter_id", "shooter_id"), ("shots",), "shots"),
    ("_merge_swap_pairs", "swp_pairs", ("out_id", "in_id"), ("count",), "count"),
    ("_merge_assist_pairs", "assist_pairs", ("from", "to"), ("goals",), "goals"),
    ("_merge_shooter_zones", "shooter_zones", ("player_id", "zone"), ("shots",), "shots"),
]

# A lebegőpontos (összeg-) mezők: fél egységekkel próbáljuk, hogy a
# kerekítés ne takarjon el semmit.
_TORT_MEZOK = {"dist_sum", "meters", "diff", "sprint_m", "depth_sum_m",
               "drop_sum_pct"}

# Három "játékos" (pár-kulcsnál három pár); az 1. csak az A meccsen, a
# 3. csak a B-n játszott, a 2. mindkettőn.
_KULCSOK = {1: (7, 8), 2: (9, 10), 3: (11, 12)}
_MEZEK = {1: 17, 2: 19, 3: 21}


def _proba_sor(kulcs_mezok, osszeg_mezok, ki, alap, mez):
    sor = {}
    for i, k in enumerate(kulcs_mezok):
        ertek = _KULCSOK[ki][i]
        sor[k] = f"zóna-{ertek}" if k == "zone" else ertek
    for j, m in enumerate(osszeg_mezok):
        sor[m] = (alap + j + 0.5) if m in _TORT_MEZOK else alap + j
    sor["jersey"] = mez
    return sor


def _ket_meccs(mezo, kulcs_mezok, osszeg_mezok):
    """A (csak 1. és 2. játékos) és B (2. és 3.) meccs riportja. A 2.
    játékos mezszáma az A meccsen még ismeretlen (None), a B-n 19."""
    a = ScoutingReport(team="home", team_name="Mi")
    b = ScoutingReport(team="home", team_name="Mi")
    setattr(a, mezo, [_proba_sor(kulcs_mezok, osszeg_mezok, 1, 3, 17),
                      _proba_sor(kulcs_mezok, osszeg_mezok, 2, 5, None)])
    setattr(b, mezo, [_proba_sor(kulcs_mezok, osszeg_mezok, 2, 2, 19),
                      _proba_sor(kulcs_mezok, osszeg_mezok, 3, 4, 21)])
    return a, b


def _kulcs_szerint(sorok, kulcs_mezok):
    return {tuple(s[k] for k in kulcs_mezok): s for s in sorok}


@pytest.mark.parametrize("fn_nev, mezo, kulcs_mezok, osszeg_mezok, rendezo",
                         _JATEKOS_SOROK, ids=[s[0] for s in _JATEKOS_SOROK])
def test_merge_jatekos_sorok_ket_meccs_pontosan_osszeadodik(
        fn_nev, mezo, kulcs_mezok, osszeg_mezok, rendezo):
    """Két meccs sorai kulcsonként összeadódnak: aki csak az egyiken
    játszott, a saját számait viszi; aki mindkettőn, az összeget — a
    mezszám (ahol a sor viszi) az első ISMERT érték."""
    from handball.pipeline import scouting

    assert mezo in {f.name for f in __import__("dataclasses").fields(
        ScoutingReport)}, f"nincs ilyen riport-mező: {mezo}"
    fn = getattr(scouting, fn_nev)
    a, b = _ket_meccs(mezo, kulcs_mezok, osszeg_mezok)
    ki = fn([a, b])
    sorok = _kulcs_szerint(ki, kulcs_mezok)

    def kulcs(i):
        return tuple(f"zóna-{v}" if k == "zone" else v
                     for k, v in zip(kulcs_mezok, _KULCSOK[i]))

    assert set(sorok) == {kulcs(1), kulcs(2), kulcs(3)}
    for j, m in enumerate(osszeg_mezok):
        fel = 0.5 if m in _TORT_MEZOK else 0
        assert sorok[kulcs(1)][m] == 3 + j + fel, (fn_nev, m)
        assert sorok[kulcs(2)][m] == (5 + j + fel) + (2 + j + fel), (fn_nev, m)
        assert sorok[kulcs(3)][m] == 4 + j + fel, (fn_nev, m)
    if "jersey" in next(iter(sorok.values())):
        assert [sorok[kulcs(i)]["jersey"] for i in (1, 2, 3)] == [17, 19, 21]
    if rendezo is not None:
        ertekek = [s[rendezo] for s in ki]
        assert ertekek == sorted(ertekek, reverse=True), (fn_nev, ertekek)
    # A meccsek sorrendje nem számít az összegben.
    forditva = _kulcs_szerint(fn([b, a]), kulcs_mezok)
    for k, s in sorok.items():
        assert {m: forditva[k][m] for m in osszeg_mezok} == \
            {m: s[m] for m in osszeg_mezok}


@pytest.mark.parametrize("fn_nev, mezo, kulcs_mezok, osszeg_mezok, rendezo",
                         _JATEKOS_SOROK, ids=[s[0] for s in _JATEKOS_SOROK])
def test_merge_jatekos_sorok_ures_bemenetre_ures(
        fn_nev, mezo, kulcs_mezok, osszeg_mezok, rendezo):
    """Riport nélkül, üres riporttal vagy hiányzó (None) mezővel az
    összefésülő üres listát ad — nem kivételt, nem kitalált nullás sort;
    egyetlen meccsből a saját sorai jönnek vissza."""
    from handball.pipeline import scouting

    fn = getattr(scouting, fn_nev)
    ures = ScoutingReport(team="home", team_name="Mi")
    assert fn([]) == []
    assert fn([ures]) == [] and fn([ures, ures]) == []
    hianyzik = ScoutingReport(team="home", team_name="Mi")
    setattr(hianyzik, mezo, None)
    assert fn([hianyzik]) == []
    a, _ = _ket_meccs(mezo, kulcs_mezok, osszeg_mezok)
    egy = _kulcs_szerint(fn([a, ures, hianyzik]), kulcs_mezok)
    assert len(egy) == 2
    for s in getattr(a, mezo):
        k = tuple(s[m] for m in kulcs_mezok)
        assert {m: egy[k][m] for m in osszeg_mezok} == \
            {m: s[m] for m in osszeg_mezok}


def _riport(**mezok):
    r = ScoutingReport(team="home", team_name="Mi")
    for k, v in mezok.items():
        assert hasattr(r, k), f"nincs ilyen riport-mező: {k}"
        setattr(r, k, v)
    return r


def test_merge_kulonleges_sorok_max_irany_es_arany_szerinti_rend():
    """Az összegtől eltérő összefésülők: a csúcs-sebesség a MAXIMUM (nem
    összeg), a hetes-dobó irányai irányonként adódnak össze, a páros
    mérlegnél a két játékos sorrendje nem számít, és az arány szerint
    rendezők az összegekből számolt aránnyal rendeznek (a nulla nevezőjű
    sor kimarad)."""
    from handball.pipeline import scouting

    ero = scouting._merge_shooter_power([
        _riport(shooter_power=[{"player_id": 7, "shots": 2, "sum_kmh": 160.5,
                                "max_kmh": 84.0}]),
        _riport(shooter_power=[{"player_id": 7, "shots": 3, "sum_kmh": 270.0,
                                "max_kmh": 97.5},
                               {"player_id": 9, "shots": 1, "sum_kmh": 70.0,
                                "max_kmh": 70.0}])])
    assert ero == [
        {"player_id": 7, "shots": 5, "sum_kmh": 430.5, "max_kmh": 97.5},
        {"player_id": 9, "shots": 1, "sum_kmh": 70.0, "max_kmh": 70.0}]

    hetes = scouting._merge_seven_takers([
        _riport(seven_takers=[{"player_id": 7, "attempts": 2, "goals": 1,
                               "dirs": {"bal": 2}}]),
        _riport(seven_takers=[{"player_id": 7, "attempts": 3, "goals": 3,
                               "dirs": {"bal": 1, "jobb": 2}},
                              {"player_id": 9, "attempts": 1, "goals": 0}])])
    assert hetes == [
        {"player_id": 7, "attempts": 5, "goals": 4,
         "dirs": {"bal": 3, "jobb": 2}},
        {"player_id": 9, "attempts": 1, "goals": 0, "dirs": {}}]

    paros = scouting._merge_pair_plus_minus([
        _riport(pair_plus_minus=[{"players": [9, 7], "frames": 100,
                                  "for": 3, "against": 1}]),
        _riport(pair_plus_minus=[{"players": [7, 9], "frames": 50,
                                  "for": 1, "against": 2},
                                 {"players": [7, 11], "frames": 80,
                                  "for": 4, "against": 0}])])
    assert paros == [
        {"players": [7, 11], "frames": 80, "for": 4, "against": 0},
        {"players": [7, 9], "frames": 150, "for": 4, "against": 3}]

    # Átlagtávolság szerint csökkenő; a lövés nélküli sor kimarad.
    tav = scouting._merge_shooter_ranges([
        _riport(shooter_ranges=[
            {"player_id": 7, "jersey": 17, "shots": 2, "sum_dist_m": 14.0},
            {"player_id": 9, "jersey": 19, "shots": 0, "sum_dist_m": 0.0}]),
        _riport(shooter_ranges=[
            {"player_id": 7, "jersey": 17, "shots": 2, "sum_dist_m": 18.0},
            {"player_id": 11, "jersey": 21, "shots": 1, "sum_dist_m": 10.5}])])
    assert tav == [
        {"player_id": 11, "jersey": 21, "shots": 1, "sum_dist_m": 10.5},
        {"player_id": 7, "jersey": 17, "shots": 4, "sum_dist_m": 32.0}]

    # A saját térfélen töltött arány szerint NÖVEKVŐ (a leglassabban
    # visszarendeződő elöl); kocka nélkül nincs sor.
    vissza = scouting._merge_recovery_players([
        _riport(recovery_players=[
            {"player_id": 7, "jersey": 17, "frames": 10, "home_frames": 8},
            {"player_id": 9, "jersey": 19, "frames": 10, "home_frames": 2}]),
        _riport(recovery_players=[
            {"player_id": 9, "jersey": 19, "frames": 10, "home_frames": 4},
            {"player_id": 11, "jersey": 21, "frames": 0, "home_frames": 0}])])
    assert vissza == [
        {"player_id": 9, "jersey": 19, "frames": 20, "home_frames": 6},
        {"player_id": 7, "jersey": 17, "frames": 10, "home_frames": 8}]

    # Átlagsebesség szerint NÖVEKVŐ (a legállóbb támadó elöl).
    allo = scouting._merge_static_attackers([
        _riport(static_attackers=[
            {"player_id": 7, "jersey": 17, "seconds": 10.0, "dist_m": 30.0},
            {"player_id": 9, "jersey": 19, "seconds": 10.0, "dist_m": 5.0}]),
        _riport(static_attackers=[
            {"player_id": 9, "jersey": 19, "seconds": 10.5, "dist_m": 6.5},
            {"player_id": 11, "jersey": 21, "seconds": 0.0, "dist_m": 0.0}])])
    assert allo == [
        {"player_id": 9, "jersey": 19, "seconds": 20.5, "dist_m": 11.5},
        {"player_id": 7, "jersey": 17, "seconds": 10.0, "dist_m": 30.0}]
    for fn in (scouting._merge_shooter_power, scouting._merge_seven_takers,
               scouting._merge_pair_plus_minus, scouting._merge_shooter_ranges,
               scouting._merge_recovery_players,
               scouting._merge_static_attackers):
        assert fn([]) == [] and fn([_riport()]) == []


def test_merge_mezonevvel_hivott_valtozatok():
    """A mezőnévvel hívott közös összefésülők (emberhátrány-lövők, kezdő
    és hajrá-emberek, irány- és darabszám-szótárak) ugyanúgy összeadnak;
    a darabszám-összegző a nem szám értéket átugorja."""
    from handball.pipeline import scouting

    a = _riport(sh_shooters=[{"player_id": 7, "jersey": None, "shots": 3,
                              "goals": 1}],
                pp_shooters=[{"player_id": 9, "jersey": 19, "shots": 9,
                              "goals": 9}])
    b = _riport(sh_shooters=[{"player_id": 7, "jersey": 17, "shots": 2,
                              "goals": 2},
                             {"player_id": 11, "jersey": 21, "shots": 4,
                              "goals": 0}])
    assert scouting._merge_pp_shooters_rows([a, b], "sh_shooters") == [
        {"player_id": 7, "jersey": 17, "shots": 5, "goals": 3},
        {"player_id": 11, "jersey": 21, "shots": 4, "goals": 0}]
    assert scouting._merge_pp_shooters_rows([a, b], "pp_shooters") == [
        {"player_id": 9, "jersey": 19, "shots": 9, "goals": 9}]
    assert scouting._merge_pp_shooters_rows([a, b], "nincs_ilyen_mezo") == []

    c = _riport(clutch_players=[{"player_id": 7, "jersey": 17,
                                 "frames": 100}])
    d = _riport(clutch_players=[{"player_id": 7, "jersey": 17, "frames": 50},
                                {"player_id": 9, "jersey": 19,
                                 "frames": 300}])
    assert scouting._merge_clutch_players_rows([c, d], "clutch_players") == [
        {"player_id": 9, "jersey": 19, "frames": 300},
        {"player_id": 7, "jersey": 17, "frames": 150}]
    assert scouting._merge_clutch_players_rows([c, d], "nincs_ilyen") == []

    e = _riport(sh_shape={"5-0": 100, "4-1": 20})
    f = _riport(sh_shape={"4-1": 200, "3-2": 7})
    assert scouting._merge_dir_counts([e, f], "sh_shape") == {
        "5-0": 100, "4-1": 220, "3-2": 7}
    assert scouting._merge_dir_counts([e, f], "nincs_ilyen") == {}
    assert scouting._merge_counts([e, f], "sh_shape") == {
        "5-0": 100, "4-1": 220, "3-2": 7}
    vegyes = _riport(sh_shape={"5-0": "7", "4-1": None, "3-2": "sok"})
    assert scouting._merge_counts([e, vegyes], "sh_shape") == {
        "5-0": 107, "4-1": 20}
    assert scouting._merge_counts([], "sh_shape") == {}


# (függvény, riport-mező, összegzett al-mezők vagy None = sima darabszám,
#  rendezett-e csökkenőre)
_SZOTAR_OSSZEFESULOK = [
    ("_merge_break_lanes", "break_lanes", ("entries", "goals"), True),
    ("_merge_pass_buckets", "pass_buckets", ("attacks", "goals"), False),
    ("_merge_attack_origins", "attack_origins", ("attacks", "goals"), False),
    ("_merge_gk_role_saves", "gk_role_saves", ("faced", "saves"), True),
    ("_merge_conceded_types", "conceded_types", None, True),
    ("_merge_sh_shape", "sh_shape", None, True),
    ("_merge_attack_outcomes", "attack_outcomes", None, True),
    ("_merge_conceded_roles", "conceded_roles", None, True),
    ("_merge_role_goals", "role_goals", None, True),
    ("_merge_assist_zones", "assist_zones", None, True),
    ("_merge_fsw_labels", "fsw_labels", None, True),
    ("_merge_earner_roles", "seven_earner_roles", None, True),
]


@pytest.mark.parametrize("fn_nev, mezo, al_mezok, rendezett",
                         _SZOTAR_OSSZEFESULOK,
                         ids=[s[0] for s in _SZOTAR_OSSZEFESULOK])
def test_merge_szotarak_kulcsonkent_osszeadodnak(fn_nev, mezo, al_mezok,
                                                 rendezett):
    """A kulcsonkénti (sáv, típus, poszt, forma …) darabszámok két
    meccsből kulcsonként összeadódnak; ahol a kimenet rendezett, a
    legnagyobb elöl; üres / hiányzó mezőre üres szótár."""
    from handball.pipeline import scouting

    fn = getattr(scouting, fn_nev)

    def ertek(n):
        if al_mezok is None:
            return n
        return {m: n + j for j, m in enumerate(al_mezok)}

    a = _riport(**{mezo: {"bal": ertek(3), "közép": ertek(5)}})
    b = _riport(**{mezo: {"közép": ertek(2), "jobb": ertek(9)}})
    ki = fn([a, b])
    if al_mezok is None:
        assert ki == {"bal": 3, "közép": 7, "jobb": 9}
        if rendezett:
            assert list(ki) == ["jobb", "közép", "bal"]
    else:
        assert ki == {
            "bal": {m: 3 + j for j, m in enumerate(al_mezok)},
            "közép": {m: 7 + 2 * j for j, m in enumerate(al_mezok)},
            "jobb": {m: 9 + j for j, m in enumerate(al_mezok)}}
        if rendezett:
            assert list(ki) == ["jobb", "közép", "bal"]
    assert fn([]) == {} and fn([_riport()]) == {}
    assert fn([_riport(**{mezo: None})]) == {}
    assert fn([b, a]) == ki


def test_merge_role_counts_es_count_dicts_szotar_listabol():
    """A szótár-listát összeadó két segéd: a poszt-darabszámok csökkenő
    sorrendben, a sima darabszám-szótár sorrend nélkül; a None elem
    kimarad, üres listára üres szótár."""
    from handball.pipeline.scouting import (_merge_count_dicts,
                                            _merge_role_counts)

    dicts = [{"szélső": 2, "beálló": 5}, None, {"szélső": 4, "irányító": 1}]
    assert _merge_role_counts(dicts) == {"szélső": 6, "beálló": 5,
                                         "irányító": 1}
    assert list(_merge_role_counts(dicts)) == ["szélső", "beálló",
                                               "irányító"]
    assert _merge_count_dicts(dicts) == {"szélső": 6, "beálló": 5,
                                         "irányító": 1}
    assert _merge_role_counts([]) == {} and _merge_count_dicts([]) == {}
    assert _merge_count_dicts([None, {}]) == {}


def test_merge_osszefesulok_a_valodi_felderites_sorain_is_futnak():
    """ŐR a néma mezőnév ellen: minden összefésülő a VALÓDI felderítés
    (scout_team) sorain fut — a sor-kulcsok tényleg azok, amiket olvas —,
    és egy meccset önmagával összefésülve ugyanannyi sort ad, mint
    egyből (a kulcsok nem sokszorozódnak)."""
    from handball.pipeline import scouting
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=120, fps=25.0, seed=5,
                              shots_per_min=8)
    rep = scout_team(m, Team.HOME)
    nem_ures = 0
    for (fn_nev, mezo, _k, _o, _r) in _JATEKOS_SOROK:
        fn = getattr(scouting, fn_nev)
        egy, ketto = fn([rep]), fn([rep, rep])
        assert len(egy) == len(ketto), fn_nev
        assert len(egy) <= len(getattr(rep, mezo) or []), fn_nev
        nem_ures += bool(egy)
    for (fn_nev, mezo, _a, _r) in _SZOTAR_OSSZEFESULOK:
        fn = getattr(scouting, fn_nev)
        assert set(fn([rep])) == set(getattr(rep, mezo) or {}), fn_nev
        assert set(fn([rep, rep])) == set(fn([rep])), fn_nev
        nem_ures += bool(fn([rep]))
    for fn in (scouting._merge_shooter_power, scouting._merge_seven_takers,
               scouting._merge_pair_plus_minus, scouting._merge_shooter_ranges,
               scouting._merge_recovery_players,
               scouting._merge_static_attackers):
        assert len(fn([rep, rep])) == len(fn([rep])), fn.__name__
    # A próba-meccs elég gazdag ahhoz, hogy a teszt ne üres sorokon fusson.
    assert nem_ures >= 15, nem_ures
    # Az összevont riport a darabszámokat tényleg megduplázza.
    ossz = combine_reports([rep, rep])
    assert ossz.matches == 2
    egyszer = {s["player_id"]: s["goals"] for s in rep.scorer_goals}
    assert egyszer, "a próba-meccsen nincs gólszerző"
    assert {s["player_id"]: s["goals"] for s in ossz.scorer_goals} == \
        {pid: 2 * g for pid, g in egyszer.items()}


# ---- További belső segédek közvetlenül ----------------------------------------

from handball.pipeline.tactics import TacticsConfig  # noqa: E402

def test_team_of_track_a_leggyakrabban_latott_csapat():
    """Egy track csapata a leggyakrabban látott címkéje — egy-két
    kockányi téves szín-besorolás (villanás) nem viszi át a játékost a
    másik csapatba; üres meccsen üres szótár."""
    from handball.pipeline.scouting import _team_of_track

    frames = []
    for t in range(10):
        csapat = Team.AWAY if t in (3, 7) else Team.HOME      # két villanás
        frames.append(Frame(t=t, players=[_pl(1, csapat, 20.0, 10.0),
                                          _pl(11, Team.AWAY, 25.0, 10.0)],
                            ball=None))
    assert _team_of_track(Match(_meta(), frames)) == {1: Team.HOME,
                                                      11: Team.AWAY}
    assert _team_of_track(Match(_meta(), [])) == {}


def _labdas_kockak(xs, team=Team.HOME):
    """A csapat labdás kockái a megadott labda-x sorozattal."""
    tid = 1 if team == Team.HOME else 11
    return [Frame(t=i, players=[_pl(tid, team, x, 10.0)],
                  ball=Ball(x=x, y=10.0, confidence=1.0))
            for i, x in enumerate(xs)]


def test_fast_break_pct_a_tamado_iranyu_gyors_labda_aranya():
    """A labdás kockák közül azok aránya, ahol a labda legalább 6 m/s-mal
    halad a TÁMADOTT kapu felé: a hazainál a +x irány számít, a
    visszafelé (saját kapu felé) repülő labda nem gyors indítás."""
    from handball.pipeline.scouting import _fast_break_pct

    cfg = TacticsConfig()
    # 10 kocka állás (x=10), aztán 10 kocka 0,4 m/kocka = 10 m/s előre.
    xs = [10.0] * 10 + [10.0 + 0.4 * i for i in range(1, 11)]
    elore = Match(_meta(), _labdas_kockak(xs))
    assert _fast_break_pct(elore, Team.HOME, cfg) == 50.0
    # Ugyanez visszafelé: a hazainak nem gyors indítás.
    hatra = Match(_meta(), _labdas_kockak(list(reversed(xs))))
    assert _fast_break_pct(hatra, Team.HOME, cfg) == 0.0
    # A vendég a x=0 kapura támad: neki a csökkenő x a gyors indítás.
    vendeg = Match(_meta(), _labdas_kockak(list(reversed(xs)), Team.AWAY))
    assert _fast_break_pct(vendeg, Team.AWAY, cfg) == 50.0
    # Lassú (2,5 m/s) előrejátszás nem gyors indítás.
    lassu = Match(_meta(), _labdas_kockak([10.0 + 0.1 * i
                                           for i in range(20)]))
    assert _fast_break_pct(lassu, Team.HOME, cfg) == 0.0


def test_fast_break_pct_labda_nelkul_nulla():
    """Ha a csapatnak nincs labdás kockája (üres meccs, vagy végig az
    ellenfélnél a labda), az arány 0,0 — nem osztás nullával."""
    from handball.pipeline.scouting import _fast_break_pct

    cfg = TacticsConfig()
    assert _fast_break_pct(Match(_meta(), []), Team.HOME, cfg) == 0.0
    csak_vendeg = Match(_meta(), _labdas_kockak([30.0] * 10, Team.AWAY))
    assert _fast_break_pct(csak_vendeg, Team.HOME, cfg) == 0.0


def test_defense_distribution_forma_megoszlas_amikor_vedekezik():
    """A forma-megoszlás (%) csak azokból a kockákból jön, amikor a
    csapat VÉDEKEZIK (az ellenfél szervezetten támad): 30 kocka 6-0 és
    10 kocka 5-1 → 75% / 25%, a gyakoribb elöl."""
    from handball.pipeline.scouting import _defense_distribution

    def kocka(t, fal):
        players = [_pl(1, Team.HOME, 28.0, 10.0)]
        players += [_pl(20 + j, Team.AWAY, x, y)
                    for j, (x, y) in enumerate(fal)]
        return Frame(t=t, players=players,
                     ball=Ball(x=28.0, y=10.0, confidence=1.0))

    hat_null = [(35.0, float(y)) for y in (2, 6, 8, 12, 14, 18)]
    ot_egy = [(35.0, float(y)) for y in (2, 6, 10, 14, 18)] + [(30.5, 10.0)]
    frames = [kocka(t, hat_null) for t in range(30)]
    frames += [kocka(30 + t, ot_egy) for t in range(10)]
    m = Match(_meta(), frames)
    megoszlas = _defense_distribution(m, Team.AWAY, TacticsConfig())
    assert megoszlas == {"6-0": 75.0, "5-1": 25.0}
    assert list(megoszlas) == ["6-0", "5-1"]
    # A TÁMADÓ csapat ezen a meccsen egyszer sem védekezett → üres.
    assert _defense_distribution(m, Team.HOME, TacticsConfig()) == {}
    assert _defense_distribution(Match(_meta(), []), Team.AWAY,
                                 TacticsConfig()) == {}


def test_shot_zones_az_elengedes_helyebol_zonankent():
    """A lövések zónánként (lövés + gól), a leggyakoribb zóna elöl; a
    zóna az ELENGEDÉS helyéből jön, nem a kapu előtti kockából; a másik
    csapat lövései nem keverednek bele."""
    from handball.pipeline.scouting import _shot_zones

    frames, t = [], 0

    def loves(y_elenged, gol):
        nonlocal t
        for _ in range(8):                       # a lövő tartja a labdát
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 29.0,
                                                  y_elenged)],
                                ball=Ball(x=29.0, y=y_elenged,
                                          confidence=1.0)))
            t += 1
        cel_y = 10.0 if gol else 5.0
        for i in range(1, 12):                   # a labda a kapura repül
            a = i / 11.0
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 29.0,
                                                  y_elenged)],
                                ball=Ball(x=29.0 + 11.0 * a,
                                          y=y_elenged + (cel_y - y_elenged) * a,
                                          confidence=1.0)))
            t += 1
        for _ in range(20):                      # szünet a lövések közt
            frames.append(Frame(t=t, players=[], ball=Ball(
                x=20.0, y=10.0, confidence=1.0)))
            t += 1

    loves(10.0, gol=True)
    loves(10.0, gol=False)
    loves(3.0, gol=True)
    m = Match(_meta(), frames)
    zonak = _shot_zones(m, Team.HOME, TacticsConfig())
    assert zonak == {"átlövés közép": {"shots": 2, "goals": 1},
                     "átlövés bal": {"shots": 1, "goals": 1}}
    assert list(zonak) == ["átlövés közép", "átlövés bal"]
    assert _shot_zones(m, Team.AWAY, TacticsConfig()) == {}
    assert _shot_zones(Match(_meta(), []), Team.HOME, TacticsConfig()) == {}


def test_top_shooter_habit_a_legkoncentraltabb_fo_lovo():
    """A fő lövő "szokása": akinek 4+ lövéséből legalább 60% egy zónából
    jön — több ilyen közül az, akinek abból a zónából a legtöbb lövése
    van; (játékos, zóna, lövés a zónából, összes lövés)."""
    from handball.pipeline.scouting import _top_shooter_habit

    rep = ScoutingReport(team="home", team_name="Mi", shooter_zones=[
        {"player_id": 7, "zone": "átlövés bal", "shots": 4},
        {"player_id": 7, "zone": "beálló (6 m)", "shots": 2},     # 4/6 = 67%
        {"player_id": 9, "zone": "jobbszél", "shots": 5},
        {"player_id": 9, "zone": "átlövés közép", "shots": 1},    # 5/6 = 83%
        {"player_id": 11, "zone": "balszél", "shots": 3},         # csak 3
    ])
    assert _top_shooter_habit(rep) == (9, "jobbszél", 5, 6)
    # Ugyanaz a zóna két sorban (két meccs) összeadódik.
    ket_sor = ScoutingReport(team="home", team_name="Mi", shooter_zones=[
        {"player_id": 7, "zone": "átlövés bal", "shots": 2},
        {"player_id": 7, "zone": "átlövés bal", "shots": 2}])
    assert _top_shooter_habit(ket_sor) == (7, "átlövés bal", 4, 4)


def test_top_shooter_habit_keves_loves_vagy_szort_loves_none():
    """4 lövés alatt, vagy ha a lövések szétszórtak (a fő zóna 60% alatt
    van), nincs kimondható szokás: None; üres / hiányzó lista is None."""
    from handball.pipeline.scouting import _top_shooter_habit

    keves = ScoutingReport(team="home", team_name="Mi", shooter_zones=[
        {"player_id": 7, "zone": "balszél", "shots": 3}])
    assert _top_shooter_habit(keves) is None
    szort = ScoutingReport(team="home", team_name="Mi", shooter_zones=[
        {"player_id": 7, "zone": "balszél", "shots": 3},
        {"player_id": 7, "zone": "jobbszél", "shots": 3}])
    assert _top_shooter_habit(szort) is None
    assert _top_shooter_habit(ScoutingReport(team="home",
                                             team_name="Mi")) is None
    ures = ScoutingReport(team="home", team_name="Mi")
    ures.shooter_zones = None
    assert _top_shooter_habit(ures) is None


def test_avg_from_sums_sulyozott_atlag_vagy_none():
    """A poszt-lencse darabszám/összeg szótáraiból a súlyozott átlag; 8
    mért lövés alatt None (nem hallgatólagos 0) — üres / None szótárra
    is."""
    from handball.pipeline.scouting import (TREND_DERIVED_MIN_SHOTS,
                                            _avg_from_sums)

    assert TREND_DERIVED_MIN_SHOTS == 8
    darab = {"szélső": 3, "átlövő": 5}
    osszeg = {"szélső": 24.0, "átlövő": 60.0}
    assert _avg_from_sums(darab, osszeg) == 84.0 / 8
    assert _avg_from_sums({"szélső": 7}, {"szélső": 70.0}) is None
    assert _avg_from_sums({}, {}) is None
    assert _avg_from_sums(None, None) is None
    # Összeg nélkül (de elég darabbal) az átlag 0 — a darab a kapu.
    assert _avg_from_sums({"szélső": 8}, None) == 0.0


def test_mpl_theme_a_meccsterv_mondat_temaja():
    """A meccsterv-mondat téma-indexe (kisebb = előbbre kerül): az első
    illeszkedő téma dönt, kis- és nagybetűtől függetlenül; ami egyik
    témába sem illik, a lista végére megy — a rendezés a témán belül
    megtartja az eredeti sorrendet."""
    from handball.pipeline.scouting import (MPL_THEMES, _mpl_order,
                                            _mpl_theme)

    nevek = [n for n, _ in MPL_THEMES]
    assert _mpl_theme("Tükör-meccs lesz, hasonló a tempótok") == \
        nevek.index("jelleg")
    assert _mpl_theme("A KAPUSUK a bal alsót gyengén védi") == \
        nevek.index("kapus")
    assert _mpl_theme("A faluk a jobb oldalon réses") == \
        nevek.index("védekezés")
    assert _mpl_theme("A szélső befutására építsetek figurát") == \
        nevek.index("támadás")
    assert _mpl_theme("Sok kétpercet szednek össze") == \
        nevek.index("fegyelem")
    assert _mpl_theme("Semmi említésre méltó") == len(MPL_THEMES)
    assert _mpl_theme("") == len(MPL_THEMES)
    # Az első illeszkedő téma dönt: a kapus megelőzi a védekezést.
    assert _mpl_theme("A kapus és a fal közti rés") == nevek.index("kapus")
    terv = ["Sok kétpercet szednek össze", "A faluk réses (1)",
            "Egyéb megjegyzés", "A kapusuk gyenge", "A faluk réses (2)"]
    assert _mpl_order(terv) == [
        "A kapusuk gyenge", "A faluk réses (1)", "A faluk réses (2)",
        "Sok kétpercet szednek össze", "Egyéb megjegyzés"]
    assert _mpl_order([]) == []


def test_az_osszefesult_figura_es_fal_kepek_a_sorokbol_szamolodnak():
    """A meccsek közti figura- és fal-képek (7a6, emberelőny, hajrá,
    állás, hajrá-fal, fal-alak, figura × forma) a riportok lapos SORAIBÓL
    számolódnak újra: a két meccs sorait együtt adják az összegzőnek;
    sorok nélkül az üres kép jön (ítélet nélkül)."""
    from handball.pipeline import defense, scouting, setplays

    alak = [0.0] * 18
    alak[11] = 1.0
    sor = {"shape": alak, "attacks": 2, "goals": 1, "rest_attacks": 1}
    a = _riport(empty_net_figure_rows=[sor], powerplay_figure_rows=[sor],
                clutch_figure_rows=[sor], clutch_wall_rows=[sor],
                defense_shape_rows=[sor])
    b = _riport(empty_net_figure_rows=[sor], powerplay_figure_rows=[sor],
                clutch_figure_rows=[sor], clutch_wall_rows=[sor],
                defense_shape_rows=[sor])
    parok = [
        (scouting._empty_net_figures_of, setplays.empty_net_figures_summary),
        (scouting._powerplay_figures_of, setplays.powerplay_figures_summary),
        (scouting._clutch_figures_of, setplays.clutch_figures_summary),
        (scouting._clutch_wall_of, defense.clutch_wall_summary),
        (scouting._defense_shapes_of, defense.defense_shape_summary),
    ]
    for of, osszegzo in parok:
        assert of([a, b]) == osszegzo([sor, sor]), of.__name__
        assert of([a]) == osszegzo([sor]), of.__name__
        assert of([]) == osszegzo([]), of.__name__
        assert of([_riport()]) == osszegzo([]), of.__name__
    # Két meccs együtt 4 támadás → már ítél; egy meccs 2 támadása kevés.
    assert scouting._powerplay_figures_of([a])["verdict"] is None
    assert scouting._powerplay_figures_of([a, b])["verdict"] is not None

    allas = {"shape": alak, "state": "leading", "attacks": 3, "goals": 1}
    forma = {"shape": alak, "formation": "6-0", "attacks": 2, "goals": 0}
    c = _riport(setplay_score_rows=[allas], setplay_formation_rows=[forma])
    assert scouting._setplay_score_of([c, c]) == \
        setplays.setplay_score_summary([allas, allas])
    assert scouting._figure_formation_of([c, c]) == \
        setplays.figure_formation_summary([forma, forma])
    assert scouting._setplay_score_of([_riport()])["verdict"] is None
    assert scouting._figure_formation_of([]) == {"figures": [],
                                                 "verdict": None}
