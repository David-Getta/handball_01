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
                "ido + dt * sebesseg"):
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
                "fetchXg", "Lövéstérkép: ki", "_labdaNyom", "Labda-nyom"):
        assert jel in kepernyo, jel
    # A kör sugara ugyanaz a képlet, mint a böngészőben (0,22 + 0,5·xG).
    assert "0.22 + 0.5 *" in kepernyo and "0.22 + 0.5 * Math.min" in \
        __import__("handball.pipeline.view3d_html",
                   fromlist=["view3d_html"]).view3d_html(_meccs())
