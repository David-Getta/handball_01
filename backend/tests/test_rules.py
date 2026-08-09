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


# ---- Emberelőny-lövők (ki fejez be a két perc alatt) -------------------------

def _pp_shooter_match(shooters, fps=25.0):
    """A VENDÉG emberhátrányban (5 fő), a hazai `shooters` listája
    szerint lőnek a +x kapura a kiállítás-ablakban."""
    frames = []
    t = 0

    def _rosters(seconds, away_n, shooter=None):
        nonlocal t, frames
        for i in range(int(seconds * fps)):
            players = [_pl(100 + k, Team.HOME, 15.0 + k, 4.0 + k)
                       for k in range(6)]
            players += [_pl(200 + k, Team.AWAY, 25.0 + k, 4.0 + k)
                        for k in range(away_n)]
            if shooter is not None:
                players.append(_pl(shooter, Team.HOME, 33.0, 10.0))
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    def _shot(shooter, away_n):
        nonlocal t, frames

        def _cast():
            players = [_pl(100 + k, Team.HOME, 15.0 + k, 4.0 + k)
                       for k in range(6)]
            players += [_pl(200 + k, Team.AWAY, 25.0 + k, 4.0 + k)
                        for k in range(away_n)]
            players.append(_pl(shooter, Team.HOME, 33.0, 10.0))
            return players

        for _ in range(3):   # a labda a lövő kezében (elengedés előtt)
            frames.append(Frame(t=t, players=_cast(),
                                ball=Ball(x=33.2, y=10.0, confidence=1.0)))
            t += 1
        for i in range(8):
            frames.append(Frame(t=t, players=_cast(),
                                ball=Ball(x=min(34.0 + i, 40.0), y=10.0,
                                          confidence=1.0)))
            t += 1
        _rosters(2.0, away_n)     # szünet a lövés-debounce-hoz

    _rosters(30.0, 6)             # normál létszám
    # A kiállítás-ablaknak legalább 45 mp-ig kell tartania, hogy a
    # felismerés emberhátrányként lássa.
    for shooter in shooters:      # kiállítás-ablak: hazai emberelőny
        _rosters(15.0, 5)
        _shot(shooter, 5)
    _rosters(30.0, 6)             # visszaáll
    return Match(_meta(fps), frames)


def test_powerplay_shooters_finds_the_finisher():
    """Négy emberelőnyös lövésből hármat ugyanaz a játékos ad le → ő a
    befejezőjük emberelőnyben."""
    from handball.pipeline.rules import powerplay_shooters

    rec = powerplay_shooters(_pp_shooter_match([7, 7, 7, 9]))["home"]
    assert rec["shots"] == 4
    assert rec["top"] is not None
    assert rec["top"]["player_id"] == 7 and rec["top"]["shots"] == 3


def test_powerplay_shooters_without_powerplay():
    """Kiállítás nélkül nincs emberelőnyös lövés és nincs ítélet."""
    from handball.pipeline.rules import powerplay_shooters

    frames = _roster_frames(0, 90, 6, 6)
    rec = powerplay_shooters(Match(_meta(), frames))["home"]
    assert rec["shots"] == 0 and rec["top"] is None


# ---- Emberhátrány-lövők (ki vállalja a befejezést öt emberrel) ---------------

def _sh_shooter_match(shooters, fps=25.0):
    """A HAZAI van emberhátrányban (5 fő), és a `shooters` listája
    szerint lőnek a +x kapura a kiállítás-ablakban."""
    frames = []
    t = 0

    def _rosters(seconds, home_n, shooter=None):
        nonlocal t, frames
        for i in range(int(seconds * fps)):
            players = [_pl(100 + k, Team.HOME, 15.0 + k, 4.0 + k)
                       for k in range(home_n)]
            players += [_pl(200 + k, Team.AWAY, 25.0 + k, 4.0 + k)
                        for k in range(6)]
            if shooter is not None:
                players.append(_pl(shooter, Team.HOME, 33.0, 10.0))
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    def _shot(shooter, home_n):
        nonlocal t, frames

        def _cast():
            # A lövő az öt egyike — ha hatodikként jelenne meg, a hazai
            # létszám visszaállna, és az emberhátrány-ablak bezárulna.
            players = [_pl(100 + k, Team.HOME, 15.0 + k, 4.0 + k)
                       for k in range(home_n - 1)]
            players += [_pl(200 + k, Team.AWAY, 25.0 + k, 4.0 + k)
                        for k in range(6)]
            players.append(_pl(shooter, Team.HOME, 33.0, 10.0))
            return players

        for _ in range(3):   # a labda a lövő kezében (elengedés előtt)
            frames.append(Frame(t=t, players=_cast(),
                                ball=Ball(x=33.2, y=10.0, confidence=1.0)))
            t += 1
        for i in range(8):
            frames.append(Frame(t=t, players=_cast(),
                                ball=Ball(x=min(34.0 + i, 40.0), y=10.0,
                                          confidence=1.0)))
            t += 1
        _rosters(2.0, home_n)

    _rosters(30.0, 6)
    for shooter in shooters:      # a kiállítás-ablak 45 mp-nél hosszabb
        _rosters(15.0, 5)
        _shot(shooter, 5)
    # Az UTOLSÓ lövés után is marad emberhátrány: a létszám-idővonal
    # ablakokra bontva dolgozik, és a záró ablakba nem eshet bele a
    # visszaállás — különben az utolsó lövés kimaradna az ablakból.
    _rosters(10.0, 5)
    _rosters(30.0, 6)
    return Match(_meta(fps), frames)


def test_shorthanded_shooters_finds_the_counter_threat():
    """Emberhátrányban háromból kettőt ugyanaz a játékos lő → ő a
    kontra-fenyegetésük."""
    from handball.pipeline.rules import shorthanded_shooters

    rec = shorthanded_shooters(_sh_shooter_match([4, 4, 8]))["home"]
    assert rec["shots"] == 3
    assert rec["top"] is not None
    assert rec["top"]["player_id"] == 4 and rec["top"]["shots"] == 2


def test_shorthanded_shooters_without_powerplay():
    """Kiállítás nélkül nincs emberhátrányos lövés és nincs ítélet."""
    from handball.pipeline.rules import shorthanded_shooters

    rec = shorthanded_shooters(
        Match(_meta(), _roster_frames(0, 90, 6, 6)))["home"]
    assert rec["shots"] == 0 and rec["top"] is None


# ---- Hetes-kiharcolás poszt szerint ------------------------------------------

def _ser_match(earner_y=3.0, n_sevens=3, fps=25.0):
    """Hetes-sorozat, ahol a kiharcoló a `earner_y` magasságban
    dolgozik (3 = szélső sáv, 10 = közép); a poszt-becsléshez hosszabb
    birtoklás is jár."""
    frames = []
    t = 0

    def _possession(seconds):
        nonlocal t, frames
        for _ in range(int(seconds * fps)):
            players = [_pl(9, Team.HOME, 36.0, earner_y),
                       _pl(1, Team.HOME, 28.0, 10.0),
                       _pl(2, Team.HOME, 30.0, 14.0)]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=28.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    for _ in range(n_sevens):
        _possession(6.0)
        for _ in range(50):     # a labda áll a 7 m-es ponton: hetes
            frames.append(Frame(
                t=t, players=[_pl(9, Team.HOME, 36.0, earner_y),
                              _pl(1, Team.HOME, 28.0, 10.0)],
                ball=Ball(x=33.0, y=10.0, confidence=1.0)))
            t += 1
        _possession(12.0)
    return Match(_meta(fps), frames)


def test_seven_earner_roles_points_to_the_wing():
    """A szélső sávban dolgozó kiharcoló → a hetesek a szélsőről
    jönnek."""
    from handball.pipeline.rules import seven_earner_roles

    rec = seven_earner_roles(_ser_match())["home"]
    assert rec["sevens"] >= 3
    assert rec["top"] is not None and rec["top"]["poszt"] == "szélső"


def test_seven_earner_roles_needs_enough_sevens():
    """Kevés (3-nál kevesebb) hetesnél nincs ítélet."""
    from handball.pipeline.rules import seven_earner_roles

    rec = seven_earner_roles(_ser_match(n_sevens=2))["home"]
    assert rec["top"] is None


# ---- Hetes-fáradás (mikor adják a heteseket) --------------------------------

def _sevens_fade_match(fh_sevens, sh_sevens, fps=25.0):
    """Hazai heteseket (a vendég adja őket) szórunk a két félidőbe;
    a szünetet üres pálya jelzi."""
    frames = []
    t = 0

    def _seven_block(count):
        nonlocal t
        for _ in range(count):
            for _ in range(30):    # a labda áll a +x 7 m-es ponton
                frames.append(Frame(
                    t=t, players=[_pl(100 + k, Team.HOME, 15.0 + k,
                                      4.0 + k) for k in range(6)] +
                    [_pl(200 + k, Team.AWAY, 25.0 + k, 4.0 + k)
                     for k in range(6)],
                    ball=Ball(x=33.0, y=10.0, confidence=1.0)))
                t += 1
            fill = _roster_frames(t, 11, 6, 6, fps)   # debounce-nyi játék
            frames.extend(fill)
            t = frames[-1].t + 1

    _seven_block(fh_sevens)
    frames.extend(_roster_frames(t, 30, 6, 6, fps))
    t = frames[-1].t + 1
    for _ in range(int(90 * fps)):                     # szünet: üres pálya
        frames.append(Frame(t=t, players=[], ball=None))
        t += 1
    _seven_block(sh_sevens)
    frames.extend(_roster_frames(t, 30, 6, 6, fps))
    return Match(_meta(), frames)


def test_sevens_fade_flags_the_tiring_defense():
    """Egy első és három második félidei adott hetes → a második
    félidőben adják a heteseket."""
    from handball.pipeline.rules import sevens_fade

    rec = sevens_fade(_sevens_fade_match(1, 3))["away"]
    assert rec["fh"] == 1 and rec["sh"] == 3
    assert rec["verdict"] == "a második félidőben adják a heteseket"


def test_sevens_fade_flags_the_cold_start():
    """Fordítva (három az elején, egy a végén) → az elején adják."""
    from handball.pipeline.rules import sevens_fade

    rec = sevens_fade(_sevens_fade_match(3, 1))["away"]
    assert rec["verdict"] == "az elején adják a heteseket"


def test_sevens_fade_needs_enough_sevens():
    """Kevés (4-nél kevesebb) adott hetesnél nincs ítélet."""
    from handball.pipeline.rules import sevens_fade

    rec = sevens_fade(_sevens_fade_match(1, 2))["away"]
    assert rec["fh"] + rec["sh"] == 3 and rec["verdict"] is None


# ---- Visszaállás (mi történik a kiállítás letelte után) ---------------------

def _post_pp_match(scorer_side, cycles=2, fps=25.0):
    """Hazai emberhátrány-szakaszok; a visszaállás után a
    `scorer_side` csapata szerez gólt."""
    frames = []
    t = 0

    def _add(block):
        nonlocal t
        for f in block:
            frames.append(Frame(t=t, players=f.players, ball=f.ball))
            t += 1

    def _goal(side):
        nonlocal t
        for i in range(8):
            if side == "home":     # hazai gól a +x kapuba
                frames.append(Frame(t=t, players=[
                    _pl(1, Team.HOME, 33.0, 10.0)],
                    ball=Ball(x=min(34.0 + i, 40.0), y=10.0,
                              confidence=1.0)))
            else:                  # vendég gól a 0-s kapuba
                frames.append(Frame(t=t, players=[
                    _pl(21, Team.AWAY, 7.0, 10.0)],
                    ball=Ball(x=max(6.0 - i, 0.0), y=10.0,
                              confidence=1.0)))
            t += 1

    for _ in range(cycles):
        _add(_roster_frames(0, 30, 6, 6, fps))    # normál létszám
        _add(_roster_frames(0, 60, 5, 6, fps))    # hazai emberhátrány
        _add(_roster_frames(0, 10, 6, 6, fps))    # visszaállás
        _goal(scorer_side)                        # gól az ablakban
        _add(_roster_frames(0, 30, 6, 6, fps))
    return Match(_meta(), frames)


def test_post_powerplay_flags_the_shaky_return():
    """Két visszaállás után is az ellenfél talál be → a visszaállásnál
    megzavarodnak."""
    from handball.pipeline.rules import post_powerplay

    rec = post_powerplay(_post_pp_match("away"))["home"]
    assert rec["returns"] == 2 and rec["goals_against"] == 2
    assert rec["verdict"] == "a visszaállásnál megzavarodnak"


def test_post_powerplay_flags_the_surging_return():
    """Ha a visszaálló csapat talál be kétszer, feltámadnak."""
    from handball.pipeline.rules import post_powerplay

    rec = post_powerplay(_post_pp_match("home"))["home"]
    assert rec["goals_for"] == 2
    assert rec["verdict"] == "a visszaálló emberrel feltámadnak"


def test_post_powerplay_needs_enough_returns():
    """Egyetlen mért visszaállásnál nincs ítélet."""
    from handball.pipeline.rules import post_powerplay

    rec = post_powerplay(_post_pp_match("away", cycles=1))["home"]
    assert rec["returns"] == 1 and rec["verdict"] is None


# ---- Hetes utáni percek (leragadnak-e az adott hetes után) ------------------

def _psl_match(with_extra, sevens=3, fps=25.0):
    """Hazai hetesek (a vendég adja); ha with_extra, a hetes utáni
    percben további hazai mezőnygól is esik."""
    frames = []
    t = 0
    for _ in range(sevens):
        for _ in range(30):    # a labda áll a +x 7 m-es ponton
            frames.append(Frame(t=t, players=[
                _pl(k + 100, Team.HOME, 15.0 + k, 4.0 + k)
                for k in range(6)] + [
                _pl(k + 200, Team.AWAY, 25.0 + k, 4.0 + k)
                for k in range(6)],
                ball=Ball(x=33.0, y=10.0, confidence=1.0)))
            t += 1
        frames.extend(_roster_frames(t, 20, 6, 6, fps))
        t = frames[-1].t + 1
        if with_extra:
            for i in range(8):     # további hazai gól az ablakban
                frames.append(Frame(t=t, players=[
                    _pl(1, Team.HOME, 33.0, 10.0)],
                    ball=Ball(x=min(34.0 + i, 40.0), y=10.0,
                              confidence=1.0)))
                t += 1
        frames.extend(_roster_frames(t, 60, 6, 6, fps))
        t = frames[-1].t + 1
    return Match(_meta(), frames)


def test_post_seven_lapses_flags_the_stalled_defense():
    """Három adott hetes után rendre további gól jön → a hetes utáni
    percben is büntetik őket."""
    from handball.pipeline.rules import post_seven_lapses

    rec = post_seven_lapses(_psl_match(True))["away"]
    assert rec["sevens_against"] == 3 and rec["extra_conceded"] >= 2
    assert rec["verdict"] == "a hetes utáni percben is büntetik őket"


def test_post_seven_lapses_clean_restart_no_verdict():
    """Ha a hetes után nincs további gól, nincs jelzés."""
    from handball.pipeline.rules import post_seven_lapses

    rec = post_seven_lapses(_psl_match(False))["away"]
    assert rec["extra_conceded"] == 0 and rec["verdict"] is None


def test_post_seven_lapses_needs_enough_sevens():
    """Kevés (3-nál kevesebb) adott hetesnél nincs ítélet."""
    from handball.pipeline.rules import post_seven_lapses

    rec = post_seven_lapses(_psl_match(True, sevens=2))["away"]
    assert rec["sevens_against"] == 2 and rec["verdict"] is None


# ---- Kiállítás-posztok (melyik poszt hozza a kétperceseket) -----------------

def _sur_match(n_susp=3, fps=25.0):
    """Kiállítás-sorozat: a vendég 205-ös a szélső sávban játszik
    (poszt-minta), a betörései után a hazaiak emberhátrányba
    kerülnek — ő a kiharcoló."""
    frames = []
    t = 0

    def mk(deep=False, home_n=6, poss_away=False):
        nonlocal t
        players = [_pl(100 + k, Team.HOME, 15.0 + k, 4.0 + k)
                   for k in range(home_n)]
        players += [_pl(200 + k, Team.AWAY, 25.0 + k, 4.0 + k)
                    for k in range(5)]
        players.append(_pl(205, Team.AWAY,
                           2.0 if deep else 10.0, 3.0))
        ball = (Ball(x=25.0, y=4.0, confidence=1.0) if poss_away
                else Ball(x=20.0, y=10.0, confidence=1.0))
        frames.append(Frame(t=t, players=players, ball=ball))
        t += 1

    for _ in range(150):        # poszt-minta: vendég birtoklás
        mk(poss_away=True)
    for _ in range(n_susp):
        for _ in range(50):     # betörés a kapuig
            mk(deep=True, poss_away=True)
        for _ in range(1500):   # 60 mp emberhátrány (5 mezőnyhazai)
            mk(home_n=5)
        for _ in range(300):    # vissza 6-ra a szakaszok közt
            mk()
    return Match(_meta(fps), frames)


def test_susp_earner_roles_points_to_the_wing():
    """A szélső sávban dolgozó kiharcoló → a kétpercesek a szélsőről
    jönnek."""
    from handball.pipeline.rules import susp_earner_roles

    rec = susp_earner_roles(_sur_match())["away"]
    assert rec["suspensions"] >= 3
    assert rec["top"] is not None and rec["top"]["poszt"] == "szélső"


def test_susp_earner_roles_needs_enough_suspensions():
    """Kevés (3-nál kevesebb) poszthoz kötött kiállításnál nincs
    kiemelt poszt."""
    from handball.pipeline.rules import susp_earner_roles

    rec = susp_earner_roles(_sur_match(n_susp=2))["away"]
    assert rec["top"] is None


def _sps_away_goal_frames(t0, fps=25.0, hold_x=6.0):
    """Egy vendég-gól: 6v6 létszám mellett a vendég lövő hold_x-ről a
    x=0 kapuba lő, majd a labda lassú visszavitel helyett a felezőre
    kerül (zóna-reset szünettel)."""
    def crowd(shooter_ball_x, shooter_x=hold_x):
        players = [_pl(100 + k, Team.HOME, 15.0 + k, 3.0 + 2 * k)
                   for k in range(6)]
        players += [_pl(201 + k, Team.AWAY, 16.0 + k, 4.0 + 2 * k)
                    for k in range(5)]
        players.append(_pl(200, Team.AWAY, shooter_x, 10.0))
        return players

    frames = []
    t = t0
    # 40 kocka: a vendég lövő tartja a labdát (hold_x,10)-nél.
    for _ in range(40):
        frames.append(Frame(t=t, players=crowd(hold_x),
                            ball=Ball(x=hold_x, y=10.0, confidence=1.0)))
        t += 1
    # Lövés: a labda 0,5/kocka lépésben a kapuba (x=0 alá) repül.
    x = hold_x
    while x > -0.5:
        x -= 0.5
        frames.append(Frame(t=t, players=crowd(x),
                            ball=Ball(x=max(x, -0.5), y=10.0,
                                      confidence=1.0)))
        t += 1
    # Zóna-reset: a labda a felezőn pihen 40 kockát.
    for _ in range(40):
        frames.append(Frame(t=t, players=crowd(20.0),
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    return frames, t


def test_suspensions_by_score_frustration_verdict():
    """3 korai vendég-gól után 3 hazai kiállítás (hátrányban) →
    'hátrányban elszáll a fegyelmük'."""
    from handball.pipeline.rules import suspensions_by_score

    frames = []
    t = 0
    for _ in range(3):
        gf, t = _sps_away_goal_frames(t)
        frames += gf
    # 3 hazai kiállítás külön 60 mp-es szakaszban, köztük visszaállás.
    for _ in range(3):
        frames += _roster_frames(t, 60, 5, 6)
        t = frames[-1].t + 1
        frames += _roster_frames(t, 30, 6, 6)
        t = frames[-1].t + 1

    sps = suspensions_by_score(Match(_meta(), frames))
    h = sps["home"]
    assert h["trailing"] == 3
    assert h["leading"] == 0 and h["level"] == 0
    assert h["verdict"] == "hátrányban elszáll a fegyelmük"
    assert sps["away"]["verdict"] is None


def test_suspensions_by_score_few_samples_none():
    """2 kiállítás (döntetlennél) → kevés minta, nincs ítélet."""
    from handball.pipeline.rules import suspensions_by_score

    frames = []
    t = 0
    for _ in range(2):
        frames += _roster_frames(t, 60, 5, 6)
        t = frames[-1].t + 1
        frames += _roster_frames(t, 30, 6, 6)
        t = frames[-1].t + 1
    sps = suspensions_by_score(Match(_meta(), frames))
    assert sps["home"]["trailing"] + sps["home"]["leading"] \
        + sps["home"]["level"] == 2
    assert sps["home"]["verdict"] is None


def test_sevens_by_score_trailing_pattern():
    """3 vendég-gól után 3 hazai kiharcolt hetes → hátrányban
    harcolják ki a heteseiket."""
    from handball.pipeline.rules import sevens_by_score

    frames = []
    t = 0
    for _ in range(3):
        gf, t = _sps_away_goal_frames(t, hold_x=10.0)
        frames += gf
    for _ in range(3):
        # Hetes-jel: a labda 2 mp-ig áll a +x kapu 7 m-es pontján.
        for _ in range(50):
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME,
                                                  32.0, 10.0)],
                                ball=Ball(x=33.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        # 11 mp szünet a felezőn (debounce + zóna-reset).
        for _ in range(int(11 * 25)):
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME,
                                                  20.0, 10.0)],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    svs = sevens_by_score(Match(_meta(), frames))
    h = svs["home"]
    assert h["trailing"] == 3
    assert h["leading"] == 0 and h["level"] == 0
    assert h["verdict"] == "hátrányban harcolják ki a heteseiket"
    assert svs["away"]["verdict"] is None


def test_sevens_by_score_few_samples_none():
    """2 kiharcolt hetes → kevés minta, nincs ítélet."""
    from handball.pipeline.rules import sevens_by_score

    frames = []
    t = 0
    for _ in range(2):
        for _ in range(50):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=33.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(int(11 * 25)):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    svs = sevens_by_score(Match(_meta(), frames))
    assert svs["home"]["level"] == 2
    assert svs["home"]["verdict"] is None


def test_excess_players_flags_overlapping_subs():
    """Két 20 mp-es szakaszban 7 hazai mezőnyjátékos → létszám-hiba."""
    from handball.pipeline.rules import excess_players

    frames = _roster_frames(0, 30, 6, 6)
    frames += _roster_frames(frames[-1].t + 1, 20, 7, 6)
    frames += _roster_frames(frames[-1].t + 1, 30, 6, 6)
    frames += _roster_frames(frames[-1].t + 1, 20, 7, 6)
    frames += _roster_frames(frames[-1].t + 1, 30, 6, 6)

    xsp = excess_players(Match(_meta(), frames))
    assert xsp["home"]["windows"] >= 2
    assert xsp["home"]["verdict"] == \
        "csere-átfedésben hetedik ember a pályán"
    assert xsp["away"]["windows"] == 0
    assert xsp["away"]["verdict"] is None


def test_excess_players_normal_roster_none():
    """Végig 6v6 → nincs létszám-hiba."""
    from handball.pipeline.rules import excess_players

    xsp = excess_players(Match(_meta(), _roster_frames(0, 90, 6, 6)))
    assert xsp["home"]["windows"] == 0
    assert xsp["home"]["verdict"] is None


def test_double_shorthand_survived():
    """30 mp négy hazai mezőnyjátékossal, kapott gól nélkül → a kettős
    hátrányt is túlélik."""
    from handball.pipeline.rules import double_shorthand

    frames = _roster_frames(0, 30, 6, 6)
    frames += _roster_frames(frames[-1].t + 1, 30, 4, 6)
    frames += _roster_frames(frames[-1].t + 1, 30, 6, 6)
    dsh = double_shorthand(Match(_meta(), frames))
    assert dsh["home"]["seconds"] >= 20.0
    assert dsh["home"]["conceded"] == 0
    assert dsh["home"]["verdict"] == "a kettős hátrányt is túlélik"
    assert dsh["away"]["verdict"] is None


def test_double_shorthand_fatal():
    """Négy hazai mezőnyjátékos mellett két gyors kapott gól → a kettős
    emberhátrány végzetes."""
    from handball.pipeline.rules import double_shorthand

    def cast(ball_x):
        players = [_pl(100 + k, Team.HOME, 15.0 + k, 6.0 + 2 * k)
                   for k in range(4)]
        players.append(_pl(200, Team.AWAY, 10.0, 10.0))
        players += [_pl(201 + k, Team.AWAY, 25.0 + k, 4.0 + 2 * k)
                    for k in range(5)]
        return players, Ball(x=ball_x, y=10.0, confidence=1.0)

    frames = _roster_frames(0, 30, 6, 6)
    t = frames[-1].t + 1
    # 40 mp 4v6, közben két vendég-gól az x=0 kapura.
    for _ in range(2):
        for _ in range(int(4 * 25)):
            pl, b = cast(10.0)
            frames.append(Frame(t=t, players=pl, ball=b))
            t += 1
        x = 10.0
        while x > -0.5:
            x -= 0.5
            pl, b = cast(max(x, -0.5))
            frames.append(Frame(t=t, players=pl, ball=b))
            t += 1
        for _ in range(int(5 * 25)):
            pl, b = cast(20.0)
            frames.append(Frame(t=t, players=pl, ball=b))
            t += 1
    frames += _roster_frames(t, 30, 6, 6)

    dsh = double_shorthand(Match(_meta(), frames))
    assert dsh["home"]["conceded"] >= 2
    assert dsh["home"]["verdict"] == "a kettős emberhátrány végzetes nekik"


# ---- Hetes-oldal (merre dobják a heteseiket) --------------------------------

def _svd_match(ys, fps=25.0):
    """`ys` = hetesenként a lövés cél-y-ja a +x kapun (8.8 = bal sáv,
    10.0 = közép, 11.2 = jobb). Minden hetes: 1 mp álló labda a 7 m-es
    ponton, lövés, majd szünet, hogy a hetesek külön eseményként
    látszódjanak."""
    frames = []
    t = 0
    for y in ys:
        for _ in range(30):
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 32.0, 10.0)],
                                ball=Ball(x=33.0, y=10.0, confidence=1.0)))
            t += 1
        for i in range(7):
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 32.0, 10.0)],
                                ball=Ball(x=min(34.0 + i, 40.0), y=y,
                                          confidence=1.0)))
            t += 1
        for _ in range(int(4 * fps)):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_seven_shot_directions_finds_the_habit_side():
    """Ha a hetesek négyötöde a bal sávba megy, a kapus előre eldöntött
    vetődéssel készülhet."""
    from handball.pipeline.rules import (SVD_MIN_ATTEMPTS,
                                         seven_shot_directions)

    rec = seven_shot_directions(_svd_match([8.8, 8.8, 8.8, 8.8, 11.2]))["home"]
    assert rec["attempts"] >= SVD_MIN_ATTEMPTS, rec
    assert rec["dominant"] == "bal", rec
    assert rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "vetődhet" in rec["verdict"], rec


def test_seven_shot_directions_silent_with_few_attempts():
    """Két mérhető hetesből nincs ítélet."""
    from handball.pipeline.rules import seven_shot_directions

    rec = seven_shot_directions(_svd_match([8.8, 8.8]))["home"]
    assert rec["dominant"] is None and rec["verdict"] is None, rec


def _svr_match(defenders):
    """`defenders` = okozott hetesenként a kiharcoló mellett álló
    VENDÉG védő (21: beálló, 23: szélső). Első szakasz: vendég-
    birtoklás a -x kapu felé, ebből áll össze a poszt-becslés; utána
    a hetesek a meglévő okozó-minta szerint, 12 mp-es szünetekkel."""
    pos = {21: (6.0, 10.0), 23: (6.0, 1.0)}
    frames = []
    t = 0
    for _ in range(120):             # vendég-birtoklás: poszt-minta
        frames.append(Frame(
            t=t,
            players=[_pl(9, Team.HOME, 20.0, 10.0),
                     _pl(21, Team.AWAY, *pos[21]),
                     _pl(23, Team.AWAY, *pos[23])],
            ball=Ball(x=6.2, y=10.0, confidence=1.0)))
        t += 1
    for tid in defenders:
        frames += _seven_conceder_frames(t, tid)
        t = frames[-1].t + 1
        for i in range(300):         # szünet a hetes-debounce miatt
            frames.append(Frame(t=t, players=[_pl(9, Team.HOME, 20.0,
                                                  10.0)],
                                ball=Ball(x=20.0 + 0.01 * i, y=10.0,
                                          confidence=1.0)))
            t += 1
    return Match(_meta(), frames)


def test_seven_conceder_roles_names_the_soft_lane():
    """Ha az okozott hetesek zöme ugyanannak a posztnak a sávjában
    szakad be, oda érdemes betörést vezetni."""
    from handball.pipeline.rules import (SVR_MIN_SEVENS,
                                         seven_conceder_roles)

    rec = seven_conceder_roles(_svr_match([21] * 3 + [23]))["away"]
    assert rec["sevens"] >= SVR_MIN_SEVENS, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "betörést" in rec["verdict"], rec


def test_seven_conceder_roles_silent_with_few_sevens():
    """Néhány okozott hetesből nincs ítélet."""
    from handball.pipeline.rules import seven_conceder_roles

    rec = seven_conceder_roles(_svr_match([21, 23]))["away"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


def _sup_match(sitters):
    """`sitters` = kiállításonként a hátrány alatt eltűnő HAZAI játékos
    (105: beálló, 104: irányító). A teljes létszámú szakaszok hazai
    támadó-birtoklások (ezekből áll össze a poszt-becslés), köztük
    60 mp-es 5v6 hátrányok, amelyekből a megadott játékos hiányzik."""
    home_pos = {100: (28.0, 10.0), 101: (30.0, 7.0), 102: (30.0, 13.0),
                103: (35.0, 3.0), 104: (29.0, 13.0), 105: (34.0, 10.0)}

    def mk(t, home_tracks):
        players = [_pl(tid, Team.HOME, *home_pos[tid])
                   for tid in home_tracks]
        players += [_pl(200 + k, Team.AWAY, 20.0 + k, 4.0 + k)
                    for k in range(6)]
        return Frame(t=t, players=players,
                     ball=Ball(x=34.2, y=10.0, confidence=1.0))

    full = sorted(home_pos)
    frames = []
    t = 0
    for tid in sitters:
        for _ in range(750):         # teljes létszám: támadó-birtoklás
            frames.append(mk(t, full)); t += 1
        down = [x for x in full if x != tid]
        for _ in range(1500):        # 60 mp hátrány a kiülő nélkül
            frames.append(mk(t, down)); t += 1
    for _ in range(750):
        frames.append(mk(t, full)); t += 1
    return Match(_meta(), frames)


def test_suspended_roles_names_the_punished_post():
    """Ha a kétpercek zöme ugyanarra a posztra jár, a meccs elején oda
    kell vezetni a játékot."""
    from handball.pipeline.rules import SUP_MIN_SUSP, suspended_roles

    rec = suspended_roles(_sup_match([105] * 3 + [104]))["home"]
    assert rec["suspensions"] >= SUP_MIN_SUSP, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "fékezve véd" in rec["verdict"], rec


def test_suspended_roles_silent_with_few_suspensions():
    """Néhány kiállításból nincs ítélet."""
    from handball.pipeline.rules import suspended_roles

    rec = suspended_roles(_sup_match([105, 104]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


def _ppr_match(shooters, fps=25.0):
    """Mint a _pp_shooter_match, de a lövők posztja eltér: a 7-es
    beálló (33, 10), a 9-es szélső (35, 3)."""
    spos = {7: (33.0, 10.0), 9: (35.0, 3.0)}
    frames = []
    t = 0

    def _rosters(seconds, away_n, extra=()):
        nonlocal t, frames
        for _ in range(int(seconds * fps)):
            players = [_pl(100 + k, Team.HOME, 15.0 + k, 4.0 + k)
                       for k in range(6)]
            players += [_pl(200 + k, Team.AWAY, 25.0 + k, 4.0 + k)
                        for k in range(away_n)]
            players += [_pl(tid, Team.HOME, *spos[tid])
                        for tid in extra]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    def _shot(shooter, away_n):
        nonlocal t, frames
        sx, sy = spos[shooter]

        def _cast():
            players = [_pl(100 + k, Team.HOME, 15.0 + k, 4.0 + k)
                       for k in range(6)]
            players += [_pl(200 + k, Team.AWAY, 25.0 + k, 4.0 + k)
                        for k in range(away_n)]
            players.append(_pl(shooter, Team.HOME, sx, sy))
            return players

        for _ in range(3):
            frames.append(Frame(t=t, players=_cast(),
                                ball=Ball(x=sx + 0.2, y=sy,
                                          confidence=1.0)))
            t += 1
        for i in range(8):
            frames.append(Frame(t=t, players=_cast(),
                                ball=Ball(x=min(sx + 1.0 + i, 40.0),
                                          y=sy, confidence=1.0)))
            t += 1
        _rosters(2.0, away_n)

    _rosters(30.0, 6)
    for shooter in shooters:
        _rosters(15.0, 5, extra=(shooter,))
        _shot(shooter, 5)
    _rosters(30.0, 6)
    return Match(_meta(fps), frames)


def test_powerplay_shooter_roles_names_the_finishing_post():
    """Ha az emberelőnyük rendre ugyanarra a posztra fut ki,
    hátrányban az ő sávját kell tartani."""
    from handball.pipeline.rules import (PPR_MIN_SHOTS,
                                         powerplay_shooter_roles)

    rec = powerplay_shooter_roles(_ppr_match([7, 7, 7, 9]))["home"]
    assert rec["shots"] >= PPR_MIN_SHOTS, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "sávját kell tartani" in rec["verdict"], rec


def test_powerplay_shooter_roles_silent_with_few_shots():
    """Néhány emberelőny-lövésből nincs ítélet."""
    from handball.pipeline.rules import powerplay_shooter_roles

    rec = powerplay_shooter_roles(_ppr_match([7, 9]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


def _shr_match(shooter_windows, fps=25.0):
    """A HAZAI van emberhátrányban; a `shooter_windows` elemei
    (lövő, lövésszám) párok — ablakonként EGY lövő, hogy a
    track-halmaz az ablakon belül ne változzon. A 4-es beálló
    (33, 10), a 8-as szélső (35, 3); a poszt-mintát a teljes
    létszámú szakaszok adják (a labda a lövőknél van)."""
    spos = {4: (33.0, 10.0), 8: (35.0, 3.0)}
    frames = []
    t = 0

    def _full(seconds, ball_at=4):
        nonlocal t, frames
        bx, by = spos[ball_at]
        for _ in range(int(seconds * fps)):
            players = [_pl(100 + k, Team.HOME, 15.0 + k, 4.0 + k)
                       for k in range(4)]
            players += [_pl(tid, Team.HOME, *xy)
                        for tid, xy in spos.items()]
            players += [_pl(200 + k, Team.AWAY, 25.0 + k, 4.0 + k)
                        for k in range(6)]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=bx + 0.2, y=by,
                                          confidence=1.0)))
            t += 1

    def _down(seconds, shooter):
        nonlocal t, frames
        for _ in range(int(seconds * fps)):
            players = [_pl(100 + k, Team.HOME, 15.0 + k, 4.0 + k)
                       for k in range(4)]
            players.append(_pl(shooter, Team.HOME, *spos[shooter]))
            players += [_pl(200 + k, Team.AWAY, 25.0 + k, 4.0 + k)
                        for k in range(6)]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    def _shot(shooter):
        nonlocal t, frames
        sx, sy = spos[shooter]

        def _cast():
            players = [_pl(100 + k, Team.HOME, 15.0 + k, 4.0 + k)
                       for k in range(4)]
            players.append(_pl(shooter, Team.HOME, sx, sy))
            players += [_pl(200 + k, Team.AWAY, 25.0 + k, 4.0 + k)
                        for k in range(6)]
            return players

        for _ in range(3):
            frames.append(Frame(t=t, players=_cast(),
                                ball=Ball(x=sx + 0.2, y=sy,
                                          confidence=1.0)))
            t += 1
        for i in range(8):
            frames.append(Frame(t=t, players=_cast(),
                                ball=Ball(x=min(sx + 1.0 + i, 40.0),
                                          y=sy, confidence=1.0)))
            t += 1

    _full(20.0, ball_at=4)
    for shooter, n_shots in shooter_windows:
        _down(50.0, shooter)
        for _ in range(n_shots):
            _shot(shooter)
            _down(4.0, shooter)
        _down(10.0, shooter)   # ráhagyás: a lövés az ablakon belül marad
        _full(20.0, ball_at=8)
    return Match(_meta(fps), frames)


def test_shorthanded_shooter_roles_names_the_brave_post():
    """Ha öt emberrel mindig ugyanaz a poszt vállal be, emberelőnyben
    az ő oldalán kell a labdabiztonság."""
    from handball.pipeline.rules import (SHR_MIN_SHOTS,
                                         shorthanded_shooter_roles)

    rec = shorthanded_shooter_roles(
        _shr_match([(4, 3), (8, 1)]))["home"]
    assert rec["shots"] >= SHR_MIN_SHOTS, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "labdabiztonság" in rec["verdict"], rec


def test_shorthanded_shooter_roles_silent_with_few_shots():
    """Néhány hátrány-lövésből nincs ítélet."""
    from handball.pipeline.rules import shorthanded_shooter_roles

    rec = shorthanded_shooter_roles(
        _shr_match([(4, 1), (8, 1)]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Passzív-poszt (melyik posztjuknál hal el a felállt támadás) -----------


def _pvr_match(hold_frames_7, hold_frames_9, fps=25.0):
    """Egyetlen hosszú, lövés nélküli felállt hazai támadás: a labda
    felváltva a 7-esnél (beálló) és a 9-esnél (szélső) áll."""
    spos = {7: (34.0, 10.0), 9: (35.0, 3.0)}

    def cast():
        return [_pl(tid, Team.HOME, *xy) for tid, xy in spos.items()]

    frames = []
    t = 0
    plan = [(7, hold_frames_7), (9, hold_frames_9)]
    for (tid, n) in plan:
        sx, sy = spos[tid]
        for _ in range(n):
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=sx + 0.2, y=sy,
                                          confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_passive_holder_roles_names_the_stalling_post():
    """A 40 mp-es, lövés nélküli támadás ideje a beállónál telik →
    passzív jelzésnél őt kell nyomás alá tenni."""
    from handball.pipeline.rules import (PVR_MIN_FRAMES,
                                         passive_holder_roles)

    rec = passive_holder_roles(_pvr_match(800, 200))["home"]
    assert rec["frames"] >= PVR_MIN_FRAMES, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "kényszer-eladás" in rec["verdict"], rec


def test_passive_holder_roles_silent_without_passive_attack():
    """Rövid (35 mp alatti) támadásból nincs passzív szakasz, se
    ítélet."""
    from handball.pipeline.rules import passive_holder_roles

    rec = passive_holder_roles(_pvr_match(400, 100))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Hetesdobó-poszt (melyik posztjuk áll oda a hetesekhez) ----------------


def _stk_match(takers, fps=25.0):
    """Poszt-minta (7: beálló, 9: szélső) + hetesek: a labda megáll a
    7 m-es ponton, majd a `takers` szerinti dobó lövi a kimenetelt."""
    spos = {7: (35.5, 10.0), 9: (35.0, 3.0)}

    def cast():
        return [_pl(tid, Team.HOME, *xy) for tid, xy in spos.items()]

    frames = []
    t = 0
    for _ in range(150):             # poszt-minta: hazai birtoklás elöl
        frames.append(Frame(t=t, players=cast(),
                            ball=Ball(x=35.7, y=10.0, confidence=1.0)))
        t += 1
    for tid in takers:
        for _ in range(25):          # a labda megáll a 7 m-es ponton
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=33.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        sx, sy = spos[tid]
        for _ in range(10):          # a dobó kézbe veszi
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=sx + 0.2, y=sy,
                                          confidence=1.0)))
            t += 1
        x = sx
        while x < 40.5:              # a kimenetel-lövés a kapura
            x += 0.5
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=min(x, 40.5), y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(260):         # szünet a hetes-debounce miatt
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_seven_taker_roles_names_the_taking_post():
    """Négy hetesből hármat a beálló dob → az ő szokásaira készül a
    kapus."""
    from handball.pipeline.rules import (STK_MIN_ATTEMPTS,
                                         seven_taker_roles)

    rec = seven_taker_roles(_stk_match([7, 7, 7, 9]))["home"]
    assert rec["attempts"] >= STK_MIN_ATTEMPTS, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "szokás-irányaira" in rec["verdict"], rec


def test_seven_taker_roles_silent_with_few_sevens():
    """Néhány hetesből nincs ítélet."""
    from handball.pipeline.rules import seven_taker_roles

    rec = seven_taker_roles(_stk_match([7, 9]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Hetespáros-poszt (ki harcolja ki és ki dobja a hetest) ----------------


def _svp_match(pairs, fps=25.0):
    """Poszt-minta (7: beálló, 1: átlövő, 9: szélső) + hetesek: a
    `pairs` elemei (kiharcoló, dobó) — a kiharcoló a jel előtt betör
    a kapu elé, majd a dobó lövi a kimenetelt."""
    spos = {7: (35.5, 10.0), 1: (30.0, 10.0), 9: (35.0, 3.0)}

    def cast(front_tid=None):
        out = []
        for tid, (x, y) in spos.items():
            if tid == front_tid:
                out.append(_pl(tid, Team.HOME, 37.5, y))
            else:
                out.append(_pl(tid, Team.HOME, x, y))
        return out

    frames = []
    t = 0
    for _ in range(150):             # poszt-minta: hazai birtoklás elöl
        frames.append(Frame(t=t, players=cast(),
                            ball=Ball(x=35.7, y=10.0, confidence=1.0)))
        t += 1
    for (earner, taker) in pairs:
        for _ in range(60):          # a kiharcoló betör a kapu elé
            frames.append(Frame(t=t, players=cast(front_tid=earner),
                                ball=Ball(x=36.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(25):          # a labda megáll a 7 m-es ponton
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=33.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        sx, sy = spos[taker]
        for _ in range(10):          # a dobó kézbe veszi
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=sx + 0.2, y=sy,
                                          confidence=1.0)))
            t += 1
        x = sx
        while x < 40.5:              # a kimenetel-lövés a kapura
            x += 0.5
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=min(x, 40.5), y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(260):         # szünet a hetes-debounce miatt
            frames.append(Frame(t=t, players=cast(),
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_seven_pair_roles_names_the_seven_duo():
    """Négy hetesből hármat a beálló harcol ki és az átlövő dob →
    két kiosztható feladat."""
    from handball.pipeline.rules import (SVP_MIN_SEVENS,
                                         seven_pair_roles)

    rec = seven_pair_roles(
        _svp_match([(7, 1), (7, 1), (7, 1), (9, 1)]))["home"]
    assert rec["sevens"] >= SVP_MIN_SEVENS, rec
    assert rec["main_role"] == "beálló→átlövő", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "kéz nélkül" in rec["verdict"], rec


def test_seven_pair_roles_silent_with_few_sevens():
    """Néhány hetesből nincs ítélet."""
    from handball.pipeline.rules import seven_pair_roles

    rec = seven_pair_roles(_svp_match([(7, 1), (9, 1)]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Emberelőnypáros-poszt (melyik tengelyen fut a 6-5 játékuk) -----------


def _ppp_match(pairs, fps=25.0):
    """Mint a _ppr_match, de a lövés ELŐTT az előkészítő is
    megkapja a labdát: a `pairs` elemei (előkészítő, befejező) — az
    1-es irányító (28, 10), a 7-es beálló (33, 10), a 9-es szélső
    (35, 3)."""
    spos = {1: (28.0, 10.0), 7: (33.0, 10.0), 9: (35.0, 3.0)}
    frames = []
    t = 0

    def _cast(away_n, extra=()):
        players = [_pl(100 + k, Team.HOME, 15.0 + k, 4.0 + k)
                   for k in range(6)]
        players += [_pl(200 + k, Team.AWAY, 25.0 + k, 4.0 + k)
                    for k in range(away_n)]
        players += [_pl(tid, Team.HOME, *spos[tid]) for tid in extra]
        return players

    def _rosters(seconds, away_n, extra=(), bx=20.0, by=10.0):
        nonlocal t, frames
        for _ in range(int(seconds * fps)):
            frames.append(Frame(t=t, players=_cast(away_n, extra),
                                ball=Ball(x=bx, y=by,
                                          confidence=1.0)))
            t += 1

    def _feed_and_shot(feeder, shooter, away_n):
        nonlocal t, frames
        fx, fy = spos[feeder]
        sx, sy = spos[shooter]
        both = (feeder, shooter)
        for _ in range(10):          # a labda az előkészítőnél
            frames.append(Frame(t=t, players=_cast(away_n, both),
                                ball=Ball(x=fx + 0.2, y=fy,
                                          confidence=1.0)))
            t += 1
        for _ in range(6):           # átvétel a befejezőnél
            frames.append(Frame(t=t, players=_cast(away_n, both),
                                ball=Ball(x=sx + 0.2, y=sy,
                                          confidence=1.0)))
            t += 1
        for i in range(8):           # a lövés a kapura
            frames.append(Frame(t=t, players=_cast(away_n, both),
                                ball=Ball(x=min(sx + 1.0 + i, 40.0),
                                          y=sy, confidence=1.0)))
            t += 1
        _rosters(2.0, away_n, both)

    _rosters(30.0, 6)
    for feeder, shooter in pairs:
        _rosters(15.0, 5, extra=(feeder, shooter))
        _feed_and_shot(feeder, shooter, 5)
    _rosters(30.0, 6)
    return Match(_meta(fps), frames)


def test_powerplay_pair_roles_names_the_axis():
    """Négy emberelőny-lövésből hármat az irányító készít elő a
    beállónak → öt emberrel ezt a tengelyt kell elvágni."""
    from handball.pipeline.rules import (PWP_MIN_SHOTS,
                                         powerplay_pair_roles)

    rec = powerplay_pair_roles(
        _ppp_match([(1, 7), (1, 7), (1, 7), (1, 9)]))["home"]
    assert rec["shots"] >= PWP_MIN_SHOTS, rec
    assert rec["main_role"] == "irányító→beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "tengelyt vágjátok el" in rec["verdict"], rec


def test_powerplay_pair_roles_silent_with_few_shots():
    """Néhány emberelőny-lövésből nincs ítélet."""
    from handball.pipeline.rules import powerplay_pair_roles

    rec = powerplay_pair_roles(_ppp_match([(1, 7), (1, 9)]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Hetes-kihagyó poszt -----------------------------------------------------

def _svm_match(n_miss, fps=25.0):
    """`n_miss` gól nélküli hazai hetes ugyanattól a dobótól (1-es), plusz
    egy birtoklás-előjáték, hogy a poszt-becslés mintaszáma meglegyen."""
    frames = []
    t = 0
    for _ in range(150):   # előjáték: labdás támadó a 11 m-es körzetben
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 28.0, 10.0)],
                            ball=Ball(x=29.0, y=10.0, confidence=1.0)))
        t += 1
    for _ in range(n_miss):
        for _ in range(30):    # álló labda a 7 m-es ponton
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 32.0, 10.0)],
                                ball=Ball(x=33.0, y=10.0, confidence=1.0)))
            t += 1
        for i in range(7):     # a lövés mellé megy (y=5)
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 32.0, 10.0)],
                                ball=Ball(x=min(34.0 + i, 40.0), y=5.0,
                                          confidence=1.0)))
            t += 1
        for i in range(300):   # 12 mp szünet (hetes-debounce)
            frames.append(Frame(t=t + i, players=[],
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 300
    return Match(_meta(fps), frames)


def test_seven_miss_roles_finds_the_missing_post():
    """Három gól nélküli hetes ugyanattól a dobótól → az ő posztja
    adja a kihagyások 100%-át, ítélettel."""
    from handball.pipeline.rules import seven_miss_roles

    rec = seven_miss_roles(_svm_match(3))["home"]
    assert rec["misses"] == 3
    assert rec["main_role"] is not None
    assert rec["roles"][rec["main_role"]] == 3
    assert rec["share_pct"] == 100.0
    assert rec["verdict"] and "hetes" in rec["verdict"]


def test_seven_miss_roles_needs_enough_misses():
    """Két kihagyás még kevés: az ítélet None, a darabszám viszont látszik."""
    from handball.pipeline.rules import seven_miss_roles

    rec = seven_miss_roles(_svm_match(2))["home"]
    assert rec["misses"] == 2
    assert rec["verdict"] is None and rec["main_role"] is None
    assert seven_miss_roles(_svm_match(2))["away"]["misses"] == 0


# ---- Emberelőny-hiba poszt ---------------------------------------------------

def _ppt_match(losers, fps=25.0, pad_s=0.0):
    """A VENDÉG van emberhátrányban (5 fő); a `losers` elemei adják,
    kinél vész el a labda az emberelőnyben. A 7-es beálló (33, 10), a
    9-es szélső (35, 3) — mindkettő végig a pályán az ablak alatt."""
    spos = {7: (33.0, 10.0), 9: (35.0, 3.0)}
    frames = []
    t = 0

    def _cast(away_n, extra=()):
        players = [_pl(100 + k, Team.HOME, 15.0 + k, 4.0 + k)
                   for k in range(6)]
        players += [_pl(200 + k, Team.AWAY, 25.0 + k, 4.0 + k)
                    for k in range(away_n)]
        players += [_pl(tid, Team.HOME, *spos[tid]) for tid in extra]
        return players

    def _hold(n, away_n, extra, ball):
        nonlocal t, frames
        for _ in range(n):
            frames.append(Frame(t=t, players=_cast(away_n, extra),
                                ball=Ball(x=ball[0], y=ball[1],
                                          confidence=1.0)))
            t += 1

    _hold(int(20.0 * fps), 6, (), (20.0, 9.0))     # teljes létszám
    for loser in losers:                            # az emberelőny
        lx, ly = spos[loser]
        _hold(int(14.0 * fps), 5, (7, 9), (lx + 0.2, ly))
        _hold(int(1.0 * fps), 5, (7, 9), (25.0, 4.0))   # elvesztve
    # A `pad_s` nyújtja az ablakot: kevés eladás mellett is legyen
    # felismert kiállítás-szakasz (PP_MIN_S).
    if pad_s:
        _hold(int(pad_s * fps), 5, (7, 9), (33.2, 10.0))
    _hold(int(20.0 * fps), 6, (), (20.0, 9.0))     # vissza hatra
    return Match(_meta(fps), frames)


def test_powerplay_turnover_roles_names_the_leaking_post():
    """Ha az emberelőnyük rendre ugyanannak a kezén akad el,
    hátrányban rá kell nyomni."""
    from handball.pipeline.rules import (PPT_MIN_TURNOVERS,
                                         powerplay_turnover_roles)

    rec = powerplay_turnover_roles(_ppt_match([7, 7, 7, 9]))["home"]
    assert rec["turnovers"] >= PPT_MIN_TURNOVERS, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "dupla büntetés" in rec["verdict"], rec


def test_powerplay_turnover_roles_silent_with_few_turnovers():
    """Két emberelőny-eladásból még nincs ítélet."""
    from handball.pipeline.rules import powerplay_turnover_roles

    rec = powerplay_turnover_roles(_ppt_match([7, 9]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec
    assert powerplay_turnover_roles(
        _ppt_match([7, 9]))["away"]["turnovers"] == 0


# ---- Emberhátrány-hiba poszt -------------------------------------------------

def _sht_match(losers, fps=25.0):
    """A HAZAI van emberhátrányban (öt mezőnyjátékos); a `losers`
    elemei adják, kinél vész el a labda. A 7-es beálló (33, 10), a
    9-es szélső (35, 3) — ők ketten a hazai ötből."""
    spos = {7: (33.0, 10.0), 9: (35.0, 3.0)}
    frames = []
    t = 0

    def _cast(home_extra=True):
        players = [_pl(100 + k, Team.HOME, 15.0 + k, 4.0 + k)
                   for k in range(3 if home_extra else 4)]
        if home_extra:
            players += [_pl(tid, Team.HOME, *xy)
                        for tid, xy in spos.items()]
        players += [_pl(200 + k, Team.AWAY, 25.0 + k, 4.0 + k)
                    for k in range(6)]
        return players

    def _hold(n, ball, home_extra=True):
        nonlocal t, frames
        for _ in range(n):
            frames.append(Frame(t=t, players=_cast(home_extra),
                                ball=Ball(x=ball[0], y=ball[1],
                                          confidence=1.0)))
            t += 1

    # Teljes létszám: a hazai hatodik ember is a pályán (nincs ablak).
    for _ in range(int(20.0 * fps)):
        players = [_pl(100 + k, Team.HOME, 15.0 + k, 4.0 + k)
                   for k in range(4)]
        players += [_pl(tid, Team.HOME, *xy) for tid, xy in spos.items()]
        players += [_pl(200 + k, Team.AWAY, 25.0 + k, 4.0 + k)
                    for k in range(6)]
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=20.0, y=9.0, confidence=1.0)))
        t += 1
    for loser in losers:                 # az emberhátrány (5 a 6 ellen)
        lx, ly = spos[loser]
        _hold(int(14.0 * fps), (lx + 0.2, ly))
        _hold(int(1.0 * fps), (25.0, 4.0))      # elvesztve
    _hold(int(20.0 * fps), (20.0, 9.0), home_extra=False)
    return Match(_meta(fps), frames)


def test_shorthanded_turnover_roles_names_the_leaking_post():
    """Ha hátrányban rendre ugyanannak a kezén vész el a labda, a
    hat az öt ellen az ő fogadására kell menni."""
    from handball.pipeline.rules import (SHT_MIN_TURNOVERS,
                                         shorthanded_turnover_roles)

    rec = shorthanded_turnover_roles(_sht_match([7, 7, 7, 9]))["home"]
    assert rec["turnovers"] >= SHT_MIN_TURNOVERS, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "üres kapura" in rec["verdict"], rec


def test_shorthanded_turnover_roles_silent_with_few_turnovers():
    """Két hátrány-eladásból még nincs ítélet."""
    from handball.pipeline.rules import shorthanded_turnover_roles

    rec = shorthanded_turnover_roles(_sht_match([7, 9]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Hetes-kihagyók (ki hibázza el a hetest) ---------------------------------

def test_seven_miss_players_names_the_shooter():
    """Két gól nélküli hetes ugyanattól a dobótól → ő a listán, és a
    kapus mehet ellene a saját megérzésére."""
    from handball.pipeline.rules import (SVMP_MIN_MISSES,
                                         seven_miss_players)

    rec = seven_miss_players(_svm_match(3))["home"]
    assert rec["misses"] == 3, rec
    assert rec["top"] is not None, rec
    assert rec["top"]["player_id"] == 1, rec
    assert rec["top"]["misses"] >= SVMP_MIN_MISSES, rec


def test_seven_miss_players_silent_after_one_miss():
    """Egyetlen kihagyásból nincs kiemelt név (a hetes ritka esemény,
    de egy eset még nem minta)."""
    from handball.pipeline.rules import seven_miss_players

    rec = seven_miss_players(_svm_match(1))["home"]
    assert rec["misses"] == 1 and rec["top"] is None, rec
    assert seven_miss_players(_svm_match(1))["away"]["players"] == []


# ---- Kétperc-páros (kiharcoló → emberelőny-befejező) -------------------------

def _schain_match(chains, fps=25.0):
    """`chains` elemei (kiharcoló, befejező) hazai id-k. A hazai
    szerzi az emberelőnyt: az ablak előtt a kiharcoló nyomul a
    kapuhoz, az ablakban a befejező lő. A 7-es beálló (34, 10), a
    9-es szélső (35, 3), az 5-ös irányító (29, 10)."""
    spos = {5: (29.0, 10.0), 7: (34.0, 10.0), 9: (35.0, 3.0)}
    frames = []
    t = 0

    def _cast(away_n, deep=None):
        players = []
        for tid, (x, y) in spos.items():
            # A kiharcoló az ablak előtt mélyebbre nyomul.
            if deep == tid:
                players.append(_pl(tid, Team.HOME, 38.0, y))
            else:
                players.append(_pl(tid, Team.HOME, x, y))
        # Három hátsó hazai játékos: velük lesz teljes (hatos) a
        # hazai létszám, de a poszt-becslésbe nem esnek bele.
        players += [_pl(100 + k, Team.HOME, 15.0 + k, 16.0 + k)
                    for k in range(3)]
        players += [_pl(200 + k, Team.AWAY, 25.0 + k, 4.0 + k)
                    for k in range(away_n)]
        return players

    def _hold(n, away_n, ball, deep=None):
        nonlocal t, frames
        for _ in range(n):
            frames.append(Frame(t=t, players=_cast(away_n, deep),
                                ball=Ball(x=ball[0], y=ball[1],
                                          confidence=1.0)))
            t += 1

    _hold(int(20.0 * fps), 6, (29.2, 10.0))     # poszt-minta
    for earner, shooter in chains:
        # A kiállítás előtti szakasz: a kiharcoló nyomul a kapuhoz.
        _hold(int(12.0 * fps), 6, (29.2, 10.0), deep=earner)
        # Az emberelőny-ablak (a vendég öt emberrel) — bőven a
        # PP_MIN_S fölött, hogy az ablak-határok se vágják meg.
        _hold(int(35.0 * fps), 5, (29.2, 10.0))
        sx, sy = spos[shooter]
        for _ in range(5):                       # a labda a lövőnél
            frames.append(Frame(t=t, players=_cast(5),
                                ball=Ball(x=sx + 0.2, y=sy,
                                          confidence=1.0)))
            t += 1
        for i in range(8):                       # a lövés
            frames.append(Frame(t=t, players=_cast(5),
                                ball=Ball(x=min(sx + 1.0 + i, 40.4),
                                          y=sy, confidence=1.0)))
            t += 1
        _hold(int(45.0 * fps), 5, (29.2, 10.0))
        _hold(int(30.0 * fps), 6, (29.2, 10.0))  # vissza hatra
    return Match(_meta(fps), frames)


def test_suspension_chain_roles_names_the_two_minute_chain():
    """Ha a kétperceket ugyanaz a lánc futja (kiharcoló → befejező),
    mindkét posztra jut feladat."""
    from handball.pipeline.rules import (SCH_MIN_PAIRS,
                                         suspension_chain_roles)

    rec = suspension_chain_roles(
        _schain_match([(9, 7), (9, 7), (9, 7), (5, 7)]))["home"]
    assert rec["chains"] >= SCH_MIN_PAIRS, rec
    assert rec["main_role"] == "szélső→beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 55.0, rec
    assert rec["verdict"] and "kiharcolójuk" in rec["verdict"], rec


def test_suspension_chain_roles_silent_with_few_chains():
    """Két láncból még nincs ítélet — a kiállítás ritka esemény."""
    from handball.pipeline.rules import suspension_chain_roles

    rec = suspension_chain_roles(_schain_match([(9, 7), (5, 7)]))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Kétperc ára (mennyi gólba kerül egy kiállításuk) ------------------------

def _sct_match(goals_per_window, fps=25.0):
    """A VENDÉG van emberhátrányban; a `goals_per_window` elemei adják,
    hány hazai gól esik az adott kiállítás-ablakban."""
    frames = []
    t = 0

    def _cast(away_n):
        players = [_pl(100 + k, Team.HOME, 15.0 + k, 4.0 + k)
                   for k in range(6)]
        players += [_pl(200 + k, Team.AWAY, 25.0 + k, 4.0 + k)
                    for k in range(away_n)]
        return players

    def _hold(n, away_n, ball):
        nonlocal t, frames
        for _ in range(n):
            frames.append(Frame(t=t, players=_cast(away_n),
                                ball=Ball(x=ball[0], y=ball[1],
                                          confidence=1.0)))
            t += 1

    def _home_goal(away_n):
        nonlocal t, frames
        for i in range(10):
            players = _cast(away_n)
            players.append(_pl(1, Team.HOME, 33.0, 10.0))
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=min(34.0 + i, 40.4),
                                          y=10.0, confidence=1.0)))
            t += 1
        _hold(int(3.0 * fps), away_n, (20.0, 9.0))

    _hold(int(20.0 * fps), 6, (20.0, 9.0))
    for n_goals in goals_per_window:
        _hold(int(20.0 * fps), 5, (20.0, 9.0))
        for _ in range(n_goals):
            _home_goal(5)
        _hold(int(40.0 * fps), 5, (20.0, 9.0))
        _hold(int(30.0 * fps), 6, (20.0, 9.0))
    return Match(_meta(fps), frames)


def test_suspension_cost_prices_the_expensive_two_minutes():
    """Ha egy kétpercük átlag több mint egy gólba kerül, a
    kiharcolás pont-termelés."""
    from handball.pipeline.rules import (SCT_MIN_WINDOWS,
                                         suspension_cost)

    rec = suspension_cost(_sct_match([2, 2, 1]))["away"]
    assert rec["windows"] >= SCT_MIN_WINDOWS, rec
    assert rec["conceded"] == 5, rec
    assert rec["per_susp"] and rec["per_susp"] >= 1.2, rec
    assert rec["verdict"] and "pont-termelés" in rec["verdict"], rec


def test_suspension_cost_flags_the_cheap_two_minutes():
    """Ha olcsón megússzák a hátrányt, nem szabad a kiállításra
    játszani."""
    from handball.pipeline.rules import suspension_cost

    rec = suspension_cost(_sct_match([0, 0, 1]))["away"]
    assert rec["per_susp"] is not None and rec["per_susp"] <= 0.5, rec
    assert rec["verdict"] and "olcsón megússzák" in rec["verdict"], rec


def test_suspension_cost_silent_with_few_windows():
    """Két kiállításból még nincs ítélet."""
    from handball.pipeline.rules import suspension_cost

    rec = suspension_cost(_sct_match([1, 1]))["away"]
    assert rec["windows"] == 2 and rec["verdict"] is None, rec
    assert rec["per_susp"] is None, rec


# ---- Emberelőny-hibázók (ki adja el a labdát a két perc alatt) --------------

def test_powerplay_turnover_players_names_the_loser():
    """Ha az emberelőnyben rendre ugyanaz veszíti el a labdát,
    hátrányban rá kell nyomni."""
    from handball.pipeline.rules import (PPTP_MIN_TURNOVERS,
                                         powerplay_turnover_players)

    rec = powerplay_turnover_players(_ppt_match([7, 7, 7, 9]))["home"]
    assert rec["turnovers"] == 4, rec
    assert rec["top"] is not None and rec["top"]["player_id"] == 7, rec
    assert rec["top"]["turnovers"] >= PPTP_MIN_TURNOVERS, rec


def test_powerplay_turnover_players_silent_after_one():
    """Egyetlen emberelőny-eladás még nem minta."""
    from handball.pipeline.rules import powerplay_turnover_players

    rec = powerplay_turnover_players(
        _ppt_match([7], pad_s=60.0))["home"]
    assert rec["turnovers"] == 1 and rec["top"] is None, rec


# ---- Emberhátrány-hibázók (öt emberrel ki veszíti el a labdát) --------------

def test_shorthanded_turnover_players_names_the_loser():
    """Ha hátrányban rendre ugyanaz veszíti el a labdát, a hat az öt
    ellen rá kell menni."""
    from handball.pipeline.rules import (SHTP_MIN_TURNOVERS,
                                         shorthanded_turnover_players)

    rec = shorthanded_turnover_players(_sht_match([7, 7, 7, 9]))["home"]
    assert rec["turnovers"] == 4, rec
    assert rec["top"] is not None and rec["top"]["player_id"] == 7, rec
    assert rec["top"]["turnovers"] >= SHTP_MIN_TURNOVERS, rec


def test_shorthanded_turnover_players_silent_after_one():
    """Egyetlen hátrány-eladás még nem minta."""
    from handball.pipeline.rules import shorthanded_turnover_players

    rec = shorthanded_turnover_players(_sht_match([7, 9]))["home"]
    assert rec["top"] is None, rec


# ---- Hetesdobók (ki áll oda a hétméteresekhez) -------------------------------

def test_seven_taker_players_names_the_taker():
    """Három hetes ugyanattól a dobótól → rá készülhet a kapus."""
    from handball.pipeline.rules import (STP_MIN_SEVENS,
                                         seven_taker_players)

    rec = seven_taker_players(_svm_match(3))["home"]
    assert rec["sevens"] == 3, rec
    assert rec["top"] is not None and rec["top"]["player_id"] == 1, rec
    assert rec["top"]["sevens"] >= STP_MIN_SEVENS, rec
    # A _svm_match hetesei mind gól nélkül zárulnak.
    assert rec["top"]["goals"] == 0, rec


def test_seven_taker_players_silent_after_one():
    """Egyetlen hetesből még nincs kiemelt dobó."""
    from handball.pipeline.rules import seven_taker_players

    rec = seven_taker_players(_svm_match(1))["home"]
    assert rec["sevens"] == 1 and rec["top"] is None, rec
