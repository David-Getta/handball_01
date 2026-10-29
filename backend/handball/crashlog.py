"""A motor NATÍV összeomlásának nyoma: hol és miért halt meg a folyamat.

Terepen látott hiba: egy videó feldolgozása közben a motor-folyamat
egyszerűen megszűnik (a videó-dekóder vagy a detektáló modell natív
kódja összeomlik, vagy a rendszer leállítja), az őrkutya újraindítja,
és a felhasználó csak annyit lát, hogy "a motor újraindult, a munka
elveszett". Python-kivétel ilyenkor nincs, tehát a meglévő hibanapló
(engine-crash.log) üres marad — a MIÉRT nyomtalanul elvész.

Ez a modul két dolgot ad:

- `enable_fault_log()`: a `faulthandler` a natív összeomláskor
  (szegmentációs hiba, abort, Windows hozzáférés-sértés) az ÖSSZES szál
  Python-hívásláncát az engine-crash.log-ba írja — ebből látszik, melyik
  sornál (videó-olvasás, modell-futtatás) halt meg a motor.
- `crash_summary(offset)`: az offset (a munka indulásakor mért
  fájlméret) UTÁN írt összeomlás egy mondatban, magyarul — az
  újrainduló motor ezzel mondja meg a félbeszakadt munkáról, mi történt.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

CRASH_LOG_NAME = "engine-crash.log"
# Ennyi bájtot olvasunk vissza a napló végéből (a szál-láncok elférnek
# benne; egy hosszú régi napló beolvasása nem lassíthatja az indulást).
CRASH_TAIL_BYTES = 64 * 1024

# A nyitva tartott naplófájl: a faulthandler a fájl-leíróba ír, tehát a
# fájlnak a folyamat végéig élnie kell.
_FAULT_FILE = None

_FATAL_RE = re.compile(r"^(Fatal Python error: .+|Windows fatal exception: .+)$")
_FRAME_RE = re.compile(r'^\s+File "(.+)", line (\d+) in (.+)$')


def crash_log_path() -> Path:
    from .storage import data_root
    return data_root() / CRASH_LOG_NAME


def enable_fault_log() -> bool:
    """A natív összeomlás szál-láncai az engine-crash.log-ba. Igaz, ha be
    is kapcsolt; a hibája sosem állíthatja meg az indulást."""
    global _FAULT_FILE
    import faulthandler
    try:
        p = crash_log_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        if _FAULT_FILE is None:
            _FAULT_FILE = open(p, "a", encoding="utf-8", errors="replace")
        faulthandler.enable(file=_FAULT_FILE, all_threads=True)
        return True
    except Exception:
        return False


def crash_log_size() -> int:
    """A napló mostani mérete (a munka indulásakor ezt jegyezzük fel)."""
    try:
        return crash_log_path().stat().st_size
    except OSError:
        return 0


def _rovid(fajl: str) -> str:
    """A fájl útja az utolsó két tagjára rövidítve (a felhasználói mappa
    neve ne kerüljön a hibaüzenetbe)."""
    tagok = re.split(r"[\\/]", fajl)
    return "/".join(tagok[-2:])


def _hol(fajl: str) -> str:
    """Emberi hely a hívás-lánc legfelső sorából — az út TAGJAI alapján:
    a telepítési mappa neve (pl. "VideoElemzes") nem téveszthet meg, és a
    saját process_video.py sem "videó-olvasás"."""
    if _sajat(fajl):
        return "a feldolgozás közben"
    tagok = [t.lower() for t in re.split(r"[\\/]", fajl) if t]
    if "cv2" in tagok or tagok[-1:] == ["loaders.py"]:
        return "a videó olvasása (dekódolása) közben"
    if "torch" in tagok or "ultralytics" in tagok:
        return "a detektáló modell futtatása közben"
    return "a feldolgozás közben"


def _sajat(fajl: str) -> bool:
    f = fajl.replace("\\", "/")
    return "/handball/" in f or "/scripts/" in f


def parse_fault(szoveg: str) -> dict | None:
    """Az UTOLSÓ faulthandler-blokk a szövegből: {fatal, top, own} vagy
    None. `top` az összeomló szál legfelső (legutóbbi) hívása, `own` az
    első saját kódbeli sora — (fájl, sor, függvény) hármasok."""
    sorok = szoveg.splitlines()
    eleje = None
    for i, s in enumerate(sorok):
        if _FATAL_RE.match(s.strip()):
            eleje = i
    if eleje is None:
        return None
    fatal = sorok[eleje].strip()
    blokk = sorok[eleje + 1:]
    # Az összeomló szál a "Current thread" blokk; ha nincs (régi alak),
    # az első szál-blokk.
    kezd = next((i for i, s in enumerate(blokk)
                 if s.startswith("Current thread")), None)
    if kezd is None:
        kezd = next((i for i, s in enumerate(blokk)
                     if s.startswith("Thread ")), None)
    keretek = []
    if kezd is not None:
        for s in blokk[kezd + 1:]:
            m = _FRAME_RE.match(s)
            if not m:
                break
            keretek.append((m.group(1), int(m.group(2)), m.group(3)))
    top = keretek[0] if keretek else None
    own = next((k for k in keretek if _sajat(k[0])), None)
    return {"fatal": fatal, "top": top, "own": own}


def crash_summary(offset: int = 0) -> str | None:
    """Az `offset` UTÁN a naplóba írt natív összeomlás egy mondatban —
    None, ha azóta nem íródott ilyen (a folyamatot ilyenkor kívülről
    állították le: elfogyott a memória, leállt / elaludt a gép)."""
    try:
        p = crash_log_path()
        meret = p.stat().st_size
        if meret <= offset:
            return None
        with open(p, "rb") as f:
            f.seek(max(int(offset), meret - CRASH_TAIL_BYTES))
            szoveg = f.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    r = parse_fault(szoveg)
    if r is None:
        return None
    ok = r["fatal"].split(":", 1)[1].strip()
    mondat = f"natív összeomlás ({ok})"
    if r["top"]:
        fajl, sor, fv = r["top"]
        mondat += f" {_hol(fajl)} — itt: {fv} ({_rovid(fajl)}:{sor})"
        if r["own"] and r["own"] != r["top"]:
            ofajl, osor, ofv = r["own"]
            mondat += f", a mi kódunkban: {ofv} ({_rovid(ofajl)}:{osor})"
    return mondat


def pid_alive(pid) -> bool:
    """Él-e még a folyamat (egy MÁSIK motor-példány dolgozhat a munkán).
    Kétes esetben hamis: a félbehagyott munkát inkább jelezzük."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            h = k32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
            if not h:
                return False
            try:
                kod = ctypes.c_ulong()
                ok = k32.GetExitCodeProcess(h, ctypes.byref(kod))
                return bool(ok) and kod.value == 259  # STILL_ACTIVE
            finally:
                k32.CloseHandle(h)
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except OSError:
        return False
