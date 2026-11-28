"""Kapus-szempontú lövés-profil a testpont-sorozatból.

A kapus azt nézi: melyik kézzel lő, hol a lövőkar az elengedéskor (fent /
oldalt / lent), felugrik-e, merre fordul a teste. Ebből ítéli meg, hova
tud a lövő reálisan lőni. Ez a modul ezeket méri — CÍMKE NÉLKÜL, a
testpontokból. A hova-ment-a-lövés tanításához (következő lépés) ezek
lesznek a bemenet.

Ellenőrizhetőség: a felugrás-ítélet összevethető az adathalmaz címkéjével
(jump-shot = felugrásos, shot = helyből) — ezt a `train` meg is méri. A
kartartásra nincs címke; azt egy kis kézi mintán kell ellenőrizni.

Korlát: a "kamerához képest" szavak szó szerint értendők. A pálya-
koordinátás irányhoz (kapu felé fordulás) kamera-kalibráció kell.
"""

from __future__ import annotations

import numpy as np

from .features import L_HIP, L_SH, L_WR, NOSE, R_HIP, R_SH, R_WR, normalize

# Kartartás az elengedéskor: a csukló magassága a vállhoz képest, törzshosszban.
# Ennél magasabban → "fent" (a fej vonalában vagy fölötte).
ARM_HIGH_MIN = 0.35
# Ennél mélyebben → "lent" (csípő felé); a kettő között → "oldalt".
ARM_LOW_MAX = -0.25
# Felugrás: a csípő ennyi törzshossznyit emelkedik az elengedés körüli
# alapvonal fölé (a futás okozta mélységi elmozdulást a lineáris alapvonal
# kiszűri).
JUMP_MIN_RISE = 0.20
# Az elengedés körüli ablak (másodperc) a felugrás-méréshez — IDŐTARTAM,
# ezért másodpercben, nem kockában (a jelenetek 30 és 48 fps-esek).
JUMP_WINDOW_S = 0.6
# Az alapvonal két végének hossza (másodperc).
JUMP_EDGE_S = 0.12
# Kevés mintánál nincs ítélet (None), nem hallgatólagos alapérték.
MIN_FRAMES = 8
MIN_VALID_FRAC = 0.5


def _smooth(x: np.ndarray) -> np.ndarray:
    if len(x) < 3:
        return x
    return np.convolve(np.pad(x, 1, mode="edge"), np.ones(3) / 3, mode="valid")


def jump_rise(center_up: np.ndarray, release: int, fps: float) -> float:
    """A csípő legnagyobb emelkedése a lineáris alapvonal fölé az elengedés körül."""
    half = max(2, int(round(JUMP_WINDOW_S * fps)))
    edge = max(1, int(round(JUMP_EDGE_S * fps)))
    a = max(0, release - half)
    b = min(len(center_up), release + half + 1)
    seg = center_up[a:b]
    if len(seg) < 2 * edge + 1:
        return 0.0
    y0, y1 = seg[:edge].mean(), seg[-edge:].mean()
    base = np.linspace(y0, y1, len(seg))
    return float(np.max(seg - base))


def shot_profile(kps: np.ndarray, boxes: np.ndarray | None, fps: float) -> dict | None:
    """Egy lövés kapus-szempontú profilja; kevés/rossz mintánál None.

    Kulcsok:
        elengedes_kocka, elengedes_ido_s — a lövőkéz csuklójának leggyorsabb pillanata
        lovokez        — "jobb" / "bal" (a lövő SAJÁT keze, anatómiailag)
        kartartas      — "fent" / "oldalt" / "lent"
        kar_magassag   — a csukló a váll fölött, törzshosszban (+ = fölötte)
        felugras       — bool; csipo_emelkedes — törzshosszban
        vallszelesseg  — |bal váll − jobb váll| / törzs: kicsi = oldalt áll a kamerának
        torzs_doles_fok — a törzs dőlése a függőlegestől
        lovo_helye_px  — (x, y) a két boka közepe a jelenet képén (pálya-kalibrációhoz)
    """
    fps = fps or 30.0
    T = len(kps)
    if T < MIN_FRAMES:
        return None
    valid = kps[..., 2] >= 0.3
    arm_valid = valid[:, [L_SH, R_SH, L_WR, R_WR]].mean()
    if arm_valid < MIN_VALID_FRAC:
        return None
    rel, motion, _conf, _scale = normalize(kps, boxes)

    # Lövőkéz: a csukló testhez mért sebességének csúcsa a nagyobb.
    def wrist_speed(j):
        d = np.linalg.norm(np.diff(rel[:, j], axis=0), axis=1) * fps
        return _smooth(np.concatenate([[0.0], d]))

    vl, vr = wrist_speed(L_WR), wrist_speed(R_WR)
    right = vr.max() >= vl.max()
    wr, sh = (R_WR, R_SH) if right else (L_WR, L_SH)
    release = int(np.argmax(vr if right else vl))

    h = float(rel[release, wr, 1] - rel[release, sh, 1])
    if h >= ARM_HIGH_MIN:
        arm = "fent"
    elif h <= ARM_LOW_MAX:
        arm = "lent"
    else:
        arm = "oldalt"

    rise = jump_rise(motion[:, 1], release, fps)
    sh_w = float(abs(rel[release, L_SH, 0] - rel[release, R_SH, 0]))
    sh_mid = (rel[release, L_SH] + rel[release, R_SH]) / 2
    lean = float(np.degrees(np.arctan2(abs(sh_mid[0]), abs(sh_mid[1]) + 1e-9)))
    feet = kps[release, [15, 16], :2].mean(0)
    if not (kps[release, [15, 16], 2] >= 0.3).all() and boxes is not None and len(boxes) > release:
        b = boxes[release]
        feet = np.array([(b[0] + b[2]) / 2, b[3]])
    return {
        "elengedes_kocka": release,
        "elengedes_ido_s": round(release / fps, 3),
        "lovokez": "jobb" if right else "bal",
        "kartartas": arm,
        "kar_magassag": round(h, 3),
        "fej_folott": bool(rel[release, wr, 1] > rel[release, NOSE, 1]),
        "felugras": bool(rise >= JUMP_MIN_RISE),
        "csipo_emelkedes": round(rise, 3),
        "vallszelesseg": round(sh_w, 3),
        "torzs_doles_fok": round(lean, 1),
        "lovo_helye_px": (round(float(feet[0]), 1), round(float(feet[1]), 1)),
    }


__all__ = ["shot_profile", "jump_rise", "ARM_HIGH_MIN", "ARM_LOW_MAX", "JUMP_MIN_RISE",
           "L_HIP", "R_HIP"]
