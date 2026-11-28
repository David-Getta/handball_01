import numpy as np

from hbd.scoreboard import glyphs, read_state, stable_states, timeline


def test_idovonal_novekvo_es_kettos_lepes():
    r = [(10, 20, (0, 0)), (30, 40, (1, 0)), (50, 60, None), (70, 80, (1, 0)), (90, 95, (7, 7)),
         (100, 110, (2, 1)), (120, 130, (2, 2))]
    res = timeline(r)
    # a (7, 7) hibás olvasat (ugrás) kiesik; az (1,0)→(2,1) kettős lépés két gól
    assert res["vegeredmeny"] == [2, 2]
    assert len(res["golok"]) == 4 and len(res["elutasitott"]) == 1
    g = res["golok"][1]
    assert (g["t_tol"], g["t_ig"]) == (80, 100)


def test_stabil_allapot_animaciot_kihagy():
    t = np.arange(0, 20, 0.2)
    crops = np.zeros((len(t), 8, 8), np.uint8)
    crops[(t >= 8) & (t < 9)] = 200          # 1 s-os villanás: nem állapot
    crops[t >= 12] = 100
    st = stable_states(crops, t, np.ones(len(t), bool))
    # a villanás kiesik; a visszaállt kép (9–12 s) ugyanaz az állapot, mint az első
    assert [round(s[0]) for s in st] == [0, 9, 12]
    assert np.array_equal(st[0][2], st[1][2])


def test_szamjegyek_kiolvasasa_sablonnal():
    img = np.zeros((40, 80), np.uint8)
    img[5:35, 10:16] = 255                   # hazai: egy "1"-es (keskeny)
    img[5:35, 50:66] = 255                   # vendég: üreges téglalap (mint egy "0")
    img[10:30, 54:62] = 0
    img[5:35, 39:41] = 255                   # középső elválasztó: nem jel
    h, v = glyphs(img)
    assert len(h) == 1 and len(v) == 1
    centers = np.stack([h[0].ravel(), v[0].ravel()])
    assert read_state(img, centers, [1, 8]) == (1, 8)
