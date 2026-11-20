"""A meccs-lövésprofil csövei szintetikus adaton."""

import json

import numpy as np

from hbd.match_shots import (arm_class, candidate_features, load_labels, pick_clicked, replay_groups,
                             split_zone, track_shooter)


def _pose(frames):
    """frames: kockánként a dobozok listája → a kinyerés formátuma (testpontok a dobozban)."""
    n = [len(f) for f in frames]
    boxes = np.array([b for f in frames for b in f], np.float32).reshape(-1, 4)
    kps = np.zeros((len(boxes), 17, 3), np.float32)
    for i, b in enumerate(boxes):
        kps[i, :, 0] = (b[0] + b[2]) / 2
        kps[i, :, 1] = np.linspace(b[1], b[3], 17)
        kps[i, :, 2] = 0.9
    return {"n": np.array(n), "offsets": np.concatenate([[0], np.cumsum(n)]), "boxes": boxes, "kps": kps,
            "fps": np.float32(25), "size": np.array([1920, 1080])}


def test_kattintott_ember_es_kozeli_tipp():
    boxes = np.array([[100, 100, 150, 250], [400, 100, 450, 250]], np.float32)
    assert pick_clicked(boxes, 120, 150) == 0
    assert pick_clicked(boxes, 425, 95) == 1          # a fej fölé kattintva is (a doboz széle mellett)
    assert pick_clicked(boxes, 900, 900) is None


def test_koveto_atugorja_a_rovid_kiesest_es_nem_ugrik_masra():
    frames = []
    for f in range(20):
        lovo = [100 + 3 * f, 100, 150 + 3 * f, 250]
        masik = [600, 100, 650, 250]
        frames.append([masik] if f in (8, 9) else [lovo, masik])   # a lövő két kockán nem látszik
    p = _pose(frames)
    tr = track_shooter(p, 10, 135, 150)
    assert tr["start"] == 0 and len(tr["kps"]) == 20
    assert np.allclose(tr["boxes"][15], [145, 100, 195, 250])
    assert (tr["kps"][8, :, 2] == 0).all()              # a kiesett kockán "nem látszik"


def test_ismetles_az_elo_parjaval_egy_csoportban():
    clips = [{"id": "a", "t_video": 100.0}, {"id": "a_ism", "t_video": 130.0, "ismetles": True},
             {"id": "b", "t_video": 200.0}, {"id": "c_ism", "t_video": 500.0, "ismetles": True}]
    g = replay_groups(clips)
    assert g == {"a": "a", "a_ism": "a", "b": "b", "c_ism": "c_ism"}


def test_zona_es_kartartas_besorolas():
    assert split_zone("lent-jobb") == (0, 2) and split_zone("kozep") == (1, 1) and split_zone(None) == (None, None)
    assert arm_class("fej_mellett") == "oldalt" and arm_class("fent") == "fent"


def test_cimkek_betoltese_kihagyja_a_rossz_klipet(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({"klip": "a", "elengedes": 10, "lovo": {"k": 10, "x": .5, "y": .5},
                                                 "rossz": False, "kartartas": "fent", "lovokez": "jobb"}))
    (tmp_path / "b.json").write_text(json.dumps({"klip": "b", "elengedes": None, "lovo": None, "rossz": True}))
    assert list(load_labels(tmp_path)) == ["a"]


def test_lovo_jelolt_jellemzok():
    frames = [[[100, 100, 150, 250], [400, 100, 440, 200]] for _ in range(15)]
    p = _pose(frames)
    X, boxes = candidate_features(p, 7)
    assert X.shape == (2, 9) and np.isfinite(X).all()
    assert X[0, 3] == 1.0 and X[1, 3] < 1.0             # a legnagyobb doboz aránya 1
