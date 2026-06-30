/// Figura-tervező — az edző a felülnézeti pályán mozgatja a támadókat, és
/// lejátszatja a figurát a TANULT védelem ellen, kiértékeléssel.
///
/// Két kulcs-pozíció (Kezdő / Vég) közt húzhatók a támadók; lejátszáskor a kettő
/// között interpolálunk, a védők a tanult modell szerint reagálnak. A szimuláció
/// kliensoldalon fut (analytics/play_simulation.dart).
library;

import "dart:async";
import "package:flutter/material.dart";

import "../analytics/play_simulation.dart";
import "../models/tracking.dart";
import "../theme/app_theme.dart";
import "court_geometry.dart";
import "court_painter.dart";

class DesignerScreen extends StatefulWidget {
  final Match match; // ebből tanuljuk a védelmet
  const DesignerScreen({super.key, required this.match});

  @override
  State<DesignerScreen> createState() => _DesignerScreenState();
}

class _DesignerScreenState extends State<DesignerScreen> {
  // 5 támadó, két kulcs-pozícióval (0 = Kezdő, 1 = Vég).
  late List<List<Offset>> _attackers;
  int _editStep = 0;
  int? _dragIndex;

  late int _numDefenders;
  double _lineDepth = 6.0;

  bool _playing = false;
  Match? _sim;
  SetPlayEvaluation? _eval;
  int _playIndex = 0;
  Timer? _timer;

  static const int _animSteps = 40;

  @override
  void initState() {
    super.initState();
    // A védelmet a betöltött meccsből tanuljuk (létszám + mélység).
    final learned = learnDefense(widget.match, Team.away);
    _numDefenders = learned.numDefenders;
    _lineDepth = learned.lineDepthM.clamp(4.0, 12.0).toDouble();

    // Alap figura: irányító, két átlövő, szélső, beálló — az edző átrendezi.
    _attackers = [
      [const Offset(22, 10), const Offset(22, 10)], // irányító (labdás)
      [const Offset(24, 5), const Offset(28, 5)],   // bal átlövő
      [const Offset(24, 15), const Offset(28, 15)], // jobb átlövő
      [const Offset(28, 2), const Offset(31, 2)],   // szélső
      [const Offset(30, 10), const Offset(34, 10)], // beálló (a kapu felé gördül)
    ];
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  DefenseModel get _model => DefenseModel(numDefenders: _numDefenders, lineDepthM: _lineDepth);

  void _onPan(Offset localPos, Size size, {bool start = false}) {
    if (_playing) return;
    final tr = CourtTransform.fit(size);
    final court = tr.toCourt(localPos.dx, localPos.dy);
    if (start) {
      // A legközelebbi támadó kiválasztása (kb. 2.5 m-en belül).
      int? best;
      double bestD = 2.5;
      for (int i = 0; i < _attackers.length; i++) {
        final p = _attackers[i][_editStep];
        final d = (p - court).distance;
        if (d < bestD) {
          bestD = d;
          best = i;
        }
      }
      _dragIndex = best;
    }
    if (_dragIndex != null) {
      setState(() {
        _attackers[_dragIndex!][_editStep] = Offset(
          court.dx.clamp(0.0, courtLength).toDouble(),
          court.dy.clamp(0.0, courtWidth).toDouble(),
        );
      });
    }
  }

  void _play() {
    // A két kulcs-pozíció között interpolálunk _animSteps lépésre.
    final interp = <List<Offset>>[];
    for (final a in _attackers) {
      final path = <Offset>[];
      for (int s = 0; s < _animSteps; s++) {
        final t = s / (_animSteps - 1);
        path.add(Offset.lerp(a[0], a[1], t)!);
      }
      interp.add(path);
    }
    final setplay = SetPlay(interp, List<int>.filled(_animSteps, 0));
    final sim = simulateSetPlay(setplay, _model);
    final eval = evaluateSetPlay(sim);

    setState(() {
      _sim = sim;
      _eval = eval;
      _playing = true;
      _playIndex = 0;
    });
    _timer?.cancel();
    _timer = Timer.periodic(const Duration(milliseconds: 40), (_) {
      setState(() {
        if (_playIndex < _animSteps - 1) {
          _playIndex++;
        } else {
          _timer?.cancel();
        }
      });
    });
  }

  void _backToEdit() {
    _timer?.cancel();
    setState(() {
      _playing = false;
      _sim = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              _header(),
              const SizedBox(height: AppSpacing.lg),
              Expanded(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Expanded(child: _courtCard()),
                    const SizedBox(width: AppSpacing.lg),
                    SizedBox(width: 300, child: _sidePanel()),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _header() => Row(
        children: [
          IconButton(
            onPressed: () => Navigator.of(context).pop(),
            icon: const Icon(Icons.arrow_back, color: AppColors.textSecondary),
          ),
          const SizedBox(width: AppSpacing.sm),
          const Text("FIGURA-TERVEZŐ", style: AppText.brand),
          const SizedBox(width: 8),
          Text("· tanult védelem ellen", style: AppText.label),
        ],
      );

  Widget _courtCard() {
    return Container(
      decoration: AppTheme.card(),
      padding: const EdgeInsets.all(AppSpacing.md),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final size = Size(constraints.maxWidth, constraints.maxHeight);
          if (_playing && _sim != null) {
            // Lejátszás: a szimulált frame-et a fő pálya-rajzolóval mutatjuk.
            return CustomPaint(painter: CourtPainter(frame: _sim!.frames[_playIndex]), size: size);
          }
          // Szerkesztés: húzható támadók + a védelem előnézete.
          return GestureDetector(
            onPanStart: (d) => _onPan(d.localPosition, size, start: true),
            onPanUpdate: (d) => _onPan(d.localPosition, size),
            onPanEnd: (_) => _dragIndex = null,
            child: CustomPaint(
              painter: _DesignerPainter(attackers: _attackers, step: _editStep, model: _model),
              size: size,
            ),
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
          Text("KULCS-POZÍCIÓ", style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.sm),
          SegmentedButton<int>(
            showSelectedIcon: false,
            segments: const [
              ButtonSegment(value: 0, label: Text("Kezdő")),
              ButtonSegment(value: 1, label: Text("Vég")),
            ],
            selected: {_editStep},
            onSelectionChanged: _playing ? null : (s) => setState(() => _editStep = s.first),
          ),
          const SizedBox(height: AppSpacing.xl),
          Text("TANULT VÉDELEM", style: AppText.sectionLabel),
          const SizedBox(height: AppSpacing.sm),
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
            Text("Védők", style: AppText.label),
            Text("$_numDefenders", style: AppText.value),
          ]),
          Row(mainAxisAlignment: MainAxisAlignment.spaceBetween, children: [
            Text("Vonalmélység", style: AppText.label),
            Text("${_lineDepth.toStringAsFixed(1)} m", style: AppText.value),
          ]),
          Slider(
            value: _lineDepth, min: 4, max: 12,
            onChanged: _playing ? null : (v) => setState(() => _lineDepth = v),
          ),
          const Spacer(),
          if (_eval != null) _evalCard(_eval!),
          const SizedBox(height: AppSpacing.md),
          _playing
              ? OutlinedButton.icon(
                  onPressed: _backToEdit,
                  icon: const Icon(Icons.edit),
                  label: const Text("Vissza a szerkesztéshez"),
                )
              : FilledButton.icon(
                  onPressed: _play,
                  style: FilledButton.styleFrom(backgroundColor: AppColors.accent, foregroundColor: const Color(0xFF06231F)),
                  icon: const Icon(Icons.play_arrow),
                  label: const Text("Lejátszás a védelem ellen"),
                ),
        ],
      ),
    );
  }

  Widget _evalCard(SetPlayEvaluation e) {
    final pct = (e.bestShotValue * 100).toStringAsFixed(0);
    final quality = e.bestShotValue >= 0.4 ? "Kiváló helyzet" : e.bestShotValue >= 0.2 ? "Ígéretes" : "Nehéz helyzet";
    return Container(
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.accentSoft,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.accent.withOpacity(0.4)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text("EREDMÉNY", style: AppText.sectionLabel.copyWith(color: AppColors.accent)),
          const SizedBox(height: 6),
          Text("$pct%", style: AppText.valueBig.copyWith(color: AppColors.accent)),
          Text("legjobb lövőhelyzet · $quality", style: AppText.label.copyWith(fontSize: 11)),
          if (e.attackerId != null)
            Text("játékos #${e.attackerId}", style: AppText.label.copyWith(fontSize: 11)),
        ],
      ),
    );
  }
}

/// A szerkesztő-réteg rajzolója: pálya + húzható támadók + védelem-előnézet.
class _DesignerPainter extends CustomPainter {
  final List<List<Offset>> attackers;
  final int step;
  final DefenseModel model;

  _DesignerPainter({required this.attackers, required this.step, required this.model});

  @override
  void paint(Canvas canvas, Size size) {
    final tr = CourtTransform.fit(size);
    _drawCourt(canvas, tr);

    // Védelem-előnézet (a labda az 1. támadónál).
    final ballY = attackers[0][step].dy;
    final defs = model.respond(ballY, courtLength);
    for (final d in defs) {
      final c = tr.toScreen(d.dx, d.dy);
      canvas.drawCircle(c, 0.6 * tr.scale, Paint()..color = AppColors.away.withOpacity(0.45));
    }

    // Támadók (húzható tokenek).
    for (int i = 0; i < attackers.length; i++) {
      final p = attackers[i][step];
      final c = tr.toScreen(p.dx, p.dy);
      canvas.drawCircle(c, 0.85 * tr.scale, Paint()..color = AppColors.home.withOpacity(0.18));
      canvas.drawCircle(c, 0.65 * tr.scale, Paint()..color = AppColors.home);
      _label(canvas, c, "${i + 1}", 0.65 * tr.scale);
    }

    // Labda (az 1. támadónál).
    final b = tr.toScreen(attackers[0][step].dx, attackers[0][step].dy);
    canvas.drawCircle(b, 0.32 * tr.scale, Paint()..color = AppColors.ball);
  }

  void _drawCourt(Canvas canvas, CourtTransform tr) {
    final fill = Paint()..color = AppColors.courtFill;
    final line = Paint()
      ..color = AppColors.courtLine
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.4;
    final rect = Rect.fromPoints(tr.toScreen(0, 0), tr.toScreen(courtLength, courtWidth));
    final rrect = RRect.fromRectAndRadius(rect, const Radius.circular(10));
    canvas.drawRRect(rrect, fill);
    canvas.drawRRect(rrect, line);
    canvas.drawLine(tr.toScreen(courtLength / 2, 0), tr.toScreen(courtLength / 2, courtWidth), line);
    for (final leftSide in [true, false]) {
      final pts = goalAreaBoundary(leftSide: leftSide).map((o) => tr.toScreen(o.dx, o.dy)).toList();
      final path = Path()..moveTo(pts.first.dx, pts.first.dy);
      for (final pt in pts.skip(1)) {
        path.lineTo(pt.dx, pt.dy);
      }
      path.close();
      canvas.drawPath(path, Paint()..color = AppColors.accent.withOpacity(0.07));
      canvas.drawPath(path, line);
    }
  }

  void _label(Canvas canvas, Offset center, String text, double radius) {
    final tp = TextPainter(
      text: TextSpan(text: text, style: TextStyle(color: Colors.white, fontSize: radius * 0.85, fontWeight: FontWeight.bold)),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(canvas, center - Offset(tp.width / 2, tp.height / 2));
  }

  @override
  bool shouldRepaint(covariant _DesignerPainter old) =>
      old.attackers != attackers || old.step != step || old.model.lineDepthM != model.lineDepthM;
}
