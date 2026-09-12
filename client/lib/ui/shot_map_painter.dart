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

  /// Megjelenés-állapot (0..1): a jelölők LÉPCSŐZVE pattannak be, amikor
  /// a nézet lövéstérképre vált. Egy csapásra megjelenő pontfelhőt a
  /// szem egyben lát; a sorban érkező jelölőket egyenként veszi észre —
  /// és mellékesen a lövések SORRENDJE is látszik.
  final double progress;

  ShotMapPainter({required this.shots, required this.currentFrame,
                  this.progress = 1.0});

  @override
  void paint(Canvas canvas, Size size) {
    final (scale, origin) = CourtPainter.transformFor(size);
    if (scale <= 0) return;
    for (final (i, s) in shots.indexed) {
      // Lépcsőzött bepattanás: az i-edik jelölő a saját kis ablakában
      // nő teljes méretre (a lista végére is jut idő).
      final span = 1.0 / (shots.length + 3);
      final local =
          ((progress - i * span) / (4 * span)).clamp(0.0, 1.0).toDouble();
      if (local <= 0) continue;
      // Enyhe túllövés a végén: a jelölő "leül" a helyére.
      final grow = local < 1.0
          ? 1.0 - math.pow(1.0 - local, 3).toDouble() * (1.0 - 0.08)
          : 1.0;
      final p = Offset(origin.dx + s.x * scale, origin.dy + s.y * scale);
      final teamColor = s.team == Team.home ? AppColors.home : AppColors.away;
      final active = s.t == currentFrame;
      // A jelölő mérete a helyzet értéke (xG): a nagy körök a nagy
      // helyzetek — ránézésre látszik, hol puskáztunk el ziccert.
      final base =
          s.xg == null ? 6.0 : 4.0 + 5.0 * (s.xg!.clamp(0.0, 0.9) / 0.9);
      final r = (active ? base + 2.5 : base) * grow;
      // Gól: puha csapatszínű ragyogás a jelölő mögött — a térkép
      // "forró pontjai" ránézésre kiugranak.
      if (s.goal) {
        _softGlow(canvas, p, r + 8, teamColor.withOpacity(0.34));
      }
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

  /// Puha kör-ragyogás elmosás nélkül. A térkép a bepattanás-animáció
  /// alatt képkockánként újrarajzolódik, és gólonként egy-egy elmosás
  /// külön rajz-menetet kényszerítene ki.
  void _softGlow(Canvas canvas, Offset center, double radius, Color color) {
    canvas.drawCircle(
        center,
        radius,
        Paint()
          ..shader = RadialGradient(
            colors: [color, color.withOpacity(0)],
            stops: const [0.40, 1.0],
          ).createShader(Rect.fromCircle(center: center, radius: radius)));
  }

  @override
  bool shouldRepaint(covariant ShotMapPainter old) =>
      old.shots != shots || old.currentFrame != currentFrame ||
      old.progress != progress;
}
