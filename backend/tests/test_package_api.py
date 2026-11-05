"""
Tesztek a meccs-csomag exportra (/matches/{id}/package/export|download).

Futtatás:
    python -m pytest tests/test_package_api.py
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import time
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_tmp = tempfile.mkdtemp(prefix="handball_package_test_")
os.environ["HANDBALL_DATA_DIR"] = _tmp

import pytest  # noqa: E402

TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient

from handball.api.app import create_app  # noqa: E402
from handball.sim.match_simulator import simulate_ground_truth  # noqa: E402


def _client_with_match():
    os.environ["HANDBALL_DATA_DIR"] = _tmp
    m = simulate_ground_truth(duration_s=5, fps=25.0, seed=1)
    matches_dir = Path(_tmp) / "data" / "matches"
    matches_dir.mkdir(parents=True, exist_ok=True)
    (matches_dir / f"{m.meta.match_id}.json").write_text(
        json.dumps(m.to_dict()), encoding="utf-8")
    return TestClient(create_app()), m.meta.match_id


def _wait_job(client, job_id, timeout_s=30):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        job = client.get(f"/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            return job
        time.sleep(0.1)
    raise AssertionError("a job nem fejeződött be időben")


def test_package_without_video_contains_report_and_csv():
    """Videó nélkül (szimulált meccs) a csomag jelentés + CSV — a klipek
    hiánya nem végzetes."""
    client, mid = _client_with_match()
    # Egy jegyzet is kerül a meccshez — a csomagnak ezt is vinnie kell.
    client.post(f"/matches/{mid}/notes",
                json={"frame": 10, "text": "fontos pillanat"})
    r = client.post(f"/matches/{mid}/package/export", json={})
    job = _wait_job(client, r.json()["job_id"])
    assert job["status"] == "done", job
    pkg = client.get(f"/matches/{mid}/package/download")
    assert pkg.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(pkg.content))
    names = z.namelist()
    assert "jelentes.html" in names and "statisztika.csv" in names
    # Az összes elemzés-réteg géppel olvasható JSON-ban is benne van.
    assert "elemzesek.json" in names
    import json as _json
    analyses = _json.loads(z.read("elemzesek.json").decode("utf-8"))
    for key in ("coach_summary", "xg", "defense", "rules", "training",
                "progression", "attack_efficiency", "assist_network",
                "possession", "outlets", "empty_net_goals",
                "empty_net_context", "fast_break_finishers",
                "key_players", "pace", "late_subs", "big_saves",
                "missed_big_chances", "xg_saved", "xg_prevented",
                "attack_origins", "recovery", "positions",
                "seven_earners", "susp_earners", "second_half_start",
                "pace_by_score", "key_moments", "setplay_efficiency",
                "attack_width", "marking", "pivot_usage",
                "breakthroughs", "pass_chains", "rotation",
                "ball_winners", "gk_positioning",
                "transition_offense", "shot_ranges",
                "gk_save_ranges", "goal_placement",
                "wing_finishing", "defensive_line_height",
                "pass_direction", "assist_sources",
                "turnover_players", "clutch_scorers"):
        assert key in analyses, key
    # Az edzésterv pontosan akkor van a csomagban, ha van fókusz —
    # csapat-szintű VAGY egyéni. (Az egyéni feladatok is a lapra
    # kerülnek: az edző emberre bontva osztja ki a hét munkáját, és a
    # csomagot sokszor épp ezért nyitja meg.)
    tf_pkg = analyses.get("training") or {}
    ptf_pkg = analyses.get("player_training_focus") or {}
    has_focus = (any((tf_pkg.get(s_) or []) for s_ in ("home", "away"))
                 or any((ptf_pkg.get(s_) or {}).get("players")
                        for s_ in ("home", "away")))
    assert ("edzesterv.txt" in names) == has_focus
    if has_focus:
        etxt = z.read("edzesterv.txt").decode("utf-8")
        assert "gyakorlat:" in etxt
        if any((ptf_pkg.get(s_) or {}).get("players")
               for s_ in ("home", "away")):
            assert "egyéni feladatok" in etxt
    # Kulcs-pillanatok: ha van ilyen fájl, időbélyeges sorokat hoz.
    if "kulcs_pillanatok.txt" in names:
        kp = z.read("kulcs_pillanatok.txt").decode("utf-8")
        assert kp.startswith("[")
    # Játékos-lapok: minden játékosnak egy HTML a jatekos_lapok/ alatt.
    pl_pages = [n for n in names if n.startswith("jatekos_lapok/")]
    assert pl_pages, names
    phtml = z.read(pl_pages[0]).decode("utf-8")
    assert "JÁTÉKOS-LAP" in phtml
    # Meccsterv a visszavágóra: ha van páros-találat, terv-fájl készül.
    if "meccsterv.txt" in names:
        mt = z.read("meccsterv.txt").decode("utf-8")
        assert "terve a" in mt and mt.strip().startswith(("Szimu", "-")) \
            or "terve a" in mt
    # Az edzői összefoglaló sima szövegként is (osszefoglalo.txt).
    assert "osszefoglalo.txt" in names
    txt = z.read("osszefoglalo.txt").decode("utf-8")
    assert "vs" in txt
    # A jegyzetek időbélyeggel, sima szövegként (jegyzetek.txt).
    assert "jegyzetek.txt" in names
    jtxt = z.read("jegyzetek.txt").decode("utf-8")
    assert "fontos pillanat" in jtxt and "[" in jtxt
    assert "klipek.zip" not in names  # nincs videó → nincs klip
    html = z.read("jelentes.html").decode("utf-8")
    assert "Meccsjelentés" in html
    csv = z.read("statisztika.csv").decode("utf-8")
    # A NÉV oszlop is ott van: a kimutatásban a név a lényeg, és a
    # meccs-CSV nem mondhat kevesebbet, mint a szezon-CSV.
    assert "Játékos;Név;Csapat" in csv
    # A játék-statisztika oszlopok is ott vannak a fejlécben.
    assert ";Gól;Lövés;xG;Blokk;Poszt;Őrzés (mp);Őrzés átl. táv (m)" in csv


def test_package_download_404_before_export():
    client, mid = _client_with_match()
    # Friss adatmappa kell, ahol még nem készült csomag ehhez a meccshez.
    import shutil
    clips_dir = Path(_tmp) / "clips"
    if clips_dir.exists():
        shutil.rmtree(clips_dir)
    assert client.get(f"/matches/{mid}/package/download").status_code == 404
    assert client.get("/matches/nincs/package/download").status_code == 404


if __name__ == "__main__":
    test_package_without_video_contains_report_and_csv()
    test_package_download_404_before_export()
    print("Minden csomag-export teszt OK.")


def test_scouting_matchup_endpoint():
    """A meccsterv-végpont a két kombinált profilból tervet ad vissza."""
    client, mid = _client_with_match()
    body = {"own": {"items": [{"match_id": mid, "team": "home"}]},
            "opp": {"items": [{"match_id": mid, "team": "away"}]}}
    r = client.post("/scouting/matchup", json=body)
    assert r.status_code == 200
    data = r.json()
    assert "plan" in data and isinstance(data["plan"], list)
    # Hiányzó oldal → 400.
    r2 = client.post("/scouting/matchup",
                     json={"own": {"items": []}})
    assert r2.status_code == 400


def test_season_report_endpoint():
    """Két tárolt meccsből a szezon-riport HTML összeáll; ismeretlen
    csapatnál 404."""
    client, mid = _client_with_match()
    # Második meccs ugyanazokkal a csapatnevekkel (másik seed).
    m2 = simulate_ground_truth(duration_s=5, fps=25.0, seed=2)
    matches_dir = Path(_tmp) / "data" / "matches"
    (matches_dir / f"{m2.meta.match_id}.json").write_text(
        json.dumps(m2.to_dict()), encoding="utf-8")
    client2 = TestClient(create_app())
    r = client2.get("/season/report",
                    params={"team": "Szimu Hazai"})
    assert r.status_code == 200
    assert "SZEZON-RIPORT" in r.text and "Szimu Hazai" in r.text
    assert "Fejlődés a szezonon belül" in r.text
    # A szezon meccsről meccsre tábla is ott van, az ellenféllel.
    assert "A szezon meccsről meccsre" in r.text
    assert "Szimu Vendég" in r.text
    # Hazai vs idegen mérleg-szakasz (mindkét meccs hazai volt).
    assert "Hazai vs idegen" in r.text
    # Ellenfél-mérleg: a két közös meccs egy sorba összegződik.
    assert "Ellenfél-mérleg" in r.text
    import re as _re
    row_o = _re.search(r"<tr><td>Szimu Vendég</td>"
                       r'<td class="num">(\d+)</td>', r.text)
    assert row_o and int(row_o.group(1)) == 2
    # A rövid (5 mp-es) sim-meccseken nincs toplista-adat — a szakasz
    # ilyenkor elegánsan elmarad (lásd a dedikált leaders-tesztet).
    assert "A szezon játékosai" not in r.text
    # Lövés nélkül tanult lövő és kapus-sáv sincs — a játékos-modell
    # szakasza is elmarad (lásd a dedikált modell-tesztet).
    assert "A szezon játékos-modellje" not in r.text
    assert client2.get("/season/report",
                       params={"team": "Nincs Ilyen"}).status_code == 404


def test_season_report_jatekos_modell_szakasz(monkeypatch):
    """A szezon-riport a csapat SZEZONBÓL tanult lövőit és a kapus
    sávjait hozza egy-egy sorban — a motor mondataival; a modell a csapat
    meccsenkénti nyers mintáiból épül (player_models_from_samples — itt
    két hazai meccs mintája, a lemezes eredmény-tárból)."""
    from handball.pipeline.play_simulation import AttackModel

    client, mid = _client_with_match()
    m2 = simulate_ground_truth(duration_s=5, fps=25.0, seed=2)
    matches_dir = Path(_tmp) / "data" / "matches"
    (matches_dir / f"{m2.meta.match_id}.json").write_text(
        json.dumps(m2.to_dict()), encoding="utf-8")
    latott = []

    def _modellek(mintak):
        latott.append(mintak)
        return {"tamadas": AttackModel(lovok={7: {"far": 1.3}}),
                "kapus": {"far": 1.2, "mid": 1.0}, "vedok": [], "sav": {},
                "lovo": {}}

    monkeypatch.setattr(
        "handball.pipeline.play_simulation.player_models_from_samples",
        _modellek)
    client2 = TestClient(create_app())
    r = client2.get("/season/report", params={"team": "Szimu Hazai"})
    assert r.status_code == 200
    # (a kész riport a címeket tartalomjegyzék-azonosítóval látja el —
    # a cím szövegét nézzük, nem a nyers <h2>-t)
    assert "A szezon játékos-modellje" in r.text
    assert ("<p><b>Lövők:</b> a lövők: a 7-es távolról 1,3× annyit lő be, "
            "mint amennyit a helyzetei érnek</p>") in r.text
    assert ("<p><b>Kapus:</b> a kapus távolról 1,2× annyi gólt kap, mint az "
            "átlag</p>") in r.text
    assert "a szezon 2 meccséből" in r.text
    [mintak] = latott[:1]
    assert len(mintak) == 2
    assert all(set(m) == {"lovo", "sav", "kapus", "vedok", "kockak"}
               for m in mintak)


def test_season_report_venue_split():
    """A pályaválasztás szerinti mérleg a jó oldalra könyveli a
    meccseket: egy hazai + egy idegen meccsből 1–1 kerül a sorokba."""
    client, mid = _client_with_match()
    m2 = simulate_ground_truth(duration_s=5, fps=25.0, seed=4)
    # A második meccsen a Szimu Hazai idegenben játszik.
    m2.meta.home_team = "Szimu Vendég"
    m2.meta.away_team = "Szimu Hazai"
    matches_dir = Path(_tmp) / "data" / "matches"
    (matches_dir / f"{m2.meta.match_id}.json").write_text(
        json.dumps(m2.to_dict()), encoding="utf-8")
    client2 = TestClient(create_app())
    r = client2.get("/season/report", params={"team": "Szimu Hazai"})
    assert r.status_code == 200
    assert "Hazai vs idegen" in r.text
    import re as _re
    row_h = _re.search(r"<tr><td>Hazai</td>"
                       r'<td class="num">(\d+)</td>', r.text)
    row_i = _re.search(r"<tr><td>Idegen</td>"
                       r'<td class="num">(\d+)</td>', r.text)
    assert row_h and row_i
    assert int(row_h.group(1)) >= 1 and int(row_i.group(1)) >= 1


def test_season_report_leaders_section():
    """Ha van toplista-adat (hosszabb meccseken labdaszerzés már
    mérhető), a szezon-riport hozza A szezon játékosai szakaszt."""
    import shutil
    tmp2 = tempfile.mkdtemp(prefix="handball_leaders_test_")
    os.environ["HANDBALL_DATA_DIR"] = tmp2
    matches_dir = Path(tmp2) / "data" / "matches"
    matches_dir.mkdir(parents=True, exist_ok=True)
    for seed in (2, 3):
        # 10 fps: a toplista másodperc-alapú (labdaszerzés/perc), a
        # rétegek az fps-ből számolnak — a ritkább mintavétel a
        # jelentést nem, a futásidőt viszont a felére viszi.
        m = simulate_ground_truth(duration_s=120, fps=10.0, seed=seed)
        (matches_dir / f"{m.meta.match_id}.json").write_text(
            json.dumps(m.to_dict()), encoding="utf-8")
    client = TestClient(create_app())
    r = client.get("/season/report", params={"team": "Szimu Hazai"})
    os.environ["HANDBALL_DATA_DIR"] = _tmp
    shutil.rmtree(tmp2, ignore_errors=True)
    assert r.status_code == 200
    assert "A szezon játékosai" in r.text
    assert "Labdaszerző" in r.text


def test_head_to_head_report_endpoint():
    """A két csapat egymás elleni riportja összeáll (mérleg + lista);
    közös meccs nélkül 404."""
    client, mid = _client_with_match()
    m2 = simulate_ground_truth(duration_s=5, fps=25.0, seed=3)
    matches_dir = Path(_tmp) / "data" / "matches"
    (matches_dir / f"{m2.meta.match_id}.json").write_text(
        json.dumps(m2.to_dict()), encoding="utf-8")
    client2 = TestClient(create_app())
    r = client2.get("/head-to-head/report",
                    params={"team_a": "Szimu Hazai",
                            "team_b": "Szimu Vendég"})
    assert r.status_code == 200
    assert "EGYMÁS ELLEN" in r.text
    assert "Mérleg (Szimu Hazai szemszögéből)" in r.text
    assert "Meccsről meccsre" in r.text
    # A rövid (5 mp-es) meccseken nincs tanult lövő és kapus-sáv — a
    # játékos-modell szakasza elmarad (lásd a dedikált tesztet).
    assert "Játékos-modell egymás ellen" not in r.text
    assert client2.get("/head-to-head/report",
                       params={"team_a": "Szimu Hazai",
                               "team_b": "Nincs Ilyen"}).status_code == 404


def test_head_to_head_report_jatekos_modell_szakasz(monkeypatch):
    """Az egymás-elleni riport a KÖZÖS meccsekből tanult lövőkkel és
    kapussal hozza a játékos-modell szakaszt mindkét csapatra: a lövők
    sora, az utolsó labda ellenük (a lövőik × a másik kapusa), az
    engedett lövő a falukban — a modellek csapatonként a közös meccsek
    nyers mintáiból épülnek (player_models_from_samples: előbb az A, aztán
    a B csapaté, ugyanannyi mintából)."""
    from handball.pipeline.play_simulation import AttackModel

    client, mid = _client_with_match()
    m2 = simulate_ground_truth(duration_s=5, fps=25.0, seed=3)
    matches_dir = Path(_tmp) / "data" / "matches"
    (matches_dir / f"{m2.meta.match_id}.json").write_text(
        json.dumps(m2.to_dict()), encoding="utf-8")
    latott = []

    def _modellek(mintak):
        latott.append(len(mintak))
        if len(latott) % 2 == 1:      # az A csapat (Szimu Hazai)
            return {"tamadas": AttackModel(lovok={7: {"far": 1.3}}),
                    "kapus": {}, "vedok": [], "sav": {},
                    "lovo": {}}
        return {"tamadas": AttackModel(lovok={4: {"far": 0.8}}),
                "kapus": {"far": 1.2}, "vedok": [], "sav": {},
                "lovo": {"4": {"far": [6, 1, 2.1]}}}

    monkeypatch.setattr(
        "handball.pipeline.play_simulation.player_models_from_samples",
        _modellek)
    client2 = TestClient(create_app())
    r = client2.get("/head-to-head/report",
                    params={"team_a": "Szimu Hazai",
                            "team_b": "Szimu Vendég"})
    assert r.status_code == 200
    assert "Játékos-modell egymás ellen (a közös meccsekből)" in r.text
    assert ("<h3>Szimu Hazai</h3><ul><li><b>Lövőik:</b> a lövők: a 7-es "
            "távolról 1,3× annyit lő be, mint amennyit a helyzetei érnek</li>"
            "<li><b>Utolsó labdájuk ellenük:</b> a 7-esé távolról") in r.text
    assert ("<li><b>Engedett lövő a falukban:</b> a 4-es ellen nem kell "
            "kilépni: távolról 0,8× annyit lő be, mint amennyit a helyzetei "
            "érnek (6 lövés, 1 gól)") in r.text
    assert ("<h3>Szimu Vendég</h3><ul><li><b>Lövőik:</b> a lövők: a 4-es "
            "távolról 0,8×") in r.text
    assert ("<li><b>Kapusuk:</b> a kapus távolról 1,2× annyi gólt kap, mint "
            "az átlag</li>") in r.text
    # A közös meccsek száma a könyvtár állapotától függ (a modul más
    # tesztjei is tesznek be közös meccset) — a két csapat modellje
    # ugyanannyi (legalább két) mintából épül.
    assert len(latott) == 2 and latott[0] == latott[1] >= 2
    assert f"a közös {latott[0]} meccsből tanulva" in r.text
