"""Gól a középkezdésből: a gól utáni újraindítás a gól második jele."""

from __future__ import annotations

from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                      PlayerPosition, PositionSource, Team)
from handball.pipeline.event_detection import (EventType, THROWOFF_STILL_S,
                                               detect_shots, throw_off_goals)


def _meta(fps=25.0):
    return MatchMeta(match_id="kk", home_team="A", away_team="B", fps=fps)


def _pl(tid, team, x, y=10.0):
    return PlayerPosition(track_id=tid, team=team, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0)


def _tamadas(x0=29.0):
    """Hazai felállt támadás a +x kapu előtt (a hazai a +x felé támad)."""
    return ([_pl(i, Team.HOME, x0 + i * 0.8, 3.0 + i * 2.0) for i in range(7)]
            + [_pl(10 + i, Team.AWAY, 34.0 + (i % 3), 3.0 + i * 2.0)
               for i in range(7)])


def _kozepkezdes_hazai_gol_utan():
    """A hazai gólja után: a vendég (gólt kapó) a SAJÁT térfelén (x > 20)
    a középen, a hazai (szerző) visszafutott a saját kapuja elé."""
    return ([_pl(i, Team.HOME, 6.0 + i, 3.0 + i * 2.0) for i in range(7)]
            + [_pl(10 + i, Team.AWAY, 20.5 + i * 0.8, 3.0 + i * 2.0)
               for i in range(7)])


def _meccs(fps=25.0, *, loves=None, kozep_jatekosok=None, kozep_mp=2.0,
           szunet_mp=6.0, mozgo_kozep=False, utana_tamadas_mp=0.0):
    """Támadás a +x kapu előtt → (lövés) → szünet labda nélkül →
    a labda a középen áll."""
    frames = []
    t = 0

    def add(players, ball):
        nonlocal t
        frames.append(Frame(t=t, players=players, ball=ball))
        t += 1

    # 4 mp felállt támadás: a labda lassan mozog 31–33 m között.
    for k in range(int(4 * fps)):
        add(_tamadas(), Ball(x=31.0 + (k % 20) * 0.1, y=10.0, confidence=1.0))
    if loves == "mellé":
        # Gyors lövés a +x kapu felé, a kapufákon KÍVÜL (y = 3).
        for k in range(6):
            add(_tamadas(), Ball(x=33.0 + 1.2 * k * 25.0 / fps, y=3.0,
                                 confidence=1.0))
    elif loves == "gól":
        for k in range(8):
            add(_tamadas(), Ball(x=min(40.0, 33.0 + 1.0 * k * 25.0 / fps),
                                 y=10.0, confidence=1.0))
    # A lövés után a támadás folytatódik (lepattanó, újabb helyzet): a
    # labda lassan mozog a kapu előtt.
    for k in range(int(utana_tamadas_mp * fps)):
        add(_tamadas(), Ball(x=31.0 + (k % 20) * 0.1, y=10.0, confidence=1.0))
    # Labda nélkül (háló, kapus, labda vissza a középre).
    for _ in range(int(szunet_mp * fps)):
        add(kozep_jatekosok or _kozepkezdes_hazai_gol_utan(), None)
    for k in range(int(kozep_mp * fps)):
        bx = 20.0 + ((k * 0.5) % 4.0 - 2.0 if mozgo_kozep else 0.05 * (k % 3))
        add(kozep_jatekosok or _kozepkezdes_hazai_gol_utan(),
            Ball(x=bx, y=10.0, confidence=1.0))
    # A középkezdés után a vendég támadni indul (a labda elhagyja a
    # közepet, de a másik kapu elé nem ér: x 17 → 15).
    for k in range(int(2 * fps)):
        add(_kozepkezdes_hazai_gol_utan(),
            Ball(x=17.0 - 2.0 * k / (2 * fps), y=10.0, confidence=1.0))
    return Match(_meta(fps), frames)


def _golok(m):
    return [e for e in detect_shots(m) if e.type is EventType.GOAL]


def test_kozepkezdes_utan_gol_akkor_is_ha_a_golt_nem_lattuk():
    golok = _golok(_meccs())
    assert len(golok) == 1
    g = golok[0]
    assert g.team is Team.HOME
    assert g.detail["goal_source"] == "középkezdés"
    assert g.detail["outcome"] == "goal"
    # A lövő nem ismert (a lövő-keresés a gól UTÁNI pillanattól keresne
    # vissza, a kapu előtt álló bármelyik támadót megtehetné szerzőnek).
    assert g.player_id is None
    assert "release_t" not in g.detail


def test_a_latott_lovest_golra_javitja():
    m = _meccs(loves="mellé")
    lov = detect_shots(m)
    assert len(lov) == 1, lov
    assert lov[0].type is EventType.GOAL
    assert lov[0].detail["goal_source"] == "középkezdés"
    assert "goalkeeper_id" not in lov[0].detail


def _kiszedeses_meccs(gyors: bool, jatekosok=None):
    """Támadás a +x kapu előtt → (gyors labda a kapu felé) → a labda
    eltűnik → a kapus 5 mp-ig áll vele a kapuban (a labda kiszedése) →
    középkezdés. Visszaad: (meccs, a lövés kezdő t-je, az eltűnés előtti
    utolsó látott t)."""
    fps = 25.0
    frames = []
    t = 0

    def add(players, ball):
        nonlocal t
        frames.append(Frame(t=t, players=players, ball=ball))
        t += 1

    for k in range(int(4 * fps)):
        add(_tamadas(), Ball(x=31.0 + (k % 20) * 0.1, y=10.0, confidence=1.0))
    loves_t = t
    if gyors:
        # Gyors labda a kapu felé (25 m/s), 35 m-ig látszik — a kapu-sávba
        # (4 m) nem ér, tehát a lövés-felismerés nem látja lövésnek.
        for k in range(4):
            add(_tamadas(), Ball(x=32.0 + k, y=10.0, confidence=1.0))
    eltunes_t = t - 1
    for _ in range(int(1 * fps)):          # eltűnik (háló, takarás)
        add(_tamadas(), None)
    for _ in range(int(5 * fps)):          # a kapus kiszedi, áll vele
        add(jatekosok or _kozepkezdes_hazai_gol_utan(),
            Ball(x=39.0, y=10.0, confidence=1.0))
    for _ in range(int(4 * fps)):
        add(jatekosok or _kozepkezdes_hazai_gol_utan(), None)
    for _ in range(int(2 * fps)):
        add(jatekosok or _kozepkezdes_hazai_gol_utan(),
            Ball(x=20.0, y=10.0, confidence=1.0))
    for k in range(int(2 * fps)):
        add(_kozepkezdes_hazai_gol_utan(),
            Ball(x=17.0 - 2.0 * k / (2 * fps), y=10.0, confidence=1.0))
    return Match(_meta(fps), frames), loves_t, eltunes_t


def test_a_kovetkeztetett_gol_ideje_a_loves_nem_a_labda_kiszedese():
    """A labda utolsó kapu előtti pillanata a gól UTÁN van (a kapus
    kiszedi a hálóból): a gól ideje a kapu felé tartó gyors labda, hogy
    a klip és a 3D jelenet a gólt mutassa."""
    m, loves_t, _ = _kiszedeses_meccs(gyors=True)
    golok = _golok(m)
    assert len(golok) == 1
    assert loves_t <= golok[0].t <= loves_t + 4, golok[0].t


def test_a_kovetkeztetett_gol_ideje_a_labda_eltunese_ha_gyors_labda_nincs():
    """Ha a gyors labdát sem láttuk, a gól ideje a labda eltűnése a kapu
    előtt — nem a labda kiszedése."""
    m, _, eltunes_t = _kiszedeses_meccs(gyors=False)
    golok = _golok(m)
    assert len(golok) == 1 and golok[0].t == eltunes_t


def test_a_latott_gyors_labdabol_valoszinu_lovot_kinal():
    """Ha a kapu felé tartó gyors labdát láttuk, a gép VALÓSZÍNŰ lövőt
    kínál (a lövés-felismerés lövő-keresésével) — de nem írja be: a gól
    lövője üres, a tipp a részletben, és a "set_player" elfogadja."""
    m, _, _ = _kiszedeses_meccs(gyors=True)
    g = _golok(m)[0]
    assert g.player_id is None
    tipp = g.detail.get("shooter_hint")
    assert tipp is not None and tipp < 10       # hazai mezőnyjátékos
    m.meta.event_overrides = [{"op": "set_player", "t": g.t,
                               "type": "goal", "player_id": tipp}]
    assert _golok(m)[0].player_id == tipp


def test_a_gyors_labda_nelkul_nincs_tipp():
    """Ha csak a labda eltűnését láttuk, nincs tipp: a "nem tudjuk" jobb,
    mint a magabiztosan rossz név."""
    m, _, _ = _kiszedeses_meccs(gyors=False)
    assert "shooter_hint" not in _golok(m)[0].detail


def test_a_lehetseges_gol_is_hozza_a_valoszinu_lovot():
    """Összekeveredett felállásnál a jel hallgat; a jelölt a látott gyors
    labdából a valószínű lövőt is hozza (player_hint)."""
    from handball.pipeline.event_detection import throw_off_candidates

    kevert = ([_pl(i, Team.HOME, 18.0 + i, 3.0 + i * 2) for i in range(7)]
              + [_pl(10 + i, Team.AWAY, 17.5 + i, 4.0 + i * 2)
                 for i in range(7)])
    m, _, _ = _kiszedeses_meccs(gyors=True, jatekosok=kevert)
    assert _golok(m) == []
    jel = throw_off_candidates(m)
    assert len(jel) == 1 and "shot_t" not in jel[0]
    assert jel[0].get("player_hint") is not None


def test_eltunes_es_gyors_labda_nelkul_a_labda_utolso_kapu_elotti_pillanata():
    m = _meccs()
    golok = _golok(m)
    utolso = max(f.t for f in m.frames
                 if f.ball is not None and f.ball.x >= 31.0)
    assert golok[0].t == utolso


def test_a_regi_vedest_nem_irja_at_golra():
    """Ha a látott lövés után a támadás még sokáig folytatódott, a gól
    egy későbbi (nem látott) lövésből esett: a régi lövés marad, ami
    volt, és a gól új, lövés nélküli esemény."""
    from handball.pipeline.event_detection import (THROWOFF_UPGRADE_S,
                                                   unseen_goal)

    m = _meccs(loves="mellé", utana_tamadas_mp=THROWOFF_UPGRADE_S + 5)
    lov = detect_shots(m)
    assert [e.type for e in lov] == [EventType.SHOT, EventType.GOAL]
    assert "goal_source" not in (lov[0].detail or {})
    assert unseen_goal(lov[1])


def test_a_mar_felismert_golt_nem_szamolja_ketszer():
    lov = detect_shots(_meccs(loves="gól"))
    golok = [e for e in lov if e.type is EventType.GOAL]
    assert len(golok) == 1
    assert "goal_source" not in (golok[0].detail or {})


def test_osszekeveredett_csapatoknal_nincs_kozepkezdes():
    """A középen álló labda önmagában nem gól: a csapatoknak a saját
    térfelükön kell állniuk."""
    kevert = ([_pl(i, Team.HOME, 18.0 + i, 3.0 + i * 2) for i in range(7)]
              + [_pl(10 + i, Team.AWAY, 17.5 + i, 4.0 + i * 2)
                 for i in range(7)])
    assert _golok(_meccs(kozep_jatekosok=kevert)) == []


def test_egy_pontba_tomorulo_jatekosoknal_nincs_kozepkezdes():
    pont = ([_pl(i, Team.HOME, 20.0) for i in range(7)]
            + [_pl(10 + i, Team.AWAY, 20.0) for i in range(7)])
    assert _golok(_meccs(kozep_jatekosok=pont)) == []


def test_forditott_felallas_nem_ennek_a_kapunak_a_golja():
    """Ha a felállás szerint a HAZAI kapta volna a gólt (ő áll a +x
    térfélen a középen), a +x kapu előtti labda nem az ő gólja."""
    forditott = ([_pl(i, Team.HOME, 20.5 + i * 0.8, 3.0 + i * 2) for i in range(7)]
                 + [_pl(10 + i, Team.AWAY, 6.0 + i, 3.0 + i * 2)
                    for i in range(7)])
    assert _golok(_meccs(kozep_jatekosok=forditott)) == []


def test_mozgo_labda_a_kozepen_nem_kozepkezdes():
    assert _golok(_meccs(mozgo_kozep=True)) == []


def test_ha_utana_ugyanarra_a_kapura_megy_nem_kozepkezdes():
    """A középen megálló labda után ugyanaz a csapat újra ugyanarra a
    kapura támad: ez nem a gólt kapó csapat középkezdése."""
    m = _meccs()
    fps = m.meta.fps
    # Az utolsó 2 mp (a vendég támadás-indítása) helyett a hazai újra a
    # +x kapu elé viszi a labdát.
    m.frames = m.frames[:-int(2 * fps)]
    t = m.frames[-1].t + 1
    for k in range(int(3 * fps)):
        m.frames.append(Frame(t=t, players=_kozepkezdes_hazai_gol_utan(),
                              ball=Ball(x=22.0 + k * 0.2, y=10.0,
                                        confidence=1.0)))
        t += 1
    assert _golok(m) == []


def test_tul_rovid_allas_nem_kozepkezdes():
    assert _golok(_meccs(kozep_mp=THROWOFF_STILL_S * 0.5)) == []


def test_kapu_elotti_labda_nelkul_nincs_gol():
    """A meccs eleji középkezdés: előtte nem járt a labda kapu előtt."""
    fps = 25.0
    frames = [Frame(t=k, players=_kozepkezdes_hazai_gol_utan(),
                    ball=Ball(x=20.0, y=10.0, confidence=1.0))
              for k in range(int(3 * fps))]
    assert throw_off_goals(Match(_meta(fps), frames), []) == []


def test_tul_regi_kapu_elotti_labda_nem_szamit():
    assert _golok(_meccs(szunet_mp=60.0)) == []


def test_ritkitva_is_megtalalja():
    """A termék minden 3. kockát dolgozza fel: a küszöbök
    másodpercben vannak, a jel ritkítva is megszólal."""
    golok = _golok(_meccs(fps=25.0 / 3))
    assert len(golok) == 1 and golok[0].team is Team.HOME


def test_darab_hataron_atnyulo_kozepkezdes_nem_gol():
    """A felvétel-darab (vagy a félidő) határa után álló középkezdés a
    második félidő kezdése lehet, nem az előző támadás gólja."""
    m = _meccs()
    kozep_t = next(f.t for f in m.frames
                   if f.ball is not None and abs(f.ball.x - 20.0) < 1.0)
    m.meta.source_segments = [{"t_from": 0}, {"t_from": kozep_t - 5}]
    assert _golok(m) == []


def test_a_minoseg_jelentes_szamolja_a_kovetkeztetett_golokat():
    """A minőség-jelentés gól-diagnózisa megmondja, hány gól jött a
    középkezdésből (az eredmény mekkora része következtetés)."""
    from handball.pipeline.quality import compute_quality_report

    q = compute_quality_report(_meccs())
    assert q["goals_detected"] == 1
    assert q["goals_from_throw_off"] == 1
    q2 = compute_quality_report(_meccs(loves="gól"))
    assert q2["goals_detected"] == 1 and q2["goals_from_throw_off"] == 0


def test_a_minoseg_jelentes_szamolja_a_lovo_nelkuli_golokat():
    """A lövő nélküli gól kimarad a góllövő-listákból: a minőség-jelentés
    megszámolja, és azt is, hol tippel a gép; a lövő megadása után 0."""
    from handball.pipeline.quality import compute_quality_report

    m, _, _ = _kiszedeses_meccs(gyors=True)
    q = compute_quality_report(m)
    assert q["goals_without_shooter"] == 1 and q["shooter_hints"] == 1
    g = _golok(m)[0]
    m.meta.event_overrides = [{"op": "set_player", "t": g.t,
                               "type": "goal",
                               "player_id": g.detail["shooter_hint"]}]
    q2 = compute_quality_report(m)
    assert q2["goals_without_shooter"] == 0 and q2["shooter_hints"] == 0


def _kapussal(m):
    """A vendég kapusa a +x kapuban (a hazai erre támad)."""
    for f in m.frames:
        f.players.append(PlayerPosition(track_id=99, team=Team.AWAY,
                                        x=39.0, y=10.0,
                                        source=PositionSource.MEASURED,
                                        confidence=1.0, role="kapus"))
    return m


def test_a_nem_latott_loves_golja_nem_rontja_a_vedes_aranyt():
    """A lövés nélküli következtetett gól az eredményben számít, a
    kapus védés-arányában és az xG-ben nem (a hasonlóan nem látott
    védéseknek nincs középkezdésük — a mérleg féloldalas lenne)."""
    from handball.pipeline.event_detection import unseen_goal
    from handball.pipeline.goalkeeper import goalkeeper_stats
    from handball.pipeline.xg import match_xg

    m = _kapussal(_meccs())
    golok = _golok(m)
    assert len(golok) == 1 and unseen_goal(golok[0])
    assert golok[0].detail["shot_seen"] is False
    gk = goalkeeper_stats(m)["away"]
    assert gk["on_target"] == 0 and gk["conceded"] == 0
    assert match_xg(m)["teams"]["home"]["goals"] == 0


def test_a_latott_loves_javitott_golja_a_kapusnak_is_gol():
    """A LÁTOTT lövés, amit a felismerés tévesen nem gólnak ítélt: a
    középkezdés gólra javítja, és a kapus-mérlegben is kapott gól."""
    from handball.pipeline.event_detection import unseen_goal
    from handball.pipeline.goalkeeper import goalkeeper_stats

    m = _kapussal(_meccs(loves="mellé"))
    lov = detect_shots(m)
    assert len(lov) == 1 and lov[0].type is EventType.GOAL
    assert not unseen_goal(lov[0])
    gk = goalkeeper_stats(m)["away"]
    assert gk["on_target"] == 1 and gk["conceded"] == 1


def test_a_latott_golt_nem_szamolja_ketszer_ha_a_kapus_sokaig_tartja():
    """Látott gól, utána a kapus 8 mp-ig a kapu előtt tartja a labdát,
    majd középkezdés: EGY gól (a labda utolsó kapu előtti pillanata a gól
    után van — a meglévő gólt a kapu előtti szakaszban kell keresni), és
    lehetséges gólt sem kínál fel."""
    from handball.pipeline.event_detection import throw_off_candidates

    fps = 25.0
    frames = []
    t = 0

    def add(players, ball):
        nonlocal t
        frames.append(Frame(t=t, players=players, ball=ball))
        t += 1

    for k in range(int(4 * fps)):
        add(_tamadas(), Ball(x=31.0 + (k % 20) * 0.1, y=10.0, confidence=1.0))
    for k in range(8):   # LÁTOTT gól: a labda a kapufák között a vonalra
        add(_tamadas(), Ball(x=min(40.0, 33.0 + k), y=10.0, confidence=1.0))
    for _ in range(int(8 * fps)):   # a kapus 8 mp-ig a kapuban tartja
        add(_kozepkezdes_hazai_gol_utan(),
            Ball(x=39.0, y=10.0, confidence=1.0))
    for _ in range(int(3 * fps)):
        add(_kozepkezdes_hazai_gol_utan(), None)
    for _ in range(int(2 * fps)):
        add(_kozepkezdes_hazai_gol_utan(), Ball(x=20.0, y=10.0,
                                                 confidence=1.0))
    for k in range(int(2 * fps)):
        add(_kozepkezdes_hazai_gol_utan(),
            Ball(x=17.0 - 2.0 * k / (2 * fps), y=10.0, confidence=1.0))
    m = Match(_meta(fps), frames)
    golok = _golok(m)
    assert len(golok) == 1, [(g.t, g.detail) for g in golok]
    assert "goal_source" not in (golok[0].detail or {})
    assert throw_off_candidates(m) == []


def _sokaig_tartott_meccs(lepattano_mp: float = 0.0):
    """Hazai támadás → LÁTOTT lövés a kapu közepére, ami a kapusnál áll
    meg (a felismerés védésnek ítéli) → (lepattanó: a támadás a 9 m-en
    folytatódik) → a labda eltűnik → a kapus 12 mp-ig a kapuban tartja →
    középkezdés."""
    fps = 25.0
    frames = []
    t = 0

    def add(players, ball):
        nonlocal t
        frames.append(Frame(t=t, players=players, ball=ball))
        t += 1

    for k in range(int(4 * fps)):
        add(_tamadas(), Ball(x=31.0 + (k % 20) * 0.1, y=10.0, confidence=1.0))
    for k in range(6):    # 25 m/s a kapu felé, a vonal előtt megáll
        add(_tamadas(), Ball(x=33.0 + k, y=10.0, confidence=1.0))
    for _ in range(int(1 * fps)):
        add(_tamadas(), None)
    for k in range(int(lepattano_mp * fps)):
        add(_tamadas(), Ball(x=31.0 + (k % 20) * 0.1, y=10.0, confidence=1.0))
    if lepattano_mp:
        for _ in range(int(1 * fps)):    # a nem látott második lövés
            add(_tamadas(), None)
    for _ in range(int(12 * fps)):       # a kapus 12 mp-ig tartja
        add(_kozepkezdes_hazai_gol_utan(),
            Ball(x=39.0, y=10.0, confidence=1.0))
    for _ in range(int(3 * fps)):
        add(_kozepkezdes_hazai_gol_utan(), None)
    for _ in range(int(2 * fps)):
        add(_kozepkezdes_hazai_gol_utan(), Ball(x=20.0, y=10.0,
                                                 confidence=1.0))
    for k in range(int(2 * fps)):
        add(_kozepkezdes_hazai_gol_utan(),
            Ball(x=17.0 - 2.0 * k / (2 * fps), y=10.0, confidence=1.0))
    return _kapussal(Match(_meta(fps), frames))


def test_a_latott_lovest_akkor_is_golra_javitja_ha_a_kapus_sokaig_tartja():
    """A látott lövés után a labda a kapuelőtérben maradt (a kapus 12
    mp-ig tartotta — régebbi, mint THROWOFF_UPGRADE_S): a lövés volt a
    gól. EGY gól, a lövőé, és a kapusnak kapott gól, nem védés."""
    from handball.pipeline.event_detection import (THROWOFF_UPGRADE_S,
                                                   unseen_goal)
    from handball.pipeline.goalkeeper import goalkeeper_stats

    assert 12 > THROWOFF_UPGRADE_S
    m = _sokaig_tartott_meccs()
    lov = detect_shots(m)
    assert [e.type for e in lov] == [EventType.GOAL], lov
    assert lov[0].detail["goal_source"] == "középkezdés"
    assert not unseen_goal(lov[0])
    assert lov[0].player_id is not None
    gk = goalkeeper_stats(m)["away"]
    assert gk["on_target"] == 1 and gk["conceded"] == 1


def test_a_lepattano_utani_golnal_a_latott_vedes_marad():
    """Ha a látott lövés után a labda kikerült a kapuelőtérből (lepattanó,
    a támadás folytatódott), a gól egy későbbi, nem látott lövésből esett:
    a védés marad, és a gól új, lövés nélküli esemény."""
    from handball.pipeline.event_detection import unseen_goal

    lov = detect_shots(_sokaig_tartott_meccs(lepattano_mp=3.0))
    assert [e.type for e in lov] == [EventType.SHOT, EventType.GOAL], lov
    assert lov[0].detail["outcome"] == "save"
    assert unseen_goal(lov[1])


def test_a_kovetkeztetett_gol_lovoje_kezzel_megadhato():
    """A középkezdésből következtetett gól lövője ismeretlen — az edző
    megadhatja ("set_player"). A lövést továbbra sem láttuk: az arány-
    mérők (xG, kapus) ugyanúgy kihagyják."""
    from handball.pipeline.event_detection import unseen_goal

    m = _meccs()
    g = _golok(m)[0]
    assert g.player_id is None
    m.meta.event_overrides = [{"op": "set_player", "t": g.t,
                               "type": "goal", "player_id": 3}]
    ki = _golok(m)
    assert len(ki) == 1 and ki[0].player_id == 3
    assert unseen_goal(ki[0])


def test_lehetseges_gol_ha_a_felallas_nem_merheto():
    """Összekeveredett felállásnál a jel hallgat — a jelölt-lista
    viszont felkínálja a pillanatot az edzőnek, a becsült
    gól-pillanattal és a kaput támadó csapattal."""
    from handball.pipeline.event_detection import throw_off_candidates

    kevert = ([_pl(i, Team.HOME, 18.0 + i, 3.0 + i * 2) for i in range(7)]
              + [_pl(10 + i, Team.AWAY, 17.5 + i, 4.0 + i * 2)
                 for i in range(7)])
    m = _meccs(kozep_jatekosok=kevert)
    assert _golok(m) == []
    jel = throw_off_candidates(m)
    assert len(jel) == 1
    assert jel[0]["team"] == "home" and jel[0]["goal_x"] == 40.0
    assert jel[0]["goal_t"] < jel[0]["t"]


def test_a_jelolt_a_latott_lovest_hozza_es_a_megerosites_azt_javitja():
    """A lehetséges gól mögött LÁTOTT lövés áll (a gép mellének ítélte):
    a jelölt hozza a lövést (shot_t, a gól ideje is az), és a megerősítés
    ("set_type" a lövés idejével) a lövést írja át gólra — EGY gól, nem
    lövés + gól. A kijelölt játékos a lövő lesz."""
    from handball.pipeline.event_detection import throw_off_candidates

    kevert = ([_pl(i, Team.HOME, 18.0 + i, 3.0 + i * 2) for i in range(7)]
              + [_pl(10 + i, Team.AWAY, 17.5 + i, 4.0 + i * 2)
                 for i in range(7)])
    m = _meccs(loves="mellé", kozep_jatekosok=kevert)
    lov = detect_shots(m)
    assert [e.type for e in lov] == [EventType.SHOT]
    jel = throw_off_candidates(m)
    assert len(jel) == 1
    assert jel[0]["shot_t"] == lov[0].t == jel[0]["goal_t"]
    m.meta.event_overrides = [{"op": "set_type", "t": jel[0]["shot_t"],
                               "type": "goal", "player_id": 3}]
    ki = detect_shots(m)
    assert [e.type for e in ki] == [EventType.GOAL]
    assert ki[0].player_id == 3
    assert throw_off_candidates(m) == []


def test_nincs_jelolt_ha_mar_van_gol():
    """A felismert (vagy következtetett) gól után nincs jelölt — a lista
    csak a hiányzó gólokat kínálja fel."""
    from handball.pipeline.event_detection import throw_off_candidates

    assert throw_off_candidates(_meccs()) == []
    assert throw_off_candidates(_meccs(loves="gól")) == []


def test_a_kezzel_felvett_gol_utan_eltunik_a_jelolt():
    """Az edző megerősíti ("Gól volt" → kézi felvétel): a jelölt eltűnik."""
    from handball.pipeline.event_detection import throw_off_candidates

    kevert = ([_pl(i, Team.HOME, 18.0 + i, 3.0 + i * 2) for i in range(7)]
              + [_pl(10 + i, Team.AWAY, 17.5 + i, 4.0 + i * 2)
                 for i in range(7)])
    m = _meccs(kozep_jatekosok=kevert)
    jel = throw_off_candidates(m)
    m.meta.event_overrides = [{"op": "add", "t": jel[0]["goal_t"],
                               "type": "goal", "team": jel[0]["team"]}]
    assert len(_golok(m)) == 1
    assert throw_off_candidates(m) == []


def test_az_elvetett_lehetseges_gol_eltunik():
    """"Nem gól": az edző elveti a jelöltet (dismiss a középkezdés
    idejével) — a lista kihagyja, a gólok nem változnak."""
    from handball.pipeline.event_detection import throw_off_candidates

    kevert = ([_pl(i, Team.HOME, 18.0 + i, 3.0 + i * 2) for i in range(7)]
              + [_pl(10 + i, Team.AWAY, 17.5 + i, 4.0 + i * 2)
                 for i in range(7)])
    m = _meccs(kozep_jatekosok=kevert)
    jel = throw_off_candidates(m)
    assert len(jel) == 1
    m.meta.event_overrides = [{"op": "dismiss", "t": jel[0]["t"],
                               "type": "goal"}]
    assert throw_off_candidates(m) == []
    assert _golok(m) == []


def test_a_minoseg_jelentes_megnevezi_a_lehetseges_golokat():
    """Kevés gól mellett a "Gyanúsan kevés gól" figyelmeztetés kimondja,
    hány lehetséges gól vár, és hol vehető fel."""
    from handball.pipeline.quality import (GOALS_RATE_MIN_MINUTES,
                                           compute_quality_report)

    kevert = ([_pl(i, Team.HOME, 18.0 + i, 3.0 + i * 2) for i in range(7)]
              + [_pl(10 + i, Team.AWAY, 17.5 + i, 4.0 + i * 2)
                 for i in range(7)])
    m = _meccs(kozep_jatekosok=kevert)
    # A meccs hosszát a gól-arány küszöbe fölé nyújtjuk (a végén álló,
    # a közepen kívüli labdával).
    fps = m.meta.fps
    t = m.frames[-1].t + 1
    while t < int((GOALS_RATE_MIN_MINUTES + 1) * 60 * fps):
        m.frames.append(Frame(t=t, players=_kozepkezdes_hazai_gol_utan(),
                              ball=Ball(x=15.0, y=10.0, confidence=1.0)))
        t += 1
    q = compute_quality_report(m)
    assert q["goal_candidates"] == 1
    keves = [w for w in q["warnings"] if "kevés gól" in w]
    assert keves and "1 lehetséges gólt is találtunk" in keves[0]


def test_az_elvetett_jelolt_nem_ter_vissza_ujabb_kozepen_allassal():
    """Elvetés után a labda röviden kimozdul, majd újra megáll a
    középen: ugyanabból a kapu előtti szakaszból nem lesz új jelölt."""
    from handball.pipeline.event_detection import throw_off_candidates

    kevert = ([_pl(i, Team.HOME, 18.0 + i, 3.0 + i * 2) for i in range(7)]
              + [_pl(10 + i, Team.AWAY, 17.5 + i, 4.0 + i * 2)
                 for i in range(7)])
    m = _meccs(kozep_jatekosok=kevert)
    jel = throw_off_candidates(m)
    assert len(jel) == 1
    m.meta.event_overrides = [{"op": "dismiss", "t": jel[0]["t"],
                               "type": "goal"}]
    fps = m.meta.fps
    t = m.frames[-1].t + 1
    # A labda (a vendég támadás-indítása után) visszakerül a középre, és
    # újra megáll — közben nem jár kapu előtt.
    for _ in range(int(2 * fps)):
        m.frames.append(Frame(t=t, players=kevert,
                              ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    assert throw_off_candidates(m) == []


def test_egy_kapu_elotti_szakaszbol_egy_gol():
    """Két egymás utáni középkezdés-szerű állás ugyanazon kapu előtti
    szakasz után: csak egy gól."""
    m = _meccs()
    fps = m.meta.fps
    t = m.frames[-1].t + 1
    for k in range(int(3 * fps)):
        m.frames.append(Frame(t=t, players=_kozepkezdes_hazai_gol_utan(),
                              ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    assert len(_golok(m)) == 1


def test_a_jelentes_es_az_osszefoglalo_kimondja_a_kovetkeztetett_golt():
    """A nyomtatható jelentés gól-idővonala és az edzői összefoglaló is
    megnevezi a középkezdésből következtetett gólt."""
    from handball.pipeline.coach_summary import _events_section
    from handball.pipeline.event_detection import detect_events
    from handball.pipeline.report_html import match_report_html

    m = _meccs()
    html = match_report_html(m, {}, detect_events(m), None)
    assert "· középkezdésből" in html
    assert "1 gólt a gól utáni középkezdésből következtetett" in html
    s = _events_section(m, "A", "B")
    assert s is not None and "középkezdésből" in s["body"]
