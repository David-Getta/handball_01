"""A hatókörös elsődleges gyorsítótár (primitive_cache) tesztjei."""
from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                      PlayerPosition, Team)
from handball.pipeline.event_detection import EventType, detect_shots
from handball.pipeline.primitive_cache import (active_match, cached,
                                               memoize_primitive,
                                               primitive_cache)
from handball.pipeline.tactics import TacticsConfig


def _meta():
    return MatchMeta(match_id="pc", home_team="H", away_team="A", fps=25.0)


def _goal_match():
    """Egy hazai gól: a labda áthalad a gólvonalon a kapufák között."""
    frames = []
    for i in range(60):
        x = 20.0 + i * 0.4
        frames.append(Frame(t=i, players=[
            PlayerPosition(track_id=1, team=Team.HOME, x=min(x, 38.0), y=10.0),
        ], ball=Ball(x=x, y=10.0, confidence=1.0)))
    return Match(_meta(), frames)


def test_cache_runs_the_measurement_once():
    """A hatókörön belül a becsomagolt mérés csak egyszer fut le."""
    calls = []

    @memoize_primitive("teszt_mérés")
    def measure(match, config=None):
        calls.append(1)
        return [len(match.frames)]

    m = _goal_match()
    with primitive_cache(m):
        first = measure(m)
        second = measure(m)
    assert first == second
    assert len(calls) == 1, calls


def test_no_cache_without_scope():
    """Hatókör nélkül minden hívás lefut — nincs elavuló gyorsítótár."""
    calls = []

    @memoize_primitive("teszt_mérés2")
    def measure(match, config=None):
        calls.append(1)
        return [len(match.frames)]

    m = _goal_match()
    measure(m)
    measure(m)
    assert len(calls) == 2, calls
    assert active_match() is None


def test_different_config_is_a_different_entry():
    """Más beállítás más eredmény — a kulcs tartalmazza a konfigurációt."""
    calls = []

    @memoize_primitive("teszt_mérés3")
    def measure(match, config=None):
        calls.append(config)
        return [getattr(config, "possession_radius_m", None)]

    m = _goal_match()
    with primitive_cache(m):
        a = measure(m, TacticsConfig(possession_radius_m=3.0))
        b = measure(m, TacticsConfig(possession_radius_m=5.0))
        c = measure(m, TacticsConfig(possession_radius_m=3.0))
    assert a == [3.0] and b == [5.0] and c == [3.0]
    assert len(calls) == 2, calls  # a harmadik hívás a gyorsítótárból jött


def test_other_match_is_not_served_from_the_cache():
    """A hatókör a meccshez kötött: másik meccs mérése normálisan fut."""
    calls = []

    @memoize_primitive("teszt_mérés4")
    def measure(match, config=None):
        calls.append(match.meta.match_id)
        return [match.meta.match_id]

    m = _goal_match()
    other = Match(MatchMeta(match_id="masik", home_team="H", away_team="A",
                            fps=25.0), list(m.frames))
    with primitive_cache(m):
        assert measure(m) == ["pc"]
        assert measure(other) == ["masik"]
        assert measure(other) == ["masik"]  # nem gyorsítótárazott
    assert calls == ["pc", "masik", "masik"], calls


def test_events_are_copies_between_layers():
    """A kiadott események másolatok: az egyik réteg jelölése nem szivárog."""
    m = _goal_match()
    with primitive_cache(m):
        first = detect_shots(m)
        goals = [e for e in first if e.type == EventType.GOAL]
        assert goals, first  # a mintameccsen van gól
        goals[0].detail = {"jelolt": True}
        second = detect_shots(m)
    assert all((e.detail or {}).get("jelolt") is None for e in second)


def test_reentrant_scope_keeps_the_outer_cache():
    """Beágyazott hatókör ugyanarra a meccsre nem indít új gyorsítótárat."""
    calls = []

    @memoize_primitive("teszt_mérés5")
    def measure(match, config=None):
        calls.append(1)
        return [1]

    m = _goal_match()
    with primitive_cache(m):
        measure(m)
        with primitive_cache(m):
            measure(m)
        measure(m)
    assert len(calls) == 1, calls


def test_scope_is_closed_on_error():
    """Kivétel esetén is bezárul a hatókör — nem marad utána gyorsítótár."""
    m = _goal_match()
    try:
        with primitive_cache(m):
            assert active_match() is m
            raise RuntimeError("szándékos hiba")
    except RuntimeError:
        pass
    assert active_match() is None


def test_cached_helper_without_scope_just_computes():
    """A `cached` segédfüggvény hatókör nélkül egyszerűen kiszámol."""
    m = _goal_match()
    calls = []

    def compute():
        calls.append(1)
        return [1, 2]

    assert cached("x", m, None, compute) == [1, 2]
    assert cached("x", m, None, compute) == [1, 2]
    assert len(calls) == 2, calls


def _gk_match():
    """Kapussal értelmezhető meccs: egy hazai játékos végig a kapujában."""
    frames = []
    for i in range(250):
        frames.append(Frame(t=i, players=[
            PlayerPosition(track_id=1, team=Team.HOME, x=1.0, y=10.0),
            PlayerPosition(track_id=2, team=Team.HOME, x=20.0, y=10.0),
        ], ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    return Match(_meta(), frames)


def test_scope_marks_goalkeepers_up_front():
    """A hatókör NYITÁSAKOR megtörténik a kapus-jelölés.

    Enélkül ugyanaz a réteg más számot ad attól függően, hányadikként
    értékeltük ki (a kapust nem számolja védőnek, birtokosnak,
    lövőnek) — ezt mérte a docs/SORREND_FUGGES.md. A jelölés a hatókör
    elején tehát SORREND-FÜGGETLENNÉ teszi az összeállítást.
    """
    m = _gk_match()
    assert not any(p.role == "kapus" for f in m.frames for p in f.players)
    with primitive_cache(m):
        assert any(p.role == "kapus" for f in m.frames for p in f.players), \
            "a hatókör nyitásakor meg kell történnie a jelölésnek"


def test_role_change_invalidates_the_cache():
    """A szerep megváltozása után a mérés ÚJRA lefut.

    Több réteg a szerepből dolgozik (`role == "kapus"`), és a szerep
    menet közben is változhat (pl. kapus-csere felismerése). A
    gyorsítótár ezért a szerep-nemzedéket is kulcsolja: aki a változás
    ELŐTT mért, ne kapja vissza ugyanazt UTÁNA.
    """
    from handball.pipeline.primitive_cache import mark_roles_changed

    seen = []

    @memoize_primitive("szerep_függő_mérés")
    def measure(match, config=None):
        roles = {p.role for f in match.frames for p in f.players}
        seen.append(roles)
        return [sorted(r or "" for r in roles)]

    m = _gk_match()
    with primitive_cache(m):
        before = measure(m)
        assert measure(m) == before and len(seen) == 1  # gyorsítótárból
        for f in m.frames:                    # szerep-változás menet közben
            for p in f.players:
                if p.track_id == 2:
                    p.role = "beálló"
        mark_roles_changed()
        after = measure(m)
    assert len(seen) == 2, seen  # a változás után újra kellett mérni
    assert after != before, (before, after)


def test_repeated_role_marking_keeps_the_cache():
    """Ismételt kapus-jelölés (ami már nem változtat) nem dobja el a tárat."""
    from handball.pipeline.goalkeeper import detect_goalkeepers

    calls = []

    @memoize_primitive("szerep_függő_mérés2")
    def measure(match, config=None):
        calls.append(1)
        return [1]

    m = _gk_match()
    detect_goalkeepers(m)  # a szerepek MÁR meg vannak jelölve
    with primitive_cache(m):
        measure(m)
        detect_goalkeepers(m)  # nem változtat semmit
        measure(m)
    assert len(calls) == 1, calls


def test_frame_level_cache_computes_once():
    """A kocka-szintű memoizálás kockánként egyszer számol a hatókörben."""
    from handball.pipeline.primitive_cache import cached_frame

    calls = []
    m = _goal_match()
    f0, f1 = m.frames[0], m.frames[1]
    cfg = TacticsConfig()

    def measure(frame):
        return cached_frame("teszt_kocka", frame, cfg,
                            lambda: (calls.append(frame.t), frame.t)[1])

    with primitive_cache(m):
        assert measure(f0) == 0
        assert measure(f0) == 0
        assert measure(f1) == 1
    assert calls == [0, 1], calls


def test_frame_level_cache_is_off_without_scope():
    """Hatókör nélkül a kocka-szintű memoizálás sem tárol."""
    from handball.pipeline.primitive_cache import cached_frame

    calls = []
    m = _goal_match()
    cfg = TacticsConfig()
    for _ in range(2):
        cached_frame("teszt_kocka2", m.frames[0], cfg,
                     lambda: calls.append(1))
    assert len(calls) == 2, calls


def test_az_alapertelmezett_beallitas_kulcsa_azonos_a_none_eval():
    """`réteg(meccs)` és `réteg(meccs, TacticsConfig())` UGYANAZ.

    A rétegek `config=None` esetén maguk állítanak elő egy
    alapértelmezett beállítást (`config or TacticsConfig()`), tehát a
    két hívás szó szerint ugyanazt számolja. Külön kulccsal viszont
    kétszer futott le — mérve az edzői összefoglalóban a
    teendő-rangsoron.
    """
    from handball.pipeline.primitive_cache import _arg_key
    from handball.pipeline.tactics import TacticsConfig

    assert _arg_key(None) == _arg_key(TacticsConfig())


def test_a_modositott_beallitas_kulcsa_MAS():
    """A normalizálás nem moshatja össze a KÜLÖNBÖZŐ beállításokat —
    az azt jelentené, hogy egy réteg más beállítás eredményét olvassa."""
    from handball.pipeline.primitive_cache import _arg_key
    from handball.pipeline.tactics import TacticsConfig

    mas = TacticsConfig()
    mas.possession_radius_m = mas.possession_radius_m + 1.0
    assert _arg_key(mas) != _arg_key(None)
    assert _arg_key(mas) != _arg_key(TacticsConfig())


def test_a_hatokor_egyszer_szamol_akkor_is_ha_az_egyik_hivo_atadja():
    """A tényleges viselkedés: két hívás, egy számolás."""
    from handball.pipeline.primitive_cache import (memoize_primitive,
                                                   primitive_cache)
    from handball.pipeline.tactics import TacticsConfig

    hivasok = []

    @memoize_primitive("proba_reteg")
    def proba(match, config=None):
        hivasok.append(1)
        return {"home": {}, "away": {}}

    m = Match(_meta(), [])
    with primitive_cache(m):
        proba(m)                       # config nélkül
        proba(m, None)                 # kifejezett None
        proba(m, TacticsConfig())      # kifejezett alapértelmezés
    assert len(hivasok) == 1, f"{len(hivasok)} számolás egy helyett"
