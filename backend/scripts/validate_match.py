"""Pontosság-validáció parancssorból — a pilot go/no-go méréshez.

Egy már feldolgozott meccs (mentett JSON) felismert eseményeit veti össze
egy EMBER által annotált eseménylistával (CSV), és kiírja a precizitás /
visszahívás / F1 értékeket + az edző-olvasható ítéletet (MEGFELEL/GYENGE).
Opcionálisan megosztható HTML-riportot is ír.

Ez ugyanaz, mint a POST /matches/{id}/validate végpont, csak offline,
szerver nélkül — egy pilot-operátor a feldolgozott meccsre és a coach
CSV-jére futtatja.

A meccs JSON a data/matches/{id}.json fájl (a program menti oda).
A CSV soronként: `idő, típus[, csapat]` — az idő tizedes mp vagy mm:ss, a
típus/csapat magyarul és angolul is jó (gól/goal, lövés/shot, hazai/home).

Használat:
    python -m scripts.validate_match data/matches/<id>.json igazsag.csv
        [--tol 3.0] [--out jelentes.html]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# A backend/ mappa a path-on, hogy a handball csomag bárhonnan látszódjon.
_BACKEND = str(Path(__file__).resolve().parents[1])
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from handball.models.tracking import Match  # noqa: E402
from handball.pipeline.validation import (  # noqa: E402
    parse_truth_csv, validate_events, validation_ledger_row,
    validation_report_html, validation_template_csv)


def _load_match(path: str) -> Match:
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return Match.from_dict(d)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Pontosság-validáció kézi ground-truth ellen.")
    ap.add_argument("match_json", help="A feldolgozott meccs JSON-ja "
                    "(pl. data/matches/<id>.json).")
    ap.add_argument("truth_csv", nargs="?", default=None,
                    help="A kézi eseménylista CSV/TSV fájlja "
                         "(elhagyható, ha --sablon fut).")
    ap.add_argument("--sablon", default=None, metavar="SABLON_CSV",
                    help="Előtöltött annotációs sablont ír ide a motor "
                         "felismeréseiből, és kilép — ezt javítja kézzel "
                         "az annotátor (lásd docs/ANNOTACIOS_UTMUTATO.md).")
    ap.add_argument("--tol", type=float, default=3.0,
                    help="Idő-tűrés másodpercben (alap: 3.0).")
    ap.add_argument("--out", default=None,
                    help="Ide írja a megosztható HTML-riportot (opcionális).")
    ap.add_argument("--jegyzokonyv", nargs="?", default=None,
                    const=str(Path(_BACKEND).parent / "docs"
                              / "MERESI_JEGYZOKONYV.md"),
                    help="A mérés sorát a mérési jegyzőkönyvhöz fűzi "
                         "(alap: docs/MERESI_JEGYZOKONYV.md).")
    args = ap.parse_args(argv)

    if not os.path.exists(args.match_json):
        print(f"HIBA: nincs ilyen meccs-fájl: {args.match_json}",
              file=sys.stderr)
        return 2
    if args.sablon:
        match = _load_match(args.match_json)
        Path(args.sablon).write_text(validation_template_csv(match),
                                     encoding="utf-8")
        print(f"Annotációs sablon kiírva: {args.sablon}")
        return 0
    if not args.truth_csv:
        print("HIBA: kell a kézi CSV (vagy futtasd --sablon móddal).",
              file=sys.stderr)
        return 2
    if not os.path.exists(args.truth_csv):
        print(f"HIBA: nincs ilyen CSV: {args.truth_csv}", file=sys.stderr)
        return 2

    match = _load_match(args.match_json)
    truth = parse_truth_csv(Path(args.truth_csv).read_text(encoding="utf-8"))
    res = validate_events(match, truth, tol_s=args.tol)

    ov = res["overall"]

    def _pct(x):
        return "—" if x is None else f"{x * 100:.0f}%"

    print(f"Meccs: {match.meta.home_team} – {match.meta.away_team}")
    print(f"Kézi események: {len(truth)} | idő-tűrés: {args.tol} mp")
    print("-" * 48)
    for ty, label in (("goal", "Gól"), ("shot", "Lövés")):
        r = res["by_type"][ty]
        print(f"{label:6} | TP {r['tp']:2}  FP {r['fp']:2}  FN {r['fn']:2}  "
              f"| P {_pct(r['precision'])}  R {_pct(r['recall'])}  "
              f"F1 {_pct(r['f1'])}")
    print("-" * 48)
    print(f"Összesen | TP {ov['tp']:2}  FP {ov['fp']:2}  FN {ov['fn']:2}  "
          f"| P {_pct(ov['precision'])}  R {_pct(ov['recall'])}  "
          f"F1 {_pct(ov['f1'])}")
    print()
    print(res["verdict"]["text"])

    if args.out:
        html = validation_report_html(
            res, match.meta.home_team, match.meta.away_team)
        Path(args.out).write_text(html, encoding="utf-8")
        print(f"\nHTML-riport: {args.out}")

    if args.jegyzokonyv:
        # Verzió: a repó rövid commit-hash-e (ha elérhető).
        import subprocess
        try:
            version = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=_BACKEND, capture_output=True, text=True,
                timeout=10).stdout.strip() or "?"
        except Exception:
            version = "?"
        row = validation_ledger_row(
            res, match_id=Path(args.match_json).stem, version=version)
        ledger = Path(args.jegyzokonyv)
        with ledger.open("a", encoding="utf-8") as f:
            f.write(row + "\n")
        print(f"\nJegyzőkönyv-sor hozzáfűzve: {ledger}")

    # A go/no-go-hoz hasznos kilépőkód: 0 = MEGFELEL, 1 = GYENGE/nincs adat.
    return 0 if res["verdict"]["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
