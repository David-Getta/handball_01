"""Védekezés-elemzés — a KAPOTT lövések oldala: hol lyukas a fal.

A támadó-oldali rétegek (lövéstérkép, xG, zónák) tükre: minden csapatra
megnézzük, milyen lövéseket ENGEDETT az ellenfélnek:

- SZABAD LÖVÉS: a lövés pillanatában nem volt védő a lövő közelében
  (FREE_DEF_RADIUS_M) — fedezés-hiba, a legtanulságosabb visszanézni;
- zóna-bontás: melyik zónából kapjuk a lövéseket/gólokat (hol a lyuk);
- kapott xG: az engedett helyzetek összesített értéke — a védekezés
  minőségének mérőszáma, függetlenül attól, hogy az ellenfél belőtte-e.

Tiszta adatfeldolgozás a felismert eseményekből, videó nélkül tesztelhető.
"""

from __future__ import annotations

from typing import Optional

from ..models.tracking import Match, Team
from .tactics import TacticsConfig

# Ha a lövés pillanatában ennél messzebb van a legközelebbi védő a lövőtől,
# a lövést SZABADNAK számoljuk (kézilabdában a fedezés 1-2 m-en belül él).
FREE_DEF_RADIUS_M = 2.0


def defense_analysis(match: Match,
                     config: Optional[TacticsConfig] = None) -> dict:
    """Mindkét csapat VÉDEKEZÉSÉNEK képe a kapott lövésekből.

    Visszatérés csapatonként ("home"/"away" = a VÉDEKEZŐ csapat):
    {"shots_against", "goals_against", "xg_against", "free_shots",
     "free_pct", "zones": {zóna: {"shots","goals","free"}}, "worst_zone",
     "shots": [{"t","zone","free","xg","goal"}]}
    — free None, ha a lövő nem azonosítható (ott fedezést sem tudunk mérni).
    """
    import math

    from .event_detection import EventType, detect_shots
    from .scouting import _shot_zone
    from .xg import xg_of_position

    config = config or TacticsConfig()
    by_t = {f.t: f for f in match.frames}
    out = {side: {"shots_against": 0, "goals_against": 0, "xg_against": 0.0,
                  "free_shots": 0, "free_pct": None, "zones": {},
                  "worst_zone": None, "shots": []}
           for side in ("home", "away")}

    for e in detect_shots(match, config):
        if e.type not in (EventType.SHOT, EventType.GOAL):
            continue
        f = by_t.get(e.t)
        if f is None:
            continue
        defender_team = Team.AWAY if e.team == Team.HOME else Team.HOME
        rec = out[defender_team.value]

        # A lövés helye: a lövő pozíciója, tartalékban a labdáé.
        x = y = None
        shooter = None
        if e.player_id is not None:
            for p in f.players:
                if p.track_id == e.player_id:
                    shooter = p
                    x, y = p.x, p.y
                    break
        if x is None and f.ball is not None:
            x, y = f.ball.x, f.ball.y
        if x is None:
            continue

        goal_x = config.attacks_toward_x(e.team)
        zone = _shot_zone(x, y, goal_x)
        xg = xg_of_position(x, y, goal_x)
        is_goal = e.type == EventType.GOAL

        # Szabad lövés: a legközelebbi VÉDŐ távolsága a lövőtől.
        free = None
        if shooter is not None:
            dists = [math.hypot(p.x - shooter.x, p.y - shooter.y)
                     for p in f.players
                     if p.team == defender_team and p.role != "kapus"]
            if dists:
                free = min(dists) > FREE_DEF_RADIUS_M

        rec["shots_against"] += 1
        rec["xg_against"] += xg
        if is_goal:
            rec["goals_against"] += 1
        if free:
            rec["free_shots"] += 1
        z = rec["zones"].setdefault(zone, {"shots": 0, "goals": 0, "free": 0})
        z["shots"] += 1
        if is_goal:
            z["goals"] += 1
        if free:
            z["free"] += 1
        rec["shots"].append({"t": e.t, "zone": zone, "free": free,
                             "xg": xg, "goal": is_goal})

    for rec in out.values():
        rec["xg_against"] = round(rec["xg_against"], 2)
        if rec["shots_against"]:
            rec["free_pct"] = round(
                100.0 * rec["free_shots"] / rec["shots_against"], 1)
        if rec["zones"]:
            # A leglyukasabb zóna: a legtöbb kapott gól (döntetlennél lövés).
            rec["worst_zone"] = max(
                rec["zones"].items(),
                key=lambda kv: (kv[1]["goals"], kv[1]["shots"]))[0]
            rec["zones"] = dict(sorted(rec["zones"].items(),
                                       key=lambda kv: -kv[1]["shots"]))
    return out


def pressure_finishing(match, config=None) -> dict:
    """Nyomás alatti befejezés: szabad vs fedezett lövések gólaránya.

    A defense_analysis lövésenkénti free-jelét a TÁMADÓ oldalról
    összegezzük: hogyan konvertál a csapat, amikor a lövőt fedezik,
    ahhoz képest, amikor szabadon lő. Nagy különbség = a csapat csak
    szabadon veszélyes (jó hír a fegyelmezett falnak); kis különbség =
    nyomás alatt is hidegvérű lövőik vannak.

    Visszatérés TÁMADÓ csapatonként: {"free": {"shots","goals","pct"},
    "covered": {"shots","goals","pct"}} — pct None kevés mintánál (0
    lövés)."""
    config = config or TacticsConfig()
    d = defense_analysis(match, config)
    out = {}
    for atk, defn in (("home", "away"), ("away", "home")):
        rec = {"free": {"shots": 0, "goals": 0, "pct": None},
               "covered": {"shots": 0, "goals": 0, "pct": None}}
        for sh in d[defn]["shots"]:
            if sh["free"] is None:
                continue
            bucket = rec["free" if sh["free"] else "covered"]
            bucket["shots"] += 1
            if sh["goal"]:
                bucket["goals"] += 1
        for bucket in rec.values():
            if bucket["shots"]:
                bucket["pct"] = round(
                    100.0 * bucket["goals"] / bucket["shots"], 1)
        out[atk] = rec
    return out


# A labdaeladás után ennyi másodpercen belüli kapott gól "átmenet-gól".
TRANSITION_WINDOW_S = 8.0


def transition_defense(match, config=None) -> dict:
    """Átmenet-védekezés: a labdavesztés utáni gyors kapott gólok.

    A modern kézilabda egyik kulcsa a VISSZAZÁRÁS: egy labdaeladás után
    az ellenfél gyors indítással könnyű gólt szerezhet. Csapatonként
    megszámoljuk, hány labdaeladást követett az ellenfél gólja
    TRANSITION_WINDOW_S-en belül — ez a rossz visszazárás mérőszáma.

    Visszatérés csapatonként (a labdát VESZTŐ csapat szemszögéből):
    {"turnovers", "transition_goals_against", "pct"} — pct: a
    labdaeladások hány százaléka végződött gyors kapott góllal."""
    from ..models.tracking import Team
    from .event_detection import EventType, detect_events

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = round(TRANSITION_WINDOW_S * fps)

    events = detect_events(match, config)
    goals = [(e.t, e.team) for e in events if e.type == EventType.GOAL]
    out = {side: {"turnovers": 0, "transition_goals_against": 0, "pct": 0.0}
           for side in ("home", "away")}

    for e in events:
        if e.type != EventType.TURNOVER:
            continue
        loser = e.team
        rec = out[loser.value]
        rec["turnovers"] += 1
        # Az ELLENFÉL gólja a labdaeladás utáni ablakban?
        if any(e.t < gt <= e.t + win and gteam != loser for (gt, gteam) in goals):
            rec["transition_goals_against"] += 1

    for rec in out.values():
        if rec["turnovers"]:
            rec["pct"] = round(
                100.0 * rec["transition_goals_against"] / rec["turnovers"], 1)
    return out


def turnover_zones(match, config=None) -> dict:
    """Hol veszíti el a labdát egy csapat — pálya-harmad szerint.

    Minden labdaeladást a labda helyéből a TÁMADÁSI irány szerinti
    harmadhoz sorolunk: "saját" (védekező harmad), "közép" (középpálya),
    "támadó" (befejező harmad). A támadó harmadban elvesztett labda a
    legveszélyesebb (üresen hagyja a védelmet a gyors indításnak).

    Visszatérés csapatonként: {"total", "zones": {zóna: db},
    "front_pct"} — a front_pct a TÁMADÓ harmadban elvesztett labdák
    aránya (magas érték = kockázatos befejezés / könnyű kontra ellen)."""
    from ..models.tracking import Team
    from .event_detection import EventType, detect_events
    from .tactics import COURT_LENGTH_M

    config = config or TacticsConfig()
    length = COURT_LENGTH_M
    frames_by_t = {f.t: f for f in match.frames}
    out = {side: {"total": 0, "zones": {}, "front_pct": 0.0}
           for side in ("home", "away")}

    for e in detect_events(match, config):
        if e.type != EventType.TURNOVER:
            continue
        frame = frames_by_t.get(e.t)
        if frame is None or frame.ball is None:
            continue
        goal_x = config.attacks_toward_x(e.team)
        # A labda-pozíció a megtámadott kaputól mért, hossz-normált táv:
        # 0 = saját kapu környéke, 1 = a megtámadott kapu.
        frac = 1.0 - abs(frame.ball.x - goal_x) / length
        zone = ("saját" if frac < 1 / 3 else
                "közép" if frac < 2 / 3 else "támadó")
        rec = out[e.team.value]
        rec["total"] += 1
        rec["zones"][zone] = rec["zones"].get(zone, 0) + 1

    for rec in out.values():
        if rec["total"]:
            rec["front_pct"] = round(
                100.0 * rec["zones"].get("támadó", 0) / rec["total"], 1)
    return out


def turnover_players(match, config=None) -> dict:
    """Labdaeladók: KI veszíti el a legtöbbször a labdát — a labdabiztonság
    egyéni mutatója.

    A labdaeladás-eseményekhez (detect_events, ahol a lövés-környéki
    eladások már ki vannak szűrve) a labdát ELVESZTŐ játékost írjuk jóvá.
    A kapust kihagyjuk (a kapus "eladása" jellemzően lövés/kidobás). A
    turnover_zones (HOL) és a ball_winners (KI szerez) párja: ez a KI veszít.

    Visszatérés csapatonként:
      {"total", "players": [{"player_id", "jersey", "losses"}], "ts":
       [{"t", "player_id"}]} — players a labdaeladások szerint csökkenően;
    ts a pillanatok (klip-exporthoz)."""
    from .event_detection import EventType, detect_events

    config = config or TacticsConfig()
    jersey: dict[int, int] = {}
    gk_tracks: set = set()
    for f in match.frames:
        for p in f.players:
            if p.jersey_number is not None and p.track_id not in jersey:
                jersey[p.track_id] = p.jersey_number
            if p.role == "kapus":
                gk_tracks.add(p.track_id)

    tally: dict[str, dict[int, int]] = {"home": {}, "away": {}}
    ts: dict[str, list] = {"home": [], "away": []}
    for e in detect_events(match, config):
        if e.type != EventType.TURNOVER or e.player_id is None:
            continue
        if e.player_id in gk_tracks:
            continue
        side = e.team.value
        tally[side][e.player_id] = tally[side].get(e.player_id, 0) + 1
        ts[side].append({"t": e.t, "player_id": e.player_id})

    out = {}
    for side in ("home", "away"):
        players = [{"player_id": tid, "jersey": jersey.get(tid),
                    "losses": n}
                   for tid, n in sorted(tally[side].items(),
                                        key=lambda kv: -kv[1])]
        out[side] = {"total": sum(tally[side].values()),
                     "players": players, "ts": ts[side]}
    return out


# Blokk-felismerés: lövés-szerű labdarepülés (gyors, kapu felé), ami a
# mezőnyben egy védőnél hirtelen visszafordul — mielőtt a kapu-zónába érne
# (ott már kapus-védés lenne). A lövés-detektor ezt nem látja, mert a
# labda nem közelíti meg a kaput.
BLOCK_SPEED_MS = 8.0          # lövés-szerű tempó (mint a lövés-detektorban)
BLOCK_MAX_GOAL_DIST_M = 14.0  # a repülés a kapu előtti térben történik
BLOCK_MIN_GOAL_DIST_M = 5.5   # a visszafordulás nem a kapusnál van
BLOCK_RADIUS_M = 1.5          # a blokkoló legfeljebb ennyire a labdától
BLOCK_COOLDOWN = 12           # két blokk közt legalább ennyi kocka


def detect_blocks(match, config=None) -> dict:
    """Blokkolt lövések: a mezőnyvédőn elakadó lövés felismerése.

    Mintázat: a labda lövés-tempóban (BLOCK_SPEED_MS) repül a kapu felé a
    kapu előtti térben, majd a következő kockán a kapu felőli irányba
    fordul vissza — és a fordulópontnál egy VÉDŐ (nem kapus) áll a labda
    mellett. Ezt a védekező csapat blokkjának számoljuk, a blokkolóval.

    Visszatérés: {"home"/"away": {"blocks", "blockers":
    [{"player_id","blocks"}], "events": [{"t","player_id"}]}} — a kulcs
    a BLOKKOLÓ (védekező) csapat; az events a klip-exporthoz ad időt.
    """
    from ..models.tracking import Team
    from .event_detection import _attacking_team_for_goal
    from .tactics import COURT_LENGTH_M

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    frames = match.frames
    out = {side: {"blocks": 0, "blockers": {}, "events": []}
           for side in ("home", "away")}
    last_block_t = -10**9

    for i in range(1, len(frames) - 1):
        f0, f1, f2 = frames[i - 1], frames[i], frames[i + 1]
        if any(fr.ball is None for fr in (f0, f1, f2)):
            continue
        vx_in = (f1.ball.x - f0.ball.x) * fps
        vx_out = (f2.ball.x - f1.ball.x) * fps
        for goal_x in (0.0, COURT_LENGTH_M):
            toward_in = (vx_in < -BLOCK_SPEED_MS if goal_x == 0.0
                         else vx_in > BLOCK_SPEED_MS)
            reversed_out = (vx_out > 0 if goal_x == 0.0 else vx_out < 0)
            dist = abs(f1.ball.x - goal_x)
            if not (toward_in and reversed_out
                    and BLOCK_MIN_GOAL_DIST_M <= dist <= BLOCK_MAX_GOAL_DIST_M
                    and f1.t - last_block_t >= BLOCK_COOLDOWN):
                continue
            attacking = _attacking_team_for_goal(goal_x, config)
            defending = Team.AWAY if attacking == Team.HOME else Team.HOME
            best = None
            for p in f1.players:
                if p.team != defending or p.role == "kapus":
                    continue
                d = ((p.x - f1.ball.x) ** 2 + (p.y - f1.ball.y) ** 2) ** 0.5
                if d <= BLOCK_RADIUS_M and (best is None or d < best[1]):
                    best = (p.track_id, d)
            if best is not None:
                rec = out[defending.value]
                rec["blocks"] += 1
                rec["blockers"][best[0]] = rec["blockers"].get(best[0], 0) + 1
                rec["events"].append({"t": f1.t, "player_id": best[0]})
                last_block_t = f1.t

    for rec in out.values():
        rec["blockers"] = [{"player_id": pid, "blocks": n}
                           for pid, n in sorted(rec["blockers"].items(),
                                                key=lambda kv: -kv[1])]
    return out


# Falba lövés: ennyi blokkolt lövés kell az ítélethez, és ekkora arány
# számít "falba lövő" (rosszul előkészített lövésű) támadójátéknak.
BLOCKED_MIN = 4
BLOCKED_HIGH_PCT = 20.0


def blocked_shot_rate(match, config=None) -> dict:
    """Falba lövés (támadó-oldali blokk-arány): a csapat lövés-kísérleteinek
    mekkora hányada akad el az ellenfél mezőnyvédőjén.

    A blokk a VÉDŐ oldalán erény (detect_blocks) — ugyanez a támadó oldalán
    tünet: a sok blokkolt lövés rosszul előkészített, kényszerű lövéseket
    jelez (nincs elzárás, nincs lövőcsel, rossz szögből lőnek a falba).

    Visszatérés csapatonként (a TÁMADÓ csapaté):
      {"blocked", "shots", "attempts", "blocked_pct"} — blocked az ellenfél
    blokkjai ellenük, shots a kapu felé elmenő (felismert) lövéseik,
    attempts a kettő összege; blocked_pct None, ha blocked < BLOCKED_MIN.
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    blocks = detect_blocks(match, config)
    shots = {"home": 0, "away": 0}
    for e in detect_shots(match, config):
        if e.type in (EventType.SHOT, EventType.GOAL):
            shots[e.team.value] += 1

    out: dict = {}
    for s in ("home", "away"):
        other = "away" if s == "home" else "home"
        blocked = blocks[other]["blocks"]  # az ellenfél blokkjai = ellenünk
        attempts = shots[s] + blocked
        out[s] = {
            "blocked": blocked,
            "shots": shots[s],
            "attempts": attempts,
            "blocked_pct": (round(100.0 * blocked / attempts, 1)
                            if blocked >= BLOCKED_MIN and attempts > 0
                            else None),
        }
    return out


# Labdabiztonság-esés: félidőnként ennyi mért birtoklás-idő kell, és ekkora
# (eladás/perc) romlás számít fáradás-/koncentráció-jelnek a 2. félidőre.
TURNOVER_FADE_MIN_POSS_S = 120.0
TURNOVER_FADE_RISE_PER_MIN = 0.2


def turnover_fade(match, config=None) -> dict:
    """Labdabiztonság-esés: az eladás-ütem változása az 1. és a 2. félidő
    között — a koncentráció/fáradás harmadik jele.

    Félidőnként a labdaeladásokat a SAJÁT birtoklás-időre vetítjük
    (eladás/perc), így az ütem-különbség nem torzít. Ha a 2. félidei ütem
    érdemben (TURNOVER_FADE_RISE_PER_MIN) magasabb, a csapat keze a meccs
    végére "kienged" — a hajrában a labdabiztonsága törékeny; ha javul, a
    hajrában is rendezett marad. A lövőerő-esés és a védekezés-fellazulás
    mellett a fáradás-kép harmadik pillére.

    Visszatérés csapatonként:
      {"fh_to", "fh_poss_s", "sh_to", "sh_poss_s", "fh_per_min",
       "sh_per_min", "rise_per_min"} — félidőnkénti eladások és mért
    birtoklás-idő; a per-perc ütemek és a változás None, ha nincs
    félidő-jel vagy kevés a mért birtoklás (TURNOVER_FADE_MIN_POSS_S).
    """
    from .event_detection import EventType, detect_events
    from .halftime import detect_halftime
    from .tactics import possession_team

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    empty = {"fh_to": 0, "fh_poss_s": 0.0, "sh_to": 0, "sh_poss_s": 0.0,
             "fh_per_min": None, "sh_per_min": None, "rise_per_min": None}
    out = {"home": dict(empty), "away": dict(empty)}
    ht = detect_halftime(match)
    if ht is None:
        return out
    for f in match.frames:
        team = possession_team(f, config)
        if team is None:
            continue
        key = "fh_poss_s" if f.t <= ht else "sh_poss_s"
        out[team.value][key] += 1.0 / fps
    for e in detect_events(match, config):
        if e.type != EventType.TURNOVER:
            continue
        key = "fh_to" if e.t <= ht else "sh_to"
        out[e.team.value][key] += 1
    for s in ("home", "away"):
        rec = out[s]
        rec["fh_poss_s"] = round(rec["fh_poss_s"], 1)
        rec["sh_poss_s"] = round(rec["sh_poss_s"], 1)
        if rec["fh_poss_s"] >= TURNOVER_FADE_MIN_POSS_S \
                and rec["sh_poss_s"] >= TURNOVER_FADE_MIN_POSS_S:
            rec["fh_per_min"] = round(60.0 * rec["fh_to"]
                                      / rec["fh_poss_s"], 2)
            rec["sh_per_min"] = round(60.0 * rec["sh_to"]
                                      / rec["sh_poss_s"], 2)
            rec["rise_per_min"] = round(rec["sh_per_min"]
                                        - rec["fh_per_min"], 2)
    return out


# Védekezés-fellazulás: félidőnként ennyi mért kocka kell, és ekkora
# (méteres) lazulás számít fáradás-jelnek a 2. félidőre.
PRESSURE_FADE_MIN_FRAMES = 100
PRESSURE_FADE_LOOSEN_M = 0.5


def pressure_fade(match, config=None) -> dict:
    """Védekezés-fellazulás: a védekezési nyomás változása az 1. és a 2.
    félidő között — a fal fáradásának jele.

    A védekezési nyomást (a labdás támadó és a legközelebbi védő átlagos
    távolsága) a felismert félidő mentén két részre bontva mérjük. Ha a 2.
    félidei átlag érdemben (PRESSURE_FADE_LOOSEN_M) nagyobb, a fal
    fellazul a meccs végére — a hajrában több lesz a szabad lövő; ha
    szorosabbra vált, a csapat a hajrában húzza meg a védekezést. A
    lövőerő-esés (shot_speed_fade) védekezés-oldali párja.

    Visszatérés csapatonként (a védekező csapaté):
      {"fh_m", "fh_frames", "sh_m", "sh_frames", "loosen_m"} — az 1./2.
    félidei átlagnyomás és kockaszám; loosen_m a változás (pozitív =
    lazul), None, ha nincs félidő-jel vagy kevés a mért kocka.
    """
    from ..models.tracking import Match as _M
    from .halftime import detect_halftime

    config = config or TacticsConfig()
    empty = {"fh_m": None, "fh_frames": 0, "sh_m": None, "sh_frames": 0,
             "loosen_m": None}
    out = {"home": dict(empty), "away": dict(empty)}
    ht = detect_halftime(match)
    if ht is None:
        return out
    fh = defensive_pressure(
        _M(match.meta, [f for f in match.frames if f.t <= ht]), config)
    sh = defensive_pressure(
        _M(match.meta, [f for f in match.frames if f.t > ht]), config)
    for s in ("home", "away"):
        rec = out[s]
        rec["fh_m"] = fh[s]["avg_pressure_m"]
        rec["fh_frames"] = fh[s]["frames"]
        rec["sh_m"] = sh[s]["avg_pressure_m"]
        rec["sh_frames"] = sh[s]["frames"]
        if (rec["fh_m"] is not None and rec["sh_m"] is not None
                and rec["fh_frames"] >= PRESSURE_FADE_MIN_FRAMES
                and rec["sh_frames"] >= PRESSURE_FADE_MIN_FRAMES):
            rec["loosen_m"] = round(rec["sh_m"] - rec["fh_m"], 2)
    return out


def defensive_pressure(match, config=None) -> dict:
    """Védekezési nyomás: mennyire szorosan védekezik egy csapat.

    A védekezés minőségének egyik jele, hogy MILYEN KÖZEL van a labdás
    támadóhoz a legközelebbi védő. Kockánként (amikor egy csapat védekezik
    — az ellenfél birtokol) megkeressük a labdabirtokost és a legközelebbi
    VÉDŐ mezőnyjátékost, és átlagoljuk a távolságukat. Alacsonyabb átlag =
    szorosabb, agresszívabb védekezés.

    Visszatérés csapatonként (a VÉDEKEZŐ csapaté):
    {"avg_pressure_m", "frames"} — avg_pressure_m None, ha nincs mérhető
    szakasz."""
    import math

    from ..models.tracking import Team
    from .decisions import ball_holder
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    acc = {Team.HOME: [0.0, 0], Team.AWAY: [0.0, 0]}
    for f in match.frames:
        holder = ball_holder(f, config)
        if holder is None:
            continue
        defender_team = Team.AWAY if holder.team == Team.HOME else Team.HOME
        dists = [math.hypot(p.x - holder.x, p.y - holder.y)
                 for p in f.players
                 if p.team == defender_team and p.role != "kapus"]
        if dists:
            acc[defender_team][0] += min(dists)
            acc[defender_team][1] += 1
    out = {}
    for team in (Team.HOME, Team.AWAY):
        total, n = acc[team]
        out[team.value] = {
            "avg_pressure_m": round(total / n, 2) if n else None,
            "frames": n,
        }
    return out


# Védekezési vonal magassága: efölött felfutó/agresszív (3-2-1 jelleg), ez
# alatt mély/passzív (6-0 jelleg) fal; ennyi mért kocka kell az ítélethez.
DEF_LINE_HIGH_M = 8.5
DEF_LINE_DEEP_M = 6.5
DEF_LINE_MIN_FRAMES = 100


def defensive_line_height(match, config=None) -> dict:
    """Védekezési vonal magassága: milyen mélyen vagy magasan áll a fal.

    Amikor a csapat védekezik (az ellenfél a csapat saját térfelén
    birtokol), a védő mezőnyjátékosok átlagos távolsága a SAJÁT
    gólvonaltól — kicsi = mély, passzív fal (6-0 jelleg, a 6-os környékén),
    nagy = felfutó, agresszív védekezés (3-2-1 jelleg, kilépő védőkkel). Ez
    más, mint a védekezési NYOMÁS (az a labdástól mért távolság): itt a fal
    HELYE a saját kapuhoz képest a kérdés.

    Visszatérés csapatonként (a védekező csapaté):
      {"avg_height_m", "frames", "style"} — style: "mély (passzív)" /
    "felfutó (agresszív)" / "kiegyensúlyozott"; avg_height_m None, ha nincs
    elég mért kocka (DEF_LINE_MIN_FRAMES).
    """
    from ..models.tracking import Team
    from .decisions import ball_holder
    from .tactics import COURT_LENGTH_M, TacticsConfig

    config = config or TacticsConfig()
    half = COURT_LENGTH_M / 2.0
    acc = {Team.HOME: [0.0, 0], Team.AWAY: [0.0, 0]}
    for f in match.frames:
        holder = ball_holder(f, config)
        if holder is None:
            continue
        deff = Team.AWAY if holder.team == Team.HOME else Team.HOME
        own_x = config.own_goal_x(deff)
        # Csak felállt védekezés: a labdás a védekező csapat térfelén van.
        if abs(holder.x - own_x) > half:
            continue
        depths = [abs(p.x - own_x) for p in f.players
                  if p.team == deff and p.role != "kapus"
                  and abs(p.x - own_x) <= half]
        if depths:
            acc[deff][0] += sum(depths) / len(depths)
            acc[deff][1] += 1

    out = {}
    for team in (Team.HOME, Team.AWAY):
        total, n = acc[team]
        if n < DEF_LINE_MIN_FRAMES:
            out[team.value] = {"avg_height_m": None, "frames": n,
                               "style": None}
            continue
        avg = round(total / n, 2)
        style = ("felfutó (agresszív)" if avg >= DEF_LINE_HIGH_M
                 else "mély (passzív)" if avg <= DEF_LINE_DEEP_M
                 else "kiegyensúlyozott")
        out[team.value] = {"avg_height_m": avg, "frames": n, "style": style}
    return out


# Védelmi tömörség: ennyi mért kocka és ennyi mért védő kell; a fal e alatt
# tömör (a szélek nyílnak), e fölött széthúzott (a közép nyílik).
DEF_WIDTH_MIN_FRAMES = 100
DEF_WIDTH_MIN_DEFENDERS = 4
DEF_WIDTH_NARROW_M = 11.0
DEF_WIDTH_WIDE_M = 15.0


def defensive_width(match, config=None) -> dict:
    """Védelmi tömörség (fal-szélesség): milyen szélesen áll a védőfal.

    Felállt védekezésnél (a labdás a védekező csapat térfelén) a védő
    mezőnyjátékosok KERESZTIRÁNYÚ (y) terjedelmét mérjük (max − min).
    Tömör (keskeny) fal a közepet zárja — ellene a szélső játék és a
    beadás nyílik; széthúzott (széles) fal a szélekre vigyáz — ellene a
    betörés és a beálló-játék a rés. A vonal-MAGASSÁG (mély/felfutó)
    mellett ez a fal második térbeli jellemzője.

    Visszatérés csapatonként (a védekező csapaté):
      {"avg_width_m", "frames", "style"} — style: "tömör (szélek nyitva)" /
    "széthúzott (közép nyitva)" / "kiegyensúlyozott"; avg_width_m None,
    ha nincs elég mért kocka (DEF_WIDTH_MIN_FRAMES).
    """
    from ..models.tracking import Team
    from .decisions import ball_holder
    from .tactics import COURT_LENGTH_M, TacticsConfig

    config = config or TacticsConfig()
    half = COURT_LENGTH_M / 2.0
    acc = {Team.HOME: [0.0, 0], Team.AWAY: [0.0, 0]}
    for f in match.frames:
        holder = ball_holder(f, config)
        if holder is None:
            continue
        deff = Team.AWAY if holder.team == Team.HOME else Team.HOME
        own_x = config.own_goal_x(deff)
        # Csak felállt védekezés: a labdás a védekező csapat térfelén van.
        if abs(holder.x - own_x) > half:
            continue
        ys = [p.y for p in f.players
              if p.team == deff and p.role != "kapus"
              and abs(p.x - own_x) <= half]
        if len(ys) >= DEF_WIDTH_MIN_DEFENDERS:
            acc[deff][0] += max(ys) - min(ys)
            acc[deff][1] += 1

    out = {}
    for team in (Team.HOME, Team.AWAY):
        total, n = acc[team]
        if n < DEF_WIDTH_MIN_FRAMES:
            out[team.value] = {"avg_width_m": None, "frames": n,
                               "style": None}
            continue
        avg = round(total / n, 2)
        style = ("széthúzott (közép nyitva)" if avg >= DEF_WIDTH_WIDE_M
                 else "tömör (szélek nyitva)" if avg <= DEF_WIDTH_NARROW_M
                 else "kiegyensúlyozott")
        out[team.value] = {"avg_width_m": avg, "frames": n, "style": style}
    return out


# Visszarendeződés: ennyi védőnek kell a saját térfélen lennie, hogy a
# védelmet "visszaértnek" tekintsük; a mérést ennyi mp-nél levágjuk.
RECOVERY_DEFENDERS = 4
RECOVERY_SLOW_S = 5.0
RECOVERY_MAX_S = 15.0


def transition_recovery(match, config=None) -> dict:
    """Visszarendeződés-idő: labdavesztés után mennyi idő alatt ér
    vissza legalább RECOVERY_DEFENDERS védő a saját térfélre.

    A kontra-védekezés nyers száma: a lassú visszarendeződés ellen a
    gyors indítás, a gyors ellen a felállt támadás a recept.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal):
      {"transitions", "sum_s", "avg_s", "slow"} — avg_s None, ha nincs
    mérhető átmenet; slow: az RECOVERY_SLOW_S-nél lassabbak száma.
    """
    from ..models.tracking import Team
    from .setplays import segment_attacks
    from .tactics import COURT_LENGTH_M, TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    frames = match.frames
    idx_of = {f.t: i for i, f in enumerate(frames)}
    out = {side: {"transitions": 0, "sum_s": 0.0, "slow": 0}
           for side in ("home", "away")}

    for seq in segment_attacks(match, config):
        att = seq.team
        deff = Team.AWAY if att == Team.HOME else Team.HOME
        # A védő a támadó céltáblájának térfelét védi.
        goal_x = config.attacks_toward_x(att)
        own_half_near = goal_x >= COURT_LENGTH_M / 2.0
        i0 = idx_of.get(seq.start_t)
        if i0 is None:
            continue
        recovered = None
        for i in range(i0, min(len(frames),
                               i0 + int(RECOVERY_MAX_S * fps))):
            fr = frames[i]
            backs = 0
            seen = 0
            for p_ in fr.players:
                if p_.team != deff or p_.role == "kapus":
                    continue
                seen += 1
                in_own = (p_.x >= COURT_LENGTH_M / 2.0
                          if own_half_near
                          else p_.x <= COURT_LENGTH_M / 2.0)
                if in_own:
                    backs += 1
            if seen < RECOVERY_DEFENDERS:
                continue  # kevés látott védő — nem mérhető kocka
            if backs >= RECOVERY_DEFENDERS:
                recovered = fr.t
                break
        if recovered is None:
            continue
        dt = (recovered - seq.start_t) / fps
        rec = out[deff.value]
        rec["transitions"] += 1
        rec["sum_s"] += dt
        if dt >= RECOVERY_SLOW_S:
            rec["slow"] += 1
    for rec in out.values():
        rec["avg_s"] = (round(rec["sum_s"] / rec["transitions"], 1)
                        if rec["transitions"] else None)
        rec["sum_s"] = round(rec["sum_s"], 1)
    return out


# Őrzési párok: kockánként a labdás csapat mezőnyjátékosaihoz rendeljük a
# legközelebbi védőt; MARK_MAX_DIST_M-en túl nem számít őrzésnek, a páros
# pedig csak MARK_MIN_FRAMES kockától kerül a listába (1 mp @ 25 fps).
MARK_MAX_DIST_M = 3.5
MARK_MIN_FRAMES = 25
MARK_LOOSE_M = 2.5
MARK_TIGHT_M = 1.5


def marking_pairs(match, config=None, until_t=None) -> dict:
    """Őrzési párok: ki kit fogott a védekezésben.

    Kockánként (amikor az ellenfélnél a labda) minden TÁMADÓ mezőny-
    játékoshoz megkeressük a legközelebbi VÉDŐ mezőnyjátékost; ha
    MARK_MAX_DIST_M-en belül van, a párost számoljuk és a távolságot
    összegezzük. Védőnként a leggyakoribb "őrzöttje" adja a párt — így
    látszik, ki kit fogott, és milyen szorosan.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal):
      {"pairs": [{"defender", "defender_jersey", "attacker",
                  "attacker_jersey", "frames", "share_pct",
                  "avg_dist_m"}], "loosest": pár|None,
       "defenders": [{"defender", "defender_jersey", "frames",
                      "dist_sum", "avg_dist_m"}]}
    — share_pct: a védő őrzés-kockáinak hány %-a jutott erre a támadóra;
    loosest: a legnagyobb átlagtávú pár (MARK_LOOSE_M felett laza őrzés);
    defenders: védőnkénti ÖSSZES őrzés-kocka és táv-összeg (bármelyik
    támadóval) — a felderítés ebből összegez pontosan meccsek között.
    until_t: ha adott, csak az addigi kockák számítanak (élő/félidei
    kép — jövőbe nézés nélkül).
    """
    import math

    from ..models.tracking import Team
    from .decisions import ball_holder
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    jersey: dict[int, int] = {}
    # (védő track, támadó track) → [kockák, táv-összeg], védőnként összes.
    acc: dict[str, dict[tuple[int, int], list[float]]] = {
        "home": {}, "away": {}}
    def_frames: dict[str, dict[int, int]] = {"home": {}, "away": {}}
    def_dist: dict[str, dict[int, float]] = {"home": {}, "away": {}}

    for f in match.frames:
        if until_t is not None and f.t > until_t:
            break
        for p in f.players:
            if p.jersey_number is not None and p.track_id not in jersey:
                jersey[p.track_id] = p.jersey_number
        holder = ball_holder(f, config)
        if holder is None:
            continue
        def_team = Team.AWAY if holder.team == Team.HOME else Team.HOME
        attackers = [p for p in f.players
                     if p.team == holder.team and p.role != "kapus"]
        defenders = [p for p in f.players
                     if p.team == def_team and p.role != "kapus"]
        if not attackers or not defenders:
            continue
        side = def_team.value
        for a in attackers:
            best = min(defenders,
                       key=lambda d: math.hypot(d.x - a.x, d.y - a.y))
            dist = math.hypot(best.x - a.x, best.y - a.y)
            if dist > MARK_MAX_DIST_M:
                continue
            rec = acc[side].setdefault((best.track_id, a.track_id),
                                       [0, 0.0])
            rec[0] += 1
            rec[1] += dist
            def_frames[side][best.track_id] = (
                def_frames[side].get(best.track_id, 0) + 1)
            def_dist[side][best.track_id] = (
                def_dist[side].get(best.track_id, 0.0) + dist)

    out = {}
    for side in ("home", "away"):
        # Védőnként a leggyakoribb őrzöttje adja a párt.
        best_of: dict[int, tuple[tuple[int, int], list[float]]] = {}
        for key, rec in acc[side].items():
            cur = best_of.get(key[0])
            if cur is None or rec[0] > cur[1][0]:
                best_of[key[0]] = (key, rec)
        pairs = []
        for dt, (key, rec) in best_of.items():
            if rec[0] < MARK_MIN_FRAMES:
                continue
            total = def_frames[side].get(dt, 0)
            pairs.append({
                "defender": dt,
                "defender_jersey": jersey.get(dt),
                "attacker": key[1],
                "attacker_jersey": jersey.get(key[1]),
                "frames": rec[0],
                "share_pct": round(100.0 * rec[0] / total, 1)
                if total else 0.0,
                "avg_dist_m": round(rec[1] / rec[0], 2),
            })
        pairs.sort(key=lambda p_: -p_["frames"])
        defenders = [
            {"defender": dt,
             "defender_jersey": jersey.get(dt),
             "frames": n,
             "dist_sum": round(def_dist[side][dt], 2),
             "avg_dist_m": round(def_dist[side][dt] / n, 2)}
            for dt, n in sorted(def_frames[side].items(),
                                key=lambda kv: -kv[1])
            if n >= MARK_MIN_FRAMES]
        out[side] = {
            "pairs": pairs,
            "loosest": (max(pairs, key=lambda p_: p_["avg_dist_m"])
                        if pairs else None),
            "defenders": defenders,
        }
    return out


# Betörés-folyosók: a labdás támadó ennyire megközelíti a kaput, az
# számít betörésnek; a sávhatárok a pálya-szélesség arányában (a támadó
# szemszögéből nézve, oldal-normalizálva).
BREAK_IN_DIST_M = 9.0
_LANE_FRACS = (0.28, 0.42, 0.58, 0.72)
_LANE_LABELS = ("bal szél", "bal átlövő", "közép",
                "jobb átlövő", "jobb szél")


def breakthrough_lanes(match, config=None) -> dict:
    """Betörés-folyosók: támadásonként hol lép be a labdás ember a
    kapu 9 m-es körzetébe (a támadó szemszögéből vett sávokban).

    Védekezés-oldali olvasata a fontos: az ELLENFÉL betörési képéből
    látszik, melyik sávban lyukas a fal. A gól-párosítás a támadás
    + rövid rátartás alatti első saját gól (mint a támadás-rétegeknél).

    Visszatérés a TÁMADÓ csapat szerint:
      {"home"/"away": {"entries", "lanes": {sáv: {"entries", "goals"}},
                       "top_lane": sáv|None,
                       "entries_ts": [{"t", "lane"}]}}
    — entries_ts: a belépési pillanatok (klip-exporthoz).
    """
    import math

    from ..models.tracking import Team
    from .decisions import ball_holder
    from .event_detection import EventType, detect_shots
    from .calibration import COURT_WIDTH_M
    from .setplays import segment_attacks
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    tail = round(2.0 * fps)
    shots = [(e.t, e.team.value, e.type == EventType.GOAL)
             for e in detect_shots(match, config)
             if e.type in (EventType.SHOT, EventType.GOAL)]

    out = {side: {"entries": 0, "lanes": {}, "top_lane": None,
                  "entries_ts": []}
           for side in ("home", "away")}
    for seq in segment_attacks(match, config):
        side = seq.team.value
        goal_x = config.attacks_toward_x(seq.team)
        entry_y = entry_t = None
        for fr in seq.frames:
            h = ball_holder(fr, config)
            if h is None:
                continue
            gy = 10.0  # kapu-közép y (20 m-es pálya)
            if math.hypot(h.x - goal_x, h.y - gy) <= BREAK_IN_DIST_M:
                # A támadó szemszögéből: a -x kapunál tükrözzük az y-t.
                entry_y = (h.y if goal_x > 0
                           else COURT_WIDTH_M - h.y)
                entry_t = fr.t
                break
        if entry_y is None:
            continue
        frac = entry_y / COURT_WIDTH_M
        lane = _LANE_LABELS[
            sum(1 for b in _LANE_FRACS if frac >= b)]
        rec = out[side]
        rec["entries"] += 1
        rec["entries_ts"].append({"t": entry_t, "lane": lane})
        lrec = rec["lanes"].setdefault(lane, {"entries": 0, "goals": 0})
        lrec["entries"] += 1
        if next((True for (t, tm, g) in shots
                 if tm == side and g
                 and seq.start_t <= t <= seq.end_t + tail), False):
            lrec["goals"] += 1
    for rec in out.values():
        if rec["lanes"]:
            rec["top_lane"] = max(
                rec["lanes"].items(),
                key=lambda kv: (kv[1]["entries"], kv[1]["goals"]))[0]
            rec["lanes"] = dict(sorted(
                rec["lanes"].items(),
                key=lambda kv: -kv[1]["entries"]))
    return out


# Szerzés-magasság: ennyi szerzés kell az ítélethez; e fölötti elöl-arány
# jelenti, hogy a letámadás élő fegyver.
STEAL_HEIGHT_MIN = 4
STEAL_HIGH_PCT = 35.0


def steal_height(match, config=None) -> dict:
    """Labdaszerzés-magasság (letámadás-jel): HOL szerez labdát a csapat.

    Minden labdaszerzésnél (az ellenfél labdaeladása) megnézzük, a pálya
    melyik felén történt a SZERZŐ csapat szemszögéből: az ELÖL (a saját
    támadó térfélen, az ellenfél építkezése közben) szerzett labda a
    letámadás terméke — és azonnali helyzetet ér; a hátul szerzett a
    felállt védekezésé. Ez kiegészíti a ball_winners-t (KI szerez) és a
    trans_steals-t (mire váltják): itt a HOL a kérdés.

    Visszatérés csapatonként (a SZERZŐ oldal):
      {"steals", "high_steals", "high_pct"} — összes mért szerzés, ebből
    az elöl történtek, és az arány (%). high_pct None, ha steals <
    STEAL_HEIGHT_MIN.
    """
    from .event_detection import EventType, detect_events
    from .tactics import COURT_LENGTH_M

    config = config or TacticsConfig()
    by_t = {f.t: f for f in match.frames}
    mid = COURT_LENGTH_M / 2.0
    acc = {"home": [0, 0], "away": [0, 0]}  # szerzés, elöl-szerzés
    for e in detect_events(match, config):
        if e.type != EventType.TURNOVER:
            continue
        gaining = Team.AWAY if e.team == Team.HOME else Team.HOME
        f = by_t.get(e.t)
        if f is None or f.ball is None:
            continue
        rec = acc[gaining.value]
        rec[0] += 1
        goal_x = config.attacks_toward_x(gaining)
        in_front = (f.ball.x > mid) if goal_x > mid else (f.ball.x < mid)
        if in_front:
            rec[1] += 1

    out: dict = {}
    for s in ("home", "away"):
        n, high = acc[s]
        out[s] = {
            "steals": n,
            "high_steals": high,
            "high_pct": (round(100.0 * high / n, 1)
                         if n >= STEAL_HEIGHT_MIN else None),
        }
    return out


def ball_winners(match, config=None) -> dict:
    """Labdaszerzők: birtokos-váltásnál (csapatváltás) az ÚJ birtokos
    kapja a labdaszerzés-jóváírást — ki a védekezés motorja.

    A blokk és az őrzési párok mellé ez a harmadik egyéni védekezés-
    mutató: a felderítésben ("vele szemben óvatos passz"), a játékos-
    lapon és az összefoglalóban is megjelenik.

    Visszatérés csapatonként (a SZERZŐ oldal):
      {"total", "players": [{"player_id", "jersey", "steals"}],
       "ts": [{"t", "player_id"}]}
    — players a szerzések száma szerint csökkenően; ts a szerzés-
    pillanatok (klip-exporthoz).
    """
    from .decisions import ball_holder
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    jersey: dict[int, int] = {}
    tally: dict[str, dict[int, int]] = {"home": {}, "away": {}}
    ts: dict[str, list] = {"home": [], "away": []}
    prev = None
    for f in match.frames:
        for p in f.players:
            if p.jersey_number is not None and p.track_id not in jersey:
                jersey[p.track_id] = p.jersey_number
        holder = ball_holder(f, config)
        if (holder is not None and prev is not None
                and holder.team != prev.team
                and holder.role != "kapus"):
            side = holder.team.value
            tally[side][holder.track_id] = (
                tally[side].get(holder.track_id, 0) + 1)
            ts[side].append({"t": f.t, "player_id": holder.track_id})
        if holder is not None:
            prev = holder
    out = {}
    for side in ("home", "away"):
        players = [{"player_id": tid, "jersey": jersey.get(tid),
                    "steals": n}
                   for tid, n in sorted(tally[side].items(),
                                        key=lambda kv: -kv[1])]
        out[side] = {"total": sum(tally[side].values()),
                     "players": players, "ts": ts[side]}
    return out


# Eladás-időzítés: ennyi időzíthető eladástól ítélünk; a birtoklás
# első ennyi másodpercében elvesztett labda számít korainak, és e
# részarány felett "korai eladó" a csapat.
TO_TIMING_MIN = 6
TO_EARLY_S = 10.0
TO_EARLY_SHARE = 0.5


def turnover_timing(match, config=None) -> dict:
    """Eladás-időzítés: a birtoklás hányadik másodpercében jön az eladás.

    A labdaeladás helye (turnover_zones) mellett az IDEJE is beszédes:
    aki a birtoklás első másodperceiben — a kihozatal és a felállás
    közben — veszíti el a labdát, az a letámadásra érzékeny: ellene a
    magas, korai pressz azonnal termel. Aki későn, a kidolgozás végén
    ad el, annak a türelmes, felállt védekezés a méreg — ott a pressz
    fölösleges kockázat.

    Minden labdaeladásnál visszakeressük, mikor került a vesztes
    csapathoz a labda (az ellenfél utolsó birtoklása utáni első saját
    kocka), és a birtoklás-hossz alapján soroljuk koraira/későire.

    Visszatérés csapatonként: {"timed", "early", "early_pct"} —
    early_pct None, ha kevés (TO_TIMING_MIN alatti) az időzíthető
    eladás.
    """
    from ..models.tracking import Team
    from .event_detection import EventType, detect_events
    from .tactics import TacticsConfig, possession_team

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    frames = match.frames
    idx_of = {f.t: i for i, f in enumerate(frames)}
    poss = [possession_team(f, config) for f in frames]
    out = {side: {"timed": 0, "early": 0, "early_pct": None}
           for side in ("home", "away")}
    for e in detect_events(match, config):
        if e.type != EventType.TURNOVER:
            continue
        i0 = idx_of.get(e.t)
        if i0 is None or i0 == 0:
            continue
        team = e.team
        other = Team.AWAY if team == Team.HOME else Team.HOME
        start = None
        # Az esemény kockáján már az ellenfélé a labda — visszafelé
        # keressük a birtoklás elejét (a szabad-labdás kockákon átlépve).
        for j in range(i0 - 1, -1, -1):
            if poss[j] == other:
                break
            if poss[j] == team:
                start = j
        if start is None:
            continue
        rec = out[team.value]
        rec["timed"] += 1
        if (frames[i0].t - frames[start].t) / fps <= TO_EARLY_S:
            rec["early"] += 1
    for rec in out.values():
        if rec["timed"] >= TO_TIMING_MIN:
            rec["early_pct"] = round(100.0 * rec["early"] / rec["timed"], 1)
    return out


# Lepattanó-fal: ennyi ellenfél-lehetőségtől (nem gólos lövéstől)
# ítélünk, és e visszaadott arány felett áteresztő a fal a második
# hullámmal szemben.
SC_ALLOW_MIN = 6
SC_ALLOW_HIGH_PCT = 35.0


def second_chance_allowed(match, config=None) -> dict:
    """Lepattanó-fal: hány második rohamot enged a védekezés.

    A második roham réteg (second_chance) védő-oldali tükörképe: ott
    az látszik, ki harcolja vissza a saját lepattanóit — itt az, ki
    ENGEDI vissza az ellenfélét. A védett vagy mellé menő lövés után
    a labda a levegőben senkié: ha a fal nem zár (nincs box-out, a
    szélsők nem lépnek be), az ellenfél újra lő — a jól védett első
    hullám munkája vész kárba. Az áteresztő fal ellen a lepattanóra
    küldött plusz ember ingyen-lövéseket termel.

    Visszatérés csapatonként (a VÉDEKEZŐ csapat szemszögéből):
    {"opp_misses", "allowed", "allowed_goals", "allowed_pct"} —
    allowed_pct None, ha kevés (SC_ALLOW_MIN alatti) az ellenfél
    lepattanó-lehetősége.
    """
    from .attack_types import second_chance

    sc = second_chance(match, config)
    out: dict = {}
    for side, opp in (("home", "away"), ("away", "home")):
        p = sc[opp]
        rec = {"opp_misses": p["misses"],
               "allowed": p["second_chances"],
               "allowed_goals": p["second_goals"],
               "allowed_pct": None}
        if rec["opp_misses"] >= SC_ALLOW_MIN:
            rec["allowed_pct"] = round(
                100.0 * rec["allowed"] / rec["opp_misses"], 1)
        out[side] = rec
    return out


# Eladás-büntetés: ennyi eladástól ítélünk; az eladás utáni ennyi
# másodpercen belüli kapott gól számít büntetésnek, és e részarány
# felett drágák az eladások.
TO_PUNISH_MIN = 6
TO_PUNISH_QUICK_S = 30.0
TO_PUNISH_HIGH_PCT = 35.0


def turnover_punishment(match, config=None,
                        quick_s: float = TO_PUNISH_QUICK_S) -> dict:
    """Eladás-büntetés: az eladott labda fél percen belül gólba kerül-e.

    A kihagyott ziccer ára (miss_punishment) eladás-oldali párja: nem
    az a kérdés, MENNYI labdát ad el a csapat (turnover_zones), hanem
    hogy MENNYIBE kerül — akinek az eladásai rendre gyors kapott gólt
    érnek, annál az eladás utáni visszarendeződés (a váltás-sprint)
    hiányzik: az ellenfél olvasata, hogy minden szerzés után azonnal
    indulni kell, mert ez a csapat ilyenkor büntethető a legjobban.

    Visszatérés csapatonként: {"turnovers", "punished", "rate_pct"} —
    rate_pct None, ha kevés (TO_PUNISH_MIN alatti) az eladás.
    """
    from .event_detection import EventType, detect_events, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = round(quick_s * fps)
    goals = sorted((e.t, e.team.value) for e in detect_shots(match, config)
                   if e.type == EventType.GOAL)
    counts = {"home": {"turnovers": 0, "punished": 0},
              "away": {"turnovers": 0, "punished": 0}}
    for e in detect_events(match, config):
        if e.type != EventType.TURNOVER:
            continue
        side = e.team.value
        other = "away" if side == "home" else "home"
        counts[side]["turnovers"] += 1
        if any(gs == other and 0 <= gt - e.t <= win
               for (gt, gs) in goals):
            counts[side]["punished"] += 1
    out = {}
    for side in ("home", "away"):
        rec = counts[side]
        out[side] = {
            **rec,
            "rate_pct": (round(100.0 * rec["punished"] / rec["turnovers"],
                               1)
                         if rec["turnovers"] >= TO_PUNISH_MIN else None),
        }
    return out


# Engedett-oldal: a két szélső sávban ennyi kapott lövéstől ítélünk,
# és e többség felett átjárható az egyik fal-oldal.
CONCEDED_SIDE_MIN_SHOTS = 8
CONCEDED_SIDE_PCT = 65.0


def conceded_side_bias(match, config=None) -> dict:
    """Engedett-oldal: a fal melyik oldala felől jönnek a lövések.

    Az oldal-részrehajlás (attack_side_bias) védő-oldali tükörképe:
    ott az látszik, a támadó honnan lő szívesen — itt az, hogy a fal
    melyik oldala engedi át a lövéseket. Ha a kapott szélső-sávos
    lövések kétharmada ugyanarról az oldalról jön, az az oldal-védő
    (és a mögötte lévő segítő-csúszás) gyengéje: az ellenfél oda
    szervezheti a befejezést, a saját edzésnek pedig kész témája van.
    A "bal" itt a VÉDEKEZŐ fal bal oldala (a támadó jobb keze felől).

    Visszatérés csapatonként: {"left", "center", "right", "weak_side",
    "weak_pct"} — weak_side/weak_pct None, ha kevés (a két szélső
    sávban együtt CONCEDED_SIDE_MIN_SHOTS alatti) a kapott lövés,
    vagy nincs érdemi (CONCEDED_SIDE_PCT alatti) többség.
    """
    from .attack_types import attack_side_bias

    sb = attack_side_bias(match, config)
    out: dict = {}
    for side, opp in (("home", "away"), ("away", "home")):
        p = sb[opp]
        # A fal a támadóval szemben áll: a támadó balja a fal jobbja.
        rec = {"left": p["right"], "center": p["center"],
               "right": p["left"], "weak_side": None, "weak_pct": None}
        wings = rec["left"] + rec["right"]
        if wings >= CONCEDED_SIDE_MIN_SHOTS:
            pct = 100.0 * max(rec["left"], rec["right"]) / wings
            if pct >= CONCEDED_SIDE_PCT:
                rec["weak_side"] = ("bal" if rec["left"] >= rec["right"]
                                    else "jobb")
                rec["weak_pct"] = round(pct, 1)
        out[side] = rec
    return out


# Fal-rés: rendezett védekezésben ekkora szomszéd-távolság már rés; a
# saját kaputól ennyin belül állók számítanak falnak; ennyi mért
# falkockától ítélünk, és e részarány felett réses a fal.
WALL_GAP_M = 3.5
WALL_GAP_DEPTH_M = 12.0
WALL_GAP_MIN_FRAMES = 100
WALL_GAP_SHARE_PCT = 40.0


def wall_gaps(match, config=None) -> dict:
    """Fal-rés: mekkora réseket hagy a rendezett védőfal.

    A betörés-folyosó (breakthrough_lanes) a következményt méri — hol
    törnek be; ez az okot: rendezett védekezésben (az ellenfél
    szervezett támadása alatt) mekkora a legnagyobb rés a fal
    szomszédos védői között. Akinek a falában a kockák 40%+ részében
    3,5 m-nél nagyobb rés tátong, az ellen a betörés és a beúszó
    beálló a terv; a saját edzésnek a zárás-távolság tartása a témája.

    Csak a mért, kapus nélküli, a saját kaputól WALL_GAP_DEPTH_M-en
    belüli védőket számoljuk, és legalább 4 fős falat ítélünk meg.

    Visszatérés csapatonként: {"frames", "wide", "share_pct",
    "avg_gap_m"} — share_pct/avg_gap_m None, ha kevés
    (WALL_GAP_MIN_FRAMES alatti) a mért falkocka.
    """
    from ..models.tracking import PositionSource, Team
    from .tactics import Phase, TacticsConfig, classify_phase

    config = config or TacticsConfig()
    counts = {"home": {"frames": 0, "wide": 0, "gap_sum": 0.0},
              "away": {"frames": 0, "wide": 0, "gap_sum": 0.0}}
    plan = (("home", Team.HOME, Phase.AWAY_ATTACK),
            ("away", Team.AWAY, Phase.HOME_ATTACK))
    for f in match.frames:
        ph = classify_phase(f, config)
        for side, team, needed in plan:
            if ph != needed:
                continue
            gx = config.own_goal_x(team)
            wall = sorted(
                p.y for p in f.players
                if p.team == team and p.source == PositionSource.MEASURED
                and p.role != "kapus" and abs(p.x - gx) <= WALL_GAP_DEPTH_M)
            if len(wall) < 4:
                continue
            gap = max(b - a for a, b in zip(wall, wall[1:]))
            rec = counts[side]
            rec["frames"] += 1
            rec["gap_sum"] += gap
            if gap >= WALL_GAP_M:
                rec["wide"] += 1
    out = {}
    for side in ("home", "away"):
        rec = counts[side]
        enough = rec["frames"] >= WALL_GAP_MIN_FRAMES
        out[side] = {
            "frames": rec["frames"],
            "wide": rec["wide"],
            "share_pct": (round(100.0 * rec["wide"] / rec["frames"], 1)
                          if enough else None),
            "avg_gap_m": (round(rec["gap_sum"] / rec["frames"], 2)
                          if enough else None),
        }
    return out


# Beálló-védekezés: ennyi ellenük vezetett beállós támadástól ítélünk;
# ha a beállós támadásaik gólaránya ennyivel magasabb a beálló
# nélkülinél, a beálló-őrzés a gyenge pont (és fordítva, ha alacsonyabb).
PIVOT_DEF_MIN_ATTACKS = 6
PIVOT_DEF_GAP_PP = 15.0


def pivot_defense(match, config=None) -> dict:
    """Beálló-védekezés: mennyire bírja a fal az ellenfél beállóját.

    A beálló-terhelés (pivot_usage) védő-oldali tükre: ott az látszik,
    ki mennyit játszik a beállóval, itt az, ki mennyire bírja ellene.
    Ugyanazokat a támadásokat nézzük, csak a MÁSIK csapat könyvelésébe
    írva: az ellenük vezetett beállós támadások gólaránya a beálló
    nélküliekhez képest. Ha a beállós támadás érdemben többet terem
    ellenük, a beálló-őrzésük (elöl-mögött váltás, kettőzés) a gyenge
    pont — az ellenfél tervbe veheti a beálló-etetést; ha kevesebbet,
    a beálló ellenük zsákutca: körbe kell játszani őket.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal könyvelésében):
    {"pivot_attacks", "pivot_goals", "other_attacks", "other_goals",
     "pivot_goal_pct", "other_goal_pct", "gap_pp", "verdict"} —
    a pct-k/gap_pp/verdict None, ha kevés (PIVOT_DEF_MIN_ATTACKS
    alatti) ellenük vezetett beállós támadás volt; a verdict
    "gyenge" / "erős" / None (nincs érdemi eltérés).
    """
    from .attack_types import pivot_usage

    pu = pivot_usage(match, config)
    out = {}
    for side, opp in (("home", "away"), ("away", "home")):
        p = pu[opp]
        other_attacks = p["attacks"] - p["pivot_attacks"]
        rec = {
            "pivot_attacks": p["pivot_attacks"],
            "pivot_goals": p["pivot_goals"],
            "other_attacks": other_attacks,
            "other_goals": p["other_goals"],
            "pivot_goal_pct": p["pivot_goal_pct"],
            "other_goal_pct": p["other_goal_pct"],
            "gap_pp": None,
            "verdict": None,
        }
        if (p["pivot_attacks"] >= PIVOT_DEF_MIN_ATTACKS
                and other_attacks > 0
                and p["pivot_goal_pct"] is not None
                and p["other_goal_pct"] is not None):
            gap = p["pivot_goal_pct"] - p["other_goal_pct"]
            rec["gap_pp"] = round(gap, 1)
            if gap >= PIVOT_DEF_GAP_PP:
                rec["verdict"] = "gyenge"
            elif gap <= -PIVOT_DEF_GAP_PP:
                rec["verdict"] = "erős"
        out[side] = rec
    return out


# Elzárás-védekezés: az elzárás-felismerés küszöbei (a screen_usage
# motorral azonosak); ennyi ellenük vezetett elzárásos lövés kell az
# ítélethez, és ekkora gólarány-különbség (százalékpont) számít
# érdeminek.
SCRDEF_MIN_SCREENED = 6
SCRDEF_GAP_PP = 15.0


def screen_defense(match, config=None) -> dict:
    """Elzárás-védekezés: bírja-e a fal az ellenfél elzárásait.

    Az elzárás-használat (screen_usage) védő-oldali tükre: ott az
    látszik, ki mennyit játszik elzárással, itt az, ki mennyire bírja
    ellene. Az ellenük leadott őrzött lövéseket elzárásos és elzárás
    nélküli csoportra bontjuk, és a gólarányukat hasonlítjuk össze. Ha
    az elzárásos lövésekből érdemben többször esik gól, a
    váltás-kommunikáció a gyenge pont: az ellenfélnek minden figurát
    elzárással kell zárnia; ha kevesebbszer, a fal jól vált — ott az
    elzárás zsákutca, tiszta 1v1-et kell keresni.

    Visszatérés csapatonként (a VÉDŐ oldal könyvelésében):
    {"screened_shots", "screened_goals", "open_shots", "open_goals",
    "screened_pct", "open_pct", "gap_pp", "verdict"} —
    pct/gap/verdict None, ha kevés (SCRDEF_MIN_SCREENED alatti) az
    elzárásos lövés; a verdict "gyenge" / "jól vált" / None.
    """
    import math

    from .attack_types import SCREEN_DIST_M, SCREEN_MARKER_MAX_M
    from .tactics import TacticsConfig
    from .xg import match_xg

    config = config or TacticsConfig()
    idx_of = {f.t: i for i, f in enumerate(match.frames)}
    counts = {s: {"screened_shots": 0, "screened_goals": 0,
                  "open_shots": 0, "open_goals": 0}
              for s in ("home", "away")}
    for sh in match_xg(match, config).get("shots", []):
        pid = sh.get("player_id")
        i0 = idx_of.get(sh["t"])
        if pid is None or i0 is None:
            continue
        f = match.frames[i0]
        shooter = next((p for p in f.players if p.track_id == pid),
                       None)
        if shooter is None:
            continue
        marker = None
        best = SCREEN_MARKER_MAX_M
        for d in f.players:
            if d.team is None or d.team == shooter.team:
                continue
            dist = math.hypot(d.x - shooter.x, d.y - shooter.y)
            if dist <= best:
                marker, best = d, dist
        if marker is None:
            continue  # szabad lövés: nem a váltásról szól
        screened = any(
            p.track_id != pid and p.team == shooter.team
            and math.hypot(p.x - marker.x, p.y - marker.y)
            <= SCREEN_DIST_M
            for p in f.players)
        defender = "away" if sh["team"] == "home" else "home"
        rec = counts[defender]
        key = "screened" if screened else "open"
        rec[key + "_shots"] += 1
        if sh["outcome"] == "goal":
            rec[key + "_goals"] += 1
    out = {}
    for side in ("home", "away"):
        rec = counts[side]
        r = {**rec, "screened_pct": None, "open_pct": None,
             "gap_pp": None, "verdict": None}
        if rec["screened_shots"] >= SCRDEF_MIN_SCREENED \
                and rec["open_shots"] > 0:
            scr = 100.0 * rec["screened_goals"] / rec["screened_shots"]
            opn = 100.0 * rec["open_goals"] / rec["open_shots"]
            r["screened_pct"] = round(scr, 1)
            r["open_pct"] = round(opn, 1)
            r["gap_pp"] = round(scr - opn, 1)
            if scr - opn >= SCRDEF_GAP_PP:
                r["verdict"] = "gyenge"
            elif opn - scr >= SCRDEF_GAP_PP:
                r["verdict"] = "jól vált"
        out[side] = r
    return out


# Ellen-press: az eladás utáni ennyi másodpercen belüli visszaszerzést
# számoljuk azonnali visszatámadásnak, ennyi eladástól ítélünk, és
# e fölött/alatt beszélünk erős, illetve beletörődő ellen-pressről.
COUNTERPRESS_WINDOW_S = 6.0
COUNTERPRESS_MIN_TO = 8
COUNTERPRESS_HIGH_PCT = 35.0
COUNTERPRESS_LOW_PCT = 15.0


def counter_press(match, config=None) -> dict:
    """Ellen-press: az eladott labdát azonnal visszaszerzik-e.

    Az eladás-büntetés (turnover_punishment) azt nézi, mennyibe KERÜL
    az eladás; a visszarendeződés-idő (transition_recovery) azt, milyen
    gyorsan érnek haza. Ez a kettő közti pillanatot méri: az eladás
    utáni COUNTERPRESS_WINDOW_S másodpercben visszakerül-e hozzájuk a
    labda. Aki sokszor szerzi vissza, az az eladás pillanatában
    rátámad: ellene a szerzés utáni ELSŐ passznak kell tisztának
    lennie — nem cselezni a saját térfélen, hanem azonnal előre
    játszani. Aki ritkán, az beletörődik: ellene minden szerzés
    ingyen lerohanás, futni kell vele.

    Visszatérés csapatonként (a labdát ELADÓ oldal):
      {"turnovers", "regained", "rate_pct", "verdict"} — rate_pct és
    verdict None, ha kevés (COUNTERPRESS_MIN_TO alatti) az eladás; a
    verdict "visszatámad" / "beletörődik" / None.
    """
    from .event_detection import EventType, detect_events
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = round(COUNTERPRESS_WINDOW_S * fps)
    tos = [(e.t, e.team.value) for e in detect_events(match, config)
           if e.type == EventType.TURNOVER]
    counts = {"home": {"turnovers": 0, "regained": 0},
              "away": {"turnovers": 0, "regained": 0}}
    for i, (t, side) in enumerate(tos):
        other = "away" if side == "home" else "home"
        counts[side]["turnovers"] += 1
        # Visszaszerzés: az ablakon belül az ELLENFÉL adja el a labdát
        # (a következő birtoklás-váltás visszafelé).
        if any(s2 == other and 0 < t2 - t <= win
               for (t2, s2) in tos[i + 1:]):
            counts[side]["regained"] += 1
    out = {}
    for side in ("home", "away"):
        rec = counts[side]
        r = {**rec, "rate_pct": None, "verdict": None}
        if rec["turnovers"] >= COUNTERPRESS_MIN_TO:
            pct = 100.0 * rec["regained"] / rec["turnovers"]
            r["rate_pct"] = round(pct, 1)
            if pct >= COUNTERPRESS_HIGH_PCT:
                r["verdict"] = "visszatámad"
            elif pct <= COUNTERPRESS_LOW_PCT:
                r["verdict"] = "beletörődik"
        out[side] = r
    return out


# Kettőzés: ennyi méteren belül számít a második védő is a labdásra
# lépőnek, ennyi labdás-kockától ítélünk, és e részarány felett
# kettőző, alatta 1v1-et hagyó a védekezés.
DOUBLE_TEAM_M = 2.5
DOUBLE_MIN_FRAMES = 250
DOUBLE_HIGH_PCT = 30.0
DOUBLE_LOW_PCT = 10.0


def double_teams(match, config=None) -> dict:
    """Kettőzés: rálép-e a második védő is a labdásra.

    A védekezési nyomás (defensive_pressure) a LEGKÖZELEBBI védő
    távolságát méri — ez azt, hogy jön-e MÁSODIK: a labdás kockáin
    megszámolja, hányban van legalább két ellenfél DOUBLE_TEAM_M-en
    belül. Aki sokat kettőz, az felszabadítja a kettőzött játékos
    társát: ellene a gyors labdaeladás (egy érintés, üres oldalra
    járatás) a recept — ha lassan játszotok, elveszik a labdát. Aki
    nem kettőz, az 1v1-et hagy: ellene a legjobb áttörőt kell
    kiválasztani és rámenni.

    Visszatérés csapatonként (a KETTŐZŐ, védekező oldal):
      {"holder_frames", "doubled_frames", "doubled_pct",
       "forced_turnovers", "verdict"} — doubled_pct és verdict None,
    ha kevés (DOUBLE_MIN_FRAMES alatti) a labdás-kocka; a verdict
    "kettőz" / "1v1-et hagy" / None.
    """
    import math

    from .decisions import ball_holder
    from .event_detection import EventType, detect_events
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = round(2.0 * fps)   # a kettőzés utáni 2 mp-en belüli eladás
    tos = [(e.t, e.team.value) for e in detect_events(match, config)
           if e.type == EventType.TURNOVER]
    counts = {s: {"holder_frames": 0, "doubled_frames": 0,
                  "forced_turnovers": 0}
              for s in ("home", "away")}
    doubled_since = {"home": None, "away": None}
    for f in match.frames:
        holder = ball_holder(f, config)
        if holder is None or holder.team is None:
            continue
        attacker = holder.team.value
        defender = "away" if attacker == "home" else "home"
        near = sum(1 for p in f.players
                   if p.team is not None and p.team != holder.team
                   and math.hypot(p.x - holder.x, p.y - holder.y)
                   <= DOUBLE_TEAM_M)
        rec = counts[defender]
        rec["holder_frames"] += 1
        if near >= 2:
            rec["doubled_frames"] += 1
            # A kettőzés akkor "hozott" eladást, ha a támadó az
            # ablakon belül elveszti a labdát.
            if any(s == attacker and 0 <= t - f.t <= win
                   for (t, s) in tos) \
                    and doubled_since[defender] != attacker:
                rec["forced_turnovers"] += 1
                doubled_since[defender] = attacker
        else:
            doubled_since[defender] = None
    out = {}
    for side in ("home", "away"):
        rec = counts[side]
        r = {**rec, "doubled_pct": None, "verdict": None}
        if rec["holder_frames"] >= DOUBLE_MIN_FRAMES:
            pct = 100.0 * rec["doubled_frames"] / rec["holder_frames"]
            r["doubled_pct"] = round(pct, 1)
            if pct >= DOUBLE_HIGH_PCT:
                r["verdict"] = "kettőz"
            elif pct <= DOUBLE_LOW_PCT:
                r["verdict"] = "1v1-et hagy"
        out[side] = r
    return out


# Drága eladók: ennyi eladástól nevezünk meg egy játékost, és ennyi
# másodpercen belüli kapott gólt tekintünk az eladás árának.
TO_COST_MIN = 3
TO_COST_WINDOW_S = 30.0


def costly_turnover_players(match, config=None) -> dict:
    """Drága eladók: kinek az eladásai kerülnek gólba.

    A labdaeladók (turnover_players) azt mutatják, KI veszti el a
    labdát — az eladás-büntetés (turnover_punishment) azt, hogy a
    csapat eladásai MENNYIBE kerülnek. Ez a kettő metszete: kinek az
    eladásaiból lesz TO_COST_WINDOW_S mp-en belül kapott gól. Akinek
    a hibái rendre gólt érnek, arra rá kell menni: őt kell
    kettőzni-zavarni a felhozatalnál, mert nála a legnagyobb a
    nyereség — saját olvasatban vele kell a nyomás alatti
    labdakezelést gyakorolni.

    Visszatérés csapatonként: {"players": [{"player_id",
    "turnovers", "punished"}], "worst"} — a lista a gólba került
    eladások szerint csökkenő; a worst az első olyan játékos, akinek
    legalább TO_COST_MIN eladása volt (egyébként None).
    """
    from .event_detection import EventType, detect_events, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = round(TO_COST_WINDOW_S * fps)
    goals = sorted((e.t, e.team.value) for e in detect_shots(match, config)
                   if e.type == EventType.GOAL)
    tally = {"home": {}, "away": {}}
    for e in detect_events(match, config):
        if e.type != EventType.TURNOVER or e.player_id is None:
            continue
        side = e.team.value
        other = "away" if side == "home" else "home"
        rec = tally[side].setdefault(e.player_id,
                                     {"turnovers": 0, "punished": 0})
        rec["turnovers"] += 1
        if any(gs == other and 0 <= gt - e.t <= win for (gt, gs) in goals):
            rec["punished"] += 1
    out = {}
    for side in ("home", "away"):
        players = [{"player_id": pid, **rec}
                   for pid, rec in sorted(
                       tally[side].items(),
                       key=lambda kv: (-kv[1]["punished"],
                                       -kv[1]["turnovers"]))]
        worst = next((p for p in players
                      if p["turnovers"] >= TO_COST_MIN
                      and p["punished"] > 0), None)
        out[side] = {"players": players, "worst": worst}
    return out


# Szélső-védekezés: ennyi méterre a hosszanti középvonaltól kezdődik a
# szélső sáv, sávonként ennyi kapott lövéstől ítélünk, és ennyi
# százalékpont gólarány-eltérés a küszöb.
WINGDEF_Y_M = 6.5
WINGDEF_MIN_SHOTS = 5
WINGDEF_GAP_PP = 15.0


def wing_defense(match, config=None) -> dict:
    """Szélső-védekezés: bírja-e a fal a szélső lövéseket.

    A szélső-befejezés (wing_finishing) a TÁMADÓ oldalról nézi, ki
    mennyire eredményes a szélről — ez a védő oldali tükre: a kapott
    lövéseket a lövő helye alapján szélső és középső sávra bontja, és
    a gólarányukat hasonlítja. Ha a szélről érkező lövések érdemben
    többször gólok, a szélső-őrzés és a kapus szöge a hiba: ellenük
    a szélső bevonása az első számú fegyver. Ha a szél zsákutca,
    marad a középső áttörés és a beálló.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal): {"wing_shots",
    "wing_goals", "center_shots", "center_goals", "wing_pct",
    "center_pct", "gap_pp", "verdict"} — az arányok és a verdict
    None, ha valamelyik sávban kevés (WINGDEF_MIN_SHOTS alatti) a
    lövés; a verdict "szélen nyitott" / "szélen zárt" / None.
    """
    from ..models.tracking import Team
    from .calibration import COURT_WIDTH_M
    from .tactics import TacticsConfig
    from .xg import match_xg

    config = config or TacticsConfig()
    mid_y = COURT_WIDTH_M / 2.0
    counts = {s: {"wing_shots": 0, "wing_goals": 0,
                  "center_shots": 0, "center_goals": 0}
              for s in ("home", "away")}
    for sh in match_xg(match, config).get("shots", []):
        team = Team.HOME if sh["team"] == "home" else Team.AWAY
        defender = "away" if team == Team.HOME else "home"
        key = ("wing" if abs(sh["y"] - mid_y) >= WINGDEF_Y_M
               else "center")
        rec = counts[defender]
        rec[key + "_shots"] += 1
        if sh["outcome"] == "goal":
            rec[key + "_goals"] += 1
    out = {}
    for side in ("home", "away"):
        rec = counts[side]
        r = {**rec, "wing_pct": None, "center_pct": None,
             "gap_pp": None, "verdict": None}
        if rec["wing_shots"] >= WINGDEF_MIN_SHOTS \
                and rec["center_shots"] >= WINGDEF_MIN_SHOTS:
            wg = 100.0 * rec["wing_goals"] / rec["wing_shots"]
            ct = 100.0 * rec["center_goals"] / rec["center_shots"]
            r["wing_pct"] = round(wg, 1)
            r["center_pct"] = round(ct, 1)
            r["gap_pp"] = round(wg - ct, 1)
            if wg - ct >= WINGDEF_GAP_PP:
                r["verdict"] = "szélen nyitott"
            elif ct - wg >= WINGDEF_GAP_PP:
                r["verdict"] = "szélen zárt"
        out[side] = r
    return out


# Célba vett védő: ennyi rá eső lövéstől ítélünk egy védőt, ennyi
# százalékpont gólarány-eltérés a csapatátlagtól a gyenge pont jele, és
# ennyi méteren belül számít egy védő a lövés "gazdájának" (ennél
# messzebbről már nem az ő hibája — az szabad lövés).
TDEF_MIN_SHOTS = 4
TDEF_GAP_PP = 15.0
TDEF_RADIUS_M = 6.0


def targeted_defenders(match, config=None) -> dict:
    """Célba vett védő: KIRE lőnek, és kinél lesz belőle gól.

    A szabad lövés (defense_analysis) és a fal lyukai (wall_gaps,
    breakthrough_lanes) a HELYET mondják meg, a labdaszerzők
    (ball_winners) a védekezés motorját — ez a hiányzó harmadik
    kérdés: melyik védő ELŐTT fejeznek be. Minden kapott lövésnél a
    lövőhöz legközelebbi mezőnyvédő kapja a lövést (TDEF_RADIUS_M-en
    belül; ennél messzebb nincs gazdája, az szabad lövés), és mellé a
    gólt, ha bement.

    Edzőileg két olvasat: akire a legtöbbet lőnek, azt keresi az
    ellenfél (őt kell segíteni, mögé a kapus szöge), akinél pedig a
    csapatátlagnál érdemben magasabb a gólarány, ott a fal tényleg
    puha — felderítéskor pont oda kell támadni.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal):
      {"shots", "goals", "players": [{"player_id", "jersey", "shots",
       "goals", "goal_pct"}], "target": {...}|None,
       "weak": {..., "gap_pp"}|None}
    — players a rá eső lövések szerint csökkenően; goal_pct None
    TDEF_MIN_SHOTS alatt; target a legtöbbet támadott védő (elég
    lövéssel), weak a csapatátlagnál TDEF_GAP_PP-vel rosszabb
    gólarányú védő — mindkettő None, ha nincs elég minta.
    """
    import math

    from ..models.tracking import Team
    from .tactics import TacticsConfig
    from .xg import match_xg

    config = config or TacticsConfig()
    by_t = {f.t: f for f in match.frames}
    jersey: dict[int, int] = {}
    tally: dict[str, dict[int, dict]] = {"home": {}, "away": {}}
    totals = {"home": [0, 0], "away": [0, 0]}  # lövés, gól

    for sh in match_xg(match, config).get("shots", []):
        f = by_t.get(sh["t"])
        if f is None:
            continue
        attacker = Team.HOME if sh["team"] == "home" else Team.AWAY
        side = "away" if attacker == Team.HOME else "home"
        near = None
        near_d = TDEF_RADIUS_M
        for p in f.players:
            if p.team != attacker and p.team is not None \
                    and p.role != "kapus":
                d = math.hypot(p.x - sh["x"], p.y - sh["y"])
                if d <= near_d:
                    near, near_d = p, d
        if near is None:
            continue
        if near.jersey_number is not None:
            jersey.setdefault(near.track_id, near.jersey_number)
        rec = tally[side].setdefault(near.track_id,
                                     {"shots": 0, "goals": 0})
        rec["shots"] += 1
        totals[side][0] += 1
        if sh["outcome"] == "goal":
            rec["goals"] += 1
            totals[side][1] += 1

    out: dict = {}
    for side in ("home", "away"):
        n_sh, n_go = totals[side]
        players = [
            {"player_id": pid, "jersey": jersey.get(pid),
             "shots": rec["shots"], "goals": rec["goals"],
             "goal_pct": (round(100.0 * rec["goals"] / rec["shots"], 1)
                          if rec["shots"] >= TDEF_MIN_SHOTS else None)}
            for pid, rec in sorted(tally[side].items(),
                                   key=lambda kv: (-kv[1]["shots"],
                                                   -kv[1]["goals"]))]
        target = next((p for p in players
                       if p["shots"] >= TDEF_MIN_SHOTS), None)
        weak = None
        if n_sh >= TDEF_MIN_SHOTS:
            avg = 100.0 * n_go / n_sh
            cands = [{**p, "gap_pp": round(p["goal_pct"] - avg, 1)}
                     for p in players
                     if p["goal_pct"] is not None
                     and p["goal_pct"] - avg >= TDEF_GAP_PP]
            if cands:
                weak = max(cands, key=lambda p: p["gap_pp"])
        out[side] = {"shots": n_sh, "goals": n_go, "players": players,
                     "target": target, "weak": weak}
    return out


# Kapott gólok posztonként: ennyi kapott góltól ítélünk, és e feletti
# részarány jelenti, hogy egy poszt ellen szivárog a védekezés.
CONCEDED_ROLE_MIN = 5
CONCEDED_ROLE_SHARE = 45.0


def conceded_by_role(match, config=None) -> dict:
    """Kapott gólok posztonként: MELYIK POSZT ELLEN szivárognak.

    A poszt szerinti gólmegoszlás (goals_by_role) védő-oldali
    tükörképe: ott az látszik, melyik posztra épül a támadó
    befejezése — itt az, hogy a fal melyik poszt ellen engedi a
    gólokat. A gólt a LÖVŐ posztjához kötjük, de a VÉDEKEZŐ csapat
    oldalán tartjuk nyilván.

    Edzőileg ez mondja meg, hova kell játszani ellenük: ha a kapott
    góljaik nagy része a szélső posztról jön, a szélsőiteket kell
    etetni; ha a beállótól, a beállós játékot kell futtatni; ha az
    átlövőktől, a távoli befejezésre kell építeni.

    Visszatérés csapatonként: {"goals" (poszthoz kötött kapott gól),
    "roles": {poszt: gólok}, "top": {"poszt", "goals", "share_pct"} |
    None} — a "top" akkor van kitöltve, ha legalább CONCEDED_ROLE_MIN
    poszthoz kötött kapott gól van, a vezető poszt részaránya eléri a
    CONCEDED_ROLE_SHARE-t, és nincs vele holtversenyben másik poszt.
    """
    from .roles import goals_by_role

    gbr = goals_by_role(match, config)
    out: dict = {}
    for side, opp in (("home", "away"), ("away", "home")):
        roles = dict(gbr[opp]["roles"])
        rec = {"goals": gbr[opp]["goals"], "roles": roles, "top": None}
        items = list(roles.items())
        if rec["goals"] >= CONCEDED_ROLE_MIN and items:
            poszt, n = items[0]
            share = 100.0 * n / rec["goals"]
            tie = len(items) > 1 and items[1][1] == n
            if share >= CONCEDED_ROLE_SHARE and not tie:
                rec["top"] = {"poszt": poszt, "goals": n,
                              "share_pct": round(share, 1)}
        out[side] = rec
    return out


# Hiba-sorozatok: ennyi eladástól ítélünk, ekkora ablakon belül
# számít egy hiba a előzőhöz tartozónak, és e feletti részarány
# jelenti, hogy sorozatban hibáznak.
TC_MIN_TURNOVERS = 5
TC_WINDOW_S = 60.0
TC_SHARE = 50.0


def turnover_clusters(match, config=None) -> dict:
    """Hiba-sorozatok: EGYMÁS UTÁN jönnek-e az eladott labdák.

    Az eladás-időzítés (turnover_timing) azt mondja meg, a birtokláson
    BELÜL mikor adják el a labdát — ez azt, hogy a hibák a meccsen
    belül egyenletesen szóródnak-e, vagy sorozatban érkeznek: két
    eladás egy klaszterbe kerül, ha TC_WINDOW_S-en belül követik
    egymást.

    Edzőileg: ha a hibáik fele sorozatban jön, egy eladás után
    kapkodni kezdenek — az első labdaszerzés után azonnal újra rá kell
    menni, mert ott jön a második ajándék. Ha szórtak a hibák, ez a
    nyomás nem fizet ki: ott a felállt védekezés a válasz.

    Visszatérés csapatonként: {"turnovers", "clusters" (a 2+ tagú
    sorozatok száma), "clustered" (a sorozatban lévő eladások),
    "share_pct", "verdict"} — a share_pct/verdict None, ha kevés
    (TC_MIN_TURNOVERS alatti) az eladás; a verdict "sorozatban
    hibáznak", ha a részarány eléri a TC_SHARE-t, egyébként "szórt
    hibák".
    """
    from .event_detection import EventType, detect_events
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = TC_WINDOW_S * fps

    times: dict = {"home": [], "away": []}
    for e in detect_events(match, config):
        if e.type == EventType.TURNOVER:
            times[e.team.value].append(e.t)

    out: dict = {}
    for side in ("home", "away"):
        ts = sorted(times[side])
        rec = {"turnovers": len(ts), "clusters": 0, "clustered": 0,
               "share_pct": None, "verdict": None}
        # Sorozat: az egymást TC_WINDOW_S-en belül követő eladások.
        run = 1
        for prev, cur in zip(ts, ts[1:]):
            if cur - prev <= win:
                run += 1
                continue
            if run >= 2:
                rec["clusters"] += 1
                rec["clustered"] += run
            run = 1
        if run >= 2:
            rec["clusters"] += 1
            rec["clustered"] += run
        if len(ts) >= TC_MIN_TURNOVERS:
            share = 100.0 * rec["clustered"] / len(ts)
            rec["share_pct"] = round(share, 1)
            rec["verdict"] = ("sorozatban hibáznak" if share >= TC_SHARE
                              else "szórt hibák")
        out[side] = rec
    return out


# Védekezési mélység állás szerint: állásonként ennyi mért kocka kell, és
# ekkora (méteres) eltérés számít érdemi állás-függő váltásnak.
LINE_SCORE_MIN_FRAMES = 100
LINE_SCORE_GAP_M = 0.8


def line_height_by_score(match, config=None) -> dict:
    """Védekezési mélység állás szerint: ELŐNYBEN vagy HÁTRÁNYBAN
    jönnek-e előre.

    A vonal-magasság (defensive_line_height) a meccs egészére adja meg,
    milyen mélyen áll a fal — a támadás-hossz állás szerint
    (pace_by_score) pedig a támadó oldal állás-függő viselkedését. Ez a
    kettő kereszteződése: védekező kockánként megnézzük a védekező
    csapat gólkülönbségét, és állásonként (vezet / hátrányban /
    döntetlen) átlagoljuk a fal magasságát.

    Edzőileg ez mondja meg, mikor jön a nyomásuk: aki hátrányban
    előrelép, annál a vezetést megszerezve nyugalom lesz, de kapott gól
    után jön a letámadás — arra kell kész kihozatal; aki vezetve
    visszaáll mélyre, ellene előnyben türelmesen kell játszani, mert a
    kapkodó átlövés az ő kezükre játszik.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal): {"leading"/"trailing"/
    "level": {"frames", "avg_height_m"}, "gap_m", "verdict"} — az
    avg_height_m None LINE_SCORE_MIN_FRAMES alatt; a gap_m a hátrány- és
    az előny-beli magasság különbsége (pozitív: hátrányban állnak
    feljebb), a verdict "hátrányban feljebb lépnek" (vagyis vezetve
    visszaállnak mélyre) / "vezetve is fent maradnak" / None.
    """
    from ..models.tracking import Team
    from .decisions import ball_holder
    from .event_detection import EventType, detect_shots
    from .tactics import COURT_LENGTH_M, TacticsConfig

    config = config or TacticsConfig()
    half = COURT_LENGTH_M / 2.0
    goals = [(e.t, e.team.value) for e in detect_shots(match, config)
             if e.type == EventType.GOAL]

    acc: dict = {side: {k: [0.0, 0] for k in
                        ("leading", "trailing", "level")}
                 for side in ("home", "away")}
    for f in match.frames:
        holder = ball_holder(f, config)
        if holder is None:
            continue
        deff = Team.AWAY if holder.team == Team.HOME else Team.HOME
        own_x = config.own_goal_x(deff)
        # Csak felállt védekezés: a labdás a védekező csapat térfelén van.
        if abs(holder.x - own_x) > half:
            continue
        depths = [abs(p.x - own_x) for p in f.players
                  if p.team == deff and p.role != "kapus"
                  and abs(p.x - own_x) <= half]
        if not depths:
            continue
        side = deff.value
        own = sum(1 for (t, tm) in goals if t < f.t and tm == side)
        opp = sum(1 for (t, tm) in goals if t < f.t and tm != side)
        state = ("leading" if own > opp
                 else "trailing" if own < opp else "level")
        rec = acc[side][state]
        rec[0] += sum(depths) / len(depths)
        rec[1] += 1

    out: dict = {}
    for side in ("home", "away"):
        rec: dict = {}
        for state in ("leading", "trailing", "level"):
            total, n = acc[side][state]
            rec[state] = {
                "frames": n,
                "avg_height_m": (round(total / n, 2)
                                 if n >= LINE_SCORE_MIN_FRAMES else None)}
        lead = rec["leading"]["avg_height_m"]
        trail = rec["trailing"]["avg_height_m"]
        gap = None
        verdict = None
        if lead is not None and trail is not None:
            gap = round(trail - lead, 2)
            # A két eset ugyanannak az éremnek a két oldala: pozitív
            # rés = hátrányban feljebb (előnyben mélyebbre) állnak.
            if gap >= LINE_SCORE_GAP_M:
                verdict = "hátrányban feljebb lépnek"
            elif gap <= -LINE_SCORE_GAP_M:
                verdict = "vezetve is fent maradnak"
        rec["gap_m"] = gap
        rec["verdict"] = verdict
        out[side] = rec
    return out


# Fal-csúszás késése: ennyi védekezett kocka kell az ítélethez, ekkora
# késleltetésekig nézünk (mp), és e felett lassú, e alatt gyors a
# csúszásuk.
SHIFT_MIN_FRAMES = 200
SHIFT_MAX_LAG_S = 1.2
SHIFT_STEP_S = 0.1
SHIFT_SLOW_S = 0.6
SHIFT_FAST_S = 0.2


def defensive_shift_lag(match, config=None) -> dict:
    """Fal-csúszás késése: MILYEN GYORSAN igazodik a faluk az
    oldalváltáshoz.

    Az oldalváltás (side_switching) a TÁMADÓ oldalról méri, milyen
    gyakran viszik át a labdát a másik oldalra — ez a védő oldali
    válasz: felállt védekezésben összevetjük a labda oldalirányú
    helyét a fal y-súlypontjával, több késleltetéssel, és azt a
    késleltetést vesszük a csúszásuk késésének, amelynél a kettő a
    legjobban fedi egymást.

    Edzőileg: aki lassan csúszik, az ellen az oldalváltás a fegyver —
    két-három gyors átjátszás után a túloldalon nyílik a rés; aki
    gyorsan igazodik, annál az oldalváltás csak fárasztja a saját
    támadást: ott a résre indított betörés és a beállós játék a
    válasz.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal): {"frames", "lag_s",
    "verdict"} — a lag_s/verdict None SHIFT_MIN_FRAMES alatt; a verdict
    "lassan csúsznak" / "gyorsan igazodnak" / None.
    """
    from ..models.tracking import Team
    from .calibration import COURT_WIDTH_M
    from .decisions import ball_holder
    from .tactics import COURT_LENGTH_M, TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    half = COURT_LENGTH_M / 2.0
    cy = COURT_WIDTH_M / 2.0

    # Védekezett kockánként: (a labda y-ja, a fal y-súlypontja).
    series: dict = {"home": [], "away": []}
    for f in match.frames:
        holder = ball_holder(f, config)
        if holder is None or f.ball is None:
            continue
        deff = Team.AWAY if holder.team == Team.HOME else Team.HOME
        own_x = config.own_goal_x(deff)
        # Csak felállt védekezés: a labdás a védekező csapat térfelén.
        if abs(holder.x - own_x) > half:
            continue
        ys = [p.y for p in f.players
              if p.team == deff and p.role != "kapus"
              and abs(p.x - own_x) <= half]
        if len(ys) < 3:
            continue
        series[deff.value].append((f.ball.y - cy,
                                   sum(ys) / len(ys) - cy))

    out: dict = {}
    for side in ("home", "away"):
        rows = series[side]
        rec = {"frames": len(rows), "lag_s": None, "verdict": None}
        if len(rows) >= SHIFT_MIN_FRAMES:
            best = None
            lag = 0.0
            while lag <= SHIFT_MAX_LAG_S + 1e-9:
                shift = round(lag * fps)
                if shift >= len(rows):
                    break
                # A fal `shift` kockával későbbi helye a labdáéhoz mérve.
                diffs = [abs(rows[i][0] - rows[i + shift][1])
                         for i in range(len(rows) - shift)]
                score = sum(diffs) / len(diffs)
                if best is None or score < best[1]:
                    best = (lag, score)
                lag += SHIFT_STEP_S
            if best is not None:
                rec["lag_s"] = round(best[0], 1)
                rec["verdict"] = ("lassan csúsznak"
                                  if rec["lag_s"] >= SHIFT_SLOW_S
                                  else "gyorsan igazodnak"
                                  if rec["lag_s"] <= SHIFT_FAST_S
                                  else None)
        out[side] = rec
    return out


# Visszaérés-fegyelem: ennyi mért játékos-kocka kell egy ember
# megítéléséhez, és e alatti "hazaérési" arány jelenti, hogy elöl lóg.
REC_DISC_MIN_FRAMES = 200
REC_DISC_LOW_PCT = 70.0


def recovery_discipline(match, config=None) -> dict:
    """Visszaérés-fegyelem: KI nem fut vissza védekezni.

    Az átmenet-védekezés (transition_defense) csapat-szinten mondja
    meg, mennyi gyors gólt kapnak labdavesztés után — ez játékosonként
    bontja: a védekezett kockákban megnézzük, ki van a SAJÁT
    térfelén. Aki a védekezett idő nagy részét az ellenfél térfelén
    tölti, az elöl lóg: nála indul a kontra ellenük.

    Edzőileg: a felderítésben ez mondja meg, melyik oldalon érdemes a
    gyors indítást vezetni (az elöl lógó ember mögött nincs védő); a
    saját csapatban pedig a visszafutás-fegyelem edzés-témája.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal): {"players":
    [{"player_id", "jersey", "frames", "home_frames", "share_pct"}],
    "worst"} — a lista a hazaérési arány szerint NÖVEKVŐ; a "worst" az
    első játékos, ha van legalább REC_DISC_MIN_FRAMES mért kockája, és
    az aránya REC_DISC_LOW_PCT alatt van.
    """
    from ..models.tracking import Team
    from .decisions import ball_holder
    from .tactics import COURT_LENGTH_M, TacticsConfig

    config = config or TacticsConfig()
    half = COURT_LENGTH_M / 2.0
    jersey: dict = {}
    acc: dict = {"home": {}, "away": {}}
    for f in match.frames:
        holder = ball_holder(f, config)
        if holder is None:
            continue
        deff = Team.AWAY if holder.team == Team.HOME else Team.HOME
        own_x = config.own_goal_x(deff)
        # Csak felállt/rendezett védekezés: a labda a védő térfelén.
        if abs(holder.x - own_x) > half:
            continue
        for p in f.players:
            if p.team != deff or p.role == "kapus":
                continue
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)
            rec = acc[deff.value].setdefault(p.track_id, [0, 0])
            rec[0] += 1
            if abs(p.x - own_x) <= half:
                rec[1] += 1

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "frames": n, "home_frames": h,
                 "share_pct": round(100.0 * h / n, 1)}
                for pid, (n, h) in acc[side].items() if n > 0]
        rows.sort(key=lambda r: r["share_pct"])
        worst = None
        cand = [r for r in rows if r["frames"] >= REC_DISC_MIN_FRAMES]
        if cand and cand[0]["share_pct"] < REC_DISC_LOW_PCT:
            worst = cand[0]
        out[side] = {"players": rows, "worst": worst}
    return out


# Védekezés-keménység: ennyi védekezett támadástól ítélünk, e feletti
# büntetés-arány a kemény, e alatti a passzív fal jele.
AGGR_MIN_ATTACKS = 10
AGGR_HARD_PCT = 12.0
AGGR_SOFT_PCT = 4.0


def defensive_aggression(match, config=None) -> dict:
    """Védekezés-keménység: MENNYI BÜNTETÉST hoz a faluk.

    A védekezési nyomás (defensive_pressure) azt méri, milyen közel
    mennek a labdáshoz, a vonal-magasság (defensive_line_height) azt,
    hol áll a fal — ez azt, MENNYIBE KERÜL: a védekezett támadásokhoz
    viszonyítjuk az ellenük megítélt hetesek és a kapott kiállítások
    számát.

    Edzőileg: a kemény fal ellen a betörés duplán fizet (vagy
    áthaladtok, vagy hetes és emberelőny jön belőle), és a
    hetes-lövőtöknek végig hidegvérűnek kell lennie; a passzív fal
    ellen viszont nem lesz ingyen büntető — ott a figurákkal és a
    beállós játékkal kell helyzetet csinálni.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal): {"attacks", "sevens",
    "suspensions", "pct", "verdict"} — a pct/verdict None
    AGGR_MIN_ATTACKS alatt; a verdict "kemény fal" / "passzív fal" /
    None.
    """
    from ..models.tracking import Team
    from .rules import detect_powerplay, detect_seven_meters
    from .setplays import segment_attacks
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    out: dict = {side: {"attacks": 0, "sevens": 0, "suspensions": 0,
                        "pct": None, "verdict": None}
                 for side in ("home", "away")}

    for seq in segment_attacks(match, config):
        defending = "away" if seq.team == Team.HOME else "home"
        out[defending]["attacks"] += 1
    for sm in detect_seven_meters(match, config):
        defending = "away" if sm["team"] == "home" else "home"
        out[defending]["sevens"] += 1
    for w in detect_powerplay(match):
        out[w["team_down"]]["suspensions"] += 1

    for side in ("home", "away"):
        rec = out[side]
        if rec["attacks"] >= AGGR_MIN_ATTACKS:
            pct = (100.0 * (rec["sevens"] + rec["suspensions"])
                   / rec["attacks"])
            rec["pct"] = round(pct, 1)
            if pct >= AGGR_HARD_PCT:
                rec["verdict"] = "kemény fal"
            elif pct <= AGGR_SOFT_PCT:
                rec["verdict"] = "passzív fal"
    return out


# Kapott gólok támadás-típus szerint: ennyi típushoz kötött kapott gól
# kell, és e feletti részarány jelenti, hogy egy műfajból szivárognak.
CAT_MIN_GOALS = 5
CAT_SHARE = 40.0


def conceded_by_attack_type(match, config=None) -> dict:
    """Kapott gólok támadás-típus szerint: MILYEN TÁMADÁSBÓL kapják a
    gólokat.

    A támadás-hatékonyság (attack_efficiency) a támadó oldalról nézi,
    melyik műfaj mennyire eredményes — ez a védő oldali párja: a
    gólokat a támadás típusához (lerohanás / gyors indítás / felállt
    támadás / 7 a 6) kötjük, de a VÉDEKEZŐ csapat oldalán tartjuk
    nyilván.

    Edzőileg ez rangsorolja a védekezési munkát: ha a kapott góljaik
    nagy része lerohanásból jön, a visszarendeződés a kulcs (nem a fal
    minősége); ha felállt támadásból, a fal szervezésén kell dolgozni.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal): {"goals", "types":
    {típus: gólok}, "top": {"type", "goals", "share_pct"} | None} — a
    "top" akkor van kitöltve, ha legalább CAT_MIN_GOALS típushoz
    kötött kapott gól van, a vezető típus részaránya eléri a
    CAT_SHARE-t, és nincs vele holtversenyben másik típus.
    """
    from ..models.tracking import Team
    from .attack_types import ATTACK_TAIL_S, classify_attacks
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    tail = round(ATTACK_TAIL_S * fps)
    goals = [(e.t, e.team.value) for e in detect_shots(match, config)
             if e.type == EventType.GOAL]

    out: dict = {side: {"goals": 0, "types": {}, "top": None}
                 for side in ("home", "away")}
    used: set = set()
    for a in classify_attacks(match, config):
        side = a["team"]
        defending = "away" if side == "home" else "home"
        for i, (t, tm) in enumerate(goals):
            if i in used or tm != side:
                continue
            if not (a["start_frame"] <= t <= a["end_frame"] + tail):
                continue
            used.add(i)
            rec = out[defending]
            rec["goals"] += 1
            rec["types"][a["type"]] = rec["types"].get(a["type"], 0) + 1

    for side in ("home", "away"):
        rec = out[side]
        rec["types"] = dict(sorted(rec["types"].items(),
                                   key=lambda kv: -kv[1]))
        items = list(rec["types"].items())
        if rec["goals"] >= CAT_MIN_GOALS and items:
            typ, n = items[0]
            share = 100.0 * n / rec["goals"]
            tie = len(items) > 1 and items[1][1] == n
            if share >= CAT_SHARE and not tie:
                rec["top"] = {"type": typ, "goals": n,
                              "share_pct": round(share, 1)}
    return out


# Falépítés-idő: ennyi mért eset kell az ítélethez, ennyi védő számít
# rendezett falnak, ennyi méteren belül a saját kaputól, és e feletti /
# alatti átlagidő a lassú, illetve a gyors felállás jele.
SETUP_MIN_CASES = 4
SETUP_DEFENDERS = 5
SETUP_ZONE_M = 12.0
SETUP_MAX_S = 20.0
SETUP_SLOW_S = 8.0
SETUP_FAST_S = 5.0


def defense_setup_time(match, config=None) -> dict:
    """Falépítés-idő: MENNYI IDŐ ALATT ÁLL FEL a faluk.

    Az átmenet-védekezés (transition_defense) azt mondja meg, mennyi
    gyors gólt kapnak labdavesztés után, a visszaérés-fegyelem
    (recovery_discipline) azt, ki nem fut vissza — ez azt, MENNYI IDŐ
    a rendezett falig: minden birtokváltásnál mérjük, hány másodperc
    múlva áll legalább SETUP_DEFENDERS mezőnyvédőjük a saját kapuhoz
    SETUP_ZONE_M-en belül.

    Edzőileg: a lassan felálló fal ellen a gyors indítás termel — a
    kapus azonnal indítson, és a szélsők a lövés pillanatában
    fussanak; a gyorsan rendeződő fal ellen a kontra kockázat, ott a
    felállt támadásra kell építeni.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal): {"cases", "avg_s",
    "verdict"} — az avg_s/verdict None SETUP_MIN_CASES alatt; a
    verdict "lassan állnak fel" / "gyorsan rendeződnek" / None.
    """
    from ..models.tracking import Team
    from .decisions import ball_holder
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    frames = match.frames
    horizon = round(SETUP_MAX_S * fps)

    # Birtokváltások: az új birtokos csapat ellenfele kezd védekezni.
    changes: list = []
    prev = None
    for i, f in enumerate(frames):
        h = ball_holder(f, config)
        if h is None:
            continue
        if prev is not None and h.team != prev:
            changes.append((i, Team.AWAY if h.team == Team.HOME
                            else Team.HOME))
        prev = h.team

    acc = {"home": [0, 0.0], "away": [0, 0.0]}
    for idx, deff in changes:
        own_x = config.own_goal_x(deff)
        setup_i = None
        for j in range(idx, min(len(frames), idx + horizon)):
            n = sum(1 for p in frames[j].players
                    if p.team == deff and p.role != "kapus"
                    and abs(p.x - own_x) <= SETUP_ZONE_M)
            if n >= SETUP_DEFENDERS:
                setup_i = j
                break
        if setup_i is None:
            continue  # a felállás nem látszik az ablakban: nem mérjük
        acc[deff.value][0] += 1
        acc[deff.value][1] += (frames[setup_i].t - frames[idx].t) / fps

    out: dict = {}
    for side in ("home", "away"):
        n, total = acc[side]
        rec = {"cases": n, "avg_s": None, "verdict": None}
        if n >= SETUP_MIN_CASES:
            avg = total / n
            rec["avg_s"] = round(avg, 1)
            if avg >= SETUP_SLOW_S:
                rec["verdict"] = "lassan állnak fel"
            elif avg <= SETUP_FAST_S:
                rec["verdict"] = "gyorsan rendeződnek"
        out[side] = rec
    return out


# Elöl szerző védők: ennyi labdaszerzéstől ítélünk emberenként, és e
# feletti "elöl" arány jelenti, hogy a támadó térfélen dolgozik.
HSP_MIN_STEALS = 3
HSP_HIGH_PCT = 50.0


def high_steal_players(match, config=None) -> dict:
    """Elöl szerző védők: KI SZED LABDÁT a támadó térfélen.

    A labdaszerzők (ball_winners) azt mondják meg, KI szerzi a
    labdákat, a szerzés-magasság (steal_height) azt, HOL történik ez
    csapat-szinten — ez a kettő kereszteződése: játékosonként bontjuk,
    hány szerzésük születik a SAJÁT támadó térfelükön (letámadásból).

    Edzőileg: az elöl szedő ember oldalán nem szabad a kihozatalt
    vezetni — vele szemben a kapus a másik oldalra indítson, és a
    felhozó ne fusson a sávjába.

    Visszatérés csapatonként: {"steals", "players": [{"player_id",
    "jersey", "steals", "high"}], "top"} — a lista elöl-szerzés
    szerint csökkenő; a "top" az a játékos, akinek legalább
    HSP_MIN_STEALS szerzése van, és azok HSP_HIGH_PCT-nál nagyobb
    része a támadó térfélen történt.
    """
    from ..models.tracking import Team
    from .decisions import ball_holder
    from .tactics import COURT_LENGTH_M, TacticsConfig

    config = config or TacticsConfig()
    half = COURT_LENGTH_M / 2.0
    jersey: dict = {}
    tally: dict = {"home": {}, "away": {}}
    prev = None
    for f in match.frames:
        h = ball_holder(f, config)
        if h is None:
            continue
        if prev is not None and h.team != prev:
            if h.jersey_number is not None:
                jersey.setdefault(h.track_id, h.jersey_number)
            rec = tally[h.team.value].setdefault(h.track_id,
                                                 {"steals": 0,
                                                  "high": 0})
            rec["steals"] += 1
            goal_x = config.attacks_toward_x(h.team)
            if abs(h.x - goal_x) <= half:
                rec["high"] += 1   # a saját támadó térfelén szerzett
        prev = h.team

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "steals": r["steals"], "high": r["high"]}
                for pid, r in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1]["high"])]
        top = None
        for row in rows:
            if row["steals"] >= HSP_MIN_STEALS and (
                    100.0 * row["high"] / row["steals"]
                    >= HSP_HIGH_PCT):
                top = row
                break
        out[side] = {"steals": sum(r["steals"] for r in rows),
                     "players": rows, "top": top}
    return out


# Fedezetten lövők: ennyi mért lövéstől ítélünk emberenként, és e
# feletti fedezett arány jelenti, hogy nyomás alatt is elhúzza a
# ravaszt.
COV_MIN_SHOTS = 5
COV_SHARE_PCT = 60.0


def covered_shooters(match, config=None) -> dict:
    """Fedezetten lövők: KI HÚZZA EL a ravaszt nyomás alatt is.

    A nyomás alatti befejezés (pressure_finishing) csapat-szinten
    mondja meg, mennyit érnek a fedezett lövéseik — ez azt, KI vállalja
    őket: lövőnként számoljuk a lövéseket és azok közül a fedezetteket
    (a lövőtől FREE_DEF_RADIUS_M-en belül van védő).

    Edzőileg: aki fedezetten is lő, alacsony értékű befejezéseket ad —
    rá nem kell kilépni, elég a blokk-kéz és a kapus mögé rendezett
    fal; aki csak szabadon lő, azt szorítani kell, mert nyomás alatt
    inkább passzol, és abból lesz a hiba.

    Visszatérés csapatonként (a TÁMADÓ oldal): {"players":
    [{"player_id", "jersey", "shots", "covered"}], "top"} — a lista
    fedezett lövés szerint csökkenő; a "top" az a játékos, akinek
    legalább COV_MIN_SHOTS lövése van, és azok COV_SHARE_PCT-nál
    nagyobb része fedezett volt.
    """
    import math

    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    by_t = {f.t: f for f in match.frames}
    jersey: dict = {}
    tally: dict = {"home": {}, "away": {}}
    for e in detect_shots(match, config):
        if e.type not in (EventType.SHOT, EventType.GOAL) \
                or e.player_id is None:
            continue
        f = by_t.get(e.t)
        if f is None:
            continue
        shooter = next((p for p in f.players
                        if p.track_id == e.player_id), None)
        if shooter is None:
            continue
        dists = [math.hypot(p.x - shooter.x, p.y - shooter.y)
                 for p in f.players
                 if p.team is not None and p.team != e.team
                 and p.role != "kapus"]
        if not dists:
            continue  # nem látszik védő: a fedezettség nem mérhető
        if shooter.jersey_number is not None:
            jersey.setdefault(shooter.track_id, shooter.jersey_number)
        rec = tally[e.team.value].setdefault(e.player_id,
                                             {"shots": 0, "covered": 0})
        rec["shots"] += 1
        if min(dists) <= FREE_DEF_RADIUS_M:
            rec["covered"] += 1

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "shots": r["shots"], "covered": r["covered"]}
                for pid, r in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1]["covered"])]
        top = None
        for row in rows:
            if row["shots"] >= COV_MIN_SHOTS and (
                    100.0 * row["covered"] / row["shots"]
                    >= COV_SHARE_PCT):
                top = row
                break
        out[side] = {"players": rows, "top": top}
    return out


# Gól utáni letámadás: ekkora ablakot nézünk a saját gól után, ennyi
# mért kocka kell mindkét oldalon, és ennyivel magasabb fal jelenti a
# letámadást (illetve ennyivel mélyebb a visszahúzódást).
PAG_WINDOW_S = 20.0
PAG_MIN_FRAMES = 60
PAG_UP_M = 1.5


def press_after_goal(match, config=None) -> dict:
    """Gól utáni letámadás: SAJÁT GÓL UTÁN feljebb megy-e a fal.

    A védekezési vonal magassága (defensive_line_height) a teljes
    meccs átlagát adja — ez azt, hogy a csapat a saját gólja utáni
    PAG_WINDOW_S másodpercben magasabban védekezik-e, mint egyébként.
    A lendület kihasználása edzői döntés: aki gól után letámad, az a
    saját gólját akarja rögtön másodikkal folytatni.

    Edzőileg: aki gól után feljebb megy, annál a kapott gól utáni
    kihozatalt előre meg kell tervezni — hosszú indítás a kapustól,
    vagy egy előre kilépő, biztos kezű átvevő; aki gól után
    visszahúzódik, annál viszont pont ilyenkor lehet nyugodtan
    felhozni és időt nyerni a felállásra.

    Visszatérés csapatonként: {"after_frames", "base_frames",
    "after_m", "base_m", "verdict"} — az avg-ek/verdict None
    PAG_MIN_FRAMES alatt; a verdict "gól után letámadnak" / "gól után
    visszahúzódnak" / None.
    """
    from ..models.tracking import Team
    from .decisions import ball_holder
    from .event_detection import EventType, detect_events
    from .tactics import COURT_LENGTH_M, TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = round(PAG_WINDOW_S * fps)
    half = COURT_LENGTH_M / 2.0

    goals = [(e.t, e.team) for e in detect_events(match, config)
             if e.type == EventType.GOAL]

    acc = {"home": {"after": [0.0, 0], "base": [0.0, 0]},
           "away": {"after": [0.0, 0], "base": [0.0, 0]}}
    for f in match.frames:
        holder = ball_holder(f, config)
        if holder is None:
            continue
        deff = Team.AWAY if holder.team == Team.HOME else Team.HOME
        own_x = config.own_goal_x(deff)
        # Csak felállt védekezés: a labdás a védekező csapat térfelén.
        if abs(holder.x - own_x) > half:
            continue
        depths = [abs(p.x - own_x) for p in f.players
                  if p.team == deff and p.role != "kapus"
                  and abs(p.x - own_x) <= half]
        if not depths:
            continue
        # A védekező csapat SAJÁT gólja utáni ablakban vagyunk?
        fresh = any(gt < f.t <= gt + win and gteam == deff
                    for (gt, gteam) in goals)
        rec = acc[deff.value]["after" if fresh else "base"]
        rec[0] += sum(depths) / len(depths)
        rec[1] += 1

    out: dict = {}
    for side in ("home", "away"):
        a_sum, a_n = acc[side]["after"]
        b_sum, b_n = acc[side]["base"]
        rec = {"after_frames": a_n, "base_frames": b_n,
               "after_m": None, "base_m": None, "verdict": None}
        if a_n >= PAG_MIN_FRAMES and b_n >= PAG_MIN_FRAMES:
            a_avg, b_avg = a_sum / a_n, b_sum / b_n
            rec["after_m"] = round(a_avg, 2)
            rec["base_m"] = round(b_avg, 2)
            if a_avg - b_avg >= PAG_UP_M:
                rec["verdict"] = "gól után letámadnak"
            elif b_avg - a_avg >= PAG_UP_M:
                rec["verdict"] = "gól után visszahúzódnak"
        out[side] = rec
    return out


# Labdaszerzés-típus: legalább ekkora birtokos nélküli rés (mp) számít
# röptében elfogott passznak, ennyi szerzés kell az ítélethez, és e
# feletti / alatti elfogás-arány a passzsáv-záró, illetve a testre menő
# védekezés jele.
STT_GAP_S = 0.2
STT_MIN_STEALS = 6
STT_INT_PCT = 60.0
STT_TACKLE_PCT = 25.0


def steal_types(match, config=None) -> dict:
    """Labdaszerzés-típus: ELFOGJÁK vagy LESZERELIK a labdát.

    A labdaszerzők (ball_winners) azt mondják meg, KI szerez, az elöl
    szerzők (high_steal_players) azt, HOL — ez azt, HOGYAN: ha a
    birtokos-váltás előtt a labda legalább STT_GAP_S másodpercig
    senkinél sem volt (röptében járt), a szerzés passz-elfogás; ha a
    labda kézből kézbe került, szerelés a támadó testén.

    Edzőileg: a passzsávakat záró csapat ellen nem szabad keresztbe
    lebegtetni — rövid, közvetlen passzok és betörések kellenek; a
    testre menő csapat ellen a gyors labdajáratás a fegyver: a labda
    hamarabb megy tovább, mint ahogy a kontakt megérkezne, a
    keresztpassz pedig nyugodtan vállalható.

    Visszatérés csapatonként (a SZERZŐ oldal): {"steals",
    "interceptions", "tackles", "int_pct", "verdict"} — az
    int_pct/verdict None STT_MIN_STEALS alatt; a verdict "a
    passzsávakat zárják" / "testre mennek" / None.
    """
    from .decisions import ball_holder
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    gap_frames = max(1, round(STT_GAP_S * fps))

    out = {side: {"steals": 0, "interceptions": 0, "tackles": 0,
                  "int_pct": None, "verdict": None}
           for side in ("home", "away")}
    prev = None
    prev_i = None
    for i, f in enumerate(match.frames):
        holder = ball_holder(f, config)
        if holder is None:
            continue
        if (prev is not None and holder.team != prev.team
                and holder.role != "kapus"):
            rec = out[holder.team.value]
            rec["steals"] += 1
            # Mekkora rés volt az előző birtokos óta? Nagy rés = a
            # labda röptében járt, a szerző a passzt fogta el.
            if i - prev_i >= gap_frames + 1:
                rec["interceptions"] += 1
            else:
                rec["tackles"] += 1
        prev, prev_i = holder, i

    for side in ("home", "away"):
        rec = out[side]
        if rec["steals"] >= STT_MIN_STEALS:
            pct = 100.0 * rec["interceptions"] / rec["steals"]
            rec["int_pct"] = round(pct, 1)
            if pct >= STT_INT_PCT:
                rec["verdict"] = "a passzsávakat zárják"
            elif pct <= STT_TACKLE_PCT:
                rec["verdict"] = "testre mennek"
    return out


# Szerzés utáni indítás: ekkora ablakban nézzük a labda útját a szerzés
# után, legalább ennyi métert kell előre haladnia az "előre indítás"
# ítélethez, ennyi mért szerzés kell, és e feletti / alatti arány az
# azonnal induló, illetve a biztosító csapat jele.
STL_WINDOW_S = 4.0
STL_FWD_M = 6.0
STL_MIN_STEALS = 6
STL_FAST_PCT = 60.0
STL_SAFE_PCT = 25.0


def steal_launch(match, config=None) -> dict:
    """Szerzés utáni indítás: AZONNAL ELŐRE megy-e a szerzett labda.

    A labdaszerzők (ball_winners) azt mondják meg, ki szerez, a
    labdaszerzés-típus (steal_types) azt, hogyan — ez azt, MI TÖRTÉNIK
    UTÁNA: a szerzés utáni STL_WINDOW_S másodpercben legalább
    STL_FWD_M métert halad-e előre a labda a támadási irányban.

    Edzőileg: az azonnal induló csapat ellen a labdavesztés
    pillanatában kész tervnek kell lennie — kijelölt fékező ember, a
    többiek sprintben hátra, és senki nem reklamál a bírónál; a
    biztosító csapat ellen a labdavesztés után van idő rendezni a
    letámadást, az első hátrapasszukra rá lehet lépni.

    Visszatérés csapatonként (a SZERZŐ oldal): {"steals", "forward",
    "fwd_pct", "verdict"} — az fwd_pct/verdict None STL_MIN_STEALS
    alatt; a verdict "szerzés után azonnal indítanak" / "szerzés után
    biztosítanak" / None.
    """
    from .decisions import ball_holder
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = round(STL_WINDOW_S * fps)
    frames = match.frames

    out = {side: {"steals": 0, "forward": 0, "fwd_pct": None,
                  "verdict": None} for side in ("home", "away")}
    prev = None
    for i, f in enumerate(frames):
        holder = ball_holder(f, config)
        if holder is None:
            continue
        if (prev is not None and holder.team != prev.team
                and holder.role != "kapus"):
            goal_x = config.attacks_toward_x(holder.team)
            start_d = abs((f.ball.x if f.ball else holder.x) - goal_x)
            best = 0.0
            for j in range(i + 1, min(len(frames), i + 1 + win)):
                b = frames[j].ball
                if b is None:
                    continue
                # Ha közben elveszik a labda, az ablak lezárul.
                h2 = ball_holder(frames[j], config)
                if h2 is not None and h2.team != holder.team:
                    break
                best = max(best, start_d - abs(b.x - goal_x))
            rec = out[holder.team.value]
            rec["steals"] += 1
            if best >= STL_FWD_M:
                rec["forward"] += 1
        prev = holder

    for side in ("home", "away"):
        rec = out[side]
        if rec["steals"] >= STL_MIN_STEALS:
            pct = 100.0 * rec["forward"] / rec["steals"]
            rec["fwd_pct"] = round(pct, 1)
            if pct >= STL_FAST_PCT:
                rec["verdict"] = "szerzés után azonnal indítanak"
            elif pct <= STL_SAFE_PCT:
                rec["verdict"] = "szerzés után biztosítanak"
    return out


# Kilépő védő: ennyi mért védekező kocka kell egy játékoshoz, és
# ennyivel a társak átlaga előtt álló védő számít kilépőnek (5-1 /
# 3-2-1 jelleg).
ADV_MIN_FRAMES = 100
ADV_GAP_M = 2.5


def advanced_defender(match, config=None) -> dict:
    """Kilépő védő: VAN-E ELŐRETOLT EMBERÜK a falban, és ki az.

    A vonal-magasság (defensive_line_height) a fal átlagos helyét
    adja — ez a fal ALAKJÁT: felállt védekezésben játékosonként
    mérjük a saját kaputól vett átlagos távolságot, és megnézzük,
    van-e a társai átlagánál legalább ADV_GAP_M méterrel előrébb
    álló védő (az 5-1 vagy 3-2-1 kilépője).

    Edzőileg: a kilépő védő mögött nyílik a tér — elzárást kell rá
    vinni, és a háta mögé befutó emberrel 2 az 1-et játszani; a saját
    csapatban pedig a kilépő mögötti biztosítás külön edzés-téma,
    mert a kilépés csak akkor ér valamit, ha mögötte zár a sor.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal): {"players":
    [{"player_id", "jersey", "frames", "avg_depth_m"}], "top",
    "gap_m", "verdict"} — a top/gap_m/verdict None, ha nincs elég
    mért kocka vagy nincs kiugró ember; a verdict "van kilépő
    védőjük" / None.
    """
    from ..models.tracking import Team
    from .decisions import ball_holder
    from .tactics import COURT_LENGTH_M, TacticsConfig

    config = config or TacticsConfig()
    half = COURT_LENGTH_M / 2.0
    jersey: dict = {}
    acc: dict = {"home": {}, "away": {}}
    for f in match.frames:
        holder = ball_holder(f, config)
        if holder is None:
            continue
        deff = Team.AWAY if holder.team == Team.HOME else Team.HOME
        own_x = config.own_goal_x(deff)
        # Csak felállt védekezés: a labdás a védekező csapat térfelén.
        if abs(holder.x - own_x) > half:
            continue
        for p in f.players:
            if p.team != deff or p.role == "kapus":
                continue
            if abs(p.x - own_x) > half:
                continue
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)
            rec = acc[deff.value].setdefault(p.track_id, [0, 0.0])
            rec[0] += 1
            rec[1] += abs(p.x - own_x)

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": tid, "jersey": jersey.get(tid),
                 "frames": n, "avg_depth_m": round(total / n, 2)}
                for tid, (n, total) in acc[side].items()
                if n >= ADV_MIN_FRAMES]
        rows.sort(key=lambda r: -r["avg_depth_m"])
        top = None
        gap = None
        verdict = None
        if len(rows) >= 3:
            cand = rows[0]
            others = rows[1:]
            base = (sum(r["avg_depth_m"] * r["frames"] for r in others)
                    / sum(r["frames"] for r in others))
            gap = round(cand["avg_depth_m"] - base, 2)
            if gap >= ADV_GAP_M:
                top = cand
                verdict = "van kilépő védőjük"
        out[side] = {"players": rows, "top": top, "gap_m": gap,
                     "verdict": verdict}
    return out


# Beálló-őr: ekkora sugáron belüli legközelebbi védő számít őrzőnek,
# ennyi mért őrzés-kocka kell az ítélethez, és e feletti részesedés
# jelenti az egy emberre bízott beálló-őrzést.
PVG_RADIUS_M = 3.0
PVG_MIN_FRAMES = 300
PVG_TOP_PCT = 60.0


def pivot_guards(match, config=None) -> dict:
    """Beálló-őr: KI ŐRZI az ellenfél beállóját.

    A beálló-védekezés (pivot_defense) azt mondja meg, mennyire bírja
    a fal a beállót — ez azt, KI a felelőse: felállt védekezésben
    megkeressük az ellenfél becsült beállójához legközelebbi védőt
    (PVG_RADIUS_M-en belül), és kockánként neki írjuk az őrzést.

    Edzőileg: ha a beálló-őrzés egy emberen áll, az elzárást rá kell
    vinni — ha őt kihúzzák, a beálló felszabadul, és a besegítés
    rendje is borul; a saját csapatban pedig látszik, kire épül a
    belső védekezés, és kinek kell a beálló-őrzés edzés-blokkja.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal): {"frames", "guards":
    [{"player_id", "jersey", "frames"}], "top", "verdict"} — a
    top/verdict None PVG_MIN_FRAMES mért kocka alatt vagy PVG_TOP_PCT
    alatti részesedésnél; a verdict "egy ember őrzi a beállót" /
    None.
    """
    import math

    from ..models.tracking import Team
    from .decisions import ball_holder
    from .roles import estimate_positions
    from .tactics import COURT_LENGTH_M, TacticsConfig

    config = config or TacticsConfig()
    half = COURT_LENGTH_M / 2.0
    posts = estimate_positions(match, config)
    pivots = {side: {tid for tid, r in posts.get(side, {}).items()
                     if r["poszt"] == "beálló"}
              for side in ("home", "away")}

    jersey: dict = {}
    acc: dict = {"home": {}, "away": {}}
    counted = {"home": 0, "away": 0}
    for f in match.frames:
        holder = ball_holder(f, config)
        if holder is None:
            continue
        deff = Team.AWAY if holder.team == Team.HOME else Team.HOME
        own_x = config.own_goal_x(deff)
        if abs(holder.x - own_x) > half:
            continue   # csak felállt védekezés
        atk_side = holder.team.value
        piv = [p for p in f.players
               if p.team == holder.team and p.track_id in pivots[atk_side]]
        if not piv:
            continue
        pv = piv[0]
        defenders = [p for p in f.players
                     if p.team == deff and p.role != "kapus"]
        if not defenders:
            continue
        guard = min(defenders,
                    key=lambda p: math.hypot(p.x - pv.x, p.y - pv.y))
        if math.hypot(guard.x - pv.x, guard.y - pv.y) > PVG_RADIUS_M:
            continue
        if guard.jersey_number is not None:
            jersey.setdefault(guard.track_id, guard.jersey_number)
        counted[deff.value] += 1
        acc[deff.value][guard.track_id] = (
            acc[deff.value].get(guard.track_id, 0) + 1)

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": tid, "jersey": jersey.get(tid),
                 "frames": n}
                for tid, n in sorted(acc[side].items(),
                                     key=lambda kv: -kv[1])]
        top = None
        verdict = None
        if counted[side] >= PVG_MIN_FRAMES and rows:
            share = 100.0 * rows[0]["frames"] / counted[side]
            if share >= PVG_TOP_PCT:
                top = rows[0]
                verdict = "egy ember őrzi a beállót"
        out[side] = {"frames": counted[side], "guards": rows,
                     "top": top, "verdict": verdict}
    return out


# Szélső-kifutás: ennyi szélső-lövés kell az ítélethez, és e feletti /
# alatti átlagos védő-távolság a késői, illetve a zárt kifutás jele.
WCO_MIN_SHOTS = 4
WCO_LATE_M = 2.5
WCO_TIGHT_M = 1.2


def wing_closeouts(match, config=None) -> dict:
    """Szélső-kifutás: IDŐBEN ÉRNEK-E KI a szélső lövéseire.

    A poszt szerinti kapott gólok (conceded_by_role) azt mondják meg,
    a szélsők ellen szivárognak-e — ez azt, MIÉRT: az ellenfél
    szélső-posztú lövőinek lövéseinél megmérjük, milyen messze volt a
    legközelebbi védő a lövés pillanatában. A nagy átlagos távolság
    késői kifutást jelent — a szélső kényelmesen, teljes szögből lő.

    Edzőileg: a későn kifutó fal ellen a széljáték ingyen terem —
    gyors oldalváltásokkal oda kell hordani a labdát; a szélsőt zárt
    fal ellen viszont a szélső-bejátszás zsákutca, a szélre húzott
    védelem mögött a beálló szabadul fel.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal): {"shots", "sum_m",
    "avg_m", "verdict"} — az avg_m/verdict None WCO_MIN_SHOTS alatt;
    a verdict "későn érnek ki a szélre" / "zárják a szélsőt" / None.
    """
    import math

    from .event_detection import EventType, detect_shots
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    by_t = {f.t: f for f in match.frames}
    posts = estimate_positions(match, config)
    wings = {side: {tid for tid, r in posts.get(side, {}).items()
                    if r["poszt"] == "szélső"}
             for side in ("home", "away")}

    acc = {"home": [0, 0.0], "away": [0, 0.0]}
    for e in detect_shots(match, config):
        if e.type not in (EventType.SHOT, EventType.GOAL):
            continue
        if e.player_id is None or e.player_id not in wings[e.team.value]:
            continue
        f = by_t.get(e.t)
        if f is None:
            continue
        shooter = next((p for p in f.players
                        if p.track_id == e.player_id), None)
        if shooter is None:
            continue
        deff = "away" if e.team.value == "home" else "home"
        dists = [math.hypot(p.x - shooter.x, p.y - shooter.y)
                 for p in f.players
                 if p.team.value == deff and p.role != "kapus"]
        if not dists:
            continue
        acc[deff][0] += 1
        acc[deff][1] += min(dists)

    out: dict = {}
    for side in ("home", "away"):
        n, total = acc[side]
        rec = {"shots": n, "sum_m": round(total, 1), "avg_m": None,
               "verdict": None}
        if n >= WCO_MIN_SHOTS:
            avg = total / n
            rec["avg_m"] = round(avg, 2)
            if avg >= WCO_LATE_M:
                rec["verdict"] = "későn érnek ki a szélre"
            elif avg <= WCO_TIGHT_M:
                rec["verdict"] = "zárják a szélsőt"
        out[side] = rec
    return out


# Blokk-lepattanó: ekkora ablakban keressük a blokk utáni első
# birtokost, ennyi blokk kell az ítélethez, és e feletti / alatti
# visszaszerzés-arány a teljes értékű, illetve a visszahulló blokk jele.
BRC_WINDOW_S = 3.0
BRC_MIN_BLOCKS = 4
BRC_GOOD_PCT = 60.0
BRC_POOR_PCT = 30.0


def block_recoveries(match, config=None) -> dict:
    """Blokk-lepattanó: A BLOKK UTÁN ki szerzi meg a labdát.

    A blokk-arány (blocked_shot_rate) azt méri, mennyi lövést fognak
    meg — ez azt, mit ér a blokk: a blokkolt labda lepattanóját a
    blokk utáni másodpercekben az első azonosított birtokoshoz
    kötjük. A blokk csak akkor teljes értékű, ha a labdát is a
    blokkoló csapat szerzi meg — különben a támadó második esélyt
    kap, sokszor még jobb helyzetből.

    Edzőileg: akinek a blokkja visszahull, annál a blokkolt lövés
    után azonnal újra kell támadni — a lepattanó az övék; aki a
    blokk után a labdát is megszerzi, annál a blokkolt lövés
    egyenlő a labdavesztéssel, és a kontrájuk indul belőle.

    Visszatérés csapatonként (a BLOKKOLÓ oldal): {"blocks",
    "recovered", "rec_pct", "verdict"} — a rec_pct/verdict None
    BRC_MIN_BLOCKS mért blokk alatt; a verdict "a blokk után a labdát
    is megszerzik" / "a blokkjaik visszahullanak" / None.
    """
    from .decisions import ball_holder
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = round(BRC_WINDOW_S * fps)
    idx_of = {f.t: i for i, f in enumerate(match.frames)}
    blocks = detect_blocks(match, config)

    out: dict = {}
    for side in ("home", "away"):
        measured = 0
        recovered = 0
        for ev in blocks[side]["events"]:
            i0 = idx_of.get(ev["t"])
            if i0 is None:
                continue
            for j in range(i0 + 1, min(len(match.frames) - 2,
                                       i0 + 1 + win)):
                h = ball_holder(match.frames[j], config)
                if h is None:
                    continue
                # Csak megült labda: a röptében elsuhanó lepattanó
                # nem birtoklás — két kockával később is nála legyen.
                h2 = ball_holder(match.frames[j + 2], config)
                if h2 is None or h2.track_id != h.track_id:
                    continue
                measured += 1
                if h.team.value == side:
                    recovered += 1
                break
        rec = {"blocks": measured, "recovered": recovered,
               "rec_pct": None, "verdict": None}
        if measured >= BRC_MIN_BLOCKS:
            pct = 100.0 * recovered / measured
            rec["rec_pct"] = round(pct, 1)
            if pct >= BRC_GOOD_PCT:
                rec["verdict"] = "a blokk után a labdát is megszerzik"
            elif pct <= BRC_POOR_PCT:
                rec["verdict"] = "a blokkjaik visszahullanak"
        out[side] = rec
    return out


# Lefogott lövők: a blokk előtt legfeljebb ennyi másodperccel korábbi
# labdabirtokos számít a lefogott lövőnek; ennyi lefogott lövés kell
# az ítélethez, és e feletti részarány emeli ki az egy embert.
BSH_LOOKBACK_S = 1.0
BSH_MIN_BLOCKED = 4
BSH_TOP_SHARE = 50.0


def blocked_shooters(match, config=None) -> dict:
    """Lefogott lövők: KINEK A LÖVÉSÉT viszi el rendre a fal.

    A falba lövés (blocked_shot_rate) a csapat-tünetet méri — ez a
    személyt: minden blokk-eseménynél visszakeressük, ki volt a lövő
    (a blokk előtti utolsó támadó labdabirtokos), és játékosonként
    számoljuk, kinek a lövése akadt el.

    Edzőileg kétirányú: az ellenfél kiemelt lefogott lövője ellen
    MEGÉRI falban maradni — az ő lövését a fal elviszi, nem kell rá
    kifutni; a saját sokat lefogott lövőnknek pedig lövő-variáció
    kell (lövőcsel, elhajlás, áttolt lövés), nem több ugyanolyan
    lövés.

    Visszatérés csapatonként (a TÁMADÓ csapaté): {"blocked",
    "shooters": [{"player_id", "jersey", "blocked"}], "top":
    {"player_id", "jersey", "blocked", "share_pct"} | None} — a
    shooters csökkenő; a "top" akkor van kitöltve, ha legalább
    BSH_MIN_BLOCKED lefogott lövés kötődik játékoshoz, a vezető
    részaránya eléri a BSH_TOP_SHARE-t, és nincs holtverseny.
    """
    from .decisions import ball_holder
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    lookback = max(1, round(BSH_LOOKBACK_S * fps))
    idx_of = {f.t: i for i, f in enumerate(match.frames)}
    blocks = detect_blocks(match, config)

    jersey: dict[int, int] = {}
    acc: dict = {"home": {}, "away": {}}
    for side in ("home", "away"):
        atk = "away" if side == "home" else "home"
        for ev in blocks[side]["events"]:
            i0 = idx_of.get(ev["t"])
            if i0 is None:
                continue
            shooter = None
            for j in range(i0, max(-1, i0 - lookback - 1), -1):
                holder = ball_holder(match.frames[j], config)
                # A röptében lévő labda a blokkoló mellett is
                # "birtokosnak" látszhat — a védő-kockákat átlépjük.
                if holder is None or holder.team.value != atk:
                    continue
                shooter = holder
                break
            if shooter is None:
                continue
            if shooter.jersey_number is not None:
                jersey.setdefault(shooter.track_id,
                                  shooter.jersey_number)
            acc[atk][shooter.track_id] = (
                acc[atk].get(shooter.track_id, 0) + 1)

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": tid, "jersey": jersey.get(tid),
                 "blocked": n}
                for tid, n in sorted(acc[side].items(),
                                     key=lambda kv: -kv[1])]
        total = sum(r["blocked"] for r in rows)
        top = None
        if total >= BSH_MIN_BLOCKED and rows:
            share = 100.0 * rows[0]["blocked"] / total
            tie = (len(rows) > 1
                   and rows[1]["blocked"] == rows[0]["blocked"])
            if share >= BSH_TOP_SHARE and not tie:
                top = {**rows[0], "share_pct": round(share, 1)}
        out[side] = {"blocked": total, "shooters": rows, "top": top}
    return out


# Falba lövő posztok: ennyi poszthoz kötött lefogott lövés kell az
# ítélethez, és e feletti részarány emeli ki a posztot.
BBR_MIN_BLOCKED = 4
BBR_SHARE = 50.0


def blocked_by_role(match, config=None) -> dict:
    """Falba lövő posztok: MELYIK POSZTJUK lő rendre a falba.

    A lefogott lövők (blocked_shooters) a nevet adják — ez a posztot:
    a lefogott lövőket a poszt-becsléshez kötjük, így akkor is
    látszik a minta, ha a nevek meccsről meccsre cserélődnek.

    Edzőileg: ha az átlövőik akadnak el a falban, a fal magasan
    tartása többet ér, mint a kilépés; ha a beállójuk, az elé állás
    után a lövő-kar zárása is jár; ha a szélsőjük lő falba, a szög
    már zárva van — elég tartani.

    Visszatérés csapatonként (a TÁMADÓ csapaté): {"blocked"
    (poszthoz kötött lefogott lövések), "roles": {poszt: darab},
    "top": {"poszt", "blocked", "share_pct"} | None} — a "top" akkor
    van kitöltve, ha legalább BBR_MIN_BLOCKED poszthoz kötött
    lefogott lövés van, a vezető poszt részaránya eléri a
    BBR_SHARE-t, és nincs holtverseny.
    """
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    shooters = blocked_shooters(match, config)
    out: dict = {side: {"blocked": 0, "roles": {}, "top": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in shooters[side]["shooters"]:
            info = roles.get(side, {}).get(row["player_id"])
            if info is None:
                continue
            rec["blocked"] += row["blocked"]
            poszt = info["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["blocked"])
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        items = list(rec["roles"].items())
        if rec["blocked"] >= BBR_MIN_BLOCKED and items:
            poszt, n = items[0]
            share = 100.0 * n / rec["blocked"]
            tie = len(items) > 1 and items[1][1] == n
            if share >= BBR_SHARE and not tie:
                rec["top"] = {"poszt": poszt, "blocked": n,
                              "share_pct": round(share, 1)}
    return out


# Kettőző emberek: ennyi kettőzött kocka kell egy csapathoz, és e
# feletti részarány emeli ki az egy kettőző embert.
DTP_MIN_FRAMES = 50
DTP_TOP_SHARE = 40.0


def doubling_defenders(match, config=None) -> dict:
    """Kettőző emberek: KI JÖN MÁSODIKNAK a labdásra.

    A kettőzés-réteg (double_teams) azt méri, kettőznek-e — ez azt,
    KI: a kettőzött kockákon a labdáshoz második legközelebbi védőt
    jegyezzük fel. Ha a kettőzés mindig ugyanattól az embertől jön,
    a minta kiszámítható — és a kettőző ŐRZÖTTJE az, aki üresen
    marad.

    Edzőileg: az ellenfél kiemelt kettőzője ellen előre kijelölhető
    a kijátszás — a kettőzés pillanatában az ő embere felé megy az
    első passz, mert ő szabadult fel; a saját kettőzésünket pedig
    forgatni kell, hogy ne legyen kiolvasható.

    Visszatérés csapatonként (a KETTŐZŐ, védekező oldal):
    {"doubled_frames", "doublers": [{"player_id", "jersey",
    "frames"}], "top": {"player_id", "jersey", "frames",
    "share_pct"} | None} — a doublers csökkenő; a "top" akkor van
    kitöltve, ha legalább DTP_MIN_FRAMES kettőzött kocka van, a
    vezető részaránya eléri a DTP_TOP_SHARE-t, és nincs holtverseny.
    """
    import math

    from .decisions import ball_holder
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    jersey: dict[int, int] = {}
    acc: dict = {"home": {}, "away": {}}
    totals = {"home": 0, "away": 0}
    for f in match.frames:
        holder = ball_holder(f, config)
        if holder is None or holder.team is None:
            continue
        defender = "away" if holder.team.value == "home" else "home"
        near = sorted(
            ((math.hypot(p.x - holder.x, p.y - holder.y), p)
             for p in f.players
             if p.team is not None and p.team != holder.team
             and p.role != "kapus"
             and math.hypot(p.x - holder.x, p.y - holder.y)
             <= DOUBLE_TEAM_M),
            key=lambda dp: dp[0])
        if len(near) < 2:
            continue
        second = near[1][1]
        if second.jersey_number is not None:
            jersey.setdefault(second.track_id, second.jersey_number)
        totals[defender] += 1
        acc[defender][second.track_id] = (
            acc[defender].get(second.track_id, 0) + 1)

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": tid, "jersey": jersey.get(tid),
                 "frames": n}
                for tid, n in sorted(acc[side].items(),
                                     key=lambda kv: -kv[1])]
        top = None
        if totals[side] >= DTP_MIN_FRAMES and rows:
            share = 100.0 * rows[0]["frames"] / totals[side]
            tie = (len(rows) > 1
                   and rows[1]["frames"] == rows[0]["frames"])
            if share >= DTP_TOP_SHARE and not tie:
                top = {**rows[0], "share_pct": round(share, 1)}
        out[side] = {"doubled_frames": totals[side],
                     "doublers": rows, "top": top}
    return out


# Átvert védők: a kapott gólnál a lövőhöz ennél közelebb álló védő
# számít átvertnek; ennyi hozzárendelt gól kell az ítélethez, és e
# feletti részarány emeli ki az egy embert.
BTN_MAX_DIST_M = 3.5
BTN_MIN_GOALS = 4
BTN_TOP_SHARE = 40.0


def beaten_defenders(match, config=None) -> dict:
    """Átvert védők: KI MÖGÖTT esnek a kapott gólok.

    Az őrzési párok (marking_pairs) azt mérik, ki kit fog — ez azt,
    ki veszíti el a párharcot, amikor számít: minden kapott gólnál a
    lövő helyéhez legközelebbi (BTN_MAX_DIST_M-en belüli) védő
    mezőnyjátékost jegyezzük fel átvertként. A radiuson kívüli lövő
    fedezetlen volt — az nem párharc-vereség, hanem szerkezeti hiba.

    Edzőileg kétirányú: az ellenfél sokat átvert védője a megtámadható
    ember — rá kell vinni az 1v1-et, elzárással hozzá terelni a
    lövőt; a saját sokat átvert védőnk mellé pedig segítés kell
    (besegítő váltás, kettőzés-készenlét), vagy párharc-edzés.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal): {"goals" (védőhöz
    rendelt kapott gólok), "free" (fedezetlen kapott gólok),
    "defenders": [{"player_id", "jersey", "beaten"}], "top":
    {"player_id", "jersey", "beaten", "share_pct"} | None} — a
    defenders csökkenő; a "top" akkor van kitöltve, ha legalább
    BTN_MIN_GOALS védőhöz rendelt gól van, a vezető részaránya
    eléri a BTN_TOP_SHARE-t, és nincs holtverseny.
    """
    import math

    from .tactics import TacticsConfig
    from .xg import match_xg

    config = config or TacticsConfig()
    idx_of = {f.t: i for i, f in enumerate(match.frames)}

    jersey: dict[int, int] = {}
    acc: dict = {"home": {}, "away": {}}
    free = {"home": 0, "away": 0}
    for sh in match_xg(match, config).get("shots", []):
        if sh.get("outcome") != "goal":
            continue
        deff = "away" if sh["team"] == "home" else "home"
        i0 = idx_of.get(sh["t"])
        if i0 is None:
            continue
        best = None
        for p in match.frames[i0].players:
            if p.team.value != deff or p.role == "kapus":
                continue
            d = math.hypot(p.x - sh["x"], p.y - sh["y"])
            if d <= BTN_MAX_DIST_M and (best is None or d < best[0]):
                best = (d, p)
        if best is None:
            free[deff] += 1
            continue
        p = best[1]
        if p.jersey_number is not None:
            jersey.setdefault(p.track_id, p.jersey_number)
        acc[deff][p.track_id] = acc[deff].get(p.track_id, 0) + 1

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": tid, "jersey": jersey.get(tid),
                 "beaten": n}
                for tid, n in sorted(acc[side].items(),
                                     key=lambda kv: -kv[1])]
        total = sum(r["beaten"] for r in rows)
        top = None
        if total >= BTN_MIN_GOALS and rows:
            share = 100.0 * rows[0]["beaten"] / total
            tie = (len(rows) > 1
                   and rows[1]["beaten"] == rows[0]["beaten"])
            if share >= BTN_TOP_SHARE and not tie:
                top = {**rows[0], "share_pct": round(share, 1)}
        out[side] = {"goals": total, "free": free[side],
                     "defenders": rows, "top": top}
    return out
