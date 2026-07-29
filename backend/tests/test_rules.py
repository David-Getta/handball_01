"""
Tesztek a szabály-értő rétegre (rules.py): kiállítás, hétméteres, passzív.

A pálya 40x20 m; a HAZAI a +x (x=40) kapu felé támad.

Futtatás:
    python -m pytest tests/test_rules.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.rules import (
    detect_powerplay, detect_seven_meters, passive_play_risks,
    suspensions_from_powerplay,
)


def _meta(fps=25.0):
    return MatchMeta(match_id="r", home_team="H", away_team="A", fps=fps)


def _pl(track_id, team, x, y):
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0)


def _roster_frames(t0, seconds, home_n, away_n, fps=25.0):
    """`seconds` másodpercnyi kocka, csapatonként adott számú mezőnyjátékossal."""
    frames = []
    n = int(seconds * fps)
    for i in range(n):
        players = [_pl(100 + k, Team.HOME, 15.0 + k, 4.0 + k) for k in range(home_n)]
        players += [_pl(200 + k, Team.AWAY, 25.0 + k, 4.0 + k) for k in range(away_n)]
        frames.append(Frame(t=t0 + i, players=players,
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    return frames


def test_powerplay_detected_and_suspension_built():
    """60 mp-en át 5 hazai vs 6 vendég mezőnyjátékos → hazai emberhátrány."""
    frames = _roster_frames(0, 30, 6, 6)       # normál létszám
    frames += _roster_frames(750, 60, 5, 6)    # kiállítás
    frames += _roster_frames(2250, 30, 6, 6)   # visszaáll
    m = Match(_meta(), frames)
    pps = detect_powerplay(m)
    assert len(pps) == 1
    assert pps[0]["team_down"] == "home"
    assert pps[0]["duration_s"] >= 45.0
    sus = suspensions_from_powerplay(m)
    assert len(sus) == 1 and sus[0].team == Team.HOME
    assert sus[0].is_active(pps[0]["start_frame"] + 10)


def test_no_powerplay_at_full_strength_or_short_gap():
    """Teljes létszámnál, vagy rövid (10 mp) hiánynál nincs jelzés."""
    m = Match(_meta(), _roster_frames(0, 90, 6, 6))
    assert detect_powerplay(m) == []
    frames = _roster_frames(0, 40, 6, 6) + _roster_frames(1000, 10, 5, 6) \
        + _roster_frames(1250, 40, 6, 6)
    assert detect_powerplay(Match(_meta(), frames)) == []


def test_seven_meter_detected():
    """A labda 1 mp-ig mozdulatlan a +x kapu 7 m-es pontján → hazai hétméteres."""
    frames = []
    for t in range(50):  # 2 mp; a labda x=33, y=10 (a 40-es kaputól 7 m)
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 32.0, 10.0)],
                            ball=Ball(x=33.0, y=10.0, confidence=1.0)))
    events = detect_seven_meters(Match(_meta(), frames))
    assert len(events) == 1
    assert events[0]["team"] == "home"


def test_no_seven_meter_for_moving_or_offcenter_ball():
    """Mozgó labda, vagy a ponttól távoli (szélső) állás nem hétméteres."""
    moving = [Frame(t=t, players=[], ball=Ball(x=30.0 + 0.2 * t, y=10.0,
                                               confidence=1.0))
              for t in range(50)]
    assert detect_seven_meters(Match(_meta(), moving)) == []
    corner = [Frame(t=t, players=[], ball=Ball(x=33.0, y=3.0, confidence=1.0))
              for t in range(50)]
    assert detect_seven_meters(Match(_meta(), corner)) == []


def test_passive_play_risk_flags_long_shotless_attack():
    """40 mp-es felállt támadás lövés nélkül → passzív-játék kockázat."""
    frames = []
    n = 40 * 25
    for i in range(n):
        x = 30.0 + 0.5 * (1 if (i // 25) % 2 == 0 else -1) * ((i % 25) / 25.0)
        players = [_pl(1, Team.HOME, x, 10.0), _pl(2, Team.HOME, 28.0, 6.0),
                   _pl(21, Team.AWAY, 37.0, 8.0), _pl(22, Team.AWAY, 37.0, 12.0)]
        frames.append(Frame(t=i, players=players,
                            ball=Ball(x=x, y=10.0, confidence=1.0)))
    risks = passive_play_risks(Match(_meta(), frames))
    assert len(risks) == 1
    assert risks[0]["duration_s"] >= 35.0


def _pp_match_with_shots():
    """Hazai emberelőny (vendég 5 fő) alatt egy hazai gól; utána egyenlő
    létszámnál egy hazai védett lövés. A kapus-jel a védéshez kell."""
    fps = 25.0
    frames = []
    # 60 mp emberelőny: hazai 6, vendég 5 mezőnyjátékos + vendég kapus.
    gk = PlayerPosition(track_id=99, team=Team.AWAY, x=39.0, y=10.0,
                        source=PositionSource.MEASURED, confidence=1.0,
                        role="kapus")
    n_pp = int(60 * fps)
    for i in range(n_pp):
        players = [_pl(100 + k, Team.HOME, 15.0 + k, 4.0 + k) for k in range(6)]
        players += [_pl(200 + k, Team.AWAY, 25.0 + k, 4.0 + k) for k in range(5)]
        players.append(gk)
        # A szakasz elején egy gyors hazai gól-esemény (x 33.6 → 40).
        bx = 33.6 + i if i < 8 else 20.0
        frames.append(Frame(t=i, players=players,
                            ball=Ball(x=min(bx, 40.0), y=10.0, confidence=1.0)))
    # 60 mp egyenlő létszám, az elején egy VÉDETT hazai lövés (megáll a kapusnál).
    for i in range(int(60 * fps)):
        t = n_pp + i
        players = [_pl(100 + k, Team.HOME, 15.0 + k, 4.0 + k) for k in range(6)]
        players += [_pl(200 + k, Team.AWAY, 25.0 + k, 4.0 + k) for k in range(6)]
        players.append(gk)
        bx = min(33.6 + i, 38.8) if i < 12 else 20.0
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=bx, y=10.0, confidence=1.0)))
    return Match(_meta(), frames)


def test_powerplay_efficiency_split():
    from handball.pipeline.rules import powerplay_efficiency
    eff = powerplay_efficiency(_pp_match_with_shots())
    home = eff["home"]
    assert home["pp_shots"] == 1 and home["pp_goals"] == 1
    assert home["pp_eff_pct"] == 100.0
    assert home["eq_shots"] == 1 and home["eq_goals"] == 0
    # A hátrányban lévő vendég kapta a gólt.
    assert eff["away"]["sh_conceded"] == 1
    assert eff["away"]["sh_seconds"] >= 45.0


def test_powerplay_efficiency_empty_without_suspension():
    from handball.pipeline.rules import powerplay_efficiency
    m = Match(_meta(), _roster_frames(0, 90, 6, 6))
    assert powerplay_efficiency(m) == {}


# ---- Hétméteres KIMENETEL (gól / védés / kihagyva) ---------------------------

from handball.pipeline.rules import seven_meter_outcomes, seven_meter_summary


def _seven_then_shot(goal=True, save=False):
    """Hazai hétméteres a +x kapura (1 mp álló labda a 7 m-es ponton), majd
    lövés: gól (y=10), védés (y=10 előtt kapus) vagy mellé (y=5)."""
    frames = []
    t = 0
    for _ in range(30):  # álló labda a (33, 10) ponton — 7 m a 40-es kaputól
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 32.0, 10.0)],
                            ball=Ball(x=33.0, y=10.0, confidence=1.0)))
        t += 1
    y = 10.0 if (goal or save) else 5.0
    for i in range(7):  # a lövés
        players = [_pl(1, Team.HOME, 32.0, 10.0)]
        if save:
            players.append(PlayerPosition(track_id=90, team=Team.AWAY,
                                          x=39.0, y=10.0, role="kapus",
                                          source=PositionSource.MEASURED,
                                          confidence=1.0))
        bx = min(34.0 + i, 39.0 if save else 40.0)
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=bx, y=y, confidence=1.0)))
        t += 1
    return Match(_meta(), frames)


def test_seven_meter_goal_outcome():
    out = seven_meter_outcomes(_seven_then_shot(goal=True))
    assert len(out) == 1
    assert out[0]["team"] == "home" and out[0]["outcome"] == "gól"
    summ = seven_meter_summary(_seven_then_shot(goal=True))
    assert summ["home"] == {"attempts": 1, "goals": 1, "saved": 0, "missed": 0}


def test_seven_meter_missed_outcome():
    out = seven_meter_outcomes(_seven_then_shot(goal=False))
    assert len(out) == 1
    assert out[0]["outcome"] == "kihagyva"


def test_seven_meter_no_shot_is_unknown():
    """Ha az ablakban nincs lövés (pl. újra lefújták), a kimenetel ismeretlen."""
    frames = []
    for t in range(30):
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 32.0, 10.0)],
                            ball=Ball(x=33.0, y=10.0, confidence=1.0)))
    out = seven_meter_outcomes(Match(_meta(), frames))
    assert len(out) == 1
    assert out[0]["outcome"] == "ismeretlen" and out[0]["shooter_id"] is None


def test_seven_meter_direction_detected():
    """A hetes iránya a kapu-síkbeli labdahelyből: a kapu közepére
    tartó lövés "közép", az alacsony y-ra tartó (a +x kapura) "bal"."""
    out = seven_meter_outcomes(_seven_then_shot(goal=True))
    assert len(out) == 1
    assert out[0]["irany"] == "közép"

    frames = []
    t = 0
    for _ in range(30):
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 32.0, 10.0)],
                            ball=Ball(x=33.0, y=10.0, confidence=1.0)))
        t += 1
    for i in range(7):  # a lövés a bal alsó sávba (y=8.8) megy
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 32.0, 10.0)],
                            ball=Ball(x=min(34.0 + i, 40.0), y=8.8,
                                      confidence=1.0)))
        t += 1
    out2 = seven_meter_outcomes(Match(_meta(), frames))
    assert len(out2) == 1
    assert out2[0]["irany"] == "bal"


def test_seven_meter_earner_identified():
    """A hetes előtt a kapuhoz legközelebb járó támadó a kiharcoló."""
    from handball.pipeline.rules import seven_meter_earners

    frames = []
    # 2 mp játék: a 9-es betör a kapu elé, az 1-es hátul áll.
    for t in range(50):
        frames.append(Frame(
            t=t,
            players=[_pl(9, Team.HOME, 37.5, 10.0),
                     _pl(1, Team.HOME, 28.0, 10.0)],
            ball=Ball(x=36.0, y=10.0, confidence=1.0)))
    # Majd a labda megáll a 7 m-es ponton (hetes-jel).
    for t in range(50, 100):
        frames.append(Frame(
            t=t,
            players=[_pl(9, Team.HOME, 34.0, 10.0),
                     _pl(1, Team.HOME, 30.0, 10.0)],
            ball=Ball(x=33.0, y=10.0, confidence=1.0)))
    earners = seven_meter_earners(Match(_meta(), frames))["home"]
    assert earners and earners[0]["player_id"] == 9


def test_suspension_earner_identified():
    """A hátrány kezdete előtt a hazai kapuig betörő vendég játékos a
    kiállítás kiharcolója."""
    from handball.pipeline.rules import suspension_earners

    def mk(t, deep=False, home_n=6):
        players = [_pl(100 + k, Team.HOME, 15.0 + k, 4.0 + k)
                   for k in range(home_n)]
        players += [_pl(200 + k, Team.AWAY, 25.0 + k, 4.0 + k)
                    for k in range(5)]
        # A 205-ös vendég: normálisan hátul, a betörésnél a kapunál.
        players.append(_pl(205, Team.AWAY, 2.0 if deep else 30.0, 9.0))
        return Frame(t=t, players=players,
                     ball=Ball(x=20.0, y=10.0, confidence=1.0))

    frames = [mk(t, deep=(t >= 700)) for t in range(750)]
    frames += [mk(t, home_n=5) for t in range(750, 2250)]  # 2 perc lenyomata
    frames += [mk(t) for t in range(2250, 3000)]
    m = Match(_meta(), frames)
    earners = suspension_earners(m)
    assert earners["away"] and earners["away"][0]["player_id"] == 205
    assert earners["away"][0]["earned"] == 1
    assert earners["home"] == []


def test_suspended_player_identified():
    """A hátrány alatt eltűnő track a kiülő; több eltűnőnél nincs
    jelölés (nincs hamis vádaskodás)."""
    from handball.pipeline.rules import suspended_players

    def mk(t, home_tracks):
        players = [_pl(tid, Team.HOME, 15.0 + (tid % 10), 4.0 + (tid % 6))
                   for tid in home_tracks]
        players += [_pl(200 + k, Team.AWAY, 25.0 + k, 4.0 + k)
                    for k in range(6)]
        return Frame(t=t, players=players,
                     ball=Ball(x=20.0, y=10.0, confidence=1.0))

    full = [100, 101, 102, 103, 104, 105]
    down = [100, 101, 102, 103, 104]  # a 105-ös ült ki
    frames = [mk(t, full) for t in range(750)]
    frames += [mk(t, down) for t in range(750, 2250)]
    frames += [mk(t, full) for t in range(2250, 3000)]
    m = Match(_meta(), frames)
    out = suspended_players(m)
    assert out["home"] == [{"player_id": 105, "suspensions": 1}]
    assert out["away"] == []


def test_key_moments_includes_powerplay_and_seven():
    """A key_moments réteg időrendben hozza a kiállítást és a hetest."""
    from handball.pipeline.momentum import key_moments

    frames = _roster_frames(0, 30, 6, 6)
    frames += _roster_frames(750, 60, 5, 6)     # kiállítás-lenyomat
    frames += _roster_frames(2250, 30, 6, 6)
    t = 3000
    for _ in range(30):  # álló labda a 7 m-es ponton
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 32.0, 10.0)],
                            ball=Ball(x=33.0, y=10.0, confidence=1.0)))
        t += 1
    for i in range(7):  # gól
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 32.0, 10.0)],
                            ball=Ball(x=min(34.0 + i, 40.0), y=10.0,
                                      confidence=1.0)))
        t += 1
    m = Match(_meta(), frames)
    kms = key_moments(m)
    labels = [k["label"] for k in kms]
    assert any("Kiállítás" in lab for lab in labels)
    assert any("Hétméteres" in lab and "gól" in lab for lab in labels)
    # Időrend: a t értékek nem csökkennek.
    ts = [k["t"] for k in kms]
    assert ts == sorted(ts)


def test_key_moment_clip_type_mapped():
    """A kulcs-pillanat klip-típus magyar fájlnév-címkét kap, és a
    key_moments elemei klip-eseménnyé alakíthatók (label-lel)."""
    from handball.pipeline.clips import _TYPE_HU
    from handball.pipeline.momentum import key_moments

    assert _TYPE_HU["key_moment"] == "kulcs-pillanat"
    frames = _roster_frames(0, 30, 6, 6)
    frames += _roster_frames(750, 60, 5, 6)
    frames += _roster_frames(2250, 30, 6, 6)
    m = Match(_meta(), frames)
    ev = [{"t": km["t"], "type": "key_moment", "team": "home",
           "label": km["label"]} for km in key_moments(m)]
    assert ev and all("label" in e and e["label"] for e in ev)


def test_key_moments_lead_change():
    """A vezetés-átvétel gólja kulcs-pillanat; az első vezetés és az
    egyenlítés nem az."""
    from handball.pipeline.momentum import key_moments

    frames = []
    t = 0

    def goal(team):
        nonlocal t
        if team == Team.HOME:
            xs = [min(34.0 + i, 40.0) for i in range(8)]
            px = 33.5
        else:
            xs = [max(6.0 - i, 0.0) for i in range(8)]
            px = 6.5
        for x in xs:
            frames.append(Frame(t=t, players=[_pl(1, team, px, 10.0)],
                                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(30):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    goal(Team.HOME)   # 1–0: első vezetés, nem váltás
    goal(Team.AWAY)   # 1–1: egyenlítés, nem váltás
    goal(Team.AWAY)   # 1–2: vezetés-váltás!
    m = Match(_meta(), frames)
    labels = [k["label"] for k in key_moments(m)]
    changes = [lab for lab in labels if "Vezetés-váltás" in lab]
    assert len(changes) == 1
    assert "1–2" in changes[0] and "A" in changes[0]


def test_key_moments_drought_end():
    """Az 5+ perces gólcsend góllal záruló megtörése kulcs-pillanat;
    a felvétel végéig tartó csend nem az."""
    from handball.pipeline.momentum import key_moments

    frames = []
    t = 0
    # Korai hazai gól, hogy legyen "gólok közti" csend.
    for i in range(8):
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 33.5, 10.0)],
                            ball=Ball(x=min(34.0 + i, 40.0), y=10.0,
                                      confidence=1.0)))
        t += 1
    # ~6 perc csend...
    for _ in range(9000):
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 20.0, 10.0)],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    # ...majd a megtörő gól.
    for i in range(8):
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 33.5, 10.0)],
                            ball=Ball(x=min(34.0 + i, 40.0), y=10.0,
                                      confidence=1.0)))
        t += 1
    for _ in range(100):
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    m = Match(_meta(), frames)
    labels = [k["label"] for k in key_moments(m)]
    ends = [lab for lab in labels if "Gólcsend vége" in lab]
    assert len(ends) == 1
    assert "6 perc" in ends[0] and "H" in ends[0]


def test_discipline_fade_late_suspensions():
    """1 kiállítás az 1. félidőben, 2 a másodikban → a hazai fegyelme a
    hajrára esik; félidő-jel nélkül nincs ítélet."""
    from handball.pipeline.rules import discipline_fade

    fps = 25.0
    frames = []
    # 1. félidő: normál létszám + 1 hazai kiállítás.
    frames += _roster_frames(0, 60, 6, 6)
    frames += _roster_frames(frames[-1].t + 1, 60, 5, 6)
    frames += _roster_frames(frames[-1].t + 1, 60, 6, 6)
    # Szünet: 120 mp üres kocka.
    t = frames[-1].t + 1
    for i in range(int(120 * fps)):
        frames.append(Frame(t=t + i, players=[], ball=None))
    # 2. félidő: 2 hazai kiállítás külön szakaszban.
    frames += _roster_frames(frames[-1].t + 1, 30, 6, 6)
    frames += _roster_frames(frames[-1].t + 1, 60, 5, 6)
    frames += _roster_frames(frames[-1].t + 1, 30, 6, 6)
    frames += _roster_frames(frames[-1].t + 1, 60, 5, 6)
    frames += _roster_frames(frames[-1].t + 1, 30, 6, 6)

    df = discipline_fade(Match(_meta(), frames))
    h = df["home"]
    assert h["fh_susp"] == 1 and h["sh_susp"] == 2
    assert h["verdict"] is None  # 3 kiállítás, de a többlet csak 1

    # +1 hajrá-kiállítással már mintázat.
    frames += _roster_frames(frames[-1].t + 1, 60, 5, 6)
    frames += _roster_frames(frames[-1].t + 1, 30, 6, 6)
    df2 = discipline_fade(Match(_meta(), frames))
    h2 = df2["home"]
    assert h2["sh_susp"] == 3
    assert h2["verdict"] == "hajrában szabálytalankodnak"

    # Félidő-jel nélkül (szünet kivágva) nincs ítélet.
    no_break = [f for f in frames if f.players]
    assert discipline_fade(Match(_meta(), no_break))["home"]["verdict"] is None


def test_seven_meter_defense_mirrors_summary():
    """A hazai hetes-gól a VENDÉG kapus mérlegébe kerül; a mellé menő
    nem 'faced'."""
    from handball.pipeline.rules import seven_meter_defense

    d = seven_meter_defense(_seven_then_shot(goal=True))
    assert d["away"] == {"faced": 1, "saved": 0, "conceded": 1,
                         "missed": 0}
    assert d["home"]["faced"] == 0

    d2 = seven_meter_defense(_seven_then_shot(goal=False))
    assert d2["away"] == {"faced": 0, "saved": 0, "conceded": 0,
                          "missed": 1}


def test_shorthanded_attack_flags_paralysed_offense():
    """A hazai egyenlő létszámnál négy gólt lő, a két perc
    emberhátrányban egyet sem → "megbénul"; a kiállítás nélküli
    vendégnél nincs ítélet."""
    from handball.pipeline.rules import shorthanded_attack

    frames = []
    t = 0

    def _roster(seconds, home_n, away_n):
        nonlocal t, frames
        frames += _roster_frames(t, seconds, home_n, away_n)
        t += int(seconds * 25)

    def _home_goal(home_n, away_n):
        """Hazai gól: a labda a +x kapuvonalig, a létszám változatlan."""
        nonlocal t, frames
        for i in range(8):
            players = [_pl(100 + k, Team.HOME, 15.0 + k, 4.0 + k)
                       for k in range(home_n)]
            players += [_pl(200 + k, Team.AWAY, 25.0 + k, 4.0 + k)
                        for k in range(away_n)]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=min(33.6 + i, 40.0), y=10.0,
                                          confidence=1.0)))
            t += 1

    # Egyenlő létszám: négy gól, közte 50-50 mp játék.
    for _ in range(4):
        _roster(50, 6, 6)
        _home_goal(6, 6)
    # Két perc hazai emberhátrány, gól nélkül (előtte szünet, hogy az
    # utolsó gól biztosan az egyenlő létszámú szakaszra essen).
    _roster(50, 6, 6)
    _roster(120, 5, 6)
    _roster(30, 6, 6)

    sha = shorthanded_attack(Match(_meta(), frames))
    h = sha["home"]
    assert h["sh_seconds"] >= 110.0 and h["sh_goals"] == 0
    assert h["eq_goals"] == 4
    assert h["sh_per_min"] == 0.0 and h["eq_per_min"] > 0.5
    assert h["verdict"] == "megbénul"

    # A vendég nem volt hátrányban → nincs ütem és nincs ítélet.
    a = sha["away"]
    assert a["sh_seconds"] == 0.0
    assert a["sh_per_min"] is None and a["verdict"] is None


def test_powerplay_defense_flags_leaking_advantage():
    """A vendég két perc emberelőnyben két gólt kap a hátrányban lévő
    hazaitól, egyenlő létszámnál semmit → "szivárog"; kiállítás
    nélkül nincs ítélet."""
    from handball.pipeline.rules import powerplay_defense

    frames = []
    t = 0

    def _roster(seconds, home_n, away_n):
        nonlocal t, frames
        frames += _roster_frames(t, seconds, home_n, away_n)
        t += int(seconds * 25)

    def _home_goal(home_n, away_n):
        """Hazai gól: a labda a +x kapuvonalig, a létszám változatlan."""
        nonlocal t, frames
        for i in range(8):
            players = [_pl(100 + k, Team.HOME, 15.0 + k, 4.0 + k)
                       for k in range(home_n)]
            players += [_pl(200 + k, Team.AWAY, 25.0 + k, 4.0 + k)
                        for k in range(away_n)]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=min(33.6 + i, 40.0), y=10.0,
                                          confidence=1.0)))
            t += 1

    # Egyenlő létszám gól nélkül, majd hazai emberhátrány, amelyben a
    # HAZAI (hátrányban lévő) csapat két gólt lő — ezt a vendég
    # emberelőnyös védekezése kapja.
    _roster(200, 6, 6)
    _roster(40, 5, 6)
    _home_goal(5, 6)
    _roster(40, 5, 6)
    _home_goal(5, 6)
    _roster(45, 5, 6)
    _roster(60, 6, 6)

    ppd = powerplay_defense(Match(_meta(), frames))
    a = ppd["away"]
    assert a["pp_seconds"] >= 90.0 and a["pp_conceded"] == 2
    assert a["eq_conceded"] == 0 and a["eq_per_min"] == 0.0
    assert a["pp_per_min"] > 0.2 and a["verdict"] == "szivárog"

    # A hazai nem volt emberelőnyben → nincs ütem és nincs ítélet.
    h = ppd["home"]
    assert h["pp_seconds"] == 0.0
    assert h["pp_per_min"] is None and h["verdict"] is None


# ---- Hetes-okozó védők -------------------------------------------------------

def _seven_conceder_frames(t0, defender_id, defender_y=10.0):
    """Egy hetes: a hazai 9-es tör be a kapu elé, mellette a megadott
    vendég védő áll — utána a labda megáll a 7 m-es ponton."""
    frames = []
    t = t0
    for _ in range(50):
        frames.append(Frame(
            t=t,
            players=[_pl(9, Team.HOME, 37.5, 10.0),
                     _pl(1, Team.HOME, 28.0, 10.0),
                     _pl(defender_id, Team.AWAY, 37.0, defender_y),
                     _pl(23, Team.AWAY, 33.0, 16.0)],
            ball=Ball(x=36.0, y=10.0, confidence=1.0)))
        t += 1
    for _ in range(50):
        frames.append(Frame(
            t=t,
            players=[_pl(9, Team.HOME, 34.0, 10.0),
                     _pl(1, Team.HOME, 30.0, 10.0),
                     _pl(defender_id, Team.AWAY, 37.0, defender_y),
                     _pl(23, Team.AWAY, 33.0, 16.0)],
            ball=Ball(x=33.0, y=10.0, confidence=1.0)))
        t += 1
    return frames


def test_seven_meter_conceder_identified():
    """Két hetesnél is a kiharcoló mellett álló 21-es védő az okozó."""
    from handball.pipeline.rules import seven_meter_conceders

    frames = _seven_conceder_frames(0, 21)
    t = frames[-1].t + 1
    # Játék a két hetes közt (10 mp debounce a felismerésben).
    for i in range(300):
        frames.append(Frame(t=t + i, players=[_pl(9, Team.HOME, 20.0, 10.0)],
                            ball=Ball(x=20.0 + 0.01 * i, y=10.0,
                                      confidence=1.0)))
    frames += _seven_conceder_frames(frames[-1].t + 1, 21)
    rec = seven_meter_conceders(Match(_meta(), frames))["away"]
    assert rec["players"] and rec["players"][0]["player_id"] == 21
    assert rec["players"][0]["conceded"] == 2
    assert rec["top"] is not None and rec["top"]["conceded"] == 2
    # A hazai nem védekezett hetes ellen.
    assert seven_meter_conceders(Match(_meta(), frames))["home"]["top"] is None


def test_seven_meter_conceder_needs_two_cases():
    """Egyetlen hetesnél a heurisztika zajos: nincs megbélyegzett védő."""
    from handball.pipeline.rules import seven_meter_conceders

    rec = seven_meter_conceders(
        Match(_meta(), _seven_conceder_frames(0, 21)))["away"]
    assert rec["players"] and rec["players"][0]["conceded"] == 1
    assert rec["top"] is None


# ---- Emberelőny-tempó -------------------------------------------------------

def _pace_attack(t0, seconds, away_n=6, fps=25.0, attack_s=None):
    """Hazai támadás a vendég térfelén + rövid vendég-birtoklás
    elválasztónak; a vendég létszáma `away_n` (5 = emberhátrány)."""
    frames = []
    t = t0
    attack_s = seconds if attack_s is None else attack_s
    for i in range(int(attack_s * fps)):
        players = [_pl(100 + k, Team.HOME, 26.0 + 0.01 * i + k * 0.5,
                       4.0 + k) for k in range(6)]
        players += [_pl(200 + k, Team.AWAY, 34.0 + k * 0.5, 4.0 + k)
                    for k in range(away_n)]
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=26.0 + 0.01 * i, y=4.0,
                                      confidence=1.0)))
        t += 1
    for i in range(int(2.0 * fps)):     # vendég-birtoklás: elválasztó
        players = [_pl(100 + k, Team.HOME, 6.0 + k * 0.5, 4.0 + k)
                   for k in range(6)]
        players += [_pl(200 + k, Team.AWAY, 14.0 - 0.01 * i + k * 0.5,
                        4.0 + k) for k in range(away_n)]
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=14.0 - 0.01 * i, y=4.0,
                                      confidence=1.0)))
        t += 1
    return frames


def _pp_pace_match(eq_n=6, eq_s=10.0, pp_n=4, pp_s=20.0, fps=25.0):
    """`eq_n` egyenlő létszámú hazai támadás `eq_s` hosszal, majd egy
    kiállítás-ablak `pp_n` hazai támadással, `pp_s` hosszal."""
    frames = []
    t = 0
    for _ in range(eq_n):
        frames += _pace_attack(t, eq_s)
        t = frames[-1].t + 1
    for _ in range(pp_n):
        frames += _pace_attack(t, pp_s, away_n=5)
        t = frames[-1].t + 1
    # A létszám visszaáll (a kiállítás-ablak lezárásához).
    frames += _pace_attack(t, 10.0)
    return Match(_meta(fps), frames)


def test_powerplay_pace_flags_the_slow_powerplay():
    """Emberelőnyben 20 mp-es, egyenlő létszámnál 10 mp-es támadások →
    elnyújtják az emberelőnyt."""
    from handball.pipeline.rules import powerplay_pace

    rec = powerplay_pace(_pp_pace_match())["home"]
    assert rec["pp_attacks"] >= 3 and rec["eq_attacks"] >= 5
    assert rec["gap_s"] is not None and rec["gap_s"] >= 5.0
    assert rec["verdict"] == "elnyújtják emberelőnyben"


def test_powerplay_pace_without_powerplay_has_no_verdict():
    """Kiállítás nélkül nincs emberelőnyös minta, így nincs ítélet."""
    from handball.pipeline.rules import powerplay_pace

    rec = powerplay_pace(_pp_pace_match(pp_n=0))["home"]
    assert rec["pp_attacks"] == 0
    assert rec["gap_s"] is None and rec["verdict"] is None


# ---- Emberhátrány-forma (mit játszanak öt emberrel) --------------------------

def _sh_shape_match(advanced=0, fps=25.0):
    """A HAZAI van emberhátrányban (5 mezőnyjátékos a vendég 6-ja
    ellen); `advanced` játékosuk áll előretolva (a 9 m-es vonalon)."""
    frames = []
    t = 0

    def _rosters(seconds, home_n):
        nonlocal t, frames
        for _ in range(int(seconds * fps)):
            players = []
            for k in range(home_n):
                # Hátsó sáv: 5 m-re a saját (0) kaputól; előretolt: 10 m.
                depth = 10.0 if k < advanced else 5.0
                players.append(_pl(100 + k, Team.HOME, depth, 4.0 + k))
            players += [_pl(200 + k, Team.AWAY, 25.0 + k, 4.0 + k)
                        for k in range(6)]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=12.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    _rosters(30.0, 6)     # normál létszám
    _rosters(60.0, 5)     # kiállítás: a hazai öt emberrel véd
    _rosters(30.0, 6)     # visszaáll
    return Match(_meta(fps), frames)


def test_shorthanded_shape_reads_the_flat_wall():
    """Öt hátsó sávban álló védő → 5-0-s emberhátrány-fal."""
    from handball.pipeline.rules import shorthanded_shape

    rec = shorthanded_shape(_sh_shape_match())["home"]
    assert rec["frames"] >= 100
    assert rec["main"] is not None and rec["main"].startswith("5-0")
    assert rec["main_pct"] >= 60.0


def test_shorthanded_shape_reads_the_advanced_defender():
    """Egy előretolt védővel a fal címkéje 4-1 jellegű."""
    from handball.pipeline.rules import shorthanded_shape

    rec = shorthanded_shape(_sh_shape_match(advanced=1))["home"]
    assert rec["main"] is not None and rec["main"].startswith("4-1")


def test_shorthanded_shape_without_powerplay():
    """Kiállítás nélkül nincs mért kocka és nincs ítélet."""
    from handball.pipeline.rules import shorthanded_shape

    frames = _roster_frames(0, 90, 6, 6)
    rec = shorthanded_shape(Match(_meta(), frames))["home"]
    assert rec["frames"] == 0 and rec["main"] is None


# ---- Kapus-hetesvédés irány szerint ------------------------------------------

def _seven_dir_match(cases, fps=25.0):
    """Hetes-sorozat: a `cases` elemei (y-magasság, védés?) párok — az
    y adja az irányt (8,8 = bal, 10 = közép, 11,2 = jobb a dobó
    szemszögéből a +x kapura)."""
    frames = []
    t = 0
    for (y, save) in cases:
        for _ in range(30):    # álló labda a 7 m-es ponton
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 32.0, 10.0)],
                                ball=Ball(x=33.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        for i in range(7):     # a lövés
            players = [_pl(1, Team.HOME, 32.0, 10.0)]
            if save:
                players.append(PlayerPosition(
                    track_id=90, team=Team.AWAY, x=39.0, y=y,
                    role="kapus", source=PositionSource.MEASURED,
                    confidence=1.0))
            bx = min(34.0 + i, 39.0 if save else 40.0)
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=bx, y=y, confidence=1.0)))
            t += 1
        for i in range(300):   # 12 mp szünet (10 mp hetes-debounce)
            frames.append(Frame(t=t + i, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
        t += 300
    return Match(_meta(fps), frames)


def test_gk_seven_directions_finds_the_weak_corner():
    """A bal sarokba menő heteseket engedi (3-ból 0 védés), a jobb
    sarokba menőket fogja (3-ból 3) → a bal a gyenge iránya."""
    from handball.pipeline.rules import gk_seven_directions

    rec = gk_seven_directions(_seven_dir_match(
        [(8.8, False)] * 3 + [(11.2, True)] * 3))["away"]
    assert rec["faced"] == 6
    assert rec["bal"]["faced"] == 3 and rec["bal"]["save_pct"] == 0.0
    assert rec["jobb"]["save_pct"] == 100.0
    assert rec["weak_dir"] is not None
    assert rec["weak_dir"]["irany"] == "bal"


def test_gk_seven_directions_needs_enough_per_direction():
    """Kevés (3-nál kevesebb) hetesnél az adott irányból nincs ítélet."""
    from handball.pipeline.rules import gk_seven_directions

    rec = gk_seven_directions(_seven_dir_match(
        [(8.8, False), (11.2, True)]))["away"]
    assert rec["faced"] == 2 and rec["weak_dir"] is None
