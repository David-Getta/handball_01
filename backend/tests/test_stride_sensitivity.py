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


# ---- A mérés, a jelentés és a main (eddig egyszer sem futottak) --------------

def test_measure_megnevezi_a_ritkitasra_valto_reteget(monkeypatch):
    """Kicsiben, három próba-réteggel: a kockaszám-küszöbű réteg (sűrűn
    ítél, ritkítva hallgat) az eltérők közé kerül az útvonallal és a két
    értékkel; a ritkítástól független réteg nem; a hibára futó réteg a
    "failed" listára, ítélet nélkül."""
    from handball.pipeline import xg
    from scripts import order_sensitivity
    from scripts.stride_sensitivity import measure

    lattak = []

    def kocka_kuszobu(match):
        # 100 mért kocka kell az ítélethez — ritkítva (50) már nincs meg.
        lattak.append((len(match.frames), round(match.meta.fps, 2)))
        return {"home": {"verdict": "gyors" if len(match.frames) >= 100
                         else None, "frames": len(match.frames)},
                "away": {"verdict": None}}

    def stabil(match):
        return {"home": {"verdict": "zárt fal", "shots": len(match.frames)}}

    def bukik(match):
        raise RuntimeError("nem mérhető")

    monkeypatch.setattr(xg, "_proba_kocka", kocka_kuszobu, raising=False)
    monkeypatch.setattr(xg, "_proba_stabil", stabil, raising=False)
    monkeypatch.setattr(xg, "_proba_bukik", bukik, raising=False)
    monkeypatch.setattr(order_sensitivity, "_layer_functions", lambda: [
        ("kocka-küszöbű", "xg", "_proba_kocka"),
        ("stabil", "xg", "_proba_stabil"),
        ("bukó", "xg", "_proba_bukik"),
        ("hiányzó", "xg", "_nincs_ilyen_fuggveny")])

    res = measure(seconds=6.0, seed=7, stride=3)
    assert res["checked"] == 2
    assert sorted(res["failed"]) == ["bukó", "hiányzó"]
    assert res["differs"] == [{"layer": "kocka-küszöbű", "changes": [
        {"path": "home.verdict", "dense": "gyors", "strided": None}]}]
    # A réteg a sűrű ÉS a ritkított meccset is megkapta: harmad annyi
    # kocka, harmad fps (a termék modellje).
    assert lattak == [(150, 25.0), (50, 8.33)]


def test_measure_azonos_iteletnel_ures_lista(monkeypatch):
    """Ha minden réteg ugyanazt ítéli sűrűn és ritkítva (a nyers számok
    eltérhetnek), nincs eltérő réteg; réteg nélkül nincs mit mérni."""
    from handball.pipeline import xg
    from scripts import order_sensitivity
    from scripts.stride_sensitivity import measure

    monkeypatch.setattr(
        xg, "_proba_stabil",
        lambda match: {"home": {"verdict": "zárt fal",
                                "frames": len(match.frames)}},
        raising=False)
    monkeypatch.setattr(order_sensitivity, "_layer_functions",
                        lambda: [("stabil", "xg", "_proba_stabil")])
    assert measure(seconds=6.0) == {"checked": 1, "differs": [],
                                    "failed": []}
    monkeypatch.setattr(order_sensitivity, "_layer_functions", lambda: [])
    assert measure(seconds=6.0) == {"checked": 0, "differs": [],
                                    "failed": []}


def test_build_report_felsorolja_az_elteroket_es_a_nem_merhetoket():
    """A jelentés a mérés fejlécével (hossz, mag, ritkítás, réteg-számok),
    rétegenként legfeljebb hat eltéréssel ("… és még N"), és a hibára
    futott rétegek névsorával készül."""
    from scripts.stride_sensitivity import build_report

    valtozasok = [{"path": f"home.verdict[{i}]", "dense": "a", "strided": None}
                  for i in range(8)]
    res = {"checked": 12, "failed": ["zeta", "alfa"],
           "differs": [{"layer": "press_height", "changes": valtozasok},
                       {"layer": "wall_gaps", "changes": [
                           {"path": "away.verdict", "dense": "réses",
                            "strided": None}]}]}
    s = build_report(res, seconds=240.0, seed=7, stride=3)
    assert s.startswith("# Stride-érzékenység")
    assert "240 mp-es szimulált meccs (mag: 7), sűrű (25 fps) vs 3-as " \
           "ritkítás; **12 réteg** összevetve, ebből **2 eltérő ítéletű**" in s
    assert "### `press_height`" in s and "### `wall_gaps`" in s
    assert s.count("- `home.verdict[") == 6
    assert "- … és még 2 eltérés" in s
    assert "- `away.verdict`: sűrűn `réses` → ritkítva `None`" in s
    assert s.index("- `alfa`") < s.index("- `zeta`")       # névsorban
    assert "Eltérő ítéletű réteg: nincs" not in s
    assert s.endswith("\n")


def test_build_report_elteres_nelkul_kimondja():
    """Eltérés és hiba nélkül a jelentés kimondja, hogy nincs eltérő
    réteg, és nincs "nem mérhető" szakasz."""
    from scripts.stride_sensitivity import build_report

    s = build_report({"checked": 5, "differs": [], "failed": []},
                     seconds=60.0, seed=1, stride=2)
    assert "## Eltérő ítéletű réteg: nincs" in s
    assert "**5 réteg** összevetve, ebből **0 eltérő ítéletű**" in s
    assert "vs 2-as ritkítás" in s
    assert "Nem mérhető" not in s and "###" not in s


def test_main_megirja_a_jelentest_a_parameterekkel(monkeypatch, tmp_path,
                                                   capsys):
    """A main a parancssori paraméterekkel mér, a jelentést a (itt a tmp
    mappába irányított) fájlba írja, és a kimenetre összegez."""
    from scripts import stride_sensitivity as ss

    kert: dict = {}

    def kamu_meres(seconds, seed, stride):
        kert.update(seconds=seconds, seed=seed, stride=stride)
        return {"checked": 3, "failed": [],
                "differs": [{"layer": "press_height", "changes": [
                    {"path": "home.verdict", "dense": "magas",
                     "strided": None}]}]}

    ki_fajl = tmp_path / "almappa" / "STRIDE.md"
    monkeypatch.setattr(ss, "measure", kamu_meres)
    monkeypatch.setattr(ss, "_OUT", ki_fajl)
    assert ss.main(["--seconds", "30", "--seed", "4", "--stride", "2"]) == 0
    assert kert == {"seconds": 30.0, "seed": 4, "stride": 2}
    szoveg = ki_fajl.read_text(encoding="utf-8")
    assert szoveg == ss.build_report(kamu_meres(30.0, 4, 2), 30.0, 4, 2)
    ki = capsys.readouterr().out
    assert f"Stride-jelentés kiírva: {ki_fajl}" in ki
    assert "összevetve: 3 réteg" in ki and "eltérő ítéletű: 1" in ki
    assert "- press_height (1 eltérés)" in ki

    # Paraméter nélkül a termék alapértékeivel (240 mp, 7-es mag, stride 3).
    assert ss.main([]) == 0
    assert kert == {"seconds": ss.DEFAULT_SECONDS, "seed": ss.DEFAULT_SEED,
                    "stride": ss.DEFAULT_STRIDE}
    assert ss.DEFAULT_STRIDE == 3
    capsys.readouterr()
