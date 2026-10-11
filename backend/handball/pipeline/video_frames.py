"""A forrás-videó kockái képként.

A feldolgozott meccs t. kockájához (a kocka t címkéje) a forrás-videó
kockája — összefűzött meccsnél a megfelelő szakasz videójából. A 3D pálya
Videó-ablaka (/matches/{id}/frame) és a jelentés videózandó-jelenet képei
ebből dolgoznak, hogy a két felület ugyanazt a kockát mutassa.
"""
from __future__ import annotations

from pathlib import Path

# A kért kép-szélesség korlátai (pixel): keskenyebb kép olvashatatlan, a
# szélesebb a hálózaton és a jelentésben fölösleges.
FRAME_MIN_W = 160
FRAME_MAX_W = 1280
# A jelentés jelenet-képeinek szélessége (pixel) és JPEG-minősége: nyomtatva
# is felismerhető a jelenet, a jelentés mégse hízzon meg (~15–25 kB/kép).
REPORT_FRAME_W = 320
REPORT_FRAME_Q = 70
# Ennyi másodpercen belül ELŐRE kért kockához nem tekerünk, hanem
# továbbolvasunk: a tekerés a megelőző kulcskockától dekódol (hosszú
# GOP-nál kockánként több száz dekódolás), a 3D Videó-ablaka pedig
# lejátszás közben egymás utáni kockákat kér. Ennél messzebb a tekerés
# olcsóbb, mint a sok kocka végigdekódolása.
SEQ_READ_MAX_S = 2.0


def source_frame(match, t: int) -> tuple[str, int] | None:
    """(videó-útvonal, forrás-kocka sorszáma) a feldolgozott t. kockához
    (start_frame + (t − a szakasz eleje) × stride); None, ha nincs
    forrás-videó, vagy nem érhető el ezen a gépen."""
    from .clips import _segment_of, _source_segments

    t = max(0, int(t))
    sz = _segment_of(_source_segments(match), t)
    if sz is None or not Path(sz["video_path"]).exists():
        return None
    return (sz["video_path"],
            sz["start_frame"] + (t - sz["t_from"]) * sz["stride"])


def read_jpeg(cap, frame_index: int, width: int,
              quality: int = 75) -> bytes | None:
    """A megnyitott videó adott kockája JPEG-ben, `width` szélesre
    kicsinyítve (arányosan; nagyítás nincs, a szélesség a FRAME_MIN_W …
    FRAME_MAX_W sávba szorítva). None: a kocka nem olvasható (pl. a
    videó vége után). Ha a kért kocka SEQ_READ_MAX_S-en belül a mostani
    olvasási hely ELŐTT van, továbbolvas (grab), különben teker."""
    import cv2

    frame_index = int(frame_index)
    try:
        hol = int(cap.get(cv2.CAP_PROP_POS_FRAMES))  # a következő kocka
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    except (TypeError, ValueError):
        hol, fps = -1, 0.0
    elore = frame_index - hol
    if hol >= 0 and fps > 0 and 0 <= elore <= SEQ_READ_MAX_S * fps:
        for _ in range(elore):
            if not cap.grab():
                return None
    else:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
    ok, img = cap.read()
    if not ok or img is None:
        return None
    szeles = max(FRAME_MIN_W, min(FRAME_MAX_W, int(width)))
    h_, w_ = img.shape[:2]
    if w_ > szeles:
        img = cv2.resize(img, (szeles, max(1, round(h_ * szeles / w_))),
                         interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img,
                           [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)])
    return buf.tobytes() if ok else None


def frames_jpeg(match, ts, width: int = REPORT_FRAME_W,
                quality: int = REPORT_FRAME_Q) -> dict:
    """Több kocka egyszerre: {t: JPEG-bájtok} — videónként EGY megnyitás,
    a kockák időrendben (a visszafelé tekerés lassú). Az elérhetetlen
    videójú vagy olvashatatlan kocka kimarad (nem hiba): a jelentés kép
    nélkül is teljes."""
    from ..video_io import VideoOpenError, open_capture

    csoport: dict = {}
    for t in sorted({max(0, int(t)) for t in ts}):
        hol = source_frame(match, t)
        if hol is not None:
            csoport.setdefault(hol[0], []).append((t, hol[1]))
    ki = {}
    for ut in sorted(csoport):
        try:
            cap = open_capture(ut)
        except VideoOpenError:
            continue
        try:
            for t, kocka in csoport[ut]:
                kep = read_jpeg(cap, kocka, width, quality)
                if kep is not None:
                    ki[t] = kep
        finally:
            cap.release()
    return ki
