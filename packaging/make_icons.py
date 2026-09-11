"""A Sport Machine JELKÉP (logó) kirajzolása ikon-fájlokba.

Egy jelkép, sok helyen: az app fejlécében és a nyitóképernyőn a kliens
RAJZOLJA (client/lib/ui/logo.dart), a gépen látszó ikonokat pedig ez a
szkript állítja elő UGYANAZZAL a geometriával — így a telepítő, az
asztali parancsikon, az ablak ikonja és az appban látható jel egy
családba tartozik.

A rajz (egység-négyzetben, 0..1) a termék fő képe, a FELÜLNÉZETI PÁLYA:
  - lekerekített sötét háttér,
  - teal keretű pálya felülnézetből, felezővonallal,
  - a két kapuelőtér arany félköre,
  - világos labda a jobb félen, mögötte halvány mozgás-ív.

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

# A kliens színei (client/lib/theme/app_theme.dart) — BGRA sorrendben,
# hogy a jelkép a gépen és az appban ugyanúgy nézzen ki.
BG = (0x1C, 0x14, 0x0E)          # #0E141C — sötét háttér
COURT_FILL = (0x24, 0x1C, 0x0B)  # #0B1C24 — a pálya sötét kitöltése
ACCENT = (0xC4, 0xD9, 0x2F)      # #2FD9C4 — teal pályavonalak
GOLD = (0x6B, 0xB3, 0xD8)        # #D8B36B — arany kapuelőtér-ívek
BALL = (0x57, 0xC8, 0xFF)        # #FFC857 — a labda

# A rajz arányai az egység-négyzetben (a Dart-oldali logó ugyanezek).
CORNER_R = 0.22       # a háttér lekerekítése
COURT_X0, COURT_X1 = 0.10, 0.90   # a pálya (felülnézet) kerete
COURT_Y0, COURT_Y1 = 0.245, 0.755
COURT_R = 0.06        # a pálya-keret lekerekítése
LINE_W = 0.045        # a pályavonalak vastagsága
GOAL_R = 0.155        # a kapuelőtér félkörének sugara
BALL_CX, BALL_CY = 0.655, 0.375
BALL_R = 0.075

# Az ikon-fájlba kerülő méretek.
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
MAC_SIZES = (16, 32, 64, 128, 256, 512, 1024)
SS = 4                # ennyiszeres túlmintavételezés (élsimítás)


def draw(size: int):
    """A jelkép BGRA képe `size` x `size` pixelen (numpy tömb)."""
    import cv2
    import numpy as np

    n = size * SS
    img = np.zeros((n, n, 4), np.uint8)

    # Lekerekített háttér: téglalapok + sarok-körök (a maszkra rajzolunk,
    # így az átlátszó sarkok is élsimítottak lesznek a kicsinyítéskor).
    r = int(round(CORNER_R * n))
    mask = np.zeros((n, n), np.uint8)
    cv2.rectangle(mask, (r, 0), (n - r, n), 255, -1)
    cv2.rectangle(mask, (0, r), (n, n - r), 255, -1)
    for cx, cy in ((r, r), (n - r, r), (r, n - r), (n - r, n - r)):
        cv2.circle(mask, (cx, cy), r, 255, -1)
    img[mask > 0] = (*BG, 255)

    def px(v):
        return int(round(v * n))

    vonal = max(1, px(LINE_W))
    x0, x1, y0, y1 = px(COURT_X0), px(COURT_X1), px(COURT_Y0), px(COURT_Y1)
    kr = px(COURT_R)

    # A pálya sötét kitöltése (lekerekített téglalap).
    cv2.rectangle(img, (x0 + kr, y0), (x1 - kr, y1), (*COURT_FILL, 255), -1)
    cv2.rectangle(img, (x0, y0 + kr), (x1, y1 - kr), (*COURT_FILL, 255), -1)
    for cx, cy in ((x0 + kr, y0 + kr), (x1 - kr, y0 + kr),
                   (x0 + kr, y1 - kr), (x1 - kr, y1 - kr)):
        cv2.circle(img, (cx, cy), kr, (*COURT_FILL, 255), -1, cv2.LINE_AA)

    # Kapuelőtér-ívek: a két alapvonalról benyúló arany félkörök.
    gr = px(GOAL_R)
    cy = (y0 + y1) // 2
    cv2.ellipse(img, (x0, cy), (gr, gr), 0, -80, 80, (*GOLD, 255),
                vonal, cv2.LINE_AA)
    cv2.ellipse(img, (x1, cy), (gr, gr), 0, 100, 260, (*GOLD, 255),
                vonal, cv2.LINE_AA)

    # A pálya kerete + felezővonal (teal).
    cv2.line(img, (px(0.5), y0), (px(0.5), y1), (*ACCENT, 255), vonal,
             cv2.LINE_AA)
    ker = np.zeros((n, n), np.uint8)
    cv2.rectangle(ker, (x0 + kr, y0), (x1 - kr, y1), 255, -1)
    cv2.rectangle(ker, (x0, y0 + kr), (x1, y1 - kr), 255, -1)
    for cx, cyy in ((x0 + kr, y0 + kr), (x1 - kr, y0 + kr),
                    (x0 + kr, y1 - kr), (x1 - kr, y1 - kr)):
        cv2.circle(ker, (cx, cyy), kr, 255, -1)
    kontur, _ = cv2.findContours(ker, cv2.RETR_EXTERNAL,
                                 cv2.CHAIN_APPROX_NONE)
    cv2.drawContours(img, kontur, -1, (*ACCENT, 255), vonal, cv2.LINE_AA)

    # A labda a jobb félen, mögötte halvány mozgás-ív (a "gépi elemzés"
    # nyoma: a rendszer a labda útját követi).
    bc = (px(BALL_CX), px(BALL_CY))
    for (tx, ty), tr, alfa in (((0.505, 0.560), 0.028, 90),
                               ((0.565, 0.485), 0.038, 150),
                               ((0.615, 0.425), 0.050, 200)):
        cv2.circle(img, (px(tx), px(ty)), px(tr), (*ACCENT, alfa), -1,
                   cv2.LINE_AA)
    cv2.circle(img, bc, px(BALL_R), (*BALL, 255), -1, cv2.LINE_AA)

    # A háttéren KÍVÜLI pixelek átlátszók maradnak (a lekerekített sarok).
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
