"""Rövid, éles videók a labda-jelöléshez: az elengedés körül, a lövő köré vágva.

A labda az elengedésnél 10–15 px-es és elmosódott; a 960 px-es klipen alig
látszik, és a kész (COCO) labdafelismerők sem találják. Ezért az EREDETI
felvételből vágunk ki éles, négyzetes videót a lövő (a meccs-lövésjelölőn
megjelölt kattintás) köré, ±WINDOW_S az elengedés körül. A jelölő kockánként
léptet, és ő választja ki a kockát, ahol a labda kézben van, ahol elválik, és
ahol repül (az első változat fix kockákat mutatott: azok sokszor nem a
lényeges pillanatot fogták meg).

A videó kódolása `-bf 0` és sűrű kulcskocka: a böngésző currentTime-ból
számolt kockaszáma így pontosan egyezik a videó kockájával.

Kimenet:
  b/<klip>.mp4       — SIDE_PX × SIDE_PX videó, a klip k0. kockájától n kockán át
  ball_manifest.json — klipenként: k0, n, fps, kivágás (x0, y0, x1, y1) px-ben, a lövő helye

    python tools/make_ball_frames.py --video meccs.mp4 --clips m1web/manifest.json \
        --labels cimkek/meccs1_lovesek_cimkek.json --out m1ball
"""

from __future__ import annotations

import argparse
import json
import subprocess
from multiprocessing import Pool
from pathlib import Path

# Az ablak az elengedés körül (s): a korábbi elengedés-jelölés sem mindig kockára pontos.
WINDOW_S = 1.2
SIDE_PX = 640
CRF = "26"
GOP = "10"


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
    x0, y0, x1, y1 = crop_box(cx, cy, w, h)
    half = int(round(WINDOW_S * fps))
    k0 = max(0, lab["elengedes"] - half)
    k1 = min(c["frames"] - 1, lab["elengedes"] + half)
    n = k1 - k0 + 1
    dst = out / "b" / f"{c['id']}.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{c['t_start'] + k0 / fps:.3f}", "-i", video,
                    "-frames:v", str(n), "-vf", f"crop={x1 - x0}:{y1 - y0}:{x0}:{y0},setpts=PTS-STARTPTS", "-an",
                    "-c:v", "libx264", "-preset", "slow", "-crf", CRF, "-g", GOP, "-bf", "0",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(dst)], check=True)
    lovo = [round((cx - x0) / (x1 - x0), 4), round((cy - y0) / (y1 - y0), 4)]  # a kivágáson belül, 0..1
    return {"id": c["id"], "ismetles": bool(c.get("ismetles")), "elengedes": lab["elengedes"],
            "lovo_k": lab["lovo"]["k"], "k0": k0, "n": n, "fps": fps, "crop": [x0, y0, x1, y1], "size": [w, h],
            "lovo": lovo, "src": f"b/{dst.name}"}


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
    (out / "ball_manifest.json").write_text(json.dumps({"klipek": items}, ensure_ascii=False))
    size = sum(f.stat().st_size for f in (out / "b").glob("*.mp4"))
    print(f"{len(items)} videó, {size / 1e6:.1f} MB → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
