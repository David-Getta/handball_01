"""A kivágott klip visszakeresése a teljes jelenetben.

Az UNIRI-HBD `actions/` klipjei a jelenet képpontjainak szó szerinti
kivágásai (állandó méretű ablak, ami a játékost követi). Ezért a klip
k-adik kockája a jelenet (eltolás + k)-adik kockájában sablon-egyezéssel
pontosan megtalálható. Így tudjuk meg, MELYIK játékos a végrehajtó és HOL
áll — a `player_detections` ezt nem mondja meg.

Két lépés:
  1. eltolás: a klip első kockáját a jelenet kockáin keressük, az első
     (gyakorlatilag) pontos egyezésnél megállunk;
  2. követés: a további kockákon csak az előző hely környezetében
     keresünk (gyors), rossz egyezésnél az egész képen.
"""

from __future__ import annotations

from typing import Iterable, Iterator

import cv2
import numpy as np

# A klip a jelenet képpontjainak másolata → a helyes kockán az egyezés 1,000.
# Ennél jobb egyezésnél az eltolás-keresés megállhat. SZIGORÚ kell: álló
# kameránál a SZOMSZÉD kocka is ~0,98-at ad, és 0,98-as küszöbnél a keresés
# egy kockával korán megállt (az egész klip elcsúszott, 0,85-ös egyezésekkel).
EXACT_MATCH = 0.999
# Követéskor ennél gyengébb ablakos egyezésnél az egész képen keresünk.
TRACK_MIN_SCORE = 0.90
# A keresőablak a sablon körül: a sablon-méret ennyiszerese, de min. ennyi px.
SEARCH_PAD_FRAC = 0.6
SEARCH_PAD_MIN = 32


def _gray(frame: np.ndarray) -> np.ndarray:
    return frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)


def match_full(frame: np.ndarray, tmpl: np.ndarray) -> tuple[float, tuple[int, int]]:
    """Legjobb egyezés az egész képen: (pontszám, (x, y) bal-felső sarok)."""
    r = cv2.matchTemplate(_gray(frame), tmpl, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(r)
    return float(score), (int(loc[0]), int(loc[1]))


def match_window(
    frame: np.ndarray, tmpl: np.ndarray, prev_xy: tuple[int, int]
) -> tuple[float, tuple[int, int]]:
    """Egyezés az előző hely környezetében; ha az ablak nem fér, az egész képen."""
    g = _gray(frame)
    th, tw = tmpl.shape
    pad = max(SEARCH_PAD_MIN, int(SEARCH_PAD_FRAC * max(th, tw)))
    x0 = max(0, prev_xy[0] - pad)
    y0 = max(0, prev_xy[1] - pad)
    x1 = min(g.shape[1], prev_xy[0] + tw + pad)
    y1 = min(g.shape[0], prev_xy[1] + th + pad)
    if x1 - x0 < tw or y1 - y0 < th:
        return match_full(g, tmpl)
    r = cv2.matchTemplate(g[y0:y1, x0:x1], tmpl, cv2.TM_CCOEFF_NORMED)
    _, score, _, loc = cv2.minMaxLoc(r)
    return float(score), (int(loc[0]) + x0, int(loc[1]) + y0)


def find_offset(frames: Iterable[np.ndarray], first_tmpl: np.ndarray) -> tuple[int, float]:
    """A jelenet melyik kockájánál kezdődik a klip: (eltolás, pontszám).

    Az első pontos egyezésnél megáll; ha nincs pontos, a legjobbat adja.
    """
    best = (-1, -1.0)
    for i, fr in enumerate(frames):
        score, _ = match_full(fr, first_tmpl)
        if score > best[1]:
            best = (i, score)
        if score >= EXACT_MATCH:
            break
    return best


def track(
    frames: Iterable[np.ndarray], action_gray: np.ndarray, offset: int
) -> Iterator[tuple[int, np.ndarray, tuple[int, int, int, int], float]]:
    """Végigköveti a klipet a jeleneten.

    Bemenet: a jelenet kockái (szürke vagy BGR, sorban), a klip szürke kockái
    (T, h, w) és az eltolás. Kimenet kockánként: (k, a jelenet kockája,
    doboz (x1, y1, x2, y2), pontszám). A jelenet végén megáll.
    """
    th, tw = action_gray.shape[1:]
    prev: tuple[int, int] | None = None
    for i, fr in enumerate(frames):
        k = i - offset
        if k < 0:
            continue
        if k >= len(action_gray):
            break
        tmpl = action_gray[k]
        if prev is None:
            score, xy = match_full(fr, tmpl)
        else:
            score, xy = match_window(fr, tmpl, prev)
            if score < TRACK_MIN_SCORE:
                s2, xy2 = match_full(fr, tmpl)
                if s2 > score:
                    score, xy = s2, xy2
        prev = xy
        yield k, fr, (xy[0], xy[1], xy[0] + tw, xy[1] + th), score
