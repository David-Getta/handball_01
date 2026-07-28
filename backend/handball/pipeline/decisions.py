"""
[4. fázis] Játékos-döntéselemzés — "mit választott, és mi lett volna a legjobb".

A vízió egyéni elemzés része: egy adott szituációban a labdás játékos opciói
(lövés, vagy passz egy-egy csapattárshoz), ezek ÉRTÉKE, és hogy a tényleges
döntés mennyire volt jó. Aggregálva: "ez a játékos hányszor passzol ide" + milyen
gyakran választja az optimális opciót.

Az értékmodell egy EGYSZERŰ, kézilabdára szabott xG-szerű (várható-érték) heurisztika:
- Lövés értéke: a kaputól mért távolság és a szög alapján (közel + középről = több).
- Passz értéke: a fogadó helyzetéből számolt lövésérték, beszorozva a passz
  sikervalószínűségével (távolság + a passz vonalában álló védők).

Ez nem a végső, betanított EPV-modell, de a felismerés és a kiértékelés CSŐVEZETÉKE
ez — a heurisztika később valódi adatból tanult modellre cserélhető. Tiszta Python,
videó nélkül tesztelhető.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from ..models.tracking import Match, Frame, PlayerPosition, Team
from .calibration import COURT_LENGTH_M, COURT_WIDTH_M
from .tactics import TacticsConfig

GOAL_Y = COURT_WIDTH_M / 2.0  # a kapu közepe y-ban (10 m)


# ---- Értékmodell -----------------------------------------------------------

def shot_value(px: float, py: float, goal_x: float) -> float:
    """Egy lövés xG-szerű értéke (0..1) a pozícióból, a megadott kapu felé.

    Két tényező: a kaputól mért TÁVOLSÁG (közelebb = jobb) és a SZÖG (középről =
    jobb, szélről rosszabb). Monoton és [0,1] közé vágva.
    """
    dist = math.hypot(px - goal_x, py - GOAL_Y)
    lateral = abs(py - GOAL_Y)                       # oldalirányú eltérés a kaputól
    angle_factor = max(0.25, 1.0 - lateral / 14.0)   # szélen kisebb
    base = max(0.0, 1.0 - dist / 22.0)               # ~22 m-en túl ~0
    return max(0.02, min(0.95, base * angle_factor))


def _point_segment_distance(px, py, ax, ay, bx, by) -> float:
    """Egy pont (p) távolsága az A–B szakasztól (a passz vonalának ellenőrzéséhez)."""
    dx, dy = bx - ax, by - ay
    seg_len2 = dx * dx + dy * dy
    if seg_len2 == 0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / seg_len2
    t = max(0.0, min(1.0, t))
    cx, cy = ax + t * dx, ay + t * dy
    return math.hypot(px - cx, py - cy)


def pass_completion(holder: PlayerPosition, target: PlayerPosition,
                    frame: Frame, lane_width_m: float = 1.5) -> float:
    """A passz sikervalószínűsége (0..1): távolság + a vonalban álló védők alapján.

    Hosszabb passz kockázatosabb; a holder–target vonalához közeli ELLENFELEK
    (a sávon belül) tovább csökkentik az esélyt.
    """
    dist = math.hypot(holder.x - target.x, holder.y - target.y)
    base = max(0.1, 1.0 - dist / 35.0)
    lane_def = 0
    for p in frame.players:
        if p.team == holder.team:
            continue
        d = _point_segment_distance(p.x, p.y, holder.x, holder.y, target.x, target.y)
        if d <= lane_width_m:
            lane_def += 1
    return max(0.05, min(0.99, base - 0.3 * lane_def))


# ---- Opciók egy szituációban ----------------------------------------------

@dataclass
class Option:
    """Egy döntési opció a labdás játékosnak.

    - kind:      "shoot" (lövés) vagy "pass" (passz).
    - target_id: passznál a fogadó track_id-ja; lövésnél None.
    - value:     az opció becsült értéke (0..1).
    """
    kind: str
    target_id: Optional[int]
    value: float


def ball_holder(frame: Frame, config: TacticsConfig) -> Optional[PlayerPosition]:
    """A labdát épp birtokló JÁTÉKOS (a labdához legközelebbi, sugáron belül)."""
    ball = frame.ball
    if ball is None or not frame.players:
        return None
    nearest = min(frame.players, key=lambda p: math.hypot(p.x - ball.x, p.y - ball.y))
    if math.hypot(nearest.x - ball.x, nearest.y - ball.y) > config.possession_radius_m:
        return None
    return nearest


# Támogatás-távolság: ennyi labdás kocka kell az ítélethez; a legközelebbi
# társ e fölött "izolált" labdás, ez alatt szoros a támogatás.
SUPPORT_MIN_FRAMES = 100
SUPPORT_ISO_M = 7.0
SUPPORT_TIGHT_M = 4.0


def support_distance(match: Match,
                     config: Optional[TacticsConfig] = None) -> dict:
    """Támogatás-távolság (izoláció-jel): milyen messze van a labdás
    játékostól a LEGKÖZELEBBI társa.

    Minden kockán, ahol azonosított labdabirtokos van, megmérjük a
    legközelebbi saját csapattárs távolságát. Ha a labdás rendre magára
    marad (nagy átlag, sok izolált kocka), a présjáték működik ellene —
    kényszerített egyéni megoldások és eladások jönnek; ha a támogatás
    szoros, a rövid passzos kijátszás pörög, a prés kockázatos ellene.

    Visszatérés csapatonként:
      {"frames", "avg_m", "iso_frames", "iso_pct"} — a mért labdás kockák
    száma, a legközelebbi társ átlagtávolsága, az izolált (SUPPORT_ISO_M+)
    kockák száma és aránya. avg_m/iso_pct None, ha frames < SUPPORT_MIN_FRAMES.
    """
    config = config or TacticsConfig()
    acc = {"home": [0, 0.0, 0], "away": [0, 0.0, 0]}  # n, összeg, izolált
    for f in match.frames:
        holder = ball_holder(f, config)
        if holder is None:
            continue
        mates = [p for p in f.players
                 if p.team == holder.team and p.track_id != holder.track_id]
        if not mates:
            continue
        d = min(math.hypot(p.x - holder.x, p.y - holder.y) for p in mates)
        rec = acc[holder.team.value]
        rec[0] += 1
        rec[1] += d
        if d >= SUPPORT_ISO_M:
            rec[2] += 1

    out: dict = {}
    for s in ("home", "away"):
        n, total, iso = acc[s]
        ok = n >= SUPPORT_MIN_FRAMES
        out[s] = {
            "frames": n,
            "avg_m": round(total / n, 2) if ok else None,
            "iso_frames": iso,
            "iso_pct": round(100.0 * iso / n, 1) if ok else None,
        }
    return out


def evaluate_options(frame: Frame, holder: PlayerPosition,
                     config: Optional[TacticsConfig] = None) -> list[Option]:
    """A labdás játékos összes opciója értékkel: lövés + passz minden csapattárshoz."""
    config = config or TacticsConfig()
    goal_x = config.attacks_toward_x(holder.team)
    options = [Option("shoot", None, shot_value(holder.x, holder.y, goal_x))]
    for p in frame.players:
        if p.team != holder.team or p.track_id == holder.track_id:
            continue
        sv = shot_value(p.x, p.y, goal_x)
        comp = pass_completion(holder, p, frame)
        options.append(Option("pass", p.track_id, sv * comp))
    return options


def best_option(options: list[Option]) -> Optional[Option]:
    """A legnagyobb értékű opció (vagy None, ha nincs)."""
    return max(options, key=lambda o: o.value) if options else None


# ---- Passzok felismerése és a döntések elemzése ----------------------------

@dataclass
class PassEvent:
    """Egy felismert passz: a labda egy csapattárshoz került.

    - t:             a passz "megérkezésének" frame-ideje.
    - passer_id:     a passzoló track_id-ja.
    - receiver_id:   a fogadó track_id-ja.
    - team:          a csapat.
    - decision_frame: a döntés frame-je (ahol a passzoló még birtokolta a labdát).
    - passer_pos:    a passzoló pozíciója a döntés pillanatában.
    """
    t: int
    passer_id: int
    receiver_id: int
    team: Team
    decision_frame: Frame
    passer_pos: PlayerPosition


def detect_passes(match: Match, config: Optional[TacticsConfig] = None) -> list[PassEvent]:
    """Passzok felismerése: a labdabirtokos csapaton belüli VÁLTÁSA egy passz.

    Végigmegyünk a frame-eken; ha a labdás játékos megváltozik UGYANAZON a
    csapaton belül, az egy passz (az előző birtokostól az újhoz).
    """
    config = config or TacticsConfig()
    passes: list[PassEvent] = []
    prev_holder: Optional[PlayerPosition] = None
    prev_frame: Optional[Frame] = None

    for f in match.frames:
        holder = ball_holder(f, config)
        if holder is not None and prev_holder is not None:
            if holder.team == prev_holder.team and holder.track_id != prev_holder.track_id:
                passes.append(PassEvent(
                    t=f.t, passer_id=prev_holder.track_id, receiver_id=holder.track_id,
                    team=holder.team, decision_frame=prev_frame, passer_pos=prev_holder,
                ))
        if holder is not None:
            prev_holder = holder
            prev_frame = f
    return passes


@dataclass
class DecisionReport:
    """Egy játékos döntéseinek összegzése.

    - player_id:        a vizsgált játékos.
    - passes:           hány passzát ismertük fel.
    - pass_distribution: fogadónként hány passz (pl. "10/7-szer ide passzol").
    - optimal_rate:     a passzok hányada (0..1), ahol az ÉRTÉK szerinti legjobb
                        opció épp a választott passz volt.
    - avg_value_gap:    átlagosan mennyi értéket "hagyott az asztalon" (a legjobb
                        opció értéke − a választott opció értéke).
    """
    player_id: int
    passes: int
    pass_distribution: dict[int, int] = field(default_factory=dict)
    optimal_rate: float = 0.0
    avg_value_gap: float = 0.0


def analyze_player_decisions(match: Match, player_id: int,
                             config: Optional[TacticsConfig] = None) -> DecisionReport:
    """Egy játékos passz-döntéseinek elemzése: kihez passzol és mennyire optimálisan.

    Minden passzánál a döntés pillanatában kiértékeljük az opciókat, megnézzük a
    legjobbat, és összevetjük a ténylegesen választott passzal.
    """
    config = config or TacticsConfig()
    passes = [pe for pe in detect_passes(match, config) if pe.passer_id == player_id]

    distribution: dict[int, int] = {}
    optimal = 0
    gaps: list[float] = []

    for pe in passes:
        distribution[pe.receiver_id] = distribution.get(pe.receiver_id, 0) + 1
        options = evaluate_options(pe.decision_frame, pe.passer_pos, config)
        best = best_option(options)
        # A ténylegesen választott opció: passz a fogadóhoz.
        actual = next((o for o in options
                       if o.kind == "pass" and o.target_id == pe.receiver_id), None)
        if best is not None and actual is not None:
            gaps.append(best.value - actual.value)
            if abs(best.value - actual.value) < 1e-9:
                optimal += 1

    n = len(passes)
    return DecisionReport(
        player_id=player_id,
        passes=n,
        pass_distribution=distribution,
        optimal_rate=(optimal / n) if n else 0.0,
        avg_value_gap=(sum(gaps) / len(gaps)) if gaps else 0.0,
    )


# Pressz-tűrés: testközelinek ennyi méteren belüli védő számít; ennyi
# esemény kell mindkét (nyomott/szabad) mintához, és ekkora
# eladás-arány-többlet (százalékpont) számít érdeminek.
PRESS_TIGHT_M = 2.0
PRESS_MIN_EVENTS = 10
PRESS_TO_RISE_PP = 15.0


def pass_security_under_pressure(match: Match,
                                 config: Optional[TacticsConfig] = None
                                 ) -> dict:
    """Pressz-tűrés: labdabiztonság testközeli védő mellett vs szabadon.

    A nyomás alatti BEFEJEZÉST a pressure_finishing méri — itt a
    passzjáték biztonsága a kérdés: rászorított (PRESS_TIGHT_M-en
    belüli) védő mellett mennyivel nő a labdaeladás aránya a szabad
    helyzethez képest. Akinél nagyot nő, az pressz-érzékeny: az
    agresszív, kilépő fal és a kettőzés ellene nem kockázat, hanem
    termelés. Akinél nem, azt szorongatni fölösleges — ellene a
    kompakt, mély fal a jobb terv.

    Minden csapaton belüli passznál (detect_passes) a döntés-kockán
    mérjük a passzolóhoz legközelebbi (nem kapus) védő távolságát;
    minden labdaeladásnál (TURNOVER) a vesztes utolsó ismert
    pozícióján ugyanezt — így minden labdás döntés "nyomott" vagy
    "szabad" mintába esik.

    Visszatérés csapatonként: {"press_passes", "press_to",
    "free_passes", "free_to", "press_to_pct", "free_to_pct",
    "rise_pp"} — a százalékok és rise_pp None, ha bármelyik minta
    kevés (PRESS_MIN_EVENTS alatti).
    """
    import math

    from .event_detection import EventType, detect_events

    config = config or TacticsConfig()
    frames = match.frames
    idx_of = {f.t: i for i, f in enumerate(frames)}

    def _tight(frame: Frame, pos, team) -> bool:
        dists = [math.hypot(p.x - pos.x, p.y - pos.y)
                 for p in frame.players
                 if p.team != team and p.role != "kapus"]
        return bool(dists) and min(dists) <= PRESS_TIGHT_M

    out = {side: {"press_passes": 0, "press_to": 0,
                  "free_passes": 0, "free_to": 0,
                  "press_to_pct": None, "free_to_pct": None,
                  "rise_pp": None}
           for side in ("home", "away")}
    for pe in detect_passes(match, config):
        if pe.decision_frame is None or pe.passer_pos is None:
            continue
        rec = out[pe.team.value]
        if _tight(pe.decision_frame, pe.passer_pos, pe.team):
            rec["press_passes"] += 1
        else:
            rec["free_passes"] += 1
    for e in detect_events(match, config):
        if e.type != EventType.TURNOVER or e.player_id is None:
            continue
        i0 = idx_of.get(e.t)
        if i0 is None:
            continue
        # A vesztes utolsó ismert pozíciója az esemény előtti kockákon.
        placed = False
        for j in range(i0 - 1, max(-1, i0 - 13), -1):
            loser = next((p for p in frames[j].players
                          if p.track_id == e.player_id), None)
            if loser is None:
                continue
            rec = out[e.team.value]
            if _tight(frames[j], loser, e.team):
                rec["press_to"] += 1
            else:
                rec["free_to"] += 1
            placed = True
            break
        if not placed:
            continue
    for rec in out.values():
        press_n = rec["press_passes"] + rec["press_to"]
        free_n = rec["free_passes"] + rec["free_to"]
        if press_n >= PRESS_MIN_EVENTS and free_n >= PRESS_MIN_EVENTS:
            rec["press_to_pct"] = round(100.0 * rec["press_to"] / press_n, 1)
            rec["free_to_pct"] = round(100.0 * rec["free_to"] / free_n, 1)
            rec["rise_pp"] = round(
                rec["press_to_pct"] - rec["free_to_pct"], 1)
    return out


# Labdatartás-idő: ennél rövidebb birtoklás csak érintés (zaj), ennyi
# labdás szakasztól ítélünk egy játékost, és ennyi másodperccel a
# csapatátlag felett labdatartó a játékos.
HOLD_MIN_FRAMES = 5
HOLD_MIN_HOLDS = 5
HOLD_GAP_S = 0.8


def hold_time_players(match: Match,
                      config: Optional[TacticsConfig] = None) -> dict:
    """Labdatartás-idő: KI meddig tartja magánál a labdát.

    A passz-tempó (pass_tempo) és a támadás-ritmus csapatszinten mondja
    meg, pörög-e a játék — ez a névre szóló olvasata: minden labdás
    szakasz hosszát a birtokoshoz írjuk, és nézzük, kinél áll meg a
    labda. Az érintésnyi (HOLD_MIN_FRAMES alatti) birtoklás zaj, azt
    nem számoljuk.

    Edzőileg két irányba szól: ellenfélnél a hosszan tartó labdás a
    kettőzés célpontja (nála van idő odaérni, és nála lassul a
    támadásuk), saját oldalon pedig a gyorsabb továbbítás témája —
    egy-két tizeddel korábbi passz egy egész átrendeződést ér.

    Visszatérés csapatonként:
      {"holds", "seconds", "avg_s", "players": [{"player_id", "jersey",
       "holds", "seconds", "avg_s"}], "slowest": {..., "gap_s"}|None}
    — players az átlagos tartás szerint csökkenően; avg_s és slowest
    None, ha kevés a minta (HOLD_MIN_HOLDS).
    """
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    jersey: dict[int, int] = {}
    tally: dict[str, dict[int, list]] = {"home": {}, "away": {}}
    run_id = run_team = None
    run_len = 0

    def _close():
        """A lezáruló labdás szakasz jóváírása a birtokosnál."""
        if run_id is None or run_team is None:
            return
        if run_len < HOLD_MIN_FRAMES:
            return
        rec = tally[run_team].setdefault(run_id, [0, 0])
        rec[0] += 1
        rec[1] += run_len

    for f in match.frames:
        holder = ball_holder(f, config)
        pid = holder.track_id if holder is not None else None
        side = (holder.team.value
                if holder is not None and holder.team is not None
                else None)
        if holder is not None and holder.jersey_number is not None:
            jersey.setdefault(holder.track_id, holder.jersey_number)
        if pid != run_id or side != run_team:
            _close()
            run_id, run_team, run_len = pid, side, 0
        if pid is not None and side is not None:
            run_len += 1
    _close()

    out: dict = {}
    for s in ("home", "away"):
        players = []
        for pid, (holds, frames) in tally[s].items():
            players.append({"player_id": pid, "jersey": jersey.get(pid),
                            "holds": holds,
                            "seconds": round(frames / fps, 1),
                            "avg_s": round(frames / fps / holds, 2)})
        players.sort(key=lambda p: -p["avg_s"])
        n_holds = sum(p["holds"] for p in players)
        n_sec = round(sum(p["seconds"] for p in players), 1)
        team_avg = (round(n_sec / n_holds, 2) if n_holds else None)
        slowest = None
        if n_holds >= HOLD_MIN_HOLDS and team_avg:
            cands = [{**p, "gap_s": round(p["avg_s"] - team_avg, 2)}
                     for p in players
                     if p["holds"] >= HOLD_MIN_HOLDS
                     and p["avg_s"] - team_avg >= HOLD_GAP_S]
            if cands:
                slowest = max(cands, key=lambda p: p["gap_s"])
        out[s] = {"holds": n_holds, "seconds": n_sec,
                  "avg_s": (team_avg if n_holds >= HOLD_MIN_HOLDS
                            else None),
                  "players": players, "slowest": slowest}
    return out


# Passz-sebesség: ennyi mért passz kell az ítélethez, e felett számít
# élesnek egy passz, és e felett már mérési hiba (követés-ugrás).
PASS_SPEED_MIN_PASSES = 10
PASS_SPEED_FAST_MS = 12.0
PASS_SPEED_MAX_MS = 25.0


def pass_speed(match: Match,
               config: Optional[TacticsConfig] = None) -> dict:
    """Passz-sebesség: ÉLES vagy LÁGY a labdajáratásuk.

    A passz-hossz (pass_length) azt mondja meg, MEKKORA távra
    passzolnak, a passz-tempó (pass_tempo) azt, MILYEN SŰRŰN — ez azt,
    milyen KEMÉNYEN: a passzoló döntés-pillanata és a fogadó
    átvételének ideje közti repülési időből és a köztük mért távolságból
    számolunk sebességet. Az egy kockán belüli birtokosváltást (ott a
    repülési idő nem mérhető) és a PASS_SPEED_MAX_MS feletti értékeket
    (követés-ugrás) kihagyjuk.

    Edzőileg: az éles, feszes passz ellen a passz-vonalba nyúlás
    kockázatos — testtel kell zárni és a fogadót kell megfogni; a lágy,
    ívelt labdajáratásba viszont bele lehet érni: kilépés, beleérő
    védekezés és a második passz elfogása azonnal termel.

    Visszatérés csapatonként: {"passes", "avg_ms", "fast", "fast_pct",
    "label"} — az avg_ms/fast_pct/label None PASS_SPEED_MIN_PASSES
    alatt; a label "éles passzjáték" / "lágy labdajáratás" / None.
    """
    import math

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    by_t = {f.t: f for f in match.frames}

    acc = {"home": [0, 0.0, 0], "away": [0, 0.0, 0]}  # n, összeg, éles
    for p in detect_passes(match, config):
        if p.decision_frame is None:
            continue
        dt = p.t - p.decision_frame.t
        if dt < 2:
            continue  # egy kockán belüli váltás: a repülési idő nem mérhető
        fr = by_t.get(p.t)
        if fr is None:
            continue
        receiver = next((q for q in fr.players
                         if q.track_id == p.receiver_id), None)
        if receiver is None:
            continue
        dist = math.hypot(receiver.x - p.passer_pos.x,
                          receiver.y - p.passer_pos.y)
        speed = dist / (dt / fps)
        if speed > PASS_SPEED_MAX_MS:
            continue
        rec = acc[p.team.value]
        rec[0] += 1
        rec[1] += speed
        if speed >= PASS_SPEED_FAST_MS:
            rec[2] += 1

    out: dict = {}
    for side in ("home", "away"):
        n, total, fast = acc[side]
        ok = n >= PASS_SPEED_MIN_PASSES
        fast_pct = round(100.0 * fast / n, 1) if ok else None
        label = None
        if fast_pct is not None:
            label = ("éles passzjáték" if fast_pct >= 50.0
                     else "lágy labdajáratás" if fast_pct <= 20.0
                     else "vegyes")
        out[side] = {"passes": n,
                     "avg_ms": round(total / n, 1) if ok else None,
                     "fast": fast, "fast_pct": fast_pct, "label": label}
    return out
