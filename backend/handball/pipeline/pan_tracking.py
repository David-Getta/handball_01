"""
[Pásztázás-követés] — a kamera jobbra-balra mozgásának kompenzálása.

A probléma: a pálya-kalibráció (4 sarok → homográfia) EGY képkockára érvényes.
A rögzített helyről PÁSZTÁZÓ kamera képe elfordul, így a kalibráció elcsúszik —
a játékosok "odébb csúsznának" a felülnézeten, pedig csak a kamera mozgott.

A megoldás: képkockáról képkockára megbecsüljük a KAMERA mozgását (globális
kép-elmozdulás), és a detektált pontokat előbb "visszaforgatjuk" a kalibráció
alap-képkockájának koordinátáiba, csak utána vetítjük a pályára:

    pálya = H0( G(t) · pixel )      ahol
    H0   : alap-képkocka → pálya (a 4 sarokból számolt homográfia),
    G(t) : aktuális képkocka → alap-képkocka (a halmozott kameramozgás).

A G(t)-t ritka jellemzőpontokból számoljuk (Shi–Tomasi sarkok + Lucas–Kanade
optikai áramlás), majd RANSAC-os hasonlósági transzformációt illesztünk. A mozgó
játékosok a pontok kisebbsége, a RANSAC kiszórja őket — a többség (pálya, lelátó,
falak) a kamera mozgását adja. Ha nincs elég pont (pl. sötét kép), az előző
állapotot tartjuk (a mozgás becslése kimarad, nem törik el a lánc).
"""

from __future__ import annotations


class PanTracker:
    """A halmozott kameramozgás (aktuális képkocka → alap-képkocka) becslése.

    Használat: minden FELDOLGOZOTT képkockára hívd meg az update(gray)-t (szürke
    kép), az eredmény a 3x3-as G(t) mátrix (listák listája). Az apply(H, x, y)
    segéddel egy pixel visszavetíthető az alap-képkocka koordinátáiba.
    """

    # Hangolható paraméterek: elegendő pont a stabil becsléshez, de gyors maradjon.
    MAX_CORNERS = 400
    QUALITY = 0.01
    MIN_DISTANCE = 8
    MIN_POINTS = 12  # ennél kevesebb követett pontból nem becslünk mozgást

    def __init__(self):
        self._prev_gray = None
        # G: aktuális → alap (3x3, numpy) — induláskor egység (nincs elmozdulás).
        self._G = None

    def update(self, gray):
        """Feldolgoz egy új (szürkeárnyalatos) képkockát; visszaadja G(t)-t.

        A visszatérési érték 3x3-as beágyazott lista (JSON-barát), ami az AKTUÁLIS
        képkocka pixeleit az ALAP (első) képkocka koordinátáiba viszi.
        """
        import cv2
        import numpy as np

        if self._G is None:
            self._G = np.eye(3, dtype=np.float64)

        if self._prev_gray is not None:
            # 1) Sarokpontok az ELŐZŐ képen (minden lépésben újra — robusztus).
            p0 = cv2.goodFeaturesToTrack(
                self._prev_gray, self.MAX_CORNERS, self.QUALITY, self.MIN_DISTANCE)
            if p0 is not None and len(p0) >= self.MIN_POINTS:
                # 2) A pontok követése az aktuális képre (Lucas–Kanade).
                p1, st, _err = cv2.calcOpticalFlowPyrLK(
                    self._prev_gray, gray, p0, None)
                if p1 is not None:
                    good = st.reshape(-1) == 1
                    if int(good.sum()) >= self.MIN_POINTS:
                        # 3) Hasonlósági transzformáció (elt+forg+skála) RANSAC-kal:
                        #    aktuális → előző. A mozgó játékosokat a RANSAC kiszórja.
                        M, _inl = cv2.estimateAffinePartial2D(
                            p1[good], p0[good], method=cv2.RANSAC,
                            ransacReprojThreshold=3.0)
                        if M is not None:
                            g = np.vstack([M, [0.0, 0.0, 1.0]])  # 2x3 → 3x3
                            # 4) Halmozás: aktuális→előző→…→alap.
                            self._G = self._G @ g

        self._prev_gray = gray
        return [[float(v) for v in row] for row in self._G]

    @property
    def translation(self):
        """A halmozott (x, y) eltolás pixelben — diagnosztikához/naplóhoz."""
        if self._G is None:
            return (0.0, 0.0)
        return (float(self._G[0][2]), float(self._G[1][2]))


def apply_h(h, x, y):
    """Egy 3x3-as homográfia/transzformáció alkalmazása egy (x, y) pontra.

    Beágyazott listákkal is működik (a PanTracker kimenetével), perspektív
    osztással. Ha a nevező ~0, az eredeti pontot adja vissza.
    """
    xs = h[0][0] * x + h[0][1] * y + h[0][2]
    ys = h[1][0] * x + h[1][1] * y + h[1][2]
    w = h[2][0] * x + h[2][1] * y + h[2][2]
    if abs(w) < 1e-12:
        return (x, y)
    return (xs / w, ys / w)
