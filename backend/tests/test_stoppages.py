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


# ---- Időkérés-időzítés (hány kapott gól után fékeznek) -----------------------

def _timeout_match(counts, fps=25.0):
    """Hazai időkérés-sorozat: a `counts` elemenként megadja, hány
    vendég-gól (a hazai kapujába) előzi meg az adott időkérést."""
    frames = []
    t = 0

    def _play(seconds):
        """Hazai birtoklás — a leállás előtt ő "kéri" majd az időt."""
        nonlocal t, frames
        for _ in range(int(seconds * fps)):
            players = _players(t, moving=True)
            hp = players[0]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=hp.x, y=hp.y,
                                          confidence=1.0)))
            t += 1

    for n_goals in counts:
        _play(10)
        for _ in range(n_goals):
            for g in _goal_frames(t, toward_home_goal=True):
                frames.append(g)
            t = frames[-1].t + 1
            _play(3)          # debounce a gólok közt
        _play(4)
        for _ in range(int(20 * fps)):   # időkérés (20 mp állás)
            frames.append(Frame(t=t, players=_players(0, moving=False),
                                ball=None))
            t += 1
        # Hosszú játék a következő kör előtt: a 120 mp-es hatás-ablak
        # ne lásson át az előző kör góljaira.
        _play(130)
    return Match(_meta(fps), frames)


def test_timeout_timing_separates_early_and_late_brakes():
    """Két időkérés egy-egy kapott gól után → "gyors fék"; három, majd
    két kapott gól után → "hagyják elszaladni"; egyetlen időkérésnél
    nincs ítélet."""
    from handball.pipeline.stoppages import timeout_timing

    early = timeout_timing(_timeout_match([1, 1]))["home"]
    assert early["timeouts"] == 2
    assert early["sum_before"] == 2
    assert early["avg_before"] == 1.0
    assert early["verdict"] == "gyors fék"

    late = timeout_timing(_timeout_match([3, 2]))["home"]
    assert late["timeouts"] == 2 and late["sum_before"] == 5
    assert late["avg_before"] == 2.5
    assert late["verdict"] == "hagyják elszaladni"

    # Egyetlen időkérés: kevés minta → nincs arány és nincs ítélet.
    one = timeout_timing(_timeout_match([3]))["home"]
    assert one["avg_before"] is None and one["verdict"] is None
    # A vendég nem kért időt.
    assert timeout_timing(_timeout_match([1, 1]))["away"]["timeouts"] == 0


# ---- Effektív játékidő -------------------------------------------------------

def test_playing_time_profile_flags_the_broken_match():
    """11 perc játék, benne két hosszú (2×90 mp) megszakítás → az
    effektív arány 80% alatt: szakadozott meccskép."""
    from handball.pipeline.stoppages import playing_time_profile

    fps = 25.0
    frames = []
    t = 0

    def _play(seconds):
        nonlocal t, frames
        for _ in range(int(seconds * fps)):
            players = _players(t, moving=True)
            hp = players[0]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=hp.x, y=hp.y,
                                          confidence=1.0)))
            t += 1

    def _stop(seconds):
        nonlocal t, frames
        for _ in range(int(seconds * fps)):
            frames.append(Frame(t=t, players=_players(0, moving=False),
                                ball=None))
            t += 1

    _play(240)
    _stop(90)
    _play(180)
    _stop(90)
    _play(60)
    rec = playing_time_profile(Match(_meta(fps), frames))["home"]
    assert rec["stoppages"] == 2
    assert rec["stopped_s"] >= 175.0
    assert rec["effective_pct"] < 80.0
    assert rec["verdict"] == "szakadozott meccskép"
    # A megszakítások előtt a hazai birtokolt: nála állt meg a játék.
    assert rec["own_stoppages"] == 2


def test_playing_time_profile_flags_the_flowing_match():
    """Megszakítás nélküli 11 perc → folyamatos meccs."""
    from handball.pipeline.stoppages import playing_time_profile

    fps = 25.0
    frames = []
    for t in range(int(660 * fps)):
        players = _players(t, moving=True)
        hp = players[0]
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=hp.x, y=hp.y, confidence=1.0)))
    rec = playing_time_profile(Match(_meta(fps), frames))["home"]
    assert rec["stoppages"] == 0 and rec["effective_pct"] == 100.0
    assert rec["verdict"] == "folyamatos meccs"


def test_playing_time_profile_needs_enough_minutes():
    """Rövid (10 percnél kevesebb) felvételnél nincs ítélet."""
    from handball.pipeline.stoppages import playing_time_profile

    rec = playing_time_profile(_match())["home"]
    assert rec["verdict"] is None
