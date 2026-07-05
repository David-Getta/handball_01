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
