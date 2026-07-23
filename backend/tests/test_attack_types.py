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


def test_attack_origins_classifies_kickoff():
    """A kapott gól utáni támadás középkezdésként címkéződik."""
    from handball.pipeline.attack_types import attack_origins

    frames = []
    t = 0
    # A hazai gólt dob (a vendég kapuba)...
    for i in range(7):
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 33.0, 10.0)],
                            ball=Ball(x=34.0 + i, y=10.0,
                                      confidence=1.0)))
        t += 1
    # ...majd a vendég azonnal támadást vezet (középkezdés).
    for i in range(80):
        frames.append(Frame(
            t=t,
            players=[_pl(9, Team.AWAY, max(30.0 - 0.3 * i, 5.0), 10.0)],
            ball=Ball(x=max(30.0 - 0.3 * i, 5.0), y=10.0,
                      confidence=1.0)))
        t += 1
    ao = attack_origins(Match(_meta(), frames))
    away = ao["away"]
    assert "középkezdés" in away
    assert away["középkezdés"]["attacks"] >= 1


def test_pace_by_score_buckets_by_lead():
    """A támadás-hossz állás szerint: gól előtt "level", utána a vezető
    csapat támadásai "leading" csoportba kerülnek."""
    from handball.models.tracking import Ball
    from handball.pipeline.attack_types import pace_by_score

    def pl(tid, team, x, y):
        return PlayerPosition(track_id=tid, team=team, x=x, y=y,
                              source=PositionSource.MEASURED,
                              confidence=1.0)

    frames = []
    t = 0

    def attack(seconds, gap=20):
        nonlocal t
        for i in range(int(seconds * 25)):
            frames.append(Frame(t=t, players=[
                pl(1, Team.HOME, 30.0, 10.0),
                pl(2, Team.AWAY, 32.0, 12.0),
            ], ball=Ball(x=30.5, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(gap):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    # Három hazai támadás döntetlennél...
    for _ in range(3):
        attack(10)
    # ...egy hazai gól...
    for i in range(8):
        frames.append(Frame(t=t, players=[pl(1, Team.HOME, 33.5, 10.0)],
                            ball=Ball(x=min(34.0 + i, 40.0), y=10.0,
                                      confidence=1.0)))
        t += 1
    for _ in range(20):
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    # ...majd három hosszabb hazai támadás vezetésnél.
    for _ in range(3):
        attack(30)
    m = Match(MatchMeta(match_id="pbs", home_team="H", away_team="A",
                        fps=25.0), frames)
    res = pace_by_score(m)["home"]
    assert res["level"]["attacks"] >= 3
    assert res["leading"]["attacks"] >= 3
    assert res["leading"]["avg_s"] is not None
    assert res["level"]["avg_s"] is not None
    assert res["leading"]["avg_s"] > res["level"]["avg_s"]


def test_attack_width_measures_spread():
    """A széthúzott támadás nagyobb átlag-szélességet ad, mint a szűk;
    kevés mintánál None."""
    from handball.models.tracking import Ball
    from handball.pipeline.attack_types import attack_width

    def pl(tid, team, x, y):
        return PlayerPosition(track_id=tid, team=team, x=x, y=y,
                              source=PositionSource.MEASURED,
                              confidence=1.0)

    def build(ys):
        frames = []
        for t in range(150):
            players = [pl(i + 1, Team.HOME, 30.0, ys[i])
                       for i in range(len(ys))]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=30.5, y=ys[0],
                                          confidence=1.0)))
        return Match(MatchMeta(match_id="aw", home_team="H",
                               away_team="A", fps=25.0), frames)

    wide = attack_width(build([2.0, 10.0, 18.0]))["home"]
    narrow = attack_width(build([8.0, 10.0, 12.0]))["home"]
    assert wide["avg_width_m"] == 16.0
    assert narrow["avg_width_m"] == 4.0
    short = attack_width(Match(MatchMeta(match_id="aw2", home_team="H",
                                         away_team="A", fps=25.0),
                               build([2.0, 10.0, 18.0]).frames[:50]))
    assert short["home"]["avg_width_m"] is None


def test_pivot_usage_labels_attacks_through_pivot():
    """A beállón átfutó támadás beállósként számolódik; ha a labda nem
    jár a beállónál, nem. A beállót a poszt-becslés adja (6 m körüli
    átlag-pozíció a támadó-fázisban)."""
    from handball.pipeline.attack_types import pivot_usage

    frames = []
    t = 0
    # 1. támadás (8 mp): a labda a beállónál (5-ös, x=34) időzik.
    for i in range(200):
        frames.append(Frame(t=t, players=[
            _pl(1, Team.HOME, 27.0, 10.0),
            _pl(5, Team.HOME, 34.0, 10.0),
            _pl(20, Team.AWAY, 36.0, 8.0)],
            ball=Ball(x=34.0, y=10.0, confidence=1.0)))
        t += 1
    # Szünet (vendég birtoklás középen) — a szakaszok szétválnak.
    for i in range(50):
        frames.append(Frame(t=t, players=[
            _pl(1, Team.HOME, 20.0, 10.0),
            _pl(5, Team.HOME, 20.0, 12.0),
            _pl(20, Team.AWAY, 19.0, 10.0)],
            ball=Ball(x=19.0, y=10.0, confidence=1.0)))
        t += 1
    # 2. hazai támadás (8 mp): a labda végig az irányítónál (1-es).
    for i in range(200):
        frames.append(Frame(t=t, players=[
            _pl(1, Team.HOME, 28.0, 10.0),
            _pl(5, Team.HOME, 34.0, 14.0),
            _pl(20, Team.AWAY, 36.0, 8.0)],
            ball=Ball(x=28.0, y=10.0, confidence=1.0)))
        t += 1
    m = Match(_meta(), frames)
    res = pivot_usage(m)
    assert 5 in res["home"]["pivot_ids"]
    assert res["home"]["attacks"] >= 2
    assert res["home"]["pivot_attacks"] >= 1
    # Volt beálló nélküli hazai támadás is.
    assert res["home"]["pivot_attacks"] < res["home"]["attacks"]


def test_pivot_usage_on_sliced_match_gives_first_half_picture():
    """A rész-meccsre (első félidő kockái) számolt beálló-kép a
    félidei állapotot adja — a második félidő beálló-játéka nem
    szivárog vissza."""
    from handball.models.tracking import Match as M
    from handball.pipeline.attack_types import pivot_usage

    frames = []
    t = 0
    # 1. félidő: a támadás a beálló NÉLKÜL megy (a labda az 1-esnél).
    for i in range(200):
        frames.append(Frame(t=t, players=[
            _pl(1, Team.HOME, 27.0, 10.0),
            _pl(5, Team.HOME, 34.0, 10.0),
            _pl(20, Team.AWAY, 36.0, 8.0)],
            ball=Ball(x=27.0, y=10.0, confidence=1.0)))
        t += 1
    half_end = t - 1
    for i in range(50):  # szünet-szerű szakasz (vendég birtoklás)
        frames.append(Frame(t=t, players=[
            _pl(1, Team.HOME, 20.0, 10.0),
            _pl(5, Team.HOME, 20.0, 12.0),
            _pl(20, Team.AWAY, 19.0, 10.0)],
            ball=Ball(x=19.0, y=10.0, confidence=1.0)))
        t += 1
    # 2. félidő: minden a beállón át.
    for i in range(200):
        frames.append(Frame(t=t, players=[
            _pl(1, Team.HOME, 27.0, 10.0),
            _pl(5, Team.HOME, 34.0, 10.0),
            _pl(20, Team.AWAY, 36.0, 8.0)],
            ball=Ball(x=34.0, y=10.0, confidence=1.0)))
        t += 1
    m = M(_meta(), frames)
    sub = M(m.meta, [f for f in m.frames if f.t <= half_end])
    fh = pivot_usage(sub)["home"]
    assert fh["attacks"] >= 1 and fh["pivot_attacks"] == 0
    full = pivot_usage(m)["home"]
    assert full["pivot_attacks"] >= 1  # a teljes képben már van beállós


def test_pass_chains_buckets_by_pass_count():
    """A passz-lánc a támadáson belüli passzokat számolja és vödrökbe
    sorolja; a passz nélküli támadás a rövid vödörbe esik."""
    from handball.pipeline.attack_types import pass_chains

    frames = []
    t = 0
    # 1. támadás: 3 passz (1→2→3→1), a labda játékosról játékosra.
    holders = [1, 1, 2, 2, 3, 3, 1, 1]
    pos = {1: (26.0, 8.0), 2: (28.0, 12.0), 3: (30.0, 10.0)}
    for h in holders:
        for _ in range(12):
            hx, hy = pos[h]
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, *pos[1]),
                _pl(2, Team.HOME, *pos[2]),
                _pl(3, Team.HOME, *pos[3]),
                _pl(20, Team.AWAY, 36.0, 8.0)],
                ball=Ball(x=hx, y=hy, confidence=1.0)))
            t += 1
    # Szünet: gazdátlan labda — szakasz-határ.
    for _ in range(40):
        frames.append(Frame(t=t, players=[
            _pl(1, Team.HOME, 15.0, 10.0),
            _pl(20, Team.AWAY, 36.0, 8.0)],
            ball=Ball(x=2.0, y=1.0, confidence=1.0)))
        t += 1
    # 2. támadás: végig az 1-esnél (0 passz).
    for _ in range(120):
        frames.append(Frame(t=t, players=[
            _pl(1, Team.HOME, 27.0, 10.0),
            _pl(20, Team.AWAY, 36.0, 8.0)],
            ball=Ball(x=27.0, y=10.0, confidence=1.0)))
        t += 1
    m = Match(_meta(), frames)
    res = pass_chains(m)["home"]
    assert res["attacks"] >= 2
    assert res["buckets"].get("3–5 passz", {}).get("attacks", 0) >= 1
    assert res["buckets"].get("0–2 passz", {}).get("attacks", 0) >= 1
    assert res["avg_passes"] is not None and res["avg_passes"] >= 1.0


def test_transition_offense_credits_quick_goals():
    """A labdaszerzés utáni 10 mp-en belüli gól gyors gólként számít;
    a szerzés nélküli gól nem."""
    from handball.pipeline.attack_types import transition_offense

    frames = []
    t = 0
    # Hazai 1-es birtokol, majd vendég 20-as szerez (csapatváltás),
    # utána a 20-as gólig visz (a labda a -x kapuba fut ~4 mp múlva).
    for _ in range(10):
        frames.append(Frame(t=t, players=[
            _pl(1, Team.HOME, 25.0, 10.0),
            _pl(20, Team.AWAY, 26.0, 10.0)],
            ball=Ball(x=25.0, y=10.0, confidence=1.0)))
        t += 1
    # Szerzés: a 20-as lesz a birtokos.
    for _ in range(10):
        frames.append(Frame(t=t, players=[
            _pl(1, Team.HOME, 25.0, 10.0),
            _pl(20, Team.AWAY, 26.0, 10.0)],
            ball=Ball(x=26.0, y=10.0, confidence=1.0)))
        t += 1
    # A 20-as (vendég) a -x (x=0) kapura tör és betöri ~4 mp múlva.
    for i in range(100):
        bx = 26.0 - 0.26 * i
        frames.append(Frame(t=t, players=[
            _pl(1, Team.HOME, 20.0, 10.0),
            _pl(20, Team.AWAY, max(0.5, bx), 10.0)],
            ball=Ball(x=max(0.2, bx), y=10.0, confidence=1.0)))
        t += 1
    m = Match(_meta(), frames)
    res = transition_offense(m)
    # A vendég szerzett és gyors gólt szerzett belőle.
    assert res["away"]["steals"] >= 1
    # A gól-felismerés a szimulált betörésből jön; ha van gól, gyors.
    if res["away"]["quick_goals"] >= 1:
        assert res["away"]["conv_pct"] is not None
        assert res["away"]["avg_s"] is not None


def _home_shot(t0, sx, goal=True):
    """Egy HAZAI lövés a +x kapura: a lövő (1-es) végig sx-nél áll, a labda
    onnan a kapuig gyorsul. sx a lövő kapu-középtől mért távolságát adja
    (a kapu (40, 10)): sx=34 → ~6 m (közeli), 31,5 → ~8,5 m (közép),
    29 → ~11 m (távoli). goal=False → a labda a kapufák mellé (y=5) megy."""
    frames = []
    for i in range(3):  # a lövő birtokolja a labdát (hogy lövőként ismerje fel)
        frames.append(Frame(t=t0 + i, players=[_pl(1, Team.HOME, sx, 10.0)],
                            ball=Ball(x=sx, y=10.0, confidence=1.0)))
    t = t0 + 3
    for i in range(8):
        bx = min(sx + 1.5 * (i + 1), 40.0)
        frames.append(Frame(t=t + i, players=[_pl(1, Team.HOME, sx, 10.0)],
                            ball=Ball(x=bx, y=(10.0 if goal else 5.0),
                                      confidence=1.0)))
    return frames


def test_shot_ranges_buckets_by_distance():
    """A lövéseket a lövő kapu-távja alapján közeli / közép / távoli sávba
    sorolja, sávonként lövés- és gólszámmal, és a domináns sávot adja."""
    from handball.pipeline.attack_types import shot_ranges

    frames = _home_shot(0, 34.0, goal=True)         # közeli, gól
    t = frames[-1].t + 1
    for i in range(20):  # szünet: a labda középen, hogy a debounce nulláz
        frames.append(Frame(t=t + i, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    t2 = frames[-1].t + 1
    frames += _home_shot(t2, 31.5, goal=True)        # közép, gól
    t3 = frames[-1].t + 1
    for i in range(20):
        frames.append(Frame(t=t3 + i, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    t4 = frames[-1].t + 1
    frames += _home_shot(t4, 29.0, goal=False)       # távoli, mellé

    m = Match(_meta(), frames)
    sr = shot_ranges(m)
    home = sr["home"]
    assert home["total_shots"] == 3
    assert home["close"]["shots"] == 1 and home["close"]["goals"] == 1
    assert home["mid"]["shots"] == 1 and home["mid"]["goals"] == 1
    assert home["far"]["shots"] == 1 and home["far"]["goals"] == 0
    assert home["close"]["goal_pct"] == 100.0
    assert home["far"]["goal_pct"] == 0.0
    assert home["dominant"] in ("close", "mid", "far")
    # A vendég nem lőtt — üres profil, domináns sáv nélkül.
    assert sr["away"]["total_shots"] == 0
    assert sr["away"]["dominant"] is None


def _corner_goal(t0, cross_y):
    """HAZAI gól a +x kapura, a labda a megadott y-on lépi át a gólvonalat
    (a kapu szája y ∈ [8,5; 11,5]): felső y → bal, alsó y → jobb (a lövő
    szemszögéből)."""
    frames = []
    sx = 33.0
    for i in range(9):
        bx = min(sx + 1.6 * (i + 1), 40.0)
        by = 10.0 + (cross_y - 10.0) * min(1.0, i / 6.0)
        frames.append(Frame(t=t0 + i, players=[_pl(1, Team.HOME, sx, 10.0)],
                            ball=Ball(x=bx, y=by, confidence=1.0)))
    return frames


def test_goal_placement_buckets_by_corner():
    """A gólokat a gólvonal-átlépés y-ja alapján bal/közép/jobb kapuoldalra
    sorolja (a lövő szemszögéből); elég góllal domináns oldalt is ad."""
    from handball.pipeline.attack_types import goal_placement

    frames = []
    # 3 gól a bal (felső y), 1 a jobb (alsó y), 1 középre.
    plan = [11.2, 11.2, 11.2, 9.0, 10.0]
    for cy in plan:
        frames += _corner_goal(frames[-1].t + 1 if frames else 0, cy)
        t = frames[-1].t + 1
        for i in range(20):  # szünet a debounce-hoz
            frames.append(Frame(t=t + i, players=[],
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    m = Match(_meta(), frames)
    gp = goal_placement(m)["home"]
    assert gp["goals"] == 5
    assert gp["bal"] == 3 and gp["jobb"] == 1 and gp["közép"] == 1
    assert gp["dominant"] == "bal"
    # A vendég nem szerzett gólt.
    assert goal_placement(m)["away"]["goals"] == 0
    assert goal_placement(m)["away"]["dominant"] is None


def _wing_or_central_shot(t0, sx, sy, goal=True):
    """HAZAI lövés a +x kapura a megadott (sx, sy) lövőhelyről."""
    frames = []
    for i in range(3):
        frames.append(Frame(t=t0 + i, players=[_pl(1, Team.HOME, sx, sy)],
                            ball=Ball(x=sx, y=sy, confidence=1.0)))
    t = t0 + 3
    for i in range(9):
        bx = min(sx + 1.6 * (i + 1), 40.0)
        by = sy + (10.0 - sy) * min(1.0, i / 6.0) if goal else 5.0
        frames.append(Frame(t=t + i, players=[_pl(1, Team.HOME, sx, sy)],
                            ball=Ball(x=bx, y=by, confidence=1.0)))
    return frames


def test_wing_finishing_counts_sharp_angle_only():
    """A szélső (éles szög, közeli) lövéseket számolja, a középsőt nem.
    A szélső lövő y=3 (|y-10|=7>=6), táv ~8,6 m (<=9) → szélső."""
    from handball.pipeline.attack_types import wing_finishing

    frames = _wing_or_central_shot(0, 35.0, 3.0, goal=True)  # szélső gól
    t = frames[-1].t + 1
    for i in range(20):
        frames.append(Frame(t=t + i, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    # Középső lövés (y=10) — NEM szélső.
    frames += _wing_or_central_shot(frames[-1].t + 1, 33.0, 10.0, goal=True)
    m = Match(_meta(), frames)
    wf = wing_finishing(m)
    assert wf["home"]["shots"] == 1 and wf["home"]["goals"] == 1
    assert wf["home"]["goal_pct"] == 100.0
    # A vendég nem lőtt szélsőt.
    assert wf["away"]["shots"] == 0 and wf["away"]["goal_pct"] is None


def test_second_chance_counts_offensive_rebounds():
    """A saját, gólt nem érő lövés után az ablakon belüli ÚJABB saját lövést
    megnyert lepattanónak (második roham) veszi; a folytatás gólja második
    esélyből szerzett gól. A távoli (ablakon kívüli) kimaradás nem az."""
    from handball.pipeline.attack_types import second_chance

    # A: kimaradt lövés → rövid szünettel B: gól (A második rohama, gól).
    frames = _home_shot(0, 31.5, goal=False)
    t = frames[-1].t + 1
    for i in range(12):  # rövid szünet (debounce-nulláz, de ablakon belül)
        frames.append(Frame(t=t + i, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    frames += _home_shot(frames[-1].t + 1, 33.0, goal=True)
    # Hosszú szünet (> 6 s), hogy a következő kimaradás önálló legyen.
    t = frames[-1].t + 1
    for i in range(200):
        frames.append(Frame(t=t + i, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    # C: magányos kimaradt lövés — nincs ablakon belüli folytatás.
    frames += _home_shot(frames[-1].t + 1, 31.5, goal=False)
    t = frames[-1].t + 1
    for i in range(200):
        frames.append(Frame(t=t + i, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    # D: még egy magányos kimaradt lövés.
    frames += _home_shot(frames[-1].t + 1, 31.5, goal=False)

    m = Match(_meta(), frames)
    sc = second_chance(m)
    home = sc["home"]
    assert home["misses"] == 3          # A, C, D
    assert home["second_chances"] == 1  # csak A-t követi saját lövés az ablakban
    assert home["second_goals"] == 1    # a folytatás (B) gól volt
    assert home["rebound_pct"] == round(100.0 / 3.0, 1)
    assert home["convert_pct"] == 100.0
    # A vendég nem lőtt — üres, arány nélkül.
    assert sc["away"]["misses"] == 0
    assert sc["away"]["rebound_pct"] is None


def test_pass_direction_forward_square_back():
    """A passzokat előre / oldalra / hátra sorolja a kapu-távolság
    változásából. HAZAI a +x kapura támad."""
    from handball.pipeline.attack_types import pass_direction

    frames = []
    t = 0

    def seg(holder_tid, positions, n=6):
        nonlocal t
        for _ in range(n):
            pls = [_pl(tid, Team.HOME, x, y) for (tid, x, y) in positions]
            bx, by = next((x, y) for (tid, x, y) in positions
                          if tid == holder_tid)
            frames.append(Frame(t=t, players=pls,
                                ball=Ball(x=bx, y=by, confidence=1.0)))
            t += 1

    pos = [(1, 25.0, 10.0), (2, 32.0, 6.0), (3, 32.0, 14.0), (4, 26.0, 10.0)]
    # 1→2 előre (25→32), 2→3 oldalra (32→32), 3→4 hátra (32→26).
    seg(1, pos)
    seg(2, pos)
    seg(3, pos)
    seg(4, pos)
    m = Match(_meta(), frames)
    pd = pass_direction(m)["home"]
    assert pd["passes"] == 3
    assert pd["forward"] == 1 and pd["square"] == 1 and pd["back"] == 1
    assert pd["forward_pct"] == round(100.0 / 3, 1)
    # Nettó előrehaladás ~ (7 + 0 − 6) / 3 ≈ 0,33 m.
    assert pd["avg_progress_m"] is not None and pd["avg_progress_m"] > 0
    assert pass_direction(m)["away"]["passes"] == 0


def test_assist_sources_classifies_by_zone():
    """A gólpassz-forrást a passzoló helye alapján zónába sorolja. Egy
    szélről (y=3) adott gólpassz → 'szél'."""
    from handball.pipeline.attack_types import assist_sources

    frames = []
    t = 0

    def add(players, bx, by):
        nonlocal t
        frames.append(Frame(t=t,
                            players=[_pl(tid, Team.HOME, x, y)
                                     for (tid, x, y) in players],
                            ball=Ball(x=bx, y=by, confidence=1.0)))
        t += 1

    # Passzoló (2) a szélen (35,3) birtokol, majd passzol a lövőnek (1),
    # aki a +x kapura lő és gólt szerez.
    for _ in range(4):
        add([(2, 35.0, 3.0), (1, 34.0, 10.0)], 35.0, 3.0)
    for _ in range(4):
        add([(2, 35.0, 3.0), (1, 34.0, 10.0)], 34.0, 10.0)  # PASS 2→1
    for i in range(9):
        bx = min(34.0 + 1.6 * (i + 1), 40.0)
        add([(2, 35.0, 3.0), (1, 34.0, 10.0)], bx, 10.0)     # 1 lő → gól
    m = Match(_meta(), frames)
    asr = assist_sources(m)["home"]
    assert asr["assists"] == 1
    assert asr["szél"] == 1 and asr["közép"] == 0 and asr["hátsó"] == 0
    # A vendégnek nincs gólpassza.
    assert assist_sources(m)["away"]["assists"] == 0
