"""
Tesztek az élő edzői javaslatokra (coaching.py).

Kézzel összerakott frame-ekkel, videó nélkül. A pálya 40x20 m; a HAZAI a +x (x=40)
kapu felé támad, saját kapuja x=0. (Alapértelmezett TacticsConfig.)

Futtatás:
    python tests/test_coaching.py
"""

from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, Ball, Team, PositionSource,
)
from handball.pipeline.tactics import TacticsConfig
from handball.pipeline.coaching import (
    suggest_for_frame, coaching_timeline, Suggestion,
)


def _pl(track_id, team, x, y):
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0)


def _meta(fps=25.0):
    return MatchMeta(match_id="t", home_team="A", away_team="B", fps=fps,
                     frame_width=1920, frame_height=1080)


def _cats(sugg):
    return {s.category for s in sugg}


def test_no_ball_gives_general_hint():
    """Labda nélkül általános (alacsony prioritású) tanácsot ad."""
    frame = Frame(t=0, players=[_pl(1, Team.HOME, 30.0, 10.0)], ball=None)
    sugg = suggest_for_frame(frame, TacticsConfig())
    assert len(sugg) == 1 and sugg[0].category == "altalanos"


def test_free_ball_transition():
    """Ha nincs birtokos (a labda messze), átmeneti/tempó tanácsot ad."""
    frame = Frame(t=0, players=[_pl(1, Team.HOME, 5.0, 10.0)],
                  ball=Ball(x=35.0, y=10.0, confidence=1.0))
    sugg = suggest_for_frame(frame, TacticsConfig())
    assert sugg[0].category == "tempo"


def test_man_advantage_detected():
    """Több támadó mezőnyjátékos → emberelőny-javaslat, magas prioritással elöl."""
    # HAZAI birtokol (x=30, a támadó térfélen), 3 mezőnytámadó, 1 védő.
    players = [
        _pl(1, Team.HOME, 30.0, 10.0),   # labdás
        _pl(2, Team.HOME, 32.0, 4.0),
        _pl(3, Team.HOME, 32.0, 16.0),
        _pl(11, Team.AWAY, 34.0, 10.0),  # egyetlen védő (mezőnyben)
    ]
    frame = Frame(t=0, players=players, ball=Ball(x=30.0, y=10.0, confidence=1.0))
    sugg = suggest_for_frame(frame, TacticsConfig())
    assert "emberelony" in _cats(sugg)
    # a legmagasabb prioritású (elöl) az emberelőny (prio 5)
    assert sugg[0].priority == 5


def test_open_teammate_suggested():
    """Az ellenfelektől távoli, támadó térfélen lévő csapattársat ajánlja."""
    players = [
        _pl(1, Team.HOME, 22.0, 10.0),   # labdás, közel a felezőhöz
        _pl(2, Team.HOME, 35.0, 3.0),    # szabad a bal oldalon (nincs védő közel)
        _pl(11, Team.AWAY, 34.0, 17.0),  # védő a másik oldalon
        _pl(12, Team.AWAY, 33.0, 15.0),
    ]
    frame = Frame(t=0, players=players, ball=Ball(x=22.0, y=10.0, confidence=1.0))
    sugg = suggest_for_frame(frame, TacticsConfig())
    assert "szabad" in _cats(sugg)


def test_formation_suggestion_always_present():
    """Mindig ad egy védőforma-alapú irányt (itt 6-0 a mély fal)."""
    players = [_pl(1, Team.HOME, 30.0, 10.0)]
    # 6 védő a saját (x=40) kapu előtt, ~6 m mélységben (depth 4-6) → 6-0
    for i, y in enumerate([2, 6, 8, 12, 14, 18]):
        players.append(_pl(20 + i, Team.AWAY, 35.0, float(y)))
    frame = Frame(t=0, players=players, ball=Ball(x=30.0, y=10.0, confidence=1.0))
    sugg = suggest_for_frame(frame, TacticsConfig())
    forma = [s for s in sugg if s.category == "forma"]
    assert forma and "6-0" in forma[0].text


def test_fastbreak_from_ball_speed():
    """A labda gyors, támadó irányú elmozdulása → gyors indítás tanács."""
    cfg = TacticsConfig()
    prev = Frame(t=0, players=[_pl(1, Team.HOME, 20.0, 10.0)],
                 ball=Ball(x=20.0, y=10.0, confidence=1.0))
    # +0.5 m/frame * 25 fps = 12.5 m/s támadó irányban (a +x felé)
    cur = Frame(t=1, players=[_pl(1, Team.HOME, 20.5, 10.0)],
                ball=Ball(x=20.5, y=10.0, confidence=1.0))
    sugg = suggest_for_frame(cur, cfg, prev_frame=prev, fps=25.0)
    assert any(s.category == "tempo" and "indítás" in s.text for s in sugg)


def test_suggestions_sorted_by_priority():
    """A javaslatok prioritás szerint csökkenő sorrendben jönnek."""
    players = [
        _pl(1, Team.HOME, 30.0, 10.0),
        _pl(2, Team.HOME, 32.0, 4.0),
        _pl(11, Team.AWAY, 34.0, 10.0),
    ]
    frame = Frame(t=0, players=players, ball=Ball(x=30.0, y=10.0, confidence=1.0))
    sugg = suggest_for_frame(frame, TacticsConfig())
    prios = [s.priority for s in sugg]
    assert prios == sorted(prios, reverse=True)


def test_timeline_matches_frame_count():
    """A coaching_timeline minden frame-hez ad egy (nem üres) javaslat-listát."""
    frames = [
        Frame(t=i, players=[_pl(1, Team.HOME, 30.0, 10.0)],
              ball=Ball(x=30.0, y=10.0, confidence=1.0))
        for i in range(4)
    ]
    tl = coaching_timeline(Match(_meta(), frames))
    assert len(tl) == 4
    assert all(len(fr) >= 1 for fr in tl)
    # a szótár-alak tartalmazza a kulcsokat
    assert {"priority", "category", "text"} <= set(tl[0][0].keys())


# ---- Belső segédek közvetlenül (második kör) --------------------------------

def test_field_players_a_kapus_nelkul():
    """A csapat mezőnyjátékosai: a saját kaputól 2 m-en belül álló
    játékos kapusnak számít és kimarad (szerep-jelölés nélkül is); a
    másik csapat nem keveredik bele."""
    from handball.pipeline.coaching import _field_players

    cfg = TacticsConfig()
    frame = Frame(t=0, players=[
        _pl(1, Team.AWAY, 39.0, 10.0),      # kapus (1 m a x=40 kaputól)
        _pl(2, Team.AWAY, 38.0, 10.0),      # pont 2 m: még kapus
        _pl(3, Team.AWAY, 34.0, 8.0), _pl(4, Team.AWAY, 34.0, 12.0),
        _pl(11, Team.HOME, 30.0, 10.0),
        _pl(12, Team.HOME, 1.0, 10.0),      # a hazai kapus
    ], ball=None)
    assert [p.track_id for p in _field_players(frame, Team.AWAY, cfg)] == [3, 4]
    assert [p.track_id for p in _field_players(frame, Team.HOME, cfg)] == [11]
    assert _field_players(Frame(t=0, players=[], ball=None), Team.HOME,
                          cfg) == []


def test_side_label_a_palya_szelessege_menten():
    """A pálya szélessége (0..20 m) mentén: az alsó harmad "bal oldalon",
    a felső "jobb oldalon", köztük "középen"."""
    from handball.pipeline.coaching import _side_label

    assert _side_label(2.0) == "bal oldalon"
    assert _side_label(10.0) == "középen"
    assert _side_label(18.0) == "jobb oldalon"
    assert _side_label(6.5) == "bal oldalon" and _side_label(6.7) == "középen"
    assert _side_label(13.1) == "középen" and _side_label(13.3) == "jobb oldalon"


def test_formation_suggestion_formahoz_illo_tanacs():
    """Minden ismert védőformához saját támadó tanács jár (3-as
    prioritással); ismeretlen / nem tipikus formánál általános tanács a
    forma nevével, alacsonyabb prioritással."""
    from handball.pipeline.coaching import _formation_suggestion

    for forma, kulcsszo in (("6-0", "9 m-es lövést"), ("5-1", "előretolt"),
                            ("4-2", "középső rés"), ("3-2-1", "beállót"),
                            ("3-3", "széles járatás")):
        s = _formation_suggestion(forma)
        assert (s.priority, s.category) == (3, "forma"), forma
        assert s.text.startswith(forma) or forma in s.text
        assert kulcsszo in s.text, forma
    egyeb = _formation_suggestion("4-1-0 (hátsó-közép-előre)")
    assert (egyeb.priority, egyeb.category) == (2, "forma")
    assert egyeb.text == ("Védőforma: 4-1-0 (hátsó-közép-előre) — keresd a "
                          "legüresebb sávot.")


def test_ball_speed_toward_attack_tamado_iranyu_sebesseg():
    """A labda sebessége a TÁMADOTT kapu felé (m/s): a hazainál a +x a
    pozitív, a vendégnél a −x; visszafelé negatív; előző kocka vagy labda
    nélkül 0."""
    from handball.pipeline.coaching import _ball_speed_toward_attack

    cfg = TacticsConfig()

    def kocka(x):
        return Frame(t=0, players=[], ball=None if x is None
                     else Ball(x=x, y=10.0, confidence=1.0))

    elott, most = kocka(20.0), kocka(20.4)
    assert abs(_ball_speed_toward_attack(most, elott, Team.HOME, cfg, 25.0)
               - 10.0) < 1e-9
    assert abs(_ball_speed_toward_attack(most, elott, Team.AWAY, cfg, 25.0)
               + 10.0) < 1e-9
    assert abs(_ball_speed_toward_attack(elott, most, Team.AWAY, cfg, 25.0)
               - 10.0) < 1e-9
    assert _ball_speed_toward_attack(most, None, Team.HOME, cfg, 25.0) == 0.0
    assert _ball_speed_toward_attack(kocka(None), elott, Team.HOME, cfg,
                                     25.0) == 0.0
    assert _ball_speed_toward_attack(most, kocka(None), Team.HOME, cfg,
                                     25.0) == 0.0


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
