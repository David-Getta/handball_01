// Az appbeli 3D pálya eszközei a demó-meccsen (backend nélkül): lövés-
// mérés koppintásra, keringés gombra, játékos-szem dupla koppintásra.
import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:handball_client/services/jobs_monitor.dart";
import "package:handball_client/ui/court3d_screen.dart";

Future<void> _nyit(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1400, 900);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(const MaterialApp(home: Court3DScreen()));
  // A meccs-lista kérése a tesztben azonnal bukik → demó-meccs.
  for (var i = 0; i < 40; i++) {
    await tester.pump(const Duration(milliseconds: 100));
    if (find.textContaining("DEMÓ").evaluate().isNotEmpty) break;
  }
}

/// A 3D kép (a legnagyobb CustomPaint a képernyőn belül, a teljes
/// ablakot kitöltő gyökér-réteg nélkül).
Finder _kep() {
  final jeloltek = find.byType(CustomPaint).evaluate().toList()
    ..sort((a, b) {
      final ma = (a.renderObject as RenderBox).size;
      final mb = (b.renderObject as RenderBox).size;
      return (mb.width * mb.height).compareTo(ma.width * ma.height);
    });
  return find.byWidget(jeloltek[1].widget);
}

/// A képernyő lebontása és a hálózati újrapróbálás időzítőinek lefuttatása
/// (a backend nélküli meccs-lista kérés percekig próbálkozna).
Future<void> _zar(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox());
  // Az app-szintű feladat-figyelő (a keret indítja) magától is
  // újraütemez — a teszt végén leállítjuk.
  JobsMonitor.instance.stop();
  await tester.pump(const Duration(minutes: 3));
  JobsMonitor.instance.stop();
}

void main() {
  testWidgets("koppintás a padlóra: lövés-mérés doboz", (tester) async {
    await _nyit(tester);
    expect(find.textContaining("DEMÓ"), findsOneWidget);
    final ter = tester.getRect(_kep());
    // A kép alsó harmada: a kamera a pályát látja, ott padló van.
    await tester.tapAt(Offset(ter.center.dx, ter.top + ter.height * 0.8));
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.textContaining("Lövés-mérés"), findsOneWidget);
    expect(find.textContaining("Kapu-szög"), findsOneWidget);
    await _zar(tester);
  });

  testWidgets("keringés gomb és védekezés-sablon", (tester) async {
    await _nyit(tester);
    await tester.tap(find.text("Keringés (O)"));
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text("Keringés: BE (O)"), findsOneWidget);
    await tester.tap(find.text("Védekezés: ki"));
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.text("6-0 sablon").last);
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.text("védett kapu"));
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.text("bal kapu").last);
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.textContaining("6-0 sablon a bal kapu előtt"), findsOneWidget);
    await _zar(tester);
  });
}
