"""
Tesztek a felderítő jelentés HTML-exportjára (report_html.py).

Futtatás:
    python tests/test_report_html.py
"""

from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.pipeline.scouting import ScoutingReport
from handball.pipeline.report_html import scouting_report_html


def _rep(**kw):
    base = dict(
        team="away", team_name="Szeged", matches=2,
        attack_share_pct=62.0, fast_break_pct=14.0,
        avg_ball_speed_ms=4.2, avg_attack_duration_s=8.5,
        defense_main="6-0", defense_distribution={"6-0": 80.0, "5-1": 20.0},
        attack_centroid_x=30.0, attack_centroid_y=10.0,
        num_figures=3, attacks=12, shots=10, goals=6, turnovers=2,
        shot_efficiency_pct=60.0,
        key_players=[{"track_id": 7, "possession_frames": 120,
                      "distance_m": 340.5, "role": "irányító"}],
        strengths=["Gyors indítás (14%)"], weaknesses=["Sok labdaeladás"],
        keys_to_game=["Mély 6-0 faluk ellen: 9 m-es lövés és beúszó."],
    )
    base.update(kw)
    return ScoutingReport(**base)


def test_defense_zone_block():
    """A védekezési zóna-blokk csak def_zones-szal jelenik meg, a szabad
    lövések számával a sáv-feliratban."""
    rep = _rep(def_zones={"beálló (6 m)": {"shots": 5, "goals": 3, "free": 2},
                          "balszél": {"shots": 2, "goals": 0, "free": 0}})
    html = scouting_report_html(rep)
    assert "Honnan kapják a lövéseket" in html
    assert "3/5 · szabad: 2" in html
    assert "0/2" in html
    # def_zones nélkül a blokk nem jelenik meg.
    assert "Honnan kapják a lövéseket" not in scouting_report_html(_rep())


def test_contains_core_content():
    """A HTML tartalmazza a csapatnevet, a kulcsokat és a védőformát."""
    html = scouting_report_html(_rep())
    assert "Szeged" in html
    assert "Hogyan játssz ellenük" in html
    assert "6-0" in html
    assert "9 m-es lövés" in html
    assert "irányító" in html
    assert "2 meccs alapján" in html


def test_self_contained_no_external_refs():
    """Önálló fájl: nincs külső betöltés (http src/href), a stílus beágyazott."""
    html = scouting_report_html(_rep())
    assert "<style>" in html
    assert 'src="http' not in html and 'href="http' not in html


def test_escapes_html_in_names():
    """A csapatnév/szövegek escape-elve kerülnek be (nincs HTML-injektálás)."""
    html = scouting_report_html(_rep(team_name='<b>Rossz&Név</b>',
                                     keys_to_game=['<script>x</script>']))
    assert "<b>Rossz&Név</b>" not in html
    assert "&lt;b&gt;" in html and "&amp;" in html
    assert "<script>x</script>" not in html


def test_empty_lists_show_placeholders():
    """Üres listáknál tájékoztató sor jelenik meg, nem üres blokk."""
    html = scouting_report_html(_rep(strengths=[], weaknesses=[],
                                     key_players=[], defense_distribution={}))
    assert "Nincs kiemelkedő erősség" in html
    assert "Nincs elég védekező minta" in html
    assert "Több meccs felderítése pontosítja" in html


def test_defense_bar_widths_clamped():
    """A sáv-szélesség 0–100% közé vágva kerül a stílusba."""
    html = scouting_report_html(_rep(defense_distribution={"6-0": 140.0, "5-1": -5.0}))
    assert "width:100%" in html
    assert "width:0%" in html


def test_playbook_section_rendering():
    """A figura-egyezés szakasz megjelenik, escape-elve; enélkül nincs szakasz."""
    pm = {"total_attacks": 5, "matched": {"<Beúszós> kereszt": 3}, "unmatched": 2}
    html = scouting_report_html(_rep(), playbook_match=pm)
    assert "Ismert figuráik" in html
    assert "&lt;Beúszós&gt; kereszt" in html and "<Beúszós>" not in html
    assert "3×" in html and "5 támadásból 2 ismeretlen" in html
    # nélküle a szakasz sem jelenik meg
    assert "Ismert figuráik" not in scouting_report_html(_rep())


def test_playbook_section_empty_states():
    """Üres egyezésnél tájékoztató szöveg (nem üres blokk)."""
    html = scouting_report_html(_rep(), playbook_match={"total_attacks": 4, "matched": {}, "unmatched": 4})
    assert "sem egyezik mentett figurával" in html


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    print(f"\n{'OK' if failures == 0 else failures} hibás teszt")
    raise SystemExit(1 if failures else 0)


def test_scouting_report_role_table():
    """A felderítő jelentés szerep-táblája a küszöböt elérő profilokat
    mutatja; küszöb alatt a szekció elmarad."""
    from handball.pipeline.report_html import scouting_report_html
    from handball.pipeline.scouting import ScoutingReport

    rep = ScoutingReport(
        team="away", team_name="Ellenfél", matches=2,
        shooter_zones=[{"player_id": 7, "zone": "átlövés bal",
                        "shots": 5}],
        blockers=[{"player_id": 5, "blocks": 4}],
        seven_takers=[{"player_id": 11, "attempts": 3, "goals": 2}],
        fb_finishers=[{"player_id": 9, "goals": 2}],
        gk_outlets=4,
        gk_outlet_targets=[{"player_id": 12, "n": 3}])
    html = scouting_report_html(rep)
    assert "Kikre készülj (szerepek)" in html
    for frag in ("Fő lövő", "7. játékos", "A fal kulcsa", "Hetes-dobó",
                 "Kontra-befejező", "Indítás-célpont"):
        assert frag in html, frag

    empty = ScoutingReport(team="away", team_name="Ellenfél")
    assert "Kikre készülj (szerepek)" not in scouting_report_html(empty)


def test_scouting_report_matchup_section():
    """A meccsterv-mondatok külön szakaszként kerülnek a felderítő
    HTML-be; nélkülük a szakasz elmarad."""
    from handball.pipeline.report_html import scouting_report_html
    from handball.pipeline.scouting import ScoutingReport

    rep = ScoutingReport(team="away", team_name="Ellenfél")
    html = scouting_report_html(
        rep, matchup=["A kontra az első számú fegyveretek."])
    assert "Meccsterv (a kettőnk párosítása)" in html
    assert "első számú fegyveretek" in html
    assert "Meccsterv" not in scouting_report_html(rep)


def test_scouting_report_seven_direction_table():
    """A felderítő jelentés hozza a hetes-dobók irány-tábláját (2+
    kísérletnél), irány-adat nélkül "—" jellel."""
    rep = ScoutingReport(
        team="away", team_name="Ellenfél",
        seven_takers=[
            {"player_id": 7, "attempts": 4, "goals": 3,
             "dirs": {"bal": 3, "közép": 1}},
            {"player_id": 9, "attempts": 2, "goals": 2, "dirs": {}},
            {"player_id": 4, "attempts": 1, "goals": 0, "dirs": {}},
        ])
    html = scouting_report_html(rep)
    assert "Hetes-dobóik (irányokkal)" in html
    assert "balra 3×" in html and "középre 1×" in html
    assert "7. játékos" in html and "9. játékos" in html
    assert "4. játékos" not in html  # 1 kísérlet a küszöb alatt


def test_trend_report_html_renders_metrics_and_summary():
    """A fejlődés-riport HTML hozza a mutató-táblát (irány-jelekkel) és
    az összegzést."""
    from handball.pipeline.report_html import trend_report_html
    tr = {
        "team_name": "Mi csapatunk",
        "older_matches": 3, "newer_matches": 2,
        "metrics": [
            {"metric": "goals", "label": "Gól / meccs", "unit": "",
             "older": 24.0, "newer": 28.0, "delta": 4.0,
             "better": True},
            {"metric": "turnovers", "label": "Labdaeladás / meccs",
             "unit": "", "older": 10.0, "newer": 13.0, "delta": 3.0,
             "better": False},
        ],
        "summary": ["Javulás: gól / meccs 24.0 → 28.0."],
    }
    html = trend_report_html(tr)
    assert "FEJLŐDÉS-RIPORT" in html and "Mi csapatunk" in html
    assert "Gól / meccs" in html and "▲" in html and "▼" in html
    assert "Javulás: gól / meccs" in html


def test_player_season_html_totals_and_rows():
    """A szezon-lap hozza az összesítőt és a meccsenkénti sorokat; a
    nem mért cellák "—" jellel."""
    from handball.pipeline.report_html import player_season_html
    points = [
        {"match_id": "m1", "date": "2026-01-10", "opponent": "A",
         "distance_m": 4200.0, "top_speed_ms": 6.5, "sprint_count": 9,
         "minutes": 42.0, "shots": 5, "goals": 3, "xg": 2.4,
         "xg_diff": 0.6},
        {"match_id": "m2", "date": "2026-01-17", "opponent": "B",
         "distance_m": 3900.0, "top_speed_ms": 6.9, "sprint_count": 7,
         "minutes": 38.0, "shots": 0, "goals": 0, "xg": None,
         "xg_diff": None},
    ]
    html = player_season_html("Mi", 7, points)
    assert "SZEZON-LAP" in html and "#7 — Mi" in html
    assert "3/5" in html            # gól/lövés az összesítőben és a sorban
    assert "2026-01-17" in html and "—" in html
    assert "Csúcssebesség" in html
