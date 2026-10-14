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
