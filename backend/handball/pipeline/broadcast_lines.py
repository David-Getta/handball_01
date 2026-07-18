"""Pályavonal-felismerés a közvetítés-képből — az auto-kalibráció alapja.

A tévés úton a kamera-állás vágásról vágásra változik, ezért az egyszeri
kézi sarok-kijelölés nem elég: minden totálkép-szakaszhoz ÚJRA meg kell
találni a pálya geometriáját. Ennek első lépcsője a hosszú, egyenes
FEHÉR VONALAK (oldalvonal, alapvonal, kapuelőtér-ív húrjai) megtalálása
a képen.

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


def detect_court_lines(gray, max_lines: int = HOUGH_MAX_LINES) -> list[dict]:
    """Pályavonal-jelöltek egy szürke képből.

    Visszatérés: [{"theta_deg", "rho", "votes", "p1", "p2"}] — a p1/p2 a
    vonal két, képen belüli végpontja (megjelenítéshez / a következő
    lépcső megfeleltetéséhez)."""
    import numpy as np

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
