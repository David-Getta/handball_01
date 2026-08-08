"""
Tesztek a játékmegszakítás/időkérés-felismerésre (stoppages.py).

Futtatás:
    python -m pytest tests/test_stoppages.py
"""

from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.stoppages import detect_stoppages


def _meta(fps=25.0):
    return MatchMeta(match_id="st", home_team="H", away_team="A", fps=fps)


def _players(t, moving):
    """8 játékos (4-4): mozgásban körpályán, álláskor fix helyen."""
    out = []
    for k in range(8):
        team = Team.HOME if k < 4 else Team.AWAY
        bx, by = 12.0 + 2.0 * k, 6.0 + (k % 4) * 2.5
        if moving:
            bx += 2.0 * math.sin(t / 5.0 + k)
            by += 1.5 * math.cos(t / 4.0 + k)
        out.append(PlayerPosition(track_id=k + 1, team=team, x=bx, y=by,
                                  source=PositionSource.MEASURED,
                                  confidence=1.0))
    return out


def _match(move1_s=20, stop_s=25, move2_s=20, fps=25.0, holder_team=Team.HOME):
    """Mozgás → állás → mozgás; az állás előtt a labda a holder_team-nél."""
    frames = []
    t = 0
    for _ in range(int(move1_s * fps)):
        players = _players(t, moving=True)
        # A labda a leállás előtt a hazai 1-es (vagy vendég 5-ös) kezében.
        hid = 1 if holder_team == Team.HOME else 5
        hp = players[hid - 1]
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=hp.x, y=hp.y, confidence=1.0)))
        t += 1
    for _ in range(int(stop_s * fps)):
        frames.append(Frame(t=t, players=_players(0, moving=False),
                            ball=None))
        t += 1
    for _ in range(int(move2_s * fps)):
        frames.append(Frame(t=t, players=_players(t, moving=True),
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    return Match(_meta(fps), frames)


def test_timeout_detected_with_likely_team():
    stops = detect_stoppages(_match())
    assert len(stops) == 1
    s = stops[0]
    assert s["kind"] == "időkérés"
    assert 20.0 <= s["duration_s"] <= 30.0
    assert s["likely_team"] == "home"  # a leállás előtt a hazai birtokolt


def test_no_stoppage_during_normal_play():
    stops = detect_stoppages(_match(stop_s=0))
    assert stops == []


def test_short_stop_ignored():
    """Egy rövid (5 mp) állás — pl. szabaddobás — nem megszakítás."""
    assert detect_stoppages(_match(stop_s=5)) == []


def test_long_stop_is_not_timeout():
    """A 2 percnél hosszabb leállás nem időkérés (sérülés/félidő)."""
    stops = detect_stoppages(_match(stop_s=130))
    assert len(stops) == 1
    assert stops[0]["kind"] == "hosszú megszakítás"


def test_empty_frames_are_not_stoppage():
    """Üres (követés-vesztett) képkockák nem számítanak leállásnak."""
    frames = [Frame(t=t, players=[], ball=None) for t in range(1000)]
    assert detect_stoppages(Match(_meta(), frames)) == []


# ---- Időkérés-hatás (megtörte-e a sorozatot) ---------------------------------

from handball.pipeline.stoppages import timeout_effects


def _goal_frames(t0, toward_home_goal):
    """Gól-kockák: a labda a kapuba száguld (8 játékos áll a pályán, hogy a
    leállás-jel ne zavarodjon össze — ők mozognak közben)."""
    frames = []
    for i in range(7):
        x = (6.4 - i) if toward_home_goal else (34.0 + i)
        frames.append(Frame(t=t0 + i, players=_players(t0 + i, moving=True),
                            ball=Ball(x=max(0.0, min(40.0, x)), y=10.0,
                                      confidence=1.0)))
    return frames


def test_timeout_that_breaks_the_run():
    """A hazai 2 gólt kap → időkérés → utána nincs kapott gól → "megtörte"."""
    fps = 25.0
    frames = []
    t = 0
    # Mozgás + 2 vendég-gól (a -x kapura → a HAZAI kapja).
    for _ in range(int(20 * fps)):
        players = _players(t, moving=True)
        hp = players[0]  # a hazai 1-es birtokol (ő "kéri" majd az időt)
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=hp.x, y=hp.y, confidence=1.0)))
        t += 1
    for g in _goal_frames(t, toward_home_goal=True):
        frames.append(g)
    t = frames[-1].t + 1
    for _ in range(int(3 * fps)):  # kis szünet a két gól közt (debounce)
        players = _players(t, moving=True)
        hp = players[0]
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=hp.x, y=hp.y, confidence=1.0)))
        t += 1
    for g in _goal_frames(t, toward_home_goal=True):
        frames.append(g)
    t = frames[-1].t + 1
    # A hazai birtokol pár mp-ig, majd időkérés (20 mp állás).
    for _ in range(int(4 * fps)):
        players = _players(t, moving=True)
        hp = players[0]
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=hp.x, y=hp.y, confidence=1.0)))
        t += 1
    for _ in range(int(20 * fps)):
        frames.append(Frame(t=t, players=_players(0, moving=False), ball=None))
        t += 1
    # Utána mozgás, kapott gól nélkül.
    for _ in range(int(30 * fps)):
        frames.append(Frame(t=t, players=_players(t, moving=True),
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1

    effects = [e for e in timeout_effects(Match(_meta(fps), frames))
               if e["kind"] == "időkérés"]
    assert len(effects) == 1
    e = effects[0]
    assert e["likely_team"] == "home"
    assert e["conceded_before"] == 2 and e["conceded_after"] == 0
    assert e["verdict"] == "megtörte a sorozatot"


def test_timeout_without_prior_run_has_no_verdict():
    """Ha az időkérés előtt nem volt kapott gól-sorozat, nincs ítélet."""
    effects = [e for e in timeout_effects(_match())
               if e["kind"] == "időkérés"]
    assert len(effects) == 1
    assert effects[0]["verdict"] is None
    assert effects[0]["conceded_before"] == 0


def test_timeout_record_aggregates_verdicts():
    """A "megtörte" ítéletű hazai időkérés a hazai mérlegben broke-ként
    jelenik meg; a vendégnek nincs időkérése."""
    from handball.pipeline.stoppages import timeout_record

    fps = 25.0
    frames = []
    t = 0
    for _ in range(int(20 * fps)):
        players = _players(t, moving=True)
        hp = players[0]
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=hp.x, y=hp.y, confidence=1.0)))
        t += 1
    for g in _goal_frames(t, toward_home_goal=True):
        frames.append(g)
    t = frames[-1].t + 1
    for _ in range(int(3 * fps)):
        players = _players(t, moving=True)
        hp = players[0]
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=hp.x, y=hp.y, confidence=1.0)))
        t += 1
    for g in _goal_frames(t, toward_home_goal=True):
        frames.append(g)
    t = frames[-1].t + 1
    for _ in range(int(4 * fps)):
        players = _players(t, moving=True)
        hp = players[0]
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=hp.x, y=hp.y, confidence=1.0)))
        t += 1
    for _ in range(int(20 * fps)):
        frames.append(Frame(t=t, players=_players(0, moving=False),
                            ball=None))
        t += 1
    for _ in range(int(30 * fps)):
        frames.append(Frame(t=t, players=_players(t, moving=True),
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1

    rec = timeout_record(Match(_meta(fps), frames))
    assert rec["home"]["timeouts"] == 1
    assert rec["home"]["broke"] == 1 and rec["home"]["failed"] == 0
    assert rec["away"]["timeouts"] == 0


# ---- Időkérés-időzítés (hány kapott gól után fékeznek) -----------------------

def _timeout_match(counts, fps=25.0):
    """Hazai időkérés-sorozat: a `counts` elemenként megadja, hány
    vendég-gól (a hazai kapujába) előzi meg az adott időkérést."""
    frames = []
    t = 0

    def _play(seconds):
        """Hazai birtoklás — a leállás előtt ő "kéri" majd az időt."""
        nonlocal t, frames
        for _ in range(int(seconds * fps)):
            players = _players(t, moving=True)
            hp = players[0]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=hp.x, y=hp.y,
                                          confidence=1.0)))
            t += 1

    for n_goals in counts:
        _play(10)
        for _ in range(n_goals):
            for g in _goal_frames(t, toward_home_goal=True):
                frames.append(g)
            t = frames[-1].t + 1
            _play(3)          # debounce a gólok közt
        _play(4)
        for _ in range(int(20 * fps)):   # időkérés (20 mp állás)
            frames.append(Frame(t=t, players=_players(0, moving=False),
                                ball=None))
            t += 1
        # Hosszú játék a következő kör előtt: a 120 mp-es hatás-ablak
        # ne lásson át az előző kör góljaira.
        _play(130)
    return Match(_meta(fps), frames)


def test_timeout_timing_separates_early_and_late_brakes():
    """Két időkérés egy-egy kapott gól után → "gyors fék"; három, majd
    két kapott gól után → "hagyják elszaladni"; egyetlen időkérésnél
    nincs ítélet."""
    from handball.pipeline.stoppages import timeout_timing

    early = timeout_timing(_timeout_match([1, 1]))["home"]
    assert early["timeouts"] == 2
    assert early["sum_before"] == 2
    assert early["avg_before"] == 1.0
    assert early["verdict"] == "gyors fék"

    late = timeout_timing(_timeout_match([3, 2]))["home"]
    assert late["timeouts"] == 2 and late["sum_before"] == 5
    assert late["avg_before"] == 2.5
    assert late["verdict"] == "hagyják elszaladni"

    # Egyetlen időkérés: kevés minta → nincs arány és nincs ítélet.
    one = timeout_timing(_timeout_match([3]))["home"]
    assert one["avg_before"] is None and one["verdict"] is None
    # A vendég nem kért időt.
    assert timeout_timing(_timeout_match([1, 1]))["away"]["timeouts"] == 0


# ---- Effektív játékidő -------------------------------------------------------

def test_playing_time_profile_flags_the_broken_match():
    """11 perc játék, benne két hosszú (2×90 mp) megszakítás → az
    effektív arány 80% alatt: szakadozott meccskép."""
    from handball.pipeline.stoppages import playing_time_profile

    fps = 25.0
    frames = []
    t = 0

    def _play(seconds):
        nonlocal t, frames
        for _ in range(int(seconds * fps)):
            players = _players(t, moving=True)
            hp = players[0]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=hp.x, y=hp.y,
                                          confidence=1.0)))
            t += 1

    def _stop(seconds):
        nonlocal t, frames
        for _ in range(int(seconds * fps)):
            frames.append(Frame(t=t, players=_players(0, moving=False),
                                ball=None))
            t += 1

    _play(240)
    _stop(90)
    _play(180)
    _stop(90)
    _play(60)
    rec = playing_time_profile(Match(_meta(fps), frames))["home"]
    assert rec["stoppages"] == 2
    assert rec["stopped_s"] >= 175.0
    assert rec["effective_pct"] < 80.0
    assert rec["verdict"] == "szakadozott meccskép"
    # A megszakítások előtt a hazai birtokolt: nála állt meg a játék.
    assert rec["own_stoppages"] == 2


def test_playing_time_profile_flags_the_flowing_match():
    """Megszakítás nélküli 11 perc → folyamatos meccs."""
    from handball.pipeline.stoppages import playing_time_profile

    fps = 25.0
    frames = []
    for t in range(int(660 * fps)):
        players = _players(t, moving=True)
        hp = players[0]
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=hp.x, y=hp.y, confidence=1.0)))
    rec = playing_time_profile(Match(_meta(fps), frames))["home"]
    assert rec["stoppages"] == 0 and rec["effective_pct"] == 100.0
    assert rec["verdict"] == "folyamatos meccs"


def test_playing_time_profile_needs_enough_minutes():
    """Rövid (10 percnél kevesebb) felvételnél nincs ítélet."""
    from handball.pipeline.stoppages import playing_time_profile

    rec = playing_time_profile(_match())["home"]
    assert rec["verdict"] is None


# ---- Időkérés utáni első támadás ---------------------------------------------

def _tfa_match(scored_after, fps=25.0):
    """Hazai időkérés-sorozat: a `scored_after` elemenként megadja,
    hogy az adott időkérés után jön-e hazai gól."""
    frames = []
    t = 0

    def _play(seconds):
        nonlocal t, frames
        for _ in range(int(seconds * fps)):
            players = _players(t, moving=True)
            hp = players[0]      # a hazai 1-es birtokol (ő kér időt)
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=hp.x, y=hp.y,
                                          confidence=1.0)))
            t += 1

    for scored in scored_after:
        _play(10)
        for _ in range(int(20 * fps)):     # időkérés: 20 mp állás
            frames.append(Frame(t=t, players=_players(0, moving=False),
                                ball=None))
            t += 1
        if scored:
            for i in range(7):             # hazai gól a +x kapura
                frames.append(Frame(
                    t=t, players=_players(t, moving=True),
                    ball=Ball(x=min(34.0 + i, 40.0), y=10.0,
                              confidence=1.0)))
                t += 1
        _play(60)
    return Match(_meta(fps), frames)


def test_timeout_first_attack_flags_the_ready_play():
    """Négy időkérésből három után gól jön → kész figurájuk van."""
    from handball.pipeline.stoppages import timeout_first_attack

    rec = timeout_first_attack(
        _tfa_match([True, True, True, False]))["home"]
    assert rec["timeouts"] == 4 and rec["goals"] == 3
    assert rec["share_pct"] == 75.0
    assert rec["verdict"] == "kész figura az időkérés után"


def test_timeout_first_attack_flags_the_empty_timeout():
    """Ha az időkérések után nem jön gól, üres az időkérés."""
    from handball.pipeline.stoppages import timeout_first_attack

    rec = timeout_first_attack(_tfa_match([False] * 4))["home"]
    assert rec["goals"] == 0 and rec["share_pct"] == 0.0
    assert rec["verdict"] == "üres időkérés"


def test_timeout_first_attack_needs_enough_timeouts():
    """Kevés (3-nál kevesebb) időkérésnél nincs ítélet."""
    from handball.pipeline.stoppages import timeout_first_attack

    rec = timeout_first_attack(_tfa_match([True, False]))["home"]
    assert rec["share_pct"] is None and rec["verdict"] is None


# ---- Időkérés utáni védekezés (megáll-e a fal a megszakítás után) -----------

def _tfd_match(conceded_after, fps=25.0):
    """Hazai időkérés-sorozat: a `conceded_after` elemenként megadja,
    hogy az adott időkérés után jön-e VENDÉG gól."""
    frames = []
    t = 0

    def _play(seconds):
        nonlocal t, frames
        for _ in range(int(seconds * fps)):
            players = _players(t, moving=True)
            hp = players[0]      # a hazai 1-es birtokol (ő kér időt)
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=hp.x, y=hp.y,
                                          confidence=1.0)))
            t += 1

    for conceded in conceded_after:
        _play(10)
        for _ in range(int(20 * fps)):     # időkérés: 20 mp állás
            frames.append(Frame(t=t, players=_players(0, moving=False),
                                ball=None))
            t += 1
        if conceded:
            for i in range(7):             # vendég gól a 0-s kapura
                players = _players(t, moving=True)
                players.append(PlayerPosition(
                    track_id=20, team=Team.AWAY, x=6.0, y=10.0,
                    source=PositionSource.MEASURED, confidence=1.0))
                frames.append(Frame(
                    t=t, players=players,
                    ball=Ball(x=max(6.0 - i, 0.0), y=10.0,
                              confidence=1.0)))
                t += 1
        _play(60)
    return Match(_meta(fps), frames)


def test_timeout_first_defense_flags_the_leaky_wall():
    """Négy időkérésből három után gólt kapnak → szivárgó fal."""
    from handball.pipeline.stoppages import timeout_first_defense

    rec = timeout_first_defense(
        _tfd_match([True, True, True, False]))["home"]
    assert rec["timeouts"] == 4 and rec["conceded"] == 3
    assert rec["share_pct"] == 75.0
    assert rec["verdict"] == "időkérés után szivárgó fal"


def test_timeout_first_defense_flags_the_fresh_wall():
    """Ha az időkérések után nem kapnak gólt, friss a fal."""
    from handball.pipeline.stoppages import timeout_first_defense

    rec = timeout_first_defense(_tfd_match([False] * 4))["home"]
    assert rec["conceded"] == 0 and rec["share_pct"] == 0.0
    assert rec["verdict"] == "időkérés után friss fal"


def test_timeout_first_defense_needs_enough_timeouts():
    """Kevés (3-nál kevesebb) időkérésnél nincs ítélet."""
    from handball.pipeline.stoppages import timeout_first_defense

    rec = timeout_first_defense(_tfd_match([True, True]))["home"]
    assert rec["timeouts"] == 2 and rec["verdict"] is None


# ---- Időkérés-csomag (az időkérés cserével jár-e) ---------------------------

def _tsc_match(with_sub_flags, fps=25.0):
    """Hazai időkérés-sorozat; a `with_sub_flags` szerinti körökben az
    időkérés után egy-ki-egy-be hazai csere is történik."""
    frames = []
    t = 0
    for k, with_sub in enumerate(with_sub_flags):
        out_tid, in_tid = 50 + 2 * k, 51 + 2 * k
        for i in range(int(20 * fps)):        # játék (hazai labda)
            players = _players(t, moving=True)
            hp = players[0]
            if with_sub:                       # a lecserélendő ember fent
                players = players + [PlayerPosition(
                    track_id=out_tid, team=Team.HOME, x=25.0, y=8.0,
                    source=PositionSource.MEASURED, confidence=1.0)]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=hp.x, y=hp.y,
                                          confidence=1.0)))
            t += 1
        for i in range(int(25 * fps)):        # időkérés: állás
            players = _players(0, moving=False)
            if with_sub:
                players = players + [PlayerPosition(
                    track_id=out_tid, team=Team.HOME, x=25.0, y=8.0,
                    source=PositionSource.MEASURED, confidence=1.0)]
            frames.append(Frame(t=t, players=players, ball=None))
            t += 1
        for i in range(int(20 * fps)):        # játék újra + csere
            players = _players(t, moving=True)
            if with_sub:
                if i < int(4 * fps):           # a régi a cserezóna felé
                    frac = i / float(int(4 * fps))
                    players = players + [PlayerPosition(
                        track_id=out_tid, team=Team.HOME,
                        x=25.0 - 5.0 * frac, y=8.0 - 7.0 * frac,
                        source=PositionSource.MEASURED, confidence=1.0)]
                if i >= int(4 * fps):          # az új a zónából befelé
                    frac = min(1.0, (i - int(4 * fps)) / float(int(4 * fps)))
                    players = players + [PlayerPosition(
                        track_id=in_tid, team=Team.HOME,
                        x=20.0 + 5.0 * frac, y=1.0 + 7.0 * frac,
                        source=PositionSource.MEASURED, confidence=1.0)]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_timeout_sub_combo_flags_the_swapping_bench():
    """Mindkét időkéréshez csere társul → az időkérésük cserével jár."""
    from handball.pipeline.stoppages import timeout_sub_combo

    rec = timeout_sub_combo(_tsc_match([True, True]))["home"]
    assert rec["timeouts"] == 2 and rec["with_subs"] == 2
    assert rec["verdict"] == "az időkérésük cserével jár"


def test_timeout_sub_combo_flags_the_pure_tactics_bench():
    """Csere nélküli időkérések → tiszta taktika."""
    from handball.pipeline.stoppages import timeout_sub_combo

    rec = timeout_sub_combo(_tsc_match([False, False]))["home"]
    assert rec["timeouts"] == 2 and rec["with_subs"] == 0
    assert rec["verdict"] == "az időkérésük tiszta taktika"


def test_timeout_sub_combo_needs_enough_timeouts():
    """Egyetlen időkérésnél nincs ítélet."""
    from handball.pipeline.stoppages import timeout_sub_combo

    rec = timeout_sub_combo(_tsc_match([True]))["home"]
    assert rec["timeouts"] == 1 and rec["verdict"] is None


# ---- Hosszú állás utáni játék (kizökkenti-e őket) ---------------------------

def _lbr_match(scorer_sides, fps=25.0):
    """Hosszú (150 mp-es) megszakítások; mindegyik után a
    `scorer_sides` szerinti csapat szerez gólt."""
    frames = []
    t = 0
    for side in scorer_sides:
        for _ in range(int(20 * fps)):        # játék
            players = _players(t, moving=True)
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=players[0].x, y=players[0].y,
                                          confidence=1.0)))
            t += 1
        for _ in range(int(150 * fps)):       # hosszú állás
            frames.append(Frame(t=t, players=_players(0, moving=False),
                                ball=None))
            t += 1
        for _ in range(int(5 * fps)):         # újraindulás
            players = _players(t, moving=True)
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        for i in range(8):                    # gól az ablakon belül
            if side == "home":
                frames.append(Frame(t=t, players=[PlayerPosition(
                    track_id=1, team=Team.HOME, x=33.0, y=10.0,
                    source=PositionSource.MEASURED, confidence=1.0)],
                    ball=Ball(x=min(34.0 + i, 40.0), y=10.0,
                              confidence=1.0)))
            else:
                frames.append(Frame(t=t, players=[PlayerPosition(
                    track_id=21, team=Team.AWAY, x=7.0, y=10.0,
                    source=PositionSource.MEASURED, confidence=1.0)],
                    ball=Ball(x=max(6.0 - i, 0.0), y=10.0,
                              confidence=1.0)))
            t += 1
        for _ in range(int(10 * fps)):        # levezetés
            players = _players(t, moving=True)
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_long_break_response_flags_the_surger():
    """Két hosszú állás után is a hazai talál be → ők meglódulnak, a
    vendéget kizökkenti."""
    from handball.pipeline.stoppages import long_break_response

    res = long_break_response(_lbr_match(["home", "home"]))
    assert res["home"]["breaks"] == 2
    assert res["home"]["verdict"] == "a hosszú állások után meglódulnak"
    assert res["away"]["verdict"] == "a hosszú állások kizökkentik őket"


def test_long_break_response_split_no_verdict():
    """Ha a két állás után más-más csapat talál be, nincs ítélet."""
    from handball.pipeline.stoppages import long_break_response

    res = long_break_response(_lbr_match(["home", "away"]))
    assert res["home"]["verdict"] is None
    assert res["away"]["verdict"] is None


def test_long_break_response_needs_enough_breaks():
    """Egyetlen hosszú állásnál nincs ítélet."""
    from handball.pipeline.stoppages import long_break_response

    res = long_break_response(_lbr_match(["home"]))
    assert res["home"]["breaks"] == 1 and res["home"]["verdict"] is None


# ---- Időkérés-befejező ------------------------------------------------------

_TOF_HOME = {1: (30.0, 10.0), 2: (28.0, 4.0), 3: (32.0, 16.0)}


def _tof_players(t, moving):
    """3 hazai a támadó térfélen + 4 vendég védő (a leállás-felismerés
    MIN_VISIBLE küszöbe miatt kell a hat látható ember)."""
    out = []
    for tid, (x, y) in _TOF_HOME.items():
        bx, by = x, y
        if moving:
            bx += 1.5 * math.sin(t / 5.0 + tid)
            by += 1.0 * math.cos(t / 4.0 + tid)
        out.append(PlayerPosition(track_id=tid, team=Team.HOME, x=bx, y=by,
                                  source=PositionSource.MEASURED,
                                  confidence=1.0))
    for k in range(4):
        bx, by = 34.0 + 0.5 * k, 5.0 + 3.0 * k
        if moving:
            bx += 1.0 * math.sin(t / 6.0 + k)
        out.append(PlayerPosition(track_id=20 + k, team=Team.AWAY, x=bx,
                                  y=by, source=PositionSource.MEASURED,
                                  confidence=1.0))
    return out


def _tof_match(shooters, fps=25.0):
    """`shooters` = időkérésenként a lövést leadó hazai játékos.

    Minden ciklus: hazai birtoklás → 20 mp állás (időkérés) → az
    újraindítás utáni lövés → hosszabb játék.
    """
    frames = []
    t = 0

    def _play(seconds):
        nonlocal t
        for _ in range(int(seconds * fps)):
            players = _tof_players(t, moving=True)
            hp = players[0]      # a hazai 1-es birtokol (ő kér időt)
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=hp.x, y=hp.y, confidence=1.0)))
            t += 1

    for tid in shooters:
        _play(10)
        for _ in range(int(20 * fps)):        # időkérés: 20 mp állás
            frames.append(Frame(t=t, players=_tof_players(0, moving=False),
                                ball=None))
            t += 1
        # A lövés MOZGÁSBAN történik: állóképnél a leállás-szakasz
        # ráterjedne a lövésre, és az kiesne a szünet utáni ablakból.
        sx, sy = _TOF_HOME[tid]
        for _ in range(6):                    # a lövő kezében a labda
            cast = _tof_players(t, moving=True)
            who = next(p for p in cast if p.track_id == tid)
            frames.append(Frame(t=t, players=cast,
                                ball=Ball(x=who.x + 0.2, y=who.y,
                                          confidence=1.0)))
            t += 1
        steps = 10
        for i in range(1, steps + 1):
            f = i / steps
            frames.append(Frame(
                t=t, players=_tof_players(t, moving=True),
                ball=Ball(x=sx + 0.2 + (40.4 - sx - 0.2) * f,
                          y=sy + (10.0 - sy) * f, confidence=1.0)))
            t += 1
        _play(60)
    return Match(_meta(fps), frames)


def test_timeout_finisher_finds_the_target_post():
    """Ha az időkérések utáni lövések nagy része ugyanarról a posztról
    jön, a megbeszélésen arra az emberre kell embert rendelni."""
    from handball.pipeline.stoppages import (TOF_MIN_SHOTS,
                                             timeout_finisher)

    rec = timeout_finisher(_tof_match([1, 1, 1, 2]))["home"]
    assert rec["timeouts"] >= 4, rec
    assert rec["shots"] >= TOF_MIN_SHOTS, rec
    assert rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "elé kell állni" in rec["verdict"], rec


def test_timeout_finisher_needs_enough_shots():
    """Két lövésből nincs ítélet — az időkérés ritka esemény."""
    from handball.pipeline.stoppages import timeout_finisher

    rec = timeout_finisher(_tof_match([1, 2]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Időkéréspáros-poszt (az időkérés utáni figura tengelye) ---------------


def _top_match(pairs, fps=25.0):
    """Mint a _tof_match, de a lövés ELŐTT az előkészítő is megkapja
    a labdát: a `pairs` elemei (előkészítő, befejező) hazai id-k."""
    frames = []
    t = 0

    def _play(seconds):
        nonlocal t
        for _ in range(int(seconds * fps)):
            players = _tof_players(t, moving=True)
            hp = players[0]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=hp.x, y=hp.y,
                                          confidence=1.0)))
            t += 1

    for feeder, shooter in pairs:
        _play(10)
        for _ in range(int(20 * fps)):        # időkérés: 20 mp állás
            frames.append(Frame(t=t,
                                players=_tof_players(0, moving=False),
                                ball=None))
            t += 1
        for _ in range(8):                    # a labda az előkészítőnél
            cast = _tof_players(t, moving=True)
            who = next(p for p in cast if p.track_id == feeder)
            frames.append(Frame(t=t, players=cast,
                                ball=Ball(x=who.x + 0.2, y=who.y,
                                          confidence=1.0)))
            t += 1
        sx, sy = _TOF_HOME[shooter]
        for _ in range(6):                    # átvétel a befejezőnél
            cast = _tof_players(t, moving=True)
            who = next(p for p in cast if p.track_id == shooter)
            frames.append(Frame(t=t, players=cast,
                                ball=Ball(x=who.x + 0.2, y=who.y,
                                          confidence=1.0)))
            t += 1
        steps = 10
        for i in range(1, steps + 1):
            f = i / steps
            frames.append(Frame(
                t=t, players=_tof_players(t, moving=True),
                ball=Ball(x=sx + 0.2 + (40.4 - sx - 0.2) * f,
                          y=sy + (10.0 - sy) * f, confidence=1.0)))
            t += 1
        _play(60)
    return Match(_meta(fps), frames)


def test_timeout_pair_roles_names_the_axis():
    """Ha az időkérés utáni figura mindig ugyanazon a tengelyen fut,
    az ELSŐ passzt kell elvágni."""
    from handball.pipeline.stoppages import (TOP_MIN_SHOTS,
                                             timeout_pair_roles)

    rec = timeout_pair_roles(
        _top_match([(1, 2), (1, 2), (1, 2), (2, 1)]))["home"]
    assert rec["shots"] >= TOP_MIN_SHOTS, rec
    assert rec["main_role"] and "→" in rec["main_role"], rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "ELSŐ passzt" in rec["verdict"], rec


def test_timeout_pair_roles_silent_with_few_shots():
    """Kevés időkérés utáni lövésből nincs ítélet."""
    from handball.pipeline.stoppages import timeout_pair_roles

    rec = timeout_pair_roles(_top_match([(1, 2), (2, 1)]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec
