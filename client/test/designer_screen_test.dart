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
}
