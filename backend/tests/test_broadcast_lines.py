"""
Tesztek a pályavonal-felismerésre (broadcast_lines.py) — szintetikus
képekkel, valódi közvetítés nélkül.

Futtatás:
    python -m pytest tests/test_broadcast_lines.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from handball.pipeline.broadcast_lines import (
    detect_court_lines, edge_mask, hough_lines,
)


def _canvas(h=120, w=200, floor=100):
    return np.full((h, w), floor, dtype=np.uint8)


def _draw_hline(img, y, val=220, thickness=2):
    img[y:y + thickness, :] = val


def _draw_vline(img, x, val=220, thickness=2):
    img[:, x:x + thickness] = val


def test_edge_mask_marks_thin_bright_line():
    img = _canvas()
    _draw_hline(img, 60)
    mask = edge_mask(img)
    # A vonal pixelei jelölve, a padló nem.
    assert mask[60, 100]
    assert not mask[30, 100]


def test_hough_finds_horizontal_and_vertical():
    img = _canvas()
    _draw_hline(img, 60)     # vízszintes vonal: normálisa 90 fok
    _draw_vline(img, 150)    # függőleges vonal: normálisa 0 fok
    lines = hough_lines(edge_mask(img))
    assert len(lines) >= 2
    angles = sorted(abs(t) for (t, _, _) in lines[:2])
    assert angles[0] < 6.0                # függőleges (normálisa ~0 fok)
    assert abs(angles[1] - 90.0) < 6.0    # vízszintes (normálisa ~90 fok)


def test_detect_court_lines_returns_endpoints():
    img = _canvas()
    _draw_hline(img, 40)
    out = detect_court_lines(img)
    assert out, "legalább egy vonal kell"
    top = out[0]
    (x1, y1), (x2, y2) = top["p1"], top["p2"]
    # A vízszintes vonal végpontjai a kép két szélén, y ~ 40-41.
    assert abs(y1 - 40.5) < 3 and abs(y2 - 40.5) < 3
    assert abs(x1 - x2) > 150


def test_empty_image_gives_no_lines():
    assert detect_court_lines(_canvas()) == []


def test_line_intersections_finds_corner():
    """Vízszintes + függőleges vonal metszése a (150, 40) sarok-jelölt;
    két párhuzamos vonal nem ad metszést."""
    from handball.pipeline.broadcast_lines import line_intersections
    img = _canvas()
    _draw_hline(img, 40)
    _draw_vline(img, 150)
    lines = detect_court_lines(img)
    pts = line_intersections(lines, width=200, height=120)
    assert pts, "kell metszéspont"
    p = pts[0]
    assert abs(p["x"] - 150.5) < 4 and abs(p["y"] - 40.5) < 4
    # Két párhuzamos vízszintes vonal: nincs (képen belüli) metszés.
    img2 = _canvas()
    _draw_hline(img2, 30)
    _draw_hline(img2, 80)
    lines2 = detect_court_lines(img2)
    assert line_intersections(lines2, width=200, height=120) == []


def test_suggest_calibration_quad_from_rectangle():
    """Két vízszintes + két függőleges vonal → a 4 metszéspont adja a
    javasolt négyszöget, bal-felsőtől óramutató szerint."""
    from handball.pipeline.broadcast_lines import (
        line_intersections, suggest_calibration_quad,
    )
    img = _canvas(h=160, w=240)
    _draw_hline(img, 30)
    _draw_hline(img, 130)
    _draw_vline(img, 40)
    _draw_vline(img, 200)
    lines = detect_court_lines(img)
    corners = line_intersections(lines, width=240, height=160)
    quad = suggest_calibration_quad(corners, width=240, height=160)
    assert quad is not None and len(quad) == 4
    (tl, tr, br, bl) = quad
    assert tl[0] < tr[0] and tl[1] < bl[1]
    assert abs(tl[0] - 40.5) < 4 and abs(tl[1] - 30.5) < 4
    assert abs(br[0] - 200.5) < 4 and abs(br[1] - 130.5) < 4


def test_suggest_calibration_quad_rejects_small():
    """Apró négyszögre (a kép <15%-a) nincs javaslat — marad a kézi."""
    from handball.pipeline.broadcast_lines import suggest_calibration_quad
    tiny = [{"x": 10, "y": 10, "lines": (0, 1)},
            {"x": 20, "y": 10, "lines": (0, 2)},
            {"x": 20, "y": 20, "lines": (3, 1)},
            {"x": 10, "y": 20, "lines": (3, 2)}]
    assert suggest_calibration_quad(tiny, width=240, height=160) is None


# --- Színes vonalak (több sportot kiszolgáló csarnok) --------------------
# A felhasználó felvételén (THW Kiel vs BT Füchse, Graz) a csarnok padlóján
# egymáson futnak a sportágak vonalai: a KÉZILABDA-pályát PIROS vonal
# jelöli, mellette kék/zöld vonalak és nagy festett mezők (sárga
# kapuelőtér). Ezek a tesztek ezt a helyzetet modellezik.

def _hall(h=160, w=240, floor=(205, 180, 140)):
    """Világos (fa) padló, RGB."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:, :] = floor
    return img


def test_color_line_mask_finds_the_red_line_not_the_blue_one():
    """A piros maszk a PIROS vonalat jelöli, a kéket nem (és fordítva)."""
    from handball.pipeline.broadcast_lines import color_line_mask

    img = _hall()
    img[80:83, :] = (215, 45, 40)      # piros kézilabda-vonal
    img[:, 120:123] = (40, 70, 210)    # kék (másik sport) vonal
    red = color_line_mask(img, "piros")
    blue = color_line_mask(img, "kek")
    assert red[81, 30] and not red[30, 121]
    assert blue[30, 121] and not blue[81, 30]


def test_color_mask_ignores_the_inside_of_a_painted_area():
    """A nagy festett MEZŐ belseje nem vonal — csak a széle jelölődik
    (a sárga kapuelőtér különben elárasztaná a Hough-teret)."""
    from handball.pipeline.broadcast_lines import color_line_mask

    img = _hall()
    img[40:120, 60:180] = (225, 215, 45)   # nagy sárga festett mező
    mask = color_line_mask(img, "sarga")
    assert not mask[80, 120], "a mező KÖZEPE nem lehet vonal-pixel"


def test_auto_picks_the_red_court_lines_in_a_multi_sport_hall():
    """Auto módban a piros (kézilabda) vonalak nyernek, ha azokból van a
    legtöbb — a fehér vonal hiányában is talál pályát a rendszer."""
    from handball.pipeline.broadcast_lines import detect_court_lines_color

    img = _hall()
    for y in (30, 130):                       # két piros oldalvonal
        img[y:y + 3, :] = (215, 45, 40)
    img[:, 20:23] = (215, 45, 40)             # piros alapvonal
    img[:, 200:202] = (40, 70, 210)           # egy kék idegen vonal
    found = detect_court_lines_color(img, "auto")
    assert found["color"] == "piros", found["pixels"]
    assert found["pixels"]["piros"] > found["pixels"]["kek"]
    assert len(found["lines"]) >= 2


def test_explicit_color_overrides_auto():
    """A felhasználó felülbírálhatja a szín-választást."""
    from handball.pipeline.broadcast_lines import detect_court_lines_color

    img = _hall()
    img[80:83, :] = (215, 45, 40)
    img[:, 120:123] = (40, 70, 210)
    assert detect_court_lines_color(img, "kek")["color"] == "kek"
    assert detect_court_lines_color(img, "feher")["color"] == "feher"


# --- Festett mezők széle és a színek tartalék-sora ------------------------
# A grazi csarnokban (THW Kiel vs BT Füchse) a felhasználó szerint a gép
# "nem nagyon látja a pálya vonalait": a padlón a kosár- és röplabda-
# vonalak (kék) együtt több pixelt adnak, mint a kézilabda piros vonalai,
# és a legjobban látszó pálya-elem a FESTETT sárga kapuelőtér és a zöld
# felület — a vékony-vonal-maszk ezek szélét eldobja.

def test_a_festett_mezo_szele_vonal_a_vekony_vonal_es_a_belseje_nem():
    from handball.pipeline.broadcast_lines import field_edge_mask

    img = _hall()
    img[40:120, 60:180] = (225, 215, 45)   # sárga festett mező
    img[:, 20:23] = (40, 70, 210)          # vékony kék vonal
    mask = field_edge_mask(img)
    assert mask[38:43, 120].any(), "a mező felső széle nem él"
    assert mask[80, 58:63].any(), "a mező bal széle nem él"
    assert not mask[80, 120], "a mező belseje nem lehet él"
    assert not mask[80, 15:28].any(), "a vékony vonal nem festett mező"
    # A parketta (kevésbé telített) nem festett mező.
    assert not field_edge_mask(_hall()).any()


def test_a_festett_mezo_szelebol_is_all_ossze_palya():
    """"mezo": a festett játékfelület széléből négyszög-javaslat."""
    from handball.pipeline.broadcast_lines import detect_court_quad

    img = _hall(h=200, w=300)
    img[40:170, 30:270] = (40, 170, 90)    # zöld játékfelület
    r = detect_court_quad(img, "mezo")
    assert r["color"] == "mezo" and r["suggested_quad"], r["lines"]
    vart = [(30, 40), (269, 40), (269, 169), (30, 169)]
    for (x, y), (vx, vy) in zip(r["suggested_quad"], vart):
        assert abs(x - vx) <= 5 and abs(y - vy) <= 5, r["suggested_quad"]


def test_auto_tovabbprobal_ha_a_legtobb_pixelbol_nem_all_ossze_palya():
    """A sok kék (más sport) vonal párhuzamos, négyszöget nem ad — az auto
    a következő színnel (piros) próbálkozik, és abból összeáll a pálya."""
    from handball.pipeline.broadcast_lines import detect_court_quad

    img = _hall(h=200, w=300)
    for x in range(10, 300, 20):           # sok párhuzamos kék vonal
        img[:, x:x + 3] = (40, 70, 210)
    for y in (40, 170):                    # piros oldalvonalak
        img[y:y + 3, :] = (215, 45, 40)
    for x in (40, 260):                    # piros alapvonalak
        img[:, x:x + 3] = (215, 45, 40)
    r = detect_court_quad(img, "auto")
    assert r["pixels"]["kek"] > r["pixels"]["piros"]
    assert r["tried"][0] == "kek" and r["color"] == "piros", r["tried"]
    assert r["suggested_quad"]


def test_kert_szinnel_nincs_tartalek():
    """A felhasználó választotta a színt: ha abból nincs pálya, nem
    cseréljük ki a háta mögött."""
    from handball.pipeline.broadcast_lines import detect_court_quad

    img = _hall(h=200, w=300)
    for x in range(10, 300, 20):
        img[:, x:x + 3] = (40, 70, 210)
    r = detect_court_quad(img, "kek")
    assert r["color"] == "kek" and r["tried"] == ["kek"]
    assert r["suggested_quad"] is None


# --- Csak a padlón ------------------------------------------------------
# A grazi kockán (valódi képernyőkép) a felismert vonalak zöme a
# LELÁTÓRÓL jött: ülősorok, üveg-korlát, reklámtábla, mennyezet — a
# Hough az egész képen keresett.

def _lelato_es_palya(h=300, w=400):
    """Felül sötét lelátó világos ülősor-vonalakkal és függőleges
    korlát-oszlopokkal (rács → sok metszéspont), alul fa padló piros
    pályával."""
    img = np.zeros((h, w, 3), dtype=np.uint8)
    img[:120] = (40, 40, 45)
    for y in range(10, 115, 15):              # ülősorok
        img[y:y + 2, :] = (230, 230, 230)
    for x in range(20, w, 60):                # korlát-oszlopok
        img[:118, x:x + 2] = (230, 230, 230)
    img[120:] = (205, 180, 140)               # parketta
    for y in (150, 280):                      # piros oldalvonalak
        img[y:y + 3, :] = (215, 45, 40)
    for x in (40, 360):                       # piros alapvonalak
        img[120:, x:x + 3] = (215, 45, 40)
    return img


def test_a_lelato_vonalai_nem_palyavonalak():
    """A padló-szűkítés nélkül a lelátó rácsából áll össze négyszög; a
    padlón keresve a piros pályából."""
    from handball.pipeline.broadcast_lines import detect_court_quad, floor_mask

    img = _lelato_es_palya()
    roi = floor_mask(img)
    assert roi is not None
    assert roi[200, 200] and not roi[50, 200], "a padló-maszk rossz helyen"
    r = detect_court_quad(img, "auto")
    assert r["floor"] is True
    assert r["suggested_quad"], r["tried"]
    assert r["color"] == "piros", r["tried"]
    assert min(y for _x, y in r["suggested_quad"]) >= 115
    regi = detect_court_quad(img, "auto", use_floor=False)
    assert regi["color"] == "feher"
    assert regi["suggested_quad"] and min(
        y for _x, y in regi["suggested_quad"]) < 115


def test_egyszinu_kepnel_nincs_padlo_szukites():
    from handball.pipeline.broadcast_lines import floor_mask

    assert floor_mask(_hall()) is None


def test_a_festett_feluleten_atfuto_feher_vonal_nem_el():
    """A zöld felületet átszelő vékony fehér vonal mentén nincs "él" — a
    zárás a rést bezárja, a felület egy folt marad."""
    from handball.pipeline.broadcast_lines import field_edge_mask

    img = _hall(h=200, w=300)
    img[40:170, 30:270] = (40, 170, 90)
    img[100:103, 30:270] = (240, 240, 240)    # fehér röplabda-vonal
    mask = field_edge_mask(img)
    assert not mask[95:108, 100:200].any(), "a fehér vonal mentén él"
    assert mask[38:43, 150].any()


# ---- Belső segédek közvetlenül (második kör) --------------------------------

def test_erode_es_dilate_negyzetes_szerkeszto_elemmel():
    """A bináris tágítás r sugarú négyzettel hizlal, az erózió ugyanennyit
    farag: egy 5×5-ös folt r=1 erózió után 3×3, tágítás után 7×7; a
    kettő egymás után (nyitás) az eredeti foltot adja vissza."""
    from handball.pipeline.broadcast_lines import _dilate, _erode

    m = np.zeros((15, 15), dtype=bool)
    m[5:10, 5:10] = True
    e = _erode(m, 1)
    assert e.sum() == 9 and e[6:9, 6:9].all()
    d = _dilate(m, 1)
    assert d.sum() == 49 and d[4:11, 4:11].all()
    assert np.array_equal(_dilate(_erode(m, 1), 1), m)
    assert e.dtype == bool and d.dtype == bool
    # r = 0: változatlan; a bemenetet egyik sem módosítja.
    assert np.array_equal(_erode(m, 0), m) and np.array_equal(_dilate(m, 0), m)
    assert m.sum() == 25


def test_erode_a_kepszelig_ero_folt_szele_nem_el():
    """A képen kívül IGAZ: a képszélig érő folt széle nem kopik le
    (különben a kép kerete vonalnak látszana); a vékony vonal viszont
    eltűnik, az üres kép üres marad."""
    from handball.pipeline.broadcast_lines import _dilate, _erode

    tele = np.ones((10, 10), dtype=bool)
    assert _erode(tele, 2).all()
    sarok = np.zeros((10, 10), dtype=bool)
    sarok[:4, :4] = True
    e = _erode(sarok, 1)
    assert e[:3, :3].all() and e.sum() == 9      # csak a belső szélek kopnak
    vonal = np.zeros((10, 10), dtype=bool)
    vonal[5, :] = True
    assert not _erode(vonal, 1).any()
    ures = np.zeros((6, 6), dtype=bool)
    assert not _erode(ures, 1).any() and not _dilate(ures, 2).any()


def test_thin_line_mask_a_vonal_megmarad_a_folt_belseje_kiesik():
    """A vékony, a környezeténél erősebb pixelek maszkja: a keskeny
    vonal megmarad, az egybefestett nagy folt BELSEJE kiesik; a túl kicsi
    képen (nincs szomszéd, amihez mérni lehetne) üres maszk."""
    from handball.pipeline.broadcast_lines import _thin_line_mask

    kep = np.zeros((60, 60), np.uint8)
    kep[30, 10:50] = 200                          # vékony vízszintes vonal
    maszk = _thin_line_mask(kep, 50)
    assert maszk[30, 20:40].all()
    assert not maszk[20, 20:40].any()
    folt = np.zeros((60, 60), np.uint8)
    folt[10:50, 10:50] = 200                      # nagy tömör folt
    assert not _thin_line_mask(folt, 50)[25:35, 25:35].any()
    # A küszöbnél gyengébb vonal nem vonal.
    halvany = np.zeros((60, 60), np.uint8)
    halvany[30, 10:50] = 30
    assert not _thin_line_mask(halvany, 50).any()
    kicsi = _thin_line_mask(np.full((8, 8), 200, np.uint8), 50)
    assert kicsi.shape == (8, 8) and not kicsi.any()


def test_auto_color_a_szin_csak_egyertelmu_folennyel_nyer():
    """Az "auto" mód: a legtöbb vonal-pixelt adó szín nyer, ha legalább
    1,3-szor annyit hoz, mint a fehér — különben a fehér marad (a fehér
    vonalas csarnok az alapeset); pixel nélkül is a fehér."""
    from handball.pipeline.broadcast_lines import (COLOR_WIN_RATIO,
                                                   LINE_COLORS, _auto_color)

    assert COLOR_WIN_RATIO == 1.3

    def pixelek(**szamok):
        p = {c: 0 for c in LINE_COLORS}
        p["feher"] = 0
        p.update(szamok)
        return p

    assert _auto_color(pixelek(feher=1000, kek=1300)) == "kek"
    assert _auto_color(pixelek(feher=1000, kek=1299)) == "feher"
    assert _auto_color(pixelek(feher=1000, kek=2000, piros=2500)) == "piros"
    assert _auto_color(pixelek(feher=0, sarga=2)) == "sarga"
    assert _auto_color(pixelek(feher=0, sarga=1)) == "feher"
    assert _auto_color(pixelek()) == "feher"
