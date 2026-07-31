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


# Fegyelem-esés: ennyi kiállítástól ítélünk, és ekkora félidők közti
# többlet számít mintázatnak (nem egyszeri balszerencsének).
DISC_FADE_MIN_TOTAL = 3
DISC_FADE_DIFF = 2


def discipline_fade(match: Match, config=None) -> dict:
    """Fegyelem-esés: a kiállítások félidőnkénti eloszlása — a fáradás-kép
    fej-oldali tagja.

    A felismert kiállításokat (emberhátrány-ablakokat) a felismert félidő
    mentén számoljuk szét. Akinek a kiállításai a 2. félidőben sűrűsödnek,
    az fáradtan, késve érkezve szabálytalankodik — a hajrában emberelőny
    várható ellene; akinek az elején jönnek, az kemény kezdés után
    szelídül.

    Visszatérés csapatonként:
      {"fh_susp", "sh_susp", "verdict"} — verdict None (nincs félidő-jel
    vagy kevés kiállítás), "hajrában szabálytalankodnak" vagy
    "az elején kemények".
    """
    from .halftime import detect_halftime

    empty = {"fh_susp": 0, "sh_susp": 0, "verdict": None}
    out = {"home": dict(empty), "away": dict(empty)}
    ht = detect_halftime(match)
    if ht is None:
        return out
    for w in detect_powerplay(match):
        rec = out[w["team_down"]]
        rec["fh_susp" if w["start_frame"] <= ht else "sh_susp"] += 1
    for s in ("home", "away"):
        rec = out[s]
        if rec["fh_susp"] + rec["sh_susp"] < DISC_FADE_MIN_TOTAL:
            continue
        if rec["sh_susp"] - rec["fh_susp"] >= DISC_FADE_DIFF:
            rec["verdict"] = "hajrában szabálytalankodnak"
        elif rec["fh_susp"] - rec["sh_susp"] >= DISC_FADE_DIFF:
            rec["verdict"] = "az elején kemények"
    return out


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
# Az irány magyar határozói alakja — minden felület ebből ír ("balra").
SEVEN_DIR_HU = {"bal": "balra", "jobb": "jobbra", "közép": "középre"}
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


def seven_meter_defense(match: Match,
                        config: Optional[TacticsConfig] = None) -> dict:
    """Hetes-védés: a kapus mérlege a RÁ dobott hetesekből.

    A hetes-mérleg (seven_meter_summary) kapus-oldali olvasata: az
    ellenfél hetesei közül mennyi ment be, mennyit fogott a kapus,
    mennyi ment mellé. A hetest fogó kapus ellen a hetes nem "kész gól"
    — a dobóknak készülniük kell; a hetest sosem fogó kapus ellen a
    hetes-kiharcolás biztos üzlet.

    Visszatérés csapatonként (a VÉDEKEZŐ csapat kapusáé):
      {"faced", "saved", "conceded", "missed"} — faced a kapura tartó
    hetesek száma (gól + védés; a mellé menő nem a kapus érdeme).
    """
    summ = seven_meter_summary(match, config)
    out = {}
    for side, other in (("home", "away"), ("away", "home")):
        rec = summ[other]
        out[side] = {
            "faced": rec["goals"] + rec["saved"],
            "saved": rec["saved"],
            "conceded": rec["goals"],
            "missed": rec["missed"],
        }
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


# Hátrány-támadás: ennyi emberhátrányban töltött másodperctől ítélünk,
# és ennyi gól/perc eltérés választja el a "veszélyes" hátrányos
# támadást a "megbénuló"-tól.
SHATK_MIN_S = 90.0
SHATK_DROP_PER_MIN = 0.15


def shorthanded_attack(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Hátrány-támadás: mit támadnak a kiállítás alatt.

    Az emberelőny-hatékonyság (powerplay_efficiency) a kiállítás
    NYERTES oldalát nézi, a hátrányban leadott lövéseket kifejezetten
    kihagyja — ez a hiányzó fele: a kiállított csapat MAGA mennyit
    támad egy emberrel kevesebben. Aki hátrányban is gólt szerez
    (labdát tart, lerohan), az kihúzza a két percet: ellene az
    emberelőnyt türelmesen kell végigjátszani, kockázatos lövés
    nélkül. Aki megbénul, annál a kiállítás azonnali gólkülönbség —
    saját olvasatban a hátrányos labdatartás az edzés-téma.

    Visszatérés csapatonként: {"sh_seconds", "sh_shots", "sh_goals",
    "sh_per_min", "eq_seconds", "eq_goals", "eq_per_min",
    "gap_per_min", "verdict"} — az ütemek és a verdict None, ha kevés
    (SHATK_MIN_S alatti) a hátrányban töltött idő; a verdict
    "veszélyes" / "megbénul" / None.
    """
    from .event_detection import detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    if not match.frames:
        return {s: {"sh_seconds": 0.0, "sh_shots": 0, "sh_goals": 0,
                    "sh_per_min": None, "eq_seconds": 0.0,
                    "eq_goals": 0, "eq_per_min": None,
                    "gap_per_min": None, "verdict": None}
                for s in ("home", "away")}
    windows = detect_powerplay(match)
    total_s = (match.frames[-1].t - match.frames[0].t) / fps
    # Egyenlő létszám: a teljes idő mínusz MINDEN kiállítás-szakasz
    # (akármelyik csapaté) — ez a közös viszonyítási alap.
    pp_total_s = sum(w["duration_s"] for w in windows)
    eq_seconds = max(0.0, total_s - pp_total_s)

    def _down_at(t: int) -> Optional[str]:
        for w in windows:
            if w["start_frame"] <= t <= w["end_frame"]:
                return w["team_down"]
        return None

    counts = {s: {"sh_seconds": 0.0, "sh_shots": 0, "sh_goals": 0,
                  "eq_goals": 0}
              for s in ("home", "away")}
    for w in windows:
        counts[w["team_down"]]["sh_seconds"] += w["duration_s"]
    for e in detect_shots(match, config):
        outcome = (e.detail or {}).get("outcome")
        if outcome not in ("goal", "save", "miss"):
            continue
        side = e.team.value
        down = _down_at(e.t)
        if down == side:
            counts[side]["sh_shots"] += 1
            if outcome == "goal":
                counts[side]["sh_goals"] += 1
        elif down is None and outcome == "goal":
            counts[side]["eq_goals"] += 1
    out = {}
    for side in ("home", "away"):
        rec = counts[side]
        r = {"sh_seconds": round(rec["sh_seconds"], 1),
             "sh_shots": rec["sh_shots"], "sh_goals": rec["sh_goals"],
             "sh_per_min": None, "eq_seconds": round(eq_seconds, 1),
             "eq_goals": rec["eq_goals"], "eq_per_min": None,
             "gap_per_min": None, "verdict": None}
        if rec["sh_seconds"] >= SHATK_MIN_S and eq_seconds > 0:
            sh_pm = 60.0 * rec["sh_goals"] / rec["sh_seconds"]
            eq_pm = 60.0 * rec["eq_goals"] / eq_seconds
            r["sh_per_min"] = round(sh_pm, 2)
            r["eq_per_min"] = round(eq_pm, 2)
            r["gap_per_min"] = round(sh_pm - eq_pm, 2)
            if eq_pm - sh_pm >= SHATK_DROP_PER_MIN:
                r["verdict"] = "megbénul"
            else:
                r["verdict"] = "veszélyes"
        out[side] = r
    return out


# Emberelőny-védekezés: ennyi emberelőnyben töltött másodperctől
# ítélünk, és ennyi kapott gól/perc eltérés a "szivárog" /
# "fegyelmezett" küszöb.
PPDEF_MIN_S = 90.0
PPDEF_RISE_PER_MIN = 0.2


def powerplay_defense(match: Match,
                      config: Optional[TacticsConfig] = None) -> dict:
    """Emberelőny-védekezés: emberelőnyben is kapnak-e gólt.

    Az emberelőny-hatékonyság (powerplay_efficiency) azt méri, mit
    TÁMADNAK a kiállítás alatt — ez azt, mit VÉDEKEZNEK közben:
    egy emberrel többen is kaphatnak lerohanás-gólt, ha a
    befejezéseik után nem rendeződnek vissza. A perces kapott
    gól-ütemet hasonlítja az egyenlő létszámúhoz. Aki előnyben is
    szivárog, annál a kiállítás nem büntetés: hátrányban is vállalni
    kell a lerohanást ellene — aki fegyelmezett, azzal szemben
    hátrányban a labdatartás a reális cél.

    Visszatérés csapatonként (az ELŐNYBEN lévő oldal): {"pp_seconds",
    "pp_conceded", "pp_per_min", "eq_seconds", "eq_conceded",
    "eq_per_min", "gap_per_min", "verdict"} — az ütemek és a verdict
    None, ha kevés (PPDEF_MIN_S alatti) az emberelőnyben töltött idő;
    a verdict "szivárog" / "fegyelmezett" / None.
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    if not match.frames:
        return {s: {"pp_seconds": 0.0, "pp_conceded": 0,
                    "pp_per_min": None, "eq_seconds": 0.0,
                    "eq_conceded": 0, "eq_per_min": None,
                    "gap_per_min": None, "verdict": None}
                for s in ("home", "away")}
    windows = detect_powerplay(match)
    total_s = (match.frames[-1].t - match.frames[0].t) / fps
    eq_seconds = max(0.0, total_s - sum(w["duration_s"] for w in windows))

    def _down_at(t: int) -> Optional[str]:
        for w in windows:
            if w["start_frame"] <= t <= w["end_frame"]:
                return w["team_down"]
        return None

    counts = {s: {"pp_seconds": 0.0, "pp_conceded": 0, "eq_conceded": 0}
              for s in ("home", "away")}
    for w in windows:
        up = "away" if w["team_down"] == "home" else "home"
        counts[up]["pp_seconds"] += w["duration_s"]
    for e in detect_shots(match, config):
        if e.type != EventType.GOAL:
            continue
        scorer = e.team.value
        conceder = "away" if scorer == "home" else "home"
        down = _down_at(e.t)
        if down == scorer:
            # A hátrányban lévő csapat szerzett gólt: ezt az
            # EMBERELŐNYBEN lévő védekezés kapta.
            counts[conceder]["pp_conceded"] += 1
        elif down is None:
            counts[conceder]["eq_conceded"] += 1
    out = {}
    for side in ("home", "away"):
        rec = counts[side]
        r = {"pp_seconds": round(rec["pp_seconds"], 1),
             "pp_conceded": rec["pp_conceded"], "pp_per_min": None,
             "eq_seconds": round(eq_seconds, 1),
             "eq_conceded": rec["eq_conceded"], "eq_per_min": None,
             "gap_per_min": None, "verdict": None}
        if rec["pp_seconds"] >= PPDEF_MIN_S and eq_seconds > 0:
            pp_pm = 60.0 * rec["pp_conceded"] / rec["pp_seconds"]
            eq_pm = 60.0 * rec["eq_conceded"] / eq_seconds
            r["pp_per_min"] = round(pp_pm, 2)
            r["eq_per_min"] = round(eq_pm, 2)
            r["gap_per_min"] = round(pp_pm - eq_pm, 2)
            if pp_pm - eq_pm >= PPDEF_RISE_PER_MIN:
                r["verdict"] = "szivárog"
            elif eq_pm - pp_pm >= PPDEF_RISE_PER_MIN:
                r["verdict"] = "fegyelmezett"
        out[side] = r
    return out


# Hetes-okozó: ennyi hetes kell egy védő megbélyegzéséhez (a
# heurisztika zaja miatt egy eset még nem minta).
SEVEN_CONCEDER_MIN = 2


def seven_meter_conceders(match: Match,
                          config: Optional[TacticsConfig] = None) -> dict:
    """Hetes-okozó védők: KINÉL szakad meg a védekezés hetessel.

    A hetes-kiharcolók (seven_meter_earners) a támadó oldalról nézik,
    kit rántanak le — ez a védő oldali párja: a hetes-jel előtt a
    kiharcolóhoz legközelebb álló (nem kapus) VÉDŐ kapja a
    jóváírást. Heurisztika, de magyarázható: a befejezésbe érkező
    embert az a védő állítja meg szabálytalanul, aki mellette van.

    Edzőileg: aki két-három hetest is okoz, annak a lábmunkájával van
    baj (kézzel áll meg a betörést) — vele szemben a betörés
    kifizetődő, a saját edzésnek pedig kész témája van.

    Visszatérés a VÉDEKEZŐ csapat oldalán: {"home"/"away":
    {"players": [{"player_id", "jersey", "conceded"}], "top":
    {"player_id", "jersey", "conceded"} | None}} — a "top" akkor van kitöltve, ha a vezető védő
    legalább SEVEN_CONCEDER_MIN hetest okozott.
    """
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    frames_by_t = {f.t: f for f in match.frames}
    tally: dict = {"home": {}, "away": {}}
    jersey: dict = {}
    for sm in detect_seven_meters(match, config):
        t_prev = sm["t"] - round(SEVEN_EARNER_LOOKBACK_S * fps)
        fr = None
        for dt in range(0, round(fps)):
            fr = frames_by_t.get(t_prev - dt) or frames_by_t.get(t_prev + dt)
            if fr is not None and fr.players:
                break
        if fr is None or not fr.players:
            continue
        for p in fr.players:
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)
        # A kiharcoló: a támadott kapuhoz legközelebbi támadó.
        earner = None
        for p in fr.players:
            if p.team.value != sm["team"] or p.role == "kapus":
                continue
            d = abs(p.x - sm["goal_x"])
            if earner is None or d < earner[1]:
                earner = (p, d)
        if earner is None:
            continue
        # Az okozó: a kiharcolóhoz legközelebbi mezőnyvédő.
        defending = "away" if sm["team"] == "home" else "home"
        best = None
        for p in fr.players:
            if p.team.value != defending or p.role == "kapus":
                continue
            d = ((p.x - earner[0].x) ** 2 + (p.y - earner[0].y) ** 2) ** 0.5
            if best is None or d < best[1]:
                best = (p.track_id, d)
        if best is not None:
            tally[defending][best[0]] = tally[defending].get(best[0], 0) + 1

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "conceded": n}
                for pid, n in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1])]
        top = (rows[0] if rows and rows[0]["conceded"] >= SEVEN_CONCEDER_MIN
               else None)
        out[side] = {"players": rows, "top": top}
    return out


# Emberelőny-tempó: ennyi mért támadás kell emberelőnyben és egyenlő
# létszámnál, és ekkora (másodperces) eltérés számít érdemi jelnek.
PP_PACE_MIN_PP = 3
PP_PACE_MIN_EQ = 5
PP_PACE_GAP_S = 5.0


def powerplay_pace(match: Match,
                   config: Optional[TacticsConfig] = None) -> dict:
    """Emberelőny-tempó: ELNYÚJTJÁK vagy KAPKODJÁK az emberelőnyt.

    Az emberelőny-hatékonyság (powerplay_efficiency) azt mondja meg,
    mennyi gólt hoznak a kiállításokból — ez azt, HOGYAN játsszák: a
    támadás-szakaszok hosszát vetjük össze emberelőnyben és egyenlő
    létszámnál.

    Edzőileg: aki emberelőnyben érdemben elnyújtja a támadást, az a
    biztos helyzetre vár — ellene türelmes, zárt fal kell, mert a
    kapkodó kilépés pont neki dolgozik; aki emberelőnyben is gyorsan
    lő, annál a két perc alatt nagy a hibaszázalék: ott az agresszív,
    kilépő védekezés kifizet.

    Visszatérés csapatonként: {"pp_attacks", "pp_avg_s", "eq_attacks",
    "eq_avg_s", "gap_s", "verdict"} — az átlagok és a gap None, ha
    kevés a minta (PP_PACE_MIN_PP / PP_PACE_MIN_EQ); a verdict
    "elnyújtják emberelőnyben" / "kapkodnak emberelőnyben" / None.
    """
    from .setplays import segment_attacks

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    windows = detect_powerplay(match)

    def _down_at(t: int) -> Optional[str]:
        for w in windows:
            if w["start_frame"] <= t <= w["end_frame"]:
                return w["team_down"]
        return None

    acc = {side: {"pp": [0, 0.0], "eq": [0, 0.0]}
           for side in ("home", "away")}
    for seq in segment_attacks(match, config):
        side = seq.team.value
        down = _down_at(seq.start_t)
        if down == side:
            continue  # emberhátrányban támadnak: külön kép (shorthanded)
        key = "pp" if down is not None else "eq"
        dur = (seq.end_t - seq.start_t + 1) / fps
        acc[side][key][0] += 1
        acc[side][key][1] += dur

    out: dict = {}
    for side in ("home", "away"):
        pp_n, pp_s = acc[side]["pp"]
        eq_n, eq_s = acc[side]["eq"]
        rec = {"pp_attacks": pp_n, "eq_attacks": eq_n,
               "pp_avg_s": None, "eq_avg_s": None, "gap_s": None,
               "verdict": None}
        if pp_n >= PP_PACE_MIN_PP and eq_n >= PP_PACE_MIN_EQ:
            rec["pp_avg_s"] = round(pp_s / pp_n, 1)
            rec["eq_avg_s"] = round(eq_s / eq_n, 1)
            rec["gap_s"] = round(rec["pp_avg_s"] - rec["eq_avg_s"], 1)
            if rec["gap_s"] >= PP_PACE_GAP_S:
                rec["verdict"] = "elnyújtják emberelőnyben"
            elif rec["gap_s"] <= -PP_PACE_GAP_S:
                rec["verdict"] = "kapkodnak emberelőnyben"
        out[side] = rec
    return out


# Emberhátrány-forma: ennyi mért kocka kell az ítélethez, és e feletti
# részarány jelenti, hogy egy formát játszanak öt emberrel.
SH_SHAPE_MIN_FRAMES = 100
SH_SHAPE_MAIN_PCT = 60.0


def shorthanded_shape(match: Match,
                      config: Optional[TacticsConfig] = None) -> dict:
    """Emberhátrány-forma: MIT JÁTSZANAK öt emberrel.

    Az emberhátrány-támadás (shorthanded_attack) azt mondja meg, mire
    mennek támadásban a két perc alatt, az emberelőny-védekezés
    (powerplay_defense) azt, mennyit kapnak — ez azt, MILYEN FALAT
    húznak: a kiállítás-ablakokban a hátrányban lévő csapat formáját
    olvassuk ki kockánként, hátsó-előretolt bontásban (5-0, 4-1,
    3-2).

    Edzőileg: az 5-0 mögött az átlövés szabad — kívülről kell lőni és
    a szélsőket etetni; a 4-1 (előretolt védő) ellen az oldalváltás és
    a beállós játék a válasz, mert az előretolt ember mögött nyílik a
    tér.

    Visszatérés csapatonként (a HÁTRÁNYBAN lévő oldal): {"frames",
    "labels": {forma: kocka}, "main", "main_pct"} — a main/main_pct
    None SH_SHAPE_MIN_FRAMES alatt vagy SH_SHAPE_MAIN_PCT alatti
    többségnél.
    """
    from .tactics import TacticsConfig, detect_formation

    config = config or TacticsConfig()
    windows = detect_powerplay(match)
    tally: dict = {"home": {}, "away": {}}
    for f in match.frames:
        for w in windows:
            if not (w["start_frame"] <= f.t <= w["end_frame"]):
                continue
            down = w["team_down"]
            team = Team.HOME if down == "home" else Team.AWAY
            form = detect_formation(f, team, config)
            # Öt (vagy kevesebb) mezőnyvédő a hátrány jele; ennél
            # többnél a címke nem az emberhátrány-falat írja le.
            if form.defenders < 3 or form.defenders > 5:
                continue
            # Emberhátrányban a szokásos név hátsó-előretolt bontású
            # (5-0, 4-1, 3-2); a hatfős címkéző itt leíró nevet adna.
            label = f"{form.back}-{form.mid + form.high}"
            tally[down][label] = tally[down].get(label, 0) + 1
            break

    out: dict = {}
    for side in ("home", "away"):
        labels = dict(sorted(tally[side].items(), key=lambda kv: -kv[1]))
        n = sum(labels.values())
        rec = {"frames": n, "labels": labels, "main": None,
               "main_pct": None}
        if n >= SH_SHAPE_MIN_FRAMES and labels:
            main, cnt = next(iter(labels.items()))
            pct = 100.0 * cnt / n
            if pct >= SH_SHAPE_MAIN_PCT:
                rec["main"] = main
                rec["main_pct"] = round(pct, 1)
        out[side] = rec
    return out


# Kapus-hetesvédés irány szerint: irányonként ennyi kapura tartó hetes
# kell az ítélethez, és ekkora (százalékpontos) különbség számít
# érdemi oldal-eltérésnek.
GK7_DIR_MIN = 3
GK7_DIR_GAP_PP = 25.0


def gk_seven_directions(match: Match,
                        config: Optional[TacticsConfig] = None) -> dict:
    """Kapus-hetesvédés irány szerint: MELYIK SAROKBA menő heteseket
    fogja a kapusuk.

    A hetes-védés (seven_meter_defense) azt mondja meg, MENNYIT fog a
    kapusuk — ez azt, MERRE: a hetes-kimenetelek (seven_meter_outcomes)
    irány-mezőjét (bal / közép / jobb, a DOBÓ szemszögéből) használjuk,
    és irányonként számolunk védési arányt.

    Edzőileg: a hetes-lövőtöknek kész terve legyen — abba a sarokba
    kell lőni, ahol a kapusuk a leggyengébb, és nem szabad "érzésre"
    dönteni a vonalnál.

    Visszatérés csapatonként (a VÉDŐ oldal = akinek a kapusa a
    kapuban van): {"bal"/"közép"/"jobb": {"faced", "saved",
    "save_pct"}, "faced", "weak_dir"} — a weak_dir a legrosszabb
    védési arányú irány, ha van legalább GK7_DIR_MIN kapura tartó
    hetes onnan, és a védés-aránya legalább GK7_DIR_GAP_PP
    százalékponttal az összesített alatt van.
    """
    config = config or TacticsConfig()
    out: dict = {}
    tally = {side: {d: {"faced": 0, "saved": 0}
                    for d in ("bal", "közép", "jobb")}
             for side in ("home", "away")}
    for sm in seven_meter_outcomes(match, config):
        if sm["outcome"] not in ("gól", "védés") or sm["irany"] is None:
            continue  # kihagyott/ismeretlen: a kapushoz nem mérhető
        defending = "away" if sm["team"] == "home" else "home"
        rec = tally[defending][sm["irany"]]
        rec["faced"] += 1
        if sm["outcome"] == "védés":
            rec["saved"] += 1

    for side in ("home", "away"):
        dirs = tally[side]
        faced = sum(r["faced"] for r in dirs.values())
        saved = sum(r["saved"] for r in dirs.values())
        for r in dirs.values():
            r["save_pct"] = (round(100.0 * r["saved"] / r["faced"], 1)
                             if r["faced"] else None)
        weak = None
        cand = [(d, r) for d, r in dirs.items()
                if r["faced"] >= GK7_DIR_MIN]
        if cand and faced:
            avg = 100.0 * saved / faced
            d, r = min(cand, key=lambda kv: kv[1]["save_pct"])
            if avg - r["save_pct"] >= GK7_DIR_GAP_PP:
                weak = {"irany": d, "save_pct": r["save_pct"],
                        "faced": r["faced"]}
        out[side] = {**dirs, "faced": faced, "weak_dir": weak}
    return out


# Emberelőny-lövők: ennyi emberelőnyben leadott lövéstől emeljük ki az
# embert (ennyi alatt a kép még véletlen).
PPS_MIN_SHOTS = 3


def powerplay_shooters(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Emberelőny-lövők: KI FEJEZ BE a két perc alatt.

    Az emberelőny-hatékonyság (powerplay_efficiency) azt mondja meg,
    mennyi gólt hoznak a kiállításokból, az emberelőny-tempó
    (powerplay_pace) azt, hogyan játsszák — ez azt, KIRE megy a
    befejezés: a kiállítás-ablakokban leadott lövéseket a lövőhöz
    írjuk.

    Edzőileg: emberhátrányban a fal nem érhet mindenhová, ezért a
    befejezőjükre kell rendezni — az ő oldalán kell a kettőzés vagy a
    kilépés, a többieket pedig rá lehet engedni.

    Visszatérés csapatonként: {"shots", "players": [{"player_id",
    "jersey", "shots", "goals"}], "top"} — a lista lövésszám szerint
    csökkenő; a "top" az első játékos, ha legalább PPS_MIN_SHOTS
    emberelőnyben leadott lövése van.
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    windows = detect_powerplay(match)
    if not windows:
        return {side: {"shots": 0, "players": [], "top": None}
                for side in ("home", "away")}

    def _down_at(t: int) -> Optional[str]:
        for w in windows:
            if w["start_frame"] <= t <= w["end_frame"]:
                return w["team_down"]
        return None

    jersey: dict = {}
    for fr in match.frames:
        for p in fr.players:
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)

    tally: dict = {"home": {}, "away": {}}
    for e in detect_shots(match, config):
        if e.type not in (EventType.SHOT, EventType.GOAL) \
                or e.player_id is None:
            continue
        side = e.team.value
        down = _down_at(e.t)
        if down is None or down == side:
            continue  # egyenlő létszám vagy emberhátrány: nem ide tartozik
        rec = tally[side].setdefault(e.player_id,
                                     {"shots": 0, "goals": 0})
        rec["shots"] += 1
        if e.type == EventType.GOAL:
            rec["goals"] += 1

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "shots": r["shots"], "goals": r["goals"]}
                for pid, r in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1]["shots"])]
        top = (rows[0] if rows and rows[0]["shots"] >= PPS_MIN_SHOTS
               else None)
        out[side] = {"shots": sum(r["shots"] for r in rows),
                     "players": rows, "top": top}
    return out


# Emberhátrány-lövők: ennyi emberhátrányban leadott lövéstől emeljük ki
# az embert (a két perc alatt kevés a lövés, de egy eset nem minta).
SHS_MIN_SHOTS = 2


def shorthanded_shooters(match: Match,
                         config: Optional[TacticsConfig] = None) -> dict:
    """Emberhátrány-lövők: KI VÁLLALJA a befejezést öt emberrel.

    Az emberhátrány-támadás (shorthanded_attack) azt mondja meg,
    mennyit érnek a két perc alatt, az emberhátrány-forma
    (shorthanded_shape) azt, milyen falat húznak — ez azt, KI LŐ
    ilyenkor: a kiállítás-ablakokban a HÁTRÁNYBAN lévő csapat
    lövéseit a lövőhöz írjuk.

    Edzőileg: emberelőnyben az ő befejezőjük a kontra-fenyegetés — rá
    kell hagyni a legkevesebb teret, és a mi emberelőnyös
    támadásunkban az ő oldalán kell a labdabiztonság, mert onnan indul
    az ellentámadásuk.

    Visszatérés csapatonként: {"shots", "players": [{"player_id",
    "jersey", "shots", "goals"}], "top"} — a "top" az első játékos, ha
    legalább SHS_MIN_SHOTS emberhátrányban leadott lövése van.
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    windows = detect_powerplay(match)
    if not windows:
        return {side: {"shots": 0, "players": [], "top": None}
                for side in ("home", "away")}

    def _down_at(t: int) -> Optional[str]:
        for w in windows:
            if w["start_frame"] <= t <= w["end_frame"]:
                return w["team_down"]
        return None

    jersey: dict = {}
    for fr in match.frames:
        for p in fr.players:
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)

    tally: dict = {"home": {}, "away": {}}
    for e in detect_shots(match, config):
        if e.type not in (EventType.SHOT, EventType.GOAL) \
                or e.player_id is None:
            continue
        side = e.team.value
        if _down_at(e.t) != side:
            continue  # csak a hátrányban lévő csapat lövései
        rec = tally[side].setdefault(e.player_id,
                                     {"shots": 0, "goals": 0})
        rec["shots"] += 1
        if e.type == EventType.GOAL:
            rec["goals"] += 1

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "shots": r["shots"], "goals": r["goals"]}
                for pid, r in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1]["shots"])]
        top = (rows[0] if rows and rows[0]["shots"] >= SHS_MIN_SHOTS
               else None)
        out[side] = {"shots": sum(r["shots"] for r in rows),
                     "players": rows, "top": top}
    return out


# Hetes-kiharcolás poszt szerint: ennyi poszthoz kötött hetestől
# ítélünk, és e feletti részarány jelenti, hogy egy posztról jönnek.
SER_MIN_SEVENS = 3
SER_SHARE = 50.0


def seven_earner_roles(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Hetes-kiharcolás poszt szerint: MELYIK POSZTRÓL rántják le őket.

    A hetes-kiharcolók (seven_meter_earners) azt mondják meg, KIT
    rántanak le — ez azt, MILYEN POSZTON: a kiharcolókat a
    poszt-becsléshez (estimate_positions) kötjük.

    Edzőileg: ha a hetesek zöme a szélsőikről jön, a szélső-védekezésnél
    tilos a kéz — csak lábbal, testtel szabad terelni; ha a beállótól,
    az elé állást kell gyakorolni, mert a beálló-fogás hetest ér.

    Visszatérés csapatonként: {"sevens", "roles": {poszt: darab},
    "top": {"poszt", "count", "share_pct"} | None} — a "top" akkor van
    kitöltve, ha legalább SER_MIN_SEVENS poszthoz kötött hetes van, a
    vezető poszt részaránya eléri a SER_SHARE-t, és nincs vele
    holtversenyben másik poszt.
    """
    from .roles import estimate_positions

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    out: dict = {side: {"sevens": 0, "roles": {}, "top": None}
                 for side in ("home", "away")}
    earners = seven_meter_earners(match, config)
    for side in ("home", "away"):
        rec = out[side]
        for row in earners.get(side, []):
            info = roles.get(side, {}).get(row["player_id"])
            if info is None:
                continue
            rec["sevens"] += row["earned"]
            poszt = info["poszt"]
            rec["roles"][poszt] = rec["roles"].get(poszt, 0) + row["earned"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        items = list(rec["roles"].items())
        if rec["sevens"] >= SER_MIN_SEVENS and items:
            poszt, n = items[0]
            share = 100.0 * n / rec["sevens"]
            tie = len(items) > 1 and items[1][1] == n
            if share >= SER_SHARE and not tie:
                rec["top"] = {"poszt": poszt, "count": n,
                              "share_pct": round(share, 1)}
    return out


# Hetes-fáradás: legalább ennyi adott hetes kell az ítélethez, és
# ekkora félidők közti többlet jelenti a fáradással (vagy az elején,
# hidegen) adott heteseket.
S7F_MIN_CONCEDED = 4
S7F_GAP = 2


def sevens_fade(match: Match,
                config: Optional[TacticsConfig] = None) -> dict:
    """Hetes-fáradás: MIKOR ADJÁK a heteseket.

    A hetes-adók (seven_meter_conceders) azt mondják meg, KI ellen
    ítélik, a szabálytalanság-fáradás (discipline_fade) a kiállítások
    idejét — ez a hetesekét: a csapat által ADOTT (az ellenfélnek
    megítélt) heteseket félidőnként számoljuk.

    Edzőileg: aki a második félidőben adja a heteseket, az fáradva
    már kézzel véd — ott a szünet után be kell vinni a labdát a
    testre, mert jön az ajándék; aki az elején ad, az hidegen
    kapkod — az első percekben kell a beállóst és a betörést erőltetni.

    Visszatérés csapatonként (az ADÓ oldal): {"fh", "sh", "verdict"}
    — a verdict None, ha nincs felismert szünet vagy kevés a hetes; a
    verdict "a második félidőben adják a heteseket" / "az elején
    adják a heteseket" / None.
    """
    from .halftime import detect_halftime

    out = {side: {"fh": 0, "sh": 0, "verdict": None}
           for side in ("home", "away")}
    ht = detect_halftime(match)
    if ht is None:
        return out

    for ev in detect_seven_meters(match, config):
        conceder = "away" if ev["team"] == "home" else "home"
        rec = out[conceder]
        if ev["t"] <= ht:
            rec["fh"] += 1
        else:
            rec["sh"] += 1

    for side in ("home", "away"):
        rec = out[side]
        total = rec["fh"] + rec["sh"]
        if total >= S7F_MIN_CONCEDED:
            if rec["sh"] - rec["fh"] >= S7F_GAP:
                rec["verdict"] = "a második félidőben adják a heteseket"
            elif rec["fh"] - rec["sh"] >= S7F_GAP:
                rec["verdict"] = "az elején adják a heteseket"
    return out
