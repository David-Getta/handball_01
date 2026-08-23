"""Videó-megnyitás EGY helyen — ékezetes útvonalon is.

Miért kell külön modul: az OpenCV `VideoCapture` Windowson a rendszer
kódlapján át nyitja a fájlt, ezért az ÉKEZETES útvonalon (pl.
`C:\\Users\\Dávid\\Videók\\meccs.mp4`) egyszerűen nem nyílik meg — és
NEM dob kivételt, csak `isOpened() == False`-t ad. Magyar felhasználónál
ez a mindennapi eset, nem a ritka kivétel.

A kódbázisban kilenc helyen nyitottunk videót, egyik sem nézte az
`isOpened()`-et: a hiba így "nem sikerült képkockát olvasni" alakban
csapódott le, ami a felhasználónak semmit nem mond, és a valódi okot
(az ékezetet az útvonalban) elrejti.

Ez a modul két dolgot ad:
  - `open_capture`: megnyitás, és ha az ékezet miatt bukna, MÁSODIK
    próbálkozás a Windows rövid (8.3-as) útvonalával — az csak ASCII
    karaktereket tartalmaz, tehát az OpenCV is elboldogul vele,
  - `explain_unopenable`: emberi mondat arról, MIÉRT nem nyílt meg, és
    mit tegyen a felhasználó.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Union


class VideoOpenError(RuntimeError):
    """A videót nem sikerült megnyitni — az üzenet emberi nyelvű."""


def has_non_ascii(text: str) -> bool:
    """Van-e nem-ASCII (pl. ékezetes) karakter a szövegben."""
    return any(ord(ch) > 127 for ch in text)


def _windows_short_path(path: str) -> Union[str, None]:
    """A Windows RÖVID (8.3-as) útvonala — csak ASCII karakterekből.

    Ez a bevett kerülőút az ékezetes útvonalakra: a rövid alak minden
    összetevőt ASCII-ra rövidít (`Dávid` → `DVID~1`), így az OpenCV is
    meg tudja nyitni. None, ha nem kérhető le (pl. a köteten ki van
    kapcsolva a 8.3-as névgenerálás).
    """
    try:
        import ctypes
        from ctypes import wintypes

        get_short = ctypes.windll.kernel32.GetShortPathNameW  # type: ignore[attr-defined]
        get_short.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD]
        get_short.restype = wintypes.DWORD
        kell = get_short(path, None, 0)
        if kell == 0:
            return None
        puffer = ctypes.create_unicode_buffer(kell)
        if get_short(path, puffer, kell) == 0:
            return None
        return puffer.value or None
    except Exception:
        return None


def explain_unopenable(path: str) -> str:
    """Miért nem nyílt meg a videó — emberi mondat, teendővel."""
    if not os.path.exists(path):
        return (f"Nem találom a videót: {path} — lehet, hogy áthelyezték, "
                "átnevezték, vagy a meghajtó nincs csatlakoztatva.")
    if has_non_ascii(path):
        return (f"A videót nem sikerült megnyitni: {path}. Az útvonalban "
                "ÉKEZETES karakter van, és a videó-olvasó ezt Windowson "
                "nem mindig bírja. Tedd a fájlt ékezet nélküli mappába "
                "(pl. C:\\\\videok\\\\meccs.mp4), és próbáld újra.")
    return (f"A videót nem sikerült megnyitni: {path}. A fájl sérült "
            "lehet, vagy olyan formátum/kodek, amit a rendszer nem ismer "
            "— próbáld MP4 (H.264) formátumban.")


def video_seconds(path: Union[str, Path]) -> Union[float, None]:
    """A videó hossza másodpercben — vagy None, ha nem olvasható ki.

    Csak a fejlécet kérdezzük meg (kockaszám / fps), tehát ez gyors:
    az indítás előtti becsléshez kell, nem szabad megvárakoztatnia a
    felhasználót. A hibás/hiányzó metaadat itt NEM hiba: ilyenkor
    egyszerűen nincs becslés.
    """
    import cv2

    cap = None
    try:
        cap = open_capture(path)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        kockak = float(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0.0)
        if fps <= 0 or kockak <= 0:
            return None
        return kockak / fps
    except Exception:
        return None
    finally:
        try:
            if cap is not None:
                cap.release()
        except Exception:
            pass


def open_capture(path: Union[str, Path]):
    """Videó megnyitása `cv2.VideoCapture`-rel, ékezet-tűrően.

    Sikertelen megnyitásnál `VideoOpenError`-t dob, EMBERI üzenettel —
    a néma `isOpened() == False` volt az, ami miatt a valódi ok (ékezetes
    útvonal, hiányzó fájl, ismeretlen kodek) sosem jutott el a
    felhasználóig.
    """
    import cv2

    p = str(path)
    cap = cv2.VideoCapture(p)
    if cap.isOpened():
        return cap
    cap.release()

    # Windows + ékezetes útvonal: második próbálkozás a rövid alakkal.
    if os.name == "nt" and has_non_ascii(p):
        rovid = _windows_short_path(p)
        if rovid and rovid != p:
            cap = cv2.VideoCapture(rovid)
            if cap.isOpened():
                return cap
            cap.release()

    raise VideoOpenError(explain_unopenable(p))
