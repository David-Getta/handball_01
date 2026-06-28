"""
Futtatható belépési pont — demonstrálja a kész adatszerződést (Tracking JSON).

Amíg a valódi modellek (YOLO, követés) nincsenek beépítve, ez a script egy
SZINTETIKUS Match-et épít (néhány frame, mért + becsült játékos, labda), kiírja
JSON-ba, és kiszámolja a statisztikát. Így:
- látszik, milyen JSON-t fog kapni a Flutter-kliens,
- a teljes lánc (modell -> szerializáció -> statisztika) végigfut és tesztelhető.

Használat:
    python -m scripts.run_pipeline            # JSON a kimenetre
    python -m scripts.run_pipeline out.json   # JSON fájlba

Később ezt a szintetikus építést a HandballPipeline.run(video_path, ...) váltja fel.
"""

from __future__ import annotations

import sys

from handball.models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, Ball, Team, PositionSource,
)
from handball.pipeline.pipeline import summarize


def build_demo_match() -> Match:
    """Egy kicsi, valósághű szerkezetű minta-Match összeállítása.

    Két frame, két csapat néhány játékosa: az egyik vendég-játékos a 2. frame-en
    BECSÜLT (mintha kicsúszott volna a képből) — így a kliens megjelenítésében is
    tesztelhető a mért vs. becsült különbség.
    """
    meta = MatchMeta(
        match_id="demo-001",
        home_team="Hazai KC",
        away_team="Vendég SE",
        fps=25.0,
        frame_width=1920,
        frame_height=1080,
        date="2026-06-28",
    )

    # 1. frame: minden játékos MÉRT (látott).
    frame0 = Frame(
        t=0,
        players=[
            PlayerPosition(track_id=1, team=Team.HOME, x=10.0, y=8.0, jersey_number=7),
            PlayerPosition(track_id=2, team=Team.HOME, x=12.0, y=12.0, jersey_number=9),
            PlayerPosition(track_id=11, team=Team.AWAY, x=28.0, y=9.0, jersey_number=4),
        ],
        ball=Ball(x=11.0, y=10.0),
    )

    # 2. frame: a 11-es vendég játékos BECSÜLT (képen kívülre került).
    frame1 = Frame(
        t=1,
        players=[
            PlayerPosition(track_id=1, team=Team.HOME, x=10.5, y=8.2, jersey_number=7),
            PlayerPosition(track_id=2, team=Team.HOME, x=12.4, y=12.1, jersey_number=9),
            PlayerPosition(
                track_id=11, team=Team.AWAY, x=28.3, y=9.1, jersey_number=4,
                source=PositionSource.ESTIMATED, confidence=0.6,
            ),
        ],
        ball=Ball(x=11.5, y=10.2, confidence=0.8),
    )

    return Match(meta=meta, frames=[frame0, frame1])


def main(argv: list[str]) -> int:
    match = build_demo_match()
    json_text = match.to_json(indent=2)

    # Kiírás: fájlba, ha kaptunk útvonalat, különben a kimenetre.
    if len(argv) > 1:
        with open(argv[1], "w", encoding="utf-8") as f:
            f.write(json_text)
        print(f"Tracking JSON kiírva: {argv[1]}")
    else:
        print(json_text)

    # Statisztika a kész Match-ből (táv, sebesség játékosonként).
    stats = summarize(match)
    print("\n--- Statisztika (demo) ---")
    for track_id, s in sorted(stats.items()):
        print(f"  #{track_id}: táv={s.distance_m:.2f} m, "
              f"átlagseb={s.avg_speed_ms:.2f} m/s, "
              f"mért={s.measured_frames}, becsült={s.estimated_frames}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
