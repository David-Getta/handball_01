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


def test_yolo_stall_guard_saves_partial(tmp_path, monkeypatch):
    """Ha a kocka-generátor beragad (nem ad több kockát), az elakadás-védő
    időkorláttal kilép, és a már feldolgozott kockák megmaradnak — a
    visszatérési érték jelzi a beragadást."""
    import sys
    import types

    import scripts.process_video as pv

    class _Boxes:
        pass

    class _FakeResult:
        def __init__(self):
            self.orig_img = np.full((64, 96, 3), 150, dtype=np.uint8)
            self.boxes = None

    class _FakeModel:
        names = {0: "person", 32: "sports ball"}

        def __init__(self, *_a, **_k):
            pass

        def track(self, **_kw):
            def gen():
                for _ in range(3):
                    yield _FakeResult()
                import threading
                threading.Event().wait(9999)  # beragadt olvasó szimulálása
            return gen()

    fake_ultra = types.ModuleType("ultralytics")
    fake_ultra.YOLO = _FakeModel
    monkeypatch.setitem(sys.modules, "ultralytics", fake_ultra)

    w = tmp_path / "w.pt"
    w.write_bytes(b"x" * 2048)  # létező "súlyfájl" a feloldáshoz
    monkeypatch.setattr(pv, "_resolve_weights", lambda _w: str(w))

    # Rövid időkorlát a teszthez: a STALL_ABORT_S modulon belüli konstans —
    # a Queue.get timeoutját a gyors futásért kicsire vesszük.
    import queue as queue_mod
    real_queue = queue_mod.Queue

    class _FastQueue(real_queue):
        def get(self, block=True, timeout=None):
            if timeout is not None and timeout > 1:
                timeout = 0.5
            return super().get(block=block, timeout=timeout)

    monkeypatch.setattr(queue_mod, "Queue", _FastQueue)

    raw, colors = [], []
    stalled = pv._process_yolo(
        "nem-letezo.mp4", str(w), stride=1, max_frames=100, imgsz=640,
        conf=0.2, raw_out=raw, colors_out=colors)
    assert stalled is True
    assert len(raw) == 3  # a beragadás előtti kockák megvannak
