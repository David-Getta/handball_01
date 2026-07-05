/// Homográfia-matematika Dart-ban — a backend _homography.py tükre.
///
/// A kalibráló képernyőhöz: 4 pálya-sarok (méter) ↔ 4 kép-pont (pixel) párból
/// kiszámol egy 3x3 homográfiát, amivel a pálya-modellt a képre lehet vetíteni
/// (élő előnézet húzás közben), illetve a kép-pontokat pálya-koordinátára váltani.
library;

/// Megold egy A·x = b lineáris rendszert (négyzetes A), Gauss-eliminációval.
List<double> _solve(List<List<double>> a, List<double> b) {
  final n = a.length;
  final m = [for (int i = 0; i < n; i++) [...a[i], b[i]]];
  for (int col = 0; col < n; col++) {
    int piv = col;
    for (int r = col + 1; r < n; r++) {
      if (m[r][col].abs() > m[piv][col].abs()) piv = r;
    }
    final tmp = m[col]; m[col] = m[piv]; m[piv] = tmp;
    for (int r = col + 1; r < n; r++) {
      final f = m[r][col] / m[col][col];
      for (int c = col; c <= n; c++) {
        m[r][c] -= f * m[col][c];
      }
    }
  }
  final x = List<double>.filled(n, 0.0);
  for (int row = n - 1; row >= 0; row--) {
    double s = m[row][n];
    for (int c = row + 1; c < n; c++) {
      s -= m[row][c] * x[c];
    }
    x[row] = s / m[row][row];
  }
  return x;
}

/// A H 3x3 homográfia `src` -> `dst` pont-párokból (legalább 4).
List<List<double>> homographyFromPoints(List<List<double>> src, List<List<double>> dst) {
  final rows = <List<double>>[];
  final rhs = <double>[];
  for (int i = 0; i < src.length; i++) {
    final px = src[i][0], py = src[i][1], x = dst[i][0], y = dst[i][1];
    rows.add([px, py, 1, 0, 0, 0, -px * x, -py * x]); rhs.add(x);
    rows.add([0, 0, 0, px, py, 1, -px * y, -py * y]); rhs.add(y);
  }
  final ata = [for (int i = 0; i < 8; i++) List<double>.filled(8, 0.0)];
  final atb = List<double>.filled(8, 0.0);
  for (int i = 0; i < rows.length; i++) {
    for (int a = 0; a < 8; a++) {
      atb[a] += rows[i][a] * rhs[i];
      for (int b = 0; b < 8; b++) {
        ata[a][b] += rows[i][a] * rows[i][b];
      }
    }
  }
  final h = _solve(ata, atb);
  return [
    [h[0], h[1], h[2]],
    [h[3], h[4], h[5]],
    [h[6], h[7], 1.0],
  ];
}

/// Egy pontra (px, py) alkalmazza a H homográfiát (perspektív osztással).
List<double> applyHomography(List<List<double>> h, double px, double py) {
  final xs = h[0][0] * px + h[0][1] * py + h[0][2];
  final ys = h[1][0] * px + h[1][1] * py + h[1][2];
  final w = h[2][0] * px + h[2][1] * py + h[2][2];
  if (w.abs() < 1e-12) return [px, py];
  return [xs / w, ys / w];
}
