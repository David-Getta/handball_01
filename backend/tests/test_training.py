"""
Tesztek az edzés-fókusz javaslatokra (training.py).

A pálya 40x20 m; a HAZAI a +x (x=40) kapu felé támad.

Futtatás:
    python -m pytest tests/test_training.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.training import training_focus


def _meta(fps=25.0):
    return MatchMeta(match_id="tr", home_team="H", away_team="A", fps=fps)


def _pl(track_id, team, x, y):
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0)


def _shots_match(n=4, goal=True, defender_far=True):
    """n hazai lövés a +x kapura (gól vagy mellé), a vendég védő távol
    (szabad lövő) vagy szorosan."""
    frames = []
    t = 0
    for _ in range(n):
        for i in range(7):
            players = [_pl(1, Team.HOME, 33.0, 10.0),
                       _pl(20, Team.AWAY, 33.0, 16.0 if defender_far else 10.7)]
            y = 10.0 if goal else 5.0
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=34.0 + i, y=y, confidence=1.0)))
            t += 1
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 20
    return Match(_meta(), frames)


def test_free_shots_trigger_defense_focus():
    """Sok szabadon hagyott lövő → a VÉDEKEZŐ csapat fedezés-fókuszt kap."""
    tf = training_focus(_shots_match(goal=True, defender_far=True))
    away = tf["away"]
    assert any(it["title"] == "Fedezés-fegyelem" for it in away)
    # A zóna-fókusz is megjelenik (2+ kapott gól a beállóból).
    assert any(it["title"].startswith("Zóna-védekezés") for it in away)
    # Minden javaslat indoklással és gyakorlattal jön.
    for it in away:
        assert it["why"] and it["drill"] and it["area"]


def test_missed_chances_trigger_finishing_focus():
    """Nagy értékű, de kihagyott helyzetek → befejezés-fókusz a támadónak."""
    tf = training_focus(_shots_match(goal=False, defender_far=False))
    assert any(it["title"] == "Befejezés nyomás alatt" for it in tf["home"])


def test_empty_match_gives_empty_lists():
    m = Match(_meta(), [Frame(t=i, players=[], ball=None) for i in range(10)])
    tf = training_focus(m)
    assert tf == {"home": [], "away": []}


def test_focus_list_is_capped():
    """A lista rangsorolt és legfeljebb 5 elemű (a fókusz kevés elem)."""
    tf = training_focus(_shots_match(goal=True, defender_far=True))
    assert len(tf["away"]) <= 5 and len(tf["home"]) <= 5
