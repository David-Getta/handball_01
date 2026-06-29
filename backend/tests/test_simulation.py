"""
Tesztek a meccs-szimulátorra (handball.sim).

Videó nélkül igazoljuk, hogy a szimulátor valósághű, reprodukálható Tracking-et
ad, és hogy a pásztázó-kamerás változat tényleg becsli a látómezőből kieső
játékosokat (a valódi [F] becslővel).

Futtatás:
    python tests/test_simulation.py
"""

from __future__ import annotations

# A backend/ mappát a kereső-útvonalra tesszük, hogy a teszt bárhonnan fusson.
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import Team, PositionSource
from handball.sim import simulate_ground_truth, simulate_with_panning_camera
from handball.pipeline.calibration import COURT_LENGTH_M, COURT_WIDTH_M


def test_ground_truth_has_full_teams_and_ball():
    """A földi igazságban minden frame-en 14 játékos (7+7) és labda van."""
    match = simulate_ground_truth(duration_s=2.0, fps=25.0, seed=1)
    assert len(match.frames) == 50
    for fr in match.frames:
        assert len(fr.players) == 14
        home = [p for p in fr.players if p.team == Team.HOME]
        away = [p for p in fr.players if p.team == Team.AWAY]
        assert len(home) == 7 and len(away) == 7
        assert fr.ball is not None
        # Minden játékos a pályán belül, és mind MÉRT (kamera-korlát nélkül).
        for p in fr.players:
            assert 0.0 <= p.x <= COURT_LENGTH_M
            assert 0.0 <= p.y <= COURT_WIDTH_M
            assert p.source == PositionSource.MEASURED


def test_ground_truth_is_reproducible():
    """Ugyanaz a seed ugyanazt a meccset adja (determinizmus)."""
    a = simulate_ground_truth(duration_s=1.0, seed=42)
    b = simulate_ground_truth(duration_s=1.0, seed=42)
    assert a.to_json() == b.to_json()


def test_panning_camera_produces_estimates():
    """Szűk látómezővel a kieső játékosokat BECSÜLI a rendszer.

    Ellenőrizzük, hogy keletkezik becsült pozíció, és hogy a látott (mért)
    játékosok tényleg a látómezőn belül vannak.
    """
    ground = simulate_ground_truth(duration_s=4.0, fps=25.0, seed=0)
    panned = simulate_with_panning_camera(ground, fov_width_m=12.0)

    total_estimated = 0
    for gt, fr in zip(ground.frames, panned.frames):
        cam_x = gt.ball.x
        for p in fr.players:
            if p.source == PositionSource.ESTIMATED:
                total_estimated += 1
            else:
                # A mért játékos a látómezőn belül van (|x - kamera| <= fél FOV).
                assert abs(p.x - cam_x) <= 6.0 + 1e-9
    assert total_estimated > 0, "szűk látómezőnél kell lennie becsült játékosnak"


def test_panning_never_exceeds_roster():
    """Csapatonként a (látott + becsült) játékosszám sosem több a pályán lévőnél (7)."""
    ground = simulate_ground_truth(duration_s=3.0, fps=25.0, seed=3)
    panned = simulate_with_panning_camera(ground, fov_width_m=14.0)
    for fr in panned.frames:
        for team in (Team.HOME, Team.AWAY):
            count = sum(1 for p in fr.players if p.team == team)
            assert count <= 7, f"{team} létszám {count} > 7"


def test_estimated_positions_within_court():
    """A becsült pozíciók is a pályán belül maradnak (a becslő határvágása miatt)."""
    ground = simulate_ground_truth(duration_s=3.0, fps=25.0, seed=7)
    panned = simulate_with_panning_camera(ground, fov_width_m=12.0)
    for fr in panned.frames:
        for p in fr.players:
            assert -1e-9 <= p.x <= COURT_LENGTH_M + 1e-9
            assert -1e-9 <= p.y <= COURT_WIDTH_M + 1e-9


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
