"""
Tesztek a track-összefűzésre (track_stitch.py).

Futtatás:
    python -m pytest tests/test_track_stitch.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.track_stitch import StitchConfig, stitch_tracks


def _match(frames, fps=25.0):
    return Match(meta=MatchMeta(match_id="t", home_team="H", away_team="A",
                                fps=fps), frames=frames)


def _walk(track_id, team, t0, t1, x0, speed=2.0, fps=25.0, y=5.0):
    """Egyenletesen mozgó játékos mért pozíciói t0..t1 kockákon."""
    out = []
    for t in range(t0, t1 + 1):
        out.append((t, PlayerPosition(
            track_id=track_id, team=team, x=x0 + speed * (t - t0) / fps, y=y)))
    return out


def _frames(*walks, n=None):
    by_t: dict = {}
    for walk in walks:
        for (t, p) in walk:
            by_t.setdefault(t, []).append(p)
    total = n or (max(by_t) + 1)
    return [Frame(t=t, players=by_t.get(t, [])) for t in range(total)]


def test_stitches_broken_track():
    """Egy játékos 1-esként indul, takarás után 7-esként folytatja —
    a folytonos pálya alapján összefűzzük, az 1-es azonosító marad."""
    a = _walk(1, Team.HOME, 0, 49, x0=10.0)   # 10 → 13.92 m
    b = _walk(7, Team.HOME, 60, 100, x0=15.0)  # 11 kocka lyuk, ~1 m-re indul
    m = _match(_frames(a, b))
    assert stitch_tracks(m) == 1
    ids = {p.track_id for f in m.frames for p in f.players}
    assert ids == {1}  # a 7-es beolvadt az 1-esbe


def test_does_not_stitch_far_or_slow_gap():
    """Fizikailag lehetetlen folytatás (túl messze) nem fűződik össze."""
    a = _walk(1, Team.HOME, 0, 49, x0=5.0)
    b = _walk(7, Team.HOME, 55, 90, x0=30.0)  # ~24 m ugrás 6 kocka alatt
    m = _match(_frames(a, b))
    assert stitch_tracks(m) == 0


def test_does_not_stitch_across_teams():
    a = _walk(1, Team.HOME, 0, 49, x0=10.0)
    b = _walk(7, Team.AWAY, 55, 90, x0=14.2)
    m = _match(_frames(a, b))
    assert stitch_tracks(m) == 0


def test_does_not_stitch_long_gap():
    """A max_gap_s-nél hosszabb lyukat nem hidaljuk át (nem találgatunk)."""
    a = _walk(1, Team.HOME, 0, 49, x0=10.0)
    b = _walk(7, Team.HOME, 130, 170, x0=14.0)  # 80 kocka = 3.2 mp lyuk
    m = _match(_frames(a, b))
    assert stitch_tracks(m, StitchConfig(max_gap_s=2.0)) == 0


def test_chain_of_breaks_resolves_to_root():
    """Kétszer megszakadt track (1 → 7 → 9): mindenki az 1-esre képződik."""
    a = _walk(1, Team.HOME, 0, 30, x0=10.0)
    b = _walk(7, Team.HOME, 40, 70, x0=12.7)
    c = _walk(9, Team.HOME, 80, 120, x0=15.6)
    m = _match(_frames(a, b, c))
    assert stitch_tracks(m) == 2
    ids = {p.track_id for f in m.frames for p in f.players}
    assert ids == {1}


def test_duplicate_resolution_prefers_measured():
    """Ha a lyukat a becslő kitöltötte (előd BECSÜLT) és az utód MÉRT
    pozíciója is jelen van ugyanazon a kockán, a mért marad."""
    a = _walk(1, Team.HOME, 0, 49, x0=10.0)
    b = _walk(7, Team.HOME, 60, 100, x0=15.0)
    frames = _frames(a, b)
    # A 60. kockán az 1-es BECSÜLT pozíciója is ott van (a becslő műve).
    frames[60].players.append(PlayerPosition(
        track_id=1, team=Team.HOME, x=13.9, y=5.0,
        source=PositionSource.ESTIMATED))
    m = _match(frames)
    assert stitch_tracks(m) == 1
    players60 = [p for p in m.frames[60].players if p.track_id == 1]
    assert len(players60) == 1
    assert players60[0].source == PositionSource.MEASURED


def test_color_gate_blocks_different_kits():
    """Tér-időben jó jelölt, de NAGYON eltérő mezszín (pl. kapus vs
    mezőnyjátékos ugyanabban a csapatban) → nincs összefűzés."""
    a = _walk(1, Team.HOME, 0, 49, x0=10.0)
    b = _walk(7, Team.HOME, 60, 100, x0=15.0)
    m = _match(_frames(a, b))
    colors = {1: [(200.0, 30.0, 30.0)] * 5,   # piros mez
              7: [(30.0, 200.0, 30.0)] * 5}   # zöld mez
    assert stitch_tracks(m, colors_by_track=colors) == 0


def test_similar_colors_still_stitch():
    """Hasonló (zajszórású) mezszín nem akadályozza az összefűzést."""
    a = _walk(1, Team.HOME, 0, 49, x0=10.0)
    b = _walk(7, Team.HOME, 60, 100, x0=15.0)
    m = _match(_frames(a, b))
    colors = {1: [(200.0, 30.0, 30.0)] * 5,
              7: [(180.0, 45.0, 40.0)] * 5}  # ~30 egység távolság
    assert stitch_tracks(m, colors_by_track=colors) == 1


def test_color_prefers_matching_candidate():
    """Két tér-időben hasonló utód közül a HASONLÓBB színű nyer."""
    a = _walk(1, Team.HOME, 0, 49, x0=10.0)
    b = _walk(7, Team.HOME, 60, 100, x0=15.0, y=5.0)   # eltérő tónus
    c = _walk(8, Team.HOME, 60, 100, x0=15.1, y=5.2)   # egyező tónus
    m = _match(_frames(a, b, c))
    colors = {1: [(200.0, 30.0, 30.0)] * 5,
              7: [(150.0, 80.0, 60.0)] * 5,   # ~85 egység (kapun belül)
              8: [(195.0, 35.0, 32.0)] * 5}   # ~7 egység
    assert stitch_tracks(m, colors_by_track=colors) == 1
    ids = {p.track_id for f in m.frames for p in f.players}
    assert 8 not in ids and 7 in ids  # a 8-as olvadt be, a 7-es önálló maradt


def test_missing_colors_fall_back_to_spatiotemporal():
    """Ismeretlen szín (nincs minta) → a régi tér-időbeli viselkedés."""
    a = _walk(1, Team.HOME, 0, 49, x0=10.0)
    b = _walk(7, Team.HOME, 60, 100, x0=15.0)
    m = _match(_frames(a, b))
    assert stitch_tracks(m, colors_by_track={1: [(200.0, 30.0, 30.0)] * 5}) == 1


if __name__ == "__main__":
    test_stitches_broken_track()
    test_does_not_stitch_far_or_slow_gap()
    test_does_not_stitch_across_teams()
    test_does_not_stitch_long_gap()
    test_chain_of_breaks_resolves_to_root()
    test_duplicate_resolution_prefers_measured()
    test_color_gate_blocks_different_kits()
    test_similar_colors_still_stitch()
    test_color_prefers_matching_candidate()
    test_missing_colors_fall_back_to_spatiotemporal()
    print("Minden track-összefűzés teszt OK.")
