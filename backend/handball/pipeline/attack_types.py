"""Támadás-típus címkézés — lerohanás / gyors indítás / felállt / 7 a 6.

A meccs támadás-szakaszait (setplays.segment_attacks) sorolja be négy,
edzői nyelven értelmes típusba. A szabályok szándékosan egyszerűek és
magyarázhatók (minden címke mögött mért szám áll):

- 7 A 6:          a szakasz ideje nagyrészt egybeesik egy lehozott kapusos
                  (detect_empty_net) ablakkal.
- LEROHANÁS:      rövid támadás (<= 6 mp), amely alatt a labda gyorsan
                  halad az ellenfél kapuja felé (>= 2 m/s nettó előrehaladás).
- GYORS INDÍTÁS:  legfeljebb 12 mp, érdemi előrehaladással (>= 1 m/s) —
                  gyors középkezdés / korai befejezés, de nem teljes sprint.
- FELÁLLT TÁMADÁS: minden más (türelmes játék a felállt védelem ellen).

Ebből áll össze a csapat TÁMADÁS-MIXE — a felderítés egyik legbeszédesebb
száma ("támadásaik 30%-a lerohanás → zárj vissza azonnal").
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from ..models.tracking import Match
from .setplays import segment_attacks
from .tactics import TacticsConfig

# Küszöbök (magyarázható, mért szabályok):
FAST_BREAK_MAX_S = 6.0     # lerohanás: legfeljebb ennyi ideig tart
FAST_BREAK_ADV_MS = 2.0    # ... és a labda legalább ennyivel halad előre
QUICK_MAX_S = 12.0         # gyors indítás: legfeljebb ennyi
QUICK_ADV_MS = 1.0         # ... legalább ennyi előrehaladással
SEVEN_SIX_OVERLAP = 0.5    # 7a6: a szakasz ekkora része esik üres-kapus ablakba


class AttackType(str, Enum):
    FAST_BREAK = "lerohanás"
    QUICK = "gyors indítás"
    POSITIONAL = "felállt támadás"
    SEVEN_SIX = "7 a 6"


def _advance_speed(seq, target_x: float, fps: float) -> float:
    """A labda nettó előrehaladási sebessége a kapu felé (m/s) a szakaszban."""
    first = next((f.ball for f in seq.frames if f.ball is not None), None)
    last = next((f.ball for f in reversed(seq.frames) if f.ball is not None),
                None)
    if first is None or last is None or seq.length < 2:
        return 0.0
    sign = 1.0 if target_x >= 20.0 else -1.0  # a +x vagy a -x kapura támad
    duration_s = seq.length / fps
    return (last.x - first.x) * sign / duration_s if duration_s > 0 else 0.0


def classify_attacks(match: Match,
                     config: Optional[TacticsConfig] = None) -> list[dict]:
    """A meccs támadás-szakaszai típus-címkével, időrendben.

    Visszatérés: [{"team", "start_frame", "end_frame", "duration_s",
    "type"}, ...] — a "type" az AttackType értéke (magyarul).
    """
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0

    # 7a6 ablakok (kapus-jelölés nélkül üres lista — a többi címke él).
    try:
        from .goalkeeper import detect_empty_net
        empty = detect_empty_net(match, config)
    except Exception:
        empty = []

    out: list[dict] = []
    for seq in segment_attacks(match, config):
        duration_s = seq.length / fps
        target_x = config.attacks_toward_x(seq.team)

        overlap = 0
        for w in empty:
            if w["team"] != seq.team.value:
                continue
            o = min(seq.end_t, w["end_frame"]) - max(seq.start_t,
                                                     w["start_frame"]) + 1
            if o > 0:
                overlap += o
        if overlap / max(1, seq.length) >= SEVEN_SIX_OVERLAP:
            label = AttackType.SEVEN_SIX
        else:
            adv = _advance_speed(seq, target_x, fps)
            if duration_s <= FAST_BREAK_MAX_S and adv >= FAST_BREAK_ADV_MS:
                label = AttackType.FAST_BREAK
            elif duration_s <= QUICK_MAX_S and adv >= QUICK_ADV_MS:
                label = AttackType.QUICK
            else:
                label = AttackType.POSITIONAL

        out.append({
            "team": seq.team.value,
            "start_frame": seq.start_t,
            "end_frame": seq.end_t,
            "duration_s": round(duration_s, 1),
            "type": label.value,
        })
    return out


# A támadás végét követő lövést is a szakaszhoz vesszük (a befejezés a
# birtoklás lezárulta után pár tizedmásodperccel csapódik le lövésként).
ATTACK_TAIL_S = 2.0


def attack_efficiency(match: Match,
                      config: Optional[TacticsConfig] = None) -> dict:
    """Támadás-típusonkénti befejezés-hatékonyság csapatonként.

    Minden felismert támadás-szakaszhoz (classify_attacks) hozzápárosítjuk
    a szakasz idején (+ ATTACK_TAIL_S) az adott csapattól ugyanarra a
    kapura leadott ELSŐ lövést, és megnézzük, gól lett-e. Így látszik,
    melyik támadás-típus mennyire eredményes — pl. "a lerohanásaik 80%-a
    gól, de a felállt támadásuk csak 30%".

    Visszatérés csapatonként:
    {típus: {"attacks", "shots", "goals", "shot_pct", "goal_pct"}}
    — shot_pct: lövésig jutott támadások aránya; goal_pct: gólig jutottak.
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    tail = round(ATTACK_TAIL_S * fps)
    shots = [(e.t, e.team.value, e.type == EventType.GOAL)
             for e in detect_shots(match, config)
             if e.type in (EventType.SHOT, EventType.GOAL)]

    out: dict = {"home": {}, "away": {}}
    for a in classify_attacks(match, config):
        side = a["team"]
        rec = out[side].setdefault(a["type"],
                                   {"attacks": 0, "shots": 0, "goals": 0})
        rec["attacks"] += 1
        hit = next(((t, goal) for (t, tm, goal) in shots
                    if tm == side
                    and a["start_frame"] <= t <= a["end_frame"] + tail),
                   None)
        if hit is not None:
            rec["shots"] += 1
            if hit[1]:
                rec["goals"] += 1
    for side in ("home", "away"):
        for rec in out[side].values():
            n = max(1, rec["attacks"])
            rec["shot_pct"] = round(100.0 * rec["shots"] / n, 1)
            rec["goal_pct"] = round(100.0 * rec["goals"] / n, 1)
    return out


# Támadás-hossz vödrök (mp): rövid / közepes / hosszú.
DURATION_BUCKETS = ((15.0, "rövid (<15 mp)"), (35.0, "közepes (15–35 mp)"))
DURATION_LONG_LABEL = "hosszú (35 mp+)"


def attack_duration_efficiency(match: Match,
                               config: Optional[TacticsConfig] = None) -> dict:
    """Befejezés-hatékonyság a támadás HOSSZA szerint.

    Ugyanaz a lövés-párosítás, mint az attack_efficiency-nél, de a
    vödrök a támadás időtartama szerint (rövid/közepes/hosszú). Ebből
    látszik, megéri-e a csapatnak a hosszú, türelmes játék — vagy épp a
    gyors befejezés hozza a góljait.

    Visszatérés csapatonként:
    {vödör: {"attacks", "shots", "goals", "goal_pct"}}.
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    tail = round(ATTACK_TAIL_S * fps)
    shots = [(e.t, e.team.value, e.type == EventType.GOAL)
             for e in detect_shots(match, config)
             if e.type in (EventType.SHOT, EventType.GOAL)]

    def bucket(duration_s: float) -> str:
        for edge, label in DURATION_BUCKETS:
            if duration_s < edge:
                return label
        return DURATION_LONG_LABEL

    out: dict = {"home": {}, "away": {}}
    for a in classify_attacks(match, config):
        side = a["team"]
        dur_s = (a["end_frame"] - a["start_frame"] + 1) / fps
        rec = out[side].setdefault(bucket(dur_s),
                                   {"attacks": 0, "shots": 0, "goals": 0})
        rec["attacks"] += 1
        hit = next(((t, goal) for (t, tm, goal) in shots
                    if tm == side
                    and a["start_frame"] <= t <= a["end_frame"] + tail),
                   None)
        if hit is not None:
            rec["shots"] += 1
            if hit[1]:
                rec["goals"] += 1
    for side in ("home", "away"):
        for rec in out[side].values():
            rec["goal_pct"] = round(
                100.0 * rec["goals"] / max(1, rec["attacks"]), 1)
    return out


def attack_mix(match: Match,
               config: Optional[TacticsConfig] = None) -> dict:
    """Csapatonkénti támadás-mix: {csapat: {típus: százalék}}.

    Csak azok a csapatok szerepelnek, amelyeknek volt támadás-szakasza;
    a százalékok a csapat összes támadásához mértek.
    """
    counts: dict[str, dict[str, int]] = {}
    for a in classify_attacks(match, config):
        counts.setdefault(a["team"], {})
        counts[a["team"]][a["type"]] = counts[a["team"]].get(a["type"], 0) + 1
    out: dict = {}
    for team, by_type in counts.items():
        total = sum(by_type.values())
        out[team] = {t: round(100.0 * n / total, 1)
                     for t, n in sorted(by_type.items(), key=lambda kv: -kv[1])}
    return out


def fast_break_finishers(match: Match,
                         config: Optional[TacticsConfig] = None) -> dict:
    """Ki fejezi be a lerohanásokat: a lerohanás-szakaszokra eső gólok
    lövőnkénti darabszáma. A kontra-védekezés kulcs-adata — ha mindig
    ugyanaz a játékos fut ki, őt kell először felvenni.

    Visszatérés csapatonként: [{"player_id", "goals"}] gólszám szerint.
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    tail = round(ATTACK_TAIL_S * fps)
    goals = [(e.t, e.team.value, e.player_id)
             for e in detect_shots(match, config)
             if e.type == EventType.GOAL and e.player_id is not None]

    tally: dict = {"home": {}, "away": {}}
    for a in classify_attacks(match, config):
        if a["type"] != AttackType.FAST_BREAK.value:
            continue
        side = a["team"]
        for (t, tm, pid) in goals:
            if tm == side and a["start_frame"] <= t <= a["end_frame"] + tail:
                tally[side][pid] = tally[side].get(pid, 0) + 1
                break
    return {side: [{"player_id": pid, "goals": n}
                   for pid, n in sorted(rec.items(), key=lambda kv: -kv[1])]
            for side, rec in tally.items()}


# Meccs-tempó küszöbök: összesített támadás/perc — e fölött "tempós",
# ez alatt "lassú" a meccs (a kettő közt "közepes tempójú").
PACE_FAST_PER_MIN = 2.2
PACE_SLOW_PER_MIN = 1.4
PACE_MIN_DURATION_MIN = 10.0


def match_pace(match: Match,
               config: Optional[TacticsConfig] = None,
               half_t: int | None = None) -> dict:
    """Meccs-tempó: hány támadás jut egy percre.

    A tempó a taktika lenyomata: a sok támadás gyors, oda-vissza
    játékot jelent (kontra-kockázattal), a kevés türelmes építkezést.
    Rövid felvételen (PACE_MIN_DURATION_MIN alatt) nem értelmezzük.

    Visszatérés: {"available", "duration_min", "home_attacks",
    "away_attacks", "per_min", "label", "halves"} — a label
    gyors/közepes/lassú; a halves {"first_per_min", "second_per_min"}
    a felismert (vagy megadott) félidő-határ szerint, ha mindkét fél
    legalább 5 perc — különben None.
    """
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    duration_min = len(match.frames) / fps / 60.0
    if duration_min < PACE_MIN_DURATION_MIN:
        return {"available": False, "duration_min": round(duration_min, 1)}
    counts = {"home": 0, "away": 0}
    seqs = list(segment_attacks(match, config))
    for seq in seqs:
        counts[seq.team.value] += 1
    total = counts["home"] + counts["away"]
    per_min = total / duration_min
    label = ("gyors" if per_min >= PACE_FAST_PER_MIN
             else "lassú" if per_min <= PACE_SLOW_PER_MIN
             else "közepes")
    # Félidőnkénti bontás: elárulja, elfogy-e a meccsből a tempó.
    halves = None
    if half_t is None:
        try:
            from .halftime import detect_halftime
            half_t = detect_halftime(match)
        except Exception:
            half_t = None
    if half_t is not None:
        first_min = half_t / fps / 60.0
        second_min = (len(match.frames) - half_t) / fps / 60.0
        if first_min >= 5.0 and second_min >= 5.0:
            first_n = sum(1 for seq in seqs if seq.start_t < half_t)
            halves = {
                "first_per_min": round(first_n / first_min, 2),
                "second_per_min": round((total - first_n) / second_min, 2),
            }
    return {"available": True, "duration_min": round(duration_min, 1),
            "home_attacks": counts["home"], "away_attacks": counts["away"],
            "per_min": round(per_min, 2), "label": label,
            "halves": halves}


# Támadás-eredet: az előzmény-esemény legfeljebb ennyi másodperccel a
# támadás kezdete előtt számít bele az eredet-címkébe.
ORIGIN_LOOKBACK_S = 8.0


def attack_origins(match: Match,
                   config: Optional[TacticsConfig] = None) -> dict:
    """Honnan indulnak a támadások: középkezdésből (kapott gól után),
    kidobásból (az ellenfél kimaradt lövése után) vagy labdaszerzésből
    (minden más). A kontra-védekezés tervezéséhez: akinek a góljai
    labdaszerzésből jönnek, az ellen a labdabiztonság duplán számít.

    Visszatérés csapatonként: {eredet: {"attacks", "goals"}}.
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    look = ORIGIN_LOOKBACK_S * fps
    tail = round(ATTACK_TAIL_S * fps)
    shots = [(e.t, e.team.value, e.type == EventType.GOAL)
             for e in detect_shots(match, config)
             if e.type in (EventType.SHOT, EventType.GOAL)]

    out: dict = {side: {} for side in ("home", "away")}
    for a in classify_attacks(match, config):
        side = a["team"]
        opp = "away" if side == "home" else "home"
        # Az utolsó ellenfél-lövés a támadás kezdete előtti ablakban.
        prev = None
        for (t, tm, goal) in shots:
            if tm == opp and a["start_frame"] - look <= t < a["start_frame"]:
                prev = (t, goal)
        if prev is None:
            origin = "labdaszerzés"
        elif prev[1]:
            origin = "középkezdés"
        else:
            origin = "kidobás"
        rec = out[side].setdefault(origin, {"attacks": 0, "goals": 0})
        rec["attacks"] += 1
        hit = next((True for (t, tm, goal) in shots
                    if tm == side and goal
                    and a["start_frame"] <= t <= a["end_frame"] + tail),
                   False)
        if hit:
            rec["goals"] += 1
    return out


# Előny-kezelés: ennyi mérhető támadás kell mindkét állás-helyzetben.
SCORE_PACE_MIN_ATTACKS = 3


def pace_by_score(match, config=None) -> dict:
    """Támadás-hossz állás szerint: mit csinál a csapat előnyben és
    hátrányban.

    Minden támadás-szakaszhoz megnézzük a támadó csapat gólkülönbségét
    a szakasz kezdetén (vezet / hátrányban / döntetlen), és állásonként
    átlagoljuk a szakasz hosszát. A vezetésnél elnyúló támadás =
    időhúzás; a hátrányban rövidülő = kapkodás — mindkettő edzői jel.

    Visszatérés csapatonként: {"leading"/"trailing"/"level":
    {"attacks", "sum_s", "avg_s"}} — avg_s None, ha nincs elég minta.
    """
    from ..models.tracking import Team
    from .event_detection import EventType, detect_shots
    from .setplays import segment_attacks
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    goals = [(e.t, e.team.value) for e in detect_shots(match, config)
             if e.type == EventType.GOAL]
    out = {side: {k: {"attacks": 0, "sum_s": 0.0, "avg_s": None}
                  for k in ("leading", "trailing", "level")}
           for side in ("home", "away")}
    for seq in segment_attacks(match, config):
        side = seq.team.value
        own = sum(1 for (t, tm) in goals if t < seq.start_t and tm == side)
        opp = sum(1 for (t, tm) in goals if t < seq.start_t and tm != side)
        state = ("leading" if own > opp
                 else "trailing" if own < opp else "level")
        rec = out[side][state]
        rec["attacks"] += 1
        rec["sum_s"] += (seq.end_t - seq.start_t + 1) / fps
    for side in ("home", "away"):
        for rec in out[side].values():
            if rec["attacks"] >= SCORE_PACE_MIN_ATTACKS:
                rec["avg_s"] = round(rec["sum_s"] / rec["attacks"], 1)
            rec["sum_s"] = round(rec["sum_s"], 1)
    return out
