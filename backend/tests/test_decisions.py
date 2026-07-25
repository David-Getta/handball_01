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
