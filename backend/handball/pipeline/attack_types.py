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
from .primitive_cache import copy_rows, memoize_primitive

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


@memoize_primitive("classify_attacks", copy=copy_rows)
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


# Tempó-esés: ennyi mért perc kell félidőnként, és ekkora támadás/perc
# esés számít érdeminek (a láb fáradása — kevesebb támadást futnak).
PACE_FADE_MIN_HALF_MIN = 8.0
PACE_FADE_DROP_PER_MIN = 0.2


def team_pace_fade(match: Match,
                   config: Optional[TacticsConfig] = None) -> dict:
    """Tempó-esés: a csapat támadás/perc mutatója az 1. vs 2. félidőben.

    A fáradás-kép "láb" tagja: akinek a 2. félidőre érdemben esik a
    támadás-üteme, az már nem bírja futni a meccset — ellene a 2.
    félidőben tempót KELL emelni; akinek nő, az a hajrára kapcsol.

    Visszatérés csapatonként: {"fh_attacks", "fh_min", "sh_attacks",
    "sh_min", "drop_per_min"} — drop_per_min a támadás/perc esése
    (pozitív = lassul), None félidő-jel vagy kevés játékperc
    (félidőnként PACE_FADE_MIN_HALF_MIN) esetén.
    """
    from .halftime import detect_halftime

    config = config or TacticsConfig()
    empty = {"fh_attacks": 0, "fh_min": 0.0, "sh_attacks": 0,
             "sh_min": 0.0, "drop_per_min": None}
    out = {"home": dict(empty), "away": dict(empty)}
    ht = detect_halftime(match)
    if ht is None or not match.frames:
        return out
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    fh_min = ht / fps / 60.0
    sh_min = (match.frames[-1].t - ht) / fps / 60.0
    seqs = list(segment_attacks(match, config))
    for side in ("home", "away"):
        rec = out[side]
        own = [s for s in seqs if s.team.value == side]
        rec["fh_attacks"] = sum(1 for s in own if s.start_t <= ht)
        rec["sh_attacks"] = len(own) - rec["fh_attacks"]
        rec["fh_min"] = round(fh_min, 1)
        rec["sh_min"] = round(sh_min, 1)
        if fh_min >= PACE_FADE_MIN_HALF_MIN \
                and sh_min >= PACE_FADE_MIN_HALF_MIN:
            rec["drop_per_min"] = round(
                rec["fh_attacks"] / fh_min - rec["sh_attacks"] / sh_min, 2)
    return out


# Ritmus-egyhangúság: ennyi támadástól ítélünk, és e relatív szórás
# (szórás/átlag) alatt számít kiszámíthatónak a támadás-hossz.
RHYTHM_MIN_ATTACKS = 10
RHYTHM_CV_LOW = 0.35


def attack_rhythm(match: Match,
                  config: Optional[TacticsConfig] = None) -> dict:
    """Ritmus-egyhangúság: mennyire egyforma hosszúak a támadások.

    A kiszámíthatóság idő-olvasata: akinek minden támadása nagyjából
    ugyanannyi ideig tart, annak belső órája van — a védekezés ráállhat
    az órára: az átlagidő előtt pár másodperccel időzített
    letámadás/kettőzés rendre a lövés-előkészítést töri meg. A
    változatos ritmusú csapat ellen órára játszani nem lehet.

    Visszatérés csapatonként: {"n", "sum_s", "sumsq_s", "avg_s",
    "sd_s", "cv"} — az összeg-mezők meccsek közt összegezhetők (az
    átlag/szórás belőlük visszaszámolható); avg_s/sd_s/cv None, ha
    kevés (RHYTHM_MIN_ATTACKS alatti) a támadás.
    """
    import math

    from .setplays import segment_attacks

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    durs = {"home": [], "away": []}
    for seq in segment_attacks(match, config):
        durs[seq.team.value].append((seq.end_t - seq.start_t) / fps)
    out = {}
    for side in ("home", "away"):
        d = durs[side]
        rec = {"n": len(d), "sum_s": round(sum(d), 1),
               "sumsq_s": round(sum(x * x for x in d), 1),
               "avg_s": None, "sd_s": None, "cv": None}
        if len(d) >= RHYTHM_MIN_ATTACKS:
            avg = sum(d) / len(d)
            var = max(0.0, sum(x * x for x in d) / len(d) - avg * avg)
            rec["avg_s"] = round(avg, 1)
            rec["sd_s"] = round(math.sqrt(var), 1)
            rec["cv"] = round(math.sqrt(var) / avg, 2) if avg > 0 else None
        out[side] = rec
    return out


# Oldal-részrehajlás: a szélső-sáv határa a pálya-középvonaltól (m),
# ennyi szélső-sávos lövéstől ítélünk, és ekkora többség számít
# részrehajlásnak.
SIDE_BAND_M = 3.33
SIDE_BIAS_MIN_SHOTS = 8
SIDE_BIAS_PCT = 65.0


def attack_side_bias(match: Match,
                     config: Optional[TacticsConfig] = None) -> dict:
    """Oldal-részrehajlás: a lövések a támadás melyik oldaláról jönnek.

    A kiszámíthatóság térbeli olvasata: akinek a szélső-sávos lövései
    kétharmadban egy oldalról jönnek, annak a támadása fél-oldalas — a
    fal eltolható, a segítő védő előre tudja, honnan jön a lövés. A
    "bal" a TÁMADÓ bal keze felőli oldal (a támadás iránya szerint),
    így a két csapat összevethető.

    Visszatérés csapatonként: {"left", "center", "right", "bias_side",
    "bias_pct"} — bias_side/"bias_pct" None, ha kevés (a két szélső
    sávban együtt SIDE_BIAS_MIN_SHOTS alatti) a lövés, vagy nincs
    érdemi (SIDE_BIAS_PCT alatti) többség.
    """
    from ..models.tracking import Team
    from .xg import match_xg

    config = config or TacticsConfig()
    counts = {"home": {"left": 0, "center": 0, "right": 0},
              "away": {"left": 0, "center": 0, "right": 0}}
    for sh in match_xg(match, config).get("shots", []):
        side = sh["team"]
        d = sh["y"] - 10.0
        team = Team.HOME if side == "home" else Team.AWAY
        if config.attacks_toward_x(team) == 0.0:
            d = -d  # a -x felé támadónál a bal kéz a -y oldal
        if d > SIDE_BAND_M:
            counts[side]["left"] += 1
        elif d < -SIDE_BAND_M:
            counts[side]["right"] += 1
        else:
            counts[side]["center"] += 1
    out = {}
    for side in ("home", "away"):
        rec = dict(counts[side])
        rec["bias_side"] = rec["bias_pct"] = None
        wings = rec["left"] + rec["right"]
        if wings >= SIDE_BIAS_MIN_SHOTS:
            pct = 100.0 * max(rec["left"], rec["right"]) / wings
            if pct >= SIDE_BIAS_PCT:
                rec["bias_side"] = ("bal" if rec["left"] >= rec["right"]
                                    else "jobb")
                rec["bias_pct"] = round(pct, 1)
        out[side] = rec
    return out


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


# Passz-irány-állás: a passz-irányok az eredményjelző szerint.
PDS_MIN_PASSES = 10   # az összevetett állapotokban ennyi-ennyi passz kell
PDS_GAP_PP = 12.0     # ekkora részarány-többlet számít mintázatnak


def pass_direction_by_score(match: Match,
                            config: Optional[TacticsConfig] = None) -> dict:
    """Passz-irány-állás: MERRE jár a labda előnyben és hátrányban.

    A passz-irány (pass_direction) a meccs egészét nézi — ez az
    eredményjelzőn: minden passznál a passzoló csapat pillanatnyi
    gólkülönbségét vesszük, és állásonként mérjük az előre-, illetve
    hátra-passzok részarányát. Az előnyben megugró hátrajáratás a
    tudatos időölés (és egyben letámadható minta); a hátrányban
    erőltetett előre-passz a kapkodás — elfogható labdákkal.

    Edzőileg: aki előnyben hátrafelé járat, arra vezetésénél magas
    letámadással kell rámenni — az első hátrapassz a jel; aki
    hátrányban előre erőltet, annál ilyenkor a passzsávokra ültetett
    védő termel. A saját oldalon a vezetés-játék tudatosítása a téma.

    Visszatérés csapatonként: {"leading"/"trailing"/"level":
    {"passes", "forward", "back"}, "verdict"} — a verdict "előnyben
    hátrafelé járatják a labdát" / "hátrányban erőltetik az
    előre-passzt" / None (állapotonként PDS_MIN_PASSES-nél kevesebb
    passznál).
    """
    from .event_detection import (EventType, detect_possession_changes,
                                  detect_shots)

    config = config or TacticsConfig()
    goals = [(e.t, e.team.value) for e in detect_shots(match, config)
             if e.type == EventType.GOAL]
    by_t = {f.t: f for f in match.frames}
    out = {side: {k: {"passes": 0, "forward": 0, "back": 0}
                  for k in ("leading", "trailing", "level")}
           for side in ("home", "away")}
    for e in detect_possession_changes(match, config):
        if e.type != EventType.PASS:
            continue
        rid = (e.detail or {}).get("receiver_id")
        f = by_t.get(e.t)
        if rid is None or f is None:
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
        side = e.team.value
        own = sum(1 for (t, tm) in goals if t < e.t and tm == side)
        opp = sum(1 for (t, tm) in goals if t < e.t and tm != side)
        state = ("leading" if own > opp
                 else "trailing" if own < opp else "level")
        rec = out[side][state]
        rec["passes"] += 1
        if prog >= PASS_FORWARD_MIN_M:
            rec["forward"] += 1
        elif prog <= -PASS_FORWARD_MIN_M:
            rec["back"] += 1

    for side in ("home", "away"):
        buckets = out[side]
        verdict = None
        lead = buckets["leading"]
        tr = buckets["trailing"]
        rest_ld = {k: tr[k] + buckets["level"][k]
                   for k in ("passes", "back")}
        if lead["passes"] >= PDS_MIN_PASSES \
                and rest_ld["passes"] >= PDS_MIN_PASSES:
            diff = (100.0 * lead["back"] / lead["passes"]
                    - 100.0 * rest_ld["back"] / rest_ld["passes"])
            if diff >= PDS_GAP_PP:
                verdict = "előnyben hátrafelé járatják a labdát"
        rest_tr = {k: lead[k] + buckets["level"][k]
                   for k in ("passes", "forward")}
        if verdict is None and tr["passes"] >= PDS_MIN_PASSES \
                and rest_tr["passes"] >= PDS_MIN_PASSES:
            diff = (100.0 * tr["forward"] / tr["passes"]
                    - 100.0 * rest_tr["forward"] / rest_tr["passes"])
            if diff >= PDS_GAP_PP:
                verdict = "hátrányban erőltetik az előre-passzt"
        buckets["verdict"] = verdict
    return out


# Szünet-váltás: a támadás-mix átrendeződése a két félidő között.
AMS_MIN_ATTACKS_HALF = 6   # félidőnként ennyi támadás kell az ítélethez
AMS_SHIFT_PP = 30.0        # ekkora össz-átrendeződés = tudatos váltás
AMS_STATIC_PP = 10.0       # ez alatt: félidőn át ugyanaz a játék


def attack_mix_shift(match: Match,
                     config: Optional[TacticsConfig] = None) -> dict:
    """Szünet-váltás: ÁTRENDEZIK-E a támadójátékot a szünet után.

    A támadás-mix (attack_mix) a meccs egészét nézi — ez a két
    félidőt külön: a támadás-típusok részarányát hasonlítjuk össze, és
    az össz-átrendeződést mérjük (a részarány-eltolódások összege
    /2, százalékpontban). A nagy váltás jól vezetett, alkalmazkodó
    csapat jele: az első félidei képe NEM a második félidei igazsága.
    A mozdulatlan mix a kiszámíthatóé: egy védő-terv kitart 60 percen
    át.

    Edzőileg: az átrendező csapat ellen a szünetben nem a folytatásra,
    hanem a VÁLTÁSRA kell készülni (mit hoznak, ha ez nem megy); a
    mozdulatlan ellen elég egy terv, és azt lehet egész meccsen
    csiszolni. A saját oldalon a B-terv hiánya edzés-téma.

    Visszatérés csapatonként: {"fh_attacks", "sh_attacks", "fh_mix",
    "sh_mix", "shift_pp", "verdict"} — a fh_mix/sh_mix típusonkénti
    darabszám; shift_pp/verdict None felismert szünet nélkül vagy
    félidőnként AMS_MIN_ATTACKS_HALF-nál kevesebb támadásnál; a
    verdict "a szünet után átrendezik a támadójátékukat" / "félidőn
    át ugyanazt játsszák" / None.
    """
    from .halftime import detect_halftime

    config = config or TacticsConfig()
    out = {side: {"fh_attacks": 0, "sh_attacks": 0,
                  "fh_mix": {}, "sh_mix": {}, "shift_pp": None,
                  "verdict": None} for side in ("home", "away")}
    ht = detect_halftime(match)
    if ht is None:
        return out
    mixes = {side: {"fh": out[side]["fh_mix"],
                    "sh": out[side]["sh_mix"]}
             for side in ("home", "away")}
    for a in classify_attacks(match, config):
        half = "fh" if a["start_frame"] <= ht else "sh"
        rec = mixes[a["team"]][half]
        rec[a["type"]] = rec.get(a["type"], 0) + 1
        out[a["team"]][half + "_attacks"] += 1
    for side in ("home", "away"):
        rec = out[side]
        if rec["fh_attacks"] < AMS_MIN_ATTACKS_HALF \
                or rec["sh_attacks"] < AMS_MIN_ATTACKS_HALF:
            continue
        fh, sh = mixes[side]["fh"], mixes[side]["sh"]
        types = set(fh) | set(sh)
        shift = sum(abs(100.0 * fh.get(tp, 0) / rec["fh_attacks"]
                        - 100.0 * sh.get(tp, 0) / rec["sh_attacks"])
                    for tp in types) / 2.0
        rec["shift_pp"] = round(shift, 1)
        if shift >= AMS_SHIFT_PP:
            rec["verdict"] = "a szünet után átrendezik a támadójátékukat"
        elif shift <= AMS_STATIC_PP:
            rec["verdict"] = "félidőn át ugyanazt játsszák"
    return out


# Lepattanó-esés: a megnyert második rohamok részaránya félidőnként.
SCF_MIN_MISSES = 3   # félidőnként ennyi lepattanó-lehetőség kell
SCF_DROP_PP = 25.0   # ekkora részarány-változás számít mintázatnak


def second_chance_fade(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Lepattanó-esés: MELYIK FÉLIDŐBEN él a második roham.

    A fáradás-család lepattanó-tagja: a második roham (second_chance)
    a meccs egészére mondja meg, hányszor harcolja vissza a csapat a
    saját kimaradt lövését — ez félidőnként: a hajrára elfogyó
    lepattanó-harc tiszta fáradás-jel, mert a lepattanó a láb és az
    akarat játéka, nem a technikáé. A fordítottja (a hajrában
    erősödő) a mélyebb kispad vagy a tudatos zárás jele.

    Edzőileg: akinek a hajrára elfogy a lepattanó-harca, az ellen
    záráskor a blokk és a védés utáni labda rendre a tiétek — a
    kimaradt lövésük a támadásuk vége; a saját oldalon a fáradásos
    lepattanó-gyakorlat a téma.

    Visszatérés csapatonként: {"fh_misses", "fh_won", "sh_misses",
    "sh_won", "gap_pp", "verdict"} — gap_pp/verdict None felismert
    szünet nélkül vagy félidőnként SCF_MIN_MISSES-nél kevesebb
    lehetőségnél; a verdict "a hajrára elfogy a lepattanó-harcuk" /
    "a hajrában erősödik a lepattanó-harcuk" / None.
    """
    from .event_detection import EventType, detect_shots
    from .halftime import detect_halftime

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = SECOND_CHANCE_WINDOW_S * fps
    out = {side: {"fh_misses": 0, "fh_won": 0, "sh_misses": 0,
                  "sh_won": 0, "gap_pp": None, "verdict": None}
           for side in ("home", "away")}
    ht = detect_halftime(match)
    if ht is None:
        return out
    shots = [e for e in detect_shots(match, config)
             if e.type in (EventType.SHOT, EventType.GOAL)]
    for i, e in enumerate(shots):
        if e.type == EventType.GOAL:
            continue
        rec = out[e.team.value]
        first = e.t <= ht
        rec["fh_misses" if first else "sh_misses"] += 1
        for nxt in shots[i + 1:]:
            if nxt.t - e.t > win:
                break
            if nxt.team != e.team:
                break
            rec["fh_won" if first else "sh_won"] += 1
            break
    for rec in out.values():
        if rec["fh_misses"] < SCF_MIN_MISSES \
                or rec["sh_misses"] < SCF_MIN_MISSES:
            continue
        fh_pct = 100.0 * rec["fh_won"] / rec["fh_misses"]
        sh_pct = 100.0 * rec["sh_won"] / rec["sh_misses"]
        rec["gap_pp"] = round(sh_pct - fh_pct, 1)
        if rec["gap_pp"] <= -SCF_DROP_PP:
            rec["verdict"] = "a hajrára elfogy a lepattanó-harcuk"
        elif rec["gap_pp"] >= SCF_DROP_PP:
            rec["verdict"] = "a hajrában erősödik a lepattanó-harcuk"
    return out


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


# Asszist-függés: ennyi góltól ítélünk; e gólpasszos arány felett
# kollektív, ez alatt egyéni a befejezés-stílus.
ASSIST_DEP_MIN_GOALS = 6
ASSIST_DEP_HIGH_PCT = 70.0
ASSIST_DEP_LOW_PCT = 35.0


def assist_reliance(match: Match,
                    config: Optional[TacticsConfig] = None) -> dict:
    """Asszist-függés: a gólok mekkora része előkészített (gólpasszos).

    A gólpassz-forrás (assist_sources) a HONNAN kérdést nézi — itt a
    MENNYIRE a kérdés: a kollektív csapat góljai kiadásból születnek
    (ellene a passzsávok elvágása — aktív kéz, a beálló elé lépés —
    többet ér, mint az 1-1 elleni hősködés), az egyéni megoldásokból
    élő csapatnál viszont a kulcsember-párharc dönt (emberfogás, korai
    test). A védekezés-terv e stílus-tengely két végén másról szól.

    Visszatérés csapatonként: {"goals", "assisted", "assisted_pct",
    "style"} — assisted_pct/style None, ha kevés
    (ASSIST_DEP_MIN_GOALS alatti) a gól; style "kollektív" /
    "egyéni" / None (köztes).
    """
    from .event_detection import EventType, detect_events

    counts = {"home": {"goals": 0, "assisted": 0},
              "away": {"goals": 0, "assisted": 0}}
    for e in detect_events(match, config or TacticsConfig()):
        if e.type != EventType.GOAL:
            continue
        rec = counts[e.team.value]
        rec["goals"] += 1
        if (e.detail or {}).get("assist_id") is not None:
            rec["assisted"] += 1
    out: dict = {}
    for side in ("home", "away"):
        rec = counts[side]
        pct = None
        style = None
        if rec["goals"] >= ASSIST_DEP_MIN_GOALS:
            pct = round(100.0 * rec["assisted"] / rec["goals"], 1)
            if pct >= ASSIST_DEP_HIGH_PCT:
                style = "kollektív"
            elif pct <= ASSIST_DEP_LOW_PCT:
                style = "egyéni"
        out[side] = {**rec, "assisted_pct": pct, "style": style}
    return out


# Előkészítő-függés: ennyi gólpasszos góltól ítélünk; e részarány
# felett egy emberre épül az előkészítés.
ASSIST_CONC_MIN = 5
ASSIST_CONC_TOP_SHARE = 0.5


def assist_concentration(match: Match,
                         config: Optional[TacticsConfig] = None) -> dict:
    """Előkészítő-függés: mennyire egy emberre épül a gólpassz-termelés.

    A lövő-koncentráció (shot_concentration) előkészítő-oldali párja,
    és az asszist-függés (assist_reliance) folytatása: az mondja meg,
    MENNYIRE előkészítettek a gólok — ez azt, hogy KI készíti elő
    őket. Ha a gólpasszok fele ugyanattól a játékostól jön, a
    kulcs-előkészítő elvágása (előfogás, a passzsávjának zárása,
    korai kettőzés) az egész befejezést megbénítja; elosztott
    előkészítés ellen ilyen rövidítés nincs.

    Visszatérés csapatonként: {"assists", "top_assists",
    "top_player_id", "share", "concentrated"} — share/concentrated
    None, ha kevés (ASSIST_CONC_MIN alatti) a gólpasszos gól.
    """
    from .event_detection import EventType, detect_events

    counts: dict = {"home": {}, "away": {}}
    for e in detect_events(match, config or TacticsConfig()):
        if e.type != EventType.GOAL:
            continue
        aid = (e.detail or {}).get("assist_id")
        if aid is None:
            continue
        by = counts[e.team.value]
        by[aid] = by.get(aid, 0) + 1
    out: dict = {}
    for side in ("home", "away"):
        by = counts[side]
        total = sum(by.values())
        top_pid = max(by, key=lambda p: by[p]) if by else None
        top = by[top_pid] if top_pid is not None else 0
        rec = {"assists": total, "top_assists": top,
               "top_player_id": top_pid, "share": None,
               "concentrated": None}
        if total >= ASSIST_CONC_MIN:
            rec["share"] = round(top / total, 2)
            rec["concentrated"] = rec["share"] >= ASSIST_CONC_TOP_SHARE
        out[side] = rec
    return out


# Gól-előkészítés hossza: a gól előtti ennyi másodperc saját passzait
# számoljuk (az előző birtoklásig visszanézve); legfeljebb ennyi passz
# a direkt, legalább ennyi a kombinatív gól; ennyi góltól ítélünk, és
# e részarányok döntik el a címkét.
BUILDUP_WINDOW_S = 20.0
BUILDUP_SHORT_PASSES = 2
BUILDUP_LONG_PASSES = 5
BUILDUP_MIN_GOALS = 4
BUILDUP_SHORT_SHARE = 50.0
BUILDUP_LONG_SHARE = 50.0


def goal_buildup(match: Match,
                 config: Optional[TacticsConfig] = None) -> dict:
    """Gól-előkészítés hossza: direkt vagy kombinatív gólokból élnek.

    Gólonként megszámoljuk a gólt szerző csapat passzait a gól előtti
    ablakban — az előző gólig vagy az ellenfél utolsó eseményéig
    (birtoklás-határ) visszanézve. A direkt csapat (a gólok fele 0–2
    passzból) az első hullámból és az átmenetből él: ellene a
    visszarendeződés és az első hullám megfogása a meccs; a
    kombinatív csapat (a gólok fele 5+ passzból) kijátssza a falat:
    ellene türelmes, fegyelmezett fal kell — aki az ötödik passznál
    kilép, azon átmennek.

    Visszatérés csapatonként: {"goals", "short", "long", "short_pct",
    "long_pct", "style"} — pct/style None, ha kevés
    (BUILDUP_MIN_GOALS alatti) a gól; a style "direkt" /
    "kombinatív" / None (vegyes).
    """
    from .event_detection import EventType, detect_events

    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = round(BUILDUP_WINDOW_S * fps)
    events = sorted(detect_events(match, config or TacticsConfig()),
                    key=lambda e: e.t)
    counts = {"home": {"goals": 0, "short": 0, "long": 0},
              "away": {"goals": 0, "short": 0, "long": 0}}
    for gi, g in enumerate(events):
        if g.type != EventType.GOAL:
            continue
        side = g.team.value
        n_pass = 0
        for e in reversed(events[:gi]):
            if g.t - e.t > win:
                break
            # Birtoklás-határ: korábbi gól vagy az ellenfél eseménye.
            if e.type == EventType.GOAL or e.team != g.team:
                break
            if e.type == EventType.PASS:
                n_pass += 1
        rec = counts[side]
        rec["goals"] += 1
        if n_pass <= BUILDUP_SHORT_PASSES:
            rec["short"] += 1
        if n_pass >= BUILDUP_LONG_PASSES:
            rec["long"] += 1
    out = {}
    for side in ("home", "away"):
        rec = counts[side]
        r = {**rec, "short_pct": None, "long_pct": None, "style": None}
        if rec["goals"] >= BUILDUP_MIN_GOALS:
            short_pct = 100.0 * rec["short"] / rec["goals"]
            long_pct = 100.0 * rec["long"] / rec["goals"]
            r["short_pct"] = round(short_pct, 1)
            r["long_pct"] = round(long_pct, 1)
            if short_pct >= BUILDUP_SHORT_SHARE:
                r["style"] = "direkt"
            elif long_pct >= BUILDUP_LONG_SHARE:
                r["style"] = "kombinatív"
        out[side] = r
    return out


# Oldalváltás: ekkora keresztirányú (y) elmozdulás számít
# oldalváltó passznak; ennyi támadó-térfeles passz kell az ítélethez,
# és e részarányok döntik el a címkét.
SWITCH_MIN_DY_M = 10.0
SWITCH_MIN_PASSES = 30
SWITCH_HIGH_PCT = 12.0
SWITCH_LOW_PCT = 3.0


def side_switching(match: Match,
                   config: Optional[TacticsConfig] = None) -> dict:
    """Oldalváltás: széthúzzák-e a falat gyors keresztpasszokkal.

    A támadó térfélen adott passzok közül megszámoljuk azokat,
    amelyeknél a passzoló és a fogadó közt legalább SWITCH_MIN_DY_M
    méter a keresztirányú (oldal-oldal) távolság. Az oldalváltó
    csapat szét akarja húzni a falat: ellene kompakt eltolás kell —
    a váltás alatt zárt sávok, senki nem csúszhat el; az egy-oldalas
    csapat beragad: a fal bátran eltolható a kedvenc oldalára, a
    túloldali szélsőjük éhen marad.

    Visszatérés csapatonként: {"passes", "switches", "switch_pct",
    "style"} — pct/style None, ha kevés (SWITCH_MIN_PASSES alatti) a
    támadó-térfeles passz; a style "oldalváltó" / "egy-oldalas" /
    None (vegyes).
    """
    from .calibration import COURT_LENGTH_M
    from .event_detection import EventType, detect_events

    config = config or TacticsConfig()
    mid = COURT_LENGTH_M / 2.0
    idx_of = {f.t: i for i, f in enumerate(match.frames)}
    counts = {"home": {"passes": 0, "switches": 0},
              "away": {"passes": 0, "switches": 0}}
    for e in detect_events(match, config):
        if e.type != EventType.PASS or e.player_id is None:
            continue
        rid = (e.detail or {}).get("receiver_id")
        if rid is None:
            continue
        i0 = idx_of.get(e.t)
        if i0 is None:
            continue
        f = match.frames[i0]
        by_id = {p.track_id: p for p in f.players}
        passer = by_id.get(e.player_id)
        receiver = by_id.get(rid)
        if passer is None or receiver is None:
            continue
        attacks_positive = config.attacks_toward_x(e.team) > mid
        def _att_half(x):
            return x > mid if attacks_positive else x < mid
        if not (_att_half(passer.x) and _att_half(receiver.x)):
            continue
        rec = counts[e.team.value]
        rec["passes"] += 1
        if abs(receiver.y - passer.y) >= SWITCH_MIN_DY_M:
            rec["switches"] += 1
    out = {}
    for side in ("home", "away"):
        rec = counts[side]
        r = {**rec, "switch_pct": None, "style": None}
        if rec["passes"] >= SWITCH_MIN_PASSES:
            pct = 100.0 * rec["switches"] / rec["passes"]
            r["switch_pct"] = round(pct, 1)
            if pct >= SWITCH_HIGH_PCT:
                r["style"] = "oldalváltó"
            elif pct <= SWITCH_LOW_PCT:
                r["style"] = "egy-oldalas"
        out[side] = r
    return out


# Elzárás-használat: a lövő őrzője ennyire lehet a lövőtől, hogy
# "őrzöttnek" számítson; a társ ennyire az őrzőtől, hogy elzárásnak;
# ennyi őrzött lövés kell az ítélethez, és e részarányok döntik el a
# címkét.
SCREEN_MARKER_MAX_M = 3.0
SCREEN_DIST_M = 2.0
SCREEN_MIN_SHOTS = 8
SCREEN_HIGH_PCT = 40.0
SCREEN_LOW_PCT = 10.0


def screen_usage(match: Match,
                 config: Optional[TacticsConfig] = None) -> dict:
    """Elzárás-használat: elzárásból lőnek, vagy tisztán, 1v1-ből.

    Lövésenként megnézzük, hogy a lövő őrzője (a hozzá legközelebbi
    védő) mellett áll-e egy támadó társ elzárásban. Az elzárásos
    csapat ellen a váltás-kommunikáció a meccs: hangos váltás vagy
    átcsúszás az elzárás alatt, különben a lövő mindig tisztán marad;
    az elzárás nélkül lövő csapat lövője viszont magára van hagyva —
    a kilépés és a blokk ellene szinte ingyen van, és saját
    olvasatban az elzárás-játék hiánya edzés-téma.

    Visszatérés csapatonként: {"shots", "screened", "screen_pct",
    "style"} — pct/style None, ha kevés (SCREEN_MIN_SHOTS alatti) az
    őrzött lövés; a style "elzárásos" / "elzárás nélküli" / None.
    """
    import math

    from .xg import match_xg

    config = config or TacticsConfig()
    idx_of = {f.t: i for i, f in enumerate(match.frames)}
    counts = {"home": {"shots": 0, "screened": 0},
              "away": {"shots": 0, "screened": 0}}
    for sh in match_xg(match, config).get("shots", []):
        pid = sh.get("player_id")
        i0 = idx_of.get(sh["t"])
        if pid is None or i0 is None:
            continue
        f = match.frames[i0]
        shooter = next((p for p in f.players if p.track_id == pid),
                       None)
        if shooter is None:
            continue
        defenders = [p for p in f.players
                     if p.team is not None and p.team != shooter.team]
        marker = None
        best = SCREEN_MARKER_MAX_M
        for d in defenders:
            dist = math.hypot(d.x - shooter.x, d.y - shooter.y)
            if dist <= best:
                marker, best = d, dist
        if marker is None:
            continue  # szabad lövés: nincs kit elzárni
        rec = counts[sh["team"]]
        rec["shots"] += 1
        screened = any(
            p.track_id != pid and p.team == shooter.team
            and math.hypot(p.x - marker.x, p.y - marker.y)
            <= SCREEN_DIST_M
            for p in f.players)
        if screened:
            rec["screened"] += 1
    out = {}
    for side in ("home", "away"):
        rec = counts[side]
        r = {**rec, "screen_pct": None, "style": None}
        if rec["shots"] >= SCREEN_MIN_SHOTS:
            pct = 100.0 * rec["screened"] / rec["shots"]
            r["screen_pct"] = round(pct, 1)
            if pct >= SCREEN_HIGH_PCT:
                r["style"] = "elzárásos"
            elif pct <= SCREEN_LOW_PCT:
                r["style"] = "elzárás nélküli"
        out[side] = r
    return out


# Passz-kockázat: ettől a távolságtól számít hosszúnak a passz;
# sávonként ennyi kísérlet kell az ítélethez, és ekkora eladás-arány
# különbség (százalékpont) számít érdeminek.
PASSRISK_LONG_M = 10.0
PASSRISK_MIN_TRIES = 8
PASSRISK_GAP_PP = 15.0


def pass_risk(match: Match,
              config: Optional[TacticsConfig] = None) -> dict:
    """Passz-kockázat: a hosszú passzok eladás-aránya a rövidekhez
    képest.

    Minden labda-továbbítási kísérletet (sikeres passz vagy eladás) a
    kiinduló és a megszerző játékos távolsága alapján hosszú és rövid
    sávra bontunk, és sávonként számoljuk az eladás-arányt. Akinek a
    hosszú passzai érdemben többször vesznek el, annál a hosszú
    passzsávok lezárása a terv: a letámadás és a sávba állás azonnal
    labdát hoz — és saját olvasatban a hosszú passz technikája
    (feszes, előre vezetett labda) az edzés-téma.

    Visszatérés csapatonként: {"long_tries", "long_to",
    "short_tries", "short_to", "long_to_pct", "short_to_pct",
    "gap_pp", "verdict"} — pct/gap/verdict None, ha bármelyik sávban
    kevés (PASSRISK_MIN_TRIES alatti) a kísérlet; a verdict
    "kockázatos" (a hosszú passz vész el) / "biztos kezű" / None.
    """
    import math

    from .event_detection import EventType, detect_events

    config = config or TacticsConfig()
    idx_of = {f.t: i for i, f in enumerate(match.frames)}
    counts = {s: {"long_tries": 0, "long_to": 0,
                  "short_tries": 0, "short_to": 0}
              for s in ("home", "away")}
    for e in detect_events(match, config):
        if e.type not in (EventType.PASS, EventType.TURNOVER):
            continue
        if e.player_id is None:
            continue
        i0 = idx_of.get(e.t)
        if i0 is None:
            continue
        f = match.frames[i0]
        by_id = {p.track_id: p for p in f.players}
        passer = by_id.get(e.player_id)
        if passer is None:
            continue
        if e.type == EventType.PASS:
            rid = (e.detail or {}).get("receiver_id")
            taker = by_id.get(rid) if rid is not None else None
        else:
            # Eladásnál a megszerző az ellenfél labdához legközelebbi
            # játékosa a kockán.
            taker = None
            if f.ball is not None:
                best = None
                for p in f.players:
                    if p.team is None or p.team == e.team:
                        continue
                    d = math.hypot(p.x - f.ball.x, p.y - f.ball.y)
                    if best is None or d < best:
                        taker, best = p, d
        if taker is None:
            continue
        dist = math.hypot(taker.x - passer.x, taker.y - passer.y)
        rec = counts[e.team.value]
        band = "long" if dist >= PASSRISK_LONG_M else "short"
        rec[band + "_tries"] += 1
        if e.type == EventType.TURNOVER:
            rec[band + "_to"] += 1
    out = {}
    for side in ("home", "away"):
        rec = counts[side]
        r = {**rec, "long_to_pct": None, "short_to_pct": None,
             "gap_pp": None, "verdict": None}
        if rec["long_tries"] >= PASSRISK_MIN_TRIES \
                and rec["short_tries"] >= PASSRISK_MIN_TRIES:
            lon = 100.0 * rec["long_to"] / rec["long_tries"]
            sho = 100.0 * rec["short_to"] / rec["short_tries"]
            r["long_to_pct"] = round(lon, 1)
            r["short_to_pct"] = round(sho, 1)
            r["gap_pp"] = round(lon - sho, 1)
            if lon - sho >= PASSRISK_GAP_PP:
                r["verdict"] = "kockázatos"
            elif sho - lon >= PASSRISK_GAP_PP:
                r["verdict"] = "biztos kezű"
        out[side] = r
    return out


# Fölény-befejezés: ennyi lövés kell sávonként az ítélethez, és ennyi
# százalékpont gólarány-eltérés a "fölény-függő" / "fal-törő" küszöb.
OVERLOAD_MIN_SHOTS = 5
OVERLOAD_GAP_PP = 15.0


def overload_finishing(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Fölény-befejezés: fölényben vagy felállt fal ellen szereznek gólt.

    Az átmenet-támadás (transition_offense) azt méri, MENNYI gyors gól
    születik a szerzésekből — ez azt, hogy a gólok LÉTSZÁMFÖLÉNYBŐL
    jönnek-e: minden lövésnél megszámolja, hány támadó és hány védő van
    a támadott térfélen. Ha több a támadó, a lövés "fölényben"
    született, egyébként felállt fal ellen. Aki csak fölényben
    eredményes, azt vissza kell kényszeríteni a felállt támadásba: a
    visszarendeződés-sprint ér ellene a legtöbbet. Aki a falat is
    töri, ellen a puszta hazaérés kevés — nyomás és szoros emberfogás
    kell.

    Visszatérés csapatonként: {"overload_shots", "overload_goals",
    "set_shots", "set_goals", "overload_pct", "set_pct", "gap_pp",
    "verdict"} — az arányok és a verdict None, ha valamelyik sávban
    kevés (OVERLOAD_MIN_SHOTS alatti) a lövés; a verdict
    "fölény-függő" / "fal-törő" / None.
    """
    from ..models.tracking import Team
    from .calibration import COURT_LENGTH_M
    from .xg import match_xg

    config = config or TacticsConfig()
    half = COURT_LENGTH_M / 2.0
    frames = {f.t: f for f in match.frames}
    counts = {s: {"overload_shots": 0, "overload_goals": 0,
                  "set_shots": 0, "set_goals": 0}
              for s in ("home", "away")}
    for sh in match_xg(match, config).get("shots", []):
        f = frames.get(sh["t"])
        if f is None:
            continue
        side = sh["team"]
        team = Team.HOME if side == "home" else Team.AWAY
        goal_x = config.attacks_toward_x(team)
        # A támadott térfél: a támadott kapuhoz közelebbi fél pálya.
        attackers = sum(1 for p in f.players
                        if p.team == team and abs(p.x - goal_x) < half)
        defenders = sum(1 for p in f.players
                        if p.team is not None and p.team != team
                        and abs(p.x - goal_x) < half)
        if attackers == 0 or defenders == 0:
            continue  # hiányos követés: nem ítélünk létszámot
        key = "overload" if attackers > defenders else "set"
        counts[side][key + "_shots"] += 1
        if sh["outcome"] == "goal":
            counts[side][key + "_goals"] += 1
    out = {}
    for side in ("home", "away"):
        rec = counts[side]
        r = {**rec, "overload_pct": None, "set_pct": None,
             "gap_pp": None, "verdict": None}
        if rec["overload_shots"] >= OVERLOAD_MIN_SHOTS \
                and rec["set_shots"] >= OVERLOAD_MIN_SHOTS:
            ovl = 100.0 * rec["overload_goals"] / rec["overload_shots"]
            st = 100.0 * rec["set_goals"] / rec["set_shots"]
            r["overload_pct"] = round(ovl, 1)
            r["set_pct"] = round(st, 1)
            r["gap_pp"] = round(ovl - st, 1)
            if ovl - st >= OVERLOAD_GAP_PP:
                r["verdict"] = "fölény-függő"
            elif st - ovl >= OVERLOAD_GAP_PP:
                r["verdict"] = "fal-törő"
        out[side] = r
    return out


# Lövő-kapuoldal: ennyi bekönyvelt góltól nevezünk meg egy játékost, és
# e részarány felett nevezzük kiszámíthatónak a kapuoldal-szokását.
SHOOTER_SIDE_MIN_GOALS = 4
SHOOTER_SIDE_SHARE = 0.6


def shooter_placement(match: Match,
                      config: Optional[TacticsConfig] = None) -> dict:
    """Lövő-kapuoldal: ki melyik sarokba lő.

    A kapu-sarok (goal_placement) csapat-szinten mondja meg, merre
    mennek a gólok — ez lövőnként: a kapus akkor tud készülni, ha
    NÉVRE szól a jelzés. Aki a góljainak SHOOTER_SIDE_SHARE részét
    ugyanarra az oldalra lövi, az kiszámítható: a kapus arra az
    oldalra állhat rá, a fal a másikat zárja — saját olvasatban neki
    a kapuoldal-váltás a gyakorlandó.

    Visszatérés csapatonként: {"players": [{"player_id", "goals",
    "bal", "közép", "jobb", "dominant", "share_pct"}], "predictable"}
    — a lista gólszám szerint csökkenő, dominant/share_pct None, ha
    kevés (SHOOTER_SIDE_MIN_GOALS alatti) a gól; a predictable az
    első olyan játékos, aki a küszöb felett egyoldalú (egyébként
    None).
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
                rel = (b.y - lo) / span
                # A lövő szemszögéhez igazítva (a két kaput tükrözzük).
                leftness = (rel if goal_x >= COURT_LENGTH_M / 2
                            else 1.0 - rel)
                if leftness >= 2.0 / 3.0:
                    return "bal"
                if leftness <= 1.0 / 3.0:
                    return "jobb"
                return "közép"
        return None

    tally: dict = {"home": {}, "away": {}}
    for e in detect_shots(match, config):
        if e.type != EventType.GOAL or e.player_id is None:
            continue
        side = _side_of_goal(e)
        if side is None:
            continue
        rec = tally[e.team.value].setdefault(
            e.player_id, {"bal": 0, "közép": 0, "jobb": 0})
        rec[side] += 1

    out: dict = {}
    for s in ("home", "away"):
        players = []
        for pid, rec in tally[s].items():
            goals = rec["bal"] + rec["közép"] + rec["jobb"]
            p = {"player_id": pid, "goals": goals, **rec,
                 "dominant": None, "share_pct": None}
            if goals >= SHOOTER_SIDE_MIN_GOALS:
                dom = max(("bal", "közép", "jobb"), key=lambda k: rec[k])
                p["dominant"] = dom
                p["share_pct"] = round(100.0 * rec[dom] / goals, 1)
            players.append(p)
        players.sort(key=lambda p: -p["goals"])
        predictable = next(
            (p for p in players
             if p["share_pct"] is not None
             and p["share_pct"] >= 100.0 * SHOOTER_SIDE_SHARE), None)
        out[s] = {"players": players, "predictable": predictable}
    return out


# Támadás-indítók: ennyi mért támadástól ítélünk, és e feletti
# részarány jelenti, hogy egy ember hozza fel a labdát.
STARTER_MIN_ATTACKS = 6
STARTER_TOP_SHARE = 40.0


def attack_starters(match: Match,
                    config: Optional[TacticsConfig] = None) -> dict:
    """Támadás-indítók: KI hozza fel a labdát.

    A támadás-eredet (attack_origins) azt mondja meg, MIBŐL indul a
    támadás (középkezdés, kidobás, labdaszerzés) — ez azt, KI INDÍTJA:
    minden támadás-szakasz első azonosított labdabirtokosát (a kapust
    kihagyva) az indítójának vesszük. A szakasz a támadó térfélen
    kezdődik, tehát az indító az az ember, akinél a labda átjön a
    felezővonalon és megindul a támadás.

    Edzőileg: ha egy ember hozza fel a labdák nagy részét, ő a
    kihozatali kulcs — rá kell menni a felhozatalnál (letámadás, az
    átadás-vonal zárása), mert nélküle megakad a felállásuk. Ha
    megoszlik, a letámadás kevésbé kifizetődő: ott a felállt védekezés
    a válasz.

    Visszatérés csapatonként: {"attacks", "players": [{"player_id",
    "jersey", "starts", "share_pct"}], "top"} — a lista indítás szerint
    csökkenő; a "top" az első játékos, ha legalább STARTER_MIN_ATTACKS
    mért támadás van, és a részaránya eléri a STARTER_TOP_SHARE-t
    (egyébként None).
    """
    from .decisions import ball_holder
    from .setplays import segment_attacks

    config = config or TacticsConfig()
    jersey: dict = {}
    tally: dict = {"home": {}, "away": {}}
    for seq in segment_attacks(match, config):
        side = seq.team.value
        for fr in seq.frames:
            h = ball_holder(fr, config)
            if h is None or h.team != seq.team:
                continue
            if getattr(h, "role", None) == "kapus":
                continue
            if getattr(h, "jersey_number", None) is not None:
                jersey.setdefault(h.track_id, h.jersey_number)
            tally[side][h.track_id] = tally[side].get(h.track_id, 0) + 1
            break

    out: dict = {}
    for side in ("home", "away"):
        n = sum(tally[side].values())
        players = [{"player_id": pid, "jersey": jersey.get(pid),
                    "starts": k,
                    "share_pct": (round(100.0 * k / n, 1) if n else None)}
                   for pid, k in sorted(tally[side].items(),
                                        key=lambda kv: -kv[1])]
        top = None
        if n >= STARTER_MIN_ATTACKS and players \
                and (players[0]["share_pct"] or 0.0) >= STARTER_TOP_SHARE:
            top = players[0]
        out[side] = {"attacks": n, "players": players, "top": top}
    return out


# Támadás-kimenetel: ennyi mért támadástól ítélünk; e feletti
# eladás-arány jelenti, hogy a támadásaik lövés nélkül halnak el, és e
# feletti lövés-arány azt, hogy szinte minden támadásukat befejezik.
OUTCOME_MIN_ATTACKS = 8
OUTCOME_TURNOVER_HIGH = 25.0
OUTCOME_SHOT_HIGH = 85.0


def attack_outcomes(match: Match,
                    config: Optional[TacticsConfig] = None) -> dict:
    """Támadás-kimenetel: MIVEL zárulnak a támadásaik.

    A támadás-hatékonyság (attack_efficiency) azt mondja meg, a
    támadásaikból mennyi lesz gól — ez azt, hogy egyáltalán ELJUTNAK-E
    a befejezésig: minden támadás-szakaszt lövéssel, hetessel,
    eladással vagy "egyéb"-bel (lefújás, félidő, követés-vesztés)
    zárunk le. A kettő közti rés a lényeg: egy 30%-os gólarány mást
    jelent 90%-os és 60%-os lövés-aránnyal.

    Edzőileg: ha a támadásaik negyede eladással hal el, a kettőzés és a
    magas nyomás azonnal termel; ha szinte mindent befejeznek, a
    nyomás kockázat — ott a blokk és a kapus mögé rendezett fal a
    válasz.

    Visszatérés csapatonként: {"attacks", "outcomes": {kimenetel:
    darab}, "shot_pct", "turnover_pct", "verdict"} — az arányok és a
    verdict None OUTCOME_MIN_ATTACKS alatt; a verdict "lövés nélkül
    halnak el" / "mindent befejeznek" / None.
    """
    from .event_detection import EventType, detect_events, detect_shots
    from .rules import detect_seven_meters

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    tail = round(ATTACK_TAIL_S * fps)
    shots = [(e.t, e.team.value) for e in detect_shots(match, config)
             if e.type in (EventType.SHOT, EventType.GOAL)]
    turnovers = [(e.t, e.team.value) for e in detect_events(match, config)
                 if e.type == EventType.TURNOVER]
    sevens = [(sm["t"], sm["team"])
              for sm in detect_seven_meters(match, config)]

    out: dict = {side: {"attacks": 0, "outcomes": {}, "shot_pct": None,
                        "turnover_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for a in classify_attacks(match, config):
        side = a["team"]
        lo, hi = a["start_frame"], a["end_frame"] + tail
        in_win = [t for (t, tm) in sevens if tm == side and lo <= t <= hi]
        if in_win:
            kind = "hetes"
        elif any(tm == side and lo <= t <= hi for (t, tm) in shots):
            kind = "lövés"
        elif any(tm == side and lo <= t <= hi for (t, tm) in turnovers):
            kind = "eladás"
        else:
            kind = "egyéb"
        rec = out[side]
        rec["attacks"] += 1
        rec["outcomes"][kind] = rec["outcomes"].get(kind, 0) + 1

    for side in ("home", "away"):
        rec = out[side]
        rec["outcomes"] = dict(sorted(rec["outcomes"].items(),
                                      key=lambda kv: -kv[1]))
        n = rec["attacks"]
        if n >= OUTCOME_MIN_ATTACKS:
            shot_pct = 100.0 * rec["outcomes"].get("lövés", 0) / n
            to_pct = 100.0 * rec["outcomes"].get("eladás", 0) / n
            rec["shot_pct"] = round(shot_pct, 1)
            rec["turnover_pct"] = round(to_pct, 1)
            if to_pct >= OUTCOME_TURNOVER_HIGH:
                rec["verdict"] = "lövés nélkül halnak el"
            elif shot_pct >= OUTCOME_SHOT_HIGH:
                rec["verdict"] = "mindent befejeznek"
    return out


# Szélső-bevonás: ennyi mért támadástól ítélünk; e feletti arányban
# széleznek, e alattiban közép-központúak.
WING_INV_MIN_ATTACKS = 8
WING_INV_HIGH = 60.0
WING_INV_LOW = 30.0


def wing_involvement(match: Match,
                     config: Optional[TacticsConfig] = None) -> dict:
    """Szélső-bevonás: ELJUT-E a labda a szélre a támadásaikban.

    A szélső-befejezés (wing_finishing) azt méri, mennyire eredményes a
    szélső, ha LŐ — ez azt, hogy egyáltalán megkapja-e a labdát:
    támadás-szakaszonként megnézzük, járt-e a labda a szél-sávban (a
    pálya közepétől WING_LATERAL_M-nél oldalabb, a támadó térfélen).

    Edzőileg: aki széthúzza a támadást, annál a szélső-védekezés és a
    kifutás a feladat; aki közép-központú (a labda ki sem megy a
    szélre), annál a szélső-védők beljebb segíthetnek — tömör fallal a
    beállót és az átlövést kell elzárni, mert a szélt úgysem játsszák
    meg.

    Visszatérés csapatonként: {"attacks", "with_wing", "share_pct",
    "verdict"} — a share_pct/verdict None WING_INV_MIN_ATTACKS alatt; a
    verdict "széthúzzák a támadást" / "közép-központú" / None.
    """
    from .calibration import COURT_WIDTH_M
    from .setplays import segment_attacks
    from .tactics import COURT_LENGTH_M

    config = config or TacticsConfig()
    cy = COURT_WIDTH_M / 2.0
    half = COURT_LENGTH_M / 2.0

    out: dict = {side: {"attacks": 0, "with_wing": 0, "share_pct": None,
                        "verdict": None} for side in ("home", "away")}
    for seq in segment_attacks(match, config):
        side = seq.team.value
        goal_x = config.attacks_toward_x(seq.team)
        rec = out[side]
        rec["attacks"] += 1
        for fr in seq.frames:
            b = fr.ball
            if b is None:
                continue
            # Csak a támadó térfélen számít a szélre kerülés.
            if abs(b.x - goal_x) > half:
                continue
            if abs(b.y - cy) >= WING_LATERAL_M:
                rec["with_wing"] += 1
                break

    for side in ("home", "away"):
        rec = out[side]
        if rec["attacks"] >= WING_INV_MIN_ATTACKS:
            share = 100.0 * rec["with_wing"] / rec["attacks"]
            rec["share_pct"] = round(share, 1)
            if share >= WING_INV_HIGH:
                rec["verdict"] = "széthúzzák a támadást"
            elif share <= WING_INV_LOW:
                rec["verdict"] = "közép-központú"
    return out


# Támadás-mélység: ennyi mérhető kocka kell az átlaghoz; e alatt
# rátapadnak a 9 m-es vonalra, e fölött mélyen, hátrahúzódva játszanak.
ATTACK_DEPTH_MIN_FRAMES = 100
ATTACK_DEPTH_CLOSE_M = 9.5
ATTACK_DEPTH_DEEP_M = 12.0


def attack_depth(match, config=None) -> dict:
    """Támadás-mélység: MILYEN MESSZE állnak a kaputól felállt
    támadásban.

    A támadás-szélesség (attack_width) az oldalirányú terjedelmet méri
    — ez a mélységet: saját labdabirtoklású kockánként a támadott
    térfélen lévő (nem kapus) támadók átlagos kapu-távolsága, legalább
    3 látott támadóval.

    Edzőileg: aki a 9 m-es vonalra tapad, az betörésre és beugrásra
    játszik — ellene a fal nem léphet ki, a segítő-csúszás és a
    testes fogadás a válasz. Aki mélyen, hátrahúzódva áll, annak idő
    kell a lövés-előkészítéshez — ellene ki kell lépni a
    lövő-vonalba, mert a távoli lövés az egyetlen fegyvere.

    Visszatérés csapatonként: {"frames", "avg_depth_m", "style"} — az
    átlag és a style None, ha nincs ATTACK_DEPTH_MIN_FRAMES mérhető
    kocka; a style "vonalra tapadó" / "mély (hátrahúzódó)" /
    "kiegyensúlyozott".
    """
    import math

    from .calibration import COURT_WIDTH_M
    from .tactics import TacticsConfig, possession_team

    config = config or TacticsConfig()
    cy = COURT_WIDTH_M / 2.0
    acc = {"home": [0, 0.0], "away": [0, 0.0]}  # (kocka, összeg)
    for fr in match.frames:
        poss = possession_team(fr, config)
        if poss is None:
            continue
        goal_x = config.attacks_toward_x(poss)
        dists = [math.hypot(p.x - goal_x, p.y - cy) for p in fr.players
                 if p.team == poss and p.role != "kapus"
                 and abs(p.x - goal_x) <= 15.0]
        if len(dists) < 3:
            continue
        rec = acc[poss.value]
        rec[0] += 1
        rec[1] += sum(dists) / len(dists)

    out = {}
    for side in ("home", "away"):
        n, total = acc[side]
        avg = round(total / n, 1) if n >= ATTACK_DEPTH_MIN_FRAMES else None
        style = None
        if avg is not None:
            style = ("vonalra tapadó" if avg <= ATTACK_DEPTH_CLOSE_M
                     else "mély (hátrahúzódó)" if avg >= ATTACK_DEPTH_DEEP_M
                     else "kiegyensúlyozott")
        out[side] = {"frames": n, "avg_depth_m": avg, "style": style}
    return out


# Beálló-kiszolgálás: ennyi mért beadás kell az ítélethez, és e feletti
# részarány jelenti, hogy egy ember szolgálja ki a beállót.
PIVOT_FEED_MIN = 4
PIVOT_FEED_SHARE = 50.0


def pivot_feeders(match: Match,
                  config: Optional[TacticsConfig] = None) -> dict:
    """Beálló-kiszolgálók: KI adja be a labdát a beállónak.

    A beálló-terhelés (pivot_usage) azt mondja meg, a támadásaik
    mekkora része megy át a beállón — ez azt, KIN keresztül: minden
    olyan passzt számolunk, amelynek a fogadója a becsült beálló, és a
    passzolóhoz írjuk.

    Edzőileg: ha egy ember adja a beadások felét, őt kell zárni — rá
    kell lépni a beálló-vonalba, és az ő oldalán kell a kettőzést
    indítani, mert nélküle a beállójuk kiesik a játékból.

    Visszatérés csapatonként: {"feeds", "players": [{"player_id",
    "jersey", "feeds", "share_pct"}], "top"} — a lista beadás szerint
    csökkenő; a "top" az első játékos, ha legalább PIVOT_FEED_MIN mért
    beadás van, a részaránya eléri a PIVOT_FEED_SHARE-t, és nincs vele
    holtversenyben másik kiszolgáló.
    """
    from .decisions import detect_passes
    from .roles import estimate_positions

    config = config or TacticsConfig()
    posts = estimate_positions(match, config)
    pivots = {side: {tid for tid, r in posts.get(side, {}).items()
                     if r["poszt"] == "beálló"}
              for side in ("home", "away")}

    jersey: dict = {}
    tally: dict = {"home": {}, "away": {}}
    for p in detect_passes(match, config):
        side = p.team.value
        if p.receiver_id not in pivots[side]:
            continue
        if p.passer_id in pivots[side]:
            continue  # beálló–beálló átadás nem kiszolgálás
        if p.passer_pos.jersey_number is not None:
            jersey.setdefault(p.passer_id, p.passer_pos.jersey_number)
        tally[side][p.passer_id] = tally[side].get(p.passer_id, 0) + 1

    out: dict = {}
    for side in ("home", "away"):
        n = sum(tally[side].values())
        players = [{"player_id": pid, "jersey": jersey.get(pid),
                    "feeds": k,
                    "share_pct": (round(100.0 * k / n, 1) if n else None)}
                   for pid, k in sorted(tally[side].items(),
                                        key=lambda kv: -kv[1])]
        top = None
        if n >= PIVOT_FEED_MIN and players \
                and (players[0]["share_pct"] or 0.0) >= PIVOT_FEED_SHARE:
            tie = (len(players) > 1
                   and players[1]["feeds"] == players[0]["feeds"])
            if not tie:
                top = players[0]
        out[side] = {"feeds": n, "players": players, "top": top}
    return out


# Beálló-oldal: ennyi mért kocka kell az ítélethez, e feletti részarány
# jelenti, hogy a beálló egy oldalon dolgozik — a sáv-küszöb a beálló
# szűk (kapu előtti) mozgásteréhez igazítva szűkebb, mint a lövéseknél.
PIVOT_SIDE_MIN_FRAMES = 100
PIVOT_SIDE_SHARE = 55.0
PIVOT_SIDE_BAND_M = 1.5


def pivot_side(match: Match,
               config: Optional[TacticsConfig] = None) -> dict:
    """Beálló-oldal: MELYIK OLDALON dolgozik a beállójuk.

    A beálló-terhelés (pivot_usage) azt mondja meg, mennyit játszanak
    rajta, a beálló-kiszolgálás (pivot_feeders) azt, kin keresztül —
    ez azt, HOL: a becsült beálló helyét kockánként (saját
    birtokláskor, a támadó térfélen) bal / közép / jobb sávba soroljuk.
    A "bal" itt is a TÁMADÓ bal keze felőli oldal, mint az
    oldal-részrehajlásnál, így a két csapat összevethető.

    Edzőileg: ha a beálló a kockák több mint felében ugyanazon az
    oldalon áll be, az adott középső-oldalsó védőpárnak kell rá
    készülnie — ott kell az átadás-fegyelem és a testes fogadás, a
    másik oldalon pedig szűkíthető a segítés.

    Visszatérés csapatonként: {"frames", "left", "center", "right",
    "dominant", "share_pct"} — a dominant/share_pct None
    PIVOT_SIDE_MIN_FRAMES alatt vagy PIVOT_SIDE_SHARE alatti
    többségnél; a dominant "bal" / "jobb" / "közép".
    """
    from ..models.tracking import Team
    from .calibration import COURT_WIDTH_M
    from .roles import estimate_positions
    from .tactics import possession_team

    config = config or TacticsConfig()
    cy = COURT_WIDTH_M / 2.0
    posts = estimate_positions(match, config)
    pivots = {side: {tid for tid, r in posts.get(side, {}).items()
                     if r["poszt"] == "beálló"}
              for side in ("home", "away")}

    counts = {side: {"left": 0, "center": 0, "right": 0}
              for side in ("home", "away")}
    for fr in match.frames:
        poss = possession_team(fr, config)
        if poss is None:
            continue
        side = poss.value
        if not pivots[side]:
            continue
        goal_x = config.attacks_toward_x(poss)
        for p in fr.players:
            if p.team != poss or p.track_id not in pivots[side]:
                continue
            if abs(p.x - goal_x) > 15.0:
                continue
            d = p.y - cy
            if config.attacks_toward_x(
                    Team.HOME if side == "home" else Team.AWAY) == 0.0:
                d = -d  # a -x felé támadónál a bal kéz a -y oldal
            if d > PIVOT_SIDE_BAND_M:
                counts[side]["left"] += 1
            elif d < -PIVOT_SIDE_BAND_M:
                counts[side]["right"] += 1
            else:
                counts[side]["center"] += 1

    out: dict = {}
    for side in ("home", "away"):
        rec = dict(counts[side])
        n = rec["left"] + rec["center"] + rec["right"]
        rec["frames"] = n
        rec["dominant"] = rec["share_pct"] = None
        if n >= PIVOT_SIDE_MIN_FRAMES:
            best = max(("left", "center", "right"), key=lambda k: rec[k])
            pct = 100.0 * rec[best] / n
            if pct >= PIVOT_SIDE_SHARE:
                rec["dominant"] = {"left": "bal", "right": "jobb",
                                   "center": "közép"}[best]
                rec["share_pct"] = round(pct, 1)
        out[side] = rec
    return out


# Szélső-befejezés oldalanként: oldalanként ennyi lövés kell az
# ítélethez, és ekkora (százalékpontos) különbség számít érdemi
# oldal-eltérésnek.
WING_SIDE_MIN_SHOTS = 3
WING_SIDE_GAP_PP = 25.0


def wing_finishing_by_side(match: Match,
                           config: Optional[TacticsConfig] = None) -> dict:
    """Szélső-befejezés oldalanként: MELYIK szélsőjük veszélyes.

    A szélső-befejezés (wing_finishing) a két szélt együtt méri — ez
    szétbontja: a szélső-sávból leadott lövéseket a TÁMADÓ bal keze
    felőli ("bal") és a másik ("jobb") oldalra osztjuk, és
    oldalanként számolunk gólarányt.

    Edzőileg ez osztja szét a védekezési feladatokat: a jól befejező
    szélső ellen időben ki kell futni és zárni a szöget (a kapus a
    rövid sarkot veszi), a gyenge szélsőre viszont rá lehet engedni a
    lövést — ott a befelé segítés többet ér.

    Visszatérés csapatonként: {"bal"/"jobb": {"shots", "goals",
    "goal_pct"}, "strong", "weak"} — a goal_pct None, ha az adott
    oldalon nem volt lövés; a "strong"/"weak" csak akkor van kitöltve,
    ha mindkét oldalon van legalább WING_SIDE_MIN_SHOTS lövés, és a
    gólarányuk legalább WING_SIDE_GAP_PP százalékponttal tér el.
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
        team = Team.HOME if side == "home" else Team.AWAY
        goal_x = config.attacks_toward_x(team)
        rec = {"bal": {"shots": 0, "goals": 0, "goal_pct": None},
               "jobb": {"shots": 0, "goals": 0, "goal_pct": None},
               "strong": None, "weak": None}
        for sh in xg["shots"]:
            if sh["team"] != side:
                continue
            dist = math.hypot(sh["x"] - goal_x, sh["y"] - cy)
            if abs(sh["y"] - cy) < WING_LATERAL_M or dist > WING_MAX_DIST_M:
                continue
            d = sh["y"] - cy
            if goal_x == 0.0:
                d = -d  # a -x felé támadónál a bal kéz a -y oldal
            band = "bal" if d > 0 else "jobb"
            rec[band]["shots"] += 1
            if sh["outcome"] == "goal":
                rec[band]["goals"] += 1
        for band in ("bal", "jobb"):
            n = rec[band]["shots"]
            if n:
                rec[band]["goal_pct"] = round(
                    100.0 * rec[band]["goals"] / n, 1)
        if all(rec[b]["shots"] >= WING_SIDE_MIN_SHOTS
               for b in ("bal", "jobb")):
            gap = rec["bal"]["goal_pct"] - rec["jobb"]["goal_pct"]
            if abs(gap) >= WING_SIDE_GAP_PP:
                rec["strong"] = "bal" if gap > 0 else "jobb"
                rec["weak"] = "jobb" if gap > 0 else "bal"
        out[side] = rec
    return out


# Lövő-távolság profil: ennyi mért lövés kell egy ember megítéléséhez.
SHOOTER_RANGE_MIN_SHOTS = 3


def shooter_ranges(match: Match,
                   config: Optional[TacticsConfig] = None) -> dict:
    """Lövő-távolság profil: KI LŐ TÁVOLRÓL és ki közelről.

    A lövés-távolság profil (shot_ranges) csapat-szinten mondja meg,
    honnan lőnek — ez játékosonként bontja: lövőnként átlagoljuk a
    kapu-középtől mért lövés-távolságot (a match_xg lövés-listájából).

    Edzőileg ez osztja szét a védőfeladatokat: a távoli lövőre ki kell
    lépni (blokk a lövő-vonalba, mögötte segítővel), a közeli
    befejezőt viszont nem szabad kihúzva várni — ott az elé állás és a
    testes fogadás a válasz, a fal nem bomolhat meg érte.

    Visszatérés csapatonként: {"players": [{"player_id", "jersey",
    "shots", "avg_dist_m"}], "far", "close"} — a lista átlagtávolság
    szerint csökkenő; a "far" a legtávolabbról lövő (ha az átlaga
    SHOT_RANGE_MID_M felett van), a "close" a legközelebbről befejező
    (ha az átlaga SHOT_RANGE_CLOSE_M alatt van), mindkettőhöz legalább
    SHOOTER_RANGE_MIN_SHOTS lövés kell.
    """
    import math

    from ..models.tracking import Team
    from .calibration import COURT_WIDTH_M
    from .xg import match_xg

    config = config or TacticsConfig()
    goal_cy = COURT_WIDTH_M / 2.0
    xg = match_xg(match, config)
    jersey: dict = {}
    for fr in match.frames:
        for p in fr.players:
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)

    out: dict = {}
    for side in ("home", "away"):
        goal_x = config.attacks_toward_x(
            Team.HOME if side == "home" else Team.AWAY)
        acc: dict = {}
        for sh in xg["shots"]:
            if sh["team"] != side or sh["player_id"] is None:
                continue
            dist = math.hypot(sh["x"] - goal_x, sh["y"] - goal_cy)
            rec = acc.setdefault(sh["player_id"], [0, 0.0])
            rec[0] += 1
            rec[1] += dist
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "shots": n, "avg_dist_m": round(d / n, 1)}
                for pid, (n, d) in acc.items()]
        rows.sort(key=lambda r: -r["avg_dist_m"])
        cand = [r for r in rows if r["shots"] >= SHOOTER_RANGE_MIN_SHOTS]
        far = close = None
        if cand:
            if cand[0]["avg_dist_m"] >= SHOT_RANGE_MID_M:
                far = cand[0]
            if cand[-1]["avg_dist_m"] <= SHOT_RANGE_CLOSE_M:
                close = cand[-1]
        out[side] = {"players": rows, "far": far, "close": close}
    return out


# Lepattanó-szerzők: ennyi megszerzett lepattanó kell egy ember
# kiemeléséhez (a heurisztika zaja miatt egy-két eset még nem minta).
REBOUND_MIN = 3


def rebound_winners(match: Match,
                    config: Optional[TacticsConfig] = None) -> dict:
    """Lepattanó-szerzők: KI NYERI a kipattanókat.

    A második roham (second_chance) csapat-szinten mondja meg, hányszor
    szerzik vissza a saját, gólt nem érő lövésüket — ez azt, KI: minden
    nem gólos lövés után megkeressük az ELSŐ azonosított labdabirtokost
    a lepattanó-ablakban, és hozzá írjuk a labdát. Ha a lövő csapata
    szerzi meg, támadó lepattanó; ha a védekező, védekező lepattanó.

    Edzőileg: a támadó lepattanókat gyűjtő ember ellen a blokk után
    azonnal be kell zárni a teret (a kapus kipattanóját a védőnek kell
    kísérnie); a saját oldalon pedig a védekező lepattanó-szerzés a
    kontra-indítás első lépése.

    Visszatérés csapatonként: {"off": [{"player_id", "jersey",
    "rebounds"}], "def": [...], "top_off", "top_def"} — az "off" a
    saját lövés után visszaszerzett labdák, a "def" az ellenfél lövése
    után megszerzettek; a top-ok csak REBOUND_MIN darabtól.
    """
    from .decisions import ball_holder
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = round(SECOND_CHANCE_WINDOW_S * fps)
    frames = match.frames
    idx_of = {f.t: i for i, f in enumerate(frames)}
    jersey: dict = {}

    tally: dict = {"home": {"off": {}, "def": {}},
                   "away": {"off": {}, "def": {}}}
    for e in detect_shots(match, config):
        if e.type != EventType.SHOT:
            continue  # gól után nincs lepattanó
        i0 = idx_of.get(e.t)
        if i0 is None:
            continue
        # Az első azonosított labdabirtokos a lepattanó-ablakban.
        winner = None
        for f in frames[i0 + 1:i0 + 1 + win]:
            h = ball_holder(f, config)
            if h is not None:
                winner = h
                break
        if winner is None:
            continue
        if winner.jersey_number is not None:
            jersey.setdefault(winner.track_id, winner.jersey_number)
        key = "off" if winner.team == e.team else "def"
        side = winner.team.value
        tally[side][key][winner.track_id] = (
            tally[side][key].get(winner.track_id, 0) + 1)

    out: dict = {}
    for side in ("home", "away"):
        rec: dict = {}
        for key in ("off", "def"):
            rows = [{"player_id": pid, "jersey": jersey.get(pid),
                     "rebounds": n}
                    for pid, n in sorted(tally[side][key].items(),
                                         key=lambda kv: -kv[1])]
            rec[key] = rows
            top = (rows[0] if rows and rows[0]["rebounds"] >= REBOUND_MIN
                   else None)
            rec[f"top_{key}"] = top
        out[side] = rec
    return out


# Kihozatal-oldal: ennyi mért támadástól ítélünk, és e feletti
# részarány jelenti, hogy egy oldalon hozzák fel a labdát.
BUILDUP_SIDE_MIN_ATTACKS = 8
BUILDUP_SIDE_SHARE = 50.0


def buildup_side(match: Match,
                 config: Optional[TacticsConfig] = None) -> dict:
    """Kihozatal-oldal: MELYIK OLDALON indítják a támadást.

    A támadás-indítók (attack_starters) azt mondják meg, KI hozza fel a
    labdát, a kapus-indítás oldala (gk_outlet_side) azt, merre kezd a
    kapus — ez azt, hol jön át a labda: minden támadás-szakasz első
    kockájában a labda oldalirányú helyét soroljuk bal / közép / jobb
    sávba (a "bal" a TÁMADÓ bal keze felőli oldal, mint az
    oldal-részrehajlásnál).

    Edzőileg: ha a kihozataluk fele ugyanazon az oldalon jön, oda kell
    szervezni a letámadást és a kettőzést — a másik oldalon addig
    elég egy ember, mert arra nem is indulnak.

    Visszatérés csapatonként: {"attacks", "left", "center", "right",
    "dominant", "share_pct"} — a dominant/share_pct None
    BUILDUP_SIDE_MIN_ATTACKS alatt vagy BUILDUP_SIDE_SHARE alatti
    többségnél; a dominant "bal" / "jobb" / "közép".
    """
    from ..models.tracking import Team
    from .calibration import COURT_WIDTH_M
    from .setplays import segment_attacks

    config = config or TacticsConfig()
    cy = COURT_WIDTH_M / 2.0
    counts = {side: {"left": 0, "center": 0, "right": 0}
              for side in ("home", "away")}
    for seq in segment_attacks(match, config):
        first = next((f for f in seq.frames if f.ball is not None), None)
        if first is None:
            continue
        side = seq.team.value
        d = first.ball.y - cy
        if config.attacks_toward_x(
                Team.HOME if side == "home" else Team.AWAY) == 0.0:
            d = -d  # a -x felé támadónál a bal kéz a -y oldal
        if d > SIDE_BAND_M:
            counts[side]["left"] += 1
        elif d < -SIDE_BAND_M:
            counts[side]["right"] += 1
        else:
            counts[side]["center"] += 1

    out: dict = {}
    for side in ("home", "away"):
        rec = dict(counts[side])
        n = rec["left"] + rec["center"] + rec["right"]
        rec["attacks"] = n
        rec["dominant"] = rec["share_pct"] = None
        if n >= BUILDUP_SIDE_MIN_ATTACKS:
            best = max(("left", "center", "right"), key=lambda k: rec[k])
            pct = 100.0 * rec[best] / n
            if pct >= BUILDUP_SIDE_SHARE:
                rec["dominant"] = {"left": "bal", "right": "jobb",
                                   "center": "közép"}[best]
                rec["share_pct"] = round(pct, 1)
        out[side] = rec
    return out


# Kontra-kíséret: ennyi mért lerohanás kell az ítélethez, a szakasz
# elejéből ennyi másodpercet nézünk, és e feletti / alatti átlagos
# felfutó-szám a tömeges, illetve a magányos kontra jele.
FBS_MIN_BREAKS = 3
FBS_WINDOW_S = 3.0
FBS_MANY = 3.0
FBS_FEW = 1.6


def fast_break_support(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Kontra-kíséret: HÁNYAN FUTNAK FEL a lerohanásaiknál.

    A lerohanás-befejezők (fast_break_finishers) azt mondják meg, ki
    fejezi be a kontrát, az átmenet-támadás (transition_offense) azt,
    mennyi gólt hoz — ez azt, MEKKORA ERŐVEL indulnak: a lerohanásnak
    címkézett szakaszok elején megszámoljuk, hány saját mezőnyjátékos
    van már az ellenfél térfelén.

    Edzőileg: a tömeges kontra ellen mindenkinek azonnal vissza kell
    rendeződnie (a lövés pillanatában már indulni kell hátra); ha csak
    egy-két ember fut fel, elég egy fékező játékos, a többiek nyugodtan
    felállhatnak a felállt védekezésbe.

    Visszatérés csapatonként: {"breaks", "avg_runners", "verdict"} — az
    átlag és a verdict None FBS_MIN_BREAKS alatt; a verdict "tömeges
    kontra" / "magányos kontra" / None.
    """
    from ..models.tracking import Team
    from .setplays import segment_attacks
    from .tactics import COURT_LENGTH_M

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    half = COURT_LENGTH_M / 2.0
    win = round(FBS_WINDOW_S * fps)

    breaks = {(a["team"], a["start_frame"]): a["type"]
              for a in classify_attacks(match, config)
              if a["type"] == AttackType.FAST_BREAK.value}

    acc = {"home": [0, 0.0], "away": [0, 0.0]}
    for seq in segment_attacks(match, config):
        side = seq.team.value
        if (side, seq.start_t) not in breaks:
            continue
        goal_x = config.attacks_toward_x(seq.team)
        counts = []
        for f in seq.frames:
            if f.t > seq.start_t + win:
                break
            n = sum(1 for p in f.players
                    if p.team == seq.team and p.role != "kapus"
                    and abs(p.x - goal_x) <= half)
            counts.append(n)
        if not counts:
            continue
        acc[side][0] += 1
        acc[side][1] += sum(counts) / len(counts)

    out: dict = {}
    for side in ("home", "away"):
        n, total = acc[side]
        rec = {"breaks": n, "avg_runners": None, "verdict": None}
        if n >= FBS_MIN_BREAKS:
            avg = total / n
            rec["avg_runners"] = round(avg, 1)
            if avg >= FBS_MANY:
                rec["verdict"] = "tömeges kontra"
            elif avg <= FBS_FEW:
                rec["verdict"] = "magányos kontra"
        out[side] = rec
    return out


# Két beállós játék: a kaputól ilyen közel számít valaki beálló-zónában
# lévőnek; a támadás akkor "két beállós", ha a kockái ekkora részében
# ketten is ott vannak, és ennyi mért támadástól ítélünk.
DPIV_ZONE_M = 7.5
DPIV_FRAME_SHARE = 40.0
DPIV_MIN_ATTACKS = 8
DPIV_ATTACK_SHARE = 30.0


def double_pivot_usage(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Két beállós játék: MENNYIT JÁTSZANAK két emberrel a 6 m-en.

    A beálló-terhelés (pivot_usage) azt mondja meg, mennyi támadás megy
    át a beállón, a beálló-oldal (pivot_side) azt, hol dolgozik — ez
    azt, HÁNY emberrel: támadás-szakaszonként megnézzük, a kockák
    mekkora részében van legalább KÉT támadó a beálló-zónában (a
    kaputól DPIV_ZONE_M-en belül).

    Edzőileg: a két beállós támadás ellen a fal középső részét
    tömöríteni kell — a két középső védő nem adhatja át egymásnak a
    beállókat, és a szélső védők feljebb léphetnek, mert a szélek
    üresen maradnak; ha viszont alig játszanak két beállóval, a segítő
    védő nyugodtan befelé dolgozhat.

    Visszatérés csapatonként: {"attacks", "double_attacks",
    "share_pct", "verdict"} — a share_pct/verdict None
    DPIV_MIN_ATTACKS alatt; a verdict "két beállóval játszanak" /
    "egy beállós felállás" / None.
    """
    import math

    from .calibration import COURT_WIDTH_M
    from .setplays import segment_attacks

    config = config or TacticsConfig()
    cy = COURT_WIDTH_M / 2.0

    out: dict = {side: {"attacks": 0, "double_attacks": 0,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for seq in segment_attacks(match, config):
        side = seq.team.value
        goal_x = config.attacks_toward_x(seq.team)
        inside = 0
        for fr in seq.frames:
            n = sum(1 for p in fr.players
                    if p.team == seq.team and p.role != "kapus"
                    and math.hypot(p.x - goal_x, p.y - cy) <= DPIV_ZONE_M)
            if n >= 2:
                inside += 1
        rec = out[side]
        rec["attacks"] += 1
        if seq.frames and (100.0 * inside / len(seq.frames)
                           >= DPIV_FRAME_SHARE):
            rec["double_attacks"] += 1

    for side in ("home", "away"):
        rec = out[side]
        if rec["attacks"] >= DPIV_MIN_ATTACKS:
            share = 100.0 * rec["double_attacks"] / rec["attacks"]
            rec["share_pct"] = round(share, 1)
            if share >= DPIV_ATTACK_SHARE:
                rec["verdict"] = "két beállóval játszanak"
            elif share <= 10.0:
                rec["verdict"] = "egy beállós felállás"
    return out


# Áttörő játékosok: ennyi betöréstől emeljük ki az embert, és a
# gól-párosítás ablaka a támadás végéhez képest.
BTP_MIN_ENTRIES = 3


def breakthrough_players(match: Match,
                         config: Optional[TacticsConfig] = None) -> dict:
    """Áttörő játékosok: KI JUT BE labdával a falba.

    A betörés-folyosók (breakthrough_lanes) azt mondják meg, MELYIK
    SÁVBAN lyukas a fal — ez azt, KI viszi be a labdát: minden
    támadás-szakaszban megnézzük, mely labdabirtokosok lépnek be a
    kapu BREAK_IN_DIST_M-es körzetébe (szakaszonként emberenként
    egyszer számolva), és hány ilyen betörésből lett gól.

    Edzőileg: az áttörő ember ellen duplázni kell — a védőjének
    segítőt kell kapnia, és a betörés vonalát a testtel kell zárni,
    mert ő az, aki a falat szétnyitja a többieknek.

    Visszatérés csapatonként: {"entries", "players": [{"player_id",
    "jersey", "entries", "goals"}], "top"} — a lista betörés szerint
    csökkenő; a "top" az első játékos, ha legalább BTP_MIN_ENTRIES
    betörése van.
    """
    import math

    from ..models.tracking import Team
    from .calibration import COURT_WIDTH_M
    from .decisions import ball_holder
    from .defense import BREAK_IN_DIST_M
    from .event_detection import EventType, detect_shots
    from .setplays import segment_attacks

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    tail = round(ATTACK_TAIL_S * fps)
    gy = COURT_WIDTH_M / 2.0
    goals = [(e.t, e.team.value) for e in detect_shots(match, config)
             if e.type == EventType.GOAL]

    jersey: dict = {}
    tally: dict = {"home": {}, "away": {}}
    for seq in segment_attacks(match, config):
        side = seq.team.value
        goal_x = config.attacks_toward_x(seq.team)
        scored = any(tm == side
                     and seq.start_t <= t <= seq.end_t + tail
                     for (t, tm) in goals)
        seen: set = set()
        for fr in seq.frames:
            h = ball_holder(fr, config)
            if h is None or h.team != seq.team or h.role == "kapus":
                continue
            if h.track_id in seen:
                continue
            if math.hypot(h.x - goal_x, h.y - gy) > BREAK_IN_DIST_M:
                continue
            seen.add(h.track_id)
            if h.jersey_number is not None:
                jersey.setdefault(h.track_id, h.jersey_number)
            rec = tally[side].setdefault(h.track_id,
                                         {"entries": 0, "goals": 0})
            rec["entries"] += 1
            if scored:
                rec["goals"] += 1

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "entries": r["entries"], "goals": r["goals"]}
                for pid, r in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1]["entries"])]
        top = (rows[0] if rows and rows[0]["entries"] >= BTP_MIN_ENTRIES
               else None)
        out[side] = {"entries": sum(r["entries"] for r in rows),
                     "players": rows, "top": top}
    return out


# Lövés-távolság esése: félidőnként ennyi mért lövés kell, és ekkora
# (méteres) növekedés számít érdemi kifelé szorulásnak.
SDF_MIN_SHOTS = 4
SDF_GAP_M = 1.0


def shot_distance_fade(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Lövés-távolság esése: KIFELÉ SZORULNAK-E a hajrára.

    A lövőerő-esés (shot_power_fade) a lövés SEBESSÉGÉT méri
    félidőnként, a befejezés-esés (finish_fade) a gólarányt — ez a
    HELYET: félidőnként átlagoljuk a lövések kapu-távolságát.

    Edzőileg: ha a második félidőben érdemben kijjebb kerülnek a
    lövéseik, elfogy az erő a betörésekhez — a hajrában elég a
    lövő-vonalba lépni, mert a közeli befejezést már nem vállalják; ha
    marad a távolság, a fáradás nem a lövés-választásukon látszik.

    Visszatérés csapatonként: {"fh_shots", "fh_avg_m", "sh_shots",
    "sh_avg_m", "gap_m", "verdict"} — az átlagok és a gap None, ha
    nincs félidő-jel vagy kevés a lövés; a verdict "kifelé szorulnak"
    / "bent maradnak" / None.
    """
    import math

    from ..models.tracking import Team
    from .calibration import COURT_WIDTH_M
    from .halftime import detect_halftime
    from .xg import match_xg

    config = config or TacticsConfig()
    cy = COURT_WIDTH_M / 2.0
    empty = {"fh_shots": 0, "fh_avg_m": None, "sh_shots": 0,
             "sh_avg_m": None, "gap_m": None, "verdict": None}
    out = {"home": dict(empty), "away": dict(empty)}
    ht = detect_halftime(match)
    if ht is None:
        return out

    xg = match_xg(match, config)
    for side in ("home", "away"):
        goal_x = config.attacks_toward_x(
            Team.HOME if side == "home" else Team.AWAY)
        halves: dict = {"fh": [], "sh": []}
        for sh in xg["shots"]:
            if sh["team"] != side:
                continue
            dist = math.hypot(sh["x"] - goal_x, sh["y"] - cy)
            halves["fh" if sh["t"] <= ht else "sh"].append(dist)
        rec = out[side]
        rec["fh_shots"] = len(halves["fh"])
        rec["sh_shots"] = len(halves["sh"])
        if (len(halves["fh"]) >= SDF_MIN_SHOTS
                and len(halves["sh"]) >= SDF_MIN_SHOTS):
            fh_avg = sum(halves["fh"]) / len(halves["fh"])
            sh_avg = sum(halves["sh"]) / len(halves["sh"])
            rec["fh_avg_m"] = round(fh_avg, 1)
            rec["sh_avg_m"] = round(sh_avg, 1)
            rec["gap_m"] = round(sh_avg - fh_avg, 1)
            if rec["gap_m"] >= SDF_GAP_M:
                rec["verdict"] = "kifelé szorulnak"
            elif rec["gap_m"] <= -SDF_GAP_M:
                rec["verdict"] = "bent maradnak"
    return out


# Elzárók: ennyi felismert elzárástól emeljük ki az embert.
SCS_MIN_SCREENS = 3


def screen_setters(match: Match,
                   config: Optional[TacticsConfig] = None) -> dict:
    """Elzárók: KI ÁLL ELZÁRÁSBA a lövőik előtt.

    Az elzárás-használat (screen_usage) azt mondja meg, a lövéseik
    mekkora része jön elzárásból — ez azt, KI zár el: lövésenként a
    lövő őrzője mellett álló társat (a SCREEN_DIST_M-en belüli
    csapattársat) jegyezzük fel elzáróként.

    Edzőileg: az elzáróra kell a váltás-kommunikáció — az ő oldalán
    hangosan kell váltani vagy átcsúszni, és őt elölről kell fogni,
    mert nélküle a lövőjük nem marad tisztán.

    Visszatérés csapatonként: {"screens", "players": [{"player_id",
    "jersey", "screens"}], "top"} — a "top" az első játékos, ha
    legalább SCS_MIN_SCREENS elzárása van.
    """
    import math

    from .xg import match_xg

    config = config or TacticsConfig()
    idx_of = {f.t: i for i, f in enumerate(match.frames)}
    jersey: dict = {}
    tally: dict = {"home": {}, "away": {}}
    for sh in match_xg(match, config).get("shots", []):
        pid = sh.get("player_id")
        i0 = idx_of.get(sh["t"])
        if pid is None or i0 is None:
            continue
        f = match.frames[i0]
        shooter = next((p for p in f.players if p.track_id == pid), None)
        if shooter is None:
            continue
        marker = None
        best = SCREEN_MARKER_MAX_M
        for d in f.players:
            if d.team is None or d.team == shooter.team:
                continue
            dist = math.hypot(d.x - shooter.x, d.y - shooter.y)
            if dist <= best:
                marker, best = d, dist
        if marker is None:
            continue  # szabad lövés: nincs kit elzárni
        # Az elzáró: az őrző mellett álló (nem lövő) csapattárs.
        setter = None
        best_s = SCREEN_DIST_M
        for p in f.players:
            if p.team != shooter.team or p.track_id == pid:
                continue
            d = math.hypot(p.x - marker.x, p.y - marker.y)
            if d <= best_s:
                setter, best_s = p, d
        if setter is None:
            continue
        if setter.jersey_number is not None:
            jersey.setdefault(setter.track_id, setter.jersey_number)
        side = sh["team"]
        tally[side][setter.track_id] = (
            tally[side].get(setter.track_id, 0) + 1)

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "screens": n}
                for pid, n in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1])]
        top = (rows[0] if rows and rows[0]["screens"] >= SCS_MIN_SCREENS
               else None)
        out[side] = {"screens": sum(r["screens"] for r in rows),
                     "players": rows, "top": top}
    return out


# Kockázatos passzolók: ennyi hosszú kísérlettől ítélünk emberenként,
# és e feletti eladás-arány jelenti, hogy nála elfogható a labda.
RISKY_MIN_TRIES = 4
RISKY_TO_PCT = 40.0


def risky_passers(match: Match,
                  config: Optional[TacticsConfig] = None) -> dict:
    """Kockázatos passzolók: KINEK a hosszú labdái foghatók el.

    A passz-kockázat (pass_risk) csapat-szinten mondja meg, a hosszú
    passzaik gyakrabban vesznek-e el — ez játékosonként bontja: a
    hosszú (PASSRISK_LONG_M feletti) továbbítási kísérleteket és
    azok közül az eladásokat a kiinduló játékoshoz írjuk.

    Edzőileg: az ő hosszú passzsávjába kell beállni — a letámadás és
    a sávba lépés nála azonnal labdát hoz, a saját oldalon pedig az
    ő passz-technikája (feszes, előre vezetett labda) az edzés-téma.

    Visszatérés csapatonként: {"players": [{"player_id", "jersey",
    "tries", "turnovers"}], "top"} — a lista eladás-szám szerint
    csökkenő; a "top" az a játékos, akinek legalább RISKY_MIN_TRIES
    hosszú kísérlete van, és az eladás-aránya eléri a RISKY_TO_PCT-t.
    """
    import math

    from .event_detection import EventType, detect_events

    config = config or TacticsConfig()
    idx_of = {f.t: i for i, f in enumerate(match.frames)}
    jersey: dict = {}
    tally: dict = {"home": {}, "away": {}}
    for e in detect_events(match, config):
        if e.type not in (EventType.PASS, EventType.TURNOVER):
            continue
        if e.player_id is None:
            continue
        i0 = idx_of.get(e.t)
        if i0 is None:
            continue
        f = match.frames[i0]
        by_id = {p.track_id: p for p in f.players}
        passer = by_id.get(e.player_id)
        if passer is None:
            continue
        if e.type == EventType.PASS:
            rid = (e.detail or {}).get("receiver_id")
            taker = by_id.get(rid) if rid is not None else None
        else:
            taker = None
            if f.ball is not None:
                best = None
                for p in f.players:
                    if p.team is None or p.team == e.team:
                        continue
                    d = math.hypot(p.x - f.ball.x, p.y - f.ball.y)
                    if best is None or d < best:
                        taker, best = p, d
        if taker is None:
            continue
        if math.hypot(taker.x - passer.x,
                      taker.y - passer.y) < PASSRISK_LONG_M:
            continue  # rövid passz: nem ebbe a képbe tartozik
        if passer.jersey_number is not None:
            jersey.setdefault(passer.track_id, passer.jersey_number)
        rec = tally[e.team.value].setdefault(passer.track_id,
                                             {"tries": 0,
                                              "turnovers": 0})
        rec["tries"] += 1
        if e.type == EventType.TURNOVER:
            rec["turnovers"] += 1

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "tries": r["tries"], "turnovers": r["turnovers"]}
                for pid, r in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1]["turnovers"])]
        top = None
        for row in rows:
            if row["tries"] >= RISKY_MIN_TRIES and (
                    100.0 * row["turnovers"] / row["tries"]
                    >= RISKY_TO_PCT):
                top = row
                break
        out[side] = {"players": rows, "top": top}
    return out


# Felhozatal-idő: ennyi mért birtoklás kell az ítélethez, ekkora
# ablakban keressük a térfél-átlépést, és e feletti / alatti átlagidő a
# lassú, illetve a gyors felhozatal jele.
BUT_MIN_CASES = 5
BUT_MAX_S = 20.0
BUT_SLOW_S = 7.0
BUT_FAST_S = 4.0


def buildup_time(match: Match,
                 config: Optional[TacticsConfig] = None) -> dict:
    """Felhozatal-idő: MENNYI IDŐ ALATT érnek a támadó térfélre.

    A középkezdés-tempó (restart_speed) csak a KAPOTT GÓL utáni
    újraindítást méri, a kihozatal-oldal (buildup_side) azt, hol jön
    át a labda — ez azt, MILYEN GYORSAN: minden birtoklás-kezdéstől
    mérjük, hány másodperc múlva lép át a labda a támadó térfélre.

    Edzőileg: a lassan felhozó csapat ellen van idő rendezetten
    felállni — ott a fal szervezése dönt, nem a visszafutás; a gyorsan
    felhozó ellen viszont a lövés pillanatában már indulni kell hátra,
    és kijelölt fékező ember kell.

    Visszatérés csapatonként: {"cases", "avg_s", "verdict"} — az
    avg_s/verdict None BUT_MIN_CASES alatt; a verdict "lassan hozzák
    fel" / "gyorsan hozzák fel" / None.
    """
    from ..models.tracking import Team
    from .decisions import ball_holder
    from .tactics import COURT_LENGTH_M

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    frames = match.frames
    half = COURT_LENGTH_M / 2.0
    horizon = round(BUT_MAX_S * fps)

    # Birtoklás-kezdések: az új birtokos csapat első kockája.
    starts: list = []
    prev = None
    for i, f in enumerate(frames):
        h = ball_holder(f, config)
        if h is None:
            continue
        if prev is None or h.team != prev:
            starts.append((i, h.team))
        prev = h.team

    acc = {"home": [0, 0.0], "away": [0, 0.0]}
    for idx, team in starts:
        goal_x = config.attacks_toward_x(team)
        # Már a támadó térfélen kezdődő birtoklás (labdaszerzés elöl):
        # ott nincs mit felhozni.
        f0 = frames[idx]
        if f0.ball is not None and abs(f0.ball.x - goal_x) <= half:
            continue
        cross_i = None
        for j in range(idx, min(len(frames), idx + horizon)):
            b = frames[j].ball
            if b is not None and abs(b.x - goal_x) <= half:
                cross_i = j
                break
        if cross_i is None:
            continue  # nem ért át az ablakban: nem mérjük
        acc[team.value][0] += 1
        acc[team.value][1] += (frames[cross_i].t - f0.t) / fps

    out: dict = {}
    for side in ("home", "away"):
        n, total = acc[side]
        rec = {"cases": n, "avg_s": None, "verdict": None}
        if n >= BUT_MIN_CASES:
            avg = total / n
            rec["avg_s"] = round(avg, 1)
            if avg >= BUT_SLOW_S:
                rec["verdict"] = "lassan hozzák fel"
            elif avg <= BUT_FAST_S:
                rec["verdict"] = "gyorsan hozzák fel"
        out[side] = rec
    return out


# Lerohanás-hatékonyság: ennyi mért lerohanás kell az ítélethez, és e
# feletti / alatti gólarány az éles, illetve az elpuskázott kontra
# jele.
FBC_MIN_BREAKS = 5
FBC_SHARP_PCT = 65.0
FBC_WASTE_PCT = 35.0


def fast_break_conversion(match: Match,
                          config: Optional[TacticsConfig] = None) -> dict:
    """Lerohanás-hatékonyság: MENNYI LESZ GÓL a kontráikból.

    A lerohanás-arány (fast_break_pct) azt mondja meg, milyen gyakran
    kontráznak, a kontra-befejezők (fast_break_finishers) azt, ki
    zárja le őket — ez azt, MEGY-E BE: a lerohanásnak címkézett
    támadás-szakaszokat nézzük, és megszámoljuk, hányat zárt le a
    csapat gólja.

    Edzőileg: aki élesen fejezi be a kontrát, ott a visszarendeződés
    fegyelme dönt — kijelölt fékező ember, és lövés után senki nem
    marad elöl a kipattanóra; aki elpuskázza, annál a kontra
    ajándék: nyugodtan rá lehet engedni őket, mert a felállt
    támadásuk a veszélyesebb.

    Visszatérés csapatonként: {"breaks", "goals", "share_pct",
    "verdict"} — a share_pct/verdict None FBC_MIN_BREAKS alatt; a
    verdict "élesen fejezik be a kontrát" / "elpuskázzák a kontrát" /
    None.
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    tail = round(ATTACK_TAIL_S * fps)
    goals = [(e.t, e.team.value) for e in detect_shots(match, config)
             if e.type == EventType.GOAL]

    out: dict = {side: {"breaks": 0, "goals": 0, "share_pct": None,
                        "verdict": None} for side in ("home", "away")}
    for a in classify_attacks(match, config):
        if a["type"] != AttackType.FAST_BREAK.value:
            continue
        side = a["team"]
        rec = out[side]
        rec["breaks"] += 1
        if any(tm == side and a["start_frame"] <= t <= a["end_frame"] + tail
               for (t, tm) in goals):
            rec["goals"] += 1

    for side in ("home", "away"):
        rec = out[side]
        if rec["breaks"] >= FBC_MIN_BREAKS:
            share = 100.0 * rec["goals"] / rec["breaks"]
            rec["share_pct"] = round(share, 1)
            if share >= FBC_SHARP_PCT:
                rec["verdict"] = "élesen fejezik be a kontrát"
            elif share <= FBC_WASTE_PCT:
                rec["verdict"] = "elpuskázzák a kontrát"
    return out


# Visszahozott támadások: a kapu-középponttól ennyire belépve számít
# betörésnek, ennyire kijőve zárul az epizód, ennyi belépés kell az
# ítélethez, és e feletti / alatti visszahozás-arány a türelmes,
# illetve az első betörésből lezáró csapat jele.
PB_ENTRY_R_M = 9.0
PB_OUT_R_M = 11.0
PB_MIN_ENTRIES = 6
PB_PATIENT_PCT = 45.0
PB_DIRECT_PCT = 15.0


def pullback_rate(match: Match,
                  config: Optional[TacticsConfig] = None) -> dict:
    """Visszahozott támadások: LEZÁRJÁK vagy ÚJRAJÁRATJÁK a betörést.

    A betörés-folyosók (breakthrough_lanes) azt mondják meg, hol lép
    be a labda a 9 méteren belülre — ez azt, MI LESZ BELŐLE: minden
    belépés-epizódnál megnézzük, lövéssel zárul-e, vagy a csapat
    lövés nélkül visszahozza a labdát a 11 méteren kívülre
    (türelmes újrajáratás). A labdavesztéssel záruló epizódok egyik
    oldalra sem számítanak.

    Edzőileg: a sokat visszahozó csapat ellen a fal kivárhat — nem
    kell az első betörésre rámozdulni, jön a passzív jel; az első
    betörésből lezáró csapat ellen viszont pont az első belépést kell
    megállítani — korai besegítés, akár korai szabálytalanság a
    9-esen.

    Visszatérés csapatonként: {"entries", "pullbacks", "shots",
    "pull_pct", "verdict"} — a pull_pct/verdict None PB_MIN_ENTRIES
    alatt; a verdict "behúzzák, aztán visszahozzák" / "az első
    betörésből lezárnak" / None.
    """
    import math

    from .calibration import COURT_WIDTH_M
    from .decisions import ball_holder
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    cy = COURT_WIDTH_M / 2.0
    shots = [(e.t, e.team.value) for e in detect_shots(match, config)
             if e.type in (EventType.SHOT, EventType.GOAL)]

    out = {side: {"entries": 0, "pullbacks": 0, "shots": 0,
                  "pull_pct": None, "verdict": None}
           for side in ("home", "away")}

    holder_team = None
    entry_team = None   # folyamatban lévő belépés-epizód csapata
    entry_t = None
    for f in match.frames:
        h = ball_holder(f, config)
        if h is not None:
            holder_team = h.team
        b = f.ball
        if b is None or holder_team is None:
            continue
        goal_x = config.attacks_toward_x(holder_team)
        d = math.hypot(b.x - goal_x, b.y - cy)
        if entry_team is None:
            if d <= PB_ENTRY_R_M:
                entry_team = holder_team
                entry_t = f.t
        else:
            if holder_team != entry_team:
                entry_team = None      # labdavesztés bent: nem számít
                continue
            if d >= PB_OUT_R_M:
                rec = out[entry_team.value]
                rec["entries"] += 1
                if any(entry_t <= t <= f.t and tm == entry_team.value
                       for (t, tm) in shots):
                    rec["shots"] += 1
                else:
                    rec["pullbacks"] += 1
                entry_team = None

    for side in ("home", "away"):
        rec = out[side]
        if rec["entries"] >= PB_MIN_ENTRIES:
            pct = 100.0 * rec["pullbacks"] / rec["entries"]
            rec["pull_pct"] = round(pct, 1)
            if pct >= PB_PATIENT_PCT:
                rec["verdict"] = "behúzzák, aztán visszahozzák"
            elif pct <= PB_DIRECT_PCT:
                rec["verdict"] = "az első betörésből lezárnak"
    return out


# Szorult játék: állapotonként ennyi mérhető kocka kell az átlaghoz, és
# ekkora szélesség-különbség jelenti a hátrányban beszűkülő, illetve
# kinyíló támadást.
WBS_MIN_FRAMES = 100
WBS_GAP_M = 2.0


def width_by_score(match: Match,
                   config: Optional[TacticsConfig] = None) -> dict:
    """Szorult játék: HÁTRÁNYBAN mennyire húzzák szét a pályát.

    A támadás-szélesség (attack_width) a teljes meccs átlagát adja —
    ez állás szerint bontja: külön mérjük a támadók oldalirányú
    terjedelmét, amikor a csapat hátrányban van, és amikor nem. A
    szorult helyzet megmutatja a csapat reflexét: van, aki hátrányban
    egy csatornába szűkül (erőltetett egyéni megoldások), és van, aki
    pont ilyenkor nyitja szélesre a játékot.

    Edzőileg: a hátrányban beszűkülő csapat ellen vezetésnél
    tömöríteni kell a falat — a szélsőik kikapcsolódnak maguktól; a
    hátrányban kinyíló ellen vezetésnél éppen a szélső-védelem és a
    kifutás dönt, mert onnan jön a visszakapaszkodásuk.

    Visszatérés csapatonként: {"trail_frames", "trail_avg_m",
    "other_frames", "other_avg_m", "verdict"} — az átlagok None
    WBS_MIN_FRAMES alatt; a verdict "hátrányban beszűkülnek" /
    "hátrányban kinyílnak" / None.
    """
    from ..models.tracking import Team
    from .event_detection import EventType, detect_shots
    from .tactics import possession_team

    config = config or TacticsConfig()
    goals = sorted((e.t, e.team.value) for e in detect_shots(match, config)
                   if e.type == EventType.GOAL)

    acc = {side: {"trail": [0, 0.0], "other": [0, 0.0]}
           for side in ("home", "away")}
    gi = 0
    score = {"home": 0, "away": 0}
    for fr in match.frames:
        while gi < len(goals) and goals[gi][0] <= fr.t:
            score[goals[gi][1]] += 1
            gi += 1
        poss = possession_team(fr, config)
        if poss is None:
            continue
        goal_x = config.attacks_toward_x(poss)
        ys = [p.y for p in fr.players
              if p.team == poss and p.role != "kapus"
              and abs(p.x - goal_x) <= 15.0]
        if len(ys) < 3:
            continue
        side = poss.value
        other = "away" if side == "home" else "home"
        bucket = "trail" if score[side] < score[other] else "other"
        rec = acc[side][bucket]
        rec[0] += 1
        rec[1] += max(ys) - min(ys)

    out: dict = {}
    for side in ("home", "away"):
        t_n, t_sum = acc[side]["trail"]
        o_n, o_sum = acc[side]["other"]
        rec = {"trail_frames": t_n, "trail_avg_m": None,
               "other_frames": o_n, "other_avg_m": None,
               "verdict": None}
        if t_n >= WBS_MIN_FRAMES and o_n >= WBS_MIN_FRAMES:
            t_avg, o_avg = t_sum / t_n, o_sum / o_n
            rec["trail_avg_m"] = round(t_avg, 1)
            rec["other_avg_m"] = round(o_avg, 1)
            if o_avg - t_avg >= WBS_GAP_M:
                rec["verdict"] = "hátrányban beszűkülnek"
            elif t_avg - o_avg >= WBS_GAP_M:
                rec["verdict"] = "hátrányban kinyílnak"
        out[side] = rec
    return out


# Kontra-forrás: ekkora ablakban nézünk vissza a lerohanás indulása
# előtt, ennyi mért lerohanás kell az ítélethez, és e feletti
# részarány emeli ki a fő forrást.
BSRC_LOOKBACK_S = 5.0
BSRC_MIN_BREAKS = 4
BSRC_TOP_PCT = 50.0


def break_sources(match: Match,
                  config: Optional[TacticsConfig] = None) -> dict:
    """Kontra-forrás: MIBŐL INDUL a lerohanásuk.

    A lerohanás-hatékonyság (fast_break_conversion) azt méri, mennyi
    lesz gól a kontrákból — ez azt, honnan jönnek: minden lerohanás
    indulása előtti BSRC_LOOKBACK_S másodpercben megnézzük, mi
    történt — az ellenfél kapura lövését védte a kapus ("védés"), az
    ellenfél mellé lőtt ("kihagyott lövés"), vagy mezőnyben szereztek
    labdát ("labdaszerzés").

    Edzőileg forrásonként más a recept: a védésből induló kontra
    ellen a lövés pillanatában kell hátraindulni (a kapus-indítás
    sávját zárva); a kihagyott lövésből induló ellen a lepattanó
    fegyelme és a kapus-kidobás lassítása dönt; a labdaszerzésből
    induló ellen a labdabiztonság — átmenetben tiltott a keresztpassz.

    Visszatérés csapatonként: {"breaks", "sources": {"védés" /
    "kihagyott lövés" / "labdaszerzés": darab}, "top", "verdict"} — a
    top/verdict None BSRC_MIN_BREAKS alatt vagy BSRC_TOP_PCT alatti
    részaránynál; a verdict "a kontráik főleg ebből indulnak:
    <forrás>" / None.
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    look = round(BSRC_LOOKBACK_S * fps)
    shots = [(e.t, e.team.value, e.type,
              (e.detail or {}).get("outcome"))
             for e in detect_shots(match, config)
             if e.type in (EventType.SHOT, EventType.GOAL)]

    out = {side: {"breaks": 0, "sources": {}, "top": None,
                  "verdict": None} for side in ("home", "away")}
    for a in classify_attacks(match, config):
        if a["type"] != AttackType.FAST_BREAK.value:
            continue
        side = a["team"]
        other = "away" if side == "home" else "home"
        rec = out[side]
        rec["breaks"] += 1
        source = "labdaszerzés"
        for (t, tm, typ, outc) in shots:
            if tm != other:
                continue
            if a["start_frame"] - look <= t <= a["start_frame"]:
                source = ("védés" if outc == "save"
                          else "kihagyott lövés")
                break
        rec["sources"][source] = rec["sources"].get(source, 0) + 1

    for side in ("home", "away"):
        rec = out[side]
        if rec["breaks"] >= BSRC_MIN_BREAKS and rec["sources"]:
            items = sorted(rec["sources"].items(),
                           key=lambda kv: -kv[1])
            src, n = items[0]
            tie = len(items) > 1 and items[1][1] == n
            if 100.0 * n / rec["breaks"] >= BSRC_TOP_PCT and not tie:
                rec["top"] = {"source": src, "breaks": n}
                rec["verdict"] = ("a kontráik főleg ebből indulnak: "
                                  + src)
    return out


# Fal-magasság elleni játék: e feletti átlagos fal-magasság számít
# felfutó falnak, vödrönként ennyi támadás kell az ítélethez, és
# ekkora (százalékpontos) gólarány-különbség dönt.
AVW_HIGH_M = 8.0
AVW_MIN_ATTACKS = 5
AVW_GAP_PP = 20.0


def attack_vs_wall_height(match: Match,
                          config: Optional[TacticsConfig] = None) -> dict:
    """Fal-magasság elleni játék: MEGBÜNTETIK-E A FELFUTÓ FALAT.

    A vonal-magasság (defensive_line_height) a falat írja le — ez a
    támadó válaszát: minden támadás-szakasznál megmérjük az ellenfél
    falának átlagos magasságát, és külön gólarányt számolunk a
    felfutó (AVW_HIGH_M feletti) és a mély fal ellen vívott
    támadásokra.

    Edzőileg: akit a felfutó fal megfog, az ellen bátran ki lehet
    lépni és magasan védekezni — nincs válaszuk a nyomásra; aki a
    felfutó falat megbünteti (mögé betör, átemeli), az ellen a mély,
    kompakt fal a biztonságos terv.

    Visszatérés csapatonként (a TÁMADÓ oldal): {"high": {"attacks",
    "goals", "goal_pct"}, "deep": {...}, "verdict"} — a pct-k/verdict
    None a vödrönkénti AVW_MIN_ATTACKS alatt; a verdict "a felfutó
    fal megfogja őket" / "a felfutó falat megbüntetik" / None.
    """
    from ..models.tracking import Team
    from .event_detection import EventType, detect_shots
    from .setplays import segment_attacks
    from .tactics import COURT_LENGTH_M

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    tail = round(ATTACK_TAIL_S * fps)
    half = COURT_LENGTH_M / 2.0
    goals = [(e.t, e.team.value) for e in detect_shots(match, config)
             if e.type == EventType.GOAL]

    out = {side: {"high": {"attacks": 0, "goals": 0, "goal_pct": None},
                  "deep": {"attacks": 0, "goals": 0, "goal_pct": None},
                  "verdict": None} for side in ("home", "away")}
    for seq in segment_attacks(match, config):
        side = seq.team.value
        deff = Team.AWAY if seq.team == Team.HOME else Team.HOME
        own_x = config.own_goal_x(deff)
        depths = []
        for f in seq.frames:
            ds = [abs(p.x - own_x) for p in f.players
                  if p.team == deff and p.role != "kapus"
                  and abs(p.x - own_x) <= half]
            if ds:
                depths.append(sum(ds) / len(ds))
        if not depths:
            continue
        bucket = ("high" if sum(depths) / len(depths) >= AVW_HIGH_M
                  else "deep")
        rec = out[side][bucket]
        rec["attacks"] += 1
        if any(tm == side and seq.start_t <= t <= seq.end_t + tail
               for (t, tm) in goals):
            rec["goals"] += 1

    for side in ("home", "away"):
        rec = out[side]
        h, d = rec["high"], rec["deep"]
        if (h["attacks"] >= AVW_MIN_ATTACKS
                and d["attacks"] >= AVW_MIN_ATTACKS):
            h["goal_pct"] = round(100.0 * h["goals"] / h["attacks"], 1)
            d["goal_pct"] = round(100.0 * d["goals"] / d["attacks"], 1)
            gap = h["goal_pct"] - d["goal_pct"]
            if gap <= -AVW_GAP_PP:
                rec["verdict"] = "a felfutó fal megfogja őket"
            elif gap >= AVW_GAP_PP:
                rec["verdict"] = "a felfutó falat megbüntetik"
    return out


# Elzárás-páros: ennyi közös elzárás-lövés kell a bejáratott pároshoz.
SCP_MIN_PAIR = 3


def screen_pairs(match: Match,
                 config: Optional[TacticsConfig] = None) -> dict:
    """Elzárás-páros: KI ZÁR KINEK — a bejáratott elzáró-lövő kettős.

    Az elzárás-emberek (screen_setters) azt mondják meg, ki zár a
    legtöbbet — ez azt, KINEK: minden elzárásból leadott lövésnél az
    (elzáró, lövő) párost jegyezzük fel. A kézilabdában az elzárás
    kettőn múlik: ha ugyanaz a páros dolgozik újra és újra, a
    kettősük bejáratott figura.

    Edzőileg: a bejáratott páros ellen a védekezés is párban készül —
    az elzáró őrzője előre szól, a lövő őrzője pedig az elzárás
    ELŐTT lép ki, hogy ne szoruljon mögé; a saját párosunkat pedig
    védeni kell a kiszámíthatóságtól: másik oldalra is járjon a
    figura.

    Visszatérés csapatonként: {"pairs": [{"setter_id", "shooter_id",
    "shots"}], "top", "verdict"} — a top/verdict None SCP_MIN_PAIR
    közös lövés alatt; a verdict "bejáratott elzárás-párosuk van" /
    None.
    """
    import math

    from .xg import match_xg

    config = config or TacticsConfig()
    idx_of = {f.t: i for i, f in enumerate(match.frames)}
    tally: dict = {"home": {}, "away": {}}
    for sh in match_xg(match, config).get("shots", []):
        pid = sh.get("player_id")
        i0 = idx_of.get(sh["t"])
        if pid is None or i0 is None:
            continue
        f = match.frames[i0]
        shooter = next((p for p in f.players if p.track_id == pid), None)
        if shooter is None:
            continue
        marker = None
        best = SCREEN_MARKER_MAX_M
        for d in f.players:
            if d.team is None or d.team == shooter.team:
                continue
            dist = math.hypot(d.x - shooter.x, d.y - shooter.y)
            if dist <= best:
                marker, best = d, dist
        if marker is None:
            continue
        setter = None
        best_s = SCREEN_DIST_M
        for p in f.players:
            if p.team != shooter.team or p.track_id == pid:
                continue
            d = math.hypot(p.x - marker.x, p.y - marker.y)
            if d <= best_s:
                setter, best_s = p, d
        if setter is None:
            continue
        side = sh["team"]
        key = (setter.track_id, pid)
        tally[side][key] = tally[side].get(key, 0) + 1

    out: dict = {}
    for side in ("home", "away"):
        pairs = [{"setter_id": s_, "shooter_id": sh_, "shots": n}
                 for (s_, sh_), n in sorted(tally[side].items(),
                                            key=lambda kv: -kv[1])]
        top = (pairs[0] if pairs and pairs[0]["shots"] >= SCP_MIN_PAIR
               else None)
        verdict = ("bejáratott elzárás-párosuk van"
                   if top is not None else None)
        out[side] = {"pairs": pairs, "top": top, "verdict": verdict}
    return out


# Labda-forgatás iránya: ennyi oldalpassz kell az ítélethez, és e
# feletti részarány jelenti az egyirányú forgatást.
CIR_MIN_PASSES = 20
CIR_DOM_PCT = 60.0


def circulation_direction(match: Match,
                          config: Optional[TacticsConfig] = None) -> dict:
    """Labda-forgatás iránya: MERRE JÁRATJÁK a labdát felállt támadásban.

    A passz-irány (pass_direction) az előre-hátra tengelyt méri — ez
    az oldalirányt: minden érdemi oldalpassznál megnézzük, a támadó
    szemszögéből balra vagy jobbra megy-e a labda. A legtöbb csapat
    forgása aszimmetrikus — a fő lövő oldalára tolják a játékot.

    Edzőileg: az egyirányba forgató csapat ellen a kettőzés a forgás
    VÉGPONTJÁN ér a legtöbbet — oda érkezik a labda, amikor lőni
    akarnak; és az ellenirányba terelés (a megszokott sáv zárása)
    kizökkenti a teljes ritmusukat.

    Visszatérés csapatonként: {"passes", "left", "right", "verdict"} —
    a verdict None CIR_MIN_PASSES alatt vagy kiegyenlített forgásnál;
    a verdict "balra forgatnak" / "jobbra forgatnak" / None.
    """
    from .decisions import detect_passes

    config = config or TacticsConfig()
    by_t = {f.t: f for f in match.frames}
    out = {side: {"passes": 0, "left": 0, "right": 0, "verdict": None}
           for side in ("home", "away")}
    for pe in detect_passes(match, config):
        f = by_t.get(pe.t)
        if f is None or pe.passer_pos is None:
            continue
        recv = next((p for p in f.players
                     if p.track_id == pe.receiver_id), None)
        if recv is None:
            continue
        dy = recv.y - pe.passer_pos.y
        if abs(dy) < 2.0:
            continue   # nem érdemi oldalmozgás
        goal_x = config.attacks_toward_x(pe.team)
        # A +x kapura támadva a +y a támadó bal keze felé esik.
        left = (dy > 0) if goal_x > 0 else (dy < 0)
        rec = out[pe.team.value]
        rec["passes"] += 1
        rec["left" if left else "right"] += 1

    for side in ("home", "away"):
        rec = out[side]
        if rec["passes"] >= CIR_MIN_PASSES:
            lp = 100.0 * rec["left"] / rec["passes"]
            if lp >= CIR_DOM_PCT:
                rec["verdict"] = "balra forgatnak"
            elif lp <= 100.0 - CIR_DOM_PCT:
                rec["verdict"] = "jobbra forgatnak"
    return out


# Felfutási létszám: ennyi mérhető támadó-kocka kell az átlaghoz, és e
# feletti / alatti átlagos támadó-létszám a mindenkit felküldő,
# illetve a biztosító támadás jele.
AHC_MIN_FRAMES = 100
AHC_ALL_IN = 5.5
AHC_SAFE = 4.5


def attack_headcount(match: Match,
                     config: Optional[TacticsConfig] = None) -> dict:
    """Felfutási létszám: HÁNY EMBERREL támadnak.

    A támadás-szélesség a teret méri — ez a létszámot: saját
    labdabirtoklású, támadó-térfeles kockánként megszámoljuk, hány
    mezőnyjátékosuk van fent a támadó térfélen. Van, aki mindenkit
    felküld, és van, aki hátrahagy egy biztosító embert.

    Edzőileg: a mindenkit felküldő csapat háta mögött üres a pálya —
    minden labdaszerzés kontrát ér ellenük, a hosszú kidobás is; a
    biztosítva támadó ellen kontrát nehéz vezetni, viszont elöl
    emberhátrányban vannak: a fal bátran kettőzhet, mert a
    kimaradó támadó nem büntet.

    Visszatérés csapatonként: {"frames", "avg_up", "verdict"} — az
    avg_up/verdict None AHC_MIN_FRAMES alatt; a verdict "mindenkit
    felküldenek" / "biztosítva támadnak" / None.
    """
    from .tactics import possession_team

    config = config or TacticsConfig()
    acc = {"home": [0, 0], "away": [0, 0]}
    for fr in match.frames:
        poss = possession_team(fr, config)
        if poss is None:
            continue
        goal_x = config.attacks_toward_x(poss)
        if fr.ball is None or abs(fr.ball.x - goal_x) > 20.0:
            continue   # csak felállt, támadó-térfeles birtoklás
        ups = sum(1 for p in fr.players
                  if p.team == poss and p.role != "kapus"
                  and abs(p.x - goal_x) <= 20.0)
        if ups == 0:
            continue
        rec = acc[poss.value]
        rec[0] += 1
        rec[1] += ups

    out: dict = {}
    for side in ("home", "away"):
        n, total = acc[side]
        rec = {"frames": n, "avg_up": None, "verdict": None}
        if n >= AHC_MIN_FRAMES:
            avg = total / n
            rec["avg_up"] = round(avg, 2)
            if avg >= AHC_ALL_IN:
                rec["verdict"] = "mindenkit felküldenek"
            elif avg <= AHC_SAFE:
                rec["verdict"] = "biztosítva támadnak"
        out[side] = rec
    return out


# Kivárás-csapda: ennyi másodperc feletti felállt támadás számít
# hosszúnak, ennyi kell az ítélethez, és e feletti / alatti elhalás-
# arány a csapdába futó, illetve a lövésig érő kivárás jele.
LAO_MIN_S = 25.0
LAO_MIN_ATTACKS = 5
LAO_DIE_PCT = 40.0
LAO_FINISH_PCT = 15.0


def long_attack_outcomes(match: Match,
                         config: Optional[TacticsConfig] = None) -> dict:
    """Kivárás-csapda: MI LESZ A HOSSZÚ TÁMADÁSAIKBÓL.

    A passzív-kockázat réteg a hosszú, lövés nélküli szakaszokat
    listázza — ez ítéletet mond: a LAO_MIN_S-nél hosszabb felállt
    támadásaikból mennyi hal el lövés nélkül (eladás, lefújás), és
    mennyi ér el legalább a lövésig.

    Edzőileg: akinek a hosszú támadásai elhalnak, annak a kivárás
    csapda — ellene a fegyelmezett, kivárós fal a recept, mert a
    passzív jel feléjük dolgozik; akinek a hosszú támadásai is
    lövésig érnek, az a kivárásból is helyzetet csinál — ellene nem
    a kivárás, hanem a korai megzavarás (kilépés, kettőzés) kell.

    Visszatérés csapatonként: {"long_attacks", "died", "die_pct",
    "verdict"} — a die_pct/verdict None LAO_MIN_ATTACKS alatt; a
    verdict "a hosszú támadásaik elhalnak" / "a hosszú támadásaik is
    lövésig érnek" / None.
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    tail = round(ATTACK_TAIL_S * fps)
    shot_ts = {"home": [], "away": []}
    for e in detect_shots(match, config):
        if e.type in (EventType.SHOT, EventType.GOAL):
            shot_ts[e.team.value].append(e.t)

    out = {side: {"long_attacks": 0, "died": 0, "die_pct": None,
                  "verdict": None} for side in ("home", "away")}
    for a in classify_attacks(match, config):
        if a["type"] != AttackType.POSITIONAL.value:
            continue
        if a["duration_s"] < LAO_MIN_S:
            continue
        side = a["team"]
        rec = out[side]
        rec["long_attacks"] += 1
        if not any(a["start_frame"] <= t <= a["end_frame"] + tail
                   for t in shot_ts[side]):
            rec["died"] += 1

    for side in ("home", "away"):
        rec = out[side]
        if rec["long_attacks"] >= LAO_MIN_ATTACKS:
            pct = 100.0 * rec["died"] / rec["long_attacks"]
            rec["die_pct"] = round(pct, 1)
            if pct >= LAO_DIE_PCT:
                rec["verdict"] = "a hosszú támadásaik elhalnak"
            elif pct <= LAO_FINISH_PCT:
                rec["verdict"] = "a hosszú támadásaik is lövésig érnek"
    return out


# Szélső-futtatás: e feletti átvételi sebesség számít futópassznak,
# ennyi szélső-átvétel kell az ítélethez, és e feletti / alatti
# futtatott arány a lendületbe hozott, illetve az álló szélső jele.
WSV_RUN_MS = 3.0
WSV_MIN_RECEPTIONS = 6
WSV_RUN_PCT = 55.0
WSV_STATIC_PCT = 25.0


def wing_service(match: Match,
                 config: Optional[TacticsConfig] = None) -> dict:
    """Szélső-futtatás: LENDÜLETBŐL vagy ÁLLVA kapják-e a szélsők a
    labdát.

    A szél-bevonás azt méri, mennyit ér a szélső játék — ez azt,
    HOGYAN érkezik a labda: a szélső-posztú játékosok átvételeinél
    megmérjük a fogadó sebességét. A futtatott szélső a kifutó védő
    előtt ér labdába — ellene a kifutás mindig késik; az állva
    átvevő szélsőt viszont a kilépő védő lezárhatja, mielőtt
    lendületet venne.

    Edzőileg: a futtatva játszó szélsők ellen a kifutás helyett a
    passzsáv-zárás véd — a futópasszt kell megakadályozni, nem a
    lövést; az állva kapó szélsők ellen a bátor, korai kifutás
    a recept.

    Visszatérés csapatonként: {"receptions", "running", "run_pct",
    "verdict"} — a run_pct/verdict None WSV_MIN_RECEPTIONS alatt; a
    verdict "futtatva kapják a szélsők" / "állva kapják a szélsők" /
    None.
    """
    import math

    from .decisions import detect_passes
    from .roles import estimate_positions

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    idx_of = {f.t: i for i, f in enumerate(match.frames)}
    posts = estimate_positions(match, config)
    wings = {side: {tid for tid, r in posts.get(side, {}).items()
                    if r["poszt"] == "szélső"}
             for side in ("home", "away")}

    out = {side: {"receptions": 0, "running": 0, "run_pct": None,
                  "verdict": None} for side in ("home", "away")}
    for pe in detect_passes(match, config):
        side = pe.team.value
        if pe.receiver_id not in wings[side]:
            continue
        i0 = idx_of.get(pe.t)
        if i0 is None or i0 < 2 or i0 + 2 >= len(match.frames):
            continue
        p_before = next((p for p in match.frames[i0 - 2].players
                         if p.track_id == pe.receiver_id), None)
        p_after = next((p for p in match.frames[i0 + 2].players
                        if p.track_id == pe.receiver_id), None)
        if p_before is None or p_after is None:
            continue
        speed = (math.hypot(p_after.x - p_before.x,
                            p_after.y - p_before.y) * fps / 4.0)
        rec = out[side]
        rec["receptions"] += 1
        if speed >= WSV_RUN_MS:
            rec["running"] += 1

    for side in ("home", "away"):
        rec = out[side]
        if rec["receptions"] >= WSV_MIN_RECEPTIONS:
            pct = 100.0 * rec["running"] / rec["receptions"]
            rec["run_pct"] = round(pct, 1)
            if pct >= WSV_RUN_PCT:
                rec["verdict"] = "futtatva kapják a szélsők"
            elif pct <= WSV_STATIC_PCT:
                rec["verdict"] = "állva kapják a szélsők"
    return out


# Keresztjáték: a hátsó sor két játékosának oldalcseréje számít
# keresztnek, ennyi mért támadás kell az ítélethez, és e feletti /
# alatti kereszt-átlag a mozgásos, illetve a statikus hátsó sor jele.
CRX_MIN_ATTACKS = 8
CRX_HIGH_PER_ATTACK = 1.0
CRX_LOW_PER_ATTACK = 0.3


def crossing_runs(match: Match,
                  config: Optional[TacticsConfig] = None) -> dict:
    """Keresztjáték: MENNYIT KERESZTEZNEK a hátsó sorban.

    Az álló támadók rétege az egyéni mozgást méri — ez a szerkezetet:
    felállt támadásonként megszámoljuk, hányszor cserél oldalt
    (y-sorrendet) a hátsó sor két játékosa. A keresztjáték a
    váltás-kényszer műfaja: minden kereszt egy védő-döntést
    provokál.

    Edzőileg: a sokat keresztező csapat ellen a váltás-fegyelem dönt
    — hangos, korai átadás a védők közt, különben a kereszt után
    ketten fogják ugyanazt az embert; a nem keresztező, statikus
    hátsó sor ellen ember-ember tartás is vállalható, mert nincs
    váltás-helyzet.

    Visszatérés csapatonként: {"attacks", "crosses", "per_attack",
    "verdict"} — a per_attack/verdict None CRX_MIN_ATTACKS alatt; a
    verdict "sokat kereszteznek" / "statikus a hátsó soruk" / None.
    """
    from .roles import estimate_positions
    from .setplays import segment_attacks

    config = config or TacticsConfig()
    posts = estimate_positions(match, config)
    backs = {side: [tid for tid, r in posts.get(side, {}).items()
                    if r["poszt"] in ("irányító", "átlövő")]
             for side in ("home", "away")}

    out = {side: {"attacks": 0, "crosses": 0, "per_attack": None,
                  "verdict": None} for side in ("home", "away")}
    for seq in segment_attacks(match, config):
        side = seq.team.value
        ids = backs[side]
        if len(ids) < 2:
            continue
        rec = out[side]
        rec["attacks"] += 1
        prev_order = None
        for f in seq.frames:
            ys = {}
            for p in f.players:
                if p.track_id in ids:
                    ys[p.track_id] = p.y
            if len(ys) < 2:
                continue
            order = tuple(sorted(ys, key=lambda k: ys[k]))
            if prev_order is not None and order != prev_order:
                rec["crosses"] += 1
            prev_order = order

    for side in ("home", "away"):
        rec = out[side]
        if rec["attacks"] >= CRX_MIN_ATTACKS:
            per = rec["crosses"] / rec["attacks"]
            rec["per_attack"] = round(per, 2)
            if per >= CRX_HIGH_PER_ATTACK:
                rec["verdict"] = "sokat kereszteznek"
            elif per <= CRX_LOW_PER_ATTACK:
                rec["verdict"] = "statikus a hátsó soruk"
    return out

# Beálló-futtatás: e feletti átvételi sebesség számít mozgásból
# érkezésnek (a beálló az elzárásból leforduló, lassabb műfaj, ezért a
# küszöb a szélsőnél alacsonyabb), ennyi beálló-átvétel kell az
# ítélethez, és e feletti / alatti mozgásos arány a leforduló,
# illetve a beragadt beálló jele.
PSV_RUN_MS = 1.8
PSV_MIN_RECEPTIONS = 5
PSV_RUN_PCT = 55.0
PSV_STATIC_PCT = 25.0


def pivot_service(match: Match,
                  config: Optional[TacticsConfig] = None) -> dict:
    """Beálló-futtatás: MOZGÁSBÓL vagy ÁLLVA kapja-e a beálló a labdát.

    A beálló-terhelés azt méri, mennyit megy a labda a beállóra, a
    kiszolgálói azt, kitől — ez azt, HOGYAN érkezik: a beálló-posztú
    játékosok átvételeinél megmérjük a fogadó sebességét. A mozgásból
    (elzárásból lefordulva) kapó beálló a védője elé fordulva már
    helyzetben van — ellene az utólagos elé lépés késik; az állva,
    beragadva kapó beállót viszont a védője lezárhatja, mielőtt
    megfordulna.

    Edzőileg: a lefordulós beálló ellen a bejátszás ELŐTT kell elé
    lépni (a passzsávot zárni, hangos váltással), nem az átvétel után
    birkózni; a beragadt beálló ellen a testes elé állás és a
    bejátszás utáni azonnali kettőzés a recept.

    Visszatérés csapatonként: {"receptions", "running", "run_pct",
    "verdict"} — a run_pct/verdict None PSV_MIN_RECEPTIONS alatt; a
    verdict "mozgásból kapja a beálló" / "állva kapja a beálló" /
    None.
    """
    import math

    from .decisions import detect_passes
    from .roles import estimate_positions

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    idx_of = {f.t: i for i, f in enumerate(match.frames)}
    posts = estimate_positions(match, config)
    pivots = {side: {tid for tid, r in posts.get(side, {}).items()
                     if r["poszt"] == "beálló"}
              for side in ("home", "away")}

    out = {side: {"receptions": 0, "running": 0, "run_pct": None,
                  "verdict": None} for side in ("home", "away")}
    for pe in detect_passes(match, config):
        side = pe.team.value
        if pe.receiver_id not in pivots[side]:
            continue
        i0 = idx_of.get(pe.t)
        if i0 is None or i0 < 2 or i0 + 2 >= len(match.frames):
            continue
        p_before = next((p for p in match.frames[i0 - 2].players
                         if p.track_id == pe.receiver_id), None)
        p_after = next((p for p in match.frames[i0 + 2].players
                        if p.track_id == pe.receiver_id), None)
        if p_before is None or p_after is None:
            continue
        speed = (math.hypot(p_after.x - p_before.x,
                            p_after.y - p_before.y) * fps / 4.0)
        rec = out[side]
        rec["receptions"] += 1
        if speed >= PSV_RUN_MS:
            rec["running"] += 1

    for side in ("home", "away"):
        rec = out[side]
        if rec["receptions"] >= PSV_MIN_RECEPTIONS:
            pct = 100.0 * rec["running"] / rec["receptions"]
            rec["run_pct"] = round(pct, 1)
            if pct >= PSV_RUN_PCT:
                rec["verdict"] = "mozgásból kapja a beálló"
            elif pct <= PSV_STATIC_PCT:
                rec["verdict"] = "állva kapja a beálló"
    return out

# Kontra-hullámok: ennyi lövésig jutó lerohanás kell az ítélethez, és
# e feletti / alatti második-hullám arány jelenti, hogy a befutó,
# illetve az első ember fejezi be a kontráikat.
FBW_MIN_BREAKS = 5
FBW_SECOND_PCT = 50.0
FBW_FIRST_PCT = 20.0


def fast_break_waves(match: Match,
                     config: Optional[TacticsConfig] = None) -> dict:
    """Kontra-hullámok: az ELSŐ EMBER vagy a MÁSODIK HULLÁM fejezi be
    a lerohanásaikat.

    A kontra-befejezők rétege a neveket adja, a kontra-hatásfok a
    végeredményt — ez a szerkezetet: a lövésig jutó lerohanásoknál
    megnézzük, a támadás indulásakor legelöl lévő játékos (az első
    hullám) lő-e, vagy egy mögötte befutó (a második hullám).

    Edzőileg ez dönti el, hogyan kell visszafutni: az első hullámra
    építő csapat ellen az indítópassz elvágása és az első ember
    azonnali felvétele öli meg a kontrát; a második hullámra építő
    ellen az első ember felvétele NEM elég — a visszafutásnál a
    középső sávot kell feltölteni, mert a gól a befutótól jön.

    Visszatérés csapatonként: {"breaks", "second", "second_pct",
    "verdict"} — a second_pct/verdict None FBW_MIN_BREAKS alatt; a
    verdict "a második hullám fejezi be a kontrát" / "az első ember
    fejezi be a kontrát" / None.
    """
    from ..models.tracking import Team
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    tail = round(ATTACK_TAIL_S * fps)
    idx_of = {f.t: i for i, f in enumerate(match.frames)}
    shots = [e for e in detect_shots(match, config)
             if e.type in (EventType.SHOT, EventType.GOAL)
             and e.player_id is not None]

    out = {side: {"breaks": 0, "second": 0, "second_pct": None,
                  "verdict": None} for side in ("home", "away")}
    for a in classify_attacks(match, config):
        if a["type"] != AttackType.FAST_BREAK.value:
            continue
        side = a["team"]
        shot = next((e for e in shots if e.team.value == side
                     and a["start_frame"] <= e.t
                     <= a["end_frame"] + tail), None)
        if shot is None:
            continue
        i0 = idx_of.get(a["start_frame"])
        if i0 is None:
            continue
        goal_x = config.attacks_toward_x(Team(side))
        runners = [p for p in match.frames[i0].players
                   if p.team.value == side and p.role != "kapus"]
        if len(runners) < 2:
            continue
        first_id = min(runners,
                       key=lambda p: abs(p.x - goal_x)).track_id
        rec = out[side]
        rec["breaks"] += 1
        if shot.player_id != first_id:
            rec["second"] += 1

    for side in ("home", "away"):
        rec = out[side]
        if rec["breaks"] >= FBW_MIN_BREAKS:
            pct = 100.0 * rec["second"] / rec["breaks"]
            rec["second_pct"] = round(pct, 1)
            if pct >= FBW_SECOND_PCT:
                rec["verdict"] = "a második hullám fejezi be a kontrát"
            elif pct <= FBW_FIRST_PCT:
                rec["verdict"] = "az első ember fejezi be a kontrát"
    return out

# Kontra-elszökés: a labdánál legalább ennyivel előrébb álló ember
# számít elszököttnek a kontra indulásakor; ennyi lerohanás kell az
# ítélethez, és e feletti / alatti elszökött arány a szökős, illetve
# az együtt felfutó kontra jele.
FBH_GAP_M = 6.0
FBH_MIN_BREAKS = 5
FBH_AHEAD_PCT = 40.0
FBH_TOGETHER_PCT = 10.0


def fast_break_headstart(match: Match,
                         config: Optional[TacticsConfig] = None) -> dict:
    """Kontra-elszökés: ELŐRE SZÖKÖTT emberrel kontráznak-e.

    A kontra-forrás azt mondja meg, miből indul a lerohanásuk, a
    kontra-hullámok azt, ki fejezi be — ez azt, HOL ÁLLNAK az
    induláskor: minden lerohanásnál megnézzük, van-e a labdánál
    legalább FBH_GAP_M méterrel előrébb váró mezőnyjátékosuk
    (elszökött ember), vagy együtt fut fel a csapat a labdával.

    Edzőileg: az elszökős csapat ellen mélységbiztosítás kell — a fal
    mögött MINDIG maradjon egy visszarendeződésre kijelölt védő, és a
    hosszú indítópasszt kell elvágni, mert mire a labda elmegy, késő;
    az együtt felfutó kontra ellen az első két visszafutó a labdás
    embert lassítja, és a védelem beér.

    Visszatérés csapatonként: {"breaks", "ahead", "ahead_pct",
    "verdict"} — az ahead_pct/verdict None FBH_MIN_BREAKS alatt; a
    verdict "előre szökött emberrel kontráznak" / "együtt futnak
    fel" / None.
    """
    from ..models.tracking import Team

    config = config or TacticsConfig()
    idx_of = {f.t: i for i, f in enumerate(match.frames)}

    out = {side: {"breaks": 0, "ahead": 0, "ahead_pct": None,
                  "verdict": None} for side in ("home", "away")}
    for a in classify_attacks(match, config):
        if a["type"] != AttackType.FAST_BREAK.value:
            continue
        side = a["team"]
        i0 = idx_of.get(a["start_frame"])
        if i0 is None:
            continue
        fr = match.frames[i0]
        if fr.ball is None:
            continue
        goal_x = config.attacks_toward_x(Team(side))
        runners = [p for p in fr.players
                   if p.team.value == side and p.role != "kapus"]
        if not runners:
            continue
        ball_dist = abs(fr.ball.x - goal_x)
        front_dist = min(abs(p.x - goal_x) for p in runners)
        rec = out[side]
        rec["breaks"] += 1
        if ball_dist - front_dist >= FBH_GAP_M:
            rec["ahead"] += 1

    for side in ("home", "away"):
        rec = out[side]
        if rec["breaks"] >= FBH_MIN_BREAKS:
            pct = 100.0 * rec["ahead"] / rec["breaks"]
            rec["ahead_pct"] = round(pct, 1)
            if pct >= FBH_AHEAD_PCT:
                rec["verdict"] = "előre szökött emberrel kontráznak"
            elif pct <= FBH_TOGETHER_PCT:
                rec["verdict"] = "együtt futnak fel"
    return out


# Kontra-esés: félidőnként legalább ennyi támadás kell az ítélethez,
# és ekkora (százalékpontos) kontra-arány változás számít érdeminek.
BRF_MIN_ATTACKS_HALF = 5
BRF_GAP_PP = 15.0


def break_share_fade(match: Match,
                     config: Optional[TacticsConfig] = None) -> dict:
    """Kontra-esés: MELYIK FÉLIDŐBEN kontráznak.

    A fáradás-család kontra-tagja: a tempó-esés a támadás-ütemüket
    méri félidőnként, ez a támadás-SZERKEZETET — a lerohanások
    részarányát az első és a második félidő támadásain belül. Van,
    akinek a lába a második félidőre elviszi a kontráit, és van, aki
    a hajrában kapcsol rohanó játékra.

    Edzőileg: akinek a második félidőben eláll a kontrája, annál az
    elejét kell túlélni — a szünet után már a felállt védekezés a
    tananyag; aki a hajrára kontrázósabb, annál a második félidőben
    duplán szigorú a visszafutás-fegyelem és a biztos labdakezelés.

    Visszatérés csapatonként: {"fh_attacks", "fh_breaks",
    "sh_attacks", "sh_breaks", "gap_pp", "verdict"} — a
    gap_pp/verdict None felismert szünet nélkül vagy félidőnként
    BRF_MIN_ATTACKS_HALF-nál kevesebb támadásnál; a verdict "a
    második félidőben eláll a kontrájuk" / "a hajrára kontrázósabbak"
    / None.
    """
    from .halftime import detect_halftime

    config = config or TacticsConfig()
    out = {side: {"fh_attacks": 0, "fh_breaks": 0, "sh_attacks": 0,
                  "sh_breaks": 0, "gap_pp": None, "verdict": None}
           for side in ("home", "away")}
    ht = detect_halftime(match)
    if ht is None:
        return out

    for a in classify_attacks(match, config):
        rec = out[a["team"]]
        first = a["start_frame"] <= ht
        rec["fh_attacks" if first else "sh_attacks"] += 1
        if a["type"] == AttackType.FAST_BREAK.value:
            rec["fh_breaks" if first else "sh_breaks"] += 1

    for side in ("home", "away"):
        rec = out[side]
        if (rec["fh_attacks"] >= BRF_MIN_ATTACKS_HALF
                and rec["sh_attacks"] >= BRF_MIN_ATTACKS_HALF):
            fh_pct = 100.0 * rec["fh_breaks"] / rec["fh_attacks"]
            sh_pct = 100.0 * rec["sh_breaks"] / rec["sh_attacks"]
            rec["gap_pp"] = round(sh_pct - fh_pct, 1)
            if rec["gap_pp"] <= -BRF_GAP_PP:
                rec["verdict"] = "a második félidőben eláll a kontrájuk"
            elif rec["gap_pp"] >= BRF_GAP_PP:
                rec["verdict"] = "a hajrára kontrázósabbak"
    return out


# Szélső-mélység: a kapu vonalától mért ekkora lövő-távolság alatt
# mélyre befutott, e felett messziről leadott a szélső-lövés; ennyi
# szélső-lövés kell az ítélethez.
WSD_MIN_SHOTS = 5
WSD_DEEP_M = 6.5
WSD_FAR_M = 8.5


def wing_shot_depth(match: Match,
                    config: Optional[TacticsConfig] = None) -> dict:
    """Szélső-mélység: MILYEN MÉLYRŐL lőnek a szélsőik.

    A szélső-befejezés a szélső-zóna hatékonyságát méri — ez a
    befutás mélységét: a szélső-posztú játékosok lövéseinél a kapu
    vonalától mért távolság átlagát. A mélyre befutó szélső a
    hatosig viszi a labdát — jó szögből, közelről fejez be; a
    messziről lövő szélső rossz szögből, kényszerből ereszti el.

    Edzőileg: a mélyre befutó szélsők ellen a kapusnak várnia kell —
    a korai kifutás öngól, a szöget a kifutó védő zárja le még a
    befutás ELŐTT; a messziről lövő szélsőknél a szög ráengedhető,
    a kapus bátran jöhet ki, a fal pedig nem szorul szét.

    Visszatérés csapatonként: {"shots", "depth_sum_m", "avg_m",
    "verdict"} — az avg_m/verdict None WSD_MIN_SHOTS alatt; a
    verdict "mélyre befutó szélsők" / "messziről lövő szélsők" /
    None.
    """
    from ..models.tracking import Team
    from .roles import estimate_positions
    from .xg import match_xg

    config = config or TacticsConfig()
    posts = estimate_positions(match, config)
    wings = {side: {tid for tid, r in posts.get(side, {}).items()
                    if r["poszt"] == "szélső"}
             for side in ("home", "away")}

    out = {side: {"shots": 0, "depth_sum_m": 0.0, "avg_m": None,
                  "verdict": None} for side in ("home", "away")}
    for sh in match_xg(match, config).get("shots", []):
        side = sh["team"]
        if sh.get("player_id") not in wings[side]:
            continue
        goal_x = config.attacks_toward_x(Team(side))
        rec = out[side]
        rec["shots"] += 1
        rec["depth_sum_m"] += abs(sh["x"] - goal_x)

    for side in ("home", "away"):
        rec = out[side]
        rec["depth_sum_m"] = round(rec["depth_sum_m"], 1)
        if rec["shots"] >= WSD_MIN_SHOTS:
            avg = rec["depth_sum_m"] / rec["shots"]
            rec["avg_m"] = round(avg, 1)
            if avg <= WSD_DEEP_M:
                rec["verdict"] = "mélyre befutó szélsők"
            elif avg >= WSD_FAR_M:
                rec["verdict"] = "messziről lövő szélsők"
    return out


# Hiba-állás: állás-vödrönként legalább ennyi támadás kell az
# összevetéshez, és ekkora (százalékpontos) eladás-arány többlet a
# kapkodás, ekkora hiány a rendezettség jele hátrányban.
TBS_MIN_ATTACKS = 5
TBS_PANIC_PP = 10.0
TBS_CALM_PP = -5.0


def turnovers_by_score(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Hiba-állás: HÁTRÁNYBAN SZÓRJÁK-E a labdát.

    A tempó-állás (pace_by_score) azt méri, gyorsítanak-e hátrányban
    — ez azt, mi lesz a labdával: minden támadáshoz megnézzük a
    kezdetekor az állást (vezet / hátrányban / döntetlen), és
    állásonként a labdaeladással végződő támadások arányát. A
    hátrányban megugró eladás-arány a kapkodás jele.

    Edzőileg: a hátrányban kapkodó csapat ellen az első ellépés után
    présre kell váltani — a nyomás alatt ontják a labdát, és minden
    szerzés a különbséget hizlalja; a hátrányban is rendezett csapat
    ellen a prés kockázata nem térül meg — a fegyelmezett fal többet
    ér.

    Visszatérés csapatonként: {"leading"/"trailing"/"level":
    {"attacks", "turnovers", "pct"}, "verdict"} — a pct None
    TBS_MIN_ATTACKS alatt; a verdict "hátrányban kapkodnak" /
    "hátrányban is rendezettek" / None (ahhoz a hátrány-vödör ÉS a
    többi együtt is elég mintás kell legyen).
    """
    from .event_detection import EventType, detect_events
    from .setplays import segment_attacks

    config = config or TacticsConfig()
    events = detect_events(match, config)
    goals = [(e.t, e.team.value) for e in events
             if e.type == EventType.GOAL]
    tos = [(e.t, e.team.value) for e in events
           if e.type == EventType.TURNOVER]

    out: dict = {side: {k: {"attacks": 0, "turnovers": 0, "pct": None}
                        for k in ("leading", "trailing", "level")}
                 for side in ("home", "away")}
    for seq in segment_attacks(match, config):
        side = seq.team.value
        own = sum(1 for (t, tm) in goals
                  if t < seq.start_t and tm == side)
        opp = sum(1 for (t, tm) in goals
                  if t < seq.start_t and tm != side)
        state = ("leading" if own > opp
                 else "trailing" if own < opp else "level")
        rec = out[side][state]
        rec["attacks"] += 1
        if any(tm == side and seq.start_t <= t <= seq.end_t + 5
               for (t, tm) in tos):
            rec["turnovers"] += 1

    for side in ("home", "away"):
        buckets = out[side]
        for rec in buckets.values():
            if rec["attacks"] >= TBS_MIN_ATTACKS:
                rec["pct"] = round(100.0 * rec["turnovers"]
                                   / rec["attacks"], 1)
        tr = buckets["trailing"]
        rest_att = (buckets["leading"]["attacks"]
                    + buckets["level"]["attacks"])
        rest_to = (buckets["leading"]["turnovers"]
                   + buckets["level"]["turnovers"])
        verdict = None
        if tr["attacks"] >= TBS_MIN_ATTACKS \
                and rest_att >= TBS_MIN_ATTACKS:
            diff = (100.0 * tr["turnovers"] / tr["attacks"]
                    - 100.0 * rest_to / rest_att)
            if diff >= TBS_PANIC_PP:
                verdict = "hátrányban kapkodnak"
            elif diff <= TBS_CALM_PP:
                verdict = "hátrányban is rendezettek"
        buckets["verdict"] = verdict
    return out


# Gólpassz-esés: a gólpasszos gólok részaránya félidőnként.
ASF_MIN_GOALS = 3    # félidőnként ennyi gól kell az ítélethez
ASF_DROP_PP = 25.0   # ekkora részarány-változás számít mintázatnak


def assist_fade(match: Match,
                config: Optional[TacticsConfig] = None) -> dict:
    """Gólpassz-esés: MEGÁLL-E A LABDA a hajrára.

    A fáradás-család előkészítés-tagja: a gólpasszból (bekönyvelt
    assziszttal) született gólok részarányát mérjük félidőnként. Ha a
    második félidőre a gólpasszos gólok aránya beesik, a csapatjáték
    fáradt el: a labda megáll, és jönnek az egyéni megoldások — ez
    védekezhetőbb, mint az első félidei mozgatás. A fordítottja is
    jel: aki a hajrára áll össze, annak az elejét kell megnyomni.

    Edzőileg: az egyéni megoldásokba fáradó csapat ellen a hajrában
    a labdás ember dupla nyomást kaphat (a passz úgyis megállt); a
    saját oldalon a hajra-csapatjáték edzendő — fáradt lábbal is
    kötelező a második-harmadik átadás.

    Visszatérés csapatonként: {"fh_goals", "fh_assisted", "sh_goals",
    "sh_assisted", "gap_pp", "verdict"} — gap_pp/verdict None
    felismert szünet nélkül vagy félidőnként ASF_MIN_GOALS-nál
    kevesebb gólnál; a verdict "a hajrában megáll a labda" /
    "a hajrára áll össze a csapatjátékuk" / None.
    """
    from .event_detection import EventType, detect_events
    from .halftime import detect_halftime

    config = config or TacticsConfig()
    out = {side: {"fh_goals": 0, "fh_assisted": 0, "sh_goals": 0,
                  "sh_assisted": 0, "gap_pp": None, "verdict": None}
           for side in ("home", "away")}
    ht = detect_halftime(match)
    if ht is None:
        return out
    for g in detect_events(match, config):
        if g.type != EventType.GOAL:
            continue
        rec = out[g.team.value]
        first = g.t <= ht
        rec["fh_goals" if first else "sh_goals"] += 1
        if (g.detail or {}).get("assist_id") is not None:
            rec["fh_assisted" if first else "sh_assisted"] += 1
    for rec in out.values():
        if rec["fh_goals"] < ASF_MIN_GOALS \
                or rec["sh_goals"] < ASF_MIN_GOALS:
            continue
        fh_pct = 100.0 * rec["fh_assisted"] / rec["fh_goals"]
        sh_pct = 100.0 * rec["sh_assisted"] / rec["sh_goals"]
        rec["gap_pp"] = round(sh_pct - fh_pct, 1)
        if rec["gap_pp"] <= -ASF_DROP_PP:
            rec["verdict"] = "a hajrában megáll a labda"
        elif rec["gap_pp"] >= ASF_DROP_PP:
            rec["verdict"] = "a hajrára áll össze a csapatjátékuk"
    return out


# Kontra-állás: a lerohanás-részarány az eredményjelző szerint.
BKS_MIN_ATTACKS = 5   # az összevetett állapotokban ennyi-ennyi támadás kell
BKS_GAP_PP = 12.0     # ekkora részarány-különbség számít mintázatnak


def breaks_by_score(match: Match,
                    config: Optional[TacticsConfig] = None) -> dict:
    """Kontra-állás: MIKOR futják a lerohanásaikat — állás szerint.

    A kontra-esés (break_share_fade) az időtengelyen nézi a
    lerohanás-részarányt — ez az eredményjelzőn: a támadás kezdetén
    vezetett, állt vagy hátrányban volt-e a támadó csapat, és
    állásonként mekkora a lerohanások részaránya. A hátrányban
    megugró kontra-arány a kényszer-kontra: a lemaradó csapat
    kapkodva futással próbál visszajönni — kockázatos labdákkal; a
    vezetésnél is futó csapat az ölő ösztön: nem ül rá az előnyre.

    Edzőileg: a kényszer-kontrás csapat ellen vezetésnél a
    visszafutás-fegyelem dönt — futni fognak; a vezetésnél is futó
    ellen sosincs "kockázatmentes" perc. A saját oldalon a hátrányban
    is szervezett (nem kapkodó) visszajövetel az edzés-téma.

    Visszatérés csapatonként: {"leading"/"trailing"/"level":
    {"attacks", "breaks"}, "verdict"} — a verdict "hátrányban
    kontrába menekülnek" / "vezetésnél is futják a kontráikat" /
    None (állapotonként BKS_MIN_ATTACKS-nál kevesebb támadásnál).
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    goals = [(e.t, e.team.value) for e in detect_shots(match, config)
             if e.type == EventType.GOAL]
    out = {side: {k: {"attacks": 0, "breaks": 0}
                  for k in ("leading", "trailing", "level")}
           for side in ("home", "away")}
    for a in classify_attacks(match, config):
        side = a["team"]
        t0 = a["start_frame"]
        own = sum(1 for (t, tm) in goals if t < t0 and tm == side)
        opp = sum(1 for (t, tm) in goals if t < t0 and tm != side)
        state = ("leading" if own > opp
                 else "trailing" if own < opp else "level")
        rec = out[side][state]
        rec["attacks"] += 1
        if a["type"] == AttackType.FAST_BREAK.value:
            rec["breaks"] += 1

    for side in ("home", "away"):
        buckets = out[side]
        verdict = None
        tr = buckets["trailing"]
        lead = buckets["leading"]
        rest_tr_att = lead["attacks"] + buckets["level"]["attacks"]
        rest_tr_brk = lead["breaks"] + buckets["level"]["breaks"]
        if tr["attacks"] >= BKS_MIN_ATTACKS \
                and rest_tr_att >= BKS_MIN_ATTACKS:
            diff = (100.0 * tr["breaks"] / tr["attacks"]
                    - 100.0 * rest_tr_brk / rest_tr_att)
            if diff >= BKS_GAP_PP:
                verdict = "hátrányban kontrába menekülnek"
        rest_ld_att = tr["attacks"] + buckets["level"]["attacks"]
        rest_ld_brk = tr["breaks"] + buckets["level"]["breaks"]
        if verdict is None and lead["attacks"] >= BKS_MIN_ATTACKS \
                and rest_ld_att >= BKS_MIN_ATTACKS:
            diff = (100.0 * lead["breaks"] / lead["attacks"]
                    - 100.0 * rest_ld_brk / rest_ld_att)
            if diff >= BKS_GAP_PP:
                verdict = "vezetésnél is futják a kontráikat"
        buckets["verdict"] = verdict
    return out


# Kidobott labda: az oldalvonalon kimenő labda — a legolcsóbb eladás.
OBT_BASELINE_GUARD_M = 3.0  # az alapvonal közelében kimenőt nem számoljuk
OBT_DEBOUNCE_S = 3.0        # két kimenés között legalább ennyi idő
OBT_LOOKBACK_S = 1.0        # a birtoklót ennyivel a kimenés előtt keressük
OBT_MIN = 3                 # ennyi kidobott labdától van ítélet


def balls_out(match: Match,
              config: Optional[TacticsConfig] = None) -> dict:
    """Kidobott labda: hányszor hagyja el a labda a pályát az OLDALVONALON.

    A legolcsóbb eladott labda az, amelyikhez ellenfél sem kellett:
    a túl hosszú szélső-passz, a túlfutott indítás, a kicsúszó labda.
    A pálya oldalvonalán kimenő labdát a kimenés előtti birtokló
    csapatnak írjuk fel; az alapvonal közelében (OBT_BASELINE_GUARD_M)
    kimenőt nem számoljuk, mert az jellemzően elhajló lövés — azt a
    lövés-rétegek már mérik.

    Edzőileg: a kidobott labda tiszta ajándék — állóhelyzeti bedobás
    az ellenfélnek, kontra-veszély nélkül, de a saját támadás odavan.
    Aki sokat dob ki, azt érdemes az oldalvonalra szorítani: a szélső
    sávban pontatlan. A saját oldalon a szélső-passz pontossága és az
    indítások hossz-kontrollja az edzés-téma.

    Visszatérés csapatonként: {"out", "verdict"} — a verdict "sok
    kidobott labda" (OBT_MIN-től), különben None.
    """
    from .calibration import COURT_LENGTH_M, COURT_WIDTH_M
    from .tactics import possession_team

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    out = {side: {"out": 0, "verdict": None} for side in ("home", "away")}

    lookback = max(1, round(OBT_LOOKBACK_S * fps))
    debounce = round(OBT_DEBOUNCE_S * fps)
    last_out = -10 ** 9
    frames = match.frames
    for i in range(1, len(frames)):
        prev_b = frames[i - 1].ball
        cur_b = frames[i].ball
        if prev_b is None or cur_b is None:
            continue
        prev_in = 0.0 <= prev_b.y <= COURT_WIDTH_M
        cur_in = 0.0 <= cur_b.y <= COURT_WIDTH_M
        if not (prev_in and not cur_in):
            continue  # csak a bent → kint átmenet számít
        if frames[i].t - last_out < debounce:
            continue
        if not (OBT_BASELINE_GUARD_M <= cur_b.x
                <= COURT_LENGTH_M - OBT_BASELINE_GUARD_M):
            continue  # alapvonal-közeli kimenés: elhajló lövés
        # A birtokló a kimenés előtti pillanatokból.
        holder = None
        for j in range(i - 1, max(-1, i - 1 - lookback), -1):
            holder = possession_team(frames[j], config)
            if holder is not None:
                break
        if holder is None:
            continue
        out[holder.value]["out"] += 1
        last_out = frames[i].t
    for rec in out.values():
        if rec["out"] >= OBT_MIN:
            rec["verdict"] = "sok kidobott labda"
    return out


# Kiosztás-célpont: a betörés zónája (méter a kaputól), a kiosztásnak
# számító passz időablaka, az ítélethez kellő kiosztás-szám, és az a
# részesedés, ami fölött EGY célpont már kiszámítható.
KOT_IN_DIST_M = 9.0
KOT_WINDOW_S = 3.0
KOT_MIN_KICKOUTS = 4
KOT_CONCENTRATION_PCT = 55.0


def kickout_targets(match: Match,
                    config: Optional[TacticsConfig] = None) -> dict:
    """Kiosztás-célpont: HOVÁ megy a labda, ha a betörés nem lövéssel zárul.

    Az áttörő emberek (breakthrough_players) azt mondják meg, KI viszi
    be a labdát a falba, a visszahozás-arány (pullback_rate) azt, hogy
    lezárják-e a betörést — ez azt, KIHEZ kerül a labda, amikor a
    betörő nem lő: minden betörés-epizód után megnézzük, ad-e a betörő
    KOT_WINDOW_S mp-en belül passzt, és ki a fogadó.

    Edzőileg ez a legkonkrétabban kiosztható feladat: ha a betörés
    után a labda mindig ugyanahhoz az emberhez megy, az ő védője
    előre elmozdulhat a passzsávba, és a betörésre indulhat a
    kettőzés — a kiosztás így elveszti az értelmét. Ha viszont
    változatos a célpont, a betörést magát kell megállítani, mert a
    passz-olvasásra nem lehet védekezést építeni.

    Visszatérés csapatonként: {"kickouts", "targets": [{"player_id",
    "jersey", "count"}], "top", "top_pct", "verdict"} — a targets
    lista darabszám szerint csökkenő; a top/top_pct/verdict None
    KOT_MIN_KICKOUTS alatt (kevés mintából nem mondunk ítéletet).
    """
    import math

    from .calibration import COURT_WIDTH_M
    from .decisions import ball_holder
    from .event_detection import (EventType, detect_possession_changes,
                                  detect_shots)
    from .setplays import segment_attacks

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    tail = round(ATTACK_TAIL_S * fps)
    win = round(KOT_WINDOW_S * fps)
    gy = COURT_WIDTH_M / 2.0

    shots = [(e.t, e.team.value) for e in detect_shots(match, config)]
    passes = [e for e in detect_possession_changes(match, config)
              if e.type == EventType.PASS]

    jersey: dict = {}
    tally: dict = {"home": {}, "away": {}}
    for seq in segment_attacks(match, config):
        side = seq.team.value
        goal_x = config.attacks_toward_x(seq.team)
        # A betörés-epizódok: összefüggő kockák, ahol a támadó csapat
        # (nem kapus) birtokosa a kapu KOT_IN_DIST_M-es körzetében van.
        episode: list = []
        for fr in list(seq.frames) + [None]:
            h = ball_holder(fr, config) if fr is not None else None
            inside = (h is not None and h.team == seq.team
                      and h.role != "kapus"
                      and math.hypot(h.x - goal_x, h.y - gy)
                      <= KOT_IN_DIST_M)
            if inside:
                episode.append((fr.t, h))
                continue
            if not episode:
                continue
            t0, _ = episode[0]
            t1, driver = episode[-1]
            episode = []
            # Lövéssel záruló betörés nem kiosztás — azt lezárták.
            if any(tm == side and t0 <= t <= t1 + tail
                   for (t, tm) in shots):
                continue
            # A kiosztás: a betörő passza az epizód után, időablakon belül.
            kick = None
            for p in passes:
                if p.t < t1 or p.t > t1 + win:
                    continue
                if p.team != seq.team or p.player_id != driver.track_id:
                    continue
                kick = p
                break
            if kick is None:
                continue
            target = (kick.detail or {}).get("receiver_id")
            if target is None:
                continue
            if driver.jersey_number is not None:
                jersey.setdefault(driver.track_id, driver.jersey_number)
            for pl in (fr.players if fr is not None else []):
                if pl.track_id == target and pl.jersey_number is not None:
                    jersey.setdefault(target, pl.jersey_number)
            tally[side][target] = tally[side].get(target, 0) + 1

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid), "count": n}
                for pid, n in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1])]
        total = sum(r["count"] for r in rows)
        top = top_pct = verdict = None
        if total >= KOT_MIN_KICKOUTS and rows:
            top = rows[0]
            top_pct = 100.0 * rows[0]["count"] / total
            verdict = ("kiszámítható a kiosztás"
                       if top_pct >= KOT_CONCENTRATION_PCT
                       else "változatos a kiosztás")
        out[side] = {"kickouts": total, "targets": rows, "top": top,
                     "top_pct": top_pct, "verdict": verdict}
    return out


# Lepattanó-poszt: ennyi poszthoz kötött második lövés kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy a második
# rohamukat egy poszt viszi.
SCR_MIN_SHOTS = 3
SCR_SHARE_PCT = 60.0


def second_chance_roles(match: Match,
                        config: Optional[TacticsConfig] = None) -> dict:
    """Lepattanó-poszt: KI LŐ MÁSODSZOR — melyik posztjuk viszi a
    második rohamot.

    A második roham rétege (second_chance) csapat-szinten mondja meg,
    harcolnak-e a lepattanóért — ez azt, KI: minden megnyert második
    rohamnál a MÁSODIK lövést az elengedő játékos posztjához írja.

    Edzőileg ez a zárás sorrendje. A lövés pillanatában a fal dolga
    nem ér véget: a lepattanónál dől el, jön-e második roham. Ha a
    második lövéseik rendre ugyanarról a posztról jönnek (tipikusan a
    beálló vagy a berobbanó átlövő), a zárásnál ŐT kell kivenni — a
    lövő kizárása helyett a lepattanó-emberre kell fordulni. Ha szórt,
    a szokásos poszt-tartás a jobb.

    Visszatérés csapatonként: {"second_shots" (poszthoz kötött második
    lövés), "roles": {poszt: lövés}, "main_role", "share_pct",
    "verdict"} — a main_role/share_pct/verdict None, ha nincs meg az
    SCR_MIN_SHOTS, vagy egyik poszt sem éri el az SCR_SHARE_PCT-t.
    """
    from .event_detection import EventType, detect_shots
    from .roles import estimate_positions

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = SECOND_CHANCE_WINDOW_S * fps
    roles = estimate_positions(match, config)
    shots = [e for e in detect_shots(match, config)
             if e.type in (EventType.SHOT, EventType.GOAL)]

    out: dict = {side: {"second_shots": 0, "roles": {},
                        "main_role": None, "share_pct": None,
                        "verdict": None} for side in ("home", "away")}
    for i, e in enumerate(shots):
        if e.type == EventType.GOAL:
            continue
        for nxt in shots[i + 1:]:
            if nxt.t - e.t > win:
                break
            if nxt.team != e.team:
                break
            if nxt.player_id is not None:
                rec_role = roles[nxt.team.value].get(nxt.player_id)
                if rec_role is not None:
                    rec = out[nxt.team.value]
                    poszt = rec_role["poszt"]
                    rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1
                    rec["second_shots"] += 1
            break

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["second_shots"] >= SCR_MIN_SHOTS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["second_shots"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= SCR_SHARE_PCT:
                rec["verdict"] = (
                    f"a második rohamukat a(z) {poszt} viszi "
                    f"({share:.0f}%, {rec['second_shots']} második "
                    "lövésből) — a lövésünk zárása után az ELSŐ dolog "
                    "őt kivenni a lepattanóból, nem a lövőt nézni")
    return out


# Elzáró-poszt: ennyi poszthoz kötött elzárás kell az ítélethez, és
# ekkora részarány fölött mondjuk ki, hogy az elzárás-játékuk egy
# posztra épül.
SCR2_MIN_SCREENS = 3
SCR2_SHARE_PCT = 60.0


def screen_setter_roles(match: Match,
                        config: Optional[TacticsConfig] = None) -> dict:
    """Elzáró-poszt: MELYIK POSZTJUK áll elzárásba.

    Az elzárók rétege (screen_setters) az embert nevezi meg — ez a
    posztot: az elzárásokat az elzáró játékos posztjához írja. Így a
    minta akkor is látszik, ha a nevek meccsről meccsre cserélődnek.

    Edzőileg ez a váltás-terv: ha az elzárásaik rendre ugyanarról a
    posztról jönnek (tipikusan a beálló), a védekezés előre tudja,
    honnan érkezik a test — az ő oldalán hangos váltás vagy átcsúszás
    kell, és őt elölről kell fogni, mert nélküle a lövőjük nem marad
    tisztán. Ha az elzáró-játékuk szórt, poszt-szintű terv helyett a
    váltás-kommunikáció általános fegyelme véd.

    Visszatérés csapatonként (a TÁMADÓ oldal): {"screens" (poszthoz
    kötött elzárás), "roles": {poszt: elzárás}, "main_role",
    "share_pct", "verdict"} — az ítélet None, ha nincs meg az
    SCR2_MIN_SCREENS, vagy egyik poszt sem éri el az SCR2_SHARE_PCT-t.
    """
    from .roles import estimate_positions

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    scs = screen_setters(match, config)

    out: dict = {side: {"screens": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in scs[side]["players"]:
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["screens"])
            rec["screens"] += row["screens"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["screens"] >= SCR2_MIN_SCREENS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["screens"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= SCR2_SHARE_PCT:
                rec["verdict"] = (
                    f"az elzárásaik a(z) {poszt} posztról jönnek "
                    f"({share:.0f}%, {rec['screens']} elzárásból) — az"
                    " ő oldalán hangos váltás vagy átcsúszás kell, és"
                    " őt elölről kell fogni")
    return out


# Bejátszó-poszt: ennyi poszthoz kötött beálló-beadás kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy a
# beálló-játékuk egy posztról fut.
PFR_MIN_FEEDS = 4
PFR_SHARE_PCT = 60.0


def pivot_feeder_roles(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Bejátszó-poszt: MELYIK POSZTJUK játssza be a beállót.

    A beálló-kiszolgálók rétege (pivot_feeders) az embert nevezi meg
    — ez a posztot: a beállóhoz futó beadásokat a passzoló játékos
    posztjához írja. Így a minta akkor is látszik, ha a nevek
    meccsről meccsre cserélődnek.

    Edzőileg ez a beálló-vonal zárásának térképe: ha a beadásaik
    rendre ugyanarról a posztról jönnek (tipikusan az irányítótól),
    az ő kezén kell a beálló-vonalba lépni, és az ő oldalán indul a
    kettőzés — a bejátszó zárása többet ér, mint a beálló birkózása.
    Ha a bejátszásuk szórt, a beállót magát kell elöl fogni.

    Visszatérés csapatonként (a TÁMADÓ oldal): {"feeds" (poszthoz
    kötött beadás), "roles": {poszt: beadás}, "main_role",
    "share_pct", "verdict"} — az ítélet None, ha nincs meg a
    PFR_MIN_FEEDS, vagy egyik poszt sem éri el a PFR_SHARE_PCT-t.
    """
    from .roles import estimate_positions

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    pf = pivot_feeders(match, config)

    out: dict = {side: {"feeds": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in pf[side]["players"]:
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["feeds"])
            rec["feeds"] += row["feeds"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["feeds"] >= PFR_MIN_FEEDS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["feeds"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= PFR_SHARE_PCT:
                rec["verdict"] = (
                    f"a beálló-beadásaik a(z) {poszt} posztról jönnek "
                    f"({share:.0f}%, {rec['feeds']} beadásból) — az ő "
                    "kezén kell a beálló-vonalba lépni, és az ő "
                    "oldalán induljon a kettőzés")
    return out


# Kockáztató-poszt: ennyi poszthoz kötött hosszú-passz eladás kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy a hazárd
# labdáik egy posztról jönnek.
RPR_MIN_TO = 3
RPR_SHARE_PCT = 60.0


def risky_passer_roles(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Kockáztató-poszt: MELYIK POSZTJUK szórja el a hosszú labdákat.

    A kockázatos passzolók rétege (risky_passers) az embert nevezi
    meg — ez a posztot: a hosszú passzokból lett eladásokat a
    kiinduló játékos posztjához írja. Így a minta akkor is látszik,
    ha a nevek meccsről meccsre cserélődnek.

    Edzőileg ez a labdaszerzés-terv: ha a hazárd labdáik rendre
    ugyanarról a posztról indulnak (tipikusan az irányítótól), az ő
    hosszú passzsávjába kell beállni — a sávba lépés nála azonnal
    labdát hoz, és minden szerzés mögött nyitott pálya van. Saját
    csapatra: az egy poszton gyűlő eladás passz-technika edzés-téma.

    Visszatérés csapatonként (a TÁMADÓ oldal): {"turnovers" (poszthoz
    kötött hosszú-passz eladás), "roles": {poszt: eladás},
    "main_role", "share_pct", "verdict"} — az ítélet None, ha nincs
    meg az RPR_MIN_TO, vagy egyik poszt sem éri el az RPR_SHARE_PCT-t.
    """
    from .roles import estimate_positions

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    rp = risky_passers(match, config)

    out: dict = {side: {"turnovers": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in rp[side]["players"]:
            if not row["turnovers"]:
                continue
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["turnovers"])
            rec["turnovers"] += row["turnovers"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["turnovers"] >= RPR_MIN_TO:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["turnovers"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= RPR_SHARE_PCT:
                rec["verdict"] = (
                    f"a hazárd hosszú labdáik a(z) {poszt} posztról "
                    f"indulnak ({share:.0f}%, {rec['turnovers']} "
                    "elszórt hosszú passzból) — az ő passzsávjába "
                    "kell beállni: a sávba lépés nála azonnal labdát "
                    "hoz")
    return out


# Kiosztás-poszt: ennyi poszthoz kötött kiosztás kell az ítélethez,
# és ekkora részarány fölött mondjuk ki, hogy a betörés utáni labda
# egy posztra jár.
KOR_MIN_KICKOUTS = 4
KOR_SHARE_PCT = 60.0


def kickout_target_roles(match: Match,
                         config: Optional[TacticsConfig] = None) -> dict:
    """Kiosztás-poszt: MELYIK POSZTRA jár a betörés utáni labda.

    A kiosztás-célpont rétege (kickout_targets) az embert nevezi meg
    — ez a posztot: a betörés utáni kiosztásokat a fogadó játékos
    posztjához írja. Így a minta akkor is látszik, ha a nevek
    meccsről meccsre cserélődnek.

    Edzőileg ez a passzsáv-terv: ha a betöréseik után a labda rendre
    ugyanarra a posztra megy (tipikusan a túloldali átlövőre), annak
    a posztnak a védője előre elmozdulhat a passzsávba, és a
    betörésre indulhat a kettőzés — a kiosztás elveszti az értelmét.
    Ha a célpont szórt, a betörést magát kell megállítani.

    Visszatérés csapatonként (a TÁMADÓ oldal): {"kickouts" (poszthoz
    kötött kiosztás), "roles": {poszt: kiosztás}, "main_role",
    "share_pct", "verdict"} — az ítélet None, ha nincs meg a
    KOR_MIN_KICKOUTS, vagy egyik poszt sem éri el a KOR_SHARE_PCT-t.
    """
    from .roles import estimate_positions

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    ko = kickout_targets(match, config)

    out: dict = {side: {"kickouts": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in ko[side]["targets"]:
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["count"])
            rec["kickouts"] += row["count"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["kickouts"] >= KOR_MIN_KICKOUTS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["kickouts"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= KOR_SHARE_PCT:
                rec["verdict"] = (
                    f"a betöréseik utáni labda a(z) {poszt} posztra "
                    f"jár ({share:.0f}%, {rec['kickouts']} "
                    "kiosztásból) — az ő védője előre elmozdulhat a "
                    "passzsávba, a betörésre pedig indulhat a "
                    "kettőzés")
    return out


# Előkészítő-poszt: ennyi poszthoz kötött lövés-előkészítő passz kell
# az ítélethez, és ekkora részarány fölött mondjuk ki, hogy a
# lövéseik előkészítése egy posztról jön.
EPR_MIN_PASSES = 5
EPR_SHARE_PCT = 60.0
EPR_WINDOW_S = 4.0


def last_pass_roles(match: Match,
                    config: Optional[TacticsConfig] = None) -> dict:
    """Előkészítő-poszt: MELYIK POSZTJUK készíti elő a lövéseket.

    A gólpassz-poszt (role_assist_sources) csak a GÓLOK passzait
    nézi — ez minden lövését: minden felismert lövéshez megkeresi a
    lövő felé menő utolsó passzt az EPR_WINDOW_S ablakban, és a
    lövést a PASSZOLÓ posztjához írja. Így a teljes előkészítő
    munka látszik, nem csak a beérett gólok.

    Edzőileg ez a passzsáv-zárás nagyobb képe: ha a lövéseik
    előkészítése rendre egy posztról jön, az ő sávjának a zárásával
    a lövéseik előkészítetlenné válnak — a lövők maguktól elhalnak.
    Saját csapatra: a szervezés ne egy kézen fusson, kell a második
    előkészítő.

    Visszatérés csapatonként: {"passes" (poszthoz kötött
    előkészítés), "roles": {poszt: darab}, "main_role", "share_pct",
    "verdict"} — az ítélet None, ha nincs meg az EPR_MIN_PASSES,
    vagy egyik poszt sem éri el az EPR_SHARE_PCT-t.
    """
    from .decisions import detect_passes
    from .event_detection import EventType, detect_shots
    from .roles import estimate_positions

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = EPR_WINDOW_S * fps
    roles = estimate_positions(match, config)
    passes = detect_passes(match, config)

    out: dict = {side: {"passes": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for e in detect_shots(match, config):
        if e.type not in (EventType.SHOT, EventType.GOAL):
            continue
        if e.player_id is None:
            continue
        best = None
        for p in passes:
            if not (0 <= e.t - p.t <= win) or p.team != e.team:
                continue
            if (p.receiver_id != e.player_id
                    or p.passer_id == e.player_id):
                continue
            if best is None or p.t > best.t:
                best = p
        if best is None:
            continue
        side = e.team.value
        rec_role = roles[side].get(best.passer_id)
        if rec_role is None:
            continue
        poszt = rec_role["poszt"]
        rec = out[side]
        rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1
        rec["passes"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["passes"] >= EPR_MIN_PASSES:
            poszt = max(rec["roles"], key=lambda p2: rec["roles"][p2])
            share = 100.0 * rec["roles"][poszt] / rec["passes"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= EPR_SHARE_PCT:
                rec["verdict"] = (
                    f"a lövéseik előkészítése {share:.0f}%-ban a(z) "
                    f"{poszt} posztról jön ({rec['passes']} "
                    "előkészítő passzból) — az ő sávjának zárásával"
                    " a lövéseik előkészítetlenné válnak, és a "
                    "lövők maguktól elhalnak")
    return out


# Hátrapassz-poszt: e méternyi kapu-távolság-növekedés fölött hátra-
# passz egy átadás; ennyi poszthoz kötött hátra-passz kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy a játék egy
# posztnál fordul vissza.
BPR_BACK_M = 1.0
BPR_MIN_PASSES = 5
BPR_SHARE_PCT = 60.0


def backward_pass_roles(match: Match,
                        config: Optional[TacticsConfig] = None) -> dict:
    """Hátrapassz-poszt: MELYIK POSZTJUKNÁL fordul vissza a játék.

    A passz-irány rétege (pass_direction) csapat-szinten mondja meg,
    mennyit játszanak hátrafelé — ez posztonként: a kaputól
    BPR_BACK_M méterrel távolabbi társhoz menő passzokat a passzoló
    posztjához írja. Így látszik, kinél fordul rendre vissza a
    lendület.

    Edzőileg ez a pressz-jutalom: amelyik posztjuk nyomás alatt
    hátrafelé menekül, arra rá lehet menni — a hátra-passza után a
    fal feljebb tolható, és a támadásuk újraindul nulláról. Saját
    csapatra: a posztnak előre-játék bátorság kell (betörés vagy
    beadás hátra-passz helyett).

    Visszatérés csapatonként: {"passes" (poszthoz kötött
    hátra-passz), "roles": {poszt: darab}, "main_role", "share_pct",
    "verdict"} — az ítélet None, ha nincs meg a BPR_MIN_PASSES, vagy
    egyik poszt sem éri el a BPR_SHARE_PCT-t.
    """
    from .decisions import detect_passes
    from .roles import estimate_positions

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)

    out: dict = {side: {"passes": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    frames_by_t = {f.t: f for f in match.frames}
    for p in detect_passes(match, config):
        if p.passer_pos is None:
            continue
        fr = frames_by_t.get(p.t)
        if fr is None:
            continue
        receiver = next((q for q in fr.players
                         if q.track_id == p.receiver_id), None)
        if receiver is None:
            continue
        goal_x = config.attacks_toward_x(p.team)
        d_passer = abs(p.passer_pos.x - goal_x)
        d_receiver = abs(receiver.x - goal_x)
        if d_receiver - d_passer < BPR_BACK_M:
            continue
        side = p.team.value
        rec_role = roles[side].get(p.passer_id)
        if rec_role is None:
            continue
        poszt = rec_role["poszt"]
        rec = out[side]
        rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1
        rec["passes"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["passes"] >= BPR_MIN_PASSES:
            poszt = max(rec["roles"], key=lambda p2: rec["roles"][p2])
            share = 100.0 * rec["roles"][poszt] / rec["passes"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= BPR_SHARE_PCT:
                rec["verdict"] = (
                    f"a játék {share:.0f}%-ban a(z) {poszt} "
                    f"posztjuknál fordul vissza ({rec['passes']} "
                    "hátra-passzból) — nyomás alatt hátrafelé "
                    "menekül: a pressz rá jutalmat hoz, a "
                    "hátra-passza után a fal feljebb tolható")
    return out


# Áttörő-poszt: ennyi poszthoz kötött betörés kell az ítélethez, és
# ekkora részarány fölött mondjuk ki, hogy a falat egy posztjuk
# nyitja szét.
BTR_MIN_ENTRIES = 4
BTR_SHARE_PCT = 60.0


def breakthrough_roles(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Áttörő-poszt: MELYIK POSZTJUK jut be labdával a falba.

    Az áttörő játékosok rétege (breakthrough_players) az embert
    nevezi meg — ez a posztot: a labdás betöréseket (a kapu közeli
    körzetébe lépés) a betörő posztjához írja. Így a minta akkor is
    látszik, ha a nevek meccsről meccsre cserélődnek.

    Edzőileg ez a kettőzés-terv belső köre: amelyik posztjuk rendre
    szétnyitja a falat, annak a védője segítőt kap, a betörés
    vonalát pedig testtel kell zárni — nélküle a többiek kívül
    rekednek. Saját csapatra: az egy emberen álló betörés-játék
    kockázat, kell a második áttörő.

    Visszatérés csapatonként: {"entries" (poszthoz kötött betörés),
    "roles": {poszt: darab}, "main_role", "share_pct", "verdict"} —
    az ítélet None, ha nincs meg a BTR_MIN_ENTRIES, vagy egyik
    poszt sem éri el a BTR_SHARE_PCT-t.
    """
    from .roles import estimate_positions

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    bp = breakthrough_players(match, config)

    out: dict = {side: {"entries": 0, "roles": {},
                        "main_role": None, "share_pct": None,
                        "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in bp[side]["players"]:
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["entries"])
            rec["entries"] += row["entries"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["entries"] >= BTR_MIN_ENTRIES:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["entries"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= BTR_SHARE_PCT:
                rec["verdict"] = (
                    f"a falat {share:.0f}%-ban a(z) {poszt} "
                    f"posztjuk nyitja szét ({rec['entries']} labdás"
                    " betörésből) — a védője segítőt kapjon, és a "
                    "betörés vonalát testtel kell zárni: nélküle a "
                    "többiek kívül rekednek")
    return out


# Elzárópáros-poszt: ennyi posztpárhoz kötött elzárt lövés kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy az
# elzárás-játékuk egy posztpárra jár.
SPP_MIN_SHOTS = 3
SPP_SHARE_PCT = 60.0


def screen_pair_roles(match: Match,
                      config: Optional[TacticsConfig] = None) -> dict:
    """Elzárópáros-poszt: MELYIK POSZTPÁRRA jár az elzárás-játékuk.

    Az elzárás-páros rétege (screen_pairs) a két embert nevezi meg —
    ez a posztpárt: minden elzárásból leadott lövést az (elzáró
    poszt → lövő poszt) párhoz ír. Így a bejáratott kettős akkor is
    látszik, ha a nevek meccsről meccsre cserélődnek.

    Edzőileg a páros ellen párban készül a védekezés: az elzáró
    posztjának őrzője előre szól, a lövő posztjának őrzője pedig az
    elzárás ELŐTT lép ki, hogy ne szoruljon mögé. Saját csapatra: a
    figura másik oldalra is járjon, különben kiszámítható.

    Visszatérés csapatonként: {"shots" (párhoz kötött elzárt lövés),
    "roles": {"elzáró→lövő": darab}, "main_role" (a fő posztpár),
    "share_pct", "verdict"} — az ítélet None, ha nincs meg az
    SPP_MIN_SHOTS, vagy egyik pár sem éri el az SPP_SHARE_PCT-t.
    """
    from .roles import estimate_positions

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    sp = screen_pairs(match, config)

    out: dict = {side: {"shots": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in sp[side]["pairs"]:
            setter = roles[side].get(row["setter_id"])
            shooter = roles[side].get(row["shooter_id"])
            if setter is None or shooter is None:
                continue
            kulcs = f"{setter['poszt']}→{shooter['poszt']}"
            rec["roles"][kulcs] = (rec["roles"].get(kulcs, 0)
                                   + row["shots"])
            rec["shots"] += row["shots"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["shots"] >= SPP_MIN_SHOTS:
            par = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][par] / rec["shots"]
            rec["main_role"] = par
            rec["share_pct"] = round(share, 1)
            if share >= SPP_SHARE_PCT:
                rec["verdict"] = (
                    f"az elzárás-játékuk a(z) {par} posztpárra jár "
                    f"({share:.0f}%, {rec['shots']} elzárt "
                    "lövésből) — a védekezés párban készül: az "
                    "elzáró őrzője előre szól, a lövőé az elzárás "
                    "előtt lép ki")
    return out
