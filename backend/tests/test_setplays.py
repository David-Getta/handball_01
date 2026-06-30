"""
Tesztek a figura-felismerésre (setplays.py).

Szintetikus támadásokkal, videó nélkül. A kulcs: két AZONOS mintázatú támadás egy
klaszterbe kerül, egy eltérő pedig külön → a rendszer megkülönbözteti a figurákat.

Futtatás:
    python tests/test_setplays.py
"""

from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, Ball, Team, PositionSource,
)
from handball.pipeline.setplays import (
    segment_attacks, attack_signature, cluster_signatures, discover_setplays,
    AttackSequence,
)


def _pl(track_id, team, x, y):
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0)


def _home_attack_frame(t, xs, ys=None):
    """Hazai-támadás frame: a hazai játékosok az `xs`/`ys` pozíciókon, labda náluk.

    Az x-eknek a támadó térfélen (x>20) kell lenniük, hogy HAZAI_TÁMADÁS legyen.
    """
    ys = ys or [10.0] * len(xs)
    players = [_pl(i + 1, Team.HOME, xs[i], ys[i]) for i in range(len(xs))]
    return Frame(t=t, players=players, ball=Ball(x=xs[0], y=ys[0], confidence=1.0))


def _attack(team, xs_per_frame, start=0):
    """AttackSequence építése: minden elem egy frame x-pozíciói."""
    frames = [_home_attack_frame(start + i, xs) for i, xs in enumerate(xs_per_frame)]
    return AttackSequence(team=team, start_t=start, end_t=start + len(frames) - 1, frames=frames)


def test_segment_attacks_groups_consecutive():
    """Az egymást követő hazai-támadás frame-ek egy szakaszba kerülnek."""
    frames = [_home_attack_frame(i, [30.0, 28.0, 32.0]) for i in range(8)]
    seqs = segment_attacks(Match(MatchMeta(match_id="t", home_team="A", away_team="B", fps=25), frames), min_length=5)
    assert len(seqs) == 1
    assert seqs[0].team == Team.HOME
    assert seqs[0].length == 8


def test_signature_normalized():
    """Az ujjlenyomat 1-re normált (a támadás hossza nem számít)."""
    seq = _attack(Team.HOME, [[30.0, 28.0, 32.0]] * 4)
    sig = attack_signature(seq)
    assert abs(sum(sig) - 1.0) < 1e-9


def test_identical_attacks_cluster_together():
    """Két azonos mintázatú támadás egy klaszter; egy eltérő külön → 2 figura."""
    # A: a támadók a jobb oldalon tömörülnek (x~30-34).
    a1 = _attack(Team.HOME, [[30.0, 32.0, 34.0]] * 6)
    a2 = _attack(Team.HOME, [[30.0, 32.0, 34.0]] * 6)  # ugyanaz a mintázat
    # B: a támadók a bal oldalon (x~6-10) — más eloszlás (itt nem megy
    # szegmentáláson át, csak az ujjlenyomat különbözőségét teszteljük).
    b1 = _attack(Team.HOME, [[6.0, 8.0, 10.0]] * 6)

    sigs = [attack_signature(s) for s in (a1, a2, b1)]
    labels = cluster_signatures(sigs, threshold=0.15)
    assert labels[0] == labels[1]      # a két azonos egy klaszter
    assert labels[2] != labels[0]      # az eltérő külön
    assert len(set(labels)) == 2       # összesen 2 figura


def test_discover_setplays_end_to_end():
    """Teljes lánc egy meccsen: két azonos + egy eltérő támadás → 2 figura.

    A támadásokat ÁTMENET (labda a saját térfélen) választja el, hogy külön
    szakaszok legyenek.
    """
    meta = MatchMeta(match_id="t", home_team="A", away_team="B", fps=25.0)
    frames: list[Frame] = []
    t = 0

    def add_attack(xs, ys):
        nonlocal t
        for _ in range(6):
            frames.append(_home_attack_frame(t, xs, ys))
            t += 1

    def add_gap():
        nonlocal t
        # Hazai a SAJÁT térfelén (x<20) → ÁTMENET, megszakítja a támadást.
        for _ in range(3):
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 8.0, 10.0)],
                                ball=Ball(x=8.0, y=10.0, confidence=1.0)))
            t += 1

    # Mind a támadó térfélen (x>20). A két azonos: BAL oldali tömörülés (y~4);
    # az eltérő: JOBB oldali tömörülés (y~16). Ugyanaz a mélység, más oldal.
    add_attack([28.0, 31.0, 34.0], [4.0, 4.0, 4.0]); add_gap()
    add_attack([28.0, 31.0, 34.0], [4.0, 4.0, 4.0]); add_gap()
    add_attack([28.0, 31.0, 34.0], [16.0, 16.0, 16.0])

    report = discover_setplays(Match(meta, frames), threshold=0.15, min_length=5)
    assert report.attacks == 3
    assert report.num_figures == 2
    # a leggyakoribb figura 2 támadásból áll
    assert max(report.figure_sizes.values()) == 2


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    print(f"\n{'OK' if failures == 0 else failures} hibás teszt")
    raise SystemExit(1 if failures else 0)
