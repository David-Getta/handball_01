"""
Tesztek a sprint-elemzésre / terhelés-monitorra (stats.py).

Futtatás:
    python tests/test_sprint_stats.py
"""

from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.stats import compute_player_stats


def _match(positions, fps=25.0):
    """Egyetlen játékos adott (x, y) pozíciósorából épít meccset (t=0,1,2...)."""
    frames = [
        Frame(t=i, players=[
            PlayerPosition(track_id=1, team=Team.HOME, x=float(x), y=float(y)),
        ])
        for i, (x, y) in enumerate(positions)
    ]
    return Match(
        meta=MatchMeta(match_id="t", home_team="H", away_team="A", fps=fps),
        frames=frames)


def test_sprint_detected_and_counted():
    """Tartósan gyors mozgás = 1 sprint; a csúcssebesség reális marad."""
    # 25 fps: 0,28 m/kocka = 7 m/s — 30 kockán át (1,2 mp) sprintel,
    # előtte-utána áll (0 m/s).
    pos = [(0.0, 5.0)] * 10
    x = 0.0
    for _ in range(30):
        x += 0.28
        pos.append((x, 5.0))
    pos += [(x, 5.0)] * 10
    stats = compute_player_stats(_match(pos))[1]
    assert stats.sprint_count == 1, f"1 sprintet vartunk, lett: {stats.sprint_count}"
    assert 6.0 <= stats.top_speed_ms <= 7.5, f"csucssebesseg: {stats.top_speed_ms}"
    assert stats.sprint_distance_m > 5.0
    assert stats.zone_seconds["sprint"] > 0.8
    print("OK: sprint felismerve, csucssebesseg realis")


def test_short_burst_is_not_a_sprint():
    """Egy-két kockányi gyors mozgás (zaj) nem számít sprintnek."""
    # 3 kockányi (0,12 mp) gyors mozgás — a minimum 0,5 mp alatt van.
    pos = [(0.0, 5.0)] * 10
    x = 0.0
    for _ in range(3):
        x += 0.28
        pos.append((x, 5.0))
    pos += [(x, 5.0)] * 10
    stats = compute_player_stats(_match(pos))[1]
    assert stats.sprint_count == 0, f"0 sprintet vartunk, lett: {stats.sprint_count}"
    print("OK: rovid loketeket nem szamoljuk sprintnek")


def test_tracking_glitch_ignored():
    """Egyetlen óriási ugrás (követési hiba) nem ad fals csúcssebességet."""
    # Álló játékos, egy kockára 8 métert "ugrik" (200 m/s) — hibás mérés.
    pos = [(10.0, 5.0)] * 10 + [(18.0, 5.0)] + [(10.0, 5.0)] * 10
    stats = compute_player_stats(_match(pos))[1]
    assert stats.top_speed_ms < 5.0, f"a glitch beszamitodott: {stats.top_speed_ms}"
    assert stats.sprint_count == 0
    print("OK: koveteshiba kiszurve")


def test_zones_sum_to_moving_time():
    """A zóna-idők összege a mozgással lefedett időt adja ki (kb.)."""
    # 100 kocka egyenletes kocogás: 0,08 m/kocka = 2 m/s.
    pos = [(i * 0.08, 5.0) for i in range(100)]
    stats = compute_player_stats(_match(pos))[1]
    total = sum(stats.zone_seconds.values())
    # 99 szakasz x 0,04 mp = 3,96 mp
    assert abs(total - 3.96) < 0.1, f"zonaido-osszeg: {total}"
    assert stats.zone_seconds["kocogas"] > 3.5
    print("OK: zonaidok konzisztensek")


def test_estimated_positions_do_not_sprint():
    """A BECSÜLT pozíciók nem szólnak bele a sprint-statisztikába."""
    frames = []
    x = 0.0
    for i in range(40):
        x += 0.30  # gyors "mozgás", de becsült forrásból
        frames.append(Frame(t=i, players=[
            PlayerPosition(track_id=1, team=Team.HOME, x=x, y=5.0,
                           source=PositionSource.ESTIMATED),
        ]))
    m = Match(meta=MatchMeta(match_id="t", home_team="H", away_team="A",
                             fps=25.0), frames=frames)
    stats = compute_player_stats(m)[1]
    assert stats.sprint_count == 0 and stats.top_speed_ms == 0.0
    print("OK: becsult mozgas nem sprint")


if __name__ == "__main__":
    test_sprint_detected_and_counted()
    test_short_burst_is_not_a_sprint()
    test_tracking_glitch_ignored()
    test_zones_sum_to_moving_time()
    test_estimated_positions_do_not_sprint()
    print("Minden sprint-statisztika teszt OK.")
