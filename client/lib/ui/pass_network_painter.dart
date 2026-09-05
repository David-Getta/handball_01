/// Passzháló-rajzoló — a csapat passz-szerkezete a felülnézeti pályán.
///
/// A csomópontok a játékosok átlagos helyén ülnek (mezszámmal), méretük a
/// passz-részvétellel nő; az élek vastagsága a két játékos közti passzok
/// számával. A ritka (1 passzos) éleket halványabban rajzoljuk, hogy a
/// domináns kapcsolatok ugorjanak ki — az edző a játék "gerincét" látja.
library;

import "package:flutter/material.dart";

import "../analytics/court_analytics.dart";
import "../models/tracking.dart";
import "../theme/app_theme.dart";
import "court_painter.dart";

class PassNetworkPainter extends CustomPainter {
  final PassNetwork network;
  final Team team;
  PassNetworkPainter({required this.network, required this.team});

  @override
  void paint(Canvas canvas, Size size) {
    final (scale, origin) = CourtPainter.transformFor(size);
    if (scale <= 0 || network.nodes.isEmpty) return;
    final color = team == Team.home ? AppColors.home : AppColors.away;
    final pos = {
      for (final n in network.nodes)
        n.trackId: Offset(origin.dx + n.x * scale, origin.dy + n.y * scale)
    };
    final maxCount = network.edges.isEmpty ? 1 : network.edges.first.count;

    // Élek (a csomópontok alatt): finoman ÍVELT vonalak — a sűrű háló
    // egyenes vonalakkal "drótkerítés", ívekkel olvasható szövet lesz.
    // Vastagság és fedettség a passz-számmal.
    for (final e in network.edges) {
      final a = pos[e.a], b = pos[e.b];
      if (a == null || b == null) continue;
      final frac = e.count / maxCount;
      final mid = Offset((a.dx + b.dx) / 2, (a.dy + b.dy) / 2);
      final d = b - a;
      final norm = d.distance == 0 ? Offset.zero
          : Offset(-d.dy, d.dx) / d.distance;
      final ctrl = mid + norm * (d.distance * 0.08);
      final path = Path()
        ..moveTo(a.dx, a.dy)
        ..quadraticBezierTo(ctrl.dx, ctrl.dy, b.dx, b.dy);
      canvas.drawPath(path, Paint()
        ..color = color.withOpacity(0.25 + 0.55 * frac)
        ..strokeWidth = 1.5 + 4.5 * frac
        ..style = PaintingStyle.stroke
        ..strokeCap = StrokeCap.round);
    }

    // Csomópontok: méret a részvétellel; mezszám (vagy track-id) felirattal.
    var maxInv = 1;
    for (final n in network.nodes) {
      if (n.involvement > maxInv) maxInv = n.involvement;
    }
    for (final n in network.nodes) {
      final p = pos[n.trackId]!;
      final r = 8.0 + 5.0 * (n.involvement / maxInv);
      // A legaktívabb ember puha ragyogást kap: a játék "gerince"
      // ránézésre kiugrik.
      //
      // Itt az elmosás MEGENGEDETT (máshol őr-teszt tiltja): a
      // passzháló nem rajzolódik újra képkockánként — a shouldRepaint
      // csak a hálóra és a csapatra néz, a lejátszófej mozgására nem —,
      // és csapatonként EGYETLEN ilyen ragyogás van.
      if (n.involvement == maxInv) {
        canvas.drawCircle(
            p,
            r + 8,
            Paint()
              ..color = color.withOpacity(0.30)
              ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 8));
      }
      canvas.drawCircle(p, r + 2, Paint()..color = AppColors.surface);
      // Enyhe sugaras átmenet: a korong nem "matrica", hanem gomb.
      canvas.drawCircle(
          p,
          r,
          Paint()
            ..shader = RadialGradient(colors: [
              Color.lerp(color, Colors.white, 0.22)!,
              color,
            ]).createShader(Rect.fromCircle(center: p, radius: r)));
      final label = n.jerseyNumber?.toString() ?? "${n.trackId}";
      final tp = TextPainter(
        text: TextSpan(text: label, style: TextStyle(
            fontSize: r >= 11 ? 11.0 : 9.0,
            fontWeight: FontWeight.w700,
            color: Colors.white)),
        textDirection: TextDirection.ltr,
      )..layout();
      tp.paint(canvas, p - Offset(tp.width / 2, tp.height / 2));
    }
  }

  @override
  bool shouldRepaint(covariant PassNetworkPainter old) =>
      old.network != network || old.team != team;
}
