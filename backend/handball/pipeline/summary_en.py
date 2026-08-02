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
