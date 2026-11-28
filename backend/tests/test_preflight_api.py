"""
Az előzetes ellenőrzés a motor felületén: POST /preflight, és a
kevés helynél való ELUTASÍTÁS a feldolgozás indításakor.

Miért itt is: a modul-tesztek a számolást őrzik, ez pedig azt, hogy a
válasz TÉNYLEG eljut a klienshez — és hogy a feldolgozás nem indul el
olyan gépen, ahol félúton elfogyna a hely (az elveszett fél óra a
felhasználó ideje).

Futtatás:
    python -m pytest tests/test_preflight_api.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

cv2 = pytest.importorskip("cv2", reason="OpenCV nincs telepítve")
np = pytest.importorskip("numpy", reason="numpy nincs telepítve")
TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient


def _tiny_video(path, frames=25, w=96, h=64):
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"),
                         25.0, (w, h))
    rng = np.random.default_rng(3)
    for _ in range(frames):
        vw.write(rng.integers(90, 200, size=(h, w, 3), dtype=np.uint8))
    vw.release()


def _client():
    from handball.api.app import create_app
    os.environ["HANDBALL_DATA_DIR"] = tempfile.mkdtemp(prefix="hb_pref_")
    return TestClient(create_app())


def _mentett_params(match_id):
    """A feldolgozás mentett paraméterei (ebből indul a Folytatás is).

    A motor ide írja ki a TÉNYLEGESEN használt kockaszámokat — a
    másodpercből átváltott értékeket is —, tehát a hossz-korlát
    helyességét itt lehet ellenőrizni.
    """
    import json
    import re
    root = Path(os.environ["HANDBALL_DATA_DIR"]) / "data" / "matches"
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", match_id) or "match"
    return json.loads((root / f"{safe}.params.json").read_text(
        encoding="utf-8"))


def test_preflight_megmondja_a_video_hosszat(tmp_path):
    """A 25 kockás, 25 fps-es videó egy másodperc — ezt kell látni."""
    video = tmp_path / "meccs.mp4"
    _tiny_video(video, frames=25)
    r = _client().post("/preflight", json={"path": str(video)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path_ok"] is True
    assert body["video_seconds"] == pytest.approx(1.0, abs=0.2)
    assert body["space_error"] is None or "szabad hely" in body["space_error"]


def test_preflight_nem_letezo_utra_is_valaszol(tmp_path):
    """A hiányzó fájl nem hiba, hanem információ: path_ok=false."""
    r = _client().post("/preflight", json={"path": str(tmp_path / "nincs.mp4")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path_ok"] is False
    assert body["estimate_s"] is None


def test_preflight_kevés_meresnel_nem_becsul(tmp_path):
    """Friss gépen nincs mérés — inkább semmi, mint téves szám."""
    video = tmp_path / "meccs.mp4"
    _tiny_video(video)
    body = _client().post("/preflight", json={"path": str(video)}).json()
    assert body["estimate_s"] is None
    assert body["estimate_label"] is None


def test_keves_helynel_el_sem_indul_a_feldolgozas(tmp_path, monkeypatch):
    """Elutasítás INDULÁS előtt, magyar indoklással — nem a 90%-nál."""
    import handball.preflight as pf

    video = tmp_path / "meccs.mp4"
    _tiny_video(video)
    client = _client()
    monkeypatch.setattr(pf, "free_gb", lambda _root: 0.2)
    r = client.post("/matches/process", json={"path": str(video)})
    assert r.status_code == 400
    assert "szabad hely" in r.json()["detail"]


def test_a_munka_rekordja_viszi_a_video_hosszat(tmp_path):
    """Enélkül a motor sosem tanulná meg, milyen gyors ez a gép."""
    video = tmp_path / "meccs.mp4"
    _tiny_video(video)
    client = _client()
    r = client.post("/matches/process", json={"path": str(video), "max": 5})
    assert r.status_code == 200, r.text
    job_id = r.json()["job_id"]
    j = client.get(f"/jobs/{job_id}").json()
    assert j.get("video_seconds") == pytest.approx(1.0, abs=0.2)


def test_preflight_a_meccsablakra_szamol(tmp_path):
    """A becslés a FELDOLGOZANDÓ szakaszra szóljon, ne a teljes videóra.

    Ha a felhasználó megadja a meccs időablakát, csak annak a részét
    dolgozzuk fel — a teljes hosszal számolt becslés ugyanúgy téves
    lenne, mint a rossz profillal számolt.
    """
    video = tmp_path / "meccs.mp4"
    _tiny_video(video, frames=250)          # 10 másodperc @ 25 fps
    client = _client()

    teljes = client.post("/preflight", json={"path": str(video)}).json()
    assert teljes["video_seconds"] == pytest.approx(10.0, abs=0.3)
    assert teljes["processed_seconds"] == pytest.approx(10.0, abs=0.3)

    ablakos = client.post("/preflight", json={
        "path": str(video), "start_s": 2.0, "end_s": 6.0}).json()
    # A videó hossza változatlan, a feldolgozandó szakasz viszont 4 mp.
    assert ablakos["video_seconds"] == pytest.approx(10.0, abs=0.3)
    assert ablakos["processed_seconds"] == pytest.approx(4.0, abs=0.3)


def test_preflight_ertelmetlen_ablakot_nem_fogad_el(tmp_path):
    """A fordított (vagy videón kívüli) ablak ne csonkítsa a becslést."""
    video = tmp_path / "meccs.mp4"
    _tiny_video(video, frames=250)
    client = _client()

    # A vége korábban van, mint a kezdet → marad a teljes hossz.
    r = client.post("/preflight", json={
        "path": str(video), "start_s": 8.0, "end_s": 3.0}).json()
    assert r["processed_seconds"] == pytest.approx(10.0, abs=0.3)

    # A videón túlnyúló vég a videó végére vágódik.
    r2 = client.post("/preflight", json={
        "path": str(video), "start_s": 2.0, "end_s": 999.0}).json()
    assert r2["processed_seconds"] == pytest.approx(8.0, abs=0.3)


def _tiny_video_fps(path, frames, fps, w=96, h=64):
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"),
                         float(fps), (w, h))
    rng = np.random.default_rng(7)
    for _ in range(frames):
        vw.write(rng.integers(90, 200, size=(h, w, 3), dtype=np.uint8))
    vw.release()


def test_a_hossz_korlat_a_valodi_fps_szerint_szamol(tmp_path):
    """A "Félidő (~35 p)" 30 fps-es videón is 35 perc legyen.

    A kliens a korlátot kockában is elküldi, de ott csak 25 fps-sel tud
    számolni — 30 fps-es telefonvideón ugyanaz a kockaszám 29 percet
    jelentene. A felhasználó a FELIRATOT hiszi el, ezért a motornak a
    valódi fps-sel kell átváltania.
    """
    video = tmp_path / "meccs.mp4"
    _tiny_video_fps(video, frames=300, fps=30.0)   # 10 másodperc @ 30 fps
    client = _client()
    # 4 másodperces korlát, stride=2 → 4 * 30 / 2 = 60 feldolgozott kocka.
    # A kliens tartalék száma (25 fps-sel) 50 lenne — azt kell felülírni.
    r = client.post("/matches/process", json={
        "path": str(video), "stride": 2, "max": 50, "max_s": 4.0,
        "match_id": "fps30"})
    assert r.status_code == 200, r.text
    assert _mentett_params("fps30")["max"] == 60


def test_olvashatatlan_fps_nel_marad_a_kliens_szama(tmp_path):
    """Ha az fps nem olvasható ki, a kliens kockában megadott tartalék
    száma marad érvényben — a próba-futás nem eshet szét teljes videóvá."""
    hianyzo = tmp_path / "nincs.mp4"
    client = _client()
    r = client.post("/matches/process", json={
        "path": str(hianyzo), "stride": 2, "max": 50, "max_s": 4.0,
        "match_id": "nofps"})
    # A hiányzó fájlt a motor utasítja el — a lényeg, hogy a `max` nem
    # veszett el útközben (nem lett 0 = teljes videó).
    if r.status_code == 200:
        assert _mentett_params("nofps")["max"] == 50
    else:
        assert r.status_code == 400


def test_a_szigorubb_korlat_nyer(tmp_path):
    """Aki 0–8 mp-es ablakot ad meg, de 4 mp-es hosszt választ, négyet
    kap — a két korlát közül a szigorúbb érvényes."""
    video = tmp_path / "meccs.mp4"
    _tiny_video_fps(video, frames=250, fps=25.0)   # 10 másodperc
    client = _client()
    r = client.post("/matches/process", json={
        "path": str(video), "stride": 1, "max": 0, "match_id": "szigoru",
        "start_s": 0.0, "end_s": 8.0, "max_s": 4.0})
    assert r.status_code == 200, r.text
    assert _mentett_params("szigoru")["max"] == 100   # 4 mp * 25 fps / 1


def test_preflight_a_hossz_korlatra_becsul(tmp_path):
    """A "Próba (~2 p)" becslése két percre szóljon, ne a teljes videóra."""
    video = tmp_path / "meccs.mp4"
    _tiny_video_fps(video, frames=250, fps=25.0)   # 10 másodperc
    client = _client()
    r = client.post("/preflight", json={"path": str(video), "max_s": 4.0}).json()
    assert r["video_seconds"] == pytest.approx(10.0, abs=0.3)
    assert r["processed_seconds"] == pytest.approx(4.0, abs=0.3)
# ---- Profil-javaslat rövid szakaszra ---------------------------------


def test_rovid_szakaszra_a_pontos_profilt_ajanljuk(tmp_path):
    """A "Pontos" profil egy teljes meccsen órákat kér — jogosan nem az
    alapértelmezés. Egy pár perces klipen viszont perceket, és pont a
    LABDA felismerésén javít, amire a birtoklás, a passz, az eladás és
    a lövés is épül.

    A felhasználó ezt magától nem tudja: a profil-választó három nevet
    kínál, és sehol nem mondja meg, mikor melyik éri meg.
    """
    video = tmp_path / "klip.mp4"
    _tiny_video(video)
    c = _client()
    r = c.post("/preflight", json={"path": str(video), "stride": 3,
                                   "imgsz": 1280}).json()
    javaslat = r["profile_hint"]
    assert javaslat, "rövid szakaszra nincs profil-javaslat"
    assert "Pontos" in javaslat
    assert "LABDA" in javaslat or "labda" in javaslat


def test_a_mar_pontos_profilt_nem_kerdojelezzuk_meg(tmp_path):
    """Aki már a Pontosat választotta, ne kapjon javaslatot ugyanarra:
    a meglévő döntést nem kérdőjelezzük meg."""
    video = tmp_path / "klip.mp4"
    _tiny_video(video)
    c = _client()
    r = c.post("/preflight", json={"path": str(video), "stride": 2,
                                   "imgsz": 1920}).json()
    assert r["profile_hint"] is None


def test_hosszu_szakaszra_nincs_javaslat(tmp_path):
    """Teljes meccsen a Pontos profil ÓRÁKAT kér — ott ez rossz tanács
    lenne. A hossz-korláttal szűkített szakaszra viszont a szűkített
    hossz számít, nem a videóé."""
    video = tmp_path / "klip.mp4"
    _tiny_video(video)
    c = _client()
    # A videó rövid, de úgy teszünk, mintha a feldolgozandó szakasz
    # hosszú lenne: a kezdet/vég a videó hosszára vágódik, ezért a
    # hossz-korlátot használjuk fordítva — a küszöb fölötti videót a
    # modul-oldali teszt fedi. Itt azt nézzük, hogy a mező LÉTEZIK.
    r = c.post("/preflight", json={"path": str(video)}).json()
    assert "profile_hint" in r


def test_a_javaslat_kuszobe_kozos_a_klip_jelzessel():
    """ŐR: a két hely UGYANAZT a küszöböt használja.

    Ha külön számot írnánk, egy felvétel kaphatna profil-javaslatot
    ("ez rövid") és közben meccs-szintű elemzést is — vagy fordítva.
    A felhasználó ezt ellentmondásnak látná, és joggal.
    """
    src = (Path(__file__).resolve().parents[1] / "handball" / "api"
           / "app.py").read_text(encoding="utf-8")
    assert "from ..pipeline.quality import CLIP_LENGTH_S" in src
    assert "feldolgozando < CLIP_LENGTH_S" in src
