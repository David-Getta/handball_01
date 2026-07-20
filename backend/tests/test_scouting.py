"""
Tesztek az ellenfél-felderítésre (scouting.py) — kézzel összerakott meccsekkel.

A pálya 40x20 m; a HAZAI a +x (x=40) kapu felé támad, saját kapuja x=0.

Futtatás:
    python tests/test_scouting.py
"""

from __future__ import annotations

import os
import sys
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
