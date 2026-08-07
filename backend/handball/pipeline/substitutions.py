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


# Csere-blokkok: ennyi cserehullámtól ítélünk, és e feletti blokkos
# arány jelenti, hogy a csapat egységeket (specialistákat) cserél.
SUBBLK_MIN_WAVES = 4
SUBBLK_BLOCK_PCT = 40.0


def substitution_blocks(match: Match,
                        config: Optional[TacticsConfig] = None) -> dict:
    """Csere-blokkok: egyesével cserélnek, vagy egységekben.

    A csere-hatás (substitution_impact) azt méri, MI TÖRTÉNIK a csere
    után, a késő csere (late_sub_flags) azt, kit felejtenek bent — ez
    a harmadik kérdés: HOGYAN cserélnek. Ha egy hullámban rendre két-
    három ember jön-megy, a csapat specialistákat mozgat (támadó és
    védekező egység); ha egyesével, akkor pihentetnek.

    Edzőileg: a blokkos csere ellen a gyors újraindítás a fegyver —
    csere közben egy ütemre rossz emberek vannak a pályán, és a
    védekező egységük támadásban (vagy fordítva) kiszolgáltatott;
    egyesével cserélő csapatnál viszont a célzott fárasztás működik.

    Visszatérés csapatonként: {"waves", "players", "block_waves",
    "block_pct", "avg_size", "verdict"} — a hullámok száma, a bennük
    mozgatott játékosok összege, a 2+ fős hullámok száma és aránya, a
    hullámok átlagos mérete; az arányok és a verdict None
    SUBBLK_MIN_WAVES alatt, a verdict "blokkos csere" / "egyesével".
    """
    config = config or TacticsConfig()
    acc = {s: {"waves": 0, "players": 0, "block_waves": 0}
           for s in ("home", "away")}
    for ev in detect_substitutions(match, config):
        size = max(len(ev["out_ids"]), len(ev["in_ids"]))
        rec = acc[ev["team"]]
        rec["waves"] += 1
        rec["players"] += size
        if size >= 2:
            rec["block_waves"] += 1

    out = {}
    for side in ("home", "away"):
        rec = acc[side]
        r = {**rec, "block_pct": None, "avg_size": None,
             "verdict": None}
        if rec["waves"] >= SUBBLK_MIN_WAVES:
            pct = 100.0 * rec["block_waves"] / rec["waves"]
            r["block_pct"] = round(pct, 1)
            r["avg_size"] = round(rec["players"] / rec["waves"], 2)
            r["verdict"] = ("blokkos csere" if pct >= SUBBLK_BLOCK_PCT
                            else "egyesével")
        out[side] = r
    return out


# Csere-kiváltók: ennyi mért csere kell az ítélethez, a kapott gól után
# ekkora ablakban számít a csere reaktívnak, és e feletti / alatti
# részarány a reaktív, illetve a tervezett csere-rend jele.
SUBTRIG_MIN_SUBS = 4
SUBTRIG_WINDOW_S = 30.0
SUBTRIG_HIGH_PCT = 50.0
SUBTRIG_LOW_PCT = 20.0


def substitution_triggers(match: Match,
                          config: Optional[TacticsConfig] = None) -> dict:
    """Csere-kiváltók: KAPOTT GÓL UTÁN cserélnek-e.

    A csere-blokkok (substitution_blocks) azt mondják meg, HOGYAN
    cserélnek (egyesével vagy egységekben), a csere-hatás
    (substitution_impact) azt, mi lesz belőle — ez azt, MIÉRT: a
    cserehullámokat ahhoz kötjük, jött-e kapott gól a megelőző
    SUBTRIG_WINDOW_S másodpercben.

    Edzőileg: aki jellemzően kapott gól után cserél, az reagál, nem
    tervez — a gólsorozat nála cserezavart is okoz, ezért a gyors
    gólváltásra kell játszani (a csere pillanatában azonnal
    középkezdés); aki tervezetten vált, annál a csere-ritmusuk
    kiszámítható, és a saját cseréidet ahhoz lehet igazítani.

    Visszatérés csapatonként: {"subs", "after_conceded", "share_pct",
    "verdict"} — a share_pct/verdict None SUBTRIG_MIN_SUBS alatt; a
    verdict "kapott gólra cserélnek" / "tervezett csere-rend" / None.
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = SUBTRIG_WINDOW_S * fps
    goals = [(e.t, e.team.value) for e in detect_shots(match, config)
             if e.type == EventType.GOAL]

    out: dict = {side: {"subs": 0, "after_conceded": 0,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for ev in detect_substitutions(match, config):
        side = ev["team"]
        rec = out[side]
        rec["subs"] += 1
        if any(tm != side and 0 <= ev["t"] - t <= win
               for (t, tm) in goals):
            rec["after_conceded"] += 1

    for side in ("home", "away"):
        rec = out[side]
        if rec["subs"] >= SUBTRIG_MIN_SUBS:
            share = 100.0 * rec["after_conceded"] / rec["subs"]
            rec["share_pct"] = round(share, 1)
            if share >= SUBTRIG_HIGH_PCT:
                rec["verdict"] = "kapott gólra cserélnek"
            elif share <= SUBTRIG_LOW_PCT:
                rec["verdict"] = "tervezett csere-rend"
    return out


# Váltópárok: ennyi egy-az-egyben csere kell az ítélethez, és ennyi
# ismétlődés tesz egy párost kiszámíthatóvá.
SWP_MIN_SWAPS = 4
SWP_MIN_REPEAT = 3


def swap_pairs(match: Match,
               config: Optional[TacticsConfig] = None) -> dict:
    """Váltópárok: KI KIT VÁLT a cseréknél.

    A csere-blokkok (substitution_blocks) azt mondják meg, egységekben
    vagy egyesével cserélnek — ez azt, KI KIT: az egy-ki-egy-be
    hullámokból párokat képzünk (mezszám szerint, ha az OCR kiolvasta,
    különben track szerint), és megnézzük, van-e ismétlődő páros.

    Edzőileg: a kiszámítható váltópár kettőt is ér — előre lehet
    készülni a beálló emberre (a cserére nem új terv kell, hanem a
    kész B-terv), és az óra is olvasható: ha a kulcsemberük fáradni
    kezd, tudni lehet, ki jön, és az ő gyengéjére már a csere előtt
    át lehet állítani a támadást.

    Visszatérés csapatonként: {"swaps", "pairs": [{"out_id", "in_id",
    "count"}], "top", "verdict"} — a pairs count szerint csökkenő; a
    top/verdict None SWP_MIN_SWAPS mért csere alatt vagy SWP_MIN_REPEAT
    alatti ismétlődésnél; a verdict "kiszámítható váltópár" / None.
    """
    config = config or TacticsConfig()
    jersey: dict[int, int] = {}
    for f in match.frames:
        for p in f.players:
            if p.jersey_number is not None and p.track_id not in jersey:
                jersey[p.track_id] = p.jersey_number

    def _label(tid: int):
        return jersey.get(tid, tid)

    tally: dict = {"home": {}, "away": {}}
    swaps = {"home": 0, "away": 0}
    for ev in detect_substitutions(match, config):
        if len(ev["out_ids"]) != 1 or len(ev["in_ids"]) != 1:
            continue   # a blokk-cserét a csere-blokk réteg kezeli
        side = ev["team"]
        swaps[side] += 1
        key = (_label(ev["out_ids"][0]), _label(ev["in_ids"][0]))
        tally[side][key] = tally[side].get(key, 0) + 1

    out: dict = {}
    for side in ("home", "away"):
        pairs = [{"out_id": o, "in_id": i, "count": n}
                 for (o, i), n in sorted(tally[side].items(),
                                         key=lambda kv: -kv[1])]
        top = None
        verdict = None
        if swaps[side] >= SWP_MIN_SWAPS and pairs \
                and pairs[0]["count"] >= SWP_MIN_REPEAT:
            top = pairs[0]
            verdict = "kiszámítható váltópár"
        out[side] = {"swaps": swaps[side], "pairs": pairs,
                     "top": top, "verdict": verdict}
    return out


# Csere-lyukak: ennél rövidebb létszám-hiány cserehiba (nem kiállítás),
# ennél hosszabb összes lyuk-idő adja a jelzést, ez alatti a feszes
# csere dicséretét.
SBG_MIN_WINDOW_S = 5.0
SBG_LEAKY_S = 20.0
SBG_TIGHT_S = 5.0


def sub_gaps(match: Match,
             config: Optional[TacticsConfig] = None) -> dict:
    """Csere-lyukak: MENNYI IDEIG JÁTSZANAK 5-EN csere közben.

    A kiállítás-felismerés a 45 másodpercnél hosszabb létszám-hiányt
    nézi — ez a rövidebbeket: azok az ablakok, ahol a csapat
    mezőnyjátékos-létszáma a cserék lassúsága miatt esik ötre. A
    lyukas csere ingyen emberelőny az ellenfélnek — párszor egy
    meccsben, de pont a gyors indításoknál.

    Edzőileg: a lyukasan cserélő csapat ellen a csere pillanata a
    jel — gyors középkezdés és azonnali támadás, amíg öten vannak; a
    saját csapatban a csere-ütem (előbb be, aztán ki? soha — ki és
    be egy ütemben, a zónán belül) külön gyakorlást kap.

    Visszatérés csapatonként: {"gap_s", "verdict"} — a verdict
    "lyukas a cseréjük" / "feszes a cseréjük" / None.
    """
    from .rules import PP_MIN_S, field_count_timeline

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    tl = field_count_timeline(match)
    if len(tl) < 2:
        return {side: {"gap_s": 0.0, "verdict": None}
                for side in ("home", "away")}
    win_frames = tl[1]["start_frame"] - tl[0]["start_frame"]
    win_s = win_frames / fps

    out: dict = {}
    for side, other in (("home", "away"), ("away", "home")):
        run_s = 0.0
        total = 0.0
        for w in tl + [None]:
            active = (w is not None and w[side] <= 4 + 1
                      and w[side] < w[other])
            if active:
                run_s += win_s
            else:
                if SBG_MIN_WINDOW_S <= run_s < PP_MIN_S:
                    total += run_s
                run_s = 0.0
        rec = {"gap_s": round(total, 1), "verdict": None}
        if total >= SBG_LEAKY_S:
            rec["verdict"] = "lyukas a cseréjük"
        elif total <= SBG_TIGHT_S:
            rec["verdict"] = "feszes a cseréjük"
        out[side] = rec
    return out


# Csere-állás: mindkét állás-vödörben legalább ennyi másodperc és
# összesen ennyi cserehullám kell az ítélethez; a vezetés közbeni
# csere-ütem ekkora szorzója a forgatás, ekkora hányada a nem nyúlnak
# hozzá jele.
SBS_MIN_STATE_S = 120.0
SBS_MIN_SUBS = 4
SBS_ROTATE_RATIO = 1.5
SBS_HOLD_RATIO = 0.5


def subs_by_score(match: Match,
                  config: Optional[TacticsConfig] = None) -> dict:
    """Csere-állás: VEZETVE FORGATNAK-E.

    A csere-kiváltók azt mérik, kapott gólra cserélnek-e — ez azt,
    mit tesznek az előnnyel: a cserehullámok ütemét (hullám/perc)
    hasonlítjuk össze a vezetésben és az összes többi állapotban
    töltött idő között. Van, aki vezetve pihentet és a padot
    járatja, és van, aki előnyben sem nyúl a kezdősorhoz.

    Edzőileg: a vezetve forgató csapat ellen a szoros meccs a
    fegyver — amíg nincs meg az előnyük, nem mernek pihentetni, és a
    kezdősoruk a hajrára elfárad; aki előnyben sem cserél, annál a
    fáradó kulcsember végig fent van — a meccs végén őt kell
    megtámadni.

    Visszatérés csapatonként: {"lead_subs", "rest_subs", "lead_s",
    "rest_s", "verdict"} — a verdict None, ha bármelyik állapotban
    SBS_MIN_STATE_S-nél kevesebb idő telt, vagy SBS_MIN_SUBS-nál
    kevesebb a cserehullám; a verdict "vezetve forgatnak" /
    "vezetve sem nyúlnak a sorhoz" / None.
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    goals = sorted((e.t, e.team.value)
                   for e in detect_shots(match, config)
                   if e.type == EventType.GOAL)

    def _state(side, t):
        own = sum(1 for (gt, tm) in goals if gt < t and tm == side)
        opp = sum(1 for (gt, tm) in goals if gt < t and tm != side)
        return "lead" if own > opp else "rest"

    out: dict = {}
    durs = {side: {"lead": 0.0, "rest": 0.0}
            for side in ("home", "away")}
    if match.frames:
        # A gól-események közti szakaszokon az állás állandó — elég a
        # szakasz-határokon számolni.
        t0, t1 = match.frames[0].t, match.frames[-1].t
        marks = [t0] + [gt for (gt, _) in goals
                        if t0 < gt < t1] + [t1]
        for a, b in zip(marks, marks[1:]):
            span_s = (b - a) / fps
            for side in ("home", "away"):
                durs[side][_state(side, a + 1)] += span_s

    waves = detect_substitutions(match, config)
    for side in ("home", "away"):
        lead_subs = sum(1 for w in waves if w["team"] == side
                        and _state(side, w["t"]) == "lead")
        rest_subs = sum(1 for w in waves if w["team"] == side
                        and _state(side, w["t"]) == "rest")
        rec = {"lead_subs": lead_subs, "rest_subs": rest_subs,
               "lead_s": round(durs[side]["lead"], 1),
               "rest_s": round(durs[side]["rest"], 1),
               "verdict": None}
        if (rec["lead_s"] >= SBS_MIN_STATE_S
                and rec["rest_s"] >= SBS_MIN_STATE_S
                and lead_subs + rest_subs >= SBS_MIN_SUBS):
            lead_rate = lead_subs / rec["lead_s"]
            rest_rate = rest_subs / rec["rest_s"]
            if lead_rate >= SBS_ROTATE_RATIO * rest_rate \
                    and lead_subs >= 3:
                rec["verdict"] = "vezetve forgatnak"
            elif lead_rate <= SBS_HOLD_RATIO * rest_rate \
                    and rest_subs >= 3:
                rec["verdict"] = "vezetve sem nyúlnak a sorhoz"
        out[side] = rec
    return out


# Csere-büntetés: a csere-lyuk utáni ennyi másodpercen belüli gól még
# a lyuk számlájára megy; ennyi kapott gól kell a büntetett, és ennyi
# lyuk-másodperc a büntetlenül megúszott ítélethez.
GPN_TAIL_S = 3.0
GPN_MIN_GOALS = 2
GPN_ESCAPE_MIN_S = 20.0


def gap_punishment(match: Match,
                   config: Optional[TacticsConfig] = None) -> dict:
    """Csere-büntetés: GÓLBA KERÜLNEK-E a csere-lyukak.

    A csere-lyukak (sub_gaps) a kitettséget mérik — ez a megfizetett
    árát: a rövid (cserés, nem kiállításos) öt fős szakaszok alatt és
    közvetlenül utánuk kapott gólokat. Van, aki éveken át lyukasan
    cserél és megússza; és van, akinél a lyuk rendre a hálóban
    végződik.

    Edzőileg: akinél a csere-lyuk gólba kerül, ott a csere-pillanat
    célzottan támadható — gyors középkezdés, azonnali befejezés; a
    saját oldalon pedig nem elég mérni a lyukat: ha már gól esett
    belőle, a csere-ütem javítása sürgős edzés-téma.

    Visszatérés csapatonként (a VÉDEKEZŐ, cserélő oldal): {"gap_s",
    "gaps", "conceded", "verdict"} — a verdict "a csere-lyukaik
    gólba kerülnek" (GPN_MIN_GOALS-tól), "a csere-lyukakat
    büntetlenül megússzák" (GPN_ESCAPE_MIN_S-nyi lyuk, gól nélkül),
    különben None.
    """
    from .event_detection import EventType, detect_shots
    from .rules import PP_MIN_S, field_count_timeline

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    tl = field_count_timeline(match)
    empty = {side: {"gap_s": 0.0, "gaps": 0, "conceded": 0,
                    "verdict": None} for side in ("home", "away")}
    if len(tl) < 2:
        return empty
    win_frames = tl[1]["start_frame"] - tl[0]["start_frame"]
    win_s = win_frames / fps
    goals = [(e.t, e.team.value) for e in detect_shots(match, config)
             if e.type == EventType.GOAL]
    tail = round(GPN_TAIL_S * fps)

    out = empty
    for side, other in (("home", "away"), ("away", "home")):
        rec = out[side]
        run_s = 0.0
        run_start = None
        spans = []
        for w in tl + [None]:
            active = (w is not None and w[side] <= 4 + 1
                      and w[side] < w[other])
            if active:
                if run_start is None:
                    run_start = w["start_frame"]
                run_s += win_s
            else:
                if SBG_MIN_WINDOW_S <= run_s < PP_MIN_S:
                    end = run_start + round(run_s * fps)
                    spans.append((run_start, end))
                    rec["gap_s"] += run_s
                run_s = 0.0
                run_start = None
        rec["gap_s"] = round(rec["gap_s"], 1)
        rec["gaps"] = len(spans)
        for (a, b) in spans:
            rec["conceded"] += sum(
                1 for (t, tm) in goals
                if tm == other and a <= t <= b + tail)
        if rec["conceded"] >= GPN_MIN_GOALS:
            rec["verdict"] = "a csere-lyukaik gólba kerülnek"
        elif rec["gap_s"] >= GPN_ESCAPE_MIN_S and rec["conceded"] == 0:
            rec["verdict"] = "a csere-lyukakat büntetlenül megússzák"
    return out


# Forgatott-poszt: ennyi poszthoz kötött lecserélés kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy a
# forgatásuk egy posztra jár.
SBR_MIN_OUTS = 3
SBR_SHARE_PCT = 60.0


def substituted_roles(match: Match,
                      config: Optional[TacticsConfig] = None) -> dict:
    """Forgatott-poszt: MELYIK POSZTJUKAT cserélik.

    A cserehullám-rétegek a hullámot nézik — ez a posztot: a
    lecserélt játékosokat a posztjukhoz írja. Így látszik, melyik
    posztjukon forognak (ott mindig friss ember áll), és melyiken
    nem (ott a fáradás felhalmozódik).

    Edzőileg ez a fárasztás-terv iránya: a sokat forgatott posztra
    fárasztásra építeni hiba — oda mindig friss ember jön; a
    terhelés-csapdát a NEM forgatott posztokra kell tenni. Saját
    csapatra: a forgatás-térkép a terhelés-elosztás tükre.

    Visszatérés csapatonként: {"outs" (poszthoz kötött lecserélés),
    "roles": {poszt: darab}, "main_role", "share_pct", "verdict"} —
    az ítélet None, ha nincs meg az SBR_MIN_OUTS, vagy egyik poszt
    sem éri el az SBR_SHARE_PCT-t.
    """
    from .roles import estimate_positions

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)

    out: dict = {side: {"outs": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for ev in detect_substitutions(match, config):
        side = ev["team"]
        for tid in ev["out_ids"]:
            rec_role = roles[side].get(tid)
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec = out[side]
            rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1
            rec["outs"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["outs"] >= SBR_MIN_OUTS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["outs"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= SBR_SHARE_PCT:
                rec["verdict"] = (
                    f"a forgatásuk a(z) {poszt} posztra jár "
                    f"({share:.0f}%, {rec['outs']} lecserélésből) — "
                    "ott mindig friss ember áll: a fárasztást a NEM"
                    " forgatott posztjaikra kell tervezni")
    return out
