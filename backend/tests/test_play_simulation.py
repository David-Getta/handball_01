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


def _press_match(nyom: bool, n: int = 60):
    """A hazai 1-es labdás 9 m-en (31; 13,3); a vendég fal a hatoson,
    `nyom` esetén a legközelebbi védő 1,2 m-re rálép."""
    frames = []
    for t in range(n):
        players = [_pl(1, Team.HOME, 31.0, 13.3), _pl(2, Team.HOME, 28.0, 8.0)]
        ys = (3, 6, 9, 11, 14, 17)
        for i, y in enumerate(ys):
            x, yy = 34.0, float(y)
            if nyom and y == 14:
                x, yy = 32.0, 14.2
            players.append(_pl(100 + i, Team.AWAY, x, yy))
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=31.0, y=13.3, confidence=1.0)))
    return Match(MatchMeta(match_id="p", home_team="A", away_team="B",
                           fps=25), frames)


def test_a_vedekezes_modell_megtanulja_a_kilepesi_hajlamot():
    """Ha a védő rendre rálép a lőtávolságon belüli labdásra, a modell
    kilépési hajlama magas; zárt falnál 0; kevés mintából (50 kocka alatt)
    nem tanul — 0 marad."""
    from handball.pipeline.play_simulation import PRESS_LEARN_MIN_FRAMES

    assert DefenseModel.learn(_press_match(True), Team.AWAY).press_rate == 1.0
    assert DefenseModel.learn(_press_match(False), Team.AWAY).press_rate == 0.0
    keves = _press_match(True, n=PRESS_LEARN_MIN_FRAMES - 1)
    assert DefenseModel.learn(keves, Team.AWAY).press_rate == 0.0


def test_a_kilepo_vedo_a_labdas_ele_lep_a_szimulacioban():
    """press_rate=1: lőtávolságon belüli labdánál a labdáshoz legközelebbi
    védő a labdás és a kapu-közép vonalán 1 m-re áll meg előtte; a többi
    védő a falban marad. press_rate=0: a fal változatlan. Távoli labdánál
    senki nem lép ki."""
    import math

    from handball.pipeline.play_simulation import PRESS_GAP_M

    labda = Ball(x=31.0, y=13.3, confidence=1.0)
    zart = DefenseModel().respond(labda, goal_x=40.0)
    kilep = DefenseModel(press_rate=1.0).respond(labda, goal_x=40.0)
    valtozott = [i for i, (a, b) in enumerate(zip(zart, kilep)) if a != b]
    assert len(valtozott) == 1, (zart, kilep)
    x, y = kilep[valtozott[0]]
    assert abs(math.hypot(x - 31.0, y - 13.3) - PRESS_GAP_M) < 1e-6
    assert x > 31.0  # a labdás és a kapu között
    tavol = Ball(x=24.0, y=10.0, confidence=1.0)
    assert (DefenseModel(press_rate=1.0).respond(tavol, goal_x=40.0)
            == DefenseModel().respond(tavol, goal_x=40.0))


def test_defense_respond_wall_outside_area_and_shift():
    """A 6-os fal a hatoson KÍVÜL áll (egy védő sincs a kapuelőtérben),
    középen a hatos előtt fél méterrel, a széleken az ívre simulva — és a
    labda y-felé tolódik."""
    import math

    model = DefenseModel(num_defenders=6, line_depth_m=6.0, lateral_gain=0.5)
    pos = model.respond(Ball(x=30.0, y=16.0, confidence=1.0), goal_x=40.0)
    assert len(pos) == 6
    # Egyik védő sem lehet a hatoson belül: a közelebbi kapufától 6 m+.
    for x, y in pos:
        post_y = min(11.5, max(8.5, y))
        assert math.hypot(x - 40.0, y - post_y) >= 6.0 - 1e-9
    # A fal íves: a szélső védő közelebb áll a kapu síkjához, mint a középső.
    mid = min(pos, key=lambda p: abs(p[1] - 10.0))
    wing = max(pos, key=lambda p: abs(p[1] - 10.0))
    assert wing[0] > mid[0]
    # Középen a hatos előtt fél méterrel (x = 40 - 6,5).
    assert abs(mid[0] - 33.5) < 0.6
    # A labda y=16 (a közép 10 felett) → a védők átlag y-ja feljebb tolódik.
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
