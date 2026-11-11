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
    assert 'const KZ_ID = FIGURA && !FV_CSOMAG ? "figura" : ADAT.match_id;' in oldal
    assert "...(FIGURA ? {figura: FIGURA_KOD} : {})" in oldal
    # (a felvétel a figurában is megy — a gombjai nincsenek elrejtve)
    assert 'for (const id of ["felvetelGomb", "felvetelValaszto", "fejezetValaszto"])' not in oldal


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


def test_a_kieso_tamado_utan_a_labdas_sor_atszamozva():
    """A pont nélküli támadó kiesik: a labdás-sor a megmaradókhoz igazodik
    (a 3D-ben és a link-kódban is) — a passz a jó támadóhoz megy."""
    from handball.pipeline.play_simulation import figura_link_kod
    nan = float("nan")
    _, e = setplay_3d_match([[(nan, 1)], [(20, 10), (25, 10)],
                             [(24, 4), (26, 4)]], DefenseModel(), ball=[1, 2])
    assert e["labda"] == [0, 1]
    assert (figura_link_kod([[(nan, 1)], [(1, 2)], [(3, 4)]], [1, 2])
            == "u=1.0,2.0;3.0,4.0&l=0,1")
    assert figura_link_kod([[(1, 2)], [(nan, 1)], [(3, 4)]], [0, 1, 2]) == (
        "u=1.0,2.0;3.0,4.0&l=0,0,1")


def test_a_figura_video_gyorsitotar(tmp_path, monkeypatch):
    """Ugyanaz a videó másodszor a gyorsítótárból (a rajzoló egyszer fut);
    más figura újra rajzol; a hibás figura 400; a füzet a nem-objektum
    JSON-t kihagyja."""
    from handball.pipeline import figura_video as fv
    hivas = []
    eredeti = fv.figura_video

    def szamlalo(*a, **k):
        hivas.append(1)
        return eredeti(*a, **k)
    monkeypatch.setattr(fv, "figura_video", szamlalo)
    c = TestClient(_app(tmp_path, monkeypatch))
    r1 = c.get("/figura-video", params={"u": U})
    r2 = c.get("/figura-video", params={"u": U})
    assert r1.status_code == r2.status_code == 200 and r1.content == r2.content
    assert len(hivas) == 1
    assert c.get("/figura-video", params={"u": U, "lepes": 1}).status_code == 200
    assert len(hivas) == 2
    konyvtar = tmp_path / "data" / "playbook"
    konyvtar.mkdir(parents=True, exist_ok=True)
    (konyvtar / "lista.json").write_text("[1, 2]", encoding="utf-8")
    assert c.get("/figura-fuzet").status_code == 200


def test_felvetel_a_figuraban(tmp_path, monkeypatch):
    """A figura-oldal felvétele a "figura" azonosító alá mentődik a figura
    paramétereivel (nélkülük / rossz alakkal 400); a lista, a lekérés, a
    megnézés és a törlés megy; a várólap és a kezdőlap listája a
    figura-oldalt nyitja ("Figura: <név>"); az oldal rögzít és szűr."""
    from handball.pipeline.view3d_html import view3d_html

    c = TestClient(_app(tmp_path, monkeypatch))
    url = "/matches/figura/felvetelek"
    all_ = [[0, {"t": 1}], [1.5, {"t": 2.5, "playing": True}]]
    fig = "u=20%2C10%3B24%2C5&l=0%2C1&cim=Kereszt"
    assert c.post(url, json={"allapotok": all_}).status_code == 400
    assert c.post(url, json={"allapotok": all_,
                             "figura": 'u=1"><b>'}).status_code == 400
    d = c.post(url, json={"nev": "Figura — Kereszt", "allapotok": all_,
                          "figura": fig}).json()
    lista = c.get(url).json()["felvetelek"]
    assert [(f["id"], f["figura"]) for f in lista] == [(d["id"], fig)]
    assert c.get(f"{url}/{d['id']}").json()["figura"] == fig
    assert c.post(f"{url}/{d['id']}/megnezte",
                  json={"nev": "Anna"}).status_code == 200
    lap = c.get("/kovet").text
    assert (f'href="/figura3d?{fig.replace("&", "&amp;")}&amp;felvetel={d["id"]}"'
            in lap)
    assert "Figura: Kereszt" in lap
    r = c.get("/library/recordings").json()["felvetelek"][0]
    assert (r["match_id"], r["home_team"], r["figura"]) == ("figura", "Kereszt", fig)
    assert c.delete(f"{url}/{d['id']}").status_code == 200
    assert c.get(url).json()["felvetelek"] == []
    # (a meccs-felvétel útja nem változott: ismeretlen meccs 404)
    assert c.post("/matches/nincs/felvetelek",
                  json={"allapotok": all_}).status_code == 404
    m, e = setplay_3d_match([[(20, 10), (27, 10)]], DefenseModel())
    oldal = view3d_html(m, figura=e)
    for kell in ('const FV_VAN = !!(ADAT.match_id || FIGURA) && !FV_CSOMAG;',
                 '...(FIGURA ? {figura: FIGURA_KOD} : {})})});',
                 ".filter(f => !FIGURA || f.figura === FIGURA_KOD);"):
        assert kell in oldal, kell


def test_a_figura_felvetel_csomagja(tmp_path, monkeypatch):
    """📦 A figura-felvétel csomagja: a figura-oldal a felvétel figurájából,
    a felvétellel beágyazva (motor nélkül — a figura motoros gombjai
    ki); figura nélküli felvételhez 404."""
    import json

    c = TestClient(_app(tmp_path, monkeypatch))
    url = "/matches/figura/felvetelek"
    fig = "u=20%2C10%2C27%2C10%3B24%2C5&l=0%2C1&cim=Kereszt&rendszer=5-1"
    d = c.post(url, json={"allapotok": [[0, {"t": 1}], [2, {"t": 3}]],
                          "figura": fig}).json()
    r = c.get(f"{url}/{d['id']}/csomag")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    html = r.text
    assert "const FV_CSOMAG = {" in html and d["id"] in html
    assert '"figura":{' in html and "Kereszt vs Védelem (5-1, 6 védő, 6,0 m)" in html
    assert ('if (FV_CSOMAG){ lapGomb.style.display = "none"; '
            'videoLe.style.display = "none"; }') in html
    # figura nélküli (sérült) felvétel: nincs miből építeni
    fajl = next(tmp_path.rglob(f"figura.felvetelek/{d['id']}.json"))
    adat = json.loads(fajl.read_text(encoding="utf-8"))
    adat.pop("figura")
    fajl.write_text(json.dumps(adat), encoding="utf-8")
    assert c.get(f"{url}/{d['id']}/csomag").status_code == 404


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


_AJANLO_FIGURAK = [
    {"id": "a", "name": "Áttörés",
     "attackers": [[[26, 10], [29, 10], [31.5, 10]], [[26, 4], [26, 4], [26, 4]]]},
    {"id": "b", "name": "Szél", "labda": [1, 1, 0],
     "attackers": [[[30, 2], [33, 2], [36, 1.5]], [[27, 10], [29, 10], [30, 10]]]},
    {"id": "c", "name": "Átlövő",
     "attackers": [[[27, 13], [28, 13], [29, 13]], [[27, 6], [27, 6], [27, 6]]]},
    {"id": "x", "name": "Hibás", "attackers": []},
    {"id": "y", "name": "Szöveg", "attackers": [[["a", "b"]]]},
]


def test_a_figura_ajanlo_rangsorol_es_figyelmeztet():
    """5-1 fal ellen: a szélső figura az első (az alaphoz képest sem zár
    jobban), a középső áttörést viszont az előretolt védő elvágja — arra
    figyelmeztet. A hibás figurák kimaradnak; a rangsor csökkenő."""
    from handball.pipeline.play_simulation import (AJANLO_ELTERES_PP,
                                                   rank_playbook)

    r = rank_playbook(_AJANLO_FIGURAK,
                      DefenseModel(num_defenders=5, rendszer="5-1"))
    ids = [s["id"] for s in r["figurak"]]
    assert ids[0] == "b" and set(ids) == {"a", "b", "c"}
    pontok = [s["pont_pct"] for s in r["figurak"]]
    assert pontok == sorted(pontok, reverse=True)
    attores = next(s for s in r["figurak"] if s["id"] == "a")
    assert attores["elteres_pp"] <= -AJANLO_ELTERES_PP
    assert r["ajanlas"].startswith("Ellenük a(z) „Szél” figura működik a "
                                   "legjobban")
    assert "a 2. támadónál" in r["ajanlas"]
    assert "Óvatosan a(z) „Áttörés” figurával" in r["ajanlas"]


def test_a_figura_ajanlo_kimondja_a_rest_es_ures_konyvtarnal_hallgat():
    """A ritka (kétvédős) fal az áttörést jóval rosszabbul zárja, mint az
    alap: az ajánlás kimondja a különbséget; az alap fal ellen nincs
    eltérés, nincs figyelmeztetés; üres könyvtárnál nincs ajánlás."""
    from handball.pipeline.play_simulation import rank_playbook

    r = rank_playbook(_AJANLO_FIGURAK[:1], DefenseModel(num_defenders=2))
    assert "az 1. támadónál" in r["ajanlas"]
    assert "százalékponttal rosszabbul zárja, mint az alap 6-0" in r["ajanlas"]
    alap = rank_playbook(_AJANLO_FIGURAK, DefenseModel())
    assert all(s["elteres_pp"] == 0.0 for s in alap["figurak"])
    assert "Óvatosan" not in alap["ajanlas"]
    assert "rosszabbul zárja" not in alap["ajanlas"]
    assert rank_playbook([], DefenseModel()) == {"figurak": [],
                                                 "ajanlas": None}


def test_a_figura_ajanlo_vegpont(tmp_path, monkeypatch):
    """GET /playbook-rangsor: a mentett figurák rangsora a tanult (vagy a
    kézi) fal ellen, a fal nevével; hibás védő-oldalra 400, ismeretlen
    meccsre 404."""
    c = TestClient(_app(tmp_path, monkeypatch))
    for d in _AJANLO_FIGURAK[:3]:
        body = {"name": d["name"], "attackers": d["attackers"]}
        if "labda" in d:
            body["labda"] = d["labda"]
        assert c.post("/playbook", json=body).status_code == 200
    r = c.get("/playbook-rangsor", params={"rendszer": "5-1", "vedok": 5})
    assert r.status_code == 200
    j = r.json()
    assert j["vedelem"].startswith("Védelem (5-1")
    assert [s["name"] for s in j["figurak"]][0] == "Szél"
    assert "Óvatosan a(z) „Áttörés” figurával" in j["ajanlas"]
    r = c.get("/playbook-rangsor", params={"meccs": "fm", "vedo": "away"})
    assert r.status_code == 200 and r.json()["vedelem"].startswith(
        "Tanult védelem — B")
    assert len(r.json()["figurak"]) == 3
    assert c.get("/playbook-rangsor", params={"meccs": "fm",
                                              "vedo": "x"}).status_code == 400
    assert c.get("/playbook-rangsor",
                 params={"meccs": "nincs"}).status_code == 404


def test_a_figurafuzet_tanult_fal_ellen_a_rangsorban_jon(tmp_path,
                                                        monkeypatch):
    """A tanult fal elleni figurafüzet a figura-ajánló rangsorában hozza
    a figurákat, az ajánló mondattal; kézi falnál név szerint, ajánlás
    nélkül."""
    import re

    app = _app(tmp_path, monkeypatch)
    app.state.put_match(Match(MatchMeta(match_id="m51", home_team="A",
                                        away_team="Ötegyes", fps=25.0),
                              _otegyes_frames()))
    c = TestClient(app)
    for d in _AJANLO_FIGURAK[:3]:
        body = {"name": d["name"], "attackers": d["attackers"]}
        if "labda" in d:
            body["labda"] = d["labda"]
        assert c.post("/playbook", json=body).status_code == 200

    def sorrend(html):
        tj = re.search(r'<ol class="tj">(.*?)</ol>', html).group(1)
        return re.findall(r"<li>(.*?)</li>", tj)

    r = c.get("/figura-fuzet", params={"meccs": "m51", "vedo": "away"})
    assert r.status_code == 200
    rang = c.get("/playbook-rangsor",
                 params={"meccs": "m51", "vedo": "away"}).json()
    assert sorrend(r.text) == [s["name"] for s in rang["figurak"]]
    assert 'class="ajanlo"' in r.text and "Ellenük a(z)" in r.text
    r = c.get("/figura-fuzet")
    # (a név-sorrend a kisbetűs kódpont szerinti — az ékezetes a végén)
    assert sorrend(r.text) == ["Szél", "Átlövő", "Áttörés"]
    assert 'class="ajanlo"' not in r.text


def _otegyes_frames():
    """A hazai támad, a vendég 5-1-ben véd (5 védő a 6 m-en, egy
    előretolt 9,5 m-en) — a tanult fal 5-1."""
    frames = []
    for t in range(10):
        players = [PlayerPosition(track_id=i + 1, team=Team.HOME, x=28.0,
                                  y=10.0, source=PositionSource.MEASURED,
                                  confidence=1.0) for i in range(3)]
        players += [PlayerPosition(track_id=100 + i, team=Team.AWAY, x=x,
                                   y=y, source=PositionSource.MEASURED,
                                   confidence=1.0)
                    for i, (x, y) in enumerate([(34, 3), (34, 6.5), (34, 10),
                                                (34, 13.5), (34, 17),
                                                (30.5, 10)])]
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=28.0, y=10.0, confidence=1.0)))
    return frames


def test_a_felderito_lap_hozza_a_figura_ajanlot(tmp_path, monkeypatch):
    """A nyomtatható felderítő lap (scouting/export) a mentett figuráink
    rangsorát is hozza a felderített csapat tanult fala ellen; mentett
    figura nélkül a szakasz nincs."""
    app = _app(tmp_path, monkeypatch)
    app.state.put_match(Match(MatchMeta(match_id="m51", home_team="A",
                                        away_team="Ötegyes", fps=25.0),
                              _otegyes_frames()))
    c = TestClient(app)
    r = c.get("/matches/m51/scouting/export", params={"team": "away"})
    assert r.status_code == 200 and "Figuráink ellenük" not in r.text
    for d in _AJANLO_FIGURAK[:3]:
        body = {"name": d["name"], "attackers": d["attackers"]}
        if "labda" in d:
            body["labda"] = d["labda"]
        assert c.post("/playbook", json=body).status_code == 200
    r = c.get("/matches/m51/scouting/export", params={"team": "away"})
    assert r.status_code == 200
    assert "Figuráink ellenük" in r.text and "Ellenük a(z)" in r.text


def test_a_vedekezesi_proba_vegpont_es_a_felderito_lap(tmp_path, monkeypatch):
    """GET /matches/{id}/vedekezesi-proba: az ő visszatérő figurájuk a
    meccs másik oldalának (a mi) tanult fala ellen, 3D-linkkel; a
    nyomtatható felderítő lap ugyanezt hozza. Hibás oldalra 400,
    ismeretlen meccsre 404."""
    from test_play_simulation import _proba_match

    app = _app(tmp_path, monkeypatch)
    app.state.put_match(_proba_match())
    c = TestClient(app)
    r = c.get("/matches/pr/vedekezesi-proba", params={"csapat": "home"})
    assert r.status_code == 200
    j = r.json()
    assert (j["csapat"], j["vedelem"]) == ("Ők", "Mi")
    assert len(j["figurak"]) == 1 and j["figurak"][0]["ismetles"] == 3
    link = j["figurak"][0]["link"]
    assert "meccs=pr" in link and "vedo=away" in link
    assert c.get("/figura3d?" + link).status_code == 200
    assert j["verdict"].startswith("a legveszélyesebb visszatérő figurájuk")
    # Az ő tanult lövőik (ebből a meccsből: nincs lövés → üres felirat),
    # a figura mezszámai és a záró lövő a sorban.
    assert j["lovo_felirat"] == ""
    assert sorted(j["figurak"][0]["mez"]) == [1, 2, 3]
    assert j["figurak"][0]["lovo_mez"] in (1, 2, 3)
    assert j["figurak"][0]["lovo_szorzo"] == 1.0
    lap = c.get("/matches/pr/scouting/export", params={"team": "home"})
    assert lap.status_code == 200
    assert "Figuráik a falatok ellen" in lap.text
    assert "A legveszélyesebb visszatérő figurájuk" in lap.text
    assert c.get("/matches/pr/vedekezesi-proba",
                 params={"csapat": "x"}).status_code == 400
    assert c.get("/matches/nincs/vedekezesi-proba").status_code == 404
    assert c.get("/matches/pr/vedekezesi-proba",
                 params={"vedo_meccs": "nincs"}).status_code == 404


def test_az_ai_finomitas_vegpont(tmp_path, monkeypatch):
    """POST /figura-finomitas: a kézi 5-1 fal ellen javaslatot ad (a
    javult lövőhelyzettel és a változásokkal), a fal nevével; hibás
    figurára 400, ismeretlen meccsre 404."""
    c = TestClient(_app(tmp_path, monkeypatch))
    figura = [[[26, 10], [29, 10], [31.5, 10]], [[26, 4], [26, 4], [26, 4]],
              [[30, 2], [33, 2], [36, 1.5]], [[27, 15], [28, 15], [29, 15]]]
    r = c.post("/figura-finomitas", json={
        "attackers": figura, "labda": [0, 0, 1], "rendszer": "5-1"})
    assert r.status_code == 200
    j = r.json()
    assert j["vedelem"].startswith("Védelem (5-1")
    assert j["pont_utana"] > j["pont_elotte"] and j["valtozasok"]
    assert len(j["attackers"]) == 4
    assert c.post("/figura-finomitas",
                  json={"attackers": []}).status_code == 400
    assert c.post("/figura-finomitas",
                  json={"attackers": [[["a", 1]]]}).status_code == 400
    assert c.post("/figura-finomitas", json={
        "attackers": figura, "meccs": "nincs"}).status_code == 404


def test_a_tanult_kapus_a_szimulacioban_es_a_3d_fejlecben(tmp_path,
                                                         monkeypatch):
    """A /simulate-setplay a tanult kapus szorzójával értékel, és egy
    mondatban visszaadja; a 3D fejléce is kiírja. A kapus a valódi
    forrás-láncból (lövéses szimulált meccs)."""
    from handball.sim.match_simulator import simulate_ground_truth

    app = _app(tmp_path, monkeypatch)
    m = simulate_ground_truth(duration_s=300, fps=25.0, seed=1,
                              shots_per_min=8, halftime_break_s=30)
    m.meta.match_id = "lov"
    app.state.put_match(m)
    c = TestClient(app)
    r = c.post("/matches/lov/simulate-setplay", params={"defending": "away"},
               json={"attackers": [[[28, 10], [30, 10]], [[26, 4], [27, 4]]],
                     "ball_carrier": [0, 0]})
    assert r.status_code == 200
    j = r.json()
    assert j["defense_model"]["kapus"]
    assert j["kapus_felirat"].startswith("a kapus ")
    k = j["kimenetek"]
    assert k and k["n"] > 0 and k["gol"] + k["vedett"] + k["eladott"] == k["n"]
    r = c.get("/figura3d", params={"u": U, "meccs": "lov", "vedo": "away"})
    assert r.status_code == 200 and "a kapus " in r.text


def test_az_elo_figura_riasztas_a_probaval_mondja_a_falatok_elleni_erteket(
        tmp_path, monkeypatch):
    """Két meccsen ugyanazt a figurát hozó csapat: a könyvtár visszatérő
    figurája riasztást ad, és mivel a védekezési próba ugyanezt a figurát
    ismeri (a tagok kockái fedik a riasztás szakaszát), a riasztás a mi
    tanult falunk elleni lövőhelyzetet is kimondja."""
    from test_play_simulation import _proba_match

    app = _app(tmp_path, monkeypatch)
    m1 = _proba_match()
    m2 = _proba_match()
    m2.meta.match_id = "pr2"
    app.state.put_match(m1)
    app.state.put_match(m2)
    c = TestClient(app)
    r = c.get("/matches/pr/vedekezesi-proba", params={"csapat": "home"})
    tagok = r.json()["figurak"][0]["tagok"]
    assert len(tagok) == 3 and all(a < b for a, b in tagok)
    al = c.get("/matches/pr/figure-alerts").json()["alerts"]
    assert al and all(a["team"] == "home" for a in al)
    assert all(a["proba_pct"] is not None and a["alap_pct"] is not None
               for a in al)
    assert "A próba szerint a falatok ellen " in al[0]["text"]
    assert "lövőhelyzetet teremt (alap fal: " in al[0]["text"]
    assert al[0]["text"].startswith("Ismert figura: Ők ")


def test_a_figura_oldalak_fala_a_csapat_osszes_meccsebol(tmp_path,
                                                        monkeypatch):
    """`csapat=<név>`: a 3D, a figura-lap, a figura-ajánló és az
    AI-finomító fala a könyvtár összes olyan meccséből tanul, ahol a
    csapat játszott (a név mutatja a meccsszámot); ismeretlen névre 404.
    A két meccs összege ugyanazt a falat adja, mint a learn_many."""
    from test_play_simulation import _proba_match

    app = _app(tmp_path, monkeypatch)
    m1 = _proba_match()
    m2 = _proba_match()
    m2.meta.match_id = "pr2"
    app.state.put_match(m1)
    app.state.put_match(m2)
    c = TestClient(app)
    r = c.get("/figura3d", params={"u": U, "csapat": "Mi"})
    assert r.status_code == 200
    assert "Figura vs Tanult védelem — Mi (2 meccs)" in r.text
    r = c.get("/figura-lap", params={"u": U, "csapat": "Mi"})
    assert r.status_code == 200 and "Mi (2 meccs)" in r.text
    r = c.get("/playbook-rangsor", params={"csapat": "Mi"})
    assert r.status_code == 200
    assert r.json()["vedelem"].startswith("Tanult védelem — Mi (2 meccs)")
    r = c.post("/figura-finomitas", json={
        "attackers": [[[26, 10], [29, 10], [31.5, 10]],
                      [[26, 4], [26, 4], [26, 4]]], "csapat": "Mi"})
    assert r.status_code == 200
    assert r.json()["vedelem"].startswith("Tanult védelem — Mi (2 meccs)")
    assert c.get("/figura3d", params={"u": U,
                                      "csapat": "Senki"}).status_code == 404
    vart = DefenseModel.learn_many([(m1, Team.AWAY), (m2, Team.AWAY)])
    egy = DefenseModel.learn(m1, Team.AWAY)
    assert (vart.num_defenders, vart.rendszer) == (egy.num_defenders,
                                                   egy.rendszer)
    # A tervező szimulációja is: csapat → a könyvtár összes meccséből.
    torzs = {"attackers": [[[28, 10], [30, 10]], [[26, 4], [27, 4]]],
             "ball_carrier": [0, 0]}
    r = c.post("/matches/pr/simulate-setplay", params={"csapat": "Mi"},
               json=torzs)
    assert r.status_code == 200 and r.json()["meccsek"] == 2
    r = c.post("/matches/pr/simulate-setplay", params={"defending": "away"},
               json=torzs)
    assert r.status_code == 200 and r.json()["meccsek"] == 1
    assert c.post("/matches/pr/simulate-setplay", params={"csapat": "Senki"},
                  json=torzs).status_code == 404


def test_a_felderites_probaja_es_ajanloja_a_szezon_falbol(tmp_path,
                                                         monkeypatch):
    """szezon=1: a védekezési próba falunk a könyvtár összes meccséből
    (meccsek = 2, a 3D-link a csapat nevével), a figura-ajánló fala a
    meccs védő csapatának összes meccséből ("(2 meccs)"); a nyomtatható
    felderítő lap is a szezon-falat írja."""
    from test_play_simulation import _proba_match

    app = _app(tmp_path, monkeypatch)
    m1 = _proba_match()
    m2 = _proba_match()
    m2.meta.match_id = "pr2"
    app.state.put_match(m1)
    app.state.put_match(m2)
    c = TestClient(app)
    r = c.get("/matches/pr/vedekezesi-proba",
              params={"csapat": "home", "szezon": 1})
    assert r.status_code == 200
    j = r.json()
    assert j["meccsek"] == 2 and j["vedelem"] == "Mi"
    assert "csapat=Mi" in j["figurak"][0]["link"]
    assert c.get("/figura3d?" + j["figurak"][0]["link"]).status_code == 200
    egy = c.get("/matches/pr/vedekezesi-proba", params={"csapat": "home"})
    assert egy.json()["meccsek"] == 1
    for d in _AJANLO_FIGURAK[:2]:
        assert c.post("/playbook", json={"name": d["name"],
                                         "attackers": d["attackers"]}
                      ).status_code == 200
    r = c.get("/playbook-rangsor", params={"meccs": "pr", "vedo": "away",
                                           "szezon": 1})
    assert r.status_code == 200
    assert r.json()["vedelem"].startswith("Tanult védelem — Mi (2 meccs)")
    assert r.json()["lovo_felirat"] == ""      # a mi lövőink: nincs lövés
    # A nyomtatható felderítő lap ajánlója a MI szezon-lövőinkkel
    # rangsorol (a felderített vendég ellenfele a hazai — mindkét
    # meccsünkből), nem a lövők nélkül.
    import handball.pipeline.play_simulation as ps
    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import AttackModel
    kapott = {}
    eredeti = ps.rank_playbook

    def _rp(figurak, defense, **kw):
        kapott["tamadas"] = kw.get("tamadas")
        return eredeti(figurak, defense, **kw)

    monkeypatch.setattr(ps, "rank_playbook", _rp)
    monkeypatch.setattr(ps.AttackModel, "learn_many", classmethod(
        lambda cls, meccsek, config=None: (
            kapott.setdefault("meccsek", [(m.meta.match_id, tm)
                                          for m, tm in meccsek])
            and AttackModel(lovok={1: {"close": 1.3}}))))
    r = c.get("/matches/pr/scouting/export", params={"team": "away"})
    assert r.status_code == 200
    assert "Figuráink ellenük" in r.text and "Ellenük a(z)" in r.text
    assert kapott["tamadas"].lovok == {1: {"close": 1.3}}
    assert sorted(kapott["meccsek"]) == [("pr", Team.HOME), ("pr2", Team.HOME)]


def test_a_mezszammal_mentett_figura_zaro_lovoje_a_rangsorban(tmp_path,
                                                             monkeypatch):
    """POST /playbook a "mez" sorral (támadónként mezszám vagy null)
    menti a mezszámokat, a GET visszaadja; a figura-ajánló sora a záró
    lövő mezszámát mondja (a modell nélkül 1-es szorzóval). Rossz hosszú
    vagy nem szám mezszám-sor: 400; csupa null: nem kerül a fájlba."""
    from test_play_simulation import _proba_match

    app = _app(tmp_path, monkeypatch)
    app.state.put_match(_proba_match())
    c = TestClient(app)
    d = _AJANLO_FIGURAK[0]
    mez = [7] * len(d["attackers"])
    r = c.post("/playbook", json={"name": "Mezes", "attackers": d["attackers"],
                                  "mez": mez})
    assert r.status_code == 200
    assert c.get(f"/playbook/{r.json()['id']}").json()["mez"] == mez
    assert c.post("/playbook", json={"name": "x", "attackers": d["attackers"],
                                     "mez": [7]}).status_code == 400
    assert c.post("/playbook", json={"name": "x", "attackers": d["attackers"],
                                     "mez": ["a"] * len(mez)}).status_code == 400
    ures = c.post("/playbook", json={"name": "Ures", "attackers": d["attackers"],
                                     "mez": [None] * len(mez)})
    assert ures.status_code == 200
    assert "mez" not in c.get(f"/playbook/{ures.json()['id']}").json()
    rang = c.get("/playbook-rangsor", params={"meccs": "pr", "vedo": "away"})
    assert rang.status_code == 200
    sorok = {s["name"]: s for s in rang.json()["figurak"]}
    assert sorok["Mezes"]["lovo_mez"] == 7 and sorok["Mezes"]["lovo_szorzo"] == 1.0
    assert sorok["Ures"]["lovo_mez"] is None
    assert rang.json()["lovo_felirat"] == ""
    lap = c.get("/matches/pr/scouting/export", params={"team": "home"})
    assert lap.status_code == 200 and "Figuráink ellenük" in lap.text
    assert "Figuráik a falatok ellen" in lap.text


def test_mentett_figura_nelkul_az_alap_figurak_rangsora(tmp_path,
                                                        monkeypatch):
    """Üres könyvtárral a figura-ajánló az öt alap-figurát rangsorolja
    (sablon=true, minden sor sablon, öt sor, mind érvényes); a sablon
    betölthető a /playbook/{id}-n; egy mentett figura után már csak az
    jön (sablon=false)."""
    from handball.pipeline.play_simulation import ALAP_FIGURAK

    assert len(ALAP_FIGURAK) == 5
    assert len({d["id"] for d in ALAP_FIGURAK}) == 5
    c = TestClient(_app(tmp_path, monkeypatch))
    r = c.get("/playbook-rangsor", params={"rendszer": "5-1", "vedok": 5})
    assert r.status_code == 200
    j = r.json()
    assert j["sablon"] is True and len(j["figurak"]) == 5
    assert all(s["sablon"] and s["pont_pct"] > 0 for s in j["figurak"])
    assert j["ajanlas"].startswith("Ellenük a(z) „")
    sab = c.get("/playbook/sablon-kereszt")
    assert sab.status_code == 200 and sab.json()["sablon"] is True
    assert c.get("/playbook/sablon-nincs").status_code == 404
    assert c.post("/playbook", json={"name": "Saját",
                                     "attackers": _AJANLO_FIGURAK[0]["attackers"]}
                  ).status_code == 200
    j = c.get("/playbook-rangsor").json()
    assert j["sablon"] is False
    assert [s["name"] for s in j["figurak"]] == ["Saját"]
    # A könyvtár-lista is: üresen a sablonok, mentett figurával csak az.
    c2 = TestClient(_app(tmp_path / "ures", monkeypatch))
    lista = c2.get("/playbook").json()["plays"]
    assert len(lista) == 5 and all(p["sablon"] for p in lista)
    assert lista[0]["players"] == 4
    assert [p["name"] for p in c.get("/playbook").json()["plays"]] == ["Saját"]


def test_a_3d_fejlec_megnevezi_a_kilepo_vedot(tmp_path, monkeypatch):
    from test_play_simulation import _vedo_match

    app = _app(tmp_path, monkeypatch)
    app.state.put_match(_vedo_match())
    r = TestClient(app).get("/figura3d", params={"u": U, "meccs": "v",
                                                 "vedo": "away"})
    assert r.status_code == 200 and "kilépő: #6 (100%)" in r.text
    assert "kettőző: #5 (100%)" in r.text


def test_az_elo_figura_ajanlo_vegpont(tmp_path, monkeypatch):
    """GET /matches/{id}/live-figura-ajanlo: mentett figurával azt
    rangsorolja (sablon=false), különben az alap-figurákat; 404 ismeretlen
    meccsre."""
    import handball.pipeline.play_simulation as ps
    from test_play_simulation import _proba_match

    monkeypatch.setattr(ps, "LIVE_AJANLO_PERCEK", (1,))
    app = _app(tmp_path, monkeypatch)
    app.state.put_match(_proba_match(ismetles=20))
    c = TestClient(app)
    r = c.get("/matches/pr/live-figura-ajanlo")
    assert r.status_code == 200 and r.json()["alerts"][0]["sablon"] is True
    assert c.post("/playbook", json={"name": "Saját",
                                     "attackers": _AJANLO_FIGURAK[0]["attackers"]}
                  ).status_code == 200
    j = c.get("/matches/pr/live-figura-ajanlo").json()["alerts"]
    assert j and j[0]["name"] == "Saját" and j[0]["sablon"] is False
    assert "a figuráink közül a „Saját”" in j[0]["text"]
    assert j[0]["lovo_mez"] is None and j[0]["lovo_szorzo"] == 1.0
    # Mezszámmal mentett figura: a záró lövő a sorban (lövés nélküli
    # könyvtár: a szorzó 1).
    assert c.post("/playbook", json={
        "name": "Mezes", "attackers": _AJANLO_FIGURAK[0]["attackers"],
        "mez": [7] * len(_AJANLO_FIGURAK[0]["attackers"])}).status_code == 200
    j = c.get("/matches/pr/live-figura-ajanlo").json()["alerts"]
    mezes = [a for a in j if a["name"] == "Mezes" or a["lovo_mez"] == 7]
    assert all(a["lovo_szorzo"] == 1.0 for a in j)
    assert mezes or j[0]["lovo_mez"] is None
    assert c.get("/matches/nincs/live-figura-ajanlo").status_code == 404


def test_az_elo_utolso_labda_vegpont_a_szezon_modelljeivel(tmp_path,
                                                           monkeypatch):
    """GET /matches/{id}/live-utolso-labda: a lövő- és a kapus-modell a
    könyvtár KORÁBBI meccseiből (ez a meccs nélkül — szezon_meccsek), a
    hajrá riasztása a küszöb feloldásával a lövő csapatnak; lövés
    nélküli meccsen (modell nélkül) üres; 404 ismeretlen meccsre."""
    import handball.pipeline.play_simulation as ps
    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import (AttackModel, kapus_many,
                                                   last_shot_choice)
    from handball.sim.match_simulator import simulate_ground_truth
    from test_play_simulation import _proba_match

    monkeypatch.setattr(ps, "LIVE_UTOLSO_KULONBSEG", 100)
    app = _app(tmp_path, monkeypatch)
    m1 = simulate_ground_truth(duration_s=600, fps=25.0, seed=1,
                               shots_per_min=8, halftime_break_s=30)
    m2 = simulate_ground_truth(duration_s=600, fps=25.0, seed=2,
                               shots_per_min=8, halftime_break_s=30)
    m1.meta.match_id, m2.meta.match_id = "gt1", "gt2"
    assert (m1.meta.home_team, m1.meta.away_team) == (
        m2.meta.home_team, m2.meta.away_team)
    app.state.put_match(m1)
    app.state.put_match(m2)
    c = TestClient(app)
    r = c.get("/matches/gt1/live-utolso-labda")
    assert r.status_code == 200
    j = r.json()
    assert j["szezon_meccsek"] == {"home": 1, "away": 1}
    assert [a["team"] for a in j["alerts"]] == ["home"]
    vart = last_shot_choice(AttackModel.learn_many([(m2, Team.HOME)]),
                            kapus_many([(m2, Team.AWAY)]))
    assert j["alerts"][0]["text"].endswith(vart["verdict"])
    app.state.put_match(_proba_match(ismetles=60))
    assert c.get("/matches/pr/live-utolso-labda").json()["alerts"] == []
    assert c.get("/matches/nincs/live-utolso-labda").status_code == 404


def test_az_elo_ai_megbizhatosag_vegpont_a_korabbi_meccsekbol(tmp_path,
                                                             monkeypatch):
    """GET /matches/{id}/live-modell-proba: csapatonként a KORÁBBI
    meccsek (ez a meccs nélkül) mintáiból a három próba és az egy soros
    összegzés — a valódi láncon (három szimulált meccs, a harmadikra
    kérve) ugyanaz, mint a motor a másik két meccsből; egyetlen másik
    meccsnél nincs sor; 404 ismeretlen meccsre."""
    import json

    from handball.models.tracking import Team
    from handball.pipeline.decisions import (decision_model_check,
                                             decision_outcome_sample,
                                             decision_samples_sum)
    from handball.pipeline.play_simulation import (keeper_model_backtest,
                                                   model_trust_summary,
                                                   player_model_sample,
                                                   shooter_model_backtest)
    from handball.sim.match_simulator import simulate_ground_truth

    app = _app(tmp_path, monkeypatch)
    meccsek = []
    for seed in (1, 2, 3):
        m = simulate_ground_truth(duration_s=600, fps=25.0, seed=seed,
                                  shots_per_min=8, halftime_break_s=30)
        m.meta.match_id = f"gt{seed}"
        m.meta.date = f"2026-10-0{seed}"
        meccsek.append(m)
        app.state.put_match(m)
        if seed == 2:
            # Egyetlen MÁSIK meccs a könyvtárban: a próbához kevés.
            c = TestClient(app)
            assert c.get("/matches/gt2/live-modell-proba").json()[
                "alerts"] == []
    j = c.get("/matches/gt3/live-modell-proba").json()
    korabbi = meccsek[:2]
    for side, team in (("home", Team.HOME), ("away", Team.AWAY)):
        mintak = [json.loads(json.dumps(player_model_sample(m, team)))
                  for m in korabbi]
        lp = shooter_model_backtest([x["lovo"] for x in mintak])
        kp = keeper_model_backtest([x["kapus"] for x in mintak])
        dp = decision_model_check(decision_samples_sum(
            [decision_outcome_sample(m)[side] for m in korabbi]))
        from handball.pipeline.play_simulation import defender_model_backtest
        vp = defender_model_backtest([x["vedok"] for x in mintak])
        sor = model_trust_summary(lp, kp, dp, vp)
        talalt = [a for a in j["alerts"]
                  if a["team"] == side and a["fajta"] == "modellek"]
        if sor is None:
            assert talalt == []
        else:
            [a] = talalt
            assert a["meccsek"] == 2
            assert a["text"].endswith(f"(2 korábbi meccs): {sor}") or \
                a["text"] == (f"AI-megbízhatóság ({a['team_name']}, 2 korábbi "
                              f"meccs): {sor}")
    assert j["alerts"], "a valódi láncon legalább egy próba ítél"
    assert c.get("/matches/nincs/live-modell-proba").status_code == 404


def test_az_elo_kapus_valasztas_vegpont_a_szezon_mintaival(tmp_path,
                                                           monkeypatch):
    """GET /matches/{id}/live-kapus-valasztas: az ő lövőik az ellenfél, a
    kapusaink a csapat könyvtári KORÁBBI meccseiből (ez a meccs nélkül —
    szezon_meccsek), a riasztás ugyanaz, mint a motor a kész mintákkal;
    404 ismeretlen meccsre."""
    import handball.pipeline.play_simulation as ps
    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import (kapus_mintak_many,
                                                   live_keeper_alerts,
                                                   lovo_minta_many)
    from handball.sim.match_simulator import simulate_ground_truth

    monkeypatch.setattr(ps, "LIVE_AJANLO_PERCEK", (3, 6))
    app = _app(tmp_path, monkeypatch)
    m1 = simulate_ground_truth(duration_s=600, fps=25.0, seed=1,
                               shots_per_min=8, halftime_break_s=30)
    m2 = simulate_ground_truth(duration_s=600, fps=25.0, seed=2,
                               shots_per_min=8, halftime_break_s=30)
    m1.meta.match_id, m2.meta.match_id = "gt1", "gt2"
    app.state.put_match(m1)
    app.state.put_match(m2)
    c = TestClient(app)
    r = c.get("/matches/gt1/live-kapus-valasztas")
    assert r.status_code == 200
    j = r.json()
    assert j["szezon_meccsek"] == {"home": 1, "away": 1}
    vart = live_keeper_alerts(
        m1, lovo_mintak={"home": lovo_minta_many([(m2, Team.AWAY)]),
                         "away": lovo_minta_many([(m2, Team.HOME)])},
        kapus_mintak={"home": kapus_mintak_many([(m2, Team.HOME)]),
                      "away": kapus_mintak_many([(m2, Team.AWAY)])})["alerts"]
    assert [a["text"] for a in j["alerts"]] == [a["text"] for a in vart]
    assert kapus_mintak_many([]) == {}
    assert c.get("/matches/nincs/live-kapus-valasztas").status_code == 404


def test_az_elo_loves_elosztas_vegpont_a_szezon_modelljeivel(tmp_path,
                                                             monkeypatch):
    """GET /matches/{id}/live-loves-elosztas: a lövő-modell a csapat, a
    kapus-modell az ellenfél könyvtári KORÁBBI meccseiből (ez a meccs
    nélkül — szezon_meccsek), a riasztás ugyanaz, mint a motor a kész
    modellekkel; 404 ismeretlen meccsre."""
    import handball.pipeline.play_simulation as ps
    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import (AttackModel, kapus_many,
                                                   live_shot_allocation_alerts)
    from handball.sim.match_simulator import simulate_ground_truth

    monkeypatch.setattr(ps, "LIVE_AJANLO_PERCEK", (3, 6))
    app = _app(tmp_path, monkeypatch)
    m1 = simulate_ground_truth(duration_s=600, fps=25.0, seed=1,
                               shots_per_min=8, halftime_break_s=30)
    m2 = simulate_ground_truth(duration_s=600, fps=25.0, seed=2,
                               shots_per_min=8, halftime_break_s=30)
    m1.meta.match_id, m2.meta.match_id = "gt1", "gt2"
    app.state.put_match(m1)
    app.state.put_match(m2)
    c = TestClient(app)
    r = c.get("/matches/gt1/live-loves-elosztas")
    assert r.status_code == 200
    j = r.json()
    assert j["szezon_meccsek"] == {"home": 1, "away": 1}
    vart = live_shot_allocation_alerts(
        m1, tamadas={"home": AttackModel.learn_many([(m2, Team.HOME)]),
                     "away": AttackModel.learn_many([(m2, Team.AWAY)])},
        kapus={"home": kapus_many([(m2, Team.AWAY)]),
               "away": kapus_many([(m2, Team.HOME)])})["alerts"]
    assert [a["text"] for a in j["alerts"]] == [a["text"] for a in vart]
    assert c.get("/matches/nincs/live-loves-elosztas").status_code == 404


def test_az_elo_kit_kinek_vegpont_a_szezon_lovoivel(tmp_path, monkeypatch):
    """GET /matches/{id}/live-kit-kinek: a lövő-modell, a sáv- és a nyers
    minta az ELLENFÉL könyvtári KORÁBBI meccseiből (ez a meccs nélkül —
    szezon_meccsek oldalanként az ellenfél meccsei), a riasztás a VÉDŐ
    oldalnak (a vendég fala a hazai lövői ellen) az addig látott falból
    — ugyanaz, mint a motor a kész modellekkel; a hazai fala nem
    tanulható (a vendég nem támad) → nincs; 404 ismeretlen meccsre."""
    import handball.pipeline.play_simulation as ps
    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import (AttackModel,
                                                   live_matchup_alerts,
                                                   lovo_minta_many,
                                                   lovo_sav_minta_many)
    from handball.sim.match_simulator import simulate_ground_truth

    monkeypatch.setattr(ps, "LIVE_AJANLO_PERCEK", (3, 6))
    app = _app(tmp_path, monkeypatch)
    m1 = simulate_ground_truth(duration_s=600, fps=25.0, seed=1,
                               shots_per_min=8, halftime_break_s=30)
    m2 = simulate_ground_truth(duration_s=600, fps=25.0, seed=2,
                               shots_per_min=8, halftime_break_s=30)
    m1.meta.match_id, m2.meta.match_id = "gt1", "gt2"
    app.state.put_match(m1)
    app.state.put_match(m2)
    c = TestClient(app)
    r = c.get("/matches/gt1/live-kit-kinek")
    assert r.status_code == 200
    j = r.json()
    assert j["szezon_meccsek"] == {"home": 1, "away": 1}
    ok = [(m2, Team.HOME)]
    vart = live_matchup_alerts(
        m1, tamadas={"away": AttackModel.learn_many(ok)},
        savok={"away": lovo_sav_minta_many(ok)},
        mintak={"away": lovo_minta_many(ok)})["alerts"]
    assert vart and all(a["team"] == "away" for a in vart)
    assert [a["text"] for a in j["alerts"]] == [a["text"] for a in vart]
    assert lovo_minta_many([]) == {} and lovo_sav_minta_many([]) == {}
    assert c.get("/matches/nincs/live-kit-kinek").status_code == 404


def test_az_elo_jelzesek_onkalibralasa_a_valodi_lancon(tmp_path,
                                                       monkeypatch):
    """Az élő kit-kinek jelzés a mögötte álló modell próbájával: az ő
    lövő-modelljük próbája a többi meccsükön (ez a meccs nélkül) — a
    valódi láncon (három szimulált meccs, az elsőre kérve) a
    "megbizhatosag" és a szöveg ugyanaz, mint a motor a másik két meccs
    mintáiból; ha a próba szerint az egyéni lövő-szorzó csak csapat-
    szinten igaz, a jelzés óvatos, és a szöveg végén az ok."""
    import json

    import handball.pipeline.play_simulation as ps
    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import (AttackModel,
                                                   BIZALOM_OVATOS_OKOK,
                                                   calibrate_alerts,
                                                   live_matchup_alerts,
                                                   lovo_minta_many,
                                                   lovo_sav_minta_many,
                                                   player_model_sample,
                                                   shooter_model_backtest,
                                                   trust_levels)
    from handball.sim.match_simulator import simulate_ground_truth

    monkeypatch.setattr(ps, "LIVE_AJANLO_PERCEK", (3, 6))
    app = _app(tmp_path, monkeypatch)
    meccsek = []
    for seed in (1, 2, 3):
        m = simulate_ground_truth(duration_s=600, fps=25.0, seed=seed,
                                  shots_per_min=8, halftime_break_s=30)
        m.meta.match_id = f"gt{seed}"
        m.meta.date = f"2026-10-0{seed}"
        meccsek.append(m)
        app.state.put_match(m)
    m1, tobbi = meccsek[0], meccsek[1:]
    c = TestClient(app)
    j = c.get("/matches/gt1/live-kit-kinek").json()
    ok = [(m, Team.HOME) for m in tobbi]
    proba = shooter_model_backtest(
        [json.loads(json.dumps(player_model_sample(m, Team.HOME)))["lovo"]
         for m in tobbi])
    szint = trust_levels(proba, None, None)["lovo"]
    # A párosításnál ("kit_kinek") a saját (vendég) védő-modellünk próbája
    # is a többi meccsünkön.
    from handball.pipeline.play_simulation import defender_model_backtest
    vszint = trust_levels(None, None, None, defender_model_backtest(
        [json.loads(json.dumps(player_model_sample(m, Team.AWAY)))["vedok"]
         for m in tobbi]))["vedo"]
    vart = []
    for a_ in live_matchup_alerts(
            m1, tamadas={"away": AttackModel.learn_many(ok)},
            savok={"away": lovo_sav_minta_many(ok)},
            mintak={"away": lovo_minta_many(ok)})["alerts"]:
        vart += calibrate_alerts([a_], {"away": {
            "lovo": szint, **({"vedo": vszint}
                              if a_["fajta"] == "kit_kinek" else {})}})
    assert vart
    assert [(a["text"], a["megbizhatosag"], a["ovatos"])
            for a in j["alerts"]] == [
        (a["text"], a["megbizhatosag"], a["ovatos"]) for a in vart]

    # A próba szerint az egyéni szorzó nem jobb a csapaténál → óvatos.
    monkeypatch.setattr(ps, "shooter_model_backtest",
                        lambda mintak: {"javulas_pct": 12.0,
                                        "egyeni_pct": -1.0})
    j2 = c.get("/matches/gt1/live-kit-kinek").json()
    ok_ = BIZALOM_OVATOS_OKOK[("lovo", "csapat")]
    assert j2["alerts"] and all(
        a["ovatos"] and a["megbizhatosag"]["lovo"] == "csapat"
        and ok_ in a["text"] for a in j2["alerts"])


def test_az_elorejelzes_vegpontjai_a_valodi_lancon(tmp_path, monkeypatch):
    """A meccs-előrejelzés a valódi láncon (hét rövid szimulált meccs,
    időrendben): GET /library/forecast a két csapat összes meccséből —
    ugyanaz, mint a motor a meccs-mintákból, a könyvtári próbával; 400
    hiányzó csapatnévre, 404 ismeretlen csapatra. GET /matches/{id}/
    live-elorejelzes a meccs NÉLKÜL (a többi hatból), a próba is a többi
    meccsen; egyetlen másik meccsnél üres. A /library/player-model-check "elorejelzes" mezője a
    könyvtár időrendjében a motor próbája."""
    import json

    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import (forecast_backtest,
                                                   forecast_backtest_text,
                                                   match_forecast,
                                                   match_forecast_sample,
                                                   match_forecast_text,
                                                   player_model_sample,
                                                   scorer_forecast,
                                                   scorer_forecast_backtest,
                                                   scorer_forecast_text,
                                                   defense_system_backtest,
                                                   defense_system_forecast,
                                                   defense_system_text)
    from handball.sim.match_simulator import simulate_ground_truth

    app = _app(tmp_path, monkeypatch)
    meccsek = []
    for seed in range(1, 8):
        m = simulate_ground_truth(duration_s=120, fps=25.0, seed=seed,
                                  shots_per_min=8)
        m.meta.match_id = f"gt{seed}"
        m.meta.date = f"2026-10-0{seed}"
        meccsek.append(m)
        app.state.put_match(m)
        if seed == 2:
            # Egyetlen MÁSIK meccs: az előrejelzéshez kevés → nincs sor.
            assert TestClient(app).get(
                "/matches/gt2/live-elorejelzes").json()["alerts"] == []
    h, a = meccsek[0].meta.home_team, meccsek[0].meta.away_team
    mintak = [json.loads(json.dumps(match_forecast_sample(m)))
              for m in meccsek]

    def lista(idx):
        return [{"match_id": meccsek[i].meta.match_id, "home": h, "away": a,
                 "minta": mintak[i]} for i in idx]

    def tort(idx, side):
        masik = "away" if side == "home" else "home"
        return [(mintak[i][side], mintak[i][masik]) for i in idx]

    c = TestClient(app)
    j = c.get("/library/forecast", params={"home": h, "away": a}).json()
    f = match_forecast(tort(range(7), "home"), tort(range(7), "away"))
    assert f is not None and j["forecast"] == f
    assert j["text"] == match_forecast_text(h, a, f)
    proba = forecast_backtest(lista(range(7)))
    assert proba is not None
    assert j["proba"] == json.loads(json.dumps(proba))
    assert j["proba_text"] == forecast_backtest_text(proba)
    assert c.get("/library/forecast", params={"home": h}).status_code == 400
    assert c.get("/library/forecast",
                 params={"home": h, "away": "Nincs"}).status_code == 404

    # A várható gólszerzők: a csapat lövő-mintái, az ellenfél kapus-
    # mintái (player_model_sample, a lemezes tár JSON-körbejárásával).
    jm = [{side: json.loads(json.dumps(player_model_sample(m, t)))
           for side, t in (("home", Team.HOME), ("away", Team.AWAY))}
          for m in meccsek]

    def gsz(idx, side):
        masik = "away" if side == "home" else "home"
        return scorer_forecast([jm[i][side]["lovo"] for i in idx],
                               [jm[i][masik]["kapus"] for i in idx])

    assert j["golszerzok"] == {"home": gsz(range(7), "home"),
                               "away": gsz(range(7), "away")}
    assert j["golszerzok"]["home"], "a hazai lövői tanulhatók"
    assert j["golszerzok_text"]["home"] == scorer_forecast_text(
        gsz(range(7), "home"))
    gp = scorer_forecast_backtest([
        {"match_id": meccsek[i].meta.match_id, "home": h, "away": a,
         "minta": jm[i]} for i in range(7)])
    assert j["golszerzo_proba"] == gp
    from handball.pipeline.play_simulation import key_player_text
    assert j["kulcsember_text"] == {
        "home": key_player_text(gsz(range(7), "home")),
        "away": key_player_text(gsz(range(7), "away"))}
    from handball.pipeline.play_simulation import key_player_absence
    assert j["kulcs_hiany"] == {
        "home": key_player_absence(gsz(range(7), "home"), f["home_goals"]),
        "away": key_player_absence(gsz(range(7), "away"), f["away_goals"])}
    # A várható védekezési rendszer: a csapat meccseinek "formak" mintái.
    ved = {side: defense_system_forecast([jm[i][side]["formak"]
                                          for i in range(7)])
           for side in ("home", "away")}
    assert j["vedekezes"] == ved and ved["away"] is not None
    assert j["vedekezes_text"]["away"] == defense_system_text(ved["away"])
    vp = defense_system_backtest([
        {"match_id": meccsek[i].meta.match_id, "home": h, "away": a,
         "minta": jm[i]} for i in range(7)])
    assert j["vedekezes_proba"] == vp

    # Élőben: a meccs eleji várható rendszer a többi hat meccsből.
    lv = c.get("/matches/gt7/live-vedekezes").json()["alerts"]
    v6 = defense_system_forecast([jm[i]["away"]["formak"] for i in range(6)])
    nyito = [x for x in lv if "varhato" in x]
    assert [(x["team"], x["text"]) for x in nyito] == [
        ("away", f"Várható védekezés ({a}): {defense_system_text(v6)}")]
    assert c.get("/matches/nincs/live-vedekezes").status_code == 404

    alerts = c.get("/matches/gt7/live-elorejelzes").json()["alerts"]
    al = alerts[0]
    f6 = match_forecast(tort(range(6), "home"), tort(range(6), "away"))
    p6 = forecast_backtest(lista(range(6)))
    assert al["forecast"] == f6
    vart = "Előrejelzés a korábbi meccsekből: " + match_forecast_text(h, a, f6)
    if p6:
        vart += f" (a próba: {forecast_backtest_text(p6)})"
    assert al["text"] == vart
    # Utána a két csapat várható gólszerzői (a meccs nélkül).
    gsorok = [x for x in alerts[1:] if "golszerzok" in x]
    vart_g = [(side, f"Várható gólszerzők ({nev}): "
               + scorer_forecast_text(gsz(range(6), side)))
              for side, nev in (("home", h), ("away", a))
              if gsz(range(6), side)]
    assert [(x["team"], x["text"]) for x in gsorok] == vart_g
    assert c.get("/matches/nincs/live-elorejelzes").status_code == 404

    mc = c.get("/library/player-model-check").json()
    assert mc["elorejelzes"] == json.loads(json.dumps(proba))
    assert mc["elorejelzes_text"] == forecast_backtest_text(proba)
    assert mc["golszerzo_proba"] == gp
    assert mc["vedekezes_proba"] == vp
    from handball.pipeline.play_simulation import model_checks_overview
    assert mc["ai_osszkep"] == model_checks_overview(
        {k: v for k, v in mc.items() if k != "ai_osszkep"})
    # A meccs eleji második AI-sor: az előrejelző modellek próbái a csapat
    # többi (hat) meccsén — a motor ugyanazokból a mintákból.
    from handball.pipeline.play_simulation import (forecast_rows_summary,
                                                   forecast_trust_summary,
                                                   hot_hand_backtest,
                                                   in_play_backtest,
                                                   shooter_form_sample)
    hat = [{"match_id": meccsek[i].meta.match_id, "home": h, "away": a,
            "minta": jm[i]} for i in range(6)]
    from handball.pipeline.primitive_cache import primitive_cache
    from handball.pipeline.setplays import (figure_recurrence_backtest,
                                            setplay_shapes)

    def alak(m):
        with primitive_cache(m):
            return json.loads(json.dumps(setplay_shapes(m)))
    fig = [{"match_id": m.meta.match_id, "home": h, "away": a,
            "alakok": alak(m)} for m in meccsek]
    assert mc["figura_proba"] == figure_recurrence_backtest(fig)
    # Hat rövid meccsen a fal-becslés próbája három jósolt meccstől ítél —
    # így a sor biztosan megszólal (a motor és a végpont ugyanazt látja).
    import handball.pipeline.play_simulation as ps_
    monkeypatch.setattr(ps_, "VR_PROBA_MIN", 3)
    assert defense_system_backtest(hat, a) is not None
    for side, nev in (("home", h), ("away", a)):
        sor2 = forecast_trust_summary(
            elore=forecast_rows_summary(p6["sorok"], nev) if p6 else None,
            golszerzo=scorer_forecast_backtest(hat, nev),
            elo=in_play_backtest(lista(range(6)), nev),
            vedekezes=defense_system_backtest(hat, nev),
            forma=hot_hand_backtest(
                [json.loads(json.dumps(shooter_form_sample(m, Team(s_))))
                 for m in meccsek[:6] for s_, n_ in (("home", h), ("away", a))
                 if n_ == nev]),
            figura=figure_recurrence_backtest(fig[:6], nev))
        kap = [x for x in c.get("/matches/gt7/live-modell-proba").json()[
            "alerts"] if x["team"] == side and x["fajta"] == "elorejelzesek"]
        if sor2 is None:
            assert kap == []
        else:
            assert [x["text"] for x in kap] == [
                f"AI-előrejelzések ({nev}, 6 korábbi meccs): {sor2}"]

    # Az élő esély próbája: a két perces felvételen fél percenként.
    import handball.pipeline.play_simulation as ps
    from handball.pipeline.play_simulation import in_play_backtest
    monkeypatch.setattr(ps, "LIVE_AJANLO_PERCEK", (0.5, 1.0, 1.5))
    ip = in_play_backtest(lista(range(7)))
    assert ip is not None and ip["pontok"] == 15
    assert c.get("/library/player-model-check").json()[
        "elo_esely_proba"] == ip


def test_a_nyomtathato_meccsterv_az_elorejelzessel(tmp_path, monkeypatch):
    """POST /scouting/export az "own" kulccsal: a meccsterv mellé az
    "Előrejelzés" szakasz — a két csapat (az items oldalainak neve)
    könyvtári meccseiből a várakozás és a két csapat várható gólszerzői,
    a valódi láncon ugyanaz, mint a motor a mintákból; "own" nélkül nincs
    szakasz. Az egymás-elleni riport ugyanezt hozza a csapatnevekkel."""
    import json
    from html import escape

    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import (match_forecast,
                                                   match_forecast_sample,
                                                   match_forecast_text,
                                                   player_model_sample,
                                                   scorer_forecast,
                                                   scorer_forecast_text)
    from handball.sim.match_simulator import simulate_ground_truth

    app = _app(tmp_path, monkeypatch)
    meccsek = []
    for seed in (1, 2, 3):
        m = simulate_ground_truth(duration_s=120, fps=25.0, seed=seed,
                                  shots_per_min=8)
        m.meta.match_id = f"gt{seed}"
        m.meta.date = f"2026-10-0{seed}"
        meccsek.append(m)
        app.state.put_match(m)
    h, a = meccsek[0].meta.home_team, meccsek[0].meta.away_team
    mintak = [json.loads(json.dumps(match_forecast_sample(m)))
              for m in meccsek]
    f = match_forecast([(x["home"], x["away"]) for x in mintak],
                       [(x["away"], x["home"]) for x in mintak])
    jm = [{side: json.loads(json.dumps(player_model_sample(m, t)))
           for side, t in (("home", Team.HOME), ("away", Team.AWAY))}
          for m in meccsek]
    ok = scorer_forecast([x["away"]["lovo"] for x in jm],
                         [x["home"]["kapus"] for x in jm])
    mi = scorer_forecast([x["home"]["lovo"] for x in jm],
                         [x["away"]["kapus"] for x in jm])
    c = TestClient(app)
    items = [{"match_id": m.meta.match_id, "team": "away"} for m in meccsek]
    own = [{"match_id": m.meta.match_id, "team": "home"} for m in meccsek]
    r = c.post("/scouting/export", json={"items": items,
                                         "own": {"items": own}})
    assert r.status_code == 200
    assert "Előrejelzés (a csapat-modellekből)" in r.text
    assert f is not None
    assert f"<p><b>{escape(match_forecast_text(h, a, f))}</b></p>" in r.text
    if ok:
        assert (f"<li>Az ő várható gólszerzőik: "
                f"{escape(scorer_forecast_text(ok))}.</li>") in r.text
    assert mi, "a hazai lövői tanulhatók"
    assert (f"<li>A mi várható gólszerzőink: "
            f"{escape(scorer_forecast_text(mi))}.</li>") in r.text
    # A döntés-próbák a könyvtárból, a motorral egyezően: a kapus-választás
    # próbája és a hetes-dobónk sora csak akkor, ha a motor is ítél (a
    # három szimulált meccsen nem); a felderítés próbájához kevés a meccs.
    from handball.pipeline.play_simulation import (keeper_choice_backtest,
                                                   seven_taker_choice,
                                                   seven_taker_sample)
    kvp = keeper_choice_backtest(
        [{"match_id": m.meta.match_id, "home": m.meta.home_team,
          "away": m.meta.away_team, "minta": x} for m, x in zip(meccsek, jm)])
    assert ("A kapus-választás próbája" in r.text) == bool(kvp)
    hj = seven_taker_choice([json.loads(json.dumps(
        seven_taker_sample(m, Team.HOME))) for m in meccsek])
    assert ("Hetes-dobónk" in r.text) == bool(hj)
    assert "A felderítés próbája" not in r.text
    from handball.pipeline.play_simulation import (defense_system_forecast,
                                                   defense_system_text)
    vo = defense_system_forecast([x["away"]["formak"] for x in jm])
    assert vo is not None
    assert (f"<li>Várható védekezésük: "
            f"{escape(defense_system_text(vo))}.</li>") in r.text
    from handball.pipeline.play_simulation import key_player_text
    kmi = key_player_text(mi)
    if kmi:
        assert (f"<li>Kulcsemberünk — juttassátok lövéshez: "
                f"{escape(kmi)}.</li>") in r.text
    else:
        assert "Kulcsemberünk" not in r.text
    # Az AI-edzésterv a meccsre: az első tétel a támadás az ő faluk ellen.
    from handball.pipeline.play_simulation import _rendszer_nevelovel
    assert "Edzésterv a meccsre (az AI javaslata)" in r.text
    assert (f"<li><b>Támadás {escape(_rendszer_nevelovel(vo['fo']))} fal "
            "ellen</b>") in r.text
    r2 = c.post("/scouting/export", json={"items": items})
    assert "Előrejelzés (a csapat-modellekből)" not in r2.text
    assert "Edzésterv a meccsre" not in r2.text
    # Az egymás-elleni riport is hozza, a csapatnevekkel címkézve.
    hr = c.get("/head-to-head/report", params={"team_a": h, "team_b": a})
    assert hr.status_code == 200
    assert "Előrejelzés a következő meccsre" in hr.text
    assert f"<p><b>{escape(match_forecast_text(h, a, f))}</b></p>" in hr.text
    assert (f"<li>{escape(h)} várható gólszerzői: "
            f"{escape(scorer_forecast_text(mi))}.</li>") in hr.text
    assert (f"<li>{escape(a)} várható védekezése: "
            f"{escape(defense_system_text(vo))}.</li>") in hr.text


def test_az_elo_napi_forma_vegpont_a_valodi_lancon(tmp_path, monkeypatch):
    """GET /matches/{id}/live-forma: a lövők a csapat, a kapus az
    ellenfél könyvtári TÖBBI meccséből (player_models_from_samples), a
    forró kéz próbája a többi meccs lövő-forma mintáiból — a valódi
    láncon ugyanaz, mint a motor; a /library/player-model-check
    "forma_proba" mezője a motor próbája; 404 ismeretlen meccsre."""
    import json

    import handball.pipeline.play_simulation as ps
    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import (hot_hand_backtest,
                                                   live_form_alerts,
                                                   player_model_sample,
                                                   player_models_from_samples,
                                                   shooter_form_sample)
    from handball.sim.match_simulator import simulate_ground_truth

    monkeypatch.setattr(ps, "LIVE_AJANLO_PERCEK", (2, 4))
    app = _app(tmp_path, monkeypatch)
    meccsek = []
    for seed in (1, 2, 3):
        m = simulate_ground_truth(duration_s=300, fps=25.0, seed=seed,
                                  shots_per_min=8)
        m.meta.match_id = f"gt{seed}"
        m.meta.date = f"2026-10-0{seed}"
        meccsek.append(m)
        app.state.put_match(m)
    tobbi = meccsek[:2]

    def modell(side):
        return player_models_from_samples(
            [json.loads(json.dumps(player_model_sample(m, Team(side))))
             for m in tobbi])

    proba = hot_hand_backtest(
        [json.loads(json.dumps(shooter_form_sample(m, Team(side))))
         for m in tobbi for side in ("home", "away")])
    vart = live_form_alerts(
        meccsek[2], tamadas={s_: modell(s_)["tamadas"] for s_ in ("home", "away")},
        kapus={s_: modell(s_)["kapus"] for s_ in ("home", "away")},
        proba=proba)["alerts"]
    c = TestClient(app)
    j = c.get("/matches/gt3/live-forma").json()
    assert vart and [a["text"] for a in j["alerts"]] == [a["text"] for a in vart]
    assert j["proba"] == proba
    assert c.get("/matches/nincs/live-forma").status_code == 404
    mc = c.get("/library/player-model-check").json()
    assert mc["forma_proba"] == hot_hand_backtest(
        [json.loads(json.dumps(shooter_form_sample(m, Team(side))))
         for m in meccsek for side in ("home", "away")])


def test_varakozas_es_valosag_vegpont_es_jelentes(tmp_path, monkeypatch):
    """GET /matches/{id}/forecast-review: a várakozás CSAK a meccs előtti
    meccsekből (időrendben) — a valódi láncon ugyanaz, mint a motor a
    mintákból; az első meccsnél nincs várakozás; a meccs-jelentés
    "Várakozás és valóság" szakasza a mondatokkal; 404 ismeretlen
    meccsre."""
    import json
    from html import escape

    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import (defense_system_forecast,
                                                   forecast_review,
                                                   match_forecast,
                                                   match_forecast_sample,
                                                   player_model_sample,
                                                   scorer_forecast)
    from handball.sim.match_simulator import simulate_ground_truth

    app = _app(tmp_path, monkeypatch)
    meccsek = []
    for seed in (3, 1, 2):          # a beolvasás sorrendje ne számítson
        m = simulate_ground_truth(duration_s=120, fps=25.0, seed=seed,
                                  shots_per_min=8)
        m.meta.match_id = f"gt{seed}"
        m.meta.date = f"2026-10-0{seed}"
        meccsek.append(m)
        app.state.put_match(m)
    meccsek.sort(key=lambda m: m.meta.date)
    h, a = meccsek[0].meta.home_team, meccsek[0].meta.away_team
    fm = [json.loads(json.dumps(match_forecast_sample(m))) for m in meccsek]
    jm = [{side: json.loads(json.dumps(player_model_sample(m, Team(side))))
           for side in ("home", "away")} for m in meccsek]
    f = match_forecast([(x["home"], x["away"]) for x in fm[:2]],
                       [(x["away"], x["home"]) for x in fm[:2]])
    vart = forecast_review(
        {"home": h, "away": a}, f,
        {"home": fm[2]["home"]["golok"], "away": fm[2]["away"]["golok"]},
        golszerzok={"home": scorer_forecast([x["home"]["lovo"] for x in jm[:2]],
                                            [x["away"]["kapus"] for x in jm[:2]]),
                    "away": scorer_forecast([x["away"]["lovo"] for x in jm[:2]],
                                            [x["home"]["kapus"] for x in jm[:2]])},
        lovo_valodi={s_: jm[2][s_]["lovo"] for s_ in ("home", "away")},
        vedekezes={s_: defense_system_forecast([x[s_]["formak"] for x in jm[:2]])
                   for s_ in ("home", "away")},
        formak_valodi={s_: jm[2][s_]["formak"] for s_ in ("home", "away")})
    c = TestClient(app)
    j = c.get("/matches/gt3/forecast-review").json()
    assert f is not None and vart["sorok"]
    assert j["sorok"] == vart["sorok"] and j["eredmeny"] == vart["eredmeny"]
    assert j["korabbi_meccsek"] == {"home": 2, "away": 2}
    elso = c.get("/matches/gt1/forecast-review").json()
    assert elso["eredmeny"] is None and elso["korabbi_meccsek"] == {
        "home": 0, "away": 0}
    assert c.get("/matches/nincs/forecast-review").status_code == 404
    r = c.get("/matches/gt3/report/export")
    assert r.status_code == 200
    assert "Várakozás és valóság" in r.text
    assert f"<li>{escape(vart['sorok'][0])}.</li>" in r.text


def test_az_ai_dontes_edzes_a_konyvtari_edzesfokuszban(tmp_path, monkeypatch):
    """GET /library/training-focus "ai_dontes": csapatonként a meccsek
    döntés-mintáinak összegéből (decisions.decision_outcome_sample) a
    training.proven_decision_drills tételei — a valódi láncon ugyanaz,
    mint a motor; a régi kulcsok változatlanok."""
    import json

    from handball.pipeline.decisions import (decision_outcome_sample,
                                             decision_samples_sum)
    from handball.pipeline.training import proven_decision_drills
    from handball.sim.match_simulator import simulate_ground_truth

    app = _app(tmp_path, monkeypatch)
    meccsek = []
    for seed in (1, 2):
        m = simulate_ground_truth(duration_s=180, fps=25.0, seed=seed,
                                  shots_per_min=8)
        m.meta.match_id = f"gt{seed}"
        m.meta.date = f"2026-10-0{seed}"
        meccsek.append(m)
        app.state.put_match(m)
    j = TestClient(app).get("/library/training-focus").json()
    assert set(j) == {"teams", "matches", "ai_dontes"}
    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import (player_model_sample,
                                                   player_models_from_samples)
    from handball.pipeline.training import season_shot_allocation_drill
    dm = [json.loads(json.dumps(decision_outcome_sample(m))) for m in meccsek]
    vart = {}
    for side, nev in (("home", meccsek[0].meta.home_team),
                      ("away", meccsek[0].meta.away_team)):
        d = proven_decision_drills(decision_samples_sum([x[side] for x in dm]))
        mod = player_models_from_samples(
            [json.loads(json.dumps(player_model_sample(m, Team(side))))
             for m in meccsek])
        le = season_shot_allocation_drill(mod["tamadas"], mod["lovo"],
                                          len(meccsek))
        if le:
            d = d + [le]
        if d:
            vart[nev] = d
    assert j["ai_dontes"] == vart


def test_a_meccs_elotti_kapus_valasztas_a_konyvtarbol(tmp_path, monkeypatch):
    """GET /library/forecast "kapus_javaslat": a csapat kapusai
    (kapusonként, az összes könyvtári meccséből) a másik csapat tanult
    lövői ellen — a valódi láncon ugyanaz, mint a keeper_choice_from a
    mintákból; egyetlen kapusnál None."""
    import json

    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import (keeper_choice_from,
                                                   player_model_sample,
                                                   player_models_from_samples)
    from handball.sim.match_simulator import simulate_ground_truth

    app = _app(tmp_path, monkeypatch)
    meccsek = []
    for seed in (1, 2, 3):
        m = simulate_ground_truth(duration_s=120, fps=25.0, seed=seed,
                                  shots_per_min=8)
        m.meta.match_id = f"gt{seed}"
        m.meta.date = f"2026-10-0{seed}"
        if seed > 1:
            # A vendég kapusa a 2. és a 3. meccsen más mezben: két kapus.
            for f in m.frames:
                for p in f.players:
                    if p.team == Team.AWAY and p.role == "kapus":
                        p.jersey_number = 12
        meccsek.append(m)
        app.state.put_match(m)
    h, a = meccsek[0].meta.home_team, meccsek[0].meta.away_team
    jm = [{side: json.loads(json.dumps(player_model_sample(m, Team(side))))
           for side in ("home", "away")} for m in meccsek]
    vart = keeper_choice_from(
        player_models_from_samples([x["home"] for x in jm])["lovo"],
        player_models_from_samples([x["away"] for x in jm])["kapusok"])
    assert vart is not None and {vart["kapus_mez"], vart["masik_mez"]} == {1, 12}
    j = TestClient(app).get("/library/forecast",
                            params={"home": h, "away": a}).json()
    assert j["kapus_javaslat"]["away"] == vart
    assert j["kapus_javaslat"]["home"] is None     # a hazainak egy kapusa van
    # A kapus-választás próbája a könyvtár időrendjében — a valódi láncon
    # ugyanaz, mint a motor a mintákból (a /library/forecast és a
    # /library/player-model-check mezője).
    from handball.pipeline.play_simulation import keeper_choice_backtest
    kvp = keeper_choice_backtest(
        [{"match_id": m.meta.match_id, "home": m.meta.home_team,
          "away": m.meta.away_team, "minta": x} for m, x in zip(meccsek, jm)])
    assert j["kapus_valasztas_proba"] == kvp
    assert TestClient(app).get("/library/player-model-check").json()[
        "kapus_valasztas_proba"] == kvp
    # A felderítés próbája a valódi láncon: a meccsenkénti felderítő
    # jelentésekből (scout_team) ugyanaz, mint a motor — a küszöbök a
    # három meccshez igazítva (mindkét modulban ugyanaz a név).
    import handball.pipeline.scouting as sc
    from handball.pipeline.scouting import scouting_backtest, scout_team
    monkeypatch.setattr(sc, "SC_PROBA_MIN", 1)
    monkeypatch.setattr(sc, "SC_MIN_KORABBI", 1)
    # A könyvtár MINDEN meccse időrendben — az _app segéd "fm" meccse (A–B)
    # is: a liga általános kulcsaiba az ő jelentései is beleszámítanak.
    tar = app.state.store
    fdp = scouting_backtest(
        [{"match_id": m.meta.match_id, "home": m.meta.home_team,
          "away": m.meta.away_team,
          "reports": {s_: scout_team(m, Team(s_)) for s_ in ("home", "away")}}
         for m in (tar.get(i) for i in ("fm", "gt1", "gt2", "gt3"))])
    assert fdp is not None and fdp["meccsek"] == 4
    assert TestClient(app).get("/library/player-model-check").json()[
        "felderites_proba"] == fdp
    assert TestClient(app).get("/library/forecast", params={
        "home": h, "away": a}).json()["felderites_proba"] == fdp


def test_az_elo_felidei_varakozas_vegpont(tmp_path, monkeypatch):
    """GET /matches/{id}/live-felido: a meccs előtti várakozás a két
    csapat TÖBBI meccséből, a félidőig látottakhoz mérve — a valódi
    láncon ugyanaz, mint a motor; várakozás nélkül üres; 404."""
    import json

    import handball.pipeline.play_simulation as ps
    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import (defense_system_forecast,
                                                   halftime_review,
                                                   match_forecast,
                                                   match_forecast_sample,
                                                   player_model_sample,
                                                   scorer_forecast)
    from handball.sim.match_simulator import simulate_ground_truth

    monkeypatch.setattr(ps, "FELIDO_PERC", 1)
    app = _app(tmp_path, monkeypatch)
    meccsek = []
    for seed in (1, 2, 3):
        m = simulate_ground_truth(duration_s=120, fps=25.0, seed=seed,
                                  shots_per_min=8)
        m.meta.match_id = f"gt{seed}"
        m.meta.date = f"2026-10-0{seed}"
        meccsek.append(m)
        app.state.put_match(m)
        if seed == 1:
            assert TestClient(app).get(
                "/matches/gt1/live-felido").json()["alerts"] == []
    h, a = meccsek[0].meta.home_team, meccsek[0].meta.away_team
    tobbi = meccsek[:2]
    fm = [json.loads(json.dumps(match_forecast_sample(m))) for m in tobbi]
    jm = [{s_: json.loads(json.dumps(player_model_sample(m, Team(s_))))
           for s_ in ("home", "away")} for m in tobbi]
    f = match_forecast([(x["home"], x["away"]) for x in fm],
                       [(x["away"], x["home"]) for x in fm])
    vart = halftime_review(
        meccsek[2], {"home": h, "away": a}, f,
        golszerzok={s_: scorer_forecast([x[s_]["lovo"] for x in jm],
                                        [x[o_]["kapus"] for x in jm])
                    for s_, o_ in (("home", "away"), ("away", "home"))},
        vedekezes={s_: defense_system_forecast([x[s_]["formak"] for x in jm])
                   for s_ in ("home", "away")})
    assert vart["sorok"]
    [al] = TestClient(app).get("/matches/gt3/live-felido").json()["alerts"]
    assert al["sorok"] == vart["sorok"] and al["t"] == vart["t"]
    assert al["text"] == "Félidő — " + "; ".join(vart["sorok"])
    assert TestClient(app).get("/matches/nincs/live-felido").status_code == 404


def test_az_elo_idokeres_jegyzet_vegpont(tmp_path, monkeypatch):
    """GET /matches/{id}/live-idokeres-jegyzet: a `perc` kérésre a
    várakozás a két csapat TÖBBI meccséből, az időkérés próbája a többi
    meccs mintáiból — a valódi láncon ugyanaz, mint a motor; kérés
    nélkül a felismert időkérések (a szimulált meccsen nincs); 422, 404."""
    import json

    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import (defense_system_forecast,
                                                   live_timeout_briefs,
                                                   match_forecast,
                                                   match_forecast_sample,
                                                   player_model_sample,
                                                   run_timeout_sample,
                                                   scorer_forecast,
                                                   timeout_brief,
                                                   timeout_brief_text,
                                                   timeout_run_backtest)
    from handball.sim.match_simulator import simulate_ground_truth

    app = _app(tmp_path, monkeypatch)
    meccsek = []
    for seed in (1, 2, 3):
        m = simulate_ground_truth(duration_s=180, fps=25.0, seed=seed,
                                  shots_per_min=8)
        m.meta.match_id = f"gt{seed}"
        m.meta.date = f"2026-10-0{seed}"
        meccsek.append(m)
        app.state.put_match(m)
    h, a = meccsek[0].meta.home_team, meccsek[0].meta.away_team
    nevek = {"home": h, "away": a}
    tobbi = meccsek[:2]
    fm = [json.loads(json.dumps(match_forecast_sample(m))) for m in tobbi]
    jm = [{s_: json.loads(json.dumps(player_model_sample(m, Team(s_))))
           for s_ in ("home", "away")} for m in tobbi]
    f = match_forecast([(x["home"], x["away"]) for x in fm],
                       [(x["away"], x["home"]) for x in fm])
    gsz = {s_: scorer_forecast([x[s_]["lovo"] for x in jm],
                               [x[o_]["kapus"] for x in jm])
           for s_, o_ in (("home", "away"), ("away", "home"))}
    ved = {s_: defense_system_forecast([x[s_]["formak"] for x in jm])
           for s_ in ("home", "away")}
    proba = timeout_run_backtest(
        [{"home": m.meta.home_team, "away": m.meta.away_team,
          "minta": json.loads(json.dumps(run_timeout_sample(m)))}
         for m in tobbi])
    vart = timeout_brief(meccsek[2], 1.5, nevek, f, golszerzok=gsz,
                         vedekezes=ved, kero="away", idokeres_proba=proba)
    assert len(vart["sorok"]) >= 3
    c = TestClient(app)
    [j] = c.get("/matches/gt3/live-idokeres-jegyzet",
                params={"perc": 1.5, "kero": "away"}).json()["jegyzetek"]
    assert j["sorok"] == vart["sorok"] and j["t"] == vart["t"]
    assert j["text"] == timeout_brief_text(vart, nevek)
    assert c.get("/matches/gt3/live-idokeres-jegyzet").json() == \
        live_timeout_briefs(meccsek[2], nevek, f, golszerzok=gsz,
                            vedekezes=ved, idokeres_proba=proba)
    assert c.get("/matches/gt3/live-idokeres-jegyzet",
                 params={"perc": 99}).json() == {"jegyzetek": []}
    assert c.get("/matches/gt3/live-idokeres-jegyzet",
                 params={"kero": "x"}).status_code == 422
    assert c.get("/matches/gt3/live-idokeres-jegyzet",
                 params={"perc": -1}).status_code == 422
    assert c.get("/matches/nincs/live-idokeres-jegyzet").status_code == 404


def test_az_ai_edzesterv_vegpont_a_valodi_lancon(tmp_path, monkeypatch):
    """GET /library/next-match-plan: a mi csapatunk (itt a vendég, két
    kapussal) az ellenfél ellen — a valódi láncon a tételek a motor
    képéből: a támadás az ő várható faluk ellen (ha van), a kapus (ha a
    választás érdemi); minden tétel cím, terület, indok, gyakorlat; 400
    hiányzó névre, 404 ismeretlen csapatra."""
    import json

    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import (_rendszer_nevelovel,
                                                   defense_system_forecast,
                                                   keeper_choice_from,
                                                   player_model_sample,
                                                   player_models_from_samples)
    from handball.sim.match_simulator import simulate_ground_truth

    app = _app(tmp_path, monkeypatch)
    meccsek = []
    for seed in (1, 2, 3):
        m = simulate_ground_truth(duration_s=120, fps=25.0, seed=seed,
                                  shots_per_min=8)
        m.meta.match_id = f"gt{seed}"
        m.meta.date = f"2026-10-0{seed}"
        if seed > 1:
            for f in m.frames:
                for p in f.players:
                    if p.team == Team.AWAY and p.role == "kapus":
                        p.jersey_number = 12
        meccsek.append(m)
        app.state.put_match(m)
    h, a = meccsek[0].meta.home_team, meccsek[0].meta.away_team
    jm = [{s_: json.loads(json.dumps(player_model_sample(m, Team(s_))))
           for s_ in ("home", "away")} for m in meccsek]
    c = TestClient(app)
    j = c.get("/library/next-match-plan", params={"home": a, "away": h}).json()
    assert (j["home"], j["away"]) == (a, h)
    cimek = [t["title"] for t in j["items"]]
    assert all(set(t) == {"title", "area", "why", "drill"} for t in j["items"])
    ved = defense_system_forecast([x["home"]["formak"] for x in jm])
    if ved:
        assert cimek[0] == f"Támadás {_rendszer_nevelovel(ved['fo'])} fal ellen"
    else:
        assert not any(c_.startswith("Támadás") for c_ in cimek)
    kv = keeper_choice_from(
        player_models_from_samples([x["home"] for x in jm])["lovo"],
        player_models_from_samples([x["away"] for x in jm])["kapusok"])
    assert any(c_.startswith("Kapus:") for c_ in cimek) == bool(
        kv and kv["dontes"])
    assert c.get("/library/next-match-plan",
                 params={"home": a}).status_code == 400
    assert c.get("/library/next-match-plan",
                 params={"home": a, "away": "Nincs"}).status_code == 404


def test_az_elo_kapus_forma_vegpont(tmp_path, monkeypatch):
    """GET /matches/{id}/live-kapus-forma: a kapusok szokásos szintje a
    csapat TÖBBI meccséből, a próba a többi meccs kapus-forma mintáiból —
    a valódi láncon ugyanaz, mint a motor; a /library/player-model-check
    "kapus_forma_proba" mezője; 404."""
    import json

    import handball.pipeline.play_simulation as ps
    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import (_kapus_szorzo,
                                                   keeper_form_sample,
                                                   keeper_hot_hand_backtest,
                                                   live_keeper_form_alerts,
                                                   player_model_sample,
                                                   player_models_from_samples)
    from handball.sim.match_simulator import simulate_ground_truth

    monkeypatch.setattr(ps, "LIVE_AJANLO_PERCEK", (2, 4))
    app = _app(tmp_path, monkeypatch)
    meccsek = []
    for seed in (1, 2, 3):
        m = simulate_ground_truth(duration_s=300, fps=25.0, seed=seed,
                                  shots_per_min=8)
        m.meta.match_id = f"gt{seed}"
        m.meta.date = f"2026-10-0{seed}"
        meccsek.append(m)
        app.state.put_match(m)
    tobbi = meccsek[:2]
    szorzok = {}
    for s_ in ("home", "away"):
        mod = player_models_from_samples(
            [json.loads(json.dumps(player_model_sample(m, Team(s_))))
             for m in tobbi])
        szorzok[s_] = {int(k): _kapus_szorzo(v)
                       for k, v in (mod.get("kapusok") or {}).items()}
    proba = keeper_hot_hand_backtest(
        [json.loads(json.dumps(keeper_form_sample(m, Team(s_))))
         for m in tobbi for s_ in ("home", "away")])
    vart = live_keeper_form_alerts(meccsek[2], kapus_szorzok=szorzok,
                                   proba=proba)["alerts"]
    c = TestClient(app)
    j = c.get("/matches/gt3/live-kapus-forma").json()
    assert vart and [a["text"] for a in j["alerts"]] == [a["text"] for a in vart]
    assert j["proba"] == proba
    assert c.get("/matches/nincs/live-kapus-forma").status_code == 404
    assert c.get("/library/player-model-check").json()[
        "kapus_forma_proba"] == keeper_hot_hand_backtest(
            [json.loads(json.dumps(keeper_form_sample(m, Team(s_))))
             for m in meccsek for s_ in ("home", "away")])


def test_az_elo_idokeres_vegpont(tmp_path, monkeypatch):
    """GET /matches/{id}/live-idokeres: a próba a TÖBBI meccs időkérés-
    mintáiból — a valódi láncon ugyanaz, mint a motor; a /library/
    player-model-check "idokeres_proba" mezője a könyvtár mintáiból; 404."""
    import json

    from handball.pipeline.play_simulation import (live_timeout_alerts,
                                                   run_timeout_sample,
                                                   timeout_run_backtest)
    from handball.sim.match_simulator import simulate_ground_truth

    app = _app(tmp_path, monkeypatch)
    meccsek = []
    for seed in (1, 2, 3):
        m = simulate_ground_truth(duration_s=300, fps=25.0, seed=seed,
                                  shots_per_min=8)
        m.meta.match_id = f"gt{seed}"
        m.meta.date = f"2026-10-0{seed}"
        meccsek.append(m)
        app.state.put_match(m)

    def lista(ms):
        return [{"match_id": m.meta.match_id, "home": m.meta.home_team,
                 "away": m.meta.away_team,
                 "minta": json.loads(json.dumps(run_timeout_sample(m)))}
                for m in ms]

    proba = timeout_run_backtest(lista(meccsek[:2]))
    vart = live_timeout_alerts(meccsek[2], proba=proba)["alerts"]
    c = TestClient(app)
    j = c.get("/matches/gt3/live-idokeres").json()
    assert vart and [a["text"] for a in j["alerts"]] == [a["text"] for a in vart]
    assert j["proba"] == proba
    assert c.get("/matches/nincs/live-idokeres").status_code == 404
    assert c.get("/library/player-model-check").json()[
        "idokeres_proba"] == timeout_run_backtest(lista(meccsek))


def test_az_elo_hetes_dobo_vegpont(tmp_path, monkeypatch):
    """GET /matches/{id}/live-hetes: a javaslat a csapat TÖBBI meccséből, a
    próba a többi meccs mintáiból — a valódi láncon ugyanaz, mint a motor
    (a szimulált hetesnek nincs azonosított dobója: üres minta, None
    javaslat); a /library/player-model-check "hetes_proba" és a
    /library/forecast "hetes_dobo" mezője; 404."""
    import json

    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import (live_seven_taker_alerts,
                                                   seven_taker_backtest,
                                                   seven_taker_choice,
                                                   seven_taker_sample)
    from handball.sim.match_simulator import simulate_ground_truth

    app = _app(tmp_path, monkeypatch)
    meccsek = []
    for seed in (1, 2, 3):
        m = simulate_ground_truth(duration_s=120, fps=25.0, seed=seed,
                                  shots_per_min=8)
        m.meta.match_id = f"gt{seed}"
        m.meta.date = f"2026-10-0{seed}"
        meccsek.append(m)
        app.state.put_match(m)
    h, a = meccsek[0].meta.home_team, meccsek[0].meta.away_team

    def lista(ms):
        return [{"match_id": m.meta.match_id, "home": m.meta.home_team,
                 "away": m.meta.away_team,
                 "minta": {s_: json.loads(json.dumps(
                     seven_taker_sample(m, Team(s_))))
                           for s_ in ("home", "away")}} for m in ms]

    from handball.pipeline.play_simulation import (
        live_seven_direction_alerts, seven_direction_backtest,
        seven_direction_profile, seven_direction_sample)

    def lista_ir(ms):
        return [{"match_id": m.meta.match_id, "home": m.meta.home_team,
                 "away": m.meta.away_team,
                 "minta": {s_: json.loads(json.dumps(
                     seven_direction_sample(m, Team(s_))))
                           for s_ in ("home", "away")}} for m in ms]

    tobbi, tobbi_ir = lista(meccsek[:2]), lista_ir(meccsek[:2])
    jav = {s_: seven_taker_choice([x["minta"][s_] for x in tobbi])
           for s_ in ("home", "away")}
    ir = {s_: seven_direction_profile([x["minta"][s_] for x in tobbi_ir])
          for s_ in ("home", "away")}
    c = TestClient(app)
    j = c.get("/matches/gt3/live-hetes").json()
    assert j["javaslat"] == jav and j["iranyok"] == ir
    assert j["alerts"] == sorted(
        live_seven_taker_alerts(meccsek[2], jav)["alerts"]
        + live_seven_direction_alerts(meccsek[2], ir)["alerts"],
        key=lambda x: (x["t"], x["team"]))
    assert j["proba"] == seven_taker_backtest(tobbi)
    assert j["irany_proba"] == seven_direction_backtest(tobbi_ir)
    assert c.get("/matches/nincs/live-hetes").status_code == 404
    mind, mind_ir = lista(meccsek), lista_ir(meccsek)
    mc = c.get("/library/player-model-check").json()
    assert mc["hetes_proba"] == seven_taker_backtest(mind)
    assert mc["hetes_irany_proba"] == seven_direction_backtest(mind_ir)
    f = c.get("/library/forecast", params={"home": h, "away": a}).json()
    assert f["hetes_dobo"] == {
        s_: seven_taker_choice([x["minta"][s_] for x in mind])
        for s_ in ("home", "away")}
    assert f["hetes_proba"] == seven_taker_backtest(mind)
    assert f["hetes_irany"] == {
        s_: seven_direction_profile([x["minta"][s_] for x in mind_ir])
        for s_ in ("home", "away")}
    assert f["hetes_irany_proba"] == seven_direction_backtest(mind_ir)


def test_a_pad_dontesei_vegpont(tmp_path, monkeypatch):
    """GET /matches/{id}/decision-review: a meccs mintái a könyvtár TÖBBI
    meccséből vett próbákhoz és javaslatokhoz mérve — a valódi láncon
    ugyanaz, mint a motor; a csapatnevek; 404."""
    import json

    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import (
        _kapus_mintak_osszege, _lovo_mintak_osszege, decision_review,
        keeper_choice_from, keeper_form_sample, keeper_hot_hand_backtest,
        player_model_sample, run_timeout_sample, seven_six_backtest,
        seven_six_sample, seven_taker_choice, seven_taker_sample,
        super_sub_backtest, super_sub_choice, super_sub_sample,
        timeout_run_backtest)
    from handball.sim.match_simulator import simulate_ground_truth

    app = _app(tmp_path, monkeypatch)
    meccsek = []
    for seed in (1, 2, 3):
        m = simulate_ground_truth(duration_s=300, fps=25.0, seed=seed,
                                  shots_per_min=8)
        m.meta.match_id = f"gt{seed}"
        m.meta.date = f"2026-10-0{seed}"
        meccsek.append(m)
        app.state.put_match(m)
    m3 = meccsek[2]
    nevek = {"home": m3.meta.home_team, "away": m3.meta.away_team}
    tobbi = meccsek[:2]
    jj = lambda x: json.loads(json.dumps(x))
    jm = {s_: [jj(player_model_sample(m, Team(s_))) for m in tobbi]
          for s_ in ("home", "away")}
    vart = decision_review(
        nevek, jj(run_timeout_sample(m3)),
        {s_: jj(seven_taker_sample(m3, Team(s_))) for s_ in ("home", "away")},
        {s_: jj(keeper_form_sample(m3, Team(s_))) for s_ in ("home", "away")},
        idokeres_proba={s_: timeout_run_backtest(
            [{"match_id": m.meta.match_id, "home": m.meta.home_team,
              "away": m.meta.away_team, "minta": jj(run_timeout_sample(m))}
             for m in tobbi], nevek[s_]) for s_ in ("home", "away")},
        hetes_javaslat={s_: seven_taker_choice(
            [jj(seven_taker_sample(m, Team(s_))) for m in tobbi])
            for s_ in ("home", "away")},
        kapus_javaslat={s_: keeper_choice_from(
            _lovo_mintak_osszege([x["lovo"] for x in jm[o_]]),
            _kapus_mintak_osszege([x["kapusok"] for x in jm[s_]]))
            for s_, o_ in (("home", "away"), ("away", "home"))},
        kapusforma_proba={s_: keeper_hot_hand_backtest(
            [jj(keeper_form_sample(m, Team(s_))) for m in tobbi])
            for s_ in ("home", "away")},
        het_a_hat_mintak={s_: jj(seven_six_sample(m3, Team(s_)))
                          for s_ in ("home", "away")},
        het_a_hat_proba={s_: seven_six_backtest(
            [{"match_id": m.meta.match_id, "home": m.meta.home_team,
              "away": m.meta.away_team,
              "minta": {t_: jj(seven_six_sample(m, Team(t_)))
                        for t_ in ("home", "away")}} for m in tobbi], nevek[s_])
            for s_ in ("home", "away")},
        szuper_csere_mintak={s_: jj(super_sub_sample(m3, Team(s_)))
                             for s_ in ("home", "away")},
        szuper_csere_javaslat={s_: super_sub_choice(
            [jj(super_sub_sample(m, Team(s_))) for m in tobbi])
            for s_ in ("home", "away")},
        szuper_csere_proba={s_: super_sub_backtest(
            [{"match_id": m.meta.match_id, "home": m.meta.home_team,
              "away": m.meta.away_team,
              "minta": {t_: jj(super_sub_sample(m, Team(t_)))
                        for t_ in ("home", "away")}} for m in tobbi], nevek[s_])
            for s_ in ("home", "away")})
    assert vart["home"]["sorok"] or vart["away"]["sorok"]
    c = TestClient(app)
    j = c.get("/matches/gt3/decision-review").json()
    assert j["nevek"] == nevek
    for s_ in ("home", "away"):
        assert j[s_] == vart[s_]
    assert c.get("/matches/nincs/decision-review").status_code == 404


def test_az_elo_7_a_6_vegpont(tmp_path, monkeypatch):
    """GET /matches/{id}/live-7a6: a mérleg a TÖBBI meccs mintáiból — a
    valódi láncon ugyanaz, mint a motor (a szimulált meccseken nincs 7 a
    6: a mérleg None, a jelzés ítélet nélkül szól); a /library/
    player-model-check "het_a_hat_proba" mezője; 404."""
    import json

    import handball.pipeline.play_simulation as ps
    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import (live_seven_six_alerts,
                                                   seven_six_backtest,
                                                   seven_six_sample)
    from handball.sim.match_simulator import simulate_ground_truth

    monkeypatch.setattr(ps, "HN_ELO_PERCEK", (1, 2))
    monkeypatch.setattr(ps, "HN_HATRANY_MAX", 1000)
    app = _app(tmp_path, monkeypatch)
    meccsek = []
    for seed in (1, 2, 3):
        m = simulate_ground_truth(duration_s=180, fps=25.0, seed=seed,
                                  shots_per_min=8)
        m.meta.match_id = f"gt{seed}"
        m.meta.date = f"2026-10-0{seed}"
        meccsek.append(m)
        app.state.put_match(m)

    def lista(ms):
        return [{"match_id": m.meta.match_id, "home": m.meta.home_team,
                 "away": m.meta.away_team,
                 "minta": {s_: json.loads(json.dumps(
                     seven_six_sample(m, Team(s_)))) for s_ in ("home", "away")}}
                for m in ms]

    proba = seven_six_backtest(lista(meccsek[:2]))
    vart = live_seven_six_alerts(meccsek[2], proba)["alerts"]
    c = TestClient(app)
    j = c.get("/matches/gt3/live-7a6").json()
    assert vart and [a["text"] for a in j["alerts"]] == [a["text"] for a in vart]
    assert j["proba"] == proba
    assert c.get("/matches/nincs/live-7a6").status_code == 404
    assert c.get("/library/player-model-check").json()["het_a_hat_proba"] == \
        seven_six_backtest(lista(meccsek))
    # A /library/forecast csapatonként a saját 7 a 6 mérleget adja (a
    # szimulált meccseken nincs 7 a 6: None).
    h, a = meccsek[0].meta.home_team, meccsek[0].meta.away_team
    f = c.get("/library/forecast", params={"home": h, "away": a}).json()
    assert f["het_a_hat_proba"] == {
        "home": seven_six_backtest(lista(meccsek), h),
        "away": seven_six_backtest(lista(meccsek), a)}


def test_az_elo_ai_dontesek_sora(tmp_path, monkeypatch):
    """GET /matches/{id}/live-modell-proba "dontesek" sora: a pad
    döntés-próbái a csapat SAJÁT döntésein, a meccs nélkül — a próbák a
    csapat nevével és a meccs kihagyásával hívódnak (itt beadott
    ítéletekkel: a szimulált meccseken egyik sem ítél); ítélet nélkül
    nincs sor."""
    import handball.pipeline.play_simulation as ps
    from handball.sim.match_simulator import simulate_ground_truth

    app = _app(tmp_path, monkeypatch)
    for seed in (1, 2, 3):
        m = simulate_ground_truth(duration_s=180, fps=25.0, seed=seed,
                                  shots_per_min=8)
        m.meta.match_id = f"gt{seed}"
        m.meta.date = f"2026-10-0{seed}"
        app.state.put_match(m)
    h = m.meta.home_team
    c = TestClient(app)
    assert not [a for a in c.get("/matches/gt3/live-modell-proba").json()[
        "alerts"] if a["fajta"] == "dontesek"]
    hivasok = []

    def ido(meccsek, csapat=None):
        hivasok.append(("ido", csapat, sorted(x["match_id"] for x in meccsek)))
        return {"itelet": "megtori"} if csapat == h else None

    def het(meccsek, csapat=None):
        hivasok.append(("het", csapat, sorted(x["match_id"] for x in meccsek)))
        return {"itelet": "nem"} if csapat == h else None

    monkeypatch.setattr(ps, "timeout_run_backtest", ido)
    monkeypatch.setattr(ps, "seven_six_backtest", het)
    j = c.get("/matches/gt3/live-modell-proba").json()
    d = [a for a in j["alerts"] if a["fajta"] == "dontesek"]
    assert [(a["team"], a["text"]) for a in d] == [
        ("home", f"AI-döntések ({h}, 2 korábbi meccs): időkérés: megtöri a "
                 "sorozatot; 7 a 6: nem éri meg")]
    # A meccs nélkül (a többi két meccs és a segéd "fm" meccse), a csapat
    # nevével.
    assert ("ido", h, ["fm", "gt1", "gt2"]) in hivasok
    assert ("het", h, ["fm", "gt1", "gt2"]) in hivasok


def test_az_elo_fal_valtas_vegpont(tmp_path, monkeypatch):
    """GET /matches/{id}/live-falvaltas: a próba a TÖBBI meccs
    mintáiból, a második fal a csapat többi meccséből — a valódi láncon
    ugyanaz, mint a motor; a /library/player-model-check "falvaltas_proba"
    mezője; 404."""
    import json

    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import (defense_switch_backtest,
                                                   defense_switch_sample,
                                                   defense_system_forecast,
                                                   live_defense_switch_alerts,
                                                   player_model_sample)
    from handball.sim.match_simulator import simulate_ground_truth

    app = _app(tmp_path, monkeypatch)
    meccsek = []
    for seed in (1, 2, 3):
        m = simulate_ground_truth(duration_s=420, fps=25.0, seed=seed,
                                  shots_per_min=8)
        m.meta.match_id = f"gt{seed}"
        m.meta.date = f"2026-10-0{seed}"
        meccsek.append(m)
        app.state.put_match(m)

    def lista(ms):
        return [{"match_id": m.meta.match_id, "home": m.meta.home_team,
                 "away": m.meta.away_team,
                 "minta": {s_: json.loads(json.dumps(
                     defense_switch_sample(m, Team(s_))))
                           for s_ in ("home", "away")}} for m in ms]

    tobbi = meccsek[:2]
    proba = defense_switch_backtest(lista(tobbi))
    alt = {s_: defense_system_forecast(
        [json.loads(json.dumps(player_model_sample(m, Team(s_))))["formak"]
         for m in tobbi]) for s_ in ("home", "away")}
    vart = live_defense_switch_alerts(meccsek[2], proba, alt)["alerts"]
    c = TestClient(app)
    j = c.get("/matches/gt3/live-falvaltas").json()
    assert vart and [a["text"] for a in j["alerts"]] == [a["text"] for a in vart]
    assert j["proba"] == proba
    assert c.get("/matches/nincs/live-falvaltas").status_code == 404
    assert c.get("/library/player-model-check").json()["falvaltas_proba"] == \
        defense_switch_backtest(lista(meccsek))


def test_az_elo_emberhatrany_vegpont(tmp_path, monkeypatch):
    """GET /matches/{id}/live-emberhatrany: a javaslat a csapat TÖBBI
    meccséből, a próba a többi meccs mintáiból — a valódi láncon ugyanaz,
    mint a motor (a szimulált meccseken nincs kiállítás: None); a
    /library/player-model-check és a /library/forecast mezői; 404."""
    import json

    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import (
        live_shorthanded_alerts, shorthanded_defense_backtest,
        shorthanded_defense_choice, shorthanded_defense_sample)
    from handball.sim.match_simulator import simulate_ground_truth

    app = _app(tmp_path, monkeypatch)
    meccsek = []
    for seed in (1, 2, 3):
        m = simulate_ground_truth(duration_s=180, fps=25.0, seed=seed,
                                  shots_per_min=8)
        m.meta.match_id = f"gt{seed}"
        m.meta.date = f"2026-10-0{seed}"
        meccsek.append(m)
        app.state.put_match(m)
    h, a = meccsek[0].meta.home_team, meccsek[0].meta.away_team

    def lista(ms):
        return [{"match_id": m.meta.match_id, "home": m.meta.home_team,
                 "away": m.meta.away_team,
                 "minta": {s_: json.loads(json.dumps(
                     shorthanded_defense_sample(m, Team(s_))))
                           for s_ in ("home", "away")}} for m in ms]

    tobbi = lista(meccsek[:2])
    jav = {s_: shorthanded_defense_choice([x["minta"][s_] for x in tobbi])
           for s_ in ("home", "away")}
    c = TestClient(app)
    j = c.get("/matches/gt3/live-emberhatrany").json()
    assert j["javaslat"] == jav
    assert j["alerts"] == live_shorthanded_alerts(meccsek[2], jav)["alerts"]
    assert j["proba"] == shorthanded_defense_backtest(tobbi)
    assert c.get("/matches/nincs/live-emberhatrany").status_code == 404
    mind = lista(meccsek)
    assert c.get("/library/player-model-check").json()[
        "emberhatrany_proba"] == shorthanded_defense_backtest(mind)
    f = c.get("/library/forecast", params={"home": h, "away": a}).json()
    assert f["emberhatrany_fal"] == {
        s_: shorthanded_defense_choice([x["minta"][s_] for x in mind])
        for s_ in ("home", "away")}
    assert f["emberhatrany_proba"] == shorthanded_defense_backtest(mind)


def test_az_utolso_labda_probaja_a_vegpontokon(tmp_path, monkeypatch):
    """GET /matches/{id}/live-utolso-labda "proba": a tanács próbája a
    könyvtár TÖBBI meccséből — a valódi láncon ugyanaz, mint a motor (a
    szimulált hajrá nem szoros: None); a /library/player-model-check
    "utolso_labda_proba" mezője."""
    import json

    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import (last_shot_backtest,
                                                   last_shot_sample,
                                                   player_model_sample)
    from handball.sim.match_simulator import simulate_ground_truth

    app = _app(tmp_path, monkeypatch)
    meccsek = []
    for seed in (1, 2, 3):
        m = simulate_ground_truth(duration_s=240, fps=25.0, seed=seed,
                                  shots_per_min=8)
        m.meta.match_id = f"gt{seed}"
        m.meta.date = f"2026-10-0{seed}"
        meccsek.append(m)
        app.state.put_match(m)

    def lista(ms):
        return [{"match_id": m.meta.match_id, "home": m.meta.home_team,
                 "away": m.meta.away_team,
                 "minta": {s_: json.loads(json.dumps(
                     player_model_sample(m, Team(s_)))) for s_ in ("home", "away")},
                 "hajra": {s_: json.loads(json.dumps(
                     last_shot_sample(m, Team(s_)))) for s_ in ("home", "away")}}
                for m in ms]

    c = TestClient(app)
    j = c.get("/matches/gt3/live-utolso-labda").json()
    assert "alerts" in j and j["proba"] == last_shot_backtest(lista(meccsek[:2]))
    assert c.get("/library/player-model-check").json()[
        "utolso_labda_proba"] == last_shot_backtest(lista(meccsek))


def test_a_finomito_es_a_szimulacio_a_mezszamokkal_es_a_lovokkel(
        tmp_path, monkeypatch):
    """POST /figura-finomitas a "mez" sorral: a válasz "mez" sora és a
    "lovo_felirat" (a mi lövőink a meccs másik oldaláról — lövés nélküli
    meccsen üres); POST /matches/{id}/simulate-setplay a "mez" sorral: a
    kiértékelés "lovo_szorzo" mezője és a "lovo_felirat"; mez nélkül a
    felirat üres. A lövős meccsen (szimulált) a felirat a tanult lövőké."""
    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import AttackModel, lovo_felirat
    from handball.sim.match_simulator import simulate_ground_truth
    from test_play_simulation import _proba_match

    app = _app(tmp_path, monkeypatch)
    app.state.put_match(_proba_match())
    c = TestClient(app)
    d = _AJANLO_FIGURAK[0]
    mez = [7] + [None] * (len(d["attackers"]) - 1)
    r = c.post("/figura-finomitas", json={
        "attackers": d["attackers"], "meccs": "pr", "vedo": "away",
        "mez": mez})
    assert r.status_code == 200
    j = r.json()
    assert j["mez"] == mez and j["lovo_felirat"] == ""
    r = c.post("/matches/pr/simulate-setplay", params={"defending": "away"},
               json={"attackers": [[[26, 10], [30, 10]], [[28, 4], [30, 6]]],
                     "ball_carrier": [0, 0], "mez": [7, None]})
    assert r.status_code == 200
    assert r.json()["evaluation"]["lovo_szorzo"] == 1.0
    assert r.json()["lovo_felirat"] == ""
    # A lövős meccsen a hazai (a vendég fal ellen mi támadunk) lövői.
    m = simulate_ground_truth(duration_s=600, fps=25.0, seed=1,
                              shots_per_min=8, halftime_break_s=30)
    m.meta.match_id = "gt"
    app.state.put_match(m)
    tam = AttackModel.learn(m, Team.HOME)
    assert tam.lovok
    mez7 = [next(iter(tam.lovok))] + [None] * (len(d["attackers"]) - 1)
    j = c.post("/figura-finomitas", json={
        "attackers": d["attackers"], "meccs": "gt", "vedo": "away",
        "mez": mez7}).json()
    assert j["lovo_felirat"] == lovo_felirat(tam)
    assert sorted(x for x in j["mez"] if x is not None) == [mez7[0]]
    s = c.post("/matches/gt/simulate-setplay", params={"defending": "away"},
               json={"attackers": [[[26, 10], [30, 10]], [[28, 4], [30, 6]]],
                     "ball_carrier": [0, 0], "mez": [mez7[0], None]}).json()
    assert s["lovo_felirat"] == lovo_felirat(tam)
    assert "lovo_szorzo" in s["evaluation"]
    assert c.post("/matches/gt/simulate-setplay", params={"defending": "away"},
                  json={"attackers": [[[26, 10], [30, 10]]],
                        "ball_carrier": [0, 0]}).json()["lovo_felirat"] == ""


def test_a_szuper_csere_probaja_a_vegpontokon(tmp_path, monkeypatch):
    """GET /matches/{id}/live-szupercsere: a tanács a könyvtár TÖBBI
    meccséből és a próba — a valódi láncon ugyanaz, mint a motor; a
    /library/player-model-check "szuper_csere_proba" és a /library/forecast
    "szuper_csere" mezője."""
    import json

    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import (super_sub_backtest,
                                                   super_sub_choice,
                                                   super_sub_sample)
    from handball.sim.match_simulator import simulate_ground_truth

    app = _app(tmp_path, monkeypatch)
    meccsek = []
    for seed in (1, 2, 3):
        m = simulate_ground_truth(duration_s=240, fps=25.0, seed=seed,
                                  shots_per_min=8)
        m.meta.match_id = f"gt{seed}"
        m.meta.date = f"2026-10-0{seed}"
        meccsek.append(m)
        app.state.put_match(m)
    h = meccsek[0].meta.home_team

    def minta(m, s_):
        return json.loads(json.dumps(super_sub_sample(m, Team(s_))))

    def lista(ms):
        return [{"match_id": m.meta.match_id, "home": m.meta.home_team,
                 "away": m.meta.away_team,
                 "minta": {s_: minta(m, s_) for s_ in ("home", "away")}}
                for m in sorted(ms, key=lambda m: ((m.meta.date or ""),
                                                   m.meta.match_id))]

    mind = list(app.state.store.values())      # az "fm" meccs is benne
    c = TestClient(app)
    j = c.get("/matches/gt3/live-szupercsere").json()
    assert "alerts" in j
    assert j["proba"] == super_sub_backtest(
        lista([m for m in mind if m.meta.match_id != "gt3"]))
    assert j["javaslat"]["home"] == super_sub_choice(
        [minta(m, "home") for m in meccsek[:2] if m.meta.home_team == h])
    assert c.get("/library/player-model-check").json()[
        "szuper_csere_proba"] == super_sub_backtest(lista(mind))
    assert c.get("/library/forecast?home=" + h + "&away="
                 + meccsek[0].meta.away_team).json()["szuper_csere"][
        "home"] == super_sub_choice([minta(m, "home") for m in meccsek])


def test_a_centis_minta_probaja_a_vegponton(tmp_path, monkeypatch):
    """/library/player-model-check "centis_proba": a valódi láncon
    ugyanaz, mint a motor (narrow_miss_backtest) a könyvtár időrendjében."""
    import json

    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import (narrow_miss_backtest,
                                                   narrow_miss_sample)
    from handball.sim.match_simulator import simulate_ground_truth

    app = _app(tmp_path, monkeypatch)
    for seed in (1, 2, 3):
        m = simulate_ground_truth(duration_s=240, fps=25.0, seed=seed,
                                  shots_per_min=8)
        m.meta.match_id = f"gt{seed}"
        m.meta.date = f"2026-10-0{seed}"
        app.state.put_match(m)
    mind = sorted(app.state.store.values(),
                  key=lambda m: ((m.meta.date or ""), m.meta.match_id))
    lista = [{"match_id": m.meta.match_id, "home": m.meta.home_team,
              "away": m.meta.away_team,
              "minta": {s_: json.loads(json.dumps(
                  narrow_miss_sample(m, Team(s_)))) for s_ in ("home", "away")}}
             for m in mind]
    c = TestClient(app)
    assert c.get("/library/player-model-check").json()[
        "centis_proba"] == narrow_miss_backtest(lista)
