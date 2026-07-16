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
