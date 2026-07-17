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
