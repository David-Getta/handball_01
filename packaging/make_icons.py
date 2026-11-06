"""A Sport Machine JELKÉP (logó) kirajzolása ikon-fájlokba.

Egy jelkép, sok helyen: az app fejlécében és a nyitóképernyőn a kliens
RAJZOLJA (client/lib/ui/logo.dart), a gépen látszó ikonokat pedig ez a
szkript állítja elő UGYANAZZAL a geometriával — így a telepítő, az
asztali parancsikon, az ablak ikonja és az appban látható jel egy
családba tartozik.

A JEL (packaging/brand/, `sportmachine-mark-*.svg`): négy ék egy
64 x 64-es négyzetben, két átlós sávba rendezve — a mozgás és az
elemzés iránya. Középpontosan szimmetrikus: 180 fokkal elforgatva
önmaga. A nyíl mindig jobbra fölé mutat, a jelet nem forgatjuk.

  - lekerekített sötét csempe (Court Ink),
  - négy teal ék (Signal Teal); a kétszínű változatban az alsó átló
    arany (Medal Gold) — a nyomtatott jelentések fejlécében ez áll.

Futtatás (a repó gyökeréből):

    python3 packaging/make_icons.py

Kimenet a packaging/icons/ mappába:
  - sportmachine.ico          — Windows (a .exe és a telepítő ikonja),
  - app_icon_<N>.png          — macOS AppIcon.appiconset méretei,
  - sportmachine_512.png      — általános használatra (dokumentáció, web).

A kiadási munkafolyamat ezeket MÁSOLJA a `flutter create` által
legenerált helyükre, mielőtt fordít — a platform-mappák ugyanis nincsenek
a repóban.
"""

from __future__ import annotations

import struct
from pathlib import Path

# A márka színei (packaging/brand/README.txt; a kliens palettája
# ugyanezeket használja) — BGRA sorrendben, hogy a jelkép a gépen és az
# appban ugyanúgy nézzen ki.
INK = (0x1F, 0x12, 0x06)         # #06121F — Court Ink (a csempe)
TEAL = (0xC4, 0xD9, 0x2F)        # #2FD9C4 — Signal Teal (a jel)
GOLD = (0x6B, 0xB3, 0xD8)        # #D8B36B — Medal Gold (kétszínű változat)

# A csempe lekerekítése az egység-négyzetben (a Dart-oldali logó ugyanez).
CORNER_R = 0.22

# A JEL négy éke a 64 x 64-es rajzdobozban (a márka SVG-jének pontjai).
# Az első kettő a felső-bal átló, a második kettő az alsó-jobb — a
# kétszínű változatban ez utóbbi kettő arany.
MARK_BOX = 64.0
# A jel VÉDETT TERÜLETE a csempén belül (a márkakönyv szerint a jel
# magasságának negyede jár körbe): a rajzdoboz ekkora peremmel ül a
# csempén, az egység-négyzet arányában.
MARK_INSET = 0.08
MARK = (
    ((23, 7), (49, 7), (28, 28), (28, 15), (15, 15)),
    ((11, 19), (24, 19), (24, 32), (7, 49), (7, 23)),
    ((57, 15), (57, 41), (49, 49), (49, 36), (36, 36)),
    ((32, 40), (45, 40), (45, 53), (41, 57), (15, 57)),
)

# Az ikon-fájlba kerülő méretek.
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
MAC_SIZES = (16, 32, 64, 128, 256, 512, 1024)
SS = 4                # ennyiszeres túlmintavételezés (élsimítás)


def draw(size: int, background: bool = True, duo: bool = False):
    """A jelkép BGRA képe `size` x `size` pixelen (numpy tömb).

    `background`: lekerekített sötét csempe (ikon-alak); ha False, csak a
    négy ék marad átlátszó háttéren. `duo`: az alsó átló arany.
    """
    import cv2
    import numpy as np

    n = size * SS
    img = np.zeros((n, n, 4), np.uint8)

    # Lekerekített csempe: téglalapok + sarok-körök (a maszkra rajzolunk,
    # így az átlátszó sarkok is élsimítottak lesznek a kicsinyítéskor).
    r = int(round(CORNER_R * n))
    mask = np.zeros((n, n), np.uint8)
    cv2.rectangle(mask, (r, 0), (n - r, n), 255, -1)
    cv2.rectangle(mask, (0, r), (n, n - r), 255, -1)
    for cx, cy in ((r, r), (n - r, r), (r, n - r), (n - r, n - r)):
        cv2.circle(mask, (cx, cy), r, 255, -1)
    if background:
        img[mask > 0] = (*INK, 255)

    # A négy ék: a rajzdoboz (64) a teljes csempére feszítve. Külön
    # maszkra rajzoljuk, hogy az él élsimított legyen a kicsinyítéskor.
    belso = n * (1.0 - 2 * MARK_INSET)
    perem = n * MARK_INSET

    def poly(pontok):
        return np.array([[int(round(perem + x / MARK_BOX * belso)),
                          int(round(perem + y / MARK_BOX * belso))]
                         for x, y in pontok], np.int32)

    for i, ek in enumerate(MARK):
        szin = GOLD if (duo and i >= 2) else TEAL
        cv2.fillPoly(img, [poly(ek)], (*szin, 255), cv2.LINE_AA)

    # A csempén KÍVÜLI pixelek átlátszók maradnak (a lekerekített sarok).
    img[mask == 0] = (0, 0, 0, 0)
    return cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA)


def png_bytes(size: int) -> bytes:
    """A jelkép PNG-ként, adott méretben."""
    import cv2
    ok, buf = cv2.imencode(".png", draw(size))
    if not ok:
        raise RuntimeError("a PNG-kódolás nem sikerült")
    return buf.tobytes()


def _bmp_entry(size: int) -> bytes:
    """Egy ICO-bejegyzés KLASSZIKUS (BMP/DIB) alakja.

    A PNG-be ágyazott ikont csak a Vista utáni Windows érti; a régi
    eszközök (és néhány telepítő-fordító) a DIB-alakot várják, ezért a
    kis méreteket így írjuk ki: 40 bájt fejléc, alulról fölfelé BGRA
    sorok, majd az (üres) AND-maszk."""
    img = draw(size)
    fej = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0, 0,
                      0, 0, 0, 0)
    sorok = b"".join(img[y].tobytes() for y in range(size - 1, -1, -1))
    # AND-maszk: 1 bit/pixel, sorok 4 bájtra igazítva, csupa 0 (látszik).
    sor_b = ((size + 31) // 32) * 4
    maszk = b"\x00" * (sor_b * size)
    return fej + sorok + maszk


def ico_bytes() -> bytes:
    """Több méretű Windows-ikon (.ico) — a nagyok PNG-ben, a kicsik DIB-ben."""
    kepek = [(s, _bmp_entry(s) if s <= 64 else png_bytes(s))
             for s in ICO_SIZES]
    fej = struct.pack("<HHH", 0, 1, len(kepek))
    eltolas = 6 + 16 * len(kepek)
    bejegyzesek, adatok = b"", b""
    for s, data in kepek:
        bejegyzesek += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0,
                                   1, 32, len(data), eltolas)
        eltolas += len(data)
        adatok += data
    return fej + bejegyzesek + adatok


def main(out_dir: Path | None = None) -> Path:
    out = out_dir or (Path(__file__).resolve().parent / "icons")
    out.mkdir(parents=True, exist_ok=True)
    (out / "sportmachine.ico").write_bytes(ico_bytes())
    for s in MAC_SIZES:
        (out / f"app_icon_{s}.png").write_bytes(png_bytes(s))
    (out / "sportmachine_512.png").write_bytes(png_bytes(512))
    print(f"jelkép kiírva: {out}")
    return out


if __name__ == "__main__":
    main()
