/// Dizájnrendszer — egy PRÉMIUM, letisztult, sötét megjelenés.
///
/// Egy helyen definiálja a színeket, tipográfiát és térközöket, hogy az egész app
/// egységes, igényes (nem "olcsó") élményt adjon. Sötét alap, visszafogott
/// kontraszt, egy elegáns akcentus (teal) + diszkrét arany kiemelés.
library;

import "package:flutter/material.dart";

/// Az alkalmazás színpalettája.
class AppColors {
  // Háttér és felületek (mély, közel fekete, enyhe kék árnyalattal).
  static const bg = Color(0xFF0B0E13);
  static const surface = Color(0xFF151A22);
  static const surfaceAlt = Color(0xFF1B212B);
  static const border = Color(0xFF2A323E);

  // Szöveg.
  static const textPrimary = Color(0xFFE8ECF2);
  static const textSecondary = Color(0xFF8B95A7);
  static const textFaint = Color(0xFF5A6475);

  // Akcentusok.
  static const accent = Color(0xFF2DD4BF);     // teal — elsődleges
  static const accentSoft = Color(0x332DD4BF);  // teal halvány (kitöltéshez)
  static const gold = Color(0xFFE5B567);        // diszkrét prémium kiemelés

  // Csapatszínek (megjelenítés, nem a valódi mez).
  static const home = Color(0xFF4C9AFF);
  static const away = Color(0xFFFF6B6B);
  static const ball = Color(0xFFFFC857);

  // Pálya.
  static const courtFill = Color(0xFF10151C);
  static const courtLine = Color(0xFF3A4350);
}

/// Egységes térközök (8 alapú skála).
class AppSpacing {
  static const xs = 4.0;
  static const sm = 8.0;
  static const md = 12.0;
  static const lg = 16.0;
  static const xl = 24.0;
  static const xxl = 32.0;
}

/// Gyakori szövegstílusok (a prémium érzethez: ritkított, finom hierarchia).
class AppText {
  static const TextStyle title =
      TextStyle(fontSize: 18, fontWeight: FontWeight.w600, color: AppColors.textPrimary, letterSpacing: 0.2);

  /// Szekciócímke: kicsi, NAGYBETŰS, ritkított — diszkrét, igényes tagolás.
  static const TextStyle sectionLabel = TextStyle(
      fontSize: 11, fontWeight: FontWeight.w700, color: AppColors.textSecondary, letterSpacing: 1.4);

  static const TextStyle label =
      TextStyle(fontSize: 13, color: AppColors.textSecondary);

  static const TextStyle value =
      TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppColors.textPrimary);

  static const TextStyle valueBig = TextStyle(
      fontSize: 22, fontWeight: FontWeight.w700, color: AppColors.textPrimary, letterSpacing: 0.3);

  static const TextStyle brand = TextStyle(
      fontSize: 15, fontWeight: FontWeight.w800, color: AppColors.textPrimary, letterSpacing: 2.0);
}

class AppTheme {
  /// A sötét, prémium téma.
  static ThemeData get dark {
    final scheme = const ColorScheme.dark(
      surface: AppColors.surface,
      primary: AppColors.accent,
      secondary: AppColors.gold,
      onPrimary: Color(0xFF06231F),
      onSurface: AppColors.textPrimary,
    );
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      scaffoldBackgroundColor: AppColors.bg,
      colorScheme: scheme,
      fontFamily: "Roboto",
      dividerColor: AppColors.border,
      sliderTheme: const SliderThemeData(
        activeTrackColor: AppColors.accent,
        inactiveTrackColor: AppColors.border,
        thumbColor: AppColors.accent,
        trackHeight: 3,
        overlayShape: RoundSliderOverlayShape(overlayRadius: 14),
      ),
      progressIndicatorTheme: const ProgressIndicatorThemeData(
        color: AppColors.accent,
        linearTrackColor: AppColors.border,
      ),
    );
  }

  /// Egységes "kártya" dekoráció (lekerekített, finom kerettel).
  static BoxDecoration card({Color? color}) => BoxDecoration(
        color: color ?? AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: AppColors.border, width: 1),
      );
}
