"""Jelölő-videók készítése a lövésekhez (a jelölő oldal bemenete).

Minden lövés-klipből egy rövid MP4: bal oldalt a lövő nagyítva, jobb oldalt
a teljes jelenet (a lövő bekeretezve) — hogy a labda útja a kapuig is
látsszon. A kocka sorszáma be van égetve: a jelölt "elengedés kockája" így
pontosan a kivágott klip kockájára mutat (k = 0 a klip első kockája).
A klip vége után még TAIL_S másodperc jelenet következik (a labda útja).

Csontváz SZÁNDÉKOSAN nincs a videón: a jelölés az ember szeme legyen, ne a
modell tippje (különben a hibáit tanítanánk vissza).

    python tools/make_label_clips.py --data /út/handball_s --poses poses.npz --out labelweb
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from multiprocessing import Pool
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hbd.dataset import SHOT_CATEGORIES, index_dataset  # noqa: E402
from hbd.locate import find_offset  # noqa: E402
from hbd.pose import load_dataset, square_crop_box  # noqa: E402
from hbd.video import ffmpeg_exe, iter_frames, probe, read_frames  # noqa: E402

# A klip vége után ennyi másodpercnyi jelenet (a labda útja a kapuig).
TAIL_S = 0.8
# Kimeneti méretek: nagyított lövő (négyzet) + teljes jelenet (16:9).
CROP_PX = 360
SCENE_W, SCENE_H = 640, 360
# A lövő-kivágás a doboz hosszabbik oldalának ennyiszerese (több környezet,
# mint a pózkinyerésnél: a kar teljes íve férjen bele).
LABEL_CROP_SCALE = 2.0


def render_clip(job: tuple) -> dict | None:
    clip, boxes, out_dir = job
    out = out_dir / "v" / f"{clip.name}.mp4"
    w, h, fps = probe(clip.scene_path)
    action = read_frames(clip.action_path, gray=True)
    offset, _ = find_offset(iter_frames(clip.scene_path, gray=True), action[0])
    T = len(boxes)
    tail = int(round(TAIL_S * fps))
    fps_out = fps or 30.0
    enc = subprocess.Popen(
        [ffmpeg_exe(), "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
         "-s", f"{CROP_PX + SCENE_W}x{SCENE_H}", "-r", f"{fps_out}", "-i", "-",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-g", "6",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)],
        stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    n = 0
    for i, frame in enumerate(iter_frames(clip.scene_path)):
        k = i - offset
        if k < 0:
            continue
        if k >= T + tail:
            break
        box = boxes[min(k, T - 1)]
        x0, y0, x1, y1 = square_crop_box(box, w, h, LABEL_CROP_SCALE)
        crop = cv2.resize(frame[y0:y1, x0:x1], (CROP_PX, CROP_PX), interpolation=cv2.INTER_CUBIC)
        scene = frame.copy()
        bx = [int(v) for v in box]
        cv2.rectangle(scene, (bx[0] - 6, bx[1] - 6), (bx[2] + 6, bx[3] + 6), (0, 220, 255),
                      max(2, w // 480))
        scene = cv2.resize(scene, (SCENE_W, SCENE_H), interpolation=cv2.INTER_AREA)
        img = np.hstack([crop, scene])
        label = f"k={k}" if k < T else f"k={k} (utana)"
        cv2.putText(img, label, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(img, label, (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
        enc.stdin.write(np.ascontiguousarray(img).tobytes())
        n += 1
    enc.stdin.close()
    enc.wait()
    if n == 0:
        return None
    return {"id": clip.name, "cat": clip.category, "fps": round(fps_out, 3), "n": int(T),
            "frames": n, "src": f"v/{clip.name}.mp4"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--poses", required=True, help="a hbd.pose kimenete (a dobozokért)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args(argv)

    out = Path(args.out)
    (out / "v").mkdir(parents=True, exist_ok=True)
    poses = {c["name"]: c for c in load_dataset(args.poses)["clips"]}
    clips = [c for c in index_dataset(args.data, SHOT_CATEGORIES) if c.name in poses]
    if args.limit:
        clips = clips[:args.limit]
    jobs = [(c, poses[c.name]["boxes"], out) for c in clips]
    with Pool(args.workers) as pool:
        items = [r for r in pool.imap(render_clip, jobs) if r]
    # Kevert sorrend (determinisztikus): ne egy kategória jöjjön sorban.
    rng = np.random.default_rng(7)
    items = [items[i] for i in rng.permutation(len(items))]
    (out / "manifest.json").write_text(json.dumps({"clips": items}, ensure_ascii=False))
    size = sum(f.stat().st_size for f in (out / "v").glob("*.mp4"))
    print(f"{len(items)} videó, összesen {size / 1e6:.1f} MB → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
