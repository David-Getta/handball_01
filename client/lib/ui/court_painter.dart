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
    // ELHALVÁNYULÓ farok: a régi szakaszok halványak és vékonyak, a
    // frissek erősek — így a nyomvonalon LÁTSZIK a mozgás iránya, nem
    // csak az útvonal alakja.
    final pts = [for (final o in tr) p(o.dx, o.dy)];
    for (var i = 0; i + 1 < pts.length; i++) {
      final t = (i + 1) / (pts.length - 1); // 0 (régi) .. 1 (friss)
      canvas.drawLine(
          pts[i],
          pts[i + 1],
          Paint()
            ..color = AppColors.gold.withOpacity(0.10 + 0.70 * t)
            ..style = PaintingStyle.stroke
            ..strokeWidth = 1.0 + 1.6 * t
            ..strokeCap = StrokeCap.round);
    }
    // A nyomvonal kezdőpontja: kis pötty, hogy látszódjon, honnan indult.
    canvas.drawCircle(pts.first, 3,
        Paint()..color = AppColors.gold.withOpacity(0.35));
  }

  void _drawCourt(Canvas canvas, Offset Function(double, double) p, double scale) {
    final fill = Paint()..color = AppColors.courtFill;
    final line = Paint()
      ..color = AppColors.courtLine
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.4;

    // Pálya háttér: finom függőleges színátmenet (a lapos folt helyett
    // mélység — mint a jól világított csarnok parkettája), lekerekítve,
    // alatta puha árnyékkal, hogy a pálya "ráüljön" a felületre.
    final court = Rect.fromPoints(p(0, 0), p(courtLength, courtWidth));
    final rrect = RRect.fromRectAndRadius(court, const Radius.circular(12));
    canvas.drawShadow(
        Path()..addRRect(rrect), Colors.black.withOpacity(0.6), 10, false);
    fill.shader = LinearGradient(
      begin: Alignment.topCenter,
      end: Alignment.bottomCenter,
      colors: [
        Color.lerp(AppColors.courtFill, Colors.white, 0.045)!,
        AppColors.courtFill,
        Color.lerp(AppColors.courtFill, Colors.black, 0.25)!,
      ],
    ).createShader(court);
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

    // 9 m-es SZABADDOBÁSI vonal — szabálykönyv szerint szaggatott. Ettől
    // olvasható a kép igazi kézilabda-pályaként (és a fal helyzete is
    // ehhez viszonyítva értelmezhető).
    final dashLine = Paint()
      ..color = AppColors.courtLine.withOpacity(0.75)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.2
      ..strokeCap = StrokeCap.round;
    for (final leftSide in [true, false]) {
      final pts = freeThrowBoundary(leftSide: leftSide, segments: 22)
          .map((o) => p(o.dx, o.dy))
          .toList();
      // Minden második szakaszt húzzuk meg — ez adja a szaggatást.
      for (var i = 0; i + 1 < pts.length; i += 2) {
        canvas.drawLine(pts[i], pts[i + 1], dashLine);
      }
    }

    // 7 m-es (hetes) vonal és 4 m-es kapus-vonal mindkét kapunál.
    final markPaint = Paint()
      ..color = AppColors.courtLine
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.6
      ..strokeCap = StrokeCap.round;
    final cy = courtWidth / 2;
    for (final gx in [0.0, courtLength]) {
      final sx = gx == 0.0 ? sevenMeterX : courtLength - sevenMeterX;
      canvas.drawLine(p(sx, cy - sevenMeterHalfLen),
          p(sx, cy + sevenMeterHalfLen), markPaint);
      final kx = gx == 0.0 ? keeperLineX : courtLength - keeperLineX;
      canvas.drawLine(p(kx, cy - keeperLineHalfLen),
          p(kx, cy + keeperLineHalfLen), markPaint);
    }

    // Kapuk (a gólvonal közepén, 3 m szélesen) — a kapufák között finom
    // háló-rács, hogy a kapu kapunak nézzen ki, ne puszta vastag vonalnak.
    final goalPaint = Paint()
      ..color = AppColors.textSecondary
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.round;
    final netPaint = Paint()
      ..color = AppColors.textFaint.withOpacity(0.45)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 0.7;
    for (final gx in [0.0, courtLength]) {
      final depth = (gx == 0.0 ? -1 : 1) * 1.0; // 1 m mély háló kifelé
      canvas.drawLine(p(gx, cy - 1.5), p(gx, cy + 1.5), goalPaint);
      // Háló: néhány párhuzamos és merőleges szál a kapu mögött.
      for (var i = 1; i <= 3; i++) {
        final t = i / 4.0;
        canvas.drawLine(p(gx + depth * t, cy - 1.5), p(gx + depth * t, cy + 1.5),
            netPaint);
      }
      for (var i = 0; i <= 4; i++) {
        final y = cy - 1.5 + 3.0 * (i / 4.0);
        canvas.drawLine(p(gx, y), p(gx + depth, y), netPaint);
      }
    }
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
        // Vetett árnyék: a token "a pálya fölött" ül, nem rá van festve.
        _softGlow(canvas, center + const Offset(0, 2), radius + 3,
            Colors.black.withOpacity(0.45));
        // Finom külső "halo" + gömbölyű (sugaras átmenetű) token.
        canvas.drawCircle(center, radius + 3, Paint()..color = base.withOpacity(0.16));
        canvas.drawCircle(
            center,
            radius,
            Paint()
              ..shader = RadialGradient(
                center: const Alignment(-0.35, -0.4),
                colors: [
                  Color.lerp(base, Colors.white, 0.34)!,
                  base,
                  Color.lerp(base, Colors.black, 0.22)!,
                ],
                stops: const [0.0, 0.55, 1.0],
              ).createShader(Rect.fromCircle(center: center, radius: radius)));
        final isCarrier = pl.trackId == carrierId;
        if (isCarrier) {
          // A labdás ember arany ragyogást is kap — a szem rögtön a
          // labda körüli eseményre néz.
          _softGlow(canvas, center, radius + 9,
              AppColors.gold.withOpacity(0.34));
        }
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
      _softGlow(canvas, c, 1.0 * scale, AppColors.ball.withOpacity(0.38));
      canvas.drawCircle(c, 0.6 * scale,
          Paint()..color = AppColors.ball.withOpacity(0.22));
      canvas.drawCircle(
          c,
          0.34 * scale,
          Paint()
            ..shader = RadialGradient(
              center: const Alignment(-0.3, -0.4),
              colors: [
                Color.lerp(AppColors.ball, Colors.white, 0.45)!,
                AppColors.ball,
              ],
            ).createShader(Rect.fromCircle(center: c, radius: 0.34 * scale)));
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

  /// Puha, kör alakú ragyogás vagy árnyék — ELMOSÁS NÉLKÜL, sugaras
  /// színátmenettel.
  ///
  /// A pálya MINDEN képkockán újrarajzolódik (lejátszás közben 25-ször
  /// másodpercenként), és a MaskFilter.blur rajzonként külön rajz-menetet
  /// kényszerít ki. Tizennégy játékos árnyéka + a labdás ember ragyogása
  /// + a labda izzása képkockánként tucatnyi ilyen menetet jelentene —
  /// gyengébb gépen ettől akadozik a lejátszás. A színátmenet ugyanezt a
  /// lágyságot adja egyetlen kitöltésből.
  void _softGlow(Canvas canvas, Offset center, double radius, Color color) {
    canvas.drawCircle(
        center,
        radius,
        Paint()
          ..shader = RadialGradient(
            colors: [color, color.withOpacity(0)],
            stops: const [0.42, 1.0],
          ).createShader(Rect.fromCircle(center: center, radius: radius)));
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
