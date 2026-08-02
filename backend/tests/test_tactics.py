"""
Tesztek a taktikai rétegre (tactics.py): birtoklás, fázis, védekezési forma.

Kézzel összerakott frame-ekkel, videó nélkül. A pálya 40x20 m; a HAZAI a +x (x=40)
kapu felé támad, saját kapuja x=0. (Alapértelmezett TacticsConfig.)

Futtatás:
    python tests/test_tactics.py
"""

from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, Ball, Team, PositionSource,
)
from handball.pipeline.tactics import (
    TacticsConfig, possession_team, classify_phase, Phase,
    phase_percentages, detect_formation,
    count_possession_segments, compute_tempo, team_style_profile,
    slow_attacks, attack_sides, efficiency_vs_formation,
)


def _pl(track_id, team, x, y):
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0)


def test_possession_nearest_within_radius():
    """A labdát a hozzá legközelebbi (sugáron belüli) játékos csapata birtokolja."""
    cfg = TacticsConfig()
    frame = Frame(t=0, players=[
        _pl(1, Team.HOME, 30.0, 10.0),   # 1 m-re a labdától
        _pl(11, Team.AWAY, 25.0, 10.0),  # távolabb
    ], ball=Ball(x=31.0, y=10.0, confidence=1.0))
    assert possession_team(frame, cfg) == Team.HOME


def test_possession_none_when_ball_far():
    """Ha a legközelebbi játékos is messze van, nincs birtokos (szabad labda)."""
    cfg = TacticsConfig(possession_radius_m=3.0)
    frame = Frame(t=0, players=[_pl(1, Team.HOME, 10.0, 10.0)],
                  ball=Ball(x=30.0, y=10.0, confidence=1.0))
    assert possession_team(frame, cfg) is None


def test_phase_home_attack():
    """Hazai birtoklás a hazai támadó térfelén (x>20) → HAZAI_TÁMADÁS."""
    cfg = TacticsConfig()
    frame = Frame(t=0, players=[_pl(1, Team.HOME, 30.0, 10.0)],
                  ball=Ball(x=30.0, y=10.0, confidence=1.0))
    assert classify_phase(frame, cfg) == Phase.HOME_ATTACK


def test_phase_transition_in_own_half():
    """Hazai birtoklás a SAJÁT térfelén (x<20) → ÁTMENET (felépítés)."""
    cfg = TacticsConfig()
    frame = Frame(t=0, players=[_pl(1, Team.HOME, 10.0, 10.0)],
                  ball=Ball(x=10.0, y=10.0, confidence=1.0))
    assert classify_phase(frame, cfg) == Phase.TRANSITION


def test_phase_away_attack():
    """Vendég birtoklás a vendég támadó térfelén (x<20) → VENDÉG_TÁMADÁS."""
    cfg = TacticsConfig()
    frame = Frame(t=0, players=[_pl(11, Team.AWAY, 8.0, 10.0)],
                  ball=Ball(x=8.0, y=10.0, confidence=1.0))
    assert classify_phase(frame, cfg) == Phase.AWAY_ATTACK


def test_phase_unknown_without_ball():
    """Labda nélkül a fázis UNKNOWN."""
    cfg = TacticsConfig()
    frame = Frame(t=0, players=[_pl(1, Team.HOME, 30.0, 10.0)], ball=None)
    assert classify_phase(frame, cfg) == Phase.UNKNOWN


def test_phase_percentages_sum_100():
    """A fázis-megoszlás összege 100% (van labdás frame)."""
    cfg = TacticsConfig()
    frames = [
        Frame(t=0, players=[_pl(1, Team.HOME, 30.0, 10.0)], ball=Ball(x=30, y=10, confidence=1)),
        Frame(t=1, players=[_pl(11, Team.AWAY, 8.0, 10.0)], ball=Ball(x=8, y=10, confidence=1)),
    ]
    pct = phase_percentages(Match(MatchMeta(match_id="t", home_team="A", away_team="B", fps=25), frames))
    assert abs(sum(pct.values()) - 100.0) < 1e-9
    assert pct[Phase.HOME_ATTACK.value] == 50.0
    assert pct[Phase.AWAY_ATTACK.value] == 50.0


def _defense(positions):
    """Védekező (AWAY) frame: a megadott (x,y) helyeken álló védőkből.
    AWAY saját kapuja x=40, tehát a kaputól mért mélység = 40 - x."""
    players = [_pl(11 + i, Team.AWAY, x, y) for i, (x, y) in enumerate(positions)]
    return Frame(t=0, players=players, ball=None)


def test_formation_6_0():
    """Hat védő a 6 m-es vonalon (x≈34, mélység≈6) → 6-0."""
    frame = _defense([(34.0, y) for y in (3, 6, 9, 11, 14, 17)])
    res = detect_formation(frame, Team.AWAY)
    assert res.label == "6-0"
    assert res.back == 6 and res.mid == 0 and res.high == 0


def test_formation_5_1():
    """Öt hátul + egy előretolt (x≈30.5, mélység≈9.5) → 5-1."""
    frame = _defense([(34.0, 3), (34.0, 6), (34.0, 9), (34.0, 11), (34.0, 14), (30.5, 10)])
    res = detect_formation(frame, Team.AWAY)
    assert res.label == "5-1"
    assert res.back == 5 and (res.mid + res.high) == 1


def test_formation_3_2_1():
    """Három lépcső: 3 hátul, 2 közép, 1 előretolt → 3-2-1."""
    frame = _defense([
        (34.0, 6), (34.0, 10), (34.0, 14),   # hátsó (mélység 6)
        (30.5, 8), (30.5, 12),               # közép (mélység 9.5)
        (27.0, 10),                          # előretolt (mélység 13)
    ])
    res = detect_formation(frame, Team.AWAY)
    assert res.label == "3-2-1"
    assert (res.back, res.mid, res.high) == (3, 2, 1)


def test_formation_excludes_goalkeeper():
    """A kaput nagyon közelről őrző játékost kapusnak vesszük (kihagyjuk)."""
    # 6 mezőnyvédő a 6 m-en + 1 kapus a kapunál (x≈39.5, mélység 0.5).
    frame = _defense([(34.0, y) for y in (3, 6, 9, 11, 14, 17)] + [(39.5, 10)])
    res = detect_formation(frame, Team.AWAY)
    assert res.defenders == 6   # a kapust nem számoltuk
    assert res.label == "6-0"


def _meta(fps=25.0):
    return MatchMeta(match_id="t", home_team="A", away_team="B", fps=fps)


def test_count_possession_segments():
    """Birtoklás A,A,B,B,A → 3 külön szakasz (csapatváltáskor új)."""
    seq = [Team.HOME, Team.HOME, Team.AWAY, Team.AWAY, Team.HOME]
    frames = []
    for i, team in enumerate(seq):
        # a labdát a birtokló csapat játékosa mellé tesszük
        x = 30.0 if team == Team.HOME else 8.0
        frames.append(Frame(t=i, players=[_pl(1, team, x, 10.0)],
                            ball=Ball(x=x, y=10.0, confidence=1.0)))
    assert count_possession_segments(Match(_meta(), frames)) == 3


def test_avg_ball_speed():
    """A labda 1 m/frame, 25 fps → 25 m/s átlagsebesség."""
    frames = [
        Frame(t=i, players=[_pl(1, Team.HOME, 30.0, 10.0)],
              ball=Ball(x=float(i), y=0.0, confidence=1.0))
        for i in range(3)  # x = 0,1,2 → 2 m elmozdulás 2 lépésben
    ]
    tempo = compute_tempo(Match(_meta(fps=25.0), frames))
    assert abs(tempo.avg_ball_speed_ms - 25.0) < 1e-9


def test_avg_attack_duration():
    """Három egymást követő hazai-támadás frame → 3/fps mp átlagos hossz."""
    frames = [
        Frame(t=i, players=[_pl(1, Team.HOME, 30.0, 10.0)],
              ball=Ball(x=30.0, y=10.0, confidence=1.0))
        for i in range(3)
    ]
    tempo = compute_tempo(Match(_meta(fps=25.0), frames))
    assert abs(tempo.avg_attack_duration_s - 3.0 / 25.0) < 1e-9


def test_team_style_profile_structure():
    """A stílusprofil tartalmazza a fázis-, forma- és tempó-részt."""
    frames = [Frame(t=0, players=[_pl(1, Team.HOME, 30.0, 10.0)],
                    ball=Ball(x=30.0, y=10.0, confidence=1.0))]
    prof = team_style_profile(Match(_meta(), frames))
    assert "phase_percentages" in prof
    assert "defense_formations" in prof
    assert "tempo" in prof and "possessions" in prof["tempo"]


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


def test_slow_attacks_flags_long_possession():
    """40 mp-es hazai támadó-szakasz → elhúzódó; a 10 mp-es nem az."""
    meta = MatchMeta(match_id="sa", home_team="H", away_team="A", fps=25.0)
    frames = []
    t = 0
    # 40 mp hazai támadás a támadó térfélen (x=30), birtoklással.
    for _ in range(int(40 * 25)):
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 30.0, 10.0)],
                            ball=Ball(x=30.0, y=10.0, confidence=1.0)))
        t += 1
    # Megszakítás (szabad labda a felezőnél, senki a közelben) — új szakasz.
    for _ in range(10):
        frames.append(Frame(t=t, players=[], ball=Ball(x=20.0, y=10.0,
                                                       confidence=1.0)))
        t += 1
    # 10 mp-es második hazai támadás.
    for _ in range(int(10 * 25)):
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 30.0, 10.0)],
                            ball=Ball(x=30.0, y=10.0, confidence=1.0)))
        t += 1
    sa = slow_attacks(Match(meta, frames))
    assert sa["home"]["attacks"] == 2
    assert sa["home"]["slow"] == 1
    assert sa["home"]["slow_pct"] == 50.0
    assert sa["home"]["longest_s"] >= 39.0
    assert sa["away"]["attacks"] == 0


def test_slow_attack_cost_idle_verdict():
    """3 elhúzódó (36 mp-es) hazai támadás gól nélkül → üresjárat."""
    from handball.pipeline.tactics import slow_attack_cost
    meta = MatchMeta(match_id="sac", home_team="H", away_team="A", fps=25.0)
    frames = []
    t = 0
    for _ in range(3):
        # 36 mp hazai támadás a támadó térfélen, birtoklással.
        for _ in range(int(36 * 25)):
            frames.append(Frame(t=t,
                                players=[_pl(1, Team.HOME, 30.0, 10.0)],
                                ball=Ball(x=30.0, y=10.0, confidence=1.0)))
            t += 1
        # Megszakítás: szabad labda a felezőnél — új szakasz kezdődik.
        for _ in range(10):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
            t += 1
    sac = slow_attack_cost(Match(meta, frames))
    assert sac["home"]["slow"] == 3
    assert sac["home"]["scored"] == 0
    assert sac["home"]["scored_pct"] == 0.0
    assert sac["home"]["verdict"] == "az elhúzódó támadásaik üresen zárulnak"
    assert sac["away"]["slow"] == 0
    assert sac["away"]["verdict"] is None


def test_slow_attack_cost_few_samples_none():
    """Egyetlen elhúzódó támadás → kevés minta, nincs ítélet."""
    from handball.pipeline.tactics import slow_attack_cost
    meta = MatchMeta(match_id="sac2", home_team="H", away_team="A", fps=25.0)
    frames = []
    t = 0
    for _ in range(int(36 * 25)):
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 30.0, 10.0)],
                            ball=Ball(x=30.0, y=10.0, confidence=1.0)))
        t += 1
    sac = slow_attack_cost(Match(meta, frames))
    assert sac["home"]["slow"] == 1
    assert sac["home"]["scored_pct"] is None
    assert sac["home"]["verdict"] is None


def test_attack_sides_direction_normalized():
    """A hazai (a +x kapura támadva) y=3-nál játszik → 'bal'; a vendég
    (a -x kapura) ugyanennél az y-nál a SAJÁT jobbján játszik."""
    meta = MatchMeta(match_id="as", home_team="H", away_team="A", fps=25.0)
    frames = []
    t = 0
    # Hazai támadás a +x térfélen, a labda y=3 (alacsony y) sávban.
    for _ in range(50):
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 30.0, 3.0)],
                            ball=Ball(x=30.0, y=3.0, confidence=1.0)))
        t += 1
    # Vendég támadás a -x térfélen, a labda szintén y=3-nál.
    for _ in range(50):
        frames.append(Frame(t=t, players=[_pl(11, Team.AWAY, 10.0, 3.0)],
                            ball=Ball(x=10.0, y=3.0, confidence=1.0)))
        t += 1
    sides = attack_sides(Match(meta, frames))
    assert sides["home"]["bal"] == 100.0
    assert sides["home"]["frames"] == 50
    assert sides["away"]["jobb"] == 100.0
    assert sides["away"]["frames"] == 50


def test_efficiency_vs_formation_buckets_by_defense():
    """A 6-0 fal ellen leadott hazai gól a '6-0' vödörbe kerül."""
    meta = MatchMeta(match_id="ef", home_team="H", away_team="A", fps=25.0)
    frames = []
    t = 0
    # 6-0-s vendég fal a +x kapunál (mint az _attack_60-ban), a lövés
    # előtti szakaszban is látszik.
    def wall():
        return [_pl(20 + j, Team.AWAY, 35.0, float(y))
                for j, y in enumerate([2, 6, 8, 12, 14, 18])]
    for _ in range(20):
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 28.0, 10.0)]
                            + wall(),
                            ball=Ball(x=28.0, y=10.0, confidence=1.0)))
        t += 1
    # Hazai gól a +x kapura.
    for i in range(7):
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 33.0, 10.0)]
                            + wall(),
                            ball=Ball(x=34.0 + i, y=10.0, confidence=1.0)))
        t += 1
    ef = efficiency_vs_formation(Match(meta, frames))
    assert "6-0" in ef["home"]
    assert ef["home"]["6-0"]["shots"] == 1
    assert ef["home"]["6-0"]["goals"] == 1
    assert ef["home"]["6-0"]["goal_pct"] == 100.0
    assert ef["away"] == {}


def test_field_tilt_opponent_half_share():
    """A HAZAI birtoklás 120 kockából 90-szer az ellenfél (x>20) térfelén →
    75% területi fölény; a vendégnek nincs elég birtokos kockája → None."""
    from handball.pipeline.tactics import field_tilt

    frames = []
    for t in range(120):
        x = 30.0 if t < 90 else 10.0  # 90 kocka elöl, 30 hátul
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, x, 10.0)],
                            ball=Ball(x=x, y=10.0, confidence=1.0)))
    ft = field_tilt(Match(_meta(), frames))
    h = ft["home"]
    assert h["frames"] == 120 and h["opp_half_frames"] == 90
    assert h["tilt_pct"] == 75.0
    assert ft["away"]["frames"] == 0 and ft["away"]["tilt_pct"] is None


def test_pass_tempo_counts_passes_per_possession_minute():
    """3 perc hazai birtoklás alatt 70 passz → ~23/perc, "pörgetett";
    rövid mérésnél (2 perc alatt) nincs ítélet."""
    from handball.pipeline.tactics import pass_tempo

    frames = []
    t = 0
    # 70 passz-kör: a labda 1-es ↔ 2-es közt vált (mindkettő HAZAI), a
    # köztes kockák kitöltik a ~2 perc birtoklást (3150 kocka 25 fps-en).
    for k in range(70):
        holder, other = (1, 2) if k % 2 == 0 else (2, 1)
        pos = {1: (22.0, 8.0), 2: (28.0, 12.0)}
        for _ in range(45):  # ~1,8 mp birtoklás passzonként
            hx, hy = pos[holder]
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, *pos[1]), _pl(2, Team.HOME, *pos[2])],
                ball=Ball(x=hx, y=hy, confidence=1.0)))
            t += 1
    m = Match(_meta(), frames)
    pt = pass_tempo(m)
    h = pt["home"]
    assert h["poss_s"] >= 120.0
    assert h["passes"] >= 60
    assert h["per_min"] is not None and h["per_min"] >= 22.0
    assert h["label"] == "pörgetett"
    # A vendégnek nincs birtoklása → nincs ítélet.
    assert pt["away"]["per_min"] is None

    short = Match(_meta(), frames[:1000])  # 40 mp — kevés a méréshez
    assert pass_tempo(short)["home"]["per_min"] is None


def test_tilt_fade_flags_second_half_retreat():
    """Az 1. félidőben végig az ellenfél térfelén, a 2.-ban végig a
    sajáton birtokol a hazai → a tilt 100% → 0%-ra esik; félidő-jel
    nélkül nincs ítélet."""
    from handball.pipeline.tactics import tilt_fade

    fps = 25.0
    frames = []
    t = 0

    def _half(seconds, ball_x):
        # 5 mért hazai játékos a labda körül (a félidő-érzékelő ne
        # lássa alacsony aktivitásnak), a labda a birtokosnál.
        nonlocal t, frames
        players = [_pl(i, Team.HOME, ball_x + 0.5 * (i - 3), 10.0)
                   for i in range(1, 6)]
        players.append(_pl(20, Team.AWAY, 39.0, 3.0))
        for _ in range(int(seconds * fps)):
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=ball_x, y=10.0,
                                          confidence=1.0)))
            t += 1

    _half(200, 30.0)                       # 1. félidő: elöl (x > 20)
    for _ in range(int(90 * fps)):         # szünet
        frames.append(Frame(t=t, players=[], ball=None))
        t += 1
    _half(200, 10.0)                       # 2. félidő: hátul (x < 20)

    tf = tilt_fade(Match(_meta(), frames))
    h = tf["home"]
    assert h["fh_frames"] >= 100 and h["sh_frames"] >= 100
    assert h["fh_opp"] == h["fh_frames"] and h["sh_opp"] == 0
    assert h["drop_pp"] is not None and h["drop_pp"] >= 90.0

    # Félidő-jel nélkül nincs ítélet.
    short = tilt_fade(Match(_meta(), frames[:2000]))
    assert short["home"]["drop_pp"] is None


def test_attack_motion_separates_static_and_fluid():
    """A hazai támadói cikcakkban futnak (~2 m/s), a vendégéi állnak →
    mozgásos vs álló ítélet; kevés mintánál nincs ítélet."""
    from handball.pipeline.tactics import attack_motion

    fps = 25.0
    frames = []
    t = 0

    # Hazai szervezett támadás: 5 játékos együtt cikcakkozik y-ban.
    off = 0.0
    for i in range(1000):
        direction = 1.0 if (i // 25) % 2 == 0 else -1.0
        off += 0.08 * direction
        players = [_pl(k, Team.HOME, 30.0, base + off)
                   for k, base in ((1, 10.0), (2, 4.0), (3, 7.0),
                                   (4, 13.0), (5, 16.0))]
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=30.0, y=10.0 + off,
                                      confidence=1.0)))
        t += 1

    # Vendég szervezett támadás: mindenki áll.
    away = [_pl(10 + k, Team.AWAY, 10.0, 4.0 + 3.0 * k)
            for k in range(5)]
    for _ in range(1000):
        frames.append(Frame(t=t, players=away,
                            ball=Ball(x=10.0, y=10.0, confidence=1.0)))
        t += 1

    am = attack_motion(Match(_meta(), frames))
    h, a = am["home"], am["away"]
    assert h["style"] == "mozgásos" and h["avg_mps"] >= 1.6
    assert a["style"] == "álló" and a["avg_mps"] <= 0.2

    # Kevés minta: nincs ítélet.
    few = attack_motion(Match(_meta(), frames[:200]))
    assert few["home"]["style"] is None


def _fsw_match(walls):
    """Hazai támadás-sorozat: minden elemhez a vendég fal x-koordinátái
    (a vendég kapuja x=40), a támadások közt szünettel."""
    frames = []
    t = 0
    for wall in walls:
        for _ in range(20):
            players = [_pl(1, Team.HOME, 28.0, 10.0)] + [
                _pl(20 + j, Team.AWAY, x, float(y))
                for j, (x, y) in enumerate(zip(wall,
                                               [2, 6, 8, 12, 14, 18]))]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=28.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(10):     # szünet: itt zárul a támadás
            frames.append(Frame(t=t, players=[], ball=None))
            t += 1
    return Match(_meta(), frames)


def test_formation_switching_separates_switchers_from_one_system():
    """Nyolc védekezett támadás felváltva 6-0 és 5-1 → "váltogatós";
    végig 6-0 → "egy rendszer"; kevés támadásnál nincs ítélet."""
    from handball.pipeline.tactics import formation_switching

    flat = [35.0] * 6                     # 6-0: mind a hátsó sávban
    one_up = [35.0] * 5 + [31.0]          # 5-1: egy előretolt védő

    sw = formation_switching(_fsw_match(
        [flat, one_up] * 4))["away"]
    assert sw["attacks"] == 8
    assert sw["main"] in ("6-0", "5-1")
    assert sw["switches"] == 7
    assert sw["switch_pct"] == 100.0
    assert sw["verdict"] == "váltogatós"
    assert sw["labels"]["6-0"] == 4 and sw["labels"]["5-1"] == 4

    one = formation_switching(_fsw_match([flat] * 8))["away"]
    assert one["attacks"] == 8 and one["switches"] == 0
    assert one["main"] == "6-0" and one["main_pct"] == 100.0
    assert one["verdict"] == "egy rendszer"

    # Két támadás: nincs elég minta → nincs arány és nincs ítélet.
    few = formation_switching(_fsw_match([flat, one_up]))
    assert few["away"]["switch_pct"] is None
    assert few["away"]["verdict"] is None
    # A hazai fal nem védekezett → üres.
    assert few["home"]["attacks"] == 0 and few["home"]["verdict"] is None


# ---- Álló támadók (ki mozog labda nélkül a legkevesebbet) --------------------

def _static_attacker_match(still_id=5, n=2000, fps=25.0):
    """HAZAI szervezett támadás: négy támadó cikcakkban mozog, a
    `still_id` végig ugyanott áll."""
    frames = []
    off = 0.0
    for i in range(n):
        direction = 1.0 if (i // 25) % 2 == 0 else -1.0
        off += 0.08 * direction
        players = []
        for k, base in ((1, 10.0), (2, 4.0), (3, 7.0), (4, 13.0),
                        (5, 16.0)):
            y = base if k == still_id else base + off
            players.append(_pl(k, Team.HOME, 30.0, y))
        frames.append(Frame(t=i, players=players,
                            ball=Ball(x=30.0, y=10.0 + off,
                                      confidence=1.0)))
    return Match(_meta(fps), frames)


def test_static_attackers_finds_the_still_player():
    """A végig egy helyben álló támadó a csapatátlag alatt marad → őt
    jelöljük álló emberként."""
    from handball.pipeline.tactics import static_attackers

    rec = static_attackers(_static_attacker_match())["home"]
    assert rec["team_avg_mps"] is not None
    assert rec["static"] is not None
    assert rec["static"]["player_id"] == 5
    assert rec["static"]["avg_mps"] < rec["team_avg_mps"]
    # A lista a legkevesebbet mozgóval kezdődik.
    assert rec["players"][0]["player_id"] == 5


def test_static_attackers_all_moving_has_no_verdict():
    """Ha mindenki egyformán mozog, nincs álló ember."""
    from handball.pipeline.tactics import static_attackers

    rec = static_attackers(_static_attacker_match(still_id=None))["home"]
    assert rec["static"] is None


def test_static_attackers_needs_enough_seconds():
    """Kevés mért másodpercnél nincs ítélet."""
    from handball.pipeline.tactics import static_attackers

    rec = static_attackers(_static_attacker_match(n=200))["home"]
    assert rec["static"] is None


def _dfs_half_frames(t0, n, advanced_one: bool):
    """n hazai támadás, ami alatt a vendég fal 6-0-t (advanced_one=False)
    vagy 5-1-et (True) véd a saját (x=40) kapuja előtt."""
    frames = []
    t = t0
    for _ in range(n):
        for _ in range(int(8 * 25)):
            players = [_pl(1, Team.HOME, 30.0, 10.0)]
            for k in range(6):
                if advanced_one and k == 0:
                    players.append(_pl(200 + k, Team.AWAY, 31.0, 10.0))
                else:
                    players.append(_pl(200 + k, Team.AWAY, 34.5,
                                       4.0 + 2.4 * k))
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=30.0, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(10):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=18.0, y=10.0, confidence=1.0)))
            t += 1
    return frames, t


def test_defense_form_shift_flags_halftime_wall_change():
    """1. félidő 6-0, 2. félidő 5-1 → a vendég falat vált a szünetre."""
    from handball.pipeline.tactics import defense_form_shift

    meta = MatchMeta(match_id="dfs", home_team="H", away_team="A", fps=25.0)
    frames, t = _dfs_half_frames(0, 5, advanced_one=False)
    for _ in range(int(90 * 25)):
        frames.append(Frame(t=t, players=[], ball=None))
        t += 1
    sh, t = _dfs_half_frames(t, 5, advanced_one=True)
    frames += sh

    dfs = defense_form_shift(Match(meta, frames))
    a = dfs["away"]
    assert a["fh_main"] == "6-0"
    assert a["sh_main"] == "5-1"
    assert a["verdict"] == "a szünet után falat váltanak (6-0 → 5-1)"
    assert dfs["home"]["verdict"] is None


def test_defense_form_shift_stable_wall_and_no_halftime():
    """Azonos fal mindkét félidőben → "ugyanaz a fal"; szünet-jel
    nélkül nincs ítélet."""
    from handball.pipeline.tactics import defense_form_shift

    meta = MatchMeta(match_id="dfs2", home_team="H", away_team="A", fps=25.0)
    frames, t = _dfs_half_frames(0, 5, advanced_one=False)
    for _ in range(int(90 * 25)):
        frames.append(Frame(t=t, players=[], ball=None))
        t += 1
    sh, t = _dfs_half_frames(t, 5, advanced_one=False)
    frames += sh
    dfs = defense_form_shift(Match(meta, frames))
    assert dfs["away"]["verdict"] == "a szünet után is ugyanaz a fal"

    nob, _t2 = _dfs_half_frames(0, 5, advanced_one=False)
    dfs2 = defense_form_shift(Match(meta, nob))
    assert dfs2["away"]["verdict"] is None
