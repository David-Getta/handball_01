"""
Tesztek a projekt-tények szkriptjére (scripts/project_facts.py).

A csomag a szkriptet eddig csak külön folyamatban (`--check`) és a
doksi-szinkronján át futtatta: a tény-lap építője, a szám-tagoló és a
main (író és ellenőrző módja) közvetlen teszt nélkül maradt. Itt a main
a tmp mappába ír — a valódi docs/SZAMOK.md-hez és a doksikhoz a teszt
nem nyúl.

Futtatás:
    python -m pytest tests/test_project_facts.py -q
"""

from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import project_facts as pf  # noqa: E402


def test_collect_facts_a_kodbazisbol_szamol():
    """A hat hivatkozható szám egész, pozitív, és a forrásból
    újraszámolható (itt a teszt-darabszámot számoljuk utána)."""
    f = pf.collect_facts()
    assert set(f) == {"layers", "tests", "matchup_rules", "training_rules",
                      "tiles", "modules"}
    assert all(isinstance(v, int) and v > 0 for v in f.values()), f
    kezzel = sum(
        len(re.findall(r"^def test_\w+", p.read_text(encoding="utf-8"),
                       flags=re.M))
        for p in sorted(pf._TESTS.glob("test_*.py")))
    assert f["tests"] == kezzel
    assert f["modules"] == len(list(pf._PIPELINE.glob("*.py")))
    assert f["layers"] >= 500                    # "500+ réteg"


def test_build_facts_md_a_szamokat_a_tablaba_irja(monkeypatch):
    """A tény-lap táblája minden mértéket a számával és a forrásával
    hoz — a doksik őre (és az olvasó) ebből a sor-alakból dolgozik."""
    monkeypatch.setattr(pf, "collect_facts", lambda: {
        "layers": 521, "tests": 3141, "matchup_rules": 475,
        "training_rules": 495, "tiles": 496, "modules": 63})
    md = pf.build_facts_md()
    assert md.startswith("# Projekt-számok (generált tény-lap)\n")
    assert "*Generált fájl — ne kézzel szerkeszd." in md
    for cimke, szam in (("Elemző réteg (meccs-csomag)", 521),
                        ("Automata teszt", 3141),
                        ("Meccsterv-szabály", 475), ("Edzés-szabály", 495),
                        ("Kliens-csempe (felderítés)", 496),
                        ("Pipeline-modul", 63)):
        assert f"| {cimke} | **{szam}** | " in md, cimke
    # A doksi-őr mintája (test_layer_registry) illik a sorokra.
    m = re.search(r"\| Automata teszt [^|]*\| \*\*(\d+)\*\*", md)
    assert m and int(m.group(1)) == 3141
    assert md.endswith("[`docs/RETEG_KATALOGUS.md`](RETEG_KATALOGUS.md).\n")


def test_build_facts_md_a_valodi_szamokkal_determinisztikus():
    """A VALÓDI kódbázisból a lap kétszer építve bitre ugyanaz (a
    `--check` ezt veti össze a beírt docs/SZAMOK.md-vel), és a beírt lap
    ugyanazt a tábla-szerkezetet viszi, mértékenként egy sorral."""
    elso = pf.build_facts_md()
    assert elso == pf.build_facts_md()
    tenyek = pf.collect_facts()
    assert f"| Automata teszt | **{tenyek['tests']}** |" in elso
    beirt = pf._OUT.read_text(encoding="utf-8")

    def sorok(md):
        return [s.split("|")[1].strip() for s in md.splitlines()
                if s.startswith("| ") and "**" in s]
    assert sorok(beirt) == sorok(elso) and len(sorok(elso)) == 6


def test_grouped_megtartja_a_doksi_tagolasat():
    """Ahol a doksiban a szám vesszővel tagolt volt ("1,227"), az új szám
    is tagolt; ahol nem, ott nem — a kis szám sosem kap vesszőt."""
    assert pf._grouped(3141, "1,227") == "3,141"
    assert pf._grouped(3141, "1227") == "3141"
    assert pf._grouped(521, "1,227") == "521"
    assert pf._grouped(1234567, "9,999") == "1,234,567"
    assert pf._grouped(0, "12") == "0"


def _proba_gyoker(tmp_path, monkeypatch):
    """Próba-repó a tmp mappában: egy magyar és egy angol doksi + README
    elavult számokkal, és egy generált doksi (amit nem bántunk)."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "PITCH.md").write_text(
        "A termék 300 elemző réteg fölött jár, 1227 automata teszt őrzi.\n",
        encoding="utf-8")
    (docs / "SUMMARY_EN.md").write_text(
        "Over 300 analysis layers, guarded by 1,227 automated tests.\n",
        encoding="utf-8")
    (docs / "RETEG_KATALOGUS.md").write_text(
        "Generált: 1 elemző réteg.\n", encoding="utf-8")
    (docs / "FRISS.md").write_text("Nincs benne szám.\n", encoding="utf-8")
    (tmp_path / "README.md").write_text(
        "- **Minőség**: 12 automata teszt.\n", encoding="utf-8")
    monkeypatch.setattr(pf, "_ROOT", tmp_path)
    monkeypatch.setattr(pf, "_OUT", docs / "SZAMOK.md")
    return docs


def test_sync_docs_igazitja_a_szovegbe_irt_szamokat(tmp_path, monkeypatch):
    """A doksikba írt réteg- és teszt-számok a tény-laphoz igazodnak,
    magyarul és angolul (a vesszős tagolás megmarad), a README-ben is; a
    generált doksi és a szám nélküli fájl érintetlen."""
    docs = _proba_gyoker(tmp_path, monkeypatch)
    tenyek = {"layers": 521, "tests": 3141}

    elavult = pf.sync_docs(tenyek, write=False)
    assert elavult == ["PITCH.md", "SUMMARY_EN.md", "README.md"]
    assert "300 elemző réteg" in (docs / "PITCH.md").read_text(
        encoding="utf-8")                        # write=False nem ír

    assert pf.sync_docs(tenyek) == elavult
    assert (docs / "PITCH.md").read_text(encoding="utf-8") == (
        "A termék 521 elemző réteg fölött jár, 3141 automata teszt őrzi.\n")
    assert (docs / "SUMMARY_EN.md").read_text(encoding="utf-8") == (
        "Over 521 analysis layers, guarded by 3,141 automated tests.\n")
    assert (tmp_path / "README.md").read_text(encoding="utf-8") == (
        "- **Minőség**: 3141 automata teszt.\n")
    assert (docs / "RETEG_KATALOGUS.md").read_text(encoding="utf-8") == (
        "Generált: 1 elemző réteg.\n")
    # Másodszorra már nincs mit igazítani.
    assert pf.sync_docs(tenyek) == []
    assert pf.sync_docs(tenyek, write=False) == []


def test_main_megirja_a_teny_lapot_es_igazitja_a_doksikat(tmp_path,
                                                          monkeypatch,
                                                          capsys):
    """Író módban a main megírja a tény-lapot, kiírja a számokat, és a
    doksikat is igazítja; utána az ellenőrző mód (--check) zöld."""
    docs = _proba_gyoker(tmp_path, monkeypatch)
    tenyek = pf.collect_facts()

    assert pf.main([]) == 0
    assert (docs / "SZAMOK.md").read_text(encoding="utf-8") == \
        pf.build_facts_md()
    ki = capsys.readouterr().out
    assert f"Tény-lap kiírva: {docs / 'SZAMOK.md'}" in ki
    assert f"  tests: {tenyek['tests']}" in ki
    assert f"  layers: {tenyek['layers']}" in ki
    assert "frissített doksik: PITCH.md, SUMMARY_EN.md, README.md" in ki
    assert f"{tenyek['layers']} elemző réteg" in (docs / "PITCH.md").read_text(
        encoding="utf-8")

    assert pf.main(["--check"]) == 0
    assert "A tény-lap friss." in capsys.readouterr().out
    # Újra írva már nincs frissítendő doksi.
    assert pf.main([]) == 0
    assert "frissített doksik" not in capsys.readouterr().out


def test_main_check_elavult_lapnal_vagy_doksinal_1_es_kod(tmp_path,
                                                          monkeypatch,
                                                          capsys):
    """Az ellenőrző mód NEM ír: hiányzó vagy elavult tény-lapnál, illetve
    elavult doksi-számnál 1-es kilépőkód, beszélő üzenettel (a teendővel
    és a fájlok nevével)."""
    docs = _proba_gyoker(tmp_path, monkeypatch)

    # 1) Nincs tény-lap.
    assert pf.main(["--check"]) == 1
    assert "a tény-lap elavult — futtasd: python -m scripts.project_facts" \
        in capsys.readouterr().err
    assert not (docs / "SZAMOK.md").exists()

    # 2) A tény-lap friss, de a doksik számai elavultak.
    (docs / "SZAMOK.md").write_text(pf.build_facts_md(), encoding="utf-8")
    assert pf.main(["--check"]) == 1
    hiba = capsys.readouterr().err
    assert "elavult számok a doksikban (PITCH.md, SUMMARY_EN.md, README.md)" \
        in hiba
    assert "300 elemző réteg" in (docs / "PITCH.md").read_text(
        encoding="utf-8")

    # 3) Kézzel átírt (elavult) tény-lap.
    pf.sync_docs(pf.collect_facts())
    (docs / "SZAMOK.md").write_text(
        pf.build_facts_md().replace("**", "*", 2), encoding="utf-8")
    assert pf.main(["--check"]) == 1
    assert "a tény-lap elavult" in capsys.readouterr().err
