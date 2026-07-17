"""
Tesztek az eseményfelismerésre (event_detection.py): lövés, gól, passz, labdaeladás.

Szintetikus pályák, videó nélkül. A HAZAI a +x (x=40) kapu felé támad.

Futtatás:
    python tests/test_event_detection.py
"""

from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, Ball, Team, PositionSource,
)
from handball.pipeline.event_detection import (
    detect_shots, detect_possession_changes, detect_events, event_counts, EventType,
)


def _meta(fps=25.0):
    return MatchMeta(match_id="t", home_team="A", away_team="B", fps=fps)


def _pl(track_id, team, x, y):
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0)


def test_detect_goal():
    """A labda gyorsan a +x kapuhoz tart és a kapufák között eléri → GÓL (hazai)."""
    # x = 34..40 (1 m/frame = 25 m/s), y=10 (kapu közepe).
    frames = [Frame(t=i, players=[], ball=Ball(x=34.0 + i, y=10.0, confidence=1.0))
              for i in range(7)]
    shots = detect_shots(Match(_meta(), frames))
    goals = [e for e in shots if e.type == EventType.GOAL]
    assert len(goals) == 1
    assert goals[0].team == Team.HOME


def test_detect_shot_not_goal_when_off_target():
    """Gyors kapu felé tartó labda, de a kapufákon KÍVÜL (y=5) → LÖVÉS, nem gól."""
    frames = [Frame(t=i, players=[], ball=Ball(x=34.0 + i, y=5.0, confidence=1.0))
              for i in range(6)]  # x 34..39, sosem éri el a vonalat a kapuban
    shots = detect_shots(Match(_meta(), frames))
    assert len(shots) == 1
    assert shots[0].type == EventType.SHOT


def test_pass_vs_turnover():
    """Csapaton belüli birtokosváltás = passz; az ellenfélhez = labdaeladás."""
    frames = [
        Frame(t=0, players=[_pl(1, Team.HOME, 25.0, 10.0)], ball=Ball(x=25.0, y=10.0, confidence=1.0)),
        Frame(t=1, players=[_pl(2, Team.HOME, 28.0, 10.0)], ball=Ball(x=28.0, y=10.0, confidence=1.0)),  # passz 1->2
        Frame(t=2, players=[_pl(11, Team.AWAY, 20.0, 10.0)], ball=Ball(x=20.0, y=10.0, confidence=1.0)),  # eladás
    ]
    evs = detect_possession_changes(Match(_meta(), frames))
    assert [e.type for e in evs] == [EventType.PASS, EventType.TURNOVER]
    assert evs[0].detail == {"receiver_id": 2}
    assert evs[1].team == Team.HOME   # a HAZAI vesztette el


def test_turnover_suppressed_after_shot():
    """A lövés után az ellenfélhez kerülő labda NEM külön labdaeladás."""
    frames = []
    # Lövés a +x kapura (gyors), gól nélkül (y=6): x 34..40 y=6.
    for i in range(7):
        frames.append(Frame(t=i, players=[_pl(1, Team.HOME, 33.0, 6.0)],
                            ball=Ball(x=34.0 + i, y=6.0, confidence=1.0)))
    # Közvetlenül utána a vendég kapusé a labda — a kaputól OLDALT (y=4), hogy a
    # lövés ne minősüljön gólnak, csak a birtokváltást teszteljük.
    frames.append(Frame(t=7, players=[_pl(17, Team.AWAY, 39.5, 4.0)],
                        ball=Ball(x=39.5, y=4.0, confidence=1.0)))
    evs = detect_events(Match(_meta(), frames))
    types = [e.type for e in evs]
    assert EventType.SHOT in types           # a lövés megmarad
    assert EventType.TURNOVER not in types   # a lövés utáni labdaeladás elnyomva


def test_event_counts():
    """Az összegző típusonként számol."""
    frames = [
        Frame(t=0, players=[_pl(1, Team.HOME, 25.0, 10.0)], ball=Ball(x=25.0, y=10.0, confidence=1.0)),
        Frame(t=1, players=[_pl(2, Team.HOME, 28.0, 10.0)], ball=Ball(x=28.0, y=10.0, confidence=1.0)),
    ]
    c = event_counts(Match(_meta(), frames))
    assert c["total"] == 1
    assert c["by_type"]["pass"] == 1


def test_shot_outcome_save_with_goalkeeper():
    """Nem-gól lövés, ahol a labda a megjelölt KAPUS közelébe ér → védés."""
    gk = PlayerPosition(track_id=9, team=Team.AWAY, x=39.0, y=10.0,
                        source=PositionSource.MEASURED, confidence=1.0,
                        role="kapus")
    # A labda a kapu felé száll (kapufák között), de a kapusnál megáll —
    # nem éri el a gólvonalat.
    frames = []
    for i in range(6):
        x = min(34.0 + i, 38.8)
        frames.append(Frame(t=i, players=[gk],
                            ball=Ball(x=x, y=10.0, confidence=1.0)))
    shots = detect_shots(Match(_meta(), frames))
    assert len(shots) == 1
    e = shots[0]
    assert e.type == EventType.SHOT
    assert e.detail["outcome"] == "save"
    assert e.detail["goalkeeper_id"] == 9


def test_shot_outcome_miss_without_goalkeeper():
    """Kapus-jel nélkül a nem-gól lövés kimenetele "miss"."""
    frames = [Frame(t=i, players=[], ball=Ball(x=34.0 + i, y=5.0, confidence=1.0))
              for i in range(6)]
    shots = detect_shots(Match(_meta(), frames))
    assert shots[0].detail["outcome"] == "miss"


def test_goal_outcome_and_shooter():
    """Gólnál a kimenetel "goal", és a lövő (az utolsó hazai birtokos) is megvan."""
    shooter = _pl(4, Team.HOME, 33.5, 10.0)
    frames = [Frame(t=0, players=[shooter],
                    ball=Ball(x=33.6, y=10.0, confidence=1.0))]
    for i in range(1, 8):
        frames.append(Frame(t=i, players=[],
                            ball=Ball(x=33.6 + i, y=10.0, confidence=1.0)))
    shots = detect_shots(Match(_meta(), frames))
    goals = [e for e in shots if e.type == EventType.GOAL]
    assert len(goals) == 1
    assert goals[0].detail["outcome"] == "goal"
    assert goals[0].player_id == 4


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


# ---- Gólpassz (assist) -------------------------------------------------------

def _goal_with_pass(passer_present=True, receiver_id=2):
    """Passz (1 → receiver_id), majd a 2-es játékos gólja a +x kapura."""
    pls = lambda *ps: list(ps)  # noqa: E731
    frames = [
        Frame(t=0, players=pls(_pl(1, Team.HOME, 25.0, 10.0),
                               _pl(2, Team.HOME, 30.0, 10.0)),
              ball=Ball(x=25.0, y=10.0, confidence=1.0)),
        Frame(t=1, players=pls(_pl(1, Team.HOME, 25.0, 10.0),
                               _pl(receiver_id, Team.HOME, 30.0, 10.0)),
              ball=Ball(x=30.0, y=10.0, confidence=1.0)),
        Frame(t=2, players=pls(_pl(1, Team.HOME, 25.0, 10.0),
                               _pl(2, Team.HOME, 33.0, 10.0)),
              ball=Ball(x=33.0, y=10.0, confidence=1.0)),
    ]
    if not passer_present:  # csak a lövő: nincs passz-esemény a gól előtt
        frames = [Frame(t=f.t, players=[p for p in f.players if p.track_id == 2],
                        ball=f.ball) for f in frames]
    for i in range(7):  # a lövés: 34..40, y=10 → gól a kapufák között
        frames.append(Frame(t=3 + i,
                            players=pls(_pl(2, Team.HOME, 33.0, 10.0)),
                            ball=Ball(x=34.0 + i, y=10.0, confidence=1.0)))
    return Match(_meta(), frames)


def test_assist_attached_to_goal():
    """Passz a lövőnek, majd gól → a gól detail-jében assist_id a passzoló."""
    evs = detect_events(_goal_with_pass())
    goals = [e for e in evs if e.type == EventType.GOAL]
    assert len(goals) == 1
    assert goals[0].player_id == 2               # a lövő
    assert goals[0].detail.get("assist_id") == 1  # a gólpassz adója


def test_no_assist_without_prior_pass():
    """Egyéni akció (nincs passz a gól előtt) → nincs assist_id."""
    evs = detect_events(_goal_with_pass(passer_present=False))
    goals = [e for e in evs if e.type == EventType.GOAL]
    assert len(goals) == 1
    assert "assist_id" not in (goals[0].detail or {})


def test_old_pass_outside_window_is_not_assist():
    """A lövő rég (több mint ASSIST_WINDOW_S) kapta a labdát → nem gólpassz
    (egyéni akciónak számít, hiába volt korábban passz)."""
    frames = [
        Frame(t=0, players=[_pl(1, Team.HOME, 25.0, 10.0),
                            _pl(2, Team.HOME, 30.0, 10.0)],
              ball=Ball(x=25.0, y=10.0, confidence=1.0)),
        Frame(t=1, players=[_pl(1, Team.HOME, 25.0, 10.0),
                            _pl(2, Team.HOME, 30.0, 10.0)],
              ball=Ball(x=30.0, y=10.0, confidence=1.0)),  # passz 1→2
    ]
    for t in range(2, 111):  # a lövő ~4,4 mp-ig vezeti a labdát
        frames.append(Frame(t=t, players=[_pl(2, Team.HOME, 33.0, 10.0)],
                            ball=Ball(x=33.0, y=10.0, confidence=1.0)))
    for i in range(7):  # lövés: 34..40, y=10 → gól
        frames.append(Frame(t=111 + i, players=[_pl(2, Team.HOME, 33.0, 10.0)],
                            ball=Ball(x=34.0 + i, y=10.0, confidence=1.0)))
    evs = detect_events(Match(_meta(), frames))
    goals = [e for e in evs if e.type == EventType.GOAL]
    assert len(goals) == 1 and goals[0].player_id == 2
    assert "assist_id" not in (goals[0].detail or {})


def test_assist_network_pairs_and_leaders():
    """Két gól, mindkettőt az 1-es passzolja a 2-esnek → egy pár (2 gól),
    az 1-es a gólpassz-vezér."""
    from handball.pipeline.event_detection import assist_network
    frames = []
    t = 0
    for _ in range(2):
        # passz 1→2, majd a 2-es gólja a +x kapura
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 25.0, 10.0),
                                          _pl(2, Team.HOME, 30.0, 10.0)],
                            ball=Ball(x=25.0, y=10.0, confidence=1.0)))
        t += 1
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 25.0, 10.0),
                                          _pl(2, Team.HOME, 30.0, 10.0)],
                            ball=Ball(x=30.0, y=10.0, confidence=1.0)))
        t += 1
        for i in range(7):
            frames.append(Frame(t=t, players=[_pl(2, Team.HOME, 33.0, 10.0)],
                                ball=Ball(x=34.0 + i, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(20):
            frames.append(Frame(t=t, players=[], ball=Ball(x=20.0, y=10.0,
                                                          confidence=1.0)))
            t += 1
    net = assist_network(Match(_meta(), frames))["home"]
    assert net["pairs"] and net["pairs"][0]["from"] == 1
    assert net["pairs"][0]["to"] == 2 and net["pairs"][0]["goals"] == 2
    assert net["leaders"][0]["player_id"] == 1 and net["leaders"][0]["assists"] == 2
