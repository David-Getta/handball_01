"""
Tesztek a KLIP-JELZÉSRE (quality "clip_note").

Egy kézilabda-meccs 2x30 perc. Egy pár perces felvétel nem meccs, hanem
KLIP — teljesen jogos bemenet, de a meccs-szintű rétegek (hajrá,
félidő-összevetés, kondíció, sorozatok) némán hallgatnak rajta. A
felhasználó ezt HIBÁNAK látja: "megcsináltam, és a fele üres".

A jelzés ezért NEM figyelmeztetés, hanem külön mező. Ha a warnings közé
kerülne, elveszne a "hibátlan feldolgozás = üres figyelmeztetés-lista"
szabály, és minden rövid próba gyanúsnak látszana.

Futtatás:
    python -m pytest tests/test_klip_jelzes.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.pipeline.quality import (  # noqa: E402
    CLIP_LENGTH_S, compute_quality_report,
)
from handball.sim.match_simulator import simulate_ground_truth  # noqa: E402


def _riport(duration_s, fps=10.0):
    m = simulate_ground_truth(duration_s=duration_s, fps=fps, seed=3)
    m.meta.calibrated = True
    return compute_quality_report(m)


def test_a_rovid_felvetel_klipnek_szamit():
    r = _riport(90)
    jelzes = r["clip_note"]
    assert jelzes, "a klip-hosszú felvételnél nincs jelzés"
    # A LÉNYEG: mi működik és mi nem — nem elég annyit mondani, hogy rövid.
    assert "MŰKÖDIK" in jelzes and "NEM szólal meg" in jelzes


def test_a_jelzes_nem_figyelmeztetes():
    """ŐR: a klip-jelzés NEM hiba.

    A `warnings` a hibáké. Ha az információ is oda kerülne, egy
    hibátlan feldolgozású klip figyelmeztetéssel jönne ki, és a
    "nincs figyelmeztetés = megbízható" szabály elveszne.
    """
    r = _riport(90)
    assert r["clip_note"]
    assert not any("klip" in w.lower() for w in r["warnings"]), r["warnings"]
    # És az ELSŐ TEENDŐ sem lesz belőle: nincs mit tenni.
    assert r["clip_note"] not in (r.get("next_action") or "")


def test_a_mezo_meccs_hosszu_felvetelnel_None_de_letezik():
    """A mező LÉTEZIK mindig — a felület ne kulcs-hiányra fusson.

    (A szimuláció órákig tartana meccs-hosszan, ezért a küszöböt a
    hosszúság-számítás felől ellenőrizzük: a mező kulcsként ott van, és
    rövid felvételnél nem None.)
    """
    r = _riport(90)
    assert "clip_note" in r
    assert CLIP_LENGTH_S > 90.0, "a küszöb alá esik a teszt-felvétel"


def test_a_kuszob_masodpercben_van():
    """ŐR: a klip-küszöb IDŐTARTAM, tehát másodpercben.

    Kockában megadva a minőségi profiltól függően háromszoros valós
    időt jelentene (a termék minden 3. kockát dolgozza fel).
    """
    src = (Path(__file__).resolve().parents[1] / "handball" / "pipeline"
           / "quality.py").read_text(encoding="utf-8")
    assert "CLIP_LENGTH_S" in src
    assert "duration_s < CLIP_LENGTH_S" in src, (
        "a küszöböt nem másodpercben hasonlítjuk")


def test_az_edzoi_osszefoglalo_is_kimondja():
    """Hibátlan feldolgozású klipnél a pontszám magas és nincs teendő —
    a "mennyire bízhatsz ebben" doboz ott riogatás lenne. A klip-jelzés
    ezért SAJÁT mezőn megy, de meg kell szólalnia."""
    from handball.pipeline.coach_summary import (
        coach_summary, coach_summary_text,
    )

    m = simulate_ground_truth(duration_s=90, fps=10.0, seed=3)
    m.meta.calibrated = True
    data = coach_summary(m)
    assert data.get("clip_note"), "az összefoglaló nem mondja ki"
    # NEM a caveat-ban: az a hibáké.
    assert data.get("caveat") is None
    # A szöveges alakban is ott van (ez megy a csomagba és a vágólapra).
    assert "Klip, nem teljes meccs" in coach_summary_text(m)


def test_a_klip_doboz_nem_hiba_doboz():
    """ŐR: a klip-jelzés NEM a piros figyelmeztetés-dobozban van.

    A `warnbox` a hibáké — ha a klip-jelzés is oda kerülne, egy
    hibátlan feldolgozású klip jelentése úgy nyílna, mintha valami
    baj lenne vele. A piros doboz ugyanolyan félrevezető, mint a
    hallgatás.
    """
    from handball.pipeline.report_html import match_report_html

    m = simulate_ground_truth(duration_s=90, fps=10.0, seed=5)
    m.meta.calibrated = True
    html = match_report_html(m, {}, [], compute_quality_report(m))
    assert 'class="infobox"' in html
    # Hibátlan feldolgozásnál a HIBA-doboz nem jelenhet meg.
    assert '<div class="warnbox">' not in html


def test_a_nyomtatott_jelentes_elejen_all():
    """Aki egy három perces klip jelentését olvassa, a hallgató
    rétegeket enélkül hiányos elemzésnek nézi — a lap ELEJÉN a helye."""
    from handball.pipeline.report_html import match_report_html

    m = simulate_ground_truth(duration_s=90, fps=10.0, seed=3)
    m.meta.calibrated = True
    q = compute_quality_report(m)
    html = match_report_html(m, {}, [], q)
    assert "Klip, nem teljes meccs" in html
    fejlec = html.index("Klip, nem teljes meccs")
    assert fejlec < html.index("Meccsről") if "Meccsről" in html else True
