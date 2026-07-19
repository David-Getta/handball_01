"""Szabály-értő réteg — a bírói döntések LENYOMATÁNAK felismerése.

A bíró karjelzéseit a rendszer (még) nem látja: ahhoz póz-becslő modell
kellene, a bírót ma csak kiszűrjük a képből (sárga mez). Amit viszont a
pálya-koordinátákból megbízhatóan fel lehet ismerni, az a döntések
KÖVETKEZMÉNYE — és az edzőt valójában ez érdekli:

- KIÁLLÍTÁS (emberhátrány/emberelőny): egy csapat tartósan 5 mezőny-
  játékossal játszik, míg a másik 6-tal → 2 perces kiállítás lenyomata.
- HÉTMÉTERES: a labda mozdulatlanul áll a 7 m-es pont környékén, mielőtt
  elvégzik a dobást — a büntető jellegzetes, összetéveszthetetlen képe.
- PASSZÍV JÁTÉK KOCKÁZAT: hosszan húzódó felállt támadás lövés nélkül —
  ahol a bíró tipikusan passzívot jelez.

Minden felismerés magyarázható (mért számokon áll), és a meglévő
Suspension/RosterTimeline adatmodellt tölti fel automatikusan — eddig ez
kézi kitöltésre várt. Tiszta adatfeldolgozás, videó nélkül tesztelhető.
"""

from __future__ import annotations

import math
from typing import Optional

from ..models.tracking import Match, PositionSource, Team
from ..models.events import Suspension
from .calibration import COURT_LENGTH_M, COURT_WIDTH_M
from .tactics import TacticsConfig

# Kiállítás-felismerés küszöbei:
PP_WINDOW_S = 10.0        # ekkora ablakonként számoljuk a pályán lévőket
PP_MIN_PRESENCE = 0.2     # egy track az ablak >=20%-ában látszódjon (zaj ki)
PP_MIN_S = 45.0           # legalább ennyi ideig tartó hiány = kiállítás
FIELD_PLAYERS = 6         # teljes létszám mezőnyjátékosból (kapus nélkül)

# Hétméteres-felismerés küszöbei:
SEVEN_M = 7.0             # a büntetőpont távolsága a kaputól
SEVEN_TOL_M = 1.2         # ennyire lehet a labda a ponttól
SEVEN_STATIC_S = 0.8      # legalább ennyi ideig áll a labda
SEVEN_MAX_SPEED = 0.7     # eközben legfeljebb ennyit mozog (m/s)
SEVEN_DEBOUNCE_S = 10.0   # két hétméteres között legalább ennyi idő

# Passzív játék: felállt támadás lövés nélkül ennél hosszabban.
PASSIVE_MIN_S = 35.0


def field_count_timeline(match: Match, window_s: float = PP_WINDOW_S) -> list[dict]:
    """Ablakonként a pályán látott MEZŐNYJÁTÉKOS-trackek száma csapatonként.

    Mért pozíciókból számol (a becslő kitöltése nem torzít), a kapust
    (role="kapus") nem számolja, és a nagyon rövid ideig látszó trackeket
    (az ablak <20%-a) zajként kihagyja. A pásztázó kamera miatt EGY kockán
    nem látszik mindenki — ablakon belül igen.
    """
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = max(1, round(window_s * fps))
    total = len(match.frames)
    out: list[dict] = []
    for w0 in range(0, total, win):
        frames = match.frames[w0:w0 + win]
        seen: dict[int, list] = {}
        for f in frames:
            for p in f.players:
                if p.source != PositionSource.MEASURED or p.role == "kapus":
                    continue
                rec = seen.setdefault(p.track_id, [0, p.team])
                rec[0] += 1
        counts = {Team.HOME: 0, Team.AWAY: 0}
        min_frames = max(1, round(len(frames) * PP_MIN_PRESENCE))
        for (n, team) in seen.values():
            if n >= min_frames:
                counts[team] += 1
        out.append({"start_frame": match.frames[w0].t,
                    "home": counts[Team.HOME], "away": counts[Team.AWAY]})
    return out


def detect_powerplay(match: Match) -> list[dict]:
    """Emberhátrány-szakaszok (kiállítás lenyomata).

    Egy csapat akkor van emberhátrányban, ha az ablakában legfeljebb 5
    mezőnyjátékosa látszik, míg az ellenfélből legalább 6 — és ez
    legalább PP_MIN_S ideig áll fenn.

    Visszatérés: [{"team_down", "start_frame", "end_frame", "duration_s"}].
    """
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    tl = field_count_timeline(match)
    if not tl:
        return []
    win_frames = (tl[1]["start_frame"] - tl[0]["start_frame"]) if len(tl) > 1 \
        else len(match.frames)

    out: list[dict] = []
    for down, other in (("home", "away"), ("away", "home")):
        run_start = None
        for i in range(len(tl) + 1):
            w = tl[i] if i < len(tl) else None
            active = (w is not None and w[down] <= FIELD_PLAYERS - 1
                      and w[other] >= FIELD_PLAYERS)
            if active and run_start is None:
                run_start = i
            elif not active and run_start is not None:
                n_win = i - run_start
                dur_s = n_win * win_frames / fps
                if dur_s >= PP_MIN_S:
                    start_f = tl[run_start]["start_frame"]
                    end_f = start_f + n_win * win_frames - 1
                    out.append({"team_down": down,
                                "start_frame": start_f,
                                "end_frame": min(end_f, match.frames[-1].t),
                                "duration_s": round(dur_s, 1)})
                run_start = None
    out.sort(key=lambda w: w["start_frame"])
    return out


def suspensions_from_powerplay(match: Match) -> list[Suspension]:
    """A felismert emberhátrányok Suspension objektumokként — a meglévő
    RosterTimeline adatmodellhez (eddig kézi kitöltésre várt)."""
    return [Suspension(team=Team.HOME if w["team_down"] == "home" else Team.AWAY,
                       start_t=w["start_frame"],
                       duration_t=w["end_frame"] - w["start_frame"] + 1)
            for w in detect_powerplay(match)]


def detect_seven_meters(match: Match,
                        config: Optional[TacticsConfig] = None) -> list[dict]:
    """Hétméteres (büntetődobás) felismerése.

    Jele: a labda a 7 m-es pont környékén (a kaputól ~7 m-re, középen)
    mozdulatlanul áll legalább SEVEN_STATIC_S ideig — a normál játékban a
    labda ott sosem áll meg. A dobó csapat a kapu támadója.

    Visszatérés: [{"t", "team", "goal_x"}] időrendben.
    """
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    need = max(2, round(SEVEN_STATIC_S * fps))
    debounce = round(SEVEN_DEBOUNCE_S * fps)

    out: list[dict] = []
    run = {0.0: 0, COURT_LENGTH_M: 0}
    last_emit = {0.0: -10 ** 9, COURT_LENGTH_M: -10 ** 9}
    prev = None
    for f in match.frames:
        b = f.ball
        if b is None:
            run = {k: 0 for k in run}
            prev = None
            continue
        speed = (math.hypot(b.x - prev[0], b.y - prev[1]) * fps
                 if prev is not None else 0.0)
        for goal_x in (0.0, COURT_LENGTH_M):
            near_spot = (abs(abs(b.x - goal_x) - SEVEN_M) <= SEVEN_TOL_M
                         and abs(b.y - COURT_WIDTH_M / 2.0) <= 2.0)
            if near_spot and speed <= SEVEN_MAX_SPEED:
                run[goal_x] += 1
                if run[goal_x] == need and f.t - last_emit[goal_x] >= debounce:
                    attacker = (Team.HOME
                                if config.attacks_toward_x(Team.HOME) == goal_x
                                else Team.AWAY)
                    out.append({"t": f.t - need + 1, "team": attacker.value,
                                "goal_x": goal_x})
                    last_emit[goal_x] = f.t
            else:
                run[goal_x] = 0
        prev = (b.x, b.y)
    return out


def passive_play_risks(match: Match,
                       config: Optional[TacticsConfig] = None) -> list[dict]:
    """Passzív játék kockázata: felállt támadás lövés nélkül, hosszan.

    Visszatérés: a szóban forgó támadás-szakaszok (attack_types alakban).
    """
    config = config or TacticsConfig()
    from .attack_types import AttackType, classify_attacks
    from .event_detection import EventType, detect_shots

    shot_ts = [e.t for e in detect_shots(match, config)
               if e.type in (EventType.SHOT, EventType.GOAL)]
    out: list[dict] = []
    for a in classify_attacks(match, config):
        if a["type"] != AttackType.POSITIONAL.value:
            continue
        if a["duration_s"] < PASSIVE_MIN_S:
            continue
        if any(a["start_frame"] <= t <= a["end_frame"] for t in shot_ts):
            continue
        out.append(a)
    return out


# A 7 m-es után ennyi másodpercen belüli lövést párosítjuk hozzá kimenetelként.
SEVEN_OUTCOME_WINDOW_S = 6.0


# A hetes iránya: a labda kapu-síkbeli y-eltérése ennél nagyobb → szélső sáv.
SEVEN_DIR_SIDE_M = 0.5
# Csak akkor mondunk irányt, ha a labda ennyire megközelítette a kapu síkját.
SEVEN_DIR_MAX_PLANE_M = 1.5


def _seven_direction(match: Match, t0: int, goal_x: float,
                     fps: float) -> Optional[str]:
    """Merre ment a hetes a kapuban (bal/közép/jobb) a DOBÓ szemszögéből.

    A lövés utáni ~1 mp-ben azt a kockát keressük, ahol a labda a
    legközelebb járt a kapu síkjához, és az ottani oldal-eltérésből
    (y a kapu közepéhez képest) mondjuk meg a sávot. None, ha a labda
    nem került a sík közelébe (pl. eltakarták).
    """
    cy = COURT_WIDTH_M / 2.0
    horizon = t0 + round(1.0 * fps)
    best = None  # (kapu-sík távolság, y)
    for f in match.frames:
        if f.t < t0 or f.t > horizon or f.ball is None:
            continue
        d = abs(f.ball.x - goal_x)
        if best is None or d < best[0]:
            best = (d, f.ball.y)
    if best is None or best[0] > SEVEN_DIR_MAX_PLANE_M:
        return None
    off = best[1] - cy
    # A dobó szemszögéből: a +x kapura nézve az alacsony y a BAL oldal;
    # a -x kapura dobva tükrözünk.
    if goal_x < COURT_LENGTH_M / 2.0:
        off = -off
    if off <= -SEVEN_DIR_SIDE_M:
        return "bal"
    if off >= SEVEN_DIR_SIDE_M:
        return "jobb"
    return "közép"


def seven_meter_outcomes(match: Match,
                         config: Optional[TacticsConfig] = None) -> list[dict]:
    """A felismert hétméteresek KIMENETELLEL: gól / védés / kihagyva.

    A 7 m-es esemény utáni SEVEN_OUTCOME_WINDOW_S-en belüli, ugyanarra a
    kapura, ugyanattól a csapattól jövő ELSŐ lövés-eseményt párosítjuk
    hozzá (a lövés-kimenetel a meglévő detect_shots detail-jéből jön).
    Ha az ablakban nincs lövés, az outcome "ismeretlen" (pl. újra
    lefújták, vagy a labda nem látszott).

    Visszatérés: [{"t", "team", "goal_x", "outcome", "shooter_id",
    "irany"}] — az irany a kapun belüli sáv (bal/közép/jobb) a dobó
    szemszögéből, None, ha nem mérhető."""
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = round(SEVEN_OUTCOME_WINDOW_S * fps)
    shots = [e for e in detect_shots(match, config)
             if e.type in (EventType.SHOT, EventType.GOAL)]

    out = []
    for sm in detect_seven_meters(match, config):
        rec = dict(sm)
        rec["outcome"] = "ismeretlen"
        rec["shooter_id"] = None
        rec["irany"] = None
        for e in shots:
            if not (sm["t"] <= e.t <= sm["t"] + win):
                continue
            if e.team.value != sm["team"]:
                continue
            rec["outcome"] = ("gól" if e.type == EventType.GOAL else
                              "védés" if (e.detail or {}).get("outcome") == "save"
                              else "kihagyva")
            rec["shooter_id"] = e.player_id
            rec["irany"] = _seven_direction(match, e.t, sm["goal_x"],
                                            fps)
            break
        out.append(rec)
    return out


def seven_meter_summary(match: Match,
                        config: Optional[TacticsConfig] = None) -> dict:
    """Hétméteres-mérleg csapatonként: kísérlet / gól / védés / kihagyva."""
    out = {side: {"attempts": 0, "goals": 0, "saved": 0, "missed": 0}
           for side in ("home", "away")}
    for sm in seven_meter_outcomes(match, config):
        rec = out[sm["team"]]
        rec["attempts"] += 1
        if sm["outcome"] == "gól":
            rec["goals"] += 1
        elif sm["outcome"] == "védés":
            rec["saved"] += 1
        elif sm["outcome"] == "kihagyva":
            rec["missed"] += 1
    return out


def rules_report(match: Match) -> dict:
    """A szabály-értő réteg összegzése egy hívásban (az API-nak)."""
    return {
        "powerplay": detect_powerplay(match),
        "powerplay_efficiency": powerplay_efficiency(match),
        # A hétméteresek kimenetellel (gól/védés/kihagyva) mennek ki.
        "seven_meters": seven_meter_outcomes(match),
        "seven_meter_summary": seven_meter_summary(match),
        "passive_risk": passive_play_risks(match),
    }

def powerplay_efficiency(match: Match,
                         config: Optional[TacticsConfig] = None) -> dict:
    """Emberelőny-hatékonyság: mire váltja a csapat a kiállításokat.

    Csapatonként szétválogatja a kapura tartó lövéseket (gól + védés)
    aszerint, hogy EMBERELŐNYBEN (az ellenfél kiállítása alatt), EGYENLŐ
    létszámnál vagy EMBERHÁTRÁNYBAN születtek — és számolja a hátrányban
    kapott gólokat is.

    Visszatérés csapatonként: {"pp_shots", "pp_goals", "pp_eff_pct",
    "eq_shots", "eq_goals", "eq_eff_pct", "pp_seconds",
    "sh_seconds", "sh_conceded"} — üres szótár, ha nem volt kiállítás.
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    windows = detect_powerplay(match)
    if not windows:
        return {}

    def _down_at(t: int) -> Optional[str]:
        for w in windows:
            if w["start_frame"] <= t <= w["end_frame"]:
                return w["team_down"]
        return None

    out = {team: {"pp_shots": 0, "pp_goals": 0, "pp_eff_pct": 0.0,
                  "eq_shots": 0, "eq_goals": 0, "eq_eff_pct": 0.0,
                  "pp_seconds": 0.0, "sh_seconds": 0.0, "sh_conceded": 0}
           for team in ("home", "away")}
    for w in windows:
        down = w["team_down"]
        up = "away" if down == "home" else "home"
        out[up]["pp_seconds"] += w["duration_s"]
        out[down]["sh_seconds"] += w["duration_s"]

    for e in detect_shots(match, config):
        outcome = (e.detail or {}).get("outcome")
        if outcome not in ("goal", "save"):
            continue  # a mellé menő lövésből nem mérünk hatékonyságot
        team = e.team.value
        down = _down_at(e.t)
        if down is None or down == team:
            # Egyenlő létszám (vagy hátrányban lőtt — az az "eq"-t se rontsa).
            if down is None:
                out[team]["eq_shots"] += 1
                if outcome == "goal":
                    out[team]["eq_goals"] += 1
        else:
            out[team]["pp_shots"] += 1
            if outcome == "goal":
                out[team]["pp_goals"] += 1
        if outcome == "goal" and down is not None and down != team:
            # A hátrányban lévő csapat kapta a gólt.
            out[down]["sh_conceded"] += 1

    for rec in out.values():
        if rec["pp_shots"]:
            rec["pp_eff_pct"] = round(100.0 * rec["pp_goals"] / rec["pp_shots"], 1)
        if rec["eq_shots"]:
            rec["eq_eff_pct"] = round(100.0 * rec["eq_goals"] / rec["eq_shots"], 1)
        rec["pp_seconds"] = round(rec["pp_seconds"], 1)
        rec["sh_seconds"] = round(rec["sh_seconds"], 1)
    return out


# Hetes-kiharcoló: ennyi másodperccel a hetes-jel előtt nézzük, ki volt
# a kapuhoz legközelebbi támadó (a szabálytalanság áldozata jellemzően ő).
SEVEN_EARNER_LOOKBACK_S = 2.0


def seven_meter_earners(match: Match,
                        config: Optional[TacticsConfig] = None) -> dict:
    """Ki harcolja ki a hétméterseket: a hetes-jel előtt a támadott
    kapuhoz legközelebb járó (nem kapus) támadó kapja a jóváírást.

    Heurisztika, de magyarázható: a befejezésbe érkező embert rántják
    le. A felderítésben ebből lesz a "vele szemben kéz nélkül" kulcs.

    Visszatérés: {"home"/"away": [{"player_id", "earned"}]}.
    """
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    frames_by_t = {f.t: f for f in match.frames}
    tally: dict = {"home": {}, "away": {}}
    for sm in detect_seven_meters(match, config):
        t_prev = sm["t"] - round(SEVEN_EARNER_LOOKBACK_S * fps)
        fr = None
        for dt in range(0, round(fps)):
            fr = frames_by_t.get(t_prev - dt) or frames_by_t.get(t_prev + dt)
            if fr is not None and fr.players:
                break
        if fr is None or not fr.players:
            continue
        best = None
        for p in fr.players:
            if p.team.value != sm["team"] or p.role == "kapus":
                continue
            d = abs(p.x - sm["goal_x"])
            if best is None or d < best[1]:
                best = (p.track_id, d)
        if best is not None:
            side = tally[sm["team"]]
            side[best[0]] = side.get(best[0], 0) + 1
    return {side: [{"player_id": pid, "earned": n}
                   for pid, n in sorted(rec.items(),
                                        key=lambda kv: -kv[1])]
            for side, rec in tally.items()}


# Kiállítás-kiharcoló: ennyivel a hátrány észlelt kezdete előtt keressük
# a szabálytalanságot kiváltó támadót (a PP-ablak felbontása miatt tág).
SUSP_EARNER_LOOKBACK_S = PP_WINDOW_S


def suspension_earners(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Ki harcolja ki a kiállításokat: a hátrány kezdete előtti
    másodpercekben a támadott kapuhoz legközelebb nyomuló (nem kapus)
    ellenfél-támadó kapja a jóváírást.

    Ugyanaz a magyarázható heurisztika, mint a hetes-kiharcolónál: a
    2 percet tipikusan a kapura törő ember elleni szabálytalanság hozza.
    A felderítésben ebből lesz a "ő hozza a kiállításokat" kulcs.

    Visszatérés: {"home"/"away": [{"player_id", "earned"}]} — a
    KIHARCOLÓ (előnyt szerző) oldal szerint csoportosítva.
    """
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    frames_by_t = {f.t: f for f in match.frames}
    tally: dict = {"home": {}, "away": {}}
    for w in detect_powerplay(match):
        earner_team = "away" if w["team_down"] == "home" else "home"
        goal_x = config.attacks_toward_x(
            Team.HOME if earner_team == "home" else Team.AWAY)
        # A hátrány-ablak kezdete előtti másodpercekben, kockáról
        # kockára: ki járt legmélyebben a kapunál.
        t0 = w["start_frame"] - round(SUSP_EARNER_LOOKBACK_S * fps)
        best = None
        for dt in range(0, round(SUSP_EARNER_LOOKBACK_S * fps) + 1):
            fr = frames_by_t.get(t0 + dt)
            if fr is None:
                continue
            for p in fr.players:
                if p.team.value != earner_team or p.role == "kapus":
                    continue
                d = abs(p.x - goal_x)
                if best is None or d < best[1]:
                    best = (p.track_id, d)
        if best is not None:
            side = tally[earner_team]
            side[best[0]] = side.get(best[0], 0) + 1
    return {side: [{"player_id": pid, "earned": n}
                   for pid, n in sorted(rec.items(),
                                        key=lambda kv: -kv[1])]
            for side, rec in tally.items()}


# A kiülő azonosításához: ennyivel a hátrány kezdete előtt nézzük, ki
# volt még a pályán (aki a teljes hátrány alatt el is tűnik, az ült ki).
SUSP_WHO_LOOKBACK_S = 20.0


def suspended_players(match: Match,
                      config: Optional[TacticsConfig] = None) -> dict:
    """Ki ült ki: a kiállítás lenyomata a TRACKEKBEN is ott van — a
    büntetett játékos a hátrány teljes ideje alatt hiányzik a pályáról.

    A hátrány kezdete előtti SUSP_WHO_LOOKBACK_S-ben mért, nem kapus
    trackek közül az a kiülő, amelyik a hátrány alatt egyszer sem
    látszik. Ha több ilyen van (cserehullám zaja), inkább nem mondunk
    semmit — nincs hamis vádaskodás.

    Visszatérés: {"home"/"away": [{"player_id", "suspensions"}]} — a
    BÜNTETETT oldal szerint, kiállítás-szám szerint csökkenő sorban.
    """
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    tally: dict = {"home": {}, "away": {}}
    for w in detect_powerplay(match):
        side = w["team_down"]
        t0, t1 = w["start_frame"], w["end_frame"]
        look = t0 - round(SUSP_WHO_LOOKBACK_S * fps)
        before: set = set()
        during: set = set()
        for f in match.frames:
            if look <= f.t < t0:
                for p in f.players:
                    if (p.team.value == side and p.role != "kapus"
                            and p.source == PositionSource.MEASURED):
                        before.add(p.track_id)
            elif t0 <= f.t <= t1:
                for p in f.players:
                    if p.team.value == side:
                        during.add(p.track_id)
        gone = [tid for tid in before if tid not in during]
        if len(gone) == 1:
            tally[side][gone[0]] = tally[side].get(gone[0], 0) + 1
    return {side: [{"player_id": pid, "suspensions": n}
                   for pid, n in sorted(rec.items(),
                                        key=lambda kv: -kv[1])]
            for side, rec in tally.items()}
