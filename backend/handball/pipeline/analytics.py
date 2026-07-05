"""
[H+] Elemzés — hőtérkép és csapat-statisztikák a kész Tracking-ből.

Ez TISZTA adatfeldolgozás (nincs ML), a kész Match-re épül, ezért valódi (nem
placeholder) és videó nélkül tesztelhető. Az edzőnek hasznos kimenetek:

- Hőtérkép (heatmap): hol tartózkodott egy játékos / csapat a pályán (rács-cellák
  látogatottsága). A felülnézeti nézeten kirajzolható.
- Csapat-összegzés: a csapat átlagos súlypontja (centroid) és kiterjedése (spread)
  — pl. mennyire húzódik szét szélességben/mélységben (kompakt vagy nyújtott).

Fontos: alapból csak a MÉRT pozíciókat számoljuk (a becsült bizonytalan, nem
akarjuk vele torzítani a statisztikát) — de opcionálisan bevehető (include_estimated).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from ..models.tracking import Match, Team, PositionSource
from .calibration import COURT_LENGTH_M, COURT_WIDTH_M


@dataclass
class Heatmap:
    """Egy hőtérkép: a pályát rácsra osztva, cellánként a látogatottság.

    - bins_x, bins_y: a rács felbontása (x és y mentén).
    - grid:           [bins_y][bins_x] mátrix; grid[iy][ix] = hányszor volt ott.
    - total:          az összes beleszámolt pozíció (a grid összege).
    A cellaméret: (COURT_LENGTH_M / bins_x) x (COURT_WIDTH_M / bins_y) méter.
    """
    bins_x: int
    bins_y: int
    grid: list[list[float]]
    total: float


def _cell_index(x: float, y: float, bins_x: int, bins_y: int) -> tuple[int, int]:
    """Egy pálya-pont (méter) rács-cellájának indexe (a pályán belülre vágva)."""
    ix = int(x / COURT_LENGTH_M * bins_x)
    iy = int(y / COURT_WIDTH_M * bins_y)
    ix = max(0, min(bins_x - 1, ix))
    iy = max(0, min(bins_y - 1, iy))
    return ix, iy


def _empty_grid(bins_x: int, bins_y: int) -> list[list[float]]:
    return [[0.0 for _ in range(bins_x)] for _ in range(bins_y)]


def compute_player_heatmap(match: Match, track_id: int,
                           bins_x: int = 20, bins_y: int = 10,
                           include_estimated: bool = False) -> Heatmap:
    """Egy játékos hőtérképe: minden frame-en a cellájába teszünk egy pontot."""
    grid = _empty_grid(bins_x, bins_y)
    total = 0.0
    for frame in match.frames:
        for p in frame.players:
            if p.track_id != track_id:
                continue
            if not include_estimated and p.source == PositionSource.ESTIMATED:
                continue
            ix, iy = _cell_index(p.x, p.y, bins_x, bins_y)
            grid[iy][ix] += 1.0
            total += 1.0
    return Heatmap(bins_x, bins_y, grid, total)


def compute_team_heatmap(match: Match, team: Team,
                         bins_x: int = 20, bins_y: int = 10,
                         include_estimated: bool = False) -> Heatmap:
    """Egy teljes csapat hőtérképe (minden játékosát összegezve)."""
    grid = _empty_grid(bins_x, bins_y)
    total = 0.0
    for frame in match.frames:
        for p in frame.players:
            if p.team != team:
                continue
            if not include_estimated and p.source == PositionSource.ESTIMATED:
                continue
            ix, iy = _cell_index(p.x, p.y, bins_x, bins_y)
            grid[iy][ix] += 1.0
            total += 1.0
    return Heatmap(bins_x, bins_y, grid, total)


@dataclass
class TeamSummary:
    """Egy csapat összegzése a meccsen (átlagolva a frame-eken).

    - avg_centroid_x/y: a csapat átlagos súlypontja (méter).
    - avg_spread_x/y:   átlagos kiterjedés (szórás) x (mélység) és y (szélesség)
                        mentén — mennyire húzódik szét a csapat.
    - frames_counted:   hány frame-et vettünk figyelembe (volt legalább 2 mért játékos).
    """
    team: str
    avg_centroid_x: float
    avg_centroid_y: float
    avg_spread_x: float
    avg_spread_y: float
    frames_counted: int


def compute_team_summary(match: Match, team: Team,
                         include_estimated: bool = False) -> TeamSummary:
    """A csapat súlypont- és kiterjedés-átlaga a meccsen.

    Frame-enként kiszámoljuk a csapat mért játékosainak súlypontját és szórását,
    majd ezeket átlagoljuk. A szóráshoz legalább 2 játékos kell egy frame-en.
    """
    cx, cy, sx, sy = [], [], [], []
    for frame in match.frames:
        xs, ys = [], []
        for p in frame.players:
            if p.team != team:
                continue
            if not include_estimated and p.source == PositionSource.ESTIMATED:
                continue
            xs.append(p.x)
            ys.append(p.y)
        if len(xs) >= 2:
            cx.append(statistics.fmean(xs))
            cy.append(statistics.fmean(ys))
            sx.append(statistics.pstdev(xs))
            sy.append(statistics.pstdev(ys))

    if not cx:
        return TeamSummary(team.value, 0.0, 0.0, 0.0, 0.0, 0)
    return TeamSummary(
        team=team.value,
        avg_centroid_x=statistics.fmean(cx),
        avg_centroid_y=statistics.fmean(cy),
        avg_spread_x=statistics.fmean(sx),
        avg_spread_y=statistics.fmean(sy),
        frames_counted=len(cx),
    )
