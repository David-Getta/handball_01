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


def test_lendites_kovetessel_gyors_karmozdulatot_lat():
    """Egy ember két egymást követő mintán: a csukló a fej fölül a váll alá csap."""
    from hbd.shot_detect import swing_features

    kps = np.zeros((2, 17, 3), np.float32)
    kps[..., 2] = 0.9
    for k in range(2):
        kps[k, 5, :2] = (0.48, 0.40)   # bal váll
        kps[k, 6, :2] = (0.52, 0.40)   # jobb váll
    kps[0, 10, :2] = (0.53, 0.30)      # jobb csukló a váll fölött
    kps[1, 10, :2] = (0.55, 0.48)      # 0.2 s múlva a váll alatt
    pose = {"n": np.array([1, 1]), "offsets": np.array([0, 1, 2]), "kps": kps,
            "boxes": np.array([[0.45, 0.3, 0.55, 0.7]] * 2, np.float32), "t": np.array([0.0, 0.2]),
            "size": np.array([1920, 1080])}
    F, names = swing_features(pose)
    assert F[0].sum() == 0
    assert F[1, names.index("csuklo_seb_fentrol_max")] > 1.0
    assert F[1, names.index("kar_lecsapas_max")] > 1.0
    assert F[1, names.index("kovetett_db")] == 1


def test_kovetes_nem_parosit_tavoli_embert():
    from hbd.shot_detect import _match_people

    prev = np.array([[100.0, 100.0], [900.0, 500.0]])
    cur = np.array([[110.0, 105.0], [400.0, 400.0]])
    assert _match_people(prev, cur, np.array([100.0, 100.0])) == [(0, 0)]


def test_eredmenyjelzo_jelenlet_es_allasvaltozas():
    from hbd.broadcast import score_change, scoreboard_presence

    rng = np.random.default_rng(1)
    board = rng.integers(0, 255, (24, 60)).astype(np.uint8)
    static = np.stack([board if i % 4 else rng.integers(0, 255, (24, 60)).astype(np.uint8) for i in range(80)])
    ncc = scoreboard_presence(static)
    assert (ncc[1::4] > 0.99).all() and (ncc[::4] < 0.5).all()
    digits = np.zeros((6, 24, 12), np.uint8)
    digits[3:] = 200                    # a 3. mintán változik az állás
    present = np.ones(6, bool)
    d = score_change(digits, present)
    assert d.argmax() == 3 and d[[1, 2, 4, 5]].max() == 0
    present[2] = False                  # ha az egyik oldalon nem látszik a grafika: nem gól
    assert score_change(digits, present)[3] == 0


def test_kozvetitesi_jelek_igazitasa_es_jellemzok():
    from hbd.broadcast import align
    from hbd.shot_detect import build_features

    pose = _fake_pose()
    pose["frame"] = np.arange(50) * 5
    bc = {"frame": np.arange(0, 300, 5), "sb_ncc": np.ones(60, np.float32), "sb_change": np.zeros(60, np.float32),
          "cam_dx": np.full(60, 0.01, np.float32), "cam_dy": np.zeros(60, np.float32),
          "cam_resp": np.ones(60, np.float32)}
    a = align(pose["frame"], bc)
    assert a["cam_dx"].shape == (50,) and np.allclose(a["cam_dx"], 0.01)
    F, names, X, xn = build_features(pose, bc)
    assert "allas_valtozas" in names and any(n.startswith("allas_valtozas@+5.0") for n in xn)
    assert X.shape == (50, len(xn)) and np.isfinite(X).all()


def test_palya_szuro_a_padlo_szinet_tanulja_es_szur():
    from hbd.court import filter_pose, floor_colors, on_court

    rng = np.random.default_rng(0)
    floor = np.array([150, 120, 100], np.float32)
    colors = np.concatenate([floor + rng.normal(0, 3, (80, 3)), rng.uniform(0, 255, (20, 3))]).astype(np.float32)
    keep = on_court(colors, floor_colors(colors))
    assert keep[:80].mean() > 0.95 and keep[80:].mean() < 0.3
    pose = _fake_pose(10)
    keep = np.zeros(len(pose["boxes"]), bool)
    keep[::2] = True
    f = filter_pose(pose, keep)
    assert f["n"].sum() == keep.sum() and f["offsets"][-1] == keep.sum() and len(f["kps"]) == keep.sum()


def test_uj_meccs_jeloltek_a_meccsjelolo_formatumaban():
    from hbd.shot_detect import candidates_doc

    t = np.arange(0, 60, 0.2)
    score = np.zeros_like(t)
    score[[50, 51, 200]] = [0.9, 0.8, 0.6]
    doc = candidates_doc(t, score, 0.5, "m2")
    ev = doc["esemenyek"]
    # a két szomszédos csúcsból egy jelölt; a nyomás = lövés + reakcióidő, mint az embernél
    assert [e["t"] for e in ev] == [round(t[50] + REACTION_S, 2), round(t[200] + REACTION_S, 2)]
    assert all(e["tipus"] == "loves" and e["gepi"] for e in ev)


def test_rogzitett_modell_osszevetese_az_emberi_jelolessel():
    from hbd.shot_detect import score_against

    t = np.arange(0, 120, 0.2)
    score = np.zeros_like(t)
    score[[100, 300, 500]] = 0.9  # 20 s, 60 s, 100 s
    res = score_against(t, score, [{"t": 20.3}, {"t": 60.0}, {"t": 80.0}])
    c = next(c for c in res["gorbe"] if c["kuszob"] == 0.5)
    assert (c["talalt"], c["teves"], c["kihagyott"]) == (2, 1, 1)


def test_josolt_kuszob_a_cel_felidezeshez_es_hianyzo_kozvetites():
    import pytest

    from hbd.shot_detect import make_bundle, predict

    curve = [{"kuszob": 0.3, "felidezes": 0.9, "teves_per_perc": 2.0}, {"kuszob": 0.5, "felidezes": 0.82,
              "teves_per_perc": 0.8}, {"kuszob": 0.7, "felidezes": 0.6, "teves_per_perc": 0.1}]
    b = make_bundle({"gorbe": curve, "legjobb": curve[2], "model": None, "features": []},
                    swing=True, broadcast=True, court=False)
    assert b["kuszob"] == 0.5
    with pytest.raises(ValueError):
        predict({"t": np.zeros(1)}, b, None)
