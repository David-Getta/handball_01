"""Réteg-katalógus generálása — a meccs-csomag minden regisztrált
elemző rétege egy helyen, egysoros magyar magyarázattal.

A katalógus a pályázati/bemutató anyagok "N elemző réteg" állításának
ellenőrizhető alátámasztása, és belső térkép is: melyik réteg melyik
modulban él, és mit mér. A kimenet a docs/RETEG_KATALOGUS.md — a
teszt-csomag őre (test_layer_registry) frissen tartja.

Használat:
    cd backend && python -m scripts.layer_catalog          # kiírja
    cd backend && python -m scripts.layer_catalog --check  # csak összevet
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_APP = _BACKEND / "handball" / "api" / "app.py"
_PIPELINE = _BACKEND / "handball" / "pipeline"
_OUT = _BACKEND.parent / "docs" / "RETEG_KATALOGUS.md"


def _registered_layers() -> dict[str, str]:
    """{réteg-név: a lambda által hívott függvény neve} — ha a kettő
    eltér (álnév), a hívott függvény docstringje a mérvadó."""
    src = _APP.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for m in re.finditer(
            r'_layer\(\s*"([a-z0-9_]+)"\s*,\s*\n?\s*lambda:\s*'
            r'([A-Za-z_][A-Za-z0-9_.]*)\(', src):
        out[m.group(1)] = m.group(2).split(".")[-1]
    # Amit a lambda-minta nem talált meg, a saját nevén keressük.
    for name in re.findall(r'_layer\(\s*"([a-z0-9_]+)"', src):
        out.setdefault(name, name)
    return out


def _find_layer(name: str) -> tuple[str, str]:
    """(modul, egysoros leírás) a réteg-függvényhez; ha nincs önálló
    függvény (beágyazott/összetett réteg), a leírás '—'."""
    pat = re.compile(rf"def {name}\(.*?\n\s+\"\"\"(.+?)(?:\n|\"\"\")",
                     re.S)
    for mod in sorted(_PIPELINE.glob("*.py")):
        src = mod.read_text(encoding="utf-8")
        if f"def {name}(" not in src:
            continue
        m = pat.search(src)
        desc = m.group(1).strip() if m else "—"
        return mod.stem, desc
    return "api/app.py", "— (összetett/beágyazott réteg)"


def build_catalog() -> str:
    layers = _registered_layers()
    by_module: dict[str, list[tuple[str, str]]] = {}
    for name, fn in sorted(layers.items()):
        mod, desc = _find_layer(fn)
        by_module.setdefault(mod, []).append((name, desc))

    n_layers = len(layers)
    lines = [
        "# Réteg-katalógus — a meccs-csomag regisztrált elemző rétegei",
        "",
        "*Generált fájl — ne kézzel szerkeszd. Frissítés:*",
        "`cd backend && python -m scripts.layer_catalog`",
        "",
        f"Összesen **{n_layers} réteg**, modulonként csoportosítva; a",
        "leírás a réteg-függvény docstringjének első sora.",
        "",
    ]
    for mod in sorted(by_module):
        lines.append(f"## {mod} ({len(by_module[mod])})")
        lines.append("")
        lines.append("| Réteg | Mit mér |")
        lines.append("|---|---|")
        for name, desc in sorted(by_module[mod]):
            desc = " ".join(desc.split())
            lines.append(f"| `{name}` | {desc} |")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def main(argv=None) -> int:
    check = "--check" in (argv or sys.argv[1:])
    text = build_catalog()
    if check:
        current = _OUT.read_text(encoding="utf-8") if _OUT.exists() else ""
        if current != text:
            print("ELTÉRÉS: a katalógus elavult — futtasd: "
                  "python -m scripts.layer_catalog", file=sys.stderr)
            return 1
        print("A katalógus friss.")
        return 0
    _OUT.write_text(text, encoding="utf-8")
    n = text.count("| `")
    print(f"Katalógus kiírva: {_OUT} ({n} réteg)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
