

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


# ---- A sebesség-szakaszok és a zóna-idők (_speed_segments / _sprint_and_zones) --

def _mintak(pontok):
    """(t, x, y, forrás) minták — alapból MÉRT."""
    from handball.models.tracking import PositionSource
    return [(t, x, y, PositionSource.MEASURED if len(p) == 0 else p[0])
            for (t, x, y, *p) in pontok]


def test_speed_segments_ido_tav_es_simitott_sebesseg():
    """Egyenletes mozgás (0,2 m/kocka, 25 fps → 5 m/s): szakaszonként
    0,04 mp, 0,2 m és 5 m/s simított sebesség."""
    from handball.pipeline.stats import _speed_segments

    seg = _speed_segments(_mintak([(t, 0.2 * t, 0.0) for t in range(6)]),
                          dt=0.04)
    assert len(seg) == 5
    for (mp, tav, seb) in seg:
        assert abs(mp - 0.04) < 1e-12 and abs(tav - 0.2) < 1e-12
        assert abs(seb - 5.0) < 1e-9


def test_speed_segments_a_zajos_pontot_simitja():
    """Egyetlen kiugró (zajos) lépés nem ad fals csúcssebességet: a
    szakasz saját sebessége 10 m/s lenne, a 3 szakaszos mozgóátlag
    lehúzza — a táv és az idő viszont a nyers érték marad."""
    from handball.pipeline.stats import _speed_segments

    # 0,1 m/kocka (2,5 m/s), a 3. lépés 0,4 m (10 m/s).
    xs = [0.0, 0.1, 0.2, 0.6, 0.7, 0.8]
    seg = _speed_segments(_mintak([(t, x, 0.0) for t, x in enumerate(xs)]),
                          dt=0.04)
    tavok = [round(s[1], 6) for s in seg]
    assert tavok == [0.1, 0.1, 0.4, 0.1, 0.1]
    assert abs(seg[2][2] - (0.6 / 0.12)) < 1e-9          # 5 m/s, nem 10
    assert max(s[2] for s in seg) < 5.1


def test_speed_segments_becsult_lyuk_es_ugras_kimarad():
    """A becsült pozíció nem szakasz-végpont; a 0,36 mp-nél hosszabb
    lyukat nem hidaljuk át; a valószínűtlen (11 m/s fölötti) ugrás
    követési hiba — egyik sem ad szakaszt."""
    from handball.models.tracking import PositionSource
    from handball.pipeline.stats import _speed_segments

    E = PositionSource.ESTIMATED
    # A 2. pont becsült: az 1→3 közti 2 kockás lyuk még áthidalható.
    seg = _speed_segments(_mintak([(0, 0.0, 0.0), (1, 5.0, 5.0, E),
                                   (2, 0.2, 0.0)]), dt=0.04)
    assert len(seg) == 1 and abs(seg[0][0] - 0.08) < 1e-12
    assert abs(seg[0][1] - 0.2) < 1e-12
    # 10 kockás (0,4 mp) lyuk: nincs szakasz.
    assert _speed_segments(_mintak([(0, 0.0, 0.0), (10, 1.0, 0.0)]),
                           dt=0.04) == []
    # 9 kocka (0,36 mp) még belefér.
    assert len(_speed_segments(_mintak([(0, 0.0, 0.0), (9, 1.0, 0.0)]),
                               dt=0.04)) == 1
    # Teleport: 1 m egy kocka alatt = 25 m/s → kimarad.
    assert _speed_segments(_mintak([(0, 0.0, 0.0), (1, 1.0, 0.0)]),
                           dt=0.04) == []


def test_speed_segments_ritkitott_felvetelen_masodpercben_merodik():
    """A lyuk-korlát és a sebesség MÁSODPERCBEN él: harmad-fps-en
    (dt = 0,12 mp) ugyanaz a mozgás ugyanazt a sebességet adja, és a
    3 ritkított kockás (0,36 mp) lyuk még áthidalható, a 4 kockás nem."""
    from handball.pipeline.stats import _speed_segments

    dt = 0.12
    seg = _speed_segments(_mintak([(t, 0.6 * t, 0.0) for t in range(5)]), dt)
    assert len(seg) == 4
    assert all(abs(s[2] - 5.0) < 1e-9 for s in seg)
    assert len(_speed_segments(_mintak([(0, 0.0, 0.0), (3, 1.0, 0.0)]),
                               dt)) == 1
    assert _speed_segments(_mintak([(0, 0.0, 0.0), (4, 1.0, 0.0)]), dt) == []


def test_speed_segments_keves_mintabol_nincs_szakasz():
    """Minta nélkül, egyetlen mintából vagy csupa becsült pozícióból
    nincs szakasz (üres lista — nem nulla sebességű szakasz)."""
    from handball.models.tracking import PositionSource
    from handball.pipeline.stats import _speed_segments

    E = PositionSource.ESTIMATED
    assert _speed_segments([], 0.04) == []
    assert _speed_segments(_mintak([(0, 1.0, 1.0)]), 0.04) == []
    assert _speed_segments(_mintak([(t, float(t), 0.0, E)
                                    for t in range(5)]), 0.04) == []


def test_sprint_and_zones_zona_idok_es_sprintek():
    """A szakaszokból: csúcssebesség, sebesség-zónánkénti idő, és a
    legalább 0,5 mp-ig tartó sprintek száma + távja (a rövid villanás
    nem sprint)."""
    from handball.pipeline.stats import (PlayerStats, SPRINT_MIN_S,
                                         _sprint_and_zones)

    assert SPRINT_MIN_S == 0.5
    szakaszok = (
        [(0.1, 0.1, 1.0)] * 10        # 1,0 mp séta
        + [(0.1, 0.2, 2.0)] * 5       # 0,5 mp kocogás
        + [(0.1, 0.4, 4.0)] * 5       # 0,5 mp futás
        + [(0.1, 0.6, 6.0)] * 6       # 0,6 mp sprint → számít (3,6 m)
        + [(0.1, 0.1, 1.0)] * 2
        + [(0.1, 0.7, 7.0)] * 4       # 0,4 mp villanás → nem sprint
        + [(0.1, 0.1, 1.0)] * 2
        + [(0.1, 0.55, 5.5)] * 5)     # 0,5 mp a végén → számít (2,75 m)
    st = PlayerStats(track_id=7)
    _sprint_and_zones(st, szakaszok)
    assert st.top_speed_ms == 7.0
    assert st.sprint_count == 2
    assert abs(st.sprint_distance_m - (3.6 + 2.75)) < 1e-9
    assert st.zone_seconds == {"seta": 1.4, "kocogas": 0.5, "futas": 0.5,
                               "sprint": 1.5}


def test_sprint_and_zones_a_zona_hatarok_a_gyorsabb_zonaba_esnek():
    """A határ-sebesség (1,4 / 3,0 / 5,0 m/s) már a GYORSABB zóna; az
    5,0 m/s már sprint-sebesség."""
    from handball.pipeline.stats import PlayerStats, _sprint_and_zones

    st = PlayerStats(track_id=1)
    _sprint_and_zones(st, [(1.0, 1.39, 1.39), (1.0, 1.4, 1.4),
                           (1.0, 2.99, 2.99), (1.0, 3.0, 3.0),
                           (1.0, 4.99, 4.99), (1.0, 5.0, 5.0)])
    assert st.zone_seconds == {"seta": 1.0, "kocogas": 2.0, "futas": 2.0,
                               "sprint": 1.0}
    assert st.sprint_count == 1 and st.sprint_distance_m == 5.0


def test_sprint_and_zones_szakasz_nelkul_nulla_ido():
    """Szakasz nélkül (nem mért játékos) minden zóna-idő 0, nincs sprint
    és nincs csúcssebesség — a zóna-szótár így is teljes."""
    from handball.pipeline.stats import PlayerStats, _sprint_and_zones

    st = PlayerStats(track_id=1)
    _sprint_and_zones(st, [])
    assert st.zone_seconds == {"seta": 0.0, "kocogas": 0.0, "futas": 0.0,
                               "sprint": 0.0}
    assert (st.top_speed_ms, st.sprint_count, st.sprint_distance_m) == (
        0.0, 0, 0.0)
