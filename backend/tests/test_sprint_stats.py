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


def test_aggregate_by_jersey_merges_broken_tracks():
    """Azonos (csapat, mezszám) trackek egy játékossá olvadnak össze."""
    from handball.pipeline.stats import PlayerStats, aggregate_by_jersey
    stats = {
        1: PlayerStats(track_id=1, distance_m=100.0, top_speed_ms=6.0,
                       sprint_count=2, sprint_distance_m=20.0,
                       measured_frames=250,
                       zone_seconds={"seta": 5.0, "futas": 3.0}),
        2: PlayerStats(track_id=2, distance_m=50.0, top_speed_ms=7.5,
                       sprint_count=1, sprint_distance_m=10.0,
                       measured_frames=250,
                       zone_seconds={"seta": 2.0, "sprint": 1.0}),
        3: PlayerStats(track_id=3, distance_m=80.0, top_speed_ms=5.0,
                       measured_frames=100),
    }
    team_of = {1: "home", 2: "home", 3: "away"}
    jersey_of = {1: 23, 2: 23}  # a 3-asnak nincs száma — külön sor marad
    rows = aggregate_by_jersey(stats, team_of, jersey_of, fps=25.0)
    assert len(rows) == 2
    merged = next(r for r in rows if r["jersey"] == 23)
    assert merged["track_ids"] == [1, 2]
    assert merged["distance_m"] == 150.0
    assert merged["top_speed_ms"] == 7.5  # maximum, nem összeg
    assert merged["sprint_count"] == 3
    # Átlagsebesség az összevont adatból: 150 m / (500 kocka / 25 fps) = 7.5.
    assert abs(merged["avg_speed_ms"] - 7.5) < 0.01
    assert merged["zone_seconds"]["seta"] == 7.0
    solo = next(r for r in rows if r["jersey"] is None)
    assert solo["label"] == "id 3" and solo["distance_m"] == 80.0


def test_aggregate_same_jersey_different_teams_stay_separate():
    """A 23-as hazai és a 23-as vendég NEM ugyanaz a játékos."""
    from handball.pipeline.stats import PlayerStats, aggregate_by_jersey
    stats = {
        1: PlayerStats(track_id=1, distance_m=10.0, measured_frames=25),
        2: PlayerStats(track_id=2, distance_m=20.0, measured_frames=25),
    }
    rows = aggregate_by_jersey(stats, {1: "home", 2: "away"},
                               {1: 23, 2: 23}, fps=25.0)
    assert len(rows) == 2


def test_rotation_depth_counts_used_and_regulars():
    """A rotáció-mélység a jelenlét-arányból számol: a végig pályán
    lévő alapember, a fél-időt játszó bevetett, a beugró (10% alatt)
    és a kapus nem számít."""
    from handball.pipeline.stats import rotation_depth

    total = 200
    frames = []
    for t in range(total):
        players = [
            PlayerPosition(track_id=1, team=Team.HOME, x=20.0, y=5.0),
            PlayerPosition(track_id=99, team=Team.HOME, x=1.0, y=10.0,
                           role="kapus"),
        ]
        if t < 60:  # a 2-es a meccs 30%-án van a pályán → bevetett
            players.append(PlayerPosition(track_id=2, team=Team.HOME,
                                          x=22.0, y=8.0))
        if t < 10:  # a 3-as csak beugró (5%) → nem számít
            players.append(PlayerPosition(track_id=3, team=Team.HOME,
                                          x=24.0, y=12.0))
        frames.append(Frame(t=t, players=players))
    m = Match(meta=MatchMeta(match_id="r", home_team="H",
                             away_team="A", fps=25.0), frames=frames)
    rec = rotation_depth(m)["home"]
    assert rec["used"] == 2          # 1-es + 2-es (kapus és beugró nem)
    assert rec["regulars"] == 1      # csak az 1-es alapember
    labels = [p["label"] for p in rec["players"]]
    assert len(labels) == 2
    assert rec["players"][0]["share_pct"] == 100.0
