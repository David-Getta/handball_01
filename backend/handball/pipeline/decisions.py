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
# A kocka-szintű gyorsítótár a LEGFORRÓBB úton hívódik (a
# birtoklás-mérés kockánként, egy összeállítás alatt milliószor): a
# függvényen belüli import ennyi hívásnál már mérhető költség.
from .primitive_cache import cached_frame, copy_events, memoize_primitive

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
    return cached_frame("ball_holder", frame, config,
                        lambda: _ball_holder(frame, config))


def _ball_holder(frame: Frame, config: TacticsConfig) -> Optional[PlayerPosition]:
    """A tényleges birtokos-keresés (lásd `ball_holder`)."""
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


# A passz-felismerés a TELJES felvételt végigjárja, és egy összeállítás
# alatt a passz-, gólpassz- és szervezés-rétegek tucatja kéri.
@memoize_primitive("detect_passes", copy=copy_events)
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
# A labdavesztő utolsó ismert helyét ennyi idővel az eladás előttről
# keressük — MÁSODPERCBEN (a "12 kocka" ritkítva 1,44 mp lett volna,
# és az eladás előtti másodperc pressz-helyzete már nem az eladásé).
PRESS_LOOKBACK_S = 0.48


def press_lookback_frames(match: Match) -> int:
    """A visszanézés kockában, a meccs saját képrátájából."""
    fps = match.meta.fps if match.meta.fps and match.meta.fps > 0 else 25.0
    return max(1, int(round(PRESS_LOOKBACK_S * fps)))


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
        for j in range(i0 - 1, max(-1, i0 - 1 - press_lookback_frames(match)), -1):
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
#
# Az érintés-küszöb MÁSODPERCBEN: a feldolgozás ritkít (a termék alapja
# minden 3. kocka), tehát 5 kocka a profiltól függően 0,2 és 0,6
# másodperc között bármit jelentene. Ez valódi időtartam: mennyi az,
# ami "csak érintés". Két tized másodperc alatt tényleg nem lehet
# birtokolni a labdát.
HOLD_MIN_S = 0.2
# Visszafelé kompatibilis kocka-alapérték (25 fps-en pontosan 0,2 mp).
HOLD_MIN_FRAMES = 5
HOLD_MIN_HOLDS = 5
HOLD_GAP_S = 0.8


def hold_time_players(match: Match,
                      config: Optional[TacticsConfig] = None) -> dict:
    """Labdatartás-idő: KI meddig tartja magánál a labdát.

    A passz-tempó (pass_tempo) és a támadás-ritmus csapatszinten mondja
    meg, pörög-e a játék — ez a névre szóló olvasata: minden labdás
    szakasz hosszát a birtokoshoz írjuk, és nézzük, kinél áll meg a
    labda. Az érintésnyi (HOLD_MIN_S alatti) birtoklás zaj, azt
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
    # Az érintés-küszöb a meccs SAJÁT képrátájából (lásd HOLD_MIN_S).
    hold_min = max(1, int(round(HOLD_MIN_S * fps)))
    jersey: dict[int, int] = {}
    tally: dict[str, dict[int, list]] = {"home": {}, "away": {}}
    run_id = run_team = None
    run_len = 0

    def _close():
        """A lezáruló labdás szakasz jóváírása a birtokosnál."""
        if run_id is None or run_team is None:
            return
        if run_len < hold_min:
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


# Labdavezetés-táv: az érintés-küszöb és a minta-minimum a
# labdatartáséval közös (HOLD_MIN_S, HOLD_MIN_HOLDS — ugyanaz a
# "mi számít birtoklásnak" kérdés); e feletti sebesség követés-ugrás,
# nem futás (méter/másodpercben); és ennyi méterrel a csapatátlag
# feletti átlagos labdás út tesz valakit labdahordóvá. Az utat
# CARRY_WINDOW_S hosszú szakaszok elmozdulásából összegezzük, nem
# kockánként: a kockánkénti összeg a detektálási remegést is útnak
# számolta — a szimulált meccsen sűrűn (25 fps) háromszor annyi
# métert adott, mint ritkítva ugyanaz a meccs.
CARRY_MAX_STEP_MS = 10.0
CARRY_LONG_GAP_M = 3.0
CARRY_WINDOW_S = 0.5


def ball_carry_players(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Labdavezetés-táv: KI mennyit MOZOG a labdával.

    A labdatartás-idő (hold_time_players) azt méri, meddig van valakinél
    a labda — ez azt, hogy közben mennyi utat tesz meg vele. A kettő
    nem ugyanaz: az egy helyben passzra váró beálló sokáig tartja, de
    nem viszi; a labdával kifelé-befelé húzogató átlövő keveset tart
    egyszerre, de sok métert cipeli. Minden labdás szakaszban a
    birtokos elmozdulását összegezzük (a követés-ugrásnyi, CARRY_MAX_
    STEP_MS feletti lépést kihagyva), és a szakasz métereit a
    birtokoshoz írjuk.

    Edzőileg: az ellenfél labdahordója a LESZÚRÁS és a halászás
    célpontja — aki sokat fut a labdával, az sokáig van elvehető
    helyzetben, és nála lassul le a támadás-szervezés. Saját oldalon a
    "vidd kevesebbet, add korábban" téma névre szólóan.

    Visszatérés csapatonként:
      {"holds", "meters", "avg_m", "players": [{"player_id", "jersey",
       "holds", "meters", "avg_m"}], "carrier": {..., "gap_m"}|None}
    — players az átlagos labdás út szerint csökkenően; avg_m és
    carrier None, ha kevés a minta (HOLD_MIN_HOLDS).
    """
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    hold_min = max(1, int(round(HOLD_MIN_S * fps)))
    jersey: dict[int, int] = {}
    tally: dict[str, dict[int, list]] = {"home": {}, "away": {}}
    run_id = run_team = None
    run_len = 0
    run_m = 0.0
    anchor = None   # (x, y, t): az aktuális ablak kezdete
    last = None     # (x, y, t): a szakasz utolsó kockája

    def _segment(a, b) -> float:
        """Egy ablak elmozdulása — a követés-ugrásnyi (CARRY_MAX_STEP_MS
        feletti) sebességű ablak nem futás, kimarad."""
        dt = (b[2] - a[2]) / fps
        if dt <= 0:
            return 0.0
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        return d if d / dt <= CARRY_MAX_STEP_MS else 0.0

    def _close():
        """A lezáruló labdás szakasz métereinek jóváírása (a nyitott
        ablak maradékával együtt)."""
        nonlocal run_m
        if run_id is None or run_team is None:
            return
        if anchor is not None and last is not None and last[2] > anchor[2]:
            run_m += _segment(anchor, last)
        if run_len < hold_min:
            return
        rec = tally[run_team].setdefault(run_id, [0, 0.0])
        rec[0] += 1
        rec[1] += run_m

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
            run_id, run_team, run_len, run_m = pid, side, 0, 0.0
            anchor = last = None
        if pid is not None and side is not None:
            run_len += 1
            now = (holder.x, holder.y, f.t)
            if anchor is None:
                anchor = now
            elif (f.t - anchor[2]) / fps >= CARRY_WINDOW_S:
                run_m += _segment(anchor, now)
                anchor = now
            last = now
    _close()

    out: dict = {}
    for s in ("home", "away"):
        players = []
        for pid, (holds, meters) in tally[s].items():
            players.append({"player_id": pid, "jersey": jersey.get(pid),
                            "holds": holds,
                            "meters": round(meters, 1),
                            "avg_m": round(meters / holds, 2)})
        players.sort(key=lambda p: -p["avg_m"])
        n_holds = sum(p["holds"] for p in players)
        n_m = round(sum(p["meters"] for p in players), 1)
        team_avg = (round(n_m / n_holds, 2) if n_holds else None)
        carrier = None
        if n_holds >= HOLD_MIN_HOLDS and team_avg is not None:
            cands = [{**p, "gap_m": round(p["avg_m"] - team_avg, 2)}
                     for p in players
                     if p["holds"] >= HOLD_MIN_HOLDS
                     and p["avg_m"] - team_avg >= CARRY_LONG_GAP_M]
            if cands:
                carrier = max(cands, key=lambda p: p["gap_m"])
        out[s] = {"holds": n_holds, "meters": n_m,
                  "avg_m": (team_avg if n_holds >= HOLD_MIN_HOLDS
                            else None),
                  "players": players, "carrier": carrier}
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


# Pressz-érzékeny játékosok: ennyi nyomott döntéstől ítélünk
# emberenként, és e feletti eladás-arány jelenti, hogy szorításban
# elveszíti a labdát.
PSP_MIN_PRESS = 5
PSP_TO_PCT = 30.0


def pressure_sensitive_players(match: Match,
                               config: Optional[TacticsConfig] = None
                               ) -> dict:
    """Pressz-érzékeny játékosok: KI VESZÍTI EL a labdát szorításban.

    A pressz-tűrés (pass_security_under_pressure) csapat-szinten
    mondja meg, mennyivel nő az eladás testközeli védő mellett — ez
    játékosonként bontja: emberenként számoljuk a NYOMOTT (a
    PRESS_TIGHT_M-en belül védővel meghozott) labdás döntéseket és
    azok közül az eladásokat.

    Edzőileg: a pressz-érzékeny emberre kell küldeni a kettőzést — az
    ő szorítása nem kockázat, hanem labdaszerzés; a saját oldalon
    pedig neki a nyomás alatti kiadás a gyakorlandó.

    Visszatérés csapatonként: {"players": [{"player_id", "jersey",
    "press_events", "press_to"}], "top"} — a lista nyomott eladás
    szerint csökkenő; a "top" az a játékos, akinek legalább
    PSP_MIN_PRESS nyomott döntése van, és az eladás-aránya eléri a
    PSP_TO_PCT-t.
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

    jersey: dict = {}
    tally: dict = {"home": {}, "away": {}}

    def _rec(side, pid):
        return tally[side].setdefault(pid, {"press_events": 0,
                                            "press_to": 0})

    for pe in detect_passes(match, config):
        if pe.decision_frame is None or pe.passer_pos is None:
            continue
        if not _tight(pe.decision_frame, pe.passer_pos, pe.team):
            continue
        if pe.passer_pos.jersey_number is not None:
            jersey.setdefault(pe.passer_id, pe.passer_pos.jersey_number)
        _rec(pe.team.value, pe.passer_id)["press_events"] += 1

    for e in detect_events(match, config):
        if e.type != EventType.TURNOVER or e.player_id is None:
            continue
        i0 = idx_of.get(e.t)
        if i0 is None:
            continue
        # A vesztes utolsó ismert pozíciója az esemény előtti kockákon.
        for j in range(i0 - 1, max(-1, i0 - 1 - press_lookback_frames(match)), -1):
            loser = next((p for p in frames[j].players
                          if p.track_id == e.player_id), None)
            if loser is None:
                continue
            if _tight(frames[j], loser, e.team):
                if loser.jersey_number is not None:
                    jersey.setdefault(loser.track_id,
                                      loser.jersey_number)
                rec = _rec(e.team.value, e.player_id)
                rec["press_events"] += 1
                rec["press_to"] += 1
            break

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "press_events": r["press_events"],
                 "press_to": r["press_to"]}
                for pid, r in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1]["press_to"])]
        top = None
        for row in rows:
            if row["press_events"] >= PSP_MIN_PRESS and (
                    100.0 * row["press_to"] / row["press_events"]
                    >= PSP_TO_PCT):
                top = row
                break
        out[side] = {"players": rows, "top": top}
    return out


# Lövésválasztás: ennyi mért lövés kell az ítélethez; ekkora
# xG-különbség számít "érdemben jobb helyzetnek" (0.10 nagyjából minden
# tizedik lövésnyi gólkülönbség); és e fölött/alatt mondunk ítéletet a
# jobb helyzetet eldobó lövések arányára.
SCQ_MIN_SHOTS = 6
SCQ_GAP_XG = 0.10
SCQ_HIGH_PCT = 45.0
SCQ_LOW_PCT = 15.0


def shot_choice_quality(match: Match,
                        config: Optional[TacticsConfig] = None) -> dict:
    """Lövésválasztás: LŐNEK-E, AMIKOR JOBB HELYZET VAN a pályán.

    A helyzetminőség (xg) azt mondja meg, MILYEN helyzetekből lőnek —
    ez azt, hogy a lövés pillanatában volt-e JOBB. Minden lövésnél
    kiszámoljuk az elengedő játékos helyzetértékét, és összevetjük a
    legjobb SZABAD csapattársáéval (szabad = a legközelebbi mezőny-védő
    FREE_DEF_RADIUS_M-nél távolabb). Ha a társé legalább SCQ_GAP_XG-vel
    nagyobb, a lövés "eldobott jobb helyzet".

    Edzőileg ez a támadó-játék fegyelme. A magas arány nem azt jelenti,
    hogy rosszul lőnek — hanem hogy NEM NÉZNEK FEL: a fal ellenük
    tudatosan hagyhatja a rossz szögű lövést, mert úgyis elveszik. Ellene
    a saját oldalon a labdás fejét kell felhozni (utolsó passz keresése
    kényszerrel), a másikon a védekezés kap tervet: aki eldobja a jobb
    helyzetet, arra RÁ LEHET engedni, a jobb helyzetben lévő társát
    viszont zárni kell — az a lövés amúgy sem jönne meg.

    Visszatérés csapatonként: {"shots" (mért lövés), "better_options"
    (eldobott jobb helyzet), "pct", "avg_gap_xg", "verdict"} — a
    pct/verdict None SCQ_MIN_SHOTS alatt; a verdict csak a magas
    (SCQ_HIGH_PCT feletti) vagy a kifejezetten fegyelmezett
    (SCQ_LOW_PCT alatti) esetben szólal meg.
    """
    from ..models.tracking import Team as _Team
    from .defense import FREE_DEF_RADIUS_M
    from .event_detection import EventType, detect_shots
    from .xg import xg_of_position

    config = config or TacticsConfig()
    by_t = {f.t: f for f in match.frames}

    out: dict = {side: {"shots": 0, "better_options": 0, "pct": None,
                        "avg_gap_xg": None, "verdict": None}
                 for side in ("home", "away")}
    gaps: dict = {"home": [], "away": []}

    for e in detect_shots(match, config):
        if e.type not in (EventType.SHOT, EventType.GOAL):
            continue
        if e.player_id is None:
            continue
        # A lövés-döntés az ELENGEDÉS pillanatában született — a lövőt,
        # a védőket és a jobb passz-opciókat is onnan mérjük (release_t;
        # az esemény kockáján mindenki elmozdult már).
        f = by_t.get((e.detail or {}).get("release_t")) or by_t.get(e.t)
        if f is None:
            continue
        shooter = next((p for p in f.players
                        if p.track_id == e.player_id), None)
        if shooter is None:
            continue
        goal_x = config.attacks_toward_x(e.team)
        defender_team = (_Team.AWAY if e.team == _Team.HOME
                         else _Team.HOME)
        defenders = [p for p in f.players
                     if p.team == defender_team and p.role != "kapus"]
        if not defenders:
            continue
        own_xg = xg_of_position(shooter.x, shooter.y, goal_x)
        best_alt = None
        for p in f.players:
            if p.team != e.team or p.track_id == shooter.track_id:
                continue
            if p.role == "kapus":
                continue
            near = min(math.hypot(d.x - p.x, d.y - p.y) for d in defenders)
            if near <= FREE_DEF_RADIUS_M:
                continue          # a társ sincs szabadon — nem opció
            alt = xg_of_position(p.x, p.y, goal_x)
            if best_alt is None or alt > best_alt:
                best_alt = alt

        rec = out[e.team.value]
        rec["shots"] += 1
        if best_alt is not None and best_alt - own_xg >= SCQ_GAP_XG:
            rec["better_options"] += 1
            gaps[e.team.value].append(best_alt - own_xg)

    for side in ("home", "away"):
        rec = out[side]
        if rec["shots"] < SCQ_MIN_SHOTS:
            continue
        pct = 100.0 * rec["better_options"] / rec["shots"]
        rec["pct"] = round(pct, 1)
        if gaps[side]:
            rec["avg_gap_xg"] = round(sum(gaps[side]) / len(gaps[side]), 3)
        if pct >= SCQ_HIGH_PCT:
            rec["verdict"] = (
                f"a lövéseik {pct:.0f}%-ánál volt jobb SZABAD helyzet a "
                "pályán — nem néznek fel: rájuk lehet engedni a rossz "
                "szögű lövést, a szabad társukat kell zárni")
        elif pct <= SCQ_LOW_PCT:
            rec["verdict"] = (
                f"fegyelmezett lövésválasztás (csak {pct:.0f}%-nál volt "
                "jobb szabad helyzet) — ellenük a helyzet-teremtést "
                "kell zárni, a lövés-pillanatban már késő")
    return out


# Döntés szorításban: a döntés pillanatában legfeljebb PRESS_TIGHT_M-re
# álló mezőny-védő a "szorítás", PDQ_FREE_M-nél messzebbi a "szabad" (a
# kettő közti sáv kimarad, hogy a két minta tisztán elváljon). Ennyi
# döntés kell MINDKÉT mintához; ekkora értékkülönbségen belül a választás
# "a legjobb" (az értékmodell zaja ennyi); ekkora százalékpontos esés
# számít érdeminek, ennél kisebb a "tartják a szintet" sáv, és e fölött
# a szorított jó-arány "jól döntenek". Játékos-szinten ennyi szorított
# döntés kell a névhez.
PDQ_FREE_M = 3.5
PDQ_MIN = 10
PDQ_TOL = 0.05
PDQ_DROP_PP = 15.0
PDQ_STEADY_PP = 5.0
PDQ_GOOD_PCT = 50.0
PDQ_PLAYER_MIN = 5


def pressure_decision_quality(match: Match,
                              config: Optional[TacticsConfig] = None
                              ) -> dict:
    """Döntés szorításban: A LEGJOBB OPCIÓT VÁLASZTJÁK-E, ha rájuk lépnek.

    A pressz-tűrés (pass_security) azt méri, mennyivel több az eladás
    testközeli védő mellett — ez azt, hogy a labda MEGTARTÁSA mellett is
    romlik-e a döntés. Minden labdás döntésnél (passz: a döntés kockáján;
    lövés: az elengedés kockáján) kiértékeljük az opciókat
    (evaluate_options: lövés + passz minden társhoz), és megnézzük, hogy
    a választott opció a legjobb PDQ_TOL-os közelében volt-e. A
    döntéseket két mintára bontjuk: SZORÍTOTT (a legközelebbi
    mezőny-védő legfeljebb PRESS_TIGHT_M-re) és SZABAD (PDQ_FREE_M-nél
    messzebb).

    Edzőileg: ha szorításban a jó döntések aránya érdemben esik, a
    labdásra lépő védekezés ellenük nem kockázat, hanem rossz döntést
    kényszerít ki — a saját oldalon pedig a nyomás alatti felnézés a
    gyakorlandó. Ha szorításban is tartják a szintet, a kilépés ellenük
    csak rést nyit a fal mögött.

    Visszatérés csapatonként: {"pressed", "pressed_best", "free",
    "free_best", "pressed_pct", "free_pct", "drop_pp", "players", "top",
    "verdict"} — a darabszámok mindig; a %-ok, a drop és a verdict None,
    ha bármelyik minta PDQ_MIN alatt van. "players": játékosonként a
    szorított döntések és közülük a legjobb-opciósak ({"player_id",
    "jersey", "press", "press_best"}, a szorított döntések szerint
    csökkenő); "top" az első játékos, akinek legalább PDQ_PLAYER_MIN
    szorított döntése van, és a jó-aránya legalább PDQ_DROP_PP-vel a
    csapat szabad aránya alatt van (None, ha nincs ilyen, vagy a csapat
    mintája kevés).
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    by_t = {f.t: f for f in match.frames}
    tally = {s: {"pressed": 0, "pressed_best": 0, "free": 0,
                 "free_best": 0} for s in ("home", "away")}
    per_player: dict = {"home": {}, "away": {}}
    jersey: dict = {}

    def _record(frame: Frame, pos: PlayerPosition, team: Team,
                chosen: Optional[float], options: list[Option]) -> None:
        best = best_option(options)
        if best is None or chosen is None:
            return
        dists = [math.hypot(p.x - pos.x, p.y - pos.y)
                 for p in frame.players
                 if p.team != team and p.role != "kapus"]
        if not dists:
            return
        near = min(dists)
        good = int(chosen >= best.value - PDQ_TOL)
        rec = tally[team.value]
        if near <= PRESS_TIGHT_M:
            rec["pressed"] += 1
            rec["pressed_best"] += good
            row = per_player[team.value].setdefault(
                pos.track_id, {"press": 0, "press_best": 0})
            row["press"] += 1
            row["press_best"] += good
            if pos.jersey_number is not None:
                jersey.setdefault(pos.track_id, pos.jersey_number)
        elif near > PDQ_FREE_M:
            rec["free"] += 1
            rec["free_best"] += good

    for pe in detect_passes(match, config):
        if pe.decision_frame is None or pe.passer_pos is None:
            continue
        opts = evaluate_options(pe.decision_frame, pe.passer_pos, config)
        chosen = next((o.value for o in opts
                       if o.kind == "pass" and o.target_id == pe.receiver_id),
                      None)
        _record(pe.decision_frame, pe.passer_pos, pe.team, chosen, opts)

    for e in detect_shots(match, config):
        if e.type not in (EventType.SHOT, EventType.GOAL) \
                or e.player_id is None:
            continue
        # A lövés-döntés az ELENGEDÉS pillanatában született (release_t).
        f = by_t.get((e.detail or {}).get("release_t")) or by_t.get(e.t)
        if f is None:
            continue
        shooter = next((p for p in f.players
                        if p.track_id == e.player_id), None)
        if shooter is None:
            continue
        opts = evaluate_options(f, shooter, config)
        chosen = next((o.value for o in opts if o.kind == "shoot"), None)
        _record(f, shooter, e.team, chosen, opts)

    out: dict = {}
    for side in ("home", "away"):
        t = tally[side]
        rows = [{"player_id": pid, "jersey": jersey.get(pid), **r}
                for pid, r in sorted(per_player[side].items(),
                                     key=lambda kv: (-kv[1]["press"],
                                                     kv[0]))]
        rec = {**t, "pressed_pct": None, "free_pct": None,
               "drop_pp": None, "players": rows, "top": None,
               "verdict": None}
        out[side] = rec
        if t["pressed"] < PDQ_MIN or t["free"] < PDQ_MIN:
            continue
        pp = 100.0 * t["pressed_best"] / t["pressed"]
        fp = 100.0 * t["free_best"] / t["free"]
        rec["pressed_pct"] = round(pp, 1)
        rec["free_pct"] = round(fp, 1)
        rec["drop_pp"] = round(fp - pp, 1)
        for row in rows:
            if row["press"] >= PDQ_PLAYER_MIN and (
                    fp - 100.0 * row["press_best"] / row["press"]
                    >= PDQ_DROP_PP):
                rec["top"] = row
                break
        if fp - pp >= PDQ_DROP_PP:
            rec["verdict"] = (
                f"szorításban rosszabbul döntenek: szabadon a döntéseik "
                f"{fp:.0f}%-a, szorítva csak {pp:.0f}%-a a legjobb opció "
                "— rájuk kell lépni, a labdásra lépő védekezés náluk "
                "rossz döntést kényszerít ki")
        elif fp - pp <= PDQ_STEADY_PP and pp >= PDQ_GOOD_PCT:
            rec["verdict"] = (
                f"szorításban is jól döntenek (szorítva a döntéseik "
                f"{pp:.0f}%-a a legjobb opció, szabadon {fp:.0f}%) — a "
                "kilépés ellenük csak rést nyit a fal mögött, zárt falban "
                "kell védekezni")
    return out


# Helyzet-döntés: a 6 m-es vonaltól ennyin belül álló társ "6 m-es"
# (beálló), a kapu közepétől oldalra ennyire álló fogadó szélső; ennyivel
# távolabb a kaputól a visszajátszás; a 6 m-es vonaltól ennyin belül
# lőtávolság (≈ 10 m). A fedezett lövő/fogadó értéke legfeljebb ennyivel
# csökken (testközeli védőnél). Helyzetenként ennyi döntés kell; a
# leggyakoribb választás e fölött "szokás", a legjobb-opció aránya e
# alatt "rossz szokás"; játékos-szinten ennyi döntés kell a névhez.
SIT_LINE_M = 1.5
SIT_WING_M = 6.0
SIT_BACK_M = 1.5
SIT_RANGE_M = 4.0
SIT_COVER_LOSS = 0.6
SIT_MIN = 8
SIT_HABIT_PCT = 50.0
SIT_MATCH_LOW_PCT = 40.0
SIT_PLAYER_MIN = 5

# A helyzetek (a besorolás sorrendjében) és a választások neve.
SIT_SITUATIONS = ("kilépnek rá", "szabad a 6 m-es társ", "szabad lőhely")
SIT_ACTIONS = ("lövés", "passz a 6 m-re", "passz a szélre",
               "visszajátszás", "átadás")
SIT_PHRASE = {"kilépnek rá": "kilépnek rájuk",
               "szabad a 6 m-es társ": "szabad a 6 m-es társuk",
               "szabad lőhely": "szabad lőhelyen kapják a labdát"}
# Ugyanez EGY játékosról (a felderítés játékos-szokásaihoz).
SIT_PHRASE_ONE = {"kilépnek rá": "ha kilépnek rá",
                  "szabad a 6 m-es társ": "ha szabad a 6 m-es társa",
                  "szabad lőhely": "szabad lőhelyen"}
SIT_ADVICE = {
    "kilépnek rá": "lépjetek ki rájuk korán: a kilépés a gyengébb "
                   "megoldásba kényszeríti őket",
    "szabad a 6 m-es társ": "a szabad 6 m-es társukat ritkán veszik "
                            "észre, a beállóőr bátran kisegíthet a "
                            "labdásra",
    "szabad lőhely": "a szabad lőhelyet nem jól használják, a fal "
                     "ellenük hátrébb állhat és a 6 m-t zárhatja",
}


def sit_article(word: str) -> str:
    """A határozott névelő (a/az) egy választás vagy helyzet elé."""
    return "az" if word[:1].lower() in "aáeéiíoóöőuúüű" else "a"


def _from_area_m(x: float, y: float, goal_x: float) -> float:
    """Távolság a kapuelőtér (6 m-es) vonalától méterben (a vonalon 0)."""
    dx = abs(x - goal_x)
    if GOAL_Y - 1.5 <= y <= GOAL_Y + 1.5:
        return max(0.0, dx - 6.0)
    py = GOAL_Y - 1.5 if y < GOAL_Y - 1.5 else GOAL_Y + 1.5
    return max(0.0, math.hypot(dx, y - py) - 6.0)


def situational_decisions(match: Match,
                          config: Optional[TacticsConfig] = None) -> dict:
    """Helyzet-döntés: MIT CSINÁLNAK az egyes helyzetekben, és mi lett
    volna a legjobb.

    A döntés-elemzés eddig összesítve mondta meg, mennyire optimális egy
    passz — ez a játékos- és csapat-modell helyzetenkénti képe. Minden
    labdás döntést (passz a döntés kockáján, lövés az elengedésén)
    besorolunk: KILÉPNEK RÁ (mezőny-védő legfeljebb PRESS_TIGHT_M-re),
    SZABAD A 6 M-ES TÁRS (egy társ a 6 m-es vonalnál, a legközelebbi
    védő FREE_DEF_RADIUS_M-nél messzebb), vagy SZABAD LŐHELY (a labdás
    PDQ_FREE_M-en túl szabad, lőtávolságon belül). A választás: lövés,
    passz a 6 m-re, passz a szélre, visszajátszás vagy átadás. A legjobb
    opciót az xG-szerű helyzetérték adja (a fogadóé a passz
    sikerességével), a fedezett lövő és a fogott fogadó
    SIT_COVER_LOSS-szal leértékelve.

    Edzőileg ez a "hogyan dönt" modell: ha egy helyzetben a szokásuk
    (a választásaik SIT_HABIT_PCT-nél nagyobb része) nem a legjobb
    megoldás, ott kell őket abba a helyzetbe kényszeríteni — kilépni
    rájuk, kisegíteni a beállóról, vagy hátrébb állni.

    Visszatérés csapatonként: {"situations": {helyzet: {"decisions",
    "actions", "best", "match"}}, "players", "situation", "habit",
    "best_action", "top", "verdict"} — a darabszámok mindig (minden
    helyzet szerepel); a "situation"/"habit"/"best_action"/"verdict" a
    legrosszabb egyezésű, legalább SIT_MIN döntéses helyzetről szól,
    ahol a szokás más, mint a leggyakoribb legjobb opció, és a
    legjobb-opció aránya legfeljebb SIT_MATCH_LOW_PCT (különben None).
    "players": játékosonként helyzet → {"decisions", "actions", "best",
    "match"};
    "top" az a játékos, akinél ugyanabban a helyzetben ugyanez a szokás
    (legalább SIT_PLAYER_MIN döntés), a legtöbb döntéssel.
    """
    from ..models.tracking import Team as _Team
    from .defense import FREE_DEF_RADIUS_M
    from .event_detection import EventType, detect_shots
    from .xg import xg_of_position

    config = config or TacticsConfig()
    by_t = {f.t: f for f in match.frames}

    def _empty():
        return {s: {"decisions": 0, "actions": {}, "best": {}, "match": 0}
                for s in SIT_SITUATIONS}

    tally = {"home": _empty(), "away": _empty()}
    per_player: dict = {"home": {}, "away": {}}
    jersey: dict = {}

    def _action(holder, target, goal_x) -> str:
        if target is None:
            return "lövés"
        if abs(target.y - GOAL_Y) >= SIT_WING_M:
            return "passz a szélre"
        if _from_area_m(target.x, target.y, goal_x) <= SIT_LINE_M:
            return "passz a 6 m-re"
        if abs(target.x - goal_x) - abs(holder.x - goal_x) >= SIT_BACK_M:
            return "visszajátszás"
        return "átadás"

    def _record(frame: Frame, holder: PlayerPosition, team,
                target_id: Optional[int]) -> None:
        goal_x = config.attacks_toward_x(team)
        opp = _Team.AWAY if team == _Team.HOME else _Team.HOME
        defs = [p for p in frame.players
                if p.team == opp and p.role != "kapus"]
        if not defs:
            return
        mates = [p for p in frame.players
                 if p.team == team and p.track_id != holder.track_id
                 and p.role != "kapus"]

        def near(p):
            return min(math.hypot(d.x - p.x, d.y - p.y) for d in defs)

        def cover(p):
            return 1.0 - SIT_COVER_LOSS * max(
                0.0, 1.0 - near(p) / FREE_DEF_RADIUS_M)

        target = None
        if target_id is not None:
            target = next((p for p in mates if p.track_id == target_id),
                          None)
            if target is None:
                return
        hn = near(holder)
        if hn <= PRESS_TIGHT_M:
            sit = "kilépnek rá"
        elif any(_from_area_m(p.x, p.y, goal_x) <= SIT_LINE_M
                 and abs(p.y - GOAL_Y) < SIT_WING_M
                 and near(p) > FREE_DEF_RADIUS_M for p in mates):
            sit = "szabad a 6 m-es társ"
        elif hn > PDQ_FREE_M and \
                _from_area_m(holder.x, holder.y, goal_x) <= SIT_RANGE_M:
            sit = "szabad lőhely"
        else:
            return
        options = [(xg_of_position(holder.x, holder.y, goal_x)
                    * cover(holder), None)]
        for p in mates:
            options.append((xg_of_position(p.x, p.y, goal_x)
                            * pass_completion(holder, p, frame)
                            * cover(p), p))
        best_v, best_p = max(options, key=lambda o: o[0])
        chosen_v = next(v for v, p in options if p is target)
        act = _action(holder, target, goal_x)
        best_act = _action(holder, best_p, goal_x)
        good = int(chosen_v >= best_v - PDQ_TOL)
        rec = tally[team.value][sit]
        rec["decisions"] += 1
        rec["actions"][act] = rec["actions"].get(act, 0) + 1
        rec["best"][best_act] = rec["best"].get(best_act, 0) + 1
        rec["match"] += good
        prow = per_player[team.value].setdefault(holder.track_id, {})
        ps = prow.setdefault(sit, {"decisions": 0, "actions": {},
                                   "best": {}, "match": 0})
        ps["decisions"] += 1
        ps["actions"][act] = ps["actions"].get(act, 0) + 1
        ps["best"][best_act] = ps["best"].get(best_act, 0) + 1
        ps["match"] += good
        if holder.jersey_number is not None:
            jersey.setdefault(holder.track_id, holder.jersey_number)

    for pe in detect_passes(match, config):
        if pe.decision_frame is None or pe.passer_pos is None:
            continue
        _record(pe.decision_frame, pe.passer_pos, pe.team, pe.receiver_id)

    for e in detect_shots(match, config):
        if e.type not in (EventType.SHOT, EventType.GOAL) \
                or e.player_id is None:
            continue
        f = by_t.get((e.detail or {}).get("release_t")) or by_t.get(e.t)
        if f is None:
            continue
        shooter = next((p for p in f.players
                        if p.track_id == e.player_id), None)
        if shooter is not None:
            _record(f, shooter, e.team, None)

    def _top_of(counts: dict) -> Optional[str]:
        # Holtversenyben a választások rögzített sorrendje dönt.
        if not counts:
            return None
        return max(SIT_ACTIONS, key=lambda a: (counts.get(a, 0),
                                               -SIT_ACTIONS.index(a)))

    out: dict = {}
    for side in ("home", "away"):
        sits = tally[side]
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "situations": s}
                for pid, s in sorted(per_player[side].items())]
        rec = {"situations": sits, "players": rows, "situation": None,
               "habit": None, "best_action": None, "top": None,
               "verdict": None}
        out[side] = rec
        worst = None
        for sit in SIT_SITUATIONS:
            s = sits[sit]
            if s["decisions"] < SIT_MIN:
                continue
            habit, best_act = _top_of(s["actions"]), _top_of(s["best"])
            share = 100.0 * s["actions"][habit] / s["decisions"]
            match_pct = 100.0 * s["match"] / s["decisions"]
            if habit == best_act or share < SIT_HABIT_PCT \
                    or match_pct > SIT_MATCH_LOW_PCT:
                continue
            if worst is None or match_pct < worst[1]:
                worst = (sit, match_pct, habit, best_act, share)
        if worst is None:
            continue
        sit, match_pct, habit, best_act, share = worst
        rec.update(situation=sit, habit=habit, best_action=best_act)
        cands = []
        for row in rows:
            ps = row["situations"].get(sit)
            if not ps or ps["decisions"] < SIT_PLAYER_MIN:
                continue
            if 100.0 * ps["actions"].get(habit, 0) / ps["decisions"] \
                    >= SIT_HABIT_PCT and 100.0 * ps["match"] \
                    / ps["decisions"] <= SIT_MATCH_LOW_PCT:
                cands.append((-ps["decisions"], row["player_id"], row))
        if cands:
            rec["top"] = min(cands, key=lambda c: c[:2])[2]
        rec["verdict"] = (
            f"ha {SIT_PHRASE[sit]}, a döntéseik {share:.0f}%-a {habit}, "
            f"pedig a modell szerint {sit_article(best_act)} {best_act} "
            f"érne többet (csak {match_pct:.0f}%-ban választják a "
            f"legjobbat) — {SIT_ADVICE[sit]}")
    return out


# Labdatartó-poszt: ennyi poszthoz kötött labdatartás-másodperc kell
# az ítélethez, és ekkora részarány fölött mondjuk ki, hogy a labda
# egy posztnál áll meg.
HTR_MIN_S = 60.0
HTR_SHARE_PCT = 60.0


def hold_time_roles(match: Match,
                    config: Optional[TacticsConfig] = None) -> dict:
    """Labdatartó-poszt: MELYIK POSZTJUKNÁL áll meg a labda.

    A labdatartás-idő rétege (hold_time_players) az embert nevezi
    meg — ez a posztot: minden mért labdás szakasz idejét a birtokos
    posztjához írja. Így a minta akkor is látszik, ha a nevek
    meccsről meccsre cserélődnek.

    Edzőileg ez a kettőzés időzítése: amelyik posztjuknál rendre
    megáll a labda, ott van idő odaérni a kettőzéssel, és ott lassul
    a támadásuk — a nyomást oda kell szervezni. Saját csapatra: ha a
    labda egy posztunknál ragad, a gyorsabb továbbítás az edzés-téma.

    Visszatérés csapatonként: {"seconds" (poszthoz kötött mért
    tartás, mp), "roles": {poszt: mp}, "main_role", "share_pct",
    "verdict"} — az ítélet None, ha nincs meg a HTR_MIN_S, vagy
    egyik poszt sem éri el a HTR_SHARE_PCT-t.
    """
    from .roles import estimate_positions

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    ht = hold_time_players(match, config)

    out: dict = {side: {"seconds": 0.0, "roles": {},
                        "main_role": None, "share_pct": None,
                        "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in ht[side]["players"]:
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = round(
                rec["roles"].get(poszt, 0.0) + row["seconds"], 1)
            rec["seconds"] = round(rec["seconds"] + row["seconds"], 1)
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["seconds"] >= HTR_MIN_S:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["seconds"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= HTR_SHARE_PCT:
                rec["verdict"] = (
                    f"a labda a(z) {poszt} posztjuknál áll meg: a "
                    f"mért labdatartásuk {share:.0f}%-a nála telik "
                    f"({rec['seconds']:.0f} mp-ből) — a kettőzést rá "
                    "kell időzíteni, nála lassul a támadásuk")
    return out


# Pressz-poszt: ennyi poszthoz kötött nyomott eladás kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy szorításban
# egy posztjuk ejti a labdát.
PSR_MIN_TO = 3
PSR_SHARE_PCT = 60.0


def press_sensitive_roles(match: Match,
                          config: Optional[TacticsConfig] = None
                          ) -> dict:
    """Pressz-poszt: MELYIK POSZTJUK ejti a labdát szorításban.

    A pressz-érzékeny játékosok rétege (pressure_sensitive_players)
    az embert nevezi meg — ez a posztot: a nyomott (testközeli védő
    melletti) eladásokat a labdavesztő posztjához írja. Így a minta
    akkor is látszik, ha a nevek meccsről meccsre cserélődnek.

    Edzőileg ez a kettőzés iránya: amelyik posztjuk szorításban
    rendre eladja a labdát, oda a kettőzés nem kockázat, hanem
    labdaszerzés. Saját csapatra: annak a posztnak a nyomás alatti
    kiadás a gyakorlandó.

    Visszatérés csapatonként: {"press_to" (poszthoz kötött nyomott
    eladás), "roles": {poszt: darab}, "main_role", "share_pct",
    "verdict"} — az ítélet None, ha nincs meg a PSR_MIN_TO, vagy
    egyik poszt sem éri el a PSR_SHARE_PCT-t.
    """
    from .roles import estimate_positions

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    psp = pressure_sensitive_players(match, config)

    out: dict = {side: {"press_to": 0, "roles": {},
                        "main_role": None, "share_pct": None,
                        "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in psp[side]["players"]:
            if not row["press_to"]:
                continue
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["press_to"])
            rec["press_to"] += row["press_to"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["press_to"] >= PSR_MIN_TO:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["press_to"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= PSR_SHARE_PCT:
                rec["verdict"] = (
                    f"szorításban a(z) {poszt} posztjuk ejti a "
                    f"labdát ({share:.0f}%, {rec['press_to']} nyomott"
                    " eladásból) — a kettőzést rá kell küldeni: az ő "
                    "szorítása nem kockázat, hanem labdaszerzés")
    return out


# Lágypassz-poszt: e sebesség alatt lágy (beleérhető) egy passz;
# ennyi poszthoz kötött lágy passz kell az ítélethez, és ekkora
# részarány fölött mondjuk ki, hogy a lágy labdák egy posztról
# jönnek.
SPS_SOFT_MS = 8.0
SPS_MIN_SOFT = 5
SPS_SHARE_PCT = 60.0


# Lágy passzolók: ennyi lágy passz kell a névhez, és ekkora
# részarány fölött mondjuk ki, hogy a lágy labdák egy emberhez
# kötődnek.
SPP_MIN_SOFT = 4
SPP_SHARE_PCT = 50.0


def soft_passers(match: Match,
                 config: Optional[TacticsConfig] = None) -> dict:
    """Lágy passzolók: KINEK a labdáiba lehet belenyúlni.

    A lágypassz-poszt (soft_pass_roles) a POSZTOT nevezi meg — ez az
    EMBERT: az SPS_SOFT_MS alatti sebességű (lágy, ívelt) passzokat a
    passzoló nevéhez írja.

    Edzőileg ez a beleérő védekezés címzettje: akinek lágyak a
    passzai, annak a labdáiba bele lehet nyúlni — kilépés és
    passzsáv-támadás az ő sávjában azonnal termel; a letámadásnál az
    ő átadásait kell megcélozni, nem a labdást szorítani. Saját
    csapatra: neki a passz-élesség (csuklós, feszes átadás) az
    edzés-témája.

    Visszatérés csapatonként: {"soft", "players": [{"player_id",
    "jersey", "soft"}], "top"} — a "top" az első játékos, ha
    legalább SPP_MIN_SOFT lágy passza van, és ez a csapat lágy
    passzainak legalább SPP_SHARE_PCT-a, különben None.
    """
    import math

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    by_t = {f.t: f for f in match.frames}

    jersey: dict = {}
    for f in match.frames:
        for q in f.players:
            if q.jersey_number is not None:
                jersey.setdefault(q.track_id, q.jersey_number)

    tally: dict = {"home": {}, "away": {}}
    for p in detect_passes(match, config):
        if p.decision_frame is None:
            continue
        dt = p.t - p.decision_frame.t
        if dt < 2:
            continue
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
        if speed > PASS_SPEED_MAX_MS or speed >= SPS_SOFT_MS:
            continue
        side = p.team.value
        if side not in tally:
            continue
        tally[side][p.passer_id] = tally[side].get(p.passer_id, 0) + 1

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "soft": n}
                for pid, n in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1])]
        total = sum(r["soft"] for r in rows)
        top = None
        if rows and rows[0]["soft"] >= SPP_MIN_SOFT:
            share = 100.0 * rows[0]["soft"] / max(1, total)
            if share >= SPP_SHARE_PCT:
                top = rows[0]
        out[side] = {"soft": total, "players": rows, "top": top}
    return out


def soft_pass_roles(match: Match,
                    config: Optional[TacticsConfig] = None) -> dict:
    """Lágypassz-poszt: MELYIK POSZTJUK passzol lágyan.

    A passz-sebesség rétege (pass_speed) csapat-szinten mondja meg,
    éles-e a labdajáratás — ez posztonként: az SPS_SOFT_MS alatti
    sebességű (lágy, ívelt) passzokat a passzoló posztjához írja. A
    mérhetetlen (egy kockán belüli) váltást és a PASS_SPEED_MAX_MS
    feletti értékeket (követés-ugrás) itt is kihagyjuk.

    Edzőileg ez a beleérő védekezés iránya: amelyik posztjuk lágyan
    passzol, annak a labdáiba bele lehet nyúlni — kilépés és
    passzsáv-támadás az ő sávjában azonnal termel. Saját csapatra:
    annak a posztnak a passz-élesség (csuklós, feszes átadás) az
    edzés-témája.

    Visszatérés csapatonként: {"soft" (poszthoz kötött lágy passz),
    "roles": {poszt: darab}, "main_role", "share_pct", "verdict"} —
    az ítélet None, ha nincs meg az SPS_MIN_SOFT, vagy egyik poszt
    sem éri el az SPS_SHARE_PCT-t.
    """
    import math

    from .roles import estimate_positions

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    by_t = {f.t: f for f in match.frames}
    roles = estimate_positions(match, config)

    out: dict = {side: {"soft": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for p in detect_passes(match, config):
        if p.decision_frame is None:
            continue
        dt = p.t - p.decision_frame.t
        if dt < 2:
            continue
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
        if speed > PASS_SPEED_MAX_MS or speed >= SPS_SOFT_MS:
            continue
        side = p.team.value
        rec_role = roles[side].get(p.passer_id)
        if rec_role is None:
            continue
        poszt = rec_role["poszt"]
        rec = out[side]
        rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1
        rec["soft"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["soft"] >= SPS_MIN_SOFT:
            poszt = max(rec["roles"], key=lambda p2: rec["roles"][p2])
            share = 100.0 * rec["roles"][poszt] / rec["soft"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= SPS_SHARE_PCT:
                rec["verdict"] = (
                    f"a lágy passzaik {share:.0f}%-a a(z) {poszt} "
                    f"posztról jön ({rec['soft']} lágy passzból) — "
                    "az ő labdáiba bele lehet nyúlni: kilépés és "
                    "passzsáv-támadás az ő sávjában azonnal termel")
    return out


# Térnyerő-poszt: ennyi poszthoz kötött, labdával megtett előre-métert
# kell mérni az ítélethez, és ekkora részarány fölött mondjuk ki,
# hogy a térnyerésük egy poszt lábán van. Egy birtoklási futam
# térnyerése a futam ELEJE és VÉGE közti előre-elmozdulás (nettó): a
# kockánkénti pozitív lépések összege a detektálási remegést is
# térnyerésnek számolta — sűrű felvételen háromszoros métert adott,
# mint ritkítva ugyanaz a meccs. A követés-ugrást lépésenkénti
# méter-korlát szűri: egy valódi lépés ritkítva sem több 1–2 m-nél,
# az ugrás több méter (a m/s-korlát a sűrű felvétel remegését is
# kiszűrte volna).
TNR_MIN_M = 50.0
TNR_SHARE_PCT = 60.0
TNR_MAX_STEP_M = 3.0


def ball_carrier_roles(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Térnyerő-poszt: MELYIK POSZTJUK viszi előre a labdát.

    A labdatartó-poszt azt méri, kinél ÁLL a labda — ez azt, kinél
    HALAD: a labdás játékos egymást követő kockái közt a támadott
    kapu felé megtett métereket a birtokos posztjához összegzi. Így
    látszik, kinek a lábán van a térnyerésük.

    Edzőileg ez a lendület-fék terve: amelyik posztjuk labdával
    rendre teret nyer, azt nem a hatosnál kell fogadni, hanem a
    felezőtől hátrálva — lendületbe engedni tilos, mert onnan már
    csak szabálytalansággal állítható meg. Saját csapatra: a
    felhozatal-teher eloszlása a rotáció-tervezés bemenete.

    Visszatérés csapatonként: {"meters" (poszthoz kötött előre-
    méter), "roles": {poszt: méter}, "main_role", "share_pct",
    "verdict"} — az ítélet None, ha nincs meg a TNR_MIN_M, vagy
    egyik poszt sem éri el a TNR_SHARE_PCT-t.
    """
    import math

    from .roles import estimate_positions

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    roles = estimate_positions(match, config)

    out: dict = {side: {"meters": 0.0, "roles": {},
                        "main_role": None, "share_pct": None,
                        "verdict": None}
                 for side in ("home", "away")}
    # Futam: ugyanaz a birtokos egymást követő kockákon; a térnyerése a
    # futam nettó előre-elmozdulása (ugrás-szűrt lépésekből).
    run = None   # [track_id, side, poszt, prev_x, prev_t, ahead, dx_sum]

    def _close():
        nonlocal run
        if run is not None and run[6] > 0.0 and run[2] is not None:
            rec = out[run[1]]
            rec["roles"][run[2]] = round(
                rec["roles"].get(run[2], 0.0) + run[6], 2)
            rec["meters"] = round(rec["meters"] + run[6], 2)
        run = None

    for f in match.frames:
        h = ball_holder(f, config)
        if h is None or h.team is None or h.role == "kapus":
            _close()
            continue
        side = h.team.value
        goal_x = config.attacks_toward_x(h.team)
        ahead = 1.0 if goal_x > COURT_LENGTH_M / 2.0 else -1.0
        if run is not None and run[0] == h.track_id and run[1] == side:
            dx = (h.x - run[3]) * ahead
            if abs(dx) <= TNR_MAX_STEP_M:
                run[6] += dx
            run[3], run[4] = h.x, f.t
        else:
            _close()
            rec_role = roles[side].get(h.track_id)
            run = [h.track_id, side,
                   rec_role["poszt"] if rec_role is not None else None,
                   h.x, f.t, ahead, 0.0]
    _close()

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["meters"] >= TNR_MIN_M:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["meters"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= TNR_SHARE_PCT:
                rec["verdict"] = (
                    f"a térnyerésük a(z) {poszt} poszt lábán van "
                    f"({share:.0f}%-a a labdával megtett "
                    f"{rec['meters']:.0f} előre-méternek) — őt a "
                    "felezőtől hátrálva kell fogadni: lendületbe "
                    "engedni tilos")
    return out


# Fáradt-eladó poszt: legalább ennyi 2. félidei eladás kell, és
# ennyiszerese az első félideinek, hogy a posztot fáradt-eladónak
# mondjuk ki.
FTO_MIN_SH = 3
FTO_FACTOR = 2.0


def tired_turnover_roles(match: Match,
                         config: Optional[TacticsConfig] = None
                         ) -> dict:
    """Fáradt-eladó poszt: MELYIK POSZTJUK labdái vesznek el fáradtan.

    Az eladás-rétegek a teljes meccset nézik — ez a fáradást: a
    labdaeladásokat félidőnként a vesztes posztjához írja, és
    megkeresi, melyik posztjuk eladásai ugranak meg a második
    félidőre. Így látszik, kinél nyílik ki fáradtan a kéz.

    Edzőileg ez a második félidei pressz-terv: akinek az eladásai
    fáradtan megugranak, azt a szünet után kell nyomás alá tenni — a
    friss védő rajta olcsó labdákat szerez. Saját csapatra: a poszt
    terhelés-menedzsmentje és fáradt labdabiztonság-edzése a téma.

    Visszatérés csapatonként: {"fh_roles": {poszt: darab},
    "sh_roles": {poszt: darab}, "main_role", "fh", "sh", "verdict"}
    — az ítélet None, ha nincs felismert szünet, vagy egyik poszt
    sem éri el az FTO_MIN_SH-t az FTO_FACTOR-os ugrással.
    """
    from .event_detection import EventType, detect_events
    from .halftime import detect_halftime
    from .roles import estimate_positions

    config = config or TacticsConfig()
    out: dict = {side: {"fh_roles": {}, "sh_roles": {},
                        "main_role": None, "fh": None, "sh": None,
                        "verdict": None}
                 for side in ("home", "away")}
    ht = detect_halftime(match)
    if ht is None:
        return out
    roles = estimate_positions(match, config)

    for e in detect_events(match, config):
        if e.type != EventType.TURNOVER or e.player_id is None:
            continue
        side = getattr(e.team, "value", e.team)
        key = "fh_roles" if e.t <= ht else "sh_roles"
        rec_role = roles[side].get(e.player_id)
        if rec_role is None:
            continue
        poszt = rec_role["poszt"]
        out[side][key][poszt] = out[side][key].get(poszt, 0) + 1

    for side in ("home", "away"):
        rec = out[side]
        fader = None
        for poszt, sh in sorted(rec["sh_roles"].items(),
                                key=lambda kv: -kv[1]):
            fh = rec["fh_roles"].get(poszt, 0)
            if sh >= FTO_MIN_SH and sh >= FTO_FACTOR * max(1, fh):
                fader = (poszt, fh, sh)
                break
        if fader is not None:
            poszt, fh, sh = fader
            rec["main_role"] = poszt
            rec["fh"], rec["sh"] = fh, sh
            rec["verdict"] = (
                f"a(z) {poszt} posztjuk eladásai a második félidőre"
                f" megugranak ({fh} → {sh}) — fáradtan nála nyílik "
                "ki a kéz: a szünet után friss védővel őt kell "
                "nyomás alá tenni, rajta olcsó a labdaszerzés")
    return out


# Menekülő-poszt: ennyi poszthoz kötött nyomás alatti passz kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy szorításban
# mindig ugyanahhoz a poszthoz menekül a labda.
ESC_MIN_PASSES = 5
ESC_SHARE_PCT = 60.0


def press_outlet_roles(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Menekülő-poszt: NYOMÁS ALATT KIHEZ megy a labda.

    A pressz-poszt azt mondja meg, melyik posztjuk VESZÍTI el a
    labdát szorításban — ez azt, hová MENEKÜL: a testközeli védő
    mellett (PRESS_TIGHT_M-en belül) meghozott passzokat a FOGADÓ
    posztjához írja.

    Edzőileg ez teszi a presszt labdaszerzéssé: ha szorításban a
    labda rendre ugyanahhoz a poszthoz megy, a kettőző mögötti
    harmadik ember előre tudja, hol kell lesben állnia — a menekülő
    passz így nem kiút, hanem elfogott labda. Saját csapatra: ha a
    kiút egy emberre szűkül, a pressz-elleni kiadásunk
    kiszámítható.

    Visszatérés csapatonként: {"passes" (poszthoz kötött nyomás
    alatti passz), "roles": {poszt: darab}, "main_role",
    "share_pct", "verdict"} — az ítélet None, ha nincs meg az
    ESC_MIN_PASSES, vagy egyik poszt sem éri el az ESC_SHARE_PCT-t.
    """
    import math

    from .roles import estimate_positions

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)

    def _tight(frame, pos, team) -> bool:
        dists = [math.hypot(p.x - pos.x, p.y - pos.y)
                 for p in frame.players
                 if p.team != team and p.role != "kapus"]
        return bool(dists) and min(dists) <= PRESS_TIGHT_M

    out: dict = {side: {"passes": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for pe in detect_passes(match, config):
        if pe.decision_frame is None or pe.passer_pos is None:
            continue
        if not _tight(pe.decision_frame, pe.passer_pos, pe.team):
            continue
        side = pe.team.value
        rec_role = roles[side].get(pe.receiver_id)
        if rec_role is None:
            continue
        poszt = rec_role["poszt"]
        rec = out[side]
        rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1
        rec["passes"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["passes"] >= ESC_MIN_PASSES:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["passes"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= ESC_SHARE_PCT:
                rec["verdict"] = (
                    f"szorításban a labda a(z) {poszt} poszthoz "
                    f"menekül ({share:.0f}%, {rec['passes']} nyomás "
                    "alatti passzból) — a kettőzés mögötti harmadik "
                    "ember ott álljon lesben: a menekülő passz így "
                    "nem kiút, hanem elfogott labda")
    return out


# Menekülők: ennyi nyomás alatti passztól emeljük ki a fogadót.
ESCP_MIN_PASSES = 3


def press_outlets(match: Match,
                  config: Optional[TacticsConfig] = None) -> dict:
    """Menekülők: NYOMÁS ALATT KIHEZ megy a labda.

    A menekülő-poszt (press_outlet_roles) a POSZTOT nevezi meg — ez
    az EMBERT: a testközeli védő mellett (PRESS_TIGHT_M-en belül)
    meghozott passzokat a FOGADÓ játékoshoz írja.

    Edzőileg ez teszi a presszt labdaszerzéssé névre szólóan: ha
    szorításban a labda rendre ugyanahhoz az emberhez megy, a
    kettőző mögötti harmadik előre tudja, hol kell lesben állnia — a
    menekülő passz így nem kiút, hanem elfogott labda. Saját
    csapatra: ha a kiút egy emberre szűkül, a pressz-elleni
    kiadásunk kiszámítható.

    Visszatérés csapatonként: {"passes" (emberhez kötött nyomás
    alatti passz), "players": [{"player_id", "jersey", "passes"}],
    "top"} — a "top" az első játékos, ha legalább ESCP_MIN_PASSES
    ilyen passzt kapott, különben None.
    """
    import math

    config = config or TacticsConfig()

    def _tight(frame, pos, team) -> bool:
        dists = [math.hypot(p.x - pos.x, p.y - pos.y)
                 for p in frame.players
                 if p.team != team and p.role != "kapus"]
        return bool(dists) and min(dists) <= PRESS_TIGHT_M

    jersey: dict = {}
    for f in match.frames:
        for p in f.players:
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)

    tally: dict = {"home": {}, "away": {}}
    for pe in detect_passes(match, config):
        if pe.decision_frame is None or pe.passer_pos is None:
            continue
        if not _tight(pe.decision_frame, pe.passer_pos, pe.team):
            continue
        side = pe.team.value
        if pe.receiver_id is None:
            continue
        tally[side][pe.receiver_id] = (
            tally[side].get(pe.receiver_id, 0) + 1)

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "passes": n}
                for pid, n in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1])]
        top = (rows[0]
               if rows and rows[0]["passes"] >= ESCP_MIN_PASSES
               else None)
        out[side] = {"passes": sum(r["passes"] for r in rows),
                     "players": rows, "top": top}
    return out


# Térnyerők: ennyi labdával megtett előre-métertől emeljük ki a
# játékost.
TNRP_MIN_M = 25.0


def ball_carriers(match: Match,
                  config: Optional[TacticsConfig] = None) -> dict:
    """Térnyerők: KI VISZI ELŐRE a labdát.

    A térnyerő-poszt (ball_carrier_roles) a POSZTOT nevezi meg — ez
    az EMBERT: a labdás játékos egymást követő kockái közt a
    támadott kapu felé megtett métereket játékosonként összegzi.

    Edzőileg ez a lendület-fék névre szóló terve: őt nem a hatosnál
    kell fogadni, hanem a felezőtől hátrálva — lendületbe engedni
    tilos, mert onnan már csak szabálytalansággal állítható meg.
    Saját csapatra: ha a térnyerés egy emberen áll, a kiesésével a
    felhozatalunk is leáll.

    Visszatérés csapatonként: {"meters" (emberhez kötött
    előre-méter), "players": [{"player_id", "jersey", "meters"}],
    "top"} — a "top" az első játékos, ha legalább TNRP_MIN_M métert
    vitt előre, különben None.
    """
    config = config or TacticsConfig()

    jersey: dict = {}
    for f in match.frames:
        for p in f.players:
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)

    tally: dict = {"home": {}, "away": {}}
    prev = None   # (track_id, side, x, elore-irany)
    for f in match.frames:
        h = ball_holder(f, config)
        if h is None or h.team is None or h.role == "kapus":
            prev = None
            continue
        side = h.team.value
        goal_x = config.attacks_toward_x(h.team)
        ahead = 1.0 if goal_x > COURT_LENGTH_M / 2.0 else -1.0
        if prev is not None and prev[0] == h.track_id \
                and prev[1] == side:
            dx = (h.x - prev[2]) * ahead
            if 0.0 < dx < 2.0:   # előre-mozgás (követés-ugrás nélkül)
                tally[side][h.track_id] = round(
                    tally[side].get(h.track_id, 0.0) + dx, 2)
        prev = (h.track_id, side, h.x, ahead)

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "meters": round(m, 1)}
                for pid, m in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1])]
        top = (rows[0]
               if rows and rows[0]["meters"] >= TNRP_MIN_M else None)
        out[side] = {"meters": round(sum(r["meters"] for r in rows), 1),
                     "players": rows, "top": top}
    return out


# Fáradt-eladók: a második félidőben ennyi eladástól emeljük ki a
# játékost, és ekkora ugrás számít fáradás-jelnek.
FTOP_MIN_SH = 2
FTOP_FACTOR = 2.0


def tired_turnover_players(match: Match,
                           config: Optional[TacticsConfig] = None
                           ) -> dict:
    """Fáradt-eladók: KINEK a labdái vesznek el fáradtan.

    A fáradt-eladó poszt (tired_turnover_roles) a POSZTOT nevezi meg
    — ez az EMBERT: a labdaeladásokat félidőnként a vesztes
    játékoshoz írja, és megkeresi, kinek ugranak meg az eladásai a
    második félidőre.

    Edzőileg ez a második félidei pressz-terv névre szólóan: akinek
    az eladásai fáradtan megugranak, azt a szünet után kell nyomás
    alá tenni — a friss védő rajta olcsó labdákat szerez. Saját
    csapatra: az ő terhelés-menedzsmentje (pihentetés, csere-ritmus)
    és a fáradt labdabiztonság-edzés a téma.

    Visszatérés csapatonként: {"fh": {játékos-kulcs: darab}, "sh":
    {...}, "top"} — a "top" az a játékos, akinek a második félidei
    eladásai elérik az FTOP_MIN_SH-t, és legalább FTOP_FACTOR-szorosai
    az elsőnek; szünet-jel nélkül üres a kép.
    """
    from .event_detection import EventType, detect_events
    from .halftime import detect_halftime

    config = config or TacticsConfig()
    out: dict = {side: {"fh": {}, "sh": {}, "top": None}
                 for side in ("home", "away")}
    ht = detect_halftime(match)
    if ht is None:
        return out

    jersey: dict = {}
    for f in match.frames:
        for p in f.players:
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)

    tally: dict = {"home": {}, "away": {}}
    for e in detect_events(match, config):
        if e.type != EventType.TURNOVER or e.player_id is None:
            continue
        side = getattr(e.team, "value", e.team)
        rec = tally[side].setdefault(e.player_id, [0, 0])
        rec[0 if e.t <= ht else 1] += 1

    for side in ("home", "away"):
        rows = sorted(tally[side].items(), key=lambda kv: -kv[1][1])
        out[side]["fh"] = {
            str(jersey.get(pid, pid)): n[0]
            for pid, n in rows if n[0]}
        out[side]["sh"] = {
            str(jersey.get(pid, pid)): n[1]
            for pid, n in rows if n[1]}
        for pid, (fh, sh) in rows:
            if sh >= FTOP_MIN_SH and sh >= FTOP_FACTOR * max(1, fh):
                out[side]["top"] = {
                    "player_id": pid, "jersey": jersey.get(pid),
                    "fh": fh, "sh": sh}
                break
    return out
