"""
Tesztek a demó forgatókönyv-epizódokra (append_demo_episodes) — a demó
meccsen az összes elemző rétegnek mutatnia kell valamit.

Futtatás:
    python -m pytest tests/test_demo_episodes.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.sim import (
    append_demo_episodes, simulate_ground_truth, simulate_with_panning_camera,
)


def _demo():
    ground = simulate_ground_truth(duration_s=10, fps=25.0, seed=1)
    match = simulate_with_panning_camera(ground)
    append_demo_episodes(match)
    return match


def test_all_new_layers_fire_on_demo():
    m = _demo()
    from handball.pipeline.momentum import scoring_runs
    from handball.pipeline.rules import seven_meter_outcomes
    from handball.pipeline.stoppages import detect_stoppages
    from handball.pipeline.substitutions import detect_substitutions

    runs = scoring_runs(m)
    assert any(r["team"] == "home" and r["length"] >= 3 for r in runs)

    sevens = seven_meter_outcomes(m)
    assert any(s["team"] == "home" for s in sevens)

    subs = detect_substitutions(m)
    assert any(ev["team"] == "home" for ev in subs)

    stops = [s for s in detect_stoppages(m) if s["kind"] == "időkérés"]
    assert len(stops) >= 1
    assert stops[0]["likely_team"] == "away"


def test_episode_frames_are_contiguous():
    """Az epizód-kockák t-értéke folytonos marad (a lejátszó erre épít)."""
    m = _demo()
    ts = [f.t for f in m.frames]
    assert ts == sorted(ts)
    assert ts[-1] - ts[0] + 1 == len(ts)
