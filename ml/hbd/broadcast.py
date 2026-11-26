"""A közvetítés saját jelei: eredményjelző és kamera-mozgás.

A tévés közvetítés többet tud a meccsről, mint amit a játékosok testtartása
mutat. Két ilyen jel, ami a lövésfelismerésnek segít:

  eredményjelző — a bal felső sarokban. GÓL után az állás megváltozik;
                  ISMÉTLÉS alatt (és sok közelinél) a grafika eltűnik.
  kamera        — a vezető kamera követi a játékot: támadásépítésnél lassan
                  úszik, lövés után megáll vagy MEGFORDUL (indul a másik
                  irányba a játék), vágásnál a kép hirtelen kicserélődik.

Ugyanazokat a mintakockákat nézi, mint a `match_pose` (minden STRIDE-adik),
így a két kimenet kockánként összefésülhető.

Az eredményjelző helye a közvetítés grafikájától függ; az alapérték az EHF
Bajnokok Ligája közvetítéseié (a kép arányában megadva, bármilyen
felbontásra jó). Más grafikánál: --sb-static / --sb-score.

    python -m hbd.broadcast --video meccs.mp4 --out meccs_broadcast.npz --stride 5
"""

from __future__ import annotations

import argparse
import subprocess
import time
from pathlib import Path

import numpy as np

from .video import ffmpeg_exe, probe

# A feldolgozó kép (szürke). Az eredményjelző számjegyei ezen ~20×25 pixelesek.
WORK = (640, 360)
# A kamera-becsléshez tovább kicsinyített kép (fázis-korreláció).
CAM = (160, 90)
# Az eredményjelző részei a kép arányában (x0, y0, x1, y1).
#   STATIC: a logó és a csapatnevek — ez mindig ugyanúgy néz ki, ha látszik;
#   SCORE:  az állás két számjegye — ez változik gólnál.
SB_STATIC = (0.090, 0.050, 0.186, 0.117)
SB_SCORE = (0.189, 0.050, 0.222, 0.117)
# Az eredményjelző "látszik", ha az állandó része ennyire hasonlít a mintára (NCC).
SB_PRESENT_NCC = 0.80
# A kamera-elmozdulás becslése ennél gyengébb csúcsnál megbízhatatlan (vágás, elmosódás).
CAM_MIN_RESPONSE = 0.05


def _box(frac, w, h):
    x0, y0, x1, y1 = frac
    return int(round(x0 * w)), int(round(y0 * h)), int(round(x1 * w)), int(round(y1 * h))


def iter_gray(video: str, stride: int):
    """(kocka-index, szürke WORK-méretű kép) minden stride-adik kockára."""
    w, h = WORK
    cmd = [ffmpeg_exe(), "-v", "error", "-i", video, "-vf",
           f"select='not(mod(n\\,{stride}))',scale={w}:{h},format=gray", "-vsync", "0",
           "-f", "rawvideo", "-pix_fmt", "gray", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    k = 0
    try:
        while True:
            buf = proc.stdout.read(w * h)
            if len(buf) < w * h:
                break
            yield k * stride, np.frombuffer(buf, np.uint8).reshape(h, w)
            k += 1
    finally:
        proc.stdout.close()
        proc.kill()
        proc.wait()


def camera_shift(prev: np.ndarray, cur: np.ndarray, win: np.ndarray) -> tuple[float, float, float]:
    """A kép elmozdulása (dx, dy a CAM-kép szélességének/magasságának arányában) és a csúcs ereje."""
    import cv2

    (dx, dy), resp = cv2.phaseCorrelate(prev, cur, win)
    return dx / CAM[0], dy / CAM[1], float(resp)


def extract(video: str, stride: int, sb_static=SB_STATIC, sb_score=SB_SCORE) -> dict:
    """Nyers jelek mintakockánként: eredményjelző-kivágások + kamera-elmozdulás."""
    import cv2

    w, h = WORK
    st, sc = _box(sb_static, w, h), _box(sb_score, w, h)
    win = cv2.createHanningWindow(CAM, cv2.CV_32F)
    frames, static, score, cam = [], [], [], []
    prev = None
    t0 = time.time()
    fps = probe(video)[2] or 25.0
    for fi, g in iter_gray(video, stride):
        frames.append(fi)
        static.append(g[st[1]:st[3], st[0]:st[2]].copy())
        score.append(g[sc[1]:sc[3], sc[0]:sc[2]].copy())
        small = cv2.resize(g, CAM, interpolation=cv2.INTER_AREA).astype(np.float32)
        cam.append(camera_shift(prev, small, win) if prev is not None else (0.0, 0.0, 0.0))
        prev = small
        if len(frames) % 3000 == 0:
            print(f"  {fi / fps / 60:5.1f}. perc · {len(frames)} minta · "
                  f"{(time.time() - t0) / len(frames) * 1000:.1f} ms/minta", flush=True)
    return {"frame": np.array(frames, np.int64), "sb_static": np.stack(static), "sb_score": np.stack(score),
            "cam": np.array(cam, np.float32), "fps": np.float32(fps), "stride": np.int32(stride)}


def _ncc(a: np.ndarray, tmpl: np.ndarray) -> np.ndarray:
    """Normált keresztkorreláció minden kivágás és a minta között (N,)."""
    a = a.reshape(len(a), -1).astype(np.float32)
    a = a - a.mean(1, keepdims=True)
    t = tmpl.ravel().astype(np.float32)
    t = t - t.mean()
    return (a @ t) / (np.linalg.norm(a, axis=1) * np.linalg.norm(t) + 1e-6)


def scoreboard_presence(static: np.ndarray) -> np.ndarray:
    """Mennyire látszik az eredményjelző (NCC a mintához, -1..1).

    A minta a medián kivágás: a grafika a közvetítés nagy részében látszik,
    így a medián maga az eredményjelző. Egy finomító kör: a medián csak a
    biztosan látszó kockákból."""
    tmpl = np.median(static, 0)
    ncc = _ncc(static, tmpl)
    sure = ncc > SB_PRESENT_NCC
    if sure.sum() > 50:
        ncc = _ncc(static, np.median(static[sure], 0))
    return ncc


def score_change(score: np.ndarray, present: np.ndarray) -> np.ndarray:
    """Az állás-számjegyek változása az előző mintához képest (átlagos abszolút eltérés).

    Csak ott értelmes, ahol MINDKÉT mintán látszik a grafika; máshol 0
    (a grafika be- és kiúszása nem gól)."""
    s = score.reshape(len(score), -1).astype(np.float32)
    d = np.zeros(len(s), np.float32)
    d[1:] = np.abs(s[1:] - s[:-1]).mean(1)
    ok = np.zeros(len(s), bool)
    ok[1:] = present[1:] & present[:-1]
    return np.where(ok, d, 0.0)


# Gólszámlálás az eredményjelzőből: egy GÓL után az állás TARTÓSAN más; a grafika
# animációja (kiúszás, statisztika-sáv, ismétlés-kártya) után a kép visszaáll.
# Egy állapot legalább ennyi ideig látszó, változatlan grafika (s); két gól közt legalább ennyi idő.
GOAL_STABLE_S = 2.0
GOAL_MIN_GAP_S = 8.0
# A jelölt változás: a mintánkénti eltérés legalább ennyi (a zaj ~0,1–0,3).
GOAL_CAND_DIFF = 2.0


def goal_changes(score: np.ndarray, t: np.ndarray, present: np.ndarray, state_diff: float | None = None) -> dict:
    """Tartós állásváltozások (gólok) időpontjai az állás-kivágásokból.

    Az állás ÁLLAPOTOK sorozata: egy állapot a grafika olyan, legalább
    GOAL_STABLE_S hosszú szakasza, ahol látszik és nem változik (szomszédos
    minták eltérése < GOAL_CAND_DIFF). Gól ott van, ahol a következő állapot
    mediánképe eltér az utoljára elfogadott állapotétól — akkor is, ha közben
    a grafika ismétlés miatt percekig nem látszott. Az ennél rövidebb szakaszok
    (animáció, beúszás) nem állapotok, így az A→B→A villanás nem számít.
    A state_diff alapból az állapot-váltások eltéréseinek kétcsúcsú eloszlásából jön (Otsu)."""
    s = score.reshape(len(score), -1).astype(np.float32)
    step = np.full(len(s), np.inf, np.float32)
    step[1:] = np.abs(s[1:] - s[:-1]).mean(1)
    ok = present & (step < GOAL_CAND_DIFF)
    ok[0] = present[0]
    # stabil szakaszok
    segs, i, n = [], 0, len(s)
    while i < n:
        if not ok[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and ok[j + 1] and present[j + 1]:
            j += 1
        if t[j] - t[i] >= GOAL_STABLE_S:
            segs.append((t[i], t[j], np.median(s[i:j + 1], 0)))
        i = j + 1
    if len(segs) < 2:
        return {"t": np.zeros(0), "kuszob": state_diff, "jeloltek": 0, "elteresek": np.zeros(0)}
    d_all = np.array([np.abs(segs[k][2] - segs[k - 1][2]).mean() for k in range(1, len(segs))])
    if state_diff is None:
        state_diff = _otsu(d_all)
    times, state = [], segs[0][2]
    for (t0, _t1, med) in segs[1:]:
        if np.abs(med - state).mean() > state_diff:
            if not times or t0 - times[-1] > GOAL_MIN_GAP_S:
                times.append(float(t0))
            state = med
    return {"t": np.array(times), "kuszob": float(state_diff), "jeloltek": len(segs), "elteresek": d_all}


def _otsu(x: np.ndarray, bins: int = 64) -> float:
    """Két csoportra bontó küszöb (Otsu) — a "nem változott" és a "változott" állás közt."""
    lx = np.log1p(x)
    hist, edges = np.histogram(lx, bins)
    centers = (edges[:-1] + edges[1:]) / 2
    best, thr = -1.0, centers[0]
    for k in range(1, bins):
        w0, w1 = hist[:k].sum(), hist[k:].sum()
        if w0 == 0 or w1 == 0:
            continue
        m0 = (hist[:k] * centers[:k]).sum() / w0
        m1 = (hist[k:] * centers[k:]).sum() / w1
        v = w0 * w1 * (m0 - m1) ** 2
        if v > best:
            best, thr = v, edges[k]
    return float(np.expm1(thr))


def features(raw: dict) -> dict:
    """A nyers jelekből a lövésfelismerő mintakockánkénti jelei."""
    present_ncc = scoreboard_presence(raw["sb_static"])
    present = present_ncc > SB_PRESENT_NCC
    dx, dy, resp = raw["cam"].T
    reliable = resp >= CAM_MIN_RESPONSE
    return {"frame": raw["frame"], "fps": raw["fps"], "stride": raw["stride"],
            "sb_ncc": present_ncc.astype(np.float32),
            "sb_change": score_change(raw["sb_score"], present),
            "cam_dx": np.where(reliable, dx, 0.0).astype(np.float32),
            "cam_dy": np.where(reliable, dy, 0.0).astype(np.float32),
            "cam_resp": resp.astype(np.float32)}


def load(path: str | Path) -> dict:
    z = np.load(path)
    d = {k: z[k] for k in z.files}
    d["t"] = d["frame"] / float(d["fps"])
    return d


def align(pose_frames: np.ndarray, bc: dict) -> dict:
    """A közvetítési jelek a póz-mintakockákra igazítva (azonos kocka-indexek)."""
    idx = np.searchsorted(bc["frame"], pose_frames)
    idx = np.clip(idx, 0, len(bc["frame"]) - 1)
    exact = bc["frame"][idx] == pose_frames
    out = {}
    for k in ("sb_ncc", "sb_change", "cam_dx", "cam_dy", "cam_resp"):
        out[k] = np.where(exact, bc[k][idx], 0.0).astype(np.float32)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Közvetítési jelek: eredményjelző és kamera-mozgás")
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--stride", type=int, default=5)
    ap.add_argument("--sb-static", type=float, nargs=4, default=SB_STATIC)
    ap.add_argument("--sb-score", type=float, nargs=4, default=SB_SCORE)
    ap.add_argument("--keep-crops", action="store_true", help="a nyers eredményjelző-kivágásokat is menti")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    raw = extract(args.video, args.stride, tuple(args.sb_static), tuple(args.sb_score))
    feat = features(raw)
    if args.keep_crops:
        feat.update(sb_static_crops=raw["sb_static"], sb_score_crops=raw["sb_score"])
    np.savez_compressed(out, **feat)
    pres = (feat["sb_ncc"] > SB_PRESENT_NCC).mean()
    print(f"Kész: {len(feat['frame'])} minta; eredményjelző látszik: {100 * pres:.0f}% → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
