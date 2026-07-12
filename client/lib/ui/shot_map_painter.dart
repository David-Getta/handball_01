/// Lövéstérkép-rajzoló — a lövések/gólok helye a felülnézeti pályán.
///
/// A jelölő a csapat színét viseli (mint a pályán a játékosok), felület-színű
/// gyűrűvel, hogy sűrű helyeken is elváljanak; a gólt arany gyűrű emeli ki.
/// Az aktuális képkockához tartozó lövés (ahová épp odaugrottunk) nagyobb,
/// fehér gyűrűs jelölőt kap.
library;

import "package:flutter/material.dart";

import "../models/tracking.dart";
import "../theme/app_theme.dart";
import "court_painter.dart";

/// Egy lövés-jelölő: hol állt a lövő (méterben), melyik csapat lőtt,
/// gól lett-e, és melyik képkockánál történt (odaugráshoz).
class ShotMarker {
  final int t;
  final Team team;
  final bool goal;
  final double x;
  final double y;
  const ShotMarker(this.t, this.team, this.goal, this.x, this.y);
}

class ShotMapPainter extends CustomPainter {
  final List<ShotMarker> shots;
  final int currentFrame;
  ShotMapPainter({required this.shots, required this.currentFrame});

  @override
  void paint(Canvas canvas, Size size) {
    final (scale, origin) = CourtPainter.transformFor(size);
    if (scale <= 0) return;
    for (final s in shots) {
      final p = Offset(origin.dx + s.x * scale, origin.dy + s.y * scale);
      final teamColor = s.team == Team.home ? AppColors.home : AppColors.away;
      final active = s.t == currentFrame;
      final r = active ? 8.0 : 6.0;
      // Felület-színű alap: sűrű helyeken is elválnak a jelölők.
      canvas.drawCircle(p, r + 2, Paint()..color = AppColors.surface);
      canvas.drawCircle(p, r, Paint()..color = teamColor.withOpacity(s.goal ? 1.0 : 0.55));
      if (s.goal) {
        canvas.drawCircle(p, r, Paint()
          ..color = AppColors.gold
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2.5);
      }
      if (active) {
        canvas.drawCircle(p, r + 3, Paint()
          ..color = Colors.white
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.5);
      }
    }
  }

  @override
  bool shouldRepaint(covariant ShotMapPainter old) =>
      old.shots != shots || old.currentFrame != currentFrame;
}
