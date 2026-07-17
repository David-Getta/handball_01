"""Irányító-függés — mi történik a csapattal, ha a fő szervező nincs játékban.

Sok csapat egyetlen irányítón keresztül épít: ha őt megfogod, összeomlik
a támadásuk. Ezt mérjük ki a felismert adatokból:

1. IRÁNYÍTÓ: a csapat legtöbb labdabirtoklás-idejű játékosa.
2. Minden támadás-szakaszra (segment_attacks) megnézzük, a labdánál
   volt-e — majd összevetjük a VELE és a NÉLKÜLE futott támadások
   eredményességét (lövésig/gólig jutottak-e).
3. FÜGGÉS: ha nélküle érezhetően romlik a lövésig jutás, a felderítő
   jelentés konkrét kulcsot ad: "fogd meg — nélküle leáll a játékuk".

Tiszta adatfeldolgozás, videó nélkül tesztelhető.
"""

from __future__ import annotations

from typing import Optional

from ..models.tracking import Match, Team
from .tactics import TacticsConfig

# Legalább ennyi támadás kell MINDKÉT csoportban (vele/nélküle), hogy a
# különbségről érdemes legyen beszélni.
MIN_ATTACKS_PER_GROUP = 3
# Ekkora lövésig-jutási különbség felett mondjuk, hogy a függés MAGAS.
HIGH_DEPENDENCY_DROP = 0.25


def playmaker_dependency(match: Match,
                         config: Optional[TacticsConfig] = None) -> dict:
    """Mindkét csapat irányító-függése.

    Visszatérés csapatonként ("home"/"away"):
    {"playmaker": track_id | None, "involvement_pct": float,
     "with": {"attacks", "shots", "goals"},
     "without": {"attacks", "shots", "goals"},
     "shot_rate_drop": float | None,  # lövésig jutás esése nélküle (0..1)
     "dependency": "magas" | "mérsékelt" | None}
    — None/üres, ha nincs elég adat."""
    from .decisions import ball_holder
    from .event_detection import EventType, detect_shots
    from .setplays import segment_attacks

    config = config or TacticsConfig()

    # Labdabirtoklás-idő játékosonként (az irányító-jelölt kereséséhez).
    poss: dict[Team, dict[int, int]] = {Team.HOME: {}, Team.AWAY: {}}
    holder_by_t: dict[int, tuple[Team, int]] = {}
    for f in match.frames:
        h = ball_holder(f, config)
        if h is not None:
            poss[h.team][h.track_id] = poss[h.team].get(h.track_id, 0) + 1
            holder_by_t[f.t] = (h.team, h.track_id)

    shots = [(e.t, e.team, e.type == EventType.GOAL)
             for e in detect_shots(match, config)]
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    tail = round(2.0 * fps)  # a támadás végét követő lövést is a szakaszhoz vesszük

    attacks = segment_attacks(match, config)
    out: dict = {}
    for team in (Team.HOME, Team.AWAY):
        rec = {"playmaker": None, "involvement_pct": 0.0,
               "with": {"attacks": 0, "shots": 0, "goals": 0},
               "without": {"attacks": 0, "shots": 0, "goals": 0},
               "shot_rate_drop": None, "dependency": None}
        out[team.value] = rec
        if not poss[team]:
            continue
        pm, pm_frames = max(poss[team].items(), key=lambda kv: kv[1])
        total = sum(poss[team].values())
        rec["playmaker"] = pm
        rec["involvement_pct"] = round(100.0 * pm_frames / total, 1)

        for seg in attacks:
            if seg.team != team:
                continue
            involved = any(holder_by_t.get(f.t) == (team, pm)
                           for f in seg.frames)
            grp = rec["with"] if involved else rec["without"]
            grp["attacks"] += 1
            seg_shots = [(t, goal) for (t, tm, goal) in shots
                         if tm == team and seg.start_t <= t <= seg.end_t + tail]
            if seg_shots:
                grp["shots"] += 1  # a támadás lövésig jutott
                if any(g for (_, g) in seg_shots):
                    grp["goals"] += 1

        w, wo = rec["with"], rec["without"]
        if (w["attacks"] >= MIN_ATTACKS_PER_GROUP
                and wo["attacks"] >= MIN_ATTACKS_PER_GROUP):
            rate_w = w["shots"] / w["attacks"]
            rate_wo = wo["shots"] / wo["attacks"]
            rec["shot_rate_drop"] = round(rate_w - rate_wo, 2)
            if rec["shot_rate_drop"] >= HIGH_DEPENDENCY_DROP:
                rec["dependency"] = "magas"
            elif rec["shot_rate_drop"] >= 0.10:
                rec["dependency"] = "mérsékelt"
    return out
