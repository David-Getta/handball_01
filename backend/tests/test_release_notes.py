"""A kiadás-jegyzet előállításának (scripts.release_notes) tesztjei.

Az app MEGMUTATJA a GitHub-kiadás leírását a frissítés előtt — ott
tehát a tényleges változás-listának kell állnia, nem sablonszövegnek.
"""
from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.release_notes import MAX_CHARS, build, section

_SAMPLE = """# Változásnapló (CHANGELOG)

Bevezető szöveg.

## Kiadatlan (a v0.1.24 óta)

- Egy még ki nem adott dolog.

## v0.1.24 — kiadva (2026-08-06)

> Kiadás-jegyzet: valami fontos.

- **Első újdonság.** Leírás.
- **Második újdonság.** Leírás.

## v0.1.23 — kiadva (2026-08-01)

- Régi dolog, ami NEM tartozik ide.
"""


def test_kiszedi_a_verzio_szakaszat():
    """A megadott verzió szakasza jön vissza, a fejléc nélkül."""
    body = section(_SAMPLE, "0.1.24")
    assert body is not None
    assert "Első újdonság" in body and "Második újdonság" in body
    assert "Kiadás-jegyzet: valami fontos." in body


def test_nem_szivarog_be_a_szomszed_szakasz():
    """Sem a korábbi kiadás, sem a kiadatlan rész nem kerül bele."""
    body = section(_SAMPLE, "0.1.24") or ""
    assert "Régi dolog" not in body
    assert "Egy még ki nem adott dolog" not in body
    assert "## v0.1.23" not in body


def test_ismeretlen_verzio_nincs_szakasz():
    """Nem létező verzióra None — a hívó dönt, mit tesz."""
    assert section(_SAMPLE, "9.9.9") is None


def test_a_teljes_leiras_tartalmazza_a_telepitest():
    """A leírásban a telepítési tudnivaló IS benne van, mindkét
    platformra — ez a kiadási oldal legfontosabb szövege."""
    text = build("0.1.24", _SAMPLE)
    assert "SportMachine-Setup.exe" in text
    assert "SportMachine-macOS.zip" in text
    assert "Mi változott a v0.1.24-ben" in text
    assert "Első újdonság" in text


def test_hianyzo_szakasznal_is_kimegy_a_kiadas():
    """Ha a verzió szakasza hiányzik, a telepítési rész akkor is kimegy.

    Egy hiányzó changelog-szakasz miatt nem maradhat el a kiadás — a
    felhasználó a telepítéshez akkor is kap útmutatót.
    """
    text = build("9.9.9", _SAMPLE)
    assert "SportMachine-Setup.exe" in text
    assert "CHANGELOG.md" in text
    assert "Első újdonság" not in text


def test_tul_hosszu_szakasz_vagodik():
    """Nagyon hosszú szakasz vágódik, és a vágást ki is mondjuk."""
    long_body = "\n".join(f"- Tétel {i}." for i in range(20000))
    sample = f"## v1.0.0 — kiadva (2026-01-01)\n\n{long_body}\n"
    text = build("1.0.0", sample)
    assert len(text) < MAX_CHARS + 2000
    assert "folytatása a CHANGELOG.md-ben" in text


def test_eles_changelogbol_a_kiadott_verzio():
    """Az ÉLES CHANGELOG-ból a v0.1.24 szakasza értelmes leírást ad."""
    text = build("0.1.24")
    assert "Mi változott a v0.1.24-ben" in text, text[:200]
    assert len(text) > 500


def test_a_workflow_a_szkriptbol_veszi_a_leirast():
    """A kiadási workflow ezt a szkriptet hívja, és a fájlját adja át.

    Enélkül a szkript zölden tesztelt, de a kiadás továbbra is
    sablonszöveget kapna — a felhasználó pedig épp azt olvasná el a
    frissítés előtt.
    """
    import pathlib

    wf = (pathlib.Path(__file__).resolve().parent.parent.parent
          / ".github" / "workflows" / "release.yml")
    if not wf.exists():
        import pytest
        pytest.skip("nincs kiadási workflow a fában")
    text = wf.read_text(encoding="utf-8")
    assert "scripts.release_notes" in text, (
        "a workflow nem a jegyzet-szkriptből dolgozik")
    assert "body_path: release_notes.md" in text, (
        "a kiadás nem a generált fájlt kapja")
    assert "Újdonságok e kiadásban: lásd a CHANGELOG.md-t" not in text, (
        "a régi sablonszöveg még bent van a workflow-ban")
