import numpy as np

from hbd.shooter_ball import (flight_features, flight_from_path, inside, merge_points, person_scores,
                              pick_shooter, pose_lag, suppress_static, tile_origins)


def _person(cx, top, h=180.0, wrist=None):
    """Egy ember doboza és testpontjai; a csuklók (9, 10) a megadott helyen, különben a csípőnél."""
    box = np.array([cx - h / 4, top, cx + h / 4, top + h], np.float32)
    kp = np.zeros((17, 3), np.float32)
    kp[:, :2] = [cx, top + h / 2]
    kp[:, 2] = 0.9
    if wrist is not None:
        kp[10, :2] = wrist
    return box, kp


def _frame(*people):
    return np.stack([p[0] for p in people]), np.stack([p[1] for p in people])


def test_csempek_lefedik_a_kepet_atfedessel():
    o = tile_origins(1920, 1080, 640)
    xs, ys = sorted({x for x, _ in o}), sorted({y for _, y in o})
    assert xs[0] == 0 and xs[-1] == 1280 and ys[0] == 0 and ys[-1] == 440
    assert all(b - a < 640 for a, b in zip(xs, xs[1:]))  # átfedés: nincs rés


def test_osszevonas_a_biztosabbat_tartja():
    c = np.array([[100, 100, 15, 0.2], [105, 102, 15, 0.5], [400, 100, 15, 0.1]], np.float32)
    m = merge_points(c, 12)
    assert len(m) == 2 and m[0, 3] == np.float32(0.5)


def test_allo_jelolt_kiesik_a_mozgo_marad():
    static = [400.0, 900.0, 25.0, 0.3]
    balls = [np.array([static, [100 + 30 * i, 200, 15, 0.1]], np.float32) for i in range(5)]
    out = suppress_static(balls)
    assert all(len(b) == 1 and b[0, 0] != 400 for b in out)


def test_a_csuklohoz_kozeli_labda_ember_nyer():
    a = _person(300, 300, wrist=(330, 290))
    b = _person(800, 300, wrist=(820, 400))
    bx, kp = _frame(a, b)
    balls = np.array([[335, 285, 18, 0.1]], np.float32)  # 18 px ≈ 0,1 × 180
    s, bi = person_scores(bx, kp, balls)
    assert s[0] > 0.05 and s[1] < 1e-6 and bi[0] == 0


def test_rossz_meretu_labda_gyengebb():
    bx, kp = _frame(_person(300, 300, wrist=(330, 290)))
    good, _ = person_scores(bx, kp, np.array([[330, 290, 18, 0.1]], np.float32))
    big, _ = person_scores(bx, kp, np.array([[330, 290, 70, 0.1]], np.float32))
    assert good[0] > 2 * big[0]


def test_lovo_valasztas_tobb_kockan_es_tartalek_labdahely():
    a = _person(300, 300, wrist=(330, 290))
    b = _person(800, 300, wrist=(820, 400))
    people = [_frame(a, b)] * 3
    balls = [np.array([[332, 288, 18, 0.1]], np.float32)] * 3
    res = pick_shooter(people, balls, 1)
    assert res["index"] == 0 and inside(res["pont"], a[0])
    # ha embert nem lát a pózbecslő, a labda helye a lövő helye
    empty = [(np.zeros((0, 4), np.float32), np.zeros((0, 17, 3), np.float32))] * 3
    res = pick_shooter(empty, balls, 1)
    assert res["index"] is None and res["pont"] == (332.0, 288.0)


def test_hely_meres_dobozhoz_kozel():
    box = np.array([100, 100, 150, 300], np.float32)  # magasság 200 → 50 px tűrés
    assert inside((120, 200), box) and inside((190, 200), box) and not inside((260, 200), box)


def test_repules_a_kovetett_palyabol_es_jellemzok():
    path = [None, None, np.array([500, 400, 15, 0.2]), None, np.array([560, 380, 15, 0.1]),
            np.array([590, 370, 15, 0.1])]
    (sx, sy), ts, (fx, fy), tf = flight_from_path(path, 2)
    assert (ts, tf) == (2, 5) and (fx, fy) == (590.0, 370.0)
    f = flight_features((sx, sy), ts, (fx, fy), tf, np.array([450, 380, 520, 580]))
    assert f[0] > 0 and f[1] < 0  # jobbra és felfelé repül
    assert flight_from_path([None, np.array([1, 1, 1, 1]), None], 1) is None


def test_duplazott_elso_kocka_felismerese():
    b = np.array([[0, 0, 10, 10], [5, 5, 20, 20]], np.float32)
    dup = {"n": np.array([2, 2, 1]), "offsets": np.array([0, 2, 4, 5]),
           "boxes": np.concatenate([b, b, b[:1] + 1])}
    ok = {"n": np.array([2, 2, 1]), "offsets": np.array([0, 2, 4, 5]),
          "boxes": np.concatenate([b, b + 3, b[:1] + 1])}
    assert pose_lag(dup) == 1 and pose_lag(ok) == 0
