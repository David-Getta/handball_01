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
