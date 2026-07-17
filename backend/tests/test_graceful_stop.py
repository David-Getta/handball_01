"""
Tesztek a feldolgozás szelíd megszakítására (stop_check).

A Megszakítás korábban kivétellel kilépett, és MINDEN addig feldolgozott
kocka elveszett — órákig tartó teljes-félidős futásnál ez volt az MVP
legfájóbb megbízhatósági hibája. Az új viselkedés: a detektálás megáll,
de az utómunka lefut, és a részleges Match elmentődik.

A tesztek a HOG-útvonalat használják (weights=None) — nincs modell-
letöltés, egy pici szintetikus videó elég.

Futtatás:
    python -m pytest tests/test_graceful_stop.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

cv2 = pytest.importorskip("cv2", reason="OpenCV nincs telepítve")
np = pytest.importorskip("numpy", reason="numpy nincs telepítve")

from handball.models.tracking import Match  # noqa: E402
from scripts.process_video import process  # noqa: E402


def _tiny_video(path, frames=30, w=96, h=64):
    """Pici, világos (nem "sötét-kihagyós") szintetikus videó."""
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"),
                         25.0, (w, h))
    rng = np.random.default_rng(1)
    for _ in range(frames):
        img = rng.integers(90, 200, size=(h, w, 3), dtype=np.uint8)
        vw.write(img)
    vw.release()


def test_stop_check_yields_partial_match(tmp_path):
    video = tmp_path / "mini.mp4"
    _tiny_video(video, frames=30)

    calls = {"n": 0}

    def stop_after_5():
        calls["n"] += 1
        return calls["n"] > 5  # az 5. ellenőrzés után kérünk leállást

    m = process(str(video), None, weights=None, stride=1, max_frames=100,
                stop_check=stop_after_5)
    assert isinstance(m, Match)
    # Részleges, de NEM üres: a leállításig feldolgozott kockák megvannak,
    # és az utómunka is lefutott (érvényes meta, fps).
    assert 0 < len(m.frames) <= 6
    assert m.meta.fps > 0


def test_without_stop_check_processes_all(tmp_path):
    video = tmp_path / "mini2.mp4"
    _tiny_video(video, frames=20)
    m = process(str(video), None, weights=None, stride=1, max_frames=100)
    assert len(m.frames) == 20  # a teljes videó feldolgozva


def test_immediate_stop_gives_empty_match(tmp_path):
    """Azonnali leállítás: üres (0 kockás) Match — a hívó dönt a sorsáról
    (a szerver ilyenkor nem menti el, "cancelled" státusszal zár)."""
    video = tmp_path / "mini3.mp4"
    _tiny_video(video, frames=10)
    m = process(str(video), None, weights=None, stride=1, max_frames=100,
                stop_check=lambda: True)
    assert isinstance(m, Match)
    assert len(m.frames) == 0
