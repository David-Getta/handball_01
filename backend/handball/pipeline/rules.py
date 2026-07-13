"""Szabály-értő réteg — a bírói döntések LENYOMATÁNAK felismerése.

A bíró karjelzéseit a rendszer (még) nem látja: ahhoz póz-becslő modell
kellene, a bírót ma csak kiszűrjük a képből (sárga mez). Amit viszont a
pálya-koordinátákból megbízhatóan fel lehet ismerni, az a döntések
KÖVETKEZMÉNYE — és az edzőt valójában ez érdekli:

- KIÁLLÍTÁS (emberhátrány/emberelőny): egy csapat tartósan 5 mezőny-
  játékossal játszik, míg a másik 6-tal → 2 perces kiállítás lenyomata.
- HÉTMÉTERES: a labda mozdulatlanul áll a 7 m-es pont környékén, mielőtt
  elvégzik a dobást — a büntető jellegzetes, összetéveszthetetlen képe.
- PASSZÍV JÁTÉK KOCKÁZAT: hosszan húzódó felállt támadás lövés nélkül —
  ahol a bíró tipikusan passzívot jelez.

Minden felismerés magyarázható (mért számokon áll), és a meglévő
Suspension/RosterTimeline adatmodellt tölti fel automatikusan — eddig ez
kézi kitöltésre várt. Tiszta adatfeldolgozás, videó nélkül tesztelhető.
"""

from __future__ import annotations

import math
from typing import Optional

from ..models.tracking import Match, PositionSource, Team
from ..models.events import Suspension
from .calibration import COURT_LENGTH_M, COURT_WIDTH_M
from .tactics import TacticsConfig

# Kiállítás-felismerés küszöbei:
PP_WINDOW_S = 10.0        # ekkora ablakonként számoljuk a pályán lévőket
PP_MIN_PRESENCE = 0.2     # egy track az ablak >=20%-ában látszódjon (zaj ki)
PP_MIN_S = 45.0           # legalább ennyi ideig tartó hiány = kiállítás
FIELD_PLAYERS = 6         # teljes létszám mezőnyjátékosból (kapus nélkül)

# Hétméteres-felismerés küszöbei:
SEVEN_M = 7.0             # a büntetőpont távolsága a kaputól
SEVEN_TOL_M = 1.2         # ennyire lehet a labda a ponttól
SEVEN_STATIC_S = 0.8      # legalább ennyi ideig áll a labda
SEVEN_MAX_SPEED = 0.7     # eközben legfeljebb ennyit mozog (m/s)
SEVEN_DEBOUNCE_S = 10.0   # két hétméteres között legalább ennyi idő

# Passzív játék: felállt támadás lövés nélkül ennél hosszabban.
PASSIVE_MIN_S = 35.0


def field_count_timeline(match: Match, window_s: float = PP_WINDOW_S) -> list[dict]:
    """Ablakonként a pályán látott MEZŐNYJÁTÉKOS-trackek száma csapatonként.

    Mért pozíciókból számol (a becslő kitöltése nem torzít), a kapust
    (role="kapus") nem számolja, és a nagyon rövid ideig látszó trackeket
    (az ablak <20%-a) zajként kihagyja. A pásztázó kamera miatt EGY kockán
    nem látszik mindenki — ablakon belül igen.
    """
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = max(1, round(window_s * fps))
    total = len(match.frames)
    out: list[dict] = []
    for w0 in range(0, total, win):
        frames = match.frames[w0:w0 + win]
        seen: dict[int, list] = {}
        for f in frames:
            for p in f.players:
                if p.source != PositionSource.MEASURED or p.role == "kapus":
                    continue
                rec = seen.setdefault(p.track_id, [0, p.team])
                rec[0] += 1
        counts = {Team.HOME: 0, Team.AWAY: 0}
        min_frames = max(1, round(len(frames) * PP_MIN_PRESENCE))
        for (n, team) in seen.values():
            if n >= min_frames:
                counts[team] += 1
        out.append({"start_frame": match.frames[w0].t,
                    "home": counts[Team.HOME], "away": counts[Team.AWAY]})
    return out


def detect_powerplay(match: Match) -> list[dict]:
    """Emberhátrány-szakaszok (kiállítás lenyomata).

    Egy csapat akkor van emberhátrányban, ha az ablakában legfeljebb 5
    mezőnyjátékosa látszik, míg az ellenfélből legalább 6 — és ez
    legalább PP_MIN_S ideig áll fenn.

    Visszatérés: [{"team_down", "start_frame", "end_frame", "duration_s"}].
    """
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    tl = field_count_timeline(match)
    if not tl:
        return []
    win_frames = (tl[1]["start_frame"] - tl[0]["start_frame"]) if len(tl) > 1 \
        else len(match.frames)

    out: list[dict] = []
    for down, other in (("home", "away"), ("away", "home")):
        run_start = None
        for i in range(len(tl) + 1):
            w = tl[i] if i < len(tl) else None
            active = (w is not None and w[down] <= FIELD_PLAYERS - 1
                      and w[other] >= FIELD_PLAYERS)
            if active and run_start is None:
                run_start = i
            elif not active and run_start is not None:
                n_win = i - run_start
                dur_s = n_win * win_frames / fps
                if dur_s >= PP_MIN_S:
                    start_f = tl[run_start]["start_frame"]
                    end_f = start_f + n_win * win_frames - 1
                    out.append({"team_down": down,
                                "start_frame": start_f,
                                "end_frame": min(end_f, match.frames[-1].t),
                                "duration_s": round(dur_s, 1)})
                run_start = None
    out.sort(key=lambda w: w["start_frame"])
    return out


def suspensions_from_powerplay(match: Match) -> list[Suspension]:
    """A felismert emberhátrányok Suspension objektumokként — a meglévő
    RosterTimeline adatmodellhez (eddig kézi kitöltésre várt)."""
    return [Suspension(team=Team.HOME if w["team_down"] == "home" else Team.AWAY,
                       start_t=w["start_frame"],
                       duration_t=w["end_frame"] - w["start_frame"] + 1)
            for w in detect_powerplay(match)]


def detect_seven_meters(match: Match,
                        config: Optional[TacticsConfig] = None) -> list[dict]:
    """Hétméteres (büntetődobás) felismerése.

    Jele: a labda a 7 m-es pont környékén (a kaputól ~7 m-re, középen)
    mozdulatlanul áll legalább SEVEN_STATIC_S ideig — a normál játékban a
    labda ott sosem áll meg. A dobó csapat a kapu támadója.

    Visszatérés: [{"t", "team", "goal_x"}] időrendben.
    """
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    need = max(2, round(SEVEN_STATIC_S * fps))
    debounce = round(SEVEN_DEBOUNCE_S * fps)

    out: list[dict] = []
    run = {0.0: 0, COURT_LENGTH_M: 0}
    last_emit = {0.0: -10 ** 9, COURT_LENGTH_M: -10 ** 9}
    prev = None
    for f in match.frames:
        b = f.ball
        if b is None:
            run = {k: 0 for k in run}
            prev = None
            continue
        speed = (math.hypot(b.x - prev[0], b.y - prev[1]) * fps
                 if prev is not None else 0.0)
        for goal_x in (0.0, COURT_LENGTH_M):
            near_spot = (abs(abs(b.x - goal_x) - SEVEN_M) <= SEVEN_TOL_M
                         and abs(b.y - COURT_WIDTH_M / 2.0) <= 2.0)
            if near_spot and speed <= SEVEN_MAX_SPEED:
                run[goal_x] += 1
                if run[goal_x] == need and f.t - last_emit[goal_x] >= debounce:
                    attacker = (Team.HOME
                                if config.attacks_toward_x(Team.HOME) == goal_x
                                else Team.AWAY)
                    out.append({"t": f.t - need + 1, "team": attacker.value,
                                "goal_x": goal_x})
                    last_emit[goal_x] = f.t
            else:
                run[goal_x] = 0
        prev = (b.x, b.y)
    return out


def passive_play_risks(match: Match,
                       config: Optional[TacticsConfig] = None) -> list[dict]:
    """Passzív játék kockázata: felállt támadás lövés nélkül, hosszan.

    Visszatérés: a szóban forgó támadás-szakaszok (attack_types alakban).
    """
    config = config or TacticsConfig()
    from .attack_types import AttackType, classify_attacks
    from .event_detection import EventType, detect_shots

    shot_ts = [e.t for e in detect_shots(match, config)
               if e.type in (EventType.SHOT, EventType.GOAL)]
    out: list[dict] = []
    for a in classify_attacks(match, config):
        if a["type"] != AttackType.POSITIONAL.value:
            continue
        if a["duration_s"] < PASSIVE_MIN_S:
            continue
        if any(a["start_frame"] <= t <= a["end_frame"] for t in shot_ts):
            continue
        out.append(a)
    return out


def rules_report(match: Match) -> dict:
    """A szabály-értő réteg összegzése egy hívásban (az API-nak)."""
    return {
        "powerplay": detect_powerplay(match),
        "powerplay_efficiency": powerplay_efficiency(match),
        "seven_meters": detect_seven_meters(match),
        "passive_risk": passive_play_risks(match),
    }

def powerplay_efficiency(match: Match,
                         config: Optional[TacticsConfig] = None) -> dict:
    """Emberelőny-hatékonyság: mire váltja a csapat a kiállításokat.

    Csapatonként szétválogatja a kapura tartó lövéseket (gól + védés)
    aszerint, hogy EMBERELŐNYBEN (az ellenfél kiállítása alatt), EGYENLŐ
    létszámnál vagy EMBERHÁTRÁNYBAN születtek — és számolja a hátrányban
    kapott gólokat is.

    Visszatérés csapatonként: {"pp_shots", "pp_goals", "pp_eff_pct",
    "eq_shots", "eq_goals", "eq_eff_pct", "pp_seconds",
    "sh_seconds", "sh_conceded"} — üres szótár, ha nem volt kiállítás.
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    windows = detect_powerplay(match)
    if not windows:
        return {}

    def _down_at(t: int) -> Optional[str]:
        for w in windows:
            if w["start_frame"] <= t <= w["end_frame"]:
                return w["team_down"]
        return None

    out = {team: {"pp_shots": 0, "pp_goals": 0, "pp_eff_pct": 0.0,
                  "eq_shots": 0, "eq_goals": 0, "eq_eff_pct": 0.0,
                  "pp_seconds": 0.0, "sh_seconds": 0.0, "sh_conceded": 0}
           for team in ("home", "away")}
    for w in windows:
        down = w["team_down"]
        up = "away" if down == "home" else "home"
        out[up]["pp_seconds"] += w["duration_s"]
        out[down]["sh_seconds"] += w["duration_s"]

    for e in detect_shots(match, config):
        outcome = (e.detail or {}).get("outcome")
        if outcome not in ("goal", "save"):
            continue  # a mellé menő lövésből nem mérünk hatékonyságot
        team = e.team.value
        down = _down_at(e.t)
        if down is None or down == team:
            # Egyenlő létszám (vagy hátrányban lőtt — az az "eq"-t se rontsa).
            if down is None:
                out[team]["eq_shots"] += 1
                if outcome == "goal":
                    out[team]["eq_goals"] += 1
        else:
            out[team]["pp_shots"] += 1
            if outcome == "goal":
                out[team]["pp_goals"] += 1
        if outcome == "goal" and down is not None and down != team:
            # A hátrányban lévő csapat kapta a gólt.
            out[down]["sh_conceded"] += 1

    for rec in out.values():
        if rec["pp_shots"]:
            rec["pp_eff_pct"] = round(100.0 * rec["pp_goals"] / rec["pp_shots"], 1)
        if rec["eq_shots"]:
            rec["eq_eff_pct"] = round(100.0 * rec["eq_goals"] / rec["eq_shots"], 1)
        rec["pp_seconds"] = round(rec["pp_seconds"], 1)
        rec["sh_seconds"] = round(rec["sh_seconds"], 1)
    return out
