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


def test_progress_cb_exception_aborts_processing(tmp_path):
    """A cb-ből dobott kivétel kifelé terjed — így működik a megszakítás.

    VALÓDI (pár kockás) videóval: a hiányzó fájl ma már korábban, saját
    hibával elszáll (lásd a következő tesztet), tehát azon nem lehetne
    a haladás-jelzést kipróbálni. Az első jelzés a videó-adatok
    beolvasása után, de a tényleges feldolgozás ELŐTT történik.
    """

    class Stop(Exception):
        pass

    def cb(stage, prog, msg):
        raise Stop()

    v = tmp_path / "t.avi"
    _tiny_video(v, frames=4)
    with pytest.raises(Stop):
        process(str(v), None, progress_cb=cb)


def test_hianyzo_video_azonnal_magyarul_szall_el():
    """A nem létező videó NE fusson bele a feldolgozásba.

    Korábban a nyers `cv2.VideoCapture` némán elbukott: az fps és a
    felbontás a tartalék értékekre esett vissza, és a feldolgozás
    elindult egy olyan videón, ami nincs is. A közös megnyitó ehelyett
    emberi magyar üzenettel áll meg — ez az üzenet jut el a
    felhasználóig.
    """
    from handball.video_io import VideoOpenError

    with pytest.raises(VideoOpenError) as exc:
        process("/nonexistent/video.mp4", None)
    assert "videó" in str(exc.value)


def test_yolo_stall_guard_saves_partial(tmp_path, monkeypatch):
    """Ha a kocka-generátor beragad (nem ad több kockát), az elakadás-védő
    az elakadt kockát ÁTUGORJA, és a folytató-olvasóval megy tovább — a
    már feldolgozott kockák megmaradnak. Itt a folytató sem talál több
    kockát (nem létező fájl), így a menet tisztán, beragadás-jelzés
    NÉLKÜL zárul: a feladás csak sok egymás utáni elakadásnál jár."""
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
    assert stalled is False  # átugrás után tisztán zárt, nem adta fel
    assert len(raw) == 3  # a beragadás előtti kockák megvannak


def test_a_start_elotti_kockakat_nem_detektaljuk(tmp_path, monkeypatch):
    """start > 0: a kezdőkocka ELŐTTI kockákon nem fut detektálás (eddig a
    folyam-olvasó a videó elejétől minden ritkított kockát detektált, csak
    hogy utána eldobja — a Folytatás a kész részt újradetektálta). A
    kezdő olvasó a kezdőkockára teker, a KÖZÖS modellel; a felület a
    modell betöltése után szól."""
    import sys
    import types

    import cv2

    import scripts.process_video as pv

    v = tmp_path / "v.mp4"
    vw = cv2.VideoWriter(str(v), cv2.VideoWriter_fourcc(*"mp4v"), 25.0,
                         (96, 64))
    for k in range(30):
        vw.write(np.full((64, 96, 3), 8 * k, dtype=np.uint8))
    vw.release()

    import threading

    hivasok = {"folyam": 0, "kockak": [], "peldany": 0, "cpu_szal": []}

    class _Res:
        def __init__(self, img, eszkoz="mps"):
            self.orig_img = img
            self.boxes = None
            self.eszkoz = eszkoz

        def cpu(self):
            hivasok["cpu_szal"].append(threading.current_thread().name)
            return _Res(self.orig_img, "cpu")

    class _FakeModel:
        names = {0: "person", 32: "sports ball"}

        def __init__(self, *_a, **_k):
            hivasok["peldany"] += 1

        def track(self, source=None, **_kw):
            if isinstance(source, str):
                hivasok["folyam"] += 1
                return iter(())
            hivasok["kockak"].append(float(source.mean()))
            return [_Res(source)]

    fake_ultra = types.ModuleType("ultralytics")
    fake_ultra.YOLO = _FakeModel
    monkeypatch.setitem(sys.modules, "ultralytics", fake_ultra)
    w = tmp_path / "w.pt"
    w.write_bytes(b"x" * 2048)
    monkeypatch.setattr(pv, "_resolve_weights", lambda _w: str(w))

    raw, jegyzet = [], []
    latott = []
    eredeti = pv._is_dark

    def _figyelo(img, *a, **k):
        latott.append(threading.current_thread().name)
        return eredeti(img, *a, **k)

    monkeypatch.setattr(pv, "_is_dark", _figyelo)
    pv._process_yolo(str(v), str(w), stride=2, max_frames=100, imgsz=640,
                     conf=0.2, start=20, skip_dark=True, raw_out=raw,
                     colors_out=[], on_note=jegyzet.append, ball_recover=False)
    # Az Apple-GPU nem szál-biztos: az eredmény CPU-ra másolása a TERMELŐ
    # szálon fut, a hívó szál (a kockák feldolgozása) már a CPU-s
    # eredményt kapja.
    fo = threading.current_thread().name
    assert hivasok["cpu_szal"] and fo not in hivasok["cpu_szal"]
    assert latott and set(latott) == {fo}
    assert hivasok["folyam"] == 0           # a folyam-olvasó nem indult
    assert hivasok["peldany"] == 1          # a közös modellel ment
    assert len(hivasok["kockak"]) == 5 == len(raw)   # 20, 22, …, 28
    assert abs(hivasok["kockak"][0] - 160) < 6       # a 20. kocka az első
    assert jegyzet and jegyzet[0].startswith("a detektáló modell betöltve")


def test_elakadas_utan_mps_en_a_folytatas_a_processzoron_fut(tmp_path,
                                                              monkeypatch):
    """Az Apple-GPU nem szál-biztos: elakadás után a folytató olvasó
    (ÚJ termelő szál, saját modell) a CPU-n számol, mert az elakadt szál
    még fogja a GPU-t; a felület is megtudja. A kezdő olvasó (start > 0,
    a közös modellel) a GPU-n marad."""
    import sys
    import threading
    import types

    import cv2

    import scripts.process_video as pv

    v = tmp_path / "v.mp4"
    vw = cv2.VideoWriter(str(v), cv2.VideoWriter_fourcc(*"mp4v"), 25.0,
                         (96, 64))
    for k in range(30):
        vw.write(np.full((64, 96, 3), 120, dtype=np.uint8))
    vw.release()
    eszkozok = []

    class _Res:
        def __init__(self, img):
            self.orig_img = img
            self.boxes = None

    class _FakeModel:
        names = {0: "person", 32: "sports ball"}

        def __init__(self, *_a, **_k):
            pass

        def track(self, source=None, **kw):
            if isinstance(source, str):     # a folyam-olvasó: 2 kocka, majd beragad
                def gen():
                    for _ in range(2):
                        yield _Res(np.full((64, 96, 3), 120, np.uint8))
                    threading.Event().wait(9999)
                return gen()
            eszkozok.append(kw.get("device"))
            return [_Res(source)]

    fake_ultra = types.ModuleType("ultralytics")
    fake_ultra.YOLO = _FakeModel
    monkeypatch.setitem(sys.modules, "ultralytics", fake_ultra)
    w = tmp_path / "w.pt"
    w.write_bytes(b"x" * 2048)
    monkeypatch.setattr(pv, "_resolve_weights", lambda _w: str(w))
    monkeypatch.setattr(pv, "_pick_device", lambda: "mps")

    import queue as queue_mod
    real_queue = queue_mod.Queue

    class _FastQueue(real_queue):
        def get(self, block=True, timeout=None):
            if timeout is not None and timeout > 1:
                timeout = 0.5
            return super().get(block=block, timeout=timeout)

    monkeypatch.setattr(queue_mod, "Queue", _FastQueue)
    jegyzet = []
    pv._process_yolo(str(v), str(w), stride=1, max_frames=100, imgsz=640,
                     conf=0.2, raw_out=[], colors_out=[], skip_dark=False,
                     on_note=jegyzet.append, ball_recover=False)
    assert eszkozok and set(eszkozok) == {"cpu"}, eszkozok
    assert any("a folytatás a processzoron fut" in j for j in jegyzet)
    # A kezdő olvasó (start > 0, a közös modellel) a GPU-n marad.
    eszkozok.clear()
    pv._process_yolo(str(v), str(w), stride=2, max_frames=100, imgsz=640,
                     conf=0.2, start=10, raw_out=[], colors_out=[],
                     skip_dark=False, ball_recover=False)
    assert eszkozok and set(eszkozok) == {"mps"}, eszkozok
