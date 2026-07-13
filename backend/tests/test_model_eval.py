"""
Tesztek a modell-kiértékelésre (model_eval.py) — ál-detektorokkal.

Futtatás:
    python -m pytest tests/test_model_eval.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

from handball.pipeline.model_eval import comparison_markdown, evaluate_detector


def _make_video(path, n_frames=100, fps=25.0, size=(320, 240), dark_first=0):
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    w = cv2.VideoWriter(str(path), fourcc, fps, size)
    for i in range(n_frames):
        val = 5 if i < dark_first else 120
        w.write(np.full((size[1], size[0], 3), val, np.uint8))
    w.release()


def _detector(persons=5, ball_every=2):
    """Ál-detektor: fix számú játékos, minden `ball_every`-edik hívásra labda."""
    calls = {"n": 0}

    def detect(img):
        calls["n"] += 1
        out = [("person", 0.8, 10.0 * i, 10.0, 10.0 * i + 8, 40.0)
               for i in range(persons)]
        if ball_every and calls["n"] % ball_every == 0:
            out.append(("ball", 0.3, 100.0, 100.0, 110.0, 110.0))
        return out

    return detect


def test_metrics_reflect_detector_behavior(tmp_path):
    video = tmp_path / "meccs.mp4"
    _make_video(video)
    rep = evaluate_detector(video, _detector(persons=5, ball_every=2),
                            samples=20)
    assert rep.frames == 20
    assert abs(rep.ball_coverage_pct - 50.0) < 0.1  # minden 2. kockán labda
    assert rep.avg_persons == 5.0
    assert rep.person_count_std == 0.0  # tökéletesen stabil
    assert rep.person_conf_mean == 0.8 and rep.ball_conf_mean == 0.3
    assert rep.ms_per_frame >= 0.0


def test_dark_frames_excluded(tmp_path):
    video = tmp_path / "sotet.mp4"
    _make_video(video, n_frames=100, dark_first=50)
    rep = evaluate_detector(video, _detector(), samples=10)
    assert rep.frames <= 6  # a minták fele sötét — kimarad


def test_low_conf_detections_filtered(tmp_path):
    video = tmp_path / "meccs.mp4"
    _make_video(video, n_frames=40)

    def weak(img):
        return [("person", 0.1, 0, 0, 10, 30), ("ball", 0.01, 0, 0, 5, 5)]

    rep = evaluate_detector(video, weak, samples=10)
    assert rep.avg_persons == 0.0  # 0.35 alatti játékos nem számít
    assert rep.ball_coverage_pct == 0.0  # 0.05 alatti labda nem számít


def test_comparison_markdown_two_models(tmp_path):
    video = tmp_path / "meccs.mp4"
    _make_video(video, n_frames=60)
    a = evaluate_detector(video, _detector(persons=5, ball_every=4), samples=12)
    b = evaluate_detector(video, _detector(persons=6, ball_every=1), samples=12)
    md = comparison_markdown("meccs.mp4", "alap.pt", a, "sajat.pt", b)
    assert "alap.pt" in md and "sajat.pt" in md
    assert "Labda-lefedettség" in md
    assert "✅" in md  # a jobb labda-lefedettség jelölve
    # Egymodelles lap is épül.
    md1 = comparison_markdown("meccs.mp4", "alap.pt", a)
    assert "alap.pt" in md1 and "Δ" not in md1


if __name__ == "__main__":
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        test_metrics_reflect_detector_behavior(Path(d))
    print("Minden modell-kiértékelő teszt OK.")
