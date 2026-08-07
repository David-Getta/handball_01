

def _irm_match(deep_bench=True, fps=25.0):
    """A vendég 21-es (beálló) minden kockán pályán van; a 23-as
    (szélső) csak a felvétel 55%-án, ha `deep_bench` — különben ő is
    végig. 10 percnyi kocka, végig vendég-birtoklással a -x kapu felé
    (ebből épül a poszt-minta)."""
    from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                          PlayerPosition,
                                          PositionSource, Team)

    def pl(tid, team, x, y, role=None):
        return PlayerPosition(track_id=tid, team=team, x=x, y=y,
                              source=PositionSource.MEASURED,
                              confidence=1.0, role=role)

    total = int(10 * 60 * fps)
    cut = int(total * 0.55)
    frames = []
    for t in range(total):
        players = [pl(1, Team.HOME, 30.0, 10.0),
                   pl(21, Team.AWAY, 6.0, 10.0),
                   pl(29, Team.AWAY, 39.5, 10.0, role="kapus")]
        if (not deep_bench) or t < cut:
            players.append(pl(23, Team.AWAY, 6.0, 1.0))
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=6.2, y=10.0, confidence=1.0)))
    return Match(MatchMeta(match_id="irm", home_team="H",
                           away_team="A", fps=fps), frames)


def test_iron_man_roles_names_the_unrested_post():
    """Ha egy poszt végigjátszik, miközben a többit cserélik, a
    hajrában oda kell vinni a tempót."""
    from handball.pipeline.stats import IRM_SHARE_PCT, iron_man_roles

    rec = iron_man_roles(_irm_match(deep_bench=True))["away"]
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= IRM_SHARE_PCT, rec
    assert rec["verdict"] and "hajrában" in rec["verdict"], rec


def test_iron_man_roles_silent_when_everyone_plays_through():
    """Ha az egész csapat cserétlen, nincs kitüntetett poszt."""
    from handball.pipeline.stats import iron_man_roles

    rec = iron_man_roles(_irm_match(deep_bench=False))["away"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec
