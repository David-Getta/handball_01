/// Meccs-sztori idővonal — a mérkőzés története egyetlen sávon.
///
/// A lejátszó felett mutatja, hol történtek a fordulópontok: gólok
/// (csapatszínű pöttyök), válasz nélküli gól-sorozatok (halvány sávok),
/// emberelőnyök (arany felső csík), 7 a 6-os szakaszok (türkiz alsó csík)
/// és hétméteresek (arany rombusz). Koppintásra a lejátszó odaugrik.
library;

import "package:flutter/material.dart";

import "../theme/app_theme.dart";

class StoryTimeline extends StatefulWidget {
  final int totalFrames;
  final double fps;
  final List<Map<String, dynamic>> events;     // gól-pöttyökhöz
  final List<Map<String, dynamic>> runs;       // gól-sorozat sávok
  final List<Map<String, dynamic>> powerplays; // emberelőny-csíkok
  final List<Map<String, dynamic>> sevens;     // hétméteres jelölők
  final List<Map<String, dynamic>> emptyNets;  // 7 a 6 szakaszok
  final List<Map<String, dynamic>> subs;       // cserehullám-jelölők
  final List<Map<String, dynamic>> stoppages;  // időkérés/megszakítás sávok
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
    this.stoppages = const [],
    this.currentFrame = 0,
    this.onSeek,
  });

  @override
  State<StoryTimeline> createState() => _StoryTimelineState();
}

class _StoryTimelineState extends State<StoryTimeline> {
  /// Az egér vízszintes helye a sávon (px) — a hover-előnézethez. Null,
  /// ha az egér nincs a sávon (érintésnél mindig null marad).
  double? _hoverX;

  // A widget mezőit rövidítve érjük el (a törzs a régi kód marad).
  int get totalFrames => widget.totalFrames;
  double get fps => widget.fps;
  List<Map<String, dynamic>> get events => widget.events;
  List<Map<String, dynamic>> get runs => widget.runs;
  List<Map<String, dynamic>> get powerplays => widget.powerplays;
  List<Map<String, dynamic>> get sevens => widget.sevens;
  List<Map<String, dynamic>> get emptyNets => widget.emptyNets;
  List<Map<String, dynamic>> get subs => widget.subs;
  List<Map<String, dynamic>> get stoppages => widget.stoppages;
  int get currentFrame => widget.currentFrame;
  void Function(int frame)? get onSeek => widget.onSeek;

  bool get _hasContent =>
      events.any((e) => e["type"] == "goal") ||
      runs.isNotEmpty || powerplays.isNotEmpty ||
      sevens.isNotEmpty || emptyNets.isNotEmpty || subs.isNotEmpty ||
      stoppages.isNotEmpty;

  @override
  Widget build(BuildContext context) {
    if (totalFrames <= 1 || !_hasContent) return const SizedBox.shrink();
    return Column(mainAxisSize: MainAxisSize.min, children: [
      LayoutBuilder(builder: (context, c) {
        return MouseRegion(
          cursor: SystemMouseCursors.click,
          // Hover-előnézet: az egér alatt megjelenik a cél-időpont, így a
          // koppintás előtt LÁTSZIK, hova fog ugrani a lejátszó.
          onHover: (e) => setState(() => _hoverX = e.localPosition.dx),
          onExit: (_) => setState(() => _hoverX = null),
          child: GestureDetector(
            onTapUp: (d) {
              if (onSeek == null) return;
              final frac = (d.localPosition.dx / c.maxWidth).clamp(0.0, 1.0);
              onSeek!((frac * (totalFrames - 1)).round());
            },
            child: CustomPaint(
              size: Size(c.maxWidth, 30),
              painter: _StoryPainter(
                totalFrames: totalFrames,
                fps: fps,
                events: events,
                runs: runs,
                powerplays: powerplays,
                sevens: sevens,
                emptyNets: emptyNets,
                subs: subs,
                stoppages: stoppages,
                currentFrame: currentFrame,
                hoverX: _hoverX,
              ),
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
        if (stoppages.isNotEmpty)
          _legend(AppColors.textFaint.withOpacity(0.5), "időkérés"),
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
  final double fps;
  final double? hoverX;
  final List<Map<String, dynamic>> events;
  final List<Map<String, dynamic>> runs;
  final List<Map<String, dynamic>> powerplays;
  final List<Map<String, dynamic>> sevens;
  final List<Map<String, dynamic>> emptyNets;
  final List<Map<String, dynamic>> subs;
  final List<Map<String, dynamic>> stoppages;
  final int currentFrame;

  _StoryPainter({
    required this.totalFrames,
    required this.fps,
    this.hoverX,
    required this.events,
    required this.runs,
    required this.powerplays,
    required this.sevens,
    required this.emptyNets,
    required this.subs,
    required this.stoppages,
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
        Paint()
          ..shader = LinearGradient(colors: [
            AppColors.surfaceAlt,
            Color.lerp(AppColors.surfaceAlt, Colors.white, 0.10)!,
            AppColors.surfaceAlt,
          ]).createShader(Rect.fromLTWH(0, midY - 1.5, size.width, 3)));

    // Megszakítások (időkérés): szürke sáv — a játék állt.
    for (final w in stoppages) {
      final a = _x((w["start_frame"] as num?) ?? 0, size);
      final b = _x((w["end_frame"] as num?) ?? 0, size);
      canvas.drawRect(Rect.fromLTRB(a, 2, b <= a ? a + 2 : b, size.height - 2),
          Paint()..color = AppColors.textFaint.withOpacity(0.18));
    }

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
      _softGlow(canvas, Offset(x, midY), 9, color.withOpacity(0.34));
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

    // Hover-előnézet: halvány vonal + a cél-időpont buborékban — a
    // koppintás előtt látszik, hova ugrik a lejátszó.
    final hx = hoverX;
    if (hx != null && hx >= 0 && hx <= size.width) {
      canvas.drawLine(
          Offset(hx, 0),
          Offset(hx, size.height),
          Paint()
            ..color = AppColors.accent.withOpacity(0.55)
            ..strokeWidth = 1.0);
      final frame = (hx / size.width * (totalFrames - 1)).round();
      final secs = fps > 0 ? frame / fps : 0.0;
      final label = "${(secs ~/ 60)}:"
          "${(secs % 60).floor().toString().padLeft(2, "0")}";
      final tp = TextPainter(
        text: TextSpan(
            text: label,
            style: const TextStyle(
                fontSize: 10,
                fontWeight: FontWeight.w600,
                color: AppColors.textPrimary)),
        textDirection: TextDirection.ltr,
      )..layout();
      final bw = tp.width + 10, bh = tp.height + 4;
      var bx = hx - bw / 2;
      if (bx < 0) bx = 0;
      if (bx + bw > size.width) bx = size.width - bw;
      final box = RRect.fromRectAndRadius(
          Rect.fromLTWH(bx, -bh - 2, bw, bh), const Radius.circular(5));
      canvas.drawRRect(box, Paint()..color = AppColors.bgSidebar);
      canvas.drawRRect(
          box,
          Paint()
            ..color = AppColors.accent.withOpacity(0.6)
            ..style = PaintingStyle.stroke
            ..strokeWidth = 1);
      tp.paint(canvas, Offset(bx + 5, -bh));
    }

    // Lejátszófej: fehér függőleges vonal az aktuális kockánál, finom
    // ragyogással és felső fogantyúval — messziről is megtalálható.
    final px = _x(currentFrame, size);
    // A lejátszófej ragyogása: vízszintesen elhalványuló sáv (nem
    // elmosás) — a sáv a lejátszás alatt MINDEN képkockán újrarajzolódik.
    canvas.drawRect(
        Rect.fromLTRB(px - 4, 0, px + 4, size.height),
        Paint()
          ..shader = LinearGradient(
            colors: [
              Colors.white.withOpacity(0),
              Colors.white.withOpacity(0.35),
              Colors.white.withOpacity(0),
            ],
          ).createShader(
              Rect.fromLTRB(px - 4, 0, px + 4, size.height)));
    canvas.drawLine(
        Offset(px, 0),
        Offset(px, size.height),
        Paint()
          ..color = Colors.white.withOpacity(0.9)
          ..strokeWidth = 1.4);
    canvas.drawPath(
        Path()
          ..moveTo(px - 3.5, 0)
          ..lineTo(px + 3.5, 0)
          ..lineTo(px, 4.5)
          ..close(),
        Paint()..color = Colors.white.withOpacity(0.9));
  }

  /// Puha kör-ragyogás elmosás nélkül (sugaras színátmenet). A sáv a
  /// lejátszófej mozgásával MINDEN képkockán újrarajzolódik, és minden
  /// gól-pötty egy-egy elmosása külön rajz-menetet kényszerítene ki —
  /// negyven gólnál ez képkockánként negyven extra menet.
  void _softGlow(Canvas canvas, Offset center, double radius, Color color) {
    canvas.drawCircle(
        center,
        radius,
        Paint()
          ..shader = RadialGradient(
            colors: [color, color.withOpacity(0)],
            stops: const [0.40, 1.0],
          ).createShader(Rect.fromCircle(center: center, radius: radius)));
  }

  @override
  bool shouldRepaint(covariant _StoryPainter old) =>
      old.currentFrame != currentFrame ||
      old.hoverX != hoverX ||
      old.totalFrames != totalFrames ||
      old.events != events ||
      old.runs != runs ||
      old.powerplays != powerplays ||
      old.sevens != sevens ||
      old.emptyNets != emptyNets ||
      old.subs != subs ||
      old.stoppages != stoppages;
}
