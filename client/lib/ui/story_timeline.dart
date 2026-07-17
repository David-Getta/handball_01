/// Meccs-sztori idővonal — a mérkőzés története egyetlen sávon.
///
/// A lejátszó felett mutatja, hol történtek a fordulópontok: gólok
/// (csapatszínű pöttyök), válasz nélküli gól-sorozatok (halvány sávok),
/// emberelőnyök (arany felső csík), 7 a 6-os szakaszok (türkiz alsó csík)
/// és hétméteresek (arany rombusz). Koppintásra a lejátszó odaugrik.
library;

import "package:flutter/material.dart";

import "../theme/app_theme.dart";

class StoryTimeline extends StatelessWidget {
  final int totalFrames;
  final double fps;
  final List<Map<String, dynamic>> events;     // gól-pöttyökhöz
  final List<Map<String, dynamic>> runs;       // gól-sorozat sávok
  final List<Map<String, dynamic>> powerplays; // emberelőny-csíkok
  final List<Map<String, dynamic>> sevens;     // hétméteres jelölők
  final List<Map<String, dynamic>> emptyNets;  // 7 a 6 szakaszok
  final List<Map<String, dynamic>> subs;       // cserehullám-jelölők
  final int currentFrame;
  final void Function(int frame)? onSeek;

  const StoryTimeline({
    super.key,
    required this.totalFrames,
    required this.fps,
    this.events = const [],
    this.runs = const [],
    this.powerplays = const [],
    this.sevens = const [],
    this.emptyNets = const [],
    this.subs = const [],
    this.currentFrame = 0,
    this.onSeek,
  });

  bool get _hasContent =>
      events.any((e) => e["type"] == "goal") ||
      runs.isNotEmpty || powerplays.isNotEmpty ||
      sevens.isNotEmpty || emptyNets.isNotEmpty || subs.isNotEmpty;

  @override
  Widget build(BuildContext context) {
    if (totalFrames <= 1 || !_hasContent) return const SizedBox.shrink();
    return Column(mainAxisSize: MainAxisSize.min, children: [
      LayoutBuilder(builder: (context, c) {
        return GestureDetector(
          onTapUp: (d) {
            if (onSeek == null) return;
            final frac = (d.localPosition.dx / c.maxWidth).clamp(0.0, 1.0);
            onSeek!((frac * (totalFrames - 1)).round());
          },
          child: CustomPaint(
            size: Size(c.maxWidth, 30),
            painter: _StoryPainter(
              totalFrames: totalFrames,
              events: events,
              runs: runs,
              powerplays: powerplays,
              sevens: sevens,
              emptyNets: emptyNets,
              subs: subs,
              currentFrame: currentFrame,
            ),
          ),
        );
      }),
      const SizedBox(height: 2),
      // Apró jelmagyarázat — csak azok az elemek, amikből van a meccsen.
      Wrap(spacing: 10, children: [
        if (events.any((e) => e["type"] == "goal"))
          _legend(AppColors.gold, "gól", shape: BoxShape.circle),
        if (runs.isNotEmpty) _legend(AppColors.home.withOpacity(0.4), "sorozat"),
        if (powerplays.isNotEmpty) _legend(AppColors.gold.withOpacity(0.6), "emberelőny"),
        if (emptyNets.isNotEmpty) _legend(AppColors.accent.withOpacity(0.7), "7 a 6"),
        if (sevens.isNotEmpty) _legend(AppColors.gold, "7 m"),
        if (subs.isNotEmpty)
          _legend(AppColors.textFaint, "csere"),
      ]),
    ]);
  }

  Widget _legend(Color color, String label,
      {BoxShape shape = BoxShape.rectangle}) {
    return Row(mainAxisSize: MainAxisSize.min, children: [
      Container(
          width: 7,
          height: 7,
          decoration: BoxDecoration(
              color: color,
              shape: shape,
              borderRadius:
                  shape == BoxShape.rectangle ? BorderRadius.circular(2) : null)),
      const SizedBox(width: 4),
      Text(label,
          style: AppText.label.copyWith(fontSize: 9.5, color: AppColors.textFaint)),
    ]);
  }
}

class _StoryPainter extends CustomPainter {
  final int totalFrames;
  final List<Map<String, dynamic>> events;
  final List<Map<String, dynamic>> runs;
  final List<Map<String, dynamic>> powerplays;
  final List<Map<String, dynamic>> sevens;
  final List<Map<String, dynamic>> emptyNets;
  final List<Map<String, dynamic>> subs;
  final int currentFrame;

  _StoryPainter({
    required this.totalFrames,
    required this.events,
    required this.runs,
    required this.powerplays,
    required this.sevens,
    required this.emptyNets,
    required this.subs,
    required this.currentFrame,
  });

  double _x(num frame, Size size) =>
      size.width * (frame.toDouble() / (totalFrames - 1)).clamp(0.0, 1.0);

  @override
  void paint(Canvas canvas, Size size) {
    final midY = size.height / 2;

    // Alap-sáv.
    canvas.drawRRect(
        RRect.fromRectAndRadius(
            Rect.fromLTWH(0, midY - 1.5, size.width, 3), const Radius.circular(2)),
        Paint()..color = AppColors.surfaceAlt);

    // Gól-sorozat sávok: teljes magasságú, halvány csapatszínű hátterek.
    for (final r in runs) {
      final a = _x((r["start_frame"] as num?) ?? 0, size);
      final b = _x((r["end_frame"] as num?) ?? 0, size);
      final color = r["team"] == "home" ? AppColors.home : AppColors.away;
      canvas.drawRect(Rect.fromLTRB(a, 2, b <= a ? a + 2 : b, size.height - 2),
          Paint()..color = color.withOpacity(0.13));
    }

    // Emberelőnyök: arany csík a sáv TETEJÉN (az előnyben lévő oldala
    // mindegy a sávnak — a részletet a szűrő-nézet adja).
    for (final w in powerplays) {
      final a = _x((w["start_frame"] as num?) ?? 0, size);
      final b = _x((w["end_frame"] as num?) ?? 0, size);
      canvas.drawRRect(
          RRect.fromRectAndRadius(
              Rect.fromLTRB(a, 2, b <= a ? a + 2 : b, 7), const Radius.circular(2)),
          Paint()..color = AppColors.gold.withOpacity(0.55));
    }

    // 7 a 6 szakaszok: türkiz csík a sáv ALJÁN.
    for (final w in emptyNets) {
      final a = _x((w["start_frame"] as num?) ?? 0, size);
      final b = _x((w["end_frame"] as num?) ?? 0, size);
      canvas.drawRRect(
          RRect.fromRectAndRadius(
              Rect.fromLTRB(a, size.height - 7, b <= a ? a + 2 : b, size.height - 2),
              const Radius.circular(2)),
          Paint()..color = AppColors.accent.withOpacity(0.6));
    }

    // Cserehullámok: halvány függőleges pipa-vonás az alsó harmadban —
    // a csapat oldalát a szín jelzi (halványan, hogy ne nyomja el a gólokat).
    for (final e in subs) {
      final x = _x((e["t"] as num?) ?? 0, size);
      final color = e["team"] == "home" ? AppColors.home : AppColors.away;
      canvas.drawLine(
          Offset(x, size.height - 10),
          Offset(x, size.height - 2),
          Paint()
            ..color = color.withOpacity(0.55)
            ..strokeWidth = 2);
    }

    // Hétméteresek: arany rombusz a felső harmadban.
    for (final s in sevens) {
      final x = _x((s["t"] as num?) ?? 0, size);
      final path = Path()
        ..moveTo(x, 4)
        ..lineTo(x + 3.5, 8)
        ..lineTo(x, 12)
        ..lineTo(x - 3.5, 8)
        ..close();
      canvas.drawPath(path, Paint()..color = AppColors.gold);
    }

    // Gólok: csapatszínű pöttyök a középvonalon, arany gyűrűvel.
    for (final e in events) {
      if (e["type"] != "goal") continue;
      final x = _x((e["t"] as num?) ?? 0, size);
      final color = e["team"] == "home" ? AppColors.home : AppColors.away;
      canvas.drawCircle(Offset(x, midY), 4.4, Paint()..color = AppColors.surface);
      canvas.drawCircle(Offset(x, midY), 3.2, Paint()..color = color);
      canvas.drawCircle(
          Offset(x, midY),
          3.2,
          Paint()
            ..color = AppColors.gold
            ..style = PaintingStyle.stroke
            ..strokeWidth = 1.2);
    }

    // Lejátszófej: fehér függőleges vonal az aktuális kockánál.
    final px = _x(currentFrame, size);
    canvas.drawLine(
        Offset(px, 0),
        Offset(px, size.height),
        Paint()
          ..color = Colors.white.withOpacity(0.75)
          ..strokeWidth = 1.4);
  }

  @override
  bool shouldRepaint(covariant _StoryPainter old) =>
      old.currentFrame != currentFrame ||
      old.totalFrames != totalFrames ||
      old.events != events ||
      old.runs != runs ||
      old.powerplays != powerplays ||
      old.sevens != sevens ||
      old.emptyNets != emptyNets ||
      old.subs != subs;
}
