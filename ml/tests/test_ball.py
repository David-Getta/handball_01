import numpy as np

from hbd.ball import fuse, interpolate_points, track, track2


def _scene(T=14, v=5.0, d=10.0, gap_at=None):
    """Gyors, egyenletes labda (v átmérő/kocka) + kockánként MÁSHOL felbukkanó, a labdánál
    biztosabb téves folt (a valódi téves jelöltek ugrálnak); a labda egy kockán (gap_at) nem látszik."""
    rng = np.random.default_rng(0)
    cands, truth = [], []
    for t in range(T):
        bx, by = 50 + v * d * t, 300.0
        truth.append((bx, by))
        rows = [[rng.uniform(0, 640), rng.uniform(0, 200), d, 0.6]]  # ugráló téves jelölt
        if t != gap_at:
            rows.insert(0, [bx, by, d, 0.4])
        cands.append(np.array(sorted(rows, key=lambda r: -r[3])))
    return cands, truth


def _hits(path, truth, d=10.0):
    return [q is not None and np.hypot(q[0] - x, q[1] - y) <= 1.5 * d for q, (x, y) in zip(path, truth)]


def test_masodrendu_kovetes_a_mozgo_labdat_koveti_nem_az_ugralo_foltot():
    cands, truth = _scene()
    h = _hits(track2(cands), truth)
    assert sum(h) >= len(truth) - 1
    assert sum(_hits([c[0] for c in cands], truth)) == 0  # kockánként a legbiztosabb mindig téves


def test_masodrendu_kovetes_kieso_kockan_at_is_folytatja():
    cands, truth = _scene(gap_at=6)
    path = track2(cands)
    h = _hits(path, truth)
    assert path[6] is None or h[6]
    assert all(h[t] for t in range(len(truth)) if t != 6)


def test_osszefesules_a_sokkal_biztosabb_jeloltet_veszi():
    c = [np.array([[10.0, 10.0, 8.0, 0.9], [100.0, 100.0, 8.0, 0.1]])]
    q = c[0][1]
    assert fuse(c, [q], ratio=3.0)[0][0] == 10.0  # 0,9 > 3 × 0,1
    assert fuse(c, [None], ratio=3.0)[0][0] == 10.0  # a követés "nem látszik" → a kocka legjobbja
    c2 = [np.array([[10.0, 10.0, 8.0, 0.5], [100.0, 100.0, 8.0, 0.3]])]
    assert fuse(c2, [c2[0][1]], ratio=3.0)[0][0] == 100.0  # nem elég biztosabb → marad a követett


def test_elsorendu_kovetes_ures_bemenet():
    assert track([]) == [] and track2([]) == []


def test_koztes_kockak_kitoltese():
    pts = [{"nev": "kezben", "k": 10, "cx": 0.2, "cy": 0.5}, {"nev": "elvalik", "k": 13, "cx": 0.5, "cy": 0.2}]
    out = interpolate_points(pts)
    assert [p["k"] for p in out] == [11, 12]
    assert np.isclose(out[0]["cx"], 0.3) and np.isclose(out[1]["cy"], 0.3)
