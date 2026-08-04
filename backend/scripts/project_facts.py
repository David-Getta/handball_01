"""Projekt-tények generálása — a kódbázisból számolt, hivatkozható számok.

A pályázati és bemutató anyagok ("N elemző réteg", "M automata teszt")
állításai csak akkor érnek valamit, ha ellenőrizhető forrásra
mutatnak. Ez a script a repóból számolja ki a számokat, és a
docs/SZAMOK.md tény-lapba írja — a doksik oda hivatkoznak, a
teszt-csomag őre (test_layer_registry) pedig frissen tartja.

Minden szám STATIKUSAN, futtatás nélkül számolható (a teszt-darabszám
a `def test_` függvények száma, ami a pytest collect-tel egyezik).

Használat:
    cd backend && python -m scripts.project_facts          # kiírja
    cd backend && python -m scripts.project_facts --check   # összeveti
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_ROOT = _BACKEND.parent
_APP = _BACKEND / "handball" / "api" / "app.py"
_PIPELINE = _BACKEND / "handball" / "pipeline"
_TESTS = _BACKEND / "tests"
_SCOUTING = _PIPELINE / "scouting.py"
_TRAINING = _PIPELINE / "training.py"
_DART = _ROOT / "client" / "lib" / "ui" / "scouting_screen.dart"
_OUT = _ROOT / "docs" / "SZAMOK.md"


def collect_facts() -> dict:
    """A hivatkozható projekt-számok egy szótárban."""
    app_src = _APP.read_text(encoding="utf-8")
    layers = set(re.findall(r'_layer\(\s*"([a-z0-9_]+)"', app_src))

    tests = 0
    for f in sorted(_TESTS.glob("test_*.py")):
        tests += len(re.findall(r"^def test_\w+",
                                f.read_text(encoding="utf-8"), flags=re.M))

    def _max_rule(path: Path) -> int:
        nums = re.findall(r"# (\d+)\)", path.read_text(encoding="utf-8"))
        return max((int(n) for n in nums), default=0)

    tiles = 0
    if _DART.exists():
        tiles = len(re.findall(r'\["[^"]+", _\w+\(r\)!\]',
                               _DART.read_text(encoding="utf-8")))

    return {
        "layers": len(layers),
        "tests": tests,
        "matchup_rules": _max_rule(_SCOUTING),
        "training_rules": _max_rule(_TRAINING),
        "tiles": tiles,
        "modules": len(list(_PIPELINE.glob("*.py"))),
    }


def build_facts_md() -> str:
    f = collect_facts()
    return f"""# Projekt-számok (generált tény-lap)

*Generált fájl — ne kézzel szerkeszd. Frissítés:*
`cd backend && python -m scripts.project_facts`

Ezek a számok a kódbázisból, statikusan számoltak — a pályázati és
bemutató anyagok ide hivatkoznak, hogy az állításaik ellenőrizhetők
legyenek. A teszt-csomag őre nem engedi elavulni.

| Mérték | Érték | Miből számolva |
|---|---:|---|
| Elemző réteg (meccs-csomag) | **{f['layers']}** | `_layer("...")` regisztrációk az `api/app.py`-ban |
| Automata teszt | **{f['tests']}** | `def test_*` függvények a `backend/tests/`-ben |
| Meccsterv-szabály | **{f['matchup_rules']}** | a legnagyobb sorszámozott szabály a `pipeline/scouting.py`-ban |
| Edzés-szabály | **{f['training_rules']}** | a legnagyobb sorszámozott szabály a `pipeline/training.py`-ban |
| Kliens-csempe (felderítés) | **{f['tiles']}** | csempe-sorok a `client/lib/ui/scouting_screen.dart`-ban |
| Pipeline-modul | **{f['modules']}** | `.py` fájlok a `backend/handball/pipeline/`-ban |

A rétegek tételes listája (mit mér melyik):
[`docs/RETEG_KATALOGUS.md`](RETEG_KATALOGUS.md).
"""


# A szövegbe ÍRT számok mintája a doksikban ("300 elemző réteg",
# "1,227 automated tests"). A vessző csak ezres tagolás.
_DOC_NUM = re.compile(
    r"([\d][\d,]*)(\s+)(elemző réteg|analysis layers|"
    r"automata teszt|automated tests)")

# Ezek generált fájlok — nem bennük tartjuk a szöveges említéseket.
_GENERATED_DOCS = ("SZAMOK.md", "RETEG_KATALOGUS.md", "SORREND_FUGGES.md")


def _grouped(value: int, sample: str) -> str:
    """A szám a helyi tagolással: ha a doksiban vesszős volt, az marad."""
    return f"{value:,}" if "," in sample else str(value)


def sync_docs(facts: dict, write: bool = True) -> list[str]:
    """A doksikba írt réteg-/teszt-számok igazítása a tény-laphoz.

    A pályázati anyagok szöveg közben is megnevezik ezeket a számokat;
    minden réteg-commit után elavulnának. Visszatérés: az ELTÉRŐ
    (write=True esetén: a frissített) fájlok neve.
    """
    changed: list[str] = []
    targets = sorted((_ROOT / "docs").glob("*.md"))
    readme = _ROOT / "README.md"
    if readme.exists():
        targets.append(readme)  # a nyitólap száma is elavulna
    for doc in targets:
        if doc.name in _GENERATED_DOCS:
            continue
        src = doc.read_text(encoding="utf-8")

        def _fix(m):
            want = (facts["layers"] if "réteg" in m.group(3)
                    or "layers" in m.group(3) else facts["tests"])
            return _grouped(want, m.group(1)) + m.group(2) + m.group(3)

        out = _DOC_NUM.sub(_fix, src)
        if out != src:
            changed.append(doc.name)
            if write:
                doc.write_text(out, encoding="utf-8")
    return changed


def main(argv=None) -> int:
    check = "--check" in (argv or sys.argv[1:])
    text = build_facts_md()
    facts = collect_facts()
    if check:
        current = _OUT.read_text(encoding="utf-8") if _OUT.exists() else ""
        if current != text:
            print("ELTÉRÉS: a tény-lap elavult — futtasd: "
                  "python -m scripts.project_facts", file=sys.stderr)
            return 1
        stale = sync_docs(facts, write=False)
        if stale:
            print("ELTÉRÉS: elavult számok a doksikban ("
                  + ", ".join(stale)
                  + ") — futtasd: python -m scripts.project_facts",
                  file=sys.stderr)
            return 1
        print("A tény-lap friss.")
        return 0
    _OUT.write_text(text, encoding="utf-8")
    print(f"Tény-lap kiírva: {_OUT}")
    for k, v in facts.items():
        print(f"  {k}: {v}")
    synced = sync_docs(facts)
    if synced:
        print("  frissített doksik: " + ", ".join(synced))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
