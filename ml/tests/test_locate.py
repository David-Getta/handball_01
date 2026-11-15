"""A klip-visszakeresés szintetikus jeleneten: ismert eltolás és pálya."""

import numpy as np

from hbd.locate import find_offset, track


def _scene(n=30, h=240, w=320, seed=0):
    rng = np.random.default_rng(seed)
    bg = rng.integers(0, 255, (h, w), dtype=np.uint8)
    patch = rng.integers(0, 255, (40, 20), dtype=np.uint8)
    frames, boxes = [], []
    for i in range(n):
        f = bg.copy()
        # a "játékos" mozog, és a háttér picit remeg (mint álló kameránál)
        x, y = 50 + 4 * i, 80 + i
        f[y:y + 40, x:x + 20] = np.roll(patch, 3 * i, axis=0)  # a mozdulat kockánként változik
        f = np.clip(f.astype(int) + rng.integers(-2, 3, f.shape), 0, 255).astype(np.uint8)
        frames.append(f)
        boxes.append((x, y, x + 20, y + 40))
    return frames, boxes


def test_eltolas_es_kovetes_pontos():
    frames, boxes = _scene()
    off = 7
    # a klip: a jelenet kivágása az eltolástól kezdve (szó szerinti képpontok)
    action = np.stack([frames[off + k][b[1]:b[3], b[0]:b[2]]
                       for k, b in enumerate(boxes[off:off + 15])])
    found, score = find_offset(iter(frames), action[0])
    assert found == off and score > 0.999
    out = list(track(iter(frames), action, found))
    assert len(out) == 15
    for k, _fr, box, sc in out:
        assert box == boxes[off + k]
        assert sc > 0.999


def test_a_jelenet_vegen_megall():
    frames, boxes = _scene(n=12)
    action = np.stack([frames[5 + k][b[1]:b[3], b[0]:b[2]] for k, b in enumerate(boxes[5:12])])
    action = np.concatenate([action, action[-1:].repeat(5, 0)])  # hosszabb, mint a jelenet maradéka
    out = list(track(iter(frames), action, 5))
    assert len(out) == 7
