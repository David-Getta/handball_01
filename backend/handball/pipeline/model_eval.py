"""
[V2] Modell-kiértékelés — detektor-minőség mérése VALÓDI felvételen.

Miért: a saját (finomhangolt) modell értéke csak méréssel bizonyítható.
Ez a modul egy videón mintavételezett képkockákon méri egy detektor
gyakorlati minőségét — cél-címkék NÉLKÜL is értelmes, összevethető
mutatókkal (a leggyengébb pont, a labda-lefedettség áll a fókuszban):

- ball_coverage_pct:   a kockák hány %-án talált labdát — a labdakövetés
                       és az eseményfelismerés ezen áll vagy bukik;
- avg_persons:         átlagos játékos-darabszám kockánként (siker: a
                       pályán lévő ~14 közelében, stabilan);
- person_count_std:    a játékos-darabszám ingadozása (kisebb = stabilabb);
- person/ball_conf:    átlagos detektálási bizonyosság;
- ms_per_frame:        sebesség (feldolgozási költség).

A detektor függvényként érkezik (mint a dataset-gyűjtőnél), így a mag
valódi modell nélkül tesztelhető; a CLI (scripts/compare_models.py) a
YOLO-t köti be, és KÉT modellt egymás mellett hasonlít össze.
"""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from .dataset import sample_frame_indices


@dataclass
class DetectorReport:
    """Egy detektor mérési eredménye egy videón."""
    frames: int = 0
    ball_coverage_pct: float = 0.0
    avg_persons: float = 0.0
    person_count_std: float = 0.0
    person_conf_mean: float = 0.0
    ball_conf_mean: float = 0.0
    ms_per_frame: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_detector(video_path: str | Path,
                      detect_fn: Callable,
                      samples: int = 120,
                      start: int = 0,
                      person_conf: float = 0.35,
                      ball_conf: float = 0.05,
                      skip_dark: bool = True,
                      dark_thresh: float = 40.0) -> DetectorReport:
    """Egy detektor mérése a videó egyenletesen mintavételezett kockáin.

    detect_fn(img) -> [(name, conf, x1, y1, x2, y2), ...] — name "person"
    vagy "ball". A sötét (bevezető) kockákat kihagyjuk, mint mindenhol.
    """
    import cv2

    cap = cv2.VideoCapture(str(video_path))
    n_total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if n_total <= 0:
        cap.release()
        raise RuntimeError(f"A videó nem olvasható: {video_path}")

    person_counts: list[int] = []
    person_confs: list[float] = []
    ball_confs: list[float] = []
    frames_with_ball = 0
    used = 0
    elapsed = 0.0

    for idx in sample_frame_indices(n_total, samples, start=start):
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, img = cap.read()
        if not ok:
            continue
        if skip_dark and float(img.mean()) < dark_thresh:
            continue
        t0 = time.perf_counter()
        dets = detect_fn(img)
        elapsed += time.perf_counter() - t0
        used += 1
        n_person = 0
        has_ball = False
        for (name, conf, *_rest) in dets:
            if name == "person" and conf >= person_conf:
                n_person += 1
                person_confs.append(float(conf))
            elif name == "ball" and conf >= ball_conf:
                has_ball = True
                ball_confs.append(float(conf))
        person_counts.append(n_person)
        if has_ball:
            frames_with_ball += 1
    cap.release()

    rep = DetectorReport(frames=used)
    if used == 0:
        return rep
    mean_p = sum(person_counts) / used
    rep.ball_coverage_pct = round(100.0 * frames_with_ball / used, 1)
    rep.avg_persons = round(mean_p, 2)
    rep.person_count_std = round(math.sqrt(
        sum((c - mean_p) ** 2 for c in person_counts) / used), 2)
    rep.person_conf_mean = round(
        sum(person_confs) / len(person_confs), 3) if person_confs else 0.0
    rep.ball_conf_mean = round(
        sum(ball_confs) / len(ball_confs), 3) if ball_confs else 0.0
    rep.ms_per_frame = round(1000.0 * elapsed / used, 1)
    return rep


def comparison_markdown(video: str, a_name: str, a: DetectorReport,
                        b_name: str | None = None,
                        b: DetectorReport | None = None) -> str:
    """Egy- vagy kétmodelles eredménylap Markdownban — a finomhangolás
    ELŐTTE/UTÁNA bizonyítéka (pályázatba/pilotnak beemelhető)."""
    rows = [
        ("Mintavételezett kocka", "frames", "db", False),
        ("Labda-lefedettség", "ball_coverage_pct", "%", True),
        ("Átl. játékos/kocka", "avg_persons", "db", True),
        ("Játékos-szám ingadozás", "person_count_std", "db", False),
        ("Játékos-bizonyosság (átl.)", "person_conf_mean", "", True),
        ("Labda-bizonyosság (átl.)", "ball_conf_mean", "", True),
        ("Sebesség", "ms_per_frame", "ms/kocka", False),
    ]
    da, db_ = a.to_dict(), (b.to_dict() if b else None)
    if db_ is None:
        header = f"| Mutató | {a_name} |\n|---|---|"
        body = "\n".join(f"| {label} | {da[key]} {unit} |"
                         for (label, key, unit, _) in rows)
    else:
        header = (f"| Mutató | {a_name} | {b_name} | Δ |\n|---|---|---|---|")
        lines = []
        for (label, key, unit, higher_better) in rows:
            va, vb = da[key], db_[key]
            delta = round(vb - va, 2)
            mark = ""
            if higher_better and delta != 0:
                mark = " ✅" if delta > 0 else " ❌"
            lines.append(f"| {label} | {va} {unit} | {vb} {unit} | "
                         f"{'+' if delta >= 0 else ''}{delta}{mark} |")
        body = "\n".join(lines)
    return (f"# Detektor-összehasonlítás\n\nVideó: `{video}`\n\n"
            f"{header}\n{body}\n\n"
            "A labda-lefedettség a kulcsmutató: az eseményfelismerés "
            "(gól/lövés/passz) minősége közvetlenül ezen múlik.\n")
