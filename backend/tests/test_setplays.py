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
from handball.pipeline.tactics import TacticsConfig
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
    # A klip-exporthoz a figura kezdő-frame-jei is megvannak.
    assert len(top["starts"]) == top["attacks"]
    assert all(isinstance(t_, int) for t_ in top["starts"])
    assert eff["away"] == []


def _spf_match(plan, ys=None):
    """`plan` = a lövést leadó hazai játékos azonosítói, támadásonként.

    Minden támadás UGYANAZZAL a mozgás-mintázattal indul (egy figura),
    csak a befejező más. A labda előbb a lövő KEZÉBEN van (ez az
    elengedés pillanata, innen jön a lövő-hozzárendelés), majd a +x
    kapuba repül.
    """
    xs = [30.0, 28.0, 32.0]
    ys = ys or [10.0, 4.0, 16.0]
    pos = {i + 1: (xs[i], ys[i]) for i in range(3)}
    frames = []
    t = 0
    for tid in plan:
        for _ in range(20):      # a figura mozgás-mintázata
            frames.append(_home_attack_frame(t, xs, ys))
            t += 1
        sx, sy = pos[tid]
        cast = [_pl(i + 1, Team.HOME, xs[i], ys[i]) for i in range(3)]
        for _ in range(6):       # a lövő kezében a labda
            frames.append(Frame(t=t, players=cast,
                                ball=Ball(x=sx + 0.2, y=sy,
                                          confidence=1.0)))
            t += 1
        steps = 10
        for i in range(1, steps + 1):
            f = i / steps
            frames.append(Frame(
                t=t, players=cast,
                ball=Ball(x=sx + 0.2 + (40.4 - sx - 0.2) * f,
                          y=sy + (10.0 - sy) * f, confidence=1.0)))
            t += 1
        for _ in range(30):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=5.0, y=10.0, confidence=1.0)))
            t += 1
    return Match(MatchMeta(match_id="spf", home_team="A", away_team="B",
                           fps=25.0), frames)


def test_setplay_finishers_finds_the_telegraphed_figure():
    """Ha a figura lövéseinek négyötöde ugyanarra a posztra fut ki, a
    falnak már a figura indulásakor arra az oldalra kell csúsznia."""
    from handball.pipeline.setplays import (SPF_MIN_SHOTS,
                                            setplay_finishers)

    rec = setplay_finishers(_spf_match([1, 1, 1, 1, 2]))["home"]
    assert rec["figures"], rec
    top = rec["figures"][0]
    assert sum(top["roles"].values()) >= SPF_MIN_SHOTS, rec
    assert rec["telegraphed"] is not None, rec
    assert rec["telegraphed"]["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "INDULÁSAKOR" in rec["verdict"], rec


def test_setplay_finishers_silent_with_few_shots():
    """Két lövésből nincs ítélet — a figura befejezője még nem minta."""
    from handball.pipeline.setplays import setplay_finishers

    rec = setplay_finishers(_spf_match([1, 2]))["home"]
    assert rec["telegraphed"] is None and rec["verdict"] is None, rec
    assert all(r["main_role"] is None for r in rec["figures"]), rec


# ---- Figura-koncentráció (egy figurára épül-e a támadójáték) ---------------


def _spk_match(sides, fps=25.0):
    """`sides` = támadásonként a tömörülés oldala ("bal"/"jobb"): a
    két oldal két külön figurát ad. Támadások közt átmenet."""
    frames = []
    t = 0
    for side in sides:
        y = 4.0 if side == "bal" else 16.0
        for _ in range(8):
            frames.append(_home_attack_frame(t, [28.0, 31.0, 34.0],
                                             [y, y, y]))
            t += 1
        for _ in range(4):     # átmenet: a hazai a saját térfelén
            frames.append(Frame(t=t,
                                players=[_pl(1, Team.HOME, 8.0, 10.0)],
                                ball=Ball(x=8.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    return Match(MatchMeta(match_id="spk", home_team="A", away_team="B",
                           fps=fps), frames)


def test_setplay_concentration_flags_the_one_figure_team():
    """Ha a támadások nagy része egyetlen mintából jön, konkrét
    figurára lehet készülni."""
    from handball.pipeline.setplays import (SPK_MIN_ATTACKS,
                                            setplay_concentration)

    rec = setplay_concentration(_spk_match(["bal"] * 6 + ["jobb"]))["home"]
    assert rec["attacks"] >= SPK_MIN_ATTACKS, rec
    assert rec["figures"] == 2, rec
    assert rec["top_pct"] and rec["top_pct"] >= 40.0, rec
    assert rec["cover_figures"] and rec["cover_figures"] >= 1, rec
    assert rec["verdict"] and "konkrét figurára" in rec["verdict"], rec


def test_setplay_concentration_silent_with_few_attacks():
    """Néhány támadásból nincs ítélet — a szám viszont látszik."""
    from handball.pipeline.setplays import setplay_concentration

    rec = setplay_concentration(_spk_match(["bal", "jobb"]))["home"]
    assert rec["attacks"] == 2, rec
    assert rec["verdict"] is None, rec
    assert setplay_concentration(
        _spk_match(["bal", "jobb"]))["away"]["attacks"] == 0


_SPD_PATTERNS = [[30.0, 28.0, 32.0], [26.0, 34.0, 30.0],
                 [33.0, 25.0, 29.0], [24.0, 31.0, 35.0]]


def _spd_match(first_goal=True, repeat_goal=False, patterns=None):
    """Négy különböző hazai figura: előbb mind egyszer (ELSŐ
    előfordulás), majd mind újra (ISMÉTLÉS) — sávonként a megadott
    kimenetellel (gól vagy befejezés nélkül)."""
    pats = patterns or _SPD_PATTERNS
    frames = []
    t = 0

    def _attack(xs, goal):
        nonlocal t
        for _ in range(8):
            frames.append(_home_attack_frame(t, xs))
            t += 1
        if goal:
            for i in range(8):
                frames.append(Frame(
                    t=t, players=[_pl(1, Team.HOME, 33.5, 10.0)],
                    ball=Ball(x=min(34.0 + i, 40.0), y=10.0,
                              confidence=1.0)))
                t += 1
        for _ in range(25):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    for xs in pats:
        _attack(xs, first_goal)
    for xs in pats:
        _attack(xs, repeat_goal)
    return Match(MatchMeta(match_id="spd", home_team="A", away_team="B",
                           fps=25.0), frames)


def test_setplay_decay_shows_the_value_of_recognition():
    """Ha az ismétlésre esik a figurák hozama, a fal maga megoldja a
    felismerést."""
    from handball.pipeline.setplays import SPD_GAP_PP, setplay_decay

    rec = setplay_decay(_spd_match())["home"]
    assert rec["first_attacks"] >= 4 and rec["repeat_attacks"] >= 4, rec
    assert rec["gap_pp"] is not None
    assert rec["first_pct"] - rec["repeat_pct"] >= SPD_GAP_PP, rec
    assert rec["verdict"] and "felismerést" in rec["verdict"], rec


def test_setplay_decay_silent_with_few_attacks():
    """Kevés figura-támadásból nincs ítélet."""
    from handball.pipeline.setplays import setplay_decay

    rec = setplay_decay(_spd_match(patterns=_SPD_PATTERNS[:2]))["home"]
    assert rec["gap_pp"] is None and rec["verdict"] is None, rec


# ---- Figura-indító (setplay_openers) ---------------------------------------


def _spo_match(openers, ys=None):
    """`openers` = támadásonként az a hazai játékos, AKINÉL a labda van
    a szakasz elején.

    A mozgás-mintázat minden támadásban UGYANAZ (a három játékos
    ugyanott áll), tehát egyetlen figura-klaszter jön létre — csak az
    INDÍTÓ ember más. Pont ezt méri a réteg.
    """
    xs = [30.0, 28.0, 32.0]
    ys = ys or [10.0, 4.0, 16.0]
    pos = {i + 1: (xs[i], ys[i]) for i in range(3)}
    frames = []
    t = 0
    for tid in openers:
        ox, oy = pos[tid]
        cast = [_pl(i + 1, Team.HOME, xs[i], ys[i]) for i in range(3)]
        for _ in range(20):      # a figura: a labda az INDÍTÓ kezében
            frames.append(Frame(t=t, players=cast,
                                ball=Ball(x=ox + 0.2, y=oy,
                                          confidence=1.0)))
            t += 1
        for _ in range(30):      # átmenet a következő támadásig
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=5.0, y=10.0, confidence=1.0)))
            t += 1
    return Match(MatchMeta(match_id="spo", home_team="A", away_team="B",
                           fps=25.0), frames)


def test_setplay_openers_finds_the_readable_start():
    """Ha a figura indításainak négyötöde ugyanarról a posztról jön, a
    fal már az ELSŐ passznál tudja, mi következik."""
    from handball.pipeline.setplays import (SPO_MIN_STARTS,
                                            setplay_openers)

    rec = setplay_openers(_spo_match([1, 1, 1, 1, 2]))["home"]
    assert rec["figures"], rec
    top = rec["figures"][0]
    assert sum(top["roles"].values()) >= SPO_MIN_STARTS, rec
    assert rec["telegraphed"] is not None, rec
    assert rec["telegraphed"]["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "passzsávot" in rec["verdict"], rec


def test_setplay_openers_silent_when_the_start_varies():
    """Váltogatott indítással nincs előjel — a figurát nem lehet az
    első passzból felismerni (sose hallgatólagos előjel)."""
    from handball.pipeline.setplays import setplay_openers

    # A 2-es és a 3-as ugyanazt a posztot (szélső) kapja a becsléstől,
    # ezért a váltogatást az 1-es (átlövő) és a 2-es között mérjük.
    rec = setplay_openers(_spo_match([1, 2, 1, 2, 1, 2]))["home"]
    assert rec["figures"][0]["roles"] == {"átlövő": 3, "szélső": 3}, rec
    assert rec["telegraphed"] is None and rec["verdict"] is None, rec


def test_setplay_openers_silent_on_thin_samples():
    """Két indításból még nem minta — a figura ítélete None."""
    from handball.pipeline.setplays import setplay_openers

    rec = setplay_openers(_spo_match([1, 2]))["home"]
    assert rec["telegraphed"] is None and rec["verdict"] is None, rec
    assert all(r["main_role"] is None for r in rec["figures"]), rec


# ---- Figura-könyvtár meccsek között ------------------------------------------

def _spl_match(sides, match_id="spl", goal=False, toward="right"):
    """`sides` = támadásonként a tömörülés oldala ("bal"/"jobb") a
    TÁMADÓ szemszögéből. `toward`: melyik kapura támad a hazai ("right"
    = +x, "left" = −x — a másik térfélről, tükrözve). Ha `goal`, minden
    támadás végén a labda a kapuba megy."""
    from handball.pipeline.setplays import attack_direction  # noqa: F401
    frames = []
    t = 0
    for side in sides:
        y = 4.0 if side == "bal" else 16.0
        xs = [28.0, 31.0, 34.0]
        if toward == "left":       # 180°-os forgatás: x → 40−x, y → 20−y
            xs = [40.0 - x for x in xs]
            y = 20.0 - y
        for _ in range(8):
            frames.append(_home_attack_frame(t, xs, [y, y, y]))
            t += 1
        sajat_x = 32.0 if toward == "left" else 8.0
        for _ in range(4):     # átmenet: a hazai a SAJÁT térfelén
            frames.append(Frame(t=t,
                                players=[_pl(1, Team.HOME, sajat_x, 10.0)],
                                ball=Ball(x=sajat_x, y=10.0,
                                          confidence=1.0)))
            t += 1
    return Match(MatchMeta(match_id=match_id, home_team="A",
                           away_team="B", fps=25.0), frames)


def test_az_iranynormalt_ujjlenyomat_a_tukorkepet_egynek_veszi():
    """Félidőben térfelet cserélnek: ugyanaz a figura a −x kapunál a
    nyers ujjlenyomatban tükörkép. Az irány-normált alaknak egyeznie
    kell — különben a könyvtár két figurát látna egy helyett."""
    from handball.pipeline.setplays import (
        _distance, attack_direction, normalized_signature, segment_attacks)

    # A modellben a támadás iránya a konfiguráció dolga (a félidei
    # térfélcserét a halftime-réteg a csapat-címkék cseréjével kezeli):
    # a −x kapura támadó hazai külön konfigurációval szegmentálódik.
    balra_cfg = TacticsConfig(home_attacks_positive=False)
    jobbra = segment_attacks(_spl_match(["bal"]), min_length=5)
    balra = segment_attacks(_spl_match(["bal"], toward="left"), balra_cfg,
                            min_length=5)
    assert len(jobbra) == 1 and len(balra) == 1
    assert attack_direction(jobbra[0]) == 1
    assert attack_direction(balra[0]) == -1
    a = normalized_signature(jobbra[0])
    b = normalized_signature(balra[0])
    assert _distance(a, b) < 1e-9, (a, b)
    # A nyers ujjlenyomat viszont eltér (ez a hiba, amit kikerülünk).
    assert _distance(attack_signature(jobbra[0]),
                     attack_signature(balra[0])) > 0.5


def test_a_figura_alakok_edzoi_nevet_kapnak():
    from handball.pipeline.setplays import (
        SPL_MIN_ATTACKS, setplay_shapes, shape_zone)

    m = _spl_match(["bal"] * 4 + ["jobb"] * 3)
    rows = setplay_shapes(m)["home"]
    assert len(rows) == 2
    assert rows[0]["attacks"] == 4 and rows[1]["attacks"] == 3
    assert rows[0]["attacks"] >= SPL_MIN_ATTACKS
    assert rows[0]["zone"].startswith("bal oldal")
    assert rows[1]["zone"].startswith("jobb oldal")
    # A vendégnek nincs mért támadása: üres lista, nem hiba.
    assert setplay_shapes(m)["away"] == []
    # Kevés támadás (2) nem kerül be.
    assert setplay_shapes(_spl_match(["bal"] * 2))["home"] == []
    # A név mélysége a súlypontból: a kapu előtti tömörülés "kapuelőtér".
    kozel = [0.0] * 18
    kozel[5] = 1.0          # ix=5 (a +x kapu előtt), iy=0 (bal)
    assert shape_zone(kozel) == "bal oldal, a kapuelőtér előtt"
    tavol = [0.0] * 18
    tavol[6 + 2] = 1.0      # ix=2 (a saját térfél), iy=1 (közép)
    assert shape_zone(tavol) == "közép, távolról"


def test_a_figura_konyvtar_a_meccsek_kozott_visszatero_alakot_talalja():
    """Két meccs — a másodikban a másik kapura támadnak —, mindkettőben
    a bal oldali figura a fő minta: a könyvtár EGY visszatérő figurát
    ad 2 meccsen, a csak egyszer látott jobb oldali nem "visszatérő"."""
    from handball.pipeline.setplays import (
        SPL_MIN_MATCHES, setplay_library, setplay_shapes)

    m1 = setplay_shapes(_spl_match(["bal"] * 4 + ["jobb"] * 3, "m1"))
    m2 = setplay_shapes(_spl_match(["bal"] * 3, "m2", toward="left"),
                        TacticsConfig(home_attacks_positive=False))
    sorok = ([{**r, "match_id": "m1"} for r in m1["home"]]
             + [{**r, "match_id": "m2"} for r in m2["home"]])
    lib = setplay_library(sorok)
    assert len(lib["figures"]) == 2
    fo = lib["figures"][0]
    assert fo["matches"] == 2 and fo["attacks"] == 7
    assert fo["zone"].startswith("bal oldal")
    assert [f["matches"] for f in lib["recurring"]] == [2]
    assert SPL_MIN_MATCHES == 2
    assert lib["verdict"] and "2 meccsen 7 támadás" in lib["verdict"]
    # Egy meccs adata: nincs visszatérő figura, nincs ítélet.
    egy = setplay_library([{**r, "match_id": "m1"} for r in m1["home"]])
    assert egy["recurring"] == [] and egy["verdict"] is None
    assert setplay_library([]) == {"figures": [], "recurring": [],
                                   "verdict": None}


def test_a_figura_konyvtar_a_valodi_felderitesen_at_is_megszolal():
    """A felderítés a VALÓDI rétegen keresztül: két meccs jelentése
    összefésülve visszatérő figurát ad, az edzői kulcs és a jelentés-
    szótár is viszi (a try/except-be zárt felület elgépelt mezőnevet
    némán nyelne el — ez a teszt ezért a valódi utat járja)."""
    from handball.pipeline.scouting import (
        _coach_keys, combine_reports, report_to_dict, scout_team)

    r1 = scout_team(_spl_match(["bal"] * 4 + ["jobb"] * 3, "m1"), Team.HOME)
    r2 = scout_team(_spl_match(["bal"] * 3, "m2"), Team.HOME)
    assert r1.setplay_shapes and r1.setplay_shapes[0]["match_id"] == "m1"
    egy = report_to_dict(r1)["setplay_library"]
    assert egy["recurring"] == []          # egy meccs még nem könyvtár
    ossz = combine_reports([r1, r2])
    assert len(ossz.setplay_shapes) == 3   # a sorok egymás mögé kerülnek
    lib = report_to_dict(ossz)["setplay_library"]
    assert lib["recurring"] and lib["recurring"][0]["matches"] == 2
    kulcsok = " ".join(" ".join(k) for k in _coach_keys(ossz))
    assert "meccsről meccsre visszatérő figurájuk" in kulcsok.lower()


def test_a_termeketlen_kedvenc_figura_edzes_szabaly_valodi_retegbol():
    """Az edzés-fókusz 478-as szabálya a valódi setplay_shapes rétegből:
    a leggyakoribb figura gól nélkül → megszólal; ha van gól, nem."""
    from handball.pipeline.training import training_focus

    m = _spl_match(["bal"] * 4 + ["jobb"] * 3, "tf")
    tetelek = training_focus(m)["home"]
    cimek = [t["title"] for t in tetelek]
    assert any(c.startswith("Terméketlen kedvenc figura") for c in cimek), cimek


def test_a_visszatero_figura_kezdokockai_klip_exporthoz():
    """A könyvtári alakhoz illő támadások kezdő-kockái — "mutasd a
    figurát, amit mindig hoznak". Az alak irány-normált: a másik kapura
    támadó meccsen is megtalálja."""
    from handball.pipeline.setplays import (
        recurring_figure_starts, setplay_library, setplay_shapes)

    m1 = _spl_match(["bal"] * 4 + ["jobb"] * 3, "m1")
    m2 = _spl_match(["bal"] * 3, "m2", toward="left")
    cfg2 = TacticsConfig(home_attacks_positive=False)
    sorok = ([{**r, "match_id": "m1"} for r in setplay_shapes(m1)["home"]]
             + [{**r, "match_id": "m2"}
                for r in setplay_shapes(m2, cfg2)["home"]])
    assert all("starts" in r for r in sorok)
    fo = setplay_library(sorok)["recurring"][0]
    # Az m1-ben 4 bal oldali támadás (12 kockánként), a jobb oldaliak nem.
    assert recurring_figure_starts(m1, fo["shape"], Team.HOME) == [0, 12, 24, 36]
    # Az m2-ben (a másik kapura) is megvan mind a három.
    assert recurring_figure_starts(m2, fo["shape"], Team.HOME, cfg2) == [0, 12, 24]
    # Idegen alakhoz semmi; üres alakhoz semmi; a vendégnek nincs támadása.
    tavol = [0.0] * 18
    tavol[2] = 1.0
    assert recurring_figure_starts(m1, tavol, Team.HOME) == []
    assert recurring_figure_starts(m1, [], Team.HOME) == []
    assert recurring_figure_starts(m1, fo["shape"], Team.AWAY) == []


def test_a_figura_riasztas_vegpontja_a_konyvtarbol_epul(tmp_path):
    """/figure-alerts: a csapat könyvtára a könyvtár ÖSSZES meccséből —
    egyetlen meccsnél nincs riasztás, két meccsnél a visszatérő figura
    szakaszai jönnek (t, t_end), a védekező csapat nevével."""
    import json
    import os

    import pytest

    from handball.pipeline.setplays import recurring_figure_segments

    TestClient = pytest.importorskip(
        "fastapi.testclient", reason="fastapi nincs telepítve").TestClient
    from handball.api.app import create_app

    os.environ["HANDBALL_DATA_DIR"] = str(tmp_path)
    d = tmp_path / "data" / "matches"
    d.mkdir(parents=True)
    m1 = _spl_match(["bal"] * 4 + ["jobb"] * 3, "m1")
    (d / "m1.json").write_text(json.dumps(m1.to_dict()), encoding="utf-8")
    c = TestClient(create_app())
    assert c.get("/matches/nincs/figure-alerts").status_code == 404
    assert c.get("/matches/m1/figure-alerts").json()["alerts"] == []
    m2 = _spl_match(["bal"] * 3, "m2")
    (d / "m2.json").write_text(json.dumps(m2.to_dict()), encoding="utf-8")
    c = TestClient(create_app())
    r = c.get("/matches/m1/figure-alerts").json()["alerts"]
    assert [a["t"] for a in r] == [0, 12, 24, 36]
    assert all(a["t_end"] >= a["t"] and a["team"] == "home" for a in r)
    assert r[0]["team_name"] == "A" and r[0]["zone"].startswith("bal oldal")
    assert "B: kettőzés" in r[0]["text"]
    # Üres alakra a motor-függvény sem ad szakaszt.
    assert recurring_figure_segments(m1, [], Team.HOME) == []


def test_a_csapat_konyvtara_meccsenkent_egyszer_szamol(tmp_path, monkeypatch):
    """A /figure-alerts (és a klip-számlálás) a csapat ÖSSZES meccsén
    számolna alakot minden híváskor — a primitív-gyorsítótár hatókörös,
    nem véd. A meccsenkénti alak-gyorsítótár: két hívás, meccsenként
    EGY számolás; az újrafeldolgozott (más hosszú) meccs újraszámol."""
    import json
    import os

    import pytest

    TestClient = pytest.importorskip(
        "fastapi.testclient", reason="fastapi nincs telepítve").TestClient
    from handball.api.app import create_app
    from handball.pipeline import setplays as sp

    os.environ["HANDBALL_DATA_DIR"] = str(tmp_path)
    d = tmp_path / "data" / "matches"
    d.mkdir(parents=True)
    for mid, sides in (("m1", ["bal"] * 4), ("m2", ["bal"] * 3)):
        (d / f"{mid}.json").write_text(
            json.dumps(_spl_match(sides, mid).to_dict()), encoding="utf-8")
    hivasok = []
    eredeti = sp.setplay_shapes
    monkeypatch.setattr(sp, "setplay_shapes",
                        lambda m, *a, **k: (hivasok.append(m.meta.match_id)
                                            or eredeti(m, *a, **k)))
    c = TestClient(create_app())
    r1 = c.get("/matches/m1/figure-alerts").json()["alerts"]
    r2 = c.get("/matches/m1/figure-alerts").json()["alerts"]
    assert r1 == r2 and len(r1) == 4
    assert sorted(hivasok) == ["m1", "m2"], hivasok
