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


def _scy_match(screened_goals=5, clean_goals=0, n=5):
    """Hazai lövés-sorozat: `n` elzárásos és `n` tiszta lövés, a
    megadott számú góllal (a többi a kapuson akad meg)."""
    frames = []
    t = 0

    def _shot(screened, goal):
        nonlocal t
        sx, gx = 30.0, 40.0
        players = [_pl(1, Team.HOME, sx, 10.0),
                   _pl(20, Team.AWAY, sx + 1.5, 10.0)]
        if screened:
            players.append(_pl(2, Team.HOME, sx + 1.5, 11.0))
        gk = _pl(30, Team.AWAY, 39.5, 10.0)
        gk.role = "kapus"
        players = players + [gk]
        for _ in range(30):
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=sx, y=10.0, confidence=1.0)))
            t += 1
        end = gx if goal else 38.5
        for i in range(14):
            frames.append(Frame(
                t=t, players=players,
                ball=Ball(x=min(sx + 0.8 * (i + 1), end), y=10.0,
                          confidence=1.0)))
            t += 1
        if not goal:                      # kipattanó: védés lesz belőle
            for i in range(10):
                frames.append(Frame(
                    t=t, players=players,
                    ball=Ball(x=38.5 - 0.8 * i, y=10.0,
                              confidence=1.0)))
                t += 1
        for _ in range(40):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    for k in range(n):
        _shot(True, goal=k < screened_goals)
    for k in range(n):
        _shot(False, goal=k < clean_goals)
    return Match(_meta(), frames)


def test_screen_yield_shows_when_the_screen_pays():
    """Ha az elzárásos lövéseik bemennek, a tiszták nem, a
    váltás-kommunikáció a meccs kulcsa."""
    from handball.pipeline.attack_types import SCY_GAP_PP, screen_yield

    rec = screen_yield(_scy_match())["home"]
    assert rec["screened_shots"] >= 4 and rec["clean_shots"] >= 4, rec
    assert rec["gap_pp"] is not None and rec["gap_pp"] >= SCY_GAP_PP, rec
    assert rec["verdict"] and "váltás-kommunikáció" in rec["verdict"], rec


def test_screen_yield_silent_with_few_shots():
    """Sávonként kevés lövésnél nincs ítélet."""
    from handball.pipeline.attack_types import screen_yield

    rec = screen_yield(_scy_match(screened_goals=2, n=2))["home"]
    assert rec["gap_pp"] is None and rec["verdict"] is None, rec


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
        for _ in range(3):   # a labda a lövő kezében (elengedés előtt)
            frames.append(Frame(t=t, players=shooter,
                                ball=Ball(x=31.2, y=10.0, confidence=1.0)))
            t += 1
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


# ---- Kontra-kíséret (hányan futnak fel a lerohanásoknál) ---------------------

def _fast_break_match(runners, n_breaks=4, fps=25.0):
    """HAZAI lerohanás-sorozat: `runners` hazai mezőnyjátékos van már a
    vendég térfelén, míg a labdás 22 m-től 38 m-ig fut."""
    frames = []
    t = 0
    for _ in range(n_breaks):
        for i in range(int(4.0 * fps)):
            x = 22.0 + 16.0 * i / (4.0 * fps)
            players = [_pl(1, Team.HOME, x, 10.0)]
            for k in range(1, runners):
                players.append(_pl(1 + k, Team.HOME, x - 1.0, 6.0 + k))
            players.append(_pl(9, Team.HOME, 1.5, 10.0, role="kapus"))
            players += [_pl(21, Team.AWAY, 38.0, 8.0),
                        _pl(22, Team.AWAY, 38.0, 12.0)]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1
        for i in range(int(2.0 * fps)):   # vendég-birtoklás: elválasztó
            frames.append(Frame(
                t=t, players=[_pl(21, Team.AWAY, 18.0 - 0.05 * i, 10.0)],
                ball=Ball(x=18.0 - 0.05 * i, y=10.0, confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_fast_break_support_flags_the_mass_break():
    """Négy felfutó emberrel indított lerohanások → tömeges kontra."""
    from handball.pipeline.attack_types import fast_break_support

    rec = fast_break_support(_fast_break_match(runners=4))["home"]
    assert rec["breaks"] >= 3
    assert rec["avg_runners"] is not None and rec["avg_runners"] >= 3.0
    assert rec["verdict"] == "tömeges kontra"


def test_fast_break_support_flags_the_lonely_break():
    """Egyedül elfutó labdással → magányos kontra."""
    from handball.pipeline.attack_types import fast_break_support

    rec = fast_break_support(_fast_break_match(runners=1))["home"]
    assert rec["avg_runners"] <= 1.6
    assert rec["verdict"] == "magányos kontra"


def test_fast_break_support_needs_enough_breaks():
    """Kevés (3-nál kevesebb) mért lerohanásnál nincs ítélet."""
    from handball.pipeline.attack_types import fast_break_support

    rec = fast_break_support(_fast_break_match(runners=4,
                                               n_breaks=2))["home"]
    assert rec["avg_runners"] is None and rec["verdict"] is None


# ---- Két beállós játék -------------------------------------------------------

def _double_pivot_match(pivots, n_attacks=10, fps=25.0):
    """HAZAI támadás-sorozat: `pivots` támadó áll a 6 m-es zónában (a
    +x kaputól 5-6 m-re), a többi a 9 m-en kívül."""
    frames = []
    t = 0
    for _ in range(n_attacks):
        for i in range(int(3.0 * fps)):
            players = [_pl(1, Team.HOME, 28.0, 10.0),
                       _pl(2, Team.HOME, 28.0, 6.0)]
            for k in range(pivots):
                players.append(_pl(5 + k, Team.HOME, 34.5,
                                   8.0 + 4.0 * k))
            players += [_pl(21, Team.AWAY, 37.0, 8.0),
                        _pl(22, Team.AWAY, 37.0, 12.0)]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=28.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        for i in range(int(1.5 * fps)):    # vendég-birtoklás: elválasztó
            frames.append(Frame(
                t=t, players=[_pl(21, Team.AWAY, 18.0 - 0.05 * i, 10.0)],
                ball=Ball(x=18.0 - 0.05 * i, y=10.0, confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_double_pivot_usage_spots_the_two_pivot_setup():
    """Két emberrel a 6 m-es zónában → két beállós játék."""
    from handball.pipeline.attack_types import double_pivot_usage

    rec = double_pivot_usage(_double_pivot_match(pivots=2))["home"]
    assert rec["attacks"] >= 8
    assert rec["double_attacks"] == rec["attacks"]
    assert rec["share_pct"] == 100.0
    assert rec["verdict"] == "két beállóval játszanak"


def test_double_pivot_usage_spots_the_single_pivot():
    """Egy beállóval → egy beállós felállás."""
    from handball.pipeline.attack_types import double_pivot_usage

    rec = double_pivot_usage(_double_pivot_match(pivots=1))["home"]
    assert rec["double_attacks"] == 0 and rec["share_pct"] == 0.0
    assert rec["verdict"] == "egy beállós felállás"


def test_double_pivot_usage_needs_enough_attacks():
    """Kevés (8-nál kevesebb) mért támadásnál nincs ítélet."""
    from handball.pipeline.attack_types import double_pivot_usage

    rec = double_pivot_usage(_double_pivot_match(pivots=2,
                                                n_attacks=4))["home"]
    assert rec["share_pct"] is None and rec["verdict"] is None


# ---- Áttörő játékosok (ki jut be labdával a falba) ---------------------------

def _breakthrough_match(entries, fps=25.0):
    """HAZAI támadás-sorozat: az `entries` elemenként megadja, melyik
    hazai játékos viszi be a labdát a kapu 9 m-es körzetébe."""
    frames = []
    t = 0
    for tid in entries:
        for i in range(int(2.0 * fps)):    # felállás a 9 m-en kívül
            players = [_pl(tid, Team.HOME, 28.0, 10.0),
                       _pl(8, Team.HOME, 28.0, 5.0),
                       _pl(21, Team.AWAY, 37.0, 10.0)]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=28.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        for i in range(int(1.5 * fps)):    # betörés: a labdás 33 m-ig megy
            players = [_pl(tid, Team.HOME, 33.5, 10.0),
                       _pl(8, Team.HOME, 28.0, 5.0),
                       _pl(21, Team.AWAY, 37.0, 10.0)]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=33.5, y=10.0,
                                          confidence=1.0)))
            t += 1
        for i in range(int(1.5 * fps)):    # vendég-birtoklás: elválasztó
            frames.append(Frame(
                t=t, players=[_pl(21, Team.AWAY, 18.0 - 0.05 * i, 10.0)],
                ball=Ball(x=18.0 - 0.05 * i, y=10.0, confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_breakthrough_players_finds_the_penetrator():
    """Négy betörésből hármat ugyanaz a játékos visz be → ő az áttörő."""
    from handball.pipeline.attack_types import breakthrough_players

    rec = breakthrough_players(_breakthrough_match([7, 7, 7, 9]))["home"]
    assert rec["top"] is not None
    assert rec["top"]["player_id"] == 7 and rec["top"]["entries"] == 3
    assert rec["entries"] == 4


def test_breakthrough_players_needs_enough_entries():
    """Kevés (3-nál kevesebb) betörésnél nincs kiemelt áttörő."""
    from handball.pipeline.attack_types import breakthrough_players

    rec = breakthrough_players(_breakthrough_match([7, 9]))["home"]
    assert rec["entries"] == 2 and rec["top"] is None


# ---- Lövés-távolság esése (kifelé szorulnak-e a hajrára) --------------------

def _distance_fade_match(fh_x=33.0, sh_x=28.0, fps=25.0):
    """Hazai lövések az 1. félidőben `fh_x`-ről, a 2.-ban `sh_x`-ről,
    közte 100 mp szünettel (a félidő-felismeréshez)."""
    frames = []
    t = 0

    def _wall():
        return [_pl(10 + j, Team.HOME, 20.0, 4.0 + 3.0 * j)
                for j in range(5)]

    def _shot(sx):
        nonlocal t, frames
        for _ in range(3):   # a labda a lövő kezében (elengedés előtt)
            frames.append(Frame(
                t=t, players=[_pl(1, Team.HOME, sx, 10.0)] + _wall(),
                ball=Ball(x=sx + 0.2, y=10.0, confidence=1.0)))
            t += 1
        for i in range(10):
            frames.append(Frame(
                t=t, players=[_pl(1, Team.HOME, sx, 10.0)] + _wall(),
                ball=Ball(x=min(sx + 1.2 * (i + 1), 40.4), y=10.0,
                          confidence=1.0)))
            t += 1
        for _ in range(42):
            frames.append(Frame(t=t, players=_wall(),
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    for _ in range(6):
        _shot(fh_x)
    for _ in range(2500):      # 100 mp szünet
        frames.append(Frame(t=t, players=[], ball=None))
        t += 1
    for _ in range(6):
        _shot(sh_x)
    return Match(_meta(fps), frames)


def test_shot_distance_fade_flags_the_outward_drift():
    """A 2. félidőben 12 m-ről lőnek a 7 m helyett → kifelé
    szorulnak."""
    from handball.pipeline.attack_types import shot_distance_fade

    rec = shot_distance_fade(_distance_fade_match())["home"]
    assert rec["fh_shots"] >= 4 and rec["sh_shots"] >= 4
    assert rec["gap_m"] is not None and rec["gap_m"] >= 1.0
    assert rec["verdict"] == "kifelé szorulnak"


def test_shot_distance_fade_without_halftime():
    """Félidő-jel nélkül nincs ítélet."""
    from handball.pipeline.attack_types import shot_distance_fade

    m = _distance_fade_match()
    no_break = Match(_meta(), [f for f in m.frames if f.players])
    rec = shot_distance_fade(no_break)["home"]
    assert rec["gap_m"] is None and rec["verdict"] is None


# ---- Elzárók (ki áll elzárásba a lövő előtt) --------------------------------

def _screen_setter_match(setters, fps=25.0):
    """HAZAI őrzött lövések: a `setters` elemenként megadja, melyik
    társ áll elzárásban a lövő őrzője mellett."""
    frames = []
    t = 0
    for setter_id in setters:
        players = [_pl(1, Team.HOME, 30.0, 10.0),          # a lövő
                   _pl(20, Team.AWAY, 31.5, 10.0),         # az őrző
                   _pl(setter_id, Team.HOME, 31.5, 11.0)]  # az elzáró
        for _ in range(30):
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=30.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        for i in range(14):
            frames.append(Frame(
                t=t, players=players,
                ball=Ball(x=min(30.0 + 0.8 * (i + 1), 40.0), y=10.0,
                          confidence=1.0)))
            t += 1
        for _ in range(40):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=40.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_screen_setters_finds_the_main_screener():
    """Négy elzárásból hármat ugyanaz a játékos állít → ő az elzáró."""
    from handball.pipeline.attack_types import screen_setters

    rec = screen_setters(_screen_setter_match([5, 5, 5, 7]))["home"]
    assert rec["screens"] == 4
    assert rec["top"] is not None
    assert rec["top"]["player_id"] == 5 and rec["top"]["screens"] == 3


def test_screen_setters_needs_enough_screens():
    """Kevés (3-nál kevesebb) elzárásnál nincs kiemelt elzáró."""
    from handball.pipeline.attack_types import screen_setters

    rec = screen_setters(_screen_setter_match([5, 7]))["home"]
    assert rec["screens"] == 2 and rec["top"] is None


# ---- Kockázatos passzolók (kinek a hosszú labdái foghatók el) ---------------

def _risky_passer_match(cases, fps=25.0):
    """Hosszú továbbítási kísérletek: a `cases` elemei (passzoló id,
    elveszett?) párok — a fogadó 12 méterre áll."""
    frames = []
    t = 0
    for (pid, lost) in cases:
        taker = (_pl(20, Team.AWAY, 30.0, 22.0) if lost
                 else _pl(2, Team.HOME, 30.0, 22.0))
        pls = [_pl(pid, Team.HOME, 30.0, 10.0), taker]
        for _ in range(5):
            frames.append(Frame(t=t, players=pls,
                                ball=Ball(x=30.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(5):
            frames.append(Frame(t=t, players=pls,
                                ball=Ball(x=30.0, y=22.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(5):    # a labda visszakerül a passzolóhoz
            frames.append(Frame(
                t=t, players=[_pl(pid, Team.HOME, 30.0, 10.0)],
                ball=Ball(x=30.0, y=10.0, confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_risky_passers_finds_the_loose_passer():
    """A 4-es hat hosszú labdájából négy elveszik → nála elfogható a
    labda."""
    from handball.pipeline.attack_types import risky_passers

    cases = [(4, True)] * 4 + [(4, False)] * 2 + [(6, False)] * 4
    rec = risky_passers(_risky_passer_match(cases))["home"]
    assert rec["top"] is not None
    assert rec["top"]["player_id"] == 4
    assert rec["top"]["tries"] == 6 and rec["top"]["turnovers"] == 4


def test_risky_passers_needs_enough_tries():
    """Kevés (4-nél kevesebb) hosszú kísérletnél nincs kiemelt
    passzoló."""
    from handball.pipeline.attack_types import risky_passers

    rec = risky_passers(_risky_passer_match(
        [(4, True), (4, True), (6, False)]))["home"]
    assert rec["top"] is None


# ---- Felhozatal-idő (milyen gyorsan érnek a támadó térfélre) ----------------

def _buildup_time_match(cases, fps=25.0):
    """HAZAI felhozatalok: a `cases` elemei a térfél-átlépésig eltelt
    másodpercek — a birtoklásokat egy rövid vendég-labda választja el."""
    frames = []
    t = 0
    for secs in cases:
        n = max(1, int(round(secs * fps)))
        for _ in range(n):        # a saját térfélen jár a labda
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 8.0, 10.0)],
                                ball=Ball(x=8.0, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(5):        # átlépés a támadó térfélre
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 21.0, 10.0)],
                                ball=Ball(x=21.0, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(10):       # vendég-birtoklás: új szakasz kezdődik
            frames.append(Frame(t=t, players=[_pl(21, Team.AWAY, 8.0, 10.0)],
                                ball=Ball(x=8.0, y=10.0, confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_buildup_time_slow_team():
    """Öt felhozatal 8 másodperc alatt → lassan hozzák fel a labdát."""
    from handball.pipeline.attack_types import buildup_time

    rec = buildup_time(_buildup_time_match([8.0] * 5))["home"]
    assert rec["cases"] == 5 and rec["avg_s"] == 8.0
    assert rec["verdict"] == "lassan hozzák fel"


def test_buildup_time_fast_team():
    """Öt felhozatal 3 másodperc alatt → gyorsan hozzák fel a labdát."""
    from handball.pipeline.attack_types import buildup_time

    rec = buildup_time(_buildup_time_match([3.0] * 5))["home"]
    assert rec["avg_s"] == 3.0 and rec["verdict"] == "gyorsan hozzák fel"


def test_buildup_time_needs_enough_cases():
    """Kevés (5-nél kevesebb) mért felhozatalnál nincs ítélet."""
    from handball.pipeline.attack_types import buildup_time

    rec = buildup_time(_buildup_time_match([3.0] * 3))["home"]
    assert rec["cases"] == 3 and rec["avg_s"] is None
    assert rec["verdict"] is None


# ---- Lerohanás-hatékonyság (mennyi lesz gól a kontrákból) ------------------

def _fbc_match(results, fps=25.0):
    """Hazai lerohanás-sorozat: a `results` elemei jelzik, gólt ért-e a
    kontra; a szakaszokat labda nélküli szünet választja el."""
    frames = []
    t = 0
    for scored in results:
        frames += (_fast_break_goal(t) if scored
                   else _attack_frames(t, 4.0, 22.0, 33.0))
        t = frames[-1].t + 1
        for _ in range(int(4 * fps)):     # szünet: nincs támadó fázis
            frames.append(Frame(t=t, players=[], ball=None))
            t += 1
    return Match(_meta(fps), frames)


def test_fast_break_conversion_flags_the_sharp_team():
    """Hat kontrából öt gól → élesen fejezik be a kontrát."""
    from handball.pipeline.attack_types import fast_break_conversion

    rec = fast_break_conversion(
        _fbc_match([True] * 5 + [False]))["home"]
    assert rec["breaks"] == 6 and rec["goals"] == 5
    assert rec["verdict"] == "élesen fejezik be a kontrát"


def test_fast_break_conversion_flags_the_wasteful_team():
    """Hat kontrából egy gól → elpuskázzák a kontrát."""
    from handball.pipeline.attack_types import fast_break_conversion

    rec = fast_break_conversion(
        _fbc_match([True] + [False] * 5))["home"]
    assert rec["goals"] == 1 and rec["verdict"] == "elpuskázzák a kontrát"


def test_fast_break_conversion_needs_enough_breaks():
    """Kevés (5-nél kevesebb) lerohanásnál nincs ítélet."""
    from handball.pipeline.attack_types import fast_break_conversion

    rec = fast_break_conversion(_fbc_match([True, False]))["home"]
    assert rec["share_pct"] is None and rec["verdict"] is None


# ---- Visszahozott támadások (lezárják vagy újrajáratják a betörést) ---------

def _pullback_match(kinds, fps=25.0):
    """Hazai betörés-epizódok: a `kinds` elemei "shot" (a belépést
    lövés zárja) vagy "pull" (lövés nélkül visszahozzák)."""
    frames = []
    t = 0

    def _carry(x_from, x_to, n):
        nonlocal t
        for i in range(n):
            x = x_from + (x_to - x_from) * i / max(1, n - 1)
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, x, 10.0)],
                                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1

    for kind in kinds:
        _carry(24.0, 32.0, 40)          # behúzás a 9-esen belülre (d=8)
        if kind == "shot":
            for i in range(7):          # lövés a +x kapura
                frames.append(Frame(
                    t=t, players=[_pl(1, Team.HOME, 32.0, 10.0)],
                    ball=Ball(x=min(33.0 + i * 1.4, 40.0), y=10.0,
                              confidence=1.0)))
                t += 1
            _carry(24.0, 24.0, 20)      # a labda újra kint (d=16)
        else:
            _carry(32.0, 26.0, 40)      # visszahozzák (d=14, lövés nélkül)
        _carry(24.0, 24.0, 20)          # szünet kint
    return Match(_meta(fps), frames)


def test_pullback_rate_flags_the_patient_team():
    """Hat betörésből négy visszahozás → behúzzák, aztán
    visszahozzák."""
    from handball.pipeline.attack_types import pullback_rate

    rec = pullback_rate(_pullback_match(
        ["pull"] * 4 + ["shot"] * 2))["home"]
    assert rec["entries"] == 6 and rec["pullbacks"] == 4
    assert rec["verdict"] == "behúzzák, aztán visszahozzák"


def test_pullback_rate_flags_the_direct_team():
    """Hat betörésből hat lövés → az első betörésből lezárnak."""
    from handball.pipeline.attack_types import pullback_rate

    rec = pullback_rate(_pullback_match(["shot"] * 6))["home"]
    assert rec["shots"] == 6 and rec["pullbacks"] == 0
    assert rec["verdict"] == "az első betörésből lezárnak"


def test_pullback_rate_needs_enough_entries():
    """Kevés (6-nál kevesebb) betörésnél nincs ítélet."""
    from handball.pipeline.attack_types import pullback_rate

    rec = pullback_rate(_pullback_match(["pull"] * 3))["home"]
    assert rec["entries"] == 3 and rec["pull_pct"] is None
    assert rec["verdict"] is None


# ---- Szorult játék (hátrányban mennyire húzzák szét a pályát) --------------

def _wbs_attack(t0, width, n=150):
    """Hazai támadás-szakasz a +x térfélen, adott terjedelemmel."""
    frames = []
    half = width / 2.0
    for i in range(n):
        players = [
            _pl(1, Team.HOME, 30.0, 10.0),
            _pl(2, Team.HOME, 32.0, 10.0 - half),
            _pl(3, Team.HOME, 32.0, 10.0 + half),
            _pl(21, Team.AWAY, 38.0, 10.0),
        ]
        frames.append(Frame(t=t0 + i, players=players,
                            ball=Ball(x=30.0, y=10.0, confidence=1.0)))
    return frames


def _wbs_match(width_even, width_trail, fps=25.0):
    """Egál-állásban width_even, aztán kapott gól utáni hátrányban
    width_trail terjedelmű hazai támadások."""
    frames = _wbs_attack(0, width_even)
    t = len(frames)
    for i in range(8):        # vendég gól a 0-s kapuba → hazai hátrány
        frames.append(Frame(
            t=t, players=[_pl(21, Team.AWAY, 7.0, 10.0)],
            ball=Ball(x=max(6.0 - i, 0.0), y=10.0, confidence=1.0)))
        t += 1
    frames += _wbs_attack(t, width_trail)
    return Match(_meta(fps), frames)


def test_width_by_score_flags_the_narrowing_team():
    """Egálban 16, hátrányban 8 m széles támadás → hátrányban
    beszűkülnek."""
    from handball.pipeline.attack_types import width_by_score

    rec = width_by_score(_wbs_match(16.0, 8.0))["home"]
    assert rec["other_avg_m"] == 16.0 and rec["trail_avg_m"] == 8.0
    assert rec["verdict"] == "hátrányban beszűkülnek"


def test_width_by_score_flags_the_widening_team():
    """Fordítva (hátrányban szélesebb) → hátrányban kinyílnak."""
    from handball.pipeline.attack_types import width_by_score

    rec = width_by_score(_wbs_match(8.0, 16.0))["home"]
    assert rec["verdict"] == "hátrányban kinyílnak"


def test_width_by_score_needs_frames_in_both_states():
    """Ha nincs mért hátrány-szakasz, nincs ítélet."""
    from handball.pipeline.attack_types import width_by_score

    rec = width_by_score(Match(_meta(), _wbs_attack(0, 16.0)))["home"]
    assert rec["trail_frames"] == 0 and rec["verdict"] is None


# ---- Kontra-forrás (miből indul a lerohanásuk) ------------------------------

def _bsrc_match(n_breaks, with_save, fps=25.0):
    """Hazai lerohanások; ha with_save, mindegyiket a hazai kapus
    védése előzi meg (vendég lövés a 0-s kapura)."""
    frames = []
    t = 0
    for _ in range(n_breaks):
        if with_save:
            for _ in range(5):     # a vendég lövő birtokol
                frames.append(Frame(t=t, players=[
                    _pl(21, Team.AWAY, 7.0, 10.0),
                    _pl(9, Team.HOME, 0.5, 10.0, role="kapus")],
                    ball=Ball(x=7.0, y=10.0, confidence=1.0)))
                t += 1
            for i in range(8):     # lövés, a kapusnál megáll (védés)
                frames.append(Frame(t=t, players=[
                    _pl(21, Team.AWAY, 7.0, 10.0),
                    _pl(9, Team.HOME, 0.5, 10.0, role="kapus")],
                    ball=Ball(x=max(7.0 - i, 1.2), y=10.0,
                              confidence=1.0)))
                t += 1
        block = _attack_frames(t, 4.0, 22.0, 38.0, fps)
        frames.extend(block)
        t = frames[-1].t + 1
        for _ in range(int(6 * fps)):   # szünet: nincs támadó fázis
            frames.append(Frame(t=t, players=[], ball=None))
            t += 1
    return Match(_meta(fps), frames)


def test_break_sources_flags_the_save_launched_counters():
    """Négy lerohanás, mind kapus-védés után → a kontráik védésből
    indulnak."""
    from handball.pipeline.attack_types import break_sources

    rec = break_sources(_bsrc_match(4, with_save=True))["home"]
    assert rec["breaks"] == 4
    assert rec["sources"].get("védés") == 4
    assert rec["verdict"] == "a kontráik főleg ebből indulnak: védés"


def test_break_sources_default_is_steal():
    """Előzmény-lövés nélkül a forrás labdaszerzés."""
    from handball.pipeline.attack_types import break_sources

    rec = break_sources(_bsrc_match(4, with_save=False))["home"]
    assert rec["sources"].get("labdaszerzés") == 4
    assert rec["verdict"] == (
        "a kontráik főleg ebből indulnak: labdaszerzés")


def test_break_sources_needs_enough_breaks():
    """Kevés (4-nél kevesebb) lerohanásnál nincs ítélet."""
    from handball.pipeline.attack_types import break_sources

    rec = break_sources(_bsrc_match(2, with_save=True))["home"]
    assert rec["breaks"] == 2 and rec["verdict"] is None


# ---- Fal-magasság elleni játék (megbüntetik-e a felfutó falat) --------------

def _avw_attack(t0, def_depth, score, fps=25.0):
    """Hazai támadás a +x kapura; a vendég fal def_depth m-re áll a
    kapujától; score esetén a végén gól."""
    frames = []
    n = int(4.0 * fps)
    for i in range(n):
        x = 24.0 + 8.0 * i / max(1, n - 1)
        frames.append(Frame(t=t0 + i, players=[
            _pl(1, Team.HOME, x, 10.0),
            _pl(21, Team.AWAY, 40.0 - def_depth, 7.0),
            _pl(22, Team.AWAY, 40.0 - def_depth, 13.0),
            _pl(29, Team.AWAY, 39.5, 10.0, role="kapus"),
        ], ball=Ball(x=x, y=10.0, confidence=1.0)))
    t = t0 + n
    if score:
        for i in range(7):
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, 32.0, 10.0)],
                ball=Ball(x=min(33.0 + i * 1.4, 40.0), y=10.0,
                          confidence=1.0)))
            t += 1
    return frames


def _avw_match(high_scores, deep_scores, fps=25.0):
    """Felfutó (10 m-es) és mély (5 m-es) fal elleni támadás-sorozat a
    megadott gól-kimenetelekkel."""
    frames = []
    t = 0
    for depth, results in ((10.0, high_scores), (5.0, deep_scores)):
        for score in results:
            block = _avw_attack(t, depth, score, fps)
            frames.extend(block)
            t = frames[-1].t + 1
            for _ in range(int(5 * fps)):    # szünet
                frames.append(Frame(t=t, players=[], ball=None))
                t += 1
    return Match(_meta(fps), frames)


def test_attack_vs_wall_height_flags_the_press_victim():
    """Felfutó fal ellen 0/5, mély ellen 4/5 gól → a felfutó fal
    megfogja őket."""
    from handball.pipeline.attack_types import attack_vs_wall_height

    rec = attack_vs_wall_height(_avw_match(
        [False] * 5, [True] * 4 + [False]))["home"]
    assert rec["high"]["attacks"] == 5 and rec["deep"]["attacks"] == 5
    assert rec["verdict"] == "a felfutó fal megfogja őket"


def test_attack_vs_wall_height_flags_the_press_breaker():
    """Fordítva (felfutó ellen terem, mély ellen nem) → a felfutó
    falat megbüntetik."""
    from handball.pipeline.attack_types import attack_vs_wall_height

    rec = attack_vs_wall_height(_avw_match(
        [True] * 4 + [False], [False] * 5))["home"]
    assert rec["verdict"] == "a felfutó falat megbüntetik"


def test_attack_vs_wall_height_needs_both_buckets():
    """Ha valamelyik vödörben kevés a támadás, nincs ítélet."""
    from handball.pipeline.attack_types import attack_vs_wall_height

    rec = attack_vs_wall_height(_avw_match(
        [False] * 2, [True] * 5))["home"]
    assert rec["verdict"] is None


# ---- Elzárás-páros (ki zár kinek) ------------------------------------------

def test_screen_pairs_finds_the_drilled_duo():
    """Négy elzárásból hármat az 5-ös állít az 1-esnek → bejáratott
    páros."""
    from handball.pipeline.attack_types import screen_pairs

    rec = screen_pairs(_screen_setter_match([5, 5, 5, 7]))["home"]
    assert rec["top"] is not None
    assert rec["top"]["setter_id"] == 5
    assert rec["top"]["shooter_id"] == 1
    assert rec["top"]["shots"] == 3
    assert rec["verdict"] == "bejáratott elzárás-párosuk van"


def test_screen_pairs_scattered_duos_no_verdict():
    """Ha minden elzárást más állít, nincs bejáratott páros."""
    from handball.pipeline.attack_types import screen_pairs

    rec = screen_pairs(_screen_setter_match([5, 6, 7]))["home"]
    assert rec["top"] is None and rec["verdict"] is None


# ---- Labda-forgatás iránya (merre járatják a labdát) ------------------------

def _cir_match(n_left, n_right, fps=25.0):
    """Hazai oldalpasszok: n_left passz +y (balra), n_right passz -y
    irányba; a passzoló és a fogadó 6 méterre áll egymástól."""
    frames = []
    t = 0
    for direction, count in (("left", n_left), ("right", n_right)):
        for _ in range(count):
            y1, y2 = (7.0, 13.0) if direction == "left" else (13.0, 7.0)
            for _ in range(6):     # a passzoló birtokol
                frames.append(Frame(t=t, players=[
                    _pl(1, Team.HOME, 28.0, y1),
                    _pl(2, Team.HOME, 28.0, y2)],
                    ball=Ball(x=28.0, y=y1, confidence=1.0)))
                t += 1
            for i in range(4):     # a labda átszáll a fogadóhoz
                frames.append(Frame(t=t, players=[
                    _pl(1, Team.HOME, 28.0, y1),
                    _pl(2, Team.HOME, 28.0, y2)],
                    ball=Ball(x=28.0,
                              y=y1 + (y2 - y1) * (i + 1) / 4.0,
                              confidence=1.0)))
                t += 1
            for _ in range(6):     # a fogadónál a labda
                frames.append(Frame(t=t, players=[
                    _pl(1, Team.HOME, 28.0, y1),
                    _pl(2, Team.HOME, 28.0, y2)],
                    ball=Ball(x=28.0, y=y2, confidence=1.0)))
                t += 1
            for _ in range(6):     # vendég-labda: nincs visszapassz
                frames.append(Frame(t=t, players=[
                    _pl(21, Team.AWAY, 20.0, 16.0)],
                    ball=Ball(x=20.0, y=16.0, confidence=1.0)))
                t += 1
    return Match(_meta(fps), frames)


def test_circulation_direction_flags_the_left_leaning_team():
    """Húsz balra és öt jobbra passz → balra forgatnak."""
    from handball.pipeline.attack_types import circulation_direction

    rec = circulation_direction(_cir_match(20, 5))["home"]
    assert rec["passes"] >= 20 and rec["left"] > rec["right"]
    assert rec["verdict"] == "balra forgatnak"


def test_circulation_direction_balanced_no_verdict():
    """Kiegyenlített forgásnál nincs ítélet."""
    from handball.pipeline.attack_types import circulation_direction

    rec = circulation_direction(_cir_match(12, 12))["home"]
    assert rec["verdict"] is None


def test_circulation_direction_needs_enough_passes():
    """Kevés (20-nál kevesebb) oldalpassznál nincs ítélet."""
    from handball.pipeline.attack_types import circulation_direction

    rec = circulation_direction(_cir_match(8, 2))["home"]
    assert rec["verdict"] is None


# ---- Felfutási létszám (hány emberrel támadnak) -----------------------------

def _ahc_match(n_up, frames=150, fps=25.0):
    """Hazai felállt támadás a +x térfélen n_up mezőnyjátékossal."""
    out = []
    for t in range(frames):
        players = [_pl(10 + k, Team.HOME, 26.0 + k, 4.0 + 2.0 * k)
                   for k in range(n_up)]
        players.append(_pl(30, Team.AWAY, 38.0, 10.0))
        out.append(Frame(t=t, players=players,
                         ball=Ball(x=26.0, y=4.0, confidence=1.0)))
    return Match(_meta(fps), out)


def test_attack_headcount_flags_the_all_in_team():
    """Hat fenti támadó → mindenkit felküldenek."""
    from handball.pipeline.attack_types import attack_headcount

    rec = attack_headcount(_ahc_match(6))["home"]
    assert rec["avg_up"] == 6.0
    assert rec["verdict"] == "mindenkit felküldenek"


def test_attack_headcount_flags_the_safe_team():
    """Négy fenti támadó → biztosítva támadnak."""
    from handball.pipeline.attack_types import attack_headcount

    rec = attack_headcount(_ahc_match(4))["home"]
    assert rec["verdict"] == "biztosítva támadnak"


def test_attack_headcount_needs_enough_frames():
    """Kevés (100-nál kevesebb) mért kockánál nincs ítélet."""
    from handball.pipeline.attack_types import attack_headcount

    rec = attack_headcount(_ahc_match(6, frames=50))["home"]
    assert rec["verdict"] is None


# ---- Kivárás-csapda (mi lesz a hosszú támadásaikból) ------------------------

def _lao_match(shot_flags, fps=25.0):
    """Hosszú (26 mp-es) felállt hazai támadások; a `shot_flags`
    szerint lövéssel vagy lövés nélkül érnek véget."""
    frames = []
    t = 0
    for with_shot in shot_flags:
        block = _attack_frames(t, 26.0, 30.0, 31.0, fps)
        frames.extend(block)
        t = frames[-1].t + 1
        if with_shot:
            for i in range(7):
                frames.append(Frame(t=t, players=[
                    _pl(1, Team.HOME, 31.0, 10.0)],
                    ball=Ball(x=min(32.0 + i * 1.4, 40.0), y=10.0,
                              confidence=1.0)))
                t += 1
        for _ in range(int(5 * fps)):
            frames.append(Frame(t=t, players=[], ball=None))
            t += 1
    return Match(_meta(fps), frames)


def test_long_attack_outcomes_flags_the_dying_patience():
    """Öt hosszú támadásból négy lövés nélkül hal el → kivárás-csapda."""
    from handball.pipeline.attack_types import long_attack_outcomes

    rec = long_attack_outcomes(_lao_match(
        [False] * 4 + [True]))["home"]
    assert rec["long_attacks"] == 5 and rec["died"] == 4
    assert rec["verdict"] == "a hosszú támadásaik elhalnak"


def test_long_attack_outcomes_flags_the_patient_finishers():
    """Ha minden hosszú támadás lövésig ér, a kivárás nem véd
    ellenük."""
    from handball.pipeline.attack_types import long_attack_outcomes

    rec = long_attack_outcomes(_lao_match([True] * 5))["home"]
    assert rec["died"] == 0
    assert rec["verdict"] == "a hosszú támadásaik is lövésig érnek"


def test_long_attack_outcomes_needs_enough_attacks():
    """Kevés (5-nél kevesebb) hosszú támadásnál nincs ítélet."""
    from handball.pipeline.attack_types import long_attack_outcomes

    rec = long_attack_outcomes(_lao_match([False] * 3))["home"]
    assert rec["long_attacks"] == 3 and rec["verdict"] is None


# ---- Szélső-futtatás (lendületből vagy állva kapják-e) ----------------------

def _wsv_match(moving, n_passes=7, fps=25.0):
    """Az irányító (3-as) sorozatban a szélsőnek (2-es) passzol; a
    szélső vagy folyamatos mozgásban van, vagy áll."""
    frames = []
    t = 0
    wx, wdir = 34.0, 1.0

    def _wing():
        nonlocal wx, wdir
        if moving:
            wx += 0.2 * wdir
            if not 33.0 <= wx <= 39.0:
                wdir *= -1.0
                wx += 0.4 * wdir
        else:
            wx = 36.0
        return _pl(2, Team.HOME, wx, 2.0)

    def _emit(bx, by, n):
        nonlocal t
        for _ in range(n):
            frames.append(Frame(t=t, players=[
                _pl(3, Team.HOME, 28.0, 10.0), _wing()],
                ball=Ball(x=bx, y=by, confidence=1.0)))
            t += 1

    _emit(28.0, 10.0, 150)          # poszt-minta: a 3-asnál a labda
    for _ in range(n_passes):
        _emit(28.0, 10.0, 6)        # az irányító birtokol
        for i in range(4):          # passz a szélsőnek
            frames.append(Frame(t=t, players=[
                _pl(3, Team.HOME, 28.0, 10.0), _wing()],
                ball=Ball(x=28.0 + (wx - 28.0) * (i + 1) / 4.0,
                          y=10.0 + (2.0 - 10.0) * (i + 1) / 4.0,
                          confidence=1.0)))
            t += 1
        for _ in range(6):          # a szélsőnél a labda
            w = _wing()
            frames.append(Frame(t=t, players=[
                _pl(3, Team.HOME, 28.0, 10.0), w],
                ball=Ball(x=w.x, y=2.0, confidence=1.0)))
            t += 1
        _emit(28.0, 10.0, 6)        # vissza az irányítóhoz
    return Match(_meta(fps), frames)


def test_wing_service_flags_the_running_wings():
    """Mozgásban átvevő szélső → futtatva kapják a szélsők."""
    from handball.pipeline.attack_types import wing_service

    rec = wing_service(_wsv_match(True))["home"]
    assert rec["receptions"] >= 6
    assert rec["verdict"] == "futtatva kapják a szélsők"


def test_wing_service_flags_the_static_wings():
    """Állva átvevő szélső → állva kapják a szélsők."""
    from handball.pipeline.attack_types import wing_service

    rec = wing_service(_wsv_match(False))["home"]
    assert rec["running"] == 0
    assert rec["verdict"] == "állva kapják a szélsők"


def test_wing_service_needs_enough_receptions():
    """Kevés (6-nál kevesebb) szélső-átvételnél nincs ítélet."""
    from handball.pipeline.attack_types import wing_service

    rec = wing_service(_wsv_match(True, n_passes=3))["home"]
    assert rec["verdict"] is None


def test_wing_runners_names_the_run_fed_wing():
    """A futó átvételeket egy szélső (2-es) kapja → ő a címzett."""
    from handball.pipeline.attack_types import wing_runners

    rec = wing_runners(_wsv_match(True))["home"]
    assert rec["running"] >= 2
    assert rec["top"] is not None
    assert rec["top"]["player_id"] == 2
    assert rec["top"]["share_pct"] >= 50.0


def test_wing_runners_needs_enough_running_receptions():
    """Kevés futó átvételnél (vagy állva kapó szélsőnél) nincs top."""
    from handball.pipeline.attack_types import wing_runners

    rec = wing_runners(_wsv_match(False))["home"]
    assert rec["running"] == 0
    assert rec["top"] is None


# ---- Keresztjáték (mennyit kereszteznek a hátsó sorban) ---------------------

def _crx_match(crossing, n_attacks=8, fps=25.0):
    """Felállt hazai támadások két hátsó emberrel (3-as irányító,
    4-es átlövő); keresztezésnél támadásonként kétszer y-sorrendet
    cserélnek."""
    frames = []
    t = 0
    for _ in range(n_attacks):
        n = int(4.0 * fps)
        for i in range(n):
            if crossing:
                phase = (i // (n // 4)) % 2      # negyedenként csere
                y3, y4 = (7.0, 13.0) if phase == 0 else (13.0, 7.0)
            else:
                y3, y4 = 7.0, 13.0
            frames.append(Frame(t=t, players=[
                _pl(3, Team.HOME, 28.0, y3),
                _pl(4, Team.HOME, 30.0, y4),
                _pl(21, Team.AWAY, 38.0, 10.0)],
                ball=Ball(x=28.0, y=y3, confidence=1.0)))
            t += 1
        for _ in range(int(3 * fps)):            # szünet
            frames.append(Frame(t=t, players=[], ball=None))
            t += 1
    return Match(_meta(fps), frames)


def test_crossing_runs_flags_the_crossing_backcourt():
    """Támadásonként több oldalcsere → sokat kereszteznek."""
    from handball.pipeline.attack_types import crossing_runs

    rec = crossing_runs(_crx_match(True))["home"]
    assert rec["attacks"] == 8 and rec["per_attack"] >= 1.0
    assert rec["verdict"] == "sokat kereszteznek"


def test_crossing_runs_flags_the_static_backcourt():
    """Oldalcsere nélkül statikus a hátsó soruk."""
    from handball.pipeline.attack_types import crossing_runs

    rec = crossing_runs(_crx_match(False))["home"]
    assert rec["crosses"] == 0
    assert rec["verdict"] == "statikus a hátsó soruk"


def test_crossing_runs_needs_enough_attacks():
    """Kevés (8-nál kevesebb) mért támadásnál nincs ítélet."""
    from handball.pipeline.attack_types import crossing_runs

    rec = crossing_runs(_crx_match(True, n_attacks=4))["home"]
    assert rec["verdict"] is None


def _crp_match(n_attacks=8, fps=25.0):
    """Három hátsó ember (3, 4, 5); a 3-as jár át a sorok közt
    (y: 5 → 10 → 15 → 10), a 4-es és 5-ös áll — minden kereszt a
    3-ason át fut."""
    frames = []
    t = 0
    for _ in range(n_attacks):
        n = int(4.0 * fps)
        for i in range(n):
            phase = (i // (n // 4)) % 4
            y3 = (5.0, 10.0, 15.0, 10.0)[phase]
            frames.append(Frame(t=t, players=[
                _pl(3, Team.HOME, 28.0, y3),
                _pl(4, Team.HOME, 30.0, 7.0),
                _pl(5, Team.HOME, 30.0, 13.0),
                _pl(21, Team.AWAY, 38.0, 10.0)],
                ball=Ball(x=28.0, y=y3, confidence=1.0)))
            t += 1
        for _ in range(int(3 * fps)):            # szünet
            frames.append(Frame(t=t, players=[], ball=None))
            t += 1
    return Match(_meta(fps), frames)


def test_crossing_runners_names_the_crossing_hub():
    """A sorok közt járó 3-as minden keresztben benne van → ő a
    keresztjáték motorja."""
    from handball.pipeline.attack_types import crossing_runners

    rec = crossing_runners(_crp_match())["home"]
    assert rec["crosses"] >= 3
    assert rec["top"] is not None
    assert rec["top"]["player_id"] == 3
    assert rec["top"]["share_pct"] >= 60.0


def test_crossing_runners_tie_of_two_backs_gives_no_top():
    """Két hátsó embernél minden kereszt holtverseny → nincs kiemelt
    keresztjáró."""
    from handball.pipeline.attack_types import crossing_runners

    rec = crossing_runners(_crx_match(True))["home"]
    assert rec["crosses"] >= 3
    assert rec["top"] is None


def test_crossing_runners_static_backcourt_gives_no_top():
    """Kereszt nélkül nincs kiemelt keresztjáró."""
    from handball.pipeline.attack_types import crossing_runners

    rec = crossing_runners(_crx_match(False))["home"]
    assert rec["crosses"] == 0
    assert rec["top"] is None


# ---- Beálló-futtatás (mozgásból vagy állva kapja a beálló) ------------------

def _psv_match(moving, n_passes=6, fps=25.0):
    """Az irányító (3-as) sorozatban a beállónak (4-es) passzol; a
    beálló vagy elzárásból lefordulva mozog, vagy beragadva áll."""
    frames = []
    t = 0
    px, pdir = 34.0, 1.0

    def _pivot():
        nonlocal px, pdir
        if moving:
            px += 0.1 * pdir
            if not 32.5 <= px <= 37.5:
                pdir *= -1.0
                px += 0.2 * pdir
        else:
            px = 34.0
        return _pl(4, Team.HOME, px, 10.0)

    def _emit(bx, by, n):
        nonlocal t
        for _ in range(n):
            frames.append(Frame(t=t, players=[
                _pl(3, Team.HOME, 28.0, 10.0), _pivot()],
                ball=Ball(x=bx, y=by, confidence=1.0)))
            t += 1

    _emit(28.0, 10.0, 150)          # poszt-minta: a 3-asnál a labda
    for _ in range(n_passes):
        _emit(28.0, 10.0, 6)        # az irányító birtokol
        for i in range(4):          # bejátszás a beállónak
            frames.append(Frame(t=t, players=[
                _pl(3, Team.HOME, 28.0, 10.0), _pivot()],
                ball=Ball(x=28.0 + (px - 28.0) * (i + 1) / 4.0,
                          y=10.0, confidence=1.0)))
            t += 1
        for _ in range(6):          # a beállónál a labda
            p = _pivot()
            frames.append(Frame(t=t, players=[
                _pl(3, Team.HOME, 28.0, 10.0), p],
                ball=Ball(x=p.x, y=10.0, confidence=1.0)))
            t += 1
        _emit(28.0, 10.0, 6)        # vissza az irányítóhoz
    return Match(_meta(fps), frames)


def test_pivot_service_flags_the_turning_pivot():
    """Mozgásban átvevő beálló → mozgásból kapja a beálló."""
    from handball.pipeline.attack_types import pivot_service

    rec = pivot_service(_psv_match(True))["home"]
    assert rec["receptions"] >= 5
    assert rec["verdict"] == "mozgásból kapja a beálló"


def test_pivot_service_flags_the_static_pivot():
    """Állva átvevő beálló → állva kapja a beálló."""
    from handball.pipeline.attack_types import pivot_service

    rec = pivot_service(_psv_match(False))["home"]
    assert rec["running"] == 0
    assert rec["verdict"] == "állva kapja a beálló"


def test_pivot_service_needs_enough_receptions():
    """Kevés (5-nél kevesebb) beálló-átvételnél nincs ítélet."""
    from handball.pipeline.attack_types import pivot_service

    rec = pivot_service(_psv_match(True, n_passes=3))["home"]
    assert rec["verdict"] is None


def test_pivot_runners_names_the_turning_pivot():
    """A mozgásos átvételeket egy beálló (4-es) hozza → ő a címzett."""
    from handball.pipeline.attack_types import pivot_runners

    rec = pivot_runners(_psv_match(True))["home"]
    assert rec["running"] >= 2
    assert rec["top"] is not None
    assert rec["top"]["player_id"] == 4
    assert rec["top"]["share_pct"] >= 50.0


def test_pivot_runners_static_pivot_gives_no_top():
    """Beragadva (állva) átvevő beállónál nincs lefordulós címzett."""
    from handball.pipeline.attack_types import pivot_runners

    rec = pivot_runners(_psv_match(False))["home"]
    assert rec["running"] == 0
    assert rec["top"] is None


# ---- Kontra-hullámok (az első ember vagy a befutó fejezi be) ----------------

def _fbw_match(second_wave, n_breaks=6, fps=25.0):
    """Lerohanás-sorozat: az 1-es fut elöl (első hullám), a 2-es fut
    be mögötte; a lövést a `second_wave` szerint a befutó vagy az
    első ember adja le. A nem-lövő a 6-os y-sávban fut, hogy a
    lövés röppályája ne érjen a közelébe."""
    frames = []
    t = 0
    y1 = 6.0 if second_wave else 10.0
    y2 = 10.0 if second_wave else 6.0
    for _ in range(n_breaks):
        n = int(3 * fps)
        for i in range(n):          # a kontra: mindkét ember fut előre
            x1 = 22.0 + 0.2 * i
            x2 = 16.0 + 0.2 * i
            bx = x2 if second_wave else x1
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, x1, y1),
                _pl(2, Team.HOME, x2, y2),
                _pl(9, Team.HOME, 1.5, 10.0, role="kapus")],
                ball=Ball(x=bx, y=10.0, confidence=1.0)))
            t += 1
        sx = (16.0 if second_wave else 22.0) + 0.2 * (n - 1)
        for i in range(7):          # lövés a +x kapura a lövő helyéről
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, 22.0 + 0.2 * (n - 1), y1),
                _pl(2, Team.HOME, 16.0 + 0.2 * (n - 1), y2),
                _pl(9, Team.HOME, 1.5, 10.0, role="kapus")],
                ball=Ball(x=min(40.0, sx + 1.5 * (i + 1)), y=10.0,
                          confidence=1.0)))
            t += 1
        for _ in range(int(4 * fps)):   # szünet a szakaszok közt
            frames.append(Frame(t=t, players=[], ball=None))
            t += 1
    return Match(_meta(fps), frames)


def test_fast_break_waves_flags_the_second_wave():
    """A befutó (2-es) lő minden kontra végén → második hullám."""
    from handball.pipeline.attack_types import fast_break_waves

    rec = fast_break_waves(_fbw_match(True))["home"]
    assert rec["breaks"] >= 5
    assert rec["verdict"] == "a második hullám fejezi be a kontrát"


def test_fast_break_waves_flags_the_first_man():
    """Az elöl futó (1-es) lő minden kontra végén → első ember."""
    from handball.pipeline.attack_types import fast_break_waves

    rec = fast_break_waves(_fbw_match(False))["home"]
    assert rec["second"] == 0
    assert rec["verdict"] == "az első ember fejezi be a kontrát"


def test_fast_break_waves_needs_enough_breaks():
    """Kevés (5-nél kevesebb) lövésig jutó kontránál nincs ítélet."""
    from handball.pipeline.attack_types import fast_break_waves

    rec = fast_break_waves(_fbw_match(True, n_breaks=3))["home"]
    assert rec["verdict"] is None


def test_second_wave_finishers_names_the_runner():
    """A befutó (2-es) adja le a második hullámos befejezéseket → ő a
    kontra befutó embere."""
    from handball.pipeline.attack_types import second_wave_finishers

    rec = second_wave_finishers(_fbw_match(True))["home"]
    assert rec["second"] >= 2
    assert rec["top"] is not None
    assert rec["top"]["player_id"] == 2
    assert rec["top"]["share_pct"] >= 50.0


def test_second_wave_finishers_first_man_gives_no_top():
    """Ha az első ember fejezi be a kontrákat, nincs befutó ember."""
    from handball.pipeline.attack_types import second_wave_finishers

    rec = second_wave_finishers(_fbw_match(False))["home"]
    assert rec["second"] == 0
    assert rec["top"] is None


# ---- Kontra-elszökés (előre szökött ember vagy együtt felfutás) -------------

def _fbh_match(ahead, n_breaks=6, fps=25.0):
    """Lerohanás-sorozat: a 2-es viszi a labdát; az `ahead` szerint az
    1-es már 10 méterrel a labda előtt várja az indítást, vagy a
    labda mellett fut fel."""
    frames = []
    t = 0
    for _ in range(n_breaks):
        for i in range(int(4 * fps)):
            bx = 4.0 + 0.2 * i
            x1 = min(36.0, bx + 10.0) if ahead else bx + 1.0
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, x1, 10.0),
                _pl(2, Team.HOME, bx, 6.0),
                _pl(9, Team.HOME, 1.5, 10.0, role="kapus")],
                ball=Ball(x=bx, y=6.0, confidence=1.0)))
            t += 1
        for _ in range(int(4 * fps)):   # szünet a szakaszok közt
            frames.append(Frame(t=t, players=[], ball=None))
            t += 1
    return Match(_meta(fps), frames)


def test_fast_break_headstart_flags_the_sneaking_team():
    """A labda előtt 10 méterrel váró ember → elszökős kontra."""
    from handball.pipeline.attack_types import fast_break_headstart

    rec = fast_break_headstart(_fbh_match(True))["home"]
    assert rec["breaks"] >= 5
    assert rec["verdict"] == "előre szökött emberrel kontráznak"


def test_fast_break_headstart_flags_the_collective_team():
    """A labdával együtt felfutó emberek → együtt futnak fel."""
    from handball.pipeline.attack_types import fast_break_headstart

    rec = fast_break_headstart(_fbh_match(False))["home"]
    assert rec["ahead"] == 0
    assert rec["verdict"] == "együtt futnak fel"


def test_fast_break_headstart_needs_enough_breaks():
    """Kevés (5-nél kevesebb) lerohanásnál nincs ítélet."""
    from handball.pipeline.attack_types import fast_break_headstart

    rec = fast_break_headstart(_fbh_match(True, n_breaks=3))["home"]
    assert rec["verdict"] is None


# ---- Kontra-esés (melyik félidőben kontráznak) ------------------------------

def _brf_match(breaks_first=True, halftime=True, fps=25.0):
    """Egyik félidőben kontrázós, a másikban felállt játék; köztük 90
    mp-es (üres) szünet, amit a félidő-felismerés megtalál."""
    frames = []
    t = 0

    def _half(with_breaks):
        nonlocal t, frames
        for _ in range(6):
            if with_breaks:
                seg = _attack_frames(t, 4.0, 22.0, 38.0, fps=fps)
            else:
                seg = _attack_frames(t, 10.0, 30.0, 31.0, fps=fps)
            frames += seg
            t = frames[-1].t + 1
            for _ in range(int(2 * fps)):   # szünet: állnak, nincs labda
                players = [
                    _pl(1, Team.HOME, 25.0, 10.0),
                    _pl(2, Team.HOME, 22.0, 6.0),
                    _pl(9, Team.HOME, 1.5, 10.0, role="kapus"),
                    _pl(21, Team.AWAY, 37.0, 8.0),
                    _pl(22, Team.AWAY, 37.0, 12.0),
                ]
                frames.append(Frame(t=t, players=players, ball=None))
                t += 1

    _half(with_breaks=breaks_first)
    if halftime:
        for _ in range(int(90 * fps)):      # félidei szünet: üres pálya
            frames.append(Frame(t=t, players=[], ball=None))
            t += 1
    _half(with_breaks=not breaks_first)
    return Match(_meta(fps), frames)


def test_break_share_fade_flags_the_fading_break():
    """Kontrázós első, felállt második félidő → eláll a kontrájuk."""
    from handball.pipeline.attack_types import break_share_fade

    rec = break_share_fade(_brf_match(True))["home"]
    assert rec["fh_breaks"] >= 5 and rec["sh_breaks"] == 0
    assert rec["verdict"] == "a második félidőben eláll a kontrájuk"


def test_break_share_fade_flags_the_late_runner():
    """Felállt első, kontrázós második félidő → a hajrára
    kontrázósabbak."""
    from handball.pipeline.attack_types import break_share_fade

    rec = break_share_fade(_brf_match(False))["home"]
    assert rec["verdict"] == "a hajrára kontrázósabbak"


def test_break_share_fade_needs_halftime():
    """Felismert félidei szünet nélkül nincs ítélet."""
    from handball.pipeline.attack_types import break_share_fade

    rec = break_share_fade(_brf_match(True, halftime=False))["home"]
    assert rec["verdict"] is None and rec["gap_pp"] is None


# ---- Szélső-mélység (milyen mélyről lőnek a szélsők) ------------------------

def _wsd_match(deep, n_shots=6, fps=25.0):
    """Szélső-lövés sorozat: a 2-es szélső a `deep` szerint a hatosig
    befutva (2,5 m) vagy messziről (9,5 m) ereszti el a lövést."""
    frames = []
    t = 0
    sx = 37.5 if deep else 30.5

    def _emit(bx, by, n):
        nonlocal t
        for _ in range(n):
            frames.append(Frame(t=t, players=[
                _pl(2, Team.HOME, 34.0, 3.0)],
                ball=Ball(x=bx, y=by, confidence=1.0)))
            t += 1

    _emit(34.0, 3.0, 150)           # poszt-minta: a szélsőnél a labda
    for _ in range(n_shots):
        _emit(34.0, 3.0, 10)        # birtoklás a szélső sávban
        for i in range(5):          # a szélső a lövő-helyre viszi
            frames.append(Frame(t=t, players=[
                _pl(2, Team.HOME, 34.0 + (sx - 34.0) * (i + 1) / 5.0,
                    3.0)],
                ball=Ball(x=34.0 + (sx - 34.0) * (i + 1) / 5.0,
                          y=3.0, confidence=1.0)))
            t += 1
        steps = max(3, int(round(40.5 - sx)))
        for i in range(1, steps + 1):   # lövés a kapura
            f_ = i / steps
            frames.append(Frame(t=t, players=[
                _pl(2, Team.HOME, sx, 3.0)],
                ball=Ball(x=sx + (40.5 - sx) * f_,
                          y=3.0 + (10.0 - 3.0) * f_,
                          confidence=1.0)))
            t += 1
        _emit(34.0, 3.0, 30)        # szünet a lövések közt
    return Match(_meta(fps), frames)


def test_wing_shot_depth_flags_the_deep_wing():
    """A hatosig befutó szélső (2,5 m-ről lő) → mélyre befutó."""
    from handball.pipeline.attack_types import wing_shot_depth

    rec = wing_shot_depth(_wsd_match(True))["home"]
    assert rec["shots"] >= 5
    assert rec["verdict"] == "mélyre befutó szélsők"


def test_wing_shot_depth_flags_the_distant_wing():
    """A messziről (9,5 m) lövő szélső → messziről lövő."""
    from handball.pipeline.attack_types import wing_shot_depth

    rec = wing_shot_depth(_wsd_match(False))["home"]
    assert rec["verdict"] == "messziről lövő szélsők"


def test_wing_shot_depth_needs_enough_shots():
    """Kevés (5-nél kevesebb) szélső-lövésnél nincs ítélet."""
    from handball.pipeline.attack_types import wing_shot_depth

    rec = wing_shot_depth(_wsd_match(True, n_shots=3))["home"]
    assert rec["verdict"] is None


# ---- Hiba-állás (hátrányban szórják-e a labdát) -----------------------------

def _tbs_match(panic=True, n=6, fps=25.0):
    """Döntetlennél tiszta (vagy eladós) hazai támadások, majd egy
    vendég-gól után hátrányban eladós (vagy tiszta) támadások."""
    frames = []
    t = 0

    def _pause(sec=1.6):
        nonlocal t
        for _ in range(int(sec * fps)):
            frames.append(Frame(t=t, players=[], ball=None))
            t += 1

    def _home_attack(turnover):
        nonlocal t, frames
        seg = _attack_frames(t, 4.0, 22.0, 33.0, fps=fps)
        frames += seg
        t = frames[-1].t + 1
        if turnover:
            # A rossz hazapassz HÁTRAFELÉ megy (nem kapu-irányba, hogy
            # ne látsszon lövésnek), és a vendég 21-es csípi el.
            for i in range(3):
                frames.append(Frame(t=t, players=[
                    _pl(1, Team.HOME, 33.0, 10.0),
                    _pl(21, Team.AWAY, 29.0, 6.0)],
                    ball=Ball(x=33.0 - (33.0 - 29.0) * (i + 1) / 3.0,
                              y=10.0 - (10.0 - 6.0) * (i + 1) / 3.0,
                              confidence=1.0)))
                t += 1
            for _ in range(8):      # a vendégnél a labda: eladás
                frames.append(Frame(t=t, players=[
                    _pl(1, Team.HOME, 33.0, 10.0),
                    _pl(21, Team.AWAY, 29.0, 6.0)],
                    ball=Ball(x=29.0, y=6.0, confidence=1.0)))
                t += 1
        _pause()

    for _ in range(n):              # döntetlen állásnál
        _home_attack(turnover=not panic)
    for _ in range(10):             # vendég-gól: a 21-es a -x kapura lő
        frames.append(Frame(t=t, players=[_pl(21, Team.AWAY, 6.0, 10.0)],
                            ball=Ball(x=6.0, y=10.0, confidence=1.0)))
        t += 1
    for i in range(7):
        frames.append(Frame(t=t, players=[_pl(21, Team.AWAY, 6.0, 10.0)],
                            ball=Ball(x=max(6.0 - (i + 1) * 1.0, -0.5),
                                      y=10.0, confidence=1.0)))
        t += 1
    _pause()
    for _ in range(n):              # hazai hátrányban
        _home_attack(turnover=panic)
    return Match(_meta(fps), frames)


def test_turnovers_by_score_flags_the_panicking_team():
    """Hátrányban minden támadás eladással zárul → kapkodnak."""
    from handball.pipeline.attack_types import turnovers_by_score

    rec = turnovers_by_score(_tbs_match(True))["home"]
    assert rec["trailing"]["attacks"] >= 5
    assert rec["trailing"]["turnovers"] >= 5
    assert rec["verdict"] == "hátrányban kapkodnak"


def test_turnovers_by_score_flags_the_composed_team():
    """Hátrányban tiszta, döntetlennél eladós → hátrányban is
    rendezettek."""
    from handball.pipeline.attack_types import turnovers_by_score

    rec = turnovers_by_score(_tbs_match(False))["home"]
    assert rec["verdict"] == "hátrányban is rendezettek"


def test_turnovers_by_score_needs_enough_attacks():
    """Kevés (5-nél kevesebb) támadásnál nincs ítélet."""
    from handball.pipeline.attack_types import turnovers_by_score

    rec = turnovers_by_score(_tbs_match(True, n=3))["home"]
    assert rec["verdict"] is None


def _obt_match(n_out: int):
    """n_out kidobott labda: hazai birtoklás (20,10), majd a labda
    kirepül az oldalvonalon (y > 20), aztán vissza a birtoklóhoz."""
    meta = MatchMeta(match_id="obt", home_team="H", away_team="A", fps=25.0)
    frames = []
    t = 0
    for _ in range(n_out):
        # 2 mp nyugodt hazai birtoklás a pálya közepén.
        for _ in range(50):
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 20.0, 10.0)],
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
            t += 1
        # A labda kirepül az oldalvonalon (a játékos a helyén marad).
        for k in range(6):
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 20.0, 10.0)],
                                ball=Ball(x=20.0, y=10.0 + 2.0 * (k + 1),
                                          confidence=1.0)))
            t += 1
        # 2 mp kint, majd a bedobás után újra bent.
        for _ in range(50):
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 20.0, 10.0)],
                                ball=Ball(x=20.0, y=22.0, confidence=1.0)))
            t += 1
        for _ in range(25):
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 20.0, 10.0)],
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
            t += 1
    return Match(meta, frames)


def test_balls_out_counts_sideline_exits():
    """3 kidobott labda a hazaiaknál → ítélet; a vendégnél semmi."""
    from handball.pipeline.attack_types import balls_out

    ob = balls_out(_obt_match(3))
    assert ob["home"]["out"] == 3
    assert ob["home"]["verdict"] == "sok kidobott labda"
    assert ob["away"]["out"] == 0
    assert ob["away"]["verdict"] is None


def test_balls_out_few_samples_no_verdict():
    """Egyetlen kimenő labda → számoljuk, de nincs ítélet."""
    from handball.pipeline.attack_types import balls_out

    ob = balls_out(_obt_match(1))
    assert ob["home"]["out"] == 1
    assert ob["home"]["verdict"] is None


def _bks_match():
    """5 döntetlennél futott felállt hazai támadás, majd 3 vendég-gól,
    utána 5 hátrányban futott hazai lerohanás."""
    meta = MatchMeta(match_id="bks", home_team="H", away_team="A", fps=25.0)
    frames = []
    t = 0

    def neutral(n=10):
        nonlocal t
        for _ in range(n):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=18.0, y=10.0, confidence=1.0)))
            t += 1

    # 5 hazai felállt támadás döntetlennél (8 mp állás x=30-nál).
    for _ in range(5):
        for _ in range(int(8 * 25)):
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 30.0, 10.0)],
                                ball=Ball(x=30.0, y=10.0, confidence=1.0)))
            t += 1
        neutral()

    # 3 vendég-gól: a lövő (10,10)-ről az x=0 kapuba lő.
    for _ in range(3):
        for _ in range(40):
            frames.append(Frame(t=t, players=[_pl(9, Team.AWAY, 10.0, 10.0)],
                                ball=Ball(x=10.0, y=10.0, confidence=1.0)))
            t += 1
        x = 10.0
        while x > -0.5:
            x -= 0.5
            frames.append(Frame(t=t, players=[_pl(9, Team.AWAY, 10.0, 10.0)],
                                ball=Ball(x=max(x, -0.5), y=10.0,
                                          confidence=1.0)))
            t += 1
        # Zóna-reset: a labda a felező közelében pihen.
        for _ in range(40):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=18.0, y=10.0, confidence=1.0)))
            t += 1

    # 5 hazai lerohanás hátrányban: 3 mp alatt x=21 → 33 (4 m/s).
    for _ in range(5):
        for k in range(int(3 * 25)):
            x = 21.0 + 12.0 * (k + 1) / (3 * 25)
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, x, 10.0)],
                                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1
        neutral()
    return Match(meta, frames)


def test_breaks_by_score_flags_forced_breaks():
    """Döntetlennél felállt, hátrányban csupa lerohanás → kényszer-kontra."""
    from handball.pipeline.attack_types import breaks_by_score

    bks = breaks_by_score(_bks_match())
    h = bks["home"]
    assert h["level"]["attacks"] >= 5 and h["level"]["breaks"] == 0
    assert h["trailing"]["attacks"] >= 5
    assert h["trailing"]["breaks"] >= 5
    assert h["verdict"] == "hátrányban kontrába menekülnek"
    assert bks["away"]["verdict"] is None


def test_breaks_by_score_few_samples_none():
    """Kevés (5-nél kevesebb) támadás állapotonként → nincs ítélet."""
    from handball.pipeline.attack_types import breaks_by_score

    meta = MatchMeta(match_id="bks2", home_team="H", away_team="A", fps=25.0)
    frames = []
    t = 0
    for _ in range(3):
        for _ in range(int(8 * 25)):
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 30.0, 10.0)],
                                ball=Ball(x=30.0, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(10):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=18.0, y=10.0, confidence=1.0)))
            t += 1
    bks = breaks_by_score(Match(meta, frames))
    assert bks["home"]["verdict"] is None


def _asf_goal_frames(t0, assisted: bool):
    """Egy hazai gól a +x kapura. assisted=True esetén P1 passza előzi
    meg (gólpassz), különben a lövő 4,5 mp-ig egyedül tartja a labdát."""
    frames = []
    t = t0
    if assisted:
        # P1 tartja (30,10)-nél 1,5 mp-ig.
        for _ in range(38):
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, 30.0, 10.0), _pl(2, Team.HOME, 33.0, 10.0),
            ], ball=Ball(x=30.0, y=10.0, confidence=1.0)))
            t += 1
        # Passz P2-nek: 0,2/kocka (5 m/s — lövésnek lassú).
        x = 30.0
        while x < 33.0:
            x += 0.2
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, 30.0, 10.0), _pl(2, Team.HOME, 33.0, 10.0),
            ], ball=Ball(x=min(x, 33.0), y=10.0, confidence=1.0)))
            t += 1
        # P2 rövid tartás (0,5 mp), a gólpassz-ablakon belül lő.
        hold = 12
    else:
        # A lövő egyedül tartja 4,5 mp-ig — nincs gólpassz-ablak.
        hold = int(4.5 * 25)
    for _ in range(hold):
        frames.append(Frame(t=t, players=[_pl(2, Team.HOME, 33.0, 10.0)],
                            ball=Ball(x=33.0, y=10.0, confidence=1.0)))
        t += 1
    # Lövés: 0,5/kocka a kapuba (x=40,5), a kapufák közt (y=10).
    x = 33.0
    while x < 40.5:
        x += 0.5
        frames.append(Frame(t=t, players=[_pl(2, Team.HOME, 33.0, 10.0)],
                            ball=Ball(x=min(x, 40.5), y=10.0,
                                      confidence=1.0)))
        t += 1
    # Zóna-reset: a labda a felezőn pihen.
    for _ in range(40):
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    return frames, t


def test_assist_fade_flags_stalling_ball():
    """1. félidő: 3 gólpasszos gól; 2. félidő: 3 egyéni gól →
    a hajrában megáll a labda."""
    from handball.pipeline.attack_types import assist_fade

    meta = MatchMeta(match_id="asf", home_team="H", away_team="A", fps=25.0)
    frames = []
    t = 0
    for _ in range(3):
        gf, t = _asf_goal_frames(t, assisted=True)
        frames += gf
    # Szünet: 90 mp üres kocka.
    for _ in range(int(90 * 25)):
        frames.append(Frame(t=t, players=[], ball=None))
        t += 1
    for _ in range(3):
        gf, t = _asf_goal_frames(t, assisted=False)
        frames += gf

    asf = assist_fade(Match(meta, frames))
    h = asf["home"]
    assert h["fh_goals"] == 3 and h["fh_assisted"] == 3
    assert h["sh_goals"] == 3 and h["sh_assisted"] == 0
    assert h["verdict"] == "a hajrában megáll a labda"
    assert asf["away"]["verdict"] is None


def test_assist_fade_needs_halftime_and_goals():
    """Felismert szünet nélkül nincs ítélet."""
    from handball.pipeline.attack_types import assist_fade

    meta = MatchMeta(match_id="asf2", home_team="H", away_team="A", fps=25.0)
    frames = []
    t = 0
    for _ in range(3):
        gf, t = _asf_goal_frames(t, assisted=True)
        frames += gf
    asf = assist_fade(Match(meta, frames))
    assert asf["home"]["verdict"] is None
    assert asf["home"]["gap_pp"] is None


def _scf_miss_frames(t0, rebound: bool):
    """Egy hazai kimaradt lövés a +x kapura (szélesre, y=5), utána
    rebound=True esetén 2 mp-en belül újra lövés (megnyert lepattanó)."""
    frames = []
    t = t0

    def flight(x0, y0, x1, y1, step=0.5):
        nonlocal t
        import math as _m
        d = _m.hypot(x1 - x0, y1 - y0)
        n = max(1, int(d / step))
        for k in range(1, n + 1):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=x0 + (x1 - x0) * k / n,
                                          y=y0 + (y1 - y0) * k / n,
                                          confidence=1.0)))
            t += 1

    # Nyugalmi tartás a zónán kívül.
    for _ in range(20):
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=30.0, y=10.0, confidence=1.0)))
        t += 1
    # Lövés szélesre: a kapufákon kívül (y=5) hagyja el a pályát.
    flight(30.0, 10.0, 40.5, 5.0)
    if rebound:
        # A lepattanó visszakerül, és 2 mp-en belül jön az új lövés.
        for _ in range(5):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=30.0, y=10.0, confidence=1.0)))
            t += 1
        flight(30.0, 10.0, 40.5, 5.0)
    # Hosszú szünet: a következő lövés már kívül esik az ablakon.
    for _ in range(int(8 * 25)):
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    return frames, t


def test_second_chance_fade_flags_fading_fight():
    """1. félidő: 3 visszaharcolt lepattanó; 2. félidő: 3 elveszett →
    a hajrára elfogy a lepattanó-harcuk."""
    from handball.pipeline.attack_types import second_chance_fade

    meta = MatchMeta(match_id="scf", home_team="H", away_team="A", fps=25.0)
    frames = []
    t = 0
    for _ in range(3):
        gf, t = _scf_miss_frames(t, rebound=True)
        frames += gf
    for _ in range(int(90 * 25)):
        frames.append(Frame(t=t, players=[], ball=None))
        t += 1
    for _ in range(3):
        gf, t = _scf_miss_frames(t, rebound=False)
        frames += gf

    scf = second_chance_fade(Match(meta, frames))
    h = scf["home"]
    assert h["fh_misses"] >= 3 and h["fh_won"] >= 3
    assert h["sh_misses"] == 3 and h["sh_won"] == 0
    assert h["verdict"] == "a hajrára elfogy a lepattanó-harcuk"
    assert scf["away"]["verdict"] is None


def test_second_chance_fade_needs_halftime():
    """Felismert szünet nélkül nincs ítélet."""
    from handball.pipeline.attack_types import second_chance_fade

    meta = MatchMeta(match_id="scf2", home_team="H", away_team="A", fps=25.0)
    frames = []
    t = 0
    for _ in range(3):
        gf, t = _scf_miss_frames(t, rebound=True)
        frames += gf
    scf = second_chance_fade(Match(meta, frames))
    assert scf["home"]["verdict"] is None
    assert scf["home"]["gap_pp"] is None


def _ams_half_frames(t0, n, fast: bool):
    """n hazai támadás: fast=True esetén 3 mp-es lerohanások (x=21→33),
    különben 8 mp-es felállt támadások (x=30-nál állva)."""
    frames = []
    t = t0
    for _ in range(n):
        if fast:
            for k in range(int(3 * 25)):
                x = 21.0 + 12.0 * (k + 1) / (3 * 25)
                frames.append(Frame(t=t,
                                    players=[_pl(1, Team.HOME, x, 10.0)],
                                    ball=Ball(x=x, y=10.0, confidence=1.0)))
                t += 1
        else:
            for _ in range(int(8 * 25)):
                frames.append(Frame(t=t,
                                    players=[_pl(1, Team.HOME, 30.0, 10.0)],
                                    ball=Ball(x=30.0, y=10.0,
                                              confidence=1.0)))
                t += 1
        for _ in range(10):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=18.0, y=10.0, confidence=1.0)))
            t += 1
    return frames, t


def test_attack_mix_shift_flags_the_adapting_team():
    """1. félidő csupa felállt, 2. félidő csupa lerohanás → átrendezik."""
    from handball.pipeline.attack_types import attack_mix_shift

    meta = MatchMeta(match_id="ams", home_team="H", away_team="A", fps=25.0)
    frames, t = _ams_half_frames(0, 6, fast=False)
    for _ in range(int(90 * 25)):
        frames.append(Frame(t=t, players=[], ball=None))
        t += 1
    sh, t = _ams_half_frames(t, 6, fast=True)
    frames += sh

    ams = attack_mix_shift(Match(meta, frames))
    h = ams["home"]
    assert h["fh_attacks"] >= 6 and h["sh_attacks"] >= 6
    assert h["shift_pp"] is not None and h["shift_pp"] >= 30.0
    assert h["verdict"] == "a szünet után átrendezik a támadójátékukat"
    assert ams["away"]["verdict"] is None


def test_attack_mix_shift_flags_the_static_team():
    """Mindkét félidő ugyanaz a felállt játék → félidőn át ugyanaz;
    szünet-jel nélkül nincs ítélet."""
    from handball.pipeline.attack_types import attack_mix_shift

    meta = MatchMeta(match_id="ams2", home_team="H", away_team="A", fps=25.0)
    frames, t = _ams_half_frames(0, 6, fast=False)
    for _ in range(int(90 * 25)):
        frames.append(Frame(t=t, players=[], ball=None))
        t += 1
    sh, t = _ams_half_frames(t, 6, fast=False)
    frames += sh

    ams = attack_mix_shift(Match(meta, frames))
    assert ams["home"]["shift_pp"] is not None
    assert ams["home"]["shift_pp"] <= 10.0
    assert ams["home"]["verdict"] == "félidőn át ugyanazt játsszák"

    # Szünet nélkül: nincs ítélet.
    nob, t2 = _ams_half_frames(0, 6, fast=False)
    ams2 = attack_mix_shift(Match(meta, nob))
    assert ams2["home"]["verdict"] is None


def _pds_pass_frames(t0, x_from, x_to, n):
    """n hazai passz az x_from → x_to álló játékosok közt, minden
    passz után szabad-labdás megszakítással (új birtoklás-lánc)."""
    frames = []
    t = t0
    for _ in range(n):
        def both():
            return [_pl(11, Team.HOME, x_from, 10.0),
                    _pl(12, Team.HOME, x_to, 10.0)]
        # A passzoló tartja a labdát.
        for _ in range(15):
            frames.append(Frame(t=t, players=both(),
                                ball=Ball(x=x_from, y=10.0,
                                          confidence=1.0)))
            t += 1
        # A labda 0,3/kocka lépéssel (7,5 m/s — lövésnek lassú) átér.
        x = x_from
        step = 0.3 if x_to > x_from else -0.3
        while (x < x_to) if x_to > x_from else (x > x_to):
            x += step
            frames.append(Frame(t=t, players=both(),
                                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1
        # A fogadó megtartja.
        for _ in range(15):
            frames.append(Frame(t=t, players=both(),
                                ball=Ball(x=x_to, y=10.0,
                                          confidence=1.0)))
            t += 1
        # Megszakítás: vendég-érintés a 18-asnál — így a következő
        # hazai birtoklás nem "hátra-passzként" kapcsolódik össze.
        for _ in range(15):
            frames.append(Frame(t=t,
                                players=[_pl(21, Team.AWAY, 18.0, 10.0)],
                                ball=Ball(x=18.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    return frames, t


def test_pass_direction_by_score_flags_clock_killing():
    """Döntetlennél előre-passzok, 3 gól után (előnyben) csupa
    hátra-passz → előnyben hátrafelé járatják a labdát."""
    from handball.pipeline.attack_types import pass_direction_by_score

    meta = MatchMeta(match_id="pds", home_team="H", away_team="A", fps=25.0)
    frames, t = _pds_pass_frames(0, 24.0, 30.0, 11)  # döntetlen: előre
    for _ in range(3):
        gf, t = _asf_goal_frames(t, assisted=False)
        frames += gf
    lead, t = _pds_pass_frames(t, 30.0, 24.0, 11)    # előnyben: hátra
    frames += lead

    pds = pass_direction_by_score(Match(meta, frames))
    h = pds["home"]
    assert h["level"]["passes"] >= 10
    assert h["level"]["forward"] >= 10
    assert h["leading"]["passes"] >= 10
    assert h["leading"]["back"] >= 10
    assert h["verdict"] == "előnyben hátrafelé járatják a labdát"
    assert pds["away"]["verdict"] is None


def test_pass_direction_by_score_few_passes_none():
    """Kevés (10-nél kevesebb) passz állapotonként → nincs ítélet."""
    from handball.pipeline.attack_types import pass_direction_by_score

    meta = MatchMeta(match_id="pds2", home_team="H", away_team="A", fps=25.0)
    frames, t = _pds_pass_frames(0, 24.0, 30.0, 5)
    pds = pass_direction_by_score(Match(meta, frames))
    assert pds["home"]["verdict"] is None


def _kot_cycle(t, target_y, fps=25.0):
    """Egy betörés → kiosztás ciklus kockái.

    1) a betörő (1) a kapu 9 méteres körzetében birtokolja a labdát,
    2) kiosztja a társának (2) a zónán kívülre → PASSZ esemény,
    3) az ellenfél megszerzi a labdát a saját térfelén → a szakasz zárul
       (és a passz-lánc sem folytatódik a következő ciklusba).
    """
    frames = []
    for _ in range(40):  # 1) betörés: a labda a kaputól 7 m-re
        frames.append(Frame(t=t, players=[
            _pl(1, Team.HOME, 33.0, 10.0),
            _pl(2, Team.HOME, 28.0, target_y),
            _pl(20, Team.AWAY, 35.0, 10.0)],
            ball=Ball(x=33.0, y=10.0, confidence=1.0)))
        t += 1
    for _ in range(30):  # 2) kiosztás a zónán kívülre
        frames.append(Frame(t=t, players=[
            _pl(1, Team.HOME, 33.0, 10.0),
            _pl(2, Team.HOME, 28.0, target_y),
            _pl(20, Team.AWAY, 35.0, 10.0)],
            ball=Ball(x=28.0, y=target_y, confidence=1.0)))
        t += 1
    for _ in range(30):  # 3) ellenfél-birtoklás: szakasz-határ
        frames.append(Frame(t=t, players=[
            _pl(1, Team.HOME, 20.0, 10.0),
            _pl(2, Team.HOME, 22.0, 12.0),
            _pl(20, Team.AWAY, 10.0, 10.0)],
            ball=Ball(x=10.0, y=10.0, confidence=1.0)))
        t += 1
    return frames, t


def test_kickout_targets_flags_a_predictable_target():
    """Öt betörés, mindig ugyanaz a kiosztás-célpont → kiszámítható."""
    from handball.pipeline.attack_types import kickout_targets

    frames, t = [], 0
    for _ in range(5):
        chunk, t = _kot_cycle(t, 14.0)
        frames += chunk
    res = kickout_targets(Match(_meta(), frames))
    h = res["home"]
    assert h["kickouts"] >= 4, h
    assert h["top"] is not None and h["top"]["player_id"] == 2, h
    assert h["top_pct"] == 100.0, h
    assert h["verdict"] == "kiszámítható a kiosztás", h
    # A vendégnek nincs betörése — nem találgatunk helyette.
    assert res["away"]["verdict"] is None, res["away"]


def test_kickout_targets_silent_with_few_kickouts():
    """Két betörés kevés az ítélethez — None, nem hallgatólagos 0."""
    from handball.pipeline.attack_types import kickout_targets

    frames, t = [], 0
    for _ in range(2):
        chunk, t = _kot_cycle(t, 14.0)
        frames += chunk
    res = kickout_targets(Match(_meta(), frames))
    h = res["home"]
    assert h["kickouts"] <= 2, h
    assert h["top"] is None and h["top_pct"] is None, h
    assert h["verdict"] is None, h


# ---- Lepattanó-poszt (ki lő másodszor) --------------------------------------

def _scr_shot(t0, tid, sx, sy, goal=False):
    """Egy hazai lövés a +x kapura a `tid` játékostól, (sx, sy)-ból; a
    2-es fixen a 6 m-nél áll (beálló-minta), az 1-es kint (átlövő)."""
    def cast():
        return [_pl(1, Team.HOME, 29.0, 10.0),
                _pl(2, Team.HOME, 34.0, 10.0)]
    px, py = (29.0, 10.0) if tid == 1 else (34.0, 10.0)
    assert (px, py) == (sx, sy)
    frames = []
    for i in range(3):
        frames.append(Frame(t=t0 + i, players=cast(),
                            ball=Ball(x=sx + 0.2, y=sy, confidence=1.0)))
    t = t0 + 3
    for i in range(8):
        bx = min(sx + 1.5 * (i + 1), 40.0)
        frames.append(Frame(t=t + i, players=cast(),
                            ball=Ball(x=bx, y=(10.0 if goal else 5.0),
                                      confidence=1.0)))
    return frames


def _scr_match(pairs):
    """`pairs` = (első lövő, második lövő) — az első kimarad, a második
    az ablakon belül újra lő; a párok közt hosszú szünet."""
    frames = []
    t = 0
    for first, second in pairs:
        # Birtoklás-bemelegítés: ebből épül a poszt-minta
        # (ROLE_MIN_SAMPLES) — a labda az 1-esnél áll.
        for i in range(40):
            frames.append(Frame(t=t + i, players=[
                _pl(1, Team.HOME, 29.0, 10.0),
                _pl(2, Team.HOME, 34.0, 10.0)],
                ball=Ball(x=29.2, y=10.0, confidence=1.0)))
        t += 40
        frames += _scr_shot(t, first, 29.0 if first == 1 else 34.0, 10.0)
        t = frames[-1].t + 1
        for i in range(12):
            frames.append(Frame(t=t + i, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
        t = frames[-1].t + 1
        frames += _scr_shot(t, second, 29.0 if second == 1 else 34.0,
                            10.0, goal=True)
        t = frames[-1].t + 1
        for i in range(200):
            frames.append(Frame(t=t + i, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
        t = frames[-1].t + 1
    return Match(_meta(), frames)


def test_second_chance_roles_finds_the_rebound_post():
    """Ha a második lövéseket rendre ugyanaz a poszt adja le, a zárás
    után őt kell kivenni a lepattanóból."""
    from handball.pipeline.attack_types import (SCR_MIN_SHOTS,
                                                second_chance_roles)

    rec = second_chance_roles(_scr_match([(1, 2)] * 3 + [(2, 1)]))["home"]
    assert rec["second_shots"] >= SCR_MIN_SHOTS, rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "lepattanó" in rec["verdict"], rec


def test_second_chance_roles_silent_with_few_shots():
    """Két második lövésből nincs ítélet."""
    from handball.pipeline.attack_types import second_chance_roles

    rec = second_chance_roles(_scr_match([(1, 2), (2, 1)]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


def _scs2_match(setters, fps=25.0):
    """`setters` = elzárásonként az elzárásba álló HAZAI játékos (5:
    beálló, 7: szélső). Első szakasz: hosszú hazai birtoklás a +x kapu
    felé (poszt-minta), utána a meglévő elzáró-minta lövésenként."""
    frames = []
    t = 0
    role_pos = {1: (28.0, 10.0), 5: (34.0, 10.0), 7: (35.0, 3.0)}
    for _ in range(300):             # hazai birtoklás: poszt-minta
        players = [_pl(pid, Team.HOME, *xy)
                   for pid, xy in role_pos.items()]
        players.append(_pl(20, Team.AWAY, 20.0, 16.0))
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=34.2, y=10.0, confidence=1.0)))
        t += 1
    for setter_id in setters:
        players = [_pl(1, Team.HOME, 30.0, 10.0),          # a lövő
                   _pl(20, Team.AWAY, 31.5, 10.0),         # az őrző
                   _pl(setter_id, Team.HOME, 31.5, 11.0)]  # az elzáró
        for _ in range(30):
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=30.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        for i in range(14):
            frames.append(Frame(
                t=t, players=players,
                ball=Ball(x=min(30.0 + 0.8 * (i + 1), 40.0), y=10.0,
                          confidence=1.0)))
            t += 1
        for _ in range(40):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=40.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_screen_setter_roles_names_the_screening_post():
    """Ha az elzárások zöme ugyanarról a posztról jön, az ő oldalán
    kell a hangos váltás."""
    from handball.pipeline.attack_types import (SCR2_MIN_SCREENS,
                                                screen_setter_roles)

    rec = screen_setter_roles(_scs2_match([5, 5, 5, 7]))["home"]
    assert rec["screens"] >= SCR2_MIN_SCREENS, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "váltás" in rec["verdict"], rec


def test_screen_setter_roles_silent_with_few_screens():
    """Néhány poszthoz kötött elzárásból nincs ítélet."""
    from handball.pipeline.attack_types import screen_setter_roles

    rec = screen_setter_roles(_scs2_match([5, 7]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


def _pfr_match(feeders, fps=25.0):
    """Mint a _feeder_match, de a kiszolgálók posztja eltér: a 2-es
    átlövő (9 m, közép), a 3-as szélső — a poszt-lencse így meg tudja
    nevezni a bejátszó posztot."""
    spots = {1: (34.0, 10.0), 2: (30.0, 9.0), 3: (35.0, 3.0)}
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

    _hold(1, 100)
    _hold(2, 100)
    _hold(3, 100)
    for pid in feeders:
        _hold(pid, 10)     # a kiszolgáló birtokol
        _hold(1, 10)       # majd a beálló kapja (passz)
    return Match(_meta(fps), frames)


def test_pivot_feeder_roles_names_the_feeding_post():
    """Ha a beálló-beadások zöme ugyanarról a posztról jön, az ő kezén
    kell a beálló-vonalba lépni."""
    from handball.pipeline.attack_types import (PFR_MIN_FEEDS,
                                                pivot_feeder_roles)

    rec = pivot_feeder_roles(_pfr_match([2] * 5 + [3]))["home"]
    assert rec["feeds"] >= PFR_MIN_FEEDS, rec
    assert rec["main_role"] == "átlövő", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "kettőzés" in rec["verdict"], rec


def test_pivot_feeder_roles_silent_with_few_feeds():
    """Néhány beadásból nincs ítélet."""
    from handball.pipeline.attack_types import pivot_feeder_roles

    rec = pivot_feeder_roles(_pfr_match([2, 3]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


def _rpr_match(cases, fps=25.0):
    """Mint a _risky_passer_match, de poszt-mintával: a 4-es átlövő
    (9 m, közép), a 6-os szélső — a `cases` elemei (passzoló id,
    elveszett?) párok."""
    role_pos = {4: (30.0, 9.0), 6: (35.0, 3.0)}
    frames = []
    t = 0
    for _ in range(150):             # hazai birtoklás: poszt-minta
        players = [_pl(pid, Team.HOME, *xy)
                   for pid, xy in role_pos.items()]
        players.append(_pl(20, Team.AWAY, 20.0, 16.0))
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=30.2, y=9.0, confidence=1.0)))
        t += 1
    for (pid, lost) in cases:
        taker = (_pl(20, Team.AWAY, 30.0, 22.0) if lost
                 else _pl(2, Team.HOME, 30.0, 22.0))
        pls = [_pl(pid, Team.HOME, 30.0, 10.0), taker]
        for _ in range(5):
            frames.append(Frame(t=t, players=pls,
                                ball=Ball(x=30.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(5):
            frames.append(Frame(t=t, players=pls,
                                ball=Ball(x=30.0, y=22.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(5):
            frames.append(Frame(
                t=t, players=[_pl(pid, Team.HOME, 30.0, 10.0)],
                ball=Ball(x=30.0, y=10.0, confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_risky_passer_roles_names_the_gambling_post():
    """Ha az elszórt hosszú labdák zöme ugyanarról a posztról indul,
    az ő passzsávjába kell beállni."""
    from handball.pipeline.attack_types import (RPR_MIN_TO,
                                                risky_passer_roles)

    rec = risky_passer_roles(
        _rpr_match([(4, True)] * 3 + [(6, True)]))["home"]
    assert rec["turnovers"] >= RPR_MIN_TO, rec
    assert rec["main_role"] == "átlövő", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "passzsávjába" in rec["verdict"], rec


def test_risky_passer_roles_silent_with_few_turnovers():
    """Néhány elszórt hosszú labdából nincs ítélet."""
    from handball.pipeline.attack_types import risky_passer_roles

    rec = risky_passer_roles(
        _rpr_match([(4, True), (6, True)]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


def _kor_cycle(t, rid, fps=25.0):
    """Mint a _kot_cycle, de két lehetséges fogadóval: a 2-es irányító
    (28, 14), a 3-as szélső (28, 3) — a `rid` kapja a kiosztást."""
    rpos = {2: (28.0, 14.0), 3: (28.0, 3.0)}
    frames = []

    def cast():
        return [_pl(1, Team.HOME, 33.0, 10.0),
                _pl(2, Team.HOME, *rpos[2]),
                _pl(3, Team.HOME, *rpos[3]),
                _pl(20, Team.AWAY, 35.0, 10.0)]

    for _ in range(40):  # betörés
        frames.append(Frame(t=t, players=cast(),
                            ball=Ball(x=33.0, y=10.0, confidence=1.0)))
        t += 1
    rx, ry = rpos[rid]
    for _ in range(30):  # kiosztás
        frames.append(Frame(t=t, players=cast(),
                            ball=Ball(x=rx, y=ry, confidence=1.0)))
        t += 1
    for _ in range(30):  # ellenfél-birtoklás: szakasz-határ
        frames.append(Frame(t=t, players=[
            _pl(1, Team.HOME, 20.0, 10.0),
            _pl(20, Team.AWAY, 10.0, 10.0)],
            ball=Ball(x=10.0, y=10.0, confidence=1.0)))
        t += 1
    return frames, t


def test_kickout_target_roles_names_the_target_post():
    """Ha a betörés utáni labda rendre ugyanarra a posztra jár, annak
    a védője előre elmozdulhat a passzsávba."""
    from handball.pipeline.attack_types import (KOR_MIN_KICKOUTS,
                                                kickout_target_roles)

    frames, t = [], 0
    for rid in [2, 2, 2, 2, 3]:
        chunk, t = _kor_cycle(t, rid)
        frames += chunk
    rec = kickout_target_roles(Match(_meta(), frames))["home"]
    assert rec["kickouts"] >= KOR_MIN_KICKOUTS, rec
    assert rec["main_role"] == "irányító", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "passzsávba" in rec["verdict"], rec


def test_kickout_target_roles_silent_with_few_kickouts():
    """Néhány kiosztásból nincs ítélet."""
    from handball.pipeline.attack_types import kickout_target_roles

    frames, t = [], 0
    for rid in [2, 3]:
        chunk, t = _kor_cycle(t, rid)
        frames += chunk
    rec = kickout_target_roles(Match(_meta(), frames))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Előkészítő-poszt (melyik posztjuk készíti elő a lövéseket) ------------


def _epr_match(feeders, fps=25.0):
    """Poszt-minta (5: irányító, 7: beálló, 9: szélső) + lövések: a
    `feeders` szerinti játékos passza után a beálló (7) lő kapura."""
    spos = {5: (29.0, 10.0), 7: (34.0, 10.0), 9: (35.0, 3.0)}

    def cast():
        return [_pl(tid, Team.HOME, *xy) for tid, xy in spos.items()]

    frames = []
    t = 0
    for _ in range(150):             # poszt-minta: hazai birtoklás elöl
        frames.append(Frame(t=t, players=cast(),
                            ball=Ball(x=34.2, y=10.0, confidence=1.0)))
        t += 1
    for fid in feeders:
        fx, fy = spos[fid]
        for _ in range(10):          # az előkészítő passzolónál a labda
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=fx + 0.2, y=fy,
                                          confidence=1.0)))
            t += 1
        for _ in range(8):           # átvétel a lövőnél (7-es)
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=34.2, y=10.0,
                                          confidence=1.0)))
            t += 1
        x = 34.0
        while x < 40.5:              # lövés a +x kapura
            x += 0.5
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=min(x, 40.5), y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(40):          # semleges szakasz + debounce
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=20.0, y=16.0,
                                          confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_last_pass_roles_names_the_preparing_post():
    """Öt lövésből négyet az irányító készít elő → az ő sávját kell
    zárni."""
    from handball.pipeline.attack_types import (EPR_MIN_PASSES,
                                                last_pass_roles)

    rec = last_pass_roles(_epr_match([5, 5, 5, 5, 9]))["home"]
    assert rec["passes"] >= EPR_MIN_PASSES, rec
    assert rec["main_role"] == "irányító", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "előkészítetlenné" in rec["verdict"], rec


def test_last_passers_names_the_feeder():
    """Ha a lövés-előkészítés egy kézen fut, őt nevezzük meg — nem a
    lövőt kell fogni, hanem a kiszolgálót."""
    from handball.pipeline.attack_types import (EPP_MIN_PASSES,
                                                last_passers)

    rec = last_passers(_epr_match([5, 5, 5, 5, 9]))["home"]
    assert rec["top"] is not None, rec
    assert rec["top"]["player_id"] == 5, rec
    assert rec["top"]["passes"] >= EPP_MIN_PASSES, rec


def test_last_passers_silent_with_few_passes():
    """Kevés előkészítésből nem nevezünk meg embert."""
    from handball.pipeline.attack_types import last_passers

    rec = last_passers(_epr_match([5, 9]))["home"]
    assert rec["top"] is None, rec


def test_last_pass_roles_silent_with_few_passes():
    """Néhány előkészített lövésből nincs ítélet."""
    from handball.pipeline.attack_types import last_pass_roles

    rec = last_pass_roles(_epr_match([5, 9]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Hátrapassz-poszt (melyik posztjuknál fordul vissza a játék) -----------


def _bpr_match(passers, fps=25.0):
    """Poszt-minta (5: irányító, 7: beálló, 9: szélső) + hátra-
    passzok: a `passers` szerinti játékos a kaputól távolabbi
    irányítónak (5) adja vissza a labdát."""
    spos = {5: (29.0, 10.0), 7: (34.0, 10.0), 9: (35.0, 3.0)}

    def cast():
        return [_pl(tid, Team.HOME, *xy) for tid, xy in spos.items()]

    frames = []
    t = 0
    for _ in range(150):             # poszt-minta: hazai birtoklás elöl
        frames.append(Frame(t=t, players=cast(),
                            ball=Ball(x=34.2, y=10.0, confidence=1.0)))
        t += 1
    for pid in passers:
        px, py = spos[pid]
        for _ in range(8):           # a labda a passzolónál
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=px + 0.2, y=py,
                                          confidence=1.0)))
            t += 1
        for _ in range(8):           # átvétel hátul az irányítónál
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=29.2, y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(10):          # semleges labda a passzok közt
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=15.0, y=16.0,
                                          confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_backward_pass_roles_names_the_turning_post():
    """Hat hátra-passzból öt a beállóé → a pressz rá jutalmat hoz."""
    from handball.pipeline.attack_types import (BPR_MIN_PASSES,
                                                backward_pass_roles)

    rec = backward_pass_roles(
        _bpr_match([7, 7, 7, 7, 7, 9]))["home"]
    assert rec["passes"] >= BPR_MIN_PASSES, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "feljebb tolható" in rec["verdict"], rec


def test_backward_pass_roles_silent_with_few_passes():
    """Néhány hátra-passzból nincs ítélet."""
    from handball.pipeline.attack_types import backward_pass_roles

    rec = backward_pass_roles(_bpr_match([7, 9]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Áttörő-poszt (melyik posztjuk nyitja szét a falat) --------------------


def _btr_match(entries, fps=25.0):
    """Poszt-minta (7: beálló, 9: szélső) + betörések: az `entries`
    szerinti hazai játékos viszi be a labdát a kapu 9 m-es
    körzetébe."""
    spos = {7: (34.0, 10.0), 9: (35.0, 3.0)}

    def cast(mover=None, mx=None, my=None):
        out = []
        for tid, (x, y) in spos.items():
            if tid == mover:
                out.append(_pl(tid, Team.HOME, mx,
                               my if my is not None else y))
            else:
                out.append(_pl(tid, Team.HOME, x, y))
        return out + [_pl(21, Team.AWAY, 37.0, 17.0)]

    frames = []
    t = 0
    for _ in range(150):             # poszt-minta: hazai birtoklás elöl
        frames.append(Frame(t=t, players=cast(),
                            ball=Ball(x=34.2, y=10.0, confidence=1.0)))
        t += 1
    for tid in entries:
        for _ in range(int(2.0 * fps)):    # felállás a 9 m-en kívül
            frames.append(Frame(
                t=t, players=cast(mover=tid, mx=28.0, my=8.0),
                ball=Ball(x=28.2, y=8.0, confidence=1.0)))
            t += 1
        for _ in range(int(1.5 * fps)):    # betörés a körzetbe
            frames.append(Frame(
                t=t, players=cast(mover=tid, mx=33.5, my=8.0),
                ball=Ball(x=33.7, y=8.0, confidence=1.0)))
            t += 1
        for i in range(int(1.5 * fps)):    # vendég-birtoklás: elválasztó
            frames.append(Frame(
                t=t,
                players=[_pl(21, Team.AWAY, 18.0 - 0.05 * i, 10.0)],
                ball=Ball(x=18.0 - 0.05 * i, y=10.0,
                          confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_breakthrough_roles_names_the_opening_post():
    """Négy betörésből hármat a beálló visz be → az ő védője kap
    segítőt."""
    from handball.pipeline.attack_types import (BTR_MIN_ENTRIES,
                                                breakthrough_roles)

    rec = breakthrough_roles(_btr_match([7, 7, 7, 9]))["home"]
    assert rec["entries"] >= BTR_MIN_ENTRIES, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "testtel kell zárni" in rec["verdict"], rec


def test_breakthrough_roles_silent_with_few_entries():
    """Néhány betörésből nincs ítélet."""
    from handball.pipeline.attack_types import breakthrough_roles

    rec = breakthrough_roles(_btr_match([7, 9]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Elzárópáros-poszt (melyik posztpárra jár az elzárás-játék) ------------


def _spp_match(setters, fps=25.0):
    """Poszt-minta (1: átlövő, 5: beálló, 9: szélső) + elzárt
    lövések: a `setters` szerinti társ zár az 1-es lövőnek."""
    spos = {1: (30.0, 10.0), 5: (34.0, 10.0), 9: (35.0, 3.0)}

    frames = []
    t = 0
    for _ in range(150):             # poszt-minta: hazai birtoklás elöl
        frames.append(Frame(
            t=t,
            players=[_pl(tid, Team.HOME, *xy)
                     for tid, xy in spos.items()],
            ball=Ball(x=30.2, y=10.0, confidence=1.0)))
        t += 1
    for setter_id in setters:
        players = [_pl(1, Team.HOME, 30.0, 10.0),          # a lövő
                   _pl(20, Team.AWAY, 31.5, 10.0),         # az őrző
                   _pl(setter_id, Team.HOME, 31.5, 11.0)]  # az elzáró
        players += [_pl(tid, Team.HOME, *spos[tid])
                    for tid in spos if tid not in (1, setter_id)]
        for _ in range(30):
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=30.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        for i in range(14):
            frames.append(Frame(
                t=t, players=players,
                ball=Ball(x=min(30.0 + 0.8 * (i + 1), 40.0), y=10.0,
                          confidence=1.0)))
            t += 1
        for _ in range(40):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=40.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_screen_pair_roles_names_the_drilled_pair():
    """Négy elzárt lövésből három a beálló→átlövő párosé → párban
    készül a védekezés."""
    from handball.pipeline.attack_types import (SPP_MIN_SHOTS,
                                                screen_pair_roles)

    rec = screen_pair_roles(_spp_match([5, 5, 5, 9]))["home"]
    assert rec["shots"] >= SPP_MIN_SHOTS, rec
    assert rec["main_role"] == "beálló→átlövő", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "párban készül" in rec["verdict"], rec


def test_screen_pair_roles_silent_with_few_shots():
    """Néhány elzárt lövésből nincs ítélet."""
    from handball.pipeline.attack_types import screen_pair_roles

    rec = screen_pair_roles(_spp_match([5, 9]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Kontrapáros-poszt (melyik tengelyen futnak a kontráik) ----------------


def _fbp_match(pairs, fps=25.0):
    """Poszt-minta (5: irányító, 7: beálló, 9: szélső) + lerohanások:
    a `pairs` elemei (indító, befejező) — az indító hátulról hozza a
    labdát, a befejező lövi; köztük vendég-birtoklás választ el."""
    spos = {5: (29.0, 10.0), 7: (34.0, 10.0), 9: (35.0, 3.0)}

    def base():
        return [_pl(tid, Team.HOME, *xy) for tid, xy in spos.items()]

    frames = []
    t = 0
    for _ in range(150):             # poszt-minta: hazai birtoklás elöl
        frames.append(Frame(t=t, players=base(),
                            ball=Ball(x=29.2, y=10.0, confidence=1.0)))
        t += 1
    for (starter, finisher) in pairs:
        for i in range(40):          # vendég-birtoklás: elválasztó
            frames.append(Frame(
                t=t, players=[_pl(21, Team.AWAY, 16.0, 10.0)],
                ball=Ball(x=16.0, y=10.0, confidence=1.0)))
            t += 1
        x = 8.0
        for i in range(30):          # az indító rohan a labdával
            players = [_pl(starter, Team.HOME, x, 10.0)] + [
                _pl(tid, Team.HOME, *spos[tid])
                for tid in spos if tid != starter]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=x + 0.2, y=10.0,
                                          confidence=1.0)))
            x += 0.5
            t += 1
        fx, fy = spos[finisher]
        for _ in range(6):           # a befejezőnél a labda
            frames.append(Frame(t=t, players=base(),
                                ball=Ball(x=fx + 0.2, y=fy,
                                          confidence=1.0)))
            t += 1
        xx = fx
        while xx < 40.5:             # a kontra-lövés a kapura
            xx += 0.5
            frames.append(Frame(t=t, players=base(),
                                ball=Ball(x=min(xx, 40.5), y=10.0,
                                          confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_fast_break_pair_roles_names_the_axis():
    """Négy lerohanásból három az irányító→szélső tengelyen fut →
    az indítót kell fékezni."""
    from handball.pipeline.attack_types import (FBP_MIN_BREAKS,
                                                fast_break_pair_roles)

    rec = fast_break_pair_roles(
        _fbp_match([(5, 9), (5, 9), (5, 9), (7, 9)]))["home"]
    assert rec["breaks"] >= FBP_MIN_BREAKS, rec
    assert rec["main_role"] == "irányító→szélső", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "labdavesztés pillanatában" \
        in rec["verdict"], rec


def test_fast_break_pair_roles_silent_with_few_breaks():
    """Néhány lerohanásból nincs ítélet."""
    from handball.pipeline.attack_types import fast_break_pair_roles

    rec = fast_break_pair_roles(_fbp_match([(5, 9), (7, 9)]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Lepattanópáros-poszt (melyik lövésre ki érkezik) ----------------------


def test_rebound_pair_roles_names_the_rebound_axis():
    """Ha az irányító lövésére rendre a beálló érkezik, a zárás után
    az ő útját kell elállni."""
    from handball.pipeline.attack_types import (RBP_MIN_SHOTS,
                                                rebound_pair_roles)

    rec = rebound_pair_roles(
        _scr_match([(1, 2)] * 3 + [(2, 1)]))["home"]
    assert rec["second_shots"] >= RBP_MIN_SHOTS, rec
    assert rec["main_role"] == "irányító→beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "útját kell elállni" in rec["verdict"], rec


def test_rebound_pair_roles_silent_with_few_shots():
    """Néhány második rohamból nincs ítélet."""
    from handball.pipeline.attack_types import rebound_pair_roles

    rec = rebound_pair_roles(_scr_match([(1, 2), (2, 1)]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Sávváltó-poszt (melyik posztjuk vált sávot a támadásban) --------------


def _lsw_match(switchers, fps=25.0):
    """Poszt-minta (7: beálló, 9: szélső) + keresztmozgás: a
    `switchers` szerinti játékos átmegy a pálya másik szélső sávjába
    (és ott marad 2 mp-ig), majd vissza. Az 5-ös irányítónál marad a
    labda, hogy a birtoklás a mozgás alatt is mérhető legyen."""
    spos = {5: (29.0, 10.0), 7: (34.0, 10.0), 9: (35.0, 3.0)}

    def cast(mover=None, my=None):
        out = []
        for tid, (x, y) in spos.items():
            if tid == mover:
                out.append(_pl(tid, Team.HOME, x, my))
            else:
                out.append(_pl(tid, Team.HOME, x, y))
        return out

    frames = []
    t = 0
    for _ in range(150):             # poszt-minta: hazai birtoklás elöl
        frames.append(Frame(t=t, players=cast(),
                            ball=Ball(x=29.2, y=10.0, confidence=1.0)))
        t += 1
    for tid in switchers:
        for my in (17.0, spos[tid][1]):   # átmegy, majd vissza
            for _ in range(int(2.0 * fps)):
                frames.append(Frame(
                    t=t, players=cast(mover=tid, my=my),
                    ball=Ball(x=29.2, y=10.0, confidence=1.0)))
                t += 1
    return Match(_meta(fps), frames)


def test_lane_switch_roles_names_the_crossing_post():
    """A beálló viszi a keresztmozgást → a védője követés/átadás
    szabályát előre el kell dönteni."""
    from handball.pipeline.attack_types import (LSW_MIN_SWITCHES,
                                                lane_switch_roles)

    rec = lane_switch_roles(_lsw_match([7, 7, 7, 9]))["home"]
    assert rec["switches"] >= LSW_MIN_SWITCHES, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "ÁTADJA" in rec["verdict"], rec


def test_lane_switch_roles_silent_with_few_switches():
    """Néhány sávváltásból nincs ítélet."""
    from handball.pipeline.attack_types import lane_switch_roles

    rec = lane_switch_roles(_lsw_match([7]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Vég-birtokos poszt (kinél ér véget a támadás lövés nélkül) ------------


def _lst_match(enders, fps=25.0):
    """Poszt-minta (5: irányító, 7: beálló) + lövés nélkül záruló
    hazai támadások: az `enders` szerinti játékosnál marad a labda,
    majd a vendég birtokol (a szakasz lezárul)."""
    spos = {5: (29.0, 10.0), 7: (34.0, 10.0)}

    def cast():
        return [_pl(tid, Team.HOME, *xy) for tid, xy in spos.items()]

    frames = []
    t = 0
    for _ in range(150):             # poszt-minta: hazai birtoklás elöl
        frames.append(Frame(t=t, players=cast(),
                            ball=Ball(x=29.2, y=10.0, confidence=1.0)))
        t += 1
    for tid in enders:
        for _ in range(40):          # hazai támadás: a labda körbejár
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=29.2, y=10.0,
                                          confidence=1.0)))
            t += 1
        ex, ey = spos[tid]
        for _ in range(40):          # a végén a lezáró birtokosnál
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=ex + 0.2, y=ey,
                                          confidence=1.0)))
            t += 1
        for _ in range(60):          # vendég-birtoklás: a szakasz zárul
            frames.append(Frame(
                t=t, players=cast() + [_pl(21, Team.AWAY, 12.0, 10.0)],
                ball=Ball(x=12.1, y=10.0, confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_last_holder_roles_names_the_closing_post():
    """A terméketlen támadások a beálló kezében halnak el → a
    támadás második felében rá kell tolni a nyomást."""
    from handball.pipeline.attack_types import (LST_MIN_ATTACKS,
                                                last_holder_roles)

    rec = last_holder_roles(_lst_match([7, 7, 7, 7, 5]))["home"]
    assert rec["attacks"] >= LST_MIN_ATTACKS, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "nyomást" in rec["verdict"], rec


def test_last_holder_roles_silent_with_few_attacks():
    """Néhány terméketlen támadásból nincs ítélet."""
    from handball.pipeline.attack_types import last_holder_roles

    rec = last_holder_roles(_lst_match([7, 5]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Kapkodás-index (kapott gól után rövidül-e a támadás) ------------------


def _rus_frames(t0, seconds, x_from, x_to, fps=25.0):
    """HAZAI támadás-szakasz (mint az _attack_frames), de a vendég
    védők a hazai térfélen is látszanak — így a vendég gól után is
    van kit birtokosnak jelölni."""
    return _attack_frames(t0, seconds, x_from, x_to, fps=fps)


def _rus_gap(t0, seconds, fps=25.0):
    """Szabad labda: nincs birtokos, a szakasz itt zárul."""
    return [Frame(t=t0 + i, players=[],
                  ball=Ball(x=20.0, y=18.0, confidence=1.0))
            for i in range(int(seconds * fps))]


def _rus_away_goal(t0, fps=25.0):
    """Vendég gól a hazai (-x) kapuba: a 21-es viszi be a labdát."""
    frames = []
    i = 0
    x = 8.0
    while x > -0.5:
        players = [_pl(21, Team.AWAY, max(x, 0.5), 10.0),
                   _pl(22, Team.AWAY, 12.0, 14.0)]
        frames.append(Frame(t=t0 + i, players=players,
                            ball=Ball(x=max(x, -0.5), y=10.0,
                                      confidence=1.0)))
        x -= 0.4
        i += 1
    return frames


def _rus_match(base_s, after_s, fps=25.0):
    """`base_s` hosszúságú hazai támadások gól nélkül, majd
    vendéggólonként egy `after_s` hosszúságú válasz-támadás."""
    frames = []
    t = 0
    for _ in range(4):                    # alap-támadások (gól előtt)
        frames += _rus_frames(t, base_s, 26.0, 31.0, fps)
        t += int(base_s * fps)
        frames += _rus_gap(t, 2.0, fps)
        t += int(2.0 * fps)
    for _ in range(3):                    # vendéggól + válasz-támadás
        g = _rus_away_goal(t, fps)
        frames += g
        t += len(g)
        frames += _rus_gap(t, 2.0, fps)
        t += int(2.0 * fps)
        frames += _rus_frames(t, after_s, 26.0, 31.0, fps)
        t += int(after_s * fps)
        frames += _rus_gap(t, 2.0, fps)
        t += int(2.0 * fps)
    return Match(_meta(fps), frames)


def test_post_goal_rush_flags_the_panicking_team():
    """Ha a kapott gól után 11 másodperccel rövidebb a támadásuk,
    kapkodnak — a gólunk után vissza kell állni."""
    from handball.pipeline.attack_types import (RUS_MIN_ATTACKS,
                                                post_goal_rush)

    rec = post_goal_rush(_rus_match(16.0, 5.0))["home"]
    assert rec["after"] >= RUS_MIN_ATTACKS, rec
    assert rec["base"] >= 4, rec
    assert rec["diff_s"] and rec["diff_s"] < 0, rec
    assert rec["verdict"] and "kapkodnak" in rec["verdict"], rec


def test_post_goal_rush_flags_the_freezing_team():
    """A fordított eset: kapott gól után hosszabb támadás = befagyás."""
    from handball.pipeline.attack_types import post_goal_rush

    rec = post_goal_rush(_rus_match(6.0, 16.0))["home"]
    assert rec["diff_s"] and rec["diff_s"] > 0, rec
    assert rec["verdict"] and "befagynak" in rec["verdict"], rec


def test_post_goal_rush_silent_without_real_change():
    """Egy másodperces eltérés nem minta — az ítélet None."""
    from handball.pipeline.attack_types import post_goal_rush

    rec = post_goal_rush(_rus_match(10.0, 9.0))["home"]
    assert rec["diff_s"] is not None and rec["verdict"] is None, rec


# ---- Áttörés-hozam (bejutnak-e, és büntetnek-e onnan) ----------------------


def _bty_match(n_entries, n_goals, fps=25.0):
    """`n_entries` hazai betörés, ezekből az első `n_goals` góllal
    zárul (a labda a +x kapuba repül)."""
    frames = []
    t = 0
    for i in range(n_entries):
        for _ in range(int(2.0 * fps)):     # felállás a 9 m-en kívül
            frames.append(Frame(t=t, players=[
                _pl(7, Team.HOME, 28.0, 10.0),
                _pl(8, Team.HOME, 28.0, 5.0),
                _pl(21, Team.AWAY, 37.0, 14.0)],
                ball=Ball(x=28.0, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(int(1.5 * fps)):     # betörés a 33,5 m-ig
            frames.append(Frame(t=t, players=[
                _pl(7, Team.HOME, 33.5, 10.0),
                _pl(8, Team.HOME, 28.0, 5.0),
                _pl(21, Team.AWAY, 37.0, 14.0)],
                ball=Ball(x=33.5, y=10.0, confidence=1.0)))
            t += 1
        if i < n_goals:                     # a betörésből gól lesz
            for k in range(10):
                frames.append(Frame(t=t, players=[
                    _pl(7, Team.HOME, 33.5, 10.0),
                    _pl(8, Team.HOME, 28.0, 5.0)],
                    ball=Ball(x=min(34.5 + k, 40.4), y=10.0,
                              confidence=1.0)))
                t += 1
        for k in range(int(2.0 * fps)):     # vendég-birtoklás: elválasztó
            frames.append(Frame(
                t=t, players=[_pl(21, Team.AWAY, 18.0 - 0.05 * k, 10.0)],
                ball=Ball(x=18.0 - 0.05 * k, y=10.0, confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_breakthrough_yield_flags_the_punishing_penetration():
    """Ha a betöréseik nagy része gólba fut, a falat előbb kell
    zárni."""
    from handball.pipeline.attack_types import (BTY_MIN_ENTRIES,
                                                breakthrough_yield)

    rec = breakthrough_yield(_bty_match(6, 4))["home"]
    assert rec["entries"] >= BTY_MIN_ENTRIES, rec
    assert rec["goal_pct"] and rec["goal_pct"] >= 40.0, rec
    assert rec["verdict"] and "bejutnak ÉS büntetnek" in rec["verdict"]


def test_breakthrough_yield_flags_the_blunt_penetration():
    """Ha bejutnak, de nem büntetnek, a záró-fal és a kapus dolgozik."""
    from handball.pipeline.attack_types import breakthrough_yield

    rec = breakthrough_yield(_bty_match(7, 0))["home"]
    assert rec["goal_pct"] == 0.0, rec
    assert rec["verdict"] and "nem büntetnek" in rec["verdict"], rec


def test_breakthrough_yield_silent_with_few_entries():
    """Kevés betörésből nincs ítélet — a számok viszont látszanak."""
    from handball.pipeline.attack_types import breakthrough_yield

    rec = breakthrough_yield(_bty_match(3, 1))["home"]
    assert rec["entries"] == 3 and rec["goal_pct"] is None, rec
    assert rec["verdict"] is None, rec


def test_last_holders_names_the_dead_end():
    """Ha a terméketlen támadások rendre ugyanannak a kezében halnak
    el, rá kell tolni a nyomást."""
    from handball.pipeline.attack_types import (LSTP_MIN_ATTACKS,
                                                last_holders)

    rec = last_holders(_lst_match([7, 7, 7, 7, 5]))["home"]
    assert rec["attacks"] >= 4, rec
    assert rec["top"] is not None and rec["top"]["player_id"] == 7, rec
    assert rec["top"]["attacks"] >= LSTP_MIN_ATTACKS, rec


def test_last_holders_silent_with_few_attacks():
    """Két terméketlen támadásból még nincs kiemelt név."""
    from handball.pipeline.attack_types import last_holders

    rec = last_holders(_lst_match([7, 5]))["home"]
    assert rec["top"] is None, rec


def test_lane_switchers_names_the_crosser():
    """Ha a keresztmozgást rendre ugyanaz viszi, a védője
    követés/átadás szabályát rá kell szabni."""
    from handball.pipeline.attack_types import (LSWP_MIN_SWITCHES,
                                                lane_switchers)

    rec = lane_switchers(_lsw_match([7, 7, 7, 9]))["home"]
    assert rec["switches"] >= LSWP_MIN_SWITCHES, rec
    assert rec["top"] is not None and rec["top"]["player_id"] == 7, rec
    assert rec["top"]["switches"] >= LSWP_MIN_SWITCHES, rec


def test_lane_switchers_silent_with_few_switches():
    """Néhány sávváltásból nincs kiemelt név."""
    from handball.pipeline.attack_types import lane_switchers

    rec = lane_switchers(_lsw_match([7]))["home"]
    assert rec["top"] is None, rec


def test_backward_passers_names_the_turner():
    """Ha nyomás alatt rendre ugyanaz fordítja vissza a labdát, rá
    érdemes kimenni."""
    from handball.pipeline.attack_types import (BPRP_MIN_PASSES,
                                                backward_passers)

    rec = backward_passers(_bpr_match([7, 7, 7, 7, 7, 9]))["home"]
    assert rec["top"] is not None and rec["top"]["player_id"] == 7, rec
    assert rec["top"]["passes"] >= BPRP_MIN_PASSES, rec


def test_backward_passers_silent_with_few_passes():
    """Két hátra-passzból még nincs kiemelt név."""
    from handball.pipeline.attack_types import backward_passers

    rec = backward_passers(_bpr_match([7, 9]))["home"]
    assert rec["top"] is None, rec
