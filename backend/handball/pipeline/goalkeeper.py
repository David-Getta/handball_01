"""[D2] Kapus-azonosítás pozíció-prior alapján.

A kapus mezszín-alapú felismerése törékeny (a kapus-szín meccsenként más,
és a színklaszterezés két csapatra van hangolva). Amit viszont a kész
Match-ből BIZTOSAN tudunk: a kapus az idejének túlnyomó részét a saját
kapuelőterében tölti — egyetlen mezőnyjátékos sem teszi ezt (a 6 m-esen
belül támadóként tartózkodni szabálytalan, védőként átmeneti).

Módszer: trackenként megmérjük, a MÉRT idejének mekkora hányada esik a
két kapu köré rajzolt körbe. Kapunként a legnagyobb hányadú track kap
"kapus" szerepet, ha a hányad és a minta is elég nagy. A döntés a track
MINDEN pozíciójára rákerül (role="kapus") — a kliens jelölheti, az
elemzések (pl. felderítés kulcsjátékosai) pedig figyelembe vehetik.

Korlát: ha egy track átível a félidőn (térfélcsere), a hányad felhígul —
a gyakorlatban a felvételek félidőnként készülnek, és a követés a
szünetben úgyis megszakad. Tiszta adatfeldolgozás, videó nélkül tesztelhető.
"""

from __future__ import annotations

import math

from ..models.tracking import Match, PositionSource
from .calibration import COURT_LENGTH_M, COURT_WIDTH_M

# A kapuelőtér sugara + ráhagyás (a 6 m-es vonalon kicsit kívülre is kilép).
GOAL_AREA_RADIUS_M = 6.8
# A mért idejének legalább ekkora hányada a kapuelőtérben → kapus-jelölt.
MIN_SHARE = 0.55
# Legalább ennyi mért jelenlét (mp) kell a döntéshez (zajos rövid track ne).
MIN_SECONDS = 8.0

ROLE_GOALKEEPER = "kapus"


def detect_goalkeepers(match: Match,
                       radius_m: float = GOAL_AREA_RADIUS_M,
                       min_share: float = MIN_SHARE,
                       min_seconds: float = MIN_SECONDS) -> dict[int, float]:
    """Kapusok azonosítása és megjelölése (helyben, role="kapus").

    Kapunként (bal: x=0, jobb: x=40) legfeljebb EGY track kap kapus
    szerepet — az, amelyik a mért idejének legnagyobb (és legalább
    `min_share`) hányadát tölti az adott kapuelőtérben.

    Visszatérés: {track_id: kapuelőtér-hányad} a megjelölt kapusokra.
    """
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    goals = ((0.0, COURT_WIDTH_M / 2.0), (COURT_LENGTH_M, COURT_WIDTH_M / 2.0))

    # Trackenként: mért kockák + kapunkénti "bent volt" kockák.
    total: dict[int, int] = {}
    in_area: dict[int, list[int]] = {}
    for frame in match.frames:
        for p in frame.players:
            if p.source != PositionSource.MEASURED:
                continue
            total[p.track_id] = total.get(p.track_id, 0) + 1
            rec = in_area.setdefault(p.track_id, [0, 0])
            for gi, (gx, gy) in enumerate(goals):
                if math.hypot(p.x - gx, p.y - gy) <= radius_m:
                    rec[gi] += 1

    min_frames = max(1, round(min_seconds * fps))
    chosen: dict[int, float] = {}
    for gi in range(2):
        best_tid = None
        best_share = 0.0
        for tid, n in total.items():
            if n < min_frames:
                continue
            share = in_area.get(tid, [0, 0])[gi] / n
            if share >= min_share and share > best_share:
                best_tid, best_share = tid, share
        if best_tid is not None:
            # Ha ugyanaz a track mindkét kapunál "nyerne" (nem életszerű),
            # a nagyobb hányad marad.
            if chosen.get(best_tid, 0.0) < best_share:
                chosen[best_tid] = best_share

    if chosen:
        for frame in match.frames:
            for p in frame.players:
                if p.track_id in chosen:
                    p.role = ROLE_GOALKEEPER
    return chosen
