"""
Tesztek a kondíció-mutatóra (intensity_trend): első vs második félidő tempó.

Futtatás:
    python -m pytest tests/test_intensity_trend.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, Team,
)
from handball.pipeline.stats import intensity_trend


def _match(frames, fps=25.0):
    return Match(
        meta=MatchMeta(match_id="t", home_team="H", away_team="A", fps=fps),
        frames=frames)


def _fast_then_slow(n1=500, n2=500, v1=4.0, v2=1.0, fps=25.0):
    """Hazai játékos: az első félidőben gyors, a másodikban lassú.
    A pályán belül maradva ide-oda mozog (háromszög-hullám 5..35 m)."""
    frames = []
    x, direction = 5.0, 1.0
    for i in range(n1 + n2):
        v = v1 if i < n1 else v2
        x += direction * v / fps
        if x >= 35.0:
            x, direction = 35.0, -1.0
        elif x <= 5.0:
            x, direction = 5.0, 1.0
        frames.append(Frame(t=i, players=[
            PlayerPosition(track_id=1, team=Team.HOME, x=x, y=5.0),
        ]))
    return frames


def test_trend_detects_second_half_drop():
    m = _match(_fast_then_slow())
    tr = intensity_trend(m)
    assert tr["home"]["first_ms"] > tr["home"]["second_ms"]
    # ~4 m/s -> ~1 m/s ≈ 75% esés.
    assert tr["home"]["drop_pct"] > 50.0
    assert tr["midpoint_frame"] == 1000 // 2


def test_trend_flat_when_constant_speed():
    m = _match(_fast_then_slow(v1=3.0, v2=3.0))
    tr = intensity_trend(m)
    assert abs(tr["home"]["drop_pct"]) < 5.0


def test_trend_empty_or_short_match_is_zero():
    tr = intensity_trend(_match([]))
    assert tr["home"]["drop_pct"] == 0.0
    assert tr["away"]["second_ms"] == 0.0


if __name__ == "__main__":
    test_trend_detects_second_half_drop()
    test_trend_flat_when_constant_speed()
    test_trend_empty_or_short_match_is_zero()
    print("Minden kondíció-teszt OK.")
