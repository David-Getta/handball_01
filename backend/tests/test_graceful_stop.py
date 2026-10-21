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
    # A meta jelzi a részlegességet, és megmondja, honnan folytatható.
    assert m.meta.partial is True
    assert m.meta.next_start_frame == len(m.frames)  # stride=1, start=0


def test_without_stop_check_processes_all(tmp_path):
    video = tmp_path / "mini2.mp4"
    _tiny_video(video, frames=20)
    m = process(str(video), None, weights=None, stride=1, max_frames=100)
    assert len(m.frames) == 20  # a teljes videó feldolgozva
    assert m.meta.partial is False  # végigért — nem részleges


def test_checkpoint_saves_partial_then_full(tmp_path):
    """Időszakos checkpoint: checkpoint_every_s=0 mellett a detektálás közben
    is elmentődik legalább egy RÉSZLEGES (de érvényes) Match, a végeredmény
    pedig a teljes videó — a checkpoint nem rontja el a végső feldolgozást."""
    video = tmp_path / "mini4.mp4"
    _tiny_video(video, frames=30)

    saved: list[Match] = []
    m = process(str(video), None, weights=None, stride=1, max_frames=100,
                checkpoint_save=saved.append, checkpoint_every_s=0.0)
    assert len(m.frames) == 30  # a végeredmény teljes
    assert saved, "legalább egy checkpoint-mentésnek történnie kellett"
    # A checkpoint-példányok érvényes, nem üres részeredmények; az első
    # biztosan rövidebb a teljesnél (a 10. kocka környékén készül).
    for cp in saved:
        assert isinstance(cp, Match)
        assert 0 < len(cp.frames) <= 30
        assert cp.meta.fps > 0
        assert cp.meta.partial is True  # a checkpoint mindig részleges
    assert len(saved[0].frames) < 30


def test_checkpoint_save_error_does_not_kill_run(tmp_path):
    """A checkpoint-mentés hibája NEM állíthatja le a feldolgozást."""
    video = tmp_path / "mini5.mp4"
    _tiny_video(video, frames=20)

    def boom(_m):
        raise RuntimeError("lemez tele")

    m = process(str(video), None, weights=None, stride=1, max_frames=100,
                checkpoint_save=boom, checkpoint_every_s=0.0)
    assert len(m.frames) == 20  # a hibás mentés ellenére végigfutott


def test_a_checkpoint_a_hatterben_fut_es_nem_allitja_a_haladast(tmp_path):
    """A lassú (fél másodperces) mentés nem tartja fel a detektálást: a
    mentés külön szálon fut, a haladás-jelzés (és vele a szívverés) megy
    tovább — a "B" lépés jelzései közt nincs fél másodperces szünet. A
    végén a futó mentést megvárjuk: a végeredmény teljes, és a mentés
    lezárult, mire a process visszatér."""
    import threading
    import time

    video = tmp_path / "mini7.mp4"
    _tiny_video(video, frames=40)
    saved: list[Match] = []
    szalak: list[str] = []
    jelzesek: list[tuple[str, float]] = []

    def lassu(m):
        szalak.append(threading.current_thread().name)
        time.sleep(0.5)
        saved.append(m)

    m = process(str(video), None, weights=None, stride=1, max_frames=100,
                checkpoint_save=lassu, checkpoint_every_s=0.0,
                progress_cb=lambda s, p, msg: jelzesek.append((s, time.time())))
    assert len(m.frames) == 40
    assert saved and all(0 < len(cp.frames) <= 40 for cp in saved)
    # Nem a detektálás szálán mentett.
    assert szalak and threading.current_thread().name not in szalak
    # A detektálás ("B") jelzései közt nincs mentésnyi szünet.
    b_idok = [t for s, t in jelzesek if s == "B"]
    assert len(b_idok) >= 30
    assert max(b - a for a, b in zip(b_idok, b_idok[1:])) < 0.4


def test_a_hatter_mentes_a_szavazo_pillanatkepevel_dolgozik(tmp_path,
                                                            monkeypatch):
    """A háttér-mentés a mezszám-szavazó MÁSOLATÁVAL számol (az élőt a
    detektálás szála közben is írja — a szótár bejárása elbukhatna); a
    végső utómunka az élő szavazót használja."""
    import threading

    from handball.pipeline import jersey_ocr

    video = tmp_path / "mini8.mp4"
    _tiny_video(video, frames=30)
    hivasok: list[tuple[int, str]] = []
    eredeti = jersey_ocr.JerseyVoter.decisions

    def figyelt(self):
        hivasok.append((id(self), threading.current_thread().name))
        return eredeti(self)

    monkeypatch.setattr(jersey_ocr.JerseyVoter, "decisions", figyelt)
    saved: list[Match] = []
    m = process(str(video), None, weights=None, stride=1, max_frames=100,
                jersey_ocr=True, checkpoint_save=saved.append,
                checkpoint_every_s=0.0)
    assert len(m.frames) == 30 and saved
    fo = threading.current_thread().name
    hatter = {v for v, sz in hivasok if sz != fo}
    elo = {v for v, sz in hivasok if sz == fo}
    assert hatter and elo
    # A háttérben mindig másolat — sosem az élő szavazó.
    assert not (hatter & elo)


def test_no_checkpoint_by_default(tmp_path):
    """checkpoint_save nélkül (alapértelmezés) nincs időszakos mentés."""
    video = tmp_path / "mini6.mp4"
    _tiny_video(video, frames=15)
    m = process(str(video), None, weights=None, stride=1, max_frames=100)
    assert len(m.frames) == 15


def test_immediate_stop_gives_empty_match(tmp_path):
    """Azonnali leállítás: üres (0 kockás) Match — a hívó dönt a sorsáról
    (a szerver ilyenkor nem menti el, "cancelled" státusszal zár)."""
    video = tmp_path / "mini3.mp4"
    _tiny_video(video, frames=10)
    m = process(str(video), None, weights=None, stride=1, max_frames=100,
                stop_check=lambda: True)
    assert isinstance(m, Match)
    assert len(m.frames) == 0
