"""
Tesztek a meccsenkénti megjelenés-profilra (appearance.py).

A lényeg: a szín-hozzárendelés NINCS bedrótozva — bármilyen meccs-színkészlettel
működik. Ezt két KÜLÖNBÖZŐ meccs profiljával igazoljuk: ugyanaz a logika más
színeknél is helyesen sorol.

Futtatás:
    python tests/test_appearance.py
"""

from __future__ import annotations

# A backend/ mappát a kereső-útvonalra tesszük, hogy a teszt bárhonnan fusson.
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.pipeline.appearance import (
    AppearanceProfile, AppearanceLabel, color_distance, nearest_label,
)


def test_color_distance_basics():
    """A színtávolság 0 azonos színre, és a fekete-fehér a maximum közelében."""
    assert color_distance((10, 20, 30), (10, 20, 30)) == 0.0
    assert abs(color_distance((0, 0, 0), (255, 255, 255)) - 441.67) < 0.1


def test_match_a_white_black_green_yellow():
    """Az 1. meccs (a valódi felvétel): fehér/fekete/zöld/sárga helyesen sorolva."""
    prof = AppearanceProfile(
        home=(240, 240, 240),       # fehér csapat
        away=(20, 20, 20),          # fekete csapat
        goalkeeper=[(30, 160, 60)], # zöld kapus
        referee=[(230, 210, 40)],   # sárga bíró
    )
    assert nearest_label((250, 250, 250), prof) == AppearanceLabel.HOME
    assert nearest_label((10, 10, 15), prof) == AppearanceLabel.AWAY
    assert nearest_label((40, 170, 70), prof) == AppearanceLabel.GOALKEEPER
    assert nearest_label((235, 205, 30), prof) == AppearanceLabel.REFEREE


def test_match_b_completely_different_colors():
    """A 2. meccs MÁS színekkel: ugyanaz a logika, bedrótozás nélkül működik.

    Itt a hazai PIROS, a vendég KÉK, a kapus NARANCS, a bíró FEKETE.
    """
    prof = AppearanceProfile(
        home=(200, 30, 30),         # piros
        away=(30, 60, 200),         # kék
        goalkeeper=[(240, 140, 20)],# narancs
        referee=[(15, 15, 15)],     # fekete
    )
    assert nearest_label((210, 40, 25), prof) == AppearanceLabel.HOME      # piros
    assert nearest_label((25, 70, 210), prof) == AppearanceLabel.AWAY      # kék
    assert nearest_label((235, 150, 30), prof) == AppearanceLabel.GOALKEEPER
    assert nearest_label((20, 20, 25), prof) == AppearanceLabel.REFEREE    # fekete


def test_unknown_color_returns_none():
    """A profil egyik színéhez sem közeli minta None (nem soroljuk be tévesen)."""
    prof = AppearanceProfile(home=(255, 255, 255), away=(0, 0, 0),
                             match_threshold=100.0)
    # Élénk lila: messze a fehértől és a feketétől is → ismeretlen.
    assert nearest_label((150, 0, 150), prof) is None


def test_empty_profile_returns_none():
    """Üres profil (még nincs betanítva) → None minden mintára."""
    prof = AppearanceProfile()
    assert nearest_label((123, 200, 50), prof) is None


def test_two_teams_separated_by_nearest():
    """Két, egymáshoz közelebbi árnyalat is a HELYES csapathoz kerül."""
    prof = AppearanceProfile(home=(200, 0, 0), away=(255, 120, 120))  # sötét vs világos piros
    assert nearest_label((190, 10, 10), prof) == AppearanceLabel.HOME
    assert nearest_label((250, 130, 125), prof) == AppearanceLabel.AWAY


def test_labeled_colors_a_profil_minden_szine_cimkevel():
    """A hozzárendelés nyersanyaga: a profil összes (címke, szín) párja —
    hazai, vendég, aztán MINDEN kapus- és bíró-szín külön párként (a két
    kapus eltérő színű lehet, több bíró is van)."""
    prof = AppearanceProfile(
        home=(240, 240, 240), away=(20, 20, 20),
        goalkeeper=[(30, 160, 60), (240, 140, 20)],
        referee=[(230, 210, 40)],
    )
    assert prof.labeled_colors() == [
        (AppearanceLabel.HOME, (240, 240, 240)),
        (AppearanceLabel.AWAY, (20, 20, 20)),
        (AppearanceLabel.GOALKEEPER, (30, 160, 60)),
        (AppearanceLabel.GOALKEEPER, (240, 140, 20)),
        (AppearanceLabel.REFEREE, (230, 210, 40)),
    ]
    # Mindkét kapus-szín tényleg kapusnak sorol.
    assert nearest_label((35, 150, 65), prof) == AppearanceLabel.GOALKEEPER
    assert nearest_label((235, 150, 30), prof) == AppearanceLabel.GOALKEEPER


def test_labeled_colors_csak_a_megadott_szinek():
    """Ami nincs megadva, az nem kerül a párok közé (nem None-színnel,
    nem alapértelmezett színnel): üres profil → üres lista; a fekete
    (0, 0, 0) viszont VALÓDI szín, nem "hiányzó"."""
    assert AppearanceProfile().labeled_colors() == []
    csak_vendeg = AppearanceProfile(away=(30, 60, 200))
    assert csak_vendeg.labeled_colors() == [
        (AppearanceLabel.AWAY, (30, 60, 200))]
    csak_biro = AppearanceProfile(referee=[(15, 15, 15), (230, 210, 40)])
    assert [c for c, _ in csak_biro.labeled_colors()] == [
        AppearanceLabel.REFEREE, AppearanceLabel.REFEREE]
    fekete = AppearanceProfile(home=(0, 0, 0))
    assert fekete.labeled_colors() == [(AppearanceLabel.HOME, (0, 0, 0))]
    assert nearest_label((5, 5, 5), fekete) == AppearanceLabel.HOME


def test_labeled_colors_friss_lista_a_profil_nem_modosul():
    """Minden hívás saját listát ad: a hívó módosítása nem ír vissza a
    profilba, és két profil kapus-listája nem közös (nincs megosztott
    alapérték)."""
    prof = AppearanceProfile(home=(200, 30, 30), goalkeeper=[(240, 140, 20)])
    parok = prof.labeled_colors()
    parok.append((AppearanceLabel.REFEREE, (1, 2, 3)))
    assert len(prof.labeled_colors()) == 2
    assert prof.referee == []
    masik = AppearanceProfile()
    masik.goalkeeper.append((1, 1, 1))
    assert AppearanceProfile().goalkeeper == []


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    print(f"\n{'OK' if failures == 0 else failures} hibás teszt")
    raise SystemExit(1 if failures else 0)
