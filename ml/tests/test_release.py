"""A tanított lövés-profil csövei szintetikus adaton."""

import numpy as np

from hbd.release import ReleaseNet, arm_hand_features, frame_features, load_labels
from tests.test_features_goalkeeper import _clip


def test_jelolesek_beolvasasa_kihagyja_a_rossz_klipet(tmp_path):
    p = tmp_path / "c.csv"
    p.write_text("klip,kategoria,fps,klip_kockak,elengedes,kartartas,lovokez,zona,kimenet,rossz\n"
                 "a,shot,30,40,25,fent,jobb,,nem_latszik,False\n"
                 "b,shot,30,40,,,,,nem_latszik,True\n")
    lab = load_labels(p)
    assert list(lab) == ["a"] and lab["a"]["elengedes"] == 25


def test_jellemzok_alakja_es_vegessege():
    kps, boxes, fps = _clip()
    F = frame_features(kps, boxes, fps)
    assert F.shape[0] == len(kps) and np.isfinite(F).all()
    a = arm_hand_features(kps, boxes, fps, 25)
    assert a.ndim == 1 and np.isfinite(a).all()


def test_az_elengedes_halo_megtanulja_a_csuklo_csucsot():
    # a lövés kockája (a csukló-ugrás) klipenként máshol van; a háló találja meg
    X, y, fps = [], [], []
    rng = np.random.default_rng(0)
    for i in range(40):
        T = 40
        kps, boxes, f = _clip(T=T)
        r = int(rng.integers(10, 30))
        kps = np.roll(kps, r - 25, axis=0)  # a _clip a 25. kockán "lő"
        X.append(frame_features(kps, boxes, f))
        y.append(r)
        fps.append(f)
    net = ReleaseNet(epochs=40, seed=0).fit(X[:30], np.array(y[:30]), np.array(fps[:30]))
    err = np.abs(net.predict(X[30:]) - np.array(y[30:]))
    assert np.median(err) <= 2
