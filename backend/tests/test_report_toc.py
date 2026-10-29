"""A nyomtatható jelentések utolsó simításainak tesztjei.

Tartalomjegyzék (`with_toc`): a meccsjelentés huszonöt-ötven szakaszig
is elmegy, és papíron nincs keresés — az edző lapozgat, amíg megtalálja
a "Hétméteresek" részt. A jegyzék ezért a fejléc alá kerül, sorszámozva.

Nyomtatási stílus (`with_print_css`): a böngésző alapértelmezett
tördelése a jelentés szerkezetéről semmit nem tud — árván hagyja a
szakasz-címet az oldal alján, és kettévágja a táblázatot.

Készítés-bélyeg (`with_stamp`): az edzőnél mappában állnak a nyomatok,
és egy elavult felderítés rosszabb, mint a semmi — mert elhiszi.
"""
from __future__ import annotations

import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.pipeline.report_html import (TOC_MIN_SECTIONS,
                                           TOC_TWO_COLUMNS_FROM,
                                           finish_report, with_print_css,
                                           with_toc)


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


# --- Nyomtatási stílus -------------------------------------------------

def test_nyomtatasi_stilus_bekerul():
    """A közös nyomtatási szabályok a stíluslap VÉGÉRE kerülnek.

    A jelentés papíron él tovább (az edző kinyomtatja és beviszi az
    öltözőbe), a böngésző alapértelmezett tördelése viszont a jelentés
    szerkezetéről semmit nem tud.
    """
    out = with_print_css(_doc(["A"]))
    assert "@media print" in out
    for rule in ["break-after: avoid",      # árva szakasz-cím
                 "break-inside: avoid",     # kettévágott táblázat
                 'a[href^="#"]']:           # papíron ne látszódjon linknek
        assert rule in out, rule
    # A stíluslap végére: a jelentés saját szabályait felülírhatja.
    assert out.index("@media print") < out.index("</style>")


def test_regi_bongeszo_jelolese_is_kikerul():
    """A `break-*` mellett a régebbi `page-break-*` is — a felhasználó
    böngészőjét nem ismerjük."""
    out = with_print_css(_doc(["A"]))
    assert "page-break-after: avoid" in out
    assert "page-break-inside: avoid" in out


def test_nyomtatasi_stilus_nem_duplazodik():
    """Kétszeri futtatás nem fűzi be újra ugyanazt a blokkot."""
    once = with_print_css(_doc(["A"]))
    assert with_print_css(once) == once


def test_stiluslap_nelkul_valtozatlan():
    """Nincs hova beszúrni → hozzá se nyúlunk."""
    src = "<html><body><h2>A</h2></body></html>"
    assert with_print_css(src) == src


def test_finish_report_mindkettot_elvegzi():
    """A generátorok egyetlen hívása: jegyzék ÉS nyomtatási stílus."""
    out = finish_report(_doc([f"Cím {i}" for i in range(TOC_MIN_SECTIONS)]))
    assert '<nav class="toc' in out
    assert "@media print" in out


def test_minden_jelentesben_van_nyomtatasi_stilus():
    """Mind a NYOLC generátor átmegy a `finish_report`-on.

    Hét jelentésből ötben eredetileg EGYÁLTALÁN nem volt `@media print`
    blokk — azok a képernyős margókkal kerültek papírra. Ez a teszt a
    forrásban rögzíti, hogy egyik se maradjon ki.

    A darabszám szándékosan pontos: új jelentés-generátornál a teszt
    elhasal, és a szám átírása az a pillanat, amikor eldől, hogy az új
    lap is a közös nyomtatási stíluson megy-e át. (A nyolcadik az
    edzésterv-lap.)
    """
    import pathlib
    src = (pathlib.Path(__file__).resolve().parent.parent
           / "handball" / "pipeline" / "report_html.py").read_text("utf-8")
    docs = src.count('f"""<!DOCTYPE html>')
    finished = src.count('return finish_report(f"""<!DOCTYPE html>')
    assert docs == finished == 8, (docs, finished)


# --- Készítés-bélyeg ---------------------------------------------------

def _stamped(**kw):
    from handball.pipeline.report_html import with_stamp
    src = ("<html><head><style>x{}</style></head><body><header></header>"
           "<h2>A</h2><footer>Lábléc-szöveg</footer></body></html>")
    return with_stamp(src, **kw)


def test_belyeg_a_lablecbe_kerul():
    """A jelentés megmondja, MIKOR készült — percre pontosan.

    Az edzőnél mappában állnak a nyomatok; ugyanarról az ellenfélről a
    szeptemberi és a novemberi felderítés eddig megkülönböztethetetlen
    volt.
    """
    from datetime import datetime
    out = _stamped(when=datetime(2026, 3, 14, 9, 5))
    assert "2026-03-14 09:05" in out
    assert out.index("Lábléc-szöveg") < out.index("Kelt:")
    assert out.index("Kelt:") < out.index("</footer>")


def test_belyeg_nem_bantja_a_meglevo_lablecet():
    """A meglévő láblécszöveg érintetlen marad."""
    out = _stamped()
    assert "Lábléc-szöveg" in out
    assert out.count("</footer>") == 1


def test_lablec_nelkul_nincs_belyeg():
    """Nincs hova tenni → hozzá se nyúlunk."""
    from handball.pipeline.report_html import with_stamp
    src = "<html><body><h2>A</h2></body></html>"
    assert with_stamp(src) == src


def test_belyeg_stilusa_egyszer_kerul_be():
    """A bélyeg stílusa nem duplázódik ismételt futtatásnál."""
    from handball.pipeline.report_html import with_stamp
    twice = with_stamp(_stamped())
    assert twice.count("footer .stamp") == 1


def test_eles_jelentes_datumozott():
    """Éles jelentésen is ott a bélyeg — ez a lényeg, nem a segéd-HTML."""
    from handball.pipeline.report_html import scouting_report_html
    from handball.pipeline.scouting import ScoutingReport
    rep = ScoutingReport(
        team="away", team_name="Szeged", matches=1,
        attack_share_pct=60.0, fast_break_pct=10.0, avg_ball_speed_ms=4.0,
        avg_attack_duration_s=8.0, defense_main="6-0",
        defense_distribution={"6-0": 100.0},
        attack_centroid_x=30.0, attack_centroid_y=10.0, num_figures=0,
        attacks=10, shots=8, goals=4, turnovers=2, shot_efficiency_pct=50.0,
        key_players=[], strengths=[], weaknesses=[], keys_to_game=[],
    )
    assert "Kelt:" in scouting_report_html(rep)
