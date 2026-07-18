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
