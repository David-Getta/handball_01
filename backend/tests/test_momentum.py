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
        for i in range(8):
            fr.append(Frame(
                t=t0 + i,
                players=[PlayerPosition(track_id=1, team=Team.HOME,
                                        x=shooter_x, y=10.0,
                                        source=PositionSource.MEASURED,
                                        confidence=1.0)],
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
