"""
Tesztek a meccs-ablakra (game_window.py): a bemelegítés / meccs előtti
rész / lefújás utáni szakasz levágása, és a félidei szünet-sávba eső
"lövések" kiszűrése (event_detection).

Futtatás:
    python -m pytest tests/test_game_window.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.game_window import detect_game_window, trim_to_game

FPS = 5.0


def _meta():
    return MatchMeta(match_id="gw", home_team="H", away_team="A", fps=FPS)


def _pl(track_id, team, x, y):
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0)


def _seg(t0, seconds, kind):
    """Felvétel-szakasz: 'warmup' (ki-ki a saját kapujánál gyakorol),
    'game' (a két csapat EGY kapu körül, mozgásban), 'empty' (üres pálya).
    A játékosok kockánként ±0.1 m-t "remegnek" — mozognak, nem állnak."""
    frames = []
    for i in range(int(seconds * FPS)):
        wig = 0.1 if i % 2 == 0 else -0.1
        if kind == "warmup":
            players = [_pl(k, Team.HOME, 5.0 + wig, 4.0 + 2 * k)
                       for k in range(3)]
            players += [_pl(10 + k, Team.AWAY, 35.0 + wig, 4.0 + 2 * k)
                        for k in range(3)]
        elif kind == "game":
            players = [_pl(k, Team.HOME, 30.0 + wig + k * 0.5, 3.0 + 2 * k)
                       for k in range(6)]
            players += [_pl(10 + k, Team.AWAY, 32.0 + wig + k * 0.5,
                            3.0 + 2 * k) for k in range(6)]
        elif kind == "lineup":
            # Bevonulás / köszöntés: a két csapat SORBAN áll a
            # felezővonal két oldalán, mozdulatlanul (a felhasználó
            # felvételén ez a "0:00" előtti ceremónia). A súlypontok
            # közel vannak — a mozgás hiánya árulja el, hogy nem játék.
            players = [_pl(k, Team.HOME, 19.0, 3.0 + 1.2 * k)
                       for k in range(7)]
            players += [_pl(10 + k, Team.AWAY, 21.0, 3.0 + 1.2 * k)
                        for k in range(7)]
        else:
            players = []
        frames.append(Frame(t=t0 + i, players=players,
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    return frames


def test_warmup_head_is_trimmed():
    """90s bemelegítés (külön térfeleken) + 120s játék: az eleje lemegy,
    kis ráhagyással; a kockák t-je változatlan (videó-időzítés)."""
    frames = _seg(0, 90, "warmup") + _seg(int(90 * FPS), 120, "game")
    m = Match(_meta(), frames)
    info = trim_to_game(m)
    assert info is not None
    # 90s él − 15s ráhagyás = 75s vágás; az első megmaradt kocka t-je a
    # VÁGATLAN felvételbeli index (nem íródik át).
    assert info["head_cut_s"] == 75.0
    assert info["tail_cut_s"] == 0.0
    assert m.frames[0].t == int(75.0 * FPS)


def test_game_only_recording_is_untouched():
    """Csak játékot tartalmazó felvétel: nincs vágás (None), a kockák
    érintetlenek."""
    m = Match(_meta(), _seg(0, 120, "game"))
    n = len(m.frames)
    assert trim_to_game(m) is None
    assert len(m.frames) == n


def test_empty_tail_trimmed_but_kept_for_partial():
    """120s játék + 90s üres pálya: a vége lemegy — de tail=False-szal
    (részleges, folytatható feldolgozás) érintetlen marad."""
    frames = _seg(0, 120, "game") + _seg(int(120 * FPS), 90, "empty")
    m1 = Match(_meta(), list(frames))
    assert trim_to_game(m1, tail=False) is None
    assert len(m1.frames) == len(frames)

    m2 = Match(_meta(), list(frames))
    info = trim_to_game(m2)
    assert info is not None
    assert info["head_cut_s"] == 0.0
    assert info["tail_cut_s"] == 75.0  # 90s él − 15s ráhagyás


def test_short_edges_are_not_trimmed():
    """A ráhagyás alatti / rövid él (itt 30s bemelegítés) nem éri meg a
    vágást — a felvétel érintetlen."""
    frames = _seg(0, 30, "warmup") + _seg(int(30 * FPS), 120, "game")
    m = Match(_meta(), frames)
    assert trim_to_game(m) is None


def test_break_span_shots_are_filtered():
    """A félidei szünet-sávba eső "gól" (bemelegítés/labdaszedő) nem
    meccs-esemény: a detektor kiszűri, a játékbeli gól megmarad."""
    from handball.pipeline.event_detection import EventType, detect_shots

    fps = 1.0
    meta = MatchMeta(match_id="gwb", home_team="H", away_team="A", fps=fps)

    def _active(t0, n):
        return [Frame(t=t0 + i,
                      players=[_pl(k, Team.HOME, 20.0, 4.0 + 2 * k)
                               for k in range(5)],
                      ball=Ball(x=20.0, y=10.0, confidence=1.0))
                for i in range(n)]

    def _goal_frames(t0):
        xs = [30.0, 39.0, 40.0]
        return [Frame(t=t0 + i, players=[],
                      ball=Ball(x=xs[i], y=10.0, confidence=1.0))
                for i in range(3)]

    frames = []
    frames += _active(0, 50) + _goal_frames(50) + _active(53, 47)
    frames += [Frame(t=t, players=[], ball=None)      # szünet: üres pálya…
               for t in range(100, 140)]
    frames += _goal_frames(140)                       # …benne egy "gól"
    frames += [Frame(t=t, players=[], ball=None) for t in range(143, 200)]
    frames += _active(200, 100)
    m = Match(meta, frames)

    events = detect_shots(m)
    goals = [e for e in events if e.type == EventType.GOAL]
    assert len(goals) == 1
    assert goals[0].t == 51  # a játékbeli gól; a szünetbeli (t=141) kimaradt


def test_lineup_ceremony_is_not_game():
    """Bevonulás/köszöntés: a két csapat sorban áll a felezővonalnál,
    elég ember a pályán, a súlypontok is közel — de MOZGÁS nincs, tehát
    nem játék: a ceremónia a meccs-ablakon kívülre esik."""
    frames = (_seg(0, 90, "lineup")
              + _seg(int(90 * FPS), 120, "game"))
    m = Match(_meta(), frames)
    info = trim_to_game(m)
    assert info is not None, "a ceremónia után van játék, kell ablak"
    assert info["head_cut_s"] == 75.0, info
    assert m.frames[0].t == int(75.0 * FPS)


def test_lineup_only_recording_has_no_game_window():
    """Csak ceremónia (nincs játék) → nincs meccs-ablak: a rendszer nem
    talál ki meccset ott, ahol nem volt."""
    m = Match(_meta(), _seg(0, 200, "lineup"))
    assert detect_game_window(m) is None
