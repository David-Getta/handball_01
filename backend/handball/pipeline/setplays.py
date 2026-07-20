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


# ---- Figura-felismerés a mentett könyvtár (playbook) ellen -------------------

def interpolate_play(attackers: list, steps: int = 20) -> list:
    """Egy mentett figura kulcs-pozícióiból folyamatos mozgáspálya.

    A figura játékosonként kulcs-pozíciók listája ([[x,y], ...]); ezeket
    szakaszonként lineárisan interpoláljuk `steps` lépésre — így ugyanolyan
    "mozgás" lesz belőle, mint egy valódi támadásból.
    """
    paths = []
    for path in attackers:
        pts = []
        if len(path) == 1:
            pts = [(float(path[0][0]), float(path[0][1]))] * steps
        else:
            for s in range(steps):
                t = s / (steps - 1)
                seg = t * (len(path) - 1)
                i = min(int(seg), len(path) - 2)
                local = seg - i
                x = path[i][0] + (path[i + 1][0] - path[i][0]) * local
                y = path[i][1] + (path[i + 1][1] - path[i][1]) * local
                pts.append((float(x), float(y)))
        paths.append(pts)
    return paths


def play_signature(attackers: list, bins_x: int = 6, bins_y: int = 3,
                   steps: int = 20, mirror_x: bool = False) -> list[float]:
    """Egy mentett figura ujjlenyomata — ÖSSZEVETHETŐ az attack_signature-rel.

    Ugyanaz a rács-hisztogram készül az interpolált mozgáspályából, mint a valódi
    támadásokból. `mirror_x`-szel a pálya hossztengelyére tükrözve — a figurát
    a tervezőben a +x kapura rajzoljuk, de az ellenfél a -x kapura is támadhat.
    """
    grid = [0.0] * (bins_x * bins_y)
    total = 0.0
    for path in interpolate_play(attackers, steps):
        for (x, y) in path:
            if mirror_x:
                x = COURT_LENGTH_M - x
            ix = min(bins_x - 1, max(0, int(x / COURT_LENGTH_M * bins_x)))
            iy = min(bins_y - 1, max(0, int(y / COURT_WIDTH_M * bins_y)))
            grid[iy * bins_x + ix] += 1.0
            total += 1.0
    if total > 0:
        grid = [v / total for v in grid]
    return grid


def match_attacks_to_playbook(match: Match, plays: list[dict],
                              config: TacticsConfig | None = None,
                              team: Team | None = None,
                              threshold: float = 0.2,
                              min_length: int = 5) -> dict:
    """A meccs támadásait a MENTETT figurákhoz (playbook) rendeli.

    `plays` elemei: {"name": ..., "attackers": [[[x,y],...], ...]}. Minden
    felismert támadás-szakaszhoz megkeressük a legközelebbi figurát (normál ÉS
    tükrözött aláírással — a támadási irány ne számítson); ha a távolság a
    küszöb alatt van, a figurához soroljuk, különben "ismeretlen".

    Visszaad: {"total_attacks", "matched": {figura-név: darab}, "unmatched"}.
    Ez a "melyik ismert figurát játsszák és hányszor" — a felderítés kiegészítése.
    """
    config = config or TacticsConfig()
    seqs = segment_attacks(match, config, min_length=min_length)
    if team is not None:
        seqs = [s for s in seqs if s.team == team]

    play_sigs = []
    for p in plays:
        attackers = p.get("attackers") or []
        if not attackers:
            continue
        play_sigs.append((str(p.get("name", "névtelen")),
                          play_signature(attackers),
                          play_signature(attackers, mirror_x=True)))

    matched: dict[str, int] = {}
    unmatched = 0
    for s in seqs:
        sig = attack_signature(s)
        best_name = None
        best_d = float("inf")
        for name, ps, psm in play_sigs:
            d = min(_distance(sig, ps), _distance(sig, psm))
            if d < best_d:
                best_d = d
                best_name = name
        if best_name is not None and best_d <= threshold:
            matched[best_name] = matched.get(best_name, 0) + 1
        else:
            unmatched += 1
    return {"total_attacks": len(seqs),
            "matched": dict(sorted(matched.items(), key=lambda kv: -kv[1])),
            "unmatched": unmatched}


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


def setplay_efficiency(match: Match, config: TacticsConfig | None = None,
                       threshold: float = 0.15, min_length: int = 5,
                       min_attacks: int = 2) -> dict:
    """Melyik figura működik: klaszterenként támadás / lövés / gól.

    A figurákat csapatonként külön klaszterezzük (a két csapat mintái
    ne keveredjenek), és minden támadás-szakaszhoz hozzárendeljük a
    benne (vagy közvetlenül utána, 3 mp-en belül) esett lövéseket.
    A felderítésben ebből lesz a "melyik figurájuk veszélyes" kép.

    Visszatérés csapatonként: [{"figure", "attacks", "shots", "goals",
    "goal_pct"}] — csak a min_attacks-szor látott figurák, gyakoriság
    szerint csökkenő sorrendben.
    """
    from .event_detection import EventType, detect_shots

    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0
    tail = round(3.0 * fps)
    shots_ev = [e for e in detect_shots(match, config)
                if e.type in (EventType.SHOT, EventType.GOAL)]
    out: dict = {}
    for team in (Team.HOME, Team.AWAY):
        seqs = [s_ for s_ in segment_attacks(match, config,
                                             min_length=min_length)
                if s_.team == team]
        labels = cluster_signatures([attack_signature(s_) for s_ in seqs],
                                    threshold=threshold)
        agg: dict = {}
        for seq, lab in zip(seqs, labels):
            rec = agg.setdefault(lab, {"attacks": 0, "shots": 0,
                                       "goals": 0})
            rec["attacks"] += 1
            for e in shots_ev:
                if e.team == team and \
                        seq.start_t <= e.t <= seq.end_t + tail:
                    rec["shots"] += 1
                    if e.type == EventType.GOAL:
                        rec["goals"] += 1
        rows = [{"figure": int(lab), **rec,
                 "goal_pct": round(100.0 * rec["goals"] / rec["attacks"],
                                   1)}
                for lab, rec in agg.items()
                if rec["attacks"] >= min_attacks]
        rows.sort(key=lambda r: (-r["attacks"], -r["goals"]))
        out[team.value] = rows
    return out
