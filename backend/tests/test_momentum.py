"""
Tesztek a gól-sorozat (momentum) felismerésre (momentum.py).

A pálya 40x20 m; a HAZAI a +x (x=40) kapu felé támad.

Futtatás:
    python -m pytest tests/test_momentum.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.momentum import scoring_runs


def _meta(fps=25.0):
    return MatchMeta(match_id="mo", home_team="H", away_team="A", fps=fps)


def _goal(t0, toward_home_goal=False):
    """Egy gól-esemény kockái: a labda gyorsan a kapuvonalig (kapufák között).
    toward_home_goal=False → a +x (x=40) kapu → HAZAI gól."""
    frames = []
    for i in range(8):
        if toward_home_goal:
            x = max(6.4 - i, 0.0)          # a -x (x=0) kapu felé → VENDÉG gól
        else:
            x = min(33.6 + i, 40.0)        # a +x (x=40) kapu felé → HAZAI gól
        frames.append(Frame(t=t0 + i, players=[], ball=Ball(x=x, y=10.0,
                                                            confidence=1.0)))
    return frames


def _match_from_goals(sequence):
    """sequence: 'H'/'A' betűk időrendben; egyenletesen elosztott gólok."""
    frames = []
    t = 0
    gap = 20  # kockányi szünet a gólok között (a debounce miatt kell)
    for ch in sequence:
        frames += _goal(t, toward_home_goal=(ch == "A"))
        t += 8
        frames.append(Frame(t=t, players=[], ball=Ball(x=20.0, y=10.0,
                                                       confidence=1.0)))
        t += gap
    return Match(_meta(), frames)


def test_detects_unanswered_run():
    """HHHH majd A: a hazai 4-gólos sorozata jelenik meg."""
    m = _match_from_goals("HHHHA")
    runs = scoring_runs(m)
    assert len(runs) == 1
    r = runs[0]
    assert r["team"] == "home" and r["length"] == 4
    assert r["score_before"] == [0, 0]
    assert r["score_after"] == [4, 0]


def test_short_runs_ignored():
    """Váltakozó gólok (max 2 egymás után) → nincs sorozat (küszöb 3)."""
    m = _match_from_goals("HHAAHA")
    assert scoring_runs(m) == []


def test_two_runs_with_scores():
    """HHH ... AAAA: két sorozat, helyes állással a másodiknál."""
    m = _match_from_goals("HHHAAAA")
    runs = scoring_runs(m)
    assert len(runs) == 2
    assert runs[0]["team"] == "home" and runs[0]["length"] == 3
    assert runs[1]["team"] == "away" and runs[1]["length"] == 4
    # A vendég-sorozat a 3-0-s hazai állásból indult, 3-4-re fordítva.
    assert runs[1]["score_before"] == [3, 0]
    assert runs[1]["score_after"] == [3, 4]


def test_min_len_parameter():
    """A küszöb állítható: min_len=2-nél a 2-es sorozat is bekerül."""
    m = _match_from_goals("HHA")
    assert scoring_runs(m, min_len=2)[0]["length"] == 2


def test_no_goals_no_runs():
    m = Match(_meta(), [Frame(t=t, players=[], ball=None) for t in range(20)])
    assert scoring_runs(m) == []


# ---- annotate_runs: a sorozatok LEHETSÉGES OKAI ------------------------------

from handball.pipeline.momentum import annotate_runs  # noqa: E402


def _pl(track_id, team, x, y):
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0)


def test_annotate_no_signals_gives_empty_context():
    """Jelek nélküli sorozat: a context üres lista (nem hiányzó kulcs)."""
    m = _match_from_goals("HHHH")
    runs = annotate_runs(m)
    assert len(runs) == 1
    assert runs[0]["context"] == []
    # A meglévő mezők változatlanok maradnak.
    assert runs[0]["team"] == "home" and runs[0]["length"] == 4


def test_annotate_powerplay_overlap_labeled():
    """A vendég 3 gólos sorozata HAZAI emberhátrány alatt → "emberelőnyben"."""
    fps = 25.0
    # 100 mp folyamatos felvétel: 5 hazai vs 6 vendég mezőnyjátékos
    # (kiállítás-lenyomat), közben a vendég 3 gólt dob a -x (x=0) kapura.
    goal_starts = {1000, 1400, 1800}
    frames = []
    for t in range(int(100 * fps)):
        players = [_pl(100 + k, Team.HOME, 12.0 + k, 4.0 + k) for k in range(5)]
        players += [_pl(200 + k, Team.AWAY, 24.0 + k, 4.0 + k) for k in range(6)]
        gs = next((g for g in goal_starts if g <= t < g + 8), None)
        if gs is not None:
            ball = Ball(x=max(6.4 - (t - gs), 0.0), y=10.0, confidence=1.0)
        else:
            ball = Ball(x=20.0, y=10.0, confidence=1.0)
        frames.append(Frame(t=t, players=players, ball=ball))
    m = Match(_meta(fps), frames)
    runs = annotate_runs(m)
    assert len(runs) == 1
    assert runs[0]["team"] == "away" and runs[0]["length"] == 3
    assert "emberelőnyben" in runs[0]["context"]


def test_annotate_accepts_precomputed_runs():
    """Előre kiszámolt sorozat-listát is elfogad (nem számol duplán)."""
    m = _match_from_goals("AAA")
    runs = scoring_runs(m)
    out = annotate_runs(m, runs=runs)
    assert out is runs and all("context" in r for r in out)


# ---- Új kontextus-jelek: időkérés + cserehullám ------------------------------

import math as _math


def _squad(t, moving=True, exclude=()):
    """8 mezőnyjátékos (4-4), mozgásban vagy állva — az időkérés-jelhez."""
    out = []
    for k in range(8):
        if (k + 1) in exclude:
            continue
        team = Team.HOME if k < 4 else Team.AWAY
        bx, by = 12.0 + 2.0 * k, 6.0 + (k % 4) * 2.5
        if moving:
            bx += 2.0 * _math.sin(t / 5.0 + k)
            by += 1.5 * _math.cos(t / 4.0 + k)
        out.append(PlayerPosition(track_id=k + 1, team=team, x=bx, y=by,
                                  source=PositionSource.MEASURED,
                                  confidence=1.0))
    return out


def test_run_despite_opponent_timeout():
    """A hazai széria közben a vendég időt kér, de a sorozat utána is
    folytatódik → "az ellenfél időkérése ellenére" címke."""
    frames = []
    t = 0

    def moving(sec, away_holds=False):
        nonlocal t
        for _ in range(int(sec * 25)):
            players = _squad(t)
            if away_holds:  # a vendég 5-ös birtokol (ő "kéri" az időt)
                hp = players[4]
                ball = Ball(x=hp.x, y=hp.y, confidence=1.0)
            else:
                ball = Ball(x=20.0, y=10.0, confidence=1.0)
            frames.append(Frame(t=t, players=players, ball=ball))
            t += 1

    def goal():
        nonlocal t
        for i in range(7):
            frames.append(Frame(t=t, players=_squad(t),
                                ball=Ball(x=34.0 + i, y=10.0, confidence=1.0)))
            t += 1

    moving(4)
    goal()          # 1. hazai gól — a sorozat kezdete
    moving(3)
    goal()          # 2. gól
    moving(4, away_holds=True)   # a vendég birtokol az időkérés előtt
    for _ in range(int(20 * 25)):  # 20 mp állás = időkérés
        frames.append(Frame(t=t, players=_squad(0, moving=False), ball=None))
        t += 1
    moving(3)
    goal()          # 3. gól — a széria az időkérés UTÁN is megy
    moving(4)

    runs = annotate_runs(Match(_meta(), frames))
    assert len(runs) == 1 and runs[0]["length"] == 3
    assert "az ellenfél időkérése ellenére" in runs[0]["context"]


def test_run_after_substitution_wave():
    """A hazai a széria előtt cserehullámot futott → "cserehullám után"."""
    frames = []
    t = 0
    for _ in range(1000):
        players = _squad(t)
        if t <= 200:  # a 20-as track a cserezónába megy, ott tűnik el
            frac = t / 200.0
            players.append(PlayerPosition(
                track_id=20, team=Team.HOME,
                x=28.0 + (20.0 - 28.0) * frac, y=8.0 + (1.0 - 8.0) * frac,
                source=PositionSource.MEASURED, confidence=1.0))
        if t >= 210:  # a 21-es ott jelenik meg, majd beáll
            frac = min(1.0, (t - 210) / 100.0)
            players.append(PlayerPosition(
                track_id=21, team=Team.HOME,
                x=20.0 + (30.0 - 20.0) * frac, y=1.0 + (12.0 - 1.0) * frac,
                source=PositionSource.MEASURED, confidence=1.0))
        # Három hazai gól a csere után (t=300/380/460).
        ball = Ball(x=20.0, y=10.0, confidence=1.0)
        for g0 in (300, 380, 460):
            if g0 <= t < g0 + 7:
                ball = Ball(x=34.0 + (t - g0), y=10.0, confidence=1.0)
        frames.append(Frame(t=t, players=players, ball=ball))
        t += 1

    runs = annotate_runs(Match(_meta(), frames))
    assert len(runs) == 1 and runs[0]["team"] == "home"
    assert "cserehullám után" in runs[0]["context"]


# ---- Vezetés-alakulás (score_progression) ------------------------------------

from handball.pipeline.momentum import score_progression  # noqa: E402


def test_score_progression_lead_changes_and_biggest():
    """H, H, A, A, A → a hazai 2-0-ra vezet, majd a vendég fordít 2-3-ra:
    egy vezetés-váltás, a legnagyobb hazai előny 2, a vendégé 1."""
    m = _match_from_goals("HHAAA")
    p = score_progression(m)
    assert p["final"] == [2, 3]
    assert p["biggest_lead"]["home"] == 2
    assert p["biggest_lead"]["away"] == 1
    assert p["lead_changes"] == 1  # döntetlenen át a vendéghez fordult
    # A vezetés-idők összege a meccs hossza körüli (kerekítéssel).
    tot = sum(p["lead_time_s"].values())
    assert tot > 0


def test_score_progression_comeback():
    """A A A H H H H → a hazai 0-3-ról fordít 4-3-ra: comeback home=3.
    A vendég sosem fordított hátrányból (a végén hátrányban áll)."""
    m = _match_from_goals("AAAHHHH")
    p = score_progression(m)
    assert p["final"] == [4, 3]
    assert p["comeback"]["home"] == 3
    assert p["comeback"]["away"] == 0


def test_score_progression_no_comeback_when_never_led():
    """H A A A → a vendég döntetlenről vezet, a hazai hátrányból csak
    egyenlítésig sem jut: nincs fordítás egyik oldalon sem... a vendégnél
    az 1 gólos hátrányból (0-1) vezetésbe fordulás 1-es comeback."""
    p = score_progression(_match_from_goals("HAAA"))
    assert p["comeback"]["home"] == 0
    assert p["comeback"]["away"] == 1


def test_score_progression_no_goals():
    m = Match(_meta(), [Frame(t=i, players=[], ball=None) for i in range(10)])
    p = score_progression(m)
    assert p["final"] == [0, 0]
    assert p["lead_changes"] == 0
    assert p["biggest_lead"] == {"home": 0, "away": 0}


def test_clutch_performance_last_window():
    """20 perces felvétel: 1-1 gól az elején, a hajrában (utolsó 5 perc)
    2 hazai gól → close hajrá, hazai 2-0 hajrá-mérleg."""
    from handball.pipeline.momentum import clutch_performance
    fps = 25.0
    total = int(1200 * fps)  # 20 perc
    frames = {}
    def put(seq):
        for fr in seq:
            frames[fr.t] = fr
    put(_goal(100))                          # hazai gól az elején
    put(_goal(400, toward_home_goal=True))   # vendég gól
    win_start = total - int(300 * fps)
    put(_goal(win_start + 200))              # hajrá: hazai
    put(_goal(win_start + 1000))             # hajrá: hazai
    all_frames = [frames.get(t, Frame(t=t, players=[],
                                      ball=Ball(x=20.0, y=10.0,
                                                confidence=1.0)))
                  for t in range(total)]
    cp = clutch_performance(Match(_meta(), all_frames))
    assert cp["available"] is True
    assert cp["start_score"] == [1, 1] and cp["close"] is True
    assert cp["home"]["goals"] == 2 and cp["away"]["goals"] == 0


def test_clutch_unavailable_on_short_clip():
    from handball.pipeline.momentum import clutch_performance
    m = _match_from_goals("HHA")  # pár másodperces klip
    assert clutch_performance(m) == {"available": False}


def test_halftime_score_counts_first_half_goals():
    """H, A az 500. kocka előtt, H utána; half_t=500 → félidei állás 1-1."""
    from handball.pipeline.momentum import halftime_score
    frames = {}
    for fr in _goal(0) + _goal(100, toward_home_goal=True) + _goal(600):
        frames[fr.t] = fr
    total = 800
    all_frames = [frames.get(t, Frame(t=t, players=[],
                                      ball=Ball(x=20.0, y=10.0,
                                                confidence=1.0)))
                  for t in range(total)]
    hs = halftime_score(Match(_meta(), all_frames), half_t=500)
    assert hs == {"half_t": 500, "home": 1, "away": 1}
    # Felismert szünet nélkül (és half_t nélkül) nincs félidei állás.
    assert halftime_score(Match(_meta(), all_frames[:50])) is None


def test_win_probability_favors_leader_and_late_goals():
    """A vezető csapat esélye 0,5 fölött; UGYANAZ az 1 gólos előny a
    hajrában többet ér, mint az elején (két külön meccsen összevetve)."""
    from handball.pipeline.momentum import win_probability

    def one_goal_match(goal_t, total=6000):
        frames = {fr.t: fr for fr in _goal(goal_t)}
        return Match(_meta(), [
            frames.get(t, Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
            for t in range(total)
        ])

    early = win_probability(one_goal_match(100))     # gól a 4. mp-ben
    late = win_probability(one_goal_match(5800))     # gól a hajrában
    assert early["timeline"][0]["p_home"] == 0.5
    assert early["final_p_home"] > 0.5
    assert late["final_p_home"] > early["final_p_home"]

    # Fordulópont: két gól közül a nagyobb esély-ugrás pillanata.
    frames = {}
    for fr in _goal(100) + _goal(5800):
        frames[fr.t] = fr
    m = Match(_meta(), [
        frames.get(t, Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        for t in range(6000)
    ])
    wp = win_probability(m)
    assert wp["turning_point"] is not None
    assert len(wp["timeline"]) == 3


def test_goal_responses_measures_answer_time():
    """H A H A: a hazai az 'A' gólokra válaszol egyszer (a másodikra már
    nem jön H), a vendég a H gólokra kétszer."""
    from handball.pipeline.momentum import goal_responses
    frames = {}
    # H a 0-nál, A a 100-nál, H a 250-nél, A a 400-nál (25 fps).
    for fr in (_goal(0) + _goal(100, toward_home_goal=True) + _goal(250)
               + _goal(400, toward_home_goal=True)):
        frames[fr.t] = fr
    total = 600
    all_frames = [frames.get(t, Frame(t=t, players=[],
                                      ball=Ball(x=20.0, y=10.0,
                                                confidence=1.0)))
                  for t in range(total)]
    r = goal_responses(Match(_meta(), all_frames))
    # A hazai a 100-as kapott gólra a 250-es góllal válaszolt (~6 mp).
    assert r["home"]["responses"] == 1
    assert abs(r["home"]["avg_s"] - 6.0) < 1.0
    # A vendég a 0-s és a 250-es hazai gólra válaszolt (100, 400).
    assert r["away"]["responses"] == 2
    assert r["away"]["fastest_s"] is not None


def test_goal_droughts_longest_gap():
    """HH...H mintában a hazai leghosszabb gólcsendje a 2. és 3. hazai
    gól közti szakasz; a gól nélküli vendégé a teljes felvétel."""
    from handball.pipeline.momentum import goal_droughts
    frames = {}
    for fr in _goal(0) + _goal(28) + _goal(500):
        frames[fr.t] = fr
    total = 700
    all_frames = [frames.get(t, Frame(t=t, players=[],
                                      ball=Ball(x=20.0, y=10.0,
                                                confidence=1.0)))
                  for t in range(total)]
    d = goal_droughts(Match(_meta(), all_frames))
    home = d["home"]
    # A 2. gól (~35. kocka) és az 500. kocka köze ~18-19 mp — ez a leghosszabb.
    assert home["longest_s"] > 15.0
    assert home["start_s"] < home["end_s"]
    # A vendég gól nélkül: a teljes felvétel a gólcsendje.
    assert abs(d["away"]["longest_s"] - total / 25.0) < 0.5


def test_scoring_timeline_buckets_goals():
    """A gólok a megfelelő idő-vödörbe kerülnek."""
    from handball.pipeline.momentum import scoring_timeline
    m = _match_from_goals("HHAAA")
    tl = scoring_timeline(m, bucket_s=1.0)
    total_home = sum(b["home"] for b in tl["buckets"])
    total_away = sum(b["away"] for b in tl["buckets"])
    assert total_home == 2 and total_away == 3
    assert len(tl["buckets"]) >= 2


def test_scoring_timeline_empty():
    from handball.pipeline.momentum import scoring_timeline
    m = Match(_meta(), [])
    assert scoring_timeline(m)["buckets"] == []
