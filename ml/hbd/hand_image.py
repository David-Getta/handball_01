"""Lövőkéz a KÉPBŐL, testpontok nélkül.

A testpontokból a lövőkéz a közvetítésen nem jön ki megbízhatóan: még a kézzel
bejelölt labdával is csak 71%-os a "melyik csuklóhoz van közelebb" szabály
(a kicsi, elmosódott csuklót a pózbecslő gyakran rossz helyre teszi). Itt a
lövőt a "kézben" kockán (a labdajelölő címkéje) kivágjuk, és egy előtanított
képosztályozó (YOLO11-cls, ImageNet) jellemző-vektorán logisztikus regresszió
dönt: bal vagy jobb kéz.

Tükrözés: a vízszintesen tükrözött képen a bal kezes lövésből jobb kezes lesz,
így a tanító minták száma kétszeres, a jóslás pedig a kép és tükörképe
átlaga (p(kép) + 1 − p(tükör)) / 2 — a modell így nem tanulhat "oldal-előítéletet".

Kiértékelés: csoportosított keresztvalidáció (az ismétlés az élő párjával egy
csoportban).

    python -m hbd.hand_image --video meccs.mp4 --clips m1web/manifest.json --zoom m1_zoom \
        --labels cimkek/meccs1_lovesek_cimkek.json --ball cimkek/meccs1_labda_cimkek.json --out res/
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

# A kivágás oldala a lövő dobozának hosszabbik oldalához képest.
CROP_X = 1.4
INPUT = 224
FOLDS = 5


def crops_for(video: str, clip: dict, zoom: dict, ks: list[int]) -> list[np.ndarray]:
    """A lövő négyzetes kivágásai a megadott klip-kockákon (az eredeti felvételből)."""
    import cv2

    from .match_shots import _orig_frames

    fps = clip["fps"]
    k0, st = int(zoom["k0"]), int(zoom["start"])
    out = []
    for k in ks:
        t = int(np.clip(k - k0 - st, 0, len(zoom["boxes"]) - 1))
        img = _orig_frames(video, clip["t_start"] + k / fps, 1)[0]
        h, w = img.shape[:2]
        x0, y0, x1, y1 = zoom["boxes"][t]
        cx, cy, side = (x0 + x1) / 2, (y0 + y1) / 2, CROP_X * max(x1 - x0, y1 - y0)
        a, b = int(max(0, cx - side / 2)), int(max(0, cy - side / 2))
        crop = img[b:int(min(h, cy + side / 2)), a:int(min(w, cx + side / 2))]
        out.append(cv2.resize(crop, (INPUT, INPUT), interpolation=cv2.INTER_AREA))
    return out


def embed(model, imgs: list[np.ndarray]) -> np.ndarray:
    return np.stack([e.cpu().numpy().ravel() for e in model.embed(imgs, imgsz=INPUT, verbose=False)])


def evaluate(X: np.ndarray, Xf: np.ndarray, y: np.ndarray, groups: np.ndarray, C: float = 0.1) -> dict:
    """X: kép-jellemzők, Xf: a tükörképeké, y: 1 = bal kéz. Csoportosított CV, tükör-átlagolt jóslás."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import balanced_accuracy_score
    from sklearn.model_selection import GroupKFold
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    p = np.zeros(len(y))
    for tr, te in GroupKFold(FOLDS).split(X, y, groups):
        clf = make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=3000))
        clf.fit(np.concatenate([X[tr], Xf[tr]]), np.concatenate([y[tr], 1 - y[tr]]))
        p[te] = (clf.predict_proba(X[te])[:, 1] + 1 - clf.predict_proba(Xf[te])[:, 1]) / 2
    pred = (p > 0.5).astype(int)
    conf = np.abs(p - 0.5) * 2
    sure = conf >= np.median(conf)
    return {"klipek": int(len(y)), "pontossag": float((pred == y).mean()),
            "kiegyensulyozott": float(balanced_accuracy_score(y, pred)),
            "biztosabb_fele_pontossag": float((pred[sure] == y[sure]).mean()),
            "mindig_jobb": float((y == 0).mean())}


def main(argv=None) -> int:
    from ultralytics import YOLO

    from .match_shots import replay_groups

    ap = argparse.ArgumentParser(description="Lövőkéz a képből")
    ap.add_argument("--video", required=True)
    ap.add_argument("--clips", required=True)
    ap.add_argument("--zoom", required=True, help="a match_shots zoom kimenete (a lövő dobozai)")
    ap.add_argument("--labels", required=True)
    ap.add_argument("--ball", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--weights", default="yolo11m-cls.pt")
    args = ap.parse_args(argv)
    man = json.loads(Path(args.clips).read_text())["clips"]
    clips = {c["id"]: c for c in man}
    groups_of = replay_groups(man)
    hands = {d["klip"]: d.get("lovokez") for d in json.loads(Path(args.labels).read_text())["cimkek"]}
    balls = {d["klip"]: {p["nev"]: p for p in d["pontok"]} for d in json.loads(Path(args.ball).read_text())["cimkek"]}
    model = YOLO(args.weights)
    rows = []
    for cid, pts in sorted(balls.items()):
        if hands.get(cid) not in ("jobb", "bal") or cid not in clips:
            continue
        zf = Path(args.zoom) / f"{cid}.npz"
        if not zf.exists():
            continue
        z = np.load(zf)
        if bool(z["lost"]) or pts["kezben"].get("nincs"):
            continue
        im = crops_for(args.video, clips[cid], z, [pts["kezben"]["k"]])[0]
        rows.append((cid, im, int(hands[cid] == "bal")))
    imgs = [r[1] for r in rows]
    X = embed(model, imgs)
    Xf = embed(model, [im[:, ::-1].copy() for im in imgs])
    y = np.array([r[2] for r in rows])
    groups = np.array([groups_of[r[0]] for r in rows])
    res = {c: evaluate(X, Xf, y, groups, c) for c in (0.01, 0.1, 1.0)}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "hand_image.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    np.savez_compressed(out / "hand_image_features.npz", X=X, Xf=Xf, y=y, groups=groups,
                        ids=np.array([r[0] for r in rows]))
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
