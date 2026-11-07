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
