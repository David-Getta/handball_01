"""
Tesztek a videó-feldolgozó szkript apró segédeire (scripts/process_video.py),
amelyek eddig egyszer sem futottak a csomagban: a törzs-kivágás és a
törzs-szín (csapatszín-mintavétel), a sárga bíró-szűrő, a tartalék
(HOG) út egyszerű követője és a parancssori belépő opció-olvasása.

A nehéz részek (YOLO, a teljes lánc) saját tesztfájlokban élnek
(test_teljes_lanc, test_process_limits, test_stall_skip, …).

Futtatás:
    python -m pytest tests/test_process_video.py -q
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from scripts import process_video as pv  # noqa: E402


# ---- Törzs-kivágás, törzs-szín, bíró-szűrő ------------------------------------

def test_torso_bounds_a_doboz_torzs_savja():
    """A törzs a doboz magasságának 20–55%-a és a szélesség középső fele
    (a fej, a lábak és a háttér-szélek nélkül) — (y1, y2, x1, x2)."""
    assert pv._torso_bounds(100, 100, 180, 300) == (140, 210, 120, 160)
    # A kép fölé lógó doboznál a sáv teteje nem megy 0 alá.
    assert pv._torso_bounds(0, -50, 40, 150) == (0, 60, 10, 30)
    # Elfajult (nulla méretű) doboz: üres sáv, nem hiba.
    assert pv._torso_bounds(50, 60, 50, 60) == (60, 60, 50, 50)


def _alak(torzs_bgr, w=200, h=400):
    """Egy "játékos" a képen: a doboz (60,100)–(140,300); a törzs-sávja a
    megadott színű, a fej és a láb más (zöld pálya, fehér nadrág)."""
    kep = np.full((h, w, 3), (40, 120, 40), np.uint8)       # pálya
    kep[100:140, 60:140] = (150, 180, 220)                  # fej (bőr)
    kep[140:210, 60:140] = torzs_bgr                        # mez
    kep[210:300, 60:140] = (245, 245, 245)                  # nadrág, láb
    return kep, (60, 100, 140, 300)


def test_torso_color_a_mez_atlagszine_rgb_ben():
    """A törzs-szín a MEZ átlagszíne RGB sorrendben (a kép BGR) — a fej,
    a nadrág és a pálya nem keveredik bele."""
    kep, doboz = _alak((10, 200, 250))                      # BGR: narancs
    assert pv._torso_color(kep, *doboz) == (250.0, 200.0, 10.0)
    fekete, doboz = _alak((20, 20, 20))
    assert pv._torso_color(fekete, *doboz) == (20.0, 20.0, 20.0)
    # Kétszínű (csíkos) mez: a két szín átlaga.
    csikos, doboz = _alak((0, 0, 200))
    csikos[140:210, 100:120] = (200, 0, 0)                  # a sáv fele kék
    r, g, b = pv._torso_color(csikos, *doboz)
    assert (r, g, b) == (100.0, 0.0, 100.0)


def test_torso_color_ures_kivagasnal_semleges_szurke():
    """Ha a törzs-sáv üres (elfajult vagy képen kívüli doboz), nincs mit
    mérni: semleges szürke megy vissza — nem NaN, nem kivétel."""
    kep, _ = _alak((10, 200, 250))
    szurke = (128.0, 128.0, 128.0)
    assert pv._torso_color(kep, 50, 60, 50, 60) == szurke
    assert pv._torso_color(kep, 500, 500, 600, 700) == szurke


def test_is_referee_a_sarga_mezt_szuri_ki():
    """A sárga mezes alak játékvezető (kiszűrendő); a fehér, fekete, kék
    és piros mezes játékos nem az."""
    sarga, doboz = _alak((40, 220, 235))                    # BGR sárga
    assert pv._is_referee(sarga, *doboz)
    for bgr in ((245, 245, 245), (20, 20, 20), (200, 60, 30), (30, 30, 200)):
        kep, doboz = _alak(bgr)
        assert not pv._is_referee(kep, *doboz), bgr


def test_is_referee_a_kuszob_a_torzs_harmada_folott():
    """A sárga csak akkor "bíró", ha a törzs-sáv több mint 35%-át adja:
    a sárga csíkos / feliratos játékos-mez (25%) nem az, a félig sárga
    (50%) már igen; a fakó (telítetlen) és a sötét sárgás szín sem az."""
    negyed, doboz = _alak((245, 245, 245))
    negyed[140:210, 100:110] = (40, 220, 235)               # a sáv 25%-a
    assert not pv._is_referee(negyed, *doboz)
    fele, doboz = _alak((245, 245, 245))
    fele[140:210, 100:120] = (40, 220, 235)                 # a sáv 50%-a
    assert pv._is_referee(fele, *doboz)
    fako, doboz = _alak((200, 235, 240))                    # krémszín
    assert not pv._is_referee(fako, *doboz)
    sotet, doboz = _alak((10, 60, 65))                      # olajzöld-barna
    assert not pv._is_referee(sotet, *doboz)


def test_is_referee_ures_kivagasnal_nem_biro():
    """Üres törzs-sávból nem szűrünk ki senkit (hamis, nem kivétel)."""
    kep, _ = _alak((40, 220, 235))
    assert pv._is_referee(kep, 50, 60, 50, 60) is False
    assert pv._is_referee(kep, 500, 500, 600, 700) is False


def test_is_dark_a_sotet_bevezetot_jelzi():
    """A fade-in / elsötétített kocka átlagfényessége a küszöb (40) alatt
    van; a normál kép nem sötét, és a küszöb állítható."""
    assert pv._is_dark(np.full((90, 160, 3), 5, np.uint8)) is True
    assert pv._is_dark(np.full((90, 160, 3), 120, np.uint8)) is False
    hataron = np.full((90, 160, 3), 40, np.uint8)
    assert pv._is_dark(hataron) is False                    # pont a küszöb
    assert pv._is_dark(hataron, thresh=41.0) is True


# ---- A tartalék út egyszerű követője --------------------------------------------

def test_simple_tracker_stabil_azonositot_ad_a_kozeli_mozgasra():
    """Kockáról kockára a közeli (80 px-en belüli) középpont megtartja az
    azonosítóját; az új, távoli alak új azonosítót kap."""
    k = pv._SimpleTracker()
    elso = k.update([(100.0, 100.0), (400.0, 100.0)])
    assert elso == {(100.0, 100.0): 1, (400.0, 100.0): 2}
    masodik = k.update([(110.0, 105.0), (395.0, 98.0), (700.0, 300.0)])
    assert masodik == {(110.0, 105.0): 1, (395.0, 98.0): 2,
                       (700.0, 300.0): 3}
    # A sorrend nem számít: a hozzárendelés a távolságból jön.
    harmadik = k.update([(705.0, 300.0), (390.0, 95.0), (120.0, 110.0)])
    assert harmadik == {(705.0, 300.0): 3, (390.0, 95.0): 2,
                        (120.0, 110.0): 1}


def test_simple_tracker_ket_alak_nem_kap_egy_azonositot():
    """Két egymáshoz közeli alak nem osztozik egy azonosítón: akinek a
    legközelebbi követése már foglalt, újat kap."""
    k = pv._SimpleTracker()
    k.update([(100.0, 100.0)])
    ket_alak = k.update([(105.0, 100.0), (110.0, 100.0)])
    assert sorted(ket_alak.values()) == [1, 2]


def test_simple_tracker_a_regen_latott_kovetest_elengedi():
    """Akit max_gap kockánál tovább nem látunk, annak a követése
    megszűnik: ha visszajön, ÚJ azonosítót kap; a rövid kihagyást
    (max_gap-en belül) viszont áthidalja."""
    k = pv._SimpleTracker(max_dist=80.0, max_gap=3)
    k.update([(100.0, 100.0), (400.0, 100.0)])
    for _ in range(3):                           # 3 kocka kihagyás: még él
        k.update([(400.0, 100.0)])
    assert k.update([(100.0, 100.0), (400.0, 100.0)])[(100.0, 100.0)] == 1
    for _ in range(4):                           # 4 kocka: elengedve
        k.update([(400.0, 100.0)])
    assert 1 not in k.tracks
    vissza = k.update([(100.0, 100.0), (400.0, 100.0)])
    assert vissza == {(100.0, 100.0): 3, (400.0, 100.0): 2}


def test_simple_tracker_ures_kockan_nincs_hozzarendeles():
    """Detektálás nélküli kockán üres a hozzárendelés (nem hiba), és a
    meglévő követések "nem látott" számlálója lép."""
    k = pv._SimpleTracker(max_gap=2)
    assert k.update([]) == {}
    k.update([(100.0, 100.0)])
    assert k.update([]) == {} and k.tracks[1][2] == 1
    k.update([])
    k.update([])
    assert k.tracks == {}


# ---- A parancssori belépő ---------------------------------------------------------

def test_main_keves_argumentumra_hasznalati_utmutato(capsys, monkeypatch):
    """Bemenet és kimenet nélkül a main nem indít feldolgozást: kiírja a
    használatot, és 1-gyel tér vissza."""
    hivasok = []
    monkeypatch.setattr(pv, "process", lambda *a, **k: hivasok.append(a))
    assert pv.main(["process_video"]) == 1
    assert pv.main(["process_video", "be.mp4"]) == 1
    assert "Használat: python -m scripts.process_video BE.mp4 KI.json" in \
        capsys.readouterr().out
    assert hivasok == []


def test_main_az_alapertekekkel_inditja_a_feldolgozast(monkeypatch):
    """Csak a két fájlnévvel a termék alapértékei mennek (minden 3. kocka,
    400 kocka, 1280 px, 0,20 megbízhatóság), minden javító lépéssel."""
    kapott: dict = {}

    def kamu(be, ki, **kw):
        kapott.update(be=be, ki=ki, **kw)

    monkeypatch.setattr(pv, "process", kamu)
    assert pv.main(["process_video", "be.mp4", "ki.json"]) == 0
    assert kapott == {
        "be": "be.mp4", "ki": "ki.json", "weights": None, "stride": 3,
        "max_frames": 400, "imgsz": 1280, "conf": 0.20, "court_poly": None,
        "calib_corners": None, "start": 0, "skip_dark": True,
        "estimate": True, "ball_smooth": True, "track_smooth": True}


def test_main_az_opciokat_es_a_json_fajlokat_atadja(monkeypatch, tmp_path):
    """Az opciók típusra váltva mennek át; a --court és a --calib JSON
    fájlból olvas; a --no-… kapcsolók a megfelelő lépést kapcsolják ki."""
    kapott: dict = {}
    monkeypatch.setattr(pv, "process",
                        lambda be, ki, **kw: kapott.update(be=be, ki=ki, **kw))
    palya = [[0, 0], [1920, 0], [1920, 1080], [0, 1080]]
    sarkok = [[100, 700], [1800, 720], [1500, 250], [400, 240]]
    (tmp_path / "palya.json").write_text(json.dumps(palya), encoding="utf-8")
    (tmp_path / "kalib.json").write_text(json.dumps(sarkok), encoding="utf-8")

    assert pv.main([
        "process_video", "be.mp4", "ki.json", "--weights", "sajat.pt",
        "--stride", "5", "--max", "0", "--imgsz", "960", "--conf", "0.35",
        "--start", "250", "--court", str(tmp_path / "palya.json"),
        "--calib", str(tmp_path / "kalib.json"), "--no-skip-dark",
        "--no-estimate", "--no-ball-smooth", "--no-track-smooth"]) == 0
    assert kapott == {
        "be": "be.mp4", "ki": "ki.json", "weights": "sajat.pt", "stride": 5,
        "max_frames": 0, "imgsz": 960, "conf": 0.35, "court_poly": palya,
        "calib_corners": sarkok, "start": 250, "skip_dark": False,
        "estimate": False, "ball_smooth": False, "track_smooth": False}
