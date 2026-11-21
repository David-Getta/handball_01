"""
Tesztek a figura-lap belső építőelemeire (figura_lap.py).

A lap és a füzet egészét a tests/test_figura3d.py nézi; itt a
segédek közvetlenül: a kulcs-pozíció neve, az út helye egy
kulcs-pozíción, a támadó térfélre vágott ábra, a szám-alak, a
dokumentum-keret és egy figura törzse.

Futtatás:
    python -m pytest tests/test_figura_lap.py -q
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.pipeline import figura_lap as fl  # noqa: E402
from handball.pipeline.play_simulation import DefenseModel  # noqa: E402


def test_pont_felirat_a_kulcs_pozicio_neve():
    """Három pontnál Kezdő / Közép / Vég, kettőnél Kezdő / Vég, többnél
    sorszám ("2. pont")."""
    assert [fl._pont_felirat(i, 3) for i in range(3)] == [
        "Kezdő", "Közép", "Vég"]
    assert [fl._pont_felirat(i, 2) for i in range(2)] == ["Kezdő", "Vég"]
    assert [fl._pont_felirat(i, 4) for i in range(4)] == [
        "1. pont", "2. pont", "3. pont", "4. pont"]
    assert fl._pont_felirat(0, 1) == "1. pont"


def test_hely_az_ut_helye_a_kulcs_pozicion():
    """Ha az útnak ugyanannyi pontja van, mint a figurának kulcs-
    pozíciója, a hely maga a pont; rövidebb útnál arányosan,
    szakaszonként lineárisan (a két pontos út a 3 pontos figura közepén
    félúton jár)."""
    ut3 = [(20.0, 10.0), (26.0, 8.0), (30.0, 12.0)]
    assert [fl._hely(ut3, i, 3) for i in range(3)] == ut3
    ut2 = [(20.0, 10.0), (30.0, 6.0)]
    assert fl._hely(ut2, 0, 3) == (20.0, 10.0)
    assert fl._hely(ut2, 1, 3) == (25.0, 8.0)
    assert fl._hely(ut2, 2, 3) == (30.0, 6.0)
    # Hosszabb út rövidebb figurán: a végek a végek.
    assert fl._hely(ut3, 0, 2) == (20.0, 10.0)
    assert fl._hely(ut3, 1, 2) == (30.0, 12.0)


def test_hely_egy_pontos_ut_vagy_egy_kulcs_pozicio():
    """Az egy pontos (helyben álló) játékos minden kulcs-pozíción ott
    áll; egyetlen kulcs-pozíciónál a kezdőpont a hely — osztás nélkül."""
    assert fl._hely([(24.0, 4.0)], 0, 3) == (24.0, 4.0)
    assert fl._hely([(24.0, 4.0)], 2, 3) == (24.0, 4.0)
    assert fl._hely([(20.0, 10.0), (30.0, 6.0)], 0, 1) == (20.0, 10.0)


def test_szam_egy_tizedes_magyar_vesszovel():
    assert fl._szam(7.0) == "7,0" and fl._szam(3.456) == "3,5"
    assert fl._szam(0) == "0,0" and fl._szam(12.04) == "12,0"


def test_dokumentum_onallo_html_a_cimmel_es_a_jelmagyarazattal():
    """A dokumentum-keret önálló HTML: escape-elt cím, a közös stílus (a
    kiegészítő stílussal), a törzs és a jelmagyarázat."""
    h = fl._dokumentum("Kereszt <b>", "<h1>törzs</h1>", ".x{color:red}")
    assert h.startswith('<!DOCTYPE html><html lang="hu"><head>'
                        '<meta charset="utf-8">')
    assert "<title>Kereszt &lt;b&gt;</title>" in h
    assert ".x{color:red}</style>" in h
    assert "<body><h1>törzs</h1>" in h
    assert "Kék nyíl: futás a következő pontig" in h
    assert h.endswith("</body></html>")
    assert ".x{" not in fl._dokumentum("c", "t")


def test_vagott_abra_a_tamado_terfelre_vag():
    """Az ábra a pálya x0..40 m-es szeletét mutatja a lap szélességében:
    a nézet (viewBox) a szelet, a kép szélessége állandó — a kisebb
    szelet nagyobb nagyítást (és magasabb képet) ad; a játékosok és a
    nyíl benne vannak."""
    d = {"players": [{"x": 30.0, "y": 10.0, "team": "home", "jersey": 1},
                     {"x": 34.0, "y": 9.0, "team": "away", "jersey": 5}],
         "ball": (30.0, 10.0), "arrows": [(30.0, 10.0, 33.0, 8.0, 1)]}
    fel = fl._vagott_abra(d, 20.0)                # a támadó térfél
    assert fel.startswith("<svg viewBox=") and fel.endswith("</svg>")
    assert f'width="{fl.FIGURA_LAP_ABRA_PX}"' in fel
    vb = [float(v) for v in re.search(r'viewBox="([^"]+)"', fel)
          .group(1).split()]
    assert abs(vb[0] - vb[2]) < 0.6               # a szelet a pálya fele
    assert fel.count("<circle") == 3              # két játékos + a labda
    assert 'class="nyil"' in fel
    # Teljes pálya (x0 = 0): a nézet a 0-tól indul, a kép alacsonyabb.
    teljes = fl._vagott_abra(d, 0.0)
    assert 'viewBox="0.0 0 340.0 170"' in teljes

    def magassag(svg):
        return int(re.search(r'height="(\d+)"', svg).group(1))
    assert magassag(fel) == 2 * magassag(teljes)


def test_figura_resz_lepesenkent_abra_es_leiras():
    """Egy figura törzse: cím, a védelem neve és az összegzés, kulcs-
    pozíciónként egy lépés ábrával és leírással — a futás távja, a passz
    iránya, a végén a befejező; a helyben álló játékos nem "fut"."""
    utak = [[(22.0, 10.0), (29.0, 10.0)], [(24.0, 4.0), (24.0, 4.0)]]
    h = fl._figura_resz(utak, [0, 1], DefenseModel(), nev="Kereszt <A>",
                        vedo_nev="Alap 6-0 fal")
    assert h.startswith("<h1>Kereszt &lt;A&gt;</h1>")
    assert "Alap 6-0 fal · a mozgás " in h and " mp (valós tempóban)" in h
    assert "labda 1 → 2" in h
    assert h.count('<div class="lepes">') == 2
    assert '<div class="lc">1. Kezdő → Vég</div>' in h
    assert '<div class="lc">2. Vég</div>' in h
    assert "1. fut 7,0 m · passz: 1 → 2" in h
    assert "2. fut" not in h                      # helyben állt
    assert "labda: 2. — befejezés" in h
    assert h.count("<svg") == 2


def test_figura_resz_mozgas_nelkul_varakozas():
    """Ha két kulcs-pozíció között senki sem mozdul és nincs passz, a
    lépés leírása "helyben — várakozás" (nem üres sor)."""
    utak = [[(26.0, 10.0), (26.0, 10.0)], [(24.0, 4.0), (24.0, 4.0)]]
    h = fl._figura_resz(utak, [0, 0], DefenseModel(), nev="Áll",
                        vedo_nev="Fal")
    assert "helyben — várakozás" in h
    assert "passz:" not in h and "labda 1 →" not in h
    assert "labda: 1. — befejezés" in h
