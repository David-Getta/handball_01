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


def test_a_varolap_a_mentett_figurakat_kinalja(tmp_path, monkeypatch):
    """A /kovet a legutóbb mentett figurákat linkeli (legfeljebb
    FIGURA_TAR_KOVET, a legújabb elöl): a link a /figura3d-t nyitja az
    utakkal, a passzokkal és a névvel; a sérült fájl kimarad."""
    import os

    from handball.pipeline import play_simulation as ps
    app = _app(tmp_path, monkeypatch)
    c = TestClient(app)
    assert "Mentett figurák" not in c.get("/kovet").text
    regi = c.post("/playbook", json={"name": "Régi <b>", "attackers": [
        [[20, 10], [25, 10]]]}).json()["id"]
    uj = c.post("/playbook", json={"name": "Kereszt", "labda": [0, 1],
                                   "attackers": [[[20, 10], [25, 10]],
                                                 [[24, 4], [26.25, 4]]]}).json()["id"]
    konyvtar = tmp_path / "data" / "playbook"
    os.utime(konyvtar / f"{regi}.json", (1000, 1000))
    os.utime(konyvtar / f"{uj}.json", (2000, 2000))
    (konyvtar / "rossz.json").write_text("{", encoding="utf-8")
    lap = c.get("/kovet").text
    assert "Mentett figurák — járd be bármelyiket" in lap
    assert lap.index("▶ Kereszt") < lap.index("▶ Régi &lt;b&gt;")
    assert ('href="/figura3d?u=20.0,10.0,25.0,10.0;24.0,4.0,26.2,4.0'
            '&amp;l=0,1&amp;cim=Kereszt"') in lap
    assert "2 támadó · passzokkal" in lap and "1 támadó</span>" in lap
    # A link valóban a figurát nyitja.
    r = c.get("/figura3d?u=20.0,10.0,25.0,10.0;24.0,4.0,26.2,4.0&l=0,1&cim=Kereszt")
    assert r.status_code == 200 and '"labda":[0,1]' in r.text
    # Legfeljebb FIGURA_TAR_KOVET (a legújabb marad).
    monkeypatch.setattr(ps, "FIGURA_TAR_KOVET", 1)
    lap = c.get("/kovet").text
    assert "▶ Kereszt" in lap and "Régi" not in lap


def test_a_figura_link_kodja():
    from handball.pipeline.play_simulation import figura_link_kod
    assert figura_link_kod([[(20, 10), (25.04, 10)]]) == "u=20.0,10.0,25.0,10.0"
    assert (figura_link_kod([[(1, 2)], [(3, 4)]], [0, 1], " Kereszt bal ")
            == "u=1.0,2.0;3.0,4.0&l=0,1&cim=Kereszt+bal")
    assert figura_link_kod([[(1, 2)]], [0, 0], "") == "u=1.0,2.0"
    with pytest.raises(ValueError):
        figura_link_kod([[("x", 2)]])


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
                 'for (const k of ["u", "l", "cim", "meccs", "vedo", "vedok", "melyseg", "rendszer"])',
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
    assert ('else if (FIGURA && !v("kamera") && !v("tv") && !v("szem") && v("kovet") !== "1") '
            'nezet("madar");') in view3d_html(m, figura=e)


def test_a_figura_lap():
    """A kiosztható lap: kulcs-pozíciónként egy ábra (a támadók, a fal, a
    kapus, a labda), a futás- és passz-nyilakkal, a lépések leírásával és
    a kiértékeléssel."""
    from handball.pipeline.figura_lap import figura_lap_html

    kp = [[(22, 10), (22, 10), (22, 10)], [(24, 5), (26, 5), (28, 5)],
          [(24, 15), (26, 15), (28, 15)]]
    lap = figura_lap_html(kp, [0, 1, 2], DefenseModel(), nev="Kereszt <b>",
                          vedo_nev="Védelem (6 védő, 6,0 m)")
    assert lap.count("<svg") == 3
    assert "Kereszt &lt;b&gt;" in lap and "<title>Kereszt &lt;b&gt;" in lap
    assert "1. Kezdő → Közép" in lap and "3. Vég" in lap
    assert "2. fut 2,0 m · 3. fut 2,0 m · passz: 1 → 2" in lap
    assert "passz: 2 → 3" in lap and "labda: 3. — befejezés" in lap
    assert "labda 1 → 2 → 3" in lap
    # 3 támadó + 6 védő + kapus kockánként
    assert lap.count('<circle') >= 3 * (3 + 6 + 1)
    # futás-nyíl (kék) és passz-nyíl (sárga) is
    assert "#2f6fb2" in lap and "#c99a06" in lap


def test_a_figura_lap_vegpont(tmp_path, monkeypatch):
    c = TestClient(_app(tmp_path, monkeypatch))
    r = c.get("/figura-lap", params={"u": U, "l": "0,1", "cim": "Kereszt"})
    assert r.status_code == 200 and "<h1>Kereszt</h1>" in r.text
    assert c.get("/figura-lap", params={"u": "1,2,3"}).status_code == 400
    r = c.get("/figura-lap", params={"u": U, "meccs": "fm"})
    assert "Tanult védelem — B" in r.text


def test_a_tervezo_figura_lap_gombja():
    from pathlib import Path

    tervezo = (Path(__file__).resolve().parents[2] / "client" / "lib" / "ui"
               / "designer_screen.dart").read_text(encoding="utf-8")
    assert 'ut: "figura-lap"' in tervezo and '"Figura-lap ↗"' in tervezo
    assert 'Uri.parse("${_api.baseUrl}/$ut")' in tervezo


def test_a_szemevel_nezet_linkrol(tmp_path, monkeypatch):
    """szem=h3: a lap a hazai 3-as szemével nyílik (VR-ben nincs dupla
    katt); a /kovet a csapat linkjén átadja (a rossz alakút nem)."""
    from handball.pipeline.view3d_html import view3d_html

    m, e = setplay_3d_match([[(20, 10), (27, 10)]], DefenseModel())
    oldal = view3d_html(m, figura=e)
    for kell in ("function szemevelIndit(hazai, mez){",
                 'if (/^[hv][0-9]{1,2}$/.test(v("szem"))) szemevelIndit(',
                 'q.set("szem", (kovet.hazai ? "h" : "v") + kovet.mez);',
                 '!v("szem") && v("kovet") !== "1") nezet("madar");'):
        assert kell in oldal, kell
    c = TestClient(_app(tmp_path, monkeypatch))
    fig = "u=20%2C10%3B24%2C5"
    c.put("/matches/figura/shared3d", json={"t": 1, "figura": fig})
    r = c.get("/kovet", params={"nev": "Anna", "szem": "h3"},
              follow_redirects=False)
    assert r.headers["location"] == f"/figura3d?{fig}&kovet=1&nev=Anna&szem=h3"
    r = c.get("/kovet", params={"szem": "x\"><"}, follow_redirects=False)
    assert "szem" not in r.headers["location"]


@pytest.mark.parametrize("rendszer", ["6-0", "5-1", "4-2", "3-2-1", "3-3"])
def test_a_fal_rendszere(rendszer):
    """A fal a rendszere szerint áll: a forma-felismerés (detect_formation)
    ugyanazt a címkét adja; senki sincs a hatoson belül; a kitolt
    vonal előtt az előretoltak is kijjebb kerülnek; kevés védőnél egy
    védő a vonalban marad."""
    from handball.pipeline.tactics import TacticsConfig, detect_formation

    m = DefenseModel(rendszer=rendszer)
    for by in (3.0, 10.0, 17.0):
        pos = m.respond(Ball(x=28.0, y=by, confidence=1.0), goal_x=40.0)
        assert len(pos) == 6
        for x, y in pos:
            kapufa = min(11.5, max(8.5, y))
            assert math.hypot(x - 40.0, y - kapufa) >= 6.0 - 1e-9
        f = Frame(t=0, players=[PlayerPosition(
            track_id=100 + i, team=Team.AWAY, x=x, y=y,
            source=PositionSource.MEASURED, confidence=1.0)
            for i, (x, y) in enumerate(pos)])
        # (középre lőtt labdánál — a sarokba szorult szélső védőt, a
        # 6-0-ban is, a felismerés kapusnak veszi)
        if by == 10.0:
            assert detect_formation(f, Team.AWAY, TacticsConfig()).label == rendszer
    kitolt = DefenseModel(rendszer=rendszer, line_depth_m=9.0).respond(
        Ball(x=28.0, y=10.0, confidence=1.0), goal_x=40.0)
    elol = kitolt[6 - {"6-0": 0, "5-1": 1, "4-2": 2, "3-2-1": 3, "3-3": 3}[rendszer]:]
    assert all(x <= 40.0 - 9.5 - 1.5 + 1e-9 for x, _ in elol)
    ketto = DefenseModel(num_defenders=2, rendszer=rendszer).respond(
        Ball(x=28.0, y=10.0, confidence=1.0), goal_x=40.0)
    assert len(ketto) == 2 and ketto[0][0] > 33.0   # az első a vonalban


def test_a_tanult_fal_rendszere():
    """Az 5-1-ben védő csapatból tanult fal 5-1, a vonal mélysége a hátsó
    sorból (6 m — az előretolt 9,5 m-e nélkül)."""
    frames = []
    for t in range(10):
        players = [PlayerPosition(track_id=i + 1, team=Team.HOME, x=28.0,
                                  y=10.0, source=PositionSource.MEASURED,
                                  confidence=1.0) for i in range(3)]
        players += [PlayerPosition(track_id=100 + i, team=Team.AWAY, x=x, y=y,
                                   source=PositionSource.MEASURED,
                                   confidence=1.0)
                    for i, (x, y) in enumerate([(34, 3), (34, 6.5), (34, 10),
                                                (34, 13.5), (34, 17),
                                                (30.5, 10)])]
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=28.0, y=10.0, confidence=1.0)))
    m = DefenseModel.learn(Match(MatchMeta(match_id="t", home_team="A",
                                           away_team="B", fps=25), frames),
                           Team.AWAY)
    assert (m.rendszer, m.num_defenders) == ("5-1", 6)
    assert abs(m.line_depth_m - 6.0) < 1e-6


def test_a_figura3d_rendszerrel(tmp_path, monkeypatch):
    c = TestClient(_app(tmp_path, monkeypatch))
    r = c.get("/figura3d", params={"u": U, "rendszer": "5-1"})
    assert r.status_code == 200
    assert "Figura vs Védelem (5-1, 6 védő, 6,0 m) — 3D" in r.text
    assert c.get("/figura3d", params={"u": U, "rendszer": "7-0"}).status_code == 400
    r = c.get("/figura-lap", params={"u": U, "rendszer": "3-2-1"})
    assert r.status_code == 200 and "Védelem (3-2-1, 6 védő, 6,0 m)" in r.text


def test_a_rendszerek_a_kliensben_is():
    """A Dart-tükör (analytics/play_simulation.dart defenseSystems) a
    motor VEDEKEZESI_RENDSZEREK-ével azonos."""
    from pathlib import Path

    from handball.pipeline.play_simulation import (ELORETOLT_MIN_ELONY_M,
                                                   VEDEKEZESI_RENDSZEREK)
    dart = (Path(__file__).resolve().parent.parent.parent / "client" / "lib"
            / "analytics" / "play_simulation.dart").read_text(encoding="utf-8")
    for nev, elol in VEDEKEZESI_RENDSZEREK.items():
        sor = (f'  "{nev}": ['
               + ", ".join("[" + ", ".join(str(float(v)) for v in e) + "]"
                           for e in elol) + "],")
        assert sor in dart, sor
    assert f"const double advancedMinLeadM = {ELORETOLT_MIN_ELONY_M};" in dart


def test_a_figura_vedoi_mezszammal():
    """A figura kapusa az 1-es, a védők 2, 3, … — a játékos-kamera és a
    szem=v3 link a védő szemével nyit; a védő feje a labdát nézi."""
    from handball.pipeline.play_simulation import FIGURA_KAPUS_MEZ
    from handball.pipeline.view3d_html import view3d_html

    m, e = setplay_3d_match([[(20, 10), (27, 10)]],
                            DefenseModel(rendszer="5-1"))
    for f in (m.frames[0], m.frames[-1]):
        vedok = sorted((p.jersey_number, p.role == "kapus")
                       for p in f.players if p.team == Team.AWAY)
        assert vedok == [(FIGURA_KAPUS_MEZ, True)] + [
            (n, False) for n in range(2, 8)]
    oldal = view3d_html(m, figura=e)
    assert "const celIrany = (FIGURA && !kovet.hazai && labda.visible)" in oldal


def test_a_vedo_linkje_a_varolaprol(tmp_path, monkeypatch):
    """A vezetett figurára a /kovet?szem=v3 a 3-as védő szemével irányít."""
    app = _app(tmp_path, monkeypatch)
    c = TestClient(app)
    vezeto = c.put("/matches/figura/shared3d",
                   json={"t": 0, "playing": False, "figura": "u=20%2C10%2C27%2C10"})
    assert vezeto.status_code == 200
    r = c.get("/kovet", params={"szem": "v3"}, follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"].endswith("&szem=v3")


def test_a_fal_lepes_tempoja():
    """A 3D figura védője kockánként legfeljebb FIGURA_VEDO_MAX_MPS / fps
    métert lép (a hatos ívére kitolva pár mm-rel többet), a hatoson belülre
    nem vág; a hosszú passz alatt a fal
    lemarad a modell-helyétől, a végére (az állóképben) beáll."""
    from handball.pipeline.play_simulation import FIGURA_VEDO_MAX_MPS

    kp = [[(22, 3), (22, 3)], [(24, 17), (24, 17)]]
    modell = DefenseModel(rendszer="5-1")
    m, _ = setplay_3d_match(kp, modell, ball=[0, 1])
    lepes_max = FIGURA_VEDO_MAX_MPS / m.meta.fps
    lemaradt = False
    for a, b in zip(m.frames, m.frames[1:]):
        va = {p.track_id: p for p in a.players if p.team == Team.AWAY}
        for p in b.players:
            if p.team != Team.AWAY or p.role == "kapus":
                continue
            # (a hatos íve mentén a kitolás a lépést pár mm-rel megnövelheti)
            assert math.hypot(p.x - va[p.track_id].x,
                              p.y - va[p.track_id].y) <= lepes_max * 1.02
            kapufa = min(11.5, max(8.5, p.y))
            assert math.hypot(p.x - 40.0, p.y - kapufa) >= 6.0 - 1e-9
        cel = modell.respond(b.ball, goal_x=40.0)
        vedok = sorted((p.track_id, p.x, p.y) for p in b.players
                       if p.team == Team.AWAY and p.role != "kapus")
        if any(math.hypot(x - cx, y - cy) > 1.0
               for (_, x, y), (cx, cy) in zip(vedok, cel)):
            lemaradt = True
    assert lemaradt
    utolso = sorted((p.track_id, p.x, p.y) for p in m.frames[-1].players
                    if p.team == Team.AWAY and p.role != "kapus")
    for (_, x, y), (cx, cy) in zip(utolso, modell.respond(
            m.frames[-1].ball, goal_x=40.0)):
        assert math.isclose(x, cx, abs_tol=1e-6) and math.isclose(y, cy, abs_tol=1e-6)


def test_a_figurafuzet():
    """A figurafüzet: tartalomjegyzék, figuránként egy oldal (a figura-lap
    tartalma, a választott fallal); a hibás figura kimarad, jelezve."""
    from handball.pipeline.figura_lap import figura_fuzet_html, figura_lap_html

    fal = DefenseModel(rendszer="5-1")
    vn = "Védelem (5-1, 6 védő, 6,0 m)"
    fuzet = figura_fuzet_html(
        [{"name": "Kereszt", "labda": [0, 1],
          "attackers": [[[20, 10], [27, 10]], [[24, 4], [26, 4]]]},
         {"name": "Rossz", "attackers": [["x", 1]]},
         {"name": "Beúszás <b>", "attackers": [[[22, 3], [30, 5]]]}],
        fal, vedo_nev=vn)
    assert fuzet.count('<section class="figura">') == 2
    assert "<li>Kereszt</li><li>Beúszás &lt;b&gt;</li>" in fuzet
    assert "Kimaradt (hibás figura): Rossz" in fuzet
    assert f"2 figura · {vn}" in fuzet
    assert ".figura{break-before:page" in fuzet
    egy = figura_lap_html([[(20, 10), (27, 10)], [(24, 4), (26, 4)]], [0, 1],
                          fal, nev="Kereszt", vedo_nev=vn)
    assert egy[egy.index("<h1>"):egy.index('<div class="jel">')] in fuzet
    ures = figura_fuzet_html([], fal, vedo_nev=vn)
    assert "Még nincs mentett figura" in ures and "<section" not in ures


def test_a_figurafuzet_vegpont(tmp_path, monkeypatch):
    """GET /figura-fuzet: alapból mind (név szerint), `ids`-szel a kért
    sorrendben; a fal a /figura-lap paramétereivel."""
    c = TestClient(_app(tmp_path, monkeypatch))
    assert "Még nincs mentett figura" in c.get("/figura-fuzet").text
    a = c.post("/playbook", json={"name": "Zóna", "attackers": [
        [[20, 10], [25, 10]]]}).json()["id"]
    b = c.post("/playbook", json={"name": "Alfa", "attackers": [
        [[22, 3], [30, 5]]]}).json()["id"]
    lap = c.get("/figura-fuzet").text
    assert lap.index("<li>Alfa</li>") < lap.index("<li>Zóna</li>")
    lap = c.get("/figura-fuzet", params={"ids": f"{a},nincs,{b}",
                                         "rendszer": "3-2-1"}).text
    assert lap.index("<li>Zóna</li>") < lap.index("<li>Alfa</li>")
    assert "2 figura · Védelem (3-2-1, 6 védő, 6,0 m)" in lap
    assert c.get("/figura-fuzet", params={"rendszer": "9-9"}).status_code == 400
    r = c.get("/figura-fuzet", params={"meccs": "fm", "vedo": "away"})
    assert r.status_code == 200 and "Tanult védelem — B" in r.text


def test_a_kesz_fal_a_vegen_beall():
    """Széles keresztpassz a végén (3-2-1, a csúcs 14 m-t lép): az állókép
    addig nyúlik, amíg a fal be nem áll — az utolsó kocka a modell-hely."""
    modell = DefenseModel(rendszer="3-2-1")
    m, _ = setplay_3d_match([[(22, 1), (22, 1)], [(24, 19), (24, 19)]],
                            modell, ball=[0, 1])
    utolso = sorted((p.track_id, p.x, p.y) for p in m.frames[-1].players
                    if p.team == Team.AWAY and p.role != "kapus")
    for (_, x, y), (cx, cy) in zip(utolso, modell.respond(
            m.frames[-1].ball, goal_x=40.0)):
        assert math.isclose(x, cx, abs_tol=1e-6) and math.isclose(y, cy, abs_tol=1e-6)
    # minden kockán kapus, és a mezszámok megvannak
    assert all(sum(1 for p in f.players if p.role == "kapus") == 1
               for f in m.frames)


def test_a_figura_lap_a_3d_falat_rajzolja():
    """A figura-lap fala a 3D kockájából jön (a késő fal is), a védők a
    mezszámukkal (a szem=v… linkekhez)."""
    from handball.pipeline.figura_lap import figura_lap_html

    lap = figura_lap_html([[(22, 1), (22, 1)], [(24, 19), (24, 19)]], [0, 1],
                          DefenseModel(rendszer="5-1"), nev="Kereszt",
                          vedo_nev="V")
    assert lap.count("<svg") == 2
    for mez in range(1, 8):
        assert f">{mez}</text>" in lap


def test_a_mentett_figura_nan_nelkul(tmp_path, monkeypatch):
    """A NaN / végtelen koordináta mentése 400; a link-kód a nem véges
    pontot kihagyja, a határokon belül marad."""
    from handball.pipeline.play_simulation import (FIGURA_3D_MAX_JATEKOS,
                                                   FIGURA_3D_MAX_PONT,
                                                   figura_link_kod)
    c = TestClient(_app(tmp_path, monkeypatch))
    for rossz in ("NaN", "Infinity"):
        r = c.post("/playbook", content=(
            '{"name": "x", "attackers": [[[20, 10], [%s, 10]]]}' % rossz),
            headers={"content-type": "application/json"})
        assert r.status_code == 400
    assert figura_link_kod([[(1, 2), (float("nan"), 3)]]) == "u=1.0,2.0"
    sok = [[(i, 1)] * 20 for i in range(12)]
    u = figura_link_kod(sok).split("=", 1)[1]
    assert len(u.split(";")) == FIGURA_3D_MAX_JATEKOS
    assert all(len(r.split(",")) == 2 * FIGURA_3D_MAX_PONT for r in u.split(";"))
    with pytest.raises(ValueError):
        figura_link_kod([[(float("inf"), 1)]])


def test_a_figura_videoja(tmp_path):
    """A figura felülnézeti videója: olvasható MP4 (a 3D hosszával, 24
    kocka/mp), a támadók kékek, a fal piros; az ékezet a feliratból le."""
    import cv2
    import numpy as np

    from handball.pipeline.figura_video import (FIGURA_VIDEO_FPS,
                                                ascii_felirat, figura_video)
    m, _ = setplay_3d_match([[(22, 10), (27, 10)], [(24, 4), (26, 4)]],
                            DefenseModel())
    ut = figura_video([[(22, 10), (27, 10)], [(24, 4), (26, 4)]], [0, 1],
                      DefenseModel(), nev="Kereszt", vedo_nev="V",
                      cel=tmp_path / "f.mp4")
    c = cv2.VideoCapture(str(ut))
    n = int(c.get(cv2.CAP_PROP_FRAME_COUNT))
    hossz = (len(m.frames) - 1) / m.meta.fps
    assert abs(n - (hossz * FIGURA_VIDEO_FPS + 1)) <= 2
    assert int(c.get(3)) % 2 == 0 and int(c.get(4)) % 2 == 0
    ok, kep = c.read()
    assert ok
    kek = np.sum((kep[:, :, 0] > 150) & (kep[:, :, 2] < 100))
    piros = np.sum((kep[:, :, 2] > 150) & (kep[:, :, 0] < 100))
    assert kek > 200 and piros > 500
    assert ascii_felirat("Védő — ő, ű →") == "Vedo - o, u ->"
    with pytest.raises(ValueError):
        figura_video([], [], DefenseModel(), nev="x", vedo_nev="V",
                     cel=tmp_path / "g.mp4")
    # A magyarázós videó kulcs-pozíciónként FIGURA_VIDEO_LEPES_S-ig áll.
    from handball.pipeline.figura_video import FIGURA_VIDEO_LEPES_S
    ut2 = figura_video([[(22, 10), (27, 10)], [(24, 4), (26, 4)]], [0, 1],
                       DefenseModel(), nev="Kereszt", vedo_nev="V",
                       cel=tmp_path / "l.mp4", lepes=True)
    n2 = int(cv2.VideoCapture(str(ut2)).get(cv2.CAP_PROP_FRAME_COUNT))
    allj = int(round(FIGURA_VIDEO_LEPES_S * FIGURA_VIDEO_FPS))
    assert abs(n2 - (n + 2 * allj)) <= 2   # két kulcs-pozíció


def test_a_figura_video_vegpont(tmp_path, monkeypatch):
    """GET /figura-video: MP4 letöltésre (ékezetes fájlnévvel); a hibás
    figura 400; a várólap a mentett figura videóját is linkeli; a
    klub-hálózatról is elérhető."""
    app = _app(tmp_path, monkeypatch)
    c = TestClient(app)
    r = c.get("/figura-video", params={"u": U, "cim": "Beúszás",
                                       "rendszer": "5-1"})
    assert r.status_code == 200 and r.headers["content-type"] == "video/mp4"
    assert "filename*=UTF-8''Be%C3%BAsz%C3%A1s.mp4" in r.headers["content-disposition"]
    assert len(r.content) > 1000
    assert c.get("/figura-video", params={"u": "1,2,3"}).status_code == 400
    c.post("/playbook", json={"name": "Kereszt", "attackers": [
        [[20, 10], [25, 10]]]})
    assert ('href="/figura-video?u=20.0,10.0,25.0,10.0&amp;cim=Kereszt">⬇ videó'
            in c.get("/kovet").text)
    from handball.pipeline.view3d_html import view3d_html
    m, e = setplay_3d_match([[(20, 10), (27, 10)]], DefenseModel())
    assert '+ (lepesMod ? "&lepes=1" : ""), "_blank");' in view3d_html(m, figura=e)
    r = c.get("/figura-video", params={"u": U, "lepes": 1})
    assert r.status_code == 200 and r.headers["content-type"] == "video/mp4"


def test_a_kulcs_poziciok_ideje():
    """A kulcs-pozíciók ideje (kulcs_t): az állókép után, a szakaszok
    végén — azon a kockán a támadó pontosan a kulcs-pozíción áll."""
    m, e = setplay_3d_match([[(20, 10), (27, 10), (34, 10)], [(24, 4)]],
                            DefenseModel())
    assert e["kulcs_t"] == [1.5, 3.5, 5.5]
    for t, (x, y) in zip(e["kulcs_t"], [(20, 10), (27, 10), (34, 10)]):
        f = m.frames[int(round(t * m.meta.fps))]
        p = next(p for p in f.players
                 if p.team == Team.HOME and p.jersey_number == 1)
        assert math.isclose(p.x, x) and math.isclose(p.y, y)
    # Egyetlen pont: egy kulcs-pozíció (az állókép végén).
    _, e = setplay_3d_match([[(20, 10)]], DefenseModel())
    assert e["kulcs_t"] == [FIGURA_3D_ALLAS_S]


def test_a_figura_lepesenkent():
    """A "⏯ Lépésenként" gomb: a lejátszás a kulcs-pozíciókon megáll, az
    N / P (VR: A / B) a kulcs-pozíciók közt lép, a link viszi (lepes=1),
    a jelző a VR-táblán is látszik."""
    from handball.pipeline.view3d_html import view3d_html

    m, e = setplay_3d_match([[(20, 10), (27, 10), (34, 10)]], DefenseModel())
    oldal = view3d_html(m, figura=e)
    assert '"kulcs_t":[1.5,3.5,5.5]' in oldal
    assert 'lepesGomb.id = "lepesGomb";' in oldal
    assert '<div id="lepesJelzo"></div>' in oldal
    assert '"hetesFelirat", "emberJelzo", "lepesJelzo"];' in oldal
    assert "vetitesFrissit(t0, ido); lepesFrissit(t0, ido);" in oldal
    assert "if (FIGURA) return kulcsLep(irany);" in oldal
    assert 'if (FIGURA && lepesMod) q.set("lepes", "1");' in oldal
    assert 'if (FIGURA && v("lepes") === "1") lepesAllit(true);' in oldal
    # A követő nem áll meg magától (a vezető megállása jön át).
    assert 'if (!lepesMod || kozosMod === "kovet") return;' in oldal


def test_a_figura_oldal_figura_lap_gombja():
    from handball.pipeline.view3d_html import view3d_html

    m, e = setplay_3d_match([[(20, 10), (27, 10)]], DefenseModel())
    oldal = view3d_html(m, figura=e)
    assert 'window.open("/figura-lap?" + FIGURA_KOD, "_blank");' in oldal
    assert 'lapGomb.id = "figuraLapGomb";' in oldal
