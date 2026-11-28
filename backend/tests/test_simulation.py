"""
Tesztek a meccs-szimulátorra (handball.sim).

Videó nélkül igazoljuk, hogy a szimulátor valósághű, reprodukálható Tracking-et
ad, és hogy a pásztázó-kamerás változat tényleg becsli a látómezőből kieső
játékosokat (a valódi [F] becslővel).

Futtatás:
    python tests/test_simulation.py
"""

from __future__ import annotations

# A backend/ mappát a kereső-útvonalra tesszük, hogy a teszt bárhonnan fusson.
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import Team, PositionSource
from handball.sim import simulate_ground_truth, simulate_with_panning_camera
from handball.pipeline.calibration import COURT_LENGTH_M, COURT_WIDTH_M


def test_ground_truth_has_full_teams_and_ball():
    """A földi igazságban minden frame-en 14 játékos (7+7) és labda van."""
    match = simulate_ground_truth(duration_s=2.0, fps=25.0, seed=1)
    assert len(match.frames) == 50
    for fr in match.frames:
        assert len(fr.players) == 14
        home = [p for p in fr.players if p.team == Team.HOME]
        away = [p for p in fr.players if p.team == Team.AWAY]
        assert len(home) == 7 and len(away) == 7
        assert fr.ball is not None
        # Minden játékos a pályán belül, és mind MÉRT (kamera-korlát nélkül).
        for p in fr.players:
            assert 0.0 <= p.x <= COURT_LENGTH_M
            assert 0.0 <= p.y <= COURT_WIDTH_M
            assert p.source == PositionSource.MEASURED


def test_ground_truth_is_reproducible():
    """Ugyanaz a seed ugyanazt a meccset adja (determinizmus)."""
    a = simulate_ground_truth(duration_s=1.0, seed=42)
    b = simulate_ground_truth(duration_s=1.0, seed=42)
    assert a.to_json() == b.to_json()


def test_panning_camera_produces_estimates():
    """Szűk látómezővel a kieső játékosokat BECSÜLI a rendszer.

    Ellenőrizzük, hogy keletkezik becsült pozíció, és hogy a látott (mért)
    játékosok tényleg a látómezőn belül vannak.
    """
    ground = simulate_ground_truth(duration_s=4.0, fps=25.0, seed=0)
    panned = simulate_with_panning_camera(ground, fov_width_m=12.0)

    total_estimated = 0
    for gt, fr in zip(ground.frames, panned.frames):
        cam_x = gt.ball.x
        for p in fr.players:
            if p.source == PositionSource.ESTIMATED:
                total_estimated += 1
            else:
                # A mért játékos a látómezőn belül van (|x - kamera| <= fél FOV).
                assert abs(p.x - cam_x) <= 6.0 + 1e-9
    assert total_estimated > 0, "szűk látómezőnél kell lennie becsült játékosnak"


def test_panning_never_exceeds_roster():
    """Csapatonként a (látott + becsült) játékosszám sosem több a pályán lévőnél (7)."""
    ground = simulate_ground_truth(duration_s=3.0, fps=25.0, seed=3)
    panned = simulate_with_panning_camera(ground, fov_width_m=14.0)
    for fr in panned.frames:
        for team in (Team.HOME, Team.AWAY):
            count = sum(1 for p in fr.players if p.team == team)
            assert count <= 7, f"{team} létszám {count} > 7"


def test_estimated_positions_within_court():
    """A becsült pozíciók is a pályán belül maradnak (a becslő határvágása miatt)."""
    ground = simulate_ground_truth(duration_s=3.0, fps=25.0, seed=7)
    panned = simulate_with_panning_camera(ground, fov_width_m=12.0)
    for fr in panned.frames:
        for p in fr.players:
            assert -1e-9 <= p.x <= COURT_LENGTH_M + 1e-9
            assert -1e-9 <= p.y <= COURT_WIDTH_M + 1e-9


# ---- A szimulátor építőkövei közvetlenül -------------------------------------

def test_roster_specs_ket_teljes_csapat_a_palyan():
    """A szimulált keret: 7 hazai + 7 vendég, csapatonként egy kapussal,
    egyedi követő-azonosítókkal és csapaton belül egyedi mezszámokkal;
    az alappozíciók a pályán belül; a hazai a x=40 kapura támad (a
    kapusa x=1-nél), a vendég fal a saját kapuja (x=40) előtt áll."""
    from handball.sim.match_simulator import _roster_specs

    keret = _roster_specs()
    assert len(keret) == 14
    assert len({s.track_id for s in keret}) == 14
    for csapat in (Team.HOME, Team.AWAY):
        sajat = [s for s in keret if s.team == csapat]
        assert len(sajat) == 7
        kapusok = [s for s in sajat if s.is_gk]
        assert len(kapusok) == 1 and kapusok[0].role == "kapus"
        assert len({s.jersey for s in sajat}) == 7
    for s in keret:
        assert 0.0 <= s.base_x <= COURT_LENGTH_M
        assert 0.0 <= s.base_y <= COURT_WIDTH_M
    kapu = {s.team: s.base_x for s in keret if s.is_gk}
    assert kapu[Team.HOME] < 5.0 and kapu[Team.AWAY] > 35.0
    fal = [s.base_x for s in keret if s.team == Team.AWAY and not s.is_gk]
    tamadok = [s.base_x for s in keret if s.team == Team.HOME and not s.is_gk]
    assert min(fal) > max(x for x in tamadok if x < 34.0)   # a fal mögöttük
    assert all(34.0 <= x <= 36.0 for x in fal)              # a 6 m-es ívnél
    # Minden hívás saját listát ad (a hívó módosíthatja).
    assert _roster_specs() is not keret


def test_player_xy_az_alappozicio_korul_a_palyan_belul():
    """Egy játékos helye: az alappozíció körül lassan ingadozik (a kapus
    kevesebbet, mint a mezőnyjátékos), kis zajjal — a pályán belül
    tartva; ugyanazzal a maggal megismételhető; az ingadozás IDŐBEN
    (másodpercben) halad, nem kockában."""
    import random

    from handball.sim.match_simulator import _PlayerSpec, _player_xy

    mezony = _PlayerSpec(3, Team.HOME, "iranyito", 27.0, 10.0, 10)
    kapus = _PlayerSpec(7, Team.HOME, "kapus", 1.0, 10.0, 1, is_gk=True)
    rng = random.Random(4)
    for t in range(0, 1500, 7):
        x, y = _player_xy(mezony, t, 25.0, rng)
        assert abs(x - 27.0) <= 0.8 + 0.15 + 1e-9
        assert abs(y - 10.0) <= 1.2 + 0.15 + 1e-9
        kx, ky = _player_xy(kapus, t, 25.0, rng)
        assert abs(kx - 1.0) <= 0.3 + 0.15 + 1e-9
        assert abs(ky - 10.0) <= 0.6 + 0.15 + 1e-9
    # Megismételhető, és a mozgás tényleg mozgás (nem áll egy helyben).
    a = [_player_xy(mezony, t, 25.0, random.Random(1)) for t in range(100)]
    b = [_player_xy(mezony, t, 25.0, random.Random(1)) for t in range(100)]
    assert a == b
    assert max(p[0] for p in a) - min(p[0] for p in a) > 0.3
    # Ugyanaz a pillanat (2 mp) 25 és 12,5 fps-en ugyanott van.
    assert _player_xy(mezony, 50, 25.0, random.Random(1)) == \
        _player_xy(mezony, 25, 12.5, random.Random(1))
    # A pálya szélén álló játékos sem lóg ki.
    sarok = _PlayerSpec(1, Team.HOME, "szelso", 40.0, 0.0, 7)
    for t in range(0, 500, 3):
        x, y = _player_xy(sarok, t, 25.0, rng)
        assert 0.0 <= x <= COURT_LENGTH_M and 0.0 <= y <= COURT_WIDTH_M


def test_ball_xy_a_birtokosnal_majd_a_fogado_fele():
    """A labda a passz-útvonalon jár körbe: a ciklus első 60%-ában a
    birtokosnál van, utána egyenletesen a következő birtokos felé halad,
    és a ciklus végén nála van; az útvonal a végén elölről kezdődik."""
    from handball.sim.match_simulator import (_BALL_ROUTE, _PASS_PERIOD_S,
                                              _ball_xy)

    assert _PASS_PERIOD_S == 1.0
    hely = {tid: (float(tid), 10.0 + tid) for tid in set(_BALL_ROUTE)}
    fps = 10.0                                       # 10 kocka / passz
    elso, masodik = _BALL_ROUTE[0], _BALL_ROUTE[1]
    for t in range(0, 7):                            # 0–60%: a birtokosnál
        assert _ball_xy(hely, t, fps) == hely[elso]
    felut = _ball_xy(hely, 8, fps)                   # 80%: félúton
    assert abs(felut[0] - (hely[elso][0] + hely[masodik][0]) / 2) < 1e-9
    assert abs(felut[1] - (hely[elso][1] + hely[masodik][1]) / 2) < 1e-9
    assert _ball_xy(hely, 10, fps) == hely[masodik]  # a következő ciklus
    # Az útvonal körbeér: a teljes kör után újra az első birtokosnál.
    kor = len(_BALL_ROUTE) * 10
    assert _ball_xy(hely, kor, fps) == hely[elso]
    assert _ball_xy(hely, kor - 10, fps) == hely[_BALL_ROUTE[-1]]
    # Nagyon ritka mintavételnél (1 kocka / passz) sincs nullával osztás.
    assert _ball_xy(hely, 3, 0.5) == hely[_BALL_ROUTE[3]]


def test_shot_episode_tartas_majd_repules_a_ciklus_vegen():
    """A lövés-epizód a ciklus VÉGÉRE esik: előbb SHOT_HOLD_FRAMES
    kockán át a lövő kezében van a labda (enélkül nincs elengedés-
    pillanat), aztán SHOT_FLIGHT_FRAMES kocka alatt a kapuba repül (a
    haladás 1/9 … 1); a lövők ciklusonként körbejárnak; lövés nélküli
    beállításnál (0 hosszú ciklus) None."""
    from handball.sim.match_simulator import (SHOT_FLIGHT_FRAMES,
                                              SHOT_HOLD_FRAMES,
                                              _SHOOTER_ROTATION,
                                              _shot_episode)

    assert (SHOT_HOLD_FRAMES, SHOT_FLIGHT_FRAMES) == (5, 9)
    ciklus = 100
    kezdet = ciklus - SHOT_HOLD_FRAMES - SHOT_FLIGHT_FRAMES      # 86
    for t in range(0, kezdet):
        assert _shot_episode(t, 25.0, ciklus) is None
    lovo = _SHOOTER_ROTATION[0]
    for t in range(kezdet, kezdet + SHOT_HOLD_FRAMES):
        assert _shot_episode(t, 25.0, ciklus) == (lovo, 0.0, True)
    haladas = [_shot_episode(t, 25.0, ciklus)
               for t in range(kezdet + SHOT_HOLD_FRAMES, ciklus)]
    assert all(e[0] == lovo and e[2] is False for e in haladas)
    assert [round(e[1] * 9) for e in haladas] == list(range(1, 10))
    assert haladas[-1][1] == 1.0                     # a végén a kapuban
    # A lövők körbejárnak, és a kör végén elölről kezdődnek.
    lovok = [_shot_episode(c * ciklus + kezdet, 25.0, ciklus)[0]
             for c in range(len(_SHOOTER_ROTATION) + 2)]
    assert lovok == _SHOOTER_ROTATION + _SHOOTER_ROTATION[:2]
    assert _shot_episode(50, 25.0, 0) is None
    assert _shot_episode(50, 25.0, -10) is None


def test_a_szimulalt_loves_a_lovo_kezebol_a_kapuba_megy():
    """A VALÓDI úton: lövésekkel szimulált meccsen a tartás kockáin a
    labda a lövő mellett van (0,3 m-re), a repülés utolsó kockáján a
    kapu közepén túl (x = 40,3; y = 10) — az epizód-segéd szerint."""
    from handball.sim.match_simulator import _shot_episode

    fps, perc_loves = 25.0, 6.0
    m = simulate_ground_truth(duration_s=30.0, fps=fps, seed=2,
                              shots_per_min=perc_loves)
    ciklus = int(fps * 60.0 / perc_loves)            # 250 kocka
    tartas = repules_vege = 0
    for f in m.frames:
        epizod = _shot_episode(f.t, fps, ciklus)
        if epizod is None:
            continue
        lovo, haladas, kezben = epizod
        p = next(p for p in f.players if p.track_id == lovo)
        if kezben:
            assert abs(f.ball.x - (p.x + 0.3)) < 1e-9
            assert abs(f.ball.y - p.y) < 1e-9
            tartas += 1
        elif haladas == 1.0:
            assert abs(f.ball.x - 40.3) < 1e-9 and abs(f.ball.y - 10.0) < 1e-9
            repules_vege += 1
    assert tartas == 3 * 5 and repules_vege == 3      # 30 mp: három lövés
    # Lövés nélkül (alapértelmezés) a labda sosem megy a kapuba.
    csendes = simulate_ground_truth(duration_s=30.0, fps=fps, seed=2)
    assert max(f.ball.x for f in csendes.frames) < 38.0


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
