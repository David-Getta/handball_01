/// Felülnézeti pálya-rajzoló (CustomPainter) — prémium sötét megjelenés.
///
/// Kirajzolja a 40x20 m-es pályát (finom vonalak, 6 m-es kapuelőterek, kapuk),
/// majd az adott frame játékosait és a labdát. A méteres koordinátákat pixelre
/// skálázza, az arányt (2:1) megtartva.
///
/// Megjelenítési elvek:
/// - MÉRT játékos: tele token, finom külső gyűrűvel; BECSÜLT játékos: halvány +
///   szaggatott gyűrű (bizonytalanság).
/// - A csapatszínek MEGJELENÍTÉSI színek (nem a valódi mez).
library;

import "dart:math" as math;
import "package:flutter/material.dart";

import "../models/tracking.dart";
import "../theme/app_theme.dart";
import "court_geometry.dart";

/// A két csapat MEGJELENÍTÉSI színe (nem a valódi mez!).
class DisplayColors {
  final Color home;
  final Color away;
  const DisplayColors({this.home = AppColors.home, this.away = AppColors.away});
}

class CourtPainter extends CustomPainter {
  final Frame? frame;
  final DisplayColors colors;

  /// A kijelölt játékos track-azonosítója (kattintással) — arany kiemelés.
  final int? selectedId;

  /// A kijelölt játékos nyomvonala MÉTERBEN (± pár másodperc útvonala).
  final List<Offset>? trail;

  CourtPainter({
    required this.frame,
    this.colors = const DisplayColors(),
    this.selectedId,
    this.trail,
  });

  /// A méter→pixel transzformáció paraméterei az adott vászonméretre
  /// (skála + origó). A kattintás-visszafejtés (találat-keresés) UGYANEZT
  /// használja, így a kép és a találat mindig egybeesik.
  static (double, Offset) transformFor(Size size) {
    const margin = 28.0;
    final usableW = size.width - 2 * margin;
    final usableH = size.height - 2 * margin;
    final scale = math.min(usableW / courtLength, usableH / courtWidth);
    final originX = (size.width - courtLength * scale) / 2;
    final originY = (size.height - courtWidth * scale) / 2;
    return (scale, Offset(originX, originY));
  }

  @override
  void paint(Canvas canvas, Size size) {
    final (scale, origin) = transformFor(size);

    Offset p(double mx, double my) =>
        Offset(origin.dx + mx * scale, origin.dy + my * scale);

    _drawCourt(canvas, p, scale);
    _drawTrail(canvas, p, scale);
    _drawFrame(canvas, p, scale);
  }

  /// A kijelölt játékos útvonala — a játékos-pontok ALATT, arany vonallal.
  void _drawTrail(Canvas canvas, Offset Function(double, double) p, double scale) {
    final tr = trail;
    if (tr == null || tr.length < 2) return;
    final path = Path()..moveTo(p(tr.first.dx, tr.first.dy).dx, p(tr.first.dx, tr.first.dy).dy);
    for (final o in tr.skip(1)) {
      final pt = p(o.dx, o.dy);
      path.lineTo(pt.dx, pt.dy);
    }
    canvas.drawPath(
        path,
        Paint()
          ..color = AppColors.gold.withOpacity(0.75)
          ..style = PaintingStyle.stroke
          ..strokeWidth = 2.2
          ..strokeCap = StrokeCap.round
          ..strokeJoin = StrokeJoin.round);
    // A nyomvonal kezdőpontja: kis pötty, hogy látszódjon az irány.
    canvas.drawCircle(p(tr.first.dx, tr.first.dy), 3,
        Paint()..color = AppColors.gold.withOpacity(0.5));
  }

  void _drawCourt(Canvas canvas, Offset Function(double, double) p, double scale) {
    final fill = Paint()..color = AppColors.courtFill;
    final line = Paint()
      ..color = AppColors.courtLine
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.4;

    // Pálya háttér (lekerekített) + finom keret.
    final court = Rect.fromPoints(p(0, 0), p(courtLength, courtWidth));
    final rrect = RRect.fromRectAndRadius(court, const Radius.circular(10));
    canvas.drawRRect(rrect, fill);
    canvas.drawRRect(rrect, line);

    // Középvonal + középkör (diszkrét).
    canvas.drawLine(p(courtLength / 2, 0), p(courtLength / 2, courtWidth), line);
    canvas.drawCircle(p(courtLength / 2, courtWidth / 2), 2.0 * scale, line);

    // 6 m-es kapuelőterek — a támadott oldalt finom akcentus-tint jelzi.
    for (final leftSide in [true, false]) {
      final pts = goalAreaBoundary(leftSide: leftSide).map((o) => p(o.dx, o.dy)).toList();
      final path = Path()..moveTo(pts.first.dx, pts.first.dy);
      for (final pt in pts.skip(1)) {
        path.lineTo(pt.dx, pt.dy);
      }
      path.close();
      canvas.drawPath(path, Paint()..color = AppColors.accent.withOpacity(0.07));
      canvas.drawPath(path, line);
    }

    // Kapuk (a gólvonal közepén, 3 m szélesen).
    final goalPaint = Paint()
      ..color = AppColors.textSecondary
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3;
    final cy = courtWidth / 2;
    canvas.drawLine(p(0, cy - 1.5), p(0, cy + 1.5), goalPaint);
    canvas.drawLine(p(courtLength, cy - 1.5), p(courtLength, cy + 1.5), goalPaint);
  }

  void _drawFrame(Canvas canvas, Offset Function(double, double) p, double scale) {
    final f = frame;
    if (f == null) return;

    // A labdás játékos (a labdához legközelebbi) — őt arany gyűrűvel emeljük ki.
    int? carrierId;
    final ball = f.ball;
    if (ball != null && f.players.isNotEmpty) {
      double bestD = double.infinity;
      for (final pl in f.players) {
        final dx = pl.x - ball.x, dy = pl.y - ball.y;
        final d = dx * dx + dy * dy;
        if (d < bestD) {
          bestD = d;
          carrierId = pl.trackId;
        }
      }
    }

    for (final pl in f.players) {
      final base = pl.team == Team.home ? colors.home : colors.away;
      final center = p(pl.x, pl.y);
      final radius = 0.6 * scale;

      // Kijelölt játékos: vastag arany gyűrű (mért és becsült pontnál is).
      final isSelected = pl.trackId == selectedId;
      if (isSelected) {
        canvas.drawCircle(center, radius + 5,
            Paint()..color = AppColors.gold.withOpacity(0.18));
        canvas.drawCircle(
            center, radius + 4,
            Paint()
              ..color = AppColors.gold
              ..style = PaintingStyle.stroke
              ..strokeWidth = 2.4);
      }

      if (pl.isEstimated) {
        canvas.drawCircle(center, radius, Paint()..color = base.withOpacity(0.22));
        _drawDashedRing(canvas, center, radius + 2, base.withOpacity(0.55));
      } else {
        // Finom külső "halo" + tele token + perem (labdásnál arany, egyébként világos).
        canvas.drawCircle(center, radius + 3, Paint()..color = base.withOpacity(0.16));
        canvas.drawCircle(center, radius, Paint()..color = base);
        final isCarrier = pl.trackId == carrierId;
        canvas.drawCircle(
            center, radius + (isCarrier ? 2 : 0),
            Paint()
              ..color = isCarrier ? AppColors.gold : Colors.white.withOpacity(0.85)
              ..style = PaintingStyle.stroke
              ..strokeWidth = isCarrier ? 2.4 : 1.2);
      }

      // Kapus: szaggatott fehér gyűrű — ránézésre elkülönül a mezőnytől.
      if (pl.role == "kapus") {
        _drawDashedRing(
            canvas, center, radius + 4, Colors.white.withOpacity(0.9));
      }

      if (pl.jerseyNumber != null) {
        _drawLabel(canvas, center, "${pl.jerseyNumber}", radius);
      } else if (pl.role == "kapus") {
        _drawLabel(canvas, center, "K", radius);
      }
    }

    // Labda — meleg szín, finom izzással. (A `ball` fentebb már deklarálva.)
    if (ball != null) {
      final c = p(ball.x, ball.y);
      canvas.drawCircle(c, 0.6 * scale, Paint()..color = AppColors.ball.withOpacity(0.25));
      canvas.drawCircle(c, 0.34 * scale, Paint()..color = AppColors.ball);
    }
  }

  void _drawDashedRing(Canvas canvas, Offset center, double radius, Color color) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.4;
    const dashes = 16;
    for (int i = 0; i < dashes; i++) {
      if (i.isOdd) continue;
      final a0 = (2 * math.pi) * (i / dashes);
      final a1 = (2 * math.pi) * ((i + 1) / dashes);
      canvas.drawArc(Rect.fromCircle(center: center, radius: radius), a0, a1 - a0, false, paint);
    }
  }

  void _drawLabel(Canvas canvas, Offset center, String text, double radius) {
    final tp = TextPainter(
      text: TextSpan(
        text: text,
        style: TextStyle(
          color: Colors.white,
          fontSize: math.max(8, radius * 0.85),
          fontWeight: FontWeight.bold,
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    tp.paint(canvas, center - Offset(tp.width / 2, tp.height / 2));
  }

  @override
  bool shouldRepaint(covariant CourtPainter old) =>
      old.frame != frame || old.selectedId != selectedId || old.trail != trail;
}
