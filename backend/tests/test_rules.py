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
