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


def _sby_match(n=4, concede=True):
    """`n` hazai csere; `concede` esetén minden csere után a vendég
    gólt dob (a labda a hazai kapuba száguld)."""
    frames = []
    t = 0
    for k in range(n):
        out_id, in_id = 10 + 2 * k, 11 + 2 * k
        for i in range(210):
            players = [_pl(1, Team.HOME, 25.0, 10.0)]
            if i <= 200:
                frac = i / 200.0
                players.append(_pl(out_id, Team.HOME,
                                   28.0 + (20.0 - 28.0) * frac,
                                   8.0 + (1.0 - 8.0) * frac))
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=22.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        for i in range(120):
            frac = min(1.0, i / 100.0)
            players = [_pl(1, Team.HOME, 25.0, 10.0),
                       _pl(in_id, Team.HOME,
                           20.0 + (30.0 - 20.0) * frac,
                           1.0 + (12.0 - 1.0) * frac)]
            bx = 22.0
            if concede and 20 <= i < 27:
                bx = max(6.0 - (i - 20) * 1.2, 0.0)
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=bx, y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(200):
            frames.append(Frame(
                t=t, players=[_pl(1, Team.HOME, 25.0, 10.0)],
                ball=Ball(x=22.0, y=10.0, confidence=1.0)))
            t += 1
    return Match(_meta(), frames)


def test_substitution_yield_flags_losing_change_window():
    """Ha a cseréik után rendre gólt kapnak, a csere-pillanat
    célzottan támadható."""
    from handball.pipeline.substitutions import (SBY_MIN_ROTATIONS,
                                                 substitution_yield)

    rec = substitution_yield(_sby_match())["home"]
    assert rec["rotations"] >= SBY_MIN_ROTATIONS, rec
    assert rec["diff"] < 0, rec
    assert rec["verdict"] and "célzottan támadható" in rec["verdict"], rec


def test_substitution_yield_silent_with_few_rotations():
    """Néhány cseréből nincs ítélet."""
    from handball.pipeline.substitutions import substitution_yield

    rec = substitution_yield(_sby_match(n=2))["home"]
    assert rec["verdict"] is None, rec


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


# ---- Váltópárok (ki kit vált) ----------------------------------------------

def _swp_pl(track_id, team, x, y, jersey=None):
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0,
                          jersey_number=jersey)


def _swap_pairs_match(waves, fps=25.0):
    """Egy-ki-egy-be hullámok: a `waves` elemei (ki-mezszám,
    be-mezszám) párok; minden hullám saját track-eket kap."""
    total = 1000 * (len(waves) + 1)
    frames = []
    for t in range(total):
        players = [_swp_pl(1, Team.HOME, 25.0, 10.0)]   # állandó ember
        for k, (out_j, in_j) in enumerate(waves):
            t_mid = 800 + 1000 * k
            out_tid, in_tid = 50 + 2 * k, 51 + 2 * k
            if t_mid - 300 <= t <= t_mid:
                frac = (t - (t_mid - 300)) / 300.0
                players.append(_swp_pl(
                    out_tid, Team.HOME, 28.0 - 8.0 * frac,
                    8.0 - 7.0 * frac, jersey=out_j))
            if t_mid + 10 <= t <= t_mid + 300:
                frac = min(1.0, (t - t_mid - 10) / 100.0)
                players.append(_swp_pl(
                    in_tid, Team.HOME, 20.0 + 10.0 * frac,
                    1.0 + 11.0 * frac, jersey=in_j))
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=22.0, y=10.0, confidence=1.0)))
    return Match(_meta(fps), frames)


def test_swap_pairs_finds_the_recurring_pair():
    """A 7-est háromszor is a 12-es váltja → kiszámítható váltópár."""
    from handball.pipeline.substitutions import swap_pairs

    rec = swap_pairs(_swap_pairs_match(
        [(7, 12), (7, 12), (7, 12), (8, 13)]))["home"]
    assert rec["swaps"] == 4
    assert rec["top"] == {"out_id": 7, "in_id": 12, "count": 3}
    assert rec["verdict"] == "kiszámítható váltópár"


def test_swap_pairs_without_repetition_has_no_verdict():
    """Négy különböző páros → nincs kiszámítható váltópár."""
    from handball.pipeline.substitutions import swap_pairs

    rec = swap_pairs(_swap_pairs_match(
        [(7, 12), (8, 13), (9, 14), (10, 15)]))["home"]
    assert rec["swaps"] == 4 and rec["top"] is None
    assert rec["verdict"] is None


def test_swap_pairs_needs_enough_swaps():
    """Kevés (4-nél kevesebb) mért cserénél nincs ítélet."""
    from handball.pipeline.substitutions import swap_pairs

    rec = swap_pairs(_swap_pairs_match([(7, 12), (7, 12)]))["home"]
    assert rec["swaps"] == 2 and rec["verdict"] is None


# ---- Csere-lyukak (mennyi ideig játszanak 5-en csere közben) ----------------

def _sbg_pl(tid, team, x, y):
    return PlayerPosition(track_id=tid, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0)


def _sbg_match(gap_runs_s, fps=25.0):
    """6-6 elleni játék; a `gap_runs_s` szerinti hosszú szakaszokban a
    hazaiak csak öten vannak (lassú csere)."""
    frames = []
    t = 0

    def _block(seconds, home_n):
        nonlocal t
        for _ in range(int(seconds * fps)):
            players = [_sbg_pl(100 + k, Team.HOME, 12.0 + k, 4.0 + k)
                       for k in range(home_n)]
            players += [_sbg_pl(200 + k, Team.AWAY, 24.0 + k, 4.0 + k)
                        for k in range(6)]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    _block(40, 6)
    for gap_s in gap_runs_s:
        _block(gap_s, 5)
        _block(40, 6)
    return Match(_meta(fps), frames)


def test_sub_gaps_flags_the_leaky_bench():
    """Két 25 mp-es öt fős szakasz → lyukas a cseréjük."""
    from handball.pipeline.substitutions import sub_gaps

    rec = sub_gaps(_sbg_match([25.0, 25.0]))["home"]
    assert rec["gap_s"] >= 20.0
    assert rec["verdict"] == "lyukas a cseréjük"


def test_sub_gaps_flags_the_tight_bench():
    """Létszám-hiány nélkül feszes a cseréjük."""
    from handball.pipeline.substitutions import sub_gaps

    rec = sub_gaps(_sbg_match([]))["home"]
    assert rec["gap_s"] == 0.0
    assert rec["verdict"] == "feszes a cseréjük"


def test_sub_gaps_long_shortage_is_not_a_sub_gap():
    """A 45 mp-nél hosszabb hiány kiállítás, nem csere-lyuk."""
    from handball.pipeline.substitutions import sub_gaps

    rec = sub_gaps(_sbg_match([60.0]))["home"]
    assert rec["gap_s"] == 0.0


# ---- Csere-állás (vezetve forgatnak-e) --------------------------------------

def _sbs_match(rotate=True, n_lead=5, n_rest=1, fps=25.0):
    """Hazai gól után vezetésben `n_lead`, előtte (döntetlennél)
    `n_rest` hazai cserehullám — a vezetés közbeni csere-ütem így
    összevethető a többivel."""
    goal_t = 3000
    rest_ts = [600 + k * 1200 for k in range(n_rest)]
    lead_ts = [goal_t + 400 + k * 500 for k in range(n_lead)]
    if not rotate:
        rest_ts = [600 + k * 500 for k in range(n_lead)]
        lead_ts = [goal_t + 800 + k * 1200 for k in range(n_rest)]
    plan = []
    tid = 300
    for t_wave in rest_ts + lead_ts:
        plan.append((t_wave, tid, tid + 1))
        tid += 2
    total = 6100

    frames = []
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
        # Hazai gól: a labda a +x kapuba száguld.
        if goal_t <= t <= goal_t + 6:
            ball = Ball(x=min(40.0, 33.6 + (t - goal_t)), y=10.0,
                        confidence=1.0)
        else:
            ball = Ball(x=22.0, y=10.0, confidence=1.0)
        frames.append(Frame(t=t, players=players, ball=ball))
    return Match(_meta(fps), frames)


def test_subs_by_score_flags_the_rotating_leader():
    """Vezetésben sűrű, döntetlennél ritka csere → vezetve forgatnak."""
    from handball.pipeline.substitutions import subs_by_score

    rec = subs_by_score(_sbs_match(True))["home"]
    assert rec["lead_subs"] >= 3
    assert rec["verdict"] == "vezetve forgatnak"


def test_subs_by_score_flags_the_frozen_lineup():
    """Döntetlennél sűrű, vezetve ritka csere → vezetve sem nyúlnak a
    sorhoz."""
    from handball.pipeline.substitutions import subs_by_score

    rec = subs_by_score(_sbs_match(False))["home"]
    assert rec["verdict"] == "vezetve sem nyúlnak a sorhoz"


def test_subs_by_score_needs_enough_subs():
    """Kevés (4-nél kevesebb) cserehullámnál nincs ítélet."""
    from handball.pipeline.substitutions import subs_by_score

    rec = subs_by_score(_sbs_match(True, n_lead=2, n_rest=1))["home"]
    assert rec["verdict"] is None


# ---- Csere-büntetés (gólba kerülnek-e a csere-lyukak) -----------------------

def _gpn_match(with_goals, gap_runs=2, fps=25.0):
    """Csere-lyukas meccs: a 30 mp-es öt fős szakaszok közepén a
    vendégek gólt lőnek (vagy nem) — a lyuk ára így mérhető."""
    frames = []
    t = 0

    def _block(seconds, home_n, goal_at_s=None):
        nonlocal t
        n = int(seconds * fps)
        goal_start = (None if goal_at_s is None
                      else int(goal_at_s * fps))
        for i in range(n):
            players = [_sbg_pl(100 + k, Team.HOME, 12.0 + k, 4.0 + k)
                       for k in range(home_n)]
            players += [_sbg_pl(200 + k, Team.AWAY, 24.0 + k, 4.0 + k)
                        for k in range(5)]
            if goal_start is not None and i >= goal_start:
                j = i - goal_start
                if j < 10:          # a vendég 205-ös a kapunk előtt
                    bx, px = 6.0, 6.0
                elif j < 17:        # lövés a -x kapunkba
                    bx, px = max(6.0 - (j - 9) * 1.0, -0.5), 6.0
                else:
                    bx, px = 20.0, 26.0
                players.append(_sbg_pl(205, Team.AWAY, px, 10.0))
                ball = Ball(x=bx, y=10.0, confidence=1.0)
            else:
                players.append(_sbg_pl(205, Team.AWAY, 26.0, 10.0))
                ball = Ball(x=20.0, y=10.0, confidence=1.0)
            frames.append(Frame(t=t, players=players, ball=ball))
            t += 1

    _block(40, 6)
    for _ in range(gap_runs):
        _block(30, 5, goal_at_s=(12.0 if with_goals else None))
        _block(40, 6)
    return Match(_meta(fps), frames)


def test_gap_punishment_flags_the_punished_gaps():
    """Mindkét csere-lyuk alatt gólt kapnak → gólba kerülnek."""
    from handball.pipeline.substitutions import gap_punishment

    rec = gap_punishment(_gpn_match(True))["home"]
    assert rec["gaps"] >= 2 and rec["conceded"] >= 2
    assert rec["verdict"] == "a csere-lyukaik gólba kerülnek"


def test_gap_punishment_flags_the_lucky_escape():
    """Sok lyuk-másodperc gól nélkül → büntetlenül megússzák."""
    from handball.pipeline.substitutions import gap_punishment

    rec = gap_punishment(_gpn_match(False))["home"]
    assert rec["gap_s"] >= 20.0 and rec["conceded"] == 0
    assert rec["verdict"] == "a csere-lyukakat büntetlenül megússzák"


def test_gap_punishment_no_gaps_no_verdict():
    """Lyuk nélkül nincs ítélet."""
    from handball.pipeline.substitutions import gap_punishment

    rec = gap_punishment(_gpn_match(False, gap_runs=0))["home"]
    assert rec["gap_s"] == 0.0 and rec["verdict"] is None


# ---- Forgatott-poszt (melyik posztjukat cserélik) --------------------------


def _sbr_match(out_plan, fps=25.0):
    """Poszt-minta (7/17/27: beálló-tájék, 9: szélső), majd az
    `out_plan` szerinti cserehullámok: a lecserélt a cserezónában
    tűnik el, a beálló új track ott jelenik meg."""
    spos = {7: (34.0, 10.0), 17: (33.5, 9.0), 27: (34.5, 11.0),
            9: (35.0, 3.0)}
    on_court = dict(spos)   # track_id -> aktuális hely

    frames = []
    t = 0
    for _ in range(150):             # poszt-minta: hazai birtoklás elöl
        frames.append(Frame(
            t=t,
            players=[_pl(tid, Team.HOME, *xy)
                     for tid, xy in on_court.items()],
            ball=Ball(x=34.2, y=10.0, confidence=1.0)))
        t += 1
    for (out_tid, in_tid) in out_plan:
        spot = on_court[out_tid]
        for i in range(50):          # a lecserélt a zóna felé tart
            frac = (i + 1) / 50.0
            x = spot[0] + (20.0 - spot[0]) * frac
            y = spot[1] + (1.0 - spot[1]) * frac
            players = [_pl(tid, Team.HOME, *xy)
                       for tid, xy in on_court.items()
                       if tid != out_tid] + [_pl(out_tid, Team.HOME,
                                                 x, y)]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=25.0, y=16.0,
                                          confidence=1.0)))
            t += 1
        del on_court[out_tid]        # eltűnik a zónában
        for _ in range(10):
            frames.append(Frame(
                t=t,
                players=[_pl(tid, Team.HOME, *xy)
                         for tid, xy in on_court.items()],
                ball=Ball(x=25.0, y=16.0, confidence=1.0)))
            t += 1
        for i in range(50):          # az új track a zónából áll be
            frac = (i + 1) / 50.0
            x = 20.0 + (spot[0] - 20.0) * frac
            y = 1.0 + (spot[1] - 1.0) * frac
            players = [_pl(tid, Team.HOME, *xy)
                       for tid, xy in on_court.items()] \
                + [_pl(in_tid, Team.HOME, x, y)]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=25.0, y=16.0,
                                          confidence=1.0)))
            t += 1
        on_court[in_tid] = spot
        for _ in range(250):         # két hullám közt eltelik az idő
            frames.append(Frame(
                t=t,
                players=[_pl(tid, Team.HOME, *xy)
                         for tid, xy in on_court.items()],
                ball=Ball(x=25.0, y=16.0, confidence=1.0)))
            t += 1
    for _ in range(150):             # záró poszt-minta a beállókkal
        frames.append(Frame(
            t=t,
            players=[_pl(tid, Team.HOME, *xy)
                     for tid, xy in on_court.items()],
            ball=Ball(x=34.2, y=10.0, confidence=1.0)))
        t += 1
    return Match(_meta(), frames)


def test_substituted_roles_names_the_rotated_post():
    """Négy cseréből három a beálló-tájékot érinti → a fárasztást a
    nem forgatott posztokra kell tenni."""
    from handball.pipeline.substitutions import (SBR_MIN_OUTS,
                                                 substituted_roles)

    rec = substituted_roles(
        _sbr_match([(7, 107), (17, 117), (27, 127),
                    (9, 119)]))["home"]
    assert rec["outs"] >= SBR_MIN_OUTS, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "friss ember" in rec["verdict"], rec


def test_substituted_roles_silent_with_few_subs():
    """Néhány cseréből nincs ítélet."""
    from handball.pipeline.substitutions import substituted_roles

    rec = substituted_roles(_sbr_match([(7, 107), (9, 119)]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Beérkező-poszt (melyik posztra hoz frissítést a padjuk) ---------------


def test_sub_in_roles_names_the_refreshed_post():
    """Négy beállásból három a beálló-tájékra érkezik → a hullám után
    arra a sávra kell váltani."""
    from handball.pipeline.substitutions import (IBR_MIN_INS,
                                                 sub_in_roles)

    rec = sub_in_roles(
        _sbr_match([(7, 107), (17, 117), (27, 127),
                    (9, 119)]))["home"]
    assert rec["ins"] >= IBR_MIN_INS, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "friss láb" in rec["verdict"], rec


def test_sub_in_roles_silent_with_few_ins():
    """Néhány beállásból nincs ítélet."""
    from handball.pipeline.substitutions import sub_in_roles

    rec = sub_in_roles(_sbr_match([(7, 107), (9, 119)]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Csere-stílus (posztot tart vagy átszab a pad) -------------------------


def _sws_match(swaps, fps=25.0):
    """Poszt-minta + cserehullámok: a `swaps` elemei (ki, be,
    be-hely) hármasok — a be-hely None esetén a beálló a lecserélt
    helyét veszi át (posztot tartó), különben a megadott új helyre
    áll (átszabó)."""
    spos = {7: (34.0, 10.0), 17: (33.5, 9.0), 27: (34.5, 11.0),
            9: (35.0, 3.0)}
    on_court = dict(spos)

    frames = []
    t = 0
    for _ in range(150):             # poszt-minta: hazai birtoklás elöl
        frames.append(Frame(
            t=t,
            players=[_pl(tid, Team.HOME, *xy)
                     for tid, xy in on_court.items()],
            ball=Ball(x=34.2, y=10.0, confidence=1.0)))
        t += 1
    for (out_tid, in_tid, in_spot) in swaps:
        spot = on_court[out_tid]
        dest = in_spot if in_spot is not None else spot
        for i in range(50):          # a lecserélt a zóna felé tart
            frac = (i + 1) / 50.0
            x = spot[0] + (20.0 - spot[0]) * frac
            y = spot[1] + (1.0 - spot[1]) * frac
            players = [_pl(tid, Team.HOME, *xy)
                       for tid, xy in on_court.items()
                       if tid != out_tid] + [_pl(out_tid, Team.HOME,
                                                 x, y)]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=25.0, y=16.0,
                                          confidence=1.0)))
            t += 1
        del on_court[out_tid]
        for _ in range(10):
            frames.append(Frame(
                t=t,
                players=[_pl(tid, Team.HOME, *xy)
                         for tid, xy in on_court.items()],
                ball=Ball(x=25.0, y=16.0, confidence=1.0)))
            t += 1
        for i in range(50):          # az új track a zónából áll be
            frac = (i + 1) / 50.0
            x = 20.0 + (dest[0] - 20.0) * frac
            y = 1.0 + (dest[1] - 1.0) * frac
            players = [_pl(tid, Team.HOME, *xy)
                       for tid, xy in on_court.items()] \
                + [_pl(in_tid, Team.HOME, x, y)]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=25.0, y=16.0,
                                          confidence=1.0)))
            t += 1
        on_court[in_tid] = dest
        for _ in range(250):         # két hullám közt eltelik az idő
            frames.append(Frame(
                t=t,
                players=[_pl(tid, Team.HOME, *xy)
                         for tid, xy in on_court.items()],
                ball=Ball(x=25.0, y=16.0, confidence=1.0)))
            t += 1
    bx, by = next(iter(on_court.values()))
    for _ in range(150):             # záró poszt-minta a beállókkal
        frames.append(Frame(
            t=t,
            players=[_pl(tid, Team.HOME, *xy)
                     for tid, xy in on_court.items()],
            ball=Ball(x=bx + 0.2, y=by, confidence=1.0)))
        t += 1
    return Match(_meta(), frames)


def test_swap_style_names_the_post_keeping_bench():
    """Három azonos-posztú váltás → posztot tartó pad."""
    from handball.pipeline.substitutions import swap_style

    rec = swap_style(_sws_match(
        [(7, 107, None), (17, 117, None), (27, 127, None)]))["home"]
    assert rec["pairs"] >= 3, rec
    assert rec["same_pct"] and rec["same_pct"] >= 70.0, rec
    assert rec["verdict"] and "posztot tartó" in rec["verdict"], rec


def test_swap_style_names_the_reshaping_bench():
    """Három átszabó váltás (beálló-tájék ki, szélső-hely be) →
    átszabó pad."""
    from handball.pipeline.substitutions import swap_style

    rec = swap_style(_sws_match(
        [(7, 107, (36.0, 17.0)), (17, 117, (36.0, 2.0)),
         (27, 127, (28.5, 10.0))]))["home"]
    assert rec["pairs"] >= 3, rec
    assert rec["same_pct"] is not None and rec["same_pct"] <= 40.0, rec
    assert rec["verdict"] and "átszabó" in rec["verdict"], rec


def test_swap_style_silent_with_few_pairs():
    """Kevés ki-be párosból nincs ítélet."""
    from handball.pipeline.substitutions import swap_style

    rec = swap_style(_sws_match(
        [(7, 107, None), (9, 119, None)]))["home"]
    assert rec["same_pct"] is None and rec["verdict"] is None, rec


def _phase_match(holder: Team, n_waves=4, fps=25.0):
    """`n_waves` egyfős HAZAI cserehullám; a labdát végig a megadott
    csapat 1-es játékosa tartja (a csere-fázis ebből dől el)."""
    frames = []
    plan = []
    tid = 500
    for k in range(n_waves):
        plan.append((400 + k * 900, tid, tid + 1))
        tid += 2
    total = 400 + n_waves * 900 + 300

    for t in range(total):
        players = [_pl(1, holder, 25.0, 10.0)]
        # A másik csapat egy embere távolabb áll (ne ő legyen a labdás).
        players.append(_pl(2, Team.AWAY if holder == Team.HOME else Team.HOME,
                           12.0, 4.0))
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
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=25.0, y=10.0, confidence=1.0)))
    return Match(_meta(fps), frames)


def test_substitution_phase_flags_the_risky_rotation():
    """Ha a cserék az ELLENFÉL birtoklása közben indulnak, kockázatos
    csere-rend (a fal egy emberrel kevesebbel áll fel)."""
    from handball.pipeline.substitutions import substitution_phase

    rec = substitution_phase(_phase_match(Team.AWAY))["home"]
    assert rec["subs"] == 4, rec
    assert rec["opp_ball"] == 4 and rec["own_ball"] == 0, rec
    assert rec["risky_pct"] == 100.0
    assert rec["verdict"] == "védekezés közben is cserélnek (kockázatos)"


def test_substitution_phase_flags_the_disciplined_rotation():
    """Saját birtoklás közbeni cserék → fegyelmezett csere-rend."""
    from handball.pipeline.substitutions import substitution_phase

    rec = substitution_phase(_phase_match(Team.HOME))["home"]
    assert rec["own_ball"] == 4 and rec["opp_ball"] == 0, rec
    assert rec["risky_pct"] == 0.0
    assert rec["verdict"] == ("fegyelmezett csere-rend "
                              "(birtokláskor váltanak)")


def test_substitution_phase_silent_on_few_subs():
    """Kevés cserénél nincs ítélet (sose hallgatólagos csere-rend)."""
    from handball.pipeline.substitutions import substitution_phase

    rec = substitution_phase(_phase_match(Team.AWAY, n_waves=2))["home"]
    assert rec["subs"] == 2 and rec["verdict"] is None, rec
    assert rec["risky_pct"] is None, rec
