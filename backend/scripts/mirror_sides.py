"""Tükrözés-őr — helyesen fordul-e meg a BAL és a JOBB.

Miért kell ez? Több réteg oldalt nevez meg: melyik szélen nyílik a rés,
melyik sarokba lő a poszt, melyik oldala gyenge a kapusnak. Ezek közül
a VÉDEKEZŐ oldalra szólók buktatósak: a két csapat SZEMBEN áll, tehát
ugyanaz a pálya-sáv az egyiknek a bal, a másiknak a jobb oldala. Aki a
nyers y-koordináta szerint nevez oldalt, az az egyik csapatról
fordítva állít — és ezt az edző készpénznek veszi.

A mérés: fogunk egy szimulált meccset, és TÜKRÖZZÜK a pálya hossz-
tengelyére (y → 20 − y). A tükörképben minden oldal-megnevezésnek meg
kell fordulnia. Amelyik rétegnél nem fordul meg (vagy megfordul, ami
nem oldal), az hibás.

Fontos nyelvi csapda: magyarul a "jobb" nem csak oldal, hanem "better"
is ("jobb szabad helyzet volt"). Ezért CSAK a pontos oldal-CÍMKÉKET
cseréljük (dict-kulcsok és önálló címke-értékek), a prózát soha — és a
prózát gyártó összegző rétegeket kihagyjuk.

Használat:
    cd backend && python -m scripts.mirror_sides            # kiírja
    cd backend && python -m scripts.mirror_sides --seconds 240
"""

from __future__ import annotations

import argparse
import copy
import importlib
import json
import re
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_OUT = _BACKEND.parent / "docs" / "TUKROZES.md"

DEFAULT_SECONDS = 120.0
DEFAULT_SEED = 7
DEFAULT_SHOTS_PER_MIN = 6.0
COURT_WIDTH_M = 20.0

# Az oldal-címke párok: CSAK ezek cserélődnek a tükörképben. A prózában
# előforduló "jobb" (= better) így érintetlen marad.
SIDE_PAIRS = {
    "bal": "jobb", "jobb": "bal",
    "bal szél": "jobb szél", "jobb szél": "bal szél",
    "bal átlövő": "jobb átlövő", "jobb átlövő": "bal átlövő",
    "balszélső": "jobbszélső", "jobbszélső": "balszélső",
    "balátlövő": "jobbátlövő", "jobbátlövő": "balátlövő",
}

# Próza-gyártó (összegző) rétegek: mondatokban beszélnek oldalról is,
# ott a szó szerinti csere értelmetlen — ezeket kihagyjuk.
PROSE_LAYERS = {"coach_summary", "counter_plan", "priority_findings",
                "training", "scouting"}

_LABEL_RE = re.compile(r'"(bal|jobb)(\s\w+)?"')


def mirror_match(match):
    """A meccs tükörképe a hossztengelyre (y → 20 − y) — új példány."""
    m = copy.deepcopy(match)
    for f in m.frames:
        for p in f.players:
            p.y = COURT_WIDTH_M - p.y
        if f.ball is not None:
            f.ball.y = COURT_WIDTH_M - f.ball.y
    return m


def swap_sides(value):
    """Az oldal-címkék cseréje kulcsokban és önálló címke-értékekben."""
    if isinstance(value, dict):
        return {SIDE_PAIRS.get(str(k), str(k)): swap_sides(v)
                for k, v in value.items()}
    if isinstance(value, list):
        return [swap_sides(v) for v in value]
    if isinstance(value, str):
        return SIDE_PAIRS.get(value, value)
    return value


def _canon(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def has_side_label(value) -> bool:
    """Ad-e a réteg PONTOS oldal-címkét (nem prózában említett oldalt)?"""
    return bool(_LABEL_RE.search(_canon(value)))


def measure(seconds: float = DEFAULT_SECONDS, seed: int = DEFAULT_SEED,
            shots_per_min: float = DEFAULT_SHOTS_PER_MIN) -> dict:
    """Rétegenkénti tükrözés-vizsgálat.

    Visszatérés: {"checked", "mirrored_ok": [...], "broken": [...],
    "skipped_prose": [...]} — a "broken" az, amelyik oldal-címkét ad, de
    a tükörképben nem fordul meg helyesen.
    """
    from scripts.order_sensitivity import _fresh_match, _layer_functions

    plain = _fresh_match(seconds, seed, shots_per_min)
    flipped = mirror_match(plain)

    ok: list[str] = []
    broken: list[str] = []
    skipped: list[str] = []
    checked = 0
    for name, mod_name, fn_name in _layer_functions():
        if name in PROSE_LAYERS:
            skipped.append(name)
            continue
        try:
            mod = importlib.import_module(f"handball.pipeline.{mod_name}")
            fn = getattr(mod, fn_name)
            a = fn(plain)
            b = fn(flipped)
        except Exception:  # noqa: BLE001 — a hibás réteget itt nem ítéljük
            continue
        if not has_side_label(a):
            continue
        checked += 1
        (ok if _canon(swap_sides(b)) == _canon(a) else broken).append(name)
    return {"checked": checked, "mirrored_ok": ok, "broken": broken,
            "skipped_prose": sorted(skipped)}


def build_report(res: dict, seconds: float, seed: int) -> str:
    lines = [
        "# Tükrözés-őr — helyesen fordul-e meg a bal és a jobb",
        "",
        "*Generált fájl — ne kézzel szerkeszd. Frissítés:*",
        "`cd backend && python -m scripts.mirror_sides`",
        "",
        "A pálya hossztengelyére tükrözött meccsen (y → 20 − y) minden",
        "oldal-megnevezésnek meg kell fordulnia. Ami nem fordul meg, az",
        "a nyers koordinátából nevez oldalt — és a két csapat közül az",
        "egyikről FORDÍTVA állít (szemben állnak).",
        "",
        f"Mérés: {seconds:.0f} mp-es szimulált meccs (mag: {seed}); "
        f"**{res['checked']} oldal-címkés réteg** vizsgálva, ebből "
        f"**{len(res['broken'])} hibás**.",
        "",
        "## Nyelvi megjegyzés",
        "",
        "Magyarul a *jobb* nem csak oldal, hanem *better* is („jobb",
        "szabad helyzet volt\"). Az őr ezért CSAK a pontos oldal-címkéket",
        "cseréli (dict-kulcs vagy önálló címke-érték), a mondatokat soha;",
        "a próza-gyártó összegző rétegek kimaradnak a mérésből.",
        "",
    ]
    if res["broken"]:
        lines += ["## Hibás rétegek", ""]
        lines += [f"- `{n}`" for n in sorted(res["broken"])]
    else:
        lines += ["## Hibás réteg: nincs", "",
                  "Minden oldal-címkés réteg helyesen tükröződik."]
    lines += ["", "## Vizsgált rétegek", ""]
    lines += [f"- `{n}`" for n in sorted(res["mirrored_ok"])]
    lines += ["", "## Kihagyva (próza-gyártó összegzők)", ""]
    lines += [f"- `{n}`" for n in res["skipped_prose"]]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seconds", type=float, default=DEFAULT_SECONDS)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = ap.parse_args(argv)

    res = measure(args.seconds, args.seed)
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(build_report(res, args.seconds, args.seed),
                    encoding="utf-8")
    print(f"Tükrözés-jelentés kiírva: {_OUT}")
    print(f"  vizsgálva: {res['checked']} réteg")
    print(f"  hibás: {len(res['broken'])}")
    for n in res["broken"]:
        print(f"    - {n}")
    return 1 if res["broken"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
