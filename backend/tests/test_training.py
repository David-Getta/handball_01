"""
Tesztek az edzés-fókusz javaslatokra (training.py).

A pálya 40x20 m; a HAZAI a +x (x=40) kapu felé támad.

Futtatás:
    python -m pytest tests/test_training.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.training import training_focus


def _meta(fps=25.0):
    return MatchMeta(match_id="tr", home_team="H", away_team="A", fps=fps)


def _pl(track_id, team, x, y):
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0)


def _shots_match(n=4, goal=True, defender_far=True):
    """n hazai lövés a +x kapura (gól vagy mellé), a vendég védő távol
    (szabad lövő) vagy szorosan."""
    frames = []
    t = 0
    for _ in range(n):
        for i in range(7):
            players = [_pl(1, Team.HOME, 33.0, 10.0),
                       _pl(20, Team.AWAY, 33.0, 16.0 if defender_far else 10.7)]
            y = 10.0 if goal else 5.0
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=34.0 + i, y=y, confidence=1.0)))
            t += 1
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 20
    return Match(_meta(), frames)


def test_free_shots_trigger_defense_focus():
    """Sok szabadon hagyott lövő → a VÉDEKEZŐ csapat fedezés-fókuszt kap."""
    tf = training_focus(_shots_match(goal=True, defender_far=True))
    away = tf["away"]
    assert any(it["title"] == "Fedezés-fegyelem" for it in away)
    # A zóna-fókusz is megjelenik (2+ kapott gól a beállóból).
    assert any(it["title"].startswith("Zóna-védekezés") for it in away)
    # Minden javaslat indoklással és gyakorlattal jön.
    for it in away:
        assert it["why"] and it["drill"] and it["area"]


def test_missed_chances_trigger_finishing_focus():
    """Nagy értékű, de kihagyott helyzetek → befejezés-fókusz a támadónak."""
    tf = training_focus(_shots_match(goal=False, defender_far=False))
    assert any(it["title"] == "Befejezés nyomás alatt" for it in tf["home"])


def test_empty_match_gives_empty_lists():
    m = Match(_meta(), [Frame(t=i, players=[], ball=None) for i in range(10)])
    tf = training_focus(m)
    assert tf == {"home": [], "away": []}


def test_focus_list_is_capped():
    """A lista rangsorolt és legfeljebb 5 elemű (a fókusz kevés elem)."""
    tf = training_focus(_shots_match(goal=True, defender_far=True))
    assert len(tf["away"]) <= 5 and len(tf["home"]) <= 5


def test_library_recurring_focus_endpoint(tmp_path):
    """A könyvtár-szintű összesítés: az azonos csapatnévvel két meccsen is
    előjövő gyengeség "visszatérő"-ként, darabszámmal jelenik meg."""
    import json
    import os
    import tempfile

    import pytest

    TestClient = pytest.importorskip(
        "fastapi.testclient", reason="fastapi nincs telepítve").TestClient

    tmp = tempfile.mkdtemp(prefix="hb_focus_")
    os.environ["HANDBALL_DATA_DIR"] = tmp
    from pathlib import Path as _P

    from handball.api.app import create_app

    mdir = _P(tmp) / "data" / "matches"
    mdir.mkdir(parents=True, exist_ok=True)
    for i in (1, 2):
        m = _shots_match(goal=True, defender_far=True)
        m.meta.match_id = f"m{i}"
        m.meta.home_team = "Veszprém"
        m.meta.away_team = "Szeged"  # ők kapják a szabad lövéseket
        (mdir / f"m{i}.json").write_text(m.to_json(), encoding="utf-8")

    client = TestClient(create_app())
    r = client.get("/library/training-focus").json()
    assert r["matches"]["Szeged"] == 2
    szeged = r["teams"]["Szeged"]
    fed = next(it for it in szeged if it["title"] == "Fedezés-fegyelem")
    assert fed["count"] == 2
    assert fed["why"] and fed["drill"]
    # A hazai (Veszprém) oldalon nincs visszatérő gyengeség ebből a jelből.
    assert "Veszprém" not in r["teams"] or all(
        it["title"] != "Fedezés-fegyelem" for it in r["teams"]["Veszprém"])


def test_front_turnovers_trigger_safe_finishing_focus():
    """6 hazai labdaeladás a támadó harmadban (x=35, a +x kapu előtt) →
    'Biztonságos befejezés' fókusz a hazaiaknak."""
    frames = []
    t = 0
    for _ in range(6):
        for _ in range(3):
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 35.0, 10.0)],
                                ball=Ball(x=35.0, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(3):
            frames.append(Frame(t=t, players=[_pl(11, Team.AWAY, 35.0, 10.0)],
                                ball=Ball(x=35.0, y=10.0, confidence=1.0)))
            t += 1
    focus = training_focus(Match(_meta(), frames))
    assert any("Biztonságos befejezés" in f_["title"] for f_ in focus["home"])
    # A vendég ugyanitt a SAJÁT harmadában veszít labdát → nála nem szól.
    assert not any("Biztonságos befejezés" in f_["title"]
                   for f_ in focus["away"])


def test_weak_attack_type_triggers_focus():
    """Sok felállt támadás gól nélkül → befejezés-fókusz az adott típusra."""
    frames = []
    t = 0
    # 4 felállt támadás lövés/gól nélkül (topogás a 9 m körül).
    for _ in range(4):
        for i in range(int(18 * 25)):  # 18 mp felállt
            x = 30.0 + 0.5 * (i % 3)
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, x, 10.0),
                _pl(2, Team.HOME, x - 2.0, 6.0),
                _pl(20, Team.AWAY, 37.0, 8.0),
                _pl(21, Team.AWAY, 37.0, 12.0)],
                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(30):  # szünet a következő támadás előtt
            frames.append(Frame(t=t, players=[], ball=None))
            t += 1
    tf = training_focus(Match(_meta(), frames))
    home = tf["home"]
    assert any(it["title"].startswith("Befejezés: felállt") for it in home)
