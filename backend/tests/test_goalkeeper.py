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
