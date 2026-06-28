"""
[H] Statisztikák — alap mérőszámok a kész Tracking-ből.

Feladata: a kész Match (Tracking) objektumból edzőnek hasznos, egyszerű
statisztikákat számolni: futott táv, sebesség, hőtérkép-adat — játékosonként.

Ez TISZTA adatfeldolgozás (nincs ML), ezért itt már valódi (nem placeholder)
számítás is lehet. Egyelőre a futott távot és az átlagsebességet számoljuk;
ezek a méteres koordinátákból és az fps-ből közvetlenül adódnak.

Fontos: a BECSÜLT (source=ESTIMATED) szakaszokat külön jelöljük/kezeljük, hogy a
becslés ne hamisítsa meg a statisztikát (a becsült mozgás nem valódi mérés).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..models.tracking import Match, PositionSource


@dataclass
class PlayerStats:
    """Egy játékos összesített statisztikái a meccsen.

    - track_id:            a játékos azonosítója.
    - distance_m:          összes MÉRT szakaszokból számolt futott táv (méter).
    - avg_speed_ms:        átlagsebesség (m/s) a mért mozgásból.
    - measured_frames:     hány frame-en volt MÉRT (látott) a játékos.
    - estimated_frames:    hány frame-en volt csak BECSÜLT.
    """
    track_id: int
    distance_m: float = 0.0
    avg_speed_ms: float = 0.0
    measured_frames: int = 0
    estimated_frames: int = 0


def compute_player_stats(match: Match) -> dict[int, PlayerStats]:
    """Játékosonkénti statisztikát számol a teljes Match-ből.

    Módszer:
    - track_id szerint összegyűjtjük a pozíciókat időrendben,
    - egymást követő MÉRT pozíciók közti euklideszi távolságot összeadjuk (méter),
    - a sebességet a táv / eltelt idő (fps-ből) adja.

    A becsült pozíciókat NEM számoljuk bele a távba (csak jelöljük a darabszámot),
    nehogy a becslés meghamisítsa a futott távot.
    """
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    dt = 1.0 / fps  # egy frame időtartama másodpercben

    # track_id -> időrendi pozíciólista (t, x, y, source)
    by_player: dict[int, list[tuple[int, float, float, PositionSource]]] = {}
    for frame in match.frames:
        for p in frame.players:
            by_player.setdefault(p.track_id, []).append((frame.t, p.x, p.y, p.source))

    result: dict[int, PlayerStats] = {}
    for track_id, samples in by_player.items():
        samples.sort(key=lambda s: s[0])  # idő szerint rendezve
        stats = PlayerStats(track_id=track_id)
        prev = None
        for (t, x, y, source) in samples:
            if source == PositionSource.MEASURED:
                stats.measured_frames += 1
            else:
                stats.estimated_frames += 1
            # Távot csak két egymást követő MÉRT pont között számolunk.
            if prev is not None and prev[3] == PositionSource.MEASURED and source == PositionSource.MEASURED:
                stats.distance_m += math.hypot(x - prev[1], y - prev[2])
            prev = (t, x, y, source)
        # Átlagsebesség: a futott táv osztva a mért szakaszok idejével.
        moving_time = max(1, stats.measured_frames) * dt
        stats.avg_speed_ms = stats.distance_m / moving_time
        result[track_id] = stats
    return result
