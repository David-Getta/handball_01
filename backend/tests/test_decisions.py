"""
Tesztek a játékos-döntéselemzésre (decisions.py).

Szintetikus szituációkkal, videó nélkül. Ellenőrizzük az értékmodellt (lövés-
érték), az opció-kiértékelést, a passz-felismerést és a döntés-összegzést
("kihez passzol", "mennyire optimális").

Futtatás:
    python tests/test_decisions.py
"""

from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, Ball, Team, PositionSource,
)
from handball.pipeline.tactics import TacticsConfig
from handball.pipeline.decisions import (
    shot_value, ball_holder, evaluate_options, best_option,
    detect_passes, analyze_player_decisions,
)

# A HAZAI a +x (x=40) kapu felé támad; a kapu közepe (40, 10).
GOAL_X = 40.0


def _pl(track_id, team, x, y):
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0)


def test_shot_value_closer_is_higher():
    """Közelebbről nagyobb a lövésérték, mint távolról (középen)."""
    near = shot_value(34.0, 10.0, GOAL_X)   # 6 m-re
    far = shot_value(20.0, 10.0, GOAL_X)    # 20 m-re
    assert near > far


def test_shot_value_central_is_higher_than_wing():
    """Azonos távolságból középről nagyobb az érték, mint szélről."""
    central = shot_value(34.0, 10.0, GOAL_X)
    wing = shot_value(34.0, 2.0, GOAL_X)
    assert central > wing


def test_ball_holder_is_nearest():
    """A labdás játékos a labdához legközelebbi (sugáron belül)."""
    cfg = TacticsConfig()
    frame = Frame(t=0, players=[_pl(1, Team.HOME, 30.0, 10.0), _pl(2, Team.HOME, 20.0, 10.0)],
                  ball=Ball(x=30.5, y=10.0, confidence=1.0))
    holder = ball_holder(frame, cfg)
    assert holder is not None and holder.track_id == 1


def test_evaluate_options_has_shoot_and_passes():
    """Az opciók közt ott a lövés és minden csapattárs mint passz-cél."""
    cfg = TacticsConfig()
    frame = Frame(t=0, players=[
        _pl(1, Team.HOME, 25.0, 10.0),   # labdás
        _pl(2, Team.HOME, 34.0, 10.0),   # közel a kapuhoz
        _pl(11, Team.AWAY, 30.0, 5.0),
    ], ball=Ball(x=25.0, y=10.0, confidence=1.0))
    holder = ball_holder(frame, cfg)
    opts = evaluate_options(frame, holder, cfg)
    assert any(o.kind == "shoot" for o in opts)
    assert any(o.kind == "pass" and o.target_id == 2 for o in opts)


def test_best_option_is_pass_to_open_pivot():
    """Ha egy csapattárs szabadon áll a kapu közelében, a legjobb opció oda passz."""
    cfg = TacticsConfig()
    frame = Frame(t=0, players=[
        _pl(1, Team.HOME, 22.0, 10.0),   # labdás, távol a kaputól
        _pl(2, Team.HOME, 35.0, 10.0),   # szabad beálló a kapu előtt
    ], ball=Ball(x=22.0, y=10.0, confidence=1.0))
    holder = ball_holder(frame, cfg)
    best = best_option(evaluate_options(frame, holder, cfg))
    assert best.kind == "pass" and best.target_id == 2


def _hold_frames(holder_id, xs_by_id, t0):
    """Egy frame, ahol a labda a `holder_id` játékosnál van; xs_by_id: id->(x,y)."""
    players = [_pl(i, Team.HOME, xy[0], xy[1]) for i, xy in xs_by_id.items()]
    hx, hy = xs_by_id[holder_id]
    return Frame(t=t0, players=players, ball=Ball(x=hx, y=hy, confidence=1.0))


def test_detect_passes_holder_change():
    """A labdás váltása csapaton belül egy passz (1 → 2)."""
    pos = {1: (22.0, 10.0), 2: (35.0, 10.0)}
    frames = [
        _hold_frames(1, pos, 0),  # labda az 1-esnél
        _hold_frames(1, pos, 1),
        _hold_frames(2, pos, 2),  # most a 2-esnél → passz 1->2
    ]
    passes = detect_passes(Match(MatchMeta(match_id="t", home_team="A", away_team="B", fps=25), frames))
    assert len(passes) == 1
    assert passes[0].passer_id == 1 and passes[0].receiver_id == 2


def test_support_distance_tight_vs_isolated():
    """Szoros támogatás (társ ~3 m-re) → kis átlag, 0% izolált; magára
    hagyott labdás (társ ~9 m-re) → nagy átlag, 100% izolált. Kevés mért
    kockánál (< 100) nincs ítélet."""
    from handball.pipeline.decisions import support_distance

    tight_pos = {1: (22.0, 10.0), 2: (24.5, 11.0)}   # társ ~2,7 m
    iso_pos = {1: (22.0, 10.0), 2: (30.0, 15.0)}     # társ ~9,4 m

    frames = [_hold_frames(1, tight_pos, t) for t in range(120)]
    m = Match(MatchMeta(match_id="t", home_team="A", away_team="B", fps=25),
              frames)
    sup = support_distance(m)["home"]
    assert sup["frames"] == 120
    assert sup["avg_m"] is not None and sup["avg_m"] < 4.0
    assert sup["iso_pct"] == 0.0

    frames = [_hold_frames(1, iso_pos, t) for t in range(120)]
    m = Match(MatchMeta(match_id="t", home_team="A", away_team="B", fps=25),
              frames)
    sup = support_distance(m)["home"]
    assert sup["avg_m"] is not None and sup["avg_m"] > 7.0
    assert sup["iso_pct"] == 100.0

    # Kevés minta → nincs ítélet (de a kocka-szám látszik).
    short = Match(MatchMeta(match_id="t", home_team="A", away_team="B",
                            fps=25),
                  [_hold_frames(1, tight_pos, t) for t in range(10)])
    sup = support_distance(short)["home"]
    assert sup["frames"] == 10 and sup["avg_m"] is None


def test_analyze_player_optimal_when_passing_to_best():
    """Ha a játékos a legjobb opcióhoz (szabad beálló) passzol → optimal_rate=1."""
    pos = {1: (22.0, 10.0), 2: (35.0, 10.0), 3: (20.0, 2.0)}
    frames = [
        _hold_frames(1, pos, 0),
        _hold_frames(2, pos, 1),  # passz 1->2 (a 2 a legjobb opció)
    ]
    rep = analyze_player_decisions(
        Match(MatchMeta(match_id="t", home_team="A", away_team="B", fps=25), frames), player_id=1)
    assert rep.passes == 1
    assert rep.pass_distribution == {2: 1}
    assert rep.optimal_rate == 1.0
    assert rep.avg_value_gap < 1e-9


def test_analyze_player_suboptimal_when_passing_to_worse():
    """Ha rosszabb opcióhoz passzol, optimal_rate<1 és a value gap pozitív."""
    # 2: szabad beálló a kapunál (legjobb). 3: messzi szélen (rosszabb). 1 a 3-hoz passzol.
    pos = {1: (22.0, 10.0), 2: (35.0, 10.0), 3: (20.0, 2.0)}
    frames = [
        _hold_frames(1, pos, 0),
        _hold_frames(3, pos, 1),  # passz 1->3 (nem a legjobb)
    ]
    rep = analyze_player_decisions(
        Match(MatchMeta(match_id="t", home_team="A", away_team="B", fps=25), frames), player_id=1)
    assert rep.pass_distribution == {3: 1}
    assert rep.optimal_rate == 0.0
    assert rep.avg_value_gap > 0.0


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


def test_pass_security_flags_press_sensitive_team():
    """A szabad passzok tiszták, a testközeli védő melletti játékban 3
    eladás jön → a nyomott eladás-arány 30% vs szabadon 0%; kevés
    mintánál nincs ítélet."""
    from handball.pipeline.decisions import pass_security_under_pressure

    # Álló felállás: p1-p2 szabadon passzolgat, p3-p4 mellett ott a
    # d1 védő (1,5 m-re mindkettőtől), a labda mindig a birtokosnál.
    spots = {
        "p1": (1, Team.HOME, 5.0, 5.0),
        "p2": (2, Team.HOME, 9.0, 5.0),
        "p3": (3, Team.HOME, 30.0, 10.0),
        "p4": (4, Team.HOME, 33.0, 10.0),
        "d1": (11, Team.AWAY, 31.5, 10.0),
    }

    def _frames(t0, holder_key, n=5):
        players = [_pl(tid, team, x, y)
                   for (tid, team, x, y) in spots.values()]
        hx, hy = spots[holder_key][2], spots[holder_key][3]
        return [Frame(t=t0 + i, players=players,
                      ball=Ball(x=hx, y=hy, confidence=1.0))
                for i in range(n)]

    holds = (["p1", "p2"] * 5 + ["p1"]        # 10 szabad passz
             + ["p3"]                          # +1 szabad passz (p1→p3)
             + ["p4", "p3"] * 3 + ["p4"]       # 7 nyomott passz
             + ["d1", "p3", "d1", "p3", "d1"])  # 3 hazai nyomott eladás
    frames = []
    t = 0
    for key in holds:
        frames += _frames(t, key)
        t += 5
    meta = MatchMeta(match_id="ps", home_team="H", away_team="A", fps=25.0)
    ps = pass_security_under_pressure(Match(meta, frames))
    h = ps["home"]
    assert h["free_passes"] == 11 and h["free_to"] == 0
    assert h["press_passes"] == 7 and h["press_to"] == 3
    assert h["press_to_pct"] is not None
    assert abs(h["press_to_pct"] - 30.0) < 0.1
    assert h["free_to_pct"] == 0.0
    assert h["rise_pp"] is not None and h["rise_pp"] >= 15.0

    # Kevés minta: nincs ítélet.
    few = pass_security_under_pressure(Match(meta, frames[:60]))
    assert few["home"]["press_to_pct"] is None


def test_hold_time_players_finds_where_the_ball_stops():
    """Az 1-es öt labdás szakaszban átlag 2 mp-et tart, a 2-es 0,4-et
    → az 1-es a labdatartó; kevés szakasznál nincs megnevezett
    játékos."""
    from handball.pipeline.decisions import hold_time_players

    frames = []
    t = 0

    def _hold(pid, seconds):
        """`seconds` mp-ig a pid-es hazai játékosnál a labda (x=25)."""
        nonlocal t, frames
        for _ in range(int(seconds * 25)):
            frames.append(Frame(t=t, players=[
                PlayerPosition(track_id=pid, team=Team.HOME, x=25.0,
                               y=10.0, source=PositionSource.MEASURED,
                               confidence=1.0),
            ], ball=Ball(x=25.0, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(3):      # labda nélküli szünet: zárul a szakasz
            frames.append(Frame(t=t, players=[], ball=None))
            t += 1

    for _ in range(5):
        _hold(1, 2.0)
    for _ in range(5):
        _hold(2, 0.4)

    meta = MatchMeta(match_id="h", home_team="H", away_team="A", fps=25.0)
    htp = hold_time_players(Match(meta, frames))
    h = htp["home"]
    one = next(p for p in h["players"] if p["player_id"] == 1)
    two = next(p for p in h["players"] if p["player_id"] == 2)
    assert one["holds"] == 5 and two["holds"] == 5
    assert one["avg_s"] == 2.0 and two["avg_s"] == 0.4
    assert h["avg_s"] == 1.2
    assert h["slowest"] is not None and h["slowest"]["player_id"] == 1
    assert h["slowest"]["gap_s"] > 0
    # A vendégnek nincs labdás szakasza → nincs átlag és nincs ítélet.
    assert htp["away"]["holds"] == 0
    assert htp["away"]["avg_s"] is None
    assert htp["away"]["slowest"] is None

    # Egyetlen szakasz: kevés minta → nincs megnevezett játékos.
    few = hold_time_players(Match(meta, frames[:53]))
    assert few["home"]["slowest"] is None


# ---- Passz-sebesség (éles vagy lágy labdajáratás) ----------------------------

def _speed_match(flight_frames, n_passes=12, dist_m=8.0, fps=25.0):
    """HAZAI passz-sorozat az 1-es és a 2-es között: a labda
    `flight_frames` kockán át repül `dist_m` métert (a repülés alatt
    senki sincs a labdánál, így a birtokosváltás ideje mérhető)."""
    frames = []
    t = 0
    a_x, b_x = 20.0, 20.0 + dist_m
    for k in range(n_passes + 1):
        src_x, dst_x = (a_x, b_x) if k % 2 == 0 else (b_x, a_x)
        for _ in range(6):    # a passzoló birtokol
            frames.append(Frame(
                t=t, players=[_pl(1, Team.HOME, a_x, 10.0),
                              _pl(2, Team.HOME, b_x, 10.0)],
                ball=Ball(x=src_x, y=10.0, confidence=1.0)))
            t += 1
        for i in range(1, flight_frames + 1):
            f_ = i / (flight_frames + 1)
            frames.append(Frame(
                t=t, players=[_pl(1, Team.HOME, a_x, 10.0),
                              _pl(2, Team.HOME, b_x, 10.0)],
                ball=Ball(x=src_x + (dst_x - src_x) * f_, y=16.0,
                          confidence=1.0)))   # repülés közben senkinél
            t += 1
    return Match(MatchMeta(match_id="ps", home_team="H", away_team="A",
                           fps=fps), frames)


def test_pass_speed_flags_the_crisp_passing():
    """8 m-es passzok ~0,44 mp repüléssel (≈18 m/s) → éles
    passzjáték."""
    from handball.pipeline.decisions import pass_speed

    rec = pass_speed(_speed_match(flight_frames=10))["home"]
    assert rec["passes"] >= 10
    assert rec["avg_ms"] is not None and rec["avg_ms"] >= 12.0
    assert rec["fast_pct"] == 100.0
    assert rec["label"] == "éles passzjáték"


def test_pass_speed_flags_the_soft_passing():
    """Ugyanaz a 8 m bő 1 mp alatt (≈8 m/s) → lágy labdajáratás."""
    from handball.pipeline.decisions import pass_speed

    rec = pass_speed(_speed_match(flight_frames=25))["home"]
    assert rec["avg_ms"] is not None and rec["avg_ms"] <= 12.0
    assert rec["fast_pct"] == 0.0
    assert rec["label"] == "lágy labdajáratás"


def test_pass_speed_needs_enough_passes():
    """Kevés (10-nél kevesebb) mért passznál nincs ítélet."""
    from handball.pipeline.decisions import pass_speed

    rec = pass_speed(_speed_match(flight_frames=10, n_passes=4))["home"]
    assert rec["avg_ms"] is None and rec["label"] is None


# ---- Pressz-érzékeny játékosok ----------------------------------------------

def _pressure_match(cases, fps=25.0):
    """Nyomott labdás döntések: a `cases` elemei (játékos id,
    elveszett?) párok — a labdás mellett végig ott a védő."""
    frames = []
    t = 0
    for (pid, lost) in cases:
        # A labdás és a rászorító védő (1 m-re).
        for _ in range(6):
            frames.append(Frame(
                t=t, players=[_pl(pid, Team.HOME, 25.0, 10.0),
                              _pl(30, Team.AWAY, 26.0, 10.0),
                              _pl(9, Team.HOME, 20.0, 16.0)],
                ball=Ball(x=25.0, y=10.0, confidence=1.0)))
            t += 1
        if lost:
            # A labda az ellenfélhez kerül: nyomott eladás.
            for _ in range(6):
                frames.append(Frame(
                    t=t, players=[_pl(pid, Team.HOME, 25.0, 10.0),
                                  _pl(30, Team.AWAY, 26.0, 10.0)],
                    ball=Ball(x=26.0, y=10.0, confidence=1.0)))
                t += 1
        else:
            # A labda a szabadon álló társhoz megy: nyomott, de sikeres.
            for _ in range(6):
                frames.append(Frame(
                    t=t, players=[_pl(pid, Team.HOME, 25.0, 10.0),
                                  _pl(30, Team.AWAY, 26.0, 10.0),
                                  _pl(9, Team.HOME, 20.0, 16.0)],
                    ball=Ball(x=20.0, y=16.0, confidence=1.0)))
                t += 1
            for _ in range(6):   # a labda visszakerül a vizsgált emberhez
                frames.append(Frame(
                    t=t, players=[_pl(pid, Team.HOME, 25.0, 10.0),
                                  _pl(30, Team.AWAY, 26.0, 10.0),
                                  _pl(9, Team.HOME, 20.0, 16.0)],
                    ball=Ball(x=25.0, y=10.0, confidence=1.0)))
                t += 1
    return Match(MatchMeta(match_id="psp", home_team="H", away_team="A",
                           fps=fps), frames)


def test_pressure_sensitive_players_finds_the_weak_link():
    """Aki hat nyomott döntéséből négyszer veszíti el a labdát → rá
    kell küldeni a kettőzést."""
    from handball.pipeline.decisions import pressure_sensitive_players

    cases = [(4, True)] * 4 + [(4, False)] * 2
    rec = pressure_sensitive_players(_pressure_match(cases))["home"]
    assert rec["top"] is not None
    assert rec["top"]["player_id"] == 4
    assert rec["top"]["press_to"] == 4


def test_pressure_sensitive_players_needs_enough_events():
    """Kevés (5-nél kevesebb) nyomott döntésnél nincs kiemelt
    játékos."""
    from handball.pipeline.decisions import pressure_sensitive_players

    rec = pressure_sensitive_players(
        _pressure_match([(4, True), (4, True)]))["home"]
    assert rec["top"] is None


# ---- Lövésválasztás (volt-e jobb szabad helyzet) ----------------------------

def _scq_match(plan, warmup=120):
    """`plan` = lövésenként (rossz_valasztas?) — ha igaz, a lövő élesen
    kifelé áll, a társa pedig szabadon a kapu előtt (jobb helyzet); ha
    hamis, fordítva.

    A lövő mellett mindig áll egy vendég védő (különben a lövés is
    "szabad" lenne), a kapu előtti társ mellett soha.
    """
    frames = []
    t = 0

    def _cast(shooter_xy, mate_xy, guard_xy):
        return [
            PlayerPosition(track_id=1, team=Team.HOME, x=shooter_xy[0],
                           y=shooter_xy[1], source=PositionSource.MEASURED,
                           confidence=1.0),
            PlayerPosition(track_id=2, team=Team.HOME, x=mate_xy[0],
                           y=mate_xy[1], source=PositionSource.MEASURED,
                           confidence=1.0),
            PlayerPosition(track_id=20, team=Team.AWAY, x=guard_xy[0],
                           y=guard_xy[1], source=PositionSource.MEASURED,
                           confidence=1.0),
            PlayerPosition(track_id=21, team=Team.AWAY, x=0.5, y=10.0,
                           source=PositionSource.MEASURED, confidence=1.0),
        ]

    def _add(cast, bx, by):
        nonlocal t
        frames.append(Frame(t=t, players=cast,
                            ball=Ball(x=bx, y=by, confidence=1.0)))
        t += 1

    for bad in plan:
        # Rossz választás: a lövő 12 m-ről, élesen; a társ a 7 m-en.
        # Jó választás: a lövő áll a 7 m-en, a "társ" messze kint.
        shooter = (28.0, 1.5) if bad else (34.0, 10.0)
        mate = (34.5, 10.0) if bad else (26.0, 1.0)
        guard = (shooter[0] - 0.5, shooter[1])
        cast = _cast(shooter, mate, guard)
        for _ in range(warmup):
            _add(cast, shooter[0] + 0.2, shooter[1])
        steps = 10
        for i in range(1, steps + 1):
            f = i / steps
            _add(cast,
                 shooter[0] + 0.2 + (40.4 - shooter[0] - 0.2) * f,
                 shooter[1] + (10.0 - shooter[1]) * f)
        for _ in range(30):
            _add(cast, 5.0, 10.0)
    return Match(MatchMeta(match_id="scq", home_team="H", away_team="A",
                           fps=25.0), frames)


def test_shot_choice_quality_flags_the_thrown_away_option():
    """Ha minden lövésnél szabadon állt a jobb helyzetű társ, a réteg
    kimondja: nem néznek fel."""
    from handball.pipeline.decisions import (SCQ_MIN_SHOTS,
                                             shot_choice_quality)

    rec = shot_choice_quality(_scq_match([True] * 6))["home"]
    assert rec["shots"] >= SCQ_MIN_SHOTS, rec
    assert rec["better_options"] >= 5, rec
    assert rec["pct"] >= 45.0, rec
    assert rec["avg_gap_xg"] and rec["avg_gap_xg"] >= 0.10, rec
    assert rec["verdict"] and "nem néznek fel" in rec["verdict"], rec


def test_shot_choice_quality_silent_with_few_shots():
    """Két lövésből nincs ítélet."""
    from handball.pipeline.decisions import shot_choice_quality

    rec = shot_choice_quality(_scq_match([True, True]))["home"]
    assert rec["pct"] is None and rec["verdict"] is None, rec


# ---- Labdatartó-poszt (melyik posztjuknál áll meg a labda) -----------------


def _htr_match(hold_plan, fps=25.0):
    """Poszt-minta (7: beálló, 9: szélső) + labdás szakaszok: a
    `hold_plan` elemei (birtokos id, hossz képkockában) párok."""
    spos = {7: (34.0, 10.0), 9: (35.0, 3.0)}

    def cast():
        return [_pl(tid, Team.HOME, *xy) for tid, xy in spos.items()]

    frames = []
    t = 0
    for _ in range(150):             # poszt-minta: hazai birtoklás elöl
        frames.append(Frame(t=t, players=cast(),
                            ball=Ball(x=34.2, y=10.0, confidence=1.0)))
        t += 1
    for (tid, n) in hold_plan:
        for _ in range(10):          # gazdátlan labda: szakasz-határ
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        sx, sy = spos[tid]
        for _ in range(n):           # a labda a birtokosnál áll
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=sx + 0.2, y=sy,
                                          confidence=1.0)))
            t += 1
    return Match(MatchMeta(match_id="t", home_team="A", away_team="B",
                           fps=fps), frames)


def test_hold_time_roles_names_the_slow_post():
    """A mért tartás dandárja a beállónál telik → nála áll a labda."""
    from handball.pipeline.decisions import HTR_MIN_S, hold_time_roles

    plan = [(7, 500)] * 3 + [(9, 100)]   # 60 mp beálló, 4 mp szélső
    rec = hold_time_roles(_htr_match(plan))["home"]
    assert rec["seconds"] >= HTR_MIN_S, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "kettőzést" in rec["verdict"], rec


def test_hold_time_roles_silent_with_little_holding():
    """Kevés mért tartásból nincs ítélet."""
    from handball.pipeline.decisions import hold_time_roles

    rec = hold_time_roles(_htr_match([(7, 100), (9, 50)]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Pressz-poszt (melyik posztjuk ejti a labdát szorításban) --------------


def _psr_match(losers, fps=25.0):
    """Poszt-minta (7: beálló, 9: szélső) + nyomott eladások: a
    `losers` elemei a labdát szorításban elvesztő hazai játékosok."""
    spos = {7: (34.0, 10.0), 9: (35.0, 3.0)}

    def cast(extra=()):
        return ([_pl(tid, Team.HOME, *xy) for tid, xy in spos.items()]
                + list(extra))

    frames = []
    t = 0
    for _ in range(150):             # poszt-minta: hazai birtoklás elöl
        frames.append(Frame(t=t, players=cast(),
                            ball=Ball(x=34.2, y=10.0, confidence=1.0)))
        t += 1
    for pid in losers:
        for _ in range(10):          # gazdátlan labda: szakasz-határ
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=15.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        # A vizsgált ember a labdával, rászorító védővel (kb. 1 m) —
        # a poszt-mintát nem zavarja: a kaputól 16+ m-re történik.
        lx, ly = (24.0, 10.0) if pid == 7 else (24.0, 3.0)
        deff = _pl(30, Team.AWAY, lx + 0.9, ly)
        holder_cast = [_pl(pid, Team.HOME, lx, ly), deff] + [
            _pl(tid, Team.HOME, *xy)
            for tid, xy in spos.items() if tid != pid]
        for _ in range(6):
            frames.append(Frame(t=t, players=holder_cast,
                                ball=Ball(x=lx, y=ly, confidence=1.0)))
            t += 1
        for _ in range(6):           # a labda a védőhöz kerül: eladás
            frames.append(Frame(t=t, players=holder_cast,
                                ball=Ball(x=lx + 0.9, y=ly,
                                          confidence=1.0)))
            t += 1
    return Match(MatchMeta(match_id="psr", home_team="H",
                           away_team="A", fps=fps), frames)


def test_press_sensitive_roles_names_the_pressed_post():
    """Négy nyomott eladásból három a beállóé → oda megy a kettőzés."""
    from handball.pipeline.decisions import (PSR_MIN_TO,
                                             press_sensitive_roles)

    rec = press_sensitive_roles(_psr_match([7, 7, 7, 9]))["home"]
    assert rec["press_to"] >= PSR_MIN_TO, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "labdaszerzés" in rec["verdict"], rec


def test_press_sensitive_roles_silent_with_few_losses():
    """Néhány nyomott eladásból nincs ítélet."""
    from handball.pipeline.decisions import press_sensitive_roles

    rec = press_sensitive_roles(_psr_match([7, 9]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Lágypassz-poszt (melyik posztjuk passzol lágyan) ----------------------


def _sps_match(soft_passers, fps=25.0):
    """Poszt-minta (7: beálló, 9: szélső) + passzok: a `soft_passers`
    szerinti játékos lágy (lassú röptű) passzt ad a társának."""
    spos = {7: (34.0, 10.0), 9: (35.0, 3.0)}

    def cast():
        return [_pl(tid, Team.HOME, *xy) for tid, xy in spos.items()]

    frames = []
    t = 0
    for _ in range(150):             # poszt-minta: hazai birtoklás elöl
        frames.append(Frame(t=t, players=cast(),
                            ball=Ball(x=34.2, y=10.0, confidence=1.0)))
        t += 1
    for pid in soft_passers:
        rid = 9 if pid == 7 else 7
        px, py = spos[pid]
        rx, ry = spos[rid]
        for _ in range(8):           # a labda a passzolónál
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=px + 0.2, y=py,
                                          confidence=1.0)))
            t += 1
        mx, my = (px + rx) / 2.0, (py + ry) / 2.0
        for i in (0.4, 0.8):         # el a passzolótól
            frames.append(Frame(
                t=t, players=cast(),
                ball=Ball(x=px + (mx - px) * i,
                          y=py + (my - py) * i, confidence=1.0)))
            t += 1
        for _ in range(30):          # íves, lágy labda: lebeg középen
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=mx, y=my,
                                          confidence=1.0)))
            t += 1
        for i in (0.4, 0.8):         # le a fogadóhoz
            frames.append(Frame(
                t=t, players=cast(),
                ball=Ball(x=mx + (rx - mx) * i,
                          y=my + (ry - my) * i, confidence=1.0)))
            t += 1
        for _ in range(8):           # átvétel a fogadónál
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=rx + 0.2, y=ry,
                                          confidence=1.0)))
            t += 1
        for _ in range(10):          # semleges labda a két passz közt
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=20.0, y=16.0,
                                          confidence=1.0)))
            t += 1
    return Match(MatchMeta(match_id="sps", home_team="H",
                           away_team="A", fps=fps), frames)


def test_soft_pass_roles_names_the_soft_post():
    """Hat lágy passzból öt a beállóé → az ő labdáiba bele lehet
    nyúlni."""
    from handball.pipeline.decisions import (SPS_MIN_SOFT,
                                             soft_pass_roles)

    rec = soft_pass_roles(_sps_match([7] * 5 + [9]))["home"]
    assert rec["soft"] >= SPS_MIN_SOFT, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "bele lehet nyúlni" in rec["verdict"], rec


def test_soft_pass_roles_silent_with_few_soft_passes():
    """Néhány lágy passzból nincs ítélet."""
    from handball.pipeline.decisions import soft_pass_roles

    rec = soft_pass_roles(_sps_match([7, 9]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Térnyerő-poszt (melyik posztjuk viszi előre a labdát) -----------------


def _tnr_match(runs, fps=25.0):
    """Poszt-minta (7: beálló, 9: szélső) + labdavezetések: a `runs`
    elemei (vivő, előre-méter) párok — a vivő a labdával halad a +x
    kapu felé, 0,2 m/kocka tempóban a saját sávjában."""
    spos = {7: (34.0, 10.0), 9: (35.0, 3.0)}

    frames = []
    t = 0
    for _ in range(150):             # poszt-minta: hazai birtoklás elöl
        frames.append(Frame(
            t=t,
            players=[_pl(tid, Team.HOME, *xy)
                     for tid, xy in spos.items()],
            ball=Ball(x=34.2, y=10.0, confidence=1.0)))
        t += 1
    for (tid, meters) in runs:
        _sx, sy = spos[tid]
        x = 20.0
        steps = int(meters / 0.2)
        for _ in range(steps):       # labdavezetés előre
            others = [_pl(o, Team.HOME, *spos[o])
                      for o in spos if o != tid]
            frames.append(Frame(
                t=t,
                players=[_pl(tid, Team.HOME, x, sy)] + others,
                ball=Ball(x=x + 0.2, y=sy, confidence=1.0)))
            x += 0.2
            t += 1
        for _ in range(10):          # semleges labda a futások közt
            frames.append(Frame(
                t=t,
                players=[_pl(tid2, Team.HOME, *spos[tid2])
                         for tid2 in spos],
                ball=Ball(x=15.0, y=16.0, confidence=1.0)))
            t += 1
    return Match(MatchMeta(match_id="tnr", home_team="H",
                           away_team="A", fps=fps), frames)


def test_ball_carrier_roles_names_the_carrying_post():
    """A térnyerés dandárja a beálló lábán van → hátrálva kell
    fogadni."""
    from handball.pipeline.decisions import (TNR_MIN_M,
                                             ball_carrier_roles)

    rec = ball_carrier_roles(
        _tnr_match([(7, 18.0), (7, 18.0), (7, 18.0),
                    (9, 10.0)]))["home"]
    assert rec["meters"] >= TNR_MIN_M, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "lendületbe engedni tilos" \
        in rec["verdict"], rec


def test_ball_carrier_roles_silent_with_little_carrying():
    """Kevés labdával megtett méterből nincs ítélet."""
    from handball.pipeline.decisions import ball_carrier_roles

    rec = ball_carrier_roles(
        _tnr_match([(7, 20.0), (9, 8.0)]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Fáradt-eladó poszt (kinek a labdái vesznek el a 2. félidőben) ---------


def _fto_match(fh_losers, sh_losers, with_break=True, fps=25.0):
    """Poszt-minta (7: beálló, 9: szélső) + eladások félidőnként: a
    vesztes labdája a 30-as vendég védőhöz kerül; a félidőket 90
    mp-es üres (szünet-) szakasz választja el."""
    spos = {7: (34.0, 10.0), 9: (35.0, 3.0)}

    def cast():
        return ([_pl(tid, Team.HOME, *xy) for tid, xy in spos.items()]
                + [_pl(30, Team.AWAY, 15.0, 10.0)])

    def lose(frames, t, tid):
        sx, sy = spos[tid]
        for _ in range(10):          # a labda a vesztesnél
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=sx + 0.2, y=sy,
                                          confidence=1.0)))
            t += 1
        for _ in range(10):          # a labda az ellenfélhez kerül
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=15.2, y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(10):          # semleges labda
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=25.0, y=16.0,
                                          confidence=1.0)))
            t += 1
        return t

    frames = []
    t = 0
    for _ in range(150):             # poszt-minta: hazai birtoklás elöl
        frames.append(Frame(t=t, players=cast(),
                            ball=Ball(x=34.2, y=10.0, confidence=1.0)))
        t += 1
    for tid in fh_losers:
        t = lose(frames, t, tid)
    if with_break:
        for _ in range(int(90 * fps)):   # félidei szünet: üres kockák
            frames.append(Frame(t=t, players=[], ball=None))
            t += 1
    for tid in sh_losers:
        t = lose(frames, t, tid)
    return Match(MatchMeta(match_id="fto", home_team="H",
                           away_team="A", fps=fps), frames)


def test_tired_turnover_roles_names_the_tiring_post():
    """A beálló eladásai 1-ről 4-re ugranak a 2. félidőre → fáradtan
    nála nyílik ki a kéz."""
    from handball.pipeline.decisions import tired_turnover_roles

    rec = tired_turnover_roles(
        _fto_match([7, 9], [7, 7, 7, 7]))["home"]
    assert rec["main_role"] == "beálló", rec
    assert rec["fh"] == 1 and rec["sh"] == 4, rec
    assert rec["verdict"] and "olcsó a labdaszerzés" in rec["verdict"], rec


def test_tired_turnover_roles_silent_without_jump():
    """Egyenletes eladás-eloszlásnál nincs ítélet."""
    from handball.pipeline.decisions import tired_turnover_roles

    rec = tired_turnover_roles(
        _fto_match([7, 7], [7, 7]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec
