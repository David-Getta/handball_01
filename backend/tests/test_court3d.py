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


def _eladasos_meccs():
    """Szintetikus meccs labdavesztésekkel (a szimulátor lövés-környéki
    váltásait az esemény-felismerés kiszűri, ezért itt építjük): a
    hazai 7-es a középső harmadban kipréselve veszít, és a vendég fél
    percen belül gólt lő belőle; a támadó harmadban magától (az ellenfél
    4 m-re, OLDALT — a kapu felé ugró labda lövésnek látszana); a saját
    harmadban kipréselve. A körök közti váltások (a vendég labdája a
    következő kör hazai birtoklásához) maguk is eladások — a vendég
    oldalán; azokat a négy réteg is ugyanígy látja."""
    def jat(tid, team, x, y, mez=None):
        return PlayerPosition(track_id=tid, team=team, x=x, y=y,
                              source=PositionSource.MEASURED,
                              confidence=1.0, jersey_number=mez)

    frames = []
    t = 0

    def ciklus(vesztes_hazai, x, tav, gol):
        nonlocal t
        v = (jat(1, Team.HOME, x, 10.0, 7) if vesztes_hazai
             else jat(11, Team.AWAY, x, 10.0, 4))
        sz = (jat(11, Team.AWAY, x, 10.0 + tav, 4) if vesztes_hazai
              else jat(1, Team.HOME, x, 10.0 + tav, 7))
        both = [v, sz]
        for _ in range(10):
            frames.append(Frame(t=t, players=both,
                                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(10):
            frames.append(Frame(t=t, players=both,
                                ball=Ball(x=x, y=10.0 + tav, confidence=1.0)))
            t += 1
        if gol:
            for _ in range(50):  # a lövés-elnyomó ablakon kívülre
                frames.append(Frame(t=t, players=both,
                                    ball=Ball(x=x, y=10.0 + tav,
                                              confidence=1.0)))
                t += 1
            lovo = [jat(12, Team.AWAY, 7.0, 10.0, 9)]
            for i in range(9):
                frames.append(Frame(t=t, players=lovo,
                                    ball=Ball(x=max(6.0 - i, 0.0), y=10.0,
                                              confidence=1.0)))
                t += 1
        for _ in range(900):  # hosszú szünet: a következő kör önálló
            frames.append(Frame(t=t, players=[], ball=None))
            t += 1

    ciklus(True, 20.0, 0.6, True)
    ciklus(True, 35.0, 4.0, False)
    ciklus(True, 8.0, 0.6, False)
    return Match(MatchMeta(match_id="to", home_team="H", away_team="A",
                           fps=25.0), frames)


def test_labdavesztes_pillanatok_a_negy_eladas_reteggel_egyeznek():
    """A labdavesztés-pillanatok ugyanazt mondják, mint a négy
    labdaeladás-réteg: a csapatonkénti szám a turnover_punishment
    eladásai, a gólba került a büntetettek, a harmadok a turnover_zones
    zónái, a kipréselt/magától a pressured_turnovers számai; a
    távolság a vesztő és a jelölt ellenfél helyéből újraszámolható."""
    from handball.pipeline.court3d import turnover_moments
    from handball.pipeline.defense import (PTO_PRESSURE_M,
                                           pressured_turnovers,
                                           turnover_punishment,
                                           turnover_zones)

    m = _eladasos_meccs()
    tm = turnover_moments(m)
    tp = turnover_punishment(m)
    tz = turnover_zones(m)
    pt = pressured_turnovers(m)
    assert tm["pressure_m"] == PTO_PRESSURE_M
    assert tm["turnovers"]["home"] == 3
    assert tm["punished"]["home"] == 1
    assert tm["forced"]["home"] == 2 and tm["unforced"]["home"] == 1
    assert [x["s"] for x in tm["moments"]] == sorted(x["s"] for x in tm["moments"])
    for side in ("home", "away"):
        sajat = [x for x in tm["moments"] if x["team"] == side]
        assert tm["turnovers"][side] == len(sajat) == tp[side]["turnovers"]
        assert tm["punished"][side] == tp[side]["punished"] == \
            sum(1 for x in sajat if x["punished"])
        zonak: dict = {}
        for x in sajat:
            if x["zone"] is not None:
                zonak[x["zone"]] = zonak.get(x["zone"], 0) + 1
        assert zonak == tz[side]["zones"]
        assert tm["forced"][side] == pt[side]["pressured"]
        assert tm["unforced"][side] == pt[side]["unforced"]
    for x in tm["moments"]:
        if x["forced"] is None:
            assert x["dist"] is None and x["opponent"] is None
            continue
        d = math.hypot(x["opponent"][0] - x["loser"][0],
                       x["opponent"][1] - x["loser"][1])
        assert abs(d - x["dist"]) < 0.02
        assert x["forced"] == (x["dist"] <= PTO_PRESSURE_M)
        assert (x["goal_after_s"] is not None) == x["punished"]
        if x["punished"]:
            assert 0 <= x["goal_after_s"] <= tm["quick_s"]
    hazai = [x for x in tm["moments"] if x["team"] == "home"]
    assert [x["zone"] for x in hazai] == ["közép", "támadó", "saját"]
    assert [x["forced"] for x in hazai] == [True, False, True]
    assert [x["punished"] for x in hazai] == [True, False, False]
    assert all(x["jersey"] == 7 for x in hazai)

def test_labdavesztes_pillanatok_ures_meccsen():
    """Eladás nélküli (labdátlan) meccsen üres a lista, a számok nullák."""
    from handball.pipeline.court3d import turnover_moments

    m = Match(MatchMeta(match_id="u", home_team="A", away_team="B",
                        fps=25.0),
              [Frame(t=i, players=[], ball=None) for i in range(50)])
    tm = turnover_moments(m)
    assert tm["moments"] == []
    assert tm["turnovers"] == {"home": 0, "away": 0}
    assert tm["punished"] == {"home": 0, "away": 0}


def test_fal_resek_a_wall_gaps_mercejevel():
    """A fal-rés réteg ugyanazt a falat látja, mint a wall_gaps: mért,
    kapus nélküli védők a saját kaputól 12 m-en belül, y szerint; a rés a
    szomszédok y-távolsága, a 3,5 m-es rés "széles"; 4 védő alatt nincs
    fal. A szimuláción a széles-kockák száma kockánként újraszámolva
    egyezik a wall_gaps "wide" számával."""
    from handball.pipeline.court3d import wall_gap_segments
    from handball.pipeline.defense import WALL_GAP_M, wall_gaps
    from handball.pipeline.tactics import (Phase, TacticsConfig,
                                           classify_phase)
    from handball.sim.match_simulator import simulate_ground_truth

    vedok = [_pl(1, Team.AWAY, 34.0, 4.0), _pl(2, Team.AWAY, 35.0, 6.5),
             _pl(3, Team.AWAY, 34.5, 11.0), _pl(4, Team.AWAY, 34.0, 13.0),
             # a kapus és a 12 m-en túli védő nem fal; a becsült sem
             PlayerPosition(track_id=5, team=Team.AWAY, x=39.0, y=10.0,
                            source=PositionSource.MEASURED, confidence=1.0,
                            role="kapus"),
             _pl(6, Team.AWAY, 26.0, 9.0),
             PlayerPosition(track_id=7, team=Team.AWAY, x=34.0, y=8.0,
                            source=PositionSource.ESTIMATED,
                            confidence=0.5),
             _pl(11, Team.HOME, 30.0, 10.0)]
    r = wall_gap_segments(vedok, Team.AWAY, 40.0)
    assert r["wall"] == [[34.0, 4.0], [35.0, 6.5], [34.5, 11.0], [34.0, 13.0]]
    assert r["gaps"] == [2.5, 4.5, 2.0]
    assert r["wide"] == [False, True, False]
    assert r["max_gap"] == 4.5 and r["max_index"] == 1
    # Három védő még nem fal.
    assert wall_gap_segments(vedok[:3], Team.AWAY, 40.0) is None

    m = simulate_ground_truth(duration_s=120, fps=25.0, seed=5,
                              shots_per_min=8)
    cfg = TacticsConfig()
    wg = wall_gaps(m, cfg)
    for side, team, kell in (("home", Team.HOME, Phase.AWAY_ATTACK),
                             ("away", Team.AWAY, Phase.HOME_ATTACK)):
        db = szeles = 0
        for f in m.frames:
            if classify_phase(f, cfg) != kell:
                continue
            x = wall_gap_segments(f.players, team, cfg.own_goal_x(team))
            if x is None:
                continue
            db += 1
            szeles += any(x["wide"])
            assert x["max_gap"] == max(x["gaps"])
            # A "széles" a kerekítetlen résből (mint a rétegben): a kiírt,
            # két tizedesre kerekített rés a küszöbön billenhet.
            if any(x["wide"]):
                assert x["max_gap"] >= WALL_GAP_M - 0.005
            else:
                assert x["max_gap"] <= WALL_GAP_M + 0.005
        assert db == wg[side]["frames"]
        assert szeles == wg[side]["wide"]


def test_gol_akciok_a_goal_buildup_lanc_szabalyaval():
    """A gól-akciók a goal_buildup réteg lánc-szabályával: gólonként a
    passzok száma adja a réteg rövid (≤ 2) és hosszú (≥ 5) számait; a
    lánc időrendben a gól előtt, legfeljebb BUILDUP_WINDOW_S hosszan;
    a cél a támadott kapu közepe."""
    from handball.pipeline.attack_types import (BUILDUP_LONG_PASSES,
                                                BUILDUP_SHORT_PASSES,
                                                BUILDUP_WINDOW_S,
                                                goal_buildup)
    from handball.pipeline.court3d import goal_build_ups
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=180, fps=25.0, seed=5,
                              shots_per_min=8)
    r = goal_build_ups(m)
    gb = goal_buildup(m)
    assert r["moments"], "a szimuláción van gól"
    for side in ("home", "away"):
        sajat = [x for x in r["moments"] if x["team"] == side]
        assert r["goals"][side] == len(sajat) == gb[side]["goals"]
        assert sum(1 for x in sajat
                   if x["n_passes"] <= BUILDUP_SHORT_PASSES) == gb[side]["short"]
        assert sum(1 for x in sajat
                   if x["n_passes"] >= BUILDUP_LONG_PASSES) == gb[side]["long"]
    for x in r["moments"]:
        assert x["n_passes"] == len(x["passes"])
        assert x["s"] <= x["goal_s"]
        assert 0 <= x["duration_s"] <= BUILDUP_WINDOW_S
        assert x["goal"][1] == 10.0 and x["goal"][0] in (0.0, 40.0)
    assert [x["goal_s"] for x in r["moments"]] == \
        sorted(x["goal_s"] for x in r["moments"])


def _kiallitasos_meccs():
    """Lövéses szimuláció, amelyben a vendég egyik mezőnyjátékosa a 30. és
    a 110. másodperc között nincs a pályán (kiállítás lenyomata)."""
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=240, fps=25.0, seed=5,
                              shots_per_min=8)
    ki = min(p.track_id for f in m.frames for p in f.players
             if p.team == Team.AWAY and p.role != "kapus")
    for f in m.frames:
        if 30 * 25 <= f.t <= 110 * 25:
            f.players = [p for p in f.players if p.track_id != ki]
    return m


def test_emberelony_szakaszok_a_powerplay_efficiency_szabalyaval():
    """Az emberelőny-szakaszok a detect_powerplay szakaszai; a szakaszon
    belüli kapura lövések és gólok csapatonként EGYEZNEK a
    powerplay_efficiency előny- és hátrány-számaival."""
    from handball.pipeline.court3d import powerplay_moments
    from handball.pipeline.rules import (detect_powerplay,
                                         powerplay_efficiency)

    m = _kiallitasos_meccs()
    pm = powerplay_moments(m)
    ab = detect_powerplay(m)
    pe = powerplay_efficiency(m)
    assert pm["windows"] == len(ab) == 1
    w = pm["moments"][0]
    assert w["team_down"] == "away" and w["team_up"] == "home"
    assert 29.0 <= w["s"] <= 31.0 and w["e"] > w["s"]
    for side in ("home", "away"):
        fel = [x for x in pm["moments"] if x["team_up"] == side]
        le = [x for x in pm["moments"] if x["team_down"] == side]
        assert sum(x["shots_up"] for x in fel) == pe[side]["pp_shots"]
        assert sum(x["goals_up"] for x in fel) == pe[side]["pp_goals"]
        assert sum(x["goals_up"] for x in le) == pe[side]["sh_conceded"]
    assert len(w["goals"]) == w["goals_up"] + w["goals_down"] > 0
    assert all(w["s"] <= g[0] <= w["e"] for g in w["goals"])


def test_emberelony_nelkul_ures():
    """Teljes létszámú meccsen nincs emberelőny-szakasz."""
    from handball.pipeline.court3d import powerplay_moments
    from handball.sim.match_simulator import simulate_ground_truth

    pm = powerplay_moments(simulate_ground_truth(duration_s=120, fps=25.0,
                                                 seed=5, shots_per_min=8))
    assert pm == {"moments": [], "windows": 0}


def test_lerohanasok_a_kontra_retegek_szabalyaival():
    """A lerohanás-jelenetek a három kontra-réteg szabályával: a
    lerohanások és a góljaik száma a lerohanás-hatékonyságé, a második
    hullámos befejezések a kontra-hullámoké, az elszökött emberrel indult
    kontrák a kontra-elszökésé; a befutó útja az indulástól a lövésig."""
    from handball.pipeline.attack_types import (FAST_BREAK_ADV_MS,
                                                FAST_BREAK_MAX_S,
                                                fast_break_conversion,
                                                fast_break_headstart,
                                                fast_break_waves)
    from handball.pipeline.court3d import FB_PATH_STEP_S, fast_break_moments
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=300, fps=25.0, seed=7,
                              shots_per_min=8)
    r = fast_break_moments(m)
    fc, fw, fh = (fast_break_conversion(m), fast_break_waves(m),
                  fast_break_headstart(m))
    assert r["moments"], "a szimuláción van lerohanás"
    assert any(x["wave"] == "second" for x in r["moments"]), \
        "van második hullámos befejezés is"
    for side in ("home", "away"):
        sajat = [x for x in r["moments"] if x["team"] == side]
        assert r["breaks"][side] == len(sajat) == fc[side]["breaks"]
        assert r["goals"][side] == fc[side]["goals"] == \
            sum(1 for x in sajat if x["outcome"] == "goal")
        assert sum(1 for x in sajat if x["wave"] is not None) == fw[side]["breaks"]
        assert sum(1 for x in sajat if x["wave"] == "second") == fw[side]["second"]
        assert sum(1 for x in sajat if x["ahead"] is not None) == fh[side]["breaks"]
        assert sum(1 for x in sajat if x["ahead"]) == fh[side]["ahead"]
    for x in r["moments"]:
        assert x["defending"] != x["team"]
        assert x["s"] <= x["e"] and 0 < x["duration_s"] <= FAST_BREAK_MAX_S
        assert x["advance_ms"] >= FAST_BREAK_ADV_MS
        assert x["goal"][1] == 10.0 and x["goal"][0] in (0.0, 40.0)
        assert x["ball"] is not None and len(x["ball"]) == 2
        if x["outcome"] is not None:
            assert x["shot_s"] is not None and x["shot"] is not None
            assert x["shooter_jersey"] is not None
            # Az út az indulástól a lövésig, fél másodpercenként (+ a
            # lövés kockája): a hossz a lövés idejéből következik.
            lepesek = math.floor((x["shot_s"] - x["s"]) / FB_PATH_STEP_S) + 1
            assert lepesek <= len(x["path"]) <= lepesek + 1
            assert x["path"][-1] == x["shot"]
        else:
            assert x["shot_s"] is None and x["shot"] is None
    assert [x["s"] for x in r["moments"]] == sorted(x["s"] for x in r["moments"])


def test_a_jelenet_lista_lerohanas_sora_a_vedekezo_csapate():
    """A kapott lerohanás a jelenet-listában a VÉDEKEZŐ csapat sora
    ("kinek a hibája"), a támadó és a befejező mezszámával, a
    kimenetellel; holtversenyben a lerohanás a labdavesztés után áll."""
    from handball.pipeline.court3d import scene_rows

    lerohanasok = [
        {"s": 19.88, "team": "home", "defending": "away", "outcome": "goal",
         "shooter_jersey": 13},
        {"s": 61.0, "team": "away", "defending": "home", "outcome": "shot",
         "shooter_jersey": None},
        {"s": 90.5, "team": "home", "defending": "away", "outcome": None,
         "shooter_jersey": 4},
    ]
    eladas = [{"s": 61.0, "team": "home", "jersey": 7, "zone": "saját",
               "goal_after_s": None}]
    sorok = scene_rows([], [], eladas, "Szeged", "Veszprém", lerohanasok)
    assert [(r["tipus"], r["ido"], r["gol"]) for r in sorok] == [
        ("k", "0:19", True), ("e", "1:01", False), ("k", "1:01", False),
        ("k", "1:30", False)]
    assert sorok[0]["szoveg"] == \
        "Veszprém védekezése — kapott lerohanás: Szeged #13 · GÓL"
    assert sorok[2]["szoveg"] == \
        "Szeged védekezése — kapott lerohanás: Veszprém · lövés"
    assert sorok[3]["szoveg"] == \
        "Veszprém védekezése — kapott lerohanás: Szeged #4 · lövés nélkül"
    # Lerohanások nélkül a lista a régi (háromlistás) hívással azonos.
    assert scene_rows([], [], eladas, "Szeged", "Veszprém") == \
        scene_rows([], [], eladas, "Szeged", "Veszprém", [])
