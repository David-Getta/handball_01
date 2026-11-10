"""
A tükrözés-őr (scripts.mirror_sides) tesztjei.

A teljes, minden rétegre kiterjedő söprés lassú (fél perc feletti),
ezért az a jelentés-szkript dolga — mint a sorrend-függésnél. Itt a
mechanikát rögzítjük gyors tesztekkel: a csere-szabályt (a magyar
"jobb" = better csapdájával), a tükrözést, és egy kézzel épített
jeleneten a legbuktatósabb védekező-oldali réteget.

Futtatás:
    python -m pytest tests/test_mirror_sides.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.mirror_sides import has_side_label, mirror_match, swap_sides

from handball.models.tracking import (
    Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)


def test_swap_flips_labels_but_never_prose():
    """A csere a címkéket fordítja meg — a mondatot, ahol a "jobb"
    better-t jelent, SOHA (ez a magyar nyelv csapdája)."""
    rec = {
        "worst_zone": "bal szél",
        "hands": {"bal": 1, "jobb": 2},
        "verdict": "csak 20%-nál volt jobb szabad helyzet",
    }
    out = swap_sides(rec)
    assert out["worst_zone"] == "jobb szél"
    assert out["hands"] == {"jobb": 1, "bal": 2}
    # A próza érintetlen: a "jobb szabad helyzet" nem oldal.
    assert out["verdict"] == "csak 20%-nál volt jobb szabad helyzet"


def test_has_side_label_ignores_prose():
    """A szűrő a címkét látja meg, a prózában említett oldalt nem."""
    assert has_side_label({"weak_side": "bal"})
    assert has_side_label({"zones": {"jobb szél": 3}})
    assert not has_side_label({"verdict": "jobb helyzet volt a pályán"})


def test_mirror_flips_players_and_ball():
    """A tükrözés az y-t fordítja (20 − y), és nem nyúl máshoz."""
    m = Match(MatchMeta(match_id="mir", home_team="H", away_team="A",
                        fps=25.0),
              [Frame(t=0,
                     players=[PlayerPosition(
                         track_id=1, team=Team.HOME, x=10.0, y=4.0,
                         source=PositionSource.MEASURED, confidence=1.0)],
                     ball=Ball(x=20.0, y=15.0, confidence=1.0))])
    m2 = mirror_match(m)
    assert m2.frames[0].players[0].y == 16.0
    assert m2.frames[0].players[0].x == 10.0
    assert m2.frames[0].ball.y == 5.0
    # Az eredeti érintetlen (mély másolat).
    assert m.frames[0].players[0].y == 4.0


def test_defensive_gaps_zone_flips_in_the_mirror():
    """A fal-rés réteg oldal-megnevezése a tükörképben megfordul — a
    védekező oldalra szóló rétegek legbuktatósabb tulajdonsága (a két
    csapat szemben áll, a nyers y-ból nevezett oldal hibás lenne)."""
    from handball.pipeline.defense import defensive_gaps

    def _pl(track_id, team, x, y, role=None):
        return PlayerPosition(track_id=track_id, team=team, x=x, y=y,
                              source=PositionSource.MEASURED,
                              confidence=1.0, role=role)

    frames = []
    for t in range(150):
        players = [_pl(1, Team.AWAY, 8.0, 10.0)]
        # A rés a NAGY y-nál tátong (16,5 közepű).
        for i, y in enumerate([2.0, 4.0, 6.0, 8.0, 10.0, 23.0]):
            players.append(_pl(10 + i, Team.HOME, 6.0, min(y, 19.5)))
        players.append(_pl(9, Team.HOME, 0.5, 10.0, role="kapus"))
        frames.append(Frame(t=t, players=players,
                            ball=Ball(x=8.0, y=10.0, confidence=1.0)))
    m = Match(MatchMeta(match_id="dg", home_team="H", away_team="A",
                        fps=25.0), frames)

    plain = defensive_gaps(m)["home"]
    flipped = defensive_gaps(mirror_match(m))["home"]
    assert plain["worst_zone"] is not None
    assert flipped["worst_zone"] == swap_sides(plain)["worst_zone"]
    assert flipped["worst_zone"] != plain["worst_zone"]


# ---- A mérés, a jelentés és a main (eddig egyszer sem futottak a csomagban) ----

def _kis_meres(monkeypatch, retegek, seconds=6.0):
    from scripts import mirror_sides, order_sensitivity

    monkeypatch.setattr(order_sensitivity, "_layer_functions",
                        lambda: retegek)
    return mirror_sides.measure(seconds=seconds, seed=7)


def test_measure_megkulonbozteti_a_helyesen_es_a_hibasan_tukrozot(
        monkeypatch):
    """Kicsiben, próba-rétegekkel. A VÉDŐ szemszögéből nevező réteg a
    tükörképben megfordul (rendben); a mindig "bal"-t mondó réteg nem
    (hibás); az oldal-címke nélküli réteg nem számít vizsgáltnak."""
    from handball.pipeline import xg

    def helyes(match):
        # A labda átlagos oldala: a tükörképben a másik oldal.
        ys = [f.ball.y for f in match.frames if f.ball is not None]
        atlag = sum(ys) / len(ys)
        return {"home": {"weak_side": "bal" if atlag < 10.0 else "jobb"}}

    def hibas(match):
        return {"home": {"weak_side": "bal"}}     # a tükörképben is "bal"

    def cimke_nelkul(match):
        return {"home": {"verdict": "jobb szabad helyzet volt", "n": 3}}

    monkeypatch.setattr(xg, "_proba_helyes", helyes, raising=False)
    monkeypatch.setattr(xg, "_proba_hibas", hibas, raising=False)
    monkeypatch.setattr(xg, "_proba_cimke_nelkul", cimke_nelkul,
                        raising=False)
    res = _kis_meres(monkeypatch, [
        ("helyes", "xg", "_proba_helyes"), ("hibás", "xg", "_proba_hibas"),
        ("címke nélkül", "xg", "_proba_cimke_nelkul")])
    assert res == {"checked": 2, "mirrored_ok": ["helyes"],
                   "broken": ["hibás"], "skipped_prose": []}


def test_measure_a_prozat_kihagyja_a_hibas_reteget_nem_iteli(monkeypatch):
    """A próza-gyártó összegzők (mondatban beszélnek oldalról) kimaradnak
    — név szerint, rendezve —, a hibára futó és a hiányzó réteg pedig
    nem kap ítéletet (sem jó, sem hibás)."""
    from handball.pipeline import xg
    from scripts.mirror_sides import PROSE_LAYERS

    def bukik(match):
        raise RuntimeError("nem megy")

    hivva = []
    monkeypatch.setattr(xg, "_proba_bukik", bukik, raising=False)
    monkeypatch.setattr(xg, "_proba_proza",
                        lambda match: hivva.append(1) or {}, raising=False)
    assert {"coach_summary", "scouting", "training"} <= PROSE_LAYERS
    res = _kis_meres(monkeypatch, [
        ("training", "xg", "_proba_proza"),
        ("coach_summary", "xg", "_proba_proza"),
        ("bukó", "xg", "_proba_bukik"),
        ("hiányzó", "xg", "_nincs_ilyen_fuggveny")])
    assert res == {"checked": 0, "mirrored_ok": [], "broken": [],
                   "skipped_prose": ["coach_summary", "training"]}
    assert hivva == []                           # a prózát meg sem hívja


def test_measure_a_valodi_oldal_cimkes_reteg_helyesen_tukrozodik(
        monkeypatch):
    """Egy VALÓDI oldal-címkés réteggel (defensive_gaps): a mérés
    vizsgáltnak veszi, és a tükörképe helyes — ezt mondja a beírt
    jelentés is."""
    res = _kis_meres(monkeypatch,
                     [("defensive_gaps", "defense", "defensive_gaps")],
                     seconds=60.0)
    assert res["broken"] == []
    assert res["checked"] == len(res["mirrored_ok"]) <= 1


def test_build_report_megnevezi_a_hibas_retegeket():
    """A jelentés fejléce a mérést (hossz, mag, darabszámok) mondja; a
    hibás rétegek névsorban, külön szakaszban állnak, alatta a vizsgált
    és a kihagyott rétegek."""
    from scripts.mirror_sides import build_report

    res = {"checked": 4, "mirrored_ok": ["wing_usage", "attack_sides"],
           "broken": ["zeta_reteg", "alfa_reteg"],
           "skipped_prose": ["coach_summary", "training"]}
    s = build_report(res, seconds=120.0, seed=7)
    assert s.startswith("# Tükrözés-őr")
    assert "120 mp-es szimulált meccs (mag: 7); **4 oldal-címkés réteg** " \
           "vizsgálva, ebből **2 hibás**" in s
    assert "## Hibás rétegek" in s and "Hibás réteg: nincs" not in s
    assert s.index("- `alfa_reteg`") < s.index("- `zeta_reteg`")
    vizsgalt = s.split("## Vizsgált rétegek")[1]
    assert vizsgalt.index("- `attack_sides`") < vizsgalt.index(
        "- `wing_usage`")
    assert "- `coach_summary`\n- `training`\n" in s.split(
        "## Kihagyva (próza-gyártó összegzők)")[1]


def test_build_report_hiba_nelkul_kimondja():
    """Hibás réteg nélkül a jelentés kimondja, hogy minden oldal-címkés
    réteg helyesen tükröződik (ezt az állapotot kell tartani)."""
    from scripts.mirror_sides import build_report

    s = build_report({"checked": 1, "mirrored_ok": ["wing_usage"],
                      "broken": [], "skipped_prose": []}, 60.0, 3)
    assert "## Hibás réteg: nincs" in s
    assert "Minden oldal-címkés réteg helyesen tükröződik." in s
    assert "**1 oldal-címkés réteg** vizsgálva, ebből **0 hibás**" in s
    assert "## Hibás rétegek" not in s


def test_main_hibas_retegnel_1_es_kod_kulonben_0(monkeypatch, tmp_path,
                                                 capsys):
    """A main megírja a (tmp mappába irányított) jelentést és összegez;
    a kilépőkód 1, ha van hibásan tükröződő réteg (a kiadás előtti őr
    ezt nézi), különben 0."""
    from scripts import mirror_sides as ms

    kert: dict = {}
    eredmeny = {"checked": 3, "mirrored_ok": ["wing_usage"],
                "broken": ["rossz_reteg"], "skipped_prose": ["training"]}

    def kamu_meres(seconds, seed):
        kert.update(seconds=seconds, seed=seed)
        return eredmeny

    ki_fajl = tmp_path / "docs" / "TUKROZES.md"
    monkeypatch.setattr(ms, "measure", kamu_meres)
    monkeypatch.setattr(ms, "_OUT", ki_fajl)
    assert ms.main(["--seconds", "30", "--seed", "4"]) == 1
    assert kert == {"seconds": 30.0, "seed": 4}
    assert ki_fajl.read_text(encoding="utf-8") == ms.build_report(
        eredmeny, 30.0, 4)
    ki = capsys.readouterr().out
    assert f"Tükrözés-jelentés kiírva: {ki_fajl}" in ki
    assert "vizsgálva: 3 réteg" in ki and "hibás: 1" in ki
    assert "    - rossz_reteg" in ki

    eredmeny["broken"] = []
    assert ms.main([]) == 0
    assert kert == {"seconds": ms.DEFAULT_SECONDS, "seed": ms.DEFAULT_SEED}
    assert "hibás: 0" in capsys.readouterr().out
    assert "## Hibás réteg: nincs" in ki_fajl.read_text(encoding="utf-8")
