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


# Támadás-szélesség: legalább ennyi mérhető kocka kell az átlaghoz.
ATTACK_WIDTH_MIN_FRAMES = 100


def attack_width(match, config=None) -> dict:
    """Támadás-szélesség: mennyire húzza szét a csapat a pályát.

    Saját labdabirtoklású kockánként a támadott térfélen lévő (nem
    kapus) támadók oldalirányú terjedelme (max y − min y), legalább
    3 látott támadóval. A széles játék a fal széthúzásának, a szűk a
    közép-erőltetésnek a jele — mindkettő ellen más a recept.

    Visszatérés csapatonként: {"frames", "avg_width_m"} — az átlag
    None, ha nincs ATTACK_WIDTH_MIN_FRAMES mérhető kocka.
    """
    from ..models.tracking import Team
    from .tactics import TacticsConfig, possession_team

    config = config or TacticsConfig()
    acc = {"home": [0, 0.0], "away": [0, 0.0]}  # (kocka, összeg)
    for fr in match.frames:
        poss = possession_team(fr, config)
        if poss is None:
            continue
        goal_x = config.attacks_toward_x(poss)
        ys = [p.y for p in fr.players
              if p.team == poss and p.role != "kapus"
              and abs(p.x - goal_x) <= 15.0]
        if len(ys) < 3:
            continue
        rec = acc[poss.value]
        rec[0] += 1
        rec[1] += max(ys) - min(ys)
    out = {}
    for side in ("home", "away"):
        n, sum_w = acc[side]
        out[side] = {
            "frames": n,
            "avg_width_m": (round(sum_w / n, 1)
                            if n >= ATTACK_WIDTH_MIN_FRAMES else None),
        }
    return out


# Beálló-terhelés: a támadás akkor "beállós", ha a labda legalább ennyi
# kockán át a becsült beállónál járt a szakasz alatt (villanás ellen).
PIVOT_TOUCH_MIN_FRAMES = 3


def pivot_usage(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """Beálló-terhelés: a támadások mekkora része megy át a beállón, és
    az eredményesebb-e, mint a beálló nélküli játék.

    A poszt-becslés (estimate_positions) beállói + a labdabirtokos
    kockánkénti azonosítása adja a "beállós támadás" címkét; a
    lövés-párosítás ugyanaz, mint az attack_efficiency-nél (a szakasz
    + ATTACK_TAIL_S alatti első saját lövés).

    Visszatérés csapatonként:
      {"attacks", "pivot_attacks", "pivot_goals", "other_goals",
       "pivot_share_pct", "pivot_goal_pct", "other_goal_pct",
       "pivot_ids", "pivot_goal_ts"}
    — a pct-k None, ha a nevezőjük 0; pivot_ids: a becsült beálló
    track-ek (mezszám híján is stabil kulcs).
    """
    from .decisions import ball_holder
    from .event_detection import EventType, detect_shots
    from .roles import estimate_positions
    from .setplays import segment_attacks

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    tail = round(ATTACK_TAIL_S * fps)
    posts = estimate_positions(match, config)
    pivots = {side: {tid for tid, r in posts.get(side, {}).items()
                     if r["poszt"] == "beálló"}
              for side in ("home", "away")}
    shots = [(e.t, e.team.value, e.type == EventType.GOAL)
             for e in detect_shots(match, config)
             if e.type in (EventType.SHOT, EventType.GOAL)]

    out = {side: {"attacks": 0, "pivot_attacks": 0, "pivot_goals": 0,
                  "other_goals": 0, "pivot_ids": sorted(pivots[side]),
                  "pivot_goal_ts": []}
           for side in ("home", "away")}
    for seq in segment_attacks(match, config):
        side = seq.team.value
        rec = out[side]
        rec["attacks"] += 1
        touch = 0
        for fr in seq.frames:
            h = ball_holder(fr, config)
            if h is not None and h.track_id in pivots[side]:
                touch += 1
        is_pivot = touch >= PIVOT_TOUCH_MIN_FRAMES
        goal_t = next((t for (t, tm, g) in shots
                       if tm == side and g
                       and seq.start_t <= t <= seq.end_t + tail), None)
        if is_pivot:
            rec["pivot_attacks"] += 1
            if goal_t is not None:
                rec["pivot_goals"] += 1
                rec["pivot_goal_ts"].append(goal_t)
        elif goal_t is not None:
            rec["other_goals"] += 1

    for rec in out.values():
        other = rec["attacks"] - rec["pivot_attacks"]
        rec["pivot_share_pct"] = (
            round(100.0 * rec["pivot_attacks"] / rec["attacks"], 1)
            if rec["attacks"] else None)
        rec["pivot_goal_pct"] = (
            round(100.0 * rec["pivot_goals"] / rec["pivot_attacks"], 1)
            if rec["pivot_attacks"] else None)
        rec["other_goal_pct"] = (
            round(100.0 * rec["other_goals"] / other, 1)
            if other > 0 else None)
    return out


# Passz-lánc vödrök: hány passzból épül a támadás (gyors befejezés /
# rövid játék / türelmes körbejáratás).
PASS_BUCKETS = ((2, "0–2 passz"), (5, "3–5 passz"))
PASS_LONG_LABEL = "6+ passz"


def pass_chains(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """Passz-lánc: támadásonként hány passz előzi meg a befejezést, és
    melyik lánc-hossz hozza a gólokat — megéri-e a türelmes
    körbejáratás, vagy a gyors befejezés a fegyverük.

    A passzokat a detect_passes adja (csapaton belüli birtokos-váltás),
    a gól-párosítás a támadás + ATTACK_TAIL_S alatti első saját gól.

    Visszatérés csapatonként:
      {"attacks", "passes", "avg_passes", "buckets":
       {vödör: {"attacks", "goals", "goal_pct"}}, "best_bucket"}
    — avg_passes None, ha nincs támadás; best_bucket a legjobb
    gólarányú vödör (2+ támadástól).
    """
    from .decisions import detect_passes
    from .event_detection import EventType, detect_shots
    from .setplays import segment_attacks

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    tail = round(ATTACK_TAIL_S * fps)
    passes = [(p.t, p.team.value) for p in detect_passes(match, config)]
    shots = [(e.t, e.team.value, e.type == EventType.GOAL)
             for e in detect_shots(match, config)
             if e.type in (EventType.SHOT, EventType.GOAL)]

    out = {side: {"attacks": 0, "passes": 0, "buckets": {},
                  "avg_passes": None, "best_bucket": None}
           for side in ("home", "away")}
    for seq in segment_attacks(match, config):
        side = seq.team.value
        n_pass = sum(1 for (t, tm) in passes
                     if tm == side and seq.start_t <= t <= seq.end_t)
        bucket = next((lab for lim, lab in PASS_BUCKETS
                       if n_pass <= lim), PASS_LONG_LABEL)
        goal = next((True for (t, tm, g) in shots
                     if tm == side and g
                     and seq.start_t <= t <= seq.end_t + tail), False)
        rec = out[side]
        rec["attacks"] += 1
        rec["passes"] += n_pass
        b = rec["buckets"].setdefault(bucket,
                                      {"attacks": 0, "goals": 0})
        b["attacks"] += 1
        if goal:
            b["goals"] += 1
    for rec in out.values():
        if rec["attacks"]:
            rec["avg_passes"] = round(rec["passes"] / rec["attacks"], 1)
        best = None
        for lab, b in rec["buckets"].items():
            b["goal_pct"] = round(100.0 * b["goals"] / b["attacks"], 1)
            if b["attacks"] >= 2 and (best is None
                                      or b["goal_pct"] > best[1]):
                best = (lab, b["goal_pct"])
        if best is not None and best[1] > 0:
            rec["best_bucket"] = best[0]
    return out


# Átmenet-támadás: a labdaszerzés után ennyi mp-en belül esett gólt
# számítjuk a szerzésből fakadó gyors gólnak.
TRANSITION_GOAL_WINDOW_S = 10.0


def transition_offense(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Átmenet-támadás: a labdaszerzésből mennyi gyors gól születik.

    A ball_winners szerzés-pillanataihoz (ts) párosítjuk az adott
    csapat TRANSITION_GOAL_WINDOW_S-en belüli első gólját — így látszik,
    mennyire fordítják a labdaszerzést azonnali gólra (a kontra-játék
    hatékonysága a szerző oldalról).

    Visszatérés csapatonként:
      {"steals", "quick_goals", "conv_pct", "avg_s"} — conv_pct a
    gólra váltott szerzések aránya; avg_s a szerzéstől a gólig eltelt
    átlagidő (None, ha nincs gyors gól).
    """
    from .defense import ball_winners
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = round(TRANSITION_GOAL_WINDOW_S * fps)
    goals = [(e.t, e.team.value)
             for e in detect_shots(match, config)
             if e.type == EventType.GOAL]
    bw = ball_winners(match, config)

    out = {}
    for side in ("home", "away"):
        steals = bw[side]["ts"]
        quick = 0
        sum_s = 0.0
        for st in steals:
            t0 = st["t"]
            gt = next((t for (t, tm) in goals
                       if tm == side and t0 < t <= t0 + win), None)
            if gt is not None:
                quick += 1
                sum_s += (gt - t0) / fps
        n = len(steals)
        out[side] = {
            "steals": n,
            "quick_goals": quick,
            "conv_pct": round(100.0 * quick / n, 1) if n else None,
            "avg_s": round(sum_s / quick, 1) if quick else None,
        }
    return out


# Lövés-távolság sávok (a kapu közepétől mért méter). A kézilabdás
# alapmegosztás: közeli (beálló/szélső, a 6-os környéke), közép (tipikus
# beállásos lövés), távoli (átlövés, hátsó sor).
SHOT_RANGE_CLOSE_M = 7.0    # eddig: "közeli"
SHOT_RANGE_MID_M = 9.5      # eddig: "közép"; efölött "távoli"


def shot_ranges(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """Lövés-távolság profil: honnan lő és honnan szerez gólt a csapat.

    Minden lövést a lövő (vagy a labda) kapu-középtől mért távolsága alapján
    három sávba sorol — "close" (<= SHOT_RANGE_CLOSE_M m), "mid"
    (<= SHOT_RANGE_MID_M m), "far" (efölött) — és sávonként számolja a
    lövéseket, gólokat és a gólarányt. A match_xg lövés-listáját használja
    újra (ott már megvan minden lövés helye és kimenetele).

    Visszatérés csapatonként:
      {"close"/"mid"/"far": {"shots", "goals", "goal_pct"},
       "total_shots", "dominant"} — dominant a legtöbb lövést adó sáv
    (None, ha nincs lövés). goal_pct None üres sávnál.
    """
    import math

    from ..models.tracking import Team
    from .calibration import COURT_WIDTH_M
    from .xg import match_xg

    config = config or TacticsConfig()
    goal_cy = COURT_WIDTH_M / 2.0
    xg = match_xg(match, config)

    def _band(x: float, y: float, team: str) -> str:
        goal_x = config.attacks_toward_x(
            Team.HOME if team == "home" else Team.AWAY)
        dist = math.hypot(x - goal_x, y - goal_cy)
        if dist <= SHOT_RANGE_CLOSE_M:
            return "close"
        if dist <= SHOT_RANGE_MID_M:
            return "mid"
        return "far"

    out: dict = {}
    for side in ("home", "away"):
        bands = {b: {"shots": 0, "goals": 0} for b in ("close", "mid", "far")}
        for sh in xg["shots"]:
            if sh["team"] != side:
                continue
            b = _band(sh["x"], sh["y"], side)
            bands[b]["shots"] += 1
            if sh["outcome"] == "goal":
                bands[b]["goals"] += 1
        total = sum(bands[b]["shots"] for b in bands)
        for b in bands:
            n = bands[b]["shots"]
            bands[b]["goal_pct"] = (round(100.0 * bands[b]["goals"] / n, 1)
                                    if n else None)
        dominant = max(("close", "mid", "far"),
                       key=lambda b: bands[b]["shots"]) if total else None
        # Ha nincs lövés, a "dominant" ne egy 0-s sávot nevezzen meg.
        if dominant is not None and bands[dominant]["shots"] == 0:
            dominant = None
        out[side] = {**bands, "total_shots": total, "dominant": dominant}
    return out


# Egy oldal "dominánssá" nyilvánításához ennyi gól kell — kevesebből a
# kapuoldal-eloszlás zajos.
PLACEMENT_MIN_GOALS = 4


def goal_placement(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """Kapu-sarok: a gólok a kapu MELYIK oldalára mennek (bal/közép/jobb),
    a lövő szemszögéből.

    Minden gólnál megkeressük, hol lépi át a labda a gólvonalat (y a kapu
    száján belül), és a kaput három függőleges harmadra osztva soroljuk be
    — a lövő nézőpontjához igazítva (a két kapu tükrözve). Ebből látszik a
    csapat befejezés-szokása: ha kiszámítható (egy oldalra megy a gólok
    zöme), a kapus felkészülhet rá, a támadó pedig változatosságot gyakorol.

    Visszatérés csapatonként:
      {"bal", "közép", "jobb", "goals", "dominant"} — a három oldal
    gólszáma, goals az összes bekönyvelt gól, dominant a legtöbbet kapó
    oldal (elég góllal: PLACEMENT_MIN_GOALS), None, ha nincs ilyen.
    """
    from ..models.tracking import Team
    from .calibration import COURT_LENGTH_M
    from .event_detection import (GOAL_LOOKAHEAD, GOAL_TOL_M, EventType,
                                  _GOAL_Y_HIGH, _GOAL_Y_LOW, detect_shots)

    config = config or TacticsConfig()
    lo, hi = _GOAL_Y_LOW, _GOAL_Y_HIGH
    span = (hi - lo) or 1.0
    idx_of = {f.t: i for i, f in enumerate(match.frames)}

    def _side_of_goal(e) -> Optional[str]:
        goal_x = config.attacks_toward_x(e.team)
        i0 = idx_of.get(e.t)
        if i0 is None:
            return None
        end = min(len(match.frames), i0 + GOAL_LOOKAHEAD)
        for j in range(i0, end):
            b = match.frames[j].ball
            if b is None:
                continue
            if abs(b.x - goal_x) <= GOAL_TOL_M and lo <= b.y <= hi:
                rel = (b.y - lo) / span  # 0 = alsó y, 1 = felső y
                # A lövő szemszögéből a "bal" a +x kapunál a felső y, a 0-s
                # kapunál az alsó y — a két kaput tükrözzük.
                leftness = rel if goal_x >= COURT_LENGTH_M / 2 else 1.0 - rel
                if leftness >= 2.0 / 3.0:
                    return "bal"
                if leftness <= 1.0 / 3.0:
                    return "jobb"
                return "közép"
        return None

    tally = {s: {"bal": 0, "közép": 0, "jobb": 0} for s in ("home", "away")}
    for e in detect_shots(match, config):
        if e.type != EventType.GOAL:
            continue
        side = _side_of_goal(e)
        if side is not None:
            tally[e.team.value][side] += 1

    out: dict = {}
    for s in ("home", "away"):
        t = tally[s]
        total = t["bal"] + t["közép"] + t["jobb"]
        dom = (max(("bal", "közép", "jobb"), key=lambda k: t[k])
               if total >= PLACEMENT_MIN_GOALS else None)
        if dom is not None and t[dom] == 0:
            dom = None
        out[s] = {**t, "goals": total, "dominant": dom}
    return out


# Szélső-lövés: a kapu-középtől oldalra legalább ennyivel (éles szög) ÉS a
# kaputól legfeljebb ennyire (a szélső a 6-os környékéről fejez be).
WING_LATERAL_M = 6.0
WING_MAX_DIST_M = 9.0


def wing_finishing(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """Szélső-befejezés: a szélső (éles) szögből, közelről leadott lövések
    és góljaik hatékonysága.

    A szélső poszt a legélesebb szögből fejez be: a kapu-középtől oldalra
    legalább WING_LATERAL_M-re és a kaputól legfeljebb WING_MAX_DIST_M-re
    leadott lövéseket számoljuk (a lövő helyéből, a match_xg-ből). Erős
    szélső-játék széthúzza a védelmet; gyenge szélső-befejezésnél a védő
    ráengedheti a szöget.

    Visszatérés csapatonként: {"shots", "goals", "goal_pct"} — goal_pct
    None, ha nem volt szélső-lövés.
    """
    import math

    from ..models.tracking import Team
    from .calibration import COURT_WIDTH_M
    from .xg import match_xg

    config = config or TacticsConfig()
    cy = COURT_WIDTH_M / 2.0
    xg = match_xg(match, config)

    out: dict = {}
    for side in ("home", "away"):
        goal_x = config.attacks_toward_x(
            Team.HOME if side == "home" else Team.AWAY)
        shots = goals = 0
        for sh in xg["shots"]:
            if sh["team"] != side:
                continue
            dist = math.hypot(sh["x"] - goal_x, sh["y"] - cy)
            if abs(sh["y"] - cy) >= WING_LATERAL_M and dist <= WING_MAX_DIST_M:
                shots += 1
                if sh["outcome"] == "goal":
                    goals += 1
        out[side] = {
            "shots": shots,
            "goals": goals,
            "goal_pct": round(100.0 * goals / shots, 1) if shots else None,
        }
    return out


# Egy passz akkor "előre" (vagy "hátra"), ha a labda ennyivel közelebb
# (vagy távolabb) kerül a támadott kapuhoz; a köztes az "oldal" (square).
PASS_FORWARD_MIN_M = 2.0


def pass_direction(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """Passz-irány: mennyire viszik ELŐRE a labdát (vertikális, penetráló
    játék) vagy oldalra/hátra (türelmes körözés).

    Minden passznál a passzoló és a fogadó kapu-távolságából számoljuk az
    előrehaladást (a támadott kapu felé). Sok előre-passz gyors, vertikális
    játékot jelez (korán vissza kell zárni); sok oldal-passz türelmes
    körbejáratást (a beállóra/elzárásokra kell figyelni).

    Visszatérés csapatonként:
      {"passes", "forward", "square", "back", "forward_pct",
       "avg_progress_m"} — forward_pct az előre-passzok aránya, avg_progress_m
    az átlagos előrehaladás méterben (negatív = inkább hátra jár a labda).
    None a százalék/átlag, ha nincs mérhető passz.
    """
    from .event_detection import EventType, detect_possession_changes

    config = config or TacticsConfig()
    by_t = {f.t: f for f in match.frames}
    tally = {s: {"forward": 0, "square": 0, "back": 0, "prog": 0.0, "n": 0}
             for s in ("home", "away")}

    for e in detect_possession_changes(match, config):
        if e.type != EventType.PASS:
            continue
        rid = (e.detail or {}).get("receiver_id")
        if rid is None:
            continue
        f = by_t.get(e.t)
        if f is None:
            continue
        px = rx = None
        for p in f.players:
            if p.track_id == e.player_id:
                px = p.x
            elif p.track_id == rid:
                rx = p.x
        if px is None or rx is None:
            continue
        goal_x = config.attacks_toward_x(e.team)
        prog = abs(px - goal_x) - abs(rx - goal_x)  # > 0 = előre
        rec = tally[e.team.value]
        rec["n"] += 1
        rec["prog"] += prog
        if prog >= PASS_FORWARD_MIN_M:
            rec["forward"] += 1
        elif prog <= -PASS_FORWARD_MIN_M:
            rec["back"] += 1
        else:
            rec["square"] += 1

    out: dict = {}
    for s in ("home", "away"):
        t = tally[s]
        n = t["n"]
        out[s] = {
            "passes": n,
            "forward": t["forward"],
            "square": t["square"],
            "back": t["back"],
            "forward_pct": round(100.0 * t["forward"] / n, 1) if n else None,
            "avg_progress_m": round(t["prog"] / n, 2) if n else None,
        }
    return out


# Gólpassz-forrás zóna-küszöbök: oldalra ennyivel a kapu-középtől = szél;
# a kaputól ennyivel + középen = hátsó (átlövő); egyébként közép (beálló/
# betörés-kiadás). Egy domináns forráshoz ennyi gólpassz kell.
ASSIST_WING_LATERAL_M = 6.0
ASSIST_BACK_DIST_M = 9.0
ASSIST_SOURCE_MIN = 3


def assist_sources(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """Gólpassz-forrás: honnan készítik elő a gólokat — szélről (beadás),
    a hátsó sorból (átlövő-kiadás) vagy középről (beálló/betörés-kiadás).

    Minden gólpasszos gólnál a passzoló helyét vesszük a passz pillanatában,
    és a kapu-középtől mért oldal-, illetve kapu-távolsága alapján zónába
    soroljuk. Ebből látszik a csapat GÓL-ELŐKÉSZÍTÉSI mintája (más, mint az
    assziszt-háló, ami a ki-kinek kérdést nézi).

    Visszatérés csapatonként:
      {"szél", "közép", "hátsó", "assists", "dominant"} — a három forrás
    gólpassz-száma, assists az összes bekönyvelt gólpassz, dominant a
    legtöbbet adó forrás (elég adattal: ASSIST_SOURCE_MIN), None egyébként.
    """
    import math

    from .calibration import COURT_WIDTH_M
    from .event_detection import (ASSIST_WINDOW_S, EventType, detect_events)

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = ASSIST_WINDOW_S * fps
    cy = COURT_WIDTH_M / 2.0
    by_t = {f.t: f for f in match.frames}
    events = detect_events(match, config)
    passes = [e for e in events if e.type == EventType.PASS]

    tally = {s: {"szél": 0, "közép": 0, "hátsó": 0} for s in ("home", "away")}
    for g in events:
        if g.type != EventType.GOAL or g.player_id is None:
            continue
        aid = (g.detail or {}).get("assist_id")
        if aid is None:
            continue
        # A gólpassz megkeresése (az utolsó illő passz a gól előtt).
        best = None
        for p in passes:
            if not (0 <= g.t - p.t <= win) or p.team != g.team:
                continue
            if p.player_id != aid:
                continue
            if (p.detail or {}).get("receiver_id") != g.player_id:
                continue
            if best is None or p.t > best.t:
                best = p
        if best is None:
            continue
        f = by_t.get(best.t)
        if f is None:
            continue
        pos = next((pp for pp in f.players if pp.track_id == aid), None)
        if pos is None:
            continue
        goal_x = config.attacks_toward_x(g.team)
        dist = math.hypot(pos.x - goal_x, pos.y - cy)
        if abs(pos.y - cy) >= ASSIST_WING_LATERAL_M:
            zone = "szél"
        elif dist >= ASSIST_BACK_DIST_M:
            zone = "hátsó"
        else:
            zone = "közép"
        tally[g.team.value][zone] += 1

    out: dict = {}
    for s in ("home", "away"):
        t = tally[s]
        total = t["szél"] + t["közép"] + t["hátsó"]
        dom = (max(("szél", "közép", "hátsó"), key=lambda k: t[k])
               if total >= ASSIST_SOURCE_MIN else None)
        if dom is not None and t[dom] == 0:
            dom = None
        out[s] = {**t, "assists": total, "dominant": dom}
    return out


# Második roham: a saját, gólt NEM érő lövés után ekkora időn belül leadott
# ÚJABB saját lövés számít lepattanó-visszaszerzésnek (offenzív lepattanó →
# második esély). Ennyi mért kimaradás kell az edzői ítélethez.
SECOND_CHANCE_WINDOW_S = 6.0
SECOND_CHANCE_MIN = 3


def second_chance(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """Második roham / lepattanó-visszaszerzés: a saját, gólt NEM érő lövés
    (védés vagy mellé) után a támadó visszaszerzi-e a labdát és újra lő-e —
    mielőtt az ellenfél lőne.

    A lövés-eseményekből (detect_shots) dolgozunk: minden nem gólos lövés egy
    lepattanó-LEHETŐSÉG. Ha ugyanaz a csapat SECOND_CHANCE_WINDOW_S-en belül
    úgy lő újra, hogy közben az ellenfél nem lőtt, azt megnyert második
    rohamnak vesszük; ha a folytatás gól, második esélyből szerzett gól. Ez a
    csapat "harc a lepattanóért" agresszivitását és a második esélyek
    kihasználását méri — záráskor a felállt védelem ellen a lepattanó dönt.

    Visszatérés csapatonként:
      {"misses", "second_chances", "second_goals", "rebound_pct",
       "convert_pct"} — misses a lepattanó-lehetőségek (nem gólos lövések),
    second_chances a megnyert második rohamok, second_goals ezekből a gólok,
    rebound_pct a visszaszerzési arány (%), convert_pct a második esélyek
    gólaránya (%). A százalékok None, ha nincs elég adat.
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = SECOND_CHANCE_WINDOW_S * fps
    shots = [e for e in detect_shots(match, config)
             if e.type in (EventType.SHOT, EventType.GOAL)]

    tally = {s: {"misses": 0, "second_chances": 0, "second_goals": 0}
             for s in ("home", "away")}
    for i, e in enumerate(shots):
        if e.type == EventType.GOAL:
            continue  # gól: a támadás lezárult, nincs lepattanó
        side = e.team.value
        tally[side]["misses"] += 1
        # A következő lövés az ablakon belül: ha a SAJÁT csapaté (és közben az
        # ellenfél nem lőtt), az a megnyert lepattanó.
        for nxt in shots[i + 1:]:
            if nxt.t - e.t > win:
                break
            if nxt.team != e.team:
                break  # az ellenfél lőtt előbb — elveszett a lepattanó
            tally[side]["second_chances"] += 1
            if nxt.type == EventType.GOAL:
                tally[side]["second_goals"] += 1
            break

    def _pct(n, d):
        return round(100.0 * n / d, 1) if d > 0 else None

    out: dict = {}
    for s in ("home", "away"):
        t = tally[s]
        out[s] = {
            **t,
            "rebound_pct": (_pct(t["second_chances"], t["misses"])
                            if t["misses"] >= SECOND_CHANCE_MIN else None),
            "convert_pct": _pct(t["second_goals"], t["second_chances"]),
        }
    return out


# Lövés-időzítés: legalább ennyi lőtt támadás kell az ítélethez; ennyi mp-en
# belüli lövés "korai" (első hullám), és ekkora korai-arány jelent első-
# hullám lövő csapatot; a kivárókat a magas átlagidő jelzi.
SHTIM_MIN_SHOTS = 5
SHTIM_EARLY_S = 8.0
SHTIM_EARLY_PCT = 45.0
SHTIM_LATE_AVG_S = 22.0


def shot_timing(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """Lövés-időzítés: MIKOR lőnek a támadáson belül — első hullámban
    (korai) vagy kivárva.

    Minden lövéssel záruló támadás-szakasznál a szakasz kezdete és a lövés
    közti időt mérjük. A korai lövők (SHTIM_EARLY_PCT%+ lövés az első
    SHTIM_EARLY_S mp-ben) az első hullámból élnek — a visszarendeződés és
    az első-hullám védekezés kritikus ellenük; a kivárók (magas átlagidő)
    a felállt fal hibájára és a passzív-jel előtti utolsó pillanatra
    játszanak. Más, mint a támadás-hossz (az a teljes szakaszt méri,
    lövés nélkül is).

    Visszatérés csapatonként:
      {"shots", "avg_s", "early", "early_pct"} — a mért (lövéssel záruló)
    támadások száma, az átlagos lövésig-idő, a korai lövések száma és
    aránya; avg_s/early_pct None, ha shots < SHTIM_MIN_SHOTS.
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    tail = round(ATTACK_TAIL_S * fps)
    segs = segment_attacks(match, config)
    shots = [e for e in detect_shots(match, config)
             if e.type in (EventType.SHOT, EventType.GOAL)]
    acc = {"home": [0, 0.0, 0], "away": [0, 0.0, 0]}  # n, összeg, korai
    for e in shots:
        # A lövés a szakaszon belül vagy közvetlenül utána (rátoldás)
        # csapódik le — mint az attack_efficiency párosításánál.
        seg = next((s_ for s_ in segs
                    if s_.team == e.team
                    and s_.start_t <= e.t <= s_.end_t + tail),
                   None)
        if seg is None:
            continue
        dt = (e.t - seg.start_t) / fps
        rec = acc[e.team.value]
        rec[0] += 1
        rec[1] += dt
        if dt <= SHTIM_EARLY_S:
            rec[2] += 1

    out: dict = {}
    for s in ("home", "away"):
        n, total, early = acc[s]
        ok = n >= SHTIM_MIN_SHOTS
        out[s] = {
            "shots": n,
            "avg_s": round(total / n, 1) if ok else None,
            "early": early,
            "early_pct": round(100.0 * early / n, 1) if ok else None,
        }
    return out
