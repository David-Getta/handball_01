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

from ..models.tracking import Match, PositionSource, Team


@dataclass
class PlayerStats:
    """Egy játékos összesített statisztikái a meccsen.

    - track_id:            a játékos azonosítója.
    - distance_m:          összes MÉRT szakaszokból számolt futott táv (méter).
    - avg_speed_ms:        átlagsebesség (m/s) a mért mozgásból.
    - measured_frames:     hány frame-en volt MÉRT (látott) a játékos.
    - estimated_frames:    hány frame-en volt csak BECSÜLT.
    - top_speed_ms:        legnagyobb (simított) sebesség (m/s) — terhelés-monitor.
    - sprint_count:        hány sprint (tartósan >= küszöb sebességű szakasz).
    - sprint_distance_m:   a sprintekben megtett táv (méter).
    - zone_seconds:        sebesség-zónánkénti idő (mp): seta/kocogas/futas/sprint.
    """
    track_id: int
    distance_m: float = 0.0
    avg_speed_ms: float = 0.0
    measured_frames: int = 0
    estimated_frames: int = 0
    top_speed_ms: float = 0.0
    sprint_count: int = 0
    sprint_distance_m: float = 0.0
    zone_seconds: dict = field(default_factory=dict)


# Sprint-elemzés küszöbei (kézilabdára hangolva):
SPRINT_SPEED_MS = 5.0      # e fölött számít sprintnek a mozgás (m/s)
SPRINT_MIN_S = 0.5         # legalább ennyi ideig kell tartania (mp)
MAX_PLAUSIBLE_MS = 11.0    # efölötti "sebesség" követési hiba (ugrás) — kihagyjuk
# Sebesség-zónák határai (m/s): séta < 1.4 <= kocogás < 3.0 <= futás < 5.0 <= sprint
ZONE_EDGES = ((1.4, "seta"), (3.0, "kocogas"), (5.0, "futas"))


def _speed_segments(samples: list, dt: float) -> list[tuple[float, float, float]]:
    """A MÉRT pontpárok közti (idő mp, táv m, simított sebesség m/s) szakaszok.

    Csak kis időbeli lyukat hidalunk át (max 3 feldolgozott kocka), a
    valószínűtlenül nagy sebességű (követési hibás) szakaszokat kihagyjuk.
    A sebességet 3 szakaszos mozgóátlaggal simítjuk, hogy egy-egy zajos
    pozíció ne dobjon fals csúcssebességet."""
    raw: list[tuple[float, float]] = []  # (szakasz-idő mp, táv m)
    prev = None
    for (t, x, y, source) in samples:
        if source != PositionSource.MEASURED:
            continue
        if prev is not None:
            gap = t - prev[0]
            if 0 < gap <= 3:
                seconds = gap * dt
                dist = math.hypot(x - prev[1], y - prev[2])
                if seconds > 0 and dist / seconds <= MAX_PLAUSIBLE_MS:
                    raw.append((seconds, dist))
        prev = (t, x, y)
    out: list[tuple[float, float, float]] = []
    for i, (seconds, dist) in enumerate(raw):
        window = raw[max(0, i - 1):i + 2]
        wsec = sum(s for s, _ in window)
        wdist = sum(d for _, d in window)
        out.append((seconds, dist, (wdist / wsec) if wsec > 0 else 0.0))
    return out


def _sprint_and_zones(stats: PlayerStats, segments: list) -> None:
    """Csúcssebesség, sprintek és zóna-idők a szakaszlistából (helyben ír)."""
    zones = {"seta": 0.0, "kocogas": 0.0, "futas": 0.0, "sprint": 0.0}
    run_s = 0.0   # a folyamatban lévő sprint hossza (mp)
    run_d = 0.0   # ... és távja (m)

    def close_run():
        nonlocal run_s, run_d
        if run_s >= SPRINT_MIN_S:
            stats.sprint_count += 1
            stats.sprint_distance_m += run_d
        run_s = run_d = 0.0

    for (seconds, dist, speed) in segments:
        stats.top_speed_ms = max(stats.top_speed_ms, speed)
        zone = "sprint"
        for edge, name in ZONE_EDGES:
            if speed < edge:
                zone = name
                break
        zones[zone] += seconds
        if speed >= SPRINT_SPEED_MS:
            run_s += seconds
            run_d += dist
        else:
            close_run()
    close_run()
    stats.zone_seconds = {k: round(v, 1) for k, v in zones.items()}


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
        # Terhelés-monitor: csúcssebesség, sprintek és sebesség-zónák.
        _sprint_and_zones(stats, _speed_segments(samples, dt))
        result[track_id] = stats
    return result


def compute_intensity_timeline(match: Match, window_s: float = 300.0) -> list[dict]:
    """Intenzitás-idővonal: a meccset idő-ablakokra bontva csapatonként az
    átlagos mozgás-sebesség (m/s) — ebből látszik, mikor esett vissza a
    tempó (fáradás, letámadás hatása). A kliens court_analytics tükre.

    Csak MÉRT, hihető (<= MAX_PLAUSIBLE_MS) szakaszokból számol, legfeljebb
    3 kockányi lyukat áthidalva — mint a játékos-statisztika. Rövid
    felvételnél az ablak zsugorodik, hogy legalább ~6 pont legyen.

    Visszatérés: [{"start_frame", "home_avg_ms", "away_avg_ms"}, ...]
    """
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    dt = 1.0 / fps
    total = len(match.frames)
    if total < 2:
        return []
    dur_s = total / fps
    win_s = min(window_s, max(5.0, dur_s / 6)) if dur_s / window_s < 6 else window_s
    win_frames = max(1, min(total, round(win_s * fps)))
    n_win = (total + win_frames - 1) // win_frames

    dist = [[0.0, 0.0] for _ in range(n_win)]
    time_ = [[0.0, 0.0] for _ in range(n_win)]

    by_player: dict[int, list] = {}
    for frame in match.frames:
        for p in frame.players:
            if p.source != PositionSource.MEASURED:
                continue
            by_player.setdefault(p.track_id, []).append((frame.t, p.x, p.y, p.team))
    for samples in by_player.values():
        samples.sort(key=lambda s: s[0])
        for (a, b) in zip(samples, samples[1:]):
            gap = b[0] - a[0]
            if gap <= 0 or gap > 3:
                continue
            seconds = gap * dt
            d = math.hypot(b[1] - a[1], b[2] - a[2])
            if d / seconds > MAX_PLAUSIBLE_MS:
                continue
            w = min(n_win - 1, a[0] // win_frames)
            ti = 0 if b[3] == Team.HOME else 1
            dist[w][ti] += d
            time_[w][ti] += seconds

    return [
        {"start_frame": w * win_frames,
         "home_avg_ms": round(dist[w][0] / time_[w][0], 3) if time_[w][0] > 0 else 0.0,
         "away_avg_ms": round(dist[w][1] / time_[w][1], 3) if time_[w][1] > 0 else 0.0}
        for w in range(n_win)
    ]
