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
    [{"player_id","blocks"}]}} — a kulcs a BLOKKOLÓ (védekező) csapat.
    """
    from ..models.tracking import Team
    from .event_detection import _attacking_team_for_goal
    from .tactics import COURT_LENGTH_M

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    frames = match.frames
    out = {side: {"blocks": 0, "blockers": {}} for side in ("home", "away")}
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
                last_block_t = f1.t

    for rec in out.values():
        rec["blockers"] = [{"player_id": pid, "blocks": n}
                           for pid, n in sorted(rec["blockers"].items(),
                                                key=lambda kv: -kv[1])]
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
