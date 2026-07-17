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
