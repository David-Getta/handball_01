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
