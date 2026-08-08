"""Gól-sorozatok (momentum) felismerése — a meccs fordulópontjai.

A meccset gyakran nem az összpontszám, hanem néhány SOROZAT dönti el:
amikor az egyik csapat több gólt szerez válasz nélkül (pl. egy 4-0-s
széria), miközben a másik oldalon elakad a játék. Ezek a leg-
beszédesebb edzői pillanatok — érdemes visszanézni, mi működött, és a
másik oldalon mi állt le (időkérés kellett-e, védekezés-váltás jött-e).

A felismerés a felismert gólokból számol (event_detection.detect_shots),
időrendben: egy sorozat egy csapat egymás utáni, VÁLASZ NÉLKÜLI góljai.
A RUN_MIN-nél hosszabb sorozatot jelöljük meg, a pillanatnyi állással
együtt. Tiszta adatfeldolgozás, videó nélkül tesztelhető.
"""

from __future__ import annotations

import math
from typing import Optional

from ..models.tracking import Match, Team

# Ennyi válasz nélküli gól már említésre méltó sorozat.
RUN_MIN = 3


def scoring_runs(match: Match, config=None,
                 min_len: int = RUN_MIN) -> list[dict]:
    """Válasz nélküli gól-sorozatok a meccsen, időrendben.

    Visszatérés: [{"team", "length", "start_frame", "end_frame",
    "score_before": [h, a], "score_after": [h, a]}] — a score a HAZAI–
    VENDÉG állás a sorozat előtt/után.
    """
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    goals = [(e.t, e.team) for e in detect_shots(match, config)
             if e.type == EventType.GOAL]
    goals.sort(key=lambda g: g[0])

    runs: list[dict] = []
    score = {Team.HOME: 0, Team.AWAY: 0}
    # Aktuális sorozat: (csapat, hossz, kezdő_t, utolsó_t, állás_a_kezdet_előtt)
    cur_team = None
    cur_len = 0
    cur_start = 0
    cur_last = 0
    score_before = [0, 0]

    def flush():
        if cur_team is not None and cur_len >= min_len:
            runs.append({
                "team": cur_team.value,
                "length": cur_len,
                "start_frame": cur_start,
                "end_frame": cur_last,
                "score_before": list(score_before),
                "score_after": [score[Team.HOME], score[Team.AWAY]],
            })

    for (t, team) in goals:
        if team == cur_team:
            cur_len += 1
            cur_last = t
        else:
            flush()
            cur_team = team
            cur_len = 1
            cur_start = t
            cur_last = t
            score_before = [score[Team.HOME], score[Team.AWAY]]
        score[team] += 1
    flush()
    return runs


# A sorozat ELŐTTI ennyi másodpercet is nézzük az okok kereséséhez (egy
# védekezés-váltás vagy kiállítás hatása kis késéssel csapódik le gólokban).
CONTEXT_LEAD_S = 20.0
# Az ellenfél tempója akkor számít "esésnek", ha a sorozat alatt a meccs-
# átlagának ennyi-szerese ALÁ süllyed.
TEMPO_DROP_RATIO = 0.9


def annotate_runs(match: Match, runs: Optional[list[dict]] = None,
                  config=None) -> list[dict]:
    """A gól-sorozatok LEHETSÉGES OKAI — az edzői "miért" réteg.

    Egy 4-0-s szériánál a legfontosabb kérdés nem a "mikor", hanem a
    "miért történt". A már meglévő elemző rétegeket vetjük össze a sorozat
    idősávjával ([start-CONTEXT_LEAD_S, end]), és minden sorozathoz
    "context" címkelistát adunk:

    - "emberelőnyben" — az ellenfél emberhátrányban volt (kiállítás);
    - "7 a 6-tal" — a sorozatot futó csapat üres kapuval, plusz mezőny-
      játékossal támadott;
    - "az ellenfél védekezés-váltása után" — az ellenfél épp formát
      váltott (az új felállás még nem ült össze);
    - "az ellenfél tempó-esése mellett" — az ellenfél mozgás-sebessége a
      sorozat alatt a saját meccs-átlaga alá esett (fáradás jele);
    - "az ellenfél időkérése ellenére" — az ellenfél a sorozat közben időt
      kért, de a széria az időkérés UTÁN is folytatódott;
    - "cserehullám után" — a sorozatot futó csapat közvetlenül előtte
      frissített (cserehullám a felvezető ablakban).

    A jelek egymástól függetlenek, több is állhat egy sorozat mellett;
    jel nélkül a context üres lista. Minden részelemzés hibatűrő: egy
    elromló réteg nem viszi el a többit."""
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    if runs is None:
        runs = scoring_runs(match, config)
    if not runs:
        return runs

    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    lead = round(CONTEXT_LEAD_S * fps)

    # Az elemző rétegek egyszer futnak le (nem sorozatonként) — hibatűrően.
    def _safe(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except Exception:
            return []

    from .goalkeeper import detect_empty_net
    from .rules import detect_powerplay
    from .scouting import formation_switch_profile
    from .stats import compute_intensity_timeline
    from .stoppages import detect_stoppages
    from .substitutions import detect_substitutions

    powerplays = _safe(detect_powerplay, match)
    empty_nets = _safe(detect_empty_net, match, config)
    timeouts = [t_ for t_ in _safe(detect_stoppages, match, config)
                if t_["kind"] == "időkérés"]
    sub_waves = _safe(detect_substitutions, match, config)
    switches = {t: _safe(formation_switch_profile, match, t, config)
                for t in (Team.HOME, Team.AWAY)}
    intensity = _safe(compute_intensity_timeline, match)

    # Az ellenfél tempó-viszonyításához a meccs-átlag (ablakok átlaga).
    avg_ms = {"home": 0.0, "away": 0.0}
    for side in ("home", "away"):
        vals = [w[f"{side}_avg_ms"] for w in intensity
                if w.get(f"{side}_avg_ms", 0) > 0]
        if vals:
            avg_ms[side] = sum(vals) / len(vals)

    def overlaps(a0, a1, b0, b1):
        return a0 <= b1 and b0 <= a1

    total = match.frames[-1].t if match.frames else 0
    for r in runs:
        team = r["team"]                       # "home" / "away"
        opp = "away" if team == "home" else "home"
        opp_team = Team.AWAY if team == "home" else Team.HOME
        w0 = max(0, r["start_frame"] - lead)   # a sorozat + felvezetése
        w1 = r["end_frame"]
        ctx: list[str] = []

        # Kiállítás: az ELLENFÉL volt emberhátrányban a sorozat idején.
        if any(p["team_down"] == opp and
               overlaps(w0, w1, p["start_frame"], p["end_frame"])
               for p in powerplays):
            ctx.append("emberelőnyben")

        # 7 a 6: a sorozatot futó csapat üres kapuval támadott.
        if any(e["team"] == team and
               overlaps(w0, w1, e["start_frame"], e["end_frame"])
               for e in empty_nets):
            ctx.append("7 a 6-tal")

        # Az ellenfél védekezés-váltása közvetlenül a sorozat előtt/alatt.
        if any(w0 <= s["t"] <= w1 for s in switches.get(opp_team, [])):
            ctx.append("az ellenfél védekezés-váltása után")

        # Az ellenfél időt kért a sorozat közben, de a széria az időkérés
        # UTÁN is folytatódott (jött még gól) — a megszakítás nem segített.
        if any(t_["likely_team"] == opp
               and r["start_frame"] <= t_["start_frame"] <= w1
               and t_["end_frame"] < w1
               for t_ in timeouts):
            ctx.append("az ellenfél időkérése ellenére")

        # A sorozatot futó csapat közvetlenül előtte frissített (csere).
        if any(sw["team"] == team and w0 <= sw["t"] <= r["start_frame"]
               for sw in sub_waves):
            ctx.append("cserehullám után")

        # Az ellenfél tempó-esése: a sorozattal átfedő intenzitás-ablakokban
        # az átlagsebessége érezhetően a meccs-átlaga alatt volt.
        if intensity and avg_ms[opp] > 0:
            n_win = len(intensity)
            win_frames = max(1, (total + 1) // n_win) if n_win else 1
            in_run = [w[f"{opp}_avg_ms"] for i, w in enumerate(intensity)
                      if w.get(f"{opp}_avg_ms", 0) > 0 and
                      overlaps(w0, w1, w["start_frame"],
                               w["start_frame"] + win_frames - 1)]
            if in_run and (sum(in_run) / len(in_run)
                           < TEMPO_DROP_RATIO * avg_ms[opp]):
                ctx.append("az ellenfél tempó-esése mellett")

        r["context"] = ctx
    return runs


def score_progression(match: Match, config=None) -> dict:
    """Vezetés-alakulás: az állás menete a felismert gólokból.

    A meccs izgalmát nem az összpontszám, hanem az ÁLLÁS MENETE adja: ki
    vezetett, mennyivel, hányszor fordult a meccs. Ezt számoljuk a
    gólokból (időrend):

    - biggest_lead: {"home", "away"} — a legnagyobb előny csapatonként;
    - lead_changes: hányszor váltott a vezetés (döntetlenből valakihez
      vagy egyik csapattól a másikhoz);
    - lead_time_s: {"home","away","tie"} — mennyi ideig vezetett k(a
      gólok közti idő az akkori állás szerint), a meccs végéig.

    Kevés/nincs gólnál nulla/üres értékek."""
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    goals = sorted((e.t, e.team) for e in detect_shots(match, config)
                   if e.type == EventType.GOAL)
    end_t = match.frames[-1].t if match.frames else 0

    score = {Team.HOME: 0, Team.AWAY: 0}
    biggest = {"home": 0, "away": 0}
    lead_time = {"home": 0.0, "away": 0.0, "tie": 0.0}
    lead_changes = 0
    prev_leader = "tie"
    last_real_leader = None  # az utolsó tényleges vezető (nem döntetlen)
    prev_t = match.frames[0].t if match.frames else 0
    # Fordítás: a legnagyobb hátrány, amiből a csapat később VEZETÉSBE
    # került (a hátrány-számláló a vezetés megszerzésekor nullázódik).
    comeback = {"home": 0, "away": 0}
    cur_deficit = {"home": 0, "away": 0}

    def leader() -> str:
        if score[Team.HOME] > score[Team.AWAY]:
            return "home"
        if score[Team.AWAY] > score[Team.HOME]:
            return "away"
        return "tie"

    for (t, team) in goals:
        # A gólig eltelt időt az EDDIGI állás vezetőjéhez írjuk.
        lead_time[prev_leader] += max(0, t - prev_t) / fps
        prev_t = t
        score[team] += 1
        lead = score[Team.HOME] - score[Team.AWAY]
        biggest["home"] = max(biggest["home"], lead)
        biggest["away"] = max(biggest["away"], -lead)
        cur = leader()
        # Vezetés-VÁLTÁS csak a két csapat közti fordulás (a nyitógól,
        # döntetlenből vezetéshez, nem az) — döntetleneken átnézve.
        if cur != "tie":
            if last_real_leader is not None and cur != last_real_leader:
                lead_changes += 1
            last_real_leader = cur
        prev_leader = cur
        # Fordítás-követés: vezetéskor az addigi hátrány "teljesítve".
        if lead > 0:
            comeback["home"] = max(comeback["home"], cur_deficit["home"])
            cur_deficit["home"] = 0
        elif lead < 0:
            comeback["away"] = max(comeback["away"], cur_deficit["away"])
            cur_deficit["away"] = 0
        if lead < 0:
            cur_deficit["home"] = max(cur_deficit["home"], -lead)
        elif lead > 0:
            cur_deficit["away"] = max(cur_deficit["away"], lead)
    # A meccs végéig tartó utolsó szakasz.
    lead_time[prev_leader] += max(0, end_t - prev_t) / fps

    return {
        "biggest_lead": biggest,
        "lead_changes": lead_changes,
        "lead_time_s": {k: round(v, 1) for k, v in lead_time.items()},
        "comeback": comeback,
        "final": [score[Team.HOME], score[Team.AWAY]],
    }


# Kezdés-profil: a meccs ELSŐ ennyi (összesített) góljából áll a "korai
# állás" — abszolút idő nélkül, csak a gól-sorrendből, ezért rövid/részleges
# felvételen is stabil.
OPENING_EARLY_GOALS = 6


def opening_profile(match: Match, config=None,
                    early_goals: int = OPENING_EARLY_GOALS) -> dict:
    """Kezdés-profil: ki szerzi a meccs ELSŐ gólját, és milyen a korai állás.

    A meccs nyitánya beszédes: a gyorsan vezetést szerző csapat rákényszeríti
    a saját tempóját, a lassan induló ellen a korai előny megtörheti a
    tervét. Csak a felismert gólok SORRENDJÉBŐL dolgozunk (abszolút idő
    nélkül) — ezért rövid vagy részleges felvételen is stabil, más, mint a
    félidő-mérleg (egész 1. félidő) vagy a szünet-kezdés (2. félidő eleje).

    - scores_first: az adott csapat szerezte-e a meccs első gólját
      (None, ha egy gól sincs);
    - early_for / early_against: a csapat és az ellenfél góljai a meccs
      első `early_goals` (összesített) góljából;
    - early_goals_seen: hány gólt néztünk (a korai ablak tényleges hossza).

    Visszatérés csapatonként a fenti kulcsokkal.
    """
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    goals = sorted((e.t, e.team) for e in detect_shots(match, config)
                   if e.type == EventType.GOAL)
    first_scorer = goals[0][1].value if goals else None
    window = goals[:max(0, early_goals)]
    cnt = {"home": 0, "away": 0}
    for (_t, team) in window:
        cnt[team.value] += 1
    seen = len(window)

    out: dict = {}
    for s in ("home", "away"):
        other = "away" if s == "home" else "home"
        out[s] = {
            "scores_first": (first_scorer == s
                             if first_scorer is not None else None),
            "early_for": cnt[s],
            "early_against": cnt[other],
            "early_goals_seen": seen,
        }
    return out


# Előny-őrzés: ekkora (gólnyi) vezetéstől beszélünk "ellépésről" — az
# ennél kisebb ingadozás a meccs normál hullámzása.
LEAD_HELD_MIN = 3


def lead_protection(match: Match, config=None,
                    lead_min: int = LEAD_HELD_MIN) -> dict:
    """Előny-őrzés: a meccs közbeni legnagyobb vezetés vs a végeredmény.

    A gól-idővonalból csapatonként kiszámoljuk a meccs közben elért
    LEGNAGYOBB vezetést és a záró különbséget. Aki `lead_min`+ gólos
    előnyt is elenged (a végén nem nyer), az mentálisan törékeny —
    ellene hátrányban sem szabad feladni; aki az ellépett előnyt mindig
    megtartja, azt nem szabad hagyni ellépni.

    Visszatérés csapatonként:
    - max_lead: a meccs közbeni legnagyobb vezetés (0, ha sosem vezetett);
    - final_margin: záró gólkülönbség (negatív = vereség);
    - led: elérte-e a `lead_min` gólos vezetést;
    - blown: led ÉS a végén nem nyert (elengedett vezetés);
    - verdict: None (nem volt `lead_min`+ vezetés) / "megtartotta" /
      "elengedte".
    """
    prog = score_progression(match, config)
    fh, fa = prog["final"]

    out: dict = {}
    for side, final in (("home", fh - fa), ("away", fa - fh)):
        max_lead = prog["biggest_lead"][side]
        led = max_lead >= lead_min
        blown = led and final <= 0
        out[side] = {
            "max_lead": max_lead,
            "final_margin": final,
            "led": led,
            "blown": blown,
            "verdict": (None if not led
                        else ("elengedte" if blown else "megtartotta")),
        }
    return out


# Hajrá-elemzés: az utolsó ennyi másodperc számít "hajrának", és csak
# ennél hosszabb felvételen értelmezzük (rövid klipnél az egész a "hajrá").
CLUTCH_WINDOW_S = 300.0
CLUTCH_MIN_DURATION_S = 600.0


def clutch_performance(match: Match, config=None) -> dict:
    """Hajrá-teljesítmény: ki bírja jobban a meccs végét.

    Az utolsó CLUTCH_WINDOW_S másodperc gólmérlege csapatonként, a
    hajrá kezdetén álló eredménnyel. A "close" jelzi, hogy a hajrá
    szoros állásról indult (legfeljebb 3 gól különbség) — ilyenkor a
    hajrá-mérleg a nyomás alatti teljesítményről szól.

    Rövid felvételen (CLUTCH_MIN_DURATION_S alatt) nem értelmezzük:
    {"available": False}. Egyébként: {"available": True, "window_s",
    "close", "start_score": [h, a], "home": {"goals"}, "away": {"goals"}}.
    """
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    total = len(match.frames)
    if total / fps < CLUTCH_MIN_DURATION_S:
        return {"available": False}
    end_t = match.frames[-1].t
    win_start = end_t - CLUTCH_WINDOW_S * fps

    goals = sorted((e.t, e.team) for e in detect_shots(match, config)
                   if e.type == EventType.GOAL)
    start_score = [0, 0]
    clutch = {"home": 0, "away": 0}
    for (t, team) in goals:
        side = 0 if team == Team.HOME else 1
        if t < win_start:
            start_score[side] += 1
        else:
            clutch["home" if side == 0 else "away"] += 1
    return {
        "available": True,
        "window_s": CLUTCH_WINDOW_S,
        "close": abs(start_score[0] - start_score[1]) <= 3,
        "start_score": start_score,
        "home": {"goals": clutch["home"]},
        "away": {"goals": clutch["away"]},
    }


def clutch_scorers(match: Match, config=None) -> dict:
    """Hajrá-emberek: KI szerzi a gólokat a meccs utolsó CLUTCH_WINDOW_S
    másodpercében — kire adjuk a labdát a hajrában, illetve kire kell a
    hajrában fokozottan figyelni.

    A clutch_performance csapat-mérlegének egyéni bontása: a hajrá-ablakban
    esett gólokat a lövőnek írjuk jóvá. Rövid felvételen (CLUTCH_MIN_
    DURATION_S alatt) üres.

    Visszatérés csapatonként:
      {"players": [{"player_id", "jersey", "goals"}], "total"} — a
    hajrá-gólok szerint csökkenően."""
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    total = len(match.frames)
    out = {s: {"players": [], "total": 0} for s in ("home", "away")}
    if total / fps < CLUTCH_MIN_DURATION_S or total == 0:
        return out
    end_t = match.frames[-1].t
    win_start = end_t - CLUTCH_WINDOW_S * fps

    jersey: dict = {}
    for f in match.frames:
        for p in f.players:
            if p.jersey_number is not None and p.track_id not in jersey:
                jersey[p.track_id] = p.jersey_number

    tally: dict = {"home": {}, "away": {}}
    for e in detect_shots(match, config):
        if e.type != EventType.GOAL or e.player_id is None:
            continue
        if e.t < win_start:
            continue
        side = e.team.value
        tally[side][e.player_id] = tally[side].get(e.player_id, 0) + 1

    for s in ("home", "away"):
        players = [{"player_id": tid, "jersey": jersey.get(tid), "goals": n}
                   for tid, n in sorted(tally[s].items(),
                                        key=lambda kv: -kv[1])]
        out[s] = {"players": players, "total": sum(tally[s].values())}
    return out


def halftime_score(match: Match, config=None,
                   half_t: int | None = None) -> dict | None:
    """Félidei állás a felismert gólokból és a félidő-határból.

    A határ a felismert félidei szünet (halftime.detect_halftime) vagy a
    half_t paraméter. Ha egyik sincs, None — inkább nincs adat, mint
    hamis "félidei eredmény" a felezőpontból.

    Visszatérés: {"half_t", "home", "away"} vagy None.
    """
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    if half_t is None:
        try:
            from .halftime import detect_halftime
            half_t = detect_halftime(match)
        except Exception:
            half_t = None
    if half_t is None:
        return None
    score = {"home": 0, "away": 0}
    for e in detect_shots(match, config):
        if e.type == EventType.GOAL and e.t < half_t:
            score[e.team.value] += 1
    return {"half_t": half_t, "home": score["home"], "away": score["away"]}


# Meccs-esély: a gólkülönbség súlya a hátralévő idő gyökével nő (egy
# késői gól többet ér) — az érzékenységet a WP_K állítja.
WP_K = 2.2
WP_MIN_REMAINING_S = 30.0


def win_probability(match: Match, config=None) -> dict:
    """Meccs-esély görbe: P(hazai győzelem) a felismert gólok mentén.

    Egyszerű, MAGYARÁZHATÓ modell (nem tanult): az esély a gólkülönbség
    és a hátralévő idő függvénye — ugyanakkora előny a hajrában sokkal
    többet ér, mint az elején. Képlet: szigmoid(WP_K * diff /
    sqrt(hátralévő perc)). A felvétel hosszát vesszük meccs-hossznak.

    Visszatérés: {"timeline": [{"t_s", "diff", "p_home"}],
    "final_p_home", "turning_point": {"t_s", "from_p", "to_p"} | None}
    — a fordulópont a legnagyobb esély-ugrás pillanata (min. 2 gólnál).
    """
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    total_s = len(match.frames) / fps if match.frames else 0.0
    goals = sorted((e.t, e.team.value) for e in detect_shots(match, config)
                   if e.type == EventType.GOAL)

    def p_home(diff: int, t_s: float) -> float:
        remaining_min = max(WP_MIN_REMAINING_S, total_s - t_s) / 60.0
        z = WP_K * diff / math.sqrt(remaining_min)
        return round(1.0 / (1.0 + math.exp(-z)), 3)

    timeline = [{"t_s": 0.0, "diff": 0, "p_home": 0.5}]
    diff = 0
    for (t, side) in goals:
        diff += 1 if side == "home" else -1
        t_s = t / fps
        timeline.append({"t_s": round(t_s, 1), "diff": diff,
                         "p_home": p_home(diff, t_s)})

    turning = None
    for prev, cur in zip(timeline, timeline[1:]):
        swing = abs(cur["p_home"] - prev["p_home"])
        if turning is None or swing > turning[0]:
            turning = (swing, {"t_s": cur["t_s"], "from_p": prev["p_home"],
                               "to_p": cur["p_home"]})
    return {
        "timeline": timeline,
        "final_p_home": timeline[-1]["p_home"],
        "turning_point": (turning[1]
                          if turning and len(goals) >= 2 else None),
    }


def goal_responses(match: Match, config=None) -> dict:
    """Válasz-gólok: milyen gyorsan felel egy csapat a kapott gólra.

    Minden kapott gól után megnézzük, mennyi idő telt el a csapat KÖVETKEZŐ
    saját góljáig (ha közben az ellenfél újra betalál, az új kapott gól
    számít a kiindulásnak). A gyors válasz a mentális stabilitás jele; a
    lassú (vagy hiányzó) válasz sorozat-veszély.

    Visszatérés csapatonként: {"responses", "avg_s", "fastest_s"} —
    avg_s/fastest_s None, ha nincs megválaszolt kapott gól.
    """
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    goals = sorted((e.t, e.team.value) for e in detect_shots(match, config)
                   if e.type == EventType.GOAL)

    waits = {"home": [], "away": []}
    pending: dict = {}  # side -> az utolsó MEGVÁLASZOLATLAN kapott gól ideje
    for (t, side) in goals:
        other = "away" if side == "home" else "home"
        # A gólt szerző csapat megválaszolja a függő kapott gólját.
        if side in pending:
            waits[side].append((t - pending.pop(side)) / fps)
        # Az ellenfélnél ez a gól új (felülíró) kapott gól.
        pending[other] = t

    out = {}
    for side in ("home", "away"):
        w = waits[side]
        out[side] = {
            "responses": len(w),
            "avg_s": round(sum(w) / len(w), 1) if w else None,
            "fastest_s": round(min(w), 1) if w else None,
        }
    return out


# Szoros meccs: legfeljebb ekkora záró különbség, és legalább ennyi
# összesített gól (részleges felvételen a "0-0 döntetlen" nem ítélet).
CLOSE_GAME_MARGIN = 2
CLOSE_GAME_MIN_GOALS = 6


def close_game_record(match: Match, config=None) -> dict:
    """Szoros meccs-mérleg: hogyan végződött az 1-2 gólos meccs.

    A szoros meccs a mentális erő mérlege: itt nem a tudás, hanem a
    hajrá-higgadtság dönt. Csapatonként megmondjuk, hogy EZ a meccs
    szoros volt-e, és mi lett a vége — a felderítés meccsek közt
    összegzi (ki hozza, ki bukja a szorosat).

    Visszatérés csapatonként: {"margin", "verdict"} — margin a záró
    gólkülönbség (negatív = vereség); verdict None (nem szoros, vagy
    kevés a felismert gól), "szoros győzelem", "szoros vereség" vagy
    "döntetlen".
    """
    prog = score_progression(match, config)
    fh, fa = prog["final"]
    total = fh + fa

    out: dict = {}
    for side, margin in (("home", fh - fa), ("away", fa - fh)):
        verdict = None
        if total >= CLOSE_GAME_MIN_GOALS:
            if margin == 0:
                verdict = "döntetlen"
            elif 0 < abs(margin) <= CLOSE_GAME_MARGIN:
                verdict = ("szoros győzelem" if margin > 0
                           else "szoros vereség")
        out[side] = {"margin": margin, "verdict": verdict}
    return out


# Sorozat-törés: ennyi elszenvedett sorozattól ítélünk átlagot, és
# ekkora átlag-hossztól számít "elfutónak" a sorozat.
RUN_CONTAIN_MIN = 2
RUN_CONTAIN_LONG = 4.5


def run_containment(match: Match, config=None) -> dict:
    """Sorozat-törés: az ellenfél sorozatait ki meddig hagyja elfutni.

    A sorozatok (scoring_runs) réteg védekező-mentális párja: nem az
    érdekel, ki fut 3-0-kat, hanem hogy az ELSZENVEDETT 3+ gólos
    sorozat hol áll meg. Aki a sorozatot rendre 3-nál töri (időkérés,
    váltás, higgadt gól), az nem esik szét; akinél a 3-0-ból rendre
    5-6-0 lesz, ott a mini-sorozat megnyomása duplán kifizetődik — és
    az időkérése sem mentőöv.

    Visszatérés csapatonként: {"made", "made_goals", "suffered",
    "suffered_goals", "avg_len"} — made/suffered a futott/elszenvedett
    3+ gólos sorozatok száma, a *_goals az összhosszuk; avg_len az
    elszenvedett sorozatok átlagos hossza, None kevés
    (RUN_CONTAIN_MIN alatti) elszenvedett sorozatnál.
    """
    runs = scoring_runs(match, config)
    out = {}
    for side in ("home", "away"):
        own = [r for r in runs if r["team"] == side]
        other = [r for r in runs if r["team"] != side]
        sg = sum(r["length"] for r in other)
        out[side] = {
            "made": len(own),
            "made_goals": sum(r["length"] for r in own),
            "suffered": len(other),
            "suffered_goals": sg,
            "avg_len": (round(sg / len(other), 1)
                        if len(other) >= RUN_CONTAIN_MIN else None)}
    return out


# Holtpont-mérleg: ennyi góllal lezárt döntetlen-állástól ítélünk.
PARITY_MIN_TIES = 3


def parity_breaks(match: Match, config=None) -> dict:
    """Holtpont-mérleg: döntetlen állásról ki lép el góllal.

    A vezetés-váltás réteg irány-párja: nem az érdekel, hányszor
    fordult a meccs, hanem hogy az egál-pillanatok (a 0-0-tól minden
    kiegyenlítés) után KI szerzi a következő gólt. A holtpont a
    legtisztább nyomás-teszt: a következő gól a fejekben dől el. Aki a
    holtpontokat rendre elviszi, azzal nem szabad egálba összecsúszni;
    aki rendre elengedi, azt utolérni elég — onnan ő remeg.

    Visszatérés csapatonként: {"ties", "won", "rate_pct"} — ties a
    góllal lezárt döntetlen-állások száma (a két oldalon azonos), won
    ebből az általa elvitt holtpontok; rate_pct None, ha kevés
    (PARITY_MIN_TIES alatti) a holtpont.
    """
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    goals = sorted(
        (e.t, e.team.value) for e in
        detect_shots(match, config or TacticsConfig())
        if e.type == EventType.GOAL)
    score = {"home": 0, "away": 0}
    won = {"home": 0, "away": 0}
    tied = True  # a 0-0 is holtpont
    ties = 0
    for _, side in goals:
        if tied:
            ties += 1
            won[side] += 1
        score[side] += 1
        tied = score["home"] == score["away"]
    out = {}
    for side in ("home", "away"):
        out[side] = {
            "ties": ties, "won": won[side],
            "rate_pct": (round(100.0 * won[side] / ties, 1)
                         if ties >= PARITY_MIN_TIES else None)}
    return out


# Félidei hátrányból fordítás: ennyi felismert gól kell az ítélethez
# (részleges felvételen a hamis "0-0" nem ítélet).
HT_COMEBACK_MIN_GOALS = 6


def halftime_comeback(match: Match, config=None) -> dict:
    """Félidei hátrányból fordítás: a félidei állás vs a végeredmény.

    A mentális profil tagja a szoros meccs-mérleg mellett: aki félidei
    hátrányból rendre fordít, azt a félidei előny nem töri meg — ellene
    a vezetés birtokában is 60 perces meccsre kell készülni; aki
    hátrányból sosem jön vissza, annál a félidei előny majdnem kész
    győzelem. A felderítés meccsek közt összegzi.

    Visszatérés csapatonként: {"ht_margin", "final_margin", "verdict"}
    — verdict None (nincs félidő-jel, kevés gól, vagy a félidőnél nem
    állt hátrányban), "fordította" (győzelem), "mentette" (döntetlen)
    vagy "elbukta" (vereség).
    """
    from .event_detection import EventType, detect_shots
    from .halftime import detect_halftime
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    empty = {"ht_margin": None, "final_margin": None, "verdict": None}
    out = {"home": dict(empty), "away": dict(empty)}
    ht = detect_halftime(match)
    if ht is None:
        return out
    goals = [(e.t, e.team.value) for e in detect_shots(match, config)
             if e.type == EventType.GOAL]
    if len(goals) < HT_COMEBACK_MIN_GOALS:
        return out
    ht_h = sum(1 for t, sd in goals if sd == "home" and t <= ht)
    ht_a = sum(1 for t, sd in goals if sd == "away" and t <= ht)
    fin_h = sum(1 for _, sd in goals if sd == "home")
    fin_a = sum(1 for _, sd in goals if sd == "away")
    for side, htm, finm in (("home", ht_h - ht_a, fin_h - fin_a),
                            ("away", ht_a - ht_h, fin_a - fin_h)):
        rec = out[side]
        rec["ht_margin"] = htm
        rec["final_margin"] = finm
        if htm < 0:
            rec["verdict"] = ("fordította" if finm > 0 else
                              "mentette" if finm == 0 else "elbukta")
    return out


# Gól utáni elalvás: az ennyi másodpercen belül érkező ellenfél-gól
# számít "azonnali válasznak" — a középkezdés utáni koncentráció-hiba.
POST_GOAL_QUICK_S = 40.0
# Ennyi saját góltól ítélünk arányt.
POST_GOAL_MIN_GOALS = 3


def post_goal_lapses(match: Match, config=None,
                     quick_s: float = POST_GOAL_QUICK_S) -> dict:
    """Gól utáni elalvás: a saját gól után azonnal visszakapott gólok.

    A válasz-idő réteg (goal_responses) párja, a másik irányból: nem az
    érdekel, milyen gyorsan válaszolunk a kapott gólra, hanem hogy a
    SAJÁT góljaink után hányszor kapunk `quick_s` másodpercen belül
    azonnali választ. A sok gyors visszakapott gól a középkezdés utáni
    elalvás jele — a szerzett előny rendre azonnal elolvad.

    Visszatérés csapatonként: {"goals", "quick_replies", "rate_pct"} —
    rate_pct None, ha kevés (POST_GOAL_MIN_GOALS alatti) a saját gól.
    """
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    goals = sorted((e.t, e.team.value) for e in detect_shots(match, config)
                   if e.type == EventType.GOAL)

    scored = {"home": 0, "away": 0}
    quick = {"home": 0, "away": 0}
    for (t1, s1), (t2, s2) in zip(goals, goals[1:]):
        scored[s1] += 1
        if s2 != s1 and (t2 - t1) / fps <= quick_s:
            quick[s1] += 1
    if goals:
        scored[goals[-1][1]] += 1

    out = {}
    for side in ("home", "away"):
        out[side] = {
            "goals": scored[side],
            "quick_replies": quick[side],
            "rate_pct": (round(100.0 * quick[side] / scored[side], 1)
                         if scored[side] >= POST_GOAL_MIN_GOALS else None),
        }
    return out


def goal_droughts(match: Match, config=None) -> dict:
    """Gólcsend: a leghosszabb saját gól nélküli időszak csapatonként.

    A felvétel elejétől az első gólig, a gólok közti szakaszokon át az
    utolsó góltól a felvétel végéig nézzük a leghosszabb szakaszt. Ebből
    látszik, mikor "állt le" a támadójáték — a visszanézés kiindulópontja.

    Visszatérés csapatonként: {"longest_s", "start_s", "end_s"} — a
    leghosszabb gólcsend hossza és helye másodpercben; gól nélküli
    csapatnál a teljes felvétel.
    """
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    total_s = (len(match.frames) / fps) if match.frames else 0.0
    goals = {"home": [], "away": []}
    for e in detect_shots(match, config):
        if e.type == EventType.GOAL:
            goals[e.team.value].append(e.t / fps)

    out = {}
    for side in ("home", "away"):
        ts = sorted(goals[side])
        # Szakasz-határok: felvétel eleje, gólok, felvétel vége.
        bounds = [0.0] + ts + [total_s]
        longest, s0, s1 = 0.0, 0.0, total_s
        for a, b in zip(bounds, bounds[1:]):
            if b - a > longest:
                longest, s0, s1 = b - a, a, b
        out[side] = {"longest_s": round(longest, 1),
                     "start_s": round(s0, 1), "end_s": round(s1, 1)}
    return out


# Felzárkózás-húzó: gól-részvétel hátrányban, a többi álláshoz mérve.
CBC_MIN_TR = 3   # ennyi hátrányban szerzett gól-részvétel kell
CBC_RATIO = 2    # ennyiszerese legyen a nem-hátrány részvételnek


def comeback_carriers(match: Match, config=None) -> dict:
    """Felzárkózás-húzó: KIN keresztül jönnek vissza hátrányból.

    A hajrá-emberek (clutch_scorers) az óra szerint nézik a végjátékot
    — ez az eredményjelző szerint: játékosonként számoljuk a
    gól-részvételt (gól vagy gólpassz) aszerint, hogy a csapat épp
    hátrányban volt-e. Akinél a hátrány-termelés kiugró, az a
    felzárkózás motorja: a csapat bajban rajta keresztül játszik.

    Edzőileg: ha vezettek az ilyen csapat ellen, a húzóemberük
    kivétele a játékból (szoros fogás, korai kettőzés) a hátrányukat
    beragasztja — a többiek nincsenek hozzászokva a mentéshez; a
    saját oldalon pedig tudatosítani kell, ki a valódi mentőember,
    és a hátrány-figurákat rá építeni.

    Visszatérés csapatonként: {"players": [{"player_id", "trailing",
    "rest"}] (trailing szerint csökkenő), "top", "verdict"} — a
    verdict "a(z) N. hozza őket vissza (T gól-részvétel hátrányban,
    máskor R)" (CBC_MIN_TR/CBC_RATIO szerint), különben None.
    """
    from .event_detection import EventType, detect_events
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    events = detect_events(match, config)
    goals = [(e.t, getattr(e.team, "value", e.team)) for e in events
             if e.type == EventType.GOAL]
    out = {side: {"players": [], "top": None, "verdict": None}
           for side in ("home", "away")}
    tally: dict = {"home": {}, "away": {}}
    for e in events:
        if e.type != EventType.GOAL:
            continue
        side = getattr(e.team, "value", e.team)
        own = sum(1 for (t, tm) in goals if t < e.t and tm == side)
        opp = sum(1 for (t, tm) in goals if t < e.t and tm != side)
        key = "trailing" if own < opp else "rest"
        for pid in (e.player_id, (e.detail or {}).get("assist_id")):
            if pid is None:
                continue
            rec = tally[side].setdefault(pid, {"trailing": 0, "rest": 0})
            rec[key] += 1
    for side in ("home", "away"):
        players = [{"player_id": pid, **rec}
                   for pid, rec in tally[side].items()]
        players.sort(key=lambda r: (-r["trailing"], r["rest"]))
        out[side]["players"] = players
        for r in players:
            if r["trailing"] >= CBC_MIN_TR \
                    and r["trailing"] >= CBC_RATIO * max(1, r["rest"]):
                out[side]["top"] = r["player_id"]
                out[side]["verdict"] = (
                    f"a(z) {r['player_id']}. hozza őket vissza "
                    f"({r['trailing']} gól-részvétel hátrányban, "
                    f"máskor {r['rest']})")
                break
    return out


# Eltűnő ember: első félidei gól-részvétel után a másodikban csend.
FDR_MIN_FH = 3   # ennyi első félidei gól-részvétel (gól+gólpassz) kell
FDR_MAX_SH = 1   # a második félidőben legfeljebb ennyi = eltűnt


def fading_scorers(match: Match, config=None) -> dict:
    """Eltűnő ember: KI él az első félidőben, és tűnik el a másodikra.

    A hajrá-emberek (clutch_scorers) azt mondják meg, ki van ott a
    végén — ez a fordítottját: játékosonként számoljuk a
    gól-részvételt (gól vagy gólpassz) félidőnként, és megkeressük,
    akinél az első félidei termelés a másodikra elhal. A tipikus ok
    a kondíció vagy az, hogy az ellenfél a szünet után ráállt — de a
    felderítésnek mindegy is: az ilyen embert az ELSŐ félidőben kell
    megfogni, a második magától megoldódik.

    Edzőileg: az eltűnő kulcsember ellen az első 30 perc a meccs —
    duplán rá kell menni, cserével frissen tartott őrzővel; a saját
    eltűnő emberünknél a terhelés-menedzsment (korábbi pihentetés,
    rövidebb blokkok) a téma.

    Visszatérés csapatonként: {"players": [{"player_id", "fh",
    "sh"}] (fh szerint csökkenő), "top", "verdict"} — a verdict
    "a(z) N. az első félidőben él (F gól-részvétel), a másodikban
    eltűnik (S)" (FDR_MIN_FH/FDR_MAX_SH szerint), felismert szünet
    nélkül None.
    """
    from .event_detection import EventType, detect_events
    from .halftime import detect_halftime
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    out = {side: {"players": [], "top": None, "verdict": None}
           for side in ("home", "away")}
    ht = detect_halftime(match)
    if ht is None:
        return out
    tally: dict = {"home": {}, "away": {}}
    for e in detect_events(match, config):
        if e.type != EventType.GOAL:
            continue
        side = getattr(e.team, "value", e.team)
        half = "fh" if e.t <= ht else "sh"
        for pid in (e.player_id, (e.detail or {}).get("assist_id")):
            if pid is None:
                continue
            rec = tally[side].setdefault(pid, {"fh": 0, "sh": 0})
            rec[half] += 1
    for side in ("home", "away"):
        players = [{"player_id": pid, **rec}
                   for pid, rec in tally[side].items()]
        players.sort(key=lambda r: (-r["fh"], r["sh"]))
        out[side]["players"] = players
        for r in players:
            if r["fh"] >= FDR_MIN_FH and r["sh"] <= FDR_MAX_SH:
                out[side]["top"] = r["player_id"]
                out[side]["verdict"] = (
                    f"a(z) {r['player_id']}. az első félidőben él "
                    f"({r['fh']} gól-részvétel), a másodikban "
                    f"eltűnik ({r['sh']})")
                break
    return out


# Fekete ötperc: ekkora bukott gólkülönbség egy öt perces ablakban.
BLW_BUCKET_S = 300.0
BLW_MIN_DEFICIT = 3


def black_window(match: Match, config=None) -> dict:
    """Fekete ötperc: a meccs MELYIK ÖT PERCE süllyed el.

    A gól-idővonal (scoring_timeline) megmutatja, mikor esnek a
    gólok — ez ítéletet mond: öt perces ablakonként számoljuk a
    dobott és kapott gólokat, és megkeressük a legrosszabb ablakot.
    A felderítésben az ablakonkénti darabszámok meccsek közt
    összegződnek, így a VISSZATÉRŐ fekete ötperc is kirajzolódik —
    az a szakasz, ahol egy csapat rendre elveszíti a meccset (tipikus
    ok: az első sor pihenője, a bemelegedés hiánya, a 2. félidő eleji
    alvás).

    Edzőileg: az ellenfél fekete ötpercére kell időzíteni a nyomást —
    kontraedzett sor, letámadás, gyors középkezdések; a saját fekete
    ötpercre pedig tervezett csere-blokk és időkérés-készenlét kell,
    mielőtt a lyuk kinyílik.

    Visszatérés csapatonként: {"buckets": {"NN–MM": {"scored",
    "conceded"}}, "worst", "worst_diff", "verdict"} — a verdict
    "a NN–MM. perc a fekete ötpercük (dobott-kapott)"
    (BLW_MIN_DEFICIT-nyi bukásnál), különben None.
    """
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = BLW_BUCKET_S * fps
    out = {side: {"buckets": {}, "worst": None, "worst_diff": None,
                  "verdict": None} for side in ("home", "away")}
    for e in detect_shots(match, config):
        if e.type != EventType.GOAL:
            continue
        i = int(e.t // win)
        label = f"{i * 5}–{(i + 1) * 5}"
        scorer = getattr(e.team, "value", e.team)
        conceder = "away" if scorer == "home" else "home"
        for side, key in ((scorer, "scored"), (conceder, "conceded")):
            b = out[side]["buckets"].setdefault(
                label, {"scored": 0, "conceded": 0})
            b[key] += 1
    for rec in out.values():
        worst = None
        worst_diff = None
        for label, b in rec["buckets"].items():
            diff = b["scored"] - b["conceded"]
            if worst_diff is None or diff < worst_diff:
                worst, worst_diff = label, diff
        rec["worst"] = worst
        rec["worst_diff"] = worst_diff
        if worst is not None and worst_diff <= -BLW_MIN_DEFICIT:
            b = rec["buckets"][worst]
            rec["verdict"] = (f"a {worst}. perc a fekete ötpercük "
                              f"({b['scored']}-{b['conceded']})")
    return out


def scoring_timeline(match: Match, bucket_s: float = 300.0, config=None) -> dict:
    """Gólok idő-eloszlása idő-vödrökben (alapból 5 perc).

    Mikor esnek a gólok? A vödrönkénti dobott/kapott gól csapatonként
    megmutatja, mikor erős/gyenge egy csapat — a hajrában elfogy-e, vagy
    épp a végén erős. Visszatérés:
    {"bucket_s", "buckets": [{"start_s","end_s","home","away"}]}."""
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    dur_s = (match.frames[-1].t / fps) if match.frames else 0.0
    if dur_s <= 0:
        return {"bucket_s": bucket_s, "buckets": []}

    # Rövid felvételnél a vödör zsugorodik, hogy legyen legalább 2 vödör.
    n = max(2, int(math.ceil(dur_s / bucket_s)))
    step = dur_s / n
    buckets = [{"start_s": round(i * step, 1),
                "end_s": round((i + 1) * step, 1),
                "home": 0, "away": 0} for i in range(n)]
    for e in detect_shots(match, config):
        if e.type != EventType.GOAL:
            continue
        idx = min(n - 1, int((e.t / fps) / step))
        buckets[idx]["home" if e.team == Team.HOME else "away"] += 1
    return {"bucket_s": round(step, 1), "buckets": buckets}


def key_moments(match: Match, config=None) -> list[dict]:
    """A meccs gerince: kulcs-pillanatok egyetlen, időrendi listában.

    Fordulópont, 3+ gólos sorozatok kezdete (okkal), kiállítások,
    hétméteresek (kimenetellel) és kapuscserék — rétegenként hibatűrő,
    így ami számolható, az mindig megjön. A csomag-export
    kulcs_pillanatok.txt fájlja és az app Kulcs-pillanatok kártyája is
    ebből az egy rétegből épül.

    Visszatérés: [{"t", "t_s", "label"}] időrendben.
    """
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    names = {"home": match.meta.home_team, "away": match.meta.away_team}
    moments: list[dict] = []

    def add(t_frame: float, label: str):
        moments.append({"t": int(t_frame),
                        "t_s": round(t_frame / fps, 1),
                        "label": label})

    try:
        tp = win_probability(match).get("turning_point")
        if tp is not None:
            add(tp["t_s"] * fps, "Fordulópont — itt billent a meccs")
    except Exception:
        pass
    try:
        for r in annotate_runs(match):
            if r.get("length", 0) >= 3:
                ctx = (f" ({r['context'][0]})" if r.get("context")
                       else "")
                add(r["start_frame"],
                    f"{r['length']} gólos "
                    f"{names.get(r['team'], r['team'])} sorozat "
                    f"kezdete{ctx}")
    except Exception:
        pass
    try:
        # Vezetés-váltások: a gól, amelyikkel a csapat átveszi a
        # vezetést (nem az egyenlítés — az még nem fordulat).
        from .event_detection import EventType, detect_shots
        sc = {"home": 0, "away": 0}
        leader = None
        for e in detect_shots(match):
            if e.type != EventType.GOAL:
                continue
            sc[e.team.value] += 1
            new_leader = ("home" if sc["home"] > sc["away"]
                          else "away" if sc["away"] > sc["home"]
                          else leader)
            if new_leader != leader and new_leader is not None                     and leader is not None:
                add(e.t,
                    f"Vezetés-váltás — a(z) {names[new_leader]} "
                    f"átveszi a vezetést ({sc['home']}–{sc['away']})")
            leader = new_leader
    except Exception:
        pass
    try:
        # Gólcsend vége: ha egy 5+ perces saját gól nélküli időszak
        # góllal zárult, a megtörés pillanata kulcs-pillanat.
        dr = goal_droughts(match)
        total_s = (len(match.frames) / fps) if match.frames else 0.0
        for side in ("home", "away"):
            rec = dr.get(side) or {}
            if rec.get("longest_s", 0.0) >= 300.0 \
                    and rec.get("end_s", total_s) < total_s - 0.5:
                add(rec["end_s"] * fps,
                    f"Gólcsend vége — a(z) {names[side]} "
                    f"{rec['longest_s'] / 60:.0f} perc után újra "
                    "betalált")
    except Exception:
        pass
    try:
        from .rules import detect_powerplay, seven_meter_outcomes
        for w in detect_powerplay(match):
            add(w["start_frame"],
                f"Kiállítás — a(z) {names[w['team_down']]} "
                "emberhátrányban")
        for sm in seven_meter_outcomes(match):
            lab = f"Hétméteres — {names.get(sm['team'], '')}"
            if sm.get("outcome") and sm["outcome"] != "ismeretlen":
                lab += f" ({sm['outcome']})"
            add(sm["t"], lab)
    except Exception:
        pass
    try:
        from .goalkeeper import goalkeeper_timeline
        tl = goalkeeper_timeline(match)
        for side in ("home", "away"):
            for ch in (tl.get(side) or {}).get("changes", []):
                add(ch * fps, f"Kapuscsere — {names[side]}")
    except Exception:
        pass
    moments.sort(key=lambda m: m["t"])
    return moments


# Gólcsend-anatómia: legalább ennyi másodperces gólcsendet boncolunk;
# percenként ennyi lövés felett "kihagyós" a csend (a helyzet megvan,
# a befejezés hiányzik), ez alatt "néma" (a helyzetig sem jutnak el).
DROUGHT_ANATOMY_MIN_S = 300.0
DROUGHT_SHOOTING_PER_MIN = 0.8
DROUGHT_SILENT_PER_MIN = 0.3


def drought_anatomy(match: Match, config=None) -> dict:
    """Gólcsend-anatómia: a leghosszabb gólcsend alatt lőtt-e a csapat.

    A gólcsend (goal_droughts) csak azt mondja, MEDDIG nem esett gól —
    itt az derül ki, MIÉRT: a "kihagyós" csendben a csapat továbbra is
    lő, csak nem megy be — a befejezés (és a túloldali forró kezű
    kapus) a téma, edzésben a helyzetkihasználás; a "néma" csendben
    lövésig sem jut el — a támadás-szervezés állt le, és ilyenkor az
    ellenfél pressze működött: ellene az olvasat, hogy ha egyszer
    megfogtátok őket, a presszt tartani kell, mert maguktól nem
    találnak vissza.

    Visszatérés csapatonként: {"drought_s", "shots", "per_min",
    "verdict"} — per_min/verdict None, ha a leghosszabb csend rövid
    (DROUGHT_ANATOMY_MIN_S alatti); a verdict "kihagyós" / "néma" /
    None (köztes ütem).
    """
    from .event_detection import detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    dr = goal_droughts(match, config)
    shots_by = {"home": [], "away": []}
    for e in detect_shots(match, config):
        shots_by[e.team.value].append(e.t / fps)
    out = {}
    for side in ("home", "away"):
        rec = dr[side]
        n = sum(1 for ts in shots_by[side]
                if rec["start_s"] <= ts <= rec["end_s"])
        r = {"drought_s": rec["longest_s"], "shots": n,
             "per_min": None, "verdict": None}
        if rec["longest_s"] >= DROUGHT_ANATOMY_MIN_S:
            pm = n / (rec["longest_s"] / 60.0)
            r["per_min"] = round(pm, 2)
            if pm >= DROUGHT_SHOOTING_PER_MIN:
                r["verdict"] = "kihagyós"
            elif pm <= DROUGHT_SILENT_PER_MIN:
                r["verdict"] = "néma"
        out[side] = r
    return out


# Középkezdés-tempó: kapott gól után ennyi másodpercen belüli
# térfél-átlépés számít gyors újraindításnak (lerohanás); eddig
# követjük az újraindítást; ennyi kapott góltól ítélünk, és e
# részarányok döntik el a címkét.
RESTART_FAST_S = 12.0
RESTART_MAX_S = 45.0
RESTART_MIN_GOALS = 4
RESTART_FAST_SHARE = 50.0
RESTART_SLOW_SHARE = 20.0


def restart_speed(match: Match, config=None) -> dict:
    """Középkezdés-tempó: kapott gól után mennyi idő alatt ér át a
    labda az ellenfél térfelére.

    Az outlet_speed a VÉDÉS utáni indítást méri — ez a KAPOTT GÓL
    utánit: a lerohanós csapat a gólt kapva is azonnal középre viszi
    és átjátssza a labdát, mielőtt a gólt szerző fal visszaérne.
    Ellene a gól utáni ünneplés tilos — azonnali visszarendeződés,
    kijelölt fékező ember középen; a lassan újraindító csapat ellen
    viszont a középkezdés letámadható. Saját olvasatban a gyors
    középkezdés begyakorolható fegyver.

    Visszatérés csapatonként (a gólt KAPÓ oldal könyvelésében):
    {"restarts", "fast", "sum_s", "avg_s", "fast_pct", "style"} —
    avg_s/fast_pct/style None, ha kevés (RESTART_MIN_GOALS alatti) a
    mérhető újraindítás; a style "lerohanós" / "lassú" / None.
    """
    from .calibration import COURT_LENGTH_M
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    goals = sorted((e.t, e.team.value) for e in
                   detect_shots(match, config)
                   if e.type == EventType.GOAL)
    counts = {"home": {"restarts": 0, "fast": 0, "sum_s": 0.0},
              "away": {"restarts": 0, "fast": 0, "sum_s": 0.0}}
    mid = COURT_LENGTH_M / 2.0
    for gi, (t0, scorer) in enumerate(goals):
        side = "away" if scorer == "home" else "home"
        team = Team.AWAY if side == "away" else Team.HOME
        attacks_positive = config.attacks_toward_x(team) > mid
        # A következő gólig, de legfeljebb RESTART_MAX_S-ig követünk.
        t_max = t0 + round(RESTART_MAX_S * fps)
        if gi + 1 < len(goals):
            t_max = min(t_max, goals[gi + 1][0])
        crossed = None
        for f in match.frames:
            if f.t <= t0 + round(1.0 * fps) or f.ball is None:
                continue
            if f.t > t_max:
                break
            in_att = (f.ball.x > mid) if attacks_positive \
                else (f.ball.x < mid)
            if in_att:
                crossed = f.t
                break
        if crossed is None:
            continue
        dt = (crossed - t0) / fps
        rec = counts[side]
        rec["restarts"] += 1
        rec["sum_s"] += dt
        if dt <= RESTART_FAST_S:
            rec["fast"] += 1
    out = {}
    for side in ("home", "away"):
        rec = counts[side]
        r = {"restarts": rec["restarts"], "fast": rec["fast"],
             "sum_s": round(rec["sum_s"], 1), "avg_s": None,
             "fast_pct": None, "style": None}
        if rec["restarts"] >= RESTART_MIN_GOALS:
            r["avg_s"] = round(rec["sum_s"] / rec["restarts"], 1)
            pct = 100.0 * rec["fast"] / rec["restarts"]
            r["fast_pct"] = round(pct, 1)
            if pct >= RESTART_FAST_SHARE:
                r["style"] = "lerohanós"
            elif pct <= RESTART_SLOW_SHARE:
                r["style"] = "lassú"
        out[side] = r
    return out


# Hajrá-lövésválasztás: fázisonként ennyi lövés kell az ítélethez, és
# ekkora átlagos xG-esés (helyzetérték/lövés) számít érdeminek.
CLUTCH_SQ_MIN_SHOTS = 5
CLUTCH_SQ_DROP = 0.05


def clutch_shot_quality(match: Match, config=None) -> dict:
    """Hajrá-lövésválasztás: milyen helyzetekből lőnek a meccs végén.

    A hajrá-teljesítmény (clutch_performance) a hajrá GÓLJAIT nézi —
    ez azt, hogy milyen HELYZETEKBŐL lőnek ott: a hajrá (utolsó
    CLUTCH_WINDOW_S mp) és az azt megelőző idő átlagos xG/lövés
    értékét hasonlítja össze. Aki a hajrában érdemben rosszabb
    helyzetekből lő, az nyomás alatt elkapkodja a befejezést: ellene
    a hajrában elég tartani a falat, ők maguktól elrontják — saját
    olvasatban a hajrá-figurák és a türelem a téma. Aki javul, az a
    végén tudatosan a kidolgozott helyzetig játszik: ellene a hajrában
    is kell a kidolgozott helyzetek elleni fegyelem.

    Rövid felvételen (CLUTCH_MIN_DURATION_S alatt) nem értelmezzük:
    {"available": False}. Egyébként csapatonként {"early_shots",
    "early_xg", "clutch_shots", "clutch_xg", "early_avg",
    "clutch_avg", "delta", "verdict"} — avg/delta/verdict None, ha
    valamelyik fázisban kevés (CLUTCH_SQ_MIN_SHOTS alatti) a lövés; a
    verdict "elkapkodja" / "kidolgozza" / None.
    """
    from .tactics import TacticsConfig
    from .xg import match_xg

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    if not match.frames:
        return {"available": False}
    duration_s = (match.frames[-1].t - match.frames[0].t) / fps
    if duration_s < CLUTCH_MIN_DURATION_S:
        return {"available": False}
    t_clutch = match.frames[-1].t - round(CLUTCH_WINDOW_S * fps)

    counts = {s: {"early_shots": 0, "early_xg": 0.0,
                  "clutch_shots": 0, "clutch_xg": 0.0}
              for s in ("home", "away")}
    for sh in match_xg(match, config).get("shots", []):
        rec = counts[sh["team"]]
        phase = "clutch" if sh["t"] >= t_clutch else "early"
        rec[phase + "_shots"] += 1
        rec[phase + "_xg"] += float(sh["xg"])
    out = {"available": True, "window_s": CLUTCH_WINDOW_S}
    for side in ("home", "away"):
        rec = counts[side]
        r = {"early_shots": rec["early_shots"],
             "early_xg": round(rec["early_xg"], 2),
             "clutch_shots": rec["clutch_shots"],
             "clutch_xg": round(rec["clutch_xg"], 2),
             "early_avg": None, "clutch_avg": None,
             "delta": None, "verdict": None}
        if rec["early_shots"] >= CLUTCH_SQ_MIN_SHOTS \
                and rec["clutch_shots"] >= CLUTCH_SQ_MIN_SHOTS:
            early = rec["early_xg"] / rec["early_shots"]
            clutch = rec["clutch_xg"] / rec["clutch_shots"]
            r["early_avg"] = round(early, 3)
            r["clutch_avg"] = round(clutch, 3)
            r["delta"] = round(clutch - early, 3)
            if early - clutch >= CLUTCH_SQ_DROP:
                r["verdict"] = "elkapkodja"
            elif clutch - early >= CLUTCH_SQ_DROP:
                r["verdict"] = "kidolgozza"
        out[side] = r
    return out


# Hajrá-eladás: ennyi eladás/perc emelkedéstől beszélünk hajrá-hibáról,
# és ennyi eladás kell a hajrá előtti szakaszon az ítélethez.
CLUTCH_TO_RISE_PER_MIN = 0.3
CLUTCH_TO_MIN_EARLY = 5


def clutch_turnovers(match: Match, config=None) -> dict:
    """Hajrá-eladás: nyomás alatt megőrzik-e a labdát.

    A hajrá-lövésválasztás (clutch_shot_quality) azt méri, milyen
    HELYZETEKBŐL lőnek a végén — ez azt, hogy egyáltalán ELJUTNAK-e a
    lövésig: a hajrá (utolsó CLUTCH_WINDOW_S mp) és az azt megelőző
    idő eladás/perc ütemét hasonlítja össze. Akinél a hajrában megugrik
    az eladás, az a döntéseiben esik szét: ellene a végén présbe kell
    tenni a labdavivőt, és minden szerzés után futni. Aki hidegvérű,
    annál a hajrá-hiba nem jön magától — gólt kell lőni ellene.

    Rövid felvételen (CLUTCH_MIN_DURATION_S alatt) nem értelmezzük:
    {"available": False}. Egyébként csapatonként {"early_to",
    "early_s", "clutch_to", "clutch_s", "early_per_min",
    "clutch_per_min", "delta_per_min", "verdict"} — az ütemek és a
    verdict None, ha kevés (CLUTCH_TO_MIN_EARLY alatti) a hajrá előtti
    eladás; a verdict "hajrá-hibázó" / "hidegvérű" / None.
    """
    from .event_detection import EventType, detect_events
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    if not match.frames:
        return {"available": False}
    duration_s = (match.frames[-1].t - match.frames[0].t) / fps
    if duration_s < CLUTCH_MIN_DURATION_S:
        return {"available": False}
    t_clutch = match.frames[-1].t - round(CLUTCH_WINDOW_S * fps)
    clutch_s = (match.frames[-1].t - t_clutch) / fps
    early_s = max(0.0, duration_s - clutch_s)

    counts = {s: {"early_to": 0, "clutch_to": 0}
              for s in ("home", "away")}
    for e in detect_events(match, config):
        if e.type != EventType.TURNOVER:
            continue
        phase = "clutch" if e.t >= t_clutch else "early"
        counts[e.team.value][phase + "_to"] += 1
    out = {"available": True, "window_s": CLUTCH_WINDOW_S}
    for side in ("home", "away"):
        rec = counts[side]
        r = {**rec, "early_s": round(early_s, 1),
             "clutch_s": round(clutch_s, 1),
             "early_per_min": None, "clutch_per_min": None,
             "delta_per_min": None, "verdict": None}
        if rec["early_to"] >= CLUTCH_TO_MIN_EARLY and early_s > 0 \
                and clutch_s > 0:
            early = 60.0 * rec["early_to"] / early_s
            clutch = 60.0 * rec["clutch_to"] / clutch_s
            r["early_per_min"] = round(early, 2)
            r["clutch_per_min"] = round(clutch, 2)
            r["delta_per_min"] = round(clutch - early, 2)
            if clutch - early >= CLUTCH_TO_RISE_PER_MIN:
                r["verdict"] = "hajrá-hibázó"
            elif early - clutch >= CLUTCH_TO_RISE_PER_MIN:
                r["verdict"] = "hidegvérű"
        out[side] = r
    return out


# Hajrá-ötös: a meccs utolsó ekkora szakaszát nézzük, és ennyi mért
# kocka kell ahhoz, hogy egy játékos a hajrá-emberek közé kerüljön.
CLUTCH_LINEUP_WINDOW_S = 600.0
CLUTCH_LINEUP_MIN_FRAMES = 100


def clutch_lineup(match: Match, config=None) -> dict:
    """Hajrá-ötös: KIK VANNAK A PÁLYÁN a döntő szakaszban.

    A hajrá-teljesítmény (clutch_performance) azt mondja meg, ki bírja
    a meccs végét, a hajrá-gólszerzők (clutch_scorers) azt, ki lő
    ilyenkor — ez azt, KIT KÜLDENEK PÁLYÁRA: az utolsó
    CLUTCH_LINEUP_WINDOW_S másodpercben játékosonként megszámoljuk a
    pályán töltött kockákat.

    Edzőileg: ha tudjuk, kik lesznek fent a végén, rájuk lehet
    tervezni a párosítást (kire menjen a kettőzés, kit hagyunk lőni);
    a saját csapatban pedig a hajrá-emberek együtt gyakorolják a záró
    figurákat és a hetest.

    Visszatérés csapatonként: {"window_s", "players": [{"player_id",
    "jersey", "frames", "share_pct"}], "core"} — a lista kockaszám
    szerint csökkenő, a "core" a hajrá-magot adó, legalább
    CLUTCH_LINEUP_MIN_FRAMES kockát töltő játékosok listája (üres, ha
    rövid a felvétel).
    """
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    frames = match.frames
    if not frames:
        return {side: {"window_s": CLUTCH_LINEUP_WINDOW_S,
                       "players": [], "core": []}
                for side in ("home", "away")}

    end_t = frames[-1].t
    total_s = (end_t - frames[0].t + 1) / fps
    win_start = end_t - CLUTCH_LINEUP_WINDOW_S * fps
    jersey: dict = {}
    acc: dict = {"home": {}, "away": {}}
    window_frames = 0
    for f in frames:
        if f.t < win_start:
            continue
        window_frames += 1
        for p in f.players:
            if p.role == "kapus":
                continue
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)
            side = p.team.value
            acc[side][p.track_id] = acc[side].get(p.track_id, 0) + 1

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "frames": n,
                 "share_pct": (round(100.0 * n / window_frames, 1)
                               if window_frames else None)}
                for pid, n in sorted(acc[side].items(),
                                     key=lambda kv: -kv[1])]
        core = ([r for r in rows
                 if r["frames"] >= CLUTCH_LINEUP_MIN_FRAMES]
                if total_s >= CLUTCH_MIN_DURATION_S else [])
        out[side] = {"window_s": CLUTCH_LINEUP_WINDOW_S,
                     "players": rows, "core": core}
    return out


# Hajrá-hibázók: ennyi hajrá-eladástól emeljük ki az embert (a hajrában
# kevés az esemény, ezért alacsony a küszöb, de egy eset még nem minta).
CTP_MIN_TURNOVERS = 2


def clutch_turnover_players(match: Match, config=None) -> dict:
    """Hajrá-hibázók: KI ADJA EL a labdát a döntő szakaszban.

    A hajrá-eladás (clutch_turnovers) csapat-szinten mondja meg,
    megugrik-e az eladás-ütem a végén — ez azt, KINÉL: az utolsó
    CLUTCH_WINDOW_S másodperc labdaeladásait a vesztes játékoshoz
    írjuk.

    Edzőileg: a hajrában présbe kell tenni azt, akinél a labda a végén
    elmegy — rá jöjjön a kettőzés és a passzsáv-zárás, mert nála a
    legolcsóbb a labdaszerzés, amikor a legtöbbet ér.

    Visszatérés csapatonként: {"window_s", "turnovers", "players":
    [{"player_id", "jersey", "turnovers"}], "top"} — a "top" az első
    játékos, ha legalább CTP_MIN_TURNOVERS hajrá-eladása van; rövid
    felvételen (CLUTCH_MIN_DURATION_S alatt) üres a kép.
    """
    from .event_detection import EventType, detect_events
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    frames = match.frames
    empty = {side: {"window_s": CLUTCH_WINDOW_S, "turnovers": 0,
                    "players": [], "top": None}
             for side in ("home", "away")}
    if not frames:
        return empty
    total_s = (frames[-1].t - frames[0].t + 1) / fps
    if total_s < CLUTCH_MIN_DURATION_S:
        return empty

    win_start = frames[-1].t - CLUTCH_WINDOW_S * fps
    jersey: dict = {}
    for f in frames:
        for p in f.players:
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)

    tally: dict = {"home": {}, "away": {}}
    for e in detect_events(match, config or TacticsConfig()):
        if e.type != EventType.TURNOVER or e.player_id is None:
            continue
        if e.t < win_start:
            continue
        side = e.team.value
        tally[side][e.player_id] = tally[side].get(e.player_id, 0) + 1

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "turnovers": n}
                for pid, n in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1])]
        top = (rows[0]
               if rows and rows[0]["turnovers"] >= CTP_MIN_TURNOVERS
               else None)
        out[side] = {"window_s": CLUTCH_WINDOW_S,
                     "turnovers": sum(r["turnovers"] for r in rows),
                     "players": rows, "top": top}
    return out


# Kezdő hatos: a meccs eleji ablak, és ennyi mért kocka kell ahhoz,
# hogy egy játékos a kezdő emberek közé kerüljön.
OPENING_LINEUP_WINDOW_S = 300.0
OPENING_LINEUP_MIN_FRAMES = 100


def opening_lineup(match: Match, config=None) -> dict:
    """Kezdő hatos: KIKKEL KEZDENEK.

    A nyitány-profil (opening_profile) azt mondja meg, hogyan indítják
    a meccset, a hajrá-ötös (clutch_lineup) azt, kikkel zárják — ez a
    másik vége: az első OPENING_LINEUP_WINDOW_S másodpercben
    játékosonként megszámoljuk a pályán töltött kockákat.

    Edzőileg: ha tudjuk, kikkel kezdenek, az első támadásokra név
    szerinti terv készíthető (kire megy a kettőzés, kit engedünk
    lőni), és látszik, kit tartogatnak a kispadon a hajrára.

    Visszatérés csapatonként: {"window_s", "players": [{"player_id",
    "jersey", "frames", "share_pct"}], "core"} — a lista kockaszám
    szerint csökkenő, a "core" a legalább OPENING_LINEUP_MIN_FRAMES
    kockát töltő játékosok listája.
    """
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    frames = match.frames
    if not frames:
        return {side: {"window_s": OPENING_LINEUP_WINDOW_S,
                       "players": [], "core": []}
                for side in ("home", "away")}

    cut = frames[0].t + OPENING_LINEUP_WINDOW_S * fps
    jersey: dict = {}
    acc: dict = {"home": {}, "away": {}}
    window_frames = 0
    for f in frames:
        if f.t > cut:
            break
        window_frames += 1
        for p in f.players:
            if p.role == "kapus":
                continue
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)
            side = p.team.value
            acc[side][p.track_id] = acc[side].get(p.track_id, 0) + 1

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "frames": n,
                 "share_pct": (round(100.0 * n / window_frames, 1)
                               if window_frames else None)}
                for pid, n in sorted(acc[side].items(),
                                     key=lambda kv: -kv[1])]
        core = [r for r in rows
                if r["frames"] >= OPENING_LINEUP_MIN_FRAMES]
        out[side] = {"window_s": OPENING_LINEUP_WINDOW_S,
                     "players": rows, "core": core}
    return out


# Félidő-nyitás: ekkora ablakot nézünk a két félidő elején, ennyi gól
# kell az ítélethez, és ekkora gólkülönbség jelenti a jó, illetve a
# lassú nyitást.
HO_WINDOW_S = 300.0
HO_MIN_GOALS = 4
HO_DIFF = 2


def half_openings(match: Match, config=None) -> dict:
    """Félidő-nyitás: HOGYAN INDULNAK a két félidő első 5 percében.

    A félidő-mérleg (a fh/sh gólok) a teljes félidőt méri, a
    hajrá-mérleg az utolsó perceket — ez a KEZDÉST: a meccs és a
    második félidő első HO_WINDOW_S másodpercében szerzett és kapott
    gólokat összegezzük.

    Edzőileg: aki jól nyitja a félidőket, az bemelegítés-ből és
    öltözői beszédből él — ellene az első öt percben a legfontosabb a
    biztos, hibátlan játék, mert egy korai szériával elszalad; aki
    lassan indul, annál pont az első öt percben kell rámenni, mert
    ott szerezhető meg a meccs vezetése.

    Visszatérés csapatonként: {"goals_for", "goals_against", "diff",
    "verdict"} — a verdict None HO_MIN_GOALS alatt (a két oldal
    összege); a verdict "jól nyitják a félidőket" / "lassan indulnak"
    / None.
    """
    from .event_detection import EventType, detect_shots
    from .halftime import detect_halftime

    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = HO_WINDOW_S * fps
    out = {side: {"goals_for": 0, "goals_against": 0, "diff": 0,
                  "verdict": None} for side in ("home", "away")}
    if not match.frames:
        return out

    starts = [match.frames[0].t]
    ht = detect_halftime(match)
    if ht is not None:
        starts.append(ht)

    for e in detect_shots(match, config):
        if e.type != EventType.GOAL:
            continue
        if not any(st <= e.t <= st + win for st in starts):
            continue
        scorer = e.team.value
        other = "away" if scorer == "home" else "home"
        out[scorer]["goals_for"] += 1
        out[other]["goals_against"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["diff"] = rec["goals_for"] - rec["goals_against"]
        if rec["goals_for"] + rec["goals_against"] >= HO_MIN_GOALS:
            if rec["diff"] >= HO_DIFF:
                rec["verdict"] = "jól nyitják a félidőket"
            elif rec["diff"] <= -HO_DIFF:
                rec["verdict"] = "lassan indulnak"
    return out


# Félidő-zárás: ekkora ablakot nézünk a két félidő vége előtt, ennyi
# mért támadás kell az ítélethez, és e feletti / alatti gólarány a jó,
# illetve az elpuskázott záró labda jele.
CLO_WINDOW_S = 60.0
CLO_MIN_ATTACKS = 3
CLO_GOOD_PCT = 50.0
CLO_WASTE_PCT = 15.0


def closing_attacks(match: Match, config=None) -> dict:
    """Félidő-zárás: MIT KEZDENEK AZ UTOLSÓ LABDÁVAL.

    A hajrá-mérleg (clutch_performance) az utolsó perceket méri, a
    félidő-nyitás (half_openings) a kezdést — ez a két félidő utolsó
    CLO_WINDOW_S másodpercét: hány támadásuk indul ott, és hányból
    lesz gól. Ez a dudaszó előtti utolsó labda kezelése: időhúzás,
    figura, biztos befejezés.

    Edzőileg: aki a záró labdát rendre gólig viszi, annál a félidő
    végén nem szabad idő előtt lőni — az óra a mi barátunk, és a
    labdát ki kell húzni; aki elpuskázza, annál pont fordítva: érdemes
    gyorsan visszaadni a labdát, mert a záró támadásuk ajándék.

    Visszatérés csapatonként: {"attacks", "goals", "share_pct",
    "verdict"} — a share_pct/verdict None CLO_MIN_ATTACKS alatt; a
    verdict "jól kezelik a záró labdát" / "elpuskázzák a záró labdát"
    / None.
    """
    from .attack_types import ATTACK_TAIL_S, classify_attacks
    from .event_detection import EventType, detect_shots
    from .halftime import detect_halftime

    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = CLO_WINDOW_S * fps
    out = {side: {"attacks": 0, "goals": 0, "share_pct": None,
                  "verdict": None} for side in ("home", "away")}
    if not match.frames:
        return out

    # Záró ablakok: a második félidő vége, és — ha van szünet — az
    # első félidő vége.
    ends = [match.frames[-1].t]
    ht = detect_halftime(match)
    if ht is not None:
        ends.append(ht)

    tail = round(ATTACK_TAIL_S * fps)
    goals = [(e.t, e.team.value) for e in detect_shots(match, config)
             if e.type == EventType.GOAL]

    for a in classify_attacks(match, config):
        if not any(end - win <= a["start_frame"] <= end for end in ends):
            continue
        side = a["team"]
        rec = out[side]
        rec["attacks"] += 1
        if any(tm == side
               and a["start_frame"] <= t <= a["end_frame"] + tail
               for (t, tm) in goals):
            rec["goals"] += 1

    for side in ("home", "away"):
        rec = out[side]
        if rec["attacks"] >= CLO_MIN_ATTACKS:
            share = 100.0 * rec["goals"] / rec["attacks"]
            rec["share_pct"] = round(share, 1)
            if share >= CLO_GOOD_PCT:
                rec["verdict"] = "jól kezelik a záró labdát"
            elif share <= CLO_WASTE_PCT:
                rec["verdict"] = "elpuskázzák a záró labdát"
    return out


# Pad-gólok: ennyi lövőhöz köthető gól kell az ítélethez, és e
# feletti / alatti pad-arány a mélyen termelő, illetve a csak a
# kezdőkre épülő támadójáték jele.
BEN_MIN_GOALS = 6
BEN_DEEP_PCT = 35.0
BEN_THIN_PCT = 10.0


def bench_scoring(match: Match, config=None) -> dict:
    """Pad-gólok: A KISPAD IS TERMEL-E, vagy csak a kezdők.

    A kezdő hatos (opening_lineup) azt mondja meg, kikkel kezdenek, a
    rotáció azt, hányan játszanak — ez azt, KI SZERZI A GÓLOKAT: a
    lövőhöz köthető gólokat kettéosztjuk a kezdő mag (a meccs első
    perceiben pályán lévők) és a padról beállók között.

    Edzőileg: akinél csak a kezdők termelnek, azt fárasztani kell —
    pörgetett tempó és letámadás mellett a hat emberük elfogy a
    második félidőre; akinél a pad is termel, ott a tempó önmagában
    nem törik meg, minden sorukra névre szóló párosítás-terv kell.

    Visszatérés csapatonként: {"goals", "bench_goals", "bench_pct",
    "verdict"} — a bench_pct/verdict None BEN_MIN_GOALS alatt; a
    verdict "a kispad is termel" / "csak a kezdők termelnek" / None.
    """
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    core = {side: {r["player_id"]
                   for r in opening_lineup(match, config)[side]["core"]}
            for side in ("home", "away")}

    out = {side: {"goals": 0, "bench_goals": 0, "bench_pct": None,
                  "verdict": None} for side in ("home", "away")}
    for e in detect_shots(match, config):
        if e.type != EventType.GOAL or e.player_id is None:
            continue
        rec = out[e.team.value]
        rec["goals"] += 1
        if e.player_id not in core[e.team.value]:
            rec["bench_goals"] += 1

    for side in ("home", "away"):
        rec = out[side]
        if rec["goals"] >= BEN_MIN_GOALS:
            pct = 100.0 * rec["bench_goals"] / rec["goals"]
            rec["bench_pct"] = round(pct, 1)
            if pct >= BEN_DEEP_PCT:
                rec["verdict"] = "a kispad is termel"
            elif pct <= BEN_THIN_PCT:
                rec["verdict"] = "csak a kezdők termelnek"
    return out


# Középkezdés-átvevő: ekkora ablakban és a felezőtől ekkora sávban
# keressük a kapott gól utáni első birtokost, ennyi mért újraindítás
# kell az ítélethez, és e feletti arány jelenti a fix átvevőt.
RST_WINDOW_S = 15.0
RST_CENTER_M = 8.0
RST_MIN_RESTARTS = 4
RST_TOP_PCT = 50.0


def restart_targets(match: Match, config=None) -> dict:
    """Középkezdés-átvevő: KINÉL indul újra a játék a kapott gól után.

    A középkezdés-tempó (restart_speed) azt méri, MILYEN GYORSAN ér át
    a labda — ez azt, KINÉL: a kapott gól utáni RST_WINDOW_S
    másodpercben megkeressük a gólt kapó csapat első, felező-környéki
    labdabirtokosát (a kapus nélkül). A legtöbb csapatnál ez
    begyakorolt szerep — ha egy emberre jár a labda, a középkezdésük
    olvasható.

    Edzőileg: a fix átvevőjű csapat ellen a gól utáni letámadásnak
    névre szóló célpontja van — az átvevőt kell fogni, és a
    középkezdésük megáll; a saját csapatban pedig a kiszámítható
    átvevő variálandó, mert a felkészült ellenfél pont őt fogja le.

    Visszatérés csapatonként (a gólt KAPÓ oldal): {"restarts",
    "players": [{"player_id", "jersey", "takes"}], "top", "verdict"}
    — a top/verdict None RST_MIN_RESTARTS alatt vagy RST_TOP_PCT
    alatti részesedésnél; a verdict "fix középkezdés-emberük van" /
    None.
    """
    from .calibration import COURT_LENGTH_M
    from .decisions import ball_holder
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = round(RST_WINDOW_S * fps)
    mid = COURT_LENGTH_M / 2.0
    frames = match.frames
    idx_of = {f.t: i for i, f in enumerate(frames)}

    goals = [(e.t, e.team) for e in detect_shots(match, config)
             if e.type == EventType.GOAL]

    jersey: dict = {}
    tally: dict = {"home": {}, "away": {}}
    restarts = {"home": 0, "away": 0}
    for (gt, gteam) in goals:
        i0 = idx_of.get(gt)
        if i0 is None:
            continue
        conceder = "away" if gteam.value == "home" else "home"
        for j in range(i0 + 1, min(len(frames), i0 + 1 + win)):
            h = ball_holder(frames[j], config)
            if h is None or h.team.value != conceder:
                continue
            if h.role == "kapus":
                continue
            if abs(h.x - mid) > RST_CENTER_M:
                continue
            if h.jersey_number is not None:
                jersey.setdefault(h.track_id, h.jersey_number)
            restarts[conceder] += 1
            tally[conceder][h.track_id] = (
                tally[conceder].get(h.track_id, 0) + 1)
            break

    out: dict = {}
    for side in ("home", "away"):
        players = [{"player_id": tid, "jersey": jersey.get(tid),
                    "takes": n}
                   for tid, n in sorted(tally[side].items(),
                                        key=lambda kv: -kv[1])]
        top = None
        verdict = None
        if restarts[side] >= RST_MIN_RESTARTS and players:
            share = 100.0 * players[0]["takes"] / restarts[side]
            if share >= RST_TOP_PCT:
                top = players[0]
                verdict = "fix középkezdés-emberük van"
        out[side] = {"restarts": restarts[side], "players": players,
                     "top": top, "verdict": verdict}
    return out


# Negyedóra-profil: legalább ennyi perc felvétel kell az ítélethez, és
# ekkora negyedórán belüli gólkülönbség emeli ki az erős, illetve a
# gyenge szakaszt.
QP_MIN_DURATION_MIN = 40.0
QP_DIFF = 3


def quarter_profile(match: Match, config=None) -> dict:
    """Negyedóra-profil: MELYIK MECCS-SZAKASZ AZ ÖVÉK az óra szerint.

    A sorozat-elemzés (runs) esemény-alapú — ez óra-alapú: a gólokat
    15 perces negyedórákba soroljuk, és negyedóránként gólkülönbséget
    számolunk. Sok csapatnak van visszatérő erős szakasza (bemelegedő
    kezdés, halálos rajt, hajrá-gép) — az óra szerinti minta előre
    tervezhetővé teszi az időkérést és a rotációt.

    Edzőileg: az ő erős negyedórájuk ELŐTT kell a saját időkérés és a
    friss sor — ne az ő lendületükben kapkodjatok; a gyenge
    negyedórájukra pedig tempót kell időzíteni, mert ott esnek szét.

    Visszatérés csapatonként: {"for": {negyedóra: gól},
    "against": {...}, "best", "worst", "verdict"} — a negyedóra kulcs
    "1".."4"; a best/worst/verdict None QP_MIN_DURATION_MIN alatti
    felvételnél vagy QP_DIFF alatti különbségnél; a verdict
    "van erős negyedórájuk" / None.
    """
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    minutes = (0.0 if not match.frames else
               (match.frames[-1].t - match.frames[0].t) / fps / 60.0)
    t0 = match.frames[0].t if match.frames else 0

    out = {side: {"for": {}, "against": {}, "best": None,
                  "worst": None, "verdict": None}
           for side in ("home", "away")}
    for e in detect_shots(match, config):
        if e.type != EventType.GOAL:
            continue
        q = str(min(3, int((e.t - t0) / fps / 60.0 // 15)) + 1)
        scorer = e.team.value
        other = "away" if scorer == "home" else "home"
        out[scorer]["for"][q] = out[scorer]["for"].get(q, 0) + 1
        out[other]["against"][q] = out[other]["against"].get(q, 0) + 1

    if minutes < QP_MIN_DURATION_MIN:
        return out
    for side in ("home", "away"):
        rec = out[side]
        diffs = {q: rec["for"].get(q, 0) - rec["against"].get(q, 0)
                 for q in ("1", "2", "3", "4")}
        best_q = max(diffs, key=lambda q: diffs[q])
        worst_q = min(diffs, key=lambda q: diffs[q])
        if diffs[best_q] >= QP_DIFF:
            rec["best"] = {"quarter": best_q, "diff": diffs[best_q]}
            rec["verdict"] = "van erős negyedórájuk"
        if diffs[worst_q] <= -QP_DIFF:
            rec["worst"] = {"quarter": worst_q, "diff": diffs[worst_q]}
    return out


# Hajrá-labdabirtoklás: ennyi mért labdás kocka kell a hajrában, és e
# feletti részesedés jelenti az egy kézben lévő végjátékot.
CBH_MIN_FRAMES = 200
CBH_TOP_PCT = 35.0


def clutch_ball_hogs(match: Match, config=None) -> dict:
    """Hajrá-labdabirtoklás: EGY KÉZBEN VAN-E a végjátékuk.

    A hajrá-ötös (clutch_lineup) azt mondja meg, kik vannak fent a
    végén, a hajrá-emberek (clutch_scorers) azt, ki lő — ez azt,
    KINÉL VAN A LABDA: az utolsó CLUTCH_WINDOW_S másodperc labdás
    kockáit játékosonként számoljuk. Sok csapat végjátéka egyetlen
    irányítón fut keresztül — ha ő kézben tartja a labdát, a többiek
    csak befejeznek.

    Edzőileg: az egy kézben futó végjáték ellen a hajrá-kettőzés a
    recept — nem a lövőket kell fogni, hanem A kezet: ha tőle elvenni
    vagy őt korán labdához nem engedni sikerül, a záró figuráik el
    sem indulnak.

    Visszatérés csapatonként: {"frames", "players": [{"player_id",
    "jersey", "frames"}], "top", "verdict"} — a top/verdict None
    CBH_MIN_FRAMES mért kocka alatt vagy CBH_TOP_PCT alatti
    részesedésnél; a verdict "egy kézben van a végjátékuk" / None.
    """
    from .decisions import ball_holder
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    if not match.frames:
        return {side: {"frames": 0, "players": [], "top": None,
                       "verdict": None} for side in ("home", "away")}
    cut = match.frames[-1].t - CLUTCH_WINDOW_S * fps

    jersey: dict = {}
    acc: dict = {"home": {}, "away": {}}
    counted = {"home": 0, "away": 0}
    for f in match.frames:
        if f.t < cut:
            continue
        h = ball_holder(f, config)
        if h is None or h.role == "kapus":
            continue
        if h.jersey_number is not None:
            jersey.setdefault(h.track_id, h.jersey_number)
        side = h.team.value
        counted[side] += 1
        acc[side][h.track_id] = acc[side].get(h.track_id, 0) + 1

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": tid, "jersey": jersey.get(tid),
                 "frames": n}
                for tid, n in sorted(acc[side].items(),
                                     key=lambda kv: -kv[1])]
        top = None
        verdict = None
        if counted[side] >= CBH_MIN_FRAMES and rows:
            share = 100.0 * rows[0]["frames"] / counted[side]
            if share >= CBH_TOP_PCT:
                top = rows[0]
                verdict = "egy kézben van a végjátékuk"
        out[side] = {"frames": counted[side], "players": rows,
                     "top": top, "verdict": verdict}
    return out


# Forró kéz: legalább ennyi egymást követő saját gól ugyanattól a
# lövőtől számít sorozatnak, és ennyi sorozat (vagy egy ennél hosszabb)
# kell az ítélethez.
HOT_STREAK_LEN = 2
HOT_MIN_STREAKS = 2
HOT_LONG_STREAK = 3


def hot_hands(match: Match, config=None) -> dict:
    """Forró kéz: VAN-E SOROZATLÖVŐJÜK, aki egymás után dobja a gólokat.

    A gólfelelős-koncentráció (shot_concentration) a teljes meccs
    eloszlását nézi — ez a sorozatokat: a csapat góljait időrendben
    végigolvasva megszámoljuk, ki dob egymás után többet (a csapat
    két szomszédos gólja ugyanattól a lövőtől). A forró kéz valós
    edzői jel: aki lendületbe jön, az a következő támadásban is
    magához veszi a labdát.

    Edzőileg: a sorozatlövő ellen az ELSŐ gólja után kell reagálni —
    őrzés-váltás vagy kettőzés rá, mielőtt a második-harmadik jönne;
    a saját csapatban pedig a forró kezű embert tudatosan kell
    játékba hozni, amíg tart a lendülete.

    Visszatérés csapatonként: {"goals", "streaks": [{"player_id",
    "length"}], "top", "verdict"} — a top/verdict None, ha nincs elég
    sorozat; a verdict "van sorozatlövőjük" / None.
    """
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    goals: dict = {"home": [], "away": []}
    for e in detect_shots(match, config):
        if e.type == EventType.GOAL and e.player_id is not None:
            goals[e.team.value].append(e.player_id)

    out: dict = {}
    for side in ("home", "away"):
        seq = goals[side]
        streaks: list = []
        i = 0
        while i < len(seq):
            j = i
            while j + 1 < len(seq) and seq[j + 1] == seq[i]:
                j += 1
            if j - i + 1 >= HOT_STREAK_LEN:
                streaks.append({"player_id": seq[i],
                                "length": j - i + 1})
            i = j + 1
        per_player: dict = {}
        for st in streaks:
            rec = per_player.setdefault(
                st["player_id"], {"player_id": st["player_id"],
                                  "streaks": 0, "longest": 0})
            rec["streaks"] += 1
            rec["longest"] = max(rec["longest"], st["length"])
        top = None
        verdict = None
        cands = [r for r in per_player.values()
                 if r["streaks"] >= HOT_MIN_STREAKS
                 or r["longest"] >= HOT_LONG_STREAK]
        if cands:
            top = max(cands, key=lambda r: (r["streaks"], r["longest"]))
            verdict = "van sorozatlövőjük"
        out[side] = {"goals": len(seq), "streaks": streaks,
                     "top": top, "verdict": verdict}
    return out


# Csend-törők: legalább ekkora saját gólcsend megtörése számít, és
# ennyi törés kell a kiemelt válság-lövőhöz.
DRB_GAP_S = 300.0
DRB_MIN_BREAKS = 2


def drought_breakers(match: Match, config=None) -> dict:
    """Csend-törők: KI DOBJA a gólcsendet megtörő gólt.

    A gólcsend-elemzés a leghosszabb szárazságot méri — ez azt, ki
    vet véget neki: minden olyan gólnál, amely a csapat legalább
    DRB_GAP_S másodperces gólcsendje után esett, a lövő csend-törő
    jóváírást kap. Aki rendre ilyenkor vállal és betalál, az a
    csapat válság-lövője.

    Edzőileg: az ellenfél válság-lövőjét pont a saját sorozatunk
    alatt kell a legszorosabban fogni — hozzá menekül a labda, amikor
    áll a szekerük; a saját válság-lövőnket pedig tudatosan kell
    játékba hozni, amikor beáll a csend.

    Visszatérés csapatonként: {"droughts_broken", "players":
    [{"player_id", "breaks"}], "top", "verdict"} — a top/verdict
    None DRB_MIN_BREAKS alatti egyéni törésnél; a verdict "van
    válság-lövőjük" / None.
    """
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    gap = DRB_GAP_S * fps

    goals: dict = {"home": [], "away": []}
    for e in detect_shots(match, config):
        if e.type == EventType.GOAL:
            goals[e.team.value].append((e.t, e.player_id))

    out: dict = {}
    for side in ("home", "away"):
        tally: dict = {}
        broken = 0
        prev_t = None
        for (t, pid) in goals[side]:
            if prev_t is not None and t - prev_t >= gap:
                broken += 1
                if pid is not None:
                    tally[pid] = tally.get(pid, 0) + 1
            prev_t = t
        players = [{"player_id": pid, "breaks": n}
                   for pid, n in sorted(tally.items(),
                                        key=lambda kv: -kv[1])]
        top = None
        verdict = None
        if players and players[0]["breaks"] >= DRB_MIN_BREAKS:
            top = players[0]
            verdict = "van válság-lövőjük"
        out[side] = {"droughts_broken": broken, "players": players,
                     "top": top, "verdict": verdict}
    return out


# Kihagyás-büntetés: a kihagyott nagy helyzet utáni ennyi másodpercen
# belüli ellenfél-gól számít azonnali büntetésnek; ennyi kihagyott
# ziccer kell az ítélethez, és e feletti arány a törékeny, ez alatti
# a jól emésztő csapat jele.
PMB_WINDOW_S = 30.0
PMB_MIN_MISSES = 4
PMB_PUNISHED_PCT = 40.0
PMB_DIGEST_PCT = 10.0


def punished_misses(match: Match, config=None) -> dict:
    """Kihagyás-büntetés: MEGBÜNTETIK-E a kihagyott ziccereiket.

    A kihagyott nagy helyzetek (missed_big_chances) a mennyiséget
    mérik — ez a következményt: a kihagyott ziccerek után
    PMB_WINDOW_S másodpercen belül hányszor jött azonnali
    ellenfél-gól. A kihagyás után összeroskadó csapat a
    lélektanilag törékeny; aki jól emészti, annál a kihagyás nem
    fordul át hátrányba.

    Edzőileg: a törékeny csapat ellen a ziccer-kimaradásuk után
    azonnal tempót kell váltani — gyors középkezdés helyett kapura
    vitt első támadás, mert ilyenkor mentálisan lent vannak; a
    saját oldalon a kihagyás utáni 30 másodperc kiemelt fókusz-idő:
    először védekezni, aztán bánkódni.

    Visszatérés csapatonként (a KIHAGYÓ oldal): {"misses"
    (kihagyott nagy helyzetek), "punished", "punished_pct",
    "verdict"} — a punished_pct/verdict None PMB_MIN_MISSES alatt;
    a verdict "a kihagyásaik után azonnal büntetik őket" / "jól
    emésztik a kihagyást" / None.
    """
    from .tactics import TacticsConfig
    from .xg import BIG_CHANCE_XG, match_xg

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = round(PMB_WINDOW_S * fps)
    shots = match_xg(match, config).get("shots", [])
    goals = [(sh["t"], sh["team"]) for sh in shots
             if sh.get("outcome") == "goal"]

    out = {side: {"misses": 0, "punished": 0, "punished_pct": None,
                  "verdict": None} for side in ("home", "away")}
    for sh in shots:
        if sh.get("xg", 0.0) < BIG_CHANCE_XG \
                or sh.get("outcome") == "goal":
            continue
        side = sh["team"]
        rec = out[side]
        rec["misses"] += 1
        if any(tm != side and 0 < gt - sh["t"] <= win
               for (gt, tm) in goals):
            rec["punished"] += 1

    for side in ("home", "away"):
        rec = out[side]
        if rec["misses"] >= PMB_MIN_MISSES:
            pct = 100.0 * rec["punished"] / rec["misses"]
            rec["punished_pct"] = round(pct, 1)
            if pct >= PMB_PUNISHED_PCT:
                rec["verdict"] = "a kihagyásaik után azonnal büntetik őket"
            elif pct <= PMB_DIGEST_PCT:
                rec["verdict"] = "jól emésztik a kihagyást"
    return out


# Hajrá-poszt: ennyi poszthoz kötött hajrá-gól kell az ítélethez, és
# ekkora részarány fölött mondjuk ki, hogy a végjátékuk egy posztra
# fut ki.
CSR_MIN_GOALS = 3
CSR_SHARE_PCT = 60.0


def clutch_scorer_roles(match: Match, config=None) -> dict:
    """Hajrá-poszt: MELYIK POSZTJUK viszi a végjátékot.

    A hajrá-emberek rétege (clutch_scorers) az embert nevezi meg —
    ez a posztot: a meccs utolsó öt percének góljait a lövő
    posztjához írja. Így a minta akkor is látszik, ha a nevek
    meccsről meccsre cserélődnek.

    Edzőileg ez az utolsó öt perc terve: szoros állásnál nem kell
    találgatni, kire fut ki a támadásuk — ha a hajrá-góljaik rendre
    ugyanarról a posztról esnek, a záró percekben őt kell fogni
    (akár emberfogással), és az ő sávjára áll rá a kapus is. Saját
    csapatra: az egy emberre épülő hajrá kockázat — második megoldás
    kell a záró percekre.

    Visszatérés csapatonként: {"goals" (poszthoz kötött hajrá-gól),
    "roles": {poszt: gól}, "main_role", "share_pct", "verdict"} — az
    ítélet None, ha nincs meg a CSR_MIN_GOALS, vagy egyik poszt sem
    éri el a CSR_SHARE_PCT-t.
    """
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    cs = clutch_scorers(match, config)

    out: dict = {side: {"goals": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in cs[side]["players"]:
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["goals"])
            rec["goals"] += row["goals"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["goals"] >= CSR_MIN_GOALS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["goals"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= CSR_SHARE_PCT:
                rec["verdict"] = (
                    f"a végjátékuk a(z) {poszt} posztra fut ki "
                    f"({share:.0f}%, {rec['goals']} hajrá-gólból) — "
                    "az utolsó öt percben őt kell fogni, és az ő "
                    "sávjára áll rá a kapus is")
    return out


# Felzárkózás-poszt: ennyi poszthoz kötött hátrány-gól-részvétel kell
# az ítélethez, és ekkora részarány fölött mondjuk ki, hogy a
# mentőjátékuk egy posztra épül.
CBR_MIN_TRAILING = 3
CBR_SHARE_PCT = 60.0


def comeback_carrier_roles(match: Match, config=None) -> dict:
    """Felzárkózás-poszt: MELYIK POSZTJUK hozza őket vissza.

    A felzárkózás-húzó rétege (comeback_carriers) az embert nevezi
    meg — ez a posztot: a hátrányban szerzett gól-részvételeket a
    játékos posztjához írja. Így a minta akkor is látszik, ha a
    nevek meccsről meccsre cserélődnek.

    Edzőileg: ha vezettek ellenük, és a mentőjátékuk egy posztra
    épül, annak a posztnak a kivétele (szoros fogás, korai kettőzés)
    a hátrányukat beragasztja — a többiek nincsenek hozzászokva a
    mentéshez. Saját csapatra: a hátrány-figuráinkat tudatosan a
    valódi mentő-posztra kell építeni, de kell mögé második út is.

    Visszatérés csapatonként: {"trailing" (poszthoz kötött hátrány-
    részvétel), "roles": {poszt: darab}, "main_role", "share_pct",
    "verdict"} — az ítélet None, ha nincs meg a CBR_MIN_TRAILING,
    vagy egyik poszt sem éri el a CBR_SHARE_PCT-t.
    """
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    cbc = comeback_carriers(match, config)

    out: dict = {side: {"trailing": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in cbc[side]["players"]:
            if not row["trailing"]:
                continue
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["trailing"])
            rec["trailing"] += row["trailing"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["trailing"] >= CBR_MIN_TRAILING:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["trailing"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= CBR_SHARE_PCT:
                rec["verdict"] = (
                    f"hátrányból a(z) {poszt} posztjuk hozza őket "
                    f"vissza ({share:.0f}%, {rec['trailing']} "
                    "hátrány-gól-részvételből) — ha vezettek, az ő "
                    "kivétele (szoros fogás, korai kettőzés) a "
                    "hátrányukat beragasztja")
    return out


# Csendtörő-poszt: ennyi poszthoz kötött csend-törő gól kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy a
# gólcsendjeiket egy poszt töri meg.
GCT_MIN_BREAKS = 3
GCT_SHARE_PCT = 60.0


def drought_breaker_roles(match: Match, config=None) -> dict:
    """Csendtörő-poszt: MELYIK POSZTJUK töri meg a gólcsendet.

    A csend-törők rétege (drought_breakers) az embert nevezi meg —
    ez a posztot: a legalább DRB_GAP_S másodperces gólcsendet
    megtörő gólokat a lövő posztjához írja. Így a minta akkor is
    látszik, ha a nevek meccsről meccsre cserélődnek.

    Edzőileg ez a saját sorozat védelme: amikor áll a szekerük, a
    labda a válság-posztjukhoz menekül — pont a mi sorozatunk alatt
    őt kell a legszorosabban fogni, mert az ő kivételével a
    csendjük tovább tart. Saját csapatra: ha a csend-törés egy
    poszton áll, a válság-megoldásunk kiszámítható.

    Visszatérés csapatonként: {"breaks" (poszthoz kötött csend-törő
    gól), "roles": {poszt: darab}, "main_role", "share_pct",
    "verdict"} — az ítélet None, ha nincs meg a GCT_MIN_BREAKS,
    vagy egyik poszt sem éri el a GCT_SHARE_PCT-t.
    """
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    db = drought_breakers(match, config)

    out: dict = {side: {"breaks": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in db[side]["players"]:
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["breaks"])
            rec["breaks"] += row["breaks"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["breaks"] >= GCT_MIN_BREAKS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["breaks"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= GCT_SHARE_PCT:
                rec["verdict"] = (
                    f"a gólcsendjüket a(z) {poszt} posztjuk töri meg"
                    f" ({share:.0f}%, {rec['breaks']} csend-törő "
                    "gólból) — a saját sorozatotok alatt őt kell a "
                    "legszorosabban fogni: hozzá menekül a labda, és"
                    " nélküle a csendjük tovább tart")
    return out


# Eltűnő-poszt: ennyi első félidei poszthoz kötött gól-részvétel
# kell, és legfeljebb ennyi második félidei ahhoz, hogy a posztot
# első félidőben élő, másodikra eltűnő posztnak mondjuk ki.
FDP_MIN_FH = 3
FDP_MAX_SH = 1


def fading_scorer_roles(match: Match, config=None) -> dict:
    """Eltűnő-poszt: MELYIK POSZTJUK tűnik el a második félidőre.

    Az eltűnő ember rétege (fading_scorers) az embert nevezi meg —
    ez a posztot: a gól-részvételeket (gól + gólpassz) félidőnként a
    játékos posztjához írja, és megkeresi, melyik posztjuk első
    félidei termelése hal el a másodikra. Így a minta akkor is
    látszik, ha a nevek meccsről meccsre cserélődnek.

    Edzőileg: az eltűnő poszt ellen az első 30 perc a meccs — oda
    duplán, cserével frissen tartott őrzővel kell ráállni, a második
    félidő magától megoldódik. Saját csapatra: az elhaló posztunk a
    terhelés-menedzsment témája (korábbi pihentetés, rövid blokkok).

    Visszatérés csapatonként: {"fh_roles": {poszt: darab},
    "sh_roles": {poszt: darab}, "main_role", "fh", "sh", "verdict"}
    — az ítélet None, ha nincs felismert szünet, vagy egyik poszt
    sem éri el az FDP_MIN_FH-t az FDP_MAX_SH melletti eltűnéssel.
    """
    from .event_detection import EventType, detect_events
    from .halftime import detect_halftime
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    out: dict = {side: {"fh_roles": {}, "sh_roles": {},
                        "main_role": None, "fh": None, "sh": None,
                        "verdict": None}
                 for side in ("home", "away")}
    ht = detect_halftime(match)
    if ht is None:
        return out
    roles = estimate_positions(match, config)

    for e in detect_events(match, config):
        if e.type != EventType.GOAL:
            continue
        side = getattr(e.team, "value", e.team)
        key = "fh_roles" if e.t <= ht else "sh_roles"
        for pid in (e.player_id, (e.detail or {}).get("assist_id")):
            if pid is None:
                continue
            rec_role = roles[side].get(pid)
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            out[side][key][poszt] = (out[side][key].get(poszt, 0)
                                     + 1)

    for side in ("home", "away"):
        rec = out[side]
        fader = None
        for poszt, fh in sorted(rec["fh_roles"].items(),
                                key=lambda kv: -kv[1]):
            sh = rec["sh_roles"].get(poszt, 0)
            if fh >= FDP_MIN_FH and sh <= FDP_MAX_SH:
                fader = (poszt, fh, sh)
                break
        if fader is not None:
            poszt, fh, sh = fader
            rec["main_role"] = poszt
            rec["fh"], rec["sh"] = fh, sh
            rec["verdict"] = (
                f"a(z) {poszt} posztjuk az első félidőben él "
                f"({fh} gól-részvétel), a másodikra eltűnik ({sh}) "
                "— az első 30 percben kell megfogni, duplán és "
                "cserével frissen tartott őrzővel; a második "
                "félidőre a termelése magától elhal")
    return out


# Hajráhiba-poszt: ennyi poszthoz kötött hajrá-eladás kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy a záró
# szakasz eladásai egy posztnál történnek.
CTR_MIN_TO = 3
CTR_SHARE_PCT = 60.0


def clutch_turnover_roles(match: Match, config=None) -> dict:
    """Hajráhiba-poszt: MELYIK POSZTJUK adja el a labdát a hajrában.

    A hajrá-hibázók rétege (clutch_turnover_players) az embert nevezi
    meg — ez a posztot: az utolsó öt perc labdaeladásait a vesztes
    posztjához írja. Így a minta akkor is látszik, ha a nevek
    meccsről meccsre cserélődnek.

    Edzőileg ez a záró percek pressz-terve: amelyik posztjuknál a
    végén rendre elmegy a labda, oda a hajrában kettőzés és
    passzsáv-zárás jön — ott a legolcsóbb a labdaszerzés, amikor a
    legtöbbet ér. Saját csapatra: a hajrá-figurákban az a poszt ne
    kapjon kényszerhelyzetet, vagy tehermentesíteni kell.

    Visszatérés csapatonként: {"turnovers" (poszthoz kötött
    hajrá-eladás), "roles": {poszt: darab}, "main_role",
    "share_pct", "verdict"} — az ítélet None, ha nincs meg a
    CTR_MIN_TO, vagy egyik poszt sem éri el a CTR_SHARE_PCT-t.
    """
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    ctp = clutch_turnover_players(match, config)

    out: dict = {side: {"turnovers": 0, "roles": {},
                        "main_role": None, "share_pct": None,
                        "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in ctp[side]["players"]:
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["turnovers"])
            rec["turnovers"] += row["turnovers"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["turnovers"] >= CTR_MIN_TO:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["turnovers"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= CTR_SHARE_PCT:
                rec["verdict"] = (
                    f"a hajrá-eladásaik {share:.0f}%-a a(z) {poszt} "
                    f"posztnál történik ({rec['turnovers']} eladás "
                    "az utolsó öt percben) — a záró percekben rá "
                    "jöjjön a kettőzés és a passzsáv-zárás: nála a "
                    "legolcsóbb a labdaszerzés, amikor a legtöbbet "
                    "ér")
    return out


# Forró-poszt: ennyi poszthoz kötött, sorozatban lőtt gól kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy a
# sorozataikat egy poszt lövi.
HHR_MIN_GOALS = 3
HHR_SHARE_PCT = 60.0


def hot_hand_roles(match: Match, config=None) -> dict:
    """Forró-poszt: MELYIK POSZTJUK lövi a gólsorozatokat.

    A forró kéz rétege (hot_hands) az embert nevezi meg — ez a
    posztot: a sorozatban (a csapat két vagy több szomszédos gólja
    ugyanattól a lövőtől) lőtt gólokat a lövő posztjához írja. Így a
    minta akkor is látszik, ha a nevek meccsről meccsre cserélődnek.

    Edzőileg ez a lendület-törés terve: ha a sorozataik rendre
    ugyanarról a posztról jönnek, az első gólja után azonnal
    reagálni kell — őrzés-váltás vagy kettőzés, mielőtt a
    második-harmadik jönne. Saját csapatra: a forró posztunkat
    tudatosan kell játékban tartani, amíg tart a lendülete.

    Visszatérés csapatonként: {"streak_goals" (poszthoz kötött,
    sorozatban lőtt gól), "roles": {poszt: darab}, "main_role",
    "share_pct", "verdict"} — az ítélet None, ha nincs meg a
    HHR_MIN_GOALS, vagy egyik poszt sem éri el a HHR_SHARE_PCT-t.
    """
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    hh = hot_hands(match, config)

    out: dict = {side: {"streak_goals": 0, "roles": {},
                        "main_role": None, "share_pct": None,
                        "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for st in hh[side]["streaks"]:
            rec_role = roles[side].get(st["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + st["length"])
            rec["streak_goals"] += st["length"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["streak_goals"] >= HHR_MIN_GOALS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["streak_goals"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= HHR_SHARE_PCT:
                rec["verdict"] = (
                    f"a gólsorozataik {share:.0f}%-a a(z) {poszt} "
                    f"posztról jön ({rec['streak_goals']} sorozatban"
                    " lőtt gólból) — az első gólja után azonnal "
                    "őrzés-váltás vagy kettőzés rá, mielőtt a "
                    "második-harmadik jönne")
    return out


# Középkezdő-poszt: ennyi poszthoz kötött középkezdés-átvétel kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy a
# középkezdésük egy posztnál indul.
RTR_MIN_TAKES = 3
RTR_SHARE_PCT = 60.0


def restart_taker_roles(match: Match, config=None) -> dict:
    """Középkezdő-poszt: MELYIK POSZTJUKNÁL indul a középkezdés.

    A középkezdés-átvevő rétege (restart_targets) az embert nevezi
    meg — ez a posztot: a kapott gól utáni első felező-környéki
    labdaátvételeket az átvevő posztjához írja. Így a minta akkor is
    látszik, ha a nevek meccsről meccsre cserélődnek.

    Edzőileg ez a gól utáni letámadás terve: ha a középkezdésük
    rendre ugyanannál a posztnál indul, a letámadásnak posztra szóló
    célpontja van — őt kell lefogni, és a középkezdésük megáll.
    Saját csapatra: a kiszámítható átvevő variálandó, mert a
    felkészült ellenfél pont őt fogja le.

    Visszatérés csapatonként (a gólt KAPÓ oldal): {"takes"
    (poszthoz kötött átvétel), "roles": {poszt: darab}, "main_role",
    "share_pct", "verdict"} — az ítélet None, ha nincs meg az
    RTR_MIN_TAKES, vagy egyik poszt sem éri el az RTR_SHARE_PCT-t.
    """
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    rt = restart_targets(match, config)

    out: dict = {side: {"takes": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in rt[side]["players"]:
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["takes"])
            rec["takes"] += row["takes"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["takes"] >= RTR_MIN_TAKES:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["takes"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= RTR_SHARE_PCT:
                rec["verdict"] = (
                    f"a kapott gól utáni középkezdésük {share:.0f}"
                    f"%-ban a(z) {poszt} posztnál indul "
                    f"({rec['takes']} átvételből) — a gól utáni "
                    "letámadásnak posztra szóló célpontja van: őt "
                    "kell lefogni, és a középkezdésük megáll")
    return out


# Hajrákéz-poszt: ennyi poszthoz kötött hajrá-labdás kocka kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy a
# végjátékuk egy poszt kezén fut.
CHR_MIN_FRAMES = 200
CHR_SHARE_PCT = 60.0


def clutch_hog_roles(match: Match, config=None) -> dict:
    """Hajrákéz-poszt: MELYIK POSZT KEZÉN fut a végjátékuk.

    A hajrá-labdabirtoklás rétege (clutch_ball_hogs) az embert
    nevezi meg — ez a posztot: az utolsó öt perc labdás kockáit a
    birtokos posztjához írja. Így a minta akkor is látszik, ha a
    nevek meccsről meccsre cserélődnek.

    Edzőileg ez a hajrá-kettőzés címzettje: ha a végjátékuk egy
    poszt kezén fut, nem a lövőket kell fogni, hanem A kezet — ha
    azt a posztot korán labdához sem engedjük, a záró figuráik el
    sem indulnak. Saját csapatra: az egy kézre épülő végjáték
    kockázat, kell a második labdakihozó.

    Visszatérés csapatonként: {"frames" (poszthoz kötött hajrá-
    labdás kocka), "roles": {poszt: kocka}, "main_role",
    "share_pct", "verdict"} — az ítélet None, ha nincs meg a
    CHR_MIN_FRAMES, vagy egyik poszt sem éri el a CHR_SHARE_PCT-t.
    """
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    cbh = clutch_ball_hogs(match, config)

    out: dict = {side: {"frames": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in cbh[side]["players"]:
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["frames"])
            rec["frames"] += row["frames"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["frames"] >= CHR_MIN_FRAMES:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["frames"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= CHR_SHARE_PCT:
                rec["verdict"] = (
                    f"a végjátékuk a(z) {poszt} poszt kezén fut "
                    f"({share:.0f}%-a az utolsó öt perc labdás "
                    "idejének) — a hajrá-kettőzés nem a lövőt fogja,"
                    " hanem ezt a kezet: ha ő nem kap labdát, a záró"
                    " figuráik el sem indulnak")
    return out


# Rajt-poszt: a meccs eleji ablak, ennyi poszthoz kötött nyitó-gól
# kell az ítélethez, és ekkora részarány fölött mondjuk ki, hogy a
# rajtjuk egy posztra épül.
OSR_WINDOW_S = 600.0
OSR_MIN_GOALS = 3
OSR_SHARE_PCT = 60.0


def opening_scorer_roles(match: Match, config=None) -> dict:
    """Rajt-poszt: MELYIK POSZTJUK viszi a meccs elejét.

    A nyitás-profil (opening_profile) csapat-szinten mondja meg,
    hogyan rajtolnak — ez a posztot: a meccs első OSR_WINDOW_S
    másodpercének góljait a lövő posztjához írja. Így a minta akkor
    is látszik, ha a nevek meccsről meccsre cserélődnek.

    Edzőileg ez a meccs eleji párosítás terve: ha a rajtjuk rendre
    ugyanarról a posztról indul, az első tíz percben őt kell a
    legjobb védővel megfogni — a korai elhúzásuk motorja nélkül a
    meccs nyitása kiegyenlített marad. Saját csapatra: az egy
    posztra épülő rajt kockázat, kell a második nyitó-megoldás.

    Visszatérés csapatonként: {"goals" (poszthoz kötött nyitó-gól),
    "roles": {poszt: darab}, "main_role", "share_pct", "verdict"} —
    az ítélet None, ha nincs meg az OSR_MIN_GOALS, vagy egyik poszt
    sem éri el az OSR_SHARE_PCT-t.
    """
    from .event_detection import EventType, detect_shots
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    roles = estimate_positions(match, config)
    t0 = match.frames[0].t if match.frames else 0
    cut = t0 + OSR_WINDOW_S * fps

    out: dict = {side: {"goals": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for e in detect_shots(match, config):
        if e.type != EventType.GOAL or e.player_id is None:
            continue
        if e.t > cut:
            continue
        side = e.team.value
        rec_role = roles[side].get(e.player_id)
        if rec_role is None:
            continue
        poszt = rec_role["poszt"]
        rec = out[side]
        rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1
        rec["goals"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["goals"] >= OSR_MIN_GOALS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["goals"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= OSR_SHARE_PCT:
                rec["verdict"] = (
                    f"a rajtjuk a(z) {poszt} posztra épül "
                    f"({share:.0f}%, {rec['goals']} gól a meccs "
                    "első tíz percében) — az első tíz percben őt "
                    "kell a legjobb védővel megfogni, és a nyitásuk "
                    "kiegyenlített marad")
    return out


# Újrakezdő-poszt: a szünet utáni ablak, ennyi poszthoz kötött gól
# kell az ítélethez, és ekkora részarány fölött mondjuk ki, hogy a
# második félidei rajtjuk egy posztra épül.
SSR_WINDOW_S = 600.0
SSR_MIN_GOALS = 3
SSR_SHARE_PCT = 60.0


def second_start_roles(match: Match, config=None) -> dict:
    """Újrakezdő-poszt: MELYIK POSZTJUK viszi a szünet utáni rajtot.

    A félidő-nyitások rétege (half_openings) csapat-szinten mondja
    meg, hogyan jönnek ki a szünetről — ez a posztot: a második
    félidő első SSR_WINDOW_S másodpercének góljait a lövő posztjához
    írja. Így a minta akkor is látszik, ha a nevek meccsről meccsre
    cserélődnek.

    Edzőileg ez a szünet utáni párosítás terve: sok csapat a
    szünetben beszéli meg, kire építi az újrakezdést — ha az rendre
    ugyanaz a poszt, a második félidő első tíz percében őt kell a
    legjobb védővel megfogni, és a szünet utáni elhúzásuk elmarad.
    Saját csapatra: a második félidei nyitó-megoldás ne egy emberen
    álljon.

    Visszatérés csapatonként: {"goals" (poszthoz kötött szünet
    utáni gól), "roles": {poszt: darab}, "main_role", "share_pct",
    "verdict"} — az ítélet None, ha nincs felismert szünet, nincs
    meg az SSR_MIN_GOALS, vagy egyik poszt sem éri el az
    SSR_SHARE_PCT-t.
    """
    from .event_detection import EventType, detect_shots
    from .halftime import detect_halftime
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    out: dict = {side: {"goals": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    ht = detect_halftime(match)
    if ht is None:
        return out
    roles = estimate_positions(match, config)
    cut = ht + SSR_WINDOW_S * fps

    for e in detect_shots(match, config):
        if e.type != EventType.GOAL or e.player_id is None:
            continue
        if not (ht < e.t <= cut):
            continue
        side = e.team.value
        rec_role = roles[side].get(e.player_id)
        if rec_role is None:
            continue
        poszt = rec_role["poszt"]
        rec = out[side]
        rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1
        rec["goals"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["goals"] >= SSR_MIN_GOALS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["goals"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= SSR_SHARE_PCT:
                rec["verdict"] = (
                    f"a szünet utáni rajtjuk a(z) {poszt} posztra "
                    f"épül ({share:.0f}%, {rec['goals']} gól a "
                    "második félidő első tíz percében) — a szünet "
                    "után őt kell a legjobb védővel megfogni, és az"
                    " elhúzásuk elmarad")
    return out


# Előnyben-poszt: ennyi poszthoz kötött, vezetésnél lőtt gól kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy az
# előny-tartásuk egy posztra épül.
LGR_MIN_GOALS = 3
LGR_SHARE_PCT = 60.0


def lead_scorer_roles(match: Match, config=None) -> dict:
    """Előnyben-poszt: MELYIK POSZTJUK viszi a játékot vezetésnél.

    A felzárkózás-poszt a hátrányt nézi, a hajrá-poszt a záró
    perceket — ez a VEZETÉST: a saját vezetés közben lőtt gólokat a
    lövő posztjához írja. Így látszik, kire épül az előny-tartásuk,
    akkor is, ha a nevek meccsről meccsre cserélődnek.

    Edzőileg ez a lendület-törés terve hátrányban: ha vezetnek, és
    az előny-tartásuk rendre ugyanarról a posztról jön, az ő
    kivételével (szoros fogás, kettőzés) a lendület-tartásuk törik
    meg — a felzárkózásra ez a leggyorsabb út. Saját csapatra: a
    vezetés-tartás ne egy emberen álljon.

    Visszatérés csapatonként: {"goals" (vezetésnél lőtt, poszthoz
    kötött gól), "roles": {poszt: darab}, "main_role", "share_pct",
    "verdict"} — az ítélet None, ha nincs meg az LGR_MIN_GOALS,
    vagy egyik poszt sem éri el az LGR_SHARE_PCT-t.
    """
    from .event_detection import EventType, detect_shots
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)

    out: dict = {side: {"goals": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    score = {"home": 0, "away": 0}
    for e in detect_shots(match, config):
        if e.type != EventType.GOAL:
            continue
        side = e.team.value
        other = "away" if side == "home" else "home"
        leading = score[side] > score[other]   # állás a gól ELŐTT
        score[side] += 1
        if not leading or e.player_id is None:
            continue
        rec_role = roles[side].get(e.player_id)
        if rec_role is None:
            continue
        poszt = rec_role["poszt"]
        rec = out[side]
        rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1
        rec["goals"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["goals"] >= LGR_MIN_GOALS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["goals"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= LGR_SHARE_PCT:
                rec["verdict"] = (
                    f"vezetésnél a(z) {poszt} posztjuk viszi a "
                    f"játékot ({share:.0f}%, {rec['goals']} "
                    "előnyben lőtt gólból) — ha ők vezetnek, az ő "
                    "kivétele (szoros fogás, kettőzés) töri meg a "
                    "lendület-tartásukat")
    return out


# Válasz-poszt: a kapott gól utáni ennyi másodpercben lőtt gól számít
# azonnali válasznak; ennyi poszthoz kötött válasz-gól kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy a válaszuk
# egy posztra épül.
RSP_WINDOW_S = 60.0
RSP_MIN_GOALS = 3
RSP_SHARE_PCT = 60.0


def response_scorer_roles(match: Match, config=None) -> dict:
    """Válasz-poszt: KAPOTT GÓL UTÁN melyik posztjuk válaszol.

    A kapott gól utáni megingás (post_goal_lapses) csapat-szinten
    mondja meg, mi történik a bekapott gól után — ez a posztot: a
    kapott gólt RSP_WINDOW_S másodpercen belül követő SAJÁT gólokat
    a lövő posztjához írja. Így látszik, kire fut ki a válasz-
    támadásuk.

    Edzőileg ez a gól utáni első védekezés terve: ha a válaszuk
    rendre ugyanarról a posztról jön, a saját gólunk után azonnal az
    ő fogására kell váltani (kiemelt őrzés, korai kettőzés) — a
    lendületük ott törik meg, ahol elindulna. Saját csapatra: ha a
    válaszunk egy emberen áll, a bekapott gól után kiszámíthatók
    vagyunk.

    Visszatérés csapatonként: {"goals" (poszthoz kötött válasz-gól),
    "roles": {poszt: darab}, "main_role", "share_pct", "verdict"} —
    az ítélet None, ha nincs meg az RSP_MIN_GOALS, vagy egyik poszt
    sem éri el az RSP_SHARE_PCT-t.
    """
    from .event_detection import EventType, detect_shots
    from .roles import estimate_positions
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = RSP_WINDOW_S * fps
    roles = estimate_positions(match, config)

    goals = [(e.t, e.team.value, e.player_id)
             for e in detect_shots(match, config)
             if e.type == EventType.GOAL]

    out: dict = {side: {"goals": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for i, (t, side, pid) in enumerate(goals):
        if pid is None:
            continue
        # Volt-e az ablakon belül ELŐTTE kapott gól?
        kapott = any(t0 < t and t - t0 <= win and s0 != side
                     for (t0, s0, _p) in goals[:i])
        if not kapott:
            continue
        rec_role = roles[side].get(pid)
        if rec_role is None:
            continue
        poszt = rec_role["poszt"]
        rec = out[side]
        rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1
        rec["goals"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["goals"] >= RSP_MIN_GOALS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["goals"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= RSP_SHARE_PCT:
                rec["verdict"] = (
                    f"kapott gól után a(z) {poszt} posztjuk válaszol"
                    f" ({share:.0f}%, {rec['goals']} válasz-gólból)"
                    " — a saját gólotok után azonnal az ő fogására "
                    "váltsatok: ott törik meg a lendületük, mielőtt "
                    "elindulna")
    return out
