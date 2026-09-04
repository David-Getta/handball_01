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
    G(t) : aktuális képkocka → alap-képkocka (a kameramozgás).

KÉT becslő dolgozik együtt:

1. LÁNC (kockáról kockára): Shi–Tomasi sarkok + Lucas–Kanade optikai áramlás,
   RANSAC-os hasonlósági transzformáció, a lépések összeszorozva. Gyors és
   minden kockán működik — de a sok kis lépés hibája ÖSSZEADÓDIK: mire a
   kamera visszafordul a kalibrált állásba, a becslés már nem az egység,
   hanem elcsúszott (drift).

2. HORGONY (a kalibrált alap-kockához illesztés): az alap-kocka ORB
   jellemzőpontjait eltároljuk, és rendszeresen a FUTÓ kockát közvetlenül
   ehhez illesztjük (Lowe-arányos párosítás + RANSAC homográfia). Ez
   abszolút mérés: nem halmozódik benne hiba. Ahol a horgonyhoz nincs elég
   egyezés (távoli svenk, takarás, sötét kép), a lánc hidal át, és a
   következő sikeres horgonynál a becslés visszaáll. Hogy a távolra
   elforduló kamerának is legyen mihez mérnie, a sikeresen horgonyzott,
   egymástól elég távoli nézetekből KULCS-HORGONYOK is készülnek (a saját,
   horgonyból származó G-jükkel) — a futó kocka mindig a legközelebbi
   pár horgonyhoz próbál illeszkedni.

A MOZGÓ EMBEREK (a detektált játékos-dobozok) mindkét becslőnél kimaszkolva:
csak az álló háttér — pálya, lelátó, falak — adja a kamera mozgását. (A
RANSAC a kisebbséget amúgy is kiszórná, de a tömörülésben a játékosok a
képpontok jelentős részét adhatják.)
"""

from __future__ import annotations


class PanTracker:
    """A kameramozgás (aktuális képkocka → alap-képkocka) becslése.

    Használat: minden FELDOLGOZOTT képkockára hívd meg az update(gray,
    exclude=dobozok)-at (szürke kép + a mozgó objektumok pixel-dobozai),
    az eredmény a 3x3-as G(t) mátrix (listák listája). Az apply_h(G, x, y)
    segéddel egy pixel visszavetíthető az alap-képkocka koordinátáiba.
    Az ALAP = az első feldolgozott kocka — a kalibrációt ehhez kell felvenni.
    """

    # Lánc: elegendő pont a stabil becsléshez, de gyors maradjon.
    MAX_CORNERS = 400
    QUALITY = 0.01
    MIN_DISTANCE = 8
    MIN_POINTS = 12  # ennél kevesebb követett pontból nem becslünk mozgást
    # Horgony: ennyi FELDOLGOZOTT kockánként próbálunk a horgonyokhoz
    # illeszteni (a lánc a köztes kockákat viszi); ennyi RANSAC-belső
    # egyezés kell egy elfogadott horgonyzáshoz; a Lowe-arány a párosításhoz;
    # ennél nagyobb skála-változás nem svenk (zoom vagy hibás illesztés).
    ANCHOR_EVERY = 5
    ANCHOR_MIN_INLIERS = 25
    ANCHOR_ORB_FEATURES = 1500
    ANCHOR_RATIO = 0.75
    ANCHOR_MAX_SCALE = 1.6
    # Kulcs-horgonyok: ennyi px eltolás-távolságra a meglévőktől készül új;
    # legfeljebb ennyi horgony; a futó kocka a legközelebbi ennyihez próbál.
    ANCHOR_SPACING_PX = 150.0
    MAX_ANCHORS = 12
    ANCHOR_TRY_NEAREST = 3

    def __init__(self, anchor: bool = True):
        self._prev_gray = None
        # G: aktuális → alap (3x3, numpy) — induláskor egység (nincs elmozdulás).
        self._G = None
        self._anchor = anchor
        self._orb = None
        self._bf = None
        # [(pontok Nx2 float32, leírók, G_horgony→alap numpy)]
        self._anchors: list = []
        self._n = 0
        # Diagnosztika: hány kockán mi vitte a becslést.
        self.stats = {"frames": 0, "anchored": 0, "chain": 0, "held": 0,
                      "anchors": 0}

    # ------------------------------------------------------------ segédek

    @staticmethod
    def _mask_of(gray, exclude):
        """255 = használható háttér, 0 = mozgó objektum (kimaszkolva)."""
        import numpy as np
        if not exclude:
            return None
        h, w = gray.shape[:2]
        mask = np.full((h, w), 255, np.uint8)
        for (x1, y1, x2, y2) in exclude:
            xa, xb = max(0, int(x1)), min(w, int(x2))
            ya, yb = max(0, int(y1)), min(h, int(y2))
            if xb > xa and yb > ya:
                mask[ya:yb, xa:xb] = 0
        return mask

    def _orb_of(self, gray, mask):
        """ORB pontok és leírók (Nx2, NxD) — vagy (None, None), ha kevés."""
        import cv2
        import numpy as np
        if self._orb is None:
            self._orb = cv2.ORB_create(self.ANCHOR_ORB_FEATURES)
            self._bf = cv2.BFMatcher(cv2.NORM_HAMMING)
        kp, des = self._orb.detectAndCompute(gray, mask)
        if des is None or len(kp) < self.ANCHOR_MIN_INLIERS:
            return None, None
        pts = np.float32([k.pt for k in kp])
        return pts, des

    def _fit_to_anchor(self, pts, des, anchor):
        """Aktuális → horgony homográfia RANSAC-kal, vagy None."""
        import cv2
        import numpy as np
        a_pts, a_des, _ = anchor
        try:
            parok = self._bf.knnMatch(des, a_des, k=2)
        except cv2.error:
            return None
        jo = [m for m, n in (p for p in parok if len(p) == 2)
              if m.distance < self.ANCHOR_RATIO * n.distance]
        if len(jo) < self.ANCHOR_MIN_INLIERS:
            return None
        src = np.float32([pts[m.queryIdx] for m in jo]).reshape(-1, 1, 2)
        dst = np.float32([a_pts[m.trainIdx] for m in jo]).reshape(-1, 1, 2)
        H, inl = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
        if H is None or inl is None or int(inl.sum()) < self.ANCHOR_MIN_INLIERS:
            return None
        if abs(H[2][2]) < 1e-9:
            return None
        H = H / H[2][2]
        # Józanság: egy svenk nem zoom és nem tükrözés.
        det = H[0][0] * H[1][1] - H[0][1] * H[1][0]
        if det <= 0:
            return None
        skala = float(np.sqrt(det))
        if not (1.0 / self.ANCHOR_MAX_SCALE <= skala <= self.ANCHOR_MAX_SCALE):
            return None
        return H

    def _try_anchor(self, gray, mask):
        """Illesztés a legközelebbi horgonyokhoz; siker esetén G frissül."""
        import numpy as np
        pts, des = self._orb_of(gray, mask)
        if pts is None:
            return False
        # A mostani becsült eltoláshoz legközelebbi horgonyok előre.
        tx, ty = float(self._G[0][2]), float(self._G[1][2])

        def _tav(a):
            g = a[2]
            return (float(g[0][2]) - tx) ** 2 + (float(g[1][2]) - ty) ** 2

        for anchor in sorted(self._anchors, key=_tav)[: self.ANCHOR_TRY_NEAREST]:
            H = self._fit_to_anchor(pts, des, anchor)
            if H is None:
                continue
            self._G = anchor[2] @ H  # aktuális → horgony → alap
            self.stats["anchored"] += 1
            self._maybe_add_anchor(pts, des)
            return True
        return False

    def _maybe_add_anchor(self, pts, des):
        """Új kulcs-horgony, ha a nézet elég messze van a meglévőktől."""
        if len(self._anchors) >= self.MAX_ANCHORS:
            return
        tx, ty = float(self._G[0][2]), float(self._G[1][2])
        for _, _, g in self._anchors:
            d = ((float(g[0][2]) - tx) ** 2 + (float(g[1][2]) - ty) ** 2) ** 0.5
            if d < self.ANCHOR_SPACING_PX:
                return
        self._anchors.append((pts, des, self._G.copy()))
        self.stats["anchors"] = len(self._anchors)

    # ------------------------------------------------------------ fő hívás

    def update(self, gray, exclude=None):
        """Feldolgoz egy új (szürkeárnyalatos) képkockát; visszaadja G(t)-t.

        `exclude`: a mozgó objektumok (detektált emberek) pixel-dobozai
        [(x1, y1, x2, y2), ...] — ezeket egyik becslő sem használja. A
        visszatérési érték 3x3-as beágyazott lista (JSON-barát), ami az
        AKTUÁLIS képkocka pixeleit az ALAP (első) képkocka koordinátáiba viszi.
        """
        import cv2
        import numpy as np

        mask = self._mask_of(gray, exclude)
        self.stats["frames"] += 1
        if self._G is None:
            self._G = np.eye(3, dtype=np.float64)
            if self._anchor:
                pts, des = self._orb_of(gray, mask)
                if pts is not None:
                    self._anchors.append((pts, des, np.eye(3)))
                    self.stats["anchors"] = 1
            self._prev_gray = gray
            self._n += 1
            return [[float(v) for v in row] for row in self._G]

        # 1) LÁNC: sarokpontok az ELŐZŐ képen, követés az aktuálisra,
        #    hasonlósági transzformáció RANSAC-kal, halmozás.
        lanc_ok = False
        p0 = cv2.goodFeaturesToTrack(
            self._prev_gray, self.MAX_CORNERS, self.QUALITY,
            self.MIN_DISTANCE, mask=mask)
        if p0 is not None and len(p0) >= self.MIN_POINTS:
            p1, st, _err = cv2.calcOpticalFlowPyrLK(
                self._prev_gray, gray, p0, None)
            if p1 is not None:
                good = st.reshape(-1) == 1
                if int(good.sum()) >= self.MIN_POINTS:
                    M, _inl = cv2.estimateAffinePartial2D(
                        p1[good], p0[good], method=cv2.RANSAC,
                        ransacReprojThreshold=3.0)
                    if M is not None:
                        g = np.vstack([M, [0.0, 0.0, 1.0]])  # 2x3 → 3x3
                        self._G = self._G @ g   # aktuális→előző→…→alap
                        lanc_ok = True

        # 2) HORGONY: rendszeresen, vagy ha a lánc elakadt — az abszolút
        #    mérés felülírja a halmozott becslést.
        horgony_ok = False
        if self._anchor and self._anchors and (
                self._n % self.ANCHOR_EVERY == 0 or not lanc_ok):
            horgony_ok = self._try_anchor(gray, mask)
        if not horgony_ok:
            if lanc_ok:
                self.stats["chain"] += 1
            else:
                self.stats["held"] += 1  # nincs becslés: az előző marad

        self._prev_gray = gray
        self._n += 1
        return [[float(v) for v in row] for row in self._G]

    @property
    def translation(self):
        """A halmozott (x, y) eltolás pixelben — diagnosztikához/naplóhoz."""
        if self._G is None:
            return (0.0, 0.0)
        return (float(self._G[0][2]), float(self._G[1][2]))

    def summary(self) -> str:
        """Egy soros magyar összegzés a naplóba."""
        s = self.stats
        return (f"pásztázás-követés: {s['frames']} kocka — horgonyzott "
                f"{s['anchored']}, lánccal vitt {s['chain']}, tartott "
                f"{s['held']}; horgonyok: {s['anchors']}")


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
