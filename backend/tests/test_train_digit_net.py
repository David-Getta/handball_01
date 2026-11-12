"""
Tesztek a számjegy-háló tanító szkriptjére (scripts/train_digit_net.py).

A mezszám-OCR agya szintetikus adatból tanul; a szkript eddig egyszer sem
futott a csomagban. Itt kicsiben (másodperc alatt) végigmegy a teljes út:
renderelés → adathalmaz → tanítás → a felismerő (jersey_ocr) ugyanezzel a
súly-alakkal osztályoz. A csomaggal szállított súlyfájlt a teszt NEM írja
felül (a mentést elkapjuk).

Futtatás:
    python -m pytest tests/test_train_digit_net.py -q
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

np = pytest.importorskip("numpy")
pytest.importorskip("cv2")

from scripts import train_digit_net as tdn  # noqa: E402


def test_render_digit_28x28_normalt_es_megismetelheto():
    """A renderelt számjegy 28×28-as, [0, 1] közti float32 kép, nem üres
    (szoros vágás után a jegy kitölti); ugyanazzal a maggal ugyanaz,
    más jegyre más kép."""
    kep = tdn.render_digit(7, np.random.default_rng(1))
    assert kep.shape == (28, 28) and kep.dtype == np.float32
    assert 0.0 <= float(kep.min()) and float(kep.max()) <= 1.0
    assert float(kep.max()) > 0.5 and float(kep.mean()) > 0.05
    assert np.array_equal(kep, tdn.render_digit(7, np.random.default_rng(1)))
    assert not np.array_equal(kep, tdn.render_digit(1, np.random.default_rng(1)))
    # Mind a tíz jegy renderelhető, sok véletlen torzítással is.
    rng = np.random.default_rng(5)
    for d in range(10):
        for _ in range(20):
            x = tdn.render_digit(d, rng)
            assert x.shape == (28, 28) and float(x.max()) > 0.3, d


def test_render_negative_nem_szamjegy_mintak():
    """A "nem számjegy" minta (betű, vonal-köteg, folt) ugyanolyan alakú
    és tartományú, mint a számjegy — és változatos (nem egyetlen kép)."""
    rng = np.random.default_rng(2)
    mintak = [tdn.render_negative(rng) for _ in range(40)]
    for x in mintak:
        assert x.shape == (28, 28) and x.dtype == np.float32
        assert 0.0 <= float(x.min()) and float(x.max()) <= 1.0
        assert float(x.max()) > 0.3
    kulonbozo = {x.tobytes() for x in mintak}
    assert len(kulonbozo) == len(mintak)
    # A tömör folt és a vékony vonal más kitöltöttségű: a minták nem
    # egyformán "tintásak".
    tinta = sorted(float((x > 0.5).mean()) for x in mintak)
    assert tinta[-1] > 2 * tinta[0]


def test_finish_ures_kepre_none_kulonben_normalt():
    """A közös normalizálás üres (csupa fekete) képre None-t ad — nincs
    mit szorosra vágni —, különben 28×28-as, [0, 1] közti képet."""
    rng = np.random.default_rng(3)
    assert tdn._finish(np.zeros((72, 72), np.uint8), rng) is None
    kep = np.zeros((72, 72), np.uint8)
    kep[20:50, 30:40] = 255
    ki = tdn._finish(kep, rng)
    assert ki.shape == (28, 28) and ki.dtype == np.float32
    assert 0.0 <= float(ki.min()) and float(ki.max()) <= 1.0
    assert float(ki.mean()) > 0.4            # a szoros vágás kitölti


def test_make_dataset_kiegyensulyozott_kevert_megismetelheto():
    """Osztályonként ugyanannyi minta (10 számjegy + az elutasító
    osztály), kilapítva (784), összekeverve; ugyanazzal a maggal
    bitre ugyanaz, más maggal más."""
    x, y = tdn.make_dataset(6, seed=11)
    assert x.shape == (66, 784) and x.dtype == np.float32
    assert y.shape == (66,) and y.dtype == np.int64
    assert np.bincount(y).tolist() == [6] * 11
    assert tdn.REJECT_CLASS == 10 and int(y.max()) == tdn.REJECT_CLASS
    assert 0.0 <= float(x.min()) and float(x.max()) <= 1.0
    assert y.tolist() != sorted(y.tolist())          # kevert
    x2, y2 = tdn.make_dataset(6, seed=11)
    assert np.array_equal(x, x2) and np.array_equal(y, y2)
    x3, _ = tdn.make_dataset(6, seed=12)
    assert not np.array_equal(x, x3)


def test_make_dataset_nulla_mintaval_nincs_adathalmaz():
    """Nulla minta/osztály: nincs miből adathalmazt építeni — a hiba
    azonnal jön (nem üres hálót tanítunk csendben)."""
    with pytest.raises(ValueError):
        tdn.make_dataset(0, seed=1)


def test_train_kis_halo_megtanulja_a_szamjegyeket(capsys):
    """Kicsiben is tanul: néhány epoch után a validációs pontosság messze
    a találgatás (1/11) fölött van; a súlyok alakja 784→128→11, és
    epochonként egy sor megy a kimenetre."""
    (w1, b1, w2, b2), acc = tdn.train(4, 120, seed=7)
    assert w1.shape == (784, 128) and b1.shape == (128,)
    assert w2.shape == (128, 11) and b2.shape == (11,)
    assert all(a.dtype == np.float32 for a in (w1, b1, w2, b2))
    assert 0.9 < acc <= 1.0
    sorok = capsys.readouterr().out.strip().splitlines()
    assert len(sorok) == 4
    assert sorok[0].startswith("epoch 1/4 · val pontosság: ")
    assert sorok[-1].startswith("epoch 4/4 · val pontosság: ")


def test_train_megismetelheto_es_tanulas_nelkul_talalgat(capsys):
    """Ugyanazzal a maggal ugyanazok a súlyok; nulla epoch-kal (tanítás
    nélkül) a pontosság a találgatás környékén marad — a magas szám
    tehát a tanulásból jön, nem a mérésből."""
    (w1, _, _, _), acc = tdn.train(1, 40, seed=7)
    (w1b, _, _, _), accb = tdn.train(1, 40, seed=7)
    assert np.array_equal(w1, w1b) and acc == accb
    _, tanulatlan = tdn.train(0, 40, seed=7)
    assert tanulatlan < 0.35 < acc
    capsys.readouterr()


def test_a_tanitott_halo_a_felismeroben_is_osztalyoz():
    """A VALÓDI felhasználó a jersey_ocr: a tanító szkript súly-alakjával
    a felismerő osztályozója a renderelt jegyeket helyesen olvassa, a
    "nem számjegy" mintákat pedig jellemzően elutasítja (None)."""
    from handball.pipeline import jersey_ocr

    net, _ = tdn.train(4, 120, seed=7)
    rng = np.random.default_rng(123)
    jo = osszes = 0
    for d in range(10):
        for _ in range(15):
            kep = (tdn.render_digit(d, rng) * 255).astype(np.uint8)
            kapott, biztos = jersey_ocr._classify_digit(kep, net)
            osszes += 1
            jo += (kapott == d)
            assert 0.0 <= biztos <= 1.0
    assert jo / osszes >= 0.9, f"{jo}/{osszes}"
    elutasitott = sum(
        jersey_ocr._classify_digit(
            (tdn.render_negative(rng) * 255).astype(np.uint8), net)[0] is None
        for _ in range(100))
    assert elutasitott >= 70, elutasitott


def test_a_szallitott_sulyfajl_a_szkript_eloszlasan_pontos():
    """ŐR: a csomaggal szállított digit_net.npz a tanító szkript
    kimenete — a szkript renderelt jegyein közel hibátlan, a súlyok
    alakja a szkripté, és a fájl viszi a pontosság-metaadatot."""
    from pathlib import Path

    from handball.pipeline import jersey_ocr

    fajl = Path(jersey_ocr.__file__).parent / "digit_net.npz"
    adat = np.load(str(fajl))
    assert {"w1", "b1", "w2", "b2", "val_accuracy",
            "trained_at"} <= set(adat.files)
    assert adat["w1"].shape == (784, 128) and adat["w2"].shape == (128, 11)
    assert 0.95 <= float(adat["val_accuracy"]) <= 1.0
    net = (adat["w1"], adat["b1"], adat["w2"], adat["b2"])
    rng = np.random.default_rng(321)
    jo = osszes = 0
    for d in range(10):
        for _ in range(15):
            kep = (tdn.render_digit(d, rng) * 255).astype(np.uint8)
            osszes += 1
            jo += (jersey_ocr._classify_digit(kep, net)[0] == d)
    assert jo / osszes >= 0.95, f"{jo}/{osszes}"


def test_main_a_csomag_sulyfajljaba_ment_a_teszt_nem_irja_felul(
        monkeypatch, capsys):
    """A main a parancssori paraméterekkel tanít, és a súlyokat (a
    pontossággal és a dátummal) a csomag digit_net.npz fájljába menti —
    a teszt a mentést elkapja, a szállított fájl érintetlen marad."""
    from pathlib import Path

    from handball.pipeline import jersey_ocr

    szallitott = Path(jersey_ocr.__file__).parent / "digit_net.npz"
    elotte = (szallitott.stat().st_mtime_ns, szallitott.stat().st_size)
    mentes: dict = {}

    def _elkap(ut, **tombok):
        mentes["ut"] = ut
        mentes["tombok"] = tombok

    monkeypatch.setattr(tdn.np, "savez_compressed", _elkap)
    monkeypatch.setattr(sys, "argv", ["train_digit_net", "--epochs", "1",
                                      "--samples", "30"])
    assert tdn.main() == 0

    assert Path(mentes["ut"]) == szallitott
    t = mentes["tombok"]
    assert set(t) == {"w1", "b1", "w2", "b2", "val_accuracy", "trained_at"}
    assert t["w1"].shape == (784, 128) and t["w2"].shape == (128, 11)
    assert 0.0 <= float(t["val_accuracy"]) <= 1.0
    assert len(bytes(t["trained_at"]).decode()) == len("2026-01-01")
    ki = capsys.readouterr().out
    assert "epoch 1/1" in ki and "kész:" in ki and "digit_net.npz" in ki
    assert (szallitott.stat().st_mtime_ns,
            szallitott.stat().st_size) == elotte
