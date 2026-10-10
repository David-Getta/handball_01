import "package:flutter/material.dart";

/// A Sport Machine JELKÉPE (logó) — rajzolva, nem képfájlból.
///
/// UGYANAZ a geometria, mint a gépen látszó ikonoké
/// (`packaging/make_icons.py`: telepítő, asztali parancsikon, ablak-ikon)
/// és a márka vektoros forrásáé (`packaging/brand/sportmachine-mark-*.svg`),
/// hogy a márka az appban és az operációs rendszerben egy család legyen.
///
/// A jel négy ék egy 64 x 64-es rajzdobozban, két átlós sávba rendezve —
/// a mozgás és az elemzés iránya. Középpontosan szimmetrikus: 180 fokkal
/// elforgatva önmaga. A jelet nem forgatjuk és nem tükrözzük.
///
/// Rajzolt jelkép, mert a Flutter platform-mappái a kiadáskor generálódnak
/// (nincs a repóban asset-könyvtár): így a logó minden felületen ott van,
/// és élesen skálázódik 16-tól 512 pixelig.
class SportMachineLogo extends StatelessWidget {
  /// A jelkép oldalhossza képpontban.
  final double size;

  /// Lekerekített sötét háttér (ikon-alak). Ha false, csak a jel
  /// látszik — átlátszó háttéren.
  final bool background;

  /// Kétszínű változat: az alsó átló arany (a nyomtatott fejlécek jele).
  final bool duo;

  const SportMachineLogo(
      {super.key, this.size = 28, this.background = true, this.duo = false});

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: size,
      height: size,
      child: CustomPaint(
        painter: _LogoPainter(background: background, duo: duo),
        isComplex: false,
      ),
    );
  }
}

/// A jelkép ÖSSZEÁLLÓ változata: a négy ék a saját átlója mentén úszik be
/// (felső-bal pár fentről-balról, alsó-jobb pár lentről-jobbról), majd egy
/// halvány fénysáv végigfut rajta — a "gép dolgozik" jelzése.
///
/// A nyitóképernyőn (a motor indítása alatt) ismétlődik, máshol egyszer
/// fut le. Külön widget, hogy a fejlécben maradhasson a statikus jel:
/// egy folyton mozgó logó a munkaképernyőn zavaró lenne.
class SportMachineLogoAnimated extends StatefulWidget {
  final double size;
  final bool background;

  /// Ismétlődjön-e (várakozás alatt igen, egyszeri bemutatáskor nem).
  final bool loop;

  const SportMachineLogoAnimated(
      {super.key, this.size = 66, this.background = true, this.loop = true});

  @override
  State<SportMachineLogoAnimated> createState() =>
      _SportMachineLogoAnimatedState();
}

class _SportMachineLogoAnimatedState extends State<SportMachineLogoAnimated>
    with SingleTickerProviderStateMixin {
  late final AnimationController _c = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 2200),
  );

  @override
  void initState() {
    super.initState();
    if (widget.loop) {
      _c.repeat();
    } else {
      _c.forward();
    }
  }

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: widget.size,
      height: widget.size,
      child: AnimatedBuilder(
        animation: _c,
        builder: (_, __) => CustomPaint(
          painter: _LogoPainter(
              background: widget.background, progress: _c.value),
          isComplex: false,
        ),
      ),
    );
  }
}

/// A jelkép arányai az egység-négyzetben — a `packaging/make_icons.py`
/// azonos nevű konstansaival egyeznek (ha itt változik, ott is kell).
class _LogoPainter extends CustomPainter {
  final bool background;
  final bool duo;

  /// 0..1 — az összeállás állapota. 1 = kész jel (statikus rajz).
  final double progress;

  _LogoPainter(
      {required this.background, this.duo = false, this.progress = 1.0});

  // Márka-színek (packaging/brand/README.txt).
  static const Color ink = Color(0xFF06121F); // Court Ink
  static const Color teal = Color(0xFF2FD9C4); // Signal Teal
  static const Color gold = Color(0xFFD8B36B); // Medal Gold
  static const Color paper = Color(0xFFEAEEF5); // Paper

  static const double cornerR = 0.22;
  static const double markBox = 64.0;
  static const double markInset = 0.08;

  /// A négy ék a 64-es rajzdobozban (a márka SVG-jének pontjai).
  static const List<List<List<double>>> mark = [
    [
      [23, 7],
      [49, 7],
      [28, 28],
      [28, 15],
      [15, 15]
    ],
    [
      [11, 19],
      [24, 19],
      [24, 32],
      [7, 49],
      [7, 23]
    ],
    [
      [57, 15],
      [57, 41],
      [49, 49],
      [49, 36],
      [36, 36]
    ],
    [
      [32, 40],
      [45, 40],
      [45, 53],
      [41, 57],
      [15, 57]
    ],
  ];

  @override
  void paint(Canvas canvas, Size size) {
    final s = size.shortestSide;
    double u(double v) => v * s;

    if (background) {
      canvas.drawRRect(
        RRect.fromLTRBR(0, 0, u(1), u(1), Radius.circular(u(cornerR))),
        Paint()..color = ink,
      );
    }

    // Összeállás közben az ékek a csempén KÍVÜLRŐL érkeznek: a csempe
    // alakjára vágunk, hogy a jel a saját keretén belül maradjon (a kész,
    // háttér nélküli jelnél nincs mit vágni).
    final vag = background || progress < 1.0;
    if (vag) {
      canvas.save();
      canvas.clipRRect(
          RRect.fromLTRBR(0, 0, u(1), u(1), Radius.circular(u(cornerR))));
    }

    final belso = s * (1.0 - 2 * markInset);
    final perem = s * markInset;
    Offset pont(List<double> p) => Offset(
        perem + p[0] / markBox * belso, perem + p[1] / markBox * belso);

    Path ekPath(List<List<double>> ek) {
      final path = Path()..moveTo(pont(ek[0]).dx, pont(ek[0]).dy);
      for (var i = 1; i < ek.length; i++) {
        path.lineTo(pont(ek[i]).dx, pont(ek[i]).dy);
      }
      return path..close();
    }

    // Összeállás: minden ék a SAJÁT átlója felől úszik be, késleltetve.
    // A felső-bal pár (0, 1) fentről-balról, az alsó-jobb (2, 3)
    // lentről-jobbról — a jel két sávja így "összezár".
    final teljes = Path();
    for (var i = 0; i < mark.length; i++) {
      final kesleltetes = i * 0.10;
      final nyers = ((progress - kesleltetes) / 0.45).clamp(0.0, 1.0);
      final p = Curves.easeOutCubic.transform(nyers);
      final irany = i < 2 ? -1.0 : 1.0;
      final el = (1.0 - p) * s * 0.28 * irany;
      final path = ekPath(mark[i]).shift(Offset(el, el));
      teljes.addPath(path, Offset.zero);
      canvas.drawPath(
          path,
          Paint()
            ..color = (duo && i >= 2 ? gold : teal)
                .withOpacity(0.15 + 0.85 * p));
    }

    // Fénysáv: az összeállás után egyszer végigfut a jelen (a "gép
    // beolvas" mozdulat). Csak a jelre látszik: a négy ékre vágjuk.
    if (progress > 0.55 && progress < 1.0) {
      final t = ((progress - 0.55) / 0.45).clamp(0.0, 1.0);
      canvas.save();
      canvas.clipPath(teljes);
      final x = -0.4 * s + t * 1.8 * s;
      canvas.drawRect(
        Rect.fromLTWH(x, -s, s * 0.22, s * 3),
        Paint()
          ..color = paper.withOpacity(0.35 * (1.0 - (t - 0.5).abs() * 2))
          ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 6),
      );
      canvas.restore();
    }

    if (vag) {
      canvas.restore();
    }
  }

  @override
  bool shouldRepaint(covariant _LogoPainter old) =>
      old.background != background ||
      old.duo != duo ||
      old.progress != progress;
}

/// A SPORTMACHINE SZÓKÉP — RAJZOLT betűkkel, nem fonttal.
///
/// A márka forrása `packaging/brand/sportmachine-wordmark-*.svg`, és
/// ugyanezek a betű-útvonalak élnek a nyomtatható jelentésekben is
/// (`report_html.WORDMARK_LETTERS`). Verzálmagasság 72, a SPORT vonala
/// 14, a MACHINE-é 6; minden sarok 45°-ra letörve, a végződések laposak,
/// a sarkok mitráltak. Így a szókép betűtípus nélkül, minden gépen és
/// minden méretben ugyanaz — és nem lehet véletlenül "újraszedni".
class SportMachineWordmark extends StatelessWidget {
  /// A szókép MAGASSÁGA képpontban (a szélesség ebből adódik).
  final double height;

  /// Sötét felületre (papír-fehér + halvány szürke) vagy világosra
  /// (tinta + szürke).
  final bool dark;

  /// Egy súly: a MACHINE is a vastag vonallal — kis méretre, ahol a
  /// vékony szár eltűnne (a márkakönyv "single-weight" változata).
  final bool singleWeight;

  const SportMachineWordmark(
      {super.key,
      this.height = 22,
      this.dark = true,
      this.singleWeight = false});

  static const double boxW = 840.0;
  static const double boxH = 72.0;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: height * boxW / boxH,
      height: height,
      child: CustomPaint(
        painter: _WordmarkPainter(dark: dark, singleWeight: singleWeight),
        isComplex: false,
      ),
    );
  }
}

class _WordmarkPainter extends CustomPainter {
  final bool dark;
  final bool singleWeight;
  _WordmarkPainter({required this.dark, required this.singleWeight});

  /// (útvonal, vízszintes eltolás a 840-es sorban, vonalvastagság).
  /// A betűk CSAK M (mozgás) és L (vonal) parancsokból állnak.
  static const List<(String, double, double)> letters = [
    ("M53 21 L39 7 L21 7 L7 21 L7 29 L14 36 L46 36 L53 43 L53 51 L39 65 "
        "L21 65 L7 51", 0, 14),
    ("M7 65 L7 7 L39 7 L53 21 L53 26 L39 40 L7 40", 72, 14),
    ("M7 23 L23 7 L37 7 L53 23 L53 49 L37 65 L23 65 L7 49 Z", 144, 14),
    ("M7 65 L7 7 L39 7 L53 21 L53 26 L39 40 L7 40 M33 40 L53 65", 216, 14),
    ("M7 7 L53 7 M30 7 L30 65", 288, 14),
    ("M7 65 L7 7 L34 40 L61 7 L61 65", 370, 6),
    ("M7 65 L7 21 L21 7 L39 7 L53 21 L53 65 M7 44 L53 44", 450, 6),
    ("M53 21 L39 7 L21 7 L7 21 L7 51 L21 65 L39 65 L53 51", 522, 6),
    ("M7 7 L7 65 M53 7 L53 65 M7 36 L53 36", 594, 6),
    ("M15 7 L15 65", 666, 6),
    ("M7 65 L7 7 L53 65 L53 7", 708, 6),
    ("M53 7 L7 7 L7 65 L53 65 M7 36 L41 36", 780, 6),
  ];

  /// A betű útvonalának felépítése: "M x y L x y … [Z]" — a márka
  /// SVG-jében csak ez a három parancs szerepel.
  Path _parse(String d, double dx, double s) {
    final path = Path();
    var i = 0;
    final darabok = d.split(RegExp(r"[\s,]+"));
    while (i < darabok.length) {
      final t = darabok[i];
      if (t == "Z" || t == "z") {
        path.close();
        i += 1;
        continue;
      }
      final parancs = t[0];
      final elso = t.length > 1 ? t.substring(1) : darabok[++i];
      final x = (double.parse(elso) + dx) * s;
      final y = double.parse(darabok[++i]) * s;
      if (parancs == "M") {
        path.moveTo(x, y);
      } else {
        path.lineTo(x, y);
      }
      i += 1;
    }
    return path;
  }

  @override
  void paint(Canvas canvas, Size size) {
    final s = size.height / SportMachineWordmark.boxH;
    final eros = dark ? _LogoPainter.paper : _LogoPainter.ink;
    final halk = dark ? const Color(0xFF93A0B4) : const Color(0xFF5C6676);
    for (final (d, dx, vastag) in letters) {
      final egySuly = singleWeight;
      canvas.drawPath(
        _parse(d, dx, s),
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = (egySuly ? 14.0 : vastag) * s
          ..strokeCap = StrokeCap.butt
          ..strokeJoin = StrokeJoin.miter
          ..color = (vastag == 14 || egySuly) ? eros : halk,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _WordmarkPainter old) =>
      old.dark != dark || old.singleWeight != singleWeight;
}
