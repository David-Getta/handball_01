"""A kiadás-jegyzet előállításának (scripts.release_notes) tesztjei.

Az app MEGMUTATJA a GitHub-kiadás leírását a frissítés előtt — ott
tehát a tényleges változás-listának kell állnia, nem sablonszövegnek.
"""
from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.release_notes import MAX_CHARS, build, main, section

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


def test_a_kiadatlan_szakasz_a_friss_kiadas_leirasa():
    """A kiadás készítésekor a verzió saját szakasza még NEM létezik (a
    munkarend utána zárja le) — a "Kiadatlan" szakasz a frissen kiadott
    tartalom. E nélkül minden kiadás leírása sablonszöveg volt, pedig az
    app pont ezt mutatja a frissítés előtt."""
    text = build("9.9.9", _SAMPLE)
    assert "SportMachine-Setup.exe" in text
    assert "Mi változott a v9.9.9-ben" in text
    assert "Egy még ki nem adott dolog" in text
    assert "Első újdonság" not in text          # az a v0.1.24-é
    assert "CHANGELOG.md" in text


def test_hianyzo_szakasznal_is_kimegy_a_kiadas():
    """Ha se a verzió szakasza, se Kiadatlan szakasz nincs, a telepítési
    rész akkor is kimegy — egy hiányzó changelog-szakasz miatt nem
    maradhat el a kiadás.
    """
    nincs = _SAMPLE.replace("## Kiadatlan (a v0.1.24 óta)\n\n"
                            "- Egy még ki nem adott dolog.\n\n", "")
    text = build("9.9.9", nincs)
    assert "SportMachine-Setup.exe" in text
    assert "CHANGELOG.md" in text
    assert "Első újdonság" not in text
    assert "ki nem adott" not in text


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
    # MINDEN feltöltő job adja a leírást. A két platform-job UGYANAZT a
    # kiadást frissíti; ha az egyik leírás NÉLKÜL tölt fel, és ő fut le
    # utoljára, KIÜTI a másik által beírt változás-listát — a kiadás
    # leírás nélkül marad (így járt a v0.1.136), és az app
    # "Újdonságok" ablaka üresen jön elő a frissítés után.
    kiadok = text.count("uses: softprops/action-gh-release")
    assert kiadok == text.count("body_path: release_notes.md"), (
        f"{kiadok} feltöltő job van, de nem mind adja a kiadás leírását")
    assert text.count("scripts.release_notes") == kiadok, (
        "van olyan feltöltő job, amelyik nem generálja a jegyzetet")


def test_fajlba_iras_utf8(tmp_path):
    """A kimenet FÁJLBA, kimondott UTF-8 kódolással megy.

    A Windows-futtatón a Python alapértelmezett kimeneti kódolása
    cp1252, és a magyar szöveg nyilai (→) ott UnicodeEncodeError-t
    adnak — a kiadás emiatt bukott el egyszer. A fájl-írás kódolása
    ezért kimondott.
    """
    out = tmp_path / "notes.md"
    assert main(["0.1.24", "--out", str(out)]) == 0
    text = out.read_text(encoding="utf-8")
    assert "Mi változott a v0.1.24-ben" in text
    # Van benne nem-ASCII (magyar ékezet és/vagy nyíl) — ez a lényeg.
    assert any(ord(ch) > 127 for ch in text)


def test_a_workflow_fajlba_irat():
    """A workflow a --out kapcsolót használja, nem átirányítást.

    Átirányításnál a Windows-futtató kódolása döntene, és a magyar
    szöveg elhasalna.
    """
    import pathlib

    wf = (pathlib.Path(__file__).resolve().parent.parent.parent
          / ".github" / "workflows" / "release.yml")
    if not wf.exists():
        import pytest
        pytest.skip("nincs kiadási workflow a fában")
    text = wf.read_text(encoding="utf-8")
    assert "--out" in text, "a workflow nem fájlba íratja a jegyzetet"


# ---- A "Kiadatlan" szakasz és a kimenetre írás (eddig közvetlen teszt nélkül) --

def test_unreleased_section_a_kiadatlan_szakasz_torzse():
    """A "## Kiadatlan (…)" szakasz törzse a fejléc nélkül, a szélein
    üres sor nélkül — a következő szakasz (a legutóbb kiadott verzió)
    nem szivárog bele."""
    from scripts.release_notes import unreleased_section

    assert unreleased_section(_SAMPLE) == "- Egy még ki nem adott dolog."
    tobb = _SAMPLE.replace(
        "- Egy még ki nem adott dolog.",
        "- Első kiadatlan.\n  folytatás\n- Második kiadatlan.")
    torzs = unreleased_section(tobb)
    assert torzs == "- Első kiadatlan.\n  folytatás\n- Második kiadatlan."
    assert "Első újdonság" not in torzs and "v0.1.24" not in torzs
    # A fejléc zárójeles része szabad szöveg, a szakasz a fájl végéig is
    # tarthat.
    assert unreleased_section("## Kiadatlan\n\n- a\n- b\n") == "- a\n- b"


def test_unreleased_section_nincs_vagy_ures_szakasznal_none():
    """Ha nincs Kiadatlan szakasz, vagy a törzse üres (frissen lezárt
    kiadás után), None — a hívó ilyenkor a CHANGELOG-ra mutat, nem üres
    "Mi változott" listát ad."""
    from scripts.release_notes import unreleased_section

    assert unreleased_section("") is None
    assert unreleased_section("# Változásnapló\n\n## v1.0.0 — kiadva\n\n- x\n"
                              ) is None
    ures = _SAMPLE.replace("- Egy még ki nem adott dolog.\n\n", "")
    assert "## Kiadatlan" in ures
    assert unreleased_section(ures) is None
    assert unreleased_section("## Kiadatlan (a v1 óta)\n\n   \n") is None
    # A "Kiadatlan" szó a szöveg belsejében nem szakasz-fejléc.
    assert unreleased_section("Lásd a ## Kiadatlan részt.\n") is None
    # Üres Kiadatlan szakasznál a leírás a CHANGELOG-ra mutat.
    text = build("9.9.9", ures)
    assert "lásd a CHANGELOG.md-t" in text
    assert "Mi változott" not in text


def test_az_eles_changelog_kiadatlan_szakasza_olvashato():
    """Az ÉLES CHANGELOG-ban a Kiadatlan szakasz megvan és a minta illik
    rá — a következő kiadás leírása ebből készül."""
    import pathlib

    from scripts.release_notes import unreleased_section

    cl = (pathlib.Path(__file__).resolve().parent.parent.parent
          / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "\n## Kiadatlan" in cl
    torzs = unreleased_section(cl)
    if torzs is not None:                      # közvetlenül kiadás után üres
        assert torzs.startswith("- ") or torzs.startswith(">")
        assert "\n## " not in torzs


def test_main_kimeneti_fajl_nelkul_a_kimenetre_ir(capsys):
    """--out nélkül a leírás a kimenetre megy (ugyanaz a szöveg, mint a
    fájlba írt), 0-s kilépőkóddal."""
    assert main(["0.1.24"]) == 0
    ki = capsys.readouterr().out
    assert ki == build("0.1.24")
    assert "Mi változott a v0.1.24-ben" in ki
    assert "SportMachine-Setup.exe" in ki


def test_build_changelog_fajl_nelkul_is_kiadja_a_telepitest(monkeypatch,
                                                            tmp_path):
    """Ha a CHANGELOG fájl nincs meg (csonka kivétel), a kiadás leírása
    akkor is elkészül: telepítési tudnivaló + mutató a CHANGELOG-ra."""
    from scripts import release_notes as rn

    monkeypatch.setattr(rn, "_CHANGELOG", tmp_path / "nincs.md")
    text = rn.build("1.2.3")
    assert "SportMachine-Setup.exe" in text
    assert "lásd a CHANGELOG.md-t" in text
    assert "Mi változott" not in text
