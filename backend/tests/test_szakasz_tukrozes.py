"""
Tesztek a szakasz KÉZI tükrözésére — az ember dönti el a térfelet.

Az automatikus térfélcsere-felismerés kevés mért pozíciónál nem dönt,
és a minőség-jelentés csak annyit tud mondani: ellenőrizd az
eredményt. A meccset látott ember viszont TUDJA a valódi végeredményt
— a flip_segment (és a /segments/{i}/flip végpont) adja a kezébe a
javítást: egy gombbal megfordítja a gyanús szakaszt, a döntés lemezre
kerül, és a származtatott kivonatok újraszámolódnak.

Futtatás:
    python -m pytest tests/test_szakasz_tukrozes.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from handball.pipeline.merge import flip_segment, merge_matches  # noqa: E402
from handball.models.tracking import (  # noqa: E402
    Ball, Frame, Match, MatchMeta, PlayerPosition, Team,
)


def _resz(match_id, n, home_x, video, fps=10.0):
    """Rész, ahol a HAZAI súlypontja home_x, a VENDÉGÉ a tükörképe."""
    from handball.pipeline.calibration import COURT_LENGTH_M

    meta = MatchMeta(match_id=match_id, home_team="Mi", away_team="Ok",
                     fps=fps, video_path=video)
    frames = []
    for i in range(n):
        frames.append(Frame(t=i, players=[
            PlayerPosition(track_id=1, team=Team.HOME,
                           x=home_x + (i % 5) * 0.1, y=8.0),
            PlayerPosition(track_id=2, team=Team.AWAY,
                           x=COURT_LENGTH_M - home_x - (i % 5) * 0.1,
                           y=12.0),
        ], ball=Ball(x=home_x, y=10.0)))
    return Match(meta, frames)


# ---------------------------------------------------------------- motor

def test_a_kezi_tukrozes_megfordit_es_dontesnek_szamit():
    """Kevés mintánál az összefűzés nem dönt — az ember viszont igen.
    A tükrözés a szakasz MINDEN koordinátáját fordítja (labdát is),
    és a döntés véglegesnek jelölődik: a figyelmeztetés elhallgat."""
    a = _resz("a1", 20, 10.0, video="/v/a.mp4")
    b = _resz("a2", 20, 10.0, video="/v/b.mp4")
    m = merge_matches([a, b], "teljes")
    sz = m.meta.source_segments
    assert sz[1]["mirror_decided"] is False
    assert sz[1]["mirrored"] is False

    flip_segment(m, 1)

    assert sz[1]["mirrored"] is True
    assert sz[1]["mirror_decided"] is True
    masodik = [f for f in m.frames if f.t >= sz[1]["t_from"]]
    hazai_x = [p.x for f in masodik for p in f.players
               if p.team == Team.HOME]
    # 10 körüli x-ből 30 körüli lett (40 m-es pálya).
    assert min(hazai_x) > 25.0, (min(hazai_x), max(hazai_x))
    assert all(f.ball.x > 25.0 for f in masodik if f.ball is not None)
    # Az ELSŐ szakasz érintetlen.
    elso = [f for f in m.frames if f.t < sz[1]["t_from"]]
    assert all(p.x < 15.0 for f in elso for p in f.players
               if p.team == Team.HOME)


def test_a_masodik_tukrozes_visszaallit():
    """A gomb oda-vissza működik: aki tévedésből fordított, egy újabb
    kattintással visszakapja az eredetit — a döntés attól még döntés."""
    a = _resz("b1", 20, 10.0, video="/v/a.mp4")
    b = _resz("b2", 20, 10.0, video="/v/b.mp4")
    m = merge_matches([a, b], "teljes")
    eredeti = [p.x for f in m.frames for p in f.players]

    flip_segment(m, 1)
    flip_segment(m, 1)

    assert m.meta.source_segments[1]["mirrored"] is False
    assert m.meta.source_segments[1]["mirror_decided"] is True
    utana = [p.x for f in m.frames for p in f.players]
    assert utana == pytest.approx(eredeti)


def test_a_rossz_index_es_a_nem_osszefuzott_hibat_dob():
    a = _resz("c1", 20, 10.0, video="/v/a.mp4")
    b = _resz("c2", 20, 10.0, video="/v/b.mp4")
    m = merge_matches([a, b], "teljes")
    with pytest.raises(ValueError):
        flip_segment(m, 5)
    sima = _resz("c3", 20, 10.0, video="/v/c.mp4")
    with pytest.raises(ValueError):
        flip_segment(sima, 0)


# ------------------------------------------------------------------ API

TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient


def _client(reszek):
    tmp = tempfile.mkdtemp(prefix="hb_flip_")
    os.environ["HANDBALL_DATA_DIR"] = tmp
    d = Path(tmp) / "data" / "matches"
    d.mkdir(parents=True, exist_ok=True)
    for m in reszek:
        (d / f"{m.meta.match_id}.json").write_text(
            json.dumps(m.to_dict()), encoding="utf-8")
    from handball.api.app import create_app
    return TestClient(create_app()), tmp


def test_a_szakasz_lista_es_a_konyvtar_jelzi_az_eldontetlent():
    a = _resz("d1", 20, 10.0, video="/v/a.mp4")
    b = _resz("d2", 20, 10.0, video="/v/b.mp4")
    c, _tmp = _client([a, b])
    r = c.post("/matches/merge", json={"ids": ["d1", "d2"],
                                       "match_id": "teljes"})
    assert r.status_code == 200

    valasz = c.get("/matches/teljes/segments").json()
    assert "goals_home" in valasz and "goals_away" in valasz
    segs = valasz["segments"]
    assert len(segs) == 2
    assert segs[0]["file"] == "a.mp4"
    assert segs[1]["mirror_decided"] is False
    assert segs[1]["from_s"] == pytest.approx(2.0)  # 20 kocka / 10 fps

    sor = [m for m in c.get("/matches").json()["matches"]
           if m["match_id"] == "teljes"][0]
    assert sor["undecided_segments"] == 1


def test_a_flip_vegpont_fordit_ment_es_lezarja_a_dontest():
    a = _resz("e1", 20, 10.0, video="/v/a.mp4")
    b = _resz("e2", 20, 10.0, video="/v/b.mp4")
    c, tmp = _client([a, b])
    c.post("/matches/merge", json={"ids": ["e1", "e2"],
                                   "match_id": "teljes"})

    r = c.post("/matches/teljes/segments/1/flip")
    assert r.status_code == 200
    segs = r.json()["segments"]
    assert segs[1]["mirrored"] is True
    assert segs[1]["mirror_decided"] is True
    # A friss eredmeny is a valaszban van: a felhasznalo a valodi
    # vegeredmennyel veti ossze, anelkul vakon nyomkodna a gombot.
    assert "goals_home" in r.json() and "goals_away" in r.json()

    # A meccs-JSON-ban tényleg fordultak a koordináták.
    m = c.get("/matches/teljes").json()
    hatar = 20
    hazai_x = [p["x"] for f in m["frames"] if f["t"] >= hatar
               for p in f["players"] if p["team"] == "home"]
    assert hazai_x and min(hazai_x) > 25.0

    # A könyvtár-jelzés eltűnik: döntés SZÜLETETT (embertől).
    sor = [x for x in c.get("/matches").json()["matches"]
           if x["match_id"] == "teljes"][0]
    assert sor["undecided_segments"] == 0

    # És a döntés LEMEZRE került: újraindítás után is él.
    mentett = json.loads(
        (Path(tmp) / "data" / "matches" / "teljes.json").read_text(
            encoding="utf-8"))
    sz = mentett["meta"]["source_segments"]
    assert sz[1]["mirrored"] is True and sz[1]["mirror_decided"] is True


def test_a_flip_hibai_erthetoek():
    a = _resz("f1", 20, 10.0, video="/v/a.mp4")
    c, _tmp = _client([a])
    # Nem összefűzött meccs: nincs forrás-térkép → 400, magyar hibával.
    r = c.post("/matches/f1/segments/0/flip")
    assert r.status_code == 400
    assert "forrás-térkép" in r.json()["detail"]
    # Nem létező meccs → 404.
    assert c.post("/matches/nincs/segments/0/flip").status_code == 404


# ------------------------------------------------- félidő a határból

def _aktiv_resz(match_id, n, home_x, video, fps=10.0):
    """Mint a _resz, de AKTÍV: 3-3 mért játékos csapatonként — így az
    aktivitás-alapú szünet-felismerés nem lát mindenütt "szünetet"
    (a ritkás fixture-t annak látná), és tényleg a szakasz-határ útja
    dönt."""
    from handball.pipeline.calibration import COURT_LENGTH_M

    meta = MatchMeta(match_id=match_id, home_team="Mi", away_team="Ok",
                     fps=fps, video_path=video)
    frames = []
    for i in range(n):
        jatekosok = []
        for j in range(3):
            jatekosok.append(PlayerPosition(
                track_id=1 + j, team=Team.HOME,
                x=home_x + (i % 5) * 0.1 + j * 0.3, y=6.0 + j * 2.0))
            jatekosok.append(PlayerPosition(
                track_id=11 + j, team=Team.AWAY,
                x=COURT_LENGTH_M - home_x - (i % 5) * 0.1 - j * 0.3,
                y=6.0 + j * 2.0))
        frames.append(Frame(t=i, players=jatekosok,
                            ball=Ball(x=home_x, y=10.0)))
    return Match(meta, frames)


def test_a_felido_a_terfelcsere_hatarbol_jon_a_darabolt_meccsen():
    """A darabokban felvett meccsben NINCS felvett szünet (a telefon a
    szünet alatt állt) — az aktivitás-alapú félidő-felismerés némán
    None-t adna, és minden félidő-tudatos réteg elhallgatna. Az
    összefűzés viszont tudja, hol fordult a pálya: az a határ a félidő."""
    from handball.pipeline.halftime import detect_halftime

    a = _aktiv_resz("ht1", 800, 10.0, video="/v/a.mp4")
    b = _aktiv_resz("ht2", 800, 30.0, video="/v/b.mp4")
    m = merge_matches([a, b], "teljes")
    assert m.meta.source_segments[1]["mirrored"] is True  # a gép döntött

    assert detect_halftime(m) == 800  # a 2. szakasz első kockája


def test_az_emberi_forditas_utan_is_meglesz_a_felido():
    """Kevés mintánál a gép nem dönt — félidő sincs. Amikor az ember a
    ⇄ gombbal megfordítja a 2. szakaszt, a döntésével együtt a
    félidő-pont is megszületik: a félidő-tudatos rétegek felébrednek."""
    from handball.pipeline.halftime import detect_halftime

    a = _resz("hu1", 20, 10.0, video="/v/a.mp4")
    b = _resz("hu2", 20, 10.0, video="/v/b.mp4")
    m = merge_matches([a, b], "teljes")
    assert detect_halftime(m) is None  # nincs döntés, nincs szünet sem

    flip_segment(m, 1)
    assert detect_halftime(m) == 20


def test_a_felidon_beluli_vagas_nem_ad_hamis_felidot():
    """Ha a telefon a félidőn BELÜL vágta el a felvételt (nincs csere a
    határon), a határ nem félidő — és nem is jelentjük annak."""
    from handball.pipeline.halftime import detect_halftime

    a = _aktiv_resz("hv1", 800, 10.0, video="/v/a.mp4")
    b = _aktiv_resz("hv2", 800, 10.0, video="/v/b.mp4")
    m = merge_matches([a, b], "teljes")
    assert m.meta.source_segments[1]["mirrored"] is False

    assert detect_halftime(m) is None


def test_tobb_fordulasnal_nem_tippelunk_felidot():
    """Oda-vissza forduló szakaszok (pl. rossz sorrendben összefűzött
    darabok) nem félidő-alakúak — ott inkább nincs félidő-pont, mint
    egy rossz."""
    from handball.pipeline.halftime import detect_halftime

    a = _aktiv_resz("hz1", 800, 10.0, video="/v/a.mp4")
    b = _aktiv_resz("hz2", 800, 30.0, video="/v/b.mp4")
    c_ = _aktiv_resz("hz3", 800, 10.0, video="/v/c.mp4")
    m = merge_matches([a, b, c_], "teljes")
    sz = m.meta.source_segments
    assert [s["mirrored"] for s in sz] == [False, True, False]

    assert detect_halftime(m) is None


def test_a_hat_darabos_meccs_masodik_felideje_egyben_fordul():
    """A hat klipes meccs (a tipikus telefonos felvétel): a félidő a 3.
    és 4. darab közé esik. A 2. félidő MINDEN darabjának tükrözve kell
    lennie — nem csak az elsőnek. (A határ előtti ablak már a
    normalizált képet mutatja, ezért a tükrözött darab utáni nyers
    darab újra "fordulást" mutat — az állapot billegtetése minden
    második 2. félidős darabot visszafordított volna.)"""
    from handball.pipeline.halftime import detect_halftime

    reszek = [
        _aktiv_resz("s1", 800, 10.0, video="/v/1.mp4"),
        _aktiv_resz("s2", 800, 10.0, video="/v/2.mp4"),
        _aktiv_resz("s3", 800, 10.0, video="/v/3.mp4"),
        _aktiv_resz("s4", 800, 30.0, video="/v/4.mp4"),
        _aktiv_resz("s5", 800, 30.0, video="/v/5.mp4"),
        _aktiv_resz("s6", 800, 30.0, video="/v/6.mp4"),
    ]
    m = merge_matches(reszek, "teljes")
    sz = m.meta.source_segments
    assert [s["mirrored"] for s in sz] == [
        False, False, False, True, True, True], sz

    # A hazai a TELJES meccsen a bal térfélen áll (normalizált kép).
    hazai_x = [p.x for f in m.frames for p in f.players
               if p.team == Team.HOME]
    assert max(hazai_x) < 15.0

    # És a félidő-pont a 4. darab eleje.
    assert detect_halftime(m) == 3 * 800
