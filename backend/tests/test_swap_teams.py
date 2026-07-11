"""A csapat-felcserélés (Match.swap_teams) tesztjei."""
from handball.models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, Ball, Team,
)


def _mini_match():
    meta = MatchMeta(match_id="m1", home_team="Piros", away_team="Kék", fps=25.0)
    frames = [
        Frame(t=0, players=[
            PlayerPosition(track_id=1, team=Team.HOME, x=10.0, y=5.0),
            PlayerPosition(track_id=2, team=Team.AWAY, x=30.0, y=15.0),
        ], ball=Ball(x=20.0, y=10.0)),
        Frame(t=1, players=[
            PlayerPosition(track_id=1, team=Team.HOME, x=11.0, y=5.0),
        ]),
    ]
    return Match(meta=meta, frames=frames)


def test_swap_flips_every_player():
    m = _mini_match()
    m.swap_teams()
    assert m.frames[0].players[0].team == Team.AWAY
    assert m.frames[0].players[1].team == Team.HOME
    assert m.frames[1].players[0].team == Team.AWAY


def test_swap_keeps_names_and_ball():
    m = _mini_match()
    m.swap_teams()
    assert m.meta.home_team == "Piros" and m.meta.away_team == "Kék"
    assert m.frames[0].ball is not None and m.frames[0].ball.x == 20.0


def test_double_swap_is_identity():
    m = _mini_match()
    m.swap_teams()
    m.swap_teams()
    assert m.frames[0].players[0].team == Team.HOME
    assert m.frames[0].players[1].team == Team.AWAY


def test_swap_survives_json_roundtrip():
    m = _mini_match()
    m.swap_teams()
    m2 = Match.from_json(m.to_json())
    assert m2.frames[0].players[0].team == Team.AWAY
