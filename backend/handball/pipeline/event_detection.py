"""
[2. fázis kiegészítés] Eseményfelismerés — passz, lövés, gól, labdaeladás.

A kész Tracking-ből (labda + pozíciók + birtoklás) felismeri a fő eseményeket:
- PASSZ:        a labdabirtokos UGYANAZON a csapaton belül változik.
- LABDAELADÁS:  a birtoklás az ELLENFÉLHEZ kerül (nem lövés után).
- LÖVÉS:        a labda gyorsan a kapu felé tart és megközelíti a gólvonalat.
- GÓL:          olyan lövés, ahol a labda a kapufák között eléri a gólvonalat.

Heurisztikus (a labda sebességéből és helyzetéből), nem betanított modell — a célja
a CSŐVEZETÉK és az API, ami valódi adattal/finomabb modellel pontosítható. Tiszta
Python, szintetikus pályákon tesztelhető.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from ..models.tracking import Match, Team
from .calibration import COURT_LENGTH_M, COURT_WIDTH_M
from .tactics import TacticsConfig
from .decisions import ball_holder
from .primitive_cache import copy_events, memoize_primitive

# Heurisztikus küszöbök:
SHOT_SPEED_MS = 8.0      # a labda ennél gyorsabban a kapu felé tartva = lövés
APPROACH_X_M = 4.0       # a kaputól (x-ben) ekkora közelségben "kapu-megközelítés"
# Lövés-CSENDIDŐ ugyanarra a kapura. A hely-alapú debounce (a labdának ki
# kell lépnie a kapu-zónából) zajos labda-észlelésnél nem elég: a labda
# ki-be billeg a zóna szélén, és EGY lövésből négy esemény lesz — éles
# meccsen pontosan ez történt (1264,6 / 1265,9 / 1266,3 / 1267,1 mp).
#
# A szabály: ezen belül nem indul újabb esemény ugyanarra a kapura, és a
# csendidő minden elnyomott jelöltnél ÚJRAINDUL. Így egy zaj-sorozat egy
# eseménnyé olvad — ez az őszinte olvasat: másfél másodpercen belül a
# felismerés nem tud két lövést szétválasztani, tehát egyet mond.
#
# A küszöb SZÁNDÉKOSAN óvatos: fél másodpercen belül ugyanarra a kapura
# két KÜLÖN lövés fizikailag sem hihető (a kipattanó összeszedése és az
# újabb elengedés ennél tovább tart), tehát itt nem dobunk el valódi
# eseményt. A ritkább, 1-1,5 másodperces ismétléseket ez nem szűri —
# azokat a kalibráció rendbetétele oldja meg, nem a csendidő: a
# zaj-sorozat oka a hibás pálya-vetítés, nem a küszöb.
SHOT_COOLDOWN_S = 0.5
GOAL_TOL_M = 0.7         # a gólvonalat ennyire megközelítve számít elértnek
GOAL_LOOKAHEAD = 12      # a góldöntéshez ennyi frame-et nézünk előre
TURNOVER_SUPPRESS = 12   # lövés után ennyi frame-en belüli labdaeladást elnyomunk

_GOAL_Y_LOW = COURT_WIDTH_M / 2.0 - 1.5   # 8.5 — alsó kapufa
_GOAL_Y_HIGH = COURT_WIDTH_M / 2.0 + 1.5  # 11.5 — felső kapufa

SHOOTER_LOOKBACK_S = 1.2  # a lövés előtt ennyi időn belülről keressük a lövőt
# A REPÜLŐ labdához közel álló játékos NEM birtokos. Kézben tartva a
# labda a játékossal együtt mozog (sprint alatt is 9 m/s alatt), egy
# lövés viszont 15–30 m/s. E fölött tehát a labda úton van, és a
# közelében álló beálló csak "útközben" van a röppályán.
SHOOTER_HELD_MAX_MS = 9.0
# Ritkított felvételen (ez alatti fps-nél) az EGYÜTEMŰ lövésnél a labda
# lassú (kézben tartott) kockája el is tűnhet a minták közül — ilyenkor
# a röppálya TÖRÉSPONTJA (passz-szár → lövés-szár irányváltás) mellett
# álló játékos a lövő. A törésponthoz ennyire közel kell állnia, és az
# irányváltást ekkora koszinusz-eltéréstől fogadjuk el.
SHOOTER_KINK_MAX_FPS = 15.0
SHOOTER_KINK_NEAR_M = 2.5
SHOOTER_KINK_COS = 0.9
ASSIST_WINDOW_S = 4.0     # a gól előtt ennyi időn belüli utolsó passz = gólpassz
# ELADOTT LABDA minimális tartása. A birtokos a labdához LEGKÖZELEBBI
# játékos; tömörülésnél (elzárás, beállós harc) és ritka
# labda-észlelésnél két SZEMBEN álló ember távolsága a labdától
# kockánként átbillen, és a jel átugrik a másik csapatra — ebből a
# felismerés eladott labdát gyárt. Éles meccsen ez a meccs ELŐTTI
# felállásnál is termelt eladásokat, miközben senki nem játszott.
#
# Csak a CSAPATVÁLTÁSRA követeljük meg a tartást, a csapaton belüli
# passzra NEM: az, hogy a labda átment az ELLENFÉLHEZ, nagyobb állítás,
# és fizikailag is tovább tart (a labdának oda kell érnie, és az
# ellenfélnek uralnia kell). Egy kockányi átbillenés nem ez.
#
# A küszöb óvatos: a termék alap-ritkításával (stride=3) ez ~0,36
# másodpercnyi valós idő — ennél gyorsabban valódi labdaszerzés sem
# stabilizálódik, tehát igazi eladást nem veszítünk el.
TURNOVER_MIN_HOLD_S = 0.3
SAVE_RADIUS_M = 1.6       # a labda ennyire a kapushoz érve = védés
_GK_NEAR_GOAL_M = 9.0     # a kapus csak a SAJÁT kapujánál "véd"


class EventType(str, Enum):
    PASS = "pass"           # passz (csapaton belül)
    SHOT = "shot"           # lövés (nem gól)
    GOAL = "goal"           # gól
    TURNOVER = "turnover"   # labdaeladás (az ellenfél szerzi meg)


@dataclass
class MatchEvent:
    """Egy felismert esemény.

    - t:       a frame ideje.
    - type:    az esemény típusa (EventType).
    - team:    a "cselekvő" csapat (passznál/lövésnél a támadó; labdaeladásnál a
               labdát ELVESZTŐ csapat).
    - player_id: a fő szereplő track_id-ja, ha értelmezhető, különben None.
    - detail:  opcionális kiegészítés (pl. passznál a fogadó id-ja).
    """
    t: int
    type: EventType
    team: Team
    player_id: Optional[int] = None
    detail: Optional[dict] = None


def _attacking_team_for_goal(goal_x: float, config: TacticsConfig) -> Team:
    """Melyik csapat TÁMADJA a megadott kaput (annak a kapunak a támadója)."""
    return Team.HOME if config.attacks_toward_x(Team.HOME) == goal_x else Team.AWAY


def _shooter_before(match: Match, idx: int, team: Team,
                    config: TacticsConfig, fps: float) -> Optional[int]:
    """A lövő: az utolsó labdabirtokos a TÁMADÓ csapatból a lövés előtt.

    A lövés pillanatában a labda már úton van (nincs birtokos), ezért
    visszafelé keresünk legfeljebb SHOOTER_LOOKBACK_S másodpercet.

    A lövés-eseményt a labda KAPU-MEGKÖZELÍTÉSEKOR jelöljük
    (APPROACH_X_M), nem az elengedés pillanatában. Távoli (átlövő)
    lövésnél a labda ekkor már a kapu közelében jár, és a puszta
    "legközelebbi játékos" szabály a röppálya mellett álló beállót
    tenné meg lövőnek. Mérve (a régi viselkedés): 12 m-ről elengedett
    lövések MIND a 6 m-en álló játékoshoz kerültek.

    Ezért a visszakeresés kihagyja azokat a kockákat, ahol a labda
    SEBESSÉGE már lövés-szintű (SHOOTER_HELD_MAX_MS fölött): ott a
    labda úton van, nincs birtokosa. Az első olyan kocka számít,
    ahol a labda lassú ÉS a támadó csapat egyik játékosa birtokolja —
    ez az elengedés pillanata.

    Ha ilyen kocka nincs az ablakban, `None`-t adunk: a "nem tudjuk"
    jobb, mint a magabiztosan rossz név.
    """
    return _shooter_release_before(match, idx, team, config, fps)[0]


def _shooter_release_before(match: Match, idx: int, team: Team,
                            config: TacticsConfig, fps: float):
    """Mint a `_shooter_before`, de az ELENGEDÉS kockáját is visszaadja.

    Visszatérés: (track_id, release_t) — mindkettő None, ha nincs
    találat. A release_t a lövés HELYÉNEK a kulcsa: az esemény t-je a
    kapu-megközelítés kockája, ahol a labda (ritkított felvételen
    különösen) már métereket repült — aki ott méri a lövés helyét, az
    a kapuhoz közelebbről mér, és az xG felfelé torzul."""
    frames = match.frames
    back = max(0, idx - round(SHOOTER_LOOKBACK_S * fps))
    # Ritkított felvételen az együtemű (elkapás után azonnali) lövésnél
    # a labda kézben-tartott kockája hiányozhat — a röppálya töréspontja
    # (ahol a passz-szár lövés-szárba vált) pontosabb, mint az utolsó
    # lassú birtokos (az a PASSZOLÓ lenne). Sűrű felvételen nem szólal
    # meg: ott az elengedés kockája megvan, a régi út pontos.
    if fps < SHOOTER_KINK_MAX_FPS:
        kink = _shooter_at_flight_kink(match, idx, back, team, fps)
        if kink is not None:
            return kink
    for j in range(idx, back - 1, -1):
        if _ball_speed_ms(frames, j, fps) > SHOOTER_HELD_MAX_MS:
            continue  # a labda repül — aki mellette áll, nem birtokos
        holder = ball_holder(frames[j], config)
        if holder is not None and holder.team == team:
            rt = frames[j].t
            # Követés-lyuknál a lista-szomszédság IDŐBEN messzire
            # mutathat: az elengedés-kocka csak akkor hiteles, ha az
            # eseményhez időben is közel van — különben a lövő nevét
            # megtartjuk, de a helyét nem állítjuk.
            if frames[idx].t - rt > round(SHOOTER_LOOKBACK_S * fps):
                rt = None
            return holder.track_id, rt
    return None, None


def _shooter_at_flight_kink(match: Match, idx: int, back: int,
                            team: Team, fps: float):
    """A röppálya töréspontja melletti játékos (ritkított felvételre).

    Az együtemű lövés röppályája két gyors szár: a passz-szár és a
    lövés-szár — köztük a töréspont, ahol az elkapó azonnal lőtt. A
    lövés-esemény kockája a passz-szárra is eshet (a szélső passz
    x-ben már "kapu-közelítés"), ezért a gyors szakaszokat ELŐRE is
    követjük, amíg a labda a kapu felé tart; a szárak végétől
    visszafelé keressük az első irányváltást (koszinusz <
    SHOOTER_KINK_COS). A töréspont kockáján a hozzá legközelebb álló
    saját-csapatbeli mezőnyjátékos a lövő — ha ilyen nincs
    SHOOTER_KINK_NEAR_M-en belül, nem találgatunk (None).

    Visszatérés: (track_id, release_t) vagy None.
    """
    frames = match.frames
    goal_x = 0.0 if frames[idx].ball.x < COURT_LENGTH_M / 2.0 \
        else COURT_LENGTH_M
    # A gyors, kapu felé tartó szakaszok vége az eseménytől előre.
    end = idx
    while end + 1 < len(frames):
        a, b = frames[end].ball, frames[end + 1].ball
        if a is None or b is None:
            break
        dx = b.x - a.x
        toward = (dx < 0 and goal_x == 0.0) or (dx > 0 and goal_x > 0.0)
        if not toward or math.hypot(dx, b.y - a.y) * fps <= SHOOTER_HELD_MAX_MS:
            break
        end += 1
    shot_dir = None
    for j2 in range(end, back, -1):
        a, b = frames[j2 - 1].ball, frames[j2].ball
        if a is None or b is None:
            return None
        dx, dy = b.x - a.x, b.y - a.y
        n = math.hypot(dx, dy)
        if n * fps <= SHOOTER_HELD_MAX_MS:
            return None  # lassú (kézben tartott) kocka — a régi út dönt
        if shot_dir is None:
            shot_dir = (dx / n, dy / n)
            continue
        cos = (dx / n) * shot_dir[0] + (dy / n) * shot_dir[1]
        if cos >= SHOOTER_KINK_COS:
            continue  # még a lövés-szár
        # Irányváltás: a töréspont a j2. kocka labda-helye (oda érkezett
        # a passz, onnan indult a lövés).
        kx, ky = frames[j2].ball.x, frames[j2].ball.y
        best = None
        best_d = SHOOTER_KINK_NEAR_M
        for pl in frames[j2].players:
            if pl.team != team or pl.role == "kapus":
                continue
            d = math.hypot(pl.x - kx, pl.y - ky)
            if d <= best_d:
                best, best_d = pl, d
        if best is None:
            return None
        return best.track_id, frames[j2].t
    return None


def _ball_speed_ms(frames, j: int, fps: float) -> float:
    """A labda sebessége a `j`. kockán (m/s), az előző kockához mérve.

    Az első kockán (és hiányzó labdánál) 0-t adunk: ott nincs mihez
    mérni, és a "nem tudjuk" itt ne zárja ki a birtoklást."""
    if j <= 0:
        return 0.0
    a, b = frames[j - 1].ball, frames[j].ball
    if a is None or b is None:
        return 0.0
    return math.hypot(b.x - a.x, b.y - a.y) * fps


def _save_by_goalkeeper(match: Match, idx: int, goal_x: float) -> Optional[int]:
    """Nem-gól lövésnél: hárította-e a kapus? A kapus-jelölést (role=
    "kapus", lásd goalkeeper.py) használja — ha a labda a lövés utáni
    ablakban a SAJÁT kapujánál álló kapus közelébe ér, az védés.

    Visszatérés: a védő kapus track_id-ja, vagy None (mellé/blokk)."""
    end = min(len(match.frames), idx + GOAL_LOOKAHEAD)
    for j in range(idx, end):
        f = match.frames[j]
        b = f.ball
        if b is None:
            continue
        for p in f.players:
            if p.role != "kapus" or abs(p.x - goal_x) > _GK_NEAR_GOAL_M:
                continue
            if math.hypot(p.x - b.x, p.y - b.y) <= SAVE_RADIUS_M:
                return p.track_id
    return None


# A gólvonal-átlépés két minta KÖZÖTT is megtörténhet: ritkított
# feldolgozásnál (stride) a labda kockánként métereket lép, és
# átugorhatja a GOL_TOL_M sávot. Ekkora (m/s) labdasebességig hisszük
# el a két minta közti átlépést — e fölött detektálási ugrás (zaj).
GOAL_CROSS_MAX_SPEED_MS = 45.0
# Az extrapolált (3.) gól-jel csak RITKÍTOTT felvételen él: e feletti
# fps-nél a sáv- és az átlépés-jel lefedi a valódi gólokat, az
# extrapoláció ott csak a téves találat kockázatát hozná.
GOAL_EXTRAP_MAX_FPS = 15.0


def _reaches_goal_line(match: Match, idx: int, goal_x: float) -> bool:
    """Előrenézve eléri-e a labda a gólvonalat a kapufák között (= gól)."""
    return goal_crossing_y(match, idx, goal_x) is not None


def goal_crossing_y(match: Match, idx: int, goal_x: float):
    """A gólvonal-átlépés y-ja a kapufák között (None, ha nincs átlépés).

    A gól-felismerés és a kapu-sarok (elhelyezés) rétegek KÖZÖS
    metszéspont-logikája — az elhelyezés így ritkított felvételen is
    a TÉNYLEGES beérkezési pontot kapja, nem a vonalon túli (métereket
    ugrott) minta y-ját, és nem is marad üresen, ha a sávba nem esik
    minta.

    Három, egymást kiegészítő jel — ritkított felvételen (stride) a
    labda kockánként métereket léphet, és az 1. jel sávja fölött
    "átrepülne":

    1. a labda egy MINTÁN a gólvonal GOAL_TOL_M sávjában, a kapufák
       között van (a hálóban megülő labda);
    2. a labda két EGYMÁST KÖVETŐ minta között átlépi a gólvonalat, és
       a metszéspont y-ja a kapufák közé esik;
    3. a kapu felé tartó labda a vonal előtt EGY LÉPÉSNYIRE jár, és a
       követés ott MEGSZAKAD (nincs következő minta, vagy
       teleport-ugrás jön — élesben a hálóba érő labdát a háló
       kitakarja, majd a középkezdésnél bukkan fel): az utolsó ismert
       sebességgel extrapolált metszéspont dönt. Ha a követés
       FOLYTONOSAN megy tovább (tehát láttuk volna a gólt vagy a
       védést), az extrapoláció nem szólal meg.
    """
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    max_step = GOAL_CROSS_MAX_SPEED_MS / fps
    end = min(len(match.frames), idx + GOAL_LOOKAHEAD)
    lo = max(0, idx - 1)
    balls = [match.frames[j].ball for j in range(lo, end)]

    for k, b in enumerate(balls):
        if b is None:
            continue
        # 1) minta a gólvonal-sávban, a kapufák között.
        if abs(b.x - goal_x) <= GOAL_TOL_M and _GOAL_Y_LOW <= b.y <= _GOAL_Y_HIGH:
            return b.y
        prev = balls[k - 1] if k > 0 else None
        if prev is None:
            continue
        dx, dy = b.x - prev.x, b.y - prev.y
        step = math.hypot(dx, dy)
        if step > max_step or abs(dx) < 1e-9:
            continue
        # 2) a két minta közti szakasz átlépi a gólvonalat.
        if (prev.x - goal_x) * (b.x - goal_x) < 0:
            yc = prev.y + dy * (goal_x - prev.x) / dx
            if _GOAL_Y_LOW <= yc <= _GOAL_Y_HIGH:
                return yc
        # 3) extrapolált átlépés folytonosság-törésnél: a labda a kapu
        # felé tart, a vonal egy lépésen belül — és a következő minta
        # hiányzik vagy teleport (a folytonos követés kizárja).
        toward = dx > 0 if goal_x > 0 else dx < 0
        remaining = abs(goal_x - b.x)
        if fps < GOAL_EXTRAP_MAX_FPS and toward \
                and remaining <= 1.25 * step:
            # A törést a MECCS következő kockáján nézzük, nem az ablak
            # szélén — az ablak vége nem a követés vége.
            j_next = lo + k + 1
            nxt = (match.frames[j_next].ball
                   if j_next < len(match.frames) else None)
            broken = (nxt is None
                      or math.hypot(nxt.x - b.x, nxt.y - b.y) > max_step)
            if broken:
                yc = b.y + dy * (goal_x - b.x) / dx
                if _GOAL_Y_LOW <= yc <= _GOAL_Y_HIGH:
                    return yc
    return None


@memoize_primitive("detect_shots", copy=copy_events)
def detect_shots(match: Match, config: Optional[TacticsConfig] = None) -> list[MatchEvent]:
    """Lövések és gólok felismerése a labda kinematikájából.

    Egy lövést akkor jelölünk, amikor a labda GYORSAN a kapu felé tart és (x-ben)
    megközelíti azt. Debounce: egy kapu-megközelítésből egy esemény. Gól, ha a
    labda a kapufák között eléri a gólvonalat.

    Nyitott `primitive_cache` hatókörön belül a mérés meccsenként egyszer
    fut le; a visszaadott lista mindig friss másolat (a hívók jelölhetik
    az eseményeket, pl. gólpasszal), blokk nélkül a viselkedés változatlan.
    """
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    events: list[MatchEvent] = []
    in_zone = {0.0: False, COURT_LENGTH_M: False}
    # Kapunként az utolsó (elfogadott VAGY elnyomott) lövés-jelölt ideje —
    # a csendidő ehhez képest telik.
    last_shot_t: dict = {0.0: None, COURT_LENGTH_M: None}
    cooldown = SHOT_COOLDOWN_S * fps
    prev = None

    for i, f in enumerate(match.frames):
        b = f.ball
        if b is None:
            prev = None
            continue
        for goal_x in (0.0, COURT_LENGTH_M):
            dxg = abs(b.x - goal_x)
            if prev is not None:
                vx = (b.x - prev[0]) * fps
                speed = math.hypot(b.x - prev[0], b.y - prev[1]) * fps
            else:
                vx = speed = 0.0
            toward = (vx < 0 and goal_x == 0.0) or (vx > 0 and goal_x == COURT_LENGTH_M)

            if dxg <= APPROACH_X_M and toward and speed >= SHOT_SPEED_MS and not in_zone[goal_x]:
                in_zone[goal_x] = True
                elozo = last_shot_t[goal_x]
                if elozo is not None and f.t - elozo < cooldown:
                    # Zaj-sorozat: a csendidő újraindul, esemény nem lesz.
                    last_shot_t[goal_x] = f.t
                    continue
                last_shot_t[goal_x] = f.t
                is_goal = _reaches_goal_line(match, i, goal_x)
                attacking = _attacking_team_for_goal(goal_x, config)
                shooter, release_t = _shooter_release_before(
                    match, i, attacking, config, fps)
                # Kimenetel: gól / védés (a kapus-jel alapján) / mellé-blokk.
                if is_goal:
                    detail: dict = {"outcome": "goal"}
                else:
                    gk = _save_by_goalkeeper(match, i, goal_x)
                    detail = ({"outcome": "save", "goalkeeper_id": gk}
                              if gk is not None else {"outcome": "miss"})
                if release_t is not None:
                    # Az elengedés kockája: a hely-alapú rétegek (xG,
                    # zónák) innen mérjenek, ne a kapu-megközelítésről.
                    detail["release_t"] = release_t
                events.append(MatchEvent(
                    t=f.t,
                    type=EventType.GOAL if is_goal else EventType.SHOT,
                    team=attacking,
                    player_id=shooter,
                    detail=detail,
                ))
            if dxg > APPROACH_X_M + 1.0:
                in_zone[goal_x] = False
        prev = (b.x, b.y)
    # A félidei szünet-sávba eső "lövés/gól" nem meccs-esemény (szünetben
    # nincs játék — az ilyen jel bemelegítés vagy labdaszedő), kimarad.
    # Csak HIHETŐ szünetnél (a felvétel többi része aktív) — a ritkás
    # követésű felvétel közepe nem szünet.
    try:
        from .halftime import credible_break_span
        span = credible_break_span(match)
        if span is not None:
            lo = match.frames[span[0]].t
            hi = match.frames[span[1]].t
            events = [e for e in events if not (lo <= e.t <= hi)]
    except Exception:
        pass
    return events


@memoize_primitive("detect_possession_changes", copy=copy_events)
def detect_possession_changes(match: Match,
                              config: Optional[TacticsConfig] = None) -> list[MatchEvent]:
    """Passzok (csapaton belül) és labdaeladások (az ellenfélhez) felismerése."""
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    # A ritkított feldolgozás miatt legalább két kocka.
    min_hold = max(2, round(TURNOVER_MIN_HOLD_S * fps))

    # 1) A birtokos-jel EGYBEFÜGGŐ szakaszokra bontva.
    szakaszok: list = []          # [track_id, team, kezdet_t, vege_t]
    for f in match.frames:
        holder = ball_holder(f, config)
        if holder is None:
            continue
        if szakaszok and szakaszok[-1][0] == holder.track_id:
            szakaszok[-1][3] = f.t
        else:
            szakaszok.append([holder.track_id, holder.team, f.t, f.t])

    # 2) CSAPAT-futamok: az egymást követő, azonos csapatú szakaszok.
    #    A kitartást a CSAPATRA mérjük, nem az egyes játékosra — a másik
    #    csapaton belüli passzok különben elnyelnék a jelöltet.
    futamok: list = []            # [[szakasz, ...], team, kezdet_t, vege_t]
    for sz in szakaszok:
        if futamok and futamok[-1][1] == sz[1]:
            futamok[-1][0].append(sz)
            futamok[-1][3] = sz[3]
        else:
            futamok.append([[sz], sz[1], sz[2], sz[3]])

    # 3) A túl rövid ELLENFÉL-futam nem labdaszerzés, hanem billegés: a
    #    körülötte lévő (azonos csapatú) futamokba olvad. Ismételve,
    #    mert egy összevonás újabb rövid futamot hozhat felszínre.
    valtozott = True
    while valtozott and len(futamok) >= 3:
        valtozott = False
        i = 1
        while i < len(futamok) - 1:
            elozo, kozep, kov = futamok[i - 1], futamok[i], futamok[i + 1]
            # A futam HOSSZA kockában: a záró kocka is beleszámít.
            if elozo[1] == kov[1] and (kozep[3] - kozep[2] + 1) < min_hold:
                elozo[0].extend(kov[0])
                elozo[3] = kov[3]
                del futamok[i:i + 2]
                valtozott = True
                continue
            i += 1

    # 3/b) A felvétel SZÉLEIN álló rövid futam sosem igazolja magát:
    #      nincs mellette mindkét oldalon szomszéd, ami megerősítené.
    #      A végén álló villanásból nem csinálunk labdaszerzést; az
    #      elején állóból pedig nem csinálunk labdaVESZTÉST (a rá
    #      következő váltást különben az ő nevére írnánk).
    while len(futamok) >= 2 and (futamok[-1][3] - futamok[-1][2] + 1) < min_hold:
        futamok.pop()
    while len(futamok) >= 2 and (futamok[0][3] - futamok[0][2] + 1) < min_hold:
        del futamok[0]

    # 4) Események: a futamon BELÜL passz, a futamok KÖZT eladott labda.
    events: list[MatchEvent] = []
    elozo_szakasz = None
    for futam in futamok:
        for sz in futam[0]:
            if elozo_szakasz is not None and sz[0] != elozo_szakasz[0]:
                if sz[1] == elozo_szakasz[1]:
                    events.append(MatchEvent(
                        t=sz[2], type=EventType.PASS, team=elozo_szakasz[1],
                        player_id=elozo_szakasz[0],
                        detail={"receiver_id": sz[0]},
                    ))
                else:
                    events.append(MatchEvent(
                        t=sz[2], type=EventType.TURNOVER,
                        team=elozo_szakasz[1],
                        player_id=elozo_szakasz[0],
                    ))
            elozo_szakasz = sz
    return events


def annotate_assists(match: Match, events: list[MatchEvent],
                     config: Optional[TacticsConfig] = None) -> list[MatchEvent]:
    """Gólpassz (assist) hozzárendelése a gólokhoz.

    Gólpassz: a gól előtti ASSIST_WINDOW_S időablakban az UTOLSÓ olyan
    saját-csapatbeli passz, amelynek a fogadója a gól lövője. A gól
    detail-jébe kerül ("assist_id": a passzoló track_id-ja) — az esemény-
    lista, a jelentés és az edzői összefoglaló innen olvassa."""
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = ASSIST_WINDOW_S * fps
    passes = [e for e in events if e.type == EventType.PASS]
    for g in events:
        if g.type != EventType.GOAL or g.player_id is None:
            continue
        best = None
        for p in passes:
            if not (0 <= g.t - p.t <= win) or p.team != g.team:
                continue
            if (p.detail or {}).get("receiver_id") != g.player_id:
                continue
            if best is None or p.t > best.t:
                best = p
        # Önmagának adott "passz" (track-zaj) nem gólpassz.
        if best is not None and best.player_id is not None \
                and best.player_id != g.player_id:
            g.detail = {**(g.detail or {}), "assist_id": best.player_id}
    return events


@memoize_primitive("detect_events", copy=copy_events)
def detect_events(match: Match, config: Optional[TacticsConfig] = None) -> list[MatchEvent]:
    """Az összes esemény időrendben, a lövés utáni labdaeladást elnyomva.

    A lövés után az ellenfél szinte mindig megszerzi a labdát (kapus/blokk) — ezt
    nem akarjuk külön "labdaeladásként" is jelölni, ezért a lövés/gól közelében
    lévő labdaeladásokat kihagyjuk. A gólokhoz a gólpasszt is hozzárendeljük
    (annotate_assists) — a passz-lista itt már együtt van a gólokkal.
    """
    config = config or TacticsConfig()
    shots = detect_shots(match, config)
    changes = detect_possession_changes(match, config)
    shot_times = [e.t for e in shots if e.type in (EventType.SHOT, EventType.GOAL)]

    filtered_changes = []
    for e in changes:
        if e.type == EventType.TURNOVER and any(abs(e.t - st) <= TURNOVER_SUPPRESS for st in shot_times):
            continue  # lövés után — nem külön labdaeladás
        filtered_changes.append(e)

    return annotate_assists(match, sorted(shots + filtered_changes, key=lambda e: e.t),
                            config)


def event_counts(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """Esemény-összegzés: típusonkénti darabszám."""
    events = detect_events(match, config)
    by_type: dict[str, int] = {t.value: 0 for t in EventType}
    for e in events:
        by_type[e.type.value] += 1
    return {"total": len(events), "by_type": by_type}


# Gól-koncentráció: legalább ennyi azonosított lövőjű gól kell az ítélethez,
# és ekkora részesedés számít "egy emberre épülő" gólszerzésnek.
CONC_MIN_GOALS = 5
CONC_TOP_SHARE_PCT = 40.0


def goal_concentration(match: Match,
                       config: Optional[TacticsConfig] = None) -> dict:
    """Gól-koncentráció (gólfüggés): mennyire épül EGY emberre a csapat
    gólszerzése.

    A felismert gólok lövő szerinti eloszlásából számoljuk a fő gólszerző
    részesedését. Ha a gólok nagy hányada (CONC_TOP_SHARE_PCT%) egy
    játékostól jön, az ő kikapcsolása (szoros emberfogás, korai kilépés)
    az egész támadójátékot megfojtja; ha a gólok elosztottak, csak a
    csapatszintű védekezés működik ellenük.

    Visszatérés csapatonként:
      {"goals", "scorers": [{"player_id","goals"}] (gólszám szerint),
       "top_share_pct", "concentrated"} — goals az azonosított lövőjű
    gólok száma; top_share_pct a fő gólszerző részesedése (None, ha
    goals < CONC_MIN_GOALS); concentrated True/False/None ítélet.
    """
    config = config or TacticsConfig()
    tally: dict[str, dict[int, int]] = {"home": {}, "away": {}}
    for e in detect_shots(match, config):
        if e.type != EventType.GOAL or e.player_id is None:
            continue
        side = tally[e.team.value]
        side[e.player_id] = side.get(e.player_id, 0) + 1

    out: dict = {}
    for s in ("home", "away"):
        scorers = [{"player_id": p, "goals": n}
                   for p, n in sorted(tally[s].items(), key=lambda kv: -kv[1])]
        total = sum(r["goals"] for r in scorers)
        if total >= CONC_MIN_GOALS and scorers:
            share = round(100.0 * scorers[0]["goals"] / total, 1)
            conc = share >= CONC_TOP_SHARE_PCT
        else:
            share = None
            conc = None
        out[s] = {"goals": total, "scorers": scorers,
                  "top_share_pct": share, "concentrated": conc}
    return out


def assist_network(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """Gólpassz-hálózat: ki kinek készíti elő a gólokat.

    A gólokhoz rendelt assist_id-ból (lásd annotate_assists) építjük a
    (gólpasszoló → lövő) párokat. Visszatérés csapatonként:
    {"pairs": [{"from","to","goals"}] (gólszám szerint), "leaders":
    [{"player_id","assists"}]} — a leaders a legtöbb gólpasszt adók."""
    config = config or TacticsConfig()
    events = detect_events(match, config)
    out = {"home": {"pairs": {}, "leaders": {}},
           "away": {"pairs": {}, "leaders": {}}}
    for e in events:
        if e.type != EventType.GOAL:
            continue
        aid = (e.detail or {}).get("assist_id")
        if aid is None or e.player_id is None:
            continue
        side = e.team.value
        key = (aid, e.player_id)
        out[side]["pairs"][key] = out[side]["pairs"].get(key, 0) + 1
        out[side]["leaders"][aid] = out[side]["leaders"].get(aid, 0) + 1

    result = {}
    for side in ("home", "away"):
        pairs = [{"from": a, "to": b, "goals": n}
                 for (a, b), n in sorted(out[side]["pairs"].items(),
                                         key=lambda kv: -kv[1])]
        leaders = [{"player_id": p, "assists": n}
                   for p, n in sorted(out[side]["leaders"].items(),
                                      key=lambda kv: -kv[1])]
        result[side] = {"pairs": pairs, "leaders": leaders}
    return result


# Hoki-assziszt (másod-előkészítés): a gólpassz ELŐTTI passz ennyi
# másodpercen belül érjen a gólpasszolóhoz; ennyi másod-előkészítés kell
# az ítélethez, és ekkora részarány teszi az embert rejtett szervezővé.
PREA_WINDOW_S = 6.0
PREA_MIN = 2
PREA_SHARE_PCT = 50.0


def pre_assists(match: Match,
                config: Optional[TacticsConfig] = None) -> dict:
    """Hoki-assziszt: KI adja a gólpassz ELŐTTI passzt.

    A gólpasszos (last_passers, assist_network) mindig látszik — a
    VALÓDI szervező viszont sokszor eggyel korábban van: ő adja azt a
    passzt, ami elmozdítja a falat (oldalváltás, betörés utáni
    kiosztás), a gólpassz utána már csak végrehajtás. Ez a réteg a
    gólokhoz a gólpassz előtti utolsó, a gólpasszolóhoz érkező saját
    passzt köti (PREA_WINDOW_S-en belül), és emberre összesíti.

    Edzőileg: a rejtett szervező ellen a passzsáv-zárást EGGYEL
    korábban kell kezdeni — nem a gólpasszolónál, hanem nála: ha ő nem
    tudja megjátszani a beadót, a gólgyáruk el sem indul. Saját oldalon
    ez a láthatatlan munka kimutatása: a hoki-asszisztos embert a
    statisztika (gól, gólpassz) alulméri, pedig a támadás rajta fordul.

    Visszatérés csapatonként: {"assisted_goals" (asszisztos gólok),
    "chained" (amelyikhez másod-előkészítés is köthető), "players":
    [{"player_id", "jersey", "pre_assists"}] csökkenően, "top"} — a
    "top" a vezető ember, ha legalább PREA_MIN másod-előkészítése van
    és eléri a "chained" PREA_SHARE_PCT-át (egyébként None).
    """
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    win = PREA_WINDOW_S * fps
    events = detect_events(match, config)
    passes = [e for e in events if e.type == EventType.PASS]
    # Támadás-határok: a lánc nem nyúlhat át az előző lövésen/gólon —
    # ami a lövés előtt történt, az egy MÁSIK támadás passza volt.
    shot_ts = sorted(e.t for e in events
                     if e.type in (EventType.SHOT, EventType.GOAL))

    jersey: dict = {}
    for f in match.frames:
        for p in f.players:
            if getattr(p, "jersey_number", None) is not None:
                jersey.setdefault(p.track_id, p.jersey_number)

    tally: dict = {"home": {}, "away": {}}
    counts = {"home": [0, 0], "away": [0, 0]}   # [asszisztos, láncolt]
    for g in events:
        if g.type != EventType.GOAL:
            continue
        aid = (g.detail or {}).get("assist_id")
        if aid is None:
            continue
        side = g.team.value
        counts[side][0] += 1
        # A gólpassz maga: az utolsó passz, aminek a fogadója a lövő.
        assist_pass = None
        for p in passes:
            if p.team != g.team or p.t > g.t:
                continue
            if (p.detail or {}).get("receiver_id") != g.player_id:
                continue
            if p.player_id != aid:
                continue
            if assist_pass is None or p.t > assist_pass.t:
                assist_pass = p
        if assist_pass is None:
            continue
        # A másod-előkészítés: az utolsó passz ELŐTTE, aminek a fogadója
        # a gólpasszoló — és nem ő maga adta (track-zaj). Az előző
        # lövés/gól előtti passz nem számít (az más támadás volt).
        boundary = max((t_ for t_ in shot_ts if t_ < assist_pass.t),
                       default=-1)
        best = None
        for p in passes:
            if p.team != g.team or not (0 <= assist_pass.t - p.t <= win):
                continue
            if p.t <= boundary:
                continue
            if (p.detail or {}).get("receiver_id") != aid:
                continue
            if p.player_id is None or p.player_id == aid:
                continue
            if best is None or p.t > best.t:
                best = p
        if best is None:
            continue
        counts[side][1] += 1
        tally[side][best.player_id] = tally[side].get(best.player_id, 0) + 1

    out: dict = {}
    for side in ("home", "away"):
        players = [{"player_id": pid, "jersey": jersey.get(pid),
                    "pre_assists": n}
                   for pid, n in sorted(tally[side].items(),
                                        key=lambda kv: -kv[1])]
        top = None
        chained = counts[side][1]
        if players and chained:
            lead = players[0]
            if (lead["pre_assists"] >= PREA_MIN
                    and 100.0 * lead["pre_assists"] / chained
                    >= PREA_SHARE_PCT):
                top = lead
        out[side] = {"assisted_goals": counts[side][0], "chained": chained,
                     "players": players, "top": top}
    return out


# Rejtett szervező poszt: ennyi poszthoz kötött másod-előkészítés kell
# az ítélethez, és ekkora részarány fölött mondjuk ki, hogy a
# szervezésük egy poszton fut.
PREAR_MIN_CHAINED = 3
PREAR_SHARE_PCT = 60.0


def pre_assist_roles(match: Match,
                     config: Optional[TacticsConfig] = None) -> dict:
    """Rejtett szervező poszt: MELYIK POSZTON fut a másod-előkészítés.

    A hoki-assziszt (pre_assists) az embert nevezi meg — ez a posztot:
    a gólpassz előtti passzokat az adó posztjához írja. Így a minta
    akkor is látszik, ha a nevek meccsről meccsre cserélődnek — a
    "mindig az irányító fordítja meg a falat" típusú szervezés
    posztról ismerszik meg, nem emberről.

    Edzőileg: ha a másod-előkészítésük rendre ugyanarról a posztról
    jön, a passzsáv-zárást a POSZT sávjában kell kezdeni, akárki
    játssza éppen — a cseréjük nem véd meg tőle. Saját oldalon: az egy
    posztra épülő szervezés kiszámítható, második indító-forrás kell.

    Visszatérés csapatonként: {"chained" (láncolt gólok), "roles":
    {poszt: darab}, "main_role", "share_pct", "verdict"} — az ítélet
    None, ha nincs meg a PREAR_MIN_CHAINED, vagy egyik poszt sem éri
    el a PREAR_SHARE_PCT-t.
    """
    from .roles import estimate_positions

    config = config or TacticsConfig()
    roles = estimate_positions(match, config)
    prea = pre_assists(match, config)

    out: dict = {}
    for side in ("home", "away"):
        rec = {"chained": prea[side]["chained"], "roles": {},
               "main_role": None, "share_pct": None, "verdict": None}
        bound = 0
        for row in prea[side]["players"]:
            rec_role = roles[side].get(row["player_id"])
            if rec_role is None:
                continue
            poszt = rec_role["poszt"]
            rec["roles"][poszt] = (rec["roles"].get(poszt, 0)
                                   + row["pre_assists"])
            bound += row["pre_assists"]
        rec["roles"] = dict(sorted(rec["roles"].items(),
                                   key=lambda kv: -kv[1]))
        if bound >= PREAR_MIN_CHAINED and rec["roles"]:
            poszt = max(rec["roles"], key=lambda k: rec["roles"][k])
            share = 100.0 * rec["roles"][poszt] / bound
            rec["main_role"] = poszt
            rec["share_pct"] = round(share, 1)
            if share >= PREAR_SHARE_PCT:
                rec["verdict"] = (
                    f"a másod-előkészítésük a(z) {poszt} poszton fut "
                    f"({share:.0f}%, {bound} másod-előkészítésből) — a "
                    "passzsáv-zárást a poszt sávjában kell kezdeni, "
                    "akárki játssza éppen")
        out[side] = rec
    return out


# Gólpassz-duó: ennyi közös gól kell a kettős kimondásához, és ekkora
# részarány fölött mondjuk ki, hogy a gólgyártásuk egy duón fut.
ADU_MIN_GOALS = 2
ADU_SHARE_PCT = 40.0


def assist_duos(match: Match,
                config: Optional[TacticsConfig] = None) -> dict:
    """Gólpassz-duó: MELYIK KETTŐSÖN fut a gólgyártásuk.

    A gólpassz-hálózat (assist_network) minden párost felsorol — ez
    az ÍTÉLETET: ha az asszisztos góljaik nagy része ugyanazon az
    (adó → befejező) kettősön születik, a duó bejáratott gólgyár.

    Edzőileg a duó ellen párban kell védekezni: az adót testtel, a
    kettejük passzsávját beleéréssel — ha a sáv zárva, a gépezet
    áll, mert a befejező magától nem teremt ugyanennyit. Saját
    csapatra: a bejáratott duó kiszámíthatóság is — kell egy második
    gól-tengely.

    Visszatérés csapatonként: {"assisted", "duos": [{"from", "to",
    "jersey_from", "jersey_to", "goals"}], "top", "verdict"} — a
    top/verdict None, ha nincs meg az ADU_MIN_GOALS, vagy a vezető
    kettős nem éri el az asszisztos gólok ADU_SHARE_PCT-át.
    """
    config = config or TacticsConfig()
    net = assist_network(match, config)

    jersey: dict = {}
    for f in match.frames:
        for q in f.players:
            if q.jersey_number is not None:
                jersey.setdefault(q.track_id, q.jersey_number)

    def _nev(tid):
        return str(jersey.get(tid, tid))

    result: dict = {}
    for side in ("home", "away"):
        pairs = net[side]["pairs"]
        total = sum(r["goals"] for r in pairs)
        duos = [{"from": r["from"], "to": r["to"],
                 "jersey_from": jersey.get(r["from"]),
                 "jersey_to": jersey.get(r["to"]),
                 "goals": r["goals"]} for r in pairs]
        rec = {"assisted": total, "duos": duos, "top": None,
               "verdict": None}
        if duos and duos[0]["goals"] >= ADU_MIN_GOALS and total > 0:
            share = 100.0 * duos[0]["goals"] / total
            if share >= ADU_SHARE_PCT:
                kulcs = f"{_nev(duos[0]['from'])}→{_nev(duos[0]['to'])}"
                rec["top"] = kulcs
                rec["verdict"] = (
                    f"a gólgyártásuk a(z) {kulcs} kettősön fut "
                    f"({duos[0]['goals']}/{total} asszisztos gól) — "
                    "a duó ellen párban kell védekezni: az adót "
                    "testtel, a kettejük passzsávját beleéréssel, és "
                    "a gépezet áll")
        result[side] = rec
    return result


# Passz-hossz: ennyi mért passz kell az ítélethez; e fölött "hosszú" a
# passz, és ekkora hosszú-arány jelent direkt (kockázatos) passzjátékot.
PLEN_MIN_PASSES = 15
PLEN_LONG_M = 10.0
PLEN_LONG_PCT = 30.0


# Passz-hossz-állás: a hosszú passzok részaránya az eredményjelző szerint.
PLS_MIN_PASSES = 10   # az összevetett állapotokban ennyi-ennyi passz kell
PLS_GAP_PP = 12.0     # ekkora hosszú-passz többlet számít mintázatnak


def pass_length_by_score(match: Match,
                         config: Optional[TacticsConfig] = None) -> dict:
    """Passz-hossz-állás: MIKOR váltanak hosszú labdákra.

    A passz-hossz profil (pass_length) a meccs egészét nézi — ez az
    eredményjelzőn: minden passznál a passzoló csapat pillanatnyi
    gólkülönbségét vesszük, és állásonként mérjük a hosszú
    (PLEN_LONG_M feletti) passzok részarányát. A hátrányban megugró
    hosszú-passz arány a kapkodó direkt játék: a lemaradó csapat
    átdobálná magát a védelmen — ezek a labdák a passzsávra ülve
    elfoghatók.

    Edzőileg: aki hátrányban hosszú labdázik, annál vezetésnél a
    passzsávokra kell ülni — az elfogás kontrát ér; a saját oldalon
    a hátrányban is rövid, biztos kombináció a téma.

    Visszatérés csapatonként: {"leading"/"trailing"/"level":
    {"passes", "long"}, "verdict"} — a verdict "hátrányban hosszú
    labdákra váltanak" (PLS_GAP_PP többletnél), különben None
    (állapotonként PLS_MIN_PASSES-nél kevesebb passznál is).
    """
    config = config or TacticsConfig()
    by_t = {f.t: f for f in match.frames}
    events = detect_events(match, config)
    goals = [(e.t, e.team.value) for e in events
             if e.type == EventType.GOAL]
    out = {side: {k: {"passes": 0, "long": 0}
                  for k in ("leading", "trailing", "level")}
           for side in ("home", "away")}
    for e in events:
        if e.type != EventType.PASS or e.player_id is None:
            continue
        rid = (e.detail or {}).get("receiver_id")
        f = by_t.get(e.t)
        if rid is None or f is None:
            continue
        passer = next((p for p in f.players
                       if p.track_id == e.player_id), None)
        receiver = next((p for p in f.players if p.track_id == rid),
                        None)
        if passer is None or receiver is None:
            continue
        d = math.hypot(receiver.x - passer.x, receiver.y - passer.y)
        side = e.team.value
        own = sum(1 for (t, tm) in goals if t < e.t and tm == side)
        opp = sum(1 for (t, tm) in goals if t < e.t and tm != side)
        state = ("leading" if own > opp
                 else "trailing" if own < opp else "level")
        rec = out[side][state]
        rec["passes"] += 1
        if d >= PLEN_LONG_M:
            rec["long"] += 1
    for side in ("home", "away"):
        buckets = out[side]
        verdict = None
        tr = buckets["trailing"]
        rest_p = (buckets["leading"]["passes"]
                  + buckets["level"]["passes"])
        rest_l = buckets["leading"]["long"] + buckets["level"]["long"]
        if tr["passes"] >= PLS_MIN_PASSES and rest_p >= PLS_MIN_PASSES:
            diff = (100.0 * tr["long"] / tr["passes"]
                    - 100.0 * rest_l / rest_p)
            if diff >= PLS_GAP_PP:
                verdict = "hátrányban hosszú labdákra váltanak"
        buckets["verdict"] = verdict
    return out


def pass_length(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """Passz-hossz profil: rövid kombinációs vagy hosszú, direkt passzjáték.

    Minden felismert passznál a passzoló és a fogadó távolságát mérjük a
    passz pillanatában. A sok hosszú passz (PLEN_LONG_M fölött) direkt,
    kockázatos játékot jelez — a passzsávra ülve elfogható; a rövid
    passzos kombináció présállóbb, de lassabban ér kaput.

    Visszatérés csapatonként:
      {"passes", "avg_m", "long_passes", "long_pct"} — a mért passzok
    száma, átlaghossza, a hosszúak száma és aránya; avg_m/long_pct None,
    ha passes < PLEN_MIN_PASSES.
    """
    config = config or TacticsConfig()
    by_t = {f.t: f for f in match.frames}
    acc = {"home": [0, 0.0, 0], "away": [0, 0.0, 0]}  # n, összeg, hosszú
    for e in detect_events(match, config):
        if e.type != EventType.PASS or e.player_id is None:
            continue
        rid = (e.detail or {}).get("receiver_id")
        f = by_t.get(e.t)
        if rid is None or f is None:
            continue
        passer = next((p for p in f.players if p.track_id == e.player_id),
                      None)
        receiver = next((p for p in f.players if p.track_id == rid), None)
        if passer is None or receiver is None:
            continue
        d = math.hypot(receiver.x - passer.x, receiver.y - passer.y)
        rec = acc[e.team.value]
        rec[0] += 1
        rec[1] += d
        if d >= PLEN_LONG_M:
            rec[2] += 1

    out: dict = {}
    for s in ("home", "away"):
        n, total, long_n = acc[s]
        ok = n >= PLEN_MIN_PASSES
        out[s] = {
            "passes": n,
            "avg_m": round(total / n, 1) if ok else None,
            "long_passes": long_n,
            "long_pct": round(100.0 * long_n / n, 1) if ok else None,
        }
    return out


# Lövés-sebesség: hihetőségi plafon (követési hiba fölötte) és a
# sebesség-méréshez nézett ablak a lövés-esemény után (kockában).
SHOT_SPEED_MAX_MS = 45.0     # ~160 km/h fölött mérési hiba
SHOT_SPEED_WINDOW = 8


def shot_speeds(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """Lövés-sebességek a labda-kinematikából.

    Minden felismert lövésnél a lövést követő pár kockában mért
    leggyorsabb labda-elmozdulás adja a lövés sebességét (m/s → km/h).
    A hihetetlen (SHOT_SPEED_MAX_MS feletti) értékeket eldobjuk.

    Visszatérés: {"shots": [{"t","team","player_id","speed_kmh"}],
    "teams": {"home"/"away": {"avg_kmh", "max_kmh", "n"}},
    "fastest": {"t","team","player_id","speed_kmh"} | None}
    """
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    frames_by_t = {f.t: f for f in match.frames}

    out_shots = []
    for e in detect_shots(match, config):
        peak = 0.0
        prev = None
        for dt in range(SHOT_SPEED_WINDOW + 1):
            fr = frames_by_t.get(e.t + dt)
            if fr is None or fr.ball is None:
                prev = None
                continue
            if prev is not None:
                v = math.hypot(fr.ball.x - prev[0], fr.ball.y - prev[1]) * fps
                if v <= SHOT_SPEED_MAX_MS:
                    peak = max(peak, v)
            prev = (fr.ball.x, fr.ball.y)
        if peak > 0:
            out_shots.append({"t": e.t, "team": e.team.value,
                              "player_id": e.player_id,
                              "speed_kmh": round(peak * 3.6, 1)})

    teams = {}
    for side in ("home", "away"):
        vals = [s_["speed_kmh"] for s_ in out_shots if s_["team"] == side]
        teams[side] = {
            "avg_kmh": round(sum(vals) / len(vals), 1) if vals else 0.0,
            "max_kmh": max(vals) if vals else 0.0,
            "n": len(vals),
        }
    fastest = max(out_shots, key=lambda s_: s_["speed_kmh"], default=None)
    return {"shots": out_shots, "teams": teams, "fastest": fastest}


# Lövőerő-esés (fáradás-jel): félidőnként legalább ennyi mért lövés kell az
# összevetéshez, és ekkora (%-os) átlagsebesség-esés számít jelzésnek.
FADE_MIN_SHOTS = 3
FADE_DROP_PCT = 8.0


def shot_speed_fade(match: Match, config: Optional[TacticsConfig] = None) -> dict:
    """Lövőerő-esés: a lövés-sebesség változása az 1. és a 2. félidő között —
    a fáradás egyik legobjektívebb jele.

    A mért lövés-sebességeket (shot_speeds) a felismert félidő (detect_halftime)
    mentén két csoportra bontjuk, és csapatonként összevetjük az átlagokat.
    Ha a 2. félidei átlag érdemben (FADE_DROP_PCT%) alacsonyabb, a csapat
    lövőereje fárad — a hajrában puhábbak a lövései; ha nő, frissen pörgetik
    a végét (mély rotáció / jó kondíció).

    Visszatérés csapatonként:
      {"fh_n", "fh_avg_kmh", "sh_n", "sh_avg_kmh", "drop_pct"} — az 1./2.
    félidei mért lövésszám és átlagsebesség; drop_pct a százalékos esés
    (pozitív = lassul, negatív = gyorsul), None, ha nincs elég mért lövés
    (félidőnként FADE_MIN_SHOTS) vagy nincs félidő-jel.
    """
    from .halftime import detect_halftime

    config = config or TacticsConfig()
    empty = {"fh_n": 0, "fh_avg_kmh": 0.0, "sh_n": 0, "sh_avg_kmh": 0.0,
             "drop_pct": None}
    out = {"home": dict(empty), "away": dict(empty)}
    ht = detect_halftime(match)
    if ht is None:
        return out
    shots = shot_speeds(match, config)["shots"]
    for side in ("home", "away"):
        fh = [s_["speed_kmh"] for s_ in shots
              if s_["team"] == side and s_["t"] <= ht]
        sh = [s_["speed_kmh"] for s_ in shots
              if s_["team"] == side and s_["t"] > ht]
        rec = out[side]
        rec["fh_n"] = len(fh)
        rec["sh_n"] = len(sh)
        rec["fh_avg_kmh"] = round(sum(fh) / len(fh), 1) if fh else 0.0
        rec["sh_avg_kmh"] = round(sum(sh) / len(sh), 1) if sh else 0.0
        if len(fh) >= FADE_MIN_SHOTS and len(sh) >= FADE_MIN_SHOTS \
                and rec["fh_avg_kmh"] > 0:
            rec["drop_pct"] = round(
                100.0 * (rec["fh_avg_kmh"] - rec["sh_avg_kmh"])
                / rec["fh_avg_kmh"], 1)
    return out


def pass_network(match: Match, config: Optional[TacticsConfig] = None,
                 top: int = 5) -> dict:
    """Passz-hálózat: ki kinek adogat — a játékszervezés fő tengelye.

    A PASS eseményekből (adó → fogadó) építjük a leggyakoribb párokat és
    a legtöbb passzban részt vevő játékosokat. A gólpassz-hálózattal
    (assist_network) szemben itt MINDEN passz számít, nem csak a gólt
    előkészítő — így a csapat játékának szerkezete látszik: kin megy át
    a labda, melyik kapcsolat a "motor".

    Visszatérés csapatonként: {"total_passes", "pairs":
    [{"from","to","passes"}] (top szerint), "hubs":
    [{"player_id","passes"}] — adott VAGY kapott passzok összege}."""
    config = config or TacticsConfig()
    events = detect_events(match, config)
    out = {"home": {"pairs": {}, "hubs": {}, "total": 0},
           "away": {"pairs": {}, "hubs": {}, "total": 0}}
    for e in events:
        if e.type != EventType.PASS:
            continue
        rid = (e.detail or {}).get("receiver_id")
        if rid is None or e.player_id is None:
            continue
        side = e.team.value
        rec = out[side]
        rec["total"] += 1
        key = (e.player_id, rid)
        rec["pairs"][key] = rec["pairs"].get(key, 0) + 1
        for pid in (e.player_id, rid):
            rec["hubs"][pid] = rec["hubs"].get(pid, 0) + 1

    result = {}
    for side in ("home", "away"):
        rec = out[side]
        pairs = [{"from": a, "to": b, "passes": n}
                 for (a, b), n in sorted(rec["pairs"].items(),
                                         key=lambda kv: -kv[1])[:top]]
        hubs = [{"player_id": p, "passes": n}
                for p, n in sorted(rec["hubs"].items(),
                                   key=lambda kv: -kv[1])[:top]]
        result[side] = {"total_passes": rec["total"], "pairs": pairs,
                        "hubs": hubs}
    return result


# Lövő-erő: ennyi mért lövéstől nevezünk meg egy játékost, és ennyi
# km/h-val a csapatátlag felett számít bombázónak.
SHOOTER_POWER_MIN_SHOTS = 4
SHOOTER_POWER_GAP_KMH = 8.0


def shooter_power(match: Match,
                  config: Optional[TacticsConfig] = None) -> dict:
    """Lövő-erő: kinek a legkeményebb a lövése.

    A lövés-sebességek (shot_speeds) csapat-átlagot és egy
    leggyorsabb lövést adnak — ez lövőnkénti profil: ki lő rendre a
    csapatátlag felett. A bombázó ellen a fal ne "vakon" blokkoljon,
    hanem zárja a szöget, a kapusnak pedig korábban kell indulnia;
    saját olvasatban tudni kell, kire lehet a hajrában bízni a
    távoli befejezést.

    Visszatérés csapatonként: {"avg_kmh", "players": [{"player_id",
    "shots", "avg_kmh", "max_kmh"}], "cannon"} — a lista átlagsebesség
    szerint csökkenő; a cannon az első olyan játékos, akinek legalább
    SHOOTER_POWER_MIN_SHOTS mért lövése van, és az átlaga legalább
    SHOOTER_POWER_GAP_KMH-val a csapatátlag felett (egyébként None).
    """
    config = config or TacticsConfig()
    speeds = shot_speeds(match, config)
    out: dict = {}
    for side in ("home", "away"):
        rows = [s_ for s_ in speeds["shots"]
                if s_["team"] == side and s_["player_id"] is not None]
        team_vals = [s_["speed_kmh"] for s_ in speeds["shots"]
                     if s_["team"] == side]
        team_avg = (round(sum(team_vals) / len(team_vals), 1)
                    if team_vals else 0.0)
        tally: dict = {}
        for s_ in rows:
            tally.setdefault(s_["player_id"], []).append(s_["speed_kmh"])
        players = [{"player_id": pid, "shots": len(vals),
                    "avg_kmh": round(sum(vals) / len(vals), 1),
                    "max_kmh": max(vals)}
                   for pid, vals in tally.items()]
        players.sort(key=lambda p: -p["avg_kmh"])
        cannon = next(
            (p for p in players
             if p["shots"] >= SHOOTER_POWER_MIN_SHOTS
             and p["avg_kmh"] - team_avg >= SHOOTER_POWER_GAP_KMH), None)
        out[side] = {"avg_kmh": team_avg, "players": players,
                     "cannon": cannon}
    return out


# Kezesség-becslés: ennyi értékelhető lövés kell egy játékos ítéletéhez,
# és e feletti egyoldalúság (bal- vagy jobb-jel aránya) adja a kezességet.
HANDED_MIN_SHOTS = 4
HANDED_SHARE_PCT = 70.0
# A labda-eltolás értékelhető sávja a lövő testétől (méter): ez alatt
# zaj (a labda "a testben" van), e felett már nem a kézben van a labda.
HANDED_OFF_MIN_M = 0.1
HANDED_OFF_MAX_M = 1.5


def shooting_hand(match: Match,
                  config: Optional[TacticsConfig] = None) -> dict:
    """Kezesség-becslés: MELYIK KÉZZEL lőnek a lövőik.

    A lövés elengedése előtti kockán a labda a lövő testéhez képest a
    dobó kéz oldalán van — a kapu-irányhoz mért oldal-eltolás előjele
    lövésenként megmondja a kezet, játékosonként összesítve pedig a
    kezességet. A balkezes lövő a védelemnek tükör-feladat: a sánc
    kezét és a kapus alapállását át kell állítani ellene (a jobb
    oldalról befelé jövő balkezes a szokott sánc mellett lő el);
    saját olvasatban a balkezes a jobbszélső/jobbátlövő poszt igazi
    fegyvere.

    Visszatérés csapatonként: {"players": [{"player_id", "jersey",
    "shots", "left", "right", "goals", "hand", "share_pct"}], "lefty"}
    — a "hand" "bal"/"jobb" ítélet legalább HANDED_MIN_SHOTS
    értékelhető lövéstől és HANDED_SHARE_PCT egyoldalúságtól
    (egyébként None); a "lefty" a legtöbbet lövő balkezes-ítéletű
    játékos, ha van.
    """
    config = config or TacticsConfig()
    idx_of = {f.t: i for i, f in enumerate(match.frames)}
    goal_y = COURT_WIDTH_M / 2.0

    tally: dict = {"home": {}, "away": {}}
    jersey: dict = {}
    for e in detect_shots(match, config):
        if e.player_id is None:
            continue
        i = idx_of.get(e.t)
        if i is None or i < 1:
            continue
        # Az elengedés kockájáról mérünk (release_t): ott a labda még a
        # kézben van. Az esemény-kocka előtti kockán — ritkított
        # felvételen különösen — a labda már repül, és a röppálya
        # oldal-eltolása hamis kezesség-jelet adna.
        i0 = idx_of.get((e.detail or {}).get("release_t"))
        if i0 is None:
            i0 = i - 1
        if i0 + 1 >= len(match.frames):
            continue
        f0, f1 = match.frames[i0], match.frames[i0 + 1]
        if f0.ball is None or f1.ball is None:
            continue
        sp = next((p for p in f0.players if p.track_id == e.player_id), None)
        if sp is None:
            continue
        if getattr(sp, "jersey_number", None) is not None:
            jersey.setdefault(e.player_id, sp.jersey_number)
        # Labda-eltolás a testtől az elengedés előtti kockán.
        ox, oy = f0.ball.x - sp.x, f0.ball.y - sp.y
        off = math.hypot(ox, oy)
        if not (HANDED_OFF_MIN_M <= off <= HANDED_OFF_MAX_M):
            continue
        # A megtámadott kapu a labda mozgás-irányából; kapu-irány a lövőtől.
        goal_x = COURT_LENGTH_M if f1.ball.x > f0.ball.x else 0.0
        gx, gy = goal_x - sp.x, goal_y - sp.y
        if math.hypot(gx, gy) < 1e-6:
            continue
        cross = gx * oy - gy * ox
        rec = tally[e.team.value].setdefault(
            e.player_id, {"left": 0, "right": 0, "goals": 0})
        # cross > 0: a labda a kapu-irány BAL oldalán (felülnézetben) —
        # a kapu felé néző lövő bal keze felől.
        rec["left" if cross > 0 else "right"] += 1
        if e.type == EventType.GOAL:
            rec["goals"] += 1

    out: dict = {}
    for side in ("home", "away"):
        players = []
        for pid, rec in tally[side].items():
            shots = rec["left"] + rec["right"]
            major = max(rec["left"], rec["right"])
            share = round(100.0 * major / shots, 1) if shots else None
            hand = None
            if shots >= HANDED_MIN_SHOTS and share is not None \
                    and share >= HANDED_SHARE_PCT:
                hand = "bal" if rec["left"] > rec["right"] else "jobb"
            players.append({"player_id": pid, "jersey": jersey.get(pid),
                            "shots": shots, "left": rec["left"],
                            "right": rec["right"], "goals": rec["goals"],
                            "hand": hand, "share_pct": share})
        players.sort(key=lambda p: -p["shots"])
        lefty = next((p for p in players if p["hand"] == "bal"), None)
        out[side] = {"players": players, "lefty": lefty}
    return out


# Gólpassz-zónák: ennyi zónázott gólpassztól ítélünk, és e feletti
# részarány jelenti, hogy egy vonalról jönnek az előkészítések.
ASSIST_ZONE_MIN = 4
ASSIST_ZONE_SHARE = 50.0
# A gólpassz-forrás (attack_types.assist_sources) zóna-nevei edzői
# nyelven — a zónázás maga ott történik, hogy egy helyen legyen.
ASSIST_ZONE_NAMES = {"szél": "szélről", "közép": "beállótól",
                     "hátsó": "átlövésből"}


def assist_zones(match: Match,
                 config: Optional[TacticsConfig] = None) -> dict:
    """Gólpassz-zónák: HONNAN érkezik a gólpassz — edzői ítélettel.

    A gólpassz-forrás (assist_sources) számolja meg, melyik zónából
    (szél / közép / hátsó) érkeznek az előkészítések; ez a réteg abból
    von le ítéletet: van-e EGY vonal, amiről a gólpasszaik fele jön.
    A gólpassz-hálózat (assist_network) a ki-kinek kérdést nézi.

    Edzőileg ez az átadás-vonal, amit zárni kell: ha a gólpasszaik
    fele a szélről jön, a szélső–beálló tengelyt kell elvágni; ha a
    beállótól, a beálló körüli kiszolgálást; ha átlövésből, az
    átlövők passz-sávját (előrelépés a lövő-vonalba).

    Visszatérés csapatonként: {"assists", "zones": {zóna: gólpasszok},
    "top": {"zone", "goals", "share_pct"} | None} — a "top" akkor van
    kitöltve, ha legalább ASSIST_ZONE_MIN zónázott gólpassz van, a
    vezető zóna részaránya eléri az ASSIST_ZONE_SHARE-t, és nincs vele
    holtversenyben másik zóna.
    """
    from .attack_types import assist_sources

    src = assist_sources(match, config)
    out: dict = {}
    for side in ("home", "away"):
        rec_src = src[side]
        zones = {name: rec_src[key]
                 for key, name in ASSIST_ZONE_NAMES.items()
                 if rec_src.get(key)}
        zones = dict(sorted(zones.items(), key=lambda kv: -kv[1]))
        rec = {"assists": rec_src["assists"], "zones": zones,
               "top": None}
        items = list(zones.items())
        if rec["assists"] >= ASSIST_ZONE_MIN and items:
            zone, n = items[0]
            share = 100.0 * n / rec["assists"]
            # Holtverseny esetén nincs "vezető" vonal: ilyenkor nem
            # egy átadás-vonalról jönnek az előkészítések.
            tie = len(items) > 1 and items[1][1] == n
            if share >= ASSIST_ZONE_SHARE and not tie:
                rec["top"] = {"zone": zone, "goals": n,
                              "share_pct": round(share, 1)}
        out[side] = rec
    return out


# Gólpassz-hossz: ennél hosszabb előkészítés számít hosszú indításnak,
# ennyi gólpasszos gól kell az ítélethez, és e feletti / alatti hosszú-
# arány a hosszú indításos, illetve a rövid kombinációs gólgyártás jele.
ASR_LONG_M = 8.0
ASR_MIN_ASSISTED = 5
ASR_LONG_PCT = 50.0
ASR_SHORT_PCT = 20.0


def assist_ranges(match: Match,
                  config: Optional[TacticsConfig] = None) -> dict:
    """Gólpassz-hossz: HOSSZÚ INDÍTÁSOKBÓL vagy RÖVID KOMBINÁCIÓKBÓL
    élnek.

    A gólpassz-hálózat azt mondja meg, ki kinek készít elő — ez azt,
    MILYEN MESSZIRŐL: minden gólpasszos gólnál megmérjük az előkészítő
    és a lövő távolságát a gól pillanatában.

    Edzőileg: a hosszú gólpasszokból élő csapat ellen a passzsávakat
    kell zárni — a hosszú labda elfogható, és minden elfogás kontrát
    ér; a rövid kombinációkból élő ellen a kis terület védése dönt —
    hangos váltások és testes besegítés a hatos előtt.

    Visszatérés csapatonként: {"assisted", "long", "long_pct",
    "verdict"} — a long_pct/verdict None ASR_MIN_ASSISTED alatt; a
    verdict "hosszú gólpasszokból élnek" / "rövid kombinációkból
    élnek" / None.
    """
    import math

    from .tactics import TacticsConfig as _TC

    config = config or _TC()
    by_t = {f.t: f for f in match.frames}
    events = annotate_assists(match, detect_events(match, config), config)

    out = {side: {"assisted": 0, "long": 0, "long_pct": None,
                  "verdict": None} for side in ("home", "away")}
    for g in events:
        if g.type != EventType.GOAL:
            continue
        aid = (g.detail or {}).get("assist_id")
        if aid is None or g.player_id is None:
            continue
        f = by_t.get(g.t)
        if f is None:
            continue
        passer = next((p for p in f.players if p.track_id == aid), None)
        scorer = next((p for p in f.players
                       if p.track_id == g.player_id), None)
        if passer is None or scorer is None:
            continue
        rec = out[g.team.value]
        rec["assisted"] += 1
        if math.hypot(passer.x - scorer.x,
                      passer.y - scorer.y) >= ASR_LONG_M:
            rec["long"] += 1

    for side in ("home", "away"):
        rec = out[side]
        if rec["assisted"] >= ASR_MIN_ASSISTED:
            pct = 100.0 * rec["long"] / rec["assisted"]
            rec["long_pct"] = round(pct, 1)
            if pct >= ASR_LONG_PCT:
                rec["verdict"] = "hosszú gólpasszokból élnek"
            elif pct <= ASR_SHORT_PCT:
                rec["verdict"] = "rövid kombinációkból élnek"
    return out
