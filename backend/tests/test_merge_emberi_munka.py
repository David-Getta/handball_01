"""
Tesztek arra, hogy az ÖSSZEFŰZÉS megőrzi az EMBERI munkát: a
jegyzeteket és a kézzel felvitt kiállításokat.

A jegyzet gépelt szöveg — nem újratermelhető adat. Aki hat klip közben
megjelölt tizenöt pillanatot, majd összefűzte a meccset, eddig mindet
elvesztette, némán.

A kockaszám a szakasz eltolásával mozog: enélkül a jegyzet egy MÁSIK
pillanatra mutatna, és a "koppints a visszanézéshez" rossz helyre
ugrana — ami rosszabb, mint ha el sem jutna oda.

Futtatás:
    python -m pytest tests/test_merge_emberi_munka.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient

from handball.models.tracking import (  # noqa: E402
    Ball, Frame, Match, MatchMeta,
)


def _resz(match_id, n, video):
    meta = MatchMeta(match_id=match_id, home_team="A", away_team="B",
                     fps=10.0, video_path=video)
    return Match(meta, [Frame(t=i, players=[], ball=Ball(x=1.0, y=1.0))
                        for i in range(n)])


def _client(reszek):
    tmp = tempfile.mkdtemp(prefix="hb_mergenotes_")
    os.environ["HANDBALL_DATA_DIR"] = tmp
    d = Path(tmp) / "data" / "matches"
    d.mkdir(parents=True, exist_ok=True)
    for m in reszek:
        (d / f"{m.meta.match_id}.json").write_text(
            json.dumps(m.to_dict()), encoding="utf-8")
    from handball.api.app import create_app
    return TestClient(create_app()), tmp


def test_a_jegyzetek_atjonnek_es_elcsusznak():
    a = _resz("k1", 20, "/v/a.mp4")
    b = _resz("k2", 20, "/v/b.mp4")
    c, _tmp = _client([a, b])
    c.post("/matches/k1/notes", json={"frame": 5, "text": "első klip"})
    c.post("/matches/k2/notes", json={"frame": 7, "text": "második klip"})

    r = c.post("/matches/merge", json={"ids": ["k1", "k2"],
                                       "match_id": "teljes"})
    assert r.status_code == 200

    jegyzetek = c.get("/matches/teljes/notes").json()["notes"]
    szoveg_ido = {j["text"]: j["frame"] for j in jegyzetek}
    assert szoveg_ido == {"első klip": 5, "második klip": 27}


def test_ugyanabbol_a_videobol_jovo_ket_szakasz_sem_csuszik_ossze():
    """ŐR: két szakasz jöhet UGYANABBÓL a fájlból (megszakadt
    feldolgozás folytatása).

    Ha a szakaszokat a videó ÚTJA szerint párosítanánk a részekhez, egy
    útvonal-kulcsú szótár összeolvasztaná őket, és a második rész
    jegyzetei az elsőre csúsznának — némán, mert a jegyzet ettől még
    ott lenne, csak rossz időn.
    """
    a = _resz("f1", 20, "/v/ugyanaz.mp4")
    b = _resz("f2", 20, "/v/ugyanaz.mp4")
    c, _tmp = _client([a, b])
    c.post("/matches/f1/notes", json={"frame": 2, "text": "elso"})
    c.post("/matches/f2/notes", json={"frame": 2, "text": "masodik"})

    c.post("/matches/merge", json={"ids": ["f1", "f2"],
                                   "match_id": "egyben"})
    jegyzetek = c.get("/matches/egyben/notes").json()["notes"]
    szoveg_ido = {j["text"]: j["frame"] for j in jegyzetek}
    assert szoveg_ido == {"elso": 2, "masodik": 22}, szoveg_ido


def test_jegyzet_nelkul_nem_keletkezik_fajl():
    """Visszafelé kompatibilis: jegyzet nélküli szakaszokból jegyzet
    nélküli meccs lesz — nem üres lista-fájl, nem kitalált bejegyzés."""
    c, _tmp = _client([_resz("n1", 10, "/v/a.mp4"),
                       _resz("n2", 10, "/v/b.mp4")])
    c.post("/matches/merge", json={"ids": ["n1", "n2"],
                                   "match_id": "ures"})
    assert c.get("/matches/ures/notes").json()["notes"] == []


def test_a_jegyzetek_idorendben_allnak():
    """Az összefűzött meccs jegyzetei a MECCS menetét kövessék: a
    szakaszonkénti felvételi sorrend itt semmit nem mondana."""
    a = _resz("s1", 20, "/v/a.mp4")
    b = _resz("s2", 20, "/v/b.mp4")
    c, _tmp = _client([a, b])
    c.post("/matches/s2/notes", json={"frame": 1, "text": "kesobb"})
    c.post("/matches/s1/notes", json={"frame": 9, "text": "korabban"})
    c.post("/matches/merge", json={"ids": ["s1", "s2"],
                                   "match_id": "sorrend"})
    jegyzetek = c.get("/matches/sorrend/notes").json()["notes"]
    assert [j["text"] for j in jegyzetek] == ["korabban", "kesobb"]
# ---- A kiállítások is emberi munka ----------------------------------


def test_a_kiallitasok_atjonnek_es_elcsusznak():
    """A kiállítás kézzel felvitt adat, és az EMBERELŐNY-rétegek
    (powerplay-hozam, hátrány-támadás, kiállítás-kiharcolás) ezen
    állnak. Összefűzéskor eddig elveszett, és ezek a rétegek némán
    elhallgattak — az edző pedig azt hitte, nincs mit mérni.

    Az idő MÁSODPERCBEN tolódik, mert a roster is másodpercben tárol.
    """
    a = _resz("r1", 100, "/v/a.mp4")   # 100 kocka / 10 fps = 10 mp
    b = _resz("r2", 100, "/v/b.mp4")
    c, tmp = _client([a, b])
    c.post("/matches/r1/roster", json={"suspensions": [
        {"team": "home", "start_s": 2.0, "duration_s": 120.0}]})
    c.post("/matches/r2/roster", json={"suspensions": [
        {"team": "away", "start_s": 3.0, "duration_s": 120.0}]})

    r = c.post("/matches/merge", json={"ids": ["r1", "r2"],
                                       "match_id": "teljes"})
    assert r.status_code == 200

    mentett = json.loads(
        (Path(tmp) / "data" / "matches" / "teljes.roster.json")
        .read_text(encoding="utf-8"))
    idok = [(k["team"], round(k["start_s"], 1))
            for k in mentett["suspensions"]]
    # A második szakasz 10 másodperccel később kezdődik.
    assert idok == [("home", 2.0), ("away", 13.0)], idok


def test_a_kapushiany_csak_egyetertesnel_orokol():
    """A kapus-hiány EGÉSZ meccsre szóló jelzés, tehát szakaszonként
    ellentmondhat. Amiről nem tudunk, arról ne állítsunk semmit —
    ugyanaz az elv, mint a kalibráltságnál.
    """
    a = _resz("g1", 100, "/v/a.mp4")
    b = _resz("g2", 100, "/v/b.mp4")
    c, tmp = _client([a, b])
    c.post("/matches/g1/roster", json={
        "suspensions": [{"team": "home", "start_s": 1.0,
                         "duration_s": 120.0}],
        "gk_absent_home": True})
    c.post("/matches/g2/roster", json={
        "suspensions": [{"team": "home", "start_s": 1.0,
                         "duration_s": 120.0}],
        "gk_absent_home": False})

    c.post("/matches/merge", json={"ids": ["g1", "g2"],
                                   "match_id": "vegyes"})
    mentett = json.loads(
        (Path(tmp) / "data" / "matches" / "vegyes.roster.json")
        .read_text(encoding="utf-8"))
    assert not mentett.get("gk_absent_home"), mentett


def test_kiallitas_nelkul_nem_keletkezik_roster():
    """Visszafelé kompatibilis: kiállítás nélküli szakaszokból nem
    keletkezik üres roster-fájl."""
    c, tmp = _client([_resz("q1", 50, "/v/a.mp4"),
                      _resz("q2", 50, "/v/b.mp4")])
    c.post("/matches/merge", json={"ids": ["q1", "q2"],
                                   "match_id": "nincs"})
    assert not (Path(tmp) / "data" / "matches"
                / "nincs.roster.json").exists()
