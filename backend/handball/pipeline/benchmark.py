"""
[V] Validációs benchmark — reprodukálható pontosság-metrikák a motorról.

Miért: egy elemző rendszer értéke azon áll, MENNYIRE PONTOS — ezt állítani
kevés, mérni kell. Ez a modul ismert "földi igazságú" (szimulált) adatokon
méri a lánc kulcslépéseit, minden futásnál ugyanúgy (rögzített seedek), így
a szám verzióról verzióra összevethető: a fejlesztés nem ronthat észrevétlenül
(a tesztek küszöböket őriznek), a pályázathoz/pilotokhoz pedig hiteles,
újrafuttatható eredménylap készül (scripts/benchmark.py).

Metrikák (mindnél a földi igazság KONSTRUKCIÓBÓL ismert):
- M1 Kalibráció: 4 zajos sarokból illesztett homográfia hibája méterben.
- M2 Képen kívüli becslés: a becsült pozíciók hibája a valódihoz képest.
- M3 Esemény-visszaidézés: a teljes rálátással felismert gólok mekkora
     részét találja meg a rendszer pásztázó (részleges) kameraképből.
- M4 Zaj-robusztusság: 5 cm-es mérési zaj mellett a sprint-számok
     stabilitása és a csúcssebesség hihetőségi plafonja.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from ..models.tracking import Frame, Match, PlayerPosition, PositionSource
from ..sim.match_simulator import simulate_ground_truth, simulate_with_panning_camera
from ._homography import apply_homography, homography_from_points
from .calibration import COURT_LENGTH_M, COURT_WIDTH_M
from .event_detection import detect_events
from .stats import MAX_PLAUSIBLE_MS, compute_player_stats


@dataclass
class Metric:
    """Egy benchmark-metrika: érték + küszöb + megfelelt-e."""
    key: str
    name: str
    value: float
    unit: str
    threshold: float
    higher_is_better: bool
    description: str

    @property
    def passed(self) -> bool:
        return (self.value >= self.threshold if self.higher_is_better
                else self.value <= self.threshold)


@dataclass
class BenchmarkReport:
    version: str = "dev"
    seeds: tuple = ()
    metrics: list = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(m.passed for m in self.metrics)

    def to_markdown(self) -> str:
        rows = "\n".join(
            f"| {m.name} | **{m.value:.2f} {m.unit}** | "
            f"{'≥' if m.higher_is_better else '≤'} {m.threshold:g} {m.unit} | "
            f"{'✅' if m.passed else '❌'} |"
            for m in self.metrics)
        notes = "\n".join(f"- **{m.name}**: {m.description}"
                          for m in self.metrics)
        return (f"# SportMachine — validációs benchmark\n\n"
                f"Verzió: `{self.version}` · seedek: {list(self.seeds)} · "
                f"minden érték a seedek átlaga.\n\n"
                f"| Metrika | Érték | Küszöb | Állapot |\n"
                f"|---|---|---|---|\n{rows}\n\n"
                f"## Módszertan\n\n{notes}\n\n"
                f"A metrikák szimulált, ismert földi igazságú adatokon "
                f"készülnek (rögzített seedekkel), ezért verziók között "
                f"közvetlenül összevethetők; a tesztcsomag a küszöböket "
                f"őrzi, így a pontosság nem romolhat észrevétlenül.\n")


def _project_court_to_image() -> list:
    """Egy tipikus oldalkamera perspektíváját utánzó VALÓDI homográfia:
    a pálya sarkai egy trapézra képződnek (a túloldal rövidebb)."""
    court = [(0.0, 0.0), (COURT_LENGTH_M, 0.0),
             (COURT_LENGTH_M, COURT_WIDTH_M), (0.0, COURT_WIDTH_M)]
    image = [(420.0, 180.0), (1500.0, 180.0), (1820.0, 980.0), (100.0, 980.0)]
    return homography_from_points(court, image), court, image


def benchmark_homography(seeds, corner_noise_px: float = 2.0) -> list[Metric]:
    """M1: a felhasználó ±2 px pontossággal jelöli a sarkokat — mennyire
    pontos ebből a pálya-koordináta? Rács-pontokon mérünk métert."""
    errors = []
    for seed in seeds:
        rng = random.Random(1000 + seed)
        h_true, court, image = _project_court_to_image()
        noisy = [(px + rng.gauss(0, corner_noise_px),
                  py + rng.gauss(0, corner_noise_px)) for (px, py) in image]
        h_fit = homography_from_points(noisy, court)
        for gx in range(2, 39, 4):
            for gy in range(2, 19, 4):
                ix, iy = apply_homography(h_true, float(gx), float(gy))
                mx, my = apply_homography(h_fit, ix, iy)
                errors.append(math.hypot(mx - gx, my - gy))
    errors.sort()
    mean = sum(errors) / len(errors)
    p95 = errors[int(0.95 * (len(errors) - 1))]
    return [
        Metric("homography_mean_m", "Kalibráció átlagos hibája", mean, "m",
               0.35, False,
               f"±{corner_noise_px:g} px sarok-zajjal illesztett homográfia "
               "hibája pálya-rácspontokon (méter)."),
        Metric("homography_p95_m", "Kalibráció 95. percentilis hibája", p95,
               "m", 0.9, False,
               "A hibaeloszlás 95. percentilise — a rossz eset is korlátos."),
    ]


def benchmark_estimation(seeds, duration_s: float = 60.0) -> list[Metric]:
    """M2: a képen kívüli játékosok BECSÜLT helye mennyire tér el a
    valóditól (méter), és a kamera mennyit lát (mért lefedettség %)."""
    errors, measured, total = [], 0, 0
    for seed in seeds:
        gt = simulate_ground_truth(duration_s=duration_s, seed=seed)
        pan = simulate_with_panning_camera(gt)
        gt_pos = {(f.t, p.track_id): (p.x, p.y)
                  for f in gt.frames for p in f.players}
        for f in pan.frames:
            for p in f.players:
                total += 1
                if p.source == PositionSource.MEASURED:
                    measured += 1
                else:
                    tx, ty = gt_pos[(f.t, p.track_id)]
                    errors.append(math.hypot(p.x - tx, p.y - ty))
    mean = sum(errors) / max(1, len(errors))
    coverage = 100.0 * measured / max(1, total)
    return [
        Metric("estimation_mean_m", "Képen kívüli becslés átlagos hibája",
               mean, "m", 4.0, False,
               "A pásztázó kamera által nem látott játékosok becsült és "
               "valódi helye közti átlagos távolság."),
        Metric("measured_coverage_pct", "Mért lefedettség", coverage, "%",
               55.0, True,
               "A játékos-pozíciók mekkora hányada közvetlen mérés (nem "
               "becslés) a pásztázó kameraképből."),
    ]


def benchmark_event_recall(seeds, duration_s: float = 60.0,
                           tol_frames: int = 25) -> list[Metric]:
    """M3: a teljes rálátással felismert (passz-)események mekkora részét
    találja meg a rendszer a pásztázó, RÉSZLEGES kameraképből is — vagyis a
    kamera-korlát mennyit ront az eseményfelismerésen."""
    found, expected = 0, 0
    for seed in seeds:
        gt = simulate_ground_truth(duration_s=duration_s, seed=seed)
        pan = simulate_with_panning_camera(gt)
        gt_ev = [e for e in detect_events(gt) if e.type.value == "pass"]
        pan_ev = [e for e in detect_events(pan) if e.type.value == "pass"]
        expected += len(gt_ev)
        used: set[int] = set()
        for g in gt_ev:
            for i, c in enumerate(pan_ev):
                if i in used:
                    continue
                if c.team == g.team and abs(c.t - g.t) <= tol_frames:
                    used.add(i)
                    found += 1
                    break
    recall = 100.0 * found / max(1, expected)
    return [
        Metric("event_recall_pct", "Esemény-visszaidézés pásztázó kamerán",
               recall, "%", 85.0, True,
               f"A teljes rálátás {expected} felismert passz-eseményéből "
               "ennyit talál meg a rendszer a labdát követő, részleges "
               "kameraképből is (±1 mp tűréssel)."),
    ]


def benchmark_noise_robustness(seeds, duration_s: float = 60.0,
                               noise_m: float = 0.05) -> list[Metric]:
    """M4: 5 cm-es mérési zaj (tipikus detektálás-remegés) mellett a
    sprint-számok stabilak maradnak-e, és a csúcssebesség a hihetőségi
    plafon alatt marad-e (a szűrők dolgoznak)."""
    diffs, top_speeds = [], []
    for seed in seeds:
        gt = simulate_ground_truth(duration_s=duration_s, seed=seed)
        rng = random.Random(2000 + seed)
        noisy = Match(meta=gt.meta, frames=[])
        for f in gt.frames:
            noisy.frames.append(Frame(t=f.t, ball=f.ball, players=[
                PlayerPosition(track_id=p.track_id, team=p.team,
                               x=p.x + rng.gauss(0, noise_m),
                               y=p.y + rng.gauss(0, noise_m),
                               source=p.source,
                               jersey_number=p.jersey_number)
                for p in f.players]))
        clean = compute_player_stats(gt)
        dirty = compute_player_stats(noisy)
        for tid, s in clean.items():
            diffs.append(abs(dirty[tid].sprint_count - s.sprint_count))
            top_speeds.append(dirty[tid].top_speed_ms)
    mean_diff = sum(diffs) / max(1, len(diffs))
    max_top = max(top_speeds) if top_speeds else 0.0
    return [
        Metric("sprint_stability_diff", "Sprint-szám eltérés 5 cm zaj alatt",
               mean_diff, "db", 1.5, False,
               "Játékosonkénti átlagos sprint-szám különbség zajos és tiszta "
               "adat között — a simítás/szűrés stabilitása."),
        Metric("top_speed_cap_ms", "Csúcssebesség-plafon zaj alatt", max_top,
               "m/s", MAX_PLAUSIBLE_MS, False,
               "Zajos adatból sem születhet emberfeletti sebesség — a "
               "hihetőségi szűrő működik."),
    ]


def run_benchmarks(seeds=(1, 2, 3), duration_s: float = 60.0,
                   version: str = "dev") -> BenchmarkReport:
    """A teljes benchmark-csomag futtatása — az eredménylap a pályázati/
    piloti bizonyíték és egyben regresszió-őr (a tesztek a küszöböket vetik
    össze az értékekkel)."""
    report = BenchmarkReport(version=version, seeds=tuple(seeds))
    report.metrics += benchmark_homography(seeds)
    report.metrics += benchmark_estimation(seeds, duration_s=duration_s)
    report.metrics += benchmark_event_recall(seeds, duration_s=duration_s)
    report.metrics += benchmark_noise_robustness(seeds, duration_s=duration_s)
    return report
