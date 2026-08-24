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

A KLIENS-őrzések (elgépelt kulcs, néma pörgettyű, nyers kivétel a
képernyőn, célt nem találó ugró-gomb) külön fájlban élnek:
tests/test_client_ui.py. Azok a Dart forrásból olvasnak, nem kell
hozzájuk se FastAPI, se szimulált meccs — ezért ott másodpercek alatt
lefutnak, itt pedig percekig tartanának.

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
    # LÖVÉSEKKEL: a szimuláció alapból csak mozgást modellez, és
    # lövések nélkül a több mint száz lövés-alapú réteg üres bemeneten
    # fut — az "egyetlen réteg sem bukhat el némán" őrzés épp rájuk nem
    # érne semmit. 40 mp / 12 lövés-perc = 8 lövés, azonosított lövővel.
    m = simulate_ground_truth(duration_s=40, fps=25.0, seed=1,
                              shots_per_min=12.0)
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


# A drága lépések (csomag-export, végpont-söprés) MODUL-hatókörű
# fixtúrákban futnak: a füstteszt több őre ugyanazt a mintameccset
# nézi más szemszögből, és a kimenet előállítása másodpercekbe kerül.
# Egyszer állítjuk elő, aztán mindegyik őr a saját állítását teszi rá.
@pytest.fixture(scope="module")
def sample_match():
    """A lövéses mintameccs és a rá nyitott kliens — egyszer épül."""
    return _client_with_match()


@pytest.fixture(scope="module")
def package_analyses(sample_match):
    """A meccs-csomag elemzés-JSON-ja — egyszer exportálva."""
    client, mid = sample_match
    r = client.post(f"/matches/{mid}/package/export",
                    json={"clip_types": []})
    job = _wait_job(client, r.json()["job_id"])
    assert job["status"] == "done", job
    pkg = client.get(f"/matches/{mid}/package/download")
    assert pkg.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(pkg.content))
    return json.loads(z.read("elemzesek.json").decode("utf-8"))


@pytest.fixture(scope="module")
def get_answers(sample_match):
    """Minden GET /matches/{id}/... végpont válasza — egyszer lekérve.

    {útvonal-sablon: (HTTP-kód, törzs)}. A paraméteres játékos-
    végpontok az első valódi track_id-vel hívódnak; ha nincs ilyen,
    kimaradnak.
    """
    client, mid = sample_match
    src = _APP_PY.read_text(encoding="utf-8")
    paths = sorted(set(re.findall(
        r'@app\.get\("(/matches/\{match_id\}[^"]*)"\)', src)))
    body = client.get(f"/matches/{mid}/positions")
    tid = None
    if body.status_code == 200 and isinstance(body.json(), dict):
        for side in ("home", "away"):
            ids = list((body.json().get(side) or {}).keys())
            if ids:
                tid = ids[0]
                break
    out: dict[str, tuple[int, object]] = {}
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
        try:
            payload = r.json()
        except ValueError:
            payload = None
        out[path] = (r.status_code, payload)
    return out


def _registered_package_layers() -> list[str]:
    src = _APP_PY.read_text(encoding="utf-8")
    return re.findall(r'_layer\(\s*"([a-z0-9_]+)"', src)


def test_package_minden_regisztralt_reteg_elkeszul(package_analyses):
    """A csomag elemzés-JSON-jában MINDEN `_layer(...)`-rel regisztrált
    réteg ott van — egy kivétellel elhasaló motor itt bukna ki, mert a
    `_layer` a hibát lenyeli, a kulcs pedig hiányozna."""
    names = _registered_package_layers()
    assert len(names) > 200, "a regisztry-olvasás elromlott"
    missing = sorted(set(names) - set(package_analyses))
    assert not missing, f"némán elbukott rétegek a csomagban: {missing}"


def test_loves_retegek_valodi_adatot_kapnak(package_analyses):
    """A lövés-alapú rétegek NEM üresen jönnek vissza.

    A "kulcs ott van" őrzés önmagában gyenge: egy lövés nélküli
    meccsen minden lövés-réteg üres szerkezetet ad, és a teszt zölden
    átmegy anélkül, hogy a réteg érdemi ága lefutott volna. A
    mintameccs ezért LŐ is — itt pedig megköveteljük, hogy a
    lövés-rétegek lássák is a lövéseket.
    """
    empty = []
    for name in ("role_shot_distance", "role_shot_timing",
                 "role_shot_power", "shot_speeds", "xg"):
        rec = package_analyses.get(name)
        if rec is None:
            empty.append(f"{name}: hiányzik")
            continue
        blob = json.dumps(rec, ensure_ascii=False)
        # A hazai csapat lő a mintameccsen: valamelyik számnak nullánál
        # nagyobbnak kell lennie.
        if not any(ch.isdigit() and ch != "0" for ch in blob):
            empty.append(f"{name}: üres")
    assert not empty, (
        "a lövés-rétegek nem kaptak valódi bemenetet — a mintameccs "
        f"lövései nem érnek el hozzájuk: {empty}")


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


def test_vegpontok_minden_regisztralt_kulcs_elkeszul(get_answers):
    """Minden elemzés-végpont válaszában ott van minden
    `res["..."]`-ként bekötött kulcs — a félidő-feltételes (_fh és
    first_half_close) kulcsok kivételével, amelyek a rövid szimulált
    meccsen jogosan hiányoznak."""
    registries = _endpoint_registries()
    assert len(registries) >= 4, "a végpont-olvasás elromlott"
    assert sum(len(k) for k in registries.values()) > 200, \
        "a kulcs-olvasás elromlott"
    problems = []
    for path, registered in sorted(registries.items()):
        status, body = get_answers[path]
        if status != 200:
            problems.append(f"{path}: HTTP {status}")
            continue
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


def test_minden_get_vegpont_tulel(get_answers):
    """Minden GET /matches/{id}/... végpont — a paraméteres
    játékos-végpontokkal együtt — 5xx nélkül fut le egy érvényes
    szimulált meccsen. A kulcs-őrök a regisztrált rétegeket nézik;
    ez azt, hogy EGYIK végpont sem omlik össze (a 404 pl. csomag-
    letöltésnél export előtt jogos, az 500 sosem az)."""
    assert len(get_answers) > 30, "az útvonal-olvasás elromlott"
    problems = [f"{path}: HTTP {status}"
                for path, (status, _) in sorted(get_answers.items())
                if status >= 500]
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
    targets = sorted((root / "docs").glob("*.md")) + [root / "README.md"]
    for doc in targets:
        if doc.name in ("SZAMOK.md", "RETEG_KATALOGUS.md",
                        "SORREND_FUGGES.md"):
            continue  # ezek generáltak
        if not doc.exists():
            continue
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


def test_szam_szinkron_javitja_az_elavult_doksit():
    """A tény-lap generálása a doksikba írt számokat is igazítja.

    Enélkül minden réteg-commit után kézzel kellene öt pályázati
    dokumentumot átírni — és pont az maradna el, amit az értékelő néz.
    """
    from scripts.project_facts import collect_facts, sync_docs

    root = Path(__file__).resolve().parent.parent.parent
    doc = root / "docs" / "PITCH_DECK_VAZLAT.md"
    original = doc.read_text(encoding="utf-8")
    # A VALÓS számokkal szinkronizálunk: így csak a szándékosan
    # elrontott réteg-szám javul, a többi doksi nem mozdul.
    facts = collect_facts()
    good = f"{facts['layers']} elemző réteg"
    assert good in original, good
    try:
        doc.write_text(original.replace(good, "42 elemző réteg"),
                       encoding="utf-8")
        stale = sync_docs(facts, write=False)
        assert "PITCH_DECK_VAZLAT.md" in stale, stale
        sync_docs(facts)
        assert good in doc.read_text(encoding="utf-8")
    finally:
        doc.write_text(original, encoding="utf-8")


def test_nincs_ketszer_definialt_modul_konstans():
    """ŐR: egy pipeline-modulban ne legyen KÉTSZER definiált
    NAGYBETŰS modul-konstans.

    A réteg-recept minden új réteghez küszöb-konstansokat kér a modul
    tetejére. Ha egy új réteg elveszi egy meglévő konstans nevét
    (pl. PPP_WINDOW_S), a Python csendben FELÜLÍRJA a régit — a régi
    réteg küszöbe megváltozik, és a hiba csak egy távoli teszten
    bukik ki. Ez a teszt a modul-szintű értékadásokat számolja meg.
    """
    import pathlib
    import re
    from collections import Counter

    pipeline_dir = pathlib.Path("handball/pipeline")
    hibak = []
    for mod in sorted(pipeline_dir.glob("*.py")):
        src = mod.read_text(encoding="utf-8")
        # Csak a modul legfelső szintje (nincs behúzás), NAGYBETŰS név.
        nevek = re.findall(r"^([A-Z][A-Z0-9_]{2,})\s*(?::[^=\n]+)?=",
                           src, flags=re.M)
        dupla = [n for n, c in Counter(nevek).items() if c > 1]
        if dupla:
            hibak.append(f"{mod.name}: {sorted(dupla)}")
    assert not hibak, ("kétszer definiált modul-konstansok: "
                       + "; ".join(hibak))


def test_nincs_ketszer_definialt_fuggveny():
    """ŐR: egy modulban ne legyen KÉTSZER definiált modul-szintű
    függvény.

    Ugyanaz a csendes felülírás, mint a konstansoknál: ha egy új
    réteg motorja elveszi egy meglévő függvény nevét, a Python az
    utolsót tartja meg — a régi réteg minden felülete észrevétlenül
    az ÚJ motort hívja. A tesztfájlokra is áll: a pytest ott is csak
    az utolsó azonos nevű tesztet futtatja, a korábbi némán eltűnik.
    """
    import pathlib
    import re
    from collections import Counter

    hibak = []
    for d, minta in ((pathlib.Path("handball/pipeline"), "*.py"),
                     (pathlib.Path("handball/api"), "*.py"),
                     (pathlib.Path("tests"), "test_*.py")):
        for mod in sorted(d.glob(minta)):
            src = mod.read_text(encoding="utf-8")
            nevek = re.findall(r"^def (\w+)\(", src, flags=re.M)
            dupla = [n for n, c in Counter(nevek).items() if c > 1]
            if dupla:
                hibak.append(f"{mod.name}: {sorted(dupla)}")
    assert not hibak, ("kétszer definiált függvények: "
                       + "; ".join(hibak))


# Idő-küszöbök, amiket MÁSODPERCBEN tartunk (a kocka-alakjuk már csak
# visszafelé kompatibilis alapérték a képrátát nem ismerő hívóknak).
# A pár: (kocka-konstans, a másodperces párja).
_IDO_KUSZOB_PAROK = (
    ("CONFIDENCE_HALFLIFE_FRAMES", "CONFIDENCE_HALFLIFE_S"),
    ("VELOCITY_FADE_FRAMES", "VELOCITY_FADE_S"),
    ("DEFAULT_MAX_GAP_FRAMES", "MAX_GAP_S"),
    ("BSR_LOOKBACK_FRAMES", "BSR_LOOKBACK_S"),
    ("MARK_MIN_FRAMES", "MARK_MIN_S"),
    ("HOLD_MIN_FRAMES", "HOLD_MIN_S"),
    ("PIVOT_TOUCH_MIN_FRAMES", "PIVOT_TOUCH_MIN_S"),
)


def test_az_ido_kuszobok_nem_esnek_vissza_kockara():
    """Az IDŐTARTAM-jelentésű küszöböket másodpercben kell tartani.

    A feldolgozás ritkít (a termék alapja minden 3. kocka), tehát egy
    kockában rögzített időtartam a minőségi profiltól függően
    háromszoros valós időt jelent. Ebből a hibafajtából egy nap alatt
    HÉT darabot találtunk (hossz-korlát, labda-hézagpótlás, becslés
    sebesség-elhalása és felezési ideje, őrzési párok, blokkolt-poszt
    visszanézés, labdatartás, beálló-villanás) — a visszaesés reális.

    A kocka-alak megmarad visszafelé kompatibilis alapértéknek, de a
    MOTORNAK a másodperces párt kell használnia: ha egy kocha-konstans
    újra megjelenik futó kódban (nem a saját definíciójában és nem
    kommentben), az regresszió.

    Fontos, ami NEM tartozik ide: a MINTASZÁM-küszöbök (pl. a
    "legalább 100 mért kocka kell az átlaghoz") jogosan kockában
    vannak — ott 100 minta tényleg 100 minta.
    """
    import re

    pipeline = Path(__file__).resolve().parent.parent / "handball" / "pipeline"
    forrasok = {py.name: py.read_text(encoding="utf-8")
                for py in sorted(pipeline.glob("*.py"))}

    hianyzo_par: list = []
    visszaeses: list = []
    for kocka, masodperc in _IDO_KUSZOB_PAROK:
        hol = [n for n, t in forrasok.items()
               if re.search(rf"^{kocka} = ", t, re.M)]
        assert hol, f"eltűnt a kocka-konstans: {kocka}"
        for modul in hol:
            szoveg = forrasok[modul]
            if not re.search(rf"^{masodperc} = ", szoveg, re.M):
                hianyzo_par.append(f"{modul}: {kocka} → nincs {masodperc}")
                continue
            for i, sor in enumerate(szoveg.split("\n"), 1):
                csupasz = sor.split("#", 1)[0]
                if kocka not in csupasz:
                    continue
                if re.match(rf"\s*{kocka} = ", csupasz):
                    continue          # a saját definíciója
                visszaeses.append(f"{modul}:{i}: {kocka} ({sor.strip()})")

    assert not hianyzo_par, (
        "idő-küszöb másodperces párja nélkül: " + "; ".join(hianyzo_par))
    assert not visszaeses, (
        "IDŐTARTAM-küszöb kocka-alakja futó kódban — a ritkítás miatt ez "
        "profilonként mást jelent; a másodperces párt kell használni: "
        + "; ".join(visszaeses))


def _client_with_sovany_match():
    """Kliens egy SZÁNDÉKOSAN sovány meccsel: mozgás van, labda nincs.

    Ez nem elméleti eset: pont ez történik, ha a labda-észlelés nem
    működik (távoli, széles felvétel, rossz megvilágítás). A
    felhasználó ilyenkor is megnyitja a jelentést — és ha egy réteg
    ezen elhasal, a `_layer` lenyeli a hibát, a szakasz pedig NYOM
    NÉLKÜL eltűnik. Épp akkor, amikor a legnagyobb szükség lenne rá,
    hogy a jelentés elmondja, mi történt.
    """
    os.environ["HANDBALL_DATA_DIR"] = _tmp
    m = simulate_ground_truth(duration_s=40, fps=25.0, seed=5,
                              shots_per_min=12.0)
    m.meta.match_id = f"{m.meta.match_id}-sovany"
    for fr in m.frames:
        fr.ball = None                       # a labda sehol nem látszik
    matches_dir = Path(_tmp) / "data" / "matches"
    matches_dir.mkdir(parents=True, exist_ok=True)
    (matches_dir / f"{m.meta.match_id}.json").write_text(
        json.dumps(m.to_dict()), encoding="utf-8")
    return TestClient(create_app()), m.meta.match_id


@pytest.fixture(scope="module")
def sovany_package_analyses():
    """A sovány meccs elemzés-JSON-ja — egyszer exportálva."""
    client, mid = _client_with_sovany_match()
    r = client.post(f"/matches/{mid}/package/export", json={"clip_types": []})
    job = _wait_job(client, r.json()["job_id"])
    assert job["status"] == "done", job
    pkg = client.get(f"/matches/{mid}/package/download")
    assert pkg.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(pkg.content))
    return json.loads(z.read("elemzesek.json").decode("utf-8"))


def _client_with_egycsapatos_match():
    """Kliens egy meccsel, ahol MINDENKI ugyanabba a csapatba került.

    Valós hibamód: ha a mezszín-klaszterezés összeomlik (azonos színű
    mezek, rossz megvilágítás), minden játékos egy oldalra kerül. A
    minőség-jelentés ezt ki is mondja ("a csapat-besorolás egyoldalú"),
    de a rétegeknek addig sem szabad NÉMÁN elhasalniuk — a felhasználó
    különben azt hiszi, azok az elemzések nem is léteznek.
    """
    os.environ["HANDBALL_DATA_DIR"] = _tmp
    from handball.models.tracking import Team
    m = simulate_ground_truth(duration_s=40, fps=25.0, seed=11,
                              shots_per_min=12.0)
    m.meta.match_id = f"{m.meta.match_id}-egycsapat"
    for fr in m.frames:
        for pl in fr.players:
            pl.team = Team.HOME
    matches_dir = Path(_tmp) / "data" / "matches"
    matches_dir.mkdir(parents=True, exist_ok=True)
    (matches_dir / f"{m.meta.match_id}.json").write_text(
        json.dumps(m.to_dict()), encoding="utf-8")
    return TestClient(create_app()), m.meta.match_id


@pytest.fixture(scope="module")
def egycsapatos_package_analyses():
    """Az egycsapatos meccs elemzés-JSON-ja — egyszer exportálva."""
    client, mid = _client_with_egycsapatos_match()
    r = client.post(f"/matches/{mid}/package/export", json={"clip_types": []})
    job = _wait_job(client, r.json()["job_id"])
    assert job["status"] == "done", job
    pkg = client.get(f"/matches/{mid}/package/download")
    assert pkg.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(pkg.content))
    return json.loads(z.read("elemzesek.json").decode("utf-8"))


def test_egy_reteg_sem_hasal_el_az_egycsapatos_meccsen(
        egycsapatos_package_analyses):
    """Összeomlott csapat-besorolásnál SEM tűnhet el réteg nyom nélkül.

    Ilyenkor a legtöbb réteg jogosan hallgat (nincs kivel szembeállítani
    a csapatot), de a kulcsnak ott kell lennie — a jelentés nem lehet
    NÉMÁN hiányos épp azon a futáson, ahol magyarázatra volna szükség.
    """
    names = _registered_package_layers()
    missing = sorted(set(names) - set(egycsapatos_package_analyses))
    assert not missing, (
        "egycsapatos meccsen NÉMÁN elbukó rétegek: " + ", ".join(missing))


def _client_with_toredek_match():
    """Kliens egy TÖREDÉK meccsel: két másodpercnyi felvétel.

    Ez a "a feldolgozás pár másodperc után megszakadt" eset — a
    részleges mentés a könyvtárba kerül, és a felhasználó megnyitja.
    Egy nullával osztó vagy üres listát indexelő réteg itt bukna el.
    """
    os.environ["HANDBALL_DATA_DIR"] = _tmp
    m = simulate_ground_truth(duration_s=2, fps=25.0, seed=7)
    m.meta.match_id = f"{m.meta.match_id}-toredek"
    matches_dir = Path(_tmp) / "data" / "matches"
    matches_dir.mkdir(parents=True, exist_ok=True)
    (matches_dir / f"{m.meta.match_id}.json").write_text(
        json.dumps(m.to_dict()), encoding="utf-8")
    return TestClient(create_app()), m.meta.match_id


@pytest.fixture(scope="module")
def toredek_package_analyses():
    """A töredék meccs elemzés-JSON-ja — egyszer exportálva."""
    client, mid = _client_with_toredek_match()
    r = client.post(f"/matches/{mid}/package/export", json={"clip_types": []})
    job = _wait_job(client, r.json()["job_id"])
    assert job["status"] == "done", job
    pkg = client.get(f"/matches/{mid}/package/download")
    assert pkg.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(pkg.content))
    return json.loads(z.read("elemzesek.json").decode("utf-8"))


def test_egy_reteg_sem_hasal_el_a_toredek_meccsen(toredek_package_analyses):
    """Két másodpercnyi felvételen SEM tűnhet el réteg nyom nélkül.

    A megszakadt feldolgozás részleges mentése a könyvtárba kerül, és
    a felhasználó megnyitja. A rétegnek itt sincs mit mondania — de a
    kulcsnak ott kell lennie, hogy a jelentés ne legyen NÉMÁN hiányos.
    """
    names = _registered_package_layers()
    missing = sorted(set(names) - set(toredek_package_analyses))
    assert not missing, (
        "két másodperces meccsen NÉMÁN elbukó rétegek: "
        + ", ".join(missing))


def test_egy_reteg_sem_hasal_el_a_labda_nelkuli_meccsen(
        sovany_package_analyses):
    """Labda nélküli feldolgozáson SEM tűnhet el réteg nyom nélkül.

    A meglévő őr a jó mintameccsre néz; ez a rossz eset párja. A
    rétegnek nem kell mondania semmit (üres/None ítélet a helyes
    válasz kevés mintára), de a KULCSNAK ott kell lennie — különben a
    jelentés némán hiányos, és a felhasználó azt hiszi, az adott
    elemzés nem is létezik.
    """
    names = _registered_package_layers()
    assert len(names) > 200, "a regisztry-olvasás elromlott"
    missing = sorted(set(names) - set(sovany_package_analyses))
    assert not missing, (
        "labda nélküli meccsen NÉMÁN elbukó rétegek: " + ", ".join(missing))
