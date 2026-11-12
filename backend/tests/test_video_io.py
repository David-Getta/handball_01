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


# ---- Képráta, hossz, és a Windows rövid útvonal ága --------------------------

def _kis_video(ut, kockak=10, fps=25.0):
    """Néhány kockás valódi videó (mp4v) a fejléc-olvasás tesztjéhez."""
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    iro = cv2.VideoWriter(str(ut), cv2.VideoWriter_fourcc(*"mp4v"), fps,
                          (64, 48))
    if not iro.isOpened():
        pytest.skip("ezen a gépen nincs mp4v író")
    for i in range(kockak):
        iro.write(np.full((48, 64, 3), 10 * i, np.uint8))
    iro.release()
    return ut


def test_video_fps_es_video_seconds_a_fejlecbol(tmp_path):
    """A képráta és a hossz a videó fejlécéből jön (a kézi meccs-ablak a
    másodpercet ebből váltja kockára): 10 kocka 25 fps-en = 0,4 mp."""
    from handball.video_io import video_fps, video_seconds

    ut = _kis_video(tmp_path / "meccs.mp4", kockak=10, fps=25.0)
    assert video_fps(ut) == pytest.approx(25.0, abs=0.01)
    assert video_fps(str(ut)) == pytest.approx(25.0, abs=0.01)   # str is jó
    assert video_seconds(ut) == pytest.approx(0.4, abs=0.05)
    lassu = _kis_video(tmp_path / "lassu.mp4", kockak=5, fps=12.5)
    assert video_fps(lassu) == pytest.approx(12.5, abs=0.01)
    assert video_seconds(lassu) == pytest.approx(0.4, abs=0.05)


def test_video_fps_none_ha_nem_olvashato(tmp_path):
    """"Nincs becslés" a kivétel helyett: hiányzó fájlra, nem-videó
    tartalomra és mappára None — a hívó (az indítás előtti ellenőrzés)
    ettől nem állhat meg."""
    pytest.importorskip("cv2")
    from handball.video_io import video_fps, video_seconds

    szoveg = tmp_path / "nem_video.mp4"
    szoveg.write_bytes(b"ez nem video")
    for ut in (tmp_path / "nincs.mp4", szoveg, tmp_path):
        assert video_fps(ut) is None
        assert video_seconds(ut) is None


class _HamisCap:
    """Hamis VideoCapture: megadott fejléc-értékek, számolt elengedés."""

    def __init__(self, ertekek, nyitva=True, bukik_get=False,
                 bukik_release=False):
        self.ertekek, self.nyitva = ertekek, nyitva
        self.bukik_get, self.bukik_release = bukik_get, bukik_release
        self.elengedve = 0

    def isOpened(self):
        return self.nyitva

    def get(self, mi):
        if self.bukik_get:
            raise RuntimeError("a fejléc olvashatatlan")
        return self.ertekek.get(mi, 0.0)

    def release(self):
        self.elengedve += 1
        if self.bukik_release:
            raise RuntimeError("az elengedés hibázott")


def test_video_fps_a_videot_mindig_elengedi(monkeypatch):
    """A megnyitott videó minden ágon elengedődik (Windowson a nyitva
    felejtett fájl nem törölhető / nem mozgatható): jó fejlécnél, nulla
    vagy hiányzó képrátánál (None) és olvasási hibánál is; az elengedés
    hibája sem jut ki."""
    cv2 = pytest.importorskip("cv2")
    import handball.video_io as vio

    def futtat(cap):
        monkeypatch.setattr(vio, "open_capture", lambda ut: cap)
        return vio.video_fps("mindegy.mp4"), vio.video_seconds("mindegy.mp4")

    jo = _HamisCap({cv2.CAP_PROP_FPS: 50.0, cv2.CAP_PROP_FRAME_COUNT: 150.0})
    assert futtat(jo) == (50.0, 3.0) and jo.elengedve == 2
    nulla = _HamisCap({cv2.CAP_PROP_FPS: 0.0,
                       cv2.CAP_PROP_FRAME_COUNT: 150.0})
    assert futtat(nulla) == (None, None) and nulla.elengedve == 2
    # A képráta megvan, a kockaszám hiányzik: fps van, hossz nincs.
    kockatlan = _HamisCap({cv2.CAP_PROP_FPS: 25.0})
    assert futtat(kockatlan) == (25.0, None)
    hibas = _HamisCap({}, bukik_get=True)
    assert futtat(hibas) == (None, None) and hibas.elengedve == 2
    makacs = _HamisCap({cv2.CAP_PROP_FPS: 25.0,
                        cv2.CAP_PROP_FRAME_COUNT: 50.0}, bukik_release=True)
    assert futtat(makacs) == (25.0, 2.0)


def test_windows_short_path_nem_windowson_none():
    """A rövid (8.3-as) útvonal csak Windowson kérhető le: máshol None —
    nem kivétel (a hívó ilyenkor a beszélő hibát adja)."""
    from handball.video_io import _windows_short_path

    if os.name == "nt":
        pytest.skip("ez a teszt a nem-Windows ágat nézi")
    assert _windows_short_path("/home/Dávid/Videók/meccs.mp4") is None
    assert _windows_short_path("") is None


def test_windows_short_path_a_rendszerhivas_eredmenyebol(monkeypatch):
    """A rövid útvonal a Windows GetShortPathNameW hívásából jön (előbb
    a szükséges hossz, aztán a puffer); None, ha a hívás 0-t ad (a
    köteten nincs 8.3-as név) vagy a puffer üres marad."""
    import ctypes
    import types

    from handball.video_io import _windows_short_path

    pytest.importorskip("ctypes.wintypes")
    hivasok = []

    class _HamisGetShort:
        """A GetShortPathNameW hamisítványa: puffer nélkül a szükséges
        hosszt adja, pufferrel kitölti és a beírt hosszt adja."""
        argtypes = restype = None            # a hívó állítja be

        def __init__(self, rovid, elso=None, masodik=None):
            self.rovid, self.elso, self.masodik = rovid, elso, masodik

        def __call__(self, ut, puffer, meret):
            hivasok.append((ut, puffer is None, meret))
            if puffer is None:
                return len(self.rovid) + 1 if self.elso is None else self.elso
            puffer.value = self.rovid
            return len(self.rovid) if self.masodik is None else self.masodik

    def hamis_windll(*a, **kw):
        return types.SimpleNamespace(kernel32=types.SimpleNamespace(
            GetShortPathNameW=_HamisGetShort(*a, **kw)))

    hosszu = "C:\\Users\\Dávid\\Videók\\meccs.mp4"
    monkeypatch.setattr(ctypes, "windll",
                        hamis_windll("C:\\Users\\DVID~1\\VIDEK~1\\meccs.mp4"),
                        raising=False)
    assert _windows_short_path(hosszu) == \
        "C:\\Users\\DVID~1\\VIDEK~1\\meccs.mp4"
    # Két hívás: előbb a méret (puffer nélkül), aztán a kitöltés.
    assert [(h[1], h[2] > 0) for h in hivasok] == [(True, False),
                                                   (False, True)]
    assert all(h[0] == hosszu for h in hivasok)
    # Nincs 8.3-as név (a méret-kérés 0), a kitöltés bukik, üres puffer.
    monkeypatch.setattr(ctypes, "windll", hamis_windll("X", elso=0),
                        raising=False)
    assert _windows_short_path(hosszu) is None
    monkeypatch.setattr(ctypes, "windll", hamis_windll("X", masodik=0),
                        raising=False)
    assert _windows_short_path(hosszu) is None
    monkeypatch.setattr(ctypes, "windll", hamis_windll(""), raising=False)
    assert _windows_short_path(hosszu) is None


def _windows_kornyezet(monkeypatch, megnyilik, rovid):
    """Windows-szerű környezet az open_capture-nek: az `os.name` "nt", a
    VideoCapture csak a `megnyilik` útvonalakon nyílik, a rövid útvonal
    a `rovid` (vagy None). Visszaadja a megnyitási kísérletek listáját és
    a létrehozott hamis videókat."""
    cv2 = pytest.importorskip("cv2")
    import types

    import handball.video_io as vio

    kiserletek, capok, rovid_keresek = [], [], []

    def hamis_capture(ut):
        kiserletek.append(ut)
        cap = _HamisCap({}, nyitva=ut in megnyilik)
        capok.append(cap)
        return cap

    monkeypatch.setattr(cv2, "VideoCapture", hamis_capture)
    monkeypatch.setattr(vio, "os", types.SimpleNamespace(
        name="nt", path=os.path))
    monkeypatch.setattr(vio, "_windows_short_path",
                        lambda ut: (rovid_keresek.append(ut), rovid)[1])
    return kiserletek, capok, rovid_keresek


def test_open_capture_windowson_az_ekezetes_utat_a_rovid_alakkal_nyitja(
        monkeypatch, tmp_path):
    """Windowson az ékezetes útvonal első megnyitása némán elbukik: a
    második próbálkozás a rövid (ASCII) alakkal megy, és az első,
    sikertelen videó elengedődik."""
    from handball.video_io import open_capture

    ekezetes = str(tmp_path / "Videók" / "meccs.mp4")
    kiserletek, capok, _ = _windows_kornyezet(
        monkeypatch, megnyilik={"C:\\VIDEK~1\\meccs.mp4"},
        rovid="C:\\VIDEK~1\\meccs.mp4")
    cap = open_capture(ekezetes)
    assert kiserletek == [ekezetes, "C:\\VIDEK~1\\meccs.mp4"]
    assert cap is capok[1] and cap.isOpened()
    assert capok[0].elengedve == 1 and capok[1].elengedve == 0


def test_open_capture_windowson_is_beszelo_hiba_ha_a_rovid_ut_sem_megy(
        monkeypatch, tmp_path):
    """Ha rövid útvonal nincs (None / ugyanaz), vagy azzal sem nyílik
    meg, a beszélő kivétel jön az ékezet okával — és minden megnyitott
    videó elengedődik; ékezet nélküli útvonalnál nincs második próba."""
    from handball.video_io import VideoOpenError, open_capture

    mappa = tmp_path / "Videók"
    mappa.mkdir()
    ekezetes = mappa / "meccs.mp4"
    ekezetes.write_bytes(b"x")
    for rovid, vart_kiserlet in ((None, 1), (str(ekezetes), 1),
                                 ("C:\\VIDEK~1\\meccs.mp4", 2)):
        kiserletek, capok, _ = _windows_kornyezet(monkeypatch, megnyilik=set(),
                                                  rovid=rovid)
        with pytest.raises(VideoOpenError) as e:
            open_capture(ekezetes)
        assert "ÉKEZETES" in str(e.value)
        assert len(kiserletek) == vart_kiserlet, rovid
        assert all(c.elengedve == 1 for c in capok)
    # Ékezet nélküli útvonal: a rövid alakot meg sem kérdezzük.
    sima = tmp_path / "meccs.mp4"
    sima.write_bytes(b"x")
    kiserletek, _, rovid_keresek = _windows_kornyezet(
        monkeypatch, megnyilik=set(), rovid="C:\\MASIK.mp4")
    with pytest.raises(VideoOpenError) as e:
        open_capture(sima)
    assert kiserletek == [str(sima)] and rovid_keresek == []
    assert "kodek" in str(e.value)
