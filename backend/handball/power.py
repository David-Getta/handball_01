"""Alvás-gátlás a feldolgozás idejére — hogy a gép ne aludjon el munka
közben, és ne fojtsa meg a számítást.

A feldolgozás percekig-órákig tart, és közben a felhasználó nem a
képernyőt bámulja: lehajtja a laptop tetejét, elmegy kávézni, vagy
egyszerűen más programmal dolgozik. Ilyenkor a rendszer energiatakarékos
üzemre vált:

  - macOS: a képernyő elalvása után **idle sleep** jön (a gép leáll), és
    a háttérbe került programokat az **App Nap** amúgy is lassítja,
  - Windows: az "alvás X perc tétlenség után" ugyanígy leállítja a
    számítást.

Mindkettőn ugyanaz a helyes megoldás: a MUNKA IDEJÉRE fogunk egy
alvás-gátló zárat, és a végén elengedjük. Nem kapcsolunk ki semmit
tartósan a felhasználó gépén — a zár a folyamatunkhoz kötődik, és a
feldolgozás végén (vagy a motor leállásakor) magától megszűnik.

ŐSZINTÉN a laptop-tetőről: ha a MacBook tetejét lehajtod és nincs
külső kijelző, a macOS akkor is elaltatja a gépet, ha zárat tartunk —
ezt alkalmazásból nem lehet felülbírálni (ez a "clamshell" viselkedés).
Amit a zár megold: a képernyő elalvása utáni tétlenségi alvást, a
lemez-alvást, és hálózati tápon a rendszer-alvást. Csatlakoztatott
tápon + külső kijelzővel a lehajtott tető sem állítja meg a munkát.
"""

from __future__ import annotations

import os
import subprocess
import sys

# Windows SetThreadExecutionState jelzők.
_ES_CONTINUOUS = 0x80000000
_ES_SYSTEM_REQUIRED = 0x00000001
_ES_AWAYMODE_REQUIRED = 0x00000040


class KeepAwake:
    """Alvás-gátló zár egy hosszú művelet idejére.

    Használat context managerként::

        with KeepAwake():
            hosszu_feldolgozas()

    A zár feloldása MINDIG megtörténik (a `finally` ágon is), és a
    hibája sosem akadályozhatja a feldolgozást: ha nem sikerül zárat
    fogni (jogosultság, hiányzó eszköz), a munka fut tovább — legfeljebb
    a gép elalhat.
    """

    def __init__(self) -> None:
        self._proc: subprocess.Popen | None = None
        self._windows_locked = False

    # -- macOS ------------------------------------------------------------
    def _start_macos(self) -> None:
        # A caffeinate a rendszer saját eszköze; a -w a MI folyamatunkhoz
        # köti, tehát ha a motor elszáll, a zár is megszűnik (nem marad
        # ott egy örökké ébren tartó folyamat a felhasználó gépén).
        #   -i: tétlenségi alvás tiltása
        #   -m: lemez-alvás tiltása
        #   -s: rendszer-alvás tiltása (hálózati tápon)
        self._proc = subprocess.Popen(
            ["/usr/bin/caffeinate", "-i", "-m", "-s", "-w", str(os.getpid())],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # -- Windows ----------------------------------------------------------
    def _start_windows(self) -> None:
        import ctypes

        # Az ES_CONTINUOUS a szálhoz köti az állapotot: amíg vissza nem
        # állítjuk, a rendszer nem alszik el tétlenség miatt.
        ctypes.windll.kernel32.SetThreadExecutionState(  # type: ignore[attr-defined]
            _ES_CONTINUOUS | _ES_SYSTEM_REQUIRED | _ES_AWAYMODE_REQUIRED)
        self._windows_locked = True

    def start(self) -> None:
        try:
            if sys.platform == "darwin":
                self._start_macos()
            elif os.name == "nt":
                self._start_windows()
            # Linuxon nincs egységes, telepítés nélküli eszköz — ott a
            # zár kimarad (a szervergépek amúgy sem alszanak el).
        except Exception:
            # A zár hibája SOSEM akadályozhatja a feldolgozást.
            self._proc = None
            self._windows_locked = False

    def stop(self) -> None:
        try:
            if self._proc is not None:
                self._proc.terminate()
                self._proc = None
        except Exception:
            pass
        try:
            if self._windows_locked:
                import ctypes

                ctypes.windll.kernel32.SetThreadExecutionState(  # type: ignore[attr-defined]
                    _ES_CONTINUOUS)
                self._windows_locked = False
        except Exception:
            pass

    @property
    def active(self) -> bool:
        """Fog-e most zárat (a diagnosztika és a tesztek kérdezik)."""
        return self._proc is not None or self._windows_locked

    def __enter__(self) -> "KeepAwake":
        self.start()
        return self

    def __exit__(self, *_exc) -> None:
        self.stop()
