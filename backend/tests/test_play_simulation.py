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


def _pl(track_id, team, x, y):
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0)


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
    védővel (6: zárt 6-0; kevesebb: ritka fal)."""
    frames = []
    t = 0
    for _ in range(ismetles):
        n = int(3 * fps)
        for s in range(n):
            u = s / (n - 1)
            a1 = (25 + 5 * u, 10.0)
            players = [_pl(1, Team.HOME, *a1),
                       _pl(2, Team.HOME, 30 + 4 * u, 2 + 6 * u),
                       _pl(3, Team.HOME, 27.0, 15.0)]
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
