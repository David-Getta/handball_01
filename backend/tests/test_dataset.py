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
    collect_dataset, hard_frame_indices, sample_frame_indices,
    yolo_label_lines,
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


def _labda_hezagos_meccs():
    """Meccs t=0..99 kockákkal; a labda mért, KIVÉVE két kiesést:
    t=10..39 (hosszú) és t=60..69 (rövid) — a rövidebbik pótolt
    (interpolált) labdát kap, ami kiesésnek számít."""
    from handball.models.tracking import Ball, Frame, Match, MatchMeta
    from handball.pipeline.ball_filter import INTERPOLATED_CONFIDENCE

    frames = []
    for t in range(100):
        if 10 <= t <= 39:
            ball = None                       # tényleg nincs észlelés
        elif 60 <= t <= 69:
            ball = Ball(x=20.0, y=10.0,
                        confidence=INTERPOLATED_CONFIDENCE)  # pótolt
        else:
            ball = Ball(x=20.0, y=10.0)
        frames.append(Frame(t=t, players=[], ball=ball))
    return Match(MatchMeta(match_id="hf", home_team="A", away_team="B",
                           fps=10.0), frames)


def test_hard_indices_a_leghosszabb_kiesesek_kozepet_adjak():
    m = _labda_hezagos_meccs()
    # count=1: csak a leghosszabb (t=10..39) közepe.
    assert hard_frame_indices(m, 1) == [24]
    # count=2: a pótolt szakasz (t=60..69) közepe is — időrendben.
    assert hard_frame_indices(m, 2) == [24, 64]
    assert hard_frame_indices(m, 0) == []


def test_collect_a_nehez_kockakat_is_menti(tmp_path):
    video = tmp_path / "aktiv.mp4"
    _make_video(video, n_frames=100)
    stats = collect_dataset(video, _stub_detect, tmp_path / "ds",
                            samples=10, hard_indices=[3, 7])
    # A nehéz kockák tényleg bekerültek (a képnév hordozza az indexet)…
    nevek = set()
    for split in ("train", "val"):
        nevek |= {p.stem for p in
                  (tmp_path / "ds" / "images" / split).iterdir()}
    assert "aktiv_000003" in nevek and "aktiv_000007" in nevek
    # …és a keret nem duzzadt: legfeljebb `samples` kép készült.
    assert stats.images <= 10


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


# ---- A YOLO dataset.yaml megírása (write_dataset_yaml) -----------------------

def _yaml_sorok(path):
    """A megírt dataset.yaml kulcs → érték párjai (a `names:` blokk az
    osztály-azonosító → név szótára)."""
    felso, nevek, blokk = {}, {}, False
    for sor in path.read_text(encoding="utf-8").splitlines():
        if sor.startswith("  "):
            assert blokk, f"behúzott sor a names blokkon kívül: {sor!r}"
            k, v = sor.strip().split(": ", 1)
            nevek[int(k)] = v
            continue
        k, _, v = sor.partition(":")
        blokk = (k == "names")
        if not blokk:
            felso[k] = v.strip()
    return felso, nevek


def test_write_dataset_yaml_a_tanitashoz_kello_kulcsokkal(tmp_path):
    """A dataset.yaml a mappa ABSZOLÚT útját, a train/val képmappát és a
    két osztály nevét (0 = person, 1 = ball) viszi — a visszaadott út
    maga a megírt fájl."""
    from handball.pipeline.dataset import CLASS_NAMES, write_dataset_yaml

    out = tmp_path / "ds"
    out.mkdir()
    yaml_path = write_dataset_yaml(out)
    assert yaml_path == out / "dataset.yaml" and yaml_path.is_file()
    felso, nevek = _yaml_sorok(yaml_path)
    assert felso == {"path": str(out.resolve()), "train": "images/train",
                     "val": "images/val"}
    assert nevek == CLASS_NAMES == {0: "person", 1: "ball"}
    assert yaml_path.read_text(encoding="utf-8").endswith("\n")


def test_write_dataset_yaml_relativ_mappabol_is_abszolut_utat_ir(
        tmp_path, monkeypatch):
    """Relatív kimeneti mappánál is abszolút `path:` kerül a fájlba (a
    tanítás más munkakönyvtárból is megtalálja), és az ismételt írás
    felülír — nem fűz hozzá."""
    from pathlib import Path

    from handball.pipeline.dataset import write_dataset_yaml

    (tmp_path / "rel_ds").mkdir()
    monkeypatch.chdir(tmp_path)
    elso = write_dataset_yaml(Path("rel_ds"))
    felso, _ = _yaml_sorok(elso)
    assert Path(felso["path"]).is_absolute()
    assert Path(felso["path"]) == (tmp_path / "rel_ds").resolve()
    tartalom = elso.read_text(encoding="utf-8")
    assert write_dataset_yaml(Path("rel_ds")).read_text(
        encoding="utf-8") == tartalom
    assert tartalom.count("names:") == 1


def test_write_dataset_yaml_hianyzo_mappaba_nem_ir(tmp_path):
    """A függvény nem hoz létre mappát: nem létező kimeneti mappánál
    hibát jelez (a gyűjtő hozza létre a szerkezetet), kóbor fájl nélkül."""
    import pytest

    from handball.pipeline.dataset import write_dataset_yaml

    hianyzik = tmp_path / "nincs_ilyen"
    with pytest.raises(FileNotFoundError):
        write_dataset_yaml(hianyzik)
    assert not hianyzik.exists()


def test_collect_yaml_a_megirt_szerkezetre_mutat(tmp_path):
    """A gyűjtés végén megírt dataset.yaml útjai a TÉNYLEGESEN létrejött
    mappákra mutatnak, és a statisztika yaml_path mezője ez a fájl."""
    from pathlib import Path

    video = tmp_path / "meccs.mp4"
    _make_video(video)
    stats = collect_dataset(video, _stub_detect, tmp_path / "ds", samples=20)
    yaml_path = Path(stats.yaml_path)
    assert yaml_path == tmp_path / "ds" / "dataset.yaml"
    felso, nevek = _yaml_sorok(yaml_path)
    gyoker = Path(felso["path"])
    assert (gyoker / felso["train"]).is_dir()
    assert (gyoker / felso["val"]).is_dir()
    assert set(nevek) == {0, 1}
