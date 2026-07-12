"""
Tanítóadat-gyűjtő CLI — YOLO-adathalmaz a saját meccsvideókból.

A jelenlegi detektor előcímkéivel (bootstrap) mintavételez képkockákat, a
kimenet szabványos YOLO-mappaszerkezet (images/labels + dataset.yaml), amit
címkéző eszközben (CVAT, LabelImg) lehet átnézni/javítani, majd a
scripts/finetune.py tanít belőle. Teljes útmutató: docs/FINETUNE.md.

Használat:
    python -m scripts.collect_dataset MECCS1.mp4 [MECCS2.mp4 ...] \
        --out dataset --samples 200 [--weights yolov8n.pt] [--start 0]

Több videó ugyanabba a --out mappába gyűjthető — az adathalmaz együtt nő.
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.pipeline.dataset import collect_dataset  # noqa: E402
from scripts.process_video import _class_ids, _pick_device, _resolve_weights  # noqa: E402


def _make_detect_fn(weights: str, imgsz: int, person_conf: float,
                    ball_conf: float):
    """YOLO-alapú detect_fn a collect_dataset-hez (nevekre képezve)."""
    from ultralytics import YOLO
    model = YOLO(_resolve_weights(weights))
    person_ids, ball_ids = _class_ids(getattr(model, "names", None))
    device = _pick_device()

    def detect(img):
        out = []
        results = model.predict(img, imgsz=imgsz,
                                conf=min(person_conf, ball_conf),
                                classes=person_ids + ball_ids, device=device,
                                verbose=False)
        for r in results:
            if r.boxes is None:
                continue
            for b in r.boxes:
                cls = int(b.cls[0])
                bc = float(b.conf[0])
                x1, y1, x2, y2 = [float(v) for v in b.xyxy[0].tolist()]
                if cls in person_ids and bc >= person_conf:
                    out.append(("person", bc, x1, y1, x2, y2))
                elif cls in ball_ids and bc >= ball_conf:
                    out.append(("ball", bc, x1, y1, x2, y2))
        return out

    return detect


def main() -> int:
    ap = argparse.ArgumentParser(
        description="YOLO tanítóadat-gyűjtés meccsvideóból")
    ap.add_argument("videos", nargs="+", help="meccsvideó(k)")
    ap.add_argument("--out", default="dataset", help="kimeneti mappa")
    ap.add_argument("--samples", type=int, default=200,
                    help="mintavételezett kockák videónként (alap: 200)")
    ap.add_argument("--start", type=int, default=0,
                    help="ettől a kép-indextől mintavételezünk (bevezető átugrása)")
    ap.add_argument("--weights", default="yolov8n.pt",
                    help="az előcímkéző modell (alap: yolov8n.pt)")
    ap.add_argument("--imgsz", type=int, default=1920,
                    help="inferencia-felbontás (alap: 1920 — a kis labdához)")
    ap.add_argument("--person-conf", type=float, default=0.35)
    ap.add_argument("--ball-conf", type=float, default=0.05)
    args = ap.parse_args()

    detect = _make_detect_fn(args.weights, args.imgsz, args.person_conf,
                             args.ball_conf)
    total_images = 0
    for video in args.videos:
        print(f"gyűjtés: {video}")
        stats = collect_dataset(video, detect, args.out,
                                samples=args.samples, start=args.start)
        total_images += stats.images
        print(f"  {stats.images} kép ({stats.train_images} train / "
              f"{stats.val_images} val) · {stats.person_boxes} játékos-doboz · "
              f"{stats.ball_boxes} labda-doboz · labda a képek "
              f"{100 * stats.images_with_ball / max(1, stats.images):.0f}%-án")
        for n in stats.notes:
            print(f"  FIGYELEM: {n}")
    print(f"\nKész: {total_images} kép a(z) {args.out} mappában.")
    print("Következő lépés: nézd át/javítsd a címkéket (CVAT/LabelImg), majd:")
    print(f"  python -m scripts.finetune --data {args.out}/dataset.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
