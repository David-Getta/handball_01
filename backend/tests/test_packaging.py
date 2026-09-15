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
