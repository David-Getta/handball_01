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
const double freeThrowRadius = 9.0; // 9 m-es (szaggatott) szabaddobási vonal
const double sevenMeterX = 7.0; // a hetes-vonal távolsága a gólvonaltól
const double sevenMeterHalfLen = 0.5; // a hetes-vonal fél hossza (1 m-es vonal)
const double keeperLineX = 4.0; // 4 m-es kapus-vonal a gólvonaltól
const double keeperLineHalfLen = 0.075; // 15 cm-es vonal fele

/// Méter↔képernyő transzformáció — a felülnézeti pálya egységes leképezése.
///
/// Ugyanazt a skálát/eltolást adja, amit a rajzolók használnak, hogy a kirajzolás
/// és az érintés-találat (a figura-tervezőben) pontosan egyezzen.
class CourtTransform {
  final double scale;
  final double originX;
  final double originY;
  const CourtTransform(this.scale, this.originX, this.originY);

  factory CourtTransform.fit(Size size, {double margin = 28}) {
    final usableW = size.width - 2 * margin;
    final usableH = size.height - 2 * margin;
    final scale = math.min(usableW / courtLength, usableH / courtWidth);
    final ox = (size.width - courtLength * scale) / 2;
    final oy = (size.height - courtWidth * scale) / 2;
    return CourtTransform(scale, ox, oy);
  }

  Offset toScreen(double mx, double my) => Offset(originX + mx * scale, originY + my * scale);
  Offset toCourt(double px, double py) => Offset((px - originX) / scale, (py - originY) / scale);
}

/// A kapuelőtér (6 m-es zóna) határoló pontjai MÉTERBEN, az adott oldalra.
///
/// [leftSide] true esetén a bal kapu (x=0), false esetén a jobb (x=40).
/// A határ: alsó negyedkör (a lenti kapufa körül) → 3 m egyenes → felső negyedkör.
/// A köríveket [segments] szakasszal mintavételezzük, hogy sima legyen.
List<Offset> goalAreaBoundary({required bool leftSide, int segments = 16}) =>
    _postArcBoundary(
        radius: goalAreaRadius, leftSide: leftSide, segments: segments);

/// A 9 m-es SZABADDOBÁSI vonal pontjai — ugyanaz az alak, 9 m sugárral.
///
/// A szabálykönyvben ez SZAGGATOTT vonal (a rajzoló így is húzza meg): a
/// szabaddobást innen kell végrehajtani, és a védekező falnak is ez a
/// vonatkoztatási vonala — a felülnézeti képen ettől lesz "igazi" pálya.
List<Offset> freeThrowBoundary({required bool leftSide, int segments = 16}) =>
    _postArcBoundary(
        radius: freeThrowRadius, leftSide: leftSide, segments: segments);

/// A kapufák köré húzott, `radius` sugarú határvonal (a 6 m-es és a 9 m-es
/// vonal alakja azonos, csak a sugár más).
List<Offset> _postArcBoundary({
  required double radius,
  required bool leftSide,
  int segments = 16,
}) {
  final cy = courtWidth / 2.0; // 10 m
  final half = goalWidth / 2.0; // 1.5 m
  final lowerPostY = cy - half; // 8.5
  final upperPostY = cy + half; // 11.5
  final pts = <Offset>[];

  // Alsó negyedkör a lenti kapufa (x=0, y=8.5) körül.
  for (int i = 0; i <= segments; i++) {
    final theta = (math.pi / 2) * (i / segments); // 0..90°
    final x = radius * math.sin(theta);
    final y = lowerPostY - radius * math.cos(theta);
    pts.add(Offset(x, y));
  }
  // 3 m-es egyenes szakasz a két negyedkör között.
  pts.add(Offset(radius, lowerPostY));
  pts.add(Offset(radius, upperPostY));
  // Felső negyedkör a fenti kapufa (x=0, y=11.5) körül.
  for (int i = 0; i <= segments; i++) {
    final theta = (math.pi / 2) * (i / segments);
    final x = radius * math.cos(theta);
    final y = upperPostY + radius * math.sin(theta);
    pts.add(Offset(x, y));
  }

  // Jobb oldalra tükrözzük (x -> 40 - x).
  if (!leftSide) {
    return pts.map((p) => Offset(courtLength - p.dx, p.dy)).toList();
  }
  return pts;
}
