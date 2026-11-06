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


def test_a_csapatcsere_utan_a_felderites_es_a_kivonat_is_frissul(tmp_path, monkeypatch):
    """Csapatcsere után a felderítő jelentés és a könyvtár-kivonat a FRISS
    adatból számol — nem a memória-tárból.

    A felderítés memória-tárának kulcsa (meccs, oldal, kockaszám,
    csapatnevek, felülírások) a csapatcserétől NEM változik, a
    kivonat-tár kulcsa (kockaszám, csapatnevek, dátum) sem: a csere után
    a hazai oldal felderítése a régi (a cserélt vendég-) jelentést adta,
    pedig a végpont azt ígérte, hogy "a statisztika/felderítés a friss
    adatból számol". Mostantól minden tár-írás eldobja a származtatott
    kivonatokat.
    """
    import json

    import pytest

    TestClient = pytest.importorskip(
        "fastapi.testclient", reason="fastapi nincs telepítve").TestClient
    from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                          PlayerPosition, PositionSource,
                                          Team)

    def pl(tid, team, x, y):
        return PlayerPosition(track_id=tid, team=team, x=x, y=y,
                              source=PositionSource.MEASURED, confidence=1.0)

    # A hazaiak négyszer lőnek a +x kapura (a vendég védő távol).
    frames = []
    t = 0
    for _ in range(4):
        for i in range(7):
            frames.append(Frame(t=t, players=[pl(1, Team.HOME, 33.0, 10.0),
                                              pl(20, Team.AWAY, 33.0, 16.0)],
                                ball=Ball(x=34.0 + i, y=10.0, confidence=1.0)))
            t += 1
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 20
    m = Match(MatchMeta(match_id="cs", home_team="H", away_team="A",
                        fps=25.0), frames)
    d = tmp_path / "data" / "matches"
    d.mkdir(parents=True)
    (d / "cs.json").write_text(json.dumps(m.to_dict()), encoding="utf-8")
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("HANDBALL_STORE_SYNC", "1")
    from handball.api.app import create_app
    client = TestClient(create_app())

    # A lövés CSAPATÁT a kapu oldala adja (a hazai a +x kapura támad), a
    # LÖVŐT viszont a támadó csapat címkéjű játékosok közül keressük —
    # a csere után a volt hazai lövő már vendég-címkés, ezért a
    # gólszerző-lista és a fedezetlen befejezések száma változik.
    elotte = client.get("/matches/cs/scouting?team=home").json()
    assert elotte["scorer_goals"] and elotte["scorer_goals"][0]["player_id"] == 1
    assert elotte["fin_free_shots"] == 4

    assert client.post("/matches/cs/swap-teams").status_code == 200

    utana = client.get("/matches/cs/scouting?team=home").json()
    assert utana["scorer_goals"] == [], "csere után a régi jelentés jött vissza"
    assert utana["fin_free_shots"] == 0
