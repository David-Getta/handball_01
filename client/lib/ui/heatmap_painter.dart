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

    // PUHA hőfoltok éles rácstéglák helyett: minden cella egy lágyan
    // elhalványuló korong a cella közepén — a szomszédos foltok
    // összemosódnak, és a kép tényleg hőtérképnek néz ki, nem mozaiknak.
    //
    // A lágyságot SUGARAS SZÍNÁTMENET adja, nem elmosás (MaskFilter):
    // a rácson 200 cella van, és cellánként egy-egy elmosás külön
    // rajz-réteget kényszerítene ki — gyengébb gépen ez akadozó
    // hőtérképet jelentene. A gradiens ugyanazt a hatást adja a GPU-n
    // egyetlen menetben.
    for (int iy = 0; iy < heatmap.binsY; iy++) {
      for (int ix = 0; ix < heatmap.binsX; ix++) {
        final value = heatmap.grid[iy][ix];
        if (value <= 0) continue;
        final intensity = value / heatmap.maxCell;
        final center = p((ix + 0.5) * cellW, (iy + 0.5) * cellH);
        final radius = (cellW * scale) * (0.95 + 0.35 * intensity);
        final rect = Rect.fromCircle(center: center, radius: radius);
        // A legforróbb cellák magja világosodik — a gócpont kiugrik.
        final core = intensity > 0.7
            ? Color.lerp(color, Colors.white,
                0.35 * (intensity - 0.7) / 0.3)!
            : color;
        canvas.drawCircle(
            center,
            radius,
            Paint()
              ..shader = RadialGradient(
                colors: [
                  core.withOpacity(0.18 + 0.45 * intensity),
                  color.withOpacity(0.10 + 0.30 * intensity),
                  color.withOpacity(0.0),
                ],
                stops: const [0.0, 0.45, 1.0],
              ).createShader(rect));
      }
    }
  }

  @override
  bool shouldRepaint(covariant HeatmapPainter old) =>
      old.heatmap != heatmap || old.color != color;
}
