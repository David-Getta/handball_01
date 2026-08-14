"""Játékmegszakítás / időkérés felismerése — mikor állt le a játék.

Az időkérés (és általában a hosszabb megszakítás) a követésben úgy
látszik, hogy a pályán lévő játékosok TARTÓSAN egy helyben állnak — a
normál játékban ez sosem fordul elő. A jel:

- legalább MIN_VISIBLE játékos látszik (üres/pásztázó képkocka nem
  "leállás", csak követés-vesztés), és
- az átlagos mozgás-sebességük STOP_SPEED_MS alatt van,
- mindez legalább TIMEOUT_MIN_S ideig folyamatosan (rövid lyukakat
  összevonva).

A TIMEOUT_LONG_S-nél hosszabb leállás jellemzően nem időkérés, hanem
hosszabb megszakítás (sérülés, félidő) — külön címkét kap. Az időkérést
tipikusan a támadó csapat kéri, ezért a leállás ELŐTTI birtoklásból
"valószínű kérő" csapatot is jelzünk.
"""

from __future__ import annotations

import math
from typing import Optional

from ..models.tracking import Match
from .tactics import TacticsConfig

STOP_SPEED_MS = 0.4     # ez alatt "állnak" a játékosok
EFFECT_WINDOW_S = 120.0  # az időkérés hatás-ablaka (előtte/utána kapott gólok)
MIN_VISIBLE = 6         # ennyi látható játékos kell a megbízható jelhez
TIMEOUT_MIN_S = 15.0    # legalább ennyi állás = megszakítás
TIMEOUT_LONG_S = 120.0  # e felett már nem időkérés (sérülés/félidő)
JOIN_S = 1.5            # ennél rövidebb "megmozdulást" összevonunk
PRE_WINDOW_S = 3.0      # a leállás előtti birtoklás-ablak (ki kérhette)


def detect_stoppages(match: Match,
                     config: Optional[TacticsConfig] = None) -> list[dict]:
    """Játékmegszakítások időrendben.

    Visszatérés: [{"start_frame", "end_frame", "duration_s",
    "kind": "időkérés" | "hosszú megszakítás",
    "likely_team": "home"/"away"/None}]."""
    from .tactics import possession_team

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    frames = match.frames
    if len(frames) < 2:
        return []

    # Kockánként: "áll-e a játék" (elég játékos látszik, és nem mozognak).
    stopped: list[bool] = [False]
    prev = {p.track_id: (p.x, p.y) for p in frames[0].players}
    for f in frames[1:]:
        cur = {p.track_id: (p.x, p.y) for p in f.players}
        speeds = [math.hypot(x - prev[t][0], y - prev[t][1]) * fps
                  for t, (x, y) in cur.items() if t in prev]
        ok = (len(cur) >= MIN_VISIBLE and speeds
              and sum(speeds) / len(speeds) < STOP_SPEED_MS)
        stopped.append(bool(ok))
        prev = cur

    # Összefüggő leállás-szakaszok, rövid lyukak összevonásával.
    join = max(1, round(JOIN_S * fps))
    need = max(2, round(TIMEOUT_MIN_S * fps))
    runs: list[list[int]] = []
    start = None
    for i, on in enumerate(stopped):
        if on and start is None:
            start = i
        elif not on and start is not None:
            runs.append([start, i - 1])
            start = None
    if start is not None:
        runs.append([start, len(stopped) - 1])
    merged: list[list[int]] = []
    for r in runs:
        if merged and r[0] - merged[-1][1] <= join:
            merged[-1][1] = r[1]
        else:
            merged.append(r)

    out: list[dict] = []
    pre = round(PRE_WINDOW_S * fps)
    for (a, b) in merged:
        if b - a + 1 < need:
            continue
        dur_s = (b - a + 1) / fps
        # Ki kérhette: a leállás előtti pár másodperc többségi birtoklása.
        tally = {"home": 0, "away": 0}
        for f in frames[max(0, a - pre):a]:
            t = possession_team(f, config)
            if t is not None:
                tally[t.value] += 1
        likely = max(tally, key=tally.get) if any(tally.values()) else None
        out.append({
            "start_frame": frames[a].t,
            "end_frame": frames[b].t,
            "duration_s": round(dur_s, 1),
            "kind": ("időkérés" if dur_s <= TIMEOUT_LONG_S
                     else "hosszú megszakítás"),
            "likely_team": likely,
        })
    return out


def timeout_effects(match: Match,
                    config: Optional[TacticsConfig] = None) -> list[dict]:
    """MŰKÖDÖTT-E az időkérés? — a kérő csapat kapott góljai előtte/utána.

    Az időkérést jellemzően a szorongatott (sorozatot kapó) csapat kéri.
    Minden felismert időkéréshez összevetjük a kérő csapat KAPOTT góljait
    az EFFECT_WINDOW_S ablakban a megszakítás előtt és után:

    - előtte ≥2 kapott gól és utána kevesebb → "megtörte a sorozatot";
    - előtte ≥2 és utána nem kevesebb → "nem hozott fordulatot";
    - előtte <2 kapott gól → nincs ítélet (nem lendület-törő időkérés).

    Visszatérés: a detect_stoppages elemei kiegészítve
    ("conceded_before", "conceded_after", "verdict")."""
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = round(EFFECT_WINDOW_S * fps)
    goals = [(e.t, e.team.value) for e in detect_shots(match, config)
             if e.type == EventType.GOAL]

    out = []
    for st in detect_stoppages(match, config):
        rec = dict(st)
        rec["conceded_before"] = rec["conceded_after"] = None
        rec["verdict"] = None
        team = st["likely_team"]
        if st["kind"] == "időkérés" and team is not None:
            a, b = st["start_frame"], st["end_frame"]
            before = sum(1 for (t, tm) in goals
                         if a - win <= t < a and tm != team)
            after = sum(1 for (t, tm) in goals
                        if b < t <= b + win and tm != team)
            rec["conceded_before"] = before
            rec["conceded_after"] = after
            if before >= 2:
                rec["verdict"] = ("megtörte a sorozatot" if after < before
                                  else "nem hozott fordulatot")
        out.append(rec)
    return out


def timeout_record(match: Match,
                   config: Optional[TacticsConfig] = None) -> dict:
    """Időkérés-mérleg csapatonként: hányszor működött a "mentő" időkérés.

    A timeout_effects ítéleteit összegzi a KÉRŐ csapat szerint: broke =
    megtörte a kapott gól-sorozatot, failed = nem hozott fordulatot. Több
    meccsen összegezve kirajzolódik, érdemes-e tartani az időkérésüktől
    (rendre rendezi a soraikat), vagy hatástalan (a megkezdett sorozat
    utána is tolható).

    Visszatérés csapatonként: {"timeouts", "broke", "failed"} — timeouts
    az összes felismert időkérésük (ítélet nélkülieket is beleértve).
    """
    config = config or TacticsConfig()
    out = {s: {"timeouts": 0, "broke": 0, "failed": 0}
           for s in ("home", "away")}
    for st in timeout_effects(match, config):
        team = st.get("likely_team")
        if st.get("kind") != "időkérés" or team not in out:
            continue
        rec = out[team]
        rec["timeouts"] += 1
        if st.get("verdict") == "megtörte a sorozatot":
            rec["broke"] += 1
        elif st.get("verdict") == "nem hozott fordulatot":
            rec["failed"] += 1
    return out


# Időkérés-hozam: ennyi ítéletes időkérés kell a kimondáshoz, és
# ekkora részarány fölött mondjuk ki, hogy az időkérésük rendez
# (vagy hatástalan).
TOY_MIN_JUDGED = 2
TOY_SHARE_PCT = 67.0


def timeout_yield(match: Match,
                  config: Optional[TacticsConfig] = None) -> dict:
    """Időkérés-hozam: MŰKÖDIK-E a mentő időkérésük.

    Az időkérés-mérleg (timeout_record) a nyers számokat adja — ez
    az ÍTÉLETET: a megtört sorozatok arányából mondja ki, hogy az
    időkérésük rendez-e.

    Edzőileg ez a sorozat-építés terve. Ha az időkérésük rendre
    megtöri a sorozatot, az ő időkérésük után nem szabad kapkodni —
    rendezett fal jön, a következő támadást ki kell dolgozni. Ha az
    időkérésük hatástalan, a megkezdett gól-sorozat az időkérésük
    UTÁN is tolható — nem kell tisztelni a zöld kartont. Saját
    csapatra: a hatástalan időkérés tartalom-kérdés (mit mondunk el
    az egy percben), nem időzítés.

    Visszatérés csapatonként (a KÉRŐ oldal): {"timeouts", "broke",
    "failed", "broke_pct", "verdict"} — a pct/verdict None, ha kevés
    (TOY_MIN_JUDGED alatti) az ítéletes időkérés.
    """
    config = config or TacticsConfig()
    rec_all = timeout_record(match, config)

    out: dict = {}
    for side in ("home", "away"):
        src = rec_all.get(side, {})
        rec = {"timeouts": src.get("timeouts", 0),
               "broke": src.get("broke", 0),
               "failed": src.get("failed", 0),
               "broke_pct": None, "verdict": None}
        judged = rec["broke"] + rec["failed"]
        if judged >= TOY_MIN_JUDGED:
            pct = 100.0 * rec["broke"] / judged
            rec["broke_pct"] = round(pct, 1)
            if pct >= TOY_SHARE_PCT:
                rec["verdict"] = (
                    f"az időkérésük rendez ({rec['broke']}/{judged} "
                    "megtört sorozat) — az ő időkérésük után nem "
                    "szabad kapkodni: rendezett fal jön, a következő "
                    "támadást ki kell dolgozni")
            elif pct <= 100.0 - TOY_SHARE_PCT:
                rec["verdict"] = (
                    f"az időkérésük hatástalan ({rec['broke']}/"
                    f"{judged} megtört sorozat) — a megkezdett "
                    "gól-sorozat az időkérésük után is tolható: nem "
                    "kell tisztelni a zöld kartont")
        out[side] = rec
    return out


# Időkérés-időzítés: ennyi felismert időkéréstől ítélünk; ennyi kapott
# gól alatti átlag a gyors fék, e felett hagyják elszaladni; és a
# meccs utolsó ennyi másodperce a hajrá.
TOT_MIN_TIMEOUTS = 2
TOT_EARLY_MAX = 1.5
TOT_LATE_MIN = 2.5
TOT_LATE_S = 600.0


def timeout_timing(match: Match,
                   config: Optional[TacticsConfig] = None) -> dict:
    """Időkérés-időzítés: MIKOR kérnek időt.

    Az időkérés-mérleg (timeout_record) azt mondja meg, MŰKÖDÖTT-E a
    megszakítás — ez azt, HOL a küszöbük: hány kapott gól után nyúlnak
    a jelzőkorongért, és mennyit tartogatnak a hajrára. Aki már az
    első-második kapott gólnál fékez, az nem hagyja kifutni a
    sorozatot; aki hármat is elenged, annál a sorozat vége a
    lendület-ablak. A hajrára tartogatott időkérés viszont azt
    jelenti, hogy a zárás náluk mindig rendezett — a döntő
    támadásokat nem lehet meglepetéssel elvinni.

    Visszatérés csapatonként (a KÉRŐ oldal): {"timeouts",
    "sum_before", "avg_before", "late_timeouts", "late_pct",
    "verdict"} — sum_before a megszakítás előtti kapott gólok
    összege (darabszám, meccsek közt összegződik); az arányok és a
    verdict None TOT_MIN_TIMEOUTS alatt, a verdict "gyors fék" /
    "hagyják elszaladni" / None.
    """
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    end_t = match.frames[-1].t if match.frames else 0
    late_from = end_t - TOT_LATE_S * fps

    acc = {s: {"timeouts": 0, "sum_before": 0, "late_timeouts": 0}
           for s in ("home", "away")}
    for st in timeout_effects(match, config):
        team = st.get("likely_team")
        if st.get("kind") != "időkérés" or team not in acc:
            continue
        rec = acc[team]
        rec["timeouts"] += 1
        rec["sum_before"] += int(st.get("conceded_before") or 0)
        if st["start_frame"] >= late_from:
            rec["late_timeouts"] += 1

    out = {}
    for side in ("home", "away"):
        rec = acc[side]
        r = {**rec, "avg_before": None, "late_pct": None,
             "verdict": None}
        if rec["timeouts"] >= TOT_MIN_TIMEOUTS:
            avg = rec["sum_before"] / rec["timeouts"]
            r["avg_before"] = round(avg, 2)
            r["late_pct"] = round(
                100.0 * rec["late_timeouts"] / rec["timeouts"], 1)
            if avg <= TOT_EARLY_MAX:
                r["verdict"] = "gyors fék"
            elif avg >= TOT_LATE_MIN:
                r["verdict"] = "hagyják elszaladni"
        out[side] = r
    return out


# Effektív játékidő: ennyi mért perctől ítélünk, e alatti effektív
# arány számít szakadozottnak, e feletti folyamatosnak.
EFF_MIN_MINUTES = 10.0
EFF_BROKEN_PCT = 80.0
EFF_FLOWING_PCT = 92.0


def playing_time_profile(match: Match,
                         config: Optional[TacticsConfig] = None) -> dict:
    """Effektív játékidő: MENNYI a tényleges játék a megszakításokhoz
    képest.

    A megszakítás-felismerés (detect_stoppages) az egyes leállásokat
    adja, az időkérés-időzítés (timeout_timing) azt, mikor nyúlnak a
    korongért — ez a meccs RITMUSÁT: a felismert megszakítások
    összegzett ideje a mért játékidőhöz mérve, és megszakításonként az
    a csapat, amelyik előtte birtokolt (nála állt meg a játék).

    Edzőileg: a szakadozott meccsképben a ritmus-tartás a feladat —
    gyors középkezdés, a megszakítások utáni első támadásra kész terv,
    és fegyelem a leállások alatt; a folyamatos meccsen a bírás és a
    cserék időzítése dönt.

    Visszatérés csapatonként (a megszakítás előtt birtokló csapat
    szerint): {"total_s", "stopped_s", "effective_pct", "stoppages",
    "own_stoppages", "own_stopped_s", "verdict"} — a total_s,
    effective_pct és a verdict a meccsre közös; a verdict None
    EFF_MIN_MINUTES alatt, egyébként "szakadozott meccskép" /
    "folyamatos meccs" / None.
    """
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    frames = match.frames
    total_s = ((frames[-1].t - frames[0].t + 1) / fps) if frames else 0.0

    stops = detect_stoppages(match, config)
    stopped_s = sum(s["duration_s"] for s in stops)
    own = {"home": [0, 0.0], "away": [0, 0.0]}
    for s in stops:
        if s["likely_team"] in own:
            own[s["likely_team"]][0] += 1
            own[s["likely_team"]][1] += s["duration_s"]

    eff_pct = (round(100.0 * (total_s - stopped_s) / total_s, 1)
               if total_s > 0 else None)
    verdict = None
    if total_s >= EFF_MIN_MINUTES * 60.0 and eff_pct is not None:
        if eff_pct <= EFF_BROKEN_PCT:
            verdict = "szakadozott meccskép"
        elif eff_pct >= EFF_FLOWING_PCT:
            verdict = "folyamatos meccs"

    return {side: {"total_s": round(total_s, 1),
                   "stopped_s": round(stopped_s, 1),
                   "effective_pct": eff_pct,
                   "stoppages": len(stops),
                   "own_stoppages": own[side][0],
                   "own_stopped_s": round(own[side][1], 1),
                   "verdict": verdict}
            for side in ("home", "away")}


# Időkérés utáni első támadás: ennyi mért időkérés kell az ítélethez, és
# e feletti / alatti gólarány a kész figura, illetve az üres időkérés
# jele. Az első támadást ekkora ablakban keressük az újraindítás után.
TFA_MIN_TIMEOUTS = 3
TFA_WINDOW_S = 40.0
TFA_HIGH_PCT = 60.0
TFA_LOW_PCT = 20.0


def timeout_first_attack(match: Match,
                         config: Optional[TacticsConfig] = None) -> dict:
    """Időkérés utáni első támadás: VAN-E KÉSZ FIGURÁJUK.

    Az időkérés-mérleg (timeout_record) azt mondja meg, megtörte-e a
    megszakítás a sorozatot, az időkérés-időzítés (timeout_timing)
    azt, mikor kérnek időt — ez azt, MIT KEZDENEK VELE: az időkérést
    kérő csapat első támadását nézzük az újraindítás után, és
    megszámoljuk, hányból lett gól.

    Edzőileg: aki az időkérések után rendre betalál, annak kész
    figurája van — arra a támadásra előre fel kell készülni (kijelölt
    védekezés, a beállójuk elé állás); akinél az első támadás rendre
    elhal, ott az időkérés nem hoz megoldást, elég a szokásos fal.

    Visszatérés csapatonként: {"timeouts", "goals", "share_pct",
    "verdict"} — a share_pct/verdict None TFA_MIN_TIMEOUTS alatt; a
    verdict "kész figura az időkérés után" / "üres időkérés" / None.
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = TFA_WINDOW_S * fps
    goals = [(e.t, e.team.value) for e in detect_shots(match, config)
             if e.type == EventType.GOAL]

    out: dict = {side: {"timeouts": 0, "goals": 0, "share_pct": None,
                        "verdict": None} for side in ("home", "away")}
    for s in detect_stoppages(match, config):
        if s["kind"] != "időkérés" or s["likely_team"] is None:
            continue
        side = s["likely_team"]
        rec = out[side]
        rec["timeouts"] += 1
        end = s["end_frame"]
        if any(tm == side and end < t <= end + win for (t, tm) in goals):
            rec["goals"] += 1

    for side in ("home", "away"):
        rec = out[side]
        if rec["timeouts"] >= TFA_MIN_TIMEOUTS:
            share = 100.0 * rec["goals"] / rec["timeouts"]
            rec["share_pct"] = round(share, 1)
            if share >= TFA_HIGH_PCT:
                rec["verdict"] = "kész figura az időkérés után"
            elif share <= TFA_LOW_PCT:
                rec["verdict"] = "üres időkérés"
    return out


# Időkérés utáni védekezés: ennyi mért időkérés kell az ítélethez,
# ekkora ablakban nézzük az ellenfél válaszát, és e feletti / alatti
# kapott gól arány a rossz, illetve a friss védekezés jele.
TFD_MIN_TIMEOUTS = 3
TFD_WINDOW_S = 40.0
TFD_LEAKY_PCT = 60.0
TFD_TIGHT_PCT = 20.0


def timeout_first_defense(match: Match,
                          config: Optional[TacticsConfig] = None) -> dict:
    """Időkérés utáni védekezés: MEGÁLL-E A FAL a megszakítás után.

    Az időkérés utáni első támadás (timeout_first_attack) azt méri,
    mit kezd a saját támadásával az időt kérő csapat — ez azt, mi
    történik a MÁSIK oldalon: az időkérést kérő csapat védekezését
    nézzük az újraindítás után, és megszámoljuk, hányszor kapott gólt
    az ellenfél első rohamából.

    Edzőileg: ha az időkérésük után rendre gólt kapnak, a megszakítás
    nem a védekezésről szólt — ilyenkor érdemes azonnal, felállás
    nélkül támadni ellenük; ha a faluk az időkérés után rendre
    megáll, ott a gyors roham veszteség, inkább rendezetten kell
    felállni és kivárni.

    Visszatérés csapatonként: {"timeouts", "conceded", "share_pct",
    "verdict"} — a share_pct/verdict None TFD_MIN_TIMEOUTS alatt; a
    verdict "időkérés után szivárgó fal" / "időkérés után friss fal" /
    None.
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = TFD_WINDOW_S * fps
    goals = [(e.t, e.team.value) for e in detect_shots(match, config)
             if e.type == EventType.GOAL]

    out: dict = {side: {"timeouts": 0, "conceded": 0, "share_pct": None,
                        "verdict": None} for side in ("home", "away")}
    for s in detect_stoppages(match, config):
        if s["kind"] != "időkérés" or s["likely_team"] is None:
            continue
        side = s["likely_team"]
        rec = out[side]
        rec["timeouts"] += 1
        end = s["end_frame"]
        # Az ELLENFÉL gólja az újraindítás utáni ablakban.
        if any(tm != side and end < t <= end + win for (t, tm) in goals):
            rec["conceded"] += 1

    for side in ("home", "away"):
        rec = out[side]
        if rec["timeouts"] >= TFD_MIN_TIMEOUTS:
            share = 100.0 * rec["conceded"] / rec["timeouts"]
            rec["share_pct"] = round(share, 1)
            if share >= TFD_LEAKY_PCT:
                rec["verdict"] = "időkérés után szivárgó fal"
            elif share <= TFD_TIGHT_PCT:
                rec["verdict"] = "időkérés után friss fal"
    return out


# Időkérés-csomag: ekkora ablakban keresünk cserét az időkérés körül,
# ennyi mért időkérés kell az ítélethez, és e feletti arány jelenti a
# cserével járó időkérést.
TSC_WINDOW_S = 60.0
TSC_MIN_TIMEOUTS = 2
TSC_COMBO_PCT = 70.0


def timeout_sub_combo(match: Match,
                      config: Optional[TacticsConfig] = None) -> dict:
    """Időkérés-csomag: AZ IDŐKÉRÉSÜK CSERÉVEL JÁR-E.

    Az időkérés-hatás (timeout_effects) azt méri, mit hoz az időkérés
    — ez azt, MI VAN BENNE: az időkérés körüli TSC_WINDOW_S
    másodpercben keresünk azonos-csapatbeli cserehullámot. Akinél az
    időkérés rendre cserével jár, ott a szünet nem csak taktika,
    hanem személycsere is — az edző új emberekkel indítja újra a
    meccset.

    Edzőileg: a cserélő időkérés után frissíteni kell a párosítást —
    az első támadásukban friss lábú ember jön, a kettőzés és az őrzés
    az ÚJ emberre menjen; aki csere nélkül kér időt, annál a szünet
    tiszta taktika: ugyanazok jönnek vissza, de új figurával — a
    fal az első támadásnál extra figyelmet kap.

    Visszatérés csapatonként: {"timeouts", "with_subs", "verdict"} —
    a verdict None TSC_MIN_TIMEOUTS alatt; a verdict "az időkérésük
    cserével jár" / "az időkérésük tiszta taktika" / None.
    """
    from .substitutions import detect_substitutions

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = round(TSC_WINDOW_S * fps)
    subs = detect_substitutions(match, config)

    out = {side: {"timeouts": 0, "with_subs": 0, "verdict": None}
           for side in ("home", "away")}
    for st in detect_stoppages(match, config):
        if st["kind"] != "időkérés" or st["likely_team"] is None:
            continue
        side = st["likely_team"]
        rec = out[side]
        rec["timeouts"] += 1
        if any(ev["team"] == side
               and st["start_frame"] - win <= ev["t"]
               <= st["end_frame"] + win
               for ev in subs):
            rec["with_subs"] += 1

    for side in ("home", "away"):
        rec = out[side]
        if rec["timeouts"] >= TSC_MIN_TIMEOUTS:
            pct = 100.0 * rec["with_subs"] / rec["timeouts"]
            if pct >= TSC_COMBO_PCT:
                rec["verdict"] = "az időkérésük cserével jár"
            elif pct <= 100.0 - TSC_COMBO_PCT:
                rec["verdict"] = "az időkérésük tiszta taktika"
    return out


# Hosszú állás utáni játék: ekkora ablakot nézünk a hosszú megszakítás
# után, ennyi mért állás kell az ítélethez, és ekkora gólkülönbség
# jelenti a meglóduló, illetve a kizökkenő újrakezdést.
LBR_WINDOW_S = 120.0
LBR_MIN_BREAKS = 2
LBR_DIFF = 2


def long_break_response(match: Match,
                        config: Optional[TacticsConfig] = None) -> dict:
    """Hosszú állás utáni játék: KIZÖKKENTI-E ŐKET a hosszú megszakítás.

    Az időkérés-rétegek a rövid, kért szünetet mérik — ez a hosszút
    (sérülés, technikai állás): a hosszú megszakítások utáni
    LBR_WINDOW_S másodperc gólmérlegét számoljuk mindkét oldalra. A
    váratlan, hosszú állás nem taktikai szünet: van, aki hidegen
    lefagy utána, és van, aki elsőnek kapcsol vissza.

    Edzőileg: a hosszú állás után kizökkenő csapat ellen az
    újraindítás a ti pillanatotok — kész figurával és letámadással
    kell jönni, amíg hidegek; a meglóduló csapat ellen az újraindítás
    utáni első védekezés kapjon extra figyelmet, és a saját
    bemelegítés (padon is mozogni) kötelező.

    Visszatérés csapatonként: {"breaks", "goals_for", "goals_against",
    "verdict"} — a verdict None LBR_MIN_BREAKS alatt; a verdict "a
    hosszú állások után meglódulnak" / "a hosszú állások kizökkentik
    őket" / None.
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = round(LBR_WINDOW_S * fps)
    goals = [(e.t, e.team.value) for e in detect_shots(match, config)
             if e.type == EventType.GOAL]

    out = {side: {"breaks": 0, "goals_for": 0, "goals_against": 0,
                  "verdict": None} for side in ("home", "away")}
    for st in detect_stoppages(match, config):
        if st["kind"] != "hosszú megszakítás":
            continue
        for side in ("home", "away"):
            rec = out[side]
            rec["breaks"] += 1
            for (t, tm) in goals:
                if st["end_frame"] < t <= st["end_frame"] + win:
                    if tm == side:
                        rec["goals_for"] += 1
                    else:
                        rec["goals_against"] += 1

    for side in ("home", "away"):
        rec = out[side]
        if rec["breaks"] >= LBR_MIN_BREAKS:
            diff = rec["goals_for"] - rec["goals_against"]
            if diff >= LBR_DIFF:
                rec["verdict"] = "a hosszú állások után meglódulnak"
            elif diff <= -LBR_DIFF:
                rec["verdict"] = "a hosszú állások kizökkentik őket"
    return out


# Időkérés-befejező: ennyi poszthoz kötött lövés kell az ítélethez az
# időkérések utáni ablakban, és ekkora részarány számít mintázatnak. Az
# időkérés ritka esemény (meccsenként 3 db), ezért a küszöb alacsony —
# a felderítésben viszont meccsek közt összegződik.
TOF_MIN_SHOTS = 3
TOF_SHARE_PCT = 60.0
TOF_WINDOW_S = 40.0


def timeout_finisher(match: Match,
                     config: Optional[TacticsConfig] = None) -> dict:
    """Időkérés-befejező: AZ IDŐKÉRÉS UTÁN KIRE JÁTSZANAK.

    Az időkérés utáni első támadás (`timeout_first_attack`) azt mondja
    meg, van-e kész figurájuk — ez azt, hogy a kész figura KIRE fut ki.
    Az időkérést kérő csapat első TOF_WINDOW_S másodpercét nézzük az
    újraindítás után, és a benne esett lövéseket az ELENGEDŐ játékos
    posztjához írjuk.

    Edzőileg ez a legolcsóbb felkészülés a meccsen belül. Az időkérés
    után a fal TUDJA, hogy figura jön — csak azt nem, kire. Ha a
    lövések nagy része ugyanarra a posztra megy, a megbeszélésben egy
    mondat elég: "időkérés után rá figyelünk, elé állunk, a többit
    hagyjuk". Ha szórt a befejezés, az időkérés utáni támadásra nem
    érdemes külön embert rendelni — a szokásos fal a jobb.

    Visszatérés csapatonként: {"timeouts", "shots" (poszthoz kötött),
    "roles": {poszt: lövés}, "main_role", "share_pct", "verdict"} — a
    main_role/share_pct/verdict None, ha nincs meg a TOF_MIN_SHOTS
    lövés, vagy egyik poszt sem éri el a TOF_SHARE_PCT részarányt.
    """
    from .event_detection import EventType, detect_shots
    from .roles import estimate_positions

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = TOF_WINDOW_S * fps
    roles = estimate_positions(match, config)
    shots = [e for e in detect_shots(match, config)
             if e.type in (EventType.SHOT, EventType.GOAL)]

    out: dict = {side: {"timeouts": 0, "shots": 0, "roles": {},
                        "main_role": None, "share_pct": None,
                        "verdict": None} for side in ("home", "away")}
    for s in detect_stoppages(match, config):
        if s["kind"] != "időkérés" or s["likely_team"] is None:
            continue
        side = s["likely_team"]
        rec = out[side]
        rec["timeouts"] += 1
        end = s["end_frame"]
        for e in shots:
            if e.team.value != side or not (end < e.t <= end + win):
                continue
            if e.player_id is None:
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
        if rec["shots"] >= TOF_MIN_SHOTS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["shots"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= TOF_SHARE_PCT:
                rec["verdict"] = (
                    f"időkérés után a(z) {poszt} fejez be "
                    f"({share:.0f}%, {rec['shots']} lövésből) — a "
                    "megbeszélésen ő kapja az embert, elé kell állni")
    return out


# Időkéréspáros-poszt: ennyi párhoz kötött időkérés utáni lövés kell
# az ítélethez, ekkora részarány fölött mondjuk ki a tengelyt, és
# ennyi időn belüli utolsó passzt tekintünk előkészítésnek.
TOP_MIN_SHOTS = 3
TOP_SHARE_PCT = 60.0
TOP_PASS_WINDOW_S = 4.0


def timeout_pair_roles(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Időkéréspáros-poszt: AZ IDŐKÉRÉS UTÁNI FIGURA TENGELYE.

    Az időkérés-befejező a figura végpontját nevezi meg — ez a
    tengelyt: az időkérés utáni ablakban leadott lövésekhez
    megkeresi a lövő felé menő utolsó passzt, és a lövést az
    (előkészítő poszt → befejező poszt) párhoz írja.

    Edzőileg ez a megbeszélés egy mondata: az időkérés után a fal
    tudja, hogy kész figura jön — ha a tengely ismert, nem csak a
    befejezőre kell figyelni, hanem az ELSŐ passzt kell elvágni. A
    figura az indításnál a legolcsóbban törik meg. Saját csapatra: az
    időkérés utáni figura ne mindig ugyanazon a tengelyen fusson.

    Visszatérés csapatonként: {"shots" (párhoz kötött), "roles":
    {"előkészítő→befejező": darab}, "main_role", "share_pct",
    "verdict"} — az ítélet None, ha nincs meg a TOP_MIN_SHOTS, vagy
    egyik pár sem éri el a TOP_SHARE_PCT-t.
    """
    from .decisions import detect_passes
    from .event_detection import EventType, detect_shots
    from .roles import estimate_positions

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = TOF_WINDOW_S * fps
    pass_win = TOP_PASS_WINDOW_S * fps
    roles = estimate_positions(match, config)
    passes = detect_passes(match, config)

    # Az időkérést kérő csapat és az újraindítás ideje.
    stops = [(s["likely_team"], s["end_frame"])
             for s in detect_stoppages(match, config)
             if s.get("likely_team") is not None]

    out: dict = {side: {"shots": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    if not stops:
        return out

    for e in detect_shots(match, config):
        if e.type not in (EventType.SHOT, EventType.GOAL):
            continue
        if e.player_id is None:
            continue
        side = e.team.value
        if not any(team == side and 0 <= e.t - end <= win
                   for (team, end) in stops):
            continue
        best = None
        for p in passes:
            if not (0 <= e.t - p.t <= pass_win) or p.team != e.team:
                continue
            if (p.receiver_id != e.player_id
                    or p.passer_id == e.player_id):
                continue
            if best is None or p.t > best.t:
                best = p
        if best is None:
            continue
        r_feed = roles[side].get(best.passer_id)
        r_shot = roles[side].get(e.player_id)
        if r_feed is None or r_shot is None:
            continue
        kulcs = f"{r_feed['poszt']}→{r_shot['poszt']}"
        rec = out[side]
        rec["roles"][kulcs] = rec["roles"].get(kulcs, 0) + 1
        rec["shots"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["shots"] >= TOP_MIN_SHOTS:
            par = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][par] / rec["shots"]
            rec["main_role"] = par
            rec["share_pct"] = round(share, 1)
            if share >= TOP_SHARE_PCT:
                rec["verdict"] = (
                    f"az időkérés utáni figurájuk a(z) {par} "
                    f"tengelyen fut ({share:.0f}%, {rec['shots']} "
                    "időkérés utáni lövésből) — ne csak a befejezőre"
                    " figyeljetek: az ELSŐ passzt vágjátok el, ott "
                    "törik meg a figura a legolcsóbban")
    return out


# Időkérés-hiba poszt küszöbei: ennyi poszthoz kötött időkérés utáni
# eladás kell az ítélethez, és ekkora részarány a vezető posztnak.
TOE_MIN_TURNOVERS = 3
TOE_SHARE_PCT = 60.0


def timeout_turnover_roles(match: Match,
                           config: Optional[TacticsConfig] = None
                           ) -> dict:
    """Időkérés-hiba poszt: A MEGBESZÉLT FIGURA kinek a kezén hal el.

    Az időkérés-befejező és az időkéréspáros a sikeres figurát írja
    le (ki fejez be, milyen tengelyen) — ez a kudarcát: az időkérés
    utáni ablakban (TOF_WINDOW_S) elkövetett labdaeladásaikat a
    vesztes posztjához írja.

    Edzőileg ez az időkérés utáni védekezés második mondata: a
    megbeszélt figura ott a legsérülékenyebb, ahol eddig is elhalt —
    ha az időkérés utáni labdájuk rendre ugyanannak a kezében vész
    el, oda kell nyomni a figura indításánál (előrelépő védő,
    kettőzés az első bejátszásnál). Saját csapatra: a táblára rajzolt
    figura nem működik, ha a kulcspasszt mindig ugyanaz rontja el —
    egyszerűbb kezdés kell.

    Visszatérés csapatonként: {"turnovers" (poszthoz kötött időkérés
    utáni eladás), "roles": {poszt: darab}, "main_role",
    "share_pct", "verdict"} — az ítélet None, ha nincs meg a
    TOE_MIN_TURNOVERS, vagy egyik poszt sem éri el a
    TOE_SHARE_PCT-t.
    """
    from .event_detection import EventType, detect_events
    from .roles import estimate_positions

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = TOF_WINDOW_S * fps
    roles = estimate_positions(match, config)

    # Az időkérést kérő csapat és az újraindítás ideje.
    stops = [(s["likely_team"], s["end_frame"])
             for s in detect_stoppages(match, config)
             if s.get("likely_team") is not None]

    out: dict = {side: {"turnovers": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    if not stops:
        return out

    for e in detect_events(match, config):
        if e.type != EventType.TURNOVER or e.player_id is None:
            continue
        side = e.team.value
        if not any(team == side and 0 <= e.t - end <= win
                   for (team, end) in stops):
            continue
        rec_role = roles[side].get(e.player_id)
        if rec_role is None:
            continue
        poszt = rec_role["poszt"]
        rec = out[side]
        rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1
        rec["turnovers"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["turnovers"] >= TOE_MIN_TURNOVERS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["turnovers"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= TOE_SHARE_PCT:
                rec["verdict"] = (
                    f"az időkérés utáni labdájuk {share:.0f}%-ban "
                    f"a(z) {poszt} kezén vész el ({rec['turnovers']} "
                    "eladásból) — a megbeszélt figurát az ő "
                    "indításánál kell megnyomni, ott hal el "
                    "magától is")
    return out


# Időkérés-hibázók: ennyi időkérés utáni eladástól emeljük ki a
# játékost (az időkérés ritka esemény, ezért alacsony a küszöb).
TOEP_MIN_TURNOVERS = 2


def timeout_turnover_players(match: Match,
                             config: Optional[TacticsConfig] = None
                             ) -> dict:
    """Időkérés-hibázók: A MEGBESZÉLT FIGURA kinek a kezén hal el.

    Az időkérés-hiba poszt (timeout_turnover_roles) a POSZTOT nevezi
    meg — ez az EMBERT: ugyanazokat az időkérés utáni ablakban
    elkövetett labdaeladásokat játékosonként számolja.

    Edzőileg ez az időkérés utáni védekezés névre szóló mondata: a
    táblára rajzolt figura ott a legsérülékenyebb, ahol eddig is
    elhalt — az ő fogadására menjen a kilépés és a kettőzés. Saját
    csapatra: a kulcspasszt ne az kapja, aki a megbeszélés utáni
    feszültségben rendre elrontja.

    Visszatérés csapatonként: {"turnovers", "players":
    [{"player_id", "jersey", "turnovers"}], "top"} — a "top" az első
    játékos, ha legalább TOEP_MIN_TURNOVERS időkérés utáni eladása
    van, különben None.
    """
    from .event_detection import EventType, detect_events

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = TOF_WINDOW_S * fps
    stops = [(s["likely_team"], s["end_frame"])
             for s in detect_stoppages(match, config)
             if s.get("likely_team") is not None]

    jersey: dict = {}
    for f in match.frames:
        for p in f.players:
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)

    tally: dict = {"home": {}, "away": {}}
    if stops:
        for e in detect_events(match, config):
            if e.type != EventType.TURNOVER or e.player_id is None:
                continue
            side = e.team.value
            if not any(team == side and 0 <= e.t - end <= win
                       for (team, end) in stops):
                continue
            tally[side][e.player_id] = (
                tally[side].get(e.player_id, 0) + 1)

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "turnovers": n}
                for pid, n in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1])]
        top = (rows[0]
               if rows and rows[0]["turnovers"] >= TOEP_MIN_TURNOVERS
               else None)
        out[side] = {"turnovers": sum(r["turnovers"] for r in rows),
                     "players": rows, "top": top}
    return out
