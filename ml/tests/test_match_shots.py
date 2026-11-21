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


class _FakeModel:
    """Kivágásonként az egyetlen "embert" adja vissza, ha a kivágásba esik (a teljes kép koordinátáiban mozog)."""

    def __init__(self, path):
        self.path, self.f, self.crops = path, 0, []

    def __call__(self, crops):
        return [self._one(c) for c in crops]

    def _one(self, crop):
        x0, y0 = crop.ox, crop.oy
        b = self.path[crop.f]
        lb = np.array([[b[0] - x0, b[1] - y0, b[2] - x0, b[3] - y0]], np.float32)
        if lb[0, 0] < 0 or lb[0, 1] < 0 or lb[0, 2] > crop.shape[1] or lb[0, 3] > crop.shape[0]:
            return np.zeros((0, 4), np.float32), np.zeros((0, 17, 3), np.float32)
        k = np.zeros((1, 17, 3), np.float32)
        k[0, :, 0], k[0, :, 1], k[0, :, 2] = (lb[0, 0] + lb[0, 2]) / 2, np.linspace(lb[0, 1], lb[0, 3], 17), 0.9
        return lb, k


def test_rakozelito_koveto_vegigviszi_a_kicsi_lovot(monkeypatch):
    import hbd.match_shots as ms

    path = [[900 + 4 * f, 500, 930 + 4 * f, 580] for f in range(12)]   # 80 px magas, jobbra fut

    class Img(np.ndarray):
        pass

    frames = []
    for f in range(12):
        im = np.zeros((1080, 1920, 3), np.uint8).view(Img)
        im.f = f
        frames.append(im)

    real = ms._zoom_detect

    def fake_detect(model, img, cx, cy, side):
        h, w = img.shape[:2]
        x0, y0 = int(max(0, cx - side / 2)), int(max(0, cy - side / 2))
        crop = img[y0:int(min(h, cy + side / 2)), x0:int(min(w, cx + side / 2))].view(Img)
        crop.f, crop.ox, crop.oy = img.f, x0, y0
        db, dk = model([crop])[0]
        if len(db):
            db = db + [x0, y0, x0, y0]
            dk[..., 0] += x0
            dk[..., 1] += y0
        return db, dk

    monkeypatch.setattr(ms, "_zoom_detect", fake_detect)
    tr = ms.zoom_track(frames, 6, 925, 540, _FakeModel(path), 25.0)
    assert real is not None and tr["start"] == 0 and len(tr["kps"]) == 12
    assert np.allclose(tr["boxes"][11], path[11])


def test_kivagas_koordinatai_visszakerulnek_a_teljes_kepre():
    from hbd.match_shots import _zoom_detect

    seen = {}

    def model(crops):
        seen["shape"] = crops[0].shape
        k = np.zeros((1, 17, 3), np.float32)
        k[0, :, :2] = (10, 20)
        return [(np.array([[10, 20, 30, 60]], np.float32), k)]

    db, dk = _zoom_detect(model, np.zeros((1080, 1920, 3), np.uint8), 1000, 500, 300)
    assert seen["shape"] == (300, 300, 3)
    assert np.allclose(db[0], [860, 370, 880, 410]) and np.allclose(dk[0, 0, :2], [860, 370])
