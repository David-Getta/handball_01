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
    # Átmenet-védekezés: gyors kapott gólok labdavesztés után (%).
    transition_turnovers: int = 0
    transition_goals_against: int = 0
    # Labdaeladások helye: összes eladás és ebből a TÁMADÓ harmadban
    # elkövetettek (darabszámok, hogy meccsek közt összegezhetők legyenek).
    turnover_total: int = 0
    turnover_front: int = 0
    # Labdabirtoklás-arány (a felderített csapaté, %).
    possession_pct: float = 0.0
    # Gólpassz-vezér: a legtöbb gólpasszt adó játékos (track_id, db).
    top_assist_id: int | None = None
    top_assist_count: int = 0
    # Passz-hálózat: a leggyakoribb passz-párok [{"from","to","passes"}]
    # (meccsek közt párokként összegezhető) és az összes passz.
    pass_pairs: list = field(default_factory=list)
    pass_total: int = 0
    # Hajrá-mérleg: szoros állásról induló hajrákban (utolsó 5 perc)
    # dobott/kapott gólok és az ilyen hajrák száma (meccsek közt összegződik).
    clutch_goals_for: int = 0
    clutch_goals_against: int = 0
    clutch_matches: int = 0
    # A leghosszabb gólcsendjük (mp) — meccsek közt a maximum marad.
    drought_longest_s: float = 0.0
    # Blokkolt lövéseik (a felderített csapat védőinek blokkjai) — összegződik.
    blocks: int = 0
    # Elhúzódó (35 mp+) támadásaik darabszámai — meccsek közt összegződik.
    slow_attacks_total: int = 0
    slow_attacks_slow: int = 0
    # Félidőnkénti gólmérleg (csak felismert szünetű meccsekből, összegződik).
    fh_goals_for: int = 0
    fh_goals_against: int = 0
    sh_goals_for: int = 0
    sh_goals_against: int = 0
    # Lövés-erő: mért lövéseik száma és sebesség-összege (km/h) — az átlag
    # a darabszámokból mindig pontosan visszaszámolható több meccsre is.
    shot_speed_n: int = 0
    shot_speed_sum_kmh: float = 0.0
    shot_speed_max_kmh: float = 0.0
    # Nyomás alatti befejezés: szabad/fedezett lövéseik és góljaik.
    fin_free_shots: int = 0
    fin_free_goals: int = 0
    fin_cov_shots: int = 0
    fin_cov_goals: int = 0
    # Támadás-oldal megoszlás: kockaszámok sávonként (összegződik).
    side_frames: dict = field(default_factory=dict)
    # Válasz-gólok: megválaszolt kapott gólok száma és összes válasz-idő
    # (mp) — az átlag darabszámból pontosan visszaszámolható.
    response_n: int = 0
    response_sum_s: float = 0.0
    # Védőforma elleni hatékonyságuk: {forma: {"shots","goals"}} —
    # formánként összegződik meccsek közt.
    vs_formation: dict = field(default_factory=dict)
    # Támadás-hossz szerinti hatékonyságuk: {vödör: {"attacks","goals"}}.
    duration_eff: dict = field(default_factory=dict)
    # Védekezési nyomás: a labdáshoz legközelebbi védő átlag-távolsága (m).
    defensive_pressure_m: float = 0.0
    # Irányító-függés (playmaker.py): a fő szervezőjük, és mennyit esik a
    # lövésig jutásuk, ha ő nincs a labdánál ("fogd meg" kulcs).
    playmaker_id: int | None = None
    playmaker_involvement_pct: float = 0.0
    playmaker_drop: float | None = None
    playmaker_dependency: str | None = None
    # Csere-minták (substitutions.py): hány cserehullámot futnak, ebből
    # hány jött HÁTRÁNYBAN, és mi a cserék utáni 90 mp gól-mérlege.
    sub_rotations: int = 0
    sub_trailing: int = 0
    sub_after_for: int = 0
    sub_after_against: int = 0
    # Lövési zónák: zóna -> {"shots": n, "goals": n} — HONNAN lőnek és honnan
    # eredményesek (balszél / beálló / átlövés bal-közép-jobb / jobbszél).
    shot_zones: dict = field(default_factory=dict)
    # A FELDERÍTETT csapat kapusa (a kapus-jelölésből, ha van):
    # kapott kapura tartó lövések / védések / kapott gólok zóna-bontással.
    gk_on_target: int = 0
    gk_saves: int = 0
    # A kapusuk bravúr-védései: fogott nagy helyzetek (xG >= 0,5, save).
    gk_big_saves: int = 0
    # Hárított xG: a fogott lövések helyzet-értékének összege — a nehéz
    # védések súlyozott mutatója; meccsek közt összegződik.
    gk_xg_saved: float = 0.0
    # Megmentett gólok (GSAx): kapura tartó xG mínusz kapott gól —
    # negatív, ha a kapusuk a vártnál többet kap; összegződik.
    gk_xg_prevented: float = 0.0
    # Ziccer-mérlegük: nagy xG-jű helyzeteik száma és a gól nélkül maradtak
    # — meccsek közt összegződik, az arány mindig visszaszámolható.
    big_total: int = 0
    big_missed: int = 0
    # Kapus-indításuk: mért indítások, összidő (mp) és a gyorsak száma
    # (védés után 6 mp-en belül a felezőn) — meccsek közt összegződik.
    gk_outlets: int = 0
    gk_outlet_sum_s: float = 0.0
    gk_outlet_fast: int = 0
    gk_conceded_zones: dict = field(default_factory=dict)
    # Minden kapura tartó lövés zóna-bontása (védés is) — ebből és a
    # kapott gólok zónáiból zónánkénti védés-hatékonyság, így a kapus
    # LEGGYENGÉBB sarka is látszik (nemcsak hova esett a legtöbb gól).
    gk_on_target_zones: dict = field(default_factory=dict)
    # 7 a 6 elleni (lehozott kapusos) játék összideje másodpercben.
    empty_net_s: float = 0.0
    # Üres kapura kapott góljaik (7 a 6 közben) — meccsek közt összegződik.
    empty_net_conceded: int = 0
    # A 7 a 6 időzítése: szakaszaik száma és ebből hány indult
    # hátrányban / a hajrában — meccsek közt összegződik.
    en_windows: int = 0
    en_trailing: int = 0
    en_endgame: int = 0
    # Tempó-profil: támadásaik száma és a mért játékpercek — az
    # átlagos támadás/perc több meccsre pontosan visszaszámolható.
    pace_attacks: int = 0
    pace_minutes: float = 0.0
    # Támadás-eredet: {eredet: {"attacks", "goals"}} — honnan indulnak
    # (középkezdés/kidobás/labdaszerzés); eredetenként összegződik.
    attack_origins: dict = field(default_factory=dict)
    # Visszarendeződés: mért átmenetek, összidő és a lassúak (5 mp+)
    # száma — az átlag több meccsre pontosan visszaszámolható.
    rec_transitions: int = 0
    rec_sum_s: float = 0.0
    rec_slow: int = 0
    # Becsült posztok: {track_id: poszt} — meccsek közt az első érdemi
    # becslés marad (a felállás ritkán változik).
    positions: dict = field(default_factory=dict)
    # Lövő-szokások: [{"player_id", "zone", "shots"}] — honnan lőnek a
    # játékosaik; (játékos, zóna) párokként meccsek közt összegezhető.
    shooter_zones: list = field(default_factory=list)
    # A lövőik fáradása: [{"player_id", "drop_sum_pct", "n"}] — a 2.
    # félidei tempó-esések összege és darabszáma (átlag visszaszámolható).
    shooter_fades: list = field(default_factory=list)
    # Gólpassz-párok: [{"from", "to", "goals"}] — ki kinek készíti elő a
    # góljaikat; párokként meccsek közt összegezhető.
    assist_pairs: list = field(default_factory=list)
    # Befejezés-többlet lövőnként: [{"player_id", "diff"}] — gól − xG;
    # játékosonként meccsek közt összegezhető.
    shooter_overperf: list = field(default_factory=list)
    # Blokkolóik: [{"player_id", "blocks"}] — ki tartja a falukat;
    # játékosonként meccsek közt összegezhető.
    blockers: list = field(default_factory=list)
    # A kapus-indításaik célpontjai: [{"player_id", "n"}] — kinek megy
    # az első hosszú passz; játékosonként meccsek közt összegezhető.
    gk_outlet_targets: list = field(default_factory=list)
    # A lerohanásaik befejezői: [{"player_id", "goals"}] — ki futja ki a
    # kontrákat; játékosonként meccsek közt összegezhető.
    fb_finishers: list = field(default_factory=list)
    # A hetes-dobóik: [{"player_id", "attempts", "goals"}] — ki áll oda a
    # hétméteresekhez és milyen mérleggel; meccsek közt összegezhető.
    seven_takers: list = field(default_factory=list)
    # Emberelőny-mutatók (kiállítások alatt): lövés/gól előnyben, és a
    # HÁTRÁNYBAN kapott gólok — a "kerüld a kiállítást ellenük" jelhez.
    pp_shots: int = 0
    pp_goals: int = 0
    sh_conceded: int = 0
    sh_seconds: float = 0.0
    # Támadás-mix: {típus: százalék} — lerohanás / gyors indítás / felállt / 7a6.
    attack_mix: dict = field(default_factory=dict)
    # Támadás-hatékonyság típusonként: {típus: {attacks, shots, goals,
    # shot_pct, goal_pct}} — melyik támadásmódjuk mennyire eredményes.
    attack_efficiency: dict = field(default_factory=dict)
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
    # Poszt-becslés: a "mezőnyjátékos" helyett konkrét posztot írunk,
    # ha van elég támadó-fázisú minta.
    try:
        from .roles import estimate_positions
        est_pos = estimate_positions(match, config).get(team.value, {})
    except Exception:
        est_pos = {}
    rows: list[KeyPlayer] = []
    # A csapat játékosai: akiket többségében ehhez a csapathoz soroltunk.
    for tid, tteam in team_of.items():
        if tteam != team:
            continue
        pf = poss_frames.get(tid, 0)
        dist = stats[tid].distance_m if tid in stats else 0.0
        role = ("kapus" if tid in gk_tracks
                else "irányító" if pf > 0 else "mezőnyjátékos")
        if role == "mezőnyjátékos" and tid in est_pos:
            role = est_pos[tid]["poszt"]
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

    # Irányító-függés: ha a fő szervező nélkül leáll a játékuk, a
    # legjobb védekezési terv Ő maga.
    if rep.playmaker_dependency == "magas" and rep.playmaker_drop is not None:
        weaknesses.append(
            f"Erősen az irányítóra épülnek — nélküle a támadásaik "
            f"lövésig jutása {100 * rep.playmaker_drop:.0f} százalékponttal esik.")
        keys.append("Fogd meg az irányítót (emberfogás/korai kontakt) — "
                    "nélküle leáll a támadásépítésük.")

    # A játékszervezésük tengelye: a leggyakoribb passz-kapcsolat. Ha egy
    # páros viszi a játékot, annak elvágása (sávzárás, letámadás) töri meg
    # a ritmusukat.
    if rep.pass_total >= 15 and rep.pass_pairs:
        pr = rep.pass_pairs[0]
        if int(pr["passes"]) >= 5:
            keys.append(
                f"A játékuk tengelye a {pr['from']}. és {pr['to']}. játékos "
                f"kapcsolata ({pr['passes']} passz) — ennek elvágása "
                "(sávzárás, agresszív letámadás) megtöri a ritmusukat.")

    # Hosszú támadásaik terméketlenek? Ha a hosszú (35 mp+) vödör (4+
    # támadásból) 20+ ponttal rosszabb a rövidnél, a türelem nekik nem
    # barát — a fegyelmezett fal kivárhatja őket.
    long_rec = rep.duration_eff.get("hosszú (35 mp+)")
    short_rec = rep.duration_eff.get("rövid (<15 mp)")
    if (long_rec and short_rec and long_rec["attacks"] >= 4
            and short_rec["attacks"] >= 4):
        long_pct = 100.0 * long_rec["goals"] / long_rec["attacks"]
        short_pct = 100.0 * short_rec["goals"] / short_rec["attacks"]
        if short_pct - long_pct >= 20.0:
            keys.append(
                f"A hosszú támadásaik terméketlenek ({long_pct:.0f}% vs "
                f"{short_pct:.0f}% a rövideknél) — kivárható őket: a "
                "fegyelmezett fal ellen elfogy az ötletük.")

    # Melyik fal fogja meg őket: ha egy forma ellen (4+ lövésből) jóval
    # rosszabbul konvertálnak, mint máshol, az a javasolt felállás.
    if rep.vs_formation:
        pools = [(f_, v) for f_, v in rep.vs_formation.items()
                 if v["shots"] >= 4]
        if len(pools) >= 2:
            def pct(v):
                return 100.0 * v["goals"] / v["shots"]
            worst = min(pools, key=lambda kv: pct(kv[1]))
            best = max(pools, key=lambda kv: pct(kv[1]))
            if pct(best[1]) - pct(worst[1]) >= 25.0:
                keys.append(
                    f"A {worst[0]} fal ellen elakadnak "
                    f"({pct(worst[1]):.0f}% gólarány, a {best[0]} ellen "
                    f"{pct(best[1]):.0f}%) — ellenük {worst[0]}-ban állj fel.")

    # Válasz-idő: gyorsan rendezik-e a sorokat kapott gól után.
    if rep.response_n >= 4:
        avg_resp = rep.response_sum_s / rep.response_n
        if avg_resp <= 60.0:
            strengths.append(
                f"Kapott gól után gyorsan rendezik a sorokat (átlag "
                f"{avg_resp:.0f} mp a válaszgólig) — egy-egy góllal nem "
                "törhetők meg, sorozat kell.")
        elif avg_resp >= 150.0:
            weaknesses.append(
                f"Kapott gól után megtorpannak (átlag {avg_resp:.0f} mp a "
                "válaszgólig) — betalálás után azonnal emelj tempót, "
                "ilyenkor építhető sorozat.")

    # Támadás-oldal súlypont: ha egy szárnyra épül a játék, a fal
    # súlypontja is oda tolható.
    side_total = sum(rep.side_frames.values()) if rep.side_frames else 0
    if side_total >= 250:  # ~10 mp támadójáték minimum
        top_side, top_n = max(rep.side_frames.items(), key=lambda kv: kv[1])
        pct = 100.0 * top_n / side_total
        if top_side != "közép" and pct >= 45.0:
            keys.append(
                f"A támadójátékuk súlypontja a {top_side} oldal "
                f"({pct:.0f}%) — told oda a fal súlypontját, és a "
                "másik szárnyon hagyj teret a kontrának.")

    # Nyomás alatti befejezés: ha fedezve alig, szabadon jól konvertálnak,
    # a fegyelmezett (szabálytalanság nélküli) szoros fal önmagában elég.
    if rep.fin_free_shots >= 3 and rep.fin_cov_shots >= 3:
        free_pct = 100.0 * rep.fin_free_goals / rep.fin_free_shots
        cov_pct = 100.0 * rep.fin_cov_goals / rep.fin_cov_shots
        if free_pct - cov_pct >= 30.0:
            keys.append(
                f"Fedezett helyzetben alig veszélyesek ({cov_pct:.0f}% vs "
                f"{free_pct:.0f}% szabadon) — a szoros, fegyelmezett fal "
                "önmagában megfogja őket, ne szabálytalankodj feleslegesen.")
        elif cov_pct >= 45.0:
            strengths.append(
                f"Nyomás alatt is hidegvérű lövőik vannak (fedezve is "
                f"{cov_pct:.0f}%-ot konvertálnak) — a fal önmagában kevés, "
                "korai zavarás és blokk kell.")

    # Lövés-erő: nagy átlagsebességű lövések — a blokk és a korai zavarás
    # felértékelődik ellenük; lassú lövéseknél a kapus-munka a kulcs.
    if rep.shot_speed_n >= 5:
        avg = rep.shot_speed_sum_kmh / rep.shot_speed_n
        if avg >= 85.0:
            strengths.append(
                f"Nagy erejű lövőik vannak (átlag {avg:.0f} km/h, "
                f"csúcs {rep.shot_speed_max_kmh:.0f}) — a kapus reakcióra "
                "nem építhetsz: blokk és korai zavarás kell.")

    # Félidő-minta: melyik félidőben erősebbek (halmozott mérlegből).
    fh_diff = rep.fh_goals_for - rep.fh_goals_against
    sh_diff = rep.sh_goals_for - rep.sh_goals_against
    fh_total = rep.fh_goals_for + rep.fh_goals_against
    if fh_total + rep.sh_goals_for + rep.sh_goals_against >= 8:
        if sh_diff - fh_diff >= 3:
            keys.append(
                f"A 2. félidőben rendre feljavulnak (félidő-mérleg "
                f"{fh_diff:+d} → {sh_diff:+d}) — az elején szerezz olyan "
                "előnyt, amit a hajrájuk sem fordít meg.")
        elif fh_diff - sh_diff >= 3:
            keys.append(
                f"A 2. félidőben rendre elfogynak (félidő-mérleg "
                f"{fh_diff:+d} → {sh_diff:+d}) — türelem: a meccs második "
                "fele neked dolgozik.")

    # Hosszan járatják a labdát: fegyelmezett fal + passzív-jel kivárása.
    if rep.slow_attacks_total >= 6:
        slow_pct = 100.0 * rep.slow_attacks_slow / rep.slow_attacks_total
        if slow_pct >= 30.0:
            keys.append(
                f"A támadásaik {slow_pct:.0f}%-a 35 mp fölé húzódik — "
                "maradj fegyelmezett a falban, ne ugorj ki: a passzív-jel "
                "és a kapkodó befejezés nekik fáj.")

    # Aktív blokkoló fal: az átlövés ellenük drága — kerülő utak kellenek.
    if rep.blocks >= 3:
        strengths.append(f"Aktív a faluk: {rep.blocks} lövést blokkoltak.")
        keys.append("Sokat blokkolnak — átlövés helyett beálló-játékkal és "
                    "szélső-befutásokkal kerüld a falat.")
    # A fal kulcsembere: ha egy védő adja a blokkok zömét, őt kell
    # kimozdítani a helyéről.
    if rep.blockers and rep.blockers[0]["blocks"] >= 3:
        top_b = rep.blockers[0]
        keys.append(
            f"A faluk kulcsa a(z) {top_b['player_id']}. játékos "
            f"({top_b['blocks']} blokk) — elzárással húzd ki a helyéről: "
            "mögötte nyílik meg az átlövés.")

    # Hosszú gólcsendre hajlamosak: ha leállnak, akkor kell ellépni.
    if rep.drought_longest_s >= 480.0:
        keys.append(
            f"Hajlamosak hosszú gólcsendre (leghosszabb: "
            f"{rep.drought_longest_s / 60:.0f} perc) — ha leáll a "
            "támadójátékuk, tempót fel: ilyenkor kell ellépni.")

    # Hajrá-mérleg: szoros végjátékban nyújtott teljesítményük.
    if rep.clutch_matches >= 1:
        diff = rep.clutch_goals_for - rep.clutch_goals_against
        if diff >= 2:
            strengths.append(
                f"Szoros hajrában erősek (+{diff} gól a hajrákban) — ne "
                "hagyd a végjátékra a döntést.")
        elif diff <= -2:
            weaknesses.append(
                f"Szoros hajrában elfogynak ({diff} gól a hajrákban) — "
                "kiegyenlített meccsen a türelem nekik fáj.")
            keys.append("Tartsd szorosan a meccset a hajráig — a végjátékban "
                        "rendre alulmaradnak.")

    # Csere-mintáik: mikor forgatnak, és mit hoznak a cseréik.
    if rep.sub_rotations >= 2:
        trail_pct = 100.0 * rep.sub_trailing / rep.sub_rotations
        diff = rep.sub_after_for - rep.sub_after_against
        if trail_pct >= 70.0:
            keys.append("Jellemzően hátrányban forgatnak — a cserehullámuk "
                        "után friss sorra és tempóváltásra készülj.")
        if diff >= 2:
            strengths.append(f"A cseréik frissítést hoznak: a cserehullámok "
                             f"utáni mérlegük +{diff} gól.")
        elif diff <= -2:
            weaknesses.append(f"A cserehullámaik után megingnak: a cserék "
                              f"utáni mérlegük {diff} gól — a forgatásuk "
                              "utáni percekben érdemes rájuk ijeszteni.")

    # Védekezési nyomás: szoros vagy laza fal — így támadd.
    if rep.defensive_pressure_m and rep.def_shots_against >= 4:
        if rep.defensive_pressure_m <= 1.3:
            keys.append("Szorosan, előretolva védekeznek (a labdásra "
                        f"átlag {rep.defensive_pressure_m:.1f} m-re lépnek ki) "
                        "— keresd a lecsúszást, a beállót és a betörést.")
        elif rep.defensive_pressure_m >= 2.5:
            keys.append("Lazán, mélyen védekeznek (a labdásra átlag "
                        f"{rep.defensive_pressure_m:.1f} m-re állnak) — "
                        "vállald a 9 m-es lövést, van rá tér.")

    # Gyenge visszazárásuk: futtass rájuk labdaszerzés után.
    if (rep.transition_turnovers >= 4
            and rep.transition_goals_against >= 2):
        pct = 100.0 * rep.transition_goals_against / rep.transition_turnovers
        keys.append(f"Gyenge a visszazárásuk (a labdavesztéseik "
                    f"{pct:.0f}%-a gyors kapott gól) — labdaszerzés után "
                    "azonnal indíts, keresd a lerohanást.")

    # Elöl (támadó harmadban) sok elvesztett labda: felkészült védekezésből
    # azonnali indítás — kontrára építhető gyengeség.
    if rep.turnover_total >= 5:
        front_pct = 100.0 * rep.turnover_front / rep.turnover_total
        if front_pct >= 50.0:
            weaknesses.append(
                f"A labdaeladásaik {front_pct:.0f}%-a a támadó harmadban "
                "történik — labdaszerzéskor a védelmük még előretolva áll.")
            keys.append("Sok labdát adnak el elöl — szervezett labdaszerzés "
                        "után azonnali hosszú indítással büntethető.")

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
    # Megmentett gólok: ha a kapusuk a vártnál többet kap, támadható.
    if rep.gk_xg_prevented / max(1, rep.matches) <= -1.0:
        weaknesses.append(
            f"Kapusuk a helyzetekhez képest sokat kap "
            f"({rep.gk_xg_prevented / rep.matches:+.1f} gól/meccs a "
            "várthoz képest) — a kapura lövés kifizetődő.")
    # Hárított xG: a kapusuk a nehéz lövéseket is fogja-e.
    if rep.gk_xg_saved / max(1, rep.matches) >= 1.0:
        strengths.append(
            f"Kapusuk a nehéz lövéseket is fogja (hárított xG: "
            f"{rep.gk_xg_saved / rep.matches:.1f}/meccs) — a helyzet "
            "önmagában nem gól ellenük.")
    # Ziccer-mérleg: bravúros kapus / kihagyós befejezés.
    if rep.gk_big_saves >= 2:
        strengths.append(f"Kapusuk ziccert is fog ({rep.gk_big_saves} "
                         "bravúr-védés) — a tiszta helyzetet is pontosan, "
                         "sarokra kell befejezni.")
    if rep.big_total >= 4 and rep.big_missed / rep.big_total >= 0.5:
        weaknesses.append(
            f"Ziccereket hagynak ki: {rep.big_total} nagy helyzetükből "
            f"{rep.big_missed} kimaradt — szoros fal mellett a nagy "
            "helyzet sem garantált gól náluk.")
    # Kapus-indításuk: ha a mért indítások fele gyors, a lövés utáni
    # visszarendeződés létkérdés ellenük.
    if rep.gk_outlets >= 2 and rep.gk_outlet_fast / rep.gk_outlets >= 0.5:
        avg = rep.gk_outlet_sum_s / rep.gk_outlets
        keys.append(
            f"Kapusuk gyorsan indít (átlag {avg:.0f} mp alatt a felezőn) "
            "— minden lövés után AZONNAL vissza: a lassú visszafutást "
            "kontrával büntetik.")
    # A hetes-dobójuk: ha kirajzolódik, ki áll oda, a kapus az ő
    # szokásaira készülhet — gyenge mérlegnél ez bizalom-kérdés is.
    if rep.seven_takers and rep.seven_takers[0]["attempts"] >= 2:
        top_s = rep.seven_takers[0]
        sent7 = (f"A heteseiket a(z) {top_s['player_id']}. játékos dobja "
                 f"({top_s['goals']}/{top_s['attempts']} gól) — a kapus "
                 "az ő szokásaira készüljön.")
        if (top_s["attempts"] >= 3
                and top_s["goals"] / top_s["attempts"] <= 0.5):
            sent7 += " A mérlege gyenge: a kapus bátran vállalhat mozgást."
        keys.append(sent7)
    # A beállójuk: ha egyértelmű, ki az, célzott utasítás jár hozzá.
    pivots = [tid for tid, p_ in (rep.positions or {}).items()
              if p_ == "beálló"]
    if len(pivots) == 1:
        keys.append(
            f"A beállójuk a(z) {pivots[0]}. játékos — az elzárásaira "
            "lépj ki korán, és tartsd folyamatos fizikai kontaktban: "
            "ha ő labdát kap 6 méteren, az már késő.")
    # Visszarendeződés: lassú védelem ellen a gyors indítás a fegyver.
    if rep.rec_transitions >= 4:
        rec_avg = rep.rec_sum_s / rep.rec_transitions
        if rec_avg >= 5.0:
            keys.append(
                f"Lassan rendeződnek vissza (átlag {rec_avg:.1f} mp a "
                "felálló védelemig) — labdaszerzés után AZONNAL indíts: "
                "az első 5 másodperc a tiéd.")
        elif rec_avg <= 3.0:
            keys.append(
                f"Villámgyorsan visszaérnek (átlag {rec_avg:.1f} mp) — "
                "a kontra ellenük ritkán jön össze, építs türelmes "
                "felállt támadásra.")
    # Támadás-eredet: ha a góljaik jelentős része labdaszerzésből jön,
    # a labdabiztonság ellenük duplán számít.
    ao = rep.attack_origins or {}
    total_goals_ao = sum(v.get("goals", 0) for v in ao.values())
    steal_goals = (ao.get("labdaszerzés") or {}).get("goals", 0)
    if total_goals_ao >= 5 and steal_goals / total_goals_ao >= 0.5:
        keys.append(
            f"A góljaik {100.0 * steal_goals / total_goals_ao:.0f}%-a "
            "labdaszerzésből indul — a labdabiztonság ellenük duplán "
            "számít: kevesebb kényszerített passz, biztos befejezés.")
    # Lövés-választás: átlagos helyzet-érték lövésenként — megmutatja,
    # válogatósak-e vagy távolról is vállalkoznak.
    if rep.shots >= 10 and rep.xg > 0:
        avg_xg = rep.xg / rep.shots
        if avg_xg <= 0.10:
            keys.append(
                f"Sok kis esélyű lövést vállalnak (átlag "
                f"{avg_xg:.2f} xG/lövés) — a távoli lövést engedheted, "
                "a betörést és a beállót zárd.")
        elif avg_xg >= 0.18:
            keys.append(
                f"Válogatósak: csak jó helyzetből lőnek (átlag "
                f"{avg_xg:.2f} xG/lövés) — fegyelmezett fal és a "
                "passzív-jel kivárása ellenük a recept.")
    # Hidegvérű befejező: aki tartósan a helyzetei felett teljesít,
    # annak a fél-helyzeteit sem szabad megengedni.
    if rep.shooter_overperf and rep.shooter_overperf[0]["diff"] >= 1.0:
        top_o = rep.shooter_overperf[0]
        keys.append(
            f"A(z) {top_o['player_id']}. játékos a helyzetei FELETT "
            f"teljesít ({top_o['diff']:+.1f} gól az xG-hez képest) — ne "
            "hagyd tisztán: a fél-helyzetét is belövi.")
    # A kontra befejezője: ha a lerohanás-gólok zömét ugyanaz a játékos
    # szerzi, a visszafutásnál ő az első számú felvevendő ember.
    if rep.fb_finishers and rep.fb_finishers[0]["goals"] >= 2:
        top_f = rep.fb_finishers[0]
        keys.append(
            f"A lerohanásaikat a(z) {top_f['player_id']}. játékos fejezi "
            f"be ({top_f['goals']} kontra-gól) — labdavesztés után őt "
            "keresd meg először a visszafutásnál.")
    # Az indítás célpontja: ha a hosszú passzok zöme ugyanahhoz a
    # játékoshoz megy, az ő megelőzése öli meg a kontrát.
    if rep.gk_outlets >= 2 and rep.gk_outlet_targets:
        top_t = rep.gk_outlet_targets[0]
        if top_t["n"] >= 2 and top_t["n"] / rep.gk_outlets >= 0.5:
            keys.append(
                f"Az indításaik célpontja a(z) {top_t['player_id']}. "
                f"játékos ({top_t['n']}/{rep.gk_outlets} indítás) — a "
                "visszafutásnál őt kell először felvenni: az elébe "
                "lépés labdaszerzés.")
    # Lövő-szokás: ha a fő lövőjük jellemzően egy zónából dolgozik,
    # arra a helyzetre külön lehet készülni.
    if rep.shooter_zones:
        best = _top_shooter_habit(rep)
        if best:
            pid, z, n, total = best
            keys.append(
                f"A(z) {pid}. játékos lövéseinek {100.0 * n / total:.0f}%-a "
                f"innen jön: {z} — erre a helyzetre külön készülj "
                "(fal-állás, kapus-pozíció).")
    # A fő lövőjük fáradása: hajrá-kulcs, ha a 2. félidőben lelassul.
    if rep.shooter_zones and rep.shooter_fades:
        per_shots: dict = {}
        for rec_sz in rep.shooter_zones:
            per_shots[rec_sz["player_id"]] = (
                per_shots.get(rec_sz["player_id"], 0) + rec_sz["shots"])
        top_pid = max(per_shots.items(), key=lambda kv: kv[1])[0]
        fade = next((f for f in rep.shooter_fades
                     if f["player_id"] == top_pid and f["n"]), None)
        if fade:
            avg_drop = fade["drop_sum_pct"] / fade["n"]
            if avg_drop >= SHOOTER_FADE_PCT:
                keys.append(
                    f"A fő lövőjük ({top_pid}. játékos) elfárad: a második "
                    f"félidőben átlag {avg_drop:.0f}%-kal lassabb — a "
                    "hajrában friss védőt rá, és kényszerítsd "
                    "visszafutásra.")
    # A gól-tengely: ha egy (gólpasszoló -> lövő) páros 3+ gólt hozott,
    # a passzsáv elvágása többet ér, mint a lövő önmagában.
    if rep.assist_pairs:
        top_ap = max(rep.assist_pairs, key=lambda pr: pr["goals"])
        if top_ap["goals"] >= 3:
            keys.append(
                f"A góljaik tengelye a(z) {top_ap['from']}. → "
                f"{top_ap['to']}. páros ({top_ap['goals']} gól) — a "
                "passzsáv elvágása (elé lépés, letámadás) többet ér, "
                "mint a lövő önálló fogása.")
    if rep.gk_conceded_zones:
        zone, n = max(rep.gk_conceded_zones.items(), key=lambda kv: kv[1])
        if n >= 2:
            keys.append(f"Kapusuk innen kapta a legtöbb gólt: {zone} "
                        f"({n} gól) — támadd onnan.")
    # Zóna szerinti védés-hatékonyság: a legalacsonyabb védés%-ú, legalább
    # 3 lövést kapott sarok — konkrét célpont a lövőknek.
    if rep.gk_on_target_zones:
        cand = []
        for z, faced in rep.gk_on_target_zones.items():
            if faced >= 3:
                conc = rep.gk_conceded_zones.get(z, 0)
                cand.append((z, 100.0 * (faced - conc) / faced, faced))
        if cand:
            z, pct, faced = min(cand, key=lambda t: t[1])
            if pct <= 50.0:
                keys.append(f"Kapusuk leggyengébb sarka: {z} "
                            f"({pct:.0f}% védés, {faced} lövésből) — "
                            "ide lőjetek.")

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
    # Tempó-profil: a csapat támadás/perc mutatója (csak érdemi, 20+
    # mért percnél). A meccs-szintű küszöbök (2,2 / 1,4 összesített)
    # fele jut egy csapatra: 1,1 fölött tempós, 0,7 alatt lassú.
    if rep.pace_minutes >= 20.0:
        per_min = rep.pace_attacks / rep.pace_minutes
        if per_min >= 1.1:
            keys.append(
                f"Tempósan játszanak ({per_min:.1f} támadás/perc) — mély "
                "rotációval bírd a tempójukat, és ha megcsúszol, "
                "lassítsd le a meccset.")
        elif per_min <= 0.7:
            keys.append(
                f"Lassú meccseket játszanak ({per_min:.1f} támadás/perc) "
                "— a tempóváltás és a gyors középkezdés kizökkenti őket.")
    # A 7 a 6 időzítése: ha mintázata van, előre lehet rá készülni.
    if rep.en_windows >= 2 and rep.en_trailing / rep.en_windows >= 0.7:
        keys.append(
            f"A 7 a 6-ot hátrányban húzzák elő ({rep.en_trailing}/"
            f"{rep.en_windows} szakasz) — ha vezetsz ellenük, számíts a "
            "lehozott kapusra: beszéld meg előre a hosszú dobás jogát.")
    # Ha ez már gólokba is került nekik, az gyengeség: büntethető szokás.
    if rep.empty_net_conceded >= 2:
        weaknesses.append(
            f"A 7 a 6-juk kockázatos: {rep.empty_net_conceded} gólt "
            "kaptak üres kapura — a labdaszerzés utáni gyors dobás "
            "ellenük kiemelten kifizetődő.")

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
            rep.gk_on_target_zones = dict(gk.get("on_target_zones", {}))
        rep.empty_net_s = round(sum(
            w["duration_s"] for w in detect_empty_net(match, config)
            if w["team"] == team.value), 1)
        from .goalkeeper import empty_net_goals
        rep.empty_net_conceded = empty_net_goals(
            match, config)[team.value]["conceded_empty"]
        from .goalkeeper import empty_net_context
        enc = empty_net_context(match, config)[team.value]
        rep.en_windows = enc["windows"]
        rep.en_trailing = enc["trailing"]
        rep.en_endgame = enc["endgame"]
        from .attack_types import match_pace
        pc = match_pace(match, config)
        if pc.get("available"):
            rep.pace_attacks = pc[f"{team.value}_attacks"]
            rep.pace_minutes = pc["duration_min"]
        from .attack_types import attack_origins
        rep.attack_origins = {
            k: dict(v) for k, v in
            attack_origins(match, config)[team.value].items()}
        from .defense import transition_recovery
        trr = transition_recovery(match, config)[team.value]
        rep.rec_transitions = trr["transitions"]
        rep.rec_sum_s = trr["sum_s"]
        rep.rec_slow = trr["slow"]
        from .roles import estimate_positions
        rep.positions = {tid: r["poszt"] for tid, r in
                         estimate_positions(match, config)
                         .get(team.value, {}).items()}
    except Exception:
        pass
    try:
        from .attack_types import attack_efficiency, attack_mix
        rep.attack_mix = attack_mix(match, config).get(team.value, {})
        rep.attack_efficiency = attack_efficiency(match, config).get(
            team.value, {})
        from .attack_types import fast_break_finishers
        rep.fb_finishers = [
            dict(f) for f in
            fast_break_finishers(match, config)[team.value]]
        from .rules import seven_meter_outcomes
        sv: dict = {}
        for sm in seven_meter_outcomes(match, config):
            if sm["team"] != team.value or sm.get("shooter_id") is None:
                continue
            rec7 = sv.setdefault(sm["shooter_id"],
                                 {"attempts": 0, "goals": 0})
            rec7["attempts"] += 1
            rec7["goals"] += int(sm["outcome"] == "gól")
        rep.seven_takers = [
            {"player_id": pid, **r}
            for pid, r in sorted(sv.items(),
                                 key=lambda kv: -kv[1]["attempts"])]
    except Exception:
        pass
    try:
        from .xg import match_xg
        trec = match_xg(match, config)["teams"][team.value]
        rep.xg = trec["xg"]
        rep.xg_diff = trec["diff"]
        from .xg import BIG_CHANCE_XG, big_saves, missed_big_chances
        rep.big_total = sum(
            1 for sh in match_xg(match, config).get("shots", [])
            if sh["team"] == team.value
            and sh.get("xg", 0.0) >= BIG_CHANCE_XG)
        rep.big_missed = sum(1 for m in missed_big_chances(match, config)
                             if m["team"] == team.value)
        # A lövő az ellenfél — a védés a felderített csapat kapusáé.
        rep.gk_big_saves = sum(1 for b in big_saves(match, config)
                               if b["team"] != team.value)
        from .xg import xg_saved
        rep.gk_xg_saved = xg_saved(match, config)[team.value]
        from .xg import xg_prevented
        rep.gk_xg_prevented = xg_prevented(
            match, config)[team.value]["prevented"]
        from .goalkeeper import outlet_speed
        orec = outlet_speed(match, config)[team.value]
        rep.gk_outlets = orec["outlets"]
        rep.gk_outlet_sum_s = orec["sum_s"]
        rep.gk_outlet_fast = orec["fast"]
        rep.gk_outlet_targets = [dict(t) for t in orec.get("targets", [])]
        # Lövő-szokások: azonosított lövőik lövései zóna szerint.
        goal_x = config.attacks_toward_x(team)
        hab: dict = {}
        for sh in match_xg(match, config).get("shots", []):
            if sh["team"] != team.value or sh.get("player_id") is None:
                continue
            z = _shot_zone(sh["x"], sh["y"], goal_x)
            hab[(sh["player_id"], z)] = hab.get((sh["player_id"], z), 0) + 1
        rep.shooter_zones = [
            {"player_id": pid, "zone": z, "shots": n}
            for (pid, z), n in sorted(hab.items(), key=lambda kv: -kv[1])]
        # A lövőik mért tempó-esése (a fő lövő elleni hajrá-kulcshoz).
        from .stats import player_fatigue
        shooter_ids = {pid for (pid, _z) in hab}
        rep.shooter_fades = [
            {"player_id": f["track_id"],
             "drop_sum_pct": f["drop_pct"], "n": 1}
            for f in player_fatigue(match)
            if f["team"] == team.value and f["track_id"] in shooter_ids]
        from .event_detection import assist_network
        rep.assist_pairs = [dict(pr) for pr in
                            assist_network(match, config)[team.value]["pairs"]]
        rep.shooter_overperf = [
            {"player_id": rec["player_id"], "diff": rec["diff"]}
            for rec in match_xg(match, config).get("shooters", [])
            if rec["team"] == team.value]
    except Exception:
        pass
    try:
        from .defense import defense_analysis
        drec = defense_analysis(match, config)[team.value]
        rep.def_shots_against = drec["shots_against"]
        rep.def_goals_against = drec["goals_against"]
        rep.def_free_shots = drec["free_shots"]
        rep.def_zones = {z: dict(v) for z, v in drec["zones"].items()}
        from .defense import transition_defense
        trec = transition_defense(match, config)[team.value]
        rep.transition_turnovers = trec["turnovers"]
        rep.transition_goals_against = trec["transition_goals_against"]
        from .defense import turnover_zones
        tzrec = turnover_zones(match, config)[team.value]
        rep.turnover_total = tzrec["total"]
        rep.turnover_front = tzrec["zones"].get("támadó", 0)
        from .stats import possession_share
        rep.possession_pct = possession_share(match, config)[team.value]["pct"]
        from .event_detection import assist_network
        leaders = assist_network(match, config)[team.value]["leaders"]
        if leaders:
            rep.top_assist_id = leaders[0]["player_id"]
            rep.top_assist_count = leaders[0]["assists"]
        from .event_detection import pass_network
        pnet = pass_network(match, config)[team.value]
        rep.pass_pairs = list(pnet["pairs"])
        rep.pass_total = pnet["total_passes"]
        from .momentum import clutch_performance
        cp = clutch_performance(match, config)
        if cp.get("available") and cp.get("close"):
            own = cp[team.value]["goals"]
            opp = cp["away" if team == Team.HOME else "home"]["goals"]
            rep.clutch_goals_for = own
            rep.clutch_goals_against = opp
            rep.clutch_matches = 1
        from .momentum import goal_droughts
        rep.drought_longest_s = goal_droughts(match, config)[
            team.value]["longest_s"]
        from .defense import detect_blocks
        blk = detect_blocks(match, config)[team.value]
        rep.blocks = blk["blocks"]
        rep.blockers = [dict(b) for b in blk.get("blockers", [])]
        from .tactics import slow_attacks
        sarec = slow_attacks(match, config)[team.value]
        rep.slow_attacks_total = sarec["attacks"]
        rep.slow_attacks_slow = sarec["slow"]
        from .attack_types import attack_duration_efficiency
        de = attack_duration_efficiency(match, config)[team.value]
        rep.duration_eff = {k: {"attacks": v["attacks"],
                                "goals": v["goals"]} for k, v in de.items()}
        from .tactics import efficiency_vs_formation
        efrec = efficiency_vs_formation(match, config)[team.value]
        rep.vs_formation = {k: {"shots": v["shots"], "goals": v["goals"]}
                            for k, v in efrec.items()}
        from .momentum import goal_responses
        grec = goal_responses(match, config)[team.value]
        rep.response_n = grec["responses"]
        rep.response_sum_s = round(
            (grec["avg_s"] or 0.0) * grec["responses"], 1)
        from .tactics import attack_sides
        asrec = attack_sides(match, config)[team.value]
        n_side = asrec["frames"]
        rep.side_frames = {k: round(asrec[k] * n_side / 100.0)
                           for k in ("bal", "közép", "jobb")}
        from .defense import pressure_finishing
        pf = pressure_finishing(match, config)[team.value]
        rep.fin_free_shots = pf["free"]["shots"]
        rep.fin_free_goals = pf["free"]["goals"]
        rep.fin_cov_shots = pf["covered"]["shots"]
        rep.fin_cov_goals = pf["covered"]["goals"]
        from .event_detection import shot_speeds
        sprec = shot_speeds(match, config)["teams"][team.value]
        rep.shot_speed_n = sprec["n"]
        rep.shot_speed_sum_kmh = round(sprec["avg_kmh"] * sprec["n"], 1)
        rep.shot_speed_max_kmh = sprec["max_kmh"]
        from .momentum import halftime_score, score_progression
        hs = halftime_score(match, config)
        if hs is not None:
            fin = score_progression(match, config)["final"]
            own_i = 0 if team == Team.HOME else 1
            own_key = "home" if team == Team.HOME else "away"
            opp_key = "away" if team == Team.HOME else "home"
            rep.fh_goals_for = hs[own_key]
            rep.fh_goals_against = hs[opp_key]
            rep.sh_goals_for = fin[own_i] - hs[own_key]
            rep.sh_goals_against = fin[1 - own_i] - hs[opp_key]
        from .defense import defensive_pressure
        pr = defensive_pressure(match, config)[team.value]["avg_pressure_m"]
        if pr is not None:
            rep.defensive_pressure_m = pr
    except Exception:
        pass
    try:
        from .playmaker import playmaker_dependency
        prec = playmaker_dependency(match, config)[team.value]
        rep.playmaker_id = prec["playmaker"]
        rep.playmaker_involvement_pct = prec["involvement_pct"]
        rep.playmaker_drop = prec["shot_rate_drop"]
        rep.playmaker_dependency = prec["dependency"]
    except Exception:
        pass
    try:
        from .substitutions import substitution_impact
        goals_sorted = sorted(
            (e.t, e.team) for e in detect_events(match, config)
            if e.type == EventType.GOAL)

        def _margin_at(t: int) -> int:
            own = sum(1 for gt, gteam in goals_sorted
                      if gt <= t and gteam == team)
            opp = sum(1 for gt, gteam in goals_sorted
                      if gt <= t and gteam != team)
            return own - opp

        si = substitution_impact(match, config)
        for ev in si["events"]:
            if ev["team"] != team.value:
                continue
            rep.sub_rotations += 1
            if _margin_at(ev["t"]) < 0:
                rep.sub_trailing += 1
            rep.sub_after_for += ev["goals_for_after"]
            rep.sub_after_against += ev["goals_against_after"]
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



# A fő lövő "elfárad" kulcs küszöbe: ekkora 2. félidei tempó-esés
# (%) fölött érdemes a hajrára külön készülni ellene.
SHOOTER_FADE_PCT = 15.0


def _top_shooter_habit(rep) -> tuple | None:
    """A legkoncentráltabb fő lövő: (player_id, zóna, lövés a zónából,
    összes lövés), ha 4+ lövésének 60%+-a egy zónából jön — különben None.
    A kulcs, a narratíva és a kliens-csempe közös küszöbe."""
    per: dict = {}
    for rec in (rep.shooter_zones or []):
        pz = per.setdefault(rec["player_id"], {})
        pz[rec["zone"]] = pz.get(rec["zone"], 0) + int(rec["shots"])
    best = None
    for pid, zn in per.items():
        total = sum(zn.values())
        z, n = max(zn.items(), key=lambda kv: kv[1])
        if total >= 4 and n / total >= 0.6 and (best is None or n > best[2]):
            best = (pid, z, n, total)
    return best


# "Ágyú" szerep: e lövés-sebesség (km/h) fölött a lövő külön említést
# érdemel a kulcsember-listában — a kapusnak reakció-terv kell rá.
CANNON_KMH = 85.0


def match_key_players(match: Match, config=None) -> dict:
    """Kulcsemberek egy meccsből: kinél dől el a játék — szereponként a
    legjellemzőbb játékos, csak érdemi mintánál. A jelentés Kulcsemberek
    táblája és az API ugyanebből dolgozik (azonos küszöbök a felderítési
    kulcsokkal).

    Visszatérés: {"home"/"away": [{"role", "player_id", "detail"}]}
    """
    config = config or TacticsConfig()
    out: dict = {"home": [], "away": []}

    # Poszt-becslés: ha van elég minta, a mérleg mellé odaírjuk a
    # posztot is ("4 gól / 6 lövés · átlövő").
    try:
        from .roles import estimate_positions
        _posts = estimate_positions(match, config)
    except Exception:
        _posts = {"home": {}, "away": {}}

    def add(side, role, pid, detail):
        p_ = (_posts.get(side) or {}).get(pid)
        if p_ is not None and role != "Bravúr-kapus":
            detail = f"{detail} · {p_['poszt']}"
        out[side].append({"role": role, "player_id": pid, "detail": detail})

    try:
        from .xg import match_xg
        r = match_xg(match, config)
        for side in ("home", "away"):
            top = next((rec for rec in r.get("shooters", [])
                        if rec["team"] == side), None)
            if top and top["shots"] >= 3:
                add(side, "Fő lövő", top["player_id"],
                    f"{top['goals']} gól / {top['shots']} lövés")
    except Exception:
        pass
    try:
        from .defense import detect_blocks
        blk = detect_blocks(match, config)
        for side in ("home", "away"):
            bl = blk[side].get("blockers") or []
            if bl and bl[0]["blocks"] >= 2:
                add(side, "A fal kulcsa", bl[0]["player_id"],
                    f"{bl[0]['blocks']} blokk")
    except Exception:
        pass
    try:
        from .rules import seven_meter_outcomes
        sv: dict = {}
        for sm in seven_meter_outcomes(match, config):
            if sm.get("shooter_id") is None:
                continue
            k = (sm["team"], sm["shooter_id"])
            a, g = sv.get(k, (0, 0))
            sv[k] = (a + 1, g + int(sm["outcome"] == "gól"))
        for side in ("home", "away"):
            cand = [(pid, ag) for (tm, pid), ag in sv.items() if tm == side]
            if cand:
                pid, (a, g) = max(cand, key=lambda c: c[1][0])
                if a >= 2:
                    add(side, "Hetes-dobó", pid, f"{g}/{a} gól")
    except Exception:
        pass
    try:
        from .attack_types import fast_break_finishers
        fb = fast_break_finishers(match, config)
        for side in ("home", "away"):
            fl = fb.get(side) or []
            if fl and fl[0]["goals"] >= 2:
                add(side, "Kontra-befejező", fl[0]["player_id"],
                    f"{fl[0]['goals']} kontra-gól")
    except Exception:
        pass
    try:
        from .goalkeeper import outlet_speed
        osp = outlet_speed(match, config)
        for side in ("home", "away"):
            tg = osp[side].get("targets") or []
            if tg and tg[0]["n"] >= 2:
                add(side, "Indítás-célpont", tg[0]["player_id"],
                    f"{tg[0]['n']} indítás")
    except Exception:
        pass
    try:
        from .event_detection import assist_network
        net = assist_network(match, config)
        for side in ("home", "away"):
            pairs = net[side]["pairs"]
            if pairs and pairs[0]["goals"] >= 2:
                top = pairs[0]
                # A tengely két emberből áll — a lövő a "játékos", az
                # előkészítő a mérlegben szerepel.
                add(side, "Gól-tengely", top["to"],
                    f"a(z) {top['from']}. játékostól, {top['goals']} gól")
    except Exception:
        pass
    try:
        from .xg import match_xg as _mxg_kp
        r_kp = _mxg_kp(match, config)
        for side in ("home", "away"):
            best = None
            for rec in r_kp.get("shooters", []):
                if rec["team"] != side:
                    continue
                if best is None or rec["diff"] > best["diff"]:
                    best = rec
            if best is not None and best["diff"] >= 1.0:
                add(side, "Hidegvérű befejező", best["player_id"],
                    f"{best['diff']:+.1f} gól az xG-hez képest")
    except Exception:
        pass
    try:
        from .goalkeeper import goalkeeper_stats
        from .xg import big_saves
        gstats = goalkeeper_stats(match)
        n_big = {"home": 0, "away": 0}
        for bs in big_saves(match, config):
            # A lövő csapata áll a rekordban — a védés a másik oldalé.
            n_big["away" if bs["team"] == "home" else "home"] += 1
        for side in ("home", "away"):
            rec_gk = gstats.get(side)
            if rec_gk and n_big[side] >= 2:
                add(side, "Bravúr-kapus", rec_gk["track_id"],
                    f"{n_big[side]} fogott ziccer")
    except Exception:
        pass
    try:
        from .event_detection import shot_speeds
        sp = shot_speeds(match, config)
        for side in ("home", "away"):
            best = None
            for sh in sp.get("shots", []):
                if sh["team"] != side or sh.get("player_id") is None:
                    continue
                if best is None or sh["speed_kmh"] > best["speed_kmh"]:
                    best = sh
            if best is not None and best["speed_kmh"] >= CANNON_KMH:
                add(side, "Ágyú", best["player_id"],
                    f"{best['speed_kmh']:.0f} km/h lövés")
    except Exception:
        pass
    return out


def _merge_seven_takers(reports) -> list:
    """Hetes-dobónkénti kísérlet/gól számok pontos összegzése."""
    tally: dict = {}
    for r in reports:
        for t in (r.seven_takers or []):
            cur = tally.setdefault(t["player_id"], [0, 0])
            cur[0] += int(t["attempts"])
            cur[1] += int(t["goals"])
    return [{"player_id": pid, "attempts": a, "goals": g}
            for pid, (a, g) in sorted(tally.items(),
                                      key=lambda kv: -kv[1][0])]


def _merge_fb_finishers(reports) -> list:
    """Kontra-befejezők gólszámainak pontos összegzése meccsek közt."""
    tally: dict = {}
    for r in reports:
        for f in (r.fb_finishers or []):
            tally[f["player_id"]] = (tally.get(f["player_id"], 0)
                                     + int(f["goals"]))
    return [{"player_id": pid, "goals": n}
            for pid, n in sorted(tally.items(), key=lambda kv: -kv[1])]


def _merge_outlet_targets(reports) -> list:
    """Indítás-célpontok darabszámainak pontos összegzése meccsek közt."""
    tally: dict = {}
    for r in reports:
        for t in (r.gk_outlet_targets or []):
            tally[t["player_id"]] = tally.get(t["player_id"], 0) + int(t["n"])
    return [{"player_id": pid, "n": n}
            for pid, n in sorted(tally.items(), key=lambda kv: -kv[1])]


def _merge_blockers(reports) -> list:
    """Blokkolónkénti blokkszámok pontos összegzése meccsek közt."""
    tally: dict = {}
    for r in reports:
        for b in (r.blockers or []):
            tally[b["player_id"]] = (tally.get(b["player_id"], 0)
                                     + int(b["blocks"]))
    return [{"player_id": pid, "blocks": n}
            for pid, n in sorted(tally.items(), key=lambda kv: -kv[1])]


def _merge_attack_origins(reports) -> dict:
    """Eredet szerinti támadás/gól számok pontos összegzése."""
    tally: dict = {}
    for r in reports:
        for k, v in (r.attack_origins or {}).items():
            cur = tally.setdefault(k, {"attacks": 0, "goals": 0})
            cur["attacks"] += int(v.get("attacks", 0))
            cur["goals"] += int(v.get("goals", 0))
    return tally


def _merge_shooter_overperf(reports) -> list:
    """Lövőnkénti befejezés-többlet (gól − xG) pontos összegzése."""
    tally: dict = {}
    for r in reports:
        for rec in (r.shooter_overperf or []):
            tally[rec["player_id"]] = round(
                tally.get(rec["player_id"], 0.0) + float(rec["diff"]), 2)
    return [{"player_id": pid, "diff": d}
            for pid, d in sorted(tally.items(), key=lambda kv: -kv[1])]


def _merge_assist_pairs(reports) -> list:
    """(gólpasszoló, lövő) párok gólszámainak pontos összegzése."""
    tally: dict = {}
    for r in reports:
        for pr in (r.assist_pairs or []):
            k = (pr["from"], pr["to"])
            tally[k] = tally.get(k, 0) + int(pr["goals"])
    return [{"from": a, "to": b, "goals": n}
            for (a, b), n in sorted(tally.items(), key=lambda kv: -kv[1])]


def _merge_shooter_fades(reports) -> list:
    """Játékosonkénti tempó-esés összegek pontos összevonása."""
    tally: dict = {}
    for r in reports:
        for rec in (r.shooter_fades or []):
            cur = tally.setdefault(rec["player_id"], [0.0, 0])
            cur[0] += float(rec["drop_sum_pct"])
            cur[1] += int(rec["n"])
    return [{"player_id": pid, "drop_sum_pct": round(d, 1), "n": n}
            for pid, (d, n) in sorted(tally.items())]


def _merge_shooter_zones(reports) -> list:
    """(játékos, zóna) párok lövésszámainak pontos összegzése meccsek közt."""
    tally: dict = {}
    for r in reports:
        for rec in (r.shooter_zones or []):
            k = (rec["player_id"], rec["zone"])
            tally[k] = tally.get(k, 0) + int(rec["shots"])
    return [{"player_id": pid, "zone": z, "shots": n}
            for (pid, z), n in sorted(tally.items(), key=lambda kv: -kv[1])]

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
        gk_big_saves=sum(r.gk_big_saves for r in reports),
        gk_xg_saved=round(sum(r.gk_xg_saved for r in reports), 2),
        gk_xg_prevented=round(sum(r.gk_xg_prevented for r in reports), 2),
        gk_outlets=sum(r.gk_outlets for r in reports),
        gk_outlet_sum_s=round(sum(r.gk_outlet_sum_s for r in reports), 1),
        gk_outlet_fast=sum(r.gk_outlet_fast for r in reports),
        big_total=sum(r.big_total for r in reports),
        big_missed=sum(r.big_missed for r in reports),
        empty_net_s=round(sum(r.empty_net_s for r in reports), 1),
        empty_net_conceded=sum(r.empty_net_conceded for r in reports),
        en_windows=sum(r.en_windows for r in reports),
        en_trailing=sum(r.en_trailing for r in reports),
        en_endgame=sum(r.en_endgame for r in reports),
        pace_attacks=sum(r.pace_attacks for r in reports),
        pace_minutes=round(sum(r.pace_minutes for r in reports), 1),
        attack_origins=_merge_attack_origins(reports),
        rec_transitions=sum(r.rec_transitions for r in reports),
        rec_sum_s=round(sum(r.rec_sum_s for r in reports), 1),
        rec_slow=sum(r.rec_slow for r in reports),
        positions={tid: poszt for r in reversed(reports)
                   for tid, poszt in (r.positions or {}).items()},
        shooter_zones=_merge_shooter_zones(reports),
        shooter_fades=_merge_shooter_fades(reports),
        assist_pairs=_merge_assist_pairs(reports),
        shooter_overperf=_merge_shooter_overperf(reports),
        blockers=_merge_blockers(reports),
        gk_outlet_targets=_merge_outlet_targets(reports),
        fb_finishers=_merge_fb_finishers(reports),
        seven_takers=_merge_seven_takers(reports),
        pp_shots=sum(r.pp_shots for r in reports),
        pp_goals=sum(r.pp_goals for r in reports),
        sh_conceded=sum(r.sh_conceded for r in reports),
        sh_seconds=round(sum(r.sh_seconds for r in reports), 1),
        xg=round(sum(r.xg for r in reports), 2),
        xg_diff=round(goals - sum(r.xg for r in reports), 2),
        def_shots_against=sum(r.def_shots_against for r in reports),
        def_goals_against=sum(r.def_goals_against for r in reports),
        def_free_shots=sum(r.def_free_shots for r in reports),
        transition_turnovers=sum(r.transition_turnovers for r in reports),
        transition_goals_against=sum(r.transition_goals_against for r in reports),
        turnover_total=sum(r.turnover_total for r in reports),
        turnover_front=sum(r.turnover_front for r in reports),
        clutch_goals_for=sum(r.clutch_goals_for for r in reports),
        clutch_goals_against=sum(r.clutch_goals_against for r in reports),
        clutch_matches=sum(r.clutch_matches for r in reports),
        drought_longest_s=max((r.drought_longest_s for r in reports),
                              default=0.0),
        blocks=sum(r.blocks for r in reports),
        slow_attacks_total=sum(r.slow_attacks_total for r in reports),
        slow_attacks_slow=sum(r.slow_attacks_slow for r in reports),
        fh_goals_for=sum(r.fh_goals_for for r in reports),
        fh_goals_against=sum(r.fh_goals_against for r in reports),
        sh_goals_for=sum(r.sh_goals_for for r in reports),
        sh_goals_against=sum(r.sh_goals_against for r in reports),
        shot_speed_n=sum(r.shot_speed_n for r in reports),
        fin_free_shots=sum(r.fin_free_shots for r in reports),
        fin_free_goals=sum(r.fin_free_goals for r in reports),
        fin_cov_shots=sum(r.fin_cov_shots for r in reports),
        fin_cov_goals=sum(r.fin_cov_goals for r in reports),
        side_frames={k: sum(r.side_frames.get(k, 0) for r in reports)
                     for k in ("bal", "közép", "jobb")},
        response_n=sum(r.response_n for r in reports),
        response_sum_s=round(sum(r.response_sum_s for r in reports), 1),
        shot_speed_sum_kmh=round(sum(r.shot_speed_sum_kmh
                                     for r in reports), 1),
        shot_speed_max_kmh=max((r.shot_speed_max_kmh for r in reports),
                               default=0.0),
        possession_pct=round(
            sum(r.possession_pct for r in reports if r.possession_pct)
            / max(1, sum(1 for r in reports if r.possession_pct)), 1),
        defensive_pressure_m=round(
            sum(r.defensive_pressure_m for r in reports if r.defensive_pressure_m)
            / max(1, sum(1 for r in reports if r.defensive_pressure_m)), 2),
        sub_rotations=sum(r.sub_rotations for r in reports),
        sub_trailing=sum(r.sub_trailing for r in reports),
        sub_after_for=sum(r.sub_after_for for r in reports),
        sub_after_against=sum(r.sub_after_against for r in reports),
        defense_switches=[s_ for r in reports for s_ in r.defense_switches],
    )
    # Támadás-hossz szerinti hatékonyság egyesítése (vödrönként).
    for r in reports:
        for k, v in r.duration_eff.items():
            m = rep.duration_eff.setdefault(k, {"attacks": 0, "goals": 0})
            m["attacks"] += v["attacks"]
            m["goals"] += v["goals"]
    # Védőforma elleni hatékonyság egyesítése (formánként összegezve).
    for r in reports:
        for form, v in r.vs_formation.items():
            m = rep.vs_formation.setdefault(form, {"shots": 0, "goals": 0})
            m["shots"] += v["shots"]
            m["goals"] += v["goals"]
    # Passz-hálózat egyesítése: azonos (from,to) párok passzai összeadódnak.
    rep.pass_total = sum(r.pass_total for r in reports)
    merged_pairs: dict = {}
    for r in reports:
        for pr in r.pass_pairs:
            key = (pr["from"], pr["to"])
            merged_pairs[key] = merged_pairs.get(key, 0) + int(pr["passes"])
    rep.pass_pairs = [{"from": a, "to": b, "passes": n}
                      for (a, b), n in sorted(merged_pairs.items(),
                                              key=lambda kv: -kv[1])[:5]]
    # Kapott-gól és kapura tartó lövés zónák egyesítése.
    for r in reports:
        for z, n in r.gk_conceded_zones.items():
            rep.gk_conceded_zones[z] = rep.gk_conceded_zones.get(z, 0) + n
        for z, n in r.gk_on_target_zones.items():
            rep.gk_on_target_zones[z] = rep.gk_on_target_zones.get(z, 0) + n
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
    # Támadás-hatékonyság egyesítése: típusonként a darabszámok összege.
    eff: dict[str, dict] = {}
    for r in reports:
        for typ, rec in (r.attack_efficiency or {}).items():
            m = eff.setdefault(typ, {"attacks": 0, "shots": 0, "goals": 0})
            for key in ("attacks", "shots", "goals"):
                m[key] += rec.get(key, 0)
    for rec in eff.values():
        n = max(1, rec["attacks"])
        rec["shot_pct"] = round(100.0 * rec["shots"] / n, 1)
        rec["goal_pct"] = round(100.0 * rec["goals"] / n, 1)
    rep.attack_efficiency = eff
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
        # Hatékonyság: a legeredményesebb támadás-típusuk külön figyelmeztetés.
        best = None
        for typ, rec in (rep.attack_efficiency or {}).items():
            if rec.get("attacks", 0) >= 3 and (
                    best is None or rec["goal_pct"] > best[1]["goal_pct"]):
                best = (typ, rec)
        if best and best[1]["goal_pct"] >= 50.0:
            body += (f" A legeredményesebb támadásmódjuk a {best[0]} "
                     f"({best[1]['goal_pct']:.0f}% gól) — ezt kell "
                     "elsőként megfognod.")
        # A játékszervezés tengelye: a leggyakoribb passz-kapcsolat.
        if rep.pass_total >= 15 and rep.pass_pairs:
            pr = rep.pass_pairs[0]
            if int(pr["passes"]) >= 5:
                body += (f" A játékuk a {pr['from']}. és {pr['to']}. játékos "
                         f"tengelyén megy ({pr['passes']} passz).")
        # Miből élnek: ha kirajzolódik a fő gól-forrás, elmondjuk.
        ao_n = rep.attack_origins or {}
        tg = sum(v.get("goals", 0) for v in ao_n.values())
        if tg >= 5:
            top_o, top_v = max(ao_n.items(),
                               key=lambda kv: kv[1].get("goals", 0))
            share_o = 100.0 * top_v.get("goals", 0) / tg
            if share_o >= 50.0:
                body += (f" A góljaik fő forrása: {top_o} "
                         f"({share_o:.0f}%).")
        # Melyik fal fogja meg őket (ha van elég formánkénti minta).
        pools = [(f_, v) for f_, v in (rep.vs_formation or {}).items()
                 if v["shots"] >= 4]
        if len(pools) >= 2:
            def _pct(v):
                return 100.0 * v["goals"] / v["shots"]
            worst = min(pools, key=lambda kv: _pct(kv[1]))
            best = max(pools, key=lambda kv: _pct(kv[1]))
            if _pct(best[1]) - _pct(worst[1]) >= 25.0:
                body += (f" A {worst[0]} fal ellen csak "
                         f"{_pct(worst[1]):.0f}%-ot konvertálnak "
                         f"(a {best[0]} ellen {_pct(best[1]):.0f}%-ot).")
        # Hosszú vs rövid támadások hozama (ha van elég minta).
        lr = rep.duration_eff.get("hosszú (35 mp+)")
        sr = rep.duration_eff.get("rövid (<15 mp)")
        if (lr and sr and lr["attacks"] >= 4 and sr["attacks"] >= 4):
            lp = 100.0 * lr["goals"] / lr["attacks"]
            sp_ = 100.0 * sr["goals"] / sr["attacks"]
            if sp_ - lp >= 20.0:
                body += (f" A hosszú támadásaik terméketlenek "
                         f"({lp:.0f}% vs {sp_:.0f}% a rövideknél).")
            elif lp - sp_ >= 20.0:
                body += (f" A türelmes, hosszú támadásaik kifejezetten "
                         f"eredményesek ({lp:.0f}%).")
        # Oldal-súlypont: melyik szárnyra épül a támadásépítés.
        side_total = sum(rep.side_frames.values()) if rep.side_frames else 0
        if side_total >= 250:
            top_side, top_n = max(rep.side_frames.items(),
                                  key=lambda kv: kv[1])
            pct = 100.0 * top_n / side_total
            if top_side != "közép" and pct >= 45.0:
                body += (f" A támadásépítésük súlypontja a {top_side} "
                         f"oldal ({pct:.0f}%).")
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

    # Félidő-minta: a felismert szünetű meccsek félidőnkénti mérlegéből.
    fh_d = rep.fh_goals_for - rep.fh_goals_against
    sh_d = rep.sh_goals_for - rep.sh_goals_against
    if (rep.fh_goals_for + rep.fh_goals_against
            + rep.sh_goals_for + rep.sh_goals_against) >= 8:
        if sh_d - fh_d >= 3:
            out.append({"title": "Félidő-minta", "body": (
                f"A második félidőben rendre feljavulnak: a félidő-mérlegük "
                f"{fh_d:+d}-ról {sh_d:+d}-ra vált — az első félidőben kell "
                "előnyt építeni ellenük.")})
        elif fh_d - sh_d >= 3:
            out.append({"title": "Félidő-minta", "body": (
                f"A második félidőben rendre elfogynak: a félidő-mérlegük "
                f"{fh_d:+d}-ról {sh_d:+d}-ra romlik — a meccs második fele "
                "ellenük dolgozik.")})

    # Végjáték: a szoros hajrák halmozott mérlege (ha volt ilyen hajrá).
    if rep.clutch_matches >= 1:
        diff = rep.clutch_goals_for - rep.clutch_goals_against
        n = rep.clutch_matches
        base = (f"{n} szoros hajrát" if n > 1 else "Egy szoros hajrát"
                ) + " látott a felderítés"
        if diff >= 2:
            body = (f"{base}: a mérlegük +{diff} gól — a végjátékban "
                    "hidegvérűek, ne hagyd a döntést a hajrára.")
        elif diff <= -2:
            body = (f"{base}: a mérlegük {diff} gól — a végjátékban "
                    "rendre alulmaradnak, a szoros meccs neked kedvez.")
        else:
            body = (f"{base}: kiegyenlített hajrá-mérleg ({diff:+d} gól).")
        out.append({"title": "Végjáték", "body": body})

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
        # Lövés-választás: válogatósak vagy távolról is vállalkoznak.
        if rep.shots >= 10 and rep.xg > 0:
            avg_xg = rep.xg / rep.shots
            if avg_xg <= 0.10:
                body += (f" Sok kis esélyű lövést vállalnak (átlag "
                         f"{avg_xg:.2f} xG/lövés).")
            elif avg_xg >= 0.18:
                body += (f" Válogatósak: csak jó helyzetből lőnek "
                         f"(átlag {avg_xg:.2f} xG/lövés).")
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
        if rep.gk_big_saves >= 2:
            body += (f" Ziccert is fog: {rep.gk_big_saves} nagy helyzetet "
                     "(xG ≥ 0,5) hárított.")
        if rep.gk_xg_saved / max(1, rep.matches) >= 1.0:
            body += (f" A védései nehézség-súlyozva is erősek: "
                     f"{rep.gk_xg_saved / rep.matches:.1f} hárított "
                     "xG meccsenként.")
        out.append({"title": "Kapusuk", "body": body})

    # Fő lövőjük szokása: honnan dolgozik (ha kirajzolódik a minta).
    habit = _top_shooter_habit(rep)
    if habit:
        pid, z, n, total = habit
        out.append({
            "title": "Fő lövőjük",
            "body": (f"A(z) {pid}. játékos {total} lövéséből {n} "
                     f"({100.0 * n / total:.0f}%) ugyanonnan jött: {z} — "
                     "a fal és a kapus erre a helyzetre készülhet."),
        })

    # Felállásuk: a becsült posztok egy mondatban.
    if rep.positions:
        by_post: dict = {}
        for tid, poszt in sorted(rep.positions.items()):
            by_post.setdefault(poszt, []).append(str(tid))
        order = ["irányító", "átlövő", "beálló", "szélső"]
        parts_p = [f"{p_}: {', '.join(by_post[p_])}."
                   for p_ in order if p_ in by_post]
        if parts_p:
            out.append({
                "title": "Felállásuk",
                "body": ("Becsült posztok a mozgásképből — "
                         + " ".join(parts_p)),
            })

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
    # Új rétegek: birtoklás (több = jobb), védekezési nyomás (kevesebb
    # méter = szorosabb = jobb), elöl vesztett labdák (kevesebb = jobb).
    ("possession_pct", "Labdabirtoklás", "%", True, False),
    ("defensive_pressure_m", "Védekezési nyomás", " m", False, False),
    ("turnover_front", "Elöl vesztett labda / meccs", "", False, True),
    ("blocks", "Blokk / meccs", "", True, True),
    # Kapus-rétegek: fogott ziccerek és gyors indítások (több = jobb).
    ("gk_big_saves", "Bravúr-védés / meccs", "", True, True),
    ("gk_outlet_fast", "Gyors indítás védés után / meccs", "", True, True),
    ("gk_xg_saved", "Hárított xG / meccs", "", True, True),
    ("gk_xg_prevented", "Megmentett gól (GSAx) / meccs", "", True, True),
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
    # Az új, opcionális rétegek 0-ja "nincs mérés"-t jelent — ilyenkor a
    # mutatót kihagyjuk, hogy ne látsszon hamis javulásnak/romlásnak.
    optional = {"possession_pct", "defensive_pressure_m",
                "gk_big_saves", "gk_outlet_fast", "gk_xg_saved",
                "gk_xg_prevented"}
    for field_name, label, unit, up_is_better, per_match in _TREND_METRICS:
        a = float(getattr(older, field_name))
        b = float(getattr(newer, field_name))
        if field_name in optional and (a == 0.0 or b == 0.0):
            continue
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
