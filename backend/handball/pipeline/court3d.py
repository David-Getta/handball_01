"""3D-pálya segédszámok — a 3D nézet (app és böngésző) közös geometriája.

A 3D pálya három edzői eszközt kap, és mindhárom számát EGY helyen
számoljuk, hogy az appbeli és a böngészős (VR) nézet ugyanazt mondja:

- **Lövés-mérés**: a padlóra kattintott pontból a közelebbi kapu
  távolsága, a "kapu-szög" (a két kapufa között látott szög — minél
  kisebb, annál kevesebb a kapu a lövőnek), és hogy a pont a 6 m-es
  kapuelőtérben, a 6–9 m közötti sávban vagy a 9 m-en túl van-e. A
  6 és 9 m-es vonal a szabálykönyv szerint a KAPUFÁKTÓL mért távolság
  (a kapufák közti szakasztól), nem a kapu közepétől.
- **Védekezési sablonok**: a 6-0, 5-1, 4-2 és 3-2-1 fal tankönyvi
  állása (hat mezőnyvédő), hogy a valódi falat mellé lehessen tenni.
  A sablonok a `tactics.detect_formation` sáv-határaival készültek: a
  felismerő a saját sablonját a saját nevén ismeri fel (teszt őrzi).
- **Védekezés-idővonal**: másodpercenként, ki védekezik és milyen
  falban (a `detect_formation` címkéjével) — a 3D nézet ebből mondja,
  "most 5-1-ben védekeznek", és ebből teszi a sablont a jó kapu elé.

Koordináták: méter, x a hosszanti tengely (0 a bal kapu, 40 a jobb),
y a rövid (0..20), a kapu közepe y = 10.
"""

from __future__ import annotations

import math
import re
from typing import Optional

from ..models.tracking import Match, Team
from .calibration import COURT_LENGTH_M, COURT_WIDTH_M, GOAL_WIDTH_M
from .primitive_cache import copy_deep, memoize_primitive
from .tactics import TacticsConfig

# A szabálykönyvi vonalak a kapufák közti szakasztól mérve (méter).
GOAL_AREA_LINE_M = 6.0
FREE_THROW_LINE_M = 9.0

# A védekezés-idővonal mintavétele (másodperc): a fal alakja ennél
# sűrűbben nem változik érdemben, és egy 60 perces meccs így 3600 sor.
DEFENCE_TIMELINE_STEP_S = 1.0


def _jersey_map(match: Match) -> dict:
    """track_id → mezszám (trackenként az ELSŐ ismert érték) — a jelenet-
    rétegek, a jegyzet-ábra és a klip-motor (clips._jersey_of_track)
    közös szabálya; a hatókörön belül meccsenként egyszer számolva."""
    from .primitive_cache import cached

    def szamol():
        jersey: dict = {}
        for f in match.frames:
            for p in f.players:
                if p.jersey_number is not None and p.track_id not in jersey:
                    jersey[p.track_id] = p.jersey_number
        return jersey
    return cached("court3d.jersey_map", match, None, szamol, copy=dict)


def _nearest_keeper(frame, team: Team, goal_x: float):
    """A csapat kapus-jelölésű játékosa a kockán — több ilyennél (cserés
    átfedés, hibás jelölés) a saját kapu közepéhez legközelebbi; None, ha
    nincs."""
    if frame is None:
        return None
    cy = COURT_WIDTH_M / 2.0
    kapusok = [p for p in frame.players if p.team == team and p.role == "kapus"]
    return (min(kapusok, key=lambda p: math.hypot(p.x - goal_x, p.y - cy))
            if kapusok else None)

# Tankönyvi falak a BAL kapu (x = 0) előtt: (mélység a gólvonaltól, y).
# Hat mezőnyvédő; a jobb kapura tükrözve (x → 40 − x). A mélységek a
# `tactics.detect_formation` sávjaihoz igazodnak (hátsó ≤ 7 m, közép
# ≤ 10,5 m, előretolt azon túl), így a felismerő ezeket a saját nevükön
# ismeri fel. Minden pont a 6 m-es vonalon KÍVÜL áll (a kapuelőtérbe a
# védő nem léphet be).
FORMATION_TEMPLATES: dict[str, list[tuple[float, float]]] = {
    # Hat ember egy vonalban a 6 m-es vonal előtt.
    "6-0": [(4.2, 2.6), (6.3, 5.6), (6.7, 8.6),
            (6.7, 11.4), (6.3, 14.4), (4.2, 17.4)],
    # Öt hátul, egy előretolt középen (az irányító zavarására).
    "5-1": [(4.4, 2.8), (6.4, 6.0), (6.8, 10.0),
            (6.4, 14.0), (4.4, 17.2), (10.0, 10.0)],
    # Négy hátul, két előretolt a két átlövő elé.
    "4-2": [(4.6, 3.4), (6.6, 7.6), (6.6, 12.4),
            (4.6, 16.6), (9.6, 7.5), (9.6, 12.5)],
    # Három lépcső: három hátul, két félhalf, egy csúcs.
    "3-2-1": [(4.4, 3.0), (6.8, 10.0), (4.4, 17.0),
              (8.6, 6.0), (8.6, 14.0), (11.0, 10.0)],
}


def _post_segment_distance(x: float, y: float, goal_x: float) -> float:
    """A pont távolsága a kapufák közti szakasztól (a 6/9 m-es vonal alapja)."""
    y1 = COURT_WIDTH_M / 2.0 - GOAL_WIDTH_M / 2.0
    y2 = COURT_WIDTH_M / 2.0 + GOAL_WIDTH_M / 2.0
    ny = min(max(y, y1), y2)
    return math.hypot(x - goal_x, y - ny)


def shot_geometry(x: float, y: float, goal: Optional[str] = None) -> dict:
    """Lövés-mérés a pálya (x, y) pontjából.

    Mit mér: a kapu közepének távolságát, a kapu-szöget (a két kapufa
    között a pontból látott szög, fokban), a kapufáktól mért távolságot
    (ez a 6 és 9 m-es vonal mércéje), és a sávot.

    Edzőileg: a távolság önmagában keveset mond — a sarokból 7 méterről
    kevesebb kapu látszik, mint középről 10 méterről. A kapu-szög ezt
    mutatja meg: ugyanaz a távolság szélről fele akkora célt ad.

    `goal`: "bal" (x = 0) vagy "jobb" (x = 40); alapból a közelebbi.
    Visszatérés: {"goal", "goal_x", "distance_m", "post_distance_m",
    "angle_deg", "zone"} — a zone "kapuelőtér" / "6–9 m" / "9 m-en túl".
    """
    if goal not in ("bal", "jobb"):
        goal = "bal" if x <= COURT_LENGTH_M / 2.0 else "jobb"
    goal_x = 0.0 if goal == "bal" else COURT_LENGTH_M
    cy = COURT_WIDTH_M / 2.0
    y1 = cy - GOAL_WIDTH_M / 2.0
    y2 = cy + GOAL_WIDTH_M / 2.0
    v1 = (goal_x - x, y1 - y)
    v2 = (goal_x - x, y2 - y)
    n1 = math.hypot(*v1)
    n2 = math.hypot(*v2)
    if n1 < 1e-9 or n2 < 1e-9:
        angle = 180.0  # a kapufán állva
    else:
        cos_a = (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)
        angle = math.degrees(math.acos(max(-1.0, min(1.0, cos_a))))
    post_d = _post_segment_distance(x, y, goal_x)
    if post_d < GOAL_AREA_LINE_M:
        zone = "kapuelőtér"
    elif post_d < FREE_THROW_LINE_M:
        zone = "6–9 m"
    else:
        zone = "9 m-en túl"
    return {"goal": goal, "goal_x": goal_x,
            "distance_m": round(math.hypot(x - goal_x, y - cy), 2),
            "post_distance_m": round(post_d, 2),
            "angle_deg": round(angle, 1),
            "zone": zone}


def formation_template(name: str, goal_x: float) -> list[tuple[float, float]]:
    """A tankönyvi fal pozíciói a `goal_x` kapu előtt (pálya-méterben).

    `goal_x` 0 (bal kapu) vagy 40 (jobb kapu); ismeretlen névre üres lista.
    """
    sablon = FORMATION_TEMPLATES.get(name)
    if not sablon:
        return []
    jobb = goal_x > COURT_LENGTH_M / 2.0
    return [((COURT_LENGTH_M - d) if jobb else d, y) for d, y in sablon]


def defence_timeline(match: Match, config: Optional[TacticsConfig] = None,
                     step_s: float = DEFENCE_TIMELINE_STEP_S) -> list[dict]:
    """Ki védekezik, milyen falban — `step_s` másodpercenként.

    Csak a SZERVEZETT támadás pillanatai (a `classify_phase` szerint):
    átmenetben és labda nélkül nincs fal, ott nem állítunk semmit.

    Visszatérés: [{"t" (videó-kocka), "s" (másodperc), "defending"
    ("home"/"away"), "label" (a `detect_formation` címkéje), "goal_x"
    (a védett kapu x-e)}], időrendben.
    """
    from .tactics import Phase, classify_phase, detect_formation

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    lepes = max(1, int(round(step_s * fps)))
    out: list[dict] = []
    utolso_t: Optional[int] = None
    for f in match.frames:
        if utolso_t is not None and f.t - utolso_t < lepes:
            continue
        phase = classify_phase(f, config)
        if phase == Phase.HOME_ATTACK:
            vedo = Team.AWAY
        elif phase == Phase.AWAY_ATTACK:
            vedo = Team.HOME
        else:
            continue
        utolso_t = f.t
        out.append({"t": f.t, "s": round(f.t / fps, 2),
                    "defending": vedo.value,
                    "label": detect_formation(f, vedo, config).label,
                    "goal_x": config.own_goal_x(vedo)})
    return out


# A 3D védekezés-paneljének "feltörés" sora: csapatonként ennyi tételt
# viszünk a felderítés rangsorából.
DEFENCE_BREAKPOINTS_TOP = 3


def defence_breakpoints_by_team(match: Match, top: int = DEFENCE_BREAKPOINTS_TOP) -> dict:
    """Hol törhető fel a két csapat védekezése — a felderítés rangsorolt
    kivonatának (scouting.defence_breakpoints) teteje csapatonként, hogy
    a 3D védekezés-panel a fal mellé írhassa: "Feltörés: a bal szél
    sávban — lendületből betörés…". Edzőileg: a tankönyvi fal és a
    valódi fal eltérése mellett az is látszik, HOL és MIVEL kell
    támadni. Visszatérés: {"home": [{"hol","mivel","miert","pont"}],
    "away": [...]} — csapatonként üres lista, ha nincs elég minta vagy a
    felderítés hibázik (egy csapat hibája nem viszi el a másikat)."""
    return tactical_keys_by_team(match, top)["breakpoints"]


def tactical_keys_by_team(match: Match, top: int = DEFENCE_BREAKPOINTS_TOP,
                          reports: Optional[dict] = None) -> dict:
    """A 3D védekezés-panel két sora EGY felderítésből csapatonként:
    "breakpoints" — hol törhető fel a csapat VÉDEKEZÉSE
    (scouting.defence_breakpoints), és "stoppers" — hogyan állítható
    meg a csapat TÁMADÁSA (scouting.attack_stoppers), mindkettő a
    rangsor teteje. Egy szervezett támadásban a panel a védekező csapat
    "breakpoints"-ját (mivel törjük fel) és a támadó csapat
    "stoppers"-ét (mivel állítjuk meg) írja. Visszatérés:
    {"breakpoints": {"home": [...], "away": [...]}, "stoppers": {...}}
    — csapatonként üres lista, ha nincs elég minta vagy a felderítés
    hibázik (egy csapat hibája nem viszi el a másikat).

    `reports`: a két csapat KÉSZ felderítése ({"home": ..., "away": ...}),
    ha a hívónak már megvan (az API lemezes felderítés-tára) — a teljes
    felderítés egy hosszú meccsen perceket vesz igénybe, a 3D oldal első
    megnyitása ezen állt."""
    from .scouting import attack_stoppers, defence_breakpoints, scout_team
    ki = {"breakpoints": {}, "stoppers": {}}
    for side, team in (("home", Team.HOME), ("away", Team.AWAY)):
        try:
            rep = ((reports or {}).get(side)
                   or scout_team(match, team))
        except Exception:
            ki["breakpoints"][side] = []
            ki["stoppers"][side] = []
            continue
        for kulcs, fn in (("breakpoints", defence_breakpoints),
                          ("stoppers", attack_stoppers)):
            try:
                ki[kulcs][side] = fn(rep)[:top]
            except Exception:
                ki[kulcs][side] = []
    return ki


# A feltörés-sáv hossza a kaputól (a 9 m-es vonalig: a fal és a lövő
# tere) és a sáv-harmadok — ugyanaz a felosztás, mint a fal-rés térképé
# (defense.DGAP_ZONES, a VÉDŐ nézőpontjából).
BREAK_BAND_DEPTH_M = FREE_THROW_LINE_M


def breakpoint_zone_band(sav: str | None, goal_x: float) -> dict | None:
    """A feltörés sávjának padló-téglalapja a `goal_x` kaput védő fal
    előtt, pálya-méterben: {"x0","x1","y0","y1"} — None, ha nincs sáv.

    A sáv a VÉDŐ nézőpontjából ("bal szél" / "közép" / "jobb szél"): a
    0-s kapuját védő a +x felé néz, neki a nagyobb y a bal keze; a másik
    kapunál fordítva (a defense.defensive_gaps szabálya). A 3D pálya ezt
    festi piros sávként a padlóra: "ide kell betörni"."""
    if sav not in ("bal szél", "közép", "jobb szél"):
        return None
    harmad = COURT_WIDTH_M / 3.0
    bal_kapu = goal_x < COURT_LENGTH_M / 2
    if sav == "közép":
        y0, y1 = harmad, 2 * harmad
    elif (sav == "bal szél") == bal_kapu:
        y0, y1 = 2 * harmad, COURT_WIDTH_M   # a nagyobb y
    else:
        y0, y1 = 0.0, harmad
    x0 = 0.0 if bal_kapu else COURT_LENGTH_M - BREAK_BAND_DEPTH_M
    x1 = BREAK_BAND_DEPTH_M if bal_kapu else COURT_LENGTH_M
    return {"x0": x0, "x1": x1, "y0": round(y0, 3), "y1": round(y1, 3)}


# ---- Passzsávok: a labdás játékos opciói a 3D pályán ---------------------
#
# A 3D nézet a pillanatnyi labdástól minden csapattársához vonalat húz, a
# döntés-elemzés passz-modelljével (decisions.pass_completion: a távolság
# és a sávban — 1,5 m-en belül — álló ellenfelek) színezve. Ugyanaz a
# modell, mint a döntés-elemzésé: a 3D nem mondhat mást a passzról, mint
# az elemzés.
# A sáv szélessége: a decisions.pass_completion alapértéke (1,5 m).
PASS_LANE_WIDTH_M = 1.5
PASS_LANE_GOOD = 0.6     # e fölött nyitott (zöld) a sáv
PASS_LANE_RISKY = 0.35   # e fölött kockázatos (sárga), alatta zárt (piros)


def pass_lane_grade(p: float) -> str:
    """A passz-esély fokozata: "nyitott" / "kockázatos" / "zárt"."""
    if p >= PASS_LANE_GOOD:
        return "nyitott"
    if p >= PASS_LANE_RISKY:
        return "kockázatos"
    return "zárt"


def pass_lanes(players, ball, possession_radius_m: Optional[float] = None) -> Optional[dict]:
    """A labdás játékos passzsávjai egy pillanatban.

    `players`: [(hazai?, x, y), …] pálya-méterben; `ball`: (x, y) vagy
    None. A labdás a labdához legközelebbi játékos, ha a döntés-elemzés
    birtoklás-sugarán (TacticsConfig.possession_radius_m) belül van —
    különben nincs labdás, és nincs sáv (None).

    Visszatérés: {"holder": [x, y, hazai?], "lanes": [{"x", "y", "p",
    "blockers", "grade"}]} — csapattársanként a passz-esély (p, 0..1,
    decisions.pass_completion), a sávban álló ellenfelek száma
    (PASS_LANE_WIDTH_M-en belül) és a fokozat (pass_lane_grade)."""
    from types import SimpleNamespace

    from .decisions import _point_segment_distance, pass_completion

    if ball is None or not players:
        return None
    radius = (possession_radius_m if possession_radius_m is not None
              else TacticsConfig().possession_radius_m)
    bx, by = ball
    pl = [SimpleNamespace(team=bool(h), x=float(x), y=float(y))
          for h, x, y in players]
    holder = min(pl, key=lambda p: math.hypot(p.x - bx, p.y - by))
    if math.hypot(holder.x - bx, holder.y - by) > radius:
        return None
    frame = SimpleNamespace(players=pl)
    lanes = []
    for t in pl:
        if t is holder or t.team != holder.team:
            continue
        p = pass_completion(holder, t, frame, lane_width_m=PASS_LANE_WIDTH_M)
        blockers = sum(1 for o in pl if o.team != holder.team and
                       _point_segment_distance(o.x, o.y, holder.x, holder.y,
                                               t.x, t.y) <= PASS_LANE_WIDTH_M)
        lanes.append({"x": t.x, "y": t.y, "p": round(p, 4),
                      "blockers": blockers, "grade": pass_lane_grade(p)})
    return {"holder": [holder.x, holder.y, holder.team], "lanes": lanes}


# ---- Döntés-pillanatok: ahol jobb opció is volt -------------------------
#
# A döntés-elemzés (decisions.analyze_player_decisions) minden passz
# döntés-pillanatában kiértékeli az opciókat (lövés, passz minden
# társhoz: shot_value × pass_completion), és összeveti a legjobbat a
# választottal — de csak átlagot ad ("60%-ban optimális"). Itt a
# PILLANATOK: a 3D nézet odaugrik, és megmutatja a választott passzt és
# a jobb opciót. Ugyanaz a modell, mint az elemzésé.
DECISION_GAP_MIN = 0.10   # ennyi érték-különbség felett "jobb opció is volt"


@memoize_primitive("court3d.decision_moments", copy=copy_deep)
def decision_moments(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """A passz-döntések, ahol a modell szerint ÉRDEMBEN jobb opció is volt.

    Minden felismert passznál (decisions.detect_passes) a döntés-kockán
    az opciók (decisions.evaluate_options) közül a legjobbat
    (best_option) összevetjük a választottal; ha a különbség eléri a
    DECISION_GAP_MIN-t, a pillanat bekerül.

    Edzőileg: ezek a videózandó jelenetek — "itt a beálló szabad volt",
    "itt lövés kellett volna". Az átlagos optimalitás nem mutatja meg,
    HOL és MI volt a jobb választás; ez igen.

    Visszatérés: {"moments": [{"s", "t" (a döntés kockája), "team",
    "player_id" (a passzoló), "passer": [x, y],
    "chosen": [x, y], "chosen_value", "best_kind", "best": [x, y],
    "best_value", "gap", "situation", "sit_n", "sit_best"}] időrendben,
    "passes": {"home"/"away": db}, "flagged": {"home"/"away": db}} — a
    "best" passznál a jobb társ helye, lövésnél a támadott kapu közepe.
    A "situation" a döntés helyzete a játékos-modell besorolásában
    (decisions.decision_situation; None, ha egyik sem), a "sit_n" /
    "sit_best" a passzoló ÖSSZES döntése ebben a helyzetben a meccsen, és
    közülük a legjobb-opciósak (situational_decisions) — a felirat ebből
    mondja ki, ha a pillanat a játékos visszatérő szokása."""
    from .decisions import (best_option, decision_situation, detect_passes,
                            evaluate_options, situational_decisions)

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    moments: list[dict] = []
    passes = {"home": 0, "away": 0}
    flagged = {"home": 0, "away": 0}
    try:
        _sd = situational_decisions(match, config)
        sit_rows = {(side_, r_["player_id"]): r_["situations"]
                    for side_ in ("home", "away")
                    for r_ in _sd[side_]["players"]}
    except Exception:
        sit_rows = {}
    for pe in detect_passes(match, config):
        side = getattr(pe.team, "value", pe.team)
        if side not in passes:
            continue
        passes[side] += 1
        opts = evaluate_options(pe.decision_frame, pe.passer_pos, config)
        best = best_option(opts)
        chosen = next((o for o in opts if o.kind == "pass"
                       and o.target_id == pe.receiver_id), None)
        if best is None or chosen is None:
            continue
        gap = best.value - chosen.value
        if gap < DECISION_GAP_MIN:
            continue
        pos = {p.track_id: p for p in pe.decision_frame.players}
        rec = pos.get(pe.receiver_id)
        if rec is None:
            continue
        if best.kind == "pass":
            tgt = pos.get(best.target_id)
            if tgt is None:
                continue
            cel = [round(tgt.x, 1), round(tgt.y, 1)]
        else:
            # Lövés: a cél a TÁMADOTT kapu közepe (a vonal a kapura mutat).
            cel = [float(config.attacks_toward_x(pe.team)), COURT_WIDTH_M / 2.0]
        flagged[side] += 1
        sit = decision_situation(pe.decision_frame, pe.passer_pos, config)
        sit_rec = (sit_rows.get((side, pe.passer_id)) or {}).get(sit) or {}
        moments.append({
            "s": round(pe.decision_frame.t / fps, 2),
            "t": pe.decision_frame.t, "team": side,
            "player_id": pe.passer_id,
            "passer": [round(pe.passer_pos.x, 1), round(pe.passer_pos.y, 1)],
            "chosen": [round(rec.x, 1), round(rec.y, 1)],
            "chosen_value": round(chosen.value, 3),
            "best_kind": best.kind,
            "best": cel,
            "best_value": round(best.value, 3),
            "gap": round(gap, 3),
            "situation": sit,
            "sit_n": int(sit_rec.get("decisions", 0)),
            "sit_best": int(sit_rec.get("match", 0)),
        })
    moments.sort(key=lambda m_: m_["s"])
    return {"moments": moments, "passes": passes, "flagged": flagged}



# ---- Szabad lövők: a fedezés-hibák pillanatai ----------------------------
#
# A védekezés-elemzés (defense.defense_analysis) minden kapott lövésnél
# megméri a legközelebbi mezőnyvédő távolságát, és SZABADNAK mondja, ha az
# FREE_DEF_RADIUS_M (2 m) fölött van — de csak arányt ad ("a lövők 84%-át
# szabadon hagyják"). Itt a PILLANATOK: a 3D odaugrik, és megmutatja a
# lövőt, a 2 m-es fedezés-kört és a legközelebbi védőt.


@memoize_primitive("court3d.free_shot_moments", copy=copy_deep)
def free_shot_moments(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """A szabadon hagyott lövők pillanatai (a VÉDEKEZŐ csapat szerint).

    Forrás: a defense_analysis lövés-sorai (ugyanaz a "szabad" ítélet és
    távolság, ugyanazon az elengedési kockán) — a 3D nem mondhat mást,
    mint a védekezés-elemzés.

    Visszatérés: {"moments": [{"s", "defending", "shooter": [x, y],
    "defender": [x, y] | None, "dist", "goal", "xg", "zone"}] időrendben,
    "shots_against": {"home"/"away": db}, "free_shots": {...: db},
    "radius_m": FREE_DEF_RADIUS_M}."""
    from .defense import FREE_DEF_RADIUS_M, defense_analysis

    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    d = defense_analysis(match, config)
    moments = []
    for side in ("home", "away"):
        for sh in d[side]["shots"]:
            if sh.get("free") is not True:
                continue
            moments.append({
                "s": round(sh["release_t"] / fps, 2), "defending": side,
                "shooter": [sh["x"], sh["y"]], "defender": sh["defender"],
                "dist": sh["def_dist"], "goal": bool(sh["goal"]),
                "xg": round(float(sh["xg"]), 3), "zone": sh["zone"]})
    moments.sort(key=lambda m_: (m_["s"], m_["defending"]))
    return {"moments": moments,
            "shots_against": {k: d[k]["shots_against"] for k in ("home", "away")},
            "free_shots": {k: d[k]["free_shots"] for k in ("home", "away")},
            "radius_m": FREE_DEF_RADIUS_M}


def _third(ball_x: float, goal_x: float) -> str:
    """A pálya-harmad a TÁMADÁSI irány szerint — a defense.turnover_zones
    képlete (0 = saját kapu környéke, 1 = a megtámadott kapu)."""
    frac = 1.0 - abs(ball_x - goal_x) / COURT_LENGTH_M
    return "saját" if frac < 1 / 3 else ("közép" if frac < 2 / 3 else "támadó")


@memoize_primitive("court3d.turnover_moments", copy=copy_deep)
def turnover_moments(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """A labdavesztések pillanatai (a labdát ELVESZTŐ csapat szerint).

    A labdaeladás-rétegek eddig számokat mondtak (KI veszít — turnover_
    players, HOL — turnover_zones, kipréselik-e — pressured_turnovers,
    mennyibe kerül — turnover_punishment); a 3D pálya a jeleneteket is
    megmutatja, és mind a négy választ EGY pillanatra teszi: a vesztő
    mezszáma, a pálya-harmad, a legközelebbi ellenfél távolsága (a
    nyomás-sugáron belül KIPRÉSELT, azon túl MAGÁTÓL jött) és hogy a
    labda fél percen belül gólba került-e. Ugyanazokból az eseményekből
    és ugyanazokkal a küszöbökkel, mint a négy réteg — a 3D nem mondhat
    mást, mint az elemzés.

    Visszatérés: {"moments": [{"s", "t" (videó-kocka), "team",
    "player_id" (a vesztő), "jersey", "loser": [x, y] |
    None, "ball": [x, y] | None, "zone" | None, "opponent": [x, y] |
    None, "dist" | None, "forced": bool | None, "punished",
    "goal_after_s" | None}] időrendben, "turnovers", "forced",
    "unforced", "punished" (csapatonként: db), "pressure_m", "quick_s"}.
    A "forced" None, ha nem mérhető (a vesztő a kapus, nem látszik, vagy
    nincs látott mezőnybeli ellenfél) — mint a pressured_turnovers-nél."""
    from .defense import PTO_PRESSURE_M, TO_PUNISH_QUICK_S
    from .event_detection import EventType, detect_events, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    win = round(TO_PUNISH_QUICK_S * fps)
    gk_tracks: set = set()
    jersey: dict = {}
    for f in match.frames:
        for p in f.players:
            if p.role == "kapus":
                gk_tracks.add(p.track_id)
            if p.jersey_number is not None and p.track_id not in jersey:
                jersey[p.track_id] = p.jersey_number
    events = [e for e in detect_events(match, config)
              if e.type == EventType.TURNOVER]
    want = {e.t for e in events}
    frames_at = {f.t: f for f in match.frames if f.t in want}
    goals = sorted((e.t, e.team.value) for e in detect_shots(match, config)
                   if e.type == EventType.GOAL)

    moments = []
    counts = {side: {"turnovers": 0, "forced": 0, "unforced": 0,
                     "punished": 0} for side in ("home", "away")}
    for e in events:
        side = e.team.value
        other = "away" if side == "home" else "home"
        f = frames_at.get(e.t)
        loser = None
        if f is not None and e.player_id is not None:
            loser = next((p for p in f.players if p.track_id == e.player_id),
                         None)
        ball = f.ball if f is not None else None
        zone = (_third(ball.x, config.attacks_toward_x(e.team))
                if ball is not None else None)
        opp_xy, dist, forced = None, None, None
        if loser is not None and e.player_id not in gk_tracks:
            # A legközelebbi mezőnybeli ellenfél (a kapusuk nem nyomás).
            best = None
            for p in f.players:
                if p.team == loser.team or p.track_id in gk_tracks:
                    continue
                d = math.hypot(p.x - loser.x, p.y - loser.y)
                if best is None or d < best[0]:
                    best = (d, p)
            if best is not None:
                dist = round(best[0], 2)
                opp_xy = [round(best[1].x, 2), round(best[1].y, 2)]
                forced = best[0] <= PTO_PRESSURE_M
        goal_t = next((gt for (gt, gs) in goals
                       if gs == other and 0 <= gt - e.t <= win), None)
        rec = counts[side]
        rec["turnovers"] += 1
        if forced is True:
            rec["forced"] += 1
        elif forced is False:
            rec["unforced"] += 1
        if goal_t is not None:
            rec["punished"] += 1
        moments.append({
            "s": round(e.t / fps, 2), "t": e.t, "team": side,
            "player_id": e.player_id, "jersey": jersey.get(e.player_id),
            "loser": ([round(loser.x, 2), round(loser.y, 2)]
                      if loser is not None else None),
            "ball": ([round(ball.x, 2), round(ball.y, 2)]
                     if ball is not None else None),
            "zone": zone, "opponent": opp_xy, "dist": dist,
            "forced": forced, "punished": goal_t is not None,
            "goal_after_s": (round((goal_t - e.t) / fps, 1)
                             if goal_t is not None else None)})
    moments.sort(key=lambda m_: (m_["s"], m_["team"]))
    return {"moments": moments,
            **{k: {side: counts[side][k] for side in ("home", "away")}
               for k in ("turnovers", "forced", "unforced", "punished")},
            "pressure_m": PTO_PRESSURE_M, "quick_s": TO_PUNISH_QUICK_S}


def wall_gap_segments(players, team: Team, goal_x: float) -> Optional[dict]:
    """A védőfal rései EGY kockán — a 3D pálya "Fal-rések" rétege.

    A wall_gaps réteg arányt mond ("a kockák 40%-ában 3,5 m-nél nagyobb
    rés tátong a falban"); ez a pillanatot mutatja: a fal védői y szerint
    sorban (defense.wall_line — UGYANAZ a kiválogatás: mért, kapus
    nélküli védők a saját kaputól WALL_GAP_DEPTH_M-en belül), a
    szomszédok közti rés (az y-irányú távolság, mint a rétegben), és hogy
    melyik rés éri el a WALL_GAP_M-et — ott nyílik a fal: oda kell
    betörni, a beálló oda úszik be.

    Visszatérés: None, ha a fal nem áll (WALL_GAP_MIN_DEFENDERS alatti
    védő); különben {"wall": [[x, y], …] y szerint, "gaps": [m, …] (a
    szomszéd-párok rései), "wide": [bool, …] (a rés ≥ WALL_GAP_M),
    "max_gap", "max_index" (a legnagyobb rés — holtversenyben az első)}.
    """
    from .defense import WALL_GAP_M, WALL_GAP_MIN_DEFENDERS, wall_line

    fal = wall_line(players, team, goal_x)
    if len(fal) < WALL_GAP_MIN_DEFENDERS:
        return None
    nyers = [b[0] - a[0] for a, b in zip(fal, fal[1:])]
    i = max(range(len(nyers)), key=lambda k: (nyers[k], -k))
    return {"wall": [[round(x, 2), round(y, 2)] for y, x in fal],
            "gaps": [round(g, 2) for g in nyers],
            "wide": [g >= WALL_GAP_M for g in nyers],
            "max_gap": round(nyers[i], 2), "max_index": i}


def _szam1_js(v: float) -> str:
    """Egy tizedes, vesszővel — a JS toFixed(1) (és a Dart
    toStringAsFixed(1)) kerekítésével: a pontos bináris érték felé
    legközelebbi, döntetlennél a NAGYOBB (0,25 → "0,3"; a Python
    formázása itt párosra kerekítene: "0,2")."""
    from decimal import ROUND_HALF_UP, Decimal

    d = Decimal(float(v)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{d:.1f}".replace(".", ",")


# A jelenet-lista "ugyanaz a pillanat" tűrése (másodperc): a kapott gól
# sora elmarad, ha ennyin belül szabad lövő GÓL-sor van — a két sor
# ugyanarról az elengedési kockáról jön, a tűrés a kerekítést fedi. A
# böngésző (JL_AZONOS_S) és az app (sceneSameMomentS) ugyanezt viszi.
SCENE_SAME_MOMENT_S = 0.05

# A jelenet-vetítés (a 3D jelenet-lista sorai egymás után): a jelenet a
# pillanata után ennyi másodpercig fut, mielőtt a lista következő sora jön
# (előtte 1,5 mp-cel indul, mint minden jelenet-ugrás) — egy jelenet így
# 5 mp, a 15 videózandó jelenet bő egy perc. A böngésző (JL_VETITES_S, a
# sablonba írva) és az app (sceneReelTailS, őr-teszt) ugyanezt viszi.
SCENE_REEL_TAIL_S = 3.5

# KÖZÖS NÉZÉS (az edző vezet, a csapat headsetjei követik — a böngészős 3D
# sablonjába írva): a vezető ennyi másodpercenként küldi a lejátszás
# állapotát, a követő ennyi másodpercenként kérdez; ennél nagyobb
# idő-eltérésnél a követő ugrik (a kisebbet a saját lejátszása tartja —
# nincs rángatás); ennyi csend után a vezetés megszakadtnak számít (az
# edző bezárta az oldalt, elment a hálózat).
SHARED3D_SEND_S = 0.3
SHARED3D_POLL_S = 0.3
SHARED3D_TOLERANCE_S = 0.4
SHARED3D_STALE_S = 15.0
# A követő az utolsó kérdése után ennyi ideig számít jelenlévőnek (a
# vezető ennyi másodpercen belül látott követőket látja — a kérdezés
# SHARED3D_POLL_S-enként jön, egy-két elveszett kérés nem ejti ki).
SHARED3D_FOLLOWER_S = 3.0
# A vezető mutatója (Shift+kattintás a padlóra) ennyi másodpercig lüktet a
# követőknél — a régebbi mutató a később csatlakozónál már nem villan fel.
SHARED3D_POINTER_S = 4.0
# A közös nézés JELENLÉTE: a követő a kérdéssel, a vezető a küldéssel a
# kamerája helyét és irányát is adja — mindenki látja a többieket a
# csarnokban. A hely a csarnok ésszerű dobozába szorítva (three-tér: x a
# pálya hossza, y a magasság, z a szélesség tükörképe — az "Ide mindenki"
# nézőpontja is ide szorul), a követő neve (a csapat linkjén: /kovet?nev=…)
# legfeljebb ennyi jel.
SHARED3D_HALL_BOX = ((-60.0, 100.0), (0.2, 60.0), (-60.0, 80.0))
SHARED3D_NAME_MAX = 16
# A saját kamerához ennél közelebbi társ nem látszik ("Ide mindenki" után
# mindenki egy helyen áll — nem a fejünkben ül). A böngésző (KZ_KOZEL, a
# sablonba írva) és az app (presenceNearM, őr-teszt) ugyanezt viszi.
SHARED3D_NEAR_M = 1.2


def shared3d_hely(ertek):
    """A jelenlét helye: [x, y, z, yaw] (three-tér, a csarnok dobozába
    szorítva, cm-re kerekítve; a yaw — a nézés iránya (−sin yaw, −cos yaw)
    — a (−π, π] tartományba hozva, ezred radiánra) egy "x,y,z,yaw"
    szövegből vagy négyelemű listából. None, ha rossz alakú (nem négy
    elem, nem szám, nem véges)."""
    import math
    if isinstance(ertek, str):
        ertek = ertek.split(",")
    if not isinstance(ertek, (list, tuple)) or len(ertek) != 4:
        return None
    try:
        v = [float(e) for e in ertek]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(e) for e in v):
        return None
    hely = [round(min(f, max(a, e)), 2)
            for e, (a, f) in zip(v[:3], SHARED3D_HALL_BOX)]
    return hely + [round(math.atan2(math.sin(v[3]), math.cos(v[3])), 3)]


# FELVÉTEL: a megbeszélés felvétele legfeljebb ennyi állapot (a vezető
# SHARED3D_SEND_S-enként rögzít: ~1,7 óra), a neve legfeljebb ennyi jel.
SHARED3D_REC_MAX = 20000
SHARED3D_REC_NAME_MAX = 80
# A felvétel egy állapotában legfeljebb ennyi kvíz-válasz (a csapat).
SHARED3D_REC_QUIZ_MAX = 60
# 🎙 A felvétel hangja (a vezető mikrofonja): legfeljebb ennyi bájt (a
# böngésző 32 kbit/s-os Opus-ával ~4,5 óra — a SHARED3D_REC_MAX ~1,7
# órája bőven belefér), és csak a böngészők MediaRecorder-ének típusai.
SHARED3D_REC_AUDIO_MAX = 64 * 1024 * 1024
SHARED3D_REC_AUDIO_TYPES = ("audio/webm", "audio/mp4", "audio/ogg")
# A /kovet "Várunk az edzőre" lapja a legutóbbi ennyi felvételt kínálja
# visszanézésre (meccsektől függetlenül, a legújabb elöl).
SHARED3D_WAIT_RECS = 8
# "Ki nézte meg?": a néző akkor számít megnézőnek, ha a felvétel ennyi
# részét TÉNYLEGESEN végignézte (lejátszás közben eltelt idő — a szünet
# és az átugrott fejezetek nem számítanak).
SHARED3D_REC_WATCHED_FRAC = 0.8


# A felvétel FEJEZETEI: ahol a játékidő a vártnál ennél többet ugrott (az
# edző egy másik jelenetre ugrott), új fejezet kezdődik; az előző fejezet
# kezdete után ennél hamarabb jövő ugrás (a csúszka húzása) nem új
# fejezet, hanem az előző landolása.
SHARED3D_REC_CHAPTER_JUMP_S = 5.0
SHARED3D_REC_CHAPTER_MIN_S = 3.0


def shared3d_felvetel_fejezetek(allapotok) -> list:
    """A felvétel fejezetei: [[eltelt-mp, játékidő-mp], …]. Az első állapot
    mindig fejezet-kezdet; utána ott kezdődik új, ahol a játékidő a
    várthoz (az előző idő, lejátszásnál + az eltelt idő × az előző
    sebesség) képest több mint SHARED3D_REC_CHAPTER_JUMP_S-t ugrott. Az
    előző fejezet kezdete után SHARED3D_REC_CHAPTER_MIN_S-on belüli ugrás
    (a csúszka húzása — sok gyors ugrás) az előző fejezetet a landolásra
    viszi, nem nyit újat (az első fejezet, a felvétel eleje, marad).
    `allapotok`: a mentett alak ([[eltelt, {"t", "playing", "speed",
    …}], …], időrendben)."""
    ki = []
    elozo = None
    for eltelt, a in allapotok:
        eltelt = float(eltelt)
        t = float(a.get("t", 0.0))
        if elozo is None:
            ki.append([eltelt, t])
        else:
            e0, a0 = elozo
            vart = float(a0.get("t", 0.0))
            if a0.get("playing"):
                vart += (eltelt - e0) * float(a0.get("speed", 1.0))
            if abs(t - vart) > SHARED3D_REC_CHAPTER_JUMP_S:
                if len(ki) > 1 and eltelt - ki[-1][0] < SHARED3D_REC_CHAPTER_MIN_S:
                    ki[-1] = [eltelt, t]
                else:
                    ki.append([eltelt, t])
        elozo = (eltelt, a)
    return ki


# A felvétel jelenlét-listája (kik követték élőben) legfeljebb ennyi név.
SHARED3D_REC_PRESENT_MAX = 100


def shared3d_felvetel_jelen(lista) -> list:
    """A felvétel jelenlét-listája megtisztítva: a nevek shared3d_nev
    szerint, ismétlés nélkül (a kulcs quiz_name_key — kis- és nagybetű,
    szóköz nem számít; az első alak marad), legfeljebb
    SHARED3D_REC_PRESENT_MAX. Nem lista: üres."""
    if not isinstance(lista, list):
        return []
    ki, latott = [], set()
    for x in lista:
        nev = shared3d_nev(x) if isinstance(x, str) else ""
        kulcs = quiz_name_key(nev)
        if nev and kulcs not in latott:
            latott.add(kulcs)
            ki.append(nev)
            if len(ki) >= SHARED3D_REC_PRESENT_MAX:
                break
    return ki


def shared3d_felvetel_nev(x) -> str:
    """A felvétel neve megtisztítva: csak kiírható jelek, a szélein szóköz
    nélkül, legfeljebb SHARED3D_REC_NAME_MAX jel ("" — a hívó tesz
    alapnevet)."""
    return "".join(ch for ch in str(x or "")
                   if ch.isprintable()).strip()[:SHARED3D_REC_NAME_MAX]


def shared3d_felvetel_allapot(d):
    """A felvétel egy állapota megtisztítva: {"t" (játékidő-mp), "playing",
    "speed" (0,25…8), "rajz" (a rajz-kód; rossz alaknál üres), "mutato"
    ({x, y, n} — a pálya ±5 m-es sávjába szorítva), "nezopont" ({x, y, z,
    yaw, pitch, n} — a csarnok dobozába szorítva), "kviz" ({n, mutat,
    d?} — a vezető köre), "valaszok" ([{nev, x, y}] — a csapat válaszai,
    a pálya ±5 m-es sávjában, legfeljebb SHARED3D_REC_QUIZ_MAX)}; None, ha
    az idő vagy a sebesség rossz. A rossz mutató, nézőpont, kvíz és
    válasz egyszerűen kimarad."""
    import math
    import re
    if not isinstance(d, dict):
        return None
    try:
        t = float(d.get("t") or 0.0)
        speed = float(d.get("speed") or 1.0)
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(t) and math.isfinite(speed)
            and 0.25 <= speed <= 8.0):
        return None
    rajz = str(d.get("rajz") or "").strip()
    if rajz and (len(rajz) > 1200 or not re.fullmatch(r"[0-9.,;\-]+", rajz)):
        rajz = ""
    ki = {"t": round(max(0.0, t), 2), "playing": bool(d.get("playing")),
          "speed": speed, "rajz": rajz}

    def _szamok(o, kulcsok):
        try:
            v = [float(o[k]) for k in kulcsok]
        except (TypeError, ValueError, KeyError):
            return None
        return v if all(math.isfinite(x) for x in v) else None

    m = _szamok(d.get("mutato"), ("x", "y", "n"))
    if m:
        ki["mutato"] = {"x": round(min(45.0, max(-5.0, m[0])), 2),
                        "y": round(min(25.0, max(-5.0, m[1])), 2), "n": m[2]}
    v = _szamok(d.get("nezopont"), ("x", "y", "z", "yaw", "pitch", "n"))
    if v:
        (xa, xf), (ya, yf), (za, zf) = SHARED3D_HALL_BOX
        ki["nezopont"] = {"x": round(min(xf, max(xa, v[0])), 2),
                          "y": round(min(yf, max(ya, v[1])), 2),
                          "z": round(min(zf, max(za, v[2])), 2),
                          "yaw": round(v[3], 4),
                          "pitch": round(min(1.6, max(-1.6, v[4])), 4),
                          "n": v[5]}
    kv = d.get("kviz")
    k = _szamok(kv, ("n",))
    if k:
        ki["kviz"] = {"n": k[0], "mutat": bool(kv.get("mutat"))}
        dd = _szamok(kv, ("d",)) if kv.get("d") is not None else None
        if dd:
            ki["kviz"]["d"] = round(dd[0], 2)
        valaszok = []
        nyers = d.get("valaszok")
        for e in (nyers[:SHARED3D_REC_QUIZ_MAX] if isinstance(nyers, list) else []):
            xy = _szamok(e, ("x", "y"))
            if xy:
                valaszok.append({"nev": shared3d_nev(e.get("nev")),
                                 "x": round(min(45.0, max(-5.0, xy[0])), 2),
                                 "y": round(min(25.0, max(-5.0, xy[1])), 2)})
        if valaszok:
            ki["valaszok"] = valaszok
    return ki


def shared3d_valasz(s):
    """A közös nézés KVÍZ-válasza: [x, y, n] — a padló pontja pálya-
    méterben (a pálya ±5 m-es sávjába szorítva, cm-re kerekítve) és a
    kvíz-kör azonosítója — egy "x,y,n" szövegből. None, ha rossz alakú
    (nem három elem, nem szám, nem véges)."""
    import math
    elemek = str(s or "").split(",")
    if len(elemek) != 3:
        return None
    try:
        x, y, n = (float(e) for e in elemek)
    except ValueError:
        return None
    if not all(math.isfinite(v) for v in (x, y, n)):
        return None
    return [round(min(45.0, max(-5.0, x)), 2),
            round(min(25.0, max(-5.0, y)), 2), n]


# DÖNTÉS-KVÍZ: a kvíz döntés-pillanatnál (decision_moments) a válaszokat a
# modell jobb opciójához méri — a jobb cél (passznál a jobb társ helye)
# ennyi méteren belül; lövésnél a cél a kapu közepe, a "találat" a
# kapuelőtér (6 m) — a játékos a kapu elé mutat, nem a kapufák közé. A
# böngésző (KVIZ_JS, a sablonba írva) és az app (quizVerdict, őr-teszt)
# ugyanezt viszi.
SHARED3D_QUIZ_HIT_M = 3.0
SHARED3D_QUIZ_SHOT_M = 6.0


def quiz_verdict(answer, best, chosen, shot: bool = False) -> bool:
    """A kvíz-válasz ítélete egy döntés-pillanatnál: a válasz (a padló
    pontja, pálya-méter) a modell JOBB opcióját mutatja-e — közelebb van a
    jobb célhoz (`best`), mint a választott passz céljához (`chosen`), és
    a jobb céltól legfeljebb SHARED3D_QUIZ_HIT_M-re (lövésnél — `shot` —
    a kapu közepétől SHARED3D_QUIZ_SHOT_M-re). Edzőileg: "látta-e a
    játékos, amit a jobb döntés kívánt"."""
    import math
    db = math.hypot(answer[0] - best[0], answer[1] - best[1])
    dc = math.hypot(answer[0] - chosen[0], answer[1] - chosen[1])
    return db < dc and db <= (SHARED3D_QUIZ_SHOT_M if shot
                              else SHARED3D_QUIZ_HIT_M)


# KVÍZ-MÉRLEG: a döntés-kvízek ítéletei játékosonként, meccseken át (a
# kvíz-jegyzetek "kviz" sorai) — ennyi ítélt válasz alatt az arány nem
# mond semmit (None, nem 0).
QUIZ_STATS_MIN_ANSWERS = 3


def quiz_name_key(nev) -> str:
    """A kvíz-név kulcsa (a kvíz-mérleg és a keret ugyanígy párosít): a
    szóközök összevonva, két szélén nélkülük, kisbetűsen."""
    import re
    return re.sub(r"\s+", " ", str(nev or "")).strip().casefold()


def quiz_stats(notes) -> list:
    """A kvíz-mérleg: a kvíz-jegyzetek (a 3D közös nézés kvízének
    eredménye — a jegyzet "kviz" sorai: [{"nev", "itelet": true/false/
    null}]) játékosonként összegezve, meccseken át. A kulcs a név
    (kisbetűsen, a szóközök összevonva — a headseten begépelt "peti " és
    "Peti" ugyanaz); a név nélküli és a "#3"-féle sorszámos válaszoló
    kimarad: meccsről meccsre nem azonosítható.

    Edzőileg: ki olvassa jól a játékot — a döntés-kvízekben (a mérce a
    modell jobb opciója) hányszor mutatott a jobb megoldásra.

    `notes`: a jegyzetek időrendben (a megjelenített név a legutóbbi
    írásmód). Visszatérés: [{"nev", "kvizek" (hány kvízben válaszolt),
    "itelt" (döntés-kvíz válaszok), "jo", "rossz", "arany" (jo / itelt;
    None, ha itelt < QUIZ_STATS_MIN_ANSWERS)}] — az arány szerint
    csökkenően (a kevés mintás a végén), azon belül az ítélt válaszok
    száma, majd a név szerint."""
    import re
    tabla: dict = {}
    for n in notes:
        sorok = n.get("kviz") if isinstance(n, dict) else None
        if not isinstance(sorok, list):
            continue
        latott = set()
        for e in sorok:
            if not isinstance(e, dict):
                continue
            nev = re.sub(r"\s+", " ", str(e.get("nev") or "")).strip()
            if not nev or re.fullmatch(r"#\d+", nev):
                continue
            kulcs = quiz_name_key(nev)
            r = tabla.setdefault(kulcs, {"nev": nev, "kvizek": 0, "itelt": 0,
                                         "jo": 0, "rossz": 0})
            r["nev"] = nev
            if kulcs not in latott:
                latott.add(kulcs)
                r["kvizek"] += 1
            it = e.get("itelet")
            if it is True or it is False:
                r["itelt"] += 1
                r["jo" if it else "rossz"] += 1
    ki = []
    for r in tabla.values():
        r["arany"] = (round(r["jo"] / r["itelt"], 3)
                      if r["itelt"] >= QUIZ_STATS_MIN_ANSWERS else None)
        ki.append(r)
    ki.sort(key=lambda r: (r["arany"] is None, -(r["arany"] or 0.0),
                           -r["itelt"], r["nev"].casefold()))
    return ki


def shared3d_nev(s) -> str:
    """A követő neve a többiek headsetjén: a látható jelek (vezérlőjel
    nélkül), két szélén szóköz nélkül, legfeljebb SHARED3D_NAME_MAX; üres,
    ha nincs."""
    s = "".join(ch for ch in str(s or "") if ch.isprintable()).strip()
    return s[:SHARED3D_NAME_MAX].strip()


def scene_anchor_t(match, row: dict) -> int:
    """A jelenet-lista sorának HORGONY-kockája (kocka-t). A kapott
    lerohanás ("k") sora az INDULÁS ideje, a horgonya a BEFEJEZÉS kockája
    (a gól) — a videózandó klip és a jelentés kockája ide néz; a többi sor
    a pillanata (s × fps). (A böngésző és az app vetítése ugyanezt a
    befejezést a saját lerohanás-adatából keresi.)"""
    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    if row.get("tipus") == "k":
        for k in fast_break_moments(match)["moments"]:
            if (abs(float(k["s"]) - float(row["s"])) < 0.01
                    and k.get("t") is not None):
                return int(k["t"])
    return int(round(float(row["s"]) * fps))


def shared3d_ora() -> float:
    """A közös nézés órája (monoton másodperc) — a motor ebből számolja a
    vezető állapotának, a követőknek, a mutatónak és a nézőpontnak a
    korát; a tesztek ezt cserélik (nem a process-szintű time.monotonic-ot,
    amit az eseményhurok is használ)."""
    import time

    return time.monotonic()

# A rajz-eszköz (nyilak a padlón) közös számai — a böngésző RAJZ_JS és az
# app court_geometry.dart tükre (őr-teszt): a színek (sárga labda/passz,
# kék futás, piros védő), legfeljebb ennyi nyíl, és ennél rövidebb húzás
# nem nyíl (méter).
DRAWING_COLORS = ("ffd23f", "4c9aff", "ff6b6b")
DRAWING_MAX = 30
DRAWING_MIN_M = 0.6
_RAJZ_SZAM = re.compile(r"-?[0-9]+(\.[0-9]+)?")
_RAJZ_EGESZ = re.compile(r"[0-9]+")


def decode_drawing(s) -> list:
    """A "rajz" szöveg (a 3D link-paraméter és a jegyzet-tár alakja:
    "x1,y1,x2,y2,szín;…") → nyilak [(x1, y1, x2, y2, színkód)], pálya-
    méterben. A böngésző rajzDekodol-jának és az app decodeDrawing-jának
    tükre: a hibás (üres vagy nem szám mezős), a pályán kívüli (−10…50 m-en
    túli), a túl rövid és az ismeretlen színű tag kimarad, legfeljebb
    DRAWING_MAX nyíl."""
    ki = []
    for tag in str(s or "").split(";"):
        p = [x.strip() for x in tag.split(",")]
        # Csak a kódoló számalakja (-12.3; szín: egész) — a böngésző és az
        # app tükre ugyanígy (a float() az "1e1"-et is elfogadná).
        if (len(p) != 5 or not all(_RAJZ_SZAM.fullmatch(x) for x in p[:4])
                or not _RAJZ_EGESZ.fullmatch(p[4])):
            continue
        v = [float(x) for x in p[:4]]
        k = int(p[4])
        if any(not math.isfinite(x) or x < -10 or x > 50 for x in v):
            continue
        if not 0 <= k < len(DRAWING_COLORS):
            continue
        if math.hypot(v[2] - v[0], v[3] - v[1]) < DRAWING_MIN_M:
            continue
        ki.append((v[0], v[1], v[2], v[3], k))
        if len(ki) >= DRAWING_MAX:
            break
    return ki


def arrow_head(x1: float, y1: float, x2: float, y2: float, hossz: float,
               szel: float) -> tuple:
    """A nyílhegy két szárnypontja: a csúcs (x2, y2), a szárak hossz-nyival
    vissza a nyíl tengelyén, onnan ±szel/2 oldalra — a böngésző
    nyilFej-ének és az app arrowHead-jének tükre."""
    d = math.hypot(x2 - x1, y2 - y1) or 1.0
    ux, uy = (x2 - x1) / d, (y2 - y1) / d
    bx, by = x2 - ux * hossz, y2 - uy * hossz
    return ((bx - uy * szel / 2, by + ux * szel / 2),
            (bx + uy * szel / 2, by - ux * szel / 2))


def note_diagram(match: Match, frame_t: int, rajz=None) -> Optional[dict]:
    """Egy jegyzet felülnézeti ábrájának adata: a jegyzet kockájához
    LEGKÖZELEBBI kocka játékosai (hely, csapat, mezszám) és a labda, plusz a
    jegyzettel mentett nyilak (decode_drawing). Edzőileg: a 3D pályán
    előkészített jelenet papíron is kiosztható — a játékos látja, hol
    állt, és a nyíl mutatja, hova kellett volna mennie. Kocka nélküli
    meccsen None.

    Visszaad: {"t", "players": [{"x", "y", "team", "jersey"}], "ball":
    (x, y) | None, "arrows": [(x1, y1, x2, y2, színkód)]}."""
    if not match.frames:
        return None
    import bisect
    idok = [f.t for f in match.frames]
    i = bisect.bisect_left(idok, int(frame_t))
    jeloltek = [j for j in (i - 1, i) if 0 <= j < len(idok)]
    f = match.frames[min(jeloltek, key=lambda j: abs(idok[j] - frame_t))]
    mez = _jersey_map(match)
    return {
        "t": f.t,
        "players": [{"x": p.x, "y": p.y,
                     "team": getattr(p.team, "value", p.team),
                     "jersey": p.jersey_number if p.jersey_number is not None
                     else mez.get(p.track_id)}
                    for p in f.players],
        "ball": (f.ball.x, f.ball.y) if f.ball is not None else None,
        "arrows": decode_drawing(rajz),
    }


def scene_rows(decisions: list, free_shots: list, turnovers: list,
               home: str, away: str,
               fast_breaks: Optional[list] = None,
               conceded_goals: Optional[list] = None) -> list[dict]:
    """A 3D jelenet-lista sorai — a böngésző (jelenetSorok) és az app
    (sceneRows) KANONIKUS forrása, a nyomtatható jelentés is ebből ír.

    Bemenet: a decision_moments / free_shot_moments / turnover_moments /
    fast_break_moments / conceded_goal_moments "moments" listái.
    Visszatérés: [{"s", "ido" ("p:mm"), "tipus" ("d" döntés, "sz" szabad
    lövés, "e" labdavesztés, "k" kapott lerohanás, "kg" kapott gól),
    "szoveg", "gol", "side" (a hibázó csapat: "home"/"away" — a jelentés
    3D-linkje szűr vele; a böngésző- és app-tükör nem viszi)}] időrendben;
    holtversenyben döntés, szabad lövés,
    labdavesztés, lerohanás, kapott gól. A lerohanás és a kapott gól sora
    a VÉDEKEZŐ csapaté ("kinek a hibája"). A kapott gól sora ELMARAD, ha
    ugyanarra a pillanatra szabad lövő GÓL-sor van (az már megnevezi) —
    a lapozóban minden kapott gól ott van, a listában egyszer."""
    def csapat(side):
        return home if side == "home" else away

    harmad = {"saját": "saját", "közép": "középső", "támadó": "támadó"}
    sorok = []
    for d in decisions:
        sorok.append({"s": d["s"], "tipus": "d", "gol": False,
                      "side": d["team"],
                      "szoveg": f"{csapat(d['team'])} — jobb opció is volt: "
                                + ("lövés" if d["best_kind"] == "shoot"
                                   else "passz egy szabadabb társhoz")})
    for d in free_shots:
        tav = d.get("dist")
        sorok.append({"s": d["s"], "tipus": "sz", "gol": bool(d["goal"]),
                      "side": d["defending"],
                      "szoveg": f"{csapat(d['defending'])} védekezése — "
                                "szabad lövő"
                                + (f" ({_szam1_js(tav)} m)" if tav is not None
                                   else "")
                                + (" · GÓL" if d["goal"] else "")})
    for d in turnovers:
        gol = d.get("goal_after_s") is not None
        h = harmad.get(d.get("zone"))
        sorok.append({"s": d["s"], "tipus": "e", "gol": gol,
                      "side": d["team"],
                      "szoveg": f"{csapat(d['team'])} — labdavesztés"
                                + (f" #{d['jersey']}" if d.get("jersey") is not None
                                   else "")
                                + (f" ({h} harmad)" if h else "")
                                + (" · gól lett belőle" if gol else "")})
    for d in fast_breaks or []:
        gol = d.get("outcome") == "goal"
        sorok.append({"s": d["s"], "tipus": "k", "gol": gol,
                      "side": d["defending"],
                      "szoveg": f"{csapat(d['defending'])} védekezése — "
                                f"kapott lerohanás: {csapat(d['team'])}"
                                + (f" #{d['shooter_jersey']}"
                                   if d.get("shooter_jersey") is not None
                                   else "")
                                + (" · GÓL" if gol
                                   else " · lövés" if d.get("outcome") == "shot"
                                   else " · lövés nélkül")})
    szabad_gol_idok = [d["s"] for d in free_shots if d["goal"]]
    for d in conceded_goals or []:
        if any(abs(d["s"] - s0) < SCENE_SAME_MOMENT_S for s0 in szabad_gol_idok):
            continue
        tav = d.get("def_dist")
        mely = d.get("keeper_depth")
        sorok.append({"s": d["s"], "tipus": "kg", "gol": True,
                      "side": d["defending"],
                      "szoveg": f"{csapat(d['defending'])} védekezése — "
                                f"kapott gól: {csapat(d['team'])}"
                                + (f" #{d['shooter_jersey']}"
                                   if d.get("shooter_jersey") is not None
                                   else "")
                                + f" ({d['zone']})"
                                + (f" · védő {_szam1_js(tav)} m" if tav is not None
                                   else "")
                                + ("" if mely is None
                                   else " · kapus kint" if d.get("keeper_out")
                                   else " · kapus a vonalon")})
    rend = {"d": 0, "sz": 1, "e": 2, "k": 3, "kg": 4}
    sorok.sort(key=lambda r: (r["s"], rend[r["tipus"]]))
    for r in sorok:
        t = max(0, math.floor(r["s"]))
        r["ido"] = f"{t // 60}:{t % 60:02d}"
    return sorok


def goal_build_ups(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """A gólok előkészítése: a gólt megelőző saját passz-lánc a pályán.

    A goal_buildup réteg ("direkt vagy kombinatív gólokból élnek")
    gólonként csak a passzok SZÁMÁT méri; a 3D pálya a láncot magát
    rajzolja ki — ki kinek adta, honnan lőtt a befejező. UGYANAZ a
    lánc-szabály: a gól előtti BUILDUP_WINDOW_S saját passzai, vissza az
    előző gólig vagy az ellenfél utolsó eseményéig (birtoklás-határ).

    Visszatérés: {"moments": [{"s" (az első passz, passz nélkül a gól
    ideje), "goal_s", "team", "passes": [{"from": [x, y], "to": [x, y],
    "from_jersey", "to_jersey"}], "shooter": [x, y] | None,
    "shooter_jersey", "goal": [x, y] (a támadott kapu közepe),
    "n_passes", "duration_s"}] a gólok időrendjében,
    "goals": {"home"/"away": db}}."""
    from .attack_types import BUILDUP_WINDOW_S
    from .event_detection import EventType, detect_events

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    win = round(BUILDUP_WINDOW_S * fps)
    events = sorted(detect_events(match, config), key=lambda e: e.t)
    by_t = {f.t: f for f in match.frames}
    jersey = _jersey_map(match)

    def hely(t, tid):
        f = by_t.get(t)
        if f is None or tid is None:
            return None
        p = next((q for q in f.players if q.track_id == tid), None)
        return [round(p.x, 2), round(p.y, 2)] if p is not None else None

    moments = []
    goals = {"home": 0, "away": 0}
    for gi, g in enumerate(events):
        if g.type != EventType.GOAL:
            continue
        side = g.team.value
        goals[side] += 1
        lanc = []
        for e in reversed(events[:gi]):
            if g.t - e.t > win:
                break
            # Birtoklás-határ: korábbi gól vagy az ellenfél eseménye
            # (a goal_buildup szabálya).
            if e.type == EventType.GOAL or e.team != g.team:
                break
            if e.type == EventType.PASS:
                lanc.append(e)
        lanc.reverse()
        passzok = []
        for e in lanc:
            rid = (e.detail or {}).get("receiver_id")
            passzok.append({"from": hely(e.t, e.player_id),
                            "to": hely(e.t, rid),
                            "from_jersey": jersey.get(e.player_id),
                            "to_jersey": jersey.get(rid)})
        t0 = lanc[0].t if lanc else g.t
        moments.append({
            "s": round(t0 / fps, 2), "goal_s": round(g.t / fps, 2),
            "team": side, "passes": passzok,
            "shooter": hely(g.t, g.player_id),
            "shooter_jersey": jersey.get(g.player_id),
            "goal": [float(config.attacks_toward_x(g.team)),
                     COURT_WIDTH_M / 2.0],
            "n_passes": len(lanc),
            "duration_s": round((g.t - t0) / fps, 1)})
    return {"moments": moments, "goals": goals}


def powerplay_moments(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """Az emberelőny-szakaszok a 3D pályán: ki van hátrányban, meddig, és
    mi történt közben.

    Forrás: a rules.detect_powerplay szakaszai (ugyanaz a kiállítás-
    felismerés), a lövések pedig a rules.powerplay_efficiency
    szabályával: kapura tartó lövés (gól vagy védés) a szakaszon belül;
    az előnyben lévő csapat lövései és góljai, és ha a HÁTRÁNYBAN lévő
    talál be, az is (ritka, de a meccset fordítja).

    Visszatérés: {"moments": [{"s", "e" (kezdet/vég mp), "team_down",
    "team_up", "duration_s", "shots_up", "goals_up", "goals_down",
    "goals": [[mp, csapat], …]}] időrendben, "windows": db}."""
    from .event_detection import detect_shots
    from .rules import detect_powerplay

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    windows = detect_powerplay(match)
    lovesek = []
    for e in detect_shots(match, config):
        outcome = (e.detail or {}).get("outcome")
        if outcome in ("goal", "save"):
            lovesek.append((e.t, e.team.value, outcome == "goal"))
    moments = []
    for w in windows:
        down = w["team_down"]
        up = "away" if down == "home" else "home"
        bent = [(t, tm, gol) for (t, tm, gol) in lovesek
                if w["start_frame"] <= t <= w["end_frame"]]
        moments.append({
            "s": round(w["start_frame"] / fps, 2),
            "e": round(w["end_frame"] / fps, 2),
            "team_down": down, "team_up": up,
            "duration_s": w["duration_s"],
            "shots_up": sum(1 for (_t, tm, _g) in bent if tm == up),
            "goals_up": sum(1 for (_t, tm, g) in bent if tm == up and g),
            "goals_down": sum(1 for (_t, tm, g) in bent if tm == down and g),
            "goals": [[round(t / fps, 2), tm] for (t, tm, g) in bent if g]})
    moments.sort(key=lambda m_: (m_["s"], m_["team_down"]))
    return {"moments": moments, "windows": len(moments)}


# Lerohanás-jelenetek: a befutó útját ekkora lépésközzel mintázzuk a
# pályára rajzoláshoz (másodperc — a ritkítás nem változtatja).
FB_PATH_STEP_S = 0.5


@memoize_primitive("court3d.fast_break_moments", copy=copy_deep)
def fast_break_moments(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """A lerohanások a 3D pályán: ki fut, honnan, és mi lett belőle.

    A kontra-rétegek számokban mondják (lerohanás-hatékonyság: mennyi
    lesz gól; kontra-hullámok: az első ember vagy a második hullám fejezi
    be; kontra-elszökés: előre szökött emberrel futnak-e) — a 3D a
    jelenetet mutatja: a befejező útját az indulástól a lövésig.
    UGYANAZOK a szabályok: a lerohanás a classify_attacks címkéje
    (FAST_BREAK_MAX_S, FAST_BREAK_ADV_MS); a gól és a lövő a szakaszban
    vagy ATTACK_TAIL_S-en belül utána (a lerohanás-hatékonyság gól-, a
    kontra-hullámok lövő-szabálya); az első ember az induláskor a kapuhoz
    legközelebbi mezőnyjátékos; az elszökés a labdánál FBH_GAP_M-rel
    előrébb váró ember.

    Visszatérés: {"moments": [{"s", "e" (a szakasz kezdete/vége mp),
    "shot_s" (a befejező lövés mp | None), "t" (a befejezés kockája: a
    gólé, ha gól lett, különben az első azonosított lövésé, lövés nélkül a
    szakasz végéé — a klipvágás e köré vág), "shooter_id" (a befejező:
    gólnál a gól azonosított lövője, különben az első azonosított lövés
    lövője | None — a mezszám, a lövés-hely, az út és a hullám is ebből;
    kipattanós gólnál ezért a hullám a kontra-hullámok rétegétől, amely az
    első lövőt nézi, eltérhet), "team" (a támadó), "defending",
    "duration_s", "advance_ms", "outcome" ("goal" / "shot" / None),
    "shooter_jersey", "first_jersey", "wave" ("first" / "second" / None —
    kettőnél kevesebb futóval vagy lövő nélkül None), "ahead" (bool |
    None — labda nélkül None), "path" [[x, y], …] (a befejező — lövő
    nélkül az első ember — útja FB_PATH_STEP_S lépésközzel az indulástól
    a lövésig / a szakasz végéig), "shot" [x, y] | None, "ball" [x, y] |
    None (a labda az induláskor), "goal" [x, y] (a támadott kapu
    közepe)}] időrendben, "breaks": {"home"/"away": db}, "goals":
    {"home"/"away": db}} — a számok a lerohanás-hatékonyság rétegével
    egyeznek."""
    from .attack_types import (ATTACK_TAIL_S, FBH_GAP_M, AttackType,
                               _advance_speed, classify_attacks)
    from .event_detection import EventType, detect_shots
    from .setplays import segment_attacks

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    tail = round(ATTACK_TAIL_S * fps)
    lepes = max(1, round(FB_PATH_STEP_S * fps))
    idx_of = {f.t: i for i, f in enumerate(match.frames)}
    shots = [e for e in detect_shots(match, config)
             if e.type in (EventType.SHOT, EventType.GOAL)]
    seqs = {s.start_t: s for s in segment_attacks(match, config)}
    jersey = _jersey_map(match)

    def hely(i, tid):
        if i is None or tid is None:
            return None
        p = next((q for q in match.frames[i].players if q.track_id == tid), None)
        return [round(p.x, 2), round(p.y, 2)] if p is not None else None

    moments = []
    breaks = {"home": 0, "away": 0}
    goals = {"home": 0, "away": 0}
    for a in classify_attacks(match, config):
        if a["type"] != AttackType.FAST_BREAK.value:
            continue
        side = a["team"]
        team = Team(side)
        goal_x = float(config.attacks_toward_x(team))
        breaks[side] += 1
        veg = a["end_frame"] + tail
        bent = [e for e in shots if e.team == team
                and a["start_frame"] <= e.t <= veg]
        gol = any(e.type == EventType.GOAL for e in bent)
        if gol:
            goals[side] += 1
        shot = next((e for e in bent if e.player_id is not None), None)
        # A klip-horgony és a befejező: ha a kontra gól lett, a GÓL
        # eseményé (kipattanóból a második lövő is lehet), különben az
        # első azonosított lövésé; lövés nélkül a szakasz vége.
        gol_ev = next((e for e in bent if e.type == EventType.GOAL), None)
        # A befejező EGY esemény: gólnál a gól lövője, ha azonosított
        # (kipattanóból a második lövő), különben az első azonosított
        # lövés — a horgony, az út, a mezszám, a lövés-hely és a hullám is
        # ebből, hogy a felirat, a rajz és a klip ugyanarról szóljon.
        befejezo = (gol_ev if gol_ev is not None and gol_ev.player_id is not None
                    else shot)
        horgony_t = (gol_ev.t if gol_ev is not None
                     else shot.t if shot is not None else a["end_frame"])
        i0 = idx_of.get(a["start_frame"])
        fr0 = match.frames[i0] if i0 is not None else None
        runners = [p for p in fr0.players
                   if p.team == team and p.role != "kapus"] if fr0 else []
        first_id = (min(runners, key=lambda p: abs(p.x - goal_x)).track_id
                    if runners else None)
        wave = None
        if befejezo is not None and len(runners) >= 2:
            wave = "second" if befejezo.player_id != first_id else "first"
        ahead = None
        if fr0 is not None and fr0.ball is not None and runners:
            front = min(abs(p.x - goal_x) for p in runners)
            ahead = abs(fr0.ball.x - goal_x) - front >= FBH_GAP_M
        futo = befejezo.player_id if befejezo is not None else first_id
        i1 = idx_of.get(befejezo.t if befejezo is not None else a["end_frame"],
                        idx_of.get(a["end_frame"]))
        path = []
        if i0 is not None and i1 is not None and futo is not None:
            indexek = list(range(i0, i1 + 1, lepes))
            if indexek[-1] != i1:
                indexek.append(i1)
            path = [h for h in (hely(i, futo) for i in indexek) if h is not None]
        seq = seqs.get(a["start_frame"])
        moments.append({
            "s": round(a["start_frame"] / fps, 2),
            "e": round(a["end_frame"] / fps, 2),
            "shot_s": (round(befejezo.t / fps, 2) if befejezo is not None
                       else None),
            "team": side, "defending": "away" if side == "home" else "home",
            "duration_s": a["duration_s"],
            "advance_ms": (round(_advance_speed(seq, goal_x, fps), 2)
                           if seq is not None else None),
            "outcome": "goal" if gol else ("shot" if bent else None),
            "t": horgony_t,
            "shooter_id": (befejezo.player_id if befejezo is not None
                           else None),
            "shooter_jersey": (jersey.get(befejezo.player_id)
                               if befejezo is not None else None),
            "first_jersey": jersey.get(first_id),
            "wave": wave, "ahead": ahead, "path": path,
            "shot": (hely(idx_of.get(befejezo.t), befejezo.player_id)
                     if befejezo is not None else None),
            "ball": ([round(fr0.ball.x, 2), round(fr0.ball.y, 2)]
                     if fr0 is not None and fr0.ball is not None else None),
            "goal": [goal_x, COURT_WIDTH_M / 2.0]})
    return {"moments": moments, "breaks": breaks, "goals": goals}


# Hétméteres: a célzott kapu-harmad közepe ennyire van a kapu közepétől
# (a 3 m-es kapu harmadai: a bal és a jobb harmad közepe 1 m-re).
SEVEN_AIM_OFFSET_M = 1.0


def seven_meter_moments(match: Match,
                        config: Optional[TacticsConfig] = None) -> dict:
    """A hétméteresek a 3D pályán: ki dobta, merre, mi lett belőle, és hol
    állt a kapus.

    A hetes-rétegek (seven_meter_outcomes: kimenet és irány;
    gk_seven_directions: a kapus gyenge oldala) számokban mondják — a 3D
    a jelenetet mutatja. UGYANAZOK a szabályok: a hetes a
    detect_seven_meters felismerése (álló labda a 7 m-es ponton), a lövés
    az utána SEVEN_OUTCOME_WINDOW_S-en belüli első saját lövés (ugyanaz,
    amit a seven_meter_outcomes párosít), az irány a _seven_direction
    sávja (bal / közép / jobb a DOBÓ szemszögéből). A kapus a védekező
    csapat kapus-jelölésű — több ilyennél a saját kapuhoz legközelebbi —
    játékosa a lövés (elengedés) kockáján; a mélysége a kapu közepétől
    mért távolság (mint a kapus-kimozdulás rétegben). Saját küszöb nincs.

    Visszatérés: {"moments": [{"s" (a hetes kezdete — az álló labda),
    "t", "shot_s" (a lövés mp | None), "team" (a dobó), "defending",
    "spot": [x, y] (a labda a 7 m-es ponton), "shooter": [x, y] | None,
    "shooter_jersey", "outcome" ("gól" / "védés" / "kihagyva" /
    "ismeretlen"), "irany" ("bal" / "közép" / "jobb" | None), "aim":
    [x, y] | None (a célzott kapu-harmad közepe), "keeper": [x, y] |
    None, "keeper_depth", "goal": [x, y] (a támadott kapu közepe)}]
    időrendben, "attempts": {"home"/"away": db}, "goals": {...}} — a
    számok a seven_meter_summary kísérlet- és gól-számaival egyeznek."""
    from .rules import seven_meter_outcomes

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    by_t = {f.t: f for f in match.frames}
    jersey = _jersey_map(match)
    cy = COURT_WIDTH_M / 2.0

    moments = []
    attempts = {"home": 0, "away": 0}
    goals = {"home": 0, "away": 0}
    for sm in seven_meter_outcomes(match, config):
        side = sm["team"]
        vedo = Team.AWAY if side == "home" else Team.HOME
        goal_x = float(sm["goal_x"])
        attempts[side] += 1
        if sm["outcome"] == "gól":
            goals[side] += 1
        # A lövés: a seven_meter_outcomes párosítása (a rekord viszi a
        # párosított lövés és az elengedés kockáját) — nem számoljuk újra.
        rel_t = sm.get("release_t")
        if rel_t not in by_t:
            rel_t = sm.get("shot_t")
        f0 = by_t.get(sm["t"])
        fl = by_t.get(rel_t) if rel_t is not None else f0
        spot = ([round(f0.ball.x, 2), round(f0.ball.y, 2)]
                if f0 is not None and f0.ball is not None else None)
        lovo = None
        if fl is not None and sm["shooter_id"] is not None:
            lovo = next((p for p in fl.players
                         if p.track_id == sm["shooter_id"]), None)
        kapus = _nearest_keeper(fl, vedo, goal_x)
        aim = None
        if sm["irany"] is not None:
            # A dobó szemszögéből: a +x kapura a bal az alacsony y (a
            # _seven_direction tükre), a -x kapura fordítva.
            d = {"bal": -1.0, "közép": 0.0, "jobb": 1.0}[sm["irany"]]
            jel = 1.0 if goal_x > COURT_LENGTH_M / 2.0 else -1.0
            aim = [goal_x, round(cy + jel * d * SEVEN_AIM_OFFSET_M, 2)]
        moments.append({
            "s": round(sm["t"] / fps, 2), "t": sm["t"],
            "shot_s": round(rel_t / fps, 2) if rel_t is not None else None,
            "team": side, "defending": vedo.value,
            "spot": spot,
            "shooter": ([round(lovo.x, 2), round(lovo.y, 2)]
                        if lovo is not None else None),
            "shooter_jersey": jersey.get(sm["shooter_id"]),
            "outcome": sm["outcome"], "irany": sm["irany"], "aim": aim,
            "keeper": ([round(kapus.x, 2), round(kapus.y, 2)]
                       if kapus is not None else None),
            "keeper_depth": (round(math.hypot(kapus.x - goal_x,
                                              kapus.y - cy), 2)
                             if kapus is not None else None),
            "goal": [goal_x, cy]})
    moments.sort(key=lambda m_: (m_["s"], m_["team"]))
    return {"moments": moments, "attempts": attempts, "goals": goals}


# Kulcs-jelenetek: a legnagyobb döntés-hibákból ennyi, és összesen
# legfeljebb ennyi sor. A plafon a fontossági sorrendben tölt (a gólba
# került eladások, a kapott lerohanás-gólok, a gólt érő szabad lövők a
# legszabadabbtól, végül a döntés-hibák a legnagyobb réstől) — nem az
# időrendben elsőket tartja meg, így a lista az egész meccsről szól.
KEY_SCENES_DECISION_TOP = 5
KEY_SCENES_MAX = 15


def key_scene_rows(match: Match, config: Optional[TacticsConfig] = None,
                   decision_top: int = KEY_SCENES_DECISION_TOP,
                   max_rows: int = KEY_SCENES_MAX) -> dict:
    """A meccs VIDEÓZANDÓ jelenetei — a jelenet-lista legfontosabb sorai.

    A 3D jelenet-lista minden hibát mutat; ez a válogatás az edző
    "mit nézzünk vissza" listája: a gólba került labdavesztések és kapott
    lerohanások, a gólt érő szabadon hagyott lövők és a `decision_top`
    legnagyobb döntés-hiba, időrendben, legfeljebb `max_rows` sor. A
    kapott gólok NINCSENEK benne (minden kapott gól nem hiba — azoknak a 3D
    "Kapott gólok" lapozója való). A plafon fontossági sorrendben tölt: a
    gólba került eladások (a leggyorsabban büntetett elöl), a kapott
    lerohanás-gólok, a gólt érő szabad lövők (a legszabadabb elöl), a
    döntés-hibák (a legnagyobb rés elöl) — nem az időrendben elsőket
    tartja meg. A nyomtatott jelentés "Videózandó jelenetek" szakasza és a
    kezdőlap meccs-kártyája UGYANEZT adja.

    Visszatérés: {"rows": [scene_rows-sor: "s", "ido", "tipus", "side",
    "szoveg", "gol"], "total": a válogatás előtti sorok száma}."""
    # A config csak megadva megy tovább: a rétegek alapértelmezése a
    # közös TacticsConfig (a jelentés tesztjei a rétegeket egy-paraméteres
    # helyettesítővel cserélik).
    kw = {} if config is None else {"config": config}
    dontesek = sorted(decision_moments(match, **kw)["moments"],
                      key=lambda d: (-d["gap"], d["s"]))[:decision_top]
    szabadok = [d for d in free_shot_moments(match, **kw)["moments"]
                if d["goal"]]
    eladasok = [d for d in turnover_moments(match, **kw)["moments"]
                if d["punished"]]
    kontrak = [d for d in fast_break_moments(match, **kw)["moments"]
               if d["outcome"] == "goal"]
    total = len(dontesek) + len(szabadok) + len(eladasok) + len(kontrak)
    # Fontossági sorrendben töltünk a plafonig (rétegenként a legfontosabb
    # elöl), aztán a kiválasztott sorok időrendben.
    maradt = max(0, max_rows)

    def vesz(lista):
        nonlocal maradt
        ki = lista[:maradt]
        maradt -= len(ki)
        return ki

    eladasok = vesz(sorted(eladasok, key=lambda d: (d["goal_after_s"], d["s"])))
    kontrak = vesz(sorted(kontrak, key=lambda d: d["s"]))
    szabadok = vesz(sorted(szabadok, key=lambda d: (-(d.get("dist") or 0.0),
                                                     d["s"])))
    dontesek = vesz(dontesek)
    sorok = scene_rows(dontesek, szabadok, eladasok,
                       match.meta.home_team, match.meta.away_team, kontrak)
    return {"rows": sorok, "total": total}


# Kapott gól: a kapus "kint állt" a lövés pillanatában, ha ennyinél
# messzebb volt a saját kapu közepétől. A kapus-kimozdulás réteg 1,5 m-e
# a MECCS-ÁTLAG küszöbe (a kapus egy lövésnél rendesen 1–2 m-re áll a
# vonaltól); egy pillanatra a 2,5 m feletti kint állás az átemelhető,
# "kijött elé" helyzet.
CG_KEEPER_OUT_M = 2.5


def conceded_goal_moments(match: Match,
                          config: Optional[TacticsConfig] = None) -> dict:
    """A kapott gólok a 3D pályán — a VÉDEKEZŐ csapat szerint: ki lőtte,
    honnan (sáv, kapu-szög), ki volt a legközelebbi védő és milyen
    messze, hol állt a kapus (mélység a saját kaputól), és mennyit ért a
    helyzet (xG). A "minden kapott gól egy listában" videóelemzés.

    Forrás: a defense_analysis gól-sorai (ugyanaz az elengedési kocka,
    lövő, lövő-hely, legközelebbi védő, szabad-ítélet és xG — a 3D nem
    mondhat mást, mint a védekezés-elemzés); a sáv és a kapu-szög a
    shot_geometry mérése; a kapus mélysége a gk_positioning mérése (a
    kapus-jelölésű — több ilyennél a saját kapuhoz legközelebbi — játékos
    távolsága a saját kapu közepétől), a "kint állt" ítélet a pillanatra
    szabott CG_KEEPER_OUT_M.

    Visszatérés: {"moments": [{"s", "t" (az elengedés kockája), "team"
    (a lövő csapat), "defending", "shooter": [x, y], "shooter_jersey",
    "zone" ("kapuelőtér" / "6–9 m" / "9 m-en túl"), "angle_deg",
    "dist_m", "defender": [x, y] | None, "def_dist", "free" (bool |
    None), "keeper": [x, y] | None, "keeper_depth", "keeper_out" (bool |
    None — kapus nélkül None), "xg", "goal": [x, y] (a támadott kapu
    közepe)}] időrendben, "conceded": {"home"/"away": db} (a védekező
    szerint — a védekezés-elemzés goals_against-ja), "free": {...},
    "keeper_out": {...}, "depth_out_m": CG_KEEPER_OUT_M, "radius_m":
    FREE_DEF_RADIUS_M}."""
    from .defense import FREE_DEF_RADIUS_M, defense_analysis

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    by_t = {f.t: f for f in match.frames}
    jersey = _jersey_map(match)
    d = defense_analysis(match, config)
    cy = COURT_WIDTH_M / 2.0
    moments = []
    conceded = {"home": 0, "away": 0}
    free = {"home": 0, "away": 0}
    keeper_out = {"home": 0, "away": 0}
    for side in ("home", "away"):
        vedo = Team(side)
        tamado = Team.AWAY if vedo == Team.HOME else Team.HOME
        own_x = float(config.own_goal_x(vedo))
        for sh in d[side]["shots"]:
            if not sh["goal"]:
                continue
            conceded[side] += 1
            f = by_t.get(sh["release_t"])
            # A kapus: a védekező csapat kapus-jelölésű játékosa az
            # elengedés kockáján (több ilyennél a kapuhoz legközelebbi).
            kapus = _nearest_keeper(f, vedo, own_x)
            geo = shot_geometry(sh["x"], sh["y"],
                                "bal" if own_x == 0.0 else "jobb")
            mely = (round(math.hypot(kapus.x - own_x, kapus.y - cy), 2)
                    if kapus is not None else None)
            kint = (mely >= CG_KEEPER_OUT_M) if mely is not None else None
            if kint:
                keeper_out[side] += 1
            if sh["free"]:
                free[side] += 1
            moments.append({
                "s": round(sh["release_t"] / fps, 2), "t": sh["release_t"],
                "team": tamado.value, "defending": side,
                "shooter": [sh["x"], sh["y"]],
                "shooter_jersey": jersey.get(sh.get("player_id")),
                "zone": geo["zone"], "angle_deg": geo["angle_deg"],
                "dist_m": geo["distance_m"],
                "defender": sh["defender"], "def_dist": sh["def_dist"],
                "free": sh["free"],
                "keeper": ([round(kapus.x, 2), round(kapus.y, 2)]
                           if kapus is not None else None),
                "keeper_depth": mely, "keeper_out": kint,
                "xg": round(float(sh["xg"]), 2),
                "goal": [own_x, cy]})
    moments.sort(key=lambda m_: (m_["s"], m_["defending"]))
    return {"moments": moments, "conceded": conceded, "free": free,
            "keeper_out": keeper_out, "depth_out_m": CG_KEEPER_OUT_M,
            "radius_m": FREE_DEF_RADIUS_M}
