"""
Tesztek a tanítóadat-gyűjtésre (dataset.py) és az osztály-felismerésre.

Futtatás:
    python -m pytest tests/test_dataset.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

from handball.pipeline.dataset import (
    collect_dataset, sample_frame_indices, yolo_label_lines,
)
from scripts.process_video import _class_ids


def _make_video(path, n_frames=100, fps=25.0, size=(320, 240), dark_first=0):
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    w = cv2.VideoWriter(str(path), fourcc, fps, size)
    for i in range(n_frames):
        val = 5 if i < dark_first else 120  # sötét bevezető vs. világos
        img = np.full((size[1], size[0], 3), val, np.uint8)
        w.write(img)
    w.release()


def _stub_detect(img):
    """Determinisztikus ál-detektor: egy játékos + egy labda minden képen."""
    return [
        ("person", 0.9, 50.0, 60.0, 90.0, 160.0),
        ("ball", 0.4, 200.0, 100.0, 214.0, 114.0),
        ("egyeb", 0.9, 0.0, 0.0, 10.0, 10.0),  # ismeretlen név — eldobjuk
    ]


def test_sample_indices_even_and_unique():
    idx = sample_frame_indices(1000, 10, start=100)
    assert len(idx) == 10 and idx[0] == 100 and idx[-1] == 999
    assert idx == sorted(set(idx))  # egyedi, növekvő
    assert sample_frame_indices(5, 100) == [0, 1, 2, 3, 4]  # plafon a hossz
    assert sample_frame_indices(10, 0) == []


def test_yolo_label_lines_normalized_and_clamped():
    lines = yolo_label_lines(
        [(0, 50, 60, 90, 160), (1, -10, -10, 30, 30), (0, 5, 5, 5, 5)],
        320, 240)
    assert len(lines) == 2  # az elfajult (0 területű) doboz kimarad
    for line in lines:
        parts = line.split()
        assert len(parts) == 5
        assert all(0.0 <= float(v) <= 1.0 for v in parts[1:])
    # Az első doboz közepe: cx=(50+90)/2/320, cy=(60+160)/2/240.
    p = lines[0].split()
    assert abs(float(p[1]) - 70 / 320) < 1e-4
    assert abs(float(p[2]) - 110 / 240) < 1e-4


def test_collect_writes_yolo_structure(tmp_path):
    video = tmp_path / "meccs.mp4"
    _make_video(video, n_frames=100)
    stats = collect_dataset(video, _stub_detect, tmp_path / "ds", samples=20)
    assert stats.images == 20
    assert stats.train_images + stats.val_images == 20
    assert stats.val_images >= 1  # van validációs rész
    assert stats.person_boxes == 20 and stats.ball_boxes == 20
    assert (tmp_path / "ds" / "dataset.yaml").exists()
    # Kép- és label-párok egyeznek.
    for split in ("train", "val"):
        imgs = {p.stem for p in (tmp_path / "ds" / "images" / split).iterdir()}
        labels = {p.stem for p in (tmp_path / "ds" / "labels" / split).iterdir()}
        assert imgs == labels
    # A label-fájl formátuma helyes (osztály + 4 normált szám).
    any_label = next((tmp_path / "ds" / "labels" / "train").iterdir())
    first = any_label.read_text(encoding="utf-8").splitlines()[0].split()
    assert first[0] in ("0", "1") and len(first) == 5


def test_collect_skips_dark_frames(tmp_path):
    video = tmp_path / "sotet.mp4"
    _make_video(video, n_frames=100, dark_first=50)
    stats = collect_dataset(video, _stub_detect, tmp_path / "ds", samples=10)
    assert stats.skipped_dark >= 4  # a minták fele a sötét részre esett
    assert stats.images + stats.skipped_dark <= 10


def test_class_ids_for_coco_and_custom_models():
    # Előtanított COCO: person=0, sports ball=32.
    assert _class_ids({0: "person", 32: "sports ball"}) == ([0], [32])
    # Saját finomhangolt modell: person=0, ball=1.
    assert _class_ids({0: "person", 1: "ball"}) == ([0], [1])
    # Ismeretlen/hiányzó névlista → COCO-tartalék.
    assert _class_ids(None) == ([0], [32])
    assert _class_ids({0: "cat", 5: "dog"}) == ([0], [32])


if __name__ == "__main__":
    import tempfile
    from pathlib import Path
    test_sample_indices_even_and_unique()
    test_yolo_label_lines_normalized_and_clamped()
    with tempfile.TemporaryDirectory() as d:
        test_collect_writes_yolo_structure(Path(d))
    test_class_ids_for_coco_and_custom_models()
    print("Minden adathalmaz-teszt OK.")
