/// Lövéstérkép-rajzoló — a lövések/gólok helye a felülnézeti pályán.
///
/// A jelölő a csapat színét viseli (mint a pályán a játékosok), felület-színű
/// gyűrűvel, hogy sűrű helyeken is elváljanak; a gólt arany gyűrű emeli ki.
/// Az aktuális képkockához tartozó lövés (ahová épp odaugrottunk) nagyobb,
/// fehér gyűrűs jelölőt kap.
library;

import "dart:math" as math;

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

  /// Helyzetminőség (0..~0,9) a backendtől — a jelölő mérete mutatja.
  final double? xg;

  /// SZABAD lövés volt-e (nem volt védő a lövő 2 m-es körzetében) —
  /// szaggatott fehér gyűrű jelzi; null: nem mérhető.
  final bool? free;
  const ShotMarker(this.t, this.team, this.goal, this.x, this.y,
      {this.xg, this.free});
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
      // A jelölő mérete a helyzet értéke (xG): a nagy körök a nagy
      // helyzetek — ránézésre látszik, hol puskáztunk el ziccert.
      final base =
          s.xg == null ? 6.0 : 4.0 + 5.0 * (s.xg!.clamp(0.0, 0.9) / 0.9);
      final r = active ? base + 2.5 : base;
      // Felület-színű alap: sűrű helyeken is elválnak a jelölők.
      canvas.drawCircle(p, r + 2, Paint()..color = AppColors.surface);
      canvas.drawCircle(p, r, Paint()..color = teamColor.withOpacity(s.goal ? 1.0 : 0.55));
      if (s.goal) {
        canvas.drawCircle(p, r, Paint()
          ..color = AppColors.gold
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2.5);
      }
      // Szabad lövés: pontozott fehér gyűrű — a fedezés-hibák ránézésre
      // kirajzolódnak (hol maradt őrizetlenül a lövő).
      if (s.free == true) {
        const dots = 10;
        for (var i = 0; i < dots; i++) {
          final a = i * 2 * 3.14159265 / dots;
          canvas.drawCircle(
              p + Offset((r + 3.5) * math.cos(a), (r + 3.5) * math.sin(a)),
              0.9,
              Paint()..color = Colors.white.withOpacity(0.85));
        }
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
