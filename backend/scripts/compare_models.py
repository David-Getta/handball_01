"""
Modell-összemérő CLI — az alap- és a saját (finomhangolt) detektor
összehasonlítása VALÓDI meccsfelvételen, cél-címkék nélkül is.

A finomhangolási kör mérőműszere:
    1. mérés az alapmodellel     → kiindulási szint
    2. gyűjtés + tanítás          → scripts/collect_dataset + finetune
    3. mérés újra, egymás mellett → számmal látszik, mennyit ért a tanítás

Használat:
    python -m scripts.compare_models MECCS.mp4 \
        [--weights-b runs/handball/weights/best.pt] \
        [--samples 120] [--start 0] [--out osszehasonlitas.md]

--weights-b nélkül egymodelles eredménylap készül (kiindulási szint).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.pipeline.model_eval import comparison_markdown, evaluate_detector  # noqa: E402
from scripts.collect_dataset import _make_detect_fn  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Detektor-minőség mérése/összehasonlítása meccsvideón")
    ap.add_argument("video", help="meccsvideó")
    ap.add_argument("--weights-a", default="yolov8n.pt",
                    help="A modell (alap: yolov8n.pt — a kiindulási szint)")
    ap.add_argument("--weights-b", default=None,
                    help="B modell (pl. a finomhangolt best.pt) — nélküle "
                         "egymodelles eredménylap készül")
    ap.add_argument("--samples", type=int, default=120)
    ap.add_argument("--start", type=int, default=0,
                    help="ettől a kép-indextől mérünk (bevezető átugrása)")
    ap.add_argument("--imgsz", type=int, default=1920)
    ap.add_argument("--out", default="modell_osszehasonlitas.md")
    args = ap.parse_args()

    def measure(weights: str):
        print(f"mérés: {weights} …")
        detect = _make_detect_fn(weights, args.imgsz, 0.35, 0.05)
        rep = evaluate_detector(args.video, detect, samples=args.samples,
                                start=args.start)
        print(f"  {rep.frames} kocka · labda-lefedettség: "
              f"{rep.ball_coverage_pct}% · átl. játékos: {rep.avg_persons} · "
              f"{rep.ms_per_frame} ms/kocka")
        return rep

    rep_a = measure(args.weights_a)
    rep_b = measure(args.weights_b) if args.weights_b else None

    md = comparison_markdown(args.video, Path(args.weights_a).name, rep_a,
                             Path(args.weights_b).name if args.weights_b else None,
                             rep_b)
    out = Path(args.out)
    out.write_text(md, encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps({
        "video": args.video,
        "a": {"weights": args.weights_a, **rep_a.to_dict()},
        **({"b": {"weights": args.weights_b, **rep_b.to_dict()}}
           if rep_b else {}),
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\neredménylap: {out} (+ {out.with_suffix('.json').name})")
    if rep_b is not None:
        diff = rep_b.ball_coverage_pct - rep_a.ball_coverage_pct
        print(f"labda-lefedettség változása: {'+' if diff >= 0 else ''}{diff:.1f} "
              "százalékpont")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
