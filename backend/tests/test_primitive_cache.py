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


def test_a_melyen_masolt_reteg_egyszer_fut_es_nem_szivarog():
    """A sokszor hívott rétegek (pl. sprint_threats) a hatókörben
    meccsenként egyszer futnak, és MÉLY védő-másolatot adnak: ha egy
    hívó a beágyazott listát módosítja, a következő hívó eredménye
    érintetlen marad (a sekély másolat a belső listát megosztaná)."""
    import copy as _copy

    from handball.pipeline import stats
    from handball.pipeline.primitive_cache import primitive_cache
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=120, fps=25.0, seed=3,
                              shots_per_min=8.0)
    hivasok = []
    eredeti = stats.sprint_threats.uncached

    def szamlalo(*a, **k):
        hivasok.append(1)
        return eredeti(*a, **k)

    with primitive_cache(m):
        stats.sprint_threats.__wrapped__ = szamlalo  # noqa: B010
        try:
            elso = stats.sprint_threats(m)
            tiszta = _copy.deepcopy(elso)
            # Mély módosítás az első hívó példányán.
            for side in elso.values():
                if isinstance(side, dict):
                    for v in side.values():
                        if isinstance(v, list):
                            v.append({"szennyezes": True})
                    side["szennyezes"] = True
            masodik = stats.sprint_threats(m)
        finally:
            del stats.sprint_threats.__wrapped__
    assert masodik == tiszta


def test_a_tobbszor_hivott_retegek_a_hatokorben_egyszer_szamolnak():
    """A sebesség-profil (docs/SEBESSEG.md) szerint egy csomagban a
    kapus-idővonal 23-szor, a védekezés-tanulás mintája 14-szer, a
    kettőzőpárosok és a visszatérő figurák 10-szer, a rotáció-mélység
    és a szorításbeli döntés 5-ször, a falválasztás 4-szer, a kit-kinek
    3-szor, a sorozat-okok 2-szer számolódtak újra — mind tiszta
    réteg (meccs → adat). Mostantól memoizáltak: a hatókörben egyszer
    futnak, minden hívó SAJÁT másolatot kap, hatókör nélkül a nyers
    függvény fut."""
    from handball.models.tracking import Team
    from handball.pipeline import (decisions, defense, goalkeeper, momentum,
                                   play_simulation, stats)
    from handball.pipeline.primitive_cache import primitive_cache
    from handball.pipeline.tactics import TacticsConfig
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=20, fps=25.0 / 3, seed=1,
                              shots_per_min=6.0)
    hivasok = [
        (play_simulation._tanulas_minta, (Team.HOME, TacticsConfig())),
        (play_simulation.defense_system_choice, ()),
        (play_simulation.shooter_defender_matchup, ()),
        (goalkeeper.goalkeeper_timeline, ()),
        (defense.doubling_pair_roles, ()),
        (stats.rotation_depth, ()),
        (decisions.pressure_decision_quality, ()),
        (momentum.annotate_runs, ()),
    ]
    for fn, args in hivasok:
        assert hasattr(fn, "uncached"), fn.__name__
        nyers = fn.uncached(m, *args)
        with primitive_cache(m):
            elso = fn(m, *args)
            masodik = fn(m, *args)
        assert elso == masodik == nyers, fn.__name__
        assert elso is not masodik, fn.__name__           # védő-másolat


def test_az_esemeny_masolat_fuggetlen_es_egyenlo():
    """A `copy_events` gyors sekély másolata (copy.copy) ugyanazt adja,
    mint a korábbi dataclasses.replace: mezőnként egyenlő, de független
    példány — a hívó jelölése nem szivárog a gyorsítótárba."""
    from dataclasses import replace

    from handball.pipeline.event_detection import detect_events
    from handball.pipeline.primitive_cache import copy_events
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=30, fps=25.0 / 3, seed=2,
                              shots_per_min=6.0)
    events = detect_events(m)
    assert events, "a próba-meccsen nincs esemény"
    masolat = copy_events(events)
    assert masolat == [replace(e) for e in events]
    assert all(a is not b for a, b in zip(events, masolat))
    assert all(type(a) is type(b) for a, b in zip(events, masolat))


# ---- A védő-másolatok (copy_rows / copy_by_id / copy_sides / …) -------------

def test_copy_rows_a_sorok_fuggetlenek_a_tartalom_azonos():
    """A dict-sorok másolata egyenlő, de független: a hívó jelölése nem
    látszik az eredetin. A nem-dict elem változatlanul megy át; üres
    listából üres lista lesz (nem None)."""
    from handball.pipeline.primitive_cache import copy_rows

    eredeti = [{"start_frame": 0, "home": 6}, {"start_frame": 250, "home": 5},
               "nem-sor", 7]
    masolat = copy_rows(eredeti)
    assert masolat == eredeti and masolat is not eredeti
    assert masolat[0] is not eredeti[0] and masolat[1] is not eredeti[1]
    masolat[0]["home"] = 99
    masolat.append({"start_frame": 500})
    assert eredeti[0]["home"] == 6 and len(eredeti) == 4
    assert masolat[2] == "nem-sor" and masolat[3] == 7
    assert copy_rows([]) == []


def test_copy_by_id_az_adatosztalyt_masolja_a_tobbit_atengedi():
    """{azonosító: adatosztály}: a példányok függetlenek, a mezők
    egyenlők. A sima érték és maga az OSZTÁLY (nem példány) változatlanul
    megy át; None-ból üres szótár lesz."""
    from dataclasses import dataclass

    from handball.pipeline.primitive_cache import copy_by_id

    @dataclass
    class Stat:
        goals: int = 0
        shots: int = 0

    eredeti = {7: Stat(goals=3, shots=5), 9: Stat(), "megj": "szöveg",
               "tipus": Stat}
    masolat = copy_by_id(eredeti)
    assert masolat == eredeti and masolat is not eredeti
    assert masolat[7] is not eredeti[7] and masolat[9] is not eredeti[9]
    masolat[7].goals = 99
    assert eredeti[7].goals == 3
    assert masolat["megj"] == "szöveg" and masolat["tipus"] is Stat
    assert copy_by_id(None) == {} and copy_by_id({}) == {}


def test_copy_sides_csapatonkent_fuggetlen_szotar():
    """{oldal: {kulcs: érték}}: a belső szótár független; a hiányzó
    (None) oldalból üres szótár, a None bemenetből üres szótár lesz."""
    from handball.pipeline.primitive_cache import copy_sides

    eredeti = {"home": {"attacks": 8, "verdict": "gyors"}, "away": None}
    masolat = copy_sides(eredeti)
    assert masolat == {"home": {"attacks": 8, "verdict": "gyors"}, "away": {}}
    assert masolat["home"] is not eredeti["home"]
    masolat["home"]["verdict"] = None
    assert eredeti["home"]["verdict"] == "gyors"
    assert copy_sides(None) == {} and copy_sides({}) == {}


def test_copy_nested_ket_szintig_masol():
    """{oldal: {azonosító: dict}}: a játékos-sor is független (a
    copy_sides itt megosztaná); None szint → üres szótár."""
    from handball.pipeline.primitive_cache import copy_nested, copy_sides

    eredeti = {"home": {7: {"role": "irányító"}, 9: {"role": "beálló"}},
               "away": None}
    masolat = copy_nested(eredeti)
    assert masolat == {"home": eredeti["home"], "away": {}}
    assert masolat["home"][7] is not eredeti["home"][7]
    masolat["home"][7]["role"] = "kapus"
    assert eredeti["home"][7]["role"] == "irányító"
    # Ellenpróba: a sekély (egyszintű) másolat a játékos-sort megosztja.
    sekely = copy_sides(eredeti)
    assert sekely["home"][9] is eredeti["home"][9]
    assert copy_nested(None) == {} and copy_nested({}) == {}


def test_copy_deep_a_beagyazott_listat_sem_osztja_meg():
    """Tetszőleges mélység: a belső lista és annak sorai is függetlenek;
    a skalár és a None változatlan."""
    from handball.pipeline.primitive_cache import copy_deep

    eredeti = {"home": {"players": [{"id": 7, "zones": [1, 2]}],
                        "verdict": None}}
    masolat = copy_deep(eredeti)
    assert masolat == eredeti
    masolat["home"]["players"][0]["zones"].append(3)
    masolat["home"]["players"].append({"id": 9})
    assert eredeti["home"]["players"] == [{"id": 7, "zones": [1, 2]}]
    assert copy_deep(None) is None and copy_deep(5) == 5


def test_a_masolo_dekoratorral_a_hivo_jelolese_nem_szivarog():
    """A `copy=copy_rows`-zal becsomagolt mérés a hatókörben egyszer fut,
    de minden hívó SAJÁT sorokat kap: az egyik jelölése a másiknál nem
    látszik."""
    from handball.pipeline.primitive_cache import copy_rows

    calls = []

    @memoize_primitive("teszt_sorok", copy=copy_rows)
    def measure(match, config=None):
        calls.append(1)
        return [{"start_frame": 0, "home": 6}]

    m = _goal_match()
    with primitive_cache(m):
        elso = measure(m)
        elso[0]["home"] = 99
        masodik = measure(m)
    assert len(calls) == 1
    assert masodik == [{"start_frame": 0, "home": 6}]


# ---- Kézi hatókör (open_scope / close_scope) ---------------------------------

def test_open_scope_ugyanugy_gyorsit_mint_a_with_blokk():
    """A kézzel nyitott hatókörben a mérés egyszer fut, a meccs az aktív
    meccs; a bezárás után nincs hatókör, a mérés újra lefut."""
    from handball.pipeline.primitive_cache import close_scope, open_scope

    calls = []

    @memoize_primitive("teszt_kezi_hatokor")
    def measure(match, config=None):
        calls.append(1)
        return [len(match.frames)]

    m = _goal_match()
    assert active_match() is None
    token = open_scope(m)
    try:
        assert token is not None
        assert active_match() is m
        assert measure(m) == measure(m) == [60]
        assert len(calls) == 1
    finally:
        close_scope(token)
    assert active_match() is None
    measure(m)
    assert len(calls) == 2


def test_open_scope_nyitaskor_megjeloli_a_kapust():
    """A kézi nyitás is elvégzi a kapus-jelölést — a `with` blokkal
    azonos, sorrend-független kiindulás."""
    from handball.pipeline.primitive_cache import close_scope, open_scope

    m = _gk_match()
    assert not any(p.role == "kapus" for f in m.frames for p in f.players)
    token = open_scope(m)
    try:
        assert any(p.role == "kapus" for f in m.frames for p in f.players)
    finally:
        close_scope(token)


def test_open_scope_ujra_belepve_none_es_a_kulso_tar_megmarad():
    """Ha a meccsre már nyitva van hatókör, az újabb nyitás None-t ad, és
    a None bezárása nem művelet: a külső hatókör és a tára megmarad."""
    from handball.pipeline.primitive_cache import close_scope, open_scope

    calls = []

    @memoize_primitive("teszt_kezi_ujra")
    def measure(match, config=None):
        calls.append(1)
        return [1]

    m = _goal_match()
    with primitive_cache(m):
        measure(m)
        belso = open_scope(m)
        assert belso is None
        measure(m)
        close_scope(belso)               # None → nem zár be semmit
        assert active_match() is m
        measure(m)
    assert len(calls) == 1
    assert active_match() is None

    # Fordítva is: kézi külső hatókörben a `with` blokk nem nyit újat.
    kulso = open_scope(m)
    try:
        with primitive_cache(m):
            measure(m)
        assert active_match() is m       # a with nem zárta be a külsőt
        measure(m)
    finally:
        close_scope(kulso)
    assert len(calls) == 2
    assert active_match() is None


def test_open_scope_masik_meccsre_beagyazva_visszaall_a_kulso():
    """Más meccsre nyitva új (belső) hatókör nyílik; a bezárása a külső
    meccs hatókörét ÉS annak már kiszámolt méréseit adja vissza."""
    from handball.pipeline.primitive_cache import close_scope, open_scope

    calls = []

    @memoize_primitive("teszt_kezi_beagyazva")
    def measure(match, config=None):
        calls.append(match.meta.match_id)
        return [match.meta.match_id]

    a, b = _goal_match(), _goal_match()
    b.meta.match_id = "masik"
    ta = open_scope(a)
    try:
        measure(a)
        tb = open_scope(b)
        try:
            assert tb is not None and active_match() is b
            assert measure(b) == ["masik"]
        finally:
            close_scope(tb)
        assert active_match() is a
        assert measure(a) == ["pc"]
    finally:
        close_scope(ta)
    assert calls == ["pc", "masik"]      # a külső mérés nem futott újra
    assert active_match() is None
