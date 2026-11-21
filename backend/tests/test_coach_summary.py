"""
Tesztek az automatikus edzői összefoglalóra (coach_summary).

Futtatás:
    python -m pytest tests/test_coach_summary.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import Match, MatchMeta  # noqa: E402
from handball.pipeline.coach_summary import (  # noqa: E402
    coach_summary,
    coach_summary_text,
)
from handball.sim.match_simulator import simulate_ground_truth  # noqa: E402


def test_summary_has_sections_on_simulated_match():
    m = simulate_ground_truth(duration_s=20, fps=25.0, seed=3)
    data = coach_summary(m)
    assert isinstance(data["sections"], list)
    assert isinstance(data["highlights"], list)
    # A szimulált meccsen van mozgás → legalább a játékkép/tempó és a
    # kiugró játékosok szekciónak össze kell állnia.
    titles = {s["title"] for s in data["sections"]}
    assert "Kiugró játékosok" in titles
    for s in data["sections"]:
        assert s["title"] and s["body"]  # üres mondat ne kerüljön a jelentésbe


def test_player_labels_use_jersey_numbers():
    m = simulate_ground_truth(duration_s=20, fps=25.0, seed=3)
    # A szimulátor mezszámokat oszt → a mondatokban "#szám" formát várunk.
    data = coach_summary(m)
    players = [s for s in data["sections"] if s["title"] == "Kiugró játékosok"]
    assert players and "#" in players[0]["body"]


def test_summary_text_is_plain_lines():
    m = simulate_ground_truth(duration_s=20, fps=25.0, seed=5)
    text = coach_summary_text(m)
    assert text.strip()
    for line in text.splitlines():
        assert ":" in line  # "Cím: mondatok" alak


def test_api_endpoint_returns_summary(tmp_path):
    # A CI minimál-környezetében nincs FastAPI — ott ez a teszt kimarad.
    TestClient = __import__("pytest").importorskip(
        "fastapi.testclient", reason="fastapi nincs telepítve").TestClient
    import json
    os.environ["HANDBALL_DATA_DIR"] = str(tmp_path)
    from handball.api.app import create_app
    m = simulate_ground_truth(duration_s=10, fps=25.0, seed=2)
    matches_dir = tmp_path / "data" / "matches"
    matches_dir.mkdir(parents=True, exist_ok=True)
    (matches_dir / f"{m.meta.match_id}.json").write_text(
        json.dumps(m.to_dict()), encoding="utf-8")
    client = TestClient(create_app())
    r = client.get(f"/matches/{m.meta.match_id}/coach-summary")
    assert r.status_code == 200
    data = r.json()
    assert data["sections"]
    assert client.get("/matches/nincs-ilyen/coach-summary").status_code == 404


def test_empty_match_degrades_gracefully():
    m = Match(meta=MatchMeta(match_id="empty", home_team="A", away_team="B",
                             fps=25.0), frames=[])
    data = coach_summary(m)
    assert data["sections"] == []
    assert coach_summary_text(m) == ""


def test_key_players_section_lists_top_shooter():
    """A 3+ lövéses fő lövő a Kulcsemberek szekcióban is megjelenik."""
    from handball.models.tracking import (Ball, Frame, PlayerPosition,
                                          PositionSource, Team)

    def pl(tid, x, y):
        return PlayerPosition(track_id=tid, team=Team.HOME, x=x, y=y,
                              source=PositionSource.MEASURED,
                              confidence=1.0)

    frames = []
    t = 0
    for _ in range(4):
        for i in range(7):
            frames.append(Frame(t=t, players=[pl(1, 33.0, 10.0)],
                                ball=Ball(x=34.0 + i, y=10.0,
                                          confidence=1.0)))
            t += 1
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 20
    m = Match(MatchMeta(match_id="kpc", home_team="H", away_team="A",
                        fps=25.0), frames)
    data = coach_summary(m)
    sec = next((s_ for s_ in data["sections"]
                if s_["title"] == "Kulcsemberek"), None)
    assert sec is not None
    assert "fő lövő" in sec["body"]
    assert "1. játékos" in sec["body"]


def test_story_section_opens_summary():
    """2+ gólos meccsen az összefoglaló első szekciója a meccs
    története, eredménnyel."""
    from handball.models.tracking import (Ball, Frame, PlayerPosition,
                                          PositionSource, Team)

    def pl(tid, x, y):
        return PlayerPosition(track_id=tid, team=Team.HOME, x=x, y=y,
                              source=PositionSource.MEASURED,
                              confidence=1.0)

    frames = []
    t = 0
    for _ in range(3):  # 3 hazai gól
        for i in range(7):
            frames.append(Frame(t=t, players=[pl(1, 33.0, 10.0)],
                                ball=Ball(x=34.0 + i, y=10.0,
                                          confidence=1.0)))
            t += 1
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 20
    m = Match(MatchMeta(match_id="st", home_team="Hazai", away_team="Vendég",
                        fps=25.0), frames)
    data = coach_summary(m)
    first = data["sections"][0]
    assert first["title"] == "A meccs története"
    assert "Hazai nyert 3–0-ra" in first["body"]
    assert "legnagyobb különbség 3 gól" in first["body"]
    assert "A meccs embere a(z) 1. játékos" in first["body"]


def test_lineups_section_in_summary():
    """A becsült posztok az összefoglalóban is megjelennek."""
    from handball.models.tracking import (Ball, Frame, PlayerPosition,
                                          PositionSource, Team)

    def pl(tid, x, y):
        return PlayerPosition(track_id=tid, team=Team.HOME, x=x, y=y,
                              source=PositionSource.MEASURED,
                              confidence=1.0)

    frames = []
    for t in range(150):
        frames.append(Frame(t=t, players=[
            pl(1, 34.0, 10.0), pl(2, 36.0, 2.0), pl(3, 28.0, 10.0),
        ], ball=Ball(x=28.3, y=10.0, confidence=1.0)))
    m = Match(MatchMeta(match_id="lus", home_team="H", away_team="A",
                        fps=25.0), frames)
    data = coach_summary(m)
    sec = next((s_ for s_ in data["sections"]
                if s_["title"] == "Felállások (becsült posztok)"), None)
    assert sec is not None
    assert "beálló: 1." in sec["body"]


def test_story_mentions_run_at_turning_point():
    """Ha a fordulópont egy gól-sorozat közben jön, a történet a
    sorozatot is megnevezi."""
    from handball.models.tracking import (Ball, Frame, PlayerPosition,
                                          PositionSource, Team)

    def pl(tid, x, y):
        return PlayerPosition(track_id=tid, team=Team.HOME, x=x, y=y,
                              source=PositionSource.MEASURED,
                              confidence=1.0)

    frames = []
    t = 0
    for _ in range(4):  # 4 gyors hazai gól = sorozat
        for i in range(7):
            frames.append(Frame(t=t, players=[pl(1, 33.0, 10.0)],
                                ball=Ball(x=34.0 + i, y=10.0,
                                          confidence=1.0)))
            t += 1
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 20
    m = Match(MatchMeta(match_id="str", home_team="H", away_team="A",
                        fps=25.0), frames)
    data = coach_summary(m)
    first = data["sections"][0]
    assert first["title"] == "A meccs története"
    if "fordulópont" in first["body"]:
        assert "sorozat hozta" in first["body"]


def test_goalkeeper_change_verdict_sentence():
    """Kapuscserénél a szekció megmondja, bejött-e a csere: a két kapus
    GSAx-mérlege (helyzet-értékkel súlyozva) alapján ítél."""
    from handball.models.tracking import (Ball, Frame, PlayerPosition,
                                          PositionSource, Team)
    from handball.pipeline.coach_summary import _goalkeepers_section

    def gk(tid):
        return PlayerPosition(track_id=tid, team=Team.AWAY, x=39.0,
                              y=10.0, source=PositionSource.MEASURED,
                              confidence=1.0, role="kapus")

    def shooter():
        return PlayerPosition(track_id=4, team=Team.HOME, x=33.5,
                              y=10.0, source=PositionSource.MEASURED,
                              confidence=1.0)

    frames = []
    t = 0
    for _ in range(600):
        frames.append(Frame(t=t, players=[gk(9)],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    # Három védés a 9-es kapusra...
    for _ in range(3):
        for i in range(8):
            x = min(33.6 + i, 38.8)
            players = [gk(9)] + ([shooter()] if i == 0 else [])
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=x, y=10.0, confidence=1.0)))
            t += 1
        # Lövés-csendidő: valós szünet kell két kapu-megközelítés közé.
        for _i in range(20):
            frames.append(Frame(t=t, players=[gk(9)],
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
            t += 1
    # ...csere után három kapott gól a 8-asra.
    for _ in range(600):
        frames.append(Frame(t=t, players=[gk(8)],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 1
    for _ in range(3):
        for i in range(8):
            players = [gk(8)] + ([shooter()] if i == 0 else [])
            frames.append(Frame(t=t, players=players,
                                ball=Ball(x=33.6 + i, y=10.0,
                                          confidence=1.0)))
            t += 1
        for _i in range(20):
            frames.append(Frame(t=t, players=[gk(8)],
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
            t += 1
    m = Match(MatchMeta(match_id="gkv", home_team="H", away_team="A",
                        fps=25.0), frames)
    sec = _goalkeepers_section(m, "H", "A")
    assert sec is not None
    assert "kapust cserélt" in sec["body"]
    assert "nem hozott javulást" in sec["body"]


def test_suspension_offender_named_in_summary():
    """A Kiállítások szekció megnevezi a kiülőt (a hátrány alatt eltűnő
    tracket)."""
    from handball.models.tracking import (Ball, Frame, PlayerPosition,
                                          PositionSource, Team)

    def mk(t, home_tracks):
        players = [PlayerPosition(track_id=tid, team=Team.HOME,
                                  x=15.0 + (tid % 10), y=4.0 + (tid % 6),
                                  source=PositionSource.MEASURED,
                                  confidence=1.0)
                   for tid in home_tracks]
        players += [PlayerPosition(track_id=200 + k, team=Team.AWAY,
                                   x=25.0 + k, y=4.0 + k,
                                   source=PositionSource.MEASURED,
                                   confidence=1.0)
                    for k in range(6)]
        return Frame(t=t, players=players,
                     ball=Ball(x=20.0, y=10.0, confidence=1.0))

    full = [100, 101, 102, 103, 104, 105]
    down = [100, 101, 102, 103, 104]
    frames = [mk(t, full) for t in range(750)]
    frames += [mk(t, down) for t in range(750, 2250)]
    frames += [mk(t, full) for t in range(2250, 3000)]
    m = Match(MatchMeta(match_id="sus", home_team="H", away_team="A",
                        fps=25.0), frames)
    data = coach_summary(m)
    sec = next((s_ for s_ in data["sections"]
                if s_["title"] == "Kiállítások és hétméteresek"), None)
    assert sec is not None
    assert "kiülői: 105. játékos" in sec["body"]


def test_xg_verdict_sentences():
    """Az xG-ítélet: megérdemelt győzelem, helyzetek elleni győzelem,
    és a hallgatás esetei (döntetlen / kicsi xG-különbség)."""
    from handball.pipeline.coach_summary import _xg_verdict
    v = _xg_verdict({"goals": 3, "xg": 1.0}, {"goals": 2, "xg": 3.2},
                    "H", "A")
    assert v is not None and "másik oldal állt jobban" in v
    assert "H győzelmét" in v
    v2 = _xg_verdict({"goals": 4, "xg": 3.5}, {"goals": 1, "xg": 1.2},
                     "H", "A")
    assert v2 is not None and "megérdemelt" in v2 and "H" in v2
    assert _xg_verdict({"goals": 2, "xg": 3.0}, {"goals": 2, "xg": 1.0},
                       "H", "A") is None
    assert _xg_verdict({"goals": 3, "xg": 2.0}, {"goals": 1, "xg": 1.5},
                       "H", "A") is None


def test_summary_sections_are_split_into_sentences():
    """A szakaszok mondatokra bontva is elmennek — a felületek ebből
    tudnak felsorolást építeni.

    A "Játékkép és tempó" szakasz a rétegekkel négyezer karakteres,
    negyvenmondatos bekezdéssé nőtt; egy ilyet senki nem olvas el.
    A `body` változatlan (a meglévő fogyasztók miatt), a `lines` az
    új, tördelhető alak.
    """
    from handball.pipeline.coach_summary import coach_summary
    from handball.sim.match_simulator import simulate_ground_truth

    cs = coach_summary(simulate_ground_truth(duration_s=180.0, seed=7))
    assert cs["sections"], "a mintameccsen van összefoglaló"
    for sec in cs["sections"]:
        assert "lines" in sec, sec.get("title")
        # A mondatok együtt kiadják a bekezdés minden szavát — a
        # tördelés nem veszíthet szöveget.
        joined = " ".join(sec["lines"])
        assert joined.split() == sec["body"].split(), sec["title"]
    longest = max(cs["sections"], key=lambda s: len(s["lines"]))
    assert len(longest["lines"]) >= 5, longest["title"]


def test_sentence_split_keeps_decimals_together():
    """A tizedes-pont nem mondathatár (3.9 m/s egy szám marad)."""
    from handball.pipeline.coach_summary import split_sentences

    lines = split_sentences(
        "A támadásuk mozgásos volt (átlag 3.9 m/s). A fal réses volt.")
    assert len(lines) == 2, lines
    assert "3.9 m/s" in lines[0]
    assert lines[1].startswith("A fal")


def test_sentence_split_handles_empty_body():
    """Üres szakaszból üres lista lesz — nem None és nem [""]."""
    from handball.pipeline.coach_summary import split_sentences

    assert split_sentences("") == []
    assert split_sentences("   ") == []


def test_gyenge_feldolgozasnal_az_osszefoglalo_elore_szol():
    """A jelentés MAGA mondja ki, ha zajról szólnak az állításai.

    Az összefoglaló minden szekciója magabiztosan fogalmaz — így is kell
    írni egy edzői jelentést. De ha a feldolgozás gyenge volt (a nézőtér
    is a pályára került), akkor ezek a mondatok nem a meccsről szólnak.
    Ezt az EDZŐ az első szekcióban tudja meg, nem a hetedik után.
    """
    from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                          PlayerPosition, PositionSource,
                                          Team)
    from handball.pipeline.coach_summary import coach_summary

    # 27 "játékos" kockánként: a pályán legfeljebb 14 lehet.
    frames = []
    for t in range(300):
        pl = [PlayerPosition(track_id=i,
                             team=Team.HOME if i % 2 == 0 else Team.AWAY,
                             x=5.0 + (i % 10) * 3.0, y=3.0 + (i % 5) * 3.0,
                             source=PositionSource.MEASURED, confidence=1.0)
              for i in range(27)]
        frames.append(Frame(t=t, players=pl,
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    m = Match(MatchMeta(match_id="rossz", home_team="H", away_team="A",
                        fps=25.0, calibrated=True), frames)

    data = coach_summary(m)
    caveat = data.get("caveat")
    assert caveat, "gyenge feldolgozásnál nincs figyelmeztetés"
    assert "/100" in caveat
    assert "Első teendő" in caveat
    # A szekciók szerkezetét NEM tolja el: a figyelmeztetés külön mező.
    assert all(s["title"] != "Mennyire bízhatsz ebben"
               for s in data["sections"])


def test_jo_feldolgozasnal_nincs_megbizhatosag_szekcio():
    """Rendben lévő feldolgozásnál ne riogassunk."""
    from handball.pipeline.coach_summary import coach_summary
    from handball.sim.match_simulator import simulate_ground_truth

    m = simulate_ground_truth(duration_s=90, fps=10.0, seed=3)
    m.meta.calibrated = True
    assert coach_summary(m).get("caveat") is None


def test_a_jelentes_a_lenyeggel_nyit():
    """Az összefoglaló az ötszáz réteggel háromezer szavassá nőtt.

    Egy edző ezt nem olvassa végig — és a mondatokra bontás sem segít,
    ha negyven felsorolás-pont lesz belőle: a hiányzó darab a
    FONTOSSÁGI SORREND. A jelentés ezért a teendő-rangsor tetejével
    nyit, csapatonként legfeljebb hárommal, és megmondja, mennyi
    maradt a részletes szakaszokra.

    Ez BEVEZETŐ, nem rövidítés: a hosszú szakaszok utána változatlanul
    ott vannak.
    """
    m = simulate_ground_truth(duration_s=600, fps=25.0, seed=3,
                              shots_per_min=8.0)
    cs = coach_summary(m)
    cimek_mind = [s["title"] for s in cs["sections"]]
    # A meccs története marad a nyitó szakasz (rövid, kontextust ad);
    # a rangsor tüstént utána jön.
    assert cimek_mind[0] == "A meccs története"
    elso = cs["sections"][1]
    assert elso["title"] == "A lényeg"
    # Csapatonként legfeljebb 3 tétel + legfeljebb 1 "további N" sor.
    assert 1 <= len(elso["lines"]) <= 8, elso["lines"]
    assert any("/ 1. " in sor for sor in elso["lines"])
    # A részletes szakaszok megmaradnak MÖGÖTTE.
    cimek = [s["title"] for s in cs["sections"]]
    assert "Játékkép és tempó" in cimek
    assert cimek.index("A lényeg") == 1
    # ...és jóval a hosszú szakasz ELŐTT.
    assert cimek.index("A lényeg") < cimek.index("Játékkép és tempó")


def test_ures_meccsen_nincs_lenyeg_szakasz():
    """Ha egyetlen jelzés sem szólal meg, nem találunk ki lényeget —
    a szakasz egyszerűen kimarad."""
    meta = MatchMeta(match_id="ures", home_team="A", away_team="B", fps=25.0)
    cs = coach_summary(Match(meta, []))
    cimek = [s["title"] for s in cs.get("sections", [])]
    assert "A lényeg" not in cimek


def test_a_lenyeg_szakaszt_a_kliens_nem_csukja_ossze():
    """A kliens a hosszú szakaszokat öt mondat után összecsukja.

    "A lényeg" viszont pont attól lényeg, hogy EGYBEN olvasható — ha
    a nyolc tételéből ötöt mutatnánk, a rangsor vége (és a "mennyi
    maradt" sor) eltűnne. A motor ezért megjelöli a szakaszt.
    """
    m = simulate_ground_truth(duration_s=600, fps=25.0, seed=3,
                              shots_per_min=8.0)
    cs = coach_summary(m)
    lenyeg = next(s for s in cs["sections"] if s["title"] == "A lényeg")
    assert lenyeg.get("show_all") is True
    # A többi szakasz NEM kap ilyen jelölést (különben az egész
    # összecsukás értelmét vesztené) — kivéve a másik RANGSOROLT
    # szakaszt, a "Gyenge pontok"-at: ott is a sorrend a lényeg, és öt
    # sor után a második csapat tételei tűnnének el.
    rangsorolt = {"A lényeg", "Gyenge pontok"}
    tobbi = [s for s in cs["sections"] if s["title"] not in rangsorolt]
    assert not any(s.get("show_all") for s in tobbi)


def test_a_meccselemzes_kiirja_a_gyenge_pontokat():
    """A meccs összefoglalója maga mondja ki a csapatok gyenge pontjait:
    hol törhető fel a védekezésük és hogyan állítható meg a támadásuk —
    "A lényeg" után, Hol / Mivel / Miért sorokban, összecsukás nélkül;
    csapatonként és oldalanként legfeljebb WEAK_POINTS_PER_SIDE tétel."""
    from handball.pipeline.coach_summary import WEAK_POINTS_PER_SIDE

    m = simulate_ground_truth(duration_s=600, fps=25.0, seed=3,
                              shots_per_min=8.0)
    cs = coach_summary(m)
    cimek = [s["title"] for s in cs["sections"]]
    assert "Gyenge pontok" in cimek, cimek
    assert cimek.index("Gyenge pontok") == cimek.index("A lényeg") + 1
    gp = cs["sections"][cimek.index("Gyenge pontok")]
    assert gp["show_all"] is True and gp["lines"]
    assert all("Hol: " in s and "Mivel: " in s and "Miért: " in s
               for s in gp["lines"])
    assert any("védekezése így törhető fel" in s for s in gp["lines"])
    assert any("támadása így állítható meg" in s for s in gp["lines"])
    assert len(gp["lines"]) <= 4 * WEAK_POINTS_PER_SIDE


def test_ures_meccsen_nincs_gyenge_pont_szakasz():
    meta = MatchMeta(match_id="ures2", home_team="A", away_team="B", fps=25.0)
    cimek = [s["title"] for s in coach_summary(Match(meta, [])).get("sections", [])]
    assert "Gyenge pontok" not in cimek


# ---- Belső segédek közvetlenül (második kör) --------------------------------

def test_team_names_a_meccs_nevei_vagy_az_alapnevek():
    """A csapatnevek a meccs fejlécéből jönnek; hiányzó (üres) névnél
    "Hazai" / "Vendég" áll a mondatokban — nem üres hely."""
    from handball.pipeline.coach_summary import _team_names

    assert _team_names(Match(MatchMeta(match_id="n", home_team="Veszprém",
                                       away_team="Szeged", fps=25.0), [])) == (
        "Veszprém", "Szeged")
    assert _team_names(Match(MatchMeta(match_id="n", home_team="",
                                       away_team="", fps=25.0), [])) == (
        "Hazai", "Vendég")
    assert _team_names(Match(MatchMeta(match_id="n", home_team="Veszprém",
                                       away_team="", fps=25.0), [])) == (
        "Veszprém", "Vendég")


def _mezes_meccs():
    from handball.models.tracking import Frame, PlayerPosition, Team

    def kocka(t, mezek):
        return Frame(t=t, players=[
            PlayerPosition(track_id=tid, team=team, x=10.0, y=10.0,
                           jersey_number=mez)
            for tid, (team, mez) in mezek.items()], ball=None)

    return Match(MatchMeta(match_id="m", home_team="Veszprém",
                           away_team="Szeged", fps=25.0), [
        kocka(0, {1: (Team.HOME, None), 11: (Team.AWAY, 4)}),
        kocka(1, {1: (Team.HOME, 7), 11: (Team.AWAY, 14)}),
        kocka(2, {1: (Team.HOME, 17), 2: (Team.HOME, None)})])


def test_jersey_of_track_es_player_label():
    """A mezszám trackenként az ELSŐ ismert érték (a későbbi, eltérő
    olvasat nem írja felül); a játékos neve a mondatokban "csapat
    #mezszám", mezszám nélkül "csapat (N. játékos)"."""
    from handball.models.tracking import Team
    from handball.pipeline.coach_summary import (_jersey_of_track,
                                                 _player_label,
                                                 _team_of_track)

    m = _mezes_meccs()
    mez = _jersey_of_track(m)
    assert mez == {11: 4, 1: 7}
    csapat = _team_of_track(m)
    assert csapat == {1: Team.HOME, 11: Team.AWAY, 2: Team.HOME}
    assert _player_label(1, csapat, mez, "Veszprém", "Szeged") == \
        "Veszprém #7"
    assert _player_label(11, csapat, mez, "Veszprém", "Szeged") == "Szeged #4"
    assert _player_label(2, csapat, mez, "Veszprém", "Szeged") == \
        "Veszprém (2. játékos)"
    # Üres meccs: üres térképek.
    ures = Match(MatchMeta(match_id="u", home_team="H", away_team="A",
                           fps=25.0), [])
    assert _jersey_of_track(ures) == {} and _team_of_track(ures) == {}


def test_rotation_sentence_szuk_vagy_szeles_pad(monkeypatch):
    """A rotáció-mondat: 6–8 bevetett játékosnál "szűk rotáció" (fáradás
    jöhet), 11-től "széles pad"; 9–10-nél nincs mit kiemelni; 6 alatt
    (kevés mért játékos) hallgat."""
    from handball.pipeline import stats
    from handball.pipeline.coach_summary import _rotation_sentence

    def rotacio(home, away):
        monkeypatch.setattr(stats, "rotation_depth", lambda match: {
            "home": {"used": home[0], "regulars": home[1]},
            "away": {"used": away[0], "regulars": away[1]}})
        return _rotation_sentence(Match(MatchMeta(
            match_id="r", home_team="H", away_team="A", fps=25.0), []), "Veszprém",
            "Szeged")

    szoveg = rotacio((7, 6), (12, 5))
    assert szoveg == (
        " A(z) Veszprém szűk rotációval játszott (7 bevetett játékos, 6 "
        "alapember) — a hajrában fáradás jöhet. A(z) Szeged széles paddal "
        "forgatott (12 bevetett játékos).")
    assert rotacio((9, 6), (10, 6)) == ""
    assert rotacio((5, 5), (3, 3)) == ""           # kevés mért játékos
    assert "szűk rotációval" in rotacio((6, 6), (8, 7))
    assert rotacio((8, 7), (11, 6)).count("A(z)") == 2


def test_rotation_sentence_hibara_ures_es_a_valodi_reteggel(monkeypatch):
    """Ha a rotáció-réteg hibára fut, a mondat üres (nem viszi el az
    összefoglalót); a VALÓDI réteggel a mezőnevek ("used", "regulars")
    tényleg azok, amiket a mondat olvas."""
    from handball.pipeline import stats
    from handball.pipeline.coach_summary import _rotation_sentence

    m = simulate_ground_truth(duration_s=60, fps=25.0, seed=3)
    rd = stats.rotation_depth(m)
    assert {"used", "regulars"} <= set(rd["home"])
    szoveg = _rotation_sentence(m, "Hazai", "Vendég")
    assert isinstance(szoveg, str)
    for side, nev in (("home", "Hazai"), ("away", "Vendég")):
        used = rd[side]["used"]
        if 6 <= used <= 8:
            assert f"A(z) {nev} szűk rotációval" in szoveg
        elif used >= 11:
            assert f"A(z) {nev} széles paddal" in szoveg
        else:
            assert f"A(z) {nev} " not in szoveg

    def bukik(match):
        raise RuntimeError("nem megy")
    monkeypatch.setattr(stats, "rotation_depth", bukik)
    assert _rotation_sentence(m, "Hazai", "Vendég") == ""


def test_quality_caveat_gyenge_feldolgozasnal_figyelmeztet(monkeypatch):
    """Gyenge feldolgozásnál (a pontszám a küszöb alatt, vagy van első
    teendő) az összefoglaló maga mondja ki a megbízhatóságot — a
    bizonytalan labda- / pálya-rétegek nevével és az első teendővel; jó
    minőségnél és üres meccsen nincs figyelmeztetés."""
    from handball.pipeline import quality
    from handball.pipeline.coach_summary import (SUMMARY_QUALITY_WARN,
                                                 _quality_caveat)

    m = simulate_ground_truth(duration_s=10, fps=25.0, seed=3)

    def minoseg(pont, teendo=None, sorok=()):
        monkeypatch.setattr(quality, "compute_quality_report",
                            lambda match: {"score": pont,
                                           "next_action": teendo})
        monkeypatch.setattr(quality, "analysis_confidence",
                            lambda match: list(sorok))
        return _quality_caveat(m)

    assert SUMMARY_QUALITY_WARN == 50
    assert minoseg(80) is None                    # jó minőség, nincs teendő
    assert minoseg(None) is None                  # nincs pontszám
    gyenge = minoseg(35)
    assert gyenge == ("A feldolgozás minősége 35/100 — az alábbi "
                      "megállapítások ennyire megbízhatóak.")
    assert minoseg(50) is None                    # pont a küszöb: még jó
    # Jó pontszám mellett is szól, ha van első teendő.
    teendos = minoseg(80, teendo="Kalibráld újra a pályát.")
    assert teendos.endswith(" Első teendő: Kalibráld újra a pályát.")
    # A bizonytalan labda- és pálya-családok név szerint.
    sorok = [{"layer": "ball", "label": "labda-alapú rétegek",
              "available": False},
             {"layer": "court", "label": "pálya-alapú rétegek",
              "available": True},
             {"layer": "egyeb", "label": "mezszámok", "available": False}]
    nevesitett = minoseg(35, sorok=sorok)
    assert ("Ezek a réteg-családok kifejezetten bizonytalanok: labda-alapú "
            "rétegek.") in nevesitett
    assert "mezszámok" not in nevesitett and "pálya-alapú" not in nevesitett


def test_quality_caveat_ures_meccsen_none_es_a_csaladok_hibajat_turi(
        monkeypatch):
    """Üres meccsre nincs mit mondani (sem állítás, sem figyelmeztetés) —
    a minőség-jelentés meg sem hívódik; ha a réteg-családok lekérése
    hibára fut, a figyelmeztetés a pontszámmal akkor is elkészül."""
    from handball.pipeline import quality
    from handball.pipeline.coach_summary import _quality_caveat

    monkeypatch.setattr(quality, "compute_quality_report",
                        lambda match: (_ for _ in ()).throw(
                            AssertionError("üres meccsen nem kell mérni")))
    assert _quality_caveat(Match(MatchMeta(match_id="u", home_team="H",
                                           away_team="A", fps=25.0), [])) is None

    def bukik(match):
        raise RuntimeError("nem megy")
    monkeypatch.setattr(quality, "compute_quality_report",
                        lambda match: {"score": 20, "next_action": None})
    monkeypatch.setattr(quality, "analysis_confidence", bukik)
    m = simulate_ground_truth(duration_s=10, fps=25.0, seed=3)
    assert _quality_caveat(m) == ("A feldolgozás minősége 20/100 — az "
                                  "alábbi megállapítások ennyire "
                                  "megbízhatóak.")


# ---- A szakasz-törzs nagy kezdőbetűje nem kisbetűsíti a neveket -------------

def test_nagy_kezdo_csak_az_elso_betut_emeli():
    """A felsorolásból összefűzött törzs nagybetűvel kezdődik, a TÖBBI
    változatlan: a csapatnév, az "xG" és a kiemelt szó megmarad (a
    str.capitalize() ezeket kisbetűsítette)."""
    from handball.pipeline.coach_summary import _nagy_kezdo

    assert _nagy_kezdo("a(z) Szeged 40 lövést kapott; a(z) Veszprém "
                       "SZABADON hagyta (xG 5.1).") == (
        "A(z) Szeged 40 lövést kapott; a(z) Veszprém SZABADON hagyta "
        "(xG 5.1).")
    assert _nagy_kezdo("érték") == "Érték"              # ékezetes kezdőbetű
    assert _nagy_kezdo("Már nagy KEZDŐ") == "Már nagy KEZDŐ"
    assert _nagy_kezdo("7 a 6 ellen a Szeged") == "7 a 6 ellen a Szeged"
    assert _nagy_kezdo("") == ""


def _ures_meccs(home="Veszprém", away="Szeged"):
    return Match(MatchMeta(match_id="nk", home_team=home, away_team=away,
                           fps=25.0), [])


def test_a_vedekezes_szakasz_megtartja_a_csapatnevet_es_a_kiemelest(
        monkeypatch):
    """REGRESSZIÓ: a "Védekezés" törzsében a második csapat neve
    "a(z) szeged" lett, a kiemelt "SZABADON" pedig "szabadon"."""
    from handball.pipeline import defense
    from handball.pipeline.coach_summary import _defense_section

    def sor(lovesek, golok, szabad):
        return {"shots_against": lovesek, "goals_against": golok,
                "xg_against": 5.2, "free_pct": szabad, "worst_zone": None,
                "zones": {}}

    monkeypatch.setattr(defense, "defense_analysis", lambda match: {
        "home": sor(10, 6, 60.0), "away": sor(8, 3, 10.0)})
    sec, kiemelesek = _defense_section(_ures_meccs(), "Veszprém", "Szeged")
    assert sec["title"] == "Védekezés"
    assert sec["body"].startswith(
        "A(z) Veszprém 10 lövést kapott (6 gól, engedett helyzet-érték "
        "5.2); a lövők 60%-a SZABADON állt a lövésnél; a(z) Szeged 8 "
        "lövést kapott (3 gól, engedett helyzet-érték 5.2)")
    assert kiemelesek[0].startswith("Veszprém: a kapott lövések 60%-ánál")
    # Kevés kapott lövés (4 alatt) mindkét oldalon: nincs szakasz.
    monkeypatch.setattr(defense, "defense_analysis", lambda match: {
        "home": sor(3, 3, 100.0), "away": sor(0, 0, None)})
    assert _defense_section(_ures_meccs(), "Veszprém", "Szeged") == (None, [])


def test_a_kapusok_szakasz_megtartja_a_csapatnevet(monkeypatch):
    """REGRESSZIÓ: a "Kapusok" törzsében a csapatnevek kisbetűsek
    lettek ("a(z) szeged kapusára")."""
    from handball.pipeline import goalkeeper
    from handball.pipeline.coach_summary import _goalkeepers_section

    monkeypatch.setattr(goalkeeper, "goalkeeper_stats", lambda match: {
        "home": {"on_target": 10, "saves": 4, "save_pct": 40.0},
        "away": {"on_target": 8, "saves": 6, "save_pct": 75.0}})
    sec = _goalkeepers_section(_ures_meccs(), "Veszprém", "Szeged")
    assert sec["title"] == "Kapusok"
    assert sec["body"].startswith(
        "A(z) Veszprém kapusára 10 kapura tartó lövés érkezett, ebből 4 "
        "védés (40%)")
    assert ("a(z) Szeged kapusára 8 kapura tartó lövés érkezett, ebből 6 "
            "védés (75%)") in sec["body"]
    assert sec["body"].endswith(".")
    # Kaputra tartó lövés nélkül nincs szakasz (sose 0-ból mondott arány).
    monkeypatch.setattr(goalkeeper, "goalkeeper_stats", lambda match: {
        "home": {"on_target": 0, "saves": 0, "save_pct": 0.0}, "away": None})
    assert _goalkeepers_section(_ures_meccs(), "Veszprém", "Szeged") is None


def test_a_sorozatok_szakasz_megtartja_a_masodik_csapat_nevet(monkeypatch):
    """REGRESSZIÓ: több sorozatnál a második csapat neve kisbetűs lett
    ("; szeged 3 gólos sorozata")."""
    from handball.pipeline import momentum
    from handball.pipeline.coach_summary import _momentum_section

    monkeypatch.setattr(momentum, "annotate_runs", lambda match: [
        {"team": "home", "length": 4, "start_frame": 0, "end_frame": 1500,
         "score_after": (4, 0), "context": ["emberelőnyben"]},
        {"team": "away", "length": 3, "start_frame": 3000,
         "end_frame": 4500, "score_after": (4, 3)}])
    sec, kiemelesek = _momentum_section(_ures_meccs(), "Veszprém", "Szeged")
    assert sec["title"] == "Sorozatok"
    assert sec["body"].startswith(
        "Veszprém 4 gólos sorozata a 0:00–1:00 között (állás utána 4–0) — "
        "emberelőnyben; Szeged 3 gólos sorozata a 2:00–3:00 között (állás "
        "utána 4–3).")
    assert kiemelesek == [
        "Veszprém 4 gólos sorozatot futott — nézd vissza, mi működött, és "
        "a másik oldalon hol akadt el a játék (időkérés, "
        "védekezés-váltás)."]
    # Sorozat és fordulás nélkül nincs szakasz.
    monkeypatch.setattr(momentum, "annotate_runs", lambda match: [])
    assert _momentum_section(_ures_meccs(), "Veszprém", "Szeged") == (
        None, [])


def test_az_osszefoglalo_belso_szakaszai_megtartjak_a_csapatnevet(
        monkeypatch):
    """REGRESSZIÓ az összefoglalóban helyben épülő három szakaszra
    (Támadás-hatékonyság, Cserék, Kiállítások és hétméteresek): a
    második csapat neve nem lesz kisbetűs."""
    from handball.pipeline import attack_types, rules, substitutions

    monkeypatch.setattr(attack_types, "attack_efficiency", lambda match: {
        "home": {"gyors indítás": {"attacks": 4, "goals": 3,
                                   "goal_pct": 75.0}},
        "away": {"felállt támadás": {"attacks": 5, "goals": 2,
                                     "goal_pct": 40.0},
                 "gyors indítás": {"attacks": 2, "goals": 2,
                                   "goal_pct": 100.0}}})
    monkeypatch.setattr(substitutions, "substitution_impact", lambda match: {
        "teams": {"home": {"rotations": 3, "goals_for_after": 2,
                           "goals_against_after": 1},
                  "away": {"rotations": 2, "goals_for_after": 0,
                           "goals_against_after": 4}}})
    monkeypatch.setattr(rules, "powerplay_efficiency", lambda match: {
        "home": {"pp_goals": 3, "pp_shots": 5, "pp_eff_pct": 60.0,
                 "eq_shots": 0, "eq_eff_pct": 0.0},
        "away": {"pp_goals": 1, "pp_shots": 4, "pp_eff_pct": 25.0,
                 "eq_shots": 0, "eq_eff_pct": 0.0}})
    torzs = {s["title"]: s["body"]
             for s in coach_summary(_ures_meccs())["sections"]}
    # A 2 támadásos típus (kevés minta) nem lehet a "leghatékonyabb".
    assert torzs["Támadás-hatékonyság"] == (
        "Veszprém leghatékonyabb támadás-típusa a gyors indítás (3/4 gól, "
        "75%); Szeged leghatékonyabb támadás-típusa a felállt támadás "
        "(2/5 gól, 40%).")
    assert torzs["Cserék"] == (
        "A(z) Veszprém 3 cserehullámot futott; a cseréket követő másfél "
        "percben 2 dobott és 1 kapott gól; a(z) Szeged 2 cserehullámot "
        "futott; a cseréket követő másfél percben 0 dobott és 4 kapott "
        "gól.")
    assert torzs["Kiállítások és hétméteresek"] == (
        "A(z) Veszprém emberelőnyben 3 gólt dobott 5 kapura tartó "
        "lövésből (60%) · a(z) Szeged emberelőnyben 1 gólt dobott 4 "
        "kapura tartó lövésből (25%).")


def test_a_valodi_osszefoglaloban_nincs_kisbetus_csapatnev():
    """ŐR a valódi láncon: szimulált meccs összefoglalójában egyetlen
    szakasz és kiemelés sem írja kisbetűvel a csapatnevet, a "Védekezés"
    megtartja a kiemelt szót, és minden törzs nagybetűvel (vagy
    számmal) kezdődik."""
    m = simulate_ground_truth(duration_s=300, fps=25.0, seed=1,
                              shots_per_min=8)
    m.meta.home_team, m.meta.away_team = "Veszprém", "Szeged"
    adat = coach_summary(m)
    torzs = {s["title"]: s["body"] for s in adat["sections"]}
    assert {"Védekezés", "Kapusok", "Sorozatok"} <= set(torzs)
    for cim, szoveg in torzs.items():
        assert "veszprém" not in szoveg and "szeged" not in szoveg, cim
        assert szoveg[:1] == szoveg[:1].upper(), cim
    for sor in adat["highlights"]:
        assert "veszprém" not in sor and "szeged" not in sor, sor
    ved = torzs["Védekezés"]
    assert ved.startswith("A(z) Szeged ") and "SZABADON állt" in ved
    assert "a(z) Veszprém " in ved


# ---- A szakasz-építők közvetlenül (harmadik kör) ----------------------------

def _xg_csapat(lovesek, golok, ertek, atlag):
    return {"shots": lovesek, "goals": golok, "xg": ertek,
            "avg_xg_per_shot": atlag, "diff": round(golok - ertek, 2)}


def test_xg_section_helyzetminoseg_mondatai(monkeypatch):
    """Helyzetminőség: a két csapat várható gólja és a tényleges gólok,
    a helyzet-minőség és a befejezés ítélete csapatonként, a győzelem
    megérdemeltsége, és a helyzetei felett / alatt teljesítő lövő — a
    3-nál kevesebb lövésű játékos nem kerül név szerint elő."""
    from handball.pipeline import xg
    from handball.pipeline.coach_summary import _xg_section

    eredmeny = {
        "teams": {"home": _xg_csapat(10, 8, 6.0, 0.5),
                  "away": _xg_csapat(9, 2, 3.0, 0.25)},
        "shooters": [
            {"player_id": 1, "team": "home", "shots": 4, "goals": 4,
             "xg": 2.0, "diff": 2.0},
            {"player_id": 11, "team": "away", "shots": 5, "goals": 0,
             "xg": 1.5, "diff": -1.5},
            # Két lövésből nincs értelmes kép — akármilyen nagy a többlet.
            {"player_id": 2, "team": "home", "shots": 2, "goals": 2,
             "xg": 0.2, "diff": 1.8}]}
    monkeypatch.setattr(xg, "match_xg", lambda match: eredmeny)
    monkeypatch.setattr(xg, "finishing_balance", lambda match: {
        "home": {"verdict": None}, "away": {"verdict": None}})
    vart = (
        "A kidolgozott helyzetek értéke (várható gól) Veszprém 6.0 – 3.0 "
        "Szeged, a tényleges gólok: 8 : 2."
        " A(z) Veszprém jó helyzeteket alakított ki (átlag 0.50 xG/lövés)."
        " A(z) Veszprém a helyzeteinél többet ért el (+2.0) — pontos "
        "befejezés."
        " A(z) Szeged sok kis esélyű lövést vállalt (átlag 0.25 xG/lövés)."
        " A(z) Szeged elpuskázott helyzeteket (-1.0) — a befejezésen "
        "érdemes dolgozni."
        " A(z) Veszprém győzelme a helyzetek alapján is megérdemelt."
        " A helyzetei felett teljesített: Veszprém #7 (4 gól, várható 2.0)."
        " A legtöbb kihagyott nagy helyzet: Szeged #4 (0 gól, várható 1.5).")
    assert _xg_section(_mezes_meccs(), "Veszprém", "Szeged") == {
        "title": "Helyzetminőség", "body": vart}

    # A befejezés-mérleg mondata (ha a réteg ítél) a csapat-mondatok után
    # jön; a réteg hibája nem viszi el a szakaszt.
    monkeypatch.setattr(xg, "finishing_balance", lambda match: {
        "home": {"verdict": "szebb", "diff": 2.0, "goals": 8, "xg": 6.0},
        "away": {"verdict": "kevesebb", "diff": -1.0, "goals": 2, "xg": 3.0}})
    merleggel = _xg_section(_mezes_meccs(), "Veszprém", "Szeged")["body"]
    assert (" A(z) Veszprém gólszáma szebb a játékánál (8 gól 6.0 várható "
            "gólra)") in merleggel
    assert (" A(z) Szeged a játékánál kevesebbet szerzett (2 gól 3.0 "
            "várható gólra)") in merleggel

    def bukik(match):
        raise RuntimeError("nem megy")
    monkeypatch.setattr(xg, "finishing_balance", bukik)
    assert _xg_section(_mezes_meccs(), "Veszprém", "Szeged")["body"] == vart


def test_xg_section_keves_lovesbol_none_es_kiegyenlitett_meccsen_rovid(
        monkeypatch):
    """Kevés minta → None: 4-nél kevesebb lövésből nincs helyzet-kép.
    Kiegyenlített számoknál csak az alap-mondat marad (nincs ítélet)."""
    from handball.pipeline import xg
    from handball.pipeline.coach_summary import _xg_section

    monkeypatch.setattr(xg, "finishing_balance", lambda match: {
        "home": {"verdict": None}, "away": {"verdict": None}})
    monkeypatch.setattr(xg, "match_xg", lambda match: {
        "teams": {"home": _xg_csapat(2, 2, 1.0, 0.5),
                  "away": _xg_csapat(1, 0, 0.3, 0.3)}, "shooters": []})
    assert _xg_section(_mezes_meccs(), "Veszprém", "Szeged") is None
    monkeypatch.setattr(xg, "match_xg", lambda match: {
        "teams": {"home": _xg_csapat(6, 2, 2.1, 0.35),
                  "away": _xg_csapat(5, 2, 1.9, 0.38)}, "shooters": []})
    assert _xg_section(_mezes_meccs(), "Veszprém", "Szeged")["body"] == (
        "A kidolgozott helyzetek értéke (várható gól) Veszprém 2.1 – 1.9 "
        "Szeged, a tényleges gólok: 2 : 2.")


def test_xg_section_a_valodi_reteg_szamaival():
    """A VALÓDI úton: a szakasz a match_xg csapat-számaival nyit (a
    mezőnevek tényleg azok, amiket a mondat olvas); üres meccsen None."""
    from handball.pipeline.coach_summary import _xg_section
    from handball.pipeline.xg import match_xg

    m = simulate_ground_truth(duration_s=120, fps=25.0, seed=1,
                              shots_per_min=8)
    r = match_xg(m)["teams"]
    assert r["home"]["shots"] + r["away"]["shots"] >= 4
    sec = _xg_section(m, "Veszprém", "Szeged")
    assert sec["title"] == "Helyzetminőség"
    assert sec["body"].startswith(
        "A kidolgozott helyzetek értéke (várható gól) Veszprém "
        f"{r['home']['xg']:.1f} – {r['away']['xg']:.1f} Szeged, a "
        f"tényleges gólok: {r['home']['goals']} : {r['away']['goals']}.")
    ures = Match(MatchMeta(match_id="u", home_team="H", away_team="A",
                           fps=25.0), [])
    assert _xg_section(ures, "H", "A") is None


def test_style_section_a_jatekkep_nyito_mondatai(monkeypatch):
    """Játékkép és tempó: a birtoklás-szakaszok száma és az átlagos
    támadás-hossz, az átmenetek aránya (25%-tól "fel-le hullámzó"), a
    leggyakoribb védekezési forma, a végén a labdabirtoklás-arány (ha
    az 50–50-től legalább 5 ponttal eltér). Birtoklás nélkül None."""
    import handball.pipeline.coach_summary as cs
    from handball.pipeline import stats

    ures = Match(MatchMeta(match_id="u", home_team="Veszprém",
                           away_team="Szeged", fps=25.0), [])
    assert cs._style_section(ures, "Veszprém", "Szeged") is None

    def profil(atmenet, formak):
        return {"tempo": {"possessions": 20, "avg_attack_duration_s": 28.4,
                          "transition_pct": atmenet},
                "defense_formations": formak}

    monkeypatch.setattr(cs, "team_style_profile", lambda match: profil(
        30.0, {"home": "6-0", "away": "—"}))
    monkeypatch.setattr(stats, "possession_share", lambda match: {
        "home": {"pct": 60.0}, "away": {"pct": 40.0}})
    sec = cs._style_section(ures, "Veszprém", "Szeged")
    assert sec["title"] == "Játékkép és tempó"
    assert sec["body"].startswith(
        "A felvételen 20 labdabirtoklási szakasz látszik, egy támadás "
        "átlagosan 28 másodpercig tartott. Az idő 30%-a átmenet "
        "(visszarendeződés/indítás) volt — gyors, fel-le hullámzó játék. "
        "Leggyakoribb védekezési forma — Veszprém: 6-0.")
    assert " Labdabirtoklás: Veszprém 60% – 40% Szeged." in sec["body"]
    # Kevés átmenet: felállt védelem elleni játék; kiegyenlített
    # birtoklásnál (52–48) nincs birtoklás-mondat.
    monkeypatch.setattr(cs, "team_style_profile", lambda match: profil(
        12.0, {}))
    monkeypatch.setattr(stats, "possession_share", lambda match: {
        "home": {"pct": 52.0}, "away": {"pct": 48.0}})
    lassu = cs._style_section(ures, "Veszprém", "Szeged")["body"]
    assert lassu.startswith(
        "A felvételen 20 labdabirtoklási szakasz látszik, egy támadás "
        "átlagosan 28 másodpercig tartott. Az átmenetek aránya 12% — "
        "inkább felállt védelem elleni játék.")
    assert "Labdabirtoklás" not in lassu and "védekezési forma" not in lassu


def test_style_section_a_valodi_profil_szamaival():
    """A VALÓDI úton: a szakasz a team_style_profile tempó-számaival
    nyit (a mezőnevek élnek)."""
    from handball.pipeline.coach_summary import _style_section
    from handball.pipeline.tactics import team_style_profile

    m = simulate_ground_truth(duration_s=60, fps=25.0, seed=3)
    tempo = team_style_profile(m)["tempo"]
    assert tempo["possessions"] > 0
    sec = _style_section(m, "Hazai", "Vendég")
    assert sec["title"] == "Játékkép és tempó"
    assert sec["body"].startswith(
        f"A felvételen {tempo['possessions']} labdabirtoklási szakasz "
        "látszik, egy támadás átlagosan "
        f"{tempo['avg_attack_duration_s']:.0f} másodpercig tartott.")


def _intenzitas_forrasok(monkeypatch, hazai, vendeg, bevetett=9):
    """Az intenzitás-szakasz forrásai kézzel: ablakonkénti átlagsebesség
    csapatonként; a lövőerő és a rotáció semleges (nincs mondatuk)."""
    import handball.pipeline.coach_summary as cs
    from handball.pipeline import event_detection, stats

    monkeypatch.setattr(cs, "compute_intensity_timeline", lambda match: [
        {"home_avg_ms": h, "away_avg_ms": a} for h, a in zip(hazai, vendeg)])
    monkeypatch.setattr(event_detection, "shot_speed_fade", lambda match: {
        "home": {"drop_pct": None}, "away": {"drop_pct": None}})
    monkeypatch.setattr(stats, "rotation_depth", lambda match: {
        "home": {"used": bevetett, "regulars": 6},
        "away": {"used": bevetett, "regulars": 6}})


def test_intensity_section_eses_felporges_es_kiegyensulyozott(monkeypatch):
    """Kezdés vs hajrá: az első és az utolsó harmad átlaga csapatonként —
    12%-nál nagyobb esés (figyelmeztetéssel a "mire nézz rá" listán),
    ugyanekkora felpörgés, vagy kiegyensúlyozott tempó."""
    from handball.pipeline.coach_summary import (INTENSITY_DROP_WARN_PCT,
                                                 _intensity_section)

    assert INTENSITY_DROP_WARN_PCT == 12.0
    m = Match(MatchMeta(match_id="i", home_team="Veszprém",
                        away_team="Szeged", fps=25.0), [])
    _intenzitas_forrasok(monkeypatch,
                         hazai=[4.0, 4.0, 3.5, 3.5, 3.0, 3.0],
                         vendeg=[3.0, 3.0, 3.2, 3.2, 3.6, 3.6])
    sec, kiemelesek = _intensity_section(m, "Veszprém", "Szeged")
    assert sec == {"title": "Intenzitás", "body": (
        "Kezdés és hajrá összevetése: a(z) Veszprém intenzitása a hajrára "
        "25%-kal esett (4.00 → 3.00 m/s); a(z) Szeged a hajrában 20%-kal "
        "pörgött fel (3.00 → 3.60 m/s).")}
    assert kiemelesek == [
        "Veszprém: jelentős intenzitás-esés a meccs végére (25%) — érdemes "
        "a cserék időzítésére ránézni."]
    # 10%-os esés még a küszöb alatt: kiegyensúlyozott, kiemelés nélkül.
    _intenzitas_forrasok(monkeypatch, hazai=[4.0, 4.0, 3.6],
                         vendeg=[3.0, 3.1, 3.0])
    sec, kiemelesek = _intensity_section(m, "Veszprém", "Szeged")
    assert sec["body"] == (
        "Kezdés és hajrá összevetése: a(z) Veszprém tempója végig "
        "kiegyensúlyozott volt (~4.00 m/s); a(z) Szeged tempója végig "
        "kiegyensúlyozott volt (~3.00 m/s).")
    assert kiemelesek == []
    # A rotáció-mondat a szakasz végére kerül (szűk pad: 7 bevetett).
    _intenzitas_forrasok(monkeypatch, hazai=[4.0, 4.0, 4.0],
                         vendeg=[3.0, 3.0, 3.0], bevetett=7)
    sec, _ = _intensity_section(m, "Veszprém", "Szeged")
    assert sec["body"].endswith(
        " A(z) Szeged szűk rotációval játszott (7 bevetett játékos, 6 "
        "alapember) — a hajrában fáradás jöhet.")


def test_intensity_section_keves_ablakbol_none(monkeypatch):
    """Kevés minta → None: három használható ablak alatt nincs mit
    összevetni; a csak az egyik csapatra mért ablakokból csak arról a
    csapatról szól; ha egyik csapatra sincs kezdés ÉS hajrá, None."""
    from handball.pipeline.coach_summary import _intensity_section

    m = Match(MatchMeta(match_id="i", home_team="Veszprém",
                        away_team="Szeged", fps=25.0), [])
    _intenzitas_forrasok(monkeypatch, hazai=[4.0, 3.0], vendeg=[3.0, 3.0])
    assert _intensity_section(m, "Veszprém", "Szeged") == (None, [])
    # A nulla-ablak (senkit nem mértünk) nem számít használhatónak.
    _intenzitas_forrasok(monkeypatch, hazai=[4.0, 0.0, 0.0, 3.0],
                         vendeg=[3.0, 0.0, 0.0, 3.0])
    assert _intensity_section(m, "Veszprém", "Szeged") == (None, [])
    # A vendégre nincs mérés: csak a hazairól van mondat.
    _intenzitas_forrasok(monkeypatch, hazai=[4.0, 4.0, 4.0],
                         vendeg=[0.0, 0.0, 0.0])
    sec, _ = _intensity_section(m, "Veszprém", "Szeged")
    assert sec["body"] == ("Kezdés és hajrá összevetése: a(z) Veszprém "
                           "tempója végig kiegyensúlyozott volt (~4.00 m/s).")
    # A hazaira csak a kezdésre, a vendégre csak a hajrára van mérés.
    _intenzitas_forrasok(monkeypatch, hazai=[4.0, 4.0, 0.0],
                         vendeg=[0.0, 3.0, 3.0])
    assert _intensity_section(m, "Veszprém", "Szeged") == (None, [])


def test_intensity_section_a_valodi_idovonalbol():
    """A VALÓDI úton: szimulált meccsen a szakasz a valódi intenzitás-
    idővonalból készül, és mindkét csapatról szól."""
    from handball.pipeline.coach_summary import _intensity_section
    from handball.pipeline.stats import compute_intensity_timeline

    m = simulate_ground_truth(duration_s=300, fps=25.0, seed=1)
    ablakok = compute_intensity_timeline(m)
    assert len([w for w in ablakok
                if w["home_avg_ms"] > 0 or w["away_avg_ms"] > 0]) >= 3
    sec, kiemelesek = _intensity_section(m, "Veszprém", "Szeged")
    assert sec["title"] == "Intenzitás"
    assert sec["body"].startswith("Kezdés és hajrá összevetése: a(z) "
                                  "Veszprém ")
    assert "a(z) Szeged " in sec["body"]
    assert isinstance(kiemelesek, list)


def test_players_section_a_kiugro_jatekosok_a_valodi_statisztikabol():
    """Kiugró játékosok: a legtöbbet futó és a leggyorsabb játékos a
    VALÓDI játékos-statisztikából (csak a legalább ~10 mp-ig mért
    játékosok közül), a csapat és a mezszám nevével."""
    from handball.pipeline.coach_summary import (_jersey_of_track,
                                                 _player_label,
                                                 _players_section,
                                                 _team_of_track)
    from handball.pipeline.stats import compute_player_stats

    m = simulate_ground_truth(duration_s=60, fps=25.0, seed=3)
    stat = {t: s for t, s in compute_player_stats(m).items()
            if s.measured_frames >= 250}
    assert stat
    csapat, mez = _team_of_track(m), _jersey_of_track(m)

    def nev(tid):
        return _player_label(tid, csapat, mez, "Veszprém", "Szeged")

    futo = max(stat.items(), key=lambda kv: kv[1].distance_m)
    gyors = max(stat.items(), key=lambda kv: kv[1].top_speed_ms)
    sec = _players_section(m, "Veszprém", "Szeged")
    assert sec["title"] == "Kiugró játékosok"
    assert sec["body"].startswith(
        f"Legtöbbet futott: {nev(futo[0])} ({futo[1].distance_m:.0f} m). "
        f"Legnagyobb sebesség: {nev(gyors[0])} "
        f"({gyors[1].top_speed_ms * 3.6:.1f} km/h).")


def test_players_section_keves_mert_jelenletbol_none():
    """Kevés minta → None: ha senki sincs legalább ~10 másodpercig mérve
    (rövid klip, üres meccs), nincs "kiugró játékos" — ne egy zajos,
    villanásnyi track vezesse a listát. A küszöb IDŐ: 12,5 fps-en fele
    annyi kocka elég."""
    from handball.models.tracking import Frame, PlayerPosition, Team
    from handball.pipeline.coach_summary import _players_section

    def meccs(kockak, fps):
        return Match(MatchMeta(match_id="p", home_team="H", away_team="A",
                               fps=fps), [
            Frame(t=t, players=[PlayerPosition(
                track_id=1, team=Team.HOME, x=10.0 + 0.1 * (t % 50),
                y=10.0, jersey_number=7)], ball=None)
            for t in range(kockak)])

    assert _players_section(meccs(0, 25.0), "H", "A") is None
    assert _players_section(meccs(200, 25.0), "H", "A") is None   # 8 mp
    hosszu = _players_section(meccs(300, 25.0), "H", "A")         # 12 mp
    assert hosszu["body"].startswith("Legtöbbet futott: H #7 (")
    # Ugyanaz a 200 kocka 12,5 fps-en már 16 mp: elég.
    assert _players_section(meccs(200, 12.5), "H", "A") is not None


def _tortenet_forrasok(monkeypatch, vegeredmeny, felido=None,
                       legnagyobb=None, fordulasok=0):
    from handball.pipeline import halftime, momentum, xg

    monkeypatch.setattr(momentum, "score_progression", lambda match: {
        "final": vegeredmeny, "biggest_lead": legnagyobb or {},
        "lead_changes": fordulasok})
    monkeypatch.setattr(momentum, "halftime_score", lambda match: felido)
    monkeypatch.setattr(momentum, "win_probability",
                        lambda match: {"turning_point": None})
    monkeypatch.setattr(momentum, "opening_profile", lambda match: {
        "home": {"scores_first": None, "early_goals_seen": 0}})
    monkeypatch.setattr(halftime, "second_half_start", lambda match: None)
    monkeypatch.setattr(xg, "match_xg", lambda match: {"shooters": []})


def test_story_section_a_meccs_tortenete_egy_bekezdesben(monkeypatch):
    """A meccs története: a győztes és az eredmény (félidővel), a
    legnagyobb különbség (3 góltól) és a vezetés-váltások (3-tól) — a
    vendég győzelménél az ő nevével és az ő góljaival elöl, döntetlennél
    győztes nélkül."""
    from handball.pipeline.coach_summary import _story_section

    m = Match(MatchMeta(match_id="s", home_team="Veszprém",
                        away_team="Szeged", fps=25.0), [])
    _tortenet_forrasok(monkeypatch, (25, 20), felido={"home": 12, "away": 11},
                       legnagyobb={"home": 6, "away": 1}, fordulasok=4)
    assert _story_section(m, "Veszprém", "Szeged") == {
        "title": "A meccs története", "body": (
            "A(z) Veszprém nyert 25–20-ra a(z) Szeged ellen (félidőben "
            "12–11). A legnagyobb különbség 6 gól volt (Veszprém). A "
            "vezetés 4× cserélt gazdát — végig szoros meccs volt.")}
    _tortenet_forrasok(monkeypatch, (20, 24),
                       legnagyobb={"home": 2, "away": 5})
    assert _story_section(m, "Veszprém", "Szeged")["body"] == (
        "A(z) Szeged nyert 24–20-ra a(z) Veszprém ellen. A legnagyobb "
        "különbség 5 gól volt (Szeged).")
    _tortenet_forrasok(monkeypatch, (22, 22),
                       legnagyobb={"home": 2, "away": 2}, fordulasok=2)
    assert _story_section(m, "Veszprém", "Szeged")["body"] == (
        "Döntetlen: 22–22.")


def test_story_section_ket_gol_alatt_none(monkeypatch):
    """Kevés minta → None: két gólnál kevesebből nincs "történet" (a
    0–0-s vagy 1–0-s töredék-felvételre ne mondjunk győztest)."""
    from handball.pipeline.coach_summary import _story_section

    m = Match(MatchMeta(match_id="s", home_team="Veszprém",
                        away_team="Szeged", fps=25.0), [])
    for vegeredmeny in ((0, 0), (1, 0), (0, 1)):
        _tortenet_forrasok(monkeypatch, vegeredmeny)
        assert _story_section(m, "Veszprém", "Szeged") is None
    _tortenet_forrasok(monkeypatch, (1, 1))
    assert _story_section(m, "Veszprém", "Szeged")["body"] == (
        "Döntetlen: 1–1.")


def test_weak_points_section_hol_mivel_miert_sorok(monkeypatch):
    """Gyenge pontok: csapatonként a védekezés feltörése és a támadás
    megállítása, tételenként egy sor ("Hol — Mivel (Miért)"), a rangsor
    sorszámával; a szakasz nem csukható össze. A motortól csapatonként
    WEAK_POINTS_PER_SIDE tételt kér."""
    from handball.pipeline import court3d
    from handball.pipeline.coach_summary import (WEAK_POINTS_PER_SIDE,
                                                 _weak_points_section)

    keres = {}

    def kulcsok(match, top):
        keres["top"] = top
        return {
            "breakpoints": {
                "home": [{"hol": "a bal szélen", "mivel": "szélső befutás",
                          "miert": "5 gól innen"}],
                "away": []},
            "stoppers": {
                "home": [],
                "away": [{"hol": "a 9-esük", "mivel": "szoros őrzés",
                          "miert": "a gólok 40%-a"},
                         {"hol": "a beállójuk", "mivel": "elé lépés",
                          "miert": "8 lövés a hatosról"}]}}

    monkeypatch.setattr(court3d, "tactical_keys_by_team", kulcsok)
    m = Match(MatchMeta(match_id="g", home_team="Veszprém",
                        away_team="Szeged", fps=25.0), [])
    sec = _weak_points_section(m, "Veszprém", "Szeged")
    assert keres["top"] == WEAK_POINTS_PER_SIDE == 3
    assert sec["title"] == "Gyenge pontok" and sec["show_all"] is True
    assert sec["lines"] == [
        "Veszprém védekezése így törhető fel / 1. Hol: a bal szélen — "
        "Mivel: szélső befutás (Miért: 5 gól innen)",
        "Szeged támadása így állítható meg / 1. Hol: a 9-esük — Mivel: "
        "szoros őrzés (Miért: a gólok 40%-a)",
        "Szeged támadása így állítható meg / 2. Hol: a beállójuk — Mivel: "
        "elé lépés (Miért: 8 lövés a hatosról)"]
    assert sec["body"] == " ".join(sec["lines"])


def test_weak_points_section_minta_nelkul_none(monkeypatch):
    """Kevés minta → None: ha egyik csapatra sincs tétel (üres vagy
    hiányzó lista), nincs szakasz — sose 0-ból mondott ítélet."""
    from handball.pipeline import court3d
    from handball.pipeline.coach_summary import _weak_points_section

    m = Match(MatchMeta(match_id="g", home_team="H", away_team="A",
                        fps=25.0), [])
    monkeypatch.setattr(court3d, "tactical_keys_by_team",
                        lambda match, top: {
                            "breakpoints": {"home": [], "away": []},
                            "stoppers": {"home": [], "away": None}})
    assert _weak_points_section(m, "H", "A") is None
    monkeypatch.setattr(court3d, "tactical_keys_by_team",
                        lambda match, top: {"breakpoints": {},
                                            "stoppers": {}})
    assert _weak_points_section(m, "H", "A") is None


def test_coach_summary_cached_ugyanaz_a_hatokorben_es_anelkul():
    """A coach_summary az alap-méréseket gyorsítótárazó hatókörben
    futtatja a tényleges építőt (_coach_summary_cached): az eredmény
    ugyanaz, mint a hatókör nélkül — a gyorsítótár csak gyorsít. A
    válasz alakja: szakaszok (mondatokra bontva is), kiemelések, és a
    két külön mező (megbízhatóság, klip-jelzés)."""
    from handball.pipeline.coach_summary import _coach_summary_cached

    m = simulate_ground_truth(duration_s=20, fps=25.0, seed=3)
    hatokorben = coach_summary(m)
    nyersen = _coach_summary_cached(m)
    assert hatokorben == nyersen
    assert set(nyersen) == {"sections", "highlights", "caveat", "clip_note"}
    assert nyersen["sections"]
    for sec in nyersen["sections"]:
        assert sec["title"] and sec["body"] and sec["lines"]
        assert all(isinstance(s, str) and s for s in sec["lines"])


def test_coach_summary_cached_egy_szakasz_hibaja_nem_viszi_el_a_tobbit(
        monkeypatch):
    """Egy szakasz-építő hibája (kivétel) csak azt az egy szakaszt
    hagyja ki: a többi szakasz és a kiemelések megmaradnak, a hívó nem
    kap kivételt."""
    import handball.pipeline.coach_summary as cs

    m = simulate_ground_truth(duration_s=60, fps=25.0, seed=3)
    teljes = cs.coach_summary(m)       # a hatókörben a _coach_summary_cached
    cimek = [s["title"] for s in teljes["sections"]]
    assert "Játékkép és tempó" in cimek and "Intenzitás" in cimek

    def bukik(match, home, away):
        raise RuntimeError("ez a szakasz most nem megy")
    monkeypatch.setattr(cs, "_style_section", bukik)
    monkeypatch.setattr(cs, "_intensity_section", bukik)
    csonka = cs.coach_summary(m)
    csonka_cimek = [s["title"] for s in csonka["sections"]]
    assert "Játékkép és tempó" not in csonka_cimek
    assert "Intenzitás" not in csonka_cimek
    # Ami nem ezekből a szakaszokból jön, az érintetlen.
    megmaradt = {s["title"]: s["body"] for s in teljes["sections"]
                 if s["title"] not in ("Játékkép és tempó", "Intenzitás",
                                       "A lényeg")}
    for sec in csonka["sections"]:
        if sec["title"] in megmaradt:
            assert sec["body"] == megmaradt[sec["title"]], sec["title"]
    assert set(megmaradt) - {"A lényeg"} <= set(csonka_cimek)


# ---- Fordulásos, de sorozat nélküli meccs: a "Sorozatok" szakasz megmarad ---

def _golos_meccs(sorrend):
    """Gólok a megadott sorrendben: "H" = hazai gól a +x kapuba, "A" =
    vendég gól a x=0 kapuba; minden gól után középkezdés."""
    from handball.models.tracking import (Ball, Frame, PlayerPosition,
                                          PositionSource, Team)

    def jatekos(tid, csapat, x):
        return PlayerPosition(track_id=tid, team=csapat, x=x, y=10.0,
                              source=PositionSource.MEASURED, confidence=1.0)

    frames, t = [], 0
    for ki in sorrend:
        for i in range(7):
            if ki == "H":
                frames.append(Frame(
                    t=t, players=[jatekos(1, Team.HOME, 33.0)],
                    ball=Ball(x=34.0 + i, y=10.0, confidence=1.0)))
            else:
                frames.append(Frame(
                    t=t, players=[jatekos(11, Team.AWAY, 7.0)],
                    ball=Ball(x=6.0 - i, y=10.0, confidence=1.0)))
            t += 1
        frames.append(Frame(t=t, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
        t += 20
    return Match(MatchMeta(match_id="fordulas", home_team="Veszprém",
                           away_team="Szeged", fps=25.0), frames)


def test_a_sorozatok_szakasz_sorozat_nelkuli_fordulasos_meccsen_is_megszolal():
    """REGRESSZIÓ a valódi úton: szoros, oda-vissza meccsen (a vezetés
    többször fordul, de egyik csapat sem lő három gólt válasz nélkül) a
    szakasz a fordulásokról szól. Korábban az üres sorozat-listán hívott
    max() kivétele az EGÉSZ szakaszt elvitte — a hívó try/except-je
    elnyelte, az összefoglalóból a szakasz némán kimaradt."""
    from handball.pipeline.coach_summary import _momentum_section
    from handball.pipeline.momentum import (RUN_MIN, annotate_runs,
                                            score_progression)

    m = _golos_meccs("HAAHH")                 # 1–0, 1–1, 1–2, 2–2, 3–2
    assert RUN_MIN == 3 and annotate_runs(m) == []
    allas = score_progression(m)
    assert allas["final"] == [3, 2] and allas["lead_changes"] == 2
    sec, kiemelesek = _momentum_section(m, "Veszprém", "Szeged")
    assert sec["title"] == "Sorozatok"
    assert sec["body"].startswith(
        "A meccs 2-szor fordult; a legnagyobb előny Veszprém javára 1 gól.")
    assert kiemelesek == []        # sorozat nélkül nincs sorozat-kiemelés
    # A teljes összefoglalóban is megvan a szakasz.
    torzs = {s["title"]: s["body"] for s in coach_summary(m)["sections"]}
    assert torzs["Sorozatok"] == sec["body"]


def test_a_sorozatok_szakasz_sorozattal_es_fordulassal_vagy_egyik_nelkul():
    """A szakasz három esete a valódi rétegekkel: sorozat ÉS fordulás (a
    sorozat-mondat után a fordulás-mondat, kiemeléssel), csak sorozat,
    és se sorozat, se fordulás (nincs szakasz — sose üres törzs)."""
    from handball.pipeline.coach_summary import _momentum_section

    # 3–0 után négy vendég gól: két sorozat, egy fordulás.
    mindketto, kiemelesek = _momentum_section(_golos_meccs("HHHAAAA"),
                                              "Veszprém", "Szeged")
    assert mindketto["body"].startswith(
        "Veszprém 3 gólos sorozata a 0:00–0:02 között (állás utána 3–0); "
        "Szeged 4 gólos sorozata a ")
    assert (" A meccs 1-szor fordult; a legnagyobb előny Veszprém javára "
            "3 gól.") in mindketto["body"]
    assert kiemelesek[0].startswith("Szeged 4 gólos sorozatot futott")
    # ...és az elengedett háromgólos előny is kiemelést kap.
    assert kiemelesek[1].startswith("Veszprém: 3 gólos előny ment el")
    assert len(kiemelesek) == 2
    # Csak sorozat (a vezetés nem fordul).
    csak_sorozat, kiemelesek = _momentum_section(_golos_meccs("HHH"),
                                                 "Veszprém", "Szeged")
    assert csak_sorozat["body"].startswith(
        "Veszprém 3 gólos sorozata a 0:00–0:02 között (állás utána 3–0).")
    assert "fordult" not in csak_sorozat["body"]
    assert kiemelesek[0].startswith("Veszprém 3 gólos sorozatot futott")
    # Felváltva lőtt gólok, a hazai végig vezet vagy döntetlen: nincs mit
    # mondani.
    assert _momentum_section(_golos_meccs("HAHAHA"), "Veszprém",
                             "Szeged") == (None, [])
