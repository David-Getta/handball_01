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
    from .scouting import defence_breakpoints, scout_team
    ki = {}
    for side, team in (("home", Team.HOME), ("away", Team.AWAY)):
        try:
            ki[side] = defence_breakpoints(scout_team(match, team))[:top]
        except Exception:
            ki[side] = []
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
