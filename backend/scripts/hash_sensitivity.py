"""Hash-függés jelentés: melyik réteg ad MÁS eredményt más hash-keveréssel.

A Python a szöveg-kulcsú halmazok (és a belőlük épített sorrendek)
bejárását folyamatonként véletlenszerűen keveri (PYTHONHASHSEED). Ha egy
réteg halmazon iterálva választ — holtversenyben az elsőt, vagy a
halmaz sorrendjében épít listát —, ugyanaz a meccs két INDÍTÁSKOR más
eredményt ad. Az edző ezt úgy látja, hogy a jelentés "magától" változik.
(Így viselkedett a felderítés "fekete ötperc" kulcsa: hol a 0–5., hol az
5–10. percet mondta, ugyanazzal a mérleggel.)

A jelentés minden regisztrált réteget (ugyanaz a lista, mint a
sorrend-függésé) friss meccsen kiszámol HÁROM külön folyamatban, három
különböző hash-maggal, és összeveti a sorosított kimenetet. A szótár-
kulcsok sorrendje normalizálva van (sort_keys) — csak a valódi
eltérés számít: lista-sorrend és érték.

Futtatás (a backend mappából, kiadás előtt — percekig fut):

    python3 -m scripts.hash_sensitivity

A hibás-lista ÜRES, és annak is kell maradnia. Ha egy réteg megjelenik,
az a halmaz-iterálás: rendezd a bejárást (időrend, szám, név), és
holtversenyben döntsön determinisztikus kulcs.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

DEFAULT_SECONDS = 600.0
DEFAULT_SEED = 3
DEFAULT_SHOTS_PER_MIN = 8.0
HASH_SEEDS = ("1", "4", "7")

_REPORT = Path(__file__).resolve().parent.parent.parent / "docs" / "HASH_FUGGES.md"


def _worker(out_path: str, seconds: float, seed: int,
            shots_per_min: float, only: str = "") -> None:
    """Egy folyamat: minden réteg friss meccsen; {név: sha1 | "HIBA"}."""
    from scripts.order_sensitivity import _dump, _fresh_match, _layer_functions

    csak = {n for n in only.split(",") if n}
    out: dict[str, str] = {}
    for name, mod_name, fn_name in _layer_functions():
        if csak and name not in csak:
            continue
        try:
            mod = importlib.import_module(f"handball.pipeline.{mod_name}")
            fn = getattr(mod, fn_name)
            val = fn(_fresh_match(seconds, seed, shots_per_min))
            out[name] = hashlib.sha1(_dump(val).encode("utf-8")).hexdigest()
        except Exception:
            out[name] = "HIBA"
    Path(out_path).write_text(json.dumps(out, sort_keys=True), encoding="utf-8")


def measure(seconds: float = DEFAULT_SECONDS, seed: int = DEFAULT_SEED,
            shots_per_min: float = DEFAULT_SHOTS_PER_MIN,
            hash_seeds=HASH_SEEDS, only: str = "") -> dict:
    """A hash-függő rétegek felmérése párhuzamos folyamatokkal.

    Visszatérés: {"checked", "sensitive": [név], "failed": [név]} — a
    "failed" azok, amelyek valamelyik folyamatban hibára futottak."""
    backend = Path(__file__).resolve().parent.parent
    with tempfile.TemporaryDirectory() as tmp:
        procs = []
        for hs in hash_seeds:
            out = os.path.join(tmp, f"h{hs}.json")
            env = dict(os.environ, PYTHONHASHSEED=hs)
            procs.append((out, subprocess.Popen(
                [sys.executable, "-m", "scripts.hash_sensitivity",
                 "--worker", out, "--seconds", str(seconds),
                 "--seed", str(seed), "--shots", str(shots_per_min),
                 "--only", only],
                cwd=str(backend), env=env)))
        runs = []
        for out, p in procs:
            if p.wait() != 0:
                raise RuntimeError(f"a mérő-folyamat hibával állt le ({out})")
            runs.append(json.loads(Path(out).read_text(encoding="utf-8")))
    names = sorted(set().union(*runs))
    sensitive, failed = [], []
    for n in names:
        vals = [r.get(n, "HIÁNYZIK") for r in runs]
        if any(v in ("HIBA", "HIÁNYZIK") for v in vals):
            failed.append(n)
        elif len(set(vals)) > 1:
            sensitive.append(n)
    return {"checked": len(names) - len(failed), "sensitive": sensitive,
            "failed": failed}


def build_report(res: dict, seconds: float, seed: int) -> str:
    sorok = [
        "# Hash-függés (generált jelentés)",
        "",
        "A `python3 -m scripts.hash_sensitivity` írja — kézzel ne szerkeszd.",
        "",
        "Minden regisztrált réteg egy friss, szimulált meccsen "
        f"({int(seconds)} mp, mag: {seed}), {len(HASH_SEEDS)} külön "
        "folyamatban, különböző hash-keveréssel (PYTHONHASHSEED = "
        + ", ".join(HASH_SEEDS) + "). Ha egy réteg kimenete eltér, ugyanaz "
        "a meccs két indításkor más eredményt ad.",
        "",
        f"- összevetve: {res['checked']} réteg",
        f"- hash-függő: {len(res['sensitive'])}",
        f"- nem mérhető (hibára futott): {len(res['failed'])}",
        "",
    ]
    if res["sensitive"]:
        sorok += ["## Hash-függő rétegek (JAVÍTANDÓ)", ""]
        sorok += [f"- `{n}`" for n in res["sensitive"]]
        sorok += [""]
    else:
        sorok += ["A hash-függő lista üres — és annak is kell maradnia.", ""]
    if res["failed"]:
        sorok += ["## Nem mérhető rétegek", ""]
        sorok += [f"- `{n}`" for n in res["failed"]]
        sorok += [""]
    return "\n".join(sorok)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--worker", help=argparse.SUPPRESS)
    ap.add_argument("--seconds", type=float, default=DEFAULT_SECONDS)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--shots", type=float, default=DEFAULT_SHOTS_PER_MIN)
    # Csak ezek a rétegek (vesszővel) — egy gyanús réteg gyors újramérése;
    # ilyenkor a jelentés-fájlt NEM írjuk felül.
    ap.add_argument("--only", default="")
    args = ap.parse_args(argv)
    if args.worker:
        _worker(args.worker, args.seconds, args.seed, args.shots, args.only)
        return 0
    res = measure(args.seconds, args.seed, args.shots, only=args.only)
    if args.only:
        print(f"hash-függő ({args.only}): {res['sensitive'] or 'nincs'}"
              f"  · nem mérhető: {res['failed'] or 'nincs'}")
        return 0
    _REPORT.write_text(build_report(res, args.seconds, args.seed),
                       encoding="utf-8")
    print(f"Hash-függés kiírva: {_REPORT}")
    print(f"  összevetve: {res['checked']} réteg")
    print(f"  hash-függő: {len(res['sensitive'])}")
    for n in res["sensitive"]:
        print(f"    - {n}")
    print(f"  nem mérhető: {len(res['failed'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
