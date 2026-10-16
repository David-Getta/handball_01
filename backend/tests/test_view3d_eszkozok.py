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
                'id="sugoGomb"', "function sugoAllit", "innerWidth >= 1600",
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
                 "if (vetitesVar){ vetitesVar = false; vetitesAllit(true); }",
                 "if (!v.ok){ vetitesVar = false; return; }",
                 "} catch (e) { vetitesVar = false;"):
        assert kell in oldal, kell
    palya = (Path(__file__).resolve().parents[2] / "client" / "lib" / "ui"
             / "court3d_screen.dart").read_text(encoding="utf-8")
    for kell in ("final sorok = _csakJegyzet", '"Jegyzeteim (${_jegyzetek.length})"',
                 "if (v) _csakKulcs = false;", "if (v) _csakJegyzet = false;",
                 'initialTypes: _csakJegyzet\n                          ? const ["note"]',
                 'if (_csakJegyzet) q["jegyzetek"] = "1";',
                 # A könyvtár Jegyzetek képernyőjéről: szűrő + vetítés.
                 "if (widget.csakJegyzet && _jegyzetek.isNotEmpty) {"):
        assert kell in palya, kell
    jegyzetek_kep = (Path(__file__).resolve().parents[2] / "client" / "lib"
                     / "ui" / "notes_screen.dart").read_text(encoding="utf-8")
    assert "vetites: true,\n                    csakJegyzet: true," in jegyzetek_kep


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
    assert r.status_code == 200 and r.json() == {"rev": 1, "followers": 0,
                                                  "csapat": []}
    a = c.get(url).json()
    assert a["active"] and a["t"] == 61.5 and a["playing"] is True
    assert a["speed"] == 2.0 and a["rajz"] == "20,13.1,28.4,16.8,0"
    assert a["rev"] == 1 and 0 <= a["kor"] < 5
    # A követők: a véletlen azonosítójuk szerint, egyszer számolva; a
    # rossz alakú azonosító nem számít, a válaszban nincs követő-lista.
    for kid in ("a1", "b2", "a1", "<x>"):
        assert "kovetok" not in c.get(url, params={"kid": kid}).json()
    assert c.put(url, json={"t": 3, "playing": False}).json() == {
        "rev": 2, "followers": 2, "csapat": []}
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


def test_a_kozos_nezes_mutatoja(tmp_path, monkeypatch):
    """A vezető mutatója a korával megy a követőnek: az ideje csak ÚJ
    mutatásnál (új n) indul; a rossz alakú mutató 400. Az oldal: Shift+
    kattintás a vezetőnél, a követő a friss új mutatót mutatja."""
    import time

    from fastapi.testclient import TestClient

    from handball.api.app import create_app
    from handball.pipeline import court3d
    from handball.pipeline.view3d_html import view3d_html

    ora = [100.0]
    monkeypatch.setattr(court3d, "shared3d_ora", lambda: ora[0])
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    m = _meccs()
    app = create_app()
    app.state.put_match(m)
    c = TestClient(app)
    url = f"/matches/{m.meta.match_id}/shared3d"
    mut = {"x": 12.34, "y": 7.0, "n": 1791700000123}
    assert c.put(url, json={"t": 1, "mutato": mut}).status_code == 200
    ora[0] += 2.5
    # Ugyanaz a mutató újra küldve: a kora nem indul újra.
    assert c.put(url, json={"t": 2, "mutato": mut}).status_code == 200
    a = c.get(url).json()["mutato"]
    assert (a["x"], a["y"], a["n"], a["kor"]) == (12.34, 7.0, 1791700000123, 2.5)
    # Új mutatás: új idő.
    assert c.put(url, json={"t": 3, "mutato": {**mut, "n": 5}}).status_code == 200
    assert c.get(url).json()["mutato"]["kor"] == 0.0
    # Mutató nélkül nincs mutató.
    c.put(url, json={"t": 4})
    assert c.get(url).json()["mutato"] is None
    for rossz in ({"x": "a", "y": 1, "n": 1}, [1, 2, 3], {"x": 1, "y": 1}):
        assert c.put(url, json={"t": 1, "mutato": rossz}).status_code == 400, rossz
    # A pályán túlnyúló pont a sávba szorítva (nem állítja meg a vezetést).
    assert c.put(url, json={"t": 1, "mutato": {"x": 100, "y": -9, "n": 11}}
                 ).status_code == 200
    a = c.get(url).json()["mutato"]
    assert (a["x"], a["y"]) == (45.0, -5.0)

    oldal = view3d_html(_meccs())
    for kell in ('if (e.shiftKey && kozosMod === "vezet"){ mutatoKattintas(',
                 "mutato: kzMutato,", "if (a.mutato.kor < KZ_MUTATO) mutatoMutat(",
                 "mutatoFrissit();", "Shift+katt a padlóra: mutató a csapatnak"):
        assert kell in oldal, kell
    assert f"const KZ_MUTATO = {float(court3d.SHARED3D_POINTER_S)!r};" in oldal
    # Az app vezetője is mutathat: ugyanaz az idő, a mutató a küldésben.
    import re
    from pathlib import Path
    gyoker = Path(__file__).resolve().parents[2] / "client" / "lib"
    palya = (gyoker / "ui" / "court3d_screen.dart").read_text(encoding="utf-8")
    api = (gyoker / "services" / "api_client.dart").read_text(encoding="utf-8")
    ertek = re.search(r"static const double _mutatoS = ([0-9.]+);", palya)
    assert ertek and float(ertek.group(1)) == court3d.SHARED3D_POINTER_S
    for kell in ("if (_vezet && HardwareKeyboard.instance.isShiftPressed) {",
                 "mutato: _mutato,", "mutato: _mutatoAllapot(),"):
        assert kell in palya, kell
    assert 'if (mutato != null) "mutato": mutato,' in api
    # Új vezetés: a régi mutató nem megy újra (böngésző és app).
    assert "kzRajz = null; kzUtolso = 0; kzMutato = null;" in oldal
    assert "_kovetok = null;\n      // Új vezetés" in palya


def test_a_kozos_nezes_nezopontja(tmp_path, monkeypatch):
    """"📍 Ide mindenki": a nézőpont a korával megy (új n = új idő), a
    csarnokon kívüli vagy hiányos 400; az oldal a gombot csak vezetés
    közben engedi, a követő a friss új nézőpontba ugrik (szabad mód)."""
    import time

    from fastapi.testclient import TestClient

    from handball.api.app import create_app
    from handball.pipeline import court3d
    from handball.pipeline.view3d_html import view3d_html

    ora = [50.0]
    monkeypatch.setattr(court3d, "shared3d_ora", lambda: ora[0])
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    m = _meccs()
    app = create_app()
    app.state.put_match(m)
    c = TestClient(app)
    url = f"/matches/{m.meta.match_id}/shared3d"
    nz = {"x": 1.5, "y": 1.7, "z": 10.0, "yaw": -1.5708, "pitch": -0.1, "n": 7}
    assert c.put(url, json={"t": 1, "nezopont": nz}).status_code == 200
    ora[0] += 1.25
    c.put(url, json={"t": 2, "nezopont": nz})
    a = c.get(url).json()["nezopont"]
    assert a == {**nz, "n": 7.0, "kor": 1.25}
    for rossz in ({"x": 1, "y": 1}, {**nz, "yaw": "x"}):
        assert c.put(url, json={"t": 1, "nezopont": rossz}).status_code == 400, rossz
    # A csarnokon túlnyúló nézőpont a dobozba szorítva (a messzire húzott
    # keringés nem állítja meg a vezetést).
    assert c.put(url, json={"t": 1, "nezopont": {**nz, "y": 500, "z": -99,
                                                  "pitch": 3, "n": 8}}
                 ).status_code == 200
    a = c.get(url).json()["nezopont"]
    assert (a["y"], a["z"], a["pitch"]) == (60.0, -60.0, 1.6)
    # A böngésző is a dobozba szorít, és hibára eldobja a mutatót.
    oldal0 = view3d_html(_meccs())
    assert "kzMutato = null; kzNezopont = null;" in oldal0
    assert "y: clamp(rig.position.y, 0.2, 60)" in oldal0

    oldal = view3d_html(_meccs())
    for kell in ('id="ideGomb"', 'ideGomb.disabled = kozosMod !== "vezet";',
                 "nezopont: kzNezopont})", "if (a.nezopont.kor < KZ_MUTATO) nezopontAlkalmaz(",
                 'modValt("szabad");\n  rig.position.set(v.x, v.y, v.z);',
                 "kozosInfo.textContent === KZ_IDE && performance.now() - kzInfoValtas < KZ_VR_MS"):
        assert kell in oldal, kell
    # Az app vezetője is küldhet nézőpontot (a böngésző three-terébe
    # átszámolva — court_geometry.browserViewpoint, egységteszttel).
    from pathlib import Path
    gyoker = Path(__file__).resolve().parents[2] / "client" / "lib"
    palya = (gyoker / "ui" / "court3d_screen.dart").read_text(encoding="utf-8")
    api = (gyoker / "services" / "api_client.dart").read_text(encoding="utf-8")
    assert "...browserViewpoint(_cx, _cy, _cz, _yaw, _pitch)," in palya
    assert "nezopont: _nezopont)" in palya
    assert 'if (nezopont != null) "nezopont": nezopont,' in api


def test_a_kozos_nezes_jelenlete(tmp_path, monkeypatch):
    """Jelenlét: a követő a kérdéssel a helyét és nevét adja, a vezető a
    küldéssel a sajátját; a vezető a csapatot (a csatlakozás sorrendjében),
    a követő a TÖBBIEKET és a vezetőt kapja. A hely a csarnok dobozába
    szorul, a rossz alakú nem számít (a követés megy tovább), a vezető
    rossz helye 400; a név megtisztítva, legfeljebb SHARED3D_NAME_MAX; a
    kiesett követő a csapatból is kiesik; a /kovet a nevet továbbviszi."""
    from fastapi.testclient import TestClient

    from handball.api.app import create_app
    from handball.pipeline import court3d
    from handball.pipeline.view3d_html import view3d_html

    ora = [500.0]
    monkeypatch.setattr(court3d, "shared3d_ora", lambda: ora[0])
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    m = _meccs()
    app = create_app()
    app.state.put_match(m)
    c = TestClient(app)
    url = f"/matches/{m.meta.match_id}/shared3d"
    # Vezető nélkül a követő nem kerül a csapatba.
    c.get(url, params={"kid": "elo", "hely": "1,1.6,2,0"})
    r = c.put(url, json={"t": 1, "hely": [20, 1.6, 27, 0.5]})
    assert r.status_code == 200 and r.json()["csapat"] == []
    a = c.get(url, params={"kid": "peti", "hely": "10,1.7,5,7",
                           "nev": " Peti\x07 "}).json()
    assert a["vezeto_hely"] == [20.0, 1.6, 27.0, 0.5]
    assert a["csapat"] == []  # magát nem látja
    # A csarnokon kívüli hely a dobozba szorul; a szög a (−π, π]-be.
    c.get(url, params={"kid": "anna", "hely": "500,-3,10,0", "nev": "Anna"})
    c.get(url, params={"kid": "nevtelen", "hely": "30,1.6,10,-1"})
    # Rossz alakú hely: követő, de hely nélkül nem látszik.
    for rossz in ("1,2,3", "a,b,c,d", "1,2,3,nan", "1,2,3,inf"):
        c.get(url, params={"kid": "rossz", "hely": rossz})
    r = c.put(url, json={"t": 2, "hely": [20, 1.6, 27, 0.5]}).json()
    assert r["followers"] == 4
    import math
    assert r["csapat"] == [
        {"sz": 1, "nev": "Peti", "hely": [10.0, 1.7, 5.0,
                                          round(math.atan2(math.sin(7), math.cos(7)), 3)]},
        {"sz": 2, "nev": "Anna", "hely": [100.0, 0.2, 10.0, 0.0]},
        {"sz": 3, "nev": "", "hely": [30.0, 1.6, 10.0, -1.0]}]
    # A követő a többieket látja (magát nem), a sorszám marad.
    a = c.get(url, params={"kid": "anna", "hely": "5,1.6,5,0", "nev": "Anna"}).json()
    assert [e["sz"] for e in a["csapat"]] == [1, 3]
    # A név legfeljebb SHARED3D_NAME_MAX jel.
    hosszu = "x" * (court3d.SHARED3D_NAME_MAX + 9)
    c.get(url, params={"kid": "peti", "hely": "10,1.7,5,0", "nev": hosszu})
    nevek = [e["nev"] for e in c.put(url, json={"t": 3}).json()["csapat"]]
    assert nevek[0] == "x" * court3d.SHARED3D_NAME_MAX
    # A vezető helye nélkül nincs arany fej; a rossz hely 400.
    assert c.get(url, params={"kid": "peti"}).json()["vezeto_hely"] is None
    for rossz in ([1, 2, 3], "a,b,c,d", [1, 2, 3, "x"], {"x": 1}):
        assert c.put(url, json={"t": 1, "hely": rossz}).status_code == 400, rossz
    # A kiesett követő a csapatból is kiesik; visszatérve új sorszám.
    ora[0] += court3d.SHARED3D_FOLLOWER_S + 1
    c.get(url, params={"kid": "peti", "hely": "1,1.6,1,0", "nev": "Peti"})
    assert c.put(url, json={"t": 4}).json()["csapat"] == [
        {"sz": 1, "nev": "Peti", "hely": [1.0, 1.6, 1.0, 0.0]}]
    ora[0] += court3d.SHARED3D_FOLLOWER_S + 1
    c.put(url, json={"t": 5})
    c.get(url, params={"kid": "peti", "hely": "1,1.6,1,0"})
    assert [e["sz"] for e in c.put(url, json={"t": 6}).json()["csapat"]] == [5]
    # A rövid link a nevet továbbviszi (megtisztítva, kódolva).
    r = c.get("/kovet", params={"nev": "Kiss Péter"}, follow_redirects=False)
    assert r.headers["location"] == (
        f"/matches/{m.meta.match_id}/view3d?kovet=1&nev=Kiss%20P%C3%A9ter")

    oldal = view3d_html(_meccs())
    for kell in ("hely: sajatHely(), mutato: kzMutato,",
                 '"&hely=" + sajatHely().join(",")',
                 '(KZ_NEV ? "&nev=" + encodeURIComponent(KZ_NEV) : "")',
                 "jelenletAllit(kzLista(a.csapat, a.vezeto_hely));",
                 "jelenletAllit(kzLista(a.csapat, null));",
                 "kzNezopont = null;\n  jelenletAllit([]);",
                 "jelenletFrissit(dt);",
                 "cs.visible = tav > KZ_KOZEL;",
                 "const s = Math.max(1, tav / 10);",
                 "Math.atan2(-kzIranyV.x, -kzIranyV.z)",
                 'if (KZ_NEV) q.set("nev", KZ_NEV);',
                 "/kovet?nev=Peti"):
        assert kell in oldal, kell
    assert (f'.slice(0, {court3d.SHARED3D_NAME_MAX});') in oldal
    assert "__KZ_NEV_MAX__" not in oldal
    assert f"const KZ_KOZEL = {float(court3d.SHARED3D_NEAR_M)!r};" in oldal
    # Az app vezetője is: a helyét küldi, a csapatot rajzolja (ugyanaz a
    # közelségi küszöb).
    import re
    from pathlib import Path
    gyoker = Path(__file__).resolve().parents[2] / "client" / "lib"
    palya = (gyoker / "ui" / "court3d_screen.dart").read_text(encoding="utf-8")
    geo = (gyoker / "ui" / "court_geometry.dart").read_text(encoding="utf-8")
    api = (gyoker / "services" / "api_client.dart").read_text(encoding="utf-8")
    ertek = re.search(r"const double presenceNearM = ([0-9.]+);", geo)
    assert ertek and float(ertek.group(1)) == court3d.SHARED3D_NEAR_M
    for kell in ("hely: browserPresence(_cx, _cy, _cz, _yaw),",
                 "_csapat = parseTeamPresence(cs);",
                 "csapat: _vezet ? _csapat : const [],",
                 "for (final t in csapat) {",
                 "_csapat = const [];\n      _kovetok = null;"):
        assert kell in palya, kell
    assert 'if (hely != null) "hely": hely,' in api
    assert 'json["csapat"]' in api


def test_a_kozos_nezes_kvize(tmp_path, monkeypatch):
    """Kvíz: a vezető köre (n) mellett a követők válasza a vezetőnek
    mindig, a csapatnak csak a felfedés után látszik; a régi kör válasza
    nem; a rossz alakú válasz nem számít, a rossz kör 400; a kvíz vége
    után nincs válasz. Az oldal: gomb, kattintás, VR-ravasz, küldés."""
    from fastapi.testclient import TestClient

    from handball.api.app import create_app
    from handball.pipeline import court3d
    from handball.pipeline.view3d_html import view3d_html

    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    m = _meccs()
    app = create_app()
    app.state.put_match(m)
    c = TestClient(app)
    url = f"/matches/{m.meta.match_id}/shared3d"
    c.put(url, json={"t": 1})
    for kid, nev, h in (("peti", "Peti", "1,1.6,1,0"), ("anna", "Anna", "2,1.6,2,0")):
        c.get(url, params={"kid": kid, "hely": h, "nev": nev})
    # Kvíz nélkül a válasz sehol.
    c.get(url, params={"kid": "peti", "hely": "1,1.6,1,0", "valasz": "30,12,7"})
    assert all("valasz" not in e for e in c.put(url, json={"t": 1}).json()["csapat"])
    kor = {"n": 7, "mutat": False}
    c.put(url, json={"t": 1, "kviz": kor})
    c.get(url, params={"kid": "peti", "hely": "1,1.6,1,0", "valasz": "30,12,7"})
    # A régi kör (5) válasza és a rossz alakú nem számít.
    c.get(url, params={"kid": "anna", "hely": "2,1.6,2,0", "valasz": "31,9,5"})
    a = c.get(url, params={"kid": "anna", "hely": "2,1.6,2,0",
                           "valasz": "x,9,7"}).json()
    assert a["kviz"] == {"n": 7.0, "mutat": False}
    # A csapat a felfedés előtt nem látja a többiek válaszát.
    assert all("valasz" not in e for e in a["csapat"])
    r = c.put(url, json={"t": 1, "kviz": kor}).json()
    assert [(e["nev"], e.get("valasz")) for e in r["csapat"]] == [
        ("Peti", [30.0, 12.0]), ("Anna", None)]
    # Anna válaszol (a pályán túli a sávba szorul); felfedés: a csapat is.
    c.get(url, params={"kid": "anna", "hely": "2,1.6,2,0", "valasz": "60,-9,7"})
    c.put(url, json={"t": 1, "kviz": {"n": 7, "mutat": True}})
    a = c.get(url, params={"kid": "anna", "hely": "2,1.6,2,0",
                           "valasz": "45,-5,7"}).json()
    assert [(e["nev"], e.get("valasz")) for e in a["csapat"]] == [
        ("Peti", [30.0, 12.0])]
    r = c.put(url, json={"t": 1, "kviz": {"n": 7, "mutat": True}}).json()
    assert [e.get("valasz") for e in r["csapat"]] == [[30.0, 12.0], [45.0, -5.0]]
    # Új kör: a régi válaszok nem látszanak; vége: semmi.
    r = c.put(url, json={"t": 1, "kviz": {"n": 8}}).json()
    assert all("valasz" not in e for e in r["csapat"])
    r = c.put(url, json={"t": 1}).json()
    assert all("valasz" not in e for e in r["csapat"])
    assert c.get(url, params={"kid": "peti"}).json()["kviz"] is None
    for rossz in ({"n": "x"}, {"mutat": True}, [1], "x"):
        assert c.put(url, json={"t": 1, "kviz": rossz}).status_code == 400, rossz
    assert c.put(url, content=b'{"t": 1, "kviz": {"n": 1e999}}',
                 headers={"Content-Type": "application/json"}).status_code == 400

    oldal = view3d_html(_meccs())
    for kell in ('id="kvizGomb"', 'kvizGomb.disabled = kozosMod !== "vezet";',
                 "kviz: kzKviz, hely: sajatHely(),",
                 '"&valasz=" + [kzValasz.x, kzValasz.y, kzValasz.n].join(",")',
                 "if (kvizValaszolhat()){ valaszKattintas(e.clientX, e.clientY); return; }",
                 "if (kvizValaszolhat()) vrValasz(k - 1);",
                 "valaszokAllit(kzKviz ? kzValaszLista(a.csapat) : []);",
                 "kzInfo(kvizSzoveg());",
                 "if (kozosMod !== \"kovet\" || !kzKvizKor || kzKvizKor.mutat) return;",
                 "megy = false; lejatszasGomb.textContent",
                 "kvíz közben a ravasz a válaszod",
                 "valaszJelFrissit(); felirat(ido);"):
        assert kell in oldal, kell
    # Az app vezetője is: a kör a küldésben, a válaszok a képen.
    from pathlib import Path
    gyoker = Path(__file__).resolve().parents[2] / "client" / "lib"
    palya = (gyoker / "ui" / "court3d_screen.dart").read_text(encoding="utf-8")
    geo = (gyoker / "ui" / "court_geometry.dart").read_text(encoding="utf-8")
    api = (gyoker / "services" / "api_client.dart").read_text(encoding="utf-8")
    for kell in ("kviz: _kvizAllapot(),",
                 "onPressed: _kvizLep,",
                 "kvizJelek: _vezet && _kviz != null ? _kvizJelek() : const [],",
                 "_playing = false; // a kérdés a megállított jeleneten",
                 "_kviz = null;\n      _csapat = const [];"):
        assert kell in palya, kell
    assert 'if (kviz != null) "kviz": kviz,' in api
    assert 'final va = e["valasz"];' in geo


def test_a_dontes_kviz_itelete_harom_tukorben():
    """court3d.quiz_verdict és a böngésző kvizItelet-je (node) ugyanazokon
    az eseteken ugyanazt mondja; a küszöbök a motor számai (az app
    quizVerdict-je a Dart-tesztben ugyanezeket az eseteket nézi)."""
    import random

    from handball.pipeline import court3d
    from handball.pipeline.court3d import quiz_verdict
    from handball.pipeline.view3d_html import KVIZ_JS

    # A kézi esetek (a Dart-teszt is ezeket nézi).
    passz = [None, 1, 20, 10, 25, 4, 0.3, "p", 30, 12, 0.6, 0.3]
    loves = [None, 1, 30, 10, 25, 4, 0.3, "s", 40, 10, 0.6, 0.3]
    kezi = [((30, 12), passz, True), ((32.9, 12), passz, True),
            ((33.1, 12), passz, False), ((25, 4), passz, False),
            ((27.4, 8), passz, False), ((35, 10), loves, True),
            ((33.9, 10), loves, False), ((28, 7), loves, False)]
    for (v, d, vart) in kezi:
        assert quiz_verdict(v, d[8:10], d[4:6], d[7] == "s") is vart, (v, d[7])
    rnd = random.Random(3)
    esetek = [((round(rnd.uniform(15, 40), 1), round(rnd.uniform(0, 20), 1)),
               rnd.choice([passz, loves])) for _ in range(300)]
    esetek += [(v, d) for v, d, _ in kezi]
    js = (KVIZ_JS.replace("__KV_TALALAT__", repr(court3d.SHARED3D_QUIZ_HIT_M))
          .replace("__KV_LOVES__", repr(court3d.SHARED3D_QUIZ_SHOT_M))
          + "const E = " + json.dumps(esetek) + ";\n"
          + "console.log(JSON.stringify(E.map(([v, d]) => kvizItelet(v[0], v[1], d))));")
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    vart = [quiz_verdict(v, d[8:10], d[4:6], d[7] == "s") for v, d in esetek]
    assert json.loads(r.stdout) == vart
    assert any(vart) and not all(vart)


def test_a_dontes_kviz_a_motorban_es_az_oldalon(tmp_path, monkeypatch):
    """A kvíz köre a döntés-pillanat idejét (d) is viszi; a rossz d 400. Az
    oldal: indításkor a látszó Döntések-sor ideje a körbe, a feliratok
    ✓/✗-gel (a vezetőnél azonnal, a csapatnál a felfedés után), a vezető
    állapot-sorában a találatok száma; a küszöbök a motor számai."""
    from fastapi.testclient import TestClient

    from handball.api.app import create_app
    from handball.pipeline import court3d
    from handball.pipeline.view3d_html import view3d_html

    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    m = _meccs()
    app = create_app()
    app.state.put_match(m)
    c = TestClient(app)
    url = f"/matches/{m.meta.match_id}/shared3d"
    assert c.put(url, json={"t": 1, "kviz": {"n": 3, "d": 61.234}}).status_code == 200
    assert c.get(url).json()["kviz"] == {"n": 3.0, "mutat": False, "d": 61.23}
    for rossz in ({"n": 3, "d": "x"}, {"n": 3, "d": [1]}):
        assert c.put(url, json={"t": 1, "kviz": rossz}).status_code == 400, rossz
    assert c.put(url, content=b'{"t": 1, "kviz": {"n": 3, "d": 1e999}}',
                 headers={"Content-Type": "application/json"}).status_code == 400

    oldal = view3d_html(_meccs())
    for kell in ("kzKviz = d ? {n: Date.now(), mutat: false, d: d[0]}",
                 "kzKviz = {...kzKviz, mutat: true};",
                 'const d = (kozosMod === "vezet" || (kor && kor.mutat)) ? kvizDontes(kor) : null;',
                 'kvizCimke = (nev, x, y, d) => d ? nev + (kvizItelet(x, y, d) ? " ✓" : " ✗") : nev;',
                 '" · ✓ " + kzJoDb + " a jobb opció"',
                 "function kvizItelet(vx, vy, d){", "KZ_KVIZ_JOBB"):
        assert kell in oldal, kell
    assert (f"const KV_TALALAT = {float(court3d.SHARED3D_QUIZ_HIT_M)!r}, "
            f"KV_LOVES = {float(court3d.SHARED3D_QUIZ_SHOT_M)!r};") in oldal
    assert "__KV_" not in oldal
    # Az app is: a pillanat a körbe, az ítélet a felirathoz, ugyanazok a
    # küszöbök (court_geometry.quizVerdict, Dart-teszttel).
    import re
    from pathlib import Path
    gyoker = Path(__file__).resolve().parents[2] / "client" / "lib"
    palya = (gyoker / "ui" / "court3d_screen.dart").read_text(encoding="utf-8")
    geo = (gyoker / "ui" / "court_geometry.dart").read_text(encoding="utf-8")
    for nev, ertek in (("quizHitM", court3d.SHARED3D_QUIZ_HIT_M),
                       ("quizShotM", court3d.SHARED3D_QUIZ_SHOT_M)):
        t = re.search(rf"const double {nev} = ([0-9.]+);", geo)
        assert t and float(t.group(1)) == ertek, nev
    for kell in ("_kvizDontes = m == null ? null : _aktivDontes(m);",
                 'return {"n": k.$1, "mutat": k.$2, if (s != null) "d": s};',
                 'loves: d["best_kind"] == "shoot");'):
        assert kell in palya, kell


def test_a_kviz_eredmenye_jegyzetbe_kerul():
    """A kvíz végén az eredmény jegyzet: a szöveg a böngészőben (node) és az
    appban (Dart-teszt) ugyanaz; döntés-kvízben a döntés kockáján, a
    passzolótól a válaszokig húzott nyilakkal."""
    from handball.pipeline.view3d_html import KVIZ_JS, view3d_html

    esetek = [([["Anna", True], ["Peti", False], ["#3", True]], "s", 1),
              ([["Anna", None], ["Peti", None]], None, 0),
              ([["Anna", False]], "p", 0), ([], None, 2)]
    js = (KVIZ_JS.replace("__KV_TALALAT__", "3.0").replace("__KV_LOVES__", "6.0")
          + "const E = " + json.dumps(esetek) + ";\n"
          + "console.log(JSON.stringify(E.map(([v, f, h]) => kvizJegyzetSzoveg(v, f, h))));")
    r = subprocess.run([NODE, "-e", js], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout) == [
        "❓ Döntés-kvíz (jobb opció: lövés) — ✓ Anna, #3 · ✗ Peti · nem válaszolt: 1",
        "❓ Kvíz — válaszolt: Anna, Peti",
        "❓ Döntés-kvíz (jobb opció: passz) — ✗ Anna",
        "❓ Kvíz — nem válaszolt: 2"]

    oldal = view3d_html(_meccs())
    for kell in ("else { kvizMent(kzKviz, kzVezetoCsapat); kzKviz = null;",
                 "frame: Math.round((d ? d[0] : ido) * FPS), text: szoveg, rajz",
                 "[d[2], d[3], e.valasz[0], e.valasz[1], itelet(e) ? 0 : 2]",
                 "kzVezetoCsapat = a.csapat || [];"):
        assert kell in oldal, kell
    from pathlib import Path
    palya = (Path(__file__).resolve().parents[2] / "client" / "lib" / "ui"
             / "court3d_screen.dart").read_text(encoding="utf-8")
    for kell in ("if (_kviz?.$2 == true) _kvizMent(_csapat, _kvizDontes);",
                 "final szoveg = quizNoteText(",
                 "itelet[t.sz] == true ? 0 : 2"):
        assert kell in palya, kell


def test_a_kviz_merleg():
    """court3d.quiz_stats: a név a kulcs (kis- és nagybetű, szóköz nem
    számít), a név nélküli és a sorszámos válaszoló kimarad, kevés ítélt
    válasznál nincs arány; a sorrend az arány, az ítélt válaszok, a név.
    (A motor végpontja: test_a_kviz_merleg_a_motorban.)"""
    from handball.pipeline.court3d import QUIZ_STATS_MIN_ANSWERS, quiz_stats

    assert QUIZ_STATS_MIN_ANSWERS == 3
    jegyzet = lambda *s: {"kviz": [{"nev": n, "itelet": i} for n, i in s]}
    k = quiz_stats([
        jegyzet(("Anna", True), ("Peti", False), ("#3", True), ("", True)),
        jegyzet(("anna ", True), ("Peti", True), ("Bence", None)),
        jegyzet(("Anna", False), ("PETI", False), ("Bence", None)),
        {"text": "sima jegyzet"}, jegyzet(("Peti", True)),
        jegyzet(("Zoli", True), ("Zoli", True), ("Zoli", True)),
    ])
    assert [(r["nev"], r["kvizek"], r["itelt"], r["jo"], r["rossz"], r["arany"])
            for r in k] == [
        ("Zoli", 1, 3, 3, 0, 1.0), ("Anna", 3, 3, 2, 1, 0.667),
        ("Peti", 4, 4, 2, 2, 0.5), ("Bence", 2, 0, 0, 0, None)]
    assert quiz_stats([]) == [] and quiz_stats([{"kviz": "x"}, None]) == []


def test_a_kviz_merleg_a_motorban(tmp_path, monkeypatch):
    """A jegyzet a kvíz-sorokat megtisztítva tárolja (rossz sor kimarad,
    legfeljebb 60), a /library/quiz-stats meccseken át összegez; az oldal
    és az app a kvíz-jegyzettel küldi a sorokat; a Jegyzetek képernyő
    mutatja."""
    from pathlib import Path

    from fastapi.testclient import TestClient

    from handball.api.app import create_app

    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    app = create_app()
    for mid, datum in (("m1", "2026-09-01"), ("m2", "2026-09-08")):
        m = _meccs()
        m.meta.match_id = mid
        m.meta.date = datum
        app.state.put_match(m)
    c = TestClient(app)
    r = c.post("/matches/m1/notes", json={
        "frame": 50, "text": "❓ Döntés-kvíz", "kviz": [
            {"nev": "Anna\x07", "itelet": True}, {"nev": "Peti", "itelet": False},
            {"nev": "x", "itelet": "igen"}, "rossz", {"nev": "Bence", "itelet": None}]})
    assert r.json()["kviz"] == [{"nev": "Anna", "itelet": True},
                                {"nev": "Peti", "itelet": False},
                                {"nev": "Bence", "itelet": None}]
    assert "kviz" not in c.post("/matches/m1/notes",
                                json={"frame": 9, "text": "sima"}).json()
    assert len(c.post("/matches/m2/notes", json={
        "frame": 5, "text": "sok", "kviz": [{"nev": f"J{i}", "itelet": True}
                                           for i in range(80)]}).json()["kviz"]) == 60
    for _ in range(2):
        c.post("/matches/m2/notes", json={"frame": 7, "text": "❓", "kviz": [
            {"nev": "anna", "itelet": True}, {"nev": "Peti", "itelet": True}]})
    a = c.get("/library/quiz-stats").json()
    assert a["min_answers"] == 3
    sorok = {r["nev"].casefold(): r for r in a["players"]}
    assert (sorok["anna"]["itelt"], sorok["anna"]["jo"], sorok["anna"]["arany"]) == (3, 3, 1.0)
    assert (sorok["peti"]["itelt"], sorok["peti"]["arany"]) == (3, 0.667)
    # A legutóbbi írásmód (a későbbi meccs) a megjelenített név.
    assert sorok["anna"]["nev"] == "anna"
    assert sorok["bence"]["arany"] is None

    from handball.pipeline.view3d_html import view3d_html
    assert ('kviz: valaszolok.map(e => ({nev: e.nev || "", itelet: itelet(e)}))'
            in view3d_html(_meccs()))
    gyoker = Path(__file__).resolve().parents[2] / "client" / "lib"
    palya = (gyoker / "ui" / "court3d_screen.dart").read_text(encoding="utf-8")
    api = (gyoker / "services" / "api_client.dart").read_text(encoding="utf-8")
    jegyz = (gyoker / "ui" / "notes_screen.dart").read_text(encoding="utf-8")
    assert '{"nev": t.nev, "itelet": itelet[t.sz]}' in palya
    assert 'if (kviz != null) "kviz": kviz,' in api
    assert '"$baseUrl/library/quiz-stats"' in api
    for kell in ("_api.fetchQuizStats().then((k) {", "_kvizSor(),",
                 '"❓ Kvíz-mérleg"'):
        assert kell in jegyz, kell


def test_a_kviz_vr_bol_is_vezetheto():
    """VR-ben a vezető bal hüvelykujj-kar lenyomása a kvíz következő
    lépése (a jobb kézben és követőként a vetítés marad), és a vezető
    VR-tábláján a kvíz állása."""
    from handball.pipeline.view3d_html import view3d_html

    oldal = view3d_html(_meccs())
    for kell in ("if (vrGombEl(kulcs, 3, nyom(3))) vrKarNyomas(forras.handedness);",
                 'if (kozosMod === "vezet" && kez === "left") kvizGomb.onclick();',
                 "else vetitesAllit(!vetites);",
                 'if (kozosMod === "vezet" && kzKviz)',
                 "bal hüvelykujj-kar lenyomása — kvíz"):
        assert kell in oldal, kell


def test_a_kviz_merleg_a_kereten_es_a_nevvalaszto(tmp_path, monkeypatch):
    """A keret-lap sorai a játékos kvíz-mérlegét viszik (a név szerint —
    kis- és nagybetű, szóköz nem számít); a 3D oldal követője a keret
    nevei közül választhat; a Keret képernyő mutatja."""
    from pathlib import Path

    from fastapi.testclient import TestClient

    from handball.api.app import create_app
    from handball.pipeline.court3d import quiz_name_key
    from handball.pipeline.view3d_html import view3d_html

    assert quiz_name_key("  Kiss   Péter ") == quiz_name_key("kiss péter")
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    app = create_app()
    m = _meccs()
    app.state.put_match(m)
    c = TestClient(app)
    mid, csapat = m.meta.match_id, m.meta.home_team
    mezek = [r["jersey"] for r in c.get("/library/roster",
                                         params={"team": csapat}).json()["players"]]
    assert mezek
    c.post("/library/players", json={"team": csapat, "jersey": mezek[0],
                                     "name": "Kiss Péter"})
    c.post(f"/matches/{mid}/notes", json={"frame": 5, "text": "❓", "kviz": [
        {"nev": "kiss  péter", "itelet": True}, {"nev": "Más", "itelet": False}]})
    sorok = {r["jersey"]: r for r in
             c.get("/library/roster", params={"team": csapat}).json()["players"]}
    assert sorok[mezek[0]]["kviz"] == {"kvizek": 1, "itelt": 1, "jo": 1,
                                       "arany": None}
    assert all(r["kviz"] is None for j, r in sorok.items() if j != mezek[0])
    # A hosszú keret-név a követő oldalán SHARED3D_NAME_MAX jelre vágva megy
    # — így is párosul (a vendég csapat egyik mezén).
    from handball.pipeline.court3d import SHARED3D_NAME_MAX
    hosszu = "Kovácsné Szabó Erzsébet"
    assert len(hosszu) > SHARED3D_NAME_MAX
    vendeg = m.meta.away_team
    vmez = c.get("/library/roster", params={"team": vendeg}).json()["players"][0]["jersey"]
    c.post("/library/players", json={"team": vendeg, "jersey": vmez, "name": hosszu})
    c.post(f"/matches/{mid}/notes", json={"frame": 6, "text": "❓", "kviz": [
        {"nev": hosszu[:SHARED3D_NAME_MAX], "itelet": False}]})
    vsor = {r["jersey"]: r for r in
            c.get("/library/roster", params={"team": vendeg}).json()["players"]}
    assert vsor[vmez]["kviz"]["itelt"] == 1 and vsor[vmez]["kviz"]["jo"] == 0

    oldal = view3d_html(_meccs())
    for kell in ('id="kzNevValaszto"', 'nevValasztoMutat(kozosMod === "kovet");',
                 'fetch("/library/players")', "let KZ_NEV = ",
                 'history.replaceState(null, "", location.pathname + "?" + q.toString());'):
        assert kell in oldal, kell
    assert "__KZ_NEV_MAX__" not in oldal
    keret = (Path(__file__).resolve().parents[2] / "client" / "lib" / "ui"
             / "roster_screen.dart").read_text(encoding="utf-8")
    assert '(p["kviz"] as Map?)?["itelt"]' in keret


def test_a_dontes_kviz_a_jatekos_fejlodesben(tmp_path, monkeypatch):
    """A /players/trend pontjai a meccs döntés-kvízét is viszik (a
    keret-név szerint); név nélkül vagy kvíz nélkül None. A képernyő
    összképe és oszlopa mutatja."""
    from pathlib import Path

    from fastapi.testclient import TestClient

    from handball.api.app import create_app

    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    app = create_app()
    m = _meccs()
    app.state.put_match(m)
    c = TestClient(app)
    mid, csapat = m.meta.match_id, m.meta.home_team
    pont = lambda: c.get("/players/trend", params={"team": csapat, "jersey": 7}
                         ).json()["points"][0]
    # Név nélkül nincs kvíz.
    c.post(f"/matches/{mid}/notes", json={"frame": 5, "text": "❓", "kviz": [
        {"nev": "Kiss Péter", "itelet": True}]})
    assert pont()["quiz_answers"] is None
    c.post("/library/players", json={"team": csapat, "jersey": 7,
                                     "name": "Kiss Péter"})
    c.post(f"/matches/{mid}/notes", json={"frame": 9, "text": "❓", "kviz": [
        {"nev": "kiss péter", "itelet": False}, {"nev": "Más", "itelet": True},
        {"nev": "Kiss Péter", "itelet": None}]})
    p = pont()
    assert (p["quiz_answers"], p["quiz_correct"]) == (2, 1)

    kep = (Path(__file__).resolve().parents[2] / "client" / "lib" / "ui"
           / "player_trend_screen.dart").read_text(encoding="utf-8")
    for kell in ('_chip("döntés-kvíz: $kvJo/$kvItelt ✓ "',
                 'if (hasQuiz) _cell("kvíz", 48),',
                 '"${p["quiz_correct"] ?? 0}/${p["quiz_answers"]}"'):
        assert kell in kep, kell


def test_a_jelenlet_helye_es_neve():
    """court3d.shared3d_hely: szöveg vagy lista, dobozba szorítva, a szög
    a (−π, π]-be; rossz alaknál None. shared3d_nev: vezérlőjel nélkül,
    levágva."""
    import math

    from handball.pipeline.court3d import (SHARED3D_NAME_MAX, shared3d_hely,
                                           shared3d_nev)

    assert shared3d_hely("1,2,3,0.5") == [1.0, 2.0, 3.0, 0.5]
    assert shared3d_hely([1, 2, 3, 0.5]) == [1.0, 2.0, 3.0, 0.5]
    assert shared3d_hely([-99, 99, 99, 0]) == [-60.0, 60.0, 80.0, 0.0]
    assert shared3d_hely("0,0,0," + repr(2 * math.pi + 1)) == [0.0, 0.2, 0.0, 1.0]
    for rossz in (None, "", "1,2,3", "1,2,3,4,5", "a,2,3,4", [1, 2, None, 4],
                  "1,2,3,nan", [1, 2, 3, float("inf")], {"x": 1}):
        assert shared3d_hely(rossz) is None, rossz
    assert shared3d_nev(" Kiss\nPéter ") == "KissPéter"
    from handball.pipeline.court3d import shared3d_valasz
    assert shared3d_valasz("12.345,7,99") == [12.35, 7.0, 99.0]
    assert shared3d_valasz("99,-99,1") == [45.0, -5.0, 1.0]
    for rossz in (None, "", "1,2", "1,2,3,4", "a,2,3", "1,2,nan", "1,inf,3"):
        assert shared3d_valasz(rossz) is None, rossz
    assert shared3d_nev(None) == ""
    assert len(shared3d_nev("é" * 40)) == SHARED3D_NAME_MAX


def test_a_rovid_csapat_link(tmp_path, monkeypatch):
    """/kovet: vezető nélkül frissülő várakozó lap; vezetéskor a legutóbb
    küldő vezető meccsének követő-oldalára irányít; a hallgató vezetőhöz
    nem; az oldal és az app a rövid linket adja."""
    from pathlib import Path

    from fastapi.testclient import TestClient

    from handball.api.app import create_app
    from handball.pipeline import court3d
    from handball.pipeline.view3d_html import view3d_html

    ora = [10.0]
    monkeypatch.setattr(court3d, "shared3d_ora", lambda: ora[0])
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    app = create_app()
    for mid in ("egy", "ket to"):
        m = _meccs()
        m.meta.match_id = mid
        app.state.put_match(m)
    c = TestClient(app)
    r = c.get("/kovet", follow_redirects=False)
    assert r.status_code == 200 and 'http-equiv="refresh"' in r.text
    c.put("/matches/egy/shared3d", json={"t": 1})
    ora[0] += 1
    c.put("/matches/ket to/shared3d", json={"t": 1})
    r = c.get("/kovet", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/matches/ket%20to/view3d?kovet=1"
    ora[0] += 0.5
    c.put("/matches/egy/shared3d", json={"t": 2})
    assert c.get("/kovet", follow_redirects=False).headers["location"] == (
        "/matches/egy/view3d?kovet=1")
    ora[0] += court3d.SHARED3D_STALE_S + 1
    assert c.get("/kovet", follow_redirects=False).status_code == 200
    # Vezető nélkül a várólap a legutóbbi felvételeket kínálja (meccsektől
    # függetlenül, a legújabb elöl, legfeljebb SHARED3D_WAIT_RECS).
    assert "legutóbbi" not in c.get("/kovet").text
    allapotok = [[0, {"t": 1}], [65.4, {"t": 2}]]
    regi = c.post("/matches/egy/felvetelek",
                  json={"nev": "Régi <b>", "allapotok": allapotok}).json()
    uj = c.post("/matches/ket to/felvetelek",
                json={"nev": "Új", "allapotok": allapotok}).json()
    fajl = next(tmp_path.rglob(f"egy.felvetelek/{regi['id']}.json"))
    d = json.loads(fajl.read_text(encoding="utf-8"))
    d["letrehozva"] = "2000-01-01T00:00:00"
    fajl.write_text(json.dumps(d), encoding="utf-8")
    lap = c.get("/kovet").text
    assert lap.index(f"/matches/ket%20to/view3d?felvetel={uj['id']}") < lap.index(
        f"/matches/egy/view3d?felvetel={regi['id']}")
    assert "Régi &lt;b&gt;" in lap and "Régi <b>" not in lap
    assert "1:05" in lap
    for i in range(court3d.SHARED3D_WAIT_RECS):
        c.post("/matches/egy/felvetelek", json={"allapotok": allapotok})
    assert c.get("/kovet").text.count("view3d?felvetel=") == court3d.SHARED3D_WAIT_RECS
    # Névvel: melyiket látta (élőben vagy felvételről) — és a link viszi a nevet.
    c.post(f"/matches/ket to/felvetelek/{uj['id']}/megnezte", json={"nev": "Anna"})
    lap = c.get("/kovet", params={"nev": "anna"}).text
    # (az azonos másodperces felvételek sorrendje az azonosítón múlik)
    lathato = f"view3d?felvetel={uj['id']}" in lap
    assert lap.count("✓ láttad") == (1 if lathato else 0)
    assert (lap.count("✓ láttad") + lap.count("• még nem láttad")
            == court3d.SHARED3D_WAIT_RECS)
    assert "&amp;nev=anna" in lap
    assert "láttad" not in c.get("/kovet").text
    assert 'kzLink = location.origin + "/kovet";' in view3d_html(_meccs())
    palya = (Path(__file__).resolve().parents[2] / "client" / "lib" / "ui"
             / "court3d_screen.dart").read_text(encoding="utf-8")
    assert 'final link = "${_api.baseUrl}/kovet";' in palya


def test_a_megbeszeles_gomb():
    """A kezdőlap "Megbeszélés" gombja a 3D-t a jegyzetek (ha nincs, a
    videózandó jelenetek) vetítésével és a közös nézés vezetésével nyitja;
    a 3D fül betöltés után indítja a vezetést (a demóban nem)."""
    from pathlib import Path

    gyoker = Path(__file__).resolve().parents[2] / "client" / "lib" / "ui"
    kezdo = (gyoker / "dashboard_screen.dart").read_text(encoding="utf-8")
    palya = (gyoker / "court3d_screen.dart").read_text(encoding="utf-8")
    i = kezdo.index('label: const Text("Megbeszélés"')
    blokk = kezdo[i - 700:i]
    for kell in ("csakVideozando: true,", "csakJegyzet: true,",
                 "vetites: true,", "vezet: true))),"):
        assert kell in blokk, kell
    assert "_kezdoVetites();\n      _kezdoVezetes();" in palya
    assert "if (!widget.vezet || _demo || _matchId == null || _vezet) return;" in palya


def test_vr_magassag_es_vr_vezeto():
    """VR-ben a kamera csoportja VR_SZEM-mel lejjebb (a headset a padlótól
    méri a fejet — a rig y-ja a szemmagasság marad); a kontrollerek
    ugyanabban a csoportban; vezetőként a markolat: bal kéz Ide mindenki,
    jobb kéz mutató a sugár padló-metszetén."""
    from handball.pipeline.view3d_html import view3d_html

    oldal = view3d_html(_meccs())
    for kell in ("rig.add(vrAllo);\nvrAllo.add(kamera);",
                 'fest.xr.addEventListener("sessionstart", () => { vrAllo.position.y = -VR_SZEM; });',
                 'fest.xr.addEventListener("sessionend", () => { vrAllo.position.y = 0; });',
                 "const c = fest.xr.getController(i); vrAllo.add(c);",
                 'if (kozosMod === "vezet" && vrGombEl(kulcs, 1, nyom(1))){',
                 'if (forras.handedness === "left") ideGomb.onclick();',
                 "else vrMutat(k - 1);", "function vrMutatoPont(origo, irany){",
                 "jobb kéz mutató"):
        assert kell in oldal, kell
    assert "rig.add(kamera);" not in oldal


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
    # Több headsethez: a súgó az útmutatóra mutat, az útmutató a két utat
    # (USB, hálózat) és a hálózati megnyitás kockázatát is megmondja.
    assert "adb reverse — vagy a klub hálózatán" in oldal
    from pathlib import Path as _P
    utmutato = (_P(__file__).resolve().parents[2] / "docs"
                / "3D_PALYA.md").read_text(encoding="utf-8")
    for kell in ("### Közös nézés több headsettel", "adb reverse tcp:8000 tcp:8000",
                 "HANDBALL_HOST=0.0.0.0", "unsafely-treat-insecure-origin-as-secure",
                 "belépés nélkül"):
        assert kell in utmutato, kell
    # Az app is vezethet: ugyanaz a végpont, ugyanaz a küldési ütem.
    import re
    gyoker = Path(__file__).resolve().parents[2] / "client" / "lib"
    palya = (gyoker / "ui" / "court3d_screen.dart").read_text(encoding="utf-8")
    api = (gyoker / "services" / "api_client.dart").read_text(encoding="utf-8")
    assert '"$baseUrl/matches/$matchId/shared3d"' in api
    ertek = re.search(r"static const double _vezetKuldS = ([0-9.]+);", palya)
    assert ertek and float(ertek.group(1)) == court3d.SHARED3D_SEND_S
    assert 'json["followers"]' in api
    for kell in ("_vezetKuld(now);", "rajz: encodeDrawing(_rajzok),",
                 '"📡 Vezetsz · $_kovetok követő"',
                 '"${_api.baseUrl}/kovet"',
                 "_api.deleteShared3d(id)"):
        assert kell in palya, kell
    assert (f"const KZ_KULD = {float(court3d.SHARED3D_SEND_S)!r}, KZ_KERD = "
            f"{float(court3d.SHARED3D_POLL_S)!r}, KZ_TURES = "
            f"{float(court3d.SHARED3D_TOLERANCE_S)!r};") in oldal


def test_a_kocka_vegpont_videoi_kidobva_is_jok(tmp_path, monkeypatch):
    """A kocka-végpont videó-gyorsítótára a plafonnál (itt 1) a régit
    zárja be: két meccs váltakozó kéréseire is mindig a jó kocka jön (a
    bezárt olvasóból nem olvas), a hibás képrátájú videónál sem olvas
    végig ezreket (SEQ_READ_MAX_FRAMES)."""
    import cv2
    import numpy as np
    from fastapi.testclient import TestClient

    from handball.api.app import create_app
    from handball.pipeline import video_frames

    monkeypatch.setattr(video_frames, "FRAME_CAPS_MAX", 1)
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path / "adat"))
    app = create_app()
    c = TestClient(app)
    for nev, alap in (("a", 0), ("b", 120)):
        ut = tmp_path / f"{nev}.mp4"
        w = cv2.VideoWriter(str(ut), cv2.VideoWriter_fourcc(*"mp4v"), 25.0,
                            (320, 160))
        for i in range(60):
            w.write(np.full((160, 320, 3), alap + i * 2, np.uint8))
        w.release()
        m = _meccs()
        m.meta.match_id = f"kocka-{nev}"
        m.meta.video_path = str(ut)
        m.meta.start_frame = 0
        m.meta.stride = 1
        app.state.put_match(m)
    for nev, alap in (("a", 0), ("b", 120), ("a", 0), ("b", 120)):
        r = c.get(f"/matches/kocka-{nev}/frame", params={"t": 10, "w": 160})
        assert r.status_code == 200, nev
        img = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
        assert abs(float(img.mean()) - (alap + 20)) < 6, nev

    class Hamis:
        """Olvasó, amely 90 000 fps-t mond (hibás konténer)."""
        def __init__(self, cap):
            self.cap, self.tekeres, self.olvasas = cap, 0, 0

        def get(self, prop):
            if prop == cv2.CAP_PROP_FPS:
                return 90000.0
            return self.cap.get(prop)

        def set(self, *a):
            self.tekeres += 1
            return self.cap.set(*a)

        def grab(self):
            self.olvasas += 1
            return self.cap.grab()

        def read(self):
            return self.cap.read()

    # (a 60 kockás próbavideón a korlát 20: a 90 000 fps-es "2 mp" ennél
    # sokkal több lenne — a korlát dönt, tekerünk)
    monkeypatch.setattr(video_frames, "SEQ_READ_MAX_FRAMES", 20)
    h = Hamis(cv2.VideoCapture(str(tmp_path / "a.mp4")))
    assert video_frames.read_jpeg(h, 50, 160) is not None
    assert h.tekeres == 1 and h.olvasas == 0  # tekert, nem olvasott végig
    h.cap.release()


def test_a_reszleges_taktikai_kulcs_nem_kerul_tarba(tmp_path, monkeypatch):
    """Ha egy csapat felderítése hibázik, a 3D kulcsok részleges eredménye
    NEM kerül az eredmény-tárba: a következő kérés újrapróbál (és a javult
    felderítéssel teljes eredményt ad)."""
    from fastapi.testclient import TestClient

    import handball.api.app as app_mod
    from handball.api.app import create_app
    from handball.pipeline import court3d

    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("HANDBALL_WARM_RESULTS", "0")
    hivasok = []

    def kamu_kulcsok(match, reports=None):
        hivasok.append(sorted(reports or {}))
        return {"breakpoints": {"home": [], "away": []},
                "stoppers": {"home": [], "away": []}}

    monkeypatch.setattr(court3d, "tactical_keys_by_team", kamu_kulcsok)
    eredeti = app_mod.scout_team
    hibazik = [True]

    def kamu_felderites(match, team, *a, **kw):
        if hibazik[0] and getattr(team, "value", team) == "away":
            raise RuntimeError("átmeneti hiba")
        return eredeti(match, team, *a, **kw)

    monkeypatch.setattr(app_mod, "scout_team", kamu_felderites)
    m = _meccs()
    app = create_app()
    app.state.put_match(m)
    c = TestClient(app)
    url = f"/matches/{m.meta.match_id}/defence-timeline"
    assert c.get(url).status_code == 200
    hibazik[0] = False
    assert c.get(url).status_code == 200
    # A második kérés újraszámolt (a részleges nem került tárba), és most
    # mindkét csapat felderítése megvolt.
    assert len(hivasok) >= 2 and hivasok[-1] == ["away", "home"]


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



def test_kerdesem_van(tmp_path, monkeypatch):
    """✋ A követő jelzése a jelenlét-sorban: a vezető (PUT válasz) és a
    többi követő is látja; kéz le — eltűnik; a régi jelzés nem marad a
    visszatérőn. Az oldal (gomb, H, VR-markolat, felirat, tábla) és az app
    (fej-felirat, Vezetsz-gomb)."""
    from pathlib import Path

    from fastapi.testclient import TestClient

    from handball.api.app import create_app
    from handball.pipeline import court3d
    from handball.pipeline.view3d_html import view3d_html

    ora = [10.0]
    monkeypatch.setattr(court3d, "shared3d_ora", lambda: ora[0])
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    app = create_app()
    m = _meccs()
    m.meta.match_id = "kez"
    app.state.put_match(m)
    c = TestClient(app)
    url = "/matches/kez/shared3d"
    c.put(url, json={"t": 1})
    c.get(url, params={"kid": "a1", "hely": "1,1.7,2,0", "nev": "Anna", "kez": "1"})
    b = c.get(url, params={"kid": "b2", "hely": "3,1.7,2,0", "nev": "Peti"}).json()
    assert [(e["nev"], e.get("kez", False)) for e in b["csapat"]] == [("Anna", True)]
    v = c.put(url, json={"t": 1}).json()
    assert [(e["nev"], e.get("kez", False)) for e in v["csapat"]] == [
        ("Anna", True), ("Peti", False)]
    c.get(url, params={"kid": "a1", "hely": "1,1.7,2,0", "nev": "Anna"})
    v = c.put(url, json={"t": 1}).json()
    assert not any(e.get("kez") for e in v["csapat"])

    oldal = view3d_html(_meccs())
    for kell in ('id="kezGomb"', '+ (kzKez ? "&kez=1" : "")',
                 'cimke: (e.kez ? "✋ " : "") + (e.nev || ("#" + e.sz)),',
                 'if (e.code === "KeyH" && kozosMod === "kovet"){ kezAllit(!kzKez); return; }',
                 'if (kozosMod === "kovet" && vrGombEl(kulcs, 1, nyom(1))) kezAllit(!kzKez);',
                 'sorok.unshift("✋ Kérdése van: " + kzKezek().join(", "));',
                 '+ (kezek.length ? " · ✋ " + kezek.join(", ") : "")'):
        assert kell in oldal, kell
    gyoker = Path(__file__).resolve().parents[2] / "client" / "lib" / "ui"
    palya = (gyoker / "court3d_screen.dart").read_text(encoding="utf-8")
    assert "text: t.felirat," in palya
    assert "_csapat.any((t) => t.kez)" in palya
    geo = (gyoker / "court_geometry.dart").read_text(encoding="utf-8")
    assert 'valasz: valasz, kez: e["kez"] == true));' in geo



def test_a_csapatnev_nem_tor_ki_a_szkriptbol():
    """BIZTONSÁG: "</script>"-et tartalmazó csapatnév (a könyvtár-import
    más gépről is hozhat ilyet) nem tör ki a beágyazott adatból, és az
    innerHTML-es feliratok a nevet escape-elve írják."""
    import re

    from handball.pipeline.view3d_html import view3d_html

    m = _meccs()
    m.meta.home_team = "Rossz</script><script>window.__xss=1</script>"
    m.meta.away_team = "<img src=x onerror=window.__xss=2>"
    oldal = view3d_html(m)
    # A beágyazott adat a modul-szkripten belül marad: a "</script>" csak
    # a valódi szkript-végeken áll.
    adat = oldal[oldal.index("const ADAT = "):]
    adat = adat[:adat.index("\n")]
    assert "</script>" not in adat and "<\\/script>" in adat
    assert "window.__xss=1</script>" not in oldal
    # Az innerHTML-es feliratok escape-elnek (nincs nyers csapatnév).
    for sor in re.findall(r".*innerHTML\s*=.*", oldal):
        assert "ADAT.home" not in sor.replace("hx(hazai ? ADAT.home", ""), sor
    for kell in ('"<b>" + hx(hazai ? ADAT.home : ADAT.away)',
                 '"Fal (" + hx(csapat) + ", "',
                 '"Most: " + hx(csapat) + " védekezik — <b>" + hx(elo.cimke)'):
        assert kell in oldal, kell



def test_vr_snap_fordulas():
    """VR: a jobb kar oldalra billentése 30°-os ugrással fordít (él-
    érzékeléssel, a fej körül), a bal kar mozgat."""
    from handball.pipeline.view3d_html import view3d_html

    oldal = view3d_html(_meccs())
    for kell in ("const VR_FORDUL_FOK = 30, VR_FORDUL_KUSZOB = 0.7;",
                 'if (kez === "right"){',
                 "if (ki && !vrFordulKi) vrFordul(ax > 0 ? -1 : 1);",
                 'vrKar(forras.handedness || "", gp.axes[2], gp.axes[3], dt);'):
        assert kell in oldal, kell



def test_a_panel_osszecsukhato_es_a_sugo_megjegyzett():
    """A vezérlőpanel ☰ / M-mel összecsukható (megjegyezve); a súgó csak
    1600 px fölött nyílik magától, és a választás megjegyzett."""
    from handball.pipeline.view3d_html import view3d_html

    oldal = view3d_html(_meccs())
    for kell in ('<button id="panelGomb"', "#eszkoz.csukva{display:none}",
                 'if (e.code === "KeyM"){ panelAllit(!panelCsukva); return; }',
                 'localStorage.getItem("sm3d.sugo")', "return innerWidth >= 1600;",
                 "sugoNyitva = !sugoNyitva; sugoMent(); sugoAllit();"):
        assert kell in oldal, kell
    assert "let sugoNyitva = innerWidth >= 1200;" not in oldal
