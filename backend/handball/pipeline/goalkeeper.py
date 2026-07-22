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
    "save_pct","faced_xg","conceded","prevented"}}} — üres, ha nincs
    kapus-jelölés. A prevented (GSAx) kapusonként: a kapott lövések
    helyzet-értéke mínusz a kapott gólok — cserénél így a két kapus
    a helyzetek nehézségén át is összemérhető.
    """
    from ..models.tracking import Team
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig
    from .xg import match_xg

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

    # A lövések helyzet-értéke időbélyeg szerint — a kapusonkénti
    # xG-mérleghez (a nehéz és a könnyű lövés nem ugyanannyit ér).
    try:
        xg_by_t = {sh["t"]: sh["xg"]
                   for sh in match_xg(match, config)["shots"]}
    except Exception:
        xg_by_t = {}

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
                rec = per_keeper.setdefault(
                    tid, {"on_target": 0, "saves": 0, "save_pct": 0.0,
                          "faced_xg": 0.0, "conceded": 0,
                          "prevented": 0.0})
                rec["on_target"] += 1
                rec["faced_xg"] += xg_by_t.get(e.t, 0.0)
                if outcome == "save":
                    rec["saves"] += 1
                else:
                    rec["conceded"] += 1
            for rec in per_keeper.values():
                if rec["on_target"]:
                    rec["save_pct"] = round(
                        100.0 * rec["saves"] / rec["on_target"], 1)
                rec["faced_xg"] = round(rec["faced_xg"], 2)
                rec["prevented"] = round(
                    rec["faced_xg"] - rec["conceded"], 2)

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


# Kapus-indítás: védés után ennyi másodpercen belül átért labda számít
# gyors felhozatalnak; ennél tovább már nem az indítást mérjük.
OUTLET_FAST_S = 6.0
OUTLET_MAX_S = 20.0
# A felező-átlépésnél ennyire közel álló saját játékos számít az
# indítás célpontjának.
OUTLET_TARGET_RADIUS_M = 4.0


def outlet_speed(match: Match, config=None) -> dict:
    """Kapus-indítás: védés után mennyi idő alatt ér a labda a felezőig
    a VÉDŐ csapat támadó irányába. A gyors kidobás kontra-fegyver — a
    lassú felhozatal idejét ad az ellenfél visszarendeződésének.

    Visszatérés csapatonként (a védést jegyző oldal):
      {"saves", "outlets", "sum_s", "avg_s", "fast",
       "targets": [{"player_id", "n"}]}
    ahol avg_s None, ha nem volt mérhető indítás; a targets a
    felező-átlépésnél a labdához legközelebbi saját mezőnyjátékos —
    az indítás tipikus célpontja.
    """
    from .xg import match_xg
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    out = {side: {"saves": 0, "outlets": 0, "sum_s": 0.0, "fast": 0,
                  "targets": {}}
           for side in ("home", "away")}
    frames = match.frames
    frames_by_t = {f.t: f for f in frames}
    for sh in match_xg(match, config).get("shots", []):
        if sh.get("outcome") != "save":
            continue
        def_side = "away" if sh["team"] == "home" else "home"
        rec = out[def_side]
        rec["saves"] += 1
        # A védés utáni első felező-átlépés a védő csapat irányába:
        # a home lövő a +x kapura lőtt, így az away indítás x < 20 felé
        # megy (és fordítva).
        t0 = sh["t"]
        crossed = None
        for fr in frames:
            if fr.t <= t0 or fr.ball is None:
                continue
            if (fr.t - t0) / fps > OUTLET_MAX_S:
                break
            if sh["team"] == "home" and fr.ball.x < 20.0:
                crossed = fr.t
                break
            if sh["team"] == "away" and fr.ball.x > 20.0:
                crossed = fr.t
                break
        if crossed is not None:
            dt = (crossed - t0) / fps
            rec["outlets"] += 1
            rec["sum_s"] += dt
            if dt <= OUTLET_FAST_S:
                rec["fast"] += 1
            # A célpont: az átlépésnél a labdához legközelebbi saját
            # (nem kapus) játékos — neki megy az első hosszú passz.
            fr = frames_by_t.get(crossed)
            if fr is not None and fr.ball is not None:
                cand = [(abs(p.x - fr.ball.x) + abs(p.y - fr.ball.y), p)
                        for p in fr.players
                        if getattr(p.team, "value", p.team) == def_side
                        and getattr(p, "role", None) != "kapus"]
                if cand:
                    d, p = min(cand, key=lambda c: c[0])
                    if d <= OUTLET_TARGET_RADIUS_M:
                        rec["targets"][p.track_id] = (
                            rec["targets"].get(p.track_id, 0) + 1)
    for rec in out.values():
        rec["avg_s"] = (round(rec["sum_s"] / rec["outlets"], 1)
                        if rec["outlets"] else None)
        rec["sum_s"] = round(rec["sum_s"], 1)
        rec["targets"] = [{"player_id": pid, "n": n}
                          for pid, n in sorted(rec["targets"].items(),
                                               key=lambda kv: -kv[1])]
    return out


# Az üres-kapus szakasz vége után ennyi másodpercig a kapott gól még
# a lehozott kapus árának számít (amíg a kapus visszaér).
EMPTY_NET_GOAL_MARGIN_S = 5.0


def empty_net_goals(match: Match, config=None) -> dict:
    """Üres kapura kapott gólok: a 7 a 6 (lehozott kapus) ára.

    Egy gól akkor "üres kapus", ha a kapott gól pillanatában a kapuját
    elhagyó csapat épp felismert üres-kapus szakaszban volt. Ez mutatja
    meg, megérte-e a plusz mezőnyjátékos.

    Visszatérés csapatonként: {"windows", "empty_s", "conceded_empty",
    "scored_7v6"} — a kapott ÉS a dobott gólok a 7 a 6 alatt (mérleg).
    """
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    margin = EMPTY_NET_GOAL_MARGIN_S * fps
    windows = detect_empty_net(match, config)
    out = {side: {"windows": 0, "empty_s": 0.0, "conceded_empty": 0,
                  "scored_7v6": 0}
           for side in ("home", "away")}
    for w in windows:
        rec = out[w["team"]]
        rec["windows"] += 1
        rec["empty_s"] += w["duration_s"]
    for e in detect_shots(match, config):
        if e.type != EventType.GOAL:
            continue
        scorer = getattr(e.team, "value", e.team)
        conceding = "away" if scorer == "home" else "home"
        for w in windows:
            # A szakasz vége után is számít pár másodpercig: a büntető
            # gól tipikusan a labdaszerzés UTÁN esik, amíg a kapus
            # visszaér (a birtoklás-váltás már lezárta a szakaszt).
            if (w["team"] == conceding
                    and w["start_frame"] <= e.t <= w["end_frame"] + margin):
                out[conceding]["conceded_empty"] += 1
                break
        # A haszon-oldal: a dobó csapat épp 7 a 6-ban játszott-e.
        for w in windows:
            if (w["team"] == scorer
                    and w["start_frame"] <= e.t <= w["end_frame"] + margin):
                out[scorer]["scored_7v6"] += 1
                break
    for rec in out.values():
        rec["empty_s"] = round(rec["empty_s"], 1)
    return out


# A 7 a 6 időzítés-elemzésben a "hajrá" a felvétel utolsó ennyi perce —
# és csak elég hosszú (20+ perces) felvételen értelmezzük.
EN_ENDGAME_WINDOW_MIN = 10.0
EN_ENDGAME_MIN_DURATION_MIN = 20.0


def empty_net_context(match: Match, config=None) -> dict:
    """A 7 a 6 szakaszok játékhelyzete: állásból és időből mikor húzzák
    elő a lehozott kapust. A felderítés ebből mondja meg, mikor kell rá
    készülni ("ha vezetsz ellenük, jön a 7 a 6").

    Visszatérés csapatonként: {"windows", "trailing", "endgame"} —
    trailing: hátrányban indított szakaszok; endgame: a hajrában
    (utolsó 10 perc) indítottak, csak 20+ perces felvételen.
    """
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    total = len(match.frames)
    duration_min = total / fps / 60.0
    goals = sorted((e.t, getattr(e.team, "value", e.team))
                   for e in detect_shots(match, config)
                   if e.type == EventType.GOAL)
    out = {side: {"windows": 0, "trailing": 0, "endgame": 0}
           for side in ("home", "away")}
    for w in detect_empty_net(match, config):
        side = w["team"]
        rec = out[side]
        rec["windows"] += 1
        own = sum(1 for (t, tm) in goals
                  if tm == side and t < w["start_frame"])
        opp = sum(1 for (t, tm) in goals
                  if tm != side and t < w["start_frame"])
        if own < opp:
            rec["trailing"] += 1
        if (duration_min >= EN_ENDGAME_MIN_DURATION_MIN
                and w["start_frame"] >= total
                - EN_ENDGAME_WINDOW_MIN * 60.0 * fps):
            rec["endgame"] += 1
    return out


# Kapus-kimozdulás: e felett az átlagos kapu-távolság felett "kint
# álló" a kapus (átemelhető), ez alatt "vonalon maradó".
GK_DEPTH_OUT_M = 1.5
GK_DEPTH_MIN_FRAMES = 100


def gk_positioning(match, config=None) -> dict:
    """Kapus-kimozdulás: milyen mélyen áll a kapus a kapuja előtt.

    Kockánként a kapus-jelölésű játékos távolsága a SAJÁT kapu
    közepétől (x-irányban a gólvonaltól, y-ban a kapu-középtől) — a
    kint álló kapus az átemelés/lob ellen sebezhető, a vonalon maradó
    a közeli lövésnél ad nagyobb felületet.

    Visszatérés csapatonként: {"avg_depth_m", "frames", "style"}
    — style: "kint álló" / "vonalon maradó" / "kiegyensúlyozott";
    avg_depth_m None, ha nincs elég mért kocka (GK_DEPTH_MIN_FRAMES).
    """
    import math

    from ..models.tracking import Team
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    acc = {Team.HOME: [0.0, 0], Team.AWAY: [0.0, 0]}
    for f in match.frames:
        for p in f.players:
            if p.role != "kapus":
                continue
            own_x = config.own_goal_x(p.team)
            d = math.hypot(p.x - own_x, p.y - 10.0)
            acc[p.team][0] += d
            acc[p.team][1] += 1
    out = {}
    for team in (Team.HOME, Team.AWAY):
        total, n = acc[team]
        if n < GK_DEPTH_MIN_FRAMES:
            out[team.value] = {"avg_depth_m": None, "frames": n,
                               "style": None}
            continue
        avg = round(total / n, 2)
        style = ("kint álló" if avg >= GK_DEPTH_OUT_M
                 else "vonalon maradó" if avg <= 0.8
                 else "kiegyensúlyozott")
        out[team.value] = {"avg_depth_m": avg, "frames": n,
                           "style": style}
    return out


# Egy sáv "megbízhatóságához" ennyi kaputra érkező lövés kell — kevesebből
# a védési arány zajos, nem mondunk róla ítéletet.
GK_RANGE_MIN_FACED = 3


def gk_save_ranges(match, config=None) -> dict:
    """Kapus védés-hatékonyság lövés-távolság szerint: melyik távolságból
    sebezhető a kapus.

    Csapatonként (a VÉDŐ oldal = akinek a kapusa a kapuban van) a rá KAPUTra
    érkezett lövéseket (gól + védés; a mellé/blokk nem kaputra megy) a lövő
    kapu-távolsága alapján közeli / közép / távoli sávba sorolja, és
    sávonként számol védési arányt. A lövő távolságát és a kimenetelt a
    match_xg adja; a sáv-küszöbök azonosak a lövés-távolság réteggel.

    Visszatérés csapatonként:
      {"close"/"mid"/"far": {"faced", "saves", "save_pct"},
       "on_target", "weak_band"} — weak_band a legrosszabb védési arányú
    sáv (elég lövéssel: GK_RANGE_MIN_FACED), None, ha nincs ilyen.
    """
    import math

    from .attack_types import SHOT_RANGE_CLOSE_M, SHOT_RANGE_MID_M
    from .calibration import COURT_WIDTH_M
    from .tactics import TacticsConfig
    from .xg import match_xg

    config = config or TacticsConfig()
    goal_cy = COURT_WIDTH_M / 2.0
    xg = match_xg(match, config)

    def _band(x: float, y: float, shooter_team: str) -> str:
        from ..models.tracking import Team
        goal_x = config.attacks_toward_x(
            Team.HOME if shooter_team == "home" else Team.AWAY)
        dist = math.hypot(x - goal_x, y - goal_cy)
        if dist <= SHOT_RANGE_CLOSE_M:
            return "close"
        if dist <= SHOT_RANGE_MID_M:
            return "mid"
        return "far"

    out: dict = {}
    for side in ("home", "away"):
        bands = {b: {"faced": 0, "saves": 0} for b in ("close", "mid", "far")}
        for sh in xg["shots"]:
            # A VÉDŐ oldal kapusát a MÁSIK csapat lövése terheli.
            if sh["team"] == side:
                continue
            outcome = sh["outcome"]
            if outcome not in ("goal", "save"):
                continue  # mellé/blokk: nem kaputra érkezett
            b = _band(sh["x"], sh["y"], sh["team"])
            bands[b]["faced"] += 1
            if outcome == "save":
                bands[b]["saves"] += 1
        on_target = sum(bands[b]["faced"] for b in bands)
        for b in bands:
            n = bands[b]["faced"]
            bands[b]["save_pct"] = (round(100.0 * bands[b]["saves"] / n, 1)
                                    if n else None)
        # A leggyengébb sáv (elég lövéssel) — itt sebezhető a kapus.
        cand = [b for b in ("close", "mid", "far")
                if bands[b]["faced"] >= GK_RANGE_MIN_FACED]
        weak = min(cand, key=lambda b: bands[b]["save_pct"]) if cand else None
        out[side] = {**bands, "on_target": on_target, "weak_band": weak}
    return out
