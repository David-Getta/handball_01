"""
Tesztek a pozíció-prior alapú kapus-azonosításra (goalkeeper.py).

Futtatás:
    python -m pytest tests/test_goalkeeper.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.goalkeeper import ROLE_GOALKEEPER, detect_goalkeepers


def _match(frames, fps=25.0):
    return Match(meta=MatchMeta(match_id="gk", home_team="H", away_team="A",
                                fps=fps), frames=frames)


def _stay(track_id, team, x, y, n, jitter=0.0):
    """Egy helyben (kis mozgással) tartózkodó játékos n kockán át."""
    out = []
    for t in range(n):
        dx = jitter * ((t % 3) - 1)
        out.append((t, PlayerPosition(track_id=track_id, team=team,
                                      x=x + dx, y=y + dx)))
    return out


def _frames(*walks, n):
    by_t: dict = {}
    for walk in walks:
        for (t, p) in walk:
            by_t.setdefault(t, []).append(p)
    return [Frame(t=t, players=by_t.get(t, [])) for t in range(n)]


def test_marks_both_goalkeepers():
    """A két kapuelőtérben álló track kapus lesz, a mezőny nem."""
    n = 300  # 12 mp @ 25 fps
    gk_home = _stay(1, Team.HOME, 1.5, 10.0, n, jitter=0.3)
    gk_away = _stay(2, Team.AWAY, 38.5, 10.0, n, jitter=0.3)
    mid = _stay(3, Team.HOME, 20.0, 10.0, n, jitter=0.5)
    m = _match(_frames(gk_home, gk_away, mid, n=n))
    marked = detect_goalkeepers(m)
    assert set(marked) == {1, 2}
    for share in marked.values():
        assert share > 0.9
    roles = {p.track_id: p.role for f in m.frames for p in f.players}
    assert roles[1] == ROLE_GOALKEEPER and roles[2] == ROLE_GOALKEEPER
    assert roles[3] is None


def test_one_goalkeeper_per_goal():
    """Két track ugyanannál a kapunál: csak a nagyobb hányadú lesz kapus
    (a másik pl. beálló/védő, aki sokat jár arra)."""
    n = 300
    gk = _stay(1, Team.HOME, 1.5, 10.0, n)
    # A 2-es track ideje felében a kapuelőtérben, felében kint.
    near = (_stay(2, Team.HOME, 4.0, 10.0, n // 2)
            + [(t + n // 2, p) for (t, p) in
               _stay(2, Team.HOME, 15.0, 10.0, n - n // 2)])
    m = _match(_frames(gk, near, n=n))
    marked = detect_goalkeepers(m)
    assert set(marked) == {1}


def test_short_or_transient_tracks_not_marked():
    """Rövid minta (< min mp) vagy alacsony kapuelőtér-hányad → nem kapus."""
    n = 300
    short = _stay(1, Team.HOME, 1.5, 10.0, 50)  # csak 2 mp
    visitor = (_stay(2, Team.AWAY, 38.5, 10.0, 90)  # 30% bent...
               + [(t + 90, p) for (t, p) in
                  _stay(2, Team.AWAY, 25.0, 10.0, 210)])  # ...70% kint
    m = _match(_frames(short, visitor, n=n))
    assert detect_goalkeepers(m) == {}
    roles = {p.role for f in m.frames for p in f.players}
    assert roles == {None}


def test_estimated_positions_ignored():
    """A BECSÜLT pozíciók nem számítanak bele a kapus-döntésbe."""
    n = 300
    est = []
    for t in range(n):
        est.append((t, PlayerPosition(track_id=1, team=Team.HOME, x=1.5,
                                      y=10.0, source=PositionSource.ESTIMATED)))
    m = _match(_frames(est, n=n))
    assert detect_goalkeepers(m) == {}


def _shot_sequence(t0, gk_track, save=True):
    """Vendég kapu (x=40) felé tartó hazai lövés kockái t0-tól: a kapus a
    kapuban áll; védésnél a labda nála áll meg, gólnál eléri a vonalat."""
    from handball.models.tracking import Ball
    frames = []
    gk = PlayerPosition(track_id=gk_track, team=Team.AWAY, x=39.0, y=10.0,
                        source=PositionSource.MEASURED, confidence=1.0,
                        role="kapus")
    shooter = PlayerPosition(track_id=4, team=Team.HOME, x=33.5, y=10.0,
                             source=PositionSource.MEASURED, confidence=1.0)
    for i in range(8):
        x = 33.6 + i
        if save:
            x = min(x, 38.8)  # a kapusnál megáll
        players = [gk] + ([shooter] if i == 0 else [])
        frames.append(Frame(t=t0 + i, players=players,
                            ball=Ball(x=x, y=10.0, confidence=1.0)))
    return frames


def test_goalkeeper_stats_counts_saves_and_conceded():
    from handball.pipeline.goalkeeper import goalkeeper_stats
    # Két lövés: egy védés + egy gól, közte a labda visszamegy középre
    # (a debounce miatt külön kapu-megközelítés kell).
    from handball.models.tracking import Ball
    frames = _shot_sequence(0, gk_track=9, save=True)
    frames.append(Frame(t=8, players=[], ball=Ball(x=20.0, y=10.0,
                                                   confidence=1.0)))
    frames += _shot_sequence(9, gk_track=9, save=False)
    m = _match(frames)
    stats = goalkeeper_stats(m)
    away = stats["away"]
    assert away["track_id"] == 9
    assert away["on_target"] == 2
    assert away["saves"] == 1 and away["conceded"] == 1
    assert away["save_pct"] == 50.0
    assert sum(away["conceded_zones"].values()) == 1
    # Minden kapura tartó lövés bekerül a zóna-bontásba (védés is), és a
    # zóna szerinti védés-hatékonyság számolható.
    assert sum(away["on_target_zones"].values()) == 2
    assert away["zone_save_pct"]  # legalább egy zónára van érték
    for zone, pct in away["zone_save_pct"].items():
        assert 0.0 <= pct <= 100.0


def test_goalkeeper_stats_empty_without_role():
    from handball.pipeline.goalkeeper import goalkeeper_stats
    m = _match(_frames(_stay(1, Team.HOME, 20.0, 10.0, 100), n=100))
    assert goalkeeper_stats(m) == {}


def _empty_net_match(gk_far=True, seconds=5, poss_own=True):
    """HAZAI támadás a labdával; a hazai kapus vagy elöl (7a6), vagy otthon."""
    from handball.models.tracking import Ball
    n = int(seconds * 25)
    frames = []
    for t in range(n):
        gk_x = 20.0 if gk_far else 1.5  # elöl játszik vs a kapujában áll
        players = [
            PlayerPosition(track_id=1, team=Team.HOME, x=gk_x, y=10.0,
                           source=PositionSource.MEASURED, confidence=1.0,
                           role="kapus"),
            PlayerPosition(track_id=2, team=Team.HOME, x=30.0, y=10.0,
                           source=PositionSource.MEASURED, confidence=1.0),
            PlayerPosition(track_id=3, team=Team.AWAY, x=35.0, y=8.0,
                           source=PositionSource.MEASURED, confidence=1.0),
        ]
        # A labda a hazai (2-es) vagy a vendég (3-as) játékosnál.
        bx, by = (30.0, 10.0) if poss_own else (35.0, 8.0)
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=bx, y=by, confidence=1.0)))
    return _match(frames)


def test_empty_net_detected_when_gk_upfield():
    from handball.pipeline.goalkeeper import detect_empty_net
    windows = detect_empty_net(_empty_net_match(gk_far=True, seconds=5))
    assert len(windows) == 1
    w = windows[0]
    assert w["team"] == "home"
    assert w["duration_s"] >= 4.5


def test_no_empty_net_when_gk_home_or_defending():
    from handball.pipeline.goalkeeper import detect_empty_net
    # A kapus a kapujában → nincs 7a6.
    assert detect_empty_net(_empty_net_match(gk_far=False)) == []
    # A kapus elöl, de az ELLENFÉL birtokol (pl. lerohanás ellenük) → nem 7a6.
    assert detect_empty_net(_empty_net_match(gk_far=True, poss_own=False)) == []


def test_short_burst_filtered():
    from handball.pipeline.goalkeeper import detect_empty_net
    # 2 mp-es szakasz a 3 mp-es küszöb alatt marad.
    assert detect_empty_net(_empty_net_match(gk_far=True, seconds=2)) == []


def test_goalkeeper_seven_meter_balance():
    """A kapus-statisztika a hétméteres-mérleget is hozza: hány büntetővel
    nézett szembe (seven_faced) és mennyit fogott (seven_saved)."""
    from handball.models.tracking import Ball
    from handball.pipeline.goalkeeper import goalkeeper_stats

    def pl(tid, team, x, y, role=None):
        return PlayerPosition(track_id=tid, team=team, x=x, y=y, role=role)

    frames = []
    t = 0
    # Hazai hétméteres a +x kapura: álló labda a 7 m-es ponton (33, 10)...
    for _ in range(30):
        frames.append(Frame(t=t, players=[
            pl(1, Team.HOME, 32.0, 10.0),
            pl(90, Team.AWAY, 39.5, 10.0, role="kapus"),
        ], ball=Ball(x=33.0, y=10.0, confidence=1.0)))
        t += 1
    # ...majd a lövést a vendég kapus fogja (a labda a kapusnál áll meg).
    for i in range(7):
        frames.append(Frame(t=t, players=[
            pl(1, Team.HOME, 32.0, 10.0),
            pl(90, Team.AWAY, 39.0, 10.0, role="kapus"),
        ], ball=Ball(x=min(34.0 + i, 39.0), y=10.0, confidence=1.0)))
        t += 1
    stats = goalkeeper_stats(_match(frames))
    rec = stats["away"]
    assert rec["seven_faced"] == 1
    assert rec["seven_saved"] == 1
    assert rec["saves"] >= 1  # a normál védés-statisztikában is benne van


def test_goalkeeper_timeline_detects_change_and_splits_stats():
    """A vendég kapuban az első felében a 9-es, a másodikban a 8-as áll;
    egy-egy hazai lövés jut mindkettőre → csere + külön mérleg."""
    from handball.models.tracking import Ball
    from handball.pipeline.goalkeeper import goalkeeper_timeline

    def gk(tid):
        return PlayerPosition(track_id=tid, team=Team.AWAY, x=39.0, y=10.0,
                              source=PositionSource.MEASURED,
                              confidence=1.0, role="kapus")

    frames = []
    # 1. szakasz: 9-es kapus (600 kocka), közben egy hazai VÉDETT lövés.
    for t in range(600):
        frames.append(Frame(t=t, players=[gk(9)],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    frames += _shot_sequence(600, gk_track=9, save=True)
    t0 = 600 + 8
    frames.append(Frame(t=t0, players=[], ball=Ball(x=20.0, y=10.0,
                                                    confidence=1.0)))
    # 2. szakasz: 8-as kapus (600 kocka), közben egy hazai GÓL.
    for i in range(600):
        frames.append(Frame(t=t0 + 1 + i, players=[gk(8)],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    frames += _shot_sequence(t0 + 601, gk_track=8, save=False)

    tl = goalkeeper_timeline(_match(frames))["away"]
    tids = [st["track_id"] for st in tl["stints"]]
    assert tids == [9, 8]
    assert len(tl["changes"]) == 1
    assert tl["per_keeper"][9]["saves"] == 1
    assert tl["per_keeper"][9]["save_pct"] == 100.0
    assert tl["per_keeper"][8]["on_target"] == 1
    assert tl["per_keeper"][8]["saves"] == 0


def test_goalkeeper_timeline_per_keeper_xg_balance():
    """Cserénél a kapusonkénti mérleg a helyzet-értéket is hozza:
    a védés pluszba, a kis xG-jű lövésből kapott gól mínuszba viszi
    a kapus GSAx-mérlegét (prevented = faced_xg − kapott gól)."""
    from handball.models.tracking import Ball
    from handball.pipeline.goalkeeper import goalkeeper_timeline

    def gk(tid):
        return PlayerPosition(track_id=tid, team=Team.AWAY, x=39.0, y=10.0,
                              source=PositionSource.MEASURED,
                              confidence=1.0, role="kapus")

    frames = []
    for t in range(600):
        frames.append(Frame(t=t, players=[gk(9)],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    frames += _shot_sequence(600, gk_track=9, save=True)
    t0 = 600 + 8
    frames.append(Frame(t=t0, players=[], ball=Ball(x=20.0, y=10.0,
                                                    confidence=1.0)))
    for i in range(600):
        frames.append(Frame(t=t0 + 1 + i, players=[gk(8)],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    frames += _shot_sequence(t0 + 601, gk_track=8, save=False)

    tl = goalkeeper_timeline(_match(frames))["away"]
    r9, r8 = tl["per_keeper"][9], tl["per_keeper"][8]
    # A 9-es védett: pozitív mérleg, kapott gól nélkül.
    assert r9["faced_xg"] > 0 and r9["conceded"] == 0
    assert r9["prevented"] == r9["faced_xg"]
    # A 8-as gólt kapott: a mérlege a helyzet-értékkel csökkentett −1.
    assert r8["conceded"] == 1
    assert r8["prevented"] < 0
    assert abs(r8["prevented"] - (r8["faced_xg"] - 1)) < 0.02


def test_outlet_speed_measures_fast_restart():
    """Védés után gyorsan felezőn átvitt labda → gyors indítás a védő
    (away) oldalon; a lassan visszahozott labda nem számít gyorsnak."""
    from handball.models.tracking import Ball
    from handball.pipeline.goalkeeper import OUTLET_FAST_S, outlet_speed

    def _pl(tid, team, x, y):
        return PlayerPosition(track_id=tid, team=team, x=x, y=y)

    def keeper():
        gk = _pl(30, Team.AWAY, 39.0, 10.0)
        gk.role = "kapus"
        return gk

    # Fogott lövés: a labda a kapusnál (38,8 m) megáll...
    frames = []
    for i in range(8):
        frames.append(Frame(
            t=i,
            players=[_pl(1, Team.HOME, 37.0, 10.0), keeper()],
            ball=Ball(x=min(37.4 + 0.6 * i, 38.8), y=10.0,
                      confidence=1.0)))
    # ...majd az indítás 2 mp alatt átér a felezőn (x < 20).
    for j in range(60):
        frames.append(Frame(
            t=8 + j,
            players=[keeper()],
            ball=Ball(x=max(38.8 - 0.4 * j, 5.0), y=10.0,
                      confidence=1.0)))
    rec = outlet_speed(_match(frames))["away"]
    assert rec["saves"] == 1
    assert rec["outlets"] == 1
    assert rec["fast"] == 1
    assert rec["avg_s"] is not None and rec["avg_s"] <= OUTLET_FAST_S
    # A home oldalon nem történt védés.
    assert outlet_speed(_match(frames))["home"]["saves"] == 0


def test_empty_net_goals_counts_punish_goal():
    """A 7 a 6 szakasz után azonnal bedobott gól "üres kapura kapott"
    gólnak számít a kaput elhagyó csapatnál."""
    from handball.models.tracking import Ball
    from handball.pipeline.goalkeeper import empty_net_goals

    frames = []
    # 5 mp 7 a 6: a hazai kapus elöl, a hazai csapat birtokol.
    for t in range(125):
        players = [
            PlayerPosition(track_id=1, team=Team.HOME, x=20.0, y=10.0,
                           source=PositionSource.MEASURED, confidence=1.0,
                           role="kapus"),
            PlayerPosition(track_id=2, team=Team.HOME, x=30.0, y=10.0,
                           source=PositionSource.MEASURED, confidence=1.0),
        ]
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=30.0, y=10.0, confidence=1.0)))
    # Labdaszerzés után a vendég azonnal az üres hazai kapuba dob.
    for i in range(7):
        players = [
            PlayerPosition(track_id=1, team=Team.HOME, x=20.0, y=10.0,
                           source=PositionSource.MEASURED, confidence=1.0,
                           role="kapus"),
            PlayerPosition(track_id=4, team=Team.AWAY, x=3.0, y=10.0,
                           source=PositionSource.MEASURED, confidence=1.0),
        ]
        frames.append(Frame(t=125 + i, players=players,
                            ball=Ball(x=max(2.6 - 0.6 * i, 0.0), y=10.0,
                                      confidence=1.0)))
    rec = empty_net_goals(_match(frames))
    assert rec["home"]["windows"] == 1
    assert rec["home"]["conceded_empty"] == 1
    assert rec["away"]["conceded_empty"] == 0


def test_empty_net_goals_counts_scored_7v6():
    """A 7 a 6 alatt (vagy közvetlenül utána) dobott gól a haszon-oldalra
    kerül: scored_7v6."""
    from handball.models.tracking import Ball
    from handball.pipeline.goalkeeper import empty_net_goals

    frames = []
    # 5 mp 7 a 6: a hazai kapus elöl, a hazai csapat birtokol.
    for t in range(125):
        players = [
            PlayerPosition(track_id=1, team=Team.HOME, x=20.0, y=10.0,
                           source=PositionSource.MEASURED, confidence=1.0,
                           role="kapus"),
            PlayerPosition(track_id=2, team=Team.HOME, x=30.0, y=10.0,
                           source=PositionSource.MEASURED, confidence=1.0),
        ]
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=30.0, y=10.0, confidence=1.0)))
    # A támadás vége: a hazai a vendég kapuba (x=40) dob.
    for i in range(7):
        players = [
            PlayerPosition(track_id=1, team=Team.HOME, x=20.0, y=10.0,
                           source=PositionSource.MEASURED, confidence=1.0,
                           role="kapus"),
            PlayerPosition(track_id=2, team=Team.HOME, x=37.0, y=10.0,
                           source=PositionSource.MEASURED, confidence=1.0),
        ]
        frames.append(Frame(t=125 + i, players=players,
                            ball=Ball(x=min(37.4 + 0.6 * i, 40.0), y=10.0,
                                      confidence=1.0)))
    rec = empty_net_goals(_match(frames))
    assert rec["home"]["windows"] == 1
    assert rec["home"]["scored_7v6"] == 1
    assert rec["home"]["conceded_empty"] == 0


def test_outlet_target_identified():
    """A felező-átlépésnél a labda melletti saját mezőnyjátékos az
    indítás célpontja."""
    from handball.models.tracking import Ball
    from handball.pipeline.goalkeeper import outlet_speed

    def _pl(tid, team, x, y, role=None):
        p = PlayerPosition(track_id=tid, team=team, x=x, y=y)
        if role:
            p.role = role
        return p

    frames = []
    for i in range(8):
        frames.append(Frame(
            t=i,
            players=[_pl(1, Team.HOME, 37.0, 10.0),
                     _pl(30, Team.AWAY, 39.0, 10.0, role="kapus")],
            ball=Ball(x=min(37.4 + 0.6 * i, 38.8), y=10.0,
                      confidence=1.0)))
    # Az indítás átér a felezőn; a 12-es away szélső ott várja a labdát.
    for j in range(60):
        bx = max(38.8 - 0.4 * j, 5.0)
        frames.append(Frame(
            t=8 + j,
            players=[_pl(30, Team.AWAY, 39.0, 10.0, role="kapus"),
                     _pl(12, Team.AWAY, 18.0, 10.0)],
            ball=Ball(x=bx, y=10.0, confidence=1.0)))
    rec = outlet_speed(_match(frames))["away"]
    assert rec["outlets"] == 1
    assert rec["targets"] == [{"player_id": 12, "n": 1}]


def test_empty_net_context_trailing():
    """A kapott gól utáni 7 a 6 szakasz "hátrányban indított"-nak
    számít; rövid felvételen hajrá-jelölés nincs."""
    from handball.models.tracking import Ball
    from handball.pipeline.goalkeeper import empty_net_context

    def pl(tid, team, x, y, role=None):
        p = PlayerPosition(track_id=tid, team=team, x=x, y=y)
        if role:
            p.role = role
        return p

    frames = []
    # A vendég gólt dob a hazai kapuba (x=0) — hazai hátrány.
    for i in range(7):
        frames.append(Frame(
            t=i,
            players=[pl(4, Team.AWAY, 3.0, 10.0)],
            ball=Ball(x=max(2.6 - 0.6 * i, 0.0), y=10.0,
                      confidence=1.0)))
    frames.append(Frame(t=8, players=[],
                        ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    # Ezután a hazai 7 a 6-ot játszik 5 mp-ig.
    for t in range(10, 135):
        frames.append(Frame(
            t=t,
            players=[pl(1, Team.HOME, 20.0, 10.0, role="kapus"),
                     pl(2, Team.HOME, 30.0, 10.0)],
            ball=Ball(x=30.0, y=10.0, confidence=1.0)))
    rec = empty_net_context(_match(frames))["home"]
    assert rec["windows"] == 1
    assert rec["trailing"] == 1
    assert rec["endgame"] == 0   # rövid felvétel: nincs hajrá-jelölés


def test_gk_positioning_styles():
    """A kint álló kapus (2,5 m) "kint álló", a vonalon lévő (0,5 m)
    "vonalon maradó"; kevés kockánál None."""
    from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                          PlayerPosition, PositionSource,
                                          Team)
    from handball.pipeline.goalkeeper import gk_positioning

    def gk(team, x):
        return PlayerPosition(track_id=1 if team == Team.HOME else 2,
                              team=team, x=x, y=10.0, role="kapus",
                              source=PositionSource.MEASURED,
                              confidence=1.0)

    frames = [Frame(t=t, players=[gk(Team.HOME, 2.5),
                                  gk(Team.AWAY, 39.5)])
              for t in range(120)]
    m = Match(MatchMeta(match_id="gp", home_team="H", away_team="A",
                        fps=25.0), frames)
    res = gk_positioning(m)
    assert res["home"]["style"] == "kint álló"
    assert abs(res["home"]["avg_depth_m"] - 2.5) < 0.05
    assert res["away"]["style"] == "vonalon maradó"
    short = Match(m.meta, m.frames[:50])
    assert gk_positioning(short)["home"]["avg_depth_m"] is None


def _range_shot(t0, sx, save=False):
    """HAZAI lövés a +x (vendég) kapura: a lövő végig sx-nél áll (a
    kapu-táv innen jön), a labda onnan a kapuig gyorsul. save=True →
    a vendég kapus a kapuban áll és a labda nála (38,6) áll meg."""
    from handball.models.tracking import Ball
    frames = []
    for i in range(3):
        pls = [PlayerPosition(track_id=1, team=Team.HOME, x=sx, y=10.0,
                              source=PositionSource.MEASURED, confidence=1.0)]
        if save:
            pls.append(PlayerPosition(track_id=99, team=Team.AWAY, x=39.2,
                                      y=10.0, source=PositionSource.MEASURED,
                                      confidence=1.0, role="kapus"))
        frames.append(Frame(t=t0 + i, players=pls,
                            ball=Ball(x=sx, y=10.0, confidence=1.0)))
    t = t0 + 3
    for i in range(9):
        bx = min(sx + 1.6 * (i + 1), 38.6 if save else 40.0)
        pls = [PlayerPosition(track_id=1, team=Team.HOME, x=sx, y=10.0,
                              source=PositionSource.MEASURED, confidence=1.0)]
        if save:
            pls.append(PlayerPosition(track_id=99, team=Team.AWAY, x=39.2,
                                      y=10.0, source=PositionSource.MEASURED,
                                      confidence=1.0, role="kapus"))
        frames.append(Frame(t=t + i, players=pls,
                            ball=Ball(x=bx, y=10.0, confidence=1.0)))
    return frames


def test_gk_save_ranges_by_distance():
    """A VÉDŐ oldal kapusára érkezett lövéseket a lövő kapu-távja alapján
    sávba sorolja, és sávonként számol védési arányt. Egy távoli gól + egy
    távoli védés → a vendég kapus távoli sávja 50% (2-ből 1)."""
    from handball.models.tracking import Ball
    from handball.pipeline.goalkeeper import gk_save_ranges

    frames = _range_shot(0, 29.0, save=False)  # távoli gól (~11 m)
    t = frames[-1].t + 1
    for i in range(25):  # szünet a debounce-hoz
        frames.append(Frame(t=t + i, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    frames += _range_shot(frames[-1].t + 1, 29.0, save=True)  # távoli védés
    m = _match(frames)
    away = gk_save_ranges(m)["away"]
    assert away["far"]["faced"] == 2 and away["far"]["saves"] == 1
    assert away["far"]["save_pct"] == 50.0
    assert away["on_target"] == 2
    assert away["close"]["faced"] == 0 and away["close"]["save_pct"] is None
    # A hazai kapusát nem érte lövés (a hazai támadott).
    assert gk_save_ranges(m)["home"]["on_target"] == 0


def test_gk_save_fade_drop_second_half():
    """Az 1. félidőben 4/4 védés, a 2.-ban 0/4 → a védés% 100 ponttal
    esik; félidő-jel nélkül nincs ítélet."""
    from handball.models.tracking import Ball
    from handball.pipeline.goalkeeper import gk_save_fade

    fps = 25.0
    frames = []
    t = 0

    def shots(n, save):
        nonlocal t
        for _ in range(n):
            frames.extend(_shot_sequence(t, gk_track=9, save=save))
            t = frames[-1].t + 1
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
            t += 1

    def active(seconds):
        # Aktív játék 12 mért játékossal — a félidő-érzékelő ezt nem
        # látja szünetnek.
        nonlocal t
        for i in range(int(seconds * fps)):
            players = [PlayerPosition(track_id=100 + k, team=Team.HOME,
                                      x=12.0 + k, y=4.0 + k,
                                      source=PositionSource.MEASURED,
                                      confidence=1.0) for k in range(6)]
            players += [PlayerPosition(track_id=200 + k, team=Team.AWAY,
                                       x=26.0 + k, y=4.0 + k,
                                       source=PositionSource.MEASURED,
                                       confidence=1.0) for k in range(6)]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=19.0, y=10.0, confidence=1.0)))
            t += 1

    active(40)
    shots(4, save=True)      # 1. félidő: 4 védés
    active(40)
    for _ in range(int(90 * fps)):  # szünet
        frames.append(Frame(t=t, players=[], ball=None))
        t += 1
    active(40)
    shots(4, save=False)     # 2. félidő: 4 kapott gól
    active(40)

    fade = gk_save_fade(_match(frames))
    a = fade["away"]
    assert a["fh_faced"] == 4 and a["fh_saves"] == 4
    assert a["sh_faced"] == 4 and a["sh_saves"] == 0
    assert a["drop_pp"] is not None and a["drop_pp"] >= 15.0
    # Félidő nélkül nincs ítélet.
    short = gk_save_fade(_match(frames[:2000]))
    assert short["away"]["drop_pp"] is None


def test_gk_change_effect_improvement():
    """A 9-es kapus 0/3 után jön a 8-as 3/3-mal → a csere +100
    százalékpontot javított; csere nélkül nincs ítélet."""
    from handball.models.tracking import Ball
    from handball.pipeline.goalkeeper import gk_change_effect

    def gk(tid):
        return PlayerPosition(track_id=tid, team=Team.AWAY, x=39.0,
                              y=10.0, source=PositionSource.MEASURED,
                              confidence=1.0, role="kapus")

    frames = []
    t = 0
    # 1. szakasz: 9-es kapus, 3 kapott gól.
    for _ in range(600):
        frames.append(Frame(t=t, players=[gk(9)],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    for _ in range(3):
        frames += _shot_sequence(t, gk_track=9, save=False)
        t = frames[-1].t + 1
        frames.append(Frame(t=t, players=[gk(9)],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    # 2. szakasz: 8-as kapus, 3 védés.
    for _ in range(600):
        frames.append(Frame(t=t, players=[gk(8)],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    for _ in range(3):
        frames += _shot_sequence(t, gk_track=8, save=True)
        t = frames[-1].t + 1
        frames.append(Frame(t=t, players=[gk(8)],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1

    eff = gk_change_effect(_match(frames))["away"]
    assert eff["changes"] == 1
    assert eff["pre_faced"] == 3 and eff["pre_saves"] == 0
    assert eff["post_faced"] == 3 and eff["post_saves"] == 3
    assert eff["delta_pp"] == 100.0

    # Csere nélkül (csak a 9-es szakasz) nincs ítélet.
    solo = [f for f in frames if all(p.track_id != 8 for p in f.players)]
    assert gk_change_effect(_match(solo))["away"]["delta_pp"] is None


def test_gk_weak_side_mirrors_conceded_goals():
    """7 hazai gól: 5 a lövő bal (felső y), 2 a jobb oldalára — a VENDÉG
    kapu gyengéje a kapus szemszögéből a JOBB oldal; kevés gólnál nincs
    ítélet."""
    from handball.models.tracking import Ball
    from handball.pipeline.goalkeeper import gk_weak_side

    def _goal(t0, cross_y):
        frames = []
        for i in range(9):
            bx = min(33.0 + 1.6 * (i + 1), 40.0)
            by = 10.0 + (cross_y - 10.0) * min(1.0, i / 6.0)
            frames.append(Frame(
                t=t0 + i,
                players=[PlayerPosition(track_id=1, team=Team.HOME,
                                        x=33.0, y=10.0,
                                        source=PositionSource.MEASURED,
                                        confidence=1.0)],
                ball=Ball(x=bx, y=by, confidence=1.0)))
        t = t0 + 9
        for i in range(20):  # szünet a debounce-hoz
            frames.append(Frame(t=t + i, players=[],
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        return frames

    frames = []
    for cy in (11.2, 11.2, 11.2, 11.2, 11.2, 9.0, 9.0):
        frames += _goal(frames[-1].t + 1 if frames else 0, cy)
    gw = gk_weak_side(_match(frames))
    a = gw["away"]  # a vendég kapta a gólokat
    assert a["goals"] == 7
    # A lövő "bal"-ja a kapus jobbja.
    assert a["jobb"] == 5 and a["bal"] == 2
    assert a["weak_side"] == "jobb"
    assert a["share"] is not None and abs(a["share"] - 5 / 7) < 0.01
    # A hazai kapu nem kapott gólt; kevés minta → nincs ítélet.
    assert gw["home"]["goals"] == 0
    assert gw["home"]["weak_side"] is None


def test_gk_outlet_length_flags_long_ball_keeper():
    """A hazai kapus 5 hosszú (24 m-es) + 2 rövid (8 m-es) indítást ad →
    71% hosszú, "hosszú" stílus; kevés kapus-passznál nincs ítélet."""
    from handball.models.tracking import Ball
    from handball.pipeline.goalkeeper import gk_outlet_length

    def _p(tid, x, y):
        return PlayerPosition(track_id=tid, team=Team.HOME, x=x, y=y,
                              source=PositionSource.MEASURED,
                              confidence=1.0)

    # A kapus (1) a kapuelőtérben áll végig; két fogadó: távoli (2,
    # 24 m) és közeli (3, 8 m).
    players = [_p(1, 1.0, 10.0), _p(2, 25.0, 10.0), _p(3, 9.0, 10.0)]

    def _hold(t0, x, y, n=5):
        return [Frame(t=t0 + i, players=players,
                      ball=Ball(x=x, y=y, confidence=1.0))
                for i in range(n)]

    frames = []
    t = 0
    for target_x in (25.0, 25.0, 25.0, 9.0, 25.0, 25.0, 9.0):
        frames += _hold(t, 1.0, 10.0)      # a kapusnál a labda
        t += 5
        frames += _hold(t, target_x, 10.0)  # indítás a fogadóhoz
        t += 5
    # Ráhagyás, hogy a kapus-azonosításnak legyen elég mért ideje.
    frames += _hold(t, 1.0, 10.0, n=250)
    go = gk_outlet_length(_match(frames))
    h = go["home"]
    assert h["outlets"] == 7 and h["long"] == 5
    assert h["long_pct"] is not None
    assert abs(h["long_pct"] - 100.0 * 5 / 7) < 0.5
    assert h["style"] == "hosszú"

    # Kevés kapus-passz: nincs ítélet.
    few = gk_outlet_length(_match(frames[:30] + frames[-250:]))
    assert few["home"]["style"] is None and few["home"]["long_pct"] is None


def test_gk_outlet_security_counts_stolen_outlets():
    """A hazai kapus 8 indításából 6 a társhoz, 2 az ellenfélhez jut →
    25%-os elcsípés-arány; kevés indításnál nincs ítélet."""
    from handball.models.tracking import Ball
    from handball.pipeline.goalkeeper import gk_outlet_security

    def _p(tid, team, x, y):
        return PlayerPosition(track_id=tid, team=team, x=x, y=y,
                              source=PositionSource.MEASURED,
                              confidence=1.0)

    players = [_p(1, Team.HOME, 1.0, 10.0),    # kapus a kapuelőtérben
               _p(2, Team.HOME, 10.0, 10.0),   # saját fogadó
               _p(11, Team.AWAY, 14.0, 5.0)]   # elcsípő ellenfél

    def _hold(t0, x, y, n=5):
        return [Frame(t=t0 + i, players=players,
                      ball=Ball(x=x, y=y, confidence=1.0))
                for i in range(n)]

    frames = []
    t = 0
    targets = [(10.0, 10.0)] * 6 + [(14.0, 5.0)] * 2
    for tx, ty in targets:
        frames += _hold(t, 1.0, 10.0)   # a kapusnál a labda
        t += 5
        frames += _hold(t, tx, ty)      # az indítás megérkezik
        t += 5
    # Ráhagyás a kapus-azonosításhoz (elég mért kocka a kapuelőtérben).
    frames += _hold(t, 1.0, 10.0, n=250)

    gs = gk_outlet_security(_match(frames))
    h = gs["home"]
    assert h["outlets"] == 8 and h["lost"] == 2
    assert h["lost_pct"] is not None
    assert abs(h["lost_pct"] - 25.0) < 0.1

    # Kevés indítás: nincs ítélet.
    few = gk_outlet_security(_match(frames[:40] + frames[-250:]))
    assert few["home"]["lost_pct"] is None


def test_gk_break_response_flags_fast_break_weakness():
    """A vendég kapus a gyorsindításos lövéseket mind kapja (0%
    védés), a rendezettekből hármat véd (75%) → lerohanásra érzékeny;
    kevés lövésnél nincs ítélet."""
    from handball.models.tracking import Ball
    from handball.pipeline.goalkeeper import gk_break_response

    frames = []
    t = 0

    def _context(n, x):
        # A lövés előtti kép: a labda a hazai játékosnál az adott
        # ponton (x < 20: saját térfél → gyorsindítás; x >= 20:
        # rendezett támadás).
        nonlocal t, frames
        holder = PlayerPosition(track_id=4, team=Team.HOME, x=x,
                                y=10.0, source=PositionSource.MEASURED,
                                confidence=1.0)
        for _ in range(n):
            frames.append(Frame(t=t, players=[holder],
                                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1

    def _shot(save):
        nonlocal t, frames
        frames += _shot_sequence(t, 30, save=save)
        t = frames[-1].t + 1

    # 4 rendezett lövés (10 mp a támadó térfélen): 3 védés, 1 gól.
    for i in range(4):
        _context(250, 28.0)
        _shot(save=(i < 3))
    # 4 gyorsindításos lövés (2 mp-vel előtte még saját térfél): mind gól.
    for _ in range(4):
        _context(50, 15.0)
        _shot(save=False)

    gbr = gk_break_response(_match(frames))
    a = gbr["away"]
    assert a["fast_faced"] >= 4 and a["set_faced"] >= 4
    assert a["verdict"] == "érzékeny"
    assert a["set_pct"] > a["fast_pct"]
    # A hazai kapura nem ment lövés: nincs ítélet.
    assert gbr["home"]["verdict"] is None

    # Kevés lövés: nincs ítélet.
    few = gk_break_response(_match(frames[:600]))
    assert few["away"]["verdict"] is None


def test_gk_outlet_side_flags_one_sided_keeper():
    """A hazai kapus 6 indítást a bal (y < 10) oldalra ad, egyet a
    jobbra → "bal" irány; kevés indításnál nincs ítélet."""
    from handball.models.tracking import Ball
    from handball.pipeline.goalkeeper import gk_outlet_side

    def _p(tid, x, y):
        return PlayerPosition(track_id=tid, team=Team.HOME, x=x, y=y,
                              source=PositionSource.MEASURED,
                              confidence=1.0)

    # A kapus (1) a kapuelőtérben; a bal oldali (2, y=4) és a jobb
    # oldali (3, y=16) fogadó ugyanolyan távol van tőle.
    players = [_p(1, 1.0, 10.0), _p(2, 20.0, 4.0), _p(3, 20.0, 16.0)]

    def _hold(t0, x, y, n=5):
        return [Frame(t=t0 + i, players=players,
                      ball=Ball(x=x, y=y, confidence=1.0))
                for i in range(n)]

    frames = []
    t = 0
    for target_y in (4.0, 4.0, 4.0, 4.0, 4.0, 4.0, 16.0):
        frames += _hold(t, 1.0, 10.0)        # a kapusnál a labda
        t += 5
        frames += _hold(t, 20.0, target_y)   # indítás a fogadóhoz
        t += 5
    # Ráhagyás, hogy a kapus-azonosításnak legyen elég mért ideje.
    frames += _hold(t, 1.0, 10.0, n=250)

    gos = gk_outlet_side(_match(frames))
    h = gos["home"]
    assert h["outlets"] == 7 and h["left"] == 6 and h["right"] == 1
    assert h["left_pct"] is not None
    assert abs(h["left_pct"] - 100.0 * 6 / 7) < 0.5
    assert h["side"] == "bal"

    # Kevés indítás: nincs arány és nincs ítélet.
    few = gk_outlet_side(_match(frames[:30] + frames[-250:]))
    assert few["home"]["side"] is None and few["home"]["left_pct"] is None


def test_gk_free_shot_saves_flags_wall_dependent_keeper():
    """A vendég kapus a fedezett lövéseket mind fogja, a szabadon
    leadottaknak csak a felét → "falfüggő"; kevés lövésnél nincs
    ítélet."""
    from handball.models.tracking import Ball
    from handball.pipeline.goalkeeper import gk_free_shot_saves

    def _cov_shot(t0, save, covered):
        """Hazai lövés a +x kapura; a védő a lövő mellett (fedezett)
        vagy messze tőle (szabad lövés) áll."""
        sx = 29.0
        frames = _range_shot(t0, sx, save=save)
        # A mezőnyvédőt minden kockára hozzátesszük: fedezésnél a lövő
        # MÖGÖTT (nem a labda útjában), szabad lövésnél az oldalvonalnál.
        dx, dy = (sx - 0.5, 10.6) if covered else (sx, 18.0)
        for f in frames:
            f.players.append(PlayerPosition(
                track_id=20, team=Team.AWAY, x=dx, y=dy,
                source=PositionSource.MEASURED, confidence=1.0))
        return frames

    frames = []
    t = 0
    # 6 fedezett lövés (mind védés) és 6 szabad lövés (3 védés).
    plan = [(True, True)] * 6 + [(True, False)] * 3 + [(False, False)] * 3
    for save, covered in plan:
        frames += _cov_shot(t, save, covered)
        t = frames[-1].t + 1
        for i in range(25):   # szünet a debounce-hoz
            frames.append(Frame(t=t + i, players=[],
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 25

    gkf = gk_free_shot_saves(_match(frames))
    a = gkf["away"]
    assert a["covered_shots"] == 6 and a["covered_saves"] == 6
    assert a["free_shots"] == 6 and a["free_saves"] == 3
    assert a["covered_save_pct"] == 100.0 and a["free_save_pct"] == 50.0
    assert a["verdict"] == "falfüggő"

    # A hazai kapusát nem érte lövés → nincs arány és nincs ítélet.
    h = gkf["home"]
    assert h["free_shots"] == 0 and h["covered_shots"] == 0
    assert h["gap_pp"] is None and h["verdict"] is None


# ---- Kapus-védés posztonként (melyik szögből sebezhető) ----------------------

# A poszt-becsléshez használt hazai felállás (a +x kapura támadva).
_ROLE_SPOTS = {1: (34.0, 10.0),   # beálló: 6 m, közép
               2: (36.0, 2.0),    # szélső: a bal sávban
               3: (28.0, 10.0)}   # irányító: 12 m, közép


def _role_shot_match(shots, warmup=150, fps=25.0):
    """Poszt-mintát adó hazai birtoklás, majd a `shots` [(track_id,
    védés?)] listája szerint egy-egy kapura tartó lövés a vendég kapusra."""
    from handball.models.tracking import Ball

    def _players():
        pls = [PlayerPosition(track_id=tid, team=Team.HOME, x=x, y=y,
                              source=PositionSource.MEASURED,
                              confidence=1.0)
               for tid, (x, y) in _ROLE_SPOTS.items()]
        pls.append(PlayerPosition(track_id=99, team=Team.AWAY, x=39.2,
                                  y=10.0, source=PositionSource.MEASURED,
                                  confidence=1.0, role="kapus"))
        return pls

    frames = []
    t = 0
    for _ in range(warmup):
        frames.append(Frame(t=t, players=_players(),
                            ball=Ball(x=28.5, y=10.0, confidence=1.0)))
        t += 1
    for tid, save in shots:
        sx, sy = _ROLE_SPOTS[tid]
        # A labda lassan (lövés-küszöb alatt) a lövőhöz vándorol.
        for i in range(1, 61):
            f_ = i / 60.0
            frames.append(Frame(
                t=t, players=_players(),
                ball=Ball(x=28.5 + (sx - 28.5) * f_,
                          y=10.0 + (sy - 10.0) * f_, confidence=1.0)))
            t += 1
        for _ in range(3):        # a lövő birtokolja a labdát
            frames.append(Frame(t=t, players=_players(),
                                ball=Ball(x=sx, y=sy, confidence=1.0)))
            t += 1
        # A lövés: a lövő helyéről a kapuba (védésnél a kapusnál megáll).
        end_x = 38.6 if save else 40.5
        steps = max(3, int(round(end_x - sx)))
        for i in range(1, steps + 1):
            f_ = i / steps
            frames.append(Frame(
                t=t, players=_players(),
                ball=Ball(x=sx + (end_x - sx) * f_,
                          y=sy + (10.0 - sy) * f_, confidence=1.0)))
            t += 1
        for _ in range(25):       # szünet a debounce-hoz
            frames.append(Frame(t=t, players=_players(),
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
            t += 1
    return Match(MatchMeta(match_id="gr", home_team="H", away_team="A",
                           fps=fps), frames)


def test_gk_saves_by_role_finds_the_weak_angle():
    """A vendég kapus a szélső lövéseit fogja (4-ből 3), a beállóét nem
    (4-ből 0) → a beálló poszt a sebezhető szög."""
    from handball.pipeline.goalkeeper import gk_saves_by_role

    shots = ([(2, True)] * 3 + [(2, False)]
             + [(1, False)] * 4)
    rec = gk_saves_by_role(_role_shot_match(shots))["away"]
    assert rec["on_target"] == 8
    assert rec["roles"]["szélső"]["faced"] == 4
    assert rec["roles"]["szélső"]["save_pct"] == 75.0
    assert rec["roles"]["beálló"]["save_pct"] == 0.0
    assert rec["weak"] is not None
    assert rec["weak"]["poszt"] == "beálló" and rec["weak"]["faced"] == 4
    # A hazai kapusát nem érte lövés (végig a hazai támadott).
    assert gk_saves_by_role(_role_shot_match(shots))["home"]["on_target"] == 0


def test_gk_saves_by_role_needs_enough_shots_per_role():
    """Kevés (4-nél kevesebb) lövésnél az adott posztról nincs ítélet."""
    from handball.pipeline.goalkeeper import gk_saves_by_role

    rec = gk_saves_by_role(_role_shot_match(
        [(2, True), (2, True), (1, False)]))["away"]
    assert rec["on_target"] == 3
    assert rec["weak"] is None


# ---- Kapus-védés lövés-sebesség szerint --------------------------------------

def _speed_shot(t0, step, save=False):
    """HAZAI lövés a +x (vendég) kapura: a labda kockánként `step`
    métert halad (ebből jön a sebesség); save=True → a vendég kapus
    fogja (a labda 38,6-nál áll meg)."""
    from handball.models.tracking import Ball

    frames = []
    sx = 30.0
    for i in range(3):
        pls = [PlayerPosition(track_id=1, team=Team.HOME, x=sx, y=10.0,
                              source=PositionSource.MEASURED,
                              confidence=1.0),
               PlayerPosition(track_id=99, team=Team.AWAY, x=39.2,
                              y=10.0, source=PositionSource.MEASURED,
                              confidence=1.0, role="kapus")]
        frames.append(Frame(t=t0 + i, players=pls,
                            ball=Ball(x=sx, y=10.0, confidence=1.0)))
    t = t0 + 3
    x = sx
    target = 38.6 if save else 40.4
    # Annyi kocka, hogy a lassabb lövés is elérje a célt.
    n_steps = min(60, int((target - sx) / step) + 3)
    for i in range(n_steps):
        x = min(x + step, target)
        pls = [PlayerPosition(track_id=1, team=Team.HOME, x=sx, y=10.0,
                              source=PositionSource.MEASURED,
                              confidence=1.0),
               PlayerPosition(track_id=99, team=Team.AWAY, x=39.2,
                              y=10.0, source=PositionSource.MEASURED,
                              confidence=1.0, role="kapus")]
        frames.append(Frame(t=t + i, players=pls,
                            ball=Ball(x=x, y=10.0, confidence=1.0)))
    return frames


def _speed_band_match(shots, fps=25.0):
    """Lövés-sorozat: a `shots` elemei (kockánkénti lépés, védés?) párok."""
    from handball.models.tracking import Ball

    frames = []
    t = 0
    for (step, save) in shots:
        frames += _speed_shot(t, step, save=save)
        t = frames[-1].t + 1
        for i in range(25):    # szünet a debounce-hoz
            frames.append(Frame(t=t + i, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
        t = frames[-1].t + 1
    return Match(MatchMeta(match_id="gs", home_team="H", away_team="A",
                           fps=fps), frames)


def test_gk_saves_by_speed_splits_hard_and_placed():
    """A kemény (1,2 m/kocka ≈ 108 km/h) lövéseket fogja, a helyezett
    (0,6 m/kocka ≈ 54 km/h) lövéseket nem → a helyezett a gyenge sávja."""
    from handball.pipeline.goalkeeper import gk_saves_by_speed

    shots = ([(1.2, True)] * 4 + [(0.6, False)] * 4)
    rec = gk_saves_by_speed(_speed_band_match(shots))["away"]
    assert rec["hard"]["faced"] == 4 and rec["hard"]["save_pct"] == 100.0
    assert rec["placed"]["faced"] == 4 and rec["placed"]["save_pct"] == 0.0
    assert rec["weak_band"] == "helyezett"
    assert rec["on_target"] == 8


def test_gk_saves_by_speed_needs_both_bands():
    """Ha csak az egyik sávban van elég lövés, nincs ítélet."""
    from handball.pipeline.goalkeeper import gk_saves_by_speed

    rec = gk_saves_by_speed(_speed_band_match([(1.2, True)] * 5))["away"]
    assert rec["hard"]["faced"] == 5 and rec["placed"]["faced"] == 0
    assert rec["weak_band"] is None


# ---- Kapus emberhátrányban ---------------------------------------------------

def _shorthanded_gk_match(sh_saves=4, sh_goals=0, eq_saves=0,
                          eq_goals=4, fps=25.0):
    """A VENDÉG kapusára érkező lövések: előbb egyenlő létszámnál,
    majd egy kiállítás-ablakban (a vendég 5 fővel véd)."""
    from handball.models.tracking import Ball

    frames = []
    t = 0

    def _roster(seconds, away_n, shooter=False, save=False):
        nonlocal t, frames
        for i in range(int(seconds * fps)):
            players = [PlayerPosition(track_id=100 + k, team=Team.HOME,
                                      x=15.0 + k, y=4.0 + k,
                                      source=PositionSource.MEASURED,
                                      confidence=1.0)
                       for k in range(6)]
            players += [PlayerPosition(track_id=200 + k, team=Team.AWAY,
                                       x=25.0 + k, y=4.0 + k,
                                       source=PositionSource.MEASURED,
                                       confidence=1.0)
                        for k in range(away_n)]
            players.append(PlayerPosition(track_id=99, team=Team.AWAY,
                                          x=39.2, y=10.0, role="kapus",
                                          source=PositionSource.MEASURED,
                                          confidence=1.0))
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    def _shot(away_n, save):
        nonlocal t, frames
        for i in range(9):
            players = [PlayerPosition(track_id=1, team=Team.HOME,
                                      x=33.0, y=10.0,
                                      source=PositionSource.MEASURED,
                                      confidence=1.0),
                       PlayerPosition(track_id=99, team=Team.AWAY,
                                      x=39.2, y=10.0, role="kapus",
                                      source=PositionSource.MEASURED,
                                      confidence=1.0)]
            players += [PlayerPosition(track_id=200 + k, team=Team.AWAY,
                                       x=25.0 + k, y=4.0 + k,
                                       source=PositionSource.MEASURED,
                                       confidence=1.0)
                        for k in range(away_n)]
            bx = min(34.0 + i, 38.6 if save else 40.4)
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=bx, y=10.0,
                                          confidence=1.0)))
            t += 1
        _roster(2.0, away_n)

    _roster(20.0, 6)
    for _ in range(eq_saves):
        _shot(6, save=True)
    for _ in range(eq_goals):
        _shot(6, save=False)
    _roster(20.0, 5)          # kiállítás-ablak indul (45 mp-nél hosszabb)
    for _ in range(sh_saves):
        _shot(5, save=True)
    for _ in range(sh_goals):
        _shot(5, save=False)
    _roster(20.0, 5)
    _roster(20.0, 6)          # a létszám visszaáll
    return Match(MatchMeta(match_id="gsh", home_team="H", away_team="A",
                           fps=fps), frames)


def test_gk_shorthanded_saves_flags_the_rising_keeper():
    """Emberhátrányban 4/4 védés, egyenlő létszámnál 0/4 → a kapus a
    két perc alatt nő."""
    from handball.pipeline.goalkeeper import gk_shorthanded_saves

    rec = gk_shorthanded_saves(_shorthanded_gk_match())["away"]
    assert rec["sh"]["faced"] >= 4 and rec["eq"]["faced"] >= 4
    assert rec["sh"]["save_pct"] == 100.0
    assert rec["eq"]["save_pct"] == 0.0
    assert rec["verdict"] == "emberhátrányban nő"


def test_gk_shorthanded_saves_needs_both_situations():
    """Kiállítás nélkül nincs emberhátrányos minta, így nincs ítélet."""
    from handball.pipeline.goalkeeper import gk_shorthanded_saves

    rec = gk_shorthanded_saves(
        _shorthanded_gk_match(sh_saves=0, sh_goals=0))["away"]
    assert rec["gap_pp"] is None and rec["verdict"] is None


# ---- Kapus-bemelegedés (a meccs első tíz perce) ------------------------------

def _early_gk_match(early_saves=0, early_goals=4, late_saves=4,
                    late_goals=0, fps=25.0):
    """A vendég kapusára érkező lövések: előbb a meccs első tíz
    percében, majd utána."""
    from handball.models.tracking import Ball

    frames = []
    t = 0

    def _idle(seconds):
        nonlocal t, frames
        for _ in range(int(seconds * fps)):
            frames.append(Frame(
                t=t, players=[PlayerPosition(
                    track_id=99, team=Team.AWAY, x=39.2, y=10.0,
                    role="kapus", source=PositionSource.MEASURED,
                    confidence=1.0)],
                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
            t += 1

    def _shot(save):
        nonlocal t, frames
        for i in range(9):
            players = [PlayerPosition(track_id=1, team=Team.HOME,
                                      x=33.0, y=10.0,
                                      source=PositionSource.MEASURED,
                                      confidence=1.0),
                       PlayerPosition(track_id=99, team=Team.AWAY,
                                      x=39.2, y=10.0, role="kapus",
                                      source=PositionSource.MEASURED,
                                      confidence=1.0)]
            bx = min(34.0 + i, 38.6 if save else 40.4)
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=bx, y=10.0,
                                          confidence=1.0)))
            t += 1
        _idle(2.0)

    _idle(10.0)
    for _ in range(early_saves):
        _shot(save=True)
    for _ in range(early_goals):
        _shot(save=False)
    _idle(600.0)          # a tizedik perc után
    for _ in range(late_saves):
        _shot(save=True)
    for _ in range(late_goals):
        _shot(save=False)
    return Match(MatchMeta(match_id="gke", home_team="H", away_team="A",
                           fps=fps), frames)


def test_gk_early_saves_flags_the_slow_starter():
    """Az első tíz percben 0/4 védés, utána 4/4 → lassan melegszik be."""
    from handball.pipeline.goalkeeper import gk_early_saves

    rec = gk_early_saves(_early_gk_match())["away"]
    assert rec["early"]["faced"] == 4 and rec["rest"]["faced"] == 4
    assert rec["early"]["save_pct"] == 0.0
    assert rec["rest"]["save_pct"] == 100.0
    assert rec["verdict"] == "lassan melegszik be"


def test_gk_early_saves_needs_both_windows():
    """Ha a meccs elején nincs elég lövés, nincs ítélet."""
    from handball.pipeline.goalkeeper import gk_early_saves

    rec = gk_early_saves(
        _early_gk_match(early_saves=0, early_goals=1))["away"]
    assert rec["gap_pp"] is None and rec["verdict"] is None


# ---- Kapus-bevonás (visszajátszás a kapusnak) --------------------------------

def _keeper_involvement_match(back_passes, fps=25.0):
    """HAZAI támadás-sorozat: a `back_passes` elemenként megadja, hogy
    az adott támadásban megkapja-e a labdát a hazai kapus."""
    from handball.models.tracking import Ball

    frames = []
    t = 0

    def _players(holder_gk):
        pls = [PlayerPosition(track_id=1, team=Team.HOME, x=26.0,
                              y=10.0, source=PositionSource.MEASURED,
                              confidence=1.0),
               PlayerPosition(track_id=9, team=Team.HOME, x=2.0,
                              y=10.0, role="kapus",
                              source=PositionSource.MEASURED,
                              confidence=1.0),
               PlayerPosition(track_id=21, team=Team.AWAY, x=37.0,
                              y=10.0, source=PositionSource.MEASURED,
                              confidence=1.0)]
        return pls

    for to_keeper in back_passes:
        for i in range(int(3.0 * fps)):     # támadás a vendég térfélen
            frames.append(Frame(t=t, players=_players(False),
                                ball=Ball(x=26.0 + 0.01 * i, y=10.0,
                                          confidence=1.0)))
            t += 1
        if to_keeper:
            for _ in range(int(1.0 * fps)):  # visszajátszás a kapusnak
                frames.append(Frame(t=t, players=_players(True),
                                    ball=Ball(x=2.0, y=10.0,
                                              confidence=1.0)))
                t += 1
        for i in range(int(1.5 * fps)):     # vendég-birtoklás: elválasztó
            frames.append(Frame(
                t=t, players=[PlayerPosition(
                    track_id=21, team=Team.AWAY, x=18.0 - 0.05 * i,
                    y=10.0, source=PositionSource.MEASURED,
                    confidence=1.0)],
                ball=Ball(x=18.0 - 0.05 * i, y=10.0, confidence=1.0)))
            t += 1
    return Match(MatchMeta(match_id="kiv", home_team="H", away_team="A",
                           fps=fps), frames)


def test_keeper_involvement_flags_the_back_passing_team():
    """Tíz támadásból ötben megkapja a labdát a kapus → sokat
    játszanak vissza."""
    from handball.pipeline.goalkeeper import keeper_involvement

    rec = keeper_involvement(_keeper_involvement_match(
        [True] * 5 + [False] * 5))["home"]
    assert rec["attacks"] >= 8
    assert rec["share_pct"] is not None and rec["share_pct"] >= 25.0
    assert rec["verdict"] == "sokat játszanak vissza"


def test_keeper_involvement_needs_enough_attacks():
    """Kevés (8-nál kevesebb) mért támadásnál nincs ítélet."""
    from handball.pipeline.goalkeeper import keeper_involvement

    rec = keeper_involvement(_keeper_involvement_match(
        [True, False]))["home"]
    assert rec["share_pct"] is None and rec["verdict"] is None


# ---- Hetesre cserélt kapus (specialista a büntetőkre) ----------------------

from handball.models.tracking import Ball


def _svk_pl(tid, team, x, y, role=None):
    return PlayerPosition(track_id=tid, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0,
                          role=role)


def _svk_match(swap, sevens=2, fps=25.0):
    """Vendég kapus véd a +x kapunál; hazai hetesek. Ha swap igaz, a
    hetes előtt pár másodperccel a 291-es (beugró) kapus áll be."""
    frames = []
    t = 0

    def _block(seconds, keeper_tid, seven=False):
        nonlocal t
        n = int(seconds * fps)
        for i in range(n):
            ball_x, ball_y = (33.0, 10.0) if (seven and i < 30) else (20.0, 6.0)
            frames.append(Frame(t=t, players=[
                _svk_pl(keeper_tid, Team.AWAY, 39.5, 10.0, role="kapus"),
                _svk_pl(1, Team.HOME, 25.0, 10.0)],
                ball=Ball(x=ball_x, y=ball_y, confidence=1.0)))
            t += 1

    for _ in range(sevens):
        _block(50.0, 290)                     # alap-kapus
        if swap:
            _block(5.0, 291)                  # beugró érkezik
            _block(15.0, 291, seven=True)     # hetes a beugróra
            _block(15.0, 291)
        else:
            _block(35.0, 290, seven=True)     # hetes az alap-kapusra
    _block(30.0, 290)
    return _match(frames, fps)


def test_seven_keeper_swaps_flags_the_specialist():
    """Két hetes, mindkettő frissen beállt kapusra → hetesre kapust
    cserélnek."""
    from handball.pipeline.goalkeeper import seven_keeper_swaps

    rec = seven_keeper_swaps(_svk_match(swap=True))["away"]
    assert rec["sevens_against"] == 2 and rec["swaps"] == 2
    assert rec["verdict"] == "hetesre kapust cserélnek"


def test_seven_keeper_swaps_no_swap_no_verdict():
    """Ha a kezdő kapus védi a heteseket, nincs jelzés."""
    from handball.pipeline.goalkeeper import seven_keeper_swaps

    rec = seven_keeper_swaps(_svk_match(swap=False))["away"]
    assert rec["sevens_against"] == 2 and rec["swaps"] == 0
    assert rec["verdict"] is None


def test_seven_keeper_swaps_needs_two_swaps():
    """Egyetlen célzott cserénél még nincs ítélet."""
    from handball.pipeline.goalkeeper import seven_keeper_swaps

    rec = seven_keeper_swaps(_svk_match(swap=True, sevens=1))["away"]
    assert rec["swaps"] == 1 and rec["verdict"] is None


# ---- Kapus állás szerint (hátrányban feljavul-e) ----------------------------

def _gks_match(trail_saves, other_saves, fps=25.0):
    """A vendég kapusra lövünk. Az egál-szakaszban minden hazai gólra
    vendég-egyenlítés jön, így az állás nem billen; aztán egy
    megválaszolatlan hazai gól után a vendég hátrányban kapja a
    trail_saves lövéseit."""
    frames = []
    t = 0

    def _pause():
        nonlocal t
        for _ in range(60):
            frames.append(Frame(t=t, players=[
                _svk_pl(1, Team.HOME, 20.0, 6.0)],
                ball=Ball(x=20.0, y=6.0, confidence=1.0)))
            t += 1

    def _away_goal():
        nonlocal t
        for i in range(8):     # vendég gól a 0-s kapuba (egyenlítés)
            frames.append(Frame(t=t, players=[
                _svk_pl(21, Team.AWAY, 7.0, 10.0)],
                ball=Ball(x=max(6.0 - i, 0.0), y=10.0,
                          confidence=1.0)))
            t += 1
        _pause()

    def _shot(save):
        nonlocal t
        frames.extend(_shot_sequence(t, gk_track=9, save=save))
        t = frames[-1].t + 1
        _pause()

    for save in other_saves:   # egál-szakasz
        _shot(save)
        if not save:
            _away_goal()
    _shot(False)               # megválaszolatlan hazai gól: hátrány
    for save in trail_saves:
        _shot(save)
    return _match(frames, fps)


def test_gk_saves_by_score_flags_the_clutch_keeper():
    """Egálban 1/4 védés, hátrányban 4/4 → hátrányban feljavul."""
    from handball.pipeline.goalkeeper import gk_saves_by_score

    rec = gk_saves_by_score(_gks_match(
        trail_saves=[True] * 4, other_saves=[True, False, False, False]))["away"]
    assert rec["trail"]["faced"] == 4 and rec["trail"]["saves"] == 4
    assert rec["other"]["faced"] == 5
    assert rec["verdict"] == "hátrányban feljavul a kapusuk"


def test_gk_saves_by_score_flags_the_collapsing_keeper():
    """Egálban 4/4 védés, hátrányban 0/4 → hátrányban összeesik."""
    from handball.pipeline.goalkeeper import gk_saves_by_score

    rec = gk_saves_by_score(_gks_match(
        trail_saves=[False] * 4, other_saves=[True] * 4))["away"]
    assert rec["verdict"] == "hátrányban összeesik a kapusuk"


def test_gk_saves_by_score_needs_shots_in_both_states():
    """Ha valamelyik állapotban kevés a minta, nincs ítélet."""
    from handball.pipeline.goalkeeper import gk_saves_by_score

    rec = gk_saves_by_score(_gks_match(
        trail_saves=[True] * 2, other_saves=[True] * 4))["away"]
    assert rec["verdict"] is None


# ---- Kapus-gól veszély (rádob-e a kapusuk az üres kapura) -------------------

def _gkg_match(keeper_shoots, fps=25.0):
    """A vendég kapus (ha keeper_shoots) a saját kapuja elől átdobja a
    labdát az üres hazai (0-s) kapuba."""
    frames = []
    t = 0
    for _ in range(100):       # alapjáték: a kapus a kapujában
        frames.append(Frame(t=t, players=[
            _svk_pl(90, Team.AWAY, 39.0, 10.0, role="kapus"),
            _svk_pl(1, Team.HOME, 20.0, 6.0)],
            ball=Ball(x=20.0, y=6.0, confidence=1.0)))
        t += 1
    shooter = (_svk_pl(90, Team.AWAY, 38.0, 10.0, role="kapus")
               if keeper_shoots else _svk_pl(21, Team.AWAY, 38.0, 10.0))
    for _ in range(5):         # a dobó birtokol
        frames.append(Frame(t=t, players=[shooter],
                            ball=Ball(x=38.0, y=10.0, confidence=1.0)))
        t += 1
    for i in range(10):        # átívelés az üres 0-s kapuba
        frames.append(Frame(t=t, players=[shooter],
                            ball=Ball(x=max(38.0 - i * 4.5, 0.0),
                                      y=10.0, confidence=1.0)))
        t += 1
    return _match(frames, fps)


def test_gk_goal_threat_flags_the_scoring_keeper():
    """A kapus átívelése az üres kapuba → gólveszélyes a kapusuk."""
    from handball.pipeline.goalkeeper import gk_goal_threat

    rec = gk_goal_threat(_gkg_match(True))["away"]
    assert rec["attempts"] >= 1 and rec["goals"] >= 1
    assert rec["verdict"] == "gólveszélyes a kapusuk"


def test_gk_goal_threat_field_scorer_no_flag():
    """Ha mezőnyjátékos dobja ugyanazt a gólt, nincs kapus-jelzés."""
    from handball.pipeline.goalkeeper import gk_goal_threat

    rec = gk_goal_threat(_gkg_match(False))["away"]
    assert rec["attempts"] == 0 and rec["verdict"] is None


# ---- Kapus-hidegedés (hideg kézzel beesik-e a védése) -----------------------

def _gcs_match(cold_saves, warm_saves, fps=25.0):
    """A vendég kapus hosszú csendek után kapja a cold_saves lövéseit,
    sűrűn a warm_saves lövéseit."""
    frames = []
    t = 0

    def _idle(seconds):
        nonlocal t
        for _ in range(int(seconds * fps)):
            frames.append(Frame(t=t, players=[
                _svk_pl(1, Team.HOME, 20.0, 6.0)],
                ball=Ball(x=20.0, y=6.0, confidence=1.0)))
            t += 1

    def _shot(save):
        nonlocal t
        frames.extend(_shot_sequence(t, gk_track=9, save=save))
        t = frames[-1].t + 1

    for save in cold_saves:      # minden lövés előtt 200 mp csend
        _idle(200.0)
        _shot(save)
    for save in warm_saves:      # sűrű lövések (10 mp-enként)
        _idle(10.0)
        _shot(save)
    return _match(frames, fps)


def test_gk_cold_streaks_flags_the_cold_prone_keeper():
    """Hidegen 0/4, melegen 4/4 védés → hidegen sebezhető."""
    from handball.pipeline.goalkeeper import gk_cold_streaks

    rec = gk_cold_streaks(_gcs_match([False] * 4, [True] * 4))["away"]
    assert rec["cold"]["faced"] == 4 and rec["warm"]["faced"] == 4
    assert rec["verdict"] == "hidegen sebezhető a kapusuk"


def test_gk_cold_streaks_flags_the_always_ready_keeper():
    """Hidegen 4/4, melegen 1/4 → hidegen is stabil."""
    from handball.pipeline.goalkeeper import gk_cold_streaks

    rec = gk_cold_streaks(_gcs_match(
        [True] * 4, [True, False, False, False]))["away"]
    assert rec["verdict"] == "hidegen is stabil a kapusuk"


def test_gk_cold_streaks_needs_shots_in_both_bands():
    """Ha valamelyik vödörben kevés a lövés, nincs ítélet."""
    from handball.pipeline.goalkeeper import gk_cold_streaks

    rec = gk_cold_streaks(_gcs_match([False] * 2, [True] * 4))["away"]
    assert rec["verdict"] is None


# ---- Kapus-kipattanó (fogja vagy kiüti a labdát) ----------------------------

def _grc_match(catch_flags, fps=25.0):
    """A vendég kapus védései: a `catch_flags` szerint megfogja a
    labdát, vagy kiüti a lövő elé."""
    frames = []
    t = 0
    for caught in catch_flags:
        shooter = _svk_pl(4, Team.HOME, 33.5, 10.0)
        gk = _svk_pl(9, Team.AWAY, 39.0, 10.0, role="kapus")
        for i, x in enumerate((33.6, 34.9, 36.2, 37.5, 38.8)):
            frames.append(Frame(
                t=t, players=[gk] + ([shooter] if i == 0 else []),
                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1
        if caught:                 # a labda a kapusnál marad
            for _ in range(15):
                frames.append(Frame(t=t, players=[gk, shooter],
                                    ball=Ball(x=39.0, y=10.0,
                                              confidence=1.0)))
                t += 1
        else:                      # kiütött labda a lövő elé pattan
            for x in (37.0, 35.5, 34.0, 33.5, 33.5, 33.5, 33.5):
                frames.append(Frame(t=t, players=[gk, shooter],
                                    ball=Ball(x=x, y=10.0,
                                              confidence=1.0)))
                t += 1
        for _ in range(50):        # szünet
            frames.append(Frame(t=t, players=[
                _svk_pl(1, Team.HOME, 20.0, 6.0)],
                ball=Ball(x=20.0, y=6.0, confidence=1.0)))
            t += 1
    return _match(frames, fps)


def test_gk_rebound_control_flags_the_catching_keeper():
    """Négy fogott védés → fogja a labdát a kapusuk."""
    from handball.pipeline.goalkeeper import gk_rebound_control

    rec = gk_rebound_control(_grc_match([True] * 4))["away"]
    assert rec["saves"] == 4 and rec["caught"] == 4
    assert rec["verdict"] == "fogja a labdát a kapusuk"


def test_gk_rebound_control_flags_the_parrying_keeper():
    """Ha a védett labda rendre a lövő elé pattan, kiüti a kapusuk."""
    from handball.pipeline.goalkeeper import gk_rebound_control

    rec = gk_rebound_control(_grc_match([False] * 4))["away"]
    assert rec["caught"] == 0
    assert rec["verdict"] == "kiüti a labdát a kapusuk"


def test_gk_rebound_control_needs_enough_saves():
    """Kevés (4-nél kevesebb) mért védésnél nincs ítélet."""
    from handball.pipeline.goalkeeper import gk_rebound_control

    rec = gk_rebound_control(_grc_match([True, True]))["away"]
    assert rec["saves"] == 2 and rec["verdict"] is None


def _otr_match(n_outlets=4):
    """Felhozatal-sorozat: a 12-es away szélső (poszt-minta a szélső
    sávban) várja a kapus-indításokat a felezőnél."""
    from handball.models.tracking import Ball

    def _pl(tid, team, x, y, role=None):
        p = PlayerPosition(track_id=tid, team=team, x=x, y=y)
        if role:
            p.role = role
        return p

    frames = []
    t = 0
    for _ in range(150):    # poszt-minta: a 12-es a szélső sávban
        frames.append(Frame(
            t=t, players=[_pl(12, Team.AWAY, 10.0, 3.0),
                          _pl(30, Team.AWAY, 39.0, 10.0, role="kapus")],
            ball=Ball(x=10.0, y=3.0, confidence=1.0)))
        t += 1
    for _ in range(20):     # labda nélküli átvezetés (nincs ál-lövés)
        frames.append(Frame(t=t, players=[], ball=None))
        t += 1
    for _ in range(n_outlets):
        for i in range(8):  # hazai lövés, a kapus fogja
            frames.append(Frame(
                t=t, players=[_pl(1, Team.HOME, 37.0, 10.0),
                              _pl(30, Team.AWAY, 39.0, 10.0,
                                  role="kapus")],
                ball=Ball(x=min(37.4 + 0.6 * i, 38.8), y=10.0,
                          confidence=1.0)))
            t += 1
        for j in range(60):  # az indítás átér a felezőn a 12-eshez
            frames.append(Frame(
                t=t, players=[_pl(30, Team.AWAY, 39.0, 10.0,
                                  role="kapus"),
                              _pl(12, Team.AWAY, 18.0, 10.0)],
                ball=Ball(x=max(38.8 - 0.4 * j, 16.0), y=10.0,
                          confidence=1.0)))
            t += 1
        for _ in range(40):  # szünet a szakaszok közt
            frames.append(Frame(t=t, players=[], ball=None))
            t += 1
    return _match(frames)


def test_outlet_target_roles_points_to_the_wing():
    """A szélső-posztú célpontra menő indítások → a felhozatal a
    szélsőre épül."""
    from handball.pipeline.goalkeeper import outlet_target_roles

    rec = outlet_target_roles(_otr_match())["away"]
    assert rec["outlets"] >= 4
    assert rec["top"] is not None and rec["top"]["poszt"] == "szélső"


def test_outlet_target_roles_needs_enough_outlets():
    """Kevés (4-nél kevesebb) poszthoz kötött célpontnál nincs
    kiemelt poszt."""
    from handball.pipeline.goalkeeper import outlet_target_roles

    rec = outlet_target_roles(_otr_match(n_outlets=3))["away"]
    assert rec["top"] is None


def _ops_match(slow_when_leading=True, n=5, fps=25.0):
    """Vendég védés-indítás sorozatok: döntetlennél gyors (vagy lassú)
    kihozatal, majd egy vendég-gól utáni vezetésnél lassú (vagy
    gyors) — az indítás-tempó állás-függése így mérhető."""
    from handball.models.tracking import Ball

    def _pl(tid, team, x, y, role=None):
        p = PlayerPosition(track_id=tid, team=team, x=x, y=y)
        if role:
            p.role = role
        return p

    frames = []
    t = 0

    def _pause(sec=1.6):
        nonlocal t
        for _ in range(int(sec * fps)):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=25.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    def _save_and_outlet(step):
        nonlocal t
        for i in range(8):      # hazai lövés, a vendég kapus fogja
            frames.append(Frame(
                t=t, players=[_pl(1, Team.HOME, 37.0, 10.0),
                              _pl(30, Team.AWAY, 39.0, 10.0,
                                  role="kapus")],
                ball=Ball(x=min(37.4 + 0.6 * i, 38.8), y=10.0,
                          confidence=1.0)))
            t += 1
        bx = 38.8
        while bx >= 19.0:       # kihozatal a felezőn túlra
            frames.append(Frame(
                t=t, players=[_pl(30, Team.AWAY, 39.0, 10.0,
                                  role="kapus")],
                ball=Ball(x=bx, y=10.0, confidence=1.0)))
            bx -= step
            t += 1
        _pause()

    def _away_goal():
        nonlocal t
        for _ in range(10):
            frames.append(Frame(t=t, players=[_pl(21, Team.AWAY, 6.0, 10.0)],
                                ball=Ball(x=6.0, y=10.0, confidence=1.0)))
            t += 1
        for i in range(7):
            frames.append(Frame(t=t, players=[_pl(21, Team.AWAY, 6.0, 10.0)],
                                ball=Ball(x=max(6.0 - (i + 1) * 1.0, -0.5),
                                          y=10.0, confidence=1.0)))
            t += 1
        _pause()

    fast, slow = 0.4, 0.1
    for _ in range(n):          # döntetlennél
        _save_and_outlet(slow if not slow_when_leading else fast)
    _away_goal()                # a vendégek vezetnek
    for _ in range(n):          # vezetés közben
        _save_and_outlet(slow if slow_when_leading else fast)
    return _match(frames)


def test_outlet_pace_by_score_flags_the_time_waster():
    """Vezetve lassú, egyébként gyors kihozatal → időhúzás."""
    from handball.pipeline.goalkeeper import outlet_pace_by_score

    rec = outlet_pace_by_score(_ops_match(True))["away"]
    assert rec["lead"]["outlets"] >= 4 and rec["rest"]["outlets"] >= 4
    assert rec["verdict"] == "vezetve lassítják az indítást"


def test_outlet_pace_by_score_flags_the_relentless_team():
    """Vezetve is gyors kihozatal → előnyben is pörgetik."""
    from handball.pipeline.goalkeeper import outlet_pace_by_score

    rec = outlet_pace_by_score(_ops_match(False))["away"]
    assert rec["verdict"] == "előnyben is pörgetik"


def test_outlet_pace_by_score_needs_enough_outlets():
    """Kevés (4-nél kevesebb) mért indításnál nincs ítélet."""
    from handball.pipeline.goalkeeper import outlet_pace_by_score

    rec = outlet_pace_by_score(_ops_match(True, n=3))["away"]
    assert rec["verdict"] is None


def _wfk_match(fooled, n_goals=5, fps=25.0):
    """Hazai gól-sorozat a vendég kapu szélére (y=8,8); a vendég
    kapus a lövésnél ellenirányba mozdul (vagy áll)."""
    from handball.models.tracking import Ball

    def _pl(tid, team, x, y, role=None):
        p = PlayerPosition(track_id=tid, team=team, x=x, y=y)
        if role:
            p.role = role
        return p

    frames = []
    t = 0
    for _ in range(n_goals):
        for _ in range(10):     # a lövő birtokol
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, 33.0, 10.0),
                _pl(30, Team.AWAY, 39.2, 10.0, role="kapus")],
                ball=Ball(x=33.0, y=10.0, confidence=1.0)))
            t += 1
        for i in range(8):      # gól a sarokba, a kapus mozdul(hat)
            gy = 10.0 + (0.08 * (i + 1) if fooled else 0.0)
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, 33.0, 10.0),
                _pl(30, Team.AWAY, 39.2, gy, role="kapus")],
                ball=Ball(x=min(33.0 + (i + 1), 40.5),
                          y=10.0 - 1.2 * min(1.0, (i + 1) / 7.0),
                          confidence=1.0)))
            t += 1
        for _ in range(40):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    return _match(frames)


def test_wrongfooted_keeper_flags_the_fooled_keeper():
    """A sarokkal ellenirányba mozduló kapus → elmozdítható."""
    from handball.pipeline.goalkeeper import wrongfooted_keeper

    rec = wrongfooted_keeper(_wfk_match(True))["away"]
    assert rec["goals"] >= 5
    assert rec["verdict"] == "elmozdítható a kapusuk"


def test_wrongfooted_keeper_flags_the_steady_keeper():
    """A helyben maradó kapus → állja a cseleket."""
    from handball.pipeline.goalkeeper import wrongfooted_keeper

    rec = wrongfooted_keeper(_wfk_match(False))["away"]
    assert rec["fooled"] == 0
    assert rec["verdict"] == "a kapusuk állja a cseleket"


def test_wrongfooted_keeper_needs_enough_goals():
    """Kevés (5-nél kevesebb) mért kapott gólnál nincs ítélet."""
    from handball.pipeline.goalkeeper import wrongfooted_keeper

    rec = wrongfooted_keeper(_wfk_match(True, n_goals=3))["away"]
    assert rec["verdict"] is None


def _rdk_match(reading, n_saves=5, fps=25.0):
    """Hazai lövés-sorozat, a vendég kapus fogja: a labda a kapu széle
    (y=8,8) felé tart, a kapus előre mozdul rá (vagy áll)."""
    from handball.models.tracking import Ball

    def _pl(tid, team, x, y, role=None):
        p = PlayerPosition(track_id=tid, team=team, x=x, y=y)
        if role:
            p.role = role
        return p

    frames = []
    t = 0
    for _ in range(n_saves):
        for _ in range(10):     # a lövő birtokol
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, 33.0, 10.0),
                _pl(30, Team.AWAY, 39.2, 10.0, role="kapus")],
                ball=Ball(x=33.0, y=10.0, confidence=1.0)))
            t += 1
        for i in range(7):      # lövés, a kapusnál megáll (védés)
            gy = 10.0 - (0.08 * (i + 1) if reading else 0.0)
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, 33.0, 10.0),
                _pl(30, Team.AWAY, 39.2, gy, role="kapus")],
                ball=Ball(x=min(33.0 + (i + 1), 39.2),
                          y=10.0 - 1.2 * min(1.0, (i + 1) / 6.0),
                          confidence=1.0)))
            t += 1
        for i in range(5):      # a védett labda visszapattan
            frames.append(Frame(t=t, players=[
                _pl(30, Team.AWAY, 39.2, 10.0, role="kapus")],
                ball=Ball(x=39.2 - (i + 1) * 1.5, y=8.8,
                          confidence=1.0)))
            t += 1
        for _ in range(40):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    return _match(frames)


def test_reading_keeper_flags_the_anticipating_keeper():
    """A labda oldala felé induló kapus → olvassa a lövéseket."""
    from handball.pipeline.goalkeeper import reading_keeper

    rec = reading_keeper(_rdk_match(True))["away"]
    assert rec["saves"] >= 5
    assert rec["verdict"] == "olvassa a lövéseket"


def test_reading_keeper_flags_the_reflex_keeper():
    """A helyben álló kapus védései → reflexből véd."""
    from handball.pipeline.goalkeeper import reading_keeper

    rec = reading_keeper(_rdk_match(False))["away"]
    assert rec["read"] == 0
    assert rec["verdict"] == "reflexből véd"


def test_reading_keeper_needs_enough_saves():
    """Kevés (5-nél kevesebb) mért védésnél nincs ítélet."""
    from handball.pipeline.goalkeeper import reading_keeper

    rec = reading_keeper(_rdk_match(True, n_saves=3))["away"]
    assert rec["verdict"] is None


def _olp_match(with_goals, n_losses=3, fps=25.0):
    """A vendég kapus indításait a hazaiak elcsípik; utána (nem) jön
    az azonnali büntető gól."""
    from handball.models.tracking import Ball

    def _pl(tid, team, x, y, role=None):
        p = PlayerPosition(track_id=tid, team=team, x=x, y=y)
        if role:
            p.role = role
        return p

    frames = []
    t = 0
    for _ in range(n_losses):
        for _ in range(8):      # a kapusnál a labda
            frames.append(Frame(t=t, players=[
                _pl(30, Team.AWAY, 39.0, 10.0, role="kapus"),
                _pl(1, Team.HOME, 36.0, 10.0)],
                ball=Ball(x=39.0, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(6):      # az indítást a hazai 1-es csípi el
            frames.append(Frame(t=t, players=[
                _pl(30, Team.AWAY, 39.0, 10.0, role="kapus"),
                _pl(1, Team.HOME, 36.0, 10.0)],
                ball=Ball(x=36.0, y=10.0, confidence=1.0)))
            t += 1
        if with_goals:
            for i in range(24):  # a hazai kihozza a zónából (lassan)
                x = 36.0 - 0.3 * (i + 1)
                frames.append(Frame(t=t, players=[
                    _pl(1, Team.HOME, x, 10.0)],
                    ball=Ball(x=x, y=10.0, confidence=1.0)))
                t += 1
            for i in range(12):  # azonnali gól a +x kapura
                frames.append(Frame(t=t, players=[
                    _pl(1, Team.HOME, 28.8, 10.0)],
                    ball=Ball(x=min(28.8 + (i + 1), 40.5), y=9.5,
                              confidence=1.0)))
                t += 1
        for _ in range(40):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    return _match(frames)


def test_outlet_punishment_flags_the_punished_losses():
    """Az elcsípett indítások után rendre gól esik → gólba kerülnek."""
    from handball.pipeline.goalkeeper import outlet_punishment

    rec = outlet_punishment(_olp_match(True))["away"]
    assert rec["lost"] >= 3 and rec["punished"] >= 2
    assert rec["verdict"] == "az elszórt indításaik gólba kerülnek"


def test_outlet_punishment_flags_the_lucky_losses():
    """Elveszett indítások gyors gól nélkül → megússzák."""
    from handball.pipeline.goalkeeper import outlet_punishment

    rec = outlet_punishment(_olp_match(False, n_losses=4))["away"]
    assert rec["lost"] >= 4 and rec["punished"] == 0
    assert rec["verdict"] == "az indítás-hibáikat megússzák"


def test_outlet_punishment_needs_signal():
    """Kevés elveszett indítás, gól nélkül → nincs ítélet."""
    from handball.pipeline.goalkeeper import outlet_punishment

    rec = outlet_punishment(_olp_match(False, n_losses=2))["away"]
    assert rec["verdict"] is None


def _ens_match(n_windows: int):
    """n_windows üres-kapus (7a6) hazai szakasz döntetlen állásnál:
    a hazai kapus a felezőnél áll, a mezőnyjátékos a labdával támad."""
    meta = MatchMeta(match_id="ens", home_team="H", away_team="A", fps=25.0)

    def pl(tid, team, x, y, role=None):
        return PlayerPosition(track_id=tid, team=team, x=x, y=y, role=role)

    frames = []
    t = 0
    for _ in range(n_windows):
        # 4 mp 7a6: a kapus (2-es) 25 m-re a saját (x=0) kaputól,
        # a mezőnyjátékos (1-es) birtokol a támadó térfélen.
        for _ in range(int(4 * 25)):
            frames.append(Frame(t=t, players=[
                pl(1, Team.HOME, 30.0, 10.0),
                pl(2, Team.HOME, 25.0, 10.0, role="kapus"),
            ], ball=Ball(x=30.0, y=10.0, confidence=1.0)))
            t += 1
        # 3 mp szünet: nincs birtoklás (szabad labda), a kapus hátul.
        for _ in range(int(3 * 25)):
            frames.append(Frame(t=t, players=[
                pl(2, Team.HOME, 1.0, 10.0, role="kapus"),
            ], ball=Ball(x=18.0, y=10.0, confidence=1.0)))
            t += 1
    return Match(meta, frames)


def test_empty_net_by_score_system_seven_six():
    """3 üres-kapus szakasz döntetlennél → állástól függetlenül
    lehozzák a kapust."""
    from handball.pipeline.goalkeeper import empty_net_by_score

    ens = empty_net_by_score(_ens_match(3))
    h = ens["home"]
    assert h["level"] == 3
    assert h["trailing"] == 0
    assert h["verdict"] == "állástól függetlenül lehozzák a kapust"
    assert ens["away"]["verdict"] is None


def test_empty_net_by_score_few_samples_none():
    """2 üres-kapus szakasz → kevés minta, nincs ítélet."""
    from handball.pipeline.goalkeeper import empty_net_by_score

    ens = empty_net_by_score(_ens_match(2))
    assert ens["home"]["level"] == 2
    assert ens["home"]["verdict"] is None


def _gkstreak_match(outcomes):
    """Kapura tartó lövés-sor a hazai (x=0) kapura: outcomes elemei
    "save" vagy "goal". A hazai kapus (role=kapus) a kapuban áll."""
    meta = MatchMeta(match_id="gks", home_team="H", away_team="A", fps=25.0)

    def gk():
        return PlayerPosition(track_id=2, team=Team.HOME, x=0.5, y=10.0,
                              role="kapus")

    frames = []
    t = 0
    for oc in outcomes:
        # Pihenő: a labda a kaputól távol (zóna-reset).
        for _ in range(20):
            frames.append(Frame(t=t, players=[gk()],
                                ball=Ball(x=10.0, y=10.0, confidence=1.0)))
            t += 1
        # Repülés a kapu felé 0,5/kocka lépéssel.
        stop = 1.0 if oc == "save" else -0.5
        x = 10.0
        while x > stop:
            x -= 0.5
            frames.append(Frame(t=t, players=[gk()],
                                ball=Ball(x=max(x, stop), y=10.0,
                                          confidence=1.0)))
            t += 1
        # A labda röviden a végpontján marad (védésnél a kapusnál).
        for _ in range(5):
            frames.append(Frame(t=t, players=[gk()],
                                ball=Ball(x=stop, y=10.0, confidence=1.0)))
            t += 1
    return Match(meta, frames)


def test_gk_save_streaks_flags_streak_keeper():
    """3 védés, gól, 3 védés → két hármas sorozat, ítélet."""
    from handball.pipeline.goalkeeper import gk_save_streaks

    gks = gk_save_streaks(_gkstreak_match(
        ["save", "save", "save", "goal", "save", "save", "save"]))
    h = gks["home"]
    assert h["on_target"] == 7
    assert h["streaks"] == 2
    assert h["longest"] == 3
    assert h["verdict"] == "ha rákap, sorozatban véd a kapusuk"
    assert gks["away"]["on_target"] == 0
    assert gks["away"]["verdict"] is None


def test_gk_save_streaks_no_streak_no_verdict():
    """Váltakozó védés-gól (nincs hármas széria) → nincs ítélet."""
    from handball.pipeline.goalkeeper import gk_save_streaks

    gks = gk_save_streaks(_gkstreak_match(
        ["save", "goal", "save", "goal", "save", "goal"]))
    h = gks["home"]
    assert h["on_target"] == 6
    assert h["streaks"] == 0
    assert h["verdict"] is None
