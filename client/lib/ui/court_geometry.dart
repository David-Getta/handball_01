/// Pálya-geometria — a szabálykönyvi méretek és a 6 m-es kapuelőtér alakja.
///
/// A felülnézeti rajzhoz méteres koordinátákban dolgozunk (a backend is így ad
/// pozíciókat), és a rajzoló skálázza pixelre. A méretek a docs/RULES.md-ből.
library;

import "dart:math" as math;
import "dart:ui";

const double courtLength = 40.0; // x tengely (hosszú)
const double courtWidth = 20.0; // y tengely (rövid)
const double goalWidth = 3.0; // kapu szélessége → kapufák y=8.5 és y=11.5
const double goalAreaRadius = 6.0; // 6 m-es kapuelőtér sugár

/// A kapuelőtér (6 m-es zóna) határoló pontjai MÉTERBEN, az adott oldalra.
///
/// [leftSide] true esetén a bal kapu (x=0), false esetén a jobb (x=40).
/// A határ: alsó negyedkör (a lenti kapufa körül) → 3 m egyenes → felső negyedkör.
/// A köríveket [segments] szakasszal mintavételezzük, hogy sima legyen.
List<Offset> goalAreaBoundary({required bool leftSide, int segments = 16}) {
  final cy = courtWidth / 2.0; // 10 m
  final half = goalWidth / 2.0; // 1.5 m
  final lowerPostY = cy - half; // 8.5
  final upperPostY = cy + half; // 11.5
  final pts = <Offset>[];

  // Alsó negyedkör a lenti kapufa (x=0, y=8.5) körül: a (0, 2.5) ponttól a (6, 8.5)-ig.
  for (int i = 0; i <= segments; i++) {
    final theta = (math.pi / 2) * (i / segments); // 0..90°
    final x = goalAreaRadius * math.sin(theta);
    final y = lowerPostY - goalAreaRadius * math.cos(theta);
    pts.add(Offset(x, y));
  }
  // 3 m-es egyenes szakasz: (6, 8.5) -> (6, 11.5).
  pts.add(Offset(goalAreaRadius, lowerPostY));
  pts.add(Offset(goalAreaRadius, upperPostY));
  // Felső negyedkör a fenti kapufa (x=0, y=11.5) körül: (6, 11.5) -> (0, 17.5).
  for (int i = 0; i <= segments; i++) {
    final theta = (math.pi / 2) * (i / segments);
    final x = goalAreaRadius * math.cos(theta);
    final y = upperPostY + goalAreaRadius * math.sin(theta);
    pts.add(Offset(x, y));
  }

  // Jobb oldalra tükrözzük (x -> 40 - x).
  if (!leftSide) {
    return pts.map((p) => Offset(courtLength - p.dx, p.dy)).toList();
  }
  return pts;
}
