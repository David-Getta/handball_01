"""Labdafelismerő a közvetítésen: tanítás a labdajelölő kattintásaiból.

A kész (COCO "sports ball") felismerők a közvetítésen nem találják a labdát:
az elengedésnél 10–25 px-es és elmosódott. Itt egy kis YOLO11 detektort
tanítunk a labdajelölő pontjain (klipenként kézben / elválik / repül).

Adat:
  - a jelölt kocka a labdajelölő éles, lövő köré vágott videójából (640 px, 1:1
    az eredeti 1080p-hez);
  - a labda doboza: középpont = a kattintás, átmérő = BALL_REL × a lövő
    doboz-magassága (kézilabda Ø 19 cm, játékos ~1,9 m), BALL_PX korlátok közt;
  - tanító képek: TILE-os kivágások, POS_PER_POINT olyan, amin a labda rajta van
    (véletlen helyen), és NEG_PER_POINT olyan, amin nincs (egy pályán egy labda
    van → ez biztos "nincs labda" példa).

Kiértékelés: a lövések (csoportok: élő + ismétlése együtt) HOLDOUT része
kimarad a tanításból; azokon a teljes 640-es kivágáson fut a felismerő, és
mérjük: a legbiztosabb jelölt a valódi labdától legfeljebb HIT_X × átmérőre
van-e.

    python -m hbd.ball build --ball-dir m1ball2 --labels cimkek/meccs1_labda_cimkek.json --zoom m1_zoom --out balldata
    python -m hbd.ball train --data balldata --epochs 40
    python -m hbd.ball evaluate --data balldata --weights runs/.../best.pt
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import numpy as np

BALL_REL = 0.10
BALL_PX = (8, 40)
TILE = 320
POS_PER_POINT = 3
NEG_PER_POINT = 1
HOLDOUT = 0.2
HIT_X = 1.5
SEED = 0


def read_video_frames(path: Path) -> list[np.ndarray]:
    """Minden kocka (BGR) egy rövid videóból."""
    from .video import iter_frames

    return list(iter_frames(path))


def ball_size(zoom: dict | None, local_k: int, default: float = 20.0) -> float:
    """A labda becsült átmérője px-ben a lövő dobozmagasságából (a ráközelítő követésből)."""
    if zoom is None or bool(zoom["lost"]):
        return default
    t = int(np.clip(local_k - int(zoom["start"]), 0, len(zoom["boxes"]) - 1))
    b = zoom["boxes"][t]
    return float(np.clip(BALL_REL * (b[3] - b[1]), *BALL_PX))


def split_groups(ids: list[str], groups: dict[str, str]) -> set[str]:
    """A kiértékelésre félretett klipek (csoportonként, determinisztikusan)."""
    gs = sorted({groups[i] for i in ids})
    rng = random.Random(SEED)
    rng.shuffle(gs)
    held = set(gs[:int(round(HOLDOUT * len(gs)))])
    return {i for i in ids if groups[i] in held}


def _tile_with(rng, cx, cy, size, W, H):
    x0 = int(np.clip(rng.uniform(cx - TILE + size, cx - size), 0, W - TILE))
    y0 = int(np.clip(rng.uniform(cy - TILE + size, cy - size), 0, H - TILE))
    return x0, y0


def _tile_without(rng, cx, cy, size, W, H, tries=50):
    for _ in range(tries):
        x0, y0 = rng.randint(0, W - TILE), rng.randint(0, H - TILE)
        if not (x0 - size <= cx <= x0 + TILE + size and y0 - size <= cy <= y0 + TILE + size):
            return x0, y0
    return None


def build(ball_dir: Path, labels: Path, zoom_dir: Path | None, clips_manifest: Path, out: Path) -> dict:
    """YOLO-formátumú adathalmaz (images/labels train+val) + a kiértékelő pontok listája."""
    import cv2

    from .match_shots import replay_groups

    man = {c["id"]: c for c in json.loads((ball_dir / "ball_manifest.json").read_text())["klipek"]}
    groups = replay_groups(json.loads(clips_manifest.read_text())["clips"])
    L = {d["klip"]: d for d in json.loads(labels.read_text())["cimkek"]}
    ids = sorted(i for i in L if i in man)
    held = split_groups(ids, groups)
    for sub in ("images/train", "labels/train", "images/val", "labels/val", "full"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    evalpts, n_tr = [], 0
    for cid in ids:
        m = man[cid]
        frames = read_video_frames(ball_dir / m["src"])
        zf = (zoom_dir / f"{cid}.npz") if zoom_dir else None
        z = np.load(zf) if zf is not None and zf.exists() else None
        # a zoom kimenet kockái a lövés-klip k0-jához mérve; a labdavideó saját k0-ja más
        for p in L[cid]["pontok"]:
            if p.get("nincs"):
                continue
            f = p["k"] - m["k0"]
            if not 0 <= f < len(frames):
                continue
            img = frames[f]
            H, W = img.shape[:2]
            cx, cy = p["cx"] * W, p["cy"] * H
            zk = p["k"] - int(z["k0"]) if z is not None else 0
            size = ball_size(z, zk)
            name = f"{cid}_{p['nev']}"
            if cid in held:
                cv2.imwrite(str(out / "full" / f"{name}.jpg"), img)
                evalpts.append({"klip": cid, "nev": p["nev"], "kep": f"full/{name}.jpg", "x": cx, "y": cy, "d": size})
                split = "val"
                reps = 1
            else:
                split = "train"
                reps = POS_PER_POINT
            for r in range(reps):
                x0, y0 = _tile_with(rng, cx, cy, size, W, H)
                tile = img[y0:y0 + TILE, x0:x0 + TILE]
                stem = f"{name}_p{r}"
                cv2.imwrite(str(out / f"images/{split}/{stem}.jpg"), tile)
                (out / f"labels/{split}/{stem}.txt").write_text(
                    f"0 {(cx - x0) / TILE:.5f} {(cy - y0) / TILE:.5f} {size / TILE:.5f} {size / TILE:.5f}\n")
                n_tr += split == "train"
            for r in range(NEG_PER_POINT if split == "train" else 0):
                pos = _tile_without(rng, cx, cy, size, W, H)
                if pos is None:
                    continue
                x0, y0 = pos
                stem = f"{name}_n{r}"
                cv2.imwrite(str(out / f"images/{split}/{stem}.jpg"), img[y0:y0 + TILE, x0:x0 + TILE])
                (out / f"labels/{split}/{stem}.txt").write_text("")
    (out / "data.yaml").write_text(f"path: {out.resolve()}\ntrain: images/train\nval: images/val\nnames:\n  0: labda\n")
    (out / "eval_points.json").write_text(json.dumps(evalpts))
    info = {"klipek": len(ids), "kiertekelo_klipek": len(held), "tanito_kepek": n_tr, "kiertekelo_pontok": len(evalpts)}
    (out / "info.json").write_text(json.dumps(info))
    return info


def evaluate(data: Path, weights: str, imgsz: int = 640, conf: float = 0.01) -> dict:
    """A félretett lövések teljes kivágásain: eltalálja-e a labdát (a legbiztosabb jelölt)."""
    from ultralytics import YOLO

    model = YOLO(weights)
    pts = json.loads((data / "eval_points.json").read_text())
    by = {}
    for p in pts:
        r = model.predict(str(data / p["kep"]), imgsz=imgsz, conf=conf, verbose=False)[0]
        b = r.boxes.xyxy.cpu().numpy()
        c = r.boxes.conf.cpu().numpy()
        hit, top = False, None
        if len(b):
            j = int(np.argmax(c))
            bx, by_ = (b[j, 0] + b[j, 2]) / 2, (b[j, 1] + b[j, 3]) / 2
            top = float(c[j])
            hit = float(np.hypot(bx - p["x"], by_ - p["y"])) <= HIT_X * p["d"]
        by.setdefault(p["nev"], []).append((hit, top))
    out = {}
    for nev, v in by.items():
        hits = np.array([h for h, _ in v])
        out[nev] = {"pontok": len(v), "talalat": float(hits.mean())}
    allh = np.array([h for v in by.values() for h, _ in v])
    out["osszes"] = {"pontok": int(len(allh)), "talalat": float(allh.mean())}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Labdafelismerő a közvetítésen")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--ball-dir", required=True, help="a make_ball_frames kimenete (ball_manifest.json + videók)")
    b.add_argument("--labels", required=True)
    b.add_argument("--clips", required=True, help="a lövés-klipek manifest.json-ja (csoportokhoz)")
    b.add_argument("--zoom", help="a match_shots zoom kimenete (a labda méretéhez)")
    b.add_argument("--out", required=True)
    t = sub.add_parser("train")
    t.add_argument("--data", required=True)
    t.add_argument("--weights", default="yolo11n.pt")
    t.add_argument("--epochs", type=int, default=40)
    t.add_argument("--device", default="cpu")
    t.add_argument("--project", default="runs_ball")
    e = sub.add_parser("evaluate")
    e.add_argument("--data", required=True)
    e.add_argument("--weights", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "build":
        info = build(Path(args.ball_dir), Path(args.labels), Path(args.zoom) if args.zoom else None,
                     Path(args.clips), Path(args.out))
        print(info)
    elif args.cmd == "train":
        from ultralytics import YOLO

        YOLO(args.weights).train(data=str(Path(args.data) / "data.yaml"), imgsz=TILE, epochs=args.epochs,
                                 device=args.device, batch=16, project=args.project, name="labda", exist_ok=True,
                                 mosaic=0.5, fliplr=0.5, degrees=0, scale=0.3, workers=2, patience=15, verbose=False)
    else:
        print(json.dumps(evaluate(Path(args.data), args.weights), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
