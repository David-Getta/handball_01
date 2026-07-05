"""
Tesztek a központi Tracking adatmodellre.

A legfontosabb, hogy a Match JSON-ra és vissza KÖRBE megy (round-trip) — ez a
backend és a Flutter-kliens közötti szerződés helyességét bizonyítja. Tiszta
stdlib-bel fut, nem kell külső csomag.

Futtatás:
    python -m pytest            (ha van pytest)
    python tests/test_tracking_model.py   (pytest nélkül is fut, lásd lent)
"""

from __future__ import annotations

# Hogy a teszt közvetlenül (python tests/test_tracking_model.py) is fusson, a
# backend/ mappát a kereső-útvonalra tesszük — így a `handball` csomag importálható
# akkor is, ha nem a backend/ a munkakönyvtár.
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, Ball, Team, PositionSource,
)
from handball.models.events import RosterTimeline, Suspension
from handball.pipeline.stats import compute_player_stats


def _sample_match() -> Match:
    """Minta-Match egy mérttel és egy becsült játékossal."""
    meta = MatchMeta(match_id="t1", home_team="A", away_team="B", fps=25.0)
    f0 = Frame(t=0, players=[
        PlayerPosition(track_id=1, team=Team.HOME, x=10.0, y=8.0, jersey_number=7),
    ], ball=Ball(x=11.0, y=10.0))
    f1 = Frame(t=1, players=[
        PlayerPosition(track_id=1, team=Team.HOME, x=13.0, y=12.0, jersey_number=7),
    ], ball=None)
    return Match(meta=meta, frames=[f0, f1])


def test_json_roundtrip():
    """A Match JSON-ba írva és visszaolvasva ugyanazt adja vissza."""
    match = _sample_match()
    text = match.to_json()
    restored = Match.from_json(text)

    assert restored.meta.match_id == "t1"
    assert restored.meta.fps == 25.0
    assert len(restored.frames) == 2
    p = restored.frames[0].players[0]
    assert p.track_id == 1
    assert p.team == Team.HOME                    # az Enum helyesen állt vissza
    assert p.source == PositionSource.MEASURED
    assert p.jersey_number == 7
    assert restored.frames[0].ball.x == 11.0
    assert restored.frames[1].ball is None        # a hiányzó labda None marad


def test_enums_serialize_as_strings():
    """Az Enumok olvasható szövegként kerülnek a JSON-ba (nem számként)."""
    match = _sample_match()
    d = match.to_dict()
    assert d["frames"][0]["players"][0]["team"] == "home"
    assert d["frames"][0]["players"][0]["source"] == "measured"


def test_distance_uses_only_measured():
    """A futott táv (3-4-5 háromszög) 5 m, és csak MÉRT pontokból számol."""
    match = _sample_match()
    stats = compute_player_stats(match)
    # (10,8) -> (13,12): dx=3, dy=4 -> táv = 5.0 m
    assert abs(stats[1].distance_m - 5.0) < 1e-9
    assert stats[1].measured_frames == 2
    assert stats[1].estimated_frames == 0


def test_roster_count_with_suspensions():
    """A létszám csökken a kiállítások alatt, de nem megy 5 alá."""
    roster = RosterTimeline(suspensions=[
        Suspension(team=Team.HOME, start_t=0, duration_t=100),
        Suspension(team=Team.HOME, start_t=0, duration_t=100),
    ])
    # 2 egyidejű kiállítás -> 7 - 2 = 5 fő a HOME csapatból a t=10 pillanatban
    assert roster.on_court_count(Team.HOME, 10) == 5
    # a kiállítások után visszaáll 7-re
    assert roster.on_court_count(Team.HOME, 200) == 7
    # az AWAY csapatot nem érinti
    assert roster.on_court_count(Team.AWAY, 10) == 7


# pytest nélkül is futtatható: lefuttatja az összes test_ függvényt.
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
