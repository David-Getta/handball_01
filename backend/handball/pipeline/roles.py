"""Poszt-becslés — ki hol játszik a támadásban.

A mezszám mögé odatehető a poszt is: a támadó-fázisban (amikor a saját
csapat birtokolja a labdát) felvett átlagos hely elárulja, ki a beálló,
ki a szélső, ki az átlövő és ki az irányító. A felderítési kulcsok így
poszt-nyelven beszélhetnek ("a beállójuk elzárásaira figyelj").

Szándékosan egyszerű, magyarázható szabályok — nem tanult modell:
minden címke mögött két szám áll (kapu-távolság + oldalsó sáv).
"""

from __future__ import annotations

from typing import Optional

from ..models.tracking import Match, Team
from .calibration import COURT_WIDTH_M
from .tactics import COURT_LENGTH_M, TacticsConfig, possession_team

# Legalább ennyi támadó-fázisú kocka kell egy játékos poszt-becsléséhez.
ROLE_MIN_SAMPLES = 100
# Szélső sáv: a pálya szélességének külső ennyi része (mindkét oldalon).
ROLE_WING_FRAC = 0.28
# Beálló: ennél közelebb a támadott kapuhoz, középen.
ROLE_PIVOT_DIST_M = 8.0
# Irányító: ennél távolabb a kaputól, középen.
ROLE_BACKCOURT_DIST_M = 10.5


def estimate_positions(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Poszt-becslés a támadó-fázis átlag-pozícióiból.

    Visszatérés: {"home"/"away": {track_id: {"poszt", "samples",
    "avg_dist_m"}}} — csak a ROLE_MIN_SAMPLES-t elérő játékosokra.
    A kapus (role="kapus") kimarad: az ő posztja adott.
    """
    config = config or TacticsConfig()
    acc: dict = {}
    for fr in match.frames:
        poss = possession_team(fr, config)
        if poss is None:
            continue
        goal_x = config.attacks_toward_x(poss)
        for p in fr.players:
            if p.team != poss or p.role == "kapus":
                continue
            # Csak az érdemi támadó-térfélen mért helyek számítanak.
            dist = abs(p.x - goal_x)
            if dist > 15.0:
                continue
            rec = acc.setdefault((p.team.value, p.track_id),
                                 [0, 0.0, 0.0])
            rec[0] += 1
            rec[1] += dist
            rec[2] += p.y
    out: dict = {"home": {}, "away": {}}
    for (side, tid), (n, dist_sum, y_sum) in acc.items():
        if n < ROLE_MIN_SAMPLES:
            continue
        avg_dist = dist_sum / n
        avg_y = y_sum / n
        wing = (avg_y <= COURT_WIDTH_M * ROLE_WING_FRAC
                or avg_y >= COURT_WIDTH_M * (1.0 - ROLE_WING_FRAC))
        if wing:
            poszt = "szélső"
        elif avg_dist <= ROLE_PIVOT_DIST_M:
            poszt = "beálló"
        elif avg_dist >= ROLE_BACKCOURT_DIST_M:
            poszt = "irányító"
        else:
            poszt = "átlövő"
        out[side][tid] = {"poszt": poszt, "samples": n,
                          "avg_dist_m": round(avg_dist, 1)}
    return out


# Poszt szerinti gólmegoszlás: ennyi poszthoz kötött góltól ítélünk, és
# e feletti részarány jelenti, hogy egy posztra épül a támadásuk.
ROLE_GOALS_MIN = 5
ROLE_GOALS_SHARE = 45.0


def goals_by_role(match: Match,
                  config: Optional[TacticsConfig] = None) -> dict:
    """Poszt szerinti gólmegoszlás: MELYIK POSZTRÓL jönnek a góljaik.

    A poszt-becslés (estimate_positions) megmondja, ki milyen poszton
    játszik; ez a réteg a gólokat köti a lövő posztjához — vagyis nem
    azt, ki a gólfelelősük, hanem hogy melyik posztra épül a
    befejezésük (szélső, beálló, átlövő, irányító).

    Edzőileg ez rendezi a védekezési feladatokat: szélső-gólok ellen a
    kifutás és a szög zárása, beállós gólok ellen az elé állás,
    átlövő-gólok ellen az előrelépés a lövő-vonalba.

    Visszatérés csapatonként: {"goals" (poszthoz kötött gólok),
    "roles": {poszt: gólok}, "top": {"poszt", "goals", "share_pct"} |
    None} — a "top" akkor van kitöltve, ha legalább ROLE_GOALS_MIN
    poszthoz kötött gól van, a vezető poszt részaránya eléri a
    ROLE_GOALS_SHARE-t, és nincs vele holtversenyben másik poszt.
    """
    from .event_detection import EventType, detect_events

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    out: dict = {side: {"goals": 0, "roles": {}, "top": None}
                 for side in ("home", "away")}
    for e in detect_events(match, config):
        if e.type != EventType.GOAL or e.player_id is None:
            continue
        side = e.team.value
        rec_role = roles[side].get(e.player_id)
        if rec_role is None:
            continue
        rec = out[side]
        rec["goals"] += 1
        poszt = rec_role["poszt"]
        rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        items = list(rec["roles"].items())
        if rec["goals"] >= ROLE_GOALS_MIN and items:
            poszt, n = items[0]
            share = 100.0 * n / rec["goals"]
            tie = len(items) > 1 and items[1][1] == n
            if share >= ROLE_GOALS_SHARE and not tie:
                rec["top"] = {"poszt": poszt, "goals": n,
                              "share_pct": round(share, 1)}
    return out
