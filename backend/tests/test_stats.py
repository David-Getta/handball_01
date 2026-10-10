

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


# ---- Vasemberek (KI játssza végig csere nélkül) ----------------------------


def test_iron_men_names_the_player_who_never_rests():
    """A végig pályán lévő ember név szerint kerül a listába; aki a
    felvétel 55%-án játszik, nem vasember."""
    from handball.pipeline.stats import IRONMEN_SHARE_PCT, iron_men

    rec = iron_men(_irm_match(deep_bench=True))["away"]
    labels = [p["label"] for p in rec["players"]]
    assert "id 21" in labels, rec
    assert all("23" not in l for l in labels), rec
    assert rec["players"][0]["share_pct"] >= IRONMEN_SHARE_PCT, rec
    assert rec["verdict"] and "friss ember" in rec["verdict"], rec


def test_iron_men_silent_on_a_short_recording():
    """Rövid felvételen nincs ítélet (sose hallgatólagos vasember)."""
    from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                          PlayerPosition,
                                          PositionSource, Team)
    from handball.pipeline.stats import iron_men

    frames = [Frame(t=t, players=[PlayerPosition(
        track_id=5, team=Team.HOME, x=20.0, y=10.0,
        source=PositionSource.MEASURED, confidence=1.0)],
        ball=Ball(x=20.0, y=10.0, confidence=1.0))
        for t in range(300)]
    m = Match(MatchMeta(match_id="imn", home_team="H", away_team="A",
                        fps=1.0), frames)   # 5 perc — a küszöb alatt
    rec = iron_men(m)["home"]
    assert rec["players"] == [] and rec["verdict"] is None, rec


# ---- Sprint-esés (megfogy-e a láb a második félidőre) ----------------------


def _sfd_pl(tid, team, x, y):
    from handball.models.tracking import PlayerPosition, PositionSource
    return PlayerPosition(track_id=tid, team=team, x=x, y=y,
                          source=PositionSource.MEASURED,
                          confidence=1.0)


def _sfd_match(fh_sprints, sh_sprints, fps=25.0):
    """Két félidő 6-6 perccel és 90 mp szünettel; félidőnként a
    megadott számú hazai sprint-futam (a többi kocka lassú séta)."""
    from handball.models.tracking import Frame, Match, MatchMeta, Team

    _pl = _sfd_pl
    frames = []
    t = 0

    def _walk(seconds, x0=10.0):
        nonlocal t
        for i in range(int(seconds * fps)):
            players = [_pl(10 + k, Team.HOME, x0 + 0.5 * k, 5.0 + k)
                       for k in range(6)]
            players += [_pl(20 + k, Team.AWAY, 30.0 + 0.5 * k,
                            5.0 + k) for k in range(6)]
            frames.append(Frame(t=t, players=players, ball=None))
            t += 1

    def _sprint():
        """Egy 1 mp-es sprint-futam a hazai 10-esnek (8 m/s)."""
        nonlocal t
        x = 5.0
        for _ in range(int(1.0 * fps)):
            players = [_pl(10, Team.HOME, x, 5.0)]
            players += [_pl(11 + k, Team.HOME, 12.0 + k, 8.0 + k)
                        for k in range(5)]
            players += [_pl(20 + k, Team.AWAY, 30.0 + 0.5 * k,
                            5.0 + k) for k in range(6)]
            frames.append(Frame(t=t, players=players, ball=None))
            x += 8.0 / fps
            t += 1

    def _break(seconds):
        nonlocal t
        for _ in range(int(seconds * fps)):
            frames.append(Frame(t=t, players=[], ball=None))
            t += 1

    _walk(150.0)
    for _ in range(fh_sprints):
        _sprint()
        _walk(5.0)
    _walk(180.0)
    _break(90.0)
    _walk(150.0)
    for _ in range(sh_sprints):
        _sprint()
        _walk(5.0)
    _walk(180.0)
    return Match(MatchMeta(match_id="sfd", home_team="H", away_team="A",
                           fps=fps), frames)


def test_sprint_fade_flags_the_tiring_team():
    """Ha a második félidőre a sprint-ütem harmadára esik, a szünet
    után tempót kell emelni ellenük."""
    from handball.pipeline.stats import sprint_fade

    rec = sprint_fade(_sfd_match(9, 2))["home"]
    assert rec["fh_sprints"] >= 8 or rec["sh_sprints"] >= 1, rec
    assert rec["ratio"] is not None and rec["ratio"] <= 0.7, rec
    assert rec["verdict"] and "megfogy a lábuk" in rec["verdict"], rec


def test_sprint_fade_flags_the_second_half_surge():
    """A fordított eset: a második félidőre kapcsolnak."""
    from handball.pipeline.stats import sprint_fade

    rec = sprint_fade(_sfd_match(2, 9))["home"]
    assert rec["ratio"] and rec["ratio"] >= 1.4, rec
    assert rec["verdict"] and "KAPCSOLNAK" in rec["verdict"], rec


def test_sprint_fade_silent_without_halftime():
    """Félidő-jel (szünet) nélkül nincs ítélet."""
    from handball.pipeline.stats import sprint_fade

    from handball.models.tracking import Frame, Match, MatchMeta, Team

    frames = [Frame(t=i, players=[_sfd_pl(10, Team.HOME, 10.0, 5.0)],
                    ball=None) for i in range(500)]
    rec = sprint_fade(Match(MatchMeta(match_id="sfd0", home_team="H",
                                      away_team="A", fps=25.0),
                            frames))["home"]
    assert rec["ratio"] is None and rec["verdict"] is None, rec
