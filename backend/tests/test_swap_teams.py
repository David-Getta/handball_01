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


def test_majority_team_voting_is_stable_under_noise():
    """Track-szintű szavazás: a zajos (kisebbségi) színminták nem
    billentik át a track csapat-címkéjét."""
    from handball.pipeline.teams import majority_team_by_track
    centers = [(200.0, 40.0, 40.0), (40.0, 40.0, 200.0)]  # piros vs kék
    colors_by_track = {
        # Zömmel piros, néhány zajos (kékes) mintával: PIROS marad.
        1: [(190, 50, 50)] * 8 + [(60, 60, 180)] * 2,
        # Zömmel kék: KÉK.
        2: [(50, 50, 190)] * 9 + [(180, 60, 60)],
        # Fele-fele: döntetlennél a HOME (determinista viselkedés).
        3: [(190, 50, 50)] * 5 + [(50, 50, 190)] * 5,
    }
    teams = majority_team_by_track(colors_by_track, centers)
    assert teams[1] == Team.HOME
    assert teams[2] == Team.AWAY
    assert teams[3] == Team.HOME


def test_majority_team_without_centers_defaults_home():
    from handball.pipeline.teams import majority_team_by_track
    teams = majority_team_by_track({1: [(1, 2, 3)], 2: []}, None)
    assert teams == {1: Team.HOME, 2: Team.HOME}
