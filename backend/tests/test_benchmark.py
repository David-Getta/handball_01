"""
Tesztek a validációs benchmarkra — a küszöbök egyben REGRESSZIÓ-ŐRÖK:
ha egy fejlesztés rontja a motor pontosságát, itt bukik el a csomag.

Futtatás:
    python -m pytest tests/test_benchmark.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.pipeline.benchmark import run_benchmarks


def test_all_benchmarks_pass_thresholds():
    """A teljes benchmark-csomag megfelel a küszöböknek (regresszió-őr).

    Rövidebb (30 mp-es) szimulációkkal futtatjuk, hogy a tesztcsomag gyors
    maradjon — a küszöbök erre a hosszra is érvényesek."""
    report = run_benchmarks(seeds=(1, 2), duration_s=30.0)
    failing = [f"{m.name}: {m.value:.2f} {m.unit} (küszöb "
               f"{'>=' if m.higher_is_better else '<='} {m.threshold:g})"
               for m in report.metrics if not m.passed]
    assert not failing, "Benchmark-regresszió: " + "; ".join(failing)


def test_report_markdown_contains_all_metrics():
    report = run_benchmarks(seeds=(1,), duration_s=20.0)
    md = report.to_markdown()
    assert "validációs benchmark" in md
    for m in report.metrics:
        assert m.name in md
    assert md.count("|") > 20  # táblázatos forma


def test_metrics_are_finite_and_sane():
    report = run_benchmarks(seeds=(1,), duration_s=20.0)
    keys = {m.key for m in report.metrics}
    assert {"homography_mean_m", "estimation_mean_m", "event_recall_pct",
            "measured_coverage_pct", "sprint_stability_diff",
            "top_speed_cap_ms"} <= keys
    for m in report.metrics:
        assert m.value == m.value and abs(m.value) < 1e6  # véges
        if m.unit == "%":
            assert 0.0 <= m.value <= 100.0


if __name__ == "__main__":
    test_all_benchmarks_pass_thresholds()
    test_report_markdown_contains_all_metrics()
    test_metrics_are_finite_and_sane()
    print("Minden benchmark-teszt OK.")
