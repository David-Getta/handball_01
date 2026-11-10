"""
Tesztek a validációs benchmark parancssori belépőjére
(scripts/benchmark.py) — a szkript eddig egyszer sem futott a csomagban.
(A metrikák tesztjei a tests/test_benchmark.py-ban élnek.)

Futtatás:
    python -m pytest tests/test_benchmark_cli.py -q
"""

from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.pipeline.benchmark import BenchmarkReport, Metric  # noqa: E402
from scripts import benchmark as cli  # noqa: E402


def test_detect_version_a_git_leiras_kulonben_dev(monkeypatch):
    """A verzió a git-leírás (szóközök nélkül); ha a git nem ad semmit
    vagy nincs is git, "dev" — az eredménylap így mindig visz verziót."""
    hivas: dict = {}

    def kamu_run(parancs, **kw):
        hivas.update(parancs=parancs, **kw)
        return SimpleNamespace(stdout="v0.1.194-3-gabc1234\n")

    monkeypatch.setattr(cli.subprocess, "run", kamu_run)
    assert cli._detect_version() == "v0.1.194-3-gabc1234"
    assert hivas["parancs"] == ["git", "describe", "--tags", "--always"]
    assert os.path.isdir(os.path.join(hivas["cwd"], "scripts"))

    monkeypatch.setattr(cli.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(stdout="  \n"))
    assert cli._detect_version() == "dev"

    def nincs_git(*a, **k):
        raise FileNotFoundError("git")
    monkeypatch.setattr(cli.subprocess, "run", nincs_git)
    assert cli._detect_version() == "dev"


def test_main_valodi_futas_eredmenylapot_es_jsont_ir(tmp_path, monkeypatch,
                                                     capsys):
    """VALÓDI (rövid) benchmark-futás: a Markdown eredménylap és mellé a
    JSON elkészül, a kimenet metrikánként egy sort és az összképet írja,
    a kilépőkód az összkép (0 = minden metrika megfelelt)."""
    ki_fajl = tmp_path / "lap.md"
    monkeypatch.setattr(cli, "_detect_version", lambda: "v-teszt")
    monkeypatch.setattr(sys, "argv", ["benchmark", "--out", str(ki_fajl),
                                      "--seeds", "1", "2", "--duration",
                                      "30"])
    kod = cli.main()

    md = ki_fajl.read_text(encoding="utf-8")
    assert "# SportMachine — validációs benchmark" in md
    assert "Verzió: `v-teszt` · seedek: [1, 2]" in md
    adat = json.loads(ki_fajl.with_suffix(".json").read_text(
        encoding="utf-8"))
    assert adat["version"] == "v-teszt" and adat["seeds"] == [1, 2]
    kulcsok = {m["key"] for m in adat["metrics"]}
    assert {"homography_mean_m", "estimation_mean_m", "event_recall_pct",
            "top_speed_cap_ms"} <= kulcsok
    assert all({"name", "value", "unit", "threshold", "higher_is_better",
                "description", "passed"} <= set(m) for m in adat["metrics"])
    megfelelt = all(m["passed"] for m in adat["metrics"])
    assert kod == (0 if megfelelt else 1)

    ki = capsys.readouterr().out
    assert ki.count("(küszöb ") == len(adat["metrics"])
    assert ("MINDEN METRIKA MEGFELELT" in ki) == megfelelt
    assert f"eredménylap: {ki_fajl} (+ lap.json)" in ki


def _kamu_riport(ertek):
    return BenchmarkReport(version="v-teszt", seeds=(7,), metrics=[
        Metric("jo", "Jó metrika", 0.2, "m", 0.35, False, "leírás"),
        Metric("masik", "Másik metrika", ertek, "%", 85.0, True, "leírás")])


def test_main_buko_metrikanal_1_es_kod_es_megnevezi(tmp_path, monkeypatch,
                                                    capsys):
    """Ha egy metrika nem éri el a küszöbét, a kilépőkód 1 (a regresszió
    így a parancssorból is megáll), a sora BUKIK jelzést kap, és a JSON
    "passed" mezője hamis; a paraméterek átmennek a futtatóba."""
    kert: dict = {}

    def kamu_futas(seeds, duration_s, version):
        kert.update(seeds=seeds, duration_s=duration_s, version=version)
        return _kamu_riport(70.0)

    monkeypatch.setattr(cli, "run_benchmarks", kamu_futas)
    monkeypatch.setattr(cli, "_detect_version", lambda: "v-teszt")
    ki_fajl = tmp_path / "lap.md"
    monkeypatch.setattr(sys, "argv", ["benchmark", "--out", str(ki_fajl),
                                      "--seeds", "7", "--duration", "12.5"])
    assert cli.main() == 1
    assert kert == {"seeds": (7,), "duration_s": 12.5, "version": "v-teszt"}
    ki = capsys.readouterr().out
    assert "[OK   ] Jó metrika: 0.20 m (küszöb <= 0.35)" in ki
    assert "[BUKIK] Másik metrika: 70.00 % (küszöb >= 85)" in ki
    assert "Összkép: VAN BUKÓ METRIKA" in ki
    adat = json.loads(ki_fajl.with_suffix(".json").read_text(
        encoding="utf-8"))
    assert [m["passed"] for m in adat["metrics"]] == [True, False]
    assert "❌" in ki_fajl.read_text(encoding="utf-8")


def test_main_alapertekek_es_megfelelt_osszkep(tmp_path, monkeypatch, capsys):
    """Paraméter nélkül az alap seedekkel (1, 2, 3) és 60 mp-es
    szimulációval fut, a lapot a munkakönyvtár benchmark_report.md
    fájljába írja; ha minden metrika megfelelt, a kilépőkód 0."""
    kert: dict = {}

    def kamu_futas(seeds, duration_s, version):
        kert.update(seeds=seeds, duration_s=duration_s)
        return _kamu_riport(90.0)

    monkeypatch.setattr(cli, "run_benchmarks", kamu_futas)
    monkeypatch.setattr(cli, "_detect_version", lambda: "v-teszt")
    monkeypatch.setattr(sys, "argv", ["benchmark"])
    monkeypatch.chdir(tmp_path)
    assert cli.main() == 0
    assert kert == {"seeds": (1, 2, 3), "duration_s": 60.0}
    assert (tmp_path / "benchmark_report.md").exists()
    assert (tmp_path / "benchmark_report.json").exists()
    assert "Összkép: MINDEN METRIKA MEGFELELT" in capsys.readouterr().out
