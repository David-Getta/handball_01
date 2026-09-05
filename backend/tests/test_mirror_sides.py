"""
A tükrözés-őr (scripts.mirror_sides) tesztjei.

A teljes, minden rétegre kiterjedő söprés lassú (fél perc feletti),
ezért az a jelentés-szkript dolga — mint a sorrend-függésnél. Itt a
mechanikát rögzítjük gyors tesztekkel: a csere-szabályt (a magyar
"jobb" = better csapdájával), a tükrözést, és egy kézzel épített
jeleneten a legbuktatósabb védekező-oldali réteget.

Futtatás:
    python -m pytest tests/test_mirror_sides.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.mirror_sides import has_side_label, mirror_match, swap_sides

from handball.models.tracking import (
    Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)


def test_swap_flips_labels_but_never_prose():
    """A csere a címkéket fordítja meg — a mondatot, ahol a "jobb"
    better-t jelent, SOHA (ez a magyar nyelv csapdája)."""
    rec = {
        "worst_zone": "bal szél",
        "hands": {"bal": 1, "jobb": 2},
        "verdict": "csak 20%-nál volt jobb szabad helyzet",
    }
    out = swap_sides(rec)
    assert out["worst_zone"] == "jobb szél"
    assert out["hands"] == {"jobb": 1, "bal": 2}
    # A próza érintetlen: a "jobb szabad helyzet" nem oldal.
    assert out["verdict"] == "csak 20%-nál volt jobb szabad helyzet"


def test_has_side_label_ignores_prose():
    """A szűrő a címkét látja meg, a prózában említett oldalt nem."""
    assert has_side_label({"weak_side": "bal"})
    assert has_side_label({"zones": {"jobb szél": 3}})
    assert not has_side_label({"verdict": "jobb helyzet volt a pályán"})


def test_mirror_flips_players_and_ball():
    """A tükrözés az y-t fordítja (20 − y), és nem nyúl máshoz."""
    m = Match(MatchMeta(match_id="mir", home_team="H", away_team="A",
                        fps=25.0),
              [Frame(t=0,
                     players=[PlayerPosition(
                         track_id=1, team=Team.HOME, x=10.0, y=4.0,
                         source=PositionSource.MEASURED, confidence=1.0)],
                     ball=Ball(x=20.0, y=15.0, confidence=1.0))])
    m2 = mirror_match(m)
    assert m2.frames[0].players[0].y == 16.0
    assert m2.frames[0].players[0].x == 10.0
    assert m2.frames[0].ball.y == 5.0
    # Az eredeti érintetlen (mély másolat).
    assert m.frames[0].players[0].y == 4.0


def test_defensive_gaps_zone_flips_in_the_mirror():
    """A fal-rés réteg oldal-megnevezése a tükörképben megfordul — a
    védekező oldalra szóló rétegek legbuktatósabb tulajdonsága (a két
    csapat szemben áll, a nyers y-ból nevezett oldal hibás lenne)."""
    from handball.pipeline.defense import defensive_gaps

    def _pl(track_id, team, x, y, role=None):
        return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                              source=PositionSource.MEASURED,
                              confidence=1.0, role=role)

    frames = []
    for t in range(150):
        players = [_pl(1, Team.AWAY, 8.0, 10.0)]
        # A rés a NAGY y-nál tátong (16,5 közepű).
        for i, y in enumerate([2.0, 4.0, 6.0, 8.0, 10.0, 23.0]):
            players.append(_pl(10 + i, Team.HOME, 6.0, min(y, 19.5)))
        players.append(_pl(9, Team.HOME, 0.5, 10.0, role="kapus"))
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=8.0, y=10.0, confidence=1.0)))
    m = Match(MatchMeta(match_id="dg", home_team="H", away_team="A",
                        fps=25.0), frames)

    plain = defensive_gaps(m)["home"]
    flipped = defensive_gaps(mirror_match(m))["home"]
    assert plain["worst_zone"] is not None
    assert flipped["worst_zone"] == swap_sides(plain)["worst_zone"]
    assert flipped["worst_zone"] != plain["worst_zone"]
