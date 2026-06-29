/// Felülnézeti pálya-rajzoló (CustomPainter).
///
/// Kirajzolja a 40x20 m-es pályát (vonalak, középvonal, 6 m-es kapuelőterek,
/// kapuk), majd az adott frame játékosait és a labdát. A méteres koordinátákat
/// pixelre skálázza, az arányt (2:1) megtartva.
///
/// Megjelenítési elvek:
/// - MÉRT játékos: tele pont; BECSÜLT játékos: halvány + szaggatott gyűrű
///   (mert a pozíciója bizonytalan — lásd a backend [F] becslőjét).
/// - A csapatszínek itt MEGJELENÍTÉSI színek (nem a valódi mezszín). A valódi
///   mezszínek meccsenként változnak; a kliens egyértelmű, jól elkülönülő
///   színekkel rajzol (alapból kék vs piros).
library;

import "dart:math" as math;
import "package:flutter/material.dart";

import "../models/tracking.dart";
import "court_geometry.dart";

/// A két csapat MEGJELENÍTÉSI színe (nem a valódi mez!).
class DisplayColors {
  final Color home;
  final Color away;
  const DisplayColors({this.home = const Color(0xFF1E66F5), this.away = const Color(0xFFE5484D)});
}

class CourtPainter extends CustomPainter {
  final Frame? frame;
  final DisplayColors colors;

  CourtPainter({required this.frame, this.colors = const DisplayColors()});

  @override
  void paint(Canvas canvas, Size size) {
    // 1) Skála és eltolás: a 40x20 m fér bele a vászonba, peremmel, arány megtartva.
    const margin = 24.0;
    final usableW = size.width - 2 * margin;
    final usableH = size.height - 2 * margin;
    final scale = math.min(usableW / courtLength, usableH / courtWidth);
    final originX = (size.width - courtLength * scale) / 2;
    final originY = (size.height - courtWidth * scale) / 2;

    // Méter -> pixel leképezés.
    Offset p(double mx, double my) =>
        Offset(originX + mx * scale, originY + my * scale);

    _drawCourt(canvas, p, scale);
    _drawFrame(canvas, p, scale);
  }

  void _drawCourt(Canvas canvas, Offset Function(double, double) p, double scale) {
    final bg = Paint()..color = const Color(0xFF2B6CB0).withOpacity(0.12);
    final line = Paint()
      ..color = Colors.white70
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2;

    // Pálya háttér + keret.
    final court = Rect.fromPoints(p(0, 0), p(courtLength, courtWidth));
    canvas.drawRect(court, bg);
    canvas.drawRect(court, line);

    // Középvonal.
    canvas.drawLine(p(courtLength / 2, 0), p(courtLength / 2, courtWidth), line);

    // 6 m-es kapuelőterek (sárgásan kitöltve — a valódi pályán is sárga).
    final areaFill = Paint()..color = const Color(0xFFF4C430).withOpacity(0.30);
    for (final leftSide in [true, false]) {
      final pts = goalAreaBoundary(leftSide: leftSide).map((o) => p(o.dx, o.dy)).toList();
      final path = Path()..moveTo(pts.first.dx, pts.first.dy);
      for (final pt in pts.skip(1)) {
        path.lineTo(pt.dx, pt.dy);
      }
      path.close();
      canvas.drawPath(path, areaFill);
      canvas.drawPath(path, line);
    }

    // Kapuk (a gólvonal közepén, 3 m szélesen) — vastag vonalka.
    final goalPaint = Paint()
      ..color = Colors.white
      ..style = PaintingStyle.stroke
      ..strokeWidth = 4;
    final cy = courtWidth / 2;
    canvas.drawLine(p(0, cy - 1.5), p(0, cy + 1.5), goalPaint);
    canvas.drawLine(p(courtLength, cy - 1.5), p(courtLength, cy + 1.5), goalPaint);
  }

  void _drawFrame(Canvas canvas, Offset Function(double, double) p, double scale) {
    final f = frame;
    if (f == null) return;

    // Játékosok.
    for (final pl in f.players) {
      final base = pl.team == Team.home ? colors.home : colors.away;
      final center = p(pl.x, pl.y);
      final radius = 0.55 * scale; // ~0.55 m sugarú pont

      if (pl.isEstimated) {
        // BECSÜLT: halvány kitöltés + szaggatott gyűrű (bizonytalanság jelzése).
        final fill = Paint()..color = base.withOpacity(0.30);
        canvas.drawCircle(center, radius, fill);
        _drawDashedRing(canvas, center, radius + 2, base.withOpacity(0.6));
      } else {
        // MÉRT: tele pont fehér kerettel.
        canvas.drawCircle(center, radius, Paint()..color = base);
        canvas.drawCircle(
            center,
            radius,
            Paint()
              ..color = Colors.white
              ..style = PaintingStyle.stroke
              ..strokeWidth = 1.5);
      }

      // Mezszám (ha ismert).
      if (pl.jerseyNumber != null) {
        _drawLabel(canvas, center, "${pl.jerseyNumber}", radius);
      }
    }

    // Labda.
    final ball = f.ball;
    if (ball != null) {
      final c = p(ball.x, ball.y);
      canvas.drawCircle(c, 0.35 * scale, Paint()..color = const Color(0xFFFF8800));
      canvas.drawCircle(
          c,
          0.35 * scale,
          Paint()
            ..color = Colors.black
            ..style = PaintingStyle.stroke
            ..strokeWidth = 1.2);
    }
  }

  /// Szaggatott gyűrű a becsült játékos köré (a bizonytalanság jelzése).
  void _drawDashedRing(Canvas canvas, Offset center, double radius, Color color) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5;
    const dashes = 16;
    for (int i = 0; i < dashes; i++) {
      if (i.isOdd) continue; // minden második szakaszt kihagyunk → szaggatott
      final a0 = (2 * math.pi) * (i / dashes);
      final a1 = (2 * math.pi) * ((i + 1) / dashes);
      final rect = Rect.fromCircle(center: center, radius: radius);
      canvas.drawArc(rect, a0, a1 - a0, false, paint);
    }
  }

  /// Mezszám-felirat a pont közepére.
  void _drawLabel(Canvas canvas, Offset center, String text, double radius) {
    final tp = TextPainter(
      text: TextSpan(
        text: text,
        style: TextStyle(
          color: Colors.white,
          fontSize: math.max(8, radius * 0.9),
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
