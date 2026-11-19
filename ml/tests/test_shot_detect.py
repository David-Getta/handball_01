"""A lövésfelismerő csövei szintetikus "meccsen"."""

import numpy as np

from hbd.shot_detect import (REACTION_S, frame_features, labels, match_events, pick_peaks,
                             shot_times, window_features)


def test_lovesek_parositasa_es_reakcioido():
    doc = {"esemenyek": [
        {"t": 10.0, "tipus": "loves"}, {"t": 10.4, "tipus": "loves", "eredmeny": "gol"},
        {"t": 20.0, "tipus": "loves"}, {"t": 20.3, "tipus": "loves", "eredmeny": "vedes"},
        {"t": 22.0, "tipus": "loves", "kipattano": True}, {"t": 22.3, "tipus": "loves", "eredmeny": "gol"},
        {"t": 30.0, "tipus": "passz"},
        {"t": 40.0, "tipus": "loves", "ismetles": True}, {"t": 40.5, "tipus": "loves", "eredmeny": "gol", "ismetles": True},
    ]}
    s = shot_times(doc)
    assert [round(x["t"], 2) for x in s] == [10 - REACTION_S, 20 - REACTION_S, 22 - REACTION_S, 40 - REACTION_S]
    assert [x["eredmeny"] for x in s] == ["gol", "vedes", "gol", "gol"]
    assert len(shot_times(doc, include_replays=False)) == 3


def test_cimkek_pozitiv_bizonytalan_negativ():
    t = np.arange(0, 20, 0.2)
    y = labels(t, [{"t": 10.0}])
    assert y[np.argmin(np.abs(t - 10))] == 1
    assert y[np.argmin(np.abs(t - 11.2))] == -1
    assert y[0] == 0


def test_csucskereses_es_parositas():
    t = np.arange(0, 60, 0.2)
    score = np.zeros_like(t)
    for c in (10, 30, 45):
        score[np.argmin(np.abs(t - c))] = 0.9
    score[np.argmin(np.abs(t - 10.4))] = 0.8  # ugyanaz a lövés: MIN_GAP_S-en belül
    pred = pick_peaks(t, score, 0.5)
    assert len(pred) == 3
    tp, fp, fn = match_events(pred, np.array([10.3, 30.5, 50.0]))
    assert (tp, fp, fn) == (2, 1, 1)


def _fake_pose(n_samples=50):
    rng = np.random.default_rng(0)
    n = rng.integers(0, 5, n_samples)
    tot = int(n.sum())
    kps = rng.uniform(0.2, 0.8, (tot, 17, 3)).astype(np.float16)
    kps[..., 2] = 0.9
    boxes = np.tile(np.array([[0.4, 0.3, 0.5, 0.6]], np.float16), (tot, 1))
    return {"n": n, "offsets": np.concatenate([[0], np.cumsum(n)]), "kps": kps, "boxes": boxes,
            "motion": rng.uniform(0, 5, n_samples).astype(np.float32),
            "t": np.arange(n_samples) * 0.2}


def test_jellemzok_alakja_ures_kockaval_is():
    pose = _fake_pose()
    F, names = frame_features(pose)
    assert F.shape == (50, len(names)) and np.isfinite(F).all()
    assert (F[pose["n"] == 0, 0] == 0).all()
    X, xn = window_features(F, pose["t"], names)
    assert X.shape[0] == 50 and X.shape[1] == len(xn) and np.isfinite(X).all()
