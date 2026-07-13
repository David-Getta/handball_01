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


def detect_events(match: Match, config: Optional[TacticsConfig] = None) -> list[MatchEvent]:
    """Az összes esemény időrendben, a lövés utáni labdaeladást elnyomva.

    A lövés után az ellenfél szinte mindig megszerzi a labdát (kapus/blokk) — ezt
    nem akarjuk külön "labdaeladásként" is jelölni, ezért a lövés/gól közelében
    lévő labdaeladásokat kihagyjuk.
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

    return sorted(shots + filtered_changes, key=lambda e: e.t)


def event_counts(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """Esemény-összegzés: típusonkénti darabszám."""
    events = detect_events(match, config)
    by_type: dict[str, int] = {t.value: 0 for t in EventType}
    for e in events:
        by_type[e.type.value] += 1
    return {"total": len(events), "by_type": by_type}
