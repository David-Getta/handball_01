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
