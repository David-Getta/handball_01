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
    kivétel — a vezető VR-ből is vezethet)."""
    assert all(m == "GET" for m, r in HALOZATI_ENGEDETT if "shared3d" not in r)
    assert len(HALOZATI_ENGEDETT) == 7
