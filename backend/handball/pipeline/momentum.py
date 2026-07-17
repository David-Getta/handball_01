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
