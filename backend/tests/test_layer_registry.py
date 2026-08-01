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
