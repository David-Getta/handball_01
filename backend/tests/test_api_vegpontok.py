"""
Tesztek azokra az API-végpontokra, amelyeket eddig egyetlen teszt sem
hívott meg (a lefedettség-mérés szerint a kezelő-függvényük sosem futott):

- fiók: feltétel-elfogadás, jelszócsere;
- videó: referencia-képkocka, közvetítés-szakaszok;
- az elmentett kalibráció visszaolvasása;
- játékos-lap, pontosság-validáció;
- egyesített felderítés, fejlődés-követés (JSON + nyomtatható HTML);
- demó-meccs, figura törlése.

Mindegyiknél a pozitív eset mellett a "nincs miből" eset is: hiányzó
meccs / videó / kulcs / törzs → beszélő hibaválasz, nem 500.

Futtatás:
    python -m pytest tests/test_api_vegpontok.py -q
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

# A CI minimál-környezetében nincs FastAPI — ott ez a modul kihagyja magát.
TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient

from handball.api.app import create_app  # noqa: E402
from handball.sim.match_simulator import simulate_ground_truth  # noqa: E402


@pytest.fixture
def adat(tmp_path, monkeypatch):
    """Izolált adat-mappa: a teszt nem ír a fejlesztői data/ alá, és a
    tesztek nem látják egymás meccseit, fiókjait, figuráit."""
    monkeypatch.setenv("HANDBALL_DATA_DIR", str(tmp_path))
    return tmp_path


def _meccs(adat, seed=1, duration_s=20):
    """Lemezre írt szimulált meccs — a tár indításkor onnan tölt."""
    m = simulate_ground_truth(duration_s=duration_s, fps=25.0, seed=seed,
                              shots_per_min=8)
    m.meta.match_id = f"sim-{seed}"
    d = adat / "data" / "matches"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{m.meta.match_id}.json").write_text(json.dumps(m.to_dict()),
                                               encoding="utf-8")
    return m


def _fiok(client, email="edzo@pelda.hu", jelszo="jelszo12345"):
    r = client.post("/accounts/register",
                    json={"email": email, "password": jelszo,
                          "name": "Edző", "accept_terms": True})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


# ---- Fiók: feltétel-elfogadás -------------------------------------------------

def test_accept_terms_a_megujult_feltetelt_elfogadja(adat, monkeypatch):
    """Ha a feltételek új verziót kapnak, a fiók "terms_ok"-ja hamis lesz;
    az elfogadás végpontja (Bearer kulccsal) rendbe teszi, és az új
    verziót írja a fiókba."""
    from handball import accounts

    client = TestClient(create_app())
    token = _fiok(client)
    assert client.get("/accounts/me",
                      headers=_bearer(token)).json()["terms_ok"] is True

    uj = accounts.TERMS_VERSION + 1
    monkeypatch.setattr(accounts, "TERMS_VERSION", uj)
    assert client.get("/accounts/me",
                      headers=_bearer(token)).json()["terms_ok"] is False
    r = client.post("/accounts/accept-terms", headers=_bearer(token))
    assert r.status_code == 200, r.text
    assert r.json()["terms_ok"] is True
    assert r.json()["terms_version"] == uj
    assert r.json()["email"] == "edzo@pelda.hu"
    assert client.get("/accounts/me",
                      headers=_bearer(token)).json()["terms_ok"] is True


def test_accept_terms_a_kulcs_a_torzsben_is_johet(adat, monkeypatch):
    """A munkamenet-kulcs a kérés törzsében ("token") is megadható."""
    from handball import accounts

    client = TestClient(create_app())
    token = _fiok(client)
    monkeypatch.setattr(accounts, "TERMS_VERSION", accounts.TERMS_VERSION + 1)
    r = client.post("/accounts/accept-terms", json={"token": token})
    assert r.status_code == 200 and r.json()["terms_ok"] is True


def test_accept_terms_ervenytelen_kulccsal_401(adat):
    """Kulcs nélkül vagy ismeretlen kulccsal 401, magyar üzenettel — és
    senkinek a fiókja nem módosul."""
    client = TestClient(create_app())
    token = _fiok(client)
    for keres in ({}, {"headers": _bearer("nem-letezo-kulcs")},
                  {"json": {"token": "x" * 40}}):
        r = client.post("/accounts/accept-terms", **keres)
        assert r.status_code == 401, keres
        assert r.json()["detail"]
    assert client.get("/accounts/me",
                      headers=_bearer(token)).status_code == 200


# ---- Fiók: jelszócsere ---------------------------------------------------------

def test_change_password_uj_kulcsot_ad_es_a_regit_ervenyteleniti(adat):
    """A jelszócsere új munkamenet-kulcsot ad, a régi kulcs megszűnik;
    belépni az új jelszóval lehet, a régivel nem."""
    client = TestClient(create_app())
    regi = _fiok(client)
    r = client.post("/accounts/change-password", headers=_bearer(regi),
                    json={"old_password": "jelszo12345",
                          "new_password": "ujjelszo6789"})
    assert r.status_code == 200, r.text
    uj = r.json()["token"]
    assert uj and uj != regi
    assert r.json()["account"]["email"] == "edzo@pelda.hu"
    assert client.get("/accounts/me", headers=_bearer(regi)).status_code == 401
    assert client.get("/accounts/me", headers=_bearer(uj)).status_code == 200
    assert client.post("/accounts/login",
                       json={"email": "edzo@pelda.hu",
                             "password": "jelszo12345"}).status_code == 401
    assert client.post("/accounts/login",
                       json={"email": "edzo@pelda.hu",
                             "password": "ujjelszo6789"}).status_code == 200


def test_change_password_hibas_keresre_400_es_semmi_nem_valtozik(adat):
    """Rossz jelenlegi jelszó, túl rövid új jelszó vagy hiányzó kulcs →
    400 magyar üzenettel; a fiók a régi jelszóval és kulccsal él tovább."""
    client = TestClient(create_app())
    token = _fiok(client)

    rossz = client.post("/accounts/change-password", headers=_bearer(token),
                        json={"old_password": "nem-ez-volt",
                              "new_password": "ujjelszo6789"})
    assert rossz.status_code == 400
    assert "jelenlegi jelszó" in rossz.json()["detail"]
    rovid = client.post("/accounts/change-password", headers=_bearer(token),
                        json={"old_password": "jelszo12345",
                              "new_password": "rovid"})
    assert rovid.status_code == 400
    assert "legalább" in rovid.json()["detail"]
    kulcs_nelkul = client.post("/accounts/change-password",
                               json={"old_password": "jelszo12345",
                                     "new_password": "ujjelszo6789"})
    assert kulcs_nelkul.status_code == 400
    assert "bejelentkezés" in kulcs_nelkul.json()["detail"]

    assert client.get("/accounts/me", headers=_bearer(token)).status_code == 200
    assert client.post("/accounts/login",
                       json={"email": "edzo@pelda.hu",
                             "password": "jelszo12345"}).status_code == 200


# ---- Videó: referencia-képkocka és közvetítés-szakaszok -------------------------

def _video(path, jelenetek, kocka=30, meret=(160, 90)):
    """Kis próba-videó: jelenetenként egyszínű kockák (BGR), kis
    textúrával."""
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 25.0,
                         meret)
    for szin in jelenetek:
        for _ in range(kocka):
            img = np.full((meret[1], meret[0], 3), szin, np.uint8)
            img[::7, :] = 255
            vw.write(img)
    vw.release()
    return str(path)


def test_reference_frame_png_kepkockat_ad(adat, tmp_path):
    """A kalibráló képernyő képe: a kért kocka PNG-ben, a videó
    felbontásában — a második jelenetből a második jelenet színével."""
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    video = _video(tmp_path / "meccs.mp4", [(200, 40, 40), (40, 200, 40)])
    client = TestClient(create_app())

    r = client.get("/reference-frame", params={"path": video, "t": 45})
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"
    kep = cv2.imdecode(np.frombuffer(r.content, np.uint8), cv2.IMREAD_COLOR)
    assert kep.shape == (90, 160, 3)
    b, g, piros = (int(v) for v in kep[45, 80])
    assert g > b and g > piros                    # a zöld jelenet kockája
    elso = client.get("/reference-frame", params={"path": video, "t": 3})
    kep0 = cv2.imdecode(np.frombuffer(elso.content, np.uint8),
                        cv2.IMREAD_COLOR)
    b0, g0, _ = (int(v) for v in kep0[45, 80])
    assert b0 > g0                                # a kék jelenet kockája


def test_reference_frame_hianyzo_video_vagy_kocka(adat, tmp_path):
    """Nem létező videó → 400, a MIÉRT-tel (a felhasználó ezt látja); a
    videó végén túli kocka → 404."""
    video = _video(tmp_path / "rovid.mp4", [(200, 40, 40)], kocka=10)
    client = TestClient(create_app())

    nincs = client.get("/reference-frame",
                       params={"path": str(tmp_path / "nincs_ilyen.mp4")})
    assert nincs.status_code == 400
    assert "Nem találom a videót" in nincs.json()["detail"]
    tul = client.get("/reference-frame", params={"path": video, "t": 5000})
    assert tul.status_code == 404
    assert tul.json()["detail"] == "frame not read"


def test_broadcast_segments_a_vagasokat_es_a_szakaszokat_adja(adat, tmp_path):
    """Három jelenetes "közvetítés": a két jelenethatár vágás, három
    szakasz keletkezik; a `max` a feldolgozott kockák számát korlátozza."""
    video = _video(tmp_path / "kozvetites.mp4",
                   [(200, 40, 40), (40, 200, 40), (40, 40, 200)])
    client = TestClient(create_app())

    r = client.get("/broadcast/segments", params={"path": video, "stride": 1})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["n_frames"] == 90
    assert len(res["cuts"]) == 2
    assert all(28 <= c <= 32 or 58 <= c <= 62 for c in res["cuts"])
    assert len(res["segments"]) == 3
    rovid = client.get("/broadcast/segments",
                       params={"path": video, "stride": 1, "max": 20}).json()
    assert rovid["n_frames"] <= 20 and rovid["cuts"] == []


def test_broadcast_segments_hianyzo_videora_404(adat, tmp_path):
    """Nem létező videóra 404 (nem 500)."""
    client = TestClient(create_app())
    r = client.get("/broadcast/segments",
                   params={"path": str(tmp_path / "nincs_ilyen.mp4")})
    assert r.status_code == 404
    assert r.json()["detail"] == "video not found"


# ---- Az elmentett kalibráció visszaolvasása -------------------------------------

def test_get_calibration_visszaadja_az_elmentettet(adat):
    """Újrafeldolgozásnál nem kell újra bejelölni a sarkokat: a mentett
    kalibrációk visszajönnek — a kulcs a videó FÁJLNEVE, tehát az
    áthelyezett videó is megtalálja."""
    client = TestClient(create_app())
    calibs = [{"corners": [[10, 20], [300, 22], [310, 200], [5, 190]],
               "region": "left", "rotate": False, "frame": 100},
              {"corners": [[11, 21], [301, 23], [311, 201], [6, 191]],
               "region": "right", "rotate": True, "frame": 2500}]
    r = client.post("/calibration",
                    json={"path": "/videok/szombat/meccs.mp4",
                          "calibs": calibs})
    assert r.status_code == 200 and r.json() == {"saved": 2}

    assert client.get("/calibration", params={
        "path": "/videok/szombat/meccs.mp4"}).json() == {"calibs": calibs}
    assert client.get("/calibration", params={
        "path": "/masik/meghajto/meccs.mp4"}).json() == {"calibs": calibs}


def test_get_calibration_mentes_nelkul_vagy_serult_fajlnal_ures(adat):
    """Amihez nincs mentés, ahhoz üres lista jön (nem 404); a sérült vagy
    rossz alakú fájl sem dönti el a végpontot."""
    client = TestClient(create_app())
    ures = {"calibs": []}
    assert client.get("/calibration",
                      params={"path": "/videok/uj.mp4"}).json() == ures

    client.post("/calibration", json={"path": "/videok/serult.mp4",
                                      "calibs": [{"corners": [], "frame": 1}]})
    fajl = adat / "data" / "calibrations" / "serult.mp4.json"
    assert fajl.exists()
    fajl.write_text("{ez nem json", encoding="utf-8")
    assert client.get("/calibration",
                      params={"path": "/videok/serult.mp4"}).json() == ures
    fajl.write_text(json.dumps({"calibs": "nem lista"}), encoding="utf-8")
    assert client.get("/calibration",
                      params={"path": "/videok/serult.mp4"}).json() == ures


# ---- Játékos-lap -----------------------------------------------------------------

def test_player_report_kioszthato_html_lap(adat):
    """Egy játékos meccs-riportja HTML-ben: a lap a játékost és a meccs
    két csapatát megnevezi."""
    m = _meccs(adat)
    track = min(p.track_id for p in m.frames[0].players)
    client = TestClient(create_app())

    r = client.get(f"/matches/{m.meta.match_id}/players/{track}/report")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/html")
    assert r.text.lstrip().startswith("<!DOCTYPE html>")
    assert "Játékos-lap" in r.text
    assert m.meta.home_team in r.text and m.meta.away_team in r.text


def test_player_report_ismeretlen_jatekos_vagy_meccs_404(adat):
    """Ismeretlen track → 404 "player not found"; ismeretlen meccs → 404
    "match not found" (nem 500)."""
    m = _meccs(adat)
    client = TestClient(create_app())

    nincs_jatekos = client.get(
        f"/matches/{m.meta.match_id}/players/987654/report")
    assert nincs_jatekos.status_code == 404
    assert nincs_jatekos.json()["detail"] == "player not found"
    nincs_meccs = client.get("/matches/nincs-ilyen/players/1/report")
    assert nincs_meccs.status_code == 404
    assert nincs_meccs.json()["detail"] == "match not found"


# ---- Pontosság-validáció ------------------------------------------------------------

def test_validate_a_sajat_sablonjara_tokeletes(adat):
    """A motor felismert eseményeiből készült sablont (truth_csv)
    visszaadva minden találat (nincs téves, nincs kimaradt): precizitás
    és visszahívás 100%, megfelelt ítélettel."""
    m = _meccs(adat)
    client = TestClient(create_app())
    sablon = client.get(f"/matches/{m.meta.match_id}/validate-template").text
    sorok = [s for s in sablon.splitlines() if s and not s.startswith("#")]
    assert sorok, "a próba-meccsen nincs felismert esemény"

    r = client.post(f"/matches/{m.meta.match_id}/validate",
                    json={"truth_csv": sablon})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["tol_s"] == 3.0
    assert res["overall"]["tp"] == len(sorok)
    assert res["overall"]["fp"] == 0 and res["overall"]["fn"] == 0
    assert res["overall"]["precision"] == 1.0
    assert res["overall"]["recall"] == 1.0
    assert res["verdict"]["pass"] is True


def test_validate_a_kimaradt_es_a_teves_esemenyt_megnevezi(adat):
    """A kézi igazság egy plusz góllal (amit a motor nem talált) és a
    motor egyik góljának elhagyásával: 1 kimaradt (fn) és 1 téves (fp) —
    a lista (`truth`) alak és a saját tűrés (`tol_s`) is működik."""
    m = _meccs(adat)
    client = TestClient(create_app())
    teljes = client.post(f"/matches/{m.meta.match_id}/validate", json={
        "truth_csv": client.get(
            f"/matches/{m.meta.match_id}/validate-template").text}).json()
    n = teljes["by_type"]["goal"]["tp"]
    assert n >= 2, "a próba-meccsen legalább két felismert gól kell"

    sablon = client.get(f"/matches/{m.meta.match_id}/validate-template").text
    golok = [s for s in sablon.splitlines()
             if s and not s.startswith("#") and "gól" in s]

    def mp(sor):
        perc, masodperc = sor.split(",")[0].strip().split(":")
        return 60 * int(perc) + int(masodperc)

    truth = [{"t_s": mp(s), "type": "gól"} for s in golok[1:]]
    truth.append({"t_s": 19.0, "type": "gól"})        # a motor nem látta
    r = client.post(f"/matches/{m.meta.match_id}/validate",
                    json={"truth": truth, "tol_s": 1.5})
    assert r.status_code == 200, r.text
    gol = r.json()["by_type"]["goal"]
    assert r.json()["tol_s"] == 1.5
    assert (gol["tp"], gol["fp"], gol["fn"]) == (n - 1, 1, 1)
    assert len(gol["missed"]) == 1 and len(gol["spurious"]) == 1
    assert gol["precision"] < 1.0 and gol["recall"] < 1.0


def test_validate_ures_igazsagra_nincs_arany_es_html_is_keszul(adat):
    """Üres igazság-listánál nincs mihez mérni: a visszahívás None (nem
    hallgatólagos 0 vagy 100%); `format: html` nyomtatható lapot ad; a
    rossz tűrés (nem szám) az alapértékre esik vissza."""
    m = _meccs(adat)
    client = TestClient(create_app())

    r = client.post(f"/matches/{m.meta.match_id}/validate",
                    json={"truth": [], "tol_s": "nem szám"})
    assert r.status_code == 200, r.text
    assert r.json()["tol_s"] == 3.0
    assert r.json()["overall"]["tp"] == 0
    assert r.json()["overall"]["recall"] is None
    html = client.post(f"/matches/{m.meta.match_id}/validate",
                       json={"truth": [], "format": "html"})
    assert html.status_code == 200
    assert html.headers["content-type"].startswith("text/html")
    assert m.meta.home_team in html.text


def test_validate_hianyzo_igazsag_vagy_meccs(adat):
    """Igazság nélkül (vagy rossz alakkal) 400; ismeretlen meccsre 404."""
    m = _meccs(adat)
    client = TestClient(create_app())

    for torzs in ({}, {"truth": "nem lista"}, {"truth_csv": 5}):
        r = client.post(f"/matches/{m.meta.match_id}/validate", json=torzs)
        assert r.status_code == 400, torzs
        assert r.json()["detail"] == "truth list or truth_csv string required"
    assert client.post("/matches/nincs-ilyen/validate",
                       json={"truth": []}).status_code == 404


# ---- Egyesített felderítés és fejlődés-követés -----------------------------------------

def test_combined_scouting_egy_es_tobb_meccsbol(adat):
    """Egy meccsből az egyesített jelentés maga a meccs jelentése; két
    meccsből a meccsszám 2, a csapat ugyanaz."""
    a, b = _meccs(adat, seed=1), _meccs(adat, seed=2)
    client = TestClient(create_app())

    egy = client.post("/scouting", json={"items": [
        {"match_id": a.meta.match_id, "team": "home"}]})
    assert egy.status_code == 200, egy.text
    assert egy.json()["matches"] == 1
    assert egy.json()["team"] == "home"
    assert egy.json()["team_name"] == a.meta.home_team
    sajat = client.get(f"/matches/{a.meta.match_id}/scouting",
                       params={"team": "home"}).json()
    assert egy.json()["attack_share_pct"] == sajat["attack_share_pct"]

    ketto = client.post("/scouting", json={"items": [
        {"match_id": a.meta.match_id, "team": "home"},
        {"match_id": b.meta.match_id, "team": "home"}]})
    assert ketto.status_code == 200, ketto.text
    assert ketto.json()["matches"] == 2
    assert ketto.json()["team_name"] == a.meta.home_team


def test_combined_scouting_hibas_torzsre_beszelo_hiba(adat):
    """Tétel nélkül 400, ismeretlen meccsre 404 (a meccs nevével), rossz
    csapat-kulcsra 400."""
    a = _meccs(adat)
    client = TestClient(create_app())

    for torzs in ({}, {"items": []}, {"items": "nem lista"}):
        r = client.post("/scouting", json=torzs)
        assert r.status_code == 400 and r.json()["detail"] == "items required"
    nincs = client.post("/scouting", json={"items": [
        {"match_id": "nincs-ilyen", "team": "home"}]})
    assert nincs.status_code == 404
    assert "nincs-ilyen" in nincs.json()["detail"]
    rossz = client.post("/scouting", json={"items": [
        {"match_id": a.meta.match_id, "team": "kozep"}]})
    assert rossz.status_code == 400
    assert "home" in rossz.json()["detail"]


def test_scouting_trend_ket_idoszak_osszevetese(adat):
    """Két időszak (régi / új) mutatónként: régi és új érték, változás,
    és a javult/romlott minősítés — ugyanazt a meccset önmagával vetve
    minden változás 0 és nincs mit kiemelni."""
    a, b = _meccs(adat, seed=1), _meccs(adat, seed=2)
    client = TestClient(create_app())
    regi = {"items": [{"match_id": a.meta.match_id, "team": "home"}]}
    uj = {"items": [{"match_id": b.meta.match_id, "team": "home"}]}

    r = client.post("/scouting/trend", json={"older": regi, "newer": uj})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["team_name"] == a.meta.home_team
    assert (res["older_matches"], res["newer_matches"]) == (1, 1)
    assert res["metrics"], "nincs összevetett mutató"
    for sor in res["metrics"]:
        assert {"metric", "label", "older", "newer", "delta",
                "better"} <= set(sor)
        assert sor["better"] in (True, False, None)
    assert isinstance(res["summary"], list)

    onmaga = client.post("/scouting/trend",
                         json={"older": regi, "newer": regi}).json()
    assert all(sor["delta"] == 0 for sor in onmaga["metrics"])
    assert all(sor["better"] is None for sor in onmaga["metrics"])


def test_scouting_trend_export_nyomtathato_html(adat):
    """Ugyanazzal a törzzsel a fejlődés-riport nyomtatható HTML-ben."""
    a, b = _meccs(adat, seed=1), _meccs(adat, seed=2)
    client = TestClient(create_app())
    torzs = {"older": {"items": [{"match_id": a.meta.match_id,
                                  "team": "home"}]},
             "newer": {"items": [{"match_id": b.meta.match_id,
                                  "team": "home"}]}}

    r = client.post("/scouting/trend/export", json=torzs)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/html")
    assert "Fejlődés-riport" in r.text
    assert a.meta.home_team in r.text
    # A lap mutatói a JSON-végpont mutatói.
    mutatok = client.post("/scouting/trend", json=torzs).json()["metrics"]
    assert mutatok[0]["label"] in r.text


def test_scouting_trend_hianyzo_idoszakra_400(adat):
    """Mindkét időszak kell (a JSON és a HTML végpontnak is); a hiányzó
    meccs 404."""
    a = _meccs(adat)
    client = TestClient(create_app())
    egy = {"items": [{"match_id": a.meta.match_id, "team": "home"}]}

    for ut in ("/scouting/trend", "/scouting/trend/export"):
        for torzs in ({}, {"older": egy}, {"newer": egy},
                      {"older": egy, "newer": {}}):
            r = client.post(ut, json=torzs)
            assert r.status_code == 400, (ut, torzs)
            assert r.json()["detail"] == "older and newer required"
        nincs = client.post(ut, json={"older": egy, "newer": {"items": [
            {"match_id": "nincs-ilyen", "team": "home"}]}})
        assert nincs.status_code == 404, ut


# ---- Demó-meccs ---------------------------------------------------------------------------

def test_create_demo_match_videó_nelkul_kiprobalhato(adat):
    """A demó-meccs bekerül a könyvtárba (és a lemezre), saját
    azonosítóval és névvel; ugyanazzal a seeddel ugyanakkora meccs
    készül, de mindig új azonosítóval."""
    client = TestClient(create_app())

    r = client.post("/matches/demo", json={"seconds": 10, "seed": 3})
    assert r.status_code == 200, r.text
    mid = r.json()["match_id"]
    assert mid.startswith("demo-")
    assert r.json()["num_frames"] > 10 * 25          # + a demó-epizódok
    lista = {m["match_id"]: m for m in client.get("/matches").json()["matches"]}
    assert lista[mid]["home_team"] == "Demó Hazai"
    assert lista[mid]["away_team"] == "Demó Vendég"
    assert lista[mid]["num_frames"] == r.json()["num_frames"]
    assert (adat / "data" / "matches" / f"{mid}.json").exists()
    # Az elemzés azonnal megy rajta.
    assert client.get(f"/matches/{mid}/positions").status_code == 200

    masik = client.post("/matches/demo", json={"seconds": 10, "seed": 3})
    assert masik.json()["match_id"] != mid
    assert masik.json()["num_frames"] == r.json()["num_frames"]


def test_create_demo_match_a_hossz_esszeru_keretek_kozt(adat):
    """Törzs nélkül is készül demó (30 mp); a túl rövid kérés 5 mp-re, a
    túl hosszú 120 mp-re szorul — nem készül sem üres, sem órás meccs."""
    client = TestClient(create_app())

    alap = client.post("/matches/demo")
    assert alap.status_code == 200, alap.text
    rovid = client.post("/matches/demo", json={"seconds": 0}).json()
    ot_mp = client.post("/matches/demo", json={"seconds": 5}).json()
    assert rovid["num_frames"] == ot_mp["num_frames"] > 0
    hosszu = client.post("/matches/demo", json={"seconds": 99999}).json()
    szazhusz = client.post("/matches/demo", json={"seconds": 120}).json()
    assert hosszu["num_frames"] == szazhusz["num_frames"]
    assert ot_mp["num_frames"] < alap.json()["num_frames"] \
        < szazhusz["num_frames"]


# ---- Figura törlése --------------------------------------------------------------------------

def test_delete_play_torli_a_figurat_a_konyvtarbol(adat):
    """A törölt figura eltűnik a listából és a lemezről; a másik marad."""
    client = TestClient(create_app())
    utak = [[[25.0, 8.0], [32.0, 10.0]], [[25.0, 12.0], [31.0, 9.0]]]
    egyik = client.post("/playbook", json={"name": "Kereszt",
                                           "attackers": utak}).json()["id"]
    masik = client.post("/playbook", json={"name": "Beálló-leválás",
                                           "attackers": utak}).json()["id"]

    r = client.delete(f"/playbook/{egyik}")
    assert r.status_code == 200 and r.json() == {"deleted": egyik}
    assert [p["id"] for p in client.get("/playbook").json()["plays"]] == [masik]
    assert client.get(f"/playbook/{egyik}").status_code == 404
    assert not list((adat / "data" / "playbook").glob(f"{egyik}*"))


def test_delete_play_ismeretlen_figurara_404(adat):
    """Nem létező (vagy már törölt) figura törlése 404 — nem 500, és a
    könyvtár többi figurája érintetlen."""
    client = TestClient(create_app())
    utak = [[[25.0, 8.0], [32.0, 10.0]]]
    marad = client.post("/playbook", json={"name": "Marad",
                                           "attackers": utak}).json()["id"]

    r = client.delete("/playbook/nincsilyen")
    assert r.status_code == 404 and r.json()["detail"] == "play not found"
    torolt = client.post("/playbook", json={"name": "Megy",
                                            "attackers": utak}).json()["id"]
    assert client.delete(f"/playbook/{torolt}").status_code == 200
    assert client.delete(f"/playbook/{torolt}").status_code == 404
    assert [p["id"] for p in client.get("/playbook").json()["plays"]] == [marad]
