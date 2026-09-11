import "dart:math" as math;

import "package:flutter/material.dart";

import "../theme/app_theme.dart";

/// A Sport Machine JELKÉPE (logó) — rajzolva, nem képfájlból.
///
/// UGYANAZ a geometria, mint a gépen látszó ikonoké
/// (`packaging/make_icons.py`: telepítő, asztali parancsikon, ablak-ikon),
/// hogy a márka az appban és az operációs rendszerben egy család legyen:
/// felülnézeti pálya (a termék fő képe), a két kapuelőtér arany félköre,
/// és egy labda a mozgás-nyomával (a gépi követés).
///
/// Rajzolt jelkép, mert a Flutter platform-mappái a kiadáskor generálódnak
/// (nincs a repóban asset-könyvtár): így a logó minden felületen ott van,
/// és élesen skálázódik 16-tól 512 pixelig.
class SportMachineLogo extends StatelessWidget {
  /// A jelkép oldalhossza képpontban.
  final double size;

  /// Lekerekített sötét háttér (ikon-alak). Ha false, csak a pálya-rajz
  /// látszik — átlátszó háttéren.
  final bool background;

  const SportMachineLogo({super.key, this.size = 28, this.background = true});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size,
      height: size,
      child: CustomPaint(
        painter: _LogoPainter(background: background),
        isComplex: false,
      ),
    );
  }
}

/// A jelkép arányai az egység-négyzetben — a `packaging/make_icons.py`
/// azonos nevű konstansaival egyeznek (ha itt változik, ott is kell).
class _LogoPainter extends CustomPainter {
  final bool background;
  _LogoPainter({required this.background});

  static const double cornerR = 0.22;
  static const double courtX0 = 0.10, courtX1 = 0.90;
  static const double courtY0 = 0.245, courtY1 = 0.755;
  static const double courtR = 0.06;
  static const double lineW = 0.045;
  static const double goalR = 0.155;
  static const double ballCx = 0.655, ballCy = 0.375, ballR = 0.075;

  @override
  void paint(Canvas canvas, Size size) {
    final s = size.shortestSide;
    double u(double v) => v * s;
    final courtRect = RRect.fromLTRBR(u(courtX0), u(courtY0), u(courtX1),
        u(courtY1), Radius.circular(u(courtR)));

    if (background) {
      canvas.drawRRect(
        RRect.fromLTRBR(0, 0, u(1), u(1), Radius.circular(u(cornerR))),
        Paint()..color = const Color(0xFF0E141C),
      );
    }
    // A pálya sötét kitöltése.
    canvas.drawRRect(courtRect, Paint()..color = const Color(0xFF0B1C24));

    // Kapuelőtér-ívek: a két alapvonalról benyúló arany félkörök. A
    // pályán kívülre eső részüket levágjuk (a rajz így "beépül").
    canvas.save();
    canvas.clipRRect(courtRect);
    final ivPaint = Paint()
      ..color = AppColors.gold
      ..style = PaintingStyle.stroke
      ..strokeWidth = u(lineW);
    final cy = u((courtY0 + courtY1) / 2);
    canvas.drawArc(
        Rect.fromCircle(center: Offset(u(courtX0), cy), radius: u(goalR)),
        -80 * math.pi / 180, 160 * math.pi / 180, false, ivPaint);
    canvas.drawArc(
        Rect.fromCircle(center: Offset(u(courtX1), cy), radius: u(goalR)),
        100 * math.pi / 180, 160 * math.pi / 180, false, ivPaint);
    canvas.restore();

    // Pálya-keret + felezővonal.
    final vonal = Paint()
      ..color = AppColors.accent
      ..style = PaintingStyle.stroke
      ..strokeWidth = u(lineW);
    canvas.drawLine(Offset(u(0.5), u(courtY0)), Offset(u(0.5), u(courtY1)),
        vonal);
    canvas.drawRRect(courtRect, vonal);

    // A labda mozgás-nyoma (a gépi követés), majd maga a labda.
    const nyom = [
      [0.505, 0.560, 0.028, 0.35],
      [0.565, 0.485, 0.038, 0.55],
      [0.615, 0.425, 0.050, 0.75],
    ];
    for (final p in nyom) {
      canvas.drawCircle(Offset(u(p[0]), u(p[1])), u(p[2]),
          Paint()..color = AppColors.accent.withOpacity(p[3]));
    }
    canvas.drawCircle(Offset(u(ballCx), u(ballCy)), u(ballR),
        Paint()..color = AppColors.ball);
  }

  @override
  bool shouldRepaint(covariant _LogoPainter old) =>
      old.background != background;
}
