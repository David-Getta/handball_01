"""A teendő-rangsor (priorities.priority_findings) tesztjei."""
from __future__ import annotations

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.models.tracking import (Ball, Frame, Match, MatchMeta,
                                      PlayerPosition, Team)
from handball.pipeline.priorities import PRF_TOP_N, priority_findings


def _meta():
    return MatchMeta(match_id="prf", home_team="H", away_team="A", fps=25.0)


def _two_family_match():
    """Olyan meccs, ami EGYSZERRE vált ki egy ár- és egy állás-jelzést.

    Három 36 mp-es hazai támadás gól nélkül → "elhúzódó támadás ára"
    (ár-család); ugyanezek alatt a hazai kapus 25 m-re a saját
    kapujától → három üres-kapus szakasz döntetlennél → "7a6-állás"
    (állás-család). A szakaszok közti 3 mp-es szabad labda szétvágja
    mindkét szakasz-sorozatot.
    """
    frames = []
    t = 0
    for _ in range(3):
        for _ in range(int(36 * 25)):
            frames.append(Frame(t=t, players=[
                PlayerPosition(track_id=1, team=Team.HOME, x=30.0, y=10.0),
                PlayerPosition(track_id=2, team=Team.HOME, x=25.0, y=10.0,
                               role="kapus"),
            ], ball=Ball(x=30.0, y=10.0, confidence=1.0)))
            t += 1
        for _ in range(int(3 * 25)):
            frames.append(Frame(t=t, players=[],
                                ball=Ball(x=20.0, y=10.0, confidence=1.0)))
            t += 1
    return Match(_meta(), frames)


def test_priority_findings_ranks_cost_before_score_state():
    """Az ár-család jelzése a rangsor élére kerül az állás-család elé."""
    prf = priority_findings(_two_family_match())
    h = prf["home"]
    assert h["total"] >= 2, h
    families = [it["family"] for it in h["top"]]
    assert families[0] == "ár", h["top"]
    assert "állás" in families, h["top"]
    # Az ár-jelzés megelőzi az állás-jelzést a listában.
    assert families.index("ár") < families.index("állás")
    labels = [it["label"] for it in h["top"]]
    assert "Elhúzódó támadás ára" in labels
    assert "7a6-állás" in labels
    assert h["families"].get("ár", 0) >= 1
    assert h["families"].get("állás", 0) >= 1
    assert len(h["top"]) <= PRF_TOP_N


def test_priority_findings_silent_without_evidence():
    """Üres meccsen egyetlen réteg sem szólal meg — nem találgatunk."""
    frames = [Frame(t=i, players=[],
                    ball=Ball(x=20.0, y=10.0, confidence=1.0))
              for i in range(200)]
    prf = priority_findings(Match(_meta(), frames))
    for side in ("home", "away"):
        assert prf[side]["top"] == []
        assert prf[side]["total"] == 0
        assert prf[side]["families"] == {}


def test_felkeszules_csalad_a_sor_vegen_all():
    """A poszt-profil jelzések a rangsor VÉGÉRE kerülnek.

    A poszt-profil nem hiba és nem romlás, hanem állandó tulajdonság
    ("a beállójuk hat méterről fejez be") — sürgősség nélkül. Ezért nem
    tolhatja el az árat, az embert vagy a fáradást; viszont ha azok
    hallgatnak (rövid felvétel, kevés esemény), legalább a lista nem
    marad üresen.
    """
    from handball.pipeline.priorities import (PRF_FAMILY_ORDER, _registry)

    assert PRF_FAMILY_ORDER[-1] == "felkészülés", PRF_FAMILY_ORDER
    fams = {f for f, _, _, _ in _registry()}
    assert "felkészülés" in fams, fams
    # Minden nyilvántartott család szerepel a sorrendben — különben a
    # rendezés némán a lista elejére dobná.
    assert fams <= set(PRF_FAMILY_ORDER), fams - set(PRF_FAMILY_ORDER)


def test_a_poszt_lencse_eljut_a_rangsorba():
    """A poszt-lencse lövés-rétegei rangsorba vont rétegek.

    Enélkül az ítéletük ("őt ki kell zárni", "a kapus arra állhat rá")
    csak böngészéssel lenne megtalálható a háromszáz réteg közt.
    """
    from handball.pipeline.priorities import _registry

    names = {fn for _, _, _, fn in _registry()}
    for layer in ("role_shot_distance", "role_shot_power",
                  "role_shot_timing", "role_goal_placement",
                  # A befejező-lencse: kire lépj ki, melyik figurájuk
                  # kire fut ki, és időkérés után kit fogj.
                  "role_pressure_finish", "setplay_finishers",
                  "timeout_finisher", "role_fast_breaks",
                  "role_assist_sources"):
        assert layer in names, f"{layer} nincs a rangsorban"
