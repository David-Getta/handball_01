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
