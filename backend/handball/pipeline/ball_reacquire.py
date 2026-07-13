"""
[B2] Labda-visszaszerzés — célzott újrakeresés, amikor a labda elveszett.

A kis, gyors labda a leggyengébb pontja a detektálásnak: a teljes képen
futó menetből gyakran kimarad. Amikor kimarad, a labda várható helye a
korábbi mozgásából jól becsülhető — ott egy KIS kivágásban újrakeresve a
labda a kivágás felbontásán sokkal nagyobbnak látszik, így az esély a
megtalálására jelentősen nő. Ez a modul a TISZTA logika (előrejelzés,
kivágás-kijelölés, koordináta-visszavetítés) — a tényleges detektor-hívást
a feldolgozó (process_video) adja hozzá, így modell nélkül tesztelhető.

Költség-korlát: csak akkor próbálkozunk, amíg a kiesés friss (max_gap
kockán belül) — régen látott labdánál az extrapoláció már csak találgatás.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BallReacquirer:
    """A labda-előzmények követése + újrakereső kivágás kijelölése.

    - roi_px:   a kereső-kivágás oldalhossza pixelben (a kivágásban a
                labda relatíve nagy lesz → könnyebb detektálni).
    - max_gap:  legfeljebb ennyi FELDOLGOZOTT kockányi kiesésig keresünk
                (utána az előrejelzés megbízhatatlan).
    """
    roi_px: int = 320
    max_gap: int = 20
    _history: list = field(default_factory=list)  # (t, x, y) — pixelben

    def note(self, t: int, xy: tuple | None) -> None:
        """Egy kocka eredményének rögzítése (xy=None, ha nem volt labda)."""
        if xy is not None:
            self._history.append((t, float(xy[0]), float(xy[1])))
            if len(self._history) > 8:
                self._history.pop(0)

    def predict(self, t: int) -> tuple[float, float] | None:
        """A labda várható helye a t kockán, vagy None, ha nincs alapja.

        Lineáris extrapoláció az utolsó két észlelésből; egyetlen észlelésnél
        az utolsó ismert hely (a labda ritkán teleportál)."""
        if not self._history:
            return None
        t_last, x_last, y_last = self._history[-1]
        gap = t - t_last
        if gap <= 0 or gap > self.max_gap:
            return None
        if len(self._history) == 1:
            return (x_last, y_last)
        t_prev, x_prev, y_prev = self._history[-2]
        dt = max(1, t_last - t_prev)
        vx = (x_last - x_prev) / dt
        vy = (y_last - y_prev) / dt
        return (x_last + vx * gap, y_last + vy * gap)

    def roi_for(self, t: int, width: int, height: int) -> tuple | None:
        """Az újrakereső kivágás (x1, y1, x2, y2) a t kockára, a képbe
        vágva — vagy None, ha nincs értelme keresni."""
        p = self.predict(t)
        if p is None:
            return None
        half = self.roi_px / 2.0
        x1 = int(max(0, min(p[0] - half, width - self.roi_px)))
        y1 = int(max(0, min(p[1] - half, height - self.roi_px)))
        x2 = int(min(width, x1 + self.roi_px))
        y2 = int(min(height, y1 + self.roi_px))
        if x2 - x1 < 32 or y2 - y1 < 32:
            return None  # túl kicsi kép — nincs értelme
        return (x1, y1, x2, y2)

    @staticmethod
    def map_back(roi: tuple, x: float, y: float) -> tuple[float, float]:
        """A kivágásban talált pozíció visszavetítése a teljes képre."""
        return (roi[0] + x, roi[1] + y)
