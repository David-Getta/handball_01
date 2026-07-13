"""Támadás-típus címkézés — lerohanás / gyors indítás / felállt / 7 a 6.

A meccs támadás-szakaszait (setplays.segment_attacks) sorolja be négy,
edzői nyelven értelmes típusba. A szabályok szándékosan egyszerűek és
magyarázhatók (minden címke mögött mért szám áll):

- 7 A 6:          a szakasz ideje nagyrészt egybeesik egy lehozott kapusos
                  (detect_empty_net) ablakkal.
- LEROHANÁS:      rövid támadás (<= 6 mp), amely alatt a labda gyorsan
                  halad az ellenfél kapuja felé (>= 2 m/s nettó előrehaladás).
- GYORS INDÍTÁS:  legfeljebb 12 mp, érdemi előrehaladással (>= 1 m/s) —
                  gyors középkezdés / korai befejezés, de nem teljes sprint.
- FELÁLLT TÁMADÁS: minden más (türelmes játék a felállt védelem ellen).

Ebből áll össze a csapat TÁMADÁS-MIXE — a felderítés egyik legbeszédesebb
száma ("támadásaik 30%-a lerohanás → zárj vissza azonnal").
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from ..models.tracking import Match
from .setplays import segment_attacks
from .tactics import TacticsConfig

# Küszöbök (magyarázható, mért szabályok):
FAST_BREAK_MAX_S = 6.0     # lerohanás: legfeljebb ennyi ideig tart
FAST_BREAK_ADV_MS = 2.0    # ... és a labda legalább ennyivel halad előre
QUICK_MAX_S = 12.0         # gyors indítás: legfeljebb ennyi
QUICK_ADV_MS = 1.0         # ... legalább ennyi előrehaladással
SEVEN_SIX_OVERLAP = 0.5    # 7a6: a szakasz ekkora része esik üres-kapus ablakba


class AttackType(str, Enum):
    FAST_BREAK = "lerohanás"
    QUICK = "gyors indítás"
    POSITIONAL = "felállt támadás"
    SEVEN_SIX = "7 a 6"


def _advance_speed(seq, target_x: float, fps: float) -> float:
    """A labda nettó előrehaladási sebessége a kapu felé (m/s) a szakaszban."""
    first = next((f.ball for f in seq.frames if f.ball is not None), None)
    last = next((f.ball for f in reversed(seq.frames) if f.ball is not None),
                None)
    if first is None or last is None or seq.length < 2:
        return 0.0
    sign = 1.0 if target_x >= 20.0 else -1.0  # a +x vagy a -x kapura támad
    duration_s = seq.length / fps
    return (last.x - first.x) * sign / duration_s if duration_s > 0 else 0.0


def classify_attacks(match: Match,
                     config: Optional[TacticsConfig] = None) -> list[dict]:
    """A meccs támadás-szakaszai típus-címkével, időrendben.

    Visszatérés: [{"team", "start_frame", "end_frame", "duration_s",
    "type"}, ...] — a "type" az AttackType értéke (magyarul).
    """
    config = config or TacticsConfig()
    fps = match.meta.fps if match.meta.fps > 0 else 25.0

    # 7a6 ablakok (kapus-jelölés nélkül üres lista — a többi címke él).
    try:
        from .goalkeeper import detect_empty_net
        empty = detect_empty_net(match, config)
    except Exception:
        empty = []

    out: list[dict] = []
    for seq in segment_attacks(match, config):
        duration_s = seq.length / fps
        target_x = config.attacks_toward_x(seq.team)

        overlap = 0
        for w in empty:
            if w["team"] != seq.team.value:
                continue
            o = min(seq.end_t, w["end_frame"]) - max(seq.start_t,
                                                     w["start_frame"]) + 1
            if o > 0:
                overlap += o
        if overlap / max(1, seq.length) >= SEVEN_SIX_OVERLAP:
            label = AttackType.SEVEN_SIX
        else:
            adv = _advance_speed(seq, target_x, fps)
            if duration_s <= FAST_BREAK_MAX_S and adv >= FAST_BREAK_ADV_MS:
                label = AttackType.FAST_BREAK
            elif duration_s <= QUICK_MAX_S and adv >= QUICK_ADV_MS:
                label = AttackType.QUICK
            else:
                label = AttackType.POSITIONAL

        out.append({
            "team": seq.team.value,
            "start_frame": seq.start_t,
            "end_frame": seq.end_t,
            "duration_s": round(duration_s, 1),
            "type": label.value,
        })
    return out


def attack_mix(match: Match,
               config: Optional[TacticsConfig] = None) -> dict:
    """Csapatonkénti támadás-mix: {csapat: {típus: százalék}}.

    Csak azok a csapatok szerepelnek, amelyeknek volt támadás-szakasza;
    a százalékok a csapat összes támadásához mértek.
    """
    counts: dict[str, dict[str, int]] = {}
    for a in classify_attacks(match, config):
        counts.setdefault(a["team"], {})
        counts[a["team"]][a["type"]] = counts[a["team"]].get(a["type"], 0) + 1
    out: dict = {}
    for team, by_type in counts.items():
        total = sum(by_type.values())
        out[team] = {t: round(100.0 * n / total, 1)
                     for t, n in sorted(by_type.items(), key=lambda kv: -kv[1])}
    return out
