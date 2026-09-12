"""
A stride-érzékenység őr (scripts.stride_sensitivity) tesztjei.

A teljes söprés (486 réteg, két futás) perc-nagyságrendű, ezért az a
jelentés-szkript dolga — mint a sorrend-függésnél és a tükrözésnél. Itt
a mechanikát rögzítjük: a ritkítás a termék modelljét követi (t
újraszámozva, fps = fps/stride, az időzítés így pontos marad), és az
ítélet-kigyűjtő csak az ítéletet nézi, a nyers számokat nem.

Futtatás:
    python -m pytest tests/test_stride_sensitivity.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.stride_sensitivity import downsample, judgements

from handball.models.tracking import Ball, Frame, Match, MatchMeta


def _match(n=30, fps=25.0):
    frames = [Frame(t=t, players=[], ball=Ball(x=float(t), y=10.0,
                                               confidence=1.0))
              for t in range(n)]
    return Match(MatchMeta(match_id="st", home_team="H", away_team="A",
                           fps=fps), frames)


def test_downsample_follows_the_product_model():
    """Minden 3. kocka marad, a t újraszámozva, az fps harmadolva — az
    időzítés (t/fps) így ugyanazt a valós időt adja."""
    m = downsample(_match(30), 3)
    assert len(m.frames) == 10
    assert [f.t for f in m.frames] == list(range(10))
    # A megtartott kockák az eredeti 0., 3., 6., ... kockák.
    assert [f.ball.x for f in m.frames][:4] == [0.0, 3.0, 6.0, 9.0]
    assert abs(m.meta.fps - 25.0 / 3) < 1e-9
    # Az utolsó kocka valós ideje változatlan: 27/25 s ≈ 9/(25/3) s.
    assert abs(m.frames[-1].t / m.meta.fps - 27 / 25.0) < 1e-6


def test_downsample_leaves_the_original_untouched():
    m = _match(30)
    downsample(m, 3)
    assert len(m.frames) == 30 and m.meta.fps == 25.0


def test_judgements_sees_verdicts_not_raw_counts():
    """Az ítélet-kigyűjtő a verdict/top/style mezőket látja (a dict-
    értékű ítéletet az azonosítójára egyszerűsítve), a nyers számokat
    (frames, shots) nem — azok ritkítva jogosan térnek el."""
    rec = {
        "home": {"frames": 250, "verdict": "rés-veszélyes fal",
                 "top": {"player_id": 7, "shots": 12},
                 "style": None},
        "away": {"frames": 83, "verdict": None},
    }
    j = judgements(rec)
    assert j["home.verdict"] == "rés-veszélyes fal"
    assert j["home.top"] == 7          # az azonosító, nem a nyers számok
    assert j["home.style"] is None
    assert j["away.verdict"] is None
    assert not any("frames" in k or "shots" in k for k in j)
