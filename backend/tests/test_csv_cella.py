"""A CSV-exportok szöveges cellái: idézés és képlet-védelem (a nevek nem
csúsztatják szét az oszlopokat, és Excelben nem futnak képletként)."""
import csv
import io

from fastapi.testclient import TestClient

from handball.csv_cella import csv_cella, keplet_vedett


def test_a_cella():
    assert csv_cella("Kiss Péter") == "Kiss Péter"
    assert csv_cella("Kiss; ifj.") == '"Kiss; ifj."'
    assert csv_cella('A "Tank"') == '"A ""Tank"""'
    assert csv_cella("=HYPERLINK(1)") == "'=HYPERLINK(1)"
    assert csv_cella("=1;2") == '"\'=1;2"'
    for jel in ("+", "-", "@", "\t"):
        assert keplet_vedett(jel + "x") == "'" + jel + "x"
    assert keplet_vedett(None) == "" and csv_cella(7) == "7"


def _olvas(szoveg: str) -> list:
    return list(csv.reader(io.StringIO(szoveg.lstrip("\ufeff")), delimiter=";"))


def test_a_statisztika_es_a_keret_csv(tmp_path, monkeypatch):
    from handball.api.app import create_app
    from handball.sim.match_simulator import simulate_ground_truth

    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    app = create_app()
    m = simulate_ground_truth(duration_s=30, fps=25.0, seed=5)
    m.meta.match_id = "csv"
    m.meta.home_team = "=HAZAI;KFT"
    app.state.put_match(m)
    c = TestClient(app)
    sorok = _olvas(c.get("/matches/csv/stats/export").text)
    fej = sorok[0]
    assert len(fej) > 5
    # Minden sor ugyanannyi oszlop; a csapat-név egyben, képlet-védve.
    assert all(len(s) == len(fej) for s in sorok[1:]), [len(s) for s in sorok]
    csapat = fej.index("Csapat")
    assert "'=HAZAI;KFT" in {s[csapat] for s in sorok[1:]}

    from handball.annotations import annotations_csv
    szoveg = annotations_csv({"events": [{"t_s": 1.0, "team": "home",
                                          "type": "lövés", "note": "=1+1"}]},
                             home="=HAZAI;KFT", away="B")
    s = _olvas(szoveg)
    assert s[1][2] == "'=HAZAI;KFT" and s[1][7] == "'=1+1"
