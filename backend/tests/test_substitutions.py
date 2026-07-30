"""
Tesztek a csere-felismerésre (substitutions.py).

A pálya 40x20 m; a cserezóna a felezővonal ±4,5 m-e az oldalvonal mellett.

Futtatás:
    python -m pytest tests/test_substitutions.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.substitutions import (
    detect_substitutions, substitution_impact,
)


def _meta(fps=25.0):
    return MatchMeta(match_id="sub", home_team="H", away_team="A", fps=fps)


def _pl(track_id, team, x, y, role=None):
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0,
                          role=role)


def _sub_match(out_end=(20.0, 1.0), in_start=(20.0, 1.0)):
    """Az 5-ös hazai track a cserezónában ér véget (t=200), a 6-os ott
    kezdődik (t=210) — közben egy állandó játékos végig a pályán van."""
    frames = []
    for t in range(600):
        players = [_pl(1, Team.HOME, 25.0, 10.0)]  # állandó játékos
        if t <= 200:
            # Az 5-ös a pálya közepéről a cserezóna felé tart, ott tűnik el.
            frac = t / 200.0
            x = 28.0 + (out_end[0] - 28.0) * frac
            y = 8.0 + (out_end[1] - 8.0) * frac
            players.append(_pl(5, Team.HOME, x, y))
        if t >= 210:
            # A 6-os a cserezónában jelenik meg, majd beáll a helyére.
            frac = min(1.0, (t - 210) / 100.0)
            x = in_start[0] + (30.0 - in_start[0]) * frac
            y = in_start[1] + (12.0 - in_start[1]) * frac
            players.append(_pl(6, Team.HOME, x, y))
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=22.0, y=10.0, confidence=1.0)))
    return Match(_meta(), frames)


def test_substitution_detected_at_zone():
    subs = detect_substitutions(_sub_match())
    assert len(subs) == 1
    ev = subs[0]
    assert ev["team"] == "home"
    assert ev["out_ids"] == [5] and ev["in_ids"] == [6]
    assert abs(ev["t"] - 200) <= 2


def test_mid_court_track_break_is_not_substitution():
    """A pálya közepén megszakadó követés (takarás) nem csere."""
    m = _sub_match(out_end=(28.0, 10.0), in_start=(30.0, 12.0))
    assert detect_substitutions(m) == []


def test_impact_counts_goals_after():
    """A csere utáni ablakban esett gól a mérlegbe kerül."""
    m = _sub_match()
    # Hazai gól a csere után (t≈300): a labda a +x kapuba száguld.
    for i, f in enumerate(m.frames):
        if 300 <= f.t < 307:
            f.ball = Ball(x=34.0 + (f.t - 300), y=10.0, confidence=1.0)
    r = substitution_impact(m)
    assert r["teams"]["home"]["rotations"] == 1
    assert r["teams"]["home"]["goals_for_after"] == 1
    assert r["teams"]["home"]["goals_against_after"] == 0
    assert r["events"][0]["goals_for_after"] == 1


def test_late_sub_flags_fading_player_left_on_court():
    """A 2. félidőben 20%+ tempót eső, le nem cserélt játékos késő-csere
    jelzést kap; az egyenletes tempójú nem."""
    from handball.pipeline.substitutions import late_sub_flags

    frames = []
    n_half = 1000  # 40 mp félidőnként (25 fps)
    x1 = 5.0
    x3 = 5.0
    for t in range(2 * n_half):
        # 1-es: az első félidőben 2 m/s, a másodikban 1 m/s (esés 50%).
        v1 = 0.08 if t < n_half else 0.04
        x1 += v1
        if x1 > 35.0:
            x1 = 5.0
        # 3-as: végig 1,5 m/s (nincs érdemi esés).
        x3 += 0.06
        if x3 > 35.0:
            x3 = 5.0
        frames.append(Frame(t=t, players=[
            _pl(1, Team.HOME, x1, 8.0),
            _pl(3, Team.HOME, x3, 12.0),
        ]))
    flags = late_sub_flags(Match(_meta(), frames))
    ids = [f["track_id"] for f in flags]
    assert 1 in ids
    assert 3 not in ids
    top = next(f for f in flags if f["track_id"] == 1)
    assert top["drop_pct"] >= 20.0


def _waves_match(sizes):
    """Cserehullámok egymás után: a `sizes` elemenként megadja, hány
    ember megy ki és jön be az adott hullámban. A kimenő track-ek a
    cserezónában érnek véget, a bejövők ott kezdődnek."""
    frames = []
    plan = []       # (t, méret, kimenő id-k, bejövő id-k)
    tid = 100
    for k, size in enumerate(sizes):
        t_wave = 200 + k * 400
        outs = list(range(tid, tid + size))
        tid += size
        ins = list(range(tid, tid + size))
        tid += size
        plan.append((t_wave, outs, ins))
    total = 200 + len(sizes) * 400 + 300
    for t in range(total):
        players = [_pl(1, Team.HOME, 25.0, 10.0)]   # állandó játékos
        for (t_wave, outs, ins) in plan:
            if t_wave - 150 <= t <= t_wave:
                # A kimenők a cserezóna felé tartanak (ott tűnnek el).
                frac = (t - (t_wave - 150)) / 150.0
                for j, oid in enumerate(outs):
                    players.append(_pl(oid, Team.HOME,
                                       28.0 + (20.0 - 28.0) * frac,
                                       8.0 + (1.0 - 8.0) * frac
                                       + 0.2 * j))
            if t_wave + 10 <= t <= t_wave + 150:
                # A bejövők a cserezónából állnak be.
                frac = (t - (t_wave + 10)) / 140.0
                for j, iid in enumerate(ins):
                    players.append(_pl(iid, Team.HOME,
                                       20.0 + 10.0 * frac,
                                       1.0 + 11.0 * frac + 0.2 * j))
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=22.0, y=10.0, confidence=1.0)))
    return Match(_meta(), frames)


def test_substitution_blocks_separates_units_from_single_swaps():
    """Négy hullámból kettő 2 fős → "blokkos csere"; csupa egyfős
    hullámnál "egyesével"; kevés hullámnál nincs ítélet."""
    from handball.pipeline.substitutions import substitution_blocks

    blocks = substitution_blocks(_waves_match([2, 2, 1, 1]))["home"]
    assert blocks["waves"] == 4
    assert blocks["block_waves"] == 2
    assert blocks["players"] == 6
    assert blocks["block_pct"] == 50.0
    assert blocks["avg_size"] == 1.5
    assert blocks["verdict"] == "blokkos csere"

    singles = substitution_blocks(_waves_match([1, 1, 1, 1]))["home"]
    assert singles["waves"] == 4 and singles["block_waves"] == 0
    assert singles["verdict"] == "egyesével"

    # Két hullám: nincs elég minta → nincs arány és nincs ítélet.
    few = substitution_blocks(_waves_match([2, 1]))["home"]
    assert few["block_pct"] is None and few["verdict"] is None
    # A vendég nem cserélt.
    assert substitution_blocks(
        _waves_match([2, 2, 1, 1]))["away"]["waves"] == 0


# ---- Csere-kiváltók (kapott gól után cserélnek-e) ----------------------------

def _trigger_match(n_waves=4, goals_before=(), fps=25.0):
    """`n_waves` egyfős hazai cserehullám; a `goals_before` indexű
    hullámok elé 4 másodperccel vendég-gól kerül (a hazai kap gólt)."""
    frames = []
    plan = []
    tid = 300
    for k in range(n_waves):
        # A hullámok közt több mint 30 mp (750 kocka) telik el, hogy egy
        # gól csak a hozzá tartozó cserét jelölje reaktívnak.
        t_wave = 400 + k * 900
        plan.append((t_wave, tid, tid + 1))
        tid += 2
    goal_ts = {plan[k][0] - 100 for k in goals_before}
    total = 400 + n_waves * 900 + 300

    for t in range(total):
        players = [_pl(1, Team.HOME, 25.0, 10.0)]
        for (t_wave, out_id, in_id) in plan:
            if t_wave - 150 <= t <= t_wave:
                frac = (t - (t_wave - 150)) / 150.0
                players.append(_pl(out_id, Team.HOME,
                                   28.0 + (20.0 - 28.0) * frac,
                                   8.0 + (1.0 - 8.0) * frac))
            if t_wave + 10 <= t <= t_wave + 150:
                frac = (t - (t_wave + 10)) / 140.0
                players.append(_pl(in_id, Team.HOME,
                                   20.0 + 10.0 * frac,
                                   1.0 + 11.0 * frac))
        # Vendég-gól: a labda a hazai (−x) kapuba száguld.
        goal_now = next((g for g in goal_ts if g <= t <= g + 6), None)
        if goal_now is not None:
            ball = Ball(x=max(0.0, 6.4 - (t - goal_now)), y=10.0,
                        confidence=1.0)
        else:
            ball = Ball(x=22.0, y=10.0, confidence=1.0)
        frames.append(Frame(t=t, players=players, ball=ball))
    return Match(_meta(fps), frames)


def test_substitution_triggers_flags_the_reactive_bench():
    """Négy cseréből három kapott gól után jön → reaktív csere-rend."""
    from handball.pipeline.substitutions import substitution_triggers

    rec = substitution_triggers(
        _trigger_match(goals_before=(0, 1, 2)))["home"]
    assert rec["subs"] == 4
    assert rec["after_conceded"] == 3
    assert rec["share_pct"] == 75.0
    assert rec["verdict"] == "kapott gólra cserélnek"


def test_substitution_triggers_flags_the_planned_bench():
    """Kapott gól nélküli cserék → tervezett csere-rend."""
    from handball.pipeline.substitutions import substitution_triggers

    rec = substitution_triggers(_trigger_match())["home"]
    assert rec["after_conceded"] == 0 and rec["share_pct"] == 0.0
    assert rec["verdict"] == "tervezett csere-rend"


def test_substitution_triggers_needs_enough_subs():
    """Kevés (4-nél kevesebb) cserénél nincs ítélet."""
    from handball.pipeline.substitutions import substitution_triggers

    rec = substitution_triggers(_trigger_match(n_waves=2))["home"]
    assert rec["share_pct"] is None and rec["verdict"] is None
