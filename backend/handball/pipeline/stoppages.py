"""Játékmegszakítás / időkérés felismerése — mikor állt le a játék.

Az időkérés (és általában a hosszabb megszakítás) a követésben úgy
látszik, hogy a pályán lévő játékosok TARTÓSAN egy helyben állnak — a
normál játékban ez sosem fordul elő. A jel:

- legalább MIN_VISIBLE játékos látszik (üres/pásztázó képkocka nem
  "leállás", csak követés-vesztés), és
- az átlagos mozgás-sebességük STOP_SPEED_MS alatt van,
- mindez legalább TIMEOUT_MIN_S ideig folyamatosan (rövid lyukakat
  összevonva).

A TIMEOUT_LONG_S-nél hosszabb leállás jellemzően nem időkérés, hanem
hosszabb megszakítás (sérülés, félidő) — külön címkét kap. Az időkérést
tipikusan a támadó csapat kéri, ezért a leállás ELŐTTI birtoklásból
"valószínű kérő" csapatot is jelzünk.
"""

from __future__ import annotations

import math
from typing import Optional

from ..models.tracking import Match
from .tactics import TacticsConfig

STOP_SPEED_MS = 0.4     # ez alatt "állnak" a játékosok
MIN_VISIBLE = 6         # ennyi látható játékos kell a megbízható jelhez
TIMEOUT_MIN_S = 15.0    # legalább ennyi állás = megszakítás
TIMEOUT_LONG_S = 120.0  # e felett már nem időkérés (sérülés/félidő)
JOIN_S = 1.5            # ennél rövidebb "megmozdulást" összevonunk
PRE_WINDOW_S = 3.0      # a leállás előtti birtoklás-ablak (ki kérhette)


def detect_stoppages(match: Match,
                     config: Optional[TacticsConfig] = None) -> list[dict]:
    """Játékmegszakítások időrendben.

    Visszatérés: [{"start_frame", "end_frame", "duration_s",
    "kind": "időkérés" | "hosszú megszakítás",
    "likely_team": "home"/"away"/None}]."""
    from .tactics import possession_team

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    frames = match.frames
    if len(frames) < 2:
        return []

    # Kockánként: "áll-e a játék" (elég játékos látszik, és nem mozognak).
    stopped: list[bool] = [False]
    prev = {p.track_id: (p.x, p.y) for p in frames[0].players}
    for f in frames[1:]:
        cur = {p.track_id: (p.x, p.y) for p in f.players}
        speeds = [math.hypot(x - prev[t][0], y - prev[t][1]) * fps
                  for t, (x, y) in cur.items() if t in prev]
        ok = (len(cur) >= MIN_VISIBLE and speeds
              and sum(speeds) / len(speeds) < STOP_SPEED_MS)
        stopped.append(bool(ok))
        prev = cur

    # Összefüggő leállás-szakaszok, rövid lyukak összevonásával.
    join = max(1, round(JOIN_S * fps))
    need = max(2, round(TIMEOUT_MIN_S * fps))
    runs: list[list[int]] = []
    start = None
    for i, on in enumerate(stopped):
        if on and start is None:
            start = i
        elif not on and start is not None:
            runs.append([start, i - 1])
            start = None
    if start is not None:
        runs.append([start, len(stopped) - 1])
    merged: list[list[int]] = []
    for r in runs:
        if merged and r[0] - merged[-1][1] <= join:
            merged[-1][1] = r[1]
        else:
            merged.append(r)

    out: list[dict] = []
    pre = round(PRE_WINDOW_S * fps)
    for (a, b) in merged:
        if b - a + 1 < need:
            continue
        dur_s = (b - a + 1) / fps
        # Ki kérhette: a leállás előtti pár másodperc többségi birtoklása.
        tally = {"home": 0, "away": 0}
        for f in frames[max(0, a - pre):a]:
            t = possession_team(f, config)
            if t is not None:
                tally[t.value] += 1
        likely = max(tally, key=tally.get) if any(tally.values()) else None
        out.append({
            "start_frame": frames[a].t,
            "end_frame": frames[b].t,
            "duration_s": round(dur_s, 1),
            "kind": ("időkérés" if dur_s <= TIMEOUT_LONG_S
                     else "hosszú megszakítás"),
            "likely_team": likely,
        })
    return out
