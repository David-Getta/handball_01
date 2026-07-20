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
    AttackSequence, interpolate_play, play_signature, match_attacks_to_playbook,
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


def _meta():
    return MatchMeta(match_id="pb", home_team="A", away_team="B", fps=25.0,
                     frame_width=1920, frame_height=1080)


def _play_frames(attackers, team=Team.HOME, steps=12, start=0):
    """Egy figura interpolált mozgásából valódi támadás-frame-ek (labda az 1.-nél)."""
    paths = interpolate_play(attackers, steps=steps)
    frames = []
    for s_i in range(steps):
        players = [PlayerPosition(track_id=i + 1, team=team,
                                  x=paths[i][s_i][0], y=paths[i][s_i][1],
                                  source=PositionSource.MEASURED, confidence=1.0)
                   for i in range(len(paths))]
        bx, by = paths[0][s_i]
        frames.append(Frame(t=start + s_i, players=players,
                            ball=Ball(x=bx, y=by, confidence=1.0)))
    return frames


# Két, térben jól elkülönülő minta-figura (a +x kapura rajzolva).
_PLAY_A = {"name": "Beúszós kereszt",
           "attackers": [[[22.0, 10.0], [30.0, 10.0]],
                         [[24.0, 5.0], [32.0, 7.0]],
                         [[24.0, 15.0], [32.0, 13.0]]]}
_PLAY_B = {"name": "Szélső befutás",
           "attackers": [[[22.0, 2.0], [34.0, 2.0]],
                         [[22.0, 18.0], [34.0, 18.0]],
                         [[21.0, 10.0], [23.0, 10.0]]]}


def test_interpolate_play_endpoints():
    """Az interpoláció az első és utolsó kulcs-pozíciót pontosan visszaadja."""
    paths = interpolate_play(_PLAY_A["attackers"], steps=10)
    assert paths[0][0] == (22.0, 10.0)
    assert paths[0][-1] == (30.0, 10.0)
    assert all(len(p) == 10 for p in paths)


def test_play_signature_normalized_and_mirrored():
    """Az ujjlenyomat 1-re normált; a tükrözött a másik térfélre kerül."""
    sig = play_signature(_PLAY_A["attackers"])
    assert abs(sum(sig) - 1.0) < 1e-9
    mir = play_signature(_PLAY_A["attackers"], mirror_x=True)
    # a normál aláírás a jobb (x>20) térfélen, a tükrözött a balon "él"
    bins_x = 6
    right_mass = sum(v for i, v in enumerate(sig) if (i % bins_x) >= bins_x // 2)
    left_mass_m = sum(v for i, v in enumerate(mir) if (i % bins_x) < bins_x // 2)
    assert right_mass > 0.9 and left_mass_m > 0.9


def test_match_recognizes_known_play():
    """A figurát pontosan követő támadást a helyes néven ismeri fel."""
    frames = _play_frames(_PLAY_A["attackers"], steps=12)
    match = Match(_meta(), frames)
    r = match_attacks_to_playbook(match, [_PLAY_A, _PLAY_B])
    assert r["total_attacks"] == 1
    assert r["matched"].get("Beúszós kereszt") == 1
    assert r["unmatched"] == 0


def test_match_mirrored_attack_recognized():
    """A -x kapura támadó (tükrözött) mozgást is ugyanahhoz a figurához rendeli."""
    mirrored = [[[40.0 - x, y] for (x, y) in path] for path in _PLAY_A["attackers"]]
    frames = _play_frames(mirrored, team=Team.AWAY, steps=12)
    match = Match(_meta(), frames)
    r = match_attacks_to_playbook(match, [_PLAY_A], team=Team.AWAY)
    assert r["matched"].get("Beúszós kereszt") == 1


def test_unknown_attack_stays_unmatched():
    """A könyvtár egyik figurájára sem hasonlító támadás "ismeretlen" marad."""
    # minden játékos egy kupacban a beállónál — egyik mintára sem hasonlít
    frames = [_home_attack_frame(t, [35.0, 35.5, 34.5], [10.0, 9.5, 10.5])
              for t in range(8)]
    match = Match(_meta(), frames)
    r = match_attacks_to_playbook(match, [_PLAY_B], threshold=0.15)
    assert r["total_attacks"] == 1
    assert r["unmatched"] == 1
    assert not r["matched"]


def test_empty_playbook_all_unmatched():
    """Üres könyvtárnál minden támadás ismeretlen (nem hibázik)."""
    frames = _play_frames(_PLAY_A["attackers"], steps=8)
    r = match_attacks_to_playbook(Match(_meta(), frames), [])
    assert r["unmatched"] == r["total_attacks"] == 1


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


def test_setplay_efficiency_counts_goals_per_figure():
    """Az azonos mintázatú, gólra vitt támadások egy figuraként, a
    gól-hozammal együtt jelennek meg."""
    from handball.pipeline.setplays import setplay_efficiency

    frames = []
    t = 0
    for _ in range(3):  # három azonos mintájú hazai támadás...
        for i in range(8):
            frames.append(_home_attack_frame(t, [30.0, 28.0, 32.0]))
            t += 1
        # ...mindegyik gólba fut (a labda a +x kapuba repül).
        for i in range(8):
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, 33.5, 10.0)],
                ball=Ball(x=min(34.0 + i, 40.0), y=10.0,
                          confidence=1.0)))
            t += 1
        for _ in range(20):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    m = Match(MatchMeta(match_id="eff", home_team="A", away_team="B",
                        fps=25.0), frames)
    eff = setplay_efficiency(m)
    rows = eff["home"]
    assert rows, eff
    top = rows[0]
    assert top["attacks"] >= 3
    assert top["goals"] >= 2
    assert top["goal_pct"] > 0
    assert eff["away"] == []
