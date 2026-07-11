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
    assert html.count("<svg") == 2  # mindkét csapat hőtérképe


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
