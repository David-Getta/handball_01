"""
[4. fázis] Játékos-döntéselemzés — "mit választott, és mi lett volna a legjobb".

A vízió egyéni elemzés része: egy adott szituációban a labdás játékos opciói
(lövés, vagy passz egy-egy csapattárshoz), ezek ÉRTÉKE, és hogy a tényleges
döntés mennyire volt jó. Aggregálva: "ez a játékos hányszor passzol ide" + milyen
gyakran választja az optimális opciót.

Az értékmodell egy EGYSZERŰ, kézilabdára szabott xG-szerű (várható-érték) heurisztika:
- Lövés értéke: a kaputól mért távolság és a szög alapján (közel + középről = több).
- Passz értéke: a fogadó helyzetéből számolt lövésérték, beszorozva a passz
  sikervalószínűségével (távolság + a passz vonalában álló védők).

Ez nem a végső, betanított EPV-modell, de a felismerés és a kiértékelés CSŐVEZETÉKE
ez — a heurisztika később valódi adatból tanult modellre cserélhető. Tiszta Python,
videó nélkül tesztelhető.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from ..models.tracking import Match, Frame, PlayerPosition, Team
from .calibration import COURT_LENGTH_M, COURT_WIDTH_M
from .tactics import TacticsConfig

GOAL_Y = COURT_WIDTH_M / 2.0  # a kapu közepe y-ban (10 m)


# ---- Értékmodell -----------------------------------------------------------

def shot_value(px: float, py: float, goal_x: float) -> float:
    """Egy lövés xG-szerű értéke (0..1) a pozícióból, a megadott kapu felé.

    Két tényező: a kaputól mért TÁVOLSÁG (közelebb = jobb) és a SZÖG (középről =
    jobb, szélről rosszabb). Monoton és [0,1] közé vágva.
    """
    dist = math.hypot(px - goal_x, py - GOAL_Y)
    lateral = abs(py - GOAL_Y)                       # oldalirányú eltérés a kaputól
    angle_factor = max(0.25, 1.0 - lateral / 14.0)   # szélen kisebb
    base = max(0.0, 1.0 - dist / 22.0)               # ~22 m-en túl ~0
    return max(0.02, min(0.95, base * angle_factor))


def _point_segment_distance(px, py, ax, ay, bx, by) -> float:
    """Egy pont (p) távolsága az A–B szakasztól (a passz vonalának ellenőrzéséhez)."""
    dx, dy = bx - ax, by - ay
    seg_len2 = dx * dx + dy * dy
    if seg_len2 == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / seg_len2
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def pass_completion(holder: PlayerPosition, target: PlayerPosition,
                    frame: Frame, lane_width_m: float = 1.5) -> float:
    """A passz sikervalószínűsége (0..1): távolság + a vonalban álló védők alapján.

    Hosszabb passz kockázatosabb; a holder–target vonalához közeli ELLENFELEK
    (a sávon belül) tovább csökkentik az esélyt.
    """
    dist = math.hypot(holder.x - target.x, holder.y - target.y)
    base = max(0.1, 1.0 - dist / 35.0)
    lane_def = 0
    for p in frame.players:
        if p.team == holder.team:
            continue
        d = _point_segment_distance(p.x, p.y, holder.x, holder.y, target.x, target.y)
        if d <= lane_width_m:
            lane_def += 1
    return max(0.05, min(0.99, base - 0.3 * lane_def))


# ---- Opciók egy szituációban ----------------------------------------------

@dataclass
class Option:
    """Egy döntési opció a labdás játékosnak.

    - kind:      "shoot" (lövés) vagy "pass" (passz).
    - target_id: passznál a fogadó track_id-ja; lövésnél None.
    - value:     az opció becsült értéke (0..1).
    """
    kind: str
    target_id: Optional[int]
    value: float


def ball_holder(frame: Frame, config: TacticsConfig) -> Optional[PlayerPosition]:
    """A labdát épp birtokló JÁTÉKOS (a labdához legközelebbi, sugáron belül)."""
    ball = frame.ball
    if ball is None or not frame.players:
        return None
    nearest = min(frame.players, key=lambda p: math.hypot(p.x - ball.x, p.y - ball.y))
    if math.hypot(nearest.x - ball.x, nearest.y - ball.y) > config.possession_radius_m:
        return None
    return nearest


def evaluate_options(frame: Frame, holder: PlayerPosition,
                     config: Optional[TacticsConfig] = None) -> list[Option]:
    """A labdás játékos összes opciója értékkel: lövés + passz minden csapattárshoz."""
    config = config or TacticsConfig()
    goal_x = config.attacks_toward_x(holder.team)
    options = [Option("shoot", None, shot_value(holder.x, holder.y, goal_x))]
    for p in frame.players:
        if p.team != holder.team or p.track_id == holder.track_id:
            continue
        sv = shot_value(p.x, p.y, goal_x)
        comp = pass_completion(holder, p, frame)
        options.append(Option("pass", p.track_id, sv * comp))
    return options


def best_option(options: list[Option]) -> Optional[Option]:
    """A legnagyobb értékű opció (vagy None, ha nincs)."""
    return max(options, key=lambda o: o.value) if options else None


# ---- Passzok felismerése és a döntések elemzése ----------------------------

@dataclass
class PassEvent:
    """Egy felismert passz: a labda egy csapattárshoz került.

    - t:             a passz "megérkezésének" frame-ideje.
    - passer_id:     a passzoló track_id-ja.
    - receiver_id:   a fogadó track_id-ja.
    - team:          a csapat.
    - decision_frame: a döntés frame-je (ahol a passzoló még birtokolta a labdát).
    - passer_pos:    a passzoló pozíciója a döntés pillanatában.
    """
    t: int
    passer_id: int
    receiver_id: int
    team: Team
    decision_frame: Frame
    passer_pos: PlayerPosition


def detect_passes(match: Match, config: Optional[TacticsConfig] = None) -> list[PassEvent]:
    """Passzok felismerése: a labdabirtokos csapaton belüli VÁLTÁSA egy passz.

    Végigmegyünk a frame-eken; ha a labdás játékos megváltozik UGYANAZON a
    csapaton belül, az egy passz (az előző birtokostól az újhoz).
    """
    config = config or TacticsConfig()
    passes: list[PassEvent] = []
    prev_holder: Optional[PlayerPosition] = None
    prev_frame: Optional[Frame] = None

    for f in match.frames:
        holder = ball_holder(f, config)
        if holder is not None and prev_holder is not None:
            if holder.team == prev_holder.team and holder.track_id != prev_holder.track_id:
                passes.append(PassEvent(
                    t=f.t, passer_id=prev_holder.track_id, receiver_id=holder.track_id,
                    team=holder.team, decision_frame=prev_frame, passer_pos=prev_holder,
                ))
        if holder is not None:
            prev_holder = holder
            prev_frame = f
    return passes


@dataclass
class DecisionReport:
    """Egy játékos döntéseinek összegzése.

    - player_id:        a vizsgált játékos.
    - passes:           hány passzát ismertük fel.
    - pass_distribution: fogadónként hány passz (pl. "10/7-szer ide passzol").
    - optimal_rate:     a passzok hányada (0..1), ahol az ÉRTÉK szerinti legjobb
                        opció épp a választott passz volt.
    - avg_value_gap:    átlagosan mennyi értéket "hagyott az asztalon" (a legjobb
                        opció értéke − a választott opció értéke).
    """
    player_id: int
    passes: int
    pass_distribution: dict[int, int] = field(default_factory=dict)
    optimal_rate: float = 0.0
    avg_value_gap: float = 0.0


def analyze_player_decisions(match: Match, player_id: int,
                             config: Optional[TacticsConfig] = None) -> DecisionReport:
    """Egy játékos passz-döntéseinek elemzése: kihez passzol és mennyire optimálisan.

    Minden passzánál a döntés pillanatában kiértékeljük az opciókat, megnézzük a
    legjobbat, és összevetjük a ténylegesen választott passzal.
    """
    config = config or TacticsConfig()
    passes = [pe for pe in detect_passes(match, config) if pe.passer_id == player_id]

    distribution: dict[int, int] = {}
    optimal = 0
    gaps: list[float] = []

    for pe in passes:
        distribution[pe.receiver_id] = distribution.get(pe.receiver_id, 0) + 1
        options = evaluate_options(pe.decision_frame, pe.passer_pos, config)
        best = best_option(options)
        # A ténylegesen választott opció: passz a fogadóhoz.
        actual = next((o for o in options
                       if o.kind == "pass" and o.target_id == pe.receiver_id), None)
        if best is not None and actual is not None:
            gaps.append(best.value - actual.value)
            if abs(best.value - actual.value) < 1e-9:
                optimal += 1

    n = len(passes)
    return DecisionReport(
        player_id=player_id,
        passes=n,
        pass_distribution=distribution,
        optimal_rate=(optimal / n) if n else 0.0,
        avg_value_gap=(sum(gaps) / len(gaps)) if gaps else 0.0,
    )
