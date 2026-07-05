"""
[3. fázis] Figura-felismerés — visszatérő támadás-mintázatok (set play-ek).

A vízió "milyen figurákat csinálnak" része. Az ötlet:
1. A meccset szervezett TÁMADÁSOKRA bontjuk (a tactics.py fázisaiból).
2. Minden támadásból egy MOZGÁS-UJJLENYOMATOT (signature) készítünk: a támadó
   csapat játékosainak térbeli eloszlása a támadás alatt, durva rácson, normálva.
   (A normálás miatt a támadás HOSSZA nem számít, csak a mintázat alakja.)
3. A hasonló ujjlenyomatú támadásokat KLASZTEREZZÜK — minden klaszter egy
   visszatérő figura. Így megtudjuk, egy csapat milyen figurákat, milyen
   gyakorisággal játszik.

Tiszta Python (nincs ML-csomag), így videó nélkül, szintetikus pályákon tesztelhető.
A valódi figurák finomabb modellt (trajektória-szekvenciák) is kaphatnak később,
de a felismerés alap-elve és csővezetéke ez.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..models.tracking import Match, Frame, Team
from .calibration import COURT_LENGTH_M, COURT_WIDTH_M
from .tactics import TacticsConfig, classify_phase, Phase


@dataclass
class AttackSequence:
    """Egy szervezett támadás-szakasz (a klaszterezés egysége).

    - team:     a támadó csapat.
    - start_t:  a szakasz első frame-ének ideje.
    - end_t:    az utolsó frame ideje.
    - frames:   a szakasz frame-jei.
    """
    team: Team
    start_t: int
    end_t: int
    frames: list[Frame] = field(default_factory=list)

    @property
    def length(self) -> int:
        return len(self.frames)


def segment_attacks(match: Match, config: TacticsConfig | None = None,
                    min_length: int = 5) -> list[AttackSequence]:
    """A meccset szervezett támadás-szakaszokra bontja.

    Az egymást követő, AZONOS támadó-fázisú (HAZAI/VENDÉG_TÁMADÁS) frame-ek egy
    szakaszt alkotnak. A `min_length`-nél rövidebb szakaszokat eldobjuk (zaj).
    """
    config = config or TacticsConfig()
    sequences: list[AttackSequence] = []
    current: AttackSequence | None = None

    def close():
        nonlocal current
        if current is not None and current.length >= min_length:
            sequences.append(current)
        current = None

    for f in match.frames:
        ph = classify_phase(f, config)
        team = (Team.HOME if ph == Phase.HOME_ATTACK
                else Team.AWAY if ph == Phase.AWAY_ATTACK else None)
        if team is None:
            close()
            continue
        if current is None or current.team != team:
            close()
            current = AttackSequence(team=team, start_t=f.t, end_t=f.t, frames=[f])
        else:
            current.frames.append(f)
            current.end_t = f.t
    close()
    return sequences


def attack_signature(seq: AttackSequence, bins_x: int = 6, bins_y: int = 3) -> list[float]:
    """Egy támadás MOZGÁS-UJJLENYOMATA: a támadó csapat térbeli eloszlása.

    A támadó csapat játékosainak látogatottságát durva rácson (alap 6x3) gyűjtjük,
    majd a vektort 1-re NORMÁLJUK (a támadás hossza ne számítson, csak az alakja).
    Visszaad egy bins_x*bins_y hosszú vektort (sorfolytonos).
    """
    grid = [0.0] * (bins_x * bins_y)
    total = 0.0
    for f in seq.frames:
        for p in f.players:
            if p.team != seq.team:
                continue
            ix = min(bins_x - 1, max(0, int(p.x / COURT_LENGTH_M * bins_x)))
            iy = min(bins_y - 1, max(0, int(p.y / COURT_WIDTH_M * bins_y)))
            grid[iy * bins_x + ix] += 1.0
            total += 1.0
    if total > 0:
        grid = [v / total for v in grid]
    return grid


def _distance(a: list[float], b: list[float]) -> float:
    """Két ujjlenyomat euklideszi távolsága."""
    return math.sqrt(sum((ai - bi) ** 2 for ai, bi in zip(a, b)))


def cluster_signatures(signatures: list[list[float]], threshold: float = 0.15) -> list[int]:
    """Mohó (greedy) klaszterezés: a hasonló ujjlenyomatok egy klaszterbe.

    Minden ujjlenyomatot a hozzá LEGKÖZELEBBI meglévő klaszter-középponthoz teszünk,
    ha a távolság a küszöb alatt van; különben új klasztert nyit. A középpontot
    (futó átlag) frissítjük. Visszaad egy klaszter-címkét (0,1,2,…) elemenként.

    A küszöb hangolható: kisebb = szigorúbb (több, finomabb figura), nagyobb =
    megengedőbb (kevesebb, durvább csoport).
    """
    centroids: list[list[float]] = []
    counts: list[int] = []
    labels: list[int] = []

    for sig in signatures:
        best_idx = -1
        best_dist = float("inf")
        for i, c in enumerate(centroids):
            d = _distance(sig, c)
            if d < best_dist:
                best_dist = d
                best_idx = i
        if best_idx >= 0 and best_dist <= threshold:
            # Hozzávesszük a klaszterhez, és frissítjük a középpontot (futó átlag).
            n = counts[best_idx]
            centroids[best_idx] = [(c * n + s) / (n + 1) for c, s in zip(centroids[best_idx], sig)]
            counts[best_idx] = n + 1
            labels.append(best_idx)
        else:
            centroids.append(list(sig))
            counts.append(1)
            labels.append(len(centroids) - 1)
    return labels


@dataclass
class SetPlayReport:
    """A figura-felismerés összegzése.

    - attacks:        a felismert támadás-szakaszok száma.
    - num_figures:    a megkülönböztetett visszatérő figurák (klaszterek) száma.
    - figure_sizes:   klaszterenként hány támadás tartozik bele (gyakoriság).
    - labels:         minden támadás-szakasz klaszter-címkéje (a sorrendjükben).
    """
    attacks: int
    num_figures: int
    figure_sizes: dict[int, int]
    labels: list[int]


def discover_setplays(match: Match, config: TacticsConfig | None = None,
                      threshold: float = 0.15, min_length: int = 5) -> SetPlayReport:
    """Végpontok közötti figura-felismerés: támadások → ujjlenyomat → klaszterek.

    Megmondja, hány visszatérő figurát játszott a csapat és milyen gyakorisággal.
    """
    config = config or TacticsConfig()
    sequences = segment_attacks(match, config, min_length=min_length)
    signatures = [attack_signature(s) for s in sequences]
    labels = cluster_signatures(signatures, threshold=threshold)

    sizes: dict[int, int] = {}
    for lab in labels:
        sizes[lab] = sizes.get(lab, 0) + 1
    return SetPlayReport(
        attacks=len(sequences),
        num_figures=len(sizes),
        figure_sizes=sizes,
        labels=labels,
    )
