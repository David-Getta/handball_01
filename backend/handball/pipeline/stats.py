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
from .primitive_cache import copy_by_id, memoize_primitive


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


@memoize_primitive("compute_player_stats", copy=copy_by_id)
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


def intensity_trend(match: Match, config=None,
                    half_t: int | None = None) -> dict:
    """Kondíció-mutató: az ELSŐ és MÁSODIK félidőben mért átlagos
    csapat-mozgássebesség (m/s), és a kettő közti esés százalékban.

    A félidő-határ a FELISMERT félidei szünet (halftime.detect_halftime),
    ha van; enélkül a felvétel felezőpontja. A half_t paraméterrel a
    határ kívülről is megadható (teszthez / kézi korrekcióhoz).

    Ha a második félidőben számottevően lassabb a csapat, az fáradásra /
    kondíció-hiányra utal. Csak MÉRT, hihető (<= MAX_PLAUSIBLE_MS)
    szakaszokból számol, legfeljebb 3 kockányi lyukat áthidalva — a
    speed_windows / intensity_timeline mintájára, hogy a becslés ne
    torzítson.

    Visszatérés csapatonként (home/away):
    {"first_ms", "second_ms", "drop_pct"} — a drop_pct pozitív, ha a
    második fél lassabb; a "midpoint_frame" a használt félidő-határ.
    """
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    dt = 1.0 / fps
    total = len(match.frames)
    if half_t is None:
        try:
            from .halftime import detect_halftime
            half_t = detect_halftime(match)
        except Exception:
            half_t = None
    mid = half_t if half_t is not None else total // 2
    out = {
        "midpoint_frame": mid,
        "home": {"first_ms": 0.0, "second_ms": 0.0, "drop_pct": 0.0},
        "away": {"first_ms": 0.0, "second_ms": 0.0, "drop_pct": 0.0},
    }
    if total < 4:
        return out

    # táv/idő félidőnként, csapatonként: [half][team] -> (dist, time)
    dist = [[0.0, 0.0], [0.0, 0.0]]
    time_ = [[0.0, 0.0], [0.0, 0.0]]
    by_player: dict[int, list] = {}
    for frame in match.frames:
        for p in frame.players:
            if p.source != PositionSource.MEASURED:
                continue
            by_player.setdefault(p.track_id, []).append(
                (frame.t, p.x, p.y, p.team))
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
            half = 0 if a[0] < mid else 1
            ti = 0 if b[3] == Team.HOME else 1
            dist[half][ti] += d
            time_[half][ti] += seconds

    for ti, side in ((0, "home"), (1, "away")):
        first = dist[0][ti] / time_[0][ti] if time_[0][ti] > 0 else 0.0
        second = dist[1][ti] / time_[1][ti] if time_[1][ti] > 0 else 0.0
        drop = round((first - second) / first * 100.0, 1) if first > 0 else 0.0
        out[side] = {"first_ms": round(first, 3),
                     "second_ms": round(second, 3), "drop_pct": drop}
    return out


# Játékos-fáradás: legalább ennyi MÉRT másodperc kell mindkét félidőben,
# és ekkora esés számít említésre méltónak.
FATIGUE_MIN_S = 30.0


# Sprint-állás: sprint-ütem az eredményjelző szerint.
SPB_MIN_STATE_S = 60.0   # ennyi játékidő kell egy összevetett állapotban
SPB_MIN_SPRINTS = 8      # ennyi hátrány-sprint kell az ítélethez
SPB_RATIO = 1.5          # ekkora ütem-többlet hátrányban = menekülés


def sprints_by_score(match: Match, config=None) -> dict:
    """Sprint-állás: MIKOR sprintel a csapat — vezetésnél vagy hátrányban.

    A sprint-számok (compute_player_stats) a meccs egészét nézik — ez
    az eredményjelzőn: csapatonként és állásonként (vezet / döntetlen /
    hátrányban) mérjük a sprint-ütemet (sprint/perc). A hátrányban
    megugró sprint-ütem a menekülő futás: a lemaradó csapat lábbal
    próbálja visszahozni a meccset — ez a hajrára elfogyó energia
    leggyorsabb útja, és a fáradás-rétegek (tempó-esés, kontra-esés)
    korai előjele.

    Edzőileg: az ilyen csapat ellen a vezetés megtartása duplán
    kifizetődő — minden vezetéses perc az ő lábukat fogyasztja; a
    saját oldalon a hátrányban is ütemtartó (nem pánik-) futás a téma.

    Visszatérés csapatonként: {"leading"/"trailing"/"level":
    {"seconds", "sprints", "per_min"}, "verdict"} — per_min None
    SPB_MIN_STATE_S-nél kevesebb játékidőnél; a verdict "hátrányban
    sprintbe menekülnek" (SPB_RATIO-s ütem-többletnél és legalább
    SPB_MIN_SPRINTS hátrány-sprintnél), különben None.
    """
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    dt = 1.0 / fps
    goals = sorted((e.t, getattr(e.team, "value", e.team))
                   for e in detect_shots(match, config)
                   if e.type == EventType.GOAL)
    out = {side: {k: {"seconds": 0.0, "sprints": 0, "per_min": None}
                  for k in ("leading", "trailing", "level")}
           for side in ("home", "away")}

    # 1. menet: kockánkénti gólkülönbség (hazai szemmel) + állapot-idő.
    diff_at: dict = {}
    gi = 0
    h = a = 0
    for f in match.frames:
        while gi < len(goals) and goals[gi][0] <= f.t:
            if goals[gi][1] == "home":
                h += 1
            else:
                a += 1
            gi += 1
        d = h - a
        diff_at[f.t] = d
        for side, dd in (("home", d), ("away", -d)):
            state = ("leading" if dd > 0
                     else "trailing" if dd < 0 else "level")
            out[side][state]["seconds"] += dt

    # 2. menet: sprint-futamok, a futam KEZDETÉNEK állapotára írva.
    prev_pos: dict = {}
    runs: dict = {}
    def close_run(tid):
        run = runs.pop(tid, None)
        if run is None or run["s"] < SPRINT_MIN_S:
            return
        side = run["team"]
        d = diff_at.get(run["t0"], 0)
        dd = d if side == "home" else -d
        state = ("leading" if dd > 0
                 else "trailing" if dd < 0 else "level")
        out[side][state]["sprints"] += 1

    for f in match.frames:
        seen = set()
        for pl in f.players:
            if pl.source != PositionSource.MEASURED:
                continue
            seen.add(pl.track_id)
            prev = prev_pos.get(pl.track_id)
            prev_pos[pl.track_id] = (f.t, pl.x, pl.y,
                                     getattr(pl.team, "value", pl.team))
            if prev is None or f.t - prev[0] != 1:
                close_run(pl.track_id)
                continue
            speed = math.hypot(pl.x - prev[1], pl.y - prev[2]) * fps
            if SPRINT_SPEED_MS <= speed <= MAX_PLAUSIBLE_MS:
                run = runs.get(pl.track_id)
                if run is None:
                    runs[pl.track_id] = {"t0": prev[0], "s": dt,
                                         "team": prev[3]}
                else:
                    run["s"] += dt
            else:
                close_run(pl.track_id)
        for tid in [t for t in runs if t not in seen]:
            close_run(tid)
    for tid in list(runs):
        close_run(tid)

    for side in ("home", "away"):
        buckets = out[side]
        for rec in buckets.values():
            rec["seconds"] = round(rec["seconds"], 1)
            if rec["seconds"] >= SPB_MIN_STATE_S:
                rec["per_min"] = round(
                    60.0 * rec["sprints"] / rec["seconds"], 2)
        tr = buckets["trailing"]
        rest_s = (buckets["leading"]["seconds"]
                  + buckets["level"]["seconds"])
        rest_n = (buckets["leading"]["sprints"]
                  + buckets["level"]["sprints"])
        verdict = None
        if tr["seconds"] >= SPB_MIN_STATE_S \
                and rest_s >= SPB_MIN_STATE_S \
                and tr["sprints"] >= SPB_MIN_SPRINTS:
            tr_rate = 60.0 * tr["sprints"] / tr["seconds"]
            rest_rate = 60.0 * rest_n / rest_s
            if tr_rate >= SPB_RATIO * max(rest_rate, 1e-9) \
                    or (rest_rate == 0 and tr_rate > 0):
                verdict = "hátrányban sprintbe menekülnek"
        buckets["verdict"] = verdict
    return out


def player_fatigue(match: Match, config=None,
                   half_t: int | None = None) -> list[dict]:
    """Játékosonkénti tempó-visszaesés: első vs második félidő átlag-
    sebessége (m/s) és az esés százalékban.

    A csapat-szintű kondíció-mutató (intensity_trend) játékos-szintű
    párja: kit visel meg leginkább a meccs — a csere-döntések nyers
    adata. A félidő-határ a felismert szünet (vagy half_t); csak MÉRT,
    hihető szakaszokból számol, és csak azok a játékosok szerepelnek,
    akiknek mindkét félidőben van legalább FATIGUE_MIN_S mért idejük.

    Visszatérés: [{"track_id", "team", "first_ms", "second_ms",
    "drop_pct"}], esés szerint csökkenő sorrendben.
    """
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    dt = 1.0 / fps
    total = len(match.frames)
    if total < 4:
        return []
    if half_t is None:
        try:
            from .halftime import detect_halftime
            half_t = detect_halftime(match)
        except Exception:
            half_t = None
    mid = half_t if half_t is not None else total // 2

    by_player: dict[int, list] = {}
    team_of: dict[int, str] = {}
    for frame in match.frames:
        for p in frame.players:
            if p.source != PositionSource.MEASURED:
                continue
            by_player.setdefault(p.track_id, []).append(
                (frame.t, p.x, p.y))
            team_of.setdefault(p.track_id, p.team.value)

    out = []
    for tid, samples in by_player.items():
        samples.sort(key=lambda s_: s_[0])
        dist = [0.0, 0.0]
        time_ = [0.0, 0.0]
        for (a, b) in zip(samples, samples[1:]):
            gap = b[0] - a[0]
            if gap <= 0 or gap > 3:
                continue
            seconds = gap * dt
            d = math.hypot(b[1] - a[1], b[2] - a[2])
            if d / seconds > MAX_PLAUSIBLE_MS:
                continue
            half = 0 if a[0] < mid else 1
            dist[half] += d
            time_[half] += seconds
        if time_[0] < FATIGUE_MIN_S or time_[1] < FATIGUE_MIN_S:
            continue
        first = dist[0] / time_[0]
        second = dist[1] / time_[1]
        drop = round((first - second) / first * 100.0, 1) if first > 0 else 0.0
        out.append({"track_id": tid, "team": team_of.get(tid, "?"),
                    "first_ms": round(first, 2),
                    "second_ms": round(second, 2), "drop_pct": drop})
    out.sort(key=lambda r: -r["drop_pct"])
    return out


def aggregate_by_jersey(stats: dict, team_of: dict, jersey_of: dict,
                        fps: float = 25.0) -> list[dict]:
    """Játékos-statisztikák MEZSZÁM szerint összevonva.

    Ha a követés megszakadt és egy játékos több track_id-t kapott, a kézi
    (vagy OCR-es) mezszám-hozzárendelés után itt válik újra EGY játékossá:
    az azonos (csapat, mezszám) párhoz tartozó trackek táv/sprint értékei
    összeadódnak, a csúcssebesség a maximum. A szám nélküli trackek külön
    sorok maradnak.

    Visszatérés: [{"label", "team", "jersey", "track_ids", distance_m,
    avg_speed_ms, top_speed_ms, sprint_count, sprint_distance_m,
    measured_frames, estimated_frames}], táv szerint csökkenő sorrendben.
    """
    groups: dict = {}
    for tid, s in stats.items():
        jersey = jersey_of.get(tid)
        team = team_of.get(tid, "?")
        key = (team, jersey) if jersey is not None else (team, f"id-{tid}")
        g = groups.setdefault(key, {
            "label": f"#{jersey}" if jersey is not None else f"id {tid}",
            "team": team, "jersey": jersey, "track_ids": [],
            "distance_m": 0.0, "top_speed_ms": 0.0, "sprint_count": 0,
            "sprint_distance_m": 0.0, "measured_frames": 0,
            "estimated_frames": 0,
            "zone_seconds": {"seta": 0.0, "kocogas": 0.0, "futas": 0.0,
                             "sprint": 0.0},
        })
        g["track_ids"].append(tid)
        g["distance_m"] += s.distance_m
        g["top_speed_ms"] = max(g["top_speed_ms"], s.top_speed_ms)
        g["sprint_count"] += s.sprint_count
        g["sprint_distance_m"] += s.sprint_distance_m
        g["measured_frames"] += s.measured_frames
        g["estimated_frames"] += s.estimated_frames
        for k, v in (s.zone_seconds or {}).items():
            g["zone_seconds"][k] = g["zone_seconds"].get(k, 0.0) + v
    out = list(groups.values())
    dt = 1.0 / (fps if fps > 0 else 25.0)
    for g in out:
        # Az átlagsebesség az összevont távból és mért időből számolódik újra.
        moving_time = max(1, g["measured_frames"]) * dt
        g["avg_speed_ms"] = g["distance_m"] / moving_time
        g["distance_m"] = round(g["distance_m"], 1)
        g["avg_speed_ms"] = round(g["avg_speed_ms"], 2)
        g["top_speed_ms"] = round(g["top_speed_ms"], 2)
        g["sprint_distance_m"] = round(g["sprint_distance_m"], 1)
        g["track_ids"].sort()
    out.sort(key=lambda g: g["distance_m"], reverse=True)
    return out


def possession_share(match: Match, config=None) -> dict:
    """Labdabirtoklás-arány csapatonként.

    Kockánként megnézzük, melyik csapaté a labda (possession_team), és a
    birtoklott kockákat összegezzük. Visszatérés:
    {"home", "away": {"frames", "seconds", "pct"}, "contested_pct"} —
    a pct a MEGHATÁROZOTT birtoklású kockákra vetített arány; a
    contested_pct a se-nem-egyik (szabad labda / nincs labda) kockák
    aránya az egészhez. Kevés adatnál nulla értékek."""
    from .tactics import TacticsConfig, possession_team

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    home = away = neither = 0
    for f in match.frames:
        t = possession_team(f, config)
        if t == Team.HOME:
            home += 1
        elif t == Team.AWAY:
            away += 1
        else:
            neither += 1
    determined = home + away
    total = home + away + neither
    out = {
        "home": {"frames": home, "seconds": round(home / fps, 1),
                 "pct": round(100.0 * home / determined, 1) if determined else 0.0},
        "away": {"frames": away, "seconds": round(away / fps, 1),
                 "pct": round(100.0 * away / determined, 1) if determined else 0.0},
        "contested_pct": round(100.0 * neither / total, 1) if total else 0.0,
    }
    return out


# Rotáció-mélység: e felett a jelenlét-arány felett számít "alapembernek"
# egy játékos, e felett a minimális arány felett "bevetettnek".
ROTATION_REGULAR_SHARE = 0.5
ROTATION_USED_SHARE = 0.1


def rotation_depth(match, config=None) -> dict:
    """Rotáció-mélység: hány emberrel játssza a csapat a meccset.

    A mezszám szerint összevont jelenlét-időkből (mért kockák) számol:
    bevetett = a meccs legalább 10%-án a pályán; alapember = legalább
    50%-án. A kapus kimarad (az ő ideje nem rotáció-kérdés). Szűk pad
    (kevés bevetett játékos) fáradáshoz vezet a hajrában — a felderítés
    és a meccsterv erre építhet.

    Visszatérés csapatonként:
      {"used", "regulars", "avg_minutes", "players":
       [{"label", "minutes", "share_pct"}]} — avg_minutes a bevetettek
    átlagos játékperce; players a bevetettek, idő szerint csökkenően.
    """
    from ..models.tracking import Team

    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    total = len(match.frames)
    if total == 0:
        return {side: {"used": 0, "regulars": 0, "avg_minutes": None,
                       "players": []} for side in ("home", "away")}
    stats = compute_player_stats(match)
    team_of: dict = {}
    jersey_of: dict = {}
    gk_tracks: set = set()
    for fr in match.frames:
        for p in fr.players:
            team_of.setdefault(p.track_id,
                               getattr(p.team, "value", p.team))
            if p.jersey_number is not None:
                jersey_of.setdefault(p.track_id, p.jersey_number)
            if p.role == "kapus":
                gk_tracks.add(p.track_id)

    out = {side: {"used": 0, "regulars": 0, "avg_minutes": None,
                  "players": []} for side in ("home", "away")}
    for g in aggregate_by_jersey(stats, team_of, jersey_of, fps=fps):
        if any(t in gk_tracks for t in g["track_ids"]):
            continue
        side = g["team"]
        if side not in out:
            continue
        share = g["measured_frames"] / total
        if share < ROTATION_USED_SHARE:
            continue
        rec = out[side]
        rec["used"] += 1
        if share >= ROTATION_REGULAR_SHARE:
            rec["regulars"] += 1
        rec["players"].append({
            "label": g["label"],
            "minutes": round(g["measured_frames"] / fps / 60.0, 1),
            "share_pct": round(100.0 * share, 1),
        })
    for rec in out.values():
        rec["players"].sort(key=lambda p_: -p_["minutes"])
        if rec["used"]:
            rec["avg_minutes"] = round(
                sum(p_["minutes"] for p_ in rec["players"])
                / rec["used"], 1)
    return out


# Játékos-mérleg: ennyi pályán töltött perctől ítélünk, és ennyi
# gól/perc eltérés a csapatátlagtól számít érdemi jelnek.
PM_MIN_MINUTES = 5.0
PM_GAP_PER_MIN = 0.15


def player_plus_minus(match, config=None) -> dict:
    """Játékos-mérleg (+/−): kinek a pályán léte alatt jobb a
    gólkülönbség.

    A rotáció-mélység (rotation_depth) azt mutatja, KI mennyit
    játszik — ez azt, hogy MI TÖRTÉNIK, amíg játszik: a pályán
    töltött ideje alatt szerzett és kapott gólok különbsége, percre
    vetítve, a csapat saját átlagához mérve. A magas mérlegű
    játékos ellen kell a legerősebb védekezés (és őt kell fárasztani);
    a negatív mérleg nem ítélet, hanem kérdés: kivel és mikor játszik.

    Visszatérés csapatonként: {"team_per_min", "players":
    [{"player_id", "minutes", "for", "against", "diff",
      "diff_per_min", "vs_team"}], "best", "worst"} — a lista a
    percre vetített mérleg szerint csökkenő; a best/worst az első
    olyan játékos, akinek legalább PM_MIN_MINUTES ideje van, és
    PM_GAP_PER_MIN-nel a csapatátlag felett/alatt van (egyébként
    None).
    """
    from ..models.tracking import Team
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    goals = [(e.t, e.team.value) for e in detect_shots(match, config)
             if e.type == EventType.GOAL]
    if not match.frames:
        return {s: {"team_per_min": None, "players": [], "best": None,
                    "worst": None} for s in ("home", "away")}

    # Pályán töltött kockák és a rájuk eső gólok játékosonként.
    on_frames: dict = {"home": {}, "away": {}}
    goal_idx: dict = {}
    for (gt, gs) in goals:
        goal_idx.setdefault(gt, []).append(gs)
    tally: dict = {"home": {}, "away": {}}
    goals_by_t = {gt: gss for gt, gss in goal_idx.items()}
    for f in match.frames:
        gss = goals_by_t.get(f.t)
        for p in f.players:
            if p.team is None:
                continue
            side = p.team.value
            on_frames[side][p.track_id] = (
                on_frames[side].get(p.track_id, 0) + 1)
            if gss:
                rec = tally[side].setdefault(p.track_id,
                                             {"for": 0, "against": 0})
                for gs in gss:
                    rec["for" if gs == side else "against"] += 1

    total_s = (match.frames[-1].t - match.frames[0].t) / fps
    out = {}
    for side in ("home", "away"):
        other = "away" if side == "home" else "home"
        team_for = sum(1 for (_t, gs) in goals if gs == side)
        team_against = sum(1 for (_t, gs) in goals if gs == other)
        team_per_min = (round(60.0 * (team_for - team_against) / total_s, 2)
                        if total_s > 0 else None)
        players = []
        for pid, frames_n in on_frames[side].items():
            minutes = frames_n / fps / 60.0
            rec = tally[side].get(pid, {"for": 0, "against": 0})
            diff = rec["for"] - rec["against"]
            per_min = (round(diff / minutes, 2) if minutes > 0 else None)
            players.append({
                "player_id": pid, "minutes": round(minutes, 1),
                "for": rec["for"], "against": rec["against"],
                "diff": diff, "diff_per_min": per_min,
                "vs_team": (round(per_min - team_per_min, 2)
                            if per_min is not None
                            and team_per_min is not None else None)})
        players.sort(key=lambda p: -(p["diff_per_min"] or 0.0))
        best = next((p for p in players
                     if p["minutes"] >= PM_MIN_MINUTES
                     and (p["vs_team"] or 0.0) >= PM_GAP_PER_MIN), None)
        worst = next((p for p in reversed(players)
                      if p["minutes"] >= PM_MIN_MINUTES
                      and (p["vs_team"] or 0.0) <= -PM_GAP_PER_MIN), None)
        out[side] = {"team_per_min": team_per_min, "players": players,
                     "best": best, "worst": worst}
    return out


# Páros-mérleg: ennyi együtt töltött perctől ítélünk egy párost, és
# ennyi gól/perc eltérés a csapatátlagtól számít érdemi jelnek.
PAIR_MIN_MINUTES = 4.0
PAIR_GAP_PER_MIN = 0.2


def pair_plus_minus(match, config=None) -> dict:
    """Páros-mérleg: MELYIK KETTŐ megy jól EGYÜTT a pályán.

    A játékos-mérleg (player_plus_minus) egy emberre nézi a
    gólkülönbséget — ez a párokra: minden együtt töltött kockát a
    két játékos párosához írunk, és a rájuk eső gólokat is. Így
    látszik, mely kettős emeli a csapatot, és melyik páros együtt
    nem működik (attól még külön-külön jók lehetnek).

    Edzőileg ez az egység-építés adata: a jó párost egy blokkban
    kell tartani (együtt cserélni), a rosszat szét kell húzni; az
    ellenfél legjobb párosát pedig a cseréikkel lehet szétszedni —
    kettőzéssel arra, aki hamarabb fárad.

    Visszatérés csapatonként: {"team_per_min", "pairs":
    [{"players": [id, id], "minutes", "for", "against", "diff",
      "diff_per_min", "vs_team"}], "best", "worst"} — a lista a
    percre vetített mérleg szerint csökkenő; a best/worst az első
    olyan páros, amelynek legalább PAIR_MIN_MINUTES közös ideje van,
    és PAIR_GAP_PER_MIN-nel a csapatátlag felett/alatt van
    (egyébként None).
    """
    from itertools import combinations

    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    empty = {s: {"team_per_min": None, "pairs": [], "best": None,
                 "worst": None} for s in ("home", "away")}
    if not match.frames:
        return empty
    goals = [(e.t, e.team.value) for e in detect_shots(match, config)
             if e.type == EventType.GOAL]
    goals_by_t: dict = {}
    for (gt, gs) in goals:
        goals_by_t.setdefault(gt, []).append(gs)

    # Együtt töltött kockák és a rájuk eső gólok páronként.
    on: dict = {"home": {}, "away": {}}
    tally: dict = {"home": {}, "away": {}}
    for f in match.frames:
        gss = goals_by_t.get(f.t)
        by_side: dict = {"home": [], "away": []}
        for p in f.players:
            if p.team is not None:
                by_side[p.team.value].append(p.track_id)
        for side, ids in by_side.items():
            for pair in combinations(sorted(set(ids)), 2):
                on[side][pair] = on[side].get(pair, 0) + 1
                if gss:
                    rec = tally[side].setdefault(pair,
                                                 {"for": 0,
                                                  "against": 0})
                    for gs in gss:
                        rec["for" if gs == side else "against"] += 1

    total_s = (match.frames[-1].t - match.frames[0].t) / fps
    out = {}
    for side in ("home", "away"):
        other = "away" if side == "home" else "home"
        team_for = sum(1 for (_t, gs) in goals if gs == side)
        team_against = sum(1 for (_t, gs) in goals if gs == other)
        team_per_min = (round(60.0 * (team_for - team_against) / total_s, 2)
                        if total_s > 0 else None)
        pairs = []
        for pair, frames_n in on[side].items():
            minutes = frames_n / fps / 60.0
            rec = tally[side].get(pair, {"for": 0, "against": 0})
            diff = rec["for"] - rec["against"]
            per_min = (round(diff / minutes, 2) if minutes > 0 else None)
            pairs.append({
                "players": list(pair), "minutes": round(minutes, 1),
                "for": rec["for"], "against": rec["against"],
                "diff": diff, "diff_per_min": per_min,
                "vs_team": (round(per_min - team_per_min, 2)
                            if per_min is not None
                            and team_per_min is not None else None)})
        pairs.sort(key=lambda p: -(p["diff_per_min"] or 0.0))
        best = next((p for p in pairs
                     if p["minutes"] >= PAIR_MIN_MINUTES
                     and (p["vs_team"] or 0.0) >= PAIR_GAP_PER_MIN), None)
        worst = next((p for p in reversed(pairs)
                      if p["minutes"] >= PAIR_MIN_MINUTES
                      and (p["vs_team"] or 0.0) <= -PAIR_GAP_PER_MIN),
                     None)
        out[side] = {"team_per_min": team_per_min, "pairs": pairs,
                     "best": best, "worst": worst}
    return out


# Sprint-veszély: ennyi csapat-sprint kell az ítélethez, és a legtöbbet
# sprintelő ember legalább ekkora részesedéssel számít kontra-motornak.
SPT_MIN_TEAM_SPRINTS = 10
SPT_TOP_SHARE_PCT = 30.0


def sprint_threats(match: Match, config=None) -> dict:
    """Sprint-veszély: KI VISZI A KONTRÁT — a legtöbbet sprintelő ember.

    A sprint-statisztika (compute_player_stats) terhelés-monitornak
    készült — ez az ellenfél-olvasata: csapatonként kigyűjtjük, ki
    hányszor sprintel, és van-e egy ember, akire a csapat
    sprintjeinek nagy része jut. A kézilabdában a sprint szinte mindig
    átmenet: aki a legtöbbet sprintel, az a lerohanások motorja.

    Edzőileg: a kontra-motor ellen névre szóló fékező-feladat kell —
    labdavesztésnél az első dolog az Ő útjának a lezárása, és tilos
    őt a fal mögé engedni; a saját csapatban pedig a sprint-teher
    eloszlása a rotáció-tervezés bemenete.

    Visszatérés csapatonként: {"team_sprints", "players":
    [{"player_id", "jersey", "sprints", "sprint_m"}], "top",
    "verdict"} — a top/verdict None SPT_MIN_TEAM_SPRINTS alatt vagy
    SPT_TOP_SHARE_PCT alatti részesedésnél; a verdict "kijelölt
    kontra-emberük van" / None.
    """
    team_of: dict[int, str] = {}
    jersey: dict[int, int] = {}
    keeper: set = set()
    for f in match.frames:
        for p in f.players:
            team_of.setdefault(p.track_id, p.team.value)
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)
            if p.role == "kapus":
                keeper.add(p.track_id)

    stats = compute_player_stats(match)
    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": tid, "jersey": jersey.get(tid),
                 "sprints": s.sprint_count,
                 "sprint_m": round(s.sprint_distance_m, 1)}
                for tid, s in stats.items()
                if team_of.get(tid) == side and tid not in keeper
                and s.sprint_count > 0]
        rows.sort(key=lambda r: -r["sprints"])
        total = sum(r["sprints"] for r in rows)
        top = None
        verdict = None
        if total >= SPT_MIN_TEAM_SPRINTS and rows:
            share = 100.0 * rows[0]["sprints"] / total
            if share >= SPT_TOP_SHARE_PCT:
                top = rows[0]
                verdict = "kijelölt kontra-emberük van"
        out[side] = {"team_sprints": total, "players": rows,
                     "top": top, "verdict": verdict}
    return out


# Futás-mérleg: legalább ennyi mért játékperc kell az ítélethez, és
# ekkora táv-többlet jelenti, hogy az egyik csapat túlfutja a másikat.
DBT_MIN_MIN = 10.0
DBT_GAP_PCT = 10.0


def distance_battle(match: Match, config=None) -> dict:
    """Futás-mérleg: MELYIK CSAPAT FUTJA TÚL a másikat.

    A játékos-statisztika (compute_player_stats) terhelés-monitor —
    ez a csapat-olvasata: a mezőnyjátékosok mért futott távját
    csapatonként összegezzük, és összevetjük a két oldalt. Aki
    érdemben többet fut, az diktálja az átmeneteket; aki alul marad,
    az rendre később ér oda a második labdákra és a visszazárásba.

    Edzőileg: a futócsapattal nem szabad futóversenyt vállalni —
    lassított tempó, felállt fal és hosszú támadások jönnek ellene; a
    keveset futó csapat ellen viszont pont a tempó a fegyver: gyors
    középkezdés, korai indítások, második hullám.

    Visszatérés csapatonként: {"distance_m", "per_min_m", "verdict"}
    — a verdict None DBT_MIN_MIN mért perc alatt; a verdict "túlfutják
    az ellenfelüket" / "túlfutja őket az ellenfél" / None.
    """
    keeper: set = set()
    team_of: dict[int, str] = {}
    for f in match.frames:
        for p in f.players:
            team_of.setdefault(p.track_id, p.team.value)
            if p.role == "kapus":
                keeper.add(p.track_id)

    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    minutes = (0.0 if not match.frames else
               (match.frames[-1].t - match.frames[0].t) / fps / 60.0)

    stats = compute_player_stats(match)
    dist = {"home": 0.0, "away": 0.0}
    for tid, s in stats.items():
        if tid in keeper or team_of.get(tid) is None:
            continue
        dist[team_of[tid]] += s.distance_m

    out: dict = {}
    for side in ("home", "away"):
        other = dist["away" if side == "home" else "home"]
        own = dist[side]
        rec = {"distance_m": round(own, 1),
               "per_min_m": (round(own / minutes, 1) if minutes else None),
               "verdict": None}
        if minutes >= DBT_MIN_MIN and own > 0 and other > 0:
            if own >= other * (1.0 + DBT_GAP_PCT / 100.0):
                rec["verdict"] = "túlfutják az ellenfelüket"
            elif own <= other * (1.0 - DBT_GAP_PCT / 100.0):
                rec["verdict"] = "túlfutja őket az ellenfél"
        out[side] = rec
    return out


# Vasember-poszt: legalább ennyi perces felvételtől ítélünk; ekkora
# jelenlét-arány számít "végigjátszásnak", és ennyi százalékponttal
# kell a többi poszt fölé nőnie (különben az egész csapat cserétlen,
# és nincs kitüntetett poszt).
IRM_MIN_MATCH_MIN = 10.0
IRM_SHARE_PCT = 85.0
IRM_GAP_PP = 15.0


def iron_man_roles(match, config=None) -> dict:
    """Vasember-poszt: MELYIK POSZTJUK játszik végig csere nélkül.

    A rotáció-mélység (rotation_depth) azt mondja meg, hány emberrel
    játszanak — ez azt, HOL nincs váltás: posztonként megnézi a
    legtöbbet pályán lévő játékos jelenlét-arányát, és kimondja, ha
    egy poszt kilóg: ott egy ember viszi az egész meccset, miközben a
    többi posztot cserével frissítik.

    Edzőileg ez a hajrá-terv: a végigjátszó poszt a meccs végére
    elfárad — az utolsó tíz percben oda kell vinni a tempót (őt kell
    futtatni, az ő sávjában jön a betörés), és a saját oldalon az ő
    ellenfelére friss embert kell hozni. Saját csapatnál ugyanez
    figyelmeztetés: a cserétlen posztunk a hajrában sebezhető.

    Visszatérés csapatonként: {"minutes" (felvétel-hossz percben),
    "roles": {poszt: jelenlét-%}, "main_role", "share_pct",
    "verdict"} — az ítélet None, ha a felvétel rövidebb az
    IRM_MIN_MATCH_MIN-nél, a vezető poszt nem éri el az
    IRM_SHARE_PCT-t, vagy nem nő ki a mezőnyből (IRM_GAP_PP).
    """
    from ..models.tracking import PositionSource
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    total = len(match.frames)
    minutes = total / fps / 60.0
    roles = estimate_positions(match, config)

    presence: dict = {"home": {}, "away": {}}
    for f in match.frames:
        for p in f.players:
            if p.source != PositionSource.MEASURED or p.role == "kapus":
                continue
            side = p.team.value
            presence[side][p.track_id] = (
                presence[side].get(p.track_id, 0) + 1)

    out: dict = {side: {"minutes": round(minutes, 1), "roles": {},
                        "main_role": None, "share_pct": None,
                        "verdict": None}
                 for side in ("home", "away")}
    if total == 0:
        return out
    for side in ("home", "away"):
        rec = out[side]
        best_by_post: dict = {}
        for tid, n in presence[side].items():
            rec_role = roles[side].get(tid)
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            share = 100.0 * n / total
            if share > best_by_post.get(poszt, 0.0):
                best_by_post[poszt] = share
        rec["roles"] = {p: round(v, 1) for p, v in
                        sorted(best_by_post.items(),
                               key=lambda kv: -kv[1])}
        if not rec["roles"] or minutes < IRM_MIN_MATCH_MIN:
            continue
        vals = list(rec["roles"].values())
        top_share = vals[0]
        gap_ok = len(vals) == 1 or top_share - vals[1] >= IRM_GAP_PP
        if top_share >= IRM_SHARE_PCT and gap_ok:
            poszt = next(iter(rec["roles"]))
            rec["main_role"] = poszt
            rec["share_pct"] = top_share
            rec["verdict"] = (
                f"a(z) {poszt} posztjuk végigjátssza a meccset "
                f"({top_share:.0f}% jelenlét, miközben a többi posztot"
                " cserélik) — a hajrában oda kell vinni a tempót: őt "
                "kell futtatni, és vele szemben friss ember jöjjön")
    return out
