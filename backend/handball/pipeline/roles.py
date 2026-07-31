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


# Egyirányú játékosok: ennyi fázis-besorolt kocka kell egy játékoshoz,
# és e feletti védekező (vagy ez alatti, azaz támadó) részarány teszi
# specialistává.
PHS_MIN_FRAMES = 1500
PHS_SPEC_PCT = 75.0


def phase_specialists(match: Match, config=None) -> dict:
    """Egyirányú játékosok: KI JÁTSZIK CSAK VÉDEKEZNI vagy CSAK TÁMADNI.

    A csere-blokkok azt mondják meg, egységekben cserélnek-e — ez azt,
    KIK az egységek: játékosonként megszámoljuk, a pályán töltött
    (labdabirtokosos) kockáiból mennyi esett a saját csapata
    védekezésére. Aki szinte csak védekezéskor van fent, az
    védő-specialista; aki szinte csak támadáskor, az támadó-
    specialista — a kettő együtt a támadás-védekezés váltott sor.

    Edzőileg: a váltott sorral játszó csapat a csere pillanatában
    sebezhető — a gyors középkezdés és a szerzés utáni azonnali
    indítás rossz embereket talál a pályán; ha pedig a támadó-
    specialistát sikerül védekezésben fent ragasztani (gyors
    átmenettel), őt kell megtámadni.

    Visszatérés csapatonként: {"players": [{"player_id", "jersey",
    "frames", "def_frames"}], "def_specialists", "atk_specialists",
    "verdict"} — a players a fázis-besorolt kockák szerint csökkenő;
    a verdict "váltott sorokkal játszanak", ha védő- ÉS támadó-
    specialista is van, különben None.
    """
    from .decisions import ball_holder
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    jersey: dict[int, int] = {}
    acc: dict = {"home": {}, "away": {}}
    for f in match.frames:
        holder = ball_holder(f, config)
        if holder is None:
            continue
        for p in f.players:
            if p.role == "kapus":
                continue
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)
            rec = acc[p.team.value].setdefault(p.track_id, [0, 0])
            rec[0] += 1
            if p.team != holder.team:
                rec[1] += 1

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": tid, "jersey": jersey.get(tid),
                 "frames": n, "def_frames": d}
                for tid, (n, d) in sorted(acc[side].items(),
                                          key=lambda kv: -kv[1][0])]
        defs = [r for r in rows if r["frames"] >= PHS_MIN_FRAMES
                and 100.0 * r["def_frames"] / r["frames"] >= PHS_SPEC_PCT]
        atks = [r for r in rows if r["frames"] >= PHS_MIN_FRAMES
                and 100.0 * r["def_frames"] / r["frames"]
                <= 100.0 - PHS_SPEC_PCT]
        verdict = ("váltott sorokkal játszanak"
                   if defs and atks else None)
        out[side] = {"players": rows, "def_specialists": defs,
                     "atk_specialists": atks, "verdict": verdict}
    return out
