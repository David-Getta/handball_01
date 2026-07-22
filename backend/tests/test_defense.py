"""
Tesztek a védekezés-elemzésre (defense.py): szabad lövés, zóna, kapott xG.

A pálya 40x20 m; a HAZAI a +x (x=40) kapu felé támad — tehát a hazai
lövéseket a VENDÉG védekezése "kapja".

Futtatás:
    python -m pytest tests/test_defense.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.defense import defense_analysis


def _meta(fps=25.0):
    return MatchMeta(match_id="d", home_team="H", away_team="A", fps=fps)


def _pl(track_id, team, x, y, role=None):
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0,
                          role=role)


def _shot(t0, defenders, goal=True):
    """Hazai lövés a +x kapura az 1-es játékostól (x=33, y=10) — a megadott
    védőkkel a lövés-képkockákon."""
    frames = []
    for i in range(7):
        players = [_pl(1, Team.HOME, 33.0, 10.0)] + defenders
        y = 10.0 if goal else 5.0
        frames.append(Frame(t=t0 + i, players=players,
                            ball=Ball(x=34.0 + i, y=y, confidence=1.0)))
    frames.append(Frame(t=t0 + 7, players=[],
                        ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    return frames


def test_free_vs_covered_shot():
    """Védő 1 m-re → fedezett; a legközelebbi védő 5 m-re → szabad lövés."""
    # A védő a lövő mellett (0,7 m), de NEM a labda röppályáján — különben
    # őt találná meg a birtokos-keresés, és a lövő azonosíthatatlan lenne.
    covered = _shot(0, [_pl(20, Team.AWAY, 32.5, 10.5)])          # 0,7 m
    free = _shot(40, [_pl(21, Team.AWAY, 33.0, 15.0)])            # 5 m
    m = Match(_meta(), covered + free)
    d = defense_analysis(m)["away"]  # a vendég védekezett
    assert d["shots_against"] == 2 and d["goals_against"] == 2
    assert d["free_shots"] == 1
    assert d["free_pct"] == 50.0
    flags = [s["free"] for s in d["shots"]]
    assert flags == [False, True]
    # A hazai védekezés nem kapott lövést.
    assert defense_analysis(m)["home"]["shots_against"] == 0


def test_goalkeeper_does_not_count_as_cover():
    """A kapus közelsége NEM fedezés — mezőnyvédő nélkül a lövés szabad."""
    gk_only = _shot(0, [_pl(30, Team.AWAY, 34.0, 10.0, role="kapus")])
    d = defense_analysis(Match(_meta(), gk_only))["away"]
    assert d["shots_against"] == 1
    # Egyetlen mezőnyvédő sincs → nincs táv-minta → free None (nem mérhető).
    assert d["shots"][0]["free"] is None
    assert d["free_shots"] == 0


def test_zones_and_worst_zone():
    """A zóna-bontás a lövés helyéből jön; a legtöbb gólt hozó zóna a
    worst_zone."""
    beallo = _shot(0, [_pl(20, Team.AWAY, 38.0, 10.0)])           # beálló (6 m)
    m = Match(_meta(), beallo)
    d = defense_analysis(m)["away"]
    assert "beálló (6 m)" in d["zones"]
    assert d["worst_zone"] == "beálló (6 m)"
    assert d["xg_against"] > 0


def test_transition_defense_counts_fast_goals():
    """Labdaeladás → az ellenfél gólja 8 mp-en belül = átmenet-gól."""
    from handball.pipeline.defense import transition_defense

    frames = []
    t = 0
    # A hazai birtokol, majd a vendég szerzi meg (labdaeladás a hazainak).
    frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 25.0, 10.0)],
                        ball=Ball(x=25.0, y=10.0, confidence=1.0)))
    t += 1
    frames.append(Frame(t=t, players=[_pl(11, Team.AWAY, 20.0, 10.0)],
                        ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    t += 1
    # Hézag: a vendég vezeti a labdát ~1 mp-ig (a lövés-közeli labdaeladás-
    # elnyomás miatt kell távolság a labdaeladás és a lövés között), de a
    # gól még a 8 mp-es átmenet-ablakon belül van.
    for i in range(25):
        bx = 20.0 - i * 0.4
        frames.append(Frame(t=t, players=[_pl(11, Team.AWAY, bx, 10.0)],
                            ball=Ball(x=bx, y=10.0, confidence=1.0)))
        t += 1
    # A vendég gólt lő a -x (x=0) kapura (a hazai kapujára).
    for i in range(7):
        frames.append(Frame(t=t, players=[_pl(11, Team.AWAY, 7.0, 10.0)],
                            ball=Ball(x=max(0.0, 6.4 - i), y=10.0,
                                      confidence=1.0)))
        t += 1
    td = transition_defense(Match(_meta(), frames))
    assert td["home"]["turnovers"] >= 1
    assert td["home"]["transition_goals_against"] >= 1
    assert td["home"]["pct"] > 0
    # A vendég nem vesztett labdát ebben a jelenetben.
    assert td["away"]["transition_goals_against"] == 0


def test_turnover_zones_classifies_front_loss():
    """A támadó harmadban (a megtámadott kapu közelében) elvesztett labda a
    'támadó' zónába kerül, és emeli a front_pct-t."""
    from handball.pipeline.defense import turnover_zones

    frames = []
    t = 0
    # A hazai birtokolja a labdát a vendég kapuja közelében (x=35, a +x
    # kapu felé támad), majd a vendég szerzi meg → labdaeladás itt.
    for _ in range(3):
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 35.0, 10.0)],
                            ball=Ball(x=35.0, y=10.0, confidence=1.0)))
        t += 1
    for _ in range(3):
        frames.append(Frame(t=t, players=[_pl(11, Team.AWAY, 35.0, 10.0)],
                            ball=Ball(x=35.0, y=10.0, confidence=1.0)))
        t += 1
    tz = turnover_zones(Match(_meta(), frames))
    assert tz["home"]["total"] == 1
    assert tz["home"]["zones"].get("támadó") == 1
    assert tz["home"]["front_pct"] == 100.0
    assert tz["away"]["total"] == 0


def test_pressure_finishing_free_vs_covered():
    """A fedezett lövés mellé megy, a szabad gól → a hazai támadók
    szabadon 100%, fedezve 0%."""
    from handball.pipeline.defense import pressure_finishing

    # Fedezett "mellé": a labda a lövőtől indul (ott azonosítható a lövő),
    # majd fokozatosan elhajlik a kapufák mellé.
    covered_miss = []
    for i in range(7):
        covered_miss.append(Frame(
            t=i,
            players=[_pl(1, Team.HOME, 33.0, 10.0),
                     _pl(20, Team.AWAY, 32.5, 10.5)],
            ball=Ball(x=34.0 + i, y=10.0 - i * 1.0, confidence=1.0)))
    covered_miss.append(Frame(t=7, players=[],
                              ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    free_goal = _shot(40, [_pl(21, Team.AWAY, 33.0, 15.0)], goal=True)
    pf = pressure_finishing(Match(_meta(), covered_miss + free_goal))
    home = pf["home"]
    assert home["free"] == {"shots": 1, "goals": 1, "pct": 100.0}
    assert home["covered"]["shots"] == 1
    assert home["covered"]["goals"] == 0
    assert home["covered"]["pct"] == 0.0
    # A vendég nem lőtt → mindkét vödör üres, pct None.
    assert pf["away"]["free"]["pct"] is None


def test_detect_blocks_credits_defender():
    """A lövés a 32,5 m-nél álló védőn pattan vissza (a kaputól ~7,5 m,
    nem a kapusnál) → a vendég védekezés blokkja."""
    from handball.pipeline.defense import detect_blocks

    frames = []
    shooter = _pl(1, Team.HOME, 28.0, 10.0)
    blocker = _pl(20, Team.AWAY, 32.5, 10.0)
    # A labda gyorsan a +x kapu felé: 29→32,4 (lövés-jel), majd visszapattan.
    xs = [29.0, 30.2, 31.4, 32.4, 31.0, 29.5, 28.0]
    for i, x in enumerate(xs):
        frames.append(Frame(t=i, players=[shooter, blocker],
                            ball=Ball(x=x, y=10.0, confidence=1.0)))
    b = detect_blocks(Match(_meta(), frames))
    assert b["away"]["blocks"] == 1
    assert b["away"]["blockers"][0]["player_id"] == 20
    assert b["home"]["blocks"] == 0


def test_defensive_pressure_tight_vs_loose():
    """Szoros védő (1 m) kisebb nyomás-átlagot ad, mint a laza (6 m)."""
    from handball.pipeline.defense import defensive_pressure

    def scene(def_y):
        frames = []
        for t in range(30):
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, 25.0, 10.0),          # labdás támadó
                _pl(20, Team.AWAY, 25.0, def_y)],       # a védő
                ball=Ball(x=25.0, y=10.0, confidence=1.0)))
        return Match(_meta(), frames)

    tight = defensive_pressure(scene(11.0))["away"]["avg_pressure_m"]
    loose = defensive_pressure(scene(16.0))["away"]["avg_pressure_m"]
    assert tight is not None and loose is not None
    assert tight < loose
    assert abs(tight - 1.0) < 0.2  # ~1 m-re állt a védő


def test_transition_recovery_measures_slow_return():
    """Ha a védők sokáig az ellenfél térfelén ragadnak, a
    visszarendeződés lassúként mérődik."""
    from handball.models.tracking import Ball, Frame, Match, MatchMeta
    from handball.pipeline.defense import transition_recovery

    def pl(tid, team, x, y):
        return PlayerPosition(track_id=tid, team=team, x=x, y=y)

    frames = []
    for t in range(300):
        # A hazai birtokol és lassan nyomul a +x kapu felé.
        bx = 22.0 + 0.05 * t
        players = [pl(1, Team.HOME, bx, 10.0)]
        # Négy vendég védő 6 mp-ig elöl ragad (x=10), majd visszaér.
        dx = 10.0 if t < 150 else 35.0
        for k in range(4):
            players.append(pl(10 + k, Team.AWAY, dx, 4.0 + 4 * k))
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=bx, y=10.0, confidence=1.0)))
    m = Match(MatchMeta(match_id="rc", home_team="H", away_team="A",
                        fps=25.0), frames)
    rec = transition_recovery(m)["away"]
    assert rec["transitions"] >= 1
    assert rec["avg_s"] is not None and rec["avg_s"] >= 5.0
    assert rec["slow"] >= 1


def test_marking_pairs_identifies_defender_assignments():
    """A támadóhoz legközelebbi védő adja az őrzési párt; a túl messzi
    (MARK_MAX_DIST_M-en kívüli) védő nem kap párt, a laza pár pedig a
    loosest mezőbe kerül."""
    from handball.models.tracking import Ball, Frame, Match
    from handball.pipeline.defense import marking_pairs

    frames = []
    for t in range(30):
        frames.append(Frame(t=t, players=[
            # Hazai támadók (a labda az 1-esnél).
            _pl(1, Team.HOME, 25.0, 10.0),
            _pl(2, Team.HOME, 25.0, 4.0),
            # Vendég védők: a 20-as szorosan az 1-esen, a 21-es lazán
            # (3 m) a 2-esen, a 22-es mindenkitől messze.
            _pl(20, Team.AWAY, 25.0, 11.0),
            _pl(21, Team.AWAY, 25.0, 7.0),
            _pl(22, Team.AWAY, 38.0, 18.0)],
            ball=Ball(x=25.0, y=10.0, confidence=1.0)))
    res = marking_pairs(Match(_meta(), frames))
    assert res["home"]["pairs"] == []          # a hazai nem védekezett
    pairs = {p["defender"]: p for p in res["away"]["pairs"]}
    assert set(pairs) == {20, 21}              # a 22-es nem őrzött senkit
    assert pairs[20]["attacker"] == 1
    assert abs(pairs[20]["avg_dist_m"] - 1.0) < 0.05
    assert pairs[20]["share_pct"] == 100.0
    assert pairs[21]["attacker"] == 2
    assert abs(pairs[21]["avg_dist_m"] - 3.0) < 0.05
    # A leglazább pár a 3 m-es őrzés.
    assert res["away"]["loosest"]["defender"] == 21


def test_marking_pairs_needs_min_frames():
    """MARK_MIN_FRAMES-nél rövidebb együttállás nem lesz pár."""
    from handball.models.tracking import Ball, Frame, Match
    from handball.pipeline.defense import MARK_MIN_FRAMES, marking_pairs

    frames = []
    for t in range(MARK_MIN_FRAMES - 5):
        frames.append(Frame(t=t, players=[
            _pl(1, Team.HOME, 25.0, 10.0),
            _pl(20, Team.AWAY, 25.0, 11.0)],
            ball=Ball(x=25.0, y=10.0, confidence=1.0)))
    res = marking_pairs(Match(_meta(), frames))
    assert res["away"]["pairs"] == []


def test_marking_pairs_until_t_limits_window():
    """until_t-vel csak az addigi kockák számítanak — a félidei kép nem
    néz a jövőbe: az első szakasz laza őrzése látszik akkor is, ha a
    védő később feljavul."""
    from handball.models.tracking import Ball, Frame, Match
    from handball.pipeline.defense import marking_pairs

    frames = []
    # Első 30 kocka: laza őrzés (3 m); utána 60 kocka szoros (1 m).
    for t in range(90):
        dy = 3.0 if t < 30 else 1.0
        frames.append(Frame(t=t, players=[
            _pl(1, Team.HOME, 25.0, 10.0),
            _pl(20, Team.AWAY, 25.0, 10.0 + dy)],
            ball=Ball(x=25.0, y=10.0, confidence=1.0)))
    m = Match(_meta(), frames)
    fh = marking_pairs(m, until_t=29)["away"]["pairs"]
    assert fh and abs(fh[0]["avg_dist_m"] - 3.0) < 0.05
    assert fh[0]["frames"] == 30
    full = marking_pairs(m)["away"]["pairs"]
    assert full[0]["frames"] == 90
    assert full[0]["avg_dist_m"] < 2.0  # a teljes képben már szoros


def test_breakthrough_lanes_detects_entry_lane():
    """A 9 m-en belülre lépő labdás ember betörésnek számít, a sávot a
    belépési y adja (oldal-normalizálva); kapu-távolban maradó
    támadásnál nincs betörés."""
    from handball.models.tracking import Ball, Frame, Match
    from handball.pipeline.defense import breakthrough_lanes

    def scene(xs, y):
        frames = []
        for t, x in enumerate(xs):
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, x, y),
                _pl(20, Team.AWAY, 38.0, 10.0)],
                ball=Ball(x=x, y=y, confidence=1.0)))
        return Match(_meta(), frames)

    # Középen betör: x 28→34 (a +x kapu 9 m-es körén belülre ér).
    xs = [28.0 + 0.1 * i for i in range(80)]
    res = breakthrough_lanes(scene(xs, 10.0))
    assert res["home"]["entries"] == 1
    assert res["home"]["top_lane"] == "közép"
    # Alsó sávban (y=3) betörve a szél-sáv kapja.
    res2 = breakthrough_lanes(scene(xs, 3.0))
    assert res2["home"]["top_lane"] in ("bal szél", "jobb szél")
    # Messze maradva (x<=30) nincs betörés.
    res3 = breakthrough_lanes(scene([28.0] * 80, 10.0))
    assert res3["home"]["entries"] == 0


def test_ball_winners_credit_new_holder():
    """Csapatváltásos birtokos-váltásnál az új birtokos kap
    labdaszerzés-jóváírást; csapaton belüli passznál senki."""
    from handball.models.tracking import Ball, Frame, Match
    from handball.pipeline.defense import ball_winners

    frames = []
    t = 0
    # Hazai 1-es birtokol, majd a vendég 20-as szerzi meg (váltás),
    # utána a 20-as passzol a 21-esnek (csapaton belül — nem szerzés).
    for holder, x, y in [(1, 25.0, 10.0)] * 10 + \
                        [(20, 26.0, 10.0)] * 10 + \
                        [(21, 28.0, 12.0)] * 10:
        frames.append(Frame(t=t, players=[
            _pl(1, Team.HOME, 25.0, 10.0),
            _pl(20, Team.AWAY, 26.0, 10.0),
            _pl(21, Team.AWAY, 28.0, 12.0)],
            ball=Ball(x=x, y=y, confidence=1.0)))
        t += 1
    res = ball_winners(Match(_meta(), frames))
    assert res["away"]["total"] == 1
    assert res["away"]["players"][0]["player_id"] == 20
    assert res["away"]["ts"] and res["away"]["ts"][0]["player_id"] == 20
    assert res["home"]["total"] == 0


def test_defensive_line_height_high_vs_deep():
    """Felfutó fal (a védők ~9 m-re a saját kaputól) magas vonalat, mély
    fal (~5 m) alacsonyat ad; a labdás a védő térfelén birtokol."""
    from handball.pipeline.defense import defensive_line_height

    def scene(def_depth):
        # A HAZAI védekezik a saját kapujánál (x=0); a VENDÉG a hazai
        # térfélen birtokol. A hazai védők def_depth m-re a 0-s kaputól.
        frames = []
        for t in range(150):
            players = [
                _pl(1, Team.AWAY, 8.0, 10.0),               # labdás támadó
                _pl(2, Team.AWAY, 12.0, 6.0),
                _pl(10, Team.HOME, def_depth, 7.0),         # hazai védők
                _pl(11, Team.HOME, def_depth, 13.0),
                _pl(12, Team.HOME, def_depth + 0.5, 10.0),
                _pl(9, Team.HOME, 0.5, 10.0, role="kapus"),
            ]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=8.0, y=10.0, confidence=1.0)))
        return Match(_meta(), frames)

    high = defensive_line_height(scene(9.0))["home"]
    deep = defensive_line_height(scene(5.0))["home"]
    assert high["avg_height_m"] > deep["avg_height_m"]
    assert high["style"] == "felfutó (agresszív)"
    assert deep["style"] == "mély (passzív)"
    # A kapus nem számít bele a vonal-magasságba.
    assert high["frames"] == 150


def test_turnover_players_credits_the_loser():
    """A labdaeladás a labdát ELVESZTŐ játékosnak számít; a kapus kimarad."""
    from handball.pipeline.defense import turnover_players

    frames = []
    t = 0
    # HAZAI 7-es birtokol középen, majd a VENDÉG 11-es szerzi meg → a 7-es
    # eladása (lövéstől távol, hogy ne szűrődjön ki).
    for _ in range(4):
        frames.append(Frame(t=t, players=[_pl(7, Team.HOME, 20.0, 10.0),
                                          _pl(11, Team.AWAY, 20.5, 10.0)],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    for _ in range(4):
        frames.append(Frame(t=t, players=[_pl(7, Team.HOME, 20.0, 10.0),
                                          _pl(11, Team.AWAY, 20.5, 10.0)],
                            ball=Ball(x=20.5, y=10.0, confidence=1.0)))
        t += 1
    tp = turnover_players(Match(_meta(), frames))
    assert tp["home"]["total"] == 1
    assert tp["home"]["players"][0]["player_id"] == 7
    assert tp["home"]["players"][0]["losses"] == 1
    assert tp["away"]["total"] == 0
