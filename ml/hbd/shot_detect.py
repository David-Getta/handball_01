"""Lövésfelismerés a teljes meccsen (időbeli keresés).

Kérdés: a meccs MELYIK pillanataiban van lövés? Bemenet a `match_pose`
kimenete (minden ritkított kockán az összes ember testpontja) és a
meccsjelölő időpontjai (a lövés pillanatában nyomott L).

Módszer (első változat, követés nélkül):
  1. Kockánként összesített jellemzők: hány ember látszik, mekkorák (széles
     kép vagy közeli), van-e magasra emelt dobókar (a csukló a fej fölött),
     milyen gyorsan változik a kép (kamera-mozgás, vágás).
  2. Időablak: minden mintakocka körül a jellemzők alakulása az előtte és
     utána lévő időszakaszokban (a lövés egy mozdulat-SOROZAT: felemelés,
     lendítés, utána a kamera a kapu felé fordul).
  3. Gradiens-erősítéses döntési fák kockánként "lövés-valószínűséget" adnak;
     a csúcsokból lesznek a jelölt lövések.

Kiértékelés: a meccs egymást követő idő-blokkjaira bontva (a szomszédos
kockák ne kerülhessenek a tanító és a teszt részbe is), ESEMÉNY-szinten:
egy jelölt akkor talált, ha MATCH_S-en belül van egy valódi lövés. Mérjük:
hány lövést talál meg (felidézés), és percenként hány téves riasztást ad.

    python -m hbd.shot_detect --pose m1_pose.npz --events meccs1_esemenyek.json --out res/
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from .match_pose import load as load_pose

# A gombnyomás a reakcióidő miatt a lövés UTÁN jön; a jelölt lövés-idő ennyivel korábban van.
REACTION_S = 0.4
# Pozitív minta: a becsült lövés-időhöz ennyire közeli mintakocka.
POS_S = 0.6
# A pozitív körüli "bizonytalan" sáv (se nem pozitív, se nem negatív a tanításban).
IGNORE_S = 2.0
# Egy jelölt akkor talált, ha ennyi másodpercen belül van valódi lövés.
MATCH_S = 1.5
# Két jelölt lövés között legalább ennyi idő (csúcskeresés).
MIN_GAP_S = 2.0
# Az időablak szakaszai (másodperc, a mintakockához képest).
WINDOWS = ((-2.0, -1.0), (-1.0, -0.2), (-0.2, 0.2), (0.2, 1.0), (1.0, 2.0))
BLOCKS = 5
PAIR_S = 4.0

# COCO testpont-indexek
NOSE, L_SH, R_SH, L_WR, R_WR, L_HIP, R_HIP = 0, 5, 6, 9, 10, 11, 12


# ------------------------------------------------------------ események
def shot_times(doc: dict, include_replays: bool = True) -> list[dict]:
    """A meccsjelölő nyomásaiból a lövések (a lövés pillanata = első nyomás − REACTION_S)."""
    from collections import deque

    ev = sorted(doc["esemenyek"], key=lambda e: e["t"])
    out, i = [], 0
    while i < len(ev):
        e = ev[i]
        n = ev[i + 1] if i + 1 < len(ev) else None
        if e.get("tipus") != "loves":
            i += 1
            continue
        paired = (not e.get("eredmeny") and n and n.get("tipus") == "loves" and n.get("eredmeny")
                  and not n.get("kipattano") and n["t"] - e["t"] <= PAIR_S
                  and bool(n.get("ismetles")) == bool(e.get("ismetles")))
        res = n["eredmeny"] if paired else e.get("eredmeny")
        out.append({"t": e["t"] - REACTION_S, "eredmeny": res, "ismetles": bool(e.get("ismetles"))})
        i += 2 if paired else 1
    del deque
    return [s for s in out if include_replays or not s["ismetles"]]


# ------------------------------------------------------------ jellemzők
def frame_features(pose: dict) -> tuple[np.ndarray, list[str]]:
    """Mintakockánkénti összesített jellemzők (N, F)."""
    off, kps, boxes = pose["offsets"], pose["kps"].astype(np.float32), pose["boxes"].astype(np.float32)
    N = len(pose["n"])
    names = ["n_ember", "doboz_mag_median", "doboz_mag_max", "kep_valtozas",
             "kar_fent_max", "kar_fent_db", "csuklo_fej_felett_db", "kar_nyujtas_max",
             "csuklo_magassag_p90", "kozep_x_szoras"]
    F = np.zeros((N, len(names)), np.float32)
    for i in range(N):
        a, b = off[i], off[i + 1]
        F[i, 0] = b - a
        F[i, 3] = pose["motion"][i]
        if b == a:
            continue
        bx = boxes[a:b]
        hgt = bx[:, 3] - bx[:, 1]
        F[i, 1], F[i, 2] = np.median(hgt), hgt.max()
        k = kps[a:b]
        ok = k[..., 2] > 0.3
        sh = (k[:, L_SH, :2] + k[:, R_SH, :2]) / 2
        hip = (k[:, L_HIP, :2] + k[:, R_HIP, :2]) / 2
        torso = np.linalg.norm(sh - hip, axis=1)
        torso = np.where((ok[:, [L_SH, R_SH, L_HIP, R_HIP]].all(1)) & (torso > 1e-3), torso, np.nan)
        # csukló a váll fölött, törzshosszban (kép-y lefelé nő → előjelváltás)
        up_l = np.where(ok[:, L_WR] & ok[:, L_SH], (k[:, L_SH, 1] - k[:, L_WR, 1]) / torso, np.nan)
        up_r = np.where(ok[:, R_WR] & ok[:, R_SH], (k[:, R_SH, 1] - k[:, R_WR, 1]) / torso, np.nan)
        up = np.fmax(up_l, up_r)
        ext_l = np.linalg.norm(k[:, L_WR, :2] - k[:, L_SH, :2], axis=1) / torso
        ext_r = np.linalg.norm(k[:, R_WR, :2] - k[:, R_SH, :2], axis=1) / torso
        ext = np.fmax(np.where(ok[:, L_WR], ext_l, np.nan), np.where(ok[:, R_WR], ext_r, np.nan))
        head = np.where(ok[:, NOSE], k[:, NOSE, 1], np.nan)
        above = (np.where(ok[:, L_WR], k[:, L_WR, 1], np.inf) < head) | (np.where(ok[:, R_WR], k[:, R_WR, 1], np.inf) < head)
        if np.isfinite(up).any():
            F[i, 4] = np.nanmax(up)
            F[i, 5] = np.nansum(up > 0.5)
            F[i, 8] = np.nanpercentile(up, 90)
        F[i, 6] = above.sum()
        if np.isfinite(ext).any():
            F[i, 7] = np.nanmax(ext)
        F[i, 9] = np.std((bx[:, 0] + bx[:, 2]) / 2)
    return np.nan_to_num(F), names


def window_features(F: np.ndarray, t: np.ndarray, names: list[str]) -> tuple[np.ndarray, list[str]]:
    """Minden mintakocka körül a WINDOWS szakaszok átlaga és maximuma (N, F*len(WINDOWS)*2)."""
    N = len(t)
    out, onames = [], []
    for lo, hi in WINDOWS:
        a = np.searchsorted(t, t + lo, side="left")
        b = np.searchsorted(t, t + hi, side="right")
        mean = np.zeros_like(F)
        mx = np.zeros_like(F)
        cs = np.concatenate([np.zeros((1, F.shape[1])), np.cumsum(F, 0)])
        for i in range(N):
            if b[i] > a[i]:
                mean[i] = (cs[b[i]] - cs[a[i]]) / (b[i] - a[i])
                mx[i] = F[a[i]:b[i]].max(0)
        out += [mean, mx]
        onames += [f"{n}@{lo:+.1f}..{hi:+.1f}:atlag" for n in names] + [f"{n}@{lo:+.1f}..{hi:+.1f}:max" for n in names]
    return np.concatenate(out, 1), onames


def labels(t: np.ndarray, shots: list[dict]) -> np.ndarray:
    """1 = lövés-pillanat, 0 = nem lövés, -1 = bizonytalan sáv (tanításból kihagyva)."""
    y = np.zeros(len(t), np.int8)
    st = np.array([s["t"] for s in shots])
    if len(st):
        d = np.abs(t[:, None] - st[None, :]).min(1)
        y[d <= IGNORE_S] = -1
        y[d <= POS_S] = 1
    return y


# ------------------------------------------------------------ események kinyerése
def pick_peaks(t: np.ndarray, score: np.ndarray, thr: float) -> list[tuple[float, float]]:
    """Csúcsok (idő, pontszám) a küszöb fölött, legalább MIN_GAP_S távolságra egymástól."""
    order = np.argsort(-score)
    chosen: list[tuple[float, float]] = []
    for i in order:
        if score[i] < thr:
            break
        if all(abs(t[i] - c) >= MIN_GAP_S for c, _ in chosen):
            chosen.append((float(t[i]), float(score[i])))
    return sorted(chosen)


def match_events(pred: list[tuple[float, float]], truth: np.ndarray) -> tuple[int, int, int]:
    """(találat, téves, kihagyott) — mohó párosítás MATCH_S-en belül."""
    used = np.zeros(len(truth), bool)
    tp = 0
    for tm, _ in sorted(pred, key=lambda p: -p[1]):
        if len(truth) == 0:
            break
        d = np.abs(truth - tm)
        d[used] = np.inf
        j = int(np.argmin(d))
        if d[j] <= MATCH_S:
            used[j] = True
            tp += 1
    return tp, len(pred) - tp, int((~used).sum())


def smooth(score: np.ndarray, k: int = 3) -> np.ndarray:
    if k <= 1:
        return score
    return np.convolve(np.pad(score, k // 2, mode="edge"), np.ones(k) / k, mode="valid")


def evaluate(pose: dict, shots: list[dict], seed: int = 0) -> dict:
    from sklearn.ensemble import HistGradientBoostingClassifier

    t = pose["t"]
    F, names = frame_features(pose)
    X, xnames = window_features(F, t, names)
    y = labels(t, shots)
    st = np.array([s["t"] for s in shots])
    edges = np.linspace(t.min(), t.max() + 1e-6, BLOCKS + 1)
    score = np.zeros(len(t))
    for b in range(BLOCKS):
        te = (t >= edges[b]) & (t < edges[b + 1])
        # a blokkhatár körüli 5 s-ot kihagyjuk a tanításból (ne szivárogjon át az ablakon)
        tr = ~te & (np.abs(t - edges[b]) > 5) & (np.abs(t - edges[b + 1]) > 5) & (y >= 0)
        clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31,
                                             l2_regularization=1.0, class_weight="balanced", random_state=seed)
        clf.fit(X[tr], y[tr])
        score[te] = clf.predict_proba(X[te])[:, 1]
    score = smooth(score, 3)

    minutes = (t.max() - t.min()) / 60
    curve = []
    for thr in np.round(np.arange(0.05, 0.96, 0.05), 2):
        pred = pick_peaks(t, score, thr)
        tp, fp, fn = match_events(pred, st)
        prec = tp / max(1, tp + fp)
        rec = tp / max(1, len(st))
        curve.append({"kuszob": float(thr), "talalt": tp, "teves": fp, "kihagyott": fn,
                      "felidezes": rec, "pontossag": prec, "teves_per_perc": fp / minutes,
                      "f1": 2 * prec * rec / max(1e-9, prec + rec)})
    best = max(curve, key=lambda c: c["f1"])
    # viszonyítás: a legegyszerűbb szabály — "valakinek magasan van a karja"
    rule = F[:, names.index("kar_fent_max")]
    rule = (rule - rule.min()) / (rule.max() - rule.min() + 1e-9)
    rule_curve = []
    for thr in np.round(np.arange(0.05, 0.96, 0.05), 2):
        tp, fp, fn = match_events(pick_peaks(t, smooth(rule, 3), thr), st)
        prec, rec = tp / max(1, tp + fp), tp / max(1, len(st))
        rule_curve.append({"kuszob": float(thr), "felidezes": rec, "pontossag": prec,
                           "teves_per_perc": fp / minutes, "f1": 2 * prec * rec / max(1e-9, prec + rec)})
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=31,
                                         l2_regularization=1.0, class_weight="balanced", random_state=seed)
    clf.fit(X[y >= 0], y[y >= 0])
    return {"percek": minutes, "mintakockak": int(len(t)), "lovesek": int(len(st)),
            "pozitiv_minta": int((y == 1).sum()), "gorbe": curve, "legjobb": best,
            "szabaly_legjobb": max(rule_curve, key=lambda c: c["f1"]),
            "score": score, "t": t, "model": clf, "features": xnames}


def at_recall(curve: list[dict], target: float) -> dict | None:
    ok = [c for c in curve if c["felidezes"] >= target]
    return min(ok, key=lambda c: c["teves_per_perc"]) if ok else None


def write_report(res: dict, out: Path, title: str) -> Path:
    b, r = res["legjobb"], res["szabaly_legjobb"]
    pct = lambda v: f"{100 * v:.0f}%"  # noqa: E731
    md = [f"# Lövésfelismerés a teljes meccsen — {title}", "",
          f"{res['percek']:.0f} perc, {res['mintakockak']} mintakocka, {res['lovesek']} jelölt lövés "
          f"(élő + ismétlés). Kiértékelés: {BLOCKS} egymást követő idő-blokk, mindig a többi blokkon tanítva. "
          f"Egy jelölt akkor talált, ha {MATCH_S} s-on belül van valódi lövés.", "",
          "| | felidézés (megtalált lövések) | pontosság (a jelöltekből valódi) | téves riasztás / perc |",
          "|---|---|---|---|",
          f"| tanított modell (legjobb F1) | {pct(b['felidezes'])} | {pct(b['pontossag'])} | {b['teves_per_perc']:.2f} |",
          f"| szabály: „valakinek magasan a karja” | {pct(r['felidezes'])} | {pct(r['pontossag'])} | {r['teves_per_perc']:.2f} |",
          "", "Felidézés–téves riasztás egyensúly (tanított modell):", "",
          "| cél-felidézés | elért | téves riasztás / perc | pontosság |", "|---|---|---|---|"]
    for target in (0.5, 0.7, 0.8, 0.9):
        c = at_recall(res["gorbe"], target)
        if c:
            md.append(f"| {pct(target)} | {pct(c['felidezes'])} | {c['teves_per_perc']:.2f} | {pct(c['pontossag'])} |")
        else:
            md.append(f"| {pct(target)} | nem érhető el | – | – |")
    p = out / "shot_detect.md"
    p.write_text("\n".join(md) + "\n")
    return p


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Lövésfelismerés a teljes meccsen")
    ap.add_argument("--pose", required=True, help="a hbd.match_pose kimenete")
    ap.add_argument("--events", required=True, help="a meccsjelölő dokumentuma (JSON)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--live-only", action="store_true", help="csak az élő lövések (ismétlések nélkül)")
    ap.add_argument("--title", default="")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    doc = json.loads(Path(args.events).read_text())
    doc = doc.get("data", doc)
    shots = shot_times(doc, include_replays=not args.live_only)
    pose = load_pose(args.pose)
    res = evaluate(pose, shots)
    import joblib

    joblib.dump({"model": res.pop("model"), "features": res["features"]}, out / "shot_detect.joblib")
    np.savez_compressed(out / "shot_scores.npz", t=res.pop("t"), score=res.pop("score"))
    (out / "shot_detect.json").write_text(json.dumps({k: v for k, v in res.items() if k != "features"},
                                                      ensure_ascii=False, indent=1))
    print(write_report(res, out, args.title or doc.get("nev", "")).read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
