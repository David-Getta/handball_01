/// Eredmény-alakulás grafikon — halmozott gólok lépcsős vonala csapatonként.
///
/// A felismert gól-eseményekből rajzolja a két csapat góljainak alakulását a
/// játékidő mentén (lépcsős vonal, a gólok pontokkal jelölve). Egy gólra
/// koppintva a lejátszó a jelenetre ugrik. A színek a csapat-identitást
/// követik (ugyanaz a kék/piros, mint a pályán és a statisztikában);
/// mindkét vonal közvetlen feliratot kap (végi állás), a rács visszafogott.
library;

import "package:flutter/material.dart";

import "../theme/app_theme.dart";

class ScoreChart extends StatelessWidget {
  /// A gól-események: {"t": képkocka, "team": "home"|"away"} (időrendben).
  final List<Map<String, dynamic>> goals;
  final int totalFrames;
  final double fps;
  final String homeName;
  final String awayName;
  final void Function(int frame)? onSeekFrame;

  /// Gól-sorozatok a backendtől: {"team", "start_frame", "end_frame",
  /// "length", ...} — halvány csapatszínű sávként kiemelve a grafikonon.
  final List<Map<String, dynamic>> runs;

  const ScoreChart({
    super.key,
    required this.goals,
    required this.totalFrames,
    required this.fps,
    required this.homeName,
    required this.awayName,
    this.onSeekFrame,
    this.runs = const [],
  });

  @override
  Widget build(BuildContext context) {
    if (goals.isEmpty) return const SizedBox.shrink();
    final homeGoals = goals.where((g) => g["team"] == "home").length;
    final awayGoals = goals.length - homeGoals;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      // Jelmagyarázat (2 sorozat → mindig van) + végeredmény.
      Row(children: [
        _legendDot(AppColors.home, "$homeName $homeGoals"),
        const SizedBox(width: AppSpacing.md),
        _legendDot(AppColors.away, "$awayName $awayGoals"),
      ]),
      const SizedBox(height: AppSpacing.sm),
      SizedBox(
        height: 120,
        child: LayoutBuilder(builder: (context, constraints) {
          return GestureDetector(
            onTapUp: (d) => _handleTap(d.localPosition, constraints.biggest),
            // Berajzolás-animáció: a vonalak balról jobbra "íródnak ki"
            // (mint egy élő közvetítés idővonala) — egyszer, betöltéskor.
            child: TweenAnimationBuilder<double>(
              tween: Tween(begin: 0, end: 1),
              duration: const Duration(milliseconds: 900),
              curve: Curves.easeInOutCubic,
              builder: (context, t, _) => CustomPaint(
                size: Size(constraints.maxWidth, 120),
                painter: _ScoreChartPainter(
                    goals: goals, totalFrames: totalFrames, fps: fps,
                    runs: runs, progress: t),
              ),
            ),
          );
        }),
      ),
      const SizedBox(height: 2),
      Text(
          runs.isEmpty
              ? "a színes mező a vezetés (szín = ki vezet, vastagság = "
                  "mennyivel) · koppints egy gólra — a lejátszó odaugrik"
              : "a színes mező a vezetés, a függőleges sávok gól-sorozatok "
                  "· koppints egy gólra vagy sávra",
          style: AppText.label.copyWith(fontSize: 10, color: AppColors.textFaint)),
    ]);
  }

  Widget _legendDot(Color color, String label) => Row(children: [
        Container(width: 8, height: 8,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
        const SizedBox(width: 6),
        Text(label, style: AppText.label.copyWith(color: AppColors.textPrimary)),
      ]);

  /// Koppintás: a legközelebbi gól-jelölő megkeresése (bő találati sávval),
  /// és a lejátszó odaugrasztása.
  void _handleTap(Offset pos, Size size) {
    if (onSeekFrame == null || totalFrames <= 1) return;
    final geom = _ChartGeom(size, goals, totalFrames);
    int? bestFrame;
    var bestDist = 24.0; // találati sugár px-ben (bőven a jelölő fölött)
    var home = 0, away = 0;
    for (final g in goals) {
      final t = (g["t"] as num?)?.toInt() ?? 0;
      if (g["team"] == "home") home++; else away++;
      final count = g["team"] == "home" ? home : away;
      final p = geom.point(t, count);
      final d = (p - pos).distance;
      if (d < bestDist) {
        bestDist = d;
        bestFrame = t;
      }
    }
    if (bestFrame != null) { onSeekFrame!(bestFrame); return; }
    // Nem gól-jelölő: ha az x egy sorozat-sávba esik, a sorozat elejére.
    final fx = geom.x(0), lx = geom.x(totalFrames - 1);
    for (final r in runs) {
      final s0 = (r["start_frame"] as num?)?.toInt() ?? 0;
      final s1 = (r["end_frame"] as num?)?.toInt() ?? s0;
      final xa = geom.x(s0).clamp(fx, lx), xb = geom.x(s1).clamp(fx, lx);
      if (pos.dx >= xa - 6 && pos.dx <= xb + 6) { onSeekFrame!(s0); return; }
    }
  }
}

/// A rajzoló és a koppintás-kezelő KÖZÖS geometriája (px ↔ adat leképezés).
class _ChartGeom {
  final Size size;
  final int totalFrames;
  final int maxGoals;
  static const padL = 18.0, padR = 12.0, padT = 6.0, padB = 16.0;

  _ChartGeom(this.size, List<Map<String, dynamic>> goals, this.totalFrames)
      : maxGoals = _maxCount(goals);

  static int _maxCount(List<Map<String, dynamic>> goals) {
    var home = 0, away = 0;
    for (final g in goals) {
      if (g["team"] == "home") home++; else away++;
    }
    final m = home > away ? home : away;
    return m < 1 ? 1 : m;
  }

  double x(int frame) =>
      padL + (size.width - padL - padR) * frame / (totalFrames - 1);
  double y(int count) =>
      size.height - padB - (size.height - padT - padB) * count / maxGoals;
  Offset point(int frame, int count) => Offset(x(frame), y(count));
}

class _ScoreChartPainter extends CustomPainter {
  final List<Map<String, dynamic>> goals;
  final int totalFrames;
  final double fps;
  final List<Map<String, dynamic>> runs;

  /// Berajzolás-állapot (0..1): ekkora hányadáig látszik a grafikon
  /// balról — a betöltő animáció hajtja.
  final double progress;

  _ScoreChartPainter(
      {required this.goals, required this.totalFrames, required this.fps,
       this.runs = const [], this.progress = 1.0});

  @override
  void paint(Canvas canvas, Size size) {
    if (totalFrames <= 1) return;
    final geom = _ChartGeom(size, goals, totalFrames);

    // A berajzolás-animáció: a vászon jobb széle még "üres".
    if (progress < 1.0) {
      canvas.clipRect(Rect.fromLTRB(0, 0, size.width * progress, size.height));
    }

    // Gól-sorozatok: halvány csapatszínű sáv a teljes magasságban, a rács
    // és a vonalak MÖGÉ. Így a fordulópontok ránézésre kirajzolódnak.
    final topY = _ChartGeom.padT, botY = size.height - _ChartGeom.padB;
    for (final r in runs) {
      final s0 = (r["start_frame"] as num?)?.toInt() ?? 0;
      final s1 = (r["end_frame"] as num?)?.toInt() ?? s0;
      final color = r["team"] == "home" ? AppColors.home : AppColors.away;
      final xa = geom.x(s0.clamp(0, totalFrames - 1));
      final xb = geom.x(s1.clamp(0, totalFrames - 1));
      final rect = Rect.fromLTRB(xa, topY, xb <= xa ? xa + 2 : xb, botY);
      canvas.drawRect(rect, Paint()..color = color.withOpacity(0.13));
      // A sorozat hossza a sáv tetején (pl. "4-0"), mellette a felismert
      // LEHETSÉGES OK (pl. "emberelőnyben") — ha a backend adott ilyet.
      final len = (r["length"] as num?)?.toInt() ?? 0;
      if (len > 0) {
        final ctx = (r["context"] as List?)?.cast<String>() ?? const [];
        final label = ctx.isEmpty ? "$len-0" : "$len-0 · ${ctx.first}";
        _text(canvas, label,
            Offset(xa + 2, topY - 1),
            TextStyle(fontSize: 9, fontWeight: FontWeight.w600, color: color));
      }
    }

    // Vezetés-sáv: a két lépcső KÖZÖTTI terület a VEZETŐ színével, a
    // fedettség a különbséggel nő. Eddig a "ki vezetett és mennyivel"
    // kérdést a néző fejben vonta ki a két vonalból — most a szem
    // szintjén dől el: ahol kék a mező, a hazai vezetett, és minél
    // vastagabb, annál nagyobb volt az előny.
    {
      var h = 0, a = 0;
      var prevX = geom.x(0);
      void band(double x0, double x1, int hh, int aa) {
        if (hh == aa || x1 <= x0) return;
        final leader = hh > aa ? AppColors.home : AppColors.away;
        final gap = (hh - aa).abs();
        canvas.drawRect(
            Rect.fromLTRB(x0, geom.y(hh > aa ? hh : aa), x1,
                geom.y(hh > aa ? aa : hh)),
            Paint()
              ..color = leader
                  .withOpacity((0.09 + 0.04 * gap).clamp(0.09, 0.32)));
      }

      for (final g in goals) {
        final gx = geom.x(((g["t"] as num?)?.toInt() ?? 0)
            .clamp(0, totalFrames - 1));
        band(prevX, gx, h, a);
        if (g["team"] == "home") { h++; } else { a++; }
        prevX = gx;
      }
      band(prevX, geom.x(totalFrames - 1), h, a);
    }

    // Visszafogott rács: legfeljebb 4 vízszintes vonal, egész gól-értékeknél.
    final grid = Paint()..color = AppColors.border.withOpacity(0.5)..strokeWidth = 1;
    final step = (geom.maxGoals / 4).ceil().clamp(1, 1 << 30);
    final labelStyle = TextStyle(fontSize: 9, color: AppColors.textFaint);
    for (var v = 0; v <= geom.maxGoals; v += step) {
      final yy = geom.y(v);
      canvas.drawLine(Offset(_ChartGeom.padL, yy),
          Offset(size.width - _ChartGeom.padR, yy), grid);
      _text(canvas, "$v", Offset(0, yy - 6), labelStyle);
    }
    // Idő-tengely: kezdő és záró időcímke (percben) — nem zsúfolunk.
    final durMin = totalFrames / fps / 60.0;
    _text(canvas, "0'", Offset(_ChartGeom.padL, size.height - 12), labelStyle);
    _text(canvas, "${durMin.toStringAsFixed(0)}'",
        Offset(size.width - _ChartGeom.padR - 4, size.height - 12), labelStyle);

    // Lépcsős vonalak + gól-jelölők csapatonként.
    for (final (team, color) in [("home", AppColors.home), ("away", AppColors.away)]) {
      final line = Paint()
        ..color = color
        ..strokeWidth = 2.2
        ..strokeJoin = StrokeJoin.round
        ..strokeCap = StrokeCap.round
        ..style = PaintingStyle.stroke;
      final path = Path()..moveTo(geom.x(0), geom.y(0));
      var count = 0;
      final markers = <Offset>[];
      for (final g in goals) {
        if (g["team"] != team) continue;
        final t = (g["t"] as num?)?.toInt() ?? 0;
        path.lineTo(geom.x(t), geom.y(count)); // vízszintes a gólig
        count++;
        path.lineTo(geom.x(t), geom.y(count)); // fel a gólnál
        markers.add(geom.point(t, count));
      }
      path.lineTo(geom.x(totalFrames - 1), geom.y(count)); // kifutás a végéig

      // Terület-kitöltés a vonal alatt: csapatszínű, lefelé elhalványuló
      // színátmenet — a "ki uralta a meccset" ránézésre is látszik.
      final fill = Path.from(path)
        ..lineTo(geom.x(totalFrames - 1), geom.y(0))
        ..lineTo(geom.x(0), geom.y(0))
        ..close();
      canvas.drawPath(
          fill,
          Paint()
            ..shader = LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [color.withOpacity(0.07), color.withOpacity(0.0)],
            ).createShader(Rect.fromLTRB(0, _ChartGeom.padT, size.width,
                size.height - _ChartGeom.padB)));
      canvas.drawPath(path, line);
      // Gól-pontok: puha ragyogással és felület-színű gyűrűvel, hogy
      // metszésnél is elváljanak. (A végállást a jelmagyarázat mutatja.)
      for (final m in markers) {
        canvas.drawCircle(
            m,
            9,
            Paint()
              ..color = color.withOpacity(0.28)
              ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 6));
        canvas.drawCircle(m, 5.5, Paint()..color = AppColors.surface);
        canvas.drawCircle(m, 3.5, Paint()..color = color);
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
  bool shouldRepaint(covariant _ScoreChartPainter old) =>
      old.goals != goals || old.totalFrames != totalFrames ||
      old.fps != fps || old.runs != runs || old.progress != progress;
}
