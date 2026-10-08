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
from typing import Optional

from ..models.tracking import Match, Team
from .calibration import COURT_LENGTH_M, COURT_WIDTH_M, GOAL_WIDTH_M
from .tactics import TacticsConfig

# A szabálykönyvi vonalak a kapufák közti szakasztól mérve (méter).
GOAL_AREA_LINE_M = 6.0
FREE_THROW_LINE_M = 9.0

# A védekezés-idővonal mintavétele (másodperc): a fal alakja ennél
# sűrűbben nem változik érdemben, és egy 60 perces meccs így 3600 sor.
DEFENCE_TIMELINE_STEP_S = 1.0

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


def tactical_keys_by_team(match: Match, top: int = DEFENCE_BREAKPOINTS_TOP) -> dict:
    """A 3D védekezés-panel két sora EGY felderítésből csapatonként:
    "breakpoints" — hol törhető fel a csapat VÉDEKEZÉSE
    (scouting.defence_breakpoints), és "stoppers" — hogyan állítható
    meg a csapat TÁMADÁSA (scouting.attack_stoppers), mindkettő a
    rangsor teteje. Egy szervezett támadásban a panel a védekező csapat
    "breakpoints"-ját (mivel törjük fel) és a támadó csapat
    "stoppers"-ét (mivel állítjuk meg) írja. Visszatérés:
    {"breakpoints": {"home": [...], "away": [...]}, "stoppers": {...}}
    — csapatonként üres lista, ha nincs elég minta vagy a felderítés
    hibázik (egy csapat hibája nem viszi el a másikat)."""
    from .scouting import attack_stoppers, defence_breakpoints, scout_team
    ki = {"breakpoints": {}, "stoppers": {}}
    for side, team in (("home", Team.HOME), ("away", Team.AWAY)):
        try:
            rep = scout_team(match, team)
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


def decision_moments(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """A passz-döntések, ahol a modell szerint ÉRDEMBEN jobb opció is volt.

    Minden felismert passznál (decisions.detect_passes) a döntés-kockán
    az opciók (decisions.evaluate_options) közül a legjobbat
    (best_option) összevetjük a választottal; ha a különbség eléri a
    DECISION_GAP_MIN-t, a pillanat bekerül.

    Edzőileg: ezek a videózandó jelenetek — "itt a beálló szabad volt",
    "itt lövés kellett volna". Az átlagos optimalitás nem mutatja meg,
    HOL és MI volt a jobb választás; ez igen.

    Visszatérés: {"moments": [{"s", "team", "passer": [x, y],
    "chosen": [x, y], "chosen_value", "best_kind", "best": [x, y],
    "best_value", "gap"}] időrendben, "passes": {"home"/"away": db},
    "flagged": {"home"/"away": db}} — a "best" passznál a jobb társ
    helye, lövésnél a támadott kapu közepe."""
    from .decisions import best_option, detect_passes, evaluate_options

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    moments: list[dict] = []
    passes = {"home": 0, "away": 0}
    flagged = {"home": 0, "away": 0}
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
        moments.append({
            "s": round(pe.decision_frame.t / fps, 2), "team": side,
            "passer": [round(pe.passer_pos.x, 1), round(pe.passer_pos.y, 1)],
            "chosen": [round(rec.x, 1), round(rec.y, 1)],
            "chosen_value": round(chosen.value, 3),
            "best_kind": best.kind,
            "best": cel,
            "best_value": round(best.value, 3),
            "gap": round(gap, 3),
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

    Visszatérés: {"moments": [{"s", "team", "jersey", "loser": [x, y] |
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
            "s": round(e.t / fps, 2), "team": side,
            "jersey": jersey.get(e.player_id),
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
