"""
Tesztek a futtatható belépési pontra (scripts/run_pipeline.py).

A szkript a kész adatszerződést (Tracking JSON) demonstrálja egy kis
szintetikus meccsen; eddig egyszer sem futott a csomagban.

Futtatás:
    python -m pytest tests/test_run_pipeline.py -q
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (  # noqa: E402
    Match, PositionSource, Team,
)
from scripts import run_pipeline as rp  # noqa: E402


def test_build_demo_match_a_szerzodes_minden_elemet_megmutatja():
    """A minta-meccs két kockája a szerződés minden elemét hordozza:
    fejléc, két csapat, mezszám, labda, és a második kockán egy BECSÜLT
    (képből kicsúszott) játékos a megbízhatóságával."""
    m = rp.build_demo_match()
    assert m.meta.match_id == "demo-001"
    assert (m.meta.home_team, m.meta.away_team) == ("Hazai KC", "Vendég SE")
    assert m.meta.fps == 25.0
    assert (m.meta.frame_width, m.meta.frame_height) == (1920, 1080)
    assert [f.t for f in m.frames] == [0, 1]
    for f in m.frames:
        assert {p.team for p in f.players} == {Team.HOME, Team.AWAY}
        assert all(p.jersey_number is not None for p in f.players)
        assert f.ball is not None
    assert all(p.source == PositionSource.MEASURED
               for p in m.frames[0].players)
    becsult = [p for p in m.frames[1].players
               if p.source == PositionSource.ESTIMATED]
    assert [(p.track_id, p.team, p.confidence) for p in becsult] == [
        (11, Team.AWAY, 0.6)]


def test_build_demo_match_json_korbe_megy():
    """A minta-meccs JSON-ra és vissza KÖRBE megy — ez a backend és a
    kliens közti szerződés; minden hívás friss, független példányt ad."""
    m = rp.build_demo_match()
    vissza = Match.from_dict(json.loads(m.to_json()))
    assert vissza.to_dict() == m.to_dict()
    masik = rp.build_demo_match()
    masik.frames.clear()
    assert len(rp.build_demo_match().frames) == 2


def test_main_fajl_nelkul_a_json_es_a_statisztika_a_kimenetre_megy(capsys):
    """Útvonal nélkül a Tracking JSON a kimenetre megy, utána a
    játékosonkénti statisztika (a becsült kocka nem fut távot)."""
    assert rp.main(["run_pipeline"]) == 0
    ki = capsys.readouterr().out
    json_resz, stat_resz = ki.split("\n--- Statisztika (demo) ---\n")
    assert json.loads(json_resz) == rp.build_demo_match().to_dict()
    sorok = stat_resz.strip().splitlines()
    assert [s.split(":")[0].strip() for s in sorok] == ["#1", "#2", "#11"]
    assert "mért=2, becsült=0" in sorok[0]
    assert "táv=0.00 m" in sorok[2] and "mért=1, becsült=1" in sorok[2]


def test_main_utvonallal_fajlba_ir(tmp_path, capsys):
    """Útvonallal a JSON a fájlba kerül (a kimenetre csak a jelzés és a
    statisztika megy), és a fájlból a meccs visszaolvasható."""
    ki_fajl = tmp_path / "ki.json"
    assert rp.main(["run_pipeline", str(ki_fajl)]) == 0
    ki = capsys.readouterr().out
    assert ki.startswith(f"Tracking JSON kiírva: {ki_fajl}\n")
    assert "match_id" not in ki
    m = Match.from_dict(json.loads(ki_fajl.read_text(encoding="utf-8")))
    assert m.to_dict() == rp.build_demo_match().to_dict()
    assert "Hazai KC" in ki_fajl.read_text(encoding="utf-8")   # ékezet épen
