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
                       gk_saves=2, gk_conceded_zones={"átlövés bal": 2})
    b = ScoutingReport(team="away", team_name="X", gk_on_target=6,
                       gk_saves=1, gk_conceded_zones={"átlövés bal": 1,
                                                      "jobbszél": 2})
    merged = combine_reports([a, b])
    assert merged.gk_on_target == 10 and merged.gk_saves == 3
    assert merged.gk_conceded_zones == {"átlövés bal": 3, "jobbszél": 2}


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
