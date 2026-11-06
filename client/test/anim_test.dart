import "package:flutter/material.dart";
import "package:flutter/gestures.dart";
import "package:flutter_test/flutter_test.dart";
import "package:handball_client/ui/anim.dart";

void main() {
  testWidgets("a HoverLift rámutatásra nem változtat méretet (csak emel)",
      (tester) async {
    // A kártya a lista teljes szélességét kitölti, a görgető a szélén
    // levág: a rámutatott kártya nem lehet szélesebb, mint a helye —
    // különben a keret oldalsó szegélye a levágott sávba kerül.
    await tester.pumpWidget(const MaterialApp(
      home: Scaffold(
        body: Center(
          child: SizedBox(
            width: 300,
            child: HoverLift(child: SizedBox(height: 60)),
          ),
        ),
      ),
    ));
    final elotte = tester.getSize(find.byType(HoverLift));
    final mouse = await tester.createGesture(kind: PointerDeviceKind.mouse);
    await mouse.addPointer(location: Offset.zero);
    addTearDown(mouse.removePointer);
    await mouse.moveTo(tester.getCenter(find.byType(HoverLift)));
    await tester.pumpAndSettle();
    expect(tester.getSize(find.byType(HoverLift)), elotte);
    expect(find.byType(AnimatedScale), findsNothing);
    // Az emelés: a tartalom HoverLift.liftPx-szel feljebb került.
    final box = tester.renderObject<RenderBox>(find.byType(SizedBox).last);
    final fent = box.localToGlobal(Offset.zero).dy;
    await mouse.moveTo(const Offset(1, 1));
    await tester.pumpAndSettle();
    final alap = box.localToGlobal(Offset.zero).dy;
    expect(alap - fent, closeTo(HoverLift.liftPx, 0.01));
  });
}
