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


def test_blocked_shot_rate_attacking_side():
    """4 hazai lövés akad el a vendég védőn (+1 tiszta lövés) → a HAZAI
    támadás blokk-aránya 4/5 = 80%; kevés blokknál nincs ítélet."""
    from handball.pipeline.defense import blocked_shot_rate

    frames = []
    t = 0
    shooter = _pl(1, Team.HOME, 28.0, 10.0)
    blocker = _pl(20, Team.AWAY, 32.5, 10.0)
    # 4 blokkolt lövés (a labda a védőn fordul vissza), köztük szünetekkel.
    for _ in range(4):
        for x in (29.0, 30.2, 31.4, 32.4, 31.0, 29.5, 28.0):
            frames.append(Frame(t=t, players=[shooter, blocker],
                                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1
        for _i in range(40):  # szünet (blokk-cooldown + lövés-debounce)
            frames.append(Frame(t=t, players=[shooter, blocker],
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
            t += 1
    # 1 tiszta (védő nélküli) gól — ez a "shots" oldalt adja.
    for i in range(3):
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 33.0, 10.0)],
                            ball=Ball(x=33.0, y=10.0, confidence=1.0)))
        t += 1
    for i in range(8):
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, 33.0, 10.0)],
                            ball=Ball(x=min(34.0 + i, 40.0), y=10.0,
                                      confidence=1.0)))
        t += 1

    br = blocked_shot_rate(Match(_meta(), frames))
    h = br["home"]
    assert h["blocked"] == 4 and h["shots"] >= 1
    assert h["blocked_pct"] is not None and h["blocked_pct"] >= 20.0
    # A vendégnek nincs blokkolt lövése → nincs ítélet.
    assert br["away"]["blocked"] == 0 and br["away"]["blocked_pct"] is None


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


def test_defensive_width_narrow_vs_wide():
    """Tömör fal (a védők y-terjedelme ~8 m) keskeny, széthúzott fal
    (~16 m) széles átlagot ad; a kapus nem számít bele."""
    from handball.pipeline.defense import defensive_width

    def scene(spread):
        # A HAZAI védekezik a saját kapujánál (x=0); a VENDÉG a hazai
        # térfélen birtokol. A hazai védők y-ban `spread` szélesen állnak.
        lo = 10.0 - spread / 2.0
        hi = 10.0 + spread / 2.0
        frames = []
        for t in range(150):
            players = [
                _pl(1, Team.AWAY, 8.0, 10.0),            # labdás támadó
                _pl(10, Team.HOME, 6.0, lo),             # hazai fal
                _pl(11, Team.HOME, 6.0, 10.0),
                _pl(12, Team.HOME, 6.0, hi),
                _pl(13, Team.HOME, 6.5, 10.0),
                _pl(9, Team.HOME, 0.5, 19.5, role="kapus"),
            ]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=8.0, y=10.0, confidence=1.0)))
        return Match(_meta(), frames)

    narrow = defensive_width(scene(8.0))["home"]
    wide = defensive_width(scene(16.0))["home"]
    assert narrow["avg_width_m"] < wide["avg_width_m"]
    assert narrow["style"] == "tömör (szélek nyitva)"
    assert wide["style"] == "széthúzott (közép nyitva)"
    assert narrow["frames"] == 150
    # A kapus (y=19,5) nem tágítja a falat: a keskeny átlag ~8 m maradt.
    assert narrow["avg_width_m"] < 9.0


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


def test_steal_height_front_vs_back():
    """Elöl (a szerző támadó térfelén) történt szerzés magas, a hátsó nem;
    kevés szerzésnél nincs ítélet."""
    from handball.pipeline.defense import steal_height

    frames = []
    t = 0

    def steal_at(x):
        # A HAZAI 1-es birtokol x-nél, majd a VENDÉG 20-as szerzi meg
        # (labda átkerül hozzá) → vendég szerzés az x pozíción.
        nonlocal t
        for _ in range(5):
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, x, 10.0),
                _pl(20, Team.AWAY, x + 0.5, 10.0)],
                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(5):
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, x, 10.0),
                _pl(20, Team.AWAY, x + 0.5, 10.0)],
                ball=Ball(x=x + 0.5, y=10.0, confidence=1.0)))
            t += 1
        # Vissza az 1-eshez, hogy új szerzés jöhessen.
        for _ in range(5):
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, x, 10.0),
                _pl(20, Team.AWAY, x + 0.5, 10.0)],
                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1

    # A VENDÉG a -x (x=0) kapura támad → az ő "elöl"-je az x < 20 térfél.
    for _ in range(3):
        steal_at(10.0)   # elöl szerzett (letámadás)
    for _ in range(2):
        steal_at(30.0)   # hátul szerzett
    sh = steal_height(Match(_meta(), frames))
    a = sh["away"]
    assert a["steals"] >= 4
    assert a["high_steals"] >= 3
    assert a["high_pct"] is not None and a["high_pct"] >= 35.0
    # A visszapasszok a HAZAI szerzései: x=10 nekik hátul (a +x kapura
    # támadnak), x=30 elöl → 2/5 elöl-szerzés, 40%.
    h = sh["home"]
    assert h["steals"] == 5 and h["high_steals"] == 2
    assert h["high_pct"] == 40.0


def test_pressure_fade_looser_second_half():
    """Az 1. félidőben szoros (1 m), a 2.-ban laza (3 m) őrzés → ~2 m
    fellazulás; félidő-jel nélkül nincs ítélet."""
    from handball.pipeline.defense import pressure_fade

    fps = 25.0

    def press_frames(t0, seconds, def_dist):
        # A VENDÉG birtokol (labdás a 11-es), a HAZAI védő def_dist m-re.
        fr = []
        for i in range(int(seconds * fps)):
            players = [
                _pl(11, Team.AWAY, 15.0, 10.0),
                _pl(12, Team.AWAY, 18.0, 6.0),
                _pl(13, Team.AWAY, 18.0, 14.0),
                _pl(14, Team.AWAY, 12.0, 10.0),
                _pl(15, Team.AWAY, 20.0, 8.0),
                _pl(16, Team.AWAY, 20.0, 12.0),
                _pl(1, Team.HOME, 15.0, 10.0 + def_dist),
                _pl(2, Team.HOME, 10.0, 6.0),
                _pl(3, Team.HOME, 10.0, 14.0),
                _pl(4, Team.HOME, 8.0, 10.0),
                _pl(5, Team.HOME, 6.0, 8.0),
                _pl(6, Team.HOME, 6.0, 12.0),
            ]
            fr.append(Frame(t=t0 + i, players=players,
                            ball=Ball(x=15.0, y=10.0, confidence=1.0)))
        return fr

    frames = press_frames(0, 60, 1.0)                      # 1. félidő: szoros
    t = len(frames)
    frames += [Frame(t=t + i, players=[], ball=None)
               for i in range(int(90 * fps))]              # szünet
    t = len(frames)
    frames += press_frames(t, 60, 3.0)                     # 2. félidő: laza

    pf = pressure_fade(Match(_meta(), frames))
    h = pf["home"]
    assert h["fh_m"] is not None and h["sh_m"] is not None
    assert h["loosen_m"] is not None and h["loosen_m"] >= 1.5
    # Félidő nélkül (rövid felvétel) nincs ítélet.
    short = pressure_fade(Match(_meta(), press_frames(0, 10, 1.0)))
    assert short["home"]["loosen_m"] is None


def test_turnover_fade_rate_rises_second_half():
    """Az 1. félidőben 1, a 2.-ban 4 eladás azonos birtoklás-idő mellett →
    az eladás-ütem érdemben nő; félidő-jel nélkül nincs ítélet."""
    from handball.pipeline.defense import turnover_fade

    fps = 25.0
    frames = []
    t = 0

    def possession_with_turnovers(seconds, n_turnovers):
        # HAZAI birtoklás `seconds` hosszan; közben n_turnovers eladás
        # (a labda rövid időre a vendég 20-ashoz kerül, majd vissza).
        nonlocal t
        total = int(seconds * fps)
        slot = total // max(1, n_turnovers + 1)
        for i in range(total):
            steal = n_turnovers and i % slot == slot - 1 \
                and i // slot < n_turnovers
            holder_away = bool(steal)
            hx = 20.0
            players = [_pl(1, Team.HOME, hx, 10.0),
                       _pl(20, Team.AWAY, hx + 0.6, 10.0)]
            bx = hx + (0.6 if holder_away else 0.0)
            for _ in range(6 if steal else 1):
                frames.append(Frame(t=t, players=players,
                                    ball=Ball(x=bx, y=10.0,
                                              confidence=1.0)))
                t += 1

    possession_with_turnovers(150, 1)          # 1. félidő: 1 eladás
    for _ in range(int(90 * fps)):             # szünet
        frames.append(Frame(t=t, players=[], ball=None))
        t += 1
    possession_with_turnovers(150, 4)          # 2. félidő: 4 eladás

    tf = turnover_fade(Match(_meta(), frames))
    h = tf["home"]
    assert h["fh_per_min"] is not None and h["sh_per_min"] is not None
    assert h["sh_to"] > h["fh_to"]
    assert h["rise_per_min"] is not None and h["rise_per_min"] >= 0.2
    # Félidő nélkül nincs ítélet.
    short = turnover_fade(Match(_meta(), frames[:1000]))
    assert short["home"]["rise_per_min"] is None


def test_turnover_timing_flags_early_losses():
    """6 rövid (2 mp-es) + 1 hosszú (12 mp-es) hazai birtoklás végén jön
    az eladás → az eladások ~86%-a korai; kevés eladásnál nincs ítélet."""
    from handball.pipeline.defense import turnover_timing

    def _hold(t0, pid, team, n):
        return [Frame(t=t0 + i,
                      players=[_pl(pid, team, 20.0, 10.0)],
                      ball=Ball(x=20.0, y=10.0, confidence=1.0))
                for i in range(n)]

    frames = []
    t = 0
    for k in range(7):
        n_home = 300 if k == 6 else 50  # 12 mp a hetedik, 2 mp a többi
        frames += _hold(t, 1, Team.HOME, n_home)
        t += n_home
        frames += _hold(t, 11, Team.AWAY, 25)
        t += 25
    tt = turnover_timing(Match(_meta(), frames))
    h = tt["home"]
    assert h["timed"] == 7 and h["early"] == 6
    assert h["early_pct"] is not None
    assert abs(h["early_pct"] - 100.0 * 6 / 7) < 0.5

    # Kevés eladás: nincs ítélet.
    few = turnover_timing(Match(_meta(), frames[:100]))
    assert few["home"]["early_pct"] is None


def test_second_chance_allowed_mirrors_defense():
    """4 hazai kimaradt lövést ablakon belüli újralövés (gól) követ, 2
    magányos kimaradás → a VENDÉG fal a 6 lehetőségből 4 második rohamot
    engedett (67%); a hazai oldalon nincs minta → nincs ítélet."""
    from handball.pipeline.defense import second_chance_allowed

    def _shot(t0, goal):
        frames = []
        for i in range(8):
            bx = min(34.0 + i, 40.0)
            by = 10.0 if goal else 5.0
            frames.append(Frame(
                t=t0 + i, players=[_pl(1, Team.HOME, 33.0, 10.0)],
                ball=Ball(x=bx, y=by, confidence=1.0)))
        return frames

    def _gap(t0, n):
        return [Frame(t=t0 + i, players=[],
                      ball=Ball(x=20.0, y=10.0, confidence=1.0))
                for i in range(n)]

    frames = []
    t = 0
    for _ in range(4):  # kimaradás → ablakon belül gól (második roham)
        frames += _shot(t, goal=False)
        t = frames[-1].t + 1
        frames += _gap(t, 12)
        t = frames[-1].t + 1
        frames += _shot(t, goal=True)
        t = frames[-1].t + 1
        frames += _gap(t, 200)
        t = frames[-1].t + 1
    for _ in range(2):  # magányos kimaradások
        frames += _shot(t, goal=False)
        t = frames[-1].t + 1
        frames += _gap(t, 200)
        t = frames[-1].t + 1
    sca = second_chance_allowed(Match(_meta(), frames))
    a = sca["away"]  # a vendég védekezett a hazai lövéseknél
    assert a["opp_misses"] == 6 and a["allowed"] == 4
    assert a["allowed_goals"] == 4
    assert a["allowed_pct"] is not None
    assert abs(a["allowed_pct"] - 100.0 * 4 / 6) < 0.5
    # A hazai fal ellen nem volt lepattanó-lehetőség → nincs ítélet.
    assert sca["home"]["opp_misses"] == 0
    assert sca["home"]["allowed_pct"] is None


def test_turnover_punishment_counts_quick_conceded_goals():
    """7 hazai eladásból 3-at fél percen belüli vendég-gól büntet →
    43%-os büntetés-arány; kevés eladásnál nincs ítélet."""
    from handball.pipeline.defense import turnover_punishment

    frames = []
    t = 0

    def _cycle(punished):
        # Hazai birtoklás → a vendég elveszi (hazai eladás), majd ha
        # punished, a vendég fél percen belül gólt lő a 0-s kapura.
        nonlocal t, frames
        both = [_pl(1, Team.HOME, 20.0, 10.0),
                _pl(11, Team.AWAY, 20.6, 10.0)]
        for _ in range(10):
            frames.append(Frame(t=t, players=both,
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(10):
            frames.append(Frame(t=t, players=both,
                                ball=Ball(x=20.6, y=10.0, confidence=1.0)))
            t += 1
        if punished:
            for _ in range(50):  # a lövés-elnyomó ablakon kívülre
                frames.append(Frame(t=t, players=both,
                                    ball=Ball(x=20.6, y=10.0,
                                              confidence=1.0)))
                t += 1
            shooter = [_pl(12, Team.AWAY, 7.0, 10.0)]
            for i in range(9):
                frames.append(Frame(t=t, players=shooter,
                                    ball=Ball(x=max(6.0 - i, 0.0), y=10.0,
                                              confidence=1.0)))
                t += 1
        for _ in range(900):  # hosszú szünet: a következő kör önálló
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=30.0, y=10.0, confidence=1.0)))
            t += 1

    for flag in (True, True, True, False, False, False, False):
        _cycle(flag)
    tp = turnover_punishment(Match(_meta(), frames))
    h = tp["home"]
    assert h["turnovers"] == 7 and h["punished"] == 3
    assert h["rate_pct"] is not None
    assert abs(h["rate_pct"] - 100.0 * 3 / 7) < 0.5

    # Kevés eladás: nincs ítélet.
    few = turnover_punishment(Match(_meta(), frames[:1000]))
    assert few["home"]["rate_pct"] is None


def test_conceded_side_bias_mirrors_attack_side():
    """A hazai 6 bal (+y) + 2 jobb (−y) oldali lövése a vendég falának
    JOBB oldalán jön át (a fal tükörben áll) → 75%-os gyenge oldal;
    kevés kapott lövésnél nincs ítélet."""
    from handball.pipeline.defense import conceded_side_bias

    def _shot(t0, y0):
        fr = []
        for i in range(8):
            fr.append(Frame(
                t=t0 + i,
                players=[_pl(1, Team.HOME, 36.6, y0)],
                ball=Ball(x=min(37.0 + 0.8 * i, 40.0), y=y0,
                          confidence=1.0)))
        fr.append(Frame(t=t0 + 9, players=[],
                        ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        return fr

    frames = []
    t = 0
    for y0 in (16.0, 16.0, 16.0, 16.0, 16.0, 16.0, 4.0, 4.0):
        frames += _shot(t, y0)
        t += 40
    cs = conceded_side_bias(Match(_meta(), frames))
    a = cs["away"]
    assert a["left"] == 2 and a["right"] == 6
    assert a["weak_side"] == "jobb"
    assert abs(a["weak_pct"] - 75.0) < 0.1
    assert cs["home"]["weak_side"] is None

    # Kevés kapott szélső-sávos lövés: nincs ítélet.
    few = conceded_side_bias(Match(_meta(), _shot(0, 16.0)))
    assert few["away"]["weak_side"] is None


def test_wall_gaps_flags_leaky_wall():
    """A vendég fala az idő felében 7 m-es rést hagy, a másik felében
    kompakt → 50%-os rés-arány; kevés falkockánál nincs ítélet."""
    from handball.pipeline.defense import wall_gaps

    def _frame(t, wall_ys):
        players = [_pl(1, Team.HOME, 30.0, 10.0)]  # labdás hazai támadó
        players += [_pl(10 + i, Team.AWAY, 35.0, y)
                    for i, y in enumerate(wall_ys)]
        return Frame(t=t, players=players,
                     ball=Ball(x=30.0, y=10.0, confidence=1.0))

    leaky = [2.0, 4.0, 6.0, 8.0, 10.0, 17.0]       # max rés 7 m
    compact = [4.0, 6.4, 8.8, 11.2, 13.6, 16.0]    # max rés 2,4 m
    frames = [_frame(t, leaky) for t in range(150)]
    frames += [_frame(150 + t, compact) for t in range(150)]

    wg = wall_gaps(Match(_meta(), frames))
    a = wg["away"]
    assert a["frames"] == 300 and a["wide"] == 150
    assert a["share_pct"] is not None
    assert abs(a["share_pct"] - 50.0) < 0.1
    assert wg["home"]["share_pct"] is None  # a hazai nem védekezett

    # Kevés falkocka: nincs ítélet.
    few = wall_gaps(Match(_meta(), frames[:50]))
    assert few["away"]["share_pct"] is None


def test_pivot_defense_flags_weak_pivot_guarding():
    """A hazai beállós támadásai mind gólt hoznak, a beálló nélküliek
    nem → a VENDÉG beálló-őrzése gyenge; kevés beállós támadásnál
    nincs ítélet."""
    from handball.pipeline.defense import pivot_defense

    frames = []
    t = 0

    def _attack(through_pivot, goal):
        # Hazai támadás: a labda a beállónál (5-ös, x=34) vagy az
        # irányítónál (1-es, x=28) időzik, majd (ha goal) gól a +x
        # kapuba; utána vendég-birtoklás választja el a szakaszokat.
        nonlocal t, frames
        hold_x = 34.0 if through_pivot else 28.0
        for _ in range(200):
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, 27.0, 10.0),
                _pl(5, Team.HOME, 34.0, 10.0),
                _pl(20, Team.AWAY, 36.0, 8.0)],
                ball=Ball(x=hold_x, y=10.0, confidence=1.0)))
            t += 1
        if goal:
            for i in range(8):
                frames.append(Frame(t=t, players=[
                    _pl(5, Team.HOME, 34.0, 10.0)],
                    ball=Ball(x=min(34.6 + 0.8 * i, 40.0), y=10.0,
                              confidence=1.0)))
                t += 1
        for _ in range(50):
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, 20.0, 10.0),
                _pl(5, Team.HOME, 20.0, 12.0),
                _pl(20, Team.AWAY, 19.0, 10.0)],
                ball=Ball(x=19.0, y=10.0, confidence=1.0)))
            t += 1

    for _ in range(6):
        _attack(through_pivot=True, goal=True)
    for _ in range(3):
        _attack(through_pivot=False, goal=False)

    pdf = pivot_defense(Match(_meta(), frames))
    a = pdf["away"]
    assert a["pivot_attacks"] >= 6 and a["pivot_goals"] >= 6
    assert a["verdict"] == "gyenge"
    assert a["gap_pp"] is not None and a["gap_pp"] >= 15.0
    # A hazai nem védekezett beállós támadás ellen → nincs ítélet.
    assert pdf["home"]["verdict"] is None

    # Kevés beállós támadás: nincs ítélet.
    few = pivot_defense(Match(_meta(), frames[:600]))
    assert few["away"]["verdict"] is None


def test_screen_defense_flags_weak_switching():
    """A hazai elzárásos lövései mind gólt hoznak, az elzárás
    nélküliek nem → a VENDÉG váltása gyenge; kevés elzárásos
    lövésnél nincs ítélet."""
    from handball.pipeline.defense import screen_defense

    frames = []
    t = 0

    def _shot(screened, goal):
        # Hazai őrzött lövés a +x kapura: a védő a lövő mellett;
        # elzárásnál társ áll a védő mellett. Gólnál a labda a
        # kapuvonalig repül, különben a kapusnál megáll.
        nonlocal t, frames
        players = [_pl(1, Team.HOME, 30.0, 10.0),
                   _pl(20, Team.AWAY, 31.5, 10.0)]
        if screened:
            players.append(_pl(2, Team.HOME, 31.5, 11.0))
        for _ in range(30):
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=30.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        for i in range(14):
            bx = min(30.0 + 0.8 * (i + 1), 40.0 if goal else 38.6)
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=bx, y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(40):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    for _ in range(6):
        _shot(screened=True, goal=True)
    for _ in range(4):
        _shot(screened=False, goal=False)

    scd = screen_defense(Match(_meta(), frames))
    a = scd["away"]
    assert a["screened_shots"] >= 6 and a["open_shots"] >= 1
    assert a["verdict"] == "gyenge"
    assert a["gap_pp"] is not None and a["gap_pp"] >= 15.0
    # A hazai ellen nem lőttek: nincs ítélet.
    assert scd["home"]["verdict"] is None

    # Kevés elzárásos lövés: nincs ítélet.
    few = screen_defense(Match(_meta(), frames[:300]))
    assert few["away"]["verdict"] is None


def test_counter_press_separates_pressing_and_resigned_team():
    """A hazai az eladásai után 1 mp-en belül visszaszerzi a labdát a
    tíz esetből hatszor ("visszatámad"), a vendég sosem, mert a hazai
    10 mp-ig tartja ("beletörődik"); kevés eladásnál nincs ítélet."""
    from handball.pipeline.defense import counter_press

    both = [_pl(1, Team.HOME, 20.0, 10.0),
            _pl(11, Team.AWAY, 20.6, 10.0)]
    frames = []
    t = 0

    def _hold(x, n):
        """n kockányi birtoklás: a labda a megadott játékosnál."""
        nonlocal t, frames
        for _ in range(n):
            frames.append(Frame(t=t, players=both,
                                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1

    # Tíz kör: a hazai mindig 10 mp-ig tartja (a vendég sosem szerzi
    # vissza gyorsan), a vendég hatszor csak 1 mp-ig (a hazai
    # visszaszerzi), négyszer 10 mp-ig.
    for k in range(10):
        _hold(20.0, 250)                      # hazai birtoklás (10 mp)
        _hold(20.6, 25 if k < 6 else 250)     # vendég birtoklás
    _hold(20.0, 250)   # a tizedik vendég-eladás is záruljon birtoklással

    cp = counter_press(Match(_meta(), frames))
    h, a = cp["home"], cp["away"]
    assert h["turnovers"] == 10 and h["regained"] == 6
    assert h["rate_pct"] == 60.0 and h["verdict"] == "visszatámad"
    assert a["turnovers"] == 10 and a["regained"] == 0
    assert a["rate_pct"] == 0.0 and a["verdict"] == "beletörődik"

    # Kevés eladás: nincs arány és nincs ítélet.
    few = counter_press(Match(_meta(), frames[:600]))
    assert few["home"]["rate_pct"] is None
    assert few["home"]["verdict"] is None


def test_double_teams_separates_doubling_and_passive_defense():
    """A vendég két védője lép rá a hazai labdásra (kettőz), a hazai
    csak egyet küld a vendég labdására (1v1-et hagy); kevés
    labdás-kockánál nincs ítélet."""
    from handball.pipeline.defense import double_teams

    frames = []
    t = 0

    def _hold(home_has_ball, n):
        """n kockányi birtoklás: a labdás mellett egy vagy két védő."""
        nonlocal t, frames
        for _ in range(n):
            if home_has_ball:
                players = [_pl(1, Team.HOME, 20.0, 10.0),
                           _pl(11, Team.AWAY, 21.0, 10.0),
                           _pl(12, Team.AWAY, 20.0, 11.5)]
                ball = Ball(x=20.0, y=10.0, confidence=1.0)
            else:
                players = [_pl(11, Team.AWAY, 30.0, 10.0),
                           _pl(1, Team.HOME, 31.0, 10.0),
                           _pl(2, Team.HOME, 36.0, 10.0)]
                ball = Ball(x=30.0, y=10.0, confidence=1.0)
            frames.append(Frame(t=t, players=players, ball=ball))
            t += 1

    for _ in range(4):
        _hold(True, 200)    # hazai labda: a vendég kettőz
        _hold(False, 200)   # vendég labda: a hazai egy védőt küld

    dt = double_teams(Match(_meta(), frames))
    h, a = dt["home"], dt["away"]
    assert a["holder_frames"] >= 250 and a["doubled_pct"] > 90.0
    assert a["verdict"] == "kettőz"
    assert h["holder_frames"] >= 250 and h["doubled_pct"] < 10.0
    assert h["verdict"] == "1v1-et hagy"

    # Kevés labdás-kocka: nincs arány és nincs ítélet.
    few = double_teams(Match(_meta(), frames[:100]))
    assert few["away"]["doubled_pct"] is None
    assert few["away"]["verdict"] is None


def test_costly_turnover_players_names_the_expensive_loser():
    """A hazai 1-es játékos három eladásából kettőt fél percen belüli
    vendég-gól büntet, a 2-esét egy sem → a "worst" az 1-es; kevés
    eladásnál nincs megnevezett játékos."""
    from handball.pipeline.defense import costly_turnover_players

    frames = []
    t = 0

    def _cycle(pid, punished):
        """A pid-es hazai játékos elveszti a labdát; ha punished, a
        vendég fél percen belül gólt lő a 0-s kapura."""
        nonlocal t, frames
        both = [_pl(pid, Team.HOME, 20.0, 10.0),
                _pl(11, Team.AWAY, 20.6, 10.0)]
        for _ in range(10):
            frames.append(Frame(t=t, players=both,
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
        for _ in range(10):
            frames.append(Frame(t=t, players=both,
                                ball=Ball(x=20.6, y=10.0,
                                          confidence=1.0)))
            t += 1
        if punished:
            for _ in range(50):   # a lövés-elnyomó ablakon kívülre
                frames.append(Frame(t=t, players=both,
                                    ball=Ball(x=20.6, y=10.0,
                                              confidence=1.0)))
                t += 1
            shooter = [_pl(12, Team.AWAY, 7.0, 10.0)]
            for i in range(7):
                frames.append(Frame(t=t, players=shooter,
                                    ball=Ball(x=max(0.0, 6.4 - i),
                                              y=10.0, confidence=1.0)))
                t += 1
        for _ in range(60):       # szünet a következő kör előtt
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    for punished in (True, True, False):
        _cycle(1, punished)
    for _ in range(3):
        _cycle(2, False)

    ctp = costly_turnover_players(Match(_meta(), frames))
    h = ctp["home"]
    worst = h["worst"]
    assert worst is not None and worst["player_id"] == 1
    assert worst["turnovers"] == 3 and worst["punished"] == 2
    # A 2-es is szerepel a listában, de nem büntetett eladásokkal.
    second = next(p for p in h["players"] if p["player_id"] == 2)
    assert second["turnovers"] == 3 and second["punished"] == 0

    # Egyetlen kör: nincs elég eladás → nincs megnevezett játékos.
    few = costly_turnover_players(Match(_meta(), frames[:150]))
    assert few["home"]["worst"] is None


def test_wing_defense_flags_open_wings():
    """A vendég fal a szélről kapott hat lövésből ötöt gólként enged,
    középről egyet hatból → "szélen nyitott"; kevés lövésnél nincs
    ítélet."""
    from handball.pipeline.defense import wing_defense

    frames = []
    t = 0

    def _wing_shot(y, goal):
        """Hazai lövés a +x kapura a megadott y-ról (szélső vagy
        középső sáv); gólnál a kapu közepére, egyébként mellé."""
        nonlocal t, frames
        shooter = [_pl(1, Team.HOME, 31.0, y)]
        y_end = 10.0 if goal else 2.0
        for i in range(10):
            bx = min(31.0 + 0.9 * (i + 1), 40.0)
            by = y + (y_end - y) * (i + 1) / 10.0
            frames.append(Frame(t=t, players=shooter,
                                ball=Ball(x=bx, y=by, confidence=1.0)))
            t += 1
        for _ in range(40):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    # Hat szélső lövés (y = 3, azaz 7 m-re a középvonaltól): öt gól.
    for k in range(6):
        _wing_shot(3.0, goal=(k < 5))
    # Hat középső lövés (y = 10): egy gól.
    for k in range(6):
        _wing_shot(10.0, goal=(k == 0))

    wd = wing_defense(Match(_meta(), frames))
    a = wd["away"]
    assert a["wing_shots"] == 6 and a["wing_goals"] == 5
    assert a["center_shots"] == 6 and a["center_goals"] == 1
    assert a["wing_pct"] > a["center_pct"]
    assert a["verdict"] == "szélen nyitott"

    # A hazai fal nem kapott lövést → nincs arány és nincs ítélet.
    h = wd["home"]
    assert h["wing_shots"] == 0 and h["center_shots"] == 0
    assert h["gap_pp"] is None and h["verdict"] is None


def test_targeted_defenders_finds_the_soft_spot():
    """A vendég fal 8-as védője előtt hat lövésből öt gól, a 9-es előtt
    hatból egy → a 8-as a célba vett és a gyenge pont; kevés lövésnél
    nincs megnevezett védő."""
    from handball.pipeline.defense import targeted_defenders

    frames = []
    t = 0

    def _shot_at(defender_id, jersey, goal):
        """Hazai lövés a +x kapura, a megadott vendég védővel a lövő
        mellett (a másik védő messze, a kapus a kapuban)."""
        nonlocal t, frames
        players = [
            _pl(1, Team.HOME, 33.0, 10.0),
            PlayerPosition(track_id=defender_id, team=Team.AWAY,
                           x=34.0, y=10.0, source=PositionSource.MEASURED,
                           confidence=1.0, jersey_number=jersey),
            _pl(20, Team.AWAY, 33.0, 1.0),          # távoli védő
            _pl(30, Team.AWAY, 39.0, 10.0, role="kapus"),
        ]
        y_end = 10.0 if goal else 2.0
        for i in range(10):
            bx = min(33.0 + 0.7 * (i + 1), 40.0)
            by = 10.0 + (y_end - 10.0) * (i + 1) / 10.0
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=bx, y=by, confidence=1.0)))
            t += 1
        for _ in range(40):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    for k in range(6):
        _shot_at(8, 8, goal=(k < 5))
    for k in range(6):
        _shot_at(9, 9, goal=(k == 0))

    td = targeted_defenders(Match(_meta(), frames))
    a = td["away"]
    assert a["shots"] == 12 and a["goals"] == 6
    eight = next(p for p in a["players"] if p["player_id"] == 8)
    nine = next(p for p in a["players"] if p["player_id"] == 9)
    assert eight["shots"] == 6 and eight["goals"] == 5
    assert nine["shots"] == 6 and nine["goals"] == 1
    assert eight["jersey"] == 8
    assert a["weak"] is not None and a["weak"]["player_id"] == 8
    assert a["weak"]["gap_pp"] > 0
    # A kapus és a távoli védő nem kap lövést.
    assert all(p["player_id"] not in (20, 30) for p in a["players"])

    # A hazai fal nem kapott lövést → nincs célpont és nincs gyenge pont.
    assert td["home"]["shots"] == 0
    assert td["home"]["target"] is None and td["home"]["weak"] is None

    # Két lövés: nincs elég minta → nincs megnevezett védő.
    few = targeted_defenders(Match(_meta(), frames[:100]))
    assert few["away"]["target"] is None and few["away"]["weak"] is None


# ---- Kapott gólok posztonként (melyik poszt ellen szivárognak) ---------------

def test_conceded_by_role_mirrors_goals_by_role():
    """A hazai szélsőre épülő befejezése a VENDÉG oldalán jelenik meg
    kapott gólként: az ő faluk a szélső poszt ellen szivárog."""
    from handball.pipeline.defense import conceded_by_role
    from handball.pipeline.roles import goals_by_role
    from tests.test_roles import _role_goal_match

    m = _role_goal_match([2, 2, 2, 2, 1, 1])
    own = goals_by_role(m)["home"]
    rec = conceded_by_role(m)["away"]
    assert rec["goals"] == own["goals"] == 6
    assert rec["roles"] == own["roles"]
    assert rec["top"] is not None
    assert rec["top"]["poszt"] == "szélső" and rec["top"]["goals"] == 4
    # A hazai nem kapott gólt: nincs poszthoz kötött kapott gólja.
    assert conceded_by_role(m)["home"]["goals"] == 0
    assert conceded_by_role(m)["home"]["top"] is None


def test_conceded_by_role_needs_enough_goals():
    """Kevés (5-nél kevesebb) kapott gólnál nincs ítélet."""
    from handball.pipeline.defense import conceded_by_role
    from tests.test_roles import _role_goal_match

    rec = conceded_by_role(_role_goal_match([2, 2, 2]))["away"]
    assert rec["goals"] == 3 and rec["top"] is None


# ---- Hiba-sorozatok (egymás után jönnek-e az eladások) -----------------------

def _turnover_match(gaps_s, fps=25.0):
    """Hazai eladás-sorozat: a `gaps_s` az egymást követő eladások közti
    szünetek másodpercben (az első eladás a meccs elején van)."""
    frames = []
    t = 0

    def _hold(pid, team, n):
        nonlocal t, frames
        for _ in range(n):
            frames.append(Frame(t=t, players=[_pl(pid, team, 20.0, 10.0)],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    for k, gap in enumerate([0.0] + list(gaps_s)):
        # A szünetet a hazai birtoklás hossza adja; a végén a vendéghez
        # kerül a labda = eladás.
        _hold(1, Team.HOME, max(2, int(gap * fps)))
        _hold(11, Team.AWAY, 2)
    return Match(_meta(fps), frames)


def test_turnover_clusters_flags_the_streaky_side():
    """Öt eladásból négy egy percen belül követi egymást → sorozatban
    hibáznak."""
    from handball.pipeline.defense import turnover_clusters

    rec = turnover_clusters(_turnover_match([20.0, 20.0, 20.0,
                                             300.0]))["home"]
    assert rec["turnovers"] == 5
    assert rec["clusters"] == 1 and rec["clustered"] == 4
    assert rec["share_pct"] == 80.0
    assert rec["verdict"] == "sorozatban hibáznak"


def test_turnover_clusters_scattered_losses():
    """Ha minden eladás közt több perc telik el, a hibák szórtak."""
    from handball.pipeline.defense import turnover_clusters

    rec = turnover_clusters(_turnover_match([200.0] * 4))["home"]
    assert rec["turnovers"] == 5
    assert rec["clusters"] == 0 and rec["clustered"] == 0
    assert rec["share_pct"] == 0.0
    assert rec["verdict"] == "szórt hibák"


def test_turnover_clusters_needs_enough_turnovers():
    """Kevés (5-nél kevesebb) eladásnál nincs ítélet."""
    from handball.pipeline.defense import turnover_clusters

    rec = turnover_clusters(_turnover_match([20.0, 20.0]))["home"]
    assert rec["turnovers"] == 3
    assert rec["share_pct"] is None and rec["verdict"] is None


# ---- Védekezési mélység állás szerint ---------------------------------------

def _line_score_match(deep_when_leading=True, fps=25.0):
    """A VENDÉG védekezik a hazai ellen: az első szakaszban döntetlen az
    állás, majd egy vendég-gól után vezetnek — és a fal helye változik.

    A hazai a +x (vendég) kapura támad, a labdás végig a vendég
    térfelén van."""
    frames = []
    t = 0

    def _defend(seconds, depth):
        """Vendég védekezés: a védők a saját (+x) kaputól `depth` méterre
        állnak, a hazai labdás előttük."""
        nonlocal t, frames
        for _ in range(int(seconds * fps)):
            players = [_pl(1, Team.HOME, 32.0, 10.0),
                       _pl(21, Team.AWAY, 40.0 - depth, 7.0),
                       _pl(22, Team.AWAY, 40.0 - depth, 13.0),
                       _pl(29, Team.AWAY, 39.5, 10.0)]
            players[-1].role = "kapus"
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=32.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    def _away_goal():
        """Vendég-gól a −x kapura (a hazai kapujába)."""
        nonlocal t, frames
        for i in range(7):
            frames.append(Frame(
                t=t, players=[_pl(21, Team.AWAY, 8.0, 10.0)],
                ball=Ball(x=max(0.0, 6.4 - i), y=10.0, confidence=1.0)))
            t += 1

    # Döntetlennél 7 m-es fal, majd a vendég-gól után (vezetve) mélyebben
    # vagy magasabban.
    _defend(6.0, 7.0)
    _away_goal()
    _defend(6.0, 5.0 if deep_when_leading else 9.0)
    return Match(_meta(fps), frames)


def test_line_height_by_score_deep_when_leading():
    """Vezetve 5 m-re, döntetlennél 7 m-re áll a vendég fal → a rés
    negatív irányban nyílik: vezetve visszaállnak mélyre."""
    from handball.pipeline.defense import line_height_by_score

    rec = line_height_by_score(_line_score_match())["away"]
    assert rec["level"]["avg_height_m"] is not None
    assert rec["leading"]["avg_height_m"] is not None
    assert rec["leading"]["avg_height_m"] < rec["level"]["avg_height_m"]
    # Hátrányban nem védekeztek: nincs mért magasság és nincs ítélet.
    assert rec["trailing"]["avg_height_m"] is None
    assert rec["gap_m"] is None and rec["verdict"] is None


def _line_score_swing_match(fps=25.0):
    """A VENDÉG előbb hátrányban (hazai gól után), majd vezetve (két
    vendég-gól után) védekezik — hátrányban 9 m-en, vezetve 5 m-en."""
    frames = []
    t = 0

    def _defend(seconds, depth):
        nonlocal t, frames
        for _ in range(int(seconds * fps)):
            players = [_pl(1, Team.HOME, 32.0, 10.0),
                       _pl(21, Team.AWAY, 40.0 - depth, 7.0),
                       _pl(22, Team.AWAY, 40.0 - depth, 13.0),
                       _pl(29, Team.AWAY, 39.5, 10.0)]
            players[-1].role = "kapus"
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=32.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    def _goal(home):
        """Gól: a hazai a +x, a vendég a −x kapura lő."""
        nonlocal t, frames
        for i in range(7):
            bx = min(34.0 + i, 40.0) if home else max(6.4 - i, 0.0)
            who = (_pl(1, Team.HOME, 33.0, 10.0) if home
                   else _pl(21, Team.AWAY, 8.0, 10.0))
            frames.append(Frame(t=t, players=[who],
                                ball=Ball(x=bx, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(25):    # szünet a lövés-debounce-hoz
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    _goal(home=True)          # 0-1: a vendég hátrányban
    _defend(6.0, 9.0)
    _goal(home=False)         # 1-1
    _goal(home=False)         # 2-1: a vendég vezet
    _defend(6.0, 5.0)
    return Match(_meta(fps), frames)


def test_line_height_by_score_flags_the_swing():
    """Hátrányban 9 m-en, vezetve 5 m-en áll a vendég fal → 4 m-es rés:
    hátrányban feljebb lépnek (vezetve visszaállnak mélyre)."""
    from handball.pipeline.defense import line_height_by_score

    rec = line_height_by_score(_line_score_swing_match())["away"]
    assert rec["trailing"]["avg_height_m"] == 9.0
    assert rec["leading"]["avg_height_m"] == 5.0
    assert rec["gap_m"] == 4.0
    assert rec["verdict"] == "hátrányban feljebb lépnek"


def test_line_height_by_score_needs_frames():
    """Kevés védekezett kockánál nincs mért magasság."""
    from handball.pipeline.defense import line_height_by_score

    m = _line_score_match()
    rec = line_height_by_score(Match(_meta(), m.frames[:40]))["away"]
    assert rec["level"]["avg_height_m"] is None
    assert rec["verdict"] is None


# ---- Fal-csúszás késése -----------------------------------------------------

def _shift_match(lag_frames, fps=25.0, cycles=6, period=50):
    """A VENDÉG fal a labda oldalváltásait `lag_frames` késéssel követi:
    a labda y-ja szinuszosan leng, a védők átlag y-ja ugyanaz, eltolva."""
    import math

    frames = []
    n = cycles * period
    for i in range(n + lag_frames):
        ball_y = 10.0 + 6.0 * math.sin(2 * math.pi * i / period)
        wall_y = 10.0 + 6.0 * math.sin(
            2 * math.pi * (i - lag_frames) / period)
        players = [_pl(1, Team.HOME, 32.0, ball_y),
                   _pl(21, Team.AWAY, 36.0, wall_y - 2.0),
                   _pl(22, Team.AWAY, 36.0, wall_y),
                   _pl(23, Team.AWAY, 36.0, wall_y + 2.0),
                   _pl(29, Team.AWAY, 39.5, 10.0)]
        players[-1].role = "kapus"
        frames.append(Frame(t=i, players=players,
                            ball=Ball(x=32.0, y=ball_y, confidence=1.0)))
    return Match(_meta(fps), frames)


def test_defensive_shift_lag_measures_the_delay():
    """20 kocka (0,8 mp) késéssel csúszó fal → lassan csúsznak."""
    from handball.pipeline.defense import defensive_shift_lag

    rec = defensive_shift_lag(_shift_match(20))["away"]
    assert rec["frames"] >= 200
    assert rec["lag_s"] == 0.8
    assert rec["verdict"] == "lassan csúsznak"


def test_defensive_shift_lag_spots_the_quick_wall():
    """Késés nélkül együtt mozgó fal → gyorsan igazodnak."""
    from handball.pipeline.defense import defensive_shift_lag

    rec = defensive_shift_lag(_shift_match(0))["away"]
    assert rec["lag_s"] == 0.0
    assert rec["verdict"] == "gyorsan igazodnak"


def test_defensive_shift_lag_needs_frames():
    """Kevés védekezett kockánál nincs ítélet."""
    from handball.pipeline.defense import defensive_shift_lag

    rec = defensive_shift_lag(_shift_match(20, cycles=1, period=40))["away"]
    assert rec["lag_s"] is None and rec["verdict"] is None


# ---- Visszaérés-fegyelem (ki nem fut vissza védekezni) -----------------------

def _recovery_match(lingering_share=0.6, n=500, fps=25.0):
    """A VENDÉG védekezik (a hazai a vendég térfelén birtokol): a 21-es
    és 22-es végig hazaér, a 23-as a kockák `lingering_share` részében
    elöl (a hazai térfélen) marad."""
    frames = []
    for i in range(n):
        up_front = i < int(n * lingering_share)
        players = [_pl(1, Team.HOME, 32.0, 10.0),
                   _pl(21, Team.AWAY, 36.0, 7.0),
                   _pl(22, Team.AWAY, 36.0, 13.0),
                   _pl(23, Team.AWAY, 12.0 if up_front else 36.0, 10.0),
                   _pl(29, Team.AWAY, 39.5, 10.0)]
        players[-1].role = "kapus"
        frames.append(Frame(t=i, players=players,
                            ball=Ball(x=32.0, y=10.0, confidence=1.0)))
    return Match(_meta(fps), frames)


def test_recovery_discipline_flags_the_lingering_player():
    """A védekezett kockák 60%-ában elöl maradó játékos → ő lóg elöl."""
    from handball.pipeline.defense import recovery_discipline

    rec = recovery_discipline(_recovery_match())["away"]
    assert rec["worst"] is not None
    assert rec["worst"]["player_id"] == 23
    assert rec["worst"]["share_pct"] == 40.0
    # A hazaérő védők a lista végén, 100%-kal.
    assert rec["players"][-1]["share_pct"] == 100.0


def test_recovery_discipline_all_back_has_no_verdict():
    """Ha mindenki hazaér, nincs megjelölt játékos."""
    from handball.pipeline.defense import recovery_discipline

    rec = recovery_discipline(_recovery_match(lingering_share=0.0))["away"]
    assert rec["worst"] is None


def test_recovery_discipline_needs_frames():
    """Kevés mért kockánál nincs ítélet."""
    from handball.pipeline.defense import recovery_discipline

    rec = recovery_discipline(_recovery_match(n=150))["away"]
    assert rec["worst"] is None


# ---- Védekezés-keménység (mennyi büntetést hoz a fal) -----------------------

def _aggression_match(n_attacks=12, n_sevens=0, fps=25.0):
    """HAZAI támadás-sorozat a vendég fal ellen; `n_sevens` támadás
    hetessel zárul (a labda megáll a 7 m-es ponton)."""
    frames = []
    t = 0

    def _attack(with_seven):
        nonlocal t, frames
        for i in range(int(3.0 * fps)):
            players = [_pl(1, Team.HOME, 26.0 + 0.02 * i, 10.0),
                       _pl(2, Team.HOME, 24.0, 14.0),
                       _pl(21, Team.AWAY, 37.0, 8.0),
                       _pl(22, Team.AWAY, 37.0, 12.0)]
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=26.0 + 0.02 * i, y=10.0,
                                          confidence=1.0)))
            t += 1
        if with_seven:
            for _ in range(int(1.5 * fps)):   # a labda áll a 7 m-es ponton
                frames.append(Frame(
                    t=t, players=[_pl(1, Team.HOME, 32.0, 10.0)],
                    ball=Ball(x=33.0, y=10.0, confidence=1.0)))
                t += 1
        for i in range(int(11.0 * fps)):      # vendég-birtoklás (elválasztó)
            frames.append(Frame(
                t=t, players=[_pl(21, Team.AWAY, 18.0 - 0.05 * i, 10.0),
                              _pl(22, Team.AWAY, 15.0, 14.0)],
                ball=Ball(x=18.0 - 0.05 * i, y=10.0, confidence=1.0)))
            t += 1

    for k in range(n_attacks):
        _attack(k < n_sevens)
    return Match(_meta(fps), frames)


def test_defensive_aggression_flags_the_hard_wall():
    """12 védekezett támadás, 3 megítélt hetes → kemény fal."""
    from handball.pipeline.defense import defensive_aggression

    rec = defensive_aggression(
        _aggression_match(n_attacks=12, n_sevens=3))["away"]
    assert rec["attacks"] >= 10 and rec["sevens"] == 3
    assert rec["pct"] is not None and rec["pct"] >= 12.0
    assert rec["verdict"] == "kemény fal"


def test_defensive_aggression_flags_the_soft_wall():
    """Büntetés nélküli védekezés → passzív fal."""
    from handball.pipeline.defense import defensive_aggression

    rec = defensive_aggression(_aggression_match(n_attacks=12))["away"]
    assert rec["sevens"] == 0 and rec["suspensions"] == 0
    assert rec["pct"] == 0.0 and rec["verdict"] == "passzív fal"


def test_defensive_aggression_needs_enough_attacks():
    """Kevés védekezett támadásnál nincs ítélet."""
    from handball.pipeline.defense import defensive_aggression

    rec = defensive_aggression(_aggression_match(n_attacks=4))["away"]
    assert rec["pct"] is None and rec["verdict"] is None


# ---- Kapott gólok támadás-típus szerint --------------------------------------

def _conceded_type_match(n_breaks=5, n_positional=2, fps=25.0):
    """HAZAI gólok lerohanásból és felállt támadásból — a VENDÉG
    kapott góljaiként jelennek meg."""
    frames = []
    t = 0

    def _attack(fast):
        nonlocal t, frames
        if fast:      # 22 → 38 m négy másodperc alatt: lerohanás
            n = int(4.0 * fps)
            x0, x1 = 22.0, 38.0
        else:         # helyben járó felállt támadás
            n = int(30.0 * fps)
            x0, x1 = 26.0, 27.0
        for i in range(n):
            x = x0 + (x1 - x0) * i / max(1, n - 1)
            frames.append(Frame(
                t=t, players=[_pl(1, Team.HOME, x, 10.0),
                              _pl(21, Team.AWAY, 37.0, 12.0)],
                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1
        for i in range(7):    # gól a +x kapura
            frames.append(Frame(
                t=t, players=[_pl(1, Team.HOME, 33.0, 10.0)],
                ball=Ball(x=min(34.0 + i, 40.0), y=10.0,
                          confidence=1.0)))
            t += 1
        for i in range(int(2.0 * fps)):   # vendég-birtoklás: elválasztó
            frames.append(Frame(
                t=t, players=[_pl(21, Team.AWAY, 18.0 - 0.05 * i, 10.0)],
                ball=Ball(x=18.0 - 0.05 * i, y=10.0, confidence=1.0)))
            t += 1

    for _ in range(n_breaks):
        _attack(fast=True)
    for _ in range(n_positional):
        _attack(fast=False)
    return Match(_meta(fps), frames)


def test_conceded_by_attack_type_flags_the_fast_breaks():
    """Öt lerohanásból és két felállt támadásból kapott gól → a
    lerohanás a vezető műfaj a vendég kapott góljaiban."""
    from handball.pipeline.defense import conceded_by_attack_type

    rec = conceded_by_attack_type(_conceded_type_match())["away"]
    assert rec["goals"] >= 5
    assert rec["top"] is not None
    assert "lerohanás" in rec["top"]["type"]
    assert rec["top"]["share_pct"] >= 40.0
    # A hazai nem kapott gólt.
    assert conceded_by_attack_type(_conceded_type_match())["home"]["goals"] == 0


def test_conceded_by_attack_type_needs_enough_goals():
    """Kevés (5-nél kevesebb) kapott gólnál nincs ítélet."""
    from handball.pipeline.defense import conceded_by_attack_type

    rec = conceded_by_attack_type(
        _conceded_type_match(n_breaks=2, n_positional=1))["away"]
    assert rec["goals"] == 3 and rec["top"] is None


# ---- Falépítés-idő (mennyi idő alatt áll fel a fal) --------------------------

def _setup_time_match(delay_s, n_cases=5, fps=25.0):
    """Birtokváltás-sorozat: a VENDÉG védői `delay_s` másodperc múlva
    érnek vissza a saját (+x) kapujuk 12 m-es zónájába."""
    frames = []
    t = 0

    def _defenders(back):
        """A vendég öt mezőnyvédője: elöl (22 m) vagy a kapu előtt."""
        x = 34.0 if back else 22.0
        return [_pl(20 + k, Team.AWAY, x, 6.0 + k) for k in range(5)]

    for _ in range(n_cases):
        # A vendég birtokol (a hazai védekezik).
        for _ in range(int(2.0 * fps)):
            frames.append(Frame(
                t=t, players=[_pl(21, Team.AWAY, 20.0, 10.0)],
                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
            t += 1
        # Birtokváltás: a hazai kapja meg — a vendég védekezni kezd.
        for _ in range(int(delay_s * fps)):
            frames.append(Frame(
                t=t, players=[_pl(1, Team.HOME, 24.0, 10.0)]
                + _defenders(back=False),
                ball=Ball(x=24.0, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(int(3.0 * fps)):
            frames.append(Frame(
                t=t, players=[_pl(1, Team.HOME, 26.0, 10.0)]
                + _defenders(back=True),
                ball=Ball(x=26.0, y=10.0, confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_defense_setup_time_flags_the_slow_wall():
    """10 másodperces visszaérés → lassan állnak fel."""
    from handball.pipeline.defense import defense_setup_time

    rec = defense_setup_time(_setup_time_match(delay_s=10.0))["away"]
    assert rec["cases"] >= 4
    assert rec["avg_s"] is not None and rec["avg_s"] >= 8.0
    assert rec["verdict"] == "lassan állnak fel"


def test_defense_setup_time_flags_the_quick_wall():
    """3 másodperces visszaérés → gyorsan rendeződnek."""
    from handball.pipeline.defense import defense_setup_time

    rec = defense_setup_time(_setup_time_match(delay_s=3.0))["away"]
    assert rec["avg_s"] <= 5.0
    assert rec["verdict"] == "gyorsan rendeződnek"


def test_defense_setup_time_needs_enough_cases():
    """Kevés mért birtokváltásnál nincs ítélet."""
    from handball.pipeline.defense import defense_setup_time

    rec = defense_setup_time(_setup_time_match(delay_s=10.0,
                                               n_cases=2))["away"]
    assert rec["avg_s"] is None and rec["verdict"] is None


# ---- Elöl szerző védők -------------------------------------------------------

def _high_steal_match(cases, fps=25.0):
    """Labdaszerzés-sorozat: a `cases` elemei (szerző id, elöl?)
    párok — a hazai szerez, elöl = a vendég térfelén (x=30)."""
    frames = []
    t = 0
    for (pid, high) in cases:
        x = 30.0 if high else 8.0
        for _ in range(10):     # a vendég birtokol
            frames.append(Frame(
                t=t, players=[_pl(21, Team.AWAY, x, 10.0)],
                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(10):     # a hazai szerzi meg
            frames.append(Frame(
                t=t, players=[_pl(pid, Team.HOME, x, 10.0)],
                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_high_steal_players_finds_the_front_stealer():
    """Aki négy szerzéséből hármat elöl szed → az ő oldalán nem
    szabad kihozni a labdát."""
    from handball.pipeline.defense import high_steal_players

    rec = high_steal_players(_high_steal_match(
        [(5, True)] * 3 + [(5, False)] + [(7, False)] * 3))["home"]
    assert rec["top"] is not None
    assert rec["top"]["player_id"] == 5
    assert rec["top"]["steals"] == 4 and rec["top"]["high"] == 3


def test_high_steal_players_needs_enough_steals():
    """Kevés (3-nál kevesebb) szerzésnél nincs kiemelt védő."""
    from handball.pipeline.defense import high_steal_players

    rec = high_steal_players(_high_steal_match(
        [(5, True), (7, False)]))["home"]
    assert rec["top"] is None


# ---- Fedezetten lövők --------------------------------------------------------

def _covered_shot_match(cases, fps=25.0):
    """Lövés-sorozat: a `cases` elemei (lövő id, fedezett?) párok — a
    fedezett lövésnél a védő 1 m-re, egyébként 5 m-re áll."""
    frames = []
    t = 0
    for (pid, covered) in cases:
        players = [_pl(pid, Team.HOME, 33.0, 10.0),
                   _pl(30, Team.AWAY, 34.0 if covered else 34.0,
                       11.0 if covered else 16.0)]
        for i in range(3):
            frames.append(Frame(t=t + i, players=players,
                                ball=Ball(x=33.0, y=10.0,
                                          confidence=1.0)))
        t += 3
        for i in range(9):
            frames.append(Frame(
                t=t, players=players,
                ball=Ball(x=min(34.0 + i, 40.0), y=10.0,
                          confidence=1.0)))
            t += 1
        for i in range(25):    # szünet a lövés-debounce-hoz
            frames.append(Frame(t=t + i, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
        t += 25
    return Match(_meta(fps), frames)


def test_covered_shooters_finds_the_pressure_shooter():
    """A 9-es hat lövéséből ötöt fedezetten ad le → rá nem kell
    kilépni."""
    from handball.pipeline.defense import covered_shooters

    cases = [(9, True)] * 5 + [(9, False)] + [(4, False)] * 5
    rec = covered_shooters(_covered_shot_match(cases))["home"]
    assert rec["top"] is not None
    assert rec["top"]["player_id"] == 9
    assert rec["top"]["shots"] == 6 and rec["top"]["covered"] == 5


def test_covered_shooters_needs_enough_shots():
    """Kevés (5-nél kevesebb) lövésnél nincs kiemelt lövő."""
    from handball.pipeline.defense import covered_shooters

    rec = covered_shooters(_covered_shot_match(
        [(9, True), (9, True), (4, False)]))["home"]
    assert rec["top"] is None


# ---- Gól utáni letámadás (saját gól után feljebb megy-e a fal) --------------

def _press_after_goal_match(after_depth, base_depth, after_frames=200,
                            base_frames=200):
    """HAZAI gól, utána `after_frames` kockányi hazai védekezés
    `after_depth` méteren, majd az ablakon kívül `base_depth` méteren."""
    frames = []
    t = 0
    for i in range(8):                       # hazai gól a +x kapuba
        frames.append(Frame(
            t=t, players=[_pl(1, Team.HOME, 33.0, 10.0)],
            ball=Ball(x=min(34.0 + i, 40.0), y=10.0, confidence=1.0)))
        t += 1

    def _defense(n, depth):
        out = []
        nonlocal t
        for _ in range(n):
            out.append(Frame(t=t, players=[
                _pl(20, Team.AWAY, 8.0, 10.0),          # labdás támadó
                _pl(10, Team.HOME, depth, 7.0),         # hazai fal
                _pl(11, Team.HOME, depth, 13.0),
                _pl(9, Team.HOME, 0.5, 10.0, role="kapus"),
            ], ball=Ball(x=8.0, y=10.0, confidence=1.0)))
            t += 1
        return out

    frames += _defense(after_frames, after_depth)       # a gól utáni ablak
    t += 600                                            # ki az ablakból
    frames += _defense(base_frames, base_depth)
    return Match(_meta(), frames)


def test_press_after_goal_finds_the_pressing_team():
    """Gól után 9 m-es, egyébként 5 m-es fal → gól után letámadnak."""
    from handball.pipeline.defense import press_after_goal

    rec = press_after_goal(_press_after_goal_match(9.0, 5.0))["home"]
    assert rec["after_m"] == 9.0 and rec["base_m"] == 5.0
    assert rec["verdict"] == "gól után letámadnak"


def test_press_after_goal_finds_the_dropping_team():
    """Fordítva (gól után mélyebb fal) → gól után visszahúzódnak."""
    from handball.pipeline.defense import press_after_goal

    rec = press_after_goal(_press_after_goal_match(5.0, 9.0))["home"]
    assert rec["verdict"] == "gól után visszahúzódnak"


def test_press_after_goal_needs_enough_frames():
    """Kevés (60-nál kevesebb) gól utáni kocka esetén nincs ítélet."""
    from handball.pipeline.defense import press_after_goal

    rec = press_after_goal(_press_after_goal_match(
        9.0, 5.0, after_frames=30))["home"]
    assert rec["after_frames"] == 30 and rec["verdict"] is None
    assert rec["after_m"] is None


# ---- Labdaszerzés-típus (elfogás vagy szerelés) ----------------------------

def _steal_types_match(kinds, fps=25.0):
    """Vendég labdaszerzés-sorozat: a `kinds` elemei "int" (röptében
    elfogott passz) vagy "tackle" (kézből kézbe, testre szerelés)."""
    frames = []
    t = 0

    def _hold(pid, team, x, n):
        nonlocal t
        for _ in range(n):
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, 20.0, 10.0),
                _pl(21, Team.AWAY, 28.0, 10.0)],
                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1

    for kind in kinds:
        _hold(1, Team.HOME, 20.0, 10)          # hazai birtoklás
        if kind == "int":
            for _ in range(7):                 # a labda röptében jár
                frames.append(Frame(t=t, players=[
                    _pl(1, Team.HOME, 20.0, 10.0),
                    _pl(21, Team.AWAY, 28.0, 10.0)],
                    ball=Ball(x=24.0, y=10.0, confidence=1.0)))
                t += 1
        _hold(21, Team.AWAY, 28.0, 10)         # a vendégnél a labda
    return Match(_meta(fps), frames)


def test_steal_types_flags_the_lane_closers():
    """Hat szerzésből öt röptében elfogott passz → a passzsávakat
    zárják."""
    from handball.pipeline.defense import steal_types

    rec = steal_types(_steal_types_match(["int"] * 5 + ["tackle"]))["away"]
    assert rec["steals"] == 6 and rec["interceptions"] == 5
    assert rec["verdict"] == "a passzsávakat zárják"


def test_steal_types_flags_the_body_tacklers():
    """Hat szerzésből öt kézből kézbe (testre szerelés) → testre
    mennek."""
    from handball.pipeline.defense import steal_types

    rec = steal_types(_steal_types_match(["tackle"] * 5 + ["int"]))["away"]
    assert rec["tackles"] == 5 and rec["verdict"] == "testre mennek"


def test_steal_types_needs_enough_steals():
    """Kevés (6-nál kevesebb) szerzésnél nincs ítélet."""
    from handball.pipeline.defense import steal_types

    rec = steal_types(_steal_types_match(["int"] * 3))["away"]
    assert rec["steals"] == 3 and rec["int_pct"] is None
    assert rec["verdict"] is None


# ---- Szerzés utáni indítás (azonnal előre megy-e a szerzett labda) ----------

def _steal_launch_match(kinds, fps=25.0):
    """Vendég szerzés-sorozat: a `kinds` elemei "fast" (a labda azonnal
    a kapu felé indul) vagy "safe" (biztosító járatás helyben).
    A vendég a -x kapu felé támad."""
    frames = []
    t = 0

    def _emit(players, bx, by):
        nonlocal t
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=bx, y=by, confidence=1.0)))
        t += 1

    home = lambda: _pl(1, Team.HOME, 20.0, 10.0)
    for kind in kinds:
        for _ in range(10):                      # hazai birtoklás
            _emit([home(), _pl(21, Team.AWAY, 28.0, 16.0)], 20.0, 10.0)
        if kind == "fast":                       # szerzés + azonnali indítás
            for i in range(50):
                x = 28.0 - 14.0 * i / 49.0
                _emit([home(), _pl(21, Team.AWAY, x, 16.0)], x, 16.0)
            for _ in range(50):
                _emit([home(), _pl(21, Team.AWAY, 14.0, 16.0)], 14.0, 16.0)
        else:                                    # szerzés + helyben járatás
            for _ in range(100):
                _emit([home(), _pl(21, Team.AWAY, 28.0, 16.0)], 28.0, 16.0)
    return Match(_meta(fps), frames)


def test_steal_launch_flags_the_instant_launchers():
    """Hat szerzésből öt azonnali előre-indítás → szerzés után azonnal
    indítanak."""
    from handball.pipeline.defense import steal_launch

    rec = steal_launch(_steal_launch_match(["fast"] * 5 + ["safe"]))["away"]
    assert rec["steals"] == 6 and rec["forward"] == 5
    assert rec["verdict"] == "szerzés után azonnal indítanak"


def test_steal_launch_flags_the_securers():
    """Hat szerzésből öt helyben járatás → szerzés után biztosítanak."""
    from handball.pipeline.defense import steal_launch

    rec = steal_launch(_steal_launch_match(["safe"] * 5 + ["fast"]))["away"]
    assert rec["forward"] == 1 and rec["verdict"] == "szerzés után biztosítanak"


def test_steal_launch_needs_enough_steals():
    """Kevés (6-nál kevesebb) szerzésnél nincs ítélet."""
    from handball.pipeline.defense import steal_launch

    rec = steal_launch(_steal_launch_match(["fast"] * 3))["away"]
    assert rec["steals"] == 3 and rec["fwd_pct"] is None
    assert rec["verdict"] is None


# ---- Kilépő védő (van-e előretolt ember a falban) ---------------------------

def _advanced_defender_match(stepper_depth, n_frames=150):
    """A HAZAI fal a saját (0-s) kapunál véd: két mély védő 6 m-en, a
    15-ös track a megadott mélységen; a vendég a hazai térfélen
    birtokol."""
    frames = []
    for t in range(n_frames):
        players = [
            _pl(20, Team.AWAY, 8.0, 10.0),            # labdás támadó
            _pl(10, Team.HOME, 6.0, 7.0),
            _pl(11, Team.HOME, 6.0, 13.0),
            _pl(15, Team.HOME, stepper_depth, 10.0),  # jelölt kilépő
            _pl(9, Team.HOME, 0.5, 10.0, role="kapus"),
        ]
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=8.0, y=10.0, confidence=1.0)))
    return Match(_meta(), frames)


def test_advanced_defender_finds_the_stepper():
    """A 15-ös 10 m-en áll a társak 6 m-e előtt → van kilépő védőjük."""
    from handball.pipeline.defense import advanced_defender

    rec = advanced_defender(_advanced_defender_match(10.0))["home"]
    assert rec["top"] is not None and rec["top"]["player_id"] == 15
    assert rec["gap_m"] >= 2.5
    assert rec["verdict"] == "van kilépő védőjük"


def test_advanced_defender_flat_wall_has_no_verdict():
    """Lapos falnál (mindenki 6-7 m-en) nincs kilépő."""
    from handball.pipeline.defense import advanced_defender

    rec = advanced_defender(_advanced_defender_match(7.0))["home"]
    assert rec["top"] is None and rec["verdict"] is None


def test_advanced_defender_needs_enough_frames():
    """Kevés mért kockánál (100 alatt) nincs ítélet."""
    from handball.pipeline.defense import advanced_defender

    rec = advanced_defender(_advanced_defender_match(10.0, n_frames=50))["home"]
    assert rec["players"] == [] and rec["verdict"] is None


# ---- Beálló-őr (ki őrzi az ellenfél beállóját) ------------------------------

def _pivot_guard_match(split_guard=False, n=400):
    """A vendég a hazai (0-s) kapura támad, beállója a hatoson; a
    hazai 10-es (vagy felváltva a 10-es és 11-es) őrzi."""
    frames = []
    for t in range(n):
        guard_near = 10 if (not split_guard or t % 2 == 0) else 11
        players = [
            _pl(20, Team.AWAY, 8.0, 16.0),    # labdás vendég (hazai térfél)
            _pl(25, Team.AWAY, 5.0, 10.0),    # vendég beálló
            _pl(10, Team.HOME, 4.5 if guard_near == 10 else 9.0, 10.0),
            _pl(11, Team.HOME, 4.5 if guard_near == 11 else 9.0, 10.5),
            _pl(9, Team.HOME, 0.5, 10.0, role="kapus"),
        ]
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=8.0, y=16.0, confidence=1.0)))
    return Match(_meta(), frames)


def test_pivot_guards_finds_the_dedicated_guard():
    """A 10-es végig a beállón → egy ember őrzi a beállót."""
    from handball.pipeline.defense import pivot_guards

    rec = pivot_guards(_pivot_guard_match())["home"]
    assert rec["top"] is not None and rec["top"]["player_id"] == 10
    assert rec["verdict"] == "egy ember őrzi a beállót"


def test_pivot_guards_split_duty_has_no_verdict():
    """Ha ketten felváltva őrzik, nincs kiemelt őr."""
    from handball.pipeline.defense import pivot_guards

    rec = pivot_guards(_pivot_guard_match(split_guard=True))["home"]
    assert rec["top"] is None and rec["verdict"] is None


def test_pivot_guards_needs_enough_frames():
    """Kevés (300-nál kevesebb) mért őrzés-kockánál nincs ítélet."""
    from handball.pipeline.defense import pivot_guards

    rec = pivot_guards(_pivot_guard_match(n=200))["home"]
    assert rec["verdict"] is None


# ---- Szélső-kifutás (időben érnek-e ki a szélső lövéseire) ------------------

def _wco_match(def_dist, n_shots=5, fps=25.0):
    """A hazai szélső (2-es) lő; a vendég legközelebbi védője
    def_dist méterre áll tőle."""
    frames = []
    t = 0
    for _ in range(150):        # poszt-minta: a 2-es a szélső sávban
        frames.append(Frame(t=t, players=[
            _pl(2, Team.HOME, 36.0, 2.0),
            _pl(3, Team.HOME, 28.0, 10.0),
            _pl(21, Team.AWAY, 30.0, 16.0)],
            ball=Ball(x=28.0, y=10.0, confidence=1.0)))
        t += 1
    for _ in range(n_shots):
        for i in range(8):      # a szélső lövése a +x kapura
            frames.append(Frame(t=t, players=[
                _pl(2, Team.HOME, 36.0, 2.0),
                _pl(21, Team.AWAY, 36.0, 2.0 + def_dist),
                _pl(29, Team.AWAY, 39.5, 10.0, role="kapus")],
                ball=Ball(x=min(36.0 + i, 40.0),
                          y=2.0 + 8.0 * min(1.0, i / 4.0),
                          confidence=1.0)))
            t += 1
        for _ in range(40):     # szünet
            frames.append(Frame(t=t, players=[
                _pl(3, Team.HOME, 28.0, 10.0)],
                ball=Ball(x=28.0, y=10.0, confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_wing_closeouts_flags_the_late_wall():
    """A védő 4 m-re áll a lövő szélsőtől → későn érnek ki."""
    from handball.pipeline.defense import wing_closeouts

    rec = wing_closeouts(_wco_match(4.0))["away"]
    assert rec["shots"] == 5 and rec["avg_m"] >= 2.5
    assert rec["verdict"] == "későn érnek ki a szélre"


def test_wing_closeouts_flags_the_tight_wall():
    """1 m-en belüli védőnél zárják a szélsőt."""
    from handball.pipeline.defense import wing_closeouts

    rec = wing_closeouts(_wco_match(1.0))["away"]
    assert rec["verdict"] == "zárják a szélsőt"


def test_wing_closeouts_needs_enough_shots():
    """Kevés (4-nél kevesebb) szélső-lövésnél nincs ítélet."""
    from handball.pipeline.defense import wing_closeouts

    rec = wing_closeouts(_wco_match(4.0, n_shots=2))["away"]
    assert rec["shots"] == 2 and rec["verdict"] is None


# ---- Blokk-lepattanó (a blokk után ki szerzi meg a labdát) ------------------

def _brc_match(recover_flags, fps=25.0):
    """Vendég blokkok hazai lövéseken; a `recover_flags` szerint a
    lepattanót a blokkoló (True) vagy a lövő (False) szerzi meg."""
    frames = []
    t = 0
    shooter = _pl(1, Team.HOME, 28.0, 10.0)
    blocker = _pl(20, Team.AWAY, 32.5, 10.0)
    for recovered in recover_flags:
        for x in (29.0, 30.2, 31.4, 32.4):     # lövés a blokkba
            frames.append(Frame(t=t, players=[shooter, blocker],
                                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1
        if recovered:                           # a lepattanó a blokkolóé
            path = (32.2, 32.4, 32.5, 32.5, 32.5, 32.5)
        else:                                   # visszahull a lövőhöz
            path = (31.0, 29.5, 28.0, 28.0, 28.0, 28.0)
        for x in path:
            frames.append(Frame(t=t, players=[shooter, blocker],
                                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(40):                     # szünet (debounce)
            frames.append(Frame(t=t, players=[shooter, blocker],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    return Match(_meta(), frames)


def test_block_recoveries_flags_the_full_value_blocks():
    """Négy blokkból négy lepattanó a blokkolóé → a labdát is
    megszerzik."""
    from handball.pipeline.defense import block_recoveries

    rec = block_recoveries(_brc_match([True] * 4))["away"]
    assert rec["blocks"] == 4 and rec["recovered"] == 4
    assert rec["verdict"] == "a blokk után a labdát is megszerzik"


def test_block_recoveries_flags_the_bouncing_blocks():
    """Ha a lepattanó rendre a lövőhöz hull vissza, a blokk nem teljes
    értékű."""
    from handball.pipeline.defense import block_recoveries

    rec = block_recoveries(_brc_match([False] * 4))["away"]
    assert rec["recovered"] == 0
    assert rec["verdict"] == "a blokkjaik visszahullanak"


def test_block_recoveries_needs_enough_blocks():
    """Kevés (4-nél kevesebb) mért blokknál nincs ítélet."""
    from handball.pipeline.defense import block_recoveries

    rec = block_recoveries(_brc_match([True, True]))["away"]
    assert rec["blocks"] == 2 and rec["verdict"] is None


# ---- Lefogott lövők (kinek a lövését viszi el a fal) ------------------------

def _bsh_match(shooter_ids, fps=25.0):
    """Blokkolt lövés-sorozat: a `shooter_ids` sorrendjében mindig a
    megadott hazai játékos lövését fogja le a vendég védő."""
    frames = []
    t = 0
    blocker = _pl(20, Team.AWAY, 32.5, 10.0)
    for sid in shooter_ids:
        shooter = _pl(sid, Team.HOME, 28.0, 10.0)
        for x in (29.0, 30.2, 31.4, 32.4, 31.0, 29.5, 28.0):
            frames.append(Frame(t=t, players=[shooter, blocker],
                                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1
        for _i in range(40):  # szünet (blokk-cooldown), a lövőnél a
            frames.append(Frame(t=t, players=[shooter, blocker],
                                ball=Ball(x=28.0, y=10.0,
                                          confidence=1.0)))
            t += 1  # labda — így poszt-minta is gyűlik
    return Match(_meta(fps), frames)


def test_blocked_shooters_names_the_blocked_shooter():
    """Négy blokkból három az 1-es lövését éri → ő a lefogott lövő."""
    from handball.pipeline.defense import blocked_shooters

    rec = blocked_shooters(_bsh_match([1, 1, 1, 2]))["home"]
    assert rec["blocked"] == 4
    assert rec["shooters"][0]["player_id"] == 1
    assert rec["top"] is not None
    assert rec["top"]["player_id"] == 1
    assert rec["top"]["share_pct"] == 75.0


def test_blocked_shooters_needs_enough_blocks():
    """Kevés (4-nél kevesebb) lefogott lövésnél nincs kiemelt lövő."""
    from handball.pipeline.defense import blocked_shooters

    rec = blocked_shooters(_bsh_match([1, 1, 2]))["home"]
    assert rec["blocked"] == 3 and rec["top"] is None


# ---- Falba lövő posztok (melyik poszt lő a falba) ---------------------------

def test_blocked_by_role_points_to_the_backcourt():
    """A 12 méterről (irányító-poszt) falba lőtt négy lövés → a hátsó
    sor lő a falba."""
    from handball.pipeline.defense import blocked_by_role

    rec = blocked_by_role(_bsh_match([1, 1, 1, 1]))["home"]
    assert rec["blocked"] == 4
    assert rec["top"] is not None
    assert rec["top"]["poszt"] == "irányító"
    assert rec["top"]["share_pct"] == 100.0


def test_blocked_by_role_needs_enough_blocks():
    """Kevés (4-nél kevesebb) poszthoz kötött lefogott lövésnél nincs
    kiemelt poszt."""
    from handball.pipeline.defense import blocked_by_role

    rec = blocked_by_role(_bsh_match([1, 1, 1]))["home"]
    assert rec["top"] is None


# ---- Kettőző emberek (ki jön másodiknak a labdásra) -------------------------

def _dtp_match(n_frames=60, fps=25.0):
    """Kettőzött kockák: a hazai labdásra a 21-es lép rá elsőnek, a
    22-es jön másodiknak — ő a kettőző ember."""
    frames = []
    for t in range(n_frames):
        frames.append(Frame(t=t, players=[
            _pl(1, Team.HOME, 30.0, 10.0),
            _pl(21, Team.AWAY, 31.0, 10.0),
            _pl(22, Team.AWAY, 30.0, 12.0),
            _pl(23, Team.AWAY, 36.0, 10.0)],
            ball=Ball(x=30.0, y=10.0, confidence=1.0)))
    return Match(_meta(fps), frames)


def test_doubling_defenders_names_the_second_man():
    """A mindig másodiknak érkező 22-es a kiemelt kettőző ember."""
    from handball.pipeline.defense import doubling_defenders

    rec = doubling_defenders(_dtp_match())["away"]
    assert rec["doubled_frames"] >= 50
    assert rec["top"] is not None
    assert rec["top"]["player_id"] == 22


def test_doubling_defenders_needs_enough_frames():
    """Kevés (50-nél kevesebb) kettőzött kockánál nincs kiemelt."""
    from handball.pipeline.defense import doubling_defenders

    rec = doubling_defenders(_dtp_match(n_frames=30))["away"]
    assert rec["top"] is None


# ---- Átvert védők (ki mögött esnek a kapott gólok) --------------------------

def _btn_match(n_goals=5, with_defender=True, fps=25.0):
    """Hazai gól-sorozat: a lövő mellett (vagy tőle távol) áll a
    vendég 21-es védő — ő az átvert ember (vagy fedezetlen a lövés)."""
    frames = []
    t = 0
    dx = 34.0 if with_defender else 37.0
    dy = 10.0 if with_defender else 3.0
    for _ in range(n_goals):
        for _ in range(10):     # a lövő birtokol
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, 33.0, 10.0),
                _pl(21, Team.AWAY, dx, dy)],
                ball=Ball(x=33.0, y=10.0, confidence=1.0)))
            t += 1
        for i in range(8):      # gól a +x kapura
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, 33.0, 10.0),
                _pl(21, Team.AWAY, dx, dy)],
                ball=Ball(x=min(33.0 + (i + 1), 40.5), y=10.0,
                          confidence=1.0)))
            t += 1
        for _ in range(40):     # szünet a gólok közt
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_beaten_defenders_names_the_beaten_man():
    """A lövő mellett álló 21-es minden gólnál átvert → ő a kiemelt."""
    from handball.pipeline.defense import beaten_defenders

    rec = beaten_defenders(_btn_match())["away"]
    assert rec["goals"] >= 4
    assert rec["top"] is not None
    assert rec["top"]["player_id"] == 21


def test_beaten_defenders_counts_free_goals():
    """A radiuson kívüli védő mellett esett gól fedezetlen, nem
    párharc-vereség."""
    from handball.pipeline.defense import beaten_defenders

    rec = beaten_defenders(_btn_match(with_defender=False))["away"]
    assert rec["goals"] == 0 and rec["free"] >= 4
    assert rec["top"] is None


def test_beaten_defenders_needs_enough_goals():
    """Kevés (4-nél kevesebb) védőhöz rendelt gólnál nincs kiemelt."""
    from handball.pipeline.defense import beaten_defenders

    rec = beaten_defenders(_btn_match(n_goals=3))["away"]
    assert rec["top"] is None


# ---- Zavartalan előkészítők (hagyják-e dolgozni a gólpassz-adót) ------------

def _upa_match(pressured, n_goals=5, fps=25.0):
    """Gólpasszos hazai gól-sorozat: a kiadó (3-as) mellett vagy áll
    vendég védő (nyomás), vagy nem — a lövő (1-es) a bejátszás után
    a kapuba lő."""
    frames = []
    t = 0
    dx, dy = (27.2, 11.5) if pressured else (24.0, 16.0)

    def _emit(bx, by, n):
        nonlocal t
        for _ in range(n):
            frames.append(Frame(t=t, players=[
                _pl(3, Team.HOME, 28.0, 10.0),
                _pl(1, Team.HOME, 33.0, 10.0),
                _pl(21, Team.AWAY, dx, dy)],
                ball=Ball(x=bx, y=by, confidence=1.0)))
            t += 1

    for _ in range(n_goals):
        _emit(28.0, 10.0, 10)       # a kiadónál a labda
        for i in range(4):          # gólpassz a lövőnek
            _emit(28.0 + (33.0 - 28.0) * (i + 1) / 4.0, 10.0, 1)
        _emit(33.0, 10.0, 4)        # a lövőnél a labda
        for i in range(8):          # gól a +x kapura
            _emit(min(33.0 + (i + 1), 40.5), 10.0, 1)
        for _ in range(40):         # szünet a gólok közt
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_unpressured_assists_flags_the_loose_defense():
    """Nyomás nélküli kiadó minden gólnál → hagyják dolgozni."""
    from handball.pipeline.defense import unpressured_assists

    rec = unpressured_assists(_upa_match(False))["away"]
    assert rec["assisted"] >= 5
    assert rec["verdict"] == "az előkészítőt hagyják dolgozni"


def test_unpressured_assists_flags_the_pressing_defense():
    """A kiadó mellett álló védő minden gólnál → rálépnek."""
    from handball.pipeline.defense import unpressured_assists

    rec = unpressured_assists(_upa_match(True))["away"]
    assert rec["unpressured"] == 0
    assert rec["verdict"] == "az előkészítőre rálépnek"


def test_unpressured_assists_needs_enough_goals():
    """Kevés (5-nél kevesebb) gólpasszos kapott gólnál nincs ítélet."""
    from handball.pipeline.defense import unpressured_assists

    rec = unpressured_assists(_upa_match(False, n_goals=3))["away"]
    assert rec["verdict"] is None


# ---- Folyosó-gólok (nyitott folyosón kapják-e a gólokat) --------------------

def _crg_match(blocked, n_goals=5, fps=25.0):
    """Hazai gól-sorozat: a lövés útjában áll (vagy nem áll) vendég
    védő — a folyosó zárt vagy nyitott."""
    frames = []
    t = 0
    dx, dy = (36.0, 10.0) if blocked else (36.0, 4.0)
    for _ in range(n_goals):
        for _ in range(10):
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, 33.0, 10.0),
                _pl(21, Team.AWAY, dx, dy)],
                ball=Ball(x=33.0, y=10.0, confidence=1.0)))
            t += 1
        for i in range(8):
            frames.append(Frame(t=t, players=[
                _pl(1, Team.HOME, 33.0, 10.0),
                _pl(21, Team.AWAY, dx, dy)],
                ball=Ball(x=min(33.0 + (i + 1), 40.5), y=10.0,
                          confidence=1.0)))
            t += 1
        for _ in range(40):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_corridor_goals_flags_the_open_corridors():
    """A lövésvonaltól távol álló védő → nyitott folyosós gólok."""
    from handball.pipeline.defense import corridor_goals

    rec = corridor_goals(_crg_match(False))["away"]
    assert rec["goals"] >= 5 and rec["open"] == rec["goals"]
    assert rec["verdict"] == "nyitott folyosókon kapják a gólokat"


def test_corridor_goals_flags_the_closed_wall():
    """A lövés útjában álló védő → zárt fal mögött is bekapják."""
    from handball.pipeline.defense import corridor_goals

    rec = corridor_goals(_crg_match(True))["away"]
    assert rec["open"] == 0
    assert rec["verdict"] == "zárt fal mögött is bekapják"


def test_corridor_goals_needs_enough_goals():
    """Kevés (5-nél kevesebb) kapott gólnál nincs ítélet."""
    from handball.pipeline.defense import corridor_goals

    rec = corridor_goals(_crg_match(False, n_goals=3))["away"]
    assert rec["verdict"] is None


# ---- Bontó tempó (a járatás szedi-e szét a védekezést) ----------------------

def _ctm_match(with_passes, n_goals=5, fps=25.0):
    """Hazai gól-sorozat: a gól előtt négyszeri gyors átadás (vagy
    csak a lövő birtoklása) — a bontó tempó így mérhető."""
    frames = []
    t = 0
    spots = [(28.0, 6.0), (28.0, 14.0), (32.0, 6.0), (32.0, 14.0)]

    def _emit(bx, by, n):
        nonlocal t
        for _ in range(n):
            players = [_pl(k + 1, Team.HOME, x, y)
                       for k, (x, y) in enumerate(spots)]
            players.append(_pl(9, Team.HOME, 33.0, 10.0))
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=bx, y=by, confidence=1.0)))
            t += 1

    for _ in range(n_goals):
        if with_passes:
            for (x, y) in spots:        # gyors körbejáratás
                _emit(x, y, 6)
        _emit(33.0, 10.0, 10)           # a lövőnél (9-es) a labda
        for i in range(8):              # gól a +x kapura
            _emit(min(33.0 + (i + 1), 40.5), 10.0, 1)
        for _ in range(40):             # szünet a gólok közt
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1
    return Match(_meta(fps), frames)


def test_conceded_tempo_flags_the_circulation_victim():
    """Gyors járatás után esett gólok → a járatás szedi szét őket."""
    from handball.pipeline.defense import conceded_tempo

    rec = conceded_tempo(_ctm_match(True))["away"]
    assert rec["goals"] >= 5
    assert rec["verdict"] == "a járatás szedi szét őket"


def test_conceded_tempo_flags_the_duel_victim():
    """Járatás nélküli gólok → egyéni akciókból kapják."""
    from handball.pipeline.defense import conceded_tempo

    rec = conceded_tempo(_ctm_match(False))["away"]
    assert rec["verdict"] == "egyéni akciókból kapják a gólokat"


def test_conceded_tempo_needs_enough_goals():
    """Kevés (5-nél kevesebb) kapott gólnál nincs ítélet."""
    from handball.pipeline.defense import conceded_tempo

    rec = conceded_tempo(_ctm_match(True, n_goals=3))["away"]
    assert rec["verdict"] is None
