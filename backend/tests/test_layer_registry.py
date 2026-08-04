"""
Réteg-regisztry füstteszt: egyetlen réteg sem bukhat el némán.

A meccs-csomag `_layer` segédje és a végpontok `try/except`
blokkjai szándékosan hibatűrőek — egy réteg hibája nem viheti el a
többit. Ennek az az ára, hogy egy elromló motor NÉMÁN tűnik el a
kimenetből. Ez a teszt zárja a rést: a forrásból kiolvassa az összes
regisztrált réteg nevét, lefuttat egy szimulált meccset a teljes
csomagon és az összes elemzés-végponton, és követeli, hogy minden
regisztrált réteg ott legyen a kimenetben.

Önfrissülő: új réteg felvételekor semmit nem kell ide írni — a nevet
a forrásból olvassuk, így az új réteg automatikusan őrzés alá kerül.

Futtatás:
    python -m pytest tests/test_layer_registry.py
"""

from __future__ import annotations

import io
import json
import os
import re
import sys
import tempfile
import time
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_tmp = tempfile.mkdtemp(prefix="handball_layer_registry_test_")
os.environ["HANDBALL_DATA_DIR"] = _tmp

import pytest  # noqa: E402

TestClient = pytest.importorskip(
    "fastapi.testclient", reason="fastapi nincs telepítve").TestClient

from handball.api.app import create_app  # noqa: E402
from handball.sim.match_simulator import simulate_ground_truth  # noqa: E402

_APP_PY = (Path(__file__).resolve().parent.parent
           / "handball" / "api" / "app.py")

# Feltételes kulcsok a végpont-válaszokban: az első félidős (_fh)
# bontások csak felismert félidei szünetnél kerülnek a válaszba, a
# first_half_close pedig csak akkor, ha az első félidő szoros volt.
# A rövid szimulált meccsen ezek jogosan hiányoznak.
_CONDITIONAL_KEYS = {"first_half_close"}


def _client_with_match():
    os.environ["HANDBALL_DATA_DIR"] = _tmp
    m = simulate_ground_truth(duration_s=8, fps=25.0, seed=1)
    matches_dir = Path(_tmp) / "data" / "matches"
    matches_dir.mkdir(parents=True, exist_ok=True)
    (matches_dir / f"{m.meta.match_id}.json").write_text(
        json.dumps(m.to_dict()), encoding="utf-8")
    return TestClient(create_app()), m.meta.match_id


def _wait_job(client, job_id, timeout_s=120):
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        job = client.get(f"/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            return job
        time.sleep(0.2)
    raise AssertionError("a csomag-job nem fejeződött be időben")


def _registered_package_layers() -> list[str]:
    src = _APP_PY.read_text(encoding="utf-8")
    return re.findall(r'_layer\(\s*"([a-z0-9_]+)"', src)


def test_package_minden_regisztralt_reteg_elkeszul():
    """A csomag elemzés-JSON-jában MINDEN `_layer(...)`-rel regisztrált
    réteg ott van — egy kivétellel elhasaló motor itt bukna ki, mert a
    `_layer` a hibát lenyeli, a kulcs pedig hiányozna."""
    names = _registered_package_layers()
    assert len(names) > 200, "a regisztry-olvasás elromlott"
    client, mid = _client_with_match()
    r = client.post(f"/matches/{mid}/package/export",
                    json={"clip_types": []})
    job = _wait_job(client, r.json()["job_id"])
    assert job["status"] == "done", job
    pkg = client.get(f"/matches/{mid}/package/download")
    assert pkg.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(pkg.content))
    analyses = json.loads(z.read("elemzesek.json").decode("utf-8"))
    missing = sorted(set(names) - set(analyses))
    assert not missing, f"némán elbukott rétegek a csomagban: {missing}"


def test_package_reteg_nevek_egyediek():
    """Két azonos nevű `_layer(...)` regisztráció némán felülírná
    egymást a csomagban — a neveknek egyedieknek kell lenniük."""
    names = _registered_package_layers()
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert not dupes, f"duplán regisztrált réteg-nevek: {dupes}"


def _endpoint_registries() -> dict[str, set[str]]:
    """Minden GET /matches/{match_id}/... végpont, amelyben
    `res["..."]` kulcs-regisztráció van: {útvonal: kulcsok}."""
    src = _APP_PY.read_text(encoding="utf-8")
    parts = re.split(r'@app\.get\("(/matches/\{match_id\}/[^"]+)"\)', src)
    out: dict[str, set[str]] = {}
    for i in range(1, len(parts), 2):
        path, body = parts[i], parts[i + 1]
        body = re.split(r'@app\.(get|post|delete|put)\(', body)[0]
        if "{" in path.replace("{match_id}", ""):
            continue  # további útvonal-paraméteres végpont kimarad
        keys = set(re.findall(r'res\["([a-z0-9_]+)"\]\s*=', body))
        if keys:
            out[path] = keys
    return out


def test_vegpontok_minden_regisztralt_kulcs_elkeszul():
    """Minden elemzés-végpont válaszában ott van minden
    `res["..."]`-ként bekötött kulcs — a félidő-feltételes (_fh és
    first_half_close) kulcsok kivételével, amelyek a rövid szimulált
    meccsen jogosan hiányoznak."""
    registries = _endpoint_registries()
    assert len(registries) >= 4, "a végpont-olvasás elromlott"
    assert sum(len(k) for k in registries.values()) > 200, \
        "a kulcs-olvasás elromlott"
    client, mid = _client_with_match()
    problems = []
    for path, registered in sorted(registries.items()):
        r = client.get(path.replace("{match_id}", mid))
        if r.status_code != 200:
            problems.append(f"{path}: HTTP {r.status_code}")
            continue
        body = r.json()
        missing = registered - set(body if isinstance(body, dict) else {})
        unexpected = sorted(
            k for k in missing
            if not k.endswith("_fh")
            and k not in _CONDITIONAL_KEYS)
        if unexpected:
            problems.append(f"{path}: {unexpected}")
    assert not problems, \
        f"némán elbukott kulcsok a végpontokon: {problems}"


# Örökölt, szándékosan nem összegzett felderítés-mezők: azonosító és
# százalék jellegűek, amelyek meccsek közt nem adhatók össze. ÚJ réteg
# mezője ide NEM kerülhet — darabszám/összeg alapú tárolással minden
# új mező összegezhető (lásd CLAUDE.md).
_LEGACY_UNMERGED_FIELDS = {
    "top_assist_id", "top_assist_count", "playmaker_id",
    "playmaker_involvement_pct", "playmaker_drop",
    "playmaker_dependency",
}


def test_combine_reports_minden_mezot_kezel():
    """A felderítési recept legkönnyebben felejthető lépése a
    combine_reports-összegzés: a kimaradó mező több meccs
    összefésülésekor NÉMÁN az alapértékére esne vissza. Minden
    ScoutingReport-mezőnek szerepelnie kell a combine_reports
    törzsében — az örökölt kivétel-lista bővítése tilos."""
    import dataclasses
    import inspect

    from handball.pipeline import scouting

    src = inspect.getsource(scouting.combine_reports)
    unmentioned = [
        f.name for f in dataclasses.fields(scouting.ScoutingReport)
        if f.name not in src and f.name not in _LEGACY_UNMERGED_FIELDS]
    assert not unmentioned, (
        f"a combine_reports nem kezeli ezeket a mezőket: {unmentioned}")


# A kliens-csempék beágyazott sor-kulcsai: ezek nem ScoutingReport-
# mezők, hanem lista-elemek belső kulcsai (player_id, frames, ...)
# vagy más térképből olvasott értékek. Zárt lista — új felső szintű
# kulcs ide nem kerülhet.
_DART_ROW_KEYS = {
    "breaks", "chances", "count", "def_frames", "depth_sum_m",
    "frames", "jersey", "narrative", "player_id", "setter_id",
    "shooter_id", "sprints", "takes",
}


def test_kliens_kulcsok_letezo_mezok():
    """A kliens minden csempe-helperje r["..."] kulcsokkal olvassa a
    felderítés-profilt — egy elgépelt kulcs némán üres csempét adna.
    Minden Dart-oldali kulcsnak létező ScoutingReport-mezőnek kell
    lennie (a beágyazott sor-kulcsok zárt listája kivétel)."""
    import dataclasses

    from handball.pipeline import scouting

    dart = (Path(__file__).resolve().parent.parent.parent
            / "client" / "lib" / "ui" / "scouting_screen.dart")
    if not dart.exists():
        pytest.skip("nincs kliens a fában")
    keys = set(re.findall(r'r\["([a-z0-9_]+)"\]',
                          dart.read_text(encoding="utf-8")))
    assert len(keys) > 400, "a kulcs-olvasás elromlott"
    fields = {f.name for f in dataclasses.fields(scouting.ScoutingReport)}
    unknown = sorted(keys - fields - _DART_ROW_KEYS)
    assert not unknown, (
        f"a kliens nem létező felderítés-mezőket olvas: {unknown}")


def test_szabaly_sorszamok_egyediek():
    """A meccsterv- és edzés-szabályok sorszámozott kommentjei ("# NNN)")
    nem ismétlődhetnek — a duplikált szám a recept számláló-frissítés
    lépésének kihagyását jelzi."""
    for mod in ("scouting", "training"):
        src = (Path(__file__).resolve().parent.parent
               / "handball" / "pipeline" / f"{mod}.py").read_text(
                   encoding="utf-8")
        nums = re.findall(r'^\s*# (\d+)\)', src, flags=re.M)
        assert len(nums) > 50, f"a sorszám-olvasás elromlott ({mod})"
        dupes = sorted({n for n in nums if nums.count(n) > 1})
        assert not dupes, f"ismétlődő szabály-sorszámok ({mod}): {dupes}"


def _client_with_halftime_match():
    """Két 20 mp-es szimulált félidő 90 mp-es (üres) szünettel — a
    félidő-felismerés (detect_halftime) megtalálja a szünetet, így a
    félidő-feltételes (_fh) kulcsok is elkészülnek."""
    from handball.models.tracking import Frame, Match

    os.environ["HANDBALL_DATA_DIR"] = _tmp
    m1 = simulate_ground_truth(duration_s=20, fps=25.0, seed=1)
    m2 = simulate_ground_truth(duration_s=20, fps=25.0, seed=2)
    frames = list(m1.frames)
    t = frames[-1].t + 1
    for _ in range(int(90 * 25)):
        frames.append(Frame(t=t, players=[], ball=None))
        t += 1
    for f in m2.frames:
        f.t = t
        frames.append(f)
        t += 1
    m = Match(m1.meta, frames)
    matches_dir = Path(_tmp) / "data" / "matches"
    matches_dir.mkdir(parents=True, exist_ok=True)
    (matches_dir / f"{m.meta.match_id}.json").write_text(
        json.dumps(m.to_dict()), encoding="utf-8")
    return TestClient(create_app()), m.meta.match_id


def test_felido_kulcsok_elkeszulnek_felidos_meccsen():
    """A félidő-feltételes (_fh) kulcsok a sima füstteszten jogosan
    hiányoznak — itt egy FELISMERT félidejű szimulált meccsen
    követeljük mindet: egy elromló _fh-ág is némán tűnne el."""
    registries = _endpoint_registries()
    fh_by_path = {path: sorted(k for k in keys if k.endswith("_fh"))
                  for path, keys in registries.items()}
    fh_by_path = {p: ks for p, ks in fh_by_path.items() if ks}
    assert fh_by_path, "nincs _fh kulcs a forrásban?"
    client, mid = _client_with_halftime_match()
    problems = []
    for path, fh_keys in sorted(fh_by_path.items()):
        r = client.get(path.replace("{match_id}", mid))
        if r.status_code != 200:
            problems.append(f"{path}: HTTP {r.status_code}")
            continue
        body = r.json()
        missing = sorted(set(fh_keys) - set(body))
        if missing:
            problems.append(f"{path}: {missing}")
    assert not problems, \
        f"hiányzó félidő-kulcsok felismert félidő mellett: {problems}"


def test_minden_get_vegpont_tulel():
    """Minden GET /matches/{id}/... végpont — a paraméteres
    játékos-végpontokkal együtt — 5xx nélkül fut le egy érvényes
    szimulált meccsen. A kulcs-őrök a regisztrált rétegeket nézik;
    ez azt, hogy EGYIK végpont sem omlik össze (a 404 pl. csomag-
    letöltésnél export előtt jogos, az 500 sosem az)."""
    src = _APP_PY.read_text(encoding="utf-8")
    paths = sorted(set(re.findall(
        r'@app\.get\("(/matches/\{match_id\}[^"]*)"\)', src)))
    assert len(paths) > 30, "az útvonal-olvasás elromlott"
    client, mid = _client_with_match()
    body = client.get(f"/matches/{mid}/positions")
    tid = None
    if body.status_code == 200 and isinstance(body.json(), dict):
        for side in ("home", "away"):
            ids = list((body.json().get(side) or {}).keys())
            if ids:
                tid = ids[0]
                break
    problems = []
    for path in paths:
        url = path.replace("{match_id}", mid)
        if "{track_id}" in url or "{player_id}" in url:
            if tid is None:
                continue
            url = (url.replace("{track_id}", str(tid))
                      .replace("{player_id}", str(tid)))
        if "{" in url:
            continue  # egyéb paraméteres útvonal kimarad
        r = client.get(url)
        if r.status_code >= 500:
            problems.append(f"{path}: HTTP {r.status_code}")
    assert not problems, f"összeomló végpontok: {problems}"


# Örökölt, csak végpont-oldali kulcsok: a csomag-regisztryben más
# néven (vagy összevontan) szereplő régi rétegek. Zárt lista — új
# réteg ide NEM kerülhet: a recept szerint minden új réteg KÉT helyre
# kötendő be (/analyze válasz ÉS meccs-csomag `_layer`).
_LEGACY_RES_ONLY_KEYS = {
    "pivot", "positioning", "pressure", "timeline", "transition",
}


def test_minden_res_kulcs_a_csomagban_is():
    """A recept "KÉT helyre" lépésének őre: minden végpont-oldali
    `res["..."]` réteg-kulcsnak a meccs-csomag `_layer`
    regisztrációjában is szerepelnie kell — a félidő-feltételes
    (_fh) bontások és az örökölt kivétel-lista kivételével. A csak
    egy helyre bekötött új réteg a csomagból némán hiányozna."""
    src = _APP_PY.read_text(encoding="utf-8")
    res_keys = set(re.findall(r'res\["([a-z0-9_]+)"\]\s*=', src))
    layer_keys = set(_registered_package_layers())
    missing = sorted(
        k for k in res_keys - layer_keys
        if not k.endswith("_fh") and k not in _LEGACY_RES_ONLY_KEYS)
    assert not missing, (
        f"csak a végpontra bekötött rétegek (a csomagból hiányoznak): "
        f"{missing}")


def test_kliens_helper_nevek_egyediek():
    """Két azonos nevű Dart-helper az egész osztályban fordítási hibát
    okoz — a zárójel-egyensúly ellenőrzés ezt nem látja, a kiadási
    (Flutter build) csak ott bukik ki. Itt fogjuk meg előbb."""
    dart = (Path(__file__).resolve().parent.parent.parent
            / "client" / "lib" / "ui" / "scouting_screen.dart")
    if not dart.exists():
        pytest.skip("nincs kliens a fában")
    names = re.findall(
        r'^\s+(?:String\?|Widget|bool|int|double|List<[^>]+>\??)\s+'
        r'(_\w+)\(', dart.read_text(encoding="utf-8"), flags=re.M)
    assert len(names) > 200, "a helper-olvasás elromlott"
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert not dupes, f"duplán deklarált kliens-helperek: {dupes}"


def test_kliens_csempe_cimkek_egyediek():
    """Két azonos című csempe a felderítés-listában
    megkülönböztethetetlen a felhasználónak — a címkéknek egyedieknek
    kell lenniük (a v0.1.23 kiadásnál három ütközés is volt)."""
    dart = (Path(__file__).resolve().parent.parent.parent
            / "client" / "lib" / "ui" / "scouting_screen.dart")
    if not dart.exists():
        pytest.skip("nincs kliens a fában")
    labels = re.findall(r'\["([^"]+)", _\w+\(r\)!\]',
                        dart.read_text(encoding="utf-8"))
    assert len(labels) > 200, "a címke-olvasás elromlott"
    dupes = sorted({l for l in labels if labels.count(l) > 1})
    assert not dupes, f"ismétlődő csempe-címkék: {dupes}"


def test_claude_md_szamlalok_szinkronban():
    """A CLAUDE.md recept-számlálóinak (következő meccsterv- és
    edzés-szabály szám) egyeznie kell a kódban ténylegesen kiosztott
    legnagyobb sorszám + 1 értékkel — a számláló-elcsúszás dupla
    sorszámot vagy lyukat okozna a következő rétegnél."""
    root = Path(__file__).resolve().parent.parent
    claude_md = root.parent / "CLAUDE.md"
    if not claude_md.exists():
        pytest.skip("nincs CLAUDE.md a fában")
    nexts = [int(m) for m in re.findall(
        r"a KÖVETKEZŐ szám: (\d+)", claude_md.read_text(encoding="utf-8"))]
    assert len(nexts) == 2, "a CLAUDE.md számláló-sorai elmozdultak"
    next_matchup, next_training = nexts

    scouting = (root / "handball" / "pipeline" / "scouting.py").read_text(
        encoding="utf-8")
    training = (root / "handball" / "pipeline" / "training.py").read_text(
        encoding="utf-8")
    max_matchup = max(int(m) for m in re.findall(r"# (\d+)\)", scouting))
    max_training = max(int(m) for m in re.findall(r"# (\d+)\)", training))
    assert next_matchup == max_matchup + 1, (
        f"CLAUDE.md meccsterv-számláló {next_matchup}, de a legnagyobb "
        f"kiosztott szabályszám {max_matchup}")
    assert next_training == max_training + 1, (
        f"CLAUDE.md edzés-számláló {next_training}, de a legnagyobb "
        f"kiosztott szabályszám {max_training}")


def test_reteg_katalogus_friss():
    """A docs/RETEG_KATALOGUS.md generált fájl — ennek a tesztnek a
    dolga, hogy ne csússzon el a kódtól: minden regisztrált rétegnek
    szerepelnie kell benne, és a fejlécben lévő darabszámnak egyeznie
    kell a registry-vel. (Frissítés: python -m scripts.layer_catalog)"""
    root = Path(__file__).resolve().parent.parent
    cat = root.parent / "docs" / "RETEG_KATALOGUS.md"
    assert cat.exists(), "hiányzik a docs/RETEG_KATALOGUS.md — generáld"
    text = cat.read_text(encoding="utf-8")
    layers = _registered_package_layers()
    missing = [n for n in layers if f"`{n}`" not in text]
    assert not missing, f"a katalógusból hiányzó rétegek: {missing}"
    m = re.search(r"Összesen \*\*(\d+) réteg\*\*", text)
    assert m, "a katalógus fejléce elmozdult"
    assert int(m.group(1)) == len(layers), (
        f"a katalógus {m.group(1)} réteget mond, a registry "
        f"{len(layers)}-t — futtasd: python -m scripts.layer_catalog")


def test_kliens_csempe_helperek_leteznek():
    """Minden csempe-sorban hivatkozott Dart-helper legyen deklarálva
    is — a hiányzó helper csak a Flutter-buildnél bukna ki (mint a
    v0.1.23-as kiadásnál a névütközés), itt fogjuk meg előbb."""
    dart = (Path(__file__).resolve().parent.parent.parent
            / "client" / "lib" / "ui" / "scouting_screen.dart")
    if not dart.exists():
        pytest.skip("nincs kliens a fában")
    src = dart.read_text(encoding="utf-8")
    declared = set(re.findall(
        r'^\s+(?:String\?|Widget|bool|int|double|List<[^>]+>\??)\s+'
        r'(_\w+)\(', src, flags=re.M))
    used = set(re.findall(r'\[\"[^\"]+\", (_\w+)\(r\)!\]', src))
    assert len(used) > 200, "a csempe-olvasás elromlott"
    missing = sorted(used - declared)
    assert not missing, f"csempéből hivatkozott, de hiányzó helperek: {missing}"


def test_projekt_szamok_frissek():
    """A docs/SZAMOK.md generált tény-lap — a pályázati és bemutató
    anyagok ide hivatkoznak, ezért nem avulhat el észrevétlenül.
    (Frissítés: python -m scripts.project_facts)"""
    import subprocess
    root = Path(__file__).resolve().parent.parent
    facts = root.parent / "docs" / "SZAMOK.md"
    assert facts.exists(), "hiányzik a docs/SZAMOK.md — generáld"
    res = subprocess.run(
        [sys.executable, "-m", "scripts.project_facts", "--check"],
        cwd=root, capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, (
        "elavult tény-lap — futtasd: python -m scripts.project_facts\n"
        + res.stderr)


def test_palyazati_szamok_egyeznek_a_teny_lappal():
    """A pályázati/bemutató anyagokba ÍRT számok egyezzenek a tény-lappal.

    Az EIC-anyagok (executive summary, Part B, pitch deck, felkészülési
    terv) szöveg közben is megnevezik a réteg- és teszt-számot. Ezek
    csendben elavulnának minden réteg-commit után — az értékelő pedig
    ellenőrzi őket. Ez az őr összeveti a szöveges említéseket a
    generált `docs/SZAMOK.md`-vel.
    """
    import re
    root = Path(__file__).resolve().parent.parent.parent
    facts = (root / "docs" / "SZAMOK.md").read_text(encoding="utf-8")

    def _fact(label: str) -> int:
        m = re.search(rf"\| {label} [^|]*\| \*\*(\d+)\*\*", facts)
        assert m, f"nincs '{label}' sor a tény-lapon"
        return int(m.group(1))

    layers = _fact("Elemző réteg")
    tests = _fact("Automata teszt")

    # "300 elemző réteg" / "300 analysis layers" / "1226 automata
    # teszt" / "1,226 automated tests" — a vessző csak tagolás.
    pat = re.compile(
        r"([\d][\d,]*)\s+(elemző réteg|analysis layers|"
        r"automata teszt|automated tests)")
    checked = 0
    for doc in sorted((root / "docs").glob("*.md")):
        if doc.name in ("SZAMOK.md", "RETEG_KATALOGUS.md"):
            continue  # ezek generáltak
        for m in pat.finditer(doc.read_text(encoding="utf-8")):
            value = int(m.group(1).replace(",", ""))
            want = layers if "réteg" in m.group(2) or "layers" in m.group(2) \
                else tests
            assert value == want, (
                f"{doc.name}: '{m.group(0)}' — a tény-lap szerint "
                f"{want}. Frissítsd a dokumentumot "
                "(python -m scripts.project_facts adja a mérvadó számot).")
            checked += 1
    assert checked >= 4, f"csak {checked} említést találtam — romlott a minta"
