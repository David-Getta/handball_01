"""Videó-megnyitás ékezetes útvonalon.

Az OpenCV `VideoCapture` Windowson a rendszer kódlapján át nyitja a
fájlt, ezért az ÉKEZETES útvonalon (magyar felhasználónál a mindennapi
eset: `C:\\Users\\Dávid\\Videók\\meccs.mp4`) nem nyílik meg — és nem is
dob kivételt, csak `isOpened() == False`-t ad. A kódbázisban kilenc
helyen nyitottunk videót, egyik sem nézte ezt: a hiba "nem sikerült
képkockát olvasni" alakban csapódott le, ami elrejtette a valódi okot.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from handball.video_io import (  # noqa: E402
    VideoOpenError, explain_unopenable, has_non_ascii, open_capture,
)


def test_az_ekezet_felismerese():
    assert has_non_ascii("C:/Users/Dávid/meccs.mp4")
    assert has_non_ascii("/home/user/Videók/a.mp4")
    assert not has_non_ascii("C:/videok/meccs.mp4")


def test_a_hianyzo_fajl_magyarazata_nem_az_ekezetre_fog(tmp_path):
    """Ha a fájl nincs meg, azt kell mondani — nem az ékezetet okolni."""
    uzenet = explain_unopenable(str(tmp_path / "nincs-ilyen.mp4"))
    assert "Nem találom" in uzenet
    assert "ÉKEZETES" not in uzenet


def test_az_ekezetes_ut_magyarazata_teendot_ad(tmp_path):
    """Létező, de megnyithatatlan ékezetes fájlnál mondjuk ki az okot
    ÉS a teendőt — enélkül a felhasználó a kodeket kezdi keresni."""
    f = tmp_path / "Videók"
    f.mkdir()
    p = f / "meccs.mp4"
    p.write_bytes(b"nem valodi video")
    uzenet = explain_unopenable(str(p))
    assert "ÉKEZETES" in uzenet
    assert "ékezet nélküli mappába" in uzenet


def test_a_kodek_hiba_nem_kever_be_ekezetet(tmp_path):
    """Ékezet nélküli, de rossz tartalmú fájlnál a kodek a gyanúsított."""
    p = tmp_path / "meccs.mp4"
    p.write_bytes(b"nem valodi video")
    uzenet = explain_unopenable(str(p))
    assert "ÉKEZETES" not in uzenet
    assert "kodek" in uzenet


def test_a_megnyithatatlan_video_beszelo_kivetelt_dob(tmp_path):
    """A NÉMA isOpened()==False volt a baj: a hívók nem nézték, és a
    hiba ok nélküli "nem olvasható képkocka" lett. Most kivétel jön,
    emberi üzenettel."""
    pytest.importorskip("cv2")
    p = tmp_path / "nincs-ilyen.mp4"
    with pytest.raises(VideoOpenError) as e:
        open_capture(p)
    assert "Nem találom" in str(e.value)
