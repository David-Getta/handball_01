"""Mezszám a közvetítésből: ki lőtte a gólt? (előtanított OCR + keret + mezszín)

A ticker (`hbd.ticker`) minden gólnál megadja a szerzőt, a keret a mezszámát —
ez kész kiértékelő halmaz. A kérdés: a gól előtti másodpercekben a képről
kiolvasható-e a szerző mezszáma?

Lépések (mind emberi jelölés nélkül):
  1. kivágás: a póz-becslés embereinek törzse (váll–csípő), ha legalább
     MIN_TORSO_PX magas (kisebben a szám olvashatatlan);
  2. OCR (EasyOCR, előtanított; csak számjegy, 1–2 jegy), és a törzs középső
     részének színe (Lab medián);
  3. csapatszín: a színek k-közép csoportjai; a csoport annak a csapatnak a
     színe, amelyiknek a KERETÉBEN szereplő számokat többször olvassuk rajta
     (a szerzőt nem használja → nincs szivárgás);
  4. azonosítás: a gólt szerző csapat (az eredményjelzőből ismert) színén
     olvasott, a keretben szereplő számok megbízhatóság-összege → rangsor.

    python -m hbd.jersey --video meccs.mp4 --pose m2_pose.npz --ticker cimkek/meccs2_ticker.json \\
        --roster cimkek/meccs2_keret.json --cache jersey_cache --out eredmeny.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import defaultdict
from pathlib import Path

import numpy as np

# Ennyi másodperc a gól (az állásváltozás kezdete) előtt; a lövés jellemzően 1–6 s-mal előtte van.
WINDOW_S = (-6.0, -0.5)
# A törzs (váll–csípő) legalább ennyi px magas az 1080p képen.
MIN_TORSO_PX = 35
MIN_KP_CONF = 0.3
MIN_OCR_CONF = 0.3
# Csapatszín: ennyi csoport (két csapat + kapusok / játékvezetők / egyéb).
COLOR_K = 4


def torso_boxes(kps: np.ndarray, W: int, H: int) -> list[tuple[int, int, int, int]]:
    """(x0, y0, x1, y1) törzs-kivágás emberenként (normált kulcspontokból); None, ha kicsi/bizonytalan."""
    out = []
    for kp in kps.astype(np.float32):
        p = kp[[5, 6, 11, 12]] * np.array([W, H, 1], np.float32)
        if (p[:, 2] < MIN_KP_CONF).any():
            out.append(None)
            continue
        x0, x1, y0, y1 = p[:, 0].min(), p[:, 0].max(), p[:, 1].min(), p[:, 1].max()
        h = y1 - y0
        if h < MIN_TORSO_PX:
            out.append(None)
            continue
        pad = 0.25 * max(x1 - x0, h)
        out.append((int(max(0, x0 - pad)), int(max(0, y0 - 0.1 * h)), int(min(W, x1 + pad)), int(min(H, y1))))
    return out


def torso_color(crop: np.ndarray) -> np.ndarray:
    """A kivágás középső részének Lab mediánja (a mez színe, a háttér nélkül)."""
    import cv2

    h, w = crop.shape[:2]
    c = crop[h // 4: 3 * h // 4, w // 4: 3 * w // 4]
    lab = cv2.cvtColor(np.ascontiguousarray(c), cv2.COLOR_RGB2LAB).reshape(-1, 3)
    return np.median(lab, 0).astype(np.float32)


def read_window(video: str, t0: float, t1: float, pose: dict, reader, W: int = 1920, H: int = 1080,
                fast: bool = False) -> list[dict]:
    """A [t0, t1] ablak póz-kockáin minden olvasható törzs: szín + OCR-olvasatok."""
    fps, frames = float(pose["fps"]), pose["frame"]
    k0, k1 = int(np.ceil(t0 * fps)), int(np.floor(t1 * fps))
    sel = np.where((frames >= k0) & (frames <= k1))[0]
    if not len(sel):
        return []
    # pontos keresés a k0. kockára (-ss a bemenet előtt, dekódolással), utána a póz-kockák n = k - k0
    want = "+".join(f"eq(n\\,{int(frames[i]) - k0})" for i in sel)
    # a -t BEMENETI kapcsoló (az -i előtt): kimeneti -t-vel a ritkított kimenet sosem éri el a
    # hosszt, és az ffmpeg a videó végéig dekódolna
    cmd = ["ffmpeg", "-v", "error", "-threads", "1", "-ss", f"{k0 / fps:.3f}", "-t", f"{(k1 - k0 + 1) / fps:.3f}",
           "-i", video, "-vf", f"select='{want}'", "-fps_mode", "passthrough",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, stdout=subprocess.PIPE, check=True).stdout
    n = len(raw) // (W * H * 3)
    imgs = np.frombuffer(raw[:n * W * H * 3], np.uint8).reshape(n, H, W, 3)
    recs = []
    for j, i in enumerate(sel[:n]):
        a, b = int(pose["offsets"][i]), int(pose["offsets"][i + 1])
        for q, box in enumerate(torso_boxes(pose["kps"][a:b], W, H)):
            if box is None:
                continue
            x0, y0, x1, y1 = box
            crop = imgs[j][y0:y1, x0:x1]
            if fast:
                # csak a felismerő a teljes kivágáson (a szám a törzs közepén van) — kb. 10× gyorsabb
                import cv2

                g = cv2.cvtColor(np.ascontiguousarray(crop), cv2.COLOR_RGB2GRAY)
                res = reader.recognize(cv2.resize(g, None, fx=2, fy=2), allowlist="0123456789")
            else:
                res = reader.readtext(crop, allowlist="0123456789", mag_ratio=3.0)
            reads = [(int(txt), round(float(conf), 3)) for _, txt, conf in res
                     if 1 <= len(txt) <= 2 and conf >= MIN_OCR_CONF]
            recs.append({"k": int(frames[i]), "ember": q, "doboz": list(box),
                         "szin": torso_color(crop).round(1).tolist(), "olvasat": reads})
    return recs


def team_colors(recs: list[dict], rosters: dict[str, set[int]], k: int = COLOR_K) -> dict:
    """A színcsoportok csapathoz rendelése a keret-számok olvasatával (a szerzőt nem nézi)."""
    from sklearn.cluster import KMeans

    X = np.array([r["szin"] for r in recs], np.float32)
    km = KMeans(k, n_init=10, random_state=0).fit(X)
    votes = np.zeros((k, len(rosters)))
    sides = sorted(rosters)
    for r, c in zip(recs, km.labels_):
        for num, conf in r["olvasat"]:
            for s, side in enumerate(sides):
                if num in rosters[side] and not any(num in rosters[o] for o in sides if o != side):
                    votes[c, s] += conf
    # csapatonként a legtöbb szavazatú csoport (két csapat nem kaphatja ugyanazt)
    assign = {}
    order = np.dstack(np.unravel_index(np.argsort(-votes, axis=None), votes.shape))[0]
    for c, s in order:
        if sides[s] not in assign and c not in assign.values() and votes[c, s] > 0:
            assign[sides[s]] = int(c)
    return {"kozeppontok": km.cluster_centers_.round(1).tolist(), "csapat_csoport": assign,
            "szavazatok": votes.round(1).tolist(), "oldalak": sides}


def rank_numbers(recs: list[dict], centers: np.ndarray, cluster: int | None, roster: set[int]) -> list[tuple[int, float]]:
    """A csapat színén olvasott keret-számok rangsora (megbízhatóság-összeg)."""
    score = defaultdict(float)
    for r in recs:
        if cluster is not None:
            c = int(np.argmin(((centers - np.array(r["szin"])) ** 2).sum(1)))
            if c != cluster:
                continue
        for num, conf in r["olvasat"]:
            if num in roster:
                score[num] += conf
    return sorted(score.items(), key=lambda z: (-z[1], z[0]))


def _roster_numbers(roster: dict) -> dict[str, set[int]]:
    return {s: {p["mez"] for p in roster[s]["jatekosok"] if p["poszt"] != "kapus"} for s in ("hazai", "vendeg")}


def _scorer_number(roster: dict, side: str, name: str) -> int | None:
    toks = set(name.lower().split())
    for p in roster[side]["jatekosok"]:
        if set(p["nev"].lower().split()) <= toks:
            return p["mez"]
    return None


def evaluate(windows: dict[str, list[dict]], goals: list[dict], roster: dict) -> dict:
    nums = _roster_numbers(roster)
    allrecs = [r for v in windows.values() for r in v]
    tc = team_colors(allrecs, nums)
    centers = np.array(tc["kozeppontok"], np.float32)
    rows = []
    for g in goals:
        key = f"{g['t_tol']:.1f}"
        if key not in windows:
            continue
        want = _scorer_number(roster, g["csapat"], g["jatekos"])
        for mode, cl in (("szinnel", tc["csapat_csoport"].get(g["csapat"])), ("szin_nelkul", None)):
            rk = rank_numbers(windows[key], centers, cl, nums[g["csapat"]])
            pos = next((i for i, (n, _) in enumerate(rk) if n == want), None)
            rows.append({"t_tol": g["t_tol"], "jatekos": g["jatekos"], "mez": want, "mod": mode,
                         "helyezes": None if pos is None else pos + 1, "jeloltek": len(rk),
                         "rangsor": rk[:5]})
    res = {"csapatszin": tc, "golok": len(goals), "sorok": rows}
    for mode in ("szinnel", "szin_nelkul"):
        r = [x for x in rows if x["mod"] == mode]
        n = len(r)
        top1 = sum(x["helyezes"] == 1 for x in r)
        top3 = sum(x["helyezes"] is not None and x["helyezes"] <= 3 for x in r)
        seen = sum(x["helyezes"] is not None for x in r)
        # viszonyítás: ha a látott keret-számok közül véletlenül választunk
        chance = float(np.mean([1.0 / x["jeloltek"] if x["jeloltek"] else 0.0 for x in r])) if r else 0.0
        res[mode] = {"golok": n, "elso": top1, "elso_harom": top3, "egyaltalan_olvasva": seen,
                     "veletlen_elso": round(chance * n, 1)}
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Mezszám a közvetítésből: a gól szerzője")
    ap.add_argument("--video", required=True)
    ap.add_argument("--pose", required=True, help="a match_pose kimenete (teljes kép, normált kulcspontok)")
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--roster", required=True)
    ap.add_argument("--cache", required=True, help="mappa: gólonként egy JSON (folytatható)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--fast", action="store_true", help="csak felismerés (szövegkeresés nélkül), ~10× gyorsabb")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    goals = [e for e in json.loads(Path(a.ticker).read_text())["esemenyek"] if e["tipus"] == "gol" and "t_tol" in e]
    if a.limit:
        goals = goals[:: max(1, len(goals) // a.limit)][: a.limit]
    roster = json.loads(Path(a.roster).read_text())
    pose = dict(np.load(a.pose))
    cache = Path(a.cache)
    cache.mkdir(parents=True, exist_ok=True)
    reader = None
    windows = {}
    for g in goals:
        key = f"{g['t_tol']:.1f}"
        f = cache / f"gol_{key}.json"
        if not f.exists():
            if reader is None:
                import easyocr

                reader = easyocr.Reader(["en"], gpu=False, verbose=False)
            recs = read_window(a.video, g["t_tol"] + WINDOW_S[0], g["t_tol"] + WINDOW_S[1], pose, reader,
                               fast=a.fast)
            f.write_text(json.dumps(recs))
            print(f"{key}: {len(recs)} törzs, {sum(len(r['olvasat']) for r in recs)} olvasat", flush=True)
        windows[key] = json.loads(f.read_text())
    res = evaluate(windows, goals, roster)
    Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1))
    for mode in ("szinnel", "szin_nelkul"):
        print(mode, res[mode])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
