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

  // A passzsávok a backend `court3d.pass_lanes` számait adják — a várt
  // értékek a Python-függvényből (decisions.pass_completion modellje).
  test("passLanes = a backend pass_lanes", () {
    _ellenoriz([(true, 18.1, 17.1), (false, 7.4, 10.2), (false, 3.8, 6.1), (false, 21.5, 17.8), (false, 23.8, 7.9), (true, 26.2, 12.3), (false, 24.9, 16.6), (false, 2.4, 3.8), (false, 24.0, 15.6)], const Offset(25.78, 14.7), (24.0, 15.6), [(0.5013, 0, "kockázatos"), (0.3622, 0, "kockázatos"), (0.9049, 0, "nyitott"), (0.7799, 0, "nyitott"), (0.9616, 0, "nyitott"), (0.2968, 0, "zárt")]);
    expect(passLanes([(false, 25.6, 10.0), (false, 18.3, 5.6), (false, 28.3, 6.3), (false, 20.5, 0.6), (false, 16.0, 16.9), (true, 2.7, 0.3), (false, 8.5, 18.5), (false, 18.8, 19.6), (true, 16.8, 11.3), (false, 31.1, 5.4)], const Offset(16.98, 2.21)), isNull);
    expect(passLanes([(false, 5.4, 14.1), (false, 2.4, 15.9), (false, 27.3, 3.8), (false, 39.4, 15.4), (true, 25.7, 2.3), (true, 39.6, 0.0), (true, 39.9, 0.4), (false, 15.8, 17.1)], const Offset(-0.81, 13.42)), isNull);
    _ellenoriz([(true, 0.4, 12.2), (true, 15.4, 1.5), (false, 23.3, 4.9), (true, 14.9, 9.1), (true, 33.3, 2.7), (true, 7.3, 3.1), (false, 32.7, 5.0), (false, 6.3, 12.6), (false, 27.5, 7.8)], const Offset(7.02, 12.05), (6.3, 12.6), [(0.1668, 1, "zárt"), (0.05, 1, "zárt"), (0.379, 0, "kockázatos")]);
    expect(passLanes([(false, 1.5, 19.3), (false, 29.6, 7.8), (true, 32.9, 11.9)], const Offset(29.74, 10.8)), isNull);
    expect(passLanes([(false, 9.1, 11.2), (false, 11.2, 18.3), (false, 30.0, 1.4)], const Offset(10.82, 15.22)), isNull);
    expect(passLanes([(true, 14.8, 11.4), (false, 3.7, 2.8), (true, 39.2, 13.1), (false, 23.6, 18.5)], const Offset(26.47, 19.91)), isNull);
    _ellenoriz([(false, 23.9, 1.5), (false, 29.2, 6.4)], const Offset(20.93, 1.82), (23.9, 1.5), [(0.7938, 0, "nyitott")]);
    _ellenoriz([(false, 31.7, 18.3), (true, 3.4, 9.5)], const Offset(34.3, 17.72), (31.7, 18.3), []);
    expect(passLanes([(true, 22.9, 12.5), (true, 15.2, 0.2)], const Offset(19.96, 13.48)), isNull);
    _ellenoriz([(true, 29.1, 7.8), (true, 17.6, 16.8), (false, 20.7, 10.3), (true, 24.1, 9.6), (false, 38.3, 2.3), (true, 10.2, 0.2)], const Offset(18.2, 11.08), (20.7, 10.3), [(0.05, 2, "zárt")]);
    _ellenoriz([(false, 30.2, 6.9), (true, 19.9, 4.8), (true, 26.6, 4.0), (true, 32.1, 15.1), (false, 35.2, 7.7), (true, 8.4, 2.7), (true, 33.5, 17.0), (false, 38.0, 5.5), (false, 4.5, 9.4), (false, 33.2, 7.7)], const Offset(4.46, 8.11), (4.5, 9.4), [(0.2622, 0, "zárt"), (0.1215, 0, "zárt"), (0.1, 0, "zárt"), (0.1786, 0, "zárt")]);
    expect(passLanes([(true, 12.8, 16.6), (true, 34.9, 0.8), (true, 22.8, 6.2), (false, 25.6, 8.1), (false, 1.0, 16.6), (false, 31.2, 15.9), (false, 17.9, 12.6), (true, 38.3, 13.7), (false, 33.0, 5.1), (false, 30.2, 10.7), (false, 7.2, 5.4)], const Offset(31.48, 19.03)), isNull);
    _ellenoriz([(false, 15.7, 15.8), (false, 3.5, 18.7), (true, 5.2, 9.1), (false, 15.1, 11.4), (true, 18.5, 13.0), (false, 4.0, 17.3), (false, 8.5, 18.0), (false, 39.1, 10.7), (true, 10.5, 14.4), (false, 13.9, 1.7)], const Offset(37.99, 10.15), (39.1, 10.7), [(0.3157, 0, "zárt"), (0.1, 0, "zárt"), (0.314, 0, "zárt"), (0.1, 0, "zárt"), (0.1012, 0, "zárt"), (0.2355, 0, "zárt")]);
    _ellenoriz([(true, 36.8, 4.4), (false, 17.2, 0.7), (true, 27.5, 18.3), (true, 5.9, 10.3), (true, 37.8, 9.9), (false, 30.3, 8.8)], const Offset(36.33, 11.5), (37.8, 9.9), [(0.8403, 0, "nyitott"), (0.6203, 0, "nyitott"), (0.05, 1, "zárt")]);
    expect(passLanes([(false, 20.9, 16.9), (true, 12.5, 7.6), (false, 12.2, 2.8), (true, 22.9, 4.0), (false, 20.1, 12.1), (false, 21.5, 0.9), (true, 21.8, 19.8), (false, 19.6, 13.8), (false, 37.2, 9.2), (true, 10.8, 9.5), (false, 13.6, 18.0), (true, 21.0, 2.2)], const Offset(22.63, 22.78)), isNull);
    _ellenoriz([(false, 1.4, 3.1), (false, 27.5, 6.4), (true, 9.8, 10.0), (true, 29.2, 2.5)], const Offset(11.32, 11.41), (9.8, 10.0), [(0.4057, 0, "kockázatos")]);
    expect(passLanes([(false, 15.0, 8.3), (false, 21.5, 17.3), (false, 21.2, 17.0), (false, 9.3, 14.8), (true, 36.1, 6.3), (true, 35.6, 3.9), (false, 35.5, 2.7), (false, 5.3, 1.8)], const Offset(32.68, 5.03)), isNull);
    expect(passLanes([(false, 8.0, 12.6), (false, 3.8, 11.4), (true, 36.5, 19.4), (false, 28.2, 12.7), (true, 20.1, 13.7), (false, 32.1, 9.6), (false, 1.5, 11.0), (true, 5.9, 3.7)], const Offset(25.91, 10.31)), isNull);
    _ellenoriz([(false, 23.2, 2.7), (true, 3.1, 1.9), (true, 18.7, 10.3), (true, 8.4, 7.5), (false, 33.8, 3.6), (true, 14.4, 7.4)], const Offset(3.83, -0.94), (3.1, 1.9), [(0.4938, 0, "kockázatos"), (0.7797, 0, "nyitott"), (0.6409, 0, "nyitott")]);
    _ellenoriz([(true, 35.7, 16.0), (true, 22.8, 3.8)], const Offset(24.93, 2.11), (22.8, 3.8), [(0.4927, 0, "kockázatos")]);
    expect(passLanes([(false, 32.6, 8.1), (true, 35.2, 13.9), (true, 30.6, 8.1)], const Offset(28.39, 10.18)), isNull);
    expect(passLanes([(true, 4.0, 17.8), (false, 9.3, 18.9), (true, 13.5, 13.2), (false, 21.3, 7.8), (true, 25.7, 14.0), (true, 39.2, 0.5)], const Offset(22.96, 12.16)), isNull);
    expect(passLanes([(true, 20.2, 15.2), (true, 0.4, 5.2), (true, 36.2, 11.0), (true, 38.7, 11.4), (false, 25.5, 16.2), (false, 22.0, 13.4), (false, 15.5, 18.8), (true, 18.9, 3.4), (true, 21.7, 11.9)], const Offset(18.62, 18.24)), isNull);
    _ellenoriz([(true, 23.9, 7.3), (true, 19.3, 5.4), (true, 26.5, 15.0), (false, 0.6, 4.9), (false, 25.3, 8.2), (true, 2.1, 6.3), (true, 2.0, 19.8), (true, 2.9, 18.1), (true, 28.8, 5.0), (false, 1.8, 2.0)], const Offset(0.41, 21.32), (2.0, 19.8), [(0.2795, 0, "zárt"), (0.3569, 0, "kockázatos"), (0.2867, 0, "zárt"), (0.6143, 0, "nyitott"), (0.945, 0, "nyitott"), (0.05, 1, "zárt")]);
    expect(passLanes([(false, 2.0, 8.3), (false, 8.1, 1.0), (false, 5.0, 8.9), (true, 18.2, 5.2), (true, 14.6, 14.9)], const Offset(11.27, 2.64)), isNull);
    expect(passLanes([(true, 4.6, 17.9), (true, 11.0, 12.2), (false, 25.3, 15.1), (false, 38.1, 10.0), (false, 35.2, 0.8)], const Offset(1.17, 16.22)), isNull);
    _ellenoriz([(false, 4.1, 10.8), (false, 30.2, 18.3)], const Offset(4.45, 11.72), (4.1, 10.8), [(0.2241, 0, "zárt")]);
    _ellenoriz([(true, 19.1, 4.2), (true, 19.8, 2.7), (false, 32.1, 8.9), (false, 17.8, 14.9), (true, 32.4, 7.4), (true, 11.6, 15.2), (false, 17.1, 7.4)], const Offset(18.83, 2.97), (19.8, 2.7), [(0.9527, 0, "nyitott"), (0.6158, 0, "nyitott"), (0.2729, 1, "zárt")]);
    _ellenoriz([(false, 17.3, 11.4), (true, 12.0, 15.5), (false, 12.4, 18.2), (false, 27.8, 9.9), (true, 11.3, 2.9), (true, 26.3, 6.5), (false, 12.9, 8.8), (true, 17.5, 16.1), (true, 18.3, 4.4), (false, 3.4, 16.6)], const Offset(16.34, 10.67), (17.3, 11.4), [(0.7605, 0, "nyitott"), (0.697, 0, "nyitott"), (0.854, 0, "nyitott"), (0.576, 0, "kockázatos")]);
    _ellenoriz([(false, 29.6, 7.4), (true, 21.6, 16.7), (false, 7.1, 15.2), (true, 32.5, 4.4), (false, 21.8, 11.3), (false, 26.0, 16.1), (false, 23.3, 6.1), (false, 13.4, 5.5)], const Offset(24.39, 13.79), (26.0, 16.1), [(0.731, 0, "nyitott"), (0.1594, 1, "zárt"), (0.8178, 0, "nyitott"), (0.7041, 0, "nyitott"), (0.5296, 0, "kockázatos")]);
    _ellenoriz([(false, 3.9, 16.3), (true, 9.8, 4.4), (true, 30.6, 7.9), (true, 32.3, 6.7), (false, 19.7, 10.7), (false, 28.3, 18.3), (true, 30.3, 19.7), (true, 34.1, 16.1), (false, 35.5, 19.2), (false, 21.0, 14.2), (false, 16.9, 8.4), (false, 9.8, 3.2)], const Offset(16.03, 6.07), (16.9, 8.4), [(0.5654, 0, "kockázatos"), (0.8965, 0, "nyitott"), (0.5686, 0, "kockázatos"), (0.3855, 0, "kockázatos"), (0.7971, 0, "nyitott"), (0.4486, 1, "kockázatos")]);
    _ellenoriz([(true, 17.0, 5.8), (false, 18.9, 14.6), (true, 25.9, 15.5), (false, 36.5, 15.1), (false, 23.4, 18.2)], const Offset(15.69, 3.68), (17.0, 5.8), [(0.6239, 0, "nyitott")]);
    expect(passLanes([(false, 23.5, 12.0), (true, 23.8, 4.5), (false, 35.8, 8.0), (true, 25.1, 18.8), (true, 34.1, 9.7), (true, 36.6, 6.8), (false, 19.3, 4.4)], const Offset(21.52, 9.44)), isNull);
    _ellenoriz([(true, 31.5, 1.2), (false, 35.7, 17.5), (true, 18.0, 4.9), (true, 24.2, 3.1), (false, 30.9, 2.9), (false, 25.5, 19.9), (true, 20.6, 1.1), (false, 0.1, 16.4)], const Offset(20.25, 1.98), (20.6, 1.1), [(0.6886, 0, "nyitott"), (0.8684, 0, "nyitott"), (0.8823, 0, "nyitott")]);
    _ellenoriz([(false, 35.6, 13.9), (false, 38.2, 11.7), (true, 0.8, 3.8), (false, 36.7, 1.8), (true, 8.3, 10.9), (true, 6.3, 16.6)], const Offset(-0.49, 3.14), (0.8, 3.8), [(0.7049, 0, "nyitott"), (0.602, 0, "nyitott")]);
    _ellenoriz([(true, 39.9, 13.3), (false, 14.4, 13.7), (false, 26.7, 13.5), (false, 26.2, 0.2), (true, 28.5, 9.5), (true, 22.6, 9.2), (false, 34.2, 16.9), (false, 36.1, 3.0), (true, 37.5, 15.0), (true, 30.2, 11.1)], const Offset(12.7, 11.6), (14.4, 13.7), [(0.6485, 0, "nyitott"), (0.4877, 0, "kockázatos"), (0.4269, 0, "kockázatos"), (0.05, 1, "zárt")]);
    _ellenoriz([(true, 12.4, 5.5), (true, 29.0, 6.6), (true, 3.7, 2.8)], const Offset(9.82, 6.41), (12.4, 5.5), [(0.5247, 0, "kockázatos"), (0.7397, 0, "nyitott")]);
    expect(passLanes([(false, 7.7, 0.7), (true, 23.7, 1.8), (false, 1.3, 19.7), (true, 16.3, 1.5)], const Offset(19.29, -1.03)), isNull);
    _ellenoriz([(false, 32.8, 7.7), (true, 36.9, 12.5), (true, 24.5, 6.4), (false, 26.4, 12.2), (false, 10.4, 3.8)], const Offset(25.56, 3.64), (24.5, 6.4), [(0.6052, 0, "nyitott")]);
  });
}

void _ellenoriz(List<(bool, double, double)> jat, Offset labda,
    (double, double) holder, List<(double, int, String)> vart) {
  final r = passLanes(jat, labda);
  expect(r, isNotNull);
  expect(r!.$1.$2, closeTo(holder.$1, 1e-9));
  expect(r.$1.$3, closeTo(holder.$2, 1e-9));
  expect(r.$2.length, vart.length);
  for (var i = 0; i < vart.length; i++) {
    expect(r.$2[i].p, closeTo(vart[i].$1, 1e-3));
    expect(r.$2[i].blockers, vart[i].$2);
    expect(r.$2[i].grade, vart[i].$3);
  }
}
