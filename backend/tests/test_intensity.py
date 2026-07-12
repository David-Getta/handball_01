"""
Tesztek az intenzitás-idővonalra (compute_intensity_timeline).

Futtatás:
    python -m pytest tests/test_intensity.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.stats import compute_intensity_timeline


def _match(frames, fps=25.0):
    return Match(
        meta=MatchMeta(match_id="t", home_team="H", away_team="A", fps=fps),
        frames=frames)


def _walking_then_standing(n1=500, n2=500, speed=2.0, fps=25.0):
    """Egy hazai játékos: az első szakaszban egyenletesen mozog, a
    másodikban áll — a tempónak vissza kell esnie."""
    frames = []
    x = 0.0
    for i in range(n1 + n2):
        if i < n1:
            x += speed / fps
        frames.append(Frame(t=i, players=[
            PlayerPosition(track_id=1, team=Team.HOME, x=min(x, 39.0), y=5.0),
        ]))
    return frames


def test_intensity_drops_when_player_stops():
    m = _match(_walking_then_standing())
    win = compute_intensity_timeline(m)
    assert len(win) >= 4
    # Az első ablakban ~2 m/s, az utolsóban ~0.
    assert abs(win[0]["home_avg_ms"] - 2.0) < 0.2
    assert win[-1]["home_avg_ms"] < 0.2
    # A vendégeknek nincs mérésük → 0.
    assert all(w["away_avg_ms"] == 0.0 for w in win)


def test_short_recording_shrinks_window():
    """Rövid felvételnél is legyen több pont (az ablak zsugorodik)."""
    m = _match(_walking_then_standing(n1=250, n2=250))  # 20 mp összesen
    win = compute_intensity_timeline(m, window_s=300.0)
    assert len(win) >= 4


def test_estimated_positions_ignored():
    frames = []
    x = 0.0
    for i in range(300):
        x += 0.1
        frames.append(Frame(t=i, players=[
            PlayerPosition(track_id=1, team=Team.HOME, x=x, y=5.0,
                           source=PositionSource.ESTIMATED),
        ]))
    win = compute_intensity_timeline(_match(frames))
    assert all(w["home_avg_ms"] == 0.0 for w in win)


def test_empty_match_gives_empty_list():
    assert compute_intensity_timeline(_match([])) == []


if __name__ == "__main__":
    test_intensity_drops_when_player_stops()
    test_short_recording_shrinks_window()
    test_estimated_positions_ignored()
    test_empty_match_gives_empty_list()
    print("Minden intenzitás-teszt OK.")
