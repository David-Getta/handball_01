"""
Tesztek a minőség-jelentésre (quality.py).

Futtatás:
    python tests/test_quality.py
"""

from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, Ball, PositionSource, Team,
)
from handball.pipeline.quality import compute_quality_report


def _meta(fps=25.0):
    return MatchMeta(match_id="q", home_team="A", away_team="B", fps=fps,
                     frame_width=1920, frame_height=1080)


def _pl(i, source=PositionSource.MEASURED):
    return PlayerPosition(track_id=i, team=Team.HOME, x=20.0, y=10.0,
                          source=source, confidence=1.0)


def test_full_coverage_high_score():
    """Teljes lefedettség (14 mért játékos + labda minden kockán): magas pontszám."""
    frames = [Frame(t=t, players=[_pl(i) for i in range(14)],
                    ball=Ball(x=20.0, y=10.0, confidence=1.0)) for t in range(20)]
    r = compute_quality_report(Match(_meta(), frames))
    assert r["score"] >= 90
    assert r["warnings"] == []
    assert r["ball_coverage_pct"] == 100.0
    assert r["avg_measured_players"] == 14.0


def test_no_ball_warning_and_lower_score():
    """Labda nélkül: figyelmeztetés + alacsonyabb pontszám."""
    frames = [Frame(t=t, players=[_pl(i) for i in range(14)], ball=None)
              for t in range(20)]
    r = compute_quality_report(Match(_meta(), frames))
    assert r["ball_coverage_pct"] == 0.0
    assert any("labda" in w.lower() for w in r["warnings"])
    assert r["score"] <= 65


def test_few_players_warning():
    """Kevés látott játékos: kalibrációra utaló figyelmeztetés."""
    frames = [Frame(t=t, players=[_pl(1), _pl(2)],
                    ball=Ball(x=20.0, y=10.0, confidence=1.0)) for t in range(10)]
    r = compute_quality_report(Match(_meta(), frames))
    assert any("kalibráció" in w.lower() for w in r["warnings"])


def test_estimated_ratio_counted():
    """A becsült pozíciók aránya megjelenik, és sok becsültnél figyelmeztet."""
    players = [_pl(i) for i in range(6)] + \
              [_pl(10 + i, PositionSource.ESTIMATED) for i in range(8)]
    frames = [Frame(t=t, players=list(players),
                    ball=Ball(x=20.0, y=10.0, confidence=1.0)) for t in range(10)]
    r = compute_quality_report(Match(_meta(), frames))
    assert abs(r["estimated_ratio_pct"] - 100.0 * 8 / 14) < 0.5
    assert any("becsült" in w.lower() for w in r["warnings"])


def test_longest_ball_gap_seconds():
    """A leghosszabb labda-hézag másodpercben, fps-sel átváltva."""
    frames = []
    for t in range(50):
        ball = None if 10 <= t < 40 else Ball(x=20.0, y=10.0, confidence=1.0)
        frames.append(Frame(t=t, players=[_pl(i) for i in range(14)], ball=ball))
    r = compute_quality_report(Match(_meta(fps=5.0), frames))
    assert abs(r["longest_ball_gap_s"] - 6.0) < 1e-9  # 30 kocka / 5 fps
    assert any("kiesés" in w.lower() for w in r["warnings"])


def test_empty_match():
    """Üres meccs: 0 pont + magyarázó figyelmeztetés (nem hibázik)."""
    r = compute_quality_report(Match(_meta(), []))
    assert r["score"] == 0 and r["frames"] == 0
    assert r["warnings"]


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
