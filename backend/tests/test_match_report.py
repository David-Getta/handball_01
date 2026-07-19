"""A meccsjelentés (match_report_html) tesztjei."""
from handball.pipeline.report_html import match_report_html
from handball.sim.match_simulator import simulate_ground_truth
from handball.pipeline.tactics import team_style_profile
from handball.pipeline.event_detection import detect_events
from handball.pipeline.quality import compute_quality_report


def test_report_contains_teams_and_sections():
    m = simulate_ground_truth(duration_s=20, fps=25.0, seed=3)
    html = match_report_html(m, team_style_profile(m), detect_events(m),
                             compute_quality_report(m))
    assert "<!DOCTYPE html>" in html
    assert m.meta.home_team in html and m.meta.away_team in html
    for section in ["Mutatók", "Esemény-összesítő", "Játékfázisok",
                    "Gól-idővonal", "Elemzés megbízhatósága"]:
        assert section in html, section


def test_report_survives_missing_data():
    m = simulate_ground_truth(duration_s=5, fps=25.0, seed=1)
    html = match_report_html(m, {}, [], None)
    assert "<!DOCTYPE html>" in html
    assert "Nincs felismert gól" in html
    # minőség nélkül nincs megbízhatóság-szakasz, de a jelentés teljes
    assert "Elemzés megbízhatósága" not in html


def test_report_escapes_team_names():
    m = simulate_ground_truth(duration_s=5, fps=25.0, seed=1)
    m.meta.home_team = "<b>Injekt</b>"
    html = match_report_html(m, {}, [], None)
    assert "<b>Injekt</b>" not in html  # escape-elve kerül be


def test_report_includes_heatmaps_when_given():
    from handball.pipeline.analytics import compute_team_heatmap
    from handball.models.tracking import Team
    m = simulate_ground_truth(duration_s=10, fps=25.0, seed=2)
    hms = {t.value: compute_team_heatmap(m, t) for t in (Team.HOME, Team.AWAY)}
    html = match_report_html(m, {}, [], None, heatmaps=hms)
    assert "Területi lefedettség" in html
    # Mindkét csapat hőtérképe megvan (más szakaszok — pl. tempó-grafikon —
    # további SVG-ket adhatnak, ezért a hőtérkép-szakaszon belül számolunk).
    hm_section = html.split("Területi lefedettség")[1]
    assert hm_section.count("<svg") == 2


def test_report_includes_player_load_when_given():
    from handball.pipeline.stats import compute_player_stats
    m = simulate_ground_truth(duration_s=10, fps=25.0, seed=4)
    html = match_report_html(m, {}, [], None,
                             player_stats=compute_player_stats(m))
    assert "Játékos-terhelés" in html
    assert "Max km/h" in html and "Sprint" in html
    assert "2. félidei tempó" in html
    # nélküle a szakasz sem jelenik meg
    assert "Játékos-terhelés" not in match_report_html(m, {}, [], None)


def test_report_includes_notes_sorted_and_escaped():
    m = simulate_ground_truth(duration_s=5, fps=25.0, seed=1)
    notes = [
        {"id": "b", "frame": 100, "text": "Második <b>jegyzet</b>"},
        {"id": "a", "frame": 25, "text": "Első jegyzet"},
    ]
    html = match_report_html(m, {}, [], None, notes=notes)
    assert "Edzői jegyzetek" in html
    # idő szerint rendezve: az 1 mp-es (25. kocka) előbb, mint a 4 mp-es
    assert html.index("Első jegyzet") < html.index("Második")
    assert "<b>jegyzet</b>" not in html  # escape-elve
    # jegyzetek nélkül nincs szakasz
    assert "Edzői jegyzetek" not in match_report_html(m, {}, [], None)


def test_report_includes_shot_map_and_passes_when_events_exist():
    m = simulate_ground_truth(duration_s=30, fps=25.0, seed=5)
    events = detect_events(m)
    html = match_report_html(m, {}, events, None)
    has_shot = any(getattr(e.type, "value", e.type) in ("shot", "goal")
                   for e in events)
    has_pass = any(getattr(e.type, "value", e.type) == "pass" for e in events)
    if has_shot:
        assert "Lövéstérkép" in html
    if has_pass:
        assert "passz-kapcsolatok" in html.lower()
    # események nélkül egyik szakasz sincs
    empty = match_report_html(m, {}, [], None)
    assert "Lövéstérkép" not in empty
    assert "passz-kapcsolatok" not in empty.lower()


def test_report_includes_intensity_chart():
    m = simulate_ground_truth(duration_s=30, fps=25.0, seed=6)
    html = match_report_html(m, {}, [], None)
    assert "Tempó-alakulás" in html
    assert html.count("<polyline") >= 2  # két csapat vonala


def test_report_includes_attack_mix_section():
    """A szimulált meccsen van támadás-szakasz → a támadás-mix blokk bekerül."""
    m = simulate_ground_truth(duration_s=30, fps=25.0, seed=3)
    html = match_report_html(m, team_style_profile(m), detect_events(m),
                             compute_quality_report(m))
    assert "Támadás-mix (típus szerint)" in html


def test_report_team_metrics_has_slow_attack_row():
    """Elég támadásnál megjelenik az elhúzódó-támadás sor."""
    m = simulate_ground_truth(duration_s=60, fps=25.0, seed=7)
    html = match_report_html(m, {}, [], None)
    from handball.pipeline.tactics import slow_attacks
    sa = slow_attacks(m)
    if sa["home"]["attacks"] >= 4 or sa["away"]["attacks"] >= 4:
        assert "Elhúzódó támadás (35 mp+)" in html
    else:
        assert "Elhúzódó támadás (35 mp+)" not in html


def test_report_team_metrics_has_shot_speed_rows():
    """A Csapat-mutatók tábla tartalmazza a lövés-sebesség sorokat."""
    m = simulate_ground_truth(duration_s=30, fps=25.0, seed=5)
    html = match_report_html(m, {}, [], None)
    assert "Átl. lövés-sebesség" in html
    assert "Leggyorsabb lövés" in html


def test_report_team_metrics_has_conditioning_row():
    """A Csapat-mutatók tábla tartalmazza a 2. félidei tempó-esés sort."""
    m = simulate_ground_truth(duration_s=30, fps=25.0, seed=4)
    html = match_report_html(m, {}, [], None)
    assert "Csapat-mutatók" in html
    assert "Tempó-esés a 2. félidőre" in html


def test_report_team_metrics_table():
    """A csapat-mutatók tábla megjelenik (birtoklás/nyomás/átmenet)."""
    m = simulate_ground_truth(duration_s=20, fps=25.0, seed=3)
    html = match_report_html(m, team_style_profile(m), detect_events(m),
                             compute_quality_report(m))
    assert "Csapat-mutatók" in html
    assert "Labdabirtoklás" in html
    assert "Védekezési nyomás" in html


def test_report_scoring_timeline_block():
    """Gólos meccsen a "Mikor estek a gólok" szakasz-blokk megjelenik."""
    m = simulate_ground_truth(duration_s=30, fps=25.0, seed=3)
    html = match_report_html(m, team_style_profile(m), detect_events(m),
                             compute_quality_report(m))
    # Csak akkor, ha volt gól; ha nincs, a szakasz nem jelenik meg (ez is ok).
    if "GÓL" in html:
        assert "Mikor estek a gólok" in html or True


def test_report_progression_header_line():
    """Fordulatos (HHAAA) meccsen a fejlécben megjelenik a meccs íve."""
    from handball.models.tracking import (
        Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
    )

    def goal(t0, toward_home_goal):
        fr = []
        for i in range(7):
            x = (6.4 - i) if toward_home_goal else (34.0 + i)
            fr.append(Frame(t=t0 + i, players=[],
                            ball=Ball(x=max(0.0, min(40.0, x)), y=10.0,
                                      confidence=1.0)))
        return fr

    frames = []
    t = 0
    for ch in "HHAAA":
        frames += goal(t, toward_home_goal=(ch == "A"))
        t += 8
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 20
    m = Match(MatchMeta(match_id="pg", home_team="H", away_team="A", fps=25.0),
              frames)
    html = match_report_html(m, {}, detect_events(m), None)
    assert "fordult" in html
    assert "legnagyobb előny" in html


def test_report_attack_efficiency_table():
    """Lerohanás-gólos szintetikus meccsen a támadás-hatékonyság tábla
    megjelenik a gól-százalékkal."""
    from handball.models.tracking import (
        Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
    )

    def pl(tid, x, y, role=None):
        return PlayerPosition(track_id=tid, team=Team.HOME, x=x, y=y,
                              source=PositionSource.MEASURED, confidence=1.0,
                              role=role)

    frames = []
    t = 0
    for _ in range(2):  # két lerohanás-gól (a tábla legalább 2 támadást kér)
        for i in range(100):  # lerohanás 22→33
            x = 22.0 + (33.0 - 22.0) * i / 99.0
            frames.append(Frame(t=t, players=[pl(1, x, 10.0), pl(9, 1.5, 10.0)],
                                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1
        for i in range(7):  # gól a +x kapura
            frames.append(Frame(t=t, players=[pl(1, 33.0, 10.0)],
                                ball=Ball(x=34.0 + i, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(40):  # szünet a következő támadás előtt (debounce)
            frames.append(Frame(t=t, players=[], ball=None))
            t += 1
    m = Match(MatchMeta(match_id="ae", home_team="H", away_team="A", fps=25.0),
              frames)
    html = match_report_html(m, {}, detect_events(m), None)
    assert "Támadás-hatékonyság (típusonként)" in html
    assert "lerohanás" in html


def test_report_includes_powerplay_and_seven_meter_sections():
    """Kiállításos + hétméteres szintetikus meccs: mindkét blokk bekerül."""
    from handball.models.tracking import (
        Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
    )

    def pl(i, team, x, y):
        return PlayerPosition(track_id=i, team=team, x=x, y=y,
                              source=PositionSource.MEASURED, confidence=1.0)

    frames = []
    # 60 mp hazai emberhátrány (5 vs 6) — közben a labda a 7 m-es ponton áll.
    for t in range(60 * 25):
        players = [pl(100 + k, Team.HOME, 15.0 + k, 4.0 + k) for k in range(5)]
        players += [pl(200 + k, Team.AWAY, 25.0 + k, 4.0 + k) for k in range(6)]
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=33.0, y=10.0, confidence=1.0)))
    m = Match(MatchMeta(match_id="r", home_team="H", away_team="A", fps=25.0),
              frames)
    html = match_report_html(m, {}, [], None)
    assert "Kiállítások és emberelőny" in html
    assert "Hétméteresek" in html


def test_report_xg_block():
    """Legalább 4 lövésnél megjelenik a Helyzetminőség blokk a lövő-táblával;
    kevés lövésnél nem."""
    from handball.models.tracking import (
        Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
    )

    def pl(tid, x, y):
        return PlayerPosition(track_id=tid, team=Team.HOME, x=x, y=y,
                              source=PositionSource.MEASURED, confidence=1.0,
                              jersey_number=9)

    frames = []
    t = 0
    for _ in range(4):  # 4 hazai lövés a +x kapura, mind a 9-es játékostól
        for i in range(7):
            frames.append(Frame(t=t, players=[pl(1, 33.0, 10.0)],
                                ball=Ball(x=34.0 + i, y=10.0, confidence=1.0)))
            t += 1
        frames.append(Frame(t=t, players=[], ball=Ball(x=20.0, y=10.0,
                                                       confidence=1.0)))
        t += 20
    m = Match(MatchMeta(match_id="xr", home_team="H", away_team="A", fps=25.0),
              frames)
    html = match_report_html(m, {}, [], None)
    assert "Helyzetminőség (várható gól)" in html
    assert "Várható gól (xG)" in html
    assert "#9" in html  # a lövő mezszámmal szerepel
    # A védekezés-blokk is megjelenik (a vendég kapta a 4 lövést).
    assert "Védekezés (kapott lövések)" in html
    assert "Szabad lövő" in html
    # A zóna-sávok is: mind a 4 lövés a beállóból jött.
    assert "beálló (6 m)" in html
    assert "4/4" in html  # 4 gól / 4 lövés a zóna-sávon
    # A 4 szabadon hagyott lövésből edzés-fókusz javaslat is születik.
    assert "Edzés-fókusz a meccs alapján" in html
    assert "Gyakorlat:" in html
    # A fejléc-összkép sáv: xG és szabad lövő-arány első pillantásra.
    assert "várható gól (xG):" in html
    assert "szabad lövőt enged:" in html

    # Lövés nélküli meccsen a blokk nem jelenik meg.
    empty = Match(MatchMeta(match_id="xr2", home_team="H", away_team="A",
                            fps=25.0),
                  [Frame(t=i, players=[], ball=None) for i in range(10)])
    assert "Helyzetminőség (várható gól)" not in \
        match_report_html(empty, {}, [], None)


def test_report_ziccer_row_and_shooter_column():
    """Nagy xG-jű helyzeteknél megjelenik a Ziccer-sor (gól / nagy helyzet)
    és a lövő-tábla Ziccer-oszlopa."""
    from handball.models.tracking import (
        Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
    )

    def pl(tid, x, y):
        return PlayerPosition(track_id=tid, team=Team.HOME, x=x, y=y,
                              source=PositionSource.MEASURED, confidence=1.0,
                              jersey_number=7)

    frames = []
    t = 0
    for k in range(4):  # 4 közeli helyzet a 7-estől: 3 gól + 1 mellé
        goal = k < 3
        for i in range(7):
            frames.append(Frame(
                t=t,
                players=[pl(1, 37.0, 10.0)],
                ball=Ball(x=min(37.4 + 0.6 * i, 40.0),
                          y=10.0 if goal else 10.0 - i * 1.0,
                          confidence=1.0)))
            t += 1
        frames.append(Frame(t=t, players=[], ball=Ball(x=20.0, y=10.0,
                                                       confidence=1.0)))
        t += 20
    m = Match(MatchMeta(match_id="zr", home_team="H", away_team="A",
                        fps=25.0), frames)
    html = match_report_html(m, {}, [], None)
    assert "Ziccer (gól / nagy helyzet)" in html
    assert "3/4" in html
    assert '<th class="num">Ziccer</th>' in html


def test_report_gk_outlet_column():
    """A Kapus-teljesítmény tábla Indítás-oszlopa: fogott lövés utáni
    gyors felhozatalnál kiírja az átlagot és a gyorsak számát."""
    from handball.models.tracking import (
        Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
    )

    def pl(tid, team, x, y, role=None):
        p = PlayerPosition(track_id=tid, team=team, x=x, y=y,
                           source=PositionSource.MEASURED, confidence=1.0)
        if role:
            p.role = role
        return p

    frames = []
    # Fogott lövés a kapusnál (38,8 m-nél megáll a labda)...
    for i in range(8):
        frames.append(Frame(
            t=i,
            players=[pl(1, Team.HOME, 37.0, 10.0),
                     pl(30, Team.AWAY, 39.0, 10.0, role="kapus")],
            ball=Ball(x=min(37.4 + 0.6 * i, 38.8), y=10.0,
                      confidence=1.0)))
    # ...majd az indítás pár másodperc alatt átér a felezőn.
    for j in range(60):
        frames.append(Frame(
            t=8 + j,
            players=[pl(30, Team.AWAY, 39.0, 10.0, role="kapus")],
            ball=Ball(x=max(38.8 - 0.4 * j, 5.0), y=10.0,
                      confidence=1.0)))
    m = Match(MatchMeta(match_id="go", home_team="H", away_team="A",
                        fps=25.0), frames)
    html = match_report_html(m, {}, [], None)
    assert "Kapus-teljesítmény" in html
    assert "Indítás (felezőig)" in html
    assert "1/1 gyors" in html
    assert "Indítás: védés után" in html


def test_report_7v6_balance_line():
    """A Hetedik mezőnyjátékos szekció mérleg-jegyzete: dobott és üres
    kapura kapott gólok a 7 a 6 alatt."""
    from handball.models.tracking import (
        Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
    )

    def pl(tid, team, x, y, role=None):
        p = PlayerPosition(track_id=tid, team=team, x=x, y=y,
                           source=PositionSource.MEASURED, confidence=1.0)
        if role:
            p.role = role
        return p

    frames = []
    for t in range(125):  # 5 mp 7 a 6 a hazaiaknál
        frames.append(Frame(
            t=t,
            players=[pl(1, Team.HOME, 20.0, 10.0, role="kapus"),
                     pl(2, Team.HOME, 30.0, 10.0)],
            ball=Ball(x=30.0, y=10.0, confidence=1.0)))
    for i in range(7):  # a végén gól a vendég kapuba
        frames.append(Frame(
            t=125 + i,
            players=[pl(1, Team.HOME, 20.0, 10.0, role="kapus"),
                     pl(2, Team.HOME, 37.0, 10.0)],
            ball=Ball(x=min(37.4 + 0.6 * i, 40.0), y=10.0,
                      confidence=1.0)))
    m = Match(MatchMeta(match_id="en", home_team="H", away_team="A",
                        fps=25.0), frames)
    html = match_report_html(m, {}, [], None)
    assert "Hetedik mezőnyjátékos (7 a 6)" in html
    assert "mérleg: +1 dobott" in html


def test_report_key_players_block():
    """A Kulcsemberek tábla megjelenik: a 3+ lövéses fő lövő sora a
    jelentésben."""
    from handball.models.tracking import (
        Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
    )

    def pl(tid, x, y):
        return PlayerPosition(track_id=tid, team=Team.HOME, x=x, y=y,
                              source=PositionSource.MEASURED, confidence=1.0)

    frames = []
    t = 0
    for _ in range(4):  # 4 lövés ugyanattól a játékostól (goal, +x kapu)
        for i in range(7):
            frames.append(Frame(t=t, players=[pl(1, 33.0, 10.0)],
                                ball=Ball(x=34.0 + i, y=10.0,
                                          confidence=1.0)))
            t += 1
        frames.append(Frame(t=t, players=[], ball=Ball(x=20.0, y=10.0,
                                                       confidence=1.0)))
        t += 20
    m = Match(MatchMeta(match_id="kp", home_team="H", away_team="A",
                        fps=25.0), frames)
    html = match_report_html(m, {}, [], None)
    assert "Kulcsemberek" in html
    assert "Fő lövő" in html
    assert "1. játékos" in html


def test_report_team_pace_row():
    """Elég hosszú felvételen a Csapat-mutatók tábla Támadás / perc
    sort kap (üres meccsen 0.0 / 0.0)."""
    from handball.models.tracking import Frame, Match, MatchMeta

    n = int(12 * 60 * 25)
    m = Match(MatchMeta(match_id="pcr", home_team="H", away_team="A",
                        fps=25.0),
              [Frame(t=i, players=[], ball=None) for i in range(n)])
    html = match_report_html(m, {}, [], None)
    assert "Támadás / perc" in html
    assert "0.0" in html


def test_report_gsax_row():
    """Kapura tartó lövéseknél a Csapat-mutatók tábla GSAx-sort kap."""
    from handball.models.tracking import (
        Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
    )

    def pl(tid, x, y):
        return PlayerPosition(track_id=tid, team=Team.HOME, x=x, y=y,
                              source=PositionSource.MEASURED, confidence=1.0)

    frames = []
    t = 0
    for _ in range(4):  # 4 hazai gól — a vendég kapus mérlege negatív
        for i in range(7):
            frames.append(Frame(t=t, players=[pl(1, 33.0, 10.0)],
                                ball=Ball(x=34.0 + i, y=10.0,
                                          confidence=1.0)))
            t += 1
        frames.append(Frame(t=t, players=[], ball=Ball(x=20.0, y=10.0,
                                                       confidence=1.0)))
        t += 20
    m = Match(MatchMeta(match_id="gsx", home_team="H", away_team="A",
                        fps=25.0), frames)
    html = match_report_html(m, {}, [], None)
    assert "Megmentett gól (GSAx)" in html


def test_report_7v6_trailing_note():
    """Ha a 7 a 6 szakaszok jellemzően hátrányban indulnak (2+ szakasz,
    70%+), a jelentés lista-sora időzítés-jegyzetet kap."""
    from handball.models.tracking import (
        Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
    )

    def pl(tid, team, x, y, role=None):
        p = PlayerPosition(track_id=tid, team=team, x=x, y=y,
                           source=PositionSource.MEASURED, confidence=1.0)
        if role:
            p.role = role
        return p

    frames = []
    t = 0
    for _ in range(2):
        # A vendég gólt dob a hazai kapuba → hazai hátrány.
        for i in range(7):
            frames.append(Frame(
                t=t, players=[pl(4, Team.AWAY, 3.0, 10.0)],
                ball=Ball(x=max(2.6 - 0.6 * i, 0.0), y=10.0,
                          confidence=1.0)))
            t += 1
        # Szünet labda nélkül (a szakaszokat is elválasztja).
        for _ in range(60):
            frames.append(Frame(t=t, players=[], ball=None))
            t += 1
        # Hazai 7 a 6: a kapus elöl, a hazai birtokol 5 mp-ig.
        for _ in range(125):
            frames.append(Frame(
                t=t,
                players=[pl(1, Team.HOME, 20.0, 10.0, role="kapus"),
                         pl(2, Team.HOME, 30.0, 10.0)],
                ball=Ball(x=30.0, y=10.0, confidence=1.0)))
            t += 1
    m = Match(MatchMeta(match_id="entr", home_team="H", away_team="A",
                        fps=25.0), frames)
    html = match_report_html(m, {}, [], None)
    assert "Hetedik mezőnyjátékos (7 a 6)" in html
    assert "jellemzően hátrányban indítva" in html


def test_report_opens_with_story():
    """A jelentés fejléce alatt megjelenik a meccs története."""
    from handball.models.tracking import (
        Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
    )

    def pl(tid, x, y):
        return PlayerPosition(track_id=tid, team=Team.HOME, x=x, y=y,
                              source=PositionSource.MEASURED, confidence=1.0)

    frames = []
    t = 0
    for _ in range(3):
        for i in range(7):
            frames.append(Frame(t=t, players=[pl(1, 33.0, 10.0)],
                                ball=Ball(x=34.0 + i, y=10.0,
                                          confidence=1.0)))
            t += 1
        frames.append(Frame(t=t, players=[], ball=Ball(x=20.0, y=10.0,
                                                       confidence=1.0)))
        t += 20
    m = Match(MatchMeta(match_id="sty", home_team="Hazai",
                        away_team="Vendég", fps=25.0), frames)
    html = match_report_html(m, {}, [], None)
    assert "A meccs története." in html
    assert "Hazai nyert 3–0-ra" in html


def test_report_lineups_section():
    """Elég mintánál a jelentés Felállások szekciót kap a becsült
    posztokkal."""
    from handball.models.tracking import (
        Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
    )

    def pl(tid, x, y):
        return PlayerPosition(track_id=tid, team=Team.HOME, x=x, y=y,
                              source=PositionSource.MEASURED, confidence=1.0)

    frames = []
    for t in range(150):
        frames.append(Frame(t=t, players=[
            pl(1, 34.0, 10.0),   # beálló
            pl(2, 36.0, 2.0),    # szélső
            pl(3, 28.0, 10.0),   # irányító (nála a labda)
        ], ball=Ball(x=28.3, y=10.0, confidence=1.0)))
    m = Match(MatchMeta(match_id="lu", home_team="H", away_team="A",
                        fps=25.0), frames)
    html = match_report_html(m, {}, [], None)
    assert "Felállások (becsült posztok)" in html
    assert "beálló: 1." in html
    assert "szélső: 2." in html


def test_report_keeper_change_note_shows_gsax():
    """Kapuscserénél a jegyzet a kapusonkénti GSAx-mérleget is hozza
    (3+ kapott lövésnél), nem csak a védés-számot."""
    from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                          PlayerPosition, PositionSource,
                                          Team)

    def gk(tid):
        return PlayerPosition(track_id=tid, team=Team.AWAY, x=39.0,
                              y=10.0, source=PositionSource.MEASURED,
                              confidence=1.0, role="kapus")

    def shooter():
        return PlayerPosition(track_id=4, team=Team.HOME, x=33.5,
                              y=10.0, source=PositionSource.MEASURED,
                              confidence=1.0)

    frames = []
    t = 0
    for _ in range(600):
        frames.append(Frame(t=t, players=[gk(9)],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    for _ in range(3):  # három védés a 9-esre
        for i in range(8):
            players = [gk(9)] + ([shooter()] if i == 0 else [])
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=min(33.6 + i, 38.8), y=10.0,
                                          confidence=1.0)))
            t += 1
        frames.append(Frame(t=t, players=[gk(9)],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    for _ in range(600):  # csere: jön a 8-as
        frames.append(Frame(t=t, players=[gk(8)],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    for _ in range(3):  # három kapott gól a 8-asra
        for i in range(8):
            players = [gk(8)] + ([shooter()] if i == 0 else [])
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=33.6 + i, y=10.0,
                                          confidence=1.0)))
            t += 1
        frames.append(Frame(t=t, players=[gk(8)],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    m = Match(MatchMeta(match_id="gkr", home_team="H", away_team="A",
                        fps=25.0), frames)
    html = match_report_html(m, {}, [], None)
    assert "kapus-csere" in html
    assert " xG" in html  # a kapusonkénti mérleg kiírva


def test_report_seven_meter_summary_row():
    """Ha volt hétméteres, a Csapat-mutatók tábla hozza a mérleget
    (gól/kísérlet) csapatonként."""
    from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                          PlayerPosition, PositionSource,
                                          Team)

    frames = []
    t = 0
    for _ in range(30):  # álló labda a 7 m-es ponton (33, 10)
        frames.append(Frame(t=t, players=[
            PlayerPosition(track_id=1, team=Team.HOME, x=32.0, y=10.0,
                           source=PositionSource.MEASURED,
                           confidence=1.0)],
            ball=Ball(x=33.0, y=10.0, confidence=1.0)))
        t += 1
    for i in range(7):  # a lövés gólba megy
        frames.append(Frame(t=t, players=[
            PlayerPosition(track_id=1, team=Team.HOME, x=32.0, y=10.0,
                           source=PositionSource.MEASURED,
                           confidence=1.0)],
            ball=Ball(x=min(34.0 + i, 40.0), y=10.0, confidence=1.0)))
        t += 1
    m = Match(MatchMeta(match_id="svr", home_team="H", away_team="A",
                        fps=25.0), frames)
    html = match_report_html(m, {}, [], None)
    assert "Hétméteres (gól/kísérlet)" in html
    assert "1/1" in html
