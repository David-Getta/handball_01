"""Az angol meccs-kártya (summary_en.match_card_en) tesztjei."""
from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                      PlayerPosition, Team)
from handball.pipeline.summary_en import match_card_en


def _meta():
    return MatchMeta(match_id="en", home_team="Lions", away_team="Bears",
                     fps=25.0)


def _pl(tid, team, x, y):
    return PlayerPosition(track_id=tid, team=team, x=x, y=y)


def _goal(frames, t, team, shooter, hold_x, goal_x):
    step = 0.5 if goal_x > hold_x else -0.5
    for _ in range(30):
        frames.append(Frame(t=t, players=[_pl(shooter, team, hold_x, 10.0)],
                            ball=Ball(x=hold_x, y=10.0, confidence=1.0)))
        t += 1
    x = hold_x
    while (x < goal_x) if step > 0 else (x > goal_x):
        x += step
        frames.append(Frame(t=t, players=[_pl(shooter, team, hold_x, 10.0)],
                            ball=Ball(x=x, y=10.0, confidence=1.0)))
        t += 1
    for _ in range(40):
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    return t


def test_match_card_en_headline_and_top_scorer():
    """3 hazai gól (az 1-estől) + 1 vendég-gól → angol eredménysor és
    gólfelelős-mondat."""
    frames = []
    t = 0
    for _ in range(3):
        t = _goal(frames, t, Team.HOME, 1, 33.0, 40.5)
    t = _goal(frames, t, Team.AWAY, 9, 10.0, -0.5)

    card = match_card_en(Match(_meta(), frames))
    assert card["headline"] == "Lions 3\u20131 Bears"
    assert any("Top scorer for Lions: player #1 with 3 goals" in l
               for l in card["lines"])


def test_match_card_en_empty_match_is_safe():
    """Gól nélküli meccsen is áll a kártya — 0-0 és nincs találgatás."""
    frames = [Frame(t=i, players=[],
                    ball=Ball(x=20.0, y=10.0, confidence=1.0))
              for i in range(100)]
    card = match_card_en(Match(_meta(), frames))
    assert card["headline"] == "Lions 0\u20130 Bears"
    assert isinstance(card["lines"], list)


def test_scouting_cards_en_reports_established_facts():
    """A szimulált meccsről angol pontok születnek — mérhető tényekből."""
    from handball.pipeline.summary_en import scouting_cards_en
    from handball.sim.match_simulator import simulate_ground_truth

    cards = scouting_cards_en(simulate_ground_truth(duration_s=180.0,
                                                    seed=3))
    assert set(cards) == {"home", "away"}
    for side in ("home", "away"):
        card = cards[side]
        assert card["headline"]
        assert card["lines"], card
        text = " ".join(card["lines"])
        assert "Main defensive formation" in text or "Possession" in text
        # Angol felület: magyar ékezetes szó nem szivároghat bele.
        assert "támadás" not in text and "lövés" not in text


def test_scouting_cards_en_stays_silent_without_evidence():
    """Üres meccsen nincs állítás — a kártya nem találgat."""
    from handball.pipeline.summary_en import scouting_cards_en

    frames = [Frame(t=i, players=[], ball=Ball(x=20.0, y=10.0,
                                               confidence=1.0))
              for i in range(120)]
    cards = scouting_cards_en(Match(_meta(), frames))
    for side in ("home", "away"):
        assert cards[side]["lines"] == [], cards[side]
