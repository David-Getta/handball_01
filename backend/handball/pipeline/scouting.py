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
    # Helyzetminőség: az összes lövésük várható gól-értéke (xG) és a
    # befejezés-eltérés (gól − xG): pozitív = a helyzeteik felett lőnek.
    xg: float = 0.0
    xg_diff: float = 0.0
    # A VÉDEKEZÉSÜK képe (defense.py): mennyi lövést engednek, ebből
    # mennyi volt SZABAD (nem volt védő a lövő 2 m-es körzetében), és
    # zónánként hol lyukas a faluk — ebből jön a "hova játssz" kulcs.
    def_shots_against: int = 0
    def_goals_against: int = 0
    def_free_shots: int = 0
    def_zones: dict = field(default_factory=dict)
    # Lövési zónák: zóna -> {"shots": n, "goals": n} — HONNAN lőnek és honnan
    # eredményesek (balszél / beálló / átlövés bal-közép-jobb / jobbszél).
    shot_zones: dict = field(default_factory=dict)
    # A FELDERÍTETT csapat kapusa (a kapus-jelölésből, ha van):
    # kapott kapura tartó lövések / védések / kapott gólok zóna-bontással.
    gk_on_target: int = 0
    gk_saves: int = 0
    gk_conceded_zones: dict = field(default_factory=dict)
    # 7 a 6 elleni (lehozott kapusos) játék összideje másodpercben.
    empty_net_s: float = 0.0
    # Emberelőny-mutatók (kiállítások alatt): lövés/gól előnyben, és a
    # HÁTRÁNYBAN kapott gólok — a "kerüld a kiállítást ellenük" jelhez.
    pp_shots: int = 0
    pp_goals: int = 0
    sh_conceded: int = 0
    sh_seconds: float = 0.0
    # Támadás-mix: {típus: százalék} — lerohanás / gyors indítás / felállt / 7a6.
    attack_mix: dict = field(default_factory=dict)
    # Védekezés-váltások: [{"t","from","to","margin"}] — mikor és milyen
    # állásnál váltottak formát (margin < 0: hátrányban voltak).
    defense_switches: list = field(default_factory=list)
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


def _shot_zone(bx: float, by: float, attacked_goal_x: float) -> str:
    """A lövés helyének kézilabdás zóna-címkéje a TÁMADÓ szemszögéből.

    A bal/jobb oldalt a támadás irányához igazítjuk (a +x kapura támadva a
    balszél az alacsony y; a -x kapura fordítva). Zónák:
    - balszél / jobbszél: a kapuhoz közel, a szélső sávban,
    - beálló (6 m): közel, középen,
    - átlövés bal/közép/jobb: távolabbról (~9 m-től).
    """
    dist = abs(bx - attacked_goal_x)
    # Bal/jobb a támadó szemszögéből: +x kapu felé az alacsony y a BAL oldal.
    left = by < COURT_WIDTH_M * 0.30
    right = by > COURT_WIDTH_M * 0.70
    if attacked_goal_x < COURT_LENGTH_M / 2.0:
        left, right = right, left  # a -x kapura támadva tükrözve
    if dist <= 9.0 and (left or right):
        return "balszél" if left else "jobbszél"
    if dist <= 7.5:
        return "beálló (6 m)"
    if left:
        return "átlövés bal"
    if right:
        return "átlövés jobb"
    return "átlövés közép"


def _shot_zones(match: Match, team: Team, config: TacticsConfig) -> dict:
    """Zóna -> {"shots": n, "goals": n} a csapat lövéseiből (eseményekből)."""
    frames_by_t = {f.t: f for f in match.frames}
    zones: dict[str, dict] = {}
    goal_x = config.attacks_toward_x(team)
    for e in detect_events(match, config):
        if e.team != team or e.type not in (EventType.SHOT, EventType.GOAL):
            continue
        frame = frames_by_t.get(e.t)
        if frame is None or frame.ball is None:
            continue
        z = _shot_zone(frame.ball.x, frame.ball.y, goal_x)
        rec = zones.setdefault(z, {"shots": 0, "goals": 0})
        rec["shots"] += 1
        if e.type == EventType.GOAL:
            rec["goals"] += 1
    # A leggyakoribb zóna elöl (a jelentésben így olvasható).
    return dict(sorted(zones.items(), key=lambda kv: -kv[1]["shots"]))


def formation_switch_profile(match: Match, team: Team,
                             config: Optional[TacticsConfig] = None) -> list[dict]:
    """Védekezés-váltások: MIKOR váltott a csapat formát, és milyen állásnál.

    15 mp-es ablakonként a többségi védekezési forma (csak érdemi, legalább
    ~1 mp-nyi védekezéssel rendelkező ablakok); két szomszédos ablak eltérő
    formája = váltás. A váltás pillanatához az AKTUÁLIS gólkülönbséget is
    kiszámoljuk (a felismert gólokból) — ebből látszik a minta: pl.
    "hátrányban 5-1-re váltanak".

    Visszatérés: [{"t", "from", "to", "margin"}] — margin < 0: a csapat
    épp hátrányban volt a váltáskor.
    """
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = max(1, round(15.0 * fps))

    goals = [(e.t, e.team) for e in detect_events(match, config)
             if e.type == EventType.GOAL]

    def margin_at(t: int) -> int:
        own = sum(1 for gt, gteam in goals if gt <= t and gteam == team)
        opp = sum(1 for gt, gteam in goals if gt <= t and gteam != team)
        return own - opp

    timeline: list[tuple[int, str]] = []
    frames = match.frames
    for w0 in range(0, len(frames), win):
        tally: dict[str, int] = {}
        for f in frames[w0:w0 + win]:
            phase = classify_phase(f, config)
            defends = (phase == Phase.HOME_ATTACK and team == Team.AWAY) or \
                      (phase == Phase.AWAY_ATTACK and team == Team.HOME)
            if not defends:
                continue
            label = detect_formation(f, team, config).label
            tally[label] = tally.get(label, 0) + 1
        if sum(tally.values()) >= fps:
            timeline.append((frames[w0].t,
                             max(tally.items(), key=lambda kv: kv[1])[0]))

    switches: list[dict] = []
    for (_, a), (t1, b) in zip(timeline, timeline[1:]):
        if a != b:
            switches.append({"t": t1, "from": a, "to": b,
                             "margin": margin_at(t1)})
    return switches


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
    # A kapus-jelölést (role="kapus", lásd goalkeeper.py) átvesszük — a
    # kapus ne "irányítóként" szerepeljen, csak mert nála is jár a labda.
    gk_tracks = {p.track_id for f in match.frames for p in f.players
                 if p.role == "kapus"}
    rows: list[KeyPlayer] = []
    # A csapat játékosai: akiket többségében ehhez a csapathoz soroltunk.
    for tid, tteam in team_of.items():
        if tteam != team:
            continue
        pf = poss_frames.get(tid, 0)
        dist = stats[tid].distance_m if tid in stats else 0.0
        role = ("kapus" if tid in gk_tracks
                else "irányító" if pf > 0 else "mezőnyjátékos")
        rows.append(KeyPlayer(track_id=tid, possession_frames=pf,
                              distance_m=round(dist, 1), role=role))
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

    # Helyzetminőség: a gólarányuknál mélyebb kép — a helyzeteikhez képest
    # lőnek-e többet/kevesebbet, és milyen minőségű helyzetekig jutnak el.
    if rep.shots >= 4 and rep.xg > 0:
        if rep.xg_diff >= 1.5:
            strengths.append(f"A helyzeteik FELETT teljesítenek "
                             f"(+{rep.xg_diff:.1f} gól a várhatóhoz képest) — "
                             "a kis esélyű lövéseiket is belövik.")
            keys.append("Ne engedj tiszta helyzetet — minden hibát büntetnek.")
        elif rep.xg_diff <= -1.5:
            weaknesses.append(f"A helyzeteiknél kevesebbet lőnek "
                              f"({rep.xg_diff:.1f}) — a befejezésük bizonytalan.")
        avg_q = rep.xg / rep.shots
        if avg_q >= 0.45:
            keys.append("Türelmesen NAGY helyzetekig jutnak — előbb a beúszást "
                        "és a hatosról jövő lövést zárd le.")
        elif avg_q <= 0.28:
            keys.append("Sok kis esélyű (távoli/szélső) lövést vállalnak — "
                        "belső zónában maradhat szoros a fal.")

    # A VÉDEKEZÉSÜK gyengéi: szabad lövések és lyukas zóna — "hova játssz".
    if rep.def_shots_against >= 4:
        free_pct = 100.0 * rep.def_free_shots / rep.def_shots_against
        if free_pct >= 40.0:
            weaknesses.append(f"A lövők {free_pct:.0f}%-át SZABADON hagyják — "
                              "türelmes körbejátszással kijön a tiszta lövés.")
            keys.append("Járasd a labdát a tiszta lövésig — gyakran marad "
                        "őrizetlen a lövő ellenük.")
        worst = max(rep.def_zones.items(),
                    key=lambda kv: (kv[1]["goals"], kv[1]["shots"]),
                    default=(None, None))[0] if rep.def_zones else None
        if worst and rep.def_zones[worst]["goals"] >= 2:
            keys.append(f"A faluk itt lyukas: {worst} "
                        f"({rep.def_zones[worst]['goals']} kapott gól) — "
                        "ide szervezz befejezést.")

    # Lövési zónák: ha egy zóna dominál (a lövések ≥40%-a, legalább 3 lövésből),
    # konkrét védekezési kulcsot adunk rá.
    total_shots = sum(z["shots"] for z in rep.shot_zones.values())
    if total_shots >= 3:
        zone, rec = next(iter(rep.shot_zones.items()))
        share = 100.0 * rec["shots"] / total_shots
        if share >= 40.0:
            keys.append(f"Lövéseik zöme ({share:.0f}%) innen jön: {zone} — ott zárj szorosabban.")
        for zone, rec in rep.shot_zones.items():
            if rec["shots"] >= 3 and rec["goals"] / rec["shots"] >= 0.6:
                strengths.append(f"Nagyon eredményesek innen: {zone} "
                                 f"({rec['goals']}/{rec['shots']} gól).")
                break

    # Kapusuk: erős/gyenge védés-hatékonyság és a verhető zóna.
    if rep.gk_on_target >= 4:
        save_pct = 100.0 * rep.gk_saves / rep.gk_on_target
        if save_pct >= 40.0:
            strengths.append(f"Jó kapus ({save_pct:.0f}% védés) — a rossz "
                             "helyzetű lövést megfogja.")
        elif save_pct <= 20.0:
            weaknesses.append(f"Bizonytalan kapus ({save_pct:.0f}% védés) — "
                              "érdemes kapura menni.")
    if rep.gk_conceded_zones:
        zone, n = max(rep.gk_conceded_zones.items(), key=lambda kv: kv[1])
        if n >= 2:
            keys.append(f"Kapusuk innen kapta a legtöbb gólt: {zone} "
                        f"({n} gól) — támadd onnan.")

    # Emberelőny: ha jól váltják gólra, a kiállítás ellenük duplán fáj.
    if rep.pp_shots >= 3:
        pp_eff = 100.0 * rep.pp_goals / rep.pp_shots
        if pp_eff >= 60.0:
            strengths.append(f"Emberelőnyben nagyon hatékonyak "
                             f"({rep.pp_goals}/{rep.pp_shots} gól) — "
                             "kerüld a felesleges kiállítást.")
        elif pp_eff <= 25.0:
            weaknesses.append(f"Az emberelőnyt rosszul használják ki "
                              f"({pp_eff:.0f}%) — hátrányban is védekezhetsz "
                              "bátran.")
    if rep.sh_seconds >= 60.0 and rep.sh_conceded >= 2:
        per_min = 60.0 * rep.sh_conceded / rep.sh_seconds
        if per_min >= 1.0:
            weaknesses.append("Emberhátrányban összeomlanak "
                              f"({rep.sh_conceded} kapott gól "
                              f"{rep.sh_seconds / 60:.1f} perc alatt).")

    # Védekezés-váltás minta: hátrányban ismétlődően ugyanarra a formára
    # váltanak → az edző előre begyakorolhatja az ellenszert.
    trailing = [s_ for s_ in rep.defense_switches if s_.get("margin", 0) < 0]
    if trailing:
        tally: dict = {}
        for s_ in trailing:
            tally[s_["to"]] = tally.get(s_["to"], 0) + 1
        to, n = max(tally.items(), key=lambda kv: kv[1])
        if n >= 2:
            keys.append(f"Amikor hátrányban vannak, {to} védekezésre "
                        f"váltanak ({n}×) — legyen begyakorolt támadásod "
                        "ellene.")

    # 7 a 6: ha érdemben használják (meccsenként >= 20 mp), készülj rá.
    if rep.empty_net_s / max(1, rep.matches) >= 20.0:
        strengths.append(f"Tudatosan játszanak 7 a 6 ellen "
                         f"(~{rep.empty_net_s / rep.matches:.0f} mp/meccs).")
        keys.append("Lehozott kapussal támadnak — labdaszerzés után az "
                    "ÜRES KAPURA azonnal dobhatsz, gyakorold a hosszú indítást.")

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
        shot_zones=_shot_zones(match, team, config),
        key_players=[asdict(k) for k in _key_players(match, team, config)],
    )
    # A felderített csapat KAPUSÁNAK mutatói (ha van kapus-jelölés) —
    # ebből jön a "kapusuk innen verhető" kulcs.
    try:
        from .goalkeeper import detect_empty_net, goalkeeper_stats
        gk = goalkeeper_stats(match, config).get(team.value)
        if gk:
            rep.gk_on_target = gk["on_target"]
            rep.gk_saves = gk["saves"]
            rep.gk_conceded_zones = dict(gk["conceded_zones"])
        rep.empty_net_s = round(sum(
            w["duration_s"] for w in detect_empty_net(match, config)
            if w["team"] == team.value), 1)
    except Exception:
        pass
    try:
        from .attack_types import attack_mix
        rep.attack_mix = attack_mix(match, config).get(team.value, {})
    except Exception:
        pass
    try:
        from .xg import match_xg
        trec = match_xg(match, config)["teams"][team.value]
        rep.xg = trec["xg"]
        rep.xg_diff = trec["diff"]
    except Exception:
        pass
    try:
        from .defense import defense_analysis
        drec = defense_analysis(match, config)[team.value]
        rep.def_shots_against = drec["shots_against"]
        rep.def_goals_against = drec["goals_against"]
        rep.def_free_shots = drec["free_shots"]
        rep.def_zones = {z: dict(v) for z, v in drec["zones"].items()}
    except Exception:
        pass
    try:
        rep.defense_switches = formation_switch_profile(match, team, config)
    except Exception:
        pass
    try:
        from .rules import powerplay_efficiency
        eff = powerplay_efficiency(match, config).get(team.value)
        if eff:
            rep.pp_shots = eff["pp_shots"]
            rep.pp_goals = eff["pp_goals"]
            rep.sh_conceded = eff["sh_conceded"]
            rep.sh_seconds = eff["sh_seconds"]
    except Exception:
        pass
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

    # Lövési zónák egyesítése: zónánként összegzett lövés/gól.
    merged_zones: dict[str, dict] = {}
    for r in reports:
        for z, rec in r.shot_zones.items():
            m = merged_zones.setdefault(z, {"shots": 0, "goals": 0})
            m["shots"] += rec["shots"]
            m["goals"] += rec["goals"]
    merged_zones = dict(sorted(merged_zones.items(), key=lambda kv: -kv[1]["shots"]))

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
        shot_zones=merged_zones,
        key_players=[],  # játékos-azonosítók meccsenként eltérők; összevonás nem triviális
        gk_on_target=sum(r.gk_on_target for r in reports),
        gk_saves=sum(r.gk_saves for r in reports),
        empty_net_s=round(sum(r.empty_net_s for r in reports), 1),
        pp_shots=sum(r.pp_shots for r in reports),
        pp_goals=sum(r.pp_goals for r in reports),
        sh_conceded=sum(r.sh_conceded for r in reports),
        sh_seconds=round(sum(r.sh_seconds for r in reports), 1),
        xg=round(sum(r.xg for r in reports), 2),
        xg_diff=round(goals - sum(r.xg for r in reports), 2),
        def_shots_against=sum(r.def_shots_against for r in reports),
        def_goals_against=sum(r.def_goals_against for r in reports),
        def_free_shots=sum(r.def_free_shots for r in reports),
        defense_switches=[s_ for r in reports for s_ in r.defense_switches],
    )
    # Kapott-gól zónák egyesítése.
    for r in reports:
        for z, n in r.gk_conceded_zones.items():
            rep.gk_conceded_zones[z] = rep.gk_conceded_zones.get(z, 0) + n
    # Védekezési zónák egyesítése (kapott lövés/gól/szabad zónánként).
    for r in reports:
        for z, v in r.def_zones.items():
            m = rep.def_zones.setdefault(z, {"shots": 0, "goals": 0, "free": 0})
            for k in ("shots", "goals", "free"):
                m[k] += v.get(k, 0)
    rep.def_zones = dict(sorted(rep.def_zones.items(),
                                key=lambda kv: -kv[1]["shots"]))

    # Támadás-mix egyesítése: a támadás-számmal súlyozott átlag.
    total_atk = sum(max(1, r.attacks) for r in reports)
    mix: dict[str, float] = {}
    for r in reports:
        w = max(1, r.attacks) / total_atk
        for t, pct in r.attack_mix.items():
            mix[t] = mix.get(t, 0.0) + pct * w
    rep.attack_mix = {t: round(v, 1) for t, v in
                      sorted(mix.items(), key=lambda kv: -kv[1])}
    s, w, k = _coach_keys(rep)
    rep.strengths, rep.weaknesses, rep.keys_to_game = s, w, k
    return rep


def scouting_narrative(rep: ScoutingReport) -> list[dict]:
    """Összefüggő magyar mondatok a jelentés számaiból: hogyan játszik a
    csapat, és hol fogható meg. A felderítő képernyő és a nyomtatott
    jelentés bevezetője — sablon-alapú és determinisztikus (minden mondat
    mögött kiszámolt szám áll).

    Visszatérés: [{"title", "body"}, ...]
    """
    name = rep.team_name or "Az ellenfél"
    out: list[dict] = []

    # Így támadnak: tempó + lerohanás-hajlam.
    parts: list[str] = []
    if rep.avg_attack_duration_s:
        if rep.avg_attack_duration_s < 6.0:
            parts.append("gyorsan, átlag "
                         f"{rep.avg_attack_duration_s:.0f} másodperces támadásokkal jön")
        elif rep.avg_attack_duration_s >= 12.0:
            parts.append("türelmesen építkezik (átlag "
                         f"{rep.avg_attack_duration_s:.0f} s egy támadás)")
        else:
            parts.append("közepes tempóban építkezik (átlag "
                         f"{rep.avg_attack_duration_s:.0f} s egy támadás)")
    if rep.fast_break_pct >= 12.0:
        parts.append(f"a labdás ideje {rep.fast_break_pct:.0f}%-ában gyorsan "
                     "indít — a lerohanás fegyverük")
    elif rep.fast_break_pct > 0:
        parts.append(f"lerohanást ritkán vezet ({rep.fast_break_pct:.0f}%)")
    if parts:
        body = f"{name} " + ", ".join(parts) + "."
        # Támadás-mix: a legjellemzőbb típus kiemelése.
        if rep.attack_mix:
            top_type, top_pct = next(iter(rep.attack_mix.items()))
            if top_pct >= 40.0:
                body += (f" Támadásaik {top_pct:.0f}%-a {top_type} — "
                         "erre készülj elsőként.")
        out.append({"title": "Így támadnak", "body": body})

    # Védekezésük: fő forma + váltogatás.
    if rep.defense_distribution:
        items = list(rep.defense_distribution.items())
        main, share = items[0]
        body = f"Fő védekezési formájuk a {main} (az idő {share:.0f}%-ában)."
        if len(items) >= 2 and items[1][1] >= 25.0:
            body += (f" Sokat váltanak {items[1][0]}-ra is "
                     f"({items[1][1]:.0f}%) — készülj mindkettőre.")
        elif share >= 75.0:
            body += " Ragaszkodnak hozzá — egy begyakorolt ellenszer sokat ér."
        out.append({"title": "Védekezésük", "body": body})

    # Befejezésük: hatékonyság + kedvenc zóna. Több meccsnél az összegek
    # félrevezetők lennének jelzés nélkül — kiírjuk a meccs-számot.
    if rep.shots:
        prefix = f"{rep.matches} meccs alatt " if rep.matches > 1 else ""
        body = (f"{prefix}{rep.shots} lövésükből {rep.goals} gól "
                f"({rep.shot_efficiency_pct:.0f}%-os gólarány).")
        total = sum(z["shots"] for z in rep.shot_zones.values())
        if total:
            zone, rec = next(iter(rep.shot_zones.items()))
            body += (f" Legtöbbet innen lőnek: {zone} "
                     f"(a lövéseik {100.0 * rec['shots'] / total:.0f}%-a).")
        if rep.turnovers:
            body += f" Labdaeladásuk: {rep.turnovers}."
        out.append({"title": "Befejezésük", "body": body})

    # Kapusuk: védés-hatékonyság, csak érdemi mintánál (>=4 kapura tartó).
    if rep.gk_on_target >= 4:
        pct = 100.0 * rep.gk_saves / rep.gk_on_target
        if pct >= 40.0:
            body = (f"Kapusuk erős: {rep.gk_on_target} kapura tartó lövésből "
                    f"{rep.gk_saves} védés ({pct:.0f}%) — a tiszta helyzetig "
                    "érdemes türelmesen játszani.")
        elif pct <= 20.0:
            body = (f"Kapusuk bizonytalan: {rep.gk_on_target} kapura tartó "
                    f"lövésből csak {rep.gk_saves} védés ({pct:.0f}%) — "
                    "a kapura lövés kifizetődő.")
        else:
            body = (f"Kapusuk átlagos: {rep.gk_saves} védés "
                    f"{rep.gk_on_target} kapura tartó lövésből ({pct:.0f}%).")
        out.append({"title": "Kapusuk", "body": body})

    # Kulcsjátékos: akinél a legtöbb labda megfordul — a kapust átugorjuk
    # (nála kidobásoknál jár a labda, nem ő szervezi a támadást).
    kp = next((k for k in rep.key_players if k.get("role") != "kapus"), None)
    if kp is not None:
        if kp.get("possession_frames", 0) > 0:
            out.append({
                "title": "Kulcsjátékos",
                "body": (f"A legtöbb labda a(z) {kp['track_id']}. játékosnál "
                         f"fordult meg ({kp.get('role', 'mezőnyjátékos')}) — az "
                         "ő megfogása a támadásaik kulcsa."),
            })

    if not out:
        out.append({"title": "Kevés adat",
                    "body": "Ehhez a csapathoz még kevés a minta — több "
                            "meccs felderítése pontosít."})
    return out


def report_to_dict(rep: ScoutingReport) -> dict:
    """A jelentés JSON-barát szótárrá alakítása (az API-hoz) — a szöveges
    narratívával kiegészítve."""
    d = asdict(rep)
    d["narrative"] = scouting_narrative(rep)
    return d


# ---- Fejlődés-követés (trend) ------------------------------------------------

# A trendben követett mutatók: (mező, magyar címke, egység, jobb-e ha nő; None =
# semleges irány, per_match: a darabszámot meccsenkénti átlagra normáljuk).
_TREND_METRICS = [
    ("attack_share_pct", "Szervezett támadás", "%", True, False),
    ("fast_break_pct", "Gyors indítás", "%", True, False),
    ("avg_attack_duration_s", "Átl. támadáshossz", " s", None, False),
    ("shot_efficiency_pct", "Gólarány", "%", True, False),
    ("shots", "Lövés / meccs", "", True, True),
    ("goals", "Gól / meccs", "", True, True),
    ("turnovers", "Labdaeladás / meccs", "", False, True),
]


def trend_report(older: ScoutingReport, newer: ScoutingReport) -> dict:
    """Két időszak jelentésének összevetése — fejlődés-követés edzői nyelven.

    A darabszám-mutatókat meccsenkénti átlagra normáljuk (különben a több meccs
    "több lövésnek" látszana). Minden mutatóhoz: régi/új érték, változás, és
    hogy ez javulás-e ("better": True/False/None). A "summary" magyar mondatok
    a jelentős (>=10%-os) változásokról.
    """
    metrics = []
    summary = []
    for field_name, label, unit, up_is_better, per_match in _TREND_METRICS:
        a = float(getattr(older, field_name))
        b = float(getattr(newer, field_name))
        if per_match:
            a = a / max(1, older.matches)
            b = b / max(1, newer.matches)
        delta = b - a
        better = None
        if up_is_better is not None and abs(delta) > 1e-9:
            better = (delta > 0) == up_is_better
        metrics.append({
            "metric": field_name, "label": label, "unit": unit,
            "older": round(a, 2), "newer": round(b, 2),
            "delta": round(delta, 2), "better": better,
        })
        # Jelentős változás → magyar mondat (a semleges irányút nem minősítjük).
        base = max(abs(a), 1e-9)
        if better is not None and abs(delta) / base >= 0.10:
            word = "Javult" if better else "Romlott"
            summary.append(f"{word}: {label.lower()} {a:.1f}{unit} → {b:.1f}{unit}.")

    if not summary:
        summary.append("Nincs jelentős változás a két időszak között.")
    return {
        "team_name": newer.team_name,
        "older_matches": older.matches,
        "newer_matches": newer.matches,
        "metrics": metrics,
        "summary": summary,
    }
