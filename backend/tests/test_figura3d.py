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
                 'for (const k of ["u", "l", "cim", "meccs", "vedo", "vedok", "melyseg"])',
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
    assert "rajzok.push([a[0], a[1], b[0], b[1], 1]);" in oldal
    assert "rajzok.push([p[0], p[1], p[2], p[3], 0]);" in oldal


def test_passz_a_figuraban():
    """A labdás kulcs-pozíciónként: ahol változik, ott passz — a labda a
    kulcs-pozícióra érkezik az átvevőhöz, előtte a passzolónál; a védelem
    a labdára reagál. A hibás / pályán kívüli sorszám az előzőé."""
    kp = [[(22, 10), (22, 10), (22, 10)], [(24, 5), (26, 5), (28, 5)],
          [(24, 15), (26, 15), (28, 15)]]
    m, e = setplay_3d_match(kp, DefenseModel(), ball=[0, 1, 2])
    assert e["labda"] == [0, 1, 2]
    # (a nyíl a két játékos helye az érkezés kulcs-pozícióján)
    assert e["passzok"] == [[22.0, 10.0, 26.0, 5.0], [28.0, 5.0, 28.0, 15.0]]
    allas = int(round(FIGURA_3D_ALLAS_S * FIGURA_3D_FPS))
    lep = int(round(e["hossz_s"] * FIGURA_3D_FPS)) + 1
    kozep = allas + (lep - 1) // 2
    # az elején a passzolónál, a Közép ponton az átvevőnél, a végén a 3.-nál
    assert (m.frames[0].ball.x, m.frames[0].ball.y) == (22, 10)
    assert math.isclose(m.frames[kozep].ball.x, 26.0)
    assert math.isclose(m.frames[kozep].ball.y, 5.0)
    assert (m.frames[-1].ball.x, m.frames[-1].ball.y) == (28, 15)
    # repülés közben se nem a passzolónál, se nem az átvevőnél
    reptiben = m.frames[kozep - 1].ball
    assert (reptiben.x, reptiben.y) not in ((22, 10), (26, 5))
    # a fal a labda felé tolódik: a 3. támadónál (y=15) lejjebb áll
    def fal_y(f):
        return sum(p.y for p in f.players
                   if p.team == Team.AWAY and p.role != "kapus")
    assert fal_y(m.frames[-1]) > fal_y(m.frames[0])
    # hibás és pályán kívüli sorszám → az előzőé; alapból végig az 1.
    _, e2 = setplay_3d_match(kp, DefenseModel(), ball=[0, "x", 9])
    assert e2["labda"] == [0, 0, 0] and e2["passzok"] == []
    _, e3 = setplay_3d_match(kp, DefenseModel())
    assert e3["labda"] == [0, 0, 0]


def test_a_figura3d_vegpont_passzal(tmp_path, monkeypatch):
    c = TestClient(_app(tmp_path, monkeypatch))
    r = c.get("/figura3d", params={"u": U, "l": "0,1"})
    assert r.status_code == 200 and '"labda":[0,1,1]' in r.text
    assert c.get("/figura3d", params={"u": U, "l": "a,b"}).status_code == 400


def test_a_figura_mentese_a_passzokkal(tmp_path, monkeypatch):
    """A figura-könyvtár a labdás-sort is menti (a tervező visszatölti);
    a nem létező játékos 400."""
    c = TestClient(_app(tmp_path, monkeypatch))
    ut = [[[22, 10], [22, 10], [22, 10]], [[24, 5], [26, 5], [28, 5]]]
    r = c.post("/playbook", json={"name": "Kereszt", "attackers": ut,
                                  "labda": [0, 1, 1]})
    assert r.status_code == 200
    assert c.get(f"/playbook/{r.json()['id']}").json()["labda"] == [0, 1, 1]
    r = c.post("/playbook", json={"name": "Régi", "attackers": ut})
    assert "labda" not in c.get(f"/playbook/{r.json()['id']}").json()
    for rossz in ([0, 2], [0, "x"], [0, 0, 0, 0]):
        assert c.post("/playbook", json={"name": "R", "attackers": ut,
                                         "labda": rossz}).status_code == 400


def test_a_figura_kozos_nezese(tmp_path, monkeypatch):
    """A figurát is lehet vezetni: a vezető a /matches/figura/shared3d-re
    a figura paramétereit is küldi, a /kovet a csapatot ugyanarra a
    figurára irányítja (a nevükkel); paraméter nélkül / rossz alakkal 400.
    Az oldal figura-módban a közös nézést megtartja, a felvételt nem."""
    from handball.pipeline.view3d_html import view3d_html

    c = TestClient(_app(tmp_path, monkeypatch))
    url = "/matches/figura/shared3d"
    assert c.put(url, json={"t": 1}).status_code == 400
    assert c.put(url, json={"t": 1, "figura": "u=1\"><b>"}).status_code == 400
    fig = "u=20%2C10%3B24%2C5&l=0%2C1&cim=Kereszt"
    assert c.put(url, json={"t": 1, "playing": True,
                            "figura": fig}).status_code == 200
    r = c.get("/kovet", params={"nev": "Anna"}, follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == f"/figura3d?{fig}&kovet=1&nev=Anna"
    assert c.get(url).json()["t"] == 1
    # a meccs közös nézése a régi úton marad
    assert c.put("/matches/nincs/shared3d", json={"t": 1}).status_code == 404
    m, e = setplay_3d_match([[(20, 10), (27, 10)]], DefenseModel())
    oldal = view3d_html(m, figura=e)
    assert 'const KZ_ID = FIGURA ? "figura" : ADAT.match_id;' in oldal
    assert "...(FIGURA ? {figura: FIGURA_KOD} : {})" in oldal
    assert 'for (const id of ["felvetelGomb", "felvetelValaszto", "fejezetValaszto"])' in oldal


def test_a_figura_neve_nem_csonkul(tmp_path, monkeypatch):
    """A figura neve 60 jelig megmarad (a követő-név tisztítója 16-ra
    vágta); a vezérlőjel kimarad."""
    app = _app(tmp_path, monkeypatch)
    helyi = TestClient(app, client=("127.0.0.1", 1))
    nev = "Beúszós kereszt visszaadással"
    r = helyi.get("/figura3d", params={"u": U, "cim": nev + "\x07"})
    assert f"<title>{nev} vs " in r.text
    assert f"▶ Figura: {nev}<" in helyi.get("/kovet").text
    r = helyi.get("/figura3d", params={"u": U, "cim": "x" * 100})
    assert "<title>" + "x" * 60 + " vs " in r.text


def _tamado_meccs(irany=1):
    """Egy 4 mp-es hazai támadás: 3 mezőnyjátékos + kapus, a labda a 2.-tól
    a 3.-hoz kerül; `irany` -1: a -x kapura támadnak (forgatandó)."""
    fps = 10.0
    frames = []
    for i in range(41):
        f = i / 40.0
        def x(v):
            return v if irany == 1 else 40.0 - v
        def y(v):
            return v if irany == 1 else 20.0 - v
        pl = [PlayerPosition(track_id=1, team=Team.HOME, x=x(28.0), y=y(4.0 + 2 * f),
                             jersey_number=5),
              PlayerPosition(track_id=2, team=Team.HOME, x=x(27.0 + 3 * f), y=y(10.0),
                             jersey_number=7),
              PlayerPosition(track_id=3, team=Team.HOME, x=x(29.0), y=y(16.0 - 2 * f)),
              PlayerPosition(track_id=9, team=Team.HOME, x=x(1.0), y=y(10.0)),
              PlayerPosition(track_id=20, team=Team.AWAY, x=x(34.0), y=y(10.0))]
        bx, by = (27.0 + 3 * f, 10.0) if f < 0.5 else (29.0, 16.0 - 2 * f)
        frames.append(Frame(t=i, players=pl, ball=Ball(x=x(bx), y=y(by), confidence=1.0)))
    return Match(MatchMeta(match_id="tf", home_team="Kiel", away_team="Berlin",
                           fps=fps), frames)


@pytest.mark.parametrize("irany", [1, -1])
def test_tamadasbol_figura(irany):
    """A valódi támadás figuraként: a mezőnyjátékosok kulcs-pozíciói (a
    kapus nélkül), a labdás, és a -x felé támadás a +x kapura forgatva."""
    from handball.pipeline.play_simulation import attack_figure
    from handball.pipeline.primitive_cache import primitive_cache
    from handball.pipeline.tactics import TacticsConfig

    m = _tamado_meccs(irany)
    cfg = TacticsConfig(home_attacks_positive=(irany == 1))
    with primitive_cache(m):
        f = attack_figure(m, 20, config=cfg)
    assert f is not None and f["csapat"] == "Kiel" and f["csapat_oldal"] == "home"
    assert len(f["attackers"]) == 3          # a kapus (x=1 / 39) nem
    # balról jobbra: y=4 (5-ös), y=10 (7-es), y=16 (mez nélkül)
    assert f["mez"] == [5, 7, None]
    assert f["attackers"][0] == [[28.0, 4.0], [28.0, 5.0], [28.0, 6.0]]
    assert f["attackers"][1][2] == [30.0, 10.0]
    # a labda: a 7-esnél, majd a 3.-nál
    assert f["labda"] == [1, 2, 2]
    assert f["t0_s"] == 0.0 and f["t1_s"] == 4.0


def test_tamadasbol_figura_vegpont(tmp_path, monkeypatch):
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    app = create_app()
    app.state.put_match(_tamado_meccs())
    c = TestClient(app)
    r = c.get("/matches/tf/attack-figure", params={"t": 2.0})
    assert r.status_code == 200
    d = r.json()
    assert d["match_id"] == "tf" and len(d["attackers"][0]) == 3
    assert len(c.get("/matches/tf/attack-figure",
                     params={"t": 2.0, "pontok": 5}).json()["attackers"][0]) == 5
    assert c.get("/matches/nincs/attack-figure", params={"t": 1}).status_code == 404


def test_a_3d_figurava_gombja():
    """Az app 3D fülén a "✎ Figurává" a mostani pillanat támadását kéri
    le, és a Figura-tervezőt ezzel a kezdő figurával nyitja."""
    from pathlib import Path

    ui = Path(__file__).resolve().parents[2] / "client" / "lib" / "ui"
    palya = (ui / "court3d_screen.dart").read_text(encoding="utf-8")
    assert '"✎ Figurává"' in palya
    assert "_api.fetchAttackFigure(id, _mostT(m) / fps)" in palya
    assert "DesignerScreen(match: m, initial: f)" in palya
    tervezo = (ui / "designer_screen.dart").read_text(encoding="utf-8")
    assert '_tanultOldal = f["csapat_oldal"] == "home" ? "away" : "home";' in tervezo


def test_a_bongeszos_3d_figurava_gombja():
    """A böngészős 3D-ben is "✎ Figurává ↗": a támadást a figura-oldalon
    nyitja, a meccs másik csapatának fala ellen; motor nélkül rejtve."""
    from handball.pipeline.view3d_html import view3d_html

    oldal = view3d_html(_tamado_meccs())
    for kell in ('<button id="figuravaGomb"',
                 'if (!ADAT.match_id) figuravaGomb.style.display = "none";',
                 '"/attack-figure?t=" + ido.toFixed(2)',
                 'q.set("vedo", f.csapat_oldal === "home" ? "away" : "home");',
                 'location.href = "/figura3d?" + q.toString();'):
        assert kell in oldal, kell


def test_a_figura_madartavlatbol_indul():
    from handball.pipeline.view3d_html import view3d_html

    m, e = setplay_3d_match([[(20, 10), (27, 10)]], DefenseModel())
    assert ('else if (FIGURA && !v("kamera") && !v("tv") && v("kovet") !== "1") '
            'nezet("madar");') in view3d_html(m, figura=e)
