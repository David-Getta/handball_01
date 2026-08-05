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

    A lövéseket a felismerés lövőjéhez kötjük. Ez korábban kapu-felé
    torzított (a távolról elengedett lövés a kapuhoz közeli poszthoz
    került); a `_shooter_before` azóta az ELENGEDÉS pillanatát keresi
    meg, tehát a poszt-bontás az elengedő posztját tükrözi. Valós
    felvételen a hozzárendelés pontosságát még ellenőrizni
    kell (docs/MERESI_JEGYZOKONYV.md).

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
        verdict = None
        if worst is not None:
            verdict = (f"a(z) {worst['poszt']} posztjukról alig megy be "
                       "a lövés")
        elif best is not None:
            verdict = (f"a(z) {best['poszt']} posztjuk a legveszélyesebb "
                       "befejező")
        out[side] = {"shots": shots, "goals": goals,
                     "team_pct": round(team_pct, 1)
                     if team_pct is not None else None,
                     "roles": rows, "best": best, "worst": worst,
                     "verdict": verdict}
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
        verdict = (f"a(z) {top['from']} → {top['to']} vonal a "
                   "gólpassz-tengelyük") if top else None
        out[side] = {"pairs_total": total, "pairs": pairs, "top": top,
                     "verdict": verdict}
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


# Eladás-ár poszt szerint: posztonként ennyi eladás kell az ítélethez,
# ennyi másodpercen belüli kapott gól számít büntetésnek, és e fölötti
# büntetett arány a kiemelt (támadható) poszt. A 30 mp-es ablak a
# csapat-szintű eladás-büntetéssel (defense.turnover_punishment) azonos.
RTC_MIN_TO = 4
RTC_QUICK_S = 30.0
RTC_HIGH_PCT = 35.0


def role_turnover_cost(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Eladás-ár poszt szerint: MELYIK POSZTJUK eladása kerül gólba.

    Az eladás-posztok (turnovers_by_role) azt mondják meg, melyik
    poszt ADJA el a labdát, a csapat-szintű eladás-büntetés
    (turnover_punishment) azt, mennyibe kerül összesen — ez a kettőt
    köti össze: melyik POSZT eladása után esik a leggyakrabban gyors
    kapott gól.

    Edzőileg ez a legdrágább információ, mert már gólban meg van
    fizetve: azt a posztot kell letámadni, amelyiknek az eladásai
    rendre büntetést érnek — ott a legnagyobb a hozam. Saját oldalon
    ugyanez a poszt visszarendeződését (váltás-sprint) írja elő.

    Visszatérés csapatonként: {"turnovers", "punished",
    "roles": {poszt: {"turnovers", "punished", "rate_pct"}},
    "worst": {"poszt", "turnovers", "punished", "rate_pct"} | None} —
    a "worst" akkor van kitöltve, ha az adott poszt elérte az
    RTC_MIN_TO eladást és a büntetett aránya az RTC_HIGH_PCT-t
    (kevés mintából nem ítélünk).
    """
    from .event_detection import EventType, detect_events

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = RTC_QUICK_S * fps

    events = detect_events(match, config)
    goals = [(e.t, e.team.value) for e in events if e.type == EventType.GOAL]

    tally: dict = {"home": {}, "away": {}}
    totals: dict = {"home": [0, 0], "away": [0, 0]}  # [eladás, büntetett]
    for e in events:
        if e.type != EventType.TURNOVER or e.player_id is None:
            continue
        side = e.team.value
        rec_role = roles[side].get(e.player_id)
        if rec_role is None:
            continue  # ismeretlen poszt — nem találgatunk
        other = "away" if side == "home" else "home"
        punished = any(tm == other and 0 <= t - e.t <= win
                       for (t, tm) in goals)
        rec = tally[side].setdefault(rec_role["poszt"], [0, 0])
        rec[0] += 1
        totals[side][0] += 1
        if punished:
            rec[1] += 1
            totals[side][1] += 1

    out: dict = {}
    for side in ("home", "away"):
        rows = {}
        for poszt, (n, p) in sorted(tally[side].items(),
                                    key=lambda kv: -kv[1][1]):
            rows[poszt] = {"turnovers": n, "punished": p,
                           "rate_pct": round(100.0 * p / n, 1) if n
                           else None}
        worst = None
        eligible = [(p, r) for p, r in rows.items()
                    if r["turnovers"] >= RTC_MIN_TO
                    and r["rate_pct"] is not None
                    and r["rate_pct"] >= RTC_HIGH_PCT]
        if eligible:
            poszt, r = max(eligible, key=lambda pr: pr[1]["rate_pct"])
            worst = {"poszt": poszt, "turnovers": r["turnovers"],
                     "punished": r["punished"], "rate_pct": r["rate_pct"]}
        verdict = (f"a(z) {worst['poszt']} posztjuk eladásai gólba "
                   "kerülnek") if worst else None
        out[side] = {"turnovers": totals[side][0],
                     "punished": totals[side][1],
                     "roles": rows, "worst": worst, "verdict": verdict}
    return out


# Poszt-állás: a hátrány-vödörben és a többi állásban is ennyi
# poszthoz kötött gól kell, és ekkora részarány-változás
# (százalékpont) számít érdemi elmozdulásnak.
RBS_MIN_GOALS = 4
RBS_GAP_PP = 20.0


def role_share_by_score(match: Match,
                        config: Optional[TacticsConfig] = None) -> dict:
    """Poszt-állás: MELYIK POSZTON keresztül fejeznek be HÁTRÁNYBAN.

    A poszt-váltás a szünetre (role_share_shift) az IDŐ szerinti
    átrendeződést nézi — ez az eredményjelző szerintit: minden gólnál
    megnézzük az addigi állást (hátrányban / nem hátrányban), és a
    poszthoz kötött gólok megoszlását a két helyzetben.

    Edzőileg ez feltételes, de nagyon konkrét: ha hátrányban mindent
    az átlövőikre bíznak, a szoros hajrában a 9 méteres vonalat kell
    lezárni és vállalni a beállót; ha a szélsőt keresik, a szélső
    kifutása lesz a döntő. A saját oldalon ugyanez a kérdés: nyomás
    alatt szűkül-e a befejezésünk egyetlen posztra.

    Visszatérés csapatonként: {"trailing": {poszt: gól}, "rest":
    {poszt: gól}, "trailing_total", "rest_total", "shift": {"poszt",
    "trailing_pct", "rest_pct", "gap_pp"} | None, "verdict": str |
    None} — a shift/verdict None, ha valamelyik oldalon
    RBS_MIN_GOALS-nál kevesebb poszthoz kötött gól van, vagy a
    legnagyobb elmozdulás sem éri el az RBS_GAP_PP-t.
    """
    from .event_detection import EventType, detect_events

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    events = detect_events(match, config)
    goals = [(e.t, e.team.value) for e in events
             if e.type == EventType.GOAL]

    tally: dict = {"home": [{}, {}], "away": [{}, {}]}  # [hátrány, többi]
    for e in events:
        if e.type != EventType.GOAL or e.player_id is None:
            continue
        side = e.team.value
        rec_role = roles[side].get(e.player_id)
        if rec_role is None:
            continue
        own = sum(1 for (t, tm) in goals if t < e.t and tm == side)
        opp = sum(1 for (t, tm) in goals if t < e.t and tm != side)
        bucket = 0 if own < opp else 1
        poszt = rec_role["poszt"]
        tally[side][bucket][poszt] = tally[side][bucket].get(poszt, 0) + 1

    out: dict = {}
    for side in ("home", "away"):
        trail, rest = tally[side]
        n1, n2 = sum(trail.values()), sum(rest.values())
        shift = verdict = None
        if n1 >= RBS_MIN_GOALS and n2 >= RBS_MIN_GOALS:
            best = None
            for poszt in set(trail) | set(rest):
                p1 = 100.0 * trail.get(poszt, 0) / n1
                p2 = 100.0 * rest.get(poszt, 0) / n2
                gap = p1 - p2  # mennyivel több hátrányban
                if best is None or abs(gap) > abs(best[3]):
                    best = (poszt, p1, p2, gap)
            if best is not None and abs(best[3]) >= RBS_GAP_PP:
                poszt, p1, p2, gap = best
                shift = {"poszt": poszt, "trailing_pct": round(p1, 1),
                         "rest_pct": round(p2, 1),
                         "gap_pp": round(gap, 1)}
                verdict = (f"hátrányban a(z) {poszt} viszi a befejezést"
                           if gap > 0
                           else f"hátrányban a(z) {poszt} tűnik el a "
                                "befejezésből")
        out[side] = {"trailing": dict(sorted(trail.items(),
                                             key=lambda kv: -kv[1])),
                     "rest": dict(sorted(rest.items(),
                                         key=lambda kv: -kv[1])),
                     "trailing_total": n1, "rest_total": n2,
                     "shift": shift, "verdict": verdict}
    return out


# Poszt-birtoklás: ennyi mért labdás kocka kell az ítélethez, és
# ekkora részarány fölött nevezzük egy posztra épülő játéknak.
RPS_MIN_FRAMES = 250
RPS_DOMINANT_PCT = 55.0


def role_possession_share(match: Match,
                          config: Optional[TacticsConfig] = None) -> dict:
    """Poszt-birtoklás: MELYIK POSZTNÁL van a labda a szervezett
    támadásaikban.

    A játékmester-függés (playmaker_dependency) és a tartás-idők
    (hold_time_players) a NEVEKET nézik — ez a posztot: a szervezett
    támadás kockáin megnézzük, melyik poszt birtokolja a labdát, és
    posztonként összegezzük. A poszt akkor is stabil, ha a nevek
    meccsről meccsre cserélődnek.

    Edzőileg: ha a labda idejének több mint felét egyetlen poszt
    tartja, arra a posztra érdemes nyomást tenni — a letámadás
    címzettje adott, és a játékuk megakad; ha viszont megoszlik, a
    nyomás nem térül meg, és inkább a falat kell rendezni.

    LÉNYEGES: ez a réteg NEM a lövő-hozzárendelésből dolgozik, hanem a
    kockánkénti birtoklásból — ezért a poszt-bontása közvetlenül
    mérhető, a lövő-felismerés pontosságától függetlenül.

    Visszatérés csapatonként: {"frames" (poszthoz kötött labdás
    kockák), "roles": {poszt: {"frames", "pct"}},
    "top": {"poszt", "frames", "pct"} | None, "verdict": str | None} —
    a top/verdict None RPS_MIN_FRAMES alatt, vagy ha a vezető poszt
    részaránya nem éri el az RPS_DOMINANT_PCT-t.
    """
    from .decisions import ball_holder
    from .tactics import Phase, classify_phase

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    attack_phase = {"home": Phase.HOME_ATTACK, "away": Phase.AWAY_ATTACK}

    tally: dict = {"home": {}, "away": {}}
    totals: dict = {"home": 0, "away": 0}
    for fr in match.frames:
        phase = classify_phase(fr, config)
        holder = ball_holder(fr, config)
        if holder is None or holder.role == "kapus":
            continue
        side = holder.team.value
        if phase != attack_phase[side]:
            continue  # csak a szervezett támadás számít
        rec_role = roles[side].get(holder.track_id)
        if rec_role is None:
            continue
        poszt = rec_role["poszt"]
        tally[side][poszt] = tally[side].get(poszt, 0) + 1
        totals[side] += 1

    out: dict = {}
    for side in ("home", "away"):
        n = totals[side]
        rows = {}
        for poszt, cnt in sorted(tally[side].items(), key=lambda kv: -kv[1]):
            rows[poszt] = {"frames": cnt,
                           "pct": round(100.0 * cnt / n, 1) if n else None}
        top = verdict = None
        items = list(rows.items())
        if n >= RPS_MIN_FRAMES and items:
            poszt, r = items[0]
            if r["pct"] is not None and r["pct"] >= RPS_DOMINANT_PCT:
                top = {"poszt": poszt, "frames": r["frames"],
                       "pct": r["pct"]}
                verdict = (f"a labda idejének {r['pct']:.0f}%-át a(z) "
                           f"{poszt} tartja")
        out[side] = {"frames": n, "roles": rows, "top": top,
                     "verdict": verdict}
    return out


# Poszt-passzháló: ennyi poszthoz kötött passz kell az ítélethez, és
# ekkora részarány fölött nevezzük kiszámítható labdajáratásnak.
RPM_MIN_PASSES = 20
RPM_SHARE = 30.0


def role_pass_map(match: Match,
                  config: Optional[TacticsConfig] = None) -> dict:
    """Poszt-passzháló: MELYIK VONALON jár a labda a támadásaikban.

    A gólpassz-tengely (assist_role_pairs) csak a GÓLT érő passzokat
    nézi, a passz-hálózat a NEVEKET — ez az összes passzt, posztról
    posztra. A poszt akkor is stabil, ha a nevek cserélődnek, és a
    kép sokkal sűrűbb, mint a gólpasszoké: egy meccsen több száz passz
    van, gólpassz húsz körül.

    Edzőileg: a legterheltebb vonal az, ahol az elfogás a
    legvalószínűbb — oda érdemes a kezet és a testet tenni. Ha egy
    vonal a passzok harmadát viszi, a labdajáratásuk kiszámítható, és
    a passzsáv zárása megakasztja a felépítést.

    Ez a réteg a birtokos-váltásokból dolgozik (nem a
    lövő-hozzárendelésből) — a poszt-bontása közvetlenül mérhető.

    Visszatérés csapatonként: {"passes_total", "pairs": {"A→B": db},
    "top": {"from", "to", "passes", "share_pct"} | None, "verdict":
    str | None} — a top/verdict None RPM_MIN_PASSES alatt, ha a vezető
    vonal nem éri el az RPM_SHARE-t, vagy ha holtverseny van.
    """
    from .event_detection import EventType, detect_possession_changes

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    tally: dict = {"home": {}, "away": {}}

    for e in detect_possession_changes(match, config):
        if e.type != EventType.PASS or e.player_id is None:
            continue
        receiver = (e.detail or {}).get("receiver_id")
        if receiver is None:
            continue
        side = e.team.value
        frm = roles[side].get(e.player_id)
        to = roles[side].get(receiver)
        if frm is None or to is None:
            continue  # ismeretlen poszt — nem találgatunk
        key = f"{frm['poszt']}→{to['poszt']}"
        tally[side][key] = tally[side].get(key, 0) + 1

    out: dict = {}
    for side in ("home", "away"):
        pairs = dict(sorted(tally[side].items(), key=lambda kv: -kv[1]))
        total = sum(pairs.values())
        top = verdict = None
        items = list(pairs.items())
        if total >= RPM_MIN_PASSES and items:
            key, n = items[0]
            share = 100.0 * n / total
            tie = len(items) > 1 and items[1][1] == n
            if share >= RPM_SHARE and not tie:
                frm_p, to_p = key.split("→", 1)
                top = {"from": frm_p, "to": to_p, "passes": n,
                       "share_pct": round(share, 1)}
                verdict = (f"a passzaik {share:.0f}%-a a(z) {frm_p} → "
                           f"{to_p} vonalon megy")
        out[side] = {"passes_total": total, "pairs": pairs, "top": top,
                     "verdict": verdict}
    return out


# Poszt-átvételi zóna: posztonként ennyi mért átvétel kell az
# ítélethez, és ekkora (méteres) eltérés a csapat-átlagtól számít
# érdeminek.
RRZ_MIN_RECEPTIONS = 8
RRZ_GAP_M = 1.5


def role_receive_zones(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Poszt-átvételi zóna: MILYEN MESSZE a kaputól veszi át a labdát
    az egyes posztjuk.

    A poszt-passzháló (role_pass_map) azt mondja meg, KI KINEK ad — ez
    azt, HOL kapja meg: minden passznál a FOGADÓ helyzetét mérjük a
    támadott kaputól, és posztonként átlagoljuk.

    Miért az átvétel és nem a lövés? A lövő-hozzárendelés kapu-felé
    torzít (lásd `event_detection._shooter_before`), ezért egy
    lövés-távolság poszt-bontása ma nem lenne megbízható. Az átvétel
    viszont PONTOSAN mért: a passz-esemény kockáján a fogadó ott áll,
    ahol a labdát megkapta.

    Edzőileg ez a fal magasságát és az elé állást állítja be. Ha a
    beállójuk 6 méteren kapja a labdát, az elé állás nem működik —
    testtel kell zárni a bejátszás vonalát; ha 8-on, akkor még
    megelőzhető. A hátsó soruk átvételi távolsága azt mondja meg,
    kell-e előrelépni a lövő-vonalba.

    Visszatérés csapatonként: {"receptions", "team_avg_m",
    "roles": {poszt: {"receptions", "avg_m"}},
    "closest"/"farthest": {"poszt", "receptions", "avg_m", "gap_m"} |
    None, "verdict": str | None} — a closest/farthest csak akkor van
    kitöltve, ha az adott poszt elérte az RRZ_MIN_RECEPTIONS átvételt,
    és a csapat-átlagtól legalább RRZ_GAP_M-rel eltér.
    """
    import math

    from .calibration import COURT_WIDTH_M
    from .event_detection import EventType, detect_possession_changes

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    gy = COURT_WIDTH_M / 2.0
    by_frame = {f.t: f for f in match.frames}

    tally: dict = {"home": {}, "away": {}}
    totals: dict = {"home": [0, 0.0], "away": [0, 0.0]}
    for e in detect_possession_changes(match, config):
        if e.type != EventType.PASS:
            continue
        receiver = (e.detail or {}).get("receiver_id")
        if receiver is None:
            continue
        side = e.team.value
        rec_role = roles[side].get(receiver)
        if rec_role is None:
            continue
        frame = by_frame.get(e.t)
        if frame is None:
            continue
        who = next((p for p in frame.players
                    if p.track_id == receiver), None)
        if who is None:
            continue
        goal_x = config.attacks_toward_x(e.team)
        dist = math.hypot(who.x - goal_x, who.y - gy)
        rec = tally[side].setdefault(rec_role["poszt"], [0, 0.0])
        rec[0] += 1
        rec[1] += dist
        totals[side][0] += 1
        totals[side][1] += dist

    out: dict = {}
    for side in ("home", "away"):
        n_all, sum_all = totals[side]
        team_avg = (sum_all / n_all) if n_all else None
        rows = {}
        for poszt, (n, tot) in sorted(tally[side].items(),
                                      key=lambda kv: -kv[1][0]):
            rows[poszt] = {"receptions": n, "avg_m": round(tot / n, 1)}
        closest = farthest = None
        if team_avg is not None:
            eligible = [(p, r) for p, r in rows.items()
                        if r["receptions"] >= RRZ_MIN_RECEPTIONS]
            for pick, key in (("closest", min), ("farthest", max)):
                if not eligible:
                    continue
                poszt, r = key(eligible, key=lambda pr: pr[1]["avg_m"])
                gap = r["avg_m"] - team_avg
                if abs(gap) < RRZ_GAP_M:
                    continue
                if (pick == "closest" and gap > 0) or \
                        (pick == "farthest" and gap < 0):
                    continue
                rec_pick = {"poszt": poszt,
                            "receptions": r["receptions"],
                            "avg_m": r["avg_m"], "gap_m": round(gap, 1)}
                if pick == "closest":
                    closest = rec_pick
                else:
                    farthest = rec_pick
        verdict = None
        if closest is not None:
            verdict = (f"a(z) {closest['poszt']} közel, "
                       f"{closest['avg_m']:.1f} m-en veszi át a labdát")
        elif farthest is not None:
            verdict = (f"a(z) {farthest['poszt']} messze, "
                       f"{farthest['avg_m']:.1f} m-en veszi át a labdát")
        out[side] = {"receptions": n_all,
                     "team_avg_m": round(team_avg, 1)
                     if team_avg is not None else None,
                     "roles": rows, "closest": closest,
                     "farthest": farthest, "verdict": verdict}
    return out


# Poszt-labdatartás: ennél rövidebb birtoklás csak érintés (zaj, a
# névre szóló hold_time_players-szel azonos küszöb), posztonként
# ennyi labdás szakasz kell az ítélethez, és ennyi másodperccel a
# csapat-átlag felett labdatartó egy poszt.
RHT_MIN_FRAMES = 5
RHT_MIN_HOLDS = 8
RHT_GAP_S = 0.7


def role_hold_time(match: Match,
                   config: Optional[TacticsConfig] = None) -> dict:
    """Poszt-labdatartás: MELYIK POSZTNÁL áll meg a labda.

    A poszt-birtoklás (role_possession_share) az össz-időt osztja
    posztokra — ez az EGY ÉRINTÉSRE jutó időt: minden labdás szakasz
    hosszát a birtokos posztjához írjuk. A kettő különbözik: egy poszt
    sok rövid érintéssel is vihet nagy össz-időt (az a labdajáratás),
    és kevés hosszú tartással is (az a megállás).

    A névre szóló változat (decisions.hold_time_players) a JÁTÉKOST
    nevezi meg; a poszt akkor is stabil, ha a nevek cserélődnek.

    Edzőileg: a hosszan tartó poszt a kettőzés célpontja — nála van
    idő odaérni, és nála lassul a támadásuk. Saját oldalon ugyanez a
    gyorsabb továbbítás témája: egy-két tizeddel korábbi passz egy
    egész átrendeződést ér.

    A réteg a kockánkénti birtoklásból dolgozik (nem a kapu-felé
    torzító lövő-hozzárendelésből), az érintésnyi (RHT_MIN_FRAMES
    alatti) birtoklás pedig zaj — azt nem számoljuk.

    Visszatérés csapatonként: {"holds", "team_avg_s",
    "roles": {poszt: {"holds", "avg_s"}},
    "slowest": {"poszt", "holds", "avg_s", "gap_s"} | None,
    "verdict": str | None} — a slowest/verdict None, ha a poszt nem
    érte el az RHT_MIN_HOLDS szakaszt, vagy a csapat-átlagot nem
    haladja meg RHT_GAP_S-szel.
    """
    from .decisions import ball_holder
    from .tactics import Phase, classify_phase

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    attack_phase = {"home": Phase.HOME_ATTACK, "away": Phase.AWAY_ATTACK}

    tally: dict = {"home": {}, "away": {}}
    totals: dict = {"home": [0, 0], "away": [0, 0]}  # [szakasz, kocka]
    cur_side = cur_poszt = None
    run = 0

    def _flush():
        nonlocal cur_side, cur_poszt, run
        if cur_side is not None and cur_poszt is not None \
                and run >= RHT_MIN_FRAMES:
            rec = tally[cur_side].setdefault(cur_poszt, [0, 0])
            rec[0] += 1
            rec[1] += run
            totals[cur_side][0] += 1
            totals[cur_side][1] += run
        cur_side = cur_poszt = None
        run = 0

    for fr in match.frames:
        holder = ball_holder(fr, config)
        poszt = side = None
        if holder is not None and holder.role != "kapus":
            side = holder.team.value
            if classify_phase(fr, config) == attack_phase[side]:
                rec_role = roles[side].get(holder.track_id)
                poszt = rec_role["poszt"] if rec_role else None
        if poszt is None or side != cur_side or poszt != cur_poszt:
            _flush()
            cur_side, cur_poszt = side, poszt
        if poszt is not None:
            run += 1
    _flush()

    out: dict = {}
    for side in ("home", "away"):
        n_holds, n_frames = totals[side]
        team_avg = (n_frames / n_holds / fps) if n_holds else None
        rows = {}
        for poszt, (h, f_) in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1][0]):
            rows[poszt] = {"holds": h, "avg_s": round(f_ / h / fps, 2)}
        slowest = verdict = None
        if team_avg is not None:
            eligible = [(p, r) for p, r in rows.items()
                        if r["holds"] >= RHT_MIN_HOLDS]
            if eligible:
                poszt, r = max(eligible, key=lambda pr: pr[1]["avg_s"])
                gap = r["avg_s"] - team_avg
                if gap >= RHT_GAP_S:
                    slowest = {"poszt": poszt, "holds": r["holds"],
                               "avg_s": r["avg_s"], "gap_s": round(gap, 2)}
                    verdict = (f"a(z) {poszt} tartja legtovább a labdát "
                               f"({r['avg_s']:.1f} mp/érintés)")
        out[side] = {"holds": n_holds,
                     "team_avg_s": round(team_avg, 2)
                     if team_avg is not None else None,
                     "roles": rows, "slowest": slowest,
                     "verdict": verdict}
    return out


# Poszt-eladási zóna: posztonként ennyi mért eladás kell az ítélethez,
# és ekkora (százalékpontos) eltérés a csapat-átlagtól számít érdemi
# kockázat-különbségnek.
RTZ_MIN_TO = 5
RTZ_GAP_PP = 20.0


def role_turnover_zones(match: Match,
                        config: Optional[TacticsConfig] = None) -> dict:
    """Poszt-eladási zóna: MELYIK POSZTJUK adja el a labdát a TÁMADÓ
    harmadban — vagyis kinek az eladása hív kontrát.

    A csapat-szintű eladási zónák (defense.turnover_zones) azt mondják
    meg, a csapat HOL veszíti el a labdát, az eladás-posztok
    (turnovers_by_role) azt, KI adja el — ez a kettőt köti össze: a
    támadó harmadban elvesztett labda a legveszélyesebb, mert üresen
    hagyja a védelmet a gyors indításnak.

    Az eladás-ár (role_turnover_cost) azt méri, mennyi gólba KERÜLT;
    ez azt, mennyire KOCKÁZATOS a hely, ahol elveszik — a kettő együtt
    mondja meg, hol térül meg a letámadás. Kevés meccsen az ár még
    zajos lehet, a zóna viszont már beszédes.

    A réteg a birtokos-váltásokból és a pozíciókból dolgozik (nem a
    lövő-hozzárendelésből).

    Visszatérés csapatonként: {"turnovers", "front", "team_front_pct",
    "roles": {poszt: {"turnovers", "front", "front_pct"}},
    "riskiest": {"poszt", "turnovers", "front", "front_pct",
    "gap_pp"} | None, "verdict": str | None} — a riskiest/verdict
    None, ha a poszt nem érte el az RTZ_MIN_TO eladást, vagy a
    csapat-átlagot nem haladja meg RTZ_GAP_PP-vel.
    """
    from .calibration import COURT_LENGTH_M
    from .event_detection import EventType, detect_events

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    by_frame = {f.t: f for f in match.frames}
    third = COURT_LENGTH_M / 3.0

    tally: dict = {"home": {}, "away": {}}
    totals: dict = {"home": [0, 0], "away": [0, 0]}  # [eladás, támadó harmad]
    for e in detect_events(match, config):
        if e.type != EventType.TURNOVER or e.player_id is None:
            continue
        side = e.team.value
        rec_role = roles[side].get(e.player_id)
        if rec_role is None:
            continue
        frame = by_frame.get(e.t)
        if frame is None:
            continue
        who = next((p for p in frame.players
                    if p.track_id == e.player_id), None)
        if who is None:
            continue
        goal_x = config.attacks_toward_x(e.team)
        # A TÁMADÓ harmad: a támadott kapuhoz legközelebbi harmad.
        dist_to_target = abs(who.x - goal_x)
        front = dist_to_target <= third
        rec = tally[side].setdefault(rec_role["poszt"], [0, 0])
        rec[0] += 1
        totals[side][0] += 1
        if front:
            rec[1] += 1
            totals[side][1] += 1

    out: dict = {}
    for side in ("home", "away"):
        n_all, n_front = totals[side]
        team_pct = (100.0 * n_front / n_all) if n_all else None
        rows = {}
        for poszt, (n, f_) in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1][0]):
            rows[poszt] = {"turnovers": n, "front": f_,
                           "front_pct": round(100.0 * f_ / n, 1)}
        riskiest = verdict = None
        if team_pct is not None:
            eligible = [(p, r) for p, r in rows.items()
                        if r["turnovers"] >= RTZ_MIN_TO]
            if eligible:
                poszt, r = max(eligible,
                               key=lambda pr: pr[1]["front_pct"])
                gap = r["front_pct"] - team_pct
                if gap >= RTZ_GAP_PP:
                    riskiest = {"poszt": poszt,
                                "turnovers": r["turnovers"],
                                "front": r["front"],
                                "front_pct": r["front_pct"],
                                "gap_pp": round(gap, 1)}
                    verdict = (f"a(z) {poszt} a támadó harmadban adja el "
                               f"a labdát ({r['front_pct']:.0f}%)")
        out[side] = {"turnovers": n_all, "front": n_front,
                     "team_front_pct": round(team_pct, 1)
                     if team_pct is not None else None,
                     "roles": rows, "riskiest": riskiest,
                     "verdict": verdict}
    return out
