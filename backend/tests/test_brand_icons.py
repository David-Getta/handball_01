"""A Sport Machine JELKÉP (logó) őrei.

Egy jelkép, sok helyen: az appban a kliens RAJZOLJA
(`client/lib/ui/logo.dart`), a gépen látszó ikonokat a
`packaging/make_icons.py` állítja elő ugyanazzal a geometriával. Ha a
kettő szétcsúszik — vagy az ikon-fájlok kimaradnak a kiadásból —, a
felhasználó két különböző "logót" lát: egyet a tálcán, egyet az appban.

Futtatás:
    python -m pytest tests/test_brand_icons.py
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

GYOKER = Path(__file__).resolve().parent.parent.parent
IKONOK = GYOKER / "packaging" / "icons"


def test_a_windows_ikon_letezik_es_ervenyes():
    """A .ico a telepítő, az .exe és az ablak ikonja — ha hiányzik vagy
    sérült, a felhasználó a Flutter alap-ikonját kapja vissza."""
    f = IKONOK / "sportmachine.ico"
    assert f.exists(), "hiányzik a Windows-ikon (packaging/make_icons.py)"
    d = f.read_bytes()
    rez, tipus, db = struct.unpack("<HHH", d[:6])
    assert (rez, tipus) == (0, 1), "nem ICO-fejléc"
    assert db >= 5, "túl kevés méret az ikonban"
    meretek = set()
    for i in range(db):
        w, h, _sz, _r, _p, _b, hossz, eltolas = struct.unpack(
            "<BBBBHHII", d[6 + 16 * i:22 + 16 * i])
        meretek.add(w or 256)
        assert eltolas + hossz <= len(d), "csonka ikon-bejegyzés"
        assert hossz > 0
    # A kis méretek KLASSZIKUS (DIB) alakban: a PNG-be ágyazott ikont a
    # régi eszközök nem értik, és pont a 16/32-es jelenik meg a tálcán.
    for i in range(db):
        w, *_x, hossz, eltolas = struct.unpack(
            "<BBBBHHII", d[6 + 16 * i:22 + 16 * i])
        png = d[eltolas:eltolas + 4] == b"\x89PNG"
        if (w or 256) <= 64:
            assert not png, f"a {w}x{w} ikon PNG-be ágyazott"
    assert {16, 32, 48, 256} <= meretek, f"hiányzó méretek: {meretek}"


def test_a_macos_ikonkeszlet_teljes():
    """A macOS AppIcon.appiconset a `flutter create` neveit várja — a
    kiadási munkafolyamat ezekre a nevekre másol."""
    for m in (16, 32, 64, 128, 256, 512, 1024):
        f = IKONOK / f"app_icon_{m}.png"
        assert f.exists(), f"hiányzik: {f.name}"
        d = f.read_bytes()
        assert d[:4] == b"\x89PNG", f"{f.name}: nem PNG"
        # A PNG IHDR-je a 16. bájttól: szélesség/magasság.
        w, h = struct.unpack(">II", d[16:24])
        assert (w, h) == (m, m), f"{f.name}: {w}x{h} a várt {m}x{m} helyett"


def test_a_jelkep_ujragenerálhato(tmp_path):
    """A rajz forrása KÓD, nem egy elveszíthető képfájl: bármikor
    újragenerálható (más méretben is), és a kimenet érvényes marad."""
    pytest.importorskip("cv2")
    import sys
    sys.path.insert(0, str(GYOKER / "packaging"))
    import make_icons

    kep = make_icons.draw(64)
    assert kep.shape == (64, 64, 4)
    # A sarok átlátszó (lekerekített ikon-alak), a közép nem.
    assert kep[0, 0, 3] < 40 and kep[32, 32, 3] == 255
    ki = make_icons.main(tmp_path)
    assert (ki / "sportmachine.ico").stat().st_size > 1000


def test_a_kliens_a_valodi_jelkepet_rajzolja():
    """A fejlécben és a nyitóképernyőn a JELKÉP legyen, ne egy általános
    Material-ikon (korábban egy háromszög-ikon állt mindkét helyen)."""
    ui = GYOKER / "client" / "lib" / "ui"
    logo = (ui / "logo.dart").read_text(encoding="utf-8")
    assert "class SportMachineLogo" in logo
    # A geometria a Python-rajzoló konstansaival egyezik.
    py = (GYOKER / "packaging" / "make_icons.py").read_text(encoding="utf-8")
    for nev, dart in (("CORNER_R", "cornerR"), ("GOAL_R", "goalR"),
                      ("BALL_R", "ballR"), ("LINE_W", "lineW")):
        ertek = [s for s in py.split("\n") if s.startswith(f"{nev} = ")]
        assert ertek, f"{nev} eltűnt a rajzolóból"
        szam = ertek[0].split("=")[1].split("#")[0].strip()
        assert f"{dart} = {szam}" in logo, (
            f"a kliens {dart} értéke nem a motoré ({nev} = {szam})")
    for f in ("shell/app_shell.dart", "bootstrap_screen.dart"):
        src = (ui / f).read_text(encoding="utf-8")
        assert "SportMachineLogo" in src, f"{f}: nincs benne a jelkép"
        assert "Icons.change_history_rounded" not in src, (
            f"{f}: még mindig az általános helyettesítő ikon van ott")


def test_a_kiadas_beteszi_az_ikonokat():
    """A platform-mappák a kiadáskor generálódnak (`flutter create`), és
    a Flutter az ALAP-ikonját teszi beléjük — a munkafolyamatnak tehát
    felül kell írnia mindkét platformon."""
    wf = (GYOKER / ".github" / "workflows"
          / "release.yml").read_text(encoding="utf-8")
    assert "packaging\\icons\\sportmachine.ico" in wf, "Windows-ikon nincs bemásolva"
    assert "app_icon_*.png" in wf, "macOS-ikonok nincsenek bemásolva"
    iss = (GYOKER / "packaging"
           / "installer_windows.iss").read_text(encoding="utf-8")
    assert "SetupIconFile" in iss, "a telepítő ikonja nincs beállítva"


def test_a_nyomtathato_jelentes_is_viseli_a_jelkepet():
    """A kinyomtatott / továbbküldött lapon is ott a márka. INLINE SVG,
    mert a jelentés ÖNÁLLÓ fájl: külső képre hivatkozva üres keret
    maradna a nyomtatásban."""
    from handball.pipeline.report_html import brand_svg

    svg = brand_svg(20)
    assert svg.startswith("<svg") and 'width="20"' in svg
    assert "<img" not in svg and "src=" not in svg, "külső kép a jelentésben"
    # A márka három színe (pályavonal, kapuelőtér, labda).
    for szin in ("#2FD9C4", "#D8B36B", "#FFC857"):
        assert szin in svg, f"hiányzó márka-szín: {szin}"
    src = (GYOKER / "backend" / "handball" / "pipeline"
           / "report_html.py").read_text(encoding="utf-8")
    assert src.count('class="brand"') == src.count("{brand_svg()}"), (
        "van olyan jelentés-fejléc, ami nem viseli a jelképet")
