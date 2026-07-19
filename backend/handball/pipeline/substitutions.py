"""Csere-felismerés — mikor forgatja a sorát a csapat, és mi lesz utána.

A kézilabdában a csere röptében történik, a CSEREZÓNÁN át (a felezővonal
±4,5 m-es sávja, az oldalvonal mellett). A követésben ez úgy látszik,
hogy egy track a cserezóna környékén VÉGET ÉR (lemegy), és röviddel
előtte/utána egy ÚJ track ugyanott MEGJELENIK (bejön).

- Egy időben közeli ki-be párokból CSERE-ESEMÉNYT képzünk (csapatonként);
- minden cseréhez megnézzük a következő IMPACT_S másodperc mérlegét
  (dobott/kapott gól) — ebből látszik, ha egy forgatás megtörte a
  lendületet, vagy épp frissítést hozott.

Óvatos heurisztika: a pálya közepén megszakadó követés (takarás) NEM
számít cserének — csak a cserezónában kezdődő/végződő track-ek.
"""

from __future__ import annotations

from typing import Optional

from ..models.tracking import Match, Team
from .calibration import COURT_LENGTH_M, COURT_WIDTH_M
from .tactics import TacticsConfig

# A cserezóna: a felezővonal ±4,5 m-e, az oldalvonalak melletti sáv.
SUB_ZONE_HALF_W_M = 4.5
SUB_ZONE_DEPTH_M = 2.5
# Ki- és belépések ennyi másodpercen belül számítanak EGY cserehullámnak.
SUB_JOIN_S = 10.0
# A csere utáni hatás-ablak (dobott/kapott gólok számolása).
IMPACT_S = 90.0
# A felvétel legelején/legvégén lévő track-kezdet/vég nem csere.
EDGE_MARGIN_S = 3.0


def _in_sub_zone(x: float, y: float) -> bool:
    mid = COURT_LENGTH_M / 2.0
    near_mid = abs(x - mid) <= SUB_ZONE_HALF_W_M
    near_side = y <= SUB_ZONE_DEPTH_M or y >= COURT_WIDTH_M - SUB_ZONE_DEPTH_M
    return near_mid and near_side


def detect_substitutions(match: Match,
                         config: Optional[TacticsConfig] = None) -> list[dict]:
    """Cserehullámok: [{"team", "t", "out_ids", "in_ids"}] időrendben.

    Egy hullámhoz legalább egy KI (a cserezónában végződő track) és egy
    BE (ott kezdődő track) kell ugyanattól a csapattól SUB_JOIN_S-en
    belül — a féloldalas jelek (csak eltűnés) nem cserék."""
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    if not match.frames:
        return []
    t0, t1 = match.frames[0].t, match.frames[-1].t
    margin = round(EDGE_MARGIN_S * fps)

    # Track-ek első/utolsó előfordulása és helye.
    first: dict = {}
    last: dict = {}
    for f in match.frames:
        for p in f.players:
            if p.role == "kapus":
                continue  # a kapuscserét a 7a6-réteg kezeli
            if p.track_id not in first:
                first[p.track_id] = (f.t, p.x, p.y, p.team)
            last[p.track_id] = (f.t, p.x, p.y, p.team)

    outs = []  # (t, team, track_id) — a cserezónában végződő track-ek
    ins = []   # (t, team, track_id) — ott kezdődők
    for tid, (ft, fx, fy, team) in first.items():
        lt, lx, ly, _ = last[tid]
        if ft > t0 + margin and _in_sub_zone(fx, fy):
            ins.append((ft, team, tid))
        if lt < t1 - margin and _in_sub_zone(lx, ly):
            outs.append((lt, team, tid))

    join = round(SUB_JOIN_S * fps)
    events: list[dict] = []
    for team in (Team.HOME, Team.AWAY):
        t_outs = sorted((t, i) for (t, tm, i) in outs if tm == team)
        t_ins = sorted((t, i) for (t, tm, i) in ins if tm == team)
        used_in: set = set()
        i = 0
        while i < len(t_outs):
            ot, _ = t_outs[i]
            wave_outs = []
            while i < len(t_outs) and t_outs[i][0] - ot <= join:
                wave_outs.append(t_outs[i][1])
                i += 1
            wave_ins = [ii for (it, ii) in t_ins
                        if abs(it - ot) <= join and ii not in used_in]
            if wave_outs and wave_ins:
                used_in.update(wave_ins)
                events.append({"team": team.value, "t": int(ot),
                               "out_ids": wave_outs, "in_ids": wave_ins})
    events.sort(key=lambda e: e["t"])
    return events


def substitution_impact(match: Match,
                        config: Optional[TacticsConfig] = None) -> dict:
    """Cserék + a cserék utáni IMPACT_S másodperc mérlege csapatonként.

    Visszatérés: {"events": [ {..., "goals_for_after", "goals_against_after"} ],
                  "teams": {"home"/"away": {"rotations", "goals_for_after",
                                            "goals_against_after"}}}"""
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = round(IMPACT_S * fps)
    goals = [(e.t, e.team.value) for e in detect_shots(match, config)
             if e.type == EventType.GOAL]

    events = detect_substitutions(match, config)
    teams = {side: {"rotations": 0, "goals_for_after": 0,
                    "goals_against_after": 0} for side in ("home", "away")}
    for ev in events:
        gf = sum(1 for (t, tm) in goals
                 if ev["t"] <= t <= ev["t"] + win and tm == ev["team"])
        ga = sum(1 for (t, tm) in goals
                 if ev["t"] <= t <= ev["t"] + win and tm != ev["team"])
        ev["goals_for_after"] = gf
        ev["goals_against_after"] = ga
        rec = teams[ev["team"]]
        rec["rotations"] += 1
        rec["goals_for_after"] += gf
        rec["goals_against_after"] += ga
    return {"events": events, "teams": teams}


# Késő csere: ekkora 2. félidei tempó-esés fölött már cserét várnánk.
LATE_SUB_DROP_PCT = 20.0


def late_sub_flags(match: Match,
                   config: Optional[TacticsConfig] = None) -> list[dict]:
    """Késő cserék: nagy tempó-esésű játékosok, akiket NEM cseréltek le.

    A fáradás-réteg (player_fatigue) és a csere-felismerés metszete:
    aki 20%+ tempót esett a 2. félidőben és végig a pályán maradt, azt
    hasonló meccsen érdemes korábban pihentetni.

    Visszatérés: [{"track_id", "team", "drop_pct"}] esés szerint.
    """
    from .stats import player_fatigue

    config = config or TacticsConfig()
    subbed_out: set = set()
    for w in detect_substitutions(match, config):
        subbed_out.update(w.get("out_ids", []))
    return [{"track_id": r["track_id"], "team": r["team"],
             "drop_pct": r["drop_pct"]}
            for r in player_fatigue(match)
            if r["drop_pct"] >= LATE_SUB_DROP_PCT
            and r["track_id"] not in subbed_out]
