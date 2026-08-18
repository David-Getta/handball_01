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


# Blokk-fáradás: félidőnként ennyi ellenfél lövés-kísérlet (blokk +
# kaputra jutott lövés) kell az ítélethez, és ekkora (százalékpontos)
# esés számít érdeminek.
BLF_MIN_SHOTS = 5
BLF_GAP_PP = 10.0


def block_fade(match, config=None) -> dict:
    """Blokk-fáradás: ELFOGY-E a blokk-munka a második félidőre.

    A blokkolt lövések rétege a darabszámot adja — ez a KITARTÁST:
    félidőnként elosztja a blokkjaikat az ellenfél lövés-
    kísérleteivel (blokk + kaputra jutott lövés), így a mennyiség
    nem torzít, ha az egyik félidőben többet lőttek rájuk.

    Edzőileg a blokk tiszta akarat-munka: ha a második félidőre
    érdemben visszaesik, a hajrában a távoli lövés ellenük szinte
    ingyen van — az utolsó húsz percben tudatosan az átlövésre kell
    építeni. Saját csapatra: a blokkoló emberek pihentetése és a
    lábmunka-állóképesség az edzés-téma, mert a blokk elfogyása nem
    taktika, hanem kondíció kérdése.

    Visszatérés csapatonként (a BLOKKOLÓ oldal): {"fh_blocks",
    "fh_shots", "sh_blocks", "sh_shots", "fh_pct", "sh_pct",
    "gap_pp", "verdict"} — a pct a blokkok aránya a félidő
    lövés-kísérleteihez (blokk + lövés) képest; a pct/gap/verdict
    None, ha nincs félidő-jel, vagy valamelyik félidőben kevés
    (BLF_MIN_SHOTS alatti) a lövés-kísérlet.
    """
    from .event_detection import EventType, detect_shots
    from .halftime import detect_halftime
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    empty = {"fh_blocks": 0, "fh_shots": 0, "sh_blocks": 0,
             "sh_shots": 0, "fh_pct": None, "sh_pct": None,
             "gap_pp": None, "verdict": None}
    out = {side: dict(empty) for side in ("home", "away")}
    ht = detect_halftime(match)
    if ht is None:
        return out

    blk = detect_blocks(match, config)
    for side in ("home", "away"):
        for ev in blk[side]["events"]:
            key = "fh_blocks" if ev["t"] <= ht else "sh_blocks"
            out[side][key] += 1

    for e in detect_shots(match, config):
        if e.type not in (EventType.SHOT, EventType.GOAL):
            continue
        atk = getattr(e.team, "value", e.team)
        deff = "away" if atk == "home" else "home"
        key = "fh_shots" if e.t <= ht else "sh_shots"
        out[deff][key] += 1

    for rec in out.values():
        fh_try = rec["fh_shots"] + rec["fh_blocks"]
        sh_try = rec["sh_shots"] + rec["sh_blocks"]
        if fh_try >= BLF_MIN_SHOTS and sh_try >= BLF_MIN_SHOTS:
            fh = 100.0 * rec["fh_blocks"] / fh_try
            sh = 100.0 * rec["sh_blocks"] / sh_try
            rec["fh_pct"] = round(fh, 1)
            rec["sh_pct"] = round(sh, 1)
            rec["gap_pp"] = round(sh - fh, 1)
            if fh - sh >= BLF_GAP_PP:
                rec["verdict"] = (
                    f"elfogy a blokk-munkájuk ({fh:.0f}% → {sh:.0f}% "
                    "blokk-arány) — a hajrában az átlövés ellenük "
                    "szinte ingyen van: az utolsó húsz percben "
                    "tudatosan a távoli lövésre kell építeni")
            elif sh - fh >= BLF_GAP_PP:
                rec["verdict"] = (
                    f"a hajrára nő a blokk-munkájuk ({fh:.0f}% → "
                    f"{sh:.0f}% blokk-arány) — a végén nem az "
                    "átlövés, hanem a bejátszás és a kiugratás a "
                    "megoldás ellenük")
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


# Védekezési formáció: a fal ALAKJA a mélység-eloszlásból. Ennyi mért védő
# kell egy kocka megítéléséhez, ekkora rés választ el két védő-szintet,
# ennyi értékelhető kocka kell az ítélethez, és e feletti részarány teszi a
# leggyakoribb alakot a csapat formációjává.
DFORM_MIN_DEFENDERS = 5
DFORM_LEVEL_GAP_M = 1.5
DFORM_MIN_FRAMES = 100
DFORM_SHARE_PCT = 50.0


def defensive_formation(match, config=None) -> dict:
    """Védekezési formáció: 6-0, 5-1 vagy 3-2-1 jellegű-e a faluk.

    A vonal-magasság az ÁTLAGOS mélységet méri, ez az ALAKOT: felállt
    védekezésnél a mezőnyvédők saját kaputól mért mélységeit szintekre
    bontjuk (DFORM_LEVEL_GAP_M-nél nagyobb rés = új szint). Egy szint =
    lapos fal (6-0); két szint egyetlen kitolt védővel = 5-1; három vagy
    több szint = 3-2-1 jelleg.

    Edzőileg más-más nyitja őket: a 6-0 ellen a távoli lövés és az
    átadás-ritmus a fegyver (a fal nem lép ki, be kell húzni); az 5-1 ellen
    a kitolt védő MÖGÖTTI tér — mellette indított kettős elzárás, a beálló
    az ő háta mögé; a 3-2-1 ellen a szélek és a gyors oldalváltás (a
    lépcsős fal keresztmozgásra lassú).

    Visszatérés csapatonként (a védekező csapaté):
      {"frames", "counts": {alak: kocka}, "formation", "share_pct"} — a
    "formation" a leggyakoribb alak, ha legalább DFORM_MIN_FRAMES
    értékelhető kocka van és a részaránya eléri a DFORM_SHARE_PCT-t
    (egyébként None).
    """
    from ..models.tracking import Team
    from .decisions import ball_holder
    from .tactics import COURT_LENGTH_M, TacticsConfig

    config = config or TacticsConfig()
    half = COURT_LENGTH_M / 2.0
    counts = {Team.HOME: {}, Team.AWAY: {}}
    frames = {Team.HOME: 0, Team.AWAY: 0}
    for f in match.frames:
        holder = ball_holder(f, config)
        if holder is None:
            continue
        deff = Team.AWAY if holder.team == Team.HOME else Team.HOME
        own_x = config.own_goal_x(deff)
        # Csak felállt védekezés: a labdás a védekező csapat térfelén van.
        if abs(holder.x - own_x) > half:
            continue
        depths = sorted(abs(p.x - own_x) for p in f.players
                        if p.team == deff and p.role != "kapus"
                        and abs(p.x - own_x) <= half)
        if len(depths) < DFORM_MIN_DEFENDERS:
            continue
        # Szintekre bontás: a rendezett mélységekben a nagy rés új szintet
        # nyit; a legutolsó szint a legelöl álló (kitolt) védőké.
        levels = [[depths[0]]]
        for d in depths[1:]:
            if d - levels[-1][-1] >= DFORM_LEVEL_GAP_M:
                levels.append([d])
            else:
                levels[-1].append(d)
        if len(levels) == 1:
            shape = "6-0 (lapos fal)"
        elif len(levels) >= 3:
            shape = "3-2-1 (lépcsős)"
        elif len(levels[-1]) == 1:
            shape = "5-1 (kitolt védő)"
        else:
            shape = "kétszintű (vegyes)"
        counts[deff][shape] = counts[deff].get(shape, 0) + 1
        frames[deff] += 1

    out = {}
    for team in (Team.HOME, Team.AWAY):
        n = frames[team]
        tally = dict(sorted(counts[team].items(), key=lambda kv: -kv[1]))
        formation, share = None, None
        if n >= DFORM_MIN_FRAMES and tally:
            top_shape, top_n = next(iter(tally.items()))
            share = round(100.0 * top_n / n, 1)
            if share >= DFORM_SHARE_PCT:
                formation = top_shape
        out[team.value] = {"frames": n, "counts": tally,
                           "formation": formation, "share_pct": share}
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


# Eltűnő védő: első félidei védő-akciók után a másodikban csend.
FDD_MIN_FH = 3   # ennyi első félidei védő-akció (szerzés+blokk) kell
FDD_MAX_SH = 1   # a második félidőben legfeljebb ennyi = leállt


def fading_defenders(match, config=None) -> dict:
    """Eltűnő védő: KI viszi a védekezést az első félidőben — és áll le.

    Az eltűnő ember (fading_scorers) védő-oldali párja: játékosonként
    számoljuk a védő-akciókat (labdaszerzés + blokk) félidőnként, és
    megkeressük, akinél az első félidei motor a másodikra leáll. A
    védekezés-fáradás így nem csapat-átlagban, hanem néven nevezve
    látszik: kinek a zónája nyílik ki a hajrára.

    Edzőileg: az ellenfél kifulladó védő-motorja ellen a második
    félidőben az Ő zónáján át kell támadni — az első félidei képe
    alapján még kerülnék, pedig addigra már nem ér oda; a saját
    oldalon a védő-motor rotációja (tervezett pihenő a szünet körül)
    az edzés-téma.

    Visszatérés csapatonként: {"players": [{"player_id", "fh",
    "sh"}] (fh szerint csökkenő), "top", "verdict"} — a verdict
    "a(z) N. viszi a védekezést az első félidőben (F szerzés+blokk),
    a másodikban leáll (S)"; felismert szünet nélkül None.
    """
    from .halftime import detect_halftime

    config = config or TacticsConfig()
    out = {side: {"players": [], "top": None, "verdict": None}
           for side in ("home", "away")}
    ht = detect_halftime(match)
    if ht is None:
        return out
    tally: dict = {"home": {}, "away": {}}

    def add(side, pid, t):
        rec = tally[side].setdefault(pid, {"fh": 0, "sh": 0})
        rec["fh" if t <= ht else "sh"] += 1

    bw = ball_winners(match, config)
    blk = detect_blocks(match, config)
    for side in ("home", "away"):
        for e in bw[side]["ts"]:
            add(side, e["player_id"], e["t"])
        for e in blk[side]["events"]:
            if e.get("player_id") is not None:
                add(side, e["player_id"], e["t"])
    for side in ("home", "away"):
        players = [{"player_id": pid, **rec}
                   for pid, rec in tally[side].items()]
        players.sort(key=lambda r: (-r["fh"], r["sh"]))
        out[side]["players"] = players
        for r in players:
            if r["fh"] >= FDD_MIN_FH and r["sh"] <= FDD_MAX_SH:
                out[side]["top"] = r["player_id"]
                out[side]["verdict"] = (
                    f"a(z) {r['player_id']}. viszi a védekezést az "
                    f"első félidőben ({r['fh']} szerzés+blokk), a "
                    f"másodikban leáll ({r['sh']})")
                break
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


# Zavartalan előkészítők: a gólpassz pillanatában ennél közelebbi védő
# számít nyomásnak; ennyi gólpasszos kapott gól kell az ítélethez, és
# e feletti zavartalan arány a laza, ez alatti a rálépős védekezés
# jele.
UPA_PRESS_M = 2.0
UPA_MIN_ASSISTED = 5
UPA_LOOSE_PCT = 60.0
UPA_TIGHT_PCT = 25.0


def unpressured_assists(match, config=None) -> dict:
    """Zavartalan előkészítők: HAGYJÁK-E DOLGOZNI a gólpassz-adót.

    Az átvert védők a lövő párharcát nézik — ez az eggyel korábbi
    pillanatot: a kapott gólpasszos góloknál volt-e védő
    (UPA_PRESS_M-en belül) a kiadó mellett a passz pillanatában. A
    gól ritkán a lövésnél dől el: ha az előkészítő zavartalanul
    mérhette ki a labdát, a hiba a passzsáv-nyomás hiánya.

    Edzőileg: aki zavartalanul hagyja az előkészítőt, annál a
    gólpassz-adóra kell lépni — a kiadás pillanatában kéz a
    passzsávba, test a kiadóra; aki rálép, annál a lövő-oldali
    párharcokon múlik a védekezés.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal): {"assisted"
    (gólpasszos kapott gólok), "unpressured", "loose_pct",
    "verdict"} — a loose_pct/verdict None UPA_MIN_ASSISTED alatt; a
    verdict "az előkészítőt hagyják dolgozni" / "az előkészítőre
    rálépnek" / None.
    """
    import math

    from .decisions import detect_passes
    from .event_detection import EventType, detect_events
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    idx_of = {f.t: i for i, f in enumerate(match.frames)}
    passes = detect_passes(match, config)

    out = {side: {"assisted": 0, "unpressured": 0, "loose_pct": None,
                  "verdict": None} for side in ("home", "away")}
    for e in detect_events(match, config):
        if e.type != EventType.GOAL or e.player_id is None:
            continue
        aid = (e.detail or {}).get("assist_id")
        if aid is None:
            continue
        pe = None
        for cand in passes:
            if (cand.team == e.team and cand.passer_id == aid
                    and cand.receiver_id == e.player_id
                    and cand.t <= e.t
                    and (pe is None or cand.t > pe.t)):
                pe = cand
        if pe is None or pe.passer_pos is None:
            continue
        i0 = idx_of.get(pe.t)
        if i0 is None:
            continue
        deff = "away" if e.team.value == "home" else "home"
        pressured = any(
            p.team.value == deff and p.role != "kapus"
            and math.hypot(p.x - pe.passer_pos.x,
                           p.y - pe.passer_pos.y) <= UPA_PRESS_M
            for p in match.frames[i0].players)
        rec = out[deff]
        rec["assisted"] += 1
        if not pressured:
            rec["unpressured"] += 1

    for side in ("home", "away"):
        rec = out[side]
        if rec["assisted"] >= UPA_MIN_ASSISTED:
            pct = 100.0 * rec["unpressured"] / rec["assisted"]
            rec["loose_pct"] = round(pct, 1)
            if pct >= UPA_LOOSE_PCT:
                rec["verdict"] = "az előkészítőt hagyják dolgozni"
            elif pct <= UPA_TIGHT_PCT:
                rec["verdict"] = "az előkészítőre rálépnek"
    return out


# Folyosó-gólok: a lövő és a kapu-közép közti szakasztól ennél
# közelebb álló védő zárja a folyosót; ennyi kapott gól kell az
# ítélethez, és e feletti / alatti nyitott arány a nyitott folyosók,
# illetve a zárt fal mögötti gólok jele.
CRG_LANE_M = 1.5
CRG_MIN_GOALS = 5
CRG_OPEN_PCT = 50.0
CRG_CLOSED_PCT = 20.0


def corridor_goals(match, config=None) -> dict:
    """Folyosó-gólok: NYITOTT FOLYOSÓN kapják-e a gólokat.

    Az átvert védők a lövő melletti párharcot nézik — ez a lövés
    útját: a kapott góloknál volt-e VALAKI a lövő és a kapu-közép
    közti sávban (a lövésvonaltól CRG_LANE_M-en belül). A nyitott
    folyosós gól a fal-zárás és a visszazárás hibája; a zárt fal
    mögött is bekapott gól a blokk-kéz és a kapus kérdése.

    Edzőileg: aki nyitott folyosókon kapja a gólokat, annál a
    betörést és a gyors átmenetet kell erőltetni — a fal nem ér oda;
    aki zárt fal mögött is bekapja, annál a lövés ereje/elhelyezése
    ütötte át a rendszert — ellene a türelmes, kimozgató játék kell,
    nem a rá-lövöldözés.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal): {"goals", "open",
    "open_pct", "verdict"} — az open_pct/verdict None CRG_MIN_GOALS
    alatt; a verdict "nyitott folyosókon kapják a gólokat" / "zárt
    fal mögött is bekapják" / None.
    """
    import math

    from ..models.tracking import Team
    from .calibration import COURT_WIDTH_M
    from .tactics import TacticsConfig
    from .xg import match_xg

    config = config or TacticsConfig()
    idx_of = {f.t: i for i, f in enumerate(match.frames)}

    def _lane_dist(px, py, ax, ay, bx, by):
        # pont távolsága az (a→b) szakasztól
        vx, vy = bx - ax, by - ay
        L2 = vx * vx + vy * vy
        if L2 <= 0:
            return math.hypot(px - ax, py - ay)
        t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / L2))
        return math.hypot(px - (ax + t * vx), py - (ay + t * vy))

    out = {side: {"goals": 0, "open": 0, "open_pct": None,
                  "verdict": None} for side in ("home", "away")}
    for sh in match_xg(match, config).get("shots", []):
        if sh.get("outcome") != "goal":
            continue
        deff = "away" if sh["team"] == "home" else "home"
        i0 = idx_of.get(sh["t"])
        if i0 is None:
            continue
        goal_x = config.attacks_toward_x(Team(sh["team"]))
        gy = COURT_WIDTH_M / 2.0
        blocked = any(
            p.team.value == deff and p.role != "kapus"
            and _lane_dist(p.x, p.y, sh["x"], sh["y"], goal_x, gy)
            <= CRG_LANE_M
            for p in match.frames[i0].players)
        rec = out[deff]
        rec["goals"] += 1
        if not blocked:
            rec["open"] += 1

    for side in ("home", "away"):
        rec = out[side]
        if rec["goals"] >= CRG_MIN_GOALS:
            pct = 100.0 * rec["open"] / rec["goals"]
            rec["open_pct"] = round(pct, 1)
            if pct >= CRG_OPEN_PCT:
                rec["verdict"] = "nyitott folyosókon kapják a gólokat"
            elif pct <= CRG_CLOSED_PCT:
                rec["verdict"] = "zárt fal mögött is bekapják"
    return out


# Bontó tempó: a kapott gól előtti ennyi másodperc passzait számoljuk;
# ennyi kapott gól kell az ítélethez, és e feletti / alatti
# passz-átlag a járatással szétszedett, illetve az egyéni akciókból
# kapott gólok jele.
CTM_WINDOW_S = 8.0
CTM_MIN_GOALS = 5
CTM_FAST_AVG = 3.0
CTM_SLOW_AVG = 1.5


def conceded_tempo(match, config=None) -> dict:
    """Bontó tempó: A JÁRATÁS SZEDI-E SZÉT a védekezésüket.

    A passz-lánc a támadó oldal türelmét méri — ez a kapott gólok
    előzményét: az utolsó CTM_WINDOW_S másodperc passzainak átlagos
    számát a kapott gólok előtt. Akit a pörgő járatás bont meg, annál
    a fal a váltásoknál nyílik szét; akit egyéni akciókból lőnek
    szét, ott a párharc-védekezés az igazi gond.

    Edzőileg: a járatással szétszedhető csapat ellen tempót KELL
    emelni — minél több oldalváltás és passz, annál előbb nyílik a
    rés; az egyéni akciókból bekapó ellen az 1v1-ben erős embereket
    kell rájuk engedni, a hosszú járatás csak időt ad nekik
    rendeződni.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal): {"goals",
    "passes_sum", "avg_passes", "verdict"} — az avg_passes/verdict
    None CTM_MIN_GOALS alatt; a verdict "a járatás szedi szét őket" /
    "egyéni akciókból kapják a gólokat" / None.
    """
    from .decisions import detect_passes
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = round(CTM_WINDOW_S * fps)
    passes = detect_passes(match, config)

    out = {side: {"goals": 0, "passes_sum": 0, "avg_passes": None,
                  "verdict": None} for side in ("home", "away")}
    for e in detect_shots(match, config):
        if e.type != EventType.GOAL:
            continue
        deff = "away" if e.team.value == "home" else "home"
        n = sum(1 for pe in passes
                if pe.team == e.team and e.t - win <= pe.t <= e.t)
        rec = out[deff]
        rec["goals"] += 1
        rec["passes_sum"] += n

    for side in ("home", "away"):
        rec = out[side]
        if rec["goals"] >= CTM_MIN_GOALS:
            avg = rec["passes_sum"] / rec["goals"]
            rec["avg_passes"] = round(avg, 1)
            if avg >= CTM_FAST_AVG:
                rec["verdict"] = "a járatás szedi szét őket"
            elif avg <= CTM_SLOW_AVG:
                rec["verdict"] = "egyéni akciókból kapják a gólokat"
    return out


# Lendület-gólok: a gól pillanatában e feletti sebességű lövő számít
# mozgásból érkezőnek; ennyi mért kapott gól kell az ítélethez, és e
# feletti / alatti mozgásos arány a bekísérés-hiba, illetve az
# állóhelyből tisztán lőtt gólok jele.
CGM_RUN_MS = 2.5
CGM_MIN_GOALS = 5
CGM_RUN_PCT = 55.0
CGM_SET_PCT = 25.0


def conceded_momentum(match, config=None) -> dict:
    """Lendület-gólok: MOZGÁSBÓL ÉRKEZŐ lövőktől kapják-e a gólokat.

    A gól-pillanati család sebesség-tagja: a kapott góloknál a lövő
    mozgás-sebességét mérjük a lövés pillanata körül. A lendületből
    érkező lövő gólja bekísérés-hiba — az embert senki nem vette fel
    időben; az állóhelyből lőtt gól tiszta felállt lövés — ott a
    kilépés (vagy a blokk-kéz) hiányzott.

    Edzőileg: aki mozgásból kapja a gólokat, az ellen a betörőt és a
    befutót kell játszani — a bekísérésük késik; aki állóból kapja,
    annak a fala enged tiszta lövést — ellene a nyugodt, kivárt
    átlövés is termel.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal): {"goals" (mért
    kapott gólok), "running", "run_pct", "verdict"} — a
    run_pct/verdict None CGM_MIN_GOALS alatt; a verdict "mozgásból
    kapják a gólokat" / "állóhelyből is bekapják" / None.
    """
    import math

    from .tactics import TacticsConfig
    from .xg import match_xg

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    idx_of = {f.t: i for i, f in enumerate(match.frames)}

    out = {side: {"goals": 0, "running": 0, "run_pct": None,
                  "verdict": None} for side in ("home", "away")}
    for sh in match_xg(match, config).get("shots", []):
        if sh.get("outcome") != "goal" or sh.get("player_id") is None:
            continue
        deff = "away" if sh["team"] == "home" else "home"
        i0 = idx_of.get(sh["t"])
        if i0 is None or i0 < 2 or i0 + 2 >= len(match.frames):
            continue
        p_before = next((p for p in match.frames[i0 - 2].players
                         if p.track_id == sh["player_id"]), None)
        p_after = next((p for p in match.frames[i0 + 2].players
                        if p.track_id == sh["player_id"]), None)
        if p_before is None or p_after is None:
            continue
        speed = (math.hypot(p_after.x - p_before.x,
                            p_after.y - p_before.y) * fps / 4.0)
        rec = out[deff]
        rec["goals"] += 1
        if speed >= CGM_RUN_MS:
            rec["running"] += 1

    for side in ("home", "away"):
        rec = out[side]
        if rec["goals"] >= CGM_MIN_GOALS:
            pct = 100.0 * rec["running"] / rec["goals"]
            rec["run_pct"] = round(pct, 1)
            if pct >= CGM_RUN_PCT:
                rec["verdict"] = "mozgásból kapják a gólokat"
            elif pct <= CGM_SET_PCT:
                rec["verdict"] = "állóhelyből is bekapják"
    return out


# Kettőzés-büntetés: a kettőzött kocka utáni ennyi másodpercen belüli
# kapott gól még a kettőzés számlájára megy; ennyi ilyen gól kell a
# büntetett ítélethez, és ennyi kettőzött kocka a büntetlenül termelő
# kettőzéshez.
DBP_TAIL_S = 3.0
DBP_MIN_GOALS = 2
DBP_MIN_FRAMES = 150


def double_punishment(match, config=None) -> dict:
    """Kettőzés-büntetés: MÖGÉ BETALÁLNAK-E a kettőzésüknek.

    A kettőzés (double_teams) megmondja, jön-e a második védő, a
    kettőző emberek azt, ki — ez az árát: a kettőzött pillanatok
    után közvetlenül (DBP_TAIL_S-en belül) kapott gólokat. A
    kettőzés mindig üresen hagy valakit: van, akinél ezt sosem
    találják meg, és van, akinél a kettőzés rendre gólba kerül.

    Edzőileg: akinek a kettőzése gólba kerül, az ellen a kettőzés-jel
    a támadási jel — az első passz azonnal a felszabadult emberhez,
    és kész a helyzet; a saját, gólba kerülő kettőzésünknél pedig
    vagy gyorsabb a visszazárás, vagy vissza kell fogni a kettőzést.

    Visszatérés csapatonként (a KETTŐZŐ, védekező oldal):
    {"doubled_frames", "conceded_after", "verdict"} — a verdict "a
    kettőzésük gólba kerül" (DBP_MIN_GOALS-tól), "a kettőzésük
    büntetlenül termel" (DBP_MIN_FRAMES-nyi kettőzés, ilyen gól
    nélkül), különben None.
    """
    import math

    from .decisions import ball_holder
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    tail = round(DBP_TAIL_S * fps)
    goals = [(e.t, e.team.value) for e in detect_shots(match, config)
             if e.type == EventType.GOAL]

    doubled_ts = {"home": [], "away": []}
    for f in match.frames:
        holder = ball_holder(f, config)
        if holder is None or holder.team is None:
            continue
        defender = "away" if holder.team.value == "home" else "home"
        near = sum(1 for p in f.players
                   if p.team is not None and p.team != holder.team
                   and p.role != "kapus"
                   and math.hypot(p.x - holder.x, p.y - holder.y)
                   <= DOUBLE_TEAM_M)
        if near >= 2:
            doubled_ts[defender].append(f.t)

    out: dict = {}
    for side, other in (("home", "away"), ("away", "home")):
        ts = doubled_ts[side]
        conceded = 0
        for (gt, tm) in goals:
            if tm != other:
                continue
            if any(0 <= gt - t <= tail for t in ts):
                conceded += 1
        rec = {"doubled_frames": len(ts), "conceded_after": conceded,
               "verdict": None}
        if conceded >= DBP_MIN_GOALS:
            rec["verdict"] = "a kettőzésük gólba kerül"
        elif len(ts) >= DBP_MIN_FRAMES and conceded == 0:
            rec["verdict"] = "a kettőzésük büntetlenül termel"
        out[side] = rec
    return out


# Kilépés-büntetés: a kapott gól előtti pillanatban a fal-vonalnál
# ennyivel előrébb álló védő számít kiugrónak; ennyi kapott gól kell
# az ítélethez, és e feletti arány a kilépés mögé kapott gólok jele.
SOP_AHEAD_M = 3.0
SOP_MIN_GOALS = 5
SOP_PUNISH_PCT = 40.0


def stepout_punishment(match, config=None) -> dict:
    """Kilépés-büntetés: A KILÉPÉSÜK MÖGÉ betalálnak-e.

    A kiugró védő (advanced_defender) megmondja, ki játszik elöl —
    ez az árát: a kapott gólok hányadánál volt a fal-vonalból
    (a védők medián kapu-távolságából) érdemben kiugró védő a gól
    előtti pillanatban. A kilépés mögött mindig rés marad — van,
    akinél ezt sosem játsszák meg, és van, akinél a kiugrás rendre
    gólt ér az ellenfélnek.

    Edzőileg: akinek a kilépése gólba kerül, az ellen a kilépőt kell
    megjátszani — gyors átemelés vagy betörés a helyére, a rés
    bizonyítottan ott van; a saját gólba kerülő kilépésnél a mögé
    csúszás (a szomszéd zár) a téma, vagy fegyelmezettebb fal kell.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal): {"goals",
    "behind_stepout", "verdict"} — a verdict "a kilépésük mögé
    betalálnak" (SOP_MIN_GOALS mért góltól, SOP_PUNISH_PCT arány
    felett), különben None.
    """
    from ..models.tracking import Team
    from .tactics import TacticsConfig
    from .xg import match_xg

    config = config or TacticsConfig()
    idx_of = {f.t: i for i, f in enumerate(match.frames)}

    out = {side: {"goals": 0, "behind_stepout": 0, "verdict": None}
           for side in ("home", "away")}
    for sh in match_xg(match, config).get("shots", []):
        if sh.get("outcome") != "goal":
            continue
        deff = "away" if sh["team"] == "home" else "home"
        i0 = idx_of.get(sh["t"])
        if i0 is None:
            continue
        own_goal_x = config.own_goal_x(
            Team.HOME if deff == "home" else Team.AWAY)
        dists = sorted(abs(p.x - own_goal_x)
                       for p in match.frames[i0].players
                       if p.team.value == deff and p.role != "kapus")
        if len(dists) < 3:
            continue
        median = dists[len(dists) // 2]
        rec = out[deff]
        rec["goals"] += 1
        if dists[-1] - median >= SOP_AHEAD_M:
            rec["behind_stepout"] += 1

    for side in ("home", "away"):
        rec = out[side]
        if rec["goals"] >= SOP_MIN_GOALS:
            pct = 100.0 * rec["behind_stepout"] / rec["goals"]
            if pct >= SOP_PUNISH_PCT:
                rec["verdict"] = "a kilépésük mögé betalálnak"
    return out


# Labdaszerző-poszt: ennyi poszthoz kötött labdaszerzés kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy a védekezésük
# egy poszton nyeri a labdákat.
RSW_MIN_STEALS = 5
RSW_SHARE_PCT = 50.0


def role_steal_sources(match, config=None) -> dict:
    """Labdaszerző-poszt: MELYIK POSZTJUK NYERI a labdákat.

    A labdaszerzők (ball_winners) az EMBERT nevezik meg — ez a posztot:
    a birtokos-váltásokat a szerző játékos posztjához írja. A küszöb
    itt 50% (nem 60), mert a labdaszerzés a legszórtabb esemény — ha
    így is egy poszthoz kötődik a fele, az már erős minta.

    Edzőileg mindkét irányban éles. Ellenük: ha a labdáik nagy részét
    ugyanaz a poszt szedi (tipikusan a szélén letámadó védő), arra az
    oldalra nem szabad odavezetni a támadást — az átadásoknak a másik
    oldalon kell átmenniük, és az ő sávjában csak biztonsági passz
    mehet. A saját oldalon: ha a szerzéseink egy emberen múlnak, a
    letámadásunk egyetlen cserével hatástalanítható — a nyomás-váltást
    (ki lép ki, ki szed) több posztra kell szétosztani.

    Visszatérés csapatonként (a SZERZŐ oldal): {"steals" (poszthoz
    kötött), "roles": {poszt: szerzés}, "main_role", "share_pct",
    "verdict"} — a main_role/share_pct/verdict None, ha nincs meg az
    RSW_MIN_STEALS, vagy egyik poszt sem éri el az RSW_SHARE_PCT-t.
    """
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    bw = ball_winners(match, config)

    out: dict = {side: {"steals": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in bw[side]["players"]:
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["steals"])
            rec["steals"] += row["steals"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["steals"] >= RSW_MIN_STEALS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["steals"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= RSW_SHARE_PCT:
                rec["verdict"] = (
                    f"a labdáik felét-többségét a(z) {poszt} szedi "
                    f"({share:.0f}%, {rec['steals']} szerzésből) — az ő "
                    "sávjába csak biztonsági passz mehet, a támadást a "
                    "másik oldalon kell átvezetni")
    return out


# Blokk-poszt: ennyi poszthoz kötött blokk kell az ítélethez, és
# ekkora részarány fölött mondjuk ki, hogy a faluk blokk-munkája egy
# poszton áll.
RBK_MIN_BLOCKS = 3
RBK_SHARE_PCT = 60.0


def role_block_sources(match, config=None) -> dict:
    """Blokk-poszt: MELYIK POSZTJUK BLOKKOL.

    A blokkolt lövések rétege (detect_blocks) az embert nevezi meg —
    ez a posztot: a blokkokat a blokkoló játékos posztjához írja.

    Edzőileg ez a lövés-előkészítés térképe. Ha a blokkjaik nagy része
    ugyanarról a posztról jön (tipikusan a középső védőtől), az ő
    sávjában átlövéssel próbálkozni ajándék labdavesztés — oda csak
    elmozgatás UTÁN szabad lőni: a figura először őt húzza ki (beálló-
    felfutás, keresztmozgás), és a lövés a megnyílt sávba megy. Ha a
    blokk-munkájuk szórt, nincs kitüntetett sáv — a lövés-választást a
    kapus-helyezkedés döntse.

    Visszatérés csapatonként (a BLOKKOLÓ oldal): {"blocks" (poszthoz
    kötött), "roles": {poszt: blokk}, "main_role", "share_pct",
    "verdict"} — a main_role/share_pct/verdict None, ha nincs meg az
    RBK_MIN_BLOCKS, vagy egyik poszt sem éri el az RBK_SHARE_PCT-t.
    """
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    blk = detect_blocks(match, config)

    out: dict = {side: {"blocks": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in blk[side]["blockers"]:
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["blocks"])
            rec["blocks"] += row["blocks"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["blocks"] >= RBK_MIN_BLOCKS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["blocks"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= RBK_SHARE_PCT:
                rec["verdict"] = (
                    f"a blokkjaik a(z) {poszt} posztról jönnek "
                    f"({share:.0f}%, {rec['blocks']} blokkból) — az ő "
                    "sávjába csak elmozgatás UTÁN szabad lőni, a "
                    "figura először őt húzza ki")
    return out


# Visszafutás-poszt: ennyi poszthoz kötött lemaradás kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy a
# visszarendeződésük egy poszton szakad el.
RTR_MIN_BREAKS = 3
RTR_SHARE_PCT = 60.0


def slow_retreat_roles(match, config=None) -> dict:
    """Visszafutás-poszt: KI MARAD LE a visszarendeződésben.

    Az ellenfél lerohanás-szakaszainak végén (a kontra kifutásának
    pillanatában) megnézi, a VÉDEKEZŐ csapat melyik mezőnyjátékosa
    van legmesszebb a saját kapujától, és a lemaradást a posztjához
    írja.

    Edzőileg két olvasat. Ellenük: ha a kontráknál rendre ugyanaz a
    posztjuk marad elöl (tipikusan a beálló vagy egy átlövő), a saját
    kontrát tudatosan az ő sávjába kell vezetni — ott a pálya üres.
    Saját csapatra: a visszafutás sorrendje edzés-téma, nem alkat
    kérdése — a lövés pillanatában kijelölt első visszafutó kell, és
    az nem lehet mindig ugyanaz a lemaradó.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal): {"breaks" (mért
    ellenfél-kontra), "roles": {poszt: lemaradás}, "main_role",
    "share_pct", "verdict"} — az ítélet None, ha nincs meg az
    RTR_MIN_BREAKS, vagy egyik poszt sem éri el az RTR_SHARE_PCT-t.
    """
    from ..models.tracking import Team
    from .attack_types import AttackType, classify_attacks
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    frames_by_t = {f.t: f for f in match.frames}

    out: dict = {side: {"breaks": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for a in classify_attacks(match, config):
        if a["type"] != AttackType.FAST_BREAK.value:
            continue
        defending = "away" if a["team"] == "home" else "home"
        fr = frames_by_t.get(a["end_frame"])
        if fr is None:
            continue
        own_x = config.own_goal_x(Team(defending))
        laggard = None
        for p in fr.players:
            if p.team.value != defending or p.role == "kapus":
                continue
            d = abs(p.x - own_x)
            if laggard is None or d > laggard[1]:
                laggard = (p.track_id, d)
        if laggard is None:
            continue
        rec_role = roles[defending].get(laggard[0])
        if rec_role is None:
            continue
        rec = out[defending]
        poszt = rec_role["poszt"]
        rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1
        rec["breaks"] += 1
    for rec in out.values():
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["breaks"] >= RTR_MIN_BREAKS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["breaks"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= RTR_SHARE_PCT:
                rec["verdict"] = (
                    f"a visszarendeződésük a(z) {poszt} poszton "
                    f"szakad el ({share:.0f}%, {rec['breaks']} "
                    "kontrából ő maradt elöl) — a saját kontrát az ő "
                    "sávjába kell vezetni: ott a pálya üres")
    return out


# Visszafutás-lemaradók: ennyi lemaradás kell ahhoz, hogy egy
# játékost megnevezzünk.
SRP_MIN_LAGS = 3


def slow_retreat_players(match, config=None) -> dict:
    """Visszafutás-lemaradók: KI marad elöl a kontráik alatt.

    A visszafutás-poszt (slow_retreat_roles) a POSZTOT nevezi meg —
    ez az EMBERT: az ellenfél lerohanás-szakaszainak végén megnézi, a
    védekező csapat melyik mezőnyjátékosa van legmesszebb a saját
    kapujától, és a lemaradást a nevéhez írja.

    Edzőileg: a poszt-kép edzés-téma, a név viszont azonnali
    beavatkozás. Ellenük: a saját kontrát az ő oldalára kell
    vezetni, mert ott marad üres a pálya. Saját csapatra: a lövés
    pillanatában neki kell a kijelölt első visszafutónak lennie —
    ha mindig ugyanaz a név jön ki, az nem alkat, hanem szabály
    kérdése.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal): {"lags" (mért
    lemaradás), "players": [{"player_id", "jersey", "lags"}],
    "top"} — a lista lemaradás szerint csökkenő; a "top" az első
    játékos, ha legalább SRP_MIN_LAGS lemaradása van, különben
    None.
    """
    from ..models.tracking import Team
    from .attack_types import AttackType, classify_attacks
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    frames_by_t = {f.t: f for f in match.frames}

    jersey: dict = {}
    tally: dict = {"home": {}, "away": {}}
    for a in classify_attacks(match, config):
        if a["type"] != AttackType.FAST_BREAK.value:
            continue
        defending = "away" if a["team"] == "home" else "home"
        fr = frames_by_t.get(a["end_frame"])
        if fr is None:
            continue
        own_x = config.own_goal_x(Team(defending))
        laggard = None
        for p in fr.players:
            if p.team.value != defending or p.role == "kapus":
                continue
            d = abs(p.x - own_x)
            if laggard is None or d > laggard[1]:
                laggard = (p, d)
        if laggard is None:
            continue
        p = laggard[0]
        if p.jersey_number is not None:
            jersey.setdefault(p.track_id, p.jersey_number)
        tally[defending][p.track_id] = (
            tally[defending].get(p.track_id, 0) + 1)

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "lags": n}
                for pid, n in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1])]
        top = (rows[0] if rows and rows[0]["lags"] >= SRP_MIN_LAGS
               else None)
        out[side] = {"lags": sum(r["lags"] for r in rows),
                     "players": rows, "top": top}
    return out


# Átvert-poszt: ennyi poszthoz kötött átverés kell az ítélethez, és
# ekkora részarány fölött mondjuk ki, hogy a párharc-vereségeik egy
# poszton gyűlnek.
BTR_MIN_GOALS = 3
BTR_SHARE_PCT = 60.0


def beaten_defender_roles(match, config=None) -> dict:
    """Átvert-poszt: MELYIK POSZTJUK mögött esnek a kapott gólok.

    Az átvert védők rétege (beaten_defenders) az embert nevezi meg —
    ez a posztot: a védőhöz rendelt kapott gólokat az átvert játékos
    posztjához írja. Így a minta akkor is látszik, ha a nevek
    meccsről meccsre cserélődnek.

    Edzőileg ez az 1v1-térkép: ha a kapott góljaik rendre ugyanannak
    a posztnak a párharc-vereségéből esnek, oda kell vinni az 1v1-et
    — elzárással hozzá terelni a lövőt, és a figura az ő emberét
    támadja. Saját csapatra: a sokat átvert posztunk mellé besegítő
    váltás és párharc-edzés kell, mert az ellenfél is látja.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal): {"goals" (poszthoz
    kötött kapott gól), "roles": {poszt: gól}, "main_role",
    "share_pct", "verdict"} — az ítélet None, ha nincs meg a
    BTR_MIN_GOALS, vagy egyik poszt sem éri el a BTR_SHARE_PCT-t.
    """
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    btn = beaten_defenders(match, config)

    out: dict = {side: {"goals": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in btn[side]["defenders"]:
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["beaten"])
            rec["goals"] += row["beaten"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["goals"] >= BTR_MIN_GOALS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["goals"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= BTR_SHARE_PCT:
                rec["verdict"] = (
                    f"a kapott góljaik a(z) {poszt} posztjuk mögött "
                    f"esnek ({share:.0f}%, {rec['goals']} védőhöz "
                    "rendelt gólból) — oda kell vinni az 1v1-et: a "
                    "figura az ő emberét támadja, elzárás is hozzá "
                    "terelje a lövőt")
    return out


# Kettőző-poszt: ennyi poszthoz kötött kettőzött kocka kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy a
# kettőzésük egy posztról érkezik.
DDR_MIN_FRAMES = 40
DDR_SHARE_PCT = 60.0


def doubling_defender_roles(match, config=None) -> dict:
    """Kettőző-poszt: MELYIK POSZTJUK lép ki kettőzni.

    A kettőző emberek rétege (doubling_defenders) az embert nevezi
    meg — ez a posztot: a kettőzött kockákat a másodiknak érkező
    védő posztjához írja. Így a minta akkor is látszik, ha a nevek
    meccsről meccsre cserélődnek.

    Edzőileg ez a kijátszás-terv: ha a kettőzésük rendre ugyanarról
    a posztról érkezik, előre tudni, HOL nyílik ki a pálya — a
    kettőzés pillanatában az ő elhagyott embere felé megy az első
    passz, mert ő szabadult fel. Saját csapatra: a kiolvasható
    kettőzést forgatni kell.

    Visszatérés csapatonként (a KETTŐZŐ, védekező oldal): {"frames"
    (poszthoz kötött kettőzött kocka), "roles": {poszt: kocka},
    "main_role", "share_pct", "verdict"} — az ítélet None, ha nincs
    meg a DDR_MIN_FRAMES, vagy egyik poszt sem éri el a
    DDR_SHARE_PCT-t.
    """
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    dd = doubling_defenders(match, config)

    out: dict = {side: {"frames": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in dd[side]["doublers"]:
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["frames"])
            rec["frames"] += row["frames"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["frames"] >= DDR_MIN_FRAMES:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["frames"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= DDR_SHARE_PCT:
                rec["verdict"] = (
                    f"a kettőzésük a(z) {poszt} posztról érkezik "
                    f"({share:.0f}% a kettőzött időből) — a kettőzés "
                    "pillanatában az ő elhagyott embere felé menjen "
                    "az első passz: ő az üres ember")
    return out


# Kettőzött-poszt: ennyi poszthoz kötött kettőzött labdás kocka kell
# az ítélethez, és ekkora részarány fölött mondjuk ki, hogy a
# kettőzések egy posztjukra érkeznek.
DTR_MIN_FRAMES = 100
DTR_SHARE_PCT = 60.0


def doubled_target_roles(match, config=None) -> dict:
    """Kettőzött-poszt: MELYIK POSZTJUKRA érkezik a kettőzés.

    A kettőzés-réteg (double_teams) a védő oldalt minősíti — ez a
    megtámadott posztot: a kettőzött (két védővel szorongatott)
    labdás kockákat a birtokos posztjához írja a TÁMADÓ oldalon. Így
    látszik, kire járnak rá az ellenfelek kettőzései.

    Edzőileg ez kollektív felderítés: ha az ellenfelek kettőzései
    rendre ugyanarra a posztjukra érkeznek, a minta bevált recept —
    érdemes követni, és oda küldeni a kettőzést. A kettőzött poszt
    mögött viszont üres ember marad: a kettőzés mögötti kilépő
    passzsáv zárása a másik fele a tervnek. Saját csapatra: ha egy
    posztunkat rendre kettőzik, neki lekapcsolódó társ és begyakorolt
    kettőzés-elleni leadás kell.

    Visszatérés csapatonként (a KETTŐZÖTT, támadó oldal): {"frames"
    (poszthoz kötött kettőzött kocka), "roles": {poszt: kocka},
    "main_role", "share_pct", "verdict"} — az ítélet None, ha nincs
    meg a DTR_MIN_FRAMES, vagy egyik poszt sem éri el a
    DTR_SHARE_PCT-t.
    """
    import math

    from .decisions import ball_holder
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)

    out: dict = {side: {"frames": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for f in match.frames:
        holder = ball_holder(f, config)
        if holder is None or holder.team is None \
                or holder.role == "kapus":
            continue
        near = sum(1 for p in f.players
                   if p.team is not None and p.team != holder.team
                   and p.role != "kapus"
                   and math.hypot(p.x - holder.x, p.y - holder.y)
                   <= DOUBLE_TEAM_M)
        if near < 2:
            continue
        side = holder.team.value
        rec_role = roles[side].get(holder.track_id)
        if rec_role is None:
            continue
        poszt = rec_role["poszt"]
        rec = out[side]
        rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1
        rec["frames"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["frames"] >= DTR_MIN_FRAMES:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["frames"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= DTR_SHARE_PCT:
                rec["verdict"] = (
                    f"az ellenfelek kettőzései {share:.0f}%-ban a(z)"
                    f" {poszt} posztjukra érkeznek — a minta bevált "
                    "recept: oda küldjétek a kettőzést, és zárjátok "
                    "a mögötte kilépő passzsávot")
    return out


# Kettőzött emberek: ennyi kettőzött labdás kocka kell a névhez, és
# ekkora részarány fölött mondjuk ki, hogy a kettőzés egy emberre
# jár rá.
DTG_MIN_FRAMES = 75
DTG_SHARE_PCT = 50.0


def doubled_targets(match, config=None) -> dict:
    """Kettőzött emberek: KIRE jár rá az ellenfelek kettőzése.

    A kettőzött-poszt (doubled_target_roles) a POSZTOT nevezi meg —
    ez az EMBERT: a kettőzött (két védővel szorongatott) labdás
    kockákat a birtokos nevéhez írja a támadó oldalon.

    Edzőileg ez kollektív felderítés névre szólóan: ha az ellenfelek
    rendre ugyanarra az emberükre küldik a kettőzést, a minta bevált
    recept — érdemes követni. A kettőzött ember mögött viszont üres
    társ marad: a kilépő passzsáv zárása a terv másik fele. Saját
    csapatra: akit rendre kettőznek, annak lekapcsolódó társ és
    begyakorolt kettőzés-elleni leadás kell — különben minden
    támadásunk rajta akad el.

    Visszatérés csapatonként (a KETTŐZÖTT, támadó oldal): {"frames",
    "players": [{"player_id", "jersey", "frames"}], "top"} — a "top"
    az első játékos, ha legalább DTG_MIN_FRAMES kettőzött kockája
    van, és ez az összes kettőzött kockájuk legalább DTG_SHARE_PCT-a,
    különben None.
    """
    import math

    from .decisions import ball_holder
    from .tactics import TacticsConfig

    config = config or TacticsConfig()

    jersey: dict = {}
    tally: dict = {"home": {}, "away": {}}
    for f in match.frames:
        holder = ball_holder(f, config)
        if holder is None or holder.team is None \
                or holder.role == "kapus":
            continue
        near = sum(1 for p in f.players
                   if p.team is not None and p.team != holder.team
                   and p.role != "kapus"
                   and math.hypot(p.x - holder.x, p.y - holder.y)
                   <= DOUBLE_TEAM_M)
        if near < 2:
            continue
        side = holder.team.value
        if holder.jersey_number is not None:
            jersey.setdefault(holder.track_id, holder.jersey_number)
        tally[side][holder.track_id] = (
            tally[side].get(holder.track_id, 0) + 1)

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "frames": n}
                for pid, n in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1])]
        total = sum(r["frames"] for r in rows)
        top = None
        if rows and rows[0]["frames"] >= DTG_MIN_FRAMES:
            share = 100.0 * rows[0]["frames"] / max(1, total)
            if share >= DTG_SHARE_PCT:
                top = rows[0]
        out[side] = {"frames": total, "players": rows, "top": top}
    return out


# Elzárt-poszt: ennyi poszthoz kötött elakadt védés kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy az
# elzárások rendre ugyanazt a védő-posztjukat találják meg.
SDR_MIN_SCREENS = 3
SDR_SHARE_PCT = 60.0


# Elzárt védők: ennyi elakadás kell a névhez, és ekkora részarány
# fölött mondjuk ki, hogy az elzárások egy védőt találnak meg.
SDP_MIN_SCREENS = 2
SDP_SHARE_PCT = 50.0


def screened_defenders(match, config=None) -> dict:
    """Elzárt védők: KI akad el az elzárásokban.

    Az elzárt-poszt (screened_defender_roles) a POSZTOT nevezi meg —
    ez az EMBERT: lövésenként megkeressük a lövő őrzőjét és a mellé
    állított elzárót, és az elakadt őrző nevéhez írjuk az esetet.

    Edzőileg ez az elzárás-célpont terve névre szólóan: akire az
    elzárás rendre ráragad, oda kell vinni a figurákat — az ő
    oldalán a zárás tisztán hagyja a lövőt. Saját csapatra: neki
    átcsúszás- és váltás-gyakorlás kell, hangos kommunikációval —
    az elakadás nem alkat, hanem technika kérdése.

    Visszatérés csapatonként (az ELAKADT, védő oldal): {"screens",
    "players": [{"player_id", "jersey", "screens"}], "top"} — a
    "top" az első játékos, ha legalább SDP_MIN_SCREENS elakadása
    van, és ez a csapat elakadásainak legalább SDP_SHARE_PCT-a,
    különben None.
    """
    import math

    from .attack_types import SCREEN_DIST_M, SCREEN_MARKER_MAX_M
    from .tactics import TacticsConfig
    from .xg import match_xg

    config = config or TacticsConfig()
    idx_of = {f.t: i for i, f in enumerate(match.frames)}

    jersey: dict = {}
    for f in match.frames:
        for q in f.players:
            if q.jersey_number is not None:
                jersey.setdefault(q.track_id, q.jersey_number)

    tally: dict = {"home": {}, "away": {}}
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
            if d.team is None or d.team == shooter.team \
                    or d.role == "kapus":
                continue
            dist = math.hypot(d.x - shooter.x, d.y - shooter.y)
            if dist <= best:
                marker, best = d, dist
        if marker is None:
            continue
        setter = None
        best_s = SCREEN_DIST_M
        for p in f.players:
            if p.team != shooter.team or p.track_id == pid:
                continue
            d = math.hypot(p.x - marker.x, p.y - marker.y)
            if d <= best_s:
                setter, best_s = p, d
        if setter is None:
            continue
        side = marker.team.value
        if side not in tally:
            continue
        tally[side][marker.track_id] = (
            tally[side].get(marker.track_id, 0) + 1)

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "screens": n}
                for pid, n in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1])]
        total = sum(r["screens"] for r in rows)
        top = None
        if rows and rows[0]["screens"] >= SDP_MIN_SCREENS:
            share = 100.0 * rows[0]["screens"] / max(1, total)
            if share >= SDP_SHARE_PCT:
                top = rows[0]
        out[side] = {"screens": total, "players": rows, "top": top}
    return out


def screened_defender_roles(match, config=None) -> dict:
    """Elzárt-poszt: MELYIK VÉDŐJÜK akad el az elzárásokban.

    Az elzárók rétege (attack_types.screen_setters) a támadó oldalt
    nevezi meg — ez a megtalált VÉDŐT: lövésenként megkeressük a
    lövő őrzőjét (SCREEN_MARKER_MAX_M-en belüli legközelebbi védő)
    és a mellé állított elzárót (a lövő SCREEN_DIST_M-en belüli
    társa az őrző mellett), és az elakadt őrző posztjához írjuk az
    esetet. Így látszik, kire érdemes elzárást vinni.

    Edzőileg ez az elzárás-célpont terve: amelyik védő-posztjuk
    rendre elakad az elzárásokban, ellene oda kell vinni a
    figurákat — az ő oldalán az elzárás tisztán hagyja a lövőt.
    Saját csapatra: annak a védőnek átcsúszás- és váltás-gyakorlás
    kell, hangos kommunikációval.

    Visszatérés csapatonként (az ELAKADT, védő oldal): {"screens"
    (poszthoz kötött elakadás), "roles": {poszt: darab},
    "main_role", "share_pct", "verdict"} — az ítélet None, ha nincs
    meg az SDR_MIN_SCREENS, vagy egyik poszt sem éri el az
    SDR_SHARE_PCT-t.
    """
    import math

    from .attack_types import SCREEN_DIST_M, SCREEN_MARKER_MAX_M
    from .roles import estimate_positions
    from .tactics import TacticsConfig
    from .xg import match_xg

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    idx_of = {f.t: i for i, f in enumerate(match.frames)}

    out: dict = {side: {"screens": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
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
            if d.team is None or d.team == shooter.team \
                    or d.role == "kapus":
                continue
            dist = math.hypot(d.x - shooter.x, d.y - shooter.y)
            if dist <= best:
                marker, best = d, dist
        if marker is None:
            continue
        setter = None
        best_s = SCREEN_DIST_M
        for p in f.players:
            if p.team != shooter.team or p.track_id == pid:
                continue
            d = math.hypot(p.x - marker.x, p.y - marker.y)
            if d <= best_s:
                setter, best_s = p, d
        if setter is None:
            continue
        side = marker.team.value
        rec_role = roles[side].get(marker.track_id)
        if rec_role is None:
            continue
        poszt = rec_role["poszt"]
        rec = out[side]
        rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1
        rec["screens"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["screens"] >= SDR_MIN_SCREENS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["screens"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= SDR_SHARE_PCT:
                rec["verdict"] = (
                    f"az elzárások {share:.0f}%-ban a(z) {poszt} "
                    f"posztjukon lévő védőt találják meg "
                    f"({rec['screens']} elakadásból) — az ő oldalán"
                    " az elzárás tisztán hagyja a lövőt: oda kell "
                    "vinni a figurákat")
    return out


# Blokkolt-poszt: ennyi poszthoz kötött blokkolt lövés kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy a falba
# lőtt labdáik egy posztról jönnek.
BSR_MIN_BLOCKS = 3
BSR_SHARE_PCT = 60.0
BSR_LOOKBACK_FRAMES = 25   # a lövő keresése a blokk előtti kockákon


def blocked_shooter_roles(match, config=None) -> dict:
    """Blokkolt-poszt: MELYIK POSZTJUK lövéseit blokkolják.

    A blokk-réteg (detect_blocks) a védő oldalt nevezi meg — ez a
    megakasztott lövőt: minden blokkhoz megkeresi a blokk előtti
    utolsó támadó labdabirtokost, és a blokkot az ő posztjához írja.
    Így látszik, kinek a lövése akad el rendre a falban.

    Edzőileg ez a fal bátorsága: amelyik posztjuk rendre falba lő,
    ellene a blokk nem szerencse, hanem terv — a védője bátran
    zárhat elé. Saját csapatra: annál a posztnál lövés előtt
    kötelező az elmozgatás (elzárás, csel) — az előkészítetlen
    lövése ajándék labdavesztés.

    Visszatérés csapatonként (a BLOKKOLT, támadó oldal): {"blocks"
    (poszthoz kötött blokkolt lövés), "roles": {poszt: darab},
    "main_role", "share_pct", "verdict"} — az ítélet None, ha nincs
    meg a BSR_MIN_BLOCKS, vagy egyik poszt sem éri el a
    BSR_SHARE_PCT-t.
    """
    from ..models.tracking import Team
    from .decisions import ball_holder
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    blk = detect_blocks(match, config)
    idx_of = {f.t: i for i, f in enumerate(match.frames)}

    out: dict = {side: {"blocks": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for def_side in ("home", "away"):
        atk_side = "away" if def_side == "home" else "home"
        atk_team = Team.HOME if atk_side == "home" else Team.AWAY
        for ev in blk[def_side]["events"]:
            i0 = idx_of.get(ev["t"])
            if i0 is None:
                continue
            shooter = None
            for j in range(i0, max(-1, i0 - BSR_LOOKBACK_FRAMES), -1):
                h = ball_holder(match.frames[j], config)
                if h is not None and h.team == atk_team \
                        and h.role != "kapus":
                    shooter = h.track_id
                    break
            if shooter is None:
                continue
            rec_role = roles[atk_side].get(shooter)
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec = out[atk_side]
            rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1
            rec["blocks"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["blocks"] >= BSR_MIN_BLOCKS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["blocks"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= BSR_SHARE_PCT:
                rec["verdict"] = (
                    f"a blokkolt lövéseik {share:.0f}%-a a(z) "
                    f"{poszt} posztról jön ({rec['blocks']} "
                    "blokkból) — a fal ellene bátran zárhat: az ő "
                    "előkészítetlen lövése falba megy, és onnan "
                    "kontra indul")
    return out


# Kilépő-poszt: posztonként ennyi mért felállt-védekezéses kocka
# kell, legalább ennyi mért poszt, és ekkora mélység-többlet a
# társakhoz képest, hogy kilépő posztot mondjunk.
ADR_MIN_FRAMES = 100
ADR_MIN_ROLES = 3
ADR_GAP_M = 2.5


def advanced_defender_roles(match, config=None) -> dict:
    """Kilépő-poszt: MELYIK POSZTJUK lép ki a falból.

    A kilépő védő rétege (advanced_defender) az embert nevezi meg —
    ez a posztot: a felállt védekezés mért kockáit és kapu-távolság
    összegét a védő (támadó-fázisból becsült) posztjához összegzi,
    és megnézi, van-e a többi posztnál legalább ADR_GAP_M méterrel
    előrébb álló poszt. Így a minta akkor is látszik, ha a nevek
    meccsről meccsre cserélődnek.

    Edzőileg: a kilépő poszt mögött nyílik a tér — elzárást kell rá
    vinni, és a háta mögé befutóval 2 az 1-et játszani. Saját
    csapatra: a kilépés mögötti biztosítás az edzés-téma.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal): {"frames" (mért
    kocka), "roles": {poszt: kocka}, "depth_m": {poszt:
    távolság-összeg}, "main_role", "gap_m", "verdict"} — az ítélet
    None, ha ADR_MIN_ROLES-nál kevesebb poszton van ADR_MIN_FRAMES
    kocka, vagy nincs ADR_GAP_M-es kiugrás.
    """
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    adv = advanced_defender(match, config)

    out: dict = {side: {"frames": 0, "roles": {}, "depth_m": {},
                        "main_role": None, "gap_m": None,
                        "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in adv[side]["players"]:
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["frames"])
            rec["depth_m"][poszt] = round(
                rec["depth_m"].get(poszt, 0.0)
                + row["avg_depth_m"] * row["frames"], 1)
            rec["frames"] += row["frames"]

        merhetok = {p: n for p, n in rec["roles"].items()
                    if n >= ADR_MIN_FRAMES}
        if len(merhetok) < ADR_MIN_ROLES:
            continue
        atlagok = {p: rec["depth_m"][p] / rec["roles"][p]
                   for p in merhetok}
        poszt = max(atlagok, key=lambda p: atlagok[p])
        tarsak_kocka = sum(rec["roles"][p] for p in merhetok
                           if p != poszt)
        tarsak_tav = sum(rec["depth_m"][p] for p in merhetok
                         if p != poszt)
        base = tarsak_tav / tarsak_kocka
        gap = round(atlagok[poszt] - base, 2)
        rec["gap_m"] = gap
        if gap >= ADR_GAP_M:
            rec["main_role"] = poszt
            rec["verdict"] = (
                f"a faluk a(z) {poszt} posztnál lép ki (a társaknál "
                f"{gap:.1f} m-rel előrébb áll) — elzárást rá, és a "
                "háta mögé befutóval 2 az 1-et: a kilépő mögött "
                "nyílik a tér")
    return out


# Beállóőr-poszt: ennyi poszthoz kötött őrzés-kocka kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy a
# beálló-őrzésük egy poszton áll.
PGR_MIN_FRAMES = 300
PGR_SHARE_PCT = 60.0


def pivot_guard_roles(match, config=None) -> dict:
    """Beállóőr-poszt: MELYIK POSZTJUK őrzi az ellenfél beállóját.

    A beálló-őr rétege (pivot_guards) az embert nevezi meg — ez a
    posztot: az őrzés-kockákat az őrző (támadó-fázisból becsült)
    posztjához írja. Így a minta akkor is látszik, ha a nevek
    meccsről meccsre cserélődnek.

    Edzőileg ez az elzárás-terv magja: ha a beálló-őrzésük egy
    poszton áll, az elzárás pont őt húzza ki — a beálló
    felszabadul, és a belső biztosításuk rendje borul. Saját
    csapatra: a beálló-őrzés ne egyetlen posztunk magánügye legyen,
    kell a váltás-szabály.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal): {"frames"
    (poszthoz kötött őrzés-kocka), "roles": {poszt: kocka},
    "main_role", "share_pct", "verdict"} — az ítélet None, ha nincs
    meg a PGR_MIN_FRAMES, vagy egyik poszt sem éri el a
    PGR_SHARE_PCT-t.
    """
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    pg = pivot_guards(match, config)

    out: dict = {side: {"frames": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in pg[side]["guards"]:
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["frames"])
            rec["frames"] += row["frames"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["frames"] >= PGR_MIN_FRAMES:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["frames"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= PGR_SHARE_PCT:
                rec["verdict"] = (
                    f"a beálló-őrzésük a(z) {poszt} posztjukon áll "
                    f"({share:.0f}%-a az őrzött időnek) — az elzárás"
                    " őt húzza ki, és a beálló felszabadul, a belső"
                    " biztosításuk pedig borul")
    return out


# Fáradt-fal poszt: legalább ennyi 2. félidei kapott gól kell egy
# posztról, és ennyiszerese az első félideinek, hogy a falat ott
# fáradónak mondjuk ki.
TCR_MIN_SH = 3
TCR_FACTOR = 2.0


def tired_conceder_roles(match, config=None) -> dict:
    """Fáradt-fal poszt: a 2. félidőben MELYIK POSZT jár át rajtuk.

    A kapott gólok poszt-térképe (conceded_by_role) a teljes meccset
    nézi — ez a fáradást: a kapott gólokat félidőnként a LÖVŐ
    posztjához írja, és megkeresi, melyik poszt góljai ugranak meg
    ellenük a második félidőre. Így látszik, hol ül le fáradtan a
    faluk.

    Edzőileg ez a szünet utáni támadás-terv: amelyik poszt a második
    félidőben rendre átjár rajtuk, onnan kell nyitni a szünet után —
    a fal ott fárad, és a friss támadó ott talál rést. Saját
    csapatra: a falunk fáradó sávja csere- és kondíció-téma.

    Visszatérés csapatonként (a VÉDŐ oldal): {"fh_roles": {poszt:
    darab}, "sh_roles": {poszt: darab}, "main_role", "fh", "sh",
    "verdict"} — az ítélet None, ha nincs felismert szünet, vagy
    egyik poszt sem éri el a TCR_MIN_SH-t a TCR_FACTOR-os ugrással.
    """
    from .event_detection import EventType, detect_shots
    from .halftime import detect_halftime
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    out: dict = {side: {"fh_roles": {}, "sh_roles": {},
                        "main_role": None, "fh": None, "sh": None,
                        "verdict": None}
                 for side in ("home", "away")}
    ht = detect_halftime(match)
    if ht is None:
        return out
    roles = estimate_positions(match, config)

    for e in detect_shots(match, config):
        if e.type != EventType.GOAL or e.player_id is None:
            continue
        atk = e.team.value
        deff = "away" if atk == "home" else "home"
        key = "fh_roles" if e.t <= ht else "sh_roles"
        rec_role = roles[atk].get(e.player_id)
        if rec_role is None:
            continue
        poszt = rec_role["poszt"]
        out[deff][key][poszt] = out[deff][key].get(poszt, 0) + 1

    for side in ("home", "away"):
        rec = out[side]
        fader = None
        for poszt, sh in sorted(rec["sh_roles"].items(),
                                key=lambda kv: -kv[1]):
            fh = rec["fh_roles"].get(poszt, 0)
            if sh >= TCR_MIN_SH and sh >= TCR_FACTOR * max(1, fh):
                fader = (poszt, fh, sh)
                break
        if fader is not None:
            poszt, fh, sh = fader
            rec["main_role"] = poszt
            rec["fh"], rec["sh"] = fh, sh
            rec["verdict"] = (
                f"a második félidőre a(z) {poszt} poszt jár át "
                f"rajtuk ({fh} → {sh} kapott gól) — a faluk ott ül "
                "le fáradtan: a szünet után onnan kell nyitni")
    return out


# Fáradt-fal emberek: ennyi második félidei gól kell a névhez, és
# ekkora szorzó az elsőhöz képest.
TCP_MIN_SH = 2
TCP_FACTOR = 2.0


def tired_conceder_players(match, config=None) -> dict:
    """Fáradt-fal emberek: KI jár át rajtuk a második félidőre.

    A fáradt-fal poszt (tired_conceder_roles) a POSZTOT nevezi meg —
    ez az EMBERT: a kapott gólokat félidőnként a LÖVŐ nevéhez írja,
    és megkeresi, kinek a góljai ugranak meg ellenük a szünet után.

    Edzőileg ez a szünet utáni támadás-terv névre szólóan: aki a
    második félidőben rendre átjár rajtuk, arra kell építeni a hajrá
    figuráit — a faluk vele szemben fárad el. Saját csapatra
    fordítva: ha ellenünk mindig ugyanaz a név hozza a második
    félidei gólokat, rá kell friss védőt és besegítést tervezni.

    Visszatérés csapatonként (a VÉDŐ oldal): {"fh": {lövő-kulcs:
    gól}, "sh": {...}, "top"} — a "top" az a lövő, akinek a második
    félidei góljai elérik a TCP_MIN_SH-t, és legalább TCP_FACTOR-
    szorosai az elsőnek; szünet-jel nélkül üres a kép.
    """
    from .event_detection import EventType, detect_shots
    from .halftime import detect_halftime
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    out: dict = {side: {"fh": {}, "sh": {}, "top": None}
                 for side in ("home", "away")}
    ht = detect_halftime(match)
    if ht is None:
        return out

    jersey: dict = {}
    for f in match.frames:
        for p in f.players:
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)

    tally: dict = {"home": {}, "away": {}}
    for e in detect_shots(match, config):
        if e.type != EventType.GOAL or e.player_id is None:
            continue
        atk = getattr(e.team, "value", e.team)
        deff = "away" if atk == "home" else "home"
        rec = tally[deff].setdefault(e.player_id, [0, 0])
        rec[0 if e.t <= ht else 1] += 1

    for side in ("home", "away"):
        rows = sorted(tally[side].items(), key=lambda kv: -kv[1][1])
        out[side]["fh"] = {str(jersey.get(pid, pid)): n[0]
                           for pid, n in rows if n[0]}
        out[side]["sh"] = {str(jersey.get(pid, pid)): n[1]
                           for pid, n in rows if n[1]}
        for pid, (fh, sh) in rows:
            if sh >= TCP_MIN_SH and sh >= TCP_FACTOR * max(1, fh):
                out[side]["top"] = {
                    "player_id": pid, "jersey": jersey.get(pid),
                    "fh": fh, "sh": sh}
                break
    return out


# Drága-eladó poszt: ennyi poszthoz kötött, gólba forduló eladás kell
# az ítélethez, és ekkora részarány fölött mondjuk ki, hogy a drága
# hibáik egy posztnál történnek.
DTO_MIN_PUNISHED = 3
DTO_SHARE_PCT = 60.0


def costly_turnover_roles(match, config=None) -> dict:
    """Drága-eladó poszt: MELYIK POSZTJUK hibái kerülnek gólba.

    A drága eladók rétege (costly_turnover_players) az embert nevezi
    meg — ez a posztot: a gólba forduló (a hibát követő kapott góllal
    büntetett) eladásokat a vesztes posztjához írja. Így a minta
    akkor is látszik, ha a nevek meccsről meccsre cserélődnek.

    Edzőileg ez a nyereség-térkép: amelyik posztjuk hibái rendre
    gólt érnek, ott a legtöbb a szerezhető gól — a felhozatalnál őt
    kell kettőzni-zavarni, és a labdájára rá kell startolni. Saját
    csapatra: annál a posztnál a nyomás alatti labdakezelés és a
    hiba utáni azonnali visszazárás a téma.

    Visszatérés csapatonként: {"punished" (poszthoz kötött, gólba
    forduló eladás), "roles": {poszt: darab}, "main_role",
    "share_pct", "verdict"} — az ítélet None, ha nincs meg a
    DTO_MIN_PUNISHED, vagy egyik poszt sem éri el a DTO_SHARE_PCT-t.
    """
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    ct = costly_turnover_players(match, config)

    out: dict = {side: {"punished": 0, "roles": {},
                        "main_role": None, "share_pct": None,
                        "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in ct[side]["players"]:
            if not row["punished"]:
                continue
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["punished"])
            rec["punished"] += row["punished"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["punished"] >= DTO_MIN_PUNISHED:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["punished"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= DTO_SHARE_PCT:
                rec["verdict"] = (
                    f"a gólba forduló eladásaik {share:.0f}%-a a(z) "
                    f"{poszt} posztnál történik ({rec['punished']} "
                    "büntetett hibából) — a felhozatalnál őt kell "
                    "kettőzni-zavarni: nála a legnagyobb a nyereség")
    return out


# Védőmotor-poszt: ennyi első félidei védő-akció (szerzés+blokk)
# kell egy posztról, és legfeljebb ennyi második félidei ahhoz, hogy
# a posztot leálló védő-motornak mondjuk ki.
FDR_MIN_FH = 3
FDR_MAX_SH = 1


def fading_defender_roles(match, config=None) -> dict:
    """Védőmotor-poszt: MELYIK POSZTJUK védő-motorja áll le.

    Az eltűnő védő rétege (fading_defenders) az embert nevezi meg —
    ez a posztot: a védő-akciókat (labdaszerzés + blokk) félidőnként
    a védő (támadó-fázisból becsült) posztjához írja, és megkeresi,
    melyik posztjuk első félidei motorja áll le a másodikra.

    Edzőileg ez a második félidei támadás-irány: az első félidei kép
    alapján a pörgő védő-zónát kerülnénk — pedig a másodikra már nem
    ér oda: a szünet után pont az ő zónáján át kell támadni. Saját
    csapatra: a védő-motor tervezett pihenője a szünet körül az
    edzés-téma.

    Visszatérés csapatonként (a VÉDŐ oldal): {"fh_roles": {poszt:
    darab}, "sh_roles": {poszt: darab}, "main_role", "fh", "sh",
    "verdict"} — az ítélet None, ha nincs felismert szünet, vagy
    egyik poszt sem éri el az FDR_MIN_FH-t az FDR_MAX_SH melletti
    leállással.
    """
    from .halftime import detect_halftime
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    out: dict = {side: {"fh_roles": {}, "sh_roles": {},
                        "main_role": None, "fh": None, "sh": None,
                        "verdict": None}
                 for side in ("home", "away")}
    ht = detect_halftime(match)
    if ht is None:
        return out
    roles = estimate_positions(match, config)

    def add(side, pid, t):
        rec_role = roles[side].get(pid)
        if rec_role is None:
            return
        poszt = rec_role["poszt"]
        key = "fh_roles" if t <= ht else "sh_roles"
        out[side][key][poszt] = out[side][key].get(poszt, 0) + 1

    bw = ball_winners(match, config)
    blk = detect_blocks(match, config)
    for side in ("home", "away"):
        for e in bw[side]["ts"]:
            add(side, e["player_id"], e["t"])
        for e in blk[side]["events"]:
            if e.get("player_id") is not None:
                add(side, e["player_id"], e["t"])

    for side in ("home", "away"):
        rec = out[side]
        fader = None
        for poszt, fh in sorted(rec["fh_roles"].items(),
                                key=lambda kv: -kv[1]):
            sh = rec["sh_roles"].get(poszt, 0)
            if fh >= FDR_MIN_FH and sh <= FDR_MAX_SH:
                fader = (poszt, fh, sh)
                break
        if fader is not None:
            poszt, fh, sh = fader
            rec["main_role"] = poszt
            rec["fh"], rec["sh"] = fh, sh
            rec["verdict"] = (
                f"a védő-motorjuk a(z) {poszt} poszton az első "
                f"félidőben pörög ({fh} szerzés+blokk), a másodikra"
                f" leáll ({sh}) — a szünet után pont az ő zónáján "
                "át kell támadni: addigra már nem ér oda")
    return out


# Fedezett-lövő poszt: ennyi poszthoz kötött fedezett lövés kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy a nyomás
# alatti lövés-vállalás egy poszton áll.
CVR_MIN_COVERED = 3
CVR_SHARE_PCT = 60.0


def covered_shooter_roles(match, config=None) -> dict:
    """Fedezett-lövő poszt: MELYIK POSZTJUK lő fedezetten is.

    A fedezetten lövők rétege (covered_shooters) az embert nevezi
    meg — ez a posztot: a fedezett (testközeli védő melletti)
    lövéseket a lövő posztjához írja. Így a minta akkor is látszik,
    ha a nevek meccsről meccsre cserélődnek.

    Edzőileg ez a fal takarékossága: amelyik posztjuk fedezetten is
    elhúzza a ravaszt, arra nem kell kilépni — a fedezett lövés
    alacsony értékű, elég a blokk-kéz és a mögé rendezett fal-kapus
    páros. Saját csapatra: a poszt lövés-szelekciója (fedezetten
    inkább passz) az edzés-téma.

    Visszatérés csapatonként (a TÁMADÓ oldal): {"covered" (poszthoz
    kötött fedezett lövés), "roles": {poszt: darab}, "main_role",
    "share_pct", "verdict"} — az ítélet None, ha nincs meg a
    CVR_MIN_COVERED, vagy egyik poszt sem éri el a CVR_SHARE_PCT-t.
    """
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    cs = covered_shooters(match, config)

    out: dict = {side: {"covered": 0, "roles": {},
                        "main_role": None, "share_pct": None,
                        "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in cs[side]["players"]:
            if not row["covered"]:
                continue
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["covered"])
            rec["covered"] += row["covered"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["covered"] >= CVR_MIN_COVERED:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["covered"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= CVR_SHARE_PCT:
                rec["verdict"] = (
                    f"a fedezett lövéseik {share:.0f}%-a a(z) "
                    f"{poszt} posztról jön ({rec['covered']} "
                    "fedezett lövésből) — rá nem kell kilépni: a "
                    "fedezett lövése alacsony értékű, elég a "
                    "blokk-kéz és a mögé rendezett fal")
    return out


# Célkereszt-poszt: ennyi poszthoz kötött rá-lövés kell az ítélethez,
# és ekkora részarány fölött mondjuk ki, hogy az ellenfelek egy
# posztjuk előtt fejeznek be.
TGR_MIN_SHOTS = 5
TGR_SHARE_PCT = 60.0


def targeted_defender_roles(match, config=None) -> dict:
    """Célkereszt-poszt: MELYIK POSZTJUK előtt fejeznek be ellenük.

    A célba vett védő rétege (targeted_defenders) az embert nevezi
    meg — ez a posztot: a kapott lövéseket a lövőhöz legközelebbi
    védő (támadó-fázisból becsült) posztjához írja. Így látszik,
    melyik posztjukat keresik az ellenfelek.

    Edzőileg kollektív felderítés: ha az ellenfelek rendre ugyanannak
    a posztnak az orra előtt fejeznek be, a minta bevált — a
    támadásokat oda kell szervezni, az ő védője elé pedig elzárást
    vinni. Saját csapatra: a célba vett posztunk segítséget kap
    (mögé a kapus szöge, mellé korai besegítés).

    Visszatérés csapatonként (a VÉDŐ oldal): {"shots" (poszthoz
    kötött rá-lövés), "roles": {poszt: darab}, "main_role",
    "share_pct", "verdict"} — az ítélet None, ha nincs meg a
    TGR_MIN_SHOTS, vagy egyik poszt sem éri el a TGR_SHARE_PCT-t.
    """
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    td = targeted_defenders(match, config)

    out: dict = {side: {"shots": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in td[side]["players"]:
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["shots"])
            rec["shots"] += row["shots"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["shots"] >= TGR_MIN_SHOTS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["shots"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= TGR_SHARE_PCT:
                rec["verdict"] = (
                    f"az ellenfelek {share:.0f}%-ban a(z) {poszt} "
                    f"posztjuk előtt fejeznek be ({rec['shots']} "
                    "rá-lövésből) — a minta bevált: oda kell "
                    "szervezni a támadást, a védője elé elzárást")
    return out


# Letámadó-poszt: ennyi poszthoz kötött elöl-szerzés kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy a
# letámadásuk egy poszton áll.
HSR_MIN_HIGH = 3
HSR_SHARE_PCT = 60.0


def high_steal_roles(match, config=None) -> dict:
    """Letámadó-poszt: MELYIK POSZTJUK szed labdát elöl.

    Az elöl szerző védők rétege (high_steal_players) az embert
    nevezi meg — ez a posztot: a támadó térfélen született
    szerzéseket a szerző posztjához írja. Így a minta akkor is
    látszik, ha a nevek meccsről meccsre cserélődnek.

    Edzőileg ez a kihozatal-terv: amelyik posztjuk elöl rendre
    labdát szed, annak az oldalán tilos a kihozatalt vezetni — a
    kapus a másik oldalra indítson, a felhozó ne fusson a sávjába.
    Saját csapatra: a letámadás-motor terhelése és biztosítása
    (mögötte nyílik a tér) a téma.

    Visszatérés csapatonként: {"high" (poszthoz kötött
    elöl-szerzés), "roles": {poszt: darab}, "main_role",
    "share_pct", "verdict"} — az ítélet None, ha nincs meg a
    HSR_MIN_HIGH, vagy egyik poszt sem éri el a HSR_SHARE_PCT-t.
    """
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    hs = high_steal_players(match, config)

    out: dict = {side: {"high": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in hs[side]["players"]:
            if not row["high"]:
                continue
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["high"])
            rec["high"] += row["high"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["high"] >= HSR_MIN_HIGH:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["high"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= HSR_SHARE_PCT:
                rec["verdict"] = (
                    f"az elöl-szerzéseik {share:.0f}%-a a(z) "
                    f"{poszt} posztjuknál születik ({rec['high']} "
                    "letámadás-szerzésből) — az ő oldalán tilos a "
                    "kihozatalt vezetni: a kapus a másik oldalra "
                    "indítson")
    return out


# Kettőzőpáros-poszt: ennyi poszthoz kötött kettőzött kocka kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy a
# kettőzésük egy védő-pároson áll.
DPP_MIN_FRAMES = 100
DPP_SHARE_PCT = 60.0


def doubling_pair_roles(match, config=None) -> dict:
    """Kettőzőpáros-poszt: MELYIK VÉDŐ-KETTŐSÜK kettőz együtt.

    A kettőző-poszt az egy védőt nevezi meg — ez a párost: a
    kettőzött (két védős) labdás kockákon a labdáshoz legközelebbi
    KÉT védő (támadó-fázisból becsült) posztját rendezetlen párként
    számolja. Így a kettőzés-szokásuk akkor is látszik, ha a nevek
    cserélődnek.

    Edzőileg a kioldó-passz térképe: ha a kettőzésük mindig
    ugyanattól a párostól jön, a kettőző által elhagyott ember FIX —
    a kettőzött játékosunk kioldó passza oda menjen, még a szorítás
    előtt begyakorolva. Saját csapatra: a kettőző-páros forgatása a
    kiszámíthatóság ellen.

    Visszatérés csapatonként (a KETTŐZŐ, védő oldal): {"frames"
    (párhoz kötött kettőzött kocka), "roles": {"A+B": kocka},
    "main_role", "share_pct", "verdict"} — az ítélet None, ha nincs
    meg a DPP_MIN_FRAMES, vagy egyik pár sem éri el a
    DPP_SHARE_PCT-t.
    """
    import math

    from .decisions import ball_holder
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)

    out: dict = {side: {"frames": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for f in match.frames:
        holder = ball_holder(f, config)
        if holder is None or holder.team is None \
                or holder.role == "kapus":
            continue
        deff = "away" if holder.team.value == "home" else "home"
        near = sorted(
            ((math.hypot(p.x - holder.x, p.y - holder.y), p)
             for p in f.players
             if p.team is not None and p.team != holder.team
             and p.role != "kapus"),
            key=lambda dp: dp[0])
        close = [p for (d, p) in near if d <= DOUBLE_TEAM_M]
        if len(close) < 2:
            continue
        r1 = roles[deff].get(close[0].track_id)
        r2 = roles[deff].get(close[1].track_id)
        if r1 is None or r2 is None:
            continue
        kulcs = "+".join(sorted((r1["poszt"], r2["poszt"])))
        rec = out[deff]
        rec["roles"][kulcs] = rec["roles"].get(kulcs, 0) + 1
        rec["frames"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["frames"] >= DPP_MIN_FRAMES:
            par = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][par] / rec["frames"]
            rec["main_role"] = par
            rec["share_pct"] = round(share, 1)
            if share >= DPP_SHARE_PCT:
                rec["verdict"] = (
                    f"a kettőzésük a(z) {par} védő-pároson áll "
                    f"({share:.0f}%-a a kettőzött időnek) — a "
                    "kettőző elhagyott embere fix: a kioldó passz "
                    "oda menjen, még a szorítás előtt begyakorolva")
    return out


# Elöl lógó poszt: ennyi védekezett kocka kell posztonként az
# ítélethez, és ez alatti hazaérési arány jelenti, hogy a poszt a
# védekezett idő nagy részét az ellenfél térfelén tölti.
RCR_MIN_FRAMES = 200
RCR_LOW_PCT = 70.0


def recovery_roles(match, config=None) -> dict:
    """Elöl lógó poszt: MELYIK POSZTJUK nem ér haza védekezni.

    A visszaérés-fegyelem rétege (recovery_discipline) az embert
    nevezi meg — ez a posztot: a védekezett kockákat posztonként
    összegzi, és megnézi, melyik poszt tölti az idejének nagy részét
    az ellenfél térfelén. A visszafutás-poszttól abban tér el, hogy
    az a kontrák VÉGÉN mért lemaradást nézi, ez pedig a védekezett
    IDŐ eloszlását: a tartósan elöl maradó posztot mutatja meg.

    Edzőileg ez a gyors indítás iránya: az elöl lógó poszt mögött
    nincs védő — a kapus indítása és a felhozatal az ő oldalára
    menjen, mert ott a pálya üres. Saját csapatra: a visszaérés
    fegyelem-kérdés, és a poszt terhelése (kondíció, csere) is
    felülvizsgálandó.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal): {"frames"
    (védekezett kocka), "roles": {poszt: {"frames", "home_frames",
    "share_pct"}}, "main_role", "share_pct", "verdict"} — az ítélet
    None, ha egyik poszt sem éri el az RCR_MIN_FRAMES-t az
    RCR_LOW_PCT alatti hazaérési aránnyal.
    """
    from ..models.tracking import Team
    from .decisions import ball_holder
    from .roles import estimate_positions
    from .tactics import COURT_LENGTH_M, TacticsConfig

    config = config or TacticsConfig()
    half = COURT_LENGTH_M / 2.0
    roles = estimate_positions(match, config)

    acc: dict = {"home": {}, "away": {}}
    for f in match.frames:
        holder = ball_holder(f, config)
        if holder is None or holder.team is None:
            continue
        deff = Team.AWAY if holder.team == Team.HOME else Team.HOME
        own_x = config.own_goal_x(deff)
        if abs(holder.x - own_x) > half:
            continue   # csak felállt/rendezett védekezés
        for p in f.players:
            if p.team != deff or p.role == "kapus":
                continue
            rec_role = roles[deff.value].get(p.track_id)
            if rec_role is None:
                continue
            rec = acc[deff.value].setdefault(rec_role["poszt"], [0, 0])
            rec[0] += 1
            if abs(p.x - own_x) <= half:
                rec[1] += 1

    out: dict = {}
    for side in ("home", "away"):
        by_role = {
            poszt: {"frames": n, "home_frames": h,
                    "share_pct": round(100.0 * h / n, 1) if n else None}
            for poszt, (n, h) in sorted(acc[side].items(),
                                        key=lambda kv: -kv[1][0])}
        main_role = None
        share_pct = None
        verdict = None
        cands = [(poszt, r) for poszt, r in by_role.items()
                 if r["frames"] >= RCR_MIN_FRAMES
                 and r["share_pct"] < RCR_LOW_PCT]
        if cands:
            poszt, r = min(cands, key=lambda pr: pr[1]["share_pct"])
            main_role = poszt
            share_pct = r["share_pct"]
            verdict = (
                f"a(z) {poszt} posztjuk lóg elöl: a védekezett "
                f"idejének csak {share_pct:.0f}%-ában van a saját "
                f"térfelén ({r['frames']} védekezett kockából) — a "
                "gyors indítást az ő oldalára vezessétek: mögötte "
                "üres a pálya")
        out[side] = {
            "frames": sum(r["frames"] for r in by_role.values()),
            "roles": by_role, "main_role": main_role,
            "share_pct": share_pct, "verdict": verdict}
    return out


# Visszaállás-idő küszöbei: ennyi mért lövés kell az ítélethez, ennyi
# védő legyen otthon, ennyi másodperc után nevezzük lassúnak a
# visszaállást, és ennyi idő alatt keressük (utána feladjuk).
RTT_MIN_SHOTS = 4
RTT_BACK_PLAYERS = 4
RTT_SLOW_S = 8.0
RTT_MAX_S = 20.0


def retreat_time(match, config=None) -> dict:
    """Visszaállás-idő: HÁNY MÁSODPERC alatt állnak vissza a lövésük után.

    A visszafutás-poszt azt mondja meg, KI marad le — ez azt, MENNYI
    IDŐ alatt áll össze a faluk: minden lövésük után megméri, mennyi
    idő telik el, míg RTT_BACK_PLAYERS mezőnyjátékosuk a saját
    térfelükre ér. Ha RTT_MAX_S alatt sem áll össze, a szakasz a
    felső korláttal számít (a lassúságot nem hallgatjuk el).

    Edzőileg ez a kontra-terv egy száma: RTT_SLOW_S fölött a lövésük
    után indított első hullám még üres pályát talál — a kapusnak
    azonnal indítania kell, nem szabad megvárni a felállt támadást.
    Saját csapatra: a lövés pillanatában kijelölt első visszafutó és
    a labda mögötti biztosítás a téma.

    Visszatérés csapatonként: {"shots" (mért lövés), "avg_s" (átlagos
    visszaállási idő), "slow" (RTT_SLOW_S fölötti eset), "verdict"} —
    az ítélet None, ha nincs meg az RTT_MIN_SHOTS, vagy az átlag a
    küszöb alatt marad.
    """
    from ..models.tracking import Team
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    max_frames = round(RTT_MAX_S * fps)
    frames_by_t = {f.t: f for f in match.frames}
    times = sorted(frames_by_t)

    out: dict = {side: {"shots": 0, "avg_s": None, "slow": 0,
                        "verdict": None}
                 for side in ("home", "away")}
    sums = {"home": 0.0, "away": 0.0}
    for e in detect_shots(match, config):
        if e.type not in (EventType.SHOT, EventType.GOAL):
            continue
        side = e.team.value
        team = Team.HOME if side == "home" else Team.AWAY
        own_x = config.own_goal_x(team)
        # A saját térfél: a saját kapu felőli oldal a pálya közepéhez
        # (20 m) képest.
        felezo = 20.0
        haza = None
        for t in times:
            if t < e.t:
                continue
            if t > e.t + max_frames:
                break
            fr = frames_by_t[t]
            n = 0
            for p in fr.players:
                if p.team != team or p.role == "kapus":
                    continue
                if (p.x <= felezo if own_x < felezo else p.x >= felezo):
                    n += 1
            if n >= RTT_BACK_PLAYERS:
                haza = (t - e.t) / fps
                break
        # Ha az ablakban nem állt össze a fal, a felső korláttal
        # számolunk — a lassúságot nem hallgatjuk el.
        if haza is None:
            haza = RTT_MAX_S
        rec = out[side]
        rec["shots"] += 1
        sums[side] += haza
        if haza > RTT_SLOW_S:
            rec["slow"] += 1

    for side in ("home", "away"):
        rec = out[side]
        if rec["shots"] <= 0:
            continue
        avg = sums[side] / rec["shots"]
        rec["avg_s"] = round(avg, 1)
        if rec["shots"] >= RTT_MIN_SHOTS and avg > RTT_SLOW_S:
            rec["verdict"] = (
                f"a lövésük után átlag {avg:.1f} másodperc, míg "
                f"{RTT_BACK_PLAYERS} emberük hazaér ({rec['shots']} "
                f"lövésből {rec['slow']} volt {RTT_SLOW_S:.0f} mp "
                "fölött) — a kapusnak azonnal indítania kell: az "
                "első hullám még üres pályát talál")
    return out


# Lepattanó-szedő poszt küszöbei: a védés utáni ablak, ennyi
# poszthoz kötött megszerzett kipattanó kell az ítélethez, és ekkora
# részarány a vezető posztnak.
RBC_WINDOW_S = 4.0
RBC_MIN_REBOUNDS = 3
RBC_SHARE_PCT = 60.0
# A kapus ennyi ideig lehet a labdánál: ez a hárítás pillanata. Ennél
# hosszabb tartás már FOGÁS (nincs kipattanó, nincs mit szedni).
RBC_GK_HOLD_S = 1.0


def defensive_rebound_roles(match, config=None) -> dict:
    """Lepattanó-szedő poszt: VÉDÉS UTÁN kinél marad a labda.

    A kapus-kipattanó (gk_rebound_control) azt mondja meg, fogja-e a
    kapus a labdát, a lepattanó-poszt (second_chance_roles) azt, ki lő
    másodszor — ez a védekező oldalt: a kapusuk védése utáni
    RBC_WINDOW_S-en belül megszerzett kipattanókat a labdát MEGSZERZŐ
    védőjük posztjához írja.

    Edzőileg ez a második helyzet terve: ha a kipattanókat rendre
    ugyanaz a posztjuk szedi össze, oda kell küldeni a berobbanó
    embert (a szélső vagy a beálló becsúszása a kipattanó-zónába) —
    a második lövés a legolcsóbb gól. Saját csapatra: a
    kipattanó-felelősség kiosztható feladat, nem véletlen.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal): {"rebounds"
    (poszthoz kötött szerzett kipattanó), "roles": {poszt: darab},
    "main_role", "share_pct", "verdict"} — az ítélet None, ha nincs
    meg a RBC_MIN_REBOUNDS, vagy egyik poszt sem éri el a
    RBC_SHARE_PCT-t.
    """
    from .decisions import ball_holder
    from .roles import estimate_positions
    from .tactics import TacticsConfig
    from .xg import match_xg

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = round(RBC_WINDOW_S * fps)
    gk_hold = round(RBC_GK_HOLD_S * fps)
    roles = estimate_positions(match, config)
    frames_by_t = {f.t: f for f in match.frames}
    times = sorted(frames_by_t)
    xg = match_xg(match, config)

    out: dict = {side: {"rebounds": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for sh in xg["shots"]:
        if sh["outcome"] != "save":
            continue
        # A VÉDEKEZŐ oldal a lövő ellenfele.
        side = "away" if sh["team"] == "home" else "home"
        gk_frames = 0
        for t in times:
            if t <= sh["t"]:
                continue
            if t > sh["t"] + win:
                break
            holder = ball_holder(frames_by_t[t], config)
            if holder is None:
                continue
            if holder.team.value != side:
                break   # a támadó szerezte vissza a labdát
            if holder.role == "kapus":
                # A hárítás pillanata: a kapus még a labdánál van.
                gk_frames += 1
                if gk_frames > gk_hold:
                    break   # nem kipattanó, hanem fogás
                continue
            rec_role = roles[side].get(holder.track_id)
            if rec_role is None:
                break
            poszt = rec_role["poszt"]
            rec = out[side]
            rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1
            rec["rebounds"] += 1
            break

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["rebounds"] >= RBC_MIN_REBOUNDS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["rebounds"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= RBC_SHARE_PCT:
                rec["verdict"] = (
                    f"a kipattanók {share:.0f}%-át a(z) {poszt} "
                    f"posztjuk szedi össze ({rec['rebounds']} "
                    "megszerzett kipattanóból) — oda kell küldeni a "
                    "berobbanó embert: a második lövés a legolcsóbb "
                    "gól")
    return out


# Visszaállás ára: ennyi másodpercen belüli kapott gól számít a
# lövésük utáni büntetésnek, ennyi mért lövés kell az ítélethez, és
# e fölötti arány már drága.
RTP_WINDOW_S = 12.0
RTP_MIN_SHOTS = 6
RTP_COSTLY_PCT = 20.0


def retreat_punishment(match, config=None) -> dict:
    """Visszaállás ára: a GÓL NÉLKÜLI lövésük után kapott gyors gól.

    A visszaállás-idő (retreat_time) azt mondja meg, HÁNY MÁSODPERC
    alatt áll össze a faluk — ez azt, MENNYIBE KERÜL: a gól nélkül
    záruló lövéseiket (védés, mellé, blokk) nézi, és megszámolja,
    hányat követett RTP_WINDOW_S-en belül az ellenfél gólja. A
    góllal záruló lövések kimaradnak: onnan középkezdés jön, nem
    lerohanás.

    Edzőileg ez a lassú visszaállás számlája: ha a lövéseik ötödét
    gyors kapott gól követi, nem a fal minősége a baj, hanem az,
    hogy a fal nincs ott. Ellenük ez az olvasat, hogy minden
    védésből azonnal indítani kell; saját csapatra a lövés
    pillanatában kijelölt visszafutó és a labda mögötti biztosítás.

    Visszatérés csapatonként: {"shots" (gól nélküli lövés),
    "punished" (gyors kapott góllal büntetett), "rate_pct",
    "verdict"} — a rate_pct None RTP_MIN_SHOTS alatt, az ítélet
    None, ha az arány a RTP_COSTLY_PCT alatt marad.
    """
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = round(RTP_WINDOW_S * fps)
    shots = [e for e in detect_shots(match, config)
             if e.type in (EventType.SHOT, EventType.GOAL)]
    goals = sorted((e.t, e.team.value) for e in shots
                   if e.type == EventType.GOAL)

    out: dict = {side: {"shots": 0, "punished": 0, "rate_pct": None,
                        "verdict": None}
                 for side in ("home", "away")}
    for e in shots:
        if e.type == EventType.GOAL:
            continue      # gól után középkezdés jön, nem lerohanás
        side = e.team.value
        other = "away" if side == "home" else "home"
        rec = out[side]
        rec["shots"] += 1
        if any(gs == other and 0 <= gt - e.t <= win
               for (gt, gs) in goals):
            rec["punished"] += 1

    for side in ("home", "away"):
        rec = out[side]
        if rec["shots"] < RTP_MIN_SHOTS:
            continue
        rate = 100.0 * rec["punished"] / rec["shots"]
        rec["rate_pct"] = round(rate, 1)
        if rate >= RTP_COSTLY_PCT:
            rec["verdict"] = (
                f"a gól nélküli lövéseik {rate:.0f}%-át gyors kapott "
                f"gól követi ({rec['punished']} a {rec['shots']} "
                f"lövésből, {RTP_WINDOW_S:.0f} másodpercen belül) — "
                "ez a lassú visszaállás ára: minden védésükből "
                "azonnal indítani kell, mert a fal még nincs ott")
    return out


# Kipattanó-szedők: ennyi megszerzett kipattanótól emeljük ki a
# játékost (a kipattanó ritkább, mint a labdaszerzés).
RBCP_MIN_REBOUNDS = 2


def defensive_rebound_players(match, config=None) -> dict:
    """Kipattanó-szedők: KI SZEDI ÖSSZE a kipattanót védés után.

    A lepattanó-szedő poszt (defensive_rebound_roles) a POSZTOT
    nevezi meg — ez az EMBERT: ugyanazokat a megszerzett
    kipattanókat játékosonként számolja.

    Edzőileg ez a berobbanó ember célpontja: aki rendre összeszedi a
    kipattanókat, azt a második helyzetnél blokkolni kell (test,
    elzárás a kipattanó-zónában). Saját csapatra: a kipattanó-munka
    elismerése és a felelősség kiosztása — nem véletlen, hanem
    feladat.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal): {"rebounds",
    "players": [{"player_id", "jersey", "rebounds"}], "top"} — a
    "top" az első játékos, ha legalább RBCP_MIN_REBOUNDS kipattanója
    van, különben None.
    """
    from .decisions import ball_holder
    from .tactics import TacticsConfig
    from .xg import match_xg

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = round(RBC_WINDOW_S * fps)
    gk_hold = round(RBC_GK_HOLD_S * fps)
    frames_by_t = {f.t: f for f in match.frames}
    times = sorted(frames_by_t)
    xg = match_xg(match, config)

    jersey: dict = {}
    for f in match.frames:
        for p in f.players:
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)

    tally: dict = {"home": {}, "away": {}}
    for sh in xg["shots"]:
        if sh["outcome"] != "save":
            continue
        side = "away" if sh["team"] == "home" else "home"
        gk_frames = 0
        for t in times:
            if t <= sh["t"]:
                continue
            if t > sh["t"] + win:
                break
            holder = ball_holder(frames_by_t[t], config)
            if holder is None:
                continue
            if holder.team.value != side:
                break
            if holder.role == "kapus":
                gk_frames += 1
                if gk_frames > gk_hold:
                    break
                continue
            tally[side][holder.track_id] = (
                tally[side].get(holder.track_id, 0) + 1)
            break

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "rebounds": n}
                for pid, n in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1])]
        top = (rows[0]
               if rows and rows[0]["rebounds"] >= RBCP_MIN_REBOUNDS
               else None)
        out[side] = {"rebounds": sum(r["rebounds"] for r in rows),
                     "players": rows, "top": top}
    return out


# Emberfogás-váltás küszöbei: félidőnként ennyi őrzés-kocka kell egy
# párostól, ez alatt a távolság alatt beszélünk emberfogásról, és
# ekkora arányú szorosodás számít váltásnak.
MSH_MIN_FRAMES = 250
MSH_TIGHT_M = 2.0
MSH_DROP_RATIO = 0.7


def marking_shift(match, config=None) -> dict:
    """Emberfogás-váltás: A SZÜNET UTÁN emberfogásra váltanak-e.

    Az őrzési párok (marking_pairs) a meccs egészére mondják meg, ki
    kit fogott — ez a VÁLTÁST: félidőnként megkeresi a legszorosabb
    párost, és összeveti a két átlagtávolságot. A szünetben hozott
    emberfogás a leggyakoribb meccs közbeni tervmódosítás, és a
    felkészülésben ez a legdrágább meglepetés.

    Edzőileg: ha a szünet után emberfogásra váltanak, a fogott
    játékosnak el kell húznia a védőjét (kifutás a szélre, mély
    beállós mozgás), és a felszabaduló területet kell megjátszani —
    nem őt erőltetni. Ha elengedik az emberfogást, épp fordítva: a
    korábban fogott ember visszakapja a labdát.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal): {"fh_dist_m",
    "fh_pair", "sh_dist_m", "sh_pair", "verdict"} — az ítélet None
    félidő-jel nélkül, kevés őrzés-kocka (MSH_MIN_FRAMES) esetén,
    vagy ha a szorosság érdemben nem változik.
    """
    from .halftime import detect_halftime
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    empty = {"fh_dist_m": None, "fh_pair": None, "sh_dist_m": None,
             "sh_pair": None, "verdict": None}
    out = {side: dict(empty) for side in ("home", "away")}
    ht = detect_halftime(match)
    if ht is None or not match.frames:
        return out

    first = marking_pairs(match, config, until_t=ht)
    whole = marking_pairs(match, config)

    for side in ("home", "away"):
        # Az első félidő párosai kulcs szerint (védő, támadó).
        fh = {(p["defender"], p["attacker"]):
              [p["frames"], p["frames"] * p["avg_dist_m"]]
              for p in first[side]["pairs"]}
        best_fh = best_sh = None
        for p in whole[side]["pairs"]:
            key = (p["defender"], p["attacker"])
            all_n = p["frames"]
            all_sum = p["frames"] * p["avg_dist_m"]
            f_n, f_sum = fh.get(key, [0, 0.0])
            # A második félidő ugyanennek a párosnak a maradéka.
            s_n, s_sum = all_n - f_n, all_sum - f_sum
            if f_n >= MSH_MIN_FRAMES:
                d = f_sum / f_n
                if best_fh is None or d < best_fh[0]:
                    best_fh = (d, key)
            if s_n >= MSH_MIN_FRAMES:
                d = s_sum / s_n
                if best_sh is None or d < best_sh[0]:
                    best_sh = (d, key)
        rec = out[side]
        if best_fh is not None:
            rec["fh_dist_m"] = round(best_fh[0], 2)
            rec["fh_pair"] = list(best_fh[1])
        if best_sh is not None:
            rec["sh_dist_m"] = round(best_sh[0], 2)
            rec["sh_pair"] = list(best_sh[1])
        if best_fh is None or best_sh is None:
            continue
        if (best_sh[0] <= MSH_TIGHT_M
                and best_sh[0] <= MSH_DROP_RATIO * best_fh[0]):
            rec["verdict"] = (
                f"a szünet után emberfogásra váltottak (a "
                f"legszorosabb páros {best_sh[0]:.1f} m az első "
                f"félidei {best_fh[0]:.1f} m helyett) — a fogott "
                "játékos húzza el a védőjét, és a felszabaduló "
                "területet kell megjátszani")
        elif (best_fh[0] <= MSH_TIGHT_M
                and best_fh[0] <= MSH_DROP_RATIO * best_sh[0]):
            rec["verdict"] = (
                f"a szünet után elengedték az emberfogást (a "
                f"legszorosabb páros {best_sh[0]:.1f} m az első "
                f"félidei {best_fh[0]:.1f} m helyett) — a korábban "
                "fogott emberünk visszakapja a labdát, rá lehet "
                "építeni a második félidőt")
    return out
