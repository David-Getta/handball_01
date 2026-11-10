"""
Tesztek a hash-függés jelentés szkriptjére (scripts/hash_sensitivity.py).

A szkript percekig fut (minden réteg, három külön folyamatban), ezért a
csomagban eddig egyszer sem futott. Itt kicsiben: a munkás-folyamat
lépése próba-rétegekkel, az összevetés logikája előre megírt
folyamat-kimenetekkel, egy VALÓDI háromfolyamatos mérés egyetlen
rétegre, a jelentés és a main három módja. (A felderítés és a meccsterv
gyors hash-őre a tests/test_hash_determinism.py.)

Futtatás:
    python -m pytest tests/test_hash_sensitivity.py -q
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from scripts import hash_sensitivity as hs  # noqa: E402


# ---- A munkás-folyamat lépése --------------------------------------------------

def _proba_retegek(monkeypatch):
    from handball.pipeline import xg
    from scripts import order_sensitivity

    def bukik(match):
        raise RuntimeError("nem megy")

    monkeypatch.setattr(xg, "_proba_a",
                        lambda match: {"home": {"kockak": len(match.frames)}},
                        raising=False)
    monkeypatch.setattr(xg, "_proba_b",
                        lambda match: {"home": {"verdict": "zárt fal"}},
                        raising=False)
    monkeypatch.setattr(xg, "_proba_bukik", bukik, raising=False)
    monkeypatch.setattr(order_sensitivity, "_layer_functions", lambda: [
        ("a", "xg", "_proba_a"), ("b", "xg", "_proba_b"),
        ("bukó", "xg", "_proba_bukik"),
        ("hiányzó", "xg", "_nincs_ilyen_fuggveny")])


def test_worker_retegenkent_lenyomatot_ir(tmp_path, monkeypatch):
    """A munkás minden réteg kimenetének lenyomatát (a kulcs-rendezett
    JSON sha1-ét) írja a fájlba; a hibára futó és a hiányzó réteg helyén
    "HIBA" áll — a többi mérését nem akasztja meg."""
    from scripts.order_sensitivity import _dump

    _proba_retegek(monkeypatch)
    ki = tmp_path / "h1.json"
    hs._worker(str(ki), seconds=4.0, seed=3, shots_per_min=8.0)
    eredmeny = json.loads(ki.read_text(encoding="utf-8"))
    assert set(eredmeny) == {"a", "b", "bukó", "hiányzó"}
    assert eredmeny["bukó"] == "HIBA" and eredmeny["hiányzó"] == "HIBA"
    assert eredmeny["b"] == hashlib.sha1(
        _dump({"home": {"verdict": "zárt fal"}}).encode("utf-8")).hexdigest()
    assert eredmeny["a"] == hashlib.sha1(
        _dump({"home": {"kockak": 100}}).encode("utf-8")).hexdigest()
    # Ugyanaz a bemenet ugyanazt a lenyomatot adja (ezen áll az összevetés).
    ki2 = tmp_path / "h2.json"
    hs._worker(str(ki2), seconds=4.0, seed=3, shots_per_min=8.0)
    assert json.loads(ki2.read_text(encoding="utf-8")) == eredmeny


def test_worker_only_csak_a_kert_retegeket_meri(tmp_path, monkeypatch):
    """Az `only` (vesszővel elválasztott nevek) a gyors újramérés: csak a
    kért rétegek kerülnek a kimenetbe; üres szűrővel mind; ismeretlen
    névre üres eredmény (nem hiba)."""
    _proba_retegek(monkeypatch)
    ki = tmp_path / "h.json"
    hs._worker(str(ki), 4.0, 3, 8.0, only="b,bukó,")
    assert set(json.loads(ki.read_text(encoding="utf-8"))) == {"b", "bukó"}
    hs._worker(str(ki), 4.0, 3, 8.0, only="nincs_ilyen_reteg")
    assert json.loads(ki.read_text(encoding="utf-8")) == {}


# ---- Az összevetés (előre megírt folyamat-kimenetekkel) -----------------------------

class _KamuFolyamat:
    def __init__(self, kod=0):
        self._kod = kod

    def wait(self):
        return self._kod


def _kamu_popen(monkeypatch, kimenetek, kod=0):
    """A három mérő-folyamat helyett: a hash-mag szerinti előre megírt
    kimenetet írja a kért fájlba, és feljegyzi, mivel hívták."""
    hivasok = []

    def popen(parancs, cwd, env):
        ki = parancs[parancs.index("--worker") + 1]
        mag = env["PYTHONHASHSEED"]
        hivasok.append({"parancs": parancs, "cwd": cwd, "mag": mag})
        with open(ki, "w", encoding="utf-8") as f:
            json.dump(kimenetek[mag], f)
        return _KamuFolyamat(kod)

    monkeypatch.setattr(hs.subprocess, "Popen", popen)
    return hivasok


def test_measure_megnevezi_a_hash_fuggo_es_a_nem_merheto_reteget(
        monkeypatch):
    """Ha egy réteg lenyomata a három folyamat közül akár egyben eltér,
    hash-függő; ha bármelyikben hibára futott vagy hiányzik, nem mérhető
    (róla nincs ítélet); az egyező réteg rendben van."""
    hivasok = _kamu_popen(monkeypatch, {
        "1": {"stabil": "aaa", "kevert": "xxx", "bukó": "ccc", "csonka": "d"},
        "4": {"stabil": "aaa", "kevert": "xxx", "bukó": "HIBA", "csonka": "d"},
        "7": {"stabil": "aaa", "kevert": "yyy", "bukó": "ccc"},
    })
    res = hs.measure(seconds=30.0, seed=5, shots_per_min=2.0)
    assert res == {"checked": 2, "sensitive": ["kevert"],
                   "failed": ["bukó", "csonka"]}

    # Három folyamat, három különböző hash-maggal, a backend mappából,
    # a mérés paramétereivel.
    assert [h["mag"] for h in hivasok] == list(hs.HASH_SEEDS) == ["1", "4", "7"]
    for h in hivasok:
        p = h["parancs"]
        assert p[:3] == [sys.executable, "-m", "scripts.hash_sensitivity"]
        assert p[p.index("--seconds") + 1] == "30.0"
        assert p[p.index("--seed") + 1] == "5"
        assert p[p.index("--shots") + 1] == "2.0"
        assert os.path.isdir(os.path.join(h["cwd"], "scripts"))


def test_measure_egyezo_folyamatoknal_ures_lista(monkeypatch):
    """Ha mindhárom folyamat ugyanazt adja, nincs hash-függő réteg (ezt
    az állapotot őrzi a jelentés); réteg nélkül nulla az összevetett."""
    egy = {"a": "111", "b": "222"}
    _kamu_popen(monkeypatch, {"1": egy, "4": egy, "7": egy})
    assert hs.measure(seconds=30.0) == {"checked": 2, "sensitive": [],
                                        "failed": []}
    _kamu_popen(monkeypatch, {"1": {}, "4": {}, "7": {}})
    assert hs.measure(seconds=30.0) == {"checked": 0, "sensitive": [],
                                        "failed": []}


def test_measure_elhalo_folyamatnal_hibaval_all_meg(monkeypatch):
    """Ha egy mérő-folyamat hibával áll le, a mérés nem ad (csonka)
    eredményt: beszélő hibával megáll."""
    egy = {"a": "111"}
    _kamu_popen(monkeypatch, {"1": egy, "4": egy, "7": egy}, kod=3)
    with pytest.raises(RuntimeError, match="mérő-folyamat hibával állt le"):
        hs.measure(seconds=30.0)


def test_measure_valodi_folyamatokkal_egy_retegre():
    """VALÓDI háromfolyamatos mérés (három külön hash-keveréssel) egyetlen
    rétegre, rövid meccsen: az xG réteg kimenete mindhárom indításkor
    ugyanaz."""
    res = hs.measure(seconds=10.0, seed=3, only="xg")
    assert res == {"checked": 1, "sensitive": [], "failed": []}


# ---- A jelentés és a main -------------------------------------------------------------

def test_build_report_felsorolja_a_javitando_retegeket():
    """A jelentés a mérést (hossz, mag, hash-magok, darabszámok) írja le;
    a hash-függő rétegek "JAVÍTANDÓ" szakaszban, a nem mérhetők külön."""
    s = hs.build_report({"checked": 12, "sensitive": ["bad_stretch"],
                         "failed": ["torott"]}, seconds=600.0, seed=3)
    assert s.startswith("# Hash-függés (generált jelentés)")
    assert "(600 mp, mag: 3), 3 külön folyamatban" in s
    assert "PYTHONHASHSEED = 1, 4, 7" in s
    assert "- összevetve: 12 réteg" in s and "- hash-függő: 1" in s
    assert "- nem mérhető (hibára futott): 1" in s
    assert "## Hash-függő rétegek (JAVÍTANDÓ)\n\n- `bad_stretch`" in s
    assert "## Nem mérhető rétegek\n\n- `torott`" in s
    assert "lista üres" not in s


def test_build_report_ures_listanal_kimondja():
    """Hash-függő réteg nélkül a jelentés kimondja, hogy a lista üres —
    és annak is kell maradnia; nincs javítandó és nincs nem-mérhető
    szakasz."""
    s = hs.build_report({"checked": 5, "sensitive": [], "failed": []},
                        seconds=60.0, seed=1)
    assert "A hash-függő lista üres — és annak is kell maradnia." in s
    assert "JAVÍTANDÓ" not in s and "Nem mérhető rétegek" not in s
    assert "- hash-függő: 0" in s


def test_main_megirja_a_jelentest_es_osszegez(monkeypatch, tmp_path, capsys):
    """Teljes módban a main a paraméterekkel mér, megírja a (tmp mappába
    irányított) jelentést, és a kimenetre összegez, név szerint."""
    kert: dict = {}

    def kamu_meres(seconds, seed, shots, only=""):
        kert.update(seconds=seconds, seed=seed, shots=shots, only=only)
        return {"checked": 9, "sensitive": ["bad_stretch"], "failed": []}

    jelentes = tmp_path / "HASH_FUGGES.md"
    monkeypatch.setattr(hs, "measure", kamu_meres)
    monkeypatch.setattr(hs, "_REPORT", jelentes)
    assert hs.main(["--seconds", "30", "--seed", "4", "--shots", "2"]) == 0
    assert kert == {"seconds": 30.0, "seed": 4, "shots": 2.0, "only": ""}
    assert jelentes.read_text(encoding="utf-8") == hs.build_report(
        kamu_meres(30.0, 4, 2.0), 30.0, 4)
    ki = capsys.readouterr().out
    assert f"Hash-függés kiírva: {jelentes}" in ki
    assert "összevetve: 9 réteg" in ki and "hash-függő: 1" in ki
    assert "    - bad_stretch" in ki and "nem mérhető: 0" in ki

    assert hs.main([]) == 0
    assert kert == {"seconds": hs.DEFAULT_SECONDS, "seed": hs.DEFAULT_SEED,
                    "shots": hs.DEFAULT_SHOTS_PER_MIN, "only": ""}
    capsys.readouterr()


def test_main_only_modban_nem_irja_felul_a_jelentest(monkeypatch, tmp_path,
                                                     capsys):
    """Egy gyanús réteg gyors újramérése (--only) egy sorban válaszol, és
    a teljes jelentés-fájlhoz nem nyúl."""
    eredmenyek = iter([
        {"checked": 1, "sensitive": [], "failed": []},
        {"checked": 1, "sensitive": ["bad_stretch"], "failed": ["torott"]}])
    kert: list = []

    def kamu_meres(seconds, seed, shots, only=""):
        kert.append(only)
        return next(eredmenyek)

    jelentes = tmp_path / "HASH_FUGGES.md"
    monkeypatch.setattr(hs, "measure", kamu_meres)
    monkeypatch.setattr(hs, "_REPORT", jelentes)
    assert hs.main(["--only", "xg"]) == 0
    assert capsys.readouterr().out.strip() == \
        "hash-függő (xg): nincs  · nem mérhető: nincs"
    assert hs.main(["--only", "bad_stretch,torott"]) == 0
    assert capsys.readouterr().out.strip() == (
        "hash-függő (bad_stretch,torott): ['bad_stretch']  · "
        "nem mérhető: ['torott']")
    assert kert == ["xg", "bad_stretch,torott"]
    assert not jelentes.exists()


def test_main_munkas_modban_csak_a_lenyomatokat_irja(monkeypatch, tmp_path,
                                                     capsys):
    """A --worker a folyamat-belépő: lefuttatja a munkást a kapott
    paraméterekkel, és nem mér, nem ír jelentést."""
    _proba_retegek(monkeypatch)
    monkeypatch.setattr(hs, "measure", lambda *a, **k: pytest.fail(
        "munkás-módban nem indulhat újabb mérés"))
    jelentes = tmp_path / "HASH_FUGGES.md"
    monkeypatch.setattr(hs, "_REPORT", jelentes)
    ki = tmp_path / "munkas.json"
    assert hs.main(["--worker", str(ki), "--seconds", "4", "--seed", "3",
                    "--shots", "8", "--only", "a,b"]) == 0
    assert set(json.loads(ki.read_text(encoding="utf-8"))) == {"a", "b"}
    assert capsys.readouterr().out == ""
    assert not jelentes.exists()
