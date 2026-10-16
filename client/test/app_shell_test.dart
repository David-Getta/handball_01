// Az oldalsáv fejléce: a SPORT MACHINE szókép a sávon BELÜL marad,
// jobbra levegővel (fix méreten kilógott, és a kártya széle vágta a
// MACHINE végét).
import "package:flutter/material.dart";
import "package:flutter_test/flutter_test.dart";
import "package:handball_client/services/jobs_monitor.dart";
import "package:handball_client/theme/app_theme.dart";
import "package:handball_client/ui/dashboard_screen.dart";
import "package:handball_client/ui/logo.dart";

void main() {
  test("a szókép magassága a helyhez igazodik", () {
    // 14 px magasan 163 px széles — bőven elég helyen marad 14 px.
    expect(wordmarkHeightFor(400), 14);
    // A sávban (154 px) kisebb, és jobbra 4 px levegő marad.
    final h = wordmarkHeightFor(154);
    expect(h, lessThan(14));
    expect(h * SportMachineWordmark.boxW / SportMachineWordmark.boxH,
        closeTo(150, 1e-9));
    expect(wordmarkHeightFor(0), 0);
  });

  testWidgets("a szókép a sávon belül marad, jobbra levegővel",
      (tester) async {
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(const MaterialApp(home: DashboardScreen()));
    for (var i = 0; i < 5; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
    final szokep = find.byType(SportMachineWordmark).first;
    final sav = find
        .ancestor(of: szokep, matching: find.byType(AnimatedContainer))
        .first;
    final jel = find.byType(SportMachineLogo).first;
    final r = tester.getRect(szokep), s = tester.getRect(sav);
    // (a sáv dobozában a bal külső margó is benne van — a kártya széle
    // ennyivel beljebb)
    final balLevego = tester.getRect(jel).left - (s.left + AppSpacing.xl);
    expect(balLevego, greaterThan(0));
    // Jobbra legalább annyi levegő, mint a jel bal oldalán.
    expect(s.right - r.right, greaterThanOrEqualTo(balLevego));
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
    JobsMonitor.instance.stop();
    await tester.pump(const Duration(minutes: 3));
    JobsMonitor.instance.stop();
  });
}
