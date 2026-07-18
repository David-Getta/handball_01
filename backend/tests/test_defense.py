"""
Tesztek a védekezés-elemzésre (defense.py): szabad lövés, zóna, kapott xG.

A pálya 40x20 m; a HAZAI a +x (x=40) kapu felé támad — tehát a hazai
lövéseket a VENDÉG védekezése "kapja".

Futtatás:
    python -m pytest tests/test_defense.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.defense import defense_analysis


def _meta(fps=25.0):
    return MatchMeta(match_id="d", home_team="H", away_team="A", fps=fps)


def _pl(track_id, team, x, y, role=None):
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0,
                          role=role)


def _shot(t0, defenders, goal=True):
    """Hazai lövés a +x kapura az 1-es játékostól (x=33, y=10) — a megadott
    védőkkel a lövés-képkockákon."""
    frames = []
    for i in range(7):
        players = [_pl(1, Team.HOME, 33.0, 10.0)] + defenders
        y = 10.0 if goal else 5.0
        frames.append(Frame(t=t0 + i, players=players,
                            ball=Ball(x=34.0 + i, y=y, confidence=1.0)))
    frames.append(Frame(t=t0 + 7, players=[],
                        ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    return frames


def test_free_vs_covered_shot():
    """Védő 1 m-re → fedezett; a legközelebbi védő 5 m-re → szabad lövés."""
    # A védő a lövő mellett (0,7 m), de NEM a labda röppályáján — különben
    # őt találná meg a birtokos-keresés, és a lövő azonosíthatatlan lenne.
    covered = _shot(0, [_pl(20, Team.AWAY, 32.5, 10.5)])          # 0,7 m
    free = _shot(40, [_pl(21, Team.AWAY, 33.0, 15.0)])            # 5 m
    m = Match(_meta(), covered + free)
    d = defense_analysis(m)["away"]  # a vendég védekezett
    assert d["shots_against"] == 2 and d["goals_against"] == 2
    assert d["free_shots"] == 1
    assert d["free_pct"] == 50.0
    flags = [s["free"] for s in d["shots"]]
    assert flags == [False, True]
    # A hazai védekezés nem kapott lövést.
    assert defense_analysis(m)["home"]["shots_against"] == 0


def test_goalkeeper_does_not_count_as_cover():
    """A kapus közelsége NEM fedezés — mezőnyvédő nélkül a lövés szabad."""
    gk_only = _shot(0, [_pl(30, Team.AWAY, 34.0, 10.0, role="kapus")])
    d = defense_analysis(Match(_meta(), gk_only))["away"]
    assert d["shots_against"] == 1
    # Egyetlen mezőnyvédő sincs → nincs táv-minta → free None (nem mérhető).
    assert d["shots"][0]["free"] is None
    assert d["free_shots"] == 0


def test_zones_and_worst_zone():
    """A zóna-bontás a lövés helyéből jön; a legtöbb gólt hozó zóna a
    worst_zone."""
    beallo = _shot(0, [_pl(20, Team.AWAY, 38.0, 10.0)])           # beálló (6 m)
    m = Match(_meta(), beallo)
    d = defense_analysis(m)["away"]
    assert "beálló (6 m)" in d["zones"]
    assert d["worst_zone"] == "beálló (6 m)"
    assert d["xg_against"] > 0


def test_transition_defense_counts_fast_goals():
    """Labdaeladás → az ellenfél gólja 8 mp-en belül = átmenet-gól."""
    from handball.pipeline.defense import transition_defense

    frames = []
    t = 0
    # A hazai birtokol, majd a vendég szerzi meg (labdaeladás a hazainak).
    frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 25.0, 10.0)],
                        ball=Ball(x=25.0, y=10.0, confidence=1.0)))
    t += 1
    frames.append(Frame(t=t, players=[_pl(11, Team.AWAY, 20.0, 10.0)],
                        ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    t += 1
    # Hézag: a vendég vezeti a labdát ~1 mp-ig (a lövés-közeli labdaeladás-
    # elnyomás miatt kell távolság a labdaeladás és a lövés között), de a
    # gól még a 8 mp-es átmenet-ablakon belül van.
    for i in range(25):
        bx = 20.0 - i * 0.4
        frames.append(Frame(t=t, players=[_pl(11, Team.AWAY, bx, 10.0)],
                            ball=Ball(x=bx, y=10.0, confidence=1.0)))
        t += 1
    # A vendég gólt lő a -x (x=0) kapura (a hazai kapujára).
    for i in range(7):
        frames.append(Frame(t=t, players=[_pl(11, Team.AWAY, 7.0, 10.0)],
                            ball=Ball(x=max(0.0, 6.4 - i), y=10.0,
                                      confidence=1.0)))
        t += 1
    td = transition_defense(Match(_meta(), frames))
    assert td["home"]["turnovers"] >= 1
    assert td["home"]["transition_goals_against"] >= 1
    assert td["home"]["pct"] > 0
    # A vendég nem vesztett labdát ebben a jelenetben.
    assert td["away"]["transition_goals_against"] == 0


def test_turnover_zones_classifies_front_loss():
    """A támadó harmadban (a megtámadott kapu közelében) elvesztett labda a
    'támadó' zónába kerül, és emeli a front_pct-t."""
    from handball.pipeline.defense import turnover_zones

    frames = []
    t = 0
    # A hazai birtokolja a labdát a vendég kapuja közelében (x=35, a +x
    # kapu felé támad), majd a vendég szerzi meg → labdaeladás itt.
    for _ in range(3):
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 35.0, 10.0)],
                            ball=Ball(x=35.0, y=10.0, confidence=1.0)))
        t += 1
    for _ in range(3):
        frames.append(Frame(t=t, players=[_pl(11, Team.AWAY, 35.0, 10.0)],
                            ball=Ball(x=35.0, y=10.0, confidence=1.0)))
        t += 1
    tz = turnover_zones(Match(_meta(), frames))
    assert tz["home"]["total"] == 1
    assert tz["home"]["zones"].get("támadó") == 1
    assert tz["home"]["front_pct"] == 100.0
    assert tz["away"]["total"] == 0


def test_defensive_pressure_tight_vs_loose():
    """Szoros védő (1 m) kisebb nyomás-átlagot ad, mint a laza (6 m)."""
    from handball.pipeline.defense import defensive_pressure

    def scene(def_y):
        frames = []
        for t in range(30):
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, 25.0, 10.0),          # labdás támadó
                _pl(20, Team.AWAY, 25.0, def_y)],       # a védő
                ball=Ball(x=25.0, y=10.0, confidence=1.0)))
        return Match(_meta(), frames)

    tight = defensive_pressure(scene(11.0))["away"]["avg_pressure_m"]
    loose = defensive_pressure(scene(16.0))["away"]["avg_pressure_m"]
    assert tight is not None and loose is not None
    assert tight < loose
    assert abs(tight - 1.0) < 0.2  # ~1 m-re állt a védő
