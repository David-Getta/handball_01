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


def test_figura_ajanlo_szakasz():
    """A saját figuráink rangsora a tanult faluk ellen: az ajánló mondat
    és legfeljebb FIGURA_AJANLO_SOROK sor, escape-elve; üres rangsornál
    nincs szakasz."""
    from handball.pipeline.report_html import FIGURA_AJANLO_SOROK

    sorok = [{"id": str(i), "name": f"<F{i}>", "pont_pct": 60.0 - i,
              "alap_pct": 50.0} for i in range(FIGURA_AJANLO_SOROK + 2)]
    html = scouting_report_html(_rep(), figura_ajanlo={
        "figurak": sorok, "ajanlas": "Ellenük a(z) „<F0>” figura …"})
    assert "Figuráink ellenük" in html
    assert "Ellenük a(z) „&lt;F0&gt;” figura" in html
    assert "60% lövőhelyzet (alap fal: 50%)" in html
    assert f"&lt;F{FIGURA_AJANLO_SOROK - 1}&gt;" in html
    assert f"&lt;F{FIGURA_AJANLO_SOROK}&gt;" not in html
    assert "Figuráink ellenük" not in scouting_report_html(
        _rep(), figura_ajanlo={"figurak": [], "ajanlas": None})


def test_a_visszatero_figurak_szakasza_rajzzal():
    """A meccsről meccsre visszatérő figurák alakkal (inline SVG) és
    edzői névvel; visszatérő figura nélkül a szakasz nincs."""
    shape = [0.0] * 18
    shape[5] = 0.6
    shape[4] = 0.4
    lib = {"figures": [], "recurring": [
        {"zone": "bal oldal, a kapuelőtér előtt", "matches": 3,
         "attacks": 11, "shots": 8, "goals": 4, "goal_pct": 36.4,
         "shape": shape}], "verdict": "x"}
    html = scouting_report_html(_rep(setplay_library=lib))
    assert "Visszatérő figuráik" in html
    assert "bal oldal, a kapuelőtér előtt" in html
    # Elnevezett figura: a név elöl, a zóna zárójelben.
    lib["recurring"][0]["name"] = "Beúszós <kereszt>"
    nevvel = scouting_report_html(_rep(setplay_library=lib))
    assert "<b>Beúszós &lt;kereszt&gt;</b> (bal oldal, a kapuelőtér előtt)" in nevvel
    assert "3 meccsen 11 támadás, 4 gól (36%)" in html
    assert html.count("<svg") >= 2 and "<img" not in html   # jelkép + alak
    ures = scouting_report_html(_rep(setplay_library={"recurring": []}))
    assert "Visszatérő figuráik" not in ures


def test_a_szezon_riport_a_sajat_visszatero_figurakat_is_rajzolja():
    """A szezon-riportban a SAJÁT csapat meccsről meccsre visszatérő
    figurái is ott vannak (rajzzal, hozammal); könyvtár nélkül a
    szakasz elmarad."""
    from handball.pipeline.report_html import season_report_html

    shape = [0.0] * 18
    shape[4] = 1.0
    lib = {"figures": [], "recurring": [
        {"zone": "közép, a 9-es körül", "matches": 4, "attacks": 15,
         "shots": 10, "goals": 6, "goal_pct": 40.0, "shape": shape}],
        "verdict": "x"}
    tr = {"metrics": [], "summary": [], "older_matches": 2,
          "newer_matches": 2}
    html = season_report_html("Szeged", tr, [], 4, figure_library=lib)
    assert "Saját visszatérő figuráink" in html
    assert "4 meccsen 15 támadás, 6 gól (40%)" in html
    assert "Saját visszatérő figuráink" not in season_report_html(
        "Szeged", tr, [], 4)


def test_a_szezon_riport_a_jatekos_modellt_is_hozza():
    """A szezon-riportban a tanult játékos-modell szakasza: a lövők és a
    kapus sora (a motor mondatai), a meccsszám a jegyzetben; ha csak az
    egyik sor van, a másik "nincs eltérő sáv"; mindkettő üresen (vagy
    modell nélkül) a szakasz elmarad."""
    from handball.pipeline.report_html import season_report_html

    tr = {"metrics": [], "summary": [], "older_matches": 2,
          "newer_matches": 2}
    jm = {"lovok": "a lövők: a 7-es távolról 1,3× annyit lő be, mint "
                   "amennyit a helyzetei érnek",
          "kapus": "a kapus távolról 1,2× annyi gólt kap, mint az átlag",
          "meccsek": 4}
    html = season_report_html("Szeged", tr, [], 4, jatekos_modell=jm)
    assert "<h2>A szezon játékos-modellje</h2>" in html
    assert f"<p><b>Lövők:</b> {jm['lovok']}</p>" in html
    assert f"<p><b>Kapus:</b> {jm['kapus']}</p>" in html
    assert "a szezon 4 meccséből" in html
    csak = season_report_html("Szeged", tr, [], 4,
                              jatekos_modell={"lovok": jm["lovok"],
                                              "kapus": "", "meccsek": 4})
    assert "<p><b>Kapus:</b> nincs az átlagtól érdemben eltérő tanult sáv</p>" in csak
    for ures in (None, {}, {"lovok": "", "kapus": "", "meccsek": 4}):
        assert "A szezon játékos-modellje" not in season_report_html(
            "Szeged", tr, [], 4, jatekos_modell=ures)


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


def test_player_season_html_goalkeeper_columns():
    """Kapus mezszámnál a szezon-lap Védés és GSAx oszlopot + kapus-
    összesítőt hoz; mezőnyjátékosnál ezek nincsenek."""
    from handball.pipeline.report_html import player_season_html
    gk_points = [
        {"match_id": "m1", "date": "2026-01-10", "opponent": "A",
         "distance_m": 900.0, "top_speed_ms": 4.0, "sprint_count": 1,
         "minutes": 55.0, "shots": 0, "goals": 0, "xg": None,
         "xg_diff": None, "gk_on_target": 12, "gk_saves": 5,
         "gk_prevented": 1.2},
        {"match_id": "m2", "date": "2026-01-17", "opponent": "B",
         "distance_m": 850.0, "top_speed_ms": 4.2, "sprint_count": 0,
         "minutes": 60.0, "shots": 0, "goals": 0, "xg": None,
         "xg_diff": None, "gk_on_target": 8, "gk_saves": 4,
         "gk_prevented": -0.4},
    ]
    html = player_season_html("Mi", 16, gk_points)
    assert "Védés összesen" in html and "9/20 (45%)" in html
    assert "GSAx összesen" in html and "+0.8" in html
    assert "5/12" in html and "4/8" in html
    field_points = [{"match_id": "m1", "date": "2026-01-10",
                     "opponent": "A", "distance_m": 4200.0,
                     "top_speed_ms": 6.5, "sprint_count": 9,
                     "minutes": 42.0, "shots": 5, "goals": 3,
                     "xg": 2.4, "xg_diff": 0.6, "gk_on_target": None,
                     "gk_saves": None, "gk_prevented": None}]
    html2 = player_season_html("Mi", 7, field_points)
    assert "Védés összesen" not in html2 and "GSAx" not in html2


def test_a_szezon_riport_a_jatekos_modell_fejlodeset_is_hozza():
    """A szezon-riport fejlődés-szakasza a lövő- és a kapus-sorokkal;
    üres sorokkal (vagy nélküle) elmarad."""
    from handball.pipeline.report_html import season_report_html

    tr = {"metrics": [], "summary": [], "older_matches": 2,
          "newer_matches": 2}
    fj = {"lovo_sorok": ["a 7-es távolról 0,9× → 1,2× (javul)"],
          "kapus_sorok": ["a kapus távolról 1,2× → 0,9× annyi gólt kap, "
                          "mint az átlag (javul)"]}
    html = season_report_html("Szeged", tr, [], 4, fejlodes=fj)
    assert "A játékos-modell fejlődése (első fél → második fél)" in html
    assert "<li>a 7-es távolról 0,9× → 1,2× (javul)</li>" in html
    assert "<li>a kapus távolról 1,2× → 0,9× annyi gólt kap" in html
    for ures in (None, {}, {"lovo_sorok": [], "kapus_sorok": []}):
        assert "A játékos-modell fejlődése" not in season_report_html(
            "Szeged", tr, [], 4, fejlodes=ures)


def test_h2h_report_html_jatekos_modell_szakasz():
    """Az egymás-elleni riport játékos-modell szakasza: csapatonként csak
    a nem üres sorok (lövőik, kapusuk, utolsó labdájuk ellenük, kit
    kinek, engedett lövő), a meccsszám a jegyzetben; üres / hiányzó
    modellel a szakasz elmarad."""
    from handball.pipeline.report_html import h2h_report_html

    stats = {"matches": 2, "wins_a": 1, "wins_b": 1, "draws": 0,
             "goals_a": 50, "goals_b": 48}
    timeline = [{"date": "2026-01-01", "score": "25 – 24", "headline": "x"}]
    jm = {"meccsek": 2,
          "Mi": {"lovok": "a lövők: a 7-es távolról 1,3× annyit lő be, mint "
                          "amennyit a helyzetei érnek",
                 "kapus": "", "utolso": "a 7-esé távolról (10 m): 0,33 "
                                        "várható gól",
                 "kit_kinek": None, "engedett": None},
          "Ok": {"lovok": "", "kapus": "a kapus távolról 1,2× annyi gólt "
                                       "kap, mint az átlag",
                 "utolso": None,
                 "kit_kinek": "a 9-es (távolról 1,3× …) a szélső sávból lő",
                 "engedett": "a 4-es ellen nem kell kilépni"}}
    html = h2h_report_html("Mi", "Ok", stats, timeline, jatekos_modell=jm)
    assert "Játékos-modell egymás ellen (a közös meccsekből)" in html
    assert "<h3>Mi</h3><ul><li><b>Lövőik:</b> a lövők: a 7-es" in html
    assert "<li><b>Utolsó labdájuk ellenük:</b> a 7-esé távolról" in html
    assert "<h3>Ok</h3><ul><li><b>Kapusuk:</b> a kapus távolról" in html
    assert "<li><b>Kit kinek a falukban:</b> a 9-es" in html
    assert "<li><b>Engedett lövő a falukban:</b> a 4-es ellen" in html
    assert html.count("<li><b>") == 5
    assert "a közös 2 meccsből tanulva" in html
    for ures in (None, {}, {"meccsek": 2, "Mi": {}, "Ok": {"lovok": ""}}):
        assert "Játékos-modell egymás ellen" not in h2h_report_html(
            "Mi", "Ok", stats, timeline, jatekos_modell=ures)


def test_h2h_report_html_matchup_section():
    """Az egymás elleni riportban a meccsterv-szakasz csak akkor jelenik
    meg, ha van kereszt-szabályból jött javaslat; ilyenkor a listát is
    kirajzolja A csapat szemszögéből."""
    from handball.pipeline.report_html import h2h_report_html
    stats = {"matches": 2, "wins_a": 1, "draws": 0, "wins_b": 1,
             "goals_a": 5, "goals_b": 4}
    timeline = [{"date": "2026-01-10", "score": "3–2",
                 "headline": "Szoros meccs."}]
    html = h2h_report_html("Mi", "Ok", stats, timeline,
                           matchup=["Támadd a szélső védőt."])
    assert "Meccsterv a visszavágóra" in html
    assert "Mi szemszögéből" in html
    assert "Támadd a szélső védőt." in html
    html2 = h2h_report_html("Mi", "Ok", stats, timeline)
    assert "Meccsterv a visszavágóra" not in html2


def test_scouting_report_markers_table():
    """A nyomtatható felderítő jelentés Emberfogóik táblát hoz (50+
    kocka), laza/tapadó címkével; kevés kockánál a tábla elmarad."""
    from handball.pipeline.report_html import scouting_report_html
    rep = _rep(markers=[{"player_id": 4, "frames": 80,
                         "dist_sum": 240.0},
                        {"player_id": 2, "frames": 60,
                         "dist_sum": 60.0},
                        {"player_id": 9, "frames": 20,
                         "dist_sum": 30.0}])
    html = scouting_report_html(rep)
    assert "Emberfogóik (átlagtávval)" in html
    assert "3.0 m · LAZA" in html
    assert "1.0 m · tapadó" in html
    assert "9. játékos" not in html  # 50 kocka alatt kimarad
    html2 = scouting_report_html(_rep(markers=[]))
    assert "Emberfogóik" not in html2


def test_player_season_html_marking_column():
    """Ha van mért őrzés, a szezon-lap Őrzés oszlopot és összesítőt
    hoz (súlyozott átlagtávval); enélkül az oszlop sincs ott."""
    from handball.pipeline.report_html import player_season_html
    pts = [
        {"match_id": "m1", "date": "2026-01-10", "opponent": "A",
         "distance_m": 4000.0, "top_speed_ms": 6.0, "sprint_count": 5,
         "minutes": 40.0, "shots": 2, "goals": 1, "xg": 0.8,
         "xg_diff": 0.2, "gk_on_target": None, "gk_saves": None,
         "gk_prevented": None, "mark_s": 120.0, "mark_dist": 1.5},
        {"match_id": "m2", "date": "2026-01-17", "opponent": "B",
         "distance_m": 3800.0, "top_speed_ms": 6.2, "sprint_count": 4,
         "minutes": 38.0, "shots": 1, "goals": 0, "xg": 0.3,
         "xg_diff": -0.3, "gk_on_target": None, "gk_saves": None,
         "gk_prevented": None, "mark_s": 60.0, "mark_dist": 3.0},
    ]
    html = player_season_html("Mi", 4, pts)
    assert "Őrzés összesen" in html
    # Súlyozott átlag: (120*1,5 + 60*3,0) / 180 = 2,0 m.
    assert "180 mp · átl. 2.0 m" in html
    assert "120 mp · 1.5 m" in html and "60 mp · 3.0 m" in html
    pts2 = [dict(p, mark_s=None, mark_dist=None) for p in pts]
    html2 = player_season_html("Mi", 4, pts2)
    assert "Őrzés" not in html2


def test_h2h_report_html_scorers_section():
    """A Ki viszi a meccseket szakasz a megadott gólfelelősöket hozza;
    scorers nélkül a szakasz elmarad."""
    from handball.pipeline.report_html import h2h_report_html
    stats = {"matches": 2, "wins_a": 1, "draws": 0, "wins_b": 1,
             "goals_a": 5, "goals_b": 4}
    timeline = [{"date": "2026-01-10", "score": "3–2",
                 "headline": "Szoros meccs."}]
    html = h2h_report_html(
        "Mi", "Ok", stats, timeline,
        scorers={"Mi": [{"jersey": 7, "goals": 5}],
                 "Ok": [{"jersey": 9, "goals": 4},
                        {"jersey": 3, "goals": 2}]})
    assert "Ki viszi a meccseket" in html
    assert "#7 (5 gól)" in html
    assert "#9 (4 gól) · #3 (2 gól)" in html
    html2 = h2h_report_html("Mi", "Ok", stats, timeline)
    assert "Ki viszi a meccseket" not in html2


def test_scouting_report_break_lanes_table():
    """A felderítő jelentés Betörés-sávjaik táblát hoz (5+ betöréstől),
    aránnyal és gólszámmal; kevés betörésnél a tábla elmarad."""
    from handball.pipeline.report_html import scouting_report_html
    rep = _rep(break_entries=8,
               break_lanes={"közép": {"entries": 5, "goals": 3},
                            "bal szél": {"entries": 3, "goals": 0}})
    html = scouting_report_html(rep)
    assert "Betörés-sávjaik" in html
    assert "5 \n(62%)" in html or "5 (62%)" in html
    assert "közép" in html and "bal szél" in html
    html2 = scouting_report_html(_rep(break_entries=3,
                                      break_lanes={"közép":
                                                   {"entries": 3,
                                                    "goals": 1}}))
    assert "Betörés-sávjaik" not in html2


def test_kapus_felkeszites_tabla():
    """A poszt-lencse három lövés-rétege EGY táblában.

    Külön csempeként a kapusedző háromszor keresi meg ugyanazt a
    posztot; együtt egy pillantás: milyen messziről, milyen keményen,
    merre lő.
    """
    import re

    html = scouting_report_html(_rep(
        rsd_shots_by_role={"irányító": 6, "beálló": 5},
        rsd_dist_sum_by_role={"irányító": 72.0, "beálló": 32.5},
        rsp_shots_by_role={"irányító": 6},
        rsp_kmh_sum_by_role={"irányító": 780.0},
        rgp_goals_by_role_side={"irányító|bal": 4, "irányító|jobb": 1}))
    m = re.search(r"<h2[^>]*>Kapus-felkészítés posztonként</h2>(.*?)</table>",
                  html, re.S)
    assert m, "hiányzik a kapus-tábla"
    body = m.group(1)
    assert "12.0 m" in body and "130 km/h" in body and "bal (80%)" in body
    # A beállónál nincs erő- és oldal-adat: ott KIMONDOTT hiány-jel áll,
    # nem nulla vagy üres cella.
    assert "6.5 m" in body and "—" in body


def test_kapus_tabla_elmarad_ha_nincs_adat():
    """Adat nélkül nincs tábla — üres fejléc rosszabb, mint a hiánya."""
    assert "Kapus-felkészítés posztonként" not in scouting_report_html(_rep())



def test_a_felderito_lap_elol_szol_a_gyenge_alapanyagrol():
    """Egy nyomtatott meccstervet fentről lefelé olvasnak: aki a végén
    tudja meg, hogy az adat gyenge, addig már eldöntötte, kit állít a
    beállóra. A figyelmeztetés ezért a narratíva ELŐTT áll."""
    rep = ScoutingReport(team="home", team_name="Alfa")
    rep.q_matches = 1
    rep.q_score_sum = 28.0
    rep.q_weak_matches = 1
    html = scouting_report_html(rep)
    assert '<div class="warnbox">' in html
    assert "28/100" in html
    # A doboz az első TARTALMI szakasz előtt áll (a tartalomjegyzék
    # után — ugyanott, ahol a meccsjelentésben).
    assert html.index('<div class="warnbox">') < html.index(
        '<h2 id="sz1">')


def test_jo_alapanyagnal_nincs_doboz_a_felderito_lapon():
    """Jó feldolgozásnál (és régi, adat nélküli jelentésnél) a lap
    tiszta marad — nem riogatunk ok nélkül."""
    jo = ScoutingReport(team="home", team_name="Alfa")
    jo.q_matches = 2
    jo.q_score_sum = 2 * 90.0
    jo.q_weak_matches = 0
    assert '<div class="warnbox">' not in scouting_report_html(jo)
    assert '<div class="warnbox">' not in scouting_report_html(
        ScoutingReport(team="home", team_name="Alfa"))


def test_a_meccsterv_megelozi_az_altalanos_kulcsokat():
    """A PÁROSÍTOTT meccsterv menjen elöl.

    Az "ő gyengéjük × a ti erősségetek" szabályok kifejezetten ERRE a
    párosításra szólnak, míg a "Hogyan játssz ellenük" kulcsok
    általános, SZÁZ FÖLÖTTI listát adnak (mérve: 123 kulcs, közel
    húszezer karakter). Aki két percet szán a felkészülésre, a
    konkrétat kell hogy elsőként lássa — ezért a nyomtatott lapon is
    a meccsterv áll előbb.
    """
    rep = ScoutingReport(team="home", team_name="Alfa")
    html = scouting_report_html(
        rep, matchup=["Az ő lassuló visszaállásuk × a ti kontrátok."])
    assert "Meccsterv (a kettőnk párosítása)" in html
    assert (html.index("Meccsterv (a kettőnk párosítása)")
            < html.index("Hogyan játssz ellenük</h2>"))


def test_a_nyomtathato_jelentes_viszi_a_vedekezes_feltoreset():
    """A "Hol törhető fel a védekezésük" blokk a nyomtatható jelentésben
    is ott van, ha van tétel — és nincs, ha a jelentés üres."""
    from handball.pipeline.scouting import ScoutingReport

    ures = ScoutingReport(team="away", team_name="Üres", matches=1)
    assert "Hol törhető fel a védekezésük" not in scouting_report_html(ures)
    rep2 = ScoutingReport(team="away", team_name="Ellenfél", matches=1)
    rep2.def_shots_against = 20
    rep2.def_free_shots = 12
    html = scouting_report_html(rep2)
    assert "Hol törhető fel a védekezésük" in html
    assert "<b>Hol:</b> 9 m-en" in html and "Mivel:" in html and "Miért:" in html


def test_a_szezon_jatekos_lap_a_lovo_es_a_kapus_modellt_is_hozza():
    """A szezon játékos-lap "Honnan lősz be" és "Hol kapsz gólt"
    táblái a szezon sávonkénti mintájából: a lövés, a gól, a várható és a
    szorzó (kevés mintánál "kevés minta"); modell nélkül a szakasz
    elmarad."""
    from handball.pipeline.report_html import player_season_html

    pontok = [{"match_id": "m1", "goals": 3, "shots": 8}]
    lm = {"lovo": [{"sav": "close", "sav_nev": "közelről", "lovesek": 5,
                    "gol": 4, "xg": 2.6, "szorzo": 1.2},
                   {"sav": "far", "sav_nev": "távolról", "lovesek": 2,
                    "gol": 0, "xg": 0.5, "szorzo": None}],
          "kapus": [{"sav": "far", "sav_nev": "távolról", "kaputra": 9,
                     "vedes": 2, "szorzo": 1.3}],
          "meccsek": 4}
    html = player_season_html("A", 7, pontok, lovo_modell=lm)
    assert "Honnan lősz be — a szezon lövő-modellje" in html
    assert ('<tr><td>közelről</td><td class="num">5</td><td class="num">4</td>'
            '<td class="num">2.6</td><td class="num">1,2×</td></tr>') in html
    assert '<td class="num">kevés minta</td>' in html
    assert "Hol kapsz gólt — a szezon kapus-modellje" in html
    assert ('<tr><td>távolról</td><td class="num">9</td><td class="num">2</td>'
            '<td class="num">1,3×</td></tr>') in html
    assert "A szezon 4 meccséből" in html
    for ures in (None, {}, {"lovo": [], "kapus": [], "meccsek": 2}):
        assert "a szezon lövő-modellje" not in player_season_html(
            "A", 7, pontok, lovo_modell=ures)


def test_a_sav_kep_a_nyers_mintabol():
    """A sávonkénti kép a nyers mintából: a lövőnél a tanult szorzó
    LOVO_MIN_LOVES lövéstől, a kapusnál KAPUS_MIN_LOVES lövéstől (ugyanaz,
    mint a modell); sorrend: közelről, közepes, távolról."""
    from handball.pipeline.play_simulation import (_kapus_szorzo,
                                                   _lovo_szorzo,
                                                   keeper_bands_from,
                                                   shooter_bands_from)

    lm = {"far": [2, 0, 0.6], "close": [3, 3, 1.5]}
    assert shooter_bands_from(lm) == [
        {"sav": "close", "sav_nev": "közelről", "lovesek": 3, "gol": 3,
         "xg": 1.5, "szorzo": _lovo_szorzo({7: lm})[7]["close"]},
        {"sav": "far", "sav_nev": "távolról", "lovesek": 2, "gol": 0,
         "xg": 0.6, "szorzo": None}]
    km = {"far": [9, 2], "mid": [2, 1]}
    assert keeper_bands_from(km) == [
        {"sav": "mid", "sav_nev": "közepes távolságból", "kaputra": 2,
         "vedes": 1, "szorzo": None},
        {"sav": "far", "sav_nev": "távolról", "kaputra": 9, "vedes": 2,
         "szorzo": _kapus_szorzo(km)["far"]}]
    assert shooter_bands_from({}) == [] and keeper_bands_from({}) == []


def test_a_szezon_riport_a_lovo_modell_probajat_is_hozza():
    """A szezon-riport "A modellek próbája" szakasza a motor
    mondatával; ítélet nélkül elmarad."""
    from handball.pipeline.report_html import season_report_html

    tr = {"metrics": [], "summary": [], "older_matches": 2,
          "newer_matches": 2}
    v = ("a korábbi meccsekből tanult lövő-modell a következő meccs góljait "
         "48%-kal pontosabban becsülte, mint a nyers várható gól")
    k = ("a korábbi meccsekből tanult kapus-modell a következő meccs kapott "
         "góljait 51%-kal pontosabban becsülte, mint az átlagos kapus")
    html = season_report_html("Szeged", tr, [], 4,
                              modell_proba={"verdict": v, "kapus_verdict": k})
    assert "A modellek próbája" in html
    assert f"<p><b>Lövők:</b> {v}.</p>" in html
    assert f"<p><b>Kapus:</b> {k}.</p>" in html
    dv = ("a modell legjobb opcióját választó 40 döntés után 8 mp-en belül "
          "30%-ban jött gól")
    d_html = season_report_html("Szeged", tr, [], 4, modell_proba={
        "dontes_verdict": dv, "dontes": {"helyzetek": [
            {"verdict": "ha szabad a 6 m-es társuk: a legjobb opció után 40% "
                        "(15 döntés), máskor 10% (20) — itt igazolja a pálya"}]}})
    assert f"<p><b>Döntések:</b> {dv}.</p>" in d_html
    assert "<li>ha szabad a 6 m-es társuk: a legjobb opció után 40%" in d_html
    csak = season_report_html("Szeged", tr, [], 4,
                              modell_proba={"verdict": None, "kapus_verdict": k})
    assert "<b>Lövők:</b>" not in csak and f"<p><b>Kapus:</b> {k}.</p>" in csak
    for ures in (None, {}, {"verdict": ""}, {"verdict": None,
                                              "kapus_verdict": None}):
        assert "A modellek próbája" not in season_report_html(
            "Szeged", tr, [], 4, modell_proba=ures)


def test_az_elorejelzes_blokk_a_dontes_probakkal():
    """_elorejelzes_blokk: a "Hetes-dobónk" sor a címkék közt, és a próba-
    jegyzetek (előrejelzés, gólszerző, kapus-választás, felderítés,
    hetes-dobó) ebben a sorrendben; az üres mezők kimaradnak."""
    from handball.pipeline.report_html import (ELOREJELZES_CIMKEK,
                                               ELOREJELZES_PROBAK,
                                               _elorejelzes_blokk)

    assert ("hetes_mi", "Hetes-dobónk") in ELOREJELZES_CIMKEK
    assert ("hetes_irany_ok", "Az ő hetes-dobóik irányai") in ELOREJELZES_CIMKEK
    assert ("het_a_hat_mi", "A 7 a 6 mérlegünk") in ELOREJELZES_CIMKEK
    assert ("emberhatrany_mi", "Emberhátrány-falunk") in ELOREJELZES_CIMKEK
    assert ("szuper_csere_mi", "Szuper-cserénk") in ELOREJELZES_CIMKEK
    assert ELOREJELZES_PROBAK == ("proba", "golszerzo_proba", "kapus_proba",
                                  "felderites_proba", "hetes_proba",
                                  "hetes_irany_proba", "szuper_csere_proba")
    ej = {"text": "Hazai 27–25 Vendég", "kapus_mi": "az 1-es álljon a kapuban",
          "hetes_mi": "a hetest a 9-es dobja (11/13 a könyvtárban, 85%)",
          "proba": None, "golszerzo_proba": "A gólszerző-becslés próbája: x",
          "kapus_proba": "A kapus-választás próbája: y",
          "felderites_proba": None,
          "hetes_proba": "A hetes-dobó választás próbája: z",
          "hetes_irany_ok": "hetes-irányaik (a dobó felől nézve): a 9-es "
                            "70% jobbra (7/10)",
          "hetes_irany_proba": "A hetes-irány próbája: w"}
    h = _elorejelzes_blokk(ej, "Előrejelzés")
    assert ("<li>Kapus ellenük: az 1-es álljon a kapuban.</li>"
            "<li>Hetes-dobónk: a hetest a 9-es dobja (11/13 a könyvtárban, "
            "85%).</li><li>Az ő hetes-dobóik irányai: hetes-irányaik (a dobó "
            "felől nézve): a 9-es 70% jobbra (7/10).</li></ul>") in h
    assert h.endswith('<p class="note">A gólszerző-becslés próbája: x.</p>'
                      '<p class="note">A kapus-választás próbája: y.</p>'
                      '<p class="note">A hetes-dobó választás próbája: z.</p>'
                      '<p class="note">A hetes-irány próbája: w.</p>')
    assert _elorejelzes_blokk({"hetes_proba": None}, "x") == ""


def test_a_meccs_jelentes_a_pad_donteseivel():
    """match_report_html `dontesek`: "A pad döntései a könyvtár tükrében"
    szakasz csapatonként a nevekkel; üres soroknál a szakasz elmarad."""
    from handball.models.tracking import Match, MatchMeta
    from handball.pipeline.report_html import match_report_html

    m = Match(MatchMeta(match_id="r", home_team="Hazai", away_team="Vendég",
                        fps=25.0), [])
    tactics = {"home": {}, "away": {}}
    d = {"nevek": {"home": "Hazai", "away": "Vendég"},
         "home": {"sorok": ["Heteseik: a 9-es 3/3 — a könyvtár dobója (a "
                            "9-es) dobta", "A kapuban az 1-es kezdett (3/10 "
                            "az első félidőben)"]},
         "away": {"sorok": []}}
    h = match_report_html(m, tactics, [], None, dontesek=d)
    # A címsor azonosítót kap (a tartalomjegyzékhez): <h2 id="szN">.
    assert (">A pad döntései a könyvtár tükrében</h2><p><b>Hazai</b></p>"
            "<ul><li>Heteseik: a 9-es 3/3 — a könyvtár dobója (a 9-es) "
            "dobta.</li><li>A kapuban az 1-es kezdett (3/10 az első "
            "félidőben).</li></ul>") in h
    assert "<p><b>Vendég</b></p>" not in h
    assert "A pad döntései" not in match_report_html(m, tactics, [], None)
    assert "A pad döntései" not in match_report_html(
        m, tactics, [], None, dontesek={"nevek": d["nevek"],
                                        "home": {"sorok": []}, "away": {}})


# ---- Belső építőelemek közvetlenül (második kör) ------------------------------

def test_section_id_sorszam_alapu_horgony():
    """A szekció horgonya sorszám alapú (az ékezetes címből képzett
    azonosító törékeny lenne) — és a tartalomjegyzék ezt használja."""
    from handball.pipeline.report_html import _section_id, with_toc

    assert _section_id(1) == "sz1" and _section_id(42) == "sz42"
    html = ("<html><head><style>x{}</style></head><body><header>F</header>"
            + "".join(f"<h2>Szakasz {i}</h2>" for i in range(1, 9))
            + "</body></html>")
    kesz = with_toc(html, min_sections=3)
    assert '<h2 id="sz1">Szakasz 1</h2>' in kesz
    assert '<li><a href="#sz8">Szakasz 8</a></li>' in kesz


def test_rows_es_metric_escape_elnek_es_az_ures_lista_tajekoztat():
    """A felsorolás tételei és a mutató-kártya szövegei HTML-escape-elve
    mennek ki (egy csapatnév "<" jele nem töri el a lapot); üres
    listánál szürke tájékoztató sor áll (nem üres <ul>)."""
    from handball.pipeline.report_html import _metric, _rows

    assert _rows(["Gyors <indítás>", 7], "nincs") == \
        "<li>Gyors &lt;indítás&gt;</li><li>7</li>"
    assert _rows([], "Nincs elég minta & adat") == \
        '<li class="empty">Nincs elég minta &amp; adat</li>'
    assert _rows(None, "üres") == '<li class="empty">üres</li>'
    assert _metric("Lövés <db>", "12 & 3") == (
        '<div class="metric"><div class="mv">12 &amp; 3</div>'
        '<div class="ml">Lövés &lt;db&gt;</div></div>')


def test_defense_bars_megoszlas_savok_0_es_100_koze_szoritva():
    """A megoszlás-sávok szélessége a százalék (0..100 közé szorítva, egész
    %-ra); megoszlás nélkül tájékoztató bekezdés — a saját szöveggel is."""
    from handball.pipeline.report_html import _defense_bars

    h = _defense_bars({"6-0": 75.4, "5-1 <agresszív>": 24.6, "hibás": 140.0,
                       "negatív": -5})
    assert h.count('<div class="bar-row">') == 4
    assert ('<span class="bar-label">6-0</span><span class="bar">'
            '<span class="bar-fill" style="width:75%"></span></span>'
            '<span class="bar-pct">75%</span>') in h
    assert "5-1 &lt;agresszív&gt;" in h and "width:25%" in h
    assert "width:100%" in h and "width:0%" in h
    assert _defense_bars({}) == '<p class="empty">Nincs elég védekező minta.</p>'
    assert _defense_bars(None, empty="Nincs támadás-mix.") == \
        '<p class="empty">Nincs támadás-mix.</p>'


def test_shot_zone_es_def_zone_bars_arany_es_gol_per_loves():
    """A lövés-zónák sávja a lövésszám ARÁNYA, a felirat "gól/lövés"; a
    kapott-lövés zónáknál a szabadon hagyott lövések száma is (ha van);
    minta nélkül tájékoztató bekezdés."""
    from handball.pipeline.report_html import _def_zone_bars, _shot_zone_bars

    zonak = {"átlövés közép": {"shots": 6, "goals": 2},
             "balszél": {"shots": 2, "goals": 2}}
    h = _shot_zone_bars(zonak)
    assert "width:75%" in h and "width:25%" in h
    assert '<span class="bar-pct">2/6</span>' in h
    assert '<span class="bar-pct">2/2</span>' in h
    assert _shot_zone_bars({}) == \
        '<p class="empty">Nincs elég lövés-minta.</p>'
    # Lövés nélküli zónák: nem oszt nullával.
    assert "width:0%" in _shot_zone_bars({"beálló": {"shots": 0, "goals": 0}})

    kapott = {"beálló (6 m)": {"shots": 4, "goals": 3, "free": 2},
              "jobbszél": {"shots": 4, "goals": 1}}
    d = _def_zone_bars(kapott)
    assert '<span class="bar-pct">3/4 · szabad: 2</span>' in d
    assert '<span class="bar-pct">1/4</span>' in d
    assert d.count("width:50%") == 2
    assert _def_zone_bars({}) == \
        '<p class="empty">Nincs elég kapott-lövés minta.</p>'


def test_stoppers_es_breakpoints_block_hol_mivel_miert(monkeypatch):
    """A két rangsorolt kivonat blokkja sorszámozott Hol / Mivel / Miért
    tételekkel készül (escape-elve); üres listánál — vagy ha a kivonat
    hibára fut — NINCS blokk (nem ígérünk ítéletet 0-ból)."""
    from handball.pipeline import report_html, scouting

    tetel = [{"hol": "bal <szél>", "mivel": "kettőzés", "miert": "5/6 gól",
              "pont": 3.0},
             {"hol": "közép", "mivel": "zárt fal", "miert": "70%", "pont": 1.0}]
    monkeypatch.setattr(scouting, "attack_stoppers", lambda rep: tetel)
    monkeypatch.setattr(scouting, "defence_breakpoints", lambda rep: tetel)
    stop = report_html._stoppers_block(_rep())
    assert stop.startswith('<div class="keys stop"><h2>Hogyan állítsd meg a '
                           'támadásukat</h2><ol>')
    assert stop.count("<li>") == 2
    assert ("<li><b>Hol:</b> bal &lt;szél&gt;<br><b>Mivel:</b> kettőzés<br>"
            '<span class="miert">Miért: 5/6 gól</span></li>') in stop
    tores = report_html._breakpoints_block(_rep())
    assert '<div class="keys break"><h2>Hol törhető fel a védekezésük</h2>' \
        in tores and tores.count("<li>") == 2

    monkeypatch.setattr(scouting, "attack_stoppers", lambda rep: [])
    monkeypatch.setattr(scouting, "defence_breakpoints", lambda rep: [])
    assert report_html._stoppers_block(_rep()) == ""
    assert report_html._breakpoints_block(_rep()) == ""

    def bukik(rep):
        raise RuntimeError("nem megy")
    monkeypatch.setattr(scouting, "attack_stoppers", bukik)
    monkeypatch.setattr(scouting, "defence_breakpoints", bukik)
    assert report_html._stoppers_block(_rep()) == ""
    assert report_html._breakpoints_block(_rep()) == ""


def test_stoppers_es_breakpoints_block_a_valodi_kivonattal():
    """A VALÓDI kivonatokkal (attack_stoppers / defence_breakpoints): üres
    riportból nincs blokk; a tételek kulcsai tényleg hol / mivel / miert."""
    from handball.pipeline.report_html import (_breakpoints_block,
                                               _stoppers_block)
    from handball.pipeline.scouting import (attack_stoppers,
                                            defence_breakpoints)

    ures = ScoutingReport(team="home", team_name="Mi")
    assert attack_stoppers(ures) == [] and defence_breakpoints(ures) == []
    assert _stoppers_block(ures) == "" and _breakpoints_block(ures) == ""
    from handball.models.tracking import Team
    from handball.pipeline.scouting import scout_team
    from handball.sim.match_simulator import simulate_ground_truth

    rep = scout_team(simulate_ground_truth(duration_s=120, fps=25.0, seed=5,
                                           shots_per_min=8), Team.HOME)
    for kivonat, blokk in ((attack_stoppers, _stoppers_block),
                           (defence_breakpoints, _breakpoints_block)):
        tetelek = kivonat(rep)
        assert all({"hol", "mivel", "miert"} <= set(t) for t in tetelek)
        assert blokk(rep).count("<li>") == len(tetelek)


def test_figura_ajanlo_es_vedekezesi_proba_sorok():
    """A figura-ajánló: a mondat, alatta legfeljebb öt figura a
    lövőhelyzettel és az alap fal elleni értékkel. A védekezési próba: a
    mondat nagy kezdőbetűvel és ponttal, figuránként az ismétlés, az
    időpont (p:mm) és — ha van — a 3D-link."""
    from handball.pipeline.report_html import (FIGURA_AJANLO_SOROK,
                                               _figura_ajanlo_rows,
                                               _vedekezesi_proba_rows)

    figurak = [{"name": f"Figura <{i}>", "pont_pct": 60.4 - i,
                "alap_pct": 40.0} for i in range(7)]
    h = _figura_ajanlo_rows({"ajanlas": "A <Kereszt> a legjobb",
                             "figurak": figurak})
    assert h.startswith("<p>A &lt;Kereszt&gt; a legjobb</p>")
    assert h.count('<div class="bar-row">') == FIGURA_AJANLO_SOROK == 5
    assert "Figura &lt;0&gt;" in h and "Figura &lt;5&gt;" not in h
    assert "60% lövőhelyzet (alap fal: 40%)" in h
    assert _figura_ajanlo_rows({}) == ""
    assert _figura_ajanlo_rows({"figurak": [{"name": "X"}]}).count(
        "0% lövőhelyzet (alap fal: 0%)") == 1

    p = _vedekezesi_proba_rows({
        "verdict": "a falunk többet enged a kelleténél",
        "figurak": [{"ismetles": 3, "t0_s": 83.4, "pont_pct": 55.0,
                     "alap_pct": 35.0, "link": "a=1&b=<2>"},
                    {"ismetles": 2, "t0_s": 5.0, "pont_pct": 20.0,
                     "alap_pct": 30.0}]})
    assert p.startswith("<p>A falunk többet enged a kelleténél.</p>")
    assert "3× · pl. 1:23" in p and "2× · pl. 0:05" in p
    assert '<a href="/figura3d?a=1&amp;b=&lt;2&gt;">3D ↗</a>' in p
    assert p.count("3D ↗") == 1
    assert _vedekezesi_proba_rows({}) == ""


def test_figure_svg_a_cella_atlatszatlansaga_a_latogatottsag():
    """A figura-alak mini-pályán: a látogatott cellák rajzolódnak, a
    leglátogatottabb a legsötétebb; rossz hosszú vagy üres alaknál nincs
    rajz (üres szöveg); csupa nulla alak üres pálya, osztás nélkül."""
    from handball.pipeline.report_html import _figure_svg

    alak = [0.0] * 18
    alak[11], alak[5] = 1.0, 0.5
    svg = _figure_svg(alak)
    assert svg.startswith('<svg width="150" height="75"') and svg.endswith(
        "</svg>")
    assert svg.count('fill="#2FD9C4"') == 2
    assert 'opacity="0.90"' in svg and 'opacity="0.49"' in svg
    # A 11-es cella (ix=5, iy=1) helye: x = 125, y = 25.
    assert '<rect x="125.0" y="25.0" width="25.0" height="25.0"' in svg
    assert _figure_svg([]) == "" and _figure_svg(None) == ""
    assert _figure_svg([1.0] * 17) == ""
    ures = _figure_svg([0.0] * 18)
    assert ures.startswith("<svg") and 'fill="#2FD9C4"' not in ures
    assert 'width="300"' in _figure_svg(alak, w=300, h=150)


def test_setplay_library_rows_visszatero_figurak_vagy_tajekoztato():
    """A visszatérő figurák sorai: rajz, edzői név (a zónával), meccs /
    támadás / gól; legfeljebb hat sor; visszatérő figura nélkül
    tájékoztató bekezdés (None könyvtárra is)."""
    from handball.pipeline.report_html import _setplay_library_rows

    alak = [0.0] * 18
    alak[11] = 1.0
    sor = {"shape": alak, "name": "Kereszt <A>", "zone": "közép",
           "matches": 3, "attacks": 9, "goals": 4, "goal_pct": 44.4}
    h = _setplay_library_rows({"recurring": [sor] * 8})
    assert h.count('<div class="bar-row"') == 6
    assert "<b>Kereszt &lt;A&gt;</b> (közép) — 3 meccsen 9 támadás, 4 gól " \
           "(44%)" in h
    assert h.count("<svg") == 6
    assert "A rajz a támadó szemszögéből" in h
    nev_nelkul = _setplay_library_rows({"recurring": [
        {"shape": alak, "zone": "bal oldal", "matches": 2, "attacks": 4,
         "goals": 1, "goal_pct": 25.0}]})
    assert "<b>bal oldal</b> — 2 meccsen 4 támadás, 1 gól (25%)" in nev_nelkul
    for ures in ({}, None, {"recurring": []}):
        assert "Még nincs meccsről meccsre visszatérő figura" in \
            _setplay_library_rows(ures)


def test_fmt_clock_es_phase_bars():
    """A játékóra p:mm alakja, és a fázis-megoszlás három sávja a két
    csapat nevével (a hiányzó fázis 0%)."""
    from handball.pipeline.report_html import _fmt_clock, _phase_bars

    assert _fmt_clock(0) == "0:00" and _fmt_clock(83.4) == "1:23"
    assert _fmt_clock(59.99) == "0:59" and _fmt_clock(3600) == "60:00"
    h = _phase_bars({"home_attack": 45.6, "away_attack": 30.2}, "Mi <A>",
                    "Ők")
    assert h.count('<div class="bar-row">') == 3
    assert "Mi &lt;A&gt; támadás" in h and "Ők támadás" in h
    assert "width:46%" in h and "width:30%" in h
    assert 'bar-fill gold" style="width:0%"' in h      # átmenet: nincs adat
    assert _phase_bars({}, "H", "A").count("width:0%") == 3


def test_heatmap_svg_a_latogatott_cellak_es_az_ures_terkep():
    """A hőtérkép-SVG 2:1 arányú; csak a látogatott cellák rajzolódnak,
    az átlátszóságuk a látogatottsággal arányos; üres térképnél csak a
    pálya (cella és osztás nélkül)."""
    from handball.models.tracking import (Frame, Match, MatchMeta,
                                          PlayerPosition, Team)
    from handball.pipeline.analytics import compute_team_heatmap
    from handball.pipeline.report_html import _heatmap_svg

    frames = [Frame(t=t, players=[
        PlayerPosition(track_id=1, team=Team.HOME, x=30.0, y=10.0),
        PlayerPosition(track_id=2, team=Team.HOME,
                       x=30.0 if t < 3 else 5.0, y=10.0 if t < 3 else 3.0),
    ], ball=None) for t in range(4)]
    m = Match(MatchMeta(match_id="hm", home_team="H", away_team="A",
                        fps=25.0), frames)
    svg = _heatmap_svg(compute_team_heatmap(m, Team.HOME))
    assert svg.startswith('<svg viewBox="0 0 360 180" width="360" '
                          'height="180"')
    assert svg.count('fill="#12988a"') == 2
    assert 'fill-opacity="0.80"' in svg           # a leglátogatottabb cella
    assert 'fill-opacity="0.18"' in svg           # 1/7-nyi látogatottság
    ures = _heatmap_svg(compute_team_heatmap(m, Team.AWAY), color="#b2453a",
                        width=200)
    assert 'viewBox="0 0 200 100"' in ures and "fill-opacity" not in ures


def _esemeny(t, tipus, team="home", player=None, detail=None):
    return {"t": t, "type": tipus, "team": team, "player_id": player,
            "detail": detail}


def test_shot_positions_a_lovo_helye_kulonben_a_labdae():
    """A lövés / gól helye a lövő pozíciója az esemény kockáján; ha a
    lövő nincs a kockán (vagy ismeretlen), a labdáé; ha az sincs, vagy
    nincs ilyen kocka, a lövés kimarad. A szótár- és az objektum-alakú
    eseményt egyaránt érti; a passz nem lövés."""
    from types import SimpleNamespace

    from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                          PlayerPosition, Team)
    from handball.pipeline.event_detection import EventType
    from handball.pipeline.report_html import _shot_positions

    frames = [
        Frame(t=10, players=[PlayerPosition(track_id=7, team=Team.HOME,
                                            x=31.0, y=9.0)],
              ball=Ball(x=38.0, y=10.0)),
        Frame(t=20, players=[], ball=Ball(x=6.0, y=12.0)),
        Frame(t=30, players=[], ball=None),
    ]
    m = Match(MatchMeta(match_id="sp", home_team="H", away_team="A",
                        fps=25.0), frames)
    esemenyek = [
        _esemeny(10, "goal", player=7),                    # a lövő helye
        _esemeny(20, "shot", team="away", player=99),      # nincs a kockán
        _esemeny(30, "shot", player=None),                 # se lövő, se labda
        _esemeny(40, "shot", player=7),                    # nincs ilyen kocka
        _esemeny(10, "pass", player=7),                    # nem lövés
        SimpleNamespace(t=10, type=EventType.SHOT, team=Team.HOME,
                        player_id=None),                   # objektum-alak
    ]
    assert _shot_positions(m, esemenyek) == [
        (31.0, 9.0, "home", True), (6.0, 12.0, "away", False),
        (38.0, 10.0, "home", False)]
    assert _shot_positions(m, []) == []


def test_shot_map_svg_a_gol_arany_korvonalat_kap():
    """A lövéstérképen a gól teli, arany körvonalú pont, a kimaradt lövés
    halványabb; a csapatok a jelentés két színével; lövés nélkül üres
    pálya."""
    from handball.pipeline.report_html import _shot_map_svg

    svg = _shot_map_svg([(30.0, 10.0, "home", True),
                         (10.0, 5.0, "away", False),
                         (20.0, 10.0, "ismeretlen", False)])
    assert svg.startswith('<svg viewBox="0 0 480 240"')
    assert ('<circle cx="360.0" cy="120.0" r="5" fill="#2f6fb2" '
            'fill-opacity="1.0" stroke="#9d7526" stroke-width="2.5"/>') in svg
    assert ('<circle cx="120.0" cy="60.0" r="5" fill="#b2453a" '
            'fill-opacity="0.45"/>') in svg
    assert 'fill="#8492A6" fill-opacity="0.45"' in svg
    assert _shot_map_svg([]).count("<circle") == 0


def test_intensity_svg_ket_vonal_vagy_ures():
    """A tempó-alakulás két vonala (hazai / vendég) az ablakok közepén;
    kevesebb mint két ablakból vagy kockából nincs rajz (üres szöveg);
    csupa nulla sebességnél sem oszt nullával."""
    from handball.pipeline.report_html import _intensity_svg

    ablakok = [{"start_frame": 0, "home_avg_ms": 2.0, "away_avg_ms": 1.0},
               {"start_frame": 750, "home_avg_ms": 3.0, "away_avg_ms": 2.5},
               {"start_frame": 1500, "home_avg_ms": 1.5, "away_avg_ms": 2.0}]
    svg = _intensity_svg(ablakok, total_frames=2250, fps=25.0)
    assert svg.startswith('<svg viewBox="0 0 720 150"')
    assert svg.count("<polyline") == 2
    assert 'stroke="#2f6fb2"' in svg and 'stroke="#b2453a"' in svg
    assert ">2'</text>" in svg                    # 2250 kocka = 1,5 perc → "2'"
    assert _intensity_svg(ablakok[:1], 2250, 25.0) == ""
    assert _intensity_svg([], 2250, 25.0) == ""
    assert _intensity_svg(ablakok, 1, 25.0) == ""
    allo = [{"start_frame": 0, "home_avg_ms": 0.0, "away_avg_ms": 0.0},
            {"start_frame": 10, "home_avg_ms": 0.0, "away_avg_ms": 0.0}]
    assert _intensity_svg(allo, 20, 25.0).count("<polyline") == 2


def test_pass_pairs_a_leggyakoribb_parok_mezszammal():
    """Egy csapat passz-összegzése: az összes passz és a leggyakoribb
    párok (az irány nem számít: 7→9 és 9→7 egy pár), mezszámmal, ha
    ismert; a másik csapat passza, a fogadó nélküli és az önmagának adott
    "passz" kimarad; passz nélkül (0, [])."""
    from handball.models.tracking import (Frame, Match, MatchMeta,
                                          PlayerPosition, Team)
    from handball.pipeline.report_html import _pass_pairs

    m = Match(MatchMeta(match_id="pp", home_team="H", away_team="A",
                        fps=25.0), [Frame(t=0, players=[
                            PlayerPosition(track_id=1, team=Team.HOME, x=1.0,
                                           y=1.0, jersey_number=7),
                            PlayerPosition(track_id=2, team=Team.HOME, x=2.0,
                                           y=2.0, jersey_number=9),
                            PlayerPosition(track_id=3, team=Team.HOME, x=3.0,
                                           y=3.0)], ball=None)])

    def passz(a, b, team="home"):
        return _esemeny(0, "pass", team=team, player=a,
                        detail={"receiver_id": b} if b is not None else None)

    esemenyek = [passz(1, 2), passz(2, 1), passz(1, 2), passz(2, 3),
                 passz(1, 1), passz(1, None), passz(11, 12, team="away"),
                 _esemeny(0, "shot", player=1)]
    assert _pass_pairs(m, esemenyek, "home") == (
        4, [("#7", "#9", 3), ("#9", "id 3", 1)])
    assert _pass_pairs(m, esemenyek, "home", top=1) == (4, [("#7", "#9", 3)])
    assert _pass_pairs(m, esemenyek, "away") == (1, [("id 11", "id 12", 1)])
    assert _pass_pairs(m, [], "home") == (0, [])


def test_kep_img_beagyazott_jpeg():
    """A jelentés videó-kockája beágyazott (base64) JPEG — a jelentés
    önálló fájl marad; a bájtok visszafejthetők."""
    import base64

    from handball.pipeline.report_html import _kep_img

    h = _kep_img(b"\xff\xd8\xff\xe0-jpeg-bajtok")
    assert h.startswith('<img alt="" src="data:image/jpeg;base64,')
    kod = h.split("base64,")[1].split('"')[0]
    assert base64.b64decode(kod) == b"\xff\xd8\xff\xe0-jpeg-bajtok"
    assert _kep_img(b"").startswith('<img alt="" src="data:image/jpeg;'
                                    'base64,"')


def test_report_frame_times_a_jegyzetek_idorendben_plafonnal():
    """A jelentés videó-kockáinak ideje: a videózandó jelenetek horgonyai,
    utánuk az időrendben első REPORT_NOTE_FRAMES_MAX jegyzet (egész
    kockára váltva; a kocka nélküli jegyzet a 0. kocka); jelenet és
    jegyzet nélkül üres."""
    from handball.models.tracking import Match, MatchMeta
    from handball.pipeline.report_html import (REPORT_NOTE_FRAMES_MAX,
                                               _report_frame_times)

    ures = Match(MatchMeta(match_id="rf", home_team="H", away_team="A",
                           fps=25.0), [])
    assert _report_frame_times(ures, None) == []
    assert _report_frame_times(ures, []) == []
    jegyzetek = [{"frame": 300}, {"frame": 100}, {"frame": 200.7},
                 {"text": "kocka nélkül"}]
    assert _report_frame_times(ures, jegyzetek) == [0, 100, 200, 300]
    sok = [{"frame": 10 * i} for i in range(REPORT_NOTE_FRAMES_MAX + 5)]
    idok = _report_frame_times(ures, list(reversed(sok)))
    assert idok == [10 * i for i in range(REPORT_NOTE_FRAMES_MAX)]


def test_trend_metrics_table_irany_nyilakkal():
    """A trend-tábla soronként a régi / új értéket és a változást adja:
    javulásnál ▲ (up), romlásnál ▼ (down), semlegesnél –; mutató nélkül
    tájékoztató bekezdés."""
    from handball.pipeline.report_html import _trend_metrics_table

    h = _trend_metrics_table({"metrics": [
        {"label": "Gyors <indítás>", "unit": "%", "older": 8.24,
         "newer": 12.0, "delta": 3.76, "better": True},
        {"label": "Eladott labda", "unit": "", "older": 9.0, "newer": 12.5,
         "delta": 3.5, "better": False},
        {"label": "Tempó", "unit": " s", "older": 2.7, "newer": 2.7,
         "delta": 0.0, "better": None}]})
    assert h.startswith("<table><tr><th>Mutató</th>")
    assert ('<tr><td>Gyors &lt;indítás&gt;</td><td class="num">8.2%</td>'
            '<td class="num">12.0%</td><td class="num up">▲ +3.8%</td></tr>'
            ) in h
    assert '<td class="num down">▼ +3.5</td>' in h
    assert '<td class="num ">– +0.0 s</td>' in h
    assert _trend_metrics_table({"metrics": []}) == \
        '<p class="empty">Nincs összevethető mutató.</p>'
    assert _trend_metrics_table({}) == \
        '<p class="empty">Nincs összevethető mutató.</p>'
