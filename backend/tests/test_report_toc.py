"""A nyomtatható jelentések tartalomjegyzékének (with_toc) tesztjei.

A meccsjelentés huszonöt-ötven szakaszig is elmegy, és papíron nincs
keresés: az edző lapozgat, amíg megtalálja a "Hétméteresek" részt. A
jegyzék ezért a fejléc alá kerül, sorszámozva.
"""
from __future__ import annotations

import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.pipeline.report_html import (TOC_MIN_SECTIONS,
                                           TOC_TWO_COLUMNS_FROM, with_toc)


def _doc(titles: list[str], header: bool = True) -> str:
    body = "".join(f"<h2>{t}</h2><p>szöveg</p>" for t in titles)
    head = "<header><h1>Cím</h1></header>" if header else ""
    return (f"<!DOCTYPE html><html><head><style>body {{}}</style></head>"
            f"<body><div class=\"page\">{head}{body}</div></body></html>")


def _links(html: str) -> list[str]:
    return re.findall(r'href="#(sz\d+)"', html)


def _ids(html: str) -> list[str]:
    return re.findall(r'<h2[^>]*id="(sz\d+)"', html)


def test_minden_szakasz_bekerul_a_jegyzekbe():
    """Minden <h2> kap horgonyt, és pontosan egy jegyzék-sort."""
    titles = ["Hogyan játssz ellenük", "Mutatók", "Honnan lőnek",
              "Kulcsjátékosaik"]
    out = with_toc(_doc(titles))
    assert out.count('<nav class="toc') == 1
    assert _links(out) == _ids(out) == ["sz1", "sz2", "sz3", "sz4"]
    for t in titles:
        assert f">{t}</a>" in out, t
    assert f"Tartalom ({len(titles)} szakasz)" in out


def test_a_jegyzek_a_fejlec_ala_kerul():
    """A jegyzék helye rögzített: a fejléc után, a tartalom elé."""
    out = with_toc(_doc(["A", "B", "C", "D"]))
    assert out.index("</header>") < out.index('<nav class="toc')
    assert out.index('<nav class="toc') < out.index('id="sz1"')


def test_keves_szakasznal_nincs_jegyzek():
    """Két-három címhez nem kell navigáció — a jegyzék csak helyet venne."""
    titles = ["A"] * (TOC_MIN_SECTIONS - 1)
    src = _doc(titles)
    out = with_toc(src)
    assert out == src, "kevés szakasznál változatlanul kell visszaadni"
    assert "toc" not in out


def _nav_class(html: str) -> str:
    """A jegyzék osztályai. (A `two-col` szabály a stíluslapban MINDIG
    ott van, ezért a nav elem attribútumát kell nézni, nem a
    dokumentumot.)"""
    m = re.search(r'<nav class="([^"]*)"', html)
    return m.group(1) if m else ""


def test_sok_szakasznal_ket_hasab():
    """Ötven soros jegyzék egy hasábban kitöltene egy A4-et."""
    few = with_toc(_doc([f"Cím {i}" for i in range(TOC_TWO_COLUMNS_FROM - 1)]))
    many = with_toc(_doc([f"Cím {i}" for i in range(TOC_TWO_COLUMNS_FROM)]))
    assert _nav_class(few) == "toc"
    assert "two-col" in _nav_class(many)


def test_ketszeri_futtatas_nem_duplaz():
    """A már megjelölt címeket nem írjuk felül újra."""
    once = with_toc(_doc(["A", "B", "C", "D"]))
    twice = with_toc(once)
    assert twice.count('<nav class="toc') == 1
    assert len(_ids(twice)) == 4
    assert twice.count('id="sz1"') == 1


def test_fejlec_nelkul_valtozatlan():
    """Nincs hova beszúrni → hozzá se nyúlunk (a jegyzék sose ronthat el
    egy jelentést)."""
    src = _doc(["A", "B", "C", "D"], header=False)
    assert with_toc(src) == src


def test_cimke_belso_jelolese_lekerul():
    """A cím szövegében lévő jelölők (pl. <b>) nem szivárognak a linkbe."""
    src = ("<html><head><style></style></head><body><header></header>"
           "<h2>Hetes<b>esek</b></h2><h2>B</h2><h2>C</h2><h2>D</h2>"
           "</body></html>")
    out = with_toc(src)
    assert ">Hetesesek</a>" in out
    assert "<b>" not in out[out.index("<nav"):out.index("</nav>")]


def test_valos_felderito_jelentesben_minden_link_celba_er():
    """Éles jelentésen: a jegyzék minden hivatkozása létező horgony."""
    from handball.pipeline.report_html import scouting_report_html
    from handball.pipeline.scouting import ScoutingReport

    rep = ScoutingReport(
        team="away", team_name="Szeged", matches=2,
        attack_share_pct=62.0, fast_break_pct=14.0, avg_ball_speed_ms=4.2,
        avg_attack_duration_s=8.5, defense_main="6-0",
        defense_distribution={"6-0": 80.0, "5-1": 20.0},
        attack_centroid_x=30.0, attack_centroid_y=10.0, num_figures=3,
        attacks=12, shots=10, goals=6, turnovers=2,
        shot_efficiency_pct=60.0,
        key_players=[{"track_id": 7, "possession_frames": 120,
                      "distance_m": 340.5, "role": "irányító"}],
        strengths=["Gyors indítás (14%)"], weaknesses=["Sok labdaeladás"],
        keys_to_game=["Mély 6-0 faluk ellen: 9 m-es lövés."],
    )
    html = scouting_report_html(rep)
    links, ids = _links(html), _ids(html)
    assert links, "az éles jelentésben van jegyzék"
    assert set(links) == set(ids), (set(links) ^ set(ids))
    assert len(ids) == len(set(ids)), "a horgonyok egyediek"
