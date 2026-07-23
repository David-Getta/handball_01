"""A pontosság-validáció (validate_events) tesztjei."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.validation import (
    parse_truth_csv, validate_events, validation_report_html)


def _meta(fps=25.0):
    return MatchMeta(match_id="v", home_team="H", away_team="A", fps=fps)


def _pl(tid, x, y):
    return PlayerPosition(track_id=tid, team=Team.HOME, x=x, y=y,
                          source=PositionSource.MEASURED, confidence=1.0)


def _home_goal(t0, sx=33.0):
    """Egy hazai gól a +x kapura, t0-tól."""
    frames = [Frame(t=t0 + i, players=[_pl(1, sx, 10.0)],
                    ball=Ball(x=sx, y=10.0, confidence=1.0)) for i in range(3)]
    for i in range(9):
        bx = min(sx + 1.6 * (i + 1), 40.0)
        frames.append(Frame(t=t0 + 3 + i, players=[_pl(1, sx, 10.0)],
                            ball=Ball(x=bx, y=10.0, confidence=1.0)))
    return frames


def _match_one_goal():
    frames = _home_goal(0)
    # tér-kitöltés, hogy a meccs ne csak a gólból álljon
    t = frames[-1].t + 1
    for i in range(30):
        frames.append(Frame(t=t + i, players=[],
                            ball=Ball(x=20.0, y=10.0, confidence=1.0)))
    return Match(_meta(), frames)


def test_validation_matches_within_tolerance():
    """A felismert gólt a tűrésen belüli kézi góllal párosítja (TP),
    a listában lévő, fel nem ismert gól kimaradás (FN)."""
    m = _match_one_goal()
    truth = [
        {"t_s": 0.4, "type": "gól", "team": "home"},   # ~egyezik a felismerttel
        {"t_s": 30.0, "type": "gól", "team": "home"},  # nincs felismert pár → FN
    ]
    res = validate_events(m, truth)
    g = res["by_type"]["goal"]
    assert g["tp"] == 1 and g["fn"] == 1 and g["fp"] == 0
    assert g["precision"] == 1.0
    assert g["recall"] == 0.5
    assert res["overall"]["tp"] == 1 and res["overall"]["fn"] == 1


def test_validation_false_positive_when_no_truth():
    """Üres kézi lista mellett a felismert gól téves pozitív (FP)."""
    m = _match_one_goal()
    res = validate_events(m, [])
    g = res["by_type"]["goal"]
    assert g["tp"] == 0 and g["fp"] == 1 and g["fn"] == 0
    assert g["precision"] == 0.0
    # Recall nem értelmezett igazság-adat nélkül.
    assert g["recall"] is None


def test_validation_team_mismatch_not_paired():
    """Ha a kézi rekord más csapatot ad meg, nem párosít (FP + FN)."""
    m = _match_one_goal()
    truth = [{"t_s": 0.4, "type": "gól", "team": "away"}]  # rossz csapat
    res = validate_events(m, truth)
    g = res["by_type"]["goal"]
    assert g["tp"] == 0 and g["fp"] == 1 and g["fn"] == 1


def test_validation_ignores_unknown_types_and_tolerance():
    """Ismeretlen típust kihagy; a tűrésen kívüli pár nem egyezik."""
    m = _match_one_goal()
    # Ismeretlen típus kimarad; a gól 10 s-re a felismerttől (tol=3) → nem pár.
    truth = [{"t_s": 10.0, "type": "gól", "team": "home"},
             {"t_s": 5.0, "type": "cselekmény"}]
    res = validate_events(m, truth, tol_s=3.0)
    g = res["by_type"]["goal"]
    assert g["tp"] == 0 and g["fp"] == 1 and g["fn"] == 1


def test_validation_verdict_pass_and_fail():
    """A verdikt a cél-küszöbökhöz méri az összesített eredményt."""
    m = _match_one_goal()
    # Tökéletes egyezés (1 felismert = 1 kézi) → MEGFELEL.
    good = validate_events(m, [{"t_s": 0.4, "type": "gól", "team": "home"}])
    assert good["overall"]["recall"] == 1.0
    assert good["verdict"]["pass"] is True
    assert "MEGFELEL" in good["verdict"]["text"]
    # Fele kimarad → GYENGE.
    bad = validate_events(m, [
        {"t_s": 0.4, "type": "gól", "team": "home"},
        {"t_s": 30.0, "type": "gól", "team": "home"}])
    assert bad["verdict"]["pass"] is False
    assert "GYENGE" in bad["verdict"]["text"]
    # Üres minta → nincs ítélet.
    empty = validate_events(Match(_meta(), [Frame(t=0, players=[], ball=None)]),
                            [])
    assert empty["verdict"]["pass"] is None


def test_validation_report_html_renders():
    """A HTML-riport tartalmazza az ítéletet, a csapatokat és a táblát;
    a beszúrt szöveg escape-elve kerül be."""
    m = _match_one_goal()
    res = validate_events(m, [{"t_s": 0.4, "type": "gól", "team": "home"}])
    html = validation_report_html(res, "Hazai<b>", "Vendég")
    assert "<!DOCTYPE html>" in html
    assert "Pontosság-validáció" in html
    assert "MEGFELEL" in html
    assert "Visszahívás" in html and "Precizitás" in html
    assert "Összesen" in html
    # A csapatnév escape-elve (nincs nyers <b>).
    assert "Hazai<b>" not in html and "Hazai&lt;b&gt;" in html


def test_parse_truth_csv_formats():
    """A CSV-beolvasó elfogadja a mm:ss időt, a magyar címkéket, a fejlécet
    kihagyja, és validate_events-nek átadható listát ad."""
    csv = (
        "ido,tipus,csapat\n"        # fejléc — kimarad
        "0:42, gól, hazai\n"        # mm:ss + magyar → 42 mp, home
        "75.5; lövés; vendég\n"     # pontosvessző + tizedes → away
        "# megjegyzés\n"            # komment — kimarad
        "1:02:03, gól\n"            # óra:perc:mp, csapat nélkül
        "rossz sor\n")             # nincs érvényes idő — kimarad
    truth = parse_truth_csv(csv)
    assert len(truth) == 3
    assert truth[0] == {"t_s": 42.0, "type": "gól", "team": "home"}
    assert truth[1]["t_s"] == 75.5 and truth[1]["team"] == "away"
    assert truth[2]["t_s"] == 3723.0 and truth[2]["team"] is None
    # Az eredmény tényleg átmegy a validate_events-en (csak típus-egyezésre).
    m = _match_one_goal()
    res = validate_events(m, parse_truth_csv("0:00, gól, hazai"))
    assert res["by_type"]["goal"]["tp"] == 1
