"""Figura-videó: a figura felülnézeti animációja MP4-ben.

A 3D figura-link csak a klub-hálózaton él, a figura-lap papír — a
csapatnak elküldhető mozgókép eddig nem volt. Ez a modul a 3D figura
kockáiból (play_simulation.setplay_3d_match: valós tempó, a késő fal,
a passzok repülése) felülnézeti videót rajzol a támadó térfélre vágva:
a támadók kékkel, a fal és a kapus pirossal (mezszámmal — mint a
szem=… linkek), a labda sárgán, a futások és a passzok halvány nyila a
padlón, fent a figura neve és a mostani kulcs-pozíció.

A kodek: a H.264, ha a gép tudja (a telefonok ezt játsszák le —
Windowson a Media Foundation, macOS-en az AVFoundation, aztán az
FFmpeg), különben az mp4v (mint a klipeké). A szöveg
Hershey-betűs: az ékezet lekerül ("Védő" → "Vedo"); a fájl neve
ékezetes marad.
"""
from __future__ import annotations

import math
import unicodedata
from pathlib import Path

from ..models.tracking import Team
from .calibration import COURT_LENGTH_M, COURT_WIDTH_M

# A videó kockasebessége (a 3D 6 kockája közt simítva) és felbontása.
FIGURA_VIDEO_FPS = 24.0
FIGURA_VIDEO_PX_M = 36
# A vágás bal széle a leghátsó támadó mögött ennyi m (mint a figura-lapon).
FIGURA_VIDEO_HATRA_M = 3.0
# A kulcs-pozíció felirata ennyi mp-ig látszik a kulcs-pozíció körül.
FIGURA_VIDEO_FELIRAT_S = 0.6
# A magyarázós (lepes=1) videó ennyi mp-ig áll meg minden kulcs-pozíción.
FIGURA_VIDEO_LEPES_S = 1.2
# A kodek-jelöltek sorrendben (OpenCV-háttér, fourcc): az első, amivel a
# gép tényleg ír. A H.264 a telefonon lejátszható; az mp4v mindig megy.
FIGURA_VIDEO_KODEKEK = (("MSMF", "H264"), ("AVFOUNDATION", "avc1"),
                        ("FFMPEG", "avc1"), ("FFMPEG", "mp4v"))
# A szerver ennyi elkészült videót tart meg (a várólapról többen is
# letöltik ugyanazt).
FIGURA_VIDEO_TAR_DB = 8
# Biztonsági korlát: ennél hosszabb videót nem írunk (a figura 3–12 mp a
# két állóképpel és a fal beállásával együtt is bőven belefér).
FIGURA_VIDEO_MAX_S = 30.0

_FEJ_PX = 46
_MARGO_M = 1.4
# Színek (BGR).
_PADLO = (52, 86, 120)
_VONAL = (235, 235, 235)
_HAZAI = (204, 120, 40)
_VENDEG = (60, 60, 214)
_LABDA = (40, 205, 245)
_FUTAS = (230, 170, 110)
_PASSZ = (40, 190, 220)
_FEJ_HATTER = (26, 20, 14)
_FEHER = (255, 255, 255)


def ascii_felirat(s: str) -> str:
    """A felirat ékezet nélkül (a videó Hershey-betűi csak ASCII-t
    írnak): "Védő — ő" → "Vedo - o"; a nem ASCII jel kimarad."""
    s = str(s or "").replace("—", "-").replace("–", "-").replace("→", "->")
    s = unicodedata.normalize("NFKD", s)
    return "".join(ch for ch in s if ord(ch) < 128 and ch.isprintable())


_kodek_valasztva: tuple | None = None


def _kodek(w: int, h: int, cel: Path) -> tuple:
    """Az első (háttér, fourcc), amivel a gép egy próba-kockát ténylegesen
    ír (a választás folyamatonként egyszer); végső esetben az mp4v."""
    global _kodek_valasztva
    if _kodek_valasztva is not None:
        return _kodek_valasztva
    import cv2
    import numpy as np
    proba = cel.with_name(cel.stem + ".proba.mp4")
    for hatter, fourcc in FIGURA_VIDEO_KODEKEK:
        api = getattr(cv2, "CAP_" + hatter, None)
        if api is None:
            continue
        ok = False
        try:
            iro = cv2.VideoWriter(str(proba), api,
                                  cv2.VideoWriter_fourcc(*fourcc),
                                  FIGURA_VIDEO_FPS, (w, h))
            ok = iro.isOpened()
            if ok:
                iro.write(np.zeros((h, w, 3), np.uint8))
            iro.release()
            ok = ok and proba.exists() and proba.stat().st_size > 0
        except cv2.error:
            ok = False
        finally:
            proba.unlink(missing_ok=True)
        if ok:
            _kodek_valasztva = (api, fourcc)
            return _kodek_valasztva
    _kodek_valasztva = (cv2.CAP_FFMPEG, "mp4v")
    return _kodek_valasztva


def _pont_felirat(i: int, k: int) -> str:
    if k == 3:
        return ("Kezdo", "Kozep", "Veg")[i]
    if k == 2:
        return ("Kezdo", "Veg")[i]
    return f"{i + 1}. pont"


def figura_video(utak: list, labda: list, defense, *, nev: str,
                 vedo_nev: str, cel: Path, lepes: bool = False) -> Path:
    """A figura felülnézeti videója a `cel` fájlba (MP4, mp4v).

    `utak`, `labda`, `defense`: mint a figura-lapnál (a 3D-vel azonos
    szimuláció). `lepes`: magyarázós videó — minden kulcs-pozíción
    FIGURA_VIDEO_LEPES_S-ig megáll (a felirattal). Visszaadja a `cel`-t;
    ValueError, ha nincs érvényes támadó, RuntimeError, ha a videó-írás
    nem sikerült."""
    import cv2
    import numpy as np

    from .play_simulation import setplay_3d_match

    sim, e = setplay_3d_match(utak, defense, ball=labda, name=nev,
                              defense_name=vedo_nev)
    px = FIGURA_VIDEO_PX_M
    x0 = min(COURT_LENGTH_M / 2.0,
             max(0.0, min(x for u in e["utak"] for x, _ in u)
                 - FIGURA_VIDEO_HATRA_M))
    w = int(round((COURT_LENGTH_M - x0 + 2 * _MARGO_M) * px))
    h = int(round((COURT_WIDTH_M + 2 * _MARGO_M) * px)) + _FEJ_PX
    w += w % 2
    h += h % 2

    def p(x: float, y: float) -> tuple[int, int]:
        return (int(round((x - x0 + _MARGO_M) * px)),
                int(round(_FEJ_PX + (y + _MARGO_M) * px)))

    # A háttér egyszer: padló, vonalak, a 6 és a (szaggatott) 9 m, kapu.
    alap = np.zeros((h, w, 3), np.uint8)
    alap[:] = _PADLO
    alap[:_FEJ_PX] = _FEJ_HATTER
    kozep = COURT_WIDTH_M / 2.0
    for sugar, szaggatott in ((6.0, False), (9.0, True)):
        r = int(round(sugar * px))
        for fa_y, a0, a1 in ((kozep - 1.5, 180, 270), (kozep + 1.5, 90, 180)):
            ivlepes = 8 if szaggatott else (a1 - a0)
            for a in range(a0, a1, ivlepes):
                if szaggatott and ((a - a0) // ivlepes) % 2:
                    continue
                cv2.ellipse(alap, p(COURT_LENGTH_M, fa_y), (r, r), 0, a,
                            min(a1, a + ivlepes), _VONAL, 2)
        x = COURT_LENGTH_M - sugar
        if szaggatott:
            for y in (kozep - 1.5, kozep):
                cv2.line(alap, p(x, y), p(x, y + 0.75), _VONAL, 2)
        else:
            cv2.line(alap, p(x, kozep - 1.5), p(x, kozep + 1.5), _VONAL, 2)
    # A pályán kívülre nyúló ív (a 9 m-es a széleken) le: a pálya körüli
    # sáv padlószínű; utána a vonalak (a vágás bal széle nem vonal — ott
    # a pálya folytatódik).
    (_, fent), (jobb, lent) = p(x0, 0), p(COURT_LENGTH_M, COURT_WIDTH_M)
    alap[_FEJ_PX:fent] = _PADLO
    alap[lent + 1:] = _PADLO
    alap[_FEJ_PX:, jobb + 1:] = _PADLO
    for y in (0.0, COURT_WIDTH_M):
        cv2.line(alap, p(x0, y), p(COURT_LENGTH_M, y), _VONAL, 2)
    cv2.line(alap, p(COURT_LENGTH_M, 0), p(COURT_LENGTH_M, COURT_WIDTH_M),
             _VONAL, 2)
    if x0 <= COURT_LENGTH_M / 2.0:
        cv2.line(alap, p(COURT_LENGTH_M / 2.0, 0),
                 p(COURT_LENGTH_M / 2.0, COURT_WIDTH_M), _VONAL, 2)
    cv2.rectangle(alap, p(COURT_LENGTH_M, kozep - 1.5),
                  p(COURT_LENGTH_M + 0.8, kozep + 1.5), _FEHER, 2)
    # A futások és a passzok halvány nyila a padlón (mint a 3D-ben).
    for ut in e["utak"]:
        for (ax, ay), (bx, by) in zip(ut, ut[1:]):
            if math.hypot(bx - ax, by - ay) >= 0.6:
                cv2.arrowedLine(alap, p(ax, ay), p(bx, by), _FUTAS, 2,
                                tipLength=0.08)
    for x1, y1, x2, y2 in e["passzok"]:
        cv2.arrowedLine(alap, p(x1, y1), p(x2, y2), _PASSZ, 2, tipLength=0.08)
    fej = ascii_felirat(f"{nev}  -  {vedo_nev}")[:70]
    cv2.putText(alap, fej, (12, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.62,
                _FEHER, 1, cv2.LINE_AA)

    kockak = sim.frames
    fps_sim = sim.meta.fps if sim.meta.fps > 0 else 6.0
    hossz_s = min(FIGURA_VIDEO_MAX_S, (len(kockak) - 1) / fps_sim)
    n = max(1, int(round(hossz_s * FIGURA_VIDEO_FPS)) + 1)
    kulcs = list(e.get("kulcs_t") or [])
    # A kockák ideje; magyarázós módban a kulcs-pozíciókon megállunk (a
    # kulcs-pozíció ideje ismétlődik).
    idok = []
    allj = int(round(FIGURA_VIDEO_LEPES_S * FIGURA_VIDEO_FPS)) if lepes else 0
    for k in range(n):
        t = k / FIGURA_VIDEO_FPS
        t0 = (k - 1) / FIGURA_VIDEO_FPS
        for kt in kulcs:
            if allj and t0 < kt <= t:
                idok.extend([kt] * allj)
        idok.append(t)
    sugar = max(6, int(round(0.42 * px)))

    cel = Path(cel)
    cel.parent.mkdir(parents=True, exist_ok=True)
    api, fourcc = _kodek(w, h, cel)
    iro = cv2.VideoWriter(str(cel), api, cv2.VideoWriter_fourcc(*fourcc),
                          FIGURA_VIDEO_FPS, (w, h))
    try:
        for t in idok:
            s = min(len(kockak) - 1.0, t * fps_sim)
            i = int(s)
            f = s - i
            a, b = kockak[i], kockak[min(i + 1, len(kockak) - 1)]
            bb = {(q.team, q.track_id): q for q in b.players}
            kep = alap.copy()
            for q in a.players:
                r_ = bb.get((q.team, q.track_id), q)
                x = q.x + (r_.x - q.x) * f
                y = q.y + (r_.y - q.y) * f
                szin = _HAZAI if q.team == Team.HOME else _VENDEG
                cv2.circle(kep, p(x, y), sugar, szin, -1, cv2.LINE_AA)
                cv2.circle(kep, p(x, y), sugar, _FEHER, 1, cv2.LINE_AA)
                if q.jersey_number:
                    szam = str(q.jersey_number)
                    (tw, th), _ = cv2.getTextSize(
                        szam, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                    cx, cy = p(x, y)
                    cv2.putText(kep, szam, (cx - tw // 2, cy + th // 2),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, _FEHER, 1,
                                cv2.LINE_AA)
            if a.ball is not None:
                lb = b.ball or a.ball
                bx = a.ball.x + (lb.x - a.ball.x) * f
                by = a.ball.y + (lb.y - a.ball.y) * f
                cv2.circle(kep, p(bx, by), max(4, sugar // 2), _LABDA, -1,
                           cv2.LINE_AA)
                cv2.circle(kep, p(bx, by), max(4, sugar // 2), (0, 0, 0), 1,
                           cv2.LINE_AA)
            for j, kt in enumerate(kulcs):
                if abs(t - kt) <= FIGURA_VIDEO_FELIRAT_S:
                    cimke = f"{j + 1}/{len(kulcs)} {_pont_felirat(j, len(kulcs))}"
                    (tw, _), _ = cv2.getTextSize(
                        cimke, cv2.FONT_HERSHEY_SIMPLEX, 0.62, 2)
                    cv2.putText(kep, cimke, (w - tw - 12, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.62, _LABDA, 2,
                                cv2.LINE_AA)
                    break
            iro.write(kep)
    finally:
        iro.release()
    if not cel.exists() or cel.stat().st_size == 0:
        raise RuntimeError(f"a figura-videó írása nem sikerült ({fourcc})")
    return cel
