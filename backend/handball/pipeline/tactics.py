"""
[2. fázis] Taktikai értelmezés — labdabirtoklás, fázis-szegmentálás, védekezési forma.

A kész Tracking-ből taktikai fogalmakat építünk (tiszta adatfeldolgozás, videó
nélkül tesztelhető):

1. Labdabirtoklás: melyik csapat birtokolja a labdát (a labdához legközelebbi
   játékos csapata, ha elég közel van — különben "senki/szabad labda").
2. Fázis-szegmentálás: HAZAI_TÁMADÁS / VENDÉG_TÁMADÁS / ÁTMENET, a birtoklásból és
   a labda térfél-helyzetéből.
3. Védekezési forma: a védekező csapat játékosainak a saját kaputól mért
   mélységéből 6-0 / 5-1 / 4-2 / 3-2-1 stb.

A pálya hossztengelye x (0..40). Konfigurálható, melyik kapu felé támad a hazai
(alapból a +x, azaz x=40 felé; a hazai saját kapuja x=0).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ..models.tracking import Match, Frame, Team
from .calibration import COURT_LENGTH_M


# ---- Konfiguráció ----------------------------------------------------------

@dataclass
class TacticsConfig:
    """A taktikai értelmezés beállításai.

    - home_attacks_positive: a HAZAI a +x (x=40) kapu felé támad-e (alap: igen).
      Ebből adódik mindkét csapat saját kapujának x-e és támadó térfele.
    - possession_radius_m: a labdától ekkora távolságon belül lévő legközelebbi
      játékos "birtokolja" a labdát; ennél messzebb "szabad labda".
    """
    home_attacks_positive: bool = True
    possession_radius_m: float = 3.0

    def own_goal_x(self, team: Team) -> float:
        """Az adott csapat SAJÁT kapujának x-koordinátája (amit véd)."""
        if team == Team.HOME:
            return 0.0 if self.home_attacks_positive else COURT_LENGTH_M
        return COURT_LENGTH_M if self.home_attacks_positive else 0.0

    def attacks_toward_x(self, team: Team) -> float:
        """Az a kapu-x, amely felé a csapat TÁMAD (az ellenfél kapuja)."""
        return COURT_LENGTH_M - self.own_goal_x(team)


# ---- Labdabirtoklás --------------------------------------------------------

def possession_team(frame: Frame, config: TacticsConfig) -> Optional[Team]:
    """A labdát birtokló csapat: a labdához legközelebbi játékos csapata.

    Ha nincs labda, vagy a legközelebbi játékos is távolabb van a sugárnál,
    None ("szabad labda" / nincs egyértelmű birtokos).
    """
    from .primitive_cache import cached_frame
    return cached_frame("possession_team", frame, config,
                        lambda: _possession_team(frame, config))


def _possession_team(frame: Frame, config: TacticsConfig) -> Optional[Team]:
    """A tényleges birtokos-csapat számítás (lásd `possession_team`)."""
    ball = frame.ball
    if ball is None or not frame.players:
        return None
    nearest = min(
        frame.players,
        key=lambda p: math.hypot(p.x - ball.x, p.y - ball.y),
    )
    dist = math.hypot(nearest.x - ball.x, nearest.y - ball.y)
    if dist > config.possession_radius_m:
        return None
    return nearest.team


# ---- Fázis-szegmentálás ----------------------------------------------------

class Phase(str, Enum):
    """A játék pillanatnyi fázisa."""
    HOME_ATTACK = "home_attack"   # a hazai szervezett támadása
    AWAY_ATTACK = "away_attack"   # a vendég szervezett támadása
    TRANSITION = "transition"     # átmenet / szabad labda / felépítés a saját térfélen
    UNKNOWN = "unknown"           # nincs elég adat (pl. nincs labda)


def classify_phase(frame: Frame, config: TacticsConfig) -> Phase:
    """Egy frame fázisa a birtoklásból és a labda térfél-helyzetéből.

    Egy csapat akkor van "szervezett támadásban", ha birtokolja a labdát ÉS a
    labda az ő TÁMADÓ térfelén van. Minden más (szabad labda, saját térfélen
    felépítés) ÁTMENET. Labda nélkül UNKNOWN.
    """
    from .primitive_cache import cached_frame
    return cached_frame("classify_phase", frame, config,
                        lambda: _classify_phase(frame, config))


def _classify_phase(frame: Frame, config: TacticsConfig) -> Phase:
    """A tényleges fázis-besorolás (lásd `classify_phase`)."""
    ball = frame.ball
    if ball is None:
        return Phase.UNKNOWN
    poss = possession_team(frame, config)
    if poss is None:
        return Phase.TRANSITION

    mid = COURT_LENGTH_M / 2.0
    attacks_positive = (config.attacks_toward_x(poss) > mid)
    in_attacking_half = (ball.x > mid) if attacks_positive else (ball.x < mid)
    if not in_attacking_half:
        return Phase.TRANSITION
    return Phase.HOME_ATTACK if poss == Team.HOME else Phase.AWAY_ATTACK


def segment_phases(match: Match, config: Optional[TacticsConfig] = None) -> list[Phase]:
    """A teljes meccs fázis-címkéi frame-enként."""
    config = config or TacticsConfig()
    return [classify_phase(f, config) for f in match.frames]


def phase_percentages(match: Match, config: Optional[TacticsConfig] = None) -> dict[str, float]:
    """A fázisok megoszlása (%) a meccsen — gyors taktikai összkép."""
    phases = segment_phases(match, config)
    if not phases:
        return {p.value: 0.0 for p in Phase}
    counts: dict[str, int] = {p.value: 0 for p in Phase}
    for ph in phases:
        counts[ph.value] += 1
    n = len(phases)
    return {k: 100.0 * v / n for k, v in counts.items()}


# ---- Védekezési forma ------------------------------------------------------

@dataclass
class TempoMetrics:
    """Tempó-metrikák a meccs egészére — mennyire gyors/szervezett a játék.

    - possessions:           birtoklás-szakaszok száma (hány külön labdabirtoklás).
    - avg_attack_duration_s: az átlagos szervezett támadás hossza (másodperc).
    - transition_pct:        az átmenet (szabad labda / felépítés) aránya (%).
    - avg_ball_speed_ms:     a labda átlagsebessége (m/s) — tempó-indikátor.
    """
    possessions: int
    avg_attack_duration_s: float
    transition_pct: float
    avg_ball_speed_ms: float


def count_possession_segments(match: Match, config: Optional[TacticsConfig] = None) -> int:
    """Hány külön labdabirtoklás volt (csapatváltáskor új szakasz).

    A szabad labda (None) nem szakítja meg: ha ugyanaz a csapat szerzi vissza, az
    nem új birtoklás. Új szakaszt csak az számít, ha MÁSIK csapaté lesz a labda.
    """
    config = config or TacticsConfig()
    prev: Optional[Team] = None
    count = 0
    for f in match.frames:
        poss = possession_team(f, config)
        if poss is not None and poss != prev:
            count += 1
            prev = poss
    return count


def _avg_attack_duration_s(match: Match, config: TacticsConfig) -> float:
    """A szervezett támadás-szakaszok átlagos hossza másodpercben.

    Az egymást követő, AZONOS támadó-fázisú frame-ek egy szakaszt alkotnak.
    """
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    runs: list[int] = []
    current = 0
    current_phase: Optional[Phase] = None
    attack_phases = {Phase.HOME_ATTACK, Phase.AWAY_ATTACK}
    for f in match.frames:
        ph = classify_phase(f, config)
        if ph in attack_phases:
            if ph == current_phase:
                current += 1
            else:
                if current > 0:
                    runs.append(current)
                current = 1
                current_phase = ph
        else:
            if current > 0:
                runs.append(current)
            current = 0
            current_phase = None
    if current > 0:
        runs.append(current)
    if not runs:
        return 0.0
    return (sum(runs) / len(runs)) / fps


# Passzív-veszély: ennél hosszabb támadás már a passzív játék (üres
# figyelmeztetés / elvett labda) kockázatát hordozza.
SLOW_ATTACK_S = 35.0


def slow_attacks(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """Elhúzódó (passzív-veszélyes) támadások csapatonként.

    Az egybefüggő támadó-fázis szakaszokat mérjük; a SLOW_ATTACK_S-nél
    hosszabb szakasz "elhúzódó". Ezek aránya a türelmes (vagy ötlettelen)
    játék jele — a passzív játék felé sodródás kockázata.

    Visszatérés csapatonként: {"attacks", "slow", "slow_pct",
    "longest_s"}.
    """
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    out = {side: {"attacks": 0, "slow": 0, "slow_pct": 0.0, "longest_s": 0.0}
           for side in ("home", "away")}

    current = 0
    current_phase: Optional[Phase] = None

    def close_run():
        nonlocal current, current_phase
        if current > 0 and current_phase is not None:
            side = ("home" if current_phase == Phase.HOME_ATTACK else "away")
            rec = out[side]
            dur = current / fps
            rec["attacks"] += 1
            rec["longest_s"] = max(rec["longest_s"], dur)
            if dur > SLOW_ATTACK_S:
                rec["slow"] += 1
        current = 0
        current_phase = None

    attack_phases = {Phase.HOME_ATTACK, Phase.AWAY_ATTACK}
    for f in match.frames:
        ph = classify_phase(f, config)
        if ph in attack_phases:
            if ph == current_phase:
                current += 1
            else:
                close_run()
                current = 1
                current_phase = ph
        else:
            close_run()
    close_run()

    for rec in out.values():
        rec["longest_s"] = round(rec["longest_s"], 1)
        if rec["attacks"]:
            rec["slow_pct"] = round(100.0 * rec["slow"] / rec["attacks"], 1)
    return out


# Elhúzódó támadás ára: megéri-e a passzív-veszélyes hosszú akció.
SAC_TAIL_S = 4.0      # a szakasz vége után ennyin belüli gól még az akcióé
SAC_MIN_SLOW = 3      # ennyi elhúzódó támadás alatt nincs ítélet
SAC_IDLE_PCT = 25.0   # gól-arány ez alatt: üresjárat
SAC_PAY_PCT = 60.0    # gól-arány e felett: érő türelem


def slow_attack_cost(match: Match,
                     config: Optional[TacticsConfig] = None) -> dict:
    """Elhúzódó támadás ára: a passzív-veszélyes hosszú akciók HOZAMA.

    Az elhúzódó támadások (slow_attacks) a kitettséget mérik — ez a
    megtérülésüket: a SLOW_ATTACK_S-nél hosszabb támadó-szakaszok
    közül hány zárul góllal (a szakasz alatt vagy SAC_TAIL_S-en
    belül utána). A türelem önmagában nem érték: ha a hosszú akció
    rendre üresen fut ki, az nem türelmes játék, hanem terv nélküli
    körbejáratás a passzív jel árnyékában.

    Edzőileg: az üresjáratos hosszú támadás ellen elég türelmesen,
    hiba nélkül védekezni — a passzív jel a védőnek dolgozik; a
    saját oldalon a támadás-lezárást (időre futtatott figura) kell
    edzeni. Aki viszont a hosszú akcióit is gólra váltja, az ellen a
    35. másodpercben is teljes koncentráció kell a faltól.

    Visszatérés csapatonként: {"slow", "scored", "scored_pct",
    "verdict"} — a verdict "az elhúzódó támadásaik üresen zárulnak"
    (SAC_IDLE_PCT alatt), "az elhúzódó támadásaikat gólra váltják"
    (SAC_PAY_PCT felett); kevés mintánál (SAC_MIN_SLOW alatt,
    scored_pct is None) és a köztes sávban None.
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    out = {side: {"slow": 0, "scored": 0, "scored_pct": None,
                  "verdict": None} for side in ("home", "away")}

    goals = [(e.t, e.team.value) for e in detect_shots(match, config)
             if e.type == EventType.GOAL]
    tail = round(SAC_TAIL_S * fps)
    min_len = SLOW_ATTACK_S * fps

    spans = []  # (oldal, kezdő frame, záró frame)
    current = 0
    current_phase: Optional[Phase] = None
    start_f: Optional[int] = None

    def close_run(end_f: int):
        nonlocal current, current_phase, start_f
        if current > min_len and current_phase is not None:
            side = ("home" if current_phase == Phase.HOME_ATTACK
                    else "away")
            spans.append((side, start_f, end_f))
        current = 0
        current_phase = None
        start_f = None

    attack_phases = {Phase.HOME_ATTACK, Phase.AWAY_ATTACK}
    for f in match.frames:
        ph = classify_phase(f, config)
        if ph in attack_phases:
            if ph == current_phase:
                current += 1
            else:
                close_run(f.t)
                current = 1
                current_phase = ph
                start_f = f.t
        else:
            close_run(f.t)
    if match.frames:
        close_run(match.frames[-1].t)

    for (side, a, b) in spans:
        rec = out[side]
        rec["slow"] += 1
        if any(tm == side and a <= t <= b + tail for (t, tm) in goals):
            rec["scored"] += 1
    for rec in out.values():
        if rec["slow"] >= SAC_MIN_SLOW:
            rec["scored_pct"] = round(
                100.0 * rec["scored"] / rec["slow"], 1)
            if rec["scored_pct"] <= SAC_IDLE_PCT:
                rec["verdict"] = "az elhúzódó támadásaik üresen zárulnak"
            elif rec["scored_pct"] >= SAC_PAY_PCT:
                rec["verdict"] = "az elhúzódó támadásaikat gólra váltják"
    return out


# Támadás-oldal megoszlás: ekkora többség számít "súlypontnak".
def attack_sides(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """Melyik oldalon folyik a támadójáték — bal/közép/jobb sáv szerint.

    A támadó-fázisú kockákon a labda KERESZTIRÁNYÚ (y) helyét soroljuk
    harmadokba, a TÁMADÁS IRÁNYA szerint normálva (a "bal" a támadó
    csapat bal keze felőli oldal, mindkét kapunál ugyanazt jelenti).
    Ebből látszik, melyik szárnyra épül a játék.

    Visszatérés csapatonként: {"bal", "közép", "jobb": %, "frames": n}.
    """
    from .calibration import COURT_WIDTH_M

    config = config or TacticsConfig()
    counts = {side: {"bal": 0, "közép": 0, "jobb": 0}
              for side in ("home", "away")}
    for f in match.frames:
        ph = classify_phase(f, config)
        if ph not in (Phase.HOME_ATTACK, Phase.AWAY_ATTACK) or f.ball is None:
            continue
        team = Team.HOME if ph == Phase.HOME_ATTACK else Team.AWAY
        third = (0 if f.ball.y < COURT_WIDTH_M / 3 else
                 1 if f.ball.y < 2 * COURT_WIDTH_M / 3 else 2)
        # A +x kapura támadva az alacsony y a támadó BAL keze; a -x
        # kapunál tükrözve (mint a lövés-zónáknál).
        attacks_positive = config.attacks_toward_x(team) > COURT_LENGTH_M / 2
        if not attacks_positive:
            third = 2 - third
        key = ("bal", "közép", "jobb")[third]
        counts[team.value][key] += 1

    out = {}
    for side in ("home", "away"):
        total = sum(counts[side].values())
        out[side] = {
            k: (round(100.0 * v / total, 1) if total else 0.0)
            for k, v in counts[side].items()
        }
        out[side]["frames"] = total
    return out


# Oldal-váltás a szünetre: a támadó oldal-súlyok a két félidőben.
SDS_MIN_FRAMES_HALF = 100   # félidőnként ennyi támadó-kocka kell
SDS_MAIN_PCT = 40.0         # a fő oldal részaránya a kimondáshoz


def attack_side_shift(match: Match,
                      config: Optional[TacticsConfig] = None) -> dict:
    """Oldal-váltás a szünetre: MÁSIK SZÁRNYRA teszik-e át a játékot.

    A támadás-oldal megoszlás (attack_sides) a meccs egészét nézi —
    ez a szünetet: félidőnként megkeressük a támadójáték FŐ oldalát
    (a támadó-fázisú kockák bal/közép/jobb megoszlásának uralkodó
    sávját, a támadás iránya szerint normálva), és összevetjük a
    kettőt. Aki a szünet után szárnyat vált, annál az első félidei
    kép alapján beállított fal-súlypont a második félidőben már
    rossz oldalon áll.

    Edzőileg: az oldalt váltó csapat ellen a szünet utáni első öt
    percben újra kell olvasni a súlypontot, és a fal erős emberét
    (meg a kettőzést) a másik oldalra tenni; a saját oldalon ez
    fegyver — a bejáratott szárny a szünet után tudatosan váltható.

    Visszatérés csapatonként: {"fh_frames", "sh_frames", "fh", "sh"
    (bal/közép/jobb %), "fh_counts", "sh_counts" (kocka-darabszámok),
    "fh_main", "sh_main", "verdict"} — a
    fh_main/sh_main None kevés kockánál vagy SDS_MAIN_PCT alatti
    uralkodó oldalnál; a verdict "a szünet után oldalt váltanak
    (X → Y)" / None.
    """
    from .calibration import COURT_WIDTH_M
    from .halftime import detect_halftime

    config = config or TacticsConfig()
    lanes = ("bal", "közép", "jobb")
    out = {side: {"fh_frames": 0, "sh_frames": 0,
                  "fh": {k: 0.0 for k in lanes},
                  "sh": {k: 0.0 for k in lanes},
                  "fh_counts": {k: 0 for k in lanes},
                  "sh_counts": {k: 0 for k in lanes},
                  "fh_main": None, "sh_main": None, "verdict": None}
           for side in ("home", "away")}
    ht = detect_halftime(match)
    if ht is None:
        return out
    counts = {side: {"fh": {k: 0 for k in lanes},
                     "sh": {k: 0 for k in lanes}}
              for side in ("home", "away")}
    for f in match.frames:
        ph = classify_phase(f, config)
        if ph not in (Phase.HOME_ATTACK, Phase.AWAY_ATTACK) \
                or f.ball is None:
            continue
        team = Team.HOME if ph == Phase.HOME_ATTACK else Team.AWAY
        third = (0 if f.ball.y < COURT_WIDTH_M / 3 else
                 1 if f.ball.y < 2 * COURT_WIDTH_M / 3 else 2)
        attacks_positive = (config.attacks_toward_x(team)
                            > COURT_LENGTH_M / 2)
        if not attacks_positive:
            third = 2 - third
        half = "fh" if f.t <= ht else "sh"
        counts[team.value][half][lanes[third]] += 1
    for side in ("home", "away"):
        rec = out[side]
        for half in ("fh", "sh"):
            total = sum(counts[side][half].values())
            rec[half + "_frames"] = total
            rec[half + "_counts"] = dict(counts[side][half])
            if not total:
                continue
            for k in lanes:
                rec[half][k] = round(
                    100.0 * counts[side][half][k] / total, 1)
            if total >= SDS_MIN_FRAMES_HALF:
                main = max(lanes, key=lambda k: rec[half][k])
                if rec[half][main] >= SDS_MAIN_PCT:
                    rec[half + "_main"] = main
        if rec["fh_main"] and rec["sh_main"] \
                and rec["fh_main"] != rec["sh_main"]:
            rec["verdict"] = (f"a szünet után oldalt váltanak "
                              f"({rec['fh_main']} → {rec['sh_main']})")
    return out


# Forma elleni hatékonyság: pár kockával a lövés ELŐTT nézzük a védő-
# formát (a lövés pillanatában a fal már felbomlóban lehet).
FORMATION_LOOKBACK = 12


def efficiency_vs_formation(match: Match,
                            config: Optional[TacticsConfig] = None) -> dict:
    """Támadó-hatékonyság a VÉDŐFORMA szerint: melyik fal ellen megy.

    Minden lövésnél/gólnál a védekező csapat formáját a lövés előtti
    kockán (FORMATION_LOOKBACK-kel korábban) olvassuk le, és formánként
    számoljuk a támadó csapat lövéseit/góljait. Ebből látszik, melyik
    védekezési forma fogja meg az adott csapatot — közvetlen "miben
    állj fel ellenük" adat.

    Visszatérés TÁMADÓ csapatonként: {forma: {"shots", "goals",
    "goal_pct"}} — csak a felismert (nem "?") formák.
    """
    from .calibration import COURT_LENGTH_M as _L  # noqa: F401 (doksi)
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    frames_by_t = {f.t: f for f in match.frames}
    out: dict = {"home": {}, "away": {}}

    for e in detect_shots(match, config):
        if e.type not in (EventType.SHOT, EventType.GOAL):
            continue
        fr = frames_by_t.get(max(0, e.t - FORMATION_LOOKBACK))
        if fr is None:
            continue
        defending = Team.AWAY if e.team == Team.HOME else Team.HOME
        form = detect_formation(fr, defending, config)
        label = form.label
        if not label or label == "?" or form.defenders < 4:
            continue  # kevés látott védő — a forma-címke nem megbízható
        rec = out[e.team.value].setdefault(label,
                                           {"shots": 0, "goals": 0,
                                            "goal_pct": 0.0})
        rec["shots"] += 1
        if e.type == EventType.GOAL:
            rec["goals"] += 1

    for side in ("home", "away"):
        for rec in out[side].values():
            rec["goal_pct"] = round(100.0 * rec["goals"] / rec["shots"], 1)
        out[side] = dict(sorted(out[side].items(),
                                key=lambda kv: -kv[1]["shots"]))
    return out


def _avg_ball_speed_ms(match: Match) -> float:
    """A labda átlagos sebessége (m/s) az egymást követő, labdás frame-ekből."""
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    dist = 0.0
    steps = 0
    prev = None
    for f in match.frames:
        b = f.ball
        if b is not None and prev is not None:
            dist += math.hypot(b.x - prev[0], b.y - prev[1])
            steps += 1
        prev = (b.x, b.y) if b is not None else None
    if steps == 0:
        return 0.0
    return dist / (steps / fps)


def compute_tempo(match: Match, config: Optional[TacticsConfig] = None) -> TempoMetrics:
    """A meccs tempó-metrikái egyben."""
    config = config or TacticsConfig()
    pct = phase_percentages(match, config)
    return TempoMetrics(
        possessions=count_possession_segments(match, config),
        avg_attack_duration_s=_avg_attack_duration_s(match, config),
        transition_pct=pct.get(Phase.TRANSITION.value, 0.0),
        avg_ball_speed_ms=_avg_ball_speed_ms(match),
    )


def team_style_profile(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """Csapat-stílusprofil: a taktikai jellemzők egy összegzésben.

    Egy helyen adja a fázis-megoszlást, a csapatonkénti leggyakoribb védekezési
    formát és a tempó-metrikákat — ez a "így játszik ez a csapat" összkép alapja
    (a vízió "csapatstílus tanulása" része).
    """
    config = config or TacticsConfig()
    tempo = compute_tempo(match, config)
    return {
        "phase_percentages": phase_percentages(match, config),
        "defense_formations": most_common_formations(match, config),
        "tempo": {
            "possessions": tempo.possessions,
            "avg_attack_duration_s": tempo.avg_attack_duration_s,
            "transition_pct": tempo.transition_pct,
            "avg_ball_speed_ms": tempo.avg_ball_speed_ms,
        },
    }


@dataclass
class FormationResult:
    """A védekező csapat formája + a mélységi sávok létszáma.

    - label:        emberi olvasatú címke (pl. "6-0", "5-1", "3-2-1", vagy a sávok
                    leírása, ha nem tipikus).
    - back/mid/high: hány védő van a SAJÁT kaputól mért mélységi sávokban
                    (hátsó ~6 m-es vonal / közép / előretolt).
    - defenders:    a figyelembe vett mezőnyvédők száma (kapus nélkül).
    """
    label: str
    back: int
    mid: int
    high: int
    defenders: int


# A mélységi sávok határai (méter a saját kaputól), a 6/9 m-es vonalakhoz igazítva.
_BACK_MAX = 7.0    # hátsó sáv: a 6 m-es vonal környéke
_MID_MAX = 10.5    # közép sáv: a 9 m-es vonal környéke
_GK_MAX = 2.0      # ennél közelebb a kapuhoz: kapusnak vesszük (kihagyjuk)


def detect_formation(frame: Frame, defending_team: Team,
                     config: Optional[TacticsConfig] = None) -> FormationResult:
    """A védekező csapat formáját adja a játékosok mélységéből.

    A saját kaputól mért távolság (mélység) alapján a védőket három sávba soroljuk
    (hátsó / közép / előretolt), és ebből nevezzük el a formát. A kaput nagyon
    közelről "őrző" játékost kapusnak vesszük és kihagyjuk.
    """
    config = config or TacticsConfig()
    goal_x = config.own_goal_x(defending_team)

    back = mid = high = 0
    for p in frame.players:
        if p.team != defending_team:
            continue
        depth = abs(p.x - goal_x)
        if depth <= _GK_MAX:
            continue  # kapus
        if depth <= _BACK_MAX:
            back += 1
        elif depth <= _MID_MAX:
            mid += 1
        else:
            high += 1

    defenders = back + mid + high
    label = _formation_label(back, mid, high)
    return FormationResult(label=label, back=back, mid=mid, high=high, defenders=defenders)


def most_common_formations(match: Match,
                           config: Optional[TacticsConfig] = None) -> dict[str, str]:
    """Csapatonként a leggyakoribb védekezési forma (amikor ÉPP VÉDEKEZIK).

    Egy csapat akkor védekezik, amikor az ellenfél támad (a fázis a másik csapat
    támadása). Ezeken a frame-eken megnézzük a védő forma címkéjét, és csapatonként
    a leggyakoribbat adjuk vissza. Ha egy csapat nem védekezett, "—".
    """
    config = config or TacticsConfig()
    tally: dict[Team, dict[str, int]] = {Team.HOME: {}, Team.AWAY: {}}
    for f in match.frames:
        phase = classify_phase(f, config)
        if phase == Phase.HOME_ATTACK:
            defending = Team.AWAY
        elif phase == Phase.AWAY_ATTACK:
            defending = Team.HOME
        else:
            continue
        label = detect_formation(f, defending, config).label
        tally[defending][label] = tally[defending].get(label, 0) + 1

    result: dict[str, str] = {}
    for team, labels in tally.items():
        if labels:
            result[team.value] = max(labels.items(), key=lambda kv: kv[1])[0]
        else:
            result[team.value] = "—"
    return result


def _formation_label(back: int, mid: int, high: int) -> str:
    """A sáv-létszámokból a szokásos kézilabda formanevet adja.

    A formákat a kézilabda-konvenció szerint nevezzük (hátsó-előre haladva):
    6-0 (mind hátul), 5-1 (egy előretolt), 4-2, 3-2-1 (három lépcső), 3-3.
    Ha nem tipikus, a sávok számával írjuk le.
    """
    advanced = mid + high
    total = back + mid + high
    if total == 6:
        if advanced == 0:
            return "6-0"
        if advanced == 1:
            return "5-1"
        if mid == 2 and high == 0:
            return "4-2"
        if back == 3 and mid == 2 and high == 1:
            return "3-2-1"
        if back == 3 and advanced == 3:
            return "3-3"
    # Nem tipikus / nem 6 védő: leíró címke a sávokkal.
    return f"{back}-{mid}-{high} (hátsó-közép-előre)"


# Területi fölény: ennyi birtokos kocka kell az ítélethez; e fölött a csapat
# az ellenfél térfelére szorítja a játékot, ez alatt a saját térfelére szorul.
TILT_MIN_FRAMES = 100
TILT_HIGH_PCT = 65.0
TILT_LOW_PCT = 45.0


def field_tilt(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """Területi fölény (field tilt): a csapat labdabirtoklásának mekkora
    része zajlik az ELLENFÉL térfelén.

    Nem azt méri, MENNYIT birtokolja a labdát (possession), hanem hogy HOL:
    a magas arány azt jelenti, hogy a csapat az ellenfél kapuja elé szorítja
    a játékot (területi nyomás), az alacsony azt, hogy a birtoklása a saját
    térfelén ragad (kihozási gondok / prés alatt van).

    Visszatérés csapatonként:
      {"frames", "opp_half_frames", "tilt_pct"} — a birtokos kockák száma,
    ebből az ellenfél térfelén lévők, és az arány (%). tilt_pct None, ha
    frames < TILT_MIN_FRAMES.
    """
    config = config or TacticsConfig()
    mid = COURT_LENGTH_M / 2.0
    acc = {"home": [0, 0], "away": [0, 0]}  # birtokos kocka, ellenfél-térfél
    for f in match.frames:
        team = possession_team(f, config)
        if team is None or f.ball is None:
            continue
        rec = acc[team.value]
        rec[0] += 1
        goal_x = config.attacks_toward_x(team)
        in_opp = (f.ball.x > mid) if goal_x > mid else (f.ball.x < mid)
        if in_opp:
            rec[1] += 1

    out: dict = {}
    for s in ("home", "away"):
        n, opp = acc[s]
        out[s] = {
            "frames": n,
            "opp_half_frames": opp,
            "tilt_pct": (round(100.0 * opp / n, 1)
                         if n >= TILT_MIN_FRAMES else None),
        }
    return out


# Területi-fölény-esés: félidőnként ennyi birtokos kocka kell az
# ítélethez, és ekkora tilt-esés (százalékpont) számít érdeminek.
TILT_FADE_MIN_FRAMES = 100
TILT_FADE_DROP_PP = 12.0


def tilt_fade(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """Területi-fölény-esés: a field tilt az 1. vs a 2. félidőben.

    A fáradás-kép terület-tagja: akinek a 2. félidőre érdemben esik a
    területi fölénye, az fáradtan már nem tudja az ellenfél térfelén
    tartani a játékot — a birtoklása hátracsúszik, a hajrában feljön
    ellene az ellenfél. Ellene a terv a türelem: az 1. félidei nyomását
    ki kell állni, mert a hajrára magától átfordul a pálya. Akinek nő,
    az a meccs végére szorít be — ellene a hajrá-labdakihozatalt kell
    külön megtervezni.

    Visszatérés csapatonként: {"fh_frames", "fh_opp", "sh_frames",
    "sh_opp", "drop_pp"} — drop_pp a tilt esése százalékpontban
    (pozitív = a 2. félidőre hátraszorul), None, ha nincs félidő-jel
    vagy kevés (félidőnként TILT_FADE_MIN_FRAMES alatti) a birtokos
    kocka.
    """
    from .halftime import detect_halftime

    config = config or TacticsConfig()
    empty = {"fh_frames": 0, "fh_opp": 0, "sh_frames": 0, "sh_opp": 0,
             "drop_pp": None}
    out = {"home": dict(empty), "away": dict(empty)}
    ht = detect_halftime(match)
    if ht is None:
        return out
    mid = COURT_LENGTH_M / 2.0
    for f in match.frames:
        team = possession_team(f, config)
        if team is None or f.ball is None:
            continue
        rec = out[team.value]
        half = "fh" if f.t <= ht else "sh"
        rec[half + "_frames"] += 1
        goal_x = config.attacks_toward_x(team)
        in_opp = (f.ball.x > mid) if goal_x > mid else (f.ball.x < mid)
        if in_opp:
            rec[half + "_opp"] += 1
    for rec in out.values():
        if rec["fh_frames"] >= TILT_FADE_MIN_FRAMES \
                and rec["sh_frames"] >= TILT_FADE_MIN_FRAMES:
            fh_pct = 100.0 * rec["fh_opp"] / rec["fh_frames"]
            sh_pct = 100.0 * rec["sh_opp"] / rec["sh_frames"]
            rec["drop_pp"] = round(fh_pct - sh_pct, 1)
    return out


# Passz-tempó: legalább ennyi mért birtoklás-idő kell az ítélethez; a
# percenkénti passzszám e fölött pörgetett, ez alatt lassú labdajáratás.
PT_MIN_POSS_S = 120.0
PT_FAST_PER_MIN = 22.0
PT_SLOW_PER_MIN = 12.0


def pass_tempo(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """Passz-tempó (labdajáratás sebessége): hány passz jut a SAJÁT
    birtoklás egy percére.

    Nem a meccs-tempót (támadás/perc) és nem a támadás-hosszt méri, hanem
    hogy a csapat a labdát MOZGATJA-e: a pörgetett labdajáratás (magas
    passz/perc) széthúzza és megmozgatja a falat, a lassú, álló járatás
    kiszámíthatóvá teszi a támadást — a védelem békében felállhat.

    Visszatérés csapatonként:
      {"passes", "poss_s", "per_min", "label"} — a felismert passzok
    száma, a mért birtoklás-idő (mp), a percenkénti passzszám és a címke
    ("pörgetett" / "lassú" / "közepes"); per_min/label None, ha a mért
    birtoklás-idő kevesebb, mint PT_MIN_POSS_S.
    """
    from .event_detection import EventType, detect_events

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    poss_frames = {"home": 0, "away": 0}
    for f in match.frames:
        team = possession_team(f, config)
        if team is not None:
            poss_frames[team.value] += 1
    passes = {"home": 0, "away": 0}
    for e in detect_events(match, config):
        if e.type == EventType.PASS:
            passes[e.team.value] += 1

    out: dict = {}
    for s in ("home", "away"):
        poss_s = poss_frames[s] / fps
        rec = {"passes": passes[s], "poss_s": round(poss_s, 1),
               "per_min": None, "label": None}
        if poss_s >= PT_MIN_POSS_S:
            per_min = 60.0 * passes[s] / poss_s
            rec["per_min"] = round(per_min, 1)
            rec["label"] = ("pörgetett" if per_min >= PT_FAST_PER_MIN
                            else "lassú" if per_min <= PT_SLOW_PER_MIN
                            else "közepes")
        out[s] = rec
    return out


# Támadó-mozgás: szervezett támadásban ennyi mért játékos-másodperctől
# ítélünk; ez alatti átlagsebesség álló, e feletti mozgásos támadás;
# az irreálisan nagy elmozdulás track-ugrás, kihagyjuk.
ATTACK_MOTION_MIN_S = 120.0
ATTACK_MOTION_STATIC_MPS = 0.9
ATTACK_MOTION_FLUID_MPS = 1.6
_MOTION_MAX_MPS = 9.0


def attack_motion(match: Match,
                  config: Optional[TacticsConfig] = None) -> dict:
    """Támadó-mozgás: álló vagy mozgásos a szervezett támadás.

    Az "álló kézilabda" a védő álma: ha a támadók labda nélkül nem
    mozognak, a fal nem kényszerül döntésekre — a kilépés, a
    letámadás kockázat nélkül vállalható ellene. A mozgásos (keresztek,
    elfutások, beúszások) támadás ellen viszont a fegyelmezett
    átadás-átvétel a kulcs, nem az emberkövetés. Szervezett támadásban
    mérjük a támadó mezőnyjátékosok átlagsebességét (kapus és
    becsült pozíciók nélkül, track-ugrás szűréssel).

    Visszatérés csapatonként: {"dist_m", "time_s", "avg_mps",
    "style"} — avg_mps/style None, ha kevés (ATTACK_MOTION_MIN_S
    alatti játékos-másodperc) a minta; a style "álló" / "mozgásos" /
    None (köztes).
    """
    from ..models.tracking import PositionSource

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    sums = {"home": {"dist": 0.0, "time": 0.0},
            "away": {"dist": 0.0, "time": 0.0}}
    prev = None
    for f in match.frames:
        ph = classify_phase(f, config)
        side = ("home" if ph == Phase.HOME_ATTACK
                else "away" if ph == Phase.AWAY_ATTACK else None)
        if prev is not None and side is not None:
            dt = (f.t - prev.t) / fps
            if 0.0 < dt <= 0.5:
                team = Team.HOME if side == "home" else Team.AWAY
                prev_pos = {
                    p.track_id: (p.x, p.y) for p in prev.players
                    if p.team == team
                    and p.source == PositionSource.MEASURED
                    and p.role != "kapus"}
                for p in f.players:
                    if (p.team != team
                            or p.source != PositionSource.MEASURED
                            or p.role == "kapus"):
                        continue
                    pp = prev_pos.get(p.track_id)
                    if pp is None:
                        continue
                    d = math.hypot(p.x - pp[0], p.y - pp[1])
                    if d / dt > _MOTION_MAX_MPS:
                        continue
                    sums[side]["dist"] += d
                    sums[side]["time"] += dt
        prev = f
    out = {}
    for side in ("home", "away"):
        rec = sums[side]
        r = {"dist_m": round(rec["dist"], 1),
             "time_s": round(rec["time"], 1),
             "avg_mps": None, "style": None}
        if rec["time"] >= ATTACK_MOTION_MIN_S:
            avg = rec["dist"] / rec["time"]
            r["avg_mps"] = round(avg, 2)
            if avg <= ATTACK_MOTION_STATIC_MPS:
                r["style"] = "álló"
            elif avg >= ATTACK_MOTION_FLUID_MPS:
                r["style"] = "mozgásos"
        out[side] = r
    return out


# Védekezés-váltás: ennyi mért védekezett támadástól ítélünk, e feletti
# váltás-aránynál váltogatós a csapat, és ennyi százalék feletti fő
# forma-arány az "egy rendszer" jele. Egy támadás formája csak akkor
# számít, ha legalább ennyi kockán olvasható a fal.
FSW_MIN_ATTACKS = 6
FSW_SWITCH_PCT = 30.0
FSW_ONE_SYSTEM_PCT = 80.0
FSW_MIN_FRAMES = 10


# Fal-váltás a szünetre: a fő védekezési forma a két félidőben.
DFS_MIN_ATTACKS_HALF = 5   # félidőnként ennyi címkézett védekezés kell
DFS_MAIN_PCT = 60.0        # a fő forma részaránya ehhez a kimondáshoz


def defense_form_shift(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Fal-váltás a szünetre: MÁS FALAT hoznak-e a második félidőre.

    A védekezés-váltás (formation_switching) a támadásról támadásra
    mért ingadozást nézi — ez a szünetet: félidőnként megkeressük a
    csapat FŐ védekezési formáját (a védekezett támadások uralkodó
    címkéjét), és összevetjük a kettőt. Aki a szünet után falat vált
    (pl. 6-0 → 5-1), annak az első félidei képe a második félidőben
    már nem igaz — a támadó-tervet is váltani kell ellene.

    Edzőileg: a falat váltó csapat ellen két kész figurasorral kell
    érkezni, és a szünet utáni első támadásnál hangosan bemondani a
    felismerést; a stabil falú ellen egy jól begyakorolt sor végig
    kitart. A saját oldalon: ha az ellenfél a szünetben átállt és mi
    nem reagáltunk, a felismerés-rutin az edzés-téma.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal): {"fh_attacks",
    "sh_attacks", "fh_labels", "sh_labels", "fh_main", "sh_main",
    "verdict"} — fh_main/sh_main None, ha kevés a címkézett védekezés
    vagy nincs DFS_MAIN_PCT-s uralkodó forma; a verdict "a szünet
    után falat váltanak (X → Y)" / "a szünet után is ugyanaz a fal" /
    None.
    """
    from .halftime import detect_halftime
    from .setplays import segment_attacks

    config = config or TacticsConfig()
    out = {side: {"fh_attacks": 0, "sh_attacks": 0,
                  "fh_labels": {}, "sh_labels": {},
                  "fh_main": None, "sh_main": None, "verdict": None}
           for side in ("home", "away")}
    ht = detect_halftime(match)
    if ht is None:
        return out
    for seq in segment_attacks(match, config):
        defending = Team.AWAY if seq.team == Team.HOME else Team.HOME
        tally: dict[str, int] = {}
        for fr in seq.frames:
            form = detect_formation(fr, defending, config)
            if not form.label or form.label == "?" or form.defenders < 4:
                continue
            tally[form.label] = tally.get(form.label, 0) + 1
        if not tally or sum(tally.values()) < FSW_MIN_FRAMES:
            continue
        label = max(tally.items(), key=lambda kv: kv[1])[0]
        rec = out[defending.value]
        half = "fh" if seq.start_t <= ht else "sh"
        rec[half + "_attacks"] += 1
        rec[half + "_labels"][label] = \
            rec[half + "_labels"].get(label, 0) + 1
    for rec in out.values():
        for half in ("fh", "sh"):
            n = rec[half + "_attacks"]
            labels = rec[half + "_labels"]
            if n < DFS_MIN_ATTACKS_HALF or not labels:
                continue
            main, cnt = max(labels.items(), key=lambda kv: kv[1])
            if 100.0 * cnt / n >= DFS_MAIN_PCT:
                rec[half + "_main"] = main
        if rec["fh_main"] and rec["sh_main"]:
            if rec["fh_main"] != rec["sh_main"]:
                rec["verdict"] = (f"a szünet után falat váltanak "
                                  f"({rec['fh_main']} → "
                                  f"{rec['sh_main']})")
            else:
                rec["verdict"] = "a szünet után is ugyanaz a fal"
    return out


def formation_switching(match: Match,
                        config: Optional[TacticsConfig] = None) -> dict:
    """Védekezés-váltás: egy rendszert játszanak, vagy váltogatnak.

    A leggyakoribb forma (most_common_formations) azt mondja meg, MIT
    játszanak, a forma szerinti hatékonyság (efficiency_vs_formation)
    azt, melyik fal fogja meg őket — ez a harmadik kérdés: MENNYIRE
    állandó a rendszerük. Támadásonként (a védekező oldal szemszögéből)
    megnézzük a fal uralkodó címkéjét, és számoljuk, hányszor tér el az
    előző védekezett támadásétól.

    Edzőileg: aki egy rendszert játszik, arra egy figurasort kell
    felépíteni és végig azt húzni; aki váltogat, ott a felismerés a
    feladat — a kihozatalnál hangosan bemondani a formát, és két kész
    változattal érkezni.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal):
      {"attacks", "labels": {forma: támadás}, "main", "main_pct",
       "switches", "switch_pct", "verdict"} — az arányok és a verdict
    None FSW_MIN_ATTACKS alatt; a verdict "váltogatós" / "egy
    rendszer" / None.
    """
    from .setplays import segment_attacks

    config = config or TacticsConfig()
    seqs: dict[str, list[str]] = {"home": [], "away": []}
    for seq in segment_attacks(match, config):
        defending = Team.AWAY if seq.team == Team.HOME else Team.HOME
        tally: dict[str, int] = {}
        for fr in seq.frames:
            form = detect_formation(fr, defending, config)
            if not form.label or form.label == "?" or form.defenders < 4:
                continue  # kevés látott védő — a címke nem megbízható
            tally[form.label] = tally.get(form.label, 0) + 1
        if not tally or sum(tally.values()) < FSW_MIN_FRAMES:
            continue
        seqs[defending.value].append(
            max(tally.items(), key=lambda kv: kv[1])[0])

    out: dict = {}
    for side in ("home", "away"):
        labels_seq = seqs[side]
        n = len(labels_seq)
        labels: dict[str, int] = {}
        for lab in labels_seq:
            labels[lab] = labels.get(lab, 0) + 1
        labels = dict(sorted(labels.items(), key=lambda kv: -kv[1]))
        switches = sum(1 for a, b in zip(labels_seq, labels_seq[1:])
                       if a != b)
        rec = {"attacks": n, "labels": labels,
               "main": (next(iter(labels)) if labels else None),
               "main_pct": None, "switches": switches,
               "switch_pct": None, "verdict": None}
        if n >= FSW_MIN_ATTACKS:
            main_pct = 100.0 * labels[rec["main"]] / n
            sw_pct = 100.0 * switches / (n - 1)
            rec["main_pct"] = round(main_pct, 1)
            rec["switch_pct"] = round(sw_pct, 1)
            if sw_pct >= FSW_SWITCH_PCT:
                rec["verdict"] = "váltogatós"
            elif main_pct >= FSW_ONE_SYSTEM_PCT:
                rec["verdict"] = "egy rendszer"
        out[side] = rec
    return out


# Álló támadók: ennyi játékos-másodperc kell egy ember megítéléséhez, és
# ekkora (százalékos) elmaradás a csapatátlagtól számít álló embernek.
STATIC_ATT_MIN_S = 60.0
STATIC_ATT_GAP_PCT = 30.0


def static_attackers(match: Match,
                     config: Optional[TacticsConfig] = None) -> dict:
    """Álló támadók: KI mozog labda nélkül a legkevesebbet.

    A támadó-mozgás (attack_motion) csapat-szinten mondja meg, álló
    vagy mozgásos a támadásuk — ez játékosonként bontja: szervezett
    támadásban mérjük az egyes támadók átlagsebességét, és a
    csapatátlaghoz viszonyítjuk.

    Edzőileg: aki érdemben a csapatátlag alatt mozog, azt a védője
    nyugodtan otthagyhatja — befelé segíthet, kettőzhet vagy a
    beállóra léphet, mert az álló ember nem bünteti meg. A saját
    edzésnek pedig kész témája van: labda nélküli munka.

    Visszatérés csapatonként: {"team_avg_mps", "players":
    [{"player_id", "jersey", "seconds", "avg_mps"}], "static"} — a
    lista átlagsebesség szerint NÖVEKVŐ (elöl a legkevesebbet
    mozgóval); a "static" az első játékos, ha van legalább
    STATIC_ATT_MIN_S mért másodperce, és az átlaga legalább
    STATIC_ATT_GAP_PCT százalékkal a csapatátlag alatt van.
    """
    from ..models.tracking import PositionSource

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    jersey: dict = {}
    acc: dict = {"home": {}, "away": {}}
    prev = None
    for f in match.frames:
        ph = classify_phase(f, config)
        side = ("home" if ph == Phase.HOME_ATTACK
                else "away" if ph == Phase.AWAY_ATTACK else None)
        if prev is not None and side is not None:
            dt = (f.t - prev.t) / fps
            if 0.0 < dt <= 0.5:
                team = Team.HOME if side == "home" else Team.AWAY
                prev_pos = {
                    p.track_id: (p.x, p.y) for p in prev.players
                    if p.team == team
                    and p.source == PositionSource.MEASURED
                    and p.role != "kapus"}
                for p in f.players:
                    if (p.team != team
                            or p.source != PositionSource.MEASURED
                            or p.role == "kapus"):
                        continue
                    pp = prev_pos.get(p.track_id)
                    if pp is None:
                        continue
                    d = math.hypot(p.x - pp[0], p.y - pp[1])
                    if d / dt > _MOTION_MAX_MPS:
                        continue  # track-ugrás
                    if p.jersey_number is not None:
                        jersey.setdefault(p.track_id, p.jersey_number)
                    rec = acc[side].setdefault(p.track_id, [0.0, 0.0])
                    rec[0] += d
                    rec[1] += dt
        prev = f

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "seconds": round(t, 1), "avg_mps": round(d / t, 2)}
                for pid, (d, t) in acc[side].items() if t > 0]
        rows.sort(key=lambda r: r["avg_mps"])
        total_d = sum(d for d, _ in acc[side].values())
        total_t = sum(t for _, t in acc[side].values())
        team_avg = round(total_d / total_t, 2) if total_t > 0 else None
        static = None
        if team_avg:
            cand = [r for r in rows if r["seconds"] >= STATIC_ATT_MIN_S]
            if cand:
                slowest = cand[0]
                gap = 100.0 * (team_avg - slowest["avg_mps"]) / team_avg
                if gap >= STATIC_ATT_GAP_PCT:
                    static = slowest
        out[side] = {"team_avg_mps": team_avg, "players": rows,
                     "static": static}
    return out


# Álló-poszt: posztonként ennyi mért másodperc kell, és a
# csapatátlagnál ekkora (százalékos) lassabb labda nélküli mozgás,
# hogy a posztot állónak mondjuk ki.
SAR_MIN_S = 20.0
SAR_GAP_PCT = 20.0


def static_attacker_roles(match: Match,
                          config: Optional[TacticsConfig] = None
                          ) -> dict:
    """Álló-poszt: MELYIK POSZTJUK áll labda nélkül.

    Az álló támadók rétege (static_attackers) az embert nevezi meg —
    ez a posztot: a szervezett támadásban mért mozgás-másodperceket
    és métereket a játékos posztjához összegzi, és megnézi, melyik
    posztjuk mozog érdemben a csapatátlag alatt.

    Edzőileg ez a besegítés-forrás: az álló posztot a védője
    nyugodtan otthagyhatja — befelé segíthet, kettőzhet vagy a
    beállóra léphet, mert az álló ember nem bünteti meg. Saját
    csapatra: a poszt labda nélküli munkája kész edzés-téma.

    Visszatérés csapatonként: {"roles": {poszt: {"seconds",
    "meters", "avg_mps"}}, "team_avg_mps", "main_role", "verdict"} —
    az ítélet None, ha egyik poszt sem éri el a SAR_MIN_S-t a
    SAR_GAP_PCT-s lemaradással.
    """
    from .roles import estimate_positions

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    sa = static_attackers(match, config)

    out: dict = {}
    for side in ("home", "away"):
        agg: dict = {}
        for row in sa[side]["players"]:
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec = agg.setdefault(poszt, {"seconds": 0.0,
                                         "meters": 0.0})
            rec["seconds"] += row["seconds"]
            rec["meters"] += row["seconds"] * row["avg_mps"]
        total_s = sum(r["seconds"] for r in agg.values())
        total_m = sum(r["meters"] for r in agg.values())
        team_avg = (total_m / total_s) if total_s > 0 else None
        for r in agg.values():
            r["seconds"] = round(r["seconds"], 1)
            r["avg_mps"] = (round(r["meters"] / r["seconds"], 2)
                            if r["seconds"] > 0 else None)
            r["meters"] = round(r["meters"], 1)
        rec_out = {"roles": dict(sorted(
                       agg.items(),
                       key=lambda kv: kv[1]["avg_mps"] or 0.0)),
                   "team_avg_mps": (round(team_avg, 2)
                                    if team_avg else None),
                   "main_role": None, "verdict": None}
        if team_avg:
            for poszt, r in rec_out["roles"].items():
                if r["seconds"] < SAR_MIN_S or r["avg_mps"] is None:
                    continue
                if r["avg_mps"] <= team_avg * (1 - SAR_GAP_PCT / 100.0):
                    rec_out["main_role"] = poszt
                    rec_out["verdict"] = (
                        f"a(z) {poszt} posztjuk áll labda nélkül "
                        f"({r['avg_mps']:.1f} m/s a "
                        f"{team_avg:.1f} m/s csapatátlag mellett) —"
                        " a védője otthagyhatja: befelé segíthet, "
                        "kettőzhet vagy a beállóra léphet")
                    break
        out[side] = rec_out
    return out
