"""
Tesztek a FORMA-IRÁNYRA a játékos-görbén (/players/trend "trend").

A görbe SZÁMOKAT mutatott meccsről meccsre — a játékos viszont egyetlen
dolgot akar tudni: jó irányba megy-e. Azt pedig egy pontsorból kinézni
nem lehet, mert minden második meccs jobb az előzőnél.

Két csapda van benne:
  - kevés meccsből irányt mondani HAZUDIK (egy jó meccs bármikor jön),
  - a kis változást iránynak nevezni HAZUDIK (az zaj).
Mindkettőre van itt teszt.

Futtatás:
    python -m pytest tests/test_forma_irany.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

pytest.importorskip("fastapi", reason="fastapi nincs telepítve")

from handball.api.app import create_app  # noqa: E402


def _irany(pontok: list) -> dict:
    """A belső forma-irány számoló, a végponton kívülről hívva.

    Az app gyári függvénye zárja körül, ezért egy üres alkalmazást
    építünk, és a saját routerén keresztül nem jutnánk el ide — a
    számolót ezért közvetlenül a modulból emeljük ki.
    """
    app = create_app()
    fn = getattr(app.state, "forma_irany", None)
    assert fn is not None, "a forma-irány számoló nincs kivezetve"
    return fn(pontok)


def _sor(ertekek, mezo="shot_pct"):
    return [{"match_id": f"m{i}", "date": f"2026-01-{i + 1:02d}",
             mezo: v} for i, v in enumerate(ertekek)]


def test_a_javulas_javulasnak_latszik():
    ki = _irany(_sor([30.0, 32.0, 31.0, 55.0, 58.0, 56.0]))
    assert ki["shot_pct"]["verdict"] == "javul"
    assert ki["shot_pct"]["change_pct"] > 0


def test_a_romlas_romlasnak_latszik():
    ki = _irany(_sor([60.0, 58.0, 62.0, 30.0, 28.0, 31.0]))
    assert ki["shot_pct"]["verdict"] == "romlik"


def test_keves_meccsbol_nincs_iteles():
    """Két-két meccsből nem szabad "javulsz"-t mondani: egy jó meccs
    bármikor jön, és a játékos elhiszi."""
    ki = _irany(_sor([30.0, 32.0, 55.0, 58.0]))
    assert "shot_pct" not in ki


def test_a_kis_valtozas_nem_irany():
    """A zajsávon belüli mozgás NEM irány — sose hallgatólagos
    "változatlan", hanem None ítélet."""
    ki = _irany(_sor([50.0, 51.0, 49.0, 51.0, 50.0, 52.0]))
    assert ki["shot_pct"]["verdict"] is None
    # A SZÁMOK ettől még ott vannak: a játékos maga eldöntheti.
    assert ki["shot_pct"]["recent"] and ki["shot_pct"]["before"]


def test_a_futomunka_nincs_az_iranyok_kozt():
    """ŐR: a méter/percnél a TÖBB nem "jobb", csak több.

    A poszt dönti el, mennyi futómunka kell — egy "romlik" ítélet a
    beállóra, aki kevesebbet fut, mint a szélső, egyszerűen hazugság
    lenne. Ezért a futómunka szándékosan kimarad az irányokból.
    """
    pontok = [{"match_id": f"m{i}", "date": f"2026-01-{i + 1:02d}",
               "distance_per_min": v}
              for i, v in enumerate([100.0, 101.0, 99.0, 150.0, 155.0,
                                     152.0])]
    assert _irany(pontok) == {}


def test_a_hiányzo_ertekek_nem_szamitanak_nullanak():
    """A None NEM nulla: a kimaradt meccs kihagyandó, nem beszámítandó.

    Ha nullaként számítanánk, egy sérülés miatt kihagyott meccs
    "romlásnak" látszana — pont annak a játékosnak, akinek a
    visszatérésnél a legkevésbé kell.
    """
    ertekek = [50.0, None, 52.0, 51.0, 55.0, None, 58.0, 56.0]
    ki = _irany(_sor(ertekek))
    assert ki["shot_pct"]["before"] == pytest.approx(51.0, abs=0.01)
# ---- A NYOMTATVÁNY sem mondhat kevesebbet ----------------------------


def test_a_szezon_lap_is_viszi_a_forma_iranyt():
    """A lapot a játékos TESZI EL.

    Ha a képernyő megmondja, hogy javul, a nyomtatvány pedig nem, a
    papír kevesebbet ér, mint a program — és pont az marad ki, amiért
    elteszi.
    """
    from handball.pipeline.report_html import player_season_html

    pontok = [{"match_id": f"m{i}", "date": f"2026-01-{i + 1:02d}",
               "opponent": "X", "goals": 3, "shots": 6, "minutes": 40.0,
               "distance_m": 4000.0, "top_speed_ms": 7.0,
               "sprint_count": 5}
              for i in range(6)]
    trend = {"shot_pct": {"recent": 55.0, "before": 31.0,
                          "change_pct": 77.4, "verdict": "javul"}}
    html = player_season_html("A", 7, pontok, "Kovács", None,
                              trend=trend, trend_window=3)
    assert "Javulok vagy romlok" in html
    assert "javul" in html
    assert "utolsó 3 meccs" in html


def test_a_nyomtatvany_az_iteles_nelkuli_esetet_is_kimondja():
    """Ítélet nélkül a SZÁMOK kimennek, de a lap kiírja, hogy zaj —
    a néma szám ítéletnek látszana a papíron is."""
    from handball.pipeline.report_html import player_season_html

    pontok = [{"match_id": "m1", "date": "2026-01-01", "opponent": "X",
               "goals": 3, "shots": 6, "minutes": 40.0,
               "distance_m": 4000.0, "top_speed_ms": 7.0,
               "sprint_count": 5}]
    html = player_season_html("A", 7, pontok, None, None,
                              trend={"goals": {"recent": 3.0,
                                               "before": 2.9,
                                               "change_pct": 3.4,
                                               "verdict": None}})
    assert "nem irány, zaj" in html


def test_trend_nelkul_a_lap_valtozatlan():
    """Visszafelé kompatibilis: trend nélkül nincs szakasz — nem üres
    címsor, hanem semmi."""
    from handball.pipeline.report_html import player_season_html

    pontok = [{"match_id": "m1", "date": "2026-01-01", "opponent": "X",
               "goals": 1, "shots": 2, "minutes": 30.0,
               "distance_m": 3000.0, "top_speed_ms": 7.0,
               "sprint_count": 3}]
    html = player_season_html("A", 7, pontok)
    assert "Javulok vagy romlok" not in html
