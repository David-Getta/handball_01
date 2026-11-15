"""Normalizálás, sorozat és kapus-profil szintetikus csontvázon."""

import numpy as np

from hbd.features import (FLIP_PERM, L_WR, R_WR, SEQ_CHANNELS, SEQ_LEN, clip_features,
                          fill_missing, flip_sequence, normalize, sequence)
from hbd.goalkeeper import shot_profile

# Álló ember (kép-koordináta, y lefelé), törzshossz = 40 px
BASE = np.array([
    [100, 20],                       # orr
    [97, 17], [103, 17], [94, 19], [106, 19],
    [90, 40], [110, 40],             # vállak (bal, jobb)
    [86, 60], [114, 60],             # könyökök
    [84, 78], [116, 78],             # csuklók
    [93, 80], [107, 80],             # csípők
    [92, 105], [108, 105],           # térdek
    [92, 130], [108, 130],           # bokák
], float)


def _clip(T=40, fps=30.0, throw_right=True, jump=False, raise_to=-30.0):
    """Lövés-szerű klip: a lövőkéz a 25. kockánál gyorsan, magasan mozdul."""
    kps = np.zeros((T, 17, 3))
    for t in range(T):
        p = BASE.copy()
        p[:, 0] += 2 * t  # halad a képen
        if jump and 18 <= t <= 30:
            p[:, 1] -= 25 * np.sin(np.pi * (t - 18) / 12)  # felugrás
        wr, sh = (R_WR, 6) if throw_right else (L_WR, 5)
        if 15 <= t <= 25:
            frac = (t - 15) / 10
            p[wr, 1] = p[sh, 1] + (BASE[wr, 1] - BASE[sh, 1]) * (1 - frac) + raise_to * frac
        if t == 25:
            p[wr, 0] += 40  # az elengedés: nagy csukló-sebesség
        kps[t, :, :2] = p
        kps[t, :, 2] = 0.9
    boxes = np.stack([kps[:, :, 0].min(1), kps[:, :, 1].min(1),
                      kps[:, :, 0].max(1), kps[:, :, 1].max(1)], 1)
    return kps, boxes, fps


def test_normalizalas_eltolas_es_meret_fuggetlen():
    kps, boxes, _ = _clip()
    rel1, _, _, s1 = normalize(kps, boxes)
    k2 = kps.copy()
    k2[..., :2] = k2[..., :2] * 2.5 + 300
    rel2, _, _, s2 = normalize(k2, boxes * 2.5 + 300)
    assert np.allclose(rel1, rel2, atol=1e-6)
    assert abs(s2 / s1 - 2.5) < 1e-6


def test_hianyzo_pont_potlasa():
    kps, _, _ = _clip(T=5)
    kps[2, L_WR, 2] = 0.0
    xy, valid = fill_missing(kps)
    assert not valid[2, L_WR]
    assert np.allclose(xy[2, L_WR], (kps[1, L_WR, :2] + kps[3, L_WR, :2]) / 2)


def test_sorozat_alak_es_tukrozes_ketszer_identitas():
    kps, boxes, _ = _clip()
    s = sequence(kps, boxes)
    assert s.shape == (SEQ_LEN, SEQ_CHANNELS)
    assert np.allclose(flip_sequence(flip_sequence(s)), s)
    assert sorted(FLIP_PERM) == list(range(17))


def test_jellemzok_vegesek():
    kps, boxes, fps = _clip()
    f = clip_features(kps, boxes, fps)
    assert len(f) > 30 and all(np.isfinite(v) for v in f.values())


def test_kapus_profil_jobbkezes_fent():
    p = shot_profile(*_clip(throw_right=True, raise_to=-30))
    assert p["lovokez"] == "jobb"
    assert p["kartartas"] == "fent"
    assert p["elengedes_kocka"] in (24, 25, 26)


def test_kapus_profil_balkezes_lent():
    p = shot_profile(*_clip(throw_right=False, raise_to=35))
    assert p["lovokez"] == "bal"
    assert p["kartartas"] == "lent"


def test_felugras_felismerese():
    assert shot_profile(*_clip(jump=True))["felugras"] is True
    assert shot_profile(*_clip(jump=False))["felugras"] is False


def test_keves_minta_none():
    kps, boxes, fps = _clip(T=5)
    assert shot_profile(kps, boxes, fps) is None
    kps, boxes, fps = _clip()
    kps[..., 2] = 0.05  # semmit sem látott a pózmodell
    assert shot_profile(kps, boxes, fps) is None
