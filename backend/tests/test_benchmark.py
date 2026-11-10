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


# ---- A metrikák külön-külön (benchmark_*) és az összesített ítélet ------------

def _metrika(value, threshold, higher_is_better):
    from handball.pipeline.benchmark import Metric
    return Metric("k", "név", value, "m", threshold, higher_is_better, "leírás")


def test_all_passed_csak_akkor_igaz_ha_minden_metrika_megfelel():
    """Az összesített ítélet: minden metrika megfelel a SAJÁT irányú
    küszöbének (kisebb a jobb / nagyobb a jobb); a küszöb maga még jó;
    egyetlen bukó metrika az egészet buktatja."""
    from handball.pipeline.benchmark import BenchmarkReport

    jo_kis = _metrika(0.3, 0.35, False)
    jo_nagy = _metrika(90.0, 85.0, True)
    assert BenchmarkReport(metrics=[jo_kis, jo_nagy]).all_passed is True
    hataron = [_metrika(0.35, 0.35, False), _metrika(85.0, 85.0, True)]
    assert BenchmarkReport(metrics=hataron).all_passed is True
    assert BenchmarkReport(
        metrics=[jo_kis, _metrika(0.36, 0.35, False)]).all_passed is False
    assert BenchmarkReport(
        metrics=[jo_nagy, _metrika(84.9, 85.0, True)]).all_passed is False


def test_all_passed_egyezik_a_teljes_csomag_metrikaival():
    """A valódi csomagon az összesített ítélet a metrikák `passed`
    értékeinek ÉS-e — a jelentés ✅ / ❌ oszlopával egyezően."""
    report = run_benchmarks(seeds=(1,), duration_s=20.0)
    assert report.all_passed == all(m.passed for m in report.metrics)
    md = report.to_markdown()
    assert ("❌" in md) == (not report.all_passed)


def test_benchmark_homography_zaj_nelkul_pontos_zajjal_romlik():
    """M1: zaj nélküli sarkokból a homográfia visszaadja a rácspontokat
    (hiba ~0); nagyobb sarok-zajjal a hiba nő; ugyanazokkal a seedekkel
    az eredmény azonos (verziók közt összevethető)."""
    from handball.pipeline.benchmark import benchmark_homography

    pontos = benchmark_homography((1, 2), corner_noise_px=0.0)
    assert [m.key for m in pontos] == ["homography_mean_m",
                                       "homography_p95_m"]
    assert all(m.unit == "m" and not m.higher_is_better for m in pontos)
    assert all(m.value < 1e-6 and m.passed for m in pontos)

    alap = benchmark_homography((1, 2))
    assert 0.0 < alap[0].value <= alap[1].value        # átlag ≤ 95. percentilis
    assert [m.value for m in benchmark_homography((1, 2))] == \
        [m.value for m in alap]
    zajos = benchmark_homography((1, 2), corner_noise_px=8.0)
    assert zajos[0].value > alap[0].value
    assert "±8 px" in zajos[0].description


def test_benchmark_estimation_hiba_es_lefedettseg():
    """M2: a becslés átlagos hibája méterben (kisebb a jobb), a mért
    lefedettség százalékban (nagyobb a jobb); rögzített seeddel
    megismételhető."""
    from handball.pipeline.benchmark import benchmark_estimation

    m = benchmark_estimation((1,), duration_s=15.0)
    assert [x.key for x in m] == ["estimation_mean_m",
                                  "measured_coverage_pct"]
    hiba, lefedettseg = m
    assert hiba.unit == "m" and not hiba.higher_is_better
    assert lefedettseg.unit == "%" and lefedettseg.higher_is_better
    assert 0.0 <= hiba.value < 40.0
    assert 0.0 < lefedettseg.value <= 100.0
    assert [x.value for x in benchmark_estimation((1,), duration_s=15.0)] \
        == [hiba.value, lefedettseg.value]


def test_benchmark_estimation_seed_nelkul_nem_megy_at():
    """Minta (seed) nélkül nincs mit mérni: nem kivétel, de a 0%-os mért
    lefedettség NEM felel meg a küszöbnek — az üres futás nem "zöld"."""
    from handball.pipeline.benchmark import benchmark_estimation

    hiba, lefedettseg = benchmark_estimation(())
    assert hiba.value == 0.0 and lefedettseg.value == 0.0
    assert lefedettseg.passed is False


def test_benchmark_event_recall_szazalek_es_a_tures_szamit():
    """M3: a pásztázó kamerán megtalált passz-események aránya 0..100%;
    szűkebb idő-tűréssel nem lehet több a találat; a leírás megnevezi,
    hány eseményből mért."""
    import re

    from handball.pipeline.benchmark import benchmark_event_recall

    (alap,) = benchmark_event_recall((1,), duration_s=20.0)
    assert alap.key == "event_recall_pct"
    assert alap.unit == "%" and alap.higher_is_better
    assert 0.0 <= alap.value <= 100.0
    db = int(re.search(r"teljes rálátás (\d+) felismert", alap.description)
             .group(1))
    assert db > 0, "a próba-meccsen nincs passz-esemény"
    (szuk,) = benchmark_event_recall((1,), duration_s=20.0, tol_frames=0)
    assert szuk.value <= alap.value
    (tag,) = benchmark_event_recall((1,), duration_s=20.0, tol_frames=500)
    assert tag.value >= alap.value


def test_benchmark_event_recall_seed_nelkul_nem_megy_at():
    """Seed nélkül nincs várt esemény: 0% (nem osztás nullával), ami a
    küszöb alatt van — az üres futás nem megy át."""
    from handball.pipeline.benchmark import benchmark_event_recall

    (m,) = benchmark_event_recall(())
    assert m.value == 0.0 and m.passed is False
    assert "0 felismert passz-eseményéből" in m.description


def test_benchmark_noise_robustness_zaj_nelkul_nulla_elteres():
    """M4: zaj nélkül a "zajos" adat azonos a tisztával → a sprint-szám
    eltérése pontosan 0; 5 cm zajjal a csúcssebesség a hihetőségi plafon
    alatt marad (a szűrők dolgoznak)."""
    from handball.pipeline.benchmark import benchmark_noise_robustness
    from handball.pipeline.stats import MAX_PLAUSIBLE_MS

    tiszta = benchmark_noise_robustness((1,), duration_s=15.0, noise_m=0.0)
    assert [m.key for m in tiszta] == ["sprint_stability_diff",
                                       "top_speed_cap_ms"]
    assert tiszta[0].value == 0.0
    zajos = benchmark_noise_robustness((1,), duration_s=15.0)
    assert zajos[0].value >= 0.0
    assert 0.0 < zajos[1].value <= MAX_PLAUSIBLE_MS
    assert zajos[1].threshold == MAX_PLAUSIBLE_MS and zajos[1].passed


def test_benchmark_noise_robustness_seed_nelkul_nulla_nem_kivetel():
    """Seed nélkül nincs játékos, akin mérni lehetne: 0 eltérés és 0
    csúcssebesség — kivétel és osztás nullával nélkül."""
    from handball.pipeline.benchmark import benchmark_noise_robustness

    elteres, csucs = benchmark_noise_robustness(())
    assert elteres.value == 0.0 and csucs.value == 0.0


if __name__ == "__main__":
    test_all_benchmarks_pass_thresholds()
    test_report_markdown_contains_all_metrics()
    test_metrics_are_finite_and_sane()
    print("Minden benchmark-teszt OK.")
