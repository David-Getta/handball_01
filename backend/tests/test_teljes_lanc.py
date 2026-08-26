"""
A TELJES lánc egy futásban: videó → feldolgozás → jelentés → csomag.

Miért itt: a modul-tesztek darabonként őrzik a motort, a
réteg-regiszter őrei pedig SZIMULÁLT meccsen néznek mindent. A kettő
közt marad egy rés: a valódi útvonal, ahol egy VIDEÓBÓL indulunk, a
detektálás és az utómunka lefut, és a végén a felhasználó jelentést
meg csomagot kap. Egy nap alatt hét idő-küszöböt és több némán
kimaradó ágat javítottunk — pont az ilyen kör mutatja meg, ha
valamelyik javítás elrontotta a valódi utat.

A videó apró és zajos: nem az elemzés MINŐSÉGÉT nézzük (azt nem is
lehetne rajta), hanem hogy a lánc egyetlen pontján se szakadjon meg,
és minden felület magyar, értelmezhető választ adjon.

Futtatás:
    python -m pytest tests/test_teljes_lanc.py
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import time
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

cv2 = pytest.importorskip("cv2", reason="OpenCV nincs telepítve")
np = pytest.importorskip("numpy", reason="numpy nincs telepítve")
TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient


def _video(path, frames=150, w=192, h=128, fps=25.0):
    """Apró, zajos felvétel — a lánc épségét nézzük, nem a tartalmat."""
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"),
                         fps, (w, h))
    rng = np.random.default_rng(11)
    for _ in range(frames):
        vw.write(rng.integers(60, 210, size=(h, w, 3), dtype=np.uint8))
    vw.release()


def _var_job(client, job_id, timeout_s=180):
    hatarido = time.time() + timeout_s
    while time.time() < hatarido:
        job = client.get(f"/jobs/{job_id}").json()
        if job["status"] in ("done", "error", "cancelled"):
            return job
        time.sleep(0.2)
    raise AssertionError("a munka nem fejeződött be időben")


def test_videotol_a_csomagig_ep_a_lanc(tmp_path):
    """Videó → feldolgozás → minőség-jelentés → meccs-csomag."""
    from handball.api.app import create_app

    os.environ["HANDBALL_DATA_DIR"] = tempfile.mkdtemp(prefix="hb_e2e_")
    client = TestClient(create_app())

    video = tmp_path / "meccs.mp4"
    _video(video)

    # 1) Indítás előtti ellenőrzés: a motor tudja, mit fog feldolgozni.
    pre = client.post("/preflight", json={"path": str(video)}).json()
    assert pre["path_ok"] is True
    assert pre["video_seconds"] == pytest.approx(6.0, abs=0.5)

    # 2) Feldolgozás — a hossz-korlát MÁSODPERCBEN (a v0.1.56 óta).
    r = client.post("/matches/process", json={
        "path": str(video), "stride": 3, "max_s": 4.0,
        "match_id": "lanc", "home_team": "Hazai", "away_team": "Vendég"})
    assert r.status_code == 200, r.text
    job = _var_job(client, r.json()["job_id"])
    assert job["status"] == "done", job

    # 3) A meccs a könyvtárban van, és viszi a feldolgozás nyomait.
    m = client.get("/matches/lanc").json()
    assert m["meta"]["home_team"] == "Hazai"
    assert m["frames"], "üres meccs jött ki a feldolgozásból"
    # A meccs-ablak felismerésének eredménye a mentésben (v0.1.56).
    assert "game_window_found" in m["meta"]

    # 4) Minőség-jelentés: magyar, teendővel, és megmondja, MELYIK
    #    szakaszt dolgoztuk fel.
    q = client.get("/matches/lanc/quality").json()
    assert isinstance(q["score"], int)
    assert q["processed_from_s"] is not None
    assert q["processed_to_s"] is not None
    # A labda-lefedettség a MÉRT labdát méri, a pótlás külön (v0.1.58).
    assert "ball_filled_pct" in q
    # Első feldolgozás: nincs mihez viszonyítani, de a kulcs ott van.
    assert q["previous"] == [] and q["score_delta"] is None
    for w in q["warnings"]:
        assert isinstance(w, str) and w.strip()

    # 5) Meccs-csomag: minden réteg elkészül, és a csomag megmondja,
    #    ha valami mégis kimaradt (v0.1.61).
    exp = client.post("/matches/lanc/package/export", json={"clip_types": []})
    assert exp.status_code == 200, exp.text
    pjob = _var_job(client, exp.json()["job_id"])
    assert pjob["status"] == "done", pjob
    pkg = client.get("/matches/lanc/package/download")
    assert pkg.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(pkg.content))
    nevek = set(z.namelist())
    assert {"jelentes.html", "statisztika.csv", "elemzesek.json"} <= nevek
    elemzesek = json.loads(z.read("elemzesek.json").decode("utf-8"))
    assert elemzesek.get("_hibas_retegek") == [], (
        "a valódi láncon elhasalt rétegek: "
        + ", ".join(elemzesek.get("_hibas_retegek") or []))

    # 6) A nyomtatható jelentés magyar és teljes.
    html = z.read("jelentes.html").decode("utf-8")
    assert "<!DOCTYPE html>" in html
    assert "Elemzés megbízhatósága" in html

    # 7) KÉZI javítás a valódi láncon: a felvett gól átüt az
    #    esemény-listán, és a jelentés ki is mondja, hogy javítás van
    #    benne (a javítás a lövés-felismerésbe épül be, nem a
    #    végpontba).
    ov = client.post("/matches/lanc/event-overrides", json={"overrides": [
        {"op": "add", "t": 5, "type": "goal", "team": "home"}]})
    assert ov.status_code == 200, ov.text
    esemenyek = client.get("/matches/lanc/events").json()["events"]
    assert any(e["type"] == "goal" and e["t"] == 5 for e in esemenyek), \
        esemenyek
    rep2 = client.get("/matches/lanc/report/export")
    assert rep2.status_code == 200
    assert "Kézi javítás" in rep2.text

    # 8) Mezszám + név → a szezon-lapok megszólalnak. (Rövid videón
    #    kevés a mérés; itt az a kérdés, hogy a lánc ÉP-e, nem az,
    #    hogy mit mond.)
    trackek = {p["track_id"] for fr in client.get("/matches/lanc").json()
               ["frames"] for p in fr["players"]}
    if trackek:
        tid = sorted(trackek)[0]
        client.post("/matches/lanc/jerseys",
                    json={"track_id": tid, "jersey": 7})
        client.post("/library/players",
                    json={"team": "Hazai", "jersey": 7, "name": "Kovács"})
        keret = client.get("/library/roster",
                           params={"team": "Hazai"}).json()
        assert any(p["jersey"] == 7 and p["name"] == "Kovács"
                   for p in keret["players"]), keret
        fokusz = client.get("/players/focus",
                            params={"team": "Hazai", "jersey": 7})
        assert fokusz.status_code == 200
        assert isinstance(fokusz.json()["focus"], list)

    # 9) A heti munkalap: az edzésterv nyomtatható lapja elkészül és
    #    magyar. (Üres fókusznál is: az üres eredményt is ki kell
    #    mondani.)
    terv = client.get("/library/training-focus/export",
                      params={"team": "Hazai"})
    assert terv.status_code == 200
    assert "<!DOCTYPE html>" in terv.text
    assert "Edzésterv" in terv.text and "Hazai" in terv.text
