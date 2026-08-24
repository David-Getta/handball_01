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
