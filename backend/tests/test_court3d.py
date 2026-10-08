"""A 3D pálya közös geometriája: lövés-mérés, falsablonok, védekezés-idővonal."""

from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (Ball, Frame, Match, MatchMeta,  # noqa: E402
                                      PlayerPosition, PositionSource, Team)
from handball.pipeline.court3d import (FORMATION_TEMPLATES,  # noqa: E402
                                       defence_timeline, formation_template,
                                       shot_geometry)


def _pl(tid, team, x, y):
    return PlayerPosition(track_id=tid, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0)


def test_a_lovesmeres_kozeprol_es_szelrol():
    """Középről a kapu-szög a két kapufa közti látószög; szélről ugyanannyi
    távolságból sokkal kisebb — a mérés ezt mutatja meg az edzőnek."""
    kozep = shot_geometry(9.0, 10.0)
    assert kozep["goal"] == "bal" and kozep["goal_x"] == 0.0
    assert kozep["distance_m"] == 9.0
    # 2·atan(1,5/9) ≈ 18,9°
    assert abs(kozep["angle_deg"] - math.degrees(2 * math.atan(1.5 / 9))) < 0.1
    assert kozep["zone"] == "9 m-en túl"  # pont a 9 m-es vonalon: már kívül

    # Ugyanakkora távolság a kapu közepétől, de a szélről (45°-ban).
    d = 9.0 / math.sqrt(2)
    szel = shot_geometry(d, 10.0 - d)
    assert abs(szel["distance_m"] - 9.0) < 0.01
    assert szel["angle_deg"] < kozep["angle_deg"]


def test_a_sav_a_kapufaktol_mert_tavolsag():
    """A 6 és 9 m-es vonal a kapufák közti SZAKASZTÓL mér: a kapu előtt 7 m
    a 6–9 m-es sáv, a jobb kapu előtt 5 m a kapuelőtér."""
    assert shot_geometry(7.0, 10.0)["zone"] == "6–9 m"
    jobb = shot_geometry(35.0, 11.0)
    assert jobb["goal"] == "jobb" and jobb["zone"] == "kapuelőtér"
    # A kapufán túli pont: a kapufától mért távolság számít (nem a
    # gólvonaltól): 5 m előre és 0,5 m oldalra a felső kapufától.
    assert shot_geometry(5.0, 12.0)["post_distance_m"] == round(math.hypot(5.0, 0.5), 2)
    assert shot_geometry(5.0, 11.0)["post_distance_m"] == 5.0
    assert shot_geometry(0.0, 8.5)["angle_deg"] == 180.0  # a kapufán


def test_a_kert_kapura_is_mer():
    """A távolabbi kapura is lehet mérni (pl. üres kapus lövés)."""
    g = shot_geometry(10.0, 10.0, goal="jobb")
    assert g["goal"] == "jobb" and g["distance_m"] == 30.0


def test_a_falsablonok_ervenyesek_es_a_felismero_a_nevukon_ismeri():
    """Minden sablon hat védő, a pályán, a 6 m-es vonalon kívül, tükör-
    szimmetrikus — és a `detect_formation` a SAJÁT nevén ismeri fel,
    mindkét kapu előtt (a sablon és az élő címke nem mondhat mást)."""
    from handball.pipeline.tactics import TacticsConfig, detect_formation

    cfg = TacticsConfig()
    for nev, sablon in FORMATION_TEMPLATES.items():
        assert len(sablon) == 6, nev
        ys = sorted(round(y, 3) for _, y in sablon)
        tukor = sorted(round(20.0 - y, 3) for _, y in sablon)
        assert ys == tukor, f"{nev}: nem szimmetrikus"
        for vedo, goal_x in ((Team.HOME, cfg.own_goal_x(Team.HOME)),
                             (Team.AWAY, cfg.own_goal_x(Team.AWAY))):
            pontok = formation_template(nev, goal_x)
            for x, y in pontok:
                assert 0.0 <= x <= 40.0 and 0.0 <= y <= 20.0, (nev, x, y)
                assert shot_geometry(x, y)["post_distance_m"] > 6.0, (nev, x, y)
            f = Frame(t=0, players=[_pl(i, vedo, x, y)
                                    for i, (x, y) in enumerate(pontok)])
            assert detect_formation(f, vedo, cfg).label == nev, (nev, vedo)
    assert formation_template("7-0", 0.0) == []


def test_a_vedekezes_idovonal_a_szervezett_tamadast_koveti():
    """Hazai támadás a +x kapura (a vendég 5-1-ben a jobb kapu előtt),
    másodpercenként egy sor; átmenetben (labda nélkül) nincs sor."""
    from handball.pipeline.tactics import TacticsConfig

    cfg = TacticsConfig()
    goal_x = cfg.own_goal_x(Team.AWAY)
    vedok = [_pl(20 + i, Team.AWAY, x, y)
             for i, (x, y) in enumerate(formation_template("5-1", goal_x))]
    frames = []
    for t in range(75):  # 3 mp @ 25 fps
        tamado = _pl(1, Team.HOME, 28.0, 10.0)
        frames.append(Frame(t=t, players=[tamado] + vedok,
                            ball=Ball(x=28.3, y=10.0, confidence=1.0)))
    for t in range(75, 100):  # 1 mp labda nélkül
        frames.append(Frame(t=t, players=vedok, ball=None))
    m = Match(MatchMeta(match_id="dt", home_team="H", away_team="A", fps=25.0),
              frames)
    sorok = defence_timeline(m, cfg)
    assert [r["t"] for r in sorok] == [0, 25, 50]
    assert all(r["defending"] == "away" and r["label"] == "5-1"
               and r["goal_x"] == goal_x for r in sorok)
    assert sorok[1]["s"] == 1.0


def test_a_feltores_sav_a_vedo_nezopontjabol_fordul():
    """A feltörés-sáv téglalapja: a 9 m-es vonalig a kapu elől, a sáv a
    VÉDŐ nézőpontjából — a 0-s kaput védőnek a bal szél a nagyobb y, a
    40-es kaput védőnek a kisebb (a defense.defensive_gaps szabálya);
    közép a középső harmad; sáv nélkül None."""
    from handball.pipeline.court3d import breakpoint_zone_band

    bal0 = breakpoint_zone_band("bal szél", 0.0)
    assert bal0 == {"x0": 0.0, "x1": 9.0, "y0": 13.333, "y1": 20.0}
    bal40 = breakpoint_zone_band("bal szél", 40.0)
    assert bal40 == {"x0": 31.0, "x1": 40.0, "y0": 0.0, "y1": 6.667}
    assert breakpoint_zone_band("jobb szél", 0.0)["y0"] == 0.0
    assert breakpoint_zone_band("közép", 40.0) == {"x0": 31.0, "x1": 40.0,
                                                   "y0": 6.667, "y1": 13.333}
    assert breakpoint_zone_band(None, 0.0) is None
    assert breakpoint_zone_band("átlövés közép", 0.0) is None


def test_a_passzsav_a_dontes_elemzes_modelljet_adja():
    """A 3D passzsávjai a döntés-elemzés passz-modellje
    (decisions.pass_completion, 1,5 m-es sáv) — a labdás a labdához
    legközelebbi, ha a birtoklás-sugáron (TacticsConfig) belül van."""
    from types import SimpleNamespace

    from handball.pipeline.court3d import pass_lane_grade, pass_lanes
    from handball.pipeline.decisions import pass_completion

    jat = [(1, 30.0, 10.0), (1, 25.0, 4.0), (1, 26.0, 16.0),
           (0, 33.0, 10.0), (0, 28.0, 7.0)]
    r = pass_lanes(jat, (30.5, 10.2))
    assert r["holder"] == [30.0, 10.0, True]
    assert len(r["lanes"]) == 2          # csak a csapattársak
    pl = [SimpleNamespace(team=bool(h), x=x, y=y) for h, x, y in jat]
    for lane, t in zip(r["lanes"], pl[1:3]):
        vart = pass_completion(pl[0], t, SimpleNamespace(players=pl))
        assert abs(lane["p"] - vart) < 1e-4
        assert lane["grade"] == pass_lane_grade(lane["p"])
    zart = next(l for l in r["lanes"] if (l["x"], l["y"]) == (25.0, 4.0))
    assert zart["blockers"] == 1          # a (28, 7) védő a sávban
    # Nincs labdás: a labda a birtoklás-sugáron kívül, vagy nincs labda.
    assert pass_lanes(jat, (40.0, 0.0)) is None
    assert pass_lanes(jat, None) is None
    assert pass_lane_grade(0.6) == "nyitott"
    assert pass_lane_grade(0.35) == "kockázatos"
    assert pass_lane_grade(0.34) == "zárt"


def test_dontes_pillanatok_a_dontes_elemzes_modelljevel():
    """A döntés-pillanatok: ahol a legjobb opció (decisions.best_option)
    legalább DECISION_GAP_MIN-nel jobb a választott passznál — a
    döntés-elemzés modelljével újraszámolva ugyanaz a különbség;
    lövésnél a cél a támadott kapu közepe; időrendben."""
    from handball.pipeline.court3d import DECISION_GAP_MIN, decision_moments
    from handball.pipeline.decisions import (best_option, detect_passes,
                                             evaluate_options)
    from handball.pipeline.tactics import TacticsConfig
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=120, fps=25.0, seed=5,
                              shots_per_min=8)
    d = decision_moments(m)
    assert d["moments"], "a szimuláción van jobb opciós pillanat"
    assert [x["s"] for x in d["moments"]] == sorted(x["s"] for x in d["moments"])
    assert sum(d["flagged"].values()) == len(d["moments"])
    assert all(d["flagged"][k] <= d["passes"][k] for k in ("home", "away"))
    cfg = TacticsConfig()
    by_s = {}
    for pe in detect_passes(m, cfg):
        opts = evaluate_options(pe.decision_frame, pe.passer_pos, cfg)
        best = best_option(opts)
        ch = next(o for o in opts if o.kind == "pass"
                  and o.target_id == pe.receiver_id)
        by_s.setdefault(round(pe.decision_frame.t / 25.0, 2), []).append(
            round(best.value - ch.value, 3))
    for x in d["moments"]:
        assert x["gap"] >= DECISION_GAP_MIN
        assert x["gap"] in by_s[x["s"]]
        # A két érték külön kerekítve: a különbségük ±0,001-en belül.
        assert abs((x["best_value"] - x["chosen_value"]) - x["gap"]) <= 0.0015
        if x["best_kind"] == "shoot":
            assert x["best"] in ([0.0, 10.0], [40.0, 10.0])


def test_kevés_passznal_nincs_dontes_pillanat():
    from handball.models.tracking import Match, MatchMeta
    from handball.pipeline.court3d import decision_moments

    d = decision_moments(Match(MatchMeta(match_id="u", home_team="A",
                                         away_team="B", fps=25.0), []))
    assert d == {"moments": [], "passes": {"home": 0, "away": 0},
                 "flagged": {"home": 0, "away": 0}}


def test_szabad_lovok_a_vedekezes_elemzes_iteletevel():
    """A szabad lövők pillanatai a defense_analysis lövés-soraiból: annyi,
    ahány szabad lövést a védekezés-elemzés számolt, a távolság a
    fedezés-sugár fölött, a védő helyéből újraszámolva egyezik."""
    import math

    from handball.pipeline.court3d import free_shot_moments
    from handball.pipeline.defense import FREE_DEF_RADIUS_M, defense_analysis
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=240, fps=25.0, seed=5,
                              shots_per_min=8)
    fs = free_shot_moments(m)
    da = defense_analysis(m)
    assert fs["radius_m"] == FREE_DEF_RADIUS_M
    for side in ("home", "away"):
        assert fs["free_shots"][side] == da[side]["free_shots"]
        assert sum(1 for x in fs["moments"] if x["defending"] == side) == \
            da[side]["free_shots"]
    assert fs["moments"], "a szimuláción van szabad lövés"
    assert [x["s"] for x in fs["moments"]] == sorted(x["s"] for x in fs["moments"])
    for x in fs["moments"]:
        assert x["dist"] > FREE_DEF_RADIUS_M
        if x["defender"] is not None:
            d = math.hypot(x["defender"][0] - x["shooter"][0],
                           x["defender"][1] - x["shooter"][1])
            assert abs(d - x["dist"]) < 0.02


def test_a_vedekezes_elemzes_lovessorai_viszik_a_helyet_es_a_vedot():
    """A defense_analysis lövés-sorai a régi mezők mellett a helyet, a
    mért kockát és a legközelebbi védőt is viszik; fedezett lövésnél a
    távolság a sugáron belül van."""
    from handball.pipeline.defense import FREE_DEF_RADIUS_M, defense_analysis
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=240, fps=25.0, seed=5,
                              shots_per_min=8)
    sorok = [sh for side in ("home", "away")
             for sh in defense_analysis(m)[side]["shots"]]
    assert sorok
    for sh in sorok:
        assert {"t", "zone", "free", "xg", "goal", "x", "y", "release_t",
                "defender", "def_dist"} <= set(sh)
        if sh["free"] is False:
            assert sh["def_dist"] <= FREE_DEF_RADIUS_M
