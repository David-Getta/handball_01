"""A figura-tervező figurája 3D-ben (böngésző / VR): valós tempó,
állókép, kapus (play_simulation.setplay_3d_match), a /figura3d végpont,
a csapat várólapjának (/kovet) linkje és az oldal figura-módja."""
import math

import pytest
from fastapi.testclient import TestClient

from handball.api.app import create_app
from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                      PlayerPosition, PositionSource, Team)
from handball.pipeline.play_simulation import (
    FIGURA_3D_ALLAS_S, FIGURA_3D_FPS, FIGURA_3D_MAX_S, FIGURA_3D_MIN_S,
    DefenseModel, setplay_3d_match)

U = "20,10,27,10,34,10;24,4,24,4,24,4"


def test_a_figura_valos_tempoban_kapussal_es_alloképpel():
    """A 7 m-es szakaszok 3,5 m/s-mal: 2 × 2 mp mozgás; előtte és utána
    állókép; a kaput kapus védi; a védők a modell szerint."""
    m, e = setplay_3d_match([[(20, 10), (27, 10), (34, 10)], [(24, 4)]],
                            DefenseModel(), name="Kereszt",
                            defense_name="Tanult védelem — B")
    assert e["hossz_s"] == 4.0
    allas = int(round(FIGURA_3D_ALLAS_S * FIGURA_3D_FPS))
    lepes = int(round(4.0 * FIGURA_3D_FPS)) + 1
    assert len(m.frames) == 2 * allas + lepes
    assert m.meta.fps == FIGURA_3D_FPS
    assert (m.meta.home_team, m.meta.away_team) == ("Kereszt",
                                                    "Tanult védelem — B")

    def tamado(f, mez):
        return next(p for p in f.players
                    if p.team == Team.HOME and p.jersey_number == mez)

    # Állókép az elején, a "Közép" pont a mozgás felénél, a vég a végén.
    assert all((tamado(f, 1).x, tamado(f, 1).y) == (20, 10)
               for f in m.frames[:allas + 1])
    kozep = tamado(m.frames[allas + (lepes - 1) // 2], 1)
    assert math.isclose(kozep.x, 27.0) and math.isclose(kozep.y, 10.0)
    assert (tamado(m.frames[-1], 1).x, tamado(m.frames[-1], 1).y) == (34, 10)
    # A labda az 1. támadónál; minden kockán kapus (a vendég kapujában).
    assert (m.frames[-1].ball.x, m.frames[-1].ball.y) == (34, 10)
    for f in m.frames:
        kapus = [p for p in f.players if p.role == "kapus"]
        assert len(kapus) == 1 and kapus[0].team == Team.AWAY
        assert kapus[0].x > 38.5 and 8.5 <= kapus[0].y <= 11.5
        assert sum(1 for p in f.players if p.team == Team.AWAY) == 7
    # A kiértékelés a kapus nélkül (mint a tervezőben).
    assert e["attacker_id"] in (1, 2) and 0 < e["best_shot_value"] <= 1


def test_a_mozgas_hossza_a_savban_marad():
    """Az apró mozgás sem villanás (FIGURA_3D_MIN_S), a hosszú sem
    vánszorog (FIGURA_3D_MAX_S); a pályán kívüli pont a pályára szorul."""
    _, e = setplay_3d_match([[(20, 10), (20.5, 10)]], DefenseModel())
    assert e["hossz_s"] == FIGURA_3D_MIN_S
    m, e = setplay_3d_match([[(0, 0), (40, 20), (0, 0), (40, 20)]],
                            DefenseModel())
    assert e["hossz_s"] == FIGURA_3D_MAX_S
    m, _ = setplay_3d_match([[(-5, 30)]], DefenseModel())
    p = next(p for p in m.frames[0].players if p.team == Team.HOME)
    assert (p.x, p.y) == (0.0, 20.0)


def test_ures_figura_hibat_ad():
    for rossz in ([], [[]], [[(float("nan"), 1.0)]]):
        with pytest.raises(ValueError):
            setplay_3d_match(rossz, DefenseModel())


def _app(tmp_path, monkeypatch):
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    app = create_app()
    frames = [Frame(t=t, players=[PlayerPosition(
        track_id=1, team=Team.HOME, x=20.0, y=10.0,
        source=PositionSource.MEASURED, confidence=1.0)],
        ball=Ball(x=20.0, y=10.0, confidence=1.0)) for t in range(10)]
    app.state.put_match(Match(MatchMeta(match_id="fm", home_team="A",
                                        away_team="B", fps=25.0), frames))
    return app


def test_a_figura3d_vegpont(tmp_path, monkeypatch):
    """GET /figura3d: a figura 3D-oldala figura-módban (a kiértékeléssel);
    a védelem kézi (vedok, melyseg) vagy egy meccsből tanult."""
    c = TestClient(_app(tmp_path, monkeypatch))
    r = c.get("/figura3d", params={"u": U, "cim": "Kereszt", "vedok": 5,
                                   "melyseg": 7.5})
    assert r.status_code == 200
    assert '"figura":{"best_shot_value":' in r.text
    assert "Kereszt vs Védelem (5 védő, 7,5 m) — 3D" in r.text
    r = c.get("/figura3d", params={"u": U, "meccs": "fm", "vedo": "away"})
    assert r.status_code == 200 and "Figura vs Tanult védelem — B" in r.text
    assert c.get("/figura3d", params={"u": "1,2,3"}).status_code == 400
    assert c.get("/figura3d", params={"u": "x,y"}).status_code == 400
    assert c.get("/figura3d").status_code == 400
    assert c.get("/figura3d", params={"u": U, "meccs": "nincs"}).status_code == 404
    assert c.get("/figura3d", params={"u": U, "meccs": "fm",
                                      "vedo": "x"}).status_code == 400


def test_a_varolap_az_edzo_figurajat_linkeli(tmp_path, monkeypatch):
    """A saját gépről (az edző) nyitott figura a csapat várólapján: "▶
    Figura: …" — más gépről nyitva nem kerül oda."""
    app = _app(tmp_path, monkeypatch)
    tavoli = TestClient(app, client=("192.168.1.9", 1))
    helyi = TestClient(app, client=("127.0.0.1", 1))
    assert "▶ Figura" not in helyi.get("/kovet").text
    tavoli.get("/figura3d", params={"u": U, "cim": "Távoli"})
    assert "▶ Figura" not in helyi.get("/kovet").text
    helyi.get("/figura3d", params={"u": U, "cim": "Kereszt <b>"})
    lap = tavoli.get("/kovet").text
    assert "▶ Figura: Kereszt &lt;b&gt;" in lap
    assert 'href="/figura3d?u=' in lap
    # A régi figura (FIGURA_3D_KOVET_S után) már nem "a mostani".
    from handball.pipeline import court3d as c3
    from handball.pipeline.play_simulation import FIGURA_3D_KOVET_S
    most = c3.shared3d_ora()
    monkeypatch.setattr(c3, "shared3d_ora",
                        lambda: most + FIGURA_3D_KOVET_S + 1)
    assert "▶ Figura" not in tavoli.get("/kovet").text


def test_az_oldal_figura_modja():
    """Figura-módban a meccshez kötött funkciók ki (match_id üres), a
    meccs-sorok rejtve, a lejátszás magától indul és ismétel; a
    játékos-kamera álló játékosnál is irányt kap."""
    from handball.pipeline.view3d_html import view3d_html

    m, e = setplay_3d_match([[(20, 10), (27, 10)]], DefenseModel())
    oldal = view3d_html(m, figura=e)
    for kell in ("const FIGURA = ADAT.figura || null;",
                 'if (FIGURA) ADAT.match_id = "";',
                 "if (FIGURA && veg > 0) ido = 0;",
                 'document.getElementById("eszkoz").prepend(fs);',
                 'for (const k of ["u", "cim", "meccs", "vedo", "vedok", "melyseg"])',
                 "if (k.ix === 0 && k.iy === 0){"):
        assert kell in oldal, kell
    assert '"figura":{' in oldal
    assert '"figura":{' not in view3d_html(m)


def test_a_figura_utjai_a_padlon():
    """A kiértékelés a pályára szorított kulcs-pozíciókat is viszi; az
    oldal ezekből a padlóra nyilat rajzol (ha a link nem hoz rajzot)."""
    from handball.pipeline.view3d_html import view3d_html

    m, e = setplay_3d_match([[(20, 10), (27, 10), (34, 10)], [(-3, 4)]],
                            DefenseModel())
    assert e["utak"] == [[[20, 10], [27, 10], [34, 10]], [[0.0, 4]]]
    oldal = view3d_html(m, figura=e)
    assert 'if (FIGURA && Array.isArray(FIGURA.utak) && !URL_PARAM.get("rajz")){' in oldal
    assert "rajzok.push([a[0], a[1], b[0], b[1], i === 0 ? 0 : 1]);" in oldal
