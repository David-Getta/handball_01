/// Felülnézeti pálya-rajzoló (CustomPainter) — prémium sötét megjelenés.
///
/// Kirajzolja a 40x20 m-es pályát (finom vonalak, 6 m-es kapuelőterek, kapuk),
/// majd az adott frame játékosait és a labdát. A méteres koordinátákat pixelre
/// skálázza, az arányt (2:1) megtartva.
///
/// Megjelenítési elvek:
/// - MÉRT játékos: tele token, finom külső gyűrűvel; BECSÜLT játékos: halvány +
///   szaggatott gyűrű (bizonytalanság).
/// - A csapatszínek MEGJELENÍTÉSI színek (nem a valódi mez).
library;

import "dart:math" as math;
import "package:flutter/material.dart";

import "../models/tracking.dart";
import "../theme/app_theme.dart";
import "court_geometry.dart";

/// A két csapat MEGJELENÍTÉSI színe (nem a valódi mez!).
class DisplayColors {
  final Color home;
  final Color away;
  const DisplayColors({this.home = AppColors.home, this.away = AppColors.away});
}

class CourtPainter extends CustomPainter {
  final Frame? frame;
  final DisplayColors colors;

  CourtPainter({required this.frame, this.colors = const DisplayColors()});

  @override
  void paint(Canvas canvas, Size size) {
    const margin = 28.0;
    final usableW = size.width - 2 * margin;
    final usableH = size.height - 2 * margin;
    final scale = math.min(usableW / courtLength, usableH / courtWidth);
    final originX = (size.width - courtLength * scale) / 2;
    final originY = (size.height - courtWidth * scale) / 2;

    Offset p(double mx, double my) =>
        Offset(originX + mx * scale, originY + my * scale);

    _drawCourt(canvas, p, scale);
    _drawFrame(canvas, p, scale);
  }

  void _drawCourt(Canvas canvas, Offset Function(double, double) p, double scale) {
    final fill = Paint()..color = AppColors.courtFill;
    final line = Paint()
      ..color = AppColors.courtLine
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.4;

    // Pálya háttér (lekerekített) + finom keret.
    final court = Rect.fromPoints(p(0, 0), p(courtLength, courtWidth));
    final rrect = RRect.fromRectAndRadius(court, const Radius.circular(10));
    canvas.drawRRect(rrect, fill);
    canvas.drawRRect(rrect, line);

    // Középvonal + középkör (diszkrét).
    canvas.drawLine(p(courtLength / 2, 0), p(courtLength / 2, courtWidth), line);
    canvas.drawCircle(p(courtLength / 2, courtWidth / 2), 2.0 * scale, line);

    // 6 m-es kapuelőterek — a támadott oldalt finom akcentus-tint jelzi.
    for (final leftSide in [true, false]) {
      final pts = goalAreaBoundary(leftSide: leftSide).map((o) => p(o.dx, o.dy)).toList();
      final path = Path()..moveTo(pts.first.dx, pts.first.dy);
      for (final pt in pts.skip(1)) {
        path.lineTo(pt.dx, pt.dy);
      }
      path.close();
      canvas.drawPath(path, Paint()..color = AppColors.accent.withOpacity(0.07));
      canvas.drawPath(path, line);
    }

    // Kapuk (a gólvonal közepén, 3 m szélesen).
    final goalPaint = Paint()
      ..color = AppColors.textSecondary
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3;
    final cy = courtWidth / 2;
    canvas.drawLine(p(0, cy - 1.5), p(0, cy + 1.5), goalPaint);
    canvas.drawLine(p(courtLength, cy - 1.5), p(courtLength, cy + 1.5), goalPaint);
  }

  void _drawFrame(Canvas canvas, Offset Function(double, double) p, double scale) {
    final f = frame;
    if (f == null) return;

    for (final pl in f.players) {
      final base = pl.team == Team.home ? colors.home : colors.away;
      final center = p(pl.x, pl.y);
      final radius = 0.6 * scale;

      if (pl.isEstimated) {
        canvas.drawCircle(center, radius, Paint()..color = base.withOpacity(0.22));
        _drawDashedRing(canvas, center, radius + 2, base.withOpacity(0.55));
      } else {
        // Finom külső "halo" + tele token + vékony világos perem.
        canvas.drawCircle(center, radius + 3, Paint()..color = base.withOpacity(0.16));
        canvas.drawCircle(center, radius, Paint()..color = base);
        canvas.drawCircle(
            center, radius,
            Paint()
              ..color = Colors.white.withOpacity(0.85)
              ..style = PaintingStyle.stroke
              ..strokeWidth = 1.2);
      }

      if (pl.jerseyNumber != null) {
        _drawLabel(canvas, center, "${pl.jerseyNumber}", radius);
      }
    }

    // Labda — meleg szín, finom izzással.
    final ball = f.ball;
    if (ball != null) {
      final c = p(ball.x, ball.y);
      canvas.drawCircle(c, 0.6 * scale, Paint()..color = AppColors.ball.withOpacity(0.25));
      canvas.drawCircle(c, 0.34 * scale, Paint()..color = AppColors.ball);
    }
  }

  void _drawDashedRing(Canvas canvas, Offset center, double radius, Color color) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.4;
    const dashes = 16;
    for (int i = 0; i < dashes; i++) {
      if (i.isOdd) continue;
      final a0 = (2 * math.pi) * (i / dashes);
      final a1 = (2 * math.pi) * ((i + 1) / dashes);
      canvas.drawArc(Rect.fromCircle(center: center, radius: radius), a0, a1 - a0, false, paint);
    }
  }

  void _drawLabel(Canvas canvas, Offset center, String text, double radius) {
    final tp = TextPainter(
      text: TextSpan(
        text: text,
        style: TextStyle(
          color: Colors.white,
          fontSize: math.max(8, radius * 0.85),
          fontWeight: FontWeight.bold,
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(canvas, center - Offset(tp.width / 2, tp.height / 2));
  }

  @override
  bool shouldRepaint(covariant CourtPainter old) => old.frame != frame;
}
