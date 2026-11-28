"""A three.js a motorból: a 3D/VR oldal internet nélkül is betölt — a
csomagolt fájlok változatlanok (a npm-csomag hash-ei), a motor
kiszolgálja (tömörítve is), az oldal import-térképe ide mutat, a
csomagolás viszi."""
import gzip
import hashlib
from pathlib import Path

from fastapi.testclient import TestClient

from handball.api.app import create_app
from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                      PlayerPosition, PositionSource, Team)

GYOKER = Path(__file__).resolve().parents[2]
HASH = {
    "build/three.module.js":
        "76dea8151bc9352aef3528b4262e249b2604f62543828328db978d060d61a495",
    "examples/jsm/webxr/VRButton.js":
        "8ed40aedce76a40992a28980af9adf98543ce4233ea5649781245929a8fa052d",
}


def _meccs():
    frames = [Frame(t=t, players=[PlayerPosition(
        track_id=1, team=Team.HOME, x=20.0, y=10.0,
        source=PositionSource.MEASURED, confidence=1.0)],
        ball=Ball(x=20.0, y=10.0, confidence=1.0)) for t in range(10)]
    return Match(MatchMeta(match_id="h3", home_team="A", away_team="B",
                           fps=25.0), frames)


def test_a_csomagolt_three_valtozatlan():
    alap = GYOKER / "backend" / "handball" / "vendor" / "three"
    for ut, h in HASH.items():
        assert hashlib.sha256((alap / ut).read_bytes()).hexdigest() == h, ut
    assert "MIT" in (alap / "LICENSE").read_text(encoding="utf-8")
    assert "REVISION = '160'" in (alap / "build" / "three.module.js").read_text(
        encoding="utf-8")


def test_a_motor_kiszolgalja_a_three_js_t(tmp_path, monkeypatch):
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    c = TestClient(create_app())
    alap = GYOKER / "backend" / "handball" / "vendor" / "three"
    for ut in HASH:
        r = c.get(f"/vendor/three@0.160.0/{ut}",
                  headers={"Accept-Encoding": "identity"})
        assert r.status_code == 200, ut
        assert r.headers["content-type"].startswith("text/javascript")
        assert "immutable" in r.headers["cache-control"]
        assert r.content == (alap / ut).read_bytes()
    # Tömörítve is (a nagy fájl a headset Wi-Fi-jén ötödére megy át).
    r = c.get("/vendor/three@0.160.0/build/three.module.js",
              headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200 and r.content == (
        alap / "build" / "three.module.js").read_bytes()
    # Más út nincs (a vendor mappa nem böngészhető).
    for rossz in ("LICENSE", "../../api/app.py", "build/nincs.js",
                  "examples/jsm/controls/OrbitControls.js"):
        assert c.get(f"/vendor/three@0.160.0/{rossz}").status_code == 404, rossz


def test_az_oldal_a_motorbol_tolti_a_three_js_t():
    from handball.pipeline.view3d_html import view3d_html

    oldal = view3d_html(_meccs())
    assert '"three":"/vendor/three@0.160.0/build/three.module.js"' in oldal
    assert '"three/addons/":"/vendor/three@0.160.0/examples/jsm/"' in oldal
    assert "cdn.jsdelivr" not in oldal
    # Az oldal csak ezt a két fájlt kéri.
    assert 'from "three/addons/webxr/VRButton.js"' in oldal
    assert oldal.count('from "three/addons/') == 1


def test_a_csomagolas_viszi_a_three_js_t():
    spec = (GYOKER / "packaging" / "backend.spec").read_text(encoding="utf-8")
    assert '(_three, "handball/vendor/three")' in spec
