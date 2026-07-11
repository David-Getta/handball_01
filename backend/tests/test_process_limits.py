"""A feldolgozás plafon- és megszakítás-viselkedésének tesztjei.

Két, éles használatban kritikus tulajdonságot rögzítenek:
 1. max_frames = 0 (az API alapértéke) a TELJES videót jelenti — nincs
    rejtett 400-kockás plafon, ami egy igazi félidőt megcsonkítana.
 2. A progress_cb-ből dobott kivétel megszakítja a feldolgozást — erre épül
    a szerver "job cancel" mechanizmusa (a cb a cancel-jelzőnél dob).
"""
import numpy as np
import pytest

from scripts.process_video import _normalize_max_frames, _process_hog, process


def test_normalize_max_frames_zero_means_whole_video():
    assert _normalize_max_frames(0) == 10 ** 9
    assert _normalize_max_frames(None) == 10 ** 9
    assert _normalize_max_frames(-5) == 10 ** 9


def test_normalize_max_frames_positive_kept():
    assert _normalize_max_frames(400) == 400
    assert _normalize_max_frames(7) == 7


def _tiny_video(path, frames=8, w=320, h=240):
    """Pár kockás, zajos teszt-videó (MJPG/AVI — a headless OpenCV is írja)."""
    import cv2
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 25.0, (w, h))
    assert vw.isOpened(), "a teszt-videó írása nem indult el"
    rng = np.random.default_rng(0)
    for _ in range(frames):
        vw.write(rng.integers(60, 200, size=(h, w, 3), dtype=np.uint8))
    vw.release()


def test_hog_without_cap_reads_whole_video(tmp_path):
    v = tmp_path / "t.avi"
    _tiny_video(v, frames=8)
    raw, _ = _process_hog(str(v), stride=1, max_frames=_normalize_max_frames(0))
    assert len(raw) == 8  # minden kocka feldolgozva, nincs csonkítás


def test_hog_cap_still_limits(tmp_path):
    v = tmp_path / "t.avi"
    _tiny_video(v, frames=8)
    raw, _ = _process_hog(str(v), stride=1, max_frames=3)
    assert len(raw) == 3  # a kifejezett plafon továbbra is érvényesül


def test_progress_cb_exception_aborts_processing():
    """A cb-ből dobott kivétel kifelé terjed — így működik a megszakítás."""

    class Stop(Exception):
        pass

    def cb(stage, prog, msg):
        raise Stop()

    with pytest.raises(Stop):
        # Nem létező fájl is jó: az első haladás-jelzés a videó-adatok
        # beolvasása után, de a tényleges feldolgozás ELŐTT történik.
        process("/nonexistent/video.mp4", None, progress_cb=cb)
