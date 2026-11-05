"""
Tesztek a figura-szimulációra (play_simulation.py).

Szintetikus adatokkal, videó nélkül: a védekezési modell tanulása, a védők
reakciója, a figura lejátszása és pontozása.

Futtatás:
    python tests/test_play_simulation.py
"""

from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, Ball, Team, PositionSource,
)
from handball.pipeline.tactics import TacticsConfig
from handball.pipeline.play_simulation import (
    DefenseModel, SetPlay, simulate_setplay, evaluate_setplay,
)


def _pl(track_id, team, x, y, jersey=None):
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0,
                          jersey_number=jersey)


def test_defense_model_learns_depth_and_count():
    """6 védő a 6 m-es vonalon (x≈34, kapu x=40 → mélység 6) → modell ~6, ~6 m."""
    frames = []
    for t in range(10):
        players = [_pl(i + 1, Team.HOME, 28.0, 10.0) for i in range(3)]  # hazai támad (x>20)
        players += [_pl(100 + i, Team.AWAY, 34.0, y) for i, y in enumerate((3, 6, 9, 11, 14, 17))]
        frames.append(Frame(t=t, players=players, ball=Ball(x=28.0, y=10.0, confidence=1.0)))
    model = DefenseModel.learn(Match(MatchMeta(match_id="t", home_team="A", away_team="B", fps=25), frames), Team.AWAY)
    assert model.num_defenders == 6
    assert abs(model.line_depth_m - 6.0) < 1e-6


def _press_match(nyom: bool, n: int = 60):
    """A hazai 1-es labdás 9 m-en (31; 13,3); a vendég fal a hatoson,
    `nyom` esetén a legközelebbi védő 1,2 m-re rálép."""
    frames = []
    for t in range(n):
        players = [_pl(1, Team.HOME, 31.0, 13.3), _pl(2, Team.HOME, 28.0, 8.0)]
        ys = (3, 6, 9, 11, 14, 17)
        for i, y in enumerate(ys):
            x, yy = 34.0, float(y)
            if nyom and y == 14:
                x, yy = 32.0, 14.2
            players.append(_pl(100 + i, Team.AWAY, x, yy))
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=31.0, y=13.3, confidence=1.0)))
    return Match(MatchMeta(match_id="p", home_team="A", away_team="B",
                           fps=25), frames)


def test_a_vedekezes_modell_megtanulja_a_kilepesi_hajlamot():
    """Ha a védő rendre rálép a lőtávolságon belüli labdásra, a modell
    kilépési hajlama magas; zárt falnál 0; kevés mintából (50 kocka alatt)
    nem tanul — 0 marad."""
    from handball.pipeline.play_simulation import PRESS_LEARN_MIN_FRAMES

    assert DefenseModel.learn(_press_match(True), Team.AWAY).press_rate == 1.0
    assert DefenseModel.learn(_press_match(False), Team.AWAY).press_rate == 0.0
    keves = _press_match(True, n=PRESS_LEARN_MIN_FRAMES - 1)
    assert DefenseModel.learn(keves, Team.AWAY).press_rate == 0.0


def _kovet_match(gain: float, n: int = 60, labda_ys=(5, 7, 10, 13, 15)):
    """A hazai labdás 12 m-re a kaputól, a labda y-ja `labda_ys` szerint
    körbejár; a vendég fal a hatoson a labda oldal-eltérésének `gain`
    részével tolódik el."""
    frames = []
    for t in range(n):
        by = float(labda_ys[t % len(labda_ys)])
        players = [_pl(1, Team.HOME, 28.0, by), _pl(2, Team.HOME, 27.0, 5.0),
                   _pl(3, Team.HOME, 27.0, 15.0)]
        for i, y in enumerate((4, 7, 9, 11, 13, 16)):
            players.append(_pl(100 + i, Team.AWAY, 34.0,
                               y + gain * (by - 10.0)))
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=28.0, y=by, confidence=1.0)))
    return Match(MatchMeta(match_id="k", home_team="A", away_team="B",
                           fps=25), frames)


def test_a_vedekezes_modell_megtanulja_a_labdakovetest():
    """A labdával 60%-ban együtt tolódó fal → 0,6; a helyben álló fal →
    0; középen álló labdából (nincs oldal-mozgás) és kevés mintából (50
    kocka alatt) nem tanul — az alapérték (0,5) marad. A tanult modell a
    szimulációban is ennyit tolódik."""
    import statistics

    from handball.pipeline.play_simulation import LATERAL_LEARN_MIN_FRAMES

    tanult = DefenseModel.learn(_kovet_match(0.6), Team.AWAY)
    assert abs(tanult.lateral_gain - 0.6) < 1e-9
    assert DefenseModel.learn(_kovet_match(0.0), Team.AWAY).lateral_gain == 0.0
    kozep = _kovet_match(0.6, labda_ys=(10,))
    assert DefenseModel.learn(kozep, Team.AWAY).lateral_gain == 0.5
    keves = _kovet_match(0.6, n=LATERAL_LEARN_MIN_FRAMES - 1)
    assert DefenseModel.learn(keves, Team.AWAY).lateral_gain == 0.5

    def fal_kozep(model, by):
        return statistics.fmean(y for _, y in model.respond(
            Ball(x=24.0, y=by, confidence=1.0), goal_x=40.0))

    eltolas = fal_kozep(tanult, 13.0) - fal_kozep(tanult, 10.0)
    assert abs(eltolas - 0.6 * 3.0) < 1e-6


def _dupla_match(dupla: bool, n: int = 60):
    """A hazai 1-es labdás 9 m-en (31; 13,3); a vendég fal a hatoson,
    egy védő mindig 1,2 m-re rálép, `dupla` esetén egy második is 2 m-re
    mellé áll."""
    frames = []
    for t in range(n):
        players = [_pl(1, Team.HOME, 31.0, 13.3), _pl(2, Team.HOME, 28.0, 8.0)]
        for i, y in enumerate((3, 6, 9, 11, 14, 17)):
            x, yy = 34.0, float(y)
            if y == 14:
                x, yy = 32.0, 14.2
            if dupla and y == 11:
                x, yy = 32.5, 11.9
            players.append(_pl(100 + i, Team.AWAY, x, yy))
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=31.0, y=13.3, confidence=1.0)))
    return Match(MatchMeta(match_id="d", home_team="A", away_team="B",
                           fps=25), frames)


def test_a_vedekezes_modell_megtanulja_a_kettozest():
    """Ha két védő is rendre a labdás mellett áll, a kettőzési hajlam
    magas; egy rálépő védőnél 0 (az csak kilépés); kevés mintából nem
    tanul. A szimulációban a második legközelebbi védő a labdás felé lép,
    és 1,2 m-re megáll tőle; a többi a falban marad."""
    import math

    from handball.pipeline.play_simulation import (DOUBLE_GAP_M,
                                                   PRESS_LEARN_MIN_FRAMES)

    assert DefenseModel.learn(_dupla_match(True), Team.AWAY).double_rate == 1.0
    assert DefenseModel.learn(_dupla_match(False), Team.AWAY).double_rate == 0.0
    keves = _dupla_match(True, n=PRESS_LEARN_MIN_FRAMES - 1)
    assert DefenseModel.learn(keves, Team.AWAY).double_rate == 0.0

    labda = Ball(x=31.0, y=13.3, confidence=1.0)
    egy = DefenseModel(press_rate=1.0).respond(labda, goal_x=40.0)
    ketto = DefenseModel(press_rate=1.0, double_rate=1.0).respond(
        labda, goal_x=40.0)
    valtozott = [i for i, (a, b) in enumerate(zip(egy, ketto)) if a != b]
    assert len(valtozott) == 1, (egy, ketto)
    x, y = ketto[valtozott[0]]
    assert abs(math.hypot(x - 31.0, y - 13.3) - DOUBLE_GAP_M) < 1e-6
    # távoli labdánál senki nem kettőz
    tavol = Ball(x=24.0, y=10.0, confidence=1.0)
    assert (DefenseModel(double_rate=1.0).respond(tavol, goal_x=40.0)
            == DefenseModel().respond(tavol, goal_x=40.0))


def test_a_figura3d_fejlece_mutatja_a_tanult_falat(tmp_path,
                                                          monkeypatch):
    """A meccsből tanult fal fejléce kiírja a labdakövetést (ha nem az
    alapérték), a kilépést és a kettőzést (5% felett)."""
    from fastapi.testclient import TestClient

    from handball.api.app import create_app

    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    app = create_app()
    app.state.put_match(_kovet_match(0.6))
    r = TestClient(app).get("/figura3d", params={
        "u": "30,5,32,8;30,15,31,12", "meccs": "k", "vedo": "away"})
    assert r.status_code == 200
    assert "követi a labdát: 60%" in r.text
    app.state.put_match(_dupla_match(True))
    r = TestClient(app).get("/figura3d", params={
        "u": "30,5,32,8;30,15,31,12", "meccs": "d", "vedo": "away"})
    assert r.status_code == 200
    assert "kilép a labdásra: 100%" in r.text and "kettőz: 100%" in r.text


def test_a_kilepo_vedo_a_labdas_ele_lep_a_szimulacioban():
    """press_rate=1: lőtávolságon belüli labdánál a labdáshoz legközelebbi
    védő a labdás és a kapu-közép vonalán 1 m-re áll meg előtte; a többi
    védő a falban marad. press_rate=0: a fal változatlan. Távoli labdánál
    senki nem lép ki."""
    import math

    from handball.pipeline.play_simulation import PRESS_GAP_M

    labda = Ball(x=31.0, y=13.3, confidence=1.0)
    zart = DefenseModel().respond(labda, goal_x=40.0)
    kilep = DefenseModel(press_rate=1.0).respond(labda, goal_x=40.0)
    valtozott = [i for i, (a, b) in enumerate(zip(zart, kilep)) if a != b]
    assert len(valtozott) == 1, (zart, kilep)
    x, y = kilep[valtozott[0]]
    assert abs(math.hypot(x - 31.0, y - 13.3) - PRESS_GAP_M) < 1e-6
    assert x > 31.0  # a labdás és a kapu között
    tavol = Ball(x=24.0, y=10.0, confidence=1.0)
    assert (DefenseModel(press_rate=1.0).respond(tavol, goal_x=40.0)
            == DefenseModel().respond(tavol, goal_x=40.0))


def test_defense_respond_wall_outside_area_and_shift():
    """A 6-os fal a hatoson KÍVÜL áll (egy védő sincs a kapuelőtérben),
    középen a hatos előtt fél méterrel, a széleken az ívre simulva — és a
    labda y-felé tolódik."""
    import math

    model = DefenseModel(num_defenders=6, line_depth_m=6.0, lateral_gain=0.5)
    pos = model.respond(Ball(x=30.0, y=16.0, confidence=1.0), goal_x=40.0)
    assert len(pos) == 6
    # Egyik védő sem lehet a hatoson belül: a közelebbi kapufától 6 m+.
    for x, y in pos:
        post_y = min(11.5, max(8.5, y))
        assert math.hypot(x - 40.0, y - post_y) >= 6.0 - 1e-9
    # A fal íves: a szélső védő közelebb áll a kapu síkjához, mint a középső.
    mid = min(pos, key=lambda p: abs(p[1] - 10.0))
    wing = max(pos, key=lambda p: abs(p[1] - 10.0))
    assert wing[0] > mid[0]
    # Középen a hatos előtt fél méterrel (x = 40 - 6,5).
    assert abs(mid[0] - 33.5) < 0.6
    # A labda y=16 (a közép 10 felett) → a védők átlag y-ja feljebb tolódik.
    avg_y = sum(y for _, y in pos) / len(pos)
    assert avg_y > 10.0


def _simple_setplay():
    """Kétlépéses figura: a 2-es támadó az 1. lépésben távol, a 2.-ban a kapu előtt."""
    attackers = [
        [(22.0, 6.0), (22.0, 6.0)],     # 1: irányító, stabil
        [(25.0, 14.0), (35.0, 10.0)],   # 2: beáll a kapu elé (x=35, y=10) a 2. lépésre
    ]
    ball_carrier = [0, 0]               # az irányítónál a labda (passzra készül)
    return SetPlay(attackers=attackers, ball_carrier=ball_carrier)


def test_simulate_setplay_builds_match():
    """A szimuláció a támadókat + tanult védőket + labdát tartalmazó Match-et ad."""
    model = DefenseModel(num_defenders=6, line_depth_m=6.0)
    match = simulate_setplay(_simple_setplay(), model)
    assert len(match.frames) == 2
    home = [p for p in match.frames[0].players if p.team == Team.HOME]
    away = [p for p in match.frames[0].players if p.team == Team.AWAY]
    assert len(home) == 2 and len(away) == 6
    assert match.frames[0].ball is not None


def test_evaluate_setplay_scores_open_chance():
    """A figura pontot kap, ha a beálló szabadon kerül a kapu közelébe.

    A védelem mélysége 9 m (x=31), így a 2. lépésben a beálló (x=35,y=10) a védők
    MÖGÉ, közel a kapuhoz kerül → magas lövésérték, szabadon.
    """
    model = DefenseModel(num_defenders=6, line_depth_m=9.0, lateral_gain=0.3)
    match = simulate_setplay(_simple_setplay(), model)
    result = evaluate_setplay(match)
    assert result["best_shot_value"] > 0.3   # teremtett jó helyzetet
    assert result["step"] == 1               # a 2. lépésben (a beállás után)


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    print(f"\n{'OK' if failures == 0 else failures} hibás teszt")
    raise SystemExit(1 if failures else 0)


def _proba_match(ismetles: int = 3, fps: float = 25.0, fal_x: float = 34.0,
                 vedok: int = 6):
    """A hazai (Ők) ugyanazt a beálló-figurát `ismetles`-szer játssza: az
    1-es középen előre, a 2-es a szélről befut; a támadások közt a labda
    a saját térfelükön (átmenet). A vendég (Mi) fala `fal_x`-en, `vedok`
    védővel (6: zárt 6-0; kevesebb: ritka fal). A támadók mezszáma a
    sorszámuk (a figura "mez" sorához)."""
    frames = []
    t = 0
    for _ in range(ismetles):
        n = int(3 * fps)
        for s in range(n):
            u = s / (n - 1)
            a1 = (25 + 5 * u, 10.0)
            players = [_pl(1, Team.HOME, *a1, jersey=1),
                       _pl(2, Team.HOME, 30 + 4 * u, 2 + 6 * u, jersey=2),
                       _pl(3, Team.HOME, 27.0, 15.0, jersey=3)]
            for i, y in enumerate((3, 6, 9, 11, 14, 17)[:vedok]):
                players.append(_pl(100 + i, Team.AWAY, fal_x, float(y)))
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=a1[0], y=a1[1], confidence=1.0)))
            t += 1
        for _s in range(int(fps)):
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 15.0, 10.0)],
                                ball=Ball(x=15.0, y=10.0, confidence=1.0)))
            t += 1
    return Match(MatchMeta(match_id="pr", home_team="Ők", away_team="Mi",
                           fps=fps), frames)


def test_a_vedekezesi_proba_az_o_figurajukat_a_mi_falunk_ellen_jatssza():
    """A háromszor ismételt figurájuk egy sorként jön (3×), a mi falunk
    és az alap 6-0 elleni lövőhelyzettel; a ritka (négyvédős) fal ellen
    a próba kimondja a különbséget. Egyszeri támadás nem visszatérő
    figura; a nem támadó csapatnál nincs mit próbálni."""
    from handball.pipeline.play_simulation import (AJANLO_ELTERES_PP,
                                                   PROBA_MIN_ISMETLES,
                                                   defense_test)

    r = defense_test(_proba_match(), Team.HOME, DefenseModel())
    assert len(r["figurak"]) == 1
    f = r["figurak"][0]
    assert f["ismetles"] == 3 and f["elteres_pp"] == 0.0
    assert f["attackers"] and len(f["labda"]) == len(f["attackers"][0])
    assert r["verdict"].startswith(
        "a legveszélyesebb visszatérő figurájuk (3×, pl. ")
    assert "százalékponttal" not in r["verdict"]

    ritka = defense_test(_proba_match(), Team.HOME,
                         DefenseModel(num_defenders=2))
    assert ritka["figurak"][0]["elteres_pp"] >= AJANLO_ELTERES_PP
    assert "be kell gyakorolni" in ritka["verdict"]

    egyszeri = _proba_match(ismetles=PROBA_MIN_ISMETLES - 1)
    assert defense_test(egyszeri, Team.HOME, DefenseModel()) == {
        "figurak": [], "verdict": None}
    assert defense_test(_proba_match(), Team.AWAY, DefenseModel()) == {
        "figurak": [], "verdict": None}


_FINOMITO_FIGURA = [[[26, 10], [29, 10], [31.5, 10]], [[26, 4], [26, 4], [26, 4]],
                    [[30, 2], [33, 2], [36, 1.5]], [[27, 15], [28, 15], [29, 15]]]


def test_az_ai_finomito_javit_a_figuran_a_tanult_fal_ellen():
    """5-1 fal ellen a finomító a kulcs-pozíciók kis módosításával
    nagyobb lövőhelyzetet talál; a kezdő felállás nem változik, egy
    támadó sem lép a hatosba vagy a saját térfelére; a változásokat
    magyarul mondja ki. A finomított figura a fal ellen tényleg annyit
    ér, amennyit a finomító állít."""
    import math

    from handball.pipeline.play_simulation import (
        FINOMITO_MIN_JAVULAS_PP, GOAL_AREA_RADIUS_M, refine_setplay,
        setplay_3d_match)

    fal = DefenseModel(rendszer="5-1", press_rate=0.4, lateral_gain=0.8)
    r = refine_setplay(_FINOMITO_FIGURA, fal, ball=[0, 0, 1])
    assert r["javulas_pp"] >= FINOMITO_MIN_JAVULAS_PP
    assert r["pont_utana"] > r["pont_elotte"]
    assert [u[0] for u in r["attackers"]] == [p[0] for p in _FINOMITO_FIGURA]
    for u in r["attackers"]:
        for x, y in u:
            fa_y = min(11.5, max(8.5, y))
            assert math.hypot(x - 40.0, y - fa_y) >= GOAL_AREA_RADIUS_M
            assert x >= 20.0
    assert r["valtozasok"] and "támadó „" in r["valtozasok"][0]
    assert "pontja" in r["valtozasok"][0]
    assert r["verdict"].startswith("A modell szerint ")
    _, e = setplay_3d_match(r["attackers"], fal, ball=r["labda"])
    assert abs(100.0 * e["best_shot_value"] - r["pont_utana"]) < 0.6


def test_az_ai_finomito_a_befejezot_is_csereli(monkeypatch):
    """A tanult lövőkkel és a mezszámokkal a finomító szerepcserét is
    próbál: a (minden sávban 1,3×) biztos kezű lövőt arra az útra
    teszi, amelyik a helyzetet teremti — egy körben ez a legjobb lépés,
    a mondat kimondja, a pontszám a cserés figurával visszaszámolható;
    modell vagy mezszám nélkül nincs csere, a "mez" sor marad."""
    import handball.pipeline.play_simulation as ps
    from handball.pipeline.play_simulation import (AttackModel,
                                                   refine_setplay,
                                                   setplay_3d_match)

    fal = DefenseModel()
    _, e0 = setplay_3d_match(_FINOMITO_FIGURA, fal, ball=[0, 0, 1])
    b = e0["attacker_id"] - 1                 # aki a helyzetbe ér
    masik = (b + 1) % len(_FINOMITO_FIGURA)
    mez = [20 + i for i in range(len(_FINOMITO_FIGURA))]
    mez[masik] = 7                            # a jó lövő rossz úton
    tam = AttackModel(lovok={7: {"close": 1.3, "mid": 1.3, "far": 1.3}})
    monkeypatch.setattr(ps, "FINOMITO_KOROK", 1)
    r = refine_setplay(_FINOMITO_FIGURA, fal, ball=[0, 0, 1], tamadas=tam,
                       mezek=mez)
    assert r["mez"][b] == 7 and r["mez"][masik] == mez[b]
    assert sorted(r["mez"]) == sorted(mez)
    assert abs(r["pont_utana"] - 1.3 * r["pont_elotte"]) < 0.2
    assert r["attackers"] == [[[float(x), float(y)] for x, y in u]
                              for u in _FINOMITO_FIGURA]
    csere = [v for v in r["valtozasok"] if v.startswith("Szerepcsere: ")]
    assert len(csere) == 1 and f"a 7-es {'az' if b + 1 in (1, 5) else 'a'} " \
        f"{b + 1}. támadó útját futja" in csere[0]
    assert "szerepcsere: " in r["verdict"]
    _, e = setplay_3d_match(r["attackers"], fal, ball=r["labda"],
                            tamadas=tam, mezek=r["mez"])
    assert abs(100.0 * e["best_shot_value"] - r["pont_utana"]) < 0.6
    # Modell nélkül, vagy egy mezszámmal: nincs csere.
    nelkul = refine_setplay(_FINOMITO_FIGURA, fal, ball=[0, 0, 1], mezek=mez)
    assert nelkul["mez"] == mez
    egy = refine_setplay(_FINOMITO_FIGURA, fal, ball=[0, 0, 1], tamadas=tam,
                         mezek=[7, None, None, None])
    assert egy["mez"] == [7, None, None, None]


def test_a_figura_kimenetek_a_tanult_lovovel():
    """A kimenet-szimuláció a tanult lövővel: a helyzetbe érő, biztos kezű
    támadóval a lejátszások átlag-értéke és a gólok száma nő (ugyanaz a
    seed); mezszám nélkül a modell nem hat."""
    from handball.pipeline.play_simulation import (AttackModel,
                                                   setplay_3d_match,
                                                   simulate_outcomes)

    _, e0 = setplay_3d_match(_FINOMITO_FIGURA, DefenseModel(), ball=[0, 0, 1])
    mez = [None] * len(_FINOMITO_FIGURA)
    mez[e0["attacker_id"] - 1] = 7
    tam = AttackModel(lovok={7: {"close": 1.3, "mid": 1.3, "far": 1.3}})
    alap = simulate_outcomes(_FINOMITO_FIGURA, DefenseModel(), ball=[0, 0, 1],
                             n=120, seed=3)
    vele = simulate_outcomes(_FINOMITO_FIGURA, DefenseModel(), ball=[0, 0, 1],
                             n=120, seed=3, tamadas=tam, mezek=mez)
    assert vele["atlag_pct"] > alap["atlag_pct"]
    assert vele["gol"] >= alap["gol"]
    assert simulate_outcomes(_FINOMITO_FIGURA, DefenseModel(), ball=[0, 0, 1],
                             n=120, seed=3, tamadas=tam) == alap


def test_az_ai_finomito_nem_valtoztat_ha_nincs_jobb(monkeypatch):
    """Ha nincs javító lépés (itt: kör nélkül), a finomító változatlanul
    hagyja a figurát, és ezt ki is mondja; üres figurára ValueError."""
    import pytest

    import handball.pipeline.play_simulation as ps
    from handball.pipeline.play_simulation import refine_setplay

    monkeypatch.setattr(ps, "FINOMITO_KOROK", 0)
    r = refine_setplay(_FINOMITO_FIGURA, DefenseModel(), ball=[0, 0, 1])
    assert r["valtozasok"] == [] and r["javulas_pp"] == 0.0
    assert r["attackers"] == [[[float(x), float(y)] for x, y in u]
                              for u in _FINOMITO_FIGURA]
    assert r["verdict"].startswith("A modell nem talált jobb változatot")
    with pytest.raises(ValueError):
        refine_setplay([], DefenseModel())


def test_az_ai_finomito_passzt_is_javasol():
    """Kilépő és kettőző fal ellen a finomító a labdát egy másik
    támadónak adatja (a futások maradnak): a labda új útja a változások
    között, a passz legfeljebb FINOMITO_PASSZ_MAX_M; a finomított figura
    a fal ellen tényleg annyit ér."""
    import math

    from handball.pipeline.play_simulation import (FINOMITO_PASSZ_MAX_M,
                                                   refine_setplay,
                                                   setplay_3d_match)

    fal = DefenseModel(press_rate=1.0, double_rate=1.0)
    r = refine_setplay(_FINOMITO_FIGURA, fal, ball=[0, 0, 1])
    assert r["labda"] != [0, 0, 1]
    assert any(v.startswith("A labda útja a kulcs-pozíciókon: ")
               for v in r["valtozasok"])
    for k in range(1, len(r["labda"])):
        a, b = r["labda"][k - 1], r["labda"][k]
        if a != b:
            pa, pb = r["attackers"][a][k], r["attackers"][b][k]
            assert math.hypot(pa[0] - pb[0],
                              pa[1] - pb[1]) <= FINOMITO_PASSZ_MAX_M
    _, e = setplay_3d_match(r["attackers"], fal, ball=r["labda"])
    assert abs(100.0 * e["best_shot_value"] - r["pont_utana"]) < 0.6


def test_a_tanult_kapus_szorzoja_simitott_es_szoritott(monkeypatch):
    """A kapus sávonkénti szorzója a gól-arány a KAPUS_SULY képzelt
    alap-lövéssel simítva, az alaphoz mérve, a KAPUS_SZORZO sávba
    szorítva; KAPUS_MIN_LOVES alatti sáv kimarad."""
    import handball.pipeline.goalkeeper as gk
    from handball.pipeline.play_simulation import (
        KAPUS_ALAP_GOL, KAPUS_SULY, KAPUS_SZORZO_MIN, _kapus_tanul)

    def ranges(match, config=None):
        return {"away": {"far": {"faced": 10, "saves": 8},
                         "mid": {"faced": 10, "saves": 3},
                         "close": {"faced": 2, "saves": 0}},
                "home": {}}

    monkeypatch.setattr(gk, "gk_save_ranges", ranges)
    k = _kapus_tanul(None, Team.AWAY, TacticsConfig())
    assert set(k) == {"far", "mid"}
    assert k["far"] == KAPUS_SZORZO_MIN          # 2 gól 10-ből: erős kapus
    vart = (7 + KAPUS_SULY * KAPUS_ALAP_GOL["mid"]) / (10 + KAPUS_SULY)
    assert abs(k["mid"] - round(vart / KAPUS_ALAP_GOL["mid"], 3)) < 1e-9
    assert _kapus_tanul(None, Team.HOME, TacticsConfig()) == {}


def test_a_tanult_kapus_valodi_lovesekbol_es_a_kiertekelesben():
    """A valódi forrás-láncon (szimulált meccs lövésekkel → match_xg →
    gk_save_ranges): a lövéseket kapó kapus sávjai szorzót kapnak, a
    lövést nem kapó csapaté üres. A kiértékelés a lövőhely sávjának
    szorzójával súlyoz, és a felirat kimondja."""
    from handball.pipeline.play_simulation import (kapus_felirat,
                                                   kapus_sav)
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=300, fps=25.0, seed=1,
                              shots_per_min=8, halftime_break_s=30)
    kapott = DefenseModel.learn(m, Team.AWAY).kapus
    assert kapott and all(v > 1.0 for v in kapott.values())
    assert kapus_felirat(kapott).startswith("a kapus ")
    assert DefenseModel.learn(m, Team.HOME).kapus == {}

    # Egy szabad, távoli lövőhely: a szorzó egy az egyben a pontszámba megy.
    egy = Match(MatchMeta(match_id="e", home_team="A", away_team="B",
                          fps=25), [Frame(t=0, players=[
                              _pl(1, Team.HOME, 28.0, 10.0),
                              _pl(100, Team.AWAY, 34.0, 3.0)],
                              ball=Ball(x=28.0, y=10.0, confidence=1.0))])
    assert kapus_sav(28.0, 10.0, 40.0) == "far"
    alap = evaluate_setplay(egy)["best_shot_value"]
    tanult = evaluate_setplay(egy, defense=DefenseModel(
        kapus={"far": 1.3}))["best_shot_value"]
    assert abs(tanult - 1.3 * alap) < 1e-9
    assert kapus_felirat({"far": 1.05}) == ""


def test_a_tobb_meccses_tanulas_osszeadja_a_mintakat():
    """learn_many: egy meccsre azonos a learn-nel; két azonos meccsre a
    fal-paraméterek ugyanazok; a kilépés a KOCKÁK szerint súlyozódik (60
    rálépős + 120 zárt kocka → 1/3); üres listára az alap fal."""
    mely = _press_match(True)
    zart = _press_match(False, n=120)
    egy = DefenseModel.learn(mely, Team.AWAY)
    assert DefenseModel.learn_many([(mely, Team.AWAY)]) == egy
    ketto = DefenseModel.learn_many([(mely, Team.AWAY), (mely, Team.AWAY)])
    assert (ketto.num_defenders, ketto.line_depth_m, ketto.rendszer,
            ketto.press_rate, ketto.double_rate, ketto.lateral_gain) == (
        egy.num_defenders, egy.line_depth_m, egy.rendszer,
        egy.press_rate, egy.double_rate, egy.lateral_gain)
    vegyes = DefenseModel.learn_many([(mely, Team.AWAY), (zart, Team.AWAY)])
    assert abs(vegyes.press_rate - 60 / 180) < 1e-3
    assert DefenseModel.learn_many([]) == DefenseModel()


def test_a_tobb_meccses_kapus_minta_osszeadodik():
    """A kapus sávjai meccsek közt összeadódnak: két azonos (minden lövést
    bekapó) meccsből a simítás gyengébb, a szorzó az 1-től távolabb; a
    kevés lövéses sáv két meccsből már eléri a küszöböt."""
    from handball.pipeline.play_simulation import (KAPUS_MIN_LOVES,
                                                   _kapus_szorzo,
                                                   _mintak_osszege)
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=300, fps=25.0, seed=1,
                              shots_per_min=8, halftime_break_s=30)
    egy = DefenseModel.learn(m, Team.AWAY).kapus
    ketto = DefenseModel.learn_many([(m, Team.AWAY), (m, Team.AWAY)]).kapus
    assert set(ketto) == set(egy)
    assert all(ketto[s] >= egy[s] for s in egy)
    fel = {"far": [KAPUS_MIN_LOVES - 1, 0]}
    assert _kapus_szorzo(fel) == {}
    assert "far" in _kapus_szorzo(_mintak_osszege([{"kapus": fel},
                                                   {"kapus": fel}])["kapus"])


def test_az_edzes_fokusz_felkeszit_a_figurajukra_a_valodi_probabol():
    """489) A ritka (kétvédős) falunk ellen az ellenfél visszatérő figurája
    jóval többet ér, mint egy alap 6-0 ellen → "Felkészülés a figurájukra"
    tétel a MI (védekező) oldalunkon, a valódi forrás-láncból (tanult fal
    + védekezési próba); zárt 6-0 falnál nem szólal meg."""
    from handball.pipeline.training import training_focus

    ritka = training_focus(_proba_match(vedok=2))
    tetel = [i for i in ritka["away"]
             if i["title"] == "Felkészülés a figurájukra"]
    assert len(tetel) == 1
    assert "3×" in tetel[0]["why"] and "százalékponttal többet" in tetel[0]["why"]
    assert "a falunk alakja nyitja a rést" in tetel[0]["why"]
    assert not [i for i in ritka["home"]
                if i["title"] == "Felkészülés a figurájukra"]
    zart = training_focus(_proba_match())
    assert not [i for s in ("home", "away") for i in zart[s]
                if i["title"] == "Felkészülés a figurájukra"]


def test_a_figura_kimenetek_determinisztikusak_es_a_fal_szerint_valtoznak():
    """Ugyanaz a seed ugyanazt adja; a darabok összege n; a ritka fal
    ellen több a gól, mint a zárt ellen; a védőn át vezetett passz
    eladott labdát is hoz; a verdict a "tízből N gól" mondat."""
    from handball.pipeline.play_simulation import simulate_outcomes

    figura = [[[26, 10], [29, 10], [31.5, 10]], [[26, 4], [26, 4], [26, 4]],
              [[30, 2], [33, 2], [36, 1.5]], [[27, 15], [28, 15], [29, 15]]]
    a = simulate_outcomes(figura, DefenseModel(), ball=[0, 0, 1], n=60, seed=3)
    b = simulate_outcomes(figura, DefenseModel(), ball=[0, 0, 1], n=60, seed=3)
    assert a == b
    assert a["gol"] + a["vedett"] + a["eladott"] == a["n"] == 60
    assert abs(a["gol_pct"] + a["vedett_pct"] + a["eladott_pct"] - 100) < 0.2
    assert a["verdict"].startswith("60 lejátszásból ") \
        and "— tízből" in a["verdict"]
    ritka = simulate_outcomes(figura, DefenseModel(num_defenders=2),
                              ball=[0, 0, 1], n=120, seed=1)
    zart = simulate_outcomes(figura, DefenseModel(rendszer="3-2-1",
                                                  press_rate=0.8),
                             ball=[0, 0, 1], n=120, seed=1)
    assert ritka["gol_pct"] > zart["gol_pct"]
    assert ritka["atlag_pct"] > zart["atlag_pct"]
    # keresztpassz a falon át: a passz vonala a védőkön halad
    kereszt = [[[26, 4], [27, 4], [28, 4]], [[33, 14], [33, 15], [33, 16]]]
    k = simulate_outcomes(kereszt, DefenseModel(), ball=[0, 0, 1], n=120,
                          seed=2)
    assert k["eladott"] > 0


def _vedo_match(n: int = 60):
    """A hazai labdás felváltva a jobb (31; 13,3) és a bal (31; 6,7)
    oldalon; a vendég fal a hatoson mezszámmal (2..7, y = 3..17): a
    6-os (y = 14) mindig rálép a jobb oldali labdásra, a 3-as (y = 6) a
    bal oldalinál a falban marad."""
    frames = []
    for t in range(2 * n):
        jobb = t % 2 == 0
        by = 13.3 if jobb else 6.7
        players = [_pl(1, Team.HOME, 31.0, by), _pl(2, Team.HOME, 28.0, 10.0)]
        for i, y in enumerate((3, 6, 9, 11, 14, 17)):
            x, yy = 34.0, float(y)
            if jobb and y == 14:
                x, yy = 32.0, 14.2
            if jobb and y == 11:
                x, yy = 32.5, 11.9      # az 5-ös kettőz (második, 2,5 m-en belül)
            players.append(PlayerPosition(
                track_id=100 + i, team=Team.AWAY, x=x, y=yy,
                source=PositionSource.MEASURED, confidence=1.0,
                jersey_number=i + 2))
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=31.0, y=by, confidence=1.0)))
    return Match(MatchMeta(match_id="v", home_team="A", away_team="B",
                           fps=25), frames)


def test_a_tanult_fal_vedonkent_lep_ki():
    """A játékos-modell a falban: a 6-os saját hajlama 1, a 3-asé 0 (a
    csapaté 0,5); a szimulációban a jobb oldali labdásra a 6-os helye
    (5. vonal-slot) teljesen kilép, a bal oldalinál senki — mint a
    press_rate=1 / 0 fal. learn_many összeadja a védők mintáját; a 3D
    fejléce megnevezi a kilépőt."""
    m = _vedo_match()
    fal = DefenseModel.learn(m, Team.AWAY)
    assert abs(fal.press_rate - 0.5) < 1e-9
    assert [v["mez"] for v in fal.vedok] == [2, 3, 4, 5, 6, 7]
    assert fal.vedok[4]["press_rate"] == 1.0 and fal.vedok[1]["press_rate"] == 0.0
    assert fal.kilepo_vedo()["mez"] == 6
    # kettőzés: a jobb oldalon az 5-ös a második és 2,5 m-en belül van; a
    # bal oldalon a 4-es a második, de a falban marad
    assert fal.vedok[3]["double_rate"] == 1.0 and fal.vedok[2]["double_rate"] == 0.0
    assert fal.kettozo_vedo()["mez"] == 5 and abs(fal.double_rate - 0.5) < 1e-9
    from dataclasses import replace

    # (a szimulált fal slotjai: y = 3, 5,8, 8,6, 11,4, 14,2, 17 — a labda
    # a 6-os (5. slot) és a 3-as (2. slot) elé)
    jobb = Ball(x=31.0, y=14.5, confidence=1.0)
    bal = Ball(x=31.0, y=5.5, confidence=1.0)
    # (ugyanaz a tanult fal védőnkénti hajlam nélkül, csapat-szintű 1 / 0)
    assert fal.respond(jobb, 40.0) == replace(fal, press_rate=1.0,
                                              double_rate=1.0,
                                              vedok=[]).respond(jobb, 40.0)
    assert fal.respond(bal, 40.0) == replace(fal, press_rate=0.0,
                                             double_rate=0.0,
                                             vedok=[]).respond(bal, 40.0)
    assert fal.respond(bal, 40.0) != replace(fal, vedok=[]).respond(bal, 40.0)
    ketto = DefenseModel.learn_many([(m, Team.AWAY), (m, Team.AWAY)])
    assert ketto.vedok[4]["kozel"] == 2 * fal.vedok[4]["kozel"]
    assert DefenseModel().kilepo_vedo() is None


def test_a_vedekezesi_proba_megnevezi_a_rest_nyito_vedot():
    """Ha a próba szerint a falunk többet enged, és a fal kilépője /
    kettőzője ismert, a verdict megnevezi őket."""
    from handball.pipeline.play_simulation import defense_test

    fal = DefenseModel.learn(_vedo_match(), Team.AWAY)
    fal.num_defenders = 2          # ritka fal → a próba rést talál
    r = defense_test(_proba_match(), Team.HOME, fal)
    assert r["verdict"].endswith(
        "be kell gyakorolni (a 6-os kilépése és az 5-ös kettőzése nyitja)")


def test_a_mezszam_nevelovel_magyarul():
    from handball.pipeline.play_simulation import mezszam_nevelovel

    assert [mezszam_nevelovel(n) for n in (1, 2, 3, 4, 5, 6, 7, 8, 9)] == [
        "az 1-es", "a 2-es", "a 3-as", "a 4-es", "az 5-ös", "a 6-os",
        "a 7-es", "a 8-as", "a 9-es"]
    assert [mezszam_nevelovel(n) for n in (10, 20, 30, 40, 50, 60, 70, 80, 90)] == [
        "a 10-es", "a 20-as", "a 30-as", "a 40-es", "az 50-es", "a 60-as",
        "a 70-es", "a 80-as", "a 90-es"]
    assert mezszam_nevelovel(55) == "az 55-ös" and mezszam_nevelovel(23) == "a 23-as"


def test_az_elo_figura_ajanlo_az_addig_latott_falbol(monkeypatch):
    """Az 1. percben (küszöb átállítva) a vendég (Mi) addig látott fala
    ellen a legjobb figurát mondja; a hazai (Ők) nem védekezik → nincs
    rá ajánlás; rövid meccsnél (nem ér el a percig) és figura nélkül
    üres; az ajánlás csak az addigi kockákból jön (a meccs vége nem
    számít)."""
    import handball.pipeline.play_simulation as ps
    from handball.pipeline.play_simulation import (ALAP_FIGURAK,
                                                   live_figure_suggestions)

    monkeypatch.setattr(ps, "LIVE_AJANLO_PERCEK", (1,))
    m = _proba_match(ismetles=20)          # 80 mp
    r = live_figure_suggestions(m, ALAP_FIGURAK)
    assert [a["team"] for a in r["alerts"]] == ["away"]
    a = r["alerts"][0]
    assert a["perc"] == 1 and a["team_name"] == "Mi" and a["sablon"] is True
    assert a["text"].startswith("Figura-ajánló (1. perc): Mi eddig látott "
                                "fala ellen az alap-figurák közül a „")
    assert "% lövőhelyzet (alap fal: " in a["text"]
    # csak az addigi kockák: a meccs első 60 mp-e önmagában ugyanazt adja
    rovid = Match(m.meta, [f for f in m.frames if f.t <= 60 * 25])
    assert live_figure_suggestions(rovid, ALAP_FIGURAK)["alerts"] == r["alerts"]
    assert live_figure_suggestions(_proba_match(ismetles=5),
                                   ALAP_FIGURAK)["alerts"] == []
    assert live_figure_suggestions(m, [])["alerts"] == []


def test_az_elo_figura_ajanlo_a_lovokkel(monkeypatch):
    """A mezszámmal mentett figura záró lövője az élő ajánlóban is
    számít: a vendég (Mi) fala ellen a hazai lövőinek modelljével a
    pontszám a záró lövő szorzójával nő, a mondat megnevezi; modell
    nélkül az addig látott kockákból tanul (lövés nélkül: nincs
    szorzó)."""
    import handball.pipeline.play_simulation as ps
    from handball.pipeline.play_simulation import (AttackModel,
                                                   live_figure_suggestions)

    monkeypatch.setattr(ps, "LIVE_AJANLO_PERCEK", (1,))
    m = _proba_match(ismetles=20)
    figura = {"id": "a", "name": "Beúszás", "attackers": _FINOMITO_FIGURA,
              "labda": [0, 0, 1]}
    alap = live_figure_suggestions(m, [figura])["alerts"]
    assert [a["team"] for a in alap] == ["away"]
    assert alap[0]["lovo_mez"] is None and alap[0]["lovo_szorzo"] == 1.0
    _, e0 = ps.setplay_3d_match(_FINOMITO_FIGURA, DefenseModel(),
                                ball=[0, 0, 1])
    mez = [None] * len(_FINOMITO_FIGURA)
    mez[e0["attacker_id"] - 1] = 7
    tam = AttackModel(lovok={7: {"close": 1.3, "mid": 1.3, "far": 1.3}})
    vele = live_figure_suggestions(m, [{**figura, "mez": mez}],
                                   tamadas={"away": tam})["alerts"]
    assert vele[0]["lovo_mez"] == 7 and vele[0]["lovo_szorzo"] == 1.3
    assert abs(vele[0]["pont_pct"] - 1.3 * alap[0]["pont_pct"]) < 0.2
    assert ("% lövőhelyzet — a 7-es lövésével, aki innen 1,3× annyit lő "
            "be, mint amennyit a helyzet ér (alap fal: ") in vele[0]["text"]
    # Mezszámmal, de modell nélkül (az addigi kockákból nincs lövő).
    nelkul = live_figure_suggestions(m, [{**figura, "mez": mez}])["alerts"]
    assert nelkul[0]["lovo_mez"] == 7 and nelkul[0]["lovo_szorzo"] == 1.0


def test_a_kit_kinek_parositas_a_modellekbol():
    """Kit kinek a kész modellekből: a távolról veszélyes lövő (a sáv
    szorzója legalább KITKINEK_LOVO_SZORZO) a leggyakoribb sávjával; a
    sávban álló lassú kilépő védő helyett a kilépőt javasolja, a mondat
    mindent kimond; ha ott kilépő áll, "jó a párosítás"; ha nincs
    kilépőnk, azt mondja; védő nélkül "nincs tanult védő"; a közeli vagy
    átlagos lövő és a kevés lövés kimarad; modell nélkül üres."""
    from handball.pipeline.play_simulation import (AttackModel,
                                                   KITKINEK_MIN_LOVES,
                                                   lovo_sav_index,
                                                   shooter_defender_pairs)

    assert [lovo_sav_index(y) for y in (0.0, 6.6, 6.7, 13.3, 13.4, 20.0)] == [
        0, 0, 1, 1, 2, 2]
    tam = AttackModel(lovok={9: {"far": 1.3}, 10: {"close": 1.3},
                             11: {"mid": 1.0}, 12: {"mid": 1.2}})
    savok = {9: [5, 1, 0], 12: [KITKINEK_MIN_LOVES - 1, 0, 0]}
    vedok = [{"mez": 3, "y": 3.0, "press_rate": 0.1},
             {"mez": 6, "y": 14.0, "press_rate": 0.6},
             {"mez": 4, "y": 9.0, "press_rate": None}]
    p = shooter_defender_pairs(tam, savok, vedok)
    assert len(p) == 1
    s = p[0]
    assert (s["lovo_mez"], s["sav"], s["sav_nev"], s["band"], s["szorzo"],
            s["lovesek"]) == (9, 0, "szélső", "far", 1.3, 5)
    assert (s["vedo_mez"], s["vedo_kilepes"], s["javasolt_mez"],
            s["javasolt_kilepes"]) == (3, 0.1, 6, 0.6)
    assert s["verdict"] == (
        "a 9-es (távolról 1,3× annyit lő be, mint amennyit a helyzetei "
        "érnek) a szélső sávból lő (5 lövés); ott a 3-as áll, aki ritkán "
        "lép ki (10%) — a 6-os (kilépő, 60%) álljon vele szemben")
    # A sávban kilépő áll: jó a párosítás; str kulcsú sáv-minta is jó.
    jo = shooter_defender_pairs(tam, {"9": [5, 1, 0]},
                                [{"mez": 3, "y": 3.0, "press_rate": 0.7}])[0]
    assert jo["javasolt_mez"] is None and jo["verdict"].endswith(
        "ott a 3-as áll, aki rendre kilép (70%) — jó a párosítás")
    # Lassú védő, de nincs kilépőnk.
    nincs = shooter_defender_pairs(tam, savok,
                                   [{"mez": 3, "y": 3.0, "press_rate": 0.1}])[0]
    assert nincs["javasolt_mez"] is None and "nincs kilépő védőnk" in nincs["verdict"]
    # Ismeretlen kilépésű védő a sávban + kilépő: csere.
    ism = shooter_defender_pairs(tam, savok, [
        {"mez": 3, "y": 3.0, "press_rate": None},
        {"mez": 6, "y": 14.0, "press_rate": 0.6}])[0]
    assert ism["javasolt_mez"] == 6 and "kilépését nem ismerjük" in ism["verdict"]
    # Védő nélkül a sávban.
    ures = shooter_defender_pairs(tam, savok,
                                  [{"mez": 6, "y": 14.0, "press_rate": 0.6}])[0]
    assert ures["vedo_mez"] is None and "ott nincs tanult védő" in ures["verdict"]
    assert shooter_defender_pairs(tam, savok, []) and \
        shooter_defender_pairs(None, savok, vedok) == []
    assert shooter_defender_pairs(AttackModel(lovok={9: {"far": 1.3}}), {},
                                  vedok) == []


def test_a_kit_kinek_valodi_meccsbol_es_a_felderitesben(monkeypatch):
    """A valódi láncon (szimulált meccs: a hazai lő, a vendég véd
    mezszámos fallal): a vendég oldal párjai a tanult lövőkből, a sáv-
    mintából és a fal védőiből állnak össze (ugyanaz, mint a kész
    modellekből), a hazainak nincs (az ellenfél nem lő). A felderítés a
    sáv-mintát és a fal védőnkénti mintáját str kulccsal tárolja, két
    meccsből összeadja, a képet (kk_lovok) újraszámolja; az edzői kulcs,
    a meccsterv (471), az edzésterv (491) és az összefoglaló ugyanebből
    beszél."""
    import handball.pipeline.training as tr
    from handball.pipeline.coach_summary import coach_summary
    from handball.pipeline.play_simulation import (
        AttackModel, _lovo_sav_minta, _vedok_mintabol,
        shooter_defender_matchup, shooter_defender_pairs)
    from handball.pipeline.scouting import (combine_reports, matchup_plan,
                                            scout_team)
    from handball.pipeline.training import training_focus
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=600, fps=25.0, seed=1,
                              shots_per_min=8, halftime_break_s=30)
    r = shooter_defender_matchup(m)
    assert r["home"] == {"parok": [], "verdict": None}
    parok = r["away"]["parok"]
    assert parok and r["away"]["verdict"] == parok[0]["verdict"]
    vedok = DefenseModel.learn(m, Team.AWAY).vedok
    assert parok == shooter_defender_pairs(
        AttackModel.learn(m, Team.HOME),
        _lovo_sav_minta(m, Team.HOME, TacticsConfig()), vedok)
    assert all(p["vedo_mez"] is not None for p in parok)

    opp = scout_team(m, Team.HOME)
    assert opp.kk_lovo_savok and all(isinstance(k, str) for k in opp.kk_lovo_savok)
    assert [p["lovo_mez"] for p in opp.kk_lovok] == [p["lovo_mez"] for p in parok]
    assert any(k.startswith("Távoli lövőjük: ") for k in opp.keys_to_game)
    own = scout_team(m, Team.AWAY)
    assert own.fal_vedok_minta and own.fal_kockak > 0
    assert _vedok_mintabol(own.fal_vedok_minta, own.fal_kockak) == vedok
    assert own.kk_lovok == []
    ketto = combine_reports([own, own])
    assert ketto.fal_kockak == 2 * own.fal_kockak
    for mez, v in own.fal_vedok_minta.items():
        assert ketto.fal_vedok_minta[mez]["n"] == 2 * v["n"]
    opp2 = combine_reports([opp, opp])
    for mez, v in opp.kk_lovo_savok.items():
        assert opp2.kk_lovo_savok[mez] == [2 * x for x in v]
    assert [p["lovo_mez"] for p in opp2.kk_lovok] == \
        [p["lovo_mez"] for p in opp.kk_lovok]
    terv = [s for s in matchup_plan(own, opp) if s.startswith("Kit kinek: ")]
    assert len(terv) == 1 and parok[0]["verdict"] in terv[0]
    assert not [s for s in matchup_plan(opp, own) if s.startswith("Kit kinek: ")]

    monkeypatch.setattr(tr, "MAX_ITEMS", 10_000)
    f = training_focus(m)
    csere = [p for p in parok if p["javasolt_mez"] is not None]
    tetel = [i for i in f["away"] if i["title"] == "Kit kinek: a lövőjük és a védőnk"]
    assert len(tetel) == (1 if csere else 0)
    if csere:
        assert tetel[0]["why"].endswith(csere[0]["verdict"])
    assert not [i for i in f["home"] if i["title"] == "Kit kinek: a lövőjük és a védőnk"]
    szoveg = " ".join(s["body"] for s in coach_summary(m)["sections"])
    assert f"falának kit kinek: {parok[0]['verdict']}." in szoveg


def test_a_kapus_valasztas_a_mintakbol():
    """Kapus-választás a kész mintákból: a lövőik sávonkénti lövésszáma
    és tanult szorzója × a kapusok sáv-szorzója — a kevesebbet kapó
    kapus; az érték visszaszámolható; a mondat a sávot is mondja; kis
    különbségnél "nincs érdemi különbség" (dontes False); egy tanult
    kapus, tanult sáv nélküli kapus vagy lövő-minta nélkül None."""
    from handball.pipeline.play_simulation import (
        KAPUS_MIN_LOVES, KAPUS_VALASZTAS_ELTERES, UTOLSO_LOVES_TAV_M,
        _kapus_szorzo, _lovo_szorzo, keeper_choice_from)
    from handball.pipeline.xg import xg_of_position

    lovok = {9: {"far": [10, 6, 3.0]}, 10: {"close": [4, 2, 1.8]}}
    kapusok = {16: {"far": [10, 8], "close": [6, 2]},
               12: {"far": [10, 3], "close": [6, 4]}}
    r = keeper_choice_from(lovok, kapusok)
    assert (r["kapus_mez"], r["masik_mez"]) == (16, 12)
    assert r["dontes"] is True and r["elteres"] >= KAPUS_VALASZTAS_ELTERES
    lsz = _lovo_szorzo(lovok)
    xg = {s: xg_of_position(40.0 - d, 10.0, 40.0)
          for s, d in UTOLSO_LOVES_TAV_M.items()}
    k16 = _kapus_szorzo(kapusok[16])
    vart = (10 * xg["far"] * lsz[9]["far"] * k16["far"]
            + 4 * xg["close"] * lsz[10]["close"] * k16["close"]) / 14
    assert abs(r["ertek"] - vart) < 1e-3
    assert [k["mez"] for k in r["kapusok"]] == [16, 12]
    assert r["verdict"].startswith(
        "a 16-os álljon a kapuban az ő lövőik ellen: ")
    assert "— távolról 0,7× annyit kap, mint az átlag" in r["verdict"]
    # Egyforma kapusok: nincs érdemi különbség.
    egyf = keeper_choice_from(lovok, {16: {"far": [10, 5]}, 12: {"far": [10, 5]}})
    assert egyf["dontes"] is False and egyf["elteres"] == 0.0
    assert egyf["verdict"].startswith("a két kapusunk között nincs érdemi")
    assert keeper_choice_from(lovok, {16: {"far": [10, 8]}}) is None
    assert keeper_choice_from(lovok, {16: {"far": [10, 8]},
                                      12: {"far": [KAPUS_MIN_LOVES - 1, 0]}}) is None
    assert keeper_choice_from({}, kapusok) is None
    assert keeper_choice_from({"9": {"far": [10, 6, 3.0]}}, kapusok)["kapus_mez"] == 16


def test_a_kapus_valasztas_valodi_meccsbol_es_a_felderitesben(monkeypatch):
    """A valódi láncon (szimulált meccs, csapatonként egy kapus): a
    kapusonkénti sáv-mérleg egy kapusra összegezve a csapat-kapus
    mérlege; egy kapussal a választás None. A felderítés a mérleget str
    kulccsal tárolja, két meccsből összeadja, a képet (kc_kapusok)
    újraszámolja, a kulcs a kapus gyenge sávját mondja; két kapussal (a
    minta kézzel bővítve) a meccsterv (472) és — a motor mintáját
    cserélve — az edzésterv (492) és az összefoglaló is szól."""
    import handball.pipeline.play_simulation as ps
    import handball.pipeline.training as tr
    from handball.pipeline.coach_summary import coach_summary
    from handball.pipeline.play_simulation import (
        _kapus_minta, _kapus_minta_kapusonkent, _kapus_szorzo,
        keeper_choice, keeper_choice_from)
    from handball.pipeline.scouting import (combine_reports, matchup_plan,
                                            scout_team)
    from handball.pipeline.training import training_focus
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=600, fps=25.0, seed=1,
                              shots_per_min=8, halftime_break_s=30)
    cfg = TacticsConfig()
    kk = _kapus_minta_kapusonkent(m, Team.AWAY, cfg)
    assert len(kk) == 1
    (mez, savok), = kk.items()
    assert isinstance(mez, int) and savok == _kapus_minta(m, Team.AWAY, cfg)
    assert _kapus_minta_kapusonkent(m, Team.HOME, cfg) == {}
    assert keeper_choice(m) == {"home": None, "away": None}

    own = scout_team(m, Team.AWAY)
    assert list(own.kapusok_minta) == [str(mez)]
    assert own.kc_kapusok == [{"mez": mez, "lovesek": sum(v[0] for v in savok.values()),
                               "szorzok": _kapus_szorzo(savok)}]
    ketto = combine_reports([own, own])
    for s, v in own.kapusok_minta[str(mez)].items():
        assert ketto.kapusok_minta[str(mez)][s] == [2 * v[0], 2 * v[1]]
    assert ketto.kc_kapusok[0]["mez"] == mez
    gyenge = [s for s, v in _kapus_szorzo(savok).items() if v >= 1.1]
    assert any(k.startswith("Kapusaik: ") for k in own.keys_to_game) == bool(gyenge)
    opp = scout_team(m, Team.HOME)
    assert opp.kapusok_minta == {} and opp.kc_kapusok == []
    assert not [s for s in matchup_plan(own, opp) if "Kapus-választás" in s]
    # Két kapus (a második kézzel: minden sávban erősebb): a meccsterv
    # a mi kapusainkat az ő lövőikkel párosítja.
    own.kapusok_minta["99"] = {s: [v[0], v[0]] for s, v in savok.items()}
    vart = keeper_choice_from(opp.lsp_lovo_minta, own.kapusok_minta)
    assert vart and vart["kapus_mez"] == 99
    terv = [s for s in matchup_plan(own, opp) if s.startswith("Kapus-választás: ")]
    assert len(terv) == 1 and vart["verdict"] in terv[0]
    # A motor mintáját cserélve: az edzésterv és az összefoglaló.
    ketkapus = dict(kk)
    ketkapus[99] = {s: [v[0], v[0]] for s, v in savok.items()}
    monkeypatch.setattr(ps, "_kapus_minta_kapusonkent",
                        lambda match, team, config: ketkapus
                        if team == Team.AWAY else {})
    monkeypatch.setattr(tr, "MAX_ITEMS", 10_000)
    r = keeper_choice(m)
    assert r["home"] is None and r["away"]["kapus_mez"] == 99
    tetel = [i for i in training_focus(m)["away"]
             if i["title"] == "Kapus-választás ellenük"]
    assert len(tetel) == (1 if r["away"]["dontes"] else 0)
    if tetel:
        assert tetel[0]["why"].endswith(r["away"]["verdict"])
    szoveg = " ".join(s["body"] for s in coach_summary(m)["sections"])
    assert (f"kapus-választása: {r['away']['verdict']}." in szoveg) == bool(
        r["away"]["dontes"])


def test_a_falvalasztas_a_figuraik_ellen():
    """Falválasztás: a vendég (Mi) fala ellen a hazai visszatérő figurája
    minden rendszerben lejátszva — a mostani a tanult rendszer, a pontja
    a védekezési próba pontja, a javasolt a legkisebb, a váltás csak
    FALVALASZTAS_ELTERES_PP felett, a mondat a motoré; a hazai oldalon
    (nincs ellenfél-figura) None; egyszeri támadásból None."""
    from handball.pipeline.play_simulation import (
        AttackModel, FALVALASZTAS_ELTERES_PP, VEDEKEZESI_RENDSZEREK,
        defense_system_choice, defense_test, recurring_figures,
        rendszer_nevelovel)

    m = _proba_match()
    r = defense_system_choice(m)
    assert r["home"] is None
    p = r["away"]
    assert p and set(p["rendszerek"]) == set(VEDEKEZESI_RENDSZEREK)
    assert p["figurak"] == 1
    fal = DefenseModel.learn(m, Team.AWAY)
    assert p["mostani"] == fal.rendszer
    assert p["mostani_pct"] == p["rendszerek"][fal.rendszer]
    proba = defense_test(m, Team.HOME, fal,
                         tamadas=AttackModel.learn(m, Team.HOME))
    assert abs(p["mostani_pct"] - proba["figurak"][0]["pont_pct"]) < 0.15
    assert p["javasolt_pct"] == min(p["rendszerek"].values())
    assert p["javulas_pp"] == round(p["mostani_pct"] - p["javasolt_pct"], 1)
    assert p["valt"] == (p["javasolt"] != p["mostani"]
                         and p["javulas_pp"] >= FALVALASZTAS_ELTERES_PP)
    assert p["verdict"].startswith("a figuráik ellen ")
    if p["valt"]:
        assert f"{rendszer_nevelovel(p['javasolt'])} zár jobban" in p["verdict"]
    else:
        assert f"a mostani {p['mostani']} a jó" in p["verdict"]
    assert len(recurring_figures(m, Team.HOME)) == 1
    assert recurring_figures(m, Team.AWAY) == []
    assert defense_system_choice(_proba_match(ismetles=1)) == {
        "home": None, "away": None}
    assert [rendszer_nevelovel(x) for x in ("6-0", "5-1", "3-2-1")] == [
        "a 6-0", "az 5-1", "a 3-2-1"]


def test_a_falvalasztas_a_felderitesben_es_az_edzestervben(monkeypatch):
    """A felderítés a figuráik ellen javasolt rendszert meccsenként
    számolja (az ő jelentésükben, a velük szemben védekező oldal
    képéből), két meccsből összeadja; a kulcs és a meccsterv (473) a
    többségi rendszerről szól legalább FV_MIN_MECCS meccsből (a ti
    szokásos falatokhoz mérve), egy meccsből még nem; az edzésterv (493)
    és az összefoglaló csak érdemi váltásnál."""
    import handball.pipeline.training as tr
    from handball.pipeline.coach_summary import coach_summary
    from handball.pipeline.play_simulation import (FV_MIN_MECCS,
                                                   defense_system_choice,
                                                   rendszer_nevelovel)
    from handball.pipeline.scouting import (combine_reports, matchup_plan,
                                            scout_team)
    from handball.pipeline.training import training_focus

    m = _proba_match()
    p = defense_system_choice(m)["away"]
    opp = scout_team(m, Team.HOME)
    assert (opp.fv_rendszer_db, opp.fv_meccsek, opp.fv_valt_db) == (
        {p["javasolt"]: 1}, 1, int(p["valt"]))
    own = scout_team(m, Team.AWAY)
    assert own.fv_meccsek == 0 and own.fv_rendszer_db == {}
    assert FV_MIN_MECCS == 2
    assert not any(k.startswith("A figuráikat a szimulációban")
                   for k in opp.keys_to_game)
    ketto = combine_reports([opp, opp])
    assert ketto.fv_meccsek == 2 and ketto.fv_rendszer_db == {p["javasolt"]: 2}
    kulcs = (f"A figuráikat a szimulációban {rendszer_nevelovel(p['javasolt'])} "
             "zárta a legjobban (2/2 meccs)")
    assert any(k.startswith(kulcs) for k in ketto.keys_to_game)
    own2 = combine_reports([own, own])
    terv = [s for s in matchup_plan(own2, ketto)
            if "zárta a legjobban (2/2 meccs)" in s]
    if own2.defense_main in ("—", "", None):
        assert terv == []
    elif own2.defense_main == p["javasolt"]:
        assert len(terv) == 1 and "maradjatok nála" in terv[0]
    else:
        assert len(terv) == 1 and \
            f"próbáljátok {rendszer_nevelovel(p['javasolt'])}-et" in terv[0]
    assert not [s for s in matchup_plan(ketto, own2) if "zárta a legjobban" in s]
    monkeypatch.setattr(tr, "MAX_ITEMS", 10_000)
    tetel = [i for i in training_focus(m)["away"]
             if i["title"] == "Falváltás a figuráik ellen"]
    assert len(tetel) == (1 if p["valt"] else 0)
    if tetel:
        assert tetel[0]["why"].endswith(p["verdict"])
    szoveg = " ".join(s["body"] for s in coach_summary(m)["sections"])
    assert (f"falválasztása: {p['verdict']}." in szoveg) == bool(p["valt"])


def test_az_engedett_lovo_a_kesz_modellbol():
    """Engedett lövő a kész modellből: akinek MINDEN tanult távoli /
    közepes sávja legfeljebb LOVO_GYENGE_SZORZO; a leggyengébb sáv kerül
    a sorba a lövésszámmal és a góllal (a minta kulcsa int vagy str);
    közelről veszélyes lövőnél (KITKINEK_LOVO_SZORZO) a mondat a betörés
    zárásáról szól; a jó, a félig jó vagy a csak közelről tanult lövő
    kimarad; modell nélkül üres."""
    from handball.pipeline.play_simulation import (KITKINEK_LOVO_SZORZO,
                                                   LOVO_GYENGE_SZORZO,
                                                   AttackModel,
                                                   allowed_shooters_from)

    assert (LOVO_GYENGE_SZORZO, KITKINEK_LOVO_SZORZO) == (0.85, 1.1)
    tamadas = AttackModel(lovok={
        7: {"far": 0.8, "mid": 0.85, "close": 1.2},   # gyenge távolról, betörő
        9: {"far": 1.2},                              # veszélyes — kit kinek
        10: {"mid": 0.7, "far": 0.9},                 # a far sávja nem gyenge
        11: {"close": 0.7},                           # nincs távoli sávja
        12: {"mid": 0.75}})                           # gyenge; betörése ismeretlen
    minta = {7: {"far": [6, 1, 2.1], "mid": [4, 1, 1.5], "close": [5, 4, 2.0]},
             "12": {"mid": [5, 1, 1.6]}}
    ki = allowed_shooters_from(tamadas, minta)
    assert [(r["mez"], r["sav"], r["szorzo"], r["lovesek"], r["gol"],
             r["kozel"], r["betores"]) for r in ki] == [
        (12, "mid", 0.75, 5, 1, None, False),
        (7, "far", 0.8, 6, 1, 1.2, True)]
    assert ki[1]["verdict"] == (
        "a 7-es ellen nem kell kilépni: távolról 0,8× annyit lő be, mint "
        "amennyit a helyzetei érnek (6 lövés, 1 gól) — a távoli lövése "
        "ajándék, a betörését viszont zárni kell: közelről 1,2×")
    assert ki[0]["verdict"] == (
        "a 12-es ellen nem kell kilépni: közepes távolságból 0,8× annyit "
        "lő be, mint amennyit a helyzetei érnek (5 lövés, 1 gól) — a "
        "közepes távolságú lövése ajándék, a fal maradjon hátul vele "
        "szemben")
    assert allowed_shooters_from(None, {}) == []
    assert allowed_shooters_from(AttackModel(), {}) == []


def test_az_engedett_lovo_a_meccsbol_a_felderitesben_es_az_edzestervben(
        monkeypatch):
    """A meccs-szintű réteg a VÉDEKEZŐ oldalról nevez (a vendég fala a
    hazai gyenge távoli lövőjét kapja, a hazaié semmit); a felderítés
    képe az összegzett lövő-mintából újraszámolódik (két meccsből dupla
    lövésszám), a kulcs, a meccsterv (474 — csak ha a ti falatokban van
    kilépő védő), az edzésterv (494) és az összefoglaló a motor mondatát
    hozza; a másik oldalon semmi."""
    import handball.pipeline.play_simulation as ps
    import handball.pipeline.training as tr
    from handball.pipeline.coach_summary import coach_summary
    from handball.pipeline.play_simulation import allowed_shooters
    from handball.pipeline.scouting import (combine_reports, matchup_plan,
                                            scout_team)
    from handball.pipeline.training import training_focus

    # A hazai 7-es: távolról 6 lövés 1 gól (2,0 xG → 0,75×), közelről 5
    # lövés 4 gól (2,0 xG → 1,45×, a felső korlát 1,3-ra szorítja); a
    # vendég nem lő.
    monkeypatch.setattr(ps, "_lovo_minta", lambda match, team, config: (
        {7: {"far": [6, 1, 2.0], "close": [5, 4, 2.0]}}
        if team == Team.HOME else {}))
    m = _proba_match()
    el = allowed_shooters(m)
    assert el["home"] == {"lovok": [], "verdict": None}
    [sor] = el["away"]["lovok"]
    assert (sor["mez"], sor["sav"], sor["szorzo"], sor["lovesek"], sor["gol"],
            sor["kozel"], sor["betores"]) == (7, "far", 0.75, 6, 1, 1.3, True)
    assert el["away"]["verdict"] == sor["verdict"]
    assert sor["verdict"].startswith(
        "a 7-es ellen nem kell kilépni: távolról 0,8×")
    assert sor["verdict"].endswith("zárni kell: közelről 1,3×")

    opp = scout_team(m, Team.HOME)
    assert [(r["mez"], r["lovesek"]) for r in opp.el_lovok] == [(7, 6)]
    assert f"Engedett lövőjük: {sor['verdict']}." in opp.keys_to_game
    own = scout_team(m, Team.AWAY)
    assert own.el_lovok == []
    assert not any(k.startswith("Engedett lövőjük") for k in own.keys_to_game)
    ketto = combine_reports([opp, opp])
    assert [(r["mez"], r["lovesek"], r["gol"]) for r in ketto.el_lovok] == [
        (7, 12, 2)]
    # A meccsterv csak kilépő védővel szól (különben a fal úgyis hátul
    # marad): a falatok tanult védői a (patchelt) védőnkénti mintából.
    monkeypatch.setattr(ps, "_vedok_mintabol", lambda minta, kockak: [
        {"mez": 5, "y": 7.0, "press_rate": 0.2}])
    assert not [s for s in matchup_plan(own, opp)
                if s.startswith("Engedett lövő:")]
    monkeypatch.setattr(ps, "_vedok_mintabol", lambda minta, kockak: [
        {"mez": 4, "y": 10.0, "press_rate": 0.6},
        {"mez": 5, "y": 7.0, "press_rate": 0.2}])
    [terv] = [s for s in matchup_plan(own, opp) if s.startswith("Engedett lövő:")]
    assert terv == (f"Engedett lövő: {sor['verdict']} — a ti kilépőtök, a 4-es "
                    "(60%) vele szemben maradjon hátul, a kilépést a veszélyes "
                    "lövőre tartsa.")
    assert not [s for s in matchup_plan(opp, own)
                if s.startswith("Engedett lövő:")]
    monkeypatch.setattr(tr, "MAX_ITEMS", 10_000)
    cim = "Hátul maradás az engedett lövő ellen"
    tetel = [i for i in training_focus(m)["away"] if i["title"] == cim]
    assert len(tetel) == 1 and tetel[0]["why"] == sor["verdict"]
    assert tetel[0]["area"] == "védekezés"
    assert not [i for i in training_focus(m)["home"] if i["title"] == cim]
    szoveg = " ".join(s["body"] for s in coach_summary(m)["sections"])
    assert f"falának engedett lövője: {sor['verdict']}." in szoveg


def test_egy_jatekos_lovo_modellje_es_a_helye_az_elosztasban(monkeypatch):
    """A Döntések panel lövő-modellje: a játékos mezszáma és csapata a
    kockákból; sávonként a nyers minta és a tanult szorzó (LOVO_MIN_LOVES
    alatt None — "kevés minta"); a lövés-elosztásban a tanult sávjainak
    részesedése, és hogy ő a "többet lőhetne"; mezszám vagy lövés nélkül
    None; a valódi láncon a minta egyezik a _lovo_minta sorával."""
    import handball.pipeline.play_simulation as ps
    from handball.pipeline.play_simulation import (_lovo_minta,
                                                   player_shooter_profile)
    from handball.sim.match_simulator import simulate_ground_truth

    monkeypatch.setattr(ps, "_lovo_minta", lambda match, team, config: (
        {1: {"close": [3, 3, 1.5], "far": [2, 0, 0.6]},
         10: {"close": [9, 3, 4.5]}} if team == Team.HOME else {}))
    m = _proba_match()
    p = player_shooter_profile(m, 1)
    assert (p["jersey"], p["team"]) == (1, "home")
    assert [(s["sav"], s["lovesek"], s["gol"], s["xg"], s["szorzo"])
            for s in p["savok"]] == [("close", 3, 3, 1.5, 1.3),
                                     ("far", 2, 0, 0.6, None)]
    assert p["felirat"] == (
        "közelről 3 lövés, 3 gól (1,5 várható) — 1,3× annyit lő be, mint "
        "amennyit a helyzetei érnek; távolról 2 lövés, 0 gól (0,6 várható) "
        "— kevés minta")
    el = p["elosztas"]
    assert el["szerep"] == "tobbet"
    assert [(r["sav"], r["arany_pct"]) for r in el["parosok"]] == [
        ("close", 21.4)]
    assert el["verdict"].startswith("többet lőhetne az 1-es közelről")
    assert player_shooter_profile(m, 2) is None          # nincs lövése
    assert player_shooter_profile(m, 999) is None        # nincs ilyen
    monkeypatch.undo()
    valodi = simulate_ground_truth(duration_s=600, fps=25.0, seed=1,
                                   shots_per_min=8, halftime_break_s=30)
    minta = _lovo_minta(valodi, Team.HOME, TacticsConfig())
    mez = next(iter(sorted(minta)))
    pid = next(pl.track_id for f in valodi.frames for pl in f.players
               if pl.team == Team.HOME and pl.jersey_number == mez)
    vp = player_shooter_profile(valodi, pid)
    assert vp["jersey"] == mez
    assert {s["sav"]: s["lovesek"] for s in vp["savok"]} == {
        s: v[0] for s, v in minta[mez].items()}


def test_a_lovo_modell_probaja_a_kovetkezo_meccsen():
    """A lövő-modell próbája: következetes lövőknél (minden meccsen
    ugyanaz a túl- / alulteljesítés) a korábbiakból tanult szorzó a
    következő meccs góljait pontosabban becsüli, mint a nyers xG; meccsről
    meccsre váltakozó formánál pontatlanabbul; kevés becsülhető csoportnál
    (PROBA_MIN_CSOPORT alatt) None; a könyvtár-összeg a csapatok
    hibáinak összegéből; a minta szöveg-kulcsa (a tárból) is megy."""
    from handball.pipeline.play_simulation import (
        PROBA_ITELET_PCT, PROBA_MIN_CSOPORT, shooter_model_backtest,
        shooter_model_backtest_summary)

    assert (PROBA_MIN_CSOPORT, PROBA_ITELET_PCT) == (5, 5.0)
    jo = {7: {"close": [6, 5, 3.0]}, 9: {"far": [6, 1, 2.4]},
          10: {"mid": [5, 2, 2.0]}}
    r = shooter_model_backtest([jo, jo, jo, jo])
    assert (r["meccsek"], r["csoportok"], r["lovesek"]) == (4, 9, 51)
    assert r["xg_hiba"] == 10.2 and r["modell_hiba"] < r["xg_hiba"]
    assert r["javulas_pct"] >= PROBA_ITELET_PCT
    assert r["verdict"].startswith(
        "a korábbi meccsekből tanult lövő-modell a következő meccs góljait "
        f"{r['javulas_pct']:.0f}%-kal pontosabban becsülte")
    # Az egyéni képesség: a csapat-szorzót is veri.
    assert r["egyeni_pct"] >= PROBA_ITELET_PCT
    assert r["modell_hiba"] < r["csapat_hiba"]
    assert r["verdict"].endswith("az egyéni szorzókra lehet építeni")
    # Mindenki ugyanannyival teljesít túl: a csapat-szorzó ugyanolyan jó
    # — a javulás a csapat befejezése, nem az egyes lövőké.
    c = {7: {"close": [8, 6, 4.0]}, 9: {"far": [8, 3, 2.0]},
         10: {"mid": [8, 4, 2.0]}}
    rc = shooter_model_backtest([c, c, c, c])
    assert rc["javulas_pct"] >= PROBA_ITELET_PCT
    assert rc["egyeni_pct"] < PROBA_ITELET_PCT
    assert "de a csapat átlagos befejezésénél nem jobban" in rc["verdict"]
    a = {7: {"close": [6, 6, 3.0]}, 9: {"far": [6, 4, 2.4]},
         10: {"mid": [5, 5, 2.0]}}
    b = {7: {"close": [6, 0, 3.0]}, 9: {"far": [6, 0, 2.4]},
         10: {"mid": [5, 0, 2.0]}}
    r2 = shooter_model_backtest([a, b, a, b])
    assert r2["javulas_pct"] <= -PROBA_ITELET_PCT
    assert "pontatlanabbul" in r2["verdict"]
    assert shooter_model_backtest([jo]) is None
    assert shooter_model_backtest([jo, jo]) is None        # 3 csoport < 5
    szoveg = [{str(k): v for k, v in m.items()} for m in (jo, jo, jo, jo)]
    assert shooter_model_backtest(szoveg) == r
    o = shooter_model_backtest_summary([r, r2])
    assert (o["csapatok"], o["csoportok"]) == (2, 18)
    assert o["xg_hiba"] == round(r["xg_hiba"] + r2["xg_hiba"], 2)
    assert o["verdict"].startswith("a könyvtár 2 csapatán")
    assert shooter_model_backtest_summary([]) is None


def test_a_kapus_modell_probaja_a_kovetkezo_meccsen():
    """A kapus-modell próbája: ha a kapus egy sávban következetesen
    gyengébb, a korábbiakból tanult sáv-szorzó a következő meccs kapott
    góljait pontosabban becsüli, mint az átlagos kapus ÉS a sávok nélküli
    szorzó; ha minden sávban egyformán jó, csak az átlagos kapusnál
    pontosabb ("az egész kapura szól"); váltakozó formánál pontatlanabb;
    kevés csoportnál None; a könyvtár-összeg a csapatok hibáiból."""
    from handball.pipeline.play_simulation import (
        PROBA_ITELET_PCT, keeper_model_backtest, keeper_model_backtest_summary)

    sav = {"far": [10, 3], "close": [8, 4], "mid": [6, 3]}
    r = keeper_model_backtest([sav] * 4)
    assert (r["meccsek"], r["csoportok"], r["lovesek"]) == (4, 9, 72)
    assert r["javulas_pct"] >= PROBA_ITELET_PCT
    assert r["sav_pct"] >= PROBA_ITELET_PCT
    assert r["verdict"].endswith("a kapus sávjaira lehet építeni")
    egyforma = {"far": [10, 8], "close": [8, 4], "mid": [6, 4]}
    e = keeper_model_backtest([egyforma] * 4)
    assert e["javulas_pct"] >= PROBA_ITELET_PCT > e["sav_pct"]
    assert "az egész kapura szól" in e["verdict"]
    a = {"far": [10, 9], "close": [8, 7], "mid": [6, 5]}
    b = {"far": [10, 2], "close": [8, 0], "mid": [6, 1]}
    v = keeper_model_backtest([a, b, a, b])
    assert v["javulas_pct"] <= -PROBA_ITELET_PCT
    assert "pontatlanabbul" in v["verdict"]
    assert keeper_model_backtest([sav, sav]) is None
    assert keeper_model_backtest([]) is None
    o = keeper_model_backtest_summary([r, e])
    assert o["csapatok"] == 2 and o["csoportok"] == 18
    assert o["atlag_hiba"] == round(r["atlag_hiba"] + e["atlag_hiba"], 2)
    assert o["verdict"].startswith("a könyvtár 2 csapatán")
    assert keeper_model_backtest_summary([]) is None


def test_a_vedo_modell_probaja():
    """defender_model_backtest: ha a védők kilépési hajlama következetesen
    egyéni (a 2-es mindig sokat, a 3-as keveset lép ki), a korábbi
    meccsekből tanult egyéni arány pontosabban jósol, mint a fal átlaga
    ("egyénre szabható"); ha mindenki ugyanúgy lép ki, nem; kevés párnál
    None. A model_trust_summary "vedo" része."""
    from handball.pipeline.play_simulation import (PROBA_MIN_CSOPORT,
                                                   defender_model_backtest,
                                                   model_trust_summary)

    def v(kozel, ralepett):
        return {"n": 100, "y_osszeg": 0.0, "kozel": kozel,
                "ralepett": ralepett, "masodik": 10, "kettozott": 3}

    egyeni = [{"2": v(20, 16), "3": v(20, 4)} for _ in range(6)]
    p = defender_model_backtest(egyeni)
    assert p["parok"] == 10 and p["javulas_pct"] > 0
    assert p["verdict"].startswith("a védők egyéni kilépési hajlama")
    assert "egyénre szabható" in p["verdict"]
    assert p["kettozes"] is not None
    kozos = [{"2": v(20, 10), "3": v(20, 10)} for _ in range(6)]
    q = defender_model_backtest(kozos)
    assert q["javulas_pct"] == 0.0 and "közös szokás" in q["verdict"]
    assert defender_model_backtest(egyeni[:2]) is None
    assert 2 < PROBA_MIN_CSOPORT
    assert model_trust_summary(None, None, None, p).startswith(
        "védő-modell: egyénre szabható (+")
    assert model_trust_summary(None, None, None, q) == (
        "védő-modell: a kilépés a fal közös szokása")


def test_az_ai_megbizhatosag_egy_sorban():
    """A három próba egy sorban: a lövő-szorzó megbízható / csak csapat-
    szinten / óvatosan / semleges; a kapus-sávok ugyanígy (a sávok nélküli
    szorzóhoz mérve); a döntés-tanácsok a százalékpont-különbség szerint;
    ítélet nélkül None."""
    from handball.pipeline.play_simulation import model_trust_summary

    assert model_trust_summary(None, None, None) is None
    sor = model_trust_summary(
        {"javulas_pct": 48.0, "egyeni_pct": 49.0},
        {"javulas_pct": 64.0, "sav_pct": -47.0},
        {"kulonbseg_pp": 20.0})
    assert sor == ("lövő-szorzók: megbízhatók (+48%); kapus-sávok: csak "
                   "egészében (a sávok nélküli szorzó jobb); döntés-tanácsok: "
                   "igazoltak (+20 százalékpont)")
    assert model_trust_summary({"javulas_pct": 5.1, "egyeni_pct": 0.0},
                               None, None) == (
        "lövő-szorzók: csak csapat-szinten (az egyéni szorzó nem jobb a "
        "csapaténál)")
    assert model_trust_summary({"javulas_pct": -17.0, "egyeni_pct": -3.0},
                               {"javulas_pct": 2.0, "sav_pct": 1.0},
                               {"kulonbseg_pp": -8.0}) == (
        "lövő-szorzók: óvatosan (-17%); kapus-sávok: semlegesek; "
        "döntés-tanácsok: óvatosan (-8 százalékpont)")


def test_az_elorejelzo_modellek_probai_egy_sorban():
    """forecast_trust_summary: az eredmény-előrejelzés és a gólszerzők a
    formához, az élő esély az álláshoz (a PROBA_ITELET_PCT küszöbével),
    a fal-becslés találata, a napi forma ítélete; ítélet nélkül None."""
    from handball.pipeline.play_simulation import forecast_trust_summary

    assert forecast_trust_summary() is None
    assert forecast_trust_summary(
        elore={"javulas_pct": 22.0}, golszerzo={"javulas_pct": -9.0},
        elo={"javulas_pct": 1.0}, vedekezes={"meccsek": 12, "talalat": 10},
        forma={"itelet": "visszaall"}) == (
        "eredmény-előrejelzés: pontosabb a formánál (+22%); gólszerzők: "
        "pontatlanabb a formánál (-9%); élő esély: nem tesz hozzá az "
        "álláshoz; fal-becslés: 12 meccsből 10 talált; napi forma: nem "
        "tart ki (a modell a jobb tipp)")
    assert forecast_trust_summary(elo={"javulas_pct": 14.0},
                                  forma={"itelet": "kitart"}) == (
        "élő esély: pontosít az álláshoz (+14%); napi forma: kitart")
    assert forecast_trust_summary(figura={"visszatero": 10,
                                          "visszatero_jott": 7}) == (
        "figurák: 10 esetből 7 jött újra")


def test_az_ai_probak_osszkepe():
    """model_checks_overview: próbánként, hogy ítélt-e és bizonyított-e —
    a lövő- és kapus-modell a megbízható szinttől, a döntés az igazolttól,
    a védő-modell a csapatok többségén, az előrejelzések a javulástól, a
    fal-becslés a liga felett, a figura-felderítés az "érdemes
    készülni"-től; ítélet nélkül None."""
    from handball.pipeline.play_simulation import model_checks_overview

    assert model_checks_overview({}) is None
    mc = {"osszes": {"javulas_pct": 48.0, "egyeni_pct": 49.0},
          "kapus_osszes": {"javulas_pct": 20.0, "sav_pct": -3.0},
          "dontes_osszes": {"kulonbseg_pp": 20.0},
          "vedok": [{"javulas_pct": 30.0}, {"javulas_pct": 1.0}],
          "elorejelzes": {"javulas_pct": 22.0},
          "golszerzo_proba": {"javulas_pct": -4.0},
          "elo_esely_proba": None,
          "vedekezes_proba": {"talalat": 10, "liga_talalat": 6},
          "kapus_valasztas_proba": {"itelet": "igazolt"},
          "figura_proba": {"verdict": "… — a visszatérő figuráikra érdemes "
                                      "készülni"},
          "felderites_proba": {"itelet": "atviheto"},
          "hetes_proba": {"itelet": "igazolt"},
          "hetes_irany_proba": {"itelet": "josolhato"}}
    o = model_checks_overview(mc)
    assert (o["itelt"], o["bizonyitott"]) == (12, 9)
    assert o["verdict"] == (
        "12 próbából 9 bizonyított: lövő-szorzók, döntés-tanácsok, "
        "eredmény-előrejelzés, fal-becslés, kapus-választás, "
        "figura-felderítés, felderítés, hetes-dobó, hetes-irány; még nem: "
        "kapus-sávok, védő-modell, gólszerzők")
    # A kapus-választás és a hetes-dobó csak az "igazolt", a felderítés
    # csak az "atviheto", a hetes-irány csak a "josolhato" ítélettel
    # bizonyított.
    o2 = model_checks_overview({**mc, "kapus_valasztas_proba": {
        "itelet": "egyenlo"}, "felderites_proba": {"itelet": "nem"},
        "hetes_proba": {"itelet": "nem"},
        "hetes_irany_proba": {"itelet": "nem"}})
    assert (o2["itelt"], o2["bizonyitott"]) == (12, 5)


def test_a_proba_szintjei_es_az_elo_jelzesek_onkalibralasa():
    """trust_levels: a három próba szintje (a lövőnél "csapat", ha csak a
    csapat-szint javít; a kapusnál "egeszeben", ha a sávok nélküli szorzó
    jobb). calibrate_alerts: a jelzés a "team" oldal szintjeit kapja; a
    részleges / negatív szint "óvatos" (a szöveg végén az ok), a
    "semleges" és a "megbizhato" nem; a bemenet nem változik."""
    from handball.pipeline.play_simulation import (BIZALOM_OVATOS_OKOK,
                                                   calibrate_alerts,
                                                   trust_levels)

    assert trust_levels(None, None, None) == {"lovo": None, "kapus": None,
                                              "dontes": None, "vedo": None}
    assert trust_levels(None, None, None, {"javulas_pct": 12.0})["vedo"] == \
        "egyeni"
    assert trust_levels(None, None, None, {"javulas_pct": 1.0})["vedo"] == \
        "kozos"
    assert trust_levels({"javulas_pct": 48.0, "egyeni_pct": 49.0},
                        {"javulas_pct": 64.0, "sav_pct": -47.0},
                        {"kulonbseg_pp": -8.0}) == {
        "lovo": "megbizhato", "kapus": "egeszeben", "dontes": "ovatos",
        "vedo": None}
    assert trust_levels({"javulas_pct": 6.0, "egyeni_pct": 0.0},
                        {"javulas_pct": -9.0, "sav_pct": 0.0},
                        {"kulonbseg_pp": 2.0}) == {
        "lovo": "csapat", "kapus": "ovatos", "dontes": "semleges",
        "vedo": None}

    be = [{"team": "home", "text": "A 7-es ellen lépjetek ki."},
          {"team": "away", "text": "A 9-es lőjön többet."},
          {"team": "home", "text": "Kapusváltás."}]
    ki = calibrate_alerts(be, {
        "home": {"lovo": "csapat", "kapus": "megbizhato"},
        "away": {"lovo": "semleges", "kapus": None}})
    assert be[0]["text"] == "A 7-es ellen lépjetek ki."
    assert ki[0]["ovatos"] is True
    assert ki[0]["megbizhatosag"] == {"kapus": "megbizhato",
                                      "lovo": "csapat"}
    assert ki[0]["text"] == ("A 7-es ellen lépjetek ki. (óvatosan: "
                             + BIZALOM_OVATOS_OKOK[("lovo", "csapat")] + ")")
    assert ki[1] == {**be[1], "megbizhatosag": {"lovo": "semleges"},
                     "ovatos": False}
    # Több óvatos ok egy jelzésen: mind a végére, "; "-vel.
    [k] = calibrate_alerts([be[2]], {"home": {"lovo": "ovatos",
                                              "kapus": "egeszeben"}})
    assert k["text"] == ("Kapusváltás. (óvatosan: "
                         + BIZALOM_OVATOS_OKOK[("kapus", "egeszeben")] + "; "
                         + BIZALOM_OVATOS_OKOK[("lovo", "ovatos")] + ")")
    # A védő-modell "közös szokás" szintje a párosítást óvatossá teszi.
    [pv] = calibrate_alerts([be[0]], {"home": {"vedo": "kozos"}})
    assert pv["ovatos"] and pv["text"].endswith(
        "(óvatosan: " + BIZALOM_OVATOS_OKOK[("vedo", "kozos")] + ")")
    [pe] = calibrate_alerts([be[0]], {"home": {"vedo": "egyeni"}})
    assert not pe["ovatos"]
    # Ítélet nélkül (kevés korábbi meccs) a jelzés változatlan szöveggel.
    assert calibrate_alerts(be, {}) == [
        {**a, "megbizhatosag": {}, "ovatos": False} for a in be]


def _ej_minta(n, gol, xg, golok=None, sav="close"):
    """Egy oldal előrejelzés-mintája (match_forecast_sample alakban)."""
    return {"lovesek": {sav: [n, gol, xg]},
            "golok": gol if golok is None else golok, "latott_golok": gol}


def test_a_meccs_elorejelzes_a_csapat_modellekbol():
    """match_forecast: két egyforma csapat (meccsenként 10 közeli lövés,
    5 gól, 5 xG — a liga-szint 1, a befejezés és a védelem szorzója 1)
    → 5–5, egyforma esélyek, az esélyek összege 1; a nem látott gólok
    átlaga hozzáadódik; az erősebb támadó a favorit; két meccsnél
    kevesebb előzménynél None; a mondat a csapatnevekkel."""
    from handball.pipeline.play_simulation import (match_forecast,
                                                   match_forecast_text)

    egy = [(_ej_minta(10, 5, 5.0), _ej_minta(10, 5, 5.0))] * 2
    f = match_forecast(egy, egy)
    assert (f["home_goals"], f["away_goals"]) == (5.0, 5.0)
    assert f["p_home"] == f["p_away"] and f["p_draw"] > 0
    assert abs(f["p_home"] + f["p_draw"] + f["p_away"] - 1.0) < 0.002
    assert (f["naiv_home"], f["naiv_away"]) == (5.0, 5.0)
    assert f["meccsek"] == {"home": 2, "away": 2}
    # Meccsenként egy nem látott gól a hazainál: +0,5 (a saját lőtt és a
    # vendég kapott nem látott góljainak átlaga).
    latatlan = [(_ej_minta(10, 5, 5.0, golok=6), _ej_minta(10, 5, 5.0))] * 2
    assert match_forecast(latatlan, egy)["home_goals"] == 5.5
    # Erősebb támadó: kétszer annyi lövés → a hazai a favorit.
    eros = [(_ej_minta(20, 10, 10.0), _ej_minta(10, 5, 5.0))] * 2
    g = match_forecast(eros, egy)
    assert g["home_goals"] > g["away_goals"] and g["p_home"] > g["p_away"]
    assert match_forecast(egy[:1], egy) is None
    assert match_forecast_text("A", "B", f) == (
        "A 5–5 B — esélyek: A {:.0f}%, döntetlen {:.0f}%, B {:.0f}%".format(
            f["p_home"] * 100, f["p_draw"] * 100, f["p_away"] * 100))
    assert match_forecast_text("A", "B", None) is None


def test_az_elorejelzes_probaja_idorendben():
    """forecast_backtest: csak az a meccs jelezhető előre, ahol mindkét
    csapatnak legalább két KORÁBBI meccse van; a sor előrejelzése a
    match_forecast a korábbiakból; a találat a döntetlen nélküli
    meccseken, a hiba a gólkülönbségé; kevés meccsnél None; a csapat-
    összegzés csak a csapat sorai; a mondat három ítélete."""
    from handball.pipeline.play_simulation import (ELOREJELZES_PROBA_MIN,
                                                   forecast_backtest,
                                                   forecast_backtest_text,
                                                   forecast_rows_summary,
                                                   match_forecast)

    erosseg = {"A": 14, "B": 10, "C": 6}
    parok = [("A", "B"), ("B", "C"), ("C", "A"), ("A", "C"), ("B", "A"),
             ("C", "B"), ("A", "B"), ("C", "A"), ("B", "C"), ("A", "C")]
    meccsek = []
    for i, (h, v) in enumerate(parok):
        mh, mv = erosseg[h], erosseg[v]
        meccsek.append({"match_id": f"m{i}", "home": h, "away": v, "minta": {
            "home": _ej_minta(2 * mh, mh, float(mh)),
            "away": _ej_minta(2 * mv, mv, float(mv))}})
    p = forecast_backtest(meccsek)
    assert p is not None and p["meccsek"] == len(p["sorok"])
    # Az első előre jelezhető meccs: ahol már mindkét csapatnak két
    # korábbi meccse van (A: m0, m2; C: m1, m2 → m3).
    assert p["sorok"][0]["match_id"] == "m3"
    elso = match_forecast(
        [(meccsek[0]["minta"]["home"], meccsek[0]["minta"]["away"]),
         (meccsek[2]["minta"]["away"], meccsek[2]["minta"]["home"])],
        [(meccsek[1]["minta"]["away"], meccsek[1]["minta"]["home"]),
         (meccsek[2]["minta"]["home"], meccsek[2]["minta"]["away"])])
    assert (p["sorok"][0]["vart_home"], p["sorok"][0]["vart_away"]) == (
        elso["home_goals"], elso["away_goals"])
    # Az erősebb csapat mindig nyer, a modell eltalálja.
    assert p["dontott"] == p["meccsek"] and p["modell_talalat"] == p["meccsek"]
    hiba = sum(abs((r["vart_home"] - r["vart_away"])
                   - (r["home_goals"] - r["away_goals"]))
               for r in p["sorok"]) / len(p["sorok"])
    assert p["modell_hiba"] == round(hiba, 2)
    assert forecast_backtest(meccsek[:ELOREJELZES_PROBA_MIN + 2]) is None
    assert forecast_rows_summary(p["sorok"], "nincs") is None
    a_sorai = [r for r in p["sorok"] if "A" in (r["home"], r["away"])]
    if len(a_sorai) >= ELOREJELZES_PROBA_MIN:
        assert forecast_rows_summary(p["sorok"], "A")["meccsek"] == len(a_sorai)

    alap = {"meccsek": 14, "dontott": 12, "modell_talalat": 8,
            "naiv_talalat": 6, "modell_hiba": 3.1, "naiv_hiba": 4.0}
    assert forecast_backtest_text({**alap, "javulas_pct": 22.5}) == (
        "a modell 12 eldőlt meccsből 8 győztest talált el (a formáé: 6); "
        "a gólkülönbség átlagos hibája 3,1 gól (a formáé 4,0; 14 előre "
        "jelzett meccs) — a modell 22%-kal pontosabb a formánál")
    assert forecast_backtest_text({**alap, "javulas_pct": -9.0}).endswith(
        "a modell 9%-kal pontatlanabb a formánál")
    assert forecast_backtest_text(
        {**alap, "dontott": 0, "javulas_pct": 1.0}) == (
        "a gólkülönbség átlagos hibája 3,1 gól (a formáé 4,0; 14 előre "
        "jelzett meccs) — a modell nagyjából olyan pontos, mint a forma")
    assert forecast_backtest_text(None) is None


def test_az_elo_esely_a_meccs_elotti_varakozasbol_es_az_allasbol():
    """in_play_odds: döntetlen várakozásnál (25–25) a 30. percben 14–10
    a hazai nagy favorit, a 0. percben 0–0 a két csapat egyforma; a
    hátralévő ütem a várakozás és az addigi gólok összevonása; a "várt"
    a perc-arányos várakozás. live_forecast_alerts: a percekben az
    addigi kockák állása és a mondat; előrejelzés nélkül üres."""
    import handball.pipeline.play_simulation as ps
    from handball.pipeline.event_detection import EventType, detect_shots
    from handball.pipeline.play_simulation import (in_play_odds,
                                                   live_forecast_alerts)
    from handball.sim.match_simulator import simulate_ground_truth

    f = {"home_goals": 25.0, "away_goals": 25.0}
    o = in_play_odds(f, 30, 14, 10)
    assert o["p_home"] > 0.8 > o["p_away"]
    assert abs(o["p_home"] + o["p_draw"] + o["p_away"] - 1.0) < 0.002
    assert (o["vart_home"], o["elteres_home"], o["elteres_away"]) == (
        12.5, 1.5, -2.5)
    z = in_play_odds(f, 0, 0, 0)
    assert z["p_home"] == z["p_away"]
    # A hátralévő 30 perc várt gólja: (25 + 14) / 90 × 30 = 13 a
    # hazainál, (25 + 10) / 90 × 30 ≈ 11,7 a vendégnél → a hazai
    # végső várt előnye 4 + 1,3.
    import math
    mu, sd = 4 + (39 - 35) / 90 * 30, math.sqrt(74 / 90 * 30)
    vart = 0.5 * (1 + math.erf((mu - 0.5) / sd / math.sqrt(2)))
    assert o["p_home"] == round(vart, 3)

    m = simulate_ground_truth(duration_s=150, fps=25.0, seed=2,
                              shots_per_min=8)
    import pytest
    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(ps, "LIVE_AJANLO_PERCEK", (1, 2, 30))
        ki = live_forecast_alerts(m, f)["alerts"]
    finally:
        mp.undo()
    assert [a["perc"] for a in ki] == [1, 2]      # a 30. perc még nem jött el
    a = ki[1]
    eddig = [fr for fr in m.frames if fr.t <= a["t"]]
    from handball.models.tracking import Match
    golok = [e for e in detect_shots(Match(meta=m.meta, frames=eddig))
             if e.type == EventType.GOAL]
    assert a["home_goals"] == sum(1 for e in golok if e.team.value == "home")
    assert a["text"].startswith(
        f"Élő esély (2. perc, {a['home_goals']}–{a['away_goals']}): "
        f"{m.meta.home_team} ")
    assert "a meccs előtti várakozás 25–25" in a["text"]
    if abs(a["elteres_home"]) >= ps.ELO_ELTERES_GOL >= abs(a["elteres_away"]):
        assert "góllal a várt" in a["text"]
    assert live_forecast_alerts(m, None) == {"alerts": []}


def test_a_varhato_golszerzok_a_lovo_es_a_kapus_mintabol():
    """scorer_forecast: a lövő meccsenkénti lövései (csak ahol lőtt) ×
    xG / lövés × a tanult szorzója × a szemközti kapus szorzója a
    sávban; az egy meccsen lőtt lövő kimarad; csökkenő sorrend; a mondat
    a legveszélyesebb okával."""
    from handball.pipeline.play_simulation import (_kapus_szorzo,
                                                   _lovo_mintak_osszege,
                                                   _lovo_szorzo,
                                                   scorer_forecast,
                                                   scorer_forecast_text)

    lovo = [{"7": {"far": [4, 2, 1.2]}, "10": {"close": [2, 1, 1.0]},
             "3": {"mid": [3, 1, 1.2]}},
            {"7": {"far": [4, 2, 1.2]}, "10": {"close": [2, 1, 1.0]}},
            {"10": {"close": [2, 1, 1.0]}}]
    kapus = [{"far": [10, 5]}, {"far": [10, 5]}]
    sorok = scorer_forecast(lovo, kapus)
    assert [r["mez"] for r in sorok] == [7, 10]      # a 3-as egy meccsen lőtt
    ls = _lovo_szorzo(_lovo_mintak_osszege(lovo))
    ks = _kapus_szorzo({"far": [20, 10]})
    hetes = sorok[0]
    assert hetes["meccsek"] == 2 and hetes["vart_loves"] == 4.0
    assert hetes["fo_sav"] == "far"
    assert hetes["vart_gol"] == round(4 * 0.3 * ls[7]["far"] * ks["far"], 1)
    assert (hetes["szorzo"], hetes["kapus_szorzo"]) == (ls[7]["far"],
                                                         ks["far"])
    tizes = sorok[1]
    assert tizes["meccsek"] == 3 and tizes["vart_loves"] == 2.0
    assert tizes["kapus_szorzo"] == 1.0         # közelről nincs kapus-minta
    szoveg = scorer_forecast_text(sorok)
    assert szoveg.startswith("a 7-es " + f"{hetes['vart_gol']:.1f}".replace(
        ".", ",") + " gól (főleg távolról: ")
    assert "a szemközti kapus ott" in szoveg
    assert szoveg.endswith(", a 10-es " + f"{tizes['vart_gol']:.1f}".replace(
        ".", ",") + " gól")
    assert scorer_forecast([], kapus) == [] and scorer_forecast_text([]) is None


def test_a_kulcsember_gol_erteke_a_csapat_tobbi_lovojehez():
    """A scorer_forecast "ertek" mezője: a lövő várható gólja mínusz
    ugyanannyi lövés a csapat TÖBBI lövőjének lövésenkénti várható
    góljával; egyetlen lövőnél None. key_player_text: a legnagyobb
    gól-értékű lövő KULCS_MIN_ERTEK-től."""
    from handball.pipeline.play_simulation import (KULCS_MIN_ERTEK,
                                                   key_player_text,
                                                   scorer_forecast)

    # A 7-es helyzetei négyszer annyit érnek lövésenként (0,8 vs 0,2 xG).
    lovo = [{"7": {"close": [5, 4, 4.0]}, "9": {"far": [10, 2, 2.0]}}] * 2
    sorok = {r["mez"]: r for r in scorer_forecast(lovo, [])}
    h, k = sorok[7], sorok[9]
    assert h["ertek"] == round(
        h["vart_gol"] - h["vart_loves"] * k["vart_gol"] / k["vart_loves"], 1)
    assert h["ertek"] > KULCS_MIN_ERTEK > k["ertek"]
    assert key_player_text(list(sorok.values())) == (
        "a 7-es: ugyanannyi lövésből " + f"{h['ertek']:.1f}".replace(".", ",")
        + " góllal többet ér meccsenként, mint a csapat többi lövője")
    egy = scorer_forecast([{"7": {"close": [5, 4, 4.0]}}] * 2, [])
    assert egy[0]["ertek"] is None and key_player_text(egy) is None
    # Egyforma lövők: senki sem kulcsember.
    egyforma = scorer_forecast([{"7": {"mid": [5, 2, 2.0]},
                                 "9": {"mid": [5, 2, 2.0]}}] * 2, [])
    assert key_player_text(egyforma) is None


def test_a_szezon_kulcsemberei_gol_ertek_szerint():
    """season_key_players: a lövők a gól-érték (scorer_forecast "ertek",
    átlagos kapussal) szerint csökkenőben, legfeljebb KULCS_SZEZON_MAX,
    mondattal; egyetlen lövőnél (nincs viszonyítás) üres."""
    from handball.pipeline.play_simulation import (KULCS_SZEZON_MAX,
                                                   scorer_forecast,
                                                   season_key_players)

    lovo = [{"7": {"close": [5, 4, 4.0]}, "9": {"far": [10, 2, 2.0]},
             "4": {"mid": [4, 1, 1.4]}}] * 2
    sorok = season_key_players(lovo)
    ert = {r["mez"]: r["ertek"] for r in scorer_forecast(lovo, [])}
    assert [r["mez"] for r in sorok] == sorted(ert, key=lambda m: -ert[m])
    hetes = sorok[0]
    assert hetes["mez"] == 7 and hetes["verdict"].startswith(
        "a 7-es: +" + f"{hetes['ertek']:.1f}".replace(".", ",")
        + " gól meccsenként ugyanannyi lövésből, mint a csapat többi lövője")
    assert len(season_key_players(lovo * 3)) <= KULCS_SZEZON_MAX
    assert season_key_players([{"7": {"close": [5, 4, 4.0]}}] * 2) == []


def test_mi_lenne_a_kulcsember_nelkul():
    """key_player_absence: a kulcsember (legalább KULCS_MIN_ERTEK
    gól-érték) kiesésekor a csapat várható gólja a gól-értékével kevesebb;
    kulcsember vagy előrejelzés nélkül None."""
    from handball.pipeline.play_simulation import (key_player_absence,
                                                   scorer_forecast)

    lovo = [{"7": {"close": [5, 4, 4.0]}, "9": {"far": [10, 2, 2.0]}}] * 2
    sorok = scorer_forecast(lovo, [])
    hetes = next(r for r in sorok if r["mez"] == 7)
    k = key_player_absence(sorok, 27.0)
    assert (k["mez"], k["vart"]) == (7, 27.0)
    assert k["nelkule"] == round(27.0 - hetes["ertek"], 1)
    assert k["text"] == ("ha a 7-es kiesik, a várható gól 27 helyett "
                         + f"{k['nelkule']:.1f}".replace(".", ","))
    assert key_player_absence(sorok, None) is None
    egyforma = scorer_forecast([{"7": {"mid": [5, 2, 2.0]},
                                 "9": {"mid": [5, 2, 2.0]}}] * 2, [])
    assert key_player_absence(egyforma, 27.0) is None


def test_a_varhato_golszerzok_probaja_idorendben():
    """scorer_forecast_backtest: a lövő várható gólja csak a korábbi
    meccsekből, összevetve a meccsen lőtt góljaival (csak aki lőtt); a
    viszonyítás a lövő korábbi gólátlaga; a csapat-szűrő; kevés párnál
    None."""
    from handball.pipeline.play_simulation import (GOLSZERZO_PROBA_MIN,
                                                   scorer_forecast,
                                                   scorer_forecast_backtest)

    def minta(mez_gol):
        return {"lovo": {str(m): {"mid": [4, g, 1.6]} for m, g in mez_gol},
                "kapus": {"mid": [8, 4]}}

    meccsek = []
    for i in range(12):
        h, v = ("A", "B") if i % 2 == 0 else ("B", "A")
        meccsek.append({"match_id": f"m{i}", "home": h, "away": v,
                        "minta": {"home": minta([(7, 2 + i % 2), (9, 1)]),
                                  "away": minta([(4, 1), (11, 2)])}})
    p = scorer_forecast_backtest(meccsek)
    assert p is not None
    # Párok: minden meccsen és oldalon az a lövő, akinek már van
    # becslése (legalább két korábbi meccsen lőtt) és most is lőtt.
    vart = 0
    lovo_t: dict = {}
    for m in meccsek:
        for side in ("home", "away"):
            nev = m[side]
            kor = lovo_t.get(nev, [])
            becsult = {r["mez"] for r in scorer_forecast(kor, [])}
            vart += sum(1 for mez in m["minta"][side]["lovo"]
                        if int(mez) in becsult)
        for side in ("home", "away"):
            lovo_t.setdefault(m[side], []).append(m["minta"][side]["lovo"])
    assert p["parok"] == vart >= GOLSZERZO_PROBA_MIN
    assert p["verdict"].startswith(f"a lövők várható gólja {vart} lövő ×")
    csak_a = scorer_forecast_backtest(meccsek, "A")
    assert csak_a is None or csak_a["parok"] < p["parok"]
    assert scorer_forecast_backtest(meccsek[:3]) is None


def test_az_elo_esely_probaja_a_vegeredmenyhez():
    """in_play_backtest: a meccs előtti előrejelzés csak a korábbiakból;
    a percekben az addigi gólok (gol_percek) — a felvétel hosszán túli
    perc kimarad; a Brier-hiba a három kimenetre, a viszonyítás a
    semleges várakozás; ha az erősebb csapat mindig nyer, a csapat-modell
    pontosít; a csapat-szűrő; kevés percpontnál None."""
    from handball.pipeline.play_simulation import (ELO_PROBA_MIN,
                                                   in_play_backtest,
                                                   in_play_odds,
                                                   match_forecast)

    erosseg = {"A": 30, "B": 22, "C": 14}

    def oldal(g):
        return {"lovesek": {"close": [2 * g, g, float(g)]}, "golok": g,
                "latott_golok": g,
                "gol_percek": [round(60.0 * (i + 0.5) / g, 2)
                               for i in range(g)]}

    parok = [("A", "B"), ("B", "C"), ("C", "A"), ("A", "C"), ("B", "A"),
             ("C", "B"), ("A", "B"), ("C", "A"), ("B", "C"), ("A", "C")]
    meccsek = [{"match_id": f"m{i}", "home": h, "away": v,
                "minta": {"home": oldal(erosseg[h]), "away": oldal(erosseg[v]),
                          "perc_hossz": 60.0 if i != 3 else 40.0}}
               for i, (h, v) in enumerate(parok)]
    p = in_play_backtest(meccsek)
    assert p is not None
    # m3-tól jósolható minden meccs; az m3 felvétele 40 perces → csak a
    # 15. és a 30. perc számít.
    assert p["meccsek"] == 7 and p["pontok"] == 7 * 3 - 1
    assert p["modell_brier"] < p["semleges_brier"]
    assert p["javulas_pct"] > 0
    assert "a csapat-modell" in p["verdict"] and "pontosít" in p["verdict"]
    # Az m3 15. perces pontja kézzel: az előrejelzés az m0–m2-ből.
    tort = {}
    for m in meccsek[:3]:
        mi = m["minta"]
        tort.setdefault(m["home"], []).append((mi["home"], mi["away"]))
        tort.setdefault(m["away"], []).append((mi["away"], mi["home"]))
    f = match_forecast(tort["A"], tort["C"])
    o = in_play_odds(f, 15, sum(1 for x in meccsek[3]["minta"]["home"][
        "gol_percek"] if x <= 15), sum(1 for x in meccsek[3]["minta"][
            "away"]["gol_percek"] if x <= 15))
    assert o["p_home"] > o["p_away"]
    csak_c = in_play_backtest(meccsek, "C")
    assert csak_c is None or csak_c["pontok"] < p["pontok"]
    # Négy meccsből csak az m3 jósolható: 3 percpont < ELO_PROBA_MIN.
    assert 3 < ELO_PROBA_MIN and in_play_backtest(meccsek[:4]) is None


def test_varakozas_es_valosag_a_meccs_utan():
    """forecast_review: az eredmény a várakozáshoz (VISSZA_GOL góltól a
    nagyobb eltérésű csapat), a lövők (VISSZA_LOVO_GOL góltól, a
    legnagyobb eltérés elöl), a fal (ha a fő rendszer más); ha semmi sem
    tér el, "a várakozás szerint"; előrejelzés nélkül csak a lövők és a
    fal."""
    from handball.pipeline.play_simulation import forecast_review

    nevek = {"home": "Hazai", "away": "Vendég"}
    f = {"home_goals": 25.0, "away_goals": 25.0}
    gsz = {"home": [{"mez": 9, "vart_gol": 3.0}, {"mez": 7, "vart_gol": 2.0}],
           "away": [{"mez": 4, "vart_gol": 5.0}]}
    lovo = {"home": {"9": {"far": [8, 6, 2.0]}, "7": {"close": [3, 2, 1.5]}},
            "away": {"4": {"mid": [6, 2, 2.0]}}}
    ved = {"home": None, "away": {"fo": "6-0", "eloszlas": {"6-0": 1.0}}}
    r = forecast_review(nevek, f, {"home": 30, "away": 24}, golszerzok=gsz,
                        lovo_valodi=lovo, vedekezes=ved,
                        formak_valodi={"away": {"5-1": 120, "6-0": 30}})
    assert r["eredmeny"] == {"vart_home": 25.0, "vart_away": 25.0,
                             "home": 30, "away": 24, "elteres_home": 5.0,
                             "elteres_away": -1.0}
    assert r["sorok"][0] == ("Várakozás: Hazai 25–25 Vendég — lett: 30–24 "
                             "(Hazai 5,0 góllal a várt felett)")
    # Egyforma eltérésnél az oldal szerint (determinisztikus).
    assert [(x["team"], x["mez"], x["elteres"]) for x in r["lovok"]] == [
        ("away", 4, -3.0), ("home", 9, 3.0)]
    assert "Hazai: a 9-es 6 gólt lőtt a várt 3,0 helyett" in r["sorok"]
    assert r["vedekezes"] == [{"team": "away", "vart": "6-0", "valodi": "5-1"}]
    assert r["sorok"][-1] == "Vendég 5-1 fallal védekezett a várt 6-0 helyett"
    nyugi = forecast_review(nevek, f, {"home": 26, "away": 24})
    assert nyugi["sorok"][-1] == "A meccs nagyjából a várakozás szerint alakult"
    nincs = forecast_review(nevek, None, {"home": 30, "away": 24},
                            golszerzok=gsz, lovo_valodi=lovo)
    assert nincs["eredmeny"] is None
    assert nincs["sorok"][:2] == [
        "Vendég: a 4-es 2 gólt lőtt a várt 5,0 helyett",
        "Hazai: a 9-es 6 gólt lőtt a várt 3,0 helyett"]


def test_felidei_varakozas_es_valosag():
    """halftime_review: a félidőig (FELIDO_PERC) látott kockák — az
    eredmény és a lövők várakozása a perc-arányos részre; a mondatok a
    félidőre szólnak; a félidő előtt üres."""
    import handball.pipeline.play_simulation as ps
    from handball.models.tracking import Match
    from handball.pipeline.event_detection import EventType, detect_shots
    from handball.pipeline.play_simulation import halftime_review
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=150, fps=25.0, seed=2,
                              shots_per_min=8)
    nevek = {"home": m.meta.home_team, "away": m.meta.away_team}
    f = {"home_goals": 25.0, "away_goals": 25.0}
    import pytest
    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(ps, "FELIDO_PERC", 2)
        r = halftime_review(m, nevek, f)
        mp.setattr(ps, "FELIDO_PERC", 30)       # a meccs nem ér el idáig
        korai = halftime_review(m, nevek, f)
    finally:
        mp.undo()
    hatar = m.frames[0].t + int(round(2 * 60 * m.meta.fps))
    golok = [e for e in detect_shots(Match(meta=m.meta, frames=[
        fr for fr in m.frames if fr.t <= hatar])) if e.type == EventType.GOAL]
    gh = sum(1 for e in golok if e.team.value == "home")
    assert r["eredmeny"]["home"] == gh and r["eredmeny"]["vart_home"] == round(
        25.0 * 2 / ps.ELO_MECCS_PERC, 1)
    assert r["sorok"][0].startswith(
        f"Félidei várakozás: {nevek['home']} ") and " — a félidőben: " in \
        r["sorok"][0]
    assert r["perc"] == 2 and r["t"] == hatar
    assert korai["sorok"] == [] and korai["t"] is None


def test_a_forro_kez_probaja_es_az_elo_napi_forma():
    """hot_hand_backtest: ha az első félidőben forró lövők a másodikban
    is a helyzeteik felett fejeznek be, a napi forma kitart; ha
    visszaállnak, nem; kevés párnál None. shooter_form_sample: a lövők
    félidőnként. live_form_alerts: a modell várakozása felett járó lövő
    a próba ítéletével, lövőnként és irányonként egyszer."""
    import handball.pipeline.play_simulation as ps
    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import (FORMA_MIN_PAR,
                                                   AttackModel,
                                                   _lovesek_mezszammal,
                                                   hot_hand_backtest,
                                                   live_form_alerts,
                                                   shooter_form_sample)
    from handball.pipeline.tactics import TacticsConfig
    from handball.sim.match_simulator import simulate_ground_truth

    forro = {"7": [[5, 4, 2.0], [5, 4, 2.0]]}      # +0,4 / lövés mindkétszer
    hideg = {"9": [[5, 0, 2.0], [5, 0, 2.0]]}      # −0,4 / lövés mindkétszer
    p = hot_hand_backtest([forro, hideg] * FORMA_MIN_PAR)
    assert (p["forro"], p["hideg"]) == (FORMA_MIN_PAR, FORMA_MIN_PAR)
    assert (p["forro_pp"], p["hideg_pp"], p["kulonbseg_pp"]) == (
        40.0, -40.0, 80.0)
    assert p["itelet"] == "kitart" and "a napi forma kitart" in p["verdict"]
    vissza = hot_hand_backtest(
        [{"7": [[5, 4, 2.0], [5, 2, 2.0]]}, {"9": [[5, 0, 2.0], [5, 2, 2.0]]}]
        * FORMA_MIN_PAR)
    assert vissza["itelet"] == "visszaall" and vissza["kulonbseg_pp"] == 0.0
    assert "a modellre" in vissza["verdict"]
    assert hot_hand_backtest([forro, hideg]) is None
    # Kevés lövés egy félidőben: a pár nem számít.
    assert hot_hand_backtest([{"7": [[3, 3, 1.0], [5, 4, 2.0]]}] * 20) is None

    m = simulate_ground_truth(duration_s=300, fps=25.0, seed=2,
                              shots_per_min=8)
    mi = shooter_form_sample(m, Team.HOME)
    lov = list(_lovesek_mezszammal(m, Team.HOME, TacticsConfig()))
    assert sum(v[0][0] + v[1][0] for v in mi.values()) == len(lov)
    # A félidő-határ (itt a felvétel közepe) előtti lövések az elsőben.
    kozep = m.frames[len(m.frames) // 2].t
    assert sum(v[0][0] for v in mi.values()) == sum(
        1 for _mez, sh in lov if sh["t"] < kozep)

    import pytest
    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(ps, "LIVE_AJANLO_PERCEK", (2, 4))
        ki = live_form_alerts(m, tamadas={"home": AttackModel()},
                              proba=vissza)["alerts"]
        nincs = live_form_alerts(m)["alerts"]
    finally:
        mp.undo()
    # A szimulált meccsen minden lövés gól: a hazai lövők forrók — a
    # hazai kispadnak a támadó, a vendégnek a védő szemszögéből.
    tam = [a for a in ki if a["nezopont"] == "tamado"]
    ved = [a for a in ki if a["nezopont"] == "vedo"]
    assert tam and all(a["team"] == "home" and a["irany"] == "forro"
                       for a in tam)
    assert [(a["mez"], a["perc"]) for a in ved] == [
        (a["mez"], a["perc"]) for a in tam]
    assert all(a["team"] == "away" for a in ved)
    assert ved[0]["text"].startswith(
        f"Forró kéz az ellenfélnél ({ved[0]['perc']}. perc): "
        f"{m.meta.home_team} — ")
    assert ved[0]["text"].endswith("ne bontsátok meg miatta a falat")
    ki = tam
    a = ki[0]
    assert a["golok"] - a["vart"] >= ps.FORMA_ELO_GOL
    assert a["text"].startswith(f"Forró kéz ({a['perc']}. perc): "
                                f"{m.meta.home_team} — ")
    assert a["text"].endswith("a könyvtár szerint a napi forma nem tart ki: "
                              "ne építsetek csak rá a hajrában")
    assert len({(x["mez"], x["irany"]) for x in ki}) == len(ki)
    assert nincs and all(x["text"].endswith(
        "a könyvtár még nem dönti el, kitart-e a napi forma") for x in nincs)


def test_a_kapus_napi_formaja_es_az_elo_kapus_forma():
    """keeper_hot_hand_backtest: ha az első félidőben jól védő kapus a
    másodikban is a várt felett véd, a napi forma kitart; ha visszaáll,
    nem; kevés párnál None. keeper_form_sample: a kapusok félidőnként.
    live_keeper_form_alerts: a szimulált meccsen minden lövés gól — a
    vendég kapusa a szokásos szintje alatt (hideg), mindkét kispadnak."""
    import handball.pipeline.play_simulation as ps
    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import (KF_MIN_PAR,
                                                   keeper_form_sample,
                                                   keeper_hot_hand_backtest,
                                                   live_keeper_form_alerts)
    from handball.sim.match_simulator import simulate_ground_truth

    jo = {"1": [[10, 2, 5.0], [10, 2, 5.0]]}       # +0,3 / lövés mindkétszer
    rossz = {"12": [[10, 8, 5.0], [10, 8, 5.0]]}   # −0,3 / lövés mindkétszer
    p = keeper_hot_hand_backtest([jo, rossz] * KF_MIN_PAR)
    assert p["itelet"] == "kitart" and p["kulonbseg_pp"] == 60.0
    assert "érdemes kapust cserélni" in p["verdict"]
    q = keeper_hot_hand_backtest(
        [{"1": [[10, 2, 5.0], [10, 5, 5.0]]}, {"12": [[10, 8, 5.0],
                                                     [10, 5, 5.0]]}]
        * KF_MIN_PAR)
    assert q["itelet"] == "visszaall" and "nem kell kapust cserélni" in \
        q["verdict"]
    assert keeper_hot_hand_backtest([jo, rossz]) is None

    m = simulate_ground_truth(duration_s=300, fps=25.0, seed=2,
                              shots_per_min=8)
    mi = keeper_form_sample(m, Team.AWAY)
    assert mi and all(v[0][1] == v[0][0] and v[1][1] == v[1][0]
                      for v in mi.values())      # minden lövés gól
    import pytest
    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(ps, "LIVE_AJANLO_PERCEK", (2, 4))
        ki = live_keeper_form_alerts(m, proba=q)["alerts"]
    finally:
        mp.undo()
    sajat = [a for a in ki if a["nezopont"] == "sajat"]
    ellen = [a for a in ki if a["nezopont"] == "ellenfel"]
    assert sajat and all(a["team"] == "away" and a["irany"] == "hideg"
                         for a in sajat)
    assert [(a["mez"], a["perc"]) for a in ellen] == [
        (a["mez"], a["perc"]) for a in sajat]
    assert sajat[0]["text"].startswith(
        f"Hideg kapus ({sajat[0]['perc']}. perc): {m.meta.away_team} — ")
    assert sajat[0]["text"].endswith(
        "egy gyenge szakasz miatt nem kell kapust cserélni")
    assert ellen[0]["team"] == "home" and ellen[0]["text"].endswith(
        "ne a kapusra építsetek")
    # Kapusonként és irányonként egyszer.
    assert len({(a["mez"], a["nezopont"]) for a in ki}) == len(ki)


def test_az_idokeres_probaja_a_sorozat_ellen_es_az_elo_tanacs():
    """_sorozat_helyzetek: a 3. válasz nélküli gólnál egy helyzet; az
    időkérés csak a sorozatot kapótól, a következő gól előtt és
    IDO_ABLAK_S-en belül számít. timeout_run_backtest: ha időkérés után a
    sorozatot kapó szerez, "megtori"; ha nem jobb, "nem_tori"; kevés
    helyzetnél None; a `csapat` szűr. live_timeout_alerts: a szimulált
    meccsen a 3. hazai gólnál mindkét kispadnak, a próba szerinti
    tanáccsal."""
    from handball.pipeline.play_simulation import (IDO_ABLAK_S,
                                                   IDO_MIN_ESET,
                                                   _sorozat_helyzetek,
                                                   live_timeout_alerts,
                                                   timeout_run_backtest)
    from handball.sim.match_simulator import simulate_ground_truth

    gol3 = [[1.0, "home"], [2.0, "home"], [3.0, "home"]]
    assert _sorozat_helyzetek({"golok": gol3 + [[5.0, "away"]],
                               "idokeresek": [[3.5, "away"]]}) == [
        (3.0, "home", "away", True)]
    kesoi = 3.0 + IDO_ABLAK_S / 60.0 + 0.5
    for ido in ([[kesoi, "away"]],      # túl későn
                [[3.5, "home"]],        # a sorozatot futó kérte
                [[2.5, "away"]],        # a sorozat-gól előtt
                [[5.5, "away"]]):       # a következő gól után
        assert _sorozat_helyzetek({"golok": gol3 + [[9.0, "away"]],
                                   "idokeresek": ido})[0][3] is False
    # A meccs végéig gól nélkül: a következő gól None; két gól: nincs helyzet.
    assert _sorozat_helyzetek({"golok": gol3, "idokeresek": []}) == [
        (3.0, "home", None, False)]
    assert _sorozat_helyzetek({"golok": gol3[:2], "idokeresek": []}) == []

    def meccs(kert, tores, home="A", away="B"):
        return {"home": home, "away": away, "minta": {
            "golok": gol3 + [[4.0, "away" if tores else "home"]],
            "idokeresek": [[3.2, "away"]] if kert else []}}

    jo = ([meccs(True, True)] * IDO_MIN_ESET
          + [meccs(False, False)] * IDO_MIN_ESET)
    p = timeout_run_backtest(jo)
    assert p["itelet"] == "megtori" and p["kulonbseg_pp"] == 100.0
    assert p["kert"] == p["kert_tores"] == IDO_MIN_ESET
    assert p["verdict"].endswith("megtöri a sorozatot: kérjetek időt")
    q = timeout_run_backtest([meccs(True, False)] * IDO_MIN_ESET
                             + [meccs(False, True)] * IDO_MIN_ESET)
    assert q["itelet"] == "nem_tori" and "váltással" in q["verdict"]
    assert timeout_run_backtest(jo[1:]) is None
    # A csapat-szűrő a sorozatot KAPÓ csapatra: a "B" helyzetei igen, az
    # "A"-éi nincsenek.
    assert timeout_run_backtest(jo, "B") == p
    assert timeout_run_backtest(jo, "A") is None

    m = simulate_ground_truth(duration_s=300, fps=25.0, seed=2,
                              shots_per_min=8)
    ki = live_timeout_alerts(m)["alerts"]
    assert [a["nezopont"] for a in ki] == ["kapo", "futo"]
    assert ki[0]["team"] == "away" and ki[1]["team"] == "home"
    assert ki[0]["allas"] == [3, 0] and ki[0]["hossz"] == 3
    assert ki[0]["text"].startswith(
        f"Sorozat ellenetek ({ki[0]['perc']}. perc, 3–0): "
        f"{m.meta.home_team} 3-0-s sorozata — ")
    assert ki[0]["text"].endswith("megtöri-e az időkérés a sorozatot")
    k2 = live_timeout_alerts(m, proba=p)["alerts"]
    assert k2[0]["text"].endswith("(időkérés nélkül 0%): kérjetek időt")
    assert "készüljetek az utána jövő figurájukra" in k2[1]["text"]
    k3 = live_timeout_alerts(m, proba=q)["alerts"]
    assert "váltással (védekezés, csere) együtt kérjétek" in k3[0]["text"]
    assert k3[1]["text"].endswith("tartsátok a tempót")


def test_az_idokeres_jegyzet(monkeypatch):
    """timeout_brief: elöl az utolsó öt perc állása, a kérő elleni
    sorozat a próba ítéletével (a sorozatot futó kérésénél nincs ilyen
    sor), aztán a várakozás "eddig"; a meccs vége után üres.
    live_timeout_briefs: a felismert időkérés percében, a kérővel."""
    import handball.pipeline.stoppages as stp
    from handball.pipeline.play_simulation import (live_timeout_briefs,
                                                   timeout_brief)
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=300, fps=25.0, seed=2,
                              shots_per_min=8)
    nevek = {"home": m.meta.home_team, "away": m.meta.away_team}
    f = {"home_goals": 30.0, "away_goals": 30.0}
    pr = {"verdict": "az időkérés megtöri a sorozatot: kérjetek időt"}
    b = timeout_brief(m, 2.0, nevek, f, kero="away", idokeres_proba=pr)
    assert b["ora"] == "02:00" and b["kero"] == "away"
    gh = b["eredmeny"]["home"]
    assert gh >= 3 and b["eredmeny"]["away"] == 0
    assert b["sorok"][0] == (f"Az utolsó 5 percben: {nevek['home']} "
                             f"{gh}–0 {nevek['away']}")
    assert b["sorok"][1] == (f"{nevek['home']} {gh}-0-s sorozatban van — "
                             f"{pr['verdict']}")
    assert b["sorok"][2].startswith(f"Várakozás eddig: {nevek['home']} 1–1 "
                                    f"{nevek['away']} — eddig: {gh}–0")
    # A sorozatot futó kér időt: nincs sorozat-sor; próba nélkül a sor
    # ítélet nélkül áll.
    assert len(timeout_brief(m, 2.0, nevek, f, kero="home")["sorok"]) == 2
    assert timeout_brief(m, 2.0, nevek, None, kero="away")["sorok"] == [
        b["sorok"][0], f"{nevek['home']} {gh}-0-s sorozatban van"]
    assert timeout_brief(m, 9.0, nevek, f)["sorok"] == []
    # A felismert időkérésnél (a felismerés helyett itt beadva).
    t0 = m.frames[0].t
    monkeypatch.setattr(stp, "detect_stoppages", lambda match, config=None: [
        {"start_frame": t0 + 3000, "kind": "időkérés", "likely_team": "away"},
        {"start_frame": t0 + 4000, "kind": "hosszú megszakítás",
         "likely_team": "home"}])
    [j] = live_timeout_briefs(m, nevek, f, idokeres_proba=pr)["jegyzetek"]
    assert j["ora"] == "02:00" and j["kero"] == "away"
    assert j["sorok"] == b["sorok"]
    assert j["text"] == (f"Időkérés-jegyzet (02:00, {nevek['away']} kér "
                         f"időt): " + "; ".join(b["sorok"]))


def test_a_kapus_valasztas_probaja():
    """keeper_choice_backtest: a korábbi meccsekből javasolt kapus (a
    lövők szerint) a meccsen kevesebbet kapott-e a másiknál; a sima
    szezon-mérleg a viszonyítás; a csapat-szűrő; kevés mérhető
    választásnál None; a meccsen kevés lövéses kapus kimarad."""
    from handball.pipeline.play_simulation import (KV_PROBA_MIN,
                                                   keeper_choice_backtest)

    # Az 1-es távolról jó, közelről rossz; a 12-es közelről és középről
    # jobb, és a sima mérlege sokkal jobb (45/60 védés a 12/30 ellen) —
    # az ellenfél távolról lő, ezért a lövők szerint az 1-es a javaslat,
    # a sima mérleg szerint végig a 12-es.
    korabbi = {"1": {"far": [10, 6], "mid": [10, 4], "close": [10, 2]},
               "12": {"far": [10, 2], "mid": [20, 16], "close": [30, 27]}}
    egyforma = {"1": {"far": [10, 6], "mid": [10, 4], "close": [10, 2]},
                "12": {"far": [10, 2], "mid": [10, 4], "close": [10, 6]}}
    lovok = {"9": {"far": [12, 5, 3.0]}, "7": {"far": [8, 3, 2.0],
                                               "mid": [4, 2, 1.6]}}
    jo = {"1": {"far": [8, 5], "mid": [2, 1]}, "12": {"far": [6, 2],
                                                        "mid": [2, 0]}}
    # A "rossz" meccsen az 1-es középről kap sokat (távolról nem — a
    # javaslat marad), a 12-es összességében kevesebbet kap.
    rossz = {"1": {"far": [5, 4], "mid": [5, 0]}, "12": {"far": [5, 1],
                                                           "mid": [3, 3]}}
    keves = {"1": {"far": [8, 5]}, "12": {"far": [3, 1]}}

    def meccs(i, kapusok):
        return {"match_id": f"m{i}", "home": "A", "away": "B",
                "minta": {"home": {"lovo": {}, "kapusok": kapusok},
                          "away": {"lovo": lovok, "kapusok": {}}}}

    ms = [meccs(0, korabbi)] + [meccs(i, jo) for i in range(1, 7)]
    p = keeper_choice_backtest(ms)
    assert (p["meccsek"], p["igazolt"], p["itelet"]) == (6, 6, "igazolt")
    assert p["sorok"][0] == {
        "match_id": "m1", "team": "A", "javasolt": 1, "masik": 12,
        "javasolt_pct": 40.0, "masik_pct": 75.0, "elteres_pp": 35.0,
        "igazolt": True, "naiv": 12, "naiv_igazolt": False}
    assert (p["naiv_meccsek"], p["naiv_igazolt"]) == (6, 0)
    assert p["verdict"] == (
        "a meccs előtti kapus-választás 6 meccsből 6 alkalommal igazolódott "
        "(a javasolt kapus lövésenként átlag +35,0 százalékponttal kevesebb "
        "gólt kapott a másiknál; a sima szezon-mérleg szerinti választás 6 "
        "meccsből 0 alkalommal) — a lövők szerinti kapus-választásra lehet "
        "építeni")
    # Egyforma sima mérlegnél az első meccsen nincs naiv tipp, utána a
    # sima mérleg is az 1-est mondja — ugyanannyit tud: "egyenlo".
    e = keeper_choice_backtest([meccs(0, egyforma)]
                               + [meccs(i, jo) for i in range(1, 7)])
    assert (e["igazolt"], e["naiv_meccsek"], e["naiv_igazolt"],
            e["itelet"]) == (6, 5, 5, "egyenlo")
    assert e["sorok"][0]["naiv"] is None
    assert e["verdict"].endswith("a szokásos kapus is jó")
    # Ha a javasolt kapus többet kap, nem igazolódik.
    q = keeper_choice_backtest([meccs(0, korabbi)]
                               + [meccs(i, rossz) for i in range(1, 7)])
    assert q["igazolt"] == 0 and q["itelet"] == "nem"
    assert q["verdict"].endswith("a kapus-kérdést a napi forma döntse el")
    # Kevés lövéses kapus a meccsen: a választás nem mérhető → None.
    assert keeper_choice_backtest([meccs(0, korabbi)]
                                  + [meccs(i, keves) for i in range(1, 7)]) \
        is None
    assert keeper_choice_backtest(ms[:KV_PROBA_MIN]) is None
    # A csapat-szűrő: a "B" csapatnak nincs kapus-választása.
    assert keeper_choice_backtest(ms, "A") == p
    assert keeper_choice_backtest(ms, "B") is None


def test_a_hetes_dobo_valasztas_es_probaja(monkeypatch):
    """seven_taker_sample: a hetesek dobónként a mezszámmal (a kimenetek
    beadva); seven_taker_choice: simított arány, kevés hetesnél None;
    seven_taker_backtest: a javasolt dobó a többiekhez és a szokásos
    dobóhoz mérve, igazolt / nem / None, csapat-szűrő;
    live_seven_taker_alerts: a hetes pillanatában a dobó kispadjának."""
    import handball.pipeline.rules as rules
    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import (HETES_MIN_DOBAS,
                                                   live_seven_taker_alerts,
                                                   seven_taker_backtest,
                                                   seven_taker_choice,
                                                   seven_taker_sample)
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=120, fps=25.0, seed=1,
                              shots_per_min=8)
    mezek = sorted({p.track_id: p.jersey_number for f in m.frames
                    for p in f.players if p.team == Team.HOME
                    and p.jersey_number is not None}.items())
    (pid1, mez1), (pid2, mez2) = mezek[0], mezek[1]
    t0 = m.frames[0].t
    monkeypatch.setattr(rules, "seven_meter_outcomes", lambda match, config=None: [
        {"t": t0 + 100, "team": "home", "outcome": "gól", "shooter_id": pid1},
        {"t": t0 + 400, "team": "home", "outcome": "védés", "shooter_id": pid1},
        {"t": t0 + 700, "team": "home", "outcome": "gól", "shooter_id": pid2},
        {"t": t0 + 900, "team": "home", "outcome": "ismeretlen",
         "shooter_id": pid2},
        {"t": t0 + 950, "team": "home", "outcome": "gól", "shooter_id": None},
        {"t": t0 + 990, "team": "away", "outcome": "gól", "shooter_id": pid1}])
    assert seven_taker_sample(m, Team.HOME) == {str(mez1): [2, 1],
                                                str(mez2): [1, 1]}
    # A vendég hetese a rekord csapata szerint számít (a dobó mezszáma a
    # kockákból).
    assert seven_taker_sample(m, Team.AWAY) == {str(mez1): [1, 1]}

    mintak = [{"9": [6, 5], "7": [4, 2]}, {"9": [5, 4], "7": [3, 3],
                                            "4": [2, 0]}]
    kc = seven_taker_choice(mintak)
    assert (kc["mez"], kc["dobas"], kc["gol"], kc["masik"]["mez"]) == \
        (9, 11, 9, 7)
    assert kc["verdict"] == ("a hetest a 9-es dobja (9/11 a könyvtárban, "
                             "82%); a második a 7-es (5/7)")
    assert [r["mez"] for r in kc["dobok"]] == [9, 7]       # a 4-es: 2 < 3
    assert seven_taker_choice([{"9": [HETES_MIN_DOBAS - 1, 1]}]) is None
    assert seven_taker_choice([]) is None

    def meccs(i, most, home="A"):
        return {"match_id": f"m{i}", "home": home, "away": "B",
                "minta": {"home": most, "away": {}}}

    jo = [meccs(0, mintak[0]), meccs(1, mintak[1])] + [
        meccs(i, {"9": [2, 2], "7": [1, 0]}) for i in range(2, 9)]
    p = seven_taker_backtest(jo)
    assert (p["meccsek"], p["javasolt"], p["tobbi"], p["itelet"]) == \
        (8, [19, 18], [12, 3], "igazolt")
    assert p["sorok"][0] == {"match_id": "m1", "team": "A", "javasolt": 9,
                             "javasolt_dobas": 5, "javasolt_gol": 4,
                             "tobbi_dobas": 5, "tobbi_gol": 3, "szokasos": 9}
    assert p["verdict"] == (
        "a könyvtár szerinti hetes-dobó 8 meccsen 18/19 hetest lőtt be (95%), "
        "a többiek 3/12 (25%); a szokásos dobó 18/19 (95%) — a hetes-dobó "
        "választásra lehet építeni")
    # Nagy múlttal a 9-es marad a javaslat, de a meccseken kihagy, a 7-es
    # belövi: a választás nem igazolódik (hat meccs után a modell már
    # váltana — a próba csak az addigiakat nézi).
    rossz = [meccs(0, {"9": [30, 27], "7": [20, 12]})] + [
        meccs(i, {"9": [2, 0], "7": [1, 1]}) for i in range(1, 6)]
    q = seven_taker_backtest(rossz)
    assert (q["javasolt"], q["tobbi"], q["itelet"]) == ([10, 0], [5, 5], "nem")
    assert all(r["javasolt"] == 9 for r in q["sorok"])
    assert q["verdict"].endswith("a hetest a napi forma döntse el")
    assert seven_taker_backtest(jo[:4]) is None       # 9 hetes < 10
    assert seven_taker_backtest(jo, "A") == p
    assert seven_taker_backtest(jo, "B") is None

    monkeypatch.setattr(rules, "detect_seven_meters", lambda match, config=None: [
        {"t": t0 + 25 * 70, "team": "home", "goal_x": 40.0},
        {"t": t0 + 25 * 100, "team": "away", "goal_x": 0.0}])
    ki = live_seven_taker_alerts(m, {"home": kc})["alerts"]
    assert len(ki) == 1 and (ki[0]["perc"], ki[0]["team"], ki[0]["mez"]) == \
        (2, "home", 9)
    assert ki[0]["text"] == f"Hetes (2. perc): {m.meta.home_team} — " + \
        kc["verdict"]
    assert live_seven_taker_alerts(m, None) == {"alerts": []}


def test_a_hetes_irany_profilja_es_probaja(monkeypatch):
    """seven_direction_sample: a hetesek irány szerint dobónként (az
    irány nélküli kimarad); _fo_irany: kevés hetes vagy nem domináns →
    None, holtversenyben bal; seven_direction_profile: dobónként és a
    csapatra; seven_direction_backtest: jósolható / nem / None, a csapat
    fő iránya, csapat-szűrő; live_seven_direction_alerts: a védekező
    kispadnak."""
    import handball.pipeline.rules as rules
    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import (
        _fo_irany, live_seven_direction_alerts, seven_direction_backtest,
        seven_direction_profile, seven_direction_sample)
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=120, fps=25.0, seed=1,
                              shots_per_min=8)
    mezek = sorted({p.track_id: p.jersey_number for f in m.frames
                    for p in f.players if p.team == Team.HOME
                    and p.jersey_number is not None}.items())
    (pid1, mez1), (pid2, mez2) = mezek[0], mezek[1]
    t0 = m.frames[0].t
    monkeypatch.setattr(rules, "seven_meter_outcomes", lambda match, config=None: [
        {"t": t0 + 100, "team": "home", "outcome": "gól", "shooter_id": pid1,
         "irany": "jobb"},
        {"t": t0 + 400, "team": "home", "outcome": "védés", "shooter_id": pid1,
         "irany": "jobb"},
        {"t": t0 + 700, "team": "home", "outcome": "gól", "shooter_id": pid2,
         "irany": "bal"},
        {"t": t0 + 900, "team": "home", "outcome": "gól", "shooter_id": pid2,
         "irany": None},
        {"t": t0 + 950, "team": "home", "outcome": "gól", "shooter_id": None,
         "irany": "bal"}])
    assert seven_direction_sample(m, Team.HOME) == {
        str(mez1): {"bal": 0, "közép": 0, "jobb": 2},
        str(mez2): {"bal": 1, "közép": 0, "jobb": 0}}
    assert seven_direction_sample(m, Team.AWAY) == {}

    assert _fo_irany({"bal": 2, "közép": 0, "jobb": 2}) == ("bal", 4, 0.5)
    assert _fo_irany({"bal": 1, "közép": 1, "jobb": 1}) is None
    assert _fo_irany({"bal": 2, "közép": 0, "jobb": 0}) is None
    assert _fo_irany({"bal": 2, "közép": 0, "jobb": 0}, 2) == ("bal", 2, 1.0)

    mintak = [{"9": {"bal": 1, "közép": 0, "jobb": 4},
               "7": {"bal": 2, "közép": 1, "jobb": 0}},
              {"9": {"bal": 1, "közép": 1, "jobb": 3},
               "4": {"bal": 1, "közép": 0, "jobb": 1}}]
    pr = seven_direction_profile(mintak)
    assert pr["verdict"] == ("hetes-irányaik (a dobó felől nézve): a 9-es "
                             "70% jobbra (7/10), a 7-es 67% balra (2/3)")
    assert pr["csapat"] == {"irany": "jobb", "dobas": 15, "arany_pct": 53.3}
    assert [r["mez"] for r in pr["dobok"]] == [9, 7]      # a 4-es: 2 hetes
    cs = seven_direction_profile([{"9": {"bal": 0, "közép": 0, "jobb": 2},
                                   "7": {"bal": 0, "közép": 0, "jobb": 2}}])
    assert cs["dobok"] == [] and cs["verdict"] == (
        "hetes-irányuk (a dobó felől nézve): a csapat 100% jobbra "
        "(4 hetesből)")
    assert seven_direction_profile([]) is None

    def meccs(i, most):
        return {"match_id": f"m{i}", "home": "A", "away": "B",
                "minta": {"home": most, "away": {}}}

    jo = [meccs(0, mintak[0]), meccs(1, mintak[1])] + [
        meccs(i, {"9": {"bal": 0, "közép": 0, "jobb": 2},
                  "7": {"bal": 1, "közép": 0, "jobb": 0}}) for i in range(2, 7)]
    p = seven_direction_backtest(jo)
    assert (p["hetesek"], p["talalt"], p["talalat_pct"], p["csapat_pct"],
            p["itelet"]) == (20, 18, 90.0, 65.0, "josolhato")
    assert p["sorok"][0] == {"match_id": "m1", "team": "A", "mez": 9,
                             "josolt": "jobb", "hetesek": 5, "talalt": 3,
                             "csapat_irany": "jobb", "csapat_talalt": 3}
    assert p["verdict"] == (
        "a dobók fő iránya 20 hetesből 18 alkalommal jött be (90%; a csapat "
        "fő iránya: 65%; véletlen: 33%) — a kapus készülhet a dobó fő "
        "irányára")
    # A 9-es a könyvtárban jobbra lő, a meccseken balra: nem jósolható.
    rossz = [meccs(0, {"9": {"bal": 2, "közép": 1, "jobb": 17}})] + [
        meccs(i, {"9": {"bal": 3, "közép": 0, "jobb": 0}}) for i in range(1, 5)]
    q = seven_direction_backtest(rossz)
    assert (q["hetesek"], q["talalt"], q["itelet"]) == (12, 0, "nem")
    assert q["verdict"].endswith("a kapus a mozdulatra figyeljen, ne a "
                                 "könyvtárra")
    assert seven_direction_backtest(jo[:2]) is None     # 5 hetes < 8
    assert seven_direction_backtest(jo, "A") == p
    assert seven_direction_backtest(jo, "B") is None

    monkeypatch.setattr(rules, "detect_seven_meters", lambda match, config=None: [
        {"t": t0 + 25 * 70, "team": "home", "goal_x": 40.0},
        {"t": t0 + 25 * 100, "team": "away", "goal_x": 0.0}])
    ki = live_seven_direction_alerts(m, {"home": pr})["alerts"]
    assert len(ki) == 1 and (ki[0]["perc"], ki[0]["team"],
                             ki[0]["dobo_team"]) == (2, "away", "home")
    assert ki[0]["text"] == (f"Hetes ellenünk (2. perc): {m.meta.home_team} "
                             f"— {pr['verdict']}")
    assert live_seven_direction_alerts(m, None) == {"alerts": []}


def test_a_pad_dontesei_a_konyvtar_tukreben():
    """decision_review: időkérés a sorozat ellen (kért / kihagyott, a
    próba ítéletével), a hetesek dobói a könyvtár dobójához mérve, a
    kezdő kapus a könyvtár javaslatához mérve, a hideg első félidő utáni
    csere (vagy maradás) a napi forma próbája szerint; üres mintáknál
    üres sorok."""
    from handball.pipeline.play_simulation import decision_review

    nevek = {"home": "Hazai", "away": "Vendég"}
    ido = {"golok": [[1, "away"], [2, "away"], [3, "away"], [5, "home"],
                     [20, "away"], [21, "away"], [22, "away"], [25, "away"]],
           "idokeresek": [[3.5, "home"]]}
    hetes = {"home": {"9": [3, 3], "7": [1, 0]}, "away": {"4": [2, 1]}}
    kf = {"home": {"1": [[10, 7, 4.5], [0, 0, 0.0]],
                   "12": [[0, 0, 0.0], [9, 3, 4.2]]},
          "away": {"16": [[8, 4, 4.0], [9, 5, 4.4]]}}
    r = decision_review(
        nevek, ido, hetes, kf,
        idokeres_proba={"home": {"itelet": "megtori"}},
        hetes_javaslat={"home": {"mez": 9, "gol": 11, "dobas": 13},
                        "away": {"mez": 7, "gol": 5, "dobas": 6}},
        kapus_javaslat={"home": {"kapus_mez": 12, "dontes": True}},
        kapusforma_proba={"home": {"itelet": "kitart"}})
    h, a = r["home"], r["away"]
    assert h["idokeres"] == {"sorozat": 2, "kert": 1, "tores_kert": 1,
                             "tores_nem": 0}
    assert h["hetes"] == {"dobok": [[9, 3, 3], [7, 1, 0]], "konyvtar_dobo": 9}
    assert h["kapus"] == {"kezdo": 1, "masodik": 12, "hideg": True,
                          "csere": True}
    assert h["sorok"] == [
        "Sorozat ellenük 2 alkalommal, időt kértek 1 alkalommal — az "
        "időkérés után 1 alkalommal ők szerezték a következő gólt; időkérés "
        "nélkül 0 alkalommal (1 sorozatból) — a könyvtár szerint az "
        "időkérés megtöri a sorozatot: a kihagyott sorozatnál is érdemes "
        "lett volna időt kérni",
        "Heteseik: a 9-es 3/3, a 7-es 0/1 — a könyvtár dobója (a 9-es) "
        "dobta, de nem mindet",
        "A kapuban az 1-es kezdett (3/10 az első félidőben) — a könyvtár a "
        "12-est javasolta",
        "Hideg első félidő (7 kapott gól a várt 4,5 helyett), a második "
        "félidőben a 12-es állt a kapuban (6/9) — a próba szerint a napi "
        "forma kitart: jó csere"]
    assert a["idokeres"] is None and a["kapus"]["hideg"] is False
    assert a["sorok"] == [
        "Heteseik: a 4-es 1/2 — a könyvtár szerint a 7-es dobná (5/6 a "
        "könyvtárban)",
        "A kapuban a 16-os kezdett (4/8 az első félidőben)"]
    # Hideg félidő után maradt a kapus — a próba szerint helyes; az
    # időkérés próbája "nem_tori"; a könyvtár dobója dobta mindet.
    r2 = decision_review(
        nevek, ido, {"home": {"9": [3, 3]}},
        {"home": {"1": [[10, 7, 4.5], [8, 5, 3.8]]}},
        idokeres_proba={"home": {"itelet": "nem_tori"}},
        hetes_javaslat={"home": {"mez": 9, "gol": 11, "dobas": 13}},
        kapusforma_proba={"home": {"itelet": "visszaall"}})["home"]
    assert r2["sorok"][0].endswith(
        "— a könyvtár szerint az időkérés önmagában nem töri meg a "
        "sorozatot: váltással együtt ér valamit")
    assert r2["sorok"][1] == ("Heteseik: a 9-es 3/3 — a könyvtár dobója "
                              "(a 9-es) dobta")
    assert r2["sorok"][3] == (
        "Hideg első félidő (7 kapott gól a várt 4,5 helyett), az 1-es "
        "maradt (a második félidőben 3/8) — a próba szerint helyes: egy "
        "gyenge félidő miatt nem kell cserélni")
    ures = decision_review(nevek, None, None, None)
    assert ures["home"] == {"sorok": [], "idokeres": None, "hetes": None,
                            "kapus": None, "het_a_hat": None}
    # 7 a 6: a szakaszok mérlege a könyvtár ítéletével; 7 a 6 nélkül
    # nincs sor.
    r3 = decision_review(
        nevek, None, None, None,
        het_a_hat_mintak={"home": {"ablak": 3, "lott": 2, "kapott": 1},
                          "away": {"ablak": 0}},
        het_a_hat_proba={"home": {"itelet": "nem"}})
    assert r3["home"]["het_a_hat"] == {"ablak": 3, "lott": 2, "kapott": 1}
    assert r3["home"]["sorok"] == [
        "7 a 6: 3 szakasz, 2 lőtt gól, 1 kapott üres kapura — a könyvtár "
        "szerint a 7 a 6 többe kerül, mint amennyit hoz"]
    assert r3["away"]["sorok"] == [] and r3["away"]["het_a_hat"] is None
    assert decision_review(nevek, None, None, None, het_a_hat_mintak={
        "home": {"ablak": 1, "lott": 1, "kapott": 0}},
        het_a_hat_proba={"home": {"itelet": "megeri"}})["home"]["sorok"] == [
        "7 a 6: 1 szakasz, 1 lőtt gól, 0 kapott üres kapura — a könyvtár "
        "szerint a 7 a 6 megéri: jó döntés"]


def test_a_dontes_probak_egy_sorban():
    """decision_trust_summary: a hat döntés-próba ítéletének rövid alakja
    a megadott sorrendben; ítélet nélkül None."""
    from handball.pipeline.play_simulation import decision_trust_summary

    assert decision_trust_summary() is None
    assert decision_trust_summary(
        kapus_valasztas={"itelet": "igazolt"}, hetes={"itelet": "nem"},
        hetes_irany={"itelet": "josolhato"}, idokeres={"itelet": "nem_tori"},
        kapus_forma={"itelet": "visszaall"},
        het_a_hat={"itelet": "megeri"}) == (
        "kapus-választás: igazolt; hetes-dobó: a napi forma döntsön; "
        "hetes-irány: jósolható; időkérés: csak váltással ér valamit; "
        "kapus napi formája: nem tart ki; 7 a 6: megéri")
    assert decision_trust_summary(
        kapus_valasztas={"itelet": "egyenlo"}, hetes={"itelet": "igazolt"},
        idokeres={"itelet": "megtori"}, kapus_forma={"itelet": "kitart"},
        het_a_hat={"itelet": "nem"}) == (
        "kapus-választás: a szokásos kapus is jó; hetes-dobó: a könyvtár "
        "dobója jobb; időkérés: megtöri a sorozatot; kapus napi formája: "
        "kitart; 7 a 6: nem éri meg")


def test_megeri_e_a_7_a_6(monkeypatch):
    """seven_six_sample: a 7 a 6 szakaszok és a 6 a 6 támadások mérlege
    (a szimulált meccsen nincs 7 a 6); seven_six_backtest: megéri /
    egyenlő / nem, kevés szakasznál None, csapat-szűrő;
    live_seven_six_alerts: a hajrá perceiben a vesztő csapatnak, a mérleg
    szerinti tanáccsal."""
    import handball.pipeline.play_simulation as ps
    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import (HN_MIN_ABLAK,
                                                   live_seven_six_alerts,
                                                   seven_six_backtest,
                                                   seven_six_sample)
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=300, fps=25.0, seed=2,
                              shots_per_min=8)
    h = seven_six_sample(m, Team.HOME)
    assert h["ablak"] == h["lott"] == h["kapott"] == 0
    assert h["tamadas"] > 0 and h["gol"] > 0
    assert seven_six_sample(m, Team.AWAY)["gol"] == 0

    def meccsek(mi, n=4, home="A"):
        return [{"home": home, "away": "B", "minta": {"home": mi, "away": {}}}
                ] * n

    jo = meccsek({"ablak": 3, "lott": 3, "kapott": 1, "tamadas": 10,
                  "gol": 4})
    p = seven_six_backtest(jo)
    assert (p["ablak"], p["het_netto"], p["hat_hozam"], p["itelet"]) == \
        (12, 0.667, 0.4, "megeri")
    assert p["verdict"] == (
        "a 7 a 6 12 szakaszból 12 gólt hozott és 4 gólt kapott üres kapura — "
        "nettó 0,67 gól szakaszonként, a 6 a 6 támadások 0,40 góljához mérve: "
        "a hátrányos hajrában megéri lehozni a kapust")
    rossz = seven_six_backtest(meccsek({"ablak": 3, "lott": 2, "kapott": 1,
                                        "tamadas": 10, "gol": 4}))
    assert rossz["itelet"] == "nem" and rossz["verdict"].endswith(
        "maradjon a kapus")
    egy = seven_six_backtest(meccsek({"ablak": 3, "lott": 2, "kapott": 1,
                                      "tamadas": 10, "gol": 3}))
    assert egy["itelet"] == "egyenlo"          # 0,33 a 0,30 mellett
    assert seven_six_backtest(meccsek({"ablak": HN_MIN_ABLAK - 1, "lott": 1,
                                       "kapott": 0, "tamadas": 30,
                                       "gol": 9}, n=1)) is None
    assert seven_six_backtest(jo, "A") == p
    assert seven_six_backtest(jo, "B") is None

    # Élőben: a percek a rövid felvételhez, a hátrány-korlát a
    # szimulált (egyoldalú) meccshez igazítva — a vendég vesztésre áll.
    monkeypatch.setattr(ps, "HN_ELO_PERCEK", (2, 4, 9))
    monkeypatch.setattr(ps, "HN_HATRANY_MAX", 1000)
    ki = live_seven_six_alerts(m, p)["alerts"]
    assert [(a["perc"], a["team"]) for a in ki] == [(2, "away"), (4, "away")]
    assert ki[0]["allas"][1] == 0 and ki[0]["hatrany"] == ki[0]["allas"][0]
    assert ki[0]["text"] == (
        f"7 a 6? (2. perc, {ki[0]['allas'][0]}–0): {m.meta.away_team} "
        f"{ki[0]['hatrany']} gól hátrányban — a könyvtár szerint megéri "
        f"lehozni a kapust ({p['verdict']})")
    k2 = live_seven_six_alerts(m)["alerts"]
    assert k2[0]["text"].endswith("a könyvtár még nem dönti el, megéri-e a "
                                  "7 a 6")
    monkeypatch.setattr(ps, "HN_HATRANY_MAX", 3)
    assert live_seven_six_alerts(m, p)["alerts"] == []


def test_a_varhato_vedekezesi_rendszer_es_probaja():
    """defense_system_forecast: a korábbi meccsek védekező kockáinak
    eloszlása és a fő rendszer (két meccstől, VR_MIN_KOCKA kockától);
    a mondat a második rendszerrel; a próba a korábbiakból jósolt fő
    rendszert a meccs valódi fő rendszeréhez méri, a liga addigi
    leggyakoribb rendszere mellé; a csapat-szűrő; kevés meccsnél None."""
    from handball.pipeline.play_simulation import (VR_MIN_KOCKA,
                                                   _rendszer_nevelovel,
                                                   defense_system_backtest,
                                                   defense_system_forecast,
                                                   defense_system_text)

    f = defense_system_forecast([{"6-0": 140, "5-1": 60},
                                 {"6-0": 70, "5-1": 30}])
    assert f == {"fo": "6-0", "eloszlas": {"6-0": 0.7, "5-1": 0.3},
                 "meccsek": 2, "kockak": 300}
    assert defense_system_text(f) == (
        "6-0 (a korábbi védekezésük 70%-a), mellette 5-1 (30%)")
    assert defense_system_forecast([{"6-0": 100}]) is None
    assert defense_system_forecast([{"6-0": 10}, {"5-1": 10}]) is None
    assert VR_MIN_KOCKA > 20
    assert (_rendszer_nevelovel("5-1"), _rendszer_nevelovel("3-2-1")) == (
        "az 5-1", "a 3-2-1")

    def minta(fo):
        return {"formak": {fo: 200, "6-0" if fo != "6-0" else "5-1": 20}}

    meccsek = []
    for i in range(8):
        # A: mindig 5-1; B: mindig 6-0 (a liga leggyakoribbja is ez lesz).
        meccsek.append({"match_id": f"m{i}", "home": "A", "away": "B",
                        "minta": {"home": minta("5-1"),
                                  "away": minta("6-0")}})
    p = defense_system_backtest(meccsek)
    # A 3. meccstől (két korábbi) mindkét oldal jósolható: 6 × 2.
    assert p["meccsek"] == 12 and p["talalat"] == 12
    assert p["liga_talalat"] < p["talalat"]
    assert p["verdict"] == ("a várható fő védekezési rendszer 12 meccsből "
                            f"12 alkalommal jött be (a liga leggyakoribb "
                            f"rendszeréé: {p['liga_talalat']})")
    assert defense_system_backtest(meccsek, "A")["meccsek"] == 6
    assert defense_system_backtest(meccsek[:4]) is None


def test_az_elo_eltero_vedekezes_jelzes():
    """live_defense_system_alerts: a percekben az addigi kockák fő
    rendszere (_tanulas_minta a részmeccsen) — ha eltér a várttól,
    jelzés a VÉDŐ oldalnak, rendszerenként egyszer; ha egyezik, nincs."""
    import handball.pipeline.play_simulation as ps
    from handball.models.tracking import Match, Team
    from handball.pipeline.play_simulation import (_fo_rendszer,
                                                   _tanulas_minta,
                                                   live_defense_system_alerts)
    from handball.pipeline.tactics import TacticsConfig
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=150, fps=25.0, seed=2,
                              shots_per_min=8)
    import pytest
    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(ps, "LIVE_AJANLO_PERCEK", (1, 2))
        hatar = m.frames[0].t + int(round(60 * m.meta.fps))
        resz = Match(meta=m.meta, frames=[f for f in m.frames if f.t <= hatar])
        most = _fo_rendszer(_tanulas_minta(resz, Team.AWAY,
                                           TacticsConfig())["formak"])
        assert most is not None
        mas = "3-3" if most != "3-3" else "6-0"
        ki = live_defense_system_alerts(
            m, {"away": {"fo": mas, "eloszlas": {mas: 1.0}}})["alerts"]
        egyezo = live_defense_system_alerts(
            m, {"away": {"fo": most, "eloszlas": {most: 1.0}}})["alerts"]
    finally:
        mp.undo()
    assert ki and ki[0]["perc"] == 1 and ki[0]["team"] == "away"
    assert ki[0]["most"] == most and ki[0]["vart"] == mas
    assert ki[0]["text"].startswith(
        f"Eltérő védekezés (1. perc): {m.meta.away_team} {most} fallal véd "
        f"a várt {mas} helyett")
    # Ugyanarra a rendszerre csak egyszer szól.
    assert len({a["most"] for a in ki}) == len(ki)
    assert all(a["most"] != most for a in egyezo)


def test_az_elo_esely_zuhanasa_idokerest_javasol():
    """live_forecast_alerts: ha egy csapat győzelmi esélye az előző mérési
    pont (a meccs eleje, illetve az előző perc) óta legalább ELO_ESES_PP
    százalékponttal esett, a mondat időkérést javasol, és az "eses" mező
    megnevezi; ha nem esett, nincs ilyen mondat."""
    import handball.pipeline.play_simulation as ps
    from handball.pipeline.play_simulation import (in_play_odds,
                                                   live_forecast_alerts)
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=150, fps=25.0, seed=2,
                              shots_per_min=8)
    f = {"home_goals": 25.0, "away_goals": 25.0, "p_home": 0.45,
         "p_draw": 0.1, "p_away": 0.45}
    import pytest
    mp = pytest.MonkeyPatch()
    try:
        mp.setattr(ps, "LIVE_AJANLO_PERCEK", (1, 2))
        ki = live_forecast_alerts(m, f)["alerts"]
        # Az előrejelzés esélyei nélkül nincs viszonyítás: nincs zuhanás.
        regi = live_forecast_alerts(
            m, {"home_goals": 25.0, "away_goals": 25.0})["alerts"]
    finally:
        mp.undo()
    # A szimulált meccsen csak a hazai támad és talál: a vendég esélye
    # az első percben zuhan.
    elso = ki[0]
    o = in_play_odds(f, 1, elso["home_goals"], elso["away_goals"])
    assert (f["p_away"] - o["p_away"]) * 100 >= ps.ELO_ESES_PP
    assert elso["eses"]["team"] == "away"
    assert elso["text"].endswith(
        f"{m.meta.away_team} esélye a meccs eleje óta "
        f"{elso['eses']['pp']:.0f} százalékponttal esett: érdemes időt kérni")
    # A második percben már nincs mit esnie.
    assert ki[1]["eses"] is None and "időt kérni" not in ki[1]["text"]
    assert all(a["eses"] is None for a in regi)


def test_az_elorejelzes_meccs_mintaja():
    """match_forecast_sample: oldalanként a látott lövések (xg.match_xg)
    sávonként, az összes felismert gól (a nem látott is) és a látott
    gólok; JSON-barát."""
    import json

    from handball.pipeline.event_detection import EventType, detect_shots
    from handball.pipeline.play_simulation import match_forecast_sample
    from handball.pipeline.xg import match_xg
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=120, fps=25.0, seed=3,
                              shots_per_min=8)
    mi = match_forecast_sample(m)
    assert json.loads(json.dumps(mi)) == mi
    xs = match_xg(m)["shots"]
    for side in ("home", "away"):
        assert sum(v[0] for v in mi[side]["lovesek"].values()) == sum(
            1 for sh in xs if sh["team"] == side)
        assert mi[side]["latott_golok"] == sum(
            1 for sh in xs if sh["team"] == side and sh["outcome"] == "goal")
        assert mi[side]["golok"] == sum(
            1 for e in detect_shots(m) if e.type == EventType.GOAL
            and e.team.value == side)
    assert mi["home"]["lovesek"]
    # A gólok perce időrendben, a felvétel hossza percben.
    for side in ("home", "away"):
        assert len(mi[side]["gol_percek"]) == mi[side]["golok"]
        assert mi[side]["gol_percek"] == sorted(mi[side]["gol_percek"])
    assert mi["perc_hossz"] == round(
        (m.frames[-1].t - m.frames[0].t) / m.meta.fps / 60.0, 2)


def test_a_jatekos_modell_fejlodese_ket_idoszak_kozott():
    """A két időszak tanult szorzói: csak a mindkét időszakban tanult sáv
    és csak FEJLODES_ELTERES feletti változás hír; a lövőnél a nagyobb,
    a kapusnál a kisebb szorzó a javulás; a változás nagysága szerint
    rendezve, legfeljebb FEJLODES_MAX lövő-sor; a mondatok."""
    from handball.pipeline.play_simulation import (FEJLODES_ELTERES,
                                                   FEJLODES_MAX, AttackModel,
                                                   player_model_development)

    assert (FEJLODES_ELTERES, FEJLODES_MAX) == (0.1, 5)
    regi = AttackModel(lovok={7: {"far": 0.9, "close": 1.0},
                              9: {"mid": 1.25}, 10: {"far": 1.1}})
    uj = AttackModel(lovok={7: {"far": 1.2, "close": 1.05},
                            9: {"mid": 1.0}, 11: {"far": 1.3}})
    r = player_model_development(regi, uj, {"far": 1.2, "close": 1.0},
                                 {"far": 0.9, "close": 1.05, "mid": 0.8})
    assert [(x["mez"], x["sav"], x["irany"]) for x in r["lovok"]] == [
        (7, "far", "javul"), (9, "mid", "romlik")]
    assert r["lovo_sorok"] == ["a 7-es távolról 0,9× → 1,2× (javul)",
                               "a 9-es közepes távolságból 1,2× → 1,0× (romlik)"]
    assert [(x["sav"], x["irany"]) for x in r["kapus"]] == [("far", "javul")]
    assert r["kapus_sorok"] == ["a kapus távolról 1,2× → 0,9× annyi gólt "
                                "kap, mint az átlag (javul)"]
    sok_regi = AttackModel(lovok={m: {"far": 0.8} for m in range(1, 9)})
    sok_uj = AttackModel(lovok={m: {"far": 0.8 + 0.05 * m} for m in range(1, 9)})
    sok = player_model_development(sok_regi, sok_uj)
    assert [x["mez"] for x in sok["lovok"]] == [8, 7, 6, 5, 4]
    ures = player_model_development(None, None)
    assert ures == {"lovok": [], "kapus": [], "lovo_sorok": [],
                    "kapus_sorok": []}


def test_a_loves_elosztas_a_kesz_modellbol():
    """Lövés-elosztás a kész modellből: a 7-es közelről többet ér (1,3×),
    mégis kevesebbet lő (25%), a 10-es kevesebbet ér (0,8×) és többet lő
    (75%) → döntés, a motor mondatával; a kapus-szorzó az értékbe
    számít; fordított részesedésnél kiegyensúlyozott; kevés lövésből
    (LE_MIN_LOVES alatt) és egy tanult párosból None."""
    from handball.pipeline.play_simulation import (LE_ELTERES, LE_MIN_LOVES,
                                                   LE_MIN_PAROS, AttackModel,
                                                   _lovo_parosok,
                                                   shot_allocation_from)

    assert (LE_MIN_LOVES, LE_MIN_PAROS, LE_ELTERES) == (10, 2, 0.05)
    tam = AttackModel(lovok={7: {"close": 1.3}, 10: {"close": 0.8}})
    minta = {7: {"close": [3, 3, 1.5]}, "10": {"close": [9, 3, 4.5]}}
    r = shot_allocation_from(tam, {}, minta)
    par = {p["mez"]: p["ertek"] for p in _lovo_parosok(tam, {})}
    assert r["lovesek"] == 12 and r["atlag_pct"] == 50.0 and r["dontes"]
    assert [(s["mez"], s["lovesek"], s["arany_pct"]) for s in r["parosok"]] == [
        (7, 3, 25.0), (10, 9, 75.0)]
    assert (r["tobbet"]["mez"], r["kevesebbet"]["mez"]) == (7, 10)
    sz = {m: f"{v:.2f}".replace(".", ",") for m, v in par.items()}
    assert r["verdict"] == (
        f"többet lőhetne a 7-es közelről ({sz[7]} várható gól lövésenként, "
        f"eddig 3 lövés — 25%), kevesebbet a 10-es közelről ({sz[10]}; 9 "
        "lövés — 75%)")
    # A kapus-szorzó az értékbe számít (közelről 1,2× annyit kap).
    k = shot_allocation_from(tam, {"close": 1.2}, minta)
    assert abs(k["parosok"][0]["ertek"] - par[7] * 1.2) < 0.002
    # Fordított részesedés: a jobb lövő lő többet → nincs döntés.
    forditott = shot_allocation_from(
        tam, {}, {7: {"close": [9, 6, 4.5]}, 10: {"close": [3, 1, 1.5]}})
    assert not forditott["dontes"] and forditott["kevesebbet"] is None
    assert forditott["verdict"] == ("a lövés-elosztás a modell szerint "
                                    "kiegyensúlyozott (12 lövés, 2 tanult "
                                    "páros)")
    assert shot_allocation_from(
        tam, {}, {7: {"close": [3, 3, 1.5]}, 10: {"close": [6, 2, 3.0]}}
    ) is None                                             # 9 lövés < 10
    assert shot_allocation_from(AttackModel(lovok={7: {"close": 1.3}}), {},
                                minta) is None             # egy páros
    assert shot_allocation_from(None, {}, minta) is None


def test_a_loves_elosztas_a_meccsbol_a_felderitesben_es_az_edzestervben(
        monkeypatch):
    """A meccs-szintű réteg a TÁMADÓ oldalról nevez (a hazai lövőinek
    elosztása, a vendégnek nincs lövése → None); a felderítés képe az
    összegzett lövő-mintából, a kulcs és a meccsterv (475 — a lövőik × a
    ti kapusotok sávjai) a motor mondatával; az edzésterv (495) és az
    összefoglaló a hazai oldalon; a valódi láncon (szimulált meccs) a
    réteg a kész modellekből számolt képpel egyezik."""
    import handball.pipeline.play_simulation as ps
    import handball.pipeline.training as tr
    from handball.pipeline.coach_summary import coach_summary
    from handball.pipeline.play_simulation import (AttackModel, _kapus_tanul,
                                                   _lovo_minta,
                                                   shot_allocation,
                                                   shot_allocation_from)
    from handball.pipeline.scouting import (combine_reports, matchup_plan,
                                            scout_team)
    from handball.pipeline.training import training_focus
    from handball.sim.match_simulator import simulate_ground_truth

    valodi = simulate_ground_truth(duration_s=600, fps=25.0, seed=1,
                                   shots_per_min=8, halftime_break_s=30)
    cfg = TacticsConfig()
    va = shot_allocation(valodi)
    assert va["home"] == shot_allocation_from(
        AttackModel.learn(valodi, Team.HOME, cfg),
        _kapus_tanul(valodi, Team.AWAY, cfg),
        _lovo_minta(valodi, Team.HOME, cfg))
    assert va["away"] is None

    # A hazai 7-es: közelről 3 lövés 3 gól (1,5 xG → 1,3×), a 10-es 9
    # lövés 3 gól (4,5 xG → 0,8×); a vendég nem lő.
    monkeypatch.setattr(ps, "_lovo_minta", lambda match, team, config: (
        {7: {"close": [3, 3, 1.5]}, 10: {"close": [9, 3, 4.5]}}
        if team == Team.HOME else {}))
    m = _proba_match()
    le = shot_allocation(m)
    assert le["away"] is None
    p = le["home"]
    assert p["dontes"] and (p["tobbet"]["mez"], p["kevesebbet"]["mez"]) == (7, 10)

    opp = scout_team(m, Team.HOME)
    assert opp.le_kep and opp.le_kep["verdict"] == p["verdict"]
    kulcs = (f"Lövés-elosztásuk: {p['verdict']} — a 7-es közeli lövését "
             "vegyétek el, a 10-es közeli lövése engedhető.")
    assert kulcs in opp.keys_to_game
    own = scout_team(m, Team.AWAY)
    assert own.le_kep is None
    assert not any(k.startswith("Lövés-elosztásuk") for k in own.keys_to_game)
    ketto = combine_reports([opp, opp])
    assert ketto.le_kep["lovesek"] == 24 and ketto.le_kep["dontes"]
    [terv] = [s for s in matchup_plan(own, opp)
              if s.startswith("Lövés-elosztásuk a ti kapusotok ellen:")]
    assert terv.endswith("— a 7-es közeli lövését zárjátok, a 10-es "
                         "közeli lövése engedhető.")
    assert not [s for s in matchup_plan(opp, own)
                if s.startswith("Lövés-elosztásuk a ti kapusotok ellen:")]
    monkeypatch.setattr(tr, "MAX_ITEMS", 10_000)
    cim = "Lövés-elosztás a modell szerint"
    tetel = [i for i in training_focus(m)["home"] if i["title"] == cim]
    assert len(tetel) == 1 and tetel[0]["why"] == p["verdict"]
    assert tetel[0]["area"] == "támadás"
    assert tetel[0]["drill"].startswith("játékrendszer a 7-es közeli lövésére")
    assert not [i for i in training_focus(m)["away"] if i["title"] == cim]
    szoveg = " ".join(s["body"] for s in coach_summary(m)["sections"])
    assert f"lövés-elosztása a modell szerint: {p['verdict']}." in szoveg


def test_a_jatekos_modell_nyers_mintaja_a_learn_many_parja():
    """A meccsenkénti nyers, JSON-barát játékos-modell minta
    (player_model_sample) összegéből (player_models_from_samples)
    ugyanazok a modellek épülnek, mint a learn_many / kapus_many /
    DefenseModel.learn_many útján — JSON-körbejárás után is (a lemezes
    eredmény-tár így tárolja)."""
    import json as _json

    from handball.pipeline.play_simulation import (
        AttackModel, _lovo_sav_minta, kapus_many, player_model_sample,
        player_models_from_samples)
    from handball.sim.match_simulator import simulate_ground_truth

    m1 = simulate_ground_truth(duration_s=600, fps=25.0, seed=1,
                               shots_per_min=8, halftime_break_s=30)
    m2 = simulate_ground_truth(duration_s=600, fps=25.0, seed=2,
                               shots_per_min=8, halftime_break_s=30)
    cfg = TacticsConfig()
    for team in (Team.HOME, Team.AWAY):
        par = [(m1, team), (m2, team)]
        mintak = [_json.loads(_json.dumps(player_model_sample(m, t)))
                  for m, t in par]
        mod = player_models_from_samples(mintak)
        assert mod["tamadas"].lovok == AttackModel.learn_many(par).lovok
        assert mod["kapus"] == kapus_many(par)
        assert mod["vedok"] == DefenseModel.learn_many(par).vedok
        egy = player_models_from_samples(mintak[:1])
        assert egy["tamadas"].lovok == AttackModel.learn(m1, team).lovok
        assert egy["sav"] == {str(k): v for k, v in
                              _lovo_sav_minta(m1, team, cfg).items()}
    assert player_models_from_samples([])["vedok"] == []


def test_a_tanult_lovo_szorzoja_simitott_es_szoritott():
    """A lövő sávonkénti szorzója a gól és az xG hányadosa LOVO_SULY
    képzelt, a sáv átlagos értékű lövésével simítva, a LOVO_SZORZO sávba
    szorítva; LOVO_MIN_LOVES alatti sáv kimarad; a minták meccsek közt
    összeadódnak (a kevés lövéses sáv két meccsből eléri a küszöböt)."""
    from handball.pipeline.play_simulation import (
        LOVO_MIN_LOVES, LOVO_SULY, LOVO_SZORZO_MAX, LOVO_SZORZO_MIN,
        _lovo_mintak_osszege, _lovo_szorzo)

    k = _lovo_szorzo({7: {"far": [10, 8, 3.0], "mid": [10, 2, 5.0],
                          "close": [LOVO_MIN_LOVES - 1, 2, 1.2]},
                      9: {"mid": [10, 5, 5.0]}})
    assert set(k[7]) == {"far", "mid"}
    assert k[7]["far"] == LOVO_SZORZO_MAX     # 8 gól 3 xG-ből: nagyon jó
    assert k[7]["mid"] == LOVO_SZORZO_MIN     # 2 gól 5 xG-ből: gyenge
    assert k[9] == {"mid": 1.0}               # pont annyi, amennyit ér
    atlag = 3.0 / 10
    vart = (4 + LOVO_SULY * atlag) / (3.0 + LOVO_SULY * atlag)
    assert _lovo_szorzo({7: {"far": [10, 4, 3.0]}})[7]["far"] == round(vart, 3)
    fel = {7: {"close": [LOVO_MIN_LOVES - 1, 2, 1.2]}}
    assert _lovo_szorzo(fel) == {}
    assert "close" in _lovo_szorzo(_lovo_mintak_osszege([fel, fel]))[7]


def test_a_tanult_lovok_valodi_lovesekbol_es_a_kiertekelesben():
    """A valódi forrás-láncon (szimulált meccs lövésekkel, mezszámmal →
    match_xg): a lövő csapat lövői szorzót kapnak (mezszám szerint), a
    nem lövő csapaté üres; két meccsből a simítás gyengébb. A kiértékelés
    a helyzetbe érő támadó sávjának szorzójával súlyoz, a feliratok
    kimondják; mezszám nélkül nincs szorzó."""
    from handball.pipeline.play_simulation import (AttackModel,
                                                   lovo_felirat)
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=600, fps=25.0, seed=1,
                              shots_per_min=8, halftime_break_s=30)
    egy = AttackModel.learn(m, Team.HOME)
    assert egy.lovok and all(isinstance(mez, int) for mez in egy.lovok)
    assert all(0.7 <= v <= 1.3 for s in egy.lovok.values() for v in s.values())
    assert AttackModel.learn(m, Team.AWAY).lovok == {}
    ketto = AttackModel.learn_many([(m, Team.HOME), (m, Team.HOME)])
    for mez, savok in egy.lovok.items():
        for sav, v in savok.items():
            assert abs(ketto.lovok[mez][sav] - 1.0) >= abs(v - 1.0) - 1e-9
    assert AttackModel.learn_many([]).lovok == {}

    # Egy szabad, távoli lövőhely: a szorzó egy az egyben a pontszámba megy.
    egy_kocka = Match(MatchMeta(match_id="e", home_team="A", away_team="B",
                                fps=25), [Frame(t=0, players=[
                                    _pl(1, Team.HOME, 28.0, 10.0),
                                    _pl(100, Team.AWAY, 34.0, 3.0)],
                                    ball=Ball(x=28.0, y=10.0, confidence=1.0))])
    alap = evaluate_setplay(egy_kocka)
    tanult = evaluate_setplay(egy_kocka, lovok=[{"far": 1.3}])
    assert abs(tanult["best_shot_value"] - 1.3 * alap["best_shot_value"]) < 1e-9
    assert (alap["lovo_szorzo"], tanult["lovo_szorzo"]) == (1.0, 1.3)
    assert evaluate_setplay(egy_kocka, lovok=[{"close": 1.3}]) == alap
    modell = AttackModel(lovok={7: {"far": 1.3}, 10: {"close": 0.8}})
    assert modell.lovo_szorzo(7, 28.0, 10.0, 40.0) == 1.3
    assert modell.lovo_szorzo(7, 34.5, 10.0, 40.0) == 1.0
    assert modell.lovo_szorzo(None, 28.0, 10.0, 40.0) == 1.0
    assert modell.figura_lovok([None, 7, "x", 10]) == [
        {}, {"far": 1.3}, {}, {"close": 0.8}]
    assert modell.figura_lovok([None, 3]) == []
    assert lovo_felirat(modell) == (
        "a lövők: a 7-es távolról 1,3×, a 10-es közelről 0,8× annyit "
        "lőnek be, mint amennyit a helyzeteik érnek")
    assert lovo_felirat(AttackModel(lovok={7: {"far": 1.3}})).endswith(
        "annyit lő be, mint amennyit a helyzetei érnek")
    assert lovo_felirat(AttackModel(lovok={7: {"far": 1.05}})) == ""
    assert lovo_felirat(None) == ""


def test_a_vedekezesi_proba_a_zaro_lovo_szorzojaval_szamol():
    """Az ő tanult lövőikkel a figurájuk pontszáma a záró lövő sávjának
    szorzójával nő (mindkét fal ellen — az eltérés a falé marad), a
    sor mondja a mezszámát, a mondat megnevezi; lövő-modell nélkül a
    mezszám ismert, a szorzó 1, és nincs záradék."""
    from handball.pipeline.play_simulation import (AttackModel,
                                                   defense_test)

    alap = defense_test(_proba_match(), Team.HOME, DefenseModel())
    f = alap["figurak"][0]
    assert sorted(f["mez"]) == [1, 2, 3]
    assert f["lovo_mez"] in (1, 2, 3) and f["lovo_szorzo"] == 1.0
    assert "lövésével" not in alap["verdict"]
    lovo = AttackModel(lovok={f["lovo_mez"]: {"close": 1.3, "mid": 1.3,
                                              "far": 1.3}})
    tanult = defense_test(_proba_match(), Team.HOME, DefenseModel(),
                          tamadas=lovo)
    g = tanult["figurak"][0]
    assert g["lovo_mez"] == f["lovo_mez"] and g["lovo_szorzo"] == 1.3
    assert abs(g["pont_pct"] - 1.3 * f["pont_pct"]) < 0.2
    assert abs(g["alap_pct"] - 1.3 * f["alap_pct"]) < 0.2
    assert tanult["verdict"].endswith(
        f"lövőhelyzetet teremt, a végén "
        f"{'az' if f['lovo_mez'] == 1 else 'a'} {f['lovo_mez']}-"
        f"{'es' if f['lovo_mez'] != 3 else 'as'} lövésével, aki innen 1,3× "
        "annyit lő be, mint amennyit a helyzet ér")
    # Más lövő szorzója nem számít (nem ő ér helyzetbe).
    masik = [m for m in (1, 2, 3) if m != f["lovo_mez"]][0]
    assert defense_test(_proba_match(), Team.HOME, DefenseModel(),
                        tamadas=AttackModel(lovok={masik: {"far": 0.7}})
                        )["figurak"][0]["pont_pct"] == f["pont_pct"]


def test_a_figura_ajanlo_a_mezszammal_mentett_figurat_a_lovovel_pontozza():
    """A figura-ajánló: a "mez" sorral mentett figura záró lövőjének
    szorzója a pontszámba megy (az alap-fal ellen is), az ajánló mondat
    megnevezi; a mezszám nélküli figura (és a lövő-modell nélküli
    rangsor) változatlan."""
    from handball.pipeline.play_simulation import (AttackModel,
                                                   rank_playbook)

    figura = [[[26, 10], [29, 10], [31.5, 10]], [[26, 4], [26, 4], [26, 4]],
              [[30, 2], [33, 2], [36, 1.5]], [[27, 15], [28, 15], [29, 15]]]
    nelkul = rank_playbook([{"id": "a", "name": "Beúszás", "attackers": figura,
                             "labda": [0, 0, 1]}], DefenseModel())
    r0 = nelkul["figurak"][0]
    assert r0["lovo_mez"] is None and r0["lovo_szorzo"] == 1.0
    mezek = [None] * 4
    mezek[r0["tamado"] - 1] = 7
    lovo = AttackModel(lovok={7: {"close": 1.3, "mid": 1.3, "far": 1.3}})
    vele = rank_playbook([{"id": "a", "name": "Beúszás", "attackers": figura,
                           "labda": [0, 0, 1], "mez": mezek}],
                         DefenseModel(), tamadas=lovo)
    r1 = vele["figurak"][0]
    assert r1["lovo_mez"] == 7 and r1["lovo_szorzo"] == 1.3
    assert abs(r1["pont_pct"] - 1.3 * r0["pont_pct"]) < 0.2
    assert abs(r1["alap_pct"] - 1.3 * r0["alap_pct"]) < 0.2
    assert ("támadónál — a 7-es lövésével, aki innen 1,3× annyit lő be, "
            "mint amennyit a helyzet ér)") in vele["ajanlas"]
    # Mezszám nélkül a modell nem hat; a modell nélkül a mezszám csak
    # a sorba kerül.
    assert rank_playbook([{"id": "a", "name": "Beúszás", "attackers": figura,
                           "labda": [0, 0, 1]}], DefenseModel(),
                         tamadas=lovo)["figurak"][0]["pont_pct"] == r0["pont_pct"]
    csak = rank_playbook([{"id": "a", "name": "Beúszás", "attackers": figura,
                           "labda": [0, 0, 1], "mez": mezek}],
                         DefenseModel())["figurak"][0]
    assert (csak["lovo_mez"], csak["lovo_szorzo"], csak["pont_pct"]) == (
        7, 1.0, r0["pont_pct"])


def test_az_edzes_fokusz_a_zaro_lovot_is_megnevezi(monkeypatch):
    """489) Az ő tanult lövőikkel (a modell a tesztben adott, a próba
    valódi) a felkészülés-tétel a figurát záró lövőt is megnevezi."""
    import handball.pipeline.play_simulation as ps
    import handball.pipeline.training as tr
    from handball.pipeline.play_simulation import AttackModel
    from handball.pipeline.training import training_focus

    # A rangsor korlátja nélkül: a tanult lövőkkel más tétel (490) is
    # megszólal, és a területek közti forgás kiszoríthatná a 489-et.
    monkeypatch.setattr(tr, "MAX_ITEMS", 10_000)
    monkeypatch.setattr(ps.AttackModel, "learn", classmethod(
        lambda cls, match, team, config=None: AttackModel(
            lovok={m: {"close": 1.3, "mid": 1.3, "far": 1.3}
                   for m in (1, 2, 3)})))
    tetel = [i for i in training_focus(_proba_match(vedok=2))["away"]
             if i["title"] == "Felkészülés a figurájukra"]
    assert len(tetel) == 1
    assert "nyitja a rést; a végén " in tetel[0]["why"]
    assert tetel[0]["why"].endswith(
        "lövésével, aki innen 1,3× annyit lő be, mint amennyit a helyzet ér")


def test_az_utolso_loves_a_lovo_es_a_kapus_szorzojabol():
    """Utolsó lövés: a tanult lövő × sáv párosok értéke az xG a sáv
    képviselő-helyén × a lövő × a szemközti kapus szorzója; a legjobb az
    ajánlás, a leggyengébb (elég nagy különbséggel) a kerülendő, a
    mondat mindkettőt mondja; átlagos kapusnál és egy jelöltnél nincs
    záradék; tanult lövő nélkül None (nem találgat)."""
    from handball.pipeline.play_simulation import (AttackModel,
                                                   UTOLSO_LOVES_ELTERES,
                                                   UTOLSO_LOVES_TAV_M,
                                                   last_shot_choice)
    from handball.pipeline.xg import xg_of_position

    xg = {s: xg_of_position(40.0 - d, 10.0, 40.0)
          for s, d in UTOLSO_LOVES_TAV_M.items()}
    assert xg["close"] > xg["mid"] > xg["far"]
    m = AttackModel(lovok={7: {"far": 1.3}, 10: {"close": 0.7}})
    p = last_shot_choice(m, kapus={"far": 1.2, "close": 0.7})
    assert (p["mez"], p["sav"], p["sav_nev"], p["tav_m"], p["jeloltek"]) == (
        7, "far", "távolról", UTOLSO_LOVES_TAV_M["far"], 2)
    assert abs(p["ertek"] - xg["far"] * 1.3 * 1.2) < 1e-3
    assert (p["lovo_szorzo"], p["kapus_szorzo"]) == (1.3, 1.2)
    rossz = round(xg["close"] * 0.7 * 0.7, 3)
    assert p["ertek"] - rossz >= UTOLSO_LOVES_ELTERES
    assert p["kerulendo"] == {"mez": 10, "sav": "close", "sav_nev": "közelről",
                              "ertek": rossz}
    e = f"{p['ertek']:.2f}".replace(".", ",")
    k = f"{rossz:.2f}".replace(".", ",")
    assert p["verdict"] == (
        f"a 7-esé távolról (10 m): {e} várható gól — ő innen 1,3× annyit "
        "lő be, mint amennyit a helyzet ér, a kapusuk távolról 1,2× annyit "
        f"kap, mint az átlag; ne a 10-esé közelről ({k})")
    # Erős kapus távolról: a közeli, gyengébb lövő kerül előre.
    q = last_shot_choice(m, kapus={"far": 0.7})
    assert (q["mez"], q["sav"]) == (10, "close")
    # Egy jelölt, átlagos kapus: nincs kerülendő, nincs záradék.
    egy = last_shot_choice(AttackModel(lovok={5: {"mid": 1.0}}))
    assert egy["kerulendo"] is None and egy["kapus_szorzo"] == 1.0
    assert egy["verdict"] == (
        f"az 5-ösé közepes távolságból (8 m): "
        + f"{egy['ertek']:.2f}".replace(".", ",") + " várható gól")
    assert last_shot_choice(AttackModel()) is None
    assert last_shot_choice(None) is None


def test_az_utolso_loves_valodi_meccsbol_es_a_felderitesben():
    """A valódi láncon (szimulált meccs → tanult lövők, a szemközti kapus
    sávjai): a lövő csapatnak van utolsó labdája (a tanult sávjai közül,
    a legnagyobb értékű), a nem lövőnek None. A felderítés a nyers
    mintákat str mezszám-kulccsal tárolja, a képet újraszámolja, két
    meccs mintája összeadódik; az edzői kulcs és a meccsterv (az ő
    lövőik × a mi kapusunk) ugyanebből beszél; az összefoglaló a
    motor mondatát írja."""
    from handball.pipeline.coach_summary import coach_summary
    from handball.pipeline.play_simulation import (AttackModel,
                                                   _kapus_tanul,
                                                   last_shot_choice,
                                                   last_shot_pick)
    from handball.pipeline.scouting import (combine_reports, matchup_plan,
                                            scout_team)
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=600, fps=25.0, seed=1,
                              shots_per_min=8, halftime_break_s=30)
    r = last_shot_pick(m)
    assert r["away"] is None
    p = r["home"]
    lovok = AttackModel.learn(m, Team.HOME).lovok
    assert p and p["sav"] in lovok[p["mez"]]
    assert p["jeloltek"] == sum(len(s) for s in lovok.values())
    kapus = _kapus_tanul(m, Team.AWAY, TacticsConfig())
    assert p["kapus_szorzo"] == kapus.get(p["sav"], 1.0)
    assert p == last_shot_choice(AttackModel(lovok=lovok), kapus)

    rep = scout_team(m, Team.HOME)
    assert rep.lsp_lovo_minta and all(isinstance(k, str)
                                      for k in rep.lsp_lovo_minta)
    assert rep.lsp_pick and rep.lsp_pick["kapus_szorzo"] == 1.0
    assert any(k.startswith("Utolsó labdájuk: ") and "lövését vegyétek el"
               in k for k in rep.keys_to_game)
    ketto = combine_reports([rep, rep])
    for mez, savok in rep.lsp_lovo_minta.items():
        for sav, v in savok.items():
            assert ketto.lsp_lovo_minta[mez][sav][0] == 2 * v[0]
    assert ketto.lsp_pick and ketto.lsp_pick["mez"] == rep.lsp_pick["mez"]
    own = scout_team(m, Team.AWAY)
    assert own.lsp_kapus_minta and own.lsp_pick is None
    assert not any("Utolsó labdájuk" in k for k in own.keys_to_game)
    terv = [s for s in matchup_plan(own, rep)
            if s.startswith("Az ő utolsó labdájuk ellenetek ")]
    assert len(terv) == 1 and "lövését vegyétek el" in terv[0]
    forditva = [s for s in matchup_plan(rep, own)
                if s.startswith("A ti utolsó labdátok az ő kapusuk ellen ")]
    assert len(forditva) == 1
    szoveg = " ".join(s["body"] for s in coach_summary(m)["sections"])
    assert f"utolsó labdája {p['verdict']}." in szoveg


def test_az_edzes_fokusz_utolso_labda_szabalya(monkeypatch):
    """490) Ha a számok szerint nem mindegy (a lövő vagy a kapus szorzója
    érdemben eltér, vagy van kerülendő), a hajrá-szituáció edzés-tétel
    lesz a motor mondatával; ha minden szorzó átlagos és nincs
    kerülendő, nem szólal meg; a nem lövő oldalon soha."""
    import handball.pipeline.play_simulation as ps
    import handball.pipeline.training as tr
    from handball.pipeline.play_simulation import (AttackModel,
                                                   last_shot_choice)
    from handball.pipeline.training import training_focus

    # A rangsor korlátja nélkül (a 490. a támadás-terület végén áll).
    monkeypatch.setattr(tr, "MAX_ITEMS", 10_000)

    def tetelek(lovok, kapus):
        monkeypatch.setattr(ps.AttackModel, "learn", classmethod(
            lambda cls, match, team, config=None: AttackModel(
                lovok=lovok if team == Team.HOME else {})))
        monkeypatch.setattr(ps, "_kapus_tanul",
                            lambda match, team, config: kapus)
        f = training_focus(_proba_match())
        return {side: [i for i in f[side]
                       if i["title"] == "Utolsó labda: kire és honnan"]
                for side in ("home", "away")}

    t = tetelek({7: {"far": 1.3}, 10: {"close": 0.7}}, {"far": 1.2})
    assert len(t["home"]) == 1 and t["away"] == []
    vart = last_shot_choice(AttackModel(lovok={7: {"far": 1.3},
                                               10: {"close": 0.7}}),
                            {"far": 1.2})
    assert t["home"][0]["why"].endswith(vart["verdict"])
    assert "a 7-es távoli lövésére fut ki" in t["home"][0]["drill"]
    assert tetelek({7: {"far": 1.0}}, {}) == {"home": [], "away": []}


def test_az_elo_utolso_labda_a_hajraban_szoros_allasnal():
    """A felvétel vége előtt LIVE_UTOLSO_ELOTTE_S-szel, ha az állás
    legfeljebb LIVE_UTOLSO_KULONBSEG gólos: csapatonként az utolsó labda
    a megadott (szezon-) modellekből, a motor mondatával; ahol nincs
    modell, az addig látott kockákból tanul (lövés nélküli meccsen nincs
    tanult lövő → üres); a hajránál rövidebb meccs üres."""
    from handball.pipeline.play_simulation import (AttackModel,
                                                   LIVE_UTOLSO_ELOTTE_S,
                                                   last_shot_choice,
                                                   live_last_shot_alerts)

    m = _proba_match(ismetles=60)            # 240 mp > a hajrá 180 mp-e
    tam = {"home": AttackModel(lovok={1: {"far": 1.3}}),
           "away": AttackModel(lovok={5: {"close": 0.7, "mid": 1.2}})}
    kap = {"home": {"far": 1.2}, "away": {}}
    r = live_last_shot_alerts(m, tamadas=tam, kapus=kap)
    # (azonos kockán a csapat neve szerint: away, home)
    assert [a["team"] for a in r["alerts"]] == ["away", "home"]
    a, h = r["alerts"]
    assert h["t"] == m.frames[-1].t - int(round(LIVE_UTOLSO_ELOTTE_S * 25))
    perc = int((h["t"] - m.frames[0].t) / 25 // 60)
    assert (h["allas"], h["kulonbseg"], h["perc"]) == ("0:0", 0, perc)
    assert (h["mez"], h["sav"], h["team_name"]) == (1, "far", "Ők")
    assert h["text"] == (f"Utolsó labda ({perc}. perc, 0:0, egál): Ők utolsó "
                         "labdája "
                         + last_shot_choice(tam["home"], kap["home"])["verdict"])
    assert (a["mez"], a["sav"], a["team_name"]) == (5, "mid", "Mi")
    assert a["ertek"] == last_shot_choice(tam["away"], {})["ertek"]
    # Csak a hazai modellel: a vendég az addigi kockákból tanul — nincs.
    csak = live_last_shot_alerts(m, tamadas={"home": tam["home"]}, kapus=kap)
    assert [x["team"] for x in csak["alerts"]] == ["home"]
    assert live_last_shot_alerts(m)["alerts"] == []
    assert live_last_shot_alerts(_proba_match(ismetles=10), tamadas=tam,
                                 kapus=kap)["alerts"] == []


def test_az_elo_kit_kinek_az_addig_latott_falbol(monkeypatch):
    """A 3. percben (küszöb átállítva) a vendég addig látott, mezszámos
    fala védői × a megadott (szezon-) lövő-modell: a veszélyes távoli
    lövőre a kit-kinek párja (a sávjában a ritkán kilépő 7-es, a kilépő
    5-ös álljon elé), a gyenge távolira az engedett-lövő sora — a motor
    mondataival; a hazai nem védekezik → semmi; a 6. percben ugyanaz a
    fal ugyanazt mondaná → nem ismétlődik; csak az addigi kockákból;
    rövid meccsnél üres; modell nélkül az addig látott kockákból tanul
    (mezszám és lövés nélküli meccsen → üres)."""
    import handball.pipeline.play_simulation as ps
    from handball.pipeline.play_simulation import (AttackModel,
                                                   _tanulas_minta,
                                                   allowed_shooters_from,
                                                   live_matchup_alerts,
                                                   shooter_defender_pairs)
    from handball.sim.match_simulator import simulate_ground_truth

    monkeypatch.setattr(ps, "LIVE_AJANLO_PERCEK", (3, 6))
    m = simulate_ground_truth(duration_s=600, fps=25.0, seed=1,
                              shots_per_min=8, halftime_break_s=30)
    nev = m.meta.away_team
    tam = AttackModel(lovok={9: {"far": 1.3}, 7: {"far": 0.8, "close": 1.2}})
    sav = {9: [5, 1, 0]}
    minta = {7: {"far": [6, 1, 2.1]}}
    be = dict(tamadas={"away": tam}, savok={"away": sav}, mintak={"away": minta})
    r = live_matchup_alerts(m, **be)["alerts"]
    assert [(a["perc"], a["team"], a["fajta"]) for a in r] == [
        (3, "away", "engedett"), (3, "away", "kit_kinek")]
    hatar = m.frames[0].t + 3 * 60 * 25
    eddig = Match(m.meta, [f for f in m.frames if f.t <= hatar])
    vedok = DefenseModel._modell_mintabol(
        _tanulas_minta(eddig, Team.AWAY, TacticsConfig())).vedok
    assert len(vedok) == 6
    par = shooter_defender_pairs(tam, sav, vedok)[0]
    eng = allowed_shooters_from(tam, minta)[0]
    e, k = r
    assert (k["lovo_mez"], k["vedo_mez"], k["javasolt_mez"], k["verdict"]) == (
        9, 7, 5, par["verdict"])
    assert k["team_name"] == nev
    assert k["text"] == f"Kit kinek (3. perc): {nev} eddig látott fala — {par['verdict']}"
    assert (e["lovo_mez"], e["vedo_mez"], e["javasolt_mez"], e["verdict"]) == (
        7, None, None, eng["verdict"])
    assert e["text"] == (f"Engedett lövő (3. perc): {nev} eddig látott fala — "
                         f"{eng['verdict']}")
    assert e["t"] == k["t"] == hatar and e["t_s"] == hatar / 25
    # csak az addigi kockák: az első 3 perc önmagában ugyanazt adja
    assert live_matchup_alerts(eddig, **be)["alerts"] == r
    assert live_matchup_alerts(Match(m.meta, m.frames[:1000]), **be)["alerts"] == []
    assert live_matchup_alerts(_proba_match(ismetles=40))["alerts"] == []


def test_az_elo_loves_elosztas_az_addigi_lovesekbol(monkeypatch):
    """Az 1. és 2. percben (küszöb átállítva) a hazai addigi lövései (a
    patchelt nyers minta — a részesedés MINDIG az addigi kockákból) × a
    megadott (szezon-) lövő-modell: döntésnél a motor mondata a támadó
    oldalnak; ugyanaz a pár a 2. percben nem ismétlődik, más pár igen;
    modell nélkül az addigi kockákból tanul; a vendégnek nincs lövése →
    semmi; a minta csak a percig tartó kockákat kapja (okszerű)."""
    import handball.pipeline.play_simulation as ps
    from handball.pipeline.play_simulation import (AttackModel,
                                                   live_shot_allocation_alerts,
                                                   shot_allocation_from)

    monkeypatch.setattr(ps, "LIVE_AJANLO_PERCEK", (1, 2))
    latott = []
    minta = {7: {"close": [3, 3, 1.5]}, 10: {"close": [9, 3, 4.5]}}

    def _minta(match, team, config):
        latott.append(match.frames[-1].t)
        return minta if team == Team.HOME else {}

    monkeypatch.setattr(ps, "_lovo_minta", _minta)
    m = _proba_match(ismetles=40)          # 160 mp — eléri a 2. percet
    r = live_shot_allocation_alerts(m)["alerts"]
    assert [(a["perc"], a["team"]) for a in r] == [(1, "home")]
    a = r[0]
    vart = shot_allocation_from(AttackModel(lovok={7: {"close": 1.3},
                                                   10: {"close": 0.8}}),
                                {}, minta)
    assert (a["tobbet_mez"], a["tobbet_sav"], a["kevesebbet_mez"],
            a["kevesebbet_sav"], a["lovesek"]) == (7, "close", 10, "close", 12)
    assert a["verdict"] == vart["verdict"]
    assert a["text"] == f"Lövés-elosztás (1. perc): Ők — {vart['verdict']}"
    hatar1 = m.frames[0].t + 60 * 25
    assert a["t"] == hatar1 and a["t_s"] == hatar1 / 25
    assert max(latott) <= m.frames[0].t + 120 * 25
    # A szezon-modell szerint a 10-es a jobb: más pár, a 2. percben is.
    tam = {"home": AttackModel(lovok={7: {"close": 0.8}, 10: {"close": 1.3},
                                      11: {"close": 1.0}})}
    monkeypatch.setattr(ps, "_lovo_minta", lambda match, team, config: (
        {7: {"close": [9, 3, 4.5]}, 10: {"close": [2, 1, 1.0]},
         11: {"close": [1, 0, 0.5]}} if team == Team.HOME else {}))
    r2 = live_shot_allocation_alerts(m, tamadas=tam)["alerts"]
    assert [(x["perc"], x["tobbet_mez"], x["kevesebbet_mez"]) for x in r2] == [
        (1, 10, 7)]
    assert live_shot_allocation_alerts(_proba_match(ismetles=5))["alerts"] == []

def test_az_elo_kapus_valasztas_a_szezon_es_az_addigiak_mintajabol(
        monkeypatch):
    """A valódi láncon (szimulált meccs: a hazai sokat lő távolról, a
    vendég kapuját az 1-es védi): a 3. percben (küszöb átállítva) a
    vendég 1-es kapusa addig távolról alig véd; a szezon-mintában a 16-os
    távolról jól véd → a modell a 16-ost javasolja, és mivel most az 1-es
    áll bent, szól — a motor mondatával; a 6. percben ugyanazt nem
    ismétli; a hazai oldalon (nincs második kapus) semmi; szezon-minta
    nélkül (egy kapus) semmi; ha a javasolt áll bent, semmi."""
    import handball.pipeline.play_simulation as ps
    from handball.pipeline.play_simulation import (_kapus_minta_kapusonkent,
                                                   _kapus_mintak_osszege,
                                                   _kapus_most, _lovo_minta,
                                                   keeper_choice_from,
                                                   live_keeper_alerts)
    from handball.sim.match_simulator import simulate_ground_truth

    monkeypatch.setattr(ps, "LIVE_AJANLO_PERCEK", (3, 6))
    m = simulate_ground_truth(duration_s=600, fps=25.0, seed=1,
                              shots_per_min=8, halftime_break_s=30)
    cfg = TacticsConfig()
    szezon = {"away": {16: {"far": [30, 22], "close": [10, 4]}}}
    r = live_keeper_alerts(m, kapus_mintak=szezon)["alerts"]
    assert [(a["perc"], a["team"], a["most_mez"], a["javasolt_mez"])
            for a in r] == [(3, "away", 1, 16)]
    hatar = m.frames[0].t + 3 * 60 * 25
    eddig = Match(m.meta, [f for f in m.frames if f.t <= hatar])
    assert _kapus_most(eddig, Team.AWAY, cfg) == 1
    vart = keeper_choice_from(
        _lovo_minta(eddig, Team.HOME, cfg),
        _kapus_mintak_osszege([szezon["away"],
                               _kapus_minta_kapusonkent(eddig, Team.AWAY, cfg)]))
    a = r[0]
    assert a["verdict"] == vart["verdict"] and a["elteres"] == vart["elteres"]
    assert a["text"] == (f"Kapus-választás (3. perc): {m.meta.away_team} "
                         f"kapujában most az 1-es áll — {vart['verdict']}")
    assert live_keeper_alerts(m)["alerts"] == []
    # Ha a szezonból a 16-os rosszabb, az 1-es marad (ő áll bent) → semmi.
    rossz = {"away": {16: {"far": [30, 2], "close": [10, 0]}}}
    assert live_keeper_alerts(m, kapus_mintak=rossz)["alerts"] == []


def test_az_elo_utolso_labda_okszeru_es_az_allast_nezi(monkeypatch):
    """A valódi láncon (szimulált meccs: a hazai sok gólt lő, a vendég
    nem): az állás a hajrá elején nem szoros → nincs riasztás; a küszöb
    feloldva a hazainak szól, az ADDIG látott kockákból tanult lövőkkel
    és a vendég kapus addigi sávjaival (a meccs vége nem számít), a
    vendégnek nincs tanult lövője."""
    import handball.pipeline.play_simulation as ps
    from handball.pipeline.play_simulation import (AttackModel,
                                                   LIVE_UTOLSO_ELOTTE_S,
                                                   _kapus_tanul,
                                                   last_shot_choice,
                                                   live_last_shot_alerts)
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=600, fps=25.0, seed=1,
                              shots_per_min=8, halftime_break_s=30)
    assert live_last_shot_alerts(m)["alerts"] == []
    monkeypatch.setattr(ps, "LIVE_UTOLSO_KULONBSEG", 100)
    r = live_last_shot_alerts(m)["alerts"]
    assert [a["team"] for a in r] == ["home"]
    a = r[0]
    t_h = m.frames[-1].t - int(round(LIVE_UTOLSO_ELOTTE_S * 25))
    eddig = Match(m.meta, [f for f in m.frames if f.t <= t_h])
    vart = last_shot_choice(AttackModel.learn(eddig, Team.HOME),
                            _kapus_tanul(eddig, Team.AWAY, TacticsConfig()))
    assert a["text"].endswith(vart["verdict"]) and a["t"] == t_h
    h, v = (int(x) for x in a["allas"].split(":"))
    assert h > v == 0 and a["kulonbseg"] == h
    assert f"{h} gól előny" in a["text"]
    # Okszerűség: a hajrá kockáit üresre cserélve (ugyanaddig tart a
    # felvétel) ugyanaz a riasztás — a későbbi lövések nem számítanak.
    ures = [Frame(t=f.t, players=[], ball=None) for f in m.frames
            if f.t > t_h]
    assert live_last_shot_alerts(Match(m.meta, eddig.frames + ures)
                                 )["alerts"] == r
