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
