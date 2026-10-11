"""A böngészős 3D/VR nézet eszközei: keringés, játékos-nézet, lövés-mérés,
védekezés-panel — és hogy a böngésző UGYANAZT méri, mint a backend."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (Ball, Frame, Match, MatchMeta,  # noqa: E402
                                      PlayerPosition, PositionSource, Team)

NODE = shutil.which("node")


def _pl(tid, team, x, y, mez=None):
    p = PlayerPosition(track_id=tid, team=team, x=x, y=y,
                       source=PositionSource.MEASURED, confidence=1.0)
    p.jersey_number = mez
    return p


def _meccs():
    """Hazai szervezett támadás a jobb kapura; a vendég 6-0-ban áll."""
    from handball.pipeline.court3d import formation_template
    vedok = [_pl(20 + i, Team.AWAY, x, y, mez=i + 2)
             for i, (x, y) in enumerate(formation_template("6-0", 40.0))]
    frames = []
    for t in range(50):
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 27.0 + t * 0.02,
                                              10.0, mez=7)] + vedok,
                            ball=Ball(x=27.3 + t * 0.02, y=10.0,
                                      confidence=1.0)))
    return Match(MatchMeta(match_id="v3t", home_team="Mi", away_team="Ok",
                           fps=25.0), frames)


def test_az_oldal_viszi_az_uj_eszkozoket():
    from handball.pipeline.view3d_html import view3d_html

    oldal = view3d_html(_meccs())
    for jel in ('id="keringGomb"', 'id="jatekosKi"', 'id="fal"',
                'id="falOldal"', 'id="falInfo"', 'id="meres"',
                "function lovesMeres", "function jatekosValasztas",
                "function kovetFrissit", "function meresKattintas",
                "function falFrissit", '"dblclick"', '"wheel"', '"KeyO"',
                '"KeyC"', "LineDashedMaterial", "computeLineDistances",
                "kapufaIv(bal, 9)", "Kapu-szög", 'id="lovesek"',
                'id="lovesInfo"', "function lovesKattintas",
                "function lovesFrissit", "lovesFrissit(ido)",
                'id="sebesseg"', 'id="nyom"', "function nyomFrissit",
                "ido + dt * sebesseg", 'id="hoter"', "function hoRacs",
                "function hoFest", 'data-n="madar"', "function nezet",
                'id="jatekosHud"', "function tavTabla", "function hudFrissit",
                "TAV_UGRAS_M = 3", 'id="passz"', "function passzFrissit",
                "passzFrissit(ido)", 'id="jatekosKamera"',
                "function kovetesFrissit", "kovetesFrissit(dt)",
                'mod === "kovetes"', 'id="linkGomb"', "function linkEpit",
                "function linkAlkalmaz", "linkAlkalmaz();", 'id="tvGomb"',
                "function tvFrissit", "tvFrissit(dt)", '"KeyT"',
                'id="passzsav"', "function passzSavok",
                'id="dontesKov"', 'id="dontesElozo"', "function dontesUgras",
                'id="szabadKov"', 'id="szabadElozo"', "function szabadUgras",
                "function szabadFrissit",
                'id="eladasKov"', 'id="eladasElozo"', "function eladasUgras",
                'id="falres"', "function falResek", "function falresFrissit",
                'id="jelenetCsapat"', "function szurt(lista)",
                'id="jelenetGomb"', 'id="jelenetLista"',
                'id="golKov"', 'id="golElozo"', "function golUgras",
                'id="emberKov"', 'id="emberElozo"', 'id="emberJelzo"',
                # a panel alacsony ablakban görgethető (nem lóg a sáv alá)
                "max-height:calc(100vh - 110px);overflow-y:auto",
                'id="sugoGomb"', "function sugoAllit", "innerWidth >= 1200",
                "function vrFeliratFrissit", "kamera.add(vrTabla)",
                'g.id = "klipGomb"', "function klipKer", "function klipAllapotSzoveg",
                "function vrGombEl", "function jelenetLep", "function vrGombok",
                'e.code === "KeyN"', 'e.code === "KeyP"',
                "vrGombok();", "vrGombEl(kulcs, 4, nyom(4))",
                '"/clips/export"', '"/jobs/" + job_id', '"/clips/download"',
                "vrFeliratFrissit();", "fest.xr.isPresenting || VR_FELIRAT_KENYSZER",
                "function emberFrissit", "function emberSzoveg",
                "emberFrissit(t)",
                "function golFrissit", 'id="golFelirat"',
                "function golAkcioFelirat",
                "function jelenetListaEpit", "jelenetListaJelol(ido)",
                'q.set("lista", "1")',
                "function jelenetInfok", 'q.set("jelenet"',
                "lapozCel(szurt(DONTESEK)", "lapozCel(szurt(SZABADOK)",
                "lapozCel(szurt(ELADASOK)", "szurt(ELADASOK).find(",
                "falresFrissit(ido)", 'q.set("falres", "1")',
                "function eladasFrissit", 'id="eladasFelirat"',
                "function dontesFrissit", "dontesFrissit(ido)",
                "function passzsavFrissit", "passzsavFrissit();",
                "const FELTORES = ADAT.breakpoints", '"Feltörés: <b>"',
                "function feltoresSav", "feltoresSik.visible = true",
                "const MEGALLITAS = ADAT.stoppers", '"Megállítás: <b>"'):
        assert jel in oldal, jel
    # Üres beágyazott ikon: a böngésző nem kér /favicon.ico-t (404 a konzolon).
    assert '<link rel="icon" href="data:,">' in oldal
    # A játékos-nézet gombja megnevezi, kinek a szemével nézünk.
    assert '" szemével ✕"' in oldal
    # A pointer-lock helyett húzással néz (a katt a mérésé).
    assert "requestPointerLock" not in oldal
    # A labda a birtokos ELŐTT: a figura eleje a helyi +z.
    assert "new THREE.Vector3(0, 0, 1)" in oldal
    assert "new THREE.Vector3(0, 0, -1)" not in oldal


def test_a_tomor_adat_viszi_a_falsablonokat_es_az_elo_falat():
    from handball.pipeline.court3d import FORMATION_TEMPLATES
    from handball.pipeline.view3d_html import _compact_data

    adat = _compact_data(_meccs())
    assert adat["formations"] == {k: [list(p) for p in v]
                                  for k, v in FORMATION_TEMPLATES.items()}
    assert adat["defence"], "a szervezett támadásnak van fal-sora"
    s, hazai, cimke, goal_x = adat["defence"][0]
    assert hazai == 0 and cimke == "6-0" and goal_x == 40.0
    assert [r[0] for r in adat["defence"]] == [0.0, 1.0]


def test_a_tomor_adat_viszi_a_feltorest():
    """A védekezés-panel "Feltörés" sora: csapatonként a felderítés
    rangsorának teteje (legfeljebb DEFENCE_BREAKPOINTS_TOP), a lövős
    szimuláción a vendégre meg is szólal; a kis fixtúrán csak az alak."""
    from handball.pipeline.court3d import (DEFENCE_BREAKPOINTS_TOP,
                                           defence_breakpoints_by_team)
    from handball.pipeline.view3d_html import _compact_data
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=240, fps=25.0, seed=5,
                              shots_per_min=8)
    f = defence_breakpoints_by_team(m)
    assert set(f) == {"home", "away"}
    assert f["away"], "a lövős szimuláció vendég-védekezése feltörhető"
    assert len(f["away"]) <= DEFENCE_BREAKPOINTS_TOP
    assert {"hol", "mivel", "miert", "pont"} <= set(f["away"][0])
    assert _compact_data(m)["breakpoints"] == f
    # A végpont a tárból adja át — a tömör adat azt viszi, nem számol újra.
    atadott = {"home": [{"hol": "x", "mivel": "y", "miert": "z", "pont": 1.0}],
               "away": []}
    assert _compact_data(_meccs(), None, atadott)["breakpoints"] == atadott
    kicsi = defence_breakpoints_by_team(_meccs())
    assert isinstance(kicsi["home"], list) and isinstance(kicsi["away"], list)


def test_a_tomor_adat_viszi_a_megallitast():
    """A "Megállítás" sor: csapatonként az attack_stoppers teteje, EGY
    felderítésből a feltöréssel együtt (tactical_keys_by_team); a
    lövős szimuláción a hazai támadásra megszólal; az átadott lista
    nem számolódik újra."""
    from handball.pipeline.court3d import (DEFENCE_BREAKPOINTS_TOP,
                                           defence_breakpoints_by_team,
                                           tactical_keys_by_team)
    from handball.pipeline.view3d_html import _compact_data
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=240, fps=25.0, seed=5,
                              shots_per_min=8)
    k = tactical_keys_by_team(m)
    assert set(k) == {"breakpoints", "stoppers"}
    assert k["stoppers"]["home"], "a lövős hazai támadás megállítható"
    assert len(k["stoppers"]["home"]) <= DEFENCE_BREAKPOINTS_TOP
    assert k["breakpoints"] == defence_breakpoints_by_team(m)
    adat = _compact_data(m)
    assert adat["stoppers"] == k["stoppers"]
    atadott = {"home": [{"hol": "x", "mivel": "y", "miert": "z", "pont": 1.0}],
               "away": []}
    assert _compact_data(_meccs(), None, {"home": [], "away": []},
                         atadott)["stoppers"] == atadott


def test_a_tomor_adat_viszi_a_dontes_pillanatokat(tmp_path, monkeypatch):
    """A tömör adat "decisions" sorai a decision_moments pillanatai
    (azonos sorrendben, a 12 mezős alakban); a végpont ugyanazt adja."""
    from fastapi.testclient import TestClient

    from handball.api.app import create_app
    from handball.pipeline.court3d import decision_moments
    from handball.pipeline.view3d_html import _compact_data
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=120, fps=25.0, seed=5,
                              shots_per_min=8)
    sorok = _compact_data(m, None, {"home": [], "away": []},
                          {"home": [], "away": []})["decisions"]
    d = decision_moments(m)["moments"]
    assert len(sorok) == len(d) > 0
    for r, x in zip(sorok, d):
        assert len(r) == 12 and r[0] == x["s"] and r[-1] == x["gap"]
        assert r[7] == ("s" if x["best_kind"] == "shoot" else "p")
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    app = create_app()
    app.state.put_match(m)
    c = TestClient(app)
    v = c.get(f"/matches/{m.meta.match_id}/decision-moments").json()
    assert len(v["moments"]) == len(d)
    assert c.get("/matches/nincs/decision-moments").status_code == 404


def test_a_tomor_adat_es_a_vegpont_viszi_a_szabad_lovoket(tmp_path, monkeypatch):
    """A tömör adat "free_shots" sorai a free_shot_moments pillanatai (9
    mezős alak, a fedezés-sugárral); a /free-shots végpont ugyanazt adja."""
    from fastapi.testclient import TestClient

    from handball.api.app import create_app
    from handball.pipeline.court3d import free_shot_moments
    from handball.pipeline.view3d_html import _compact_data
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=240, fps=25.0, seed=5,
                              shots_per_min=8)
    adat = _compact_data(m, None, {"home": [], "away": []},
                         {"home": [], "away": []})
    fs = free_shot_moments(m)
    assert adat["free_radius"] == fs["radius_m"]
    assert len(adat["free_shots"]) == len(fs["moments"]) > 0
    for r, x in zip(adat["free_shots"], fs["moments"]):
        assert len(r) == 9 and r[0] == x["s"] and r[6] == x["dist"]
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    app = create_app()
    app.state.put_match(m)
    c = TestClient(app)
    v = c.get(f"/matches/{m.meta.match_id}/free-shots").json()
    assert len(v["moments"]) == len(fs["moments"])
    assert c.get("/matches/nincs/free-shots").status_code == 404


def test_a_tomor_adat_es_a_vegpont_viszi_a_labdavesztest(tmp_path, monkeypatch):
    """A tömör adat "turnovers" sorai a turnover_moments pillanatai (13
    mezős alak: a harmad indexe, a kipréselt 1/0/null), a nyomás-sugárral;
    a /turnover-moments végpont ugyanazt adja, ismeretlen meccsre 404."""
    from fastapi.testclient import TestClient
    from test_court3d import _eladasos_meccs

    from handball.api.app import create_app
    from handball.pipeline.court3d import turnover_moments
    from handball.pipeline.view3d_html import _compact_data

    m = _eladasos_meccs()
    adat = _compact_data(m, None, {"home": [], "away": []},
                         {"home": [], "away": []})
    tm = turnover_moments(m)
    assert adat["turnover_pressure"] == tm["pressure_m"]
    assert len(adat["turnovers"]) == len(tm["moments"]) > 0
    harmad = {"saját": 0, "közép": 1, "támadó": 2, None: None}
    for r, x in zip(adat["turnovers"], tm["moments"]):
        assert len(r) == 13 and r[0] == x["s"]
        assert r[1] == (1 if x["team"] == "home" else 0)
        assert r[2] == x["jersey"] and r[7] == harmad[x["zone"]]
        assert r[10] == x["dist"] and r[12] == x["goal_after_s"]
        assert r[11] == (None if x["forced"] is None else int(x["forced"]))
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    app = create_app()
    app.state.put_match(m)
    c = TestClient(app)
    v = c.get(f"/matches/{m.meta.match_id}/turnover-moments").json()
    assert len(v["moments"]) == len(tm["moments"])
    assert v["punished"] == tm["punished"]
    assert c.get("/matches/nincs/turnover-moments").status_code == 404

def test_a_tomor_adat_viszi_a_passzokat():
    """A passz-sorok: [mp, hazai?, adó x, y, fogadó x, y] a felismerés
    PASS eseményeiből — annyi, ahánynak az adója és a fogadója is a
    passz kockáján van. Passz nélküli meccsen üres (nem hiba)."""
    from handball.pipeline.event_detection import EventType, detect_events
    from handball.pipeline.view3d_html import _compact_data
    from handball.sim.match_simulator import simulate_ground_truth

    assert _compact_data(_meccs())["passes"] == []
    m = simulate_ground_truth(duration_s=60, fps=25.0, seed=3,
                              shots_per_min=6)
    passzok = _compact_data(m)["passes"]
    assert passzok, "a szimuláció passzol"
    by_t = {f.t: f for f in m.frames}
    vart = 0
    for e in detect_events(m):
        if e.type != EventType.PASS or e.player_id is None:
            continue
        f = by_t.get(e.t)
        ids = {p.track_id for p in f.players} if f else set()
        rid = (e.detail or {}).get("receiver_id")
        if rid is not None and e.player_id in ids and rid in ids:
            vart += 1
    assert len(passzok) == vart
    for mp, hazai, x1, y1, x2, y2 in passzok:
        assert hazai in (0, 1) and 0 <= x1 <= 40 and 0 <= x2 <= 40
        assert 0 <= y1 <= 20 and 0 <= y2 <= 20
    assert [r[0] for r in passzok] == sorted(r[0] for r in passzok)


def test_a_tomor_adat_viszi_a_lovesterkepet():
    """A lövéstérkép sorai a match_xg lövéseiből: [mp, hazai?, x, y, xG,
    kimenet, a támadott kapu x-e] — a böngésző ebből rajzolja a köröket.
    Lövés nélküli meccsen üres lista (nem hiba)."""
    from handball.pipeline.view3d_html import _compact_data
    from handball.pipeline.xg import match_xg
    from handball.sim.match_simulator import simulate_ground_truth

    assert _compact_data(_meccs())["shots"] == []
    m = simulate_ground_truth(duration_s=60, fps=25.0, seed=3,
                              shots_per_min=6)
    lovesek = _compact_data(m)["shots"]
    xg = match_xg(m)["shots"]
    assert lovesek and len(lovesek) == len(xg)
    for sor, s in zip(lovesek, xg):
        mp, hazai, x, y, xg_ert, kimenet, goal_x = sor
        assert mp == round(s["t"] / 25.0, 2)
        assert hazai == (1 if s["team"] == "home" else 0)
        assert (x, y) == (s["x"], s["y"]) and abs(xg_ert - s["xg"]) < 1e-3
        assert kimenet in ("g", "v", "m") and goal_x in (0.0, 40.0)
        assert (kimenet == "g") == (s["outcome"] == "goal")


@pytest.mark.skipif(NODE is None, reason="nincs node a gépen")
def test_a_bongeszo_hoterkepe_a_backend_racsat_adja():
    """A böngésző hőtérkép-rácsa (hoRacs) ugyanazt a cellába sorolást
    végzi, mint az elemzés hőtérképe (`analytics._cell_index`: 20×10
    cella, csak a MÉRT helyek) — a tömör adat (0,1 m-re kerekített)
    kockáin futtatva, cellánként pontosan egyező számokkal."""
    from handball.pipeline.analytics import _cell_index
    from handball.pipeline.view3d_html import _compact_data, view3d_html

    m = _meccs()
    adat = _compact_data(m)
    kod = _modul_szkript(view3d_html(m))
    i0 = kod.index("function hoRacs("); i1 = kod.index("let hoRacsok")
    js = ("const H = 40, W = 20, HO_X = 20, HO_Y = 10;\nconst frames = " +
          json.dumps(adat["frames"]) + ";\n" + kod[i0:i1] +
          "\nconsole.log(JSON.stringify([hoRacs(true), hoRacs(false)]));\n")
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    hazai, vendeg = json.loads(r.stdout)
    for js_r, hazai_e in ((hazai, 1), (vendeg, 0)):
        py = [[0] * 20 for _ in range(10)]
        for f in adat["frames"]:
            for p in f[1]:
                if p[0] != hazai_e or not p[3]:
                    continue
                ix, iy = _cell_index(p[1], p[2], 20, 10)
                py[iy][ix] += 1
        assert js_r["r"] == py, hazai_e
        assert js_r["max"] == max(max(sor) for sor in py) > 0


@pytest.mark.skipif(NODE is None, reason="nincs node a gépen")
def test_a_bongeszo_megtett_utja_a_python_osszeget_adja():
    """A játékos-nézet HUD-jának megtett útja (tavTabla): kockánként
    összegzett elmozdulás a mezszám szerint, a 3 m-nél nagyobb lépés
    (követés-ugrás) kihagyva — a Python-referenciával egyezik, a
    kihagyott lépés tényleg kimarad."""
    from handball.pipeline.view3d_html import _compact_data, view3d_html

    m = _meccs()
    # Egy ugrás a hazai 7-esnek a 20. kockán (követés-hiba): nem számít.
    m.frames[20].players[0].x += 10.0
    adat = _compact_data(m)
    kod = _modul_szkript(view3d_html(m))
    i0 = kod.index("const TAV_UGRAS_M"); i1 = kod.index("const jatekosHud")
    js = ("const frames = " + json.dumps(adat["frames"]) + ";\n" + kod[i0:i1] +
          "\nconsole.log(JSON.stringify([Array.from(tavTabla(true, 7)),"
          " Array.from(tavTabla(false, 2))]));\n")
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    hazai7, vendeg2 = json.loads(r.stdout)

    def ref(cs, mez):
        import math
        ossz, ex, ki = 0.0, None, []
        for f in adat["frames"]:
            p = next((q for q in f[1] if q[0] == cs and q[5] == mez), None)
            if p is not None:
                if ex is not None:
                    d = math.hypot(p[1] - ex[0], p[2] - ex[1])
                    if d <= 3:
                        ossz += d
                ex = (p[1], p[2])
            ki.append(ossz)
        return ki

    assert all(abs(a - b) < 1e-9 for a, b in zip(hazai7, ref(1, 7)))
    assert all(abs(a - b) < 1e-9 for a, b in zip(vendeg2, ref(0, 2)))
    # A 7-es 50 kockán 0,02 m-t lép kockánként (a tömör adat 0,1 m-re
    # kerekít: 0,8 m), az ugrás 10 m-e és a visszaugrás nélkül — nem
    # 20 m fölött.
    assert 0.5 < hazai7[-1] < 1.0, hazai7[-1]
    assert vendeg2[-1] == 0.0  # a fal áll


@pytest.mark.skipif(NODE is None, reason="nincs node a gépen")
def test_a_bongeszo_feltores_savja_a_backendet_tukrozi():
    """A böngésző feltörés-sávja (feltoresSav) ugyanazt a téglalapot adja,
    mint a court3d.breakpoint_zone_band — mindkét kapura, mindhárom sávra."""
    from handball.pipeline.court3d import breakpoint_zone_band
    from handball.pipeline.view3d_html import view3d_html

    kod = _modul_szkript(view3d_html(_meccs()))
    i0 = kod.index("function feltoresSav(")
    i1 = kod.index("\n}\n", i0) + 2   # a függvény záró kapcsos zárójele
    js = ("const H = 40, W = 20;\n" + kod[i0:i1] +
          "\nconst ki = [];\nfor (const g of [0, 40]) for (const s of "
          "['bal szél', 'közép', 'jobb szél', 'x']) ki.push(feltoresSav(s, g));"
          "\nconsole.log(JSON.stringify(ki));\n")
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    js_ki = json.loads(r.stdout)
    py_ki = [breakpoint_zone_band(s, g) for g in (0.0, 40.0)
             for s in ("bal szél", "közép", "jobb szél", "x")]
    for a, b in zip(js_ki, py_ki):
        if b is None:
            assert a is None
            continue
        for k in ("x0", "x1", "y0", "y1"):
            assert abs(a[k] - b[k]) < 0.01, (a, b)


@pytest.mark.skipif(NODE is None, reason="nincs node a gépen")
def test_a_bongeszo_passzsavjai_a_backendet_tukrozik():
    """A böngésző passzsávjai (passzSavok) ugyanazt adják, mint a
    court3d.pass_lanes — 300 véletlen álláson (labdás, esélyek, blokkolók,
    fokozat), a backend-konstansokkal beágyazva."""
    import random

    from handball.pipeline.court3d import pass_lanes
    from handball.pipeline.view3d_html import view3d_html

    kod = _modul_szkript(view3d_html(_meccs()))
    i0 = kod.index("const PS_SUGAR"); i1 = kod.index("\n}\n", kod.index("function passzSavok")) + 2
    rnd = random.Random(7)
    esetek = []
    for _ in range(300):
        jat = [[rnd.randint(0, 1), round(rnd.uniform(0, 40), 1),
                round(rnd.uniform(0, 20), 1)] for _ in range(rnd.randint(2, 14))]
        h = rnd.choice(jat)
        labda = [h[1] + rnd.uniform(-3.5, 3.5), h[2] + rnd.uniform(-3.5, 3.5)]
        esetek.append([jat, labda])
    js = (kod[i0:i1] + "\nconst E = " + json.dumps(esetek) + ";\n"
          "console.log(JSON.stringify(E.map(e => passzSavok(e[0], e[1]))));\n")
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    js_ki = json.loads(r.stdout)
    volt = 0
    for (jat, labda), j in zip(esetek, js_ki):
        py = pass_lanes([tuple(p) for p in jat], tuple(labda))
        if py is None:
            assert j is None
            continue
        volt += 1
        assert j["holder"][:2] == py["holder"][:2]
        assert bool(j["holder"][2]) == bool(py["holder"][2])
        assert len(j["lanes"]) == len(py["lanes"])
        for a, b in zip(j["lanes"], py["lanes"]):
            assert abs(a["p"] - b["p"]) < 1e-3, (a, b)
            assert a["blockers"] == b["blockers"] and a["grade"] == b["grade"]
    assert volt > 100, "kevés eset jutott labdáshoz"



@pytest.mark.skipif(NODE is None, reason="nincs node a gépen")
def test_a_bongeszo_fal_resei_a_backendet_tukrozik():
    """A böngésző fal-rései (falResek) ugyanazt adják, mint a
    court3d.wall_gap_segments — 400 véletlen álláson (mért/becsült,
    kapus, a 12 m-es mélység két oldalán, y-holtversennyel), a
    backend-konstansokkal beágyazva."""
    import random

    from handball.models.tracking import (PlayerPosition, PositionSource,
                                          Team)
    from handball.pipeline.court3d import wall_gap_segments
    from handball.pipeline.view3d_html import view3d_html

    kod = _modul_szkript(view3d_html(_meccs()))
    i0 = kod.index("const FR_RES")
    i1 = kod.index("\n}\n", kod.index("function falResek")) + 2
    rnd = random.Random(11)
    esetek = []
    for _ in range(400):
        goal_x = rnd.choice([0.0, 40.0])
        jat = []
        for _ in range(rnd.randint(4, 16)):
            x = round(abs(goal_x - rnd.uniform(1, 16)), 1)
            # durva y-rács: gyakori holtverseny (a rendezés x-szel dönt)
            y = round(rnd.choice([rnd.uniform(1, 19), rnd.randint(2, 18)]), 1)
            jat.append([rnd.randint(0, 1), x, y,
                        1 if rnd.random() < 0.85 else 0,
                        1 if rnd.random() < 0.08 else 0])
        esetek.append([jat, rnd.randint(0, 1), goal_x])
    js = (kod[i0:i1] + "\nconst E = " + json.dumps(esetek) + ";\n"
          "console.log(JSON.stringify(E.map(e => falResek(e[0], !!e[1], e[2]))));\n")
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    volt = 0
    for (jat, hazai, goal_x), j in zip(esetek, json.loads(r.stdout)):
        jatekosok = [PlayerPosition(
            track_id=i, team=Team.HOME if p[0] else Team.AWAY, x=p[1], y=p[2],
            source=(PositionSource.MEASURED if p[3]
                    else PositionSource.ESTIMATED),
            confidence=1.0, role="kapus" if p[4] else None)
            for i, p in enumerate(jat)]
        py = wall_gap_segments(jatekosok, Team.HOME if hazai else Team.AWAY,
                               goal_x)
        if py is None:
            assert j is None
            continue
        volt += 1
        assert len(j["fal"]) == len(py["wall"])
        for a, b in zip(j["fal"], py["wall"]):
            assert abs(a[0] - b[0]) < 0.01 and abs(a[1] - b[1]) < 0.01
        assert j["szeles"] == py["wide"]
        assert j["maxI"] == py["max_index"]
        assert abs(j["max"] - py["max_gap"]) < 0.01
    assert volt > 100, "kevés esetben állt fal"

# A lapozó elvárt viselkedése — a böngésző (node) és az app (Dart) ugyanezt
# a táblát futtatja: (idők, most, utolsó, irány) → cél.
LAPOZO_ESETEK = [
    ([1.12, 2.28, 6.0], 0.0, None, 1, 1.12),     # az első 1,6 mp is elérhető
    ([1.12, 2.28, 6.0], 0.0, 1.12, 1, 2.28),     # ugrás után a következőre
    ([1.12, 2.28, 6.0], 0.78, 2.28, 1, 6.0),     # a 2,28 ablakában: tovább
    ([1.12, 2.28, 6.0], 4.5, 6.0, -1, 2.28),     # vissza az ugrott elől
    ([1.12, 2.28, 6.0], 20.0, 6.0, -1, 6.0),     # ablakon kívül: a fejtől
    ([1.12, 2.28, 6.0], 20.0, 6.0, 1, None),     # nincs több előre
    ([1.12, 2.28, 6.0], 0.0, None, -1, None),    # nincs korábbi
    ([5.0], 3.4, None, 1, 5.0),                  # a lejátszófej után
]


@pytest.mark.skipif(NODE is None, reason="nincs node a gépen")
def test_a_bongeszo_lapozoja_eleri_az_elso_pillanatot_es_nem_ragad():
    """A pillanat-lapozó (lapozCel): az első 1,6 mp pillanata is elérhető
    (a régi "> most + 1,6" szabály a meccs elején kihagyta), ugrás után
    a KÖVETKEZŐRE lép (nem ragad le), vissza az ugrott elől lép."""
    from handball.pipeline.view3d_html import LAPOZO_JS

    js = (LAPOZO_JS + "\nconst E = " + json.dumps(
        [list(e[:4]) for e in LAPOZO_ESETEK]) + ";\n"
        "console.log(JSON.stringify(E.map(e => lapozCel(e[0], e[1], e[2], e[3]))));\n")
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [e[4] for e in LAPOZO_ESETEK]


def test_az_app_lapozoja_ugyanazt_a_tablat_futtatja():
    """A Dart-tükör (court_geometry.lapozCel) tesztje ugyanazt az
    esettáblát futtatja — a táblát innen olvassuk ki és vetjük össze."""
    from pathlib import Path

    teszt = (Path(__file__).resolve().parent.parent.parent / "client" /
             "test" / "court_geometry_test.dart").read_text(encoding="utf-8")
    for idok, most, utolso, irany, cel in LAPOZO_ESETEK:
        sor = (f"lapozCel({[float(x) for x in idok]}, {float(most)}, "
               f"{'null' if utolso is None else float(utolso)}, {irany}), "
               f"{'isNull' if cel is None else float(cel)}")
        assert sor in teszt, sor




@pytest.mark.skipif(NODE is None, reason="nincs node a gépen")
def test_a_jelenet_lista_sorai_idorendben_magyar_felirattal():
    """A jelenet-lista (jelenetSorok) a három lapozó tömör soraiból egy
    időrendi listát épít: holtversenyben döntés, szabad lövés,
    labdavesztés; a felirat a csapattal, a jobb opcióval, a védő
    távolságával, a mezszámmal, a harmaddal és a góllal."""
    from handball.pipeline.view3d_html import view3d_html

    kod = _modul_szkript(view3d_html(_meccs()))
    i0 = kod.index("function jelenetSorok")
    i1 = kod.index("\n}\n", i0) + 2
    dontesek = [[5.0, 1, 30, 5, 34, 8, 0.18, "s", 40, 10, 0.36, 0.18],
                [61.5, 0, 12, 5, 9, 8, 0.2, "p", 6, 14, 0.4, 0.2]]
    szabadok = [[5.0, 0, 33, 12, 36, 15, 3.64, 1, 0.42],
                [70.0, 1, 8, 9, None, None, None, 0, 0.1]]
    eladasok = [[3.25, 1, 7, 20, 10, 20, 10.6, 1, 20, 10.6, 0.6, 1, 6.0],
                [65.0, 0, None, None, None, 35, 10, None, None, None, None,
                 None, None]]
    js = (kod[i0:i1] + "\nconsole.log(JSON.stringify(jelenetSorok(" +
          json.dumps(dontesek) + ", " + json.dumps(szabadok) + ", " +
          json.dumps(eladasok) + ', "Szeged", "Veszprém")));\n')
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    sorok = json.loads(r.stdout)
    assert [(x["ido"], x["tipus"]) for x in sorok] == [
        ("0:03", "e"), ("0:05", "d"), ("0:05", "sz"), ("1:01", "d"),
        ("1:05", "e"), ("1:10", "sz")]
    sz = [x["szoveg"] for x in sorok]
    assert sz[0] == ("Szeged — labdavesztés #7 (középső harmad) · gól lett "
                     "belőle")
    assert sz[1] == "Szeged — jobb opció is volt: lövés"
    assert sz[2] == "Veszprém védekezése — szabad lövő (3,6 m) · GÓL"
    assert sz[3] == "Veszprém — jobb opció is volt: passz egy szabadabb társhoz"
    assert sz[4] == "Veszprém — labdavesztés"
    assert sz[5] == "Szeged védekezése — szabad lövő"
    assert [x["gol"] for x in sorok] == [True, False, True, False, False,
                                         False]
    # A kanonikus Python-forrás (court3d.scene_rows) ugyanerre a helyzetre
    # (az API sorainak alakjában) ugyanezt adja.
    from handball.pipeline.court3d import scene_rows
    py = scene_rows(
        [{"s": 5.0, "team": "home", "best_kind": "shoot"},
         {"s": 61.5, "team": "away", "best_kind": "pass"}],
        [{"s": 5.0, "defending": "away", "dist": 3.64, "goal": True},
         {"s": 70.0, "defending": "home", "dist": None, "goal": False}],
        [{"s": 3.25, "team": "home", "jersey": 7, "zone": "közép",
          "goal_after_s": 6.0},
         {"s": 65.0, "team": "away", "jersey": None, "zone": None,
          "goal_after_s": None}],
        "Szeged", "Veszprém")
    assert [(x["ido"], x["tipus"], x["szoveg"], x["gol"]) for x in py] == \
        [(x["ido"], x["tipus"], x["szoveg"], x["gol"]) for x in sorok]
    # Az app tükre (court_geometry.sceneRows) UGYANEZT a helyzetet
    # futtatja ugyanezekkel a várt feliratokkal — itt keressük meg őket.
    from pathlib import Path
    dart = (Path(__file__).resolve().parent.parent.parent / "client" /
            "test" / "court_geometry_test.dart").read_text(encoding="utf-8")
    for felirat in sz:
        assert f'"{felirat}"' in dart, felirat


@pytest.mark.skipif(NODE is None, reason="nincs node a gépen")
def test_a_jelenet_lista_a_python_forrast_tukrozi():
    """Valódi meccseken (lövésekkel teli szimuláció: döntések és szabad
    lövések; az eladásos meccs: labdavesztések) a böngésző jelenetSorok-ja
    a tömör adatból sorról sorra ugyanazt adja, mint a court3d.scene_rows
    a végpontok soraiból — idő, fajta, felirat, gól."""
    from test_court3d import _eladasos_meccs

    from handball.pipeline.court3d import (conceded_goal_moments,
                                           decision_moments,
                                           fast_break_moments,
                                           free_shot_moments, scene_rows,
                                           turnover_moments)
    from handball.pipeline.view3d_html import _compact_data, view3d_html
    from handball.sim.match_simulator import simulate_ground_truth

    kod = _modul_szkript(view3d_html(_meccs()))
    i0 = kod.index("function jelenetSorok")
    i1 = kod.index("\n}\n", i0) + 2
    volt = {"d": 0, "sz": 0, "e": 0, "k": 0, "kg": 0}
    for m in (simulate_ground_truth(duration_s=120, fps=25.0, seed=5,
                                    shots_per_min=8), _eladasos_meccs()):
        adat = _compact_data(m, None, {"home": [], "away": []},
                             {"home": [], "away": []})
        js = (kod[i0:i1] + "\nconsole.log(JSON.stringify(jelenetSorok(" +
              json.dumps(adat["decisions"]) + ", " +
              json.dumps(adat["free_shots"]) + ", " +
              json.dumps(adat["turnovers"]) + ", " +
              json.dumps(m.meta.home_team) + ", " +
              json.dumps(m.meta.away_team) + ", " +
              json.dumps(adat["fast_breaks"]) + ", " +
              json.dumps(adat["conceded_goals"]) + ")));\n")
        r = subprocess.run([NODE, "-e", js], capture_output=True, text=True,
                           timeout=60)
        assert r.returncode == 0, r.stderr
        py = scene_rows(decision_moments(m)["moments"],
                        free_shot_moments(m)["moments"],
                        turnover_moments(m)["moments"],
                        m.meta.home_team, m.meta.away_team,
                        fast_break_moments(m)["moments"],
                        conceded_goal_moments(m)["moments"])
        jsk = json.loads(r.stdout)
        assert [(x["ido"], x["tipus"], x["szoveg"], x["gol"]) for x in jsk] \
            == [(x["ido"], x["tipus"], x["szoveg"], x["gol"]) for x in py]
        for x in py:
            volt[x["tipus"]] += 1
    assert all(volt.values()), volt


def test_a_tomor_adat_es_a_vegpont_viszi_a_gol_akciokat(tmp_path,
                                                         monkeypatch):
    """A tömör adat "goal_build_ups" sorai a goal_build_ups góljai (11
    mezős alak, a lánc 6 mezős passz-sorokkal); a /goal-build-ups
    végpont ugyanazt adja, ismeretlen meccsre 404."""
    from fastapi.testclient import TestClient

    from handball.api.app import create_app
    from handball.pipeline.court3d import goal_build_ups
    from handball.pipeline.view3d_html import _compact_data
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=120, fps=25.0, seed=5,
                              shots_per_min=8)
    adat = _compact_data(m, None, {"home": [], "away": []},
                         {"home": [], "away": []})
    gb = goal_build_ups(m)
    assert adat["match_id"] == m.meta.match_id  # a Klipek gomb kéréséhez
    assert len(adat["goal_build_ups"]) == len(gb["moments"]) > 0
    for r, x in zip(adat["goal_build_ups"], gb["moments"]):
        assert len(r) == 11 and r[0] == x["s"] and r[1] == x["goal_s"]
        assert len(r[3]) == x["n_passes"] == r[9]
        assert all(len(p) == 6 for p in r[3])
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    app = create_app()
    app.state.put_match(m)
    c = TestClient(app)
    v = c.get(f"/matches/{m.meta.match_id}/goal-build-ups").json()
    assert len(v["moments"]) == len(gb["moments"])
    assert c.get("/matches/nincs/goal-build-ups").status_code == 404


@pytest.mark.skipif(NODE is None, reason="nincs node a gépen")
def test_a_gol_akcio_felirata():
    """A gól-akció felirata: a passzolók mezszámai nyíllal, hosszú
    láncnál az első kettő és az utolsó kettő, a lövő, a passzok száma és
    az időtartam; passz nélkül és ismeretlen mezszámmal is."""
    from handball.pipeline.view3d_html import view3d_html

    kod = _modul_szkript(view3d_html(_meccs()))
    i0 = kod.index("function golAkcioFelirat")
    i1 = kod.index("\n}\n", i0) + 2
    p = lambda a, b: [1, 1, 2, 2, a, b]  # noqa: E731
    esetek = [
        [3.0, 9.5, 1, [p(10, 9), p(9, 7), p(7, 10)], 30, 10, 10, 40, 10, 3,
         6.5],
        [1.0, 12.0, 0, [p(2, 3), p(3, 4), p(4, 5), p(5, 6), p(6, 2)], 8, 9,
         2, 0, 10, 5, 11.0],
        [20.0, 20.0, 1, [], 35, 10, None, 40, 10, 0, 0.0],
    ]
    js = (kod[i0:i1] + "\nconsole.log(JSON.stringify(" + json.dumps(esetek)
          + '.map(d => golAkcioFelirat(d, "Szeged", "Veszprém"))));\n')
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [
        "Szeged gólja — #10 → #9 → #7 → #10 lő · 3 passz, 6,5 mp",
        "Veszprém gólja — #2 → #3 → … → #5 → #6 → #2 lő · 5 passz, 11,0 mp",
        "Szeged gólja — ? lő · passz nélkül"]
    # Az app tükre (court_geometry.goalBuildUpCaption) ugyanezt a három
    # esetet futtatja ugyanezekkel a várt feliratokkal.
    from pathlib import Path
    dart = (Path(__file__).resolve().parent.parent.parent / "client" /
            "test" / "court_geometry_test.dart").read_text(encoding="utf-8")
    for felirat in json.loads(r.stdout):
        assert f'"{felirat}"' in dart, felirat


def test_a_tomor_adat_es_a_vegpont_viszi_az_emberelonyt(tmp_path,
                                                        monkeypatch):
    """A tömör adat "powerplays" sorai a powerplay_moments szakaszai (7
    mezős alak); a /powerplay-moments végpont ugyanazt adja, 404."""
    from fastapi.testclient import TestClient
    from test_court3d import _kiallitasos_meccs

    from handball.api.app import create_app
    from handball.pipeline.court3d import powerplay_moments
    from handball.pipeline.view3d_html import _compact_data

    m = _kiallitasos_meccs()
    adat = _compact_data(m, None, {"home": [], "away": []},
                         {"home": [], "away": []})
    pm = powerplay_moments(m)
    assert len(adat["powerplays"]) == len(pm["moments"]) == 1
    r, w = adat["powerplays"][0], pm["moments"][0]
    assert len(r) == 7 and r[:6] == [w["s"], w["e"], 0, w["goals_up"],
                                     w["goals_down"], w["shots_up"]]
    assert len(r[6]) == len(w["goals"])
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    app = create_app()
    app.state.put_match(m)
    c = TestClient(app)
    v = c.get(f"/matches/{m.meta.match_id}/powerplay-moments").json()
    assert v["windows"] == 1
    assert c.get("/matches/nincs/powerplay-moments").status_code == 404


@pytest.mark.skipif(NODE is None, reason="nincs node a gépen")
def test_az_emberelony_jelzo_szovege():
    """Az élő jelző: ki van előnyben, ki hiányos, mennyi van hátra (p:mm,
    felfelé kerekítve), és az előny alatti állás a lejátszófejig — a
    későbbi gól még nem számít."""
    from handball.pipeline.view3d_html import view3d_html

    kod = _modul_szkript(view3d_html(_meccs()))
    i0 = kod.index("function emberSzoveg")
    i1 = kod.index("\n}\n", i0) + 2
    d = [30.0, 110.0, 0, 2, 1, 5, [[40.0, 1], [55.5, 0], [90.0, 1]]]
    esetek = [[d, 37.9], [d, 60.0], [d, 100.0],
              [[200.0, 290.4, 1, 0, 0, 0, []], 200.0]]
    js = (kod[i0:i1] + "\nconsole.log(JSON.stringify(" + json.dumps(esetek)
          + '.map(([d, t]) => emberSzoveg(d, t, "Szeged", "Veszprém"))));\n')
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [
        "Emberelőny: Szeged (Veszprém kiállítás miatt hiányos) · még 1:13 · "
        "az előny alatt eddig 0–0",
        "Emberelőny: Szeged (Veszprém kiállítás miatt hiányos) · még 0:50 · "
        "az előny alatt eddig 1–1",
        "Emberelőny: Szeged (Veszprém kiállítás miatt hiányos) · még 0:10 · "
        "az előny alatt eddig 2–1",
        "Emberelőny: Veszprém (Szeged kiállítás miatt hiányos) · még 1:31 · "
        "az előny alatt eddig 0–0"]
    # Az app tükre (court_geometry.powerplayCaption) ugyanezt a négy
    # esetet futtatja ugyanezekkel a várt szövegekkel.
    from pathlib import Path
    dart = (Path(__file__).resolve().parent.parent.parent / "client" /
            "test" / "court_geometry_test.dart").read_text(encoding="utf-8")
    for szoveg in json.loads(r.stdout):
        assert f'"{szoveg}"' in dart, szoveg


def test_a_klipek_kepernyo_a_kert_meccset_valasztja():
    """A Klipek képernyő a 3D jelenet-listából a NÉZETT meccsel nyílik:
    az initialMatchId-t a könyvtárban megkeresi, és azt választja (nem
    az első meccset) — a forrásban a választás ott van."""
    from pathlib import Path

    klip = (Path(__file__).resolve().parent.parent.parent / "client" / "lib"
            / "ui" / "clips_screen.dart").read_text(encoding="utf-8")
    assert "this.initialMatchId" in klip
    assert 'ms.any((e) => e["match_id"] == kert)' in klip


@pytest.mark.skipif(NODE is None, reason="nincs node a gépen")
def test_a_klip_munka_allapot_szovege():
    """A böngészős Klipek gomb állapota a /jobs válaszból: futás közben a
    haladás-üzenet, készen a motor összegzése ("kész: 5 klip …"), hibánál
    az üzenet vagy a hiba."""
    from handball.pipeline.view3d_html import view3d_html

    kod = _modul_szkript(view3d_html(_meccs()))
    i0 = kod.index("function klipAllapotSzoveg")
    i1 = kod.index("\n}\n", i0) + 2
    esetek = [None, {"status": "running", "message": "3/12 jelenet"},
              {"status": "done", "message": "kész: 5 klip"},
              {"status": "error", "message": "hiba: nincs videó"},
              {"status": "error", "error": "x"}]
    js = (kod[i0:i1] + "\nconsole.log(JSON.stringify(" + json.dumps(esetek)
          + ".map(klipAllapotSzoveg)));\n")
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == ["", "Klipek vágása… 3/12 jelenet",
                                    "kész: 5 klip", "hiba: nincs videó",
                                    "hiba: x"]


@pytest.mark.skipif(NODE is None, reason="nincs node a gépen")
def test_a_vr_kontroller_gomb_el_erzekelese():
    """A kontroller-gomb él-érzékelése: egy lenyomás EGY lépés — a nyomva
    tartott gomb nem pörget, az elengedés után az új lenyomás megint
    lép; a két kontroller és a gombok egymástól függetlenek."""
    from handball.pipeline.view3d_html import view3d_html

    kod = _modul_szkript(view3d_html(_meccs()))
    i0 = kod.index("const vrGombElozo = new Map();")
    i1 = kod.index("\n}\n", kod.index("function vrGombEl")) + 2
    js = (kod[i0:i1] + """
const ki = [];
for (const [k, i, l] of [["bal1", 4, true], ["bal1", 4, true], ["bal1", 4, false],
                         ["bal1", 4, true], ["jobb2", 4, true], ["bal1", 5, true],
                         ["bal1", 5, true], ["bal1", 4, false], ["bal1", 4, true]])
  ki.push(vrGombEl(k, i, l));
console.log(JSON.stringify(ki));
""")
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [True, False, False, True, True, True,
                                    False, False, True]

def _fal_dart_sorok() -> list:
    """A Dart-tükör (court_geometry.wallGapSegments) esettáblájának sorai
    — a várt értékek a backend wall_gap_segments-éből (rögzített mag,
    holtversenyes y-okkal, mért/becsült és kapus játékosokkal)."""
    import random

    from handball.models.tracking import (PlayerPosition, PositionSource,
                                          Team)
    from handball.pipeline.court3d import wall_gap_segments

    def b(v):
        return "true" if v else "false"

    rnd = random.Random(23)
    sorok = []
    for _ in range(24):
        goal_x = rnd.choice([0.0, 40.0])
        hazai = rnd.random() < 0.5
        jat = []
        for _ in range(rnd.randint(4, 10)):
            x = round(abs(goal_x - rnd.uniform(1, 14)), 1)
            y = float(rnd.randint(2, 18)) if rnd.random() < 0.3 \
                else round(rnd.uniform(1, 19), 1)
            sajat = rnd.random() < 0.8
            jat.append((hazai if sajat else not hazai, x, y,
                        rnd.random() < 0.9, rnd.random() < 0.06))
        py = wall_gap_segments(
            [PlayerPosition(track_id=i, team=Team.HOME if h else Team.AWAY,
                            x=x, y=y,
                            source=(PositionSource.MEASURED if m
                                    else PositionSource.ESTIMATED),
                            confidence=1.0, role="kapus" if k else None)
             for i, (h, x, y, m, k) in enumerate(jat)],
            Team.HOME if hazai else Team.AWAY, goal_x)
        bemenet = ("[" + ", ".join(f"({b(h)}, {x}, {y}, {b(m)}, {b(k)})"
                                   for h, x, y, m, k in jat)
                   + f"], {b(hazai)}, {goal_x}")
        if py is None:
            sorok.append(f"expect(wallGapSegments({bemenet}), isNull);")
        else:
            fal = ", ".join(f"({float(x)}, {float(y)})" for x, y in py["wall"])
            szeles = ", ".join(b(w) for w in py["wide"])
            sorok.append(f"_falEllenoriz({bemenet}, [{fal}], [{szeles}], "
                         f"{py['max_index']}, {py['max_gap']});")
    return sorok


def test_az_app_fal_resei_a_backend_tablajat_futtatjak():
    """A Dart fal-rés tükrének tesztje (court_geometry_test.dart) a backend
    wall_gap_segments-éből számolt esettáblát futtatja — a sorokat itt
    újraszámoljuk és megkeressük a Dart-tesztben; a Dart-küszöbök a
    backend konstansai."""
    from pathlib import Path

    from handball.pipeline.defense import (WALL_GAP_DEPTH_M, WALL_GAP_M,
                                           WALL_GAP_MIN_DEFENDERS)

    gyoker = Path(__file__).resolve().parent.parent.parent
    teszt = (gyoker / "client" / "test" /
             "court_geometry_test.dart").read_text(encoding="utf-8")
    sorok = _fal_dart_sorok()
    assert sum(1 for s in sorok if s.startswith("_falEllenoriz")) >= 8
    for sor in sorok:
        assert sor in teszt, sor
    geo = (gyoker / "client" / "lib" / "ui" /
           "court_geometry.dart").read_text(encoding="utf-8")
    assert f"const double wallGapM = {WALL_GAP_M};" in geo
    assert f"const double wallGapDepthM = {WALL_GAP_DEPTH_M};" in geo
    assert f"const int wallGapMinDefenders = {WALL_GAP_MIN_DEFENDERS};" in geo

def test_az_oldal_sablonja_escape_nelkul_toltodik():
    """A böngészős oldal sablonja NEM raw string: egy egyszeres "\\n" a
    beszúrt JS-ben valódi sortöréssé válik (az egész modul-szkript
    elhal), az egyszeres "\\s" DeprecationWarning. A modul
    figyelmeztetés nélkül importálható — a sablonba kettőzött escape
    kell."""
    import importlib
    import warnings

    import handball.pipeline.view3d_html as v

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        importlib.reload(v)

def _modul_szkript(oldal: str) -> str:
    m = re.search(r'<script type="module">(.*?)</script>', oldal, re.S)
    assert m, "nincs modul-szkript"
    return m.group(1)


@pytest.mark.skipif(NODE is None, reason="nincs node a gépen")
def test_az_oldal_szkriptje_szintaktikailag_ep():
    """A beágyazott JS parse-olható (node --check): egy elgépelt zárójel
    a teljes 3D nézetet vinné el, és ezt Python-teszt mással nem látja."""
    from handball.pipeline.view3d_html import view3d_html

    kod = _modul_szkript(view3d_html(_meccs()))
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False,
                                     encoding="utf-8") as f:
        f.write(kod)
        ut = f.name
    try:
        r = subprocess.run([NODE, "--check", ut], capture_output=True,
                           text=True, timeout=60)
        assert r.returncode == 0, r.stderr[-2000:]
    finally:
        os.unlink(ut)


@pytest.mark.skipif(NODE is None, reason="nincs node a gépen")
def test_a_bongeszo_ugyanazt_meri_mint_a_backend():
    """A lövés-mérés JS-tükre a pálya rácsán (és a kapuk mögött) a
    `court3d.shot_geometry` számait adja — a két nézet nem mondhat mást."""
    from handball.pipeline.court3d import shot_geometry
    from handball.pipeline.view3d_html import LOVES_MERES_JS

    pontok = [(x * 0.5, y * 0.5) for x in range(-4, 85, 3)
              for y in range(-2, 43, 3)]
    pontok += [(0.0, 8.5), (40.0, 11.5), (20.0, 10.0), (6.0, 10.0)]
    kod = ("const H = 40, W = 20, KAPU_SZ = 3;\n" + LOVES_MERES_JS +
           "\nconst P = " + json.dumps(pontok) + ";\n"
           "console.log(JSON.stringify(P.map(p => lovesMeres(p[0], p[1]))));\n")
    r = subprocess.run([NODE, "-e", kod], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    js = json.loads(r.stdout)
    for (x, y), j in zip(pontok, js):
        py = shot_geometry(x, y)
        assert j["kapu"] == py["goal"] and j["gx"] == py["goal_x"], (x, y)
        assert abs(j["tav"] - py["distance_m"]) < 0.01, (x, y)
        assert abs(j["kapufa"] - py["post_distance_m"]) < 0.01, (x, y)
        assert abs(j["szog"] - py["angle_deg"]) < 0.06, (x, y)
        assert j["sav"] == py["zone"], (x, y, j["sav"], py["zone"])


def test_a_vedekezes_idovonal_vegpont(tmp_path, monkeypatch):
    """Az appbeli 3D pálya a /defence-timeline végpontból kapja az élő
    falat és a sablonokat; ismeretlen meccsre 404."""
    from fastapi.testclient import TestClient

    from handball.api.app import create_app

    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    app = create_app()
    app.state.put_match(_meccs())
    c = TestClient(app)
    r = c.get("/matches/v3t/defence-timeline")
    assert r.status_code == 200
    d = r.json()
    assert d["rows"][0]["defending"] == "away" and d["rows"][0]["label"] == "6-0"
    assert d["rows"][0]["goal_x"] == 40.0
    assert set(d["formations"]) == {"6-0", "5-1", "4-2", "3-2-1"}
    # Feltörés csapatonként: lista (a kis fixtúrán üres is lehet).
    assert set(d["breakpoints"]) == {"home", "away"}
    assert all(isinstance(v, list) for v in d["breakpoints"].values())
    assert set(d["stoppers"]) == {"home", "away"}
    assert all(isinstance(v, list) for v in d["stoppers"].values())
    assert c.get("/matches/v3t/defence-timeline").json() == d  # tárból is
    assert c.get("/matches/nincs/defence-timeline").status_code == 404


def test_az_appbeli_3d_a_backend_sablonjait_es_mereset_tukrozi():
    """Az appbeli 3D pálya (Dart) ugyanazokat a falsablonokat és lövés-
    mérési képletet viszi, mint a backend `court3d` — a forrást vetjük
    össze, hogy a két nézet ne mondhasson mást."""
    from pathlib import Path

    from handball.pipeline.court3d import FORMATION_TEMPLATES

    gyoker = Path(__file__).resolve().parent.parent.parent
    geo = (gyoker / "client" / "lib" / "ui"
           / "court_geometry.dart").read_text(encoding="utf-8")
    for nev, pontok in FORMATION_TEMPLATES.items():
        m = re.search(r'"' + re.escape(nev) + r'": \[(.*?)\],', geo)
        assert m, f"a Dart-sablonból hiányzik: {nev}"
        dart = [tuple(float(v) for v in par)
                for par in re.findall(r"\(([\d.]+), ([\d.]+)\)", m.group(1))]
        assert dart == [tuple(p) for p in pontok], nev
    assert "Rect? breakpointZoneBand(String? sav, double goalX)" in geo
    for jel in ("ShotGeometry shotGeometry", "math.acos(c)",
                "y.clamp(y1, y2)", '"kapuelőtér"', '"6–9 m"',
                '"9 m-en túl"', "formationDeviation"):
        assert jel in geo, jel

    kepernyo = (gyoker / "client" / "lib" / "ui"
                / "court3d_screen.dart").read_text(encoding="utf-8")
    for jel in ("_keringValt", "_szemValasztas", "_meresKoppintas",
                "onDoubleTap", "onScaleUpdate", "fetchDefenceTimeline",
                "formationPositions", "class _Vetites", "Kapu-szög",
                "LogicalKeyboardKey.keyO", "LogicalKeyboardKey.escape",
                "identical(j, rejtett)", "substitutionLineX",
                "_lovesKoppintas", "_lathatoLovesek", "class _LovesJel",
                "fetchXg", "Lövéstérkép: ki", "_labdaNyom", "Labda-nyom",
                "computeTeamHeatmap", "Hőtérkép: ki", "_tavTabla",
                "_tavUgrasM = 3.0", "km/h", "_passzok", "Passzok: ki",
                "class _PasszVonal", "_passzVonalak", 'q["kamera"]',
                'q["hoter"]', 'q["loves"]', 'q["passz"]', 'q["fal"]',
                "_mostT(m) / fpsB", "this.lovesTerkep", "_falBreak",
                '"Feltörés: ${f.first["hol"]}', "breakpointZoneBand",
                "_falStop", '"Megállítás: ${st.first["hol"]}',
                "_passzsavok(", "passzsavok: _passzsav", "Passzsávok",
                "fetchDecisionMoments", "_dontesUgras", "_aktivDontes",
                "fetchFreeShots", "_szabadUgras", "_aktivSzabad",
                "szabad: _aktivSzabad(m)",
                "fetchTurnoverMoments", "_eladasUgras", "_aktivEladas",
                "wallGapSegments", "falresek: _falresek(m, allapot)?.$1",
                "_jelenetCsapat", '_szurt(_szabadok, "defending")',
                "_jelenetListaPanel(m)", "sceneRows(", "_jelenetUgras(m, r)",
                "fetchGoalBuildUps", "_golUgras", "_aktivGol",
                "fetchPowerplayMoments", "_emberUgras", "_emberJelzo(m)",
                # a jelenet-listából a Klipek képernyő a nézett meccsel
                "ClipsScreen(", "initialMatchId: _matchId",
                "LogicalKeyboardKey.keyN", "_jelenetLep(m,",
                '"bad_decision", "free_shot", "costly_turnover"',
                "powerplayCaption(",
                "gol: _aktivGol(m)", "goalBuildUpCaption(",
                '"Jelenet-lista"',
                '_szurt(_dontesek, "team")', '_szurt(_eladasok, "team")',
                "Hibák: mindkét csapat",
                '"Fal-rések"', 'q["passzsav"]', 'q["falres"]',
                "eladas: _aktivEladas(m)", "_pillanatFeliratok(m)",
                "dontes: _aktivDontes(m)",
                "feltoresSav: fal.$3"):
        assert jel in kepernyo, jel
    # A kör sugara ugyanaz a képlet, mint a böngészőben (0,22 + 0,5·xG).
    assert "0.22 + 0.5 *" in kepernyo and "0.22 + 0.5 * Math.min" in \
        __import__("handball.pipeline.view3d_html",
                   fromlist=["view3d_html"]).view3d_html(_meccs())


def test_a_tomor_adat_es_a_vegpont_viszi_a_lerohanasokat(tmp_path,
                                                          monkeypatch):
    """A tömör adat "fast_breaks" sorai a fast_break_moments lerohanásai
    (15 mezős alak: a 2. elem a VÉDEKEZŐ csapat — a szűrőhöz —, az út, a
    lövés, a kapu, a labda és a jelenet vége); a /fast-break-moments
    végpont ugyanazt adja, ismeretlen meccsre 404."""
    from fastapi.testclient import TestClient

    from handball.api.app import create_app
    from handball.pipeline.court3d import fast_break_moments
    from handball.pipeline.view3d_html import _compact_data
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=300, fps=25.0, seed=7,
                              shots_per_min=8)
    adat = _compact_data(m, None, {"home": [], "away": []},
                         {"home": [], "away": []})
    fb = fast_break_moments(m)
    assert len(adat["fast_breaks"]) == len(fb["moments"]) > 0
    for r, x in zip(adat["fast_breaks"], fb["moments"]):
        assert len(r) == 15 and r[0] == x["s"]
        assert r[1] == (1 if x["defending"] == "home" else 0)
        assert r[2] == x["shooter_jersey"]
        assert r[3] == {"first": "e", "second": "m", None: None}[x["wave"]]
        assert r[6] == {"goal": "g", "shot": "l", None: None}[x["outcome"]]
        assert r[7] == x["path"] and r[10:12] == x["goal"]
        assert r[8:10] == (x["shot"] or [None, None])
        assert r[14] == (x["shot_s"] if x["shot_s"] is not None else x["e"])
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    app = create_app()
    app.state.put_match(m)
    c = TestClient(app)
    v = c.get(f"/matches/{m.meta.match_id}/fast-break-moments").json()
    assert len(v["moments"]) == len(fb["moments"])
    assert v["breaks"] == fb["breaks"] and v["goals"] == fb["goals"]
    assert c.get("/matches/nincs/fast-break-moments").status_code == 404


@pytest.mark.skipif(NODE is None, reason="nincs node a gépen")
def test_a_lerohanas_felirata():
    """A lerohanás felirata: a támadó csapat, a befejező mezszáma, az első
    ember / második hullám, az elszökés, az időtartam és a kimenet; a
    hiányzó részek kimaradnak. Az app tükre (court_geometry.fastBreakCaption)
    ugyanezt a három esetet futtatja ugyanezekkel a feliratokkal."""
    from handball.pipeline.view3d_html import view3d_html

    kod = _modul_szkript(view3d_html(_meccs()))
    i0 = kod.index("function kontraFelirat")
    i1 = kod.index("\n}\n", i0) + 2
    # [s, a védekező hazai?, mez, hullám, elszökött, hossz, kimenet, …]
    esetek = [
        [10.0, 0, 7, "m", 1, 4.2, "g", [], None, None, 40, 10, 20, 10, 14.0],
        [20.0, 1, 13, "e", 0, 2.25, "l", [], None, None, 0, 10, 20, 10, 22.0],
        [30.0, 0, None, None, None, 3.0, None, [], None, None, 40, 10, None,
         None, 33.0],
    ]
    js = (kod[i0:i1] + "\nconsole.log(JSON.stringify(" + json.dumps(esetek)
          + '.map(d => kontraFelirat(d, "Szeged", "Veszprém"))));\n')
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [
        "Lerohanás (Szeged): #7 fejezi be · második hullám · elszökött "
        "emberrel · 4,2 mp · GÓL",
        "Lerohanás (Veszprém): #13 fejezi be · első ember · együtt felfutva "
        "· 2,3 mp · lövés",
        "Lerohanás (Szeged): 3,0 mp · lövés nélkül"]
    from pathlib import Path
    dart = (Path(__file__).resolve().parent.parent.parent / "client" /
            "test" / "court_geometry_test.dart").read_text(encoding="utf-8")
    for felirat in json.loads(r.stdout):
        assert f'"{felirat}"' in dart, felirat


def test_a_lerohanas_lapozo_az_oldalon_es_az_appban():
    """A Lerohanások lapozó a böngészős oldalon (sor, felirat-doboz, a
    rajzoló és a felirat-függvény, a VR-tábla forrása, a súgó) és az
    appban (lapozó, szűrt lista, felirat, festő)."""
    from pathlib import Path

    from handball.pipeline.view3d_html import view3d_html

    oldal = view3d_html(_meccs())
    for kell in ('id="kontraElozo"', 'id="kontraKov"', 'id="kontraInfo"',
                 '<div id="kontraFelirat"></div>', "function kontraFelirat",
                 "function kontraFrissit", "function kontraUgras",
                 "const KONTRAK = ADAT.fast_breaks || [];",
                 "kontraFrissit(t)", '"kontraFelirat", "kapottFelirat", "hetesFelirat", "emberJelzo"',
                 "Lerohanások ◀ ▶", "ADAT.home, ADAT.away, szurt(KONTRAK)",
                 'k: "#59d98c"'):
        assert kell in oldal, kell
    dart = (Path(__file__).resolve().parent.parent.parent / "client" / "lib"
            / "ui" / "court3d_screen.dart").read_text(encoding="utf-8")
    for kell in ('tooltip: "Következő lerohanás"', "_kontrakSz",
                 '_szurt(_kontrak, "defending")', "fastBreakCaption(k,",
                 "kontra: _aktivKontra(m),", "fetchFastBreakMoments(id)",
                 "buildDemoFastBreaks(_match!)", "m.meta.awayTeam, _kontrakSz,"):
        assert kell in dart, kell


def test_a_tomor_adat_es_a_vegpont_viszi_a_kapott_golokat(tmp_path,
                                                          monkeypatch):
    """A tömör adat "conceded_goals" sorai a conceded_goal_moments kapott
    góljai (20 mezős alak: a 2. elem a VÉDEKEZŐ csapat — a szűrőhöz —, a
    lövő, a sáv kódja, a védő, a kapus, az xG, a kapu, a kocka); a
    /conceded-goals végpont ugyanazt adja, ismeretlen meccsre 404."""
    from fastapi.testclient import TestClient

    from handball.api.app import create_app
    from handball.pipeline.court3d import conceded_goal_moments
    from handball.pipeline.view3d_html import _compact_data
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=120, fps=25.0, seed=5,
                              shots_per_min=8)
    adat = _compact_data(m, None, {"home": [], "away": []},
                         {"home": [], "away": []})
    cg = conceded_goal_moments(m)
    assert len(adat["conceded_goals"]) == len(cg["moments"]) > 0
    sav = {"kapuelőtér": 0, "6–9 m": 1, "9 m-en túl": 2}
    for r, x in zip(adat["conceded_goals"], cg["moments"]):
        assert len(r) == 20 and r[0] == x["s"]
        assert r[1] == (1 if x["defending"] == "home" else 0)
        assert r[2] == x["shooter_jersey"] and r[3:5] == x["shooter"]
        assert r[5] == sav[x["zone"]] and r[6] == x["angle_deg"]
        assert r[8:10] == (x["defender"] or [None, None])
        assert r[10] == x["def_dist"]
        assert r[12:14] == (x["keeper"] or [None, None])
        assert r[14] == x["keeper_depth"] and r[16] == x["xg"]
        assert r[17:19] == x["goal"] and r[19] == x["t"]
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    app = create_app()
    app.state.put_match(m)
    c = TestClient(app)
    v = c.get(f"/matches/{m.meta.match_id}/conceded-goals").json()
    assert len(v["moments"]) == len(cg["moments"])
    assert v["conceded"] == cg["conceded"]
    assert c.get("/matches/nincs/conceded-goals").status_code == 404


@pytest.mark.skipif(NODE is None, reason="nincs node a gépen")
def test_a_kapott_gol_felirata():
    """A kapott gól felirata: a védekező és a lövő csapat, a lövő
    mezszáma, a sáv és a kapu-szög, a védő távolsága (szabadon), a kapus
    mélysége (kint / a vonalon), az xG; a nem mérhető részek szöveggel. Az
    app tükre (court_geometry.concededGoalCaption) ugyanezt a három esetet
    futtatja ugyanezekkel a feliratokkal."""
    from handball.pipeline.view3d_html import view3d_html

    kod = _modul_szkript(view3d_html(_meccs()))
    i0 = kod.index("function kapottFelirat")
    i1 = kod.index("\n}\n", i0) + 2
    # [s, a védekező hazai?, mez, lövő x, y, sáv, szög, táv, védő x, y,
    #  védő-táv, szabad, kapus x, y, mélység, kint, xG, kapu x, y, kocka]
    esetek = [
        [7.08, 0, 10, 27.72, 10.95, 2, 13.8, 12.32, 33.93, 10.55, 6.22, 1,
         39.26, 10.57, 0.93, 0, 0.09, 40, 10, 177],
        [20.0, 1, 7, 5.0, 10.0, 0, 64.25, 5.0, 5.5, 10.2, 0.7, 0,
         1.6, 10.8, 1.8, 1, 0.55, 0, 10, 500],
        [30.0, 0, None, 32.0, 8.0, 1, 30.0, 8.2, None, None, None, None,
         None, None, None, None, 0.3, 40, 10, 750],
    ]
    js = (kod[i0:i1] + "\nconsole.log(JSON.stringify(" + json.dumps(esetek)
          + '.map(d => kapottFelirat(d, "Szeged", "Veszprém"))));\n')
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [
        "Kapott gól (Veszprém): Szeged #10 · 9 m-en túl, kapu-szög 13,8° · "
        "védő 6,2 m-re — szabadon · kapus 0,9 m-re a vonalon · xG 0,09",
        "Kapott gól (Szeged): Veszprém #7 · kapuelőtér, kapu-szög 64,3° · "
        "védő 0,7 m-re · kapus 1,8 m-re kint · xG 0,55",
        "Kapott gól (Veszprém): Szeged · 6–9 m, kapu-szög 30,0° · védő nem "
        "mérhető · kapus nem mérhető · xG 0,30"]
    from pathlib import Path
    dart = (Path(__file__).resolve().parent.parent.parent / "client" /
            "test" / "court_geometry_test.dart").read_text(encoding="utf-8")
    for felirat in json.loads(r.stdout):
        assert f'"{felirat}"' in dart, felirat


def test_a_kapott_golok_lapozo_az_oldalon_es_az_appban():
    """A Kapott gólok lapozó a böngészős oldalon (sor, felirat-doboz, a
    rajzoló és a felirat-függvény, a VR-tábla forrása, a súgó, a lista
    hetedik listája) és az appban (lapozó, szűrt lista, felirat, festő)."""
    from pathlib import Path

    from handball.pipeline.view3d_html import view3d_html

    oldal = view3d_html(_meccs())
    for kell in ('id="kapottElozo"', 'id="kapottKov"', 'id="kapottInfo"',
                 '<div id="kapottFelirat"></div>', "function kapottFelirat",
                 "function kapottFrissit", "function kapottUgras",
                 "const KAPOTTAK = ADAT.conceded_goals || [];",
                 "kapottFrissit(t)", '"kapottFelirat", "hetesFelirat", "emberJelzo"',
                 "Kapott gólok ◀ ▶", "szurt(KONTRAK), szurt(KAPOTTAK)",
                 'kg: "#c084fc"', "szabadGolIdok"):
        assert kell in oldal, kell
    dart = (Path(__file__).resolve().parent.parent.parent / "client" / "lib"
            / "ui" / "court3d_screen.dart").read_text(encoding="utf-8")
    for kell in ('tooltip: "Következő kapott gól"', "_kapottakSz",
                 '_szurt(_kapottak, "defending")', "concededGoalCaption(g,",
                 "kapott: _aktivKapott(m),", "fetchConcededGoals(id)",
                 "buildDemoConcededGoals(_match!)", "_kontrakSz, _kapottakSz)"):
        assert kell in dart, kell



def test_a_jelenet_lista_azonos_pillanat_turese_tukrozve():
    """A jelenet-lista "ugyanaz a pillanat" tűrése (court3d.SCENE_SAME_MOMENT_S)
    a böngésző (JL_AZONOS_S) és az app (sceneSameMomentS) tükrében is
    ugyanaz a szám — egy oldalon változtatva a listák széttartanának."""
    import re
    from pathlib import Path

    from handball.pipeline.court3d import SCENE_SAME_MOMENT_S
    from handball.pipeline.view3d_html import JELENETLISTA_JS

    js = re.search(r"const JL_AZONOS_S = ([0-9.]+);", JELENETLISTA_JS)
    assert js and float(js.group(1)) == SCENE_SAME_MOMENT_S
    assert "< JL_AZONOS_S" in JELENETLISTA_JS
    dart = (Path(__file__).resolve().parent.parent.parent / "client" / "lib"
            / "ui" / "court_geometry.dart").read_text(encoding="utf-8")
    d = re.search(r"const double sceneSameMomentS = ([0-9.]+);", dart)
    assert d and float(d.group(1)) == SCENE_SAME_MOMENT_S
    assert "< sceneSameMomentS" in dart



def test_a_tomor_adat_es_a_vegpont_viszi_a_heteseket(tmp_path, monkeypatch):
    """A tömör adat "sevens" sorai a seven_meter_moments hetesei (17 mezős
    alak: a pont, a dobó, a kimenet- és az irány-kód, a cél, a kapus, a
    kapu, a lövés ideje); a /seven-meter-moments végpont ugyanazt adja,
    ismeretlen meccsre 404."""
    from fastapi.testclient import TestClient
    from test_court3d import _hetes_meccs

    from handball.api.app import create_app
    from handball.pipeline.court3d import seven_meter_moments
    from handball.pipeline.view3d_html import _compact_data

    m = _hetes_meccs()
    adat = _compact_data(m, None, {"home": [], "away": []},
                         {"home": [], "away": []})
    sm = seven_meter_moments(m)
    assert len(adat["sevens"]) == len(sm["moments"]) > 0
    for r, x in zip(adat["sevens"], sm["moments"]):
        assert len(r) == 17 and r[0] == x["s"]
        assert r[1] == (1 if x["team"] == "home" else 0)
        assert r[3:5] == (x["spot"] or [None, None])
        assert r[7] == {"gól": "g", "védés": "v", "kihagyva": "k"}.get(x["outcome"], "?")
        assert r[8] == {"bal": 0, "közép": 1, "jobb": 2}.get(x["irany"])
        assert r[9:11] == (x["aim"] or [None, None])
        assert r[13] == x["keeper_depth"] and r[14:16] == x["goal"]
        assert r[16] == x["shot_s"]
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    app = create_app()
    app.state.put_match(m)
    c = TestClient(app)
    v = c.get(f"/matches/{m.meta.match_id}/seven-meter-moments").json()
    assert len(v["moments"]) == len(sm["moments"])
    assert v["attempts"] == sm["attempts"]
    assert c.get("/matches/nincs/seven-meter-moments").status_code == 404


@pytest.mark.skipif(NODE is None, reason="nincs node a gépen")
def test_a_hetes_felirata():
    """A hétméteres felirata: a dobó csapat, a mezszám, az irány, a
    kimenet és a kapus mélysége; a hiányzó részek kimaradnak vagy
    szöveggel. Az app tükre (court_geometry.sevenMeterCaption) ugyanezt a
    három esetet futtatja ugyanezekkel a feliratokkal."""
    from handball.pipeline.view3d_html import view3d_html

    kod = _modul_szkript(view3d_html(_meccs()))
    i0 = kod.index("function hetesFelirat")
    i1 = kod.index("\n}\n", i0) + 2
    # [s, hazai, mez, pont x, y, dobó x, y, kim, irány, cél x, y, kapus x,
    #  y, mélység, kapu x, y, lövés mp]
    esetek = [
        [17.72, 1, 7, 33, 10, 32.6, 10, "g", 1, 40, 10, 39.1, 9.6, 0.98,
         40, 10, 18.3],
        [40.0, 0, 13, 7, 10, 7.4, 10, "v", 0, 0, 11, 1.2, 10.4, 1.26, 0,
         10, 41.0],
        [60.0, 1, None, 33, 10, None, None, "?", None, None, None, None,
         None, None, 40, 10, None],
    ]
    js = (kod[i0:i1] + "\nconsole.log(JSON.stringify(" + json.dumps(esetek)
          + '.map(d => hetesFelirat(d, "Szeged", "Veszprém"))));\n')
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [
        "Hetes (Szeged): #7 · középre · GÓL · kapus 1,0 m-re a kaputól",
        "Hetes (Veszprém): #13 · balra · védés · kapus 1,3 m-re a kaputól",
        "Hetes (Szeged): kimenet ismeretlen · kapus nem mérhető"]
    from pathlib import Path
    dart = (Path(__file__).resolve().parent.parent.parent / "client" /
            "test" / "court_geometry_test.dart").read_text(encoding="utf-8")
    for felirat in json.loads(r.stdout):
        assert f'"{felirat}"' in dart, felirat


def test_a_hetes_lapozo_az_oldalon_es_az_appban():
    """A Hétméteresek lapozó a böngészős oldalon (sor, felirat-doboz, a
    rajzoló és a felirat-függvény, a VR-tábla forrása, a súgó) és az
    appban (lapozó, felirat, festő, demó)."""
    from pathlib import Path

    from handball.pipeline.view3d_html import view3d_html

    oldal = view3d_html(_meccs())
    for kell in ('id="hetesElozo"', 'id="hetesKov"', 'id="hetesInfo"',
                 '<div id="hetesFelirat"></div>', "function hetesFelirat",
                 "function hetesFrissit", "function hetesUgras",
                 "const HETESEK = ADAT.sevens || [];", "hetesFrissit(t)",
                 '"hetesFelirat", "emberJelzo"', "Hétméteresek ◀ ▶"):
        assert kell in oldal, kell
    dart = (Path(__file__).resolve().parent.parent.parent / "client" / "lib"
            / "ui" / "court3d_screen.dart").read_text(encoding="utf-8")
    for kell in ('tooltip: "Következő hétméteres"', "_aktivHetes(m)",
                 "sevenMeterCaption(h,", "hetes: _aktivHetes(m),",
                 "fetchSevenMeterMoments(id)", "buildDemoSevens(_match!)"):
        assert kell in dart, kell



def test_a_jelenet_feliratok_egy_oszlopban_rendezodnek():
    """A jelenet-feliratok (döntés, szabad lövő, labdavesztés, gól-akció,
    lerohanás, kapott gól, hetes) egy közös oszlopban állnak: a láthatók
    fentről, hézag nélkül rendeződnek, és egyiknek sincs rögzített
    függőleges helye (korábban egy magányos felirat a képernyő közepén
    lógott, fölötte üres sávokkal); az oszlop nem fogja el a kattintást."""
    import re

    from handball.pipeline.view3d_html import view3d_html

    oldal = view3d_html(_meccs())
    oszlop = oldal.split('<div id="feliratOszlop">', 1)[1].split("\n</div>\n", 1)[0]
    for fid in ("dontesFelirat", "szabadFelirat", "eladasFelirat",
                "golFelirat", "kontraFelirat", "kapottFelirat",
                "hetesFelirat"):
        assert f'<div id="{fid}"></div>' in oszlop, fid
        css = re.search(r" #" + fid + r"\{([^}]*)\}", oldal).group(1)
        assert "position:fixed" not in css and "top:" not in css, fid
    css = re.search(r" #feliratOszlop\{([^}]*)\}", oldal).group(1)
    assert "flex-direction:column" in css and "pointer-events:none" in css



def test_a_3d_oldal_rajz_csoportjai_felszabaditjak_a_geometriat():
    """A képkockánként újrarajzolt rétegek a levett geometriát és anyagot
    felszabadítják (csoportUrit — dispose), és a gól-akció, a lerohanás, a
    kapott gól és a hetes csak jelenet-váltáskor rajzol újra; régi,
    felszabadítás nélküli ürítés nem maradt."""
    import re

    from handball.pipeline.view3d_html import view3d_html

    oldal = view3d_html(_meccs())
    assert "function csoportUrit(cs)" in oldal
    assert "x.geometry.dispose()" in oldal and "q.dispose()" in oldal
    assert not re.search(r"while \(\w+\.children\.length\) \w+\.remove", oldal)
    for cs in ("golCsoport", "kontraCsoport", "kapottCsoport", "hetesCsoport"):
        assert f"if ({cs}.userData.kesz && {cs}.userData.d === d) return {cs}.userData.szoveg;" in oldal, cs



def test_a_jelenet_lista_videozando_szuroje():
    """A tömör adat "key_scenes" párjai a kulcs-jelenetek (court3d.
    key_scene_rows) — és mind megvan a jelenet-lista sorai közt (ugyanaz a
    típus és idő); az oldalon a "Videózandó" szűrő a listára, az N/P-re és
    a linkre is hat; az appban a szűrő-chip, a /key-scenes és a kezdőlap
    bekapcsolt nyitása."""
    from pathlib import Path

    from handball.pipeline.court3d import (conceded_goal_moments,
                                           decision_moments,
                                           fast_break_moments,
                                           free_shot_moments, key_scene_rows,
                                           scene_rows, turnover_moments)
    from handball.pipeline.view3d_html import _compact_data, view3d_html
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=180, fps=25.0, seed=5,
                              shots_per_min=8)
    adat = _compact_data(m, None, {"home": [], "away": []},
                         {"home": [], "away": []})
    ks = key_scene_rows(m)["rows"]
    assert adat["key_scenes"] == [[r["s"], r["tipus"]] for r in ks] and ks
    osszes = {(r["tipus"], r["s"]) for r in scene_rows(
        decision_moments(m)["moments"], free_shot_moments(m)["moments"],
        turnover_moments(m)["moments"], m.meta.home_team, m.meta.away_team,
        fast_break_moments(m)["moments"], conceded_goal_moments(m)["moments"])}
    assert {(t, s) for s, t in adat["key_scenes"]} <= osszes
    oldal = view3d_html(_meccs())
    for kell in ("const KULCS = new Set(", "function kulcsSzur(sorok)",
                 'kc.id = "jelenetKulcs"', "kulcsSzur(jelenetSorok(",
                 'q.set("kulcs", "1")', 'v("kulcs") === "1"'):
        assert kell in oldal, kell
    # A lista, az N/P és a vetítés közös forrása (jelenetSorokSzurt).
    assert oldal.count("kulcsSzur(jelenetSorok(") == 1
    gyoker = Path(__file__).resolve().parent.parent.parent / "client" / "lib" / "ui"
    palya = (gyoker / "court3d_screen.dart").read_text(encoding="utf-8")
    for kell in ("final bool csakVideozando;", "fetchKeyScenes(id)",
                 "_kulcsSzur(sceneRows(", '"Videózandó (${_kulcsJelenetek.length})"'):
        assert kell in palya, kell
    assert palya.count("_kulcsSzur(sceneRows(") == 1  # a közös _jelenetSorok
    assert "csakVideozando: true" in (gyoker / "dashboard_screen.dart").read_text(
        encoding="utf-8")



def test_a_jelenet_vetites_a_lista_sorain_lep():
    """Vetítés: a jelenet a pillanata után court3d.SCENE_REEL_TAIL_S mp-ig
    fut (a böngésző a sablonba írva, az app tükrében ugyanaz a szám), aztán
    a lista következő sora jön. Az oldal a szűrt sorok közös forrásából
    lép, a hurok a léptetés után hívja; a gomb, a V billentyű, a
    VR-kontroller és a felirat-oszlop (VR-tábla) jelzője megvan; az app a
    tickből lép, és a V és a fejléc-gomb kapcsolja."""
    import re
    from pathlib import Path

    from handball.pipeline.court3d import SCENE_REEL_TAIL_S
    from handball.pipeline.view3d_html import view3d_html

    oldal = view3d_html(_meccs())
    assert "__JL_VETITES_S__" not in oldal
    js = re.search(r"const JL_VETITES_S = ([0-9.]+);", oldal)
    assert js and float(js.group(1)) == SCENE_REEL_TAIL_S
    for kell in ('vb.id = "vetitesGomb"', 'e.code === "KeyV"',
                 "vetitesFrissit(t0, ido);", '<div id="vetitesJelzo"></div>',
                 '["vetitesJelzo", ', "vrGombEl(kulcs, 3, nyom(3))",
                 "vetitesSor = r; vetitesJelzoFrissit();",
                 "const hatar = vetitesVeg(vetitesSor);"):
        assert kell in oldal, kell
    # A lista, az N/P és a vetítés ugyanazokon a sorokon.
    assert oldal.count("= jelenetSorokSzurt();") >= 4
    ui = Path(__file__).resolve().parent.parent.parent / "client" / "lib" / "ui"
    d = re.search(r"const double sceneReelTailS = ([0-9.]+);",
                  (ui / "court_geometry.dart").read_text(encoding="utf-8"))
    assert d and float(d.group(1)) == SCENE_REEL_TAIL_S
    palya = (ui / "court3d_screen.dart").read_text(encoding="utf-8")
    for kell in ("_vetitesFrissit(m, t0, _mostT(m) / fps, vege);",
                 "LogicalKeyboardKey.keyV", "_vetitesSor = r;",
                 "final hatar = _vetitesVeg(r);",
                 "() => _vetitesAllit(m, !_vetitesBe)"):
        assert kell in palya, kell
    assert palya.count("final sorok = _jelenetSorok(m);") >= 3
    # Egy kattintásra: a vetit=1 link-paraméter (olvasva és írva), az app
    # vetites paramétere, a kezdőlap "Vetítés" gombja.
    # (a Jegyzeteim szűrővel a vetítés a jegyzetek megjöttét várja)
    assert ('if (v("vetit") === "1"){ if (csakJegyzet) vetitesVar = true; '
            'else vetitesAllit(true); }') in oldal
    assert 'if (vetites) q.set("vetit", "1");' in oldal
    assert oldal.index('v("vetit")') > oldal.index('v("kulcs")')
    assert "final bool vetites;" in palya
    assert palya.count("_kezdoVetites();") == 2
    # Az egy kattintásos vetítés TV-kamerával nyit (a jelentés linkje
    # tv=1-et visz, az app a _kezdoVetites-ben kapcsolja).
    i = palya.index("void _kezdoVetites()")
    assert "_tvKamera = true;" in palya[i:i + 600]
    kezdolap = (ui / "dashboard_screen.dart").read_text(encoding="utf-8")
    assert "matchId: id, csakVideozando: true, vetites: true" in kezdolap
    # A Klipek gomb a Videózandó szűrővel a videózandó csomagot kéri.
    assert ': (csakKulcs ? ["key_scene"] : KLIP_TIPUSOK)' in oldal
    # A jegyzetek (a lista sorai közt) a jegyzet-csomagban.
    assert '.concat(jegyzetek.length ? ["note"] : [])' in oldal
    assert 'if (_jegyzetek.isNotEmpty) "note",' in palya
    assert '...(_csakKulcs\n                            ? const ["key_scene"]' in palya
    klip = (ui / "clips_screen.dart").read_text(encoding="utf-8")
    assert '("key_scene", "Videózandó jelenetek",' in klip
    assert '("Videózandó jelenetek", ["key_scene"])' in klip



@pytest.mark.skipif(NODE is None, reason="node nincs telepítve")
def test_a_rajz_nyilhegye_es_link_kodolasa():
    """A rajz-eszköz tiszta függvényei: a nyílhegy szárnypontjai a tengely
    két oldalán, a csúcstól a megadott hosszal vissza; a link-kódolás
    0,1 m-re kerekít, és a dekódolás a hibás, pályán kívüli, túl rövid és
    ismeretlen színű tagokat elhagyja (legfeljebb RAJZ_MAX nyíl)."""
    from handball.pipeline.view3d_html import RAJZ_JS

    js = RAJZ_JS + """
const fej = nyilFej(0, 0, 10, 0, 1, 0.8);
const kod = rajzKodol([[1.234, 2.25, 9.87, 4, 1], [3, 3, 6, 7, 2]]);
const vissza = rajzDekodol(kod);
const hibas = rajzDekodol("1,2,3,4;1,2,3,4,9;1,2,99,4,0;1,1,1.2,1,0;x,1,2,3,0;5,5,8,9,0");
const sok = rajzDekodol(Array.from({length: 40}, (_, i) => "0,0,5," + i + ",0").join(";"));
console.log(JSON.stringify({fej, kod, vissza, hibas, sok: sok.length, max: RAJZ_MAX}));
"""
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    ki = json.loads(r.stdout)
    assert ki["fej"] == [[9, 0.4], [9, -0.4]]
    assert ki["kod"] == "1.2,2.3,9.9,4,1;3,3,6,7,2"
    assert ki["vissza"] == [[1.2, 2.3, 9.9, 4, 1], [3, 3, 6, 7, 2]]
    assert ki["hibas"] == [[5, 5, 8, 9, 0]]
    assert ki["sok"] == ki["max"] == 30


def test_a_rajz_az_oldalon_es_a_linkben():
    """Az oldalon a rajz-eszköz: a gomb, a színválasztó, a vissza és a
    törlés, az E billentyű, a mutató-kezelés (rajz-módban a húzás nyíl,
    két ujj csípés), a link írja és olvassa a "rajz" paramétert, a nyíl a
    padlón lapos test (VR-ben is látszik)."""
    from handball.pipeline.view3d_html import view3d_html

    oldal = view3d_html(_meccs())
    for kell in ('id="rajzGomb"', 'id="rajzSzin"', 'id="rajzVissza"',
                 'id="rajzTorles"', 'e.code === "KeyE"',
                 "else if (rajzMod) rajzModAllit(false);",
                 "if (rajzFolyo){ rajzKesz(); return; }",
                 "function padloPont(cx, cy)", "function nyilMesh(",
                 'q.set("rajz", rajzKodol(rajzok))',
                 'rajzok.push(...rajzDekodol(v("rajz")))',
                 "const RAJZ_SZINEK = ", "function rajzDekodol(s)",
                 "szinpad.add(rajzCsoport);", "csoportUrit(rajzCsoport);"):
        assert kell in oldal, kell



def test_a_rajz_az_appban_a_bongeszo_tukre():
    """Az app rajz-eszköze a böngésző RAJZ_JS tükre (a színek, a plafon, a
    legrövidebb nyíl), a festő a padlóra rajzol, az E és az Esc kezeli; a
    "Böngészőben" gomb a rajzot és a jelenet-lista állapotát (csapat,
    nyitott lista, Videózandó, vetítés) is átviszi."""
    import re
    from pathlib import Path

    from handball.pipeline.view3d_html import RAJZ_JS

    ui = Path(__file__).resolve().parent.parent.parent / "client" / "lib" / "ui"
    geo = (ui / "court_geometry.dart").read_text(encoding="utf-8")
    js_szinek = re.search(r"const RAJZ_SZINEK = \[([^\]]*)\]", RAJZ_JS).group(1)
    dart_szinek = re.search(r"const List<int> drawingColors = \[([^\]]*)\]",
                            geo).group(1)
    assert [s.strip().strip('"').lower() for s in js_szinek.split(",")] == \
        [s.strip()[4:].lower() for s in dart_szinek.split(",")]
    assert int(re.search(r"const RAJZ_MAX = (\d+);", RAJZ_JS).group(1)) == \
        int(re.search(r"const int drawingMax = (\d+);", geo).group(1))
    assert float(re.search(r"const RAJZ_MIN_M = ([0-9.]+);", RAJZ_JS).group(1)) == \
        float(re.search(r"const double drawingMinM = ([0-9.]+);", geo).group(1))
    palya = (ui / "court3d_screen.dart").read_text(encoding="utf-8")
    for kell in ('q["rajz"] = encodeDrawing(_rajzok);', 'q["vetit"] = "1";',
                 'q["kulcs"] = "1";', 'q["lista"] = "1";',
                 'q["jelenet"] = "hazai";', 'q["jelenet"] = "vendeg";',
                 "LogicalKeyboardKey.keyE", "_rajzModAllit(false);",
                 "if (_rajzFolyo != null) _rajzFolyo!,",
                 "_nyil(canvas, a, b, k);", "if (!_rajzMod) _meresKoppintas("):
        assert kell in palya, kell



def test_a_3d_jegyzet_a_kozos_jegyzet_tarba_ir():
    """A 3D pálya jegyzete a motor /notes tárába ír (kockában — a tömör
    adat viszi a képrátát), a jelenet-lista sorai közt "n" sorként
    jelenik meg (az azonos pillanatú jelenet-sor után, ✕ törli), a
    felirat-oszlopban és a VR-táblán is; az app ugyanezt a tárat olvassa
    és írja, a sorait a listába fűzi. A végpontok útja: amit a 3D ír, a
    jelentés és a klip-csomag olvassa."""
    from pathlib import Path

    from handball.pipeline.view3d_html import _compact_data, view3d_html

    m = _meccs()
    adat = _compact_data(m, None, {"home": [], "away": []},
                         {"home": [], "away": []})
    assert adat["fps"] == m.meta.fps
    oldal = view3d_html(m)
    for kell in ('id="jegyzetGomb"', 'e.code === "KeyJ"', "function jegyzetIr()",
                 "function jegyzetBetolt()", "function jegyzetTorol(id)",
                 'tipus: "n"', 'szoveg: "Jegyzet: " + j.text',
                 'frame: Math.round(ido * FPS)', '["vetitesJelzo", "jegyzetFelirat", ',
                 "jegyzetFrissit(ido);", "jegyzetBetolt();",
                 'else if (r.tipus === "e") eladasUtolso = r.s;',
                 'n: "#e8eef5"', 'x.className = "jtorol"'):
        assert kell in oldal, kell
    ui = Path(__file__).resolve().parent.parent.parent / "client" / "lib" / "ui"
    palya = (ui / "court3d_screen.dart").read_text(encoding="utf-8")
    for kell in ("_api.fetchNotes(id)", "_api.addNote(id, frame, szoveg.trim(),",
                 "LogicalKeyboardKey.keyJ", '"n", "Jegyzet: ${j["text"] ?? ""}',
                 '} else if (r.tipus == "e") {'):
        assert kell in palya, kell


def test_a_3d_jegyzet_vegpontjai_es_a_jelentes(tmp_path, monkeypatch):
    """A 3D oldal hívásai (POST/GET/DELETE /matches/{id}/notes) a közös
    tárat írják: a jegyzet kockája a GET-ben, a jelentésben a szöveg."""
    from fastapi.testclient import TestClient

    from handball.api.app import create_app

    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    m = _meccs()
    app = create_app()
    app.state.put_match(m)
    c = TestClient(app)
    mid = m.meta.match_id
    j = c.post(f"/matches/{mid}/notes",
               json={"frame": 50, "text": "Itt zárni kellett volna"}).json()
    assert c.get(f"/matches/{mid}/notes").json()["notes"][0]["frame"] == 50
    assert "Itt zárni kellett volna" in c.get(
        f"/matches/{mid}/report/export").text
    assert c.delete(f"/matches/{mid}/notes/{j['id']}").status_code == 200
    assert c.get(f"/matches/{mid}/notes").json()["notes"] == []



def test_a_jegyzet_a_rajzot_is_megorzi(tmp_path, monkeypatch):
    """A jegyzet "rajz" mezője: a böngésző link-kódolása megmarad, a
    szemét (betű, túl hosszú) kimarad; a jelentés jegyzet-sora jelzi (✎),
    és a motor címével "3D ↗" linket kap. Az oldal a jegyzettel küldi a
    rajzot, a jegyzet pillanatában visszarajzolja; az app ugyanígy."""
    from pathlib import Path

    from fastapi.testclient import TestClient

    from handball.api.app import create_app
    from handball.pipeline.view3d_html import view3d_html

    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    m = _meccs()
    app = create_app()
    app.state.put_match(m)
    c = TestClient(app, base_url="http://motor:8123")
    mid = m.meta.match_id
    jo = c.post(f"/matches/{mid}/notes",
                json={"frame": 50, "text": "Zárás", "rajz": "20,13.1,28.4,16.8,0"}).json()
    assert jo["rajz"] == "20,13.1,28.4,16.8,0"
    rossz = c.post(f"/matches/{mid}/notes",
                   json={"frame": 60, "text": "x", "rajz": "<script>"}).json()
    assert "rajz" not in rossz
    hosszu = c.post(f"/matches/{mid}/notes",
                    json={"frame": 70, "text": "y", "rajz": "1," * 700}).json()
    assert "rajz" not in hosszu
    tar = c.get(f"/matches/{mid}/notes").json()["notes"]
    assert [n.get("rajz") for n in tar] == ["20,13.1,28.4,16.8,0", None, None]
    html = c.get(f"/matches/{mid}/report/export").text
    assert "Zárás ✎" in html
    assert f'href="http://motor:8123/matches/{mid}/view3d?t=0.5&lista=1"' in html
    oldal = view3d_html(m)
    for kell in ('rajz: rajzzal ? rajzKodol(rajzok) : ""',
                 'rajz: rajzDekodol(n.rajz || "")',
                 "for (const r of j.rajz) jegyzetRajzCsoport.add(nyilMesh(...r));",
                 "if (rajzzal){ rajzok.length = 0; rajzFrissit(); }"):
        assert kell in oldal, kell
    ui = Path(__file__).resolve().parent.parent.parent / "client" / "lib"
    palya = (ui / "ui" / "court3d_screen.dart").read_text(encoding="utf-8")
    for kell in ("rajz: rajzzal ? encodeDrawing(_rajzok) : null",
                 "..._jegyzetRajz(m),", 'decodeDrawing(j["rajz"] as String?)'):
        assert kell in palya, kell
    api = (ui / "services" / "api_client.dart").read_text(encoding="utf-8")
    assert 'if (rajz != null && rajz.isNotEmpty) "rajz": rajz,' in api


@pytest.mark.skipif(NODE is None, reason="node nincs telepítve")
def test_a_rajz_dekodolasa_a_dart_tukorrel_egyezik():
    """A böngésző rajzDekodol-ja és az app decodeDrawing-ja ugyanazokat a
    tagokat ejti el — a Dart-teszt ugyanezt az esetet ellenőrzi
    (court_geometry_test.dart)."""
    from handball.pipeline.view3d_html import RAJZ_JS

    js = RAJZ_JS + """
console.log(JSON.stringify(rajzDekodol("1,2,3,4;1,2,3,4,9;1,2,99,4,0;1,1,1.2,1,0;x,1,2,3,0;5,5,8,9,0;-3,-2.5,4,4,1")));
"""
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [[5, 5, 8, 9, 0], [-3, -2.5, 4, 4, 1]]



def test_a_konyvtar_jegyzet_listaja_jelzi_a_rajzot(tmp_path, monkeypatch):
    """A /library/notes viszi a jegyzet rajzát ("" ha nincs), a
    Jegyzetek képernyő a rajzos sort ✎-gel jelzi."""
    from pathlib import Path

    from fastapi.testclient import TestClient

    from handball.api.app import create_app

    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    m = _meccs()
    app = create_app()
    app.state.put_match(m)
    c = TestClient(app)
    mid = m.meta.match_id
    c.post(f"/matches/{mid}/notes",
           json={"frame": 50, "text": "Zárás", "rajz": "20,13.1,28.4,16.8,0"})
    c.post(f"/matches/{mid}/notes", json={"frame": 60, "text": "Szöveg"})
    sajat = [n for n in c.get("/library/notes").json()["notes"]
             if n["match_id"] == mid]
    assert [n["rajz"] for n in sajat] == ["20,13.1,28.4,16.8,0", ""]
    kep = (Path(__file__).resolve().parent.parent.parent / "client" / "lib"
           / "ui" / "notes_screen.dart").read_text(encoding="utf-8")
    assert '(n["rajz"] as String? ?? "").isNotEmpty' in kep



def test_a_3d_oldal_gzip_pel_megy_at_ha_a_kliens_keri(tmp_path, monkeypatch):
    """A /view3d gzip-pel válaszol, ha a kliens kéri (a tartalom
    ugyanaz), különben tömörítetlenül."""
    import gzip

    from fastapi.testclient import TestClient

    from handball.api.app import create_app

    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    m = _meccs()
    app = create_app()
    app.state.put_match(m)
    c = TestClient(app)
    url = f"/matches/{m.meta.match_id}/view3d"
    tomor = c.get(url, headers={"Accept-Encoding": "gzip"})
    assert tomor.status_code == 200
    assert tomor.headers.get("content-encoding") == "gzip"
    assert "accept-encoding" in tomor.headers.get("vary", "").lower()
    sima = c.get(url, headers={"Accept-Encoding": "identity"})
    assert "content-encoding" not in sima.headers
    assert tomor.text == sima.text and "<html" in sima.text.lower()
    assert sima.headers["content-type"].startswith("text/html")
    # A hálózaton tényleg kisebb.
    assert len(gzip.compress(sima.text.encode("utf-8"))) < len(sima.text) / 3



def test_a_harmadik_atnezes_javitasai_a_3d_oldalon():
    """A vetítés a sort a fajta, az idő, a felirat és a jegyzet-azonosító
    szerint ismeri fel (két jegyzet egy kockán nem ragad körbe), a kettőzött
    sort átlépi, a kapott lerohanás vége a lövés; a döntés-, szabad-lövés-
    és eladás-réteg csak pillanat-váltáskor rajzol; az élő passzok és a
    passzsávok közös ("tartós") anyagokkal, amit a csoportUrit nem
    szabadít fel; az app ugyanígy (a nyilak a figurák előtt rajzolva)."""
    from pathlib import Path

    from handball.pipeline.view3d_html import view3d_html

    oldal = view3d_html(_meccs())
    for kell in ("function azonosSor(a, b)", "function vetitesVeg(r)",
                 "sorok.slice(i + 1).find(x => !azonosSor(x, vetitesSor))",
                 "const hatar = vetitesVeg(vetitesSor);",
                 "if (!q.userData.tartos) q.dispose();",
                 "dontesCsoport.userData.d === d", "szabadCsoport.userData.d === d",
                 "eladasCsoport.userData.d === d", "passzAnyag(hazai, ",
                 "new THREE.Line(g, PS_ANYAG[l.grade])"):
        assert kell in oldal, kell
    i = oldal.index("function dontesFrissit(t){")
    assert "csoportUrit(dontesCsoport);\n  const d" not in oldal[i:i + 200]
    ui = Path(__file__).resolve().parent.parent.parent / "client" / "lib" / "ui"
    palya = (ui / "court3d_screen.dart").read_text(encoding="utf-8")
    for kell in ("static bool _azonosSor(SceneRow a, SceneRow b)",
                 "double _vetitesVeg(SceneRow r)",
                 "final hatar = _vetitesVeg(r);"):
        assert kell in palya, kell
    # A nyilak a figurák ELŐTT (a festő-algoritmusban alattuk).
    assert palya.index("_nyil(canvas, a, b, k);") < palya.index(
        "_figura(canvas, j, frame.tSec);")


def test_a_3d_oldal_gzip_q0_eseten_tomoritetlen(tmp_path, monkeypatch):
    """A "gzip;q=0" elutasítás: tömörítetlen válasz."""
    from fastapi.testclient import TestClient

    from handball.api.app import create_app

    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    m = _meccs()
    app = create_app()
    app.state.put_match(m)
    c = TestClient(app)
    r = c.get(f"/matches/{m.meta.match_id}/view3d",
              headers={"Accept-Encoding": "gzip;q=0, identity"})
    assert r.status_code == 200 and "content-encoding" not in r.headers



def test_a_kocka_vegpont_a_forras_video_kockajat_adja(tmp_path, monkeypatch):
    """/matches/{id}/frame: a feldolgozott t. kockához a forrás-videó
    start_frame + t × stride. kockája JPEG-ben (a kért szélességgel); a
    videó nélküli meccsen 404. A szintetikus videó kockáinak szürkesége a
    kocka sorszáma — a visszakapott kép ebből azonosítható."""
    import cv2
    import numpy as np
    from fastapi.testclient import TestClient

    from handball.api.app import create_app

    ut = tmp_path / "v.mp4"
    w = cv2.VideoWriter(str(ut), cv2.VideoWriter_fourcc(*"mp4v"), 25.0,
                        (320, 160))
    for i in range(120):
        w.write(np.full((160, 320, 3), (i * 2) % 250, np.uint8))
    w.release()
    m = _meccs()
    m.meta.video_path = str(ut)
    m.meta.start_frame = 10
    m.meta.stride = 2
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path / "adat"))
    app = create_app()
    app.state.put_match(m)
    c = TestClient(app)
    r = c.get(f"/matches/{m.meta.match_id}/frame", params={"t": 20, "w": 160})
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    img = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
    assert img.shape[1] == 160
    # A 10 + 20 × 2 = 50. kocka: szürkeség 100 (±a tömörítés).
    assert abs(float(img.mean()) - 100) < 6
    m2 = _meccs()
    m2.meta.match_id = "videotlan"
    app.state.put_match(m2)
    assert c.get("/matches/videotlan/frame", params={"t": 5}).status_code == 404


def test_a_jegyzeteim_szuro():
    """"Jegyzeteim": a lista csak a jegyzetek (a vetítés a megjelölt
    pillanatokat játssza), a Videózandó párja (egy él a kettő közül), a
    Klipek a jegyzet-csomagot kéri, a link viszi (jegyzetek=1), és a
    linkes vetítés a jegyzetek megjöttét várja. Az app ugyanígy."""
    from pathlib import Path

    from handball.pipeline.view3d_html import view3d_html

    oldal = view3d_html(_meccs())
    for kell in ('jc.id = "jelenetJegyzet"', "const sorok = csakJegyzet ? [] : kulcsSzur(",
                 "if (csakKulcs) csakJegyzet = false;", "if (csakJegyzet) csakKulcs = false;",
                 'types: csakJegyzet ? ["note"]', 'q.set("jegyzetek", "1")',
                 'v("jegyzetek") === "1"',
                 'if (csakJegyzet) vetitesVar = true; else vetitesAllit(true);',
                 "if (vetitesVar){ vetitesVar = false; vetitesAllit(true); }"):
        assert kell in oldal, kell
    palya = (Path(__file__).resolve().parents[2] / "client" / "lib" / "ui"
             / "court3d_screen.dart").read_text(encoding="utf-8")
    for kell in ("final sorok = _csakJegyzet", '"Jegyzeteim (${_jegyzetek.length})"',
                 "if (v) _csakKulcs = false;", "if (v) _csakJegyzet = false;",
                 'initialTypes: _csakJegyzet\n                          ? const ["note"]',
                 'if (_csakJegyzet) q["jegyzetek"] = "1";'):
        assert kell in palya, kell


def test_a_kozos_nezes_vegpontjai(tmp_path, monkeypatch):
    """/matches/{id}/shared3d: a vezető állapota (PUT) a követőnek (GET) a
    korával — sorszámmal, csendben "nincs vezető", DELETE után sincs; a
    rossz alakú érték 400, az ismeretlen meccs 404."""
    from fastapi.testclient import TestClient

    from handball.api.app import create_app
    from handball.pipeline import court3d

    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    m = _meccs()
    app = create_app()
    app.state.put_match(m)
    c = TestClient(app)
    url = f"/matches/{m.meta.match_id}/shared3d"
    assert c.get(url).json() == {"active": False}
    r = c.put(url, json={"t": 61.5, "playing": True, "speed": 2,
                         "rajz": "20,13.1,28.4,16.8,0"})
    assert r.status_code == 200 and r.json() == {"rev": 1, "followers": 0}
    a = c.get(url).json()
    assert a["active"] and a["t"] == 61.5 and a["playing"] is True
    assert a["speed"] == 2.0 and a["rajz"] == "20,13.1,28.4,16.8,0"
    assert a["rev"] == 1 and 0 <= a["kor"] < 5
    # A követők: a véletlen azonosítójuk szerint, egyszer számolva; a
    # rossz alakú azonosító nem számít, a válaszban nincs követő-lista.
    for kid in ("a1", "b2", "a1", "<x>"):
        assert "kovetok" not in c.get(url, params={"kid": kid}).json()
    assert c.put(url, json={"t": 3, "playing": False}).json() == {
        "rev": 2, "followers": 2}
    assert c.get(url).json()["speed"] == 1.0
    for rossz in ({"t": "x"}, {"t": 1, "speed": 20}, {"t": 1, "rajz": "<b>"}):
        assert c.put(url, json=rossz).status_code == 400, rossz
    # A végtelen idő (a JSON 1e999-e) sem fér be.
    assert c.put(url, content=b'{"t": 1e999}',
                 headers={"Content-Type": "application/json"}).status_code == 400
    assert c.put("/matches/nincs/shared3d", json={"t": 1}).status_code == 404
    # A régóta nem kérdező követő kiesik.
    monkeypatch.setattr(court3d, "SHARED3D_FOLLOWER_S", -1.0)
    assert c.put(url, json={"t": 3}).json()["followers"] == 0
    monkeypatch.setattr(court3d, "SHARED3D_FOLLOWER_S", 3.0)
    # A hallgató vezető: megszakadt vezetés.
    monkeypatch.setattr(court3d, "SHARED3D_STALE_S", -1.0)
    assert c.get(url).json()["active"] is False
    monkeypatch.setattr(court3d, "SHARED3D_STALE_S", 15.0)
    assert c.delete(url).json() == {"ok": True}
    assert c.get(url).json() == {"active": False}


def test_a_3d_oldal_kozos_nezese():
    """Az oldalon a "📡 Vezetem" / "👥 Követem": a vezető küld, a követő
    kérdez és követ (idő a korral, szünet, sebesség, rajz), a link viszi
    (kovet=1); a küszöbök a motor számai. Az app is vezethet (ugyanaz a
    végpont és ütem)."""
    from pathlib import Path

    from handball.pipeline import court3d
    from handball.pipeline.view3d_html import view3d_html

    oldal = view3d_html(_meccs())
    for kell in ('id="vezetGomb"', 'id="kovetGomb"', 'id="kozosInfo"',
                 "function kozosFrissit()", "kozosFrissit();",
                 '"/shared3d"', 'method: "PUT"', 'method: "DELETE"',
                 "a.t + (a.playing ? a.kor * a.speed : 0)",
                 "Math.abs(ido - cel) > KZ_TURES",
                 "rajzok.push(...rajzDekodol(a.rajz))",
                 'q.set("kovet", "1")', 'v("kovet") === "1"',
                 'v("vezet") === "1"', "if (vetites) vetitesAllit(false);",
                 # A követő állapota a VR-táblán (váltáskor, hibánál végig).
                 'const kz = kozosMod === "kovet" ? kozosInfo.textContent : "";',
                 "kz !== KZ_KOVETED || performance.now() - kzInfoValtas < KZ_VR_MS",
                 # A vezető látja, hányan követik (a követő azonosítója).
                 'kzCim() + "?kid=" + KZ_KID', "kzKovetok = a.followers;"):
        assert kell in oldal, kell
    assert "__KZ_" not in oldal
    # Az app is vezethet: ugyanaz a végpont, ugyanaz a küldési ütem.
    import re
    gyoker = Path(__file__).resolve().parents[2] / "client" / "lib"
    palya = (gyoker / "ui" / "court3d_screen.dart").read_text(encoding="utf-8")
    api = (gyoker / "services" / "api_client.dart").read_text(encoding="utf-8")
    assert '"$baseUrl/matches/$matchId/shared3d"' in api
    ertek = re.search(r"static const double _vezetKuldS = ([0-9.]+);", palya)
    assert ertek and float(ertek.group(1)) == court3d.SHARED3D_SEND_S
    assert 'json["followers"]' in api
    for kell in ("_vezetKuld(now);", "rajz: encodeDrawing(_rajzok))",
                 '"📡 Vezetsz · $_kovetok követő"',
                 '"${_api.baseUrl}/matches/$id/view3d?kovet=1"',
                 "_api.deleteShared3d(id)"):
        assert kell in palya, kell
    assert (f"const KZ_KULD = {float(court3d.SHARED3D_SEND_S)!r}, KZ_KERD = "
            f"{float(court3d.SHARED3D_POLL_S)!r}, KZ_TURES = "
            f"{float(court3d.SHARED3D_TOLERANCE_S)!r};") in oldal


def test_a_3d_oldal_videoja():
    """Az oldalon a "📺 Videó" (K): kép a képben és kivetítő (VR-ben is), a
    kocka-szám a lejátszási idő × képráta, a link viszi (video=1)."""
    from handball.pipeline.view3d_html import view3d_html

    oldal = view3d_html(_meccs())
    for kell in ('id="videoGomb"', 'id="videoAblak"', 'id="videoKep"',
                 'e.code === "KeyK"', "function videoFrissit(t)",
                 '"/frame?t=" + kocka', "Math.round(t * FPS)",
                 "szinpad.add(kivetito);", "videoFrissit(ido);",
                 "new THREE.CanvasTexture(videoVaszon)",
                 'q.set("video", "1")', 'v("video") === "1"',
                 # Videó nélküli meccsen az első 404 után nem kér újra
                 # minden kockán (a K próbálja újra).
                 "if (!videoBe || videoToltes || videoNincs) return;",
                 "if (videoVolt) return;\n  videoNincs = true;"):
        assert kell in oldal, kell
    # Az app párja: a 3D kép MELLETT, ugyanabból a végpontból, a K-ra; a
    # böngészős link viszi.
    from pathlib import Path
    gyoker = Path(__file__).resolve().parents[2] / "client" / "lib"
    palya = (gyoker / "ui" / "court3d_screen.dart").read_text(encoding="utf-8")
    api = (gyoker / "services" / "api_client.dart").read_text(encoding="utf-8")
    assert '"$baseUrl/matches/$matchId/frame?t=$t&w=$w"' in api
    for kell in ("LogicalKeyboardKey.keyK", "_api.frameUrl(id, t, w: 480)",
                 'if (_videoBe) q["video"] = "1";',
                 "Expanded(child: _nezetEsVideo(m))"):
        assert kell in palya, kell
