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


def test_trend_uses_explicit_half_boundary():
    """Aszimmetrikus félidők: a határ a 300. kockánál van (nem a
    felezőponton) — a half_t paraméterrel a mérés pontos marad."""
    m = _match(_fast_then_slow(n1=300, n2=700, v1=4.0, v2=1.0))
    tr = intensity_trend(m, half_t=300)
    assert tr["midpoint_frame"] == 300
    assert abs(tr["home"]["first_ms"] - 4.0) < 0.3
    assert abs(tr["home"]["second_ms"] - 1.0) < 0.3
    assert tr["home"]["drop_pct"] > 60.0


def test_trend_empty_or_short_match_is_zero():
    tr = intensity_trend(_match([]))
    assert tr["home"]["drop_pct"] == 0.0
    assert tr["away"]["second_ms"] == 0.0


def test_player_fatigue_ranks_faders():
    """Két játékos: az 1-es a 2. félidőre lelassul (4→1 m/s), a 2-es
    végig egyenletes — az 1-es vezeti a fáradás-listát."""
    from handball.pipeline.stats import player_fatigue
    frames = []
    x1, d1 = 5.0, 1.0
    x2, d2 = 5.0, 1.0
    n = 2000  # 80 mp @ 25 fps
    for i in range(n):
        v1 = 4.0 if i < n // 2 else 1.0
        x1 += d1 * v1 / 25.0
        if x1 >= 35.0:
            x1, d1 = 35.0, -1.0
        elif x1 <= 5.0:
            x1, d1 = 5.0, 1.0
        x2 += d2 * 3.0 / 25.0
        if x2 >= 35.0:
            x2, d2 = 35.0, -1.0
        elif x2 <= 5.0:
            x2, d2 = 5.0, 1.0
        frames.append(Frame(t=i, players=[
            PlayerPosition(track_id=1, team=Team.HOME, x=x1, y=5.0),
            PlayerPosition(track_id=2, team=Team.HOME, x=x2, y=10.0),
        ]))
    rows = player_fatigue(_match(frames), half_t=n // 2)
    assert rows and rows[0]["track_id"] == 1
    assert rows[0]["drop_pct"] > 60.0
    steady = next(r for r in rows if r["track_id"] == 2)
    assert abs(steady["drop_pct"]) < 5.0


if __name__ == "__main__":
    test_trend_detects_second_half_drop()
    test_trend_flat_when_constant_speed()
    test_trend_empty_or_short_match_is_zero()
    print("Minden kondíció-teszt OK.")
