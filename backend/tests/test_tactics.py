"""
Tesztek a taktikai rétegre (tactics.py): birtoklás, fázis, védekezési forma.

Kézzel összerakott frame-ekkel, videó nélkül. A pálya 40x20 m; a HAZAI a +x (x=40)
kapu felé támad, saját kapuja x=0. (Alapértelmezett TacticsConfig.)

Futtatás:
    python tests/test_tactics.py
"""

from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, Ball, Team, PositionSource,
)
from handball.pipeline.tactics import (
    TacticsConfig, possession_team, classify_phase, Phase,
    phase_percentages, detect_formation,
    count_possession_segments, compute_tempo, team_style_profile,
    slow_attacks,
)


def _pl(track_id, team, x, y):
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0)


def test_possession_nearest_within_radius():
    """A labdát a hozzá legközelebbi (sugáron belüli) játékos csapata birtokolja."""
    cfg = TacticsConfig()
    frame = Frame(t=0, players=[
        _pl(1, Team.HOME, 30.0, 10.0),   # 1 m-re a labdától
        _pl(11, Team.AWAY, 25.0, 10.0),  # távolabb
    ], ball=Ball(x=31.0, y=10.0, confidence=1.0))
    assert possession_team(frame, cfg) == Team.HOME


def test_possession_none_when_ball_far():
    """Ha a legközelebbi játékos is messze van, nincs birtokos (szabad labda)."""
    cfg = TacticsConfig(possession_radius_m=3.0)
    frame = Frame(t=0, players=[_pl(1, Team.HOME, 10.0, 10.0)],
                  ball=Ball(x=30.0, y=10.0, confidence=1.0))
    assert possession_team(frame, cfg) is None


def test_phase_home_attack():
    """Hazai birtoklás a hazai támadó térfelén (x>20) → HAZAI_TÁMADÁS."""
    cfg = TacticsConfig()
    frame = Frame(t=0, players=[_pl(1, Team.HOME, 30.0, 10.0)],
                  ball=Ball(x=30.0, y=10.0, confidence=1.0))
    assert classify_phase(frame, cfg) == Phase.HOME_ATTACK


def test_phase_transition_in_own_half():
    """Hazai birtoklás a SAJÁT térfelén (x<20) → ÁTMENET (felépítés)."""
    cfg = TacticsConfig()
    frame = Frame(t=0, players=[_pl(1, Team.HOME, 10.0, 10.0)],
                  ball=Ball(x=10.0, y=10.0, confidence=1.0))
    assert classify_phase(frame, cfg) == Phase.TRANSITION


def test_phase_away_attack():
    """Vendég birtoklás a vendég támadó térfelén (x<20) → VENDÉG_TÁMADÁS."""
    cfg = TacticsConfig()
    frame = Frame(t=0, players=[_pl(11, Team.AWAY, 8.0, 10.0)],
                  ball=Ball(x=8.0, y=10.0, confidence=1.0))
    assert classify_phase(frame, cfg) == Phase.AWAY_ATTACK


def test_phase_unknown_without_ball():
    """Labda nélkül a fázis UNKNOWN."""
    cfg = TacticsConfig()
    frame = Frame(t=0, players=[_pl(1, Team.HOME, 30.0, 10.0)], ball=None)
    assert classify_phase(frame, cfg) == Phase.UNKNOWN


def test_phase_percentages_sum_100():
    """A fázis-megoszlás összege 100% (van labdás frame)."""
    cfg = TacticsConfig()
    frames = [
        Frame(t=0, players=[_pl(1, Team.HOME, 30.0, 10.0)], ball=Ball(x=30, y=10, confidence=1)),
        Frame(t=1, players=[_pl(11, Team.AWAY, 8.0, 10.0)], ball=Ball(x=8, y=10, confidence=1)),
    ]
    pct = phase_percentages(Match(MatchMeta(match_id="t", home_team="A", away_team="B", fps=25), frames))
    assert abs(sum(pct.values()) - 100.0) < 1e-9
    assert pct[Phase.HOME_ATTACK.value] == 50.0
    assert pct[Phase.AWAY_ATTACK.value] == 50.0


def _defense(positions):
    """Védekező (AWAY) frame: a megadott (x,y) helyeken álló védőkből.
    AWAY saját kapuja x=40, tehát a kaputól mért mélység = 40 - x."""
    players = [_pl(11 + i, Team.AWAY, x, y) for i, (x, y) in enumerate(positions)]
    return Frame(t=0, players=players, ball=None)


def test_formation_6_0():
    """Hat védő a 6 m-es vonalon (x≈34, mélység≈6) → 6-0."""
    frame = _defense([(34.0, y) for y in (3, 6, 9, 11, 14, 17)])
    res = detect_formation(frame, Team.AWAY)
    assert res.label == "6-0"
    assert res.back == 6 and res.mid == 0 and res.high == 0


def test_formation_5_1():
    """Öt hátul + egy előretolt (x≈30.5, mélység≈9.5) → 5-1."""
    frame = _defense([(34.0, 3), (34.0, 6), (34.0, 9), (34.0, 11), (34.0, 14), (30.5, 10)])
    res = detect_formation(frame, Team.AWAY)
    assert res.label == "5-1"
    assert res.back == 5 and (res.mid + res.high) == 1


def test_formation_3_2_1():
    """Három lépcső: 3 hátul, 2 közép, 1 előretolt → 3-2-1."""
    frame = _defense([
        (34.0, 6), (34.0, 10), (34.0, 14),   # hátsó (mélység 6)
        (30.5, 8), (30.5, 12),               # közép (mélység 9.5)
        (27.0, 10),                          # előretolt (mélység 13)
    ])
    res = detect_formation(frame, Team.AWAY)
    assert res.label == "3-2-1"
    assert (res.back, res.mid, res.high) == (3, 2, 1)


def test_formation_excludes_goalkeeper():
    """A kaput nagyon közelről őrző játékost kapusnak vesszük (kihagyjuk)."""
    # 6 mezőnyvédő a 6 m-en + 1 kapus a kapunál (x≈39.5, mélység 0.5).
    frame = _defense([(34.0, y) for y in (3, 6, 9, 11, 14, 17)] + [(39.5, 10)])
    res = detect_formation(frame, Team.AWAY)
    assert res.defenders == 6   # a kapust nem számoltuk
    assert res.label == "6-0"


def _meta(fps=25.0):
    return MatchMeta(match_id="t", home_team="A", away_team="B", fps=fps)


def test_count_possession_segments():
    """Birtoklás A,A,B,B,A → 3 külön szakasz (csapatváltáskor új)."""
    seq = [Team.HOME, Team.HOME, Team.AWAY, Team.AWAY, Team.HOME]
    frames = []
    for i, team in enumerate(seq):
        # a labdát a birtokló csapat játékosa mellé tesszük
        x = 30.0 if team == Team.HOME else 8.0
        frames.append(Frame(t=i, players=[_pl(1, team, x, 10.0)],
                            ball=Ball(x=x, y=10.0, confidence=1.0)))
    assert count_possession_segments(Match(_meta(), frames)) == 3


def test_avg_ball_speed():
    """A labda 1 m/frame, 25 fps → 25 m/s átlagsebesség."""
    frames = [
        Frame(t=i, players=[_pl(1, Team.HOME, 30.0, 10.0)],
              ball=Ball(x=float(i), y=0.0, confidence=1.0))
        for i in range(3)  # x = 0,1,2 → 2 m elmozdulás 2 lépésben
    ]
    tempo = compute_tempo(Match(_meta(fps=25.0), frames))
    assert abs(tempo.avg_ball_speed_ms - 25.0) < 1e-9


def test_avg_attack_duration():
    """Három egymást követő hazai-támadás frame → 3/fps mp átlagos hossz."""
    frames = [
        Frame(t=i, players=[_pl(1, Team.HOME, 30.0, 10.0)],
              ball=Ball(x=30.0, y=10.0, confidence=1.0))
        for i in range(3)
    ]
    tempo = compute_tempo(Match(_meta(fps=25.0), frames))
    assert abs(tempo.avg_attack_duration_s - 3.0 / 25.0) < 1e-9


def test_team_style_profile_structure():
    """A stílusprofil tartalmazza a fázis-, forma- és tempó-részt."""
    frames = [Frame(t=0, players=[_pl(1, Team.HOME, 30.0, 10.0)],
                    ball=Ball(x=30.0, y=10.0, confidence=1.0))]
    prof = team_style_profile(Match(_meta(), frames))
    assert "phase_percentages" in prof
    assert "defense_formations" in prof
    assert "tempo" in prof and "possessions" in prof["tempo"]


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    print(f"\n{'OK' if failures == 0 else failures} hibás teszt")
    raise SystemExit(1 if failures else 0)


def test_slow_attacks_flags_long_possession():
    """40 mp-es hazai támadó-szakasz → elhúzódó; a 10 mp-es nem az."""
    meta = MatchMeta(match_id="sa", home_team="H", away_team="A", fps=25.0)
    frames = []
    t = 0
    # 40 mp hazai támadás a támadó térfélen (x=30), birtoklással.
    for _ in range(int(40 * 25)):
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 30.0, 10.0)],
                            ball=Ball(x=30.0, y=10.0, confidence=1.0)))
        t += 1
    # Megszakítás (szabad labda a felezőnél, senki a közelben) — új szakasz.
    for _ in range(10):
        frames.append(Frame(t=t, players=[], ball=Ball(x=20.0, y=10.0,
                                                       confidence=1.0)))
        t += 1
    # 10 mp-es második hazai támadás.
    for _ in range(int(10 * 25)):
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 30.0, 10.0)],
                            ball=Ball(x=30.0, y=10.0, confidence=1.0)))
        t += 1
    sa = slow_attacks(Match(meta, frames))
    assert sa["home"]["attacks"] == 2
    assert sa["home"]["slow"] == 1
    assert sa["home"]["slow_pct"] == 50.0
    assert sa["home"]["longest_s"] >= 39.0
    assert sa["away"]["attacks"] == 0
