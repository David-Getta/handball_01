/// Hőtérkép-rajzoló — a csapat látogatottságát rácscellákként a pályára festi.
///
/// Ugyanazt a méter→pixel skálázást használja, mint a CourtPainter, hogy a
/// hőtérkép pontosan a pályára illeszkedjen. A cella színének átlátszatlansága a
/// cellában mért látogatottsággal arányos (a legnagyobb cellához normálva).
library;

import "dart:math" as math;
import "package:flutter/material.dart";

import "../analytics/court_analytics.dart";
import "court_geometry.dart";

class HeatmapPainter extends CustomPainter {
  final Heatmap heatmap;
  final Color color;

  HeatmapPainter({required this.heatmap, this.color = const Color(0xFFE5484D)});

  @override
  void paint(Canvas canvas, Size size) {
    if (heatmap.maxCell <= 0) return;

    // Ugyanaz a skála/eltolás, mint a CourtPainter-ben (a pályára illeszkedjen).
    const margin = 24.0;
    final usableW = size.width - 2 * margin;
    final usableH = size.height - 2 * margin;
    final scale = math.min(usableW / courtLength, usableH / courtWidth);
    final originX = (size.width - courtLength * scale) / 2;
    final originY = (size.height - courtWidth * scale) / 2;

    Offset p(double mx, double my) =>
        Offset(originX + mx * scale, originY + my * scale);

    final cellW = courtLength / heatmap.binsX; // cella szélessége méterben
    final cellH = courtWidth / heatmap.binsY;

    for (int iy = 0; iy < heatmap.binsY; iy++) {
      for (int ix = 0; ix < heatmap.binsX; ix++) {
        final value = heatmap.grid[iy][ix];
        if (value <= 0) continue;
        // Normált intenzitás 0..1 → átlátszatlanság (kis alapszinttel, hogy látszódjon).
        final intensity = value / heatmap.maxCell;
        final alpha = 0.15 + 0.65 * intensity;
        final rect = Rect.fromPoints(
          p(ix * cellW, iy * cellH),
          p((ix + 1) * cellW, (iy + 1) * cellH),
        );
        canvas.drawRect(rect, Paint()..color = color.withOpacity(alpha));
      }
    }
  }

  @override
  bool shouldRepaint(covariant HeatmapPainter old) =>
      old.heatmap != heatmap || old.color != color;
}
