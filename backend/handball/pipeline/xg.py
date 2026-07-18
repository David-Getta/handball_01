"""Helyzetminőség (xG) — mennyit "ér" egy lövéshelyzet.

Két lövés nem egyforma: a hatosról, szemből leadott lövés sokkal nagyobb
eséllyel gól, mint a szélső szögből vagy kilencméterről lőtt. Minden
felismert lövéshez (detect_shots) kiszámolunk egy 0..1 közti értéket a
helyzet minőségére, KIZÁRÓLAG a lövés helyéből:

- távolság a kapu közepétől: közelebbről könnyebb;
- a kapu látott szöge: szemből a teljes 3 m-es kapu "látszik", éles
  szélső szögből csak egy szelete.

Szándékosan átlátható heurisztika (nem betanított modell): minden szám
mögött geometria áll, így az érték magyarázható az edzőnek — valódi
adathalmazon később kalibrálható. A csapat-összeg a "várható gól":
a tényleges gólszámmal összevetve látszik, melyik csapat fejezte be
hatékonyan a helyzeteit, és melyik puskázta el őket.
"""

from __future__ import annotations

import math
from typing import Optional

from ..models.tracking import Match, Team
from .calibration import COURT_LENGTH_M, COURT_WIDTH_M
from .tactics import TacticsConfig

# A kapu a pálya rövid oldalának közepén, 3 m széles (y: 8,5..11,5).
_GOAL_HALF_W = 1.5
_GOAL_CY = COURT_WIDTH_M / 2.0

# Távolság-görbe: 6 m-ről ~0,60, 9 m-ről ~0,37, 12 m-ről ~0,15 az alap.
_DIST_BASE = 1.05
_DIST_SLOPE = 0.075
# A látott kapuszög normálása: ~0,9 rad a közeli-középső helyzet szöge.
_ANGLE_FULL_RAD = 0.9
# Az xG végső korlátai (0 és 1 helyett óvatos sáv — heurisztika vagyunk).
_XG_MIN, _XG_MAX = 0.05, 0.90


def xg_of_position(x: float, y: float, goal_x: float) -> float:
    """Egy lövéshelyzet értéke (0..1) a helyből: távolság + látott kapuszög."""
    dx = max(0.5, abs(x - goal_x))  # a kapu síkján állva se osszunk nullával
    dist = math.hypot(x - goal_x, y - _GOAL_CY)
    # A két kapufa iránya közti szög — szemből nagy, éles szögből kicsi.
    a1 = math.atan2(y - (_GOAL_CY - _GOAL_HALF_W), dx)
    a2 = math.atan2(y - (_GOAL_CY + _GOAL_HALF_W), dx)
    angle = abs(a1 - a2)
    p_dist = min(max(_DIST_BASE - _DIST_SLOPE * dist, 0.08), 0.85)
    ang_norm = min(max(angle / _ANGLE_FULL_RAD, 0.0), 1.0)
    xg = p_dist * (0.55 + 0.45 * ang_norm)
    return round(min(max(xg, _XG_MIN), _XG_MAX), 3)


def match_xg(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """A meccs minden lövésének helyzetminősége + csapat-összegzés.

    A lövés helye: a lövő pozíciója az esemény képkockáján; ha a lövő nem
    azonosítható, a labda helye. Visszatérés:
    {"shots": [{"t", "team", "player_id", "x", "y", "xg", "outcome"}],
     "teams": {"home"/"away": {"xg", "goals", "shots", "diff"}},
     "shooters": [{"player_id", "team", "shots", "goals", "xg", "diff"}]}
    — diff = gól − várható gól (pozitív: a helyzetei FELETT teljesít,
    negatív: kihagyott nagy helyzetek). A shooters xG szerint csökkenő."""
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    by_t = {f.t: f for f in match.frames}
    shots: list[dict] = []
    teams = {"home": {"xg": 0.0, "goals": 0, "shots": 0},
             "away": {"xg": 0.0, "goals": 0, "shots": 0}}

    for e in detect_shots(match, config):
        if e.type not in (EventType.SHOT, EventType.GOAL):
            continue
        f = by_t.get(e.t)
        if f is None:
            continue
        x = y = None
        if e.player_id is not None:
            for p in f.players:
                if p.track_id == e.player_id:
                    x, y = p.x, p.y
                    break
        if x is None and f.ball is not None:
            x, y = f.ball.x, f.ball.y
        if x is None:
            continue
        goal_x = config.attacks_toward_x(e.team)
        xg = xg_of_position(x, y, goal_x)
        outcome = (e.detail or {}).get("outcome") or \
            ("goal" if e.type == EventType.GOAL else "miss")
        side = e.team.value
        shots.append({"t": e.t, "team": side, "player_id": e.player_id,
                      "x": round(x, 2), "y": round(y, 2),
                      "xg": xg, "outcome": outcome})
        teams[side]["xg"] += xg
        teams[side]["shots"] += 1
        if e.type == EventType.GOAL:
            teams[side]["goals"] += 1

    for side in ("home", "away"):
        # A lövés-választás minősége: átlagos xG lövésenként (magas = jó
        # helyzetek, alacsony = sok kis esélyű lövés).
        n_sh = teams[side]["shots"]
        teams[side]["avg_xg_per_shot"] = (round(teams[side]["xg"] / n_sh, 3)
                                          if n_sh else 0.0)
        teams[side]["xg"] = round(teams[side]["xg"], 2)
        teams[side]["diff"] = round(teams[side]["goals"] - teams[side]["xg"], 2)

    # Lövőnkénti bontás: ki teljesít a helyzetei felett/alatt. (A lövő
    # nélküli — azonosíthatatlan — lövések csak a csapat-összegben vannak.)
    by_shooter: dict[int, dict] = {}
    for sh in shots:
        pid = sh["player_id"]
        if pid is None:
            continue
        rec = by_shooter.setdefault(pid, {"player_id": pid, "team": sh["team"],
                                          "shots": 0, "goals": 0, "xg": 0.0})
        rec["shots"] += 1
        rec["xg"] += sh["xg"]
        if sh["outcome"] == "goal":
            rec["goals"] += 1
    shooters = []
    for rec in by_shooter.values():
        rec["xg"] = round(rec["xg"], 2)
        rec["diff"] = round(rec["goals"] - rec["xg"], 2)
        shooters.append(rec)
    shooters.sort(key=lambda r: -r["xg"])
    return {"shots": shots, "teams": teams, "shooters": shooters}


# Kihagyott ziccer: legalább ekkora helyzet-érték, gól nélkül.
BIG_CHANCE_XG = 0.5


def missed_big_chances(match: Match,
                       config: Optional[TacticsConfig] = None) -> list[dict]:
    """A kihagyott nagy helyzetek: xG >= BIG_CHANCE_XG, de nem gól.

    A leginkább visszanézendő jelenetek — a klip-export "kihagyott
    ziccer" típusa erre épül. Visszatérés: [{"t","team","player_id",
    "xg"}], idő szerint."""
    out = []
    for sh in match_xg(match, config).get("shots", []):
        if sh.get("xg", 0.0) >= BIG_CHANCE_XG and sh.get("outcome") != "goal":
            out.append({"t": sh["t"], "team": sh["team"],
                        "player_id": sh.get("player_id"), "xg": sh["xg"]})
    out.sort(key=lambda r: r["t"])
    return out


def big_saves(match: Match,
              config: Optional[TacticsConfig] = None) -> list[dict]:
    """Bravúr-védések: nagy értékű (xG >= BIG_CHANCE_XG) helyzet, amit a
    kapus fogott. A kihagyott ziccer tükörképe — a kapus-kiemelések és a
    "nagy védés" klipek alapja. Visszatérés: [{"t","team","player_id",
    "xg"}] — a team a LÖVŐ csapata (a védő kapus az ellenfélé)."""
    out = []
    for sh in match_xg(match, config).get("shots", []):
        if sh.get("xg", 0.0) >= BIG_CHANCE_XG and sh.get("outcome") == "save":
            out.append({"t": sh["t"], "team": sh["team"],
                        "player_id": sh.get("player_id"), "xg": sh["xg"]})
    out.sort(key=lambda r: r["t"])
    return out
