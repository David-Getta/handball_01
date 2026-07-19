"""Félidő-érzékelés és térfélcsere-normalizálás.

Teljes meccset EGYBEN tartalmazó felvételnél a rendszer eddig nem tudta,
mikor volt a félidő — pedig a térfélcsere minden irány-érzékeny elemzést
érint (támadás-irány, saját kapu, hétméteres-oldal, 7a6). Ez a modul:

1. FELISMERI a szünetet: hosszú, alacsony aktivitású szakasz a felvétel
   közepe táján (kevés mért játékos a pályán, a labda eltűnik/áll).
2. ELLENŐRZI a térfélcserét: a hazai csapat súlypontja a szünet előtt és
   után melyik térfélen volt — ha átvált, a csapatok cseréltek.
3. NORMALIZÁL: a második félidő koordinátáit tükrözi (x→40−x, y→20−y),
   így a támadás-irányok a TELJES meccsen egységesek, és minden meglévő
   elemzés változtatás nélkül helyesen működik.

Félidőnként külön feldolgozott felvételeknél nincs dolga (nem talál
szünetet) — nem árt, csak a teljes-meccses felvételt javítja.
"""

from __future__ import annotations

from typing import Optional

from ..models.tracking import Match, PositionSource, Team
from .calibration import COURT_LENGTH_M, COURT_WIDTH_M

# Szünet-felismerés küszöbei:
BREAK_WINDOW_S = 10.0     # ekkora ablakokban mérjük az aktivitást
BREAK_MIN_S = 60.0        # legalább ennyi alacsony aktivitás = szünet
LOW_PLAYERS = 4.0         # ablak-átlagban ennél kevesebb mért játékos = áll a játék
MID_LO, MID_HI = 0.2, 0.8  # a szünetet a felvétel középső részén keressük

# Térfélcsere: a súlypont-eltolódásnak legalább ekkora és ellentétes
# oldalra esőnek kell lennie (méter, a felezővonaltól).
SWAP_MIN_SHIFT_M = 3.0


def detect_halftime(match: Match) -> Optional[int]:
    """A félidei szünet KÖZEPÉNEK frame-ideje, vagy None, ha nincs szünet.

    Ablakonként méri az aktivitást (mért játékosok átlagos száma); a
    felvétel középső 20–80%-ában keresi a leghosszabb alacsony-aktivitású
    összefüggő szakaszt, és csak BREAK_MIN_S felett fogadja el.
    """
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    total = len(match.frames)
    if total < 2:
        return None
    win = max(1, round(BREAK_WINDOW_S * fps))

    lows: list[bool] = []
    starts: list[int] = []
    for w0 in range(0, total, win):
        frames = match.frames[w0:w0 + win]
        measured = sum(
            sum(1 for p in f.players if p.source == PositionSource.MEASURED)
            for f in frames)
        avg_players = measured / max(1, len(frames))
        lows.append(avg_players < LOW_PLAYERS)
        starts.append(w0)

    # A leghosszabb összefüggő "alacsony" futam a középső tartományban.
    best: Optional[tuple[int, int]] = None  # (hossz ablakban, kezdő index)
    run_start = None
    for i in range(len(lows) + 1):
        low = lows[i] if i < len(lows) else False
        mid_ok = i < len(lows) and MID_LO * total <= starts[i] <= MID_HI * total
        if low and mid_ok and run_start is None:
            run_start = i
        elif (not low or not mid_ok) and run_start is not None:
            length = i - run_start
            if best is None or length > best[0]:
                best = (length, run_start)
            run_start = None
    if best is None or best[0] * win / fps < BREAK_MIN_S:
        return None
    mid_idx = min(total - 1, starts[best[1]] + (best[0] * win) // 2)
    return match.frames[mid_idx].t


def _centroid_x(match: Match, team: Team, t_from: int, t_to: int) -> Optional[float]:
    """A csapat mért pozícióinak átlagos x-e a [t_from, t_to) tartományban."""
    total = 0.0
    n = 0
    for f in match.frames:
        if not (t_from <= f.t < t_to):
            continue
        for p in f.players:
            if p.team == team and p.source == PositionSource.MEASURED:
                total += p.x
                n += 1
    return total / n if n else None


def detect_side_swap(match: Match, halftime_t: int) -> bool:
    """Igaz, ha a csapatok a szünet után térfelet cseréltek.

    Jele: a hazai (és a vendég) súlypont a felezővonal MÁSIK oldalára
    kerül, legalább SWAP_MIN_SHIFT_M-rel a felezőtől mindkét félidőben.
    """
    mid = COURT_LENGTH_M / 2.0
    last_t = match.frames[-1].t + 1
    swapped = 0
    checked = 0
    for team in (Team.HOME, Team.AWAY):
        a = _centroid_x(match, team, 0, halftime_t)
        b = _centroid_x(match, team, halftime_t, last_t)
        if a is None or b is None:
            continue
        checked += 1
        if (a - mid) * (b - mid) < 0 and abs(a - mid) >= SWAP_MIN_SHIFT_M \
                and abs(b - mid) >= SWAP_MIN_SHIFT_M:
            swapped += 1
    return checked > 0 and swapped == checked


def normalize_sides(match: Match, halftime_t: int) -> int:
    """A második félidő tükrözése (x→40−x, y→20−y) — a támadás-irányok a
    teljes meccsen egységesek lesznek. Visszaadja a tükrözött kockák számát.
    """
    n = 0
    for f in match.frames:
        if f.t < halftime_t:
            continue
        for p in f.players:
            p.x = COURT_LENGTH_M - p.x
            p.y = COURT_WIDTH_M - p.y
        if f.ball is not None:
            f.ball.x = COURT_LENGTH_M - f.ball.x
            f.ball.y = COURT_WIDTH_M - f.ball.y
        n += 1
    return n


def auto_normalize(match: Match) -> Optional[dict]:
    """Félidő-felismerés + térfélcsere-normalizálás egy lépésben.

    Visszatérés: {"halftime_t", "swapped", "mirrored_frames"} ha volt
    felismert szünet, különben None.
    """
    ht = detect_halftime(match)
    if ht is None:
        return None
    swapped = detect_side_swap(match, ht)
    mirrored = normalize_sides(match, ht) if swapped else 0
    return {"halftime_t": ht, "swapped": swapped, "mirrored_frames": mirrored}


# A szünet utáni kezdés ablaka: a 2. félidő első percei.
RESTART_WINDOW_S = 300.0


def second_half_start(match: Match, config=None) -> Optional[dict]:
    """A szünet utáni kezdés mérlege: ki üt először a 2. félidőben.

    A felismert félidő utáni RESTART_WINDOW_S-ben (5 perc) dobott gólok
    csapatonként — az "öltözőből rosszul kijövő" csapat visszatérő
    mintája felderítési kulcsot érdemel. None, ha nincs felismert
    félidő-jel.
    """
    from .event_detection import EventType, detect_shots
    from .tactics import TacticsConfig

    ht = detect_halftime(match)
    if ht is None:
        return None
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    t_end = ht + round(RESTART_WINDOW_S * fps)
    goals = {"home": 0, "away": 0}
    for e in detect_shots(match, config or TacticsConfig()):
        if e.type == EventType.GOAL and ht <= e.t <= t_end:
            goals[e.team.value] += 1
    return {"halftime_s": round(ht / fps, 1),
            "home": goals["home"], "away": goals["away"]}
