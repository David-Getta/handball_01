"""
Tesztek a sprint-elemzésre / terhelés-monitorra (stats.py).

Futtatás:
    python tests/test_sprint_stats.py
"""

from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.stats import compute_player_stats


def _match(positions, fps=25.0):
    """Egyetlen játékos adott (x, y) pozíciósorából épít meccset (t=0,1,2...)."""
    frames = [
        Frame(t=i, players=[
            PlayerPosition(track_id=1, team=Team.HOME, x=float(x), y=float(y)),
        ])
        for i, (x, y) in enumerate(positions)
    ]
    return Match(
        meta=MatchMeta(match_id="t", home_team="H", away_team="A", fps=fps),
        frames=frames)


def test_sprint_detected_and_counted():
    """Tartósan gyors mozgás = 1 sprint; a csúcssebesség reális marad."""
    # 25 fps: 0,28 m/kocka = 7 m/s — 30 kockán át (1,2 mp) sprintel,
    # előtte-utána áll (0 m/s).
    pos = [(0.0, 5.0)] * 10
    x = 0.0
    for _ in range(30):
        x += 0.28
        pos.append((x, 5.0))
    pos += [(x, 5.0)] * 10
    stats = compute_player_stats(_match(pos))[1]
    assert stats.sprint_count == 1, f"1 sprintet vartunk, lett: {stats.sprint_count}"
    assert 6.0 <= stats.top_speed_ms <= 7.5, f"csucssebesseg: {stats.top_speed_ms}"
    assert stats.sprint_distance_m > 5.0
    assert stats.zone_seconds["sprint"] > 0.8
    print("OK: sprint felismerve, csucssebesseg realis")


def test_short_burst_is_not_a_sprint():
    """Egy-két kockányi gyors mozgás (zaj) nem számít sprintnek."""
    # 3 kockányi (0,12 mp) gyors mozgás — a minimum 0,5 mp alatt van.
    pos = [(0.0, 5.0)] * 10
    x = 0.0
    for _ in range(3):
        x += 0.28
        pos.append((x, 5.0))
    pos += [(x, 5.0)] * 10
    stats = compute_player_stats(_match(pos))[1]
    assert stats.sprint_count == 0, f"0 sprintet vartunk, lett: {stats.sprint_count}"
    print("OK: rovid loketeket nem szamoljuk sprintnek")


def test_tracking_glitch_ignored():
    """Egyetlen óriási ugrás (követési hiba) nem ad fals csúcssebességet."""
    # Álló játékos, egy kockára 8 métert "ugrik" (200 m/s) — hibás mérés.
    pos = [(10.0, 5.0)] * 10 + [(18.0, 5.0)] + [(10.0, 5.0)] * 10
    stats = compute_player_stats(_match(pos))[1]
    assert stats.top_speed_ms < 5.0, f"a glitch beszamitodott: {stats.top_speed_ms}"
    assert stats.sprint_count == 0
    print("OK: koveteshiba kiszurve")


def test_zones_sum_to_moving_time():
    """A zóna-idők összege a mozgással lefedett időt adja ki (kb.)."""
    # 100 kocka egyenletes kocogás: 0,08 m/kocka = 2 m/s.
    pos = [(i * 0.08, 5.0) for i in range(100)]
    stats = compute_player_stats(_match(pos))[1]
    total = sum(stats.zone_seconds.values())
    # 99 szakasz x 0,04 mp = 3,96 mp
    assert abs(total - 3.96) < 0.1, f"zonaido-osszeg: {total}"
    assert stats.zone_seconds["kocogas"] > 3.5
    print("OK: zonaidok konzisztensek")


def test_estimated_positions_do_not_sprint():
    """A BECSÜLT pozíciók nem szólnak bele a sprint-statisztikába."""
    frames = []
    x = 0.0
    for i in range(40):
        x += 0.30  # gyors "mozgás", de becsült forrásból
        frames.append(Frame(t=i, players=[
            PlayerPosition(track_id=1, team=Team.HOME, x=x, y=5.0,
                           source=PositionSource.ESTIMATED),
        ]))
    m = Match(meta=MatchMeta(match_id="t", home_team="H", away_team="A",
                             fps=25.0), frames=frames)
    stats = compute_player_stats(m)[1]
    assert stats.sprint_count == 0 and stats.top_speed_ms == 0.0
    print("OK: becsult mozgas nem sprint")


if __name__ == "__main__":
    test_sprint_detected_and_counted()
    test_short_burst_is_not_a_sprint()
    test_tracking_glitch_ignored()
    test_zones_sum_to_moving_time()
    test_estimated_positions_do_not_sprint()
    print("Minden sprint-statisztika teszt OK.")


def test_aggregate_by_jersey_merges_broken_tracks():
    """Azonos (csapat, mezszám) trackek egy játékossá olvadnak össze."""
    from handball.pipeline.stats import PlayerStats, aggregate_by_jersey
    stats = {
        1: PlayerStats(track_id=1, distance_m=100.0, top_speed_ms=6.0,
                       sprint_count=2, sprint_distance_m=20.0,
                       measured_frames=250,
                       zone_seconds={"seta": 5.0, "futas": 3.0}),
        2: PlayerStats(track_id=2, distance_m=50.0, top_speed_ms=7.5,
                       sprint_count=1, sprint_distance_m=10.0,
                       measured_frames=250,
                       zone_seconds={"seta": 2.0, "sprint": 1.0}),
        3: PlayerStats(track_id=3, distance_m=80.0, top_speed_ms=5.0,
                       measured_frames=100),
    }
    team_of = {1: "home", 2: "home", 3: "away"}
    jersey_of = {1: 23, 2: 23}  # a 3-asnak nincs száma — külön sor marad
    rows = aggregate_by_jersey(stats, team_of, jersey_of, fps=25.0)
    assert len(rows) == 2
    merged = next(r for r in rows if r["jersey"] == 23)
    assert merged["track_ids"] == [1, 2]
    assert merged["distance_m"] == 150.0
    assert merged["top_speed_ms"] == 7.5  # maximum, nem összeg
    assert merged["sprint_count"] == 3
    # Átlagsebesség az összevont adatból: 150 m / (500 kocka / 25 fps) = 7.5.
    assert abs(merged["avg_speed_ms"] - 7.5) < 0.01
    assert merged["zone_seconds"]["seta"] == 7.0
    solo = next(r for r in rows if r["jersey"] is None)
    assert solo["label"] == "id 3" and solo["distance_m"] == 80.0


def test_aggregate_same_jersey_different_teams_stay_separate():
    """A 23-as hazai és a 23-as vendég NEM ugyanaz a játékos."""
    from handball.pipeline.stats import PlayerStats, aggregate_by_jersey
    stats = {
        1: PlayerStats(track_id=1, distance_m=10.0, measured_frames=25),
        2: PlayerStats(track_id=2, distance_m=20.0, measured_frames=25),
    }
    rows = aggregate_by_jersey(stats, {1: "home", 2: "away"},
                               {1: 23, 2: 23}, fps=25.0)
    assert len(rows) == 2


def test_rotation_depth_counts_used_and_regulars():
    """A rotáció-mélység a jelenlét-arányból számol: a végig pályán
    lévő alapember, a fél-időt játszó bevetett, a beugró (10% alatt)
    és a kapus nem számít."""
    from handball.pipeline.stats import rotation_depth

    total = 200
    frames = []
    for t in range(total):
        players = [
            PlayerPosition(track_id=1, team=Team.HOME, x=20.0, y=5.0),
            PlayerPosition(track_id=99, team=Team.HOME, x=1.0, y=10.0,
                           role="kapus"),
        ]
        if t < 60:  # a 2-es a meccs 30%-án van a pályán → bevetett
            players.append(PlayerPosition(track_id=2, team=Team.HOME,
                                          x=22.0, y=8.0))
        if t < 10:  # a 3-as csak beugró (5%) → nem számít
            players.append(PlayerPosition(track_id=3, team=Team.HOME,
                                          x=24.0, y=12.0))
        frames.append(Frame(t=t, players=players))
    m = Match(meta=MatchMeta(match_id="r", home_team="H",
                             away_team="A", fps=25.0), frames=frames)
    rec = rotation_depth(m)["home"]
    assert rec["used"] == 2          # 1-es + 2-es (kapus és beugró nem)
    assert rec["regulars"] == 1      # csak az 1-es alapember
    labels = [p["label"] for p in rec["players"]]
    assert len(labels) == 2
    assert rec["players"][0]["share_pct"] == 100.0


def test_rotation_depth_on_sliced_match_first_half_picture():
    """A rész-meccsre (első félidő) számolt rotáció a félidei állapotot
    adja: a csak a 2. félidőben beálló játékos nem szivárog vissza."""
    from handball.pipeline.stats import rotation_depth

    total = 200
    frames = []
    for t in range(total):
        players = [
            PlayerPosition(track_id=1, team=Team.HOME, x=20.0, y=5.0)]
        if t >= 100:  # a 2-es csak a "második félidőben" áll be
            players.append(PlayerPosition(track_id=2, team=Team.HOME,
                                          x=22.0, y=8.0))
        frames.append(Frame(t=t, players=players))
    m = Match(meta=MatchMeta(match_id="rf", home_team="H",
                             away_team="A", fps=25.0), frames=frames)
    sub = Match(meta=m.meta, frames=[f for f in m.frames if f.t < 100])
    fh = rotation_depth(sub)["home"]
    assert fh["used"] == 1           # az első félidőben csak az 1-es
    full = rotation_depth(m)["home"]
    assert full["used"] == 2         # a teljes képben már ketten


def test_player_plus_minus_ranks_on_court_goal_difference():
    """Az 1-es hazai játékos két hazai gólnál van a pályán, a 2-es két
    kapott gólnál → az 1-es a legjobb, a 2-es a legrosszabb mérlegű;
    kevés játékidőnél nincs megnevezett játékos."""
    from handball.models.tracking import Ball
    from handball.pipeline.stats import player_plus_minus

    def _pl(track_id, team, x, y):
        return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                              source=PositionSource.MEASURED,
                              confidence=1.0)

    frames = []
    t = 0

    def _play(pid, seconds):
        """`seconds` mp játék: a pid-es hazai játékos a pályán."""
        nonlocal t, frames
        for _ in range(int(seconds * 25)):
            frames.append(Frame(t=t, players=[_pl(pid, Team.HOME,
                                                  20.0, 10.0)],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    def _goal(pid, home_goal):
        """Gól a +x (hazai) vagy a -x (vendég) kapura, a pid-essel a
        pályán."""
        nonlocal t, frames
        for i in range(8):
            bx = (min(33.6 + i, 40.0) if home_goal
                  else max(6.4 - i, 0.0))
            frames.append(Frame(t=t, players=[_pl(pid, Team.HOME,
                                                  20.0, 10.0)],
                                ball=Ball(x=bx, y=10.0,
                                          confidence=1.0)))
            t += 1

    # Az 1-es 6 percet játszik két hazai góllal, a 2-es 6 percet két
    # kapott góllal.
    for _ in range(2):
        _play(1, 180)
        _goal(1, home_goal=True)
    for _ in range(2):
        _play(2, 180)
        _goal(2, home_goal=False)

    pm = player_plus_minus(Match(
        meta=MatchMeta(match_id="pm", home_team="H", away_team="A",
                       fps=25.0), frames=frames))
    h = pm["home"]
    one = next(p for p in h["players"] if p["player_id"] == 1)
    two = next(p for p in h["players"] if p["player_id"] == 2)
    assert one["for"] == 2 and one["against"] == 0
    assert two["for"] == 0 and two["against"] == 2
    assert one["diff_per_min"] > two["diff_per_min"]
    assert h["best"]["player_id"] == 1
    assert h["worst"]["player_id"] == 2

    # Rövid részlet: nincs elég játékidő → nincs megnevezett játékos.
    few = player_plus_minus(Match(
        meta=MatchMeta(match_id="pm", home_team="H", away_team="A",
                       fps=25.0), frames=frames[:500]))
    assert few["home"]["best"] is None and few["home"]["worst"] is None


def test_pair_plus_minus_ranks_partnerships():
    """Az 1-2 páros két hazai gólnál van együtt a pályán, az 1-3 páros
    két kapott gólnál → az 1-2 a legjobb, az 1-3 a legrosszabb
    mérlegű; rövid részletnél nincs megnevezett páros."""
    from handball.models.tracking import Ball
    from handball.pipeline.stats import pair_plus_minus

    def _pl(track_id, x):
        return PlayerPosition(track_id=track_id, team=Team.HOME, x=x,
                              y=10.0, source=PositionSource.MEASURED,
                              confidence=1.0)

    frames = []
    t = 0

    def _play(partner, seconds):
        """`seconds` mp játék: az 1-es és a partnere a pályán."""
        nonlocal t, frames
        for _ in range(int(seconds * 25)):
            frames.append(Frame(t=t,
                                players=[_pl(1, 20.0), _pl(partner, 22.0)],
                                ball=Ball(x=20.0, y=10.0,
                                          confidence=1.0)))
            t += 1

    def _goal(partner, home_goal):
        """Gól a +x (hazai) vagy a -x (vendég) kapura, a párossal a
        pályán."""
        nonlocal t, frames
        for i in range(8):
            bx = (min(33.6 + i, 40.0) if home_goal
                  else max(6.4 - i, 0.0))
            frames.append(Frame(t=t,
                                players=[_pl(1, 20.0), _pl(partner, 22.0)],
                                ball=Ball(x=bx, y=10.0, confidence=1.0)))
            t += 1

    for _ in range(2):
        _play(2, 150)
        _goal(2, home_goal=True)
    for _ in range(2):
        _play(3, 150)
        _goal(3, home_goal=False)

    prm = pair_plus_minus(Match(
        meta=MatchMeta(match_id="pr", home_team="H", away_team="A",
                       fps=25.0), frames=frames))
    h = prm["home"]
    good = next(p for p in h["pairs"] if p["players"] == [1, 2])
    bad = next(p for p in h["pairs"] if p["players"] == [1, 3])
    assert good["for"] == 2 and good["against"] == 0
    assert bad["for"] == 0 and bad["against"] == 2
    assert good["diff_per_min"] > bad["diff_per_min"]
    assert h["best"]["players"] == [1, 2]
    assert h["worst"]["players"] == [1, 3]
    # A vendégnek nincs játékosa → nincs páros.
    assert prm["away"]["pairs"] == []

    # Rövid részlet: nincs elég közös idő → nincs megnevezett páros.
    few = pair_plus_minus(Match(
        meta=MatchMeta(match_id="pr", home_team="H", away_team="A",
                       fps=25.0), frames=frames[:400]))
    assert few["home"]["best"] is None and few["home"]["worst"] is None


# ---- Sprint-veszély (ki viszi a kontrát) -----------------------------------

def _sprint_threat_match(sprints_by_player, fps=25.0):
    """Vendég játékosok adott számú sprintet futnak (0,28 m/kocka, 30
    kockán át), köztük állnak; a hazai 1-es végig áll."""
    max_sprints = max(sprints_by_player.values())
    frames = []
    t = 0
    xs = {tid: 5.0 for tid in sprints_by_player}
    direction = {tid: 1.0 for tid in sprints_by_player}
    for k in range(max_sprints):
        for phase in ("run", "rest"):
            for i in range(30 if phase == "run" else 15):
                players = [PlayerPosition(track_id=1, team=Team.HOME,
                                          x=2.0, y=2.0)]
                for j, (tid, n) in enumerate(sprints_by_player.items()):
                    if phase == "run" and k < n:
                        xs[tid] += 0.28 * direction[tid]
                    players.append(PlayerPosition(
                        track_id=tid, team=Team.AWAY,
                        x=xs[tid], y=6.0 + 3.0 * j))
                frames.append(Frame(t=t, players=players))
                t += 1
        for tid in sprints_by_player:      # forduló a pálya széle előtt
            direction[tid] *= -1.0
    return Match(
        meta=MatchMeta(match_id="t", home_team="H", away_team="A", fps=fps),
        frames=frames)


def test_sprint_threats_finds_the_break_runner():
    """A 21-es nyolcszor sprintel a társak 2-2 sprintje mellett → ő a
    kijelölt kontra-ember."""
    from handball.pipeline.stats import sprint_threats

    rec = sprint_threats(_sprint_threat_match(
        {21: 8, 22: 2, 23: 2}))["away"]
    assert rec["team_sprints"] == 12
    assert rec["top"] is not None and rec["top"]["player_id"] == 21
    assert rec["verdict"] == "kijelölt kontra-emberük van"


def test_sprint_threats_even_load_has_no_verdict():
    """Egyenletes sprint-teher mellett nincs kiemelt kontra-ember."""
    from handball.pipeline.stats import sprint_threats

    rec = sprint_threats(_sprint_threat_match(
        {21: 4, 22: 4, 23: 4, 24: 4}))["away"]
    assert rec["team_sprints"] == 16 and rec["top"] is None
    assert rec["verdict"] is None


def test_sprint_threats_needs_enough_sprints():
    """Kevés (10-nél kevesebb) csapat-sprintnél nincs ítélet."""
    from handball.pipeline.stats import sprint_threats

    rec = sprint_threats(_sprint_threat_match({21: 4, 22: 1}))["away"]
    assert rec["team_sprints"] == 5 and rec["verdict"] is None


# ---- Futás-mérleg (melyik csapat futja túl a másikat) -----------------------

def _distance_battle_match(home_step, away_step, minutes=12.0, fps=5.0):
    """A hazai és a vendég mezőnyjátékosok kockánként adott métert
    lépnek (ide-oda ingázva); 12 percnyi felvétel."""
    n = int(minutes * 60 * fps)
    frames = []
    hx, ax = 10.0, 30.0
    hdir, adir = 1.0, 1.0
    for t in range(n):
        hx += home_step * hdir
        ax += away_step * adir
        if not 5.0 <= hx <= 18.0:
            hdir *= -1.0
            hx += 2 * home_step * hdir
        if not 22.0 <= ax <= 35.0:
            adir *= -1.0
            ax += 2 * away_step * adir
        frames.append(Frame(t=t, players=[
            PlayerPosition(track_id=1, team=Team.HOME, x=hx, y=8.0),
            PlayerPosition(track_id=2, team=Team.HOME, x=hx, y=12.0),
            PlayerPosition(track_id=21, team=Team.AWAY, x=ax, y=8.0),
            PlayerPosition(track_id=22, team=Team.AWAY, x=ax, y=12.0),
        ]))
    return Match(
        meta=MatchMeta(match_id="d", home_team="H", away_team="A", fps=fps),
        frames=frames)


def test_distance_battle_flags_the_running_team():
    """A hazaiak kétszer annyit mozognak → túlfutják az ellenfelüket,
    a vendégeket túlfutja az ellenfél."""
    from handball.pipeline.stats import distance_battle

    res = distance_battle(_distance_battle_match(0.2, 0.1))
    assert res["home"]["verdict"] == "túlfutják az ellenfelüket"
    assert res["away"]["verdict"] == "túlfutja őket az ellenfél"
    assert res["home"]["distance_m"] > res["away"]["distance_m"]


def test_distance_battle_even_match_has_no_verdict():
    """Közel azonos futásmennyiségnél nincs ítélet."""
    from handball.pipeline.stats import distance_battle

    res = distance_battle(_distance_battle_match(0.2, 0.195))
    assert res["home"]["verdict"] is None
    assert res["away"]["verdict"] is None


def test_distance_battle_needs_enough_minutes():
    """Rövid (10 percnél kevesebb) felvételen nincs ítélet."""
    from handball.pipeline.stats import distance_battle

    res = distance_battle(_distance_battle_match(0.2, 0.1, minutes=5.0))
    assert res["home"]["verdict"] is None


def test_sprints_by_score_flags_panic_running():
    """Döntetlennél kocogás, 3 kapott gól után sprint-sorozat →
    hátrányban sprintbe menekülnek."""
    from handball.models.tracking import Ball
    from handball.pipeline.stats import sprints_by_score

    frames = []
    t = 0

    def jog(seconds, speed_per_frame):
        nonlocal t, frames
        x, direction = 15.0, 1
        for _ in range(int(seconds * 25)):
            x += direction * speed_per_frame
            if x > 25.0 or x < 10.0:
                direction *= -1
                x += 2 * direction * speed_per_frame
            frames.append(Frame(t=t, players=[
                PlayerPosition(track_id=5, team=Team.HOME, x=x, y=5.0),
            ], ball=Ball(x=20.0, y=10.0, confidence=1.0)))
            t += 1

    def bursts(n):
        nonlocal t, frames
        x, direction = 15.0, 1
        for _ in range(n):
            for _ in range(20):     # 0,8 mp 6 m/s-mal: sprint
                x += direction * 0.24
                frames.append(Frame(t=t, players=[
                    PlayerPosition(track_id=5, team=Team.HOME,
                                   x=x, y=5.0),
                ], ball=Ball(x=20.0, y=10.0, confidence=1.0)))
                t += 1
            for _ in range(30):     # megállás
                frames.append(Frame(t=t, players=[
                    PlayerPosition(track_id=5, team=Team.HOME,
                                   x=x, y=5.0),
                ], ball=Ball(x=20.0, y=10.0, confidence=1.0)))
                t += 1
            direction *= -1

    def away_goal():
        nonlocal t, frames
        for _ in range(30):
            frames.append(Frame(t=t, players=[
                PlayerPosition(track_id=9, team=Team.AWAY, x=10.0, y=10.0),
            ], ball=Ball(x=10.0, y=10.0, confidence=1.0)))
            t += 1
        x = 10.0
        while x > -0.5:
            x -= 0.5
            frames.append(Frame(t=t, players=[
                PlayerPosition(track_id=9, team=Team.AWAY, x=10.0, y=10.0),
            ], ball=Ball(x=max(x, -0.5), y=10.0, confidence=1.0)))
            t += 1
        for _ in range(40):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
            t += 1

    jog(90, 0.08)          # döntetlen: 2 m/s, nincs sprint
    for _ in range(3):
        away_goal()
    bursts(45)             # hátrányban: 45 sprint-löket

    m = Match(meta=MatchMeta(match_id="spb", home_team="H",
                             away_team="A", fps=25.0), frames=frames)
    spb = sprints_by_score(m)
    h = spb["home"]
    assert h["level"]["seconds"] >= 60.0
    assert h["level"]["sprints"] == 0
    assert h["trailing"]["seconds"] >= 60.0
    assert h["trailing"]["sprints"] >= 40
    assert h["verdict"] == "hátrányban sprintbe menekülnek"
    assert spb["away"]["verdict"] is None


def test_sprints_by_score_needs_state_time():
    """Hátrány (kapott gól) nélkül nincs ítélet."""
    from handball.models.tracking import Ball
    from handball.pipeline.stats import sprints_by_score

    frames = []
    x = 10.0
    for t in range(int(90 * 25)):
        x += 0.24 if (t // 20) % 3 == 0 and x < 30 else 0.0
        frames.append(Frame(t=t, players=[
            PlayerPosition(track_id=5, team=Team.HOME, x=x, y=5.0),
        ], ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    m = Match(meta=MatchMeta(match_id="spb2", home_team="H",
                             away_team="A", fps=25.0), frames=frames)
    spb = sprints_by_score(m)
    assert spb["home"]["trailing"]["seconds"] == 0.0
    assert spb["home"]["verdict"] is None


# ---- Sprint-poszt (melyik posztjuk futja a sprinteket) ---------------------


def _spr_match(sprints_by_player, fps=25.0):
    """Vendég poszt-minta (21: beálló, 22: szélső a -x kapunál), majd
    a megadott számú sprint (0,28 m/kocka, 30 kockán át)."""
    from handball.models.tracking import Ball

    spos = {21: (6.0, 10.0), 22: (5.0, 3.0)}

    def base_cast():
        return [PlayerPosition(track_id=tid, team=Team.AWAY, x=x,
                               y=y, source=PositionSource.MEASURED,
                               confidence=1.0)
                for tid, (x, y) in spos.items()]

    frames = []
    t = 0
    for _ in range(150):             # poszt-minta: vendég birtoklás elöl
        frames.append(Frame(t=t, players=base_cast(),
                            ball=Ball(x=6.2, y=10.0, confidence=1.0)))
        t += 1
    max_sprints = max(sprints_by_player.values())
    xs = {tid: 12.0 for tid in sprints_by_player}
    direction = {tid: 1.0 for tid in sprints_by_player}
    for k in range(max_sprints):
        for phase in ("run", "rest"):
            for _ in range(30 if phase == "run" else 15):
                players = []
                for j, (tid, n) in enumerate(
                        sprints_by_player.items()):
                    if phase == "run" and k < n:
                        xs[tid] += 0.28 * direction[tid]
                    players.append(PlayerPosition(
                        track_id=tid, team=Team.AWAY, x=xs[tid],
                        y=6.0 + 3.0 * j,
                        source=PositionSource.MEASURED,
                        confidence=1.0))
                frames.append(Frame(t=t, players=players))
                t += 1
        for tid in sprints_by_player:    # forduló a pálya széle előtt
            direction[tid] *= -1.0
    return Match(
        meta=MatchMeta(match_id="t", home_team="H", away_team="A",
                       fps=fps),
        frames=frames)


def test_sprint_threat_roles_names_the_running_post():
    """Tizenkét sprintből kilencet a beálló fut → az ő útját kell
    lezárni labdavesztésnél."""
    from handball.pipeline.stats import (SPR_MIN_SPRINTS,
                                         sprint_threat_roles)

    rec = sprint_threat_roles(_spr_match({21: 9, 22: 3}))["away"]
    assert rec["sprints"] >= SPR_MIN_SPRINTS, rec
    assert rec["main_role"] == "beálló", rec
    assert rec["share_pct"] and rec["share_pct"] >= 60.0, rec
    assert rec["verdict"] and "útját kell először lezárni" \
        in rec["verdict"], rec


def test_sprint_threat_roles_silent_with_few_sprints():
    """Kevés sprintből nincs ítélet."""
    from handball.pipeline.stats import sprint_threat_roles

    rec = sprint_threat_roles(_spr_match({21: 4, 22: 2}))["away"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec


# ---- Fáradó-poszt (melyik posztjuk esik vissza a 2. félidőre) --------------


def _ftr_match(v7_first, v7_second, fps=25.0):
    """Poszt-minta (7: beálló, 9: szélső), majd mozgás-szakaszok: a
    7-es az 1. félidőben v7_first, a 2.-ban v7_second m/s-mal
    ingázik a helye körül, a 9-es végig 2 m/s-mal; köztük 90 mp-es
    üres (szünet-) szakasz."""
    from handball.models.tracking import Ball

    spos = {7: (6.0, 10.0), 9: (5.0, 3.0)}

    def _p(tid, x, y):
        return PlayerPosition(track_id=tid, team=Team.AWAY, x=x, y=y,
                              source=PositionSource.MEASURED,
                              confidence=1.0)

    frames = []
    t = 0
    for _ in range(150):             # poszt-minta: vendég birtoklás
        frames.append(Frame(
            t=t,
            players=[_p(tid, *xy) for tid, xy in spos.items()],
            ball=Ball(x=6.2, y=10.0, confidence=1.0)))
        t += 1
    x7, d7 = spos[7][0], 1.0
    x9, d9 = spos[9][0], 1.0

    def _osc(x, d, v):
        x += d * v / fps
        if x >= 8.0:
            d = -1.0
        elif x <= 4.0:
            d = 1.0
        return x, d

    for phase, v7 in (("fh", v7_first), ("sh", v7_second)):
        for _ in range(int(40 * fps)):   # 40 mp mért mozgás
            x7, d7 = _osc(x7, d7, v7)
            x9, d9 = _osc(x9, d9, 2.0)
            frames.append(Frame(t=t, players=[
                _p(7, x7, spos[7][1]), _p(9, x9, spos[9][1])]))
            t += 1
        if phase == "fh":
            for _ in range(int(90 * fps)):   # félidei szünet
                frames.append(Frame(t=t, players=[], ball=None))
                t += 1
    return Match(
        meta=MatchMeta(match_id="t", home_team="H", away_team="A",
                       fps=fps),
        frames=frames)


def test_fatigue_roles_names_the_fading_post():
    """A beálló tempója a 2. félidőre harmadára esik → a szünet után
    az ő sávjában kell támadni."""
    from handball.pipeline.stats import FTR_DROP_PCT, fatigue_roles

    rec = fatigue_roles(_ftr_match(3.0, 1.0))["away"]
    assert rec["main_role"] == "beálló", rec
    assert rec["drop_pct"] and rec["drop_pct"] >= FTR_DROP_PCT, rec
    assert rec["verdict"] and "friss embert" in rec["verdict"], rec


def test_fatigue_roles_silent_when_steady():
    """Egyenletes tempónál nincs ítélet."""
    from handball.pipeline.stats import fatigue_roles

    rec = fatigue_roles(_ftr_match(2.0, 2.0))["away"]
    assert rec["main_role"] is None and rec["verdict"] is None, rec
