"""A labdafelismerő Kaggle-adatcsomagja (zip) a GPU-s tanításhoz.

A `kaggle/labda_gpu.ipynb` ezt várja bemenetként (Kaggle: *Add Input* → a
feltöltött, PRIVÁT adathalmaz). Tartalma:

  balldata/     — a `hbd.ball build` kimenete (tanító kivágások, a félretett
                  lövések teljes kivágásai, eval_points.json, labels_full.json)
  labdavideo/   — CSAK a félretett lövések labdajelölő-videói + a szűkített
                  manifest (a követés kiértékeléséhez)
  alap/labda2.pt — a jelenlegi (v2) felismerő, az összevetés alapja

A közvetítésből vágott képek: a csomag (és a Kaggle-adathalmaz) maradjon privát.

    python tools/labda_kaggle_csomag.py --data balldata2 --ball-dir m1ball2 \\
        --weights runs_ball/labda2/weights/best.pt --out labda_kaggle.zip
"""

from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

DATA_FILES = ("eval_points.json", "labels_full.json", "info.json")
DATA_DIRS = ("images", "labels", "full")


def pack(data: Path, ball_dir: Path, weights: Path, out: Path) -> dict:
    held = sorted(json.loads((data / "labels_full.json").read_text()))
    man = json.loads((ball_dir / "ball_manifest.json").read_text())
    clips = [c for c in man["klipek"] if c["id"] in held]
    missing = set(held) - {c["id"] for c in clips}
    if missing:
        raise SystemExit(f"a labdajelölő manifestjéből hiányzik: {sorted(missing)[:5]}")
    n = 0
    # A jpg/mp4 már tömörített: ZIP_STORED gyorsabb, és alig nagyobb.
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as z:
        for f in DATA_FILES:
            z.write(data / f, f"balldata/{f}")
        for d in DATA_DIRS:
            for p in sorted((data / d).rglob("*")):
                if p.is_file() and not p.name.endswith(".cache"):
                    z.write(p, f"balldata/{p.relative_to(data)}")
                    n += 1
        z.writestr("labdavideo/ball_manifest.json", json.dumps({"klipek": clips}, ensure_ascii=False))
        for c in clips:
            z.write(ball_dir / c["src"], f"labdavideo/{c['src']}")
        z.write(weights, "alap/labda2.pt")
    return {"fajlok": n, "felretett_klipek": len(clips), "meret_mb": round(out.stat().st_size / 1e6, 1)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", required=True, help="a hbd.ball build kimenete")
    ap.add_argument("--ball-dir", required=True, help="a labdajelölő videói (ball_manifest.json)")
    ap.add_argument("--weights", required=True, help="az összevetés alapja (v2 best.pt)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    print(pack(Path(a.data), Path(a.ball_dir), Path(a.weights), Path(a.out)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
