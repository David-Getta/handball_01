"""
[Élő edzői javaslatok] — az AKTUÁLIS frame-re valós idejű taktikai tanácsok.

A vízió "élő meccskövetés valós idejű edzői javaslatokkal" része. A meglévő
taktikai rétegre (tactics.py: birtoklás, fázis, védekezési forma) épül, és a
BIRTOKLÓ (támadó) csapat szemszögéből ad rangsorolt javaslatokat:

- védekezési forma kihasználása (6-0 / 5-1 / 3-2-1 / 4-2 …),
- ember-előny/hátrány (kiállítás miatti létszámkülönbség),
- szabad (üres) csapattárs a veszélyes zónában,
- gyors indítás / lefutás lehetősége (tempó a labda elmozdulásából).

Tiszta adatfeldolgozás (videó nélkül tesztelhető). A kliens ugyanezt a logikát
tükrözi (coaching.dart), hogy a lejátszás közben backend nélkül is folyjon a
javaslat-adás; a backend /coaching végpont az "igazság forrása" és a tesztelt hely.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, asdict
from typing import Optional

from ..models.tracking import Match, Frame, Team
from .calibration import COURT_LENGTH_M, COURT_WIDTH_M
from .tactics import (
    TacticsConfig, Phase, possession_team, classify_phase, detect_formation,
)

# A kapushoz ilyen közel lévő játékost NEM mezőnyjátékosnak veszünk (létszámhoz).
_GK_MAX = 2.0
# Ekkora távolságon túl a legközelebbi védőtől egy támadót "szabadnak" tekintünk.
_OPEN_RADIUS_M = 3.5
# A labda ekkora (támadó irányú) elmozdulása/frame felett "gyors indítás".
_FASTBREAK_MS = 6.0


@dataclass
class Suggestion:
    """Egy edzői javaslat: prioritás (1..5, nagyobb = sürgősebb), kategória, szöveg."""
    priority: int
    category: str
    text: str


def _field_players(frame: Frame, team: Team, config: TacticsConfig) -> list:
    """A csapat MEZŐNYjátékosai (a kapust a kapuközelség alapján kihagyjuk)."""
    goal_x = config.own_goal_x(team)
    return [p for p in frame.players
            if p.team == team and abs(p.x - goal_x) > _GK_MAX]


def _side_label(y: float) -> str:
    """A pálya szélessége (0..20) mentén bal/közép/jobb megnevezés."""
    if y < COURT_WIDTH_M * 0.33:
        return "bal oldalon"
    if y > COURT_WIDTH_M * 0.66:
        return "jobb oldalon"
    return "középen"


def _formation_suggestion(label: str) -> Suggestion:
    """A védekezési formához illő támadó tanács."""
    table = {
        "6-0": "Mély 6-0 fal — keresd a beúszót és a 9 m-es lövést; csald ki a védőt.",
        "5-1": "5-1 — az előretolt védő mögötti tér a kulcs; gyors lefordulás, kétszemélyes fal.",
        "4-2": "4-2 — a két előretolt közti középső rés a cél; beálló-játék.",
        "3-2-1": "3-2-1 — terheld a beállót és a szélső réseket; mozgasd a magas védőt.",
        "3-3": "3-3 — széles járatás, a hátsó és első lépcső közti tér kihasználható.",
    }
    text = table.get(label)
    if text is None:
        return Suggestion(2, "forma", f"Védőforma: {label} — keresd a legüresebb sávot.")
    return Suggestion(3, "forma", text)


def _ball_speed_toward_attack(frame: Frame, prev: Optional[Frame],
                              attacking: Team, config: TacticsConfig, fps: float) -> float:
    """A labda TÁMADÓ irányú sebessége (m/s) az előző frame-hez képest.

    Pozitív, ha a labda az ellenfél kapuja felé halad — a gyors indítás jele.
    """
    if prev is None or frame.ball is None or prev.ball is None:
        return 0.0
    target_x = config.attacks_toward_x(attacking)
    sign = 1.0 if target_x > COURT_LENGTH_M / 2.0 else -1.0
    dx = (frame.ball.x - prev.ball.x) * sign
    return dx * fps


def suggest_for_frame(frame: Frame, config: Optional[TacticsConfig] = None,
                      prev_frame: Optional[Frame] = None, fps: float = 25.0) -> list[Suggestion]:
    """Az adott frame edzői javaslatai a BIRTOKLÓ (támadó) csapat szemszögéből.

    Rangsorolt lista (legsürgősebb elöl). Ha nincs egyértelmű birtokos, átmeneti
    (visszazárás/harc a labdáért) tanácsot adunk.
    """
    config = config or TacticsConfig()
    out: list[Suggestion] = []

    poss = possession_team(frame, config)
    if frame.ball is None:
        return [Suggestion(1, "altalanos", "Nincs labda a képen — kövesd a felépítést.")]
    if poss is None:
        return [Suggestion(4, "tempo", "Szabad labda — harcolj érte, vagy zárj vissza gyorsan!")]

    attacking = poss
    defending = Team.AWAY if attacking == Team.HOME else Team.HOME

    # 1) Ember-előny/hátrány (kiállítás miatti létszámkülönbség).
    att_n = len(_field_players(frame, attacking, config))
    def_n = len(_field_players(frame, defending, config))
    diff = att_n - def_n
    if diff >= 1:
        out.append(Suggestion(5, "emberelony",
                              f"Emberelőny (+{diff}) — gyors oldalváltás, használd ki!"))
    elif diff <= -1:
        out.append(Suggestion(4, "emberhatrany",
                              f"Emberhátrány ({diff}) — húzd az időt, biztos passzok."))

    # 2) Gyors indítás / lefutás (a labda támadó irányú sebességéből).
    speed = _ball_speed_toward_attack(frame, prev_frame, attacking, config, fps)
    if speed >= _FASTBREAK_MS:
        out.append(Suggestion(5, "tempo", "Gyors indítás — lefutás lehetséges, indíts előre!"))

    # 3) Szabad (üres) csapattárs a támadó térfélen — a legüresebbet ajánljuk.
    carrier = min(frame.players,
                  key=lambda p: math.hypot(p.x - frame.ball.x, p.y - frame.ball.y))
    target_x = config.attacks_toward_x(attacking)
    best_open = None  # (távolság a legközelebbi védőtől, játékos)
    for p in frame.players:
        if p.team != attacking or p is carrier:
            continue
        # csak a támadó térfélen (az ellenfél kapujához közelebbi félen) lévők
        on_attacking_half = (p.x > COURT_LENGTH_M / 2.0) if target_x > COURT_LENGTH_M / 2.0 \
            else (p.x < COURT_LENGTH_M / 2.0)
        if not on_attacking_half:
            continue
        nearest_def = min(
            (math.hypot(p.x - d.x, p.y - d.y) for d in frame.players if d.team == defending),
            default=math.inf,
        )
        if nearest_def >= _OPEN_RADIUS_M and (best_open is None or nearest_def > best_open[0]):
            best_open = (nearest_def, p)
    if best_open is not None:
        out.append(Suggestion(4, "szabad",
                              f"Szabad ember {_side_label(best_open[1].y)} — passzold neki!"))

    # 4) A védekezési formához illő tanács (mindig ad egy alap-irányt).
    formation = detect_formation(frame, defending, config)
    out.append(_formation_suggestion(formation.label))

    out.sort(key=lambda s: s.priority, reverse=True)
    return out


def coaching_timeline(match: Match, config: Optional[TacticsConfig] = None) -> list[list[dict]]:
    """A teljes meccs javaslatai frame-enként (a kliens ebbe indexel lejátszáskor)."""
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    result: list[list[dict]] = []
    prev: Optional[Frame] = None
    for f in match.frames:
        sugg = suggest_for_frame(f, config, prev_frame=prev, fps=fps)
        result.append([asdict(s) for s in sugg])
        prev = f
    return result
