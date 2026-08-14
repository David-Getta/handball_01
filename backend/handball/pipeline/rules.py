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
from .primitive_cache import copy_rows, memoize_primitive

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


@memoize_primitive("field_count_timeline", copy=copy_rows)
def field_count_timeline(match: Match, window_s: float = PP_WINDOW_S) -> list[dict]:
    """Ablakonként a pályán látott MEZŐNYJÁTÉKOS-trackek száma csapatonként.

    Mért pozíciókból számol (a becslő kitöltése nem torzít), a kapust
    (role="kapus") nem számolja, és a nagyon rövid ideig látszó trackeket
    (az ablak <20%-a) zajként kihagyja. A pásztázó kamera miatt EGY kockán
    nem látszik mindenki — ablakon belül igen.

    Nyitott `primitive_cache` hatókörön belül meccsenként egyszer fut
    le; a visszaadott lista mindig friss másolat.
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


# Kettős emberhátrány: legfeljebb négy mezőnyjátékos a pályán.
DSH_MIN_S = 20.0      # legalább ennyi kettős-hátrány idő kell
DSH_FATAL_GOALS = 2   # ennyi kapott gól alatta: végzetes minta
DSH_TAIL_S = 3.0      # a szakasz utáni gól még a hátrányé


def double_shorthand(match: Match, config=None) -> dict:
    """Kettős emberhátrány: MIT KEZD a csapat négy mezőnyjátékossal.

    Az emberhátrány-rétegek az 5 fős játékot nézik — ez a ritkább, de
    meccsdöntő kettős hátrányt (két kiállítás átfedésben, legfeljebb
    4 mezőnyjátékos): mennyi ideig tartott, és hány gól esett bele.
    A kettős hátrány kezelése külön műfaj: más fal (3-1 vagy 4-0
    mélyen), más labdatartás — aki nem gyakorolja, annak két perc
    alatt fordul meg a meccse.

    Edzőileg: akinél a kettős hátrány rendre gólesőt hoz, ott a
    második kiállítás kiprovokálása tudatos fegyver lehet ellene; a
    saját oldalon a 4 fős fal és az időhúzó labdatartás gyakorlása a
    téma.

    Visszatérés csapatonként: {"seconds", "conceded", "verdict"} — a
    verdict "a kettős emberhátrány végzetes nekik" (DSH_FATAL_GOALS
    kapott góltól), "a kettős hátrányt is túlélik" (DSH_MIN_S-nyi idő
    gól nélkül), különben None.
    """
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    tl = field_count_timeline(match)
    out = {side: {"seconds": 0.0, "conceded": 0, "verdict": None}
           for side in ("home", "away")}
    if len(tl) < 2:
        return out
    win_frames = tl[1]["start_frame"] - tl[0]["start_frame"]
    win_s = win_frames / fps
    goals = [(e.t, getattr(e.team, "value", e.team))
             for e in detect_shots(match, config)
             if e.type == EventType.GOAL]
    tail = round(DSH_TAIL_S * fps)
    for side, other in (("home", "away"), ("away", "home")):
        rec = out[side]
        for w in tl:
            if w[side] <= 4 and w[side] < w[other]:
                rec["seconds"] += win_s
                a = w["start_frame"]
                b = a + win_frames
                rec["conceded"] += sum(
                    1 for (t, tm) in goals
                    if tm == other and a <= t <= b + tail)
        rec["seconds"] = round(rec["seconds"], 1)
        if rec["conceded"] >= DSH_FATAL_GOALS:
            rec["verdict"] = "a kettős emberhátrány végzetes nekik"
        elif rec["seconds"] >= DSH_MIN_S and rec["conceded"] == 0:
            rec["verdict"] = "a kettős hátrányt is túlélik"
    return out


# Létszám-hiba: csere-átfedésből hetedik mezőnyjátékos a pályán.
XSP_MIN_WINDOWS = 2   # ennyi (PP_WINDOW_S-es) többlet-ablaktól ítélet


def excess_players(match: Match, config=None) -> dict:
    """Létszám-hiba: mikor van HETEDIK mezőnyjátékos a pályán.

    A kiállítás-felismerés (detect_powerplay) a hiányt nézi — ez a
    többletet: azokat az ablakokat, amikben egy csapatnak hétnél is
    több mezőnyjátékos-track-je van a pályán. Ez tipikusan
    csere-átfedés: a lejövő még a pályán, a felálló már beállt. A
    szabály szerint ez büntetendő (kiállítás-kockázat), és a
    váltás-pillanat rendezetlenségét is jelzi.

    Edzőileg: az átfedően cserélő ellenfélnél a váltás-pillanat
    kettős célpont — jelezhető a zsűrinek, és a rendezetlenségbe
    gyors támadás mehet; a saját oldalon a cserefolyosó-fegyelem
    (előbb le, aztán fel) az edzés-téma, mert ez ingyen kiállítást
    ér.

    Visszatérés csapatonként: {"windows", "seconds", "verdict"} — a
    verdict "csere-átfedésben hetedik ember a pályán"
    (XSP_MIN_WINDOWS ablaktól), különben None.
    """
    tl = field_count_timeline(match)
    out = {side: {"windows": 0, "seconds": 0.0, "verdict": None}
           for side in ("home", "away")}
    if len(tl) < 2:
        return out
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win_s = (tl[1]["start_frame"] - tl[0]["start_frame"]) / fps
    for w in tl:
        for side in ("home", "away"):
            if w[side] >= 7:
                out[side]["windows"] += 1
                out[side]["seconds"] += win_s
    for rec in out.values():
        rec["seconds"] = round(rec["seconds"], 1)
        if rec["windows"] >= XSP_MIN_WINDOWS:
            rec["verdict"] = "csere-átfedésben hetedik ember a pályán"
    return out


# Fegyelem-állás: kiállítások az eredményjelző szerint.
SPS_MIN_TOTAL = 3   # ennyi kiállítás alatt nincs ítélet
SPS_DIFF = 2        # ekkora többlet számít mintázatnak


def suspensions_by_score(match: Match, config=None) -> dict:
    """Fegyelem-állás: MIKOR jönnek a kiállítások — állás szerint.

    A fegyelem-esés (discipline_fade) az időtengelyen nézi a
    kiállításokat — ez az eredményjelzőn: a kiállítás pillanatában
    vezetett, állt vagy hátrányban volt-e a kiállított csapat. A
    hátrányban sűrűsödő kiállítás a frusztrációs szabálytalanság
    jele: aki az eredmény után fut, késve érkezik és üt. Az előnyben
    sűrűsödő a vezetés-őrző (hideg) keménység.

    Edzőileg: a frusztrációs csapat ellen a vezetés maga a fegyver —
    vállalt kontakt és türelmes játék kiállítást terem; a saját
    oldalon a hátrányban is hideg fej az edzés-téma, mert a
    frusztrációs kiállítás dupla ár: ember is, gól is.

    Visszatérés csapatonként: {"trailing", "leading", "level",
    "verdict"} — a verdict "hátrányban elszáll a fegyelmük" /
    "előnyben szabálytalankodnak" / None (kevés kiállítás vagy
    egyenletes kép).
    """
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    goals = [(e.t, e.team.value) for e in detect_shots(match, config)
             if e.type == EventType.GOAL]
    out = {side: {"trailing": 0, "leading": 0, "level": 0,
                  "verdict": None} for side in ("home", "away")}
    for w in detect_powerplay(match):
        side = w["team_down"]
        t0 = w["start_frame"]
        own = sum(1 for (t, tm) in goals if t < t0 and tm == side)
        opp = sum(1 for (t, tm) in goals if t < t0 and tm != side)
        state = ("leading" if own > opp
                 else "trailing" if own < opp else "level")
        out[side][state] += 1
    for rec in out.values():
        total = rec["trailing"] + rec["leading"] + rec["level"]
        if total < SPS_MIN_TOTAL:
            continue
        if rec["trailing"] - (rec["leading"] + rec["level"]) >= SPS_DIFF:
            rec["verdict"] = "hátrányban elszáll a fegyelmük"
        elif rec["leading"] - (rec["trailing"] + rec["level"]) >= SPS_DIFF:
            rec["verdict"] = "előnyben szabálytalankodnak"
    return out


# Hetes-állás: a kiharcolt hetesek az eredményjelző szerint.
SVS_MIN_TOTAL = 3   # ennyi kiharcolt hetes alatt nincs ítélet
SVS_DIFF = 2        # ekkora hátrány-többlet számít mintázatnak


def sevens_by_score(match: Match, config=None) -> dict:
    """Hetes-állás: MIKOR harcolják ki a heteseiket — állás szerint.

    A hetes-kiharcolók (seven_meter_earners) azt mondják meg, KI hozza
    a heteseket — ez azt, MILYEN ÁLLÁSNÁL jönnek: a kiharcolás
    pillanatában vezetett, állt vagy hátrányban volt-e a kiharcoló
    csapat. A hátrányban sűrűsödő hetes tudatos menekülő-fegyver:
    a lemaradó csapat a betörésbe és a kontaktba menekül, mert a
    hetes a legolcsóbb gól.

    Edzőileg: az ilyen csapat ellen vezetésnél a fal lábbal
    védekezzen és ne üssön — a betörőjük a kezet keresi; a kapusnak
    pedig vezetésnél kell a hetes-készenlét, mert jönni fog. A saját
    oldalon ugyanez fegyverként tanítható: hátrányban a betörés a
    hetesig vihető.

    Visszatérés csapatonként (a KIHARCOLÓ oldal): {"trailing",
    "leading", "level", "verdict"} — a verdict "hátrányban harcolják
    ki a heteseiket" (SVS_DIFF-nyi hátrány-többletnél), különben
    None (kevés hetesnél is None).
    """
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    config = config or TacticsConfig()
    goals = [(e.t, e.team.value) for e in detect_shots(match, config)
             if e.type == EventType.GOAL]
    out = {side: {"trailing": 0, "leading": 0, "level": 0,
                  "verdict": None} for side in ("home", "away")}
    for sm in detect_seven_meters(match, config):
        side = sm["team"]
        t0 = sm["t"]
        own = sum(1 for (t, tm) in goals if t < t0 and tm == side)
        opp = sum(1 for (t, tm) in goals if t < t0 and tm != side)
        state = ("leading" if own > opp
                 else "trailing" if own < opp else "level")
        out[side][state] += 1
    for rec in out.values():
        total = rec["trailing"] + rec["leading"] + rec["level"]
        if total < SVS_MIN_TOTAL:
            continue
        if rec["trailing"] - (rec["leading"] + rec["level"]) >= SVS_DIFF:
            rec["verdict"] = "hátrányban harcolják ki a heteseiket"
    return out


# Fegyelem-esés: ennyi kiállítástól ítélünk, és ekkora félidők közti
# többlet számít mintázatnak (nem egyszeri balszerencsének).
DISC_FADE_MIN_TOTAL = 3
DISC_FADE_DIFF = 2


def discipline_fade(match: Match, config=None) -> dict:
    """Fegyelem-esés: a kiállítások félidőnkénti eloszlása — a fáradás-kép
    fej-oldali tagja.

    A felismert kiállításokat (emberhátrány-ablakokat) a felismert félidő
    mentén számoljuk szét. Akinek a kiállításai a 2. félidőben sűrűsödnek,
    az fáradtan, késve érkezve szabálytalankodik — a hajrában emberelőny
    várható ellene; akinek az elején jönnek, az kemény kezdés után
    szelídül.

    Visszatérés csapatonként:
      {"fh_susp", "sh_susp", "verdict"} — verdict None (nincs félidő-jel
    vagy kevés kiállítás), "hajrában szabálytalankodnak" vagy
    "az elején kemények".
    """
    from .halftime import detect_halftime

    empty = {"fh_susp": 0, "sh_susp": 0, "verdict": None}
    out = {"home": dict(empty), "away": dict(empty)}
    ht = detect_halftime(match)
    if ht is None:
        return out
    for w in detect_powerplay(match):
        rec = out[w["team_down"]]
        rec["fh_susp" if w["start_frame"] <= ht else "sh_susp"] += 1
    for s in ("home", "away"):
        rec = out[s]
        if rec["fh_susp"] + rec["sh_susp"] < DISC_FADE_MIN_TOTAL:
            continue
        if rec["sh_susp"] - rec["fh_susp"] >= DISC_FADE_DIFF:
            rec["verdict"] = "hajrában szabálytalankodnak"
        elif rec["fh_susp"] - rec["sh_susp"] >= DISC_FADE_DIFF:
            rec["verdict"] = "az elején kemények"
    return out


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


# Passzív-kockázat: ennyi felállt támadás kell az ítélethez, és
# ekkora részarány fölött mondjuk ki, hogy rendszeresen belefutnak a
# passzív jelbe.
PSR_MIN_ATTACKS = 4
PSR_SHARE_PCT = 20.0


def passive_risk(match: Match,
                 config: Optional[TacticsConfig] = None) -> dict:
    """Passzív-kockázat: MENNYIRE gyakran futnak bele a passzív jelbe.

    A passzív-kockázatú szakaszok (passive_play_risks) a listát
    adják — ez az ARÁNYT: a lövés nélkül elnyúló felállt támadásokat
    az ÖSSZES felállt támadásukhoz viszonyítja.

    Edzőileg ez a türelem jutalma: ha rendszeresen belefutnak a
    passzív jelbe, ellenük a zárt, türelmes fal dolgozik — nem kell
    kilépni és kockáztatni, a játékvezető és az óra a szövetségesünk.
    Saját csapatra: a lövés nélkül elnyúló támadás nem stílus, hanem
    befejezés-hiány — a második hullámnak befejezés-lehetőséggel
    kell érkeznie.

    Visszatérés csapatonként: {"positional", "passive", "share_pct",
    "verdict"} — a share_pct/verdict None, ha kevés
    (PSR_MIN_ATTACKS alatti) a felállt támadás.
    """
    from .attack_types import AttackType, classify_attacks

    config = config or TacticsConfig()
    out = {side: {"positional": 0, "passive": 0, "share_pct": None,
                  "verdict": None}
           for side in ("home", "away")}

    for a in classify_attacks(match, config):
        if a["type"] != AttackType.POSITIONAL.value:
            continue
        side = a["team"]
        if side in out:
            out[side]["positional"] += 1
    for a in passive_play_risks(match, config):
        side = a["team"]
        if side in out:
            out[side]["passive"] += 1

    for rec in out.values():
        if rec["positional"] >= PSR_MIN_ATTACKS:
            share = 100.0 * rec["passive"] / rec["positional"]
            rec["share_pct"] = round(share, 1)
            if share >= PSR_SHARE_PCT:
                rec["verdict"] = (
                    f"rendszeresen belefutnak a passzív jelbe "
                    f"({rec['passive']}/{rec['positional']} felállt "
                    f"támadás, {share:.0f}%) — ellenük a zárt, "
                    "türelmes fal dolgozik: nem kell kilépni, az óra "
                    "és a játékvezető nekünk dolgozik")
    return out


# A 7 m-es után ennyi másodpercen belüli lövést párosítjuk hozzá kimenetelként.
SEVEN_OUTCOME_WINDOW_S = 6.0


# A hetes iránya: a labda kapu-síkbeli y-eltérése ennél nagyobb → szélső sáv.
SEVEN_DIR_SIDE_M = 0.5
# Az irány magyar határozói alakja — minden felület ebből ír ("balra").
SEVEN_DIR_HU = {"bal": "balra", "jobb": "jobbra", "közép": "középre"}
# Csak akkor mondunk irányt, ha a labda ennyire megközelítette a kapu síkját.
SEVEN_DIR_MAX_PLANE_M = 1.5


def _seven_direction(match: Match, t0: int, goal_x: float,
                     fps: float) -> Optional[str]:
    """Merre ment a hetes a kapuban (bal/közép/jobb) a DOBÓ szemszögéből.

    A lövés utáni ~1 mp-ben azt a kockát keressük, ahol a labda a
    legközelebb járt a kapu síkjához, és az ottani oldal-eltérésből
    (y a kapu közepéhez képest) mondjuk meg a sávot. None, ha a labda
    nem került a sík közelébe (pl. eltakarták).
    """
    cy = COURT_WIDTH_M / 2.0
    horizon = t0 + round(1.0 * fps)
    best = None  # (kapu-sík távolság, y)
    for f in match.frames:
        if f.t < t0 or f.t > horizon or f.ball is None:
            continue
        d = abs(f.ball.x - goal_x)
        if best is None or d < best[0]:
            best = (d, f.ball.y)
    if best is None or best[0] > SEVEN_DIR_MAX_PLANE_M:
        return None
    off = best[1] - cy
    # A dobó szemszögéből: a +x kapura nézve az alacsony y a BAL oldal;
    # a -x kapura dobva tükrözünk.
    if goal_x < COURT_LENGTH_M / 2.0:
        off = -off
    if off <= -SEVEN_DIR_SIDE_M:
        return "bal"
    if off >= SEVEN_DIR_SIDE_M:
        return "jobb"
    return "közép"


def seven_meter_outcomes(match: Match,
                         config: Optional[TacticsConfig] = None) -> list[dict]:
    """A felismert hétméteresek KIMENETELLEL: gól / védés / kihagyva.

    A 7 m-es esemény utáni SEVEN_OUTCOME_WINDOW_S-en belüli, ugyanarra a
    kapura, ugyanattól a csapattól jövő ELSŐ lövés-eseményt párosítjuk
    hozzá (a lövés-kimenetel a meglévő detect_shots detail-jéből jön).
    Ha az ablakban nincs lövés, az outcome "ismeretlen" (pl. újra
    lefújták, vagy a labda nem látszott).

    Visszatérés: [{"t", "team", "goal_x", "outcome", "shooter_id",
    "irany"}] — az irany a kapun belüli sáv (bal/közép/jobb) a dobó
    szemszögéből, None, ha nem mérhető."""
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = round(SEVEN_OUTCOME_WINDOW_S * fps)
    shots = [e for e in detect_shots(match, config)
             if e.type in (EventType.SHOT, EventType.GOAL)]

    out = []
    for sm in detect_seven_meters(match, config):
        rec = dict(sm)
        rec["outcome"] = "ismeretlen"
        rec["shooter_id"] = None
        rec["irany"] = None
        for e in shots:
            if not (sm["t"] <= e.t <= sm["t"] + win):
                continue
            if e.team.value != sm["team"]:
                continue
            rec["outcome"] = ("gól" if e.type == EventType.GOAL else
                              "védés" if (e.detail or {}).get("outcome") == "save"
                              else "kihagyva")
            rec["shooter_id"] = e.player_id
            rec["irany"] = _seven_direction(match, e.t, sm["goal_x"],
                                            fps)
            break
        out.append(rec)
    return out


def seven_meter_summary(match: Match,
                        config: Optional[TacticsConfig] = None) -> dict:
    """Hétméteres-mérleg csapatonként: kísérlet / gól / védés / kihagyva."""
    out = {side: {"attempts": 0, "goals": 0, "saved": 0, "missed": 0}
           for side in ("home", "away")}
    for sm in seven_meter_outcomes(match, config):
        rec = out[sm["team"]]
        rec["attempts"] += 1
        if sm["outcome"] == "gól":
            rec["goals"] += 1
        elif sm["outcome"] == "védés":
            rec["saved"] += 1
        elif sm["outcome"] == "kihagyva":
            rec["missed"] += 1
    return out


# Hetes-hozam: ennyi mért hetes kell az ítélethez; e fölött
# "biztos kezűek", e alatt "megfoghatók" a hetesnél.
SVY_MIN_ATTEMPTS = 4
SVY_HIGH_PCT = 85.0
SVY_LOW_PCT = 60.0


def seven_yield(match: Match,
                config: Optional[TacticsConfig] = None) -> dict:
    """Hetes-hozam: MENNYIT ÉR NÁLUK egy megítélt hetes.

    A hétméteres-mérleg (seven_meter_summary) a nyers számokat adja
    — ez az ÍTÉLETET: a felismert hetesek gólarányát méri, és
    megmondja, mit ér ellenük a hetest érő szabálytalanság.

    Edzőileg ez a védekezés ár-kalkulációja. Ha a heteseik szinte
    mindig bemennek, a hetest érő szabálytalanság a legrosszabb
    üzlet: a fal lábbal védekezzen, és a beugró ellen inkább a
    testtel elzárt út kell, mint a kézzel visszahúzás. Ha a
    hetesük megfogható, a biztos helyzetet megállító szabálytalanság
    vállalható, és a kapusnak érdemes a hetesre külön készülnie.
    Saját csapatra: a hetes-értékesítésünk mérhető, nem hitkérdés.

    Visszatérés csapatonként (a DOBÓ oldal): {"attempts", "goals",
    "saved", "missed", "goal_pct", "verdict"} — a pct/verdict None,
    ha kevés (SVY_MIN_ATTEMPTS alatti) a mért hetes.
    """
    config = config or TacticsConfig()
    summ = seven_meter_summary(match, config)

    out: dict = {}
    for side in ("home", "away"):
        rec = dict(summ.get(side, {"attempts": 0, "goals": 0,
                                   "saved": 0, "missed": 0}))
        rec["goal_pct"] = None
        rec["verdict"] = None
        if rec["attempts"] >= SVY_MIN_ATTEMPTS:
            pct = 100.0 * rec["goals"] / rec["attempts"]
            rec["goal_pct"] = round(pct, 1)
            if pct >= SVY_HIGH_PCT:
                rec["verdict"] = (
                    f"a hetesük szinte biztos gól ({rec['goals']}/"
                    f"{rec['attempts']}, {pct:.0f}%) — a hetest érő "
                    "szabálytalanság a legrosszabb üzlet: a fal "
                    "lábbal védekezzen, a beugró elé testtel kell "
                    "állni, nem kézzel visszahúzni")
            elif pct <= SVY_LOW_PCT:
                rec["verdict"] = (
                    f"a hetesük megfogható ({rec['goals']}/"
                    f"{rec['attempts']}, {pct:.0f}%) — a biztos "
                    "helyzetet megállító szabálytalanság ellenük "
                    "vállalható, és a kapusnak külön készülnie kell "
                    "a hetesükre")
        out[side] = rec
    return out


def seven_meter_defense(match: Match,
                        config: Optional[TacticsConfig] = None) -> dict:
    """Hetes-védés: a kapus mérlege a RÁ dobott hetesekből.

    A hetes-mérleg (seven_meter_summary) kapus-oldali olvasata: az
    ellenfél hetesei közül mennyi ment be, mennyit fogott a kapus,
    mennyi ment mellé. A hetest fogó kapus ellen a hetes nem "kész gól"
    — a dobóknak készülniük kell; a hetest sosem fogó kapus ellen a
    hetes-kiharcolás biztos üzlet.

    Visszatérés csapatonként (a VÉDEKEZŐ csapat kapusáé):
      {"faced", "saved", "conceded", "missed"} — faced a kapura tartó
    hetesek száma (gól + védés; a mellé menő nem a kapus érdeme).
    """
    summ = seven_meter_summary(match, config)
    out = {}
    for side, other in (("home", "away"), ("away", "home")):
        rec = summ[other]
        out[side] = {
            "faced": rec["goals"] + rec["saved"],
            "saved": rec["saved"],
            "conceded": rec["goals"],
            "missed": rec["missed"],
        }
    return out


def rules_report(match: Match) -> dict:
    """A szabály-értő réteg összegzése egy hívásban (az API-nak)."""
    return {
        "powerplay": detect_powerplay(match),
        "powerplay_efficiency": powerplay_efficiency(match),
        # A hétméteresek kimenetellel (gól/védés/kihagyva) mennek ki.
        "seven_meters": seven_meter_outcomes(match),
        "seven_meter_summary": seven_meter_summary(match),
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


# Hetes-kiharcoló: ennyi másodperccel a hetes-jel előtt nézzük, ki volt
# a kapuhoz legközelebbi támadó (a szabálytalanság áldozata jellemzően ő).
SEVEN_EARNER_LOOKBACK_S = 2.0


# Hetes-forrás: ennyi felismert hetes kell az ítélethez, és ekkora
# részarány fölött mondjuk ki, hogy a heteseik egy játékhelyzetből
# jönnek.
SVS_MIN_SEVENS = 3
SVS_SHARE_PCT = 60.0


def seven_sources(match: Match,
                  config: Optional[TacticsConfig] = None) -> dict:
    """Hetes-forrás: MILYEN HELYZETBŐL jön a hetesük.

    A hetes-kiharcolók (seven_earners) az embert nevezik meg, a
    hetes-okozók a védőt — ez a JÁTÉKHELYZETET: minden felismert
    hetest ahhoz a támadás-szakaszhoz köt, amelyben esett, és a
    szakasz típusa szerint csoportosít (lerohanás, felállt támadás,
    átmenet).

    Edzőileg ez a szabálytalanság-fegyelem címzettje. Ha a heteseik
    zöme lerohanásból jön, a visszafutásnál tilos a kézzel fékezés —
    inkább menjen be a gól, mint a hetes plusz kiállítás; ha felállt
    támadásból, a fal lábmunkája a kérdés, és a beugró elé testtel
    kell állni. Saját csapatra fordítva: ugyanez mutatja, honnan
    tudunk hetest kiharcolni.

    Visszatérés csapatonként (a DOBÓ oldal): {"sevens", "types":
    {típus: darab}, "main_type", "share_pct", "verdict"} — az ítélet
    None, ha nincs meg az SVS_MIN_SEVENS, vagy egyik típus sem éri
    el az SVS_SHARE_PCT-t.
    """
    from .attack_types import classify_attacks

    config = config or TacticsConfig()
    attacks = classify_attacks(match, config)

    out: dict = {side: {"sevens": 0, "types": {}, "main_type": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for sm in detect_seven_meters(match, config):
        side = sm["team"]
        if side not in out:
            continue
        tipus = None
        for a in attacks:
            if (a["team"] == side
                    and a["start_frame"] <= sm["t"] <= a["end_frame"]):
                tipus = a["type"]
                break
        if tipus is None:
            continue
        rec = out[side]
        rec["types"][tipus] = rec["types"].get(tipus, 0) + 1
        rec["sevens"] += 1

    for rec in out.values():
        rec["types"] = dict(sorted(rec["types"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["sevens"] >= SVS_MIN_SEVENS:
            tipus = max(rec["types"], key=lambda k: rec["types"][k])
            share = 100.0 * rec["types"][tipus] / rec["sevens"]
            rec["main_type"] = tipus
            rec["share_pct"] = round(share, 1)
            if share >= SVS_SHARE_PCT:
                rec["verdict"] = (
                    f"a heteseik {share:.0f}%-a {tipus} helyzetből "
                    f"jön ({rec['sevens']} felismert hetesből) — a "
                    "szabálytalanság-fegyelmet oda kell vinni: ott "
                    "kézzel fékezni tilos, inkább menjen be a gól, "
                    "mint a hetes")
    return out


def seven_meter_earners(match: Match,
                        config: Optional[TacticsConfig] = None) -> dict:
    """Ki harcolja ki a hétméterseket: a hetes-jel előtt a támadott
    kapuhoz legközelebb járó (nem kapus) támadó kapja a jóváírást.

    Heurisztika, de magyarázható: a befejezésbe érkező embert rántják
    le. A felderítésben ebből lesz a "vele szemben kéz nélkül" kulcs.

    Visszatérés: {"home"/"away": [{"player_id", "earned"}]}.
    """
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    frames_by_t = {f.t: f for f in match.frames}
    tally: dict = {"home": {}, "away": {}}
    for sm in detect_seven_meters(match, config):
        t_prev = sm["t"] - round(SEVEN_EARNER_LOOKBACK_S * fps)
        fr = None
        for dt in range(0, round(fps)):
            fr = frames_by_t.get(t_prev - dt) or frames_by_t.get(t_prev + dt)
            if fr is not None and fr.players:
                break
        if fr is None or not fr.players:
            continue
        best = None
        for p in fr.players:
            if p.team.value != sm["team"] or p.role == "kapus":
                continue
            d = abs(p.x - sm["goal_x"])
            if best is None or d < best[1]:
                best = (p.track_id, d)
        if best is not None:
            side = tally[sm["team"]]
            side[best[0]] = side.get(best[0], 0) + 1
    return {side: [{"player_id": pid, "earned": n}
                   for pid, n in sorted(rec.items(),
                                        key=lambda kv: -kv[1])]
            for side, rec in tally.items()}


# Kiállítás-kiharcoló: ennyivel a hátrány észlelt kezdete előtt keressük
# a szabálytalanságot kiváltó támadót (a PP-ablak felbontása miatt tág).
SUSP_EARNER_LOOKBACK_S = PP_WINDOW_S


def suspension_earners(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Ki harcolja ki a kiállításokat: a hátrány kezdete előtti
    másodpercekben a támadott kapuhoz legközelebb nyomuló (nem kapus)
    ellenfél-támadó kapja a jóváírást.

    Ugyanaz a magyarázható heurisztika, mint a hetes-kiharcolónál: a
    2 percet tipikusan a kapura törő ember elleni szabálytalanság hozza.
    A felderítésben ebből lesz a "ő hozza a kiállításokat" kulcs.

    Visszatérés: {"home"/"away": [{"player_id", "earned"}]} — a
    KIHARCOLÓ (előnyt szerző) oldal szerint csoportosítva.
    """
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    frames_by_t = {f.t: f for f in match.frames}
    tally: dict = {"home": {}, "away": {}}
    for w in detect_powerplay(match):
        earner_team = "away" if w["team_down"] == "home" else "home"
        goal_x = config.attacks_toward_x(
            Team.HOME if earner_team == "home" else Team.AWAY)
        # A hátrány-ablak kezdete előtti másodpercekben, kockáról
        # kockára: ki járt legmélyebben a kapunál.
        t0 = w["start_frame"] - round(SUSP_EARNER_LOOKBACK_S * fps)
        best = None
        for dt in range(0, round(SUSP_EARNER_LOOKBACK_S * fps) + 1):
            fr = frames_by_t.get(t0 + dt)
            if fr is None:
                continue
            for p in fr.players:
                if p.team.value != earner_team or p.role == "kapus":
                    continue
                d = abs(p.x - goal_x)
                if best is None or d < best[1]:
                    best = (p.track_id, d)
        if best is not None:
            side = tally[earner_team]
            side[best[0]] = side.get(best[0], 0) + 1
    return {side: [{"player_id": pid, "earned": n}
                   for pid, n in sorted(rec.items(),
                                        key=lambda kv: -kv[1])]
            for side, rec in tally.items()}


# A kiülő azonosításához: ennyivel a hátrány kezdete előtt nézzük, ki
# volt még a pályán (aki a teljes hátrány alatt el is tűnik, az ült ki).
SUSP_WHO_LOOKBACK_S = 20.0


def suspended_players(match: Match,
                      config: Optional[TacticsConfig] = None) -> dict:
    """Ki ült ki: a kiállítás lenyomata a TRACKEKBEN is ott van — a
    büntetett játékos a hátrány teljes ideje alatt hiányzik a pályáról.

    A hátrány kezdete előtti SUSP_WHO_LOOKBACK_S-ben mért, nem kapus
    trackek közül az a kiülő, amelyik a hátrány alatt egyszer sem
    látszik. Ha több ilyen van (cserehullám zaja), inkább nem mondunk
    semmit — nincs hamis vádaskodás.

    Visszatérés: {"home"/"away": [{"player_id", "suspensions"}]} — a
    BÜNTETETT oldal szerint, kiállítás-szám szerint csökkenő sorban.
    """
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    tally: dict = {"home": {}, "away": {}}
    for w in detect_powerplay(match):
        side = w["team_down"]
        t0, t1 = w["start_frame"], w["end_frame"]
        look = t0 - round(SUSP_WHO_LOOKBACK_S * fps)
        before: set = set()
        during: set = set()
        for f in match.frames:
            if look <= f.t < t0:
                for p in f.players:
                    if (p.team.value == side and p.role != "kapus"
                            and p.source == PositionSource.MEASURED):
                        before.add(p.track_id)
            elif t0 <= f.t <= t1:
                for p in f.players:
                    if p.team.value == side:
                        during.add(p.track_id)
        gone = [tid for tid in before if tid not in during]
        if len(gone) == 1:
            tally[side][gone[0]] = tally[side].get(gone[0], 0) + 1
    return {side: [{"player_id": pid, "suspensions": n}
                   for pid, n in sorted(rec.items(),
                                        key=lambda kv: -kv[1])]
            for side, rec in tally.items()}


# Kiülő-poszt: ennyi poszthoz kötött kiállítás kell az ítélethez, és
# ekkora részarány fölött mondjuk ki, hogy a kétperceik egy posztra
# járnak.
SUP_MIN_SUSP = 3
SUP_SHARE_PCT = 60.0


def suspended_roles(match: Match,
                    config: Optional[TacticsConfig] = None) -> dict:
    """Kiülő-poszt: MELYIK POSZTJUK gyűjti a kétperceket.

    A "ki ült ki" réteg (suspended_players) az embert nevezi meg — ez
    a posztot: a kiállításokat a kiülő játékos posztjához írja. Így a
    minta akkor is látszik, ha a nevek meccsről meccsre cserélődnek.

    Edzőileg két olvasat egyszerre. Ellenük: ha a kétperceik rendre
    ugyanarról a posztról jönnek, a meccs elején oda kell vezetni a
    játékot — az az ember hamar behúzza az első kettőt, és onnantól
    vagy hiányzik, vagy fékezve véd. Saját csapatra: ha a mi
    kétperceink egy poszton gyűlnek, az az ember (vagy a mögötte lévő
    besegítés-szabály) szorul rendezésre, mert a fegyelmezetlenség
    rendszer-hiba, nem pech.

    Visszatérés csapatonként (a BÜNTETETT oldal): {"suspensions"
    (poszthoz kötött), "roles": {poszt: kiállítás}, "main_role",
    "share_pct", "verdict"} — az ítélet None, ha nincs meg a
    SUP_MIN_SUSP, vagy egyik poszt sem éri el a SUP_SHARE_PCT-t.
    """
    from .roles import estimate_positions

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    susp = suspended_players(match, config)

    out: dict = {side: {"suspensions": 0, "roles": {},
                        "main_role": None, "share_pct": None,
                        "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in susp[side]:
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["suspensions"])
            rec["suspensions"] += row["suspensions"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["suspensions"] >= SUP_MIN_SUSP:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["suspensions"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= SUP_SHARE_PCT:
                rec["verdict"] = (
                    f"a kétperceik a(z) {poszt} posztra járnak "
                    f"({share:.0f}%, {rec['suspensions']} "
                    "kiállításból) — a meccs elején oda kell vezetni "
                    "a játékot: az első két perc után az az ember "
                    "vagy hiányzik, vagy fékezve véd")
    return out


# Kétperc-gyűjtők: ennyi kiállítástól nevezünk meg embert (a
# harmadik kétperc már kizárás — ezért éles a második).
STC_MIN_SUSP = 2


def suspension_collectors(match: Match,
                          config: Optional[TacticsConfig] = None
                          ) -> dict:
    """Kétperc-gyűjtők: KI ül ki náluk a legtöbbször.

    A kiülő-poszt (suspended_roles) a POSZTOT nevezi meg — ez az
    EMBERT: a felismert kiállításokat a kiülő játékos nevéhez
    összegzi.

    Edzőileg ez a szabályok adta erőforrás. Ellenük: akinél már két
    kétperc van, egy lépésre áll a kizárástól — rá kell vinni a
    játékot (betörés az ő sávjába, elzárás rá), mert vagy fékezve
    véd, vagy elmegy a meccs hátralévő részére. Saját csapatra: ha a
    kétperceink egy emberre gyűlnek, az nem pech, hanem rendszer-
    hiba — a mögötte lévő besegítés hiányzik, vagy a párharcait
    későn kezdi.

    Visszatérés csapatonként (a BÜNTETETT oldal): {"suspensions",
    "players": [{"player_id", "jersey", "suspensions"}], "top"} — a
    "top" az első játékos, ha legalább STC_MIN_SUSP kiállítása van,
    különben None.
    """
    config = config or TacticsConfig()
    susp = suspended_players(match, config)

    jersey: dict = {}
    for f in match.frames:
        for p in f.players:
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": r["player_id"],
                 "jersey": jersey.get(r["player_id"]),
                 "suspensions": r["suspensions"]}
                for r in sorted(susp[side],
                                key=lambda r: -r["suspensions"])]
        top = (rows[0]
               if rows and rows[0]["suspensions"] >= STC_MIN_SUSP
               else None)
        out[side] = {"suspensions": sum(r["suspensions"] for r in rows),
                     "players": rows, "top": top}
    return out


# Hátrány-támadás: ennyi emberhátrányban töltött másodperctől ítélünk,
# és ennyi gól/perc eltérés választja el a "veszélyes" hátrányos
# támadást a "megbénuló"-tól.
SHATK_MIN_S = 90.0
SHATK_DROP_PER_MIN = 0.15


def shorthanded_attack(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Hátrány-támadás: mit támadnak a kiállítás alatt.

    Az emberelőny-hatékonyság (powerplay_efficiency) a kiállítás
    NYERTES oldalát nézi, a hátrányban leadott lövéseket kifejezetten
    kihagyja — ez a hiányzó fele: a kiállított csapat MAGA mennyit
    támad egy emberrel kevesebben. Aki hátrányban is gólt szerez
    (labdát tart, lerohan), az kihúzza a két percet: ellene az
    emberelőnyt türelmesen kell végigjátszani, kockázatos lövés
    nélkül. Aki megbénul, annál a kiállítás azonnali gólkülönbség —
    saját olvasatban a hátrányos labdatartás az edzés-téma.

    Visszatérés csapatonként: {"sh_seconds", "sh_shots", "sh_goals",
    "sh_per_min", "eq_seconds", "eq_goals", "eq_per_min",
    "gap_per_min", "verdict"} — az ütemek és a verdict None, ha kevés
    (SHATK_MIN_S alatti) a hátrányban töltött idő; a verdict
    "veszélyes" / "megbénul" / None.
    """
    from .event_detection import detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    if not match.frames:
        return {s: {"sh_seconds": 0.0, "sh_shots": 0, "sh_goals": 0,
                    "sh_per_min": None, "eq_seconds": 0.0,
                    "eq_goals": 0, "eq_per_min": None,
                    "gap_per_min": None, "verdict": None}
                for s in ("home", "away")}
    windows = detect_powerplay(match)
    total_s = (match.frames[-1].t - match.frames[0].t) / fps
    # Egyenlő létszám: a teljes idő mínusz MINDEN kiállítás-szakasz
    # (akármelyik csapaté) — ez a közös viszonyítási alap.
    pp_total_s = sum(w["duration_s"] for w in windows)
    eq_seconds = max(0.0, total_s - pp_total_s)

    def _down_at(t: int) -> Optional[str]:
        for w in windows:
            if w["start_frame"] <= t <= w["end_frame"]:
                return w["team_down"]
        return None

    counts = {s: {"sh_seconds": 0.0, "sh_shots": 0, "sh_goals": 0,
                  "eq_goals": 0}
              for s in ("home", "away")}
    for w in windows:
        counts[w["team_down"]]["sh_seconds"] += w["duration_s"]
    for e in detect_shots(match, config):
        outcome = (e.detail or {}).get("outcome")
        if outcome not in ("goal", "save", "miss"):
            continue
        side = e.team.value
        down = _down_at(e.t)
        if down == side:
            counts[side]["sh_shots"] += 1
            if outcome == "goal":
                counts[side]["sh_goals"] += 1
        elif down is None and outcome == "goal":
            counts[side]["eq_goals"] += 1
    out = {}
    for side in ("home", "away"):
        rec = counts[side]
        r = {"sh_seconds": round(rec["sh_seconds"], 1),
             "sh_shots": rec["sh_shots"], "sh_goals": rec["sh_goals"],
             "sh_per_min": None, "eq_seconds": round(eq_seconds, 1),
             "eq_goals": rec["eq_goals"], "eq_per_min": None,
             "gap_per_min": None, "verdict": None}
        if rec["sh_seconds"] >= SHATK_MIN_S and eq_seconds > 0:
            sh_pm = 60.0 * rec["sh_goals"] / rec["sh_seconds"]
            eq_pm = 60.0 * rec["eq_goals"] / eq_seconds
            r["sh_per_min"] = round(sh_pm, 2)
            r["eq_per_min"] = round(eq_pm, 2)
            r["gap_per_min"] = round(sh_pm - eq_pm, 2)
            if eq_pm - sh_pm >= SHATK_DROP_PER_MIN:
                r["verdict"] = "megbénul"
            else:
                r["verdict"] = "veszélyes"
        out[side] = r
    return out


# Emberelőny-védekezés: ennyi emberelőnyben töltött másodperctől
# ítélünk, és ennyi kapott gól/perc eltérés a "szivárog" /
# "fegyelmezett" küszöb.
PPDEF_MIN_S = 90.0
PPDEF_RISE_PER_MIN = 0.2


def powerplay_defense(match: Match,
                      config: Optional[TacticsConfig] = None) -> dict:
    """Emberelőny-védekezés: emberelőnyben is kapnak-e gólt.

    Az emberelőny-hatékonyság (powerplay_efficiency) azt méri, mit
    TÁMADNAK a kiállítás alatt — ez azt, mit VÉDEKEZNEK közben:
    egy emberrel többen is kaphatnak lerohanás-gólt, ha a
    befejezéseik után nem rendeződnek vissza. A perces kapott
    gól-ütemet hasonlítja az egyenlő létszámúhoz. Aki előnyben is
    szivárog, annál a kiállítás nem büntetés: hátrányban is vállalni
    kell a lerohanást ellene — aki fegyelmezett, azzal szemben
    hátrányban a labdatartás a reális cél.

    Visszatérés csapatonként (az ELŐNYBEN lévő oldal): {"pp_seconds",
    "pp_conceded", "pp_per_min", "eq_seconds", "eq_conceded",
    "eq_per_min", "gap_per_min", "verdict"} — az ütemek és a verdict
    None, ha kevés (PPDEF_MIN_S alatti) az emberelőnyben töltött idő;
    a verdict "szivárog" / "fegyelmezett" / None.
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    if not match.frames:
        return {s: {"pp_seconds": 0.0, "pp_conceded": 0,
                    "pp_per_min": None, "eq_seconds": 0.0,
                    "eq_conceded": 0, "eq_per_min": None,
                    "gap_per_min": None, "verdict": None}
                for s in ("home", "away")}
    windows = detect_powerplay(match)
    total_s = (match.frames[-1].t - match.frames[0].t) / fps
    eq_seconds = max(0.0, total_s - sum(w["duration_s"] for w in windows))

    def _down_at(t: int) -> Optional[str]:
        for w in windows:
            if w["start_frame"] <= t <= w["end_frame"]:
                return w["team_down"]
        return None

    counts = {s: {"pp_seconds": 0.0, "pp_conceded": 0, "eq_conceded": 0}
              for s in ("home", "away")}
    for w in windows:
        up = "away" if w["team_down"] == "home" else "home"
        counts[up]["pp_seconds"] += w["duration_s"]
    for e in detect_shots(match, config):
        if e.type != EventType.GOAL:
            continue
        scorer = e.team.value
        conceder = "away" if scorer == "home" else "home"
        down = _down_at(e.t)
        if down == scorer:
            # A hátrányban lévő csapat szerzett gólt: ezt az
            # EMBERELŐNYBEN lévő védekezés kapta.
            counts[conceder]["pp_conceded"] += 1
        elif down is None:
            counts[conceder]["eq_conceded"] += 1
    out = {}
    for side in ("home", "away"):
        rec = counts[side]
        r = {"pp_seconds": round(rec["pp_seconds"], 1),
             "pp_conceded": rec["pp_conceded"], "pp_per_min": None,
             "eq_seconds": round(eq_seconds, 1),
             "eq_conceded": rec["eq_conceded"], "eq_per_min": None,
             "gap_per_min": None, "verdict": None}
        if rec["pp_seconds"] >= PPDEF_MIN_S and eq_seconds > 0:
            pp_pm = 60.0 * rec["pp_conceded"] / rec["pp_seconds"]
            eq_pm = 60.0 * rec["eq_conceded"] / eq_seconds
            r["pp_per_min"] = round(pp_pm, 2)
            r["eq_per_min"] = round(eq_pm, 2)
            r["gap_per_min"] = round(pp_pm - eq_pm, 2)
            if pp_pm - eq_pm >= PPDEF_RISE_PER_MIN:
                r["verdict"] = "szivárog"
            elif eq_pm - pp_pm >= PPDEF_RISE_PER_MIN:
                r["verdict"] = "fegyelmezett"
        out[side] = r
    return out


# Hetes-okozó: ennyi hetes kell egy védő megbélyegzéséhez (a
# heurisztika zaja miatt egy eset még nem minta).
SEVEN_CONCEDER_MIN = 2


def seven_meter_conceders(match: Match,
                          config: Optional[TacticsConfig] = None) -> dict:
    """Hetes-okozó védők: KINÉL szakad meg a védekezés hetessel.

    A hetes-kiharcolók (seven_meter_earners) a támadó oldalról nézik,
    kit rántanak le — ez a védő oldali párja: a hetes-jel előtt a
    kiharcolóhoz legközelebb álló (nem kapus) VÉDŐ kapja a
    jóváírást. Heurisztika, de magyarázható: a befejezésbe érkező
    embert az a védő állítja meg szabálytalanul, aki mellette van.

    Edzőileg: aki két-három hetest is okoz, annak a lábmunkájával van
    baj (kézzel áll meg a betörést) — vele szemben a betörés
    kifizetődő, a saját edzésnek pedig kész témája van.

    Visszatérés a VÉDEKEZŐ csapat oldalán: {"home"/"away":
    {"players": [{"player_id", "jersey", "conceded"}], "top":
    {"player_id", "jersey", "conceded"} | None}} — a "top" akkor van kitöltve, ha a vezető védő
    legalább SEVEN_CONCEDER_MIN hetest okozott.
    """
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    frames_by_t = {f.t: f for f in match.frames}
    tally: dict = {"home": {}, "away": {}}
    jersey: dict = {}
    for sm in detect_seven_meters(match, config):
        t_prev = sm["t"] - round(SEVEN_EARNER_LOOKBACK_S * fps)
        fr = None
        for dt in range(0, round(fps)):
            fr = frames_by_t.get(t_prev - dt) or frames_by_t.get(t_prev + dt)
            if fr is not None and fr.players:
                break
        if fr is None or not fr.players:
            continue
        for p in fr.players:
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)
        # A kiharcoló: a támadott kapuhoz legközelebbi támadó.
        earner = None
        for p in fr.players:
            if p.team.value != sm["team"] or p.role == "kapus":
                continue
            d = abs(p.x - sm["goal_x"])
            if earner is None or d < earner[1]:
                earner = (p, d)
        if earner is None:
            continue
        # Az okozó: a kiharcolóhoz legközelebbi mezőnyvédő.
        defending = "away" if sm["team"] == "home" else "home"
        best = None
        for p in fr.players:
            if p.team.value != defending or p.role == "kapus":
                continue
            d = ((p.x - earner[0].x) ** 2 + (p.y - earner[0].y) ** 2) ** 0.5
            if best is None or d < best[1]:
                best = (p.track_id, d)
        if best is not None:
            tally[defending][best[0]] = tally[defending].get(best[0], 0) + 1

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "conceded": n}
                for pid, n in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1])]
        top = (rows[0] if rows and rows[0]["conceded"] >= SEVEN_CONCEDER_MIN
               else None)
        out[side] = {"players": rows, "top": top}
    return out


# Hetes-okozó poszt: ennyi poszthoz kötött okozott hetes kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy a heteseik
# egy sávban szakadnak be.
SVR_MIN_SEVENS = 3
SVR_SHARE_PCT = 60.0


def seven_conceder_roles(match: Match,
                         config: Optional[TacticsConfig] = None) -> dict:
    """Hetes-okozó poszt: MELYIK SÁVJUK szakad be hetessel.

    A hetes-okozó védők rétege az embert nevezi meg — ez a posztot:
    az okozott heteseket az okozó védő posztjához írja. Így akkor is
    látszik a minta, ha a nevek meccsről meccsre cserélődnek.

    Edzőileg ez a betörés-térkép: ha a heteseik rendre ugyanazon a
    poszton szakadnak be, az a sáv kézzel véd a lábmunka helyett —
    oda ÉRDEMES betörést vezetni, mert vagy gól lesz belőle, vagy
    hetes (és idővel kiállítás). Ha a hetes-okozásuk szórt, nincs
    kitüntetett sáv — a betörést a mozgó fal réseihez kell igazítani.

    Visszatérés csapatonként (a VÉDEKEZŐ oldal): {"sevens" (poszthoz
    kötött okozott hetes), "roles": {poszt: hetes}, "main_role",
    "share_pct", "verdict"} — az ítélet None, ha nincs meg az
    SVR_MIN_SEVENS, vagy egyik poszt sem éri el az SVR_SHARE_PCT-t.
    """
    from .roles import estimate_positions

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    conc = seven_meter_conceders(match, config)

    out: dict = {side: {"sevens": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in conc[side]["players"]:
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["conceded"])
            rec["sevens"] += row["conceded"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["sevens"] >= SVR_MIN_SEVENS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["sevens"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= SVR_SHARE_PCT:
                rec["verdict"] = (
                    f"a heteseik a(z) {poszt} poszton szakadnak be "
                    f"({share:.0f}%, {rec['sevens']} okozott hetesből)"
                    " — abba a sávba érdemes betörést vezetni: kézzel"
                    " véd, gól vagy hetes lesz belőle")
    return out


# Emberhátrány-túlélés: ennyi hátrányban töltött másodperc kell az
# ítélethez, és a KÉT PERCRE vetített kapott gól e küszöbei döntik
# el, beszakadnak-e vagy állják a hátrányt.
SHS_MIN_S = 90.0
SHS_BAD_PER_2MIN = 1.5
SHS_GOOD_PER_2MIN = 0.5


def shorthanded_survival(match: Match,
                         config: Optional[TacticsConfig] = None
                         ) -> dict:
    """Emberhátrány-túlélés: MIT ÉR ellenük az emberelőny.

    Az emberelőny-hozam (powerplay_yield) a NYERTES oldalt nézi — ez
    a BÜNTETETT oldalt: a hátrányban töltött időre vetíti a
    hátrányban kapott gólokat (gól / két perc hátrány).

    Edzőileg ez az emberelőny-terv címzettje. Ha hátrányban
    beszakadnak, a kiállításukat végig kell büntetni: türelmes,
    zárt emberelőny-figurák, semmi kapkodás — az idő nekik fáj. Ha
    hátrányban is állnak, a kettős fölény ellenük keveset ér: az
    emberelőnyben is az egyenlő létszámú fegyverek (1v1, betörés)
    dolgoznak, és a kiállításuk alatt a gyors gól többet ér, mint a
    hosszú járatás. Saját csapatra: a hátrány-védekezés (4+1 fal,
    labdatartás) edzés-téma.

    Visszatérés csapatonként (a BÜNTETETT oldal): {"sh_seconds",
    "sh_conceded", "per_2min", "verdict"} — a per_2min/verdict None,
    ha kevés (SHS_MIN_S alatti) a hátrányban töltött idő.
    """
    config = config or TacticsConfig()
    eff = powerplay_efficiency(match, config)

    out: dict = {}
    for side in ("home", "away"):
        src = (eff or {}).get(side, {})
        rec = {"sh_seconds": round(src.get("sh_seconds", 0.0), 1),
               "sh_conceded": int(src.get("sh_conceded", 0)),
               "per_2min": None, "verdict": None}
        if rec["sh_seconds"] >= SHS_MIN_S:
            per2 = 120.0 * rec["sh_conceded"] / rec["sh_seconds"]
            rec["per_2min"] = round(per2, 2)
            if per2 >= SHS_BAD_PER_2MIN:
                rec["verdict"] = (
                    f"hátrányban beszakadnak ({rec['per_2min']:.1f} "
                    f"kapott gól két percenként, {rec['sh_seconds']:.0f}"
                    " mp hátrányból) — a kiállításukat végig kell "
                    "büntetni: türelmes, zárt emberelőny-figurák, az "
                    "idő nekik fáj")
            elif per2 <= SHS_GOOD_PER_2MIN:
                rec["verdict"] = (
                    f"hátrányban is állnak ({rec['per_2min']:.1f} "
                    "kapott gól két percenként) — a kettős fölény "
                    "ellenük keveset ér: emberelőnyben is az 1v1 és "
                    "a betörés dolgozik, és a gyors gól többet ér a "
                    "hosszú járatásnál")
        out[side] = rec
    return out


# Emberelőny-hozam: sávonként ennyi kaputra tartó lövés kell az
# ítélethez, és ekkora (százalékpontos) különbség számít érdeminek.
PPY_MIN_SHOTS = 4
PPY_GAP_PP = 15.0


def powerplay_yield(match: Match,
                    config: Optional[TacticsConfig] = None) -> dict:
    """Emberelőny-hozam: MEGBÜNTETIK-E a kiállítást.

    Az emberelőny-hatékonyság (powerplay_efficiency) a nyers
    számokat adja — ez az ÍTÉLETET: összeveti a kaputra tartó
    lövéseik gólarányát emberelőnyben és egyenlő létszámnál.

    Edzőileg ez rangsorolja a fegyelmet. Ha emberelőnyben érdemben
    jobban fejeznek be, ellenük a kétperc a legdrágább hiba: a falnak
    lábbal kell védekeznie, a taktikai szabálytalanság tilos, és a
    kiállítás utáni percet külön kell megbeszélni. Ha emberelőnyben
    sem jobbak (vagy rosszabbak), a két perc ellenük olcsó — a
    szükséges taktikai megállítás vállalható. Saját csapatra: az
    emberelőny-játékunk hozama mérhető, nem érzés kérdése.

    Visszatérés csapatonként: {"pp_shots", "pp_goals", "eq_shots",
    "eq_goals", "pp_pct", "eq_pct", "gap_pp", "verdict"} — a
    pct/gap/verdict None, ha nem volt kiállítás, vagy valamelyik
    sávban kevés (PPY_MIN_SHOTS alatti) a kaputra tartó lövés.
    """
    config = config or TacticsConfig()
    empty = {"pp_shots": 0, "pp_goals": 0, "eq_shots": 0,
             "eq_goals": 0, "pp_pct": None, "eq_pct": None,
             "gap_pp": None, "verdict": None}
    out = {side: dict(empty) for side in ("home", "away")}

    eff = powerplay_efficiency(match, config)
    if not eff:
        return out

    for side in ("home", "away"):
        rec = out[side]
        src = eff.get(side, {})
        rec["pp_shots"] = src.get("pp_shots", 0)
        rec["pp_goals"] = src.get("pp_goals", 0)
        rec["eq_shots"] = src.get("eq_shots", 0)
        rec["eq_goals"] = src.get("eq_goals", 0)
        if (rec["pp_shots"] >= PPY_MIN_SHOTS
                and rec["eq_shots"] >= PPY_MIN_SHOTS):
            pp = 100.0 * rec["pp_goals"] / rec["pp_shots"]
            eq = 100.0 * rec["eq_goals"] / rec["eq_shots"]
            rec["pp_pct"] = round(pp, 1)
            rec["eq_pct"] = round(eq, 1)
            rec["gap_pp"] = round(pp - eq, 1)
            if pp - eq >= PPY_GAP_PP:
                rec["verdict"] = (
                    f"megbüntetik a kiállítást ({pp:.0f}% "
                    f"emberelőnyben, {eq:.0f}% egyenlő létszámnál) — "
                    "ellenük a kétperc a legdrágább hiba: a fal "
                    "lábbal védekezzen, taktikai szabálytalanság "
                    "nincs")
            elif eq - pp >= PPY_GAP_PP:
                rec["verdict"] = (
                    f"nem büntetik a kiállítást ({pp:.0f}% "
                    f"emberelőnyben, {eq:.0f}% egyenlő létszámnál) — "
                    "a két perc ellenük olcsó: a szükséges taktikai "
                    "megállítás vállalható")
    return out


# Emberelőny-tempó: ennyi mért támadás kell emberelőnyben és egyenlő
# létszámnál, és ekkora (másodperces) eltérés számít érdemi jelnek.
PP_PACE_MIN_PP = 3
PP_PACE_MIN_EQ = 5
PP_PACE_GAP_S = 5.0


def powerplay_pace(match: Match,
                   config: Optional[TacticsConfig] = None) -> dict:
    """Emberelőny-tempó: ELNYÚJTJÁK vagy KAPKODJÁK az emberelőnyt.

    Az emberelőny-hatékonyság (powerplay_efficiency) azt mondja meg,
    mennyi gólt hoznak a kiállításokból — ez azt, HOGYAN játsszák: a
    támadás-szakaszok hosszát vetjük össze emberelőnyben és egyenlő
    létszámnál.

    Edzőileg: aki emberelőnyben érdemben elnyújtja a támadást, az a
    biztos helyzetre vár — ellene türelmes, zárt fal kell, mert a
    kapkodó kilépés pont neki dolgozik; aki emberelőnyben is gyorsan
    lő, annál a két perc alatt nagy a hibaszázalék: ott az agresszív,
    kilépő védekezés kifizet.

    Visszatérés csapatonként: {"pp_attacks", "pp_avg_s", "eq_attacks",
    "eq_avg_s", "gap_s", "verdict"} — az átlagok és a gap None, ha
    kevés a minta (PP_PACE_MIN_PP / PP_PACE_MIN_EQ); a verdict
    "elnyújtják emberelőnyben" / "kapkodnak emberelőnyben" / None.
    """
    from .setplays import segment_attacks

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    windows = detect_powerplay(match)

    def _down_at(t: int) -> Optional[str]:
        for w in windows:
            if w["start_frame"] <= t <= w["end_frame"]:
                return w["team_down"]
        return None

    acc = {side: {"pp": [0, 0.0], "eq": [0, 0.0]}
           for side in ("home", "away")}
    for seq in segment_attacks(match, config):
        side = seq.team.value
        down = _down_at(seq.start_t)
        if down == side:
            continue  # emberhátrányban támadnak: külön kép (shorthanded)
        key = "pp" if down is not None else "eq"
        dur = (seq.end_t - seq.start_t + 1) / fps
        acc[side][key][0] += 1
        acc[side][key][1] += dur

    out: dict = {}
    for side in ("home", "away"):
        pp_n, pp_s = acc[side]["pp"]
        eq_n, eq_s = acc[side]["eq"]
        rec = {"pp_attacks": pp_n, "eq_attacks": eq_n,
               "pp_avg_s": None, "eq_avg_s": None, "gap_s": None,
               "verdict": None}
        if pp_n >= PP_PACE_MIN_PP and eq_n >= PP_PACE_MIN_EQ:
            rec["pp_avg_s"] = round(pp_s / pp_n, 1)
            rec["eq_avg_s"] = round(eq_s / eq_n, 1)
            rec["gap_s"] = round(rec["pp_avg_s"] - rec["eq_avg_s"], 1)
            if rec["gap_s"] >= PP_PACE_GAP_S:
                rec["verdict"] = "elnyújtják emberelőnyben"
            elif rec["gap_s"] <= -PP_PACE_GAP_S:
                rec["verdict"] = "kapkodnak emberelőnyben"
        out[side] = rec
    return out


# Emberhátrány-forma: ennyi mért kocka kell az ítélethez, és e feletti
# részarány jelenti, hogy egy formát játszanak öt emberrel.
SH_SHAPE_MIN_FRAMES = 100
SH_SHAPE_MAIN_PCT = 60.0


def shorthanded_shape(match: Match,
                      config: Optional[TacticsConfig] = None) -> dict:
    """Emberhátrány-forma: MIT JÁTSZANAK öt emberrel.

    Az emberhátrány-támadás (shorthanded_attack) azt mondja meg, mire
    mennek támadásban a két perc alatt, az emberelőny-védekezés
    (powerplay_defense) azt, mennyit kapnak — ez azt, MILYEN FALAT
    húznak: a kiállítás-ablakokban a hátrányban lévő csapat formáját
    olvassuk ki kockánként, hátsó-előretolt bontásban (5-0, 4-1,
    3-2).

    Edzőileg: az 5-0 mögött az átlövés szabad — kívülről kell lőni és
    a szélsőket etetni; a 4-1 (előretolt védő) ellen az oldalváltás és
    a beállós játék a válasz, mert az előretolt ember mögött nyílik a
    tér.

    Visszatérés csapatonként (a HÁTRÁNYBAN lévő oldal): {"frames",
    "labels": {forma: kocka}, "main", "main_pct"} — a main/main_pct
    None SH_SHAPE_MIN_FRAMES alatt vagy SH_SHAPE_MAIN_PCT alatti
    többségnél.
    """
    from .tactics import TacticsConfig, detect_formation

    config = config or TacticsConfig()
    windows = detect_powerplay(match)
    tally: dict = {"home": {}, "away": {}}
    for f in match.frames:
        for w in windows:
            if not (w["start_frame"] <= f.t <= w["end_frame"]):
                continue
            down = w["team_down"]
            team = Team.HOME if down == "home" else Team.AWAY
            form = detect_formation(f, team, config)
            # Öt (vagy kevesebb) mezőnyvédő a hátrány jele; ennél
            # többnél a címke nem az emberhátrány-falat írja le.
            if form.defenders < 3 or form.defenders > 5:
                continue
            # Emberhátrányban a szokásos név hátsó-előretolt bontású
            # (5-0, 4-1, 3-2); a hatfős címkéző itt leíró nevet adna.
            label = f"{form.back}-{form.mid + form.high}"
            tally[down][label] = tally[down].get(label, 0) + 1
            break

    out: dict = {}
    for side in ("home", "away"):
        labels = dict(sorted(tally[side].items(), key=lambda kv: -kv[1]))
        n = sum(labels.values())
        rec = {"frames": n, "labels": labels, "main": None,
               "main_pct": None}
        if n >= SH_SHAPE_MIN_FRAMES and labels:
            main, cnt = next(iter(labels.items()))
            pct = 100.0 * cnt / n
            if pct >= SH_SHAPE_MAIN_PCT:
                rec["main"] = main
                rec["main_pct"] = round(pct, 1)
        out[side] = rec
    return out


# Kapus-hetesvédés irány szerint: irányonként ennyi kapura tartó hetes
# kell az ítélethez, és ekkora (százalékpontos) különbség számít
# érdemi oldal-eltérésnek.
GK7_DIR_MIN = 3
GK7_DIR_GAP_PP = 25.0


def gk_seven_directions(match: Match,
                        config: Optional[TacticsConfig] = None) -> dict:
    """Kapus-hetesvédés irány szerint: MELYIK SAROKBA menő heteseket
    fogja a kapusuk.

    A hetes-védés (seven_meter_defense) azt mondja meg, MENNYIT fog a
    kapusuk — ez azt, MERRE: a hetes-kimenetelek (seven_meter_outcomes)
    irány-mezőjét (bal / közép / jobb, a DOBÓ szemszögéből) használjuk,
    és irányonként számolunk védési arányt.

    Edzőileg: a hetes-lövőtöknek kész terve legyen — abba a sarokba
    kell lőni, ahol a kapusuk a leggyengébb, és nem szabad "érzésre"
    dönteni a vonalnál.

    Visszatérés csapatonként (a VÉDŐ oldal = akinek a kapusa a
    kapuban van): {"bal"/"közép"/"jobb": {"faced", "saved",
    "save_pct"}, "faced", "weak_dir"} — a weak_dir a legrosszabb
    védési arányú irány, ha van legalább GK7_DIR_MIN kapura tartó
    hetes onnan, és a védés-aránya legalább GK7_DIR_GAP_PP
    százalékponttal az összesített alatt van.
    """
    config = config or TacticsConfig()
    out: dict = {}
    tally = {side: {d: {"faced": 0, "saved": 0}
                    for d in ("bal", "közép", "jobb")}
             for side in ("home", "away")}
    for sm in seven_meter_outcomes(match, config):
        if sm["outcome"] not in ("gól", "védés") or sm["irany"] is None:
            continue  # kihagyott/ismeretlen: a kapushoz nem mérhető
        defending = "away" if sm["team"] == "home" else "home"
        rec = tally[defending][sm["irany"]]
        rec["faced"] += 1
        if sm["outcome"] == "védés":
            rec["saved"] += 1

    for side in ("home", "away"):
        dirs = tally[side]
        faced = sum(r["faced"] for r in dirs.values())
        saved = sum(r["saved"] for r in dirs.values())
        for r in dirs.values():
            r["save_pct"] = (round(100.0 * r["saved"] / r["faced"], 1)
                             if r["faced"] else None)
        weak = None
        cand = [(d, r) for d, r in dirs.items()
                if r["faced"] >= GK7_DIR_MIN]
        if cand and faced:
            avg = 100.0 * saved / faced
            d, r = min(cand, key=lambda kv: kv[1]["save_pct"])
            if avg - r["save_pct"] >= GK7_DIR_GAP_PP:
                weak = {"irany": d, "save_pct": r["save_pct"],
                        "faced": r["faced"]}
        out[side] = {**dirs, "faced": faced, "weak_dir": weak}
    return out


# Emberelőny-lövők: ennyi emberelőnyben leadott lövéstől emeljük ki az
# embert (ennyi alatt a kép még véletlen).
PPS_MIN_SHOTS = 3


def powerplay_shooters(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Emberelőny-lövők: KI FEJEZ BE a két perc alatt.

    Az emberelőny-hatékonyság (powerplay_efficiency) azt mondja meg,
    mennyi gólt hoznak a kiállításokból, az emberelőny-tempó
    (powerplay_pace) azt, hogyan játsszák — ez azt, KIRE megy a
    befejezés: a kiállítás-ablakokban leadott lövéseket a lövőhöz
    írjuk.

    Edzőileg: emberhátrányban a fal nem érhet mindenhová, ezért a
    befejezőjükre kell rendezni — az ő oldalán kell a kettőzés vagy a
    kilépés, a többieket pedig rá lehet engedni.

    Visszatérés csapatonként: {"shots", "players": [{"player_id",
    "jersey", "shots", "goals"}], "top"} — a lista lövésszám szerint
    csökkenő; a "top" az első játékos, ha legalább PPS_MIN_SHOTS
    emberelőnyben leadott lövése van.
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    windows = detect_powerplay(match)
    if not windows:
        return {side: {"shots": 0, "players": [], "top": None}
                for side in ("home", "away")}

    def _down_at(t: int) -> Optional[str]:
        for w in windows:
            if w["start_frame"] <= t <= w["end_frame"]:
                return w["team_down"]
        return None

    jersey: dict = {}
    for fr in match.frames:
        for p in fr.players:
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)

    tally: dict = {"home": {}, "away": {}}
    for e in detect_shots(match, config):
        if e.type not in (EventType.SHOT, EventType.GOAL) \
                or e.player_id is None:
            continue
        side = e.team.value
        down = _down_at(e.t)
        if down is None or down == side:
            continue  # egyenlő létszám vagy emberhátrány: nem ide tartozik
        rec = tally[side].setdefault(e.player_id,
                                     {"shots": 0, "goals": 0})
        rec["shots"] += 1
        if e.type == EventType.GOAL:
            rec["goals"] += 1

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "shots": r["shots"], "goals": r["goals"]}
                for pid, r in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1]["shots"])]
        top = (rows[0] if rows and rows[0]["shots"] >= PPS_MIN_SHOTS
               else None)
        out[side] = {"shots": sum(r["shots"] for r in rows),
                     "players": rows, "top": top}
    return out


# Emberhátrány-lövők: ennyi emberhátrányban leadott lövéstől emeljük ki
# az embert (a két perc alatt kevés a lövés, de egy eset nem minta).
SHS_MIN_SHOTS = 2


def shorthanded_shooters(match: Match,
                         config: Optional[TacticsConfig] = None) -> dict:
    """Emberhátrány-lövők: KI VÁLLALJA a befejezést öt emberrel.

    Az emberhátrány-támadás (shorthanded_attack) azt mondja meg,
    mennyit érnek a két perc alatt, az emberhátrány-forma
    (shorthanded_shape) azt, milyen falat húznak — ez azt, KI LŐ
    ilyenkor: a kiállítás-ablakokban a HÁTRÁNYBAN lévő csapat
    lövéseit a lövőhöz írjuk.

    Edzőileg: emberelőnyben az ő befejezőjük a kontra-fenyegetés — rá
    kell hagyni a legkevesebb teret, és a mi emberelőnyös
    támadásunkban az ő oldalán kell a labdabiztonság, mert onnan indul
    az ellentámadásuk.

    Visszatérés csapatonként: {"shots", "players": [{"player_id",
    "jersey", "shots", "goals"}], "top"} — a "top" az első játékos, ha
    legalább SHS_MIN_SHOTS emberhátrányban leadott lövése van.
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    windows = detect_powerplay(match)
    if not windows:
        return {side: {"shots": 0, "players": [], "top": None}
                for side in ("home", "away")}

    def _down_at(t: int) -> Optional[str]:
        for w in windows:
            if w["start_frame"] <= t <= w["end_frame"]:
                return w["team_down"]
        return None

    jersey: dict = {}
    for fr in match.frames:
        for p in fr.players:
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)

    tally: dict = {"home": {}, "away": {}}
    for e in detect_shots(match, config):
        if e.type not in (EventType.SHOT, EventType.GOAL) \
                or e.player_id is None:
            continue
        side = e.team.value
        if _down_at(e.t) != side:
            continue  # csak a hátrányban lévő csapat lövései
        rec = tally[side].setdefault(e.player_id,
                                     {"shots": 0, "goals": 0})
        rec["shots"] += 1
        if e.type == EventType.GOAL:
            rec["goals"] += 1

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "shots": r["shots"], "goals": r["goals"]}
                for pid, r in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1]["shots"])]
        top = (rows[0] if rows and rows[0]["shots"] >= SHS_MIN_SHOTS
               else None)
        out[side] = {"shots": sum(r["shots"] for r in rows),
                     "players": rows, "top": top}
    return out


# Hetes-kiharcolás poszt szerint: ennyi poszthoz kötött hetestől
# ítélünk, és e feletti részarány jelenti, hogy egy posztról jönnek.
SER_MIN_SEVENS = 3
SER_SHARE = 50.0


def seven_earner_roles(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Hetes-kiharcolás poszt szerint: MELYIK POSZTRÓL rántják le őket.

    A hetes-kiharcolók (seven_meter_earners) azt mondják meg, KIT
    rántanak le — ez azt, MILYEN POSZTON: a kiharcolókat a
    poszt-becsléshez (estimate_positions) kötjük.

    Edzőileg: ha a hetesek zöme a szélsőikről jön, a szélső-védekezésnél
    tilos a kéz — csak lábbal, testtel szabad terelni; ha a beállótól,
    az elé állást kell gyakorolni, mert a beálló-fogás hetest ér.

    Visszatérés csapatonként: {"sevens", "roles": {poszt: darab},
    "top": {"poszt", "count", "share_pct"} | None} — a "top" akkor van
    kitöltve, ha legalább SER_MIN_SEVENS poszthoz kötött hetes van, a
    vezető poszt részaránya eléri a SER_SHARE-t, és nincs vele
    holtversenyben másik poszt.
    """
    from .roles import estimate_positions

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    out: dict = {side: {"sevens": 0, "roles": {}, "top": None}
                 for side in ("home", "away")}
    earners = seven_meter_earners(match, config)
    for side in ("home", "away"):
        rec = out[side]
        for row in earners.get(side, []):
            info = roles.get(side, {}).get(row["player_id"])
            if info is None:
                continue
            rec["sevens"] += row["earned"]
            poszt = info["poszt"]
            rec["roles"][poszt] = rec["roles"].get(poszt, 0) + row["earned"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        items = list(rec["roles"].items())
        if rec["sevens"] >= SER_MIN_SEVENS and items:
            poszt, n = items[0]
            share = 100.0 * n / rec["sevens"]
            tie = len(items) > 1 and items[1][1] == n
            if share >= SER_SHARE and not tie:
                rec["top"] = {"poszt": poszt, "count": n,
                              "share_pct": round(share, 1)}
    return out


# Hetes-fáradás: legalább ennyi adott hetes kell az ítélethez, és
# ekkora félidők közti többlet jelenti a fáradással (vagy az elején,
# hidegen) adott heteseket.
S7F_MIN_CONCEDED = 4
S7F_GAP = 2


def sevens_fade(match: Match,
                config: Optional[TacticsConfig] = None) -> dict:
    """Hetes-fáradás: MIKOR ADJÁK a heteseket.

    A hetes-adók (seven_meter_conceders) azt mondják meg, KI ellen
    ítélik, a szabálytalanság-fáradás (discipline_fade) a kiállítások
    idejét — ez a hetesekét: a csapat által ADOTT (az ellenfélnek
    megítélt) heteseket félidőnként számoljuk.

    Edzőileg: aki a második félidőben adja a heteseket, az fáradva
    már kézzel véd — ott a szünet után be kell vinni a labdát a
    testre, mert jön az ajándék; aki az elején ad, az hidegen
    kapkod — az első percekben kell a beállóst és a betörést erőltetni.

    Visszatérés csapatonként (az ADÓ oldal): {"fh", "sh", "verdict"}
    — a verdict None, ha nincs felismert szünet vagy kevés a hetes; a
    verdict "a második félidőben adják a heteseket" / "az elején
    adják a heteseket" / None.
    """
    from .halftime import detect_halftime

    out = {side: {"fh": 0, "sh": 0, "verdict": None}
           for side in ("home", "away")}
    ht = detect_halftime(match)
    if ht is None:
        return out

    for ev in detect_seven_meters(match, config):
        conceder = "away" if ev["team"] == "home" else "home"
        rec = out[conceder]
        if ev["t"] <= ht:
            rec["fh"] += 1
        else:
            rec["sh"] += 1

    for side in ("home", "away"):
        rec = out[side]
        total = rec["fh"] + rec["sh"]
        if total >= S7F_MIN_CONCEDED:
            if rec["sh"] - rec["fh"] >= S7F_GAP:
                rec["verdict"] = "a második félidőben adják a heteseket"
            elif rec["fh"] - rec["sh"] >= S7F_GAP:
                rec["verdict"] = "az elején adják a heteseket"
    return out


# Visszaállás-ablak: ennyi másodpercet nézünk a kiállítás letelte után,
# ennyi mért visszaállás kell az ítélethez, és ekkora gólkülönbség
# jelenti a megzavarodó, illetve a feltámadó visszaállást.
PPP_WINDOW_S = 60.0
PPP_MIN_RETURNS = 2
PPP_DIFF = 2


def post_powerplay(match: Match,
                   config: Optional[TacticsConfig] = None) -> dict:
    """Visszaállás: MI TÖRTÉNIK, AMIKOR VISSZAÉR a kiállított ember.

    Az emberelőny-hatékonyság a kiállítás ALATTI játékot méri — ez az
    UTÁNIT: a kiállítás letelte utáni PPP_WINDOW_S másodperc
    gólmérlegét a visszaálló (addig emberhátrányos) csapat
    szemszögéből. A visszaérő ember hidegen jön, a felállás egy
    percig rendezetlen — van, aki ilyenkor esik szét, és van, aki
    pont ilyenkor lendül meg.

    Edzőileg: aki a visszaállásnál megzavarodik, annál a kiállítás
    végére időzített figyelem kell — a lejáró kiállítás a ti
    támadás-jelzésetek; aki feltámad, annál a visszaérés utáni első
    támadást kell mindenáron megfogni, mert lendületet vesznek
    belőle.

    Visszatérés csapatonként (a VISSZAÁLLÓ oldal): {"returns",
    "goals_for", "goals_against", "verdict"} — a verdict None
    PPP_MIN_RETURNS alatt; a verdict "a visszaállásnál megzavarodnak"
    / "a visszaálló emberrel feltámadnak" / None.
    """
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig as _TC

    config = config or _TC()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = round(PPP_WINDOW_S * fps)
    goals = [(e.t, e.team.value) for e in detect_shots(match, config)
             if e.type == EventType.GOAL]

    out = {side: {"returns": 0, "goals_for": 0, "goals_against": 0,
                  "verdict": None} for side in ("home", "away")}
    for w in detect_powerplay(match):
        side = w["team_down"]
        rec = out[side]
        rec["returns"] += 1
        t0 = w["end_frame"]
        for (t, tm) in goals:
            if t0 < t <= t0 + win:
                if tm == side:
                    rec["goals_for"] += 1
                else:
                    rec["goals_against"] += 1

    for side in ("home", "away"):
        rec = out[side]
        if rec["returns"] >= PPP_MIN_RETURNS:
            diff = rec["goals_for"] - rec["goals_against"]
            if diff <= -PPP_DIFF:
                rec["verdict"] = "a visszaállásnál megzavarodnak"
            elif diff >= PPP_DIFF:
                rec["verdict"] = "a visszaálló emberrel feltámadnak"
    return out


# Hetes utáni percek: a hetes-esemény után ennyivel kezdődő és eddig
# tartó ablakban nézzük a további kapott gólokat, ennyi adott hetes
# kell az ítélethez, és ennyi plusz kapott gól jelenti a leragadást.
PSL_SKIP_S = 15.0
PSL_WINDOW_S = 75.0
PSL_MIN_SEVENS = 3
PSL_MIN_EXTRA = 2


def post_seven_lapses(match: Match,
                      config: Optional[TacticsConfig] = None) -> dict:
    """Hetes utáni percek: LERAGADNAK-E az adott hetes után.

    A hetes-rétegek magát a büntetőt mérik — ez az utóhatását: az
    adott (ellenük ítélt) hetes utáni percben nézzük a TOVÁBBI kapott
    gólokat (a hetes-lövés saját ablakát átugorva). A hetes körüli
    leállás sok csapat védekezés-ritmusát megtöri — reklamálás,
    átrendeződés, és a következő támadás máris bent van.

    Edzőileg: aki a hetes után is kap rá, annál az ellenük megítélt
    hetes duplán ér — a hetes utáni támadást is kész figurával kell
    megjátszani; a saját oldalon a hetes utáni első védekezés hangos
    újrarendezést kap, mielőtt a játék újraindul.

    Visszatérés csapatonként (az ADÓ oldal): {"sevens_against",
    "extra_conceded", "verdict"} — a verdict None PSL_MIN_SEVENS
    alatt; a verdict "a hetes utáni percben is büntetik őket" / None.
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    skip = round(PSL_SKIP_S * fps)
    win = round(PSL_WINDOW_S * fps)
    goals = [(e.t, e.team.value) for e in detect_shots(match, config)
             if e.type == EventType.GOAL]

    out = {side: {"sevens_against": 0, "extra_conceded": 0,
                  "verdict": None} for side in ("home", "away")}
    for ev in detect_seven_meters(match, config):
        conceder = "away" if ev["team"] == "home" else "home"
        rec = out[conceder]
        rec["sevens_against"] += 1
        for (t, tm) in goals:
            if ev["t"] + skip < t <= ev["t"] + win and tm != conceder:
                rec["extra_conceded"] += 1

    for side in ("home", "away"):
        rec = out[side]
        if (rec["sevens_against"] >= PSL_MIN_SEVENS
                and rec["extra_conceded"] >= PSL_MIN_EXTRA):
            rec["verdict"] = "a hetes utáni percben is büntetik őket"
    return out


# Kiállítás-kiharcolás poszt szerint: ennyi poszthoz kötött kiállítás
# kell az ítélethez, és e feletti részarány emeli ki a posztot.
SUR_MIN_SUSP = 3
SUR_SHARE = 50.0


def susp_earner_roles(match: Match,
                      config: Optional[TacticsConfig] = None) -> dict:
    """Kiállítás-kiharcolás poszt szerint: MELYIK POSZTJUK hozza a
    kétperceseket.

    A kiállítás-kiharcolók (suspension_earners) azt mondják meg, KI
    ellen szabálytalankodnak kiállításig — ez azt, MILYEN POSZTON: a
    kiharcolókat a poszt-becsléshez (estimate_positions) kötjük, a
    hetes-posztok (seven_earner_roles) mintájára.

    Edzőileg: ha a kétperceseket az átlövőjük hozza, a betörése ellen
    korán, még a lendület előtt kell lépni — a kései fogás kiállítást
    ér; ha a beállójuk, az elzárás-birkózást kell fegyelmezetten,
    testtel kezelni; ha a szélsőjük, a kifutásnál tilos a kéz.

    Visszatérés csapatonként: {"suspensions", "roles": {poszt:
    darab}, "top": {"poszt", "count", "share_pct"} | None} — a "top"
    akkor van kitöltve, ha legalább SUR_MIN_SUSP poszthoz kötött
    kiállítás van, a vezető poszt részaránya eléri a SUR_SHARE-t, és
    nincs holtverseny.
    """
    from .roles import estimate_positions

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    out: dict = {side: {"suspensions": 0, "roles": {}, "top": None}
                 for side in ("home", "away")}
    earners = suspension_earners(match, config)
    for side in ("home", "away"):
        rec = out[side]
        for row in earners.get(side, []):
            info = roles.get(side, {}).get(row["player_id"])
            if info is None:
                continue
            rec["suspensions"] += row["earned"]
            poszt = info["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["earned"])
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        items = list(rec["roles"].items())
        if rec["suspensions"] >= SUR_MIN_SUSP and items:
            poszt, n = items[0]
            share = 100.0 * n / rec["suspensions"]
            tie = len(items) > 1 and items[1][1] == n
            if share >= SUR_SHARE and not tie:
                rec["top"] = {"poszt": poszt, "count": n,
                              "share_pct": round(share, 1)}
    return out


# Hetes-oldal: ennyi irány-mérhető hetes kell az ítélethez, és ekkora
# részarány számít kiszámíthatónak. A hetes ritka, de a legtisztább
# helyzet a meccsen — három mérhető dobásból kirajzolódó oldal-szokás
# már megéri a kapus-megbeszélés egy mondatát.
SVD_MIN_ATTEMPTS = 3
SVD_SHARE_PCT = 60.0


def seven_shot_directions(match: Match,
                          config: Optional[TacticsConfig] = None) -> dict:
    """Hetes-oldal: MERRE DOBJÁK a heteseiket.

    A hetes-mérleg (seven_meter_summary) azt mondja meg, hogyan
    konvertálnak — ez azt, HOVA: a hetes-kimenetelek irány-jelét
    (bal/közép/jobb a dobó szemszögéből) csapatonként összegezzük.

    Edzőileg ez a kapus-megbeszélés legolcsóbb mondata. A hetes az
    egyetlen helyzet, ahol a kapusnak van ideje DÖNTENI, merre vetődik —
    és a dobók szokás-állatok: nyomás alatt a begyakorolt sarkukat
    keresik. Ha a heteseik jelentős része ugyanarra az oldalra megy, a
    kapus arra az oldalra vetődhet tudatosan; ha szórnak, a kapusnak a
    dobó mozdulatából kell olvasnia, nem előre eldöntenie.

    Visszatérés csapatonként: {"attempts" (irány-mérhető hetes),
    "goals", "dirs": {"bal","közép","jobb"}, "goal_dirs": {...},
    "dominant", "share_pct", "verdict"} — a dominant/share_pct/verdict
    None, ha nincs meg az SVD_MIN_ATTEMPTS, vagy egyik oldal sem éri el
    az SVD_SHARE_PCT részarányt.
    """
    config = config or TacticsConfig()
    out: dict = {side: {"attempts": 0, "goals": 0,
                        "dirs": {"bal": 0, "közép": 0, "jobb": 0},
                        "goal_dirs": {"bal": 0, "közép": 0, "jobb": 0},
                        "dominant": None, "share_pct": None,
                        "verdict": None} for side in ("home", "away")}
    for sm in seven_meter_outcomes(match, config):
        if sm["irany"] is None:
            continue
        rec = out[sm["team"]]
        rec["attempts"] += 1
        rec["dirs"][sm["irany"]] += 1
        if sm["outcome"] == "gól":
            rec["goals"] += 1
            rec["goal_dirs"][sm["irany"]] += 1

    for side in ("home", "away"):
        rec = out[side]
        if rec["attempts"] < SVD_MIN_ATTEMPTS:
            continue
        dom = max(rec["dirs"], key=lambda k: rec["dirs"][k])
        share = 100.0 * rec["dirs"][dom] / rec["attempts"]
        if share >= SVD_SHARE_PCT:
            rec["dominant"] = dom
            rec["share_pct"] = round(share, 1)
            rec["verdict"] = (
                f"a heteseik {share:.0f}%-a {dom} oldalra megy "
                f"({rec['attempts']} mérhető dobásból) — hetesnél a "
                "kapus tudatosan arra az oldalra vetődhet")
    return out


# Emberelőny-poszt: ennyi poszthoz kötött emberelőny-lövés kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy az
# emberelőnyük egy posztra fut ki.
PPR_MIN_SHOTS = 3
PPR_SHARE_PCT = 60.0


def powerplay_shooter_roles(match: Match,
                            config: Optional[TacticsConfig] = None
                            ) -> dict:
    """Emberelőny-poszt: MELYIK POSZTJUK fejez be a két perc alatt.

    Az emberelőny-lövők rétege (powerplay_shooters) az embert nevezi
    meg — ez a posztot: a kiállítás-ablakokban leadott lövéseiket a
    lövő posztjához írja. Így a minta akkor is látszik, ha a nevek
    meccsről meccsre cserélődnek.

    Edzőileg ez az emberhátrány-terv: öt védővel a fal nem érhet
    mindenhová — ha az emberelőnyük rendre ugyanarra a posztra fut
    ki, a hátrányban az ő sávját kell tartani, és a többieket rá
    lehet engedni. Saját csapatra: az egy posztra futó emberelőny
    kiszámítható — második kifutási út kell.

    Visszatérés csapatonként (a TÁMADÓ oldal): {"shots" (poszthoz
    kötött emberelőny-lövés), "roles": {poszt: lövés}, "main_role",
    "share_pct", "verdict"} — az ítélet None, ha nincs meg a
    PPR_MIN_SHOTS, vagy egyik poszt sem éri el a PPR_SHARE_PCT-t.
    """
    from .roles import estimate_positions

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    pps = powerplay_shooters(match, config)

    out: dict = {side: {"shots": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in pps[side]["players"]:
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["shots"])
            rec["shots"] += row["shots"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["shots"] >= PPR_MIN_SHOTS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["shots"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= PPR_SHARE_PCT:
                rec["verdict"] = (
                    f"az emberelőnyük a(z) {poszt} posztra fut ki "
                    f"({share:.0f}%, {rec['shots']} emberelőny-"
                    "lövésből) — hátrányban az ő sávját kell tartani,"
                    " a többieket rá lehet engedni")
    return out


# Emberhátrány-poszt: ennyi poszthoz kötött hátrány-lövés kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy öt emberrel
# egy posztra fut ki a játékuk.
SHR_MIN_SHOTS = 3
SHR_SHARE_PCT = 60.0


def shorthanded_shooter_roles(match: Match,
                              config: Optional[TacticsConfig] = None
                              ) -> dict:
    """Emberhátrány-poszt: MELYIK POSZTJUK vállal be öt emberrel.

    Az emberhátrány-lövők rétege (shorthanded_shooters) az embert
    nevezi meg — ez a posztot: a kiállítás-ablakokban a HÁTRÁNYBAN
    lévő csapat lövéseit a lövő posztjához írja. Így a minta akkor is
    látszik, ha a nevek meccsről meccsre cserélődnek.

    Edzőileg ez az emberelőny-védelem terve: az ő hátrány-lövő
    posztjuk a kontra-fenyegetés — a saját emberelőnyben az ő oldalán
    kell a labdabiztonság, és rá kell hagyni a legkevesebb teret.
    Saját csapatra: ha öt emberrel mindig ugyanaz a poszt vállal be,
    a hátrány-játékunk kiszámítható — időhúzó variáció is kell.

    Visszatérés csapatonként (a HÁTRÁNYBAN lévő oldal): {"shots"
    (poszthoz kötött hátrány-lövés), "roles": {poszt: lövés},
    "main_role", "share_pct", "verdict"} — az ítélet None, ha nincs
    meg az SHR_MIN_SHOTS, vagy egyik poszt sem éri el az
    SHR_SHARE_PCT-t.
    """
    from .roles import estimate_positions

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    shs = shorthanded_shooters(match, config)

    out: dict = {side: {"shots": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for side in ("home", "away"):
        rec = out[side]
        for row in shs[side]["players"]:
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["shots"])
            rec["shots"] += row["shots"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["shots"] >= SHR_MIN_SHOTS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["shots"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= SHR_SHARE_PCT:
                rec["verdict"] = (
                    f"öt emberrel a(z) {poszt} posztjuk vállal be "
                    f"({share:.0f}%, {rec['shots']} hátrány-lövésből)"
                    " — emberelőnyben az ő oldalán kell a "
                    "labdabiztonság: onnan indul az ellentámadásuk")
    return out


# Passzív-poszt: ennyi poszthoz kötött labdás kocka kell a passzív
# (lövés nélküli, hosszú) támadásokból az ítélethez, és ekkora
# részarány fölött mondjuk ki, hogy a támadásuk egy posztnál hal el.
PVR_MIN_FRAMES = 250
PVR_SHARE_PCT = 60.0


# Passzív-birtoklók: ennyi passzív labdás kocka kell a névhez, és
# ekkora részarány fölött mondjuk ki, hogy a terméketlen idő egy
# ember kezén telik.
PVP_MIN_FRAMES = 200
PVP_SHARE_PCT = 50.0


def passive_holders(match: Match,
                    config: Optional[TacticsConfig] = None) -> dict:
    """Passzív-birtoklók: KINÉL hal el a felállt támadásuk.

    A passzív-poszt (passive_holder_roles) a POSZTOT nevezi meg — ez
    az EMBERT: a lövés nélküli, hosszú felállt támadások labdás
    kockáit a birtokos nevéhez írja.

    Edzőileg ez a passzív jelzés terve névre szólóan: ha a
    terméketlen támadás-idő rendre ugyanannak a kezén telik, a
    passzív jelzés alatt ŐT kell nyomás alá tenni — nála jön a
    kényszer-lövés vagy az eladás. Saját csapatra: neki kell kész
    befejező megoldás, mielőtt a játékvezető keze felmegy.

    Visszatérés csapatonként: {"frames", "players": [{"player_id",
    "jersey", "frames"}], "top"} — a "top" az első játékos, ha
    legalább PVP_MIN_FRAMES passzív labdás kockája van, és ez a
    csapat passzív idejének legalább PVP_SHARE_PCT-a, különben None.
    """
    from .decisions import ball_holder

    config = config or TacticsConfig()
    segments = [(a["start_frame"], a["end_frame"], a["team"])
                for a in passive_play_risks(match, config)]

    jersey: dict = {}
    tally: dict = {"home": {}, "away": {}}
    if segments:
        for f in match.frames:
            side = next((s for (a, b, s) in segments
                         if a <= f.t <= b), None)
            if side is None:
                continue
            h = ball_holder(f, config)
            if h is None or h.team is None \
                    or h.team.value != side or h.role == "kapus":
                continue
            if h.jersey_number is not None:
                jersey.setdefault(h.track_id, h.jersey_number)
            tally[side][h.track_id] = tally[side].get(h.track_id, 0) + 1

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "frames": n}
                for pid, n in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1])]
        total = sum(r["frames"] for r in rows)
        top = None
        if rows and rows[0]["frames"] >= PVP_MIN_FRAMES:
            share = 100.0 * rows[0]["frames"] / max(1, total)
            if share >= PVP_SHARE_PCT:
                top = rows[0]
        out[side] = {"frames": total, "players": rows, "top": top}
    return out


def passive_holder_roles(match: Match,
                         config: Optional[TacticsConfig] = None
                         ) -> dict:
    """Passzív-poszt: MELYIK POSZTJUKNÁL hal el a felállt támadás.

    A passzív-kockázat rétege (passive_play_risks) a szakaszt nevezi
    meg — ez a posztot: a lövés nélküli, hosszú felállt támadások
    labdás kockáit a birtokos posztjához írja. Így látszik, kinél
    áll meg a játék, amikor a támadásuk nem jut el a lövésig.

    Edzőileg ez a passzív jelzés terve: ha a terméketlen támadásaik
    ideje rendre ugyanannál a posztnál telik, a passzív jelzés alatt
    őt kell nyomás alá tenni — nála jön a kényszer-lövés vagy az
    eladás. Saját csapatra: annál a posztnál kell a kész befejező
    megoldás, mielőtt a játékvezető keze felmegy.

    Visszatérés csapatonként: {"frames" (poszthoz kötött passzív
    labdás kocka), "roles": {poszt: kocka}, "main_role",
    "share_pct", "verdict"} — az ítélet None, ha nincs meg a
    PVR_MIN_FRAMES, vagy egyik poszt sem éri el a PVR_SHARE_PCT-t.
    """
    from .decisions import ball_holder
    from .roles import estimate_positions

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    segments = [(a["start_frame"], a["end_frame"], a["team"])
                for a in passive_play_risks(match, config)]

    out: dict = {side: {"frames": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    if segments:
        for f in match.frames:
            side = next((s for (a, b, s) in segments
                         if a <= f.t <= b), None)
            if side is None:
                continue
            h = ball_holder(f, config)
            if h is None or h.team is None \
                    or h.team.value != side or h.role == "kapus":
                continue
            rec_role = roles[side].get(h.track_id)
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec = out[side]
            rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1
            rec["frames"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["frames"] >= PVR_MIN_FRAMES:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["frames"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= PVR_SHARE_PCT:
                rec["verdict"] = (
                    f"a lövés nélküli, hosszú támadásaik labdás "
                    f"idejének {share:.0f}%-a a(z) {poszt} posztnál "
                    "telik — ott hal el a támadásuk: passzív "
                    "jelzésnél őt kell nyomás alá tenni, nála jön a "
                    "kényszer-eladás")
    return out


# Hetesdobó-poszt: ennyi poszthoz kötött hetes-kísérlet kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy a heteseiket
# egy poszt dobja.
STK_MIN_ATTEMPTS = 3
STK_SHARE_PCT = 60.0


def seven_taker_roles(match: Match,
                      config: Optional[TacticsConfig] = None) -> dict:
    """Hetesdobó-poszt: MELYIK POSZTJUK áll oda a hétméteresekhez.

    A hetes-dobók listája az embert nevezi meg — ez a posztot: a
    felismert hétméteresek kimenetel-lövéseit (seven_meter_outcomes)
    a dobó posztjához írja. Így a minta akkor is látszik, ha a nevek
    meccsről meccsre cserélődnek.

    Edzőileg ez a kapus-felkészülés és a fárasztás terve: ha a
    heteseiket rendre ugyanaz a poszt dobja, a kapus az ő
    szokás-irányait tanulja (a Hetes-oldal réteggel együtt), a
    meccsterv pedig tudja: ha ezt a posztot kivesszük (kiállítás,
    fáradás, csere-kényszer), a hetes-rutinjuk is vele megy. Saját
    csapatra: kell a második kijelölt dobó.

    Visszatérés csapatonként: {"attempts" (poszthoz kötött hetes),
    "roles": {poszt: darab}, "main_role", "share_pct", "verdict"} —
    az ítélet None, ha nincs meg az STK_MIN_ATTEMPTS, vagy egyik
    poszt sem éri el az STK_SHARE_PCT-t.
    """
    from .roles import estimate_positions

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)

    out: dict = {side: {"attempts": 0, "roles": {},
                        "main_role": None, "share_pct": None,
                        "verdict": None}
                 for side in ("home", "away")}
    for sm in seven_meter_outcomes(match, config):
        pid = sm.get("shooter_id")
        if pid is None:
            continue
        side = sm["team"]
        rec_role = roles[side].get(pid)
        if rec_role is None:
            continue
        poszt = rec_role["poszt"]
        rec = out[side]
        rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1
        rec["attempts"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["attempts"] >= STK_MIN_ATTEMPTS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["attempts"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= STK_SHARE_PCT:
                rec["verdict"] = (
                    f"a heteseiket {share:.0f}%-ban a(z) {poszt} "
                    f"posztjuk dobja ({rec['attempts']} hetesből) — "
                    "a kapus az ő szokás-irányaira készüljön; ha ezt"
                    " a posztot kiveszik, a hetes-rutinjuk is vele "
                    "megy")
    return out


# Hetespáros-poszt: ennyi poszthoz kötött hetes kell az ítélethez, és
# ekkora részarány fölött mondjuk ki, hogy a hetes-játékuk egy
# (kiharcoló → dobó) posztpárra jár.
SVP_MIN_SEVENS = 3
SVP_SHARE_PCT = 60.0


def seven_pair_roles(match: Match,
                     config: Optional[TacticsConfig] = None) -> dict:
    """Hetespáros-poszt: KI HARCOLJA KI és KI DOBJA a heteseiket.

    A hetes-kiharcoló és a hetesdobó poszt külön-külön ismert — ez a
    kettőt köti össze hetesenként: a (kiharcoló poszt → dobó poszt)
    párost számolja. A bejáratott hetes-munkamegosztás akkor is
    látszik, ha a nevek meccsről meccsre cserélődnek.

    Edzőileg két kiosztható feladat egyszerre: a kiharcoló posztja
    ellen kéz nélkül, lábmunkával kell védekezni (nála a lerántás
    büntető), a dobó posztjának szokás-irányait pedig a kapus
    tanulja. Saját csapatra: ha a kiharcolás és a dobás is egy-egy
    emberen áll, mindkettőhöz kell tartalék.

    Visszatérés csapatonként: {"sevens" (párhoz kötött hetes),
    "roles": {"kiharcoló→dobó": darab}, "main_role", "share_pct",
    "verdict"} — az ítélet None, ha nincs meg az SVP_MIN_SEVENS,
    vagy egyik pár sem éri el az SVP_SHARE_PCT-t.
    """
    from .roles import estimate_positions

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    frames_by_t = {f.t: f for f in match.frames}
    roles = estimate_positions(match, config)

    out: dict = {side: {"sevens": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for sm in seven_meter_outcomes(match, config):
        taker_id = sm.get("shooter_id")
        if taker_id is None:
            continue
        # A kiharcoló: a jel előtti pillanatban a kapuhoz legközelebb
        # járó (nem kapus) támadó — mint a seven_meter_earners-ben.
        t_prev = sm["t"] - round(SEVEN_EARNER_LOOKBACK_S * fps)
        fr = None
        for dt in range(0, round(fps)):
            fr = (frames_by_t.get(t_prev - dt)
                  or frames_by_t.get(t_prev + dt))
            if fr is not None and fr.players:
                break
        if fr is None or not fr.players:
            continue
        best = None
        for p in fr.players:
            if p.team.value != sm["team"] or p.role == "kapus":
                continue
            d = abs(p.x - sm["goal_x"])
            if best is None or d < best[1]:
                best = (p.track_id, d)
        if best is None:
            continue
        side = sm["team"]
        r_earn = roles[side].get(best[0])
        r_take = roles[side].get(taker_id)
        if r_earn is None or r_take is None:
            continue
        kulcs = f"{r_earn['poszt']}→{r_take['poszt']}"
        rec = out[side]
        rec["roles"][kulcs] = rec["roles"].get(kulcs, 0) + 1
        rec["sevens"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["sevens"] >= SVP_MIN_SEVENS:
            par = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][par] / rec["sevens"]
            rec["main_role"] = par
            rec["share_pct"] = round(share, 1)
            if share >= SVP_SHARE_PCT:
                rec["verdict"] = (
                    f"a hetes-játékuk a(z) {par} posztpárra jár "
                    f"({share:.0f}%, {rec['sevens']} hetesből) — a "
                    "kiharcoló ellen kéz nélkül kell védekezni, a "
                    "dobó szokás-irányait a kapus tanulja")
    return out


# Emberelőnypáros-poszt: ennyi párhoz kötött emberelőny-lövés kell az
# ítélethez, és ekkora részarány fölött mondjuk ki, hogy a 6-5
# játékuk egy (előkészítő → befejező) tengelyen fut.
PWP_MIN_SHOTS = 3
PWP_SHARE_PCT = 60.0
PWP_WINDOW_S = 4.0


def powerplay_pair_roles(match: Match,
                         config: Optional[TacticsConfig] = None
                         ) -> dict:
    """Emberelőnypáros-poszt: MELYIK TENGELYEN fut a 6-5 játékuk.

    Az emberelőny-poszt a befejezőt nevezi meg — ez a tengelyt:
    minden emberelőnyben leadott lövésnél megkeresi a lövő felé menő
    utolsó passzt (PWP_WINDOW_S ablakban), és a lövést az
    (előkészítő poszt → befejező poszt) párhoz írja.

    Edzőileg ez az öt emberrel is kiosztható feladat: emberhátrányban
    nincs elég kéz mindenre, ezért a tengelyt kell elvágni — az
    előkészítő posztjának passzsávját zárja a fal széle, a befejező
    posztjára pedig a kilépés jusson. Saját csapatra: ha a 6-5-ünk
    egy tengelyen fut, öt emberrel is kiszámítható vagyunk.

    Visszatérés csapatonként: {"shots" (párhoz kötött emberelőny-
    lövés), "roles": {"előkészítő→befejező": darab}, "main_role",
    "share_pct", "verdict"} — az ítélet None, ha nincs meg a
    PWP_MIN_SHOTS, vagy egyik pár sem éri el a PWP_SHARE_PCT-t.
    """
    from .decisions import detect_passes
    from .event_detection import EventType, detect_shots
    from .roles import estimate_positions

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = PWP_WINDOW_S * fps
    roles = estimate_positions(match, config)
    passes = detect_passes(match, config)

    # Emberelőny-ablakok az ELŐNYBEN lévő csapat szerint.
    up_windows: list[tuple] = []
    for w in detect_powerplay(match):
        up = "away" if w["team_down"] == "home" else "home"
        up_windows.append((up, w["start_frame"], w["end_frame"]))

    out: dict = {side: {"shots": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    if not up_windows:
        return out

    for e in detect_shots(match, config):
        if e.type not in (EventType.SHOT, EventType.GOAL):
            continue
        if e.player_id is None:
            continue
        side = e.team.value
        if not any(up == side and a <= e.t <= b
                   for (up, a, b) in up_windows):
            continue
        best = None
        for p in passes:
            if not (0 <= e.t - p.t <= win) or p.team != e.team:
                continue
            if (p.receiver_id != e.player_id
                    or p.passer_id == e.player_id):
                continue
            if best is None or p.t > best.t:
                best = p
        if best is None:
            continue
        r_feed = roles[side].get(best.passer_id)
        r_shot = roles[side].get(e.player_id)
        if r_feed is None or r_shot is None:
            continue
        kulcs = f"{r_feed['poszt']}→{r_shot['poszt']}"
        rec = out[side]
        rec["roles"][kulcs] = rec["roles"].get(kulcs, 0) + 1
        rec["shots"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["shots"] >= PWP_MIN_SHOTS:
            par = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][par] / rec["shots"]
            rec["main_role"] = par
            rec["share_pct"] = round(share, 1)
            if share >= PWP_SHARE_PCT:
                rec["verdict"] = (
                    f"a 6-5 játékuk a(z) {par} tengelyen fut "
                    f"({share:.0f}%, {rec['shots']} emberelőny-"
                    "lövésből) — öt emberrel a tengelyt vágjátok el:"
                    " az előkészítő passzsávját a fal széle zárja, a"
                    " befejezőre jusson a kilépés")
    return out


# Hetes-kihagyó poszt: ennyi poszthoz kötött, gól nélkül záruló
# hetes kell az ítélethez, és ekkora részarány fölött mondjuk ki,
# hogy a kihagyott heteseik egy posztra sűrűsödnek.
SVM_MIN_MISSES = 3
SVM_SHARE_PCT = 60.0


def seven_miss_roles(match: Match,
                     config: Optional[TacticsConfig] = None) -> dict:
    """Hetes-kihagyó poszt: MELYIK POSZTJUK hibázza el a hetest.

    A hetesdobó-poszt azt mondja meg, ki áll oda — ez azt, ki hibáz:
    a felismert hétméteresek közül a gól NÉLKÜL zárulókat (védés
    vagy mellé) a dobó posztjához írja.

    Edzőileg ez a kapus felkészítésének második fele: ha a
    kihagyásaik egy posztra sűrűsödnek, a kapus tudja, melyik dobó
    ellen érdemes a saját megérzésére hagyatkozni (kimozdulás,
    késleltetett vetődés) — nála a hetes nem automatikus gól. Saját
    csapatra: a kihagyó poszt hetes-gyakorlása és a második dobó
    kijelölése a téma.

    Visszatérés csapatonként: {"misses" (poszthoz kötött kihagyott
    hetes), "roles": {poszt: darab}, "main_role", "share_pct",
    "verdict"} — az ítélet None, ha nincs meg az SVM_MIN_MISSES,
    vagy egyik poszt sem éri el az SVM_SHARE_PCT-t.
    """
    from .roles import estimate_positions

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)

    out: dict = {side: {"misses": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for sm in seven_meter_outcomes(match, config):
        pid = sm.get("shooter_id")
        if pid is None or sm.get("outcome") == "gól":
            continue
        if sm.get("outcome") in (None, "ismeretlen"):
            continue   # nem mérhető kimenetel: nem számoljuk hibának
        side = sm["team"]
        rec_role = roles[side].get(pid)
        if rec_role is None:
            continue
        poszt = rec_role["poszt"]
        rec = out[side]
        rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1
        rec["misses"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["misses"] >= SVM_MIN_MISSES:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["misses"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= SVM_SHARE_PCT:
                rec["verdict"] = (
                    f"a kihagyott heteseik {share:.0f}%-a a(z) "
                    f"{poszt} posztjukhoz kötődik ({rec['misses']} "
                    "gól nélküli hetesből) — ellene a kapus a saját "
                    "megérzésére hagyatkozhat (kimozdulás, "
                    "késleltetett vetődés): nála a hetes nem "
                    "automatikus gól")
    return out


# Emberelőny-hiba poszt küszöbei: ennyi poszthoz kötött
# emberelőny-eladás kell az ítélethez, és ekkora részarány a vezető
# posztnak.
PPT_MIN_TURNOVERS = 3
PPT_SHARE_PCT = 60.0


def powerplay_turnover_roles(match: Match,
                             config: Optional[TacticsConfig] = None
                             ) -> dict:
    """Emberelőny-hiba poszt: KINEK A KEZÉN akad el az emberelőnyük.

    Az emberelőny-poszt azt mondja meg, kire fut ki a hat a öt ellen
    — ez azt, kinél vész el: a kiállítás-ablakokban, EMBERELŐNYBEN
    elkövetett labdaeladásaikat a vesztes posztjához írja. A
    poszt-hibák rétege az egész meccset nézi, ez csak a két percet,
    ahol a hiba a legdrágább.

    Edzőileg ez a hátrányban álló csapat egyetlen esélye: ha az
    emberelőnyük rendre ugyanannak a kezén akad el, hátrányban rá
    kell nyomni (kettőzés, passzsáv-zárás a fogadásánál) — az ő
    elvett labdája dupla büntetés, mert a kétperc alatt kontrázni
    lehet belőle. Saját csapatra: az emberelőny-figurát nem szabad
    ugyanarra a kézre bízni, ha ott szakad el.

    Visszatérés csapatonként (a TÁMADÓ, tehát emberelőnyben lévő
    oldal): {"turnovers" (poszthoz kötött emberelőny-eladás),
    "roles": {poszt: darab}, "main_role", "share_pct", "verdict"} —
    az ítélet None, ha nincs meg a PPT_MIN_TURNOVERS, vagy egyik
    poszt sem éri el a PPT_SHARE_PCT-t.
    """
    from .event_detection import EventType, detect_events
    from .roles import estimate_positions

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    # Az emberelőny-ablakok a TÁMADÓ (előnyben lévő) oldal szerint.
    windows = [("away" if w["team_down"] == "home" else "home",
                w["start_frame"], w["end_frame"])
               for w in detect_powerplay(match)]

    out: dict = {side: {"turnovers": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    if not windows:
        return out
    for e in detect_events(match, config):
        if e.type != EventType.TURNOVER or e.player_id is None:
            continue
        side = e.team.value
        if not any(s == side and a <= e.t <= b for s, a, b in windows):
            continue
        rec_role = roles[side].get(e.player_id)
        if rec_role is None:
            continue
        poszt = rec_role["poszt"]
        rec = out[side]
        rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1
        rec["turnovers"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["turnovers"] >= PPT_MIN_TURNOVERS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["turnovers"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= PPT_SHARE_PCT:
                rec["verdict"] = (
                    f"az emberelőnyük {share:.0f}%-ban a(z) {poszt} "
                    f"kezén akad el ({rec['turnovers']} "
                    "emberelőny-eladásból) — hátrányban rá kell "
                    "nyomni: az ő elvett labdája dupla büntetés, "
                    "mert a kétperc alatt kontrázni lehet belőle")
    return out


# Emberhátrány-hiba poszt küszöbei: ennyi poszthoz kötött hátrányban
# elkövetett eladás kell az ítélethez, és ekkora részarány a vezető
# posztnak.
SHT_MIN_TURNOVERS = 3
SHT_SHARE_PCT = 60.0


def shorthanded_turnover_roles(match: Match,
                               config: Optional[TacticsConfig] = None
                               ) -> dict:
    """Emberhátrány-hiba poszt: ÖT EMBERREL kinek a kezén vész el.

    Az emberhátrány-poszt azt mondja meg, ki vállalja a befejezést öt
    emberrel — ez a párja: a kiállítás-ablakokban, EMBERHÁTRÁNYBAN
    elkövetett labdaeladásaikat a vesztes posztjához írja. Az
    emberelőny-hiba poszt a két percet előnyből nézi, ez hátrányból,
    ahol egy elvesztett labda azonnal gólt ér.

    Edzőileg ez az emberelőny-védekezésük gyenge pontja: ha hátrányban
    rendre ugyanannak a kezén vész el a labda, a hat a öt ellen az ő
    fogadására kell menni (kilépő védő, passzsáv-zárás) — az elvett
    labdából üres kapura indulhat a kontra. Saját csapatra: öt
    emberrel a kockázatos passzt ki kell venni a rendszerből, és a
    labda a legbiztosabb kézben maradjon.

    Visszatérés csapatonként (a HÁTRÁNYBAN lévő oldal): {"turnovers"
    (poszthoz kötött hátrány-eladás), "roles": {poszt: darab},
    "main_role", "share_pct", "verdict"} — az ítélet None, ha nincs
    meg a SHT_MIN_TURNOVERS, vagy egyik poszt sem éri el a
    SHT_SHARE_PCT-t.
    """
    from .event_detection import EventType, detect_events
    from .roles import estimate_positions

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    # Az ablakok a HÁTRÁNYBAN lévő oldal szerint.
    windows = [(w["team_down"], w["start_frame"], w["end_frame"])
               for w in detect_powerplay(match)]

    out: dict = {side: {"turnovers": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    if not windows:
        return out
    for e in detect_events(match, config):
        if e.type != EventType.TURNOVER or e.player_id is None:
            continue
        side = e.team.value
        if not any(s == side and a <= e.t <= b for s, a, b in windows):
            continue
        rec_role = roles[side].get(e.player_id)
        if rec_role is None:
            continue
        poszt = rec_role["poszt"]
        rec = out[side]
        rec["roles"][poszt] = rec["roles"].get(poszt, 0) + 1
        rec["turnovers"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["turnovers"] >= SHT_MIN_TURNOVERS:
            poszt = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][poszt] / rec["turnovers"]
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= SHT_SHARE_PCT:
                rec["verdict"] = (
                    f"hátrányban {share:.0f}%-ban a(z) {poszt} kezén "
                    f"vész el a labdájuk ({rec['turnovers']} "
                    "hátrány-eladásból) — a hat az öt ellen az ő "
                    "fogadására kell menni: az elvett labdából üres "
                    "kapura indulhat a kontra")
    return out


# Hetes-kihagyók: ennyi gól nélküli hetes kell ahhoz, hogy a
# játékost kiemeljük (a hetes ritka esemény, ezért alacsony a küszöb).
SVMP_MIN_MISSES = 2


def seven_miss_players(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Hetes-kihagyók: KI HIBÁZZA EL a hetest.

    A hetes-mérleg (seven_meter_summary) csapat-szinten mondja meg,
    mennyi megy be a hetesekből, a hetes-kihagyó poszt a POSZTOT — ez
    az EMBERT: a gól nélkül záruló hétméteresek (védés vagy mellé) a
    dobó játékoshoz kerülnek.

    Edzőileg ez a kapus felkészítésének névsora: ha ő áll oda, a
    kapus mehet a saját megérzésére (kimozdulás, késleltetett
    vetődés) — nála a hetes nem automatikus gól. Saját csapatra: a
    hetes-sorrend nem rangsor, hanem napi forma; a listán szereplő
    dobó mögé kell egy második ember.

    Visszatérés csapatonként: {"misses" (gól nélküli hetes),
    "players": [{"player_id", "jersey", "misses"}], "top"} — a "top"
    az első játékos, ha legalább SVMP_MIN_MISSES kihagyása van,
    különben None.
    """
    config = config or TacticsConfig()

    jersey: dict = {}
    for f in match.frames:
        for p in f.players:
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)

    tally: dict = {"home": {}, "away": {}}
    for sm in seven_meter_outcomes(match, config):
        pid = sm.get("shooter_id")
        if pid is None or sm.get("outcome") in ("gól", None,
                                                "ismeretlen"):
            continue
        side = sm["team"]
        tally[side][pid] = tally[side].get(pid, 0) + 1

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "misses": n}
                for pid, n in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1])]
        top = (rows[0] if rows and rows[0]["misses"] >= SVMP_MIN_MISSES
               else None)
        out[side] = {"misses": sum(r["misses"] for r in rows),
                     "players": rows, "top": top}
    return out


# Kétperc-páros küszöbei: ennyi poszthoz kötött (kiharcoló →
# emberelőny-befejező) pár kell az ítélethez, és ekkora részarány a
# vezető párosnak. A kiállítás ritka esemény, ezért enyhébb a
# részarány-küszöb, mint az egy-posztos lencséknél.
SCH_MIN_PAIRS = 3
SCH_SHARE_PCT = 55.0


def suspension_chain_roles(match: Match,
                           config: Optional[TacticsConfig] = None
                           ) -> dict:
    """Kétperc-páros: KI HARCOLJA KI és KI FEJEZI BE a kétpercüket.

    A kiállítás-kiharcolás poszt szerint azt mondja meg, ki hozza a
    kétperceseket, az emberelőny-poszt azt, kire fut ki a hat az öt
    ellen — ez a kettőt köti össze kiállításonként: a (kiharcoló
    poszt → emberelőny-befejező poszt) párost számolja, az ablakon
    belül leadott lövéseik alapján.

    Edzőileg egy kiállítás két feladatot ad egyszerre: a kiharcoló
    posztja ellen fegyelmezetten, testtel kell védekezni (nála a
    kései fogás kétpercet ér), a befejező posztját pedig hátrányban
    kell letiltani — a lánc így már az elején elvágható. Saját
    csapatra: ha a kiharcolás és az emberelőny-befejezés is egy-egy
    poszton áll, mindkettő kiszámítható.

    Visszatérés csapatonként (a KÉTPERCET SZERZŐ oldal): {"chains"
    (poszthoz kötött lánc), "roles": {"A→B": darab}, "main_role" (a
    fő páros), "share_pct", "verdict"} — az ítélet None, ha nincs meg
    a SCH_MIN_PAIRS, vagy egyik páros sem éri el a SCH_SHARE_PCT-t.
    """
    from .event_detection import EventType, detect_shots
    from .roles import estimate_positions

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    frames_by_t = {f.t: f for f in match.frames}
    roles = estimate_positions(match, config)
    shots = [e for e in detect_shots(match, config)
             if e.type in (EventType.SHOT, EventType.GOAL)]

    out: dict = {side: {"chains": 0, "roles": {}, "main_role": None,
                        "share_pct": None, "verdict": None}
                 for side in ("home", "away")}
    for w in detect_powerplay(match):
        up = "away" if w["team_down"] == "home" else "home"
        goal_x = config.attacks_toward_x(
            Team.HOME if up == "home" else Team.AWAY)
        # A kiharcoló: az ablak kezdete előtt a kapuhoz legmélyebben
        # nyomuló támadó — ugyanaz a heurisztika, mint a
        # suspension_earners-ben.
        t0 = w["start_frame"] - round(SUSP_EARNER_LOOKBACK_S * fps)
        best = None
        for dt in range(0, round(SUSP_EARNER_LOOKBACK_S * fps) + 1):
            fr = frames_by_t.get(t0 + dt)
            if fr is None:
                continue
            for p in fr.players:
                if p.team.value != up or p.role == "kapus":
                    continue
                d = abs(p.x - goal_x)
                if best is None or d < best[1]:
                    best = (p.track_id, d)
        if best is None:
            continue
        r_earn = roles[up].get(best[0])
        if r_earn is None:
            continue
        for e in shots:
            if e.team.value != up or e.player_id is None:
                continue
            if not (w["start_frame"] <= e.t <= w["end_frame"]):
                continue
            r_fin = roles[up].get(e.player_id)
            if r_fin is None:
                continue
            kulcs = f"{r_earn['poszt']}→{r_fin['poszt']}"
            rec = out[up]
            rec["roles"][kulcs] = rec["roles"].get(kulcs, 0) + 1
            rec["chains"] += 1

    for side in ("home", "away"):
        rec = out[side]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if rec["chains"] >= SCH_MIN_PAIRS:
            par = max(rec["roles"], key=lambda p: rec["roles"][p])
            share = 100.0 * rec["roles"][par] / rec["chains"]
            rec["main_role"] = par
            rec["share_pct"] = round(share, 1)
            if share >= SCH_SHARE_PCT:
                rec["verdict"] = (
                    f"a kétperceik {share:.0f}%-a ugyanazt a láncot "
                    f"futja ({par}, {rec['chains']} "
                    "emberelőny-lövésből) — a kiharcolójuk ellen "
                    "testtel, kéz nélkül kell védekezni, a "
                    "befejezőjüket pedig hátrányban le kell tiltani")
    return out


# Kétperc ára: ennyi mért kiállítás-ablak kell az ítélethez, e fölött
# drága a kétperc (gól/kiállítás), ez alatt viszont olcsó — a
# hátrány-védekezésük jó.
SCT_MIN_WINDOWS = 3
SCT_COSTLY = 1.2
SCT_CHEAP = 0.5


def suspension_cost(match: Match,
                    config: Optional[TacticsConfig] = None) -> dict:
    """Kétperc ára: MENNYI GÓLBA KERÜL egy kiállításuk.

    Az emberelőny-hatékonyság azt méri, mit TÁMADNAK a két perc
    alatt, az emberelőny-védekezés azt, mit kapnak közben — ez a
    HÁTRÁNY oldalát egyetlen számban: hány gólt kapnak átlagosan egy
    kiállítás-ablak alatt.

    Edzőileg ez a fegyelem ára forintosítva. Ha egy kétperc átlag
    több mint egy gólba kerül nekik, a kiharcolás önmagában
    pont-termelés: a betöréseket vállalni kell, mert a szabálytalanság
    duplán fizet. Ha viszont olcsón megússzák, a kiállítás nem
    stratégia — nem szabad rá játszani, marad a felállt támadás.
    Saját csapatra: a hátrány-védekezés (fal-forma, kapus, labdatartás)
    a téma.

    Visszatérés csapatonként (a KIÁLLÍTOTT oldal): {"windows"
    (kiállítás-ablak), "conceded" (közben kapott gól), "per_susp",
    "verdict"} — a per_susp None SCT_MIN_WINDOWS alatt, az ítélet
    None, ha a két küszöb közé esik.
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    goals = sorted((e.t, e.team.value) for e in detect_shots(match, config)
                   if e.type == EventType.GOAL)

    out: dict = {side: {"windows": 0, "conceded": 0, "per_susp": None,
                        "verdict": None}
                 for side in ("home", "away")}
    for w in detect_powerplay(match):
        down = w["team_down"]
        up = "away" if down == "home" else "home"
        rec = out[down]
        rec["windows"] += 1
        rec["conceded"] += sum(
            1 for (gt, gs) in goals
            if gs == up and w["start_frame"] <= gt <= w["end_frame"])

    for side in ("home", "away"):
        rec = out[side]
        if rec["windows"] < SCT_MIN_WINDOWS:
            continue
        per = rec["conceded"] / rec["windows"]
        rec["per_susp"] = round(per, 2)
        if per >= SCT_COSTLY:
            rec["verdict"] = (
                f"egy kiállításuk átlag {per:.1f} gólba kerül "
                f"({rec['conceded']} gól {rec['windows']} kétperc "
                "alatt) — a kiharcolás náluk pont-termelés: a "
                "betöréseket vállalni kell, mert a szabálytalanság "
                "duplán fizet")
        elif per <= SCT_CHEAP:
            rec["verdict"] = (
                f"egy kiállításuk csak {per:.1f} gólba kerül "
                f"({rec['conceded']} gól {rec['windows']} kétperc "
                "alatt) — olcsón megússzák a hátrányt: nem szabad a "
                "kiállítás kiharcolására játszani, marad a felállt "
                "támadás")
    return out


# Emberelőny-hibázók: ennyi emberelőny-eladástól emeljük ki a
# játékost (a két perc rövid, ezért alacsony a küszöb).
PPTP_MIN_TURNOVERS = 2


def powerplay_turnover_players(match: Match,
                               config: Optional[TacticsConfig] = None
                               ) -> dict:
    """Emberelőny-hibázók: KI ADJA EL a labdát a két perc alatt.

    Az emberelőny-hiba poszt (powerplay_turnover_roles) a POSZTOT
    nevezi meg — ez az EMBERT: ugyanazokat a kiállítás-ablakokban,
    emberelőnyben elkövetett labdaeladásokat játékosonként számolja.

    Edzőileg ez a hátrány-védekezés névre szóló célpontja: hátrányban
    rá kell nyomni (kettőzés, passzsáv-zárás a fogadásánál), mert az
    ő elvett labdája dupla büntetés — a kétperc alatt kontrázni lehet
    belőle. Saját csapatra: az emberelőny-figurában a kockázatos
    passzt ki kell venni a kezéből.

    Visszatérés csapatonként (a TÁMADÓ, tehát emberelőnyben lévő
    oldal): {"turnovers", "players": [{"player_id", "jersey",
    "turnovers"}], "top"} — a "top" az első játékos, ha legalább
    PPTP_MIN_TURNOVERS emberelőny-eladása van, különben None.
    """
    from .event_detection import EventType, detect_events

    config = config or TacticsConfig()
    windows = [("away" if w["team_down"] == "home" else "home",
                w["start_frame"], w["end_frame"])
               for w in detect_powerplay(match)]

    jersey: dict = {}
    for f in match.frames:
        for p in f.players:
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)

    tally: dict = {"home": {}, "away": {}}
    if windows:
        for e in detect_events(match, config):
            if e.type != EventType.TURNOVER or e.player_id is None:
                continue
            side = e.team.value
            if not any(s == side and a <= e.t <= b
                       for s, a, b in windows):
                continue
            tally[side][e.player_id] = (
                tally[side].get(e.player_id, 0) + 1)

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "turnovers": n}
                for pid, n in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1])]
        top = (rows[0]
               if rows and rows[0]["turnovers"] >= PPTP_MIN_TURNOVERS
               else None)
        out[side] = {"turnovers": sum(r["turnovers"] for r in rows),
                     "players": rows, "top": top}
    return out


# Emberhátrány-hibázók: ennyi hátrány-eladástól emeljük ki a
# játékost — öt emberrel egy elvesztett labda azonnal gólt ér.
SHTP_MIN_TURNOVERS = 2


def shorthanded_turnover_players(match: Match,
                                 config: Optional[TacticsConfig] = None
                                 ) -> dict:
    """Emberhátrány-hibázók: ÖT EMBERREL ki veszíti el a labdát.

    Az emberhátrány-hiba poszt (shorthanded_turnover_roles) a
    POSZTOT nevezi meg — ez az EMBERT: ugyanazokat a
    kiállítás-ablakokban, emberhátrányban elkövetett labdaeladásokat
    játékosonként számolja.

    Edzőileg ez az emberelőny-játékunk névre szóló célpontja: a hat
    az öt ellen az ő fogadására kell menni, mert az elvett labdából
    üres kapura indulhat a kontra. Saját csapatra: hátrányban a
    labdát a legbiztosabb kézben kell tartani — ha nála rendre
    elmegy, más legyen a labdatartó.

    Visszatérés csapatonként (a HÁTRÁNYBAN lévő oldal):
    {"turnovers", "players": [{"player_id", "jersey", "turnovers"}],
    "top"} — a "top" az első játékos, ha legalább
    SHTP_MIN_TURNOVERS hátrány-eladása van, különben None.
    """
    from .event_detection import EventType, detect_events

    config = config or TacticsConfig()
    windows = [(w["team_down"], w["start_frame"], w["end_frame"])
               for w in detect_powerplay(match)]

    jersey: dict = {}
    for f in match.frames:
        for p in f.players:
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)

    tally: dict = {"home": {}, "away": {}}
    if windows:
        for e in detect_events(match, config):
            if e.type != EventType.TURNOVER or e.player_id is None:
                continue
            side = e.team.value
            if not any(s == side and a <= e.t <= b
                       for s, a, b in windows):
                continue
            tally[side][e.player_id] = (
                tally[side].get(e.player_id, 0) + 1)

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "turnovers": n}
                for pid, n in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1])]
        top = (rows[0]
               if rows and rows[0]["turnovers"] >= SHTP_MIN_TURNOVERS
               else None)
        out[side] = {"turnovers": sum(r["turnovers"] for r in rows),
                     "players": rows, "top": top}
    return out


# Hetesdobók: ennyi hetestől emeljük ki a játékost (a hetes ritka
# esemény, ezért alacsony a küszöb).
STP_MIN_SEVENS = 2


def seven_taker_players(match: Match,
                        config: Optional[TacticsConfig] = None) -> dict:
    """Hetesdobók: KI ÁLL ODA a hétméteresekhez.

    A hetesdobó-poszt (seven_taker_roles) a POSZTOT nevezi meg, a
    hetes-kihagyók azt, ki HIBÁZZA el — ez azt, ki áll oda
    egyáltalán: a felismert hétméteresek dobóit számolja
    játékosonként, a góllal és a gól nélkül zárulókat együtt.

    Edzőileg ez a kapus felkészítésének első lapja: ha a hetesek nagy
    részét ugyanaz dobja, a kapus RÁ készülhet (szokás-sarok,
    lépésritmus, csel), és a videó-elemzés is egy emberre szűkül.
    Saját csapatra: az egyetlen hetesdobó kockázat — kiállítás,
    sérülés vagy rossz nap esetén kell egy második ember.

    Visszatérés csapatonként: {"sevens" (dobóhoz kötött hetes),
    "players": [{"player_id", "jersey", "sevens", "goals"}], "top"} —
    a "top" az első játékos, ha legalább STP_MIN_SEVENS hetese van,
    különben None.
    """
    config = config or TacticsConfig()

    jersey: dict = {}
    for f in match.frames:
        for p in f.players:
            if p.jersey_number is not None:
                jersey.setdefault(p.track_id, p.jersey_number)

    tally: dict = {"home": {}, "away": {}}
    for sm in seven_meter_outcomes(match, config):
        pid = sm.get("shooter_id")
        if pid is None:
            continue
        rec = tally[sm["team"]].setdefault(pid, {"sevens": 0,
                                                 "goals": 0})
        rec["sevens"] += 1
        if sm.get("outcome") == "gól":
            rec["goals"] += 1

    out: dict = {}
    for side in ("home", "away"):
        rows = [{"player_id": pid, "jersey": jersey.get(pid),
                 "sevens": r["sevens"], "goals": r["goals"]}
                for pid, r in sorted(tally[side].items(),
                                     key=lambda kv: -kv[1]["sevens"])]
        top = (rows[0] if rows and rows[0]["sevens"] >= STP_MIN_SEVENS
               else None)
        out[side] = {"sevens": sum(r["sevens"] for r in rows),
                     "players": rows, "top": top}
    return out
