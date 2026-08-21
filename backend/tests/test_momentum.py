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


def test_opening_profile_first_scorer_and_early_score():
    """A A A H H H H → a vendég szerzi az első gólt, és a meccs első 6
    góljából (AAAHHH) a vendég 3–3-ra áll a hazaival; a 7. gól már nem
    számít a korai ablakba."""
    from handball.pipeline.momentum import opening_profile
    op = opening_profile(_match_from_goals("AAAHHHH"))
    assert op["away"]["scores_first"] is True
    assert op["home"]["scores_first"] is False
    assert op["home"]["early_goals_seen"] == 6      # a 7. gól kimarad
    assert op["home"]["early_for"] == 3 and op["home"]["early_against"] == 3
    assert op["away"]["early_for"] == 3 and op["away"]["early_against"] == 3


def test_opening_profile_no_goals_none():
    """Gól nélkül a nyitógól ismeretlen (None), a korai ablak üres."""
    from handball.pipeline.momentum import opening_profile
    m = Match(_meta(), [Frame(t=i, players=[], ball=None) for i in range(10)])
    op = opening_profile(m)
    assert op["home"]["scores_first"] is None
    assert op["home"]["early_goals_seen"] == 0
    assert op["home"]["early_for"] == 0


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


def test_clutch_scorers_credits_late_shooter():
    """Elég hosszú felvételen a hajrá-ablakban esett gólt a lövőnek írja
    jóvá; rövid klipen üres."""
    from handball.pipeline.momentum import (CLUTCH_MIN_DURATION_S,
                                            clutch_scorers)
    fps = 25.0

    def pl(tid, x, y, j=None):
        return PlayerPosition(track_id=tid, team=Team.HOME, x=x, y=y,
                              source=PositionSource.MEASURED, confidence=1.0,
                              jersey_number=j)

    frames = []
    t = 0
    for _ in range(int((CLUTCH_MIN_DURATION_S + 30) * fps)):
        frames.append(Frame(t=t, players=[pl(7, 20.0, 10.0, 7)],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    # Hajrá-gól a 7-es lövőtől a +x kapura.
    for _ in range(3):
        frames.append(Frame(t=t, players=[pl(7, 33.0, 10.0, 7)],
                            ball=Ball(x=33.0, y=10.0, confidence=1.0)))
        t += 1
    for i in range(9):
        bx = min(33.0 + 1.6 * (i + 1), 40.0)
        frames.append(Frame(t=t, players=[pl(7, 33.0, 10.0, 7)],
                            ball=Ball(x=bx, y=10.0, confidence=1.0)))
        t += 1
    cs = clutch_scorers(Match(_meta(), frames))
    assert cs["home"]["total"] == 1
    assert cs["home"]["players"][0]["player_id"] == 7
    assert cs["home"]["players"][0]["goals"] == 1
    # Rövid klipen üres.
    short = _match_from_goals("HH")
    assert clutch_scorers(short)["home"]["total"] == 0


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


def test_lead_protection_blown_and_held():
    """A hazai 3-0-ra ellép, majd 3-4-re kikap → elengedett vezetés; a
    vendég fordít és nyer → az ő (1 gólos) előnye küszöb alatti."""
    from handball.pipeline.momentum import lead_protection
    m = _match_from_goals("HHHAAAA")
    lp = lead_protection(m)
    h = lp["home"]
    assert h["max_lead"] == 3 and h["final_margin"] == -1
    assert h["led"] and h["blown"] and h["verdict"] == "elengedte"
    a = lp["away"]
    assert a["max_lead"] == 1 and not a["led"] and a["verdict"] is None

    # Megtartott előny: 4-1-es győzelem 3+ gólos ellépéssel.
    lp2 = lead_protection(_match_from_goals("HHHAH"))
    h2 = lp2["home"]
    assert h2["led"] and not h2["blown"] and h2["verdict"] == "megtartotta"


def test_lead_protection_no_goals():
    from handball.pipeline.momentum import lead_protection
    lp = lead_protection(Match(_meta(), []))
    assert lp["home"]["max_lead"] == 0 and lp["home"]["verdict"] is None


def test_post_goal_lapses_quick_reply_counted():
    """A hazai 3 góljából egyre jön 10 mp-en belüli válasz → 33%; a
    vendégnek kevés a gólja az ítélethez."""
    from handball.pipeline.momentum import post_goal_lapses

    frames = []
    for t0, ch in ((0, "H"), (250, "A"), (2000, "H"), (3000, "H"),
                   (8000, "A")):
        frames += _goal(t0, toward_home_goal=(ch == "A"))
        frames.append(Frame(t=frames[-1].t + 1, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    pgl = post_goal_lapses(Match(_meta(), frames))
    h = pgl["home"]
    assert h["goals"] == 3 and h["quick_replies"] == 1
    assert abs(h["rate_pct"] - 33.3) < 0.1
    a = pgl["away"]
    assert a["goals"] == 2 and a["rate_pct"] is None


def test_post_goal_lapses_no_goals():
    from handball.pipeline.momentum import post_goal_lapses
    pgl = post_goal_lapses(Match(_meta(), []))
    assert pgl["home"]["goals"] == 0 and pgl["home"]["rate_pct"] is None


def test_close_game_record_verdicts():
    """4-3 → szoros győzelem/vereség; 4-4 → döntetlen; kevés gólnál nincs
    ítélet."""
    from handball.pipeline.momentum import close_game_record

    cg = close_game_record(_match_from_goals("HHAAHAH"))  # 4-3
    assert cg["home"]["margin"] == 1
    assert cg["home"]["verdict"] == "szoros győzelem"
    assert cg["away"]["verdict"] == "szoros vereség"

    cg2 = close_game_record(_match_from_goals("HHAAHAAH"))  # 4-4
    assert cg2["home"]["verdict"] == "döntetlen"

    cg3 = close_game_record(_match_from_goals("HHA"))  # 2-1, kevés gól
    assert cg3["home"]["verdict"] is None

    # Sima (3+ gólos) győzelem: nem szoros, nincs ítélet.
    cg4 = close_game_record(_match_from_goals("HHHHHAA"))  # 5-2
    assert cg4["home"]["verdict"] is None
    assert cg4["home"]["margin"] == 3


def test_halftime_comeback_turned_from_deficit():
    """A hazai félidei 1-2 hátrányból 4-3-ra fordít; félidő-jel nélkül
    nincs ítélet."""
    from handball.models.tracking import PlayerPosition, PositionSource
    from handball.pipeline.momentum import halftime_comeback

    def _active(t0, seconds):
        players = [PlayerPosition(track_id=100 + k,
                                  team=Team.HOME if k < 4 else Team.AWAY,
                                  x=8.0 + 3.0 * k, y=4.0 + (k % 4),
                                  source=PositionSource.MEASURED,
                                  confidence=1.0) for k in range(8)]
        return [Frame(t=t0 + i, players=players,
                      ball=Ball(x=20.0, y=10.0, confidence=1.0))
                for i in range(int(seconds * 25))]

    def _half(t0, sequence):
        frames = _active(t0, 100)
        t = frames[-1].t + 1
        for ch in sequence:
            frames += _goal(t, toward_home_goal=(ch == "A"))
            t += 8
            frames += _active(t, 100)
            t = frames[-1].t + 1
        return frames

    frames = _half(0, "AAH")            # félidőben 1-2
    t = frames[-1].t + 1
    frames += [Frame(t=t + i, players=[], ball=None)
               for i in range(int(120 * 25))]
    frames += _half(frames[-1].t + 1, "HHHA")  # vége 4-3
    htc = halftime_comeback(Match(_meta(), frames))
    h = htc["home"]
    assert h["ht_margin"] == -1 and h["final_margin"] == 1
    assert h["verdict"] == "fordította"
    # A vendég a félidőnél vezetett → róla nincs hátrány-ítélet.
    assert htc["away"]["verdict"] is None

    # Félidő-jel nélkül nincs ítélet.
    no_ht = halftime_comeback(_match_from_goals("HHAAHAH"))
    assert no_ht["home"]["verdict"] is None


def test_parity_breaks_counts_tie_breaking_goals():
    """HAHAHH: három holtpont (0-0, 1-1, 2-2), mindet a hazai viszi el;
    kevés holtpontnál nincs ítélet."""
    from handball.pipeline.momentum import parity_breaks

    pb = parity_breaks(_match_from_goals("HAHAHH"))
    h = pb["home"]
    assert h["ties"] == 3 and h["won"] == 3
    assert h["rate_pct"] == 100.0
    assert pb["away"]["won"] == 0 and pb["away"]["rate_pct"] == 0.0

    # Két holtpont: kevés az ítélethez.
    pb2 = parity_breaks(_match_from_goals("HAH"))
    assert pb2["home"]["ties"] == 2
    assert pb2["home"]["rate_pct"] is None


def test_run_containment_measures_suffered_run_lengths():
    """HHHAHHHH: a vendég két hazai sorozatot szenved el (3 és 4 gól,
    átlag 3,5); egy sorozatnál nincs átlag-ítélet."""
    from handball.pipeline.momentum import run_containment

    rc = run_containment(_match_from_goals("HHHAHHHH"))
    a = rc["away"]
    assert a["suffered"] == 2 and a["suffered_goals"] == 7
    assert a["avg_len"] == 3.5
    assert rc["home"]["made"] == 2 and rc["home"]["made_goals"] == 7
    assert rc["home"]["suffered"] == 0

    # Egyetlen elszenvedett sorozat: kevés az átlaghoz.
    rc2 = run_containment(_match_from_goals("HHHA"))
    assert rc2["away"]["suffered"] == 1
    assert rc2["away"]["avg_len"] is None


def test_drought_anatomy_separates_silent_and_wasteful():
    """Mindkét csapat korán gólt lő, majd 10 percig egyik sem — de a
    vendég közben 10 kapura törést kihagy (kihagyós csend), a hazai
    lövésig sem jut (néma csend); rövid felvételnél nincs ítélet."""
    from handball.pipeline.momentum import drought_anatomy

    def _away_miss(t0):
        fr = []
        for i in range(7):
            fr.append(Frame(
                t=t0 + i,
                players=[PlayerPosition(
                    track_id=11, team=Team.AWAY, x=3.0, y=10.0,
                    source=PositionSource.MEASURED, confidence=1.0)],
                ball=Ball(x=max(2.6 - 0.6 * i, 0.0), y=10.0 - i * 1.0,
                          confidence=1.0)))
        fr.append(Frame(t=t0 + 8, players=[],
                        ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        return fr

    frames = _goal(0) + _goal(50, toward_home_goal=True)
    events = {t: True for t in range(100, 15100, 1500)}  # 10 kihagyás
    t = 100
    while t < 15100:
        if t in events:
            frames += _away_miss(t)
            t += 10
        else:
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    da = drought_anatomy(Match(_meta(), frames))
    assert da["home"]["verdict"] == "néma"
    assert da["away"]["verdict"] == "kihagyós"
    assert da["away"]["shots"] >= 10
    assert da["home"]["shots"] <= 2

    # Rövid felvétel: a leghosszabb csend is rövid → nincs ítélet.
    short = drought_anatomy(Match(_meta(), frames[:2000]))
    assert short["home"]["verdict"] is None


def test_restart_speed_separates_fast_break_and_slow_restart():
    """A vendég a kapott gólok után 5 mp alatt átviszi a labdát
    (lerohanós), a hazai 30 mp alatt (lassú); kevés újraindításnál
    nincs ítélet."""
    from handball.pipeline.momentum import restart_speed

    frames = []
    t = 0

    def _idle(n, x):
        nonlocal t, frames
        for _ in range(n):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1

    for _ in range(4):
        # Hazai gól (+x kapu) → a vendég 5 mp alatt átér (x < 20).
        frames += _goal(t)
        t = frames[-1].t + 1
        _idle(120, 30.0)   # ~5 mp a vendég térfelén
        _idle(30, 15.0)    # átlépve a hazai térfélre
        _idle(100, 15.0)
    for _ in range(4):
        # Vendég gól (-x kapu) → a hazai 30 mp alatt ér csak át.
        frames += _goal(t, toward_home_goal=True)
        t = frames[-1].t + 1
        _idle(750, 10.0)   # 30 mp a hazai térfélen
        _idle(30, 25.0)    # átlépve a vendég térfélre
        _idle(100, 25.0)

    rs = restart_speed(Match(_meta(), frames))
    h, a = rs["home"], rs["away"]
    assert a["restarts"] >= 4 and a["style"] == "lerohanós"
    assert h["restarts"] >= 4 and h["style"] == "lassú"
    assert h["avg_s"] > a["avg_s"]

    # Kevés újraindítás: nincs ítélet.
    few = restart_speed(Match(_meta(), frames[:300]))
    assert few["home"]["style"] is None and few["away"]["style"] is None


def test_clutch_shot_quality_flags_rushed_finishing():
    """A hazai a hajrá előtt a hatosról fejezi be, a hajrában 15 m-ről
    kapkod → "elkapkodja"; a vendégnek nincs lövése → nincs ítélet.
    Rövid felvételen a réteg nem értelmezhető."""
    from handball.pipeline.momentum import clutch_shot_quality

    def _home_shot(t0, shooter_x):
        """Egy hazai lövés a +x kapura, a megadott távolságból."""
        fr = []
        def _pl():
            return PlayerPosition(track_id=1, team=Team.HOME, x=shooter_x,
                                  y=10.0, source=PositionSource.MEASURED,
                                  confidence=1.0)
        # A labda előbb a lövő kezében (különben nincs elengedés-pillanat,
        # és a lövő azonosítatlan marad).
        for k in range(3):
            fr.append(Frame(t=t0 - 3 + k, players=[_pl()],
                            ball=Ball(x=shooter_x + 0.2, y=10.0,
                                      confidence=1.0)))
        for i in range(8):
            fr.append(Frame(
                t=t0 + i,
                players=[_pl()],
                ball=Ball(x=min(shooter_x + (40.0 - shooter_x) / 7.0 * i,
                                40.0),
                          y=10.0, confidence=1.0)))
        return fr

    # 800 mp-es felvétel; a hajrá az utolsó 300 mp (t >= 12500 kocka).
    shots = {}
    for k in range(6):
        shots[1000 + k * 500] = 34.0        # hajrá előtt: ~6 m
    for k in range(6):
        shots[13000 + k * 400] = 25.0       # hajrában: ~15 m

    frames = []
    t = 0
    while t < 20000:
        if t in shots:
            frames += _home_shot(t, shots[t])
            t += 10
        else:
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
            t += 1

    csq = clutch_shot_quality(Match(_meta(), frames))
    assert csq["available"] is True
    h = csq["home"]
    assert h["early_shots"] >= 5 and h["clutch_shots"] >= 5
    assert h["early_avg"] > h["clutch_avg"]
    assert h["delta"] < 0
    assert h["verdict"] == "elkapkodja"

    # A vendégnek nincs lövése → nincs átlag és nincs ítélet.
    a = csq["away"]
    assert a["clutch_shots"] == 0
    assert a["clutch_avg"] is None and a["verdict"] is None

    # Rövid felvétel (10 perc alatt): a réteg nem értelmezhető.
    short = clutch_shot_quality(Match(_meta(), frames[:5000]))
    assert short == {"available": False}


def test_clutch_turnovers_flags_pressure_mistakes():
    """A hazai a hajrában sűrűbben adja el a labdát, mint előtte →
    "hajrá-hibázó"; rövid felvételen a réteg nem értelmezhető."""
    from handball.pipeline.momentum import clutch_turnovers

    both = [PlayerPosition(track_id=1, team=Team.HOME, x=20.0, y=10.0,
                           source=PositionSource.MEASURED,
                           confidence=1.0),
            PlayerPosition(track_id=11, team=Team.AWAY, x=20.6, y=10.0,
                           source=PositionSource.MEASURED,
                           confidence=1.0)]
    frames = []
    t = 0

    def _hold(x, n):
        nonlocal t, frames
        for _ in range(n):
            frames.append(Frame(t=t, players=both,
                                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1

    # 800 mp: a hajrá előtt (500 mp) ritka labdaváltás, a hajrában
    # (utolsó 300 mp) sűrű — a hazai eladás-üteme megugrik.
    while t < 12500:
        _hold(20.0, 1000)    # 40 mp hazai birtoklás
        _hold(20.6, 250)     # 10 mp vendég birtoklás
    while t < 20000:
        _hold(20.0, 125)     # 5 mp hazai birtoklás
        _hold(20.6, 125)     # 5 mp vendég birtoklás

    cto = clutch_turnovers(Match(_meta(), frames))
    assert cto["available"] is True
    h = cto["home"]
    assert h["early_to"] >= 5 and h["clutch_to"] >= 5
    assert h["clutch_per_min"] > h["early_per_min"]
    assert h["delta_per_min"] > 0
    assert h["verdict"] == "hajrá-hibázó"

    # Rövid felvétel (10 perc alatt): nem értelmezhető.
    short = clutch_turnovers(Match(_meta(), frames[:5000]))
    assert short == {"available": False}


# ---- Hajrá-ötös (kik vannak a pályán a döntő szakaszban) ---------------------

def _clutch_lineup_match(total_s=900.0, late_ids=(1, 2, 3, 4, 5, 6),
                         fps=25.0):
    """A meccs első kétharmadában a 11-16-os, az utolsó 10 percben a
    `late_ids` játékosok vannak a hazai pályán."""
    frames = []
    n = int(total_s * fps)
    late_start = n - int(600.0 * fps)
    for i in range(n):
        ids = late_ids if i >= late_start else (11, 12, 13, 14, 15, 16)
        players = [_pl(pid, Team.HOME, 20.0 + k, 4.0 + k)
                   for k, pid in enumerate(ids)]
        players += [_pl(90, Team.AWAY, 30.0, 10.0)]
        frames.append(Frame(t=i, players=players,
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    return Match(_meta(fps), frames)


def test_clutch_lineup_lists_the_closing_players():
    """Az utolsó 10 perc emberei kerülnek a hajrá-magba, a korábbi
    ötös nem."""
    from handball.pipeline.momentum import clutch_lineup

    rec = clutch_lineup(_clutch_lineup_match())["home"]
    core_ids = {p["player_id"] for p in rec["core"]}
    assert core_ids == {1, 2, 3, 4, 5, 6}
    assert rec["players"][0]["share_pct"] == 100.0
    # A korábbi szakasz emberei legfeljebb az ablak-határon lógnak be
    # egy-két kockával, a hajrá-magba nem kerülnek.
    early = [p for p in rec["players"] if p["player_id"] == 11]
    assert not early or early[0]["frames"] <= 2


def test_clutch_lineup_short_match_has_no_core():
    """Rövid (10 percnél kevesebb) felvételen nincs hajrá-mag."""
    from handball.pipeline.momentum import clutch_lineup

    rec = clutch_lineup(_clutch_lineup_match(total_s=300.0))["home"]
    assert rec["core"] == []


# ---- Hajrá-hibázók (ki adja el a labdát a végén) ----------------------------

def _clutch_turnover_match(late_losers=(3, 3, 5), total_s=900.0,
                           fps=25.0):
    """A meccs végén (az utolsó 5 percben) a `late_losers` játékosok
    adják el a labdát a vendégnek; korábban nincs eladás."""
    frames = []
    n = int(total_s * fps)
    losses = {}
    for k, pid in enumerate(late_losers):
        # Az utolsó 5 percen belül, egymástól távol.
        losses[n - int((240 - k * 60) * fps)] = pid

    holder = (1, Team.HOME)
    for i in range(n):
        if i in losses:
            holder = (losses[i], Team.HOME)
        elif any(i == t + 30 for t in losses):
            holder = (21, Team.AWAY)      # a labda a vendéghez kerül
        elif any(i == t + 120 for t in losses):
            holder = (1, Team.HOME)       # majd vissza a hazaihoz
        pid, team = holder
        frames.append(Frame(
            t=i, players=[_pl(pid, team, 20.0, 10.0)],
            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    return Match(_meta(fps), frames)


def test_clutch_turnover_players_finds_the_late_loser():
    """A hajrában kétszer eladó játékos kerül a lista élére."""
    from handball.pipeline.momentum import clutch_turnover_players

    rec = clutch_turnover_players(_clutch_turnover_match())["home"]
    assert rec["turnovers"] >= 2
    assert rec["top"] is not None and rec["top"]["player_id"] == 3
    assert rec["top"]["turnovers"] == 2


def test_clutch_turnover_players_short_match():
    """Rövid felvételen nincs hajrá-kép."""
    from handball.pipeline.momentum import clutch_turnover_players

    rec = clutch_turnover_players(
        _clutch_turnover_match(total_s=300.0))["home"]
    assert rec["players"] == [] and rec["top"] is None


# ---- Kezdő hatos (kikkel kezdenek) ------------------------------------------

def test_opening_lineup_lists_the_starters():
    """A meccs első öt percének emberei kerülnek a kezdő magba, a
    később beálló csere nem."""
    from handball.pipeline.momentum import opening_lineup

    rec = opening_lineup(_clutch_lineup_match(
        late_ids=(1, 2, 3, 4, 5, 6)))["home"]
    core_ids = {p["player_id"] for p in rec["core"]}
    assert core_ids == {11, 12, 13, 14, 15, 16}
    assert rec["players"][0]["share_pct"] == 100.0


def test_opening_lineup_empty_match():
    """Üres felvételen üres a kép."""
    from handball.pipeline.momentum import opening_lineup

    rec = opening_lineup(Match(_meta(), []))["home"]
    assert rec["players"] == [] and rec["core"] == []


# ---- Félidő-nyitás (hogyan indulnak az első 5 percben) ---------------------

def _half_opening_match(early, late=(), fps=25.0):
    """`early`: a nyitó 5 percbe eső gólok (True = hazai), `late`: az
    ablakon kívüli gólok — a gólok között 3 másodperc szünet."""
    frames = []
    t = 0
    for home_goal in early:
        frames += _goal(t, toward_home_goal=not home_goal)
        t = frames[-1].t + 1
        for _ in range(int(3 * fps)):     # szünet: a labda középen áll
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
            t += 1
    t = max(t, int(310 * fps))            # ki a nyitó ablakból
    for home_goal in late:
        frames += _goal(t, toward_home_goal=not home_goal)
        t = frames[-1].t + 1
        for _ in range(int(3 * fps)):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_half_openings_flags_the_fast_starter():
    """A nyitó 5 percben 3-1 → jól nyitják a félidőket (a másik oldal
    lassan indul); az ablakon kívüli gólok nem számítanak."""
    from handball.pipeline.momentum import half_openings

    res = half_openings(_half_opening_match(
        [True, True, False, True], late=[False, False, False]))
    assert res["home"]["goals_for"] == 3
    assert res["home"]["goals_against"] == 1
    assert res["home"]["verdict"] == "jól nyitják a félidőket"
    assert res["away"]["verdict"] == "lassan indulnak"


def test_half_openings_needs_enough_goals():
    """Kevés (4-nél kevesebb) nyitó gólnál nincs ítélet."""
    from handball.pipeline.momentum import half_openings

    res = half_openings(_half_opening_match([True, True, False]))
    assert res["home"]["goals_for"] == 2 and res["home"]["verdict"] is None


# ---- Félidő-zárás (mit kezdenek az utolsó labdával) ------------------------

def _clo_pl(track_id, team, x, y, role=None):
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0,
                          role=role)


def _closing_match(results, fps=25.0):
    """Hazai záró támadások: a `results` elemei jelzik, gólt ért-e a
    támadás; a szakaszok a felvétel utolsó perceibe esnek."""
    frames = []
    t = 0
    for scored in results:
        n = int(4.0 * fps)
        for i in range(n):                 # támadás: 22 → 33 m
            x = 22.0 + 11.0 * i / max(1, n - 1)
            frames.append(Frame(t=t, players=[
                _clo_pl(1, Team.HOME, x, 10.0),
                _clo_pl(20, Team.AWAY, 37.0, 8.0),
                _clo_pl(9, Team.AWAY, 39.5, 10.0, role="kapus"),
            ], ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1
        if scored:
            for i in range(7):             # gól a +x kapuba
                frames.append(Frame(t=t, players=[
                    _clo_pl(1, Team.HOME, 33.0, 10.0)],
                    ball=Ball(x=min(34.0 + i, 40.0), y=10.0,
                              confidence=1.0)))
                t += 1
        for _ in range(int(4.0 * fps)):    # szünet: nincs támadó fázis
            frames.append(Frame(t=t, players=[], ball=None))
            t += 1
    return Match(_meta(fps), frames)


def test_closing_attacks_flags_the_cool_finisher():
    """Négy záró támadásból három gól → jól kezelik a záró labdát."""
    from handball.pipeline.momentum import closing_attacks

    rec = closing_attacks(_closing_match([True, True, True, False]))["home"]
    assert rec["attacks"] == 4 and rec["goals"] == 3
    assert rec["verdict"] == "jól kezelik a záró labdát"


def test_closing_attacks_flags_the_wasteful_team():
    """Ha egyik záró támadásból sem lesz gól, elpuskázzák a záró
    labdát."""
    from handball.pipeline.momentum import closing_attacks

    rec = closing_attacks(_closing_match([False] * 4))["home"]
    assert rec["goals"] == 0 and rec["verdict"] == "elpuskázzák a záró labdát"


def test_closing_attacks_needs_enough_attacks():
    """Kevés (3-nál kevesebb) záró támadásnál nincs ítélet."""
    from handball.pipeline.momentum import closing_attacks

    rec = closing_attacks(_closing_match([True, False]))["home"]
    assert rec["attacks"] == 2 and rec["verdict"] is None


# ---- Pad-gólok (a kispad is termel-e) --------------------------------------

def _bench_match(scorers, fps=25.0):
    """Az 1-es a kezdő mag (a nyitányt végigjátssza); a `scorers`
    elemei az egyes gólok lövői (1 = kezdő, 7 = padról beálló)."""
    frames = []
    t = 0
    for _ in range(150):     # nyitány: az 1-es (és a vendég 21-es) fent
        frames.append(Frame(t=t, players=[
            _clo_pl(1, Team.HOME, 10.0, 10.0),
            _clo_pl(21, Team.AWAY, 30.0, 16.0)],
            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    for pid in scorers:
        for _ in range(4):   # a labda a lövő KEZÉBEN (az elengedés előtt)
            frames.append(Frame(t=t, players=[
                _clo_pl(pid, Team.HOME, 33.0, 10.0)],
                ball=Ball(x=33.2, y=10.0, confidence=1.0)))
            t += 1
        for i in range(8):   # gól a +x kapuba, a labda a lövőtől indul
            frames.append(Frame(t=t, players=[
                _clo_pl(pid, Team.HOME, 33.0, 10.0)],
                ball=Ball(x=min(33.0 + i, 40.0), y=10.0,
                          confidence=1.0)))
            t += 1
        for _ in range(40):  # szünet a gólok közt
            frames.append(Frame(t=t, players=[
                _clo_pl(1, Team.HOME, 10.0, 10.0)],
                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_bench_scoring_flags_the_starter_only_team():
    """Hat gól, mind a kezdő 1-estől → csak a kezdők termelnek."""
    from handball.pipeline.momentum import bench_scoring

    rec = bench_scoring(_bench_match([1] * 6))["home"]
    assert rec["goals"] == 6 and rec["bench_goals"] == 0
    assert rec["verdict"] == "csak a kezdők termelnek"


def test_bench_scoring_flags_the_deep_team():
    """Hat gólból három a padról beálló 7-estől → a kispad is termel."""
    from handball.pipeline.momentum import bench_scoring

    rec = bench_scoring(_bench_match([1, 7, 1, 7, 1, 7]))["home"]
    assert rec["bench_goals"] == 3
    assert rec["verdict"] == "a kispad is termel"


def test_bench_scoring_needs_enough_goals():
    """Kevés (6-nál kevesebb) lövőhöz köthető gólnál nincs ítélet."""
    from handball.pipeline.momentum import bench_scoring

    rec = bench_scoring(_bench_match([1, 1, 1]))["home"]
    assert rec["goals"] == 3 and rec["bench_pct"] is None
    assert rec["verdict"] is None


def _ssr_match(scorers):
    """Poszt-olvasható pad: a kezdő mag (1-es) az első percekben, majd
    t=7600-tól (a kezdő-ablakon túl) a padról beálló 7-es (vonal, beálló)
    és 9-es (szél) játszik; a `scorers` a pad-gólok lövői sorban."""
    spos = {1: (30.0, 14.0), 7: (34.0, 10.0), 9: (35.0, 3.0)}

    def pl(tid, x, y):
        return PlayerPosition(track_id=tid, team=Team.HOME, x=x, y=y,
                              source=PositionSource.MEASURED,
                              confidence=1.0)

    def cast():
        return [pl(tid, *xy) for tid, xy in spos.items()]

    frames = []
    for t in range(150):     # nyitány: csak a kezdő 1-es (és a vendég)
        frames.append(Frame(t=t, players=[
            _clo_pl(1, Team.HOME, 10.0, 10.0),
            _clo_pl(21, Team.AWAY, 30.0, 16.0)],
            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    t = 7600                 # a kezdő-ablakon (300 s) túl: a pad játszik
    for _ in range(160):     # poszt-becsléshez elég mért kocka
        frames.append(Frame(t=t, players=cast(),
                            ball=Ball(x=34.2, y=10.0, confidence=1.0)))
        t += 1
    for tid in scorers:
        sx, sy = spos[tid]
        for _ in range(3):   # a labda a lövőnél
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=sx + 0.2, y=sy,
                                          confidence=1.0)))
            t += 1
        for i in range(9):   # gól a +x kapura
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=min(sx + 1.6 * (i + 1),
                                                40.0),
                                          y=sy, confidence=1.0)))
            t += 1
        for _ in range(30):  # vissza középre
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=30.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    return Match(_meta(), frames)


def test_super_sub_roles_names_the_bench_post():
    """Ha a pad-gólok zöme egy posztról esik, a paduk posztról
    olvasható — az oda érkező frisset azonnal fel kell venni."""
    from handball.pipeline.momentum import super_sub_roles

    rec = super_sub_roles(_ssr_match([7, 7, 7, 9]))["home"]
    assert rec["goals"] >= 3, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "posztról termel" in rec["verdict"], rec


def test_super_sub_roles_silent_with_few_goals():
    """Kevés poszthoz kötött pad-gólnál nincs ítélet."""
    from handball.pipeline.momentum import super_sub_roles

    rec = super_sub_roles(_ssr_match([7, 9]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


def test_super_sub_names_the_bench_scorer():
    """A pad-gólok zöme a 7-esé → ő a szuper-csere, névre szólóan."""
    from handball.pipeline.momentum import super_sub

    rec = super_sub(_bench_match([7, 7, 1, 7, 8]))["home"]
    assert rec["bench_goals"] == 4
    assert rec["top"]["player_id"] == 7 and rec["top"]["goals"] == 3
    assert rec["verdict"] == "szuper-cseréjük van"


def test_super_sub_needs_enough_bench_goals():
    """Kevés (SSUB_MIN_BENCH_GOALS alatti) pad-gólnál nincs ítélet."""
    from handball.pipeline.momentum import super_sub

    rec = super_sub(_bench_match([7, 1, 1]))["home"]
    assert rec["bench_goals"] == 1
    assert rec["top"] is None and rec["verdict"] is None


def test_super_sub_spread_bench_is_not_a_super_sub():
    """Ha a pad-gólok szétoszlanak (nincs 50%-os ember), nincs
    szuper-csere — a mély pad nem ugyanaz, mint az egy kiemelt ember."""
    from handball.pipeline.momentum import super_sub

    rec = super_sub(_bench_match([7, 8, 9]))["home"]
    assert rec["bench_goals"] == 3
    assert rec["top"] is None and rec["verdict"] is None


# ---- Középkezdés-átvevő (kinél indul újra a játék) --------------------------

def _restart_match(receivers, fps=25.0):
    """Hazai gólok sorozata; a kapott gól után a vendég `receivers`
    szerinti játékosa veszi át a labdát a felezőnél."""
    frames = []
    t = 0
    for pid in receivers:
        for i in range(7):        # hazai gól a +x kapuba
            frames.append(Frame(t=t, players=[
                _clo_pl(1, Team.HOME, 33.0, 10.0)],
                ball=Ball(x=min(34.0 + i, 40.0), y=10.0,
                          confidence=1.0)))
            t += 1
        for _ in range(20):       # a labda középen, az átvevőnél
            frames.append(Frame(t=t, players=[
                _clo_pl(1, Team.HOME, 33.0, 10.0),
                _clo_pl(pid, Team.AWAY, 20.0, 10.0)],
                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(120):      # szünet: üres középpálya
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=8.0, y=4.0, confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_restart_targets_finds_the_fixed_taker():
    """Négy kapott gól után mindig a 21-es veszi át → fix
    középkezdés-ember."""
    from handball.pipeline.momentum import restart_targets

    rec = restart_targets(_restart_match([21] * 4))["away"]
    assert rec["restarts"] == 4
    assert rec["top"] is not None and rec["top"]["player_id"] == 21
    assert rec["verdict"] == "fix középkezdés-emberük van"


def test_restart_targets_spread_takers_no_verdict():
    """Ha négy átvevő négyfelé oszlik, nincs fix ember."""
    from handball.pipeline.momentum import restart_targets

    rec = restart_targets(_restart_match([21, 22, 23, 24]))["away"]
    assert rec["restarts"] == 4 and rec["top"] is None
    assert rec["verdict"] is None


def test_restart_targets_needs_enough_restarts():
    """Kevés (4-nél kevesebb) mért újraindításnál nincs ítélet."""
    from handball.pipeline.momentum import restart_targets

    rec = restart_targets(_restart_match([21, 21]))["away"]
    assert rec["restarts"] == 2 and rec["verdict"] is None


# ---- Negyedóra-profil (melyik meccs-szakasz az övék) ------------------------

def _quarter_match(home_goal_minutes, away_goal_minutes, minutes=60.0,
                   fps=5.0):
    """Gólok a megadott percekben; a felvétel `minutes` hosszú."""
    events = sorted([(m, "home") for m in home_goal_minutes] +
                    [(m, "away") for m in away_goal_minutes])
    frames = []
    t = 0
    total = int(minutes * 60 * fps)
    ei = 0
    while t < total:
        if ei < len(events) and t >= int(events[ei][0] * 60 * fps):
            side = events[ei][1]
            for i in range(8):
                if side == "home":
                    frames.append(Frame(t=t, players=[
                        _clo_pl(1, Team.HOME, 33.0, 10.0)],
                        ball=Ball(x=min(33.0 + i * 2.5, 40.0), y=10.0,
                                  confidence=1.0)))
                else:
                    frames.append(Frame(t=t, players=[
                        _clo_pl(21, Team.AWAY, 7.0, 10.0)],
                        ball=Ball(x=max(7.0 - i * 2.5, 0.0), y=10.0,
                                  confidence=1.0)))
                t += 1
            ei += 1
        else:
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_quarter_profile_finds_the_strong_quarter():
    """Négy hazai gól a 4. negyedórában → van erős negyedórájuk."""
    from handball.pipeline.momentum import quarter_profile

    rec = quarter_profile(_quarter_match(
        [46.0, 49.0, 52.0, 55.0], [5.0]))["home"]
    assert rec["for"].get("4") == 4
    assert rec["best"] == {"quarter": "4", "diff": 4}
    assert rec["verdict"] == "van erős negyedórájuk"


def test_quarter_profile_even_match_has_no_verdict():
    """Szétszórt góloknál nincs kiemelt negyedóra."""
    from handball.pipeline.momentum import quarter_profile

    rec = quarter_profile(_quarter_match(
        [5.0, 20.0, 35.0, 50.0], [10.0, 25.0, 40.0, 55.0]))["home"]
    assert rec["best"] is None and rec["verdict"] is None


def test_quarter_profile_needs_long_recording():
    """Rövid (40 percnél rövidebb) felvételen nincs ítélet."""
    from handball.pipeline.momentum import quarter_profile

    rec = quarter_profile(_quarter_match(
        [5.0, 8.0, 11.0, 14.0], [], minutes=20.0))["home"]
    assert rec["verdict"] is None


# ---- Hajrá-labdabirtoklás (egy kézben van-e a végjáték) ---------------------

def _cbh_match(hog_share, total=6000, fps=25.0):
    """Az utolsó percek labdás kockáinak hog_share hányada a hazai
    7-esé, a többi felváltva a 8-asé és 9-esé."""
    frames = []
    for t in range(total):
        cycle = t % 100
        if cycle < int(100 * hog_share):
            holder = _clo_pl(7, Team.HOME, 28.0, 10.0)
        elif cycle % 2 == 0:
            holder = _clo_pl(8, Team.HOME, 30.0, 6.0)
        else:
            holder = _clo_pl(9, Team.HOME, 30.0, 14.0)
        frames.append(Frame(t=t, players=[holder],
                            ball=Ball(x=holder.x, y=holder.y,
                                      confidence=1.0)))
    return Match(_meta(fps), frames)


def test_clutch_ball_hogs_finds_the_one_hand():
    """A hajrá-birtoklás fele a 7-esé → egy kézben van a végjátékuk."""
    from handball.pipeline.momentum import clutch_ball_hogs

    rec = clutch_ball_hogs(_cbh_match(0.5))["home"]
    assert rec["top"] is not None and rec["top"]["player_id"] == 7
    assert rec["verdict"] == "egy kézben van a végjátékuk"


def test_clutch_ball_hogs_spread_endgame_no_verdict():
    """Megosztott hajrá-birtoklásnál nincs kiemelt kéz."""
    from handball.pipeline.momentum import clutch_ball_hogs

    rec = clutch_ball_hogs(_cbh_match(0.34))["home"]
    assert rec["top"] is None and rec["verdict"] is None


def test_clutch_ball_hogs_needs_enough_frames():
    """Kevés (200-nál kevesebb) mért labdás kockánál nincs ítélet."""
    from handball.pipeline.momentum import clutch_ball_hogs

    rec = clutch_ball_hogs(_cbh_match(0.5, total=150))["home"]
    assert rec["verdict"] is None


# ---- Forró kéz (van-e sorozatlövőjük) ---------------------------------------

def test_hot_hands_finds_the_streak_shooter():
    """A 7-es kétszer is két egymás utáni gólt dob → sorozatlövő."""
    from handball.pipeline.momentum import hot_hands

    rec = hot_hands(_bench_match([7, 7, 1, 7, 7, 1]))["home"]
    assert rec["goals"] == 6
    assert rec["top"] is not None and rec["top"]["player_id"] == 7
    assert rec["top"]["streaks"] == 2
    assert rec["verdict"] == "van sorozatlövőjük"


def test_hot_hands_alternating_scorers_no_verdict():
    """Felváltva dobott góloknál nincs sorozatlövő."""
    from handball.pipeline.momentum import hot_hands

    rec = hot_hands(_bench_match([7, 1, 7, 1, 7, 1]))["home"]
    assert rec["streaks"] == [] and rec["verdict"] is None


def test_hot_hands_single_long_streak_counts():
    """Egyetlen háromgólos sorozat is elég az ítélethez."""
    from handball.pipeline.momentum import hot_hands

    rec = hot_hands(_bench_match([1, 7, 7, 7, 1, 1]))["home"]
    assert rec["top"] is not None and rec["top"]["longest"] >= 3
    assert rec["verdict"] == "van sorozatlövőjük"


# ---- Csend-törők (ki dobja a gólcsendet megtörő gólt) -----------------------

def _drb_match(goal_plan, fps=5.0):
    """Hazai gólok: a `goal_plan` elemei (perc, lövő-azonosító) párok."""
    frames = []
    t = 0
    for (minute, pid) in sorted(goal_plan):
        target = int(minute * 60 * fps)
        while t < target:
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(3):   # a labda a lövő kezében (elengedés előtt)
            frames.append(Frame(t=t, players=[
                _clo_pl(pid, Team.HOME, 33.0, 10.0)],
                ball=Ball(x=33.2, y=10.0, confidence=1.0)))
            t += 1
        for i in range(8):
            frames.append(Frame(t=t, players=[
                _clo_pl(pid, Team.HOME, 33.0, 10.0)],
                ball=Ball(x=min(33.0 + i * 2.5, 40.0), y=10.0,
                          confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_drought_breakers_finds_the_crisis_scorer():
    """A 7-es kétszer is 5+ perces csendet tör meg → válság-lövő."""
    from handball.pipeline.momentum import drought_breakers

    rec = drought_breakers(_drb_match(
        [(1.0, 1), (2.0, 1), (9.0, 7), (10.0, 1), (17.0, 7)]))["home"]
    assert rec["droughts_broken"] == 2
    assert rec["top"] is not None and rec["top"]["player_id"] == 7
    assert rec["verdict"] == "van válság-lövőjük"


def test_drought_breakers_spread_breaks_no_verdict():
    """Ha a töréseket más-más lövő dobja, nincs kiemelt ember."""
    from handball.pipeline.momentum import drought_breakers

    rec = drought_breakers(_drb_match(
        [(1.0, 1), (9.0, 7), (17.0, 8)]))["home"]
    assert rec["droughts_broken"] == 2 and rec["top"] is None
    assert rec["verdict"] is None


def test_drought_breakers_dense_goals_no_droughts():
    """Sűrű gólok között nincs mérhető csend."""
    from handball.pipeline.momentum import drought_breakers

    rec = drought_breakers(_drb_match(
        [(1.0, 7), (2.0, 7), (3.0, 7)]))["home"]
    assert rec["droughts_broken"] == 0 and rec["verdict"] is None


# ---- Kihagyás-büntetés (megbüntetik-e a kihagyott ziccert) ------------------

def _pmb_match(punished, n_misses=5, fps=25.0):
    """Hazai kihagyott ziccerek (közeli lövés kapu mellé), utána a
    vendégek (nem) büntetnek azonnali góllal."""
    frames = []
    t = 0

    def _emit(players, ball, n=1):
        nonlocal t
        for _ in range(n):
            frames.append(Frame(t=t, players=players, ball=ball))
            t += 1

    for _ in range(n_misses):
        sh = _pl(1, Team.HOME, 35.5, 10.0)
        _emit([sh], Ball(x=35.5, y=10.0, confidence=1.0), 10)
        for i in range(5):          # nagy helyzet, de mellé
            _emit([sh], Ball(x=35.5 + (i + 1),
                             y=10.0 + 0.7 * (i + 1),
                             confidence=1.0))
        _emit([], Ball(x=20.0, y=10.0, confidence=1.0), 30)
        if punished:                # azonnali vendég-válasz
            aw = _pl(21, Team.AWAY, 6.0, 10.0)
            _emit([aw], Ball(x=6.0, y=10.0, confidence=1.0), 10)
            for i in range(7):
                _emit([aw], Ball(x=max(6.0 - (i + 1), -0.5), y=10.0,
                                 confidence=1.0))
        _emit([], Ball(x=20.0, y=10.0, confidence=1.0), 40)
    return Match(_meta(fps), frames)


def test_punished_misses_flags_the_fragile_team():
    """Minden kihagyás után azonnali ellenfél-gól → büntetik őket."""
    from handball.pipeline.momentum import punished_misses

    rec = punished_misses(_pmb_match(True))["home"]
    assert rec["misses"] >= 4 and rec["punished"] >= 4
    assert rec["verdict"] == "a kihagyásaik után azonnal büntetik őket"


def test_punished_misses_flags_the_composed_team():
    """Kihagyások válasz-gól nélkül → jól emésztik."""
    from handball.pipeline.momentum import punished_misses

    rec = punished_misses(_pmb_match(False))["home"]
    assert rec["punished"] == 0
    assert rec["verdict"] == "jól emésztik a kihagyást"


def test_punished_misses_needs_enough_misses():
    """Kevés (4-nél kevesebb) kihagyott ziccernél nincs ítélet."""
    from handball.pipeline.momentum import punished_misses

    rec = punished_misses(_pmb_match(True, n_misses=3))["home"]
    assert rec["verdict"] is None


def _blw_away_goal(frames, t):
    """Egy vendég-gól a t kezdő-időnél: lövő (10,10) → x=0 kapu."""
    for _ in range(30):
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
    for _ in range(40):
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    return t


def test_black_window_flags_recurring_hole():
    """3 kapott gól az 5–10. perc ablakában → hazai fekete ötperc."""
    from handball.pipeline.momentum import black_window

    frames = []
    t = 0
    # Üresjárat a 6. percig (t = 6*60*25 = 9000).
    while t < 9000:
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    for _ in range(3):
        t = _blw_away_goal(frames, t)
    m = Match(_meta(), frames)

    blw = black_window(m)
    h = blw["home"]
    assert h["worst"] == "5–10"
    assert h["worst_diff"] == -3
    assert h["verdict"] == "a 5–10. perc a fekete ötpercük (0-3)"
    # A vendégnél ugyanez az arany-ablak, nem fekete.
    assert blw["away"]["verdict"] is None


def test_black_window_small_deficit_none():
    """Egyetlen kapott gól → nincs fekete ötperc."""
    from handball.pipeline.momentum import black_window

    frames = []
    t = 0
    while t < 9000:
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    t = _blw_away_goal(frames, t)
    blw = black_window(Match(_meta(), frames))
    assert blw["home"]["worst_diff"] == -1
    assert blw["home"]["verdict"] is None


def _fdr_away_goal(frames, t, shooter_id):
    """Egy vendég-gól a megadott lövővel: (10,10) → x=0 kapu."""
    for _ in range(30):
        frames.append(Frame(t=t,
                            players=[_pl(shooter_id, Team.AWAY, 10.0, 10.0)],
                            ball=Ball(x=10.0, y=10.0, confidence=1.0)))
        t += 1
    x = 10.0
    while x > -0.5:
        x -= 0.5
        frames.append(Frame(t=t,
                            players=[_pl(shooter_id, Team.AWAY, 10.0, 10.0)],
                            ball=Ball(x=max(x, -0.5), y=10.0,
                                      confidence=1.0)))
        t += 1
    for _ in range(40):
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    # Hazai érintés: a következő vendég-birtoklás ne kapcsolódjon
    # össze fantom vendég-passzá (gólpassz-jóváírást okozna).
    for _ in range(10):
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 20.0, 10.0)],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    return t


def test_fading_scorers_flags_first_half_star():
    """A 9-es 3 első félidei gólja után a másodikban csendben marad →
    eltűnő ember."""
    from handball.pipeline.momentum import fading_scorers

    frames = []
    t = 0
    for _ in range(3):
        t = _fdr_away_goal(frames, t, 9)
    for _ in range(int(90 * 25)):
        frames.append(Frame(t=t, players=[], ball=None))
        t += 1
    for _ in range(2):
        t = _fdr_away_goal(frames, t, 8)

    fdr = fading_scorers(Match(_meta(), frames))
    a = fdr["away"]
    assert a["top"] == 9
    assert a["verdict"] == ("a(z) 9. az első félidőben él "
                            "(3 gól-részvétel), a másodikban "
                            "eltűnik (0)")
    assert fdr["home"]["verdict"] is None


def test_fading_scorers_needs_halftime():
    """Felismert szünet nélkül nincs ítélet."""
    from handball.pipeline.momentum import fading_scorers

    frames = []
    t = 0
    for _ in range(3):
        t = _fdr_away_goal(frames, t, 9)
    fdr = fading_scorers(Match(_meta(), frames))
    assert fdr["away"]["verdict"] is None
    assert fdr["away"]["players"] == []


def _cbc_home_goal(frames, t, shooter_id=1):
    """Egy hazai gól: a lövő (33,10)-ről a +x kapuba lő."""
    for _ in range(30):
        frames.append(Frame(t=t,
                            players=[_pl(shooter_id, Team.HOME, 33.0, 10.0)],
                            ball=Ball(x=33.0, y=10.0, confidence=1.0)))
        t += 1
    x = 33.0
    while x < 40.5:
        x += 0.5
        frames.append(Frame(t=t,
                            players=[_pl(shooter_id, Team.HOME, 33.0, 10.0)],
                            ball=Ball(x=min(x, 40.5), y=10.0,
                                      confidence=1.0)))
        t += 1
    for _ in range(40):
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    # Vendég-érintés: a következő birtoklás ne kapcsolódjon össze
    # fantom passzá.
    for _ in range(10):
        frames.append(Frame(t=t, players=[_pl(21, Team.AWAY, 20.0, 10.0)],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    return t


def test_comeback_carriers_flags_the_rescuer():
    """3 hazai gól után a vendég 9-es hárompontnyi hátrányban szerzett
    góljai → ő a felzárkózás-húzó; döntetlennél már a 8-as fejez be."""
    from handball.pipeline.momentum import comeback_carriers

    frames = []
    t = 0
    for _ in range(3):
        t = _cbc_home_goal(frames, t, 1)
    for _ in range(3):
        t = _fdr_away_goal(frames, t, 9)   # 0-3 → 3-3, végig hátrányban
    t = _fdr_away_goal(frames, t, 8)       # 3-3-nál: rest

    cbc = comeback_carriers(Match(_meta(), frames))
    a = cbc["away"]
    assert a["top"] == 9
    assert a["verdict"] == ("a(z) 9. hozza őket vissza (3 gól-részvétel "
                            "hátrányban, máskor 0)")
    assert cbc["home"]["verdict"] is None  # a hazai gólok nem hátrányban


def test_comeback_carriers_few_samples_none():
    """Két hátrány-gól még kevés az ítélethez."""
    from handball.pipeline.momentum import comeback_carriers

    frames = []
    t = 0
    for _ in range(2):
        t = _cbc_home_goal(frames, t, 1)
    for _ in range(2):
        t = _fdr_away_goal(frames, t, 9)
    cbc = comeback_carriers(Match(_meta(), frames))
    assert cbc["away"]["verdict"] is None


def _csr_match(scorers, fps=25.0):
    """`scorers` = hajrá-gólonként a lövő HAZAI játékos (7: beálló,
    9: szélső). A felvétel első ~10 perce hazai birtoklás a +x kapu
    felé (poszt-minta), a gólok a záró öt percen belül esnek."""
    from handball.pipeline.momentum import CLUTCH_MIN_DURATION_S

    spos = {7: (34.0, 10.0), 9: (35.0, 3.0)}

    def pl(tid, x, y):
        return PlayerPosition(track_id=tid, team=Team.HOME, x=x, y=y,
                              source=PositionSource.MEASURED,
                              confidence=1.0)

    def cast():
        return [pl(tid, *xy) for tid, xy in spos.items()]

    frames = []
    t = 0
    for _ in range(int((CLUTCH_MIN_DURATION_S + 30) * fps)):
        frames.append(Frame(t=t, players=cast(),
                            ball=Ball(x=34.2, y=10.0, confidence=1.0)))
        t += 1
    for tid in scorers:
        sx, sy = spos[tid]
        for _ in range(3):           # a labda a lövőnél
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=sx + 0.2, y=sy,
                                          confidence=1.0)))
            t += 1
        for i in range(9):           # gól a +x kapura
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=min(sx + 1.6 * (i + 1),
                                                40.0),
                                          y=sy, confidence=1.0)))
            t += 1
        for _ in range(30):          # vissza középre: zóna-visszaállás
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=30.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    return Match(_meta(), frames)


def test_clutch_scorer_roles_names_the_endgame_post():
    """Ha a hajrá-gólok zöme ugyanarról a posztról esik, az utolsó öt
    percben őt kell fogni."""
    from handball.pipeline.momentum import (CSR_MIN_GOALS,
                                            clutch_scorer_roles)

    rec = clutch_scorer_roles(_csr_match([7, 7, 7, 9]))["home"]
    assert rec["goals"] >= CSR_MIN_GOALS, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "utolsó öt percben" in rec["verdict"], rec


def test_clutch_scorer_roles_silent_with_few_goals():
    """Néhány hajrá-gólból nincs ítélet."""
    from handball.pipeline.momentum import clutch_scorer_roles

    rec = clutch_scorer_roles(_csr_match([7, 9]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


def _cbr_match(rescuers):
    """`rescuers` = hátrány-gólonként a vendég lövő (9: átlövő, 8:
    szélső). Először 3 hazai gól (vendég-hátrány), majd a megadott
    lövők vendég-góljai; a poszt-mintát egy vendég-birtoklás szakasz
    adja a gólok előtt."""
    role_pos = {9: (10.0, 10.0), 8: (6.0, 1.0)}
    frames = []
    t = 0
    for _ in range(150):             # vendég-birtoklás: poszt-minta
        players = [_pl(1, Team.HOME, 30.0, 10.0)]
        players += [_pl(tid, Team.AWAY, *xy)
                    for tid, xy in role_pos.items()]
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=10.2, y=10.0, confidence=1.0)))
        t += 1
    for _ in range(3):
        t = _cbc_home_goal(frames, t, 1)
    for tid in rescuers:
        t = _fdr_away_goal(frames, t, tid)
    return Match(_meta(), frames)


def test_comeback_carrier_roles_names_the_rescue_post():
    """Ha a hátrány-gólok zöme ugyanarról a posztról jön, az ő
    kivétele a hátrányukat beragasztja."""
    from handball.pipeline.momentum import (CBR_MIN_TRAILING,
                                            comeback_carrier_roles)

    rec = comeback_carrier_roles(_cbr_match([9, 9, 9]))["away"]
    assert rec["trailing"] >= CBR_MIN_TRAILING, rec
    assert rec["main_role"] == "átlövő", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "beragasztja" in rec["verdict"], rec


def test_comeback_carrier_roles_silent_with_few_goals():
    """Néhány hátrány-gól-részvételből nincs ítélet."""
    from handball.pipeline.momentum import comeback_carrier_roles

    rec = comeback_carrier_roles(_cbr_match([9, 8]))["away"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Csendtörő-poszt (melyik posztjuk töri meg a gólcsendet) ---------------


def _gct_match(breakers, fps=25.0):
    """Poszt-minta (7: beálló, 9: szélső) + gólok: egy nyitó gól után
    a `breakers` lövői 300+ mp-es gólcsendek után találnak be."""
    from handball.pipeline.momentum import DRB_GAP_S

    spos = {7: (34.0, 10.0), 9: (35.0, 3.0)}

    def cast():
        return [_pl(tid, Team.HOME, *xy) for tid, xy in spos.items()]

    def goal(frames, t, tid):
        sx, sy = spos[tid]
        for _ in range(20):          # a labda a lövőnél
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=sx + 0.2, y=sy,
                                          confidence=1.0)))
            t += 1
        x = sx
        while x < 40.5:              # gól a +x kapura
            x += 0.5
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=min(x, 40.5), y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(40):          # zóna-visszaállás
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        return t

    frames = []
    t = 0
    for _ in range(150):             # poszt-minta: hazai birtoklás elöl
        frames.append(Frame(t=t, players=cast(),
                            ball=Ball(x=34.2, y=10.0, confidence=1.0)))
        t += 1
    t = goal(frames, t, 7)           # nyitó gól (nem csend-törés)
    for tid in breakers:
        gap = int(DRB_GAP_S * fps) + 100
        for _ in range(gap):         # gólcsend: a labda középen áll
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        t = goal(frames, t, tid)
    return Match(_meta(fps), frames)


def test_drought_breaker_roles_names_the_crisis_post():
    """Négy csend-törő gólból három a beállóé → ő a válság-poszt."""
    from handball.pipeline.momentum import (GCT_MIN_BREAKS,
                                            drought_breaker_roles)

    rec = drought_breaker_roles(_gct_match([7, 7, 7, 9]))["home"]
    assert rec["breaks"] >= GCT_MIN_BREAKS, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "legszorosabban" in rec["verdict"], rec


def test_drought_breaker_roles_silent_with_few_breaks():
    """Néhány csend-törő gólból nincs ítélet."""
    from handball.pipeline.momentum import drought_breaker_roles

    rec = drought_breaker_roles(_gct_match([7, 9]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Eltűnő-poszt (melyik posztjuk tűnik el a második félidőre) ------------


def _fdp_match(fh_scorers, sh_scorers, with_break=True, fps=25.0):
    """Poszt-minta (7: beálló, 9: szélső) + első/második félidei
    gólok, köztük 90 mp-es üres (szünet-) szakasszal."""
    # 8: második szélső — a 2. félidei gólok passzolója, hogy a
    # gólpassz-jóváírás ne a beállóhoz vándoroljon.
    spos = {7: (34.0, 10.0), 9: (35.0, 3.0), 8: (34.0, 17.0)}

    def cast():
        return [_pl(tid, Team.HOME, *xy) for tid, xy in spos.items()]

    def goal(frames, t, tid, feeder=None):
        if feeder is not None:       # a gólpassz a megadott társtól jön
            fx, fy = spos[feeder]
            for _ in range(15):
                frames.append(Frame(t=t, players=cast(),
                                    ball=Ball(x=fx + 0.2, y=fy,
                                              confidence=1.0)))
                t += 1
        sx, sy = spos[tid]
        for _ in range(20):
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=sx + 0.2, y=sy,
                                          confidence=1.0)))
            t += 1
        x = sx
        while x < 40.5:
            x += 0.5
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=min(x, 40.5), y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(40):
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        return t

    frames = []
    t = 0
    for _ in range(150):             # poszt-minta: hazai birtoklás elöl
        frames.append(Frame(t=t, players=cast(),
                            ball=Ball(x=34.2, y=10.0, confidence=1.0)))
        t += 1
    for tid in fh_scorers:
        t = goal(frames, t, tid)
    if with_break:
        for _ in range(int(90 * fps)):   # félidei szünet: üres kockák
            frames.append(Frame(t=t, players=[], ball=None))
            t += 1
    for tid in sh_scorers:
        t = goal(frames, t, tid, feeder=8)
    return Match(_meta(fps), frames)


def test_fading_scorer_roles_names_the_fading_post():
    """A beálló 3 első félidei részvétel után eltűnik → őt az első
    félidőben kell megfogni."""
    from handball.pipeline.momentum import fading_scorer_roles

    rec = fading_scorer_roles(
        _fdp_match([7, 7, 7], [9, 9]))["home"]
    assert rec["main_role"] == "beálló", rec
    assert rec["fh"] == 3 and rec["sh"] == 0, rec
    assert rec["verdict"] and "első 30 percben" in rec["verdict"], rec


def test_fading_scorer_roles_silent_without_pattern():
    """Kevés első félidei részvételből nincs ítélet."""
    from handball.pipeline.momentum import fading_scorer_roles

    rec = fading_scorer_roles(_fdp_match([7, 7], [9, 9]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Hajráhiba-poszt (melyik posztjuk adja el a labdát a hajrában) ---------


def _ctr_match(losers, fps=25.0):
    """Poszt-minta (7: beálló, 9: szélső) + az utolsó öt percben a
    `losers` játékosok eladják a labdát a 30-as védőnek."""
    from handball.pipeline.momentum import CLUTCH_MIN_DURATION_S

    spos = {7: (34.0, 10.0), 9: (35.0, 3.0)}

    def cast():
        return ([_pl(tid, Team.HOME, *xy) for tid, xy in spos.items()]
                + [_pl(30, Team.AWAY, 15.0, 10.0)])

    frames = []
    t = 0
    for _ in range(int((CLUTCH_MIN_DURATION_S + 30) * fps)):
        frames.append(Frame(t=t, players=cast(),
                            ball=Ball(x=34.2, y=10.0, confidence=1.0)))
        t += 1
    for tid in losers:
        sx, sy = spos[tid]
        for _ in range(10):          # a labda a vesztesnél
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=sx + 0.2, y=sy,
                                          confidence=1.0)))
            t += 1
        for _ in range(10):          # a labda az ellenfélhez kerül
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=15.2, y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(10):          # semleges labda a két eset közt
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=25.0, y=16.0,
                                          confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_clutch_turnover_roles_names_the_leaky_post():
    """Négy hajrá-eladásból három a beállóé → oda jön a záró pressz."""
    from handball.pipeline.momentum import (CTR_MIN_TO,
                                            clutch_turnover_roles)

    rec = clutch_turnover_roles(_ctr_match([7, 7, 7, 9]))["home"]
    assert rec["turnovers"] >= CTR_MIN_TO, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "passzsáv" in rec["verdict"], rec


def test_clutch_turnover_roles_silent_with_few_losses():
    """Néhány hajrá-eladásból nincs ítélet."""
    from handball.pipeline.momentum import clutch_turnover_roles

    rec = clutch_turnover_roles(_ctr_match([7, 9]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Forró-poszt (melyik posztjuk lövi a gólsorozatokat) -------------------


def _hhr_match(scorers, fps=25.0):
    """Poszt-minta (7: beálló, 9: szélső) + gólok a megadott
    sorrendben — az egymás utáni azonos lövők sorozatot adnak."""
    spos = {7: (34.0, 10.0), 9: (35.0, 3.0)}

    def cast():
        return [_pl(tid, Team.HOME, *xy) for tid, xy in spos.items()]

    def goal(frames, t, tid):
        sx, sy = spos[tid]
        for _ in range(20):
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=sx + 0.2, y=sy,
                                          confidence=1.0)))
            t += 1
        x = sx
        while x < 40.5:
            x += 0.5
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=min(x, 40.5), y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(40):
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        return t

    frames = []
    t = 0
    for _ in range(150):             # poszt-minta: hazai birtoklás elöl
        frames.append(Frame(t=t, players=cast(),
                            ball=Ball(x=34.2, y=10.0, confidence=1.0)))
        t += 1
    for tid in scorers:
        t = goal(frames, t, tid)
    return Match(_meta(fps), frames)


def test_hot_hand_roles_names_the_streak_post():
    """A beálló hármas sorozata adja a sorozat-gólokat → az első
    gólja után kell reagálni."""
    from handball.pipeline.momentum import (HHR_MIN_GOALS,
                                            hot_hand_roles)

    rec = hot_hand_roles(_hhr_match([7, 7, 7, 9]))["home"]
    assert rec["streak_goals"] >= HHR_MIN_GOALS, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "őrzés-váltás" in rec["verdict"], rec


def test_hot_hand_roles_silent_without_streaks():
    """Sorozat nélkül (felváltva lőtt gólok) nincs ítélet."""
    from handball.pipeline.momentum import hot_hand_roles

    rec = hot_hand_roles(_hhr_match([7, 9, 7, 9]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Középkezdő-poszt (melyik posztjuknál indul a középkezdés) -------------


def _rtr_match(takers, fps=25.0):
    """Vendég poszt-minta (21: beálló, 22: szélső a -x kapunál) +
    hazai gólok; a kapott gól után a `takers` szerinti vendég veszi
    át a labdát a felezőnél."""
    spos = {21: (6.0, 10.0), 22: (5.0, 3.0)}

    def away_cast(mid_tid=None):
        out = []
        for tid, (x, y) in spos.items():
            if tid == mid_tid:
                out.append(_pl(tid, Team.AWAY, 20.0, 10.0))
            else:
                out.append(_pl(tid, Team.AWAY, x, y))
        return out

    frames = []
    t = 0
    for _ in range(150):             # poszt-minta: vendég birtoklás elöl
        frames.append(Frame(t=t, players=away_cast(),
                            ball=Ball(x=6.2, y=10.0, confidence=1.0)))
        t += 1
    for _ in range(40):              # semleges szakasz a lövés-zónán kívül
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=25.0, y=16.0, confidence=1.0)))
        t += 1
    for tid in takers:
        for i in range(7):           # hazai gól a +x kapuba
            frames.append(Frame(
                t=t, players=[_pl(1, Team.HOME, 33.0, 10.0)],
                ball=Ball(x=min(34.0 + i, 40.0), y=10.0,
                          confidence=1.0)))
            t += 1
        for _ in range(20):          # az átvevő a felezőnél kapja
            frames.append(Frame(
                t=t,
                players=[_pl(1, Team.HOME, 33.0, 10.0)]
                + away_cast(mid_tid=tid),
                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(120):         # szünet: üres középpálya
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=8.0, y=4.0,
                                          confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_restart_taker_roles_names_the_taker_post():
    """Négy átvételből három a beállóé → posztra szóló letámadás."""
    from handball.pipeline.momentum import (RTR_MIN_TAKES,
                                            restart_taker_roles)

    rec = restart_taker_roles(_rtr_match([21, 21, 21, 22]))["away"]
    assert rec["takes"] >= RTR_MIN_TAKES, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "letámadás" in rec["verdict"], rec


def test_restart_taker_roles_silent_with_few_takes():
    """Néhány átvételből nincs ítélet."""
    from handball.pipeline.momentum import restart_taker_roles

    rec = restart_taker_roles(_rtr_match([21, 22]))["away"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Hajrákéz-poszt (melyik poszt kezén fut a végjátékuk) ------------------


def _chr_match(hold_plan, fps=25.0):
    """Poszt-minta (7: beálló, 9: szélső), majd holt szakasz, végül a
    hajrá-ablakban a `hold_plan` szerinti (birtokos, kocka) tartások."""
    from handball.pipeline.momentum import CLUTCH_MIN_DURATION_S

    spos = {7: (34.0, 10.0), 9: (35.0, 3.0)}

    def cast():
        return [_pl(tid, Team.HOME, *xy) for tid, xy in spos.items()]

    frames = []
    t = 0
    for _ in range(int(250 * fps)):  # poszt-minta: hazai birtoklás elöl
        frames.append(Frame(t=t, players=cast(),
                            ball=Ball(x=34.2, y=10.0, confidence=1.0)))
        t += 1
    while t < int((CLUTCH_MIN_DURATION_S + 60) * fps):
        frames.append(Frame(t=t, players=cast(),   # holt szakasz
                            ball=Ball(x=20.0, y=16.0, confidence=1.0)))
        t += 1
    for (tid, n) in hold_plan:       # a hajrá-ablak tartásai
        sx, sy = spos[tid]
        for _ in range(n):
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=sx + 0.2, y=sy,
                                          confidence=1.0)))
            t += 1
        for _ in range(10):
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=20.0, y=16.0,
                                          confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_clutch_hog_roles_names_the_hand():
    """A hajrá labdás idejének dandárja a beállónál van → őt kell
    labdától elzárni."""
    from handball.pipeline.momentum import (CHR_MIN_FRAMES,
                                            clutch_hog_roles)

    rec = clutch_hog_roles(
        _chr_match([(7, 200), (9, 60), (7, 100)]))["home"]
    assert rec["frames"] >= CHR_MIN_FRAMES, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "el sem indulnak" in rec["verdict"], rec


def test_clutch_hog_roles_silent_with_little_holding():
    """Kevés hajrá-labdás kockából nincs ítélet."""
    from handball.pipeline.momentum import clutch_hog_roles

    rec = clutch_hog_roles(_chr_match([(7, 60), (9, 40)]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Rajt-poszt (melyik posztjuk viszi a meccs elejét) ---------------------


def test_opening_scorer_roles_names_the_starting_post():
    """A meccs eleji gólokból három a beállóé → az első tíz percben
    őt kell megfogni."""
    from handball.pipeline.momentum import (OSR_MIN_GOALS,
                                            opening_scorer_roles)

    rec = opening_scorer_roles(_hhr_match([7, 9, 7, 7]))["home"]
    assert rec["goals"] >= OSR_MIN_GOALS, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "első tíz percben" in rec["verdict"], rec


def test_opening_scorers_names_the_starter():
    """Ha a meccs eleji gólok egy embertől jönnek, az első tíz
    percben őt kell a legjobb védővel megfogni."""
    from handball.pipeline.momentum import (OSP_MIN_GOALS,
                                            opening_scorers)

    rec = opening_scorers(_hhr_match([7, 9, 7, 7]))["home"]
    assert rec["top"] is not None, rec
    assert rec["top"]["player_id"] == 7, rec
    assert rec["top"]["goals"] >= OSP_MIN_GOALS, rec


def test_opening_scorers_silent_with_one_goal():
    """Egyetlen nyitó-gólból nem nevezünk meg embert."""
    from handball.pipeline.momentum import opening_scorers

    rec = opening_scorers(_hhr_match([7]))["home"]
    assert rec["top"] is None, rec


def test_opening_scorer_roles_silent_with_few_goals():
    """Néhány meccs eleji gólból nincs ítélet."""
    from handball.pipeline.momentum import opening_scorer_roles

    rec = opening_scorer_roles(_hhr_match([7, 9]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Újrakezdő-poszt (melyik posztjuk viszi a szünet utáni rajtot) ---------


def test_second_start_roles_names_the_restart_post():
    """A szünet utáni gólokból három a beállóé → a második félidő
    elején őt kell megfogni."""
    from handball.pipeline.momentum import (SSR_MIN_GOALS,
                                            second_start_roles)

    rec = second_start_roles(
        _fdp_match([9, 9], [7, 7, 7, 9]))["home"]
    assert rec["goals"] >= SSR_MIN_GOALS, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "szünet után" in rec["verdict"], rec


def test_second_start_roles_silent_without_break():
    """Felismert szünet nélkül nincs ítélet."""
    from handball.pipeline.momentum import second_start_roles

    rec = second_start_roles(
        _fdp_match([9, 9], [7, 7, 7], with_break=False))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


def test_second_start_scorers_names_the_restart_man():
    """Ha a szünet utáni gólok egy embertől jönnek, a második félidő
    elején őt kell megfogni."""
    from handball.pipeline.momentum import (SSP_MIN_GOALS,
                                            second_start_scorers)

    rec = second_start_scorers(
        _fdp_match([9, 9], [7, 7, 7, 9]))["home"]
    assert rec["top"] is not None, rec
    assert rec["top"]["player_id"] == 7, rec
    assert rec["top"]["goals"] >= SSP_MIN_GOALS, rec


def test_second_start_scorers_silent_without_break():
    """Felismert szünet nélkül nincs megnevezett ember."""
    from handball.pipeline.momentum import second_start_scorers

    rec = second_start_scorers(
        _fdp_match([9, 9], [7, 7, 7], with_break=False))["home"]
    assert rec["top"] is None, rec


# ---- Előnyben-poszt (vezetésnél melyik posztjuk viszi a játékot) -----------


def test_lead_scorer_roles_names_the_lead_post():
    """A vezetés közbeni gólok a beállótól jönnek → az ő kivétele
    töri a lendület-tartást."""
    from handball.pipeline.momentum import (LGR_MIN_GOALS,
                                            lead_scorer_roles)

    # Az első gól (9) még döntetlennél esik, a többi már vezetésnél.
    rec = lead_scorer_roles(_hhr_match([9, 7, 7, 7]))["home"]
    assert rec["goals"] >= LGR_MIN_GOALS, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "lendület-tartásukat" in rec["verdict"], rec


def test_lead_scorer_roles_silent_with_few_lead_goals():
    """Kevés előnyben lőtt gólból nincs ítélet."""
    from handball.pipeline.momentum import lead_scorer_roles

    rec = lead_scorer_roles(_hhr_match([9, 7]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


def test_lead_scorers_names_the_lead_man():
    """Ha a vezetés közbeni gólok egy embertől jönnek, az ő kivétele
    töri meg a lendület-tartást."""
    from handball.pipeline.momentum import LGP_MIN_GOALS, lead_scorers

    # Az első gól (9) még döntetlennél esik, a többi már vezetésnél.
    rec = lead_scorers(_hhr_match([9, 7, 7, 7]))["home"]
    assert rec["top"] is not None, rec
    assert rec["top"]["player_id"] == 7, rec
    assert rec["top"]["goals"] >= LGP_MIN_GOALS, rec


def test_lead_scorers_silent_with_few_lead_goals():
    """Egyetlen előnyben lőtt gólból nem nevezünk meg embert."""
    from handball.pipeline.momentum import lead_scorers

    rec = lead_scorers(_hhr_match([9, 7]))["home"]
    assert rec["top"] is None, rec


# ---- Válasz-poszt (kapott gól után melyik posztjuk válaszol) ---------------


def _rsp_match(scorers, fps=25.0):
    """Poszt-minta (7: beálló, 9: szélső) + gólváltás: minden hazai
    gól ELŐTT a vendég 21-es betalál, így minden hazai gól válasz."""
    spos = {7: (34.0, 10.0), 9: (35.0, 3.0)}

    def cast(extra=()):
        return ([_pl(tid, Team.HOME, *xy) for tid, xy in spos.items()]
                + list(extra))

    frames = []
    t = 0
    for _ in range(150):             # poszt-minta: hazai birtoklás elöl
        frames.append(Frame(t=t, players=cast(),
                            ball=Ball(x=34.2, y=10.0, confidence=1.0)))
        t += 1
    for tid in scorers:
        away = [_pl(21, Team.AWAY, 10.0, 10.0)]
        for _ in range(10):          # a labda a vendég lövőnél
            frames.append(Frame(t=t, players=cast(away),
                                ball=Ball(x=10.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        x = 10.0
        while x > -0.5:              # vendég gól a -x kapuba
            x -= 0.5
            frames.append(Frame(t=t, players=cast(away),
                                ball=Ball(x=max(x, -0.5), y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(20):          # semleges szakasz
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=20.0, y=16.0,
                                          confidence=1.0)))
            t += 1
        sx, sy = spos[tid]
        for _ in range(10):          # a labda a hazai lövőnél
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=sx + 0.2, y=sy,
                                          confidence=1.0)))
            t += 1
        xx = sx
        while xx < 40.5:             # hazai válasz-gól a +x kapuba
            xx += 0.5
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=min(xx, 40.5), y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(40):          # zóna-visszaállás
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_response_scorer_roles_names_the_answering_post():
    """Négy válasz-gólból hármat a beálló lő → a saját gólunk után
    azonnal az ő fogására kell váltani."""
    from handball.pipeline.momentum import (RSP_MIN_GOALS,
                                            response_scorer_roles)

    rec = response_scorer_roles(_rsp_match([7, 7, 7, 9]))["home"]
    assert rec["goals"] >= RSP_MIN_GOALS, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "fogására" in rec["verdict"], rec


def test_response_scorers_names_the_answer_man():
    """Ha a válasz-gólok egy embertől jönnek, a saját gólunk után az
    ő fogására kell váltani."""
    from handball.pipeline.momentum import (RSPP_MIN_GOALS,
                                            response_scorers)

    rec = response_scorers(_rsp_match([7, 7, 7, 9]))["home"]
    assert rec["top"] is not None, rec
    assert rec["top"]["player_id"] == 7, rec
    assert rec["top"]["goals"] >= RSPP_MIN_GOALS, rec


def test_response_scorers_silent_with_few_goals():
    """Egyetlen válasz-gólból nem nevezünk meg embert."""
    from handball.pipeline.momentum import response_scorers

    rec = response_scorers(_rsp_match([7]))["home"]
    assert rec["top"] is None, rec


def test_response_scorer_roles_silent_with_few_goals():
    """Néhány válasz-gólból nincs ítélet."""
    from handball.pipeline.momentum import response_scorer_roles

    rec = response_scorer_roles(_rsp_match([7, 9]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Válaszhiba-poszt --------------------------------------------------------

def _rto_match(losers, fps=25.0):
    """Mint az _rsp_match, de a kapott gól után nem gól, hanem
    LABDAELADÁS jön: a `losers` adja, kinek a kezén vész el."""
    spos = {7: (34.0, 10.0), 9: (35.0, 3.0)}

    def cast(extra=()):
        return ([_pl(tid, Team.HOME, *xy) for tid, xy in spos.items()]
                + list(extra))

    frames = []
    t = 0
    for _ in range(150):             # poszt-minta: hazai birtoklás elöl
        frames.append(Frame(t=t, players=cast(),
                            ball=Ball(x=34.2, y=10.0, confidence=1.0)))
        t += 1
    for tid in losers:
        away = [_pl(21, Team.AWAY, 10.0, 10.0)]
        for _ in range(10):          # a labda a vendég lövőnél
            frames.append(Frame(t=t, players=cast(away),
                                ball=Ball(x=10.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        x = 10.0
        while x > -0.5:              # vendég gól a -x kapuba
            x -= 0.5
            frames.append(Frame(t=t, players=cast(away),
                                ball=Ball(x=max(x, -0.5), y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(20):          # semleges szakasz (nincs birtokos)
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=20.0, y=16.0,
                                          confidence=1.0)))
            t += 1
        sx, sy = spos[tid]
        for _ in range(15):          # a labda a hazai vesztesnél
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=sx + 0.2, y=sy,
                                          confidence=1.0)))
            t += 1
        for _ in range(15):          # elvesztve: a vendégnél a labda
            frames.append(Frame(t=t, players=cast(away),
                                ball=Ball(x=10.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(40):          # zóna-visszaállás
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=20.0, y=16.0,
                                          confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_response_turnover_roles_names_the_panicking_post():
    """Ha a kapott gól után rendre ugyanannak a kezén vész el a
    labda, a saját gólunk után az ő fogadására kell menni."""
    from handball.pipeline.momentum import (RTO_MIN_TURNOVERS,
                                            response_turnover_roles)

    rec = response_turnover_roles(_rto_match([7, 7, 7, 9]))["home"]
    assert rec["turnovers"] >= RTO_MIN_TURNOVERS, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "el sem indul" in rec["verdict"], rec


def test_response_turnover_roles_silent_with_few_turnovers():
    """Két válasz-eladásból még nincs ítélet."""
    from handball.pipeline.momentum import response_turnover_roles

    rec = response_turnover_roles(_rto_match([7, 9]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Óralopás (vezetve elhúzzák-e a támadást a hajrában) -------------------


def _clk_match(base_s, lead_s, fps=25.0):
    """Két hazai gól (vezetés), `base_s` hosszú alap-támadások, majd
    a felvétel utolsó öt percében `lead_s` hosszú hazai támadások."""
    frames = []
    t = 0

    def _attack(seconds):
        nonlocal t
        for _ in range(int(seconds * fps)):
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 28.0, 10.0)],
                                ball=Ball(x=28.2, y=10.0,
                                          confidence=1.0)))
            t += 1

    def _gap(seconds):
        nonlocal t
        for _ in range(int(seconds * fps)):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=18.0,
                                          confidence=1.0)))
            t += 1

    def _home_goal():
        nonlocal t
        for i in range(10):
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 33.0, 10.0)],
                                ball=Ball(x=min(34.0 + i, 40.4), y=10.0,
                                          confidence=1.0)))
            t += 1
        _gap(3.0)

    for _ in range(2):        # két gól: a hazai vezet
        _home_goal()
    for _ in range(4):        # alap-támadások
        _attack(base_s)
        _gap(3.0)
    _gap(120.0)               # a hajrá-ablak előtti szakasz
    for _ in range(3):        # a hajrá: vezetéses támadások
        _attack(lead_s)
        _gap(3.0)
    _gap(300.0 - 3 * (lead_s + 3.0))
    return Match(_meta(fps), frames)


def test_clock_management_flags_the_clock_killer():
    """Ha vezetve elhúzzák a támadást a hajrában, passzív jelre kell
    játszani."""
    from handball.pipeline.momentum import (CLK_MIN_ATTACKS,
                                            clock_management)

    rec = clock_management(_clk_match(6.0, 18.0))["home"]
    assert rec["lead"] >= CLK_MIN_ATTACKS, rec
    assert rec["base"] >= 4, rec
    assert rec["diff_s"] and rec["diff_s"] > 0, rec
    assert rec["verdict"] and "lopják az órát" in rec["verdict"], rec


def test_clock_management_flags_the_hurrying_leader():
    """A fordított eset: vezetve rövidebb támadás = sietnek."""
    from handball.pipeline.momentum import clock_management

    rec = clock_management(_clk_match(16.0, 6.0))["home"]
    assert rec["diff_s"] and rec["diff_s"] < 0, rec
    assert rec["verdict"] and "sietnek" in rec["verdict"], rec


def test_clock_management_silent_without_real_change():
    """Egy másodperces eltérés nem minta — az ítélet None."""
    from handball.pipeline.momentum import clock_management

    rec = clock_management(_clk_match(10.0, 9.0))["home"]
    assert rec["diff_s"] is not None and rec["verdict"] is None, rec


def test_response_turnover_players_names_the_panicking_player():
    """Ha a kapott gól után rendre ugyanaz veszíti el a labdát, a
    gólunk után az ő fogadására kell menni."""
    from handball.pipeline.momentum import (RTOP_MIN_TURNOVERS,
                                            response_turnover_players)

    rec = response_turnover_players(_rto_match([7, 7, 7, 9]))["home"]
    assert rec["turnovers"] >= 4, rec
    assert rec["top"] is not None and rec["top"]["player_id"] == 7, rec
    assert rec["top"]["turnovers"] >= RTOP_MIN_TURNOVERS, rec


def test_response_turnover_players_silent_after_one():
    """Egyetlen válasz-eladás még nem minta."""
    from handball.pipeline.momentum import response_turnover_players

    rec = response_turnover_players(_rto_match([7]))["home"]
    assert rec["top"] is None, rec


def _ctl_match(shares, fps=25.0, block_s=300.0):
    """`shares` = ötperces blokkonként a HAZAI birtoklás aránya
    (0..1). Minden blokkban a labda a megadott arányban van a hazai,
    illetve a vendég játékosnál."""
    from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                          PlayerPosition,
                                          PositionSource, Team)

    def _pl(tid, team, x, y):
        return PlayerPosition(track_id=tid, team=team, x=x, y=y,
                              source=PositionSource.MEASURED,
                              confidence=1.0)

    frames = []
    t = 0
    n = int(block_s * fps)
    for share in shares:
        hazai = int(n * share)
        for i in range(n):
            bx = 30.0 if i < hazai else 10.0
            frames.append(Frame(
                t=t,
                players=[_pl(1, Team.HOME, 30.0, 10.0),
                         _pl(21, Team.AWAY, 10.0, 10.0)],
                ball=Ball(x=bx, y=10.0, confidence=1.0)))
            t += 1
    return Match(MatchMeta(match_id="ctl", home_team="H", away_team="A",
                           fps=fps), frames)


def test_control_timeline_marks_block_owners():
    """Ötperces blokkonként megmondja, kié volt a birtoklás — és a
    blokk-mérleg alapján, ki diktált."""
    from handball.pipeline.momentum import (CTL_OWN_PCT,
                                            control_timeline)

    rec = control_timeline(_ctl_match([0.9, 0.9, 0.9, 0.2]))["home"]
    assert len(rec["blocks"]) == 4, rec["blocks"]
    assert rec["blocks"][0]["poss_pct"] >= CTL_OWN_PCT
    assert rec["won"] == 3 and rec["lost"] == 1, rec
    assert rec["verdict"] and "diktálnak" in rec["verdict"], rec
    # A vendég oldalon ugyanez a kép, fordítva.
    tukor = control_timeline(_ctl_match([0.9, 0.9, 0.9, 0.2]))["away"]
    assert tukor["won"] == 1 and tukor["lost"] == 3, tukor


def test_control_timeline_silent_with_few_blocks():
    """Két blokkból nincs ítélet."""
    from handball.pipeline.momentum import control_timeline

    rec = control_timeline(_ctl_match([0.9, 0.9]))["home"]
    assert rec["verdict"] is None and rec["best"] is None, rec


def test_restart_yield_flags_the_instant_answer():
    """Ha a kapott gólra rendre góllal válaszolnak, a gól utáni
    ünneplés ellenük tilos."""
    from handball.pipeline.momentum import (RSY_GOOD_PCT,
                                            restart_yield)

    rec = restart_yield(_rsp_match([7, 7, 7, 7]))["away"]
    assert rec["restarts"] >= 4, rec
    assert rec["answer_pct"] is not None
    assert rec["answer_pct"] >= RSY_GOOD_PCT, rec
    assert rec["verdict"] and "ünneplés" in rec["verdict"], rec


def test_restart_yield_silent_with_few_restarts():
    """Kevés mért újraindításból nincs ítélet."""
    from handball.pipeline.momentum import restart_yield

    rec = restart_yield(_rsp_match([7, 7]))["away"]
    assert rec["answer_pct"] is None and rec["verdict"] is None, rec


# --- Egálbontó emberek (parity_break_scorers) ------------------------


def _goal_with_shooter(t0, pid, toward_home_goal=False):
    """Gól-kockák LÖVŐVEL: a támadó csapat játékosa a labda indulási
    helyén áll már a lövés ELŐTT is (elő-kockák), így a detektor hozzá
    tudja rendelni a gólt."""
    if toward_home_goal:
        shooter = _pl(pid, Team.AWAY, 6.4, 10.0)
    else:
        shooter = _pl(pid, Team.HOME, 33.6, 10.0)
    frames = []
    for i in range(5):              # elő-kockák: a lövő a labdánál áll
        frames.append(Frame(t=t0 + i, players=[shooter],
                            ball=Ball(x=shooter.x, y=10.0,
                                      confidence=1.0)))
    for i in range(8):
        x = (max(6.4 - i, 0.0) if toward_home_goal
             else min(33.6 + i, 40.0))
        frames.append(Frame(t=t0 + 5 + i, players=[shooter],
                            ball=Ball(x=x, y=10.0, confidence=1.0)))
    return frames


def _pbp_match(seq):
    """seq: (irány, mez) párok időrendben — 'H'/'A' + a lövő track_id."""
    frames = []
    t = 0
    for ch, pid in seq:
        frames += _goal_with_shooter(t, pid, toward_home_goal=(ch == "A"))
        t += 13
        frames.append(Frame(t=t, players=[], ball=Ball(x=20.0, y=10.0,
                                                       confidence=1.0)))
        t += 20
    return Match(_meta(), frames)


def test_parity_break_scorers_names_the_tie_breaker():
    """HAHAHH, minden hazai egálbontó gólt a 7-es lövi → ő a
    holtpont-ember."""
    from handball.pipeline.momentum import parity_break_scorers

    m = _pbp_match([("H", 7), ("A", 21), ("H", 7), ("A", 21),
                    ("H", 7), ("H", 8)])
    rec = parity_break_scorers(m)["home"]
    assert rec["breaks"] == 3
    assert rec["top"] is not None
    assert rec["top"]["player_id"] == 7
    assert rec["top"]["share_pct"] == 100.0


def test_parity_break_scorers_spread_gives_no_top():
    """Ha az egálbontó gólok megoszlanak (mind más embertől), nincs
    kiemelt holtpont-ember."""
    from handball.pipeline.momentum import parity_break_scorers

    m = _pbp_match([("H", 7), ("A", 21), ("H", 8), ("A", 21),
                    ("H", 9), ("H", 7)])
    rec = parity_break_scorers(m)["home"]
    assert rec["breaks"] == 3
    assert rec["top"] is None
