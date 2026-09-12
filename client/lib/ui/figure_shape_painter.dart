/// Figura-alak mini-pályán — a felderítés, a meccs-összefoglaló és a
/// szezon-nézet KÖZÖS rajzolója (a backend 6x3-as ujjlenyomat-rácsa,
/// a támadó szemszögéből, jobbra a megtámadott kapu).
library;

import "dart:math";

import "package:flutter/material.dart";

import "../theme/app_theme.dart";

/// Figura-alak mini-pályán: 6x3 rács (a backend ujjlenyomat-rácsa), a
/// cella átlátszatlansága a látogatottság; felezővonal és a két
/// kapuelőtér-ív tájolja a képet.
class FigureShapePainter extends CustomPainter {
  final List<double> shape;
  FigureShapePainter(this.shape);

  @override
  void paint(Canvas canvas, Size size) {
    const binsX = 6, binsY = 3;
    final bg = Paint()..color = AppColors.surfaceAlt;
    final r = RRect.fromRectAndRadius(Offset.zero & size, const Radius.circular(4));
    canvas.drawRRect(r, bg);
    if (shape.length == binsX * binsY) {
      final mx = shape.reduce(max);
      if (mx > 0) {
        final cw = size.width / binsX, ch = size.height / binsY;
        for (var i = 0; i < shape.length; i++) {
          final v = shape[i];
          if (v <= 0) continue;
          canvas.drawRect(
              Rect.fromLTWH((i % binsX) * cw, (i ~/ binsX) * ch, cw, ch),
              Paint()..color = AppColors.accent.withOpacity(0.08 + 0.82 * v / mx));
        }
      }
    }
    final line = Paint()
      ..color = AppColors.textFaint
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1;
    canvas.drawRRect(r, line);
    canvas.drawLine(Offset(size.width / 2, 0), Offset(size.width / 2, size.height), line);
    final arc = Paint()
      ..color = AppColors.gold
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5;
    final gr = size.height * 0.3;
    canvas.drawArc(Rect.fromCircle(center: Offset(0, size.height / 2), radius: gr),
        -pi / 2, pi, false, arc);
    canvas.drawArc(Rect.fromCircle(center: Offset(size.width, size.height / 2), radius: gr),
        pi / 2, pi, false, arc);
  }

  @override
  bool shouldRepaint(covariant FigureShapePainter old) => old.shape != shape;
}
