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
