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


def test_lost_clutch_triggers_endgame_focus():
    """20 perces meccs, szoros állásról a hajrában 0-2 → a hazai
    'Szoros végjáték gyakorlása' fókuszt kap."""
    from handball.models.tracking import Ball
    fps = 25.0
    total = int(1200 * fps)
    win_start = total - int(300 * fps)

    def goal_frames(t0, toward_home_goal):
        out = []
        for i in range(8):
            x = max(6.4 - i, 0.0) if toward_home_goal else min(33.6 + i, 40.0)
            out.append(Frame(t=t0 + i, players=[],
                             ball=Ball(x=x, y=10.0, confidence=1.0)))
        return out

    frames = {}
    for fr in (goal_frames(100, False) + goal_frames(400, True)
               + goal_frames(win_start + 200, True)
               + goal_frames(win_start + 1500, True)):
        frames[fr.t] = fr
    all_frames = [frames.get(t, Frame(t=t, players=[],
                                      ball=Ball(x=20.0, y=10.0,
                                                confidence=1.0)))
                  for t in range(total)]
    focus = training_focus(Match(_meta(), all_frames))
    assert any("végjáték" in f_["title"].lower() for f_ in focus["home"])
    assert not any("végjáték" in f_["title"].lower() for f_ in focus["away"])


def test_blocked_shots_trigger_shot_prep_focus():
    """3 hazai lövést blokkol a vendég fal → a hazai 'Lövés a blokk
    ellen' fókuszt kap."""
    from handball.models.tracking import Ball

    frames = []
    t = 0
    blocker = _pl(20, Team.AWAY, 32.5, 10.0)
    shooter = _pl(1, Team.HOME, 28.0, 10.0)
    for _ in range(3):
        # Lövés-tempójú repülés a +x kapu felé, ami a védőn visszapattan.
        for x in [29.0, 30.2, 31.4, 32.4, 31.0, 29.5, 28.0]:
            frames.append(Frame(t=t, players=[shooter, blocker],
                                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(15):  # szünet a blokk-debounce miatt
            frames.append(Frame(t=t, players=[shooter, blocker],
                                ball=Ball(x=25.0, y=10.0, confidence=1.0)))
            t += 1
    focus = training_focus(Match(_meta(), frames))
    assert any("blokk" in f_["title"].lower() for f_ in focus["home"])
    assert not any("blokk" in f_["title"].lower() for f_ in focus["away"])


def test_second_half_fade_triggers_conditioning_focus():
    """Félidőben 5-1, végén 5-6 (a hazai a 2. félidőt 0-5-re bukja) →
    'Második félidei visszaesés' fókusz a hazainak. A half_t-t nem
    mockoljuk: a fixture 70 mp üres-játékos szünetet tartalmaz középen,
    amit a detect_halftime felismer."""
    from handball.models.tracking import Ball

    def goal_frames(t0, toward_home_goal):
        out = []
        for i in range(8):
            x = max(6.4 - i, 0.0) if toward_home_goal else min(33.6 + i, 40.0)
            out.append(Frame(t=t0 + i, players=[],
                             ball=Ball(x=x, y=10.0, confidence=1.0)))
        return out

    fps = 25.0
    total = int(400 * fps)  # 400 mp
    half = total // 2
    frames = {}
    # 1. félidő: 5 hazai + 1 vendég gól (30 kockánként, hogy ne olvadjanak
    # össze a debounce-ban).
    t = 0
    for _ in range(5):
        for fr in goal_frames(t, False):
            frames[fr.t] = fr
        t += 40
    for fr in goal_frames(t, True):
        frames[fr.t] = fr
    # 2. félidő: 5 vendég gól.
    t = half + int(36 * fps)  # rögtön a szünet-ablak után kezdve
    for _ in range(5):
        for fr in goal_frames(t, True):
            frames[fr.t] = fr
        t += 40

    all_frames = []
    for i in range(total):
        if i in frames:
            all_frames.append(frames[i])
            continue
        # A szünet (a felezőpont körüli 70 mp) üres; máskor 6 mért játékos
        # van a pályán, hogy az aktivitás magas legyen.
        in_break = abs(i - half) <= int(35 * fps)
        players = [] if in_break else [
            _pl(k, Team.HOME if k < 4 else Team.AWAY, 10.0 + k, 5.0)
            for k in range(1, 8)]
        all_frames.append(Frame(t=i, players=players,
                                ball=None if in_break
                                else Ball(x=20.0, y=10.0, confidence=1.0)))
    focus = training_focus(Match(_meta(), all_frames))
    assert any("visszaesés" in f_["title"].lower() for f_ in focus["home"])
    assert not any("visszaesés" in f_["title"].lower()
                   for f_ in focus["away"])


def test_slow_response_triggers_mental_focus():
    """3 lassan (200+ mp) megválaszolt kapott gól → 'Újraindulás' fókusz."""
    from handball.models.tracking import Ball

    def goal_frames(t0, toward_home_goal):
        out = []
        for i in range(8):
            x = max(6.4 - i, 0.0) if toward_home_goal else min(33.6 + i, 40.0)
            out.append(Frame(t=t0 + i, players=[],
                             ball=Ball(x=x, y=10.0, confidence=1.0)))
        return out

    frames = {}
    t = 0
    # 3 kör: vendég gól, majd a hazai ~200 mp múlva válaszol.
    for _ in range(3):
        for fr in goal_frames(t, True):
            frames[fr.t] = fr
        t += int(200 * 25)
        for fr in goal_frames(t, False):
            frames[fr.t] = fr
        t += 40
    total = t + 50
    all_frames = [frames.get(i, Frame(t=i, players=[],
                                      ball=Ball(x=20.0, y=10.0,
                                                confidence=1.0)))
                  for i in range(total)]
    focus = training_focus(Match(_meta(), all_frames))
    assert any("jraindul" in f_["title"] for f_ in focus["home"])
    # A vendég gyorsan "válaszolt" (a hazai gólok után ~40 kockával) —
    # nála nem szólal meg a szabály.
    assert not any("jraindul" in f_["title"] for f_ in focus["away"])


def test_barren_long_attacks_trigger_shot_clock_focus():
    """4 rövid gólos + 4 hosszú gól nélküli hazai támadás → 'Befejezés
    időkorláttal' fókusz."""
    from handball.models.tracking import Ball

    frames = []
    t = 0
    # 4 rövid (gyors, gólos) támadás: lerohanás + lövés-gól.
    for _ in range(4):
        seg = _attack_frames_local(t, 4.0, 22.0, 33.0)
        frames += seg
        t += len(seg)
        for i in range(7):
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 33.0, 10.0)],
                                ball=Ball(x=34.0 + i, y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(25):
            frames.append(Frame(t=t, players=[], ball=None))
            t += 1
    # 4 hosszú (40 mp-es), lövés nélküli felállt támadás.
    for _ in range(4):
        seg = _attack_frames_local(t, 40.0, 30.0, 31.0)
        frames += seg
        t += len(seg)
        for _ in range(25):
            frames.append(Frame(t=t, players=[], ball=None))
            t += 1
    focus = training_focus(Match(_meta(), frames))
    assert any("időkorlát" in f_["title"].lower() for f_ in focus["home"])
    assert not any("időkorlát" in f_["title"].lower()
                   for f_ in focus["away"])


def _attack_frames_local(t0, duration_s, x_from, x_to, fps=25.0):
    """Hazai birtoklás a +x térfélen: a labdás játékos x_from→x_to közt
    mozog duration_s ideig (támadó-fázisú szakasz)."""
    from handball.models.tracking import Ball
    n = int(duration_s * fps)
    out = []
    for i in range(n):
        x = x_from + (x_to - x_from) * (i / max(1, n - 1))
        out.append(Frame(t=t0 + i,
                         players=[_pl(1, Team.HOME, x, 10.0)],
                         ball=Ball(x=x, y=10.0, confidence=1.0)))
    return out


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


def test_missed_big_chances_trigger_ziccer_focus():
    """3+ kihagyott ziccer (nagy xG, gól nélkül) → Ziccer-befejezés fókusz
    a támadó csapatnak."""
    frames = []
    t0 = 0.0
    for _ in range(3):
        # A labda a lövőtől (37, 10) indul — így a lövő azonosítható —,
        # majd a kapu mellé hajlik el (nincs gól, nincs kapus).
        for i in range(7):
            frames.append(Frame(
                t=t0 + i,
                players=[_pl(1, Team.HOME, 37.0, 10.0)],
                ball=Ball(x=min(37.4 + 0.6 * i, 40.0), y=10.0 - i * 1.0,
                          confidence=1.0)))
        frames.append(Frame(t=t0 + 8, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t0 += 40.0
    tf = training_focus(Match(_meta(), frames))
    item = next((it for it in tf["home"]
                 if it["title"] == "Ziccer-befejezés"), None)
    assert item is not None
    assert "3 nagy helyzet" in item["why"]
    assert tf["away"] == [] or all(
        it["title"] != "Ziccer-befejezés" for it in tf["away"])


def test_slow_outlets_trigger_restart_focus():
    """3 mért, de lassú kapus-indítás → "Gyors indítás védés után" fókusz
    a védő (away) oldalon."""
    def keeper():
        gk = _pl(30, Team.AWAY, 39.0, 10.0)
        gk.role = "kapus"
        return gk

    frames = []
    t = 0
    for _ in range(3):
        # Fogott lövés: a labda a kapusnál (38,8 m) megáll...
        for i in range(8):
            frames.append(Frame(
                t=t,
                players=[_pl(1, Team.HOME, 37.0, 10.0), keeper()],
                ball=Ball(x=min(37.4 + 0.6 * i, 38.8), y=10.0,
                          confidence=1.0)))
            t += 1
        # ...majd a labda ~8 mp-ig a saját térfélen marad, csak utána
        # ér át a felezőn (lassú indítás).
        for j in range(200):
            frames.append(Frame(t=t, players=[keeper()],
                                ball=Ball(x=30.0, y=10.0, confidence=1.0)))
            t += 1
        frames.append(Frame(t=t, players=[keeper()],
                            ball=Ball(x=19.0, y=10.0, confidence=1.0)))
        t += 100
    tf = training_focus(Match(_meta(), frames))
    item = next((it for it in tf["away"]
                 if it["title"] == "Gyors indítás védés után"), None)
    assert item is not None
    assert "3 mért indításból" in item["why"]
    assert item["area"] == "kapus"


def test_empty_net_costs_trigger_7v6_focus():
    """2 üres kapura kapott gól → "7 a 6 labdabiztonság" fókusz a kaput
    elhagyó (hazai) csapatnak."""
    def gk_home():
        gk = _pl(1, Team.HOME, 20.0, 10.0)
        gk.role = "kapus"
        return gk

    frames = []
    # 5 mp 7 a 6: a hazai kapus elöl, a hazai csapat birtokol.
    for t in range(125):
        frames.append(Frame(
            t=t,
            players=[gk_home(), _pl(2, Team.HOME, 30.0, 10.0)],
            ball=Ball(x=30.0, y=10.0, confidence=1.0)))
    # Két gyors büntető gól az üres hazai kapuba (a türelmi ablakon belül).
    t = 125
    for start in (125, 140):
        t = start
        for i in range(7):
            frames.append(Frame(
                t=t,
                players=[gk_home(),
                         _pl(4, Team.AWAY, 3.0, 10.0)],
                ball=Ball(x=max(2.6 - 0.6 * i, 0.0), y=10.0,
                          confidence=1.0)))
            t += 1
        frames.append(Frame(t=t, players=[gk_home()],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    tf = training_focus(Match(_meta(), frames))
    item = next((it for it in tf["home"]
                 if it["title"] == "7 a 6 labdabiztonság"), None)
    assert item is not None
    assert "2 gólt kaptak üres kapura" in item["why"]


def test_single_axis_goals_trigger_variety_focus():
    """Ha minden gól ugyanarról az (1-es -> 2-es) tengelyről jön (3 gól),
    "Támadás-változatosság" fókusz születik."""
    frames = []
    t = 0
    for _ in range(3):
        # passz 1→2, majd a 2-es gólja a +x kapura
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 25.0, 10.0),
                                          _pl(2, Team.HOME, 30.0, 10.0)],
                            ball=Ball(x=25.0, y=10.0, confidence=1.0)))
        t += 1
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 25.0, 10.0),
                                          _pl(2, Team.HOME, 30.0, 10.0)],
                            ball=Ball(x=30.0, y=10.0, confidence=1.0)))
        t += 1
        for i in range(7):
            frames.append(Frame(t=t,
                                players=[_pl(2, Team.HOME, 33.0, 10.0)],
                                ball=Ball(x=34.0 + i, y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(20):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    tf = training_focus(Match(_meta(), frames))
    item = next((it for it in tf["home"]
                 if it["title"] == "Támadás-változatosság"), None)
    assert item is not None
    assert "1. → 2. tengelyről" in item["why"]


def test_multiple_fading_players_trigger_rotation_focus():
    """Két 20%+ tempót eső, le nem cserélt játékos → Rotáció-tervezés
    fókusz a csapatnak."""
    frames = []
    n_half = 1000  # 40 mp félidőnként (25 fps)
    xs = {1: 5.0, 2: 5.0}
    for t in range(2 * n_half):
        players = []
        for tid in (1, 2):
            v = 0.08 if t < n_half else 0.04  # 2 m/s -> 1 m/s (esés 50%)
            xs[tid] += v
            if xs[tid] > 35.0:
                xs[tid] = 5.0
            players.append(_pl(tid, Team.HOME, xs[tid], 6.0 + 4 * tid))
        frames.append(Frame(t=t, players=players))
    tf = training_focus(Match(_meta(), frames))
    item = next((it for it in tf["home"]
                 if it["title"] == "Rotáció-tervezés"), None)
    assert item is not None
    assert "2 játékos" in item["why"]
    assert item["area"] == "kondíció"


def test_negative_gsax_triggers_keeper_focus():
    """Ha a kapus a helyzetekből várhatónál 2+ góllal többet kap,
    Kapus-forma fókusz születik a védő oldalon."""
    def gk():
        p = _pl(30, Team.AWAY, 39.0, 10.0)
        p.role = "kapus"
        return p

    # 4 távoli, kis xG-jű hazai gól: a kapus a várhatónál jóval
    # többet kap (GSAx ~ −3) — ez a kapus-forma jel.
    frames = []
    t = 0
    for _ in range(4):
        for i in range(10):
            frames.append(Frame(
                t=t,
                players=[_pl(1, Team.HOME, 28.0, 4.0), gk()],
                ball=Ball(x=min(28.5 + 1.3 * i, 40.0),
                          y=4.0 + min(0.65 * i, 6.0),
                          confidence=1.0)))
            t += 1
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 20
    tf = training_focus(Match(_meta(), frames))
    item = next((it for it in tf["away"]
                 if it["title"] == "Kapus-forma"), None)
    assert item is not None
    assert "GSAx" in item["why"]
    assert item["area"] == "kapus"


def test_slow_recovery_triggers_transition_focus():
    """Méréssel lassú visszarendeződés → Visszarendeződés-tempó fókusz
    a védekező oldalon."""
    frames = []
    t = 0
    for _ in range(4):  # négy támadás, mindegyiknél késve érnek vissza
        for i in range(250):
            bx = 22.0 + 0.05 * i
            players = [_pl(1, Team.HOME, bx, 10.0)]
            dx = 10.0 if i < 150 else 35.0
            for k in range(4):
                players.append(_pl(10 + k, Team.AWAY, dx, 4.0 + 4 * k))
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=bx, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(40):  # birtoklás-szünet: külön szakaszok
            frames.append(Frame(t=t, players=[], ball=None))
            t += 1
    tf = training_focus(Match(_meta(), frames))
    item = next((it for it in tf["away"]
                 if it["title"] == "Visszarendeződés-tempó"), None)
    assert item is not None
    assert "felálló védelemig" in item["why"]


def test_unused_wings_trigger_width_focus():
    """Ha a felállásban vannak szélsők, de a gólok mind középről jönnek,
    Szélső-játék fókusz születik."""
    frames = []
    t = 0
    # Birtoklás-fázis: szélsők a sávban, a lövő középen (poszt-minta).
    for _ in range(150):
        frames.append(Frame(t=t, players=[
            _pl(1, Team.HOME, 33.0, 10.0),
            _pl(2, Team.HOME, 36.0, 2.0),
            _pl(7, Team.HOME, 36.0, 18.0),
        ], ball=Ball(x=33.2, y=10.0, confidence=1.0)))
        t += 1
    # 6 gól, mind az 1-estől (középről).
    for _ in range(6):
        for i in range(7):
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 33.0, 10.0)],
                                ball=Ball(x=34.0 + i, y=10.0,
                                          confidence=1.0)))
            t += 1
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 20
    tf = training_focus(Match(_meta(), frames))
    item = next((it for it in tf["home"]
                 if it["title"] == "Szélső-játék bevonása"), None)
    assert item is not None
    assert "6 gólból csak 0" in item["why"]


def test_repeated_suspensions_trigger_discipline_focus():
    """2+ felismert kiállítás → Fegyelmezett védekezés fókusz a
    büntetett oldalon."""
    from handball.models.tracking import Ball

    def mk(t, home_n):
        players = [_pl(100 + k, Team.HOME, 15.0 + k, 4.0 + k)
                   for k in range(home_n)]
        players += [_pl(200 + k, Team.AWAY, 25.0 + k, 4.0 + k)
                    for k in range(6)]
        return Frame(t=t, players=players,
                     ball=Ball(x=20.0, y=10.0, confidence=1.0))

    frames = [mk(t, 6) for t in range(750)]
    frames += [mk(t, 5) for t in range(750, 2250)]     # 1. kiállítás
    frames += [mk(t, 6) for t in range(2250, 3000)]
    frames += [mk(t, 5) for t in range(3000, 4500)]    # 2. kiállítás
    frames += [mk(t, 6) for t in range(4500, 5250)]
    m = Match(_meta(), frames)
    tf = training_focus(m)
    titles = [f["title"] for f in tf["home"]]
    assert "Fegyelmezett védekezés" in titles
    assert all(f["title"] != "Fegyelmezett védekezés"
               for f in tf["away"])


def test_bad_restart_triggers_protocol_focus():
    """Ha a 2. félidő első 5 percében 2+ gólos mínuszba kerül a csapat,
    a Szünet utáni protokoll fókusz jár."""
    from handball.models.tracking import Ball

    def play(t0, seconds, fps=25.0):
        frames = []
        for i in range(int(seconds * fps)):
            players = [_pl(100 + k, Team.HOME, 12.0 + k * 0.5,
                           4.0 + k * 2) for k in range(6)]
            players += [_pl(200 + k, Team.AWAY, 26.0 + k * 0.5,
                            4.0 + k * 2) for k in range(6)]
            frames.append(Frame(t=t0 + i, players=players,
                                ball=Ball(x=19.0, y=10.0,
                                          confidence=1.0)))
        return frames

    def brk(t0, seconds, fps=25.0):
        return [Frame(t=t0 + i, players=[], ball=None)
                for i in range(int(seconds * fps))]

    def away_goal(t0):
        frames = []
        for i in range(8):  # vendég gól a -x kapuba
            frames.append(Frame(t=t0 + i,
                                players=[_pl(201, Team.AWAY, 6.5, 10.0)],
                                ball=Ball(x=max(6.0 - i, 0.0), y=10.0,
                                          confidence=1.0)))
        return frames

    frames = play(0, 120)
    t = len(frames)
    frames += brk(t, 90)
    t = len(frames)
    frames += play(t, 20)
    t = len(frames)
    frames += away_goal(t)
    t += 8
    frames += play(t, 20)
    t = len(frames)
    frames += away_goal(t)
    t += 8
    frames += play(t, 20)
    m = Match(_meta(), frames)
    tf = training_focus(m)
    titles = [f["title"] for f in tf["home"]]
    assert "Szünet utáni protokoll" in titles
    assert all(f["title"] != "Szünet utáni protokoll"
               for f in tf["away"])


def test_unproductive_figure_triggers_refresh_focus():
    """Ha a leggyakoribb figura 4+ támadásból sem hoz gólt, a
    Figura-frissítés fókusz jár."""
    from handball.models.tracking import Ball

    frames = []
    t = 0
    for _ in range(4):  # négy azonos mintájú hazai támadás, gól nélkül
        for _ in range(8):
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, 30.0, 10.0),
                _pl(2, Team.HOME, 28.0, 8.0),
                _pl(3, Team.HOME, 32.0, 12.0),
            ], ball=Ball(x=30.0, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(20):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    m = Match(_meta(), frames)
    tf = training_focus(m)
    titles = [f["title"] for f in tf["home"]]
    assert "Figura-frissítés" in titles


def test_predictable_seven_taker_triggers_variation_focus():
    """Ha a dobó két mért hetese ugyanabba a sávba megy, a
    Hetes-variáció fókusz jár."""
    from handball.models.tracking import Ball

    def taker():
        return _pl(1, Team.HOME, 32.0, 10.0)

    frames = []
    t = 0
    for _ in range(2):  # két hetes, mindkettő balra (y=8.8)
        for _ in range(30):
            frames.append(Frame(t=t, players=[taker()],
                                ball=Ball(x=33.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        for i in range(7):
            frames.append(Frame(t=t, players=[taker()],
                                ball=Ball(x=min(34.0 + i, 40.0), y=8.8,
                                          confidence=1.0)))
            t += 1
        for _ in range(260):
            frames.append(Frame(t=t, players=[taker()],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    m = Match(_meta(), frames)
    tf = training_focus(m)
    titles = [f["title"] for f in tf["home"]]
    assert "Hetes-variáció" in titles


def test_training_flags_loose_marking():
    """29) Ha a leglazább emberfogó 2,5 m+ átlagról őrzi az emberét
    (50+ kockán át), Emberfogás-tapadás fókusz születik; szoros
    őrzésnél nem."""
    def scene(dy):
        frames = []
        for t in range(60):
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, 25.0, 10.0),
                _pl(20, Team.AWAY, 25.0, 10.0 + dy)],
                ball=Ball(x=25.0, y=10.0, confidence=1.0)))
        return Match(_meta(), frames)

    out = training_focus(scene(3.0))
    away = [it for it in out["away"]
            if it["title"] == "Emberfogás-tapadás"]
    assert away and "3.0 m-ről őrzi" in away[0]["why"]
    out2 = training_focus(scene(1.0))
    assert not any(it["title"] == "Emberfogás-tapadás"
                   for it in out2["away"])
