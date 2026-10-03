"""A pontosság-validáció (validate_events) tesztjei."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (
    Ball, Frame, Match, MatchMeta, PlayerPosition, PositionSource, Team,
)
from handball.pipeline.validation import (
    parse_truth_csv, validate_events, validation_report_html,
    validation_template_csv)


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


def test_validation_template_round_trips():
    """A felismert eseményekből generált sablon vissza-beolvasva a saját
    meccsre tökéletes egyezést ad (a coach kiindulópontja)."""
    m = _match_one_goal()
    csv = validation_template_csv(m)
    assert csv.startswith("#")               # magyarázó fejléc
    assert "gól" in csv                       # a felismert gól sora
    truth = parse_truth_csv(csv)
    assert len(truth) >= 1
    res = validate_events(m, truth)
    # A sablon a motor kimenete → önmagára nézve nincs FP és nincs FN.
    assert res["overall"]["fp"] == 0 and res["overall"]["fn"] == 0
    assert res["verdict"]["pass"] is True


def test_validate_match_cli(tmp_path, capsys):
    """A parancssori eszköz betölti a mentett meccset + a CSV-t, kiírja az
    ítéletet, HTML-riportot ír, és a go/no-go kilépőkódot adja."""
    import json as _json

    from scripts.validate_match import main

    m = _match_one_goal()
    mj = tmp_path / "match.json"
    mj.write_text(_json.dumps(m.to_dict()), encoding="utf-8")
    csv = tmp_path / "truth.csv"
    csv.write_text("ido,tipus,csapat\n0:00, gól, hazai\n", encoding="utf-8")
    out = tmp_path / "riport.html"

    code = main([str(mj), str(csv), "--out", str(out)])
    printed = capsys.readouterr().out
    assert code == 0                          # MEGFELEL → 0
    assert "MEGFELEL" in printed
    assert "Összesen" in printed
    assert out.exists() and "Pontosság-validáció" in out.read_text(
        encoding="utf-8")

    # Hiányzó fájl → 2-es hibakód.
    assert main([str(tmp_path / "nincs.json"), str(csv)]) == 2


def test_validate_match_cli_writes_template(tmp_path, capsys):
    """A `--sablon` kiírja az annotációs sablont, és KILÉP.

    Ez a TRL-4 bizonyíték-út első lépése: az annotátor ezt a fájlt
    javítja kézzel. Ha ez elromlik, a valós felvétel érkezésekor
    derülne ki — amikor már drága.
    """
    import json as _json

    from scripts.validate_match import main

    m = _match_one_goal()
    mj = tmp_path / "match.json"
    mj.write_text(_json.dumps(m.to_dict()), encoding="utf-8")
    sablon = tmp_path / "sablon.csv"

    assert main([str(mj), "--sablon", str(sablon)]) == 0
    assert sablon.exists(), "nem készült sablon"
    text = sablon.read_text(encoding="utf-8")
    assert text.startswith("#"), "hiányzik a magyarázó fejléc"
    assert "gól" in text, "a felismert gól nincs a sablonban"


def test_validate_match_cli_appends_to_ledger(tmp_path):
    """A `--jegyzokonyv` a naplóhoz FŰZ egy dátumozott sort.

    Ez a bizonyíték-út utolsó lépése: a mérés eredménye
    verziószámmal, meccsel és P/R értékekkel a naplóba kerül. A
    meglévő tartalom nem veszhet el.
    """
    import json as _json

    from scripts.validate_match import main

    m = _match_one_goal()
    mj = tmp_path / "match.json"
    mj.write_text(_json.dumps(m.to_dict()), encoding="utf-8")
    csv = tmp_path / "truth.csv"
    csv.write_text("ido,tipus,csapat\n0:00, gól, hazai\n", encoding="utf-8")
    log = tmp_path / "naplo.md"
    log.write_text("# Napló\n\n| Dátum | Verzió |\n|---|---|\n",
                   encoding="utf-8")

    assert main([str(mj), str(csv), "--jegyzokonyv", str(log)]) == 0
    text = log.read_text(encoding="utf-8")
    assert "# Napló" in text, "a meglévő tartalom elveszett"
    rows = [ln for ln in text.splitlines()
            if ln.startswith("|") and "Dátum" not in ln and "---" not in ln]
    assert rows, "nem került új sor a naplóba"
    assert rows[-1].count("|") >= 7, rows[-1]   # dátum..ítélet oszlopok


def test_validation_ledger_row_formats_markdown():
    """A jegyzőkönyv-sor dátumot, verziót, meccset és P/R értékeket
    tartalmaz Markdown-táblázatsorként."""
    from handball.pipeline.validation import validation_ledger_row

    res = {"by_type": {"goal": {"precision": 0.9, "recall": 1.0},
                       "shot": {"precision": 0.8, "recall": 0.75}},
           "overall": {"precision": 0.85, "recall": 0.9, "f1": 0.87}}
    row = validation_ledger_row(res, match_id="m1", version="abc1234",
                                when="2026-08-02")
    assert row == ("| 2026-08-02 | abc1234 | m1 | 90%/100% | 80%/75% "
                   "| 87% | MEGFELEL |")


def test_validation_ledger_row_handles_missing_data():
    """Üres mérésnél kötőjelek és kérdőjeles ítélet — a sor akkor is
    érvényes Markdown marad."""
    from handball.pipeline.validation import validation_ledger_row

    res = {"by_type": {}, "overall": {"precision": None, "recall": None,
                                      "f1": None}}
    row = validation_ledger_row(res)
    assert row.startswith("| ") and row.endswith("| ? |")
    assert row.count("—/—") == 2


def test_mismatch_lines_point_to_the_footage():
    """Az eltérések idő szerint, emberi nyelven — mit nézzen meg az annotáló."""
    from handball.pipeline.validation import mismatch_lines

    res = {"by_type": {
        "goal": {"missed": [{"t_s": 65.0, "type": "goal", "team": "home"}],
                 "spurious": []},
        "shot": {"missed": [],
                 "spurious": [{"t_s": 12.0, "type": "shot",
                               "team": "away"}]},
    }}
    lines = mismatch_lines(res)
    assert lines == ["0:12 — téves lövés (vendég)",
                     "1:05 — kimaradt gól (hazai)"], lines


def test_mismatch_lines_are_empty_without_errors():
    """Hibátlan validációnál nincs teendő-lista."""
    from handball.pipeline.validation import mismatch_lines

    res = {"by_type": {"goal": {"missed": [], "spurious": []},
                       "shot": {"missed": [], "spurious": []}}}
    assert mismatch_lines(res) == []


def test_mismatch_lines_truncate_long_lists():
    """Hosszú listát levágunk, de kimondjuk, hány maradt ki."""
    from handball.pipeline.validation import mismatch_lines

    res = {"by_type": {
        "goal": {"missed": [{"t_s": float(i), "type": "goal",
                             "team": "home"} for i in range(25)],
                 "spurious": []},
        "shot": {"missed": [], "spurious": []},
    }}
    lines = mismatch_lines(res, limit=5)
    assert len(lines) == 6, lines
    assert "további 20 eltérés" in lines[-1]


def test_validate_events_lists_the_missed_event():
    """A kimaradt kézi esemény tételesen is megjelenik az eredményben."""
    from handball.pipeline.validation import validate_events
    from handball.sim.match_simulator import simulate_ground_truth

    match = simulate_ground_truth(duration_s=90.0, seed=2)
    # Olyan időpont, ahol biztosan nincs felismert gól (a felvétel eleje).
    res = validate_events(match, [{"t_s": 1.0, "type": "gol",
                                   "team": "home"}])
    goal = res["by_type"]["goal"]
    assert goal["fn"] == 1, goal
    assert goal["missed"] == [{"t_s": 1.0, "type": "goal",
                               "team": "home"}], goal["missed"]


def test_validation_report_html_shows_the_mismatches():
    """A HTML-riport is felsorolja, mit kell megnézni a felvételen."""
    from handball.pipeline.validation import validation_report_html

    res = {"tol_s": 3.0, "verdict": {"pass": False, "text": "GYENGE"},
           "overall": {"tp": 0, "fp": 0, "fn": 1, "precision": None,
                       "recall": 0.0, "f1": None},
           "by_type": {
               "goal": {"tp": 0, "fp": 0, "fn": 1, "precision": None,
                        "recall": 0.0, "f1": None,
                        "missed": [{"t_s": 65.0, "type": "goal",
                                    "team": "home"}],
                        "spurious": []},
               "shot": {"tp": 0, "fp": 0, "fn": 0, "precision": None,
                        "recall": None, "f1": None,
                        "missed": [], "spurious": []}}}
    html = validation_report_html(res, "H", "A")
    assert "Mit nézz meg a felvételen" in html
    assert "1:05 — kimaradt gól (hazai)" in html
    # Hibátlan futásnál viszont kimondjuk, hogy nincs eltérés.
    clean = {"tol_s": 3.0, "verdict": {"pass": True, "text": "MEGFELEL"},
             "overall": {"tp": 1, "fp": 0, "fn": 0},
             "by_type": {"goal": {"tp": 1, "fp": 0, "fn": 0,
                                  "missed": [], "spurious": []},
                         "shot": {"tp": 0, "fp": 0, "fn": 0,
                                  "missed": [], "spurious": []}}}
    assert "Nincs eltérés" in validation_report_html(clean)
