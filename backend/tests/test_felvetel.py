"""⏺ FELVÉTEL — a megbeszélés felvétele és visszajátszása: az állapot
megtisztítása, a motor végpontjai, az oldal (rögzítés a vezető
küldésével, visszajátszás a követés útján)."""
from fastapi.testclient import TestClient

from handball.api.app import create_app
from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                      PlayerPosition, PositionSource, Team)
from handball.pipeline.court3d import (SHARED3D_REC_MAX,
                                       shared3d_felvetel_allapot)


def _meccs():
    frames = [Frame(t=t, players=[PlayerPosition(
        track_id=1, team=Team.HOME, x=20.0, y=10.0,
        source=PositionSource.MEASURED, confidence=1.0)],
        ball=Ball(x=20.0, y=10.0, confidence=1.0)) for t in range(10)]
    return Match(MatchMeta(match_id="fv", home_team="A", away_team="B",
                           fps=25.0), frames)


def test_az_allapot_megtisztitasa():
    a = shared3d_felvetel_allapot({
        "t": 61.234, "playing": 1, "speed": 2, "rajz": "20,13.1,28.4,16.8,0",
        "mutato": {"x": 99, "y": -9, "n": 5},
        "nezopont": {"x": 1, "y": 500, "z": -99, "yaw": 1.5, "pitch": 3, "n": 7}})
    assert a == {"t": 61.23, "playing": True, "speed": 2.0,
                 "rajz": "20,13.1,28.4,16.8,0",
                 "mutato": {"x": 45.0, "y": -5.0, "n": 5.0},
                 "nezopont": {"x": 1.0, "y": 60.0, "z": -60.0, "yaw": 1.5,
                              "pitch": 1.6, "n": 7.0}}
    # Rossz rajz és mutató kimarad, az állapot megmarad.
    a = shared3d_felvetel_allapot({"t": 1, "rajz": "<b>", "mutato": {"x": "a"}})
    assert a == {"t": 1.0, "playing": False, "speed": 1.0, "rajz": ""}
    for rossz in (None, [], {"t": "x"}, {"t": 1, "speed": 20},
                  {"t": float("inf")}):
        assert shared3d_felvetel_allapot(rossz) is None, rossz


def test_a_felvetel_vegpontjai(tmp_path, monkeypatch):
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    app = create_app()
    app.state.put_match(_meccs())
    c = TestClient(app)
    url = "/matches/fv/felvetelek"
    assert c.get(url).json() == {"felvetelek": []}
    allapotok = [[1.2, {"t": 31, "playing": True, "speed": 1}],
                 [0.0, {"t": 30, "playing": True, "speed": 1,
                        "mutato": {"x": 20, "y": 10, "n": 3}}],
                 ["x", {"t": 1}], [0.6, {"t": "rossz"}], "rossz"]
    r = c.post(url, json={"nev": "Hétfői\x07 megbeszélés", "allapotok": allapotok})
    assert r.status_code == 200
    d = r.json()
    assert (d["nev"], d["hossz_s"], d["db"]) == ("Hétfői megbeszélés", 1.2, 2)
    teljes = c.get(f"{url}/{d['id']}").json()
    assert [s[0] for s in teljes["allapotok"]] == [0.0, 1.2]
    assert teljes["allapotok"][0][1]["mutato"] == {"x": 20.0, "y": 10.0, "n": 3.0}
    # A lista a legújabb elöl; név nélkül "Megbeszélés".
    d2 = c.post(url, json={"allapotok": allapotok[:2]}).json()
    lista = c.get(url).json()["felvetelek"]
    assert {f["id"] for f in lista} == {d["id"], d2["id"]}
    assert d2["nev"] == "Megbeszélés"
    # Rossz kérések.
    assert c.post(url, json={"allapotok": allapotok[2:]}).status_code == 400
    assert c.post(url, json={"allapotok": "x"}).status_code == 400
    tul = [[i * 0.3, {"t": 1}] for i in range(SHARED3D_REC_MAX + 1)]
    assert c.post(url, json={"allapotok": tul}).status_code == 400
    assert c.post("/matches/nincs/felvetelek",
                  json={"allapotok": allapotok}).status_code == 404
    for rossz in ("nincs", "../x", "a.b"):
        assert c.get(f"{url}/{rossz}").status_code == 404, rossz
    # Törlés.
    assert c.delete(f"{url}/{d['id']}").json() == {"ok": True}
    assert c.get(f"{url}/{d['id']}").status_code == 404
    assert c.delete(f"{url}/{d['id']}").status_code == 404
    assert [f["id"] for f in c.get(url).json()["felvetelek"]] == [d2["id"]]


def test_az_oldal_rogzit_es_visszajatszik():
    from handball.pipeline.view3d_html import view3d_html

    oldal = view3d_html(_meccs())
    for kell in ('id="felvetelGomb"', 'id="felvetelValaszto"',
                 "function kzAllapotAlkalmaz(a){", "kzAllapotAlkalmaz(a);",
                 "    felvetelRogzit();\n    fetch(kzCim(), {method: \"PUT\",",
                 "felvetelAll();\n  if (elozo === \"vezet\" && kozosMod !== \"vezet\" && kzFelvetel) felvetelMent();",
                 "jelenletFrissit(dt); felvetelFrissit(); valaszJelFrissit();",
                 "else if (fvLejatszas) felvetelGomb.onclick();",
                 "felvetelListaBetolt();", "⏺ Felvétel: a megbeszélés visszanézhető"):
        assert kell in oldal, kell
    assert f"const FV_MAX = {SHARED3D_REC_MAX};" in oldal
    assert "__FV_MAX__" not in oldal


def test_a_felvetelek_az_appban(tmp_path, monkeypatch):
    """Az app vezetője is rögzít, a 3D fül "▶ Felvételek" listája
    megnyit (?felvetel=<id> — a böngésző magától indítja), átnevez
    (PATCH) és töröl; a Dart-állandók a motoréi."""
    import re
    from pathlib import Path

    from handball.pipeline.court3d import SHARED3D_REC_NAME_MAX
    from handball.pipeline.view3d_html import view3d_html

    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    app = create_app()
    app.state.put_match(_meccs())
    c = TestClient(app)
    url = "/matches/fv/felvetelek"
    d = c.post(url, json={"nev": "x", "allapotok": [
        [0, {"t": 1}], [0.3, {"t": 1.3}]]}).json()
    r = c.patch(f"{url}/{d['id']}", json={"nev": "  Védekezés\x07 6-0  "})
    assert r.json() == {"id": d["id"], "nev": "Védekezés 6-0"}
    assert c.get(url).json()["felvetelek"][0]["nev"] == "Védekezés 6-0"
    assert c.get(f"{url}/{d['id']}").json()["nev"] == "Védekezés 6-0"
    assert c.patch(f"{url}/{d['id']}", json={}).json()["nev"] == "Megbeszélés"
    hosszu = c.patch(f"{url}/{d['id']}", json={"nev": "a" * 200}).json()
    assert len(hosszu["nev"]) == SHARED3D_REC_NAME_MAX
    for rossz in ("nincs", "a.b"):
        assert c.patch(f"{url}/{rossz}", json={"nev": "y"}).status_code == 404
    assert c.patch("/matches/nincs/felvetelek/abc",
                   json={"nev": "y"}).status_code == 404

    oldal = view3d_html(_meccs())
    assert 'let fvUrlIndit = URL_PARAM.get("felvetel") || "";' in oldal
    assert "felvetelValaszto.value = kert; felvetelIndit(kert);" in oldal

    gyoker = Path(__file__).resolve().parents[2] / "client" / "lib"
    geo = (gyoker / "ui" / "court_geometry.dart").read_text(encoding="utf-8")
    assert f"const int recordingMax = {SHARED3D_REC_MAX};" in geo
    assert f"const int recordingNameMax = {SHARED3D_REC_NAME_MAX};" in geo
    palya = (gyoker / "ui" / "court3d_screen.dart").read_text(encoding="utf-8")
    for kell in ("onPressed: _felvetelValt,", "onPressed: _felvetelekNyit,",
                 'q\n        ..clear()\n        ..["felvetel"] = felvetel;',
                 "if (!be) _felvetelMent();",
                 "_felvetelMent(csendes: true);",
                 "if (f.length >= recordingMax) _felvetelMent();"):
        assert kell in palya, kell
    # Az app ugyanazokat a mezőket rögzíti, amiket a motor megtisztít.
    rogzit = palya.split("final f = _felvetel;", 1)[1].split("_api", 1)[0]
    assert set(re.findall(r'"(\w+)":', rogzit)) == {
        "t", "playing", "speed", "rajz", "mutato", "nezopont"}
    api = (gyoker / "services" / "api_client.dart").read_text(encoding="utf-8")
    for kell in ("Future<Map<String, dynamic>> saveRecording(",
                 "Future<List<Map<String, dynamic>>> fetchRecordings(",
                 "Future<void> renameRecording(",
                 "Future<void> deleteRecording("):
        assert kell in api, kell
    assert "internet kell" not in palya


def test_a_felvetel_hangja(tmp_path, monkeypatch):
    """🎙 A hang feltöltése, letöltése (tekerhető), a listában jelölve, a
    törléssel együtt megy; rossz kérések. Az oldal rögzít és szinkronban
    játszik vissza."""
    from handball.pipeline.court3d import (SHARED3D_REC_AUDIO_MAX,
                                           SHARED3D_REC_AUDIO_TYPES)
    from handball.pipeline.view3d_html import view3d_html

    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    app = create_app()
    app.state.put_match(_meccs())
    c = TestClient(app)
    url = "/matches/fv/felvetelek"
    d = c.post(url, json={"allapotok": [[0, {"t": 1}], [4.5, {"t": 5.5}]]}).json()
    assert c.get(url).json()["felvetelek"][0]["hang"] is False
    assert c.get(f"{url}/{d['id']}/hang").status_code == 404
    hang = bytes(range(256)) * 40
    r = c.put(f"{url}/{d['id']}/hang", params={"eltolas": 1.234}, content=hang,
              headers={"Content-Type": "audio/webm;codecs=opus"})
    assert r.status_code == 200
    assert r.json()["hang"] == {"tipus": "audio/webm", "eltolas": 1.23,
                                "meret": len(hang)}
    assert c.get(url).json()["felvetelek"][0]["hang"] is True
    assert c.get(f"{url}/{d['id']}").json()["hang"]["eltolas"] == 1.23
    le = c.get(f"{url}/{d['id']}/hang")
    assert le.status_code == 200 and le.content == hang
    assert le.headers["content-type"].startswith("audio/webm")
    resz = c.get(f"{url}/{d['id']}/hang", headers={"Range": "bytes=10-19"})
    assert resz.status_code == 206 and resz.content == hang[10:20]
    # Az eltolás a felvétel hosszába szorul; a NaN 0.
    for e, vart in ((99, 4.5), (-3, 0.0), ("nan", 0.0)):
        r = c.put(f"{url}/{d['id']}/hang", params={"eltolas": e}, content=b"ab",
                  headers={"Content-Type": "audio/ogg"})
        assert r.json()["hang"]["eltolas"] == vart, e
    # Rossz kérések.
    assert c.put(f"{url}/{d['id']}/hang", content=b"ab",
                 headers={"Content-Type": "text/html"}).status_code == 415
    assert c.put(f"{url}/{d['id']}/hang", content=b"",
                 headers={"Content-Type": "audio/mp4"}).status_code == 400
    assert c.put(f"{url}/nincs/hang", content=b"ab",
                 headers={"Content-Type": "audio/mp4"}).status_code == 404
    assert c.put(f"{url}/{d['id']}/hang", content=b"ab",
                 headers={"Content-Type": "audio/mp4",
                          "Content-Length": str(SHARED3D_REC_AUDIO_MAX + 1)}
                 ).status_code == 413
    assert "audio/webm" in SHARED3D_REC_AUDIO_TYPES
    # A törlés a hangot is viszi.
    assert c.delete(f"{url}/{d['id']}").json() == {"ok": True}
    assert not list((tmp_path).rglob("*.hang"))

    oldal = view3d_html(_meccs())
    for kell in ("felvetelHangIndit(kzFelvetel);",
                 "const hang = f ? await felvetelHangLeallit(f.hang) : null;",
                 '"/hang?eltolas="', "felvetelHangFrissit(f, e);",
                 'fvHangForras(adat.hang ? fvCim() + "/" + encodeURIComponent(id) + "/hang" : "");',
                 "🎙 a hangoddal is"):
        assert kell in oldal, kell


def test_a_felvetel_fejezetei():
    """Fejezet ott kezdődik, ahol az edző a meccsben ugrott — a lejátszás
    (bármilyen sebességgel) és a szünet nem ugrás; a csúszka-húzás sok
    gyors ugrása egy fejezet, az utolsó landolással."""
    from handball.pipeline.court3d import (SHARED3D_REC_CHAPTER_JUMP_S,
                                           SHARED3D_REC_CHAPTER_MIN_S,
                                           shared3d_felvetel_fejezetek)

    def a(t, megy=True, seb=1.0):
        return {"t": t, "playing": megy, "speed": seb}

    allapotok = [[0.0, a(100)], [0.3, a(100.3)], [0.6, a(100.6)],
                 [0.9, a(100.6, seb=2)], [1.2, a(101.2, seb=2)],
                 [1.5, a(101.8, False)], [6.0, a(101.8, False)],
                 [6.3, a(300, False)],
                 [20.0, a(500)], [20.3, a(520)], [20.6, a(540)],
                 [20.9, a(540.3)], [30.0, a(549.4)]]
    assert shared3d_felvetel_fejezetek(allapotok) == [
        [0.0, 100.0], [6.3, 300.0], [20.6, 540.0]]
    # A felvétel eleje utáni gyors ugrás új fejezet (az eleje marad).
    assert shared3d_felvetel_fejezetek([[0, a(100)], [1.0, a(400)]]) == [
        [0.0, 100.0], [1.0, 400.0]]
    # A küszöb alatti eltérés (kerekítés, egy kicsi tekerés) nem fejezet.
    kis = SHARED3D_REC_CHAPTER_JUMP_S - 0.5
    assert len(shared3d_felvetel_fejezetek(
        [[0, a(100, False)], [5, a(100 + kis, False)]])) == 1
    assert SHARED3D_REC_CHAPTER_MIN_S < SHARED3D_REC_CHAPTER_JUMP_S
    assert shared3d_felvetel_fejezetek([]) == []


def test_a_fejezetek_a_vegpontokon_es_az_oldalon(tmp_path, monkeypatch):
    from handball.pipeline.view3d_html import view3d_html

    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    app = create_app()
    app.state.put_match(_meccs())
    c = TestClient(app)
    url = "/matches/fv/felvetelek"
    d = c.post(url, json={"allapotok": [
        [0, {"t": 1, "playing": False}], [4, {"t": 1, "playing": False}],
        [4.3, {"t": 8, "playing": False}], [9, {"t": 8, "playing": False}]]}).json()
    assert c.get(f"{url}/{d['id']}").json()["fejezetek"] == [[0.0, 1.0], [4.3, 8.0]]
    assert c.get(url).json()["felvetelek"][0]["fejezetek"] == 2

    oldal = view3d_html(_meccs())
    for kell in ('id="fejezetValaszto"', "fejezetListaToltes(adat);",
                 "if (fvLejatszas) felvetelFejezet(1); else jelenetLep(1);",
                 "if (fvLejatszas) felvetelFejezet(-1); else jelenetLep(-1);",
                 ". fejezet (N / P)"):
        assert kell in oldal, kell
    # A billentyű és a VR-gomb is (két-két hely).
    assert oldal.count("if (fvLejatszas) felvetelFejezet(1); else jelenetLep(1);") == 2


def test_a_meccs_torlese_a_felveteleit_is_torli(tmp_path, monkeypatch):
    """A meccs törlése a felvételeit és hangjukat is viszi (eddig árván
    maradtak); az oldal a hang leállítását időkorláttal végzi, a nem
    tölthető hangot megnevezi, és felvétel közben a bezárás előtt kérdez."""
    from handball.pipeline.view3d_html import view3d_html

    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    app = create_app()
    app.state.put_match(_meccs())
    c = TestClient(app)
    url = "/matches/fv/felvetelek"
    d = c.post(url, json={"allapotok": [[0, {"t": 1}], [1, {"t": 2}]]}).json()
    assert c.put(f"{url}/{d['id']}/hang", content=b"ab",
                 headers={"Content-Type": "audio/webm"}).status_code == 200
    assert list(tmp_path.rglob("fv.felvetelek/*"))
    assert c.delete("/matches/fv").status_code == 200
    assert not list(tmp_path.rglob("fv.felvetelek"))
    assert not list(tmp_path.rglob("*.hang"))

    oldal = view3d_html(_meccs())
    for kell in ("setTimeout(vege, FV_HANG_STOP_MS);",
                 'addEventListener("beforeunload", (e) => {',
                 'if (err && err.name === "NotAllowedError")',
                 "a hang nem tölthető"):
        assert kell in oldal, kell


def test_ki_nezte_meg(tmp_path, monkeypatch):
    """A néző jelzése a névvel (kis- és nagybetű, szóköz nem számít — az
    újabb felülírja), a listában a megnézés sorrendjében; rossz kérések; a
    felvétel törlése a megnézőket is viszi. Az oldal a ténylegesen
    lejátszott idő után, névvel küldi."""
    from handball.pipeline.court3d import SHARED3D_REC_WATCHED_FRAC
    from handball.pipeline.view3d_html import view3d_html

    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    app = create_app()
    app.state.put_match(_meccs())
    c = TestClient(app)
    url = "/matches/fv/felvetelek"
    d = c.post(url, json={"allapotok": [[0, {"t": 1}], [1, {"t": 2}]]}).json()
    assert c.get(url).json()["felvetelek"][0]["nezok"] == []
    meg = f"{url}/{d['id']}/megnezte"
    assert c.post(meg, json={"nev": "Anna"}).json() == {"nezok": ["Anna"]}
    assert c.post(meg, json={"nev": " Peti\x07 "}).json()["nezok"] == ["Anna", "Peti"]
    assert c.post(meg, json={"nev": "anna "}).json()["nezok"] in (
        ["Peti", "anna"], ["anna", "Peti"])
    assert len(c.get(url).json()["felvetelek"][0]["nezok"]) == 2
    assert c.post(meg, json={"nev": "  "}).status_code == 400
    assert c.post(meg, json={}).status_code == 400
    assert c.post(f"{url}/nincs/megnezte", json={"nev": "A"}).status_code == 404
    assert c.post("/matches/x/felvetelek/a/megnezte",
                  json={"nev": "A"}).status_code == 404
    assert c.delete(f"{url}/{d['id']}").json() == {"ok": True}
    assert not list(tmp_path.rglob("*.nezok"))

    oldal = view3d_html(_meccs())
    assert f"const FV_MEGNEZTE = {SHARED3D_REC_WATCHED_FRAC!r};" in oldal
    for kell in ('"/megnezte", {method: "POST",',
                 "(f.nezett || 0) >= hossz * FV_MEGNEZTE",
                 "if (!KZ_NEV) nevValasztoMutat(true);", "✓ megnézted",
                 "✓ megnézted (az edző látja)"):
        assert kell in oldal, kell


def test_a_legutobbi_megbeszelesek(tmp_path, monkeypatch):
    """GET /library/recordings: meccsektől függetlenül, a legújabb elöl, a
    meccs csapataival és a megnézőkkel; limit; a kezdőlap kártyája és a
    közös böngésző-nyitó (Windowson nem a cmd — az a címet az első &-nél
    elvágta)."""
    import json
    from pathlib import Path

    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    app = create_app()
    for mid in ("egy", "ket"):
        m = _meccs()
        m.meta.match_id = mid
        m.meta.home_team = mid.upper()
        app.state.put_match(m)
    c = TestClient(app)
    assert c.get("/library/recordings").json() == {"felvetelek": [], "osszes": 0}
    all_ = [[0, {"t": 1}], [1, {"t": 2}]]
    regi = c.post("/matches/egy/felvetelek", json={"nev": "Régi", "allapotok": all_}).json()
    uj = c.post("/matches/ket/felvetelek", json={"nev": "Új", "allapotok": all_}).json()
    fajl = next(tmp_path.rglob(f"egy.felvetelek/{regi['id']}.json"))
    d = json.loads(fajl.read_text(encoding="utf-8"))
    d["letrehozva"] = "2000-01-01T00:00:00"
    fajl.write_text(json.dumps(d), encoding="utf-8")
    c.post(f"/matches/ket/felvetelek/{uj['id']}/megnezte", json={"nev": "Anna"})
    r = c.get("/library/recordings").json()
    assert r["osszes"] == 2
    assert [(f["match_id"], f["home_team"], f["nev"], f["nezok"])
            for f in r["felvetelek"]] == [("ket", "KET", "Új", ["Anna"]),
                                          ("egy", "EGY", "Régi", [])]
    assert len(c.get("/library/recordings", params={"limit": 1}).json()[
        "felvetelek"]) == 1
    assert len(c.get("/library/recordings", params={"limit": 0}).json()[
        "felvetelek"]) == 1
    # A sérült megnéző-fájl nem dönti el a listát.
    next(tmp_path.rglob(f"{uj['id']}.json")).with_suffix(".nezok").write_text(
        "[1, 2]", encoding="utf-8")
    assert c.get("/library/recordings").json()["felvetelek"][0]["nezok"] == []

    gyoker = Path(__file__).resolve().parents[2] / "client" / "lib"
    nyito = (gyoker / "services" / "browser_open.dart").read_text(encoding="utf-8")
    assert '"rundll32", ["url.dll,FileProtocolHandler", url]' in nyito
    assert '"/c", "start"' not in nyito
    for nev in ("ui/court3d_screen.dart", "ui/dashboard_screen.dart"):
        src = (gyoker / nev).read_text(encoding="utf-8")
        assert "await openInBrowser(url);" in src, nev
        assert '"/c", "start"' not in src, nev
    dash = (gyoker / "ui" / "dashboard_screen.dart").read_text(encoding="utf-8")
    assert "..._recordingsCard()," in dash
    assert "_api.fetchLibraryRecordings().then((r) {" in dash
