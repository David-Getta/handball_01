/// Intenzitás-grafikon — a két csapat tempójának alakulása idő-ablakonként.
///
/// A computeIntensityTimeline ablakaiból vonaldiagram: y = átlagos mozgás-
/// sebesség (m/s), x = játékidő. A vonalak a csapat-identitás színeit viselik
/// (mint mindenhol az appban); a rács visszafogott; egy pontra koppintva a
/// lejátszó az ablak kezdetére ugrik. Ebből látszik, MIKOR esett vissza a
/// csapat tempója (fáradás, időkérés/letámadás hatása).
library;

import "package:flutter/material.dart";

import "../analytics/court_analytics.dart";
import "../theme/app_theme.dart";
import "anim.dart";

class IntensityChart extends StatelessWidget {
  final List<IntensityWindow> windows;
  final int totalFrames;
  final double fps;
  final String homeName;
  final String awayName;
  final void Function(int frame)? onSeekFrame;

  const IntensityChart({
    super.key,
    required this.windows,
    required this.totalFrames,
    required this.fps,
    required this.homeName,
    required this.awayName,
    this.onSeekFrame,
  });

  @override
  Widget build(BuildContext context) {
    if (windows.length < 2) return const SizedBox.shrink();
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Row(children: [
        _legendDot(AppColors.home, homeName),
        const SizedBox(width: AppSpacing.md),
        _legendDot(AppColors.away, awayName),
      ]),
      const SizedBox(height: AppSpacing.sm),
      SizedBox(
        height: 110,
        child: LayoutBuilder(builder: (context, constraints) {
          return GestureDetector(
            onTapUp: (d) => _handleTap(d.localPosition, constraints.biggest),
            // Berajzolás betöltéskor: a tempó-görbék balról jobbra épülnek.
            child: TweenAnimationBuilder<double>(
              tween: Tween(begin: 0, end: 1),
              duration: reduceMotion(context)
                  ? Duration.zero
                  : const Duration(milliseconds: 900),
              curve: Curves.easeInOutCubic,
              builder: (context, t, _) => CustomPaint(
                size: Size(constraints.maxWidth, 110),
                painter: _IntensityPainter(
                    windows: windows, totalFrames: totalFrames, fps: fps,
                    progress: t),
              ),
            ),
          );
        }),
      ),
      const SizedBox(height: 2),
      Text("átlagos mozgás-sebesség (m/s) idő-ablakonként · koppints — a lejátszó odaugrik",
          style: AppText.label.copyWith(fontSize: 10, color: AppColors.textFaint)),
    ]);
  }

  Widget _legendDot(Color color, String label) => Row(children: [
        Container(width: 8, height: 8,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
        const SizedBox(width: 6),
        Text(label, style: AppText.label.copyWith(color: AppColors.textPrimary)),
      ]);

  void _handleTap(Offset pos, Size size) {
    if (onSeekFrame == null) return;
    final geom = _IntensityGeom(size, windows, totalFrames);
    int? best;
    var bestDx = 24.0;
    for (final w in windows) {
      final x = geom.x(geom.centerFrame(w));
      final d = (x - pos.dx).abs();
      if (d < bestDx) {
        bestDx = d;
        best = w.startFrame;
      }
    }
    if (best != null) onSeekFrame!(best);
  }
}

/// A rajzoló és a koppintás közös geometriája.
class _IntensityGeom {
  final Size size;
  final List<IntensityWindow> windows;
  final int totalFrames;
  late final double maxMs;
  static const padL = 22.0, padR = 8.0, padT = 6.0, padB = 16.0;

  _IntensityGeom(this.size, this.windows, this.totalFrames) {
    var m = 0.0;
    for (final w in windows) {
      if (w.homeAvgMs > m) m = w.homeAvgMs;
      if (w.awayAvgMs > m) m = w.awayAvgMs;
    }
    maxMs = m <= 0 ? 1.0 : m * 1.15; // kis fejtér a felső pont fölött
  }

  /// Az ablak középidejének frame-je (a pont oda kerül).
  int centerFrame(IntensityWindow w) {
    final i = windows.indexOf(w);
    final next = i + 1 < windows.length
        ? windows[i + 1].startFrame
        : totalFrames;
    return (w.startFrame + next) ~/ 2;
  }

  double x(int frame) =>
      padL + (size.width - padL - padR) * frame / (totalFrames - 1);
  double y(double ms) =>
      size.height - padB - (size.height - padT - padB) * ms / maxMs;
}

class _IntensityPainter extends CustomPainter {
  final List<IntensityWindow> windows;
  final int totalFrames;
  final double fps;

  /// Berajzolás-állapot (0..1) — a betöltő animáció hajtja.
  final double progress;

  _IntensityPainter(
      {required this.windows, required this.totalFrames, required this.fps,
       this.progress = 1.0});

  @override
  void paint(Canvas canvas, Size size) {
    if (totalFrames <= 1 || windows.length < 2) return;
    final geom = _IntensityGeom(size, windows, totalFrames);
    if (progress < 1.0) {
      canvas.clipRect(Rect.fromLTRB(0, 0, size.width * progress, size.height));
    }

    // Visszafogott rács: 3 vízszintes vonal kerek m/s értékeknél.
    final grid = Paint()..color = AppColors.border.withOpacity(0.5)..strokeWidth = 1;
    final labelStyle = TextStyle(fontSize: 9, color: AppColors.textFaint);
    final step = geom.maxMs <= 2 ? 0.5 : 1.0;
    for (var v = 0.0; v <= geom.maxMs; v += step) {
      final yy = geom.y(v);
      canvas.drawLine(Offset(_IntensityGeom.padL, yy),
          Offset(size.width - _IntensityGeom.padR, yy), grid);
      _text(canvas, v == v.roundToDouble() ? "${v.toInt()}" : "$v",
          Offset(0, yy - 6), labelStyle);
    }
    final durMin = totalFrames / fps / 60.0;
    _text(canvas, "0'", Offset(_IntensityGeom.padL, size.height - 12), labelStyle);
    _text(canvas, "${durMin.toStringAsFixed(0)}'",
        Offset(size.width - _IntensityGeom.padR - 14, size.height - 12),
        labelStyle);

    // A két csapat vonala + pontjai.
    for (final (sel, color) in [
      ((IntensityWindow w) => w.homeAvgMs, AppColors.home),
      ((IntensityWindow w) => w.awayAvgMs, AppColors.away),
    ]) {
      final line = Paint()
        ..color = color
        ..strokeWidth = 2.2
        ..strokeJoin = StrokeJoin.round
        ..strokeCap = StrokeCap.round
        ..style = PaintingStyle.stroke;
      // SIMA görbe a pontokon át (Catmull-Rom → Bézier): a tempó nem
      // szögletes lépcső, hanem hullámzás — a szemnek is az.
      final pts = [
        for (final w in windows)
          Offset(geom.x(geom.centerFrame(w)), geom.y(sel(w)))
      ];
      final path = Path()..moveTo(pts.first.dx, pts.first.dy);
      for (var i = 0; i < pts.length - 1; i++) {
        final p0 = i == 0 ? pts[0] : pts[i - 1];
        final p1 = pts[i];
        final p2 = pts[i + 1];
        final p3 = i + 2 < pts.length ? pts[i + 2] : p2;
        final c1 = p1 + (p2 - p0) / 6.0;
        final c2 = p2 - (p3 - p1) / 6.0;
        path.cubicTo(c1.dx, c1.dy, c2.dx, c2.dy, p2.dx, p2.dy);
      }

      // Terület-kitöltés a görbe alatt: lefelé elhalványuló csapatszín.
      final base = size.height - _IntensityGeom.padB;
      final fill = Path.from(path)
        ..lineTo(pts.last.dx, base)
        ..lineTo(pts.first.dx, base)
        ..close();
      canvas.drawPath(
          fill,
          Paint()
            ..shader = LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [color.withOpacity(0.14), color.withOpacity(0.0)],
            ).createShader(
                Rect.fromLTRB(0, _IntensityGeom.padT, size.width, base)));
      canvas.drawPath(path, line);
      for (final p in pts) {
        canvas.drawCircle(p, 4.5, Paint()..color = AppColors.surface);
        canvas.drawCircle(p, 3.0, Paint()..color = color);
      }
    }
  }

  void _text(Canvas canvas, String s, Offset pos, TextStyle style) {
    final tp = TextPainter(
        text: TextSpan(text: s, style: style),
        textDirection: TextDirection.ltr)
      ..layout();
    tp.paint(canvas, pos);
  }

  @override
  bool shouldRepaint(covariant _IntensityPainter old) =>
      old.windows != windows || old.totalFrames != totalFrames ||
      old.progress != progress;
}
