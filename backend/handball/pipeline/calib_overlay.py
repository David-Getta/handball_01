"""
[Kalibráció-ellenőrzés] — a pályavonalak visszarajzolása a videó kockáira.

A felhasználó a pontosságot nem a számokból, hanem a SZEMÉVEL ítéli meg:
ha a felülnézetre vetített játékosok "odébb vannak", nem tudja, a
kalibráció rossz-e, vagy a kamera-mozgás követése csúszott el. Ez a modul
a fordított irányt adja: a pálya ismert vonalait (alapvonalak, felező,
6 m-es kapuelőterek, kapuk) visszavetíti a videó EGY ADOTT kockájára —
ha a rajzolt vonal a valódira ül, a helyek hihetők; ahol elcsúszik, ott
a kalibráció vagy a pásztázás-követés a hibás.

Ehhez két dolog kell a meccs mellől (MatchMeta):
- `court_homography`: az alap-kocka pixel → pálya méter leképezés (H0),
- `pan_keyframes`: a kamera-mozgás ritkított sora [[t, G], …], ahol G az
  adott kocka pixeleit az alap-kocka koordinátáiba viszi.

A pálya-pont → pixel út: pixel = G⁻¹ · H0⁻¹ · pálya. Tiszta függvények,
videó nélkül tesztelhetők; a rajzolás cv2-vel, a hívó adja a képet.
"""

from __future__ import annotations

import math
from typing import Optional

from ._homography import apply_homography, invert_3x3
from .calibration import COURT_LENGTH_M, COURT_WIDTH_M

# Ennyi másodpercenként teszünk el egy kamera-mátrixot a meccs mellé.
# IDŐTARTAM, tehát másodpercben: a kocka-lépést a meccs saját (ritkított)
# képrátájából számoljuk. Két másodperc alatt a svenk nem megy messzire;
# egy 60 perces meccs ~1800 mátrix, kb. 100 KB — elfér a mentésben.
PAN_KEYFRAME_S = 2.0
# A kapuelőtér ívének felbontása (fokban) a rajzoláshoz.
ARC_STEP_DEG = 6


def sample_pan_keyframes(pan_list: list, fps: float) -> list:
    """A kockánkénti G-mátrixokból ritkított sor: [[t, G], …].

    `pan_list[i]` az i-edik feldolgozott kocka mátrixa (3x3 lista) vagy
    None; a kocka t címkéje maga az i index (a feldolgozó így számoz).
    Az első kocka mindig benne van (t=0, egység), utána PAN_KEYFRAME_S
    lépésenként; a None-okat átugorjuk.
    """
    if not pan_list:
        return []
    lepes = max(1, int(round(PAN_KEYFRAME_S * (fps if fps > 0 else 25.0))))
    ki = []
    for i in range(0, len(pan_list), lepes):
        g = pan_list[i]
        if g is None:
            continue
        ki.append([i, [[float(v) for v in sor] for sor in g]])
    return ki


def keyframe_at(pan_keyframes: Optional[list], t: int) -> list:
    """A t kockához tartozó G: az utolsó kulcs-kocka, amelynek t-je ≤ t
    (a két kulcs között a kamera nem megy messzire). Ha nincs, egység."""
    egyseg = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
    if not pan_keyframes:
        return egyseg
    talalt = egyseg
    for tk, g in pan_keyframes:
        if tk <= t:
            talalt = g
        else:
            break
    return talalt


def court_polylines() -> list:
    """A pálya vonalai méterben: alapvonal-téglalap, felező, két
    kapuelőtér (6 m — negyedkör + egyenes + negyedkör), két kapu."""
    H, W = COURT_LENGTH_M, COURT_WIDTH_M
    vonalak = [
        [(0.0, 0.0), (H, 0.0), (H, W), (0.0, W), (0.0, 0.0)],
        [(H / 2, 0.0), (H / 2, W)],
    ]
    also, felso = W / 2 - 1.5, W / 2 + 1.5
    for bal in (True, False):
        cx = 0.0 if bal else H
        elojel = 1.0 if bal else -1.0
        ut = []
        for a in range(-90, 1, ARC_STEP_DEG):
            rad = math.radians(a)
            ut.append((cx + elojel * math.cos(rad) * 6.0,
                       also + math.sin(rad) * 6.0))
        for a in range(0, 91, ARC_STEP_DEG):
            rad = math.radians(a)
            ut.append((cx + elojel * math.cos(rad) * 6.0,
                       felso + math.sin(rad) * 6.0))
        vonalak.append(ut)
        vonalak.append([(cx, also), (cx, felso)])  # kapu a gólvonalon
    return vonalak


def overlay_pixels(court_homography: list, g_at_t: Optional[list] = None,
                   width: Optional[int] = None,
                   height: Optional[int] = None) -> list:
    """A pálya vonalai PIXELBEN az adott kockán: G⁻¹ · H0⁻¹ · pálya.

    A kép mögé (a homográfia horizontja mögé) eső pontokat — ahol a
    nevező előjelet vált — kihagyjuk, hogy ne húzzon vonalat a kép
    túloldalára; a kép méretét ismerve a messze kívül eső pontokat is.
    Visszatérés: [[(px, py), …], …] — polyline-onként.
    """
    h_inv = invert_3x3(court_homography)
    g_inv = invert_3x3(g_at_t) if g_at_t is not None else None
    ki = []
    for vonal in court_polylines():
        pontok = []
        for (x, y) in vonal:
            # Alap-kocka pixel; a horizont mögötti pontot a nevező jelzi.
            w = h_inv[2][0] * x + h_inv[2][1] * y + h_inv[2][2]
            if w <= 1e-9:
                if len(pontok) >= 2:
                    ki.append(pontok)
                pontok = []
                continue
            bx, by = apply_homography(h_inv, x, y)
            if g_inv is not None:
                bx, by = apply_homography(g_inv, bx, by)
            if width and height and (bx < -width or bx > 2 * width
                                     or by < -height or by > 2 * height):
                if len(pontok) >= 2:
                    ki.append(pontok)
                pontok = []
                continue
            pontok.append((bx, by))
        if len(pontok) >= 2:
            ki.append(pontok)
    return ki


def draw_overlay(img, polylines: list, color=(60, 220, 255),
                 thickness: int = 2):
    """A pixel-polyline-ok rárajzolása a képre (helyben) — cv2."""
    import cv2
    import numpy as np
    for vonal in polylines:
        pts = np.array([[int(round(x)), int(round(y))] for x, y in vonal],
                       dtype=np.int32).reshape(-1, 1, 2)
        cv2.polylines(img, [pts], False, color, thickness, cv2.LINE_AA)
    return img


def camera_path_summary(pan_keyframes: Optional[list]) -> Optional[dict]:
    """A kamera útjának összegzése a diagnosztikához (px, az alap-kockához
    képest): hány kulcs-kocka, mekkora a legnagyobb és a záró eltolás.
    None, ha nincs kulcs-kocka (régi mentés, kalibráció nélkül)."""
    if not pan_keyframes:
        return None
    legnagyobb = 0.0
    zaro = 0.0
    for _t, g in pan_keyframes:
        try:
            tx, ty = float(g[0][2]), float(g[1][2])
        except (TypeError, IndexError):
            continue
        zaro = math.hypot(tx, ty)
        legnagyobb = max(legnagyobb, zaro)
    return {"keyframes": len(pan_keyframes),
            "max_shift_px": round(legnagyobb, 1),
            "final_shift_px": round(zaro, 1)}


# Vonal-illeszkedés: ennyi px-es sávban keressük az élt a rajzolt vonal
# körül (a kalibráció és a JPEG-tömörítés miatt a vonal nem hajszálpontos),
# és ennyi px-enként veszünk mintát a vonal mentén.
FIT_BAND_PX = 3
FIT_STEP_PX = 2.0


def edge_map(gray):
    """A kép él-térképe az illeszkedés-méréshez: Sobel-nagyság 0..1-re
    normálva (a 99,5 percentilis = 1), FIT_BAND_PX sávra kitágítva —
    egy kockára EGYSZER számoljuk, sok jelölt-vonalra újrahasználható.
    Visszatérés: (sav, alapszint)."""
    import cv2
    import numpy as np
    g = gray.astype(np.float32)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    mag = cv2.magnitude(gx, gy)
    csucs = float(np.percentile(mag, 99.5)) or 1.0
    mag = np.clip(mag / csucs, 0.0, 1.0)
    k = 2 * FIT_BAND_PX + 1
    sav = cv2.dilate(mag, np.ones((k, k), np.uint8))
    return sav, float(sav.mean())


def sample_points(polylines: list):
    """A vonalak menti mintapontok (Nx2 float32, px) — EGYSZER számoljuk,
    az eltolás-rács csak eltolja őket (numpy, nem Python-ciklus: egy
    4K-s kockán ~7000 pont, a finomítás ~130 jelöltet próbál)."""
    import numpy as np
    xs, ys = [], []
    for vonal in polylines:
        for (x1, y1), (x2, y2) in zip(vonal, vonal[1:]):
            hossz = math.hypot(x2 - x1, y2 - y1)
            n = max(1, int(hossz / FIT_STEP_PX))
            a = np.linspace(0.0, 1.0, n + 1)
            xs.append(x1 + (x2 - x1) * a)
            ys.append(y1 + (y2 - y1) * a)
    if not xs:
        return np.zeros((0, 2), np.float32)
    return np.stack([np.concatenate(xs), np.concatenate(ys)],
                    axis=1).astype(np.float32)


def fit_on_points(sav, alap: float, pts, dx: float = 0.0,
                  dy: float = 0.0) -> dict:
    """Illeszkedés a kész él-térképen a (dx, dy)-vel eltolt mintapontokra
    (lásd line_fit_score)."""
    import numpy as np
    h, w = sav.shape[:2]
    if len(pts) == 0:
        return {"fit": None, "on_line": None, "baseline": round(alap, 3),
                "samples": 0}
    xi = np.rint(pts[:, 0] + dx).astype(np.int64)
    yi = np.rint(pts[:, 1] + dy).astype(np.int64)
    bent = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
    n = int(bent.sum())
    if n < 20:
        return {"fit": None, "on_line": None, "baseline": round(alap, 3),
                "samples": n}
    vonalon = float(sav[yi[bent], xi[bent]].mean())
    fit = (vonalon - alap) / (1.0 - alap) if alap < 1.0 else 0.0
    return {"fit": round(max(0.0, min(1.0, fit)), 3),
            "on_line": round(vonalon, 3), "baseline": round(alap, 3),
            "samples": n}


def fit_on_edge_map(sav, alap: float, polylines: list) -> dict:
    """Illeszkedés egy kész él-térképen (lásd line_fit_score)."""
    return fit_on_points(sav, alap, sample_points(polylines))



def line_fit_score(gray, polylines: list) -> dict:
    """MENNYIRE ÜL a rajzolt vonal a kép valódi vonalain — 0..1.

    A kép él-erősségét (Sobel-nagyság, 0..1) a rajzolt vonalak mentén
    mintavételezzük (FIT_BAND_PX sávban a legerősebb élt véve), és a kép
    egészének él-alapszintjéhez mérjük: fit = (vonalon − alapszint) /
    (1 − alapszint). Egy jól ülő vonal alatt él van, a mellécsúszott
    alatt csak a padló — a különbség számszerű. Kevés mintánál (a vonalak
    a képen kívül) fit=None.

    Visszatérés: {"fit", "on_line", "baseline", "samples"}.
    """
    sav, alap = edge_map(gray)
    return fit_on_edge_map(sav, alap, polylines)



def fit_summary(points: list) -> Optional[dict]:
    """A feldolgozás alatt mért illeszkedés-pontok [(t, fit|None), …]
    összegzése a meta-ba: {"mean_fit", "min_fit", "worst_t", "points"} —
    a minőség-jelentés a leggyengébb kockából ítél. None, ha nincs
    mérhető pont."""
    ertekes = [(int(t), float(f)) for t, f in points if f is not None]
    if not ertekes:
        return None
    rossz_t, rossz = min(ertekes, key=lambda p: p[1])
    return {"mean_fit": round(sum(f for _, f in ertekes) / len(ertekes), 3),
            "min_fit": round(rossz, 3), "worst_t": rossz_t,
            "points": [[t, round(f, 3)] for t, f in ertekes]}


# ÖNKORREKCIÓ a pályavonalak alapján: ha egy kulcs-kockán az illeszkedés
# ez alá esik, a motor ±REFINE_MAX_PX-es eltolás-rácson megkeresi, hol
# ülne a legjobban a rajz (durva, majd finom lépés), és ha legalább
# FIT_REFINE_GAIN-nyit javul, ráigazítja a kamera-mátrixot. A pálya
# saját vonalai a legmegbízhatóbb "távpontok": nem mozognak, és
# pontosan tudjuk, hol kell lenniük.
FIT_REFINE_BELOW = 0.35
FIT_REFINE_GAIN = 0.15
REFINE_MAX_PX = 24
REFINE_COARSE_PX = 8
REFINE_FINE_PX = 2


def _eltolt(polylines: list, dx: float, dy: float) -> list:
    return [[(x + dx, y + dy) for x, y in vonal] for vonal in polylines]


def refine_shift(sav, alap: float, court_homography: list,
                 g_at_t: Optional[list], width: int, height: int) -> dict:
    """A rajzolt vonalak legjobb ELTOLÁSA a kép élein (px, a kockán).

    Durva rács (REFINE_COARSE_PX) a ±REFINE_MAX_PX tartományon, majd
    finom rács (REFINE_FINE_PX) a legjobb körül. Visszatérés: {"dx", "dy",
    "fit", "fit0"} — fit0 az eltolás nélküli illeszkedés; dx=dy=0, ha
    semmi sem jobb. A hívó G' = G · T(−dx, −dy)-vel igazít (a kockán
    +dx-szel odébb rajzolt vonal = a kocka pixeleit −dx-szel toljuk az
    alap-kocka felé).
    """
    pts = sample_points(
        overlay_pixels(court_homography, g_at_t, width, height))
    fit0 = fit_on_points(sav, alap, pts).get("fit")
    if fit0 is None:
        return {"dx": 0.0, "dy": 0.0, "fit": None, "fit0": None}
    legjobb = (fit0, 0.0, 0.0)

    def _probal(dx, dy):
        nonlocal legjobb
        f = fit_on_points(sav, alap, pts, dx, dy).get("fit")
        if f is not None and f > legjobb[0]:
            legjobb = (f, dx, dy)

    r = REFINE_MAX_PX
    for dx in range(-r, r + 1, REFINE_COARSE_PX):
        for dy in range(-r, r + 1, REFINE_COARSE_PX):
            if dx or dy:
                _probal(float(dx), float(dy))
    # FINOM lépés: a kitágított sávon egy 3-4 px-es plató minden pontja
    # "tökéletes" — a valódi vonalhoz ÉLESEBB térképen (a sáv
    # visszaszűkítve, ±1 px) keressük a plató közepét.
    import cv2
    import numpy as np
    k = 2 * FIT_BAND_PX - 1
    eles = cv2.erode(sav, np.ones((k, k), np.uint8))
    eles_alap = float(eles.mean())
    _f, cx, cy = legjobb
    legjobb = (fit_on_points(eles, eles_alap, pts, cx, cy).get("fit") or 0.0,
               cx, cy)

    def _probal_eles(dx, dy):
        nonlocal legjobb
        f = fit_on_points(eles, eles_alap, pts, dx, dy).get("fit")
        if f is not None and f > legjobb[0]:
            legjobb = (f, dx, dy)

    for dx in range(-REFINE_COARSE_PX, REFINE_COARSE_PX + 1, REFINE_FINE_PX):
        for dy in range(-REFINE_COARSE_PX, REFINE_COARSE_PX + 1,
                        REFINE_FINE_PX):
            if dx or dy:
                _probal_eles(cx + dx, cy + dy)
    # A visszaadott fit a kitágított sávon mért (a hívó küszöbei ahhoz
    # vannak kalibrálva); az eltolás az éles térképen talált.
    _fe, fx, fy = legjobb
    legjobb = (fit_on_points(sav, alap, pts, fx, fy).get("fit") or 0.0, fx, fy)
    f, dx, dy = legjobb
    return {"dx": dx, "dy": dy, "fit": round(f, 3), "fit0": fit0}


def shifted_g(g_at_t: Optional[list], dx: float, dy: float) -> list:
    """G' = G · T(−dx, −dy): a kockán (dx, dy)-vel odébb ülő vonalhoz
    tartozó javított kamera-mátrix (G: aktuális → alap)."""
    g = g_at_t if g_at_t is not None else [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0],
                                           [0.0, 0.0, 1.0]]
    t = [[1.0, 0.0, -dx], [0.0, 1.0, -dy], [0.0, 0.0, 1.0]]
    return [[sum(g[i][k] * t[k][j] for k in range(3)) for j in range(3)]
            for i in range(3)]
