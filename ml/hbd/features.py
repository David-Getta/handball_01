"""Testpont-sorozatból tanítható bemenet.

Két alak:
  * SOROZAT (a neurális hálónak): kockánként a 17 testpont a csípő-
    középponthoz viszonyítva, törzshosszal osztva, felfelé pozitív y-nal,
    plusz a test középpontjának elmozdulása; fix hosszra (SEQ_LEN) átmintázva.
  * JELLEMZŐK (a döntési fának): klipenként néhány tucat értelmezhető szám
    (kar-magasság, csukló-sebesség, felugrás, váll-szélesség, ...).

A normalizálás teszi a kis (~110 px) és a nagy játékost, a kép bal és jobb
szélét összevethetővé. Az idő MÁSODPERCBEN számít (a jelenetek 30 és 48
fps-esek vegyesen) — a sebesség tehát egység / s, nem egység / kocka.
"""

from __future__ import annotations

import numpy as np

# COCO testpont-indexek
NOSE = 0
L_SH, R_SH, L_EL, R_EL, L_WR, R_WR = 5, 6, 7, 8, 9, 10
L_HIP, R_HIP, L_KN, R_KN, L_AN, R_AN = 11, 12, 13, 14, 15, 16
# Tükrözéskor (bal ↔ jobb) a testpontok cseréje
FLIP_PERM = [0, 2, 1, 4, 3, 6, 5, 8, 7, 10, 9, 12, 11, 14, 13, 16, 15]

# Ennél kisebb megbízhatóságú testpontot hiányzónak veszünk és időben pótoljuk.
KP_MIN_CONF = 0.3
# A neurális háló bemenetének hossza (kocka).
SEQ_LEN = 32
# A sorozat csatornái: 17×(x, y) + középpont-elmozdulás (dx, dy) + 17 megbízhatóság
SEQ_CHANNELS = 17 * 2 + 2 + 17


def fill_missing(kps: np.ndarray, min_conf: float = KP_MIN_CONF):
    """Hiányzó testpontok időbeli lineáris pótlása.

    Visszaad: xy (T, 17, 2) — a sosem látott testpont NaN —, valid (T, 17).
    """
    T = len(kps)
    xy = kps[..., :2].astype(np.float64).copy()
    valid = kps[..., 2] >= min_conf
    t = np.arange(T)
    for j in range(kps.shape[1]):
        v = valid[:, j]
        if v.sum() == 0:
            xy[:, j] = np.nan
        elif v.sum() < T:
            for d in range(2):
                xy[:, j, d] = np.interp(t, t[v], xy[v, j, d])
    return xy, valid


def _mid(xy, a, b):
    return (xy[:, a] + xy[:, b]) / 2


def body_scale(xy: np.ndarray, boxes: np.ndarray | None = None) -> float:
    """Törzshossz px-ben (váll-közép ↔ csípő-közép medián); ha nincs, a doboz-magasság 1/3-a."""
    torso = np.linalg.norm(_mid(xy, L_SH, R_SH) - _mid(xy, L_HIP, R_HIP), axis=1)
    s = float(np.nanmedian(torso)) if np.isfinite(torso).any() else float("nan")
    if not np.isfinite(s) or s < 1e-3:
        if boxes is not None and len(boxes):
            s = float(np.median(boxes[:, 3] - boxes[:, 1])) / 3
        else:
            s = 1.0
    return max(s, 1e-3)


def normalize(kps: np.ndarray, boxes: np.ndarray | None = None):
    """Testközpontú, törzshosszal osztott, felfelé pozitív koordináták.

    Visszaad: rel (T, 17, 2), center_motion (T, 2) a kezdőponthoz képest,
    conf (T, 17), scale (px).
    """
    xy, _valid = fill_missing(kps)
    scale = body_scale(xy, boxes)
    center = _mid(xy, L_HIP, R_HIP)
    if boxes is not None and len(boxes):
        box_c = np.stack([(boxes[:, 0] + boxes[:, 2]) / 2, (boxes[:, 1] + boxes[:, 3]) / 2], 1)
        bad = ~np.isfinite(center).all(1)
        center[bad] = box_c[bad]
    center = np.nan_to_num(center)
    rel = (xy - center[:, None, :]) / scale
    rel[..., 1] *= -1  # kép-y lefelé nő → felfelé pozitívra fordítjuk
    motion = (center - center[:1]) / scale
    motion[:, 1] *= -1
    return np.nan_to_num(rel), motion, kps[..., 2].astype(np.float64), scale


def resample(arr: np.ndarray, n: int = SEQ_LEN) -> np.ndarray:
    """Időbeli lineáris átmintázás n kockára (az első tengely az idő)."""
    T = len(arr)
    if T == 0:
        return np.zeros((n,) + arr.shape[1:])
    if T == 1:
        return np.repeat(arr, n, axis=0)
    src = np.linspace(0, T - 1, n)
    i0 = np.floor(src).astype(int)
    i1 = np.minimum(i0 + 1, T - 1)
    w = (src - i0).reshape((-1,) + (1,) * (arr.ndim - 1))
    return arr[i0] * (1 - w) + arr[i1] * w


def sequence(kps: np.ndarray, boxes: np.ndarray | None = None, n: int = SEQ_LEN) -> np.ndarray:
    """A neurális háló bemenete: (n, SEQ_CHANNELS) float32."""
    rel, motion, conf, _ = normalize(kps, boxes)
    T = len(kps)
    flat = np.concatenate([rel.reshape(T, -1), motion, conf], axis=1)
    return resample(flat, n).astype(np.float32)


def flip_sequence(seq: np.ndarray) -> np.ndarray:
    """Tükrözött sorozat (adatbővítéshez): x negálva, bal ↔ jobb testpontok cserélve."""
    out = seq.copy()
    pts = out[:, :34].reshape(len(out), 17, 2)[:, FLIP_PERM]
    pts[..., 0] *= -1
    out[:, :34] = pts.reshape(len(out), -1)
    out[:, 34] *= -1  # vízszintes elmozdulás
    out[:, 36:] = seq[:, 36:][:, FLIP_PERM]
    return out


def _angle(a, b, c):
    """A b csúcsú szög fokban (a-b-c), kockánként."""
    v1, v2 = a - b, c - b
    cos = (v1 * v2).sum(-1) / (np.linalg.norm(v1, axis=-1) * np.linalg.norm(v2, axis=-1) + 1e-9)
    return np.degrees(np.arccos(np.clip(cos, -1, 1)))


def _speed(p: np.ndarray, fps: float) -> np.ndarray:
    """Pont-pálya sebessége egység / s (kockánként, az első kocka 0)."""
    if len(p) < 2:
        return np.zeros(len(p))
    v = np.linalg.norm(np.diff(p, axis=0), axis=-1) * fps
    return np.concatenate([[0.0], v])


def _stats(prefix: str, x: np.ndarray) -> dict:
    if len(x) == 0:
        return {f"{prefix}_{k}": 0.0 for k in ("mean", "std", "min", "max")}
    return {f"{prefix}_mean": float(np.mean(x)), f"{prefix}_std": float(np.std(x)),
            f"{prefix}_min": float(np.min(x)), f"{prefix}_max": float(np.max(x))}


def clip_features(kps: np.ndarray, boxes: np.ndarray | None, fps: float) -> dict:
    """Klip-szintű, értelmezhető jellemzők (név → szám, rögzített sorrend)."""
    fps = fps or 30.0
    rel, motion, conf, _ = normalize(kps, boxes)
    T = len(kps)
    f: dict[str, float] = {
        "duration_s": T / fps,
        "kp_conf_mean": float(conf.mean()) if T else 0.0,
        "kp_valid_frac": float((conf >= KP_MIN_CONF).mean()) if T else 0.0,
    }
    for side, sh, el, wr in (("l", L_SH, L_EL, L_WR), ("r", R_SH, R_EL, R_WR)):
        h = rel[:, wr, 1] - rel[:, sh, 1]  # csukló a váll fölött (+)
        f.update(_stats(f"wrist_h_{side}", h))
        f[f"wrist_h_{side}_argmax"] = float(np.argmax(h) / max(1, T - 1)) if T else 0.0
        f.update(_stats(f"wrist_v_{side}", _speed(rel[:, wr], fps)))
        f.update(_stats(f"elbow_ang_{side}", _angle(rel[:, sh], rel[:, el], rel[:, wr])))
    both_h = np.maximum(rel[:, L_WR, 1] - rel[:, L_SH, 1], rel[:, R_WR, 1] - rel[:, R_SH, 1])
    f["wrist_h_max_both"] = float(both_h.max()) if T else 0.0
    head_y = rel[:, NOSE, 1]
    f["wrist_above_head_frac"] = float(
        (np.maximum(rel[:, L_WR, 1], rel[:, R_WR, 1]) > head_y).mean()) if T else 0.0
    # test-mozgás: vízszintes sebesség, függőleges kilengés (felugrás)
    f.update(_stats("center_v", _speed(motion, fps)))
    f["center_dy_range"] = float(np.ptp(motion[:, 1])) if T else 0.0
    f["center_dx_range"] = float(np.ptp(motion[:, 0])) if T else 0.0
    # váll-szélesség a törzshez: kicsi = oldalt áll a kamerának, nagy = szemben
    f.update(_stats("shoulder_w", np.abs(rel[:, L_SH, 0] - rel[:, R_SH, 0])))
    # törzs dőlése a függőlegestől (fok)
    sh_mid = (rel[:, L_SH] + rel[:, R_SH]) / 2
    lean = np.degrees(np.arctan2(np.abs(sh_mid[:, 0]), np.abs(sh_mid[:, 1]) + 1e-9))
    f.update(_stats("lean", lean))
    f.update(_stats("knee_ang_l", _angle(rel[:, L_HIP], rel[:, L_KN], rel[:, L_AN])))
    f.update(_stats("knee_ang_r", _angle(rel[:, R_HIP], rel[:, R_KN], rel[:, R_AN])))
    f["ankle_spread_max"] = float(np.abs(rel[:, L_AN, 0] - rel[:, R_AN, 0]).max()) if T else 0.0
    return f


def feature_matrix(clips: list[dict]) -> tuple[np.ndarray, list[str]]:
    rows = [clip_features(c["kps"], c.get("boxes"), c.get("fps", 30.0)) for c in clips]
    names = list(rows[0]) if rows else []
    X = np.array([[r[n] for n in names] for r in rows], np.float64)
    return np.nan_to_num(X), names
