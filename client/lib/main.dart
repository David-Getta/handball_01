/// A Flutter-kliens belépési pontja (desktop-first, prémium sötét téma).
///
/// Ugyanaz a kódbázis fut Windows/Mac/Linux desktopon és tableten (iPad/Android).
/// Indítás (asztali, lokális teszt): `flutter run -d windows` (vagy macos/linux).
library;

import "package:flutter/material.dart";

import "theme/app_theme.dart";
import "ui/match_screen.dart";

void main() {
  runApp(const HandballApp());
}

class HandballApp extends StatelessWidget {
  const HandballApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: "Handball Analytics",
      debugShowCheckedModeBanner: false,
      theme: AppTheme.dark,
      home: const MatchScreen(),
    );
  }
}
