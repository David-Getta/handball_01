// A 3D pálya közös geometriája — a Dart-tükör ugyanazt adja, mint a
// backend `court3d` (a várt értékek a Python-függvényből számolva).
import "dart:ui";

import "package:flutter_test/flutter_test.dart";
import "package:handball_client/ui/court_geometry.dart";

void main() {
  test("lövés-mérés = backend court3d.shot_geometry", () {
    // (pont, bal kapu?, távolság, kapufa-távolság, kapu-szög, sáv)
    const esetek = [
      ((9.0, 10.0), true, 9.0, 9.0, 18.9, "9 m-en túl"),
      ((6.36, 3.64), true, 8.99, 8.0, 13.6, "6–9 m"),
      ((7.0, 10.0), true, 7.0, 7.0, 24.2, "6–9 m"),
      ((35.0, 11.0), false, 5.1, 5.0, 32.3, "kapuelőtér"),
      ((5.0, 12.0), true, 5.39, 5.02, 29.3, "kapuelőtér"),
      ((0.0, 8.5), true, 1.5, 0.0, 180.0, "kapuelőtér"),
      ((12.5, 1.0), true, 15.4, 14.58, 9.1, "9 m-en túl"),
      ((30.0, 18.0), false, 12.81, 11.93, 10.5, "9 m-en túl"),
      ((20.0, 10.0), true, 20.0, 20.0, 8.6, "9 m-en túl"),
    ];
    for (final ((x, y), bal, tav, kapufa, szog, sav) in esetek) {
      final g = shotGeometry(x, y);
      expect(g.leftGoal, bal, reason: "$x,$y");
      expect(g.distance, closeTo(tav, 0.006), reason: "$x,$y");
      expect(g.postDistance, closeTo(kapufa, 0.006), reason: "$x,$y");
      expect(g.angleDeg, closeTo(szog, 0.06), reason: "$x,$y");
      expect(g.zone, sav, reason: "$x,$y");
    }
  });

  test("falsablon a jobb kapu elé tükrözve", () {
    expect(formationPositions("5-1", 40.0), const [
      Offset(35.6, 2.8), Offset(33.6, 6.0), Offset(33.2, 10.0),
      Offset(33.6, 14.0), Offset(35.6, 17.2), Offset(30.0, 10.0),
    ]);
    expect(formationPositions("7-0", 0.0), isEmpty);
  });

  test("eltérés a sablontól: mohó párosítás", () {
    final sablon = formationPositions("6-0", 0.0);
    expect(formationDeviation(sablon, sablon), 0.0);
    final elcsuszott = [for (final p in sablon) p + const Offset(1.0, 0.0)];
    expect(formationDeviation(elcsuszott, sablon), closeTo(1.0, 1e-9));
    expect(formationDeviation(const [], sablon), isNull);
  });
}
