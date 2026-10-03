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

/// A cserevonal jele az oldalvonalon: a félpályától ennyire (méter).
const double substitutionLineX = 4.5;

/// Lövés-mérés egy pálya-pontból — a backend `court3d.shot_geometry`
/// TÜKRE (ugyanazok a képletek; a backend teszt a böngészős tükröt
/// node-dal veti össze, ezt a forrás-őr nézi).
class ShotGeometry {
  final bool leftGoal; // a bal (x=0) kapura mérünk
  final double goalX;
  final double distance; // a kapu közepétől (m)
  final double postDistance; // a kapufák közti szakasztól (m) — 6/9 m mércéje
  final double angleDeg; // a két kapufa között látott szög
  final String zone; // "kapuelőtér" / "6–9 m" / "9 m-en túl"
  const ShotGeometry(this.leftGoal, this.goalX, this.distance,
      this.postDistance, this.angleDeg, this.zone);
}

ShotGeometry shotGeometry(double x, double y, {bool? leftGoal}) {
  final bal = leftGoal ?? x <= courtLength / 2;
  final gx = bal ? 0.0 : courtLength;
  final cy = courtWidth / 2;
  final y1 = cy - goalWidth / 2, y2 = cy + goalWidth / 2;
  final v1x = gx - x, v1y = y1 - y, v2x = gx - x, v2y = y2 - y;
  final n1 = math.sqrt(v1x * v1x + v1y * v1y);
  final n2 = math.sqrt(v2x * v2x + v2y * v2y);
  var szog = 180.0;
  if (n1 >= 1e-9 && n2 >= 1e-9) {
    final c = ((v1x * v2x + v1y * v2y) / (n1 * n2)).clamp(-1.0, 1.0);
    szog = math.acos(c) * 180 / math.pi;
  }
  final ny = y.clamp(y1, y2);
  final kapufa = math.sqrt((x - gx) * (x - gx) + (y - ny) * (y - ny));
  final sav = kapufa < goalAreaRadius
      ? "kapuelőtér"
      : (kapufa < freeThrowRadius ? "6–9 m" : "9 m-en túl");
  final tav = math.sqrt((x - gx) * (x - gx) + (y - cy) * (y - cy));
  return ShotGeometry(bal, gx, tav, kapufa, szog, sav);
}

/// Tankönyvi falak a BAL kapu előtt: (mélység a gólvonaltól, y) — a
/// backend `court3d.FORMATION_TEMPLATES` tükre (a forrás-őr veti össze).
/// A jobb kapura tükrözve: x → 40 − mélység.
const Map<String, List<(double, double)>> formationTemplates = {
  "6-0": [(4.2, 2.6), (6.3, 5.6), (6.7, 8.6), (6.7, 11.4), (6.3, 14.4), (4.2, 17.4)],
  "5-1": [(4.4, 2.8), (6.4, 6.0), (6.8, 10.0), (6.4, 14.0), (4.4, 17.2), (10.0, 10.0)],
  "4-2": [(4.6, 3.4), (6.6, 7.6), (6.6, 12.4), (4.6, 16.6), (9.6, 7.5), (9.6, 12.5)],
  "3-2-1": [(4.4, 3.0), (6.8, 10.0), (4.4, 17.0), (8.6, 6.0), (8.6, 14.0), (11.0, 10.0)],
};

/// A sablon pozíciói a `goalX` kapu előtt, pálya-méterben.
List<Offset> formationPositions(String name, double goalX) {
  final s = formationTemplates[name];
  if (s == null) return const [];
  final jobb = goalX > courtLength / 2;
  return [for (final (d, y) in s) Offset(jobb ? courtLength - d : d, y)];
}

/// Átlagos eltérés a sablontól: mohó párosítás (a legközelebbi pár előbb)
/// — a böngészős nézet `elteres` függvényének tükre.
double? formationDeviation(List<Offset> vedok, List<Offset> pontok) {
  final parok = <(double, int, int)>[];
  for (var i = 0; i < vedok.length; i++) {
    for (var j = 0; j < pontok.length; j++) {
      parok.add(((vedok[i] - pontok[j]).distance, i, j));
    }
  }
  parok.sort((a, b) => a.$1.compareTo(b.$1));
  final vi = <int>{}, pj = <int>{};
  var osszeg = 0.0;
  var db = 0;
  for (final (d, i, j) in parok) {
    if (vi.contains(i) || pj.contains(j)) continue;
    vi.add(i);
    pj.add(j);
    osszeg += d;
    db++;
  }
  return db == 0 ? null : osszeg / db;
}
