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


def test_shot_timing_early_vs_waiting():
    """5 lőtt támadás: 3 korai (a támadás ~5. mp-ében lő) és 2 kivárt
    (~20 mp után) → 60% korai arány; kevés lövésnél nincs ítélet."""
    from handball.pipeline.attack_types import shot_timing

    frames = []

    def attack_then_shot(seconds):
        # HAZAI támadás `seconds` hosszan a kapu előteréig, majd lövés (gól).
        t0 = len(frames)
        frames.extend(_attack_frames(t0, seconds, 22.0, 33.0))
        t = len(frames)
        for i in range(8):
            bx = min(33.0 + 1.5 * (i + 1), 40.0)
            frames.append(Frame(t=t + i,
                                players=[_pl(1, Team.HOME, 33.0, 10.0)],
                                ball=Ball(x=bx, y=10.0, confidence=1.0)))
        t = len(frames)
        for i in range(60):  # szünet: se labda, se játékos (szakasz-határ)
            frames.append(Frame(t=t + i, players=[], ball=None))

    for _ in range(3):
        attack_then_shot(5.0)    # korai lövés (~5 mp)
    for _ in range(2):
        attack_then_shot(20.0)   # kivárt lövés (~20 mp)

    st = shot_timing(Match(_meta(), frames))
    h = st["home"]
    assert h["shots"] == 5
    assert h["early"] == 3
    assert h["early_pct"] == 60.0
    assert h["avg_s"] is not None and 8.0 < h["avg_s"] < 20.0
    # A vendég nem lőtt → nincs ítélet.
    assert st["away"]["early_pct"] is None


def test_team_pace_fade_needs_halftime_and_minutes():
    """Félidő-jellel és 8+ perces felekkel a drop számolódik (támadás
    nélkül 0,0); félidő-jel nélkül vagy rövid féllel None."""
    from handball.pipeline.attack_types import team_pace_fade

    def active(t0, seconds):
        frames = []
        for i in range(int(seconds * 25)):
            players = [_pl(100 + k, Team.HOME, 12.0 + k, 4.0 + k)
                       for k in range(4)]
            players += [_pl(200 + k, Team.AWAY, 26.0 + k, 4.0 + k)
                        for k in range(4)]
            frames.append(Frame(t=t0 + i, players=players,
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        return frames

    frames = active(0, 510)
    t = frames[-1].t + 1
    frames += [Frame(t=t + i, players=[], ball=None)
               for i in range(int(90 * 25))]
    t = frames[-1].t + 1
    frames += active(t, 510)
    tpf = team_pace_fade(Match(_meta(), frames))
    assert tpf["home"]["drop_per_min"] == 0.0
    assert tpf["home"]["fh_min"] >= 8.0

    # Félidő-jel nélkül nincs ítélet.
    no_ht = team_pace_fade(Match(_meta(), active(0, 300)))
    assert no_ht["home"]["drop_per_min"] is None


def test_attack_side_bias_flags_one_sided_attack():
    """A hazai szélső-sávos lövéseiből 6 a bal (+y), 2 a jobb (−y)
    oldalról jön → 75% bal-részrehajlás; kevés lövésnél nincs ítélet."""
    from handball.pipeline.attack_types import attack_side_bias

    def _shot(t0, y0):
        fr = []
        for i in range(8):
            fr.append(Frame(
                t=t0 + i,
                players=[_pl(1, Team.HOME, 36.6, y0)],
                ball=Ball(x=min(37.0 + 0.8 * i, 40.0), y=y0,
                          confidence=1.0)))
        fr.append(Frame(t=t0 + 9, players=[],
                        ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        return fr

    frames = []
    t = 0
    for y0 in (16.0, 16.0, 16.0, 16.0, 16.0, 16.0, 4.0, 4.0):
        frames += _shot(t, y0)
        t += 40
    sb = attack_side_bias(Match(_meta(), frames))
    h = sb["home"]
    assert h["left"] == 6 and h["right"] == 2
    assert h["bias_side"] == "bal"
    assert abs(h["bias_pct"] - 75.0) < 0.1
    assert sb["away"]["bias_side"] is None

    # Kevés szélső-sávos lövés: nincs ítélet.
    few = attack_side_bias(Match(_meta(), _shot(0, 16.0)))
    assert few["home"]["bias_side"] is None


def test_attack_rhythm_flags_metronome_offense():
    """12 egyforma (20 mp-es) hazai támadás → cv ~0, kiszámítható óra;
    kevés támadásnál nincs ítélet."""
    from handball.pipeline.attack_types import attack_rhythm

    def _neutral(t0, seconds=4.0):
        players = [_pl(50 + k, Team.HOME if k < 4 else Team.AWAY,
                       8.0 + 3.0 * k, 4.0 + (k % 4)) for k in range(8)]
        return [Frame(t=t0 + i, players=players,
                      ball=Ball(x=20.0, y=10.0, confidence=1.0))
                for i in range(int(seconds * 25))]

    frames = []
    t = 0
    for _ in range(12):
        frames += _attack_frames(t, 20.0, 24.0, 36.0)
        t = frames[-1].t + 1
        frames += _neutral(t)
        t = frames[-1].t + 1
    ar = attack_rhythm(Match(_meta(), frames))
    h = ar["home"]
    assert h["n"] == 12
    assert h["avg_s"] is not None and 18.0 <= h["avg_s"] <= 21.0
    assert h["cv"] is not None and h["cv"] <= 0.1

    # Kevés támadás: nincs ítélet.
    few = attack_rhythm(Match(_meta(), _attack_frames(0, 20.0, 24.0,
                                                      36.0)))
    assert few["home"]["n"] >= 1 and few["home"]["cv"] is None


def test_assist_reliance_flags_collective_finishing():
    """5 gólpasszos + 2 egyéni gól → 71% asszisztált, "kollektív"
    stílus; kevés gólnál nincs ítélet."""
    from handball.pipeline.attack_types import assist_reliance

    def _goal(t0, assisted):
        players = [_pl(1, Team.HOME, 33.0, 10.0)]
        if assisted:
            players = [_pl(2, Team.HOME, 30.0, 10.0)] + players
        frames = []
        t = t0
        if assisted:  # p2 birtokol, majd passz p1-nek
            for i in range(5):
                frames.append(Frame(t=t + i, players=players,
                                    ball=Ball(x=30.0, y=10.0,
                                              confidence=1.0)))
            t += 5
        for i in range(5):  # p1 birtokol
            frames.append(Frame(t=t + i, players=players,
                                ball=Ball(x=33.0, y=10.0, confidence=1.0)))
        t += 5
        for i in range(8):  # lövés a kapuba
            frames.append(Frame(t=t + i, players=players,
                                ball=Ball(x=min(34.0 + i, 40.0), y=10.0,
                                          confidence=1.0)))
        t += 8
        for i in range(200):  # hosszú szünet a következő gólig
            frames.append(Frame(t=t + i, players=[],
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        return frames

    frames = []
    for assisted in (True, True, True, True, True, False, False):
        frames += _goal(frames[-1].t + 1 if frames else 0, assisted)
    ar = assist_reliance(Match(_meta(), frames))
    h = ar["home"]
    assert h["goals"] == 7 and h["assisted"] == 5
    assert h["assisted_pct"] is not None
    assert abs(h["assisted_pct"] - 100.0 * 5 / 7) < 0.5
    assert h["style"] == "kollektív"

    # Kevés gól: nincs ítélet.
    few = assist_reliance(Match(_meta(), frames[:500]))
    assert few["home"]["style"] is None and few["home"]["assisted_pct"] is None


def test_assist_concentration_flags_single_playmaker():
    """Hat gólpasszos gólból ötöt ugyanaz a játékos készít elő →
    koncentrált előkészítés; kevés gólpasszos gólnál nincs ítélet."""
    from handball.pipeline.attack_types import assist_concentration

    frames = []
    t = 0

    def _assisted_goal(passer_id):
        # Passz (passer → 2-es), a 2-es gólja a +x kapura, majd
        # üres-labdás szünet választja el a köröket.
        nonlocal t, frames
        frames.append(Frame(t=t, players=[
            _pl(passer_id, Team.HOME, 25.0, 10.0),
            _pl(2, Team.HOME, 30.0, 10.0)],
            ball=Ball(x=25.0, y=10.0, confidence=1.0)))
        t += 1
        for _ in range(3):
            frames.append(Frame(t=t, players=[
                _pl(passer_id, Team.HOME, 25.0, 10.0),
                _pl(2, Team.HOME, 30.0, 10.0)],
                ball=Ball(x=30.0, y=10.0, confidence=1.0)))
            t += 1
        for i in range(7):
            frames.append(Frame(t=t, players=[
                _pl(2, Team.HOME, 30.0, 10.0)],
                ball=Ball(x=min(34.0 + i, 40.0), y=10.0,
                          confidence=1.0)))
            t += 1
        for _ in range(50):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    for _ in range(5):
        _assisted_goal(1)   # a fő előkészítő
    _assisted_goal(3)       # egy másik előkészítő

    ac = assist_concentration(Match(_meta(), frames))
    h = ac["home"]
    assert h["assists"] >= 6
    assert h["top_player_id"] == 1
    assert h["share"] is not None and h["share"] >= 0.5
    assert h["concentrated"] is True
    # A vendégnek nincs gólpasszos gólja: nincs ítélet.
    assert ac["away"]["concentrated"] is None

    # Kevés gólpasszos gól: nincs ítélet.
    few = assist_concentration(Match(_meta(), frames[:130]))
    assert few["home"]["concentrated"] is None


def test_goal_buildup_separates_direct_and_combinative():
    """A hazai góljai 1 passzból esnek (direkt), a vendégé 6 passzos
    akciókból (kombinatív); kevés gólnál nincs ítélet."""
    from handball.pipeline.attack_types import goal_buildup

    frames = []
    t = 0

    def _sep():
        nonlocal t, frames
        for _ in range(60):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    def _direct_goal():
        # 1 passz (1-es → 2-es), a 2-es viszi és lövi: direkt gól.
        nonlocal t, frames
        pls = [_pl(1, Team.HOME, 25.0, 10.0),
               _pl(2, Team.HOME, 30.0, 10.0)]
        for _ in range(4):
            frames.append(Frame(t=t, players=pls,
                                ball=Ball(x=25.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(3):
            frames.append(Frame(t=t, players=pls,
                                ball=Ball(x=30.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        frames.append(Frame(t=t, players=[_pl(2, Team.HOME, 33.0, 10.0)],
                            ball=Ball(x=33.0, y=10.0, confidence=1.0)))
        t += 1
        for i in range(7):
            frames.append(Frame(t=t, players=[
                _pl(2, Team.HOME, 33.0, 10.0)],
                ball=Ball(x=min(34.0 + i, 40.0), y=10.0,
                          confidence=1.0)))
            t += 1
        _sep()

    def _combinative_goal():
        # 6 passz a 11-12-13 háromszögben (csak y-irányú ugrások),
        # majd a 11-es lövése: kombinatív gól a -x kapura.
        nonlocal t, frames
        spots = {11: (15.0, 10.0), 12: (15.0, 4.0), 13: (15.0, 16.0)}
        pls = [_pl(pid, Team.AWAY, x, y)
               for pid, (x, y) in spots.items()]
        order = [11, 12, 13, 11, 12, 13, 11]
        for holder in order:
            hx, hy = spots[holder]
            for _ in range(4):
                frames.append(Frame(t=t, players=pls,
                                    ball=Ball(x=hx, y=hy,
                                              confidence=1.0)))
                t += 1
        for i in range(19):
            frames.append(Frame(t=t, players=pls,
                                ball=Ball(x=max(14.2 - 0.8 * i, 0.0),
                                          y=10.0, confidence=1.0)))
            t += 1
        _sep()

    for _ in range(4):
        _direct_goal()
    for _ in range(4):
        _combinative_goal()

    gb = goal_buildup(Match(_meta(), frames))
    h, a = gb["home"], gb["away"]
    assert h["goals"] >= 4 and h["style"] == "direkt"
    assert a["goals"] >= 4 and a["style"] == "kombinatív"

    # Kevés gól: nincs ítélet.
    few = goal_buildup(Match(_meta(), frames[:200]))
    assert few["home"]["style"] is None


def test_side_switching_separates_cross_court_and_one_sided():
    """A hazai minden passza oldalváltó keresztpassz, a vendégé mind
    rövid, azonos oldali; kevés passznál nincs ítélet."""
    from handball.pipeline.attack_types import side_switching

    frames = []
    t = 0

    def _pass_block(team, spots):
        # A labda a két pont közt jár (5-5 kocka birtoklás): minden
        # elkapás egy passz a támadó térfélen.
        nonlocal t, frames
        ids = (1, 2) if team == Team.HOME else (11, 12)
        pls = [_pl(ids[0], team, spots[0][0], spots[0][1]),
               _pl(ids[1], team, spots[1][0], spots[1][1])]
        for k in range(34):
            hx, hy = spots[k % 2]
            for _ in range(5):
                frames.append(Frame(t=t, players=pls,
                                    ball=Ball(x=hx, y=hy,
                                              confidence=1.0)))
                t += 1

    # Hazai (+x térfél): keresztpasszok a két szél közt (Δy = 14 m).
    _pass_block(Team.HOME, [(30.0, 3.0), (30.0, 17.0)])
    # Vendég (-x térfél): rövid passzok azonos oldalon (Δy = 4 m).
    _pass_block(Team.AWAY, [(10.0, 8.0), (10.0, 12.0)])

    ssw = side_switching(Match(_meta(), frames))
    h, a = ssw["home"], ssw["away"]
    assert h["passes"] >= 30 and h["style"] == "oldalváltó"
    assert a["passes"] >= 30 and a["style"] == "egy-oldalas"
    assert h["switch_pct"] > a["switch_pct"]

    # Kevés passz: nincs ítélet.
    few = side_switching(Match(_meta(), frames[:100]))
    assert few["home"]["style"] is None


def test_screen_usage_separates_screened_and_isolated_shooters():
    """A hazai lövéseinél társ zárja el a lövő őrzőjét (elzárásos), a
    vendégnél a lövő egyedül van a védőjével (elzárás nélküli);
    kevés őrzött lövésnél nincs ítélet."""
    from handball.pipeline.attack_types import screen_usage

    frames = []
    t = 0

    def _shot(home_side, screened):
        # Őrzött lövés: a védő a lövő mellett (1,5 m); elzárásnál egy
        # társ is a védő mellett áll (1 m-re).
        nonlocal t, frames
        if home_side:
            team, opp = Team.HOME, Team.AWAY
            sx, gx = 30.0, 40.0
        else:
            team, opp = Team.AWAY, Team.HOME
            sx, gx = 10.0, 0.0
        players = [_pl(1 if home_side else 11, team, sx, 10.0),
                   _pl(20 if home_side else 21, opp, sx + 1.5, 10.0)]
        if screened:
            players.append(_pl(2 if home_side else 12, team,
                               sx + 1.5, 11.0))
        for _ in range(30):
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=sx, y=10.0,
                                          confidence=1.0)))
            t += 1
        for i in range(14):
            bx = (min(sx + 0.8 * (i + 1), gx) if home_side
                  else max(sx - 0.8 * (i + 1), gx))
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=bx, y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(40):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=gx, y=10.0,
                                          confidence=1.0)))
            t += 1

    for _ in range(8):
        _shot(True, screened=True)
    for _ in range(8):
        _shot(False, screened=False)

    scu = screen_usage(Match(_meta(), frames))
    h, a = scu["home"], scu["away"]
    assert h["shots"] >= 8 and h["style"] == "elzárásos"
    assert a["shots"] >= 8 and a["style"] == "elzárás nélküli"
    assert h["screen_pct"] > a["screen_pct"]

    # Kevés őrzött lövés: nincs ítélet.
    few = screen_usage(Match(_meta(), frames[:200]))
    assert few["home"]["style"] is None


def test_pass_risk_flags_lost_long_balls():
    """A hazai hosszú passzai zömmel az ellenfélnél kötnek ki, a
    rövidek nem → kockázatos hosszú passz; kevés kísérletnél nincs
    ítélet."""
    from handball.pipeline.attack_types import pass_risk

    frames = []
    t = 0

    def _transfer(dist_y, lost):
        # A labda a 1-esről a társ (2-es) vagy — eladásnál — az
        # ellenfél (20-as) kezébe kerül; a fogadó dist_y méterre áll.
        nonlocal t, frames
        taker = (_pl(20, Team.AWAY, 30.0, 10.0 + dist_y) if lost
                 else _pl(2, Team.HOME, 30.0, 10.0 + dist_y))
        pls = [_pl(1, Team.HOME, 30.0, 10.0), taker]
        for _ in range(5):
            frames.append(Frame(t=t, players=pls,
                                ball=Ball(x=30.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(5):
            frames.append(Frame(t=t, players=pls,
                                ball=Ball(x=30.0, y=10.0 + dist_y,
                                          confidence=1.0)))
            t += 1
        # A labda visszakerül az 1-eshez: a következő kísérlet innen
        # indul (eladás után "visszaszerzés").
        for _ in range(5):
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, 30.0, 10.0)],
                ball=Ball(x=30.0, y=10.0, confidence=1.0)))
            t += 1

    for i in range(10):
        _transfer(12.0, lost=(i < 6))   # hosszú: 60% elveszik
    for i in range(10):
        _transfer(3.0, lost=False)      # rövid: nincs eladás

    prk = pass_risk(Match(_meta(), frames))
    h = prk["home"]
    assert h["long_tries"] >= 8 and h["short_tries"] >= 8
    assert h["verdict"] == "kockázatos"
    assert h["long_to_pct"] > h["short_to_pct"]

    # Kevés kísérlet: nincs ítélet.
    few = pass_risk(Match(_meta(), frames[:100]))
    assert few["home"]["verdict"] is None


def test_overload_finishing_separates_overload_and_set_defense():
    """A hazai létszámfölényben mind gólt lő, felállt fal ellen alig —
    "fölény-függő"; a lövés nélküli vendégnél nincs ítélet."""
    from handball.pipeline.attack_types import overload_finishing

    frames = []
    t = 0

    def _shot(overload, goal):
        """Hazai lövés a +x kapura; fölényben 3 támadó áll 1 védővel
        szemben a támadott térfélen, felállt fal ellen 2 a 4-gyel."""
        nonlocal t, frames
        players = [_pl(1, Team.HOME, 30.0, 10.0)]
        if overload:
            players += [_pl(2, Team.HOME, 32.0, 6.0),
                        _pl(3, Team.HOME, 34.0, 14.0),
                        _pl(21, Team.AWAY, 36.0, 10.0)]
        else:
            players += [_pl(2, Team.HOME, 32.0, 6.0),
                        _pl(21, Team.AWAY, 34.0, 8.0),
                        _pl(22, Team.AWAY, 35.0, 10.0),
                        _pl(23, Team.AWAY, 36.0, 12.0),
                        _pl(24, Team.AWAY, 37.0, 14.0)]
        for _ in range(30):
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=30.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        # Gólnál a kapu közepére, kihagyásnál a kapufa mellé megy.
        y_end = 10.0 if goal else 3.0
        for i in range(14):
            bx = min(30.0 + 0.8 * (i + 1), 40.0)
            by = 10.0 + (y_end - 10.0) * (i + 1) / 14.0
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=bx, y=by, confidence=1.0)))
            t += 1
        for _ in range(40):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    for _ in range(6):
        _shot(overload=True, goal=True)
    for k in range(6):
        _shot(overload=False, goal=(k == 0))

    ovl = overload_finishing(Match(_meta(), frames))
    h = ovl["home"]
    assert h["overload_shots"] == 6 and h["overload_goals"] == 6
    assert h["set_shots"] == 6 and h["set_goals"] == 1
    assert h["overload_pct"] > h["set_pct"]
    assert h["verdict"] == "fölény-függő"

    # A vendégnek nincs lövése → nincs arány és nincs ítélet.
    a = ovl["away"]
    assert a["overload_shots"] == 0 and a["set_shots"] == 0
    assert a["gap_pp"] is None and a["verdict"] is None


def test_shooter_placement_flags_predictable_finisher():
    """Az 1-es hazai lövő öt góljából négy a bal (felső y) sarokba megy
    → kiszámítható; a négy gól alatti lövőnél nincs ítélet."""
    from handball.pipeline.attack_types import shooter_placement

    frames = []
    t = 0

    def _goal(pid, y_end):
        """A pid-es hazai lövő gólja a +x kapu megadott magasságába."""
        nonlocal t, frames
        shooter = [_pl(pid, Team.HOME, 31.0, 10.0)]
        for i in range(12):
            bx = min(31.0 + 0.9 * (i + 1), 40.0)
            by = 10.0 + (y_end - 10.0) * (i + 1) / 12.0
            frames.append(Frame(t=t, players=shooter,
                                ball=Ball(x=bx, y=by, confidence=1.0)))
            t += 1
        for _ in range(40):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    # A +x kapunál a "bal" a felső y (11,3), a "jobb" az alsó (8,7).
    for _ in range(4):
        _goal(1, 11.3)
    _goal(1, 8.7)
    for _ in range(2):
        _goal(2, 8.7)

    shp = shooter_placement(Match(_meta(), frames))
    h = shp["home"]
    one = next(p for p in h["players"] if p["player_id"] == 1)
    assert one["goals"] == 5 and one["bal"] == 4 and one["jobb"] == 1
    assert one["dominant"] == "bal" and one["share_pct"] == 80.0
    assert h["predictable"]["player_id"] == 1

    # A két góllal szereplő 2-es lövőnél nincs ítélet.
    two = next(p for p in h["players"] if p["player_id"] == 2)
    assert two["goals"] == 2
    assert two["dominant"] is None and two["share_pct"] is None


# ---- Támadás-indítók (ki hozza fel a labdát) ---------------------------------

def _starter_match(starters, fps=25.0):
    """HAZAI támadás-sorozat: a `starters` elemenként megadja, melyik
    hazai játékos (track_id) birtokolja a labdát a támadás első
    kockáin; utána az 1-es viszi tovább. A támadásokat egy-egy rövid
    vendég-birtoklás választja el."""
    from handball.pipeline.attack_types import attack_starters  # noqa: F401

    frames = []
    t = 0

    def _home(holder_id, seconds):
        """Hazai támadás-kockák: a labda a `holder_id` játékosnál."""
        nonlocal t, frames
        for i in range(int(seconds * fps)):
            x = 24.0 + 0.05 * i
            spots = {1: (x, 10.0), 2: (x - 1.5, 5.0), 3: (x - 1.5, 15.0)}
            players = [_pl(pid, Team.HOME, px, py)
                       for pid, (px, py) in spots.items()]
            players.append(_pl(9, Team.HOME, 1.5, 10.0, role="kapus"))
            players += [_pl(21, Team.AWAY, 37.0, 8.0),
                        _pl(22, Team.AWAY, 37.0, 12.0)]
            hx, hy = spots[holder_id]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=hx, y=hy, confidence=1.0)))
            t += 1

    def _away(seconds):
        """Vendég-birtoklás: elválasztja a két hazai támadást."""
        nonlocal t, frames
        for i in range(int(seconds * fps)):
            x = 18.0 - 0.05 * i
            players = [_pl(1, Team.HOME, 3.0, 8.0),
                       _pl(2, Team.HOME, 3.0, 12.0),
                       _pl(3, Team.HOME, 5.0, 10.0),
                       _pl(9, Team.HOME, 1.5, 10.0, role="kapus"),
                       _pl(21, Team.AWAY, x, 10.0),
                       _pl(22, Team.AWAY, x - 3.0, 14.0)]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1

    for pid in starters:
        _home(pid, 1.0)      # az indító kockái
        _home(1, 2.0)        # utána az 1-es viszi
        _away(1.5)
    return Match(_meta(fps), frames)


def test_attack_starters_finds_the_single_outlet():
    """Hat támadásból ötöt a 2-es indít → ő a kihozatali kulcs."""
    from handball.pipeline.attack_types import attack_starters

    rec = attack_starters(_starter_match([2, 2, 2, 2, 2, 3]))["home"]
    assert rec["attacks"] == 6
    top = rec["top"]
    assert top is not None
    assert top["player_id"] == 2 and top["starts"] == 5
    assert top["share_pct"] > 80.0
    # A vendég oldalon az elválasztó birtoklásokat a 21-es indítja.
    away = attack_starters(_starter_match([2] * 6))["away"]
    assert away["top"] is not None and away["top"]["player_id"] == 21


def test_attack_starters_shared_outlet_has_no_top():
    """Ha három ember osztozik a felhozatalon, nincs kiemelt indító."""
    from handball.pipeline.attack_types import attack_starters

    rec = attack_starters(_starter_match([1, 2, 3, 1, 2, 3]))["home"]
    assert rec["attacks"] == 6
    assert rec["top"] is None
    assert {p["player_id"] for p in rec["players"]} == {1, 2, 3}


def test_attack_starters_needs_enough_attacks():
    """Kevés (6-nál kevesebb) mért támadásnál nincs ítélet."""
    from handball.pipeline.attack_types import attack_starters

    rec = attack_starters(_starter_match([2, 2, 2]))["home"]
    assert rec["attacks"] == 3 and rec["top"] is None


# ---- Támadás-kimenetel (mivel zárulnak a támadásaik) -------------------------

def _outcome_match(kinds, fps=25.0):
    """HAZAI támadás-sorozat: a `kinds` elemenként "lövés" vagy
    "eladás" — a támadásokat egy-egy vendég-birtoklás választja el."""
    frames = []
    t = 0

    def _home(seconds):
        nonlocal t, frames
        for i in range(int(seconds * fps)):
            x = 24.0 + 0.05 * i
            players = [_pl(1, Team.HOME, x, 10.0),
                       _pl(2, Team.HOME, x - 2.0, 6.0),
                       _pl(9, Team.HOME, 1.5, 10.0, role="kapus"),
                       _pl(21, Team.AWAY, 37.0, 8.0),
                       _pl(22, Team.AWAY, 37.0, 12.0)]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1

    def _shot():
        """A hazai befejezi a támadást: a labda a +x kapuba száguld."""
        nonlocal t, frames
        for i in range(1, 8):
            players = [_pl(1, Team.HOME, 33.0, 10.0),
                       _pl(21, Team.AWAY, 37.0, 8.0)]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=33.0 + i, y=10.0,
                                          confidence=1.0)))
            t += 1

    def _away(seconds):
        nonlocal t, frames
        for i in range(int(seconds * fps)):
            x = 18.0 - 0.05 * i
            players = [_pl(1, Team.HOME, 5.0, 10.0),
                       _pl(21, Team.AWAY, x, 10.0),
                       _pl(22, Team.AWAY, x - 3.0, 14.0)]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1

    for kind in kinds:
        _home(3.0)
        if kind == "lövés":
            _shot()
        _away(1.5)
    return Match(_meta(fps), frames)


def test_attack_outcomes_flags_shotless_attacks():
    """Nyolc támadásból három eladással hal el → a támadásaik több mint
    negyede lövés nélkül zárul."""
    from handball.pipeline.attack_types import attack_outcomes

    rec = attack_outcomes(_outcome_match(
        ["lövés"] * 5 + ["eladás"] * 3))["home"]
    assert rec["attacks"] == 8
    assert rec["outcomes"]["lövés"] == 5
    assert rec["outcomes"]["eladás"] == 3
    assert rec["shot_pct"] == 62.5 and rec["turnover_pct"] == 37.5
    assert rec["verdict"] == "lövés nélkül halnak el"


def test_attack_outcomes_flags_finishing_teams():
    """Ha minden támadásuk lövéssel zárul, mindent befejeznek."""
    from handball.pipeline.attack_types import attack_outcomes

    rec = attack_outcomes(_outcome_match(["lövés"] * 8))["home"]
    assert rec["attacks"] == 8 and rec["shot_pct"] == 100.0
    assert rec["verdict"] == "mindent befejeznek"


def test_attack_outcomes_needs_enough_attacks():
    """Kevés (8-nál kevesebb) mért támadásnál nincs ítélet."""
    from handball.pipeline.attack_types import attack_outcomes

    rec = attack_outcomes(_outcome_match(["lövés", "eladás"]))["home"]
    assert rec["attacks"] == 2
    assert rec["shot_pct"] is None and rec["verdict"] is None


# ---- Szélső-bevonás (eljut-e a labda a szélre) -------------------------------

def _wing_match(wings, fps=25.0):
    """HAZAI támadás-sorozat: a `wings` elemenként megadja, kimegy-e a
    labda a szél-sávba az adott támadásban."""
    frames = []
    t = 0

    def _home(to_wing):
        nonlocal t, frames
        for i in range(int(3.0 * fps)):
            # A labda a támadó térfélen; szélezésnél kikerül y=2-re.
            y = 2.0 if (to_wing and i >= 25) else 10.0
            players = [_pl(1, Team.HOME, 26.0, y),
                       _pl(2, Team.HOME, 24.0, 12.0),
                       _pl(9, Team.HOME, 1.5, 10.0, role="kapus"),
                       _pl(21, Team.AWAY, 37.0, 8.0),
                       _pl(22, Team.AWAY, 37.0, 12.0)]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=26.0, y=y, confidence=1.0)))
            t += 1

    def _away():
        nonlocal t, frames
        for i in range(int(1.5 * fps)):
            players = [_pl(1, Team.HOME, 5.0, 10.0),
                       _pl(21, Team.AWAY, 18.0 - 0.05 * i, 10.0),
                       _pl(22, Team.AWAY, 15.0, 14.0)]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=18.0 - 0.05 * i, y=10.0,
                                          confidence=1.0)))
            t += 1

    for to_wing in wings:
        _home(to_wing)
        _away()
    return Match(_meta(fps), frames)


def test_wing_involvement_spots_the_wide_attack():
    """Nyolc támadásból hatban kimegy a labda a szélre → széthúzzák a
    támadást."""
    from handball.pipeline.attack_types import wing_involvement

    rec = wing_involvement(_wing_match([True] * 6 + [False] * 2))["home"]
    assert rec["attacks"] == 8 and rec["with_wing"] == 6
    assert rec["share_pct"] == 75.0
    assert rec["verdict"] == "széthúzzák a támadást"


def test_wing_involvement_spots_the_narrow_attack():
    """Ha a labda alig megy ki a szélre, közép-központúak."""
    from handball.pipeline.attack_types import wing_involvement

    rec = wing_involvement(_wing_match([True] * 2 + [False] * 6))["home"]
    assert rec["share_pct"] == 25.0
    assert rec["verdict"] == "közép-központú"


def test_wing_involvement_needs_enough_attacks():
    """Kevés (8-nál kevesebb) mért támadásnál nincs ítélet."""
    from handball.pipeline.attack_types import wing_involvement

    rec = wing_involvement(_wing_match([True, False]))["home"]
    assert rec["attacks"] == 2
    assert rec["share_pct"] is None and rec["verdict"] is None


# ---- Támadás-mélység (milyen messze állnak a kaputól) ------------------------

def _depth_match(dist_m, fps=25.0, seconds=6.0):
    """HAZAI felállt támadás: a támadók a +x kaputól `dist_m` méterre
    állnak (a labdás középen), a védők a kapu előtt."""
    frames = []
    for i in range(int(seconds * fps)):
        x = 40.0 - dist_m
        players = [_pl(1, Team.HOME, x, 10.0),
                   _pl(2, Team.HOME, x, 6.0),
                   _pl(3, Team.HOME, x, 14.0),
                   _pl(9, Team.HOME, 1.5, 10.0, role="kapus"),
                   _pl(21, Team.AWAY, 38.0, 8.0),
                   _pl(22, Team.AWAY, 38.0, 12.0)]
        frames.append(Frame(t=i, players=players,
                            ball=Ball(x=x, y=10.0, confidence=1.0)))
    return Match(_meta(fps), frames)


def test_attack_depth_flags_the_line_huggers():
    """9 m-en belül álló támadók → vonalra tapadó felállás."""
    from handball.pipeline.attack_types import attack_depth

    rec = attack_depth(_depth_match(8.0))["home"]
    assert rec["frames"] >= 100
    assert rec["avg_depth_m"] is not None and rec["avg_depth_m"] <= 9.5
    assert rec["style"] == "vonalra tapadó"


def test_attack_depth_flags_the_deep_attack():
    """13 m-re hátrahúzódó támadók → mély felállás."""
    from handball.pipeline.attack_types import attack_depth

    rec = attack_depth(_depth_match(13.0))["home"]
    assert rec["avg_depth_m"] >= 12.0
    assert rec["style"] == "mély (hátrahúzódó)"


def test_attack_depth_needs_enough_frames():
    """Kevés mérhető kockánál nincs átlag és nincs ítélet."""
    from handball.pipeline.attack_types import attack_depth

    rec = attack_depth(_depth_match(10.0, seconds=1.0))["home"]
    assert rec["avg_depth_m"] is None and rec["style"] is None


# ---- Beálló-kiszolgálók (ki adja be a labdát a beállónak) --------------------

def _feeder_match(feeders, fps=25.0):
    """HAZAI felállás: az 1-es beálló (6 m, közép), a 2-es és 3-as
    átlövők — a `feeders` elemenként megadja, melyik átlövő adja be a
    labdát a beállónak."""
    spots = {1: (34.0, 10.0), 2: (30.0, 5.0), 3: (30.0, 15.0)}
    frames = []
    t = 0

    def _hold(holder_id, n):
        nonlocal t, frames
        for _ in range(n):
            players = [_pl(tid, Team.HOME, x, y)
                       for tid, (x, y) in spots.items()]
            players.append(_pl(21, Team.AWAY, 38.0, 10.0))
            hx, hy = spots[holder_id]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=hx, y=hy, confidence=1.0)))
            t += 1

    # Poszt-minta a becsléshez; a sorrend végén NEM a beálló birtokol,
    # hogy a bemelegítés ne adjon plusz beadást.
    _hold(1, 100)
    _hold(2, 100)
    _hold(3, 100)
    for pid in feeders:
        _hold(pid, 10)     # a kiszolgáló birtokol
        _hold(1, 10)       # majd a beálló kapja (passz)
    return Match(_meta(fps), frames)


def test_pivot_feeders_finds_the_single_server():
    """Hat beadásból ötöt a 2-es ad → ő a beálló kiszolgálója."""
    from handball.pipeline.attack_types import pivot_feeders

    rec = pivot_feeders(_feeder_match([2, 2, 2, 2, 2, 3]))["home"]
    assert rec["feeds"] == 6
    assert rec["top"] is not None
    assert rec["top"]["player_id"] == 2 and rec["top"]["feeds"] == 5


def test_pivot_feeders_shared_service_has_no_top():
    """Ha két ember fele-fele arányban szolgálja ki a beállót, nincs
    kiemelt kiszolgáló."""
    from handball.pipeline.attack_types import pivot_feeders

    rec = pivot_feeders(_feeder_match([2, 3, 2, 3, 2, 3]))["home"]
    assert rec["feeds"] == 6 and rec["top"] is None


def test_pivot_feeders_needs_enough_feeds():
    """Kevés (4-nél kevesebb) beadásnál nincs ítélet."""
    from handball.pipeline.attack_types import pivot_feeders

    rec = pivot_feeders(_feeder_match([2, 2]))["home"]
    assert rec["feeds"] == 2 and rec["top"] is None


# ---- Beálló-oldal (melyik oldalon áll be a beálló) ---------------------------

def _pivot_side_match(pivot_y, frames_n=300, fps=25.0):
    """HAZAI felállás: az 1-es a beálló (6 m-re a +x kaputól, `pivot_y`
    magasságban), a 2-es és 3-as átlövők — a labda az átlövőnél."""
    frames = []
    for i in range(frames_n):
        players = [_pl(1, Team.HOME, 34.0, pivot_y),
                   _pl(2, Team.HOME, 30.0, 6.0),
                   _pl(3, Team.HOME, 30.0, 14.0),
                   _pl(21, Team.AWAY, 38.0, 10.0)]
        frames.append(Frame(t=i, players=players,
                            ball=Ball(x=30.0, y=6.0, confidence=1.0)))
    return Match(_meta(fps), frames)


def test_pivot_side_finds_the_working_side():
    """A +y oldalon (a támadó bal keze felől) dolgozó beálló → bal
    oldali beállós játék."""
    from handball.pipeline.attack_types import pivot_side

    rec = pivot_side(_pivot_side_match(13.0))["home"]
    assert rec["frames"] >= 100
    assert rec["left"] > rec["right"]
    assert rec["dominant"] == "bal" and rec["share_pct"] == 100.0


def test_pivot_side_center_pivot():
    """A kapu közepén dolgozó beálló → közép."""
    from handball.pipeline.attack_types import pivot_side

    rec = pivot_side(_pivot_side_match(10.0))["home"]
    assert rec["dominant"] == "közép"


def test_pivot_side_needs_enough_frames():
    """Kevés mért kockánál nincs ítélet."""
    from handball.pipeline.attack_types import pivot_side

    # 99 kocka a 100-as küszöb alatt (a poszt-becsléshez elég, az
    # ítélethez nem).
    rec = pivot_side(_pivot_side_match(13.0, frames_n=99))["home"]
    assert rec["dominant"] is None and rec["share_pct"] is None


# ---- Szélső-befejezés oldalanként -------------------------------------------

def _wing_side_match(shots):
    """HAZAI szélső-lövések sorozata: a `shots` elemei (y, gól?) párok —
    y=17 a támadó bal keze felőli oldal, y=3 a másik."""
    frames = []
    t = 0
    for (sy, goal) in shots:
        frames += _wing_or_central_shot(t, 35.0, sy, goal=goal)
        t = frames[-1].t + 1
        for i in range(20):    # szünet a lövés-debounce-hoz
            frames.append(Frame(t=t + i, players=[],
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t = frames[-1].t + 1
    return Match(_meta(), frames)


def test_wing_finishing_by_side_splits_the_two_wings():
    """A bal oldali szélső 3-ból 3-at, a jobb 3-ból 0-t értékesít → a
    bal az erős, a jobb a gyenge oldaluk."""
    from handball.pipeline.attack_types import wing_finishing_by_side

    rec = wing_finishing_by_side(_wing_side_match(
        [(17.0, True)] * 3 + [(3.0, False)] * 3))["home"]
    assert rec["bal"]["shots"] == 3 and rec["bal"]["goal_pct"] == 100.0
    assert rec["jobb"]["shots"] == 3 and rec["jobb"]["goal_pct"] == 0.0
    assert rec["strong"] == "bal" and rec["weak"] == "jobb"


def test_wing_finishing_by_side_needs_shots_on_both_sides():
    """Ha csak az egyik oldalon volt lövés, nincs oldal-ítélet."""
    from handball.pipeline.attack_types import wing_finishing_by_side

    rec = wing_finishing_by_side(_wing_side_match(
        [(17.0, True)] * 4))["home"]
    assert rec["bal"]["shots"] == 4 and rec["jobb"]["shots"] == 0
    assert rec["strong"] is None and rec["weak"] is None


def test_wing_finishing_by_side_similar_sides_have_no_verdict():
    """Ha a két oldal hasonlóan fejez be, nincs kiemelt oldal."""
    from handball.pipeline.attack_types import wing_finishing_by_side

    rec = wing_finishing_by_side(_wing_side_match(
        [(17.0, True)] * 3 + [(3.0, True)] * 3))["home"]
    assert rec["strong"] is None and rec["weak"] is None


# ---- Lövő-távolság profil (ki lő távolról, ki közelről) ----------------------

def _shooter_range_match(shots):
    """HAZAI lövés-sorozat: a `shots` elemei (track_id, lövőhely x)
    párok — a lövő a saját helyéről lő a +x kapura."""
    frames = []
    t = 0
    for (tid, sx) in shots:
        for i in range(3):
            frames.append(Frame(t=t + i,
                                players=[_pl(tid, Team.HOME, sx, 10.0)],
                                ball=Ball(x=sx, y=10.0, confidence=1.0)))
        t += 3
        steps = max(3, int(round(40.5 - sx)))
        for i in range(1, steps + 1):
            frames.append(Frame(
                t=t, players=[_pl(tid, Team.HOME, sx, 10.0)],
                ball=Ball(x=sx + (40.5 - sx) * i / steps, y=10.0,
                          confidence=1.0)))
            t += 1
        for i in range(20):    # szünet a lövés-debounce-hoz
            frames.append(Frame(t=t + i, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
        t += 20
    return Match(_meta(), frames)


def test_shooter_ranges_separates_far_and_close_finishers():
    """A 7-es 12 m-ről, a 9-es 5 m-ről fejez be → távoli lövő és
    közeli befejező."""
    from handball.pipeline.attack_types import shooter_ranges

    rec = shooter_ranges(_shooter_range_match(
        [(7, 28.0)] * 3 + [(9, 35.0)] * 3))["home"]
    assert rec["far"] is not None and rec["far"]["player_id"] == 7
    assert rec["far"]["avg_dist_m"] >= 9.5
    assert rec["close"] is not None and rec["close"]["player_id"] == 9
    assert rec["close"]["avg_dist_m"] <= 7.0


def test_shooter_ranges_needs_enough_shots():
    """Kevés (3-nál kevesebb) lövésnél nincs kiemelt lövő."""
    from handball.pipeline.attack_types import shooter_ranges

    rec = shooter_ranges(_shooter_range_match(
        [(7, 28.0), (9, 35.0)]))["home"]
    assert rec["far"] is None and rec["close"] is None


# ---- Lepattanó-szerzők (ki nyeri a kipattanókat) -----------------------------

def _rebound_match(winners, fps=25.0):
    """HAZAI kimaradt lövések sorozata: a `winners` elemenként megadja,
    melyik játékos (track_id, csapat) szerzi meg a kipattanót."""
    frames = []
    t = 0
    for (tid, team) in winners:
        # Lövés a +x kapura, ami mellé megy (y=5 → nem a kapufák közt).
        for i in range(3):
            frames.append(Frame(
                t=t + i, players=[_pl(1, Team.HOME, 33.0, 10.0)],
                ball=Ball(x=33.0, y=10.0, confidence=1.0)))
        t += 3
        for i in range(9):
            frames.append(Frame(
                t=t, players=[_pl(1, Team.HOME, 33.0, 10.0)],
                ball=Ball(x=min(34.0 + i, 40.0), y=5.0, confidence=1.0)))
            t += 1
        # A kipattanót a megadott játékos szerzi meg.
        for _ in range(int(2.0 * fps)):
            frames.append(Frame(
                t=t, players=[_pl(tid, team, 36.0, 6.0)],
                ball=Ball(x=36.0, y=6.0, confidence=1.0)))
            t += 1
        for i in range(25):    # szünet a lövés-debounce-hoz
            frames.append(Frame(t=t + i, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
        t += 25
    return Match(_meta(fps), frames)


def test_rebound_winners_counts_offensive_and_defensive():
    """Három kipattanót a hazai 5-ös (támadó lepattanó), hármat a
    vendég 21-es (védekező lepattanó) szerez meg."""
    from handball.pipeline.attack_types import rebound_winners

    rec = rebound_winners(_rebound_match(
        [(5, Team.HOME)] * 3 + [(21, Team.AWAY)] * 3))
    home = rec["home"]
    away = rec["away"]
    assert home["top_off"] is not None
    assert home["top_off"]["player_id"] == 5
    assert home["top_off"]["rebounds"] == 3
    assert away["top_def"] is not None
    assert away["top_def"]["player_id"] == 21


def test_rebound_winners_needs_enough_cases():
    """Kevés (3-nál kevesebb) lepattanónál nincs kiemelt szerző."""
    from handball.pipeline.attack_types import rebound_winners

    rec = rebound_winners(_rebound_match([(5, Team.HOME)] * 2))["home"]
    assert rec["off"] and rec["off"][0]["rebounds"] == 2
    assert rec["top_off"] is None


# ---- Kihozatal-oldal (melyik oldalon indítják a támadást) --------------------

def _buildup_match(sides, fps=25.0):
    """HAZAI támadás-sorozat: a `sides` elemenként megadja a támadás
    indító y-magasságát (nagy y = a támadó bal keze felőli oldal)."""
    frames = []
    t = 0
    for y0 in sides:
        for i in range(int(3.0 * fps)):
            x = 24.0 + 0.05 * i
            players = [_pl(1, Team.HOME, x, y0),
                       _pl(2, Team.HOME, x - 2.0, 10.0),
                       _pl(21, Team.AWAY, 37.0, 8.0),
                       _pl(22, Team.AWAY, 37.0, 12.0)]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=x, y=y0, confidence=1.0)))
            t += 1
        for i in range(int(1.5 * fps)):   # vendég-birtoklás: elválasztó
            players = [_pl(1, Team.HOME, 5.0, 10.0),
                       _pl(21, Team.AWAY, 18.0 - 0.05 * i, 10.0)]
            frames.append(Frame(
                t=t, players=players,
                ball=Ball(x=18.0 - 0.05 * i, y=10.0, confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_buildup_side_finds_the_dominant_side():
    """Nyolc támadásból hat a +y (bal) oldalról indul → bal oldali
    kihozatal."""
    from handball.pipeline.attack_types import buildup_side

    rec = buildup_side(_buildup_match([16.0] * 6 + [4.0] * 2))["home"]
    assert rec["attacks"] == 8 and rec["left"] == 6
    assert rec["dominant"] == "bal" and rec["share_pct"] == 75.0


def test_buildup_side_balanced_has_no_verdict():
    """Ha a két oldal és a közép között oszlik, nincs kiemelt oldal."""
    from handball.pipeline.attack_types import buildup_side

    rec = buildup_side(_buildup_match(
        [16.0] * 3 + [4.0] * 3 + [10.0] * 2))["home"]
    assert rec["dominant"] is None and rec["share_pct"] is None


def test_buildup_side_needs_enough_attacks():
    """Kevés (8-nál kevesebb) mért támadásnál nincs ítélet."""
    from handball.pipeline.attack_types import buildup_side

    rec = buildup_side(_buildup_match([16.0] * 4))["home"]
    assert rec["attacks"] == 4 and rec["dominant"] is None
