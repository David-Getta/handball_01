"""Videó-metaadat: a felvétel dátumának kinyerése.

A meccs dátuma eddig jellemzően üresen maradt (a feltöltésnél senki nem
írja be) — pedig a játékos-trend időrendje és a könyvtár rendezése is
erre épül. A felvétel ideje viszont ott van a legtöbb videófájlban:

- MP4/MOV: az `mvhd` (movie header) doboz creation_time mezője
  (másodpercek 1904-01-01 UTC óta) — telefonok/kamerák kitöltik.
- Tartalék: a fájl módosítási ideje (feltöltésnél ez a feltöltés napja,
  ami tipikusan a meccs másnapja — még mindig jobb, mint a semmi).

Tiszta Python (struct + datetime), új függőség nélkül.
"""

from __future__ import annotations

import datetime
import os
import struct
from typing import Optional

# Az mvhd creation_time epoch-ja (QuickTime): 1904-01-01 UTC.
_QT_EPOCH = datetime.datetime(1904, 1, 1, tzinfo=datetime.timezone.utc)
# Csak életszerű dátumot fogadunk el (a 0 = 1904 a "nincs kitöltve" jele).
_MIN_YEAR, _MAX_YEAR = 1995, 2100
# Ekkora darabot olvasunk a fájl elejéről/végéről (a moov doboz vagy
# legelöl van — faststart —, vagy a fájl legvégén).
_SCAN_BYTES = 8 * 1024 * 1024


def _mvhd_creation(data: bytes) -> Optional[datetime.datetime]:
    """Az első értelmes mvhd creation_time a bájtokból, vagy None."""
    idx = 0
    while True:
        idx = data.find(b"mvhd", idx)
        if idx < 0:
            return None
        try:
            version = data[idx + 4]
            if version == 1:
                (secs,) = struct.unpack(">Q", data[idx + 8:idx + 16])
            else:
                (secs,) = struct.unpack(">I", data[idx + 8:idx + 12])
            dt = _QT_EPOCH + datetime.timedelta(seconds=secs)
            if _MIN_YEAR <= dt.year <= _MAX_YEAR:
                return dt
        except Exception:
            pass
        idx += 4  # tovább keresünk (pl. véletlen bájt-egyezés volt)


def video_recording_date(path: str) -> Optional[str]:
    """A felvétel dátuma ISO alakban (YYYY-MM-DD), vagy None hibánál.

    Először az MP4/MOV mvhd creation_time-ot keressük (a fájl elején,
    majd a végén), tartalékként a fájl módosítási ideje.
    """
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            head = f.read(min(size, _SCAN_BYTES))
            dt = _mvhd_creation(head)
            if dt is None and size > _SCAN_BYTES:
                f.seek(max(0, size - _SCAN_BYTES))
                dt = _mvhd_creation(f.read(_SCAN_BYTES))
        if dt is not None:
            return dt.date().isoformat()
        # Tartalék: a fájl módosítási ideje.
        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(path))
        if _MIN_YEAR <= mtime.year <= _MAX_YEAR:
            return mtime.date().isoformat()
    except Exception:
        pass
    return None
