"""
Tesztek az eseményfelismerésre (event_detection.py): lövés, gól, passz, labdaeladás.

Szintetikus pályák, videó nélkül. A HAZAI a +x (x=40) kapu felé támad.

Futtatás:
    python tests/test_event_detection.py
"""

from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, Ball, Team, PositionSource,
)
from handball.pipeline.event_detection import (
    detect_shots, detect_possession_changes, detect_events, event_counts, EventType,
)


def _meta(fps=25.0):
    return MatchMeta(match_id="t", home_team="A", away_team="B", fps=fps)


def _pl(track_id, team, x, y):
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0)


def _hold(frames, n=3):
    """Minden kockát n-szer ismétel, ÚJRA-IDŐZÍTVE (t = 0, 1, 2, ...).

    Miért kell: a birtoklás-fixture-ök kockánként váltó birtokost
    modelleznek (1 → 2 → 11, kockánként egy). Valódi meccsen ez nem
    fordul elő: aki megkapja a labdát, legalább néhány tized
    másodpercig tartja is. A kockánkénti váltás azért fontos
    különbség, mert éppen ez a KÜLÖNBSÉG választja el a valódi
    passz-sorozatot a "legközelebbi játékos" szabály zajától
    (tömörülésnél a jel kockánként ide-oda billeg) — lásd
    docs/ROADMAP.md, "Birtoklás-váltás billegése".

    A segéd a fixture-ök szemantikáját nem érinti: ugyanaz a
    birtokos-SORREND, csak valósághű tartással. A jelenlegi
    felismeréssel az események száma változatlan — ezt a zöld
    teszt-csomag igazolja.

    KORLÁT: LÖVÉS-fixture-re nem alkalmazható. A lövés-felismerés a
    labda SEBESSÉGÉBŐL dolgozik, az ismételt kocka pedig álló labdát
    jelent — a 25 m/s-os röppályából 8,3 m/s lenne, épp a
    lövés-küszöb környékén. Csak TISZTA birtoklás-fixture-höz."""
    ki = []
    t = 0
    for f in frames:
        for _ in range(n):
            ki.append(Frame(t=t, players=list(f.players), ball=f.ball))
            t += 1
    return ki


def test_detect_goal():
    """A labda gyorsan a +x kapuhoz tart és a kapufák között eléri → GÓL (hazai)."""
    # x = 34..40 (1 m/frame = 25 m/s), y=10 (kapu közepe).
    frames = [Frame(t=i, players=[], ball=Ball(x=34.0 + i, y=10.0, confidence=1.0))
              for i in range(7)]
    shots = detect_shots(Match(_meta(), frames))
    goals = [e for e in shots if e.type == EventType.GOAL]
    assert len(goals) == 1
    assert goals[0].team == Team.HOME


def test_detect_shot_not_goal_when_off_target():
    """Gyors kapu felé tartó labda, de a kapufákon KÍVÜL (y=5) → LÖVÉS, nem gól."""
    frames = [Frame(t=i, players=[], ball=Ball(x=34.0 + i, y=5.0, confidence=1.0))
              for i in range(6)]  # x 34..39, sosem éri el a vonalat a kapuban
    shots = detect_shots(Match(_meta(), frames))
    assert len(shots) == 1
    assert shots[0].type == EventType.SHOT


def test_pass_vs_turnover():
    """Csapaton belüli birtokosváltás = passz; az ellenfélhez = labdaeladás."""
    frames = [
        Frame(t=0, players=[_pl(1, Team.HOME, 25.0, 10.0)], ball=Ball(x=25.0, y=10.0, confidence=1.0)),
        Frame(t=1, players=[_pl(2, Team.HOME, 28.0, 10.0)], ball=Ball(x=28.0, y=10.0, confidence=1.0)),  # passz 1->2
        Frame(t=2, players=[_pl(11, Team.AWAY, 20.0, 10.0)], ball=Ball(x=20.0, y=10.0, confidence=1.0)),  # eladás
    ]
    # Tartás: 10 kocka @ 25 fps = 0,4 mp birtoklásonként — valódi
    # meccsen a birtokos nem kockánként vált (lásd _hold).
    evs = detect_possession_changes(Match(_meta(), _hold(frames, 10)))
    assert [e.type for e in evs] == [EventType.PASS, EventType.TURNOVER]
    assert evs[0].detail == {"receiver_id": 2}
    assert evs[1].team == Team.HOME   # a HAZAI vesztette el


def test_turnover_suppressed_after_shot():
    """A lövés után az ellenfélhez kerülő labda NEM külön labdaeladás."""
    frames = []
    # Lövés a +x kapura (gyors), gól nélkül (y=6): x 34..40 y=6.
    for i in range(7):
        frames.append(Frame(t=i, players=[_pl(1, Team.HOME, 33.0, 6.0)],
                            ball=Ball(x=34.0 + i, y=6.0, confidence=1.0)))
    # Közvetlenül utána a vendég kapusé a labda — a kaputól OLDALT (y=4), hogy a
    # lövés ne minősüljön gólnak, csak a birtokváltást teszteljük.
    frames.append(Frame(t=7, players=[_pl(17, Team.AWAY, 39.5, 4.0)],
                        ball=Ball(x=39.5, y=4.0, confidence=1.0)))
    evs = detect_events(Match(_meta(), frames))
    types = [e.type for e in evs]
    assert EventType.SHOT in types           # a lövés megmarad
    assert EventType.TURNOVER not in types   # a lövés utáni labdaeladás elnyomva


def test_event_counts():
    """Az összegző típusonként számol."""
    frames = [
        Frame(t=0, players=[_pl(1, Team.HOME, 25.0, 10.0)], ball=Ball(x=25.0, y=10.0, confidence=1.0)),
        Frame(t=1, players=[_pl(2, Team.HOME, 28.0, 10.0)], ball=Ball(x=28.0, y=10.0, confidence=1.0)),
    ]
    c = event_counts(Match(_meta(), _hold(frames)))
    assert c["total"] == 1
    assert c["by_type"]["pass"] == 1


def test_shot_outcome_save_with_goalkeeper():
    """Nem-gól lövés, ahol a labda a megjelölt KAPUS közelébe ér → védés."""
    gk = PlayerPosition(track_id=9, team=Team.AWAY, x=39.0, y=10.0,
                        source=PositionSource.MEASURED, confidence=1.0,
                        role="kapus")
    # A labda a kapu felé száll (kapufák között), de a kapusnál megáll —
    # nem éri el a gólvonalat.
    frames = []
    for i in range(6):
        x = min(34.0 + i, 38.8)
        frames.append(Frame(t=i, players=[gk],
                            ball=Ball(x=x, y=10.0, confidence=1.0)))
    shots = detect_shots(Match(_meta(), frames))
    assert len(shots) == 1
    e = shots[0]
    assert e.type == EventType.SHOT
    assert e.detail["outcome"] == "save"
    assert e.detail["goalkeeper_id"] == 9


def test_shot_outcome_miss_without_goalkeeper():
    """Kapus-jel nélkül a nem-gól lövés kimenetele "miss"."""
    frames = [Frame(t=i, players=[], ball=Ball(x=34.0 + i, y=5.0, confidence=1.0))
              for i in range(6)]
    shots = detect_shots(Match(_meta(), frames))
    assert shots[0].detail["outcome"] == "miss"


def test_goal_outcome_and_shooter():
    """Gólnál a kimenetel "goal", és a lövő (az utolsó hazai birtokos) is megvan."""
    shooter = _pl(4, Team.HOME, 33.5, 10.0)
    frames = [Frame(t=0, players=[shooter],
                    ball=Ball(x=33.6, y=10.0, confidence=1.0))]
    for i in range(1, 8):
        frames.append(Frame(t=i, players=[],
                            ball=Ball(x=33.6 + i, y=10.0, confidence=1.0)))
    shots = detect_shots(Match(_meta(), frames))
    goals = [e for e in shots if e.type == EventType.GOAL]
    assert len(goals) == 1
    assert goals[0].detail["outcome"] == "goal"
    assert goals[0].player_id == 4


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


# ---- Gólpassz (assist) -------------------------------------------------------

def _goal_with_pass(passer_present=True, receiver_id=2):
    """Passz (1 → receiver_id), majd a 2-es játékos gólja a +x kapura."""
    pls = lambda *ps: list(ps)  # noqa: E731
    frames = [
        Frame(t=0, players=pls(_pl(1, Team.HOME, 25.0, 10.0),
                               _pl(2, Team.HOME, 30.0, 10.0)),
              ball=Ball(x=25.0, y=10.0, confidence=1.0)),
        Frame(t=1, players=pls(_pl(1, Team.HOME, 25.0, 10.0),
                               _pl(receiver_id, Team.HOME, 30.0, 10.0)),
              ball=Ball(x=30.0, y=10.0, confidence=1.0)),
        Frame(t=2, players=pls(_pl(1, Team.HOME, 25.0, 10.0),
                               _pl(2, Team.HOME, 33.0, 10.0)),
              ball=Ball(x=33.0, y=10.0, confidence=1.0)),
    ]
    if not passer_present:  # csak a lövő: nincs passz-esemény a gól előtt
        frames = [Frame(t=f.t, players=[p for p in f.players if p.track_id == 2],
                        ball=f.ball) for f in frames]
    for k in range(3):  # a labda a lövő kezében (elengedés előtt)
        frames.append(Frame(t=3 + k,
                            players=pls(_pl(2, Team.HOME, 33.0, 10.0)),
                            ball=Ball(x=33.2, y=10.0, confidence=1.0)))
    for i in range(7):  # a lövés: 34..40, y=10 → gól a kapufák között
        frames.append(Frame(t=6 + i,
                            players=pls(_pl(2, Team.HOME, 33.0, 10.0)),
                            ball=Ball(x=34.0 + i, y=10.0, confidence=1.0)))
    return Match(_meta(), frames)


def test_assist_attached_to_goal():
    """Passz a lövőnek, majd gól → a gól detail-jében assist_id a passzoló."""
    evs = detect_events(_goal_with_pass())
    goals = [e for e in evs if e.type == EventType.GOAL]
    assert len(goals) == 1
    assert goals[0].player_id == 2               # a lövő
    assert goals[0].detail.get("assist_id") == 1  # a gólpassz adója


def test_no_assist_without_prior_pass():
    """Egyéni akció (nincs passz a gól előtt) → nincs assist_id."""
    evs = detect_events(_goal_with_pass(passer_present=False))
    goals = [e for e in evs if e.type == EventType.GOAL]
    assert len(goals) == 1
    assert "assist_id" not in (goals[0].detail or {})


def test_old_pass_outside_window_is_not_assist():
    """A lövő rég (több mint ASSIST_WINDOW_S) kapta a labdát → nem gólpassz
    (egyéni akciónak számít, hiába volt korábban passz)."""
    frames = [
        Frame(t=0, players=[_pl(1, Team.HOME, 25.0, 10.0),
                            _pl(2, Team.HOME, 30.0, 10.0)],
              ball=Ball(x=25.0, y=10.0, confidence=1.0)),
        Frame(t=1, players=[_pl(1, Team.HOME, 25.0, 10.0),
                            _pl(2, Team.HOME, 30.0, 10.0)],
              ball=Ball(x=30.0, y=10.0, confidence=1.0)),  # passz 1→2
    ]
    for t in range(2, 111):  # a lövő ~4,4 mp-ig vezeti a labdát
        frames.append(Frame(t=t, players=[_pl(2, Team.HOME, 33.0, 10.0)],
                            ball=Ball(x=33.0, y=10.0, confidence=1.0)))
    for i in range(7):  # lövés: 34..40, y=10 → gól
        frames.append(Frame(t=111 + i, players=[_pl(2, Team.HOME, 33.0, 10.0)],
                            ball=Ball(x=34.0 + i, y=10.0, confidence=1.0)))
    evs = detect_events(Match(_meta(), frames))
    goals = [e for e in evs if e.type == EventType.GOAL]
    assert len(goals) == 1 and goals[0].player_id == 2
    assert "assist_id" not in (goals[0].detail or {})


def test_assist_network_pairs_and_leaders():
    """Két gól, mindkettőt az 1-es passzolja a 2-esnek → egy pár (2 gól),
    az 1-es a gólpassz-vezér."""
    from handball.pipeline.event_detection import assist_network
    frames = []
    t = 0
    for _ in range(2):
        # passz 1→2, majd a 2-es gólja a +x kapura
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 25.0, 10.0),
                                          _pl(2, Team.HOME, 30.0, 10.0)],
                            ball=Ball(x=25.0, y=10.0, confidence=1.0)))
        t += 1
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 25.0, 10.0),
                                          _pl(2, Team.HOME, 30.0, 10.0)],
                            ball=Ball(x=30.0, y=10.0, confidence=1.0)))
        t += 1
        for _ in range(3):   # a labda a lövő kezében (elengedés előtt)
            frames.append(Frame(t=t, players=[_pl(2, Team.HOME, 33.0, 10.0)],
                                ball=Ball(x=33.2, y=10.0, confidence=1.0)))
            t += 1
        for i in range(7):
            frames.append(Frame(t=t, players=[_pl(2, Team.HOME, 33.0, 10.0)],
                                ball=Ball(x=34.0 + i, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(20):
            frames.append(Frame(t=t, players=[], ball=Ball(x=20.0, y=10.0,
                                                          confidence=1.0)))
            t += 1
    net = assist_network(Match(_meta(), frames))["home"]
    assert net["pairs"] and net["pairs"][0]["from"] == 1
    assert net["pairs"][0]["to"] == 2 and net["pairs"][0]["goals"] == 2
    assert net["leaders"][0]["player_id"] == 1 and net["leaders"][0]["assists"] == 2


# ---- Hoki-assziszt (a gólpassz előtti passz) --------------------------------


def _prea_frames(n, with_pre=True):
    """`n` hazai gól: passz 3→1 (másod-előkészítés, ha `with_pre`),
    majd passz 1→2, és a 2-es gólja a +x kapura."""
    frames = []
    t = 0
    for _ in range(n):
        cast = [_pl(3, Team.HOME, 20.0, 10.0),
                _pl(1, Team.HOME, 25.0, 10.0),
                _pl(2, Team.HOME, 30.0, 10.0)]
        if with_pre:
            frames.append(Frame(t=t, players=cast,
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
            t += 1
        frames.append(Frame(t=t, players=cast,
                            ball=Ball(x=25.0, y=10.0, confidence=1.0)))
        t += 1
        frames.append(Frame(t=t, players=cast,
                            ball=Ball(x=25.0, y=10.0, confidence=1.0)))
        t += 1
        frames.append(Frame(t=t, players=cast,
                            ball=Ball(x=30.0, y=10.0, confidence=1.0)))
        t += 1
        for _ in range(3):
            frames.append(Frame(t=t, players=[_pl(2, Team.HOME, 33.0, 10.0)],
                                ball=Ball(x=33.2, y=10.0, confidence=1.0)))
            t += 1
        for i in range(7):
            frames.append(Frame(t=t, players=[_pl(2, Team.HOME, 33.0, 10.0)],
                                ball=Ball(x=34.0 + i, y=10.0,
                                          confidence=1.0)))
            t += 1
        # Középkezdés: a labda az ELLENFÉLHEZ kerül (mint élesben) — a
        # két hazai támadás közt így nincs hamis csapaton belüli passz.
        for _ in range(10):
            frames.append(Frame(t=t, players=[_pl(30, Team.AWAY,
                                                  20.0, 10.0)],
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(10):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=15.0, y=10.0, confidence=1.0)))
            t += 1
    return frames


def _prear_match(n):
    """Mint a _prea_frames, de a 3-as (másod-előkészítő) poszt-becsléshez
    elegendő mért kockát kap a beálló helyén (34, 10) — a réteg így
    posztra tudja írni a másod-előkészítéseit."""
    frames = []
    t = 0
    for _ in range(160):     # poszt-minta: a 3-as a vonalon, labda nála
        frames.append(Frame(t=t, players=[
            _pl(3, Team.HOME, 34.0, 10.0),
            _pl(1, Team.HOME, 30.0, 14.0),
            _pl(2, Team.HOME, 30.0, 6.0)],
            ball=Ball(x=34.2, y=10.0, confidence=1.0)))
        t += 1
    tail = _prea_frames(n)
    for f in tail:
        f.t += t
    return Match(_meta(), frames + tail)


def test_pre_assist_roles_names_the_organizing_post():
    """Ha a másod-előkészítések zöme egy posztról jön, a szervezésük
    posztról olvasható — a sáv-zárás a posztra megy, akárki játssza."""
    from handball.pipeline.event_detection import pre_assist_roles

    rec = pre_assist_roles(_prear_match(3))["home"]
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "poszton fut" in rec["verdict"], rec


def test_pre_assist_roles_silent_with_few_chains():
    """Kevés poszthoz kötött másod-előkészítésnél nincs ítélet."""
    from handball.pipeline.event_detection import pre_assist_roles

    rec = pre_assist_roles(_prear_match(2))["home"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


def test_pre_assists_names_the_hidden_organizer():
    """A 3→1→2→gól láncban a 3-as a rejtett szervező: ő adja a gólpassz
    előtti passzt."""
    from handball.pipeline.event_detection import PREA_MIN, pre_assists

    rec = pre_assists(Match(_meta(), _prea_frames(2)))["home"]
    assert rec["assisted_goals"] == 2 and rec["chained"] == 2, rec
    assert rec["top"] is not None and rec["top"]["player_id"] == 3, rec
    assert rec["top"]["pre_assists"] >= PREA_MIN

    # A gólpasszoló (1-es) és a lövő (2-es) NEM másod-előkészítő.
    pids = [p["player_id"] for p in rec["players"]]
    assert 1 not in pids and 2 not in pids, rec


def test_pre_assists_silent_without_a_chain():
    """Ha a gólpassz előtt nincs korábbi passz (kétszemélyes akció),
    nincs lánc — és kevés mintánál nincs ítélet."""
    from handball.pipeline.event_detection import pre_assists

    rec = pre_assists(Match(_meta(), _prea_frames(2,
                                                  with_pre=False)))["home"]
    assert rec["assisted_goals"] == 2, rec
    assert rec["chained"] == 0 and rec["top"] is None, rec

    egy = pre_assists(Match(_meta(), _prea_frames(1)))["home"]
    assert egy["chained"] == 1 and egy["top"] is None, egy


def _adu_frames(n_pairs):
    """`n_pairs` darab 1→2 asszisztos hazai gól kockái."""
    frames = []
    t = 0
    for _ in range(n_pairs):
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 25.0, 10.0),
                                          _pl(2, Team.HOME, 30.0, 10.0)],
                            ball=Ball(x=25.0, y=10.0, confidence=1.0)))
        t += 1
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 25.0, 10.0),
                                          _pl(2, Team.HOME, 30.0, 10.0)],
                            ball=Ball(x=30.0, y=10.0, confidence=1.0)))
        t += 1
        for _ in range(3):
            frames.append(Frame(t=t, players=[_pl(2, Team.HOME, 33.0, 10.0)],
                                ball=Ball(x=33.2, y=10.0, confidence=1.0)))
            t += 1
        for i in range(7):
            frames.append(Frame(t=t, players=[_pl(2, Team.HOME, 33.0, 10.0)],
                                ball=Ball(x=34.0 + i, y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(20):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
            t += 1
    return frames


def test_assist_duos_names_the_goal_machine():
    """Ha az asszisztos gólok egy kettősön születnek, a duó ellen
    párban kell védekezni."""
    from handball.pipeline.event_detection import (ADU_MIN_GOALS,
                                                   assist_duos)

    rec = assist_duos(Match(_meta(), _adu_frames(2)))["home"]
    assert rec["assisted"] >= ADU_MIN_GOALS, rec
    assert rec["top"] == "1→2", rec
    assert rec["verdict"] and "párban kell védekezni" in rec["verdict"], rec


def test_assist_duos_silent_with_one_goal():
    """Egyetlen asszisztos gólból nincs ítélet."""
    from handball.pipeline.event_detection import assist_duos

    rec = assist_duos(Match(_meta(), _adu_frames(1)))["home"]
    assert rec["top"] is None and rec["verdict"] is None, rec


def test_goal_concentration_top_share():
    """6 hazai gólból 4-et az 1-es szerez (67%) → koncentrált gólszerzés;
    kevés gólnál (vendég: 0) nincs ítélet."""
    from handball.pipeline.event_detection import goal_concentration

    def goal(t0, shooter):
        fr = [Frame(t=t0 + i, players=[_pl(shooter, Team.HOME, 33.0, 10.0)],
                    ball=Ball(x=33.0, y=10.0, confidence=1.0))
              for i in range(3)]
        for i in range(8):
            fr.append(Frame(t=t0 + 3 + i,
                            players=[_pl(shooter, Team.HOME, 33.0, 10.0)],
                            ball=Ball(x=min(34.0 + i, 40.0), y=10.0,
                                      confidence=1.0)))
        return fr

    frames = []
    for shooter in (1, 1, 1, 1, 2, 3):
        frames += goal(len(frames), shooter)
        t = len(frames)
        for i in range(20):  # szünet a debounce-nak
            frames.append(Frame(t=t + i, players=[],
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))

    gc = goal_concentration(Match(_meta(), frames))
    h = gc["home"]
    assert h["goals"] == 6
    assert h["scorers"][0]["player_id"] == 1 and h["scorers"][0]["goals"] == 4
    assert h["top_share_pct"] is not None and h["top_share_pct"] >= 40.0
    assert h["concentrated"] is True
    assert gc["away"]["goals"] == 0 and gc["away"]["concentrated"] is None


def test_shot_speeds_measures_ball_velocity():
    """1 m/kocka a kapu felé 25 fps-en = 25 m/s = 90 km/h."""
    from handball.pipeline.event_detection import shot_speeds
    frames = []
    for i in range(8):
        frames.append(Frame(t=i, players=[_pl(1, Team.HOME, 33.0, 10.0)],
                            ball=Ball(x=34.0 + i, y=10.0, confidence=1.0)))
    r = shot_speeds(Match(_meta(), frames))
    assert len(r["shots"]) == 1
    assert abs(r["shots"][0]["speed_kmh"] - 90.0) < 2.0
    assert r["teams"]["home"]["n"] == 1
    assert abs(r["teams"]["home"]["max_kmh"] - 90.0) < 2.0
    assert r["fastest"]["team"] == "home"
    assert r["teams"]["away"]["n"] == 0


def test_shot_speed_fade_second_half_drop():
    """Az 1. félidőben gyors (~144 km/h), a 2.-ban lassú (~45 km/h) lövések:
    a lövőerő-esés kimutatja a százalékos lassulást; félidő-jel nélkül None."""
    from handball.pipeline.event_detection import shot_speed_fade

    fps = 25.0

    def idle(t0, seconds):
        # Aktív "állójáték": 6 mért játékos + labda középen — a félidő-
        # érzékelő ezt NEM látja szünetnek.
        fr = []
        for i in range(int(seconds * fps)):
            fr.append(Frame(t=t0 + i,
                            players=[_pl(10 + k, Team.HOME, 15.0 + k, 6.0 + k)
                                     for k in range(6)],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        return fr

    def shot(t0, step):
        # Egy hazai lövés a +x kapura: a labda `step` m/kockával repül.
        fr = [Frame(t=t0 + i, players=[_pl(1, Team.HOME, 33.0, 10.0)],
                    ball=Ball(x=33.0, y=10.0, confidence=1.0))
              for i in range(3)]
        for i in range(8):
            bx = min(33.0 + step * (i + 1), 40.0)
            fr.append(Frame(t=t0 + 3 + i, players=[_pl(1, Team.HOME, 33.0, 10.0)],
                            ball=Ball(x=bx, y=10.0, confidence=1.0)))
        return fr

    frames = []
    # 1. félidő: 3 gyors lövés (1,6 m/kocka = 40 m/s = 144 km/h) állójátékkal.
    for _ in range(3):
        frames += idle(len(frames), 20)
        frames += shot(len(frames), 1.6)
    frames += idle(len(frames), 15)
    # Szünet: 90 mp üres pálya a felvétel közepén.
    frames += [Frame(t=len(frames) + i, players=[], ball=None)
               for i in range(int(90 * fps))]
    # 2. félidő: 3 lassú lövés (0,5 m/kocka = 12,5 m/s = 45 km/h).
    for _ in range(3):
        frames += idle(len(frames), 20)
        frames += shot(len(frames), 0.5)
    frames += idle(len(frames), 15)

    m = Match(_meta(), frames)
    fade = shot_speed_fade(m)
    h = fade["home"]
    assert h["fh_n"] == 3 and h["sh_n"] == 3
    assert h["fh_avg_kmh"] > h["sh_avg_kmh"]
    assert h["drop_pct"] is not None and h["drop_pct"] >= 8.0
    # A vendég nem lőtt — nincs ítélet.
    assert fade["away"]["drop_pct"] is None
    # Félidő-jel nélkül (rövid, szünet nélküli felvétel) nincs ítélet.
    short = Match(_meta(), shot(0, 1.6))
    assert shot_speed_fade(short)["home"]["drop_pct"] is None


def test_pass_length_short_vs_long():
    """16 passz egy 5 m-es és egy 12 m-es cél közt felváltva → ~8,5 m átlag,
    50% hosszú-arány; kevés passznál nincs ítélet."""
    from handball.pipeline.event_detection import pass_length

    frames = []
    t = 0
    pos = {1: (20.0, 10.0), 2: (25.0, 10.0), 3: (20.0, 10.0)}
    # 1→2 rövid (5 m), 2→1 rövid, 1→3... a 3-as 12 m-re: hosszú váltások.
    seq = []
    for _ in range(8):
        seq += [(1, 2), (2, 1)]      # rövid oda-vissza
    long_pos = {1: (20.0, 10.0), 4: (32.0, 10.0)}
    for _ in range(8):
        seq += [(1, 4), (4, 1)]      # hosszú oda-vissza (12 m)
    # Rövid szakasz.
    cur = {1: (20.0, 10.0), 2: (25.0, 10.0)}
    for (frm, to) in seq[:16]:
        for _ in range(3):
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, *cur[1]), _pl(2, Team.HOME, *cur[2])],
                ball=Ball(x=cur[frm][0], y=cur[frm][1], confidence=1.0)))
            t += 1
    # Hosszú szakasz.
    for (frm, to) in seq[16:]:
        for _ in range(3):
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, *long_pos[1]), _pl(4, Team.HOME,
                                                     *long_pos[4])],
                ball=Ball(x=long_pos[frm][0], y=long_pos[frm][1],
                          confidence=1.0)))
            t += 1

    pl_ = pass_length(Match(_meta(), frames))
    h = pl_["home"]
    assert h["passes"] >= 15
    assert h["avg_m"] is not None and 5.0 < h["avg_m"] < 12.0
    assert h["long_passes"] >= 8
    assert h["long_pct"] is not None and h["long_pct"] >= 30.0
    # A vendégnek nincs passza → nincs ítélet.
    assert pl_["away"]["avg_m"] is None


def test_pass_network_pairs_and_hubs():
    """3 passz 1→2 és 1 passz 2→3: a fő pár az 1→2, a hub az 1-es vagy
    a 2-es (mindkettő 4 passzban érintett — a 2-esé: 3 kapott + 1 adott)."""
    from handball.pipeline.event_detection import pass_network
    frames = []
    t = 0
    for _ in range(3):
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 25.0, 10.0),
                                          _pl(2, Team.HOME, 30.0, 10.0)],
                            ball=Ball(x=25.0, y=10.0, confidence=1.0)))
        t += 1
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 25.0, 10.0),
                                          _pl(2, Team.HOME, 30.0, 10.0)],
                            ball=Ball(x=30.0, y=10.0, confidence=1.0)))
        t += 1
        # vissza az 1-eshez (2→1 passz), hogy újra indulhasson a kör
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 25.0, 10.0),
                                          _pl(2, Team.HOME, 30.0, 10.0)],
                            ball=Ball(x=25.0, y=10.0, confidence=1.0)))
        t += 1
    net = pass_network(Match(_meta(), _hold(frames)))["home"]
    assert net["total_passes"] >= 4
    assert net["pairs"][0]["from"] == 1 and net["pairs"][0]["to"] == 2
    assert net["pairs"][0]["passes"] == 3
    hub_ids = [h["player_id"] for h in net["hubs"]]
    assert 1 in hub_ids and 2 in hub_ids
    # A vendégnek nincs passza.
    away = pass_network(Match(_meta(), frames))["away"]
    assert away["total_passes"] == 0 and away["pairs"] == []


def test_shooter_power_names_the_cannon():
    """Az 1-es hazai lövő négy lövése ~144 km/h, a 2-esé ~72 km/h → az
    1-es a bombázó; kevés mért lövésnél nincs megnevezett játékos."""
    from handball.pipeline.event_detection import shooter_power

    frames = []
    t = 0

    def _shot(pid, step):
        """A pid-es hazai lövő lövése: a labda `step` m/kocka tempóban
        halad a +x kapu felé (25 fps → step * 90 km/h)."""
        nonlocal t, frames
        shooter = [_pl(pid, Team.HOME, 33.0, 10.0)]
        for _ in range(3):   # a labda a lövő kezében (elengedés előtt)
            frames.append(Frame(t=t, players=shooter,
                                ball=Ball(x=33.2, y=10.0, confidence=1.0)))
            t += 1
        for i in range(8):
            frames.append(Frame(t=t, players=shooter,
                                ball=Ball(x=min(34.0 + step * i, 40.0),
                                          y=10.0, confidence=1.0)))
            t += 1
        for _ in range(40):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    for _ in range(4):
        _shot(1, 1.6)     # ~144 km/h
    for _ in range(4):
        _shot(2, 0.8)     # ~72 km/h

    spw = shooter_power(Match(_meta(), frames))
    h = spw["home"]
    cannon = h["cannon"]
    assert cannon is not None and cannon["player_id"] == 1
    assert cannon["shots"] == 4 and cannon["avg_kmh"] > h["avg_kmh"]
    # A lassabb lövő is a listában van, de nem ő a bombázó.
    slow = next(p for p in h["players"] if p["player_id"] == 2)
    assert slow["avg_kmh"] < cannon["avg_kmh"]

    # Egyetlen lövés: nincs elég minta → nincs megnevezett bombázó.
    few = shooter_power(Match(_meta(), frames[:48]))
    assert few["home"]["cannon"] is None



def _assist_from(px, py, t0):
    """Egy gól kockái: a passzoló (1-es) a (px, py) helyről adja a
    labdát a 2-esnek, aki a +x kapura lő."""
    frames = [
        Frame(t=t0, players=[_pl(1, Team.HOME, px, py),
                             _pl(2, Team.HOME, 33.0, 10.0)],
              ball=Ball(x=px, y=py, confidence=1.0)),
        Frame(t=t0 + 1, players=[_pl(1, Team.HOME, px, py),
                                 _pl(2, Team.HOME, 33.0, 10.0)],
              ball=Ball(x=33.0, y=10.0, confidence=1.0)),   # passz 1→2
    ]
    for k in range(3):   # a labda a lövő kezében (elengedés előtt)
        frames.append(Frame(t=t0 + 2 + k,
                            players=[_pl(1, Team.HOME, px, py),
                                     _pl(2, Team.HOME, 33.0, 10.0)],
                            ball=Ball(x=33.2, y=10.0, confidence=1.0)))
    for i in range(7):   # lövés: 34..40, y=10 → gól
        frames.append(Frame(t=t0 + 5 + i,
                            players=[_pl(1, Team.HOME, px, py),
                                     _pl(2, Team.HOME, 33.0, 10.0)],
                            ball=Ball(x=34.0 + i, y=10.0, confidence=1.0)))
    return frames


def _assist_match(spots):
    """A `spots` (x, y) párokból egy-egy gólpasszos gól, egymás után."""
    frames = []
    t = 0
    for (px, py) in spots:
        frames += _assist_from(px, py, t)
        t = frames[-1].t + 30      # szünet a gólok közt
    return Match(_meta(), frames)


def test_assist_zones_reads_the_wing_line():
    """Négy gólpasszból három a szélről (y=2, illetve y=18) → a szélső
    átadás-vonal a zárandó."""
    from handball.pipeline.event_detection import assist_zones

    rec = assist_zones(_assist_match([(30.0, 2.0), (30.0, 18.0),
                                      (30.0, 2.0), (28.0, 10.0)]))["home"]
    assert rec["assists"] == 4
    assert rec["zones"]["szélről"] == 3
    assert rec["top"] is not None
    assert rec["top"]["zone"] == "szélről" and rec["top"]["goals"] == 3


def test_assist_zones_separates_pivot_and_backcourt():
    """A kapuhoz közeli (9 m-en belüli) középső passz beállós
    kiszolgálás, a távolabbi átlövő-vonalból jön."""
    from handball.pipeline.event_detection import assist_zones

    rec = assist_zones(_assist_match([(34.0, 10.0), (34.0, 11.0),
                                      (24.0, 10.0), (24.0, 9.0)]))["home"]
    assert rec["zones"]["beállótól"] == 2
    assert rec["zones"]["átlövésből"] == 2
    assert rec["top"] is None          # nincs 50%-ot elérő vezető zóna


def test_assist_zones_needs_enough_assists():
    """Kevés (4-nél kevesebb) gólpassznál nincs ítélet."""
    from handball.pipeline.event_detection import assist_zones

    rec = assist_zones(_assist_match([(30.0, 2.0), (30.0, 2.0)]))["home"]
    assert rec["assists"] == 2 and rec["top"] is None


# ---- Gólpassz-hossz (hosszú indítás vagy rövid kombináció) ------------------

def test_assist_ranges_flags_the_long_ball_team():
    """Öt gólpasszból négy 8+ méteres → hosszú gólpasszokból élnek."""
    from handball.pipeline.event_detection import assist_ranges

    rec = assist_ranges(_assist_match(
        [(22.0, 10.0), (24.0, 10.0), (22.0, 16.0), (23.0, 4.0),
         (31.0, 10.0)]))["home"]
    assert rec["assisted"] == 5 and rec["long"] == 4
    assert rec["verdict"] == "hosszú gólpasszokból élnek"


def test_assist_ranges_flags_the_short_combo_team():
    """Öt gólpasszból mind rövid (8 m alatti) → rövid kombinációkból
    élnek."""
    from handball.pipeline.event_detection import assist_ranges

    rec = assist_ranges(_assist_match(
        [(30.0, 10.0), (31.0, 12.0), (29.0, 8.0), (30.0, 13.0),
         (31.5, 10.0)]))["home"]
    assert rec["long"] == 0
    assert rec["verdict"] == "rövid kombinációkból élnek"


def test_assist_ranges_needs_enough_assisted_goals():
    """Kevés (5-nél kevesebb) gólpasszos gólnál nincs ítélet."""
    from handball.pipeline.event_detection import assist_ranges

    rec = assist_ranges(_assist_match(
        [(22.0, 10.0), (24.0, 10.0)]))["home"]
    assert rec["assisted"] == 2 and rec["verdict"] is None


def _pls_pass_frames(t0, x_from, x_to, n):
    """n hazai passz az x_from → x_to álló játékosok közt; a ciklusok
    közé vendég-érintés kerül, hogy ne álljon össze hamis passz."""
    frames = []
    t = t0
    for _ in range(n):
        def both():
            return [_pl(11, Team.HOME, x_from, 10.0),
                    _pl(12, Team.HOME, x_to, 10.0)]
        for _ in range(15):
            frames.append(Frame(t=t, players=both(),
                                ball=Ball(x=x_from, y=10.0,
                                          confidence=1.0)))
            t += 1
        x = x_from
        step = 0.3 if x_to > x_from else -0.3
        while (x < x_to) if x_to > x_from else (x > x_to):
            x += step
            frames.append(Frame(t=t, players=both(),
                                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(15):
            frames.append(Frame(t=t, players=both(),
                                ball=Ball(x=x_to, y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(15):
            frames.append(Frame(t=t,
                                players=[_pl(21, Team.AWAY, 18.0, 10.0)],
                                ball=Ball(x=18.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    return frames, t


def _pls_away_goal_frames(t0):
    """Egy vendég-gól: a lövő (10,10)-ről az x=0 kapuba lő."""
    frames = []
    t = t0
    for _ in range(40):
        frames.append(Frame(t=t, players=[_pl(9, Team.AWAY, 10.0, 10.0)],
                            ball=Ball(x=10.0, y=10.0, confidence=1.0)))
        t += 1
    x = 10.0
    while x > -0.5:
        x -= 0.5
        frames.append(Frame(t=t, players=[_pl(9, Team.AWAY, 10.0, 10.0)],
                            ball=Ball(x=max(x, -0.5), y=10.0,
                                      confidence=1.0)))
        t += 1
    for _ in range(40):
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    return frames, t


def test_pass_length_by_score_flags_long_ball_panic():
    """Döntetlennél rövid (6 m-es) passzok, 3 kapott gól után csupa
    hosszú (12 m-es) → hátrányban hosszú labdákra váltanak."""
    from handball.pipeline.event_detection import pass_length_by_score

    frames, t = _pls_pass_frames(0, 24.0, 30.0, 11)   # rövid, döntetlen
    for _ in range(3):
        gf, t = _pls_away_goal_frames(t)
        frames += gf
    tr, t = _pls_pass_frames(t, 15.0, 27.0, 11)       # hosszú, hátrányban
    frames += tr

    pls = pass_length_by_score(Match(_meta(), frames))
    h = pls["home"]
    assert h["level"]["passes"] >= 10 and h["level"]["long"] == 0
    assert h["trailing"]["passes"] >= 10
    assert h["trailing"]["long"] >= 10
    assert h["verdict"] == "hátrányban hosszú labdákra váltanak"
    assert pls["away"]["verdict"] is None


def test_pass_length_by_score_few_passes_none():
    """Kevés (10-nél kevesebb) passz állapotonként → nincs ítélet."""
    from handball.pipeline.event_detection import pass_length_by_score

    frames, t = _pls_pass_frames(0, 15.0, 27.0, 5)
    pls = pass_length_by_score(Match(_meta(), frames))
    assert pls["home"]["verdict"] is None


def test_shooter_is_the_releasing_player_not_the_nearest_to_goal():
    """A lövő az ELENGEDŐ, nem a kapuhoz legközelebbi játékos.

    Korábban ez fordítva volt (jellemző-tesztként rögzítve): a lövés-
    eseményt a labda kapu-megközelítésekor jelöljük, és a puszta
    "legközelebbi játékos" szabály a röppálya mellett álló beállót
    tette meg lövőnek. A `_shooter_before` most kihagyja azokat a
    kockákat, ahol a labda sebessége lövés-szintű — így az elengedés
    pillanatát találja meg.
    """
    # A távoli játékos (id 3) 12 m-ről engedi el; a közeli (id 1) a
    # kapu előtt, 6 m-en áll, és nem nyúl a labdához.
    frames = []
    t = 0
    players = [
        PlayerPosition(track_id=3, team=Team.HOME, x=28.0, y=10.0,
                       source=PositionSource.MEASURED, confidence=1.0),
        PlayerPosition(track_id=1, team=Team.HOME, x=34.0, y=10.0,
                       source=PositionSource.MEASURED, confidence=1.0),
    ]
    for _ in range(30):          # a távoli játékos birtokol
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=28.0, y=10.0, confidence=1.0)))
        t += 1
    for i in range(1, 14):       # a lövés a kapuba (~1 m/kocka)
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=28.0 + 12.5 * (i / 13.0), y=10.0,
                                      confidence=1.0)))
        t += 1
    match = Match(MatchMeta(match_id="sb", home_team="H", away_team="A",
                            fps=25.0), frames)
    goals = [e for e in detect_shots(match) if e.type == EventType.GOAL]
    assert goals, "a mintajeleneten van gól"
    # A LÖVŐ a 3-as (12 m-ről engedte el); az 1-es csak a kapu előtt áll.
    assert goals[0].player_id == 3, (
        "a lövés a kapuhoz közeli játékoshoz került — visszatért a "
        "kapu-felé torzítás")


# --- Kezesség-becslés (shooting_hand) --------------------------------


def _hand_shot(t0, pid, ball_dy, goals_x=40.0):
    """Egy hazai lövés kockái, a lövő a labdához képest ball_dy-nal:
    a labda a lövő testétől y-ban ennyivel eltolva indul (a dobó kéz
    oldala). A +x kapu felé tart, a kapufák között → gól."""
    frames = []
    sx, sy = 33.0, 10.0
    for i in range(4):
        # Az elengedés ELŐTTI kockán a labda a lövő kezében (eltolva),
        # utána a kapu felé gyorsul.
        bx = sx + (0.0 if i == 0 else 2.0 + 2.0 * i)
        by = sy + (ball_dy if i == 0 else 0.0)
        frames.append(Frame(
            t=t0 + i, players=[_pl(pid, Team.HOME, sx, sy)],
            ball=Ball(x=min(bx, goals_x), y=by, confidence=1.0)))
    return frames


def _hand_match(pid, ball_dy, n):
    """n darab egyforma kezességű lövés egy játékostól, szünetekkel."""
    frames = []
    t = 0
    for _ in range(n):
        frames += _hand_shot(t, pid, ball_dy)
        t += 4
        frames.append(Frame(t=t, players=[_pl(pid, Team.HOME, 20.0, 10.0)],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 20
    return Match(_meta(fps=25.0), frames)


def test_shooting_hand_flags_the_lefty():
    """A kapu felé nézve a labda következetesen a bal kéz oldalán indul
    → balkezes ítélet, és ő a csapat 'lefty'-je."""
    from handball.pipeline.event_detection import shooting_hand

    # Felülnézetben a +x kapu felé forduló lövő bal keze a NAGYOBB y felé
    # esik (mint a térképen kelet felé nézve a bal kéz észak felé).
    m = _hand_match(7, ball_dy=0.5, n=5)
    rec = shooting_hand(m)["home"]
    assert rec["lefty"] is not None
    assert rec["lefty"]["player_id"] == 7
    assert rec["lefty"]["hand"] == "bal"
    assert rec["lefty"]["left"] >= 4


def test_shooting_hand_needs_enough_shots():
    """Kevés lövésből (2) nincs kezesség-ítélet — a jel megvan, de a
    minta kevés (nincs hallgatólagos 'balkezes')."""
    from handball.pipeline.event_detection import shooting_hand

    m = _hand_match(7, ball_dy=0.5, n=2)
    rec = shooting_hand(m)["home"]
    assert rec["lefty"] is None
    assert all(p["hand"] is None for p in rec["players"])


# ---- Gól-felismerés ritkított felvételen (stride) ---------------------------


def _sparse_goal_frames(fps, behind_line=False):
    """Egy hazai lövés RITKA mintavétellel: a labda kockánként ~2,4 m-t
    lép, és a gólvonal 0,7 m-es sávját ÁTUGORJA. `behind_line`: van-e
    minta a vonalon túlról (ha nincs, a követés a vonal előtt szakad
    meg — élesben a hálóba érő labdát a háló kitakarja)."""
    frames = []
    xs = [30.0, 32.4, 34.8, 37.2, 39.6]
    if behind_line:
        xs.append(42.0)
    t = 0
    for _ in range(3):
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 29.8, 10.0)],
                            ball=Ball(x=30.0, y=10.0, confidence=1.0)))
        t += 1
    for x in xs:
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 29.8, 10.0)],
                            ball=Ball(x=x, y=10.0, confidence=1.0)))
        t += 1
    for _ in range(10):   # középkezdés (teleport)
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    return frames


def test_sparse_sampling_goal_is_still_a_goal():
    """A termék alap-ritkításánál (effektív ~8 fps) a labda átugorja a
    gólvonal-sávot — a két minta közti átlépés (vonalon túli mintával)
    és a megszakadó követés előtti extrapoláció (anélkül) is gól."""
    meta = MatchMeta(match_id="sg", home_team="H", away_team="A",
                     fps=8.33)
    crossed = detect_shots(Match(meta, _sparse_goal_frames(
        8.33, behind_line=True)))
    assert [e.type for e in crossed] == [EventType.GOAL], crossed

    vanished = detect_shots(Match(meta, _sparse_goal_frames(
        8.33, behind_line=False)))
    assert [e.type for e in vanished] == [EventType.GOAL], vanished


def test_dense_sampling_keeps_the_old_stopping_shot_a_miss():
    """SŰRŰ (25 fps) felvételen az extrapoláció nem él: a vonal előtt
    megálló, majd eltűnő labda továbbra sem gól — a sűrű mintavételnél
    a valódi gólt a sáv- vagy az átlépés-jel úgyis megfogja."""
    frames = []
    t = 0
    for _ in range(3):
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 33.0, 10.0)],
                            ball=Ball(x=33.2, y=10.0, confidence=1.0)))
        t += 1
    for x in (34.0, 35.0, 36.0, 37.0, 38.0, 39.0):  # megáll a vonal előtt
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 33.0, 10.0)],
                            ball=Ball(x=x, y=10.0, confidence=1.0)))
        t += 1
    for _ in range(10):
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    evs = detect_shots(Match(_meta(), frames))
    assert [e.type for e in evs] == [EventType.SHOT], evs
    assert (evs[0].detail or {}).get("outcome") != "goal"


def test_sparse_one_timer_shooter_is_the_kink_player():
    """Ritkított felvételen az EGYÜTEMŰ (elkapásból azonnali) lövésnél a
    labda kézben-tartott kockája eltűnhet a minták közül — a régi
    szabály ilyenkor a PASSZOLÓT nevezné lövőnek. A röppálya
    töréspontja (passz-szár → lövés-szár) melletti játékos a lövő."""
    from handball.pipeline.event_detection import EventType, detect_shots

    fps = 8.33
    frames = []
    t = 0
    # A 6-os (passzoló) középen tartja a labdát, a 2-es szélső lent áll.
    for _ in range(4):
        frames.append(Frame(t=t, players=[
            _pl(6, Team.HOME, 28.0, 10.0), _pl(2, Team.HOME, 36.0, 3.0)],
            ball=Ball(x=28.2, y=10.0, confidence=1.0)))
        t += 1
    # Passz-szár: a labda a szélső felé repül (két gyors minta), majd
    # lövés-szár: a szélsőtől a kapuba — kézben-tartott kocka NINCS.
    path = [(31.0, 7.5), (34.0, 4.5), (36.0, 3.0),   # passz a 2-eshez
            (38.0, 6.5), (40.0, 10.0)]               # együtemű lövés
    for x, y in path:
        frames.append(Frame(t=t, players=[
            _pl(6, Team.HOME, 28.0, 10.0), _pl(2, Team.HOME, 36.0, 3.0)],
            ball=Ball(x=x, y=y, confidence=1.0)))
        t += 1
    for _ in range(6):    # középkezdés
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    m = Match(MatchMeta(match_id="kink", home_team="H", away_team="A",
                        fps=fps), frames)
    evs = [e for e in detect_shots(m)
           if e.type in (EventType.SHOT, EventType.GOAL)]
    assert len(evs) == 1, evs
    assert evs[0].player_id == 2, evs[0]  # a szélső, nem a passzoló


def test_lovest_nem_ismetel_a_csendidon_belul():
    """Zaj-sorozatból EGY lövés lesz, nem négy.

    Éles meccsen a hibás pálya-vetítés miatt a labda ki-be billegett a
    kapu-zóna szélén, és egyetlen lövésből négy esemény lett (1264,6 /
    1265,9 / 1266,3 / 1267,1 mp). A hely-alapú debounce ezt nem fogja
    meg — a csendidő igen.
    """
    from handball.pipeline.event_detection import (EventType,
                                                   SHOT_COOLDOWN_S,
                                                   detect_shots)

    fps = 25.0
    frames = []
    t = 0
    # Négy egymást követő "kapu-megközelítés", köztük rövid kilépéssel a
    # zónából — tehát a hely-alapú debounce mindegyiket átengedné.
    for _ in range(4):
        for i in range(4):
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 33.0, 10.0)],
                                ball=Ball(x=34.0 + i, y=10.0,
                                          confidence=1.0)))
            t += 1
        for i in range(2):   # kilépés a zónából (x < 35 m), rövid ideig
            frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 33.0, 10.0)],
                                ball=Ball(x=33.0, y=10.0, confidence=1.0)))
            t += 1

    ev = [e for e in detect_shots(Match(_meta(fps=fps), frames))
          if e.type in (EventType.SHOT, EventType.GOAL)]
    # A négy jelölt összesen ~1 másodpercen belül van: egy eseménnyé olvad.
    assert len(ev) == 1, [e.t for e in ev]
    assert SHOT_COOLDOWN_S > 0


def test_a_csendido_utan_uj_loves_johet():
    """A csendidő nem nyeli el a KÉSŐBBI, valódi lövést."""
    from handball.pipeline.event_detection import (EventType,
                                                   SHOT_COOLDOWN_S,
                                                   detect_shots)

    fps = 25.0

    def megkozelites(t0):
        fr = []
        for i in range(4):
            fr.append(Frame(t=t0 + i, players=[_pl(1, Team.HOME, 33.0, 10.0)],
                            ball=Ball(x=34.0 + i, y=10.0, confidence=1.0)))
        return fr

    frames = megkozelites(0)
    t = len(frames)
    # Bőven a csendidőn túl (és a zónán kívül) — ez külön lövés.
    varakozas = int(SHOT_COOLDOWN_S * fps) + 20
    for i in range(varakozas):
        frames.append(Frame(t=t + i, players=[_pl(1, Team.HOME, 20.0, 10.0)],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    frames += megkozelites(t + varakozas)

    ev = [e for e in detect_shots(Match(_meta(fps=fps), frames))
          if e.type in (EventType.SHOT, EventType.GOAL)]
    assert len(ev) == 2, [e.t for e in ev]


def test_eladott_labda_nem_szuletik_billegesbol():
    """Kockánként átbillenő birtokos NEM eladott labda.

    A birtokos a labdához legközelebbi játékos. Tömörülésnél (elzárás,
    beállós harc) és ritka labda-észlelésnél két SZEMBEN álló ember
    távolsága kockánként átbillen — éles meccsen ez a meccs ELŐTTI
    felállásnál is eladásokat termelt, miközben senki nem játszott.
    """
    frames = []
    for t in range(200):
        # A labda áll; a két játékos felváltva a legközelebbi hozzá.
        kozel, tavol = ((10.6, 13.0) if t % 2 == 0 else (13.0, 10.6))
        frames.append(Frame(
            t=t,
            players=[_pl(1, Team.HOME, kozel, 10.0),
                     _pl(11, Team.AWAY, tavol, 10.0)],
            ball=Ball(x=11.0, y=10.0, confidence=1.0)))
    evs = detect_possession_changes(Match(_meta(), frames))
    eladas = [e for e in evs if e.type == EventType.TURNOVER]
    assert eladas == [], [e.t for e in eladas]


def test_valodi_eladott_labda_megmarad():
    """A kitartó csapatváltás továbbra is eladott labda."""
    from handball.pipeline.event_detection import TURNOVER_MIN_HOLD_S

    fps = 25.0
    tart = int(TURNOVER_MIN_HOLD_S * fps) + 5
    frames = []
    t = 0
    for _ in range(tart):   # a hazai birtokolja
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 10.6, 10.0),
                                          _pl(11, Team.AWAY, 13.0, 10.0)],
                            ball=Ball(x=11.0, y=10.0, confidence=1.0)))
        t += 1
    for _ in range(tart):   # majd tartósan a vendég
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 13.0, 10.0),
                                          _pl(11, Team.AWAY, 10.6, 10.0)],
                            ball=Ball(x=11.0, y=10.0, confidence=1.0)))
        t += 1
    evs = detect_possession_changes(Match(_meta(fps=fps), frames))
    eladas = [e for e in evs if e.type == EventType.TURNOVER]
    assert len(eladas) == 1, [e.t for e in eladas]
    assert eladas[0].team == Team.HOME       # a HAZAI vesztette el
    assert eladas[0].player_id == 1


def test_csapaton_beluli_passz_valtozatlan():
    """A passzra NEM vonatkozik a kitartás-követelmény.

    A csapaton belüli birtokosváltás kisebb állítás (a labda nem hagyta
    el a csapatot), és a passz-alapú rétegek a régi viselkedésre
    épülnek — ezt szándékosan nem bántjuk.
    """
    frames = [
        Frame(t=0, players=[_pl(1, Team.HOME, 25.0, 10.0)],
              ball=Ball(x=25.0, y=10.0, confidence=1.0)),
        Frame(t=1, players=[_pl(2, Team.HOME, 28.0, 10.0)],
              ball=Ball(x=28.0, y=10.0, confidence=1.0)),
    ]
    evs = detect_possession_changes(Match(_meta(), frames))
    assert [e.type for e in evs] == [EventType.PASS]


def test_a_masik_csapat_passzai_nem_nyelik_el_a_szerzest():
    """A kitartást a CSAPATRA mérjük, nem az egyes játékosra.

    Ha az ellenfél megszerzi a labdát, és rögtön TOVÁBB is passzolja a
    társának, a labda attól még náluk van: a szerzés valódi. Ha a
    kitartást játékosonként néznénk, az ő passzaik elnyelnék a
    jelöltet, és a labdaszerzés sosem születne meg.
    """
    frames = []
    t = 0
    for _ in range(12):     # a hazai birtokol
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 20.0, 10.0)],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    for pid in (11, 12, 13):   # a vendégek egymásnak adogatnak, 5-5 kocka
        for _ in range(5):
            frames.append(Frame(t=t, players=[_pl(pid, Team.AWAY, 20.0, 10.0)],
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
            t += 1
    evs = detect_possession_changes(Match(_meta(), frames))
    eladas = [e for e in evs if e.type == EventType.TURNOVER]
    passzok = [e for e in evs if e.type == EventType.PASS]
    assert len(eladas) == 1 and eladas[0].team == Team.HOME
    assert len(passzok) == 2      # 11→12 és 12→13


def test_a_felvetel_elejen_allo_villanasbol_nincs_eladas():
    """Egy-kockás nyitó villanásból ne írjunk labdavesztést senki nevére.

    A felvétel SZÉLEIN álló rövid futam sosem igazolja magát: nincs
    mellette mindkét oldalon szomszéd, ami megerősítené. A végén álló
    villanásból labdaSZERZÉST, az elején állóból labdaVESZTÉST nem
    csinálunk.
    """
    frames = []
    t = 0
    # Egyetlen kocka a hazaié...
    frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 20.0, 10.0)],
                        ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    t += 1
    # ...aztán tartósan a vendégé.
    for _ in range(30):
        frames.append(Frame(t=t, players=[_pl(11, Team.AWAY, 20.0, 10.0)],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    evs = detect_possession_changes(Match(_meta(), frames))
    assert [e for e in evs if e.type == EventType.TURNOVER] == []


# ---- A gólvonal-átlépés y-ja (goal_crossing_y) -------------------------------

def _labda_match(pontok, fps=25.0):
    """Kockánként egy labda-pont (None = nem látszik), játékos nélkül."""
    return Match(_meta(fps), [
        Frame(t=i, players=[],
              ball=None if p is None else Ball(x=p[0], y=p[1],
                                               confidence=1.0))
        for i, p in enumerate(pontok)])


def test_goal_crossing_y_minta_a_golvonal_savjaban():
    """1. jel: a labda egy mintán a gólvonal 0,7 m-es sávjában, a kapufák
    (8,5–11,5) között van → az a minta y-ja; mindkét kapura."""
    from handball.pipeline.event_detection import goal_crossing_y

    plusz = _labda_match([(36.0, 9.5), (38.0, 9.5), (39.6, 9.5)])
    assert goal_crossing_y(plusz, 0, 40.0) == 9.5
    minusz = _labda_match([(4.0, 11.0), (2.0, 11.0), (0.5, 11.0)])
    assert goal_crossing_y(minusz, 0, 0.0) == 11.0
    # Ugyanaz a labda a MÁSIK kapuhoz nem ért oda.
    assert goal_crossing_y(plusz, 0, 0.0) is None


def test_goal_crossing_y_ket_minta_kozti_atlepes_metszespontja():
    """2. jel: a sávot átugró labdánál a két minta közti szakasz és a
    gólvonal METSZÉSPONTJA számít — nem a vonalon túli minta y-ja."""
    from handball.pipeline.event_detection import goal_crossing_y

    m = _labda_match([(37.6, 8.6), (39.2, 9.0), (40.8, 9.4)])
    assert abs(goal_crossing_y(m, 1, 40.0) - 9.2) < 1e-9
    # Ritkított felvételen (harmad-fps) a labda kockánként métereket
    # lép: a metszéspont ott is a tényleges beérkezési pont.
    ritka = _labda_match([(32.0, 9.0), (37.0, 9.5), (42.0, 10.0)],
                         fps=25.0 / 3.0)
    assert abs(goal_crossing_y(ritka, 1, 40.0) - 9.8) < 1e-9


def test_goal_crossing_y_none_ha_melle_megy_vagy_nem_er_oda():
    """A kapufákon kívüli átlépés, a vonalat el nem érő labda, a
    detektálási ugrás (45 m/s fölötti "átlépés") és a labda nélküli
    szakasz nem gól-átlépés: None."""
    from handball.pipeline.event_detection import goal_crossing_y

    melle = _labda_match([(37.6, 5.0), (39.2, 5.0), (40.8, 5.0)])
    assert goal_crossing_y(melle, 1, 40.0) is None
    # A sávba eső, de a kapufán kívüli minta sem az (y = 12 > 11,5).
    kapufa = _labda_match([(38.0, 12.0), (39.6, 12.0)])
    assert goal_crossing_y(kapufa, 0, 40.0) is None
    nem_er_oda = _labda_match([(30.0, 10.0), (31.0, 10.0), (32.0, 10.0)])
    assert goal_crossing_y(nem_er_oda, 0, 40.0) is None
    ugras = _labda_match([(30.0, 10.0), (30.5, 10.0), (41.0, 10.0)])
    assert goal_crossing_y(ugras, 1, 40.0) is None
    nincs_labda = _labda_match([None, None, None])
    assert goal_crossing_y(nincs_labda, 0, 40.0) is None
    # Az ablakon (a meccs végén) túli index: üres ablak → None.
    assert goal_crossing_y(nem_er_oda, 3, 40.0) is None


def test_goal_crossing_y_csak_az_elorenezes_ablakaban_keres():
    """A góldöntés 0,48 mp-et (25 fps-en 12 kockát) néz előre: a később
    beérő labda már nem ehhez a lövéshez tartozik."""
    from handball.pipeline.event_detection import (goal_crossing_y,
                                                   goal_lookahead_frames)

    m = _labda_match([(30.0, 10.0)] * 20 + [(39.8, 10.0)])
    assert goal_lookahead_frames(m) == 12
    assert goal_crossing_y(m, 0, 40.0) is None
    assert goal_crossing_y(m, 10, 40.0) == 10.0


def test_goal_crossing_y_megszakado_kovetesnel_extrapolal_ritkitva():
    """3. jel (csak ritkított felvételen): a kapu felé tartó labda a
    vonal előtt egy lépésnyire jár, és a követés megszakad (a háló
    kitakarja) → az utolsó sebességgel extrapolált metszéspont. Ha a
    követés folytonosan megy tovább (láttuk volna a gólt), nem szól."""
    from handball.pipeline.event_detection import (GOAL_EXTRAP_MAX_FPS,
                                                   goal_crossing_y)

    fps = 25.0 / 3.0
    megszakad = _labda_match([(33.0, 10.0), (36.5, 10.2), None], fps=fps)
    assert abs(goal_crossing_y(megszakad, 1, 40.0) - 10.4) < 1e-9
    # A felvétel vége is követés-szakadás.
    vege = _labda_match([(33.0, 10.0), (36.5, 10.2)], fps=fps)
    assert abs(goal_crossing_y(vege, 1, 40.0) - 10.4) < 1e-9
    # Teleport a középkezdéshez: az is szakadás.
    teleport = _labda_match([(33.0, 10.0), (36.5, 10.2), (20.0, 10.0)],
                            fps=fps)
    assert abs(goal_crossing_y(teleport, 1, 40.0) - 10.4) < 1e-9
    # Folytonos követés (a labda lelassult — védés): nincs extrapoláció.
    folytonos = _labda_match([(33.0, 10.0), (36.5, 10.2), (38.0, 10.3)],
                             fps=fps)
    assert goal_crossing_y(folytonos, 1, 40.0) is None
    # Az extrapolált pont a kapufán kívülre esik → nem gól.
    kivul = _labda_match([(33.0, 10.0), (36.5, 11.4), None], fps=fps)
    assert goal_crossing_y(kivul, 1, 40.0) is None
    # Sűrű felvételen (a küszöb fölött) a 3. jel nem él.
    assert 25.0 >= GOAL_EXTRAP_MAX_FPS
    suru = _labda_match([(38.0, 10.0), (39.2, 10.0), None], fps=25.0)
    assert goal_crossing_y(suru, 1, 40.0) is None
    kozepes = _labda_match([(38.0, 10.0), (39.2, 10.0), None], fps=12.0)
    assert goal_crossing_y(kozepes, 1, 40.0) == 10.0


# ---- Gólpassz (annotate_assists) ----------------------------------------------

def _ev(t, tipus, team=Team.HOME, player=None, detail=None):
    from handball.pipeline.event_detection import MatchEvent
    return MatchEvent(t=t, type=tipus, team=team, player_id=player,
                      detail=detail)


def test_annotate_assists_az_utolso_passz_a_lovonek():
    """A gól előtti 4 mp-ben az UTOLSÓ saját passz, amelynek fogadója a
    lövő, a gólpassz: a gól detail-jébe kerül, a meglévő mezők mellé."""
    from handball.pipeline.event_detection import annotate_assists

    m = Match(_meta(), [])
    events = [
        _ev(20, EventType.PASS, player=3, detail={"receiver_id": 1}),
        _ev(60, EventType.PASS, player=2, detail={"receiver_id": 1}),
        _ev(100, EventType.GOAL, player=1, detail={"outcome": "goal"}),
    ]
    ki = annotate_assists(m, events)
    assert ki is events
    assert events[2].detail == {"outcome": "goal", "assist_id": 2}
    # A passz-események változatlanok.
    assert events[0].detail == {"receiver_id": 1}
    assert events[1].detail == {"receiver_id": 1}


def test_annotate_assists_detail_nelkuli_golra_is_beir():
    """A detail nélküli (None) gól is megkapja a gólpasszt."""
    from handball.pipeline.event_detection import annotate_assists

    events = [_ev(60, EventType.PASS, player=2, detail={"receiver_id": 1}),
              _ev(100, EventType.GOAL, player=1)]
    annotate_assists(Match(_meta(), []), events)
    assert events[1].detail == {"assist_id": 2}


def test_annotate_assists_nincs_golpassz_ha_nem_illik():
    """Nincs gólpassz, ha a passz az ablakon kívül esik, az ellenfélé,
    másnak szólt, a gól UTÁN történt, önmagának szól (track-zaj), vagy
    a gól lövője ismeretlen; a kihagyott lövés sosem kap gólpasszt."""
    from handball.pipeline.event_detection import (ASSIST_WINDOW_S,
                                                   annotate_assists)

    m = Match(_meta(), [])
    hatar = int(ASSIST_WINDOW_S * 25.0)          # 100 kocka

    def gol_detail(passz, gol=None):
        gol = gol or _ev(200, EventType.GOAL, player=1)
        annotate_assists(m, [passz, gol])
        return gol.detail

    # Pont az ablak szélén még gólpassz, egy kockával korábban már nem.
    assert gol_detail(_ev(200 - hatar, EventType.PASS, player=2,
                          detail={"receiver_id": 1})) == {"assist_id": 2}
    assert gol_detail(_ev(200 - hatar - 1, EventType.PASS, player=2,
                          detail={"receiver_id": 1})) is None
    # Az ellenfél passza.
    assert gol_detail(_ev(190, EventType.PASS, team=Team.AWAY, player=12,
                          detail={"receiver_id": 1})) is None
    # Másnak szólt / nincs fogadó.
    assert gol_detail(_ev(190, EventType.PASS, player=2,
                          detail={"receiver_id": 5})) is None
    assert gol_detail(_ev(190, EventType.PASS, player=2)) is None
    # A gól után.
    assert gol_detail(_ev(201, EventType.PASS, player=2,
                          detail={"receiver_id": 1})) is None
    # Önmagának adott "passz".
    assert gol_detail(_ev(190, EventType.PASS, player=1,
                          detail={"receiver_id": 1})) is None
    # Ismeretlen passzoló.
    assert gol_detail(_ev(190, EventType.PASS, player=None,
                          detail={"receiver_id": 1})) is None
    # Ismeretlen lövő: a gól érintetlen marad.
    assert gol_detail(_ev(190, EventType.PASS, player=2,
                          detail={"receiver_id": None}),
                      _ev(200, EventType.GOAL, player=None)) is None
    # A kihagyott lövés nem gól.
    loves = _ev(200, EventType.SHOT, player=1, detail={"outcome": "miss"})
    annotate_assists(m, [_ev(190, EventType.PASS, player=2,
                             detail={"receiver_id": 1}), loves])
    assert loves.detail == {"outcome": "miss"}
    # Üres eseménylista: üres marad.
    assert annotate_assists(m, []) == []


def test_annotate_assists_az_ablak_masodpercben_el():
    """Az ablak 4 MÁSODPERC: harmad-fps-en (a termék ritkítása) 33 kocka
    — a 33 kockával korábbi passz gólpassz, a 34-gyel korábbi nem."""
    from handball.pipeline.event_detection import annotate_assists

    ritka = Match(_meta(25.0 / 3.0), [])

    def assist(dt):
        gol = _ev(100, EventType.GOAL, player=1)
        annotate_assists(ritka, [_ev(100 - dt, EventType.PASS, player=2,
                                     detail={"receiver_id": 1}), gol])
        return (gol.detail or {}).get("assist_id")

    assert assist(33) == 2
    assert assist(34) is None
    # Ugyanez a 34 kocka sűrű (25 fps) felvételen bőven az ablakban van.
    gol = _ev(100, EventType.GOAL, player=1)
    annotate_assists(Match(_meta(), []), [
        _ev(66, EventType.PASS, player=2, detail={"receiver_id": 1}), gol])
    assert gol.detail == {"assist_id": 2}


def test_detect_events_a_golpasszt_a_valodi_esemenyekbol_irja_be():
    """A teljes lánc: a 2-es passzol az 1-esnek, aki gólt lő — a
    detect_events gól-eseményében ott az assist_id (a mezőnevek a VALÓDI
    passz- és gól-eseményekből jönnek, nem kitalált alakból)."""
    frames = []
    t = 0
    for _ in range(8):                       # a 2-es tartja a labdát
        frames.append(Frame(t=t, players=[_pl(2, Team.HOME, 26.0, 6.0),
                                          _pl(1, Team.HOME, 31.0, 10.0)],
                            ball=Ball(x=26.0, y=6.0, confidence=1.0)))
        t += 1
    for _ in range(8):                       # az 1-es megkapta
        frames.append(Frame(t=t, players=[_pl(2, Team.HOME, 26.0, 6.0),
                                          _pl(1, Team.HOME, 31.0, 10.0)],
                            ball=Ball(x=31.0, y=10.0, confidence=1.0)))
        t += 1
    for i in range(1, 10):                   # az 1-es lövése a +x kapura
        frames.append(Frame(t=t, players=[_pl(2, Team.HOME, 26.0, 6.0),
                                          _pl(1, Team.HOME, 31.0, 10.0)],
                            ball=Ball(x=min(31.0 + i, 40.0), y=10.0,
                                      confidence=1.0)))
        t += 1
    events = detect_events(Match(_meta(), frames))
    golok = [e for e in events if e.type == EventType.GOAL]
    assert len(golok) == 1
    assert golok[0].player_id == 1
    assert golok[0].detail.get("assist_id") == 2


# ---- A lövő visszakeresése (_shooter_before) ---------------------------------

def _atlovo_match(lovo_team=Team.HOME, tartas=5):
    """Átlövés 12 m-ről: a 7-es `tartas` kockán át tartja a labdát
    (28, 10)-nél, aztán a labda 25 m/s-mal repül a +x kapu felé — a
    röppálya mellett, a hatoson a 9-es beálló áll."""
    frames = []
    t = 0
    for _ in range(tartas):
        frames.append(Frame(t=t, players=[_pl(7, lovo_team, 28.0, 10.0),
                                          _pl(9, Team.HOME, 34.0, 10.5)],
                            ball=Ball(x=28.0, y=10.0, confidence=1.0)))
        t += 1
    for i in range(1, 8):
        frames.append(Frame(t=t, players=[_pl(7, lovo_team, 28.0, 10.0),
                                          _pl(9, Team.HOME, 34.0, 10.5)],
                            ball=Ball(x=28.0 + i, y=10.0, confidence=1.0)))
        t += 1
    return Match(_meta(), frames)


def test_shooter_before_az_elengedo_nem_a_roppalya_mellett_allo():
    """A lövés-esemény a kapu-megközelítéskor jön, amikor a labda már a
    beálló mellett repül: a lövő mégis az, aki ELENGEDTE (a 7-es) — a
    repülő labda melletti játékos nem birtokos."""
    from handball.pipeline.event_detection import _shooter_before
    from handball.pipeline.tactics import TacticsConfig

    m = _atlovo_match()
    cfg = TacticsConfig()
    # idx = 11: a labda (35, 10)-nél, a beállótól 1,1 m-re repül.
    assert m.frames[11].ball.x == 35.0
    assert _shooter_before(m, 11, Team.HOME, cfg, 25.0) == 7
    # Az elengedés előtti (még kézben tartott) kockán is ő a birtokos.
    assert _shooter_before(m, 3, Team.HOME, cfg, 25.0) == 7


def test_shooter_before_none_ha_nincs_tamado_birtokos_az_ablakban():
    """"Nem tudjuk" a magabiztosan rossz név helyett: None, ha a
    visszanézés ablakában (1,2 mp) a labdát csak az ellenfél tartotta,
    senki sem tartotta, vagy az elengedés régebben volt."""
    from handball.pipeline.event_detection import (SHOOTER_LOOKBACK_S,
                                                   _shooter_before)
    from handball.pipeline.tactics import TacticsConfig

    cfg = TacticsConfig()
    # A labdát a VENDÉG 7-es engedte el: hazai lövőt nem találunk — a
    # röppálya mellett álló hazai beálló sem lesz az.
    ellenfel = _atlovo_match(lovo_team=Team.AWAY)
    assert _shooter_before(ellenfel, 11, Team.HOME, cfg, 25.0) is None
    assert _shooter_before(ellenfel, 11, Team.AWAY, cfg, 25.0) == 7
    # Végig gazdátlan (lassú) labda, játékos nélkül.
    gazdatlan = _labda_match([(30.0 + 0.1 * i, 10.0) for i in range(12)])
    assert _shooter_before(gazdatlan, 11, Team.HOME, cfg, 25.0) is None
    # Az elengedés több mint 1,2 mp-cel (30 kockával) a lövés előtt volt:
    # a labda utána játékostól távol, lassan gurult.
    ablak = round(SHOOTER_LOOKBACK_S * 25.0)
    frames = [Frame(t=0, players=[_pl(7, Team.HOME, 20.0, 10.0)],
                    ball=Ball(x=20.0, y=10.0, confidence=1.0))]
    for i in range(1, ablak + 3):
        frames.append(Frame(t=i, players=[_pl(7, Team.HOME, 20.0, 10.0)],
                            ball=Ball(x=24.0 + 0.2 * i, y=10.0,
                                      confidence=1.0)))
    regi = Match(_meta(), frames)
    assert _shooter_before(regi, len(frames) - 1, Team.HOME, cfg,
                           25.0) is None
    # Ugyanez egy kockával az ablakon belül már megtalálja.
    assert _shooter_before(regi, ablak, Team.HOME, cfg, 25.0) == 7


# ---- Belső segédek közvetlenül (második kör) --------------------------------

def test_attacking_team_for_goal_melyik_csapat_tamadja_a_kaput():
    """Alapból a +x (x=40) kaput a hazai, a x=0 kaput a vendég támadja;
    fordított támadási iránynál (térfélcsere) fordítva."""
    from handball.pipeline.event_detection import _attacking_team_for_goal
    from handball.pipeline.tactics import TacticsConfig

    cfg = TacticsConfig()
    assert _attacking_team_for_goal(40.0, cfg) == Team.HOME
    assert _attacking_team_for_goal(0.0, cfg) == Team.AWAY
    forditva = TacticsConfig(home_attacks_positive=False)
    assert _attacking_team_for_goal(40.0, forditva) == Team.AWAY
    assert _attacking_team_for_goal(0.0, forditva) == Team.HOME


def test_ball_speed_ms_az_elozo_kockahoz_merve():
    """A labda sebessége az előző kockához mért elmozdulásból (m/s); az
    első kockán és hiányzó labdánál 0 — a "nem tudjuk" nem zárja ki a
    birtoklást."""
    from handball.pipeline.event_detection import _ball_speed_ms

    m = _labda_match([(10.0, 10.0), (10.4, 10.0), (10.4, 10.3), None,
                      (20.0, 10.0)])
    assert _ball_speed_ms(m.frames, 0, 25.0) == 0.0
    assert abs(_ball_speed_ms(m.frames, 1, 25.0) - 10.0) < 1e-9
    assert abs(_ball_speed_ms(m.frames, 2, 25.0) - 7.5) < 1e-9
    assert _ball_speed_ms(m.frames, 3, 25.0) == 0.0     # nincs labda
    assert _ball_speed_ms(m.frames, 4, 25.0) == 0.0     # az előzőn nincs
    # Harmad-fps-en ugyanaz az elmozdulás harmad akkora sebesség.
    assert abs(_ball_speed_ms(m.frames, 1, 25.0 / 3.0) - 10.0 / 3.0) < 1e-9


def test_median_paratlan_es_paros_elemszamra():
    """A medián páratlan elemszámnál a középső, párosnál a két középső
    átlaga — a bemenet sorrendjétől függetlenül."""
    from handball.pipeline.event_detection import _median

    assert _median([3.0, 1.0, 2.0]) == 2.0
    assert _median([4.0, 1.0, 3.0, 2.0]) == 2.5
    assert _median([7.0]) == 7.0
    assert _median([5.0, 5.0, 100.0]) == 5.0


def test_reaches_goal_line_a_gol_dontes():
    """A góldöntés: eléri-e a labda előrenézve a gólvonalat a kapufák
    között — igaz a kapuba tartó, hamis a mellé menő és a kapuig el nem
    érő labdára."""
    from handball.pipeline.event_detection import _reaches_goal_line

    gol = _labda_match([(36.0, 9.5), (38.0, 9.5), (39.6, 9.5)])
    assert _reaches_goal_line(gol, 0, 40.0) is True
    melle = _labda_match([(36.0, 5.0), (38.0, 5.0), (39.6, 5.0)])
    assert _reaches_goal_line(melle, 0, 40.0) is False
    rovid = _labda_match([(30.0, 10.0), (31.0, 10.0)])
    assert _reaches_goal_line(rovid, 0, 40.0) is False
    assert _reaches_goal_line(gol, 0, 0.0) is False     # a másik kapu


def _kapus(tid, team, x, y, role="kapus"):
    p = _pl(tid, team, x, y)
    p.role = role
    return p


def test_save_by_goalkeeper_a_kapujanal_allo_kapus_vedese():
    """Nem-gól lövésnél: ha a labda a lövés utáni ablakban a SAJÁT
    kapujánál álló kapus 1,6 m-es közelébe ér, az védés — a kapus
    azonosítójával."""
    from handball.pipeline.event_detection import (SAVE_RADIUS_M,
                                                   _save_by_goalkeeper)

    assert SAVE_RADIUS_M == 1.6
    frames = [Frame(t=i, players=[_pl(1, Team.HOME, 30.0, 10.0),
                                  _kapus(90, Team.AWAY, 39.0, 10.0)],
                    ball=Ball(x=34.0 + i, y=10.0, confidence=1.0))
              for i in range(5)]                        # 34 → 38 m
    assert _save_by_goalkeeper(Match(_meta(), frames), 0, 40.0) == 90


def test_save_by_goalkeeper_none_ha_nem_a_kapus_fogja():
    """Nincs védés, ha a labda közelében nem KAPUS áll (blokk / mellé),
    ha a kapus nem a kapujánál van (kijött), ha a labda nem ér a
    közelébe, vagy nincs labda — és a másik kapu kapusa sem számít."""
    from handball.pipeline.event_detection import _save_by_goalkeeper

    def meccs(vedo, labda_x=38.0):
        return Match(_meta(), [Frame(
            t=i, players=[_pl(1, Team.HOME, 30.0, 10.0), vedo],
            ball=None if labda_x is None
            else Ball(x=labda_x, y=10.0, confidence=1.0)) for i in range(3)])

    mezonyvedo = _kapus(21, Team.AWAY, 38.5, 10.0, role=None)
    assert _save_by_goalkeeper(meccs(mezonyvedo), 0, 40.0) is None
    kijott = _kapus(90, Team.AWAY, 30.0, 10.0)        # 10 m-re a kapujától
    assert _save_by_goalkeeper(meccs(kijott, labda_x=30.5), 0, 40.0) is None
    kapus = _kapus(90, Team.AWAY, 39.0, 10.0)
    assert _save_by_goalkeeper(meccs(kapus, labda_x=30.0), 0, 40.0) is None
    assert _save_by_goalkeeper(meccs(kapus, labda_x=None), 0, 40.0) is None
    assert _save_by_goalkeeper(meccs(kapus), 0, 40.0) == 90
    # A x=0 kapuhoz ez a kapus nem tartozik.
    assert _save_by_goalkeeper(meccs(kapus), 0, 0.0) is None
    assert _save_by_goalkeeper(Match(_meta(), []), 0, 40.0) is None


def _felallas(hazai_x, vendeg_x, n=6):
    """Egy kocka: a két csapat n-n mért játékosa a megadott x körül."""
    players = [_pl(k, Team.HOME, hazai_x + 0.5 * k, 3.0 + 2.5 * k)
               for k in range(n)]
    players += [_pl(10 + k, Team.AWAY, vendeg_x - 0.5 * k, 3.0 + 2.5 * k)
                for k in range(n)]
    return Frame(t=0, players=players, ball=Ball(x=20.0, y=10.0,
                                                 confidence=1.0))


def test_throw_off_low_team_a_sajat_terfelen_allo_csapatok():
    """A középkezdés felállása: mindkét csapat a SAJÁT térfelén áll — a
    függvény megmondja, melyik áll az alacsony x térfélen; térfélcsere
    után a másik."""
    from handball.pipeline.event_detection import _throw_off_low_team

    assert _throw_off_low_team(_felallas(10.0, 30.0)) == Team.HOME
    assert _throw_off_low_team(_felallas(27.0, 13.0)) == Team.AWAY


def test_throw_off_low_team_none_ha_nem_kozepkezdes_felallas():
    """Nem középkezdés-felállás: csapatonként 4-nél kevesebb mért
    játékos, mindkét csapat egy térfélen (támadás), a két csapat túl
    közel a felezőnél, vagy üres kocka → None."""
    from handball.models.tracking import PositionSource
    from handball.pipeline.event_detection import (THROWOFF_MIN_PLAYERS,
                                                   _throw_off_low_team)

    assert THROWOFF_MIN_PLAYERS == 4
    assert _throw_off_low_team(_felallas(10.0, 30.0, n=3)) is None
    assert _throw_off_low_team(_felallas(25.0, 36.0)) is None    # egy térfél
    assert _throw_off_low_team(_felallas(17.0, 23.0)) is None    # túl közel
    assert _throw_off_low_team(Frame(t=0, players=[], ball=None)) is None
    # A becsült pozíció nem számít: 4 MÉRT hazaival még megvan a
    # felállás, 3-mal már nincs.
    becsult = _felallas(10.0, 30.0, n=6)
    for p in becsult.players[:2]:
        p.source = PositionSource.ESTIMATED
    assert _throw_off_low_team(becsult) == Team.HOME
    becsult.players[2].source = PositionSource.ESTIMATED
    assert _throw_off_low_team(becsult) is None


def test_throw_off_followed_a_gol_utan_a_masik_iranyba_indul_a_jatek():
    """A középkezdés után a gólt KAPÓ csapat támad: a labda az adott időn
    belül átér a gólt szerző térfelére (3 m-rel a felezőn túl) — ez
    igazolja a gólt. Ha előbb a gól kapuja elé ér vissza, vagy az idő
    lejár, nem."""
    from handball.pipeline.event_detection import _throw_off_followed

    # A gól a +x kapuba esett → a középkezdés után a labda a x=0 felé megy.
    indul = _labda_match([(20.0, 10.0)] * 5 + [(20.0 - i, 10.0)
                                               for i in range(1, 8)])
    assert _throw_off_followed(indul.frames, 0, 40.0, follow_t=50) is True
    assert _throw_off_followed(indul.frames, 0, 40.0, follow_t=6) is False
    # Rossz irány: a labda a gól kapuja felé megy vissza (nem volt gól).
    vissza = _labda_match([(20.0, 10.0)] * 5 + [(20.0 + 2 * i, 10.0)
                                                for i in range(1, 8)])
    assert _throw_off_followed(vissza.frames, 0, 40.0, follow_t=50) is False
    # A x=0 kapuba esett gól után tükrözve.
    assert _throw_off_followed(vissza.frames, 0, 0.0, follow_t=50) is True
    # A labda nélküli kockák nem szakítják meg a követést.
    lyukas = _labda_match([(20.0, 10.0), None, None, (16.0, 10.0)])
    assert _throw_off_followed(lyukas.frames, 0, 40.0, follow_t=50) is True
    # A meccs végén túli kezdet: hamis.
    assert _throw_off_followed(indul.frames, 99, 40.0, follow_t=50) is False
    assert _throw_off_followed([], 0, 40.0, follow_t=50) is False


def test_in_center_es_still_at_center_a_kozepen_allo_labda():
    """A középkezdés-jel: a LÁTOTT labda a pálya közepén áll az ablak
    végéig (legfeljebb 1,5 m-t mozdul). Nem áll, ha a labda az ablakban
    kimegy a középről, ha az első kockán csak pótolt (interpolált) a
    labda, ha az ablak túlnyúlik a meccs végén, vagy nincs labda."""
    from handball.pipeline.event_detection import (_in_center,
                                                   _still_at_center)

    assert _in_center(Ball(x=20.0, y=10.0)) is True
    assert _in_center(Ball(x=30.0, y=10.0)) is False
    assert _in_center(Ball(x=20.0, y=2.0)) is False

    all_kozepen = _labda_match([(20.0, 10.0)] * 30)
    assert _still_at_center(all_kozepen.frames, 0, 25, 0.5) is True
    assert _still_at_center(all_kozepen.frames, 5, 25, 0.5) is True
    assert _still_at_center(all_kozepen.frames, 6, 25, 0.5) is False  # túlnyúlik
    kimegy = _labda_match([(20.0, 10.0)] * 10 + [(30.0, 10.0)] * 20)
    assert _still_at_center(kimegy.frames, 0, 25, 0.5) is False
    assert _still_at_center(kimegy.frames, 0, 10, 0.5) is True
    # Az első kockán pótolt (alacsony megbízhatóságú) labda nem jel.
    potolt = _labda_match([(20.0, 10.0)] * 30)
    potolt.frames[0].ball.confidence = 0.2
    assert _still_at_center(potolt.frames, 0, 25, 0.5) is False
    assert _still_at_center(potolt.frames, 1, 25, 0.5) is True
    nincs = _labda_match([None] * 30)
    assert _still_at_center(nincs.frames, 0, 25, 0.5) is False


def test_half_boundaries_a_felido_es_a_darab_hatarok():
    """A határok: a felismert félidő-pont és minden további felvétel-
    darab kezdete — a kapu előtti labdának és a középkezdésnek ugyanabban
    a félidőben és darabban kell lennie. Határ nélküli meccsen üres."""
    from handball.pipeline.event_detection import _half_boundaries

    m = _labda_match([(20.0, 10.0)] * 10)
    assert _half_boundaries(m) == []
    # Darabokban felvett meccs: a 2. és 3. darab kezdete határ; a forduló
    # (döntött) darab-határ egyben a félidő-pont is.
    m.meta.source_segments = [
        {"t_from": 0, "t_to": 4, "mirrored": False, "mirror_decided": True},
        {"t_from": 4, "t_to": 7, "mirrored": True, "mirror_decided": True},
        {"t_from": 7, "t_to": 10, "mirrored": True, "mirror_decided": True}]
    assert _half_boundaries(m) == [4, 4, 7]
    # A rossz alakú darab-bejegyzés kimarad (nem viszi el a többit).
    m.meta.source_segments = [{"t_from": 0}, {"t_from": "nem szám"},
                              {"t_from": 6}]
    assert _half_boundaries(m) == [6]


# ---- Belső segédek közvetlenül (harmadik kör) -------------------------------

def test_shooter_release_before_az_elengedes_kockajat_is_adja():
    """A lövő mellé az ELENGEDÉS kockája is kell (a lövés HELYÉNEK a
    kulcsa): átlövésnél az utolsó kézben tartott kocka — nem az esemény
    (kapu-megközelítés) kockája; találat nélkül mindkettő None."""
    from handball.pipeline.event_detection import _shooter_release_before
    from handball.pipeline.tactics import TacticsConfig

    cfg = TacticsConfig()
    m = _atlovo_match()
    # A 7-es a 0–4. kockán tartja a labdát, az 5.-től repül.
    assert _shooter_release_before(m, 11, Team.HOME, cfg, 25.0) == (7, 4)
    assert _shooter_release_before(m, 2, Team.HOME, cfg, 25.0) == (7, 2)
    ellenfel = _atlovo_match(lovo_team=Team.AWAY)
    assert _shooter_release_before(ellenfel, 11, Team.HOME, cfg,
                                   25.0) == (None, None)


def test_shooter_release_before_kovetes_lyuknal_nevet_ad_helyet_nem():
    """Követés-lyuknál a lista-szomszédság IDŐBEN messzire mutathat: a
    lövő nevét megtartjuk, de az elengedés kockáját (a lövés helyét) nem
    állítjuk — None."""
    from handball.pipeline.event_detection import _shooter_release_before
    from handball.pipeline.tactics import TacticsConfig

    surun = _atlovo_match()
    # Ugyanaz a jelenet, de a repülés kockái 100 kockával később jönnek
    # (a követés közben kimaradt).
    lyukas = Match(_meta(), [
        Frame(t=f.t if i < 5 else f.t + 100, players=f.players, ball=f.ball)
        for i, f in enumerate(surun.frames)])
    assert _shooter_release_before(lyukas, 11, Team.HOME, TacticsConfig(),
                                   25.0) == (7, None)


def _egyutemu_kockak(szelso=(36.0, 3.0), szelso_csapat=Team.HOME,
                     szelso_szerep=None, labda_lyuk=None):
    """Együtemű lövés ritkítva: a 6-os tartja a labdát (0–3. kocka), a
    passz-szár két gyors mintája után a labda a szélsőnél (6. kocka)
    megtörik, és a lövés-szár a kapuba megy — kézben tartott kocka a
    szélsőnél NINCS."""
    ut = [(28.2, 10.0)] * 4 + [(31.0, 7.5), (34.0, 4.5), (36.0, 3.0),
                               (38.0, 6.5), (40.0, 10.0)]
    frames = []
    for t, (x, y) in enumerate(ut):
        jatekosok = [_pl(6, Team.HOME, 28.0, 10.0),
                     PlayerPosition(track_id=2, team=szelso_csapat,
                                    x=szelso[0], y=szelso[1],
                                    source=PositionSource.MEASURED,
                                    confidence=1.0, role=szelso_szerep)]
        labda = None if t == labda_lyuk else Ball(x=x, y=y, confidence=1.0)
        frames.append(Frame(t=t, players=jatekosok, ball=labda))
    return Match(_meta(8.33), frames)


def test_shooter_at_flight_kink_a_toresponton_allo_a_lovo():
    """A röppálya töréspontja (passz-szár → lövés-szár) mellett álló
    saját mezőnyjátékos a lövő, az elengedés kockája a töréspont — akár
    a lövés-szár, akár a passz-szár kockájáról indul a keresés."""
    from handball.pipeline.event_detection import _shooter_at_flight_kink

    m = _egyutemu_kockak()
    assert _shooter_at_flight_kink(m, 8, 0, Team.HOME, 8.33) == (2, 6)
    assert _shooter_at_flight_kink(m, 7, 0, Team.HOME, 8.33) == (2, 6)
    # A passz-szár kockájáról is: a gyors, kapu felé tartó szakaszokat
    # előre követi a lövés-szár végéig.
    assert _shooter_at_flight_kink(m, 5, 0, Team.HOME, 8.33) == (2, 6)


def test_shooter_at_flight_kink_nem_talalgat():
    """None (a régi út dönt), ha a töréspontnál nincs saját
    mezőnyjátékos 2,5 m-en belül (messze áll, ellenfél, kapus), ha a
    visszanézésben nincs irányváltás, ha lassú (kézben tartott) kocka
    jön előbb, vagy ha a labda közben nem látszik."""
    from handball.pipeline.event_detection import (SHOOTER_KINK_NEAR_M,
                                                   _shooter_at_flight_kink)

    assert SHOOTER_KINK_NEAR_M == 2.5
    messze = _egyutemu_kockak(szelso=(36.0, 6.0))            # 3 m-re
    assert _shooter_at_flight_kink(messze, 8, 0, Team.HOME, 8.33) is None
    kozel = _egyutemu_kockak(szelso=(36.0, 5.0))             # 2 m-re
    assert _shooter_at_flight_kink(kozel, 8, 0, Team.HOME, 8.33) == (2, 6)
    ellenfel = _egyutemu_kockak(szelso_csapat=Team.AWAY)
    assert _shooter_at_flight_kink(ellenfel, 8, 0, Team.HOME, 8.33) is None
    kapus = _egyutemu_kockak(szelso_szerep="kapus")
    assert _shooter_at_flight_kink(kapus, 8, 0, Team.HOME, 8.33) is None
    # A visszanézés a lövés-szárnál véget ér (back = 7): nincs töréspont.
    m = _egyutemu_kockak()
    assert _shooter_at_flight_kink(m, 8, 7, Team.HOME, 8.33) is None
    # Egyenes átlövés: a lövés-szár előtt a labda kézben volt (lassú).
    atlovo = _atlovo_match()
    assert _shooter_at_flight_kink(atlovo, 11, 0, Team.HOME, 25.0) is None
    # A passz-szár egyik mintája hiányzik: nem találgatunk.
    lyukas = _egyutemu_kockak(labda_lyuk=5)
    assert _shooter_at_flight_kink(lyukas, 8, 0, Team.HOME, 8.33) is None


def _latott(pontok, gyenge=()):
    """Kockák a labda x-éből (y = 10; None = nem látszik); a `gyenge`
    indexeken a labda csak becsült (megbízhatóság 0,2)."""
    return [Frame(t=i, players=[],
                  ball=None if x is None else Ball(
                      x=x, y=10.0, confidence=0.2 if i in gyenge else 1.0))
            for i, x in enumerate(pontok)]


def test_inferred_goal_moment_a_kapu_fele_tarto_gyors_labda():
    """(1) A lövés nélküli gól pillanata az utolsó LÁTOTT, kapu felé
    tartó, lövés-sebességű labda — nem a labda utolsó kapu előtti
    kockája (az már a gól utáni: a kapus szedi ki a hálóból). Mindkét
    kapura, és az index-alak ugyanazt adja."""
    from handball.pipeline.event_detection import (_inferred_goal_index,
                                                   _inferred_goal_moment)

    # 0–4: kézben (30 m); 5–8: lövés (2 m / kocka = 50 m/s); utána a
    # hálóban áll.
    xs = [30.0] * 5 + [32.0, 34.0, 36.0, 38.0] + [39.5] * 20
    frames = _latott(xs)
    j = len(frames) - 1
    # Az utolsó gyors, kapu felé tartó minta-pár ELSŐ kockája: 38 → 39,5.
    assert _inferred_goal_moment(frames, j, 40.0, 25.0, 0.3) == (8, "loves")
    assert _inferred_goal_index(frames, j, 40.0, 25.0, 0.3) == 8
    tukor = _latott([40.0 - x for x in xs])
    assert _inferred_goal_moment(tukor, j, 0.0, 25.0, 0.3) == (8, "loves")
    # A másik kapu felől nézve ugyanez a labda TÁVOLODIK: nem lövés.
    assert _inferred_goal_moment(tukor, j, 40.0, 25.0, 0.3)[1] != "loves"


def test_inferred_goal_moment_a_labda_eltunese_vagy_az_utolso_kocka():
    """(2) Gyors labda híján az utolsó látott labda a kapu előtt, amely
    után legalább 0,4 mp hézag jön (az elmosódott lövés-labda eltűnése);
    (3) különben marad a `j`. Üres kocka-listára is (j, "utolso")."""
    from handball.pipeline.event_detection import (THROWOFF_GOALTIME_GAP_S,
                                                   _inferred_goal_index,
                                                   _inferred_goal_moment)

    assert THROWOFF_GOALTIME_GAP_S == 0.4            # 25 fps-en 10 kocka
    # 0–10: áll a labda 33 m-nél; 11–24: nem látszik; 25-től a hálóban.
    xs = [33.0] * 11 + [None] * 14 + [39.5] * 10
    frames = _latott(xs)
    j = len(frames) - 1
    assert _inferred_goal_moment(frames, j, 40.0, 25.0, 0.3) == (
        10, "eltunes")
    assert _inferred_goal_index(frames, j, 40.0, 25.0, 0.3) == 10
    # A hézag csak 0,36 mp (9 kocka): nem eltűnés — és a két minta közt
    # 0,5 mp-en belül a labda 6,5 m-t ment a kapu felé: az már LÖVÉS.
    rovid = _latott([33.0] * 11 + [None] * 8 + [39.5] * 10)
    assert _inferred_goal_moment(rovid, len(rovid) - 1, 40.0, 25.0,
                                 0.3) == (10, "loves")
    # Végig álló, látott labda: nincs miből következtetni.
    allo = _latott([39.0] * 30)
    assert _inferred_goal_moment(allo, 29, 40.0, 25.0, 0.3) == (29, "utolso")
    assert _inferred_goal_moment([], 7, 40.0, 25.0, 0.3) == (7, "utolso")


def test_inferred_goal_moment_csak_latott_kozeli_friss_labdabol():
    """A becsült (kis megbízhatóságú) labda nem bizonyíték; a kaputól 12
    m-nél messzebbről induló gyors labda nem lövés; és csak az utolsó 15
    MÁSODPERC számít — a kép-rátától függetlenül."""
    from handball.pipeline.event_detection import (
        THROWOFF_GOALTIME_BACK_S, THROWOFF_GOALTIME_RANGE_M,
        _inferred_goal_moment)

    assert (THROWOFF_GOALTIME_BACK_S, THROWOFF_GOALTIME_RANGE_M) == (
        15.0, 12.0)
    xs = [30.0] * 5 + [32.0, 34.0, 36.0, 38.0] + [39.5] * 20
    j = len(xs) - 1
    # A lövés-szár kockái csak becsültek: a látott minták (30 → 39,5)
    # közt 0,2 mp telik el — a kapu felé tartó gyors labda így is
    # megvan, de a kezdete az utolsó LÁTOTT kocka (a 4.).
    becsult = _latott(xs, gyenge={5, 6, 7, 8})
    assert _inferred_goal_moment(becsult, j, 40.0, 25.0, 0.3) == (4, "loves")
    # Minden labda becsült: nincs látott minta.
    semmi = _latott(xs, gyenge=set(range(len(xs))))
    assert _inferred_goal_moment(semmi, j, 40.0, 25.0, 0.3) == (j, "utolso")
    # Gyors labda a pálya közepén (20 → 26 m: a kaputól 14+ m-re indul),
    # utána lassan gurul a kapu elé.
    tavoli = _latott([20.0] * 3 + [22.0, 24.0, 26.0]
                     + [26.0 + 0.1 * i for i in range(1, 30)])
    assert _inferred_goal_moment(tavoli, len(tavoli) - 1, 40.0, 25.0,
                                 0.3)[1] == "utolso"
    # A lövés 16 mp-cel a `j` előtt volt: kívül az ablakon; 14 mp-nél
    # belül — 25 és 12,5 fps-en ugyanúgy.
    for fps in (25.0, 12.5):
        lepes = 50.0 / fps                      # 50 m/s kockánként
        regi = _latott([30.0] * 3 + [30.0 + lepes, 30.0 + 2 * lepes]
                       + [39.5] * int(17 * fps))
        assert _inferred_goal_moment(regi, 4 + int(16 * fps), 40.0, fps,
                                     0.3)[1] == "utolso", fps
        assert _inferred_goal_moment(regi, 4 + int(14 * fps), 40.0, fps,
                                     0.3)[1] == "loves", fps


def _halos_atlovo_match(allas=20):
    """Az átlövő (7-es) elengedi a labdát, az 1 m / kockával (25 m/s) a
    kapuig repül, aztán `allas` kockán át a hálóban áll."""
    alap = _atlovo_match()
    frames = list(alap.frames)
    jatekosok = frames[-1].players
    t = frames[-1].t + 1
    for x in [36.0, 37.0, 38.0, 39.0] + [39.5] * allas:
        frames.append(Frame(t=t, players=jatekosok,
                            ball=Ball(x=x, y=10.0, confidence=1.0)))
        t += 1
    return Match(_meta(), frames)


def test_shooter_hint_a_latott_loves_elengedoje():
    """A lövés nélküli gól VALÓSZÍNŰ lövője: ha a kapu felé tartó gyors
    labdát láttuk, a lövő az, aki elengedte (a 7-es) — nem a röppálya
    mellett álló beálló."""
    from handball.pipeline.event_detection import _shooter_hint
    from handball.pipeline.tactics import TacticsConfig

    m = _halos_atlovo_match()
    j = len(m.frames) - 1
    assert _shooter_hint(m, m.frames, j, 40.0, Team.HOME, TacticsConfig(),
                         25.0, 0.3) == 7
    # A vendég csapatból senki sem tartotta a labdát: nincs tipp.
    assert _shooter_hint(m, m.frames, j, 40.0, Team.AWAY, TacticsConfig(),
                         25.0, 0.3) is None


def test_shooter_hint_none_ha_a_lovest_nem_lattuk():
    """Ha a gól pillanata csak a labda eltűnéséből vagy az utolsó
    kockából következik (nem látott lövésből), nincs lövő-tipp — akkor
    sem, ha a labdánál ott áll egy támadó."""
    from handball.pipeline.event_detection import (_inferred_goal_moment,
                                                   _shooter_hint)
    from handball.pipeline.tactics import TacticsConfig

    # A 7-es végig a labdánál áll a kapu előtt: nincs gyors labda.
    frames = [Frame(t=i, players=[_pl(7, Team.HOME, 33.0, 10.0)],
                    ball=Ball(x=33.0, y=10.0, confidence=1.0))
              for i in range(30)]
    m = Match(_meta(), frames)
    assert _inferred_goal_moment(frames, 29, 40.0, 25.0, 0.3)[1] == "utolso"
    assert _shooter_hint(m, frames, 29, 40.0, Team.HOME, TacticsConfig(),
                         25.0, 0.3) is None
    # Eltűnő labda (0,6 mp hézag) — ez sem látott lövés.
    lyukas = [Frame(t=i, players=[_pl(7, Team.HOME, 33.0, 10.0)],
                    ball=(None if 11 <= i < 26 else Ball(
                        x=33.0 if i < 11 else 39.5, y=10.0, confidence=1.0)))
              for i in range(36)]
    assert _inferred_goal_moment(lyukas, 35, 40.0, 25.0, 0.3)[1] == "eltunes"
    assert _shooter_hint(Match(_meta(), lyukas), lyukas, 35, 40.0, Team.HOME,
                         TacticsConfig(), 25.0, 0.3) is None


def test_near_goal_stretch_start_a_kapu_elotti_utolso_szakasz_eleje():
    """A `j`-től visszafelé, amíg a labda a kapu előtti 9 m-es sávban
    van — a labda-hézag nem szakítja meg, az első sávon kívüli labda
    igen; ha a `j` kockán a labda nincs a sávban, a szakasz maga a `j`."""
    from handball.pipeline.event_detection import (THROWOFF_GOAL_ZONE_M,
                                                   _near_goal_stretch_start)

    assert THROWOFF_GOAL_ZONE_M == 9.0
    frames = _latott([20.0, 25.0, 33.0, None, None, 35.0, 38.0, 39.0])
    assert _near_goal_stretch_start(frames, 7, 40.0) == 2
    assert _near_goal_stretch_start(frames, 5, 40.0) == 2
    assert _near_goal_stretch_start(frames, 1, 40.0) == 1      # sávon kívül
    # A sáv széle még benne van (31 m), egy centivel kijjebb már nem.
    assert _near_goal_stretch_start(_latott([31.0, 39.0]), 1, 40.0) == 0
    assert _near_goal_stretch_start(_latott([30.99, 39.0]), 1, 40.0) == 1
    # A másik kapura tükrözve ugyanaz.
    tukor = _latott([20.0, 15.0, 7.0, None, None, 5.0, 2.0, 1.0])
    assert _near_goal_stretch_start(tukor, 7, 0.0) == 2
    # A felvétel elejéig tartó szakasz (és a kezdő hézag) sem hiba.
    assert _near_goal_stretch_start(_latott([None, 36.0, 39.0]), 2,
                                    40.0) == 1


def _kapuelotti(n, kint=(), nem_latszik=(), gyenge=()):
    """`n` kocka 5 fps-en: a labda alapból a hálóban (39,5; 10), a
    `kint` indexeken a kapuelőtéren kívül (28; 10), a `nem_latszik`
    indexeken nincs labda, a `gyenge` indexeken csak becsült."""
    return [Frame(t=i, players=[],
                  ball=None if i in nem_latszik else Ball(
                      x=28.0 if i in kint else 39.5, y=10.0,
                      confidence=0.2 if i in gyenge else 1.0))
            for i in range(n)]


def test_held_at_goal_since_a_labda_a_haloban_maradt():
    """A lövés (k) után a labda a kapuelőtérben maradt, és csak a végén
    vitték ki a középre: a támadás nem folytatódott — igaz. A lövés
    utáni repülés (1 mp) még a kapuelőtéren kívül lehet."""
    from handball.pipeline.event_detection import _held_at_goal_since

    fps = 5.0
    # A 200. kocka a lövés: a labda még 1 mp-ig (5 kocka) úton van,
    # aztán a hálóban; a 291.-től viszik ki a középre.
    kint = set(range(200, 206)) | set(range(291, 301))
    frames = _kapuelotti(301, kint=kint)
    assert _held_at_goal_since(frames, 200, 300, 40.0, fps, 0.3) is True
    # Végig a hálóban (a `j` kockán is): szintén igaz.
    assert _held_at_goal_since(_kapuelotti(301), 200, 300, 40.0, fps,
                               0.3) is True
    # A becsült labda nem számít: a közbeeső "kinti" becslések nem
    # rontják el.
    becsult = _kapuelotti(301, kint=kint | {240, 241},
                          gyenge={240, 241})
    assert _held_at_goal_since(becsult, 200, 300, 40.0, fps, 0.3) is True


def test_held_at_goal_since_hamis_ha_a_tamadas_folytatodott():
    """Hamis, ha a labda a repülés után kijött a kapuelőtérből és újra
    visszakerült (lepattanó, újabb helyzet), ha egyszer sem volt a
    kapuelőtérben, vagy ha a kapuelőteret több mint 5 mp-cel a `j` előtt
    hagyta el."""
    from handball.pipeline.event_detection import (THROWOFF_HELD_EXIT_S,
                                                   THROWOFF_HELD_FLIGHT_S,
                                                   THROWOFF_HELD_M,
                                                   _held_at_goal_since)

    assert (THROWOFF_HELD_M, THROWOFF_HELD_FLIGHT_S,
            THROWOFF_HELD_EXIT_S) == (6.0, 1.0, 5.0)
    fps = 5.0
    # Lepattanó: a 220–230. kockán a labda újra kint, aztán megint bent.
    lepattano = _kapuelotti(301, kint=set(range(220, 231)))
    assert _held_at_goal_since(lepattano, 200, 300, 40.0, fps, 0.3) is False
    # Ugyanez a repülés idején belül (a 201–205. kockán) még belefér.
    repules = _kapuelotti(301, kint=set(range(200, 206)))
    assert _held_at_goal_since(repules, 200, 300, 40.0, fps, 0.3) is True
    # Egyszer sem volt bent.
    soha = _kapuelotti(301, kint=set(range(0, 301)))
    assert _held_at_goal_since(soha, 200, 300, 40.0, fps, 0.3) is False
    # A labda nem látszik a lövés után: nincs bizonyíték.
    vak = _kapuelotti(301, nem_latszik=set(range(200, 301)))
    assert _held_at_goal_since(vak, 200, 300, 40.0, fps, 0.3) is False
    # A kapuelőteret 5 mp-nél (25 kocka) régebben hagyta el: 26 kocka.
    regen = _kapuelotti(301, kint=set(range(275, 301)))
    assert _held_at_goal_since(regen, 200, 300, 40.0, fps, 0.3) is False
    epp = _kapuelotti(301, kint=set(range(276, 301)))
    assert _held_at_goal_since(epp, 200, 300, 40.0, fps, 0.3) is True
    # A másik kapunál (x = 0) ugyanez a labda 39,5 m-re van: nincs bent.
    assert _held_at_goal_since(_kapuelotti(301), 200, 300, 0.0, fps,
                               0.3) is False


def test_upgradable_shot_a_golt_szerzo_utolso_friss_lovese():
    """A középkezdés előtti gól LÁTOTT lövése: a gólt szerző csapat
    legutolsó (nem gól) lövése, legfeljebb 10 mp-cel a labda utolsó kapu
    előtti kockája előtt — az `events` listabeli indexével."""
    from handball.pipeline.event_detection import (THROWOFF_LOOKBACK_S,
                                                   THROWOFF_UPGRADE_S,
                                                   _upgradable_shot)

    assert (THROWOFF_LOOKBACK_S, THROWOFF_UPGRADE_S) == (45.0, 10.0)
    fps = 5.0
    frames = _kapuelotti(400, kint=set(range(0, 240)))
    j, t0 = 300, 320            # a labda utolsó kapu előtti kockája, kezdés
    events = [
        _ev(255, EventType.SHOT, Team.AWAY),     # 0: a másik csapaté
        _ev(260, EventType.SHOT, Team.HOME),     # 1: friss lövés
        _ev(270, EventType.PASS, Team.HOME),     # 2: nem lövés
        _ev(280, EventType.SHOT, Team.HOME),     # 3: a legutolsó friss
        _ev(290, EventType.GOAL, Team.HOME),     # 4: már gól — nem javítandó
        _ev(330, EventType.SHOT, Team.HOME),     # 5: a középkezdés UTÁN
    ]
    assert _upgradable_shot(frames, events, Team.HOME, t0, j, 40.0, fps,
                            0.3) == 3
    assert _upgradable_shot(frames, events, Team.AWAY, t0, j, 40.0, fps,
                            0.3) == 0
    # Az előre kiszámolt idő-lista ugyanazt adja.
    assert _upgradable_shot(frames, events, Team.HOME, t0, j, 40.0, fps,
                            0.3, idok=[f.t for f in frames]) == 3
    # Nincs lövés (vagy üres az esemény-lista): None.
    assert _upgradable_shot(frames, events[2:3], Team.HOME, t0, j, 40.0,
                            fps, 0.3) is None
    assert _upgradable_shot(frames, [], Team.HOME, t0, j, 40.0, fps,
                            0.3) is None


def test_upgradable_shot_regi_loves_csak_ha_a_labda_a_haloban_maradt():
    """A 10 mp-nél régebbi lövés után a támadás folytatódhatott — az a
    védés nem írható át gólra; KIVÉVE, ha a lövés óta a labda végig a
    kapuelőtérben maradt. A 45 mp-es visszanézésen túli lövés soha."""
    from handball.pipeline.event_detection import _upgradable_shot

    fps = 5.0
    j, t0 = 300, 320
    regi = [_ev(200, EventType.SHOT, Team.HOME)]      # 20 mp-cel a j előtt
    # A lövés (200) után a labda a hálóban maradt, a 291.-től viszik ki.
    haloban = _kapuelotti(400, kint=set(range(200, 206))
                          | set(range(291, 400)))
    assert _upgradable_shot(haloban, regi, Team.HOME, t0, j, 40.0, fps,
                            0.3) == 0
    # A lövés után lepattanó: a támadás folytatódott → nincs javítás.
    lepattano = _kapuelotti(400, kint=set(range(220, 231))
                            | set(range(291, 400)))
    assert _upgradable_shot(lepattano, regi, Team.HOME, t0, j, 40.0, fps,
                            0.3) is None
    # Pont a 10 mp-es határon (250) a lövés még friss — a labda útja
    # nem számít (itt a lövés után, a 260–270. kockán lepattanó jön);
    # egy kockával régebbről ugyanez a lepattanó már kizárja.
    kesoi = _kapuelotti(400, kint=set(range(260, 271))
                        | set(range(291, 400)))
    hataron = [_ev(250, EventType.SHOT, Team.HOME)]
    assert _upgradable_shot(kesoi, hataron, Team.HOME, t0, j, 40.0, fps,
                            0.3) == 0
    assert _upgradable_shot(kesoi, [_ev(249, EventType.SHOT, Team.HOME)],
                            Team.HOME, t0, j, 40.0, fps, 0.3) is None
    # A középkezdés előtt 45 mp-nél (225 kocka) régebbi lövés: soha,
    # akkor sem, ha a labda azóta a hálóban volt.
    vegig = _kapuelotti(400)
    assert _upgradable_shot(vegig, [_ev(95, EventType.SHOT, Team.HOME)],
                            Team.HOME, t0, j, 40.0, fps, 0.3) == 0
    assert _upgradable_shot(vegig, [_ev(94, EventType.SHOT, Team.HOME)],
                            Team.HOME, t0, j, 40.0, fps, 0.3) is None
