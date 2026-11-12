"""Sebesség-profil — mennyi idő a réteg-csomag egy teljes meccsen.

Miért kell ez? Az edző nem vár órákat: a kész termék sebesség-célja,
hogy egy 60 perces meccs TELJES elemzése (felismerés + minden réteg)
a pilot GPU-s szerverén 15 percen belül, a "gyors kép" (eredmény,
lövés-térkép, edzői összefoglaló) 3 percen belül kész legyen
(`docs/ROADMAP.md`, "Sebesség-cél"). Ez a szkript a RÉTEG-részt méri:
a kész követésből a 500+ elemző réteg kiértékelése mennyi idő — tehát
azt, ami a motor sajátja, és nem a GPU-tól függ. A felismerés
(detektálás) idejét a pilot valódi felvételen méri, külön sorban.

Módszer: egy szimulált, teljes hosszú meccs a termék alap-ritkításával
(fps = 25/3), a termék gyorsítótár-hatókörében (`primitive_cache`,
ahogy a meccs-csomag futtatja), rétegenként mért idővel. A kimenet a
docs/SEBESSEG.md (a lassú rétegek rangsora) és — `--jegyzokonyv`
kapcsolóval — egy dátumozott sor a mérési jegyzőkönyv Sebesség
táblájában.

A szám GÉPFÜGGŐ (laptop vs. szerver), ezért a jelentést NEM őrzi teszt
— a mechanikát (`tests/test_speed_profile.py`) igen. A cél-küszöb a
réteg-részre: SEBESSEG_CEL_RETEGEK_S.

Használat:
    cd backend && python -m scripts.speed_profile                 # 60 perc
    cd backend && python -m scripts.speed_profile --seconds 600   # gyors
    cd backend && python -m scripts.speed_profile --jegyzokonyv   # + sor
"""

from __future__ import annotations

import argparse
import datetime as _dt
import importlib
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_OUT = _BACKEND.parent / "docs" / "SEBESSEG.md"
_JEGYZOKONYV = _BACKEND.parent / "docs" / "MERESI_JEGYZOKONYV.md"

# Egy teljes meccs: 2 × 30 perc játékidő.
DEFAULT_SECONDS = 3600.0
DEFAULT_SEED = 7
# A termék alap-ritkítása: minden 3. kocka a 25 fps-es forrásból.
DEFAULT_FPS = 25.0 / 3.0
# Valós meccstempó: két csapatra ~50-60 lövés egy meccsen.
DEFAULT_SHOTS_PER_MIN = 1.0

# A sebesség-cél a KÉSZ termékre (docs/ROADMAP.md, "Sebesség-cél"):
# 60 perces meccs teljes elemzése ≤ 15 perc a pilot GPU-s szerverén,
# a gyors kép ≤ 3 perc. A réteg-rész ebből legfeljebb ennyi lehet CPU-n
# (laptopon is), hogy a többi a felismerésnek maradjon:
SEBESSEG_CEL_TELJES_S = 15 * 60.0
SEBESSEG_CEL_GYORS_KEP_S = 3 * 60.0
SEBESSEG_CEL_RETEGEK_S = 5 * 60.0
# A "gyors kép" rétegei: amit az edző a meccs után először néz meg.
GYORS_KEP_RETEGEK = ("coach_summary", "xg", "defense", "training_focus")
# A rangsorban ennyi leglassabb réteget sorolunk fel.
TOP_N = 15


def _gep_leiras() -> str:
    """A mérés gépe egy sorban (processzor + Python) — a szám csak
    ezzel együtt értelmezhető."""
    cpu = platform.processor() or platform.machine() or "?"
    try:
        n = __import__("os").cpu_count() or 0
    except Exception:
        n = 0
    return f"{cpu}, {n} mag, Python {platform.python_version()}"


def _verzio() -> str:
    """Verzió-címke: a CHANGELOG utolsó kiadott verziója + a rövid
    commit-hash (így a kiadás óta fejlődött kód is azonosítható)."""
    ver = "dev"
    try:
        cl = (_BACKEND.parent / "CHANGELOG.md").read_text(encoding="utf-8")
        m = re.search(r"^## (v\d+\.\d+\.\d+) — kiadva", cl, re.M)
        if m:
            ver = m.group(1)
    except Exception:
        pass
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=5,
                             cwd=str(_BACKEND))
        h = out.stdout.strip()
        return f"{ver}+{h}" if h else ver
    except Exception:
        return ver


def measure(seconds: float = DEFAULT_SECONDS, seed: int = DEFAULT_SEED,
            fps: float = DEFAULT_FPS,
            shots_per_min: float = DEFAULT_SHOTS_PER_MIN,
            only: tuple[str, ...] = ()) -> dict:
    """A réteg-csomag időmérése egy szimulált meccsen.

    Visszatérés: {"seconds", "fps", "frames", "szimulacio_s",
    "retegek": [(név, mp) | (név, None) hibánál], "osszes_s",
    "gyors_kep_s", "hibas": [név, ...]} — a rétegek a termék
    gyorsítótár-hatókörében futnak, a mért idő a tiszta kiértékelés.
    """
    from handball.pipeline.primitive_cache import primitive_cache
    from handball.sim.match_simulator import simulate_ground_truth
    from scripts.order_sensitivity import _layer_functions

    t0 = time.perf_counter()
    match = simulate_ground_truth(duration_s=seconds, fps=fps, seed=seed,
                                  shots_per_min=shots_per_min)
    szimulacio_s = time.perf_counter() - t0

    csak = set(only)
    retegek: list[tuple[str, float | None]] = []
    hibas: list[str] = []
    gyors_kep_s = 0.0
    osszes_s = 0.0
    with primitive_cache(match):
        for name, mod_name, fn_name in _layer_functions():
            if csak and name not in csak:
                continue
            try:
                mod = importlib.import_module(f"handball.pipeline.{mod_name}")
                fn = getattr(mod, fn_name)
            except Exception:
                hibas.append(name)
                retegek.append((name, None))
                continue
            t1 = time.perf_counter()
            try:
                fn(match)
            except Exception:
                hibas.append(name)
                retegek.append((name, None))
                continue
            dt = time.perf_counter() - t1
            osszes_s += dt
            if name in GYORS_KEP_RETEGEK:
                gyors_kep_s += dt
            retegek.append((name, dt))
    return {"seconds": seconds, "fps": fps, "frames": len(match.frames),
            "szimulacio_s": szimulacio_s, "retegek": retegek,
            "osszes_s": osszes_s, "gyors_kep_s": gyors_kep_s,
            "hibas": hibas}


def _ido(s: float) -> str:
    """Másodperc ember-olvasható alakban: 120 ms / 0,8 mp / 2 perc 15 mp."""
    if s < 1:
        return f"{s * 1000:.0f} ms"
    if s < 60:
        return f"{s:.1f} mp".replace(".", ",")
    m, r = divmod(int(round(s)), 60)
    return f"{m} perc {r} mp" if r else f"{m} perc"


def itelet(res: dict) -> str:
    """MEGFELEL, ha a réteg-rész a cél-küszöbön belül van (a teljes
    meccsre vetítve — rövidebb mérésnél arányosítva), különben GYENGE."""
    arany = DEFAULT_SECONDS / max(res["seconds"], 1.0)
    vetitett = res["osszes_s"] * arany
    return "MEGFELEL" if vetitett <= SEBESSEG_CEL_RETEGEK_S else "GYENGE"


def build_report(res: dict, verzio: str, gep: str) -> str:
    mert = [(n, t) for n, t in res["retegek"] if t is not None]
    lassu = sorted(mert, key=lambda x: -x[1])[:TOP_N]
    n = len(mert)
    atlag = res["osszes_s"] / n if n else 0.0
    lines = [
        "# Sebesség-profil — a réteg-csomag ideje egy teljes meccsen",
        "",
        "*Generált fájl — ne kézzel szerkeszd. Frissítés:*",
        "`cd backend && python -m scripts.speed_profile`",
        "",
        "A kész termék sebesség-célja (`docs/ROADMAP.md`, \"Sebesség-cél\"):",
        f"egy 60 perces meccs TELJES elemzése ≤ {_ido(SEBESSEG_CEL_TELJES_S)}",
        f"a pilot GPU-s szerverén, a gyors kép ≤ {_ido(SEBESSEG_CEL_GYORS_KEP_S)}.",
        "Ez a lap a RÉTEG-részt méri (kész követésből a 500+ elemző réteg),",
        f"amelyre a keret ≤ {_ido(SEBESSEG_CEL_RETEGEK_S)} CPU-n — a többi a",
        "felismerésé, azt a pilot valódi felvételen méri.",
        "",
        f"Mérés: {res['seconds']:.0f} mp-es szimulált meccs, "
        f"{res['fps']:.2f} fps (a termék ritkítása), {res['frames']} kocka; "
        f"verzió {verzio}; gép: {gep}.",
        "",
        f"- **Rétegek összesen: {_ido(res['osszes_s'])}** ({n} réteg, "
        f"átlag {atlag * 1000:.0f} ms) — ítélet: **{itelet(res)}**",
        f"- Gyors kép ({', '.join(GYORS_KEP_RETEGEK)}): "
        f"{_ido(res['gyors_kep_s'])}",
        f"- Szimuláció (nem a termék része): {_ido(res['szimulacio_s'])}",
    ]
    if res["hibas"]:
        lines.append(f"- Hibára futott / kihagyott: {len(res['hibas'])} "
                     f"({', '.join(sorted(res['hibas'])[:8])}"
                     f"{', …' if len(res['hibas']) > 8 else ''})")
    lines += ["", f"## A {len(lassu)} leglassabb réteg", "",
              "| Réteg | Idő | A csomag %-a |", "|---|---|---|"]
    for name, t in lassu:
        pct = 100.0 * t / res["osszes_s"] if res["osszes_s"] else 0.0
        lines.append(f"| `{name}` | {_ido(t)} | {pct:.1f}% |")
    lines += [
        "",
        "## Olvasat",
        "",
        "A réteg-csomag ideje a kocka-számmal nő: a lassú rétegek a",
        "kockánként dolgozó alap-mérések (lövés-felismerés, poszt-becslés,",
        "formáció), amelyeket a `primitive_cache` hatókör meccsenként",
        "egyszer számol — a csomagban tehát a fenti összeg a felső",
        "korlát, a megosztott mérések miatt a valóság kevesebb. Ha egy",
        "réteg a csomag több mint 10%-át viszi, az a gyorsítás első",
        "jelöltje (gyorsítótárazott alap-mérés, időablakos számolás).",
        "",
    ]
    return "\n".join(lines)


def jegyzokonyv_sor(res: dict, verzio: str, gep: str,
                    datum: str | None = None) -> str:
    """Egy sor a mérési jegyzőkönyv Sebesség táblájába."""
    datum = datum or _dt.date.today().isoformat()
    mert = sum(1 for _, t in res["retegek"] if t is not None)
    return (f"| {datum} | {verzio} | szimulált, {res['seconds'] / 60:.0f} perc, "
            f"{res['frames']} kocka | {mert} | {_ido(res['osszes_s'])} | "
            f"{_ido(res['gyors_kep_s'])} | {gep} | {itelet(res)} |")


SEBESSEG_FEJLEC = "| Dátum | Verzió | Felvétel | Rétegek | Réteg-csomag | Gyors kép | Gép | Ítélet |"


def append_jegyzokonyv(sor: str, path: Path = _JEGYZOKONYV) -> None:
    """A sort a jegyzőkönyv Sebesség táblájának VÉGÉRE fűzi (a tábla
    fejlécét a dokumentum tartalmazza; ha nincs, hiba — ne találjunk
    ki szerkezetet)."""
    text = path.read_text(encoding="utf-8")
    if SEBESSEG_FEJLEC not in text:
        raise SystemExit("a jegyzőkönyvben nincs Sebesség tábla "
                         f"({SEBESSEG_FEJLEC!r})")
    head, tail = text.split(SEBESSEG_FEJLEC, 1)
    lines = tail.split("\n")
    i = 1  # a 0. az elválasztó |---| sor
    while i < len(lines) and lines[i].startswith("|"):
        i += 1
    lines.insert(i, sor)
    path.write_text(head + SEBESSEG_FEJLEC + "\n".join(lines),
                    encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seconds", type=float, default=DEFAULT_SECONDS)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--fps", type=float, default=DEFAULT_FPS)
    ap.add_argument("--shots-per-min", type=float,
                    default=DEFAULT_SHOTS_PER_MIN)
    ap.add_argument("--only", default="",
                    help="vesszővel elválasztott réteg-nevek (gyors kör)")
    ap.add_argument("--jegyzokonyv", action="store_true",
                    help="sor a docs/MERESI_JEGYZOKONYV.md Sebesség táblájába")
    ap.add_argument("--no-write", action="store_true",
                    help="ne írja a docs/SEBESSEG.md-t, csak kiírja")
    args = ap.parse_args(argv)

    only = tuple(n for n in args.only.split(",") if n)
    res = measure(args.seconds, args.seed, args.fps, args.shots_per_min, only)
    verzio, gep = _verzio(), _gep_leiras()
    report = build_report(res, verzio, gep)
    print(report)
    if not args.no_write and not only:
        _OUT.write_text(report + "\n", encoding="utf-8")
        print(f"\nKiírva: {_OUT}")
    if args.jegyzokonyv:
        sor = jegyzokonyv_sor(res, verzio, gep)
        append_jegyzokonyv(sor)
        print(f"Jegyzőkönyv-sor: {sor}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
