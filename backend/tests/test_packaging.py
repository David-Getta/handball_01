"""
Csomagolás-őrzések: amit a TELEPÍTHETŐ kiadásról fordító nélkül is meg
lehet — és meg KELL — követelni.

A becsomagolt motor (PyInstaller) hibái némák: egy kimaradt modul nem a
buildnél jelentkezik, hanem a felhasználó gépén, futás közben — a rétegek
try/except-je elnyeli, a fiók-végpont pedig hibát ad. Ezek a tesztek a
spec-fájlt és a kiadás-workflow-t OLVASSÁK, és a két legfontosabb
biztosítékot rögzítik:

1. a saját csomagok MINDEN almodulja bekerül a bundle-be (a projekt sok
   modult futásidőben, függvényen belül importál),
2. a füstteszt nem áll meg a /health-nél, hanem végigjátssza a
   FIÓK-folyamatot is (ez a felhasználó első képernyője).

Futtatás:
    python -m pytest tests/test_packaging.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

_ROOT = Path(__file__).resolve().parents[2]
_SPEC = _ROOT / "packaging" / "backend.spec"
_WORKFLOW = _ROOT / ".github" / "workflows" / "release.yml"


def _spec() -> str:
    if not _SPEC.exists():
        pytest.skip("nincs csomagoló-spec a fában")
    return _SPEC.read_text(encoding="utf-8")


def _workflow() -> str:
    if not _WORKFLOW.exists():
        pytest.skip("nincs kiadás-workflow a fában")
    return _WORKFLOW.read_text(encoding="utf-8")


def test_a_sajat_csomagok_minden_almodulja_bekerul():
    """ŐR: a spec a `handball` és a `scripts` MINDEN almodulját
    begyűjti. A projekt szándékosan sok modult importál futásidőben, a
    függvény testéből (`from .xg import ...`) — a PyInstaller statikus
    elemzése ezekre nem mindig fut rá."""
    src = _spec()
    for pkg in ("handball", "scripts"):
        assert f'"{pkg}"' in src, f"{pkg} nincs a hiddenimports-ban"
    assert "collect_submodules(own)" in src or (
        'collect_submodules("handball")' in src), (
        "a saját csomagok almoduljait nem gyűjti be a spec")


def test_minden_handball_modul_importalhato():
    """ŐR: a `handball` csomag minden almodulja IMPORTÁLHATÓ.

    Ha egy modul csak lusta importon keresztül él, egy elgépelt vagy
    körkörös import a fejlesztői futásban is elrejtőzhet (a hívó
    try/except-je elnyeli), a becsomagolt kiadásban pedig végképp. Ez a
    teszt mindet behúzza egyszer."""
    import importlib
    import pkgutil

    import handball

    hibas = []
    for m in pkgutil.walk_packages(handball.__path__, "handball."):
        try:
            importlib.import_module(m.name)
        except Exception as e:  # noqa: BLE001
            hibas.append(f"{m.name}: {e}")
    assert not hibas, f"nem importálható modulok: {hibas}"


def test_a_fiok_folyamat_is_fustteszt_alatt_van():
    """ŐR: a kiadás-workflow füsttesztje nem áll meg a /health-nél — a
    becsomagolt motoron a fiók-folyamatot is végigjátssza (feltételek,
    állapot, fiók-létrehozás, elfogadás nélküli elutasítás, belépés).
    Ez a felhasználó ELSŐ képernyője: ha ez nem megy, az app használhatatlan."""
    src = _workflow()
    for kell in ("/legal/terms", "/accounts/status",
                 "/accounts/register", "/accounts/login"):
        assert src.count(kell) >= 2, (
            f"a füstteszt nem hívja mindkét platformon: {kell}")
    # Az elfogadás nélküli regisztrációnak el KELL bukni (400) — ez a
    # jogi kapu, nem apróság.
    assert src.count('"accept_terms":false') >= 2, (
        "a füstteszt nem ellenőrzi, hogy elfogadás nélkül nincs fiók")


def test_a_fustteszt_izolalt_adatmappaban_dolgozik():
    """ŐR: a füstteszt saját HANDBALL_DATA_DIR-be ír — a próba-fiók nem
    szivárog bele a csomagba vagy a futtató gép állapotába."""
    src = _workflow()
    assert src.count("HANDBALL_DATA_DIR") >= 2, (
        "a füstteszt nem izolált adatmappában dolgozik")


def test_a_becsomagolt_motor_valodi_feldolgozast_is_futtat():
    """ŐR: a kiadás-build mindkét platformon VALÓDI feldolgozást is
    lefuttat a becsomagolt motorral (packaging/smoke_process.py) — a régi
    füstteszt csak az indulást és a fiók-utat nézte, így a csomagban a
    detektálásnál összeomló motor ("a motor újraindult", 2%-nál) csak a
    felhasználónál derült ki. A füstteszt a kliens kérésével dolgozik:
    yolov8n, két térfél-kalibráció, kezdőkocka, mezszám-felismerés."""
    src = _workflow()
    assert src.count("python packaging/smoke_process.py") >= 2, (
        "a feldolgozási füstteszt nem fut mindkét platformon")
    smoke = (_ROOT / "packaging" / "smoke_process.py").read_text(
        encoding="utf-8")
    for kell in ('"weights": "yolov8n.pt"', '"jersey_ocr": True',
                 '"calibs"', '"start": 30', "/matches/process",
                 "engine-crash.log"):
        assert kell in smoke, f"a füstteszt nem a kliens kérésével fut: {kell}"


def test_a_kiadas_tesztlepese_parhuzamosan_fut():
    """ŐR: a kiadás-build tesztlépése pytest-xdisttel, 4 munkással fut —
    sorban ~20 perc volt, és a csomagoló jobok csak utána indulnak."""
    src = _workflow()
    assert "pip install pytest pytest-xdist" in src
    assert "run: python -m pytest -q -n 4" in src


def test_a_kiadas_fuggosegei_rogzitve_vannak():
    """ŐR: a kiadás-build a packaging/constraints-release.txt-vel telepít —
    a backend[ml] csak alsó korlátot ad, így a build eddig mindig a
    legfrissebb torch / ultralytics / OpenCV verziót húzta be, és egy új
    upstream kiadás bármikor eltörhette a becsomagolt motort. A rögzített
    készlet az, amelyen a feldolgozási füstteszt mindkét platformon
    végigfutott; frissíteni próba-builddel lehet."""
    src = _workflow()
    assert src.count("-c packaging/constraints-release.txt") >= 2, (
        "a kiadás-build nem a rögzített függőségekkel telepít")
    sorok = (_ROOT / "packaging" / "constraints-release.txt").read_text(
        encoding="utf-8").splitlines()
    rogzitett = {s.split("==")[0] for s in sorok if "==" in s}
    for kell in ("torch", "torchvision", "ultralytics", "opencv-python",
                 "numpy", "pyinstaller"):
        assert kell in rogzitett, f"nincs rögzítve: {kell}"
