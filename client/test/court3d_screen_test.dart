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

  testWidgets("labda-nyom gomb: be/ki", (tester) async {
    await _nyit(tester);
    await tester.tap(find.text("Labda-nyom (3 mp)"));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text("Labda-nyom: BE"), findsOneWidget);
    await tester.tap(find.text("Labda-nyom: BE"));
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text("Labda-nyom (3 mp)"), findsOneWidget);
    await _zar(tester);
  });

  testWidgets("lövéstérkép: összegző, koppintás egy körre — odaugrik",
      (tester) async {
    await _nyit(tester);
    await tester.tap(find.text("Lövéstérkép: ki"));
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.text("Minden lövés").last);
    await tester.pump(const Duration(milliseconds: 300));
    // A demó hat lövése, három gól.
    expect(find.textContaining("6 lövés, 3 gól"), findsOneWidget);
    // Felülnézetből végigkoppintjuk a képet, míg egy kört eltalálunk: a
    // mérés-doboz ilyenkor a lövés sorával kezdődik, és a lejátszó megy.
    await tester.tap(find.text("Madártávlat"));
    await tester.pump(const Duration(milliseconds: 100));
    final ter = tester.getRect(_kep());
    var talalt = false;
    for (var i = 1; i < 24 && !talalt; i++) {
      for (var j = 1; j < 14 && !talalt; j++) {
        await tester.tapAt(Offset(ter.left + ter.width * i / 24,
            ter.top + ter.height * j / 14));
        // A dupla koppintás ablakánál hosszabb szünet két koppintás közt.
        await tester.pump(const Duration(milliseconds: 400));
        talalt = find.textContaining("lövése").evaluate().isNotEmpty;
      }
    }
    expect(talalt, isTrue, reason: "egy lövés-kört sem talált a koppintás");
    expect(find.textContaining("· xG "), findsOneWidget);
    expect(find.textContaining("Lövés-mérés"), findsOneWidget);
    // "Eddig" módban a lejátszófej előtti lövések látszanak csak.
    await tester.tap(find.text("Minden lövés"));
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.text("Lövések eddig").last);
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.textContaining("6 lövés, 3 gól"), findsNothing);
    await _zar(tester);
  });
}
