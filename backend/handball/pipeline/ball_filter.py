"""
[Labda-utómunka] — a zajos labda-detektálás szűrése és a hézagok pótlása.

A valódi felvételen a labdát alacsony küszöbbel detektáljuk (kicsi és gyors),
ezért a nyers idősor zajos:
- KIUGRÓ PONTOK: téves észlelés (pl. fej, cipő, reklámtábla) a pálya másik
  felén — fizikailag lehetetlen ugrás az idősorozatban,
- HÉZAGOK: képkockák, ahol a labda nem látszik (takarás, motion blur).

A birtoklás-, passz- és lövés-felismerés folytonos labda-pályát igényel, ezért
a feldolgozás végén ([H] előtt):
1. a kiugró pontokat eldobjuk (ha egy észlelés MINDKÉT szomszédjától
   lehetetlenül messze van, az nem a labda),
2. a rövid hézagokat lineárisan pótoljuk, csökkentett confidence-szel
   (a hosszú hézagot NEM találjuk ki — ott tényleg nincs adat).

Tiszta adatfeldolgozás, videó nélkül tesztelhető.
"""

from __future__ import annotations

import math

from ..models.tracking import Match, Ball

# Fizikai plauzibilitás: a kézilabda átlövésnél sem megy ~30 m/s fölé.
MAX_BALL_SPEED_MS = 30.0
# Ennél hosszabb hézagot nem pótolunk (nincs alapunk kitalálni, merre járt).
DEFAULT_MAX_GAP_FRAMES = 12
# A pótolt (interpolált) pozíciók megbízhatósága — a kliens/elemzés lássa,
# hogy ez származtatott adat.
INTERPOLATED_CONFIDENCE = 0.4


def _dist(a: Ball, b: Ball) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def remove_ball_outliers(match: Match, max_speed_ms: float = MAX_BALL_SPEED_MS) -> int:
    """A fizikailag lehetetlen labda-észlelések eldobása. Visszaadja a darabszámot.

    Egy észlelés kiugró, ha az ELŐZŐ és a KÖVETKEZŐ labdás képkockához képest is
    gyorsabb mozgást feltételezne a megengedettnél — vagyis a szomszédok egymással
    konzisztensek, csak ez a pont lóg ki (tipikus téves detektálás).
    """
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    # A labdás képkockák indexei (időrendben).
    idxs = [i for i, f in enumerate(match.frames) if f.ball is not None]
    removed = 0
    for k in range(1, len(idxs) - 1):
        i_prev, i_cur, i_next = idxs[k - 1], idxs[k], idxs[k + 1]
        prev_b = match.frames[i_prev].ball
        cur_b = match.frames[i_cur].ball
        next_b = match.frames[i_next].ball
        if cur_b is None or prev_b is None or next_b is None:
            continue  # (elvileg nem fordul elő; a korábbi eldobás módosíthatja)
        # Megengedett elmozdulás az eltelt idő alatt (méter).
        lim_prev = max_speed_ms * (i_cur - i_prev) / fps
        lim_next = max_speed_ms * (i_next - i_cur) / fps
        if _dist(prev_b, cur_b) > lim_prev and _dist(cur_b, next_b) > lim_next:
            match.frames[i_cur].ball = None
            removed += 1
    return removed


def interpolate_ball_gaps(match: Match,
                          max_gap_frames: int = DEFAULT_MAX_GAP_FRAMES) -> int:
    """A rövid labda-hézagok lineáris pótlása. Visszaadja a pótolt kockák számát.

    Csak két VALÓDI észlelés közti, legfeljebb `max_gap_frames` hosszú hézagot
    töltünk ki; a pótolt pozíció confidence-e csökkentett (INTERPOLATED_CONFIDENCE),
    hogy megkülönböztethető legyen a mérttől.
    """
    frames = match.frames
    idxs = [i for i, f in enumerate(frames) if f.ball is not None]
    filled = 0
    for k in range(len(idxs) - 1):
        i0, i1 = idxs[k], idxs[k + 1]
        gap = i1 - i0 - 1
        if gap <= 0 or gap > max_gap_frames:
            continue
        b0 = frames[i0].ball
        b1 = frames[i1].ball
        for j in range(1, gap + 1):
            t = j / (gap + 1)
            frames[i0 + j].ball = Ball(
                x=b0.x + (b1.x - b0.x) * t,
                y=b0.y + (b1.y - b0.y) * t,
                confidence=INTERPOLATED_CONFIDENCE,
            )
            filled += 1
    return filled


def smooth_ball(match: Match, max_speed_ms: float = MAX_BALL_SPEED_MS,
                max_gap_frames: int = DEFAULT_MAX_GAP_FRAMES) -> dict:
    """A teljes labda-utómunka: kiugrók eldobása, majd hézagpótlás.

    A sorrend fontos: előbb a téves észleléseket dobjuk el, hogy a pótlás ne
    egy kiugró pont felé interpoláljon. Visszaadja: {"removed", "filled"}.
    """
    removed = remove_ball_outliers(match, max_speed_ms)
    filled = interpolate_ball_gaps(match, max_gap_frames)
    return {"removed": removed, "filled": filled}
