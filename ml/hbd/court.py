"""Ki áll a pályán? — a nézők és a lelátó kiszűrése a láb alatti színből.

A pózbecslő a lelátón ülő nézőket is embernek látja, és egy gólnál felemelt
szurkolói kar a lövésfelismerőnek "dobókar". Egyszerű, olcsó szűrő: a
játékos lába alatt a PÁLYA PADLÓJA van, a nézőé alatt szék, korlát, másik
néző. A padló színét a meccsből tanuljuk: a láb alatti foltok
leggyakoribb színe (a legtöbb észlelt ember a pályán áll).

Az eredmény emberenkénti jelző (`on_court`), a `match_pose` sorrendjében;
a `filter_pose` ennek alapján szűri a póz-adatot.

    python -m hbd.court --video meccs.mp4 --pose m1_pose.npz --out m1_court.npz
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import numpy as np

from .video import ffmpeg_exe

WORK = (640, 360)
# A láb alatti folt: a doboz alsó szélének közepén, a doboz-magasság ennyi részéig lefelé.
FOOT_PATCH = 0.06
# Lab-színtávolság a padló-színtől, ami alatt "pályán áll".
FLOOR_DIST = 22.0
# A padló-színt ennyi leggyakoribb színcsoport adja (a pálya több színű lehet: alap + 9-es terület).
FLOOR_BINS = 2
BIN = 16


def foot_colors(video: str, pose: dict) -> np.ndarray:
    """Emberenként a láb alatti folt átlagos Lab-színe (össz_emberek, 3)."""
    import cv2

    w, h = WORK
    stride = int(pose["stride"])
    frames = pose["frame"]
    off, boxes = pose["offsets"], pose["boxes"].astype(np.float32)
    out = np.zeros((len(boxes), 3), np.float32)
    cmd = [ffmpeg_exe(), "-v", "error", "-i", video, "-vf", f"select='not(mod(n\\,{stride}))',scale={w}:{h}",
           "-vsync", "0", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    i, k = 0, 0
    try:
        while i < len(frames):
            buf = proc.stdout.read(w * h * 3)
            if len(buf) < w * h * 3:
                break
            if k * stride != frames[i]:
                k += 1
                continue
            lab = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(h, w, 3), cv2.COLOR_BGR2LAB)
            for j in range(off[i], off[i + 1]):
                x0, y0, x1, y1 = boxes[j] * [w, h, w, h]
                cx, bh = (x0 + x1) / 2, max(y1 - y0, 1.0)
                ya, yb = int(min(h - 1, y1)), int(min(h, y1 + max(2, FOOT_PATCH * bh)))
                xa, xb = int(max(0, cx - 3)), int(min(w, cx + 4))
                patch = lab[ya:max(yb, ya + 1), xa:max(xb, xa + 1)]
                out[j] = patch.reshape(-1, 3).mean(0)
            i += 1
            k += 1
    finally:
        proc.stdout.close()
        proc.kill()
        proc.wait()
    return out


def floor_colors(colors: np.ndarray) -> np.ndarray:
    """A padló színe(i): a láb alatti színek FLOOR_BINS leggyakoribb csoportjának mediánja."""
    q = (colors // BIN).astype(np.int32)
    keys = q[:, 0] * 10000 + q[:, 1] * 100 + q[:, 2]
    vals, counts = np.unique(keys, return_counts=True)
    out = []
    for key in vals[np.argsort(-counts)][:FLOOR_BINS]:
        out.append(np.median(colors[keys == key], 0))
    return np.array(out, np.float32)


def on_court(colors: np.ndarray, floor: np.ndarray) -> np.ndarray:
    d = np.linalg.norm(colors[:, None, :] - floor[None, :, :], axis=2).min(1)
    return d <= FLOOR_DIST


def filter_pose(pose: dict, keep: np.ndarray) -> dict:
    """A póz-adat csak a megtartott emberekkel (azonos mintakockák)."""
    off = pose["offsets"]
    n = np.array([int(keep[off[i]:off[i + 1]].sum()) for i in range(len(pose["n"]))], np.int32)
    out = dict(pose)
    out.update(n=n, offsets=np.concatenate([[0], np.cumsum(n)]).astype(np.int64),
               boxes=pose["boxes"][keep], kps=pose["kps"][keep])
    return out


def main(argv=None) -> int:
    from .match_pose import load

    ap = argparse.ArgumentParser(description="Pályán álló emberek (a nézők kiszűrése)")
    ap.add_argument("--video", required=True)
    ap.add_argument("--pose", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    pose = load(args.pose)
    col = foot_colors(args.video, pose)
    floor = floor_colors(col)
    keep = on_court(col, floor)
    np.savez_compressed(args.out, colors=col.astype(np.float16), floor=floor, on_court=keep)
    print(f"Padló-szín (Lab): {np.round(floor, 1).tolist()}; pályán: {keep.mean():.0%} "
          f"({keep.sum()} / {len(keep)} észlelés) → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
