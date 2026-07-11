"""
Homográfia-matematika — TISZTA Python (numpy/OpenCV nélkül).

Egy homográfia egy 3x3-as mátrix (H), amely egy SÍK pontjait egy másik sík
pontjaira képezi perspektivikusan. Nálunk: kép-pixel (px, py) -> pálya-méter (X, Y).

A leképezés homogén koordinátában:
    [X']     [h11 h12 h13]   [px]
    [Y']  =  [h21 h22 h23] * [py]
    [W ]     [h31 h32 h33]   [ 1 ]
majd a valós koordináta: X = X'/W, Y = Y'/W (perspektív osztás).

A H-t pont-párokból becsüljük (kép<->pálya). Minden pár 2 egyenletet ad, 8
ismeretlenre (h33-at 1-re rögzítjük), tehát legalább 4 pár kell. Több párnál
legkisebb-négyzetes megoldást adunk (normálegyenletek).

Ez a modul szándékosan függőségmentes, hogy a kalibráció magja mindig fusson és
egyszerű szintetikus pontokkal tesztelhető legyen. (A valódi videós illesztés
később jöhet OpenCV-vel, de a koordináta-átváltás matematikája ez.)
"""

from __future__ import annotations

Matrix = list[list[float]]


def solve_linear(a: Matrix, b: list[float]) -> list[float]:
    """Megold egy A x = b lineáris egyenletrendszert (négyzetes A).

    Gauss-elimináció részleges főelem-választással (partial pivoting), ami a
    numerikus stabilitást javítja. Az `a` és `b` másolaton dolgozunk, hogy a
    bemenetet ne módosítsuk.

    Visszaadja az x megoldásvektort. ValueError, ha a rendszer szingulárisnak tűnik.
    """
    n = len(a)
    # Bővített mátrix [A | b] másolata.
    m = [list(row) + [b[i]] for i, row in enumerate(a)]

    for col in range(n):
        # 1) Főelem keresése: a legnagyobb abszolút értékű elem az oszlopban.
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-12:
            raise ValueError("szinguláris rendszer — a pontok elfajultak (pl. egy vonalban)")
        # Sorcsere, hogy a főelem a helyére kerüljön.
        m[col], m[pivot] = m[pivot], m[col]

        # 2) Az oszlop alatti elemek kinullázása.
        for r in range(col + 1, n):
            factor = m[r][col] / m[col][col]
            for c in range(col, n + 1):
                m[r][c] -= factor * m[col][c]

    # 3) Visszahelyettesítés alulról felfelé.
    x = [0.0] * n
    for row in range(n - 1, -1, -1):
        s = m[row][n] - sum(m[row][c] * x[c] for c in range(row + 1, n))
        x[row] = s / m[row][row]
    return x


def homography_from_points(src: list[tuple[float, float]],
                           dst: list[tuple[float, float]]) -> Matrix:
    """A H 3x3 homográfiát becsli `src` (kép) -> `dst` (pálya) pont-párokból.

    Legalább 4 pár kell. Minden (px,py)->(X,Y) pár két egyenletet ad:
        h11*px + h12*py + h13 - h31*px*X - h32*py*X = X
        h21*px + h22*py + h23 - h31*px*Y - h32*py*Y = Y
    az ismeretlenek: [h11,h12,h13, h21,h22,h23, h31,h32], h33 := 1.

    Több párnál legkisebb-négyzetes megoldás a normálegyenletekkel (MᵀM x = Mᵀr).
    """
    if len(src) != len(dst):
        raise ValueError("a kép- és pálya-pontok száma nem egyezik")
    if len(src) < 4:
        raise ValueError("legalább 4 pont-pár kell a homográfiához")

    # M (2N x 8) és r (2N) felépítése a fenti egyenletek szerint.
    rows: Matrix = []
    rhs: list[float] = []
    for (px, py), (X, Y) in zip(src, dst):
        rows.append([px, py, 1, 0, 0, 0, -px * X, -py * X])
        rhs.append(X)
        rows.append([0, 0, 0, px, py, 1, -px * Y, -py * Y])
        rhs.append(Y)

    # Normálegyenletek: A = MᵀM (8x8), b = Mᵀr (8). Ezt oldjuk meg.
    n_unknowns = 8
    ata: Matrix = [[0.0] * n_unknowns for _ in range(n_unknowns)]
    atb: list[float] = [0.0] * n_unknowns
    for i in range(len(rows)):
        ri = rows[i]
        bi = rhs[i]
        for a_idx in range(n_unknowns):
            atb[a_idx] += ri[a_idx] * bi
            ra = ri[a_idx]
            row_a = ata[a_idx]
            for b_idx in range(n_unknowns):
                row_a[b_idx] += ra * ri[b_idx]

    h = solve_linear(ata, atb)
    # Vissza 3x3 alakra, h33 = 1.
    return [
        [h[0], h[1], h[2]],
        [h[3], h[4], h[5]],
        [h[6], h[7], 1.0],
    ]


def invert_3x3(h: Matrix) -> Matrix:
    """Egy 3x3-as mátrix inverze (adjungált / determináns módszerrel).

    A kettős térfél-kalibrációnál kell: a második kalibráció képkockájáról az
    ALAP képkockára visszavezetéshez a pásztázás-mátrix inverzét használjuk.
    ValueError, ha a mátrix szinguláris.
    """
    a, b, c = h[0]
    d, e, f = h[1]
    g, i, j = h[2]
    det = a * (e * j - f * i) - b * (d * j - f * g) + c * (d * i - e * g)
    if abs(det) < 1e-12:
        raise ValueError("szinguláris mátrix — nem invertálható")
    return [
        [(e * j - f * i) / det, (c * i - b * j) / det, (b * f - c * e) / det],
        [(f * g - d * j) / det, (a * j - c * g) / det, (c * d - a * f) / det],
        [(d * i - e * g) / det, (b * g - a * i) / det, (a * e - b * d) / det],
    ]


def compose(h2: Matrix, h1: Matrix) -> Matrix:
    """Mátrix-szorzás: a visszaadott H a h1, MAJD h2 leképezés (H = h2·h1)."""
    return [
        [sum(h2[r][k] * h1[k][c] for k in range(3)) for c in range(3)]
        for r in range(3)
    ]


def apply_homography(h: Matrix, px: float, py: float) -> tuple[float, float]:
    """Egy pontra (px, py) alkalmazza a H homográfiát, perspektív osztással.

    Visszaadja a leképezett (X, Y) pontot. ValueError, ha a W (harmadik) komponens
    nullához közeli (a pont a "végtelenbe" képződne — kalibrációs hiba jele).
    """
    xs = h[0][0] * px + h[0][1] * py + h[0][2]
    ys = h[1][0] * px + h[1][1] * py + h[1][2]
    w = h[2][0] * px + h[2][1] * py + h[2][2]
    if abs(w) < 1e-12:
        raise ValueError("érvénytelen leképezés (W ~ 0)")
    return xs / w, ys / w
