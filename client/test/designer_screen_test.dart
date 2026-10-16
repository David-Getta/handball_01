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
}
