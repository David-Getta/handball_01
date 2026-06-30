"""
Tesztek a figura-szimulációra (play_simulation.py).

Szintetikus adatokkal, videó nélkül: a védekezési modell tanulása, a védők
reakciója, a figura lejátszása és pontozása.

Futtatás:
    python tests/test_play_simulation.py
"""

from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, Ball, Team, PositionSource,
)
from handball.pipeline.tactics import TacticsConfig
from handball.pipeline.play_simulation import (
    DefenseModel, SetPlay, simulate_setplay, evaluate_setplay,
)


def _pl(track_id, team, x, y):
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0)


def test_defense_model_learns_depth_and_count():
    """6 védő a 6 m-es vonalon (x≈34, kapu x=40 → mélység 6) → modell ~6, ~6 m."""
    frames = []
    for t in range(10):
        players = [_pl(i + 1, Team.HOME, 28.0, 10.0) for i in range(3)]  # hazai támad (x>20)
        players += [_pl(100 + i, Team.AWAY, 34.0, y) for i, y in enumerate((3, 6, 9, 11, 14, 17))]
        frames.append(Frame(t=t, players=players, ball=Ball(x=28.0, y=10.0, confidence=1.0)))
    model = DefenseModel.learn(Match(MatchMeta(match_id="t", home_team="A", away_team="B", fps=25), frames), Team.AWAY)
    assert model.num_defenders == 6
    assert abs(model.line_depth_m - 6.0) < 1e-6


def test_defense_respond_line_and_shift():
    """A védők a tanult mélységben állnak (x=34) és a labda y-felé tolódnak."""
    model = DefenseModel(num_defenders=6, line_depth_m=6.0, lateral_gain=0.5)
    pos = model.respond(Ball(x=30.0, y=16.0, confidence=1.0), goal_x=40.0)
    assert all(abs(x - 34.0) < 1e-9 for x, _ in pos)   # vonal a kaputól 6 m-re
    # a labda y=16 (a közép 10 felett) → a védők átlag y-ja feljebb tolódik
    avg_y = sum(y for _, y in pos) / len(pos)
    assert avg_y > 10.0


def _simple_setplay():
    """Kétlépéses figura: a 2-es támadó az 1. lépésben távol, a 2.-ban a kapu előtt."""
    attackers = [
        [(22.0, 6.0), (22.0, 6.0)],     # 1: irányító, stabil
        [(25.0, 14.0), (35.0, 10.0)],   # 2: beáll a kapu elé (x=35, y=10) a 2. lépésre
    ]
    ball_carrier = [0, 0]               # az irányítónál a labda (passzra készül)
    return SetPlay(attackers=attackers, ball_carrier=ball_carrier)


def test_simulate_setplay_builds_match():
    """A szimuláció a támadókat + tanult védőket + labdát tartalmazó Match-et ad."""
    model = DefenseModel(num_defenders=6, line_depth_m=6.0)
    match = simulate_setplay(_simple_setplay(), model)
    assert len(match.frames) == 2
    home = [p for p in match.frames[0].players if p.team == Team.HOME]
    away = [p for p in match.frames[0].players if p.team == Team.AWAY]
    assert len(home) == 2 and len(away) == 6
    assert match.frames[0].ball is not None


def test_evaluate_setplay_scores_open_chance():
    """A figura pontot kap, ha a beálló szabadon kerül a kapu közelébe.

    A védelem mélysége 9 m (x=31), így a 2. lépésben a beálló (x=35,y=10) a védők
    MÖGÉ, közel a kapuhoz kerül → magas lövésérték, szabadon.
    """
    model = DefenseModel(num_defenders=6, line_depth_m=9.0, lateral_gain=0.3)
    match = simulate_setplay(_simple_setplay(), model)
    result = evaluate_setplay(match)
    assert result["best_shot_value"] > 0.3   # teremtett jó helyzetet
    assert result["step"] == 1               # a 2. lépésben (a beállás után)


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
