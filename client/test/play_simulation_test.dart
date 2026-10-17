// A figura falának Dart-tükre ugyanott állítja a védőket, mint a backend
// play_simulation.DefenseModel.respond (a várt értékek a Python-függvényből
// számolva: labda y = 13, kapu x = 40).
import "package:flutter_test/flutter_test.dart";
import "package:handball_client/analytics/play_simulation.dart";

void main() {
  void egyezik(DefenseModel m, List<List<double>> vart) {
    final pos = m.respond(13.0, 40.0);
    expect(pos.length, vart.length);
    for (var i = 0; i < vart.length; i++) {
      expect(pos[i].dx, closeTo(vart[i][0], 1e-3), reason: "x $i");
      expect(pos[i].dy, closeTo(vart[i][1], 1e-3), reason: "y $i");
    }
  }

  test("5-1: a csúcs 9,5 m-en, a labda felé", () {
    egyezik(const DefenseModel(rendszer: "5-1"), [
      [35.0279, 4.5], [33.5209, 8.0], [33.5, 11.5], [34.6266, 15.0],
      [39.5, 18.5], [30.5, 12.4],
    ]);
  });

  test("3-2-1: három lépcső", () {
    egyezik(const DefenseModel(rendszer: "3-2-1"), [
      [35.0279, 4.5], [33.5, 11.5], [39.5, 18.5], [31.5, 7.3], [31.5, 16.3],
      [29.0, 12.4],
    ]);
  });

  test("4-2 kitolt vonallal: az előretoltak is kijjebb", () {
    egyezik(const DefenseModel(rendszer: "4-2", lineDepthM: 9.0), [
      [32.0279, 4.5], [30.5, 9.1667], [30.9723, 13.8333], [36.5, 18.5],
      [29.0, 8.3], [29.0, 15.3],
    ]);
  });

  test("ismeretlen rendszer: 6-0", () {
    expect(const DefenseModel(rendszer: "x").respond(10.0, 40.0),
        const DefenseModel().respond(10.0, 40.0));
  });
}
