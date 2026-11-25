"""Egy ÚJ meccs teljes előkészítése egy paranccsal — a jelölés előtt, vakon.

Lépések (mindegyik kihagyva, ha a kimenete már megvan → megszakítás után folytatható):
  1. póz a teljes meccsen         (hbd.match_pose, ~50 perc CPU-n)
  2. eredményjelző + kamera       (hbd.broadcast, ~6 perc)
  3. pálya-szűrő (nézők ki)       (hbd.court)
  4. jelölt lövések a KÉSZ modellel (hbd.shot_detect --model; az új meccsen nem tanul)
  5. klipek a jelöltek köré        (tools/cut_match_clips.py) → a meccs-lövésjelölő bemenete

A 4. lépés kimenete (jelolt_lovesek.json) a "vak jóslat": commitold, MIELŐTT az
emberi jelölés megérkezik, így a későbbi összevetés becsületes.

    python tools/uj_meccs.py --video meccs2.mp4 --name m2 --model shot_detect.joblib --out m2/
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ML = Path(__file__).resolve().parents[1]


def run(cmd: list[str], done: Path, what: str) -> None:
    if done.exists():
        print(f"[kész] {what}: {done}")
        return
    print(f"[fut] {what}", flush=True)
    subprocess.run([sys.executable, *cmd], check=True, cwd=ML,
                   env={**__import__("os").environ, "PYTHONPATH": str(ML)})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Új meccs előkészítése (vak lövés-jóslat + klipek)")
    ap.add_argument("--video", required=True)
    ap.add_argument("--name", required=True, help="rövid azonosító, pl. m2 (a klipek előtagja)")
    ap.add_argument("--model", required=True, help="a lövésfelismerő kész modellje (shot_detect.joblib)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--pose-weights", default="yolo11n-pose.pt")
    ap.add_argument("--device", default=None)
    ap.add_argument("--threshold", type=float, help="jelölt-küszöb (alapból a modellé)")
    ap.add_argument("--no-clips", action="store_true", help="csak a jóslat, klipek nélkül")
    args = ap.parse_args(argv)
    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    video = str(Path(args.video).resolve())
    n = args.name
    pose, bc, court = out / f"{n}_pose.npz", out / f"{n}_broadcast.npz", out / f"{n}_court.npz"
    dev = ["--device", args.device] if args.device else []
    run(["-m", "hbd.match_pose", "--video", video, "--out", str(pose), "--stride", "5", "--imgsz", "1280",
         "--weights", args.pose_weights, *dev], pose, "póz")
    run(["-m", "hbd.broadcast", "--video", video, "--out", str(bc), "--stride", "5"], bc, "közvetítés-jelek")
    run(["-m", "hbd.court", "--video", video, "--pose", str(pose), "--out", str(court)], court, "pálya-szűrő")
    sd = out / "jeloltek"
    thr = ["--threshold", str(args.threshold)] if args.threshold is not None else []
    run(["-m", "hbd.shot_detect", "--pose", str(pose), "--broadcast", str(bc), "--court", str(court),
         "--model", str(Path(args.model).resolve()), "--out", str(sd), "--title", n, *thr],
        sd / "jelolt_lovesek.json", "vak lövés-jóslat")
    if not args.no_clips:
        clips = out / "klipek"
        run([str(ML / "tools" / "cut_match_clips.py"), "--video", video, "--events", str(sd / "jelolt_lovesek.json"),
             "--out", str(clips), "--prefix", f"{n}g", "--negatives", "0"], clips / "manifest.json", "klipek")
    print(f"kész → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
