/// Kalibráló képernyő — a felhasználó a 4 pálya-sarkot ráhúzza a képkockára,
/// és ÉLŐBEN látja a pálya-modellt (négyszög + középvonal + 6 m + kapuk) ráugrani.
///
/// A 4 sarok = teljes homográfia (kép ↔ valós pálya). Ebből lesz a pontos
/// felülnézet és a pályán kívüliek (kispad/edző) szűrése. A referencia-képkockát
/// éles használatban a backend adja a feltöltött videóból; itt egy helyőrző mutatja
/// a UX-et. A számítás a homography.dart-tal (a backend tükre).
library;

import "dart:math" as math;
import "package:flutter/material.dart";

import "../analytics/homography.dart";
import "../theme/app_theme.dart";
import "court_geometry.dart";
import "shell/app_shell.dart";

class CalibrationScreen extends StatefulWidget {
  const CalibrationScreen({super.key});

  @override
  State<CalibrationScreen> createState() => _CalibrationScreenState();
}

class _CalibrationScreenState extends State<CalibrationScreen> {
  // A 4 sarok a kép-területen belül, arányban (0..1), hogy méretfüggetlen legyen.
  // Sorrend: távoli-bal, távoli-jobb, közeli-jobb, közeli-bal.
  List<Offset> _corners = const [
    Offset(0.20, 0.35), Offset(0.75, 0.32), Offset(0.90, 0.72), Offset(0.10, 0.78),
  ];
  int? _drag;
  bool _saved = false;

  @override
  Widget build(BuildContext context) {
    return AppShell(
      active: NavId.upload,
      crumbTag: "1e",
      crumbPath: "KALIBRÁCIÓ · PÁLYA ILLESZTÉSE",
      collapsed: true,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text("Pálya-kalibráció", style: AppText.title),
          const SizedBox(height: 4),
          Text("Húzd a 4 sarkot a pálya sarkaira — a modell élőben illeszkedik.", style: AppText.subtitle),
          const SizedBox(height: AppSpacing.lg),
          Expanded(
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Expanded(child: _frameCard()),
                const SizedBox(width: AppSpacing.lg),
                SizedBox(width: 280, child: _sidePanel()),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _frameCard() {
    return Container(
      decoration: AppTheme.card(),
      clipBehavior: Clip.antiAlias,
      child: LayoutBuilder(
        builder: (context, c) {
          final size = Size(c.maxWidth, c.maxHeight);
          final pts = [for (final f in _corners) Offset(f.dx * size.width, f.dy * size.height)];
          return GestureDetector(
            onPanStart: (d) {
              double best = 32;
              _drag = null;
              for (int i = 0; i < pts.length; i++) {
                final dist = (pts[i] - d.localPosition).distance;
                if (dist < best) { best = dist; _drag = i; }
              }
            },
            onPanUpdate: (d) {
              if (_drag == null) return;
              setState(() {
                _corners = [..._corners];
                _corners[_drag!] = Offset(
                  (d.localPosition.dx / size.width).clamp(0.0, 1.0),
                  (d.localPosition.dy / size.height).clamp(0.0, 1.0),
                );
                _saved = false;
              });
            },
            onPanEnd: (_) => _drag = null,
            child: CustomPaint(painter: _CalibPainter(pts), size: size),
          );
        },
      ),
    );
  }

  Widget _sidePanel() {
    return Container(
      decoration: AppTheme.card(),
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text("SARKOK", style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.sm),
          _cornerRow("Távoli-bal", 0),
          _cornerRow("Távoli-jobb", 1),
          _cornerRow("Közeli-jobb", 2),
          _cornerRow("Közeli-bal", 3),
          const Spacer(),
          Text(
            "Éles használatban ide a feltöltött videó egy képkockája kerül; a 4 "
            "sarokból a rendszer kiszámolja a homográfiát, és a pályán kívüli "
            "személyeket (kispad, edző) automatikusan kiszűri.",
            style: AppText.label.copyWith(fontSize: 11),
          ),
          const SizedBox(height: AppSpacing.md),
          FilledButton.icon(
            style: FilledButton.styleFrom(backgroundColor: AppColors.accent, foregroundColor: AppColors.onAccent),
            onPressed: () => setState(() => _saved = true),
            icon: const Icon(Icons.check),
            label: Text(_saved ? "Kalibráció mentve" : "Kalibráció mentése"),
          ),
        ],
      ),
    );
  }

  Widget _cornerRow(String name, int i) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
          Row(children: [
            Container(width: 10, height: 10, decoration: const BoxDecoration(color: AppColors.accent, shape: BoxShape.circle)),
            const SizedBox(width: 8),
            Text(name, style: AppText.label.copyWith(color: AppColors.textPrimary)),
          ]),
          Text("${(_corners[i].dx * 100).round()}, ${(_corners[i].dy * 100).round()}",
              style: AppText.label.copyWith(fontSize: 11)),
        ]),
      );
}

/// Kirajzolja a referencia-helyőrzőt + a húzható sarkokat + a pálya-modellt.
class _CalibPainter extends CustomPainter {
  final List<Offset> corners; // 4 kép-pont (pixel)
  _CalibPainter(this.corners);

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(Offset.zero & size, Paint()..color = const Color(0xFF0C1119));
    final hint = TextPainter(
      text: TextSpan(text: "referencia képkocka", style: AppText.label.copyWith(color: AppColors.textFaint)),
      textDirection: TextDirection.ltr,
    )..layout();
    hint.paint(canvas, const Offset(16, 12));

    // Homográfia: pálya-sarkok (méter) -> a húzott kép-pontok.
    final courtCorners = [
      [0.0, 0.0], [courtLength, 0.0], [courtLength, courtWidth], [0.0, courtWidth],
    ];
    final dst = [for (final c in corners) [c.dx, c.dy]];
    final h = homographyFromPoints(courtCorners, dst);
    Offset p(double mx, double my) {
      final r = applyHomography(h, mx, my);
      return Offset(r[0], r[1]);
    }

    final line = Paint()..color = AppColors.accent..style = PaintingStyle.stroke..strokeWidth = 2.5;
    final gold = Paint()..color = AppColors.gold..style = PaintingStyle.stroke..strokeWidth = 2;
    final goalP = Paint()..color = AppColors.away..style = PaintingStyle.stroke..strokeWidth = 4;

    final path = Path()..moveTo(corners[0].dx, corners[0].dy);
    for (int i = 1; i < 4; i++) { path.lineTo(corners[i].dx, corners[i].dy); }
    path.close();
    canvas.drawPath(path, line);
    canvas.drawLine(p(courtLength / 2, 0), p(courtLength / 2, courtWidth), line);

    const cy = courtWidth / 2;
    canvas.drawLine(p(0, cy - 1.5), p(0, cy + 1.5), goalP);
    canvas.drawLine(p(courtLength, cy - 1.5), p(courtLength, cy + 1.5), goalP);

    for (final gx in [0.0, courtLength]) {
      final s = gx == courtLength ? -1.0 : 1.0;
      Offset? prev;
      for (int i = 0; i <= 20; i++) {
        final th = math.pi * i / 20;
        final cur = p(gx + s * 6 * math.sin(th), cy - 6 * math.cos(th));
        if (prev != null) canvas.drawLine(prev, cur, gold);
        prev = cur;
      }
    }

    for (final c in corners) {
      canvas.drawCircle(c, 11, Paint()..color = AppColors.accent.withOpacity(0.25));
      canvas.drawCircle(c, 7, Paint()..color = AppColors.accent);
      canvas.drawCircle(c, 7, Paint()..color = Colors.white..style = PaintingStyle.stroke..strokeWidth = 1.5);
    }
  }

  @override
  bool shouldRepaint(covariant _CalibPainter old) => old.corners != corners;
}
