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
from .primitive_cache import copy_nested, memoize_primitive

# Legalább ennyi támadó-fázisú kocka kell egy játékos poszt-becsléséhez.
ROLE_MIN_SAMPLES = 100
# Szélső sáv: a pálya szélességének külső ennyi része (mindkét oldalon).
ROLE_WING_FRAC = 0.28
# Beálló: ennél közelebb a támadott kapuhoz, középen.
ROLE_PIVOT_DIST_M = 8.0
# Irányító: ennél távolabb a kaputól, középen.
ROLE_BACKCOURT_DIST_M = 10.5


@memoize_primitive("estimate_positions", copy=copy_nested)
def estimate_positions(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Poszt-becslés a támadó-fázis átlag-pozícióiból.

    Visszatérés: {"home"/"away": {track_id: {"poszt", "samples",
    "avg_dist_m"}}} — csak a ROLE_MIN_SAMPLES-t elérő játékosokra.
    A kapus (role="kapus") kimarad: az ő posztja adott.

    Nyitott `primitive_cache` hatókörön belül meccsenként egyszer fut le;
    a visszaadott dict mindig friss másolat.
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


# Poszt-hibák: ennyi poszthoz kötött labdaeladás kell az ítélethez, és
# e feletti részarány emeli ki a hibázó posztot.
ROLE_TO_MIN = 6
ROLE_TO_SHARE = 40.0


def turnovers_by_role(match: Match,
                      config: Optional[TacticsConfig] = None) -> dict:
    """Poszt-hibák: MELYIK POSZTJUK veszíti el a labdát.

    A labdaeladók (turnover_players) a hibázó EMBERT nevezik meg, a
    hiba-zónák (turnover_zones) a helyet — ez a posztot: a
    labdaeladásokat a vesztes becsült posztjához kötjük, így akkor is
    látszik a minta, ha a nevek meccsről meccsre cserélődnek.

    Edzőileg ez mondja meg, melyik passzsávban érdemes zavarni: ha a
    beállójuk szórja el a bejátszásokat, a beálló-vonalra kell lépni;
    ha az irányítójuk, a felső kettőzés termel; ha a szélsőjük, a
    szélső-bejátszásokat lehet vadászni.

    Visszatérés csapatonként: {"turnovers" (poszthoz kötött eladások),
    "roles": {poszt: eladások}, "top": {"poszt", "turnovers",
    "share_pct"} | None} — a "top" akkor van kitöltve, ha legalább
    ROLE_TO_MIN poszthoz kötött eladás van, a vezető poszt részaránya
    eléri a ROLE_TO_SHARE-t, és nincs holtverseny.
    """
    from .event_detection import EventType, detect_events

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    out: dict = {side: {"turnovers": 0, "roles": {}, "top": None}
                 for side in ("home", "away")}
    for e in detect_events(match, config):
        if e.type != EventType.TURNOVER or e.player_id is None:
            continue
        side = e.team.value
        rec_role = roles[side].get(e.player_id)
        if rec_role is None:
            continue
        rec = out[side]
        rec["turnovers"] += 1
        poszt = rec_role["poszt"]
        rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        items = list(rec["roles"].items())
        if rec["turnovers"] >= ROLE_TO_MIN and items:
            poszt, n = items[0]
            share = 100.0 * n / rec["turnovers"]
            tie = len(items) > 1 and items[1][1] == n
            if share >= ROLE_TO_SHARE and not tie:
                rec["top"] = {"poszt": poszt, "turnovers": n,
                              "share_pct": round(share, 1)}
    return out


# Gólpassz-posztok: ennyi poszthoz kötött gólpassz kell az ítélethez,
# és e feletti részarány jelenti, hogy egy posztról készítik elő a
# góljaikat.
ROLE_AS_MIN = 5
ROLE_AS_SHARE = 45.0


def assists_by_role(match: Match,
                    config: Optional[TacticsConfig] = None) -> dict:
    """Gólpassz-posztok: MELYIK POSZTJUK készíti elő a góljaikat.

    A gólpassz-forrás (assist_sources) a HELYET nézi (hátsó sor vagy
    közép), a gólpassz-hálózat a neveket — ez a posztot: a gólokhoz
    rendelt gólpasszokat az előkészítő becsült posztjához kötjük, így
    akkor is látszik a minta, ha a nevek meccsről meccsre cserélődnek.

    Edzőileg ez mondja meg, melyik poszt kezét kell megfogni: ha az
    irányítójuk osztja a gólpasszokat, a felső kettőzés vágja el a
    játékukat; ha a szélsőjük, a szélről visszatett labdákra kell
    zárni; ha a beállójuk, az elé állás a bejátszás UTÁN is
    folytatódjon (kiosztás ellen).

    Visszatérés csapatonként: {"assists" (poszthoz kötött gólpasszok),
    "roles": {poszt: gólpasszok}, "top": {"poszt", "assists",
    "share_pct"} | None} — a "top" akkor van kitöltve, ha legalább
    ROLE_AS_MIN poszthoz kötött gólpassz van, a vezető poszt
    részaránya eléri a ROLE_AS_SHARE-t, és nincs holtverseny.
    """
    from .event_detection import EventType, detect_events

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    out: dict = {side: {"assists": 0, "roles": {}, "top": None}
                 for side in ("home", "away")}
    for e in detect_events(match, config):
        if e.type != EventType.GOAL:
            continue
        aid = (e.detail or {}).get("assist_id")
        if aid is None:
            continue
        side = e.team.value
        rec_role = roles[side].get(aid)
        if rec_role is None:
            continue
        rec = out[side]
        rec["assists"] += 1
        poszt = rec_role["poszt"]
        rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        items = list(rec["roles"].items())
        if rec["assists"] >= ROLE_AS_MIN and items:
            poszt, n = items[0]
            share = 100.0 * n / rec["assists"]
            tie = len(items) > 1 and items[1][1] == n
            if share >= ROLE_AS_SHARE and not tie:
                rec["top"] = {"poszt": poszt, "assists": n,
                              "share_pct": round(share, 1)}
    return out


# Poszt szerinti befejezés-hatékonyság: ennyi poszthoz kötött lövés
# kell egy poszt megítéléséhez, és ekkora eltérés a csapat-átlagtól
# számít érdemi különbségnek (százalékpont).
SER_MIN_SHOTS = 5
SER_GAP_PP = 15.0


def shot_efficiency_by_role(match: Match,
                            config: Optional[TacticsConfig] = None) -> dict:
    """Poszt szerinti befejezés-hatékonyság: MELYIK POSZTRÓL ÉRDEMES
    engedni a lövést.

    A poszt szerinti gólmegoszlás (goals_by_role) azt mondja meg,
    honnan JÖNNEK a góljaik — de egy poszt attól is termelhet sok
    gólt, hogy sokat lő. Ez a réteg a poszt lövéseit és góljait
    együtt nézi: melyik posztról hány százalék megy be.

    Edzőileg ez fordítja meg a védekezési logikát: a csapat-átlagnál
    SOKKAL rosszabb posztra rá lehet engedni a lövést (ott áll a
    legkevesebb kockázat), a sokkal jobbat viszont el kell zárni —
    inkább vállalva, hogy máshonnan lőnek. Ez a "hova tereld" döntés.

    Visszatérés csapatonként: {"shots", "goals", "team_pct",
    "roles": {poszt: {"shots", "goals", "pct"}},
    "best"/"worst": {"poszt", "shots", "goals", "pct", "gap_pp"} |
    None} — a best/worst csak akkor van kitöltve, ha az adott poszt
    elérte a SER_MIN_SHOTS lövést, és a csapat-átlagtól legalább
    SER_GAP_PP százalékponttal tér el (kevés mintából nem ítélünk).
    """
    from .event_detection import EventType, detect_events

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    out: dict = {}
    tally: dict = {"home": {}, "away": {}}
    totals: dict = {"home": [0, 0], "away": [0, 0]}  # [lövés, gól]

    for e in detect_events(match, config):
        if e.type not in (EventType.SHOT, EventType.GOAL):
            continue
        if e.player_id is None:
            continue
        side = e.team.value
        rec_role = roles[side].get(e.player_id)
        if rec_role is None:
            continue  # ismeretlen poszt — nem találgatunk
        poszt = rec_role["poszt"]
        rec = tally[side].setdefault(poszt, [0, 0])
        rec[0] += 1
        totals[side][0] += 1
        if e.type == EventType.GOAL:
            rec[1] += 1
            totals[side][1] += 1

    for side in ("home", "away"):
        shots, goals = totals[side]
        team_pct = (100.0 * goals / shots) if shots else None
        rows = {}
        for poszt, (s_n, g_n) in sorted(tally[side].items(),
                                        key=lambda kv: -kv[1][0]):
            rows[poszt] = {"shots": s_n, "goals": g_n,
                           "pct": round(100.0 * g_n / s_n, 1) if s_n
                           else None}
        best = worst = None
        if team_pct is not None:
            eligible = [(p, r) for p, r in rows.items()
                        if r["shots"] >= SER_MIN_SHOTS]
            for pick, key in (("best", max), ("worst", min)):
                if not eligible:
                    continue
                poszt, r = key(eligible, key=lambda pr: pr[1]["pct"])
                gap = r["pct"] - team_pct
                if abs(gap) < SER_GAP_PP:
                    continue
                if (pick == "best" and gap < 0) or \
                        (pick == "worst" and gap > 0):
                    continue
                rec_pick = {"poszt": poszt, "shots": r["shots"],
                            "goals": r["goals"], "pct": r["pct"],
                            "gap_pp": round(gap, 1)}
                if pick == "best":
                    best = rec_pick
                else:
                    worst = rec_pick
        out[side] = {"shots": shots, "goals": goals,
                     "team_pct": round(team_pct, 1)
                     if team_pct is not None else None,
                     "roles": rows, "best": best, "worst": worst}
    return out


# Gólpassz-tengelyek: ennyi poszthoz kötött gólpassz-pár kell az
# ítélethez, és ekkora részarány fölött nevezzük tengelynek.
ARP_MIN_PAIRS = 4
ARP_SHARE = 40.0


def assist_role_pairs(match: Match,
                      config: Optional[TacticsConfig] = None) -> dict:
    """Gólpassz-tengelyek poszt szerint: MELYIK VONALON esnek a góljaik.

    A gólpassz-posztok (assists_by_role) azt mondják meg, melyik poszt
    OSZTJA a gólpasszokat, a poszt szerinti gólmegoszlás
    (goals_by_role) azt, melyik poszt LŐ — ez a kettőt köti össze:
    melyik poszt melyik posztnak adja a gólpasszt (pl. "irányító →
    beálló"). A neveket használó gólpassz-hálózattal szemben ez akkor
    is látszik, ha a játékosok meccsről meccsre cserélődnek.

    Edzőileg ez egyetlen, kiosztható feladat: a domináns tengelyt kell
    elvágni, nem két embert külön fogni. Irányító→beálló tengelynél a
    beálló elé állás és a felső kettőzés együtt; átlövő→szélső
    tengelynél a szélső zárása a lövő-mozdulat pillanatában.

    Visszatérés csapatonként: {"pairs_total", "pairs": {"A→B": darab},
    "top": {"from", "to", "goals", "share_pct"} | None} — a "top"
    akkor van kitöltve, ha legalább ARP_MIN_PAIRS poszthoz kötött pár
    van, a vezető pár részaránya eléri az ARP_SHARE-t, és nincs
    holtversenyben másik párral.
    """
    from .event_detection import EventType, detect_events

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    tally: dict = {"home": {}, "away": {}}

    for e in detect_events(match, config):
        if e.type != EventType.GOAL or e.player_id is None:
            continue
        assist_id = (e.detail or {}).get("assist_id")
        if assist_id is None:
            continue
        side = e.team.value
        scorer = roles[side].get(e.player_id)
        passer = roles[side].get(assist_id)
        if scorer is None or passer is None:
            continue  # ismeretlen poszt — nem találgatunk
        key = f"{passer['poszt']}→{scorer['poszt']}"
        tally[side][key] = tally[side].get(key, 0) + 1

    out: dict = {}
    for side in ("home", "away"):
        pairs = dict(sorted(tally[side].items(), key=lambda kv: -kv[1]))
        total = sum(pairs.values())
        top = None
        items = list(pairs.items())
        if total >= ARP_MIN_PAIRS and items:
            key, n = items[0]
            share = 100.0 * n / total
            tie = len(items) > 1 and items[1][1] == n
            if share >= ARP_SHARE and not tie:
                frm, to = key.split("→", 1)
                top = {"from": frm, "to": to, "goals": n,
                       "share_pct": round(share, 1)}
        out[side] = {"pairs_total": total, "pairs": pairs, "top": top}
    return out


# Poszt-váltás a szünetre: félidőnként ennyi poszthoz kötött gól kell,
# és ekkora részarány-változás (százalékpont) számít érdemi váltásnak.
RSS_MIN_GOALS = 4
RSS_GAP_PP = 20.0


def role_share_shift(match: Match,
                     config: Optional[TacticsConfig] = None) -> dict:
    """Poszt-váltás a szünetre: MELYIK POSZTRA épül a befejezésük a
    második félidőben.

    A poszt szerinti gólmegoszlás (goals_by_role) az egész meccset
    nézi — de egy edző a szünetben átrendezi a támadást. Ez a réteg a
    felismert félidő előtti és utáni gólok poszt-megoszlását veti
    össze, és megnevezi azt a posztot, amelynek a részaránya a
    legtöbbet mozdult.

    Edzőileg ez a meccs közbeni döntést írja felül: ha tudjuk, hogy a
    szünet után a beállójukra állnak rá, a beálló-őrzést már a
    félidőben meg kell erősíteni, nem a második gól után; ha a
    szélsőjük tűnik el, a szélső védője behúzható középre.

    Visszatérés csapatonként: {"first": {poszt: gól}, "second":
    {poszt: gól}, "first_total", "second_total", "shift": {"poszt",
    "first_pct", "second_pct", "gap_pp"} | None, "verdict": str |
    None} — a shift/verdict None, ha nincs felismert félidő, ha
    valamelyik félidőben RSS_MIN_GOALS-nál kevesebb poszthoz kötött
    gól van, vagy ha a legnagyobb elmozdulás sem éri el az
    RSS_GAP_PP-t (kevés mintából nem ítélünk).
    """
    from .event_detection import EventType, detect_events
    from .halftime import detect_halftime

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    ht = detect_halftime(match)

    tally: dict = {"home": [{}, {}], "away": [{}, {}]}
    if ht is not None:
        for e in detect_events(match, config):
            if e.type != EventType.GOAL or e.player_id is None:
                continue
            side = e.team.value
            rec_role = roles[side].get(e.player_id)
            if rec_role is None:
                continue
            half = 0 if e.t <= ht else 1
            poszt = rec_role["poszt"]
            tally[side][half][poszt] = tally[side][half].get(poszt, 0) + 1

    out: dict = {}
    for side in ("home", "away"):
        first, second = tally[side]
        n1, n2 = sum(first.values()), sum(second.values())
        shift = verdict = None
        if n1 >= RSS_MIN_GOALS and n2 >= RSS_MIN_GOALS:
            best = None
            for poszt in set(first) | set(second):
                p1 = 100.0 * first.get(poszt, 0) / n1
                p2 = 100.0 * second.get(poszt, 0) / n2
                gap = p2 - p1
                if best is None or abs(gap) > abs(best[3]):
                    best = (poszt, p1, p2, gap)
            if best is not None and abs(best[3]) >= RSS_GAP_PP:
                poszt, p1, p2, gap = best
                shift = {"poszt": poszt, "first_pct": round(p1, 1),
                         "second_pct": round(p2, 1),
                         "gap_pp": round(gap, 1)}
                verdict = (f"a(z) {poszt} szerepe nő a szünet után"
                           if gap > 0
                           else f"a(z) {poszt} szerepe csökken a szünet "
                                "után")
        out[side] = {"first": dict(sorted(first.items(),
                                          key=lambda kv: -kv[1])),
                     "second": dict(sorted(second.items(),
                                           key=lambda kv: -kv[1])),
                     "first_total": n1, "second_total": n2,
                     "shift": shift, "verdict": verdict}
    return out
