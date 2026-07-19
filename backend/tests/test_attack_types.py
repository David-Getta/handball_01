"""
Tesztek a támadás-típus címkézésre (attack_types.py).

A pálya 40x20 m; a HAZAI a +x (x=40) kapu felé támad.

Futtatás:
    python -m pytest tests/test_attack_types.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.attack_types import (
    AttackType, attack_mix, classify_attacks,
)


def _meta(fps=25.0):
    return MatchMeta(match_id="a", home_team="H", away_team="A", fps=fps)


def _pl(track_id, team, x, y, role=None):
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0,
                          role=role)


def _attack_frames(t0, seconds, x_from, x_to, fps=25.0, gk_x=1.5):
    """HAZAI támadás-szakasz: a labda (és a labdás játékos) x_from→x_to
    halad; a védő vendégek a saját kapujuknál állnak."""
    n = int(seconds * fps)
    frames = []
    for i in range(n):
        x = x_from + (x_to - x_from) * i / max(1, n - 1)
        players = [
            _pl(1, Team.HOME, x, 10.0),
            _pl(2, Team.HOME, x - 3.0, 6.0),
            _pl(9, Team.HOME, gk_x, 10.0, role="kapus"),
            _pl(21, Team.AWAY, 37.0, 8.0),
            _pl(22, Team.AWAY, 37.0, 12.0),
        ]
        frames.append(Frame(t=t0 + i, players=players,
                            ball=Ball(x=x, y=10.0, confidence=1.0)))
    return frames


def test_fast_break_label():
    """4 mp alatt 22→38 m (4 m/s előrehaladás) → lerohanás."""
    m = Match(_meta(), _attack_frames(0, 4.0, 22.0, 38.0))
    attacks = [a for a in classify_attacks(m) if a["team"] == "home"]
    assert attacks and attacks[0]["type"] == AttackType.FAST_BREAK.value


def test_positional_label():
    """20 mp-en át topogás a 9 m körül (nincs előrehaladás) → felállt támadás."""
    m = Match(_meta(), _attack_frames(0, 20.0, 30.0, 31.0))
    attacks = [a for a in classify_attacks(m) if a["team"] == "home"]
    assert attacks and attacks[0]["type"] == AttackType.POSITIONAL.value


def test_quick_label():
    """10 mp alatt 22→38 m (~1,6 m/s) → gyors indítás (nem teljes sprint)."""
    m = Match(_meta(), _attack_frames(0, 10.0, 22.0, 38.0))
    attacks = [a for a in classify_attacks(m) if a["team"] == "home"]
    assert attacks and attacks[0]["type"] == AttackType.QUICK.value


def test_seven_six_label_overrides():
    """Ha a szakasz lehozott kapusos ablakban fut (a kapus elöl játszik),
    a címke 7 a 6 — akkor is, ha egyébként felállt támadás lenne."""
    m = Match(_meta(), _attack_frames(0, 20.0, 30.0, 31.0, gk_x=22.0))
    attacks = [a for a in classify_attacks(m) if a["team"] == "home"]
    assert attacks and attacks[0]["type"] == AttackType.SEVEN_SIX.value


def test_attack_mix_percentages():
    """A mix a címkék darabszám-aránya, 100%-ra összegződve."""
    frames = _attack_frames(0, 4.0, 22.0, 38.0)  # lerohanás
    # Szünet (nincs támadó fázis): a labda középen, senki a közelében.
    t0 = len(frames)
    for i in range(10):
        frames.append(Frame(t=t0 + i, players=[], ball=None))
    frames += _attack_frames(t0 + 10, 20.0, 30.0, 31.0)  # felállt
    m = Match(_meta(), frames)
    mix = attack_mix(m).get("home", {})
    assert set(mix) == {AttackType.FAST_BREAK.value,
                        AttackType.POSITIONAL.value}
    assert abs(sum(mix.values()) - 100.0) < 0.2


def _fast_break_goal(t0):
    """Lerohanás (22→33) majd lövés-gól a +x kapura."""
    frames = _attack_frames(t0, 4.0, 22.0, 33.0)
    t = t0 + len(frames)
    for i in range(7):
        frames.append(Frame(t=t + i, players=[_pl(1, Team.HOME, 33.0, 10.0)],
                            ball=Ball(x=34.0 + i, y=10.0, confidence=1.0)))
    return frames


def test_attack_efficiency_pairs_shots_and_goals():
    """A lerohanás lövésig és gólig jut → 100% shot_pct/goal_pct rá."""
    from handball.pipeline.attack_types import attack_efficiency

    frames = _fast_break_goal(0)
    # Szünet (a debounce miatt), majd egy felállt támadás lövés nélkül.
    t0 = len(frames)
    for i in range(30):
        frames.append(Frame(t=t0 + i, players=[], ball=None))
    frames += _attack_frames(t0 + 30, 20.0, 30.0, 31.0)
    m = Match(_meta(), frames)

    eff = attack_efficiency(m)["home"]
    fb = eff.get(AttackType.FAST_BREAK.value)
    assert fb and fb["attacks"] >= 1
    assert fb["shots"] == fb["attacks"] and fb["goals"] == fb["attacks"]
    assert fb["goal_pct"] == 100.0
    # A felállt támadás lövés nélkül maradt.
    pos = eff.get(AttackType.POSITIONAL.value)
    if pos:
        assert pos["shots"] == 0 and pos["goal_pct"] == 0.0


def test_attack_efficiency_no_attacks_empty():
    from handball.pipeline.attack_types import attack_efficiency
    m = Match(_meta(), [Frame(t=i, players=[], ball=None) for i in range(10)])
    eff = attack_efficiency(m)
    assert eff == {"home": {}, "away": {}}


def test_attack_duration_efficiency_buckets():
    """A gyors (pár mp-es) gólos támadás a 'rövid' vödörbe kerül 100%
    gólaránnyal; üres meccsen üres a kimenet."""
    from handball.pipeline.attack_types import attack_duration_efficiency

    m = Match(_meta(), _fast_break_goal(0))
    eff = attack_duration_efficiency(m)["home"]
    assert "rövid (<15 mp)" in eff
    rec = eff["rövid (<15 mp)"]
    assert rec["attacks"] >= 1 and rec["goals"] >= 1
    assert rec["goal_pct"] == 100.0

    empty = Match(_meta(), [Frame(t=i, players=[], ball=None)
                            for i in range(10)])
    assert attack_duration_efficiency(empty) == {"home": {}, "away": {}}


def test_match_pace_counts_and_label():
    """A tempó a szegmentált támadásokból és a felvétel hosszából jön;
    rövid felvételen nem értelmezzük."""
    from handball.pipeline.attack_types import match_pace

    # Rövid felvétel: nincs tempó-értékelés.
    short = Match(_meta(), [Frame(t=i, players=[], ball=None)
                            for i in range(100)])
    assert match_pace(short)["available"] is False

    # 12 perces üres felvétel: 0 támadás → lassú címke, 0/perc.
    n = int(12 * 60 * 25)
    long_empty = Match(_meta(), [Frame(t=i, players=[], ball=None)
                                 for i in range(n)])
    pc = match_pace(long_empty)
    assert pc["available"] is True
    assert pc["home_attacks"] == 0 and pc["away_attacks"] == 0
    assert pc["per_min"] == 0.0
    assert pc["label"] == "lassú"


def test_match_pace_halves_split():
    """Megadott félidő-határnál a tempó félidőnként is kijön; határ
    nélkül (és rövid féllel) a halves None."""
    from handball.pipeline.attack_types import match_pace

    n = int(12 * 60 * 25)
    m = Match(_meta(), [Frame(t=i, players=[], ball=None)
                        for i in range(n)])
    # Kézzel megadott félidő-határ: mindkét fél 6 perc.
    pc = match_pace(m, half_t=n // 2)
    assert pc["halves"] == {"first_per_min": 0.0, "second_per_min": 0.0}
    # Túl rövid második fél: nincs bontás.
    pc2 = match_pace(m, half_t=n - 100)
    assert pc2["halves"] is None
