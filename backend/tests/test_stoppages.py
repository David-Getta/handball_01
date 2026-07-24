"""
Tesztek a játékmegszakítás/időkérés-felismerésre (stoppages.py).

Futtatás:
    python -m pytest tests/test_stoppages.py
"""

from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.stoppages import detect_stoppages


def _meta(fps=25.0):
    return MatchMeta(match_id="st", home_team="H", away_team="A", fps=fps)


def _players(t, moving):
    """8 játékos (4-4): mozgásban körpályán, álláskor fix helyen."""
    out = []
    for k in range(8):
        team = Team.HOME if k < 4 else Team.AWAY
        bx, by = 12.0 + 2.0 * k, 6.0 + (k % 4) * 2.5
        if moving:
            bx += 2.0 * math.sin(t / 5.0 + k)
            by += 1.5 * math.cos(t / 4.0 + k)
        out.append(PlayerPosition(track_id=k + 1, team=team, x=bx, y=by,
                                  source=PositionSource.MEASURED,
                                  confidence=1.0))
    return out


def _match(move1_s=20, stop_s=25, move2_s=20, fps=25.0, holder_team=Team.HOME):
    """Mozgás → állás → mozgás; az állás előtt a labda a holder_team-nél."""
    frames = []
    t = 0
    for _ in range(int(move1_s * fps)):
        players = _players(t, moving=True)
        # A labda a leállás előtt a hazai 1-es (vagy vendég 5-ös) kezében.
        hid = 1 if holder_team == Team.HOME else 5
        hp = players[hid - 1]
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=hp.x, y=hp.y, confidence=1.0)))
        t += 1
    for _ in range(int(stop_s * fps)):
        frames.append(Frame(t=t, players=_players(0, moving=False),
                            ball=None))
        t += 1
    for _ in range(int(move2_s * fps)):
        frames.append(Frame(t=t, players=_players(t, moving=True),
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    return Match(_meta(fps), frames)


def test_timeout_detected_with_likely_team():
    stops = detect_stoppages(_match())
    assert len(stops) == 1
    s = stops[0]
    assert s["kind"] == "időkérés"
    assert 20.0 <= s["duration_s"] <= 30.0
    assert s["likely_team"] == "home"  # a leállás előtt a hazai birtokolt


def test_no_stoppage_during_normal_play():
    stops = detect_stoppages(_match(stop_s=0))
    assert stops == []


def test_short_stop_ignored():
    """Egy rövid (5 mp) állás — pl. szabaddobás — nem megszakítás."""
    assert detect_stoppages(_match(stop_s=5)) == []


def test_long_stop_is_not_timeout():
    """A 2 percnél hosszabb leállás nem időkérés (sérülés/félidő)."""
    stops = detect_stoppages(_match(stop_s=130))
    assert len(stops) == 1
    assert stops[0]["kind"] == "hosszú megszakítás"


def test_empty_frames_are_not_stoppage():
    """Üres (követés-vesztett) képkockák nem számítanak leállásnak."""
    frames = [Frame(t=t, players=[], ball=None) for t in range(1000)]
    assert detect_stoppages(Match(_meta(), frames)) == []


# ---- Időkérés-hatás (megtörte-e a sorozatot) ---------------------------------

from handball.pipeline.stoppages import timeout_effects


def _goal_frames(t0, toward_home_goal):
    """Gól-kockák: a labda a kapuba száguld (8 játékos áll a pályán, hogy a
    leállás-jel ne zavarodjon össze — ők mozognak közben)."""
    frames = []
    for i in range(7):
        x = (6.4 - i) if toward_home_goal else (34.0 + i)
        frames.append(Frame(t=t0 + i, players=_players(t0 + i, moving=True),
                            ball=Ball(x=max(0.0, min(40.0, x)), y=10.0,
                                      confidence=1.0)))
    return frames


def test_timeout_that_breaks_the_run():
    """A hazai 2 gólt kap → időkérés → utána nincs kapott gól → "megtörte"."""
    fps = 25.0
    frames = []
    t = 0
    # Mozgás + 2 vendég-gól (a -x kapura → a HAZAI kapja).
    for _ in range(int(20 * fps)):
        players = _players(t, moving=True)
        hp = players[0]  # a hazai 1-es birtokol (ő "kéri" majd az időt)
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=hp.x, y=hp.y, confidence=1.0)))
        t += 1
    for g in _goal_frames(t, toward_home_goal=True):
        frames.append(g)
    t = frames[-1].t + 1
    for _ in range(int(3 * fps)):  # kis szünet a két gól közt (debounce)
        players = _players(t, moving=True)
        hp = players[0]
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=hp.x, y=hp.y, confidence=1.0)))
        t += 1
    for g in _goal_frames(t, toward_home_goal=True):
        frames.append(g)
    t = frames[-1].t + 1
    # A hazai birtokol pár mp-ig, majd időkérés (20 mp állás).
    for _ in range(int(4 * fps)):
        players = _players(t, moving=True)
        hp = players[0]
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=hp.x, y=hp.y, confidence=1.0)))
        t += 1
    for _ in range(int(20 * fps)):
        frames.append(Frame(t=t, players=_players(0, moving=False), ball=None))
        t += 1
    # Utána mozgás, kapott gól nélkül.
    for _ in range(int(30 * fps)):
        frames.append(Frame(t=t, players=_players(t, moving=True),
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1

    effects = [e for e in timeout_effects(Match(_meta(fps), frames))
               if e["kind"] == "időkérés"]
    assert len(effects) == 1
    e = effects[0]
    assert e["likely_team"] == "home"
    assert e["conceded_before"] == 2 and e["conceded_after"] == 0
    assert e["verdict"] == "megtörte a sorozatot"


def test_timeout_without_prior_run_has_no_verdict():
    """Ha az időkérés előtt nem volt kapott gól-sorozat, nincs ítélet."""
    effects = [e for e in timeout_effects(_match())
               if e["kind"] == "időkérés"]
    assert len(effects) == 1
    assert effects[0]["verdict"] is None
    assert effects[0]["conceded_before"] == 0


def test_timeout_record_aggregates_verdicts():
    """A "megtörte" ítéletű hazai időkérés a hazai mérlegben broke-ként
    jelenik meg; a vendégnek nincs időkérése."""
    from handball.pipeline.stoppages import timeout_record

    fps = 25.0
    frames = []
    t = 0
    for _ in range(int(20 * fps)):
        players = _players(t, moving=True)
        hp = players[0]
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=hp.x, y=hp.y, confidence=1.0)))
        t += 1
    for g in _goal_frames(t, toward_home_goal=True):
        frames.append(g)
    t = frames[-1].t + 1
    for _ in range(int(3 * fps)):
        players = _players(t, moving=True)
        hp = players[0]
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=hp.x, y=hp.y, confidence=1.0)))
        t += 1
    for g in _goal_frames(t, toward_home_goal=True):
        frames.append(g)
    t = frames[-1].t + 1
    for _ in range(int(4 * fps)):
        players = _players(t, moving=True)
        hp = players[0]
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=hp.x, y=hp.y, confidence=1.0)))
        t += 1
    for _ in range(int(20 * fps)):
        frames.append(Frame(t=t, players=_players(0, moving=False),
                            ball=None))
        t += 1
    for _ in range(int(30 * fps)):
        frames.append(Frame(t=t, players=_players(t, moving=True),
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1

    rec = timeout_record(Match(_meta(fps), frames))
    assert rec["home"]["timeouts"] == 1
    assert rec["home"]["broke"] == 1 and rec["home"]["failed"] == 0
    assert rec["away"]["timeouts"] == 0
