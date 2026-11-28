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


def _mentesre_var(kiirva):
    """progress_cb: a detektálás a 15. kockánál megvárja, hogy a
    háttér-mentés kiírjon. A mentés a detektálás végén elavul (a késői
    részeredmény nem íródik ki) — a gyors teszt-videón különben a
    mentés sosem érne a kiírásig."""
    import re

    def cb(stage, _p, msg):
        k = re.match(r"detektálás (\d+)/", msg or "") if stage == "B" else None
        if k and int(k.group(1)) >= 15 and not kiirva.is_set():
            kiirva.wait(20.0)
    return cb


def test_checkpoint_saves_partial_then_full(tmp_path):
    """Időszakos checkpoint: checkpoint_every_s=0 mellett a detektálás közben
    is elmentődik legalább egy RÉSZLEGES (de érvényes) Match, a végeredmény
    pedig a teljes videó — a checkpoint nem rontja el a végső feldolgozást."""
    video = tmp_path / "mini4.mp4"
    _tiny_video(video, frames=30)

    import threading

    saved: list[Match] = []
    kiirva = threading.Event()

    def ment(cp):
        saved.append(cp)
        kiirva.set()

    m = process(str(video), None, weights=None, stride=1, max_frames=100,
                checkpoint_save=ment, checkpoint_every_s=0.0,
                progress_cb=_mentesre_var(kiirva))
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
    """A lassú mentés nem tartja fel a detektálást: a mentés külön szálon
    fut, és MIALATT fut, a detektálás tovább jelez (a szívverés nem áll).
    Falióra nélkül: a detektálás a 15. kockánál megvárja, hogy a mentés
    elinduljon, a mentés pedig addig tart, amíg közben detektálás-jelzés
    érkezik — ha a mentés a detektálás szálán futna, ez sosem jönne meg."""
    import re
    import threading

    video = tmp_path / "mini7.mp4"
    _tiny_video(video, frames=60)
    saved: list[Match] = []
    szalak: list[str] = []
    mentes_indult = threading.Event()
    mentes_alatt = threading.Event()

    def lassu(m):
        szalak.append(threading.current_thread().name)
        mentes_indult.set()
        mentes_alatt.wait(20.0)
        saved.append(m)

    def jelzes(stage, _p, msg):
        if stage != "B":
            return
        k = re.match(r"detektálás (\d+)/", msg or "")
        if not k:
            return
        if mentes_indult.is_set():
            mentes_alatt.set()          # a mentés alatt a detektálás jelez
        elif int(k.group(1)) >= 15:
            mentes_indult.wait(20.0)    # a 10. kockánál indult mentés elérje a kiírást

    m = process(str(video), None, weights=None, stride=1, max_frames=100,
                checkpoint_save=lassu, checkpoint_every_s=0.0,
                progress_cb=jelzes)
    assert len(m.frames) == 60
    assert mentes_alatt.is_set(), "a mentés alatt a detektálás nem jelzett"
    # Nem a detektálás szálán mentett.
    assert saved and szalak
    assert threading.current_thread().name not in szalak


def test_a_detektalas_vege_utan_a_kesei_mentes_elmarad(tmp_path, monkeypatch):
    """A detektálás vége a még futó háttér-mentést elavulttá teszi: a
    késői részeredmény NEM íródik ki (nem kerülhet a végeredmény fölé, és
    hiba után sem ír a lezárt munkára), és a process nem várja meg."""
    import threading
    import time

    import handball.pipeline.track_stitch as ts

    video = tmp_path / "mini9.mp4"
    _tiny_video(video, frames=30)
    kiirt: list[Match] = []
    bent = threading.Event()
    engedd = threading.Event()
    eredeti = ts.stitch_tracks
    fo = threading.current_thread()

    def lassitott(*a, **k):
        # Csak a háttér-mentés akad meg itt — a végső utómunka nem.
        if threading.current_thread() is not fo:
            bent.set()
            engedd.wait(20.0)
        return eredeti(*a, **k)

    monkeypatch.setattr(ts, "stitch_tracks", lassitott)
    m = process(str(video), None, weights=None, stride=1, max_frames=100,
                checkpoint_save=kiirt.append, checkpoint_every_s=0.0)
    # A process visszatért, a háttér-mentés még bent ragad — nem várta meg.
    assert len(m.frames) == 30
    assert bent.wait(20.0)
    engedd.set()
    hatarido = time.time() + 20
    while any("_checkpoint_hatter" in t.name for t in threading.enumerate()):
        assert time.time() < hatarido
        time.sleep(0.05)
    assert kiirt == [], "a detektálás vége után részeredmény íródott ki"


def test_a_hatter_mentes_nem_hivja_a_szavazot(tmp_path, monkeypatch):
    """A háttér-mentés a detektálás szálán SZÁMOLT mezszám-döntéseket kapja:
    a háttérszál sosem nyúl a szavazóhoz (az élőt a detektálás közben is
    írja — a szótár bejárása elbukhatna)."""
    import threading

    from handball.pipeline import jersey_ocr

    video = tmp_path / "mini8.mp4"
    _tiny_video(video, frames=30)
    szalak: list[str] = []
    eredeti = jersey_ocr.JerseyVoter.decisions

    def figyelt(self):
        szalak.append(threading.current_thread().name)
        return eredeti(self)

    monkeypatch.setattr(jersey_ocr.JerseyVoter, "decisions", figyelt)
    saved: list[Match] = []
    kiirva = threading.Event()

    def ment(cp):
        saved.append(cp)
        kiirva.set()

    m = process(str(video), None, weights=None, stride=1, max_frames=100,
                jersey_ocr=True, checkpoint_save=ment,
                checkpoint_every_s=0.0, progress_cb=_mentesre_var(kiirva))
    assert len(m.frames) == 30 and saved
    fo = threading.current_thread().name
    assert szalak and set(szalak) == {fo}


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
