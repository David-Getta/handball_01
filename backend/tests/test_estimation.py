"""
Tesztek a [F] képen kívüli becslőre (OffScreenEstimator).

Szintetikus pályák, nincs videó/külső csomag. Azt ellenőrizzük, hogy:
- a becslő a sebességgel helyesen extrapolál,
- a megbízhatóság az idővel csökken,
- a pozíciót a pálya határaira vágja,
- pontosan annyit becsül, amennyi hiányzik (a legutóbb látottakat preferálva).

Futtatás:
    python tests/test_estimation.py
"""

from __future__ import annotations

# A backend/ mappát a kereső-útvonalra tesszük, hogy a teszt bárhonnan fusson.
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, PositionSource, Team,
)
from handball.models.events import RosterTimeline, Suspension
from handball.pipeline.estimation import (
    OffScreenEstimator, CONFIDENCE_HALFLIFE_FRAMES, VELOCITY_FADE_FRAMES,
    augment_match_with_estimates, reapply_estimates,
)


def _home(track_id, x, y, conf=1.0):
    return PlayerPosition(track_id=track_id, team=Team.HOME, x=x, y=y, confidence=conf)


def _only_home(estimated):
    """Csak a HOME csapat becsült játékosai (az AWAY-t a default roster miatt
    hagyjuk figyelmen kívül — ott nincs jelölt, így úgysem keletkezik becslés)."""
    return [p for p in estimated if p.team == Team.HOME]


def test_extrapolates_along_velocity():
    """Egyenes vonalú mozgásból a következő frame-re előrevetít.

    A játékos (10,8)->(11,8): sebesség (1,0)/frame. t=2-n képen kívül → x≈12.
    """
    est = OffScreenEstimator(RosterTimeline())
    est.update_seen(0, [_home(1, 10.0, 8.0)])
    est.update_seen(1, [_home(1, 11.0, 8.0)])

    out = _only_home(est.estimate_missing(2, measured=[]))
    assert len(out) == 1
    p = out[0]
    assert p.track_id == 1
    assert p.source == PositionSource.ESTIMATED
    assert abs(p.x - 12.0) < 1e-9
    assert abs(p.y - 8.0) < 1e-9


def test_confidence_decays_over_time():
    """A becslés megbízhatósága a felezési idő szerint csökken.

    Az utolsó mért confidence 1.0; pontosan CONFIDENCE_HALFLIFE_FRAMES eltelt idő
    után ~0.5-re csökken.
    """
    est = OffScreenEstimator(RosterTimeline())
    est.update_seen(0, [_home(1, 10.0, 8.0, conf=1.0)])

    half_t = int(CONFIDENCE_HALFLIFE_FRAMES)  # ennyi frame múlva feleződik
    out = _only_home(est.estimate_missing(half_t, measured=[]))
    assert len(out) == 1
    assert abs(out[0].confidence - 0.5) < 0.02


def test_position_clamped_to_court():
    """A pálya széle felé mozgó játékos becslése a 40 m-es határon megáll."""
    est = OffScreenEstimator(RosterTimeline())
    est.update_seen(0, [_home(1, 38.0, 10.0)])
    est.update_seen(1, [_home(1, 39.0, 10.0)])  # sebesség (1,0)/frame, a határ felé

    # Sok idő múlva: nyersen 39 + 1*eff messze túllógna, de a pályán belül marad.
    out = _only_home(est.estimate_missing(100, measured=[]))
    assert len(out) == 1
    assert out[0].x <= 40.0 + 1e-9
    assert abs(out[0].x - 40.0) < 1e-9  # a határra vágva


def test_velocity_fade_caps_displacement():
    """A sebesség hatása legfeljebb VELOCITY_FADE_FRAMES-ig tart (utána megáll).

    Lassú, a pályán belül maradó mozgásnál az elmozdulás vel * FADE-nél nem nagyobb.
    """
    est = OffScreenEstimator(RosterTimeline())
    est.update_seen(0, [_home(1, 5.0, 10.0)])
    est.update_seen(1, [_home(1, 5.1, 10.0)])  # sebesség (0.1,0)/frame

    far_t = int(VELOCITY_FADE_FRAMES) + 100  # jóval a fade után
    out = _only_home(est.estimate_missing(far_t, measured=[]))
    # Utolsó pozíció x=5.1; max elmozdulás 0.1 * FADE.
    expected_max_x = 5.1 + 0.1 * VELOCITY_FADE_FRAMES
    assert out[0].x <= expected_max_x + 1e-9


def test_estimates_only_missing_count_and_prefers_recent():
    """Pontosan a hiányzó számú játékost becsli, a legutóbb látottat preferálva.

    6 hazai látszik (id 1..6), 3 korábbi hazai (id 7,8,9) képen kívül. Teljes
    létszám 7 → 1 hiányzik → 1 becslés, a legutóbb látott jelöltre (id 9).
    """
    est = OffScreenEstimator(RosterTimeline())
    # Korábbi, most már képen kívüli játékosok, eltérő utolsó látási idővel:
    est.update_seen(0, [_home(7, 1.0, 1.0), _home(8, 2.0, 2.0)])
    est.update_seen(1, [_home(9, 3.0, 3.0)])  # a 9-est láttuk a legutóbb

    measured = [_home(i, 10.0 + i, 10.0) for i in range(1, 7)]  # id 1..6 most látszik
    est.update_seen(5, measured)  # ahogy a pipeline is teszi: előbb update, majd estimate

    out = _only_home(est.estimate_missing(5, measured))
    assert len(out) == 1                 # 7 kell, 6 látszik → 1 becsült
    assert out[0].track_id == 9          # a legutóbb látott jelölt


def test_no_estimate_when_all_present():
    """Ha minden játékos látszik (vagy ki van állítva), nincs becslés.

    2 kiállítás → a hazai létszám 5; ha 5 hazai látszik, nincs mit becsülni.
    """
    roster = RosterTimeline(suspensions=[
        Suspension(team=Team.HOME, start_t=0, duration_t=100),
        Suspension(team=Team.HOME, start_t=0, duration_t=100),
    ])
    est = OffScreenEstimator(roster)
    measured = [_home(i, 10.0 + i, 10.0) for i in range(1, 6)]  # 5 hazai látszik
    est.update_seen(10, measured)

    out = _only_home(est.estimate_missing(10, measured))
    assert len(out) == 0


def test_augment_match_fills_disappeared_player():
    """A képből kikerült játékost a Match utólagos kiegészítése becsléssel pótolja.

    A 0-1. frame-en 5 hazai látszik (2 kiállítás → 5 kell), a 2. frame-től az
    5-ös eltűnik (a kamera elpásztázott róla) → a kiegészítés után a 2. frame-en
    is 5 hazai van, az 5-ös ESTIMATED-ként, csökkent megbízhatósággal.
    """
    roster = RosterTimeline(suspensions=[
        Suspension(team=Team.HOME, start_t=0, duration_t=100),
        Suspension(team=Team.HOME, start_t=0, duration_t=100),
    ])
    meta = MatchMeta(match_id="e", home_team="A", away_team="B", fps=25.0,
                     frame_width=1920, frame_height=1080)
    def frame(t, ids):
        return Frame(t=t, players=[_home(i, 10.0 + i, 10.0) for i in ids], ball=None)
    match = Match(meta, [frame(0, [1, 2, 3, 4, 5]),
                         frame(1, [1, 2, 3, 4, 5]),
                         frame(2, [1, 2, 3, 4])])  # az 5-ös eltűnt
    added = augment_match_with_estimates(match, roster)
    assert added == 1
    last = match.frames[2].players
    assert len([p for p in last if p.team == Team.HOME]) == 5
    est = [p for p in last if p.source == PositionSource.ESTIMATED]
    assert len(est) == 1 and est[0].track_id == 5
    assert est[0].confidence < 1.0


def test_augment_match_no_change_when_all_visible():
    """Ha mindenki látszik (a roster szerinti létszám), nem kerül be becslés."""
    roster = RosterTimeline(suspensions=[
        Suspension(team=Team.HOME, start_t=0, duration_t=100),
        Suspension(team=Team.HOME, start_t=0, duration_t=100),
    ])
    meta = MatchMeta(match_id="e", home_team="A", away_team="B", fps=25.0,
                     frame_width=1920, frame_height=1080)
    match = Match(meta, [Frame(t=t, players=[_home(i, 10.0 + i, 10.0)
                                             for i in range(1, 6)], ball=None)
                         for t in range(3)])
    added = augment_match_with_estimates(match, roster)
    assert added == 0
    assert all(len(f.players) == 5 for f in match.frames)


def test_reapply_with_suspension_removes_phantom():
    """Utólagos kiállítás-felvitel: az újraszámítás eltünteti a fantom-becslést.

    Alap roster (7 kell): a 2. frame-en eltűnt 6-ost becsléssel pótolnánk. Ha
    viszont az edző felviszi, hogy a 2. frame-től KÉT kiállítás él (7-2=5 fő
    elég, és pont 5 látszik), az újraszámítás után nem marad becsült játékos.
    (Megjegyzés: a szabálykönyvi alsó korlát 5 fő — ez alá a létszám-igény
    kiállításokkal sem mehet.)
    """
    meta = MatchMeta(match_id="e", home_team="A", away_team="B", fps=25.0,
                     frame_width=1920, frame_height=1080)
    def frame(t, ids):
        return Frame(t=t, players=[_home(i, 10.0 + i, 10.0) for i in ids], ball=None)
    match = Match(meta, [frame(0, [1, 2, 3, 4, 5, 6]),
                         frame(1, [1, 2, 3, 4, 5, 6]),
                         frame(2, [1, 2, 3, 4, 5])])  # a 6-os eltűnt
    # Először alap roster (7 kell): a 2. frame-en a 6-ost pótolja (1 becslés).
    assert augment_match_with_estimates(match) == 1
    # Az edző felviszi: a 2. frame-től két kiállítás → 5 fő elég, 5 látszik.
    r2 = RosterTimeline(suspensions=[
        Suspension(team=Team.HOME, start_t=2, duration_t=100),
        Suspension(team=Team.HOME, start_t=2, duration_t=100),
    ])
    added = reapply_estimates(match, r2)
    assert added == 0
    # nem maradt becsült pozíció, és a mértek érintetlenek
    assert all(p.source == PositionSource.MEASURED
               for f in match.frames for p in f.players)
    assert len(match.frames[2].players) == 5


def test_reapply_is_idempotent():
    """Kétszer ugyanazzal a rosterrel újraszámolva ugyanaz az eredmény."""
    meta = MatchMeta(match_id="e", home_team="A", away_team="B", fps=25.0,
                     frame_width=1920, frame_height=1080)
    def frame(t, ids):
        return Frame(t=t, players=[_home(i, 10.0 + i, 10.0) for i in ids], ball=None)
    match = Match(meta, [frame(0, [1, 2, 3, 4, 5]),
                         frame(1, [1, 2, 3, 4])])
    r = RosterTimeline(suspensions=[
        Suspension(team=Team.HOME, start_t=0, duration_t=100),
        Suspension(team=Team.HOME, start_t=0, duration_t=100),
    ])
    a1 = reapply_estimates(match, r)
    n1 = [len(f.players) for f in match.frames]
    a2 = reapply_estimates(match, r)
    n2 = [len(f.players) for f in match.frames]
    assert a1 == a2 and n1 == n2


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
