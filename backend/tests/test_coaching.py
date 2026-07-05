"""
Tesztek az élő edzői javaslatokra (coaching.py).

Kézzel összerakott frame-ekkel, videó nélkül. A pálya 40x20 m; a HAZAI a +x (x=40)
kapu felé támad, saját kapuja x=0. (Alapértelmezett TacticsConfig.)

Futtatás:
    python tests/test_coaching.py
"""

from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, Ball, Team, PositionSource,
)
from handball.pipeline.tactics import TacticsConfig
from handball.pipeline.coaching import (
    suggest_for_frame, coaching_timeline, Suggestion,
)


def _pl(track_id, team, x, y):
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0)


def _meta(fps=25.0):
    return MatchMeta(match_id="t", home_team="A", away_team="B", fps=fps,
                     frame_width=1920, frame_height=1080)


def _cats(sugg):
    return {s.category for s in sugg}


def test_no_ball_gives_general_hint():
    """Labda nélkül általános (alacsony prioritású) tanácsot ad."""
    frame = Frame(t=0, players=[_pl(1, Team.HOME, 30.0, 10.0)], ball=None)
    sugg = suggest_for_frame(frame, TacticsConfig())
    assert len(sugg) == 1 and sugg[0].category == "altalanos"


def test_free_ball_transition():
    """Ha nincs birtokos (a labda messze), átmeneti/tempó tanácsot ad."""
    frame = Frame(t=0, players=[_pl(1, Team.HOME, 5.0, 10.0)],
                  ball=Ball(x=35.0, y=10.0, confidence=1.0))
    sugg = suggest_for_frame(frame, TacticsConfig())
    assert sugg[0].category == "tempo"


def test_man_advantage_detected():
    """Több támadó mezőnyjátékos → emberelőny-javaslat, magas prioritással elöl."""
    # HAZAI birtokol (x=30, a támadó térfélen), 3 mezőnytámadó, 1 védő.
    players = [
        _pl(1, Team.HOME, 30.0, 10.0),   # labdás
        _pl(2, Team.HOME, 32.0, 4.0),
        _pl(3, Team.HOME, 32.0, 16.0),
        _pl(11, Team.AWAY, 34.0, 10.0),  # egyetlen védő (mezőnyben)
    ]
    frame = Frame(t=0, players=players, ball=Ball(x=30.0, y=10.0, confidence=1.0))
    sugg = suggest_for_frame(frame, TacticsConfig())
    assert "emberelony" in _cats(sugg)
    # a legmagasabb prioritású (elöl) az emberelőny (prio 5)
    assert sugg[0].priority == 5


def test_open_teammate_suggested():
    """Az ellenfelektől távoli, támadó térfélen lévő csapattársat ajánlja."""
    players = [
        _pl(1, Team.HOME, 22.0, 10.0),   # labdás, közel a felezőhöz
        _pl(2, Team.HOME, 35.0, 3.0),    # szabad a bal oldalon (nincs védő közel)
        _pl(11, Team.AWAY, 34.0, 17.0),  # védő a másik oldalon
        _pl(12, Team.AWAY, 33.0, 15.0),
    ]
    frame = Frame(t=0, players=players, ball=Ball(x=22.0, y=10.0, confidence=1.0))
    sugg = suggest_for_frame(frame, TacticsConfig())
    assert "szabad" in _cats(sugg)


def test_formation_suggestion_always_present():
    """Mindig ad egy védőforma-alapú irányt (itt 6-0 a mély fal)."""
    players = [_pl(1, Team.HOME, 30.0, 10.0)]
    # 6 védő a saját (x=40) kapu előtt, ~6 m mélységben (depth 4-6) → 6-0
    for i, y in enumerate([2, 6, 8, 12, 14, 18]):
        players.append(_pl(20 + i, Team.AWAY, 35.0, float(y)))
    frame = Frame(t=0, players=players, ball=Ball(x=30.0, y=10.0, confidence=1.0))
    sugg = suggest_for_frame(frame, TacticsConfig())
    forma = [s for s in sugg if s.category == "forma"]
    assert forma and "6-0" in forma[0].text


def test_fastbreak_from_ball_speed():
    """A labda gyors, támadó irányú elmozdulása → gyors indítás tanács."""
    cfg = TacticsConfig()
    prev = Frame(t=0, players=[_pl(1, Team.HOME, 20.0, 10.0)],
                 ball=Ball(x=20.0, y=10.0, confidence=1.0))
    # +0.5 m/frame * 25 fps = 12.5 m/s támadó irányban (a +x felé)
    cur = Frame(t=1, players=[_pl(1, Team.HOME, 20.5, 10.0)],
                ball=Ball(x=20.5, y=10.0, confidence=1.0))
    sugg = suggest_for_frame(cur, cfg, prev_frame=prev, fps=25.0)
    assert any(s.category == "tempo" and "indítás" in s.text for s in sugg)


def test_suggestions_sorted_by_priority():
    """A javaslatok prioritás szerint csökkenő sorrendben jönnek."""
    players = [
        _pl(1, Team.HOME, 30.0, 10.0),
        _pl(2, Team.HOME, 32.0, 4.0),
        _pl(11, Team.AWAY, 34.0, 10.0),
    ]
    frame = Frame(t=0, players=players, ball=Ball(x=30.0, y=10.0, confidence=1.0))
    sugg = suggest_for_frame(frame, TacticsConfig())
    prios = [s.priority for s in sugg]
    assert prios == sorted(prios, reverse=True)


def test_timeline_matches_frame_count():
    """A coaching_timeline minden frame-hez ad egy (nem üres) javaslat-listát."""
    frames = [
        Frame(t=i, players=[_pl(1, Team.HOME, 30.0, 10.0)],
              ball=Ball(x=30.0, y=10.0, confidence=1.0))
        for i in range(4)
    ]
    tl = coaching_timeline(Match(_meta(), frames))
    assert len(tl) == 4
    assert all(len(fr) >= 1 for fr in tl)
    # a szótár-alak tartalmazza a kulcsokat
    assert {"priority", "category", "text"} <= set(tl[0][0].keys())


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
