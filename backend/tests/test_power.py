"""Alvás-gátlás a feldolgozás idejére.

A feldolgozás percekig-órákig tart, és közben a felhasználó nem a
képernyőt nézi: lehajtja a laptop tetejét, elmegy. Zár nélkül a rendszer
tétlenségi alvásra vált, és a számítás megáll vagy lelassul.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from handball.power import KeepAwake  # noqa: E402


def test_a_zar_hibaja_nem_allitja_meg_a_munkat(monkeypatch):
    """ŐR: ha a zár fogása elhasal (nincs eszköz, jogosultsági hiba), a
    feldolgozásnak akkor is futnia kell.

    Ez a legfontosabb tulajdonsága: kényelmi funkció, nem előfeltétel —
    a hibája SOSEM akadályozhatja a munkát.
    """
    import subprocess

    def robban(*a, **k):
        raise OSError("nincs ilyen eszköz")

    monkeypatch.setattr(subprocess, "Popen", robban)
    zar = KeepAwake()
    zar.start()      # nem dobhat
    assert zar.active is False
    zar.stop()       # nem dobhat


def test_a_context_manager_mindig_felold(monkeypatch):
    """ŐR: a zár a kivétel útján is feloldódik — különben a gép a
    feldolgozás után is ébren maradna, és enné az akkumulátort."""
    elengedve = {"igen": False}

    zar = KeepAwake()
    monkeypatch.setattr(zar, "start", lambda: None)
    monkeypatch.setattr(zar, "stop",
                        lambda: elengedve.update(igen=True))
    try:
        with zar:
            raise RuntimeError("a feldolgozás elszállt")
    except RuntimeError:
        pass
    assert elengedve["igen"], "a zár kivétel esetén nem oldódott fel"


def test_a_zar_a_sajat_folyamatunkhoz_kotodik():
    """ŐR: macOS-en a caffeinate a MI folyamatunkra vár (-w <pid>).

    Enélkül egy elszálló motor után ott maradna egy örökké ébren tartó
    folyamat a felhasználó gépén — a mi hibánkból merülne le az
    akkumulátora.
    """
    from pathlib import Path

    src = (Path(__file__).resolve().parent.parent
           / "handball" / "power.py").read_text(encoding="utf-8")
    assert '"-w", str(os.getpid())' in src, (
        "a caffeinate nincs a saját folyamatunkhoz kötve")
