"""
[2. fázis kiegészítés] Eseményfelismerés — passz, lövés, gól, labdaeladás.

A kész Tracking-ből (labda + pozíciók + birtoklás) felismeri a fő eseményeket:
- PASSZ:        a labdabirtokos UGYANAZON a csapaton belül változik.
- LABDAELADÁS:  a birtoklás az ELLENFÉLHEZ kerül (nem lövés után).
- LÖVÉS:        a labda gyorsan a kapu felé tart és megközelíti a gólvonalat.
- GÓL:          olyan lövés, ahol a labda a kapufák között eléri a gólvonalat.

Heurisztikus (a labda sebességéből és helyzetéből), nem betanított modell — a célja
a CSŐVEZETÉK és az API, ami valódi adattal/finomabb modellel pontosítható. Tiszta
Python, szintetikus pályákon tesztelhető.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ..models.tracking import Match, Team
from .calibration import COURT_LENGTH_M, COURT_WIDTH_M
from .tactics import TacticsConfig
from .decisions import ball_holder

# Heurisztikus küszöbök:
SHOT_SPEED_MS = 8.0      # a labda ennél gyorsabban a kapu felé tartva = lövés
APPROACH_X_M = 4.0       # a kaputól (x-ben) ekkora közelségben "kapu-megközelítés"
GOAL_TOL_M = 0.7         # a gólvonalat ennyire megközelítve számít elértnek
GOAL_LOOKAHEAD = 12      # a góldöntéshez ennyi frame-et nézünk előre
TURNOVER_SUPPRESS = 12   # lövés után ennyi frame-en belüli labdaeladást elnyomunk

_GOAL_Y_LOW = COURT_WIDTH_M / 2.0 - 1.5   # 8.5 — alsó kapufa
_GOAL_Y_HIGH = COURT_WIDTH_M / 2.0 + 1.5  # 11.5 — felső kapufa

SHOOTER_LOOKBACK_S = 0.8  # a lövés előtt ennyi időn belülről keressük a lövőt
ASSIST_WINDOW_S = 4.0     # a gól előtt ennyi időn belüli utolsó passz = gólpassz
SAVE_RADIUS_M = 1.6       # a labda ennyire a kapushoz érve = védés
_GK_NEAR_GOAL_M = 9.0     # a kapus csak a SAJÁT kapujánál "véd"


class EventType(str, Enum):
    PASS = "pass"           # passz (csapaton belül)
    SHOT = "shot"           # lövés (nem gól)
    GOAL = "goal"           # gól
    TURNOVER = "turnover"   # labdaeladás (az ellenfél szerzi meg)


@dataclass
class MatchEvent:
    """Egy felismert esemény.

    - t:       a frame ideje.
    - type:    az esemény típusa (EventType).
    - team:    a "cselekvő" csapat (passznál/lövésnél a támadó; labdaeladásnál a
               labdát ELVESZTŐ csapat).
    - player_id: a fő szereplő track_id-ja, ha értelmezhető, különben None.
    - detail:  opcionális kiegészítés (pl. passznál a fogadó id-ja).
    """
    t: int
    type: EventType
    team: Team
    player_id: Optional[int] = None
    detail: Optional[dict] = None


def _attacking_team_for_goal(goal_x: float, config: TacticsConfig) -> Team:
    """Melyik csapat TÁMADJA a megadott kaput (annak a kapunak a támadója)."""
    return Team.HOME if config.attacks_toward_x(Team.HOME) == goal_x else Team.AWAY


def _shooter_before(match: Match, idx: int, team: Team,
                    config: TacticsConfig, fps: float) -> Optional[int]:
    """A lövő: az utolsó labdabirtokos a TÁMADÓ csapatból a lövés előtt.

    A lövés pillanatában a labda már úton van (nincs birtokos), ezért
    visszafelé keresünk legfeljebb SHOOTER_LOOKBACK_S másodpercet."""
    back = max(0, idx - round(SHOOTER_LOOKBACK_S * fps))
    for j in range(idx, back - 1, -1):
        holder = ball_holder(match.frames[j], config)
        if holder is not None and holder.team == team:
            return holder.track_id
    return None


def _save_by_goalkeeper(match: Match, idx: int, goal_x: float) -> Optional[int]:
    """Nem-gól lövésnél: hárította-e a kapus? A kapus-jelölést (role=
    "kapus", lásd goalkeeper.py) használja — ha a labda a lövés utáni
    ablakban a SAJÁT kapujánál álló kapus közelébe ér, az védés.

    Visszatérés: a védő kapus track_id-ja, vagy None (mellé/blokk)."""
    end = min(len(match.frames), idx + GOAL_LOOKAHEAD)
    for j in range(idx, end):
        f = match.frames[j]
        b = f.ball
        if b is None:
            continue
        for p in f.players:
            if p.role != "kapus" or abs(p.x - goal_x) > _GK_NEAR_GOAL_M:
                continue
            if math.hypot(p.x - b.x, p.y - b.y) <= SAVE_RADIUS_M:
                return p.track_id
    return None


def _reaches_goal_line(match: Match, idx: int, goal_x: float) -> bool:
    """Előrenézve eléri-e a labda a gólvonalat a kapufák között (= gól)."""
    end = min(len(match.frames), idx + GOAL_LOOKAHEAD)
    for j in range(idx, end):
        b = match.frames[j].ball
        if b is None:
            continue
        if abs(b.x - goal_x) <= GOAL_TOL_M and _GOAL_Y_LOW <= b.y <= _GOAL_Y_HIGH:
            return True
    return False


def detect_shots(match: Match, config: Optional[TacticsConfig] = None) -> list[MatchEvent]:
    """Lövések és gólok felismerése a labda kinematikájából.

    Egy lövést akkor jelölünk, amikor a labda GYORSAN a kapu felé tart és (x-ben)
    megközelíti azt. Debounce: egy kapu-megközelítésből egy esemény. Gól, ha a
    labda a kapufák között eléri a gólvonalat.
    """
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    events: list[MatchEvent] = []
    in_zone = {0.0: False, COURT_LENGTH_M: False}
    prev = None

    for i, f in enumerate(match.frames):
        b = f.ball
        if b is None:
            prev = None
            continue
        for goal_x in (0.0, COURT_LENGTH_M):
            dxg = abs(b.x - goal_x)
            if prev is not None:
                vx = (b.x - prev[0]) * fps
                speed = math.hypot(b.x - prev[0], b.y - prev[1]) * fps
            else:
                vx = speed = 0.0
            toward = (vx < 0 and goal_x == 0.0) or (vx > 0 and goal_x == COURT_LENGTH_M)

            if dxg <= APPROACH_X_M and toward and speed >= SHOT_SPEED_MS and not in_zone[goal_x]:
                in_zone[goal_x] = True
                is_goal = _reaches_goal_line(match, i, goal_x)
                attacking = _attacking_team_for_goal(goal_x, config)
                shooter = _shooter_before(match, i, attacking, config, fps)
                # Kimenetel: gól / védés (a kapus-jel alapján) / mellé-blokk.
                if is_goal:
                    detail: dict = {"outcome": "goal"}
                else:
                    gk = _save_by_goalkeeper(match, i, goal_x)
                    detail = ({"outcome": "save", "goalkeeper_id": gk}
                              if gk is not None else {"outcome": "miss"})
                events.append(MatchEvent(
                    t=f.t,
                    type=EventType.GOAL if is_goal else EventType.SHOT,
                    team=attacking,
                    player_id=shooter,
                    detail=detail,
                ))
            if dxg > APPROACH_X_M + 1.0:
                in_zone[goal_x] = False
        prev = (b.x, b.y)
    return events


def detect_possession_changes(match: Match,
                              config: Optional[TacticsConfig] = None) -> list[MatchEvent]:
    """Passzok (csapaton belül) és labdaeladások (az ellenfélhez) felismerése."""
    config = config or TacticsConfig()
    events: list[MatchEvent] = []
    prev_holder = None
    for f in match.frames:
        holder = ball_holder(f, config)
        if holder is not None and prev_holder is not None and holder.track_id != prev_holder.track_id:
            if holder.team == prev_holder.team:
                events.append(MatchEvent(
                    t=f.t, type=EventType.PASS, team=prev_holder.team,
                    player_id=prev_holder.track_id,
                    detail={"receiver_id": holder.track_id},
                ))
            else:
                events.append(MatchEvent(
                    t=f.t, type=EventType.TURNOVER, team=prev_holder.team,
                    player_id=prev_holder.track_id,
                ))
        if holder is not None:
            prev_holder = holder
    return events


def annotate_assists(match: Match, events: list[MatchEvent],
                     config: Optional[TacticsConfig] = None) -> list[MatchEvent]:
    """Gólpassz (assist) hozzárendelése a gólokhoz.

    Gólpassz: a gól előtti ASSIST_WINDOW_S időablakban az UTOLSÓ olyan
    saját-csapatbeli passz, amelynek a fogadója a gól lövője. A gól
    detail-jébe kerül ("assist_id": a passzoló track_id-ja) — az esemény-
    lista, a jelentés és az edzői összefoglaló innen olvassa."""
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = ASSIST_WINDOW_S * fps
    passes = [e for e in events if e.type == EventType.PASS]
    for g in events:
        if g.type != EventType.GOAL or g.player_id is None:
            continue
        best = None
        for p in passes:
            if not (0 <= g.t - p.t <= win) or p.team != g.team:
                continue
            if (p.detail or {}).get("receiver_id") != g.player_id:
                continue
            if best is None or p.t > best.t:
                best = p
        # Önmagának adott "passz" (track-zaj) nem gólpassz.
        if best is not None and best.player_id is not None \
                and best.player_id != g.player_id:
            g.detail = {**(g.detail or {}), "assist_id": best.player_id}
    return events


def detect_events(match: Match, config: Optional[TacticsConfig] = None) -> list[MatchEvent]:
    """Az összes esemény időrendben, a lövés utáni labdaeladást elnyomva.

    A lövés után az ellenfél szinte mindig megszerzi a labdát (kapus/blokk) — ezt
    nem akarjuk külön "labdaeladásként" is jelölni, ezért a lövés/gól közelében
    lévő labdaeladásokat kihagyjuk. A gólokhoz a gólpasszt is hozzárendeljük
    (annotate_assists) — a passz-lista itt már együtt van a gólokkal.
    """
    config = config or TacticsConfig()
    shots = detect_shots(match, config)
    changes = detect_possession_changes(match, config)
    shot_times = [e.t for e in shots if e.type in (EventType.SHOT, EventType.GOAL)]

    filtered_changes = []
    for e in changes:
        if e.type == EventType.TURNOVER and any(abs(e.t - st) <= TURNOVER_SUPPRESS for st in shot_times):
            continue  # lövés után — nem külön labdaeladás
        filtered_changes.append(e)

    return annotate_assists(match, sorted(shots + filtered_changes, key=lambda e: e.t),
                            config)


def event_counts(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """Esemény-összegzés: típusonkénti darabszám."""
    events = detect_events(match, config)
    by_type: dict[str, int] = {t.value: 0 for t in EventType}
    for e in events:
        by_type[e.type.value] += 1
    return {"total": len(events), "by_type": by_type}


# Gól-koncentráció: legalább ennyi azonosított lövőjű gól kell az ítélethez,
# és ekkora részesedés számít "egy emberre épülő" gólszerzésnek.
CONC_MIN_GOALS = 5
CONC_TOP_SHARE_PCT = 40.0


def goal_concentration(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Gól-koncentráció (gólfüggés): mennyire épül EGY emberre a csapat
    gólszerzése.

    A felismert gólok lövő szerinti eloszlásából számoljuk a fő gólszerző
    részesedését. Ha a gólok nagy hányada (CONC_TOP_SHARE_PCT%) egy
    játékostól jön, az ő kikapcsolása (szoros emberfogás, korai kilépés)
    az egész támadójátékot megfojtja; ha a gólok elosztottak, csak a
    csapatszintű védekezés működik ellenük.

    Visszatérés csapatonként:
      {"goals", "scorers": [{"player_id","goals"}] (gólszám szerint),
       "top_share_pct", "concentrated"} — goals az azonosított lövőjű
    gólok száma; top_share_pct a fő gólszerző részesedése (None, ha
    goals < CONC_MIN_GOALS); concentrated True/False/None ítélet.
    """
    config = config or TacticsConfig()
    tally: dict[str, dict[int, int]] = {"home": {}, "away": {}}
    for e in detect_shots(match, config):
        if e.type != EventType.GOAL or e.player_id is None:
            continue
        side = tally[e.team.value]
        side[e.player_id] = side.get(e.player_id, 0) + 1

    out: dict = {}
    for s in ("home", "away"):
        scorers = [{"player_id": p, "goals": n}
                   for p, n in sorted(tally[s].items(), key=lambda kv: -kv[1])]
        total = sum(r["goals"] for r in scorers)
        if total >= CONC_MIN_GOALS and scorers:
            share = round(100.0 * scorers[0]["goals"] / total, 1)
            conc = share >= CONC_TOP_SHARE_PCT
        else:
            share = None
            conc = None
        out[s] = {"goals": total, "scorers": scorers,
                  "top_share_pct": share, "concentrated": conc}
    return out


def assist_network(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """Gólpassz-hálózat: ki kinek készíti elő a gólokat.

    A gólokhoz rendelt assist_id-ból (lásd annotate_assists) építjük a
    (gólpasszoló → lövő) párokat. Visszatérés csapatonként:
    {"pairs": [{"from","to","goals"}] (gólszám szerint), "leaders":
    [{"player_id","assists"}]} — a leaders a legtöbb gólpasszt adók."""
    config = config or TacticsConfig()
    events = detect_events(match, config)
    out = {"home": {"pairs": {}, "leaders": {}},
           "away": {"pairs": {}, "leaders": {}}}
    for e in events:
        if e.type != EventType.GOAL:
            continue
        aid = (e.detail or {}).get("assist_id")
        if aid is None or e.player_id is None:
            continue
        side = e.team.value
        key = (aid, e.player_id)
        out[side]["pairs"][key] = out[side]["pairs"].get(key, 0) + 1
        out[side]["leaders"][aid] = out[side]["leaders"].get(aid, 0) + 1

    result = {}
    for side in ("home", "away"):
        pairs = [{"from": a, "to": b, "goals": n}
                 for (a, b), n in sorted(out[side]["pairs"].items(),
                                         key=lambda kv: -kv[1])]
        leaders = [{"player_id": p, "assists": n}
                   for p, n in sorted(out[side]["leaders"].items(),
                                      key=lambda kv: -kv[1])]
        result[side] = {"pairs": pairs, "leaders": leaders}
    return result


# Lövés-sebesség: hihetőségi plafon (követési hiba fölötte) és a
# sebesség-méréshez nézett ablak a lövés-esemény után (kockában).
SHOT_SPEED_MAX_MS = 45.0     # ~160 km/h fölött mérési hiba
SHOT_SPEED_WINDOW = 8


def shot_speeds(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """Lövés-sebességek a labda-kinematikából.

    Minden felismert lövésnél a lövést követő pár kockában mért
    leggyorsabb labda-elmozdulás adja a lövés sebességét (m/s → km/h).
    A hihetetlen (SHOT_SPEED_MAX_MS feletti) értékeket eldobjuk.

    Visszatérés: {"shots": [{"t","team","player_id","speed_kmh"}],
    "teams": {"home"/"away": {"avg_kmh", "max_kmh", "n"}},
    "fastest": {"t","team","player_id","speed_kmh"} | None}
    """
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    frames_by_t = {f.t: f for f in match.frames}

    out_shots = []
    for e in detect_shots(match, config):
        peak = 0.0
        prev = None
        for dt in range(SHOT_SPEED_WINDOW + 1):
            fr = frames_by_t.get(e.t + dt)
            if fr is None or fr.ball is None:
                prev = None
                continue
            if prev is not None:
                v = math.hypot(fr.ball.x - prev[0], fr.ball.y - prev[1]) * fps
                if v <= SHOT_SPEED_MAX_MS:
                    peak = max(peak, v)
            prev = (fr.ball.x, fr.ball.y)
        if peak > 0:
            out_shots.append({"t": e.t, "team": e.team.value,
                              "player_id": e.player_id,
                              "speed_kmh": round(peak * 3.6, 1)})

    teams = {}
    for side in ("home", "away"):
        vals = [s_["speed_kmh"] for s_ in out_shots if s_["team"] == side]
        teams[side] = {
            "avg_kmh": round(sum(vals) / len(vals), 1) if vals else 0.0,
            "max_kmh": max(vals) if vals else 0.0,
            "n": len(vals),
        }
    fastest = max(out_shots, key=lambda s_: s_["speed_kmh"], default=None)
    return {"shots": out_shots, "teams": teams, "fastest": fastest}


# Lövőerő-esés (fáradás-jel): félidőnként legalább ennyi mért lövés kell az
# összevetéshez, és ekkora (%-os) átlagsebesség-esés számít jelzésnek.
FADE_MIN_SHOTS = 3
FADE_DROP_PCT = 8.0


def shot_speed_fade(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """Lövőerő-esés: a lövés-sebesség változása az 1. és a 2. félidő között —
    a fáradás egyik legobjektívebb jele.

    A mért lövés-sebességeket (shot_speeds) a felismert félidő (detect_halftime)
    mentén két csoportra bontjuk, és csapatonként összevetjük az átlagokat.
    Ha a 2. félidei átlag érdemben (FADE_DROP_PCT%) alacsonyabb, a csapat
    lövőereje fárad — a hajrában puhábbak a lövései; ha nő, frissen pörgetik
    a végét (mély rotáció / jó kondíció).

    Visszatérés csapatonként:
      {"fh_n", "fh_avg_kmh", "sh_n", "sh_avg_kmh", "drop_pct"} — az 1./2.
    félidei mért lövésszám és átlagsebesség; drop_pct a százalékos esés
    (pozitív = lassul, negatív = gyorsul), None, ha nincs elég mért lövés
    (félidőnként FADE_MIN_SHOTS) vagy nincs félidő-jel.
    """
    from .halftime import detect_halftime

    config = config or TacticsConfig()
    empty = {"fh_n": 0, "fh_avg_kmh": 0.0, "sh_n": 0, "sh_avg_kmh": 0.0,
             "drop_pct": None}
    out = {"home": dict(empty), "away": dict(empty)}
    ht = detect_halftime(match)
    if ht is None:
        return out
    shots = shot_speeds(match, config)["shots"]
    for side in ("home", "away"):
        fh = [s_["speed_kmh"] for s_ in shots
              if s_["team"] == side and s_["t"] <= ht]
        sh = [s_["speed_kmh"] for s_ in shots
              if s_["team"] == side and s_["t"] > ht]
        rec = out[side]
        rec["fh_n"] = len(fh)
        rec["sh_n"] = len(sh)
        rec["fh_avg_kmh"] = round(sum(fh) / len(fh), 1) if fh else 0.0
        rec["sh_avg_kmh"] = round(sum(sh) / len(sh), 1) if sh else 0.0
        if len(fh) >= FADE_MIN_SHOTS and len(sh) >= FADE_MIN_SHOTS \
                and rec["fh_avg_kmh"] > 0:
            rec["drop_pct"] = round(
                100.0 * (rec["fh_avg_kmh"] - rec["sh_avg_kmh"])
                / rec["fh_avg_kmh"], 1)
    return out


def pass_network(match: Match, config: Optional[TacticsConfig] = None,
                 top: int = 5) -> dict:
    """Passz-hálózat: ki kinek adogat — a játékszervezés fő tengelye.

    A PASS eseményekből (adó → fogadó) építjük a leggyakoribb párokat és
    a legtöbb passzban részt vevő játékosokat. A gólpassz-hálózattal
    (assist_network) szemben itt MINDEN passz számít, nem csak a gólt
    előkészítő — így a csapat játékának szerkezete látszik: kin megy át
    a labda, melyik kapcsolat a "motor".

    Visszatérés csapatonként: {"total_passes", "pairs":
    [{"from","to","passes"}] (top szerint), "hubs":
    [{"player_id","passes"}] — adott VAGY kapott passzok összege}."""
    config = config or TacticsConfig()
    events = detect_events(match, config)
    out = {"home": {"pairs": {}, "hubs": {}, "total": 0},
           "away": {"pairs": {}, "hubs": {}, "total": 0}}
    for e in events:
        if e.type != EventType.PASS:
            continue
        rid = (e.detail or {}).get("receiver_id")
        if rid is None or e.player_id is None:
            continue
        side = e.team.value
        rec = out[side]
        rec["total"] += 1
        key = (e.player_id, rid)
        rec["pairs"][key] = rec["pairs"].get(key, 0) + 1
        for pid in (e.player_id, rid):
            rec["hubs"][pid] = rec["hubs"].get(pid, 0) + 1

    result = {}
    for side in ("home", "away"):
        rec = out[side]
        pairs = [{"from": a, "to": b, "passes": n}
                 for (a, b), n in sorted(rec["pairs"].items(),
                                         key=lambda kv: -kv[1])[:top]]
        hubs = [{"player_id": p, "passes": n}
                for p, n in sorted(rec["hubs"].items(),
                                   key=lambda kv: -kv[1])[:top]]
        result[side] = {"total_passes": rec["total"], "pairs": pairs,
                        "hubs": hubs}
    return result
