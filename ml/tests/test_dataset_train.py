"""Adathalmaz-bejárás és a kiértékelés csövei (szintetikus adattal)."""

import json

import numpy as np

from hbd.dataset import TASKS, index_dataset, read_detections
from hbd.pose import iou, pick_person, save_dataset, square_crop_box
from hbd.train import group_folds, main as train_main


def test_bejaras_es_arva_klip(tmp_path):
    root = tmp_path / "x" / "handball_s"
    for sub in ("actions/shot", "scenes/shot", "player_detections/shot", "actions/passing",
                "scenes/passing"):
        (root / sub).mkdir(parents=True)
    (root / "actions/shot/shot_KS_1_act1.avi").write_bytes(b"")
    (root / "actions/shot/shot_KS_1_act2.avi").write_bytes(b"")
    (root / "scenes/shot/shot_KS_1.mp4").write_bytes(b"")
    (root / "player_detections/shot/shot_KS_1.csv").write_text("Frame 1\n1, 2, 3, 4, 0.9\n")
    (root / "actions/passing/passing_KS_9_act1.avi").write_bytes(b"")  # árva: nincs jelenet
    clips = index_dataset(tmp_path)
    assert [c.name for c in clips] == ["shot_KS_1_act1", "shot_KS_1_act2"]
    assert clips[0].scene_id == clips[1].scene_id == "shot/shot_KS_1"
    assert read_detections(clips[0].detections_path) == [[(1.0, 2.0, 3.0, 4.0, 0.9)]]


def test_feladat_cimkek():
    names, m = TASKS["binary"]
    assert m["shot"] == m["jump-shot"] == 1 and m["passing"] == 0
    names, m = TASKS["shot3"]
    assert names[m["jump-shot"]] == "felugrasos" and names[m["shot"]] == "helybol"


def test_kivagas_es_szemelyvalasztas():
    x0, y0, x1, y1 = square_crop_box((100, 100, 120, 160), 1920, 1080)
    assert x1 - x0 == y1 - y0 == 96
    assert square_crop_box((0, 0, 20, 60), 1920, 1080)[:2] == (0, 0)
    dets = np.array([[0, 0, 10, 10], [98, 99, 121, 158]], float)
    assert pick_person(dets, (100, 100, 120, 160)) == 1
    assert pick_person(dets[:1], (100, 100, 120, 160)) is None
    assert iou((0, 0, 10, 10), (0, 0, 10, 10)) == 1.0


def test_csoportos_felosztas_nem_szivarog():
    rng = np.random.default_rng(0)
    groups = np.repeat(np.arange(40), 2)
    y = (groups % 3 == 0).astype(int)
    for tr, te in group_folds(y, groups, 5, 0):
        assert not set(groups[tr]) & set(groups[te])
    _ = rng


def _fake_clip(cat, t, rng):
    """Lövés: a jobb csukló a végén magasra és gyorsan; egyéb: lóg a kar."""
    from tests.test_features_goalkeeper import _clip

    kps, boxes, fps = _clip(T=30 + t % 7, throw_right=True, raise_to=-30 if cat == "shot" else 30)
    kps[..., :2] += rng.normal(0, 1.0, kps[..., :2].shape)
    if cat != "shot":
        kps[:, 10, :2] = kps[:, 8, :2] + [0, 15]  # a csukló a könyök alatt marad
    return kps, boxes, fps


def test_kiertekeles_vegig_fut_es_tanul(tmp_path):
    from hbd.dataset import Clip

    rng = np.random.default_rng(1)
    clips, results = [], []
    for i in range(60):
        cat = "shot" if i % 2 else "passing"
        kps, boxes, fps = _fake_clip(cat, i, rng)
        clips.append(Clip(f"{cat}_KS_{i // 2}_act1", cat, tmp_path / "a", tmp_path / f"{cat}_KS_{i // 2}.mp4", None))
        results.append({"kps": kps.astype(np.float32), "boxes": boxes.astype(np.float32),
                        "match": np.ones(len(kps), np.float32), "fps": fps, "frame_size": (1920, 1080)})
    p = tmp_path / "poses.npz"
    save_dataset(p, clips, results)
    out = tmp_path / "res"
    assert train_main(["--poses", str(p), "--out", str(out), "--tasks", "binary",
                       "--nn-epochs", "5", "--folds", "3"]) == 0
    res = json.loads((out / "results.json").read_text())
    m = res["tasks"]["binary"]["models"]
    assert m["majority"]["balanced_accuracy"] == 0.5
    assert m["hgb"]["balanced_accuracy"] > 0.9  # a különbség egyértelmű, meg kell tanulnia
    assert "tcn" in m
    assert (out / "results.md").exists() and (out / "model_binary_hgb.joblib").exists()
    assert res["goalkeeper"]["profil_db"] == 30
