"""
Tesztek a minőség-jelentésre (quality.py).

Futtatás:
    python tests/test_quality.py
"""

from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, Ball, PositionSource, Team,
)
from handball.pipeline.quality import compute_quality_report


def _meta(fps=25.0):
    return MatchMeta(match_id="q", home_team="A", away_team="B", fps=fps,
                     frame_width=1920, frame_height=1080)


def _pl(i, source=PositionSource.MEASURED):
    # Kiegyensúlyozott felállás: a páros indexek hazaiak, a páratlanok
    # vendégek — mint egy valódi meccsen (az arány-ellenőrzés miatt).
    team = Team.HOME if i % 2 == 0 else Team.AWAY
    return PlayerPosition(track_id=i, team=team, x=20.0, y=10.0,
                          source=source, confidence=1.0)


def test_full_coverage_high_score():
    """Teljes lefedettség (14 mért játékos + labda minden kockán): magas pontszám."""
    frames = [Frame(t=t, players=[_pl(i) for i in range(14)],
                    ball=Ball(x=20.0, y=10.0, confidence=1.0)) for t in range(20)]
    r = compute_quality_report(Match(_meta(), frames))
    assert r["score"] >= 90
    assert r["warnings"] == []
    assert r["ball_coverage_pct"] == 100.0
    assert r["avg_measured_players"] == 14.0


def test_no_ball_warning_and_lower_score():
    """Labda nélkül: figyelmeztetés + alacsonyabb pontszám."""
    frames = [Frame(t=t, players=[_pl(i) for i in range(14)], ball=None)
              for t in range(20)]
    r = compute_quality_report(Match(_meta(), frames))
    assert r["ball_coverage_pct"] == 0.0
    assert any("labda" in w.lower() for w in r["warnings"])
    assert r["score"] <= 65


def test_few_players_warning():
    """Kevés látott játékos: kalibrációra utaló figyelmeztetés."""
    frames = [Frame(t=t, players=[_pl(1), _pl(2)],
                    ball=Ball(x=20.0, y=10.0, confidence=1.0)) for t in range(10)]
    r = compute_quality_report(Match(_meta(), frames))
    assert any("kalibráció" in w.lower() for w in r["warnings"])


def test_estimated_ratio_counted():
    """A becsült pozíciók aránya megjelenik, és sok becsültnél figyelmeztet."""
    players = [_pl(i) for i in range(6)] + \
              [_pl(10 + i, PositionSource.ESTIMATED) for i in range(8)]
    frames = [Frame(t=t, players=list(players),
                    ball=Ball(x=20.0, y=10.0, confidence=1.0)) for t in range(10)]
    r = compute_quality_report(Match(_meta(), frames))
    assert abs(r["estimated_ratio_pct"] - 100.0 * 8 / 14) < 0.5
    assert any("becsült" in w.lower() for w in r["warnings"])


def test_longest_ball_gap_seconds():
    """A leghosszabb labda-hézag másodpercben, fps-sel átváltva."""
    frames = []
    for t in range(50):
        ball = None if 10 <= t < 40 else Ball(x=20.0, y=10.0, confidence=1.0)
        frames.append(Frame(t=t, players=[_pl(i) for i in range(14)], ball=ball))
    r = compute_quality_report(Match(_meta(fps=5.0), frames))
    assert abs(r["longest_ball_gap_s"] - 6.0) < 1e-9  # 30 kocka / 5 fps
    assert any("kiesés" in w.lower() for w in r["warnings"])


def test_empty_match():
    """Üres meccs: 0 pont + magyarázó figyelmeztetés (nem hibázik)."""
    r = compute_quality_report(Match(_meta(), []))
    assert r["score"] == 0 and r["frames"] == 0
    assert r["warnings"]


def test_goalkeeper_warning_on_long_match_without_roles():
    """2+ perces felvételen kapus-jelölés nélkül figyelmeztetés jár."""
    frames = [Frame(t=t, players=[_pl(i) for i in range(14)],
                    ball=Ball(x=20.0, y=10.0, confidence=1.0))
              for t in range(int(150 * 25))]
    r = compute_quality_report(Match(_meta(), frames))
    assert r["goalkeepers"] == {"home": False, "away": False}
    assert any("kapust" in w for w in r["warnings"])


def test_goalkeeper_fields_true_when_marked():
    """Megjelölt kapusokkal nincs kapus-figyelmeztetés."""
    def gk(i, team):
        return PlayerPosition(track_id=i, team=team, x=1.5, y=10.0,
                              source=PositionSource.MEASURED,
                              confidence=1.0, role="kapus")
    frames = [Frame(t=t, players=[_pl(i) for i in range(12)]
                    + [gk(50, Team.HOME), gk(51, Team.AWAY)],
                    ball=Ball(x=20.0, y=10.0, confidence=1.0))
              for t in range(int(150 * 25))]
    r = compute_quality_report(Match(_meta(), frames))
    assert r["goalkeepers"] == {"home": True, "away": True}
    assert not any("kapust" in w for w in r["warnings"])


def test_seven_meter_spam_warning():
    """Percenként ~2 "hétméteres" (álló labda a 7 m-es ponton) gyanús."""
    frames = []
    for t in range(int(120 * 25)):
        # A labda 33/10-en áll (a +x kapu 7 m-es pontja), 25 mp-enként
        # 5 mp-re "elmozdul", hogy sok külön esemény szülessen.
        moving = (t // 25) % 6 == 5
        bx = 20.0 if moving else 33.0
        frames.append(Frame(t=t, players=[_pl(i) for i in range(14)],
                            ball=Ball(x=bx, y=10.0, confidence=1.0)))
    r = compute_quality_report(Match(_meta(), frames))
    assert r["seven_meters"] >= 2
    assert any("hétméteres" in w for w in r["warnings"])


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


def test_tracking_health_metrics_present():
    """Az új követés-egészség mutatók jelen vannak és értelmesek."""
    from handball.sim.match_simulator import simulate_ground_truth
    m = simulate_ground_truth(duration_s=10, fps=25.0, seed=2)
    q = compute_quality_report(m)
    assert q["track_count"] == 14  # a szimulátor 14 stabil játékosa
    assert abs(q["fragmentation"] - 1.0) < 0.01  # nincs szakadás
    assert q["avg_track_length_s"] > 5.0
    assert 35.0 <= q["home_share_pct"] <= 65.0
    assert q["jersey_coverage_pct"] == 100.0  # a szimulátor mezszámot is ad
    # Kiegyensúlyozott, ép követésnél nincs töredezettség/arány-figyelmeztetés.
    assert not any("töredezett" in w for w in q["warnings"])
    assert not any("egyoldalú" in w for w in q["warnings"])


def test_fragmentation_warning_on_many_short_tracks():
    """Sok rövid track (szakadozó követés) → töredezettség-figyelmeztetés."""
    frames = []
    for t in range(100):
        # Minden 2 kockán új track-azonosító — extrém töredezettség.
        frames.append(Frame(t=t, players=[
            PlayerPosition(track_id=1000 + t // 2, team=Team.HOME,
                           x=10.0 + (t % 5), y=5.0),
        ]))
    m = Match(meta=_meta(), frames=frames)
    q = compute_quality_report(m)
    assert q["fragmentation"] > 3.0
    assert any("töredezett" in w for w in q["warnings"])


def test_one_sided_team_share_warning():
    """Ha szinte minden mért pozíció egy csapaté → arány-figyelmeztetés."""
    frames = [Frame(t=t, players=[
        PlayerPosition(track_id=1, team=Team.HOME, x=10.0, y=5.0),
        PlayerPosition(track_id=2, team=Team.HOME, x=12.0, y=6.0),
        PlayerPosition(track_id=3, team=Team.HOME, x=14.0, y=7.0),
    ]) for t in range(50)]
    m = Match(meta=_meta(), frames=frames)
    q = compute_quality_report(m)
    assert q["home_share_pct"] > 90.0
    assert any("egyoldalú" in w for w in q["warnings"])


def test_analysis_confidence_rows():
    """A réteg-megbízhatóság minden sora teljes; rövid, gól nélküli
    klipnél az xG/momentum/hajrá nem elérhető, magyar indoklással."""
    from handball.pipeline.quality import analysis_confidence
    from handball.sim.match_simulator import simulate_ground_truth
    rows = analysis_confidence(simulate_ground_truth(duration_s=20,
                                                     fps=25.0, seed=2))
    assert {r["layer"] for r in rows} >= {"xg", "goalkeeper", "halftime",
                                          "clutch", "momentum",
                                          "conditioning"}
    for r in rows:
        assert r["label"] and r["reason"]
        assert isinstance(r["available"], bool)
    clutch = next(r for r in rows if r["layer"] == "clutch")
    assert clutch["available"] is False
    assert "rövidebb" in clutch["reason"]


def test_simulated_halftime_break_is_detected():
    """A szimulátor félidei szünetével a szünet-felismerés működik, és a
    félidő-rétegek elérhetővé válnak a réteg-megbízhatóságban."""
    from handball.pipeline.halftime import detect_halftime
    from handball.pipeline.quality import analysis_confidence
    from handball.sim.match_simulator import simulate_ground_truth
    m = simulate_ground_truth(duration_s=240, fps=25.0, seed=3,
                              halftime_break_s=90.0)
    half_t = detect_halftime(m)
    assert half_t is not None
    # A szünet a játékidő közepe táján van.
    assert 0.3 * len(m.frames) < half_t < 0.7 * len(m.frames)
    rows = analysis_confidence(m)
    ht = next(r for r in rows if r["layer"] == "halftime")
    assert ht["available"] is True
