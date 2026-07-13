"""
Tesztek a pozíció-prior alapú kapus-azonosításra (goalkeeper.py).

Futtatás:
    python -m pytest tests/test_goalkeeper.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.goalkeeper import ROLE_GOALKEEPER, detect_goalkeepers


def _match(frames, fps=25.0):
    return Match(meta=MatchMeta(match_id="gk", home_team="H", away_team="A",
                                fps=fps), frames=frames)


def _stay(track_id, team, x, y, n, jitter=0.0):
    """Egy helyben (kis mozgással) tartózkodó játékos n kockán át."""
    out = []
    for t in range(n):
        dx = jitter * ((t % 3) - 1)
        out.append((t, PlayerPosition(track_id=track_id, team=team,
                                      x=x + dx, y=y + dx)))
    return out


def _frames(*walks, n):
    by_t: dict = {}
    for walk in walks:
        for (t, p) in walk:
            by_t.setdefault(t, []).append(p)
    return [Frame(t=t, players=by_t.get(t, [])) for t in range(n)]


def test_marks_both_goalkeepers():
    """A két kapuelőtérben álló track kapus lesz, a mezőny nem."""
    n = 300  # 12 mp @ 25 fps
    gk_home = _stay(1, Team.HOME, 1.5, 10.0, n, jitter=0.3)
    gk_away = _stay(2, Team.AWAY, 38.5, 10.0, n, jitter=0.3)
    mid = _stay(3, Team.HOME, 20.0, 10.0, n, jitter=0.5)
    m = _match(_frames(gk_home, gk_away, mid, n=n))
    marked = detect_goalkeepers(m)
    assert set(marked) == {1, 2}
    for share in marked.values():
        assert share > 0.9
    roles = {p.track_id: p.role for f in m.frames for p in f.players}
    assert roles[1] == ROLE_GOALKEEPER and roles[2] == ROLE_GOALKEEPER
    assert roles[3] is None


def test_one_goalkeeper_per_goal():
    """Két track ugyanannál a kapunál: csak a nagyobb hányadú lesz kapus
    (a másik pl. beálló/védő, aki sokat jár arra)."""
    n = 300
    gk = _stay(1, Team.HOME, 1.5, 10.0, n)
    # A 2-es track ideje felében a kapuelőtérben, felében kint.
    near = (_stay(2, Team.HOME, 4.0, 10.0, n // 2)
            + [(t + n // 2, p) for (t, p) in
               _stay(2, Team.HOME, 15.0, 10.0, n - n // 2)])
    m = _match(_frames(gk, near, n=n))
    marked = detect_goalkeepers(m)
    assert set(marked) == {1}


def test_short_or_transient_tracks_not_marked():
    """Rövid minta (< min mp) vagy alacsony kapuelőtér-hányad → nem kapus."""
    n = 300
    short = _stay(1, Team.HOME, 1.5, 10.0, 50)  # csak 2 mp
    visitor = (_stay(2, Team.AWAY, 38.5, 10.0, 90)  # 30% bent...
               + [(t + 90, p) for (t, p) in
                  _stay(2, Team.AWAY, 25.0, 10.0, 210)])  # ...70% kint
    m = _match(_frames(short, visitor, n=n))
    assert detect_goalkeepers(m) == {}
    roles = {p.role for f in m.frames for p in f.players}
    assert roles == {None}


def test_estimated_positions_ignored():
    """A BECSÜLT pozíciók nem számítanak bele a kapus-döntésbe."""
    n = 300
    est = []
    for t in range(n):
        est.append((t, PlayerPosition(track_id=1, team=Team.HOME, x=1.5,
                                      y=10.0, source=PositionSource.ESTIMATED)))
    m = _match(_frames(est, n=n))
    assert detect_goalkeepers(m) == {}


def _shot_sequence(t0, gk_track, save=True):
    """Vendég kapu (x=40) felé tartó hazai lövés kockái t0-tól: a kapus a
    kapuban áll; védésnél a labda nála áll meg, gólnál eléri a vonalat."""
    from handball.models.tracking import Ball
    frames = []
    gk = PlayerPosition(track_id=gk_track, team=Team.AWAY, x=39.0, y=10.0,
                        source=PositionSource.MEASURED, confidence=1.0,
                        role="kapus")
    shooter = PlayerPosition(track_id=4, team=Team.HOME, x=33.5, y=10.0,
                             source=PositionSource.MEASURED, confidence=1.0)
    for i in range(8):
        x = 33.6 + i
        if save:
            x = min(x, 38.8)  # a kapusnál megáll
        players = [gk] + ([shooter] if i == 0 else [])
        frames.append(Frame(t=t0 + i, players=players,
                            ball=Ball(x=x, y=10.0, confidence=1.0)))
    return frames


def test_goalkeeper_stats_counts_saves_and_conceded():
    from handball.pipeline.goalkeeper import goalkeeper_stats
    # Két lövés: egy védés + egy gól, közte a labda visszamegy középre
    # (a debounce miatt külön kapu-megközelítés kell).
    from handball.models.tracking import Ball
    frames = _shot_sequence(0, gk_track=9, save=True)
    frames.append(Frame(t=8, players=[], ball=Ball(x=20.0, y=10.0,
                                                   confidence=1.0)))
    frames += _shot_sequence(9, gk_track=9, save=False)
    m = _match(frames)
    stats = goalkeeper_stats(m)
    away = stats["away"]
    assert away["track_id"] == 9
    assert away["on_target"] == 2
    assert away["saves"] == 1 and away["conceded"] == 1
    assert away["save_pct"] == 50.0
    assert sum(away["conceded_zones"].values()) == 1


def test_goalkeeper_stats_empty_without_role():
    from handball.pipeline.goalkeeper import goalkeeper_stats
    m = _match(_frames(_stay(1, Team.HOME, 20.0, 10.0, 100), n=100))
    assert goalkeeper_stats(m) == {}


def _empty_net_match(gk_far=True, seconds=5, poss_own=True):
    """HAZAI támadás a labdával; a hazai kapus vagy elöl (7a6), vagy otthon."""
    from handball.models.tracking import Ball
    n = int(seconds * 25)
    frames = []
    for t in range(n):
        gk_x = 20.0 if gk_far else 1.5  # elöl játszik vs a kapujában áll
        players = [
            PlayerPosition(track_id=1, team=Team.HOME, x=gk_x, y=10.0,
                           source=PositionSource.MEASURED, confidence=1.0,
                           role="kapus"),
            PlayerPosition(track_id=2, team=Team.HOME, x=30.0, y=10.0,
                           source=PositionSource.MEASURED, confidence=1.0),
            PlayerPosition(track_id=3, team=Team.AWAY, x=35.0, y=8.0,
                           source=PositionSource.MEASURED, confidence=1.0),
        ]
        # A labda a hazai (2-es) vagy a vendég (3-as) játékosnál.
        bx, by = (30.0, 10.0) if poss_own else (35.0, 8.0)
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=bx, y=by, confidence=1.0)))
    return _match(frames)


def test_empty_net_detected_when_gk_upfield():
    from handball.pipeline.goalkeeper import detect_empty_net
    windows = detect_empty_net(_empty_net_match(gk_far=True, seconds=5))
    assert len(windows) == 1
    w = windows[0]
    assert w["team"] == "home"
    assert w["duration_s"] >= 4.5


def test_no_empty_net_when_gk_home_or_defending():
    from handball.pipeline.goalkeeper import detect_empty_net
    # A kapus a kapujában → nincs 7a6.
    assert detect_empty_net(_empty_net_match(gk_far=False)) == []
    # A kapus elöl, de az ELLENFÉL birtokol (pl. lerohanás ellenük) → nem 7a6.
    assert detect_empty_net(_empty_net_match(gk_far=True, poss_own=False)) == []


def test_short_burst_filtered():
    from handball.pipeline.goalkeeper import detect_empty_net
    # 2 mp-es szakasz a 3 mp-es küszöb alatt marad.
    assert detect_empty_net(_empty_net_match(gk_far=True, seconds=2)) == []
