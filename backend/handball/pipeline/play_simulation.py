"""
[5. fázis] Figura-szimuláció — az edző figurája egy TANULT ellenfél ellen.

A vízió "edző kipróbálja a kitalált figuráit egy adott csapat ellen" része:
1. DefenseModel.learn(...) — egy ellenfél meccséből megtanuljuk a védekezési
   stílusát (hány védő, milyen mélyen áll a saját kaputól, mennyire követi a labdát).
2. SetPlay — az edző által megtervezett figura: a támadók útvonala lépésenként +
   ki birtokolja a labdát.
3. simulate_setplay(...) — lejátssza a figurát: a támadók a terv szerint mozognak,
   a védők a TANULT modell szerint reagálnak. Kimenet egy Match (Tracking), amit a
   kliens ugyanúgy ki tud rajzolni, mint egy valódi meccset.
4. evaluate_setplay(...) — pontozza a figurát: teremtett-e szabad, közeli
   lövőhelyzetet (a legjobb lövésérték * "szabadság" a védőktől).

Tiszta Python, videó nélkül tesztelhető. A védekezési modell egyszerű, de VALÓDI
adatból tanult paraméterekre épül — később finomabb (tanult) modellre cserélhető.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

from ..models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, Ball, Team, PositionSource,
)
from .calibration import COURT_LENGTH_M, COURT_WIDTH_M
from .tactics import TacticsConfig, classify_phase, Phase
from .decisions import shot_value


# ---- Tanult védekezési modell ---------------------------------------------

@dataclass
class DefenseModel:
    """Egy csapat védekezési stílusa, meccsadatból tanult paraméterekkel.

    - num_defenders: hány mezőnyvédő áll a vonalban (kapus nélkül).
    - line_depth_m:  a védővonal átlagos mélysége a SAJÁT kaputól (méter).
    - lateral_gain:  mennyire követi a védelem a labda y-helyzetét (0..1).
    """
    num_defenders: int = 6
    line_depth_m: float = 6.0
    lateral_gain: float = 0.5

    @classmethod
    def learn(cls, match: Match, defending_team: Team,
              config: TacticsConfig | None = None) -> "DefenseModel":
        """Megtanulja a védekezési stílust azokból a frame-ekből, ahol a csapat véd.

        A csapat akkor véd, amikor az ellenfél támad. Ezeken a frame-eken a
        mezőnyvédők (kapus nélkül) átlagos mélységét és átlagos számát becsüljük.
        """
        config = config or TacticsConfig()
        goal_x = config.own_goal_x(defending_team)
        depths: list[float] = []
        counts: list[int] = []
        for f in match.frames:
            ph = classify_phase(f, config)
            defends = ((defending_team == Team.AWAY and ph == Phase.HOME_ATTACK) or
                       (defending_team == Team.HOME and ph == Phase.AWAY_ATTACK))
            if not defends:
                continue
            outfield = [p for p in f.players
                        if p.team == defending_team and abs(p.x - goal_x) > 2.0]
            if outfield:
                counts.append(len(outfield))
                depths.extend(abs(p.x - goal_x) for p in outfield)
        return cls(
            num_defenders=round(statistics.fmean(counts)) if counts else 6,
            line_depth_m=statistics.fmean(depths) if depths else 6.0,
        )

    def respond(self, ball: Ball, goal_x: float) -> list[tuple[float, float]]:
        """A védők pozíciói a labdára reagálva (a tanult mélységben, y-ban a labda felé).

        A védővonal a kaputól `line_depth_m`-re húzódik (a pálya belseje felé), a
        védők y-ban egyenletesen elosztva, a labda y-helyzete felé eltolva.
        """
        sign = -1.0 if goal_x == COURT_LENGTH_M else 1.0
        line_x = goal_x + sign * self.line_depth_m

        n = max(1, self.num_defenders)
        # Egyenletes y-eloszlás a [3, 17] sávban.
        if n == 1:
            base_ys = [COURT_WIDTH_M / 2.0]
        else:
            lo, hi = 3.0, COURT_WIDTH_M - 3.0
            base_ys = [lo + (hi - lo) * i / (n - 1) for i in range(n)]

        shift = self.lateral_gain * (ball.y - COURT_WIDTH_M / 2.0)
        return [(line_x, max(1.0, min(COURT_WIDTH_M - 1.0, by + shift))) for by in base_ys]


# ---- A figura (set play) és a szimuláció ----------------------------------

@dataclass
class SetPlay:
    """Az edző által tervezett figura.

    - attackers:    [támadó][lépés] = (x, y) — minden támadó útvonala lépésenként.
                    Minden támadó listája azonos hosszú (a lépések száma).
    - ball_carrier: lépésenként melyik támadó (index) birtokolja a labdát.
    """
    attackers: list[list[tuple[float, float]]]
    ball_carrier: list[int]

    @property
    def steps(self) -> int:
        return len(self.ball_carrier)


def simulate_setplay(setplay: SetPlay, defense: DefenseModel,
                     config: TacticsConfig | None = None,
                     fps: float = 25.0) -> Match:
    """Lejátssza a figurát a tanult védelem ellen, és Match-et (Tracking) ad.

    A HAZAI a támadó (a +x kapu felé), a VENDÉG véd (saját kapuja x=40). A
    kimenet ugyanolyan Tracking, mint egy valódi meccs — a kliens kirajzolhatja.
    """
    config = config or TacticsConfig()
    away_goal_x = config.own_goal_x(Team.AWAY)
    meta = MatchMeta(match_id="setplay-sim", home_team="Terv (támadó)",
                     away_team="Tanult védelem", fps=fps, frame_width=1920, frame_height=1080)
    frames: list[Frame] = []

    for step in range(setplay.steps):
        players: list[PlayerPosition] = []
        for ai, path in enumerate(setplay.attackers):
            x, y = path[step]
            players.append(PlayerPosition(track_id=ai + 1, team=Team.HOME, x=x, y=y,
                                          source=PositionSource.MEASURED, confidence=1.0,
                                          jersey_number=ai + 1))
        carrier = setplay.ball_carrier[step]
        bx, by = setplay.attackers[carrier][step]
        ball = Ball(x=bx, y=by, confidence=1.0)
        for di, (dx, dy) in enumerate(defense.respond(ball, away_goal_x)):
            players.append(PlayerPosition(track_id=100 + di, team=Team.AWAY, x=dx, y=dy,
                                          source=PositionSource.MEASURED, confidence=1.0))
        frames.append(Frame(t=step, players=players, ball=ball))

    return Match(meta=meta, frames=frames)


def evaluate_setplay(match: Match, config: TacticsConfig | None = None) -> dict:
    """Pontozza a szimulált figurát: a teremtett legjobb lövőhelyzet.

    Minden lépésben minden támadóra: lövésérték * "szabadság" (a legközelebbi védő
    távolsága alapján — 4 m-en belül fedezett). A legjobb érték a figura pontszáma.
    """
    config = config or TacticsConfig()
    goal_x = config.attacks_toward_x(Team.HOME)
    best = {"best_shot_value": 0.0, "step": -1, "attacker_id": None}

    for f in match.frames:
        attackers = [p for p in f.players if p.team == Team.HOME]
        defenders = [p for p in f.players if p.team == Team.AWAY]
        for a in attackers:
            sv = shot_value(a.x, a.y, goal_x)
            if defenders:
                nd = min(math.hypot(a.x - d.x, a.y - d.y) for d in defenders)
            else:
                nd = 99.0
            openness = max(0.0, min(1.0, nd / 4.0))  # 4 m-en belül fedezett
            score = sv * openness
            if score > best["best_shot_value"]:
                best = {"best_shot_value": score, "step": f.t, "attacker_id": a.track_id}
    return best
