"""
[Ellenfél-felderítés] — egy meccsből (vagy több meccsből) EGY edzői felderítő
jelentést állít össze egy adott csapatról.

Ez a szoftver "headline" haszna: az edző hetente órákat tölt az ellenfél
meccseinek kézi elemzésével (hogyan védekeznek, mi a tempójuk, ki a kulcs-lövő,
milyen figurákat játszanak). Ezt itt AUTOMATIKUSAN, egy jelentéssé sűrítjük — a
korábbi elemző rétegekre építve (tactics, analytics, event_detection, setplays).

A jelentés EGY csapatra szól (a felderített ellenfélre). Tartalma:
- Támadó identitás: mennyit támadnak szervezetten, tempó, gyors-indítás arány,
- Védekezés: leggyakoribb forma + megoszlás (amikor ez a csapat véd),
- Támadó zónák: súlypont + hotspotok, figurák száma,
- Befejezés: lövések/gólok/hatékonyság,
- Kulcsjátékosok: legaktívabbak + labdabirtoklás-idő,
- Edzői kulcsok: "hogyan játssz ellenük" + erősségek/gyengeségek.

Tiszta adatfeldolgozás (videó nélkül tesztelhető). Több meccs egyesíthető
(combine_reports) — több meccs adja a valós, zajmentes profilt.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Optional

from ..models.tracking import Match, Frame, Team
from .calibration import COURT_LENGTH_M, COURT_WIDTH_M
from .tactics import (
    TacticsConfig, Phase, possession_team, classify_phase, detect_formation,
    compute_tempo, phase_percentages,
)
from .analytics import compute_team_heatmap, compute_team_summary
from .event_detection import detect_events, EventType
from .setplays import segment_attacks, discover_setplays
from .stats import compute_player_stats

# A labda ekkora (támadó irányú) sebessége (m/s) felett "gyors indítás".
_FASTBREAK_MS = 6.0


@dataclass
class KeyPlayer:
    """Egy kulcsjátékos összegzője a felderített csapatból."""
    track_id: int
    possession_frames: int   # hány frame-en át volt nála a labda (irányító-jel)
    distance_m: float        # megtett táv (aktivitás)
    role: str                # becsült szerep (pl. "irányító", "aktív mezőnyjátékos")


@dataclass
class ScoutingReport:
    """Egy csapat felderítő jelentése (edzői nyelven is)."""
    team: str
    team_name: str
    matches: int = 1
    # Támadó identitás
    attack_share_pct: float = 0.0
    fast_break_pct: float = 0.0
    avg_ball_speed_ms: float = 0.0
    avg_attack_duration_s: float = 0.0
    # Védekezés
    defense_main: str = "—"
    defense_distribution: dict = field(default_factory=dict)
    # Támadó zóna
    attack_centroid_x: float = 0.0
    attack_centroid_y: float = 0.0
    num_figures: int = 0
    attacks: int = 0
    # Befejezés
    shots: int = 0
    goals: int = 0
    turnovers: int = 0
    shot_efficiency_pct: float = 0.0
    # Kulcsjátékosok + edzői kulcsok
    key_players: list = field(default_factory=list)
    strengths: list = field(default_factory=list)
    weaknesses: list = field(default_factory=list)
    keys_to_game: list = field(default_factory=list)


def _other(team: Team) -> Team:
    return Team.AWAY if team == Team.HOME else Team.HOME


def _team_of_track(match: Match) -> dict:
    """track_id -> a leggyakrabban látott csapata (a csapat-hovatartozás stabil jele)."""
    tally: dict[int, dict[Team, int]] = {}
    for f in match.frames:
        for p in f.players:
            tally.setdefault(p.track_id, {}).setdefault(p.team, 0)
            tally[p.track_id][p.team] += 1
    return {tid: max(counts.items(), key=lambda kv: kv[1])[0] for tid, counts in tally.items()}


def _fast_break_pct(match: Match, team: Team, config: TacticsConfig) -> float:
    """A csapat labdás pillanatai közül mennyi a GYORS, támadó irányú indítás (%)."""
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    target_x = config.attacks_toward_x(team)
    sign = 1.0 if target_x > COURT_LENGTH_M / 2.0 else -1.0
    poss_frames = 0
    fast = 0
    prev = None
    for f in match.frames:
        poss = possession_team(f, config)
        if poss == team and f.ball is not None:
            poss_frames += 1
            if prev is not None:
                speed = (f.ball.x - prev) * sign * fps
                if speed >= _FASTBREAK_MS:
                    fast += 1
        prev = f.ball.x if f.ball is not None else None
    return 100.0 * fast / poss_frames if poss_frames else 0.0


def _defense_distribution(match: Match, team: Team, config: TacticsConfig) -> dict:
    """A csapat védekezési formáinak megoszlása (%), amikor ÉPP VÉDEKEZIK."""
    tally: dict[str, int] = {}
    for f in match.frames:
        phase = classify_phase(f, config)
        # a csapat akkor véd, ha az ELLENFELE támad
        defends = (phase == Phase.HOME_ATTACK and team == Team.AWAY) or \
                  (phase == Phase.AWAY_ATTACK and team == Team.HOME)
        if not defends:
            continue
        label = detect_formation(f, team, config).label
        tally[label] = tally.get(label, 0) + 1
    total = sum(tally.values())
    if not total:
        return {}
    return {k: round(100.0 * v / total, 1) for k, v in sorted(tally.items(), key=lambda kv: -kv[1])}


def _key_players(match: Match, team: Team, config: TacticsConfig, top: int = 4) -> list[KeyPlayer]:
    """A csapat kulcsjátékosai: labdabirtoklás-idő (irányító-jel) + aktivitás."""
    team_of = _team_of_track(match)
    poss_frames: dict[int, int] = {}
    for f in match.frames:
        if f.ball is None or not f.players:
            continue
        holder = min(f.players, key=lambda p: math.hypot(p.x - f.ball.x, p.y - f.ball.y))
        d = math.hypot(holder.x - f.ball.x, holder.y - f.ball.y)
        if d <= config.possession_radius_m and holder.team == team:
            poss_frames[holder.track_id] = poss_frames.get(holder.track_id, 0) + 1

    stats = compute_player_stats(match)
    rows: list[KeyPlayer] = []
    # A csapat játékosai: akiket többségében ehhez a csapathoz soroltunk.
    for tid, tteam in team_of.items():
        if tteam != team:
            continue
        pf = poss_frames.get(tid, 0)
        dist = stats[tid].distance_m if tid in stats else 0.0
        rows.append(KeyPlayer(track_id=tid, possession_frames=pf, distance_m=round(dist, 1),
                              role="irányító" if pf > 0 else "mezőnyjátékos"))
    # Rendezés: előbb a legtöbb labdabirtoklás, majd a legaktívabb.
    rows.sort(key=lambda r: (r.possession_frames, r.distance_m), reverse=True)
    # A legaktívabbat "irányítónak" csak akkor hívjuk, ha tényleg birtokolt sokat.
    return rows[:top]


def _coach_keys(rep: ScoutingReport) -> tuple[list, list, list]:
    """Edzői kulcsok: erősségek, gyengeségek, és "hogyan játssz ellenük"."""
    strengths, weaknesses, keys = [], [], []

    # Védekezés elleni terv.
    dmain = rep.defense_main
    if dmain == "6-0":
        keys.append("Mély 6-0 faluk ellen: 9 m-es lövés és beúszó, csald ki a védőt.")
    elif dmain == "5-1":
        keys.append("5-1-ük ellen: az előretolt védő kicselezése, gyors lefordulás.")
    elif dmain == "3-2-1":
        keys.append("3-2-1-ük ellen: terheld a beállót és a szélső réseket.")
    elif dmain and dmain != "—":
        keys.append(f"Védőformájuk főleg {dmain} — keresd a legüresebb sávot ellene.")

    # Tempó.
    if rep.fast_break_pct >= 12.0:
        strengths.append(f"Gyors indítás ({rep.fast_break_pct:.0f}%) — veszélyes lerohanás.")
        keys.append("Zárj vissza gyorsan lövés/labdavesztés után — magas a lerohanásuk.")
    if rep.avg_attack_duration_s and rep.avg_attack_duration_s < 6.0:
        strengths.append(f"Gyors támadásépítés (~{rep.avg_attack_duration_s:.1f} s).")
    elif rep.avg_attack_duration_s >= 12.0:
        weaknesses.append(f"Lassú, hosszú támadások (~{rep.avg_attack_duration_s:.1f} s) — türelmes védekezés kifárasztja őket.")

    # Befejezés.
    if rep.shots >= 3:
        if rep.shot_efficiency_pct >= 55.0:
            strengths.append(f"Erős befejezés ({rep.shot_efficiency_pct:.0f}% gólarány).")
            keys.append("Szűkítsd a lövőteret 9 m-en és a szélen — jól fejeznek be.")
        elif rep.shot_efficiency_pct <= 35.0:
            weaknesses.append(f"Gyenge befejezés ({rep.shot_efficiency_pct:.0f}%) — engedd a rossz helyzetű lövést.")
    if rep.turnovers >= 3 and rep.turnovers >= rep.shots:
        weaknesses.append("Sok labdaeladás — agresszív, aktív védekezés kifizetődő ellenük.")

    if not keys:
        keys.append("Kevés a minta — több meccsük felderítése pontosít.")
    return strengths, weaknesses, keys


def scout_team(match: Match, team: Team, config: Optional[TacticsConfig] = None) -> ScoutingReport:
    """Egy csapat felderítő jelentése EGY meccsből."""
    config = config or TacticsConfig()
    team_name = match.meta.home_team if team == Team.HOME else match.meta.away_team

    # Támadó identitás.
    pct = phase_percentages(match, config)
    attack_key = Phase.HOME_ATTACK.value if team == Team.HOME else Phase.AWAY_ATTACK.value
    tempo = compute_tempo(match, config)

    # Védekezés.
    dist = _defense_distribution(match, team, config)
    dmain = next(iter(dist), "—")

    # Támadó zóna + figurák.
    summ = compute_team_summary(match, team)
    figures = discover_setplays(match, config)
    team_attacks = sum(1 for s in segment_attacks(match, config) if s.team == team)

    # Befejezés (események).
    events = detect_events(match, config)
    shots = sum(1 for e in events if e.type in (EventType.SHOT, EventType.GOAL) and e.team == team)
    goals = sum(1 for e in events if e.type == EventType.GOAL and e.team == team)
    turnovers = sum(1 for e in events if e.type == EventType.TURNOVER and e.team == team)
    eff = 100.0 * goals / shots if shots else 0.0

    rep = ScoutingReport(
        team=team.value,
        team_name=team_name,
        attack_share_pct=round(pct.get(attack_key, 0.0), 1),
        fast_break_pct=round(_fast_break_pct(match, team, config), 1),
        avg_ball_speed_ms=round(tempo.avg_ball_speed_ms, 2),
        avg_attack_duration_s=round(tempo.avg_attack_duration_s, 2),
        defense_main=dmain,
        defense_distribution=dist,
        attack_centroid_x=round(summ.avg_centroid_x, 1),
        attack_centroid_y=round(summ.avg_centroid_y, 1),
        num_figures=figures.num_figures,
        attacks=team_attacks,
        shots=shots,
        goals=goals,
        turnovers=turnovers,
        shot_efficiency_pct=round(eff, 1),
        key_players=[asdict(k) for k in _key_players(match, team, config)],
    )
    s, w, k = _coach_keys(rep)
    rep.strengths, rep.weaknesses, rep.keys_to_game = s, w, k
    return rep


def combine_reports(reports: list[ScoutingReport]) -> ScoutingReport:
    """Több meccs jelentését egyesíti egy csapatról (több meccs = valós profil).

    A számszerű mezőket átlagolja, a darabszámokat összegzi, a védőforma-megoszlást
    súlyozottan egyesíti, és újraszámolja az edzői kulcsokat az összképből.
    """
    if not reports:
        raise ValueError("üres jelentéslista")
    if len(reports) == 1:
        return reports[0]

    n = len(reports)
    def avg(attr):
        return round(sum(getattr(r, attr) for r in reports) / n, 2)

    # Védőforma-megoszlás egyesítése (átlag a jelentések között).
    merged_dist: dict[str, float] = {}
    for r in reports:
        for k, v in r.defense_distribution.items():
            merged_dist[k] = merged_dist.get(k, 0.0) + v / n
    merged_dist = {k: round(v, 1) for k, v in sorted(merged_dist.items(), key=lambda kv: -kv[1])}

    shots = sum(r.shots for r in reports)
    goals = sum(r.goals for r in reports)
    rep = ScoutingReport(
        team=reports[0].team,
        team_name=reports[0].team_name,
        matches=n,
        attack_share_pct=avg("attack_share_pct"),
        fast_break_pct=avg("fast_break_pct"),
        avg_ball_speed_ms=avg("avg_ball_speed_ms"),
        avg_attack_duration_s=avg("avg_attack_duration_s"),
        defense_main=next(iter(merged_dist), "—"),
        defense_distribution=merged_dist,
        attack_centroid_x=avg("attack_centroid_x"),
        attack_centroid_y=avg("attack_centroid_y"),
        num_figures=sum(r.num_figures for r in reports),
        attacks=sum(r.attacks for r in reports),
        shots=shots,
        goals=goals,
        turnovers=sum(r.turnovers for r in reports),
        shot_efficiency_pct=round(100.0 * goals / shots, 1) if shots else 0.0,
        key_players=[],  # játékos-azonosítók meccsenként eltérők; összevonás nem triviális
    )
    s, w, k = _coach_keys(rep)
    rep.strengths, rep.weaknesses, rep.keys_to_game = s, w, k
    return rep


def report_to_dict(rep: ScoutingReport) -> dict:
    """A jelentés JSON-barát szótárrá alakítása (az API-hoz)."""
    return asdict(rep)
