// A figura-tervező megnyílik (túlcsordulás nélkül) a szokásos
// ablakméretekben — a "3D / VR ↗" gombbal az oldalsáv eggyel hosszabb.
import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:handball_client/models/tracking.dart";
import "package:handball_client/ui/designer_screen.dart";

void main() {
  for (final meret in const [Size(1400, 900), Size(900, 700), Size(700, 600)]) {
    testWidgets(
        "a tervező megnyílik (${meret.width.toInt()}×${meret.height.toInt()})",
        (tester) async {
      tester.view.physicalSize = meret;
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);
      final m = Match(
          meta: MatchMeta(
              matchId: "t",
              homeTeam: "A",
              awayTeam: "B",
              fps: 25,
              frameWidth: 1920,
              frameHeight: 1080),
          frames: const []);
      await tester.pumpWidget(MaterialApp(home: DesignerScreen(match: m)));
      await tester.pump();
      expect(tester.takeException(), isNull);
      expect(find.text("3D / VR ↗"), findsOneWidget);
    });
  }

  testWidgets("kulcs-pozíció be és ki (legfeljebb 6, legalább 2)",
      (tester) async {
    tester.view.physicalSize = const Size(700, 600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    final m = Match(
        meta: MatchMeta(
            matchId: "t",
            homeTeam: "A",
            awayTeam: "B",
            fps: 25,
            frameWidth: 1920,
            frameHeight: 1080),
        frames: const []);
    await tester.pumpWidget(MaterialApp(home: DesignerScreen(match: m)));
    await tester.pump();
    expect(find.text("Közép"), findsOneWidget);
    for (var i = 0; i < 5; i++) {
      await tester.tap(find.byIcon(Icons.add_circle_outline));
      await tester.pump();
    }
    // 6 pontnál megáll, a feliratok sorszámok
    Finder pont(String t) => find.descendant(
        of: find.byType(SegmentedButton<int>), matching: find.text(t));
    expect(pont("6"), findsOneWidget);
    expect(pont("7"), findsNothing);
    expect(tester.takeException(), isNull);
    for (var i = 0; i < 6; i++) {
      await tester.tap(find.byIcon(Icons.remove_circle_outline));
      await tester.pump();
    }
    // 2 pontnál megáll
    expect(find.text("Kezdő"), findsOneWidget);
    expect(find.text("Vég"), findsOneWidget);
    expect(find.text("Közép"), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets("a meccs támadásából kapott kezdő figura", (tester) async {
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    final m = Match(
        meta: MatchMeta(
            matchId: "m1",
            homeTeam: "Kiel",
            awayTeam: "Berlin",
            fps: 25,
            frameWidth: 1920,
            frameHeight: 1080),
        frames: const []);
    final kezdo = {
      "attackers": [
        for (final y in [4.0, 8.0, 12.0, 16.0])
          [[28.0, y], [29.0, y], [31.0, y]]
      ],
      "labda": [1, 2, 2],
      "csapat": "Kiel",
      "csapat_oldal": "home",
      "t0_s": 754.0,
      "match_id": "m1",
    };
    await tester.pumpWidget(
        MaterialApp(home: DesignerScreen(match: m, initial: kezdo)));
    await tester.pump();
    expect(tester.takeException(), isNull);
    // 4 játékos (a labdás-választó 1..4), 3 kulcs-pozíció
    Finder chip(String t) => find.descendant(
        of: find.byType(ChoiceChip), matching: find.text(t));
    expect(chip("4"), findsOneWidget);
    expect(chip("5"), findsNothing);
    expect(find.text("Közép"), findsOneWidget);
    // a Kezdő pontnál a 2. játékosnál a labda
    final kivalasztott = tester
        .widgetList<ChoiceChip>(find.byType(ChoiceChip))
        .where((c) => c.selected)
        .toList();
    expect(kivalasztott.length, 1);
    expect((kivalasztott.first.label as Text).data, "2");
  });
}
