"""
Tesztek a csere-felismerésre (substitutions.py).

A pálya 40x20 m; a cserezóna a felezővonal ±4,5 m-e az oldalvonal mellett.

Futtatás:
    python -m pytest tests/test_substitutions.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.substitutions import (
    detect_substitutions, substitution_impact,
)


def _meta(fps=25.0):
    return MatchMeta(match_id="sub", home_team="H", away_team="A", fps=fps)


def _pl(track_id, team, x, y, role=None):
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0,
                          role=role)


def _sub_match(out_end=(20.0, 1.0), in_start=(20.0, 1.0)):
    """Az 5-ös hazai track a cserezónában ér véget (t=200), a 6-os ott
    kezdődik (t=210) — közben egy állandó játékos végig a pályán van."""
    frames = []
    for t in range(600):
        players = [_pl(1, Team.HOME, 25.0, 10.0)]  # állandó játékos
        if t <= 200:
            # Az 5-ös a pálya közepéről a cserezóna felé tart, ott tűnik el.
            frac = t / 200.0
            x = 28.0 + (out_end[0] - 28.0) * frac
            y = 8.0 + (out_end[1] - 8.0) * frac
            players.append(_pl(5, Team.HOME, x, y))
        if t >= 210:
            # A 6-os a cserezónában jelenik meg, majd beáll a helyére.
            frac = min(1.0, (t - 210) / 100.0)
            x = in_start[0] + (30.0 - in_start[0]) * frac
            y = in_start[1] + (12.0 - in_start[1]) * frac
            players.append(_pl(6, Team.HOME, x, y))
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=22.0, y=10.0, confidence=1.0)))
    return Match(_meta(), frames)


def test_substitution_detected_at_zone():
    subs = detect_substitutions(_sub_match())
    assert len(subs) == 1
    ev = subs[0]
    assert ev["team"] == "home"
    assert ev["out_ids"] == [5] and ev["in_ids"] == [6]
    assert abs(ev["t"] - 200) <= 2


def test_mid_court_track_break_is_not_substitution():
    """A pálya közepén megszakadó követés (takarás) nem csere."""
    m = _sub_match(out_end=(28.0, 10.0), in_start=(30.0, 12.0))
    assert detect_substitutions(m) == []


def test_impact_counts_goals_after():
    """A csere utáni ablakban esett gól a mérlegbe kerül."""
    m = _sub_match()
    # Hazai gól a csere után (t≈300): a labda a +x kapuba száguld.
    for i, f in enumerate(m.frames):
        if 300 <= f.t < 307:
            f.ball = Ball(x=34.0 + (f.t - 300), y=10.0, confidence=1.0)
    r = substitution_impact(m)
    assert r["teams"]["home"]["rotations"] == 1
    assert r["teams"]["home"]["goals_for_after"] == 1
    assert r["teams"]["home"]["goals_against_after"] == 0
    assert r["events"][0]["goals_for_after"] == 1


def test_late_sub_flags_fading_player_left_on_court():
    """A 2. félidőben 20%+ tempót eső, le nem cserélt játékos késő-csere
    jelzést kap; az egyenletes tempójú nem."""
    from handball.pipeline.substitutions import late_sub_flags

    frames = []
    n_half = 1000  # 40 mp félidőnként (25 fps)
    x1 = 5.0
    x3 = 5.0
    for t in range(2 * n_half):
        # 1-es: az első félidőben 2 m/s, a másodikban 1 m/s (esés 50%).
        v1 = 0.08 if t < n_half else 0.04
        x1 += v1
        if x1 > 35.0:
            x1 = 5.0
        # 3-as: végig 1,5 m/s (nincs érdemi esés).
        x3 += 0.06
        if x3 > 35.0:
            x3 = 5.0
        frames.append(Frame(t=t, players=[
            _pl(1, Team.HOME, x1, 8.0),
            _pl(3, Team.HOME, x3, 12.0),
        ]))
    flags = late_sub_flags(Match(_meta(), frames))
    ids = [f["track_id"] for f in flags]
    assert 1 in ids
    assert 3 not in ids
    top = next(f for f in flags if f["track_id"] == 1)
    assert top["drop_pct"] >= 20.0
