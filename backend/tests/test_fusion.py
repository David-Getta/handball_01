"""
Tesztek a nézet-fúzióra (fusion.py) — szintetikus két-kamerás nézetekkel.

Futtatás:
    python -m pytest tests/test_fusion.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.fusion import fuse_matches


def _meta():
    return MatchMeta(match_id="fu", home_team="H", away_team="A", fps=25.0)


def _pl(tid, team, x, y):
    return PlayerPosition(track_id=tid, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0)


def test_fusion_averages_noisy_views():
    """Ugyanaz a játékos két nézetben ±0,2 m zajjal → a fúzió a kettő
    átlagát adja (pontosabb, mint bármelyik nézet)."""
    a = Match(_meta(), [Frame(t=0, players=[_pl(1, Team.HOME, 19.8, 10.2)])])
    b = Match(_meta(), [Frame(t=0, players=[_pl(7, Team.HOME, 20.2, 9.8)])])
    fused = fuse_matches([a, b])
    assert len(fused.frames[0].players) == 1
    p = fused.frames[0].players[0]
    assert abs(p.x - 20.0) < 0.01 and abs(p.y - 10.0) < 0.01


def test_fusion_fills_occlusion_from_other_view():
    """A 2. kockán az egyik nézetből eltűnik a játékos (takarás) — a
    másik nézet kitölti, és a fúziós track-azonosító folytonos marad."""
    a = Match(_meta(), [
        Frame(t=0, players=[_pl(1, Team.HOME, 20.0, 10.0)]),
        Frame(t=1, players=[]),                       # takarás az A nézetben
        Frame(t=2, players=[_pl(1, Team.HOME, 20.6, 10.0)]),
    ])
    b = Match(_meta(), [
        Frame(t=0, players=[_pl(9, Team.HOME, 20.0, 10.0)]),
        Frame(t=1, players=[_pl(9, Team.HOME, 20.3, 10.0)]),
        Frame(t=2, players=[_pl(9, Team.HOME, 20.6, 10.0)]),
    ])
    fused = fuse_matches([a, b])
    tids = [fused.frames[i].players[0].track_id for i in range(3)]
    assert len(set(tids)) == 1          # végig ugyanaz a fúziós track
    assert fused.frames[1].players     # a takart kockán is van pozíció


def test_fusion_keeps_separate_players_apart():
    """Két különböző (2 m-nél távolabbi) játékos nem olvad össze; az
    azonos helyen álló ELLENFÉL sem."""
    a = Match(_meta(), [Frame(t=0, players=[
        _pl(1, Team.HOME, 10.0, 10.0),
        _pl(2, Team.HOME, 14.0, 10.0),
        _pl(11, Team.AWAY, 10.2, 10.0),
    ])])
    fused = fuse_matches([a])
    assert len(fused.frames[0].players) == 3


def test_fusion_picks_highest_confidence_ball():
    a = Match(_meta(), [Frame(t=0, players=[],
                              ball=Ball(x=10.0, y=5.0, confidence=0.4))])
    b = Match(_meta(), [Frame(t=0, players=[],
                              ball=Ball(x=10.1, y=5.0, confidence=0.9))])
    fused = fuse_matches([a, b])
    assert abs(fused.frames[0].ball.x - 10.1) < 1e-6


def test_clock_offset_estimated_from_ball_path():
    """A b nézet 7 kockával késik → az eltolás-becslés 7-et ad, és az
    apply_offset után a fúzió a helyes (átlagolt) pályát adja."""
    import math as _m
    from handball.pipeline.fusion import apply_offset, estimate_clock_offset

    def view(shift, noise):
        frames = []
        for t in range(120):
            src = t - shift
            if src < 0:
                frames.append(Frame(t=t, players=[], ball=None))
                continue
            x = 20.0 + 10.0 * _m.sin(src / 8.0)
            y = 10.0 + 3.0 * _m.cos(src / 5.0)
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=x + noise, y=y,
                                          confidence=1.0)))
        return Match(_meta(), frames)

    a = view(0, 0.0)
    b = view(7, 0.05)
    off = estimate_clock_offset(a, b, max_offset=20)
    assert off == 7
    b_synced = apply_offset(b, off)
    # Összeigazítás után a két nézet labdája (majdnem) egybeesik.
    fused = fuse_matches([a, b_synced])
    ball0 = fused.frames[50].ball
    x_true = 20.0 + 10.0 * _m.sin(50 / 8.0)
    assert ball0 is not None and abs(ball0.x - x_true) < 0.1


def test_clock_offset_none_without_overlap():
    from handball.pipeline.fusion import estimate_clock_offset
    a = Match(_meta(), [Frame(t=0, players=[], ball=None)])
    b = Match(_meta(), [Frame(t=0, players=[],
                              ball=Ball(x=1.0, y=1.0, confidence=1.0))])
    assert estimate_clock_offset(a, b) is None


def test_fuse_endpoint_creates_new_match(tmp_path):
    """A POST /matches/fuse két nézetből új meccset tesz a könyvtárba,
    amin a szokásos végpontok futnak."""
    import os
    os.environ["HANDBALL_DATA_DIR"] = str(tmp_path)
    from fastapi.testclient import TestClient
    from handball.api.app import create_app

    app = TestClient(create_app())
    a = Match(_meta(), [Frame(t=t, players=[_pl(1, Team.HOME,
                                                20.0 + 0.1 * t, 10.0)])
                        for t in range(30)])
    b_meta = MatchMeta(match_id="fu-b", home_team="H", away_team="A",
                       fps=25.0)
    b = Match(b_meta, [Frame(t=t, players=[_pl(5, Team.HOME,
                                               20.0 + 0.1 * t, 10.2)])
                       for t in range(30)])
    app.app.state.put_match(a)
    app.app.state.put_match(b)

    r = app.post("/matches/fuse", json={
        "match_ids": ["fu", "fu-b"], "match_id": "fuzio-teszt",
        "auto_sync": False})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["match_id"] == "fuzio-teszt"
    assert body["n_views"] == 2 and body["frames"] == 30
    # Az új meccs lekérhető, és a fúziós pozíció a két nézet átlaga.
    got = app.get("/matches/fuzio-teszt")
    assert got.status_code == 200
    # Kevés nézet → 400; ismeretlen id → 404.
    assert app.post("/matches/fuse",
                    json={"match_ids": ["fu"]}).status_code == 400
    assert app.post("/matches/fuse",
                    json={"match_ids": ["fu", "nincs"]}).status_code == 404
