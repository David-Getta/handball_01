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
