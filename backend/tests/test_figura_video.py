"""
Tesztek a figura-videó belső segédeire (figura_video.py): a kulcs-
pozíció ékezet nélküli felirata és a kodek-választás. (A videó egészét
a tests/test_figura3d.py nézi.)

Futtatás:
    python -m pytest tests/test_figura_video.py -q
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

cv2 = pytest.importorskip("cv2")
pytest.importorskip("numpy")

from handball.pipeline import figura_video as fv  # noqa: E402


def test_pont_felirat_ekezet_nelkul():
    """A videó Hershey-betűi csak ASCII-t írnak: a kulcs-pozíció neve
    ékezet nélkül megy a képre (Kezdo / Kozep / Veg), a figura-lap
    neveivel párhuzamosan."""
    from handball.pipeline.figura_lap import _pont_felirat as lap_felirat

    assert [fv._pont_felirat(i, 3) for i in range(3)] == [
        "Kezdo", "Kozep", "Veg"]
    assert [fv._pont_felirat(i, 2) for i in range(2)] == ["Kezdo", "Veg"]
    assert fv._pont_felirat(3, 5) == "4. pont"
    for k in (2, 3, 5):
        for i in range(k):
            assert fv._pont_felirat(i, k) == fv.ascii_felirat(
                lap_felirat(i, k))
            assert fv._pont_felirat(i, k).isascii()


@pytest.fixture
def tiszta_kodek(monkeypatch):
    """A kodek-választás folyamatonként egyszer történik — a teszt
    idejére tiszta lappal indul, utána a korábbi választás áll vissza."""
    monkeypatch.setattr(fv, "_kodek_valasztva", None)


def test_kodek_mukodo_irot_valaszt_es_megjegyzi(tmp_path, tiszta_kodek):
    """A kodek az első (háttér, fourcc), amivel a gép egy próba-kockát
    TÉNYLEG ki tud írni; a választás megmarad (a második hívás nem
    próbálkozik újra), és a próba-fájl nem marad a lemezen."""
    cel = tmp_path / "figura.mp4"
    elso = fv._kodek(320, 180, cel)
    api, fourcc = elso
    assert isinstance(api, int) and len(fourcc) == 4
    assert fourcc in {f for _, f in fv.FIGURA_VIDEO_KODEKEK}
    assert list(tmp_path.iterdir()) == []         # a próba-fájl eltűnt
    assert fv._kodek(640, 360, tmp_path / "masik.mp4") is elso
    # A választott kodekkel valóban írható videó.
    import numpy as np
    iro = cv2.VideoWriter(str(cel), api, cv2.VideoWriter_fourcc(*fourcc),
                          fv.FIGURA_VIDEO_FPS, (320, 180))
    assert iro.isOpened()
    iro.write(np.zeros((180, 320, 3), np.uint8))
    iro.release()
    assert cel.exists() and cel.stat().st_size > 0


def test_kodek_ha_egyik_sem_ir_az_mp4v_a_vegso_tartalek(tmp_path,
                                                        tiszta_kodek,
                                                        monkeypatch):
    """Ha a gépen egyik jelölt kodekkel sem nyitható író (hiányzó
    kodek-csomag), a választás a végső tartalék: FFMPEG + mp4v — nem
    kivétel, és próba-fájl sem marad."""
    class _NemNyilik:
        def __init__(self, *a, **k):
            pass

        def isOpened(self):
            return False

        def write(self, _kocka):
            raise AssertionError("zárt íróba nem írunk")

        def release(self):
            pass

    monkeypatch.setattr(cv2, "VideoWriter", _NemNyilik)
    assert fv._kodek(320, 180, tmp_path / "figura.mp4") == (
        cv2.CAP_FFMPEG, "mp4v")
    assert list(tmp_path.iterdir()) == []
