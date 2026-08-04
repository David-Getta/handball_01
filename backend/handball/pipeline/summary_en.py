"""Angol meccs-kártya — tömör, angol nyelvű meccs-összefoglaló.

A magyar edzői összefoglaló (coach_summary) a termék lelke — ez a
nemzetközi felület: EU-s pilotokhoz, bemutatókhoz és értékelőknek ad
egy rövid, tényszerű angol kártyát a meccsről (eredmény, félidő,
gólfelelősök, hatékonyság, legnagyobb sorozat, hetesek, kiállítások).
Szándékosan tömör és ítélet-mentes: a taktikai ítéletek magyarul, a
teljes elemzési mélységgel élnek — ez a kártya a kapunyitó.
"""

from __future__ import annotations

from typing import Optional

from ..models.tracking import Match


def match_card_en(match: Match, config=None) -> dict:
    """English match card: compact, English-language match summary.

    Returns {"headline": str, "lines": [str, ...]} — headline is the
    final score ("Home 27–24 Away"), lines are short factual English
    sentences (halftime score, top scorers, shooting efficiency,
    longest scoring run, seven-metre throws, suspensions). Facts that
    cannot be established are simply omitted — the card never guesses.
    """
    from .event_detection import EventType, detect_shots
    from .halftime import detect_halftime
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    home = match.meta.home_team or "Home"
    away = match.meta.away_team or "Away"
    events = detect_shots(match, config)
    goals = [(e.t, getattr(e.team, "value", e.team), e.player_id)
             for e in events if e.type == EventType.GOAL]
    shots = [(getattr(e.team, "value", e.team)) for e in events
             if e.type in (EventType.SHOT, EventType.GOAL)]
    gh = sum(1 for (_, tm, _) in goals if tm == "home")
    ga = sum(1 for (_, tm, _) in goals if tm == "away")
    lines: list[str] = []

    headline = f"{home} {gh}\u2013{ga} {away}"

    ht = detect_halftime(match)
    if ht is not None:
        hh = sum(1 for (t, tm, _) in goals if t <= ht and tm == "home")
        ha = sum(1 for (t, tm, _) in goals if t <= ht and tm == "away")
        lines.append(f"Halftime: {hh}\u2013{ha}.")

    for side, name in (("home", home), ("away", away)):
        tally: dict = {}
        for (_, tm, pid) in goals:
            if tm == side and pid is not None:
                tally[pid] = tally.get(pid, 0) + 1
        if tally:
            pid, n = max(tally.items(), key=lambda kv: kv[1])
            if n >= 2:
                lines.append(f"Top scorer for {name}: player #{pid} "
                             f"with {n} goals.")

    for side, name, g in (("home", home, gh), ("away", away, ga)):
        s = sum(1 for tm in shots if tm == side)
        if s >= 5:
            lines.append(f"{name} converted {g} of {s} shots "
                         f"({100.0 * g / s:.0f}%).")

    try:
        from .momentum import scoring_runs
        runs = scoring_runs(match, config=config)
        best = max((r for r in runs), key=lambda r: r.get("length", 0),
                   default=None)
        if best and best.get("length", 0) >= 3:
            name = home if best.get("team") == "home" else away
            lines.append(f"Longest scoring run: {best['length']}\u20130 "
                         f"by {name}.")
    except Exception:
        pass

    try:
        from .rules import detect_powerplay, detect_seven_meters
        sevens = detect_seven_meters(match, config)
        if sevens:
            sh = sum(1 for sm in sevens if sm["team"] == "home")
            lines.append(f"Seven-metre throws: {sh} for {home}, "
                         f"{len(sevens) - sh} for {away}.")
        pps = detect_powerplay(match)
        if pps:
            ph = sum(1 for w in pps if w["team_down"] == "home")
            lines.append(f"Suspensions: {ph} for {home}, "
                         f"{len(pps) - ph} for {away}.")
    except Exception:
        pass

    return {"headline": headline, "lines": lines}


# Angol felderítő kártya: ennyi minta kell egy-egy állításhoz, és
# ekkora gól−xG eltérés fölött mondjuk ki a befejezés-minőséget.
SCEN_MIN_SHOTS = 5
SCEN_MIN_ATTACKS = 5
SCEN_MIN_KICKOUTS = 4
SCEN_XG_GAP = 1.0
SCEN_KICKOUT_PCT = 55.0


def scouting_cards_en(match: Match, config=None) -> dict:
    """English scouting card: a one-page opponent brief per team.

    A magyar felderítő jelentés (scouting.scout_team) a teljes mélység
    — ez a nemzetközi felület: EU-s pilot-klubnak, bemutatónak és
    értékelőnek ad rövid, tényszerű angol pontokat az ellenfélről.
    Szándékosan a MEGÁLLAPÍTHATÓ tényekre szorítkozik: amihez kevés a
    minta, az egyszerűen kimarad (nem találgatunk).

    Returns per team: {"headline": str, "lines": [str, ...]} —
    headline is the team name, lines are short factual English
    statements (attack identity, defensive formation, finishing,
    chance quality, what they concede, ball security, possession,
    and the kick-out target after a drive).
    """
    from ..models.tracking import Team
    from .scouting import scout_team
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    out: dict = {}
    for side, team in (("home", Team.HOME), ("away", Team.AWAY)):
        try:
            rep = scout_team(match, team, config)
        except Exception:
            out[side] = {"headline": side, "lines": []}
            continue
        lines: list[str] = []

        if rep.attacks >= SCEN_MIN_ATTACKS:
            lines.append(
                f"Attacking style: {rep.fast_break_pct:.0f}% of their "
                f"attacks come from transition; a set attack lasts "
                f"{rep.avg_attack_duration_s:.0f} s on average "
                f"({rep.attacks} attacks measured).")
        if rep.defense_main and rep.defense_main != "—":
            lines.append(f"Main defensive formation: {rep.defense_main}.")
        if rep.shots >= SCEN_MIN_SHOTS:
            lines.append(
                f"Finishing: {rep.shot_efficiency_pct:.0f}% "
                f"({rep.goals} goals from {rep.shots} shots).")
            if abs(rep.xg_diff) >= SCEN_XG_GAP:
                word = ("outperform" if rep.xg_diff > 0 else "underperform")
                lines.append(
                    f"They {word} their chances by "
                    f"{abs(rep.xg_diff):.1f} goals (xG {rep.xg:.1f}) — "
                    "the difference is in the finishing, not the "
                    "chance creation.")
        if rep.def_shots_against >= SCEN_MIN_SHOTS:
            lines.append(
                f"What they concede: {rep.def_free_shots} of "
                f"{rep.def_shots_against} shots against were "
                "unmarked (no defender within 2 m of the shooter).")
        if rep.turnover_total >= SCEN_MIN_SHOTS:
            lines.append(
                f"Ball security: {rep.turnover_total} turnovers, "
                f"{rep.turnover_front} of them in the attacking third "
                "(those are the ones that turn into fast breaks).")
        if rep.possession_pct:
            lines.append(f"Possession: {rep.possession_pct:.0f}%.")
        if rep.kot_targets and rep.kot_kickouts >= SCEN_MIN_KICKOUTS:
            who, n = max(rep.kot_targets.items(), key=lambda kv: kv[1])
            pct = 100.0 * n / rep.kot_kickouts
            if pct >= SCEN_KICKOUT_PCT:
                lines.append(
                    f"After a drive into the wall, the ball goes to "
                    f"{who} {pct:.0f}% of the time ({n} of "
                    f"{rep.kot_kickouts}) — that pass lane can be "
                    "taken away.")
        out[side] = {"headline": rep.team_name or side, "lines": lines}
    return out
