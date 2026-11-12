"""
A sebesség-profil (scripts.speed_profile) tesztjei.

A teljes, 60 perces mérés percekig tart és GÉPFÜGGŐ számot ad, ezért
az a jelentés-szkript dolga (docs/SEBESSEG.md). Itt a mechanikát
rögzítjük gyors tesztekkel: a mérés a termék hatókörében fut és
rétegenként ad időt, az ítélet a cél-küszöbhöz mér (rövid mérésnél a
teljes meccsre vetítve), a jegyzőkönyv-sor pedig a Sebesség tábla
VÉGÉRE kerül — és a tábla a dokumentumban tényleg ott van.

Futtatás:
    python -m pytest tests/test_speed_profile.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts import speed_profile as sp  # noqa: E402

_DOCS = Path(__file__).resolve().parents[2] / "docs"


def test_a_meres_retegenkent_ad_idot_es_osszegez():
    """Két réteg rövid meccsen: mindkettőnek van ideje, az összeg a
    kettő összege, a gyors-kép rész csak a gyors-kép rétegeké."""
    res = sp.measure(seconds=12.0, seed=3, only=("xg", "coach_summary"))
    nevek = [n for n, _ in res["retegek"]]
    assert sorted(nevek) == ["coach_summary", "xg"]
    idok = {n: t for n, t in res["retegek"]}
    assert all(t is not None and t >= 0 for t in idok.values())
    assert abs(res["osszes_s"] - sum(idok.values())) < 1e-9
    # Mindkét réteg a gyors képhez tartozik → a gyors kép = az összes.
    assert abs(res["gyors_kep_s"] - res["osszes_s"]) < 1e-9
    assert res["hibas"] == []
    assert res["frames"] > 0 and res["fps"] == sp.DEFAULT_FPS


def test_az_itelet_a_teljes_meccsre_vetit():
    """Rövid mérésnél az idő a 60 percre arányosítva mérődik a célhoz:
    6 perces mérésen 30 mp réteg-idő = 5 perc vetítve → még MEGFELEL,
    31 mp már GYENGE."""
    alap = {"seconds": 360.0, "retegek": []}
    assert sp.itelet({**alap, "osszes_s": 30.0}) == "MEGFELEL"
    assert sp.itelet({**alap, "osszes_s": 31.0}) == "GYENGE"
    # Teljes meccsen a küszöb maga a cél.
    teljes = {"seconds": sp.DEFAULT_SECONDS, "retegek": []}
    assert sp.itelet({**teljes, "osszes_s": sp.SEBESSEG_CEL_RETEGEK_S}) == "MEGFELEL"
    assert sp.itelet({**teljes, "osszes_s": sp.SEBESSEG_CEL_RETEGEK_S + 1}) == "GYENGE"


def _minta_eredmeny():
    return {"seconds": 3600.0, "fps": sp.DEFAULT_FPS, "frames": 30000,
            "szimulacio_s": 4.0, "osszes_s": 125.0, "gyors_kep_s": 20.0,
            "hibas": [],
            "retegek": [("xg", 20.0), ("defense", 100.0), ("blocks", 5.0),
                        ("torott", None)]}


def test_a_jelentes_rangsorol_es_itel():
    rep = sp.build_report(_minta_eredmeny(), "v0.1.193", "teszt-gép")
    assert "Rétegek összesen: 2 perc 5 mp" in rep
    assert "MEGFELEL" in rep
    # A leglassabb elöl, a csomag %-ával.
    i_def, i_xg = rep.index("`defense`"), rep.index("`xg`")
    assert i_def < i_xg
    assert "| `defense` | 1 perc 40 mp | 80.0% |" in rep
    assert "v0.1.193" in rep and "teszt-gép" in rep


def test_a_jegyzokonyv_sor_a_tabla_vegere_kerul(tmp_path):
    doc = tmp_path / "j.md"
    doc.write_text("# Napló\n\n## Sebesség\n\n" + sp.SEBESSEG_FEJLEC +
                   "\n|---|---|---|---|---|---|---|---|\n"
                   "| 2026-01-01 | v0 | régi | 1 | 1,0 mp | 0,5 mp | g | MEGFELEL |\n"
                   "\nUtána szöveg.\n", encoding="utf-8")
    sor = sp.jegyzokonyv_sor(_minta_eredmeny(), "v0.1.193", "teszt-gép",
                             datum="2026-11-06")
    assert sor.startswith("| 2026-11-06 | v0.1.193 | szimulált, 60 perc, 30000 kocka | 3 |")
    assert "| 2 perc 5 mp | 20,0 mp | teszt-gép | MEGFELEL |" in sor
    sp.append_jegyzokonyv(sor, doc)
    sorok = doc.read_text(encoding="utf-8").split("\n")
    regi = next(i for i, s in enumerate(sorok) if s.startswith("| 2026-01-01"))
    assert sorok[regi + 1] == sor
    assert sorok[regi + 2] == ""  # a tábla utáni üres sor megmaradt


def test_a_jegyzokonyvben_van_sebesseg_tabla():
    """A szkript a VALÓDI jegyzőkönyvbe ír — a fejlécnek ott kell
    lennie, különben a `--jegyzokonyv` hibával áll meg."""
    text = (_DOCS / "MERESI_JEGYZOKONYV.md").read_text(encoding="utf-8")
    assert sp.SEBESSEG_FEJLEC in text


# ---- A segédek, a hibás réteg és a main (eddig egyszer sem futottak) ----------

def test_az_ido_ember_olvashato_alakban():
    """Az idő alakja: egy másodperc alatt ezredmásodperc, egy perc alatt
    tizedes másodperc (magyar tizedesvesszővel), fölötte perc (+ mp)."""
    assert sp._ido(0.0) == "0 ms"
    assert sp._ido(0.12) == "120 ms"
    assert sp._ido(0.9994) == "999 ms"
    assert sp._ido(1.0) == "1,0 mp"
    assert sp._ido(12.34) == "12,3 mp"
    assert sp._ido(59.94) == "59,9 mp"
    assert sp._ido(60.0) == "1 perc"
    assert sp._ido(125.0) == "2 perc 5 mp"
    assert sp._ido(sp.SEBESSEG_CEL_TELJES_S) == "15 perc"


def test_a_gep_leiras_egy_sorban_megnevezi_a_gepet():
    """A mérés gépe egy sorban: processzor, magok száma, Python-verzió —
    a szám csak ezzel együtt értelmezhető."""
    import platform
    import re

    gep = sp._gep_leiras()
    assert "\n" not in gep
    assert re.fullmatch(r".+, \d+ mag, Python \d+\.\d+\.\d+.*", gep), gep
    assert platform.python_version() in gep
    assert f", {os.cpu_count()} mag," in gep


def test_a_gep_leiras_ismeretlen_gepen_sem_ures(monkeypatch):
    """Ha a rendszer nem árulja el a processzort (üres szöveg), az
    architektúra, végső soron "?" áll a helyén — sosem üres mező."""
    import platform

    monkeypatch.setattr(platform, "processor", lambda: "")
    monkeypatch.setattr(platform, "machine", lambda: "arm64")
    assert sp._gep_leiras().startswith("arm64, ")
    monkeypatch.setattr(platform, "machine", lambda: "")
    assert sp._gep_leiras().startswith("?, ")


def test_a_verzio_a_kiadott_verzio_es_a_commit_hash(monkeypatch, tmp_path):
    """A verzió-címke a CHANGELOG utolsó KIADOTT verziója + a rövid
    commit-hash; hash nélkül (nincs git) csak a verzió; CHANGELOG nélkül
    "dev"."""
    from types import SimpleNamespace

    (tmp_path / "CHANGELOG.md").write_text(
        "# Változásnapló\n\n## Kiadatlan (a v0.1.9 óta)\n\n- új\n\n"
        "## v0.1.9 — kiadva 2026-11-01\n\n- régi\n\n"
        "## v0.1.8 — kiadva 2026-10-01\n", encoding="utf-8")
    (tmp_path / "backend").mkdir()
    monkeypatch.setattr(sp, "_BACKEND", tmp_path / "backend")

    monkeypatch.setattr(sp.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(stdout="abc1234\n"))
    assert sp._verzio() == "v0.1.9+abc1234"
    monkeypatch.setattr(sp.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(stdout=""))
    assert sp._verzio() == "v0.1.9"

    def nincs_git(*a, **k):
        raise FileNotFoundError("git")
    monkeypatch.setattr(sp.subprocess, "run", nincs_git)
    assert sp._verzio() == "v0.1.9"

    (tmp_path / "CHANGELOG.md").unlink()
    assert sp._verzio() == "dev"
    monkeypatch.setattr(sp.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(stdout="abc1234\n"))
    assert sp._verzio() == "dev+abc1234"


def test_a_verzio_a_valodi_valtozasnaplobol(monkeypatch):
    """A VALÓDI CHANGELOG-ból: a címke egy kiadott verzióval kezdődik
    (a fejléc-minta ma is illik a naplóra)."""
    import re
    from types import SimpleNamespace

    monkeypatch.setattr(sp.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(stdout=""))
    assert re.fullmatch(r"v\d+\.\d+\.\d+", sp._verzio()), sp._verzio()


def test_a_hibas_reteg_ido_nelkul_a_hibasok_kozt(monkeypatch):
    """A hibára futó és a nem létező réteg idő nélkül (None) kerül a
    listára és a "hibas" névsorba — az összeg csak a mért rétegeké, a
    jelentés pedig megnevezi a kihagyottakat."""
    from handball.pipeline import xg
    from scripts import order_sensitivity

    def bukik(match):
        raise RuntimeError("nem megy")

    monkeypatch.setattr(xg, "_proba_bukik", bukik, raising=False)
    monkeypatch.setattr(order_sensitivity, "_layer_functions", lambda: [
        ("xg", "xg", "match_xg"), ("bukó", "xg", "_proba_bukik"),
        ("hiányzó", "xg", "_nincs_ilyen_fuggveny"),
        ("rossz modul", "nincs_ilyen_modul", "f")])
    res = sp.measure(seconds=6.0, seed=3)
    idok = dict(res["retegek"])
    assert list(idok) == ["xg", "bukó", "hiányzó", "rossz modul"]
    assert idok["xg"] is not None and idok["xg"] >= 0
    assert idok["bukó"] is None and idok["hiányzó"] is None
    assert idok["rossz modul"] is None
    assert res["hibas"] == ["bukó", "hiányzó", "rossz modul"]
    assert abs(res["osszes_s"] - idok["xg"]) < 1e-9
    rep = sp.build_report(res, "v0", "gép")
    assert "- Hibára futott / kihagyott: 3 (bukó, hiányzó, rossz modul)" in rep
    assert "## A 1 leglassabb réteg" in rep

    # Réteg nélkül nincs mit mérni: nulla összeg, üres rangsor, 0 átlag.
    monkeypatch.setattr(order_sensitivity, "_layer_functions", lambda: [])
    ures = sp.measure(seconds=6.0, seed=3)
    assert ures["retegek"] == [] and ures["osszes_s"] == 0.0
    rep = sp.build_report(ures, "v0", "gép")
    assert "(0 réteg, átlag 0 ms)" in rep and "## A 0 leglassabb réteg" in rep


def test_a_jelentes_sok_hibas_retegnel_roviditi_a_nevsort():
    """Nyolcnál több hibás rétegnél a névsor az első nyolc (ábécében) és
    egy "…" — a darabszám a teljes."""
    res = _minta_eredmeny()
    res["hibas"] = [f"r{i:02d}" for i in range(11, 0, -1)]
    rep = sp.build_report(res, "v0", "gép")
    assert ("- Hibára futott / kihagyott: 11 (r01, r02, r03, r04, r05, "
            "r06, r07, r08, …)") in rep


def test_a_jegyzokonyv_tabla_nelkul_hibaval_all_meg(tmp_path):
    """Ha a jegyzőkönyvben nincs Sebesség tábla, a hozzáfűzés beszélő
    hibával megáll — nem talál ki szerkezetet, és a fájl változatlan."""
    import pytest

    doc = tmp_path / "j.md"
    doc.write_text("# Napló\n\nNincs benne tábla.\n", encoding="utf-8")
    with pytest.raises(SystemExit) as hiba:
        sp.append_jegyzokonyv("| sor |", doc)
    assert "nincs Sebesség tábla" in str(hiba.value)
    assert doc.read_text(encoding="utf-8") == "# Napló\n\nNincs benne tábla.\n"


def _main_kornyezet(monkeypatch, tmp_path):
    """A main a tmp mappába ír (a doksikat nem bántja), kamu méréssel."""
    kert: dict = {}

    def kamu_meres(seconds, seed, fps, shots_per_min, only):
        kert.update(seconds=seconds, seed=seed, fps=fps,
                    shots_per_min=shots_per_min, only=only)
        return _minta_eredmeny()

    jelentes = tmp_path / "SEBESSEG.md"
    naplo = tmp_path / "MERESI_JEGYZOKONYV.md"
    naplo.write_text("# Napló\n\n" + sp.SEBESSEG_FEJLEC
                     + "\n|---|---|---|---|---|---|---|---|\n",
                     encoding="utf-8")
    monkeypatch.setattr(sp, "measure", kamu_meres)
    monkeypatch.setattr(sp, "_OUT", jelentes)
    monkeypatch.setattr(sp, "_verzio", lambda: "v9.9.9+teszt")
    monkeypatch.setattr(sp, "_gep_leiras", lambda: "teszt-gép")
    # Az append_jegyzokonyv alap-útja definíciókor kötődik: a main-ből
    # hívott változatot irányítjuk át.
    eredeti = sp.append_jegyzokonyv
    monkeypatch.setattr(sp, "append_jegyzokonyv",
                        lambda sor: eredeti(sor, naplo))
    return kert, jelentes, naplo


def test_main_megirja_a_jelentest_az_alapertekekkel(monkeypatch, tmp_path,
                                                    capsys):
    """Paraméter nélkül a teljes meccs alapértékeivel mér, a jelentést
    kiírja a kimenetre ÉS a fájlba; a jegyzőkönyvhöz nem nyúl."""
    kert, jelentes, naplo = _main_kornyezet(monkeypatch, tmp_path)
    naplo_elotte = naplo.read_text(encoding="utf-8")

    assert sp.main([]) == 0
    assert kert == {"seconds": sp.DEFAULT_SECONDS, "seed": sp.DEFAULT_SEED,
                    "fps": sp.DEFAULT_FPS,
                    "shots_per_min": sp.DEFAULT_SHOTS_PER_MIN, "only": ()}
    rep = sp.build_report(_minta_eredmeny(), "v9.9.9+teszt", "teszt-gép")
    assert jelentes.read_text(encoding="utf-8") == rep + "\n"
    ki = capsys.readouterr().out
    assert rep in ki and f"Kiírva: {jelentes}" in ki
    assert "Jegyzőkönyv-sor" not in ki
    assert naplo.read_text(encoding="utf-8") == naplo_elotte


def test_main_gyors_kor_es_no_write_nem_irja_a_jelentest(monkeypatch,
                                                         tmp_path, capsys):
    """A részleges mérés (--only) és a --no-write nem írja felül a teljes
    meccs jelentését — csak a kimenetre ír; a paraméterek átmennek."""
    kert, jelentes, _ = _main_kornyezet(monkeypatch, tmp_path)

    assert sp.main(["--only", "xg,defense,", "--seconds", "60",
                    "--seed", "4", "--fps", "25", "--shots-per-min",
                    "2.5"]) == 0
    assert kert == {"seconds": 60.0, "seed": 4, "fps": 25.0,
                    "shots_per_min": 2.5, "only": ("xg", "defense")}
    assert not jelentes.exists()
    assert "Kiírva:" not in capsys.readouterr().out

    assert sp.main(["--no-write"]) == 0
    assert not jelentes.exists()
    ki = capsys.readouterr().out
    assert "# Sebesség-profil" in ki and "Kiírva:" not in ki


def test_main_jegyzokonyv_sort_fuz_a_sebesseg_tablahoz(monkeypatch,
                                                       tmp_path, capsys):
    """A --jegyzokonyv a mérés sorát a Sebesség tábla végére fűzi (a
    verzióval, a géppel és az ítélettel), és ki is írja."""
    _, _, naplo = _main_kornyezet(monkeypatch, tmp_path)

    assert sp.main(["--jegyzokonyv", "--no-write"]) == 0
    sorok = naplo.read_text(encoding="utf-8").split("\n")
    uj = [s for s in sorok if "v9.9.9+teszt" in s]
    assert len(uj) == 1
    assert uj[0].endswith("| 2 perc 5 mp | 20,0 mp | teszt-gép | MEGFELEL |")
    assert sorok.index(uj[0]) == sorok.index(sp.SEBESSEG_FEJLEC) + 2
    assert f"Jegyzőkönyv-sor: {uj[0]}" in capsys.readouterr().out
