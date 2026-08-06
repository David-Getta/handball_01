"""Kiadás-jegyzet előállítása a CHANGELOG-ból.

A GitHub-kiadás leírása eddig sablonszöveg volt ("Újdonságok: lásd a
CHANGELOG.md-t"). Az app viszont MEGMUTATJA ezt a leírást a frissítés
előtt — a felhasználó tehát pont ott olvasta volna el, mi változik, és
pont ott nem kapott választ.

Ez a szkript kiszedi a CHANGELOG-ból az adott verzió szakaszát, és
elé teszi a telepítési tudnivalót. A workflow ezt a fájlt adja át a
kiadásnak.

Használat:
    cd backend && python -m scripts.release_notes 0.1.24 > notes.md
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_CHANGELOG = _ROOT / "CHANGELOG.md"

# A GitHub-kiadás leírásának felső korlátja 125 000 karakter. Ennél
# jóval korábban olvashatatlan, ezért itt vágunk — a teljes szöveg a
# CHANGELOG-ban marad meg.
MAX_CHARS = 20000

_INSTALL = """**Sport Machine**

- **Windows**: töltsd le a `SportMachine-Setup.exe`-t, dupla kattintás,
  majd Tovább → Telepítés. Részletes (laikus) útmutató: TELEPITES.md.
- **macOS**: töltsd le a `SportMachine-macOS.zip`-et, csomagold ki, és
  húzd az alkalmazást az Applications mappába.
"""


def section(changelog: str, version: str) -> str | None:
    """Az adott verzió szakasza a CHANGELOG-ból (fejléc nélkül).

    A fejléc alakja: `## v0.1.24 — kiadva (2026-08-06)`. A szakasz a
    következő `## ` kezdetű sorig tart. Ha nincs ilyen verzió, None.
    """
    pattern = re.compile(
        r"^## v" + re.escape(version) + r"\b[^\n]*\n(.*?)(?=^## |\Z)",
        re.S | re.M)
    m = pattern.search(changelog)
    if m is None:
        return None
    return m.group(1).strip()


def build(version: str, changelog: str | None = None) -> str:
    """A kiadás teljes leírása: telepítés + a verzió változásai.

    Ha a verzió szakasza nem található, a telepítési rész akkor is
    kimegy, a változás-lista helyett pedig a CHANGELOG-ra mutatunk —
    egy hiányzó szakasz miatt nem maradhat el a kiadás.
    """
    if changelog is None:
        changelog = (_CHANGELOG.read_text(encoding="utf-8")
                     if _CHANGELOG.exists() else "")
    body = section(changelog, version)
    if not body:
        return (_INSTALL + "\nÚjdonságok e kiadásban: lásd a CHANGELOG.md-t "
                "a repó gyökerében.\n")
    if len(body) > MAX_CHARS:
        body = (body[:MAX_CHARS].rsplit("\n", 1)[0]
                + "\n\n*(A lista folytatása a CHANGELOG.md-ben.)*")
    return f"{_INSTALL}\n## Mi változott a v{version}-ben\n\n{body}\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("version", help="a kiadás verziója, v nélkül (0.1.24)")
    args = ap.parse_args(argv)
    sys.stdout.write(build(args.version))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
