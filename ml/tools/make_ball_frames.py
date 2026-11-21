"""Állóképek a labda-jelöléshez: klipenként 3 kocka az elengedés körül, a lövő köré vágva.

A labda az elengedésnél 10–15 px-es és elmosódott; a 960 px-es klipen alig
látszik, és a kész (COCO) labdafelismerők sem találják. Ezért az EREDETI
felvételből vágunk ki éles képeket a lövő (a meccs-lövésjelölőn megjelölt
kattintás) köré, és ezeken kattint a jelölő a labdára.

Kockák az elengedéshez (E) képest: OFFSETS. A kivágás négyzetes, SIDE_PX
oldalú (1080p-n), a kattintás körül, a képre szorítva.

Kimenet:
  b/<klip>.jpg       — a 3 kivágott kocka egymás mellett (képcsík)
  ball_manifest.json — klipenként a kockák: klip-kocka (k), kép, kivágás (x0, y0, x1, y1) px-ben

    python tools/make_ball_frames.py --video meccs.mp4 --clips m1web/manifest.json \
        --labels cimkek/meccs1_lovesek_cimkek.json --out m1ball
"""

from __future__ import annotations

import argparse
import json
import subprocess
from multiprocessing import Pool
from pathlib import Path

# Kockák az elengedéshez képest: még kézben, épp elengedte, már repül.
OFFSETS = (-2, 1, 3)
NAMES = ("kezben", "elengedte", "repul")
SIDE_PX = 640
QUALITY = 4  # ffmpeg -q:v (2 = legjobb, 31 = legrosszabb)


def crop_box(cx: float, cy: float, w: int, h: int, side: int = SIDE_PX) -> tuple[int, int, int, int]:
    """Négyzetes kivágás (cx, cy) körül, a képen belül tolva (nem vágva) — mindig side × side."""
    side = min(side, w, h)
    x0 = int(round(min(max(0, cx - side / 2), w - side)))
    y0 = int(round(min(max(0, cy - side / 2), h - side)))
    return x0, y0, x0 + side, y0 + side


def job(args) -> dict:
    video, out, c, lab, w, h = args
    fps = c["fps"]
    cx, cy = lab["lovo"]["x"] * w, lab["lovo"]["y"] * h
    box = crop_box(cx, cy, w, h)
    frames = []
    for j, (off, name) in enumerate(zip(OFFSETS, NAMES)):
        k = max(0, min(c["frames"] - 1, lab["elengedes"] + off))
        dst = out / "b" / f"{c['id']}_{j}.jpg"
        t = c["t_start"] + k / fps
        x0, y0, x1, y1 = box
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", video, "-frames:v", "1",
                        "-vf", f"crop={x1 - x0}:{y1 - y0}:{x0}:{y0}", "-q:v", str(QUALITY), str(dst)], check=True)
        frames.append({"k": int(k), "nev": name, "src": f"b/{dst.name}"})
    # a 3 kockát egy képcsíkba fűzzük (egy fájl / klip: az oldal verziónkénti fájlkorlátja miatt)
    import cv2
    import numpy as np

    imgs = [cv2.imread(str(out / f["src"])) for f in frames]
    sprite = out / "b" / f"{c['id']}.jpg"
    cv2.imwrite(str(sprite), np.hstack(imgs), [cv2.IMWRITE_JPEG_QUALITY, 88])
    for f in frames:
        (out / f["src"]).unlink()
        del f["src"]
    x0, y0, x1, y1 = box
    lovo = [round((cx - x0) / (x1 - x0), 4), round((cy - y0) / (y1 - y0), 4)]  # a kivágáson belül, 0..1
    return {"id": c["id"], "ismetles": bool(c.get("ismetles")), "elengedes": lab["elengedes"],
            "crop": list(box), "size": [w, h], "lovo": lovo, "sprite": f"b/{sprite.name}", "frames": frames}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--clips", required=True, help="a cut_match_clips manifest.json-ja")
    ap.add_argument("--labels", required=True, help="cimkek/meccs1_lovesek_cimkek.json")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--size", type=int, nargs=2, default=(1920, 1080))
    args = ap.parse_args(argv)
    man = {c["id"]: c for c in json.loads(Path(args.clips).read_text())["clips"]}
    labs = [d for d in json.loads(Path(args.labels).read_text())["cimkek"]
            if not d.get("rossz") and d.get("lovo") and d.get("elengedes") is not None]
    out = Path(args.out)
    (out / "b").mkdir(parents=True, exist_ok=True)
    w, h = args.size
    with Pool(args.workers) as pool:
        items = pool.map(job, [(args.video, out, man[d["klip"]], d, w, h) for d in labs if d["klip"] in man])
    items.sort(key=lambda it: it["id"])
    (out / "ball_manifest.json").write_text(json.dumps({"kockak": list(NAMES), "klipek": items}, ensure_ascii=False))
    size = sum(f.stat().st_size for f in (out / "b").glob("*.jpg"))
    print(f"{len(items)} klip, {3 * len(items)} kocka, {size / 1e6:.1f} MB → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
