"""
Tesztek a mezszám-OCR prototípusra (jersey_ocr.py) — szintetikus mezekkel.

Futtatás:
    python -m pytest tests/test_jersey_ocr.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2
import numpy as np

from handball.pipeline.jersey_ocr import JerseyVoter, read_jersey_number


def _jersey_crop(number: int, light_on_dark: bool = True, size=(120, 120)):
    """Szintetikus mez-kivágás: egyszínű "mez" + nagy szám a közepén."""
    bg = 40 if light_on_dark else 215
    fg = 235 if light_on_dark else 30
    img = np.full((size[1], size[0], 3), bg, np.uint8)
    text = str(number)
    scale = 2.2 if len(text) == 1 else 1.8
    tw = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 4)[0]
    org = ((size[0] - tw[0]) // 2, (size[1] + tw[1]) // 2)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale,
                (fg, fg, fg), 4)
    return img


def test_reads_single_and_double_digits():
    for number in (7, 23, 5, 41):
        r = read_jersey_number(_jersey_crop(number))
        assert r is not None, f"nem olvasta le: {number}"
        assert r[0] == number, f"várt {number}, lett {r[0]} (conf {r[1]:.2f})"


def test_reads_dark_number_on_light_jersey():
    r = read_jersey_number(_jersey_crop(18, light_on_dark=False))
    assert r is not None and r[0] == 18


def test_rejects_blank_and_tiny_crops():
    blank = np.full((120, 120, 3), 60, np.uint8)
    assert read_jersey_number(blank) is None
    tiny = np.full((10, 10, 3), 60, np.uint8)
    assert read_jersey_number(tiny) is None
    assert read_jersey_number(None) is None


def test_voter_needs_votes_and_margin():
    v = JerseyVoter(min_votes=3.0, min_margin=2.0)
    v.add(1, 23)
    v.add(1, 23)
    assert v.decide(1) is None  # kevés szavazat
    v.add(1, 23)
    assert v.decide(1) == 23
    # Zajos, megosztott track: nincs elég előny → nincs döntés.
    v.add(2, 7)
    v.add(2, 7)
    v.add(2, 7)
    v.add(2, 1)
    v.add(2, 1)
    assert v.decide(2) is None
    # További 7-esek: az előny meglesz.
    v.add(2, 7)
    v.add(2, 7)
    v.add(2, 7)
    assert v.decide(2) == 7


def test_voter_decisions_format_matches_jerseys_store():
    v = JerseyVoter(min_votes=1.0, min_margin=1.0)
    v.add(4, 11)
    v.add(9, 32)
    v.add(5, 150)  # érvénytelen szám — eldobjuk
    d = v.decisions()
    assert d == {4: 11, 9: 32}


def test_end_to_end_ocr_plus_voter():
    """A felismerő + szavazó együtt: több zajos kivágásból stabil döntés."""
    v = JerseyVoter(min_votes=2.0, min_margin=1.5)
    rng = np.random.default_rng(3)
    for _ in range(6):
        crop = _jersey_crop(9)
        noise = rng.integers(0, 18, crop.shape, dtype=np.uint8)
        r = read_jersey_number(cv2.add(crop, noise))
        if r is not None:
            v.add(1, r[0], r[1])
    assert v.decide(1) == 9




def _letter_crop(ch: str, size=(120, 120)):
    """Szintetikus mez-kivágás BETŰVEL (pl. a név egy betűje) — nem mezszám."""
    img = np.full((size[1], size[0], 3), 40, np.uint8)
    tw = cv2.getTextSize(ch, cv2.FONT_HERSHEY_SIMPLEX, 2.2, 4)[0]
    org = ((size[0] - tw[0]) // 2, (size[1] + tw[1]) // 2)
    cv2.putText(img, ch, org, cv2.FONT_HERSHEY_SIMPLEX, 2.2,
                (235, 235, 235), 4)
    return img


def test_rejects_letters_via_reject_class():
    """A 11 osztályos háló a betűket elutasítja — nem lesz belőlük hamis
    mezszám (a hamis szám rosszabb, mint a hiányzó)."""
    rejected = 0
    for ch in "AEFKMRTX":
        if read_jersey_number(_letter_crop(ch)) is None:
            rejected += 1
    # Nem minden betű "számjegy-szerű" a kontúr-szűrőnek sem; a lényeg,
    # hogy a többségük ne kapjon számot.
    assert rejected >= 6, f"csak {rejected}/8 betű lett elutasítva"


def test_digits_still_read_with_reject_class():
    """Az elutasító osztály NEM ronthatja el a valódi számok leolvasását."""
    for number in (2, 9, 13, 77):
        r = read_jersey_number(_jersey_crop(number))
        assert r is not None and r[0] == number



if __name__ == "__main__":
    test_reads_single_and_double_digits()
    test_reads_dark_number_on_light_jersey()
    test_rejects_blank_and_tiny_crops()
    test_voter_needs_votes_and_margin()
    test_voter_decisions_format_matches_jerseys_store()
    test_end_to_end_ocr_plus_voter()
    print("Minden mezszám-OCR teszt OK.")


def test_torso_crop_geometry():
    from handball.pipeline.jersey_ocr import torso_crop
    img = np.zeros((400, 400, 3), np.uint8)
    crop = torso_crop(img, (100, 100, 180, 300))  # 80 széles, 200 magas doboz
    assert crop is not None
    # A törzs-sáv: y 124..200 (0.12h..0.5h), x 112..168 (15% margó).
    assert crop.shape[0] == 76 and crop.shape[1] == 56
    # Kicsi doboz: nem olvasható → None.
    assert torso_crop(img, (0, 0, 20, 50)) is None
    # Kép szélére lógó doboz: levágva, de nem hibázik.
    assert torso_crop(img, (350, 300, 480, 600)) is not None


def test_apply_decisions_respects_manual_assignments():
    from handball.models.tracking import (
        Frame, Match, MatchMeta, PlayerPosition, Team,
    )
    from handball.pipeline.jersey_ocr import apply_jersey_decisions
    frames = [Frame(t=0, players=[
        PlayerPosition(track_id=1, team=Team.HOME, x=1.0, y=1.0),
        PlayerPosition(track_id=2, team=Team.HOME, x=2.0, y=2.0,
                       jersey_number=99),  # kézi szám — az OCR nem írja felül
    ])]
    m = Match(meta=MatchMeta(match_id="t", home_team="H", away_team="A",
                             fps=25.0), frames=frames)
    n = apply_jersey_decisions(m, {1: 23, 2: 11, 5: 4})
    assert n == 1
    assert frames[0].players[0].jersey_number == 23
    assert frames[0].players[1].jersey_number == 99  # a kézi maradt


def test_digit_net_ships_and_classifies():
    """A tanított számjegy-háló a csomag része, betölthető, és a
    renderelt jegyeket magas találati aránnyal osztályozza — beleértve
    olyan torzításokat is (elforgatás), amiken a sablon-illesztés elvérzik."""
    from handball.pipeline.jersey_ocr import _classify_digit, _load_digit_net
    net = _load_digit_net()
    assert net is not None, "digit_net.npz hiányzik a csomagból"

    rng = np.random.default_rng(5)
    ok = 0
    total = 0
    for d in range(10):
        for _ in range(20):
            # Renderelés a felismerő normalizálásával (szoros vágás + 28x28),
            # elforgatással és zajjal.
            img = np.zeros((72, 72), np.uint8)
            cv2.putText(img, str(d), (14, 58), cv2.FONT_HERSHEY_SIMPLEX,
                        float(rng.uniform(1.5, 2.2)), 255,
                        int(rng.integers(2, 5)))
            M = cv2.getRotationMatrix2D((36, 36), float(rng.uniform(-10, 10)), 1.0)
            img = cv2.warpAffine(img, M, (72, 72))
            ys, xs = np.nonzero(img)
            roi = img[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
            roi = cv2.resize(roi, (28, 28), interpolation=cv2.INTER_AREA)
            pred, conf = _classify_digit(roi, net)
            total += 1
            if pred == d:
                ok += 1
    assert ok / total >= 0.95, f"pontosság: {ok}/{total}"


def test_reader_still_works_with_net():
    """A teljes felismerő (kivágás→binarizálás→háló) továbbra is olvas —
    és most már döntött (forgatott) számot is."""
    crop = _jersey_crop(23)
    # Enyhe forgatás az egész kivágáson.
    M = cv2.getRotationMatrix2D((60, 60), 8.0, 1.0)
    rotated = cv2.warpAffine(crop, M, (120, 120),
                             borderValue=(40, 40, 40))
    r = read_jersey_number(rotated)
    assert r is not None and r[0] == 23, f"lett: {r}"
