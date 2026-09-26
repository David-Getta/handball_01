"""
Tesztek a minőség-jelentésre (quality.py).

Futtatás:
    python tests/test_quality.py
"""

from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Match, MatchMeta, Frame, PlayerPosition, Ball, PositionSource, Team,
)
from handball.pipeline.quality import compute_quality_report


def _meta(fps=25.0):
    # A tiszta alapeset KALIBRÁLT feldolgozás — enélkül minden mérés
    # csak arányos becslés lenne, és a jelentés joggal figyelmeztetne.
    return MatchMeta(match_id="q", home_team="A", away_team="B", fps=fps,
                     frame_width=1920, frame_height=1080, calibrated=True)


def _pl(i, source=PositionSource.MEASURED):
    # Kiegyensúlyozott felállás: a páros indexek hazaiak, a páratlanok
    # vendégek — mint egy valódi meccsen (az arány-ellenőrzés miatt).
    team = Team.HOME if i % 2 == 0 else Team.AWAY
    return PlayerPosition(track_id=i, team=team, x=20.0, y=10.0,
                          source=source, confidence=1.0)


def test_full_coverage_high_score():
    """Teljes lefedettség (14 mért játékos + labda minden kockán): magas pontszám."""
    frames = [Frame(t=t, players=[_pl(i) for i in range(14)],
                    ball=Ball(x=20.0, y=10.0, confidence=1.0)) for t in range(20)]
    r = compute_quality_report(Match(_meta(), frames))
    assert r["score"] >= 90
    assert r["warnings"] == []
    assert r["ball_coverage_pct"] == 100.0
    assert r["avg_measured_players"] == 14.0


def test_no_ball_warning_and_lower_score():
    """Labda nélkül: figyelmeztetés + alacsonyabb pontszám."""
    frames = [Frame(t=t, players=[_pl(i) for i in range(14)], ball=None)
              for t in range(20)]
    r = compute_quality_report(Match(_meta(), frames))
    assert r["ball_coverage_pct"] == 0.0
    assert any("labda" in w.lower() for w in r["warnings"])
    assert r["score"] <= 65


def test_few_players_warning():
    """Kevés látott játékos: kalibrációra utaló figyelmeztetés."""
    frames = [Frame(t=t, players=[_pl(1), _pl(2)],
                    ball=Ball(x=20.0, y=10.0, confidence=1.0)) for t in range(10)]
    r = compute_quality_report(Match(_meta(), frames))
    assert any("kalibráció" in w.lower() for w in r["warnings"])


def test_estimated_ratio_counted():
    """A becsült pozíciók aránya megjelenik, és sok becsültnél figyelmeztet."""
    players = [_pl(i) for i in range(6)] + \
              [_pl(10 + i, PositionSource.ESTIMATED) for i in range(8)]
    frames = [Frame(t=t, players=list(players),
                    ball=Ball(x=20.0, y=10.0, confidence=1.0)) for t in range(10)]
    r = compute_quality_report(Match(_meta(), frames))
    assert abs(r["estimated_ratio_pct"] - 100.0 * 8 / 14) < 0.5
    assert any("becsült" in w.lower() for w in r["warnings"])


def test_longest_ball_gap_seconds():
    """A leghosszabb labda-hézag másodpercben, fps-sel átváltva."""
    frames = []
    for t in range(50):
        ball = None if 10 <= t < 40 else Ball(x=20.0, y=10.0, confidence=1.0)
        frames.append(Frame(t=t, players=[_pl(i) for i in range(14)], ball=ball))
    r = compute_quality_report(Match(_meta(fps=5.0), frames))
    assert abs(r["longest_ball_gap_s"] - 6.0) < 1e-9  # 30 kocka / 5 fps
    assert any("kiesés" in w.lower() for w in r["warnings"])


def test_empty_match():
    """Üres meccs: 0 pont + magyarázó figyelmeztetés (nem hibázik)."""
    r = compute_quality_report(Match(_meta(), []))
    assert r["score"] == 0 and r["frames"] == 0
    assert r["warnings"]


def test_goalkeeper_warning_on_long_match_without_roles():
    """2+ perces felvételen kapus-jelölés nélkül figyelmeztetés jár."""
    frames = [Frame(t=t, players=[_pl(i) for i in range(14)],
                    ball=Ball(x=20.0, y=10.0, confidence=1.0))
              for t in range(int(150 * 25))]
    r = compute_quality_report(Match(_meta(), frames))
    assert r["goalkeepers"] == {"home": False, "away": False}
    assert any("kapust" in w for w in r["warnings"])


def test_goalkeeper_fields_true_when_marked():
    """Megjelölt kapusokkal nincs kapus-figyelmeztetés."""
    def gk(i, team):
        return PlayerPosition(track_id=i, team=team, x=1.5, y=10.0,
                              source=PositionSource.MEASURED,
                              confidence=1.0, role="kapus")
    frames = [Frame(t=t, players=[_pl(i) for i in range(12)]
                    + [gk(50, Team.HOME), gk(51, Team.AWAY)],
                    ball=Ball(x=20.0, y=10.0, confidence=1.0))
              for t in range(int(150 * 25))]
    r = compute_quality_report(Match(_meta(), frames))
    assert r["goalkeepers"] == {"home": True, "away": True}
    assert not any("kapust" in w for w in r["warnings"])


def test_seven_meter_spam_warning():
    """Percenként ~2 "hétméteres" (álló labda a 7 m-es ponton) gyanús."""
    frames = []
    for t in range(int(120 * 25)):
        # A labda 33/10-en áll (a +x kapu 7 m-es pontja), 25 mp-enként
        # 5 mp-re "elmozdul", hogy sok külön esemény szülessen.
        moving = (t // 25) % 6 == 5
        bx = 20.0 if moving else 33.0
        frames.append(Frame(t=t, players=[_pl(i) for i in range(14)],
                            ball=Ball(x=bx, y=10.0, confidence=1.0)))
    r = compute_quality_report(Match(_meta(), frames))
    assert r["seven_meters"] >= 2
    assert any("hétméteres" in w for w in r["warnings"])


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


def test_tracking_health_metrics_present():
    """Az új követés-egészség mutatók jelen vannak és értelmesek."""
    from handball.sim.match_simulator import simulate_ground_truth
    m = simulate_ground_truth(duration_s=10, fps=25.0, seed=2)
    q = compute_quality_report(m)
    assert q["track_count"] == 14  # a szimulátor 14 stabil játékosa
    assert abs(q["fragmentation"] - 1.0) < 0.01  # nincs szakadás
    assert q["avg_track_length_s"] > 5.0
    assert 35.0 <= q["home_share_pct"] <= 65.0
    assert q["jersey_coverage_pct"] == 100.0  # a szimulátor mezszámot is ad
    # Kiegyensúlyozott, ép követésnél nincs töredezettség/arány-figyelmeztetés.
    assert not any("töredezett" in w for w in q["warnings"])
    assert not any("egyoldalú" in w for w in q["warnings"])


def test_fragmentation_warning_on_many_short_tracks():
    """Sok rövid track (szakadozó követés) → töredezettség-figyelmeztetés."""
    frames = []
    for t in range(100):
        # Minden 2 kockán új track-azonosító — extrém töredezettség.
        frames.append(Frame(t=t, players=[
            PlayerPosition(track_id=1000 + t // 2, team=Team.HOME,
                           x=10.0 + (t % 5), y=5.0),
        ]))
    m = Match(meta=_meta(), frames=frames)
    q = compute_quality_report(m)
    assert q["fragmentation"] > 3.0
    assert any("töredezett" in w for w in q["warnings"])


def test_one_sided_team_share_warning():
    """Ha szinte minden mért pozíció egy csapaté → arány-figyelmeztetés."""
    frames = [Frame(t=t, players=[
        PlayerPosition(track_id=1, team=Team.HOME, x=10.0, y=5.0),
        PlayerPosition(track_id=2, team=Team.HOME, x=12.0, y=6.0),
        PlayerPosition(track_id=3, team=Team.HOME, x=14.0, y=7.0),
    ]) for t in range(50)]
    m = Match(meta=_meta(), frames=frames)
    q = compute_quality_report(m)
    assert q["home_share_pct"] > 90.0
    assert any("egyoldalú" in w for w in q["warnings"])


def test_analysis_confidence_rows():
    """A réteg-megbízhatóság minden sora teljes; rövid, gól nélküli
    klipnél az xG/momentum/hajrá nem elérhető, magyar indoklással."""
    from handball.pipeline.quality import analysis_confidence
    from handball.sim.match_simulator import simulate_ground_truth
    rows = analysis_confidence(simulate_ground_truth(duration_s=20,
                                                     fps=25.0, seed=2))
    assert {r["layer"] for r in rows} >= {"xg", "goalkeeper", "halftime",
                                          "clutch", "momentum",
                                          "conditioning"}
    for r in rows:
        assert r["label"] and r["reason"]
        assert isinstance(r["available"], bool)
    clutch = next(r for r in rows if r["layer"] == "clutch")
    assert clutch["available"] is False
    assert "rövidebb" in clutch["reason"]


def test_simulated_halftime_break_is_detected():
    """A szimulátor félidei szünetével a szünet-felismerés működik, és a
    félidő-rétegek elérhetővé válnak a réteg-megbízhatóságban."""
    from handball.pipeline.halftime import detect_halftime
    from handball.pipeline.quality import analysis_confidence
    from handball.sim.match_simulator import simulate_ground_truth
    m = simulate_ground_truth(duration_s=240, fps=25.0, seed=3,
                              halftime_break_s=90.0)
    half_t = detect_halftime(m)
    assert half_t is not None
    # A szünet a játékidő közepe táján van.
    assert 0.3 * len(m.frames) < half_t < 0.7 * len(m.frames)
    rows = analysis_confidence(m)
    ht = next(r for r in rows if r["layer"] == "halftime")
    assert ht["available"] is True


def test_confidence_includes_positions_layer():
    """A megbízhatósági lista tartalmazza a poszt-becslés réteget, és
    üres meccsen nem elérhetőként jelöli."""
    from handball.models.tracking import Frame, Match, MatchMeta
    from handball.pipeline.quality import analysis_confidence

    m = Match(MatchMeta(match_id="qp", home_team="H", away_team="A",
                        fps=25.0),
              [Frame(t=i, players=[], ball=None) for i in range(100)])
    rows = analysis_confidence(m)
    pos = next(r for r in rows if r["layer"] == "positions")
    assert pos["available"] is False
    assert "poszt" in pos["reason"]


def test_confidence_includes_jersey_layer():
    """A mezszám-lefedettség sor jelen van: mezszámos meccsnél
    elérhető, szám nélküli meccsnél magyar teendővel jelez."""
    from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                          PlayerPosition, PositionSource,
                                          Team)
    from handball.pipeline.quality import analysis_confidence
    from handball.sim.match_simulator import simulate_ground_truth

    rows = analysis_confidence(simulate_ground_truth(duration_s=10,
                                                     fps=25.0, seed=3))
    jr = next(r for r in rows if r["layer"] == "jerseys")
    assert "mezszám" in jr["reason"]

    frames = [Frame(t=0, players=[
        PlayerPosition(track_id=1, team=Team.HOME, x=10.0, y=10.0,
                       source=PositionSource.MEASURED, confidence=1.0),
        PlayerPosition(track_id=2, team=Team.AWAY, x=30.0, y=10.0,
                       source=PositionSource.MEASURED, confidence=1.0),
    ], ball=Ball(x=20.0, y=10.0, confidence=1.0))]
    m = Match(MatchMeta(match_id="jq", home_team="H", away_team="A",
                        fps=25.0), frames)
    jr2 = next(r for r in analysis_confidence(m)
               if r["layer"] == "jerseys")
    assert jr2["available"] is False
    assert "rendelj" in jr2["reason"]


def test_elcsuszott_kalibracio_figyelmeztetes():
    """Ha a mért pozíciók jelentős része a pályán KÍVÜLRE vetül, a
    jelentés kimondja: elcsúszott kalibráció — és megmondja, mit
    ellenőrizzen a felhasználó (6 m-es ÉS 9 m-es vonal)."""
    def _out(i):
        # Minden negyedik játékos jóval a pályán kívülre vetül.
        team = Team.HOME if i % 2 == 0 else Team.AWAY
        x, y = (20.0, 10.0) if i % 4 else (48.0, 27.0)
        return PlayerPosition(track_id=i, team=team, x=x, y=y,
                              source=PositionSource.MEASURED,
                              confidence=1.0)

    frames = [Frame(t=t, players=[_out(i) for i in range(12)],
                    ball=Ball(x=20.0, y=10.0, confidence=1.0))
              for t in range(30)]
    r = compute_quality_report(Match(_meta(), frames))
    assert r["out_of_court_pct"] >= 12.0
    assert any("kívülre" in w.lower() for w in r["warnings"])
    assert any("9 m-es" in w for w in r["warnings"])


def test_jo_kalibracional_nincs_kivulre_figyelmeztetes():
    """A pályán belüli mérésekre nincs kalibráció-figyelmeztetés (a
    kifutó szélsőt és a mérés zaját a tűrés elnyeli)."""
    frames = [Frame(t=t, players=[_pl(i) for i in range(14)],
                    ball=Ball(x=20.0, y=10.0, confidence=1.0))
              for t in range(20)]
    r = compute_quality_report(Match(_meta(), frames))
    assert r["out_of_court_pct"] == 0.0
    assert not any("kívülre" in w.lower() for w in r["warnings"])


def _jo_frames(n=20):
    return [Frame(t=t, players=[_pl(i) for i in range(14)],
                  ball=Ball(x=20.0, y=10.0, confidence=1.0))
            for t in range(n)]


def test_meccs_ablak_sikertelenseget_kimondja():
    """"Amikor ott álltak a csapatok, akkor is írta, hogy eladott labda."

    Ha a meccs-ablak felismerése NEM talált összefüggő játékot, akkor a
    bemelegítés és a csapatbemutatás bennmaradt az elemzésben. A
    jelentésnek ezt ki kell mondania — a felhasználó a számokból nem
    tudja kitalálni —, és az ELSŐ TEENDŐ-nek a kézi időablakot kell
    ajánlania.
    """
    meta = _meta()
    meta.game_window_found = False
    r = compute_quality_report(Match(meta, _jo_frames()))
    assert r["game_window_found"] is False
    assert any("meccs tényleges kezdetét" in w for w in r["warnings"])
    assert any("bemelegítés" in w for w in r["warnings"])
    assert r["next_action"] is not None
    assert "időablak" in r["next_action"]


def test_sikeres_meccs_ablak_nem_figyelmeztet():
    """Ha megtaláltuk a játékot, nincs miről szólni — a levágott
    szakaszok hossza viszont a jelentésbe kerül (a kliens ezt mutatja
    meg: TÉNYLEG kimaradt a bemelegítés)."""
    meta = _meta()
    meta.game_window_found = True
    meta.game_trim_head_s = 180.0
    meta.game_trim_tail_s = 0.0
    r = compute_quality_report(Match(meta, _jo_frames()))
    assert r["game_window_found"] is True
    assert r["game_trim_head_s"] == 180.0
    assert not any("meccs tényleges kezdetét" in w for w in r["warnings"])


def test_regi_mentesrol_nem_allitunk_semmit():
    """A mező előtti mentésekben nincs adat (None) — arra sem
    figyelmeztetést, sem megnyugtatást nem adunk."""
    r = compute_quality_report(Match(_meta(), _jo_frames()))
    assert r["game_window_found"] is None
    assert not any("meccs tényleges kezdetét" in w for w in r["warnings"])
    assert r["warnings"] == []


def test_a_feldolgozott_szakaszclock_label_szerint():
    """"Csak az első félidőt elemezte ki" — a százalék ezt nem mondja el.

    A jelentésnek meg kell mondania, MELYIK szakaszt dolgoztuk fel a
    forrásvideó órája szerint, mert a felhasználó a videót
    perc:másodpercben keresi vissza. A "60%" nem árulja el, hogy az
    eleje vagy a vége maradt ki.
    """
    from handball.pipeline.quality import clock_label

    meta = _meta(fps=12.5)          # 25 fps forrás, stride=2
    meta.stride = 2
    meta.start_frame = 1500         # 60 mp a videó elejétől (25 fps-sel)
    meta.video_seconds = 600.0
    frames = [Frame(t=t, players=[_pl(i) for i in range(14)],
                    ball=Ball(x=20.0, y=10.0, confidence=1.0))
              for t in range(1250)]   # 1250 / 12.5 = 100 mp játék
    r = compute_quality_report(Match(meta, frames))
    assert r["processed_from_s"] == 60.0
    assert r["processed_to_s"] == 160.0
    # A figyelmeztetés a konkrét szakaszt mondja, nem csak a százalékot.
    assert any("1:00–2:40" in w for w in r["warnings"])
    assert clock_label(0) == "0:00"
    assert clock_label(2054) == "34:14"
    assert clock_label(3725) == "1:02:05"
    assert clock_label(None) == "?"


def test_a_labda_lefedettseg_nem_hizik_a_sajat_potlasunkkal():
    """A lefedettség azt méri, milyen gyakran LÁTTUK a labdát.

    A rövid hézagokat egyenes vonallal pótoljuk, hogy a birtoklás- és
    passz-felismerés folytonos pályát kapjon — de ezek a pozíciók a mi
    találgatásaink, csökkentett megbízhatósággal jelölve. Ha
    beleszámítanának a lefedettségbe, az őszinteség-mutató a saját
    kitalációnktól tűnne jobbnak, és a "kevés labda-észlelés"
    figyelmeztetés épp azokon a felvételeken hallgatna, ahol kellene.
    """
    from handball.pipeline.ball_filter import INTERPOLATED_CONFIDENCE
    from handball.pipeline.quality import analysis_confidence

    def _fr(t, conf):
        return Frame(t=t, players=[_pl(i) for i in range(14)],
                     ball=(None if conf is None
                           else Ball(x=20.0, y=10.0, confidence=conf)))

    # 10 kockából 2 MÉRT labda, 8 PÓTOLT → 20% lefedettség, 80% pótolt.
    frames = [_fr(t, 1.0) for t in range(2)]
    frames += [_fr(t, INTERPOLATED_CONFIDENCE) for t in range(2, 10)]
    r = compute_quality_report(Match(_meta(), frames))
    assert r["ball_coverage_pct"] == 20.0
    assert r["ball_filled_pct"] == 80.0
    assert any("Kevés labda-észlelés" in w for w in r["warnings"])

    # A réteg-megbízhatóság ugyanezt a MÉRT számot nézi.
    sorok = {row["layer"]: row for row in analysis_confidence(
        Match(_meta(), frames))}
    assert sorok["ball"]["available"] is False
    assert "20%" in sorok["ball"]["reason"]


def test_gyanusan_keves_gol_figyelmeztetes_es_teendo():
    """Az edző az EREDMÉNYBŐL dönti el, hogy hisz-e a jelentésnek.

    Kézilabdában a két csapat együtt percenként nagyjából egy gólt
    szerez. Ha a felismerés ennek a töredékét látja, nem szoros meccset
    mért, hanem gólokat hagyott ki — és ha ezt nem mondjuk ki, az edző
    a JÓ számokat is elveti. A teendő nem zsákutca: a javítás helyét is
    megmondjuk.
    """
    from handball.pipeline.quality import (GOALS_RATE_MIN_MINUTES,
                                           next_action)

    fps = 25.0
    percek = GOALS_RATE_MIN_MINUTES + 2
    frames = [Frame(t=t, players=[_pl(i) for i in range(14)],
                    ball=Ball(x=20.0, y=10.0, confidence=1.0))
              for t in range(int(percek * 60 * fps))]
    r = compute_quality_report(Match(_meta(fps), frames))
    kevés = [w for w in r["warnings"] if "kevés gól" in w]
    assert kevés, r["warnings"]
    assert "GÓL volt" in kevés[0], "a figyelmeztetés nem mondja meg, hol javítható"
    # A teendő-lista is ismeri (különben a rangsorolás átugorná).
    assert next_action(kevés) is not None


def test_rovid_felvetelre_nem_szol_a_gol_arany():
    """Pár perces próbán a szórás önmagában eldönti a gólarányt —
    ilyenkor a figyelmeztetés csak zaj lenne."""
    fps = 25.0
    frames = [Frame(t=t, players=[_pl(i) for i in range(14)],
                    ball=Ball(x=20.0, y=10.0, confidence=1.0))
              for t in range(int(60 * fps))]  # 1 perc
    r = compute_quality_report(Match(_meta(fps), frames))
    assert not [w for w in r["warnings"] if "kevés gól" in w]


def _golos_match(hazai: int, vendeg: int, percek: float = 12.0,
                 fps: float = 25.0):
    """Szintetikus meccs adott gólaránnyal (a labda a kapukba fut be)."""
    frames = []
    t = 0

    def _gol(t, plusz_x):
        for i in range(7):
            x = (34.0 + i) if plusz_x else (6.0 - i)
            frames.append(Frame(t=t, players=[_pl(i2) for i2 in range(14)],
                                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(60):  # szünet a lövések közt (csendidő)
            frames.append(Frame(t=t, players=[_pl(i2) for i2 in range(14)],
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
            t += 1
        return t

    for _ in range(hazai):
        t = _gol(t, True)
    for _ in range(vendeg):
        t = _gol(t, False)
    while t < int(percek * 60 * fps):
        frames.append(Frame(t=t, players=[_pl(i2) for i2 in range(14)],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    return Match(_meta(fps), frames)


def test_aranytalan_eredmeny_figyelmeztetes():
    """A két kapu felismerése KÜLÖN romolhat el.

    Kézilabdában a nagy különbség is jellemzően kétszeres arány körül
    van; ötszörös eltérés inkább azt jelenti, hogy az egyik oldalon nem
    látjuk a gólokat (féloldalas kalibráció, takart kapu). Ha ezt nem
    mondjuk ki, az edző egyoldalú meccsnek olvassa a mérési hibát.
    """
    from handball.pipeline.quality import next_action

    r = compute_quality_report(_golos_match(15, 1))
    aran = [w for w in r["warnings"] if "Aránytalan eredmény" in w]
    assert aran, r["warnings"]
    assert "kalibráció" in aran[0]
    assert next_action(aran) is not None


def test_kiegyensulyozott_eredmenyre_nem_szol():
    """Szoros meccsre nincs mit mondani — a figyelmeztetés csak akkor
    ér valamit, ha ritka."""
    r = compute_quality_report(_golos_match(8, 7))
    assert not [w for w in r["warnings"] if "Aránytalan eredmény" in w]
