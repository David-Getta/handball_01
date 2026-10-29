// A figura falának Dart-tükre ugyanott állítja a védőket, mint a backend
// play_simulation.DefenseModel.respond (a várt értékek a Python-függvényből
// számolva: labda y = 13, kapu x = 40).
import "package:flutter_test/flutter_test.dart";
import "package:handball_client/analytics/play_simulation.dart";
import "package:handball_client/models/tracking.dart";

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

  test("a tanult fal rendszere (mint a backend learn-je)", () {
    // 5 védő a 6 m-en (x = 34), egy előretolt 9,5 m-en; a hazai támad.
    PlayerPosition pl(int id, Team t, double x, double y) => PlayerPosition(
        trackId: id,
        team: t,
        x: x,
        y: y,
        source: PositionSource.measured,
        confidence: 1.0);
    final frames = [
      for (int t = 0; t < 10; t++)
        Frame(t: t, players: [
          for (int i = 0; i < 3; i++) pl(i + 1, Team.home, 28.0, 10.0),
          pl(100, Team.away, 34, 3),
          pl(101, Team.away, 34, 6.5),
          pl(102, Team.away, 34, 10),
          pl(103, Team.away, 34, 13.5),
          pl(104, Team.away, 34, 17),
          pl(105, Team.away, 30.5, 10),
        ], ball: Ball(x: 28.0, y: 10.0, confidence: 1.0)),
    ];
    final m = learnDefense(
        Match(
            meta: MatchMeta(
                matchId: "t",
                homeTeam: "A",
                awayTeam: "B",
                fps: 25,
                frameWidth: 1920,
                frameHeight: 1080),
            frames: frames),
        Team.away);
    expect(m.rendszer, "5-1");
    expect(m.numDefenders, 6);
    expect(m.lineDepthM, closeTo(6.0, 1e-9));
  });

  test("a tanult fal labdakövetése (mint a backend learn-je)", () {
    // A backend test_a_vedekezes_modell_megtanulja_a_labdakovetest
    // fixture-je: a labda y-ja 5, 7, 10, 13, 15 körbe, a fal a labda
    // oldal-eltérésének 60%-ával tolódik — a backend 0,6-ot tanul.
    PlayerPosition pl(int id, Team t, double x, double y) => PlayerPosition(
        trackId: id,
        team: t,
        x: x,
        y: y,
        source: PositionSource.measured,
        confidence: 1.0);
    Match meccs(double gain, int n, List<double> labdaYs) {
      final frames = [
        for (int t = 0; t < n; t++)
          Frame(t: t, players: [
            pl(1, Team.home, 28.0, labdaYs[t % labdaYs.length]),
            pl(2, Team.home, 27.0, 5.0),
            pl(3, Team.home, 27.0, 15.0),
            for (final (i, y) in [4.0, 7.0, 9.0, 11.0, 13.0, 16.0].indexed)
              pl(100 + i, Team.away, 34.0,
                  y + gain * (labdaYs[t % labdaYs.length] - 10.0)),
          ], ball: Ball(
              x: 28.0, y: labdaYs[t % labdaYs.length], confidence: 1.0)),
      ];
      return Match(
          meta: MatchMeta(
              matchId: "k",
              homeTeam: "A",
              awayTeam: "B",
              fps: 25,
              frameWidth: 1920,
              frameHeight: 1080),
          frames: frames);
    }

    const ys = [5.0, 7.0, 10.0, 13.0, 15.0];
    expect(learnDefense(meccs(0.6, 60, ys), Team.away).lateralGain,
        closeTo(0.6, 1e-9));
    expect(learnDefense(meccs(0.0, 60, ys), Team.away).lateralGain, 0.0);
    // középen álló labda és kevés minta: az alapérték marad
    expect(learnDefense(meccs(0.6, 60, [10.0]), Team.away).lateralGain, 0.5);
    expect(learnDefense(meccs(0.6, 49, ys), Team.away).lateralGain, 0.5);
  });

  test("ismeretlen rendszer: 6-0", () {
    expect(const DefenseModel(rendszer: "x").respond(10.0, 40.0),
        const DefenseModel().respond(10.0, 40.0));
  });
}
