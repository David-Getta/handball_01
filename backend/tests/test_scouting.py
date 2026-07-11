"""
Tesztek az ellenfél-felderítésre (scouting.py) — kézzel összerakott meccsekkel.

A pálya 40x20 m; a HAZAI a +x (x=40) kapu felé támad, saját kapuja x=0.

Futtatás:
    python tests/test_scouting.py
"""

from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, Ball, Team, PositionSource,
)
from handball.pipeline.scouting import (
    scout_team, combine_reports, ScoutingReport, _shot_zone, trend_report,
)


def _pl(track_id, team, x, y):
    return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0)


def _meta(fps=25.0):
    return MatchMeta(match_id="s", home_team="Veszprém", away_team="Szeged", fps=fps,
                     frame_width=1920, frame_height=1080)


def _attack_60(n=30):
    """HAZAI szervezett támadás a +x térfélen, AWAY 6-0 fallal a x=40 kapunál."""
    frames = []
    for t in range(n):
        players = [_pl(1, Team.HOME, 28.0, 10.0), _pl(2, Team.HOME, 30.0, 5.0),
                   _pl(3, Team.HOME, 30.0, 15.0)]
        for j, y in enumerate([2, 6, 8, 12, 14, 18]):
            players.append(_pl(20 + j, Team.AWAY, 35.0, float(y)))
        frames.append(Frame(t=t, players=players, ball=Ball(x=28.0, y=10.0, confidence=1.0)))
    return Match(_meta(), frames)


def test_defense_distribution_detects_60():
    """A védekező (AWAY) csapat felderítve: leggyakoribb forma 6-0."""
    rep = scout_team(_attack_60(), Team.AWAY)
    assert rep.defense_main == "6-0"
    assert rep.defense_distribution.get("6-0", 0) > 0


def test_attack_share_for_attacking_team():
    """A támadó (HOME) csapatnál magas a szervezett-támadás arány."""
    rep = scout_team(_attack_60(), Team.HOME)
    assert rep.attack_share_pct > 50.0


def test_keys_to_game_mention_60():
    """A 6-0 fal ellen konkrét edzői kulcsot ad."""
    rep = scout_team(_attack_60(), Team.AWAY)
    assert any("6-0" in k for k in rep.keys_to_game)


def test_shot_and_goal_counting():
    """Lövés/gól számolás és hatékonyság a felderített csapatra."""
    # HAZAI gyorsan a x=40 kapu felé lő (gól), majd a labda a kapuvonalra ér.
    frames = []
    xs = [30, 33, 36, 39, 40.0]  # gyorsan a kapu felé
    for t, x in enumerate(xs):
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, x - 1, 10.0)],
                            ball=Ball(x=float(x), y=10.0, confidence=1.0)))
    m = Match(_meta(), frames)
    rep = scout_team(m, Team.HOME)
    assert rep.shots >= 1
    assert 0.0 <= rep.shot_efficiency_pct <= 100.0


def test_key_players_ranked_by_possession():
    """A legtöbbet birtokló játékos kerül előre a kulcsjátékosok közé."""
    rep = scout_team(_attack_60(), Team.HOME)
    assert len(rep.key_players) >= 1
    # az 1-es (a labdás) birtoklás-ideje a legnagyobb
    assert rep.key_players[0]["track_id"] == 1
    assert rep.key_players[0]["possession_frames"] > 0


def test_combine_reports_aggregates():
    """Több meccs egyesítése: matches nő, forma marad, számok összeadódnak."""
    r1 = scout_team(_attack_60(), Team.AWAY)
    r2 = scout_team(_attack_60(), Team.AWAY)
    comb = combine_reports([r1, r2])
    assert comb.matches == 2
    assert comb.defense_main == "6-0"
    assert comb.num_figures == r1.num_figures + r2.num_figures


def test_shot_zone_labels():
    """A zóna-címkék helyesek, a bal/jobb a támadás irányához igazodik."""
    assert _shot_zone(34.0, 2.0, 40.0) == "balszél"
    assert _shot_zone(34.0, 18.0, 40.0) == "jobbszél"
    assert _shot_zone(34.0, 10.0, 40.0) == "beálló (6 m)"
    assert _shot_zone(30.0, 10.0, 40.0) == "átlövés közép"
    assert _shot_zone(30.0, 3.0, 40.0) == "átlövés bal"
    # a -x kapura támadva a bal/jobb tükröződik
    assert _shot_zone(6.0, 2.0, 0.0) == "jobbszél"
    assert _shot_zone(10.0, 17.0, 0.0) == "átlövés bal"


def test_shot_zones_in_report():
    """A jelentésben megjelennek a lövési zónák (a szintetikus gól zónájával)."""
    frames = []
    xs = [30, 33, 36, 39, 40.0]  # gyors lövés a +x kapura, középről
    for t, x in enumerate(xs):
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, x - 1, 10.0)],
                            ball=Ball(x=float(x), y=10.0, confidence=1.0)))
    rep = scout_team(Match(_meta(), frames), Team.HOME)
    assert rep.shot_zones, "legalább egy zóna kell"
    zone = next(iter(rep.shot_zones))
    assert zone in ("átlövés közép", "beálló (6 m)")
    assert rep.shot_zones[zone]["shots"] >= 1


def test_combine_merges_shot_zones():
    """Az összevonás zónánként összegzi a lövéseket/gólokat."""
    frames = []
    xs = [30, 33, 36, 39, 40.0]
    for t, x in enumerate(xs):
        frames.append(Frame(t=t, players=[_pl(1, Team.HOME, x - 1, 10.0)],
                            ball=Ball(x=float(x), y=10.0, confidence=1.0)))
    r1 = scout_team(Match(_meta(), frames), Team.HOME)
    comb = combine_reports([r1, r1])
    zone = next(iter(r1.shot_zones))
    assert comb.shot_zones[zone]["shots"] == 2 * r1.shot_zones[zone]["shots"]


def test_combine_single_returns_same():
    """Egyetlen jelentés egyesítése önmagát adja."""
    r1 = scout_team(_attack_60(), Team.AWAY)
    assert combine_reports([r1]) is r1


def _rep_for_trend(**kw):
    base = dict(team="home", team_name="Mi", matches=2,
                attack_share_pct=50.0, fast_break_pct=10.0,
                avg_attack_duration_s=8.0, shot_efficiency_pct=40.0,
                shots=20, goals=8, turnovers=8)
    base.update(kw)
    return ScoutingReport(**base)


def test_trend_per_match_normalization():
    """A darabszámok meccsenkénti átlagra normálódnak (2 meccs / 20 lövés = 10)."""
    r = trend_report(_rep_for_trend(matches=2, shots=20),
                     _rep_for_trend(matches=4, shots=48))
    shots = next(m for m in r["metrics"] if m["metric"] == "shots")
    assert shots["older"] == 10.0 and shots["newer"] == 12.0
    assert shots["better"] is True


def test_trend_better_and_worse_flags():
    """A gólarány-növekedés javulás; a labdaeladás-növekedés romlás."""
    r = trend_report(_rep_for_trend(shot_efficiency_pct=40.0, turnovers=8),
                     _rep_for_trend(shot_efficiency_pct=55.0, turnovers=12))
    eff = next(m for m in r["metrics"] if m["metric"] == "shot_efficiency_pct")
    to = next(m for m in r["metrics"] if m["metric"] == "turnovers")
    assert eff["better"] is True
    assert to["better"] is False
    assert any(s.startswith("Javult") for s in r["summary"])
    assert any(s.startswith("Romlott") for s in r["summary"])


def test_trend_neutral_metric_not_judged():
    """A semleges irányú mutatót (támadáshossz) nem minősítjük."""
    r = trend_report(_rep_for_trend(avg_attack_duration_s=6.0),
                     _rep_for_trend(avg_attack_duration_s=12.0))
    dur = next(m for m in r["metrics"] if m["metric"] == "avg_attack_duration_s")
    assert dur["better"] is None
    assert not any("támadáshossz" in s.lower() for s in r["summary"])


def test_trend_no_change_summary():
    """Változatlan időszakok: "nincs jelentős változás" összegzés."""
    r = trend_report(_rep_for_trend(), _rep_for_trend())
    assert r["summary"] == ["Nincs jelentős változás a két időszak között."]


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
