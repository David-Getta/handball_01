"""Stride-érzékenység — mely rétegek ítélete függ a kocka-ritkítástól.

Miért kell ez? A feldolgozó alapból MINDEN HARMADIK képkockát dolgozza
fel (stride=3), és a meccs effektív fps-e ennek megfelelően kisebb
(fps/stride — a t/fps időzítés így pontos marad). A rétegek egy része
viszont KOCKASZÁM-küszöbbel ítél (pl. "legalább 100 mért kocka"): ami
25 fps-nél 4 másodperc, az ~8 fps-nél 12 — ugyanaz a meccs ritkítva
másképp (jellemzően óvatosabban) ítélhet.

Ez a szkript nem javít semmit — MEGMÉRI: ugyanazt a szimulált meccset
lefuttatja teljes sűrűséggel és 3-as ritkítással, és rétegenként
összeveti az ÍTÉLET-mezőket (verdict, top, main_role, dominant, style,
formation, favorite, weak_*). A nyers számok (frames, összegek)
természetesen eltérnek — azokat nem hasonlítjuk.

A kimenet a docs/STRIDE_ERZEKENYSEG.md: az eltérő rétegek listája a
két ítélettel. Ez a lista a döntés alapja, hol érdemes a kockaszám-
küszöböt másodperc-alapúra váltani.

Használat:
    cd backend && python -m scripts.stride_sensitivity
    cd backend && python -m scripts.stride_sensitivity --seconds 300
"""

from __future__ import annotations

import argparse
import copy
import importlib
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_OUT = _BACKEND.parent / "docs" / "STRIDE_ERZEKENYSEG.md"

DEFAULT_SECONDS = 240.0
DEFAULT_SEED = 7
DEFAULT_SHOTS_PER_MIN = 6.0
DEFAULT_STRIDE = 3   # a termék alapértelmezése (api/app.py)

# Az ÍTÉLET-mezők: csak ezek értékét hasonlítjuk a két futás között.
JUDGEMENT_KEYS = {
    "verdict", "top", "main_role", "dominant", "style", "formation",
    "favorite", "weak_side", "weak_dir", "weak_hand", "worst_zone",
    "lefty", "lefty_role", "top_lane", "main_dir",
}


def downsample(match, stride: int):
    """A meccs ritkított másolata: minden `stride`-adik kocka marad, a
    t-k újraszámozva (0..), az fps a termékkel azonosan fps/stride."""
    m = copy.deepcopy(match)
    kept = [f for i, f in enumerate(m.frames) if i % stride == 0]
    for i, f in enumerate(kept):
        f.t = i
    m.frames = kept
    m.meta.fps = m.meta.fps / stride
    return m


def judgements(value, path: str = "") -> dict:
    """Az ítélet-mezők kigyűjtése {útvonal: érték} alakban.

    A dict-értékű ítéletet (pl. "top": {...}) az azonosítójára
    egyszerűsítjük — a benne lévő nyers számok (shots, frames) a
    ritkításnál jogosan térnek el."""
    out: dict = {}
    if isinstance(value, dict):
        for k, v in value.items():
            p = f"{path}.{k}" if path else str(k)
            if str(k) in JUDGEMENT_KEYS:
                if isinstance(v, dict):
                    out[p] = v.get("player_id", v.get("poszt", "van"))
                elif isinstance(v, (list, tuple)):
                    out[p] = "van" if v else None
                else:
                    out[p] = v
            else:
                out.update(judgements(v, p))
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            out.update(judgements(v, f"{path}[{i}]"))
    return out


def measure(seconds: float = DEFAULT_SECONDS, seed: int = DEFAULT_SEED,
            shots_per_min: float = DEFAULT_SHOTS_PER_MIN,
            stride: int = DEFAULT_STRIDE) -> dict:
    """Rétegenkénti összevetés a sűrű és a ritkított meccsen.

    Visszatérés: {"checked", "differs": [{"layer", "changes":
    [{"path", "dense", "strided"}]}], "failed": [...]}.
    """
    from scripts.order_sensitivity import _fresh_match, _layer_functions

    dense = _fresh_match(seconds, seed, shots_per_min)
    thin = downsample(dense, stride)

    differs: list[dict] = []
    failed: list[str] = []
    checked = 0
    for name, mod_name, fn_name in _layer_functions():
        try:
            mod = importlib.import_module(f"handball.pipeline.{mod_name}")
            fn = getattr(mod, fn_name)
            a = judgements(fn(dense))
            b = judgements(fn(thin))
        except Exception:  # noqa: BLE001
            failed.append(name)
            continue
        checked += 1
        changes = []
        for k in sorted(set(a) | set(b)):
            if a.get(k) != b.get(k):
                changes.append({"path": k, "dense": a.get(k),
                                "strided": b.get(k)})
        if changes:
            differs.append({"layer": name, "changes": changes})
    return {"checked": checked, "differs": differs, "failed": failed}


def build_report(res: dict, seconds: float, seed: int,
                 stride: int) -> str:
    lines = [
        "# Stride-érzékenység — az ítélet és a kocka-ritkítás",
        "",
        "*Generált fájl — ne kézzel szerkeszd. Frissítés:*",
        "`cd backend && python -m scripts.stride_sensitivity`",
        "",
        "A feldolgozó alapból minden harmadik képkockát dolgozza fel",
        "(stride=3, effektív fps = fps/3). A kockaszám-küszöbbel ítélő",
        "rétegek ugyanarról a meccsről ritkítva másképp — jellemzően",
        "óvatosabban — ítélhetnek. Ez a lista a döntés alapja, hol",
        "érdemes a kockaszám-küszöböt másodperc-alapúra váltani.",
        "",
        f"Mérés: {seconds:.0f} mp-es szimulált meccs (mag: {seed}), "
        f"sűrű (25 fps) vs {stride}-as ritkítás; "
        f"**{res['checked']} réteg** összevetve, ebből "
        f"**{len(res['differs'])} eltérő ítéletű**.",
        "",
        "## Fontos: mit jelent az eltérés",
        "",
        "Az eltérés NEM feltétlenül hiba: a ritkított meccsen kevesebb a",
        "minta, és a \"kevés mintánál nincs ítélet\" elv pont ezt",
        "kívánja. A lista arra való, hogy a küszöb-kalibrálás tudatos",
        "legyen — a termék alap-stride-jánál (3) a kocka-küszöbök",
        "háromszor annyi valós időt követelnek.",
        "",
    ]
    if res["differs"]:
        lines += ["## Eltérő ítéletű rétegek", ""]
        for d in res["differs"]:
            lines.append(f"### `{d['layer']}`")
            lines.append("")
            for c in d["changes"][:6]:
                lines.append(f"- `{c['path']}`: sűrűn `{c['dense']}` → "
                             f"ritkítva `{c['strided']}`")
            if len(d["changes"]) > 6:
                lines.append(f"- … és még {len(d['changes']) - 6} eltérés")
            lines.append("")
    else:
        lines += ["## Eltérő ítéletű réteg: nincs", ""]
    if res["failed"]:
        lines += ["## Nem mérhető (hibára futott)", ""]
        lines += [f"- `{n}`" for n in sorted(res["failed"])]
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seconds", type=float, default=DEFAULT_SECONDS)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--stride", type=int, default=DEFAULT_STRIDE)
    args = ap.parse_args(argv)

    res = measure(args.seconds, args.seed, stride=args.stride)
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(build_report(res, args.seconds, args.seed, args.stride),
                    encoding="utf-8")
    print(f"Stride-jelentés kiírva: {_OUT}")
    print(f"  összevetve: {res['checked']} réteg")
    print(f"  eltérő ítéletű: {len(res['differs'])}")
    for d in res["differs"][:20]:
        print(f"    - {d['layer']} ({len(d['changes'])} eltérés)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
