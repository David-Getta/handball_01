"""[D2] Kapus-azonosítás pozíció-prior alapján.

A kapus mezszín-alapú felismerése törékeny (a kapus-szín meccsenként más,
és a színklaszterezés két csapatra van hangolva). Amit viszont a kész
Match-ből BIZTOSAN tudunk: a kapus az idejének túlnyomó részét a saját
kapuelőterében tölti — egyetlen mezőnyjátékos sem teszi ezt (a 6 m-esen
belül támadóként tartózkodni szabálytalan, védőként átmeneti).

Módszer: trackenként megmérjük, a MÉRT idejének mekkora hányada esik a
két kapu köré rajzolt körbe. Kapunként a legnagyobb hányadú track kap
"kapus" szerepet, ha a hányad és a minta is elég nagy. A döntés a track
MINDEN pozíciójára rákerül (role="kapus") — a kliens jelölheti, az
elemzések (pl. felderítés kulcsjátékosai) pedig figyelembe vehetik.

Korlát: ha egy track átível a félidőn (térfélcsere), a hányad felhígul —
a gyakorlatban a felvételek félidőnként készülnek, és a követés a
szünetben úgyis megszakad. Tiszta adatfeldolgozás, videó nélkül tesztelhető.
"""

from __future__ import annotations

import math

from ..models.tracking import Match, PositionSource
from .calibration import COURT_LENGTH_M, COURT_WIDTH_M

# A kapuelőtér sugara + ráhagyás (a 6 m-es vonalon kicsit kívülre is kilép).
GOAL_AREA_RADIUS_M = 6.8
# A mért idejének legalább ekkora hányada a kapuelőtérben → kapus-jelölt.
MIN_SHARE = 0.55
# Legalább ennyi mért jelenlét (mp) kell a döntéshez (zajos rövid track ne).
MIN_SECONDS = 8.0

ROLE_GOALKEEPER = "kapus"


def detect_goalkeepers(match: Match,
                       radius_m: float = GOAL_AREA_RADIUS_M,
                       min_share: float = MIN_SHARE,
                       min_seconds: float = MIN_SECONDS) -> dict[int, float]:
    """Kapusok azonosítása és megjelölése (helyben, role="kapus").

    Kapunként (bal: x=0, jobb: x=40) legfeljebb EGY track kap kapus
    szerepet — az, amelyik a mért idejének legnagyobb (és legalább
    `min_share`) hányadát tölti az adott kapuelőtérben.

    Visszatérés: {track_id: kapuelőtér-hányad} a megjelölt kapusokra.
    """
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    goals = ((0.0, COURT_WIDTH_M / 2.0), (COURT_LENGTH_M, COURT_WIDTH_M / 2.0))

    # Trackenként: mért kockák + kapunkénti "bent volt" kockák.
    total: dict[int, int] = {}
    in_area: dict[int, list[int]] = {}
    for frame in match.frames:
        for p in frame.players:
            if p.source != PositionSource.MEASURED:
                continue
            total[p.track_id] = total.get(p.track_id, 0) + 1
            rec = in_area.setdefault(p.track_id, [0, 0])
            for gi, (gx, gy) in enumerate(goals):
                if math.hypot(p.x - gx, p.y - gy) <= radius_m:
                    rec[gi] += 1

    min_frames = max(1, round(min_seconds * fps))
    chosen: dict[int, float] = {}
    for gi in range(2):
        best_tid = None
        best_share = 0.0
        for tid, n in total.items():
            if n < min_frames:
                continue
            share = in_area.get(tid, [0, 0])[gi] / n
            if share >= min_share and share > best_share:
                best_tid, best_share = tid, share
        if best_tid is not None:
            # Ha ugyanaz a track mindkét kapunál "nyerne" (nem életszerű),
            # a nagyobb hányad marad.
            if chosen.get(best_tid, 0.0) < best_share:
                chosen[best_tid] = best_share

    if chosen:
        for frame in match.frames:
            for p in frame.players:
                if p.track_id in chosen:
                    p.role = ROLE_GOALKEEPER
    return chosen

def goalkeeper_stats(match: Match, config=None) -> dict:
    """Kapus-teljesítmény a lövés-kimenetelekből (lásd event_detection).

    Csapatonként (amelyiknek van megjelölt kapusa): hány kapura tartó
    lövést kapott, ebből mennyit hárított / hány gólt kapott, védés-
    hatékonyság, és a KAPOTT gólok zóna-bontása (honnan verhető).

    Visszatérés: {"home"/"away": {"track_id", "on_target", "saves",
    "conceded", "save_pct", "conceded_zones": {zóna: db},
    "seven_faced", "seven_saved"}} — a hétméteres-mérleg a kapus
    szemszögéből (hány büntetővel nézett szembe / mennyit fogott).
    Csak azok a csapatok szerepelnek, ahol van kapus-jelölés.
    """
    from ..models.tracking import Team
    from .event_detection import EventType, detect_shots
    from .scouting import _shot_zone
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    gk_of_team: dict = {}
    for f in match.frames:
        for p in f.players:
            if p.role == ROLE_GOALKEEPER and p.team not in gk_of_team:
                gk_of_team[p.team] = p.track_id
    if not gk_of_team:
        return {}

    frames_by_t = {f.t: f for f in match.frames}
    out: dict = {}
    for team, tid in gk_of_team.items():
        out[team.value] = {"track_id": tid, "on_target": 0, "saves": 0,
                           "conceded": 0, "save_pct": 0.0,
                           "conceded_zones": {}, "on_target_zones": {},
                           "zone_save_pct": {},
                           "seven_faced": 0, "seven_saved": 0}

    for e in detect_shots(match, config):
        defending = Team.AWAY if e.team == Team.HOME else Team.HOME
        rec = out.get(defending.value)
        if rec is None:
            continue
        outcome = (e.detail or {}).get("outcome")
        if outcome not in ("goal", "save"):
            continue  # a mellé menő lövés nem a kapus dolga
        rec["on_target"] += 1
        # Honnan jött a kapura tartó lövés (a lövés pillanatának labda-
        # pozíciójából) — minden kapura tartó lövésnél, hogy a zóna-
        # bontásból védés-hatékonyságot is tudjunk számolni.
        z = None
        frame = frames_by_t.get(e.t)
        if frame is not None and frame.ball is not None:
            goal_x = config.attacks_toward_x(e.team)
            z = _shot_zone(frame.ball.x, frame.ball.y, goal_x)
            rec["on_target_zones"][z] = rec["on_target_zones"].get(z, 0) + 1
        if outcome == "save":
            rec["saves"] += 1
        else:
            rec["conceded"] += 1
            if z is not None:
                rec["conceded_zones"][z] = rec["conceded_zones"].get(z, 0) + 1

    # Hétméteresek a kapus szemszögéből: a VÉDEKEZŐ (kapus-) csapathoz
    # írjuk, hány büntetővel nézett szembe és mennyit fogott meg.
    try:
        from .rules import seven_meter_outcomes
        for sm in seven_meter_outcomes(match, config):
            defending = Team.AWAY if sm["team"] == "home" else Team.HOME
            rec = out.get(defending.value)
            if rec is None or sm["outcome"] == "ismeretlen":
                continue
            rec["seven_faced"] += 1
            if sm["outcome"] == "védés":
                rec["seven_saved"] += 1
    except Exception:
        pass  # a mérleg nélkül is teljes a kapus-statisztika

    for rec in out.values():
        if rec["on_target"]:
            rec["save_pct"] = round(100.0 * rec["saves"] / rec["on_target"], 1)
        # Zóna szerinti védés-hatékonyság: (kapura tartó − kapott) / kapura
        # tartó az adott zónában — melyik sarok a kapus gyenge/erős pontja.
        for zone, faced in rec["on_target_zones"].items():
            if not faced:
                continue
            conceded = rec["conceded_zones"].get(zone, 0)
            rec["zone_save_pct"][zone] = round(
                100.0 * (faced - conceded) / faced, 1)
    return out

# Kapus-csere: legalább ennyi ideig kell a kapuban lennie, hogy
# "szolgálatnak" számítson (a pillanatnyi track-villanás nem csere).
GK_STINT_MIN_S = 10.0


def goalkeeper_timeline(match: Match, config=None) -> dict:
    """Ki védett mikor — kapus-szolgálatok és cserék csapatonként.

    Kockánként megnézzük, melyik kapus-jelölésű track van a pályán az
    adott csapatból (ha több, a saját kapuhoz legközelebbi), és ebből
    összefüggő szolgálat-szakaszokat építünk (GK_STINT_MIN_S alatti
    szakasz zaj). Minden kapura tartó lövést az AKKOR szolgálatban lévő
    kapushoz írunk — így kapus-cserénél külön mérleg készül.

    Visszatérés csapatonként: {"stints": [{"track_id","from_s","to_s"}],
    "changes": [mp], "per_keeper": {tid: {"on_target","saves",
    "save_pct"}}} — üres, ha nincs kapus-jelölés.
    """
    from ..models.tracking import Team
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    min_frames = round(GK_STINT_MIN_S * fps)

    # Kockánkénti ügyeletes kapus csapatonként.
    duty: dict[str, list] = {"home": [], "away": []}  # (t, tid)
    for f in match.frames:
        for team in (Team.HOME, Team.AWAY):
            own_x = config.own_goal_x(team)
            gks = [p for p in f.players
                   if p.team == team and p.role == ROLE_GOALKEEPER]
            if not gks:
                continue
            gk = min(gks, key=lambda p: abs(p.x - own_x))
            duty[team.value].append((f.t, gk.track_id))

    out: dict = {}
    for side in ("home", "away"):
        seq = duty[side]
        stints = []
        for (t, tid) in seq:
            if stints and stints[-1]["tid"] == tid:
                stints[-1]["end"] = t
            else:
                stints.append({"tid": tid, "start": t, "end": t})
        # Zaj-szűrés: a rövid villanásokat eldobjuk, a szomszédos azonos
        # kapusú szakaszokat összevonjuk.
        stints = [st for st in stints
                  if st["end"] - st["start"] + 1 >= min_frames]
        merged = []
        for st in stints:
            if merged and merged[-1]["tid"] == st["tid"]:
                merged[-1]["end"] = st["end"]
            else:
                merged.append(dict(st))
        changes = [round(st["start"] / fps, 1) for st in merged[1:]]

        per_keeper: dict = {}
        if merged:
            def on_duty(t: int):
                for st in merged:
                    if st["start"] <= t <= st["end"]:
                        return st["tid"]
                # A szakaszok közti lyukban a legutóbbi szolgálat él.
                last = None
                for st in merged:
                    if st["start"] <= t:
                        last = st["tid"]
                return last

            defending = Team.HOME if side == "home" else Team.AWAY
            for e in detect_shots(match, config):
                if e.team == defending:
                    continue  # a saját lövésük nem a kapusuk dolga
                outcome = (e.detail or {}).get("outcome")
                if outcome not in ("goal", "save"):
                    continue
                tid = on_duty(e.t)
                if tid is None:
                    continue
                rec = per_keeper.setdefault(tid, {"on_target": 0,
                                                  "saves": 0,
                                                  "save_pct": 0.0})
                rec["on_target"] += 1
                if outcome == "save":
                    rec["saves"] += 1
            for rec in per_keeper.values():
                if rec["on_target"]:
                    rec["save_pct"] = round(
                        100.0 * rec["saves"] / rec["on_target"], 1)

        out[side] = {
            "stints": [{"track_id": st["tid"],
                        "from_s": round(st["start"] / fps, 1),
                        "to_s": round(st["end"] / fps, 1)}
                       for st in merged],
            "changes": changes,
            "per_keeper": per_keeper,
        }
    return out


# 7 a 6 elleni (üres kapus) játék felismerése:
EMPTY_NET_FAR_M = 12.0   # a kapus ennyire elhagyta a saját kapuját
EMPTY_NET_MIN_S = 3.0    # legalább ennyi ideig tartó szakasz számít
EMPTY_NET_JOIN_S = 1.0   # ennél rövidebb megszakadást összevonunk


def detect_empty_net(match: Match, config=None) -> list[dict]:
    """7 a 6 elleni (üres kapus) szakaszok felismerése.

    Jele: a megjelölt kapus tartósan TÁVOL van a saját kapujától (vagy
    lecserélték — a track eltűnt), miközben a CSAPATA birtokolja a labdát.
    A modern kézilabda tudatos fegyvere — az ellenfélnek (és a saját
    edzőnek) is fontos tudni, mikor és mennyit játszotta a csapat.

    Visszatérés: [{"team", "start_frame", "end_frame", "duration_s"}, ...]
    időrendben. Kapus-jelölés nélkül üres lista.
    """
    from .tactics import TacticsConfig, possession_team

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0

    gk_of_team: dict = {}
    for f in match.frames:
        for p in f.players:
            if p.role == ROLE_GOALKEEPER and p.team not in gk_of_team:
                gk_of_team[p.team] = p.track_id
    if not gk_of_team:
        return []

    # Kockánként: csapatonként "üres-e a kapu, miközben ők támadnak".
    flags: dict = {team: [] for team in gk_of_team}
    for f in match.frames:
        poss = possession_team(f, config)
        for team, tid in gk_of_team.items():
            gk_pos = next((p for p in f.players if p.track_id == tid), None)
            if gk_pos is None:
                away_from_goal = True  # lecserélve / nem látszik
            else:
                own_x = config.own_goal_x(team)
                away_from_goal = math.hypot(
                    gk_pos.x - own_x,
                    gk_pos.y - COURT_WIDTH_M / 2.0) > EMPTY_NET_FAR_M
            flags[team].append(bool(away_from_goal and poss == team))

    # Összefüggő szakaszok kigyűjtése + rövid lyukak összevonása.
    min_frames = max(1, round(EMPTY_NET_MIN_S * fps))
    join_frames = max(1, round(EMPTY_NET_JOIN_S * fps))
    out: list[dict] = []
    for team, seq in flags.items():
        runs: list[list[int]] = []
        start = None
        for i, on in enumerate(seq):
            if on and start is None:
                start = i
            elif not on and start is not None:
                runs.append([start, i - 1])
                start = None
        if start is not None:
            runs.append([start, len(seq) - 1])
        # Rövid megszakadások összevonása (pl. a labda 1-2 kockára szabad).
        merged: list[list[int]] = []
        for run in runs:
            if merged and run[0] - merged[-1][1] <= join_frames:
                merged[-1][1] = run[1]
            else:
                merged.append(run)
        for (a, b) in merged:
            if b - a + 1 >= min_frames:
                out.append({
                    "team": team.value,
                    "start_frame": match.frames[a].t,
                    "end_frame": match.frames[b].t,
                    "duration_s": round((b - a + 1) / fps, 1),
                })
    out.sort(key=lambda w: w["start_frame"])
    return out
