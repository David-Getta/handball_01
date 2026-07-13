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
