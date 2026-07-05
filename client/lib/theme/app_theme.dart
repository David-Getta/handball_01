/// Dizájnrendszer — a "Sport Machine" design alapján (pontos tokenek).
///
/// Sötét, prémium felület: mély háttér, finom kártyák, teal akcentus + diszkrét
/// arany. A színek a hivatalos design-exportból származnak.
library;

import "package:flutter/material.dart";

class AppColors {
  // Háttér és felületek.
  static const bg = Color(0xFF0A0E13);          // app háttér
  static const bgSidebar = Color(0xFF0C1017);   // oldalsáv (sötétebb)
  static const surface = Color(0xFF10151D);      // kártyák
  static const surfaceAlt = Color(0xFF1E2530);   // belső csempék / kiemelés
  static const border = Color(0xFF212A36);       // finom keret
  static const borderStrong = Color(0xFF2A3444);

  // Szöveg.
  static const textPrimary = Color(0xFFEAEEF5);
  static const textSecondary = Color(0xFF93A0B4);
  static const textFaint = Color(0xFF6E7B8F);

  // Akcentusok.
  static const accent = Color(0xFF2FD9C4);      // teal — elsődleges
  static const accentSoft = Color(0x262FD9C4);  // teal halvány kitöltés
  static const gold = Color(0xFFD8B36B);        // diszkrét prémium kiemelés
  static const onAccent = Color(0xFF06121F);    // szöveg akcentuson

  // Csapatszínek / labda (megjelenítés).
  static const home = Color(0xFF4C9AFF);
  static const away = Color(0xFFFF6B6B);
  static const ball = Color(0xFFFFC857);

  // Pálya.
  static const courtFill = Color(0xFF10151D);
  static const courtLine = Color(0xFF37414F);
}

class AppSpacing {
  static const xs = 4.0;
  static const sm = 8.0;
  static const md = 12.0;
  static const lg = 16.0;
  static const xl = 24.0;
  static const xxl = 32.0;
}

class AppText {
  static const TextStyle title =
      TextStyle(fontSize: 26, fontWeight: FontWeight.w700, color: AppColors.textPrimary, letterSpacing: 0.2);

  static const TextStyle subtitle =
      TextStyle(fontSize: 13, color: AppColors.textSecondary, letterSpacing: 0.3);

  /// Szekciócímke: kicsi, NAGYBETŰS, erősen ritkított (a design jellegzetessége).
  static const TextStyle sectionLabel = TextStyle(
      fontSize: 11, fontWeight: FontWeight.w700, color: AppColors.textFaint, letterSpacing: 2.0);

  static const TextStyle label =
      TextStyle(fontSize: 13, color: AppColors.textSecondary);

  static const TextStyle value =
      TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: AppColors.textPrimary);

  static const TextStyle statBig = TextStyle(
      fontSize: 40, fontWeight: FontWeight.w800, color: AppColors.textPrimary, letterSpacing: 0.5);

  static const TextStyle valueBig = TextStyle(
      fontSize: 22, fontWeight: FontWeight.w700, color: AppColors.textPrimary, letterSpacing: 0.3);

  static const TextStyle brand = TextStyle(
      fontSize: 15, fontWeight: FontWeight.w800, color: AppColors.textPrimary, letterSpacing: 1.5);

  /// Breadcrumb-stílus a felső sávhoz (nagyon ritkított, halvány).
  static const TextStyle crumb = TextStyle(
      fontSize: 12, fontWeight: FontWeight.w600, color: AppColors.textFaint, letterSpacing: 2.5);
}

class AppTheme {
  static ThemeData get dark {
    final scheme = const ColorScheme.dark(
      surface: AppColors.surface,
      primary: AppColors.accent,
      secondary: AppColors.gold,
      onPrimary: AppColors.onAccent,
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

  /// Egységes kártya-dekoráció (lekerekített, finom kerettel).
  static BoxDecoration card({Color? color, Color? borderColor}) => BoxDecoration(
        color: color ?? AppColors.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: borderColor ?? AppColors.border, width: 1),
      );
}
