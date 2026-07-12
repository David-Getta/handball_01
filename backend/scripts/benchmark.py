"""
Validációs benchmark CLI — reprodukálható pontosság-eredménylap a motorról.

Használat:
    python -m scripts.benchmark [--out benchmark_report.md] [--seeds 1 2 3]
        [--duration 60]

Kimenet: Markdown eredménylap (+ .json ugyanott) — verzióval és seedekkel,
így két futás/két verzió közvetlenül összevethető. Pályázathoz (EIC) és
pilot-partnereknek is ez a hiteles "mennyire pontos?" válasz.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.pipeline.benchmark import run_benchmarks  # noqa: E402


def _detect_version() -> str:
    """A futó kód verziója: git-leírás, ha van; különben 'dev'."""
    try:
        out = subprocess.run(["git", "describe", "--tags", "--always"],
                             capture_output=True, text=True, timeout=5,
                             cwd=os.path.dirname(os.path.dirname(
                                 os.path.abspath(__file__))))
        v = out.stdout.strip()
        return v or "dev"
    except Exception:
        return "dev"


def main() -> int:
    ap = argparse.ArgumentParser(description="SportMachine validációs benchmark")
    ap.add_argument("--out", default="benchmark_report.md",
                    help="a Markdown eredménylap útja (mellé .json is készül)")
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    ap.add_argument("--duration", type=float, default=60.0,
                    help="szimulált meccs-hossz metrikánként (mp)")
    args = ap.parse_args()

    report = run_benchmarks(seeds=tuple(args.seeds),
                            duration_s=args.duration,
                            version=_detect_version())

    for m in report.metrics:
        rel = ">=" if m.higher_is_better else "<="
        state = "OK   " if m.passed else "BUKIK"
        print(f"[{state}] {m.name}: {m.value:.2f} {m.unit} "
              f"(küszöb {rel} {m.threshold:g})")
    print(f"\nÖsszkép: {'MINDEN METRIKA MEGFELELT' if report.all_passed else 'VAN BUKÓ METRIKA'}")

    out = Path(args.out)
    out.write_text(report.to_markdown(), encoding="utf-8")
    out.with_suffix(".json").write_text(
        json.dumps({
            "version": report.version,
            "seeds": list(report.seeds),
            "metrics": [dataclasses.asdict(m) | {"passed": m.passed}
                        for m in report.metrics],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"eredménylap: {out} (+ {out.with_suffix('.json').name})")
    return 0 if report.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
