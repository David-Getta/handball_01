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


# Poszt-lövéstávolság: posztonként ennyi mért lövés kell az ítélethez,
# és ekkora (méteres) eltérés a csapat-átlagtól számít érdeminek. A
# 2 m nagyjából egy egész lövés-zónányi különbség (9 m-es vonal vs.
# beugrás), tehát edzőileg is más döntést kíván.
RSD_MIN_SHOTS = 4
RSD_GAP_M = 2.0


def role_shot_distance(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Poszt-lövéstávolság: MELYIK POSZTJUK MILYEN MESSZIRŐL lő.

    Minden felismert lövéshez megkeressük az ELENGEDŐ játékost és a
    helyét az elengedés kockáján, majd a támadott kaputól mért
    távolságot a posztjához írjuk.

    Edzőileg ez a "meddig lépj ki" döntés. Aki rendre 11-12 méterről
    lő, arra RÁ LEHET engedni: a távoli lövés a kapusnak kedvez, és a
    kilépés helyett érdemesebb a passzsávot zárni. Aki viszont
    beugrással 7 méterre jön be, azt KI KELL zárni, mert onnan a
    kapusnak alig van esélye. A csapat-átlag önmagában keveset mond —
    a posztok közti KÜLÖNBSÉG mondja meg, kire kell másképp védekezni.

    Ez a réteg a lövő-hozzárendelésre épül, amely az elengedés
    pillanatát keresi meg (lásd `event_detection._shooter_before`) —
    a mért távolság tehát az elengedés helye, nem a becsapódásé.

    Visszatérés csapatonként: {"shots" (mért lövés), "team_avg_m",
    "roles": {poszt: {"shots", "avg_m"}}, "farthest": {"poszt",
    "shots", "avg_m", "gap_m"} | None, "closest": {...} | None,
    "verdict": str | None} — a farthest/closest/verdict None, ha a
    poszt nem érte el az RSD_MIN_SHOTS lövést, vagy a csapat-átlagtól
    való eltérése kisebb RSD_GAP_M-nél.
    """
    import math

    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    by_frame = {f.t: f for f in match.frames}

    tally: dict = {"home": {}, "away": {}}     # poszt → [db, összeg m]
    totals: dict = {"home": [0, 0.0], "away": [0, 0.0]}
    for e in detect_shots(match, config):
        if e.type not in (EventType.SHOT, EventType.GOAL):
            continue
        if e.player_id is None:
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
        # A kaputól mért TÉNYLEGES (egyenes) távolság: a szélső 6 m-es
        # lövése is messzebb van a kaputól, mint a beállóé.
        dist = math.hypot(goal_x - who.x, 10.0 - who.y)
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
        for poszt, (n, s_m) in sorted(tally[side].items(),
                                      key=lambda kv: -kv[1][0]):
            rows[poszt] = {"shots": n, "avg_m": round(s_m / n, 1)}
        farthest = closest = verdict = None
        if team_avg is not None:
            eligible = [(p, r) for p, r in rows.items()
                        if r["shots"] >= RSD_MIN_SHOTS]
            if eligible:
                p_far, r_far = max(eligible, key=lambda pr: pr[1]["avg_m"])
                if r_far["avg_m"] - team_avg >= RSD_GAP_M:
                    farthest = {"poszt": p_far, "shots": r_far["shots"],
                                "avg_m": r_far["avg_m"],
                                "gap_m": round(r_far["avg_m"] - team_avg, 1)}
                p_near, r_near = min(eligible, key=lambda pr: pr[1]["avg_m"])
                if team_avg - r_near["avg_m"] >= RSD_GAP_M:
                    closest = {"poszt": p_near, "shots": r_near["shots"],
                               "avg_m": r_near["avg_m"],
                               "gap_m": round(team_avg - r_near["avg_m"], 1)}
                if closest is not None:
                    verdict = (f"a(z) {closest['poszt']} közelről fejez be "
                               f"(átl. {closest['avg_m']:.1f} m) — őt ki "
                               f"kell zárni")
                elif farthest is not None:
                    verdict = (f"a(z) {farthest['poszt']} távolról lő "
                               f"(átl. {farthest['avg_m']:.1f} m) — rá "
                               f"lehet engedni")
        out[side] = {"shots": n_all,
                     "team_avg_m": round(team_avg, 1)
                     if team_avg is not None else None,
                     "roles": rows, "farthest": farthest,
                     "closest": closest, "verdict": verdict}
    return out


# Poszt-lövésidőzítés: posztonként ennyi mért lövés kell az ítélethez,
# és ekkora (másodperces) eltérés a csapat-átlagtól számít érdeminek.
# A 4 mp nagyjából egy támadás-fázisnyi különbség (első hullám vs.
# felállt támadás), tehát más védekezési készenlétet kíván.
RST_MIN_SHOTS = 4
RST_GAP_S = 4.0


def role_shot_timing(match: Match,
                     config: Optional[TacticsConfig] = None) -> dict:
    """Poszt-lövésidőzítés: MELYIK POSZTJUK MIKOR fejez be a támadáson
    belül.

    A csapat-szintű lövés-időzítés (attack_types.shot_timing) azt
    mondja meg, korán vagy kivárva lőnek — ez azt, KI lő korán és ki
    kivárva. Minden lövéshez megkeressük a támadás-szakasz kezdetét, és
    az addig eltelt időt az ELENGEDŐ játékos posztjához írjuk.

    Edzőileg ez a KÉSZENLÉT beosztása. Aki az első pár másodpercben
    fejez be, az a visszarendeződés hibájából él: ellene a
    visszafutásnál kell embert rendelni hozzá. Aki a támadás végén lő,
    az a felállt fal megfáradását várja ki: ellene a húsz másodperc
    utáni koncentráció és a passzív-jel előtti utolsó labda a kérdés.
    Ugyanaz a fal nem tud mindkettőre egyszerre készülni — ezért kell
    tudni, melyik posztjuk melyik.

    Visszatérés csapatonként: {"shots" (mért lövés), "team_avg_s",
    "roles": {poszt: {"shots", "avg_s"}}, "earliest": {"poszt",
    "shots", "avg_s", "gap_s"} | None, "latest": {...} | None,
    "verdict": str | None} — az earliest/latest/verdict None, ha a
    poszt nem érte el az RST_MIN_SHOTS lövést, vagy a csapat-átlagtól
    való eltérése kisebb RST_GAP_S-nél.
    """
    from .attack_types import ATTACK_TAIL_S, segment_attacks
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    tail = round(ATTACK_TAIL_S * fps)
    roles = estimate_positions(match, config)
    segs = segment_attacks(match, config)

    tally: dict = {"home": {}, "away": {}}     # poszt → [db, összeg mp]
    totals: dict = {"home": [0, 0.0], "away": [0, 0.0]}
    for e in detect_shots(match, config):
        if e.type not in (EventType.SHOT, EventType.GOAL):
            continue
        if e.player_id is None:
            continue
        side = e.team.value
        rec_role = roles[side].get(e.player_id)
        if rec_role is None:
            continue
        # A lövés a szakaszon belül vagy közvetlenül utána csapódik le
        # (mint a csapat-szintű lövés-időzítésnél).
        seg = next((s_ for s_ in segs
                    if s_.team == e.team
                    and s_.start_t <= e.t <= s_.end_t + tail), None)
        if seg is None:
            continue
        dt = (e.t - seg.start_t) / fps
        rec = tally[side].setdefault(rec_role["poszt"], [0, 0.0])
        rec[0] += 1
        rec[1] += dt
        totals[side][0] += 1
        totals[side][1] += dt

    out: dict = {}
    for side in ("home", "away"):
        n_all, sum_all = totals[side]
        team_avg = (sum_all / n_all) if n_all else None
        rows = {}
        for poszt, (n, s_s) in sorted(tally[side].items(),
                                      key=lambda kv: -kv[1][0]):
            rows[poszt] = {"shots": n, "avg_s": round(s_s / n, 1)}
        earliest = latest = verdict = None
        if team_avg is not None:
            eligible = [(p, r) for p, r in rows.items()
                        if r["shots"] >= RST_MIN_SHOTS]
            if eligible:
                p_e, r_e = min(eligible, key=lambda pr: pr[1]["avg_s"])
                if team_avg - r_e["avg_s"] >= RST_GAP_S:
                    earliest = {"poszt": p_e, "shots": r_e["shots"],
                                "avg_s": r_e["avg_s"],
                                "gap_s": round(team_avg - r_e["avg_s"], 1)}
                p_l, r_l = max(eligible, key=lambda pr: pr[1]["avg_s"])
                if r_l["avg_s"] - team_avg >= RST_GAP_S:
                    latest = {"poszt": p_l, "shots": r_l["shots"],
                              "avg_s": r_l["avg_s"],
                              "gap_s": round(r_l["avg_s"] - team_avg, 1)}
                if earliest is not None:
                    verdict = (f"a(z) {earliest['poszt']} korán fejez be "
                               f"(átl. {earliest['avg_s']:.1f} mp) — a "
                               "visszarendeződésnél kell rá ember")
                elif latest is not None:
                    verdict = (f"a(z) {latest['poszt']} a támadás végén "
                               f"lő (átl. {latest['avg_s']:.1f} mp) — a "
                               "kivárt labdára kell koncentrálni")
        out[side] = {"shots": n_all,
                     "team_avg_s": round(team_avg, 1)
                     if team_avg is not None else None,
                     "roles": rows, "earliest": earliest,
                     "latest": latest, "verdict": verdict}
    return out


# Poszt-lövéserő: posztonként ennyi mért lövés kell az ítélethez, és
# ekkora (km/h) eltérés a csapat-átlagtól számít érdeminek. A 12 km/h
# nagyjából egy kapus-reakciónyi különbség a hat méteren.
RSP_MIN_SHOTS = 4
RSP_GAP_KMH = 12.0


def role_shot_power(match: Match,
                    config: Optional[TacticsConfig] = None) -> dict:
    """Poszt-lövéserő: MELYIK POSZTJUK LŐ KEMÉNYEN.

    A lövő-erő (event_detection.shooter_power) NÉVRE mondja meg, ki a
    bombázó — ez posztra. A név meccsről meccsre cserélődhet (sérülés,
    csere, más felállás), a poszt viszont marad: a kapus felkészítése
    ezért poszt-alapon tart.

    Edzőileg: a kemény lövésre a kapusnak KORÁBBAN kell indulnia és
    inkább a szöget kell zárnia, mint reagálnia; a helyezett (lassabb)
    lövésnél fordítva — ott a kivárás fizet. A fal ugyanezt a döntést
    hozza: a bombázó poszttal szemben szöget zárni, a helyezővel
    szemben a kezet fent tartani. Ha nem tudjuk, melyik posztjuk
    melyik, a kapus mindkettőre félig készül.

    Visszatérés csapatonként: {"shots" (mért lövés), "team_avg_kmh",
    "roles": {poszt: {"shots", "avg_kmh"}}, "hardest": {"poszt",
    "shots", "avg_kmh", "gap_kmh"} | None, "verdict": str | None} — a
    hardest/verdict None, ha a poszt nem érte el az RSP_MIN_SHOTS
    lövést, vagy a csapat-átlagot nem haladja meg RSP_GAP_KMH-val.
    """
    from .event_detection import shot_speeds

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    speeds = shot_speeds(match, config)

    tally: dict = {"home": {}, "away": {}}     # poszt → [db, összeg km/h]
    totals: dict = {"home": [0, 0.0], "away": [0, 0.0]}
    for s_ in speeds["shots"]:
        side = s_["team"]
        pid = s_["player_id"]
        if side not in tally or pid is None:
            continue
        rec_role = roles[side].get(pid)
        if rec_role is None:
            continue
        rec = tally[side].setdefault(rec_role["poszt"], [0, 0.0])
        rec[0] += 1
        rec[1] += s_["speed_kmh"]
        totals[side][0] += 1
        totals[side][1] += s_["speed_kmh"]

    out: dict = {}
    for side in ("home", "away"):
        n_all, sum_all = totals[side]
        team_avg = (sum_all / n_all) if n_all else None
        rows = {}
        for poszt, (n, s_k) in sorted(tally[side].items(),
                                      key=lambda kv: -kv[1][0]):
            rows[poszt] = {"shots": n, "avg_kmh": round(s_k / n, 1)}
        hardest = verdict = None
        if team_avg is not None:
            eligible = [(p, r) for p, r in rows.items()
                        if r["shots"] >= RSP_MIN_SHOTS]
            if eligible:
                poszt, r = max(eligible, key=lambda pr: pr[1]["avg_kmh"])
                gap = r["avg_kmh"] - team_avg
                if gap >= RSP_GAP_KMH:
                    hardest = {"poszt": poszt, "shots": r["shots"],
                               "avg_kmh": r["avg_kmh"],
                               "gap_kmh": round(gap, 1)}
                    verdict = (f"a(z) {poszt} lő a legkeményebben "
                               f"(átl. {r['avg_kmh']:.0f} km/h) — ellene "
                               "a kapus korábban induljon, a fal szöget "
                               "zárjon")
        out[side] = {"shots": n_all,
                     "team_avg_kmh": round(team_avg, 1)
                     if team_avg is not None else None,
                     "roles": rows, "hardest": hardest, "verdict": verdict}
    return out


# Poszt-kapuoldal: posztonként ennyi mért gól kell az ítélethez, és
# ekkora részarány számít kiszámíthatónak. A 60% azt jelenti, hogy
# minden ötödik-hatodik gólból három-négy ugyanoda megy — a kapus
# ennyiből már érdemben ráállhat az oldalra.
RGP_MIN_GOALS = 4
RGP_SHARE_PCT = 60.0


def role_goal_placement(match: Match,
                        config: Optional[TacticsConfig] = None) -> dict:
    """Poszt-kapuoldal: MELYIK POSZTJUK MELYIK SARKOT keresi.

    A lövő-kapuoldal (attack_types.shooter_placement) NÉVRE mondja meg,
    ki kiszámítható — ez posztra. A név cserélődhet (sérülés, csere, más
    felállás), a poszt viszont marad: a kapus felkészítése ezért
    poszt-alapon tart, akkor is, ha az ellenfél mást állít be.

    Edzőileg: ha egy posztjuk a góljainak nagy részét ugyanabba a
    sarokba lövi, a kapus arra az oldalra állhat rá, a fal pedig a
    másikat zárja. Ez a poszt-lencse utolsó darabja a kapus-felkészítés
    három kérdésében: MILYEN MESSZIRŐL (role_shot_distance), MILYEN
    KEMÉNYEN (role_shot_power) és MOST MÁR: HOVA.

    Az oldalt a LÖVŐ szemszögéből adjuk meg (a két kaput tükrözzük),
    ahogy a lövő-kapuoldal réteg is — így a két réteg olvasata azonos.

    Visszatérés csapatonként: {"goals" (mért gól), "roles": {poszt:
    {"goals", "bal", "közép", "jobb", "dominant", "share_pct"}},
    "predictable": {"poszt", "goals", "dominant", "share_pct"} | None,
    "verdict": str | None} — a predictable/verdict None, ha a poszt nem
    érte el az RGP_MIN_GOALS gólt, vagy egyik oldal sem éri el az
    RGP_SHARE_PCT részarányt.
    """
    from .attack_types import shooter_placement

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    placement = shooter_placement(match, config)

    out: dict = {}
    for side in ("home", "away"):
        tally: dict = {}
        total = 0
        for p in placement[side]["players"]:
            rec_role = roles[side].get(p["player_id"])
            if rec_role is None:
                continue
            row = tally.setdefault(rec_role["poszt"],
                                   {"bal": 0, "közép": 0, "jobb": 0})
            for k in ("bal", "közép", "jobb"):
                row[k] += p[k]
                total += p[k]

        rows = {}
        for poszt, row in sorted(tally.items(),
                                 key=lambda kv: -(kv[1]["bal"]
                                                  + kv[1]["közép"]
                                                  + kv[1]["jobb"])):
            goals = row["bal"] + row["közép"] + row["jobb"]
            dom = max(("bal", "közép", "jobb"), key=lambda k: row[k])
            rows[poszt] = {
                "goals": goals, **row,
                "dominant": dom if goals >= RGP_MIN_GOALS else None,
                "share_pct": (round(100.0 * row[dom] / goals, 1)
                              if goals >= RGP_MIN_GOALS else None),
            }

        predictable = verdict = None
        best = [(p, r) for p, r in rows.items()
                if r["share_pct"] is not None
                and r["share_pct"] >= RGP_SHARE_PCT]
        if best:
            poszt, r = max(best, key=lambda pr: pr[1]["share_pct"])
            predictable = {"poszt": poszt, "goals": r["goals"],
                           "dominant": r["dominant"],
                           "share_pct": r["share_pct"]}
            verdict = (f"a(z) {poszt} a góljai {r['share_pct']:.0f}%-át "
                       f"{r['dominant']} oldalra lövi — a kapus arra "
                       "állhat rá, a fal a másikat zárja")
        out[side] = {"goals": total, "roles": rows,
                     "predictable": predictable, "verdict": verdict}
    return out


# Poszt-nyomás: posztonként ennyi FEDEZETT lövés kell az ítélethez, és
# ekkora (százalékpontos) eltérés a csapat fedezett gólarányától
# számít érdeminek. A 20 százalékpont nagyjából minden ötödik fedezett
# lövés — ennyi már átírja, kire szabad rálépni és kit kell kizárni.
RPF_MIN_SHOTS = 4
RPF_GAP_PCT = 20.0


def role_pressure_finish(match: Match,
                         config: Optional[TacticsConfig] = None) -> dict:
    """Poszt-nyomás: MELYIK POSZTJUK FEJEZ BE FEDEZETTEN IS.

    A csapat-szintű nyomás alatti befejezés (defense.pressure_finishing)
    azt mondja meg, mennyit ér a fedezés a csapat ellen — ez azt, KIN
    fog. Minden felismert lövéshez megkeressük az ELENGEDŐ játékost, és
    az elengedés kockáján a legközelebbi MEZŐNY-védő távolságát: a
    FREE_DEF_RADIUS_M-en belüli lövés fedezett, a távolabbi szabad. A
    fedezett lövések gólarányát a lövő posztjához írjuk.

    Edzőileg ez a KIRE LÉPJ KI döntés. Aki fedezetten is belövi, azt
    nem elég "megzavarni": ellene KIZÁRÁS kell — a labdát ne is kapja
    meg, mert a kinyújtott kéz nála nem elég. Aki viszont fedezetten
    beesik, azt épp rá kell engedni: nála a nyomás önmagában megoldja a
    helyzetet, és a fal nem szakad szét egy fölösleges kettőzésben.
    Ugyanaz a fal nem tud mindenkire kilépni — ez a réteg mondja meg,
    kire érdemes.

    Visszatérés csapatonként: {"shots" (mért lövés), "covered_shots",
    "team_covered_pct", "roles": {poszt: {"covered_shots",
    "covered_goals", "covered_pct", "free_shots", "free_goals"}},
    "coldblooded": {"poszt", "covered_shots", "covered_pct",
    "gap_pct"} | None, "pressure_shy": {...} | None, "verdict": str |
    None} — a coldblooded/pressure_shy/verdict None, ha a poszt nem
    érte el az RPF_MIN_SHOTS fedezett lövést, vagy az eltérése kisebb
    RPF_GAP_PCT-nél.
    """
    import math

    from ..models.tracking import Team
    from .defense import FREE_DEF_RADIUS_M
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    by_frame = {f.t: f for f in match.frames}

    # poszt → [fedezett lövés, fedezett gól, szabad lövés, szabad gól]
    tally: dict = {"home": {}, "away": {}}
    totals: dict = {"home": [0, 0, 0], "away": [0, 0, 0]}  # lövés, fed, fed-gól
    for e in detect_shots(match, config):
        if e.type not in (EventType.SHOT, EventType.GOAL):
            continue
        if e.player_id is None:
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
        defender_team = Team.AWAY if e.team == Team.HOME else Team.HOME
        # A kapus nem számít fedezésnek: a mezőnyvédő közelsége az,
        # ami a lövés szögét és a karmunkát zavarja.
        dists = [math.hypot(p.x - who.x, p.y - who.y)
                 for p in frame.players
                 if p.team == defender_team and p.role != "kapus"]
        if not dists:
            continue
        covered = min(dists) <= FREE_DEF_RADIUS_M
        rec = tally[side].setdefault(rec_role["poszt"], [0, 0, 0, 0])
        goal = e.type == EventType.GOAL
        if covered:
            rec[0] += 1
            rec[1] += 1 if goal else 0
            totals[side][1] += 1
            totals[side][2] += 1 if goal else 0
        else:
            rec[2] += 1
            rec[3] += 1 if goal else 0
        totals[side][0] += 1

    out: dict = {}
    for side in ("home", "away"):
        n_all, n_cov, g_cov = totals[side]
        team_pct = (100.0 * g_cov / n_cov) if n_cov else None
        rows = {}
        for poszt, (cs, cg, fs, fg) in sorted(
                tally[side].items(), key=lambda kv: -(kv[1][0] + kv[1][2])):
            rows[poszt] = {
                "covered_shots": cs, "covered_goals": cg,
                "covered_pct": round(100.0 * cg / cs, 1) if cs else None,
                "free_shots": fs, "free_goals": fg}
        cold = shy = verdict = None
        if team_pct is not None:
            eligible = [(p, r) for p, r in rows.items()
                        if r["covered_shots"] >= RPF_MIN_SHOTS]
            if eligible:
                p_c, r_c = max(eligible, key=lambda pr: pr[1]["covered_pct"])
                if r_c["covered_pct"] - team_pct >= RPF_GAP_PCT:
                    cold = {"poszt": p_c,
                            "covered_shots": r_c["covered_shots"],
                            "covered_pct": r_c["covered_pct"],
                            "gap_pct": round(r_c["covered_pct"] - team_pct, 1)}
                p_s, r_s = min(eligible, key=lambda pr: pr[1]["covered_pct"])
                if team_pct - r_s["covered_pct"] >= RPF_GAP_PCT:
                    shy = {"poszt": p_s,
                           "covered_shots": r_s["covered_shots"],
                           "covered_pct": r_s["covered_pct"],
                           "gap_pct": round(team_pct - r_s["covered_pct"], 1)}
                if cold is not None:
                    verdict = (f"a(z) {cold['poszt']} fedezetten is "
                               f"befejez ({cold['covered_pct']:.0f}% "
                               f"{cold['covered_shots']} fedezett "
                               "lövésből) — őt ki kell zárni, a puszta "
                               "kilépés nála kevés")
                elif shy is not None:
                    verdict = (f"a(z) {shy['poszt']} fedezetten beesik "
                               f"({shy['covered_pct']:.0f}% "
                               f"{shy['covered_shots']} fedezett "
                               "lövésből) — rá érdemes kilépni, a "
                               "nyomás nála megoldja a helyzetet")
        out[side] = {"shots": n_all, "covered_shots": n_cov,
                     "team_covered_pct": round(team_pct, 1)
                     if team_pct is not None else None,
                     "roles": rows, "coldblooded": cold,
                     "pressure_shy": shy, "verdict": verdict}
    return out


# Kontra-poszt: ennyi poszthoz kötött kontra-lövés kell az ítélethez,
# és ekkora részarány számít kiszámíthatónak. A lerohanás ritkább, mint
# a felállt támadás, ezért a küszöb alacsonyabb — a felderítésben
# meccsek közt összegződik.
RFB_MIN_SHOTS = 3
RFB_SHARE_PCT = 60.0


def role_fast_breaks(match: Match,
                     config: Optional[TacticsConfig] = None) -> dict:
    """Kontra-poszt: MELYIK POSZTJUK FUT KI a lerohanásokon.

    A kontra-befejezők rétege (attack_types.fast_break_finishers) a
    GÓLT szerző EMBERT nevezi meg — ez a posztot, és nemcsak a gólnál:
    a lerohanás-szakaszokra eső MINDEN lövést az elengedő játékos
    posztjához írja.

    Edzőileg ez a visszafutás sorrendje. Visszarendeződéskor nem lehet
    mindenkit egyszerre felvenni — azt kell először, aki a kontrát
    ténylegesen befejezi. Ha a lerohanásaik rendre ugyanarról a
    posztról záródnak (tipikusan a szélső), a visszafutásnál őt kell
    kijelölt embernek adni, a többiek ráérnek egy ütemmel később. Ha a
    kontra-befejezésük szórt, a visszafutásban a LABDÁT kell késleltetni
    (a felhozó emberre ráállni), nem a befejezőt keresni.

    Visszatérés csapatonként: {"breaks" (lerohanás-szakasz), "shots"
    (poszthoz kötött kontra-lövés), "roles": {poszt: lövés},
    "main_role", "share_pct", "verdict"} — a main_role/share_pct/
    verdict None, ha nincs meg az RFB_MIN_SHOTS lövés, vagy egyik poszt
    sem éri el az RFB_SHARE_PCT részarányt.
    """
    from .attack_types import (ATTACK_TAIL_S, AttackType,
                               classify_attacks)
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    tail = round(ATTACK_TAIL_S * fps)
    roles = estimate_positions(match, config)
    shots = [e for e in detect_shots(match, config)
             if e.type in (EventType.SHOT, EventType.GOAL)
             and e.player_id is not None]

    out: dict = {side: {"breaks": 0, "shots": 0, "roles": {},
                        "main_role": None, "share_pct": None,
                        "verdict": None} for side in ("home", "away")}
    for a in classify_attacks(match, config):
        if a["type"] != AttackType.FAST_BREAK.value:
            continue
        side = a["team"]
        rec = out[side]
        rec["breaks"] += 1
        for e in shots:
            if e.team.value != side or not (
                    a["start_frame"] <= e.t <= a["end_frame"] + tail):
                continue
            rec_role = roles[side].get(e.player_id)
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1
            rec["shots"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["shots"] >= RFB_MIN_SHOTS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["shots"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= RFB_SHARE_PCT:
                rec["verdict"] = (
                    f"a lerohanásaik a(z) {poszt} poszton záródnak "
                    f"({share:.0f}%, {rec['shots']} kontra-lövésből) — "
                    "visszafutásnál őt kell először felvenni, a "
                    "többiek egy ütemmel ráérnek")
    return out


# Gólpassz-poszt: ennyi poszthoz kötött gólpassz kell az ítélethez, és
# ekkora részarány fölött mondjuk ki, hogy a gólgyártásuk egy poszt
# kezéből indul.
RAS_MIN_ASSISTS = 3
RAS_SHARE_PCT = 60.0


def role_assist_sources(match: Match,
                        config: Optional[TacticsConfig] = None) -> dict:
    """Gólpassz-poszt: MELYIK POSZTJUK KEZÉBŐL indulnak a góljaik.

    A gólpassz-forrás (attack_types.assist_sources) a pálya-ZÓNÁT nézi
    (szél/közép/hátsó), a gólpassz-hálózat az embert — ez a POSZTOT: a
    gólokhoz rendelt gólpasszokat az adó játékos posztjához írja.

    Edzőileg ez a védekezés célpont-váltása. A befejező-lencse
    megmondja, KI fejez be — de ha a gólok nagy része ugyanannak a
    posztnak a kezéből INDUL (tipikusan az irányító), a lövés zárása
    késő: tőle a PASSZT kell elvenni. A fal egy emberrel feljebb lép rá,
    a többiek posztot tartanak — a lövők maguktól elhalkulnak, ha nem
    kapnak labdát helyzetben.

    Visszatérés csapatonként: {"assists" (poszthoz kötött gólpassz),
    "roles": {poszt: gólpassz}, "main_role", "share_pct", "verdict"} —
    a main_role/share_pct/verdict None, ha nincs meg a RAS_MIN_ASSISTS,
    vagy egyik poszt sem éri el a RAS_SHARE_PCT részarányt.
    """
    from .event_detection import EventType, detect_events

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)

    out: dict = {side: {"assists": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
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
        poszt = rec_role["poszt"]
        rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1
        rec["assists"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["assists"] >= RAS_MIN_ASSISTS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["assists"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= RAS_SHARE_PCT:
                rec["verdict"] = (
                    f"a góljaik a(z) {poszt} kezéből indulnak "
                    f"({share:.0f}%, {rec['assists']} gólpasszból) — "
                    "nem a lövést kell zárni, hanem TŐLE a passzt "
                    "elvenni: egy ember feljebb lép rá, a többiek "
                    "posztot tartanak")
    return out


# Kiszolgált-poszt: ennyi poszthoz kötött asszisztos gól kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy a
# kiszolgált gólokat egy poszt fejezi be.
ASR_MIN_ASSISTED = 3
ASR_SHARE_PCT = 60.0


def assisted_scorer_roles(match: Match,
                          config: Optional[TacticsConfig] = None
                          ) -> dict:
    """Kiszolgált-poszt: MELYIK POSZTJUK fejezi be a bejátszásokat.

    A gólpassz-poszt (role_assist_sources) azt mondja meg, kinek a
    kezéből INDUL a gól — ez azt, hova ÉRKEZIK: a gólpasszos
    (asszisztált) gólokat a BEFEJEZŐ posztjához írja. Így a minta
    akkor is látszik, ha a nevek meccsről meccsre cserélődnek.

    Edzőileg ez a passzsáv-zárás címzettje: a kiszolgálásból élő
    posztot nem fogni kell, hanem éheztetni — a felé futó passzt
    elvágni (sávzárás, előrelépő védő), és ő magától elhal, mert
    egyénileg nem teremt helyzetet. Saját csapatra: ha egy posztunk
    csak kiszolgálásból él, a bejátszó emberének kiesésekor tervre
    van szüksége.

    Visszatérés csapatonként: {"assisted" (poszthoz kötött
    asszisztos gól), "roles": {poszt: darab}, "main_role",
    "share_pct", "verdict"} — az ítélet None, ha nincs meg az
    ASR_MIN_ASSISTED, vagy egyik poszt sem éri el az
    ASR_SHARE_PCT-t.
    """
    from .event_detection import EventType, detect_events

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)

    out: dict = {side: {"assisted": 0, "roles": {},
                        "main_role": None, "share_pct": None,
                        "verdict": None}
                 for side in ("home", "away")}
    for e in detect_events(match, config):
        if e.type != EventType.GOAL or e.player_id is None:
            continue
        if not (e.detail or {}).get("assist_id"):
            continue
        side = getattr(e.team, "value", e.team)
        rec_role = roles[side].get(e.player_id)
        if rec_role is None:
            continue
        poszt = rec_role["poszt"]
        rec = out[side]
        rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1
        rec["assisted"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["assisted"] >= ASR_MIN_ASSISTED:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["assisted"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= ASR_SHARE_PCT:
                rec["verdict"] = (
                    f"a kiszolgált góljaik {share:.0f}%-át a(z) "
                    f"{poszt} posztjuk fejezi be ({rec['assisted']} "
                    "asszisztos gólból) — őt nem fogni kell, hanem "
                    "éheztetni: a felé futó passz elvágásával "
                    "magától elhal")
    return out


# Kiszolgált befejezők: ennyi bejátszásból esett gól kell a névhez,
# és ekkora részarány fölött mondjuk ki, hogy ő kiszolgálásból él.
ASP_MIN_ASSISTED = 3
ASP_SHARE_PCT = 60.0


def assisted_scorers(match: Match,
                     config: Optional[TacticsConfig] = None) -> dict:
    """Kiszolgált befejezők: KI él a bejátszásokból.

    A kiszolgált-poszt (assisted_scorer_roles) a POSZTOT nevezi meg —
    ez az EMBERT: minden gólnál megnézi, volt-e gólpassz, és a
    befejező nevéhez írja a gólt (kiszolgáltként vagy sajátként).

    Edzőileg ez dönti el, mit kell ellene tenni. Aki a góljai nagy
    részét bejátszásból szerzi, azt nem fogni kell, hanem éheztetni:
    a felé futó passzt elvágni (sávzárás, előrelépő védő) — ő
    egyénileg nem teremt helyzetet. Aki maga teremt, ott a passz
    elvágása keveset ér: oda emberfogás vagy kettőzés kell. Saját
    csapatra: aki csak kiszolgálásból él, a bejátszó emberének
    kiesésekor tervre szorul.

    Visszatérés csapatonként: {"assisted", "players": [{"player_id",
    "jersey", "assisted", "goals"}], "top"} — a lista kiszolgált gól
    szerint csökkenő; a "top" az első játékos, ha legalább
    ASP_MIN_ASSISTED kiszolgált gólja van, és ezek a góljainak
    legalább ASP_SHARE_PCT-át adják, különben None.
    """
    from .event_detection import EventType, detect_events

    config = config or TacticsConfig()

    jersey: dict = {}
    for f in match.frames:
        for p in f.players:
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)

    tally: dict = {"home": {}, "away": {}}
    for e in detect_events(match, config):
        if e.type != EventType.GOAL or e.player_id is None:
            continue
        side = getattr(e.team, "value", e.team)
        if side not in tally:
            continue
        rec = tally[side].setdefault(e.player_id, {"assisted": 0,
                                                   "goals": 0})
        rec["goals"] += 1
        if (e.detail or {}).get("assist_id"):
            rec["assisted"] += 1

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "assisted": r["assisted"], "goals": r["goals"]}
                for pid, r in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1]["assisted"])]
        top = None
        if rows and rows[0]["assisted"] >= ASP_MIN_ASSISTED:
            share = 100.0 * rows[0]["assisted"] / max(1, rows[0]["goals"])
            if share >= ASP_SHARE_PCT:
                top = rows[0]
        out[side] = {"assisted": sum(r["assisted"] for r in rows),
                     "players": rows, "top": top}
    return out


# Indító-poszt: ennyi poszthoz kötött támadás-indítás kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy a
# szervezésük egy posztnál indul.
ATS_MIN_ATTACKS = 5
ATS_SHARE_PCT = 60.0


def attack_starter_roles(match: Match,
                         config: Optional[TacticsConfig] = None
                         ) -> dict:
    """Indító-poszt: MELYIK POSZTJUKNÁL indul a támadás-szervezés.

    A támadás-szakaszok (segment_attacks) a szakaszt adják — ez a
    posztot: minden szakasz ELSŐ labdabirtokosát megkeresi, és a
    szakaszt az ő posztjához írja. Így látszik, kinek a kezén indul
    a szervezésük, akkor is, ha a nevek meccsről meccsre cserélődnek.

    Edzőileg ez a korai pressz címzettje: ha a támadásaik rendre
    ugyanannál a posztnál indulnak, a felhozatalt őt presszingelve
    lehet borítani — korai nyomás rá már a felezőnél, és a
    szervezésük el sem kezdődik. Saját csapatra: kell a második
    labdafelhozó, különben egy jó pressz megfojt minket.

    Visszatérés csapatonként: {"attacks" (poszthoz kötött indítás),
    "roles": {poszt: darab}, "main_role", "share_pct", "verdict"} —
    az ítélet None, ha nincs meg az ATS_MIN_ATTACKS, vagy egyik
    poszt sem éri el az ATS_SHARE_PCT-t.
    """
    from .decisions import ball_holder
    from .setplays import segment_attacks

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)

    out: dict = {side: {"attacks": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for seq in segment_attacks(match, config):
        side = seq.team.value
        starter = None
        for f in seq.frames:
            h = ball_holder(f, config)
            if h is not None and h.team == seq.team \
                    and h.role != "kapus":
                starter = h.track_id
                break
        if starter is None:
            continue
        rec_role = roles[side].get(starter)
        if rec_role is None:
            continue
        poszt = rec_role["poszt"]
        rec = out[side]
        rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1
        rec["attacks"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["attacks"] >= ATS_MIN_ATTACKS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["attacks"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= ATS_SHARE_PCT:
                rec["verdict"] = (
                    f"a támadásaik {share:.0f}%-a a(z) {poszt} "
                    f"posztnál indul ({rec['attacks']} szakaszból) —"
                    " a felhozatalt őt presszingelve lehet borítani:"
                    " korai nyomás rá már a felezőnél, és a "
                    "szervezésük el sem kezdődik")
    return out


# Gólpasszpáros-poszt: ennyi poszthoz kötött asszisztos gól kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy a góljaik
# egy (adó → befejező) posztpáron születnek.
APR_MIN_GOALS = 3
APR_SHARE_PCT = 60.0


def assist_pair_roles(match: Match,
                      config: Optional[TacticsConfig] = None) -> dict:
    """Gólpasszpáros-poszt: MELYIK TENGELYEN születnek a góljaik.

    A gólpassz-poszt az adót, a kiszolgált-poszt a befejezőt nevezi
    meg — ez a kettőt köti össze gólonként: az asszisztos gólokat az
    (adó poszt → befejező poszt) párhoz írja. A bejáratott
    gól-tengely akkor is látszik, ha a nevek cserélődnek.

    Edzőileg ez a tengely-vágás terve: a bejáratott adó-befejező
    kettős közti passzsáv a fal első számú zárnivalója — az adót
    testtel, a sávot beleéréssel, és a gól-gépezetük áll. Saját
    csapatra: a tengely kiszámíthatósága ellen második befejező-út
    kell.

    Visszatérés csapatonként: {"goals" (párhoz kötött asszisztos
    gól), "roles": {"adó→befejező": darab}, "main_role",
    "share_pct", "verdict"} — az ítélet None, ha nincs meg az
    APR_MIN_GOALS, vagy egyik pár sem éri el az APR_SHARE_PCT-t.
    """
    from .event_detection import EventType, detect_events

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)

    out: dict = {side: {"goals": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for e in detect_events(match, config):
        if e.type != EventType.GOAL or e.player_id is None:
            continue
        aid = (e.detail or {}).get("assist_id")
        if aid is None:
            continue
        side = getattr(e.team, "value", e.team)
        r_a = roles[side].get(aid)
        r_s = roles[side].get(e.player_id)
        if r_a is None or r_s is None:
            continue
        kulcs = f"{r_a['poszt']}→{r_s['poszt']}"
        rec = out[side]
        rec["roles"][kulcs] = rec["roles"].get(kulcs, 0) + 1
        rec["goals"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["goals"] >= APR_MIN_GOALS:
            par = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][par] / rec["goals"]
            rec["main_role"] = par
            rec["share_pct"] = round(share, 1)
            if share >= APR_SHARE_PCT:
                rec["verdict"] = (
                    f"a góljaik a(z) {par} tengelyen születnek "
                    f"({share:.0f}%, {rec['goals']} asszisztos "
                    "gólból) — a kettős közti passzsáv a fal első "
                    "számú zárnivalója: az adót testtel, a sávot "
                    "beleéréssel")
    return out


# Specialista-poszt: ennyi mért JELENLÉT (játékos-másodperc) kell
# posztonként az ítélethez, ennyi kell a csapatnak MINDKÉT fázisban
# (különben egy fél-támadásnyi klip is 100%-ot mutatna), és ekkora
# egyoldalúság fölött mondjuk ki, hogy a posztot váltott sorban
# (csak védekezésre vagy csak támadásra) használják.
SPC_MIN_S = 120.0
SPC_MIN_PHASE_S = 60.0
SPC_SPEC_PCT = 80.0


def specialist_roles(match: Match,
                     config: Optional[TacticsConfig] = None) -> dict:
    """Specialista-poszt: MELYIK POSZTOT játsszák váltott sorban.

    Az egyirányú játékosok rétege (phase_specialists) az embert
    nevezi meg — ez a posztot: a fázis-besorolt (labdabirtokos
    melletti) kockákat posztonként összegzi, és megnézi, melyik
    poszt tölti az idejét szinte csak védekezésben vagy szinte csak
    támadásban. Így a váltott sor akkor is látszik, ha a nevek
    meccsről meccsre cserélődnek.

    Edzőileg ez a csere-pillanat kihasználása: a váltott sorban
    játszott poszt a labda elvesztésekor/megszerzésekor cserélődik —
    a gyors középkezdés és a szerzés utáni azonnali indítás pont
    ott talál rossz embert (vagy hiányzót) a pályán. Saját
    csapatra: a specialista-poszt cseréje idő, és a fáradó ellenfél
    ellen kockázat.

    Visszatérés csapatonként: {"seconds" (mért jelenlét,
    játékos-másodperc), "roles": {poszt: {"seconds", "def_seconds",
    "def_pct"}}, "main_role", "def_pct", "verdict"} — az ítélet
    None, ha a csapatnak nincs meg mindkét fázisban az
    SPC_MIN_PHASE_S, vagy egyik poszt sem éri el az SPC_MIN_S-t az
    SPC_SPEC_PCT-os egyoldalúsággal.
    """
    from .decisions import ball_holder
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    roles = estimate_positions(match, config)

    acc: dict = {"home": {}, "away": {}}
    for f in match.frames:
        holder = ball_holder(f, config)
        if holder is None or holder.team is None:
            continue
        for p in f.players:
            if p.role == "kapus" or p.team is None:
                continue
            rec_role = roles[p.team.value].get(p.track_id)
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec = acc[p.team.value].setdefault(poszt, [0, 0])
            rec[0] += 1
            if p.team != holder.team:
                rec[1] += 1

    out: dict = {}
    for side in ("home", "away"):
        by_role = {
            poszt: {"seconds": round(n / fps, 1),
                    "def_seconds": round(d / fps, 1),
                    "def_pct": round(100.0 * d / n, 1) if n else None}
            for poszt, (n, d) in sorted(acc[side].items(),
                                        key=lambda kv: -kv[1][0])}
        total_s = sum(r["seconds"] for r in by_role.values())
        def_s = sum(r["def_seconds"] for r in by_role.values())
        atk_s = total_s - def_s
        main_role = None
        def_pct = None
        verdict = None
        # Mindkét fázisnak meg kell lennie: egy fél-támadásnyi
        # felvételen a jelen lévő poszt triviálisan 100%-os lenne.
        if def_s >= SPC_MIN_PHASE_S and atk_s >= SPC_MIN_PHASE_S:
            cands = [(poszt, r) for poszt, r in by_role.items()
                     if r["seconds"] >= SPC_MIN_S
                     and (r["def_pct"] >= SPC_SPEC_PCT
                          or r["def_pct"] <= 100.0 - SPC_SPEC_PCT)]
            if cands:
                poszt, r = max(
                    cands,
                    key=lambda pr: abs(pr[1]["def_pct"] - 50.0))
                main_role = poszt
                def_pct = r["def_pct"]
                irany = ("védekezésben" if def_pct >= SPC_SPEC_PCT
                         else "támadásban")
                verdict = (
                    f"a(z) {poszt} posztjukat váltott sorban "
                    f"játsszák: az idejük "
                    f"{max(def_pct, 100.0 - def_pct):.0f}%-át "
                    f"{irany} töltik ({r['seconds']:.0f} mp mért "
                    "jelenlétből) — a csere-pillanatuk sebezhető: "
                    "gyors középkezdéssel és a szerzés utáni "
                    "azonnali indítással rossz embert találtok a "
                    "pályán")
        out[side] = {"seconds": round(total_s, 1), "roles": by_role,
                     "main_role": main_role, "def_pct": def_pct,
                     "verdict": verdict}
    return out


# Poszt-kezesség: posztonként ennyi értékelhető lövés kell az ítélethez,
# és ekkora egyoldalúság nevezi a posztot balkezesnek/jobbkezesnek.
RSH_MIN_SHOTS = 4
RSH_SHARE_PCT = 70.0


def role_shooting_hand(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Poszt-kezesség: MELYIK POSZTJUKON lő balkezes.

    A kezesség-becslés (event_detection.shooting_hand) NÉVRE mondja meg,
    ki balkezes — ez POSZTRA. A név meccsről meccsre cserélődhet, a
    poszt marad: a védekezés-terv és a kapus-felkészítés poszt-alapon
    tart ki. A kézilabdában ez különösen fontos, mert a balkezes a JOBB
    oldali posztok (jobbszélső, jobbátlövő) igazi fegyvere — onnan
    befelé jövet a megszokott sánc-kéz mellett lő el.

    Edzőileg: a balkezes posztjuk ellen tükrözni kell — a sánc a másik
    kezét emelje, a kapus alapállása a túlsó sarokra álljon, és a
    befelé vezető utat kell elzárni. Ha a jobb oldali posztjuk
    JOBBkezes, az fordítva jó hír: az ő szöge zártabb, a szélső
    befejezését a kapus a rövid sarokra állva veheti el.

    Visszatérés csapatonként: {"shots", "roles": {poszt: {"shots",
    "left", "right", "hand", "share_pct"}}, "lefty_role"} — a "hand"
    "bal"/"jobb" ítélet legalább RSH_MIN_SHOTS lövéstől és
    RSH_SHARE_PCT egyoldalúságtól (egyébként None); a "lefty_role" a
    legtöbbet lövő balkezes-ítéletű poszt, ha van.
    """
    from .event_detection import shooting_hand

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    hands = shooting_hand(match, config)

    out: dict = {}
    for side in ("home", "away"):
        tally: dict = {}
        for rec_p in hands[side]["players"]:
            rec_role = roles[side].get(rec_p["player_id"])
            if rec_role is None:
                continue
            rec = tally.setdefault(rec_role["poszt"], {"left": 0, "right": 0})
            rec["left"] += rec_p["left"]
            rec["right"] += rec_p["right"]

        rows: dict = {}
        for poszt, rec in sorted(tally.items(),
                                 key=lambda kv: -(kv[1]["left"]
                                                  + kv[1]["right"])):
            shots = rec["left"] + rec["right"]
            if not shots:
                continue
            major = max(rec["left"], rec["right"])
            share = round(100.0 * major / shots, 1)
            hand = None
            if shots >= RSH_MIN_SHOTS and share >= RSH_SHARE_PCT:
                hand = "bal" if rec["left"] > rec["right"] else "jobb"
            rows[poszt] = {"shots": shots, "left": rec["left"],
                           "right": rec["right"], "hand": hand,
                           "share_pct": share}
        lefty_role = next((p for p, r in rows.items() if r["hand"] == "bal"),
                          None)
        out[side] = {"shots": sum(r["shots"] for r in rows.values()),
                     "roles": rows, "lefty_role": lefty_role}
    return out
