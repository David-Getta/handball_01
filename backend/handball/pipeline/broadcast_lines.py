"""Pályavonal-felismerés a közvetítés-képből — az auto-kalibráció alapja.

A tévés úton a kamera-állás vágásról vágásra változik, ezért az egyszeri
kézi sarok-kijelölés nem elég: minden totálkép-szakaszhoz ÚJRA meg kell
találni a pálya geometriáját. Ennek első lépcsője a hosszú, egyenes
VONALAK (oldalvonal, alapvonal, kapuelőtér-ív húrjai) megtalálása a
képen.

A vonal nem mindig fehér: a több sportot kiszolgáló csarnokokban a
padlón egymáson futnak a kosár-, futsal- és röplabda-vonalak, és a
KÉZILABDA-PÁLYÁÉ gyakran PIROS (mellette festett mezők is: sárga
kapuelőtér, színes pályafelület). Ezért a fényesség-alapú maszk mellett
van szín-alapú is (color_line_mask), és az "auto" mód a képből dönti
el, melyik szín vonalait kövesse (detect_court_lines_color).

A mag tiszta numpy (egyszerűsített Hough-transzformáció), így valódi
közvetítés-felvétel nélkül, szintetikus képekkel tesztelhető. A
következő lépcső (külön kör): a talált vonalak megfeleltetése a pálya-
modell vonalainak → homográfia-jelölt.

Folyamat:
1. edge_mask:   világos-és-vékony pixelek maszkja (a fehér festett vonal
                világosabb a padlónál);
2. hough_lines: a maszk pontjaira illesztett domináns egyenesek
                (szög, távolság) csúcs-keresés a Hough-térben;
3. detect_court_lines: a kettő összefűzve, kép-koordinátás vég-
                pontokkal visszaadva.
"""

from __future__ import annotations

# A vonal-pixel a környezeténél legalább ennyivel világosabb (0..255).
LINE_BRIGHTNESS_DELTA = 40
# A Hough-tér felbontása és a csúcs-elfogadás küszöbe.
HOUGH_ANGLE_STEPS = 90
HOUGH_RHO_STEP = 2.0
HOUGH_MIN_VOTES_FRAC = 0.25   # a legerősebb csúcs szavazatainak ekkora része
HOUGH_MAX_LINES = 8
# Két csúcs ennél közelebb (szög fok / rho pixel) ugyanaz a vonal.
HOUGH_MIN_ANGLE_SEP_DEG = 8.0
HOUGH_MIN_RHO_SEP = 20.0


def edge_mask(gray, delta: int = LINE_BRIGHTNESS_DELTA):
    """Világos, vékony vonal-pixelek maszkja (bool tömb).

    A pixel akkor vonal-jelölt, ha a 5 pixelnyire lévő bal-jobb VAGY
    fel-le szomszédainál legalább `delta`-val világosabb — ez a vékony,
    a padlónál fényesebb festett vonal jele (a nagy fényes foltokat, pl.
    reklámtáblát a kétoldali feltétel kiszűri)."""
    import numpy as np

    g = gray.astype(np.int16)
    out = np.zeros(g.shape, dtype=bool)
    d = 5
    core = g[d:-d, d:-d]
    horiz = ((core - g[d:-d, :-2 * d] >= delta)
             & (core - g[d:-d, 2 * d:] >= delta))
    vert = ((core - g[:-2 * d, d:-d] >= delta)
            & (core - g[2 * d:, d:-d] >= delta))
    out[d:-d, d:-d] = horiz | vert
    return out


# A SZÍNES vonalak felismerése (több sportot kiszolgáló csarnokok).
# A kézilabda-pálya vonala sok teremben NEM fehér: a padlón egymáson
# futnak a kosár-, futsal- és röplabda-vonalak, és a kézié gyakran PIROS
# (mellette kék/zöld/sárga vonalak és festett mezők). A szín-maszk azt a
# pixelt tartja meg, ahol a választott szín érdemben erősebb a többinél,
# ÉS a pixel vékony vonalként kiemelkedik a környezetéből — így a nagy
# festett MEZŐK (pl. a sárga kapuelőtér, a zöld pályafelület) nem
# szennyezik a vonal-keresést, csak a szélük.
COLOR_LINE_DOMINANCE = 30   # a szín-csatorna ennyivel erősebb a többinél
COLOR_LINE_DELTA = 18       # ...és a vonal ennyivel üt el a környezetétől

# A támogatott vonalszínek: magyar név → (pozitív csatornák, negatív
# csatornák) az RGB-ből. A pontszám = min(pozitívak) − max(negatívak).
LINE_COLORS = {
    "piros": ((0,), (1, 2)),
    "kek": ((2,), (0, 1)),
    "zold": ((1,), (0, 2)),
    "sarga": ((0, 1), (2,)),
}


def _thin_line_mask(score, delta):
    """Vékony, a környezeténél `delta`-val erősebb pixelek maszkja.

    Ugyanaz a kétoldali teszt, mint a fehér vonalaknál (edge_mask): a
    pixel bal-jobb VAGY fel-le szomszédainál is erősebb — a nagy egybe-
    festett foltok belseje így kiesik, csak a vonalak maradnak."""
    import numpy as np

    g = score.astype(np.int16)
    out = np.zeros(g.shape, dtype=bool)
    d = 5
    if g.shape[0] <= 2 * d or g.shape[1] <= 2 * d:
        return out
    core = g[d:-d, d:-d]
    horiz = ((core - g[d:-d, :-2 * d] >= delta)
             & (core - g[d:-d, 2 * d:] >= delta))
    vert = ((core - g[:-2 * d, d:-d] >= delta)
            & (core - g[2 * d:, d:-d] >= delta))
    out[d:-d, d:-d] = horiz | vert
    return out


def color_line_mask(rgb, color: str = "piros",
                    dominance: int = COLOR_LINE_DOMINANCE,
                    delta: int = COLOR_LINE_DELTA):
    """Adott SZÍNŰ, vékony vonal-pixelek maszkja (bool tömb).

    `rgb`: (magasság, szélesség, 3) tömb R,G,B sorrendben (OpenCV-ből
    BGR jön — meg kell fordítani). `color`: a LINE_COLORS kulcsa.

    Két feltétel együtt: a szín érdemben DOMINÁL a pixelen (a saját
    csatornája legalább `dominance`-szal erősebb a többinél), és a pixel
    vékony vonalként ki is emelkedik a környezetéből (`delta`)."""
    import numpy as np

    if color not in LINE_COLORS:
        raise ValueError(f"ismeretlen vonalszín: {color}")
    pos, neg = LINE_COLORS[color]
    a = np.asarray(rgb).astype(np.int16)
    pos_v = np.min(np.stack([a[:, :, i] for i in pos], axis=0), axis=0)
    neg_v = np.max(np.stack([a[:, :, i] for i in neg], axis=0), axis=0)
    score = pos_v - neg_v
    return _thin_line_mask(score, delta) & (score >= dominance)


# FESTETT MEZŐK SZÉLE. Több csarnokban a kézilabda-pálya legjobban látszó
# eleme nem vonal, hanem FESTETT FELÜLET: tömör sárga (kék, narancs)
# kapuelőtér, színes játékfelület. A szélük a pálya vonala (gólvonal,
# 6 m-es vonal, oldalvonal) — a vékony-vonal-maszk viszont épp ezt dobja
# el (a kétoldali próba csak a vékony vonalat tartja meg). Ez a maszk a
# telített, nagy foltok HATÁRÁT adja: a parketta (kevésbé telített) és a
# vékony festett vonal (a nyitás kiszedi) nem folt.
FIELD_MIN_SAT = 0.55       # a festett felület telítettsége (0..1)
FIELD_MIN_VAL = 80         # ...és világossága (0..255)
FIELD_DOMINANCE = 40       # a szín-csatorna ennyivel erősebb a többinél
# A nyitás sugara a kép rövidebb oldalához mérve: az ennél vékonyabb
# festett vonal nem folt (1080p-n ~4 px sugár → ~9 px-ig kiesik).
FIELD_OPEN_FRAC = 1.0 / 250.0


def _erode(m, r: int):
    """Bináris erózió (2r+1)×(2r+1)-es négyzettel, szétválasztva (sor,
    majd oszlop). A képen kívül IGAZ — a képszélig érő folt széle így nem
    lesz "él" (különben a kép kerete vonalnak látszana)."""
    import numpy as np

    out = m.copy()
    for d in range(1, r + 1):
        out[:, d:] &= m[:, :-d]
        out[:, :-d] &= m[:, d:]
    sor = out.copy()
    for d in range(1, r + 1):
        out[d:, :] &= sor[:-d, :]
        out[:-d, :] &= sor[d:, :]
    return np.asarray(out, dtype=bool)


def _dilate(m, r: int):
    """Bináris tágítás (2r+1)×(2r+1)-es négyzettel, szétválasztva."""
    import numpy as np

    out = m.copy()
    for d in range(1, r + 1):
        out[:, d:] |= m[:, :-d]
        out[:, :-d] |= m[:, d:]
    sor = out.copy()
    for d in range(1, r + 1):
        out[d:, :] |= sor[:-d, :]
        out[:-d, :] |= sor[d:, :]
    return np.asarray(out, dtype=bool)


def field_edge_mask(rgb):
    """A FESTETT mezők (kapuelőtér, színes játékfelület) határának maszkja.

    Színenként (LINE_COLORS) a telített, domináns színű pixelek foltja;
    a morfológiai nyitás kiszedi a vékony festett vonalakat; a határ a
    folt 1 px-es tágítása és szűkítése közti sáv. A két szomszédos
    festett mező (sárga kapuelőtér a zöld felületen) határa mindkét
    színnél él."""
    import numpy as np

    a = np.asarray(rgb).astype(np.int16)
    mx = a.max(axis=2)
    mn = a.min(axis=2)
    telitett = ((mx - mn) >= FIELD_MIN_SAT * np.maximum(mx, 1)) \
        & (mx >= FIELD_MIN_VAL)
    r = max(2, int(round(min(a.shape[:2]) * FIELD_OPEN_FRAC)))
    out = np.zeros(a.shape[:2], dtype=bool)
    for pos, neg in LINE_COLORS.values():
        pos_v = np.min(np.stack([a[:, :, i] for i in pos], axis=0), axis=0)
        neg_v = np.max(np.stack([a[:, :, i] for i in neg], axis=0), axis=0)
        folt = telitett & ((pos_v - neg_v) >= FIELD_DOMINANCE)
        if not folt.any():
            continue
        folt = _dilate(_erode(folt, r), r)          # nyitás
        out |= _dilate(folt, 1) & ~_erode(folt, 1)  # a határ
    return out


def hough_lines(mask, max_lines: int = HOUGH_MAX_LINES):
    """Domináns egyenesek a maszk pontjaiból: [(theta_deg, rho, votes)].

    Egyszerűsített Hough: theta a vonal NORMÁLISÁNAK szöge (0..180 fok),
    rho = x*cos(theta) + y*sin(theta). A csúcsokat szavazat szerint
    csökkenő sorrendben adjuk, a közeli (azonos vonalhoz tartozó)
    csúcsokat elnyomva."""
    import numpy as np

    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return []
    thetas = np.deg2rad(np.linspace(0.0, 180.0, HOUGH_ANGLE_STEPS,
                                    endpoint=False))
    diag = float(np.hypot(mask.shape[0], mask.shape[1]))
    n_rho = int(2 * diag / HOUGH_RHO_STEP) + 1
    acc = np.zeros((HOUGH_ANGLE_STEPS, n_rho), dtype=np.int32)
    cos_t, sin_t = np.cos(thetas), np.sin(thetas)
    # rho minden pont-szög párra; eltolva, hogy az index nemnegatív legyen.
    rho = np.outer(xs, cos_t) + np.outer(ys, sin_t)      # (n_pont, n_szog)
    idx = ((rho + diag) / HOUGH_RHO_STEP).astype(np.int32)
    for a in range(HOUGH_ANGLE_STEPS):
        binc = np.bincount(idx[:, a], minlength=n_rho)
        acc[a, :len(binc)] += binc.astype(np.int32)

    peaks = []
    best = int(acc.max())
    if best == 0:
        return []
    min_votes = max(10, int(best * HOUGH_MIN_VOTES_FRAC))
    flat = np.argsort(acc, axis=None)[::-1]
    angle_step_deg = 180.0 / HOUGH_ANGLE_STEPS
    for f in flat:
        a, r = divmod(int(f), n_rho)
        votes = int(acc[a, r])
        if votes < min_votes or len(peaks) >= max_lines:
            break
        theta_deg = a * angle_step_deg
        rho_val = r * HOUGH_RHO_STEP - diag
        # Kanonizálás (-90..90] fokra: a (178°, -rho) ugyanaz a vonal,
        # mint a (-2°, rho) — egy alakban tartjuk.
        if theta_deg > 90.0:
            theta_deg -= 180.0
            rho_val = -rho_val
        # Közeli csúcs elnyomása (a szög ±90 foknál is átfordulhat).
        dup = False
        for (pt, pr, _) in peaks:
            d_ang = min(abs(pt - theta_deg), 180.0 - abs(pt - theta_deg))
            same_rho = (abs(pr - rho_val) < HOUGH_MIN_RHO_SEP
                        or abs(pr + rho_val) < HOUGH_MIN_RHO_SEP)
            if d_ang < HOUGH_MIN_ANGLE_SEP_DEG and same_rho:
                dup = True
                break
        if not dup:
            peaks.append((theta_deg, rho_val, votes))
    return peaks


def detect_court_lines(gray, max_lines: int = HOUGH_MAX_LINES,
                       mask=None) -> list[dict]:
    """Pályavonal-jelöltek egy szürke képből (vagy kész maszkból).

    `mask`: ha meg van adva, azt használjuk a fehér-vonal maszk helyett
    — így ugyanez a Hough-lépcső dolgozik a SZÍNES vonalakon is (lásd
    color_line_mask / detect_court_lines_color). A `gray` ilyenkor is
    kell: belőle jön a kép mérete.

    Visszatérés: [{"theta_deg", "rho", "votes", "p1", "p2"}] — a p1/p2 a
    vonal két, képen belüli végpontja (megjelenítéshez / a következő
    lépcső megfeleltetéséhez)."""
    import numpy as np

    if mask is None:
        mask = edge_mask(gray)
    h, w = gray.shape[:2]
    out = []
    for (theta_deg, rho, votes) in hough_lines(mask, max_lines):
        t = np.deg2rad(theta_deg)
        ct, st = float(np.cos(t)), float(np.sin(t))
        pts = []
        # Metszés a kép négy szélével; a képen belüli kettőt tartjuk meg.
        if abs(st) > 1e-6:
            for x_edge in (0.0, float(w - 1)):
                y = (rho - x_edge * ct) / st
                if 0.0 <= y <= h - 1:
                    pts.append((round(x_edge, 1), round(y, 1)))
        if abs(ct) > 1e-6:
            for y_edge in (0.0, float(h - 1)):
                x = (rho - y_edge * st) / ct
                if 0.0 <= x <= w - 1:
                    pts.append((round(x, 1), round(y_edge, 1)))
        # Duplikált sarok-metszések kiszűrése.
        uniq = []
        for p in pts:
            if all(abs(p[0] - q[0]) + abs(p[1] - q[1]) > 1.0 for q in uniq):
                uniq.append(p)
        if len(uniq) < 2:
            continue
        out.append({"theta_deg": round(theta_deg, 1), "rho": round(rho, 1),
                    "votes": votes, "p1": uniq[0], "p2": uniq[1]})
    return out


# A szín-választáshoz: a nyertes szín-maszknak ennyivel több vonal-pixelt
# kell adnia, mint a fehérnek — különben maradunk a fehérnél (a legtöbb
# csarnokban az a jó, és a kevés szín-pixel könnyen zaj).
COLOR_WIN_RATIO = 1.3


def detect_court_lines_color(rgb, color: str = "auto",
                             max_lines: int = HOUGH_MAX_LINES) -> dict:
    """Pályavonal-jelöltek SZÍNES vonalakhoz — több sportot kiszolgáló
    csarnokokhoz.

    A kézilabda-pálya vonala sok teremben nem fehér (a felhasználó
    felvételén PIROS), és mellette más sportok kék/zöld/sárga vonalai
    futnak. A `color`:
      - "feher": a régi, fényesség-alapú maszk,
      - "piros"/"kek"/"zold"/"sarga": az adott szín vonalai,
      - "mezo": a festett mezők (kapuelőtér, színes felület) széle
        (field_edge_mask),
      - "auto": mindet kipróbáljuk, és a LEGTÖBB vonal-pixelt adó
        maszk nyer — a fehér csak akkor veszít, ha egy szín érdemben
        (COLOR_WIN_RATIO-szor) több pixelt hoz. (A négyszög-javaslat
        ennél tovább próbálkozik: detect_court_quad.)

    `rgb`: (magasság, szélesség, 3) R,G,B tömb.

    Visszatérés: {"color", "lines", "pixels": {szín: pixel-szám}} — a
    "color" a ténylegesen használt vonalszín (a kliens ezt kiírhatja,
    hogy a felhasználó lássa, mit követ a rendszer).
    """
    import numpy as np

    a = np.asarray(rgb)
    gray = a.mean(axis=2).astype(np.uint8)
    masks = {"feher": edge_mask(gray)}
    for name in LINE_COLORS:
        masks[name] = color_line_mask(a, name)
    pixels = {k: int(m.sum()) for k, m in masks.items()}

    if color == "auto":
        chosen = _auto_color(pixels)
    elif color == FIELD_EDGE_COLOR:
        # A festett mezők széle (field_edge_mask) — csak kérésre (vagy
        # a detect_court_quad tartalék-sorában), az "auto" nem választja.
        masks[color] = field_edge_mask(a)
        pixels[color] = int(masks[color].sum())
        chosen = color
    else:
        if color not in masks:
            raise ValueError(f"ismeretlen vonalszín: {color}")
        chosen = color

    lines = detect_court_lines(gray, max_lines, mask=masks[chosen])
    return {"color": chosen, "lines": lines, "pixels": pixels}


# A festett mezők szélének "színe" a vonalszín-választásban.
FIELD_EDGE_COLOR = "mezo"
# A tartalék-sorba csak az a szín kerül, amelyik legalább ennyi
# vonal-pixelt ad a kép területéhez képest (a pár pixeles zaj nem pálya).
COLOR_MIN_PIXEL_FRAC = 0.0005


def _auto_color(pixels: dict) -> str:
    """Az "auto" mód első választása: a legtöbb vonal-pixelt adó szín, ha
    COLOR_WIN_RATIO-szor többet hoz a fehérnél — különben a fehér."""
    best_color = max(LINE_COLORS, key=lambda c: pixels[c])
    return (best_color
            if pixels[best_color] >= COLOR_WIN_RATIO * max(1, pixels["feher"])
            else "feher")


def detect_court_quad(rgb, color: str = "auto",
                      max_lines: int = HOUGH_MAX_LINES) -> dict:
    """Vonalak + sarok-jelöltek + kalibrációs négyszög-javaslat egy képből.

    Konkrét `color`-nál az adott szín vonalaiból. "auto"-nál a több sportot
    kiszolgáló csarnok miatt NEM egyetlen tippből: a legtöbb pixel nem
    jelenti a kézilabda-pályát (a kosár- és röplabda-vonalak együtt
    gyakran többen vannak). Sorban próbálja: az első választás
    (_auto_color), aztán a többi szín a vonal-pixelek száma szerint
    csökkenő sorrendben (a zaj-szintűek kimaradnak), végül a festett
    mezők széle — és az ELSŐ, amelyikből négyszög áll össze, nyer. Ha
    egyikből sem, az első választás vonalait adja (a kliens kirajzolja,
    mit látott a gép).

    Visszatérés: {"color", "lines", "pixels", "corners",
    "suggested_quad", "tried": [kipróbált színek]}."""
    import numpy as np

    a = np.asarray(rgb)
    h, w = a.shape[:2]

    def _egy(szin: str) -> dict:
        found = detect_court_lines_color(a, szin, max_lines)
        corners = line_intersections(found["lines"], w, h)
        found["corners"] = corners
        found["suggested_quad"] = suggest_calibration_quad(corners, w, h)
        return found

    if color != "auto":
        r = _egy(color)
        r["tried"] = [r["color"]]
        return r
    elso = _egy("auto")
    probalt = [elso["color"]]
    if elso["suggested_quad"]:
        elso["tried"] = probalt
        return elso
    pixels = elso["pixels"]
    minimum = COLOR_MIN_PIXEL_FRAC * w * h
    sor = sorted((c for c in ["feher", *LINE_COLORS]
                  if c != elso["color"] and pixels.get(c, 0) >= minimum),
                 key=lambda c: (-pixels[c], c))
    for szin in [*sor, FIELD_EDGE_COLOR]:
        r = _egy(szin)
        probalt.append(szin)
        if r["suggested_quad"]:
            r["tried"] = probalt
            return r
    elso["tried"] = probalt
    return elso


# Metszéspont-számításnál ennél párhuzamosabb vonalpárt nem metszünk.
MIN_INTERSECT_ANGLE_DEG = 25.0


def line_intersections(lines: list[dict], width: int,
                       height: int) -> list[dict]:
    """Sarok-jelöltek: a nem-párhuzamos vonalpárok képen belüli
    metszéspontjai.

    A jövőbeli pálya-modell megfeleltetés (homográfia) sarokpontokat
    keres — az oldalvonal x alapvonal metszés a pálya sarka. A közel
    párhuzamos párokat (MIN_INTERSECT_ANGLE_DEG alatt) kihagyjuk, mert
    a metszéspontjuk numerikusan instabil.

    Visszatérés: [{"x", "y", "lines": (i, j)}] — az i/j a bemeneti lista
    indexei."""
    import numpy as np

    out = []
    for i in range(len(lines)):
        for j in range(i + 1, len(lines)):
            t1, r1 = lines[i]["theta_deg"], lines[i]["rho"]
            t2, r2 = lines[j]["theta_deg"], lines[j]["rho"]
            d_ang = abs(t1 - t2)
            d_ang = min(d_ang, 180.0 - d_ang)
            if d_ang < MIN_INTERSECT_ANGLE_DEG:
                continue
            a1, a2 = np.deg2rad(t1), np.deg2rad(t2)
            A = np.array([[np.cos(a1), np.sin(a1)],
                          [np.cos(a2), np.sin(a2)]])
            b = np.array([r1, r2])
            try:
                x, y = np.linalg.solve(A, b)
            except np.linalg.LinAlgError:
                continue
            if 0.0 <= x <= width - 1 and 0.0 <= y <= height - 1:
                out.append({"x": round(float(x), 1),
                            "y": round(float(y), 1), "lines": (i, j)})
    return out


# A javasolt kalibrációs négyszög minimális területe a képhez képest.
QUAD_MIN_AREA_FRAC = 0.15


def suggest_calibration_quad(corners: list[dict], width: int,
                             height: int) -> list[tuple] | None:
    """Kalibrációs négyszög-javaslat a sarok-jelöltekből.

    A meglévő (kézi) kalibráció 4 sarokpontot vár — ez a függvény a
    felismert sarok-jelöltekből választja ki a legnagyobb területű,
    KONVEX négyszöget, és a kézi folyamat sorrendjében adja vissza
    (bal-felső, jobb-felső, jobb-alsó, bal-alsó). A kliens ezt
    előtöltheti a kalibrációs képernyőre: az edző csak igazít rajta,
    nem nulláról jelöl.

    None, ha nincs 4 jelölt, vagy a legjobb négyszög is túl kicsi
    (QUAD_MIN_AREA_FRAC alatt) — ilyenkor marad a kézi kijelölés.
    """
    from itertools import combinations

    if len(corners) < 4:
        return None

    def order_quad(pts):
        # Óramutató szerint a súlypont körül, bal-felsőtől indítva.
        import math
        cx = sum(p[0] for p in pts) / 4.0
        cy = sum(p[1] for p in pts) / 4.0
        ordered = sorted(pts, key=lambda p: math.atan2(p[1] - cy,
                                                       p[0] - cx))
        # Kezdés a bal-felsőhöz legközelebbi ponttól.
        start = min(range(4), key=lambda i: ordered[i][0] + ordered[i][1])
        return ordered[start:] + ordered[:start]

    def shoelace(pts):
        area = 0.0
        for i in range(4):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % 4]
            area += x1 * y2 - x2 * y1
        return abs(area) / 2.0

    def convex(pts):
        # Az egymást követő élek keresztszorzatai azonos előjelűek.
        signs = []
        for i in range(4):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % 4]
            x3, y3 = pts[(i + 2) % 4]
            cross = (x2 - x1) * (y3 - y2) - (y2 - y1) * (x3 - x2)
            if abs(cross) > 1e-9:
                signs.append(cross > 0)
        return len(set(signs)) <= 1 and bool(signs)

    pts_all = [(c["x"], c["y"]) for c in corners]
    best = None
    best_area = 0.0
    for combo in combinations(pts_all, 4):
        quad = order_quad(list(combo))
        if not convex(quad):
            continue
        area = shoelace(quad)
        if area > best_area:
            best_area = area
            best = quad
    if best is None or best_area < QUAD_MIN_AREA_FRAC * width * height:
        return None
    return [(round(x, 1), round(y, 1)) for (x, y) in best]
