"""Teljes meccs: minden (ritkított) kockán az összes ember testpontja.

A lövésfelismerőnek a meccs minden pillanatáról kell tudnia, mi látszik:
hány ember van a képen, felemelt dobókar van-e valakinél, mozog-e a kamera.
Ez a modul egy meccsfelvételből kockánként (STRIDE-onként) lefuttatja a
YOLO-pose-t a teljes képen, és tömören elmenti:

  t        — a kocka ideje (s)
  boxes    — emberek dobozai (n, 4), a kép szélességével/magasságával osztva (0..1)
  kps      — testpontok (n, 17, 3): x, y (0..1), megbízhatóság
  motion   — a kép változása az előző mintához képest (kamera-mozgás / vágás jelző)

Követés (ki kicsoda a kockák között) NINCS benne: ritkított mintán a
kézilabda gyors mozgásánál megbízhatatlan. A lövésfelismerő első változata
kocka-szintű összesítésekkel dolgozik; a követéses változat GPU-n, teljes
kockaszámmal futhat (ugyanezzel a modullal, --stride 1).

Megszakítás után folytatható (darabonkénti gyorsítótár).

    python -m hbd.match_pose --video meccs.mp4 --out meccs_pose.npz --stride 5 --imgsz 1280
"""

from __future__ import annotations

import argparse
import subprocess
import time
from pathlib import Path

import numpy as np

from .video import ffmpeg_exe, probe

# Széles (közvetítési) képen a kicsi, távoli játékosokhoz nagy bemenet kell:
# 640-en ~3, 960-on ~7, 1280-on ~18 embert talál ugyanazon a kockán.
DEFAULT_IMGSZ = 1280
DEFAULT_STRIDE = 5
CHUNK = 1500          # ennyi mintakocka kerül egy gyorsítótár-darabba
MOTION_SIZE = (64, 36)  # a kamera-mozgás jelzőhöz kicsinyített szürke kép


def iter_sampled(video: str, stride: int, w: int, h: int, start_frame: int = 0):
    """(kocka-index, BGR kép) minden stride-adik kockára, a start_frame-től."""
    fps = probe(video)[2] or 25.0
    ss = start_frame / fps
    cmd = [ffmpeg_exe(), "-v", "error"]
    if ss > 0:
        cmd += ["-ss", f"{ss:.3f}"]
    cmd += ["-i", video, "-vf", f"select='not(mod(n\\,{stride}))'", "-vsync", "0",
            "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    size = w * h * 3
    k = 0
    try:
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            yield start_frame + k * stride, np.frombuffer(buf, np.uint8).reshape(h, w, 3)
            k += 1
    finally:
        proc.stdout.close()
        proc.kill()
        proc.wait()


def run(video: str, out: Path, stride: int, imgsz: int, weights: str, device: str | None,
        batch: int = 8, conf: float = 0.1) -> Path:
    import cv2
    from ultralytics import YOLO

    w, h, fps = probe(video)
    fps = fps or 25.0
    cache = out.parent / (out.stem + "_cache")
    cache.mkdir(parents=True, exist_ok=True)
    model = YOLO(weights)
    done = sorted(cache.glob("chunk_*.npz"))
    start_frame = 0
    if done:
        last = np.load(done[-1])
        start_frame = int(last["frame"][-1]) + stride
    print(f"{video}: {w}x{h} @ {fps:.2f} fps; minta minden {stride}. kocka; indulás: {start_frame}", flush=True)

    buf_frames, buf_idx = [], []
    rec = {"frame": [], "n": [], "boxes": [], "kps": [], "motion": []}
    prev_small = None
    t0 = time.time()
    chunk_id = len(done)

    def flush_batch():
        nonlocal prev_small
        res = model.predict(buf_frames, imgsz=imgsz, conf=conf, device=device, verbose=False)
        for fi, img, r in zip(buf_idx, buf_frames, res):
            small = cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), MOTION_SIZE).astype(np.float32)
            mot = float(np.abs(small - prev_small).mean()) if prev_small is not None else 0.0
            prev_small = small
            if r.keypoints is not None and len(r.boxes):
                b = r.boxes.xyxy.cpu().numpy() / [w, h, w, h]
                xy = r.keypoints.xy.cpu().numpy() / [w, h]
                kc = r.keypoints.conf
                kc = kc.cpu().numpy() if kc is not None else np.ones(xy.shape[:2])
                k = np.concatenate([xy, kc[..., None]], -1)
            else:
                b, k = np.zeros((0, 4)), np.zeros((0, 17, 3))
            rec["frame"].append(fi)
            rec["n"].append(len(b))
            rec["boxes"].append(b.astype(np.float16))
            rec["kps"].append(k.astype(np.float16))
            rec["motion"].append(mot)
        buf_frames.clear()
        buf_idx.clear()

    def save_chunk():
        nonlocal chunk_id
        if not rec["frame"]:
            return
        np.savez_compressed(
            cache / f"chunk_{chunk_id:04d}.npz",
            frame=np.array(rec["frame"], np.int64), n=np.array(rec["n"], np.int32),
            boxes=np.concatenate(rec["boxes"]) if sum(rec["n"]) else np.zeros((0, 4), np.float16),
            kps=np.concatenate(rec["kps"]) if sum(rec["n"]) else np.zeros((0, 17, 3), np.float16),
            motion=np.array(rec["motion"], np.float32))
        chunk_id += 1
        for v in rec.values():
            v.clear()

    count = 0
    for fi, img in iter_sampled(video, stride, w, h, start_frame):
        buf_frames.append(img)
        buf_idx.append(fi)
        if len(buf_frames) == batch:
            flush_batch()
        count += 1
        if len(rec["frame"]) >= CHUNK:
            save_chunk()
            el = time.time() - t0
            print(f"  {fi / fps / 60:5.1f}. perc · {count} minta · {el / count * 1000:.0f} ms/minta", flush=True)
    if buf_frames:
        flush_batch()
    save_chunk()
    return combine(cache, out, fps, stride, (w, h))


def combine(cache: Path, out: Path, fps: float, stride: int, size) -> Path:
    parts = [np.load(f) for f in sorted(cache.glob("chunk_*.npz"))]
    n = np.concatenate([p["n"] for p in parts])
    np.savez_compressed(
        out, frame=np.concatenate([p["frame"] for p in parts]), n=n,
        offsets=np.concatenate([[0], np.cumsum(n)]).astype(np.int64),
        boxes=np.concatenate([p["boxes"] for p in parts]), kps=np.concatenate([p["kps"] for p in parts]),
        motion=np.concatenate([p["motion"] for p in parts]), fps=np.float32(fps), stride=np.int32(stride),
        size=np.array(size, np.int32))
    print(f"Kész: {len(n)} mintakocka, átlag {n.mean():.1f} ember/kocka → {out}")
    return out


def load(path: str | Path) -> dict:
    z = np.load(path)
    d = {k: z[k] for k in z.files}
    d["t"] = d["frame"] / float(d["fps"])
    return d


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Teljes meccs: testpontok minden ritkított kockán")
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--stride", type=int, default=DEFAULT_STRIDE)
    ap.add_argument("--imgsz", type=int, default=DEFAULT_IMGSZ)
    ap.add_argument("--weights", default="yolo11n-pose.pt")
    ap.add_argument("--device", default=None)
    ap.add_argument("--batch", type=int, default=8)
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    run(args.video, out, args.stride, args.imgsz, args.weights, args.device, args.batch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
