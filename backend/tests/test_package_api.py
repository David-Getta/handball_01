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
    assert all(set(m) == {"lovo", "sav", "kapus", "vedok", "kockak", "kapusok",
                          "formak"}
               for m in mintak)


def test_season_report_jatekos_modell_fejlodes(monkeypatch):
    """A szezon-riport a két fél (a fejlődés-tábla vágása) külön tanult
    lövőit és kapusát veti össze: a régebbi fél egy meccsének mintájából
    0,9×, az újabbéból 1,2× → "javul" sor; a két fél modellje a fél
    meccseinek nyers mintáiból épül (player_models_from_samples — az
    egész szezon után előbb a régebbi, aztán az újabb fél, egy-egy
    mintából)."""
    from handball.pipeline.play_simulation import AttackModel

    client, mid = _client_with_match()
    m2 = simulate_ground_truth(duration_s=5, fps=25.0, seed=2)
    matches_dir = Path(_tmp) / "data" / "matches"
    (matches_dir / f"{m2.meta.match_id}.json").write_text(
        json.dumps(m2.to_dict()), encoding="utf-8")
    hivasok = []

    def _modellek(mintak):
        hivasok.append(len(mintak))
        ures = {"tamadas": AttackModel(), "kapus": {}, "vedok": [],
                "sav": {}, "lovo": {}}
        if len(mintak) != 1:
            return ures
        egyes = sum(1 for n in hivasok if n == 1)
        return {**ures, "tamadas": AttackModel(
            lovok={7: {"far": 0.9 if egyes == 1 else 1.2}})}

    monkeypatch.setattr(
        "handball.pipeline.play_simulation.player_models_from_samples",
        _modellek)
    client2 = TestClient(create_app())
    r = client2.get("/season/report", params={"team": "Szimu Hazai"})
    assert r.status_code == 200
    assert hivasok[-3:] == [2, 1, 1]
    assert "A játékos-modell fejlődése (első fél → második fél)" in r.text
    assert "<li>a 7-es távolról 0,9× → 1,2× (javul)</li>" in r.text


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


def test_season_report_elorejelzes_sora(monkeypatch):
    """A szezon-riport próba-szakaszának "Előrejelzés" sora: a könyvtári
    meccs-előrejelzés próbájából a csapat sorai (forecast_rows_summary) —
    a valódi láncon (hét rövid meccs, időrendben) ugyanaz, mint a motor
    a meccs-mintákból; a "Gólszerzők" sor a csapat lövőinek próbája
    (scorer_forecast_backtest), az "Élő esély" sor a csapat meccsein
    (in_play_backtest)."""
    import shutil

    import handball.pipeline.play_simulation as ps
    from handball.models.tracking import Team
    from handball.pipeline.play_simulation import (forecast_backtest,
                                                   forecast_backtest_text,
                                                   forecast_rows_summary,
                                                   in_play_backtest,
                                                   match_forecast_sample,
                                                   player_model_sample,
                                                   scorer_forecast_backtest)
    # Az élő esély percei a félperces felvételhez igazítva.
    monkeypatch.setattr(ps, "LIVE_AJANLO_PERCEK", (0.1, 0.2, 0.3))
    tmp2 = tempfile.mkdtemp(prefix="handball_elorejelzes_test_")
    os.environ["HANDBALL_DATA_DIR"] = tmp2
    try:
        matches_dir = Path(tmp2) / "data" / "matches"
        matches_dir.mkdir(parents=True, exist_ok=True)
        lista, jm = [], []
        for seed in range(1, 8):
            m = simulate_ground_truth(duration_s=30, fps=10.0, seed=seed,
                                      shots_per_min=8)
            m.meta.match_id = f"ej{seed}"
            m.meta.date = f"2026-10-0{seed}"
            (matches_dir / f"{m.meta.match_id}.json").write_text(
                json.dumps(m.to_dict()), encoding="utf-8")
            lista.append({"match_id": m.meta.match_id,
                          "home": m.meta.home_team, "away": m.meta.away_team,
                          "minta": json.loads(json.dumps(
                              match_forecast_sample(m)))})
            jm.append({"match_id": m.meta.match_id,
                       "home": m.meta.home_team, "away": m.meta.away_team,
                       "minta": {side: json.loads(json.dumps(
                           player_model_sample(m, t))) for side, t in (
                               ("home", Team.HOME), ("away", Team.AWAY))}})
        ep = forecast_rows_summary(forecast_backtest(lista)["sorok"],
                                   "Szimu Hazai")
        assert ep is not None
        gp = scorer_forecast_backtest(jm, "Szimu Hazai")
        ip = in_play_backtest(lista, "Szimu Hazai")
        assert ip is not None
        from handball.models.tracking import Match
        from handball.pipeline.primitive_cache import primitive_cache
        from handball.pipeline.setplays import (figure_recurrence_backtest,
                                                setplay_shapes)
        figm = []
        for x in lista:
            mm = Match.from_dict(json.loads(
                (matches_dir / f"{x['match_id']}.json").read_text(
                    encoding="utf-8")))
            with primitive_cache(mm):
                figm.append({**x, "alakok": json.loads(json.dumps(
                    setplay_shapes(mm)))})
        fp = figure_recurrence_backtest(figm, "Szimu Hazai")
        from handball.pipeline.play_simulation import (
            keeper_form_sample, keeper_hot_hand_backtest)
        kp = keeper_hot_hand_backtest([json.loads(json.dumps(
            keeper_form_sample(Match.from_dict(json.loads(
                (matches_dir / f"{x['match_id']}.json").read_text(
                    encoding="utf-8"))), Team.HOME))) for x in lista])
        from handball.pipeline.play_simulation import keeper_choice_backtest
        kvp = keeper_choice_backtest(jm, "Szimu Hazai")
        from handball.pipeline.play_simulation import (seven_taker_backtest,
                                                       seven_taker_sample)
        hp = seven_taker_backtest([{**x, "minta": {
            s_: seven_taker_sample(Match.from_dict(json.loads(
                (matches_dir / f"{x['match_id']}.json").read_text(
                    encoding="utf-8"))), Team(s_)) for s_ in ("home", "away")}}
            for x in lista], "Szimu Hazai")
        from handball.pipeline.scouting import scouting_backtest, scout_team
        fdp = scouting_backtest([{**x, "reports": {
            s_: scout_team(Match.from_dict(json.loads(
                (matches_dir / f"{x['match_id']}.json").read_text(
                    encoding="utf-8"))), Team(s_)) for s_ in ("home", "away")}}
            for x in lista], "Szimu Hazai")
        from handball.pipeline.play_simulation import (
            run_timeout_sample, timeout_run_backtest)
        tp = timeout_run_backtest([{**x, "minta": json.loads(json.dumps(
            run_timeout_sample(Match.from_dict(json.loads(
                (matches_dir / f"{x['match_id']}.json").read_text(
                    encoding="utf-8"))))))} for x in lista], "Szimu Hazai")
        r = TestClient(create_app()).get("/season/report",
                                         params={"team": "Szimu Hazai"})
    finally:
        os.environ["HANDBALL_DATA_DIR"] = _tmp
        shutil.rmtree(tmp2, ignore_errors=True)
    assert r.status_code == 200
    assert "A modellek próbája" in r.text
    assert (f"<p><b>Előrejelzés:</b> {forecast_backtest_text(ep)}.</p>"
            in r.text)
    # A várható gólszerzők próbája a csapat lövőire (a motorral egyezik;
    # kevés párnál a sor elmarad).
    if gp:
        assert f"<p><b>Gólszerzők:</b> {gp['verdict']}.</p>" in r.text
    else:
        assert "<b>Gólszerzők:</b>" not in r.text
    # Az élő esély próbája a csapat meccsein (in_play_backtest).
    assert f"<p><b>Élő esély:</b> {ip['verdict']}.</p>" in r.text
    # A szezon kulcsemberei (gól-érték a cserénél) a motorból.
    from handball.pipeline.play_simulation import season_key_players
    ks = season_key_players([x["minta"]["home"]["lovo"] for x in jm])
    if ks:
        assert "Kulcsemberek (gól-érték a cserénél)" in r.text
        assert f"<li>{ks[0]['verdict']}</li>" in r.text
    else:
        assert "Kulcsemberek (gól-érték a cserénél)" not in r.text
    # A figuráik próbája a csapat meccsein (a motorral egyezik; kevés
    # figuránál a sor elmarad).
    if fp:
        assert f"<p><b>Figurák:</b> {fp['verdict']}.</p>" in r.text
    else:
        assert "<b>Figurák:</b>" not in r.text
    # A kapusaik napi formájának próbája (a motorral egyezik; a félperces
    # meccseken kevés a lövés egy félidőre — a sor elmarad).
    if kp:
        assert f"<p><b>Kapus napi formája:</b> {kp['verdict']}.</p>" in r.text
    else:
        assert "<b>Kapus napi formája:</b>" not in r.text
    # A hetes-dobó választásuk próbája (a motorral egyezik; a szimulált
    # hetesnek nincs azonosított dobója — a sor elmarad).
    if hp:
        assert f"<p><b>Hetes-dobó:</b> {hp['verdict']}.</p>" in r.text
    else:
        assert "<b>Hetes-dobó:</b>" not in r.text
    # A felderítésük próbája (a motorral egyezik; hét meccsen öt mérhető).
    if fdp:
        assert f"<p><b>Felderítés:</b> {fdp['verdict']}.</p>" in r.text
    else:
        assert "<b>Felderítés:</b>" not in r.text
    # A kapus-választásuk próbája (a motorral egyezik; egy kapusnál a sor
    # elmarad).
    if kvp:
        assert f"<p><b>Kapus-választás:</b> {kvp['verdict']}.</p>" in r.text
    else:
        assert "<b>Kapus-választás:</b>" not in r.text
    # Az időkéréseik próbája a sorozat ellen (a motorral egyezik; a
    # szimulált meccseken nincs időkérés — a sor elmarad).
    if tp:
        assert (f"<p><b>Időkérés a sorozat ellen:</b> {tp['verdict']}.</p>"
                in r.text)
    else:
        assert "<b>Időkérés a sorozat ellen:</b>" not in r.text


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
