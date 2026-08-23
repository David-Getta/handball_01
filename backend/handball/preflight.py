"""Előzetes ellenőrzés a feldolgozás INDÍTÁSA előtt.

Egy meccs feldolgozása fél-egy óra. A legrosszabb, ami történhet, hogy
ez az óra elmegy, és a végén derül ki: nincs hova írni az eredményt.
Ez a modul azokat a kérdéseket teszi fel ELŐRE, amikre a válasz
utólag már fájdalmas:

  - Van-e elég szabad hely az adatmappán? (A meccs-fájl, a részleges
    mentések és a klip-export mind oda mennek.)
  - Nagyjából mennyi ideig fog tartani? (Ezt EZEN a gépen mért adatból
    mondjuk meg — a becslés a korábbi feldolgozások tényleges idejéből
    jön, nem egy laborban mért számból.)

A modul szándékosan nem "okoskodik": ha nincs elég korábbi mérés,
inkább nem mond becslést (None), mint hogy tévesen nyugtasson meg.
"""

from __future__ import annotations

import shutil
from pathlib import Path

# Ennyi szabad hely kell mindenképpen az adatmappán. A meccs-fájl
# mérete a videó hosszával nő, a részleges mentés pedig menet közben
# megduplázhatja — 2 GB az a küszöb, ami alatt a feldolgozás közben
# elfogyó hely reális kockázat.
MIN_FREE_GB = 2.0

# A kimenetre a videó méretének ekkora hányadát tartjuk fenn a fenti
# alapon FELÜL (meccs-fájl + részleges mentések + naplók). Mért érték
# nincs rá; óvatos, kerek becslés.
OUTPUT_SHARE = 0.10

# Ennyi korábbi, SIKERES feldolgozás kell, hogy időt merjünk becsülni.
# Egyetlen mérésből az ütem félrevezető (első futásnál a modell
# letöltése is beleszámít).
MIN_HISTORY_RUNS = 2


def free_gb(root: Path | str) -> float | None:
    """Szabad hely az adott mappa mögötti köteten, GB-ban (vagy None)."""
    try:
        return shutil.disk_usage(str(root)).free / 1e9
    except Exception:
        return None


def disk_space_error(video_path: str | None, root: Path | str) -> str | None:
    """Magyar hibaüzenet, ha NEM biztonságos elindítani — különben None.

    Az üzenet megmondja, mennyi van és mennyi kellene: a felhasználó
    csak így tudja eldönteni, mit takarítson ki.
    """
    szabad = free_gb(root)
    if szabad is None:
        return None  # nem tudjuk megmérni — ne akadályozzuk a munkát
    kell = MIN_FREE_GB
    try:
        if video_path:
            meret_gb = Path(video_path).stat().st_size / 1e9
            kell += meret_gb * OUTPUT_SHARE
    except Exception:
        pass
    if szabad >= kell:
        return None
    return (f"nincs elég szabad hely a feldolgozáshoz: {szabad:.1f} GB "
            f"van, kb. {kell:.1f} GB kellene. Szabadíts fel helyet, és "
            f"indítsd újra — így a feldolgozás nem áll meg a közepén.")


def _sikeres_futasok(rows: list[dict]) -> list[tuple[float, float]]:
    """(videó-másodperc, feldolgozás-másodperc) párok a naplóból.

    Csak a KÉSZ munkák számítanak: a megszakított és a hibára futott
    munkák ideje nem a teljes videóé, tehát az ütemet elrontaná.
    """
    ki: list[tuple[float, float]] = []
    for r in rows:
        if r.get("status") != "done":
            continue
        vid = r.get("video_seconds")
        start = r.get("started")
        veg = r.get("finished")
        try:
            vid = float(vid)
            munka = float(veg) - float(start)
        except (TypeError, ValueError):
            continue
        if vid > 0 and munka > 0:
            ki.append((vid, munka))
    return ki


def speed_from_history(rows: list[dict]) -> float | None:
    """Hány másodperc feldolgozás jut EGY másodperc videóra ezen a gépen.

    A napló legutóbbi futásaiból, a teljes videó-idő és a teljes
    munkaidő hányadosaként (a hosszabb futások így nagyobb súlyt
    kapnak, ami helyes: az ütem rájuk jellemzőbb). Kevés mérésnél None.
    """
    parok = _sikeres_futasok(rows)
    if len(parok) < MIN_HISTORY_RUNS:
        return None
    ossz_video = sum(v for v, _ in parok)
    ossz_munka = sum(m for _, m in parok)
    if ossz_video <= 0:
        return None
    return ossz_munka / ossz_video


def estimate_seconds(video_seconds: float | None,
                     rows: list[dict]) -> int | None:
    """A videó feldolgozásának becsült ideje másodpercben (vagy None)."""
    if not video_seconds or video_seconds <= 0:
        return None
    utem = speed_from_history(rows)
    if utem is None:
        return None
    return int(round(video_seconds * utem))


def human_duration(seconds: int | None) -> str | None:
    """Emberi felirat a becsléshez — "kb." nélkül (azt a hívó teszi ki)."""
    if seconds is None or seconds <= 0:
        return None
    if seconds < 60:
        return f"{seconds} másodperc"
    perc = int(round(seconds / 60))
    if perc < 60:
        return f"{perc} perc"
    ora = seconds // 3600
    maradek = int(round((seconds % 3600) / 60))
    if maradek == 0:
        return f"{ora} óra"
    return f"{ora} óra {maradek} perc"
