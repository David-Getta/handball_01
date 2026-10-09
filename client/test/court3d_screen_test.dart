// Az appbeli 3D pálya eszközei a demó-meccsen (backend nélkül): lövés-
// mérés koppintásra, keringés gombra, játékos-szem dupla koppintásra.
import "package:flutter/material.dart";
import "package:flutter/services.dart";
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
  // A célt tévesztő koppintás HIBA, ne csak figyelmeztetés: a panel alját
  // egyszer egy összegző-doboz takarta, és a teszt "rákattintott" a
  // Madártávlatra — a koppintás némán mellément, a teszt mégis átment.
  setUpAll(() => WidgetController.hitTestWarningShouldBeFatal = true);
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

  testWidgets("hőtérkép-választó: a demó mindkét csapatára", (tester) async {
    await _nyit(tester);
    await tester.tap(find.text("Hőtérkép: ki"));
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.text("Mindkét csapat").last);
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.text("Mindkét csapat"), findsOneWidget);
    // A kép továbbra is rajzol (nem dob kivételt a cellák vetítése).
    await tester.ensureVisible(find.text("Madártávlat"));
    await tester.pump();
    await tester.tap(find.text("Madártávlat"));
    await tester.pump(const Duration(milliseconds: 300));
    expect(tester.takeException(), isNull);
    await _zar(tester);
  });

  testWidgets("passz-háló: a demó hazai passzai, összegzővel", (tester) async {
    await _nyit(tester);
    await tester.tap(find.text("Passzok: ki"));
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.text("Hazai passz-háló").last);
    await tester.pump(const Duration(milliseconds: 300));
    // A demó 200 kockáján 25-ösével vált a birtokos: 7 passz.
    expect(find.textContaining("7 passz — Demó Hazai"), findsOneWidget);
    await tester.ensureVisible(find.text("Madártávlat"));
    await tester.pump();
    await tester.tap(find.text("Madártávlat"));
    await tester.pump(const Duration(milliseconds: 300));
    expect(tester.takeException(), isNull);
    await _zar(tester);
  });

  testWidgets("T billentyű: TV-kamera be/ki", (tester) async {
    await _nyit(tester);
    expect(find.text("TV-kamera (labda)"), findsOneWidget);
    await tester.sendKeyEvent(LogicalKeyboardKey.keyT);
    await tester.pump(const Duration(milliseconds: 200));
    expect(find.text("TV-kamera: BE"), findsOneWidget);
    await tester.sendKeyEvent(LogicalKeyboardKey.keyT);
    await tester.pump(const Duration(milliseconds: 200));
    expect(find.text("TV-kamera (labda)"), findsOneWidget);
    await _zar(tester);
  });

  testWidgets("döntés-pillanat: ▶ odaugrik, felirat a jobb opcióval",
      (tester) async {
    await _nyit(tester);
    expect(find.text("2"), findsWidgets); // a demó két pillanata
    final kov = find.byTooltip("Következő döntés-pillanat");
    await tester.ensureVisible(kov);
    await tester.pump();
    await tester.tap(kov);
    // A pillanat 1,5 mp-cel előtte indul, lejátszva: ~2 mp múlva aktív.
    for (var i = 0; i < 30; i++) {
      await tester.pump(const Duration(milliseconds: 100));
      if (find.textContaining("jobb opció is volt").evaluate().isNotEmpty) {
        break;
      }
    }
    expect(find.textContaining("jobb opció is volt: LÖVÉS (0,36)"),
        findsOneWidget);
    expect(tester.takeException(), isNull);
    await _zar(tester);
  });

  testWidgets("az eszköz-panel minden gombja elérhető, és összecsukható",
      (tester) async {
    await _nyit(tester);
    // Görgetéssel minden panel-gomb kattintható helyre hozható (a panel
    // korábban a kép alá lógott — a Madártávlat nem volt kattintható).
    for (final cimke in ["Lelátó", "Kapu mögül", "Pálya-szint",
        "Madártávlat", "Labda-nyom (3 mp)", "Passzsávok"]) {
      final f = find.text(cimke);
      await tester.ensureVisible(f);
      await tester.pump();
      expect(f.hitTestable(), findsOneWidget, reason: cimke);
    }
    // Összecsukva csak a kapcsoló marad, a pálya szabad.
    await tester.tap(find.text("Eszközök ▴"));
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text("Madártávlat"), findsNothing);
    expect(find.text("Eszközök ▾"), findsOneWidget);
    await tester.tap(find.text("Eszközök ▾"));
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text("Madártávlat"), findsOneWidget);
    await _zar(tester);
  });

  testWidgets("szabad lövő: ▶ odaugrik, felirat a védő távolságával",
      (tester) async {
    await _nyit(tester);
    final kov = find.byTooltip("Következő szabadon hagyott lövő");
    await tester.ensureVisible(kov);
    await tester.pump();
    await tester.tap(kov);
    for (var i = 0; i < 30; i++) {
      await tester.pump(const Duration(milliseconds: 100));
      if (find.textContaining("szabadon hagyott lövő").evaluate().isNotEmpty) {
        break;
      }
    }
    expect(find.textContaining("a legközelebbi védő 2,9 m-re"), findsOneWidget);
    expect(tester.takeException(), isNull);
    await _zar(tester);
  });

  testWidgets("labdavesztés: ▶ odaugrik, felirat a vesztővel és a góllal",
      (tester) async {
    await _nyit(tester);
    final kov = find.byTooltip("Következő labdavesztés");
    await tester.ensureVisible(kov);
    await tester.pump();
    await tester.tap(kov);
    for (var i = 0; i < 30; i++) {
      await tester.pump(const Duration(milliseconds: 100));
      if (find.textContaining("labdavesztés —").evaluate().isNotEmpty) break;
    }
    // A demó első labdavesztése a középső harmadban, és gól lett belőle.
    expect(find.textContaining("a középső harmadban"), findsOneWidget);
    expect(find.textContaining("6,0 mp múlva kapott gól"), findsOneWidget);
    // A második ▶ továbblép: a második eladásból már nem lett gól.
    await tester.tap(kov);
    for (var i = 0; i < 30; i++) {
      await tester.pump(const Duration(milliseconds: 100));
      if (find.textContaining("labdavesztés —").evaluate().isNotEmpty &&
          find.textContaining("kapott gól").evaluate().isEmpty) {
        break;
      }
    }
    expect(find.textContaining("labdavesztés —"), findsOneWidget);
    expect(find.textContaining("kapott gól"), findsNothing);
    expect(tester.takeException(), isNull);
    await _zar(tester);
  });

  testWidgets("fal-rések: a demó vendég-falának rései, összegzővel",
      (tester) async {
    await _nyit(tester);
    final gomb = find.text("Fal-rések");
    await tester.ensureVisible(gomb);
    await tester.pump();
    await tester.tap(gomb);
    await tester.pump(const Duration(milliseconds: 200));
    expect(find.text("Fal-rések: BE"), findsOneWidget);
    // A demó vendége a jobb kapu előtt védekezik (hat mezőnyvédő): a fal
    // áll, az összegző megnevezi a csapatot és a legnagyobb rést.
    expect(find.textContaining("Fal (Demó Vendég, 6 védő)"), findsOneWidget);
    expect(find.textContaining("a legnagyobb"), findsOneWidget);
    await tester.tap(find.text("Fal-rések: BE"));
    await tester.pump(const Duration(milliseconds: 200));
    expect(find.textContaining("Fal (Demó Vendég"), findsNothing);
    expect(tester.takeException(), isNull);
    await _zar(tester);
  });

  testWidgets("kinek a hibái: a szűrő a lapozók számát és célját szűri",
      (tester) async {
    await _nyit(tester);
    // A demóban a döntések és a labdavesztések a hazaié, a szabad lövők a
    // vendég védekezéséé: vendégre szűrve csak a szabad lövők maradnak.
    final szuro = find.text("Hibák: mindkét csapat");
    await tester.ensureVisible(szuro);
    await tester.pump();
    await tester.tap(szuro);
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.text("Hibák: Demó Vendég").last);
    await tester.pump(const Duration(milliseconds: 300));
    final kovEladas = find.byTooltip("Következő labdavesztés");
    final gomb = tester.widget<IconButton>(find.ancestor(
        of: find.byIcon(Icons.chevron_right),
        matching: find.byType(IconButton)).at(2));
    expect(gomb.onPressed, isNull, reason: "a vendégnek nincs eladása");
    expect(tester.widget<IconButton>(find.ancestor(
            of: find.byIcon(Icons.chevron_right),
            matching: find.byType(IconButton)).at(1)).onPressed,
        isNotNull, reason: "a vendég szabad lövései maradnak");
    expect(kovEladas, findsOneWidget);
    expect(tester.takeException(), isNull);
    await _zar(tester);
  });

  testWidgets("jelenet-lista: a demó jelenetei, koppintásra odaugrik",
      (tester) async {
    await _nyit(tester);
    final gomb = find.text("Jelenet-lista");
    await tester.ensureVisible(gomb);
    await tester.pump();
    await tester.tap(gomb);
    await tester.pump(const Duration(milliseconds: 200));
    // A demó két döntése, két szabad lövése és két labdavesztése.
    expect(find.textContaining("jobb opció is volt: lövés"), findsNWidgets(2));
    expect(find.textContaining("védekezése — szabad lövő"), findsNWidgets(2));
    final golos = find.textContaining("· gól lett belőle");
    expect(golos, findsOneWidget);
    await tester.tap(golos);
    for (var i = 0; i < 30; i++) {
      await tester.pump(const Duration(milliseconds: 100));
      if (find.textContaining("6,0 mp múlva kapott gól").evaluate().isNotEmpty) {
        break;
      }
    }
    expect(find.textContaining("6,0 mp múlva kapott gól"), findsOneWidget);
    expect(tester.takeException(), isNull);
    await _zar(tester);
  });

  testWidgets("gól-akció: ▶ odaugrik, felirat a lánccal", (tester) async {
    await _nyit(tester);
    final kov = find.byTooltip("Következő gól-akció");
    await tester.ensureVisible(kov);
    await tester.pump();
    await tester.tap(kov);
    for (var i = 0; i < 30; i++) {
      await tester.pump(const Duration(milliseconds: 100));
      if (find.textContaining("gólja —").evaluate().isNotEmpty) break;
    }
    // A demó gól-akciója: három passz, a végén lövés.
    expect(find.textContaining("Demó Hazai gólja —"), findsOneWidget);
    expect(find.textContaining("· 3 passz,"), findsOneWidget);
    expect(tester.takeException(), isNull);
    await _zar(tester);
  });

  testWidgets("emberelőny: ▶ a szakaszra ugrik, élő jelzővel", (tester) async {
    await _nyit(tester);
    final kov = find.byTooltip("Következő emberelőny");
    await tester.ensureVisible(kov);
    await tester.pump();
    await tester.tap(kov);
    for (var i = 0; i < 30; i++) {
      await tester.pump(const Duration(milliseconds: 100));
      if (find.textContaining("Emberelőny: Demó Hazai").evaluate().isNotEmpty) {
        break;
      }
    }
    expect(
        find.textContaining(
            "Emberelőny: Demó Hazai (Demó Vendég kiállítás miatt hiányos)"),
        findsOneWidget);
    expect(tester.takeException(), isNull);
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
    await tester.ensureVisible(find.text("Madártávlat"));
    await tester.pump();
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
    // "Eddig" módban a lejátszófej előtti lövések látszanak csak. (A
    // panel a Madártávlathoz görgetve — a választót előbb láthatóvá kell
    // görgetni, ahogy a felhasználó is tenné.)
    await tester.ensureVisible(find.text("Minden lövés"));
    await tester.pump();
    await tester.tap(find.text("Minden lövés"));
    await tester.pump(const Duration(milliseconds: 300));
    await tester.tap(find.text("Lövések eddig").last);
    await tester.pump(const Duration(milliseconds: 300));
    expect(find.textContaining("6 lövés, 3 gól"), findsNothing);
    await _zar(tester);
  });
}
