"""
Szintetikus meccs generálása — futtatható, videó nélkül.

Előállít egy valósághű meccset (földi igazság), majd egy pásztázó-kamerás
változatot (a valódi becslővel), és kiírja a Tracking JSON-t. Ezzel a Flutter-
kliens és a downstream elemzés valós adaton fejleszthető.

Használat:
    python -m scripts.simulate_match                 # összefoglaló a kimenetre
    python -m scripts.simulate_match match.json      # pásztázó-kamerás Tracking fájlba
    python -m scripts.simulate_match match.json --ground-truth   # a teljes földi igazság

Opciók (egyszerű, pozíció után): --seconds N  --fps N  --seed N  --fov M
"""

from __future__ import annotations

import sys

from handball.sim import simulate_ground_truth, simulate_with_panning_camera
from handball.pipeline.pipeline import summarize
from handball.models.tracking import PositionSource


def _arg(argv, name, default, cast):
    """Egyszerű opció-kiolvasás: --name ERTEK."""
    if name in argv:
        return cast(argv[argv.index(name) + 1])
    return default


def main(argv: list[str]) -> int:
    seconds = _arg(argv, "--seconds", 8.0, float)
    fps = _arg(argv, "--fps", 25.0, float)
    seed = _arg(argv, "--seed", 0, int)
    fov = _arg(argv, "--fov", 18.0, float)
    want_ground_truth = "--ground-truth" in argv

    # Az első nem-opciós argumentum a kimeneti fájl (ha van).
    out_path = None
    for a in argv[1:]:
        if not a.startswith("--") and (argv[argv.index(a) - 1] not in ("--seconds", "--fps", "--seed", "--fov")):
            out_path = a
            break

    ground = simulate_ground_truth(duration_s=seconds, fps=fps, seed=seed)
    panned = simulate_with_panning_camera(ground, fov_width_m=fov)

    result = ground if want_ground_truth else panned
    json_text = result.to_json(indent=2)

    if out_path:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(json_text)
        print(f"Tracking JSON kiírva: {out_path} "
              f"({'földi igazság' if want_ground_truth else 'pásztázó kamera'})")
    else:
        # JSON nélkül: csak összefoglaló, hogy ne öntsük tele a kimenetet.
        print(f"Szimulált meccs: {len(ground.frames)} frame, fps={fps}, seed={seed}")

    # Összefoglaló: mennyi a mért vs. becsült a pásztázó-kamerás változatban.
    total = meas = est = 0
    for fr in panned.frames:
        for p in fr.players:
            total += 1
            if p.source == PositionSource.MEASURED:
                meas += 1
            else:
                est += 1
    print(f"Pásztázó kamera: {total} játékos-pozíció összesen — "
          f"mért={meas} ({100*meas//max(1,total)}%), becsült={est} ({100*est//max(1,total)}%)")

    stats = summarize(panned)
    print("\n--- Néhány játékos statisztika (pásztázó kamera) ---")
    for track_id, s in sorted(stats.items())[:5]:
        print(f"  #{track_id}: táv={s.distance_m:.1f} m, átlagseb={s.avg_speed_ms:.2f} m/s, "
              f"mért={s.measured_frames}, becsült={s.estimated_frames}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
