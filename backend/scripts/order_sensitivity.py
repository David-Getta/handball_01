"""Sorrend-érzékenység mérése — mely rétegek eredménye függ attól,
hogy a kapus-jelölés MÁR megtörtént-e.

Miért kell ez? A `detect_goalkeepers` BELEÍR a meccsbe (`p.role =
"kapus"`), és több réteg a szerepből dolgozik (a kapust nem számolja
védőnek, birtokosnak, lövőnek). Emiatt ugyanaz a réteg MÁS számot adhat
friss meccsen, mint azután, hogy egy korábbi réteg már megjelölte a
kapusokat. Egy nagy összeállításban (meccs-csomag, támadás-végpont) így
a kiértékelés SORRENDJE befolyásolja az eredményt.

Ez a szkript nem javít semmit — MEGMÉRI, hogy pontosan mely rétegeket
érinti. A kimenet a docs/SORREND_FUGGES.md: ez a lista a döntés
alapja, hogy melyik rétegnél érdemes kimondott (determinisztikus)
szerep-jelöléssel indítani.

Módszer: rétegenként két FRISS, azonos magból generált szimulált meccs.
Az egyiken a réteg fut előbb; a másikon előbb a `detect_goalkeepers`,
és csak utána a réteg. Ha a két eredmény eltér, a réteg sorrend-függő.

Használat:
    cd backend && python -m scripts.order_sensitivity            # kiírja
    cd backend && python -m scripts.order_sensitivity --seconds 180
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_OUT = _BACKEND.parent / "docs" / "SORREND_FUGGES.md"

# A mérés alapja: ekkora szimulált meccs, ezzel a maggal. Rövidebb
# meccsen kevesebb réteg szólal meg, tehát kevesebb eltérés látszik —
# a szám a futásidő és a lefedettség kompromisszuma.
DEFAULT_SECONDS = 240.0
DEFAULT_SEED = 7
# A szimuláció alapból NEM termel lövést (csak mozgást). Enélkül a
# lövés-alapú rétegek üres bemenettel futnak, és a mérés róluk nem mond
# semmit — ezért itt bekapcsoljuk. A 6 lövés/perc nagyjából valós
# meccstempó (két csapatra ~50-60 lövés egy meccsen).
DEFAULT_SHOTS_PER_MIN = 6.0


def _layer_functions() -> list[tuple[str, str, str]]:
    """(réteg-név, modul, függvénynév) — a katalógus regisztrációja
    alapján, csak azokra, amelyek tényleg önálló pipeline-függvények."""
    from scripts.layer_catalog import _find_layer, _registered_layers

    out = []
    for name, fn in sorted(_registered_layers().items()):
        mod, _ = _find_layer(fn)
        if mod == "api/app.py":
            continue  # összetett/beágyazott réteg — nincs önálló belépő
        out.append((name, mod, fn))
    return out


def _fresh_match(seconds: float, seed: int,
                 shots_per_min: float = DEFAULT_SHOTS_PER_MIN):
    from handball.sim.match_simulator import simulate_ground_truth
    return simulate_ground_truth(duration_s=seconds, seed=seed,
                                 shots_per_min=shots_per_min)


def _dump(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def measure(seconds: float = DEFAULT_SECONDS,
            seed: int = DEFAULT_SEED,
            shots_per_min: float = DEFAULT_SHOTS_PER_MIN) -> dict:
    """A sorrend-függő rétegek felmérése.

    Visszatérés: {"checked", "sensitive": [réteg-név, ...],
    "failed": [réteg-név, ...]} — a "failed" azok, amelyek valamelyik
    ágon hibára futottak (azokról nem mondunk ítéletet).
    """
    from handball.pipeline.goalkeeper import detect_goalkeepers

    sensitive: list[str] = []
    failed: list[str] = []
    checked = 0
    for name, mod_name, fn_name in _layer_functions():
        try:
            mod = importlib.import_module(f"handball.pipeline.{mod_name}")
            fn = getattr(mod, fn_name)
        except Exception:
            failed.append(name)
            continue
        try:
            plain = fn(_fresh_match(seconds, seed, shots_per_min))
            marked_match = _fresh_match(seconds, seed, shots_per_min)
            detect_goalkeepers(marked_match)
            marked = fn(marked_match)
        except TypeError:
            failed.append(name)
            continue
        except Exception:
            failed.append(name)
            continue
        checked += 1
        if _dump(plain) != _dump(marked):
            sensitive.append(name)
    return {"checked": checked, "sensitive": sensitive, "failed": failed}


def build_report(res: dict, seconds: float, seed: int,
                 shots_per_min: float = DEFAULT_SHOTS_PER_MIN) -> str:
    lines = [
        "# Sorrend-függés — mely rétegre hat a kapus-jelölés",
        "",
        "*Generált fájl — ne kézzel szerkeszd. Frissítés:*",
        "`cd backend && python -m scripts.order_sensitivity`",
        "",
        "A `detect_goalkeepers` beleír a meccsbe (`role = \"kapus\"`), és",
        "több réteg a szerepből dolgozik. Az alábbi rétegek eredménye",
        "ezért ATTÓL FÜGG, megtörtént-e már a kapus-jelölés, amikor",
        "lefutnak — egy nagy összeállításban tehát a kiértékelés",
        "sorrendjétől. Ez a lista a döntés alapja: hol érdemes kimondott,",
        "determinisztikus szerep-jelöléssel indítani.",
        "",
        f"Mérés: {seconds:.0f} mp-es szimulált meccs (mag: {seed}); "
        f"**{res['checked']} réteg** összevetve, ebből "
        f"**{len(res['sensitive'])} sorrend-függő**.",
        "",
        "## A mérés köre",
        "",
    ]
    if shots_per_min > 0:
        lines += [
            f"A szimuláció ebben a futásban LŐ is ({shots_per_min:.0f}",
            "lövés/perc, a hazai mezőnyjátékosok körbejárva), tehát a",
            "lövés-alapú rétegek valódi bemenetet kaptak. A szimuláció",
            "alapértelmezésben csak mozgást modellez — enélkül ezek a",
            "rétegek üres bemeneten futnának, és a mérés róluk nem",
            "mondana semmit.",
            "",
        ]
    else:
        lines += [
            "Ebben a futásban a szimuláció NEM termelt lövést, ezért a",
            "lövés-alapú rétegek üres bemenettel futottak: mindkét ágon",
            "ugyanazt a semmit adják, tehát \"nem sorrend-függőnek\"",
            "LÁTSZANAK. Ez nem bizonyíték — csak annyit jelent, hogy",
            "ezekről a rétegekről a mérés NEM MOND SEMMIT.",
            "",
        ]
    if res["sensitive"]:
        lines += ["## Sorrend-függő rétegek", "", "| Réteg |", "|---|"]
        lines += [f"| `{n}` |" for n in res["sensitive"]]
        lines.append("")
    else:
        lines += ["Ezen a mintán egyetlen réteg sem bizonyult "
                  "sorrend-függőnek.", ""]
    if res["failed"]:
        lines += [
            f"## Nem mérhető ({len(res['failed'])})",
            "",
            "Ezek a rétegek valamelyik ágon hibára futottak vagy nem",
            "hívhatók egyetlen meccs-paraméterrel — róluk nem mondunk",
            "ítéletet.",
            "",
            "| Réteg |", "|---|",
        ]
        lines += [f"| `{n}` |" for n in res["failed"]]
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seconds", type=float, default=DEFAULT_SECONDS,
                    help="a szimulált meccs hossza másodpercben")
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED,
                    help="a szimuláció magja")
    ap.add_argument("--shots-per-min", type=float,
                    default=DEFAULT_SHOTS_PER_MIN,
                    help="hazai lövés/perc a szimulációban (0 = nincs)")
    args = ap.parse_args(argv)

    res = measure(args.seconds, args.seed, args.shots_per_min)
    _OUT.write_text(
        build_report(res, args.seconds, args.seed, args.shots_per_min),
        encoding="utf-8")
    print(f"Sorrend-függés kiírva: {_OUT}")
    print(f"  összevetve: {res['checked']} réteg")
    print(f"  sorrend-függő: {len(res['sensitive'])}")
    print(f"  nem mérhető: {len(res['failed'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
