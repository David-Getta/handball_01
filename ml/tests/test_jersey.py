"""Mezszám-azonosítás: törzs-kivágás és a csapat-színre szűrt rangsor."""

import numpy as np

from hbd.jersey import rank_numbers, torso_boxes


def test_torzs_kivagas_es_meretkorlat():
    kp = np.zeros((2, 17, 3), np.float32)
    # nagy ember: vállak y=0,4, csípők y=0,5 → 108 px magas törzs
    for i, (x, y) in {5: (0.40, 0.40), 6: (0.45, 0.40), 11: (0.41, 0.50), 12: (0.44, 0.50)}.items():
        kp[0, i] = (x, y, 0.9)
    # kicsi ember: 11 px → kimarad
    for i, (x, y) in {5: (0.10, 0.40), 6: (0.11, 0.40), 11: (0.10, 0.41), 12: (0.11, 0.41)}.items():
        kp[1, i] = (x, y, 0.9)
    b = torso_boxes(kp, 1920, 1080)
    assert b[1] is None
    x0, y0, x1, y1 = b[0]
    assert x0 < 0.40 * 1920 < 0.45 * 1920 < x1 and y0 < 0.40 * 1080 and y1 == 540


def test_rangsor_csak_a_csapat_szinen_es_a_keretbol():
    centers = np.array([[200, 128, 128], [80, 100, 150]], np.float32)   # világos mez, sötét mez
    recs = [
        {"szin": [198, 128, 128], "olvasat": [(19, 0.9)]},
        {"szin": [201, 127, 129], "olvasat": [(19, 0.8), (77, 0.9)]},   # 77 nincs a keretben
        {"szin": [82, 101, 149], "olvasat": [(10, 0.99)]},              # a másik csapat színén
    ]
    rk = rank_numbers(recs, centers, 0, {10, 19, 17})
    assert rk == [(19, 1.7000000000000002)]
    assert [n for n, _ in rank_numbers(recs, centers, None, {10, 19, 17})] == [19, 10]
