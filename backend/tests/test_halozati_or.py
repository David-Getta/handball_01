"""A hálózati őr: ha a motor a hálózat felé is nyitva van
(HANDBALL_HOST nem a saját gép), a más gépről jövő kérés csak a közös
nézés követő-útját éri el; a saját gépről minden megy; alapból nincs őr."""
from fastapi.testclient import TestClient

from handball.api.app import HALOZATI_ENGEDETT, create_app
from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                      PlayerPosition, PositionSource, Team)


def _meccs():
    frames = [Frame(t=t, players=[PlayerPosition(
        track_id=1, team=Team.HOME, x=20.0, y=10.0,
        source=PositionSource.MEASURED, confidence=1.0)],
        ball=Ball(x=20.0, y=10.0, confidence=1.0)) for t in range(10)]
    return Match(MatchMeta(match_id="halo", home_team="A", away_team="B",
                           fps=25.0), frames)


def _app(tmp_path, monkeypatch, host):
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    if host is None:
        monkeypatch.delenv("HANDBALL_HOST", raising=False)
    else:
        monkeypatch.setenv("HANDBALL_HOST", host)
    app = create_app()
    app.state.put_match(_meccs())
    return app


def test_a_halozatrol_csak_a_kozos_nezes_erheto_el(tmp_path, monkeypatch):
    app = _app(tmp_path, monkeypatch, "0.0.0.0")
    tavoli = TestClient(app, client=("192.168.1.23", 50000))
    helyi = TestClient(app, client=("127.0.0.1", 50000))
    # A követő-út nyitva (a 404 a hiányzó videó — nem az őr).
    assert tavoli.get("/matches/halo/view3d").status_code == 200
    assert tavoli.get("/matches/halo/shared3d").status_code == 200
    assert tavoli.put("/matches/halo/shared3d", json={"t": 1}).status_code == 200
    assert tavoli.get("/matches/halo/notes").status_code == 200
    assert tavoli.get("/library/players").status_code == 200
    assert tavoli.get("/kovet", follow_redirects=False).status_code in (200, 307)
    assert tavoli.get("/matches/halo/frame", params={"t": 0}).status_code != 403
    # A felvételek visszajátszása is (olvasás) — a mentés és a törlés nem.
    assert tavoli.get("/matches/halo/felvetelek").status_code == 200
    assert tavoli.post("/matches/halo/felvetelek", json={}).status_code == 403
    assert tavoli.delete("/matches/halo/felvetelek/abc").status_code == 403
    # A hang is letölthető (404: nincs ilyen) — a feltöltése nem.
    assert tavoli.get("/matches/halo/felvetelek/abc/hang").status_code == 404
    assert tavoli.put("/matches/halo/felvetelek/abc/hang",
                      content=b"x").status_code == 403
    # A "megnéztem" jelzés is (404: nincs ilyen felvétel — nem az őr).
    assert tavoli.post("/matches/halo/felvetelek/abc/megnezte",
                       json={"nev": "Anna"}).status_code == 404
    # A tervező figurája 3D-ben is (a várólap linkeli).
    assert tavoli.get("/figura3d", params={"u": "20,10"}).status_code == 200
    # A three.js is (a 3D oldal a motorból tölti).
    assert tavoli.get("/vendor/three@0.160.0/build/three.module.js").status_code == 200
    # A többi zárva — a nem létező út is (az őr az útválasztás előtt áll).
    for ut in ("/library/notes", "/library/quiz-stats", "/matches/halo/report",
               "/nincs-ilyen"):
        r = tavoli.get(ut)
        assert r.status_code == 403, ut
        assert "közös nézés" in r.json()["detail"]
    assert tavoli.post("/matches/halo/notes",
                       json={"frame": 1, "text": "x"}).status_code == 403
    assert tavoli.delete("/matches/halo/notes/x").status_code == 403
    # A saját gépről minden megy.
    assert helyi.get("/library/notes").status_code == 200
    assert helyi.post("/matches/halo/notes",
                      json={"frame": 1, "text": "x"}).status_code == 200
    # IPv6 loopback is a saját gép.
    assert TestClient(app, client=("::1", 1)).get(
        "/library/notes").status_code == 200


def test_alapbol_nincs_halozati_or(tmp_path, monkeypatch):
    for host in (None, "127.0.0.1", "localhost"):
        app = _app(tmp_path, monkeypatch, host)
        tavoli = TestClient(app, client=("192.168.1.23", 50000))
        assert tavoli.get("/library/notes").status_code == 200, host


def test_az_engedett_utak_a_kovetohoz_kellenek():
    """Az engedett utak listája szűk: csak olvasás (a közös nézés állapota
    kivétel — a vezető VR-ből is vezethet —, és a felvétel "megnéztem"
    jelzése, ami a headsetről jön)."""
    assert all(m == "GET" for m, r in HALOZATI_ENGEDETT
               if "shared3d" not in r and "megnezte" not in r)
    assert [m for m, r in HALOZATI_ENGEDETT if "megnezte" in r] == ["POST"]
    assert len(HALOZATI_ENGEDETT) == 11


def test_a_halozati_csapat_link(tmp_path, monkeypatch):
    """GET /halozat: saját gépes módban nem hálózati, üres lista; hálózati
    módban a /kovet a gép hálózati címeivel, azon a porton, amelyen a kérés
    jött (a motor tartalék porton is futhat). Az oldal és az app ezt adja a
    csapatnak."""
    from pathlib import Path

    import handball.api.app as appmod

    monkeypatch.setattr(appmod, "halozati_cimek",
                        lambda: ["192.168.1.23", "10.0.0.5"])
    app = _app(tmp_path, monkeypatch, None)
    helyi = TestClient(app, base_url="http://testserver:8000",
                       client=("127.0.0.1", 1))
    assert helyi.get("/halozat").json() == {"halozati": False, "linkek": []}
    app = _app(tmp_path, monkeypatch, "0.0.0.0")
    helyi = TestClient(app, base_url="http://testserver:8017",
                       client=("127.0.0.1", 1))
    assert helyi.get("/halozat").json() == {
        "halozati": True,
        "linkek": ["http://192.168.1.23:8017/kovet",
                   "http://10.0.0.5:8017/kovet"]}
    # A headsetnek nem kell (a hálózati őr zárja).
    assert TestClient(app, client=("192.168.1.50", 1)).get(
        "/halozat").status_code == 403

    from handball.pipeline.view3d_html import view3d_html
    oldal = view3d_html(_meccs())
    assert 'fetch("/halozat").then(r => r.ok ? r.json() : null).then(h => {' in oldal
    assert "kzLink = h.linkek[0];" in oldal
    gyoker = Path(__file__).resolve().parents[2] / "client" / "lib"
    palya = (gyoker / "ui" / "court3d_screen.dart").read_text(encoding="utf-8")
    api = (gyoker / "services" / "api_client.dart").read_text(encoding="utf-8")
    assert "_api.fetchNetworkLinks().then((linkek) {" in palya
    assert '"$baseUrl/halozat"' in api


def test_a_gep_halozati_cimei():
    """A felderítés nem dob, és nem ad saját gépes (loopback) címet."""
    import ipaddress

    from handball.api.app import halozati_cimek

    cimek = halozati_cimek()
    assert isinstance(cimek, list)
    for c in cimek:
        ip = ipaddress.ip_address(c)
        assert ip.version == 4 and not ip.is_loopback, c


def test_a_klub_halozat_az_appbol():
    """Az app 3D fülének kapcsolója elmenti a beállítást, a motor-indító a
    lemezről olvassa, és klub-hálózatban 0.0.0.0-ra köt — ilyenkor a motor
    hálózati őre kapcsol be (a host-ellenőrzés ugyanazokat az értékeket
    ismeri)."""
    from pathlib import Path

    gyoker = Path(__file__).resolve().parents[2] / "client" / "lib"
    inditas = (gyoker / "services" / "backend_launcher.dart").read_text(
        encoding="utf-8")
    tar = (gyoker / "services" / "session_store.dart").read_text(encoding="utf-8")
    palya = (gyoker / "ui" / "court3d_screen.dart").read_text(encoding="utf-8")
    assert '"HANDBALL_HOST": clubNetwork ? "0.0.0.0" : "127.0.0.1",' in inditas
    assert "final klub = await SessionStore.clubNetworkFromDisk();" in inditas
    assert "environment: engineEnvironment(clubNetwork: klub, port: port)," in inditas
    assert '"club_network": clubNetwork,' in tar
    assert 'data["club_network"] == true' in tar
    for kell in ("onPressed: _klubHalozatValt,",
                 "await SessionStore.setClubNetwork(be);",
                 "Csak megbízható, zárt hálózaton kapcsold be."):
        assert kell in palya, kell
    # A motor oldalon ugyanaz a két érték: 0.0.0.0 nyitott, 127.0.0.1 nem.
    import os

    from handball.api.app import halozati_nyitott
    regi = os.environ.get("HANDBALL_HOST")
    try:
        os.environ["HANDBALL_HOST"] = "0.0.0.0"
        assert halozati_nyitott()
        os.environ["HANDBALL_HOST"] = "127.0.0.1"
        assert not halozati_nyitott()
    finally:
        if regi is None:
            os.environ.pop("HANDBALL_HOST", None)
        else:
            os.environ["HANDBALL_HOST"] = regi


# ---- Az őr telepítője közvetlenül (harmadik kör) ----------------------------

def _csupasz_app(monkeypatch, host):
    """Egy csupasz FastAPI alkalmazás két úttal — csak az őr telepítője
    fut rá (a teljes motor nélkül)."""
    from fastapi import FastAPI

    from handball.api.app import _halozati_or_telepit

    if host is None:
        monkeypatch.delenv("HANDBALL_HOST", raising=False)
    else:
        monkeypatch.setenv("HANDBALL_HOST", host)
    app = FastAPI()

    @app.get("/kovet")
    def kovet():
        return {"ok": "kovet"}

    @app.get("/titkos")
    def titkos():
        return {"ok": "titkos"}

    @app.post("/kovet")
    def kovet_iras():
        return {"ok": "iras"}

    _halozati_or_telepit(app)
    return app


def test_halozati_or_telepit_alapbol_nem_telepit_semmit(monkeypatch):
    """Alapból (a motor csak a saját gépen hallgat: nincs HANDBALL_HOST,
    vagy az 127.0.0.1 / localhost / ::1 / üres) az őr NINCS telepítve —
    egy "távoli" kérés is mindent elér (a hálózat felől úgysem jöhet)."""
    for host in (None, "127.0.0.1", "localhost", "::1", "", "  "):
        app = _csupasz_app(monkeypatch, host)
        assert app.user_middleware == [], host
        tavoli = TestClient(app, client=("192.168.1.23", 50000))
        assert tavoli.get("/titkos").json() == {"ok": "titkos"}


def test_halozati_or_telepit_nyitott_motornal_csak_az_engedett_ut(
        monkeypatch):
    """Hálózatra nyitott motornál (HANDBALL_HOST = 0.0.0.0 vagy a gép
    címe) a más gépről jövő kérés csak az engedett út + módszer párost
    éri el; a többi 403 beszélő üzenettel — a nem létező út is (az őr az
    útválasztás előtt áll)."""
    for host in ("0.0.0.0", "192.168.1.10"):
        app = _csupasz_app(monkeypatch, host)
        assert len(app.user_middleware) == 1, host
        tavoli = TestClient(app, client=("192.168.1.23", 50000))
        assert tavoli.get("/kovet").json() == {"ok": "kovet"}
        for valasz in (tavoli.get("/titkos"), tavoli.get("/nincs-ilyen"),
                       tavoli.post("/kovet")):      # a /kovet csak GET-tel
            assert valasz.status_code == 403
            assert valasz.json()["detail"].startswith(
                "a hálózatról csak a közös nézés érhető el")


def test_halozati_or_telepit_a_sajat_geprol_minden_megy(monkeypatch):
    """A saját gépről (loopback IPv4 / IPv6, "localhost") a nyitott
    motornál is minden megy; ami nem cím és nem "localhost" (ismeretlen
    kliens), az távolinak számít — az őr a biztonságos oldalra téved."""
    app = _csupasz_app(monkeypatch, "0.0.0.0")
    for cim in ("127.0.0.1", "127.0.0.53", "::1", "localhost"):
        helyi = TestClient(app, client=(cim, 50000))
        assert helyi.get("/titkos").json() == {"ok": "titkos"}, cim
        assert helyi.post("/kovet").json() == {"ok": "iras"}, cim
    for cim in ("testclient", "10.0.0.5", "nem-cim"):
        idegen = TestClient(app, client=(cim, 50000))
        assert idegen.get("/titkos").status_code == 403, cim
        assert idegen.get("/kovet").status_code == 200, cim
