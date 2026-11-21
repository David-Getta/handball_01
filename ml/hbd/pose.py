"""Testpont-kinyerés: minden klip végrehajtójára 17 COCO-testpont kockánként.

Folyamat klipenként:
  1. a kivágott klip megkeresése a jelenetben (`locate`) → a végrehajtó doboza,
  2. a doboz körül négyzetes, MARGÓS kivágás a teljes felbontású jelenetből
     (a pózmodellnek kell a környezet; a klip maga szorosan vágott),
  3. előtanított YOLO-pose (Ultralytics) a kivágásokon, kötegben,
  4. a kivágáson talált emberek közül az, amelyik a végrehajtó dobozával a
     legjobban fed (több ember is lehet a kivágásban),
  5. a testpontok visszaszámolása a jelenet képkoordinátáiba.

Kimenet: egyetlen tömör .npz (néhány MB) — erre épül minden tanítás.
Megszakítás után folytatható: klipenként gyorsítótár-fájl készül.

Futtatás (Kaggle GPU-n):
    python -m hbd.pose --data /kaggle/input/uniri-hbd --out /kaggle/working/poses.npz --device 0
Gyors próba CPU-n:
    python -m hbd.pose --data ./handball_s --out poses.npz --limit 5 --weights yolo11n-pose.pt
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

from .dataset import Clip, index_dataset
from .locate import find_offset, track
from .video import iter_frames, probe, read_frames

KP_COUNT = 17
# A pózkivágás oldala = a végrehajtó dobozának hosszabbik oldala × ennyi.
CROP_SCALE = 1.6
# A pózmodell bemeneti mérete (a ~110 px-es játékost erre nagyítjuk).
POSE_IMGSZ = 384
# Ennél kisebb fedés (IoU) a végrehajtó dobozával → nem őt találta a modell.
MIN_PICK_IOU = 0.15
# Alapértelmezett súlyok: GPU-n a legpontosabb, CPU-n a legkisebb.
DEFAULT_WEIGHTS_GPU = "yolo11x-pose.pt"
DEFAULT_WEIGHTS_CPU = "yolo11n-pose.pt"

# COCO-csontváz a rajzoláshoz
SKELETON = [(5, 7), (7, 9), (6, 8), (8, 10), (5, 6), (5, 11), (6, 12), (11, 12),
            (11, 13), (13, 15), (12, 14), (14, 16), (0, 5), (0, 6)]


def square_crop_box(box, frame_w: int, frame_h: int, scale: float = CROP_SCALE):
    """Négyzetes kivágó-ablak a doboz közepe körül, a képre szorítva: (x0, y0, x1, y1)."""
    x1, y1, x2, y2 = box
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    side = max(x2 - x1, y2 - y1) * scale
    x0 = int(round(max(0, cx - side / 2)))
    y0 = int(round(max(0, cy - side / 2)))
    xe = int(round(min(frame_w, cx + side / 2)))
    ye = int(round(min(frame_h, cy + side / 2)))
    return x0, y0, xe, ye


def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0.0


def pick_person(det_boxes: np.ndarray, target_box) -> int | None:
    """A végrehajtó dobozával legjobban fedő észlelés indexe (vagy None)."""
    if len(det_boxes) == 0:
        return None
    scores = [iou(b, target_box) for b in det_boxes]
    j = int(np.argmax(scores))
    return j if scores[j] >= MIN_PICK_IOU else None


class PoseModel:
    """Vékony burok az Ultralytics YOLO-pose köré (lusta import)."""

    def __init__(self, weights: str, device: str | None = None, imgsz: int = POSE_IMGSZ,
                 batch: int = 32):
        from ultralytics import YOLO  # lusta: a tesztekhez nem kell

        self.model = YOLO(weights)
        self.device = device
        self.imgsz = imgsz
        self.batch = batch

    def __call__(self, crops: list[np.ndarray]) -> list[tuple[np.ndarray, np.ndarray]]:
        """Kivágásonként: (dobozok (n, 4), testpontok (n, 17, 3)) a kivágás koordinátáiban."""
        out = []
        for i in range(0, len(crops), self.batch):
            res = self.model.predict(crops[i:i + self.batch], imgsz=self.imgsz,
                                     device=self.device, verbose=False, conf=0.1)
            for r in res:
                if r.keypoints is None or len(r.boxes) == 0:
                    out.append((np.zeros((0, 4), np.float32), np.zeros((0, KP_COUNT, 3), np.float32)))
                    continue
                boxes = r.boxes.xyxy.cpu().numpy().astype(np.float32)
                xy = r.keypoints.xy.cpu().numpy()
                conf = r.keypoints.conf
                conf = conf.cpu().numpy() if conf is not None else np.ones(xy.shape[:2])
                out.append((boxes, np.concatenate([xy, conf[..., None]], -1).astype(np.float32)))
        return out


def extract_clip(clip: Clip, model) -> dict:
    """Egy klip végrehajtójának testpont-sorozata a jelenet koordinátáiban."""
    action = read_frames(clip.action_path, gray=True)
    w, h, fps = probe(clip.scene_path)
    offset, off_score = find_offset(iter_frames(clip.scene_path, gray=True), action[0])

    crops, origins, boxes, scores = [], [], [], []
    for _k, frame, box, score in track(iter_frames(clip.scene_path), action, offset):
        x0, y0, x1, y1 = square_crop_box(box, w, h)
        crops.append(np.ascontiguousarray(frame[y0:y1, x0:x1]))
        origins.append((x0, y0))
        boxes.append(box)
        scores.append(score)

    T = len(crops)
    kps = np.zeros((T, KP_COUNT, 3), np.float32)
    if T:
        for t, (det_boxes, det_kps) in enumerate(model(crops)):
            ox, oy = origins[t]
            tb = boxes[t]
            local_target = (tb[0] - ox, tb[1] - oy, tb[2] - ox, tb[3] - oy)
            j = pick_person(det_boxes, local_target)
            if j is not None:
                kps[t] = det_kps[j]
                kps[t, :, 0] += ox
                kps[t, :, 1] += oy
    return {
        "kps": kps,
        "boxes": np.asarray(boxes, np.float32).reshape(T, 4),
        "match": np.asarray(scores, np.float32),
        "offset": offset,
        "offset_score": off_score,
        "fps": fps,
        "frame_size": (w, h),
        "action_len": len(action),
        "crops_preview": crops[T // 2] if T else None,
    }


def save_dataset(path: Path, clips: list[Clip], results: list[dict]) -> None:
    """Az összes klip egy tömör .npz-ben (pickle nélkül)."""
    lens = [len(r["kps"]) for r in results]
    offsets = np.concatenate([[0], np.cumsum(lens)]).astype(np.int64)
    np.savez_compressed(
        path,
        names=np.array([c.name for c in clips]),
        categories=np.array([c.category for c in clips]),
        scene_ids=np.array([c.scene_id for c in clips]),
        offsets=offsets,
        kps=np.concatenate([r["kps"] for r in results]) if results else np.zeros((0, KP_COUNT, 3)),
        boxes=np.concatenate([r["boxes"] for r in results]) if results else np.zeros((0, 4)),
        match=np.concatenate([r["match"] for r in results]) if results else np.zeros(0),
        fps=np.array([r["fps"] for r in results], np.float32),
        frame_size=np.array([r["frame_size"] for r in results], np.int32).reshape(-1, 2),
    )


def load_dataset(path: str | Path) -> dict:
    """Az .npz visszaolvasása klip-listává: [{name, category, scene_id, kps, boxes, fps}]."""
    z = np.load(path)
    off = z["offsets"]
    clips = []
    for i, name in enumerate(z["names"]):
        a, b = off[i], off[i + 1]
        clips.append({
            "name": str(name),
            "category": str(z["categories"][i]),
            "scene_id": str(z["scene_ids"][i]),
            "kps": z["kps"][a:b],
            "boxes": z["boxes"][a:b],
            "match": z["match"][a:b],
            "fps": float(z["fps"][i]) or 30.0,
        })
    return {"clips": clips}


def draw_pose(img: np.ndarray, kps: np.ndarray, min_conf: float = 0.3) -> np.ndarray:
    import cv2

    out = img.copy()
    for a, b in SKELETON:
        if kps[a, 2] >= min_conf and kps[b, 2] >= min_conf:
            cv2.line(out, tuple(int(v) for v in kps[a, :2]), tuple(int(v) for v in kps[b, :2]),
                     (0, 255, 255), 1, cv2.LINE_AA)
    for j, (x, y, c) in enumerate(kps):
        if c >= min_conf:
            col = (0, 0, 255) if j in (9, 10) else (0, 255, 0)  # csukló piros
            cv2.circle(out, (int(x), int(y)), 2, col, -1, cv2.LINE_AA)
    return out


def _preview_tile(clip: Clip, res: dict, size: int = 200) -> np.ndarray | None:
    import cv2

    T = len(res["kps"])
    if T == 0:
        return None
    t = T // 2
    crop = res["crops_preview"]
    w, h = res["frame_size"]
    x0, y0, _, _ = square_crop_box(res["boxes"][t], w, h)
    k = res["kps"][t].copy()
    k[:, 0] -= x0
    k[:, 1] -= y0
    sc = size / max(crop.shape[:2])
    img = cv2.resize(crop, None, fx=sc, fy=sc, interpolation=cv2.INTER_CUBIC)
    k[:, :2] *= sc
    img = draw_pose(img, k)
    tile = np.zeros((size + 18, size, 3), np.uint8)
    tile[:img.shape[0], :img.shape[1]] = img
    cv2.putText(tile, clip.name[:28], (2, size + 13), cv2.FONT_HERSHEY_SIMPLEX, 0.33,
                (255, 255, 255), 1, cv2.LINE_AA)
    return tile


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="UNIRI-HBD: testpont-kinyerés a végrehajtóra")
    ap.add_argument("--data", required=True, help="az adathalmaz (vagy egy szülő mappája)")
    ap.add_argument("--out", required=True, help="kimeneti .npz")
    ap.add_argument("--weights", default=None, help="YOLO-pose súlyok (alap: GPU-n x, CPU-n n)")
    ap.add_argument("--device", default=None, help="pl. 0 (GPU) vagy cpu")
    ap.add_argument("--imgsz", type=int, default=POSE_IMGSZ)
    ap.add_argument("--batch", type=int, default=32)
    ap.add_argument("--limit", type=int, default=0, help="csak az első N klip kategóriánként")
    ap.add_argument("--categories", default="", help="vesszővel, pl. shot,jump-shot")
    ap.add_argument("--preview", type=int, default=0, help="ennyi ellenőrző kép kategóriánként")
    args = ap.parse_args(argv)

    cats = tuple(c for c in args.categories.split(",") if c) or None
    clips = index_dataset(args.data, cats)
    if args.limit:
        per: dict[str, int] = {}
        kept = []
        for c in clips:
            per[c.category] = per.get(c.category, 0) + 1
            if per[c.category] <= args.limit:
                kept.append(c)
        clips = kept

    weights = args.weights
    if weights is None:
        try:
            import torch

            gpu = torch.cuda.is_available() and args.device != "cpu"
        except ImportError:
            gpu = False
        weights = DEFAULT_WEIGHTS_GPU if gpu else DEFAULT_WEIGHTS_CPU
    model = PoseModel(weights, device=args.device, imgsz=args.imgsz, batch=args.batch)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cache = out.parent / (out.stem + "_cache")
    cache.mkdir(exist_ok=True)

    results, done_clips, tiles = [], [], {}
    t0 = time.time()
    for i, clip in enumerate(clips):
        cf = cache / f"{clip.category}__{clip.name}.npz"
        want_tile = len(tiles.get(clip.category, [])) < args.preview
        if cf.exists() and not want_tile:
            z = np.load(cf)
            res = {k: z[k] for k in ("kps", "boxes", "match")}
            res.update(fps=float(z["fps"]), frame_size=tuple(z["frame_size"]))
        else:
            try:
                res = extract_clip(clip, model)
            except Exception as e:  # egy hibás videó ne vigye el a futást
                print(f"  ! {clip.name}: {e}", file=sys.stderr)
                continue
            np.savez_compressed(cf, kps=res["kps"], boxes=res["boxes"], match=res["match"],
                                fps=res["fps"], frame_size=np.array(res["frame_size"]))
            if want_tile:
                tile = _preview_tile(clip, res)
                if tile is not None:
                    tiles.setdefault(clip.category, []).append(tile)
        results.append(res)
        done_clips.append(clip)
        if (i + 1) % 25 == 0 or i + 1 == len(clips):
            el = time.time() - t0
            print(f"  {i + 1}/{len(clips)} klip, {el:.0f} s (≈{el / (i + 1):.1f} s/klip)", flush=True)

    save_dataset(out, done_clips, results)
    total = sum(len(r["kps"]) for r in results)
    seen = sum(int((r["kps"][:, :, 2].max(1) > 0).sum()) for r in results)
    low = sum(int((r["match"] < 0.9).sum()) for r in results)
    print(f"Kész: {len(done_clips)} klip, {total} kocka → {out}")
    print(f"  pózt talált a kockák {100 * seen / max(1, total):.1f}%-án; "
          f"gyenge klip-egyezés (<0,9): {low} kocka")

    if tiles:
        import cv2

        rows = []
        width = max(len(v) for v in tiles.values())
        for cat in sorted(tiles):
            row = tiles[cat] + [np.zeros_like(tiles[cat][0])] * (width - len(tiles[cat]))
            rows.append(np.hstack(row))
        pv = out.parent / (out.stem + "_preview.jpg")
        cv2.imwrite(str(pv), np.vstack(rows))
        print(f"  ellenőrző kép: {pv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
